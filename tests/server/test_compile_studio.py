"""Studio task pagination, submission retry and restart recovery contracts."""

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from openviking.server.identity import RequestContext, Role
from openviking.service.compile_targets import (
    new_operation,
)
from openviking.service.external_task_service import ExternalTaskService
from openviking.service.task_pagination import decode_cursor, encode_cursor, page_scope
from openviking.service.task_store import PersistentTaskStore
from openviking.service.task_tracker import TaskStatus, TaskTracker
from openviking_cli.exceptions import ConflictError, InvalidArgumentError
from openviking_cli.session.user_id import UserIdentifier
from tests.test_task_tracker import _FakeAgfs


@pytest.mark.parametrize(
    "skill,valid",
    [
        ("viking://system/compile/example-skills/llm-wiki/SKILL.md", True),
        ("viking://system/compile/example-skills", False),
        ("viking://system/compile/example-skills/llm-wiki/references", False),
        ("viking://system/memory/memory_templates/builtin", False),
    ],
)
def test_compile_builtin_skill_uri(skill, valid):
    """Compile accepts system Skill roots and rejects other system directories."""
    from openviking.service.compile_service import CompileRequest, CompileService
    from openviking_cli.utils.config.open_viking_config import CompileApiConfig

    service = CompileService(CompileApiConfig(), ExternalTaskService(), SimpleNamespace())
    ctx = RequestContext(user=UserIdentifier("acme", "alice"), role=Role.USER)
    request = CompileRequest.model_validate(
        {"from": ["viking://resources/source"], "to": "viking://resources/wiki", "skill": skill}
    )
    if valid:
        assert service._normalize_request_uris(request, ctx).skill == skill.removesuffix(
            "/SKILL.md"
        )
    else:
        with pytest.raises(InvalidArgumentError, match="skill must resolve"):
            service._normalize_request_uris(request, ctx)


@pytest.mark.parametrize(
    "target",
    [
        "viking://system",
        "viking://system/compile",
        "viking://system/compile/example-skills",
        "viking://system/resources/wiki",
    ],
)
def test_compile_rejects_system_target(target):
    from openviking.service.compile_service import CompileService

    CompileService._validate_target("viking://user/alice/skills")
    CompileService._validate_target("viking://agent/skills")

    with pytest.raises(InvalidArgumentError, match="system namespace"):
        CompileService._validate_target(target)


@pytest.mark.parametrize(
    "source",
    [
        "viking://system/compile/example-skills/llm-wiki",
        "viking://system/memory/memory_templates/custom/qa/input",
    ],
)
def test_compile_rejects_system_source(source):
    from openviking.service.compile_service import CompileRequest, CompileService
    from openviking_cli.utils.config.open_viking_config import CompileApiConfig

    service = CompileService(CompileApiConfig(), ExternalTaskService(), SimpleNamespace())
    ctx = RequestContext(user=UserIdentifier("acme", "alice"), role=Role.ADMIN)
    request = CompileRequest.model_validate(
        {
            "from": [source],
            "to": "viking://resources/wiki",
            "skill": "viking://system/compile/example-skills/llm-wiki",
        }
    )

    with pytest.raises(InvalidArgumentError, match="Compile source.*system namespace"):
        service._normalize_request_uris(request, ctx)


