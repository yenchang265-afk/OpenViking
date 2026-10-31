//! Lightweight metrics owned by the cache wrapper.

use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

/// Filesystem operation that consulted the cache.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CacheOperation {
    /// Full-file `read`.
    Read,
    /// Direct `read_dir` (`ls`).
    ReadDir,
    /// Directory reads issued by cached `tree` traversal.
    Tree,
    /// File and directory reads issued by cached `grep` traversal.
    Grep,
}

impl CacheOperation {
    /// Number of operations tracked per wrapper.
    pub const COUNT: usize = 4;

    /// Every operation in a stable export order.
    pub const fn all() -> [Self; Self::COUNT] {
        [Self::Read, Self::ReadDir, Self::Tree, Self::Grep]
    }

    /// Stable metric label value.
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Read => "read",
            Self::ReadDir => "read_dir",
            Self::Tree => "tree",
            Self::Grep => "grep",
        }
    }

    const fn index(self) -> usize {
        self as usize
    }
}

/// Snapshot of cache lookups made on behalf of one operation.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct CacheOperationSnapshot {
    /// Lookups served from cache.
    pub hits: u64,
    /// Lookups that fell through to the backend.
    pub misses: u64,
    /// Reads that skipped the cache by policy, range semantics, or runtime bypass.
    pub bypasses: u64,
}

#[derive(Default)]
struct CacheOperationCounters {
    hits: AtomicU64,
    misses: AtomicU64,
    bypasses: AtomicU64,
}

impl CacheOperationCounters {
    fn snapshot(&self) -> CacheOperationSnapshot {
        CacheOperationSnapshot {
            hits: self.hits.load(Ordering::Relaxed),
            misses: self.misses.load(Ordering::Relaxed),
            bypasses: self.bypasses.load(Ordering::Relaxed),
        }
    }
}

/// Snapshot of cache wrapper counters.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct CacheMetricsSnapshot {
    /// Successful file cache hits.
    pub file_hits: u64,
    /// File cache misses.
    pub file_misses: u64,
    /// Successful directory cache hits.
    pub read_dir_hits: u64,
    /// Directory cache misses.
    pub read_dir_misses: u64,
    /// Backend loads caused by cache misses.
    pub backend_fallbacks: u64,
    /// Cache writes attempted.
    pub puts: u64,
    /// Cache deletes attempted.
    pub deletes: u64,
    /// Logical invalidations completed.
    pub invalidations: u64,
    /// Provider or cache-data errors hidden by bypass mode.
    pub errors: u64,
    /// Reads deliberately bypassed by policy or range semantics.
    pub policy_bypasses: u64,
    /// Backend bytes returned on cacheable reads.
    pub backend_bytes: u64,
    /// Bytes returned from cache objects.
    pub cache_bytes: u64,
    /// Total provider get latency in nanoseconds.
    pub get_latency_ns: u64,
    /// Total provider put latency in nanoseconds.
    pub put_latency_ns: u64,
    /// Total provider delete latency in nanoseconds.
    pub delete_latency_ns: u64,
    /// Inflight miss leaders.
    pub inflight_leaders: u64,
    /// Inflight miss followers.
    pub inflight_followers: u64,
    /// Backend reads avoided by inflight followers.
    pub inflight_backend_saved: u64,
    /// Cached entries rejected because a recorded counter moved since the fill.
    pub stale_versions: u64,
    /// Counter bumps that still failed after retries; other instances may
    /// serve stale entries for the affected paths until the cache TTL.
    pub invalidation_failures: u64,
    /// Hit, miss, and bypass counts indexed in `CacheOperation::all()` order.
    pub operations: [CacheOperationSnapshot; CacheOperation::COUNT],
}

impl CacheMetricsSnapshot {
    /// Return the counts recorded for one operation.
    pub fn operation(&self, operation: CacheOperation) -> CacheOperationSnapshot {
        self.operations[operation.index()]
    }
}

/// Thread-safe cache metric counters.
#[derive(Default)]
pub struct CacheMetrics {
    file_hits: AtomicU64,
    file_misses: AtomicU64,
    read_dir_hits: AtomicU64,
    read_dir_misses: AtomicU64,
    backend_fallbacks: AtomicU64,
    puts: AtomicU64,
    deletes: AtomicU64,
    invalidations: AtomicU64,
    errors: AtomicU64,
    policy_bypasses: AtomicU64,
    backend_bytes: AtomicU64,
    cache_bytes: AtomicU64,
    get_latency_ns: AtomicU64,
    put_latency_ns: AtomicU64,
    delete_latency_ns: AtomicU64,
    inflight_leaders: AtomicU64,
    inflight_followers: AtomicU64,
    inflight_backend_saved: AtomicU64,
    stale_versions: AtomicU64,
    invalidation_failures: AtomicU64,
    operations: [CacheOperationCounters; CacheOperation::COUNT],
}

