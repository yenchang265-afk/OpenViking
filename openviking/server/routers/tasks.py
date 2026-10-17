# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Task tracking endpoints for OpenViking HTTP Server.

Provides observability for background operations (e.g. session commit
with ``wait=false``).  Callers receive a ``task_id`` and can poll these
endpoints to check completion, results, or errors.
"""

import asyncio
import json
from typing import Any, AsyncGenerator, Callable, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from openviking.server.auth import get_request_context
from openviking.server.identity import RequestContext, Role
from openviking.server.models import Response
from openviking.service.task_change_feed import RESYNC, TaskChangeFeed
from openviking.service.task_store import SYSTEM_TASK_ACCOUNT_ID, SYSTEM_TASK_USER_ID
from openviking.service.task_tracker import TaskRecord, get_task_tracker
from openviking_cli.exceptions import (
    FailedPreconditionError,
    OpenVikingError,
    PermissionDeniedError,
)

router = APIRouter(prefix="/api/v1", tags=["tasks"])

# Keeps idle streams open through proxies and lets clients detect dead ones.
TASK_EVENTS_HEARTBEAT_SECONDS = 15.0


class _ClosingStreamingResponse(StreamingResponse):
    """Close the body generator however the response ends.

    On client disconnect Starlette abandons the generator suspended at
    ``yield``; without an explicit close its cleanup waits for GC.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.body_iterator.aclose()


def _task_visibility(
    ctx: RequestContext, task_type: Optional[str], include_internal: bool
) -> Callable[[TaskRecord], bool]:
    """Mirror GET /tasks visibility: ROOT sees every owner, others their own."""

    def visible(task: TaskRecord) -> bool:
        if ctx.role != Role.ROOT and (
            task.account_id != ctx.account_id or task.user_id != ctx.user.user_id
        ):
            return False
        if not include_internal and task.meta.get("internal") is True:
            return False
        return not task_type or task.task_type == task_type

    return visible


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


async def task_event_stream(
    feed: TaskChangeFeed,
    visible: Callable[[TaskRecord], bool],
    *,
    complete: bool,
    heartbeat: float = TASK_EVENTS_HEARTBEAT_SECONDS,
) -> AsyncGenerator[str, None]:
    """Yield SSE frames: ``ready`` once subscribed, then ``task``, ``resync``
    or an idle ``ping``."""
    subscription = feed.subscribe(visible)
    try:
        yield _sse("ready", {"complete": complete})
        while True:
            try:
                item = await subscription.next(heartbeat)
            except asyncio.TimeoutError:
                # An event, not a comment: browser clients never see comments.
                yield _sse("ping", {})
                continue
            yield _sse("resync", {}) if item is RESYNC else _sse("task", item)
    finally:
        feed.unsubscribe(subscription)


@router.get("/tasks/events")
async def stream_task_events(
    request: Request,
    task_type: Optional[str] = Query(None, description="Only push tasks of this type"),
    include_internal: bool = Query(False, description="Include internal Connector child tasks"),
    _ctx: RequestContext = Depends(get_request_context),
):
    """Push background task changes as Server-Sent Events.

    Subscribe first, then read GET /tasks on ``ready`` so no change is missed.
    ``task`` frames carry the same record as GET /tasks/{task_id}; ``resync``
    means changes were dropped and the list must be read again. ``complete`` is
    false with several workers, where only this worker's changes are pushed.
    """
    config = getattr(request.app.state, "config", None)
    complete = getattr(config, "workers", 1) <= 1
    return _ClosingStreamingResponse(
        task_event_stream(
            get_task_tracker().change_feed,
            _task_visibility(_ctx, task_type, include_internal),
            complete=complete,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: str,
    include_events: bool = Query(False, description="Include recorded execution events"),
    _ctx: RequestContext = Depends(get_request_context),
):
    """Get the status of a single background task."""
    tracker = get_task_tracker()
    if _ctx.role == Role.ROOT:
        task = await tracker.get(task_id)
        if task is None:
            task = await tracker.get(task_id, account_id=_ctx.account_id, user_id=_ctx.user.user_id)
        if task is None:
            task = await tracker.get(
                task_id,
                account_id=SYSTEM_TASK_ACCOUNT_ID,
                user_id=SYSTEM_TASK_USER_ID,
            )
    else:
        task = await tracker.get(
            task_id,
            account_id=_ctx.account_id,
            user_id=_ctx.user.user_id,
        )
    if not task:
        raise OpenVikingError(
            "Task not found or expired",
            code="NOT_FOUND",
            details={"resource": task_id, "type": "task"},
        )
    return Response(status="ok", result=task.to_dict(include_events=include_events))


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    _ctx: RequestContext = Depends(get_request_context),
):
    """Request cooperative cancellation of a background task."""
    if _ctx.role == Role.ROOT:
        raise PermissionDeniedError("ROOT may not cancel tasks")
    tracker = get_task_tracker()
    try:
        task = await tracker.cancel(
            task_id,
            account_id=_ctx.account_id,
            user_id=_ctx.user.user_id,
        )
    except ValueError as exc:
        raise FailedPreconditionError(str(exc)) from exc
    if task is None:
        raise OpenVikingError(
            "Task not found or expired",
            code="NOT_FOUND",
            details={"resource": task_id, "type": "task"},
        )
    return Response(status="ok", result=task.to_dict())


