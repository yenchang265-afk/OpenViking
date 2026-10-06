# Spec: Unified Streaming Large-File Upload

Status: **Approved** (Phase 1: Specify) — all open questions resolved as proposed, 2026-10-06
Date: 2026-10-06
Plan: [PLAN.md](PLAN.md)

## Assumptions

Correct any of these before Phase 2 (Plan):

1. Deployment of record: single OpenViking pod, AGFS backend `s3` (SeaweedFS locally, S3-compatible in prod), encryption **off**, `temp_upload.default_mode = local`. Multi-replica `shared` mode must work but is not the primary target.
2. Goal is bounded memory, not raw throughput. A slower upload with flat RSS is acceptable.
3. Large files are mostly documents, media and archives. Parsing a huge single file (e.g. 300 MB PDF) still loads it in the parser; that is **out of scope** here (see Open Questions).
4. No new third-party dependencies are needed: `aws-sdk-s3` already supports multipart; browser `Blob.slice`, Go `io.SectionReader`, Node `fs.FileHandle.read` and Python file seek are stdlib.
5. Existing clients and the existing `POST /api/v1/resources/temp_upload` contract (single multipart request, zip for folders) must keep working unchanged.
6. MCP agents keep uploading with one `curl -F file=@…` to the signed URL; they do not adopt chunking in v1.

## Objective

