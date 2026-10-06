# Plan: Unified Streaming Large-File Upload

Status: **Approved** 2026-10-06 (Phase 2: Plan + Phase 3: Tasks) — implementation in progress
Spec: [SPEC.md](SPEC.md) (approved 2026-10-06)

## Components and dependencies

```
P1 ragfs core ──────────────┐
  T1 trait defaults         │
  T2–T4 wrapper forwarding  ├─▶ P1b bindings ─▶ P2 server/ingest ─┬─▶ P4 sessions ─▶ P5 Go/TS + docs
  T5 localfs  T6–T7 s3fs    │   T8 ragfs-py      T10 staging      │     T15–T17 server
                            │   T9 VikingFS      T11–T12 ingest   │     T18–T21 clients
                            │                    T13 shared mode  │
                            └──────────────── P3 limits (T14) ────┘  (P3 only needs P2)
```

- **P1 is the foundation.** No other layer can stream until ragfs can.
- **P2 removes the pod-side whole-file reads.** It fixes pod memory for every existing client with no API change. This is the biggest win for your deployment.
- **P3** removes the 10 MB Web Studio cap while still using the legacy single request. That request already streams to disk in `local` mode.
- **P4** adds the chunked protocol: resume, client-side bounded memory, folders without zip.
- **P5** covers the remaining SDKs and docs.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| A wrapper doesn't forward `write_from_path`, so the path silently falls back to buffered (correct but not streaming) | Per-wrapper unit test with a spy inner FS that asserts the inner `write_from_path` was called |
| Pathlock or cache semantics drift from `write` | Each forwarder copies the exact lock/invalidate code of that wrapper's `write`; reuse the existing `write` tests parametrised over both methods |
| Orphaned S3 multipart parts after a crash | `AbortMultipartUpload` on every error path; document a bucket lifecycle rule (`AbortIncompleteMultipartUpload` after 1 day) |
| SeaweedFS multipart behaves differently from AWS/TOS | Integration test is env-gated; run it against SeaweedFS in dev and against a real bucket before release |
| `staged_source` change touches **every** `add_resource` | Keep concurrency and symlink rules; run the full `tests/resource` + `tests/server` suites; behaviour-identical tests for small files |
| Worker temp disk fills up (paths replace RAM) | Materialize under the workspace temp dir, clean up in `finally`, document disk sizing (≈ 2–3× upload) |
| Encrypted mounts: new 512 MiB cap rejects writes that used to succeed (with huge RAM) | Clear error message; documented in config docs; encryption is off in the current deployment |
| Regenerating the Web Studio client needs a live server on :1933 | Run the server locally from the branch during T14/T21 |
| vitest hangs on `/mnt/c`, and pyo3 needs a rebuild | Use the commands in SPEC.md (native-fs copy; `make build`) |
| Measuring pod RSS inside pytest includes test noise | Memory test runs ingest in a **subprocess** and reads its `VmHWM` |

## Verification checkpoints

- **A (after T9):** `cargo test -p ragfs`, the s3 integration test against SeaweedFS, `make build`, `pytest tests/storage tests/pyagfs`.
- **B (after T13):** memory regression test (1 GiB direct-upload file, local and shared mode, S3 AGFS) ≤ 128 MiB; existing `tests/server` + `tests/resource` + `tests/parse` pass. → **Success criteria 1, 2, 3.**
- **C (after T14):** Web Studio uploads a 1 GiB file through the legacy endpoint; changing `max_file_bytes` changes the UI limit. → **Criterion 6 (partly).**
- **D (after T21):** criteria 4, 5, 6, 7, 8; manual E2E checklist.

## Parallel work

- T5 ∥ T6–T7 (after T1–T4)
- T10 ∥ T11–T12 ∥ T13 (after T9)
- T18 ∥ T19 ∥ T20–T21 (after T17)
- T22 ∥ T23 ∥ T24 (after T17)

## Tasks

Each task is TDD: write the failing test first. Each touches ≤ 5 files.

### P1 — ragfs streaming core (Rust)