@router.get("/tasks")
async def list_tasks(
    task_type: Optional[str] = Query(None, description="Filter by task type (e.g. session_commit)"),
    status: Optional[str] = Query(
        None,
        description="Filter by status (pending/running/cancelling/completed/failed/cancelled)",
    ),
    resource_id: Optional[str] = Query(None, description="Filter by resource ID (e.g. session_id)"),
    include_internal: bool = Query(False, description="Include internal Connector child tasks"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    pagination: Optional[str] = Query(None, pattern="^cursor$"),
    cursor: Optional[str] = Query(None, max_length=2048),
    q: Optional[str] = Query(None, max_length=200),
    _ctx: RequestContext = Depends(get_request_context),
):
    """List background tasks with optional filters."""
    tracker = get_task_tracker()
    if pagination == "cursor":
        from openviking.service.task_pagination import decode_cursor, encode_cursor, page_scope

        filters = {
            "task_type": task_type,
            "status": status,
            "resource_id": resource_id,
            "include_internal": include_internal,
            "q": q,
        }
        scope = page_scope(
            account=_ctx.account_id, user=_ctx.user.user_id, role=str(_ctx.role), **filters
        )
        list_call = (
            tracker.list_root_tasks(
                account_id=_ctx.account_id,
                user_id=_ctx.user.user_id,
                limit=limit + 1,
                before=decode_cursor(cursor, scope),
                task_type=task_type,
                status=status,
                resource_id=resource_id,
                include_internal=include_internal,
                q=q,
            )
            if _ctx.role == Role.ROOT
            else tracker.list_tasks(
                account_id=_ctx.account_id,
                user_id=_ctx.user.user_id,
                limit=limit + 1,
                before=decode_cursor(cursor, scope),
                task_type=task_type,
                status=status,
                resource_id=resource_id,
                include_internal=include_internal,
                q=q,
            )
        )
        tasks = await list_call
        more = len(tasks) > limit
        items = [t.to_dict() for t in tasks[:limit]]
        return Response(
            status="ok",
            result={
                "items": items,
                "has_more": more,
                "next_cursor": encode_cursor(items[-1], scope) if more else None,
            },
        )
    if _ctx.role == Role.ROOT:
        system_tasks = await tracker.list_tasks(
            task_type=task_type,
            status=status,
            resource_id=resource_id,
            limit=limit,
            account_id=SYSTEM_TASK_ACCOUNT_ID,
            user_id=SYSTEM_TASK_USER_ID,
            include_internal=include_internal,
        )
        cached_tasks = await tracker.list_tasks(
            task_type=task_type,
            status=status,
            resource_id=resource_id,
            limit=limit,
            include_internal=include_internal,
        )
        tasks_by_id = {task.task_id: task for task in cached_tasks}
        tasks_by_id.update({task.task_id: task for task in system_tasks})
        tasks = sorted(tasks_by_id.values(), key=lambda task: task.created_at, reverse=True)[:limit]
    else:
        tasks = await tracker.list_tasks(
            task_type=task_type,
            status=status,
            resource_id=resource_id,
            limit=limit,
            account_id=_ctx.account_id,
            user_id=_ctx.user.user_id,
            include_internal=include_internal,
        )
    return Response(status="ok", result=[t.to_dict() for t in tasks])
