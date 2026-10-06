//! Test-only helpers shared by wrapper tests.

use async_trait::async_trait;
use std::path::Path;
use std::sync::{Arc, Mutex};

use super::{
    ConfigParameter, FileInfo, FileSystem, PluginConfig, Result, ServicePlugin, WriteFlag,
};
use crate::plugins::memfs::MemFileSystem;

/// In-memory filesystem that records which data-path methods were called.
///
/// Wrapper tests use it as the inner filesystem to prove that `write_from_path`
/// and `read_to_path` are forwarded instead of falling back to the buffered
/// trait defaults (which would show up as `write` / `read`). Clones share the
/// same storage and call log, so a clone can be mounted through [`SpyPlugin`]
/// while the test keeps a handle for assertions.
#[derive(Clone)]
pub(crate) struct SpyFs {
    inner: Arc<MemFileSystem>,
    calls: Arc<Mutex<Vec<&'static str>>>,
}

impl SpyFs {
    pub(crate) fn new() -> Self {
        Self {
            inner: Arc::new(MemFileSystem::new()),
            calls: Arc::new(Mutex::new(Vec::new())),
        }
    }

    pub(crate) fn calls(&self) -> Vec<&'static str> {
        self.calls.lock().unwrap().clone()
    }

    pub(crate) fn clear_calls(&self) {
        self.calls.lock().unwrap().clear();
    }

    fn record(&self, call: &'static str) {
        self.calls.lock().unwrap().push(call);
    }
}

#[async_trait]
impl FileSystem for SpyFs {
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
        self.record("read");
        self.inner.read(path, offset, size).await
    }

    async fn write(&self, path: &str, data: &[u8], offset: u64, flags: WriteFlag) -> Result<u64> {
        self.record("write");
        self.inner.write(path, data, offset, flags).await
    }

    async fn write_from_path(&self, path: &str, src: &Path, flags: WriteFlag) -> Result<u64> {
        self.record("write_from_path");
        self.inner.write_from_path(path, src, flags).await
    }

    async fn read_to_path(&self, path: &str, dst: &Path) -> Result<u64> {
        self.record("read_to_path");
        self.inner.read_to_path(path, dst).await
    }

    async fn read_dir(
        &self,
        path: &str,
        offset: Option<usize>,
        limit: Option<usize>,
        sort_by: Option<super::ListSortBy>,
        sort_order: Option<super::SortOrder>,
    ) -> Result<Vec<FileInfo>> {
        self.inner
            .read_dir(path, offset, limit, sort_by, sort_order)
            .await
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

/// Plugin named `spy` that mounts a clone of the given [`SpyFs`].
pub(crate) struct SpyPlugin {
    pub(crate) spy: SpyFs,
}

#[async_trait]
impl ServicePlugin for SpyPlugin {
    fn name(&self) -> &str {
        "spy"
    }

    fn readme(&self) -> &str {
        "Recording plugin for wrapper forwarding tests"
    }

    async fn validate(&self, _config: &PluginConfig) -> Result<()> {
        Ok(())
    }

    async fn initialize(&self, _config: PluginConfig) -> Result<Box<dyn FileSystem>> {
        Ok(Box::new(self.spy.clone()))
    }

    fn config_params(&self) -> &[ConfigParameter] {
        &[]
    }
}
