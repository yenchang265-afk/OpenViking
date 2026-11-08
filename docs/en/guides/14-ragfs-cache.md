# RAGFS Cache

RAGFS cache is an optional read-cache layer for OpenViking query results and file contents. It speeds up full-file `read`, `stat`, `read_dir`, `tree_directory`, `glob_directory`, and `grep`. It is only an acceleration layer, not the source of truth; backend filesystem data remains authoritative.

CachedFileSystem assumptions:

- When more than one OpenViking / RAGFS process shares a cache namespace (the same `service_name` on the same cache Provider), every one of them sets `storage.agfs.cachefs.multi_instance: true`. See "Multiple Instances" below.
- File and directory changes go through RAGFS.
- The backend is not modified externally by bypassing RAGFS.
- Every instance sees the same backend, and a backend write is visible to every instance once it returns. S3 or SeaweedFS and the MariaDB small-file tier qualify; separate local disks per pod do not.
- After a cache Provider successfully writes or deletes one key, later reads of that key do not return the old value.

These assumptions apply to the read-cache layer. QueueFS and PathLock also use
CacheRuntime, but define their own consistency rules.

## Quick Start

For first-time setup, complete the base configuration first:

```bash
openviking-server init
openviking-server doctor
```

Configure the global top-level `cache` Provider, then select `backend=cache` under `storage.agfs.cachefs`:

```json
{
  "service_name": "openviking-server",
  "cache": {
    "provider": "redis",
    "params": {
      "mode": "standalone",
      "endpoints": ["redis://127.0.0.1:6379"],
      "pool_size": 32,
      "connect_timeout_ms": 1000,
      "command_timeout_ms": 1000,
      "default_ttl_seconds": 300
    }
  },
  "storage": {
    "workspace": "./data",
    "agfs": {
      "backend": "local",
      "cachefs": {
        "backend": "cache"
      },
      "pathlock": {
        "provider": "cache",
        "lock_expire_secs": 30.0
      }
    }
  }
}
```

Start Redis and OpenViking:

```bash
redis-server
```

In a second terminal, start OpenViking:

```bash
openviking-server --config ~/.openviking/ov.conf
```

If the configuration file is at the default path `~/.openviking/ov.conf`, you can also run:

```bash
openviking-server
```

Available Providers:

| Provider | Best for | Notes |
|----------|----------|-------|
| `redis` | Default delivery on standard networks | Built into RAGFS; supports standalone, Cluster, and Sentinel |
| `dynamic` | YuanRong, Mooncake, or closed-source cache systems | Loaded from an external shared library through the versioned C ABI |

`MemoryMockProvider` is only used by unit and smoke tests; it is not a production configuration option.

### Cache-backed PathLock

Set `storage.agfs.pathlock.provider` to `cache` to coordinate path locks
between OpenViking processes through the shared Redis CacheRuntime.
OpenViking derives the PathLock Redis namespace from top-level `service_name`.
Use distinct service names for independent deployments. Distributed path
locking does not replace `storage.agfs.cachefs.multi_instance` when several
instances share CacheFS.
Cache-backed PathLock only supports the built-in Redis Provider.

Redis HASH keys are partitioned by logical path scope:

```text
{service_name}:ov:pathlock:global:tokens
{service_name}:ov:pathlock:scope:_system:tokens
{service_name}:ov:pathlock:scope:account:{account}:tokens
```

`{service_name}` is used as the Redis Cluster
hash tag, so all PathLock keys for one deployment remain in one slot. Tree
conflict checks scan only the HASH for
the request scope. `/` and `/local` use the global HASH but do not scan
account or `_system` HASHes. A batch containing paths from different scopes
is rejected.

Do not run versions that use the legacy single HASH key together with versions
that use scoped keys. Stop old writers, wait at least
`2 * lock_expire_secs` for legacy keys to expire, and then start the new
version.

## Breaking Configuration Change

Legacy cache configuration is no longer accepted. Migrate before upgrading:

| Removed configuration | Canonical replacement |
|-----------------------|-----------------------|
| `storage.agfs.cache` | top-level `cache.provider` + `cache.params`, plus `storage.agfs.cachefs.backend="cache"` |
| `storage.agfs.queuefs.backend="redis"` and `queuefs.redis` | `storage.agfs.queuefs.backend="cache"`, plus the shared top-level `cache` section |
| Redis `mode="singleton"` | `mode="standalone"` |
| `tls_enabled=true` | use `rediss://` endpoints |
| `read_from_replica` | removed; all reads use the primary |