impl CacheMetrics {
    /// Return an immutable snapshot.
    pub fn snapshot(&self) -> CacheMetricsSnapshot {
        CacheMetricsSnapshot {
            file_hits: self.file_hits.load(Ordering::Relaxed),
            file_misses: self.file_misses.load(Ordering::Relaxed),
            read_dir_hits: self.read_dir_hits.load(Ordering::Relaxed),
            read_dir_misses: self.read_dir_misses.load(Ordering::Relaxed),
            backend_fallbacks: self.backend_fallbacks.load(Ordering::Relaxed),
            puts: self.puts.load(Ordering::Relaxed),
            deletes: self.deletes.load(Ordering::Relaxed),
            invalidations: self.invalidations.load(Ordering::Relaxed),
            errors: self.errors.load(Ordering::Relaxed),
            policy_bypasses: self.policy_bypasses.load(Ordering::Relaxed),
            backend_bytes: self.backend_bytes.load(Ordering::Relaxed),
            cache_bytes: self.cache_bytes.load(Ordering::Relaxed),
            get_latency_ns: self.get_latency_ns.load(Ordering::Relaxed),
            put_latency_ns: self.put_latency_ns.load(Ordering::Relaxed),
            delete_latency_ns: self.delete_latency_ns.load(Ordering::Relaxed),
            inflight_leaders: self.inflight_leaders.load(Ordering::Relaxed),
            inflight_followers: self.inflight_followers.load(Ordering::Relaxed),
            inflight_backend_saved: self.inflight_backend_saved.load(Ordering::Relaxed),
            stale_versions: self.stale_versions.load(Ordering::Relaxed),
            invalidation_failures: self.invalidation_failures.load(Ordering::Relaxed),
            operations: std::array::from_fn(|index| self.operations[index].snapshot()),
        }
    }

    fn operation(&self, operation: CacheOperation) -> &CacheOperationCounters {
        &self.operations[operation.index()]
    }

    pub(crate) fn file_hit(&self, operation: CacheOperation, bytes: usize) {
        self.file_hits.fetch_add(1, Ordering::Relaxed);
        self.cache_bytes.fetch_add(bytes as u64, Ordering::Relaxed);
        self.operation(operation)
            .hits
            .fetch_add(1, Ordering::Relaxed);
    }

    pub(crate) fn file_miss(&self, operation: CacheOperation) {
        self.file_misses.fetch_add(1, Ordering::Relaxed);
        self.operation(operation)
            .misses
            .fetch_add(1, Ordering::Relaxed);
    }

    pub(crate) fn read_dir_hit(&self, operation: CacheOperation) {
        self.read_dir_hits.fetch_add(1, Ordering::Relaxed);
        self.operation(operation)
            .hits
            .fetch_add(1, Ordering::Relaxed);
    }

    pub(crate) fn read_dir_miss(&self, operation: CacheOperation) {
        self.read_dir_misses.fetch_add(1, Ordering::Relaxed);
        self.operation(operation)
            .misses
            .fetch_add(1, Ordering::Relaxed);
    }

    pub(crate) fn backend_fallback(&self, bytes: usize) {
        self.backend_fallbacks.fetch_add(1, Ordering::Relaxed);
        self.backend_bytes
            .fetch_add(bytes as u64, Ordering::Relaxed);
    }

    pub(crate) fn put(&self, elapsed: Duration) {
        self.puts.fetch_add(1, Ordering::Relaxed);
        self.put_latency_ns.fetch_add(
            elapsed.as_nanos().min(u64::MAX as u128) as u64,
            Ordering::Relaxed,
        );
    }

    pub(crate) fn get(&self, elapsed: Duration) {
        self.get_latency_ns.fetch_add(
            elapsed.as_nanos().min(u64::MAX as u128) as u64,
            Ordering::Relaxed,
        );
    }

    pub(crate) fn delete(&self, elapsed: Duration) {
        self.deletes.fetch_add(1, Ordering::Relaxed);
        self.delete_latency_ns.fetch_add(
            elapsed.as_nanos().min(u64::MAX as u128) as u64,
            Ordering::Relaxed,
        );
    }

    pub(crate) fn invalidation(&self) {
        self.invalidations.fetch_add(1, Ordering::Relaxed);
    }

    pub(crate) fn error(&self) {
        self.errors.fetch_add(1, Ordering::Relaxed);
    }

    pub(crate) fn policy_bypass(&self, operation: CacheOperation) {
        self.policy_bypasses.fetch_add(1, Ordering::Relaxed);
        self.operation(operation)
            .bypasses
            .fetch_add(1, Ordering::Relaxed);
    }

    pub(crate) fn inflight_leader(&self) {
        self.inflight_leaders.fetch_add(1, Ordering::Relaxed);
    }

    pub(crate) fn inflight_follower(&self) {
        self.inflight_followers.fetch_add(1, Ordering::Relaxed);
    }

    pub(crate) fn inflight_backend_saved(&self) {
        self.inflight_backend_saved.fetch_add(1, Ordering::Relaxed);
    }

    pub(crate) fn stale_version(&self) {
        self.stale_versions.fetch_add(1, Ordering::Relaxed);
    }

    pub(crate) fn invalidation_failure(&self) {
        self.invalidation_failures.fetch_add(1, Ordering::Relaxed);
    }
}
