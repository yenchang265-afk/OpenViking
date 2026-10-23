//! AGFS backend for Git object, ref and commit-index storage.
//!
//! Stores Git data through a RAGFS [`FileSystem`] (normally a size-tiered mount
//! reached via `MountableFS`), so small objects land in the tier store instead
//! of becoming individual S3 objects. The layout under `root` mirrors the S3
//! backend exactly, which lets an existing S3 Git prefix be migrated in place
//! with the tiered mount's `import_existing`:
//!
//! - objects: `{root}/{account}/objects/{aa}/{bb..}`
//! - refs:    `{root}/{account}/{ref_name}` (content `"{hex}\n"`)
//! - index:   `{root}/{account}/index/{branch}.json`

use std::sync::Arc;

use async_trait::async_trait;
use bytes::Bytes;
use gix_hash::ObjectId;

use crate::core::errors::Error;
use crate::core::filesystem::FileSystem;
use crate::core::types::WriteFlag;
use crate::git::error::{ObjectStoreError, RefStoreError};
use crate::git::index_store::{
    decode_index, encode_index, systemtime_to_ns, CommitIndex, IndexStore, IndexStoreError,
};
use crate::git::object_store::ObjectStore;
use crate::git::ref_store::RefStore;
use crate::git::util::validate_ref_name;

/// Shared path layout for the three AGFS Git stores.
#[derive(Clone)]
struct Layout {
    fs: Arc<dyn FileSystem>,
    root: String,
}

impl Layout {
    fn new(fs: Arc<dyn FileSystem>, root: &str) -> Self {
        Self {
            fs,
            root: root.trim_end_matches('/').to_string(),
        }
    }

    fn account_dir(&self, account: &str) -> String {
        format!("{}/{}", self.root, account)
    }

    fn object_path(&self, account: &str, oid: &ObjectId) -> String {
        let hex = oid.to_hex().to_string();
        format!(
            "{}/objects/{}/{}",
            self.account_dir(account),
            &hex[..2],
            &hex[2..]
        )
    }

    fn ref_path(&self, account: &str, ref_name: &str) -> String {
        format!("{}/{}", self.account_dir(account), ref_name)
    }

    fn index_path(&self, account: &str, branch: &str) -> String {
        format!("{}/index/{}.json", self.account_dir(account), branch)
    }

    /// Write `data`, creating parent directories on filesystems that need them.
    /// Tiered mounts create parents implicitly, so this costs nothing there.
    async fn write(&self, path: &str, data: &[u8], flags: WriteFlag) -> Result<(), Error> {
        match self.fs.write(path, data, 0, flags).await {
            Err(Error::NotFound(_)) => {
                self.fs.ensure_parent_dirs(path, 0o755).await?;
                self.fs.write(path, data, 0, flags).await.map(|_| ())
            }
            other => other.map(|_| ()),
        }
    }
}

fn backend_error(error: Error) -> String {
    format!("agfs: {}", error)
}

/// [`ObjectStore`] over a RAGFS filesystem.
pub struct AgfsObjectStore {
    layout: Layout,
}

impl AgfsObjectStore {
    /// Store objects under `root` (e.g. `/ovgit`) of `fs`.
    pub fn new(fs: Arc<dyn FileSystem>, root: &str) -> Self {
        Self {
            layout: Layout::new(fs, root),
        }
    }
}

#[async_trait]
impl ObjectStore for AgfsObjectStore {
    async fn put(
        &self,
        account: &str,
        oid: &ObjectId,
        zlib_body: Bytes,
    ) -> Result<(), ObjectStoreError> {
        let path = self.layout.object_path(account, oid);
        // Objects are content-addressed: an existing object already holds these bytes.
        match self
            .layout
            .write(&path, &zlib_body, WriteFlag::CreateNew)
            .await
        {
            Ok(()) | Err(Error::AlreadyExists(_)) => Ok(()),
            Err(error) => Err(ObjectStoreError::Backend(backend_error(error))),
        }
    }

    async fn get(&self, account: &str, oid: &ObjectId) -> Result<Bytes, ObjectStoreError> {
        let path = self.layout.object_path(account, oid);
        match self.layout.fs.read(&path, 0, 0).await {
            Ok(bytes) => Ok(Bytes::from(bytes)),
            Err(Error::NotFound(_)) => Err(ObjectStoreError::NotFound(*oid)),
            Err(error) => Err(ObjectStoreError::Backend(backend_error(error))),
        }
    }

