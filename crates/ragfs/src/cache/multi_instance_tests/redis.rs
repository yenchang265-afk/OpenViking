//! Real-Redis variants: every instance opens its own connection, like separate
//! OpenViking processes. Set `REDIS_URL` (standalone) and/or
//! `REDIS_CLUSTER_URLS` (comma-separated cluster seeds) to run them.

use super::*;
use crate::cache_runtime::RedisProviderConfig;

fn configs() -> Vec<RedisProviderConfig> {
    let base = RedisProviderConfig {
        connect_timeout_ms: 30_000,
        command_timeout_ms: 1_000,
        default_ttl_seconds: 60,
        ..RedisProviderConfig::default()
    };
    let standalone = std::env::var("REDIS_URL")
        .ok()
        .map(|url| RedisProviderConfig {
            endpoints: vec![url],
            ..base.clone()
        });
    let cluster = std::env::var("REDIS_CLUSTER_URLS")
        .ok()
        .map(|urls| RedisProviderConfig {
            mode: "cluster".to_string(),
            endpoints: urls.split(',').map(|url| url.trim().to_string()).collect(),
            ..base.clone()
        });
    standalone.into_iter().chain(cluster).collect()
}

/// Unique namespace per test and run, so reruns never see old keys.
fn service(test: &str) -> String {
    format!(
        "ragfs-multi-instance-{test}-{}",
        uuid::Uuid::new_v4().simple()
    )
}

struct RedisCluster {
    backend: Arc<dyn FileSystem>,
    config: RedisProviderConfig,
    service: String,
}

impl RedisCluster {
    fn new(config: RedisProviderConfig, test: &str) -> Self {
        Self {
            backend: Arc::new(MemFileSystem::new()),
            config,
            service: service(test),
        }
    }

    async fn instance(&self) -> Instance {
        let runtime = CacheRuntime::redis(self.config.clone()).await.unwrap();
        instance_on(
            &self.backend,
            runtime,
            &self.service,
            CachePolicy::default().with_multi_instance(true),
        )
    }

    async fn seed(&self, path: &str, content: &str) {
        self.backend
            .write(path, content.as_bytes(), 0, WriteFlag::Create)
            .await
            .unwrap();
    }
}

#[tokio::test]
async fn redis_late_fill_after_write_is_never_served() {
    for config in configs() {
        let cluster = RedisCluster::new(config, "write");
        cluster.seed("/f", "v1").await;
        let (a, b) = (cluster.instance().await, cluster.instance().await);
        assert_eq!(b.read_string("/f").await.unwrap(), "v1");
        assert_eq!(b.read_string("/f").await.unwrap(), "v1");
        assert_eq!(b.fs.metrics().snapshot().file_hits, 1, "shared hit");

        a.fs.write("/f", b"v1b", 0, WriteFlag::Truncate)
            .await
            .unwrap();
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
        reader.await.unwrap().unwrap();

        assert_eq!(b.read_string("/f").await.unwrap(), "v2");
        assert_eq!(a.read_string("/f").await.unwrap(), "v2");
    }
}

#[tokio::test]
async fn redis_late_fill_after_ancestor_remove_all_is_never_served() {
    for config in configs() {
        let cluster = RedisCluster::new(config, "remove-all");
        cluster.backend.mkdir("/d", 0o755).await.unwrap();
        cluster.seed("/d/f", "v1").await;
        let (a, b) = (cluster.instance().await, cluster.instance().await);

        let mut gate = b.arm(GateOp::Read, "/d/f");
        let reader = {
            let fs = Arc::clone(&b.fs);
            tokio::spawn(async move { fs.read("/d/f", 0, 0).await })
        };
        gate.wait().await;
        a.fs.remove_all("/d").await.unwrap();
        gate.release();
        reader.await.unwrap().unwrap();

        assert!(is_not_found(&b.fs.read("/d/f", 0, 0).await));
    }
}

#[tokio::test]
async fn redis_late_listing_fill_after_child_create_is_never_served() {
    for config in configs() {
        let cluster = RedisCluster::new(config, "listing");
        cluster.backend.mkdir("/d", 0o755).await.unwrap();
        cluster.seed("/d/a", "a").await;
        let (a, b) = (cluster.instance().await, cluster.instance().await);

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
}

#[tokio::test]
async fn redis_concurrent_bumps_from_two_connections_both_count() {
    for config in configs() {
        let cluster = RedisCluster::new(config, "bumps");
        let (a, b) = (cluster.instance().await, cluster.instance().await);
        a.fs.mkdir("/d", 0o755).await.unwrap();
        let key = a.fs.generation_key("/d");
        let runtime = a.fs.runtime();
        let raw = runtime.get(&key).await.unwrap().unwrap();
        let before: i64 = std::str::from_utf8(&raw).unwrap().parse().unwrap();

        let bumps = (0..16).map(|index| {
            let fs = if index % 2 == 0 { &a.fs } else { &b.fs };
            fs.remove_all("/d")
        });
        futures::future::join_all(bumps).await;

        let raw = runtime.get(&key).await.unwrap().unwrap();
        let after: i64 = std::str::from_utf8(&raw).unwrap().parse().unwrap();
        assert_eq!(after - before, 16, "counters are decimal INCRBY values");
    }
}
