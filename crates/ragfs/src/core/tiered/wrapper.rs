//! [`TieredFileSystem`]: routes file bytes by size between a [`TierStore`]
//! (small files, plus the index for everything) and a blob backend (large files).
//!
//! Write ordering keeps the index authoritative under crashes:
//! - large write: PUT blob -> upsert row -> delete the previous blob
//! - delete: remove row -> delete blob
//!
//! A crash can therefore leave an unreferenced blob (collected by
//! [`TieredFileSystem::collect_orphan_blobs`]) but never a row that points at
//! missing bytes.

use std::path::Path;
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime};

use async_trait::async_trait;
use tokio::task::JoinHandle;
use tracing::{info, warn};

use crate::core::errors::{Error, Result};
use crate::core::filesystem::{apply_read_dir_options, FileSystem};
use crate::core::types::{FileInfo, ListSortBy, SortOrder, WriteFlag};

use super::store::{Expected, Location, PutMode, TierEntry, TierStore};

/// Blob backend directory holding large-file objects.
pub const BLOB_ROOT: &str = "/_blobs";
/// Longest accepted path in bytes (InnoDB index key limit for the path column).
pub const MAX_PATH_BYTES: usize = 3072;

/// Counts from [`TieredFileSystem::import_untiered`].
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct ImportStats {
    /// Directories added to the index.
    pub directories: usize,
    /// Small files moved into the store.
    pub inlined: usize,
    /// Large files indexed at their existing object key.
    pub indexed_in_place: usize,
    /// Leftover objects of already inlined files that were deleted.
    pub cleaned: usize,
    /// Backend directories (S3 directory markers) removed once emptied.
    pub removed_directories: usize,
}

/// A `FileSystem` that keeps small files in a [`TierStore`] and large files in
/// a blob backend.
pub struct TieredFileSystem {
    store: Arc<dyn TierStore>,
    blobs: Arc<dyn FileSystem>,
    threshold: u64,
    import_exclude: Vec<String>,
}

impl TieredFileSystem {
    /// Wrap `blobs` so files smaller than `threshold` bytes live in `store`.
    pub fn new(store: Arc<dyn TierStore>, blobs: Arc<dyn FileSystem>, threshold: u64) -> Self {
        Self {
            store,
            blobs,
            threshold,
            import_exclude: Vec::new(),
        }
    }

    /// Ignore these top-level backend names in [`Self::has_untiered_data`] and
    /// [`Self::import_untiered`], because another mount owns them.
    pub fn with_import_exclude(mut self, names: Vec<String>) -> Self {
        self.import_exclude = names;
        self
    }

    /// Whether a top-level backend entry belongs to this mount's legacy data.
    fn is_importable_root_entry(&self, name: &str) -> bool {
        name != BLOB_ROOT.trim_start_matches('/') && !self.import_exclude.iter().any(|n| n == name)
    }

    /// Delete blobs that no index row references and that are older than `min_age`.
    ///
    /// `min_age` protects blobs whose row is still being written. Returns the
    /// number of blobs deleted.
    pub async fn collect_orphan_blobs(&self, min_age: Duration) -> Result<usize> {
        collect_orphans(self.store.as_ref(), self.blobs.as_ref(), min_age).await
    }

    /// Run [`Self::collect_orphan_blobs`] every `interval` in the background.
    ///
    /// The task holds weak references and stops once this filesystem is
    /// dropped. Every instance of a deployment may run it: deleting a blob
    /// another instance already removed is not an error.
    pub fn spawn_orphan_gc(&self, interval: Duration, min_age: Duration) -> JoinHandle<()> {
        let store = Arc::downgrade(&self.store);
        let blobs = Arc::downgrade(&self.blobs);
        tokio::spawn(async move {
            loop {
                tokio::time::sleep(interval).await;
                let (Some(store), Some(blobs)) = (store.upgrade(), blobs.upgrade()) else {
                    return;
                };
                let started = Instant::now();
                match collect_orphans(store.as_ref(), blobs.as_ref(), min_age).await {
                    Ok(deleted) => info!(
                        deleted,
                        elapsed_ms = started.elapsed().as_millis() as u64,
                        "tiered: orphan blob GC finished"
                    ),
                    Err(error) => warn!(%error, "tiered: orphan blob GC failed"),
                }
            }
        })
    }

