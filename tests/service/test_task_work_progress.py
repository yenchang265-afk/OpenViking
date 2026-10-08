# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Per-task queue progress derived from the task work index."""

from openviking.service.task_work_index import QueueTaskMetadata, TaskWorkIndex


def _work(work_id: str, task_id: str = "task-1") -> QueueTaskMetadata:
    return QueueTaskMetadata(task_id, work_id, "acme", "alice")


async def test_progress_counts_settled_work_per_queue():
    index = TaskWorkIndex()
    index.register("AddResource", _work("parent"))
    for work_id in ("s1", "s2"):
        index.register("Semantic", _work(work_id))
    for work_id in ("e1", "e2", "e3"):
        index.register("Embedding", _work(work_id))

    await index.prepare_ack("Semantic", _work("s1"))
    await index.prepare_ack("Embedding", _work("e1"))

    assert index.progress("task-1", exclude_work_id="parent") == {
        "Semantic": {"done": 1, "total": 2},
        "Embedding": {"done": 1, "total": 3},
    }


async def test_progress_ignores_duplicate_registration_and_discarded_work():
    index = TaskWorkIndex()
    index.register("AddResource", _work("parent"))
    index.register("Semantic", _work("s1"))
    index.register("Semantic", _work("s1"))
    index.register("Semantic", _work("s2"))

    # Work that never reached the durable queue is not part of the task.
    await index.discard("Semantic", _work("s2"))

    assert index.progress("task-1", exclude_work_id="parent") == {
        "Semantic": {"done": 0, "total": 1},
    }


async def test_progress_is_forgotten_once_task_has_no_work():
    index = TaskWorkIndex()
    index.register("Semantic", _work("s1"))
    await index.prepare_ack("Semantic", _work("s1"))

    assert index.progress("task-1") == {}
    index.register("Semantic", _work("s2"))
    assert index.progress("task-1") == {"Semantic": {"done": 0, "total": 1}}


def test_progress_after_rebuild_starts_from_pending_work():
    index = TaskWorkIndex()
    index.rebuild(
        {
            "Semantic": [{"task_id": "task-1", "_task_work_id": "s1"}],
            "Embedding": [
                {"task_id": "task-1", "_task_work_id": "e1"},
                {"task_id": "task-1", "_task_work_id": "e2"},
            ],
        }
    )

    assert index.progress("task-1") == {
        "Semantic": {"done": 0, "total": 1},
        "Embedding": {"done": 0, "total": 2},
    }


def test_progress_survives_ack_rollback_without_negative_counts():
    index = TaskWorkIndex()
    index.register("Semantic", _work("s1"))
    index.register("Semantic", _work("s2"))
    index.rollback_ack("Semantic", _work("s3"))

    assert index.progress("task-1") == {"Semantic": {"done": 0, "total": 3}}
