# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0

"""A Skill added with apply_privacy=False must not run the privacy LLM scan."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from openviking.server.identity import RequestContext, Role
from openviking.utils.skill_processor import SkillProcessor
from openviking_cli.session.user_id import UserIdentifier

SKILL = "---\nname: opt-out\ndescription: Example\n---\n\napi_key: sk-test-value\n"


@pytest.fixture(autouse=True)
def _no_skill_history(monkeypatch):
    """Processor history bookkeeping is covered by its own tests."""
    import openviking.server.skill_history as history

    monkeypatch.setattr(history, "read_skill_history", AsyncMock(return_value=None))
    monkeypatch.setattr(history, "skill_package_hash", AsyncMock(return_value="hash"))
    monkeypatch.setattr(history, "record_skill_change", AsyncMock(return_value={}))


@pytest.fixture
def processor():
    processor = SkillProcessor(vikingdb=None, privacy_config_service=object())
    scan = AsyncMock(return_value=SimpleNamespace(settings=None, matches=[]))
    processor.prepare_skill_privacy = scan
    processor.process_prepared_skill = AsyncMock(return_value={"status": "success"})
    return processor, scan


@pytest.fixture
def ctx():
    return RequestContext(user=UserIdentifier.the_default_user(), role=Role.ROOT)


async def test_opting_out_skips_the_scan_and_keeps_content(processor, ctx):
    processor, scan = processor

    await processor.process_skill(
        SKILL, viking_fs=None, ctx=ctx, allow_local_path_resolution=False, apply_privacy=False
    )

    scan.assert_not_awaited()
    preparation = processor.process_prepared_skill.await_args.args[0]
    assert "sk-test-value" in preparation.skill_dict["content"]
    assert preparation.privacy is None


async def test_default_still_scans_for_privacy_values(processor, ctx):
    processor, scan = processor

    await processor.process_skill(
        SKILL, viking_fs=None, ctx=ctx, allow_local_path_resolution=False
    )

    scan.assert_awaited_once()
    preparation = processor.process_prepared_skill.await_args.args[0]
    assert preparation.privacy is scan.return_value
