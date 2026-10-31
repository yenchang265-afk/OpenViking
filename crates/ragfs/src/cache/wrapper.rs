//! A transparent [`FileSystem`](crate::FileSystem) cache wrapper.

use super::envelope::{CacheEnvelope, CacheObjectKind};
use super::versions::{
    ancestor_scopes, normalize_path, KeyKind, VersionMemo, VersionSnapshot, VersionStore,
};
use super::{CacheMetrics, CacheOperation, CachePolicy, CacheTraversalMode};
use crate::cache_runtime::{CacheResult, CacheRuntime, SetOptions, SetResult};
use crate::core::filesystem::{
    apply_read_dir_options, compile_grep_regex, is_excluded_path, normalize_prefix_path,
    paginate_entries, relative_depth, relative_match_file,
};
use crate::core::grep::GrepLineCollector;
use crate::core::types::GrepContextLine;
use crate::core::{
    FileInfo, FileSystem, GlobPage, GrepMatch, GrepOptions, GrepResult, ListSortBy,
    MultiWriteWrappedFS, Result, SortOrder, TreeEntry, WriteFlag,
};
use async_trait::async_trait;
use bytes::Bytes;
use futures::future::join_all;
use futures::stream::{self, StreamExt};
use regex::Regex;
use std::collections::HashMap;
use std::path::Path;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::{Mutex, RwLock, RwLockWriteGuard};

const GREP_CACHE_FILE_CONCURRENCY: usize = 8;
/// Backoff between attempts to bump counters that failed after a mutation.
const BUMP_RETRY_DELAYS: [Duration; 3] = [
    Duration::from_millis(10),
    Duration::from_millis(50),
    Duration::from_millis(200),
];

/// Counter bumps that failed, as `(key, normalized path)` pairs.
type PendingBumps = Vec<(String, String)>;

/// A provider-independent read-through filesystem cache.
///
/// Construction is explicit. RAGFS does not install this wrapper in the
/// default mount path, so existing filesystem behavior remains unchanged.
pub struct CachedFileSystem {
    backend: Box<dyn FileSystem>,
    runtime: Arc<CacheRuntime>,
    versions: VersionStore,
    policy: CachePolicy,
    metrics: Arc<CacheMetrics>,
    operation_lock: RwLock<()>,
    inflight: Mutex<HashMap<String, Arc<Mutex<()>>>>,
    bypass_scopes: RwLock<Vec<String>>,
}

impl CachedFileSystem {
    /// Wrap an existing backend with the unified cache runtime.
    pub fn with_runtime(
        backend: Box<dyn FileSystem>,
        runtime: Arc<CacheRuntime>,
        service_name: impl Into<String>,
        policy: CachePolicy,
    ) -> Self {
        Self::build(backend, runtime, service_name.into(), policy)
    }

    fn build(
        backend: Box<dyn FileSystem>,
        runtime: Arc<CacheRuntime>,
        service_name: String,
        policy: CachePolicy,
    ) -> Self {
        let versions = VersionStore::new(Arc::clone(&runtime), service_name);
        if policy.multi_instance() && !versions.atomic_bump() {
            // The stack builder rejects this; direct callers only get a warning.
            tracing::warn!(
                "CacheFS multi_instance mode without atomic INCRBY: concurrent bumps \
                 from different processes can be lost"
            );
        }
        Self {
            backend,
            versions,
            runtime,
            policy,
            metrics: Arc::new(CacheMetrics::default()),
            operation_lock: RwLock::new(()),
            inflight: Mutex::new(HashMap::new()),
            bypass_scopes: RwLock::new(Vec::new()),
        }
    }

    /// Return this wrapper's cache metrics.
    pub fn metrics(&self) -> Arc<CacheMetrics> {
        Arc::clone(&self.metrics)
    }

    /// Return the unified cache runtime used by this wrapper.
    pub fn runtime(&self) -> Arc<CacheRuntime> {
        Arc::clone(&self.runtime)
    }

    /// Return the wrapped filesystem for mount-stack capability discovery.
    pub(crate) fn inner_fs(&self) -> &dyn FileSystem {
        self.backend.as_ref()
    }

    fn wraps_multiwrite(&self) -> bool {
        let any = self.backend.as_ref() as &dyn std::any::Any;
        any.downcast_ref::<MultiWriteWrappedFS>().is_some()
    }

    /// Invalidate cache objects affected by a write that bypassed this wrapper.
    ///
    /// Raw writers may also have created missing parent directories, so every
    /// ancestor listing is invalidated, not only the direct parent.
    pub(crate) async fn invalidate_external_write(&self, path: &str) {
        let guard = self.operation_lock.write().await;
        let scopes = ancestor_scopes(&parent_path(path));
        let counters = std::iter::once((KeyKind::Object, path))
            .chain(scopes.iter().map(|scope| (KeyKind::Object, scope.as_str())))
            .collect::<Vec<_>>();
        let pending = self.bump_counters(&counters).await;
        self.invalidate_path_objects(path).await;
        for scope in &scopes {
            self.cache_delete(&self.directory_key(scope), scope).await;
        }
        self.settle_bumps(guard, pending).await;
    }

