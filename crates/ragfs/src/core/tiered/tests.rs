use std::collections::{HashMap, HashSet};
use std::sync::atomic::{AtomicU8, Ordering};
use std::sync::Arc;
use std::time::{Duration, SystemTime};

use async_trait::async_trait;

use super::*;
use crate::core::errors::{Error, Result};
use crate::core::filesystem::FileSystem;
use crate::core::types::{ConfigValue, FileInfo, WriteFlag};
use crate::plugins::memfs::MemFileSystem;

const THRESHOLD: u64 = 16;

fn small() -> Vec<u8> {
    b"tiny".to_vec()
}

fn large() -> Vec<u8> {
    vec![b'x'; THRESHOLD as usize * 2]
}

fn setup() -> (TieredFileSystem, Arc<MemoryTierStore>, Arc<MemFileSystem>) {
    let store = Arc::new(MemoryTierStore::new());
    let blobs = Arc::new(MemFileSystem::new());
    let fs = TieredFileSystem::new(store.clone(), blobs.clone(), THRESHOLD);
    (fs, store, blobs)
}

async fn blob_keys(blobs: &MemFileSystem) -> Vec<String> {
    let Ok(shards) = blobs.read_dir(BLOB_ROOT, None, None, None, None).await else {
        return Vec::new();
    };
    let mut keys = Vec::new();
    for shard in shards {
        let shard_path = format!("{}/{}", BLOB_ROOT, shard.name);
        for blob in blobs
            .read_dir(&shard_path, None, None, None, None)
            .await
            .unwrap()
        {
            keys.push(format!("{}/{}", shard_path, blob.name));
        }
    }
    keys
}

async fn location(store: &MemoryTierStore, path: &str) -> Location {
    store.get(path).await.unwrap().unwrap().location
}

#[tokio::test]
async fn small_file_stays_inline_and_never_reaches_blob_backend() {
    let (fs, store, blobs) = setup();
    fs.write("/docs/glossary.md", &small(), 0, WriteFlag::Create)
        .await
        .unwrap();

    assert_eq!(
        location(&store, "/docs/glossary.md").await,
        Location::Inline
    );
    assert!(blob_keys(&blobs).await.is_empty());
    assert_eq!(fs.read("/docs/glossary.md", 0, 0).await.unwrap(), small());
}

#[tokio::test]
async fn file_at_threshold_goes_to_blob_backend() {
    let (fs, store, blobs) = setup();
    let below = vec![b'a'; THRESHOLD as usize - 1];
    let at = vec![b'b'; THRESHOLD as usize];
    fs.write("/below", &below, 0, WriteFlag::Create)
        .await
        .unwrap();
    fs.write("/at", &at, 0, WriteFlag::Create).await.unwrap();

    assert_eq!(location(&store, "/below").await, Location::Inline);
    assert!(matches!(location(&store, "/at").await, Location::Blob(_)));
    assert_eq!(blob_keys(&blobs).await.len(), 1);
    assert_eq!(fs.read("/at", 0, 0).await.unwrap(), at);
}

#[tokio::test]
async fn overwrite_across_threshold_moves_bytes_and_releases_old_blob() {
    let (fs, store, blobs) = setup();
    fs.write("/f", &small(), 0, WriteFlag::Create)
        .await
        .unwrap();
    fs.write("/f", &large(), 0, WriteFlag::Truncate)
        .await
        .unwrap();
    assert!(matches!(location(&store, "/f").await, Location::Blob(_)));
    assert_eq!(blob_keys(&blobs).await.len(), 1);

    fs.write("/f", &large(), 0, WriteFlag::Truncate)
        .await
        .unwrap();
    assert_eq!(blob_keys(&blobs).await.len(), 1, "previous blob released");

    fs.write("/f", &small(), 0, WriteFlag::Truncate)
        .await
        .unwrap();
    assert_eq!(location(&store, "/f").await, Location::Inline);
    assert!(blob_keys(&blobs).await.is_empty());
    assert_eq!(fs.read("/f", 0, 0).await.unwrap(), small());
}

#[tokio::test]
async fn range_reads_work_in_both_tiers() {
    let (fs, _, _) = setup();
    fs.write("/s", b"0123456789", 0, WriteFlag::Create)
        .await
        .unwrap();
    let big: Vec<u8> = (0..40u8).collect();
    fs.write("/b", &big, 0, WriteFlag::Create).await.unwrap();

    assert_eq!(fs.read("/s", 2, 3).await.unwrap(), b"234");
    assert_eq!(fs.read("/s", 8, 0).await.unwrap(), b"89");
    assert_eq!(fs.read("/s", 50, 4).await.unwrap(), b"");
    assert_eq!(fs.read("/b", 30, 5).await.unwrap(), big[30..35].to_vec());
}

#[tokio::test]
async fn append_and_offset_writes_can_promote_to_blob() {
    let (fs, store, _) = setup();
    fs.write("/log", b"abc", 0, WriteFlag::Create)
        .await
        .unwrap();
    fs.write("/log", b"def", 0, WriteFlag::Append)
        .await
        .unwrap();
    assert_eq!(fs.read("/log", 0, 0).await.unwrap(), b"abcdef");

    fs.write("/log", b"XY", 1, WriteFlag::None).await.unwrap();
    assert_eq!(fs.read("/log", 0, 0).await.unwrap(), b"aXYdef");

    fs.write("/log", &large(), 0, WriteFlag::Append)
        .await
        .unwrap();
    assert!(matches!(location(&store, "/log").await, Location::Blob(_)));
    let content = fs.read("/log", 0, 0).await.unwrap();
    assert_eq!(&content[..6], b"aXYdef");
    assert_eq!(content.len(), 6 + large().len());
}

