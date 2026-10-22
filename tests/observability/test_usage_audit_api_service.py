# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from openviking.observability.usage_audit import api_service as api_service_module
from openviking.observability.usage_audit.api_service import UsageAuditQueryService
from openviking.server.identity import RequestContext, Role
from openviking_cli.exceptions import InvalidArgumentError
from openviking_cli.session.user_id import UserIdentifier

UTC = timezone.utc


class FakeStore:
    def __init__(self) -> None:
        self.audit_call: dict[str, Any] | None = None
        self.token_series_call: dict[str, Any] | None = None
        self.window_tokens_call: dict[str, Any] | None = None

    async def get_today_tokens(self, **_kwargs):
        return {"vlm_input": 0, "vlm_output": 0, "embedding_input": 0, "total": 0}

    async def get_today_retrievals(self, **_kwargs):
        return {"find": 0, "search": 0, "total": 0}

    async def get_window_tokens(self, **kwargs):
        self.window_tokens_call = kwargs
        return {"vlm_input": 900, "vlm_output": 450, "embedding_input": 150, "total": 1500}

    minute_tokens: dict[datetime, dict[str, int]] = {}
    minute_tokens_call: dict[str, Any] | None = None

    async def get_minute_tokens(self, **kwargs):
        self.minute_tokens_call = kwargs
        return self.minute_tokens

    async def get_token_series(self, **kwargs):
        self.token_series_call = kwargs
        return []

    async def query_audit_logs(self, **kwargs):
        self.audit_call = kwargs
        return {"total": 0, "success_rate": 0.0, "page": 1, "page_size": 10, "items": []}


class FakeInventory:
    async def get_counts(self, _ctx):
        return {}


@pytest.mark.asyncio
async def test_admin_metrics_and_audit_logs_are_account_wide():
    store = FakeStore()
    service = UsageAuditQueryService(store=store, inventory=FakeInventory(), timezone_name="UTC")
    ctx = RequestContext(
        user=UserIdentifier(account_id="acct-1", user_id="admin-1"),
        role=Role.ADMIN,
    )

    await service.token_series(
        ctx=ctx,
        start_date="2026-05-01",
        end_date="2026-05-01",
        bucket="day",
    )
    await service.audit_logs(
        ctx=ctx,
        request_id=None,
        statuses=[],
        api_types=[],
        page=1,
        page_size=10,
    )

    assert store.token_series_call is not None
    assert store.audit_call is not None
    assert store.token_series_call["user_id"] is None
    assert store.audit_call["user_id"] is None


@pytest.mark.asyncio
async def test_regular_user_metrics_and_audit_logs_use_current_identity():
    store = FakeStore()
    service = UsageAuditQueryService(store=store, inventory=FakeInventory(), timezone_name="UTC")
    ctx = RequestContext(
        user=UserIdentifier(account_id="acct-1", user_id="alice"),
        role=Role.USER,
    )

    await service.token_series(
        ctx=ctx,
        start_date="2026-05-01",
        end_date="2026-05-01",
        bucket="day",
    )
    await service.audit_logs(
        ctx=ctx,
        request_id=None,
        statuses=[],
        api_types=[],
        page=1,
        page_size=10,
    )

    assert store.token_series_call is not None
    assert store.audit_call is not None
    assert store.token_series_call["user_id"] == "alice"
    assert store.audit_call["user_id"] == "alice"


@pytest.mark.asyncio
async def test_dashboard_summary_reports_tokens_per_minute_since_previous_hour(monkeypatch):
    store = FakeStore()
    service = UsageAuditQueryService(store=store, inventory=FakeInventory(), timezone_name="UTC")
    ctx = RequestContext(
        user=UserIdentifier(account_id="acct-1", user_id="alice"),
        role=Role.USER,
    )
    monkeypatch.setattr(
        api_service_module,
        "_utc_now",
        lambda: datetime(2026, 5, 12, 23, 30, tzinfo=timezone.utc),
    )

    summary = await service.dashboard_summary(ctx)

    # The window spans the previous UTC hour bucket plus the elapsed part of
    # the current one: 22:00 -> 23:30 = 90 minutes.
    assert store.window_tokens_call == {
        "account_id": "acct-1",
        "utc_start": datetime(2026, 5, 12, 22, tzinfo=timezone.utc),
        "utc_end": datetime(2026, 5, 13, 0, tzinfo=timezone.utc),
        "user_id": "alice",
    }
    assert summary["tokens_per_minute"] == {
        "vlm_input": 10.0,
        "vlm_output": 5.0,
        "embedding_input": 1.7,
        "total": 16.7,
        "window_minutes": 90,
    }