## DynamicProvider

OpenViking ships the DynamicProvider loader and a versioned C ABI. The default wheel does not bundle third-party SDKs or Provider libraries. Deploy the Provider shared library separately and configure `provider=dynamic` when an external cache system is required.

A dynamic library must export this versioned entry point:

```text
openviking_cache_provider_v1
```

The C contract is defined by `crates/ragfs/include/openviking_cache_provider_v1.h`. The Provider must use the Host allocator for returned data, obey the documented ownership and close semantics, catch exceptions before they cross the C ABI, and make its handle safe for concurrent calls.

Provider artifacts should declare the ABI version, target OS and CPU, minimum runtime version, external SDK version, dynamic dependencies, and SHA256. When a Provider depends on native libraries, its publisher must make them discoverable through RPATH, `LD_LIBRARY_PATH`, or deployment instructions.

External Providers can be upgraded independently without rebuilding the default OpenViking wheel. OpenViking only needs a coordinated upgrade when the DynamicProvider ABI becomes incompatible.

## Configuration

Top-level `service_name` defaults to `"openviking-server"` and supplies the Redis
namespace for CacheFS, QueueFS cache backend, cache-backed PathLock, and
cache-backed multi-write metadata.

The top-level `cache` section is a sibling of `storage`:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `provider` | str | none | Provider name; supports `redis` and `dynamic` |
| `params` | object | `{}` | Provider-owned parameters |

`storage.agfs.cachefs` controls CacheFS behavior:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `backend` | str | `"local"` | `local` preserves existing behavior; `cache` enables CachedFileSystem |
| `max_file_size_bytes` | int | `1048576` | Largest file whose full contents CacheFS caches. Ranged reads and larger files go to the backend; `0` disables file-content caching |
| `multi_instance` | bool | `false` | Several instances share this cache namespace: delete affected buckets before each write returns. Requires `backend: "cache"` and a cache default TTL greater than `0`. See "Multiple Instances" |

