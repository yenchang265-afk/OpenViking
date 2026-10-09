# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Local uploads expire by TTL even when no new upload triggers cleanup."""

import asyncio
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from openviking.server import temp_upload_store
from openviking.server.temp_upload_store import TempUploadStore


@pytest.fixture
def upload_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    config = SimpleNamespace(storage=SimpleNamespace(get_upload_temp_dir=lambda: tmp_path))
    monkeypatch.setattr(temp_upload_store, "get_openviking_config", lambda: config)
    return tmp_path


def _store(ttl_seconds: int) -> TempUploadStore:
    store = object.__new__(TempUploadStore)
    store.temp_cfg = SimpleNamespace(ttl_seconds=ttl_seconds)
    return store


def _upload(upload_dir: Path, name: str, age_seconds: float) -> tuple[Path, Path]:
    upload = upload_dir / name
    upload.write_text("content")
    meta = upload_dir / f"{name}.ov_upload.meta"
    meta.write_text("{}")
    stamp = time.time() - age_seconds
    for path in (upload, meta):
        os.utime(path, (stamp, stamp))
    return upload, meta


async def test_sweep_removes_only_expired_uploads(upload_dir: Path):
    expired = _upload(upload_dir, "upload_old.md", age_seconds=7200)
    fresh = _upload(upload_dir, "upload_new.md", age_seconds=60)

    await _store(ttl_seconds=3600).sweep_local_uploads()

    assert not any(path.exists() for path in expired)
    assert all(path.exists() for path in fresh)


async def test_sweep_loop_survives_errors_and_stops_on_cancel(monkeypatch):
    calls = []

    async def sweep(self):
        calls.append(len(calls))
        if len(calls) == 1:
            raise OSError("disk unavailable")

    monkeypatch.setattr(TempUploadStore, "sweep_local_uploads", sweep)
    monkeypatch.setattr(TempUploadStore, "build", staticmethod(lambda _config: _store(60)))

    loop = asyncio.create_task(
        temp_upload_store.run_local_upload_sweep_loop(object(), interval_seconds=0)
    )
    while len(calls) < 3:
        await asyncio.sleep(0)
    loop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await loop
