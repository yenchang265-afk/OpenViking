# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Shared-storage upload sessions against real VikingFS storage."""

from pathlib import Path
from typing import AsyncIterator

import pytest

from openviking.server.config import ServerConfig
from openviking.server.identity import RequestContext, Role
from openviking.server.shared_upload_sessions import (
    SharedUploadSessionStore,
    is_shared_session_upload_id,
)
from openviking.server.temp_upload_store import TempUploadStore
from openviking_cli.exceptions import PermissionDeniedError
from openviking_cli.session.user_id import UserIdentifier

MIB = 1024 * 1024


def _ctx(user: str = "alice") -> RequestContext:
    return RequestContext(user=UserIdentifier("acct", user), role=Role.USER)


def _config() -> ServerConfig:
    return ServerConfig(
        temp_upload={"default_mode": "shared"},
        upload={"max_file_bytes": 4 * MIB, "max_session_bytes": 8 * MIB, "part_size_bytes": MIB},
    )


async def _chunks(data: bytes) -> AsyncIterator[bytes]:
    for i in range(0, len(data), 64 * 1024):
        yield data[i : i + 64 * 1024]


async def _upload(store, kind, name, files, ctx) -> str:
    created = await store.create(
        kind=kind, name=name, files=[{"path": p, "size": len(d)} for p, d in files], ctx=ctx
    )
    upload_id = created["upload_id"]
    assert is_shared_session_upload_id(upload_id)
    for index, (_, data) in enumerate(files):
        for n in range(1, -(-len(data) // MIB) + 1):
            # A fresh store per request: replicas share nothing but storage.
            await SharedUploadSessionStore(_config()).put_part(
                upload_id, index, n, _chunks(data[(n - 1) * MIB : n * MIB]), ctx
            )
    return (await SharedUploadSessionStore(_config()).complete(upload_id, ctx))["temp_file_id"]


@pytest.mark.asyncio
async def test_other_users_cannot_touch_a_shared_session(service):
    store = SharedUploadSessionStore(_config())
    created = await store.create(
        kind="file", name="f.md", files=[{"path": "f.md", "size": 3}], ctx=_ctx()
    )
    upload_id = created["upload_id"]

    for call in (
        store.status(upload_id, _ctx("mallory")),
        store.put_part(upload_id, 0, 1, _chunks(b"abc"), _ctx("mallory")),
        store.complete(upload_id, _ctx("mallory")),
        store.abort(upload_id, _ctx("mallory")),
    ):
        with pytest.raises(PermissionDeniedError):
            await call


@pytest.mark.asyncio
async def test_consumers_rebuild_a_shared_folder_session(service):
    files = [("a.md", b"# a\n"), ("sub/b.bin", bytes(range(256)) * 5000)]
    temp_file_id = await _upload(
        SharedUploadSessionStore(_config()), "directory", "docs", files, _ctx()
    )

    resolved = await TempUploadStore.build(_config()).resolve_for_consume(temp_file_id, _ctx())
    root = Path(resolved.local_path)
    try:
        assert resolved.mode == "shared" and resolved.original_filename == "docs"
        assert root.name == "docs"
        assert (root / "a.md").read_bytes() == files[0][1]
        assert (root / "sub" / "b.bin").read_bytes() == files[1][1]
    finally:
        await resolved.cleanup()
    assert not root.exists()

    with pytest.raises(PermissionDeniedError):
        await TempUploadStore.build(_config()).resolve_for_consume(
            temp_file_id, _ctx_other_account()
        )


def _ctx_other_account() -> RequestContext:
    return RequestContext(user=UserIdentifier("other", "alice"), role=Role.USER)
