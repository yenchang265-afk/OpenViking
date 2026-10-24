//! TieredFileSystem + MySqlTierStore integration tests.
//!
//! Ignored by default; they need a reachable MariaDB/MySQL. Run against the local
//! sidecar (`docker compose --profile tiered up -d mariadb`) with:
//!
//! ```text
//! OV_TIERED_TEST_DSN=mysql://openviking:openviking@127.0.0.1:3306/openviking \
//!   cargo test -p ragfs --features tiered --test tiered_mysql_integration -- --ignored
//! ```
//!
//! Every test creates its own uniquely named table and drops it afterwards, so it
//! never touches application data. Large files go to an in-memory blob backend.

#![cfg(feature = "tiered")]

use std::sync::Arc;
use std::time::Duration;

use ragfs::core::tiered::mysql::MySqlTierStore;
use ragfs::core::tiered::{Location, TierStore, TieredFileSystem};
use ragfs::core::{Error, FileSystem, WriteFlag};
use ragfs::plugins::MemFileSystem;
use sqlx::Executor;

const THRESHOLD: u64 = 64;

struct Harness {
    fs: Arc<TieredFileSystem>,
    store: Arc<MySqlTierStore>,
    dsn: String,
    table: String,
}

impl Harness {
    /// Connect a fresh table, or `None` to skip when no DSN is configured.
    async fn new() -> Option<Self> {
        let dsn = std::env::var("OV_TIERED_TEST_DSN")
            .ok()
            .filter(|v| !v.is_empty())?;
        let id = uuid::Uuid::new_v4().simple().to_string();
        let table = format!("it_{id}");
        let store = Arc::new(MySqlTierStore::connect(&dsn, &table, 8).await.unwrap());
        let blobs = Arc::new(MemFileSystem::new());
        let fs = Arc::new(TieredFileSystem::new(store.clone(), blobs, THRESHOLD));
        Some(Self {
            fs,
            store,
            dsn,
            table,
        })
    }

    async fn drop_table(&self) {
        let pool = sqlx::MySqlPool::connect(&self.dsn).await.unwrap();
        pool.execute(format!("DROP TABLE IF EXISTS `{}`", self.table).as_str())
            .await
            .unwrap();
    }
}

fn large() -> Vec<u8> {
    vec![b'L'; THRESHOLD as usize * 4]
}

macro_rules! harness {
    () => {
        match Harness::new().await {
            Some(h) => h,
            None => {
                eprintln!("skipping: OV_TIERED_TEST_DSN not set");
                return;
            }
        }
    };
}

#[tokio::test]
#[ignore = "requires OV_TIERED_TEST_DSN (MySQL or MariaDB)"]
async fn routes_by_size_and_round_trips_both_tiers() {
    let h = harness!();
    let fs = &h.fs;
    fs.write("/kb/glossary.md", b"term: meaning", 0, WriteFlag::Create)
        .await
        .unwrap();
    fs.write("/kb/manual.pdf", &large(), 0, WriteFlag::Create)
        .await
        .unwrap();

    let small = h.store.get("/kb/glossary.md").await.unwrap().unwrap();
    let big = h.store.get("/kb/manual.pdf").await.unwrap().unwrap();
    assert_eq!(small.location, Location::Inline);
    assert!(matches!(big.location, Location::Blob(_)));
    assert_eq!(fs.read("/kb/glossary.md", 6, 7).await.unwrap(), b"meaning");
    assert_eq!(fs.read("/kb/manual.pdf", 0, 0).await.unwrap(), large());

    let names: Vec<_> = fs
        .read_dir("/kb", None, None, None, None)
        .await
        .unwrap()
        .into_iter()
        .map(|info| info.name)
        .collect();
    assert_eq!(names, vec!["glossary.md", "manual.pdf"]);
    h.drop_table().await;
}

#[tokio::test]
#[ignore = "requires OV_TIERED_TEST_DSN (MySQL or MariaDB)"]
async fn directory_rename_and_subtree_delete_use_byte_ranges() {
    let h = harness!();
    let fs = &h.fs;
    fs.write("/proj/a.md", b"a", 0, WriteFlag::Create)
        .await
        .unwrap();
    fs.write("/proj/sub/b.bin", &large(), 0, WriteFlag::Create)
        .await
        .unwrap();
    fs.write("/proj-other/c.md", b"c", 0, WriteFlag::Create)
        .await
        .unwrap();
    fs.write("/projX/d.md", b"d", 0, WriteFlag::Create)
        .await
        .unwrap();

    fs.rename("/proj", "/archive/2026/proj").await.unwrap();
    assert_eq!(
        fs.read("/archive/2026/proj/sub/b.bin", 0, 0).await.unwrap(),
        large()
    );
    let moved = h
        .store
        .get("/archive/2026/proj/sub")
        .await
        .unwrap()
        .unwrap();
    assert!(moved.is_dir());
    assert_eq!(
        fs.read_dir("/archive/2026/proj/sub", None, None, None, None)
            .await
            .unwrap()
            .len(),
        1,
        "children follow the renamed parent"
    );
    assert!(matches!(fs.stat("/proj").await, Err(Error::NotFound(_))));

    fs.remove_all("/archive").await.unwrap();
    fs.stat("/proj-other/c.md")
        .await
        .expect("a sibling sharing the prefix survives");
    fs.stat("/projX/d.md")
        .await
        .expect("a sibling sharing the prefix survives");
    assert!(matches!(fs.stat("/archive").await, Err(Error::NotFound(_))));
    h.drop_table().await;
}