`storage.agfs.pathlock` controls PathLock storage:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `provider` | str | `"filesystem"` | `filesystem`, `memory`, `sqlite`, or `cache`; see [SQLite setup](../configuration/01-server.md#storage) |
| `lock_expire_secs` | float | `30.0` | Lock stale timeout; must be at least `1.0` |

Redis configuration:

| Option | Default | Description |
|--------|---------|-------------|
| `mode` | `"standalone"` | Redis deployment mode |
| `endpoints` | `["redis://127.0.0.1:6379"]` | Redis connection URLs; use `redis://` for plaintext or `rediss://` for TLS |
| `username` | `""` | Redis ACL username |
| `password_env` | `""` | Environment variable that stores the Redis password |
| `pool_size` | `32` | Command concurrency |
| `connect_timeout_ms` | `10000` | Connection timeout in milliseconds |
| `command_timeout_ms` | `0` | Command timeout in milliseconds; `0` disables command timeouts |
| `default_ttl_seconds` | `300` | Runtime default TTL used by CacheFS query buckets; `0` means no TTL |
| `tls_insecure_skip_verify` | `false` | Skip certificate verification for `rediss://`; intended only for controlled test environments |

All Redis reads are sent to the primary node so QueueFS does not observe stale queue state. CacheRuntime relies on Redis transport security when required and does not add a separate application-layer value encryption format.

With `command_timeout_ms=0`, CacheRuntime does not time out slow Redis commands. It also does not automatically fall back after a fixed interval.

DynamicProvider configuration:

OpenViking uses `cache.params.library` to load the dynamic library. All remaining fields are Provider-owned and passed to `create` as JSON. Use the schema documented by the Provider publisher.

```json
{
  "cache": {
    "provider": "dynamic",
    "params": {
      "library": "/opt/openviking/providers/libopenviking_cache_provider.so",
      "endpoint": "127.0.0.1:31501",
      "request_timeout_ms": 5000
    }
  }
}
```

## Architecture

RAGFS separates Provider access from its consumers:

- `CachedFileSystem`: implements filesystem semantics, including cache hit/miss handling, backend fallback, cache fill, invalidation, request checks, and metrics.
- `CacheRuntime`: exposes common primitive operations and binds either the built-in RedisProvider or an external DynamicProvider during startup.
- `QueueFS` and `RedisPathLockProvider`: reuse the shared CacheRuntime for queue and distributed-lock storage. RedisPathLockProvider requires the built-in RedisProvider.

Call flow:

```text
OpenViking
  -> RAGFS / MountableFS
       |-> CachedFileSystem ------\
       |-> QueueFS cache backend --+-> shared CacheRuntime -> RedisProvider
       `-> RedisPathLockProvider --/                     `-> DynamicProvider
       `-> Backend FileSystem
```

CachedFileSystem and QueueFS can use RedisProvider or DynamicProvider.
RedisPathLockProvider depends on Redis Lua execution and therefore only uses
RedisProvider. Filesystem semantics remain in CachedFileSystem; an external
Provider only supplies primitive key-value operations through the stable C
ABI.

## Cache Objects

RAGFS caches read-only query results. It no longer stores legacy path-object cache entries.

### Query Bucket

Each path and operation has one HASH bucket:

```text
{<service_name>}:ov:cache:v1:<path_key>:<op>
```

Each bucket reserves `__epoch` for a random generation token. Query fields use
`xxh3_128(canonical_request_json)` and store a `QueryCacheEnvelope` containing:

- `request`
- `payload`

RAGFS compares the stored `request` with the current request before returning the cached payload. This protects against hash collisions and request encoding changes.

Supported operations:

- `read` (full-file reads up to `max_file_size_bytes`)
- `stat`
- `read_dir`
- `tree_directory`
- `glob_directory`
- `grep`

### Query Index

All active buckets are registered in one ZSET:

```text
{<service_name>}:ov:cacheidx:v1
```

The ZSET member is the bucket key. The score is `expire_at_ms`. The Redis hash tag keeps buckets and the index in the same cluster slot so CacheFS can update them in one Lua script. This index lets writes delete affected buckets without scanning all Redis keys.

## Consistency and Invalidation

RAGFS does not need a distributed write lock. It physically deletes query buckets affected by each write.

For a normal path change, RAGFS builds the affected bucket list in memory:

- exact path buckets: `read`, `stat`, `read_dir`, `tree_directory`, `glob_directory`, `grep`
- parent bucket: `read_dir(parent)`
- ancestor recursive buckets: `tree_directory`, `glob_directory`, `grep`

It then runs one script per bucket to `UNLINK` the bucket and `ZREM` its index member atomically.

For recursive path operations such as `remove_all`, `rename`, and `replace`, RAGFS also scans the query index:

```text
ZSCAN {<service_name>}:ov:cacheidx:v1 MATCH '{<service_name>}:ov:cache:v1:<path_key>/*:*' COUNT 1000
```

Matched descendant buckets are deleted by the same bucket/index script.
After a miss, an atomic script captures `__epoch` and registers the bucket before backend fallback.
Another script fills the query field and refreshes the index only when that epoch is still current.
A successful `UNLINK` removes the epoch, so an older query cannot restore stale data.
Pending no-TTL epochs expire after 300 seconds; successful fills remain persistent.

Typical write order without `multi_instance`:

```text
Apply backend change
-> Schedule asynchronous invalidation
-> Return result
Background task -> ZSCAN descendant buckets
Background task -> Build exact-path and ancestor buckets
Background task -> Run bucket/index delete script for each bucket
```

With `multi_instance`, the same steps run before the result is returned. Bucket
deletes run concurrently and retry three times with jittered 10, 20 and 40 ms
backoff.

If a Provider fails, RAGFS treats the backend as authoritative for the current request. It records the cache error and does not cache that result.

### Multiple Instances

Several OpenViking instances can share one cache namespace (same
`service_name`, same Redis). Each sees the other instances' fills as cache
hits, and every invalidation reaches all of them. Set `multi_instance: true`
on every instance:

```json
{
  "storage": {
    "agfs": {
      "cachefs": {"backend": "cache", "multi_instance": true}
    }
  }
}
```

Without it, invalidation runs in the background after the write returns. In
one process that window is short, but another instance that reads right after
the write (for example because the writer told it to) can still get the old
listing or `stat`. With `multi_instance`, the write returns only after the
affected buckets are gone, so any read that starts after the write returned
misses and reads the backend. The epoch check above covers reads that were
already in flight.

Writes take longer in this mode: each one waits for its bucket deletes
(roughly one Redis round trip per batch of 16 buckets, plus a `ZSCAN` for
recursive operations).

Startup fails unless the cache default TTL is greater than `0` (with Redis,
`default_ttl_seconds`).

Requirements and remaining risks:

- The backend must give every instance read-after-write consistency (see the
  assumptions at the top of this page).
- If a bucket delete still fails after retries, the write succeeds and
  `invalidation_failures` goes up. **Other instances can serve the old result
  until the bucket's TTL expires.** Alert on this counter and keep
  `default_ttl_seconds` as short as your hit rate allows.
- Redis Sentinel and Cluster replicate asynchronously. A failover can lose a
  delete the old primary had acknowledged, with the same TTL-bounded effect.
  Consider `min-replicas-to-write` on the primary.
- Request coalescing (below) is per process. Instances that miss the same query
  at the same time each read the backend once.

Upgrading from the earlier version-counter CacheFS: its `traversal_mode` and
`bypass_prefixes` options are ignored (`max_file_size_bytes` keeps its meaning),
and its `ov:cache:v2:*` keys are not read. They expire with their TTL, or delete them with
`redis-cli --scan --pattern '<service_name>:ov:cache:v2:*' | xargs redis-cli unlink`.

## Request Coalescing

When multiple requests read the same uncached query at the same time, `CachedFileSystem` uses an in-process inflight table to coalesce them:

```text
The first miss becomes the leader and performs backend fallback and cache fill.
Later requests for the same key become followers and wait for the leader result.
The inflight entry is removed after the request completes.
```

This only reduces duplicate backend access within one OpenViking process. It does not change the Provider consistency boundary.

### File Contents

A full-file `read` (offset 0, no size) of a file up to `max_file_size_bytes`
uses a `read` bucket on the file's path. It follows the same epoch, fill and
invalidation rules as the query buckets, so a write, `truncate`, `rename`,
`replace` or `remove_all` drops it like the file's `stat`. Its field holds the
raw bytes behind a small binary header that records the path, not JSON.

Ranged reads, files over the limit, and runtime-internal files go to the
backend and count as `read` bypasses. `read_to_path` downloads stream from the
backend.

On a single-backend mount with encryption, CacheFS sits below the encryption
layer, so the cache holds ciphertext and each hit is decrypted. Multi-write
mounts encrypt inside each backend, which puts CacheFS above encryption; there,
file contents are never cached while encryption is configured.

Size Redis for the files you let in: each cached file takes up to
`max_file_size_bytes` until its TTL.

## Cache Scope

CacheFS stores full-file contents up to `max_file_size_bytes` and query results for `stat`, `read_dir`, `tree_directory`, `glob_directory`, and `grep`. Cache keys are derived from the path, operation name, and query parameters. Successful writes actively remove affected query buckets. Runtime-internal PathLock files such as `.path.ovlock` and `.exact.ovlock.*` are excluded from query cache payloads, and direct queries against those files bypass CacheFS.

## Failure and Observability

The cache layer must not affect filesystem correctness:

- `get` failure: fall back to backend.
- `put` failure: record the error and keep the backend result.
- `delete` failure: retry, then record the error and count `invalidation_failures`; TTL remains the fallback.
- Provider unavailable: do not return old cache; use backend results as authoritative.

Recommended signals to watch:

- query hit / miss
- provider get / put / delete latency
- cache set / delete failures
- `invalidation_failures` (with `multi_instance`, other instances may serve stale results until the TTL)
- backend fallbacks

## Recommended Rollout

1. Disable caching to validate baseline backend behavior.
2. Use the built-in `redis` Provider to validate remote-cache benefits.
3. Use an independently released DynamicProvider `.so` for high-performance or closed-source cache systems.
4. Cache full-file reads and `stat`, `read_dir`, `tree_directory`, `glob_directory`, and `grep` query results.

RAGFS cache handles invalidation according to filesystem semantics; the Provider decides where cache objects live. The backend remains the source of truth, and every cache hit must pass request validation before it is returned.

After enabling the cache, compare repeated reads and invalidation after a file update against the baseline. A higher hit rate is useful only if the returned contents remain current.