#[tokio::test]
async fn create_new_and_create_refuse_existing_files() {
    let (fs, _, _) = setup();
    fs.write("/f", &small(), 0, WriteFlag::CreateNew)
        .await
        .unwrap();
    assert!(matches!(
        fs.write("/f", &small(), 0, WriteFlag::CreateNew).await,
        Err(Error::AlreadyExists(_))
    ));
    assert!(matches!(
        fs.create("/f").await,
        Err(Error::AlreadyExists(_))
    ));
    fs.create("/empty").await.unwrap();
    assert_eq!(fs.stat("/empty").await.unwrap().size, 0);
}

#[tokio::test]
async fn writes_create_parent_directories_implicitly() {
    let (fs, _, _) = setup();
    fs.write("/a/b/c.md", &small(), 0, WriteFlag::Create)
        .await
        .unwrap();

    assert!(fs.stat("/a").await.unwrap().is_dir);
    let names: Vec<_> = fs
        .read_dir("/a/b", None, None, None, None)
        .await
        .unwrap()
        .into_iter()
        .map(|info| info.name)
        .collect();
    assert_eq!(names, vec!["c.md"]);
    assert!(fs.stat("/").await.unwrap().is_dir);
    assert_eq!(
        fs.read_dir("/", None, None, None, None)
            .await
            .unwrap()
            .len(),
        1
    );
}

#[tokio::test]
async fn directory_errors_match_filesystem_contract() {
    let (fs, _, _) = setup();
    fs.write("/dir/file", &small(), 0, WriteFlag::Create)
        .await
        .unwrap();

    assert!(matches!(
        fs.read("/dir", 0, 0).await,
        Err(Error::IsADirectory(_))
    ));
    assert!(matches!(
        fs.write("/dir", &small(), 0, WriteFlag::Create).await,
        Err(Error::IsADirectory(_))
    ));
    assert!(matches!(
        fs.read_dir("/dir/file", None, None, None, None).await,
        Err(Error::NotADirectory(_))
    ));
    assert!(matches!(
        fs.read_dir("/missing", None, None, None, None).await,
        Err(Error::NotFound(_))
    ));
    assert!(matches!(
        fs.write("/dir/file/child", &small(), 0, WriteFlag::Create)
            .await,
        Err(Error::NotADirectory(_))
    ));
    assert!(matches!(
        fs.mkdir("/dir", 0o755).await,
        Err(Error::AlreadyExists(_))
    ));
    assert!(matches!(fs.stat("/nope").await, Err(Error::NotFound(_))));
}

#[tokio::test]
async fn remove_releases_blob_and_guards_non_empty_dirs() {
    let (fs, _, blobs) = setup();
    fs.write("/d/big", &large(), 0, WriteFlag::Create)
        .await
        .unwrap();

    assert!(matches!(
        fs.remove("/d").await,
        Err(Error::DirectoryNotEmpty(_))
    ));
    assert!(matches!(
        fs.remove("/").await,
        Err(Error::InvalidOperation(_))
    ));
    fs.remove("/d/big").await.unwrap();
    assert!(blob_keys(&blobs).await.is_empty());
    fs.remove("/d").await.unwrap();
    assert!(matches!(fs.remove("/d").await, Err(Error::NotFound(_))));
}

#[tokio::test]
async fn remove_all_releases_every_blob_and_ignores_missing_paths() {
    let (fs, _, blobs) = setup();
    fs.write("/r/a", &large(), 0, WriteFlag::Create)
        .await
        .unwrap();
    fs.write("/r/sub/b", &large(), 0, WriteFlag::Create)
        .await
        .unwrap();
    fs.write("/r/sub/c", &small(), 0, WriteFlag::Create)
        .await
        .unwrap();
    fs.write("/rr", &large(), 0, WriteFlag::Create)
        .await
        .unwrap();

    fs.remove_all("/r").await.unwrap();
    assert!(matches!(fs.stat("/r").await, Err(Error::NotFound(_))));
    assert!(
        fs.stat("/rr").await.is_ok(),
        "sibling with shared prefix survives"
    );
    assert_eq!(blob_keys(&blobs).await.len(), 1);
    fs.remove_all("/never-existed").await.unwrap();

    fs.remove_all("/").await.unwrap();
    assert!(blob_keys(&blobs).await.is_empty());
}

#[tokio::test]
async fn rename_directory_moves_rows_without_copying_blobs() {
    let (fs, _, blobs) = setup();
    fs.write("/old/big", &large(), 0, WriteFlag::Create)
        .await
        .unwrap();
    fs.write("/old/sub/small", &small(), 0, WriteFlag::Create)
        .await
        .unwrap();
    let before = blob_keys(&blobs).await;

    fs.rename("/old", "/new/place").await.unwrap();

    assert_eq!(blob_keys(&blobs).await, before, "no blob copied or deleted");
    assert_eq!(fs.read("/new/place/big", 0, 0).await.unwrap(), large());
    assert_eq!(
        fs.read("/new/place/sub/small", 0, 0).await.unwrap(),
        small()
    );
    assert!(matches!(fs.stat("/old").await, Err(Error::NotFound(_))));
    assert!(matches!(
        fs.rename("/new", "/new/place/inner").await,
        Err(Error::InvalidOperation(_))
    ));
}