def _minute(hour: int, minute: int) -> datetime:
    return datetime(2026, 5, 12, hour, minute, tzinfo=UTC)


def _user_ctx() -> RequestContext:
    return RequestContext(
        user=UserIdentifier(account_id="acct-1", user_id="alice"),
        role=Role.USER,
    )


@pytest.mark.asyncio
async def test_token_rate_series_reports_each_minute_and_the_peak(monkeypatch):
    store = FakeStore()
    store.minute_tokens = {
        _minute(10, 5): {
            "vlm_input": 300,
            "vlm_output": 100,
            "embedding_input": 0,
            "rerank": 0,
        },
        # Rerank-heavy minute: it is the peak only if rerank tokens count.
        _minute(10, 6): {
            "vlm_input": 0,
            "vlm_output": 0,
            "embedding_input": 50,
            "rerank": 1500,
        },
        _minute(10, 30): {
            "vlm_input": 1000,
            "vlm_output": 200,
            "embedding_input": 0,
            "rerank": 0,
        },
    }
    service = UsageAuditQueryService(store=store, inventory=FakeInventory(), timezone_name="UTC")
    monkeypatch.setattr(
        api_service_module, "_utc_now", lambda: datetime(2026, 5, 12, 10, 30, 30, tzinfo=UTC)
    )

    result = await service.token_rate_series(ctx=_user_ctx(), window="1h")

    # The current minute is included, so the hour ends at 10:31.
    assert store.minute_tokens_call == {
        "account_id": "acct-1",
        "utc_start": _minute(9, 31),
        "utc_end": _minute(10, 31),
        "user_id": "alice",
    }
    assert result["window"] == "1h"
    assert result["bucket_minutes"] == 1
    assert result["start"] == "2026-05-12T09:31:00+00:00"
    assert result["end"] == "2026-05-12T10:31:00+00:00"
    items = result["items"]
    assert len(items) == 60
    assert items[0]["start"] == "2026-05-12T09:31:00+00:00"
    by_start = {item["start"]: item for item in items}
    assert by_start["2026-05-12T10:05:00+00:00"] == {
        "start": "2026-05-12T10:05:00+00:00",
        "vlm_input": 300.0,
        "vlm_output": 100.0,
        "embedding_input": 0.0,
        "bot_input": 0.0,
        "bot_output": 0.0,
        "rerank": 0.0,
        "total": 400.0,
        "peak_total": 400,
    }
    assert by_start["2026-05-12T10:06:00+00:00"]["rerank"] == 1500.0
    assert by_start["2026-05-12T10:06:00+00:00"]["total"] == 1550.0
    assert by_start["2026-05-12T10:00:00+00:00"]["total"] == 0.0
    assert result["peak"] == {
        "minute": "2026-05-12T10:06:00+00:00",
        "vlm_input": 0,
        "vlm_output": 0,
        "embedding_input": 50,
        "rerank": 1500,
        "total": 1550,
    }
    assert result["average_total"] == round((400 + 1550 + 1200) / 60, 1)