@pytest.mark.asyncio
async def test_compile_api_rejects_system_target_without_creating_task(service, app, client):
    from openviking.server.auth import get_request_context
    from openviking.service.task_tracker import get_task_tracker

    ctx = RequestContext(user=service.user, role=Role.USER, api_key="test-compile-key")
    app.dependency_overrides[get_request_context] = lambda: ctx
    owner = {"account_id": ctx.account_id, "user_id": ctx.user.user_id}
    tracker = get_task_tracker()
    before = {
        task.task_id for task in await tracker.list_tasks(task_type="compile", limit=None, **owner)
    }

    response = await client.post(
        "/api/v1/compile",
        json={
            "from": ["viking://resources/source"],
            "to": "viking://system/compile-output",
            "skill": "viking://system/compile/example-skills/llm-wiki",
        },
    )

    assert response.status_code == 400, response.text
    assert "system namespace" in response.text
    after = {
        task.task_id for task in await tracker.list_tasks(task_type="compile", limit=None, **owner)
    }
    assert after == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source",
    [
        "viking://system/compile/example-skills/llm-wiki",
        "viking://system/memory/memory_templates/custom/qa/input",
    ],
)
async def test_compile_api_rejects_system_source_without_creating_task(
    source, service, app, client
):
    from openviking.server.auth import get_request_context
    from openviking.service.task_tracker import get_task_tracker

    ctx = RequestContext(user=service.user, role=Role.ADMIN, api_key="test-compile-key")
    app.dependency_overrides[get_request_context] = lambda: ctx
    owner = {"account_id": ctx.account_id, "user_id": ctx.user.user_id}
    tracker = get_task_tracker()
    before = {
        task.task_id for task in await tracker.list_tasks(task_type="compile", limit=None, **owner)
    }

    response = await client.post(
        "/api/v1/compile",
        json={
            "from": [source],
            "to": "viking://resources/wiki",
            "skill": "viking://system/compile/example-skills/llm-wiki",
        },
    )

    assert response.status_code == 400, response.text
    assert "Compile source must not be in the system namespace" in response.text
    after = {
        task.task_id for task in await tracker.list_tasks(task_type="compile", limit=None, **owner)
    }
    assert after == before


@pytest.mark.asyncio
async def test_page_reads_past_200_and_isolates_owner():
    agfs = _FakeAgfs()
    store = PersistentTaskStore(agfs)
    tracker = TaskTracker(store)
    owner = {"account_id": "acme", "user_id": "alice"}
    for index in range(205):
        await tracker.create(
            "compile",
            task_id=f"cmp_{index:03}",
            meta={"request": {"to": "viking://resources/wiki"}},
            **owner,
        )
    await tracker.create("compile", task_id="foreign", account_id="acme", user_id="bob")
    # Empty cache: pagination must read durable records without repopulating all tasks.
    store = PersistentTaskStore(agfs)
    tracker = TaskTracker(store)
    filters = {
        "task_type": "compile",
        "status": None,
        "resource_id": None,
        "include_internal": False,
        "q": "wiki",
    }
    seen = []
    before = None
    while True:
        page = await tracker.list_tasks(**owner, limit=30, before=before, **filters)
        if not page:
            break
        seen.extend(task.task_id for task in page)
        before = (page[-1].created_at, page[-1].task_id)
    assert len(seen) == len(set(seen)) == 205
    assert seen[0] == "cmp_204"
    assert "foreign" not in seen


def test_cursor_is_bound_to_identity_and_filters():
    scope = page_scope(account="a", user="u", status="running")
    cursor = encode_cursor({"created_at": 123.4, "task_id": "cmp_a"}, scope)
    assert decode_cursor(cursor, scope) == (123.4, "cmp_a")
    with pytest.raises(InvalidArgumentError):
        decode_cursor(cursor, page_scope(account="a", user="other", status="running"))
    with pytest.raises(InvalidArgumentError):
        decode_cursor("broken", scope)


