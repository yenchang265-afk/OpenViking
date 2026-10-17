# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Per-task queue progress derived from the task store's Work records."""

import pytest

from openviking.service.task_store import PersistentTaskStore
from openviking.service.task_tracker import TaskTracker
from tests.test_task_tracker import _FakeAgfs

OWNER = {"account_id": "acme", "user_id": "alice"}


@pytest.fixture
async def task_id():
    tracker = TaskTracker(store=PersistentTaskStore(_FakeAgfs()))
    task = await tracker.create("add_resource", **OWNER)
    await tracker.start(task.task_id, **OWNER)
    await tracker.register_work(task.task_id, "parent", "AddResource", **OWNER)
    return tracker, task.task_id


async def test_progress_counts_settled_work_per_queue(task_id):
    tracker, tid = task_id
    for work_id in ("s1", "s2"):
        await tracker.register_work(tid, work_id, "Semantic", **OWNER)
    for work_id in ("e1", "e2", "e3"):
        await tracker.register_work(tid, work_id, "Embedding", **OWNER)

    await tracker.mark_work_done(tid, "s1", **OWNER)
    await tracker.mark_work_failed(tid, "e1", "boom", **OWNER)

    assert await tracker.work_progress(tid, exclude_work_id="parent", **OWNER) == {
        "Semantic": {"done": 1, "total": 2},
        "Embedding": {"done": 1, "total": 3},
    }


async def test_progress_ignores_duplicate_registration_and_discarded_work(task_id):
    tracker, tid = task_id
    await tracker.register_work(tid, "s1", "Semantic", **OWNER)
    await tracker.register_work(tid, "s1", "Semantic", **OWNER)
    await tracker.register_work(tid, "s2", "Semantic", **OWNER)

    # Work that never reached the durable queue is not part of the task.
    await tracker.discard_work(tid, "s2", **OWNER)

    assert await tracker.work_progress(tid, exclude_work_id="parent", **OWNER) == {
        "Semantic": {"done": 0, "total": 1},
    }


async def test_progress_counts_requeued_and_running_work_as_open(task_id):
    tracker, tid = task_id
    await tracker.register_work(tid, "s1", "Semantic", **OWNER)
    await tracker.register_work(tid, "s2", "Semantic", **OWNER)
    await tracker.start_work(tid, "s1", **OWNER)
    await tracker.mark_work_requeued(tid, "s2", **OWNER)

    assert await tracker.work_progress(tid, exclude_work_id="parent", **OWNER) == {
        "Semantic": {"done": 0, "total": 2},
    }


async def test_progress_after_restart_starts_from_recovered_work(task_id):
    tracker, tid = task_id
    restarted = TaskTracker(store=PersistentTaskStore(tracker._store._agfs))
    await restarted.reconcile_delivery(tid, "s1", "Semantic", **OWNER)
    await restarted.reconcile_delivery(tid, "e1", "Embedding", **OWNER)
    await restarted.reconcile_delivery(tid, "e2", "Embedding", **OWNER)

    assert await restarted.work_progress(tid, **OWNER) == {
        "Semantic": {"done": 0, "total": 1},
        "Embedding": {"done": 0, "total": 2},
    }