#[tokio::test]
async fn rename_file_over_existing_file_releases_its_blob() {
    let (fs, _, blobs) = setup();
    fs.write("/src", &small(), 0, WriteFlag::Create)
        .await
        .unwrap();
    fs.write("/dst", &large(), 0, WriteFlag::Create)
        .await
        .unwrap();

    fs.rename("/src", "/dst").await.unwrap();
    assert_eq!(fs.read("/dst", 0, 0).await.unwrap(), small());
    assert!(blob_keys(&blobs).await.is_empty());

    fs.mkdir("/dir", 0o755).await.unwrap();
    assert!(matches!(
        fs.rename("/dst", "/dir").await,
        Err(Error::AlreadyExists(_))
    ));
    assert!(matches!(
        fs.rename("/missing", "/x").await,
        Err(Error::NotFound(_))
    ));
}

#[tokio::test]
async fn replace_moves_files_and_rejects_directories() {
    let (fs, _, _) = setup();
    fs.write("/tmp/new", &large(), 0, WriteFlag::Create)
        .await
        .unwrap();
    fs.write("/final", &small(), 0, WriteFlag::Create)
        .await
        .unwrap();

    fs.replace("/tmp/new", "/final").await.unwrap();
    assert_eq!(fs.read("/final", 0, 0).await.unwrap(), large());
    assert!(matches!(fs.stat("/tmp/new").await, Err(Error::NotFound(_))));
    assert!(matches!(
        fs.replace("/tmp", "/other").await,
        Err(Error::InvalidOperation(_))
    ));
}

#[tokio::test]
async fn compare_and_write_checks_content_in_both_tiers() {
    let (fs, _, blobs) = setup();
    fs.write("/lock", b"v1", 0, WriteFlag::Create)
        .await
        .unwrap();

    assert!(!fs.compare_and_write("/lock", b"nope", b"v2").await.unwrap());
    assert!(fs.compare_and_write("/lock", b"v1", b"v2").await.unwrap());
    assert_eq!(fs.read("/lock", 0, 0).await.unwrap(), b"v2");

    // inline -> blob, then blob -> blob.
    assert!(fs
        .compare_and_write("/lock", b"v2", &large())
        .await
        .unwrap());
    let bigger = vec![b'y'; THRESHOLD as usize * 3];
    assert!(!fs.compare_and_write("/lock", b"v2", &bigger).await.unwrap());
    assert_eq!(blob_keys(&blobs).await.len(), 1, "losing CAS blob deleted");
    assert!(fs
        .compare_and_write("/lock", &large(), &bigger)
        .await
        .unwrap());
    assert_eq!(blob_keys(&blobs).await.len(), 1, "replaced blob released");

    assert!(!fs.compare_and_write("/absent", b"", b"x").await.unwrap());
}

#[tokio::test]
async fn compare_and_remove_only_removes_matching_content() {
    let (fs, _, blobs) = setup();
    fs.write("/s", b"keep", 0, WriteFlag::Create).await.unwrap();
    fs.write("/b", &large(), 0, WriteFlag::Create)
        .await
        .unwrap();

    assert!(!fs.compare_and_remove("/s", b"other").await.unwrap());
    assert!(fs.compare_and_remove("/s", b"keep").await.unwrap());
    assert!(fs.compare_and_remove("/b", &large()).await.unwrap());
    assert!(blob_keys(&blobs).await.is_empty());
    assert!(!fs.compare_and_remove("/s", b"keep").await.unwrap());
}

#[tokio::test]
async fn write_from_path_streams_large_files_and_inlines_small_ones() {
    let (fs, store, blobs) = setup();
    let dir = tempfile::tempdir().unwrap();
    let big_src = dir.path().join("big.bin");
    let small_src = dir.path().join("small.txt");
    std::fs::write(&big_src, large()).unwrap();
    std::fs::write(&small_src, small()).unwrap();

    let written = fs
        .write_from_path("/up/big.bin", &big_src, WriteFlag::Create)
        .await
        .unwrap();
    assert_eq!(written, large().len() as u64);
    fs.write_from_path("/up/small.txt", &small_src, WriteFlag::Create)
        .await
        .unwrap();

    assert!(matches!(
        location(&store, "/up/big.bin").await,
        Location::Blob(_)
    ));
    assert_eq!(location(&store, "/up/small.txt").await, Location::Inline);
    assert_eq!(blob_keys(&blobs).await.len(), 1);

    let dst = dir.path().join("out.bin");
    fs.read_to_path("/up/big.bin", &dst).await.unwrap();
    assert_eq!(std::fs::read(&dst).unwrap(), large());
    assert!(matches!(
        fs.write_from_path("/up/big.bin", &big_src, WriteFlag::CreateNew)
            .await,
        Err(Error::AlreadyExists(_))
    ));
}

#[tokio::test]
async fn chmod_persists_and_survives_overwrite() {
    let (fs, _, _) = setup();
    fs.write("/f", &small(), 0, WriteFlag::Create)
        .await
        .unwrap();
    fs.chmod("/f", 0o600).await.unwrap();
    fs.write("/f", &large(), 0, WriteFlag::Truncate)
        .await
        .unwrap();
    assert_eq!(fs.stat("/f").await.unwrap().mode, 0o600);
    assert!(matches!(
        fs.chmod("/nope", 0o600).await,
        Err(Error::NotFound(_))
    ));
}

#[tokio::test]
async fn overlong_paths_are_rejected_without_panicking_on_utf8() {
    let (fs, _, _) = setup();
    let long = format!("/{}", "術".repeat(MAX_PATH_BYTES));
    assert!(matches!(
        fs.write(&long, &small(), 0, WriteFlag::Create).await,
        Err(Error::InvalidPath(_))
    ));
}

const PUT_OK: u8 = 0;
/// `put_file` fails without proof of rollback (e.g. connection lost during commit).
const PUT_AMBIGUOUS: u8 = 1;
/// `put_file` fails with a definite conflict (the row was not written).
const PUT_CONFLICT: u8 = 2;