@pytest.mark.asyncio
async def test_concurrent_submission_retry_and_restart(monkeypatch):
    import ragfs_python

    import openviking.service.external_task_service as module
    from openviking.storage.queuefs.queue_manager import QueueManager

    agfs = _FakeAgfs()
    store = PersistentTaskStore(agfs)
    tracker = TaskTracker(store)
    monkeypatch.setattr(module, "get_task_tracker", lambda: tracker)
    monkeypatch.setattr("openviking.service.task_tracker.get_task_tracker", lambda: tracker)
    transport = ragfs_python.RAGFSBindingClient()
    transport.mount("queuefs", "/queue", {"backend": "memory"})
    manager = QueueManager(transport)
    manager.get_queue(manager.EXTERNAL_TASK, allow_create=True)
    monkeypatch.setattr(module, "get_queue_manager", lambda: manager)
    provider = SimpleNamespace(
        task_type="compile",
        task_id_prefix="cmp_",
        serialization_key=lambda payload: payload["to"],
        run=AsyncMock(return_value={"done": True}),
    )
    service = ExternalTaskService()
    service.register(provider)
    ctx = RequestContext(user=UserIdentifier("acme", "alice"), role=Role.USER)
    params = {
        "resource_id": None,
        "payload": {"from": ["viking://resources/a"], "to": "viking://resources/b"},
        "ctx": ctx,
        "idempotency_key": "test-submission-123",
    }
    try:
        results = await asyncio.gather(*(service.create("compile", **params) for _ in range(5)))
        assert len({t.task_id for t in results}) == 1
        tracker = TaskTracker(PersistentTaskStore(agfs))
        again = await service.create("compile", **params)
        assert again.task_id == results[0].task_id
        with pytest.raises(ConflictError):
            await service.create("compile", **{**params, "payload": {"to": "different"}})
        other = RequestContext(user=UserIdentifier("acme", "bob"), role=Role.USER)
        waiting = await service.create("compile", **{**params, "ctx": other})
        assert waiting.task_id != again.task_id

        # The server stops while the first task is mid-pipeline; its message is unacked.
        owner = {"account_id": ctx.account_id, "user_id": ctx.user.user_id}
        await tracker.start(again.task_id, stage="pipeline", **owner)
        tracker = TaskTracker(PersistentTaskStore(agfs))
        service = ExternalTaskService()
        service.register(provider)
        await manager.prepare_task_tracking(tracker)
        recovered = await manager.get_queued_tasks(tracker, manager.EXTERNAL_TASK)
        assert {task.task_id for task in recovered} == {again.task_id, waiting.task_id}
        await service.restore_tasks(recovered)

        # The interrupted task still owns its target, so the other one rotates behind it.
        assert not await service.execute(waiting.task_id, other.account_id, other.user.user_id)
        provider.run.assert_not_awaited()
        # Redelivery re-runs the interrupted task in-process as its owner, to completion.
        assert await service.execute(again.task_id, ctx.account_id, ctx.user.user_id)
        # The outcome is persisted before the queue ACK finalizes the status.
        resumed = await tracker.get(again.task_id, **owner)
        assert resumed.result == {"done": True}
        assert resumed.error is None
        run_ctx = provider.run.await_args.args[2]
        assert (run_ctx.account_id, run_ctx.user.user_id, run_ctx.role) == (
            "acme",
            "alice",
            Role.USER,
        )
        assert await service.execute(waiting.task_id, other.account_id, other.user.user_id)
        assert (await tracker.get(waiting.task_id, account_id="acme", user_id="bob")).result == {
            "done": True
        }
    finally:
        transport.close()


