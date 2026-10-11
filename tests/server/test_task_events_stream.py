# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Server-Sent Events stream of task changes."""

import json

import pytest
from starlette.requests import ClientDisconnect
from starlette.routing import Match

import openviking.server.routers.tasks as task_router
from openviking.server.identity import RequestContext, Role
from openviking.service.task_change_feed import TaskChangeFeed
from openviking.service.task_tracker import TaskRecord
from openviking_cli.session.user_id import UserIdentifier

pytestmark = pytest.mark.asyncio


def _ctx(role: Role = Role.USER) -> RequestContext:
    return RequestContext(user=UserIdentifier("acme", "alice"), role=role)


def _record(**overrides) -> TaskRecord:
    fields = {
        "task_id": "t1",
        "task_type": "add_resource",
        "account_id": "acme",
        "user_id": "alice",
    }
    return TaskRecord(**{**fields, **overrides})


def _parse(chunk: str) -> tuple[str, dict]:
    lines = dict(line.split(": ", 1) for line in chunk.strip().splitlines())
    return lines["event"], json.loads(lines["data"])


async def test_user_sees_only_own_visible_tasks_of_requested_type():
    visible = task_router._task_visibility(_ctx(), "add_resource", include_internal=False)

    assert visible(_record())
    assert not visible(_record(user_id="bob"))
    assert not visible(_record(account_id="other"))
    assert not visible(_record(task_type="compile"))
    assert not visible(_record(meta={"internal": True}))


async def test_root_sees_every_owner_like_the_task_list():
    visible = task_router._task_visibility(_ctx(Role.ROOT), None, include_internal=True)

    assert visible(_record(account_id="other", user_id="bob", meta={"internal": True}))


async def test_stream_announces_ready_then_pushes_changes_and_heartbeats():
    feed = TaskChangeFeed()
    stream = task_router.task_event_stream(feed, lambda task: True, complete=True, heartbeat=0.05)

    assert _parse(await anext(stream)) == ("ready", {"complete": True})
    feed.publish(_record(), lambda: {"task_id": "t1", "status": "running"})
    assert _parse(await anext(stream)) == ("task", {"task_id": "t1", "status": "running"})
    assert _parse(await anext(stream)) == ("ping", {})

    await stream.aclose()
    assert not feed.has_subscribers()


async def test_client_disconnect_unsubscribes_immediately():
    feed = TaskChangeFeed()
    response = task_router._ClosingStreamingResponse(
        task_router.task_event_stream(feed, lambda task: True, complete=True),
        media_type="text/event-stream",
    )

    async def send(message):
        if message["type"] == "http.response.body" and message.get("body"):
            raise OSError("client went away")

    async def receive():
        return {"type": "http.disconnect"}

    scope = {"type": "http", "asgi": {"spec_version": "2.4"}}
    with pytest.raises(ClientDisconnect):
        await response(scope, receive, send)

    assert not feed.has_subscribers()


async def test_events_path_is_not_captured_by_task_lookup():
    scope = {"type": "http", "path": "/api/v1/tasks/events", "method": "GET"}

    route = next(r for r in task_router.router.routes if r.matches(scope)[0] == Match.FULL)

    assert route.endpoint is task_router.stream_task_events
