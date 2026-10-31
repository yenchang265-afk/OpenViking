//! Shared version counters that keep cache entries valid across instances.
//!
//! Every cached path has an object version (`ver`), and every directory scope
//! has a subtree generation (`subtree`). A cache envelope records the values
//! of its own object version and of every ancestor subtree generation,
//! snapshotted *before* the backend read that produced it. Mutations bump the
//! affected counters *after* the backend change, so any envelope whose
//! backend read could have missed that change no longer matches.

use crate::cache_runtime::{
    CacheError, CacheOperation, CacheResult, CacheRuntime, SetCondition, SetOptions, SetResult,
};
use bytes::Bytes;
use futures::future::join_all;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::Mutex;
use uuid::Uuid;

const KEY_LAYOUT_VERSION: &str = "v2";
const INIT_ATTEMPTS: usize = 3;
/// Every live counter starts at or above this value. A smaller value means
/// INCRBY recreated a lost key, so the bump re-bases it to a random value.
const MIN_BASE: i64 = 1 << 40;

/// Counter values already read during one traversal, keyed by counter key.
pub(super) type VersionMemo = Mutex<HashMap<String, i64>>;

/// One counter value recorded in a cache envelope.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub(crate) struct VersionSnapshot {
    pub key: String,
    pub value: i64,
}

/// Kinds of keys stored under one CacheFS namespace.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) enum KeyKind {
    File,
    Directory,
    Subtree,
    Object,
}

impl KeyKind {
    fn segment(self) -> &'static str {
        match self {
            Self::File => "file",
            Self::Directory => "dir",
            Self::Subtree => "subtree",
            Self::Object => "ver",
        }
    }
}

/// Key layout and counter operations for one CacheFS namespace.
pub(super) struct VersionStore {
    runtime: Arc<CacheRuntime>,
    service_name: String,
    atomic_bump: bool,
}

impl VersionStore {
    /// Use `INCRBY` for bumps when the provider supports it.
    pub fn new(runtime: Arc<CacheRuntime>, service_name: String) -> Self {
        let atomic_bump = runtime
            .require_operations(&[CacheOperation::IncrBy])
            .is_ok();
        Self {
            runtime,
            service_name,
            atomic_bump,
        }
    }

    /// Return whether bumps use atomic INCRBY (safe across processes).
    pub fn atomic_bump(&self) -> bool {
        self.atomic_bump
    }

    /// Return the provider key for one object kind and path.
    pub fn key(&self, kind: KeyKind, path: &str) -> String {
        let normalized = normalize_path(path);
        format!(
            "{}:ov:cache:{}:{}:{:016x}",
            self.service_name,
            KEY_LAYOUT_VERSION,
            kind.segment(),
            stable_hash(normalized.as_bytes())
        )
    }

    /// Counter keys an envelope for `path` must record: the subtree
    /// generation of every strict ancestor and the object version of `path`.
    ///
    /// `subtree(path)` itself is not needed: every operation that bumps it
    /// (mkdir, remove, remove_all, rename, replace) also bumps `ver(path)`.
    pub fn snapshot_keys(&self, path: &str) -> Vec<String> {
        let mut scopes = ancestor_scopes(path);
        scopes.pop();
        scopes
            .iter()
            .map(|scope| self.key(KeyKind::Subtree, scope))
            .chain(std::iter::once(self.key(KeyKind::Object, path)))
            .collect()
    }

    /// Read the counters an envelope for `path` must record.
    pub async fn snapshot(
        &self,
        path: &str,
        memo: Option<&VersionMemo>,
    ) -> CacheResult<Vec<VersionSnapshot>> {
        let keys = self.snapshot_keys(path);
        let values = self.current(&keys, memo).await?;
        Ok(keys
            .into_iter()
            .zip(values)
            .map(|(key, value)| VersionSnapshot { key, value })
            .collect())
    }

    /// Return whether every recorded counter still has its recorded value.
    pub async fn matches(
        &self,
        snapshots: &[VersionSnapshot],
        memo: Option<&VersionMemo>,
    ) -> CacheResult<bool> {
        let keys = snapshots
            .iter()
            .map(|snapshot| snapshot.key.clone())
            .collect::<Vec<_>>();
        let values = self.current(&keys, memo).await?;
        Ok(snapshots
            .iter()
            .zip(values)
            .all(|(snapshot, value)| snapshot.value == value))
    }