    async fn get_limited(
        &self,
        account: &str,
        oid: &ObjectId,
        max_bytes: u64,
    ) -> Result<Bytes, ObjectStoreError> {
        let path = self.layout.object_path(account, oid);
        let size = match self.layout.fs.stat(&path).await {
            Ok(info) => info.size,
            Err(Error::NotFound(_)) => return Err(ObjectStoreError::NotFound(*oid)),
            Err(error) => return Err(ObjectStoreError::Backend(backend_error(error))),
        };
        if size > max_bytes {
            return Err(ObjectStoreError::ReadLimitExceeded {
                size,
                limit: max_bytes,
            });
        }
        let bytes = self.get(account, oid).await?;
        let size = bytes.len() as u64;
        if size > max_bytes {
            return Err(ObjectStoreError::ReadLimitExceeded {
                size,
                limit: max_bytes,
            });
        }
        Ok(bytes)
    }

    async fn exists(&self, account: &str, oid: &ObjectId) -> Result<bool, ObjectStoreError> {
        let path = self.layout.object_path(account, oid);
        match self.layout.fs.stat(&path).await {
            Ok(_) => Ok(true),
            Err(Error::NotFound(_)) => Ok(false),
            Err(error) => Err(ObjectStoreError::Backend(backend_error(error))),
        }
    }
}

/// [`RefStore`] over a RAGFS filesystem.
///
/// `cas_update` uses the filesystem's `compare_and_write`, which a tiered mount
/// executes as one database transaction, so concurrent writers in different
/// processes are serialized without an extra lock service.
pub struct AgfsRefStore {
    layout: Layout,
}

impl AgfsRefStore {
    /// Store refs under `root` (e.g. `/ovgit`) of `fs`.
    pub fn new(fs: Arc<dyn FileSystem>, root: &str) -> Self {
        Self {
            layout: Layout::new(fs, root),
        }
    }

    /// Current raw ref bytes and their parsed oid, or `None` when absent.
    async fn read_raw(&self, path: &str) -> Result<Option<(Vec<u8>, ObjectId)>, RefStoreError> {
        let bytes = match self.layout.fs.read(path, 0, 0).await {
            Ok(bytes) => bytes,
            Err(Error::NotFound(_)) => return Ok(None),
            Err(error) => return Err(RefStoreError::Backend(backend_error(error))),
        };
        let oid = parse_ref(&bytes)?;
        Ok(Some((bytes, oid)))
    }

    /// Value after a lost race, for the `Conflict` error.
    async fn current(&self, path: &str) -> Result<Option<ObjectId>, RefStoreError> {
        Ok(self.read_raw(path).await?.map(|(_, oid)| oid))
    }
}

fn parse_ref(bytes: &[u8]) -> Result<ObjectId, RefStoreError> {
    let text = std::str::from_utf8(bytes)
        .map_err(|_| RefStoreError::Backend("non-UTF-8 ref content".to_string()))?;
    let trimmed = text.trim();
    trimmed
        .parse::<ObjectId>()
        .map_err(|_| RefStoreError::Backend(format!("invalid oid in ref: {trimmed}")))
}

#[async_trait]
impl RefStore for AgfsRefStore {
    async fn read(&self, account: &str, ref_name: &str) -> Result<ObjectId, RefStoreError> {
        validate_ref_name(ref_name)?;
        let path = self.layout.ref_path(account, ref_name);
        self.read_raw(&path)
            .await?
            .map(|(_, oid)| oid)
            .ok_or_else(|| RefStoreError::NotFound(ref_name.to_string()))
    }

    async fn cas_update(
        &self,
        account: &str,
        ref_name: &str,
        expected: Option<ObjectId>,
        new: ObjectId,
    ) -> Result<(), RefStoreError> {
        validate_ref_name(ref_name)?;
        let path = self.layout.ref_path(account, ref_name);
        let body = format!("{}\n", new.to_hex());
        let applied = match expected {
            None => match self
                .layout
                .write(&path, body.as_bytes(), WriteFlag::CreateNew)
                .await
            {
                Ok(()) => true,
                Err(Error::AlreadyExists(_)) => false,
                Err(error) => return Err(RefStoreError::Backend(backend_error(error))),
            },
            Some(want) => match self.read_raw(&path).await? {
                // Compare against the exact stored bytes, whatever their formatting.
                Some((raw, oid)) if oid == want => self
                    .layout
                    .fs
                    .compare_and_write(&path, &raw, body.as_bytes())
                    .await
                    .map_err(|error| RefStoreError::Backend(backend_error(error)))?,
                _ => false,
            },
        };
        if applied {
            return Ok(());
        }
        Err(RefStoreError::Conflict {
            expected,
            actual: self.current(&path).await?,
        })
    }

