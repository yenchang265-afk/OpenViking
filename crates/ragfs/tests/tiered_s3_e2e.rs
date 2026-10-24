//! End-to-end: s3fs + MySQL through `TieredFileSystem` at the production 1 MiB
//! threshold, asserting the bucket never receives an object smaller than 1 MiB.
//!
//! Ignored by default; needs both an S3-compatible endpoint and MySQL/MariaDB:
//!
//! ```text
//! OV_S3_TEST_ENDPOINT=http://127.0.0.1:8333 \
//! OV_S3_TEST_ACCESS_KEY=... OV_S3_TEST_SECRET_KEY=... OV_S3_TEST_BUCKET=openviking \
//! OV_TIERED_TEST_DSN=mysql://openviking:openviking@127.0.0.1:3306/openviking \
//!   cargo test -p ragfs --features s3,tiered --test tiered_s3_e2e -- --ignored
//! ```
//!
//! The run writes under a unique `_it/tiered/` prefix and a unique table, and
//! removes both afterwards.

#![cfg(all(feature = "s3", feature = "tiered"))]

use std::collections::HashMap;
use std::sync::Arc;

use aws_sdk_s3::config::{BehaviorVersion, Credentials, Region};
use aws_sdk_s3::Client;
use ragfs::core::tiered::mysql::MySqlTierStore;
use ragfs::core::tiered::{TieredFileSystem, DEFAULT_SMALL_THRESHOLD_BYTES};
use ragfs::core::{ConfigValue, FileSystem, PluginConfig, ServicePlugin, WriteFlag};
use ragfs::plugins::S3FSPlugin;
use sqlx::Executor;

const MIB: usize = 1024 * 1024;

struct Env {
    endpoint: String,
    access_key: String,
    secret_key: String,
    bucket: String,
    prefix: String,
    dsn: String,
    table: String,
}

impl Env {
    fn from_env() -> Option<Self> {
        let var = |name: &str| std::env::var(name).ok().filter(|v| !v.is_empty());
        let id = uuid::Uuid::new_v4().simple().to_string();
        let run = &id[..20];
        Some(Self {
            endpoint: var("OV_S3_TEST_ENDPOINT")?,
            access_key: var("OV_S3_TEST_ACCESS_KEY")?,
            secret_key: var("OV_S3_TEST_SECRET_KEY")?,
            bucket: var("OV_S3_TEST_BUCKET").unwrap_or_else(|| "ragfs-it".to_string()),
            dsn: var("OV_TIERED_TEST_DSN")?,
            prefix: format!("_it/tiered/{run}"),
            table: format!("e2e_{run}"),
        })
    }

    fn raw_client(&self) -> Client {
        let config = aws_sdk_s3::Config::builder()
            .behavior_version(BehaviorVersion::latest())
            .region(Region::new("us-east-1"))
            .force_path_style(true)
            .endpoint_url(&self.endpoint)
            .credentials_provider(Credentials::new(
                &self.access_key,
                &self.secret_key,
                None,
                None,
                "ragfs-it",
            ))
            .build();
        Client::from_conf(config)
    }

    async fn ensure_bucket(&self) {
        let client = self.raw_client();
        if client
            .head_bucket()
            .bucket(&self.bucket)
            .send()
            .await
            .is_err()
        {
            client
                .create_bucket()
                .bucket(&self.bucket)
                .send()
                .await
                .expect("create test bucket");
        }
    }

    async fn s3fs(&self) -> Arc<dyn FileSystem> {
        let params: HashMap<String, ConfigValue> = [
            ("bucket", ConfigValue::String(self.bucket.clone())),
            ("region", ConfigValue::String("us-east-1".to_string())),
            ("endpoint", ConfigValue::String(self.endpoint.clone())),
            (
                "access_key_id",
                ConfigValue::String(self.access_key.clone()),
            ),
            (
                "secret_access_key",
                ConfigValue::String(self.secret_key.clone()),
            ),
            ("use_path_style", ConfigValue::Bool(true)),
            ("prefix", ConfigValue::String(self.prefix.clone())),
            (
                "directory_marker_mode",
                ConfigValue::String("none".to_string()),
            ),
        ]
        .into_iter()
        .map(|(k, v)| (k.to_string(), v))
        .collect();
        let config = PluginConfig::single_backend("s3fs", "/local", params);
        let plugin = S3FSPlugin::new();
        plugin.validate(&config).await.expect("valid s3fs config");
        Arc::from(plugin.initialize(config).await.expect("s3fs mounts"))
    }