    /// Advance one counter so every envelope that recorded it stops matching.
    pub async fn bump(&self, key: &str) -> CacheResult<()> {
        if !self.atomic_bump {
            // Without INCRBY the bump is GET+SET; it is only safe while one
            // process uses the namespace (its operation lock serializes bumps).
            let current = self.current(&[key.to_string()], None).await?[0];
            return self
                .store(key, current.wrapping_add(1), SetCondition::None)
                .await
                .map(|_| ());
        }
        // Live counters start at MIN_BASE or above, so a smaller INCRBY result
        // means the key was just recreated from nothing. Re-base it to a fresh
        // random value: a small value could collide with one a surviving
        // envelope recorded before the key was lost. Checking `< MIN_BASE`
        // rather than `== 1` still re-bases when a retry follows a lost reply
        // or a failed re-base. Overwriting is safe because any value written
        // in between is replaced by a value nobody recorded.
        if self.runtime.incr_by(key, 1).await? < MIN_BASE {
            self.store(key, random_counter(), SetCondition::None)
                .await?;
        }
        Ok(())
    }

    /// Read counters, initializing missing ones to a value all instances agree on.
    async fn current(&self, keys: &[String], memo: Option<&VersionMemo>) -> CacheResult<Vec<i64>> {
        let mut values = vec![None; keys.len()];
        if let Some(memo) = memo {
            let memo = memo.lock().await;
            for (slot, key) in values.iter_mut().zip(keys) {
                *slot = memo.get(key).copied();
            }
        }

        let missing = keys
            .iter()
            .zip(&values)
            .filter(|(_, value)| value.is_none())
            .map(|(key, _)| key.clone())
            .collect::<Vec<_>>();
        if !missing.is_empty() {
            let fetched = self.fetch(&missing).await?;
            let mut fetched = missing.into_iter().zip(fetched).collect::<HashMap<_, _>>();
            for (slot, key) in values.iter_mut().zip(keys) {
                if slot.is_none() {
                    *slot = fetched.remove(key);
                }
            }
            if let Some(memo) = memo {
                let mut memo = memo.lock().await;
                for (key, value) in keys.iter().zip(&values) {
                    if let Some(value) = value {
                        memo.entry(key.clone()).or_insert(*value);
                    }
                }
            }
        }

        values
            .into_iter()
            .map(|value| value.ok_or_else(|| CacheError::Internal("missing counter".into())))
            .collect()
    }

    async fn fetch(&self, keys: &[String]) -> CacheResult<Vec<i64>> {
        let raw = if keys.len() == 1 {
            vec![self.runtime.get(&keys[0]).await?]
        } else {
            self.runtime.mget(keys).await?
        };
        if raw.len() != keys.len() {
            return Err(CacheError::InvalidData(format!(
                "batch_get returned {} values for {} keys",
                raw.len(),
                keys.len()
            )));
        }

        join_all(keys.iter().zip(raw).map(|(key, value)| async move {
            match value {
                Some(value) => decode_counter(key, &value),
                None => self.initialize(key).await,
            }
        }))
        .await
        .into_iter()
        .collect()
    }

    /// Store a random base with SET NX, or adopt the value another instance won with.
    async fn initialize(&self, key: &str) -> CacheResult<i64> {
        for _ in 0..INIT_ATTEMPTS {
            let candidate = random_counter();
            if self.store(key, candidate, SetCondition::Nx).await? == SetResult::Applied {
                return Ok(candidate);
            }
            if let Some(value) = self.runtime.get(key).await? {
                return decode_counter(key, &value);
            }
            // The winner's key expired before we read it; try again.
        }
        Err(CacheError::Internal(format!(
            "counter {key} could not be initialized"
        )))
    }

    async fn store(
        &self,
        key: &str,
        value: i64,
        condition: SetCondition,
    ) -> CacheResult<SetResult> {
        self.runtime
            .set(
                key,
                Bytes::from(value.to_string()),
                SetOptions {
                    condition,
                    ..SetOptions::default()
                },
            )
            .await
    }
}

fn decode_counter(key: &str, value: &[u8]) -> CacheResult<i64> {
    std::str::from_utf8(value)
        .ok()
        .and_then(|text| text.parse::<i64>().ok())
        .ok_or_else(|| CacheError::InvalidData(format!("counter {key} is not a decimal integer")))
}

