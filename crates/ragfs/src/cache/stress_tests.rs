//! Randomized stress test: several CacheFS instances share one cache runtime
//! and one backend while tasks race writes, removes and reads.
//!
//! Oracle: per path, a read may return the value of mutation `m` only if `m`
//! started before the read ended and no other mutation that started after `m`
//! finished had itself finished before the read started. A stale cache entry
//! breaks exactly that rule. Hits that overlap an in-flight mutation may still
//! return the value from before it, because the counter bump is the commit
//! point.
//!
//! `RAGFS_CACHE_STRESS_SEED` and `RAGFS_CACHE_STRESS_OPS` override the fixed
//! seed and the per-task operation count for longer local runs.

use super::{CachePolicy, CachedFileSystem};
use crate::cache_runtime::CacheRuntime;
use crate::core::{Error, FileInfo, FileSystem, ListSortBy, Result, SortOrder, WriteFlag};
use crate::plugins::memfs::MemFileSystem;
use async_trait::async_trait;
use rand::rngs::StdRng;
use rand::{Rng, SeedableRng};
use std::collections::HashMap;
use std::path::Path;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

const INSTANCES: usize = 3;
const TASKS_PER_INSTANCE: usize = 2;
const DEFAULT_OPS_PER_TASK: usize = 300;
const DEFAULT_SEED: u64 = 0x5eed_cafe;
const MAX_JITTER_MICROS: u64 = 3_000;
const DIR: &str = "/d/e";
const PATHS: [&str; 4] = ["/d/a", "/d/b", "/d/e/c", "/d/e/f"];

/// Backend wrapper that sleeps a random time after each data call, widening
/// the window between a backend call and the cache work that follows it.
struct JitterFs {
    inner: Arc<dyn FileSystem>,
    rng: Mutex<StdRng>,
}

impl JitterFs {
    async fn jitter(&self) {
        let micros = self.rng.lock().unwrap().gen_range(0..=MAX_JITTER_MICROS);
        tokio::time::sleep(Duration::from_micros(micros)).await;
    }
}

#[async_trait]
impl FileSystem for JitterFs {
    async fn create(&self, path: &str) -> Result<()> {
        self.inner.create(path).await
    }

    async fn mkdir(&self, path: &str, mode: u32) -> Result<()> {
        let result = self.inner.mkdir(path, mode).await;
        self.jitter().await;
        result
    }

    async fn remove(&self, path: &str) -> Result<()> {
        let result = self.inner.remove(path).await;
        self.jitter().await;
        result
    }

    async fn remove_all(&self, path: &str) -> Result<()> {
        let result = self.inner.remove_all(path).await;
        self.jitter().await;
        result
    }

    async fn read(&self, path: &str, offset: u64, size: u64) -> Result<Vec<u8>> {
        let result = self.inner.read(path, offset, size).await;
        self.jitter().await;
        result
    }

    async fn write(&self, path: &str, data: &[u8], offset: u64, flags: WriteFlag) -> Result<u64> {
        let result = self.inner.write(path, data, offset, flags).await;
        self.jitter().await;
        result
    }

    async fn write_from_path(&self, path: &str, src: &Path, flags: WriteFlag) -> Result<u64> {
        self.inner.write_from_path(path, src, flags).await
    }

    async fn read_to_path(&self, path: &str, dst: &Path) -> Result<u64> {
        self.inner.read_to_path(path, dst).await
    }

