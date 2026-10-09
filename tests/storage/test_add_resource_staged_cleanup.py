# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Staged-source cleanup failures are reported instead of silently leaking."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from openviking.storage.queuefs import add_resource_processor
from openviking.storage.queuefs.add_resource_processor import AddResourceProcessor

STAGED = {
    "temp_uri": "viking://temp/alice/10091530_abc123",
    "source_uri": "viking://temp/alice/10091530_abc123/source/notes.md",
    "source_type": "local",
    "original_source": "notes.md",
    "meta": {},
}


def _msg(staged_source):
    return SimpleNamespace(staged_source=staged_source, task_id="task-1")


async def test_cleanup_deletes_staged_bundle():
    viking_fs = SimpleNamespace(delete_temp=AsyncMock())
    processor = AddResourceProcessor(SimpleNamespace(), "add_resource", viking_fs)

    await processor._cleanup_staged_source(_msg(STAGED), ctx=None)

    viking_fs.delete_temp.assert_awaited_once_with(STAGED["temp_uri"], ctx=None)


async def test_cleanup_failure_is_logged_not_raised(monkeypatch):
    warning = MagicMock()
    monkeypatch.setattr(add_resource_processor.logger, "warning", warning)
    viking_fs = SimpleNamespace(delete_temp=AsyncMock(side_effect=PermissionError("denied")))
    processor = AddResourceProcessor(SimpleNamespace(), "add_resource", viking_fs)

    await processor._cleanup_staged_source(_msg(STAGED), ctx=None)
    await processor._cleanup_staged_source(_msg({"temp_uri": "not-temp"}), ctx=None)

    assert warning.call_count == 2
    logged = " ".join(str(arg) for call in warning.call_args_list for arg in call.args)
    assert "task-1" in logged
    assert STAGED["temp_uri"] in logged
