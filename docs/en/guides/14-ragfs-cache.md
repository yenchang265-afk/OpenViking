# RAGFS Cache

RAGFS cache is an optional read-cache layer for OpenViking. It speeds up full file reads and directory reads. It is only an acceleration layer, not the source of truth; backend filesystem data remains authoritative.

CachedFileSystem assumptions:

- When more than one OpenViking / RAGFS process shares a cache namespace (the same `service_name` on the same cache Provider), every one of them sets `storage.agfs.cachefs.multi_instance: true`. See "Multiple Instances" below.
- File and directory changes go through RAGFS.
- The backend is not modified externally by bypassing RAGFS.
- Every instance sees the same backend, and a backend write is visible to every instance once it returns. S3 or SeaweedFS and the MariaDB small-file tier qualify; separate local disks per pod do not.
- After a cache Provider successfully writes, deletes, or increments one key, later reads of that key do not return the old value.

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
      "default_ttl_seconds": 3600
    }
  },
  "storage": {
    "workspace": "./data",
    "agfs": {
      "backend": "local",
      "cachefs": {
        "backend": "cache",
        "max_file_size_bytes": 1048576,
        "bypass_prefixes": ["/queue", "/tmp"]
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
Use distinct service names for independent deployments. CachedFileSystem
does not rely on PathLock for cache consistency; it uses its own version
counters (see "Consistency and Invalidation").
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

CacheFS keys moved from `ov:cache:v1` to `ov:cache:v2`, and cache envelopes to
format version 2. The cache starts empty once after the upgrade. Old and new
versions never read each other's entries, but an old instance does not bump
the new version counters, so **do not run old and new versions against the
same namespace at the same time**. To upgrade a fleet: set
`storage.agfs.cachefs.backend` to `local` on every instance, roll out the new
version, then switch CacheFS back on. Stopping every old instance before
starting the new ones also works.

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
| `max_file_size_bytes` | int | `1048576` | Maximum full-file object size admitted to cache |
| `traversal_mode` | str | `"backend"` | Use backend traversal or `cached_traversal` for recursive APIs |
| `bypass_prefixes` | list[str] | `[]` | Path prefixes that always bypass cache |
| `multi_instance` | bool | `false` | Set on every instance when several processes share the cache namespace. Requires `backend="cache"`, a Provider with atomic `incrby`, and (with Redis) `default_ttl_seconds > 0` |

`storage.agfs.pathlock` controls PathLock storage:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `provider` | str | `"filesystem"` | `filesystem`, `memory`, or `cache` |
| `lock_expire_secs` | float | `30.0` | Lock stale timeout; must be at least `1.0` |

Redis configuration:

| Option | Default | Description |
|--------|---------|-------------|
| `mode` | `"standalone"` | Redis deployment mode |
| `endpoints` | `["redis://127.0.0.1:6379"]` | Redis connection URLs; use `redis://` for plaintext or `rediss://` for TLS |
| `username` | `""` | Redis ACL username |
| `password_env` | `""` | Environment variable that stores the Redis password |
| `pool_size` | `32` | Command concurrency |
| `connect_timeout_ms` | `1000` | Connection timeout |
| `command_timeout_ms` | `20` | Command timeout |
| `default_ttl_seconds` | `3600` | Default TTL; `0` means no TTL |
| `tls_insecure_skip_verify` | `false` | Skip certificate verification for `rediss://`; intended only for controlled test environments |

All Redis reads are sent to the primary node so QueueFS does not observe stale queue state. CacheRuntime relies on Redis transport security when required and does not add a separate application-layer value encryption format.

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

- `CachedFileSystem`: implements filesystem semantics, including cache hit/miss handling, backend fallback, cache fill, invalidation, version checks, and metrics.
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

RAGFS mainly caches three object types.

### File Cache

File keys use a stable namespace and path hash:

```text
<service_name>:ov:cache:v2:file:<hash(path)>
```

The file value is a `CacheEnvelope` containing file content, object kind, path, and a snapshot of the version counters it depends on. After a full-read cache hit, RAGFS validates the envelope and every recorded counter before returning the content.

The default policy prefers summary files such as `.abstract.md` and `.overview.md`. Files larger than `max_file_size_bytes` are not admitted to cache. Non-full range reads also bypass the cache.

### Directory Cache

Directory key:

```text
<service_name>:ov:cache:v2:dir:<hash(path)>
```

The directory cache stores raw backend `read_dir` entries, not permission-filtered final results. Permission, role, and agent-context filtering still happens in the OpenViking upper layer at request time.

This lets one directory cache object serve `ls`, `tree`, `glob`, the file-collection phase of `grep`, and path collection before delete or move operations.

### Version Counters

Two kinds of counters decide whether an envelope is still valid:

```text
<service_name>:ov:cache:v2:ver:<hash(path)>       object version of one path
<service_name>:ov:cache:v2:subtree:<hash(scope)>  generation of one directory scope
```

An envelope for `path` records the object version of `path` and the subtree
generation of every ancestor scope, including `path` itself. Counters are
decimal integers, so the Provider can advance them with an atomic `INCRBY`.
A missing counter (expired or evicted) is re-created from a random value with
`SET NX`, so every instance adopts the same value and old envelopes never
match by accident.

`remove_all` and directory `rename` can leave descendant keys behind in the
Provider. RAGFS bumps the subtree generation, so every descendant envelope
fails its check. Later real reads fall back to the backend and rebuild the
cache.

## Consistency and Invalidation

RAGFS keeps the cache correct with two rules:

1. **Snapshot before reading.** On a miss, RAGFS reads the counters an envelope
   needs *before* it reads the backend, and stores that snapshot in the
   envelope.
2. **Bump after changing.** After every backend change, RAGFS bumps the
   affected counters. A cache hit is returned only if every recorded counter
   still has its recorded value.

A fill that raced a change therefore never validates: either its snapshot came
before the bump and no longer matches, or it came after the bump and the
backend read already included the change. This holds across processes, so no
distributed write lock is needed.

Counters bumped by each operation:

| Operation | Bumped counters |
|-----------|-----------------|
| `create`, `write`, `write_from_path`, `truncate`, `chmod` | `ver(path)`, `ver(parent)` |
| `mkdir`, `remove`, `remove_all` | `subtree(path)`, `ver(path)`, `ver(parent)` |
| `rename`, `replace` | `subtree` and `ver` of both paths, `ver` of both parents |
| `ensure_parent_dirs` | `ver` of every ancestor scope |

RAGFS still deletes the affected `file` and `dir` keys after a change, but only
to free space; the bump is what invalidates.

Typical write order:

```text
Acquire the in-process operation lock
-> Apply backend change
-> Bump the affected counters (INCRBY)
-> Delete the affected file/dir keys
-> Return result
```

### Multiple Instances

Several OpenViking instances can share one cache namespace (same
`service_name`, same Redis). Each sees the other instances' fills as cache
hits, and every bump reaches all of them. Set `multi_instance: true` on every
instance:

```json
{
  "storage": {
    "agfs": {
      "cachefs": {"backend": "cache", "multi_instance": true}
    }
  }
}
```

Multi-instance mode changes two things:

- A full write no longer fills the cache with the written bytes. Two instances
  writing the same file could otherwise fill in the opposite order of their
  backend writes. The next read fills the cache instead.
- Startup fails unless the Provider supports atomic `incrby` (the built-in
  Redis Provider does; a DynamicProvider must export it). With Redis,
  `default_ttl_seconds` must be greater than `0`.

Requirements and remaining risks:

- The backend must give every instance read-after-write consistency (see the
  assumptions at the top of this page).
- If a bump still fails after retries (10, 50, and 200 ms), the write succeeds,
  the failing instance bypasses the cache for that path, and
  `invalidation_failures` goes up. **Other instances can serve the old entry
  until its TTL expires.** Alert on this counter and keep
  `default_ttl_seconds` as short as your hit rate allows.
- Redis Sentinel and Cluster replicate asynchronously. A failover can lose a
  bump the old primary had acknowledged, with the same TTL-bounded effect.
  Consider `min-replicas-to-write` on the primary.
- In Redis Cluster mode the counters of one path live in different slots, so a
  miss reads them one key at a time.

Without `multi_instance`, writers in one process are serialized by its
operation lock, and a full write also fills the cache. Providers without
`incrby` then fall back to GET+SET bumps, which are only safe for one process.

## Request Coalescing

When multiple requests read the same uncached small file or directory at the same time, `CachedFileSystem` uses an in-process inflight table to coalesce them:

```text
The first miss becomes the leader and performs backend fallback and cache fill.
Later requests for the same key become followers and wait for the leader result.
The inflight entry is removed after the request completes.
```

This only reduces duplicate backend access within one OpenViking process. It does not change the Provider consistency boundary.

## Cache Policy

RAGFS automatically bypasses paths that are not suitable for caching:

- Lock files: `.path.ovlock`, `*.lock`, `*.lck`
- Control files: `enqueue`, `dequeue`, `peek`, `ack`
- Transient state: `heartbeat`, `lease`, `cursor`, `offset`, `pid`
- Path prefixes configured through `bypass_prefixes`

Add permission-sensitive directories to `bypass_prefixes`. If raw directory entries themselves depend on the caller's permissions, that directory should not be cached.

## Failure and Observability

The cache layer must not affect filesystem correctness:

- `get` failure: fall back to backend.
- `put` failure: record the error and put the path into bypass.
- `delete` failure: record the error and put the path or scope into bypass.
- Counter bump failure: retry, then count an invalidation failure and put the path into bypass on this instance.
- Provider unavailable: do not return old cache; use backend results as authoritative.

Recommended signals to watch:

- cache hit / miss / bypass
- stale versions (entries rejected because a counter moved)
- invalidation failures (bumps that failed after retries)
- provider get / put / delete latency
- cache set / delete failures
- inflight leader / follower / backend saved
- backend fallback bytes

When CacheFS is enabled, OpenViking Studio shows the overall cache hit rate on
the Home dashboard and a per-operation breakdown (`read`, `read_dir`, `tree`,
`grep`) under Monitoring → Cache. Both read `GET /api/v1/console/cache`, which
reports counters since server start. Hit rate is `hits / (hits + misses)`;
reads bypassed by policy are counted separately. The same endpoint also reports
`stale_versions` and `invalidation_failures`. The same counters are exported
as `openviking_ragfs_cache_requests_total`,
`openviking_ragfs_cache_operation_requests_total`,
`openviking_ragfs_cache_stale_versions_total`, and
`openviking_ragfs_cache_invalidation_failures_total`.

## Recommended Rollout

1. Disable caching to validate baseline backend behavior.
2. Use the built-in `redis` Provider to validate remote-cache benefits.
3. Use an independently released DynamicProvider `.so` for high-performance or closed-source cache systems.
4. Cache summary files and raw `read_dir` first, then expand to more regular small files.
5. Add lock, control-plane, and permission-sensitive paths to `bypass_prefixes`.

RAGFS cache handles invalidation according to filesystem semantics; the Provider decides where cache objects live. The backend remains the source of truth, and every cache hit must pass envelope and version validation before it is returned.

After enabling the cache, compare repeated reads and invalidation after a file update against the baseline. A higher hit rate is useful only if the returned contents remain current.