    async fn tree_directory_via_cache(
        &self,
        path: &str,
        show_hidden: bool,
        node_limit: Option<usize>,
        level_limit: Option<usize>,
        offset: Option<usize>,
        sort_by: Option<ListSortBy>,
        sort_order: Option<SortOrder>,
        directories_only: bool,
    ) -> Result<Vec<TreeEntry>> {
        enum TreeTask {
            VisitDir(String),
            Emit(TreeEntry),
        }

        let base_path = normalize_prefix_path(path);
        let mut result = Vec::new();
        let mut stack = vec![TreeTask::VisitDir(base_path.clone())];
        let traversal_limit = node_limit.map(|limit| offset.unwrap_or(0).saturating_add(limit));

        while let Some(task) = stack.pop() {
            if traversal_limit.is_some_and(|limit| result.len() >= limit) {
                break;
            }

            match task {
                TreeTask::Emit(entry) => result.push(entry),
                TreeTask::VisitDir(current_path) => {
                    if let Some(limit) = level_limit {
                        let current_rel = relative_match_file(&base_path, &current_path);
                        if relative_depth(&current_rel) >= limit {
                            continue;
                        }
                    }

                    let entries = self
                        .read_dir_for(
                            CacheOperation::Tree,
                            &current_path,
                            None,
                            None,
                            sort_by,
                            sort_order,
                        )
                        .await?;
                    for entry in entries.into_iter().rev() {
                        let is_hidden_file = !entry.is_dir && entry.name.starts_with('.');
                        if is_hidden_file && !show_hidden {
                            continue;
                        }

                        let entry_path = if current_path == "/" {
                            format!("/{}", entry.name)
                        } else {
                            format!("{}/{}", current_path, entry.name)
                        };
                        let rel_path = relative_match_file(&base_path, &entry_path);
                        let is_dir = entry.is_dir;
                        let tree_entry = TreeEntry {
                            path: entry_path.clone(),
                            rel_path,
                            info: entry,
                            extra: HashMap::new(),
                        };

                        if is_dir {
                            stack.push(TreeTask::VisitDir(entry_path));
                        }
                        if is_dir || !directories_only {
                            stack.push(TreeTask::Emit(tree_entry));
                        }
                    }
                }
            }
        }

        Ok(paginate_entries(result, offset, node_limit))
    }

    async fn grep_via_cache(
        &self,
        path: &str,
        pattern: &str,
        options: GrepOptions<'_>,
    ) -> Result<GrepResult> {
        enum GrepTask {
            Visit { path: String, is_dir: Option<bool> },
        }

        let re = compile_grep_regex(pattern, options.case_insensitive)?;
        let base_path = normalize_prefix_path(path);
        let normalized_exclude = options.exclude_path.map(normalize_prefix_path);
        let options = GrepOptions {
            exclude_path: normalized_exclude.as_deref(),
            ..options
        };
        let mut result = GrepResult::new();
        let generation_cache = VersionMemo::default();
        let mut file_batch = Vec::new();
        let mut stack = vec![GrepTask::Visit {
            path: base_path.clone(),
            is_dir: None,
        }];

        while let Some(GrepTask::Visit {
            path: current_path,
            is_dir,
        }) = stack.pop()
        {
            if options
                .node_limit
                .is_some_and(|limit| result.count >= limit)
            {
                break;
            }

            if let Some(exclude) = normalized_exclude.as_deref() {
                if is_excluded_path(&current_path, exclude) {
                    continue;
                }
            }

            let is_dir = match is_dir {
                Some(is_dir) => is_dir,
                None => self.stat(&current_path).await?.is_dir,
            };
            if is_dir {
                self.flush_grep_file_batch(
                    &mut file_batch,
                    &base_path,
                    &re,
                    options,
                    &mut result,
                    &generation_cache,
                )
                .await?;
                if options
                    .node_limit
                    .is_some_and(|limit| result.count >= limit)
                {
                    break;
                }

                if !options.recursive && current_path != base_path {
                    continue;
                }

                if let Some(limit) = options.level_limit {
                    let rel = relative_match_file(&base_path, &current_path);
                    if relative_depth(&rel) >= limit {
                        continue;
                    }
                }

                let entries = self
                    .read_dir_with_generation_cache(
                        CacheOperation::Grep,
                        &current_path,
                        &generation_cache,
                    )
                    .await?;
                for entry in entries.into_iter().rev() {
                    let entry_path = if current_path == "/" {
                        format!("/{}", entry.name)
                    } else {
                        format!("{}/{}", current_path, entry.name)
                    };
                    stack.push(GrepTask::Visit {
                        path: entry_path,
                        is_dir: Some(entry.is_dir),
                    });
                }
            } else {
                if let Some(limit) = options.level_limit {
                    let rel = relative_match_file(&base_path, &current_path);
                    if relative_depth(&rel) > limit {
                        continue;
                    }
                }

                file_batch.push(current_path);
                if file_batch.len() >= GREP_CACHE_FILE_CONCURRENCY {
                    self.flush_grep_file_batch(
                        &mut file_batch,
                        &base_path,
                        &re,
                        options,
                        &mut result,
                        &generation_cache,
                    )
                    .await?;
                }
            }
        }

        self.flush_grep_file_batch(
            &mut file_batch,
            &base_path,
            &re,
            options,
            &mut result,
            &generation_cache,
        )
        .await?;

        Ok(result)
    }

    async fn flush_grep_file_batch(
        &self,
        file_batch: &mut Vec<String>,
        base_path: &str,
        re: &Regex,
        options: GrepOptions<'_>,
        result: &mut GrepResult,
        generation_cache: &VersionMemo,
    ) -> Result<()> {
        if file_batch.is_empty()
            || options
                .node_limit
                .is_some_and(|limit| result.count >= limit)
        {
            file_batch.clear();
            return Ok(());
        }

        let remaining_limit = options
            .node_limit
            .map(|limit| limit.saturating_sub(result.count))
            .unwrap_or(usize::MAX);
        let files = std::mem::take(file_batch);
        let mut indexed = stream::iter(files.into_iter().enumerate())
            .map(|(index, path)| async move {
                let matches = self
                    .grep_cached_file(
                        &path,
                        base_path,
                        re,
                        remaining_limit,
                        options.before_context,
                        options.after_context,
                        generation_cache,
                    )
                    .await;
                (index, matches)
            })
            .buffer_unordered(GREP_CACHE_FILE_CONCURRENCY)
            .collect::<Vec<_>>()
            .await;

        indexed.sort_by_key(|(index, _)| *index);
        for (_, matches) in indexed {
            for item in matches? {
                if options
                    .node_limit
                    .is_some_and(|limit| result.count >= limit)
                {
                    return Ok(());
                }
                result.matches.push(item);
                result.count += 1;
            }
        }

        Ok(())
    }