    /// Whether the blob backend holds data written before tiering was enabled.
    ///
    /// Only checked while the index is empty: an existing bucket would otherwise
    /// look empty through this filesystem.
    pub async fn has_untiered_data(&self) -> Result<bool> {
        if !self.store.list_children("/").await?.is_empty() {
            return Ok(false);
        }
        match self.blobs.read_dir("/", None, None, None, None).await {
            Ok(entries) => Ok(entries
                .iter()
                .any(|entry| self.is_importable_root_entry(&entry.name))),
            Err(Error::NotFound(_)) => Ok(false),
            Err(error) => Err(error),
        }
    }

    /// Index files that exist in the blob backend but not in the store.
    ///
    /// Small files move inline (row first, then the object is deleted). Large
    /// files are indexed in place: their row points at the existing object key,
    /// so nothing is copied and no data moves before its row exists. Safe to
    /// re-run after a crash; already indexed paths are skipped and leftover
    /// objects of inlined files are deleted. Backend directories left empty
    /// afterwards are removed too, since on S3 each is a 0-byte marker object.
    pub async fn import_untiered(&self) -> Result<ImportStats> {
        let mut stats = ImportStats::default();
        // Objects already referenced by a row (e.g. a large file imported in place
        // and renamed since) must not be imported a second time at their key.
        let referenced = self.store.blob_keys().await?;
        let mut pending = vec!["/".to_string()];
        // Discovery order: every directory comes after its parent.
        let mut visited = Vec::new();
        while let Some(dir) = pending.pop() {
            for info in self.blobs.read_dir(&dir, None, None, None, None).await? {
                let path = if dir == "/" {
                    format!("/{}", info.name)
                } else {
                    format!("{}/{}", dir, info.name)
                };
                if dir == "/" && !self.is_importable_root_entry(&info.name) {
                    continue;
                }
                if info.is_dir {
                    match self.store.create_dir(&path, info.mode, info.mod_time).await {
                        Ok(()) => stats.directories += 1,
                        Err(Error::AlreadyExists(_)) => {}
                        Err(error) => return Err(error),
                    }
                    visited.push(path.clone());
                    pending.push(path);
                } else if !referenced.contains(&path) {
                    self.import_file(&path, &info, &mut stats).await?;
                }
            }
        }
        // Children before parents, so emptied subtrees disappear bottom-up.
        for dir in visited.iter().rev() {
            if self.remove_empty_backend_dir(dir).await? {
                stats.removed_directories += 1;
            }
        }
        Ok(stats)
    }

    /// Remove `dir` from the blob backend if it has no children left.
    ///
    /// Backends disagree on `remove` for directories (s3fs deletes an empty
    /// one, memfs refuses), so emptiness is checked here and `remove_all`
    /// deletes the bare directory. Nothing writes to legacy paths once the
    /// mount is tiered, so the directory cannot gain children in between.
    async fn remove_empty_backend_dir(&self, dir: &str) -> Result<bool> {
        match self.blobs.read_dir(dir, None, None, None, None).await {
            // Still holds large files indexed in place.
            Ok(children) if !children.is_empty() => return Ok(false),
            Ok(_) => {}
            Err(Error::NotFound(_)) => return Ok(false),
            Err(error) => return Err(error),
        }
        match self.blobs.remove_all(dir).await {
            Ok(()) => Ok(true),
            Err(Error::NotFound(_)) => Ok(false),
            Err(error) => Err(error),
        }
    }

