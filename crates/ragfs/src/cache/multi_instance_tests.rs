//! Cross-instance consistency tests for [`CachedFileSystem`].
//!
//! Several wrappers share one cache runtime and one backend, the way
//! OpenViking replicas share Redis and object storage. [`GatedFs`] pauses a
//! chosen backend call after it returns, so a test can interleave instances
//! deterministically.

use super::{CachePolicy, CachedFileSystem};
use crate::cache_runtime::{CacheRuntime, MemoryMockProvider};
use crate::core::{Error, FileInfo, FileSystem, ListSortBy, Result, SortOrder, WriteFlag};
use crate::plugins::memfs::MemFileSystem;
use async_trait::async_trait;
use std::collections::HashMap;
use std::path::Path;
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tokio::sync::oneshot;

const SERVICE: &str = "multi-instance-test";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
enum GateOp {
    Read,
    ReadDir,
    Write,
}

struct Gate {
    reached: oneshot::Sender<()>,
    release: oneshot::Receiver<()>,
}

type GateTable = Arc<Mutex<HashMap<(GateOp, String), Gate>>>;

/// Test handle for one paused backend call.
struct Armed {
    reached: oneshot::Receiver<()>,
    release: oneshot::Sender<()>,
}

impl Armed {
    /// Wait until the gated backend call has returned and is paused.
    async fn wait(&mut self) {
        (&mut self.reached)
            .await
            .expect("gated backend call never ran");
    }

    /// Let the paused call hand its result back to the cache wrapper.
    fn release(self) {
        let _ = self.release.send(());
    }
}

/// Backend wrapper that can pause one call per (operation, path) after the
/// inner call returns, before the cache wrapper sees the result.
struct GatedFs {
    inner: Arc<dyn FileSystem>,
    gates: GateTable,
}

impl GatedFs {
    async fn pause(&self, op: GateOp, path: &str) {
        let gate = self.gates.lock().unwrap().remove(&(op, path.to_string()));
        if let Some(gate) = gate {
            let _ = gate.reached.send(());
            let _ = gate.release.await;
        }
    }
}

#[async_trait]
impl FileSystem for GatedFs {
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
        let result = self.inner.read(path, offset, size).await;
        self.pause(GateOp::Read, path).await;
        result
    }

    async fn write(&self, path: &str, data: &[u8], offset: u64, flags: WriteFlag) -> Result<u64> {
        let result = self.inner.write(path, data, offset, flags).await;
        self.pause(GateOp::Write, path).await;
        result
    }

    async fn write_from_path(&self, path: &str, src: &Path, flags: WriteFlag) -> Result<u64> {
        self.inner.write_from_path(path, src, flags).await
    }

    async fn read_to_path(&self, path: &str, dst: &Path) -> Result<u64> {
        self.inner.read_to_path(path, dst).await
    }

    async fn read_dir(
        &self,
        path: &str,
        offset: Option<usize>,
        limit: Option<usize>,
        sort_by: Option<ListSortBy>,
        sort_order: Option<SortOrder>,
    ) -> Result<Vec<FileInfo>> {
        let result = self
            .inner
            .read_dir(path, offset, limit, sort_by, sort_order)
            .await;
        self.pause(GateOp::ReadDir, path).await;
        result
    }

    async fn stat(&self, path: &str) -> Result<FileInfo> {
        self.inner.stat(path).await
    }

    async fn rename(&self, old_path: &str, new_path: &str) -> Result<()> {
        self.inner.rename(old_path, new_path).await
    }

    async fn replace(&self, src_path: &str, dst_path: &str) -> Result<()> {
        self.inner.replace(src_path, dst_path).await
    }

    async fn chmod(&self, path: &str, mode: u32) -> Result<()> {
        self.inner.chmod(path, mode).await
    }
}

/// One simulated OpenViking replica.
struct Instance {
    fs: Arc<CachedFileSystem>,
    gates: GateTable,
}

impl Instance {
    /// Pause this instance's next backend `op` on `path` after it returns.
    fn arm(&self, op: GateOp, path: &str) -> Armed {
        let (reached_tx, reached_rx) = oneshot::channel();
        let (release_tx, release_rx) = oneshot::channel();
        self.gates.lock().unwrap().insert(
            (op, path.to_string()),
            Gate {
                reached: reached_tx,
                release: release_rx,
            },
        );
        Armed {
            reached: reached_rx,
            release: release_tx,
        }
    }

    async fn read_string(&self, path: &str) -> Result<String> {
        let data = self.fs.read(path, 0, 0).await?;
        Ok(String::from_utf8(data).expect("test content is UTF-8"))
    }

