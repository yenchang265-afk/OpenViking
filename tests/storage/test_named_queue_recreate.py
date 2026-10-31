# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Queues re-register themselves when the cache backend loses them.

A cache-backed QueueFS keeps its queue registry in Redis. When Redis restarts
without persistence (or is flushed, or fails over without the data), every queue
created at startup is gone and each operation reports "not found" until the queue
is created again.
"""

from unittest.mock import AsyncMock, call

import pytest

from openviking.pyagfs import AsyncAGFSClient
from openviking.pyagfs.exceptions import AGFSNotFoundError
from openviking.storage.queuefs.named_queue import NamedQueue

PATH = "/queue/Test"


@pytest.fixture
def transport(monkeypatch):
    client = AsyncMock(spec=AsyncAGFSClient)
    client.write.return_value = "message-1"
    monkeypatch.setattr(
        "openviking.storage.queuefs.named_queue.AsyncAGFSClient", lambda _client: client
    )
    return client


def _missing():
    return AGFSNotFoundError(f"queue not found: {PATH}")


async def test_enqueue_recreates_a_queue_the_backend_lost(transport):
    queue = NamedQueue(object(), "/queue", "Test")
    assert await queue.enqueue({"value": 1}) == "message-1"
    transport.write.side_effect = [_missing(), "message-2"]

    receipt = await queue.enqueue({"value": 2})

    assert receipt == "message-2"
    assert transport.mkdir.await_args_list == [call(PATH), call(PATH)]
    assert transport.write.await_count == 3


async def test_enqueue_reports_a_queue_that_stays_missing(transport):
    queue = NamedQueue(object(), "/queue", "Test")
    transport.write.side_effect = _missing()

    with pytest.raises(AGFSNotFoundError):
        await queue.enqueue({"value": 1})
    assert transport.write.await_count == 2


async def test_size_poll_repairs_a_lost_queue(transport):
    queue = NamedQueue(object(), "/queue", "Test")
    transport.read.side_effect = [_missing(), b"3"]

    assert await queue.size() == 3
    assert transport.mkdir.await_args_list == [call(PATH), call(PATH)]


async def test_dequeue_raw_recreates_a_lost_queue(transport):
    queue = NamedQueue(object(), "/queue", "Test")
    transport.read.side_effect = [_missing(), b'{"id": "m1", "data": "{}"}']

    assert await queue.dequeue_raw() == {"id": "m1", "data": "{}"}
    assert transport.mkdir.await_count == 2


async def test_other_errors_do_not_recreate_the_queue(transport):
    queue = NamedQueue(object(), "/queue", "Test")
    transport.write.side_effect = RuntimeError("backend exploded")

    with pytest.raises(RuntimeError):
        await queue.enqueue({"value": 1})
    assert transport.mkdir.await_count == 1
