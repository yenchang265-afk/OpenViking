//! Index + small-file store contract for [`super::TieredFileSystem`].
//!
//! A [`TierStore`] is the single source of truth for every path in a tiered
//! mount: it records directories, holds the bytes of small files inline, and
//! points large files at an immutable blob key in the object store. Because a
//! blob key is never rewritten, "location unchanged" implies "content
//! unchanged", which is what makes compare-and-swap on large files safe.

use std::collections::{BTreeMap, HashSet};
use std::time::SystemTime;

use async_trait::async_trait;
use tokio::sync::RwLock;

use crate::core::errors::{Error, Result};

/// Where the bytes of one entry live.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Location {
    /// A directory; it has no bytes.
    Directory,
    /// File bytes are stored inline in the [`TierStore`].
    Inline,
    /// File bytes are stored in the blob backend under this immutable key.
    Blob(String),
}

/// One index row.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TierEntry {
    /// Normalized absolute path (`/a/b.md`); never `/`.
    pub path: String,
    /// File size in bytes; `0` for directories.
    pub size: u64,
    /// Unix-style mode bits.
    pub mode: u32,
    /// Last modification time.
    pub mod_time: SystemTime,
    /// Where the bytes live.
    pub location: Location,
}

impl TierEntry {
    /// Whether this entry is a directory.
    pub fn is_dir(&self) -> bool {
        self.location == Location::Directory
    }

    /// The blob key, when the bytes live in the blob backend.
    pub fn blob_key(&self) -> Option<&str> {
        match &self.location {
            Location::Blob(key) => Some(key),
            _ => None,
        }
    }
}

/// How [`TierStore::put_file`] treats an existing row.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PutMode {
    /// Replace an existing file row.
    Upsert,
    /// Fail with `AlreadyExists` when the path exists.
    CreateNew,
}