    async fn read_dir(
        &self,
        path: &str,
        offset: Option<usize>,
        limit: Option<usize>,
        sort_by: Option<ListSortBy>,
        sort_order: Option<SortOrder>,
    ) -> Result<Vec<FileInfo>> {
        let result = self
            .inner
            .read_dir(path, offset, limit, sort_by, sort_order)
            .await;
        self.jitter().await;
        result
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

#[derive(Debug, Clone)]
struct Mutation {
    start: Instant,
    /// `None` while the call is still running.
    end: Option<Instant>,
    value: Option<Vec<u8>>,
}

/// Mutations per path, starting from the empty initial state. A mutation is
/// recorded when it starts, because readers can observe its effect before
/// the call returns.
struct History {
    mutations: Mutex<HashMap<&'static str, Vec<Option<Mutation>>>>,
}

impl History {
    fn new(origin: Instant) -> Self {
        let initial = Mutation {
            start: origin,
            end: Some(origin),
            value: None,
        };
        Self {
            mutations: Mutex::new(
                PATHS
                    .iter()
                    .map(|path| (*path, vec![Some(initial.clone())]))
                    .collect(),
            ),
        }
    }

    fn begin(&self, path: &'static str, start: Instant, value: Option<Vec<u8>>) -> usize {
        let mut mutations = self.mutations.lock().unwrap();
        let entries = mutations.get_mut(path).unwrap();
        entries.push(Some(Mutation {
            start,
            end: None,
            value,
        }));
        entries.len() - 1
    }

    /// Mark a mutation finished, or forget it when it changed nothing.
    fn finish(&self, path: &'static str, index: usize, applied: bool) {
        let mut mutations = self.mutations.lock().unwrap();
        let slot = &mut mutations.get_mut(path).unwrap()[index];
        if applied {
            if let Some(mutation) = slot.as_mut() {
                mutation.end = Some(Instant::now());
            }
        } else {
            *slot = None;
        }
    }

    /// Return a description of the violation if `observed` is a stale value.
    fn check(
        &self,
        path: &str,
        read_start: Instant,
        read_end: Instant,
        observed: &Option<Vec<u8>>,
    ) -> Option<String> {
        let mutations = self.mutations.lock().unwrap();
        let mutations = mutations[path].iter().flatten().collect::<Vec<_>>();
        let superseded = |candidate: &Mutation| {
            candidate.end.is_some_and(|candidate_end| {
                mutations.iter().any(|later| {
                    later.start > candidate_end && later.end.is_some_and(|end| end < read_start)
                })
            })
        };
        let acceptable = mutations.iter().any(|candidate| {
            &candidate.value == observed && candidate.start <= read_end && !superseded(candidate)
        });
        (!acceptable).then(|| {
            format!(
                "{path}: read returned {:?}, superseded before the read started",
                observed.as_deref().map(String::from_utf8_lossy)
            )
        })
    }
}

fn env_or<T: std::str::FromStr>(name: &str, default: T) -> T {
    std::env::var(name)
        .ok()
        .and_then(|value| value.parse().ok())
        .unwrap_or(default)
}

async fn run_task(
    fs: Arc<dyn FileSystem>,
    history: Arc<History>,
    task: usize,
    seed: u64,
    ops: usize,
) -> Vec<String> {
    let mut rng = StdRng::seed_from_u64(seed.wrapping_add(task as u64));
    let mut violations = Vec::new();
    for op in 0..ops {
        let path = PATHS[rng.gen_range(0..PATHS.len())];
        let roll = rng.gen_range(0..100);
        let start = Instant::now();
        match roll {
            0..=49 => {
                let observed = match fs.read(path, 0, 0).await {
                    Ok(data) => Some(data),
                    Err(Error::NotFound(_)) => None,
                    Err(error) => panic!("unexpected read error on {path}: {error}"),
                };
                if let Some(violation) = history.check(path, start, Instant::now(), &observed) {
                    violations.push(violation);
                }
            }
            50..=74 => {
                let value = format!("t{task}-op{op}").into_bytes();
                let index = history.begin(path, start, Some(value.clone()));
                let applied = fs.write(path, &value, 0, WriteFlag::Create).await.is_ok();
                history.finish(path, index, applied);
            }
            75..=84 => {
                let index = history.begin(path, start, None);
                let applied = fs.remove(path).await.is_ok();
                history.finish(path, index, applied);
            }
            85..=89 => {
                // A failed recursive delete still leaves no descendant behind
                // (the directory was already gone), so it always counts.
                let indexes = PATHS
                    .iter()
                    .filter(|path| path.starts_with(DIR))
                    .map(|path| (*path, history.begin(path, start, None)))
                    .collect::<Vec<_>>();
                let _ = fs.remove_all(DIR).await;
                for (path, index) in indexes {
                    history.finish(path, index, true);
                }
            }
            _ => {
                let _ = fs.mkdir(DIR, 0o755).await;
            }
        }
    }
    violations
}

/// Run the workload on `INSTANCES` filesystems built over one shared backend
/// and return every stale read the oracle found.
async fn run_workload<F>(
    seed: u64,
    ops: usize,
    build: F,
) -> (Arc<dyn FileSystem>, Vec<Arc<dyn FileSystem>>, Vec<String>)
where
    F: Fn(usize, Arc<dyn FileSystem>) -> Arc<dyn FileSystem>,
{
    let backend: Arc<dyn FileSystem> = Arc::new(MemFileSystem::new());
    backend.mkdir("/d", 0o755).await.unwrap();
    backend.mkdir(DIR, 0o755).await.unwrap();
    let instances = (0..INSTANCES)
        .map(|index| {
            let jitter: Arc<dyn FileSystem> = Arc::new(JitterFs {
                inner: Arc::clone(&backend),
                rng: Mutex::new(StdRng::seed_from_u64(seed ^ ((index as u64 + 1) << 32))),
            });
            build(index, jitter)
        })
        .collect::<Vec<_>>();
    let history = Arc::new(History::new(Instant::now()));

    let tasks = (0..INSTANCES * TASKS_PER_INSTANCE)
        .map(|task| {
            let fs = Arc::clone(&instances[task % INSTANCES]);
            tokio::spawn(run_task(fs, Arc::clone(&history), task, seed, ops))
        })
        .collect::<Vec<_>>();
    let mut violations = Vec::new();
    for task in tasks {
        violations.extend(task.await.unwrap());
    }
    (backend, instances, violations)
}

/// Control: the oracle must accept the uncached backend itself.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn oracle_accepts_the_uncached_backend() {
    let seed = env_or("RAGFS_CACHE_STRESS_SEED", DEFAULT_SEED);
    let ops = env_or("RAGFS_CACHE_STRESS_OPS", DEFAULT_OPS_PER_TASK);
    let (_, _, violations) = run_workload(seed, ops, |_, jitter| jitter).await;
    assert!(
        violations.is_empty(),
        "seed {seed:#x}: {:?}",
        &violations[..violations.len().min(5)]
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn randomized_instances_never_serve_superseded_values() {
    let seed = env_or("RAGFS_CACHE_STRESS_SEED", DEFAULT_SEED);
    let ops = env_or("RAGFS_CACHE_STRESS_OPS", DEFAULT_OPS_PER_TASK);
    let runtime = CacheRuntime::memory();
    let (backend, instances, violations) = run_workload(seed, ops, |_, jitter| {
        Arc::new(CachedFileSystem::with_runtime(
            Box::new(crate::core::mountable::ArcFileSystem(jitter)),
            Arc::clone(&runtime),
            "stress-test",
            CachePolicy::default().with_multi_instance(true),
        )) as Arc<dyn FileSystem>
    })
    .await;
    assert!(
        violations.is_empty(),
        "seed {seed:#x}: {} stale reads, first: {:?}",
        violations.len(),
        &violations[..violations.len().min(5)]
    );

    // After quiescence every instance must agree with the backend.
    for path in PATHS {
        let expected = backend.read(path, 0, 0).await.ok();
        for (index, fs) in instances.iter().enumerate() {
            assert_eq!(
                fs.read(path, 0, 0).await.ok(),
                expected,
                "seed {seed:#x}: instance {index} disagrees with the backend on {path}"
            );
        }
    }
}
