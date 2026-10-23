//! MariaDB / MySQL implementation of [`TierStore`].
//!
//! One InnoDB table holds every path of a tiered mount. `path` is a
//! `VARBINARY` primary key, so subtree operations are byte-range scans
//! (`path >= 'p/' AND path < 'p0'`, since `'0'` is the byte after `'/'`).
//! Sessions run at READ COMMITTED to avoid gap-lock deadlocks; the few
//! deadlocks that remain are retried.

use std::collections::HashSet;
use std::future::Future;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use async_trait::async_trait;
use sqlx::mysql::{MySqlConnectOptions, MySqlPool, MySqlPoolOptions, MySqlRow};
use sqlx::{Executor, MySql, Row, Transaction};

use crate::core::errors::{Error, Result};

use super::store::{
    ancestors_of, is_same_or_descendant, parent_of, Expected, Location, PutMode, TierEntry,
    TierStore,
};

const KIND_DIR: i8 = 0;
const KIND_INLINE: i8 = 1;
const KIND_BLOB: i8 = 2;
const COLUMNS: &str = "path, kind, size, mode, mtime_us, blob_key";
const ER_LOCK_DEADLOCK: u16 = 1213;
const MAX_ATTEMPTS: usize = 3;
const ACQUIRE_TIMEOUT: Duration = Duration::from_secs(10);

/// Failure inside one transaction attempt: retryable database errors are kept
/// apart from filesystem errors that must surface unchanged.
enum TxError {
    Db(sqlx::Error),
    Fs(Error),
}

impl From<sqlx::Error> for TxError {
    fn from(error: sqlx::Error) -> Self {
        Self::Db(error)
    }
}

impl From<Error> for TxError {
    fn from(error: Error) -> Self {
        Self::Fs(error)
    }
}

type TxResult<T> = std::result::Result<T, TxError>;

fn is_deadlock(error: &sqlx::Error) -> bool {
    error
        .as_database_error()
        .and_then(|db| db.try_downcast_ref::<sqlx::mysql::MySqlDatabaseError>())
        .is_some_and(|db| db.number() == ER_LOCK_DEADLOCK)
}

fn into_fs_error(error: TxError, path: &str) -> Error {
    match error {
        TxError::Fs(error) => error,
        TxError::Db(sqlx::Error::Database(db)) if db.is_unique_violation() => {
            Error::already_exists(path)
        }
        TxError::Db(error) => Error::internal(format!("tiered store: {}", error)),
    }
}

/// Run `op` up to [`MAX_ATTEMPTS`] times while it fails with a deadlock.
async fn with_retry<T, F, Fut>(path: &str, mut op: F) -> Result<T>
where
    F: FnMut() -> Fut,
    Fut: Future<Output = TxResult<T>>,
{
    let mut attempt = 1;
    loop {
        match op().await {
            Err(TxError::Db(error)) if is_deadlock(&error) && attempt < MAX_ATTEMPTS => {
                attempt += 1;
            }
            other => return other.map_err(|error| into_fs_error(error, path)),
        }
    }
}

fn to_micros(time: SystemTime) -> i64 {
    time.duration_since(UNIX_EPOCH)
        .map(|elapsed| i64::try_from(elapsed.as_micros()).unwrap_or(i64::MAX))
        .unwrap_or(0)
}

fn from_micros(micros: i64) -> SystemTime {
    UNIX_EPOCH + Duration::from_micros(u64::try_from(micros).unwrap_or(0))
}

fn kind_of(location: &Location) -> i8 {
    match location {
        Location::Directory => KIND_DIR,
        Location::Inline => KIND_INLINE,
        Location::Blob(_) => KIND_BLOB,
    }
}

fn entry_from_row(row: &MySqlRow) -> TxResult<TierEntry> {
    let path = String::from_utf8(row.try_get::<Vec<u8>, _>("path")?)
        .map_err(|_| Error::internal("tiered store: non-UTF-8 path in index"))?;
    let kind: i8 = row.try_get("kind")?;
    let location = match kind {
        KIND_DIR => Location::Directory,
        KIND_INLINE => Location::Inline,
        KIND_BLOB => {
            let key: Option<Vec<u8>> = row.try_get("blob_key")?;
            let key = key
                .and_then(|key| String::from_utf8(key).ok())
                .ok_or_else(|| {
                    Error::internal(format!("tiered store: blob row without key: {}", path))
                })?;
            Location::Blob(key)
        }
        other => {
            return Err(Error::internal(format!(
                "tiered store: unknown kind {} for {}",
                other, path
            ))
            .into())
        }
    };
    Ok(TierEntry {
        path,
        size: row.try_get::<u64, _>("size")?,
        mode: row.try_get::<u32, _>("mode")?,
        mod_time: from_micros(row.try_get::<i64, _>("mtime_us")?),
        location,
    })
}

