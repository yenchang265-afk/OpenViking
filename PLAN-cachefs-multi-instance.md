# Plan: Multi-Instance CacheFS

Status: **Implemented** 2026-10-29 on branch `worktree-cachefs-multi-instance-plan` (T1–T15). T16 (deployment check) is left for a manual run.

## Implementation notes

- **Open questions, as decided:** (1) explicit `multi_instance` flag, default off; (2) degrade on a failed bump (retry, metric, TTL bound), no strict mode; (3) no Redis Cluster hash tag. T13 had no Cluster numbers, so this stays open.
- **Test location:** the race, bump-table and stress tests live in-crate (`src/cache/multi_instance_tests.rs`, `src/cache/stress_tests.rs`) instead of `tests/`, because the harness needs `pub(crate)` items (`ArcFileSystem`, key helpers). The real-Redis variants (T11) are a `redis` submodule there, gated on `REDIS_URL` / `REDIS_CLUSTER_URLS`. `tests/common/gated_fs.rs` was not needed.
- **R3** (concurrent write-through) needs the T8 flag, so its RED test landed with T8. It reproduced `v1` served while the backend held `v2`.
- **R4 harness:** the provider's GET delay sleeps before reading, so it never overlaps two bumps. The test uses a SET delay instead.
- **Bump:** `INCRBY` first. A result of 1 means the key was missing, and only then is it re-based with a random `SET`. That keeps the common case to one round trip.
- **Stress oracle:** mutations are recorded when they start, not when they return, because readers see a write's effect before the call returns. An uncached control run validates the oracle. With 3×2 tasks × 300 ops and 0–3 ms jitter, the test caught an injected missing write bump. It passed on 8 seeds.
- **Benchmark (T13):** standalone Redis through the WSL→Docker port forward, p50 over 3 runs each. Depth 3 hit: main 573–581 µs, branch 574–655 µs. Depth 8 hit: main 598–610 µs, branch 651–680 µs (about +10%, at the budget; run-to-run spread about ±8%). Miss and fill were in line with main.
- **Not verified locally:** Redis Cluster mode (no multi-node cluster available) and T16.
Scope: `crates/ragfs/src/cache/*`, the CacheFS config path (Rust builder, `ragfs-python` binding, `openviking_cli` config), metrics, and the RAGFS cache guide.

## Problem

Several OpenViking instances can already share one Redis-backed CacheFS namespace (`{service_name}:ov:cache:v1:*`). All instances then see the same hits and the same invalidations. But `CachedFileSystem` is only correct when **one process** uses that namespace, as `docs/en/guides/14-ragfs-cache.md` already states. Cache-fill reads also write to the cache, so "one writer, many readers" is not safe either.

The races found in `crates/ragfs/src/cache/wrapper.rs` (line numbers as of `main`):

| # | Race | Where | Effect |
|---|---|---|---|
| R1 | **Stale fill.** Instance B misses and reads the old backend data. Instance A writes the backend and DELs the key. B SETs the old envelope. | `read` :1126, `read_with_generation_cache` :811, `read_dir_*` :879/:947, `fill_*` :1014/:1033 | Stale until the TTL expires (default 3600 s). `operation_lock` only excludes inside one process. |
| R2 | **Generation snapshot is taken after the backend read.** `fill_*` calls `generation_snapshots` after `backend.read`, so a `remove`/`remove_all`/`rename` that lands in between is recorded as already seen. | `fill_file` :1014 | A stale envelope passes generation validation. |
| R3 | **Write-through fill between concurrent writers.** A writes v1 to the backend, B writes v2, B SETs v2, then A SETs v1. | `write` :1179 | The cache holds v1 while the backend holds v2. |
| R4 | **Generation bump is not atomic.** It does GET then SET, not INCR. | `bump_generation` :637 | Concurrent bumps can overwrite each other, which widens R1/R2. |
| R5 | **Lost generation keys are re-initialized per process.** Two instances SET different random values. The last write wins. | `current_generations` :506 | Never serves stale data, but entries churn constantly. |
| R6 | **Failure bypass is per process.** If A's DEL fails, only A bypasses. | `bypass_scopes` :42, `mark_bypass` :479 | B keeps serving the stale key. |

These parts are already safe across instances and are out of scope: QueueFS cache backend and cache-backed PathLock (they have their own consistency rules), and per-process request coalescing (it only affects efficiency).

