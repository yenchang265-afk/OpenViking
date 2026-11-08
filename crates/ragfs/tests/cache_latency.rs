//! CacheFS query hit/miss and write latency against a real Redis.
//!
//! Ignored by default. Run with:
//! `REDIS_URL=redis://127.0.0.1:6379 cargo test --features cache --test cache_latency -- --ignored --nocapture`
//!
//! Set `REDIS_CLUSTER_URLS` (comma-separated seeds) to also measure Cluster mode.
//!
//! It uses only the public API so the same file can be run on an older
//! checkout to compare before/after numbers.

use ragfs::cache::CachedFileSystem;
use ragfs::cache_runtime::{CacheRuntime, RedisProviderConfig};
use ragfs::core::{FileInfo, FileSystem, ListSortBy, Result, SortOrder};
use ragfs::plugins::MemFileSystem;
use ragfs::WriteFlag;
use std::path::Path;
use std::sync::Arc;
use std::time::{Duration, Instant};

const SAMPLES: usize = 2_000;
const FILE_BYTES: usize = 4 * 1024;

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
    async fn write_from_path(&self, path: &str, src: &Path, flags: WriteFlag) -> Result<u64> {
        self.0.write_from_path(path, src, flags).await
    }
    async fn read_to_path(&self, path: &str, dst: &Path) -> Result<u64> {
        self.0.read_to_path(path, dst).await
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

fn percentile(samples: &mut [Duration], fraction: f64) -> Duration {
    samples.sort();
    let index = ((samples.len() as f64 - 1.0) * fraction).round() as usize;
    samples[index]
}

fn report(label: &str, mut samples: Vec<Duration>) {
    let p50 = percentile(&mut samples, 0.50);
    let p99 = percentile(&mut samples, 0.99);
    println!(
        "{label:<22} p50 {:>7.1} us   p99 {:>7.1} us",
        p50.as_secs_f64() * 1e6,
        p99.as_secs_f64() * 1e6
    );
}

async fn measure_depth(config: &RedisProviderConfig, depth: usize) {
    let backend: Arc<dyn FileSystem> = Arc::new(MemFileSystem::new());
    let mut dir = String::new();
    for level in 0..depth - 1 {
        dir.push_str(&format!("/l{level}"));
        backend.mkdir(&dir, 0o755).await.unwrap();
    }
    let path = format!("{dir}/f");
    let payload = vec![b'x'; FILE_BYTES];
    backend
        .write(&path, &payload, 0, WriteFlag::Create)
        .await
        .unwrap();

    let service = format!("ragfs-latency-{}-{depth}", std::process::id());
    let instance = |multi_instance: bool| {
        let (backend, config, service) = (Arc::clone(&backend), config.clone(), service.clone());
        async move {
            CachedFileSystem::with_runtime(
                Box::new(Shared(backend)),
                CacheRuntime::redis(config).await.unwrap(),
                service,
            )
            .with_multi_instance(multi_instance)
        }
    };
    let single = instance(false).await;
    let (writer, reader) = (instance(true).await, instance(true).await);

    reader.stat(&path).await.unwrap();
    let mut stat_hits = Vec::with_capacity(SAMPLES);
    for _ in 0..SAMPLES {
        let started = Instant::now();
        reader.stat(&path).await.unwrap();
        stat_hits.push(started.elapsed());
    }

    reader.read_dir(&dir, None, None, None, None).await.unwrap();
    let mut dir_hits = Vec::with_capacity(SAMPLES);
    for _ in 0..SAMPLES {
        let started = Instant::now();
        reader.read_dir(&dir, None, None, None, None).await.unwrap();
        dir_hits.push(started.elapsed());
    }

    reader.read(&path, 0, 0).await.unwrap();
    let mut read_hits = Vec::with_capacity(SAMPLES);
    for _ in 0..SAMPLES {
        let started = Instant::now();
        reader.read(&path, 0, 0).await.unwrap();
        read_hits.push(started.elapsed());
    }

    // Background invalidation: the write returns before buckets are deleted.
    let mut single_writes = Vec::with_capacity(SAMPLES / 4);
    for _ in 0..SAMPLES / 4 {
        let started = Instant::now();
        single
            .write(&path, &payload, 0, WriteFlag::None)
            .await
            .unwrap();
        single_writes.push(started.elapsed());
    }
    tokio::time::sleep(Duration::from_millis(200)).await;

    let mut multi_writes = Vec::with_capacity(SAMPLES / 4);
    let mut misses = Vec::with_capacity(SAMPLES / 4);
    for _ in 0..SAMPLES / 4 {
        reader.stat(&path).await.unwrap();
        // Awaited invalidation: the write returns after its buckets are gone,
        // so the reader's next stat is a real miss.
        let started = Instant::now();
        writer
            .write(&path, &payload, 0, WriteFlag::None)
            .await
            .unwrap();
        multi_writes.push(started.elapsed());
        let started = Instant::now();
        reader.stat(&path).await.unwrap();
        misses.push(started.elapsed());
    }

    report(&format!("depth {depth} stat hit"), stat_hits);
    report(&format!("depth {depth} read_dir hit"), dir_hits);
    report(&format!("depth {depth} read hit"), read_hits);
    report(&format!("depth {depth} stat miss+fill"), misses);
    report(&format!("depth {depth} write single"), single_writes);
    report(&format!("depth {depth} write multi"), multi_writes);
    assert!(
        writer.metrics().snapshot().invalidation_failures == 0,
        "invalidation must not fail against a healthy Redis"
    );
}

#[tokio::test]
#[ignore = "needs REDIS_URL or REDIS_CLUSTER_URLS; prints latency numbers"]
async fn cachefs_hit_and_miss_latency() {
    let base = RedisProviderConfig {
        command_timeout_ms: 1_000,
        default_ttl_seconds: 60,
        ..RedisProviderConfig::default()
    };
    let standalone = std::env::var("REDIS_URL").ok().map(|url| {
        (
            "standalone",
            RedisProviderConfig {
                endpoints: vec![url],
                ..base.clone()
            },
        )
    });
    // Comma-separated cluster seeds. Every CacheFS key shares the
    // `{service_name}` hash tag, so all of them live in one slot.
    let cluster = std::env::var("REDIS_CLUSTER_URLS").ok().map(|urls| {
        (
            "cluster",
            RedisProviderConfig {
                mode: "cluster".to_string(),
                endpoints: urls.split(',').map(|url| url.trim().to_string()).collect(),
                ..base.clone()
            },
        )
    });
    let configs = standalone.into_iter().chain(cluster).collect::<Vec<_>>();
    if configs.is_empty() {
        eprintln!("REDIS_URL / REDIS_CLUSTER_URLS not set; skipping");
        return;
    }
    for (mode, config) in configs {
        eprintln!("== {mode}");
        for depth in [3, 8] {
            measure_depth(&config, depth).await;
        }
    }
}