/// Lower and upper bounds of the strict descendants of `path`.
fn descendant_bounds(path: &str) -> (String, String) {
    if path == "/" {
        ("/".to_string(), "0".to_string())
    } else {
        (format!("{}/", path), format!("{}0", path))
    }
}

/// A [`TierStore`] backed by one MariaDB/MySQL table.
pub struct MariaDbTierStore {
    pool: MySqlPool,
    table: String,
}

impl MariaDbTierStore {
    /// Connect with `dsn` (`mysql://user:pass@host:3306/db`) and create the
    /// table when missing. `table` must already be a validated identifier.
    pub async fn connect(dsn: &str, table: &str, max_connections: u32) -> Result<Self> {
        let options: MySqlConnectOptions = dsn
            .parse()
            .map_err(|_| Error::config("tiered store DSN is not a valid mysql:// URL"))?;
        let pool = MySqlPoolOptions::new()
            .max_connections(max_connections)
            .acquire_timeout(ACQUIRE_TIMEOUT)
            .after_connect(|conn, _meta| {
                Box::pin(async move {
                    conn.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
                        .await?;
                    Ok(())
                })
            })
            .connect_with(options)
            .await
            .map_err(|error| Error::config(format!("tiered store: cannot connect: {}", error)))?;
        let store = Self {
            pool,
            table: table.to_string(),
        };
        store.create_table().await?;
        Ok(store)
    }

