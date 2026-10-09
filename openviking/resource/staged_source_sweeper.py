# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Remove staged-source copies that task cleanup left behind.

An add-resource task deletes its staged bundle when it settles, but nothing
retries that delete if it fails, so a bundle can outlive its task forever.
The sweep is lazy and per user space, like shared-upload cleanup: staging a
new source schedules at most one sweep per space per interval.

Only leaves holding a ``source/`` bundle are touched. Other temp users
(parsers, semantic processing) share ``viking://temp`` and own their leaves.
A bundle is staged moments before its task is created, so bundles staged after
the user's oldest still-active task (less a margin) are never swept, however
long that task has been queued.
"""

import asyncio
import re
import time
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional, Set

from openviking.storage.viking_fs._base import LS_ALL_NODES
from openviking_cli.utils.logger import get_logger

logger = get_logger(__name__)

STAGED_SOURCE_SWEEP_INTERVAL_S = 3600
# Staging precedes task creation by seconds; this absorbs slow staging.
ACTIVE_TASK_MARGIN_S = 3600
# Leaf names come from VikingURI.create_temp_uri: MMDDHHMM_<6 hex>, local time.
_LEAF_NAME = re.compile(r"^(\d{2})(\d{2})(\d{2})(\d{2})_[0-9a-f]{6}$")

_NEXT_SWEEP_AT: Dict[str, float] = {}


def staged_leaf_created_at(name: str, now: datetime) -> Optional[float]:
    """Return a temp leaf's creation timestamp, or None if the name is not a leaf."""
    match = _LEAF_NAME.match(name)
    if match is None:
        return None
    month, day, hour, minute = (int(part) for part in match.groups())
    for year in (now.year, now.year - 1):
        try:
            created = datetime(year, month, day, hour, minute)
        except ValueError:
            continue
        # Names carry no year: a time later than now belongs to last year.
        if created <= now:
            return created.timestamp()
    return None


def _space_uri(ctx: Any) -> str:
    return f"viking://temp/{ctx.user.user_space_name()}"


async def sweep_expired_staged_sources(
    viking_fs: Any,
    ctx: Any,
    ttl_seconds: int,
    *,
    now: Optional[datetime] = None,
    oldest_active_at: Optional[float] = None,
) -> int:
    """Delete the caller's expired, unowned staged bundles; return the count removed."""
    if ttl_seconds <= 0:
        return 0
    now = now or datetime.now()
    cutoff = now.timestamp() - ttl_seconds
    if oldest_active_at is not None:
        cutoff = min(cutoff, oldest_active_at - ACTIVE_TASK_MARGIN_S)
    space_uri = _space_uri(ctx)
    try:
        entries = await viking_fs.ls(
            space_uri,
            show_all_hidden=True,
            node_limit=LS_ALL_NODES,
            ctx=ctx,
        )
    except Exception as exc:
        logger.debug("[StagedSourceSweep] Skipped %s: %s", space_uri, exc)
        return 0

    removed = 0
    for entry in entries:
        if not entry.get("isDir"):
            continue
        leaf_uri = str(entry.get("uri") or "").rstrip("/")
        name = leaf_uri.removeprefix(f"{space_uri}/")
        if not leaf_uri.startswith(f"{space_uri}/") or "/" in name:
            continue
        created_at = staged_leaf_created_at(name, now)
        if created_at is None or created_at >= cutoff:
            continue
        bundle_uri = f"{leaf_uri}/source"
        try:
            if not await viking_fs.exists(bundle_uri, ctx=ctx):
                continue
            await viking_fs.delete_temp(leaf_uri, ctx=ctx)
            # delete_temp logs and swallows rm failures; confirm it is gone.
            if await viking_fs.exists(bundle_uri, ctx=ctx):
                continue
        except Exception as exc:
            logger.warning("[StagedSourceSweep] Failed to remove %s: %s", leaf_uri, exc)
            continue
        removed += 1
        logger.info("[StagedSourceSweep] Removed orphaned staged source %s", leaf_uri)
    return removed


def schedule_staged_source_sweep(
    viking_fs: Any,
    ctx: Any,
    ttl_seconds: int,
    *,
    background_tasks: Set["asyncio.Task[Any]"],
    oldest_active_at: Optional[Callable[[], Awaitable[Optional[float]]]] = None,
) -> bool:
    """Start a background sweep of the caller's space unless one ran recently.

    ``oldest_active_at`` reports when the caller's oldest active task was
    created; if it fails the sweep is skipped rather than risk a live bundle.
    """
    if ttl_seconds <= 0:
        return False
    key = f"{ctx.account_id}/{ctx.user.user_space_name()}"
    now = time.monotonic()
    if now < _NEXT_SWEEP_AT.get(key, 0.0):
        return False
    _NEXT_SWEEP_AT[key] = now + STAGED_SOURCE_SWEEP_INTERVAL_S
    task = asyncio.create_task(_sweep(viking_fs, ctx, ttl_seconds, oldest_active_at))
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    return True


async def _sweep(
    viking_fs: Any,
    ctx: Any,
    ttl_seconds: int,
    oldest_active_at: Optional[Callable[[], Awaitable[Optional[float]]]],
) -> int:
    since = None
    if oldest_active_at is not None:
        try:
            since = await oldest_active_at()
        except Exception as exc:
            logger.warning("[StagedSourceSweep] Skipped; active tasks unknown: %s", exc)
            return 0
    return await sweep_expired_staged_sources(viking_fs, ctx, ttl_seconds, oldest_active_at=since)
