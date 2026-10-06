//! S3FS path-based write/read integration tests (single PUT vs multipart).
//!
//! Ignored by default; they need a reachable S3-compatible endpoint. Run against the
//! local SeaweedFS sidecar (`docker compose --profile s3 up -d seaweedfs`) with:
//!
//! ```text
//! OV_S3_TEST_ENDPOINT=http://127.0.0.1:8333 \
//! OV_S3_TEST_ACCESS_KEY=... OV_S3_TEST_SECRET_KEY=... \
//! OV_S3_TEST_BUCKET=openviking \
//!   cargo test -p ragfs --features s3 --test s3_multipart_integration -- --ignored
//! ```
//!
//! Every run writes under a unique `_it/multipart/` prefix (outside the app's `prefix`)
//! and deletes its objects afterwards, so it never touches application data. Prefer an
//! existing bucket: the bucket is created if missing, but a SeaweedFS server with no free
//! volume slots rejects writes to a new bucket's collection with HTTP 500.

#![cfg(feature = "s3")]

use std::collections::HashMap;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use aws_sdk_s3::config::{BehaviorVersion, Credentials, Region};
use aws_sdk_s3::Client;
use ragfs::core::{ConfigValue, Error, FileSystem, PluginConfig, ServicePlugin, WriteFlag};
use ragfs::plugins::S3FSPlugin;

const MIB: u64 = 1024 * 1024;
const PART_SIZE: u64 = 5 * MIB;
const THRESHOLD: u64 = 6 * MIB;

struct TestEnv {
    endpoint: String,
    access_key: String,
    secret_key: String,
    bucket: String,
    prefix: String,
}

