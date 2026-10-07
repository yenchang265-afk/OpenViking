# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Chunked upload session store: lifecycle, resume, limits, path safety and ownership."""

import os
import time
from pathlib import Path
from typing import AsyncIterator

import pytest

from openviking.server.config import UploadConfig
from openviking.server.identity import RequestContext, Role
from openviking.server.upload_sessions import UploadSessionStore, UploadTooLargeError
from openviking_cli.exceptions import InvalidArgumentError, NotFoundError, PermissionDeniedError
from openviking_cli.session.user_id import UserIdentifier

MIB = 1024 * 1024
PART = MIB


def _ctx(account: str = "acct", user: str = "alice") -> RequestContext:
    return RequestContext(user=UserIdentifier(account, user), role=Role.USER)


def _store(tmp_path: Path, **limits) -> UploadSessionStore:
    config = UploadConfig(
        **{
            "max_file_bytes": 8 * MIB,
            "max_session_bytes": 16 * MIB,
            "max_files": 5,
            "part_size_bytes": PART,
            **limits,
        }
    )
    return UploadSessionStore(tmp_path / "upload", limits=config, ttl_seconds=3600)


async def _chunks(data: bytes, size: int = 64 * 1024) -> AsyncIterator[bytes]:
    for i in range(0, len(data), size):
        yield data[i : i + size]


def _data(size: int, seed: int = 0) -> bytes:
    return bytes((i + seed) % 251 for i in range(size))


async def _upload_all(store, upload_id, files_data, ctx):
    for index, data in enumerate(files_data):
        for n in range(1, -(-len(data) // PART) + 1):
            part = data[(n - 1) * PART : n * PART]
            await store.put_part(upload_id, index, n, _chunks(part), ctx)


@pytest.mark.asyncio
async def test_single_file_lifecycle_resolves_to_assembled_file(tmp_path):
    store = _store(tmp_path)
    data = _data(2 * PART + 123)
    ctx = _ctx()

    created = await store.create(
        kind="file", name="report.pdf", files=[{"path": "report.pdf", "size": len(data)}], ctx=ctx
    )
    assert created["part_size_bytes"] == PART
    assert created["files"] == [
        {"index": 0, "path": "report.pdf", "size": len(data), "total_parts": 3}
    ]

    await _upload_all(store, created["upload_id"], [data], ctx)
    done = await store.complete(created["upload_id"], ctx)
    path, name = store.resolve(done["temp_file_id"], ctx)

    assert done["temp_file_id"].startswith("session_")
    assert name == "report.pdf"
    assert path.is_file() and path.read_bytes() == data


@pytest.mark.asyncio
async def test_directory_lifecycle_rebuilds_tree_including_empty_files(tmp_path):
    store = _store(tmp_path)
    ctx = _ctx()
    files = {"a.md": _data(10), "sub/deep/b.bin": _data(PART + 7, seed=3), "empty.txt": b""}

    created = await store.create(
        kind="directory",
        name="docs",
        files=[{"path": p, "size": len(d)} for p, d in files.items()],
        ctx=ctx,
    )
    await _upload_all(store, created["upload_id"], list(files.values()), ctx)
    done = await store.complete(created["upload_id"], ctx)
    root, name = store.resolve(done["temp_file_id"], ctx)

    assert name == "docs" and root.is_dir() and root.name == "docs"
    restored = {
        p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }
    assert restored == files


@pytest.mark.asyncio
async def test_status_lists_received_parts_and_parts_are_idempotent(tmp_path):
    store = _store(tmp_path)
    ctx = _ctx()
    data = _data(3 * PART)
    created = await store.create(
        kind="file", name="f.bin", files=[{"path": "f.bin", "size": len(data)}], ctx=ctx
    )
    upload_id = created["upload_id"]

    await store.put_part(upload_id, 0, 2, _chunks(b"\x00" * PART), ctx)
    await store.put_part(upload_id, 0, 2, _chunks(data[PART : 2 * PART]), ctx)
    status = await store.status(upload_id, ctx)
    assert status["completed"] is False
    assert status["files"][0]["received_parts"] == [2]

    with pytest.raises(InvalidArgumentError, match="missing"):
        await store.complete(upload_id, ctx)

    await store.put_part(upload_id, 0, 1, _chunks(data[:PART]), ctx)
    await store.put_part(upload_id, 0, 3, _chunks(data[2 * PART :]), ctx)
    first = await store.complete(upload_id, ctx)
    again = await store.complete(upload_id, ctx)
    assert first == again
    assert store.resolve(first["temp_file_id"], ctx)[0].read_bytes() == data


@pytest.mark.asyncio
async def test_part_size_and_range_are_enforced(tmp_path):
    store = _store(tmp_path)
    ctx = _ctx()
    created = await store.create(
        kind="file", name="f.bin", files=[{"path": "f.bin", "size": PART + 10}], ctx=ctx
    )
    upload_id = created["upload_id"]

    with pytest.raises(UploadTooLargeError, match="exceeds size limit"):
        await store.put_part(upload_id, 0, 1, _chunks(b"x" * (PART + 1)), ctx)
    with pytest.raises(InvalidArgumentError, match="expected"):
        await store.put_part(upload_id, 0, 2, _chunks(b"x" * 9), ctx)
    for file_index, part_number in [(0, 0), (0, 3), (1, 1), (-1, 1)]:
        with pytest.raises(InvalidArgumentError):
            await store.put_part(upload_id, file_index, part_number, _chunks(b"x"), ctx)
    assert (await store.status(upload_id, ctx))["files"][0]["received_parts"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("files", "error"),
    [
        ([{"path": "big.bin", "size": 8 * MIB + 1}], UploadTooLargeError),
        ([{"path": f"f{i}.bin", "size": 6 * MIB} for i in range(3)], UploadTooLargeError),
        ([{"path": f"f{i}.bin", "size": 1} for i in range(6)], InvalidArgumentError),
        ([], InvalidArgumentError),
        ([{"path": "neg.bin", "size": -1}], InvalidArgumentError),
    ],
)
async def test_create_enforces_limits(tmp_path, files, error):
    with pytest.raises(error):
        await _store(tmp_path).create(kind="directory", name="d", files=files, ctx=_ctx())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_path",
    [
        "../escape.txt",
        "/abs.txt",
        "a/../../b.txt",
        "C:\\x.txt",
        "a\x00b.txt",
        "a//b.txt",
        "./a.txt",
        "a/",
    ],
)
async def test_create_rejects_unsafe_paths(tmp_path, bad_path):
    with pytest.raises(InvalidArgumentError):
        await _store(tmp_path).create(
            kind="directory", name="d", files=[{"path": bad_path, "size": 1}], ctx=_ctx()
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "name", "paths"),
    [
        ("directory", "d", ["a.txt", "a.txt"]),
        ("directory", "d", ["Read.me", "read.ME"]),
        ("directory", "d", ["a", "a/b"]),
        ("directory", "../d", ["a.txt"]),
        ("directory", "x/y", ["a.txt"]),
        ("file", "f.txt", ["f.txt", "g.txt"]),
        ("file", "f.txt", ["other.txt"]),
    ],
)
async def test_create_rejects_conflicting_or_invalid_layouts(tmp_path, kind, name, paths):
    with pytest.raises(InvalidArgumentError):
        await _store(tmp_path).create(
            kind=kind, name=name, files=[{"path": p, "size": 1} for p in paths], ctx=_ctx()
        )


