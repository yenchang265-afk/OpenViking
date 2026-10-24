//! End-to-end: Git history through the `agfs` backend on a tiered `/ovgit`
//! mount (s3fs + MySQL), asserting the bucket never receives an object
//! smaller than 1 MiB, and that legacy S3 Git data migrates with
//! `tiered_import_existing`.
//!
//! Ignored by default; needs an S3-compatible endpoint and MySQL/MariaDB:
//!
//! ```text
//! OV_S3_TEST_ENDPOINT=http://127.0.0.1:8333 \
//! OV_S3_TEST_ACCESS_KEY=... OV_S3_TEST_SECRET_KEY=... OV_S3_TEST_BUCKET=openviking \
//! OV_TIERED_TEST_DSN=mysql://openviking:openviking@127.0.0.1:3306/openviking \
//!   cargo test -p ragfs --features s3,tiered --test git_agfs_tiered_e2e -- --ignored
//! ```
//!
//! Each test uses a unique S3 prefix and table and removes both afterwards.

#![cfg(all(feature = "s3", feature = "tiered"))]

use std::collections::HashMap;
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use aws_sdk_s3::config::{BehaviorVersion, Credentials, Region};
use aws_sdk_s3::Client;
use ragfs::core::tiered::DEFAULT_SMALL_THRESHOLD_BYTES;
use ragfs::core::{ConfigValue, FileSystem, MountableFS, PluginConfig, WriteFlag};
use ragfs::git::{
    AgfsIndexStore, AgfsObjectStore, AgfsRefStore, CasMode, CommitRequest, CommitResponse,
    GitService, LogRequest, ObjectStore, RefStore, S3Config, S3ObjectStore, S3RefStore,
    ShowRequest, ShowResponse,
};
use ragfs::plugins::{MemFSPlugin, S3FSPlugin};
use sqlx::Executor;

const MIB: usize = 1024 * 1024;
const GIT_MOUNT: &str = "/ovgit";

struct Env {
    endpoint: String,
    access_key: String,
    secret_key: String,
    bucket: String,
    dsn: String,
    prefix: String,
    table: String,
    account: String,
}