    async fn grep_cached_file(
        &self,
        path: &str,
        base_path: &str,
        re: &Regex,
        remaining_limit: usize,
        before_context: usize,
        after_context: usize,
        generation_cache: &VersionMemo,
    ) -> Result<Vec<GrepMatch>> {
        let content = self
            .read_with_generation_cache(CacheOperation::Grep, path, 0, 0, generation_cache)
            .await?;
        let content_str = String::from_utf8_lossy(&content);
        let rel_file = relative_match_file(base_path, path);
        let mut result = GrepResult {
            matches: Vec::with_capacity(remaining_limit.min(64)),
            count: 0,
        };
        let mut collector = GrepLineCollector::new(
            rel_file.clone(),
            before_context,
            after_context,
            remaining_limit,
            &mut result,
        );

        for (line_index, line) in content_str.lines().enumerate() {
            let is_match = re.is_match(line);
            if !collector.consume_line(
                &rel_file,
                GrepContextLine {
                    line: (line_index + 1) as u64,
                    content: line.to_string(),
                },
                is_match,
            ) {
                break;
            }
        }

        drop(collector);
        Ok(result.matches)
    }

    async fn cache_get(&self, key: &str) -> CacheResult<Option<Bytes>> {
        let started = Instant::now();
        let result = self.runtime.get(key).await;
        self.metrics.get(started.elapsed());
        result
    }

    async fn cache_put(&self, key: &str, value: Bytes, affected_path: &str) -> bool {
        let started = Instant::now();
        let result = self.runtime.set(key, value, SetOptions::default()).await;
        self.metrics.put(started.elapsed());
        match result {
            Ok(SetResult::Applied) => true,
            Ok(SetResult::ConditionNotMet) => {
                self.metrics.error();
                self.mark_bypass(affected_path).await;
                false
            }
            Err(_) => {
                self.metrics.error();
                self.mark_bypass(affected_path).await;
                false
            }
        }
    }

    async fn cache_delete(&self, key: &str, affected_path: &str) {
        let started = Instant::now();
        let result = self.runtime.del(&[key.to_string()]).await;
        self.metrics.delete(started.elapsed());
        match result {
            Ok(_) => self.metrics.invalidation(),
            Err(_) => {
                self.metrics.error();
                self.mark_bypass(affected_path).await;
            }
        }
    }

    async fn mark_bypass(&self, path: &str) {
        let normalized = normalize_path(path);
        let mut scopes = self.bypass_scopes.write().await;
        if scopes
            .iter()
            .any(|scope| is_same_or_descendant(&normalized, scope))
        {
            return;
        }
        scopes.retain(|scope| !is_same_or_descendant(scope, &normalized));
        scopes.push(normalized);
    }

    async fn is_runtime_bypassed(&self, path: &str) -> bool {
        let normalized = normalize_path(path);
        self.bypass_scopes
            .read()
            .await
            .iter()
            .any(|scope| is_same_or_descendant(&normalized, scope))
    }

    /// Bump counters after a backend mutation so other instances stop
    /// trusting entries filled before it. Returns the bumps that failed; the
    /// caller hands them to [`Self::settle_bumps`] together with its lock.
    async fn bump_counters(&self, counters: &[(KeyKind, &str)]) -> PendingBumps {
        let mut pending = Vec::<(String, String)>::new();
        for (kind, path) in counters {
            let key = self.versions.key(*kind, path);
            if !pending.iter().any(|(existing, _)| existing == &key) {
                pending.push((key, normalize_path(path)));
            }
        }
        self.attempt_bumps(pending).await
    }

    async fn attempt_bumps(&self, pending: PendingBumps) -> PendingBumps {
        let results = join_all(pending.iter().map(|(key, _)| async move {
            let started = Instant::now();
            let result = self.versions.bump(key).await;
            self.metrics.put(started.elapsed());
            result
        }))
        .await;
        pending
            .into_iter()
            .zip(results)
            .filter_map(|(counter, result)| match result {
                Ok(()) => {
                    self.metrics.invalidation();
                    None
                }
                Err(_) => {
                    self.metrics.error();
                    Some(counter)
                }
            })
            .collect()
    }

    /// Retry failed bumps, then release the mutation's operation lock.
    ///
    /// The bump is the commit point for every instance sharing the namespace,
    /// so failed bumps are retried before this instance falls back to a local
    /// bypass. Other instances may then serve stale entries until their TTL.
    /// Atomic bumps do not need the lock, so it is released before the retry
    /// backoff instead of stalling every other operation in this process.
    async fn settle_bumps(&self, guard: RwLockWriteGuard<'_, ()>, mut pending: PendingBumps) {
        let _guard = if self.versions.atomic_bump() {
            drop(guard);
            None
        } else {
            Some(guard)
        };
        for delay in BUMP_RETRY_DELAYS {
            if pending.is_empty() {
                return;
            }
            tokio::time::sleep(delay).await;
            pending = self.attempt_bumps(pending).await;
        }
        for (key, path) in pending {
            self.metrics.invalidation_failure();
            tracing::error!(
                path = %path,
                key = %key,
                "CacheFS counter bump failed; other instances may serve stale \
                 entries for this path until the cache TTL expires"
            );
            self.mark_bypass(&path).await;
        }
    }

    /// Check an envelope's recorded counters. A mismatch against the traversal
    /// memo is re-checked against live counters: the memo may be older than
    /// an entry another instance filled after a bump.
    async fn validate(
        &self,
        envelope: &CacheEnvelope,
        memo: Option<&VersionMemo>,
    ) -> CacheResult<bool> {
        match self.versions.matches(envelope.versions(), memo).await {
            Ok(false) if memo.is_some() => self.versions.matches(envelope.versions(), None).await,
            result => result,
        }
    }

    /// Return a validated cached file, recording a hit for `record_hit` when set.
    async fn probe_file(
        &self,
        key: &str,
        path: &str,
        record_hit: Option<CacheOperation>,
    ) -> Option<Vec<u8>> {
        self.probe_file_with_generation_cache(key, path, record_hit, None)
            .await
    }

