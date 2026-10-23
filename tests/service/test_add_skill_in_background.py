# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Background skill installs return a task before the privacy LLM call runs."""

import asyncio
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from openviking.server.identity import RequestContext, Role
from openviking.service.resource_service import ResourceService
from openviking.service.task_store import PersistentTaskStore
from openviking.service.task_tracker import TaskStatus, TaskTracker
from openviking.utils.skill_processor import SkillProcessingPreparation, SkillProcessor
from openviking_cli.exceptions import InvalidArgumentError
from openviking_cli.session.user_id import UserIdentifier
from tests.test_task_tracker import _FakeAgfs

SKILL_MD = "---\nname: demo\ndescription: Does the demo thing\n---\n# Demo\n"


def _ctx() -> RequestContext:
    return RequestContext(user=UserIdentifier.the_default_user(), role=Role.ROOT)


@pytest.fixture
def tracker(monkeypatch):
    tracker = TaskTracker(store=PersistentTaskStore(_FakeAgfs()))
    monkeypatch.setattr("openviking.service.task_tracker.get_task_tracker", lambda: tracker)
    return tracker


def _service(add_skill) -> ResourceService:
    service = ResourceService.__new__(ResourceService)
    service._resource_processor = object()
    service._viking_fs = object()
    service._skill_processor = SkillProcessor(vikingdb=None)
    service._background_tasks = set()
    service._unstarted_skill_tasks = {}
    service.add_skill = add_skill
    return service


@pytest.mark.asyncio
async def test_shutdown_before_start_fails_the_task(tracker):
    add_skill = AsyncMock()
    service = _service(add_skill)
    ctx = _ctx()

    result = await service.add_skill_in_background(
        SKILL_MD, ctx, target_uri="viking://agent/skills"
    )
    # Shutdown cancels the background run before its first step.
    await service.close_background_tasks()

    add_skill.assert_not_awaited()
    owner = {"account_id": ctx.account_id, "user_id": ctx.user.user_id}
    task = await tracker.get(result["task_id"], **owner)
    assert task.status is TaskStatus.FAILED
    assert not service._unstarted_skill_tasks


@pytest.mark.asyncio
async def test_returns_task_before_processing_finishes(tracker):
    release = asyncio.Event()

    async def slow_add_skill(data, ctx, **kwargs):
        await release.wait()
        return {"task_id": kwargs["task_id"]}

    add_skill = AsyncMock(side_effect=slow_add_skill)
    service = _service(add_skill)
    ctx = _ctx()

    result = await service.add_skill_in_background(
        SKILL_MD, ctx, target_uri="viking://agent/skills"
    )

    assert result["status"] == "accepted"
    assert result["name"] == "demo"
    assert result["uri"] == result["root_uri"] == "viking://agent/skills/demo"
    owner = {"account_id": ctx.account_id, "user_id": ctx.user.user_id}
    task = await tracker.get(result["task_id"], **owner)
    assert task.task_type == "add_skill"
    assert task.status is TaskStatus.PENDING

    await asyncio.sleep(0)
    preparation = add_skill.await_args.args[0]
    assert isinstance(preparation, SkillProcessingPreparation)
    assert preparation.privacy_pending is True
    assert add_skill.await_args.kwargs["task_id"] == result["task_id"]
    assert len(service._background_tasks) == 1

    release.set()
    await asyncio.gather(*service._background_tasks)
    assert not service._background_tasks


@pytest.mark.asyncio
async def test_invalid_skill_fails_synchronously(tracker):
    add_skill = AsyncMock()
    service = _service(add_skill)

    with pytest.raises((InvalidArgumentError, ValueError)):
        await service.add_skill_in_background(
            {"name": "bad name!", "description": "x"},
            _ctx(),
            target_uri="viking://agent/skills",
        )
    add_skill.assert_not_awaited()
    assert not service._background_tasks


@pytest.mark.asyncio
async def test_skill_with_source_files_runs_inline(tracker, tmp_path: Path):
    (tmp_path / "SKILL.md").write_text(SKILL_MD)
    (tmp_path / "helper.py").write_text("print('hi')\n")
    add_skill = AsyncMock(return_value={"task_id": "inline"})
    service = _service(add_skill)

    result = await service.add_skill_in_background(
        tmp_path,
        _ctx(),
        target_uri="viking://agent/skills",
        allow_local_path_resolution=True,
    )

    # The request's source files are deleted when it returns, so it cannot defer.
    assert result == {"task_id": "inline"}
    add_skill.assert_awaited_once()
    assert add_skill.await_args.args[0].privacy_pending is True
    assert "task_id" not in add_skill.await_args.kwargs
    assert not service._background_tasks


@pytest.mark.asyncio
async def test_prepared_skill_with_pending_privacy_runs_extraction():
    viking_fs = MagicMock()
    viking_fs._async_agfs.pathlock_acquire_tree = AsyncMock(return_value={"lease_ref": "t"})
    viking_fs._async_agfs.pathlock_release = AsyncMock()
    processor = SkillProcessor(vikingdb=None)
    sanitized = {"name": "demo", "description": "d", "content": "{{secret}}"}
    processor.prepare_skill_privacy = AsyncMock(return_value=(sanitized, {"token": "abc"}))
    processor.apply_skill_privacy = AsyncMock(side_effect=lambda skill, *a, **k: skill)
    processor._write_skill_content = AsyncMock()
    processor._enqueue_skill_package = AsyncMock()
    preparation = await processor.prepare_skill_processing(
        SKILL_MD, ctx=_ctx(), extract_privacy=False
    )
    preparation = replace(preparation, privacy_pending=True)

    await processor.process_prepared_skill(
        preparation, viking_fs=viking_fs, ctx=_ctx(), target_uri="viking://agent/skills"
    )

    processor.prepare_skill_privacy.assert_awaited_once()
    applied_skill, applied_values = processor.apply_skill_privacy.await_args.args[:2]
    assert applied_skill == sanitized
    assert applied_values == {"token": "abc"}