    async fn import_file(
        &self,
        path: &str,
        info: &FileInfo,
        stats: &mut ImportStats,
    ) -> Result<()> {
        if self.store.get(path).await?.is_some() {
            // Indexed already and not referenced as a blob (checked by the caller):
            // the object is a leftover of an inlined file or of an overwritten path.
            self.blobs.remove(path).await?;
            stats.cleaned += 1;
            return Ok(());
        }
        let mode = if info.mode == 0 { 0o644 } else { info.mode };
        if info.size < self.threshold {
            let data = self.blobs.read(path, 0, 0).await?;
            let mut entry = Self::file_entry(path, data.len() as u64, mode, Location::Inline);
            entry.mod_time = info.mod_time;
            self.store
                .put_file(entry, Some(&data), PutMode::CreateNew)
                .await?;
            self.blobs.remove(path).await?;
            stats.inlined += 1;
        } else {
            let mut entry =
                Self::file_entry(path, info.size, mode, Location::Blob(path.to_string()));
            entry.mod_time = info.mod_time;
            self.store.put_file(entry, None, PutMode::CreateNew).await?;
            stats.indexed_in_place += 1;
        }
        Ok(())
    }

    /// The blob backend, for mount-stack capability discovery.
    pub(crate) fn inner_fs(&self) -> &Arc<dyn FileSystem> {
        &self.blobs
    }

    /// Canonical form of `path`: leading `/`, no empty segments (`//` collapses
    /// like s3fs), no trailing `/`. `.` and `..` segments are rejected because
    /// the index stores paths verbatim.
    fn normalize(path: &str) -> Result<String> {
        let mut normalized = String::with_capacity(path.len() + 1);
        for segment in path.split('/').filter(|segment| !segment.is_empty()) {
            if segment == "." || segment == ".." {
                return Err(Error::invalid_path(format!(
                    "relative segment in path: {}",
                    path
                )));
            }
            normalized.push('/');
            normalized.push_str(segment);
        }
        if normalized.is_empty() {
            normalized.push('/');
        }
        if normalized.len() > MAX_PATH_BYTES {
            let head: String = normalized.chars().take(64).collect();
            return Err(Error::invalid_path(format!(
                "path exceeds {} bytes: {}…",
                MAX_PATH_BYTES, head
            )));
        }
        Ok(normalized)
    }

    fn new_blob_key() -> String {
        let id = uuid::Uuid::new_v4().simple().to_string();
        format!("{}/{}/{}", BLOB_ROOT, &id[..2], id)
    }

    fn root_info() -> FileInfo {
        FileInfo {
            name: "/".to_string(),
            size: 0,
            mode: 0o755,
            mod_time: SystemTime::now(),
            is_dir: true,
        }
    }

    fn to_info(entry: &TierEntry) -> FileInfo {
        FileInfo {
            name: entry
                .path
                .rsplit('/')
                .next()
                .unwrap_or_default()
                .to_string(),
            size: entry.size,
            mode: entry.mode,
            mod_time: entry.mod_time,
            is_dir: entry.is_dir(),
        }
    }

    fn file_entry(path: &str, size: u64, mode: u32, location: Location) -> TierEntry {
        TierEntry {
            path: path.to_string(),
            size,
            mode,
            mod_time: SystemTime::now(),
            location,
        }
    }

    /// Delete a blob that is no longer referenced. Failures leave an orphan for GC.
    async fn release_blob(&self, entry: Option<&TierEntry>) {
        let Some(key) = entry.and_then(TierEntry::blob_key) else {
            return;
        };
        if let Err(error) = self.blobs.remove(key).await {
            warn!(blob = key, %error, "tiered: failed to delete released blob; left for orphan GC");
        }
    }

    async fn release_blobs(&self, entries: &[TierEntry]) {
        for entry in entries {
            self.release_blob(Some(entry)).await;
        }
    }

    /// Read a file's full bytes from whichever tier holds them.
    async fn read_entry(&self, entry: &TierEntry, offset: u64, size: u64) -> Result<Vec<u8>> {
        match &entry.location {
            Location::Directory => Err(Error::IsADirectory(entry.path.clone())),
            Location::Inline => {
                let data = self
                    .store
                    .read_inline(&entry.path)
                    .await?
                    .ok_or_else(|| Error::not_found(&entry.path))?;
                Ok(slice_range(&data, offset, size))
            }
            Location::Blob(key) => self.blobs.read(key, offset, size).await,
        }
    }