    async fn probe_file_with_generation_cache(
        &self,
        key: &str,
        path: &str,
        record_hit: Option<CacheOperation>,
        generation_cache: Option<&VersionMemo>,
    ) -> Option<Vec<u8>> {
        let value = match self.cache_get(key).await {
            Ok(value) => value?,
            Err(_) => {
                self.metrics.error();
                self.mark_bypass(path).await;
                return None;
            }
        };

        let envelope = match CacheEnvelope::decode(&value) {
            Ok(envelope) if envelope.matches(CacheObjectKind::File, path) => envelope,
            _ => {
                self.metrics.error();
                self.cache_delete(key, path).await;
                return None;
            }
        };

        match self.validate(&envelope, generation_cache).await {
            Ok(true) => match envelope.into_file() {
                Ok(data) => {
                    if let Some(operation) = record_hit {
                        self.metrics.file_hit(operation, data.len());
                    }
                    Some(data)
                }
                Err(_) => {
                    self.metrics.error();
                    self.cache_delete(key, path).await;
                    None
                }
            },
            Ok(false) => {
                self.metrics.stale_version();
                self.cache_delete(key, path).await;
                None
            }
            Err(_) => {
                self.metrics.error();
                self.mark_bypass(path).await;
                None
            }
        }
    }

    /// Return validated cached entries, recording a hit for `record_hit` when set.
    async fn probe_directory(
        &self,
        key: &str,
        path: &str,
        record_hit: Option<CacheOperation>,
    ) -> Option<Vec<FileInfo>> {
        self.probe_directory_with_generation_cache(key, path, record_hit, None)
            .await
    }

    async fn probe_directory_with_generation_cache(
        &self,
        key: &str,
        path: &str,
        record_hit: Option<CacheOperation>,
        generation_cache: Option<&VersionMemo>,
    ) -> Option<Vec<FileInfo>> {
        let value = match self.cache_get(key).await {
            Ok(value) => value?,
            Err(_) => {
                self.metrics.error();
                self.mark_bypass(path).await;
                return None;
            }
        };

        let envelope = match CacheEnvelope::decode(&value) {
            Ok(envelope) if envelope.matches(CacheObjectKind::Directory, path) => envelope,
            _ => {
                self.metrics.error();
                self.cache_delete(key, path).await;
                return None;
            }
        };

        match self.validate(&envelope, generation_cache).await {
            Ok(true) => match envelope.into_directory() {
                Ok(entries) => {
                    if !self.policy.cache_directory_entries(path, entries.len()) {
                        self.cache_delete(key, path).await;
                        return None;
                    }
                    if let Some(operation) = record_hit {
                        self.metrics.read_dir_hit(operation);
                    }
                    Some(entries)
                }
                Err(_) => {
                    self.metrics.error();
                    self.cache_delete(key, path).await;
                    None
                }
            },
            Ok(false) => {
                self.metrics.stale_version();
                self.cache_delete(key, path).await;
                None
            }
            Err(_) => {
                self.metrics.error();
                self.mark_bypass(path).await;
                None
            }
        }
    }

    async fn acquire_inflight(&self, key: &str) -> (Arc<Mutex<()>>, bool) {
        let mut inflight = self.inflight.lock().await;
        if let Some(lock) = inflight.get(key) {
            (Arc::clone(lock), false)
        } else {
            let lock = Arc::new(Mutex::new(()));
            inflight.insert(key.to_string(), Arc::clone(&lock));
            (lock, true)
        }
    }

    async fn release_inflight(&self, key: &str, lock: &Arc<Mutex<()>>) {
        let mut inflight = self.inflight.lock().await;
        if inflight
            .get(key)
            .is_some_and(|current| Arc::ptr_eq(current, lock) && Arc::strong_count(lock) == 2)
        {
            inflight.remove(key);
        }
    }

    async fn read_with_generation_cache(
        &self,
        operation: CacheOperation,
        path: &str,
        offset: u64,
        size: u64,
        generation_cache: &VersionMemo,
    ) -> Result<Vec<u8>> {
        if offset != 0
            || size != 0
            || !self.policy.cache_file(path, 0)
            || self.is_runtime_bypassed(path).await
        {
            self.metrics.policy_bypass(operation);
            return self.backend.read(path, offset, size).await;
        }

        let _operation_guard = self.operation_lock.read().await;
        if self.is_runtime_bypassed(path).await {
            self.metrics.policy_bypass(operation);
            return self.backend.read(path, offset, size).await;
        }

        let normalized = normalize_path(path);
        let key = self.file_key(&normalized);
        if let Some(data) = self
            .probe_file_with_generation_cache(
                &key,
                &normalized,
                Some(operation),
                Some(generation_cache),
            )
            .await
        {
            return Ok(data);
        }
        self.metrics.file_miss(operation);

        let (inflight, leader) = self.acquire_inflight(&key).await;
        if leader {
            self.metrics.inflight_leader();
        } else {
            self.metrics.inflight_follower();
        }
        let inflight_guard = inflight.lock().await;

        if !leader {
            if let Some(data) = self
                .probe_file_with_generation_cache(&key, &normalized, None, Some(generation_cache))
                .await
            {
                self.metrics.inflight_backend_saved();
                drop(inflight_guard);
                self.release_inflight(&key, &inflight).await;
                return Ok(data);
            }
        }

        // Snapshot before the backend read: a mutation that lands after it
        // bumps a recorded counter, so a late fill can never validate.
        // Snapshot live counters, not the traversal memo: a memoized value that
        // moved since the traversal started would make this fill stale for
        // every other reader the moment it is written.
        let versions = self.versions.snapshot(&normalized, None).await;
        let data = self.backend.read(path, 0, 0).await;
        if let Ok(value) = &data {
            self.metrics.backend_fallback(value.len());
            self.fill_file(&key, &normalized, value, versions).await;
        }
        drop(inflight_guard);
        self.release_inflight(&key, &inflight).await;
        data
    }

