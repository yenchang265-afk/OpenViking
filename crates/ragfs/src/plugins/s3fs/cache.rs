//! Dual-layer cache for S3FS
//!
//! Provides two caches:
//! - **ListDirCache**: Caches directory listing results (default TTL: 30s)
//! - **StatCache**: Caches file/directory metadata (default TTL: 60s, 5x capacity)
//!
//! Both caches use LRU eviction with TTL-based expiry.

use super::single_flight::SingleFlight;
use crate::core::types::FileInfo;
use crate::core::Result;
use lru::LruCache;
use std::future::Future;
use std::num::NonZeroUsize;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::RwLock;

/// Cache entry with timestamp for TTL
#[derive(Clone)]
struct CacheEntry<T: Clone> {
    value: T,
    timestamp: Instant,
}

/// Inner cache state (generic)
struct CacheInner<T: Clone> {
    cache: LruCache<String, CacheEntry<T>>,
    ttl: Duration,
    enabled: bool,
}

/// Generic TTL-LRU cache
struct TtlLruCache<T: Clone> {
    inner: Arc<RwLock<CacheInner<T>>>,
}

impl<T: Clone> TtlLruCache<T> {
    fn new(max_size: usize, ttl: Duration, enabled: bool) -> Self {
        let max_size = if max_size == 0 { 1000 } else { max_size };
        Self {
            inner: Arc::new(RwLock::new(CacheInner {
                cache: LruCache::new(NonZeroUsize::new(max_size).unwrap()),
                ttl,
                enabled,
            })),
        }
    }

    async fn get(&self, key: &str) -> Option<T> {
        let mut inner = self.inner.write().await;
        if !inner.enabled {
            return None;
        }

        let ttl = inner.ttl;
        let result = inner.cache.get(key).and_then(|entry| {
            if Instant::now().duration_since(entry.timestamp) > ttl {
                None
            } else {
                Some(entry.value.clone())
            }
        });

        match result {
            Some(value) => {
                if let Some(entry) = inner.cache.get_mut(key) {
                    entry.timestamp = Instant::now();
                }
                Some(value)
            }
            None => {
                inner.cache.pop(key);
                None
            }
        }
    }

    async fn put(&self, key: String, value: T) {
        let mut inner = self.inner.write().await;
        if !inner.enabled {
            return;
        }
        inner.cache.put(
            key,
            CacheEntry {
                value,
                timestamp: Instant::now(),
            },
        );
    }

    async fn invalidate(&self, key: &str) {
        let mut inner = self.inner.write().await;
        inner.cache.pop(key);
    }

    async fn invalidate_prefix(&self, prefix: &str) {
        let mut inner = self.inner.write().await;
        if !inner.enabled {
            return;
        }

        let normalized_prefix = if prefix == "/" {
            "/"
        } else {
            prefix.trim_end_matches('/')
        };
        let child_prefix = if normalized_prefix == "/" {
            "/".to_string()
        } else {
            format!("{normalized_prefix}/")
        };
        let to_remove: Vec<String> = inner
            .cache
            .iter()
            .filter(|(k, _)| *k == normalized_prefix || k.starts_with(&child_prefix))
            .map(|(k, _)| k.clone())
            .collect();

        for key in to_remove {
            inner.cache.pop(&key);
        }
    }

    async fn invalidate_parent(&self, path: &str) {
        if let Some(parent) = parent_path(path) {
            self.invalidate(&parent).await;
        }
    }
}

/// Parent directory of `path` ("/" is its own parent).
fn parent_path(path: &str) -> Option<String> {
    if path == "/" {
        return Some("/".to_string());
    }
    let trimmed = path.trim_end_matches('/');
    let pos = trimmed.rfind('/')?;
    Some(if pos == 0 {
        "/".to_string()
    } else {
        trimmed[..pos].to_string()
    })
}

/// Directory listing cache
pub struct S3ListDirCache {
    cache: TtlLruCache<Vec<FileInfo>>,
}

impl S3ListDirCache {
    /// Create a new directory listing cache
    pub fn new(max_size: usize, ttl_seconds: u64, enabled: bool) -> Self {
        Self {
            cache: TtlLruCache::new(
                max_size,
                Duration::from_secs(if ttl_seconds == 0 { 30 } else { ttl_seconds }),
                enabled,
            ),
        }
    }

    /// Get cached listing
    pub async fn get(&self, path: &str) -> Option<Vec<FileInfo>> {
        self.cache.get(path).await
    }

    /// Store listing
    pub async fn put(&self, path: String, files: Vec<FileInfo>) {
        self.cache.put(path, files).await;
    }

    /// Invalidate a specific path
    pub async fn invalidate(&self, path: &str) {
        self.cache.invalidate(path).await;
    }

    /// Invalidate all entries with a prefix
    pub async fn invalidate_prefix(&self, prefix: &str) {
        self.cache.invalidate_prefix(prefix).await;
    }

    /// Invalidate the parent of a path
    pub async fn invalidate_parent(&self, path: &str) {
        self.cache.invalidate_parent(path).await;
    }
}

/// File metadata (stat) cache
pub struct S3StatCache {
    cache: TtlLruCache<Option<FileInfo>>,
    /// In-flight lookups for cache misses. Invalidation detaches them so a
    /// caller arriving after a write never joins a lookup that began before it.
    flights: SingleFlight<FileInfo>,
}