impl Env {
    fn from_env() -> Option<Self> {
        let var = |name: &str| std::env::var(name).ok().filter(|v| !v.is_empty());
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let run = format!("{}_{}", std::process::id(), nanos % 1_000_000_000_000);
        Some(Self {
            endpoint: var("OV_S3_TEST_ENDPOINT")?,
            access_key: var("OV_S3_TEST_ACCESS_KEY")?,
            secret_key: var("OV_S3_TEST_SECRET_KEY")?,
            bucket: var("OV_S3_TEST_BUCKET").unwrap_or_else(|| "ragfs-it".to_string()),
            dsn: var("OV_TIERED_TEST_DSN")?,
            prefix: format!("_it/tiered-git/{run}"),
            table: format!("git_{run}"),
            account: format!("acct{}", nanos % 1_000_000),
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

    /// The legacy S3 Git backend's config, writing to this run's prefix.
    fn legacy_git_config(&self) -> S3Config {
        S3Config {
            bucket: self.bucket.clone(),
            prefix: self.prefix.clone(),
            region: "us-east-1".to_string(),
            endpoint: Some(self.endpoint.clone()),
            access_key_id: Some(self.access_key.clone()),
            secret_access_key: Some(self.secret_key.clone()),
            use_path_style: true,
            cas_mode: CasMode::Native,
            resilience: Default::default(),
        }
    }

    /// A `MountableFS` with a memfs working tree at `/local` and the tiered
    /// Git mount at `/ovgit`, mounted through the production `mount()` path.
    async fn vfs(&self, import_existing: bool) -> Arc<MountableFS> {
        self.try_vfs(import_existing)
            .await
            .expect("mount tiered /ovgit")
    }

    async fn try_vfs(&self, import_existing: bool) -> ragfs::core::Result<Arc<MountableFS>> {
        let fs = Arc::new(MountableFS::new());
        fs.register_plugin(MemFSPlugin).await;
        fs.register_plugin(S3FSPlugin::new()).await;
        fs.mount(PluginConfig::single_backend(
            "memfs",
            "/local",
            HashMap::new(),
        ))
        .await
        .expect("mount /local");
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
            ("tiered_enabled", ConfigValue::Bool(true)),
            (
                "tiered_dsn_env",
                ConfigValue::String("OV_TIERED_TEST_DSN".to_string()),
            ),
            ("tiered_table", ConfigValue::String(self.table.clone())),
            ("tiered_import_existing", ConfigValue::Bool(import_existing)),
        ]
        .into_iter()
        .map(|(k, v)| (k.to_string(), v))
        .collect();
        fs.mount(PluginConfig::single_backend("s3fs", GIT_MOUNT, params))
            .await?;
        Ok(fs)
    }

    fn agfs_service(&self, vfs: &Arc<MountableFS>) -> GitService {
        let vfs: Arc<dyn FileSystem> = vfs.clone();
        GitService::with_index(
            vfs.clone(),
            Arc::new(AgfsObjectStore::new(vfs.clone(), GIT_MOUNT)),
            Arc::new(AgfsRefStore::new(vfs.clone(), GIT_MOUNT)),
            Some(Arc::new(AgfsIndexStore::new(vfs, GIT_MOUNT))),
        )
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

    async fn assert_no_small_objects(&self) -> usize {
        let objects = self.objects().await;
        let small: Vec<_> = objects
            .iter()
            .filter(|(_, size)| (*size as u64) < DEFAULT_SMALL_THRESHOLD_BYTES)
            .collect();
        assert!(
            small.is_empty(),
            "objects below 1 MiB reached the bucket: {small:?}"
        );
        objects.len()
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

/// Incompressible bytes, so the zlib Git blob stays above the threshold.
fn noise(len: usize, seed: u64) -> Vec<u8> {
    // Odd and distinct per seed (xorshift must not start at 0).
    let mut state = seed.wrapping_mul(2).wrapping_add(1);
    (0..len)
        .map(|_| {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            state as u8
        })
        .collect()
}

async fn write_tree(vfs: &Arc<MountableFS>, account: &str, version: usize) {
    for i in 0..20 {
        let path = format!("/local/{account}/resources/kb/doc{i}.md");
        vfs.ensure_parent_dirs(&path, 0o755).await.unwrap();
        let body = format!("doc {i} version {}\n", if i < 3 { version } else { 0 });
        vfs.write(&path, body.as_bytes(), 0, WriteFlag::Create)
            .await
            .unwrap();
    }
    let big = format!("/local/{account}/resources/media/video.bin");
    vfs.ensure_parent_dirs(&big, 0o755).await.unwrap();
    vfs.write(
        &big,
        &noise(2 * MIB, version as u64 + 7),
        0,
        WriteFlag::Create,
    )
    .await
    .unwrap();
}

fn commit_req(account: &str, message: &str) -> CommitRequest {
    CommitRequest {
        account: account.to_string(),
        branch: "main".to_string(),
        message: message.to_string(),
        paths: None,
        author_name: "tester".to_string(),
        author_email: "tester@example.com".to_string(),
    }
}

async fn show_text(svc: &GitService, account: &str, target: &str, path: &str) -> String {
    let resp = svc
        .show(ShowRequest {
            account: account.to_string(),
            target_ref: target.to_string(),
            path: Some(path.to_string()),
        })
        .await
        .expect("show");
    match resp {
        ShowResponse::Blob { bytes, .. } => String::from_utf8(bytes.to_vec()).unwrap(),
        other => panic!("expected blob, got {other:?}"),
    }
}

/// Commit ids on `main`, newest first.
async fn log_oids(svc: &GitService, account: &str) -> Vec<String> {
    svc.log(LogRequest {
        account: account.to_string(),
        branch: "main".to_string(),
        limit: 100,
        paths: None,
    })
    .await
    .expect("log")
    .iter()
    .map(|entry| entry.oid.to_hex().to_string())
    .collect()
}

#[tokio::test]
#[ignore = "requires OV_S3_TEST_* and OV_TIERED_TEST_DSN"]
async fn git_history_on_tiered_mount_never_creates_small_objects() {
    let Some(env) = Env::from_env() else {
        eprintln!("skipping: OV_S3_TEST_* / OV_TIERED_TEST_DSN not set");
        return;
    };
    env.ensure_bucket().await;
    let vfs = env.vfs(false).await;
    let svc = env.agfs_service(&vfs);

    for version in 1..=5 {
        write_tree(&vfs, &env.account, version).await;
        let resp = svc
            .commit(commit_req(&env.account, &format!("v{version}")))
            .await
            .expect("commit");
        assert!(
            matches!(resp, CommitResponse::Created { .. }),
            "v{version}: {resp:?}"
        );
    }

    let oids = log_oids(&svc, &env.account).await;
    assert_eq!(oids.len(), 5);
    assert_eq!(
        show_text(&svc, &env.account, "main", "resources/kb/doc0.md").await,
        "doc 0 version 5\n"
    );
    // An abbreviated id is resolved by listing refs and walking parents.
    let oldest = &oids[4][..10];
    assert_eq!(
        show_text(&svc, &env.account, oldest, "resources/kb/doc0.md").await,
        "doc 0 version 1\n"
    );

    // Five distinct 2 MiB video blobs are the only objects large enough for S3.
    let count = env.assert_no_small_objects().await;
    assert_eq!(count, 5, "one S3 object per large git blob");
    env.cleanup().await;
}

#[tokio::test]
#[ignore = "requires OV_S3_TEST_* and OV_TIERED_TEST_DSN"]
async fn legacy_s3_git_history_migrates_with_import_existing() {
    let Some(env) = Env::from_env() else {
        eprintln!("skipping: OV_S3_TEST_* / OV_TIERED_TEST_DSN not set");
        return;
    };
    env.ensure_bucket().await;

    // 1. History written by the legacy S3 backend: one S3 object per git object.
    let legacy_tree = Arc::new(MountableFS::new());
    legacy_tree.register_plugin(MemFSPlugin).await;
    legacy_tree
        .mount(PluginConfig::single_backend(
            "memfs",
            "/local",
            HashMap::new(),
        ))
        .await
        .unwrap();
    let objects: Arc<dyn ObjectStore> = Arc::new(
        S3ObjectStore::from_config(env.legacy_git_config())
            .await
            .unwrap(),
    );
    let refs: Arc<dyn RefStore> = Arc::new(
        S3RefStore::from_config(env.legacy_git_config())
            .await
            .unwrap(),
    );
    let legacy = GitService::new(legacy_tree.clone(), objects, refs);
    for version in 1..=3 {
        write_tree(&legacy_tree, &env.account, version).await;
        legacy
            .commit(commit_req(&env.account, &format!("legacy v{version}")))
            .await
            .expect("legacy commit");
    }
    assert!(
        env.objects()
            .await
            .iter()
            .any(|(_, size)| (*size as u64) < 1024),
        "precondition: the legacy backend wrote small objects"
    );

    // 2. Without import, the tiered mount refuses to hide the legacy data.
    match env.try_vfs(false).await {
        Err(ragfs::core::Error::Config(message)) => {
            assert!(message.contains("tiered_import_existing"), "{message}")
        }
        Err(other) => panic!("expected a config error, got {other}"),
        Ok(_) => panic!("mount must refuse a bucket with untiered git data"),
    }

    // 3. Mount with import_existing and read the full history through agfs.
    let vfs = env.vfs(true).await;
    let svc = env.agfs_service(&vfs);
    let oids = log_oids(&svc, &env.account).await;
    assert_eq!(oids.len(), 3);
    assert_eq!(
        show_text(&svc, &env.account, &oids[2], "resources/kb/doc1.md").await,
        "doc 1 version 1\n"
    );

    // 4. New commits continue the migrated history.
    write_tree(&vfs, &env.account, 4).await;
    svc.commit(commit_req(&env.account, "v4 after migration"))
        .await
        .expect("commit after migration");
    assert_eq!(log_oids(&svc, &env.account).await.len(), 4);

    env.assert_no_small_objects().await;
    env.cleanup().await;
}