/// The current state a conditional update requires.
#[derive(Debug, Clone, Copy)]
pub enum Expected<'a> {
    /// The row is inline and its bytes equal this slice.
    Inline(&'a [u8]),
    /// The row points at this blob key.
    Blob(&'a str),
}

/// Persistent index of a tiered mount.
///
/// Implementations must make each method atomic. Missing ancestor directories
/// are created implicitly by `put_file`, `create_dir` and `move_entry`, which
/// matches object-store semantics where directories are implied by keys.
#[async_trait]
pub trait TierStore: Send + Sync {
    /// Return the row for `path`, without inline bytes.
    async fn get(&self, path: &str) -> Result<Option<TierEntry>>;

    /// Return the inline bytes for `path`, or `None` when it is not an inline file.
    async fn read_inline(&self, path: &str) -> Result<Option<Vec<u8>>>;

    /// Insert or replace a file row and return the row it replaced.
    ///
    /// `inline` must be `Some` exactly when `entry.location` is `Inline`.
    /// Fails with `IsADirectory` when `path` is a directory and with
    /// `AlreadyExists` for `PutMode::CreateNew` when `path` exists.
    async fn put_file(
        &self,
        entry: TierEntry,
        inline: Option<&[u8]>,
        mode: PutMode,
    ) -> Result<Option<TierEntry>>;

    /// Create a directory row. Fails with `AlreadyExists` when `path` exists.
    async fn create_dir(&self, path: &str, mode: u32, mod_time: SystemTime) -> Result<()>;

    /// Return the direct children of directory `dir` (`/` for the root).
    async fn list_children(&self, dir: &str) -> Result<Vec<TierEntry>>;

    /// Remove one file or empty directory and return its row.
    ///
    /// Fails with `NotFound` when missing and `DirectoryNotEmpty` when `path`
    /// has children.
    async fn remove_entry(&self, path: &str) -> Result<TierEntry>;

    /// Remove `path` and every descendant (`/` removes everything) and return
    /// the removed rows. A missing path removes nothing.
    async fn remove_subtree(&self, path: &str) -> Result<Vec<TierEntry>>;

    /// Move `src` (and its subtree when it is a directory) to `dst`.
    ///
    /// A file may replace an existing file at `dst`; the replaced row is
    /// returned so its blob can be released. Moving onto an existing directory,
    /// or moving a directory onto anything, fails with `AlreadyExists`.
    async fn move_entry(
        &self,
        src: &str,
        dst: &str,
        mod_time: SystemTime,
    ) -> Result<Option<TierEntry>>;

    /// Replace the file row at `path` only when it matches `expected`.
    ///
    /// Returns the replaced row on success and `None` when the row is missing
    /// or does not match.
    async fn compare_and_put(
        &self,
        expected: Expected<'_>,
        entry: TierEntry,
        inline: Option<&[u8]>,
    ) -> Result<Option<TierEntry>>;

    /// Remove the file row at `path` only when it matches `expected`.
    async fn compare_and_remove(
        &self,
        path: &str,
        expected: Expected<'_>,
    ) -> Result<Option<TierEntry>>;

    /// Update the mode bits of an existing row.
    async fn set_mode(&self, path: &str, mode: u32) -> Result<()>;

    /// Return every blob key referenced by the index, for orphan collection.
    async fn blob_keys(&self) -> Result<HashSet<String>>;
}

/// Parent directory of a normalized path (`/a/b` -> `/a`, `/a` -> `/`).
pub(crate) fn parent_of(path: &str) -> &str {
    match path.rfind('/') {
        Some(0) | None => "/",
        Some(idx) => &path[..idx],
    }
}

/// Every proper ancestor of `path` except the root, outermost first.
pub(crate) fn ancestors_of(path: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut current = parent_of(path);
    while current != "/" {
        out.push(current.to_string());
        current = parent_of(current);
    }
    out.reverse();
    out
}

/// Whether `candidate` is `root` itself or lives under it.
pub(crate) fn is_same_or_descendant(candidate: &str, root: &str) -> bool {
    root == "/"
        || candidate == root
        || (candidate.len() > root.len()
            && candidate.starts_with(root)
            && candidate.as_bytes()[root.len()] == b'/')
}

/// Rewrite the `src` prefix of `path` to `dst`.
pub(crate) fn rebase(path: &str, src: &str, dst: &str) -> String {
    format!("{}{}", dst, &path[src.len()..])
}

type MemoryRow = (TierEntry, Option<Vec<u8>>);

/// In-process [`TierStore`] for tests and single-process development.
#[derive(Default)]
pub struct MemoryTierStore {
    rows: RwLock<BTreeMap<String, MemoryRow>>,
}

impl MemoryTierStore {
    /// Create an empty store.
    pub fn new() -> Self {
        Self::default()
    }

    fn ensure_ancestors(
        rows: &mut BTreeMap<String, MemoryRow>,
        path: &str,
        now: SystemTime,
    ) -> Result<()> {
        for ancestor in ancestors_of(path) {
            match rows.get(&ancestor) {
                Some((entry, _)) if !entry.is_dir() => {
                    return Err(Error::NotADirectory(ancestor));
                }
                Some(_) => {}
                None => {
                    let dir = TierEntry {
                        path: ancestor.clone(),
                        size: 0,
                        mode: 0o755,
                        mod_time: now,
                        location: Location::Directory,
                    };
                    rows.insert(ancestor, (dir, None));
                }
            }
        }
        Ok(())
    }

    fn has_children(rows: &BTreeMap<String, MemoryRow>, path: &str) -> bool {
        let prefix = format!("{}/", path);
        rows.range(prefix.clone()..)
            .next()
            .is_some_and(|(key, _)| key.starts_with(&prefix))
    }

    fn subtree_keys(rows: &BTreeMap<String, MemoryRow>, root: &str) -> Vec<String> {
        rows.keys()
            .filter(|key| is_same_or_descendant(key, root))
            .cloned()
            .collect()
    }

    fn matches(row: &MemoryRow, expected: Expected<'_>) -> bool {
        match (expected, &row.0.location) {
            (Expected::Inline(bytes), Location::Inline) => row.1.as_deref() == Some(bytes),
            (Expected::Blob(key), Location::Blob(current)) => key == current,
            _ => false,
        }
    }
}

#[async_trait]
impl TierStore for MemoryTierStore {
    async fn get(&self, path: &str) -> Result<Option<TierEntry>> {
        Ok(self
            .rows
            .read()
            .await
            .get(path)
            .map(|(entry, _)| entry.clone()))
    }

    async fn read_inline(&self, path: &str) -> Result<Option<Vec<u8>>> {
        Ok(self
            .rows
            .read()
            .await
            .get(path)
            .and_then(|(_, data)| data.clone()))
    }

    async fn put_file(
        &self,
        entry: TierEntry,
        inline: Option<&[u8]>,
        mode: PutMode,
    ) -> Result<Option<TierEntry>> {
        let mut rows = self.rows.write().await;
        let previous = rows.get(&entry.path).map(|(row, _)| row.clone());
        match &previous {
            Some(row) if row.is_dir() => return Err(Error::IsADirectory(entry.path)),
            Some(_) if mode == PutMode::CreateNew => return Err(Error::already_exists(entry.path)),
            _ => {}
        }
        Self::ensure_ancestors(&mut rows, &entry.path, entry.mod_time)?;
        rows.insert(entry.path.clone(), (entry, inline.map(<[u8]>::to_vec)));
        Ok(previous)
    }

    async fn create_dir(&self, path: &str, mode: u32, mod_time: SystemTime) -> Result<()> {
        let mut rows = self.rows.write().await;
        if rows.contains_key(path) {
            return Err(Error::already_exists(path));
        }
        Self::ensure_ancestors(&mut rows, path, mod_time)?;
        let dir = TierEntry {
            path: path.to_string(),
            size: 0,
            mode,
            mod_time,
            location: Location::Directory,
        };
        rows.insert(path.to_string(), (dir, None));
        Ok(())
    }

    async fn list_children(&self, dir: &str) -> Result<Vec<TierEntry>> {
        let rows = self.rows.read().await;
        Ok(rows
            .values()
            .filter(|(entry, _)| parent_of(&entry.path) == dir)
            .map(|(entry, _)| entry.clone())
            .collect())
    }

    async fn remove_entry(&self, path: &str) -> Result<TierEntry> {
        let mut rows = self.rows.write().await;
        let entry = rows
            .get(path)
            .map(|(entry, _)| entry.clone())
            .ok_or_else(|| Error::not_found(path))?;
        if entry.is_dir() && Self::has_children(&rows, path) {
            return Err(Error::DirectoryNotEmpty(path.to_string()));
        }
        rows.remove(path);
        Ok(entry)
    }

    async fn remove_subtree(&self, path: &str) -> Result<Vec<TierEntry>> {
        let mut rows = self.rows.write().await;
        let keys = Self::subtree_keys(&rows, path);
        Ok(keys
            .iter()
            .filter_map(|key| rows.remove(key).map(|(entry, _)| entry))
            .collect())
    }

    async fn move_entry(
        &self,
        src: &str,
        dst: &str,
        mod_time: SystemTime,
    ) -> Result<Option<TierEntry>> {
        let mut rows = self.rows.write().await;
        let source = rows
            .get(src)
            .map(|(entry, _)| entry.clone())
            .ok_or_else(|| Error::not_found(src))?;
        let replaced = match rows.get(dst).map(|(entry, _)| entry.clone()) {
            Some(existing) if existing.is_dir() || source.is_dir() => {
                return Err(Error::already_exists(dst));
            }
            other => other,
        };
        if source.is_dir() && is_same_or_descendant(dst, src) {
            return Err(Error::invalid_operation(format!(
                "cannot move directory {} into itself",
                src
            )));
        }
        Self::ensure_ancestors(&mut rows, dst, mod_time)?;
        rows.remove(dst);
        for key in Self::subtree_keys(&rows, src) {
            if let Some((mut entry, data)) = rows.remove(&key) {
                entry.path = rebase(&key, src, dst);
                if key == src {
                    entry.mod_time = mod_time;
                }
                rows.insert(entry.path.clone(), (entry, data));
            }
        }
        Ok(replaced)
    }

    async fn compare_and_put(
        &self,
        expected: Expected<'_>,
        entry: TierEntry,
        inline: Option<&[u8]>,
    ) -> Result<Option<TierEntry>> {
        let mut rows = self.rows.write().await;
        let Some(current) = rows.get(&entry.path) else {
            return Ok(None);
        };
        if !Self::matches(current, expected) {
            return Ok(None);
        }
        let previous = current.0.clone();
        rows.insert(entry.path.clone(), (entry, inline.map(<[u8]>::to_vec)));
        Ok(Some(previous))
    }

    async fn compare_and_remove(
        &self,
        path: &str,
        expected: Expected<'_>,
    ) -> Result<Option<TierEntry>> {
        let mut rows = self.rows.write().await;
        let Some(current) = rows.get(path) else {
            return Ok(None);
        };
        if !Self::matches(current, expected) {
            return Ok(None);
        }
        Ok(rows.remove(path).map(|(entry, _)| entry))
    }

    async fn set_mode(&self, path: &str, mode: u32) -> Result<()> {
        let mut rows = self.rows.write().await;
        let (entry, _) = rows.get_mut(path).ok_or_else(|| Error::not_found(path))?;
        entry.mode = mode;
        Ok(())
    }

    async fn blob_keys(&self) -> Result<HashSet<String>> {
        let rows = self.rows.read().await;
        Ok(rows
            .values()
            .filter_map(|(entry, _)| entry.blob_key().map(str::to_string))
            .collect())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parent_and_ancestors_follow_path_components() {
        assert_eq!(parent_of("/a"), "/");
        assert_eq!(parent_of("/a/b/c"), "/a/b");
        assert_eq!(ancestors_of("/a/b/c"), vec!["/a", "/a/b"]);
        assert!(ancestors_of("/a").is_empty());
    }

    #[test]
    fn descendant_check_respects_component_boundaries() {
        assert!(is_same_or_descendant("/a/b", "/a"));
        assert!(is_same_or_descendant("/a", "/a"));
        assert!(!is_same_or_descendant("/ab", "/a"));
        assert!(is_same_or_descendant("/anything", "/"));
    }

    #[test]
    fn rebase_swaps_only_the_prefix() {
        assert_eq!(rebase("/a/b/c", "/a/b", "/x"), "/x/c");
        assert_eq!(rebase("/a/b", "/a/b", "/x/y"), "/x/y");
    }
}
