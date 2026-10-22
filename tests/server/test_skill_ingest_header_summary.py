# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""User skill installs summarize SKILL.md from its header instead of an LLM call."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from openviking.server import skill_ingest
from openviking.server.identity import RequestContext, Role
from openviking.utils.skill_processor import SkillProcessor
from openviking_cli.session.user_id import UserIdentifier


def _ctx() -> RequestContext:
    return RequestContext(user=UserIdentifier.the_default_user(), role=Role.ROOT)


@pytest.mark.asyncio
async def test_install_skills_summarizes_from_header(monkeypatch):
    add_skill = AsyncMock(return_value={"uri": "viking://agent/skills/demo"})
    service = SimpleNamespace(resources=SimpleNamespace(add_skill=add_skill))
    monkeypatch.setattr(skill_ingest, "get_service", lambda: service)

    @asynccontextmanager
    async def fake_source(data, **_):
        yield [(data, {"type": "api"})]

    monkeypatch.setattr(skill_ingest, "resolve_skill_source", fake_source)

    await skill_ingest.install_skills("---\nname: demo\n---", _ctx())

    assert add_skill.await_args.kwargs["summarize_from_header"] is True


def _processor_with_mocks():
    viking_fs = MagicMock()
    viking_fs._async_agfs.pathlock_acquire_tree = AsyncMock(return_value={"lease_ref": "t"})
    viking_fs._async_agfs.pathlock_release = AsyncMock()
    processor = SkillProcessor(vikingdb=None)
    processor._write_skill_content = AsyncMock()
    processor._enqueue_skill_package = AsyncMock()
    return processor, viking_fs


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("description", "expect_header"),
    [("Does the demo thing", True), ("", False), ("   ", False)],
)
async def test_header_summary_requires_description(description, expect_header):
    processor, viking_fs = _processor_with_mocks()

    await processor.process_skill(
        data={"name": "demo", "description": description, "content": "# Demo"},
        viking_fs=viking_fs,
        ctx=_ctx(),
        allow_local_path_resolution=False,
        summarize_from_header=True,
    )

    file_abstracts = processor._enqueue_skill_package.await_args.kwargs["file_abstracts"]
    assert (file_abstracts is not None) is expect_header
