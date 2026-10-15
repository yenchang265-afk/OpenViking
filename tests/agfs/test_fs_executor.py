# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Storage calls run on a dedicated, bounded thread pool."""

import asyncio
import contextvars
import threading

import pytest

from openviking.pyagfs import AsyncAGFSClient
from openviking.pyagfs.exceptions import AGFSTimeoutError
from openviking.pyagfs.fs_executor import configure_fs_executor, run_in_fs_executor

_request_id = contextvars.ContextVar("request_id", default=None)


@pytest.fixture(autouse=True)
def small_fs_executor():
    configure_fs_executor(threads=1, queue_timeout_seconds=0.2)
    yield
    configure_fs_executor(threads=64, queue_timeout_seconds=30.0)


class BlockingClient:
    """Sync client whose `ls` blocks until released, like a call to a stalled S3."""

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = []

    def ls(self, path, **kwargs):
        self.calls.append(path)
        self.started.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("test did not release the call")
        return []

    def stat(self, path, **kwargs):
        return {"thread": threading.current_thread().name, "request_id": _request_id.get()}


@pytest.mark.asyncio
async def test_storage_calls_run_on_the_fs_pool_with_caller_context():
    client = AsyncAGFSClient(BlockingClient())
    _request_id.set("req-1")

    result = await client.stat("/local/acct/file")

    assert result["thread"].startswith("openviking-fs")
    assert result["request_id"] == "req-1"


@pytest.mark.asyncio
async def test_saturated_fs_pool_does_not_starve_the_default_executor():
    blocking = BlockingClient()
    client = AsyncAGFSClient(blocking)
    stalled = asyncio.create_task(client.ls("/local/acct"))
    try:
        assert await asyncio.to_thread(blocking.started.wait, 5)

        # Other default-executor work (vector DB, auth, ...) still runs.
        assert await asyncio.wait_for(asyncio.to_thread(lambda: "ok"), timeout=1) == "ok"
    finally:
        blocking.release.set()
        await stalled


@pytest.mark.asyncio
async def test_call_that_cannot_start_in_time_fails_fast_and_never_runs():
    blocking = BlockingClient()
    client = AsyncAGFSClient(blocking)
    stalled = asyncio.create_task(client.ls("/local/acct/first"))
    try:
        assert await asyncio.to_thread(blocking.started.wait, 5)

        with pytest.raises(AGFSTimeoutError, match="did not start within"):
            await client.ls("/local/acct/second")
    finally:
        blocking.release.set()
        await stalled
    # The rejected call was dropped from the queue, not run late.
    await asyncio.sleep(0.05)
    assert blocking.calls == ["/local/acct/first"]


def test_configure_rejects_invalid_values():
    with pytest.raises(ValueError):
        configure_fs_executor(threads=0, queue_timeout_seconds=1.0)
    with pytest.raises(ValueError):
        configure_fs_executor(threads=1, queue_timeout_seconds=0)


@pytest.mark.asyncio
async def test_cancelling_a_queued_call_drops_it_from_the_queue():
    configure_fs_executor(threads=1, queue_timeout_seconds=5.0)
    blocking = BlockingClient()
    calls = []
    stalled = asyncio.create_task(run_in_fs_executor(blocking.ls, "/local/acct/first"))
    try:
        assert await asyncio.to_thread(blocking.started.wait, 5)
        queued = asyncio.create_task(run_in_fs_executor(calls.append, "second"))
        await asyncio.sleep(0.05)
        queued.cancel()
        with pytest.raises(asyncio.CancelledError):
            await queued
    finally:
        blocking.release.set()
        await stalled
    await asyncio.sleep(0.05)
    assert calls == []


@pytest.mark.asyncio
async def test_forked_child_builds_a_fresh_pool():
    from openviking.pyagfs import fs_executor

    assert await run_in_fs_executor(lambda: "parent") == "parent"
    inherited = fs_executor._executor
    assert inherited is not None

    fs_executor._reset_after_fork()

    assert fs_executor._executor is None
    assert await run_in_fs_executor(lambda: "child") == "child"
    assert fs_executor._executor is not inherited
    inherited.shutdown(wait=False)
