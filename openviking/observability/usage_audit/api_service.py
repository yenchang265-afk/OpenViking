# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Read service for product Usage/Audit APIs.

The store always persists UTC. The viewer's timezone is resolved per request
from the `?timezone=` query parameter (IANA name, e.g. `Asia/Shanghai`) and
falls back to the server-default tz from config when absent or invalid.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Sequence

from openviking.observability.events import ObservabilityEvent, get_event_bus
from openviking.server.identity import RequestContext, Role
from openviking_cli.exceptions import InvalidArgumentError

from .inventory import ContextInventoryProvider
from .store import UsageAuditStore
from .time import resolve_usage_timezone, resolve_user_timezone

# Token series in the TPM trend; rerank is included so the peak covers every
# model call that spends tokens.
TOKEN_TYPES = ("vlm_input", "vlm_output", "embedding_input", "bot_input", "bot_output", "rerank")
# Bot reports carry their own call times; older or future times are recorded as received.
BOT_CALL_MAX_AGE = timedelta(hours=1)
# window -> (window length in minutes, bucket size in minutes). Buckets stay at or
# under ~360 points; each still reports its busiest single minute.
TOKEN_RATE_WINDOWS = {
    "1h": (60, 1),
    "6h": (360, 1),
    "24h": (1440, 5),
    "7d": (10080, 60),
}