#[tokio::test]
#[ignore = "requires OV_TIERED_TEST_DSN (MySQL or MariaDB)"]
async fn conditional_ops_and_error_contract() {
    let h = harness!();
    let fs = &h.fs;
    fs.write("/lock", b"v1", 0, WriteFlag::CreateNew)
        .await
        .unwrap();
    assert!(matches!(
        fs.write("/lock", b"v1", 0, WriteFlag::CreateNew).await,
        Err(Error::AlreadyExists(_))
    ));
    assert!(!fs
        .compare_and_write("/lock", b"stale", b"v2")
        .await
        .unwrap());
    assert!(fs
        .compare_and_write("/lock", b"v1", &large())
        .await
        .unwrap());
    assert!(fs.compare_and_remove("/lock", &large()).await.unwrap());

    fs.write("/d/f", b"x", 0, WriteFlag::Create).await.unwrap();
    assert!(matches!(
        fs.remove("/d").await,
        Err(Error::DirectoryNotEmpty(_))
    ));
    assert!(matches!(
        fs.write("/d/f/g", b"x", 0, WriteFlag::Create).await,
        Err(Error::NotADirectory(_))
    ));
    fs.chmod("/d/f", 0o600).await.unwrap();
    fs.chmod("/d/f", 0o600).await.unwrap(); // unchanged value still succeeds
    assert_eq!(fs.stat("/d/f").await.unwrap().mode, 0o600);
    assert!(matches!(
        fs.chmod("/nope", 0o600).await,
        Err(Error::NotFound(_))
    ));
    h.drop_table().await;
}

#[tokio::test]
#[ignore = "requires OV_TIERED_TEST_DSN (MySQL or MariaDB)"]
async fn concurrent_create_new_has_exactly_one_winner() {
    let h = harness!();
    let tasks: Vec<_> = (0..8)
        .map(|i| {
            let fs = h.fs.clone();
            tokio::spawn(async move {
                fs.write(
                    "/race/once",
                    format!("w{i}").as_bytes(),
                    0,
                    WriteFlag::CreateNew,
                )
                .await
            })
        })
        .collect();
    let mut winners = 0;
    for task in tasks {
        match task.await.unwrap() {
            Ok(_) => winners += 1,
            Err(Error::AlreadyExists(_)) => {}
            Err(other) => panic!("unexpected error: {other}"),
        }
    }
    assert_eq!(winners, 1);
    h.drop_table().await;
}

#[tokio::test]
#[ignore = "requires OV_TIERED_TEST_DSN (MySQL or MariaDB)"]
async fn parallel_writers_sharing_new_ancestors_all_succeed() {
    let h = harness!();
    let tasks: Vec<_> = (0..16)
        .map(|i| {
            let fs = h.fs.clone();
            tokio::spawn(async move {
                let data = if i % 2 == 0 { b"s".to_vec() } else { large() };
                fs.write(
                    &format!("/deep/a/b/c/file-{i}"),
                    &data,
                    0,
                    WriteFlag::Create,
                )
                .await
            })
        })
        .collect();
    for task in tasks {
        task.await.unwrap().unwrap();
    }
    let entries =
        h.fs.read_dir("/deep/a/b/c", None, None, None, None)
            .await
            .unwrap();
    assert_eq!(entries.len(), 16);
    h.drop_table().await;
}

#[tokio::test]
#[ignore = "requires OV_TIERED_TEST_DSN (MySQL or MariaDB)"]
async fn orphan_gc_keeps_referenced_blobs() {
    let h = harness!();
    h.fs.write("/keep.bin", &large(), 0, WriteFlag::Create)
        .await
        .unwrap();
    h.fs.write("/keep.bin", &large(), 0, WriteFlag::Truncate)
        .await
        .unwrap();
    assert_eq!(h.fs.collect_orphan_blobs(Duration::ZERO).await.unwrap(), 0);
    assert_eq!(h.fs.read("/keep.bin", 0, 0).await.unwrap(), large());
    h.drop_table().await;
}
