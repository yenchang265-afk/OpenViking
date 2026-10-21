# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Console BFF endpoints for usage and audit data."""

from __future__ import annotations

import asyncio
import os
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from openviking.metrics.ragfs_cache import summarize_cache_metrics
from openviking.server.auth import require_role
from openviking.server.dependencies import get_service_or_none
from openviking.server.identity import RequestContext, Role
from openviking.server.models import Response
from openviking.server.routers import bot

router = APIRouter(prefix="/api/v1/console", tags=["console"])

# Bounds one bot report; the bot flushes every few seconds, so real batches are small.
MAX_BOT_CALLS_PER_REPORT = 1000
MAX_BOT_CALL_TOKENS = 100_000_000


class BotModelCall(BaseModel):
    """Token usage of one model call made by VikingBot."""

    provider: str = Field(default="", max_length=128)
    model_name: str = Field(default="", max_length=256)
    prompt_tokens: int = Field(default=0, ge=0, le=MAX_BOT_CALL_TOKENS)
    completion_tokens: int = Field(default=0, ge=0, le=MAX_BOT_CALL_TOKENS)
    occurred_at: Optional[datetime] = None


class BotUsageReport(BaseModel):
    calls: list[BotModelCall] = Field(max_length=MAX_BOT_CALLS_PER_REPORT)


def _split_multi(values: Optional[list[str]]) -> list[str]:
    if not values:
        return []
    result: list[str] = []
    for value in values:
        result.extend(part.strip() for part in str(value).split(",") if part.strip())
    return result


def _runtime_service(request: Request):
    runtime = getattr(request.app.state, "usage_audit_runtime", None)
    if runtime is None:
        return None
    return runtime.api_service


def _ok_response(result):
    return Response(status="ok", result=result).model_dump(exclude_none=True)


def _disabled_response():
    return _ok_response(
        {
            "enabled": False,
            "message": "Usage/Audit is disabled or not initialized.",
        }
    )


@router.get("/dashboard/summary")
async def dashboard_summary(
    request: Request,
    timezone: Optional[str] = Query(
        None,
        description="IANA viewer timezone (e.g. Asia/Shanghai). Defaults to server tz.",
    ),
    _ctx: RequestContext = require_role(Role.ROOT, Role.ADMIN, Role.USER),
):
    """Return Dashboard top-card data."""
    service = _runtime_service(request)
    if service is None:
        return _disabled_response()
    return _ok_response(await service.dashboard_summary(_ctx, timezone_name=timezone))


@router.get("/cache")
async def cache_stats(
    _ctx: RequestContext = require_role(Role.ROOT, Role.ADMIN, Role.USER),
):
    """Return CacheFS hit rates since server start, overall and per operation."""
    client = getattr(get_service_or_none(), "_agfs_client", None)
    if client is None or not hasattr(client, "metrics"):
        return _ok_response({"enabled": False, "message": "CacheFS is not available."})
    records = await asyncio.to_thread(client.metrics)
    return _ok_response(summarize_cache_metrics(records))


@router.get("/tokens")
async def token_series(
    request: Request,
    start_date: str = Query(..., description="Start date (viewer-local) in YYYY-MM-DD"),
    end_date: str = Query(..., description="End date (viewer-local) in YYYY-MM-DD"),
    bucket: str = Query("day", pattern="^(day)$"),
    timezone: Optional[str] = Query(
        None,
        description="IANA viewer timezone (e.g. Asia/Shanghai). Defaults to server tz.",
    ),
    _ctx: RequestContext = require_role(Role.ROOT, Role.ADMIN, Role.USER),
):
    """Return token usage trend for a date range."""
    service = _runtime_service(request)
    if service is None:
        return _disabled_response()
    result = await service.token_series(
        ctx=_ctx,
        start_date=start_date,
        end_date=end_date,
        bucket=bucket,
        timezone_name=timezone,
    )
    return _ok_response(result)


@router.get("/tokens/rate")
async def token_rate_series(
    request: Request,
    window: str = Query("24h", pattern="^(1h|6h|24h|7d)$"),
    _ctx: RequestContext = require_role(Role.ROOT, Role.ADMIN, Role.USER),
):
    """Return tokens-per-minute trend buckets and the peak minute for a recent window."""
    service = _runtime_service(request)
    if service is None:
        return _disabled_response()
    return _ok_response(await service.token_rate_series(ctx=_ctx, window=window))


@router.post("/usage/bot")
async def report_bot_usage(
    request: Request,
    body: BotUsageReport,
    x_gateway_token: str = Header(default=""),
    _ctx: RequestContext = require_role(Role.ROOT, Role.ADMIN, Role.USER),
):
    """Record VikingBot model-call token usage for the authenticated user.

    Only the Bot gateway this server manages (``--with-bot``) may report, proven by
    the gateway token it shares with this server; user keys alone cannot add usage.
    """
    token = os.environ.get("OPENVIKING_BOT_STUDIO_TOKEN") or bot.BOT_API_KEY
    if not (token and secrets.compare_digest(token.encode(), x_gateway_token.encode())):
        raise HTTPException(403, "Bot usage reports require the managed Bot gateway token")
    service = _runtime_service(request)
    if service is None:
        return _disabled_response()
    calls = [call.model_dump() for call in body.calls]
    return _ok_response({"accepted": service.record_bot_calls(_ctx, calls)})


@router.get("/context-commits")
async def context_commits(
    request: Request,
    start_date: str = Query(..., description="Start date (viewer-local) in YYYY-MM-DD"),
    end_date: str = Query(..., description="End date (viewer-local) in YYYY-MM-DD"),
    bucket: str = Query("hour", pattern="^(hour|4h)$"),
    timezone: Optional[str] = Query(
        None,
        description="IANA viewer timezone (e.g. Asia/Shanghai). Defaults to server tz.",
    ),
    _ctx: RequestContext = require_role(Role.ROOT, Role.ADMIN, Role.USER),
):
    """Return context write heatmap rows for a date range."""
    service = _runtime_service(request)
    if service is None:
        return _disabled_response()
    result = await service.context_commits(
        ctx=_ctx,
        start_date=start_date,
        end_date=end_date,
        bucket=bucket,
        timezone_name=timezone,
    )
    return _ok_response(result)


@router.get("/audit")
async def audit_logs(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    request_id: Optional[str] = Query(None),
    status: Optional[list[str]] = Query(None),
    api_type: Optional[list[str]] = Query(None),
    _ctx: RequestContext = require_role(Role.ROOT, Role.ADMIN, Role.USER),
):
    """Return filtered request audit logs."""
    service = _runtime_service(request)
    if service is None:
        return _disabled_response()
    result = await service.audit_logs(
        ctx=_ctx,
        request_id=request_id,
        statuses=_split_multi(status),
        api_types=_split_multi(api_type),
        page=page,
        page_size=page_size,
    )
    return _ok_response(result)