# Request health reads audit rows, whose retention is capped per account, so a
# busy account may cover less than the whole window; `since` reports how much.
REQUEST_HEALTH_WINDOWS = {"1h": timedelta(hours=1), "24h": timedelta(hours=24)}
RETRIEVAL_API_TYPES = frozenset({"search.find", "search.search"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _token_rate_bounds(now: datetime, window: str) -> tuple[datetime, datetime, int]:
    """Return `(start, end, bucket_minutes)` with the current minute included.

    `end` is rounded up to the bucket size so every bucket is aligned on a
    whole multiple of it.
    """
    total_minutes, bucket_minutes = TOKEN_RATE_WINDOWS[window]
    current_end = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    bucket = timedelta(minutes=bucket_minutes)
    remainder = (current_end - datetime(1970, 1, 1, tzinfo=timezone.utc)) % bucket
    end = current_end + (bucket - remainder if remainder else timedelta(0))
    return end - timedelta(minutes=total_minutes), end, bucket_minutes


def _recent_token_window(now: datetime) -> tuple[datetime, datetime]:
    """Return the UTC `[start, end)` hour buckets covering the previous and current hour.

    Tokens are persisted per UTC hour, so a true rolling 60-minute window is not
    available; the previous full hour plus the current partial hour is the
    smallest window that never reads as zero right after an hour boundary.
    """
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    return current_hour - timedelta(hours=1), current_hour + timedelta(hours=1)


def _percentile(sorted_values: Sequence[float], percent: int) -> float:
    """Nearest-rank percentile of an ascending, non-empty sequence."""
    rank = max(math.ceil(percent / 100 * len(sorted_values)), 1)
    return sorted_values[rank - 1]


def _latency_summary(durations: Sequence[float]) -> dict[str, float] | None:
    if not durations:
        return None
    ordered = sorted(durations)
    return {"p50": round(_percentile(ordered, 50), 1), "p95": round(_percentile(ordered, 95), 1)}


def summarize_request_health(window: str, rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Summarize audit rows (newest first) into error counts and latency percentiles."""
    statuses = [int(row["status_code"]) for row in rows]
    durations = [float(row["duration_ms"]) for row in rows]
    retrieval = [
        float(row["duration_ms"]) for row in rows if row["api_type"] in RETRIEVAL_API_TYPES
    ]
    server_errors = sum(1 for status in statuses if status >= 500)
    return {
        "window": window,
        "sample_size": len(rows),
        "since": rows[-1]["created_at"] if rows else None,
        "server_errors": server_errors,
        "client_errors": sum(1 for status in statuses if 400 <= status < 500),
        "error_rate": round(server_errors / len(rows), 4) if rows else 0.0,
        "latency_ms": _latency_summary(durations),
        "retrieval": {"count": len(retrieval), "latency_ms": _latency_summary(retrieval)},
    }


class UsageAuditQueryService:
    """High-level query facade used by HTTP readers."""

    def __init__(
        self,
        *,
        store: UsageAuditStore,
        inventory: ContextInventoryProvider,
        timezone_name: str = "local",
    ) -> None:
        self._store = store
        self._inventory = inventory
        self._default_tz = resolve_usage_timezone(timezone_name)

    def _resolve_tz(self, timezone_name: str | None):
        return resolve_user_timezone(timezone_name, fallback=self._default_tz)

    @staticmethod
    def _usage_user_id(ctx: RequestContext) -> str | None:
        if ctx.role in (Role.ROOT, Role.ADMIN):
            return None
        return ctx.user.user_id

    @staticmethod
    def _audit_user_id(ctx: RequestContext) -> str | None:
        if ctx.role in (Role.ROOT, Role.ADMIN):
            return None
        return ctx.user.user_id

    def today(self, timezone_name: str | None = None) -> str:
        """Return today's date in the viewer's timezone (or the default)."""
        tz = self._resolve_tz(timezone_name)
        return datetime.now(tz).date().isoformat()

    async def dashboard_summary(
        self, ctx: RequestContext, *, timezone_name: str | None = None
    ) -> dict[str, Any]:
        """Return all Dashboard top-card data for the viewer's tz."""
        tz = self._resolve_tz(timezone_name)
        today = datetime.now(tz).date().isoformat()
        context_counts = await self._inventory.get_counts(ctx)
        user_id = self._usage_user_id(ctx)
        today_tokens = await self._store.get_today_tokens(
            account_id=ctx.account_id, user_date=today, tz=tz, user_id=user_id
        )
        today_retrievals = await self._store.get_today_retrievals(
            account_id=ctx.account_id, user_date=today, tz=tz, user_id=user_id
        )
        tokens_per_minute = await self._tokens_per_minute(ctx, user_id=user_id)
        return {
            "context_counts": context_counts,
            "today_tokens": today_tokens,
            "today_retrievals": today_retrievals,
            "tokens_per_minute": tokens_per_minute,
        }

    async def _tokens_per_minute(
        self, ctx: RequestContext, *, user_id: str | None
    ) -> dict[str, float | int]:
        """Return average tokens per minute since the start of the previous UTC hour."""
        now = _utc_now()
        utc_start, utc_end = _recent_token_window(now)
        tokens = await self._store.get_window_tokens(
            account_id=ctx.account_id, utc_start=utc_start, utc_end=utc_end, user_id=user_id
        )
        elapsed_minutes = (now - utc_start).total_seconds() / 60
        result: dict[str, float | int] = {
            key: round(value / elapsed_minutes, 1) for key, value in tokens.items()
        }
        result["window_minutes"] = round(elapsed_minutes)
        return result

    async def token_series(
        self,
        *,
        ctx: RequestContext,
        start_date: str,
        end_date: str,
        bucket: str,
        timezone_name: str | None = None,
    ) -> dict[str, Any]:
        """Return token usage series in the viewer's tz."""
        tz = self._resolve_tz(timezone_name)
        self._validate_date_range(start_date, end_date)
        items = await self._store.get_token_series(
            account_id=ctx.account_id,
            start_user_date=start_date,
            end_user_date=end_date,
            bucket=bucket,
            tz=tz,
            user_id=self._usage_user_id(ctx),
        )
        return {"start_date": start_date, "end_date": end_date, "bucket": bucket, "items": items}

    async def token_rate_series(self, *, ctx: RequestContext, window: str) -> dict[str, Any]:
        """Return tokens-per-minute buckets and the busiest minute in a recent window."""
        if window not in TOKEN_RATE_WINDOWS:
            raise InvalidArgumentError(f"window must be one of {', '.join(TOKEN_RATE_WINDOWS)}")
        now = _utc_now()
        start, end, bucket_minutes = _token_rate_bounds(now, window)
        minutes = await self._store.get_minute_tokens(
            account_id=ctx.account_id,
            utc_start=start,
            utc_end=end,
            user_id=self._usage_user_id(ctx),
        )
        # Minutes after the current one have not happened yet; averages divide
        # only by elapsed minutes.
        elapsed_end = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        bucket = timedelta(minutes=bucket_minutes)
        grouped: dict[int, list[dict[str, int]]] = {}
        for ts, counts in minutes.items():
            grouped.setdefault((ts - start) // bucket, []).append(counts)
        items = [
            self._token_rate_bucket(
                grouped.get(index, []), start + index * bucket, bucket, elapsed_end
            )
            for index in range((end - start) // bucket)
        ]
        peak_minute = max(
            minutes,
            key=lambda ts: (sum(minutes[ts].values()), ts),
            default=None,
        )
        peak = None
        if peak_minute is not None and sum(minutes[peak_minute].values()) > 0:
            peak = {
                "minute": peak_minute.isoformat(),
                **minutes[peak_minute],
                "total": sum(minutes[peak_minute].values()),
            }
        window_total = sum(sum(counts.values()) for counts in minutes.values())
        window_minutes = (min(end, elapsed_end) - start).total_seconds() / 60
        return {
            "window": window,
            "bucket_minutes": bucket_minutes,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "items": items,
            "peak": peak,
            "average_total": round(window_total / window_minutes, 1),
        }

    @staticmethod
    def _token_rate_bucket(
        counts: list[dict[str, int]],
        bucket_start: datetime,
        bucket: timedelta,
        elapsed_end: datetime,
    ) -> dict[str, Any]:
        elapsed = (min(bucket_start + bucket, elapsed_end) - bucket_start).total_seconds() / 60
        elapsed = max(elapsed, 1)
        sums = {key: sum(c.get(key, 0) for c in counts) for key in TOKEN_TYPES}
        item: dict[str, Any] = {"start": bucket_start.isoformat()}
        item.update({key: round(value / elapsed, 1) for key, value in sums.items()})
        item["total"] = round(sum(sums.values()) / elapsed, 1)
        item["peak_total"] = max((sum(c.values()) for c in counts), default=0)
        return item

    def record_bot_calls(self, ctx: RequestContext, calls: list[dict[str, Any]]) -> int:
        """Publish VikingBot model calls as `bot.call` events for the requesting user.

        The bot runs in its own process, so its calls are reported here instead of
        reaching this server's event bus directly. Returns the number of calls accepted.
        """
        now = _utc_now()
        bus = get_event_bus()
        for call in calls:
            occurred_at = call.get("occurred_at")
            if occurred_at is not None:
                if occurred_at.tzinfo is None:
                    occurred_at = occurred_at.replace(tzinfo=timezone.utc)
                occurred_at = occurred_at.astimezone(timezone.utc)
            if occurred_at is None or not now - BOT_CALL_MAX_AGE <= occurred_at <= now:
                occurred_at = now
            bus.publish(
                ObservabilityEvent(
                    event_name="bot.call",
                    payload={
                        "provider": call.get("provider") or "",
                        "model_name": call.get("model_name") or "",
                        "prompt_tokens": call["prompt_tokens"],
                        "completion_tokens": call["completion_tokens"],
                    },
                    timestamp=occurred_at,
                    account_id=ctx.account_id,
                    user_id=ctx.user.user_id,
                )
            )
        return len(calls)

    async def context_commits(
        self,
        *,
        ctx: RequestContext,
        start_date: str,
        end_date: str,
        bucket: str,
        timezone_name: str | None = None,
    ) -> dict[str, Any]:
        """Return context write heatmap rows in the viewer's tz."""
        tz = self._resolve_tz(timezone_name)
        self._validate_date_range(start_date, end_date)
        items = await self._store.get_context_commit_heatmap(
            account_id=ctx.account_id,
            start_user_date=start_date,
            end_user_date=end_date,
            bucket=bucket,
            tz=tz,
            user_id=self._usage_user_id(ctx),
        )
        return {"start_date": start_date, "end_date": end_date, "bucket": bucket, "items": items}

    async def request_health(self, *, ctx: RequestContext, window: str) -> dict[str, Any]:
        """Return server error rate and latency percentiles for recent requests."""
        span = REQUEST_HEALTH_WINDOWS.get(window)
        if span is None:
            raise InvalidArgumentError(f"window must be one of {sorted(REQUEST_HEALTH_WINDOWS)}")
        rows = await self._store.get_request_samples(
            account_id=ctx.account_id,
            utc_start=_utc_now() - span,
            user_id=self._audit_user_id(ctx),
        )
        return summarize_request_health(window, rows)

    async def audit_logs(
        self,
        *,
        ctx: RequestContext,
        request_id: str | None,
        statuses: list[str],
        api_types: list[str],
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        """Return filtered request audit rows.

        `created_at` is returned as a UTC ISO string; the client formats it in
        the viewer's locale on render.
        """
        return await self._store.query_audit_logs(
            account_id=ctx.account_id,
            user_id=self._audit_user_id(ctx),
            request_id=request_id,
            statuses=statuses,
            api_types=api_types,
            page=max(int(page), 1),
            page_size=min(max(int(page_size), 1), 100),
        )

    @staticmethod
    def _validate_date_range(start_date: str, end_date: str) -> None:
        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
        except ValueError as exc:
            raise InvalidArgumentError("date must be in YYYY-MM-DD format") from exc
        if end < start:
            raise InvalidArgumentError("end_date must be greater than or equal to start_date")
