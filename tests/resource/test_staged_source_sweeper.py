# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Sweeping staged-source copies that task cleanup left behind."""

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from openviking.resource import staged_source_sweeper as sweeper

NOW = datetime(2026, 10, 9, 16, 0)
TTL = 7 * 24 * 3600
SPACE = "viking://temp/alice"


def _ctx(account: str = "acme", space: str = "alice"):
    return SimpleNamespace(account_id=account, user=SimpleNamespace(user_space_name=lambda: space))


def _leaf(when: datetime, suffix: str = "abc123") -> str:
    return f"{SPACE}/{when.strftime('%m%d%H%M')}_{suffix}"


class _FakeVikingFS:
    def __init__(self, entries, existing=(), fail_ls=False, stuck=()):
        self.entries = entries
        self.existing = set(existing)
        self.fail_ls = fail_ls
        # Like VikingFS.delete_temp, a failed rm is logged there, not raised.
        self.stuck = set(stuck)
        self.deleted = []
        self.listed = []

    async def ls(self, uri, **kwargs):
        self.listed.append(uri)
        if self.fail_ls:
            raise RuntimeError("listing failed")
        return self.entries

    async def exists(self, uri, ctx=None):
        return uri in self.existing

    async def delete_temp(self, temp_uri, ctx=None):
        self.deleted.append(temp_uri)
        if temp_uri not in self.stuck:
            self.existing = {uri for uri in self.existing if not uri.startswith(f"{temp_uri}/")}


@pytest.fixture(autouse=True)
def _reset_throttle():
    sweeper._NEXT_SWEEP_AT.clear()
    yield
    sweeper._NEXT_SWEEP_AT.clear()


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("10091530_abc123", datetime(2026, 10, 9, 15, 30)),
        # A leaf "later" than now was created last year (names carry no year).
        ("12311200_abc123", datetime(2025, 12, 31, 12, 0)),
        ("02301200_abc123", None),
        ("1009153_abc123", None),
        ("10091530_ABC123", None),
        ("source", None),
    ],
)
def test_staged_leaf_created_at(name, expected):
    created = sweeper.staged_leaf_created_at(name, NOW)
    assert created == (expected.timestamp() if expected else None)


async def test_sweep_removes_only_expired_staged_sources():
    old = NOW - timedelta(days=8)
    expired_staged = _leaf(old, "aaaaaa")
    expired_other = _leaf(old, "bbbbbb")
    fresh_staged = _leaf(NOW - timedelta(days=1), "cccccc")
    vfs = _FakeVikingFS(
        entries=[
            {"isDir": True, "uri": expired_staged},
            {"isDir": True, "uri": f"{expired_other}/"},
            {"isDir": True, "uri": fresh_staged},
            {"isDir": False, "uri": _leaf(old, "dddddd")},
            {"isDir": True, "uri": f"{SPACE}/not-a-leaf"},
        ],
        existing={f"{expired_staged}/source", f"{fresh_staged}/source"},
    )

    removed = await sweeper.sweep_expired_staged_sources(vfs, _ctx(), TTL, now=NOW)

    assert removed == 1
    assert vfs.listed == [SPACE]
    assert vfs.deleted == [expired_staged]


async def test_sweep_spares_bundles_of_long_running_tasks():
    queued_since = NOW - timedelta(days=10)
    # Staged just before its still-active task was created, ten days ago.
    in_use = _leaf(queued_since - timedelta(minutes=5), "aaaaaa")
    orphaned = _leaf(queued_since - timedelta(hours=3), "bbbbbb")
    vfs = _FakeVikingFS(
        entries=[{"isDir": True, "uri": in_use}, {"isDir": True, "uri": orphaned}],
        existing={f"{in_use}/source", f"{orphaned}/source"},
    )

    removed = await sweeper.sweep_expired_staged_sources(
        vfs, _ctx(), TTL, now=NOW, oldest_active_at=queued_since.timestamp()
    )

    assert removed == 1
    assert vfs.deleted == [orphaned]


async def test_sweep_does_not_count_deletes_that_left_the_bundle():
    stuck = _leaf(NOW - timedelta(days=8), "aaaaaa")
    vfs = _FakeVikingFS(
        entries=[{"isDir": True, "uri": stuck}],
        existing={f"{stuck}/source"},
        stuck={stuck},
    )

    assert await sweeper.sweep_expired_staged_sources(vfs, _ctx(), TTL, now=NOW) == 0
    assert vfs.deleted == [stuck]


async def test_sweep_is_disabled_by_zero_ttl():
    vfs = _FakeVikingFS(entries=[])
    assert await sweeper.sweep_expired_staged_sources(vfs, _ctx(), 0, now=NOW) == 0
    assert vfs.listed == []