/// Store that can be told to fail `put_file`.
struct FailingStore {
    inner: MemoryTierStore,
    fail_put: AtomicU8,
}

#[async_trait]
impl TierStore for FailingStore {
    async fn get(&self, path: &str) -> Result<Option<TierEntry>> {
        self.inner.get(path).await
    }
    async fn read_inline(&self, path: &str) -> Result<Option<Vec<u8>>> {
        self.inner.read_inline(path).await
    }
    async fn put_file(
        &self,
        entry: TierEntry,
        inline: Option<&[u8]>,
        mode: PutMode,
    ) -> Result<Option<TierEntry>> {
        match self.fail_put.load(Ordering::SeqCst) {
            PUT_AMBIGUOUS => return Err(Error::internal("injected store failure")),
            PUT_CONFLICT => return Err(Error::already_exists(entry.path)),
            _ => {}
        }
        self.inner.put_file(entry, inline, mode).await
    }
    async fn create_dir(&self, path: &str, mode: u32, mod_time: SystemTime) -> Result<()> {
        self.inner.create_dir(path, mode, mod_time).await
    }
    async fn list_children(&self, dir: &str) -> Result<Vec<TierEntry>> {
        self.inner.list_children(dir).await
    }
    async fn remove_entry(&self, path: &str) -> Result<TierEntry> {
        self.inner.remove_entry(path).await
    }
    async fn remove_subtree(&self, path: &str) -> Result<Vec<TierEntry>> {
        self.inner.remove_subtree(path).await
    }
    async fn move_entry(
        &self,
        src: &str,
        dst: &str,
        mod_time: SystemTime,
    ) -> Result<Option<TierEntry>> {
        self.inner.move_entry(src, dst, mod_time).await
    }
    async fn compare_and_put(
        &self,
        expected: Expected<'_>,
        entry: TierEntry,
        inline: Option<&[u8]>,
    ) -> Result<Option<TierEntry>> {
        self.inner.compare_and_put(expected, entry, inline).await
    }
    async fn compare_and_remove(
        &self,
        path: &str,
        expected: Expected<'_>,
    ) -> Result<Option<TierEntry>> {
        self.inner.compare_and_remove(path, expected).await
    }
    async fn set_mode(&self, path: &str, mode: u32) -> Result<()> {
        self.inner.set_mode(path, mode).await
    }
    async fn blob_keys(&self) -> Result<HashSet<String>> {
        self.inner.blob_keys().await
    }
}

fn failing_setup() -> (TieredFileSystem, Arc<FailingStore>, Arc<MemFileSystem>) {
    let store = Arc::new(FailingStore {
        inner: MemoryTierStore::new(),
        fail_put: AtomicU8::new(PUT_OK),
    });
    let blobs = Arc::new(MemFileSystem::new());
    let fs = TieredFileSystem::new(store.clone(), blobs.clone(), THRESHOLD);
    (fs, store, blobs)
}

#[tokio::test]
async fn definite_publish_conflict_deletes_the_new_blob() {
    let (fs, store, blobs) = failing_setup();
    fs.write("/keep", &large(), 0, WriteFlag::Create)
        .await
        .unwrap();

    store.fail_put.store(PUT_CONFLICT, Ordering::SeqCst);
    assert!(matches!(
        fs.write("/keep", &large(), 0, WriteFlag::Truncate).await,
        Err(Error::AlreadyExists(_))
    ));

    assert_eq!(
        blob_keys(&blobs).await.len(),
        1,
        "only the published blob remains"
    );
    assert_eq!(fs.read("/keep", 0, 0).await.unwrap(), large());
}

#[tokio::test]
async fn ambiguous_publish_failure_leaves_the_blob_for_gc() {
    let (fs, store, blobs) = failing_setup();
    fs.write("/keep", &large(), 0, WriteFlag::Create)
        .await
        .unwrap();

    store.fail_put.store(PUT_AMBIGUOUS, Ordering::SeqCst);
    assert!(fs
        .write("/keep", &large(), 0, WriteFlag::Truncate)
        .await
        .is_err());

    // The commit may have landed, so the blob is kept; GC removes it once unreferenced.
    assert_eq!(blob_keys(&blobs).await.len(), 2);
    assert_eq!(fs.collect_orphan_blobs(Duration::ZERO).await.unwrap(), 0);
    assert_eq!(fs.collect_orphan_blobs(Duration::ZERO).await.unwrap(), 1);
    assert_eq!(fs.read("/keep", 0, 0).await.unwrap(), large());
}

#[tokio::test]
async fn paths_are_canonicalized_like_s3fs() {
    let (fs, _, _) = setup();
    fs.write("//a///b.md/", &small(), 0, WriteFlag::Create)
        .await
        .unwrap();

    assert_eq!(fs.read("/a/b.md", 0, 0).await.unwrap(), small());
    let names: Vec<_> = fs
        .read_dir("a", None, None, None, None)
        .await
        .unwrap()
        .into_iter()
        .map(|info| info.name)
        .collect();
    assert_eq!(names, vec!["b.md"], "no phantom empty-named directory");
    for bad in ["/a/./b", "/a/../b", "/.."] {
        assert!(
            matches!(fs.stat(bad).await, Err(Error::InvalidPath(_))),
            "{bad} should be rejected"
        );
    }
}

#[tokio::test]
async fn compare_on_a_blob_released_mid_race_is_a_mismatch() {
    let (fs, store, blobs) = setup();
    fs.write("/f", &large(), 0, WriteFlag::Create)
        .await
        .unwrap();
    let Location::Blob(key) = location(&store, "/f").await else {
        panic!("expected a blob");
    };
    // Simulate a concurrent overwrite that already released the blob.
    blobs.remove(&key).await.unwrap();

    assert!(!fs.compare_and_write("/f", &large(), b"new").await.unwrap());
    assert!(!fs.compare_and_remove("/f", &large()).await.unwrap());
}

