"""CompileService validation and dispatch, and durable task outcomes."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from openviking.server.identity import RequestContext, Role
from openviking.service.compile_service import CompileRequest, CompileService
from openviking.service.external_task_service import ExternalTaskError, ExternalTaskService
from openviking.service.task_store import PersistentTaskStore
from openviking.service.task_tracker import TaskStatus, TaskTracker
from openviking.storage.queuefs.external_task_processor import ExternalTaskProcessor
from openviking.storage.queuefs.queue_manager import QueueManager
from openviking_cli.exceptions import InvalidArgumentError
from openviking_cli.session.user_id import UserIdentifier
from openviking_cli.utils.config.open_viking_config import CompileApiConfig
from tests.compile.test_compile_restart import _wait_for
from tests.test_task_tracker import _FakeAgfs

CTX = RequestContext(user=UserIdentifier("acme", "alice"), role=Role.USER)
OWNER = {"account_id": "acme", "user_id": "alice"}


@pytest.fixture(autouse=True)
def tracker(monkeypatch):
    """An isolated task tracker for capacity checks and durable task tests."""
    import openviking.service.task_tracker as tracker_module

    tracker = TaskTracker(PersistentTaskStore(_FakeAgfs()))
    monkeypatch.setattr(tracker_module, "get_task_tracker", lambda: tracker)
    return tracker


def _compile_service(tmp_path, fs=None, config=None):
    fs = fs or SimpleNamespace(
        stat=AsyncMock(
            side_effect=lambda uri, ctx: {"uri": uri, "isDir": not uri.endswith("SKILL.md")}
        ),
        ensure_write_access=AsyncMock(),
    )
    tasks = SimpleNamespace(create=AsyncMock(return_value="task"), recover_submission=AsyncMock())
    service = CompileService(config or CompileApiConfig(), tasks, fs)
    service.configure_runtime(
        service=SimpleNamespace(), vlm_resolver=None, work_root=tmp_path, model_concurrency=2
    )
    return service, tasks


def _request(**overrides):
    return CompileRequest.model_validate(
        {
            "from": ["viking://resources/raw"],
            "to": "viking://resources/wiki",
            "skill": "viking://agent/skills/llm-wiki",
            **overrides,
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "args",
    [{"api_key": "x"}, {"wiki_links": "yes"}, {"last_compile_time": "not-a-time"}],
)
async def test_create_rejects_unsupported_args(tmp_path, args):
    service, tasks = _compile_service(tmp_path)
    with pytest.raises(InvalidArgumentError):
        await service.create(_request(args=args), ctx=CTX)
    tasks.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_rejects_memory_targets_for_skill_compile(tmp_path):
    service, _ = _compile_service(tmp_path)
    with pytest.raises(InvalidArgumentError, match="--skill memory"):
        await service.create(_request(to="viking://user/alice/memories/entities"), ctx=CTX)


@pytest.mark.asyncio
async def test_create_queues_normalized_payload(tmp_path):
    service, tasks = _compile_service(tmp_path)
    await service.create(
        _request(args={"wiki_links": True, "last_compile_time": 1700000000}), ctx=CTX
    )
    kwargs = tasks.create.await_args.kwargs
    assert kwargs["payload"] == {
        "from": ["viking://resources/raw"],
        "to": "viking://resources/wiki",
        "skill": "viking://agent/skills/llm-wiki",
        "args": {"wiki_links": True, "last_compile_time": 1700000000},
    }
    assert kwargs["ctx"] is CTX
    request = service._sanitized_request(kwargs["payload"])
    assert request.wiki_links is True
    assert request.last_compile_time.year == 2023
    assert request.instruction_provided is False


@pytest.mark.asyncio
async def test_memory_skill_runs_through_memory_runner(tmp_path):
    service, _ = _compile_service(tmp_path)
    memory = SimpleNamespace(run=AsyncMock(return_value={"skill": "memory"}))
    service._memory_runner = memory
    progress = AsyncMock()
    payload = {"to": "viking://user/alice/memories", "skill": "memory"}
    task = SimpleNamespace(task_id="cmp_memory")
    result = await service.run(task, payload, CTX, progress=progress, cancelled=AsyncMock())
    assert result == {"skill": "memory"}
    progress.assert_awaited_once_with("consolidating", {})
    memory.run.assert_awaited_once_with("cmp_memory", payload, CTX)


class _Provider:
    task_type = "compile"
    task_id_prefix = "cmp_"

    def __init__(self, run):
        self.run = run

    def serialization_key(self, payload):
        return payload["to"]


@pytest.fixture
def durable(monkeypatch):
    """A tracker and in-memory QueueFS wired like the server's ExternalTask queue."""
    import ragfs_python

    import openviking.service.external_task_service as external
    import openviking.service.task_tracker as tracker_module

    tracker = TaskTracker(PersistentTaskStore(_FakeAgfs()))
    transport = ragfs_python.RAGFSBindingClient()
    transport.mount("queuefs", "/queue", {"backend": "memory"})
    manager = QueueManager(transport, max_concurrent_external_task=2)
    monkeypatch.setattr(external, "get_task_tracker", lambda: tracker)
    monkeypatch.setattr(tracker_module, "get_task_tracker", lambda: tracker)
    monkeypatch.setattr(external, "get_queue_manager", lambda: manager)

    def start(provider):
        service = ExternalTaskService()
        service.register(provider)
        manager.get_queue(
            manager.EXTERNAL_TASK, dequeue_handler=ExternalTaskProcessor(service), allow_create=True
        )
        manager.start()
        return service

    yield SimpleNamespace(tracker=tracker, start=start)
    manager.stop()
    transport.close()