    async fn create_table(&self) -> Result<()> {
        let ddl = format!(
            "CREATE TABLE IF NOT EXISTS `{}` (
                path     VARBINARY(3072) NOT NULL,
                parent   VARBINARY(3072) NOT NULL,
                kind     TINYINT NOT NULL,
                size     BIGINT UNSIGNED NOT NULL,
                mode     INT UNSIGNED NOT NULL,
                mtime_us BIGINT NOT NULL,
                blob_key VARBINARY(3072) NULL,
                data     MEDIUMBLOB NULL,
                PRIMARY KEY (path),
                KEY idx_parent (parent)
            ) ENGINE=InnoDB ROW_FORMAT=DYNAMIC",
            self.table
        );
        self.pool.execute(ddl.as_str()).await.map_err(|error| {
            Error::config(format!("tiered store: cannot create table: {}", error))
        })?;
        Ok(())
    }

    fn sql(&self, template: &str) -> String {
        template.replace("{t}", &format!("`{}`", self.table))
    }

    async fn lock_row(
        &self,
        tx: &mut Transaction<'_, MySql>,
        path: &str,
    ) -> TxResult<Option<TierEntry>> {
        let sql = self.sql(&format!(
            "SELECT {} FROM {{t}} WHERE path = ? FOR UPDATE",
            COLUMNS
        ));
        let row = sqlx::query(&sql)
            .bind(path.as_bytes())
            .fetch_optional(&mut **tx)
            .await?;
        row.as_ref().map(entry_from_row).transpose()
    }

    async fn lock_row_with_data(
        &self,
        tx: &mut Transaction<'_, MySql>,
        path: &str,
    ) -> TxResult<Option<(TierEntry, Option<Vec<u8>>)>> {
        let sql = self.sql(&format!(
            "SELECT {}, data FROM {{t}} WHERE path = ? FOR UPDATE",
            COLUMNS
        ));
        let row = sqlx::query(&sql)
            .bind(path.as_bytes())
            .fetch_optional(&mut **tx)
            .await?;
        match row {
            None => Ok(None),
            Some(row) => Ok(Some((entry_from_row(&row)?, row.try_get("data")?))),
        }
    }

    /// Create missing ancestor directories of `path`, failing if one is a file.
    async fn ensure_ancestors(
        &self,
        tx: &mut Transaction<'_, MySql>,
        path: &str,
        now: SystemTime,
    ) -> TxResult<()> {
        let insert = self.sql(
            "INSERT INTO {t} (path, parent, kind, size, mode, mtime_us) \
             VALUES (?, ?, 0, 0, 493, ?) ON DUPLICATE KEY UPDATE path = path",
        );
        let kind_sql = self.sql("SELECT kind FROM {t} WHERE path = ?");
        for ancestor in ancestors_of(path) {
            sqlx::query(&insert)
                .bind(ancestor.as_bytes())
                .bind(parent_of(&ancestor).as_bytes())
                .bind(to_micros(now))
                .execute(&mut **tx)
                .await?;
            let kind: i8 = sqlx::query_scalar(&kind_sql)
                .bind(ancestor.as_bytes())
                .fetch_one(&mut **tx)
                .await?;
            if kind != KIND_DIR {
                return Err(Error::NotADirectory(ancestor).into());
            }
        }
        Ok(())
    }

    async fn write_row(
        &self,
        tx: &mut Transaction<'_, MySql>,
        entry: &TierEntry,
        inline: Option<&[u8]>,
        upsert: bool,
    ) -> TxResult<()> {
        let mut sql = self.sql(
            "INSERT INTO {t} (path, parent, kind, size, mode, mtime_us, blob_key, data) \
             VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        );
        if upsert {
            sql.push_str(
                " ON DUPLICATE KEY UPDATE kind = VALUES(kind), size = VALUES(size), \
                 mode = VALUES(mode), mtime_us = VALUES(mtime_us), \
                 blob_key = VALUES(blob_key), data = VALUES(data)",
            );
        }
        sqlx::query(&sql)
            .bind(entry.path.as_bytes())
            .bind(parent_of(&entry.path).as_bytes())
            .bind(kind_of(&entry.location))
            .bind(entry.size)
            .bind(entry.mode)
            .bind(to_micros(entry.mod_time))
            .bind(entry.blob_key().map(str::as_bytes))
            .bind(inline)
            .execute(&mut **tx)
            .await?;
        Ok(())
    }

    async fn delete_row(&self, tx: &mut Transaction<'_, MySql>, path: &str) -> TxResult<()> {
        sqlx::query(&self.sql("DELETE FROM {t} WHERE path = ?"))
            .bind(path.as_bytes())
            .execute(&mut **tx)
            .await?;
        Ok(())
    }

    fn matches(current: &(TierEntry, Option<Vec<u8>>), expected: Expected<'_>) -> bool {
        match (expected, &current.0.location) {
            (Expected::Inline(bytes), Location::Inline) => current.1.as_deref() == Some(bytes),
            (Expected::Blob(key), Location::Blob(current)) => key == current,
            _ => false,
        }
    }

    async fn put_file_once(
        &self,
        entry: &TierEntry,
        inline: Option<&[u8]>,
        mode: PutMode,
    ) -> TxResult<Option<TierEntry>> {
        let mut tx = self.pool.begin().await?;
        let previous = self.lock_row(&mut tx, &entry.path).await?;
        match &previous {
            Some(row) if row.is_dir() => return Err(Error::IsADirectory(entry.path.clone()).into()),
            Some(_) if mode == PutMode::CreateNew => {
                return Err(Error::already_exists(&entry.path).into())
            }
            _ => {}
        }
        self.ensure_ancestors(&mut tx, &entry.path, entry.mod_time)
            .await?;
        self.write_row(&mut tx, entry, inline, mode == PutMode::Upsert)
            .await?;
        tx.commit().await?;
        Ok(previous)
    }

    async fn create_dir_once(&self, entry: &TierEntry) -> TxResult<()> {
        let mut tx = self.pool.begin().await?;
        if self.lock_row(&mut tx, &entry.path).await?.is_some() {
            return Err(Error::already_exists(&entry.path).into());
        }
        self.ensure_ancestors(&mut tx, &entry.path, entry.mod_time)
            .await?;
        self.write_row(&mut tx, entry, None, false).await?;
        tx.commit().await?;
        Ok(())
    }

    async fn remove_entry_once(&self, path: &str) -> TxResult<TierEntry> {
        let mut tx = self.pool.begin().await?;
        let entry = self
            .lock_row(&mut tx, path)
            .await?
            .ok_or_else(|| Error::not_found(path))?;
        if entry.is_dir() {
            let child = sqlx::query(&self.sql("SELECT 1 FROM {t} WHERE parent = ? LIMIT 1"))
                .bind(path.as_bytes())
                .fetch_optional(&mut *tx)
                .await?;
            if child.is_some() {
                return Err(Error::DirectoryNotEmpty(path.to_string()).into());
            }
        }
        self.delete_row(&mut tx, path).await?;
        tx.commit().await?;
        Ok(entry)
    }

    async fn remove_subtree_once(&self, path: &str) -> TxResult<Vec<TierEntry>> {
        let (lo, hi) = descendant_bounds(path);
        let mut tx = self.pool.begin().await?;
        let select = self.sql(&format!(
            "SELECT {} FROM {{t}} WHERE path = ? OR (path >= ? AND path < ?) FOR UPDATE",
            COLUMNS
        ));
        let rows = sqlx::query(&select)
            .bind(path.as_bytes())
            .bind(lo.as_bytes())
            .bind(hi.as_bytes())
            .fetch_all(&mut *tx)
            .await?;
        let removed = rows
            .iter()
            .map(entry_from_row)
            .collect::<TxResult<Vec<_>>>()?;
        sqlx::query(&self.sql("DELETE FROM {t} WHERE path = ? OR (path >= ? AND path < ?)"))
            .bind(path.as_bytes())
            .bind(lo.as_bytes())
            .bind(hi.as_bytes())
            .execute(&mut *tx)
            .await?;
        tx.commit().await?;
        Ok(removed)
    }

    async fn move_entry_once(
        &self,
        src: &str,
        dst: &str,
        mod_time: SystemTime,
    ) -> TxResult<Option<TierEntry>> {
        let mut tx = self.pool.begin().await?;
        let source = self
            .lock_row(&mut tx, src)
            .await?
            .ok_or_else(|| Error::not_found(src))?;
        let replaced = match self.lock_row(&mut tx, dst).await? {
            Some(existing) if existing.is_dir() || source.is_dir() => {
                return Err(Error::already_exists(dst).into());
            }
            other => other,
        };
        if source.is_dir() && is_same_or_descendant(dst, src) {
            return Err(Error::invalid_operation(format!(
                "cannot move directory {} into itself",
                src
            ))
            .into());
        }
        self.ensure_ancestors(&mut tx, dst, mod_time).await?;
        if replaced.is_some() {
            self.delete_row(&mut tx, dst).await?;
        }
        if source.is_dir() {
            // Every descendant's path and parent start with `src`, so one prefix swap rebases both.
            let (lo, hi) = descendant_bounds(src);
            let offset = src.len() as i64 + 1;
            let rebase = self.sql(
                "UPDATE {t} SET path = CONCAT(?, SUBSTRING(path, ?)), \
                 parent = CONCAT(?, SUBSTRING(parent, ?)) WHERE path >= ? AND path < ?",
            );
            sqlx::query(&rebase)
                .bind(dst.as_bytes())
                .bind(offset)
                .bind(dst.as_bytes())
                .bind(offset)
                .bind(lo.as_bytes())
                .bind(hi.as_bytes())
                .execute(&mut *tx)
                .await?;
        }
        sqlx::query(&self.sql("UPDATE {t} SET path = ?, parent = ?, mtime_us = ? WHERE path = ?"))
            .bind(dst.as_bytes())
            .bind(parent_of(dst).as_bytes())
            .bind(to_micros(mod_time))
            .bind(src.as_bytes())
            .execute(&mut *tx)
            .await?;
        tx.commit().await?;
        Ok(replaced)
    }

    async fn compare_and_put_once(
        &self,
        expected: Expected<'_>,
        entry: &TierEntry,
        inline: Option<&[u8]>,
    ) -> TxResult<Option<TierEntry>> {
        let mut tx = self.pool.begin().await?;
        let Some(current) = self.lock_row_with_data(&mut tx, &entry.path).await? else {
            return Ok(None);
        };
        if !Self::matches(&current, expected) {
            return Ok(None);
        }
        self.write_row(&mut tx, entry, inline, true).await?;
        tx.commit().await?;
        Ok(Some(current.0))
    }

    async fn compare_and_remove_once(
        &self,
        path: &str,
        expected: Expected<'_>,
    ) -> TxResult<Option<TierEntry>> {
        let mut tx = self.pool.begin().await?;
        let Some(current) = self.lock_row_with_data(&mut tx, path).await? else {
            return Ok(None);
        };
        if !Self::matches(&current, expected) {
            return Ok(None);
        }
        self.delete_row(&mut tx, path).await?;
        tx.commit().await?;
        Ok(Some(current.0))
    }
}