    async fn list(
        &self,
        account: &str,
        prefix: &str,
    ) -> Result<Vec<(String, ObjectId)>, RefStoreError> {
        let account_dir = self.layout.account_dir(account);
        let start = format!("{}/{}", account_dir, prefix.trim_end_matches('/'));
        let mut result = Vec::new();
        let mut pending = vec![start];
        while let Some(dir) = pending.pop() {
            let entries = match self.layout.fs.read_dir(&dir, None, None, None, None).await {
                Ok(entries) => entries,
                Err(Error::NotFound(_)) | Err(Error::NotADirectory(_)) => continue,
                Err(error) => return Err(RefStoreError::Backend(backend_error(error))),
            };
            for entry in entries {
                let path = format!("{}/{}", dir, entry.name);
                if entry.is_dir {
                    pending.push(path);
                    continue;
                }
                let Some(ref_name) = path.strip_prefix(&format!("{}/", account_dir)) else {
                    continue;
                };
                // Unparsable files are skipped, as in the local backend.
                if let Ok(Some((_, oid))) = self.read_raw(&path).await {
                    result.push((ref_name.to_string(), oid));
                }
            }
        }
        Ok(result)
    }
}

/// [`IndexStore`] over a RAGFS filesystem.
///
/// Like the other backends, every decode problem degrades to `Ok(None)` on
/// `load`; the index is a soft-state cache validated by `parent_oid`.
pub struct AgfsIndexStore {
    layout: Layout,
}

impl AgfsIndexStore {
    /// Store commit indexes under `root` (e.g. `/ovgit`) of `fs`.
    pub fn new(fs: Arc<dyn FileSystem>, root: &str) -> Self {
        Self {
            layout: Layout::new(fs, root),
        }
    }
}

#[async_trait]
impl IndexStore for AgfsIndexStore {
    async fn load(
        &self,
        account: &str,
        branch: &str,
    ) -> Result<Option<CommitIndex>, IndexStoreError> {
        validate_ref_name(branch)
            .map_err(|_| IndexStoreError::InvalidBranch(branch.to_string()))?;
        let path = self.layout.index_path(account, branch);
        let bytes = match self.layout.fs.read(&path, 0, 0).await {
            Ok(bytes) => bytes,
            Err(Error::NotFound(_)) => return Ok(None),
            Err(error) => return Err(IndexStoreError::Backend(backend_error(error))),
        };
        let Ok(Some(mut index)) = decode_index(&bytes) else {
            return Ok(None);
        };
        // Stamp the save time for the racy-clean guard; unknown means "all racy".
        index.saved_at_ns = self
            .layout
            .fs
            .stat(&path)
            .await
            .ok()
            .and_then(|info| systemtime_to_ns(info.mod_time));
        Ok(Some(index))
    }