    async fn read_dir_with_generation_cache(
        &self,
        operation: CacheOperation,
        path: &str,
        generation_cache: &VersionMemo,
    ) -> Result<Vec<FileInfo>> {
        if !self.policy.cache_directory(path) || self.is_runtime_bypassed(path).await {
            self.metrics.policy_bypass(operation);
            return self.backend.read_dir(path, None, None, None, None).await;
        }

        let _operation_guard = self.operation_lock.read().await;
        if self.is_runtime_bypassed(path).await {
            self.metrics.policy_bypass(operation);
            return self.backend.read_dir(path, None, None, None, None).await;
        }

        let normalized = normalize_path(path);
        let key = self.directory_key(&normalized);
        if let Some(entries) = self
            .probe_directory_with_generation_cache(
                &key,
                &normalized,
                Some(operation),
                Some(generation_cache),
            )
            .await
        {
            return Ok(entries);
        }
        self.metrics.read_dir_miss(operation);

        let (inflight, leader) = self.acquire_inflight(&key).await;
        if leader {
            self.metrics.inflight_leader();
        } else {
            self.metrics.inflight_follower();
        }
        let inflight_guard = inflight.lock().await;

        if !leader {
            if let Some(entries) = self
                .probe_directory_with_generation_cache(
                    &key,
                    &normalized,
                    None,
                    Some(generation_cache),
                )
                .await
            {
                self.metrics.inflight_backend_saved();
                drop(inflight_guard);
                self.release_inflight(&key, &inflight).await;
                return Ok(entries);
            }
        }

        let versions = self.versions.snapshot(&normalized, None).await;
        let entries = self.backend.read_dir(path, None, None, None, None).await;
        if let Ok(value) = &entries {
            self.metrics.backend_fallback(0);
            self.fill_directory(&key, &normalized, value, versions)
                .await;
        }
        drop(inflight_guard);
        self.release_inflight(&key, &inflight).await;
        entries
    }

    /// Read a directory through the cache, attributing lookups to `operation`.
    async fn read_dir_for(
        &self,
        operation: CacheOperation,
        path: &str,
        offset: Option<usize>,
        limit: Option<usize>,
        sort_by: Option<ListSortBy>,
        sort_order: Option<SortOrder>,
    ) -> Result<Vec<FileInfo>> {
        if !self.policy.cache_directory(path) || self.is_runtime_bypassed(path).await {
            self.metrics.policy_bypass(operation);
            return self
                .backend
                .read_dir(path, offset, limit, sort_by, sort_order)
                .await;
        }

        let _operation_guard = self.operation_lock.read().await;
        if self.is_runtime_bypassed(path).await {
            self.metrics.policy_bypass(operation);
            return self
                .backend
                .read_dir(path, offset, limit, sort_by, sort_order)
                .await;
        }

        let normalized = normalize_path(path);
        let key = self.directory_key(&normalized);
        if let Some(entries) = self
            .probe_directory(&key, &normalized, Some(operation))
            .await
        {
            return Ok(apply_read_dir_options(
                entries, offset, limit, sort_by, sort_order,
            ));
        }
        self.metrics.read_dir_miss(operation);

        let (inflight, leader) = self.acquire_inflight(&key).await;
        if leader {
            self.metrics.inflight_leader();
        } else {
            self.metrics.inflight_follower();
        }
        let inflight_guard = inflight.lock().await;

        if !leader {
            if let Some(entries) = self.probe_directory(&key, &normalized, None).await {
                self.metrics.inflight_backend_saved();
                drop(inflight_guard);
                self.release_inflight(&key, &inflight).await;
                return Ok(apply_read_dir_options(
                    entries, offset, limit, sort_by, sort_order,
                ));
            }
        }

        let versions = self.versions.snapshot(&normalized, None).await;
        let entries = self.backend.read_dir(path, None, None, None, None).await;
        if let Ok(value) = &entries {
            self.metrics.backend_fallback(0);
            self.fill_directory(&key, &normalized, value, versions)
                .await;
        }
        drop(inflight_guard);
        self.release_inflight(&key, &inflight).await;
        entries.map(|entries| apply_read_dir_options(entries, offset, limit, sort_by, sort_order))
    }

    /// Store `data` with the counter snapshot taken before it was read.
    async fn fill_file(
        &self,
        key: &str,
        path: &str,
        data: &[u8],
        versions: CacheResult<Vec<VersionSnapshot>>,
    ) {
        if !self.policy.cache_file(path, data.len()) {
            return;
        }
        let Ok(versions) = versions else {
            self.metrics.error();
            return;
        };
        match CacheEnvelope::file(path.to_string(), data.to_vec(), versions).encode() {
            Ok(value) => {
                self.cache_put(key, value, path).await;
            }
            Err(_) => self.metrics.error(),
        }
    }

    /// Store raw entries with the counter snapshot taken before they were read.
    async fn fill_directory(
        &self,
        key: &str,
        path: &str,
        entries: &[FileInfo],
        versions: CacheResult<Vec<VersionSnapshot>>,
    ) {
        if !self.policy.cache_directory_entries(path, entries.len()) {
            return;
        }
        let Ok(versions) = versions else {
            self.metrics.error();
            return;
        };
        match CacheEnvelope::directory(path.to_string(), entries.to_vec(), versions).encode() {
            Ok(value) => {
                self.cache_put(key, value, path).await;
            }
            Err(_) => self.metrics.error(),
        }
    }

    /// Bump counters for a change to the object at `path` (content, mode, or
    /// existence) so its own entries and its parent listing stop matching.
    async fn bump_object(&self, path: &str) -> PendingBumps {
        let parent = parent_path(path);
        self.bump_counters(&[(KeyKind::Object, path), (KeyKind::Object, &parent)])
            .await
    }

