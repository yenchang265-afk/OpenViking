//! Size-tiered storage: small files and the path index in a SQL store, large
//! files in the object store.
//!
//! Object stores such as MinIO pay a fixed per-object cost (metadata on every
//! erasure-set drive), so many tiny objects hurt them. A tiered mount keeps
//! every file below `tiered_small_threshold_bytes` inline in a [`TierStore`]
//! (MariaDB in production) and writes only larger files to the wrapped backend,
//! under immutable blob keys. Users keep uploading files of any size.
//!
//! Enabled per mount with `tiered_enabled = true` in the plugin params:
//!
//! | param | default | meaning |
//! |---|---|---|
//! | `tiered_enabled` | `false` | wrap the mount |
//! | `tiered_small_threshold_bytes` | 1 MiB | files below this stay inline |
//! | `tiered_dsn_env` | `RAGFS_TIERED_DSN` | env var holding `mysql://user:pass@host:3306/db` |
//! | `tiered_table` | `agfs_entries` | index table name |
//! | `tiered_max_connections` | 16 | SQL pool size |
//! | `tiered_import_existing` | `false` | index objects written before tiering at mount |
//! | `tiered_import_exclude` | `[]` | top-level names owned by another mount |
//! | `tiered_gc_interval_secs` | 3600 | orphan blob GC period; `0` disables it |
//! | `tiered_gc_min_age_secs` | 3600 | GC only deletes unreferenced blobs older than this |

#[cfg(feature = "tiered")]
pub mod mariadb;
pub mod store;
pub mod wrapper;

#[cfg(test)]
mod tests;

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;

use tracing::info;

use crate::core::errors::{Error, Result};
use crate::core::filesystem::FileSystem;
use crate::core::types::{ConfigValue, PluginConfig};

pub use store::{Expected, Location, MemoryTierStore, PutMode, TierEntry, TierStore};
pub use wrapper::{ImportStats, TieredFileSystem, BLOB_ROOT, MAX_PATH_BYTES};

const MIB: i64 = 1024 * 1024;
/// Default inline threshold: the infra minimum object size.
pub const DEFAULT_SMALL_THRESHOLD_BYTES: u64 = MIB as u64;
/// Largest inline threshold; keeps rows well under MariaDB's `max_allowed_packet`.
pub const MAX_SMALL_THRESHOLD_BYTES: u64 = 8 * MIB as u64;
/// Default env var holding the store DSN.
pub const DEFAULT_DSN_ENV: &str = "RAGFS_TIERED_DSN";
/// Default index table name.
pub const DEFAULT_TABLE: &str = "agfs_entries";
const DEFAULT_MAX_CONNECTIONS: u32 = 16;
const MAX_MAX_CONNECTIONS: i64 = 256;
/// Default orphan GC period and minimum blob age (one hour).
const DEFAULT_GC_SECS: i64 = 3600;
/// Upper bound for GC timing settings (one week).
const MAX_GC_SECS: i64 = 7 * 24 * 3600;
/// Shortest allowed GC age: blobs younger than this may still be publishing.
const MIN_GC_MIN_AGE_SECS: i64 = 60;

/// Validated `tiered_*` mount parameters.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TieredSettings {
    /// Files smaller than this many bytes stay inline.
    pub small_threshold_bytes: u64,
    /// Env var that holds the store DSN (the DSN itself is never in config).
    pub dsn_env: String,
    /// Index table name.
    pub table: String,
    /// SQL connection pool size.
    pub max_connections: u32,
    /// Index pre-existing bucket objects when mounting.
    pub import_existing: bool,
    /// Top-level backend names owned by another mount (e.g. `.ovgit` when this
    /// mount's prefix is the bucket root); ignored by the untiered-data guard
    /// and by the import.
    pub import_exclude: Vec<String>,
    /// How often orphan blobs are collected; `None` disables the background GC.
    pub gc_interval: Option<Duration>,
    /// Minimum age of an unreferenced blob before GC deletes it.
    pub gc_min_age: Duration,
}

impl TieredSettings {
    /// Parse `tiered_*` params; `None` when tiering is disabled.
    pub fn from_params(params: &HashMap<String, ConfigValue>) -> Result<Option<Self>> {
        let enabled = bool_param(params, "tiered_enabled")?;
        if !enabled {
            return Ok(None);
        }
        let threshold = int_param(
            params,
            "tiered_small_threshold_bytes",
            DEFAULT_SMALL_THRESHOLD_BYTES as i64,
            1,
            MAX_SMALL_THRESHOLD_BYTES as i64,
        )?;
        let max_connections = int_param(
            params,
            "tiered_max_connections",
            i64::from(DEFAULT_MAX_CONNECTIONS),
            1,
            MAX_MAX_CONNECTIONS,
        )?;
        let dsn_env = string_param(params, "tiered_dsn_env", DEFAULT_DSN_ENV)?;
        if dsn_env.is_empty() {
            return Err(Error::config("tiered_dsn_env must not be empty"));
        }
        let table = string_param(params, "tiered_table", DEFAULT_TABLE)?;
        if !is_valid_table_name(&table) {
            return Err(Error::config(format!(
                "tiered_table must match [A-Za-z_][A-Za-z0-9_]{{0,63}}, got '{}'",
                table
            )));
        }
        Ok(Some(Self {
            small_threshold_bytes: threshold as u64,
            dsn_env,
            table,
            max_connections: max_connections as u32,
            import_existing: bool_param(params, "tiered_import_existing")?,
            import_exclude: name_list_param(params, "tiered_import_exclude")?,
            gc_interval: match int_param(
                params,
                "tiered_gc_interval_secs",
                DEFAULT_GC_SECS,
                0,
                MAX_GC_SECS,
            )? {
                0 => None,
                secs => Some(Duration::from_secs(secs as u64)),
            },
            gc_min_age: Duration::from_secs(int_param(
                params,
                "tiered_gc_min_age_secs",
                DEFAULT_GC_SECS,
                MIN_GC_MIN_AGE_SECS,
                MAX_GC_SECS,
            )? as u64),
        }))
    }
}