    async fn save(
        &self,
        account: &str,
        branch: &str,
        index: &CommitIndex,
    ) -> Result<(), IndexStoreError> {
        validate_ref_name(branch)
            .map_err(|_| IndexStoreError::InvalidBranch(branch.to_string()))?;
        let bytes = encode_index(index)?;
        let path = self.layout.index_path(account, branch);
        self.layout
            .write(&path, &bytes, WriteFlag::Create)
            .await
            .map_err(|error| IndexStoreError::Backend(backend_error(error)))?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;
    use std::time::Duration;

    use super::*;
    use crate::core::tiered::{Location, MemoryTierStore, TierStore, TieredFileSystem};
    use crate::git::types::IndexEntry;
    use crate::plugins::memfs::MemFileSystem;

    const ACCOUNT: &str = "acct";
    const MIB: u64 = 1024 * 1024;

    fn oid(hex_byte: u8) -> ObjectId {
        ObjectId::from_bytes_or_panic(&[hex_byte; 20])
    }

    /// A tiered filesystem at the production threshold, as the `/ovgit` mount uses.
    fn tiered() -> (Arc<TieredFileSystem>, Arc<MemoryTierStore>, Arc<MemFileSystem>) {
        let store = Arc::new(MemoryTierStore::new());
        let blobs = Arc::new(MemFileSystem::new());
        let fs = Arc::new(TieredFileSystem::new(store.clone(), blobs.clone(), MIB));
        (fs, store, blobs)
    }

    #[tokio::test]
    async fn objects_round_trip_and_put_is_idempotent() {
        let (fs, store, _) = tiered();
        let objects = AgfsObjectStore::new(fs, "/");
        let body = Bytes::from_static(b"zlib-bytes");

        assert!(!objects.exists(ACCOUNT, &oid(1)).await.unwrap());
        objects.put(ACCOUNT, &oid(1), body.clone()).await.unwrap();
        objects.put(ACCOUNT, &oid(1), body.clone()).await.unwrap();

        assert!(objects.exists(ACCOUNT, &oid(1)).await.unwrap());
        assert_eq!(objects.get(ACCOUNT, &oid(1)).await.unwrap(), body);
        let key = format!("/{}/objects/01/{}", ACCOUNT, "01".repeat(19));
        assert_eq!(
            store.get(&key).await.unwrap().unwrap().location,
            Location::Inline,
            "small objects stay in the tier store, using the S3 backend's key layout"
        );
        assert!(matches!(
            objects.get(ACCOUNT, &oid(2)).await,
            Err(ObjectStoreError::NotFound(_))
        ));
    }

    #[tokio::test]
    async fn concurrent_puts_of_one_object_all_succeed() {
        let (fs, _, _) = tiered();
        let objects = Arc::new(AgfsObjectStore::new(fs, "/ovgit"));
        let tasks: Vec<_> = (0..16)
            .map(|_| {
                let objects = objects.clone();
                tokio::spawn(async move {
                    objects
                        .put(ACCOUNT, &oid(7), Bytes::from_static(b"same"))
                        .await
                })
            })
            .collect();
        for task in tasks {
            task.await.unwrap().unwrap();
        }
        assert_eq!(objects.get(ACCOUNT, &oid(7)).await.unwrap(), "same");
    }

    #[tokio::test]
    async fn large_objects_go_to_the_blob_backend() {
        let (fs, _, blobs) = tiered();
        let objects = AgfsObjectStore::new(fs, "/");
        let big = Bytes::from(vec![9u8; (MIB + 1) as usize]);
        objects.put(ACCOUNT, &oid(3), big.clone()).await.unwrap();

        assert_eq!(objects.get(ACCOUNT, &oid(3)).await.unwrap(), big);
        assert!(blobs.stat("/_blobs").await.unwrap().is_dir);
    }

    #[tokio::test]
    async fn get_limited_rejects_before_reading() {
        let (fs, _, _) = tiered();
        let objects = AgfsObjectStore::new(fs, "/");
        objects
            .put(ACCOUNT, &oid(4), Bytes::from(vec![0u8; 100]))
            .await
            .unwrap();

        assert!(matches!(
            objects.get_limited(ACCOUNT, &oid(4), 99).await,
            Err(ObjectStoreError::ReadLimitExceeded { size: 100, limit: 99 })
        ));
        assert_eq!(objects.get_limited(ACCOUNT, &oid(4), 100).await.unwrap().len(), 100);
        assert!(matches!(
            objects.get_limited(ACCOUNT, &oid(5), 100).await,
            Err(ObjectStoreError::NotFound(_))
        ));
    }

    #[tokio::test]
    async fn refs_follow_compare_and_swap_semantics() {
        let (fs, _, _) = tiered();
        let refs = AgfsRefStore::new(fs, "/ovgit");
        let main = "refs/heads/main";

        assert!(matches!(
            refs.read(ACCOUNT, main).await,
            Err(RefStoreError::NotFound(_))
        ));
        refs.cas_update(ACCOUNT, main, None, oid(1)).await.unwrap();
        assert!(matches!(
            refs.cas_update(ACCOUNT, main, None, oid(2)).await,
            Err(RefStoreError::Conflict {
                expected: None,
                actual: Some(_)
            })
        ));
        refs.cas_update(ACCOUNT, main, Some(oid(1)), oid(2))
            .await
            .unwrap();
        assert_eq!(refs.read(ACCOUNT, main).await.unwrap(), oid(2));
        match refs.cas_update(ACCOUNT, main, Some(oid(1)), oid(3)).await {
            Err(RefStoreError::Conflict { actual, .. }) => assert_eq!(actual, Some(oid(2))),
            other => panic!("expected conflict, got {other:?}"),
        }
        assert!(matches!(
            refs.cas_update(ACCOUNT, "../escape", None, oid(1)).await,
            Err(RefStoreError::InvalidName(_))
        ));
    }

    #[tokio::test]
    async fn ref_cas_accepts_refs_written_without_trailing_newline() {
        let (fs, _, _) = tiered();
        // A ref imported from another writer, stored without the trailing newline.
        let path = format!("/ovgit/{}/refs/heads/main", ACCOUNT);
        fs.write(&path, oid(1).to_hex().to_string().as_bytes(), 0, WriteFlag::Create)
            .await
            .unwrap();
        let refs = AgfsRefStore::new(fs, "/ovgit");

        refs.cas_update(ACCOUNT, "refs/heads/main", Some(oid(1)), oid(2))
            .await
            .unwrap();
        assert_eq!(refs.read(ACCOUNT, "refs/heads/main").await.unwrap(), oid(2));
    }

    #[tokio::test]
    async fn concurrent_ref_updates_never_lose_a_commit() {
        let (fs, _, _) = tiered();
        let refs = Arc::new(AgfsRefStore::new(fs, "/"));
        let tasks: Vec<_> = (1..=10u8)
            .map(|i| {
                let refs = refs.clone();
                tokio::spawn(async move {
                    for _ in 0..100 {
                        let current = refs.read(ACCOUNT, "refs/heads/main").await.ok();
                        match refs.cas_update(ACCOUNT, "refs/heads/main", current, oid(i)).await {
                            Ok(()) => return true,
                            Err(RefStoreError::Conflict { .. }) => {
                                tokio::time::sleep(Duration::from_millis(1)).await
                            }
                            Err(error) => panic!("unexpected error: {error}"),
                        }
                    }
                    false
                })
            })
            .collect();
        for task in tasks {
            assert!(task.await.unwrap(), "every writer eventually wins its CAS");
        }
    }

    #[tokio::test]
    async fn list_returns_account_relative_ref_names() {
        let (fs, _, _) = tiered();
        let refs = AgfsRefStore::new(fs, "/ovgit");
        refs.cas_update(ACCOUNT, "refs/heads/main", None, oid(1))
            .await
            .unwrap();
        refs.cas_update(ACCOUNT, "refs/heads/feature/x", None, oid(2))
            .await
            .unwrap();
        refs.cas_update(ACCOUNT, "refs/tags/v1", None, oid(3))
            .await
            .unwrap();

        let mut heads = refs.list(ACCOUNT, "refs/heads/").await.unwrap();
        heads.sort();
        assert_eq!(
            heads,
            vec![
                ("refs/heads/feature/x".to_string(), oid(2)),
                ("refs/heads/main".to_string(), oid(1)),
            ]
        );
        assert!(refs.list("other", "refs/heads/").await.unwrap().is_empty());
    }

    #[tokio::test]
    async fn index_round_trips_and_degrades_to_none() {
        let (fs, _, _) = tiered();
        let indexes = AgfsIndexStore::new(fs.clone(), "/ovgit");
        assert!(indexes.load(ACCOUNT, "main").await.unwrap().is_none());

        let mut entries = HashMap::new();
        entries.insert(
            "resources/a.md".to_string(),
            IndexEntry {
                size: 11,
                mtime_ns: 1_700_000_000_000_000_000,
                oid: oid(0xAA),
            },
        );
        let index = CommitIndex {
            parent_oid: oid(0xCC),
            entries,
            saved_at_ns: None,
        };
        indexes.save(ACCOUNT, "main", &index).await.unwrap();
        let loaded = indexes.load(ACCOUNT, "main").await.unwrap().unwrap();
        assert_eq!(loaded.parent_oid, index.parent_oid);
        assert_eq!(loaded.entries, index.entries);
        assert!(loaded.saved_at_ns.is_some(), "stamped from the stored mtime");

        let path = format!("/ovgit/{}/index/main.json", ACCOUNT);
        fs.write(&path, b"not json", 0, WriteFlag::Truncate)
            .await
            .unwrap();
        assert!(indexes.load(ACCOUNT, "main").await.unwrap().is_none());
        assert!(matches!(
            indexes.load(ACCOUNT, "../escape").await,
            Err(IndexStoreError::InvalidBranch(_))
        ));
    }

    #[tokio::test]
    async fn stores_work_on_filesystems_that_need_parent_directories() {
        let fs: Arc<dyn FileSystem> = Arc::new(MemFileSystem::new());
        let objects = AgfsObjectStore::new(fs.clone(), "/ovgit");
        let refs = AgfsRefStore::new(fs, "/ovgit");

        objects
            .put(ACCOUNT, &oid(1), Bytes::from_static(b"x"))
            .await
            .unwrap();
        refs.cas_update(ACCOUNT, "refs/heads/main", None, oid(1))
            .await
            .unwrap();
        assert_eq!(objects.get(ACCOUNT, &oid(1)).await.unwrap(), "x");
        assert_eq!(refs.read(ACCOUNT, "refs/heads/main").await.unwrap(), oid(1));
    }
}