    /// Bump counters for a change that can affect everything below `path`.
    async fn bump_subtree(&self, path: &str) -> PendingBumps {
        let parent = parent_path(path);
        self.bump_counters(&[
            (KeyKind::Subtree, path),
            (KeyKind::Object, path),
            (KeyKind::Object, &parent),
        ])
        .await
    }

    /// Bump counters for a move of `from` onto `to`.
    async fn bump_move(&self, from: &str, to: &str) -> PendingBumps {
        let (from_parent, to_parent) = (parent_path(from), parent_path(to));
        self.bump_counters(&[
            (KeyKind::Subtree, from),
            (KeyKind::Subtree, to),
            (KeyKind::Object, from),
            (KeyKind::Object, to),
            (KeyKind::Object, &from_parent),
            (KeyKind::Object, &to_parent),
        ])
        .await
    }

    async fn invalidate_path_objects(&self, path: &str) {
        self.cache_delete(&self.file_key(path), path).await;
        self.cache_delete(&self.directory_key(path), path).await;
    }

    async fn invalidate_parent_directory(&self, path: &str) {
        let parent = parent_path(path);
        self.cache_delete(&self.directory_key(&parent), &parent)
            .await;
    }

    fn file_key(&self, path: &str) -> String {
        self.versions.key(KeyKind::File, path)
    }

    fn directory_key(&self, path: &str) -> String {
        self.versions.key(KeyKind::Directory, path)
    }

    #[cfg(test)]
    pub(super) fn generation_key(&self, path: &str) -> String {
        self.versions.key(KeyKind::Subtree, path)
    }
}

#[async_trait]
impl FileSystem for CachedFileSystem {
    async fn create(&self, path: &str) -> Result<()> {
        let guard = self.operation_lock.write().await;
        self.backend.create(path).await?;
        let pending = self.bump_object(path).await;
        self.invalidate_path_objects(path).await;
        self.invalidate_parent_directory(path).await;
        self.settle_bumps(guard, pending).await;
        Ok(())
    }

    async fn mkdir(&self, path: &str, mode: u32) -> Result<()> {
        let guard = self.operation_lock.write().await;
        self.backend.mkdir(path, mode).await?;
        let pending = self.bump_subtree(path).await;
        self.cache_delete(&self.directory_key(path), path).await;
        self.invalidate_parent_directory(path).await;
        self.settle_bumps(guard, pending).await;
        Ok(())
    }

    async fn remove(&self, path: &str) -> Result<()> {
        let guard = self.operation_lock.write().await;
        self.backend.remove(path).await?;
        let pending = self.bump_subtree(path).await;
        self.invalidate_path_objects(path).await;
        self.invalidate_parent_directory(path).await;
        self.settle_bumps(guard, pending).await;
        Ok(())
    }

    async fn remove_all(&self, path: &str) -> Result<()> {
        let guard = self.operation_lock.write().await;
        let result = self.backend.remove_all(path).await;
        // Recursive deletion is not transactional: a backend can remove part of
        // the subtree before reporting an error. Invalidate conservatively so
        // provider-backed caches cannot continue serving deleted objects.
        let pending = self.bump_subtree(path).await;
        self.invalidate_path_objects(path).await;
        self.invalidate_parent_directory(path).await;
        self.settle_bumps(guard, pending).await;
        result
    }

    async fn read(&self, path: &str, offset: u64, size: u64) -> Result<Vec<u8>> {
        if offset != 0
            || size != 0
            || !self.policy.cache_file(path, 0)
            || self.is_runtime_bypassed(path).await
        {
            self.metrics.policy_bypass(CacheOperation::Read);
            return self.backend.read(path, offset, size).await;
        }

        let _operation_guard = self.operation_lock.read().await;
        if self.is_runtime_bypassed(path).await {
            self.metrics.policy_bypass(CacheOperation::Read);
            return self.backend.read(path, offset, size).await;
        }

        let normalized = normalize_path(path);
        let key = self.file_key(&normalized);
        if let Some(data) = self
            .probe_file(&key, &normalized, Some(CacheOperation::Read))
            .await
        {
            return Ok(data);
        }
        self.metrics.file_miss(CacheOperation::Read);

        let (inflight, leader) = self.acquire_inflight(&key).await;
        if leader {
            self.metrics.inflight_leader();
        } else {
            self.metrics.inflight_follower();
        }
        let inflight_guard = inflight.lock().await;

        if !leader {
            if let Some(data) = self.probe_file(&key, &normalized, None).await {
                self.metrics.inflight_backend_saved();
                drop(inflight_guard);
                self.release_inflight(&key, &inflight).await;
                return Ok(data);
            }
        }

        let versions = self.versions.snapshot(&normalized, None).await;
        let data = self.backend.read(path, 0, 0).await;
        if let Ok(value) = &data {
            self.metrics.backend_fallback(value.len());
            self.fill_file(&key, &normalized, value, versions).await;
        }
        drop(inflight_guard);
        self.release_inflight(&key, &inflight).await;
        data
    }

    async fn write(&self, path: &str, data: &[u8], offset: u64, flags: WriteFlag) -> Result<u64> {
        let guard = self.operation_lock.write().await;
        let written = self.backend.write(path, data, offset, flags).await?;
        let normalized = normalize_path(path);
        let key = self.file_key(&normalized);
        let pending = self.bump_object(&normalized).await;
        self.cache_delete(&key, &normalized).await;
        // Across processes a concurrent writer's fill can land after a newer
        // backend write, so multi-instance mode leaves filling to the next read.
        if !self.policy.multi_instance()
            && pending.is_empty()
            && offset == 0
            && matches!(
                flags,
                WriteFlag::Create | WriteFlag::CreateNew | WriteFlag::Truncate
            )
            && self.policy.cache_file(&normalized, data.len())
            && !self.is_runtime_bypassed(&normalized).await
        {
            // The operation lock serializes this process's writers, so a
            // snapshot taken after this write's own bump is current.
            let versions = self.versions.snapshot(&normalized, None).await;
            self.fill_file(&key, &normalized, data, versions).await;
        }
        self.invalidate_parent_directory(path).await;
        self.settle_bumps(guard, pending).await;
        Ok(written)
    }