#[tokio::test]
async fn orphan_gc_deletes_only_old_unreferenced_blobs() {
    let (fs, _, blobs) = setup();
    fs.write("/live", &large(), 0, WriteFlag::Create)
        .await
        .unwrap();
    // A blob whose row was never published, as after a crash mid-write.
    blobs
        .ensure_parent_dirs("/_blobs/zz/orphan", 0o755)
        .await
        .unwrap();
    blobs
        .write("/_blobs/zz/orphan", b"lost", 0, WriteFlag::Create)
        .await
        .unwrap();

    assert_eq!(
        fs.collect_orphan_blobs(Duration::from_secs(3600))
            .await
            .unwrap(),
        0
    );
    assert_eq!(fs.collect_orphan_blobs(Duration::ZERO).await.unwrap(), 0);
    assert_eq!(fs.collect_orphan_blobs(Duration::ZERO).await.unwrap(), 1);
    assert_eq!(blob_keys(&blobs).await.len(), 1);
    assert_eq!(fs.read("/live", 0, 0).await.unwrap(), large());
}

/// A blob backend holding data written before tiering was enabled.
async fn legacy_backend() -> (TieredFileSystem, Arc<MemoryTierStore>, Arc<MemFileSystem>) {
    let (fs, store, blobs) = setup();
    blobs.mkdir("/docs", 0o755).await.unwrap();
    blobs
        .write("/docs/a.md", &small(), 0, WriteFlag::Create)
        .await
        .unwrap();
    blobs
        .write("/docs/big.bin", &large(), 0, WriteFlag::Create)
        .await
        .unwrap();
    (fs, store, blobs)
}

#[tokio::test]
async fn excluded_root_names_belong_to_another_mount() {
    let (fs, _, blobs) = setup();
    // Legacy Git data under the bucket root, owned by the /ovgit mount.
    blobs
        .ensure_parent_dirs("/.ovgit/acct/objects/aa/bb", 0o755)
        .await
        .unwrap();
    blobs
        .write("/.ovgit/acct/objects/aa/bb", b"git", 0, WriteFlag::Create)
        .await
        .unwrap();
    assert!(
        fs.has_untiered_data().await.unwrap(),
        "unexcluded: guard trips"
    );

    let fs = fs.with_import_exclude(vec![".ovgit".to_string()]);
    assert!(!fs.has_untiered_data().await.unwrap());
    assert_eq!(fs.import_untiered().await.unwrap(), ImportStats::default());
    assert!(matches!(fs.stat("/.ovgit").await, Err(Error::NotFound(_))));
    assert!(
        blobs.stat("/.ovgit/acct/objects/aa/bb").await.is_ok(),
        "the other mount's objects are left untouched"
    );
}

#[test]
fn settings_parse_import_exclude_list() {
    let map = params(&[
        ("tiered_enabled", ConfigValue::Bool(true)),
        (
            "tiered_import_exclude",
            ConfigValue::StringList(vec![".ovgit".into()]),
        ),
    ]);
    let settings = TieredSettings::from_params(&map).unwrap().unwrap();
    assert_eq!(settings.import_exclude, vec![".ovgit"]);
}

#[tokio::test]
async fn untiered_data_is_detected_only_while_the_index_is_empty() {
    let (fresh, _, _) = setup();
    assert!(!fresh.has_untiered_data().await.unwrap());

    let (fs, _, _) = legacy_backend().await;
    assert!(fs.has_untiered_data().await.unwrap());
    fs.import_untiered().await.unwrap();
    assert!(!fs.has_untiered_data().await.unwrap());
}

#[tokio::test]
async fn import_inlines_small_files_and_moves_large_ones_into_blobs() {
    let (fs, store, blobs) = legacy_backend().await;

    let stats = fs.import_untiered().await.unwrap();

    assert_eq!(
        stats,
        ImportStats {
            directories: 1,
            inlined: 1,
            moved_to_blobs: 1,
            cleaned: 0,
            removed_directories: 1,
            conflicts: 0
        }
    );
    assert_eq!(location(&store, "/docs/a.md").await, Location::Inline);
    let Location::Blob(key) = location(&store, "/docs/big.bin").await else {
        panic!("expected a blob");
    };
    assert!(key.starts_with("/_blobs/"), "{key} is GC-managed");
    for legacy in ["/docs/a.md", "/docs/big.bin", "/docs"] {
        assert!(
            matches!(blobs.stat(legacy).await, Err(Error::NotFound(_))),
            "{legacy} should be gone from the backend"
        );
    }
    assert_eq!(fs.read("/docs/a.md", 0, 0).await.unwrap(), small());
    assert_eq!(fs.read("/docs/big.bin", 0, 0).await.unwrap(), large());
}

#[tokio::test]
async fn import_is_idempotent_and_survives_renames_of_imported_files() {
    let (fs, _, blobs) = legacy_backend().await;
    fs.import_untiered().await.unwrap();
    assert_eq!(fs.import_untiered().await.unwrap(), ImportStats::default());

    fs.rename("/docs/big.bin", "/archive/big.bin")
        .await
        .unwrap();
    assert_eq!(fs.import_untiered().await.unwrap(), ImportStats::default());
    assert!(matches!(
        fs.stat("/docs/big.bin").await,
        Err(Error::NotFound(_))
    ));

    // Overwriting the renamed file releases its blob.
    fs.write("/archive/big.bin", &small(), 0, WriteFlag::Truncate)
        .await
        .unwrap();
    assert!(blob_keys(&blobs).await.is_empty());
}

