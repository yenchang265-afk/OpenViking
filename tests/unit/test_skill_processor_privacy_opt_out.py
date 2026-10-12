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


@pytest.fixture
def processor(monkeypatch):
    extract = AsyncMock(
        return_value=SimpleNamespace(
            values={"api_key": "sk-test-value"},
            sanitized_content="api_key: {{api_key}}\n",
        )
    )
    monkeypatch.setattr("openviking.utils.skill_processor.extract_skill_privacy_values", extract)
    processor = SkillProcessor(vikingdb=None, privacy_config_service=object())
    processor.process_prepared_skill = AsyncMock(return_value={"status": "success"})
    return processor, extract


@pytest.fixture
def ctx():
    return RequestContext(user=UserIdentifier.the_default_user(), role=Role.ROOT)


async def test_opting_out_skips_the_scan_and_keeps_content(processor, ctx):
    processor, extract = processor

    await processor.process_skill(
        SKILL, viking_fs=None, ctx=ctx, allow_local_path_resolution=False, apply_privacy=False
    )

    extract.assert_not_awaited()
    preparation = processor.process_prepared_skill.await_args.args[0]
    assert "sk-test-value" in preparation.skill_dict["content"]
    assert preparation.privacy_values == {}


async def test_default_still_scans_for_privacy_values(processor, ctx):
    processor, extract = processor

    await processor.process_skill(
        SKILL, viking_fs=None, ctx=ctx, allow_local_path_resolution=False
    )

    extract.assert_awaited_once()
    preparation = processor.process_prepared_skill.await_args.args[0]
    assert preparation.privacy_values == {"api_key": "sk-test-value"}