    /// Stream `src` to the backend, then invalidate like `write`.
    ///
    /// The bytes are never in memory here, so the file cache is not refilled;
    /// the next full read misses and fills it.
    async fn write_from_path(&self, path: &str, src: &Path, flags: WriteFlag) -> Result<u64> {
        let guard = self.operation_lock.write().await;
        let written = self.backend.write_from_path(path, src, flags).await?;
        let normalized = normalize_path(path);
        let key = self.file_key(&normalized);
        let pending = self.bump_object(&normalized).await;
        self.cache_delete(&key, &normalized).await;
        self.invalidate_parent_directory(path).await;
        self.settle_bumps(guard, pending).await;
        Ok(written)
    }

    /// Stream from the backend, bypassing the file cache like ranged reads do.
    async fn read_to_path(&self, path: &str, dst: &Path) -> Result<u64> {
        self.metrics.policy_bypass(CacheOperation::Read);
        self.backend.read_to_path(path, dst).await
    }

    async fn read_dir(
        &self,
        path: &str,
        offset: Option<usize>,
        limit: Option<usize>,
        sort_by: Option<ListSortBy>,
        sort_order: Option<SortOrder>,
    ) -> Result<Vec<FileInfo>> {
        self.read_dir_for(
            CacheOperation::ReadDir,
            path,
            offset,
            limit,
            sort_by,
            sort_order,
        )
        .await
    }

    async fn stat(&self, path: &str) -> Result<FileInfo> {
        self.backend.stat(path).await
    }

    async fn rename(&self, old_path: &str, new_path: &str) -> Result<()> {
        let guard = self.operation_lock.write().await;
        self.backend.rename(old_path, new_path).await?;
        let pending = self.bump_move(old_path, new_path).await;
        self.invalidate_path_objects(old_path).await;
        self.invalidate_path_objects(new_path).await;
        self.invalidate_parent_directory(old_path).await;
        self.invalidate_parent_directory(new_path).await;
        self.settle_bumps(guard, pending).await;
        Ok(())
    }

    async fn replace(&self, src_path: &str, dst_path: &str) -> Result<()> {
        let guard = self.operation_lock.write().await;
        self.backend.replace(src_path, dst_path).await?;
        let pending = self.bump_move(src_path, dst_path).await;
        self.invalidate_path_objects(src_path).await;
        self.invalidate_path_objects(dst_path).await;
        self.invalidate_parent_directory(src_path).await;
        self.invalidate_parent_directory(dst_path).await;
        self.settle_bumps(guard, pending).await;
        Ok(())
    }

    async fn chmod(&self, path: &str, mode: u32) -> Result<()> {
        let guard = self.operation_lock.write().await;
        self.backend.chmod(path, mode).await?;
        let pending = self.bump_object(path).await;
        self.invalidate_path_objects(path).await;
        self.invalidate_parent_directory(path).await;
        self.settle_bumps(guard, pending).await;
        Ok(())
    }

    async fn truncate(&self, path: &str, size: u64) -> Result<()> {
        let guard = self.operation_lock.write().await;
        self.backend.truncate(path, size).await?;
        let pending = self.bump_object(path).await;
        self.cache_delete(&self.file_key(path), path).await;
        self.invalidate_parent_directory(path).await;
        self.settle_bumps(guard, pending).await;
        Ok(())
    }

    async fn exists(&self, path: &str) -> bool {
        self.backend.exists(path).await
    }

    async fn ensure_parent_dirs(&self, path: &str, mode: u32) -> Result<()> {
        let guard = self.operation_lock.write().await;
        self.backend.ensure_parent_dirs(path, mode).await?;
        let scopes = ancestor_scopes(&parent_path(path));
        let counters = scopes
            .iter()
            .map(|scope| (KeyKind::Object, scope.as_str()))
            .collect::<Vec<_>>();
        let pending = self.bump_counters(&counters).await;
        for scope in &scopes {
            self.cache_delete(&self.directory_key(scope), scope).await;
        }
        self.settle_bumps(guard, pending).await;
        Ok(())
    }

    async fn grep(
        &self,
        path: &str,
        pattern: &str,
        options: GrepOptions<'_>,
    ) -> Result<GrepResult> {
        if self.policy.traversal_mode() == CacheTraversalMode::CachedTraversal
            && !self.wraps_multiwrite()
        {
            return self.grep_via_cache(path, pattern, options).await;
        }

        self.backend.grep(path, pattern, options).await
    }

    async fn tree_directory(
        &self,
        path: &str,
        show_hidden: bool,
        node_limit: Option<usize>,
        level_limit: Option<usize>,
        offset: Option<usize>,
        sort_by: Option<ListSortBy>,
        sort_order: Option<SortOrder>,
        directories_only: bool,
    ) -> Result<Vec<TreeEntry>> {
        if self.policy.traversal_mode() == CacheTraversalMode::CachedTraversal
            && !self.wraps_multiwrite()
        {
            return self
                .tree_directory_via_cache(
                    path,
                    show_hidden,
                    node_limit,
                    level_limit,
                    offset,
                    sort_by,
                    sort_order,
                    directories_only,
                )
                .await;
        }

        self.backend
            .tree_directory(
                path,
                show_hidden,
                node_limit,
                level_limit,
                offset,
                sort_by,
                sort_order,
                directories_only,
            )
            .await
    }

    async fn glob_directory(
        &self,
        path: &str,
        pattern: &str,
        show_hidden: bool,
        page_size: Option<usize>,
        level_limit: Option<usize>,
        continuation_token: Option<String>,
    ) -> Result<GlobPage> {
        self.backend
            .glob_directory(
                path,
                pattern,
                show_hidden,
                page_size,
                level_limit,
                continuation_token,
            )
            .await
    }
}