#[async_trait]
impl TierStore for MariaDbTierStore {
    async fn get(&self, path: &str) -> Result<Option<TierEntry>> {
        with_retry(path, || async {
            let sql = self.sql(&format!("SELECT {} FROM {{t}} WHERE path = ?", COLUMNS));
            let row = sqlx::query(&sql)
                .bind(path.as_bytes())
                .fetch_optional(&self.pool)
                .await?;
            row.as_ref().map(entry_from_row).transpose()
        })
        .await
    }

    async fn read_inline(&self, path: &str) -> Result<Option<Vec<u8>>> {
        with_retry(path, || async {
            let sql = self.sql("SELECT data FROM {t} WHERE path = ? AND kind = 1");
            let data: Option<Option<Vec<u8>>> = sqlx::query_scalar(&sql)
                .bind(path.as_bytes())
                .fetch_optional(&self.pool)
                .await?;
            Ok(data.flatten())
        })
        .await
    }

    async fn put_file(
        &self,
        entry: TierEntry,
        inline: Option<&[u8]>,
        mode: PutMode,
    ) -> Result<Option<TierEntry>> {
        with_retry(&entry.path, || self.put_file_once(&entry, inline, mode)).await
    }

    async fn create_dir(&self, path: &str, mode: u32, mod_time: SystemTime) -> Result<()> {
        let entry = TierEntry {
            path: path.to_string(),
            size: 0,
            mode,
            mod_time,
            location: Location::Directory,
        };
        with_retry(path, || self.create_dir_once(&entry)).await
    }