## Design: snapshot-before-read versions

Extend the existing subtree-generation idea to every cached object, and fix *when* the snapshot is taken.

1. **Per-path object version.** New key `…:ver:{hash(path)}`. It covers both the file envelope and the directory envelope of `path`.
2. **Envelope v2 records a snapshot** of `ver(path)` plus `subtree(scope)` for every ancestor scope. **The snapshot is taken before the backend read.**
3. **A hit is valid only if every recorded value equals the current value.** One MGET, as today, plus one more key.
4. **Every mutation bumps versions with atomic `INCRBY` after the backend mutation.** The bump is the commit point. DEL of the data keys stays, but only as best-effort cleanup.

**Why this is correct.** Assume the backend is read-after-write consistent across instances, and the provider is linearizable per key (Redis primary reads, already enforced). Take any backend change C, followed by its bump B_C. If a fill's snapshot S comes before B_C, the envelope is rejected after B_C. If S comes after B_C, then C finished before S, which is before the fill's backend read, so the read already includes C. A stale fill that arrives late can at worst overwrite a fresher envelope. That causes a miss, never a stale hit. This closes R1, R2 and R4 **without Lua**. It only needs GET/SET/DEL/MGET/INCRBY, so it works with RedisProvider (standalone, Cluster, Sentinel) and with any DynamicProvider that exports `incrby`.

### Bump table