    /// Store `content` at `path` in the tier its size selects.
    async fn store_content(
        &self,
        path: &str,
        content: &[u8],
        mode: u32,
        put_mode: PutMode,
    ) -> Result<()> {
        let size = content.len() as u64;
        if size < self.threshold {
            let entry = Self::file_entry(path, size, mode, Location::Inline);
            let previous = self.store.put_file(entry, Some(content), put_mode).await?;
            self.release_blob(previous.as_ref()).await;
            return Ok(());
        }
        let key = Self::new_blob_key();
        self.put_blob(&key, content).await?;
        self.publish_blob(path, key, size, mode, put_mode).await
    }

    /// Write a new blob. Object stores need no parent directories; backends that
    /// do (memfs, localfs) get them created on the first `NotFound`.
    async fn put_blob(&self, key: &str, content: &[u8]) -> Result<()> {
        match self.blobs.write(key, content, 0, WriteFlag::Create).await {
            Err(Error::NotFound(_)) => {
                self.blobs.ensure_parent_dirs(key, 0o755).await?;
                self.blobs.write(key, content, 0, WriteFlag::Create).await?;
                Ok(())
            }
            other => other.map(|_| ()),
        }
    }

    /// Stream a local file into a new blob; see [`Self::put_blob`] for parents.
    async fn put_blob_from_path(&self, key: &str, src: &Path) -> Result<u64> {
        match self
            .blobs
            .write_from_path(key, src, WriteFlag::Create)
            .await
        {
            Err(Error::NotFound(_)) => {
                self.blobs.ensure_parent_dirs(key, 0o755).await?;
                self.blobs
                    .write_from_path(key, src, WriteFlag::Create)
                    .await
            }
            other => other,
        }
    }

    /// Point `path` at an already-written blob, deleting the blob if that fails.
    ///
    /// The blob is deleted only when the error proves the row was not written.
    /// Any other failure (e.g. a dropped connection during commit) may have
    /// committed, so the blob is left for orphan GC instead of risking a row
    /// that points at missing bytes.
    async fn publish_blob(
        &self,
        path: &str,
        key: String,
        size: u64,
        mode: u32,
        put_mode: PutMode,
    ) -> Result<()> {
        let entry = Self::file_entry(path, size, mode, Location::Blob(key.clone()));
        match self.store.put_file(entry, None, put_mode).await {
            Ok(previous) => {
                self.release_blob(previous.as_ref()).await;
                Ok(())
            }
            Err(error) => {
                let rolled_back = matches!(
                    error,
                    Error::AlreadyExists(_) | Error::IsADirectory(_) | Error::NotADirectory(_)
                );
                if rolled_back {
                    if let Err(cleanup) = self.blobs.remove(&key).await {
                        warn!(blob = %key, %cleanup, "tiered: failed to delete unpublished blob");
                    }
                }
                Err(error)
            }
        }
    }

    /// Return the existing file row, rejecting directories and the root.
    async fn existing_file(&self, path: &str) -> Result<Option<TierEntry>> {
        if path == "/" {
            return Err(Error::IsADirectory(path.to_string()));
        }
        match self.store.get(path).await? {
            Some(entry) if entry.is_dir() => Err(Error::IsADirectory(path.to_string())),
            other => Ok(other),
        }
    }

    /// Return the current bytes of `entry` (empty when absent).
    async fn current_bytes(&self, entry: Option<&TierEntry>) -> Result<Vec<u8>> {
        match entry {
            Some(entry) => self.read_entry(entry, 0, 0).await,
            None => Ok(Vec::new()),
        }
    }