    async fn list_children(&self, dir: &str) -> Result<Vec<TierEntry>> {
        with_retry(dir, || async {
            let sql = self.sql(&format!("SELECT {} FROM {{t}} WHERE parent = ?", COLUMNS));
            let rows = sqlx::query(&sql)
                .bind(dir.as_bytes())
                .fetch_all(&self.pool)
                .await?;
            rows.iter().map(entry_from_row).collect()
        })
        .await
    }

    async fn remove_entry(&self, path: &str) -> Result<TierEntry> {
        with_retry(path, || self.remove_entry_once(path)).await
    }

    async fn remove_subtree(&self, path: &str) -> Result<Vec<TierEntry>> {
        with_retry(path, || self.remove_subtree_once(path)).await
    }

    async fn move_entry(
        &self,
        src: &str,
        dst: &str,
        mod_time: SystemTime,
    ) -> Result<Option<TierEntry>> {
        with_retry(dst, || self.move_entry_once(src, dst, mod_time)).await
    }

    async fn compare_and_put(
        &self,
        expected: Expected<'_>,
        entry: TierEntry,
        inline: Option<&[u8]>,
    ) -> Result<Option<TierEntry>> {
        with_retry(&entry.path, || {
            self.compare_and_put_once(expected, &entry, inline)
        })
        .await
    }

    async fn compare_and_remove(
        &self,
        path: &str,
        expected: Expected<'_>,
    ) -> Result<Option<TierEntry>> {
        with_retry(path, || self.compare_and_remove_once(path, expected)).await
    }

    async fn set_mode(&self, path: &str, mode: u32) -> Result<()> {
        let updated = with_retry(path, || async {
            let result = sqlx::query(&self.sql("UPDATE {t} SET mode = ? WHERE path = ?"))
                .bind(mode)
                .bind(path.as_bytes())
                .execute(&self.pool)
                .await?;
            Ok(result.rows_affected())
        })
        .await?;
        // MariaDB reports 0 affected rows when the value is unchanged, so confirm existence.
        if updated == 0 && self.get(path).await?.is_none() {
            return Err(Error::not_found(path));
        }
        Ok(())
    }

    async fn blob_keys(&self) -> Result<HashSet<String>> {
        with_retry("/", || async {
            let sql = self.sql("SELECT blob_key FROM {t} WHERE kind = 2");
            let keys: Vec<Vec<u8>> = sqlx::query_scalar(&sql).fetch_all(&self.pool).await?;
            Ok(keys
                .into_iter()
                .filter_map(|key| String::from_utf8(key).ok())
                .collect())
        })
        .await
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn descendant_bounds_bracket_only_children() {
        let (lo, hi) = descendant_bounds("/a");
        assert!("/a/b" >= lo.as_str() && "/a/b" < hi.as_str());
        assert!("/a/zzz/deep" >= lo.as_str() && "/a/zzz/deep" < hi.as_str());
        assert!(
            !("/a" >= lo.as_str()),
            "the root itself is matched separately"
        );
        assert!(!("/ab" >= lo.as_str() && "/ab" < hi.as_str()));
        assert!(!("/a-b" >= lo.as_str() && "/a-b" < hi.as_str()));
    }

    #[test]
    fn micros_round_trip_keeps_microsecond_precision() {
        let time = UNIX_EPOCH + Duration::from_micros(1_700_000_000_123_456);
        assert_eq!(from_micros(to_micros(time)), time);
        assert_eq!(to_micros(UNIX_EPOCH - Duration::from_secs(1)), 0);
    }
}
