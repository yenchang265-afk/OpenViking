//! Two CacheFS instances in multi-instance mode on a real Redis.
//!
//! Each instance has its own Redis connection, like two pods. Runs against
//! `REDIS_URL` (standalone), `REDIS_CLUSTER_URLS` (comma-separated seeds) and
//! `REDIS_SENTINEL_TEST_URLS` with `REDIS_SENTINEL_TEST_MASTER`, whichever are
//! set; skips otherwise.

use ragfs::cache::CachedFileSystem;
use ragfs::cache_runtime::{CacheRuntime, RedisProviderConfig};
use ragfs::core::{FileInfo, FileSystem, ListSortBy, Result, SortOrder};
use ragfs::plugins::MemFileSystem;
use ragfs::WriteFlag;
use std::sync::Arc;

/// Forwards to one backend shared by several cache wrappers.
struct Shared(Arc<dyn FileSystem>);

#[async_trait::async_trait]
impl FileSystem for Shared {
    async fn create(&self, path: &str) -> Result<()> {
        self.0.create(path).await
    }
    async fn mkdir(&self, path: &str, mode: u32) -> Result<()> {
        self.0.mkdir(path, mode).await
    }
    async fn remove(&self, path: &str) -> Result<()> {
        self.0.remove(path).await
    }
    async fn remove_all(&self, path: &str) -> Result<()> {
        self.0.remove_all(path).await
    }
    async fn read(&self, path: &str, offset: u64, size: u64) -> Result<Vec<u8>> {
        self.0.read(path, offset, size).await
    }
    async fn write(&self, path: &str, data: &[u8], offset: u64, flags: WriteFlag) -> Result<u64> {
        self.0.write(path, data, offset, flags).await
    }
    async fn read_dir(
        &self,
        path: &str,
        offset: Option<usize>,
        limit: Option<usize>,
        sort_by: Option<ListSortBy>,
        sort_order: Option<SortOrder>,
    ) -> Result<Vec<FileInfo>> {
        self.0
            .read_dir(path, offset, limit, sort_by, sort_order)
            .await
    }
    async fn stat(&self, path: &str) -> Result<FileInfo> {
        self.0.stat(path).await
    }
    async fn rename(&self, old_path: &str, new_path: &str) -> Result<()> {
        self.0.rename(old_path, new_path).await
    }
    async fn chmod(&self, path: &str, mode: u32) -> Result<()> {
        self.0.chmod(path, mode).await
    }
}

fn endpoints(variable: &str) -> Option<Vec<String>> {
    let endpoints = std::env::var(variable)
        .ok()?
        .split(',')
        .map(str::trim)
        .filter(|endpoint| !endpoint.is_empty())
        .map(str::to_string)
        .collect::<Vec<_>>();
    (!endpoints.is_empty()).then_some(endpoints)
}

fn configs() -> Vec<(&'static str, RedisProviderConfig)> {
    let base = RedisProviderConfig {
        connect_timeout_ms: 10_000,
        command_timeout_ms: 3_000,
        default_ttl_seconds: 60,
        ..RedisProviderConfig::default()
    };
    let mut configs = Vec::new();
    if let Ok(url) = std::env::var("REDIS_URL") {
        configs.push((
            "standalone",
            RedisProviderConfig {
                endpoints: vec![url],
                ..base.clone()
            },
        ));
    }
    if let Some(endpoints) = endpoints("REDIS_CLUSTER_URLS") {
        configs.push((
            "cluster",
            RedisProviderConfig {
                mode: "cluster".into(),
                endpoints,
                ..base.clone()
            },
        ));
    }
    if let (Some(endpoints), Ok(master)) = (
        endpoints("REDIS_SENTINEL_TEST_URLS"),
        std::env::var("REDIS_SENTINEL_TEST_MASTER"),
    ) {
        configs.push((
            "sentinel",
            RedisProviderConfig {
                mode: "sentinel".into(),
                endpoints,
                master_name: Some(master),
                ..base
            },
        ));
    }
    configs
}

async fn names(fs: &CachedFileSystem, path: &str) -> Vec<String> {
    let mut names = fs
        .read_dir(path, None, None, None, None)
        .await
        .unwrap()
        .into_iter()
        .map(|entry| entry.name)
        .collect::<Vec<_>>();
    names.sort();
    names
}

async fn pair(mode: &str, config: &RedisProviderConfig) -> (CachedFileSystem, CachedFileSystem) {
    let backend: Arc<dyn FileSystem> = Arc::new(MemFileSystem::new());
    backend.mkdir("/docs", 0o755).await.unwrap();
    backend.mkdir("/docs/sub", 0o755).await.unwrap();
    backend
        .write("/docs/sub/a.txt", b"v1", 0, WriteFlag::Create)
        .await
        .unwrap();
    let service = format!("ragfs-multi-{mode}-{}", uuid::Uuid::new_v4());
    let mut instances = Vec::new();
    for _ in 0..2 {
        instances.push(
            CachedFileSystem::with_runtime(
                Box::new(Shared(Arc::clone(&backend))),
                CacheRuntime::redis(config.clone()).await.unwrap(),
                service.clone(),
            )
            .with_multi_instance(true),
        );
    }
    let b = instances.pop().unwrap();
    (instances.pop().unwrap(), b)
}

#[tokio::test]
async fn multi_instance_mutations_are_visible_on_the_other_instance_when_they_return() {
    for (mode, config) in configs() {
        let (a, b) = pair(mode, &config).await;

        // Fill b's cache, then confirm it is served from Redis.
        assert_eq!(names(&b, "/docs/sub").await, ["a.txt"], "{mode}");
        assert_eq!(b.stat("/docs/sub/a.txt").await.unwrap().size, 2, "{mode}");
        names(&b, "/docs").await;
        let hits = b.metrics().snapshot().query_hits;
        assert_eq!(names(&b, "/docs/sub").await, ["a.txt"], "{mode}");
        assert_eq!(b.metrics().snapshot().query_hits, hits + 1, "{mode}");

        a.write("/docs/sub/a.txt", b"v2-longer", 0, WriteFlag::Create)
            .await
            .unwrap();
        a.write("/docs/sub/b.txt", b"x", 0, WriteFlag::Create)
            .await
            .unwrap();
        assert_eq!(names(&b, "/docs/sub").await, ["a.txt", "b.txt"], "{mode}");
        assert_eq!(b.stat("/docs/sub/a.txt").await.unwrap().size, 9, "{mode}");

        a.rename("/docs/sub", "/docs/moved").await.unwrap();
        assert_eq!(names(&b, "/docs").await, ["moved"], "{mode}");
        assert!(b.stat("/docs/sub/a.txt").await.is_err(), "{mode}");

        names(&b, "/docs/moved").await;
        b.stat("/docs/moved/b.txt").await.unwrap();
        a.remove_all("/docs/moved").await.unwrap();
        assert!(b.stat("/docs/moved/b.txt").await.is_err(), "{mode}");
        assert!(names(&b, "/docs").await.is_empty(), "{mode}");

        assert_eq!(a.metrics().snapshot().invalidation_failures, 0, "{mode}");
    }
}
