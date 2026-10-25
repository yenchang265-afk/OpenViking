"""A Compile interrupted by a server stop resumes from its durable queue message."""

import asyncio
import threading
import time

import pytest

from openviking.server.identity import RequestContext, Role
from openviking.service.external_task_service import ExternalTaskService
from openviking.service.task_store import PersistentTaskStore
from openviking.service.task_tracker import TaskStatus, TaskTracker
from openviking.storage.queuefs.external_task_processor import ExternalTaskProcessor
from openviking.storage.queuefs.queue_manager import QueueManager
from openviking_cli.session.user_id import UserIdentifier
from tests.test_task_tracker import _FakeAgfs


class _Provider:
    """Blocks the first attempt until the server stops; later attempts succeed."""

    task_type = "compile"
    task_id_prefix = "cmp_"

    def __init__(self, *, block: bool):
        self.block = block
        self.started = threading.Event()
        self.attempts = 0

    def serialization_key(self, payload):
        return payload["to"]

    async def run(self, task, payload, ctx, *, progress, cancelled):
        self.attempts += 1
        await progress("pipeline", {})
        self.started.set()
        if self.block:
            await asyncio.Event().wait()
        return {"to": payload["to"], "pages": 1}


def _server(db_path, provider):
    import ragfs_python

    transport = ragfs_python.RAGFSBindingClient()
    transport.mount(
        "queuefs", "/queue", {"backend": "sqlite", "db_path": str(db_path), "recover_stale_sec": 0}
    )
    # The default concurrent worker drains briefly, then cancels in-flight work on stop.
    manager = QueueManager(transport, max_concurrent_external_task=2)
    service = ExternalTaskService()
    service.register(provider)
    manager.get_queue(
        manager.EXTERNAL_TASK, dequeue_handler=ExternalTaskProcessor(service), allow_create=True
    )
    return transport, manager, service


async def _wait_for(predicate, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if await predicate():
            return
        await asyncio.sleep(0.1)
    raise AssertionError("condition not reached")


@pytest.mark.asyncio
async def test_compile_interrupted_by_restart_runs_again_to_completion(tmp_path, monkeypatch):
    import openviking.service.external_task_service as external
    import openviking.service.task_tracker as tracker_module

    agfs = _FakeAgfs()
    state = {"tracker": TaskTracker(PersistentTaskStore(agfs)), "manager": None}
    monkeypatch.setattr(external, "get_task_tracker", lambda: state["tracker"])
    monkeypatch.setattr(tracker_module, "get_task_tracker", lambda: state["tracker"])
    monkeypatch.setattr(external, "get_queue_manager", lambda: state["manager"])
    db_path = tmp_path / "queue.db"
    ctx = RequestContext(user=UserIdentifier("acme", "alice"), role=Role.USER)
    owner = {"account_id": "acme", "user_id": "alice"}

    first = _Provider(block=True)
    transport, manager, service = _server(db_path, first)
    state["manager"] = manager
    try:
        task = await service.create(
            "compile",
            resource_id="viking://resources/raw",
            payload={"from": ["viking://resources/raw"], "to": "viking://resources/wiki"},
            ctx=ctx,
        )
        manager.start()
        assert await asyncio.to_thread(first.started.wait, 20)
        running = await state["tracker"].get(task.task_id, **owner)
        assert (running.status, running.stage) == (TaskStatus.RUNNING, "pipeline")
    finally:
        # Shutdown cancels the attempt without acknowledging its message.
        manager.stop()
        transport.close()

    # A new process: fresh task store cache, queue transport and workers.
    state["tracker"] = TaskTracker(PersistentTaskStore(agfs))
    second = _Provider(block=False)
    transport, manager, service = _server(db_path, second)
    state["manager"] = manager
    try:
        await manager.prepare_task_tracking(state["tracker"])
        restored = await manager.get_queued_tasks(state["tracker"], manager.EXTERNAL_TASK)
        assert [item.task_id for item in restored] == [task.task_id]
        await service.restore_tasks(restored)
        manager.start()

        async def completed():
            current = await state["tracker"].get(task.task_id, **owner)
            return current.status == TaskStatus.COMPLETED

        await _wait_for(completed)
        done = await state["tracker"].get(task.task_id, **owner)
        assert done.result == {"to": "viking://resources/wiki", "pages": 1}
        assert second.attempts == 1
        # The interrupted start and the completed re-run are both counted.
        assert done.meta["attempts"] == 2
    finally:
        manager.stop()
        transport.close()