    async fn names(&self, path: &str) -> Vec<String> {
        let mut names = self
            .fs
            .read_dir(path, None, None, None, None)
            .await
            .unwrap()
            .into_iter()
            .map(|entry| entry.name)
            .collect::<Vec<_>>();
        names.sort();
        names
    }
}

/// Build one instance over a shared backend and the given runtime.
fn instance_on(
    backend: &Arc<dyn FileSystem>,
    runtime: Arc<CacheRuntime>,
    service: &str,
    policy: CachePolicy,
) -> Instance {
    let gates = GateTable::default();
    let gated = GatedFs {
        inner: Arc::clone(backend),
        gates: Arc::clone(&gates),
    };
    Instance {
        fs: Arc::new(CachedFileSystem::with_runtime(
            Box::new(gated),
            runtime,
            service,
            policy,
        )),
        gates,
    }
}

/// Shared backend and cache provider for several instances.
struct Cluster {
    backend: Arc<dyn FileSystem>,
    provider: Arc<MemoryMockProvider>,
    runtime: Arc<CacheRuntime>,
}

impl Cluster {
    fn new() -> Self {
        Self::with_provider(MemoryMockProvider::new())
    }

    fn with_provider(provider: MemoryMockProvider) -> Self {
        let provider = Arc::new(provider);
        Self {
            backend: Arc::new(MemFileSystem::new()),
            runtime: CacheRuntime::memory_with_provider(Arc::clone(&provider)),
            provider,
        }
    }

    fn instance(&self) -> Instance {
        self.instance_with(CachePolicy::default())
    }

    fn instance_with(&self, policy: CachePolicy) -> Instance {
        instance_on(&self.backend, Arc::clone(&self.runtime), SERVICE, policy)
    }

    async fn seed(&self, path: &str, content: &str) {
        self.backend
            .write(path, content.as_bytes(), 0, WriteFlag::Create)
            .await
            .unwrap();
    }

    async fn seed_dir(&self, path: &str) {
        self.backend.mkdir(path, 0o755).await.unwrap();
    }
}

/// Read one counter value stored as decimal text or as 8 big-endian bytes.
fn counter_value(raw: &[u8]) -> i128 {
    match std::str::from_utf8(raw)
        .ok()
        .and_then(|text| text.parse::<i64>().ok())
    {
        Some(value) => i128::from(value),
        None => {
            let bytes: [u8; 8] = raw.try_into().expect("counter is 8 bytes");
            i128::from(u64::from_be_bytes(bytes))
        }
    }
}

fn is_not_found<T>(result: &Result<T>) -> bool {
    matches!(result, Err(Error::NotFound(_)))
}

#[tokio::test]
async fn instances_share_hits_and_invalidations() {
    let cluster = Cluster::new();
    cluster.seed("/f", "v1").await;
    let (a, b) = (cluster.instance(), cluster.instance());

    assert_eq!(a.read_string("/f").await.unwrap(), "v1");
    assert_eq!(b.read_string("/f").await.unwrap(), "v1");
    assert_eq!(b.fs.metrics().snapshot().file_hits, 1);

    a.fs.write("/f", b"v2", 0, WriteFlag::Truncate)
        .await
        .unwrap();
    assert_eq!(b.read_string("/f").await.unwrap(), "v2");
}

/// R1: a fill that read the backend before another instance's write must not
/// survive that write.
#[tokio::test]
async fn late_fill_after_write_is_never_served() {
    let cluster = Cluster::new();
    cluster.seed("/f", "v1").await;
    let (a, b) = (cluster.instance(), cluster.instance());

    let mut gate = b.arm(GateOp::Read, "/f");
    let reader = {
        let fs = Arc::clone(&b.fs);
        tokio::spawn(async move { fs.read("/f", 0, 0).await })
    };
    gate.wait().await;
    a.fs.write("/f", b"v2", 0, WriteFlag::Truncate)
        .await
        .unwrap();
    gate.release();

    // The gated read overlapped the write, so it may return either value.
    reader.await.unwrap().unwrap();
    assert_eq!(b.read_string("/f").await.unwrap(), "v2");
    assert_eq!(a.read_string("/f").await.unwrap(), "v2");
}

