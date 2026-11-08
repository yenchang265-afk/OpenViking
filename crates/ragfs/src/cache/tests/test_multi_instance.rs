//! Several CacheFS instances sharing one cache namespace and one backend.

use super::*;
use crate::cache_runtime::{CacheRuntime, MemoryMockProvider};
use crate::core::mountable::ArcFileSystem;
use crate::core::{FileSystem, WriteFlag};
use crate::plugins::memfs::MemFileSystem;
use std::sync::Arc;
use std::time::Duration;

const SERVICE_NAME: &str = "multi-instance-test";
/// Long enough that background invalidation is still pending when the next read runs.
const UNLINK_DELAY: Duration = Duration::from_millis(300);

struct Cluster {
    provider: Arc<MemoryMockProvider>,
    a: CachedFileSystem,
    b: CachedFileSystem,
}

/// Two wrappers over one backend and one provider, like two pods on one Redis.
async fn cluster(multi_instance: bool) -> Cluster {
    let backend: Arc<dyn FileSystem> = Arc::new(MemFileSystem::new());
    backend.mkdir("/docs", 0o755).await.unwrap();
    backend.mkdir("/docs/sub", 0o755).await.unwrap();
    backend
        .write("/docs/sub/a.txt", b"v1", 0, WriteFlag::Create)
        .await
        .unwrap();
    let provider = Arc::new(MemoryMockProvider::new().with_unlink_delay(UNLINK_DELAY));
    let runtime = CacheRuntime::memory_with_provider_and_default_ttl(
        Arc::clone(&provider),
        Some(Duration::from_secs(60)),
    );
    let instance = || {
        CachedFileSystem::with_runtime(
            Box::new(ArcFileSystem(Arc::clone(&backend))),
            Arc::clone(&runtime),
            SERVICE_NAME,
        )
        .with_multi_instance(multi_instance)
    };
    Cluster {
        provider,
        a: instance(),
        b: instance(),
    }
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

/// Background invalidation lets another instance read a listing a write already changed.
#[tokio::test]
async fn single_instance_mode_can_serve_a_stale_listing_to_another_instance() {
    let c = cluster(false).await;
    assert_eq!(names(&c.b, "/docs/sub").await, ["a.txt"]);

    c.a.write("/docs/sub/b.txt", b"x", 0, WriteFlag::Create)
        .await
        .unwrap();

    // The write returned before its buckets were deleted.
    assert_eq!(names(&c.b, "/docs/sub").await, ["a.txt"]);
}

/// Multi-instance mode deletes the affected buckets before the write returns.
#[tokio::test]
async fn multi_instance_write_is_visible_on_the_other_instance_when_it_returns() {
    let c = cluster(true).await;
    assert_eq!(names(&c.b, "/docs/sub").await, ["a.txt"]);
    assert_eq!(c.b.stat("/docs/sub/a.txt").await.unwrap().size, 2);

    c.a.write("/docs/sub/a.txt", b"v2-longer", 0, WriteFlag::Create)
        .await
        .unwrap();
    c.a.write("/docs/sub/b.txt", b"x", 0, WriteFlag::Create)
        .await
        .unwrap();

    assert_eq!(names(&c.b, "/docs/sub").await, ["a.txt", "b.txt"]);
    assert_eq!(c.b.stat("/docs/sub/a.txt").await.unwrap().size, 9);
}

/// Recursive removal and rename reach descendant buckets cached by the other instance.
#[tokio::test]
async fn multi_instance_remove_all_and_rename_reach_cached_descendants() {
    let c = cluster(true).await;
    assert_eq!(names(&c.b, "/docs").await, ["sub"]);
    assert_eq!(names(&c.b, "/docs/sub").await, ["a.txt"]);
    c.b.stat("/docs/sub/a.txt").await.unwrap();

    c.a.rename("/docs/sub", "/docs/moved").await.unwrap();
    assert_eq!(names(&c.b, "/docs").await, ["moved"]);
    assert!(c.b.stat("/docs/sub/a.txt").await.is_err());
    assert_eq!(names(&c.b, "/docs/moved").await, ["a.txt"]);

    c.a.remove_all("/docs/moved").await.unwrap();
    assert!(c.b.stat("/docs/moved/a.txt").await.is_err());
    assert!(names(&c.b, "/docs").await.is_empty());
}

/// A delete that keeps failing still lets the write succeed, and is counted.
#[tokio::test]
async fn multi_instance_counts_invalidation_failures_without_failing_the_write() {
    let c = cluster(true).await;
    names(&c.b, "/docs/sub").await;

    c.provider.set_delete_failure(true);
    c.a.write("/docs/sub/b.txt", b"x", 0, WriteFlag::Create)
        .await
        .unwrap();

    let metrics = c.a.metrics().snapshot();
    assert!(metrics.invalidation_failures > 0, "{metrics:?}");
}
