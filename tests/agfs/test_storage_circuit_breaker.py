# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Storage calls fail fast while a mount's backend is failing."""

import pytest

from openviking.pyagfs import AsyncAGFSClient
from openviking.pyagfs.exceptions import (
    AGFSCircuitOpenError,
    AGFSNotFoundError,
    AGFSTimeoutError,
)
from openviking.pyagfs.storage_breaker import configure_storage_breaker
from openviking.server.error_mapping import map_exception
from openviking.server.models import ERROR_CODE_TO_HTTP_STATUS


@pytest.fixture(autouse=True)
def fast_breaker():
    configure_storage_breaker(
        enabled=True, failure_threshold=3, reset_timeout_seconds=0.2, max_reset_timeout_seconds=1
    )
    yield
    configure_storage_breaker(
        enabled=True, failure_threshold=5, reset_timeout_seconds=15, max_reset_timeout_seconds=120
    )


class ScriptedClient:
    """Sync client whose `stat` raises the queued errors, then succeeds."""

    def __init__(self, *errors):
        self.errors = list(errors)
        self.calls = []

    def stat(self, path, **kwargs):
        self.calls.append(path)
        if self.errors:
            raise self.errors.pop(0)
        return {"name": path}


async def _fail_times(client, path, n):
    for _ in range(n):
        with pytest.raises(AGFSTimeoutError):
            await client.stat(path)


@pytest.mark.asyncio
async def test_consecutive_backend_timeouts_open_the_circuit_for_that_mount():
    sync = ScriptedClient(*[AGFSTimeoutError("s3 slow")] * 3)
    client = AsyncAGFSClient(sync)
    await _fail_times(client, "/local/acct/a", 3)

    with pytest.raises(AGFSCircuitOpenError):
        await client.stat("/local/acct/b")

    # Rejected without touching the backend.
    assert sync.calls == ["/local/acct/a"] * 3


@pytest.mark.asyncio
async def test_open_circuit_on_one_mount_does_not_block_other_mounts():
    sync = ScriptedClient(*[AGFSTimeoutError("s3 slow")] * 3)
    client = AsyncAGFSClient(sync)
    await _fail_times(client, "/local/acct/a", 3)

    assert await client.stat("/queue/semantic") == {"name": "/queue/semantic"}


@pytest.mark.asyncio
async def test_non_transient_errors_do_not_trip_the_circuit():
    sync = ScriptedClient(*[AGFSNotFoundError("missing")] * 5)
    client = AsyncAGFSClient(sync)
    for _ in range(5):
        with pytest.raises(AGFSNotFoundError):
            await client.stat("/local/acct/missing")

    assert await client.stat("/local/acct/a") == {"name": "/local/acct/a"}


@pytest.mark.asyncio
async def test_circuit_lets_a_probe_through_after_the_reset_timeout_and_closes_on_success():
    import asyncio

    sync = ScriptedClient(*[AGFSTimeoutError("s3 slow")] * 3)
    client = AsyncAGFSClient(sync)
    await _fail_times(client, "/local/acct/a", 3)
    with pytest.raises(AGFSCircuitOpenError):
        await client.stat("/local/acct/a")

    await asyncio.sleep(0.25)

    assert await client.stat("/local/acct/a") == {"name": "/local/acct/a"}
    assert await client.stat("/local/acct/b") == {"name": "/local/acct/b"}


@pytest.mark.asyncio
async def test_disabled_breaker_never_rejects():
    configure_storage_breaker(
        enabled=False, failure_threshold=1, reset_timeout_seconds=60, max_reset_timeout_seconds=60
    )
    sync = ScriptedClient(*[AGFSTimeoutError("s3 slow")] * 3)
    client = AsyncAGFSClient(sync)
    await _fail_times(client, "/local/acct/a", 3)

    assert await client.stat("/local/acct/a") == {"name": "/local/acct/a"}


def test_open_circuit_maps_to_unavailable():
    mapped = map_exception(AGFSCircuitOpenError("storage circuit open for /local"))

    assert mapped.code == "UNAVAILABLE"
    assert ERROR_CODE_TO_HTTP_STATUS[mapped.code] == 503