/// R2: the generation snapshot must be taken before the backend read.
#[tokio::test]
async fn late_fill_after_remove_is_never_served() {
    let cluster = Cluster::new();
    cluster.seed_dir("/d").await;
    cluster.seed("/d/f", "v1").await;
    let (a, b) = (cluster.instance(), cluster.instance());

    let mut gate = b.arm(GateOp::Read, "/d/f");
    let reader = {
        let fs = Arc::clone(&b.fs);
        tokio::spawn(async move { fs.read("/d/f", 0, 0).await })
    };
    gate.wait().await;
    a.fs.remove("/d/f").await.unwrap();
    gate.release();

    reader.await.unwrap().unwrap();
    assert!(is_not_found(&b.fs.read("/d/f", 0, 0).await));
}

#[tokio::test]
async fn late_fill_after_ancestor_remove_all_is_never_served() {
    let cluster = Cluster::new();
    cluster.seed_dir("/d").await;
    cluster.seed_dir("/d/e").await;
    cluster.seed("/d/e/f", "v1").await;
    let (a, b) = (cluster.instance(), cluster.instance());

    let mut gate = b.arm(GateOp::Read, "/d/e/f");
    let reader = {
        let fs = Arc::clone(&b.fs);
        tokio::spawn(async move { fs.read("/d/e/f", 0, 0).await })
    };
    gate.wait().await;
    a.fs.remove_all("/d").await.unwrap();
    gate.release();

    reader.await.unwrap().unwrap();
    assert!(is_not_found(&b.fs.read("/d/e/f", 0, 0).await));
}

#[tokio::test]
async fn late_fill_after_rename_is_never_served() {
    let cluster = Cluster::new();
    cluster.seed_dir("/d").await;
    cluster.seed("/d/f", "v1").await;
    let (a, b) = (cluster.instance(), cluster.instance());

    let mut gate = b.arm(GateOp::Read, "/d/f");
    let reader = {
        let fs = Arc::clone(&b.fs);
        tokio::spawn(async move { fs.read("/d/f", 0, 0).await })
    };
    gate.wait().await;
    a.fs.rename("/d/f", "/d/g").await.unwrap();
    gate.release();

    reader.await.unwrap().unwrap();
    assert!(is_not_found(&b.fs.read("/d/f", 0, 0).await));
    assert_eq!(b.read_string("/d/g").await.unwrap(), "v1");
}

#[tokio::test]
async fn late_directory_fill_after_child_create_is_never_served() {
    let cluster = Cluster::new();
    cluster.seed_dir("/d").await;
    cluster.seed("/d/a", "a").await;
    let (a, b) = (cluster.instance(), cluster.instance());

    let mut gate = b.arm(GateOp::ReadDir, "/d");
    let reader = {
        let fs = Arc::clone(&b.fs);
        tokio::spawn(async move { fs.read_dir("/d", None, None, None, None).await })
    };
    gate.wait().await;
    a.fs.write("/d/x", b"x", 0, WriteFlag::Create)
        .await
        .unwrap();
    gate.release();

    reader.await.unwrap().unwrap();
    assert_eq!(b.names("/d").await, vec!["a", "x"]);
}

/// R4: two instances bumping one generation at the same time must both count.
/// The SET delay widened the old GET+SET race; INCRBY bumps must not lose
/// updates either way.
#[tokio::test]
async fn concurrent_generation_bumps_are_not_lost() {
    let cluster =
        Cluster::with_provider(MemoryMockProvider::new().with_set_delay(Duration::from_millis(20)));
    let (a, b) = (cluster.instance(), cluster.instance());
    a.fs.mkdir("/d", 0o755).await.unwrap();
    let key = a.fs.generation_key("/d");
    let before = counter_value(&cluster.runtime.get(&key).await.unwrap().unwrap());

    let (_, _) = tokio::join!(a.fs.remove_all("/d"), b.fs.remove_all("/d"));

    let after = counter_value(&cluster.runtime.get(&key).await.unwrap().unwrap());
    assert_eq!(after - before, 2, "one of two concurrent bumps was lost");
}

/// R5: instances that find the same generation key missing must agree on the
/// value that replaces it, or their entries invalidate each other.
#[tokio::test]
async fn instances_agree_on_reinitialized_generation() {
    let cluster =
        Cluster::with_provider(MemoryMockProvider::new().with_set_delay(Duration::from_millis(20)));
    cluster.seed_dir("/d").await;
    cluster.seed("/d/f", "f").await;
    cluster.seed("/d/g", "g").await;
    let (a, b, c) = (cluster.instance(), cluster.instance(), cluster.instance());

    let (f, g) = tokio::join!(a.fs.read("/d/f", 0, 0), b.fs.read("/d/g", 0, 0));
    f.unwrap();
    g.unwrap();

    c.fs.read("/d/f", 0, 0).await.unwrap();
    c.fs.read("/d/g", 0, 0).await.unwrap();
    let snapshot = c.fs.metrics().snapshot();
    assert_eq!(
        (snapshot.file_hits, snapshot.file_misses),
        (2, 0),
        "both entries must stay valid for a third instance"
    );
    assert!(cluster.provider.len().await > 0);
}

