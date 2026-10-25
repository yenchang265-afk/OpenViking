"""Upstream Compile lifecycle (target registry, incremental plans) on the in-server runtime."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from openviking.compile.models import CompileFailure
from openviking.compile.ov_client import InProcessVikingClient
from openviking.compile.pipeline_agent import ScratchFileTool
from openviking.compile.scratch import ScratchDir
from openviking.service.compile_service import _validate_changes
from openviking.service.external_task_service import ExternalTaskSnapshot
from openviking.service.task_tracker import TaskStatus
from tests.compile.test_compile_restart import _wait_for
from tests.compile.test_compile_service import (
    CTX,
    OWNER,
    _compile_service,
    _direct_service,
    _Provider,
    _request,
    _submit,
    durable,  # noqa: F401 - pytest fixture
    tracker,  # noqa: F401 - pytest fixture
)

SNAPSHOT = "a" * 40
CHANGES = {
    "base": "b" * 40,
    "head": "c" * 40,
    "diff_dirs": ["viking://resources/raw"],
    "full_dirs": [],
    "execution": {"mode": "incremental"},
    "skill_snapshot": {"uri": "viking://agent/skills/llm-wiki", "snapshot_id": SNAPSHOT},
}


def _lifecycle(**overrides):
    async def prepare(payload, ctx, *, instruction_set, scheduled_target_id=None):
        task_payload = {k: v for k, v in payload.items() if k != "args"}
        runtime = {k: v for k, v in (payload.get("args") or {}).items() if k != "mode"}
        if runtime:
            task_payload["args"] = runtime
        task_payload["compile"] = {"target_id": "t1", "trigger": "manual"}
        return task_payload

    hooks = {
        "prepare": AsyncMock(side_effect=prepare),
        "record_created": AsyncMock(),
        "record_queued": AsyncMock(),
        "runtime_changes": AsyncMock(return_value=None),
    }
    return SimpleNamespace(**{**hooks, **overrides})


@pytest.mark.asyncio
async def test_create_registers_target_and_keeps_submission_hash_input(tmp_path):
    service, tasks = _compile_service(tmp_path)
    tasks.recover_submission.return_value = None  # First submission for this key.
    lifecycle = _lifecycle()
    service.configure_lifecycle(lifecycle)

    await service.create(
        _request(args={"mode": "full", "wiki_links": True}, instruction="refresh"),
        ctx=CTX,
        idempotency_key="key-0123456789abcdef",
    )

    assert lifecycle.prepare.await_args.kwargs["instruction_set"] is True
    kwargs = tasks.create.await_args.kwargs
    assert kwargs["payload"]["compile"]["target_id"] == "t1"
    assert kwargs["payload"]["args"] == {"wiki_links": True}
    # Idempotent retries compare the caller's request, not the registry metadata.
    assert "compile" not in kwargs["submission_payload"]
    assert kwargs["submission_payload"]["args"] == {"mode": "full", "wiki_links": True}
    lifecycle.record_queued.assert_awaited_once()
    lifecycle.record_created.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_rejects_invalid_control_args(tmp_path):
    service, tasks = _compile_service(tmp_path)
    service.configure_lifecycle(_lifecycle())
    from openviking_cli.exceptions import InvalidArgumentError

    with pytest.raises(InvalidArgumentError, match="args.mode"):
        await service.create(_request(args={"mode": "sometimes"}), ctx=CTX)
    tasks.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_passes_change_plan_and_pins_skill_snapshot(tmp_path):
    service, _ = _compile_service(tmp_path)
    service.configure_lifecycle(_lifecycle(runtime_changes=AsyncMock(return_value=CHANGES)))
    service._vlm_resolver = SimpleNamespace(get_vlm=AsyncMock(return_value=SimpleNamespace()))
    captured = {}

    async def run(task_id, request, *, client, **kwargs):
        captured.update(request=request, client=client)
        return {"ok": True}

    service._runner = SimpleNamespace(run=run)
    payload = {
        "from": ["viking://resources/raw"],
        "to": "viking://resources/wiki",
        "skill": "viking://agent/skills/llm-wiki",
        "args": {"last_compile_time": 1700000000},
        "compile": {"target_id": "t1"},
    }
    task = SimpleNamespace(task_id="cmp_1")

    result = await service.run(task, payload, CTX, progress=AsyncMock(), cancelled=AsyncMock())

    assert result == {"ok": True}
    request = captured["request"]
    assert request.changes["head"] == CHANGES["head"]
    assert request.last_compile_time is None  # The change plan supersedes the cutoff.
    client = captured["client"]
    assert client._snapshot_ref("viking://agent/skills/llm-wiki/SKILL.md") == SNAPSHOT
    assert client._snapshot_ref("viking://resources/raw/a.md") is None
    assert client._edit_source == "compile"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({**CHANGES, "full_dirs": ["viking://resources/raw"]}, "partition"),
        ({**CHANGES, "diff_dirs": [], "full_dirs": ["viking://resources/other"]}, "partition"),
        ({**CHANGES, "execution": {"mode": "full"}}, "base/head"),
        (
            {**CHANGES, "diff_dirs": [], "full_dirs": ["viking://resources/raw"], "head": None},
            "full",
        ),
        ({**CHANGES, "execution": None}, "Invalid"),
    ],
)
def test_invalid_change_plans_fail_before_model_calls(changes, message):
    with pytest.raises(CompileFailure, match=message):
        _validate_changes(changes, ["viking://resources/raw"], "viking://agent/skills/llm-wiki")


def test_skill_snapshot_must_match_requested_skill():
    with pytest.raises(CompileFailure, match="Skill snapshot"):
        _validate_changes(CHANGES, ["viking://resources/raw"], "viking://agent/skills/other")


@pytest.mark.asyncio
async def test_on_start_busy_rotates_until_target_is_free(monkeypatch, tracker):  # noqa: F811
    run = AsyncMock(return_value={"done": True})
    service = _direct_service(monkeypatch, tracker, run)
    provider = service._providers["compile"]
    states = iter(["busy", "proceed"])
    provider.on_start = AsyncMock(side_effect=lambda task: next(states))
    task = await _submit(service)

    # Another instance owns the target: rotate without running or keeping the claim.
    assert not await service.execute(task.task_id, "acme", "alice")
    run.assert_not_awaited()
    assert not service._owners and not service._executing

    assert await service.execute(task.task_id, "acme", "alice")
    run.assert_awaited_once()
    assert (await tracker.get(task.task_id, **OWNER)).status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_on_start_snapshot_settles_without_running(durable):  # noqa: F811
    run = AsyncMock()
    provider = _Provider(run)

    async def on_start(task):
        return ExternalTaskSnapshot(status="completed", result={"replayed": True})

    provider.on_start = on_start
    task = await _submit(durable.start(provider))

    async def completed():
        current = await durable.tracker.get(task.task_id, **OWNER)
        return current.status == TaskStatus.COMPLETED

    await _wait_for(completed)
    assert (await durable.tracker.get(task.task_id, **OWNER)).result == {"replayed": True}
    run.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_finish_replaces_recorded_outcome(durable):  # noqa: F811
    async def run(task, payload, ctx, *, progress, cancelled):
        return {"files": 1}

    provider = _Provider(run)
    seen = []

    async def on_finish(task, snapshot):
        seen.append(snapshot.status)
        return ExternalTaskSnapshot(status="failed", error_code="ROLLED_BACK", error_message="x")

    provider.on_finish = on_finish
    task = await _submit(durable.start(provider))

    async def failed():
        current = await durable.tracker.get(task.task_id, **OWNER)
        return current.status == TaskStatus.FAILED

    await _wait_for(failed)
    assert seen == ["completed"]
    assert (await durable.tracker.get(task.task_id, **OWNER)).error == "ROLLED_BACK: x"


@pytest.mark.asyncio
async def test_final_review_tools_browse_task_but_write_only_artifacts(tmp_path):
    scratch = ScratchDir(tmp_path / "task")
    scratch.reset()
    await scratch.write_file("pipeline/notes.md", "keep")
    write = ScratchFileTool("write_file", scratch, "pipeline", "artifacts/run")
    listing = ScratchFileTool("list_dir", scratch, "pipeline", "artifacts/run")

    assert await write.execute(path="artifacts/run/page.md", content="ok") == (
        "Wrote artifacts/run/page.md."
    )
    with pytest.raises(ValueError, match="Write only inside artifacts/run/"):
        await write.execute(path="notes.md", content="overwrite")
    assert await listing.execute(path=".") == "artifacts/\nnotes.md"


@pytest.mark.asyncio
async def test_snapshot_reads_come_from_pinned_commit():
    fs = SimpleNamespace(
        show_blob_raw=AsyncMock(return_value={"bytes": b"line1\nline2\n"}),
        read=AsyncMock(return_value="live"),
    )
    client = InProcessVikingClient(
        SimpleNamespace(fs=fs),
        CTX,
        skill_snapshot={"uri": "viking://agent/skills/llm-wiki", "snapshot_id": SNAPSHOT},
    )

    assert await client.read_raw("viking://agent/skills/llm-wiki/SKILL.md", offset=1) == "line2\n"
    fs.show_blob_raw.assert_awaited_once_with(
        SNAPSHOT, path="viking://agent/skills/llm-wiki/SKILL.md", ctx=CTX
    )
    assert await client.read_raw("viking://agent/skills/llm-wiki-other/SKILL.md") == "live"


def test_snapshot_id_must_be_a_commit():
    with pytest.raises(ValueError, match="commit ID"):
        InProcessVikingClient(
            SimpleNamespace(), CTX, skill_snapshot={"uri": "viking://x", "snapshot_id": "main"}
        )