async def test_sweep_survives_listing_failure():
    vfs = _FakeVikingFS(entries=[], fail_ls=True)
    assert await sweeper.sweep_expired_staged_sources(vfs, _ctx(), TTL, now=NOW) == 0


async def test_schedule_runs_at_most_once_per_interval_per_space(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(sweeper.time, "monotonic", lambda: clock[0])
    vfs = _FakeVikingFS(entries=[])
    tasks = set()

    assert sweeper.schedule_staged_source_sweep(vfs, _ctx(), TTL, background_tasks=tasks)
    assert not sweeper.schedule_staged_source_sweep(vfs, _ctx(), TTL, background_tasks=tasks)
    # Another user's space has its own throttle.
    assert sweeper.schedule_staged_source_sweep(vfs, _ctx(space="bob"), TTL, background_tasks=tasks)
    clock[0] += sweeper.STAGED_SOURCE_SWEEP_INTERVAL_S
    assert sweeper.schedule_staged_source_sweep(vfs, _ctx(), TTL, background_tasks=tasks)

    await asyncio.gather(*list(tasks))
    assert tasks == set()
    assert vfs.listed == [SPACE, "viking://temp/bob", SPACE]


async def test_schedule_skips_sweep_when_active_tasks_are_unknown():
    old = _leaf(NOW - timedelta(days=30))
    vfs = _FakeVikingFS(entries=[{"isDir": True, "uri": old}], existing={f"{old}/source"})
    tasks = set()

    async def lookup_fails():
        raise RuntimeError("task store unavailable")

    assert sweeper.schedule_staged_source_sweep(
        vfs, _ctx(), TTL, background_tasks=tasks, oldest_active_at=lookup_fails
    )
    await asyncio.gather(*list(tasks))

    assert vfs.listed == []


def test_schedule_skips_when_disabled():
    vfs = _FakeVikingFS(entries=[])
    assert not sweeper.schedule_staged_source_sweep(vfs, _ctx(), 0, background_tasks=set())


def test_resource_service_schedules_sweep_with_configured_ttl(monkeypatch):
    from openviking.service.resource_service import ResourceService

    calls = []
    monkeypatch.setattr(
        sweeper,
        "schedule_staged_source_sweep",
        lambda vfs, ctx, ttl, *, background_tasks, oldest_active_at: calls.append(
            (vfs, ctx, ttl, oldest_active_at)
        ),
    )
    config = SimpleNamespace(storage=SimpleNamespace(staged_source_ttl_seconds=123))
    monkeypatch.setattr(
        "openviking_cli.utils.config.open_viking_config.get_openviking_config", lambda: config
    )
    service = object.__new__(ResourceService)
    service._viking_fs = object()
    service._background_tasks = set()
    ctx = _ctx()

    service._schedule_staged_source_sweep(ctx)

    assert [call[:3] for call in calls] == [(service._viking_fs, ctx, 123)]
    assert callable(calls[0][3])


async def test_resource_service_reports_oldest_active_add_resource(monkeypatch):
    from openviking.service.resource_service import ResourceService
    from openviking.service.task_tracker import TaskStatus

    def task(task_type, status, created_at):
        return SimpleNamespace(task_type=task_type, status=status, created_at=created_at)

    tracker = SimpleNamespace(
        list_tasks=AsyncMock(
            return_value=[
                task("add_resource", TaskStatus.RUNNING, 300.0),
                task("add_resource", TaskStatus.PENDING, 200.0),
                task("add_resource", TaskStatus.COMPLETED, 50.0),
                task("add_skill", TaskStatus.RUNNING, 10.0),
            ]
        )
    )
    monkeypatch.setattr("openviking.service.task_tracker.get_task_tracker", lambda: tracker)
    ctx = SimpleNamespace(account_id="acme", user=SimpleNamespace(user_id="alice"))

    oldest = await object.__new__(ResourceService)._oldest_active_add_resource_at(ctx)

    assert oldest == 200.0
    tracker.list_tasks.assert_awaited_once_with(
        task_type="add_resource", limit=None, account_id="acme", user_id="alice"
    )


def test_ttl_must_stay_below_a_year():
    # Leaf names carry no year, so ages are only meaningful under a year.
    from pydantic import ValidationError

    from openviking_cli.utils.config.storage_config import StorageConfig

    assert StorageConfig(staged_source_ttl_seconds=180 * 24 * 3600)
    with pytest.raises(ValidationError):
        StorageConfig(staged_source_ttl_seconds=365 * 24 * 3600)
