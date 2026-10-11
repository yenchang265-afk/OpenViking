# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Push delivery of committed task mutations."""

import asyncio
import threading

import pytest

from openviking.service.task_change_feed import RESYNC, TaskChangeFeed
from openviking.service.task_store import PersistentTaskStore
from openviking.service.task_tracker import TaskRecord, TaskTracker
from tests.test_task_tracker import _FakeAgfs

pytestmark = pytest.mark.asyncio


def _record(task_id: str = "t1", user_id: str = "alice") -> TaskRecord:
    return TaskRecord(task_id=task_id, task_type="add_resource", account_id="acme", user_id=user_id)


async def test_delivers_only_matching_tasks():
    feed = TaskChangeFeed()
    sub = feed.subscribe(lambda task: task.user_id == "alice")

    feed.publish(_record("bob-task", user_id="bob"), lambda: {"task_id": "bob-task"})
    feed.publish(_record("alice-task"), lambda: {"task_id": "alice-task"})

    assert await sub.next(1) == {"task_id": "alice-task"}
    with pytest.raises(asyncio.TimeoutError):
        await sub.next(0.05)


async def test_publish_from_another_thread_reaches_subscriber_loop():
    feed = TaskChangeFeed()
    sub = feed.subscribe(lambda task: True)

    thread = threading.Thread(target=feed.publish, args=(_record(), lambda: {"task_id": "t1"}))
    thread.start()
    thread.join()

    assert await sub.next(1) == {"task_id": "t1"}


async def test_overflow_drops_backlog_and_asks_for_resync():
    feed = TaskChangeFeed(max_pending=2)
    sub = feed.subscribe(lambda task: True)

    for index in range(3):
        feed.publish(_record(f"t{index}"), lambda index=index: {"task_id": f"t{index}"})
    feed.publish(_record("after"), lambda: {"task_id": "after"})

    assert await sub.next(1) is RESYNC
    assert await sub.next(1) == {"task_id": "after"}


async def test_unsubscribed_and_payload_skipped_without_listeners():
    feed = TaskChangeFeed()
    sub = feed.subscribe(lambda task: True)
    feed.unsubscribe(sub)
    built = []

    feed.publish(_record(), lambda: built.append(1) or {})

    assert not feed.has_subscribers()
    assert built == []


async def test_failing_predicate_does_not_block_other_subscribers():
    feed = TaskChangeFeed()
    feed.subscribe(lambda task: 1 / 0)
    healthy = feed.subscribe(lambda task: True)

    feed.publish(_record(), lambda: {"task_id": "t1"})

    assert await healthy.next(1) == {"task_id": "t1"}


async def test_tracker_publishes_committed_mutations():
    tracker = TaskTracker(store=PersistentTaskStore(_FakeAgfs()))
    sub = tracker.change_feed.subscribe(lambda task: True)

    task = await tracker.create("add_resource", account_id="acme", user_id="alice")
    await tracker.complete(
        task.task_id, {"root_uri": "viking://r"}, account_id="acme", user_id="alice"
    )

    events = [await sub.next(1)]
    while events[-1]["status"] != "completed":
        events.append(await sub.next(1))
    assert (events[0]["task_id"], events[0]["status"]) == (task.task_id, "pending")
    assert events[-1]["result"] == {"root_uri": "viking://r"}
    assert all("auth" not in event for event in events)
