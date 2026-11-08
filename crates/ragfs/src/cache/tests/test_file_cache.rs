//! Full-file reads through the CacheFS `read` bucket.

use super::*;
use crate::cache_runtime::{CacheRuntime, MemoryMockProvider};
use crate::core::mountable::ArcFileSystem;
use crate::core::{FileSystem, WriteFlag};
use crate::plugins::memfs::MemFileSystem;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;

const SERVICE_NAME: &str = "file-cache-test";

/// Counts backend reads so tests can tell cache hits from backend loads.
struct CountingFs {
    inner: MemFileSystem,
    reads: Arc<AtomicU64>,
}

#[async_trait]
impl FileSystem for CountingFs {
    async fn create(&self, path: &str) -> Result<()> {
        self.inner.create(path).await
    }
    async fn mkdir(&self, path: &str, mode: u32) -> Result<()> {
        self.inner.mkdir(path, mode).await
    }
    async fn remove(&self, path: &str) -> Result<()> {
        self.inner.remove(path).await
    }
    async fn remove_all(&self, path: &str) -> Result<()> {
        self.inner.remove_all(path).await
    }
    async fn read(&self, path: &str, offset: u64, size: u64) -> Result<Vec<u8>> {
        self.reads.fetch_add(1, Ordering::SeqCst);
        self.inner.read(path, offset, size).await
    }
    async fn write(&self, path: &str, data: &[u8], offset: u64, flags: WriteFlag) -> Result<u64> {
        self.inner.write(path, data, offset, flags).await
    }
    async fn read_dir(
        &self,
        path: &str,
        offset: Option<usize>,
        limit: Option<usize>,
        sort_by: Option<ListSortBy>,
        sort_order: Option<SortOrder>,
    ) -> Result<Vec<FileInfo>> {
        self.inner
            .read_dir(path, offset, limit, sort_by, sort_order)
            .await
    }
    async fn stat(&self, path: &str) -> Result<FileInfo> {
        self.inner.stat(path).await
    }
    async fn rename(&self, old_path: &str, new_path: &str) -> Result<()> {
        self.inner.rename(old_path, new_path).await
    }
    async fn chmod(&self, path: &str, mode: u32) -> Result<()> {
        self.inner.chmod(path, mode).await
    }
}

struct Fixture {
    reads: Arc<AtomicU64>,
    a: CachedFileSystem,
    b: CachedFileSystem,
}

impl Fixture {
    fn reads(&self) -> u64 {
        self.reads.load(Ordering::SeqCst)
    }
}

/// Two multi-instance wrappers over one counted backend and one provider.
async fn fixture(max_file_size_bytes: usize) -> Fixture {
    let reads = Arc::new(AtomicU64::new(0));
    let inner = MemFileSystem::new();
    inner.mkdir("/docs", 0o755).await.unwrap();
    inner.mkdir("/docs/sub", 0o755).await.unwrap();
    inner
        .write("/docs/sub/a.bin", &[0, 1, 2, 255], 0, WriteFlag::Create)
        .await
        .unwrap();
    let backend: Arc<dyn FileSystem> = Arc::new(CountingFs {
        inner,
        reads: Arc::clone(&reads),
    });
    let runtime = CacheRuntime::memory_with_provider_and_default_ttl(
        Arc::new(MemoryMockProvider::new()),
        Some(Duration::from_secs(60)),
    );
    let instance = || {
        CachedFileSystem::with_runtime(
            Box::new(ArcFileSystem(Arc::clone(&backend))),
            Arc::clone(&runtime),
            SERVICE_NAME,
        )
        .with_multi_instance(true)
        .with_max_file_size_bytes(max_file_size_bytes)
    };
    Fixture {
        reads,
        a: instance(),
        b: instance(),
    }
}

#[tokio::test]
async fn full_reads_are_served_from_cache_and_ranged_reads_bypass_it() {
    let f = fixture(DEFAULT_MAX_FILE_SIZE_BYTES).await;

    assert_eq!(
        f.a.read("/docs/sub/a.bin", 0, 0).await.unwrap(),
        [0, 1, 2, 255]
    );
    assert_eq!(f.reads(), 1);
    // The other instance hits the entry the first one filled.
    assert_eq!(
        f.b.read("/docs/sub/a.bin", 0, 0).await.unwrap(),
        [0, 1, 2, 255]
    );
    assert_eq!(f.reads(), 1);
    assert_eq!(f.b.read("/docs/sub/a.bin", 1, 2).await.unwrap(), [1, 2]);
    assert_eq!(f.reads(), 2);

    let read = f.b.metrics().snapshot().operation(CacheOperation::Read);
    assert_eq!((read.hits, read.misses, read.bypasses), (1, 0, 1));
}

#[tokio::test]
async fn writes_on_one_instance_invalidate_cached_contents_on_the_other() {
    let f = fixture(DEFAULT_MAX_FILE_SIZE_BYTES).await;
    f.b.read("/docs/sub/a.bin", 0, 0).await.unwrap();

    f.a.write("/docs/sub/a.bin", b"v2", 0, WriteFlag::Create)
        .await
        .unwrap();
    assert_eq!(f.b.read("/docs/sub/a.bin", 0, 0).await.unwrap(), b"v2");

    f.a.truncate("/docs/sub/a.bin", 1).await.unwrap();
    assert_eq!(f.b.read("/docs/sub/a.bin", 0, 0).await.unwrap(), b"v");

    f.a.rename("/docs/sub", "/docs/moved").await.unwrap();
    assert!(f.b.read("/docs/sub/a.bin", 0, 0).await.is_err());
    assert_eq!(f.b.read("/docs/moved/a.bin", 0, 0).await.unwrap(), b"v");

    f.a.remove_all("/docs/moved").await.unwrap();
    assert!(f.b.read("/docs/moved/a.bin", 0, 0).await.is_err());
}

#[tokio::test]
async fn files_over_the_limit_and_a_zero_limit_are_not_cached() {
    let f = fixture(3).await;
    f.a.read("/docs/sub/a.bin", 0, 0).await.unwrap();
    f.a.read("/docs/sub/a.bin", 0, 0).await.unwrap();
    assert_eq!(f.reads(), 2, "a 4-byte file exceeds a 3-byte limit");

    let f = fixture(0).await;
    f.a.read("/docs/sub/a.bin", 0, 0).await.unwrap();
    f.a.read("/docs/sub/a.bin", 0, 0).await.unwrap();
    assert_eq!(f.reads(), 2);
    let read = f.a.metrics().snapshot().operation(CacheOperation::Read);
    assert_eq!((read.hits, read.misses, read.bypasses), (0, 0, 2));
}
