"""Shared MySQL usage projections and request audit history.

Bucket identities hash the complete projection key rather than truncating model
or identity strings to fit a MySQL compound index. Counters increment atomically.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    Double,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    and_,
    delete,
    func,
    insert,
    or_,
    select,
)
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import create_async_engine

from openviking.server.account_stores.mysql import MySQLAccountStore
from openviking.storage.mysql_runtime import (
    get_shared_mysql_runtime,
    mysql_runtime_store,
    wait_mysql_cleanup,
)
from openviking_cli.utils.config.config_utils import normalize_service_name

from .projection import project_events, safe_int
from .sqlite_store import (
    DAILY_TOKEN_KEYS,
    MINUTE_RETENTION_DAYS,
    MINUTE_TOKEN_KEYS,
    REQUEST_SAMPLE_LIMIT,
    SQLiteUsageAuditStore,
    _date_range,
    _user_day_window_utc,
)

UTC = timezone.utc
metadata = MetaData()
buckets = Table(
    "ov_usage_buckets",
    metadata,
    Column("service_name", String(64), primary_key=True),
    Column("bucket_id", String(64), primary_key=True),
    Column("kind", String(16), nullable=False),
    Column("account_id", String(128), nullable=False),
    Column("user_id", String(128), nullable=False),
    Column("date_utc", String(10), nullable=False),
    Column("dimensions", JSON, nullable=False),
    Column("count", BigInteger, nullable=False),
    Column("result_count", BigInteger, nullable=False),
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_bin",
)
AUDIT_FIELDS = (
    "request_id",
    "account_id",
    "user_id",
    "method",
    "route",
    "api_type",
    "status_code",
    "duration_ms",
    "error_code",
    "error_message",
    "error_details",
    "created_at",
)
audit = Table(
    "ov_request_audit",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("service_name", String(64), nullable=False),
    Column("request_id", String(128)),
    Column("account_id", String(128), nullable=False),
    Column("user_id", String(128)),
    Column("method", String(16), nullable=False),
    Column("route", Text, nullable=False),
    Column("api_type", String(128), nullable=False),
    Column("status_code", Integer, nullable=False),
    Column("duration_ms", Double, nullable=False),
    Column("error_code", Text),
    Column("error_message", Text),
    Column("error_details", Text),
    Column("created_at", String(40), nullable=False),
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_bin",
)
Index("ix_ov_usage_owner_date", buckets.c.service_name, buckets.c.account_id, buckets.c.date_utc)
Index(
    "ix_ov_audit_owner_created",
    audit.c.service_name,
    audit.c.account_id,
    audit.c.created_at,
    audit.c.id,
)


@mysql_runtime_store
class MySQLUsageAuditStore:
    def __init__(
        self,
        *,
        service_name,
        params,
        usage_retention_days=14,
        audit_retention_days=7,
        audit_retention_per_account=1000,
    ):
        self._service_name = normalize_service_name(service_name)
        self._url, self._options = MySQLAccountStore._connection_options(dict(params))
        self._mysql_runtime = get_shared_mysql_runtime()
        self._engine = None
        self._mysql_lease = False
        self._usage_retention_days = usage_retention_days
        self._audit_retention_days = audit_retention_days
        self._audit_retention_per_account = audit_retention_per_account

    async def initialize(self):
        if self._engine is not None:
            return
        await self._mysql_runtime.acquire()
        self._mysql_lease = True
        try:
            self._engine = create_async_engine(self._url, **self._options)
            async with self._engine.connect() as connection:
                for table in (buckets, audit):
                    await connection.execute(select(table).limit(0))
        except BaseException:
            await wait_mysql_cleanup(self._close())
            raise

    async def close(self):
        await self._close()

    async def _close(self):
        try:
            if self._engine is not None:
                await wait_mysql_cleanup(self._engine.dispose())
        finally:
            self._engine = None
            if self._mysql_lease:
                self._mysql_lease = False
                await self._mysql_runtime.release()

    def _scope(self, table, account_id, user_id=None):
        conditions = [table.c.service_name == self._service_name, table.c.account_id == account_id]
        if user_id is not None:
            conditions.append(table.c.user_id == user_id)
        return conditions

    async def record_batch(self, events):
        if not events:
            return
        projection = project_events(events)
        groups = (
            ("token", projection.token_rows),
            ("minute", projection.token_minute_rows),
            ("retrieval", projection.retrieval_rows),
            ("context", projection.context_rows),
        )
        rows = []
        for kind, values in groups:
            for key, value in values.items():
                count, result_count = value if kind == "retrieval" else (value, 0)
                identity = json.dumps([kind, *key], ensure_ascii=False, separators=(",", ":"))
                rows.append(
                    {
                        "service_name": self._service_name,
                        "bucket_id": hashlib.sha256(identity.encode()).hexdigest(),
                        "kind": kind,
                        "account_id": key[0],
                        "user_id": key[1],
                        "date_utc": key[2],
                        "dimensions": list(key),
                        "count": count,
                        "result_count": result_count,
                    }
                )
        async with self._engine.begin() as connection:
            # Stable lock order avoids counter-update deadlocks between replicas.
            for row in sorted(rows, key=lambda row: row["bucket_id"]):
                statement = mysql_insert(buckets).values(**row)
                await connection.execute(
                    statement.on_duplicate_key_update(
                        count=buckets.c.count + statement.inserted.count,
                        result_count=buckets.c.result_count + statement.inserted.result_count,
                    )
                )
            if projection.audit_rows:
                await connection.execute(
                    insert(audit),
                    [
                        dict(
                            service_name=self._service_name,
                            **dict(zip(AUDIT_FIELDS, row, strict=False)),
                        )
                        for row in projection.audit_rows
                    ],
                )
            max_dates = SQLiteUsageAuditStore._usage_max_dates(projection)
            for account_id, max_date in sorted(max_dates.items()):
                for minute in (False, True):
                    days = (
                        (
                            min(MINUTE_RETENTION_DAYS, self._usage_retention_days)
                            if self._usage_retention_days > 0
                            else MINUTE_RETENTION_DAYS
                        )
                        if minute
                        else self._usage_retention_days
                    )
                    if days <= 0:
                        continue
                    cutoff = (date.fromisoformat(max_date) - timedelta(days=days - 1)).isoformat()
                    kind_filter = (
                        buckets.c.kind == "minute" if minute else buckets.c.kind != "minute"
                    )
                    await connection.execute(
                        delete(buckets).where(
                            *self._scope(buckets, account_id),
                            kind_filter,
                            buckets.c.date_utc < cutoff,
                        )
                    )
            for account_id in sorted(projection.touched_audit_accounts):
                await self._trim_audit(connection, account_id)

    async def _trim_audit(self, connection, account_id):
        scope = self._scope(audit, account_id)
        if self._audit_retention_days > 0:
            latest = (
                await connection.execute(select(func.max(audit.c.created_at)).where(*scope))
            ).scalar_one_or_none()
            if latest:
                cutoff = (
                    date.fromisoformat(latest[:10])
                    - timedelta(
                        days=self._audit_retention_days - 1,
                    )
                ).isoformat()
                await connection.execute(delete(audit).where(*scope, audit.c.created_at < cutoff))
        if self._audit_retention_per_account > 0:
            cutoff = (
                await connection.execute(
                    select(audit.c.created_at, audit.c.id)
                    .where(
                        *scope,
                    )
                    .order_by(audit.c.created_at.desc(), audit.c.id.desc())
                    .offset(
                        self._audit_retention_per_account,
                    )
                    .limit(1)
                )
            ).first()
            if cutoff:
                await connection.execute(
                    delete(audit).where(
                        *scope,
                        or_(
                            audit.c.created_at < cutoff.created_at,
                            and_(audit.c.created_at == cutoff.created_at, audit.c.id <= cutoff.id),
                        ),
                    )
                )

    async def delete_data(self, *, account_id, user_id=None):
        names = {
            "token": "usage_token_hourly",
            "minute": "usage_token_minute",
            "retrieval": "usage_retrieval_hourly",
            "context": "usage_context_write_bucket",
        }
        result = {}
        async with self._engine.begin() as connection:
            for kind, name in names.items():
                deleted = await connection.execute(
                    delete(buckets).where(
                        *self._scope(buckets, account_id, user_id),
                        buckets.c.kind == kind,
                    )
                )
                result[name] = deleted.rowcount
            deleted = await connection.execute(
                delete(audit).where(
                    *self._scope(audit, account_id, user_id),
                )
            )
            result["request_audit"] = deleted.rowcount
        return result

    async def _rows(self, kind, account_id, start, end, user_id=None):
        start, end = start.astimezone(UTC), end.astimezone(UTC)
        # Match the existing UTC bucket boundary contract, including fractional-
        # hour timezones. Hourly reads compare hours; minute reads compare minutes.
        if kind == "minute":
            start = start.replace(second=0, microsecond=0)
            end = end.replace(second=0, microsecond=0)
        else:
            start = start.replace(minute=0, second=0, microsecond=0)
            end = end.replace(minute=0, second=0, microsecond=0)
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        select(buckets).where(
                            *self._scope(buckets, account_id, user_id),
                            buckets.c.kind == kind,
                            buckets.c.date_utc >= start.date().isoformat(),
                            buckets.c.date_utc <= end.date().isoformat(),
                        )
                    )
                )
                .mappings()
                .all()
            )
        for row in rows:
            key = row["dimensions"]
            minute = key[3] if kind == "minute" else key[3] * 60
            timestamp = datetime.fromisoformat(key[2]).replace(tzinfo=UTC) + timedelta(
                minutes=minute
            )
            if start <= timestamp < end:
                yield key, row["count"], timestamp

    async def get_window_tokens(self, *, account_id, utc_start, utc_end, user_id=None):
        totals = dict.fromkeys(DAILY_TOKEN_KEYS, 0)
        async for key, count, _ in self._rows("token", account_id, utc_start, utc_end, user_id):
            name = f"{key[4]}_{key[5]}"
            if name in totals:
                totals[name] += count
        return {**totals, "total": sum(totals.values())}

    async def get_today_tokens(self, *, account_id, user_date, tz, user_id=None):
        start, end = _user_day_window_utc(date.fromisoformat(user_date), tz)
        return await self.get_window_tokens(
            account_id=account_id, utc_start=start, utc_end=end, user_id=user_id
        )

    async def get_minute_tokens(self, *, account_id, utc_start, utc_end, user_id=None):
        result = {}
        async for key, count, timestamp in self._rows(
            "minute", account_id, utc_start, utc_end, user_id
        ):
            name = "rerank" if key[4] == "rerank" else f"{key[4]}_{key[5]}"
            if name in MINUTE_TOKEN_KEYS:
                result.setdefault(timestamp, dict.fromkeys(MINUTE_TOKEN_KEYS, 0))[name] += count
        return result

    async def get_today_retrievals(self, *, account_id, user_date, tz, user_id=None):
        start, end = _user_day_window_utc(date.fromisoformat(user_date), tz)
        totals = {"find": 0, "search": 0}
        async for key, count, _ in self._rows("retrieval", account_id, start, end, user_id):
            if key[4] in totals and key[5] == "success":
                totals[key[4]] += count
        return {**totals, "total": sum(totals.values())}

    async def get_token_series(
        self,
        *,
        account_id,
        start_user_date,
        end_user_date,
        bucket,
        tz,
        user_id=None,
    ):
        start, _ = _user_day_window_utc(date.fromisoformat(start_user_date), tz)
        _, end = _user_day_window_utc(date.fromisoformat(end_user_date), tz)
        result = {
            day: {"date": day, **dict.fromkeys(DAILY_TOKEN_KEYS, 0)}
            for day in _date_range(start_user_date, end_user_date)
        }
        async for key, count, timestamp in self._rows("token", account_id, start, end, user_id):
            day, name = timestamp.astimezone(tz).date().isoformat(), f"{key[4]}_{key[5]}"
            if day in result and name in DAILY_TOKEN_KEYS:
                result[day][name] += count
        return list(result.values())

    async def get_context_commit_heatmap(
        self,
        *,
        account_id,
        start_user_date,
        end_user_date,
        bucket,
        tz,
        user_id=None,
    ):
        size = 4 if bucket == "4h" else 1
        start, _ = _user_day_window_utc(date.fromisoformat(start_user_date), tz)
        _, end = _user_day_window_utc(date.fromisoformat(end_user_date), tz)
        result = {
            (day, hour): SQLiteUsageAuditStore._empty_context_row(day, hour)
            for day in _date_range(start_user_date, end_user_date)
            for hour in range(0, 24, size)
        }
        async for key, count, timestamp in self._rows("context", account_id, start, end, user_id):
            local = timestamp.astimezone(tz)
            slot = result.get((local.date().isoformat(), local.hour // size * size))
            name = key[4].replace(".", "_")
            if slot is not None:
                if name in slot:
                    slot[name] += count
                slot["total"] += count
        return [result[key] for key in sorted(result)]

    async def get_request_samples(
        self,
        *,
        account_id,
        utc_start,
        user_id=None,
        limit=REQUEST_SAMPLE_LIMIT,
    ):
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(
                        audit.c.api_type,
                        audit.c.status_code,
                        audit.c.duration_ms,
                        audit.c.created_at,
                    )
                    .where(
                        *self._scope(audit, account_id, user_id),
                        audit.c.created_at >= utc_start.astimezone(UTC).isoformat(),
                    )
                    .order_by(audit.c.created_at.desc(), audit.c.id.desc())
                    .limit(max(limit, 1))
                )
            ).mappings()
            return [dict(row) for row in rows]

    async def query_audit_logs(
        self,
        *,
        account_id,
        user_id=None,
        request_id=None,
        statuses=None,
        api_types=None,
        page=1,
        page_size=10,
    ):
        conditions = self._scope(audit, account_id, user_id)
        if request_id:
            conditions.append(audit.c.request_id == request_id)
        if api_types:
            conditions.append(audit.c.api_type.in_(api_types))
        status_conditions = []
        for status in statuses or []:
            value = str(status).strip().lower()
            if value in ("success", "ok"):
                status_conditions.append(audit.c.status_code.between(200, 399))
            elif value in ("error", "failed"):
                status_conditions.append(audit.c.status_code >= 400)
            elif len(value) == 3 and value.endswith("xx") and value[0].isdigit():
                status_conditions.append(
                    audit.c.status_code.between(int(value[0]) * 100, int(value[0]) * 100 + 99)
                )
            elif value:
                status_conditions.append(audit.c.status_code == safe_int(value))
        if status_conditions:
            conditions.append(or_(*status_conditions))
        async with self._engine.connect() as connection:
            total = (
                await connection.execute(
                    select(func.count())
                    .select_from(audit)
                    .where(
                        *conditions,
                    )
                )
            ).scalar_one()
            success = (
                await connection.execute(
                    select(func.count())
                    .select_from(audit)
                    .where(
                        *conditions,
                        audit.c.status_code.between(200, 399),
                    )
                )
            ).scalar_one()
            rows = (
                await connection.execute(
                    select(*(audit.c[name] for name in AUDIT_FIELDS))
                    .where(
                        *conditions,
                    )
                    .order_by(audit.c.created_at.desc(), audit.c.id.desc())
                    .limit(page_size)
                    .offset(
                        max(page - 1, 0) * page_size,
                    )
                )
            ).mappings()
            return {
                "total": total,
                "success_rate": success / total if total else 0.0,
                "page": page,
                "page_size": page_size,
                "items": [SQLiteUsageAuditStore._audit_item(row) for row in rows],
            }