fn parent_path(path: &str) -> String {
    let normalized = normalize_path(path);
    if normalized == "/" {
        return "/".to_string();
    }
    normalized
        .rsplit_once('/')
        .map(|(parent, _)| {
            if parent.is_empty() {
                "/".to_string()
            } else {
                parent.to_string()
            }
        })
        .unwrap_or_else(|| "/".to_string())
}

fn is_same_or_descendant(path: &str, scope: &str) -> bool {
    scope == "/"
        || path == scope
        || path
            .strip_prefix(scope)
            .is_some_and(|suffix| suffix.starts_with('/'))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cache::CacheOperationSnapshot;
    use crate::plugins::memfs::MemFileSystem;

    async fn cached_memfs(mode: CacheTraversalMode) -> CachedFileSystem {
        let backend = MemFileSystem::new();
        backend.mkdir("/docs", 0o755).await.unwrap();
        backend
            .write("/docs/a.md", b"alpha\nbeta\n", 0, WriteFlag::Create)
            .await
            .unwrap();
        CachedFileSystem::with_runtime(
            Box::new(backend),
            CacheRuntime::memory(),
            "operation-metrics-test",
            CachePolicy::default().with_traversal_mode(mode),
        )
    }

    fn counts(hits: u64, misses: u64, bypasses: u64) -> CacheOperationSnapshot {
        CacheOperationSnapshot {
            hits,
            misses,
            bypasses,
        }
    }

    #[tokio::test]
    async fn cached_traversal_attributes_lookups_to_tree_and_grep() {
        let fs = cached_memfs(CacheTraversalMode::CachedTraversal).await;

        fs.tree_directory("/docs", false, None, None, None, None, None, false)
            .await
            .unwrap();
        fs.tree_directory("/docs", false, None, None, None, None, None, false)
            .await
            .unwrap();
        let options = GrepOptions {
            recursive: true,
            ..GrepOptions::default()
        };
        fs.grep("/docs", "beta", options).await.unwrap();
        fs.read_dir("/docs", None, None, None, None).await.unwrap();

        let snapshot = fs.metrics().snapshot();
        assert_eq!(snapshot.operation(CacheOperation::Tree), counts(1, 1, 0));
        // The directory was filled by `tree`; the file is read for the first time.
        assert_eq!(snapshot.operation(CacheOperation::Grep), counts(1, 1, 0));
        assert_eq!(snapshot.operation(CacheOperation::ReadDir), counts(1, 0, 0));
        assert_eq!(snapshot.operation(CacheOperation::Read), counts(0, 0, 0));
        assert_eq!(snapshot.read_dir_hits, 3);
        assert_eq!(snapshot.file_misses, 1);
    }

    /// A traversal memo older than a bump must not reject (and delete) an
    /// entry that was filled after the bump with the current counter values.
    #[tokio::test]
    async fn stale_traversal_memo_keeps_a_fresh_entry() {
        let fs = cached_memfs(CacheTraversalMode::CachedTraversal).await;
        assert_eq!(fs.read("/docs/a.md", 0, 0).await.unwrap(), b"alpha\nbeta\n");

        let memo = VersionMemo::default();
        let key = fs.generation_key("/docs");
        let live = fs.versions.snapshot("/docs/a.md", None).await.unwrap();
        let current = live
            .iter()
            .find(|snapshot| snapshot.key == key)
            .unwrap()
            .value;
        memo.lock().await.insert(key, current - 1);

        let data = fs
            .read_with_generation_cache(CacheOperation::Grep, "/docs/a.md", 0, 0, &memo)
            .await
            .unwrap();
        assert_eq!(data, b"alpha\nbeta\n");
        let snapshot = fs.metrics().snapshot();
        assert_eq!(snapshot.operation(CacheOperation::Grep), counts(1, 0, 0));
        assert_eq!(snapshot.stale_versions, 0);
    }

    /// A generation key that expires (or is evicted) must never be restored to an
    /// old value: a later bump would then reproduce a generation some surviving
    /// cache entry already recorded, and that entry would validate again.
    #[tokio::test]
    async fn lost_generation_key_never_revalidates_deleted_subtree() {
        use crate::core::mountable::ArcFileSystem;

        let backend: Arc<dyn FileSystem> = Arc::new(MemFileSystem::new());
        backend.mkdir("/p", 0o755).await.unwrap();
        backend
            .write("/p/x", b"v1", 0, WriteFlag::Create)
            .await
            .unwrap();
        backend
            .write("/p/y", b"y", 0, WriteFlag::Create)
            .await
            .unwrap();
        let runtime = CacheRuntime::memory();
        let instance = || {
            CachedFileSystem::with_runtime(
                Box::new(ArcFileSystem(backend.clone())),
                runtime.clone(),
                "generation-loss-test",
                CachePolicy::default(),
            )
        };
        let (a, b, c) = (instance(), instance(), instance());

        // C remembers the current generation of /p.
        c.read("/p/x", 0, 0).await.unwrap();
        // A deletes the subtree (one bump of /p); it is recreated without further
        // bumps, and B caches the new content under the bumped generation.
        a.remove_all("/p").await.unwrap();
        backend.mkdir("/p", 0o755).await.unwrap();
        backend
            .write("/p/x", b"v2", 0, WriteFlag::Create)
            .await
            .unwrap();
        backend
            .write("/p/y", b"y", 0, WriteFlag::Create)
            .await
            .unwrap();
        assert_eq!(b.read("/p/x", 0, 0).await.unwrap(), b"v2");

        // The /p generation key expires while B's entry for /p/x survives.
        runtime.del(&[c.generation_key("/p")]).await.unwrap();
        // C touches the subtree again, then A deletes it.
        c.read("/p/y", 0, 0).await.unwrap();
        a.remove_all("/p").await.unwrap();

        assert!(
            matches!(
                b.read("/p/x", 0, 0).await,
                Err(crate::core::Error::NotFound(_))
            ),
            "B must not serve content deleted after the generation key was lost"
        );
    }
}