    /// `(key, size)` of every object under this run's prefix.
    async fn objects(&self) -> Vec<(String, i64)> {
        let client = self.raw_client();
        let mut out = Vec::new();
        let mut token = None;
        loop {
            let resp = client
                .list_objects_v2()
                .bucket(&self.bucket)
                .prefix(format!("{}/", self.prefix))
                .set_continuation_token(token)
                .send()
                .await
                .expect("list objects");
            for object in resp.contents() {
                out.push((
                    object.key().unwrap_or_default().to_string(),
                    object.size().unwrap_or_default(),
                ));
            }
            match resp.next_continuation_token() {
                Some(next) => token = Some(next.to_string()),
                None => return out,
            }
        }
    }

    async fn cleanup(&self) {
        let client = self.raw_client();
        for (key, _) in self.objects().await {
            let _ = client
                .delete_object()
                .bucket(&self.bucket)
                .key(key)
                .send()
                .await;
        }
        let pool = sqlx::MySqlPool::connect(&self.dsn).await.unwrap();
        pool.execute(format!("DROP TABLE IF EXISTS `{}`", self.table).as_str())
            .await
            .unwrap();
    }
}

fn sized(size: usize, fill: u8) -> Vec<u8> {
    vec![fill; size]
}

#[tokio::test]
#[ignore = "requires OV_S3_TEST_* and OV_TIERED_TEST_DSN"]
async fn bucket_never_receives_objects_below_one_mib() {
    let Some(env) = Env::from_env() else {
        eprintln!("skipping: OV_S3_TEST_* / OV_TIERED_TEST_DSN not set");
        return;
    };
    env.ensure_bucket().await;
    let store = Arc::new(
        MySqlTierStore::connect(&env.dsn, &env.table, 8)
            .await
            .unwrap(),
    );
    let fs = TieredFileSystem::new(store, env.s3fs().await, DEFAULT_SMALL_THRESHOLD_BYTES);

    // Typical knowledge-base content: many small files plus a few large ones.
    for i in 0..30 {
        let body = format!("term-{i}: definition\n").repeat(1 + i * 50);
        fs.write(
            &format!("/kb/glossary/t{i}.md"),
            body.as_bytes(),
            0,
            WriteFlag::Create,
        )
        .await
        .unwrap();
    }
    fs.write(
        "/kb/code/main.rs",
        &sized(3 * 1024, b'c'),
        0,
        WriteFlag::Create,
    )
    .await
    .unwrap();
    fs.write("/kb/.abstract.md", b"summary", 0, WriteFlag::Create)
        .await
        .unwrap();
    fs.mkdir("/kb/empty", 0o755).await.unwrap();
    fs.write(
        "/kb/exactly-1mib.bin",
        &sized(MIB, b'e'),
        0,
        WriteFlag::Create,
    )
    .await
    .unwrap();
    fs.write(
        "/kb/manual.pdf",
        &sized(2 * MIB, b'p'),
        0,
        WriteFlag::Create,
    )
    .await
    .unwrap();
    let dir = tempfile::tempdir().unwrap();
    let video = dir.path().join("video.mp4");
    std::fs::write(&video, sized(17 * MIB, b'v')).unwrap();
    fs.write_from_path("/kb/media/video.mp4", &video, WriteFlag::Create)
        .await
        .unwrap();

    // Structural changes and overwrites must not create small objects either.
    fs.rename("/kb/glossary", "/kb/terms").await.unwrap();
    fs.write("/kb/manual.pdf", b"now tiny", 0, WriteFlag::Truncate)
        .await
        .unwrap();
    fs.write("/kb/lock", b"v1", 0, WriteFlag::CreateNew)
        .await
        .unwrap();
    assert!(fs
        .compare_and_write("/kb/lock", b"v1", b"v2")
        .await
        .unwrap());

    let objects = env.objects().await;
    let small: Vec<_> = objects
        .iter()
        .filter(|(_, size)| (*size as u64) < DEFAULT_SMALL_THRESHOLD_BYTES)
        .collect();
    assert!(
        small.is_empty(),
        "objects below 1 MiB reached the bucket: {small:?}"
    );
    assert_eq!(
        objects.len(),
        2,
        "only exactly-1mib.bin and video.mp4 remain: {objects:?}"
    );

    // Everything still reads back through the tiered view.
    assert_eq!(fs.read("/kb/manual.pdf", 0, 0).await.unwrap(), b"now tiny");
    assert_eq!(
        fs.read("/kb/media/video.mp4", 0, 0).await.unwrap().len(),
        17 * MIB
    );
    assert_eq!(
        fs.read_dir("/kb/terms", None, None, None, None)
            .await
            .unwrap()
            .len(),
        30
    );
    assert!(fs.stat("/kb/empty").await.unwrap().is_dir);

    fs.remove_all("/").await.unwrap();
    assert!(
        env.objects().await.is_empty(),
        "remove_all released every blob"
    );
    env.cleanup().await;
}