/// Gate instance B's backend `gate_op` on `target`, run `mutate` on instance A
/// while B is paused, then require B to agree with the backend.
async fn assert_late_fill_rejected<F, Fut>(label: &str, gate_op: GateOp, target: &str, mutate: F)
where
    F: FnOnce(Arc<CachedFileSystem>, Arc<dyn FileSystem>) -> Fut,
    Fut: std::future::Future<Output = ()>,
{
    let cluster = Cluster::new();
    cluster.seed_dir("/d").await;
    cluster.seed("/d/f", "v1").await;
    cluster.seed("/d/g", "g").await;
    let (a, b) = (cluster.instance(), cluster.instance());

    let mut gate = b.arm(gate_op, target);
    let reader = {
        let fs = Arc::clone(&b.fs);
        let target = target.to_string();
        tokio::spawn(async move {
            match gate_op {
                GateOp::ReadDir => fs
                    .read_dir(&target, None, None, None, None)
                    .await
                    .map(|_| ()),
                _ => fs.read(&target, 0, 0).await.map(|_| ()),
            }
        })
    };
    gate.wait().await;
    mutate(Arc::clone(&a.fs), Arc::clone(&cluster.backend)).await;
    gate.release();
    let _ = reader.await.unwrap();

    match gate_op {
        GateOp::ReadDir => {
            let mut expected = cluster
                .backend
                .read_dir(target, None, None, None, None)
                .await
                .unwrap()
                .into_iter()
                .map(|entry| entry.name)
                .collect::<Vec<_>>();
            expected.sort();
            assert_eq!(b.names(target).await, expected, "{label}");
        }
        _ => {
            let expected = cluster.backend.read(target, 0, 0).await.ok();
            assert_eq!(b.fs.read(target, 0, 0).await.ok(), expected, "{label}");
        }
    }
}

#[tokio::test]
async fn every_file_mutation_rejects_late_fills() {
    assert_late_fill_rejected("truncate", GateOp::Read, "/d/f", |a, _| async move {
        a.truncate("/d/f", 0).await.unwrap();
    })
    .await;
    assert_late_fill_rejected("replace", GateOp::Read, "/d/f", |a, _| async move {
        a.replace("/d/g", "/d/f").await.unwrap();
    })
    .await;
    assert_late_fill_rejected("write_from_path", GateOp::Read, "/d/f", |a, _| async move {
        let dir = tempfile::tempdir().unwrap();
        let src = dir.path().join("src");
        std::fs::write(&src, b"streamed").unwrap();
        a.write_from_path("/d/f", &src, WriteFlag::Truncate)
            .await
            .unwrap();
    })
    .await;
    assert_late_fill_rejected(
        "invalidate_external_write",
        GateOp::Read,
        "/d/f",
        |a, backend| async move {
            backend
                .write("/d/f", b"raw", 0, WriteFlag::Truncate)
                .await
                .unwrap();
            a.invalidate_external_write("/d/f").await;
        },
    )
    .await;
}

#[tokio::test]
async fn every_directory_mutation_rejects_late_listing_fills() {
    assert_late_fill_rejected("mkdir", GateOp::ReadDir, "/d", |a, _| async move {
        a.mkdir("/d/sub", 0o755).await.unwrap();
    })
    .await;
    assert_late_fill_rejected("remove", GateOp::ReadDir, "/d", |a, _| async move {
        a.remove("/d/f").await.unwrap();
    })
    .await;
    assert_late_fill_rejected("rename", GateOp::ReadDir, "/d", |a, _| async move {
        a.rename("/d/f", "/d/h").await.unwrap();
    })
    .await;
    assert_late_fill_rejected(
        "ensure_parent_dirs",
        GateOp::ReadDir,
        "/d",
        |a, _| async move {
            a.ensure_parent_dirs("/d/new/x", 0o755).await.unwrap();
        },
    )
    .await;
}