    /// Check that `entry` still holds `expected` and return the matching CAS token.
    async fn matching_token<'a>(
        &self,
        entry: &'a TierEntry,
        expected: &'a [u8],
    ) -> Result<Option<Expected<'a>>> {
        match &entry.location {
            Location::Directory => Ok(None),
            Location::Inline => Ok(Some(Expected::Inline(expected))),
            Location::Blob(key) => {
                // Blob keys are immutable, so matching the key later pins this content.
                // A blob released by a concurrent overwrite is a mismatch, as in s3fs.
                match self.blobs.read(key, 0, 0).await {
                    Ok(current) => Ok((current == expected).then_some(Expected::Blob(key))),
                    Err(Error::NotFound(_)) => Ok(None),
                    Err(error) => Err(error),
                }
            }
        }
    }
}

/// Delete unreferenced blobs under [`BLOB_ROOT`] older than `min_age`.
async fn collect_orphans(
    store: &dyn TierStore,
    blobs: &dyn FileSystem,
    min_age: Duration,
) -> Result<usize> {
    // Snapshot references before listing so a blob written in between is
    // either referenced or younger than `min_age`.
    let referenced = store.blob_keys().await?;
    let shards = match blobs.read_dir(BLOB_ROOT, None, None, None, None).await {
        Ok(shards) => shards,
        Err(Error::NotFound(_)) => return Ok(0),
        Err(error) => return Err(error),
    };
    let cutoff = SystemTime::now()
        .checked_sub(min_age)
        .unwrap_or(SystemTime::UNIX_EPOCH);
    let mut deleted = 0;
    for shard in shards.iter().filter(|shard| shard.is_dir) {
        let shard_path = format!("{}/{}", BLOB_ROOT, shard.name);
        let entries = match blobs.read_dir(&shard_path, None, None, None, None).await {
            Ok(entries) => entries,
            Err(Error::NotFound(_)) => continue,
            Err(error) => return Err(error),
        };
        for blob in entries.iter().filter(|blob| !blob.is_dir) {
            let key = format!("{}/{}", shard_path, blob.name);
            if referenced.contains(&key) || blob.mod_time > cutoff {
                continue;
            }
            match blobs.remove(&key).await {
                Ok(()) => deleted += 1,
                // Another instance's GC got there first.
                Err(Error::NotFound(_)) => {}
                Err(error) => return Err(error),
            }
        }
    }
    Ok(deleted)
}

/// Return `data[offset..offset+size]`, clamped; `size == 0` reads to the end.
fn slice_range(data: &[u8], offset: u64, size: u64) -> Vec<u8> {
    let start = usize::try_from(offset)
        .unwrap_or(usize::MAX)
        .min(data.len());
    let end = if size == 0 {
        data.len()
    } else {
        start
            .saturating_add(usize::try_from(size).unwrap_or(usize::MAX))
            .min(data.len())
    };
    data[start..end].to_vec()
}

/// Overwrite `base` with `data` at `offset`, zero-filling any gap.
fn splice(mut base: Vec<u8>, offset: u64, data: &[u8]) -> Vec<u8> {
    let start = usize::try_from(offset).unwrap_or(usize::MAX);
    let end = start.saturating_add(data.len());
    if base.len() < end {
        base.resize(end, 0);
    }
    base[start..end].copy_from_slice(data);
    base
}

#[async_trait]
impl FileSystem for TieredFileSystem {
    async fn create(&self, path: &str) -> Result<()> {
        let path = Self::normalize(path)?;
        self.existing_file(&path).await?;
        self.store_content(&path, &[], 0o644, PutMode::CreateNew)
            .await
    }

    async fn mkdir(&self, path: &str, mode: u32) -> Result<()> {
        let path = Self::normalize(path)?;
        if path == "/" {
            return Err(Error::already_exists(path));
        }
        self.store.create_dir(&path, mode, SystemTime::now()).await
    }

    async fn remove(&self, path: &str) -> Result<()> {
        let path = Self::normalize(path)?;
        if path == "/" {
            return Err(Error::invalid_operation("cannot remove root directory"));
        }
        let removed = self.store.remove_entry(&path).await?;
        self.release_blob(Some(&removed)).await;
        Ok(())
    }

    async fn remove_all(&self, path: &str) -> Result<()> {
        let path = Self::normalize(path)?;
        let removed = self.store.remove_subtree(&path).await?;
        self.release_blobs(&removed).await;
        Ok(())
    }