- [x] **T1: Trait methods with buffered defaults**
  - Acceptance: `FileSystem::write_from_path(path, src, flags)` and `read_to_path(path, dst)` exist; the defaults use `self.write` / `self.read`; all existing impls compile unchanged.
  - Verify: `cargo test -p ragfs core::filesystem`; new tests on memfs (0 B, 1 B, 3 MiB round trip).
  - Files: `crates/ragfs/src/core/filesystem.rs`, `crates/ragfs/src/plugins/memfs/mod.rs` (tests)

- [x] **T2: Forward through Stats + PathLock wrappers**
  - Acceptance: both override and forward to the inner FS; PathLock takes the same lock as `write`; stats count as a write.
  - Verify: spy-inner tests assert forwarding plus lock acquire/release.
  - Files: `crates/ragfs/src/core/stats_wrapper.rs`, `crates/ragfs/src/lock/wrapper.rs`

- [x] **T3: Forward through Mountable + Cache + MultiWrite**
  - Acceptance: `ArcFileSystem` / `MountableFS` route to the mounted FS; `CachedFileSystem` invalidates like `write`. `MultiWriteWrappedFS` **keeps the buffered default** (decided during T3: async backup fan-out outlives the caller's temp file; see SPEC A), pinned by a test covering size redirects.
  - Verify: spy-inner tests; existing `tests/cache_wrapper.rs` passes.
  - Files: `crates/ragfs/src/core/mountable.rs`, `crates/ragfs/src/cache/wrapper.rs`, `crates/ragfs/src/core/multibackend_wrapper.rs`

- [x] **T4: Encryption wrapper: buffered + cap**
  - Acceptance: an explicit override checks the source size against a fixed 512 MiB cap (not yet configurable; see SPEC A), reads the file, then uses the existing temp+replace envelope write and returns the plaintext length. `read_to_path` decrypts to the file.
  - Verify: unit tests for under, at and over the cap, plus round trip.
  - Files: `crates/ragfs/src/core/encryption_wrapper.rs`, encryption config struct (`core/types.rs` or `builder.rs`)

- [x] **T5: localfs streaming override**
  - Acceptance: `write_from_path` streams through `tokio::fs`/`io::copy` while honouring `WriteFlag` (Create/CreateNew/Truncate); `read_to_path` streams out; path validation unchanged.
  - Verify: unit tests for each flag, missing parent → NotFound, 50 MiB round trip.
  - Files: `crates/ragfs/src/plugins/localfs/mod.rs`

- [x] **T6: s3 client multipart primitives**
  - Acceptance: `put_object_from_path` (single PUT using `ByteStream::from_path`) plus `multipart_upload_from_path` (create → parts read from file at `multipart_part_size_bytes` → complete; abort on any error); `get_object_to_path` (ranged loop). Thresholds come from mount config (16 MiB / 8 MiB defaults).
  - Verify: unit tests for part planning (sizes, last part, 10,000-part limit) and config parsing.
  - Files: `crates/ragfs/src/plugins/s3fs/client.rs`, s3fs config parsing in `s3fs/mod.rs`

- [x] **T7: s3fs overrides + integration test**
  - Acceptance: `S3FileSystem::write_from_path` picks single PUT vs multipart by size; CreateNew uses a conditional PUT below the threshold. Above it, `If-None-Match` on Complete if the backend supports it; otherwise HEAD-check + documented race. Caches invalidated; `read_to_path` uses the ranged loop.
  - Verify: `crates/ragfs/tests/s3_multipart_integration.rs` (`#[ignore]`, env `OV_S3_TEST_ENDPOINT`): 0 B, 1 B, threshold±1, 50 MiB; md5 matches; forced failure leaves no MPU (`ListMultipartUploads`).
  - Files: `crates/ragfs/src/plugins/s3fs/mod.rs`, `crates/ragfs/tests/s3_multipart_integration.rs`

- [ ] **T8: ragfs-python bindings**
  - Acceptance: `write_file_from_path(path, local_path, ctx=None)` and `read_file_to_path(path, local_path, ctx=None)` call `top.*`, release the GIL (`run_scoped`), and use the same ctx handling as `write`.
  - Verify: `make build`; pytest calling both through a memfs/localfs binding.
  - Files: `crates/ragfs-python/src/lib.rs`, `openviking/pyagfs/async_client.py` (+ sync client if separate)

- [ ] **T9: VikingFS path methods**
  - Acceptance: `VikingFS.write_file_from_path(uri, local_path, ctx, lease_ref, auto_pathlock)` performs exactly the same ACL check, URI mapping, parent-dir creation and pathlock ctx as `write_file_bytes`; `read_file_to_path(uri, local_path, ctx)` mirrors `read_file_bytes` access checks.
  - Verify: `tests/storage` unit tests: ACL denial, parent creation, round trip.
  - Files: `openviking/storage/viking_fs/_ops.py`, `tests/storage/test_viking_fs_path_io.py` (new)

**Checkpoint A**

### P2 — Server and ingest use paths (Python)

- [ ] **T10: Durable staging via paths**
  - Acceptance: `stage_source` file and dir branches and `_copy_local_tree` call `write_file_from_path`; `materialize_source` calls `read_file_to_path`. No `read_bytes` / `read_file_bytes` left in the module; concurrency and symlink skipping unchanged.
  - Verify: existing `tests/resource` pass; a new test with a spy VikingFS asserts path methods are used.
  - Files: `openviking/resource/staged_source.py`, its tests

- [ ] **T11: Parse output writer: path writes + incremental md5**
  - Acceptance: `ParseArtifactWriter.write_from_path(rel, local_path)` computes md5 in chunks and records it; `AgfsParseOutputStore` and `LocalParseOutputStore` implement path writes (copy for local).
  - Verify: unit tests: manifest md5 equals `content_md5` of the bytes; streamed hashing helper.
  - Files: `openviking/parse/output.py`, `openviking/utils/content_hash.py`

- [ ] **T12: DirectoryParser + media originals via paths**
  - Acceptance: direct-upload files and media originals use `write_from_path`. Text normalisation applies only to text ≤ `parsers.max_text_normalize_bytes` (16 MiB); everything else is copied raw.
  - Verify: existing `tests/parse` pass; new test: a 20 MiB text file is copied raw, a small text file is still normalised.
  - Files: `openviking/parse/parsers/directory.py`, `media/image.py`, `media/audio.py`, `openviking/parse/parsers/upload_utils.py`

- [ ] **T13: Shared temp-upload mode via paths**
  - Acceptance: `_save_shared` uses `write_file_from_path`; `_resolve_shared` uses `read_file_to_path`; both `read_bytes` / `read_file_bytes` calls removed.
  - Verify: `tests/server/test_temp_upload_store_async_io.py` passes, plus a new assertion with spy VikingFS.
  - Files: `openviking/server/temp_upload_store.py`, its tests

- [ ] **T13b: Memory regression test**
  - Acceptance: a subprocess harness ingests a 1 GiB direct-upload file (local and shared mode) against SeaweedFS AGFS and reports `VmHWM` delta.
  - Verify: delta ≤ 128 MiB (marked `slow`, env-gated).
  - Files: `tests/integration/test_upload_memory.py`

**Checkpoint B**

### P3 — One limit config

- [ ] **T14: `server.upload` config + limits endpoint + Web Studio reads it**
  - Acceptance: `UploadConfig` (`max_file_bytes` 2 GiB, `max_session_bytes` 5 GiB, `max_files` 10,000, `part_size_bytes` 8 MiB). `temp_upload.shared_max_size_bytes` becomes a deprecated alias with a startup warning. `temp_upload_store` enforces `max_file_bytes`. `GET /api/v1/uploads/limits` added. Web Studio fetches limits and removes the hard-coded 10 MB.
  - Verify: pytest for config alias precedence and endpoint; vitest for limit-driven validation; manual 1 GiB upload in Web Studio.
  - Files: `openviking/server/config.py`, `openviking/server/routers/uploads.py` (new; limits only), `openviking/server/app.py`, `web-studio/src/routes/resources/-lib/upload.ts`, `upload-resource-fields.tsx` (+ regenerated `src/gen/ov-client`)

**Checkpoint C**

### P4 — Chunked upload sessions

- [ ] **T15: Session store**
  - Acceptance: `UploadSessionStore`: create (validates paths with the `zip_safe` rules, sizes, counts against limits), `put_part` (streams the body to disk, ≤ part size, idempotent), `status`, `complete` (streams parts into files under `sessions/{id}/tree`, verifies sizes, returns `temp_file_id`), `abort`, TTL sweep (removes session dirs). Bound to account + user.
  - Verify: `tests/server/test_upload_sessions.py`: lifecycle, idempotent part, resume listing, traversal, oversize part/file/session, cross-user denial, expiry.
  - Files: `openviking/server/upload_sessions.py` (new), `tests/server/test_upload_sessions.py` (new)

- [ ] **T16: Session endpoints + directory temp ids**
  - Acceptance: `POST /uploads`, `PUT …/parts/{n}`, `GET /uploads/{id}`, `POST …/complete`, `DELETE`; auth via `get_upload_request_context`; 400/404/413 mapping. `_resolve_local` accepts session ids that resolve to a staged file or dir; the local TTL sweep removes directories.
  - Verify: API tests with TestClient; ingesting a folder session produces the same resources as the equivalent zip upload.
  - Files: `openviking/server/routers/uploads.py`, `openviking/server/temp_upload_store.py`, `openviking/server/resource_ingest.py`, tests

- [ ] **T17: Legacy `temp_upload` on the session code path**
  - Acceptance: `POST /resources/temp_upload` internally creates a single-part session (no chunk limit for this legacy path). Signed-token MCP flow is unchanged in behaviour.
  - Verify: `test_api_resources.py`, `test_resources_temp_upload_token.py` and `test_temp_upload_store_async_io.py` pass **unchanged**.
  - Files: `openviking/server/routers/resources.py`, `openviking/server/temp_upload_store.py`

- [ ] **T18: Python SDK session upload**
  - Acceptance: files and folders upload through sessions (folders without zip); falls back to legacy on 404; one reusable part buffer.
  - Verify: `sdk/python/tests` with a mock transport: part order and sizes, folder manifest, fallback.
  - Files: `sdk/python/openviking_sdk/client.py`, `sdk/python/openviking_sdk/_upload.py` (new), tests

- [ ] **T19: Rust CLI session upload**
  - Acceptance: `FileUploader` uses sessions with a reused `Vec` part buffer; folders without zip (honouring `ignore_dirs`); progress per part; falls back to legacy on 404.
  - Verify: `cargo test -p ov_cli` with a mock server.
  - Files: `crates/ov_cli/src/base_client.rs`, `crates/ov_cli/src/client.rs`, `crates/ov_cli/src/upload_session.rs` (new)

- [ ] **T20: Web Studio chunked uploader lib**
  - Acceptance: `uploadSession(files, opts)`: `Blob.slice` parts, 3 parallel PUTs, retry with backoff, resume via `GET /uploads/{id}` within the page session, progress callback, abort.
  - Verify: vitest with mocked client: slicing, resume skips received parts, retries, abort.
  - Files: `web-studio/src/routes/resources/-lib/chunked-upload.ts` (new), its test

- [ ] **T21: Web Studio wiring + folders without zip**
  - Acceptance: `use-resource-upload` uses `uploadSession`; a folder is one multi-file session; `zipFolder` and its dependency use removed; client regenerated.
  - Verify: vitest; manual: 1 GiB folder, Chrome tab memory ≤ +150 MiB, network-drop resume.
  - Files: `use-resource-upload.tsx`, `upload-resource-fields.tsx`, `-lib/folder-upload.ts`, `src/gen/ov-client/*` (generated)

**Checkpoint D**

### P5 — Remaining SDKs and docs

- [ ] **T22: Go SDK sessions** (`io.SectionReader`, no `bytes.Buffer` body) — `sdk/go/upload.go`, tests
- [ ] **T23: TS SDK sessions** (Node `FileHandle.read`, browser `Blob.slice`; drop `zipSync` from the upload path) — `sdk/typescript/src/{client,node-files}.ts`, tests
- [ ] **T24: Docs** — `docs/en/api/02-resources.md` (session API), `docs/en/guides/01-configuration.md` (`server.upload`, multipart thresholds, encryption cap, S3 lifecycle rule, pod disk sizing)

## Delivery

- One PR per phase (P1, P2, P3, P4, P5), each linking the SPEC section it implements.
- P1 + P2 alone deliver success criteria 1–3 for every existing client.