@pytest.mark.asyncio
async def test_http_contract_preserves_legacy_list_and_retries(monkeypatch, tmp_path):
    import httpx
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    import openviking.server.routers.compile as compile_router
    import openviking.server.routers.tasks as task_router
    import openviking.service.external_task_service as external
    import openviking.service.task_tracker as tracker_module
    from openviking.server.auth import get_request_context
    from openviking.service.compile_service import CompileService
    from openviking_cli.exceptions import OpenVikingError
    from openviking_cli.utils.config.open_viking_config import CompileApiConfig

    agfs = _FakeAgfs()
    store = PersistentTaskStore(agfs)
    tracker = TaskTracker(store)
    monkeypatch.setattr(external, "get_task_tracker", lambda: tracker)
    monkeypatch.setattr(task_router, "get_task_tracker", lambda: tracker)
    monkeypatch.setattr(tracker_module, "get_task_tracker", lambda: tracker)
    monkeypatch.setattr(external, "get_queue_manager", lambda: SimpleNamespace(enqueue=AsyncMock()))
    tasks = ExternalTaskService()
    fs = SimpleNamespace(
        stat=AsyncMock(
            side_effect=lambda uri, ctx, **_: {"uri": uri, "isDir": not uri.endswith("SKILL.md")}
        ),
        ensure_write_access=AsyncMock(),
    )
    compile_service = CompileService(CompileApiConfig(), tasks, fs)

    def configure_runtime():
        compile_service.configure_runtime(
            service=SimpleNamespace(), vlm_resolver=None, work_root=tmp_path, model_concurrency=1
        )

    configure_runtime()
    tasks.register(compile_service)
    monkeypatch.setattr(
        compile_router, "get_service", lambda: SimpleNamespace(compile=compile_service)
    )
    ctx = RequestContext(user=UserIdentifier("acme", "alice"), role=Role.USER)
    app = FastAPI()
    app.include_router(compile_router.router)
    app.include_router(task_router.router)
    app.dependency_overrides[get_request_context] = lambda: ctx

    @app.exception_handler(OpenVikingError)
    async def on_error(request, error):
        return JSONResponse(
            status_code=409 if error.code == "CONFLICT" else 400, content={"error": error.code}
        )

    payload = {
        "from": ["viking://resources/source"],
        "to": "viking://resources/wiki",
        "skill": "viking://agent/skills/wiki",
        "args": {"wiki_links": True},
    }
    headers = {"Idempotency-Key": "http-retry-key-123"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        empty_page = await client.get(
            "/api/v1/tasks", params={"pagination": "cursor", "task_type": "compile", "limit": 30}
        )
        assert empty_page.status_code == 200, empty_page.text
        assert empty_page.json()["result"] == {
            "items": [],
            "has_more": False,
            "next_cursor": None,
        }
        first = await client.post("/api/v1/compile", json=payload, headers=headers)
        assert first.status_code == 202, first.text
        second = await client.post("/api/v1/compile", json=payload, headers=headers)
        task_id = first.json()["result"]["task_id"]
        assert second.json()["result"]["task_id"] == task_id
        # Only the server-resolved identity is kept; no forwarded credentials.
        auth = await tracker.get_task_auth(task_id, account_id="acme", user_id="alice")
        assert auth["request_identity"]["role"] == "user"
        assert "openviking_connection" not in auth
        unsupported = await client.post(
            "/api/v1/compile", json={**payload, "args": {"api_key": "x"}}
        )
        assert unsupported.status_code == 400
        recovery = await client.get("/api/v1/compile/submissions/http-retry-key-123")
        assert recovery.json()["result"]["task_id"] == task_id
        assert isinstance((await client.get("/api/v1/tasks")).json()["result"], list)
        paged = await client.get(
            "/api/v1/tasks", params={"pagination": "cursor", "task_type": "compile"}
        )
        assert paged.json()["result"]["items"][0]["task_id"] == task_id
        assert (await client.get("/api/v1/tasks", params={"limit": 0})).status_code == 422
        conflict = await client.post(
            "/api/v1/compile", json={**payload, "instruction": "changed"}, headers=headers
        )
        assert conflict.status_code == 409
        stopped = await client.post(f"/api/v1/tasks/{task_id}/cancel")
        assert stopped.status_code == 200
        assert stopped.json()["result"]["status"] in {"cancelled", "cancelling"}
        retry_after_cancel = await client.post("/api/v1/compile", json=payload, headers=headers)
        assert retry_after_cancel.json()["result"]["task_id"] == task_id
        assert "submission_hash" not in retry_after_cancel.json()["result"]["meta"]
        ctx = RequestContext(user=UserIdentifier("acme", "alice"), role=Role.ROOT)
        store = PersistentTaskStore(agfs)
        tracker = TaskTracker(store)
        root_page = await client.get(
            "/api/v1/tasks", params={"pagination": "cursor", "task_type": "compile"}
        )
        assert root_page.json()["result"]["items"][0]["task_id"] == task_id
        assert tracker.count() == 0
        detail = await client.get(f"/api/v1/tasks/{task_id}")
        assert detail.status_code == 200
        assert detail.json()["result"]["task_id"] == task_id

        # Recovery must not need the old resources or a currently configured backend.
        from openviking_cli.exceptions import NotFoundError

        fs.stat.side_effect = NotFoundError("deleted-source", "resource")
        compile_service._runner = None
        restored = await client.post("/api/v1/compile", json=payload, headers=headers)
        assert restored.status_code == 202, restored.text
        assert restored.json()["result"]["task_id"] == task_id
        changed = await client.post(
            "/api/v1/compile", json={**payload, "args": {"wiki_links": False}}, headers=headers
        )
        assert changed.status_code == 409
        configure_runtime()
        rejected = await client.post(
            "/api/v1/compile", json=payload, headers={"Idempotency-Key": "new-invalid-request-key"}
        )
        assert rejected.status_code != 202
        ctx = RequestContext(user=UserIdentifier("acme", "bob"), role=Role.USER)
        assert (await client.get("/api/v1/tasks", params={"pagination": "cursor"})).json()[
            "result"
        ]["items"] == []


@pytest.mark.asyncio
async def test_schedule_retries_initial_failure_and_disables_deleted_targets(service, monkeypatch):
    """Initial failure remains retryable; invalid credentials and deletion disable scheduling."""
    from datetime import datetime, timedelta

    import openviking.service.compile_scheduler as scheduling

    store = service.compile.lifecycle.store
    account = service.user.account_id
    ctx = RequestContext(user=service.user, role=Role.USER)
    target = "viking://resources/scheduled"
    async with store.edit(account, target, create=True):
        pass
    config = await service.compile.get_config(target, ctx)
    assert config["auto_update"] is False and config["update_schedule"] is None
    schedule = {"frequency": "daily", "hour": 0, "minute": 0}

    scheduler = scheduling.CompileScheduler(service.compile, store, service.viking_fs)
    scheduler.install_expiry(
        SimpleNamespace(register_handler=Mock(), report=AsyncMock(), unregister=AsyncMock())
    )
    now = datetime(2026, 10, 22, 12, tzinfo=scheduling.TZ)
    assert await scheduler.trigger_if_due(account, target, now) == "not_due"

    async with store.edit(account, target) as record:
        record.update(
            initialized=False,
            last_run={"status": "failed"},
            auto_update=True,
            update_schedule=schedule,
            auto_update_enabled_at="2026-10-20T00:00:00+08:00",
        )
    with monkeypatch.context() as patch:
        patch.setattr(scheduler, "_executor", AsyncMock(return_value=(ctx, {})))
        submit = AsyncMock()
        patch.setattr(service.compile, "create_scheduled", submit)
        assert await scheduler.trigger_if_due(account, target, now) == "submitted"
        assert await scheduler.trigger_if_due(account, target, now) == "not_due"
        submit.assert_awaited_once()
    assert await scheduler.trigger_if_due(account, target, now + timedelta(days=1)) == "disabled"
    invalid = await store.get(account, target)
    assert invalid["auto_update"] is False and invalid["update_schedule"] is None
    assert (await store.list_summaries(account))[0]["update_schedule"] is None

    async with store.edit(account, target) as record:
        record.update(auto_update=True, update_schedule=schedule)
    await service.compile.lifecycle.versions.after_remove(target, ctx)
    deleted = await store.get(account, target)
    assert deleted["status"] == "deleted" and deleted["update_schedule"] is None
    async with store.edit(account, target, create=True):
        pass
    reused = await store.get(account, target)
    assert reused["status"] == "active" and reused["auto_update"] is False
    assert reused["update_schedule"] is None


@pytest.mark.asyncio
async def test_cursor_prunes_cold_expired_records_without_loading_cache():
    agfs = _FakeAgfs()
    store = PersistentTaskStore(agfs)
    tracker = TaskTracker(store)
    owner = {"account_id": "acme", "user_id": "alice"}
    for task_id, status, days in [
        ("expired-complete", TaskStatus.COMPLETED, 2),
        ("expired-cancelled", TaskStatus.CANCELLED, 2),
        ("expired-failed", TaskStatus.FAILED, 8),
        ("recent-failed", TaskStatus.FAILED, 2),
        ("active", TaskStatus.RUNNING, 8),
    ]:
        task = await tracker.create("compile", task_id=task_id, **owner)
        path = f"/local/acme/_system/tasks/alice/{task.task_id}.json"
        payload = json.loads(agfs.files[path])
        payload["status"] = status.value
        payload["updated_at"] = time.time() - days * 86400
        agfs.files[path] = json.dumps(payload).encode()
    store = PersistentTaskStore(agfs)
    tracker = TaskTracker(store)
    await tracker.delete_expired()
    page = await asyncio.wait_for(
        tracker.list_tasks(
            **owner,
            limit=30,
            task_type="compile",
            status=None,
            resource_id=None,
            include_internal=False,
            q=None,
        ),
        timeout=3,
    )
    assert {task.task_id for task in page} == {"recent-failed", "active"}
    assert {task.task_id for task in await store.list("acme", user_id="alice")} == {
        "recent-failed",
        "active",
    }


@pytest.mark.asyncio
async def test_cursor_cleanup_rechecks_task_updated_after_scan():
    agfs = _FakeAgfs()
    store = PersistentTaskStore(agfs)
    tracker = TaskTracker(store)
    owner = {"account_id": "acme", "user_id": "alice"}
    task = await tracker.create("compile", task_id="updated-after-scan", **owner)
    path = f"/local/acme/_system/tasks/alice/{task.task_id}.json"
    payload = json.loads(agfs.files[path])
    payload["status"] = TaskStatus.COMPLETED.value
    payload["updated_at"] = time.time() - 2 * 86400
    agfs.files[path] = json.dumps(payload).encode()
    store = PersistentTaskStore(agfs)
    tracker = TaskTracker(store)
    record_lock = ("acme", "alice", task.task_id)
    async with store._record_locks.acquire(record_lock):
        cleanup = asyncio.create_task(tracker.delete_expired())
        await asyncio.sleep(0)
        payload["updated_at"] = time.time()
        agfs.files[path] = json.dumps(payload).encode()
    await asyncio.wait_for(cleanup, timeout=3)
    page = await tracker.list_tasks(
        **owner,
        limit=30,
        task_type="compile",
        status=None,
        resource_id=None,
        include_internal=False,
        q=None,
    )
    assert [record.task_id for record in page] == [task.task_id]
    assert await store.get_task(task.task_id, **owner) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_dir", ["operation_outputs", "operations"])
async def test_compile_history_retention_and_retry(service, monkeypatch, failed_dir):
    store = service.compile.lifecycle.store
    account = service.user.account_id
    target = "viking://resources/history"
    async with store.edit(account, target, create=True):
        pass
    now = time.time()
    for operation_id, status, finished_at in (
        ("expired", "completed", now - 604801),
        ("boundary", "failed", now - 604800),
        ("missing", "cancelled", None),
        ("running", "running", now - 604801),
    ):
        operation = new_operation(operation_id, "restore", {}, "user", status=status)
        operation["finished_at"] = finished_at
        await store.merge_outputs(account, target, operation_id, [])
        await store.put_operation(account, target, operation)
    async with store.edit(account, "viking://resources/history") as record:
        record["active_task_id"] = "running-task"
    assert await store.delete_expired(now=now, limit=256) == 0
    async with store.edit(account, "viking://resources/history") as record:
        record["active_task_id"] = None
    remove = store.remove

    async def fail_remove(path, **kwargs):
        if path.endswith(f"/{failed_dir}/expired.json"):
            raise OSError("history deletion failed")
        await remove(path, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(store, "remove", fail_remove)
        assert await store.delete_expired(now=now, limit=256) == 0
    assert await store.get_operation(account, target, "expired") is not None
    for _ in range(4):
        await store.delete_expired(now=now, limit=2)
    assert await store.get_operation(account, target, "expired") is None
    assert await store.get_outputs(account, target, "expired") is None
    for operation_id in ("boundary", "missing", "running"):
        assert await store.get_operation(account, target, operation_id) is not None
        assert await store.get_outputs(account, target, operation_id) is not None