| Operation | Bumps (after backend success, or always for `remove_all`) |
|---|---|
| `create`, `write`, `write_from_path`, `truncate`, `chmod`, `invalidate_external_write` | `ver(path)`, `ver(parent)` |
| `mkdir`, `remove`, `remove_all` | `subtree(path)`, `ver(path)`, `ver(parent)` |
| `rename`, `replace` (a→b) | `subtree(a)`, `subtree(b)`, `ver(a)`, `ver(b)`, `ver(parent a)`, `ver(parent b)` |
| `ensure_parent_dirs` | `ver(scope)` for each ancestor scope (replaces today's dir-key DELs) |

### Key layout and encoding (v2)

- `{service_name}:ov:cache:v2:{file|dir|subtree|ver}:{hash:016x}`. The namespace moves from `v1` to `v2` because the value format changes. `CACHE_ENVELOPE_VERSION` becomes 2.
- Version and generation values are **decimal ASCII i64**, so `INCRBY` works on them. Today's 8-byte big-endian u64 values are not INCR-compatible.
- **Missing key on read:** `SET NX` a random positive i63, then use the stored value. On `ConditionNotMet`, GET it. Every instance then agrees on one value, which fixes R5.
- **Missing key on bump:** `SET NX` random, then `INCRBY 1`. If the key expires between the two calls, INCRBY recreates it at 1. That can only collide with an envelope that recorded exactly 1, which requires the same race. The risk is negligible and documented.
- Version keys follow the provider's default TTL, like other keys. If a version key expires before its data keys, the next read re-initializes it randomly and old envelopes miss.

### Multi-instance mode

New flag `storage.agfs.cachefs.multi_instance` (default `false`).

| | `false` (today's deployments) | `true` |
|---|---|---|
| Version protocol | on | on |
| Write-through fill after a full `write` | on (safe: `operation_lock` serializes writers) | **off**, because of R3. The next read fills. |
| Bump without provider `IncrBy` | falls back to GET+SET under `operation_lock` | **startup error** (`require_operations` adds `IncrBy`) |
| `default_ttl_seconds = 0` (Redis) | allowed | **rejected**: TTL is the backstop for failed bumps |

### Failure handling

- **Bump fails after the backend mutation:** retry 3× with 10/50/200 ms backoff. If it still fails: `mark_bypass(scope)` locally, increment `invalidation_failures`, and log an error with the path. The operation still returns success, because the backend change has already happened. Other instances can serve stale data until the data key's TTL. This is the documented residual risk (R6). Alert on the metric.
- **Probe, snapshot or fill fails:** same as today (local bypass and backend fallback).
- **Redis failover** with async replication can lose an acknowledged `INCRBY`, leaving stale data up to the TTL. Document this. Recommend `min-replicas-to-write` for Sentinel/Cluster.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Extra latency on hit (one more key in the MGET) and on miss (a snapshot MGET before the backend read) | Reuse the probe's MGET values as the snapshot when the envelope existed. Benchmark in T13 and accept ≤ 10 % p50 hit regression on standalone Redis. |
| Redis Cluster: snapshot keys sit in different slots, so `mget` falls back to one GET per key (`redis/client.rs:172`). This costs N round trips per miss. | Measure in T13. Option: put `ver`/`subtree` keys under a `{service_name}` hash tag (like PathLock) for one-slot MGET, at the cost of a hot slot. Decide from data. |
| Mixed v1/v2 fleet during a rolling upgrade: v1 writers don't bump v2 versions | Upgrade procedure: set `cachefs.backend=local` everywhere, roll the new version, then re-enable. Or stop all v1 instances first. Documented like the PathLock key migration. |
| Backend not read-after-write consistent across instances (e.g. per-pod local disk) | Document it as a prerequisite. `local` AGFS on per-pod disk is meaningless for multi-instance anyway. S3/SeaweedFS and MariaDB tiers qualify. |
| `wrapper.rs` is already 1 555 lines (rule: ≤ 800) | New logic goes in `cache/versions.rs`. New tests go in `crates/ragfs/tests/cache_multi_instance.rs`. No drive-by restructuring of `wrapper.rs`. |
| Dynamic providers without `incrby` break | Only rejected in `multi_instance` mode. Single-instance keeps the GET+SET fallback. |
| `remove_all` partial failure | Already bumps unconditionally. Keep that behavior and cover it with a test. |

## Verification checkpoints

- **A (after T3):** race tests R1–R5 exist and **fail** on `main` (RED).
- **B (after T7):** R1–R5 pass. All existing `cache` tests pass: `cargo test -p ragfs --features cache,test-utils`.
- **C (after T10):** Python config and binding tests pass. `make build`. `pytest tests/misc/test_config_validation.py tests/observability/test_console_router.py`.
- **D (after T13):** two-runtime Redis tests (standalone, plus Cluster if available) and the stress test pass. Benchmark is within budget.
- **E (after T15):** two app containers on `openviking-net` share redis/seaweedfs/mariadb, and the manual checklist passes.

## Parallel work

- T4 ∥ T1–T3 (the version store doesn't depend on the harness)
- T8 ∥ T9 (after T7)
- T11 ∥ T12 (after T10)
- T14 ∥ T13

## Tasks

Each task is TDD: write the failing test first. Each touches ≤ 5 files.

### P0 — Test harness and failing race tests

- [x] **T1: Two-instance harness**
  - Acceptance: a helper builds N `CachedFileSystem`s that share one `CacheRuntime::memory()` and one backend. `SharedFs` forwards to an `Arc<MemFileSystem>`, because `with_runtime` takes a `Box<dyn FileSystem>`. A `GatedFs` wrapper can pause chosen ops (`read`, `read_dir`, `write`) after the inner call returns, using `tokio::sync::Notify`/`Barrier`, to force interleavings deterministically.
  - Verify: a smoke test where both instances read and write the same file without gating and stay consistent.
  - Files: `crates/ragfs/tests/cache_multi_instance.rs` (new), `crates/ragfs/tests/common/gated_fs.rs` (new)

- [x] **T2: RED tests R1/R2**
  - Acceptance: (a) B's read of `/f` is gated after the backend read, A writes `/f`, B is released, then a read from either instance must return the new data. (b) The same with A `remove`ing `/f`: the next read must be NotFound. (c) The same with A `remove_all`ing the ancestor `/d`. (d) Directory variant: B's `read_dir(/d)` is gated, A creates `/d/x`, then the listing must contain `x`.
  - Verify: all four **fail** on `main`.
  - Files: `crates/ragfs/tests/cache_multi_instance.rs`

- [x] **T3: RED tests R3/R4/R5**
  - Acceptance: (a) R3: A and B write `/f` with interleaved gating while write-through fill is enabled in multi-instance mode, and the final read must equal the backend. This is marked as expecting the multi-instance flag from T8. (b) R4: a gated provider wrapper around `MemoryMockProvider` interleaves two bumps, and both must take effect (final value = initial + 2). (c) R5: an envelope is filled on A after the generation key was lost, and B must get a hit (both agree on the re-initialized value).
  - Verify: all **fail** on `main`.
  - Files: `crates/ragfs/tests/cache_multi_instance.rs`, `crates/ragfs/src/cache_runtime/memory.rs` (gate hook, test-utils only)

### P1 — Version store

- [x] **T4: `cache/versions.rs`**
  - Acceptance: `VersionStore` owns the key layout v2 (`object_key(kind, path)`, with `file`/`dir`/`subtree`/`ver`), decimal i64 encoding, `snapshot(paths, memo) -> Vec<VersionSnapshot>` (MGET plus `SET NX` init plus re-GET on lost NX), `matches(snapshot, memo)`, and `bump(keys)` (`SET NX` random then `INCRBY`, or a GET+SET fallback when the provider lacks `IncrBy`). It reports per-key errors so the caller can bypass the affected scope.
  - Verify: unit tests for encoding round trip, NX agreement between two callers, bump atomicity using T3's gated provider, the fallback path, and invalid-length/invalid-decimal values → `InvalidData`.
  - Files: `crates/ragfs/src/cache/versions.rs` (new), `crates/ragfs/src/cache/mod.rs`

- [x] **T5: Envelope v2**
  - Acceptance: `CACHE_ENVELOPE_VERSION = 2`. `GenerationSnapshot` is renamed to `VersionSnapshot { key, value: i64 }` and covers both `ver` and `subtree`. v1 envelopes are rejected (decode error, then the key is deleted).
  - Verify: unit tests for decoding v1 (rejected) and v2 (round trip).
  - Files: `crates/ragfs/src/cache/envelope.rs`

### P2 — Wire the protocol into `CachedFileSystem`

- [x] **T6: Snapshot before backend read**
  - Acceptance: `read`, `read_with_generation_cache`, `read_dir_with_generation_cache` and `read_dir_for` take the snapshot before `backend.read*`, reusing probe values when the envelope existed. `fill_file`/`fill_directory` take the snapshot as a parameter and never re-read versions. Probes validate `ver(path)` as well as the ancestor `subtree`s. `current_generations*` and `put_missing_generations` are replaced by `VersionStore`.
  - Verify: T2 (a)–(d) and T3 (c) go GREEN. The existing `lost_generation_key_never_revalidates_deleted_subtree` still passes.
  - Files: `crates/ragfs/src/cache/wrapper.rs`

- [x] **T7: Bump table for mutations**
  - Acceptance: every mutation in the bump table calls `VersionStore::bump` after the backend call. Data-key DELs stay as cleanup. `bump_generation` uses atomic bump. `invalidate_external_write` bumps `ver(path)` and `ver(parent)`. Bump failure retries 3× with backoff, then local bypass, an `invalidation_failures` metric and an error log.
  - Verify: T3 (b) GREEN. A new test per row of the bump table: gate a fill, run the op on the other instance, assert no stale hit. A test that a provider failure on bump does not fail the write and increments the metric.
  - Files: `crates/ragfs/src/cache/wrapper.rs`, `crates/ragfs/src/cache/metrics.rs`

### P3 — Multi-instance mode and config

- [x] **T8: `multi_instance` in Rust config**
  - Acceptance: `CachePolicy::with_multi_instance(bool)`. When true, `write` skips write-through fill. `build_configured_stack` adds `CacheOperation::IncrBy` to `require_operations` when `multi_instance` is set, and fails startup with a clear message if the provider lacks it.
  - Verify: T3 (a) GREEN. A builder test: a dynamic provider stub without `incrby` plus `multi_instance` gives a config error, and without `multi_instance` it starts.
  - Files: `crates/ragfs/src/cache/policy.rs`, `crates/ragfs/src/cache/wrapper.rs`, `crates/ragfs/src/core/builder.rs`

- [x] **T9: Binding parse**
  - Acceptance: `ragfs-python` reads `storage.agfs.cachefs.multi_instance` (bool, default false, type-checked). With the Redis provider, it rejects `multi_instance=true` with `default_ttl_seconds=0`.
  - Verify: binding unit tests for default, true, wrong type, and TTL=0 rejection.
  - Files: `crates/ragfs-python/src/lib.rs`

- [x] **T10: Python config model**
  - Acceptance: `AGFSCacheFSConfig.multi_instance: bool = False`. The validator rejects `multi_instance=true` with `backend="local"`. `open_viking_config` cross-checks the Redis `default_ttl_seconds > 0` with a user-friendly error. `agfs_utils` passes the flag through.
  - Verify: `tests/misc/test_config_validation.py` cases. `make build`, then `pytest tests/misc tests/unit/service/test_core_encryption_startup.py`.
  - Files: `openviking_cli/utils/config/agfs_config.py`, `openviking_cli/utils/config/open_viking_config.py`, `openviking/utils/agfs_utils.py`, `tests/misc/test_config_validation.py`

### P4 — Integration, stress and performance

- [x] **T11: Two runtimes on real Redis** (env-gated like `redis_runtime.rs`)
  - Acceptance: two `CacheRuntime::redis` connections to the same server, each wrapping a `CachedFileSystem` over a shared backend. T2/T3 scenarios replayed. Cluster variant if `REDIS_CLUSTER_URL` is set. Version values are verified as decimal strings via a raw GET.
  - Files: `crates/ragfs/tests/cache_multi_instance_redis.rs` (new)

- [x] **T12: Randomized stress test**
  - Acceptance: 3 instances × 8 tasks, random ops (`write`/`read`/`remove`/`rename`/`mkdir`/`read_dir`) over a small path set, with random gate delays. Oracle (per-path write history): a read may return the value of write W only if no other write that *completed before the read started* was ordered after W. Hits that overlap an in-flight write may return the value from before that write, because the bump is the commit point. After quiescence, every cached read equals the backend. Fixed seed in CI, plus an env var for long runs.
  - Files: `crates/ragfs/tests/cache_multi_instance.rs`

- [x] **T13: Benchmark**
  - Acceptance: hit and miss latency, before and after, on standalone Redis (local docker sidecar) for 4 KiB files at depth 3 and 8. Hit p50 regression ≤ 10 %. Record numbers in the PR. Cluster numbers inform the hash-tag decision (open question 3).
  - Files: `crates/ragfs/benches/` or a `tests/benchmark` script (follow existing bench layout)

### P5 — Observability and docs

- [x] **T14: Metrics and console**
  - Acceptance: new counters `stale_version` (envelope rejected because a version moved) and `invalidation_failures`, exported as `openviking_ragfs_cache_*` and included in `GET /api/v1/console/cache`.
  - Verify: `tests/observability/test_console_router.py`.
  - Files: `crates/ragfs/src/cache/metrics.rs`, `crates/ragfs-python/src/lib.rs` (metrics snapshot), `openviking/metrics/ragfs_cache.py`, `openviking/server/routers/console.py`

- [x] **T15: Guide and configuration docs (en + zh)**
  - Acceptance: replace the single-writer assumption with the multi-instance contract. Cover the prerequisites (consistent backend, Redis primary reads, TTL > 0), the bump table, the residual risks (failed bumps, failover), the v1→v2 upgrade procedure, and the `multi_instance` option row.
  - Files: `docs/en/guides/14-ragfs-cache.md`, `docs/zh/guides/14-ragfs-cache.md`, `docs/en/guides/01-configuration.md`, `docs/zh/guides/01-configuration.md`

- [ ] **T16: Deployment check (manual)**
  - Checklist: two app containers via `docker run` on `openviking-net` with the same `ov.conf` (`multi_instance: true`) and `tiered.env`, sharing redis/seaweedfs/mariadb. Write on A, then read on B returns the new content. `rm -r` a directory on A, then `ls`/`tree` on B is consistent. Kill Redis mid-write: the write succeeds, the `invalidation_failures` metric goes up, and the B read recovers after the TTL. Studio cache dashboard shows the hit rate on both instances.

## Out of scope (follow-ups)

- **Write-through fill in multi-instance mode** under a distributed PathLock held for the write.
- **Strict mode:** bump before the backend mutation and fail the write if the provider is unreachable. This trades write availability for no-stale-on-partition.
- **Lua compare-and-set fill** to stop late fills overwriting fresher envelopes (perf only).
- **Cross-instance request coalescing.**

## Open questions

1. **Flag vs. always-on.** Recommend the explicit `multi_instance` flag (default off), so single-instance setups keep write-through fill and dynamic providers without `incrby` keep working.
2. **Failed bump policy.** Recommend degrade (retry, metric, TTL bound) over strict fail-write for now. Is a TTL-bounded stale window on bump failure acceptable for production?
3. **Redis Cluster hash tag** for `ver`/`subtree` keys: decide after T13.

## Delivery

- PR 1: P0 + P1 + P2 (protocol, RED→GREEN race tests). Behavior stays the same for single-instance, apart from the namespace bump to `v2` (the cache starts cold once).
- PR 2: P3 + P4 (flag, config, Redis/stress/bench).
- PR 3: P5 (metrics, docs, deployment check).