@pytest.mark.asyncio
async def test_other_users_cannot_touch_a_session(tmp_path):
    store = _store(tmp_path)
    owner = _ctx()
    created = await store.create(
        kind="file", name="f.bin", files=[{"path": "f.bin", "size": 3}], ctx=owner
    )
    upload_id = created["upload_id"]

    for intruder in (_ctx(user="mallory"), _ctx(account="other")):
        with pytest.raises(PermissionDeniedError):
            await store.put_part(upload_id, 0, 1, _chunks(b"abc"), intruder)
        with pytest.raises(PermissionDeniedError):
            await store.status(upload_id, intruder)
        with pytest.raises(PermissionDeniedError):
            await store.complete(upload_id, intruder)
        with pytest.raises(PermissionDeniedError):
            await store.abort(upload_id, intruder)

    await store.put_part(upload_id, 0, 1, _chunks(b"abc"), owner)
    done = await store.complete(upload_id, owner)
    with pytest.raises(PermissionDeniedError):
        store.resolve(done["temp_file_id"], _ctx(user="mallory"))


@pytest.mark.asyncio
async def test_unknown_or_malformed_ids_are_not_found(tmp_path):
    store = _store(tmp_path)
    for upload_id in ["0" * 32, "../../etc", "x"]:
        with pytest.raises(NotFoundError):
            await store.status(upload_id, _ctx())
    with pytest.raises(NotFoundError):
        store.resolve("session_" + "0" * 32, _ctx())


@pytest.mark.asyncio
async def test_resolve_requires_completed_session(tmp_path):
    store = _store(tmp_path)
    created = await store.create(
        kind="file", name="f.bin", files=[{"path": "f.bin", "size": 3}], ctx=_ctx()
    )
    with pytest.raises(NotFoundError):
        store.resolve(f"session_{created['upload_id']}", _ctx())


@pytest.mark.asyncio
async def test_abort_removes_session(tmp_path):
    store = _store(tmp_path)
    ctx = _ctx()
    created = await store.create(
        kind="file", name="f.bin", files=[{"path": "f.bin", "size": 3}], ctx=ctx
    )
    await store.put_part(created["upload_id"], 0, 1, _chunks(b"abc"), ctx)

    await store.abort(created["upload_id"], ctx)

    with pytest.raises(NotFoundError):
        await store.status(created["upload_id"], ctx)
    assert not any((tmp_path / "upload" / "sessions").iterdir())


@pytest.mark.asyncio
async def test_expired_sessions_are_swept_on_create(tmp_path):
    store = _store(tmp_path)
    ctx = _ctx()
    old = await store.create(
        kind="file", name="f.bin", files=[{"path": "f.bin", "size": 3}], ctx=ctx
    )
    old_dir = tmp_path / "upload" / "sessions" / old["upload_id"]
    stale = time.time() - 7200
    os.utime(old_dir / "session.json", (stale, stale))

    await store.create(kind="file", name="g.bin", files=[{"path": "g.bin", "size": 3}], ctx=ctx)

    assert not old_dir.exists()