/// A bump that keeps failing must not fail the write; this instance stops
/// trusting the cache for the path and the failure is counted.
#[tokio::test]
async fn failed_bump_degrades_without_failing_the_write() {
    let cluster = Cluster::new();
    cluster.seed("/f", "v1").await;
    let a = cluster.instance();
    assert_eq!(a.read_string("/f").await.unwrap(), "v1");

    cluster.provider.set_unavailable(true);
    a.fs.write("/f", b"v2", 0, WriteFlag::Truncate)
        .await
        .unwrap();
    cluster.provider.set_unavailable(false);

    let snapshot = a.fs.metrics().snapshot();
    assert!(snapshot.invalidation_failures >= 1);
    assert_eq!(a.read_string("/f").await.unwrap(), "v2");
    assert!(a.fs.metrics().snapshot().policy_bypasses >= 1);
}

/// R3: write-through fill is unsafe across writers. A's backend write lands
/// first, B's second, but A's fill lands last.
#[tokio::test]
async fn multi_instance_mode_never_serves_a_superseded_write() {
    let cluster = Cluster::new();
    cluster.seed("/f", "v0").await;
    let policy = || CachePolicy::default().with_multi_instance(true);
    let (a, b) = (
        cluster.instance_with(policy()),
        cluster.instance_with(policy()),
    );

    let mut gate = a.arm(GateOp::Write, "/f");
    let writer = {
        let fs = Arc::clone(&a.fs);
        tokio::spawn(async move { fs.write("/f", b"v1", 0, WriteFlag::Truncate).await })
    };
    gate.wait().await;
    b.fs.write("/f", b"v2", 0, WriteFlag::Truncate)
        .await
        .unwrap();
    gate.release();
    writer.await.unwrap().unwrap();

    assert_eq!(a.read_string("/f").await.unwrap(), "v2");
    assert_eq!(b.read_string("/f").await.unwrap(), "v2");
}

#[tokio::test]
async fn single_instance_mode_keeps_write_through_fill() {
    let cluster = Cluster::new();
    let a = cluster.instance();
    a.fs.write("/f", b"v1", 0, WriteFlag::Create).await.unwrap();
    assert_eq!(a.read_string("/f").await.unwrap(), "v1");
    let snapshot = a.fs.metrics().snapshot();
    assert_eq!((snapshot.file_hits, snapshot.file_misses), (1, 0));
}

#[tokio::test]
async fn external_write_that_created_parents_invalidates_every_ancestor_listing() {
    let cluster = Cluster::new();
    cluster.seed_dir("/a").await;
    let (a, b) = (cluster.instance(), cluster.instance());
    assert!(b.names("/").await == vec!["a"]);
    assert!(b.names("/a").await.is_empty());

    // A raw writer (bypassing the wrapper) creates /a/b/c/f with its parents.
    cluster
        .backend
        .ensure_parent_dirs("/a/b/c/f", 0o755)
        .await
        .unwrap();
    cluster.seed("/a/b/c/f", "f").await;
    a.fs.invalidate_external_write("/a/b/c/f").await;

    assert_eq!(b.names("/a").await, vec!["b"]);
    assert_eq!(b.names("/a/b").await, vec!["c"]);
}

/// Atomic bump retries must not hold the operation lock: other operations in
/// the same process keep running while a write waits out the backoff.
#[tokio::test]
async fn bump_retries_do_not_block_other_operations() {
    let cluster = Cluster::new();
    cluster.seed("/f", "v1").await;
    cluster.seed("/g", "g").await;
    let a = Arc::new(cluster.instance());

    cluster.provider.set_unavailable(true);
    let writer = {
        let a = Arc::clone(&a);
        tokio::spawn(async move {
            let started = std::time::Instant::now();
            a.fs.write("/f", b"v2", 0, WriteFlag::Truncate)
                .await
                .unwrap();
            started.elapsed()
        })
    };
    tokio::time::sleep(Duration::from_millis(30)).await;
    let started = std::time::Instant::now();
    assert_eq!(a.read_string("/g").await.unwrap(), "g");
    let read_elapsed = started.elapsed();
    let write_elapsed = writer.await.unwrap();
    cluster.provider.set_unavailable(false);

    assert!(
        write_elapsed >= Duration::from_millis(250),
        "{write_elapsed:?}"
    );
    assert!(
        read_elapsed < Duration::from_millis(150),
        "read waited for the writer's retries: {read_elapsed:?}"
    );
}

/// Real-Redis variants: every instance opens its own connection, like separate
/// OpenViking processes. Set `REDIS_URL` (standalone), `REDIS_CLUSTER_URLS`
/// (comma-separated cluster seeds), and/or `REDIS_SENTINEL_TEST_URLS` plus
/// `REDIS_SENTINEL_TEST_MASTER` to run them.
mod redis;