async def _submit(service):
    return await service.create(
        "compile",
        resource_id=None,
        payload={"from": ["viking://resources/raw"], "to": "viking://resources/wiki"},
        ctx=CTX,
    )


@pytest.mark.asyncio
async def test_failed_task_keeps_partial_result(durable):
    async def run(task, payload, ctx, *, progress, cancelled):
        raise ExternalTaskError("MEMORY_CONSOLIDATION_FAILED", "nothing applied", result={"n": 0})

    task = await _submit(durable.start(_Provider(run)))

    async def failed():
        current = await durable.tracker.get(task.task_id, **OWNER)
        return current.status == TaskStatus.FAILED

    await _wait_for(failed)
    current = await durable.tracker.get(task.task_id, **OWNER)
    assert current.error == "MEMORY_CONSOLIDATION_FAILED: nothing applied"
    assert current.result == {"n": 0}


@pytest.mark.asyncio
async def test_cancel_stops_running_compile_before_publishing(durable):
    started = threading.Event()
    published = AsyncMock()

    async def run(task, payload, ctx, *, progress, cancelled):
        started.set()
        await asyncio.Event().wait()
        await published()

    task = await _submit(durable.start(_Provider(run)))
    assert await asyncio.to_thread(started.wait, 20)
    await durable.tracker.cancel(task.task_id, **OWNER)

    async def cancelled():
        current = await durable.tracker.get(task.task_id, **OWNER)
        return current.status == TaskStatus.CANCELLED

    await _wait_for(cancelled)
    published.assert_not_awaited()


def test_legacy_task_auth_restores_user_context():
    from openviking.service.external_task_service import restore_request_context

    legacy = {"openviking_connection": {"api_key": "k", "account_id": "acme", "user_id": "alice"}}
    ctx = restore_request_context(legacy, "acme", "alice")
    assert (ctx.account_id, ctx.user.user_id, ctx.role) == ("acme", "alice", Role.USER)


@pytest.mark.asyncio
async def test_task_interrupted_too_often_fails_without_running(monkeypatch):
    import openviking.service.external_task_service as external
    import openviking.service.task_tracker as tracker_module

    tracker = TaskTracker(PersistentTaskStore(_FakeAgfs()))
    monkeypatch.setattr(external, "get_task_tracker", lambda: tracker)
    monkeypatch.setattr(tracker_module, "get_task_tracker", lambda: tracker)
    monkeypatch.setattr(external, "get_queue_manager", lambda: SimpleNamespace(enqueue=AsyncMock()))
    run = AsyncMock(return_value={})
    service = ExternalTaskService()
    service.register(_Provider(run))
    task = await _submit(service)
    await tracker.update_meta(task.task_id, {"attempts": external.MAX_TASK_ATTEMPTS}, **OWNER)

    assert await service.execute(task.task_id, "acme", "alice")
    run.assert_not_awaited()
    current = await tracker.get(task.task_id, **OWNER)
    assert current.error.startswith("INTERRUPTED:")


@pytest.mark.asyncio
async def test_create_rejects_beyond_active_task_cap(tmp_path, tracker):
    from openviking_cli.exceptions import ResourceExhaustedError

    service, tasks = _compile_service(
        tmp_path, config=CompileApiConfig(max_active_tasks_per_user=2)
    )
    await tracker.create("compile", task_id="cmp_a", **OWNER)
    await service.create(_request(), ctx=CTX)
    await tracker.create("compile", task_id="cmp_b", **OWNER)
    # Another user's tasks do not count against this user.
    await tracker.create("compile", task_id="cmp_c", account_id="acme", user_id="bob")
    with pytest.raises(ResourceExhaustedError):
        await service.create(_request(), ctx=CTX)
    assert tasks.create.await_count == 1


@pytest.mark.asyncio
async def test_attempt_runs_with_owner_access_narrowed_to_current():
    service = ExternalTaskService()
    stored = RequestContext(
        user=UserIdentifier("acme", "alice"), role=Role.ADMIN, group_ids=("eng", "ops")
    )
    assert await service._current_identity(stored) is stored

    service.set_identity_resolver(AsyncMock(return_value=(Role.USER, ("eng", "sales"))))
    narrowed = await service._current_identity(stored)
    assert (narrowed.role, narrowed.group_ids) == (Role.USER, ("eng",))

    # A later promotion never widens the submit-time identity.
    service.set_identity_resolver(AsyncMock(return_value=(Role.ROOT, ("eng", "ops"))))
    assert (await service._current_identity(stored)).role == Role.ADMIN

    service.set_identity_resolver(AsyncMock(return_value=None))
    with pytest.raises(ExternalTaskError) as raised:
        await service._current_identity(stored)
    assert raised.value.code == "UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_key_store_resolver_reads_role_and_groups():
    from openviking.service.external_task_service import key_store_identity_resolver

    manager = SimpleNamespace(
        get_user=AsyncMock(side_effect=lambda a, u: {"role": "admin"} if u == "alice" else None),
        get_user_group_ids=AsyncMock(return_value=["eng"]),
    )
    resolve = key_store_identity_resolver(manager)
    assert await resolve("acme", "alice") == ("admin", ("eng",))
    assert await resolve("acme", "ghost") is None