#[tokio::test]
async fn a_large_file_leaked_after_import_is_collected_and_never_resurrected() {
    let (fs, store, blobs) = legacy_backend().await;
    fs.import_untiered().await.unwrap();
    // Crash between deleting the row and releasing its blob.
    store.remove_entry("/docs/big.bin").await.unwrap();
    fs.write("/live", &small(), 0, WriteFlag::Create)
        .await
        .unwrap();

    assert_eq!(fs.import_untiered().await.unwrap(), ImportStats::default());
    assert!(
        matches!(fs.stat("/docs/big.bin").await, Err(Error::NotFound(_))),
        "a re-import must not bring the deleted file back"
    );
    assert_eq!(fs.collect_orphan_blobs(Duration::ZERO).await.unwrap(), 0);
    assert_eq!(fs.collect_orphan_blobs(Duration::ZERO).await.unwrap(), 1);
    assert!(blob_keys(&blobs).await.is_empty());
}

#[tokio::test]
async fn import_removes_backend_directories_it_emptied() {
    let (fs, _, blobs) = legacy_backend().await;
    blobs
        .ensure_parent_dirs("/notes/deep/x.md", 0o755)
        .await
        .unwrap();
    blobs
        .write("/notes/deep/x.md", &small(), 0, WriteFlag::Create)
        .await
        .unwrap();
    blobs.mkdir("/empty", 0o755).await.unwrap();

    let stats = fs.import_untiered().await.unwrap();

    // On S3 each of these is a 0-byte directory marker object.
    assert_eq!(stats.removed_directories, 4);
    for gone in ["/notes/deep", "/notes", "/empty", "/docs"] {
        assert!(
            matches!(blobs.stat(gone).await, Err(Error::NotFound(_))),
            "{gone} should be removed from the backend"
        );
        assert!(fs.stat(gone).await.unwrap().is_dir, "{gone} stays indexed");
    }
    assert_eq!(fs.import_untiered().await.unwrap(), ImportStats::default());
}

#[tokio::test]
async fn import_rerun_cleans_objects_left_by_a_crash_after_inlining() {
    let (fs, store, blobs) = legacy_backend().await;
    // Simulate a crash after the row was written but before the object was deleted.
    let entry = TierEntry {
        path: "/docs/a.md".to_string(),
        size: small().len() as u64,
        mode: 0o644,
        mod_time: SystemTime::now(),
        location: Location::Inline,
    };
    store
        .put_file(entry, Some(&small()), PutMode::CreateNew)
        .await
        .unwrap();

    let stats = fs.import_untiered().await.unwrap();

    assert_eq!(stats.cleaned, 1);
    assert!(matches!(
        blobs.stat("/docs/a.md").await,
        Err(Error::NotFound(_))
    ));
    assert_eq!(fs.read("/docs/a.md", 0, 0).await.unwrap(), small());
}

#[tokio::test]
async fn orphan_gc_is_a_no_op_before_any_blob_exists() {
    let (fs, _, _) = setup();
    assert_eq!(fs.collect_orphan_blobs(Duration::ZERO).await.unwrap(), 0);
}

/// Write an unreferenced blob, as a crash between upload and publish leaves.
async fn plant_orphan(blobs: &MemFileSystem) {
    blobs
        .ensure_parent_dirs("/_blobs/zz/orphan", 0o755)
        .await
        .unwrap();
    blobs
        .write("/_blobs/zz/orphan", b"lost", 0, WriteFlag::Create)
        .await
        .unwrap();
}