Make large uploads (files and folders, up to a configured limit well above today's 10 MB) work **the same way for every client and every storage backend**, with **memory use that does not grow with file size** on the client or the pod.

### Problem today

| Layer | Current behaviour | Evidence |
|---|---|---|
| Web Studio | Hard-coded 10 MB limit; folders zipped in tab RAM | `web-studio/src/routes/resources/-lib/upload.ts:2`, `zipFolder` |
| Rust CLI | Reads whole file into RAM (`tokio::fs::read`) | `crates/ov_cli/src/base_client.rs:1058` |
| Go SDK | Builds whole multipart body in `bytes.Buffer` | `sdk/go/upload.go` |
| TS SDK | `readFile` + `zipSync` in RAM | `sdk/typescript/src/node-files.ts:58-104` |
| Python SDK | Zips folder to temp file, streams it (good) | `sdk/python/openviking_sdk/client.py:680-710` |
| Server, `local` mode | Streams 1 MiB chunks to disk (good) | `openviking/server/temp_upload_store.py:190` |
| Server, `shared` mode | `read_bytes()` whole file on save and consume | `temp_upload_store.py:351, 531` |
| Durable source staging | Every local `add_resource` copies the whole source into VikingFS (`read_bytes()` + `write_file_bytes`), then the worker reads it back whole (`read_file_bytes`) | `openviking/resource/staged_source.py:75-156` |
| Ingest | `read_bytes()` per file, then write | `parse/parsers/directory.py:831,870`, `media/image.py`, `media/audio.py` |
| ragfs trait | Only `write(path, &[u8], …)` — whole buffer | `crates/ragfs/src/core/filesystem.rs:265` |
| s3fs | One `PutObject` per file, extra `to_vec()` copy, no multipart (5 GB cap) | `crates/ragfs/src/plugins/s3fs/{mod.rs:614, client.rs:626}` |
| Encryption wrapper | Single AES-GCM over whole file | `crates/ragfs/src/core/encryption_wrapper.rs:360` |
| Limits | 10 MB in UI, 512 MiB server, 10 MB per-file skip in code repos — three sources | various |

### Users

- **Web Studio user** uploading large files or folders from a browser.
- **CLI / SDK user** (Rust `ov`, Python, Go, TS) scripting bulk imports.
- **MCP agent** adding a local file via a signed upload URL.
- **Operator** sizing pod memory/disk and setting limits in `ov.conf`.

### Core rule

> **No code path holds a whole uploaded file in memory.** Every hop streams with a bounded buffer (≤ one part, default 8 MiB). The only difference between backends is the final storage hop.

### Design (one pipeline)

```
client ──chunked parts──▶ server staging (pod disk) ──path──▶ ingest ──write_from_path──▶ ragfs plugin
                                                                                          ├─ localfs: streaming copy
                                                                                          ├─ s3fs: multipart upload
                                                                                          └─ others: default (buffered) impl
```

#### A. Storage layer: ragfs streaming I/O

- New `FileSystem` trait methods, each with a **default** implementation so all plugins and wrappers compile unchanged:
  - `write_from_path(path, src: &Path, flags) -> Result<u64>`. Default: read the file and call `write` (buffered, correct).
  - `read_to_path(path, dst: &Path) -> Result<u64>`. Default: `read` then write the file.
- Overrides:
  - **s3fs `write_from_path`:** objects ≤ `multipart_threshold` (default 16 MiB) use a single `PutObject` streamed from file (`ByteStream::from_path`). Larger objects use `CreateMultipartUpload` → `UploadPart` (part size default 8 MiB, read from file) → `CompleteMultipartUpload`. On error, call `AbortMultipartUpload`. Removes the 5 GB cap.
  - **s3fs `read_to_path`:** chunked `get_object_range` loop (the reader at `s3fs/mod.rs:76-140` already exists) into the file.
  - **localfs:** streaming copy (`tokio::io::copy`).
  - **Wrappers** must override and forward explicitly. The default (buffered `self.write`) is correct but never reaches a plugin's streaming override. The runtime stack is `Stats(PathLock(Mountable → [Cached] Stats(Encryption(backend))))`:
    - `StatsWrappedFS` (`core/stats_wrapper.rs`), `PathLockWrappedFS` (`lock/wrapper.rs`, same lock as `write`), `ArcFileSystem` / `MountableFS` (`core/mountable.rs`), and `CachedFileSystem` (`cache/wrapper.rs`, invalidates like `write`).
    - **Exception: `MultiWriteWrappedFS` keeps the buffered default.** In `SyncMode::Async` the backup fan-out runs in a spawned task after the call returns and holds the bytes (`BackupWriteOp::WriteFile`), so the caller's temp file cannot stand in for them. Multi-write mounts are not used in the current deployment; streaming them needs a durable spool and is a separate change.
  - **Encryption wrapper:** v1 keeps the buffered fallback (whole-file AES-GCM) and enforces `encryption.max_file_bytes` (default 512 MiB) with a clear error. A chunked AEAD format is a separate spec.
- `ragfs-python` exposes `write_file_from_path(uri, local_path)` and `read_file_to_path(uri, local_path)`, releasing the GIL.
- `VikingFS` (`openviking/storage/viking_fs/_ops.py`) gains `write_file_from_path` / `read_file_to_path` with the **same** ACL, path-lock and side-effect semantics as `write_file_bytes`.

#### B. Ingest uses paths, not bytes

- Durable source staging (`resource/staged_source.py`): `stage_source` / `_copy_local_tree` call `write_file_from_path` per file. The worker's `materialize_source` calls `read_file_to_path` per entry. Concurrency (`_COPY_CONCURRENCY`) and symlink skipping stay the same.
- `DirectoryParser._upload_file_directly` and media-original writes (`image.py`, `audio.py`) call `write_file_from_path`.
- Encoding normalisation (`detect_and_convert_encoding`) applies only to text files under `parsers.max_text_normalize_bytes` (default 16 MiB). Larger or binary files are copied raw.
- The md5 manifest is computed incrementally (`hashlib` over chunks).

#### C. Server staging: one path for `local` and `shared`

- Every upload is staged on pod disk under `{workspace}/temp/upload/` and handled as a **path** from then on.
- `shared` mode = local staging + `write_file_from_path` to `viking://upload/…`. Consume = `read_file_to_path` to local staging. Remove both `read_bytes()` calls.
- The legacy `POST /api/v1/resources/temp_upload` becomes a thin wrapper: a single-part session that runs through the same code.
- `temp_file_id` may resolve to a staged **directory** (a folder session). `_resolve_local` (which currently requires `is_file()`) and the local TTL sweep (which currently skips directories) must both handle directories. Downstream (`stage_source`, `media_processor`, the parser registry) already accepts directories.

#### D. Chunked upload sessions (new API)

All endpoints use the existing auth (`get_upload_request_context`: API key, or signed token for MCP). Sessions are bound to `account_id` + `user_id`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/uploads/limits` | `{max_file_bytes, max_session_bytes, max_files, part_size_bytes}` |
| `POST` | `/api/v1/uploads` | Body `{files:[{path, size}], upload_mode?}` → `{upload_id, part_size_bytes, expires_at}` |
| `PUT` | `/api/v1/uploads/{id}/files/{index}/parts/{n}` | Raw body (`application/octet-stream`), `Content-Length` required, ≤ `part_size_bytes`, idempotent overwrite, optional `X-OV-Part-SHA256` |
| `GET` | `/api/v1/uploads/{id}` | Received parts per file (used to resume) |
| `POST` | `/api/v1/uploads/{id}/complete` | Validates sizes, assembles files on disk → `{temp_file_id}` |
| `DELETE` | `/api/v1/uploads/{id}` | Abort, delete staged data |

- A folder is **one session with N files**, each with its relative `path`. No zip. The server rebuilds the tree on disk, and `ingest_temp_upload` sends a staged directory straight to `DirectoryParser`. Zip uploads still go to `ZipParser` as today.
- Path validation reuses the `utils/zip_safe.py` rules: reject absolute paths, `..`, drive letters, NUL, and paths that collide after normalisation.
- Limits are enforced while streaming: a part over its size, a file over its declared size, or a session over its total size → 413, and staged data for that file is dropped.
- Expired sessions are swept by the existing temp-upload TTL cleanup (`temp_upload.ttl_seconds`).

#### E. Clients

| Client | v1 change |
|---|---|
| Web Studio | Read limits from `/uploads/limits`; drop the hard-coded 10 MB; `Blob.slice` parts, 3 parallel PUTs, per-part progress, retry/resume via `GET /uploads/{id}`; folders as multi-file sessions (remove `zipFolder`) |
| Rust CLI | Session upload with one reusable part buffer; folders without zip |
| Python SDK | Session upload; folders without zip (drop `_zip_directory` from the upload path) |
| Go SDK | Session upload with `io.SectionReader` — **phase 5** |
| TS SDK | Node `FileHandle.read` / browser `Blob.slice` — **phase 5** |
| MCP | Unchanged (single signed `curl`); server routes it through the same staging and storage code |

#### F. One limit config

```json
"server": {
  "upload": {
    "max_file_bytes": 2147483648,
    "max_session_bytes": 5368709120,
    "max_files": 10000,
    "part_size_bytes": 8388608
  }
}
```

- `temp_upload.shared_max_size_bytes` stays as a deprecated alias for `max_file_bytes` (a warning is logged at startup when it is set).
- `storage.agfs.s3.multipart_threshold_bytes` (16 MiB) and `multipart_part_size_bytes` (8 MiB) are separate settings: storage tuning, not policy.
- The 10 MB per-file skip in code repos (`upload_utils.py:90`) is a parsing policy and stays as it is (see Open Questions).

## Tech Stack

- Python 3.10+ / FastAPI / Starlette (server, ingest, Python SDK); `uv`, `pytest` (asyncio auto), `ruff` (line length 100)
- Rust workspace: `crates/ragfs`, `crates/ragfs-python` (pyo3 + maturin), `crates/ov_cli` (reqwest); `aws-sdk-s3` (already a dependency)
- Web Studio: React + Vite + TanStack Router, `vitest`, npm (`package-lock.json`)
- Go SDK (`sdk/go`), TS SDK (`sdk/typescript`, tsup + vitest)
- Local S3: SeaweedFS (`docker compose --profile s3`), which supports multipart

## Commands

```bash
# Python (pyproject addopts need pytest-cov, so they are cleared)
uv run pytest -o addopts="" tests/server/test_temp_upload_store_async_io.py tests/server/test_resources_temp_upload_token.py
uv run pytest -o addopts="" tests/server/test_upload_sessions.py tests/storage tests/parse
uv run ruff check openviking openviking_cli sdk/python && uv run ruff format --check openviking openviking_cli sdk/python

# Rust
cargo test -p ragfs
cargo test -p ov_cli
cargo clippy -p ragfs -p ragfs-python -p ov_cli --all-targets -- -D warnings
make build            # rebuilds ragfs-python into openviking/lib (maturin)

# S3 integration (SeaweedFS)
docker compose --profile s3 up -d seaweedfs s3-init
OV_S3_TEST_ENDPOINT=http://127.0.0.1:8333 cargo test -p ragfs --test s3_multipart_integration -- --ignored

# Web Studio: vitest hangs on /mnt/c, so run from a native-fs copy
(cd web-studio && npm ci && npm run lint && npm run format)
git ls-files web-studio | tar -cf - -T - | tar -xf - -C "$SCRATCH" && (cd "$SCRATCH/web-studio" && npm ci && npm test)

# SDKs
(cd sdk/go && go test ./...)
(cd sdk/typescript && npm ci && npm run typecheck && npm test)
```

## Project Structure

```
crates/ragfs/src/core/filesystem.rs          → trait: write_from_path / read_to_path (+ defaults)
crates/ragfs/src/core/*_wrapper.rs, mountable.rs → forward new methods; encryption cap
crates/ragfs/src/plugins/s3fs/{client,mod}.rs → multipart write, ranged read-to-path
crates/ragfs/src/plugins/localfs/            → streaming copy
crates/ragfs/tests/s3_multipart_integration.rs → new, #[ignore] + env-gated
crates/ragfs-python/src/lib.rs               → write_file_from_path / read_file_to_path
crates/ov_cli/src/{base_client,client}.rs    → session upload, folder without zip
openviking/storage/viking_fs/_ops.py         → VikingFS path-based read/write
openviking/pyagfs/async_client.py            → AsyncAGFSClient path-based read/write
openviking/resource/staged_source.py         → durable staging/materialize via paths
openviking/parse/parsers/directory.py, media/{image,audio}.py → path-based writes
openviking/server/upload_sessions.py         → new: session store (staging, parts, assemble, TTL)
openviking/server/routers/uploads.py         → new: /api/v1/uploads endpoints
openviking/server/temp_upload_store.py       → shared mode via paths; legacy wrapper
openviking/server/resource_ingest.py         → accept staged directory
openviking/server/config.py                  → UploadConfig + deprecated alias
sdk/python/openviking_sdk/client.py          → session upload
web-studio/src/routes/resources/-lib/        → chunked uploader, limits fetch; remove zipFolder
web-studio/src/gen/ov-client/                → regenerate from OpenAPI
tests/server/test_upload_sessions.py         → new
docs/en/guides/01-configuration.md, docs/en/api/02-resources.md → document config + API
```

## Code Style

Match the existing code. Python: async, with blocking I/O pushed to threads and a bounded loop, as in `temp_upload_store.py`:

```python
async def _stream_part_to_disk(request: Request, dest: Path, max_bytes: int) -> int:
    total = 0
    f = await asyncio.to_thread(_open_binary_for_write, dest)
    try:
        async for chunk in request.stream():
            total += len(chunk)
            if total > max_bytes:
                raise InvalidArgumentError(f"Part exceeds size limit ({max_bytes} bytes).")
            await asyncio.to_thread(f.write, chunk)
    finally:
        await asyncio.to_thread(_close_file, f)
    return total
```

Rust: trait methods get a default body so existing plugins keep compiling; overrides sit next to `write` in each plugin:

```rust
/// Stream a local file into `path` without buffering it whole.
/// Default falls back to a buffered `write`; plugins override for true streaming.
async fn write_from_path(&self, path: &str, src: &Path, flags: WriteFlag) -> Result<u64> {
    let data = tokio::fs::read(src).await?;
    self.write(path, &data, 0, flags).await
}
```

- Names: `snake_case` (Python/Rust), `camelCase` (TS), `*_bytes` suffix for sizes in config.
- Errors: `InvalidArgumentError` → 400/413 as `temp_upload` maps today; never echo file contents in errors or logs.
- Files under 800 lines: the session logic goes in a new module, not in the 600+ line `temp_upload_store.py`.

## Testing Strategy

TDD per task: write the failing test first.

| Level | What | Where |
|---|---|---|
| Rust unit | Default `write_from_path` / `read_to_path` on memfs/localfs; wrapper forwarding; encryption cap error | `crates/ragfs/src/**` `#[cfg(test)]` |
| Rust integration | s3fs multipart against SeaweedFS: 0 B, 1 B, threshold−1, threshold+1, 50 MiB, abort-on-error leaves no MPU; env-gated `#[ignore]` | `crates/ragfs/tests/s3_multipart_integration.rs` |
| Python unit | Session lifecycle, part idempotency, resume listing, size/count limits → 413, path traversal rejection, cross-user access denied, TTL sweep, legacy `temp_upload` via session, shared mode without `read_bytes` | `tests/server/test_upload_sessions.py`, extend `test_temp_upload_store_async_io.py` |
| Python unit | Ingest uses `write_file_from_path` (mock VikingFS asserts no `write_file_bytes` for direct-upload files); incremental md5 | `tests/parse/` |
| Memory regression | Ingest a 512 MiB direct-upload file and sample pod RSS (`/proc/self/status` `VmHWM`), plus `tracemalloc` peak for the Python side | `tests/integration/test_upload_memory.py` (marked `slow`) |
| Web Studio | Chunker slices correctly; resume skips received parts; limits drive validation; folder → multi-file session | `web-studio/src/routes/resources/-lib/*.test.ts` |
| CLI / SDKs | Mock server: parts sent in order, buffer reused, folder without zip, falls back to legacy endpoint on 404 | `crates/ov_cli` tests, `sdk/python/tests`, `sdk/go`, `sdk/typescript` |
| Manual E2E | Chrome: upload a 1 GiB folder from Web Studio; check tab memory in Task Manager and pod `docker stats` | checklist in PR |

Coverage: ≥ 80% on new modules (`upload_sessions.py`, `routers/uploads.py`, s3fs multipart path).

## Boundaries

**Always**
- Stream with a bounded buffer (≤ part size) on every new path; add a test that proves it.
- Validate every client-supplied path, size and count at the server boundary.
- Keep `POST /resources/temp_upload` and zip uploads working; run their existing tests on every task.
- Abort S3 multipart uploads on failure; delete staged data on abort or expiry.
- Regenerate `web-studio/src/gen/ov-client` from OpenAPI rather than hand-editing it.

**Ask first**
- Any new dependency (none expected).
- Changing the encrypted file format, or raising the encryption cap.
- Changing parse behaviour for large files (skip or raw-store thresholds).
- Renaming or removing existing config keys (beyond the deprecated alias).
- Removing legacy endpoints or zip-folder support.
- CI workflow changes (e.g. adding a SeaweedFS service).

**Never**
- Call `read_bytes()` / `tokio::fs::read` / `readFile` on uploaded content in a new code path.
- Break reads of existing objects (plain or encrypted).
- Log or echo uploaded file contents.
- Push to `main`, force-push, or tag `v*.*.*`.

## Success Criteria

1. **Pod memory flat (local mode):** uploading and ingesting a 1 GiB direct-upload file from each of Web Studio, `ov` and the Python SDK, with S3 AGFS, raises pod peak RSS by **≤ 128 MiB** over idle.
2. **Pod memory flat (shared mode):** same bound as #1; no `read_bytes` left in `temp_upload_store.py`.
3. **Over 5 GB on S3:** with `max_file_bytes` raised, a 6 GiB file is stored through multipart, and its md5 matches when read back.
4. **Browser:** a 1 GiB folder uploads from Web Studio with no zip step; tab memory grows **≤ 150 MiB**.
5. **Resume:** after the network drops mid-upload, the client resends only the missing parts (checked via server part log).
6. **One limit:** changing `server.upload.max_file_bytes` alone changes the limit in Web Studio, CLI, SDK and server. An oversize request gets 413 before staging completes.
7. **Backward compatible:** the existing `tests/server/test_api_resources.py`, `test_resources_temp_upload_token.py` and `test_temp_upload_store_async_io.py` pass unchanged; an old CLI binary can still upload.
8. **Security:** traversal paths, cross-user session access, oversize parts and expired sessions are rejected, each with a test.

## Phases (detailed in Phase 2 Plan)

1. ragfs `write_from_path` / `read_to_path` + s3fs multipart + ragfs-python + VikingFS → **fixes pod memory for every client**
2. Ingest switched to paths; shared mode switched to paths
3. `server.upload` config + `/uploads/limits`; Web Studio reads limits (removes 10 MB with the legacy single request still in use)
4. Session API + Web Studio, Rust CLI, Python SDK
5. Go SDK, TS SDK; docs

## Decisions (resolved open questions, 2026-10-06)

1. **Limits:** `max_file_bytes` 2 GiB, `max_session_bytes` 5 GiB, `max_files` 10,000.
2. **Huge files that get parsed:** out of scope; separate spec.
3. **Encryption:** v1 keeps the buffered fallback with a 512 MiB `encryption.max_file_bytes` cap; chunked AEAD is a separate spec.
4. **Resume:** within one page/process only; no resume across browser reloads.
5. **Go/TS SDKs:** phase 5.
6. **Code-repo 10 MB per-file skip:** unchanged.
7. **Branch:** `docs/streaming-upload-spec` from `main`.