impl S3StatCache {
    /// Create a new stat cache (5x the capacity of dir cache)
    pub fn new(max_size: usize, ttl_seconds: u64, enabled: bool) -> Self {
        let max_size = if max_size == 0 { 5000 } else { max_size * 5 };
        Self {
            cache: TtlLruCache::new(
                max_size,
                Duration::from_secs(if ttl_seconds == 0 { 60 } else { ttl_seconds }),
                enabled,
            ),
            flights: SingleFlight::default(),
        }
    }

    /// Run `fetch` for a cache miss on `path`, sharing it with concurrent misses.
    pub(crate) async fn coalesce<F, Fut>(&self, path: &str, fetch: F) -> Result<FileInfo>
    where
        F: FnOnce() -> Fut,
        Fut: Future<Output = Result<FileInfo>>,
    {
        self.flights.run(path, fetch).await
    }

    /// Get cached stat result
    pub async fn get(&self, path: &str) -> Option<Option<FileInfo>> {
        self.cache.get(path).await
    }

    /// Store stat result (None means "does not exist")
    pub async fn put(&self, path: String, info: Option<FileInfo>) {
        self.cache.put(path, info).await;
    }

    /// Invalidate a specific path
    pub async fn invalidate(&self, path: &str) {
        self.flights.forget(path);
        self.cache.invalidate(path).await;
    }

    /// Invalidate all entries with a prefix
    pub async fn invalidate_prefix(&self, prefix: &str) {
        self.flights.forget_prefix(prefix);
        self.cache.invalidate_prefix(prefix).await;
    }

    /// Invalidate the parent of a path
    pub async fn invalidate_parent(&self, path: &str) {
        if let Some(parent) = parent_path(path) {
            self.flights.forget(&parent);
        }
        self.cache.invalidate_parent(path).await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_list_dir_cache_basic() {
        let cache = S3ListDirCache::new(10, 5, true);

        // Miss
        assert!(cache.get("/test").await.is_none());

        // Put and hit
        let files = vec![FileInfo {
            name: "file.txt".to_string(),
            size: 100,
            mode: 0o644,
            mod_time: std::time::SystemTime::now(),
            is_dir: false,
        }];

        cache.put("/test".to_string(), files.clone()).await;
        let result = cache.get("/test").await;
        assert!(result.is_some());
        assert_eq!(result.unwrap().len(), 1);
    }

    #[tokio::test]
    async fn test_stat_cache_basic() {
        let cache = S3StatCache::new(10, 5, true);

        // Miss
        assert!(cache.get("/test").await.is_none());

        // Put file info
        let info = FileInfo {
            name: "file.txt".to_string(),
            size: 100,
            mode: 0o644,
            mod_time: std::time::SystemTime::now(),
            is_dir: false,
        };

        cache.put("/test".to_string(), Some(info)).await;
        let result = cache.get("/test").await;
        assert!(result.is_some());
        assert!(result.unwrap().is_some());
    }

    #[tokio::test]
    async fn test_stat_cache_negative() {
        let cache = S3StatCache::new(10, 5, true);

        // Cache a "not found" result
        cache.put("/missing".to_string(), None).await;
        let result = cache.get("/missing").await;
        assert!(result.is_some()); // entry exists
        assert!(result.unwrap().is_none()); // but value is None
    }

    #[tokio::test]
    async fn test_cache_invalidation() {
        let cache = S3ListDirCache::new(10, 60, true);

        cache.put("/a".to_string(), vec![]).await;
        cache.put("/a/b".to_string(), vec![]).await;
        cache.put("/c".to_string(), vec![]).await;

        // Invalidate prefix /a
        cache.invalidate_prefix("/a").await;

        assert!(cache.get("/a").await.is_none());
        assert!(cache.get("/a/b").await.is_none());
        assert!(cache.get("/c").await.is_some()); // unaffected
    }

    #[tokio::test]
    async fn test_cache_disabled() {
        let cache = S3ListDirCache::new(10, 5, false);

        cache.put("/test".to_string(), vec![]).await;
        assert!(cache.get("/test").await.is_none());
    }

    #[tokio::test]
    async fn test_root_prefix_invalidation_clears_descendants() {
        let cache = S3ListDirCache::new(10, 60, true);
        cache.put("/".to_string(), vec![]).await;
        cache.put("/a".to_string(), vec![]).await;
        cache.put("/a/b".to_string(), vec![]).await;

        cache.invalidate_prefix("/").await;

        assert!(cache.get("/").await.is_none());
        assert!(cache.get("/a").await.is_none());
        assert!(cache.get("/a/b").await.is_none());
    }

    #[tokio::test]
    async fn test_prefix_invalidation_normalizes_trailing_slash() {
        let cache = S3ListDirCache::new(10, 60, true);
        cache.put("/a".to_string(), vec![]).await;
        cache.put("/a/b".to_string(), vec![]).await;
        cache.put("/ab".to_string(), vec![]).await;

        cache.invalidate_prefix("/a/").await;

        assert!(cache.get("/a").await.is_none());
        assert!(cache.get("/a/b").await.is_none());
        assert!(cache.get("/ab").await.is_some());
    }
}