#[tokio::test]
async fn background_gc_deletes_orphans_and_keeps_live_blobs() {
    let (fs, _, blobs) = setup();
    fs.write("/live", &large(), 0, WriteFlag::Create)
        .await
        .unwrap();
    plant_orphan(&blobs).await;

    let _gc = fs.spawn_orphan_gc(Duration::from_millis(10), Duration::ZERO);
    for _ in 0..200 {
        if blob_keys(&blobs).await.len() == 1 {
            break;
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }

    assert_eq!(blob_keys(&blobs).await.len(), 1, "orphan collected");
    assert_eq!(fs.read("/live", 0, 0).await.unwrap(), large());
}

#[tokio::test]
async fn background_gc_stops_when_the_filesystem_is_dropped() {
    let (fs, store, blobs) = setup();
    let gc = fs.spawn_orphan_gc(Duration::from_millis(5), Duration::ZERO);
    drop((fs, store, blobs));

    tokio::time::timeout(Duration::from_secs(2), gc)
        .await
        .expect("GC task exits once its filesystem is gone")
        .unwrap();
}

#[tokio::test]
async fn concurrent_gc_runs_delete_each_orphan_once_without_errors() {
    let (fs, _, blobs) = setup();
    fs.write("/live", &small(), 0, WriteFlag::Create)
        .await
        .unwrap();
    plant_orphan(&blobs).await;
    assert_eq!(fs.collect_orphan_blobs(Duration::ZERO).await.unwrap(), 0);

    let (a, b) = tokio::join!(
        fs.collect_orphan_blobs(Duration::ZERO),
        fs.collect_orphan_blobs(Duration::ZERO)
    );

    assert_eq!(a.unwrap() + b.unwrap(), 1);
    assert!(blob_keys(&blobs).await.is_empty());
}

#[tokio::test]
async fn gc_spares_a_blob_published_between_two_runs() {
    let (fs, store, blobs) = setup();
    fs.write("/live", &small(), 0, WriteFlag::Create)
        .await
        .unwrap();
    // A multipart upload reports LastModified = upload start, so a blob can look
    // old the moment it appears, before its row is committed.
    plant_orphan(&blobs).await;
    assert_eq!(fs.collect_orphan_blobs(Duration::ZERO).await.unwrap(), 0);
    assert_eq!(blob_keys(&blobs).await.len(), 1, "first sighting only");

    let entry = TierEntry {
        path: "/big".to_string(),
        size: 4,
        mode: 0o644,
        mod_time: SystemTime::now(),
        location: Location::Blob("/_blobs/zz/orphan".to_string()),
    };
    store
        .put_file(entry, None, PutMode::CreateNew)
        .await
        .unwrap();

    assert_eq!(fs.collect_orphan_blobs(Duration::ZERO).await.unwrap(), 0);
    assert_eq!(fs.read("/big", 0, 0).await.unwrap(), b"lost");
}

#[tokio::test]
async fn gc_never_runs_against_an_empty_index() {
    // Wrong DSN/table or a lost database: every blob would look unreferenced.
    let (fs, _, blobs) = setup();
    plant_orphan(&blobs).await;

    for _ in 0..3 {
        assert_eq!(fs.collect_orphan_blobs(Duration::ZERO).await.unwrap(), 0);
    }
    assert_eq!(blob_keys(&blobs).await.len(), 1);
}

#[tokio::test]
async fn blobs_without_an_index_are_detected() {
    let (fresh, _, _) = setup();
    assert!(!fresh.has_blobs_without_index().await.unwrap());

    let (fs, _, blobs) = setup();
    plant_orphan(&blobs).await;
    assert!(fs.has_blobs_without_index().await.unwrap());
    assert!(
        !fs.has_untiered_data().await.unwrap(),
        "blobs are not legacy data"
    );

    fs.write("/live", &small(), 0, WriteFlag::Create)
        .await
        .unwrap();
    assert!(!fs.has_blobs_without_index().await.unwrap());
}

#[tokio::test]
async fn import_keeps_an_object_newer_than_its_row() {
    let (fs, _, blobs) = legacy_backend().await;
    fs.import_untiered().await.unwrap();
    // An untiered writer (e.g. an old replica mid-rollout) rewrites the path.
    tokio::time::sleep(Duration::from_millis(20)).await;
    blobs.ensure_parent_dirs("/docs/a.md", 0o755).await.unwrap();
    blobs
        .write("/docs/a.md", b"newer", 0, WriteFlag::Create)
        .await
        .unwrap();

    let stats = fs.import_untiered().await.unwrap();

    assert_eq!(stats.conflicts, 1);
    assert_eq!(stats.cleaned, 0);
    assert_eq!(
        blobs.read("/docs/a.md", 0, 0).await.unwrap(),
        b"newer",
        "the newer object is not deleted"
    );
}

/// A blob backend whose listings were taken before another replica imported.
struct StaleListingFs {
    inner: Arc<MemFileSystem>,
    listings: HashMap<String, Vec<FileInfo>>,
}

impl StaleListingFs {
    async fn snapshot(inner: Arc<MemFileSystem>, dirs: &[&str]) -> Self {
        let mut listings = HashMap::new();
        for dir in dirs {
            let entries = inner.read_dir(dir, None, None, None, None).await.unwrap();
            listings.insert(dir.to_string(), entries);
        }
        Self { inner, listings }
    }
}

#[async_trait]
impl FileSystem for StaleListingFs {
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
        sort_by: Option<crate::core::ListSortBy>,
        sort_order: Option<crate::core::SortOrder>,
    ) -> Result<Vec<FileInfo>> {
        match self.listings.get(path) {
            Some(entries) => Ok(entries.clone()),
            None => {
                self.inner
                    .read_dir(path, offset, limit, sort_by, sort_order)
                    .await
            }
        }
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

#[tokio::test]
async fn import_tolerates_another_replica_importing_the_same_bucket() {
    let (fs_a, store, blobs) = legacy_backend().await;
    blobs
        .write("/docs/gone.md", &small(), 0, WriteFlag::Create)
        .await
        .unwrap();
    let stale = StaleListingFs::snapshot(blobs.clone(), &["/", "/docs"]).await;
    let fs_b = TieredFileSystem::new(store.clone(), Arc::new(stale), THRESHOLD);

    // Replica A finishes first; B still works from listings taken before A ran.
    fs_a.import_untiered().await.unwrap();
    // Also an object that vanished after B listed it, with no row anywhere.
    store.remove_entry("/docs/gone.md").await.unwrap();

    fs_b.import_untiered()
        .await
        .expect("a concurrent import converges instead of failing the mount");
    assert_eq!(fs_b.read("/docs/a.md", 0, 0).await.unwrap(), small());
    assert_eq!(fs_b.read("/docs/big.bin", 0, 0).await.unwrap(), large());
}

#[test]
fn settings_gc_defaults_and_bounds() {
    let on = params(&[("tiered_enabled", ConfigValue::Bool(true))]);
    let settings = TieredSettings::from_params(&on).unwrap().unwrap();
    assert_eq!(settings.gc_interval, Some(Duration::from_secs(3600)));
    assert_eq!(settings.gc_min_age, Duration::from_secs(3600));

    let off = params(&[
        ("tiered_enabled", ConfigValue::Bool(true)),
        ("tiered_gc_interval_secs", ConfigValue::Int(0)),
    ]);
    assert_eq!(
        TieredSettings::from_params(&off)
            .unwrap()
            .unwrap()
            .gc_interval,
        None
    );

    for (key, value) in [
        ("tiered_gc_min_age_secs", 59),
        ("tiered_gc_interval_secs", 8 * 24 * 3600),
        ("tiered_gc_interval_secs", -1),
    ] {
        let map = params(&[
            ("tiered_enabled", ConfigValue::Bool(true)),
            (key, ConfigValue::Int(value)),
        ]);
        assert!(
            matches!(TieredSettings::from_params(&map), Err(Error::Config(_))),
            "{key}={value} should be rejected"
        );
    }
}

fn params(pairs: &[(&str, ConfigValue)]) -> HashMap<String, ConfigValue> {
    pairs
        .iter()
        .map(|(key, value)| (key.to_string(), value.clone()))
        .collect()
}

#[test]
fn settings_are_disabled_by_default() {
    assert_eq!(TieredSettings::from_params(&HashMap::new()).unwrap(), None);
    let off = params(&[("tiered_enabled", ConfigValue::Bool(false))]);
    assert_eq!(TieredSettings::from_params(&off).unwrap(), None);
}

#[test]
fn settings_apply_defaults_and_overrides() {
    let on = params(&[("tiered_enabled", ConfigValue::Bool(true))]);
    let settings = TieredSettings::from_params(&on).unwrap().unwrap();
    assert_eq!(
        settings.small_threshold_bytes,
        DEFAULT_SMALL_THRESHOLD_BYTES
    );
    assert_eq!(settings.dsn_env, DEFAULT_DSN_ENV);
    assert_eq!(settings.table, DEFAULT_TABLE);
    assert_eq!(settings.max_connections, 16);
    assert!(!settings.import_existing);
    assert_eq!(settings.backend, TieredBackend::Mysql);

    let custom = params(&[
        ("tiered_enabled", ConfigValue::Bool(true)),
        (
            "tiered_small_threshold_bytes",
            ConfigValue::Int(2 * 1024 * 1024),
        ),
        ("tiered_dsn_env", ConfigValue::String("MY_DSN".into())),
        (
            "tiered_table",
            ConfigValue::String("tenant_a_entries".into()),
        ),
        ("tiered_max_connections", ConfigValue::Int(4)),
        ("tiered_backend", ConfigValue::String("mysql".into())),
    ]);
    let settings = TieredSettings::from_params(&custom).unwrap().unwrap();
    assert_eq!(settings.backend, TieredBackend::Mysql);
    assert_eq!(settings.small_threshold_bytes, 2 * 1024 * 1024);
    assert_eq!(settings.dsn_env, "MY_DSN");
    assert_eq!(settings.table, "tenant_a_entries");
    assert_eq!(settings.max_connections, 4);
}

#[test]
fn settings_reject_invalid_values() {
    let cases = [
        ("tiered_enabled", ConfigValue::String("yes".into())),
        ("tiered_small_threshold_bytes", ConfigValue::Int(0)),
        (
            "tiered_small_threshold_bytes",
            ConfigValue::Int(64 * 1024 * 1024),
        ),
        ("tiered_max_connections", ConfigValue::Int(0)),
        (
            "tiered_table",
            ConfigValue::String("entries; DROP TABLE x".into()),
        ),
        (
            "tiered_table",
            ConfigValue::String("1starts_with_digit".into()),
        ),
        ("tiered_dsn_env", ConfigValue::String(String::new())),
        ("tiered_backend", ConfigValue::String("mariadb".into())),
        ("tiered_backend", ConfigValue::String("postgres".into())),
        ("tiered_backend", ConfigValue::Bool(true)),
        (
            "tiered_import_exclude",
            ConfigValue::String(".ovgit".into()),
        ),
        (
            "tiered_import_exclude",
            ConfigValue::StringList(vec!["a/b".into()]),
        ),
        (
            "tiered_import_exclude",
            ConfigValue::StringList(vec![String::new()]),
        ),
    ];
    for (key, value) in cases {
        let mut map = params(&[("tiered_enabled", ConfigValue::Bool(true))]);
        map.insert(key.to_string(), value.clone());
        assert!(
            matches!(TieredSettings::from_params(&map), Err(Error::Config(_))),
            "{key}={value:?} should be rejected"
        );
    }
}

fn tiered_mount_config(extra: &[(&str, ConfigValue)]) -> crate::core::PluginConfig {
    let mut params = params(&[("tiered_enabled", ConfigValue::Bool(true))]);
    for (key, value) in extra {
        params.insert(key.to_string(), value.clone());
    }
    crate::core::PluginConfig {
        name: "memfs".to_string(),
        mount_path: "/local".to_string(),
        params,
        ..Default::default()
    }
}

#[tokio::test]
async fn mount_rejects_invalid_tiered_settings() {
    let mfs = crate::core::MountableFS::new();
    mfs.register_plugin(crate::plugins::MemFSPlugin).await;
    let config = tiered_mount_config(&[("tiered_small_threshold_bytes", ConfigValue::Int(0))]);
    assert!(matches!(mfs.mount(config).await, Err(Error::Config(_))));
    assert!(mfs.list_mounts().await.is_empty());
}

#[tokio::test]
async fn mount_fails_loudly_when_dsn_env_is_unset() {
    let mfs = crate::core::MountableFS::new();
    mfs.register_plugin(crate::plugins::MemFSPlugin).await;
    let config = tiered_mount_config(&[(
        "tiered_dsn_env",
        ConfigValue::String("RAGFS_TIERED_DSN_UNSET_FOR_TEST".into()),
    )]);
    match mfs.mount(config).await {
        Err(Error::Config(message)) => assert!(
            message.contains("RAGFS_TIERED_DSN_UNSET_FOR_TEST")
                || message.contains("'tiered' feature"),
            "unexpected message: {message}"
        ),
        other => panic!("expected config error, got {other:?}"),
    }
    assert!(
        mfs.list_mounts().await.is_empty(),
        "no silent untiered fallback"
    );
}