@pytest.mark.asyncio
async def test_token_rate_series_buckets_keep_the_busiest_minute(monkeypatch):
    store = FakeStore()
    store.minute_tokens = {
        _minute(10, 20): {"vlm_input": 100, "vlm_output": 0, "embedding_input": 0},
        _minute(10, 21): {"vlm_input": 400, "vlm_output": 0, "embedding_input": 0},
        _minute(10, 30): {"vlm_input": 30, "vlm_output": 0, "embedding_input": 0},
    }
    service = UsageAuditQueryService(store=store, inventory=FakeInventory(), timezone_name="UTC")
    monkeypatch.setattr(
        api_service_module, "_utc_now", lambda: datetime(2026, 5, 12, 10, 30, 30, tzinfo=UTC)
    )

    result = await service.token_rate_series(ctx=_user_ctx(), window="24h")

    assert result["bucket_minutes"] == 5
    # Buckets are aligned to 5 minutes, so the window ends at 10:35.
    assert result["end"] == "2026-05-12T10:35:00+00:00"
    assert store.minute_tokens_call["utc_start"] == _minute(10, 35) - timedelta(days=1)
    items = result["items"]
    assert len(items) == 288
    by_start = {item["start"]: item for item in items}
    full = by_start["2026-05-12T10:20:00+00:00"]
    assert full["total"] == 100.0  # (100 + 400) / 5 minutes
    assert full["peak_total"] == 400
    # The current bucket has only one elapsed minute (10:30).
    current = by_start["2026-05-12T10:30:00+00:00"]
    assert current["total"] == 30.0
    assert current["peak_total"] == 30
    assert result["peak"]["minute"] == "2026-05-12T10:21:00+00:00"


@pytest.mark.asyncio
async def test_token_rate_series_has_no_peak_without_tokens(monkeypatch):
    store = FakeStore()
    service = UsageAuditQueryService(store=store, inventory=FakeInventory(), timezone_name="UTC")
    monkeypatch.setattr(
        api_service_module, "_utc_now", lambda: datetime(2026, 5, 12, 10, 30, tzinfo=UTC)
    )

    result = await service.token_rate_series(ctx=_user_ctx(), window="7d")

    assert result["bucket_minutes"] == 60
    assert len(result["items"]) == 168
    assert result["peak"] is None
    assert result["average_total"] == 0.0


@pytest.mark.asyncio
async def test_token_rate_series_rejects_unknown_windows():
    service = UsageAuditQueryService(
        store=FakeStore(), inventory=FakeInventory(), timezone_name="UTC"
    )
    with pytest.raises(InvalidArgumentError):
        await service.token_rate_series(ctx=_user_ctx(), window="2h")


def test_record_bot_calls_publishes_events_for_the_requesting_user(monkeypatch):
    now = datetime(2026, 5, 12, 10, 30, 0, tzinfo=UTC)
    monkeypatch.setattr(api_service_module, "_utc_now", lambda: now)
    published = []

    class Bus:
        def publish(self, event):
            published.append(event)

    monkeypatch.setattr(api_service_module, "get_event_bus", lambda: Bus())
    service = UsageAuditQueryService(store=FakeStore(), inventory=FakeInventory())
    ctx = RequestContext(user=UserIdentifier(account_id="acct-1", user_id="user-1"), role=Role.USER)
    recent = now - timedelta(minutes=2)

    accepted = service.record_bot_calls(
        ctx,
        [
            {
                "provider": "openai",
                "model_name": "m",
                "prompt_tokens": 10,
                "completion_tokens": 4,
                "occurred_at": recent,
            },
            # Stale, future and naive times: stale/future fall back to now, naive is UTC.
            {"prompt_tokens": 1, "completion_tokens": 0, "occurred_at": now - timedelta(days=1)},
            {"prompt_tokens": 1, "completion_tokens": 0, "occurred_at": now + timedelta(hours=1)},
            {
                "prompt_tokens": 1,
                "completion_tokens": 0,
                "occurred_at": recent.replace(tzinfo=None),
            },
        ],
    )

    assert accepted == 4
    assert [event.event_name for event in published] == ["bot.call"] * 4
    assert {(event.account_id, event.user_id) for event in published} == {("acct-1", "user-1")}
    assert published[0].payload == {
        "provider": "openai",
        "model_name": "m",
        "prompt_tokens": 10,
        "completion_tokens": 4,
    }
    assert [event.timestamp for event in published] == [recent, now, now, recent]