fn name_list_param(params: &HashMap<String, ConfigValue>, key: &str) -> Result<Vec<String>> {
    let Some(value) = params.get(key) else {
        return Ok(Vec::new());
    };
    let names = value
        .as_string_list()
        .ok_or_else(|| Error::config(format!("{} must be a list of strings", key)))?;
    if let Some(bad) = names
        .iter()
        .find(|name| name.is_empty() || name.contains('/'))
    {
        return Err(Error::config(format!(
            "{} entries must be single path segments, got '{}'",
            key, bad
        )));
    }
    Ok(names.to_vec())
}

fn bool_param(params: &HashMap<String, ConfigValue>, key: &str) -> Result<bool> {
    match params.get(key) {
        None => Ok(false),
        Some(value) => value
            .as_bool()
            .ok_or_else(|| Error::config(format!("{} must be a bool", key))),
    }
}

fn int_param(
    params: &HashMap<String, ConfigValue>,
    key: &str,
    default: i64,
    min: i64,
    max: i64,
) -> Result<i64> {
    let value = match params.get(key) {
        None => return Ok(default),
        Some(value) => value
            .as_int()
            .ok_or_else(|| Error::config(format!("{} must be an integer", key)))?,
    };
    if !(min..=max).contains(&value) {
        return Err(Error::config(format!(
            "{} must be between {} and {}, got {}",
            key, min, max, value
        )));
    }
    Ok(value)
}

fn string_param(params: &HashMap<String, ConfigValue>, key: &str, default: &str) -> Result<String> {
    match params.get(key) {
        None => Ok(default.to_string()),
        Some(value) => value
            .as_string()
            .map(str::to_string)
            .ok_or_else(|| Error::config(format!("{} must be a string", key))),
    }
}

/// Table names are interpolated into SQL, so only plain identifiers are allowed.
fn is_valid_table_name(name: &str) -> bool {
    let mut chars = name.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    name.len() <= 64
        && (first.is_ascii_alphabetic() || first == '_')
        && chars.all(|c| c.is_ascii_alphanumeric() || c == '_')
}

/// Connect the production [`TierStore`] described by `settings`.
#[cfg(feature = "tiered")]
pub async fn connect_store(settings: &TieredSettings) -> Result<Arc<dyn TierStore>> {
    let dsn = std::env::var(&settings.dsn_env).map_err(|_| {
        Error::config(format!(
            "tiered storage is enabled but env var {} is not set",
            settings.dsn_env
        ))
    })?;
    let store =
        mariadb::MariaDbTierStore::connect(&dsn, &settings.table, settings.max_connections).await?;
    Ok(Arc::new(store))
}

/// Connect the production [`TierStore`] described by `settings`.
#[cfg(not(feature = "tiered"))]
pub async fn connect_store(_settings: &TieredSettings) -> Result<Arc<dyn TierStore>> {
    Err(Error::config(
        "tiered_enabled requires ragfs built with the 'tiered' feature",
    ))
}

/// Wrap a freshly initialized backend when its mount enables tiering.
pub async fn maybe_wrap(
    raw: Box<dyn FileSystem>,
    config: &PluginConfig,
) -> Result<Box<dyn FileSystem>> {
    let Some(settings) = TieredSettings::from_params(&config.params)? else {
        return Ok(raw);
    };
    if config.backups.is_some() {
        return Err(Error::config(
            "tiered storage does not support multi-write (backups) mounts",
        ));
    }
    let store = connect_store(&settings).await?;
    let tiered = TieredFileSystem::new(store, Arc::from(raw), settings.small_threshold_bytes)
        .with_import_exclude(settings.import_exclude);
    if settings.import_existing {
        let stats = tiered.import_untiered().await?;
        info!(mount = %config.mount_path, ?stats, "tiered: imported pre-existing objects");
    } else if tiered.has_untiered_data().await? {
        return Err(Error::config(format!(
            "tiered storage index is empty but mount '{}' already holds objects; \
             set tiered_import_existing=true once to index them",
            config.mount_path
        )));
    }
    if let Some(interval) = settings.gc_interval {
        tiered.spawn_orphan_gc(interval, settings.gc_min_age);
    }
    Ok(Box::new(tiered))
}