    async fn read(&self, path: &str, offset: u64, size: u64) -> Result<Vec<u8>> {
        let path = Self::normalize(path)?;
        if path == "/" {
            return Err(Error::IsADirectory(path));
        }
        let entry = self
            .store
            .get(&path)
            .await?
            .ok_or_else(|| Error::not_found(&path))?;
        match self.read_entry(&entry, offset, size).await {
            // A concurrent overwrite may have released the blob we resolved; re-resolve once.
            Err(Error::NotFound(_)) => {
                let fresh = self
                    .store
                    .get(&path)
                    .await?
                    .ok_or_else(|| Error::not_found(&path))?;
                self.read_entry(&fresh, offset, size).await
            }
            other => other,
        }
    }

    async fn write(&self, path: &str, data: &[u8], offset: u64, flags: WriteFlag) -> Result<u64> {
        let path = Self::normalize(path)?;
        let existing = self.existing_file(&path).await?;
        let mode = existing.as_ref().map_or(0o644, |entry| entry.mode);
        // Like memfs and s3fs, whole-file flags replace the content and ignore `offset`.
        let (content, put_mode) = match flags {
            WriteFlag::CreateNew => {
                if existing.is_some() {
                    return Err(Error::already_exists(&path));
                }
                (data.to_vec(), PutMode::CreateNew)
            }
            WriteFlag::Create | WriteFlag::Truncate => (data.to_vec(), PutMode::Upsert),
            WriteFlag::Append => {
                let mut current = self.current_bytes(existing.as_ref()).await?;
                current.extend_from_slice(data);
                (current, PutMode::Upsert)
            }
            WriteFlag::None => {
                let current = self.current_bytes(existing.as_ref()).await?;
                (splice(current, offset, data), PutMode::Upsert)
            }
        };
        self.store_content(&path, &content, mode, put_mode).await?;
        Ok(data.len() as u64)
    }

    async fn write_from_path(&self, path: &str, src: &Path, flags: WriteFlag) -> Result<u64> {
        let size = tokio::fs::metadata(src).await?.len();
        let streamable = matches!(
            flags,
            WriteFlag::Create | WriteFlag::CreateNew | WriteFlag::Truncate
        );
        if size < self.threshold || !streamable {
            let data = tokio::fs::read(src).await?;
            return self.write(path, &data, 0, flags).await;
        }
        let path = Self::normalize(path)?;
        let existing = self.existing_file(&path).await?;
        let put_mode = if flags == WriteFlag::CreateNew {
            if existing.is_some() {
                return Err(Error::already_exists(&path));
            }
            PutMode::CreateNew
        } else {
            PutMode::Upsert
        };
        let mode = existing.as_ref().map_or(0o644, |entry| entry.mode);
        let key = Self::new_blob_key();
        // Stream through the backend so large uploads use multipart, not one buffer.
        let written = self.put_blob_from_path(&key, src).await?;
        self.publish_blob(&path, key, written, mode, put_mode)
            .await?;
        Ok(written)
    }

    async fn read_to_path(&self, path: &str, dst: &Path) -> Result<u64> {
        let path = Self::normalize(path)?;
        let entry = self
            .existing_file(&path)
            .await?
            .ok_or_else(|| Error::not_found(&path))?;
        match entry.blob_key() {
            Some(key) => self.blobs.read_to_path(key, dst).await,
            None => {
                let data = self.read_entry(&entry, 0, 0).await?;
                tokio::fs::write(dst, &data).await?;
                Ok(data.len() as u64)
            }
        }
    }