impl TestEnv {
    /// Read the endpoint settings, or `None` to skip when they are not configured.
    fn from_env() -> Option<Self> {
        let var = |name: &str| std::env::var(name).ok().filter(|v| !v.is_empty());
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        Some(Self {
            endpoint: var("OV_S3_TEST_ENDPOINT")?,
            access_key: var("OV_S3_TEST_ACCESS_KEY")?,
            secret_key: var("OV_S3_TEST_SECRET_KEY")?,
            bucket: var("OV_S3_TEST_BUCKET").unwrap_or_else(|| "ragfs-it".to_string()),
            prefix: format!("_it/multipart/{}-{nanos}", std::process::id()),
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

    async fn filesystem(&self, threshold: u64) -> Box<dyn FileSystem> {
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
                "multipart_threshold_bytes",
                ConfigValue::Int(threshold as i64),
            ),
            (
                "multipart_part_size_bytes",
                ConfigValue::Int(PART_SIZE as i64),
            ),
        ]
        .into_iter()
        .map(|(k, v)| (k.to_string(), v))
        .collect();
        let config = PluginConfig::single_backend("s3fs", "/s3", params);
        let plugin = S3FSPlugin::new();
        plugin.validate(&config).await.expect("valid s3fs config");
        plugin.initialize(config).await.expect("s3fs mounts")
    }

    async fn open_multipart_uploads(&self) -> usize {
        let resp = self
            .raw_client()
            .list_multipart_uploads()
            .bucket(&self.bucket)
            .prefix(&self.prefix)
            .send()
            .await
            .expect("list multipart uploads");
        resp.uploads().len()
    }

    /// Delete every object and pending multipart upload under this run's prefix.
    async fn cleanup(&self) {
        let client = self.raw_client();
        if let Ok(resp) = client
            .list_objects_v2()
            .bucket(&self.bucket)
            .prefix(&self.prefix)
            .send()
            .await
        {
            for object in resp.contents() {
                if let Some(key) = object.key() {
                    let _ = client
                        .delete_object()
                        .bucket(&self.bucket)
                        .key(key)
                        .send()
                        .await;
                }
            }
        }
        if let Ok(resp) = client
            .list_multipart_uploads()
            .bucket(&self.bucket)
            .prefix(&self.prefix)
            .send()
            .await
        {
            for upload in resp.uploads() {
                if let (Some(key), Some(id)) = (upload.key(), upload.upload_id()) {
                    let _ = client
                        .abort_multipart_upload()
                        .bucket(&self.bucket)
                        .key(key)
                        .upload_id(id)
                        .send()
                        .await;
                }
            }
        }
    }
}

fn patterned_file(dir: &Path, name: &str, len: u64) -> (std::path::PathBuf, Vec<u8>) {
    let data: Vec<u8> = (0..len).map(|i| (i % 251) as u8).collect();
    let path = dir.join(name);
    std::fs::write(&path, &data).unwrap();
    (path, data)
}

#[tokio::test]
#[ignore = "needs an S3-compatible endpoint; see module docs"]
async fn write_from_path_round_trips_across_single_put_and_multipart() {
    let Some(env) = TestEnv::from_env() else {
        eprintln!("skipping: OV_S3_TEST_* not set");
        return;
    };
    env.ensure_bucket().await;
    let fs = env.filesystem(THRESHOLD).await;
    let scratch = tempfile::tempdir().unwrap();

    let sizes = [
        ("empty", 0),
        ("one", 1),
        ("below_threshold", THRESHOLD - 1),
        ("at_threshold", THRESHOLD),
        ("above_threshold", THRESHOLD + 1),
        ("three_parts", 2 * PART_SIZE + 3),
    ];
    for (name, len) in sizes {
        let (src, data) = patterned_file(scratch.path(), name, len);
        let target = format!("/{name}.bin");

        let written = fs
            .write_from_path(&target, &src, WriteFlag::Create)
            .await
            .unwrap_or_else(|e| panic!("write {name}: {e}"));
        let dst = scratch.path().join(format!("{name}.out"));
        let read = fs.read_to_path(&target, &dst).await.unwrap();

        assert_eq!((written, read), (len, len), "{name}");
        assert!(std::fs::read(&dst).unwrap() == data, "{name} content");
        assert_eq!(fs.stat(&target).await.unwrap().size, len, "{name} stat");
    }

    assert_eq!(env.open_multipart_uploads().await, 0);
    env.cleanup().await;
}

#[tokio::test]
#[ignore = "needs an S3-compatible endpoint; see module docs"]
async fn multipart_create_new_rejects_existing_key() {
    let Some(env) = TestEnv::from_env() else {
        eprintln!("skipping: OV_S3_TEST_* not set");
        return;
    };
    env.ensure_bucket().await;
    let fs = env.filesystem(THRESHOLD).await;
    let scratch = tempfile::tempdir().unwrap();
    let (src, data) = patterned_file(scratch.path(), "big", THRESHOLD + 1);
    fs.write_from_path("/exists.bin", &src, WriteFlag::Create)
        .await
        .unwrap();

    let result = fs
        .write_from_path("/exists.bin", &src, WriteFlag::CreateNew)
        .await;

    assert!(matches!(result, Err(Error::AlreadyExists(_))), "{result:?}");
    assert!(fs.read("/exists.bin", 0, 0).await.unwrap() == data);
    env.cleanup().await;
}

#[tokio::test]
#[ignore = "needs an S3-compatible endpoint; see module docs"]
async fn failed_multipart_upload_is_aborted() {
    let Some(env) = TestEnv::from_env() else {
        eprintln!("skipping: OV_S3_TEST_* not set");
        return;
    };
    env.ensure_bucket().await;
    // A directory reports a non-zero size on Linux and opens fine, but reading it fails
    // with EISDIR after CreateMultipartUpload: a deterministic mid-upload failure.
    let fs = env.filesystem(1).await;
    let scratch = tempfile::tempdir().unwrap();
    let not_a_file = scratch.path().join("dir");
    std::fs::create_dir(&not_a_file).unwrap();
    if std::fs::metadata(&not_a_file).unwrap().len() <= 1 {
        eprintln!("skipping: directory size does not exceed the 1-byte threshold here");
        return;
    }

    let result = fs
        .write_from_path("/broken.bin", &not_a_file, WriteFlag::Create)
        .await;

    assert!(result.is_err());
    assert_eq!(env.open_multipart_uploads().await, 0);
    assert!(matches!(
        fs.stat("/broken.bin").await,
        Err(Error::NotFound(_))
    ));
    env.cleanup().await;
}