/// Random base in `[MIN_BASE, 2^62)`, far below `i64::MAX` so INCRBY never
/// overflows in practice.
fn random_counter() -> i64 {
    let value = ((Uuid::new_v4().as_u128() as u64) >> 2) as i64;
    value.max(MIN_BASE)
}

pub(super) fn normalize_path(path: &str) -> String {
    if path.is_empty() || path == "/" {
        "/".to_string()
    } else {
        format!("/{}", path.trim_matches('/'))
    }
}

pub(super) fn ancestor_scopes(path: &str) -> Vec<String> {
    let normalized = normalize_path(path);
    if normalized == "/" {
        return vec!["/".to_string()];
    }

    let mut scopes = vec!["/".to_string()];
    let mut current = String::new();
    for component in normalized.trim_start_matches('/').split('/') {
        current.push('/');
        current.push_str(component);
        scopes.push(current.clone());
    }
    scopes
}

fn stable_hash(bytes: &[u8]) -> u64 {
    let mut hash = 0xcbf29ce484222325_u64;
    for byte in bytes {
        hash ^= u64::from(*byte);
        hash = hash.wrapping_mul(0x100000001b3);
    }
    hash
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cache_runtime::MemoryMockProvider;
    use std::time::Duration;

    fn store_with(provider: MemoryMockProvider) -> (VersionStore, Arc<CacheRuntime>) {
        let runtime = CacheRuntime::memory_with_provider(Arc::new(provider));
        (
            VersionStore::new(Arc::clone(&runtime), "svc".to_string()),
            runtime,
        )
    }

    #[test]
    fn keys_use_v2_layout_and_normalized_paths() {
        let (store, _) = store_with(MemoryMockProvider::new());
        let key = store.key(KeyKind::Object, "a/b/");
        assert!(key.starts_with("svc:ov:cache:v2:ver:"), "{key}");
        assert_eq!(key, store.key(KeyKind::Object, "/a/b"));
        assert_ne!(key, store.key(KeyKind::Subtree, "/a/b"));
    }

    #[test]
    fn snapshot_keys_cover_strict_ancestors_and_object() {
        let (store, _) = store_with(MemoryMockProvider::new());
        assert_eq!(
            store.snapshot_keys("/a/b"),
            vec![
                store.key(KeyKind::Subtree, "/"),
                store.key(KeyKind::Subtree, "/a"),
                store.key(KeyKind::Object, "/a/b"),
            ]
        );
        assert_eq!(
            store.snapshot_keys("/"),
            vec![store.key(KeyKind::Object, "/")]
        );
    }

    #[tokio::test]
    async fn counters_are_stored_as_decimal_text() {
        let (store, runtime) = store_with(MemoryMockProvider::new());
        let key = store.key(KeyKind::Object, "/f");
        let snapshot = store.snapshot("/f", None).await.unwrap();
        let raw = runtime.get(&key).await.unwrap().unwrap();
        let recorded = snapshot.iter().find(|s| s.key == key).unwrap().value;
        assert_eq!(std::str::from_utf8(&raw).unwrap(), recorded.to_string());
        assert!(recorded > 0);
    }

    #[tokio::test]
    async fn bump_invalidates_recorded_snapshot() {
        let (store, _) = store_with(MemoryMockProvider::new());
        let snapshot = store.snapshot("/d/f", None).await.unwrap();
        assert!(store.matches(&snapshot, None).await.unwrap());
        store
            .bump(&store.key(KeyKind::Subtree, "/d"))
            .await
            .unwrap();
        assert!(!store.matches(&snapshot, None).await.unwrap());
    }

    #[tokio::test]
    async fn bump_of_missing_key_starts_from_random_base() {
        let (store, runtime) = store_with(MemoryMockProvider::new());
        let key = store.key(KeyKind::Object, "/f");
        store.bump(&key).await.unwrap();
        let raw = runtime.get(&key).await.unwrap().unwrap();
        let value = decode_counter(&key, &raw).unwrap();
        assert!(value >= MIN_BASE, "bump must not restart the counter at 1");
    }

    #[tokio::test]
    async fn bump_retry_rebases_after_a_failed_rebase() {
        let provider = Arc::new(MemoryMockProvider::new());
        let runtime = CacheRuntime::memory_with_provider(Arc::clone(&provider));
        let store = VersionStore::new(Arc::clone(&runtime), "svc".to_string());
        let key = store.key(KeyKind::Object, "/f");

        provider.fail_next_set_matching(":ver:");
        assert!(store.bump(&key).await.is_err(), "re-base SET failed");
        // The retry sees 2, not 1, and must still re-base.
        store.bump(&key).await.unwrap();
        let value = decode_counter(&key, &runtime.get(&key).await.unwrap().unwrap()).unwrap();
        assert!(
            value >= MIN_BASE,
            "retried bump left a small counter: {value}"
        );
    }

    #[tokio::test]
    async fn concurrent_bumps_are_atomic() {
        let (store, runtime) =
            store_with(MemoryMockProvider::new().with_set_delay(Duration::from_millis(10)));
        let key = store.key(KeyKind::Subtree, "/d");
        let before = store
            .current(std::slice::from_ref(&key), None)
            .await
            .unwrap()[0];
        let (first, second) = tokio::join!(store.bump(&key), store.bump(&key));
        first.unwrap();
        second.unwrap();
        let after = decode_counter(&key, &runtime.get(&key).await.unwrap().unwrap()).unwrap();
        assert_eq!(after - before, 2);
    }

    #[tokio::test]
    async fn bump_falls_back_to_get_and_set_without_incr_by() {
        let (store, runtime) = store_with(MemoryMockProvider::new().without_incr_by());
        assert!(!store.atomic_bump);
        let key = store.key(KeyKind::Object, "/f");
        let before = store
            .current(std::slice::from_ref(&key), None)
            .await
            .unwrap()[0];
        store.bump(&key).await.unwrap();
        let after = decode_counter(&key, &runtime.get(&key).await.unwrap().unwrap()).unwrap();
        assert_eq!(after, before + 1);
    }

    #[tokio::test]
    async fn concurrent_initializers_agree() {
        let provider =
            Arc::new(MemoryMockProvider::new().with_set_delay(Duration::from_millis(10)));
        let runtime = CacheRuntime::memory_with_provider(provider);
        let a = VersionStore::new(Arc::clone(&runtime), "svc".to_string());
        let b = VersionStore::new(Arc::clone(&runtime), "svc".to_string());
        let (left, right) = tokio::join!(a.snapshot("/d/f", None), b.snapshot("/d/g", None));
        let (left, right) = (left.unwrap(), right.unwrap());
        // Both snapshots share the `/` and `/d` subtree counters.
        assert_eq!(left[..2], right[..2]);
        assert!(left.iter().all(|snapshot| snapshot.value >= MIN_BASE));
    }

    #[tokio::test]
    async fn memo_reuses_values_within_one_traversal() {
        let (store, runtime) = store_with(MemoryMockProvider::new());
        let memo = VersionMemo::default();
        let first = store.snapshot("/d/f", Some(&memo)).await.unwrap();
        store
            .bump(&store.key(KeyKind::Subtree, "/d"))
            .await
            .unwrap();
        let second = store.snapshot("/d/f", Some(&memo)).await.unwrap();
        assert_eq!(
            first, second,
            "memoized values are stable during a traversal"
        );
        let fresh = store.snapshot("/d/f", None).await.unwrap();
        assert_ne!(first, fresh);
        drop(runtime);
    }

    #[tokio::test]
    async fn invalid_counter_values_are_rejected() {
        let (store, runtime) = store_with(MemoryMockProvider::new());
        let key = store.key(KeyKind::Object, "/f");
        runtime
            .set(&key, Bytes::from_static(b"\x00\x01"), SetOptions::default())
            .await
            .unwrap();
        assert!(matches!(
            store.snapshot("/f", None).await,
            Err(CacheError::InvalidData(_))
        ));
    }

    #[tokio::test]
    async fn unavailable_provider_fails_bump() {
        let provider = Arc::new(MemoryMockProvider::new());
        let runtime = CacheRuntime::memory_with_provider(Arc::clone(&provider));
        let store = VersionStore::new(runtime, "svc".to_string());
        provider.set_unavailable(true);
        assert!(store.bump(&store.key(KeyKind::Object, "/f")).await.is_err());
    }
}