    async fn compare_and_write(
        &self,
        path: &str,
        expected: &[u8],
        new_data: &[u8],
    ) -> Result<bool> {
        let path = Self::normalize(path)?;
        let Some(entry) = self.existing_file(&path).await? else {
            return Ok(false);
        };
        let Some(token) = self.matching_token(&entry, expected).await? else {
            return Ok(false);
        };
        let size = new_data.len() as u64;
        let (new_entry, inline, new_key) = if size < self.threshold {
            let entry = Self::file_entry(&path, size, entry.mode, Location::Inline);
            (entry, Some(new_data), None)
        } else {
            let key = Self::new_blob_key();
            self.put_blob(&key, new_data).await?;
            let entry = Self::file_entry(&path, size, entry.mode, Location::Blob(key.clone()));
            (entry, None, Some(key))
        };
        match self.store.compare_and_put(token, new_entry, inline).await? {
            Some(previous) => {
                self.release_blob(Some(&previous)).await;
                Ok(true)
            }
            None => {
                if let Some(key) = new_key {
                    if let Err(error) = self.blobs.remove(&key).await {
                        warn!(blob = %key, %error, "tiered: failed to delete losing CAS blob");
                    }
                }
                Ok(false)
            }
        }
    }

    async fn compare_and_remove(&self, path: &str, expected: &[u8]) -> Result<bool> {
        let path = Self::normalize(path)?;
        let Some(entry) = self.existing_file(&path).await? else {
            return Ok(false);
        };
        let Some(token) = self.matching_token(&entry, expected).await? else {
            return Ok(false);
        };
        match self.store.compare_and_remove(&path, token).await? {
            Some(removed) => {
                self.release_blob(Some(&removed)).await;
                Ok(true)
            }
            None => Ok(false),
        }
    }

    async fn read_dir(
        &self,
        path: &str,
        offset: Option<usize>,
        limit: Option<usize>,
        sort_by: Option<ListSortBy>,
        sort_order: Option<SortOrder>,
    ) -> Result<Vec<FileInfo>> {
        let path = Self::normalize(path)?;
        if path != "/" {
            match self.store.get(&path).await? {
                None => return Err(Error::not_found(&path)),
                Some(entry) if !entry.is_dir() => return Err(Error::NotADirectory(path)),
                Some(_) => {}
            }
        }
        let entries = self
            .store
            .list_children(&path)
            .await?
            .iter()
            .map(Self::to_info)
            .collect();
        Ok(apply_read_dir_options(
            entries, offset, limit, sort_by, sort_order,
        ))
    }

    async fn stat(&self, path: &str) -> Result<FileInfo> {
        let path = Self::normalize(path)?;
        if path == "/" {
            return Ok(Self::root_info());
        }
        self.store
            .get(&path)
            .await?
            .map(|entry| Self::to_info(&entry))
            .ok_or_else(|| Error::not_found(&path))
    }

    async fn rename(&self, old_path: &str, new_path: &str) -> Result<()> {
        let old_path = Self::normalize(old_path)?;
        let new_path = Self::normalize(new_path)?;
        if old_path == "/" || new_path == "/" {
            return Err(Error::invalid_operation("cannot rename root directory"));
        }
        if old_path == new_path {
            return Ok(());
        }
        let replaced = self
            .store
            .move_entry(&old_path, &new_path, SystemTime::now())
            .await?;
        self.release_blob(replaced.as_ref()).await;
        Ok(())
    }

    async fn replace(&self, src_path: &str, dst_path: &str) -> Result<()> {
        let src_path = Self::normalize(src_path)?;
        let dst_path = Self::normalize(dst_path)?;
        if src_path == "/" || dst_path == "/" {
            return Err(Error::invalid_operation("cannot replace root directory"));
        }
        match self.store.get(&src_path).await? {
            None => return Err(Error::not_found(&src_path)),
            Some(entry) if entry.is_dir() => {
                return Err(Error::invalid_operation(
                    "replace only supports files in tiered storage",
                ))
            }
            Some(_) => {}
        }
        if src_path == dst_path {
            return Ok(());
        }
        let replaced = self
            .store
            .move_entry(&src_path, &dst_path, SystemTime::now())
            .await?;
        self.release_blob(replaced.as_ref()).await;
        Ok(())
    }

    async fn chmod(&self, path: &str, mode: u32) -> Result<()> {
        let path = Self::normalize(path)?;
        if path == "/" {
            return Ok(());
        }
        self.store.set_mode(&path, mode).await
    }
}
