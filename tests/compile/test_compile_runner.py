"""CompileRunner attempt lifecycle around a stubbed pipeline."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from openviking.compile import runner as runner_module
from openviking.compile.models import CompileFailure, CompileLimits, SanitizedCompileRequest
from openviking.compile.pipeline_io import TaskFiles
from openviking.compile.renderer import RenderedBundle
from openviking.service.external_task_service import TaskCompletedDuringCancel

PAGE = "viking://resources/wiki/topic.md"


class _Client:
    def __init__(self):
        self.batch_write = AsyncMock(
            return_value={"created": [PAGE], "updated": [], "unchanged": [], "conflicts": []}
        )

    async def stat(self, uri):
        return {"isDir": not uri.endswith(".md")}

    async def list_resources(self, uri, node_limit, offset=0):
        page = [{"uri": "viking://resources/raw/a.md", "isDir": False, "modTime": "2026-01-01"}]
        return page[offset : offset + node_limit]

    async def read_raw(self, uri, offset=0, limit=-1):
        return "# Skill" if uri.endswith("SKILL.md") else "source text"


def _request(**overrides):
    return SanitizedCompileRequest(
        **{
            "from": ["viking://resources/raw"],
            "to": "viking://resources/wiki",
            "instruction": "Compile.",
            "skill": "viking://agent/skills/llm-wiki",
            **overrides,
        }
    )


@pytest.fixture
def stub_pipeline(monkeypatch):
    """Replace the LLM pipeline with one that renders a single page."""
    bundle = RenderedBundle(
        operations=[{"uri": PAGE, "content": "# Topic", "mode": "create"}],
        created=[PAGE],
        wiki_uris=[PAGE],
    )
    state = SimpleNamespace(bundle=bundle, seen_batches=[])

    class Pipeline:
        def __init__(self, *, sandbox, **kwargs):
            self.files = TaskFiles(sandbox)
            self.model = SimpleNamespace(agent_runner=None)
            self.failures, self.warnings, self.artifacts = [], [], []
            self.noop = False

        async def run(self, batches):
            async for batch in batches:
                state.seen_batches.append(batch)
            await self.files.put("summary", {})
            return state.bundle

        async def write_coverage(self, published):
            state.published = list(published)

    monkeypatch.setattr(runner_module, "Pipeline", Pipeline)
    return state


def _run(tmp_path, client, request, *, cancelled=False):
    runner = runner_module.CompileRunner(limits=CompileLimits(), work_root=tmp_path)
    progress = AsyncMock()
    provider = SimpleNamespace(model="m", temperature=0.0)
    attempt = runner.run(
        "cmp_test",
        request,
        client=client,
        provider=provider,
        progress=progress,
        cancelled=AsyncMock(return_value=cancelled),
        owner=("acme", "alice"),
    )
    return attempt, progress


@pytest.mark.asyncio
async def test_attempt_publishes_and_removes_scratch(tmp_path, stub_pipeline):
    client = _Client()
    stale = tmp_path / "acme" / "alice" / "cmp_test" / "left-from-crash.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}")
    attempt, progress = _run(tmp_path, client, _request())
    result = await attempt
    assert result["created"] == [PAGE]
    assert result["page_count"] == 1
    assert client.batch_write.await_args.kwargs["skip_conflicts"] is True
    assert [call.args[0] for call in progress.await_args_list][:2] == [
        "collecting_context",
        "pipeline",
    ]
    assert stub_pipeline.seen_batches
    # A previous interrupted attempt is discarded and success cleans up.
    assert not (tmp_path / "acme" / "alice" / "cmp_test").exists()


@pytest.mark.asyncio
async def test_cancellation_stops_before_any_write(tmp_path, stub_pipeline):
    client = _Client()
    attempt, _ = _run(tmp_path, client, _request(), cancelled=True)
    with pytest.raises(asyncio.CancelledError):
        await attempt
    client.batch_write.assert_not_awaited()
    assert (tmp_path / "acme" / "alice" / "cmp_test").exists()


@pytest.mark.asyncio
async def test_incremental_compile_without_new_sources_is_noop(tmp_path, stub_pipeline):
    client = _Client()
    cutoff = datetime(2026, 6, 1, tzinfo=timezone.utc)
    attempt, _ = _run(tmp_path, client, _request(last_compile_time=cutoff))
    result = await attempt
    assert result["created"] == [] and result["to"] == "viking://resources/wiki"
    assert not stub_pipeline.seen_batches
    client.batch_write.assert_not_awaited()


@pytest.mark.asyncio
async def test_nothing_published_fails_with_model_hint(tmp_path, stub_pipeline):
    stub_pipeline.bundle = RenderedBundle()
    attempt, _ = _run(tmp_path, _Client(), _request())
    with pytest.raises(CompileFailure) as raised:
        await attempt
    assert raised.value.code == "COMPILE_INCOMPLETE"
    assert "more capable" in str(raised.value)
    # Failed attempts keep their scratch files for diagnosis.
    assert (tmp_path / "acme" / "alice" / "cmp_test").exists()


@pytest.mark.asyncio
async def test_publish_runs_outside_task_context_and_survives_cancel(tmp_path, stub_pipeline):
    from openviking.service.task_work_index import bind_task_context, get_task_context

    client = _Client()
    writing = asyncio.Event()
    release = asyncio.Event()
    seen = {}

    async def batch_write(**kwargs):
        seen["context"] = get_task_context()
        writing.set()
        await release.wait()
        seen["finished"] = True
        return {"created": [PAGE], "updated": [], "unchanged": [], "conflicts": []}

    client.batch_write = batch_write
    with bind_task_context("cmp_test", "acme", "alice"):
        attempt, _ = _run(tmp_path, client, _request())
        task = asyncio.create_task(attempt)
    await writing.wait()
    task.cancel()
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(TaskCompletedDuringCancel) as raised:
        await task
    # The write completed before cancellation took effect, outside the Compile task,
    # and its result travels with the cancellation.
    assert seen == {"context": None, "finished": True}
    assert raised.value.result["created"] == [PAGE]


def test_prune_scratch_removes_only_old_other_tasks(tmp_path):
    import os
    import time

    runner = runner_module.CompileRunner(limits=CompileLimits(), work_root=tmp_path)
    old = runner.scratch("cmp_old", ("acme", "bob")).root
    recent = runner.scratch("cmp_recent", ("acme", "alice")).root
    current = runner.scratch("cmp_now", ("acme", "alice")).root
    for path in (old, recent, current):
        path.mkdir(parents=True)
    stale = time.time() - runner_module.SCRATCH_RETENTION_SECONDS - 60
    os.utime(old, (stale, stale))
    os.utime(current, (stale, stale))
    runner.prune_scratch(keep=current)
    assert not old.exists()
    assert recent.exists() and current.exists()


def test_purge_owner_removes_user_or_account_scratch(tmp_path):
    runner = runner_module.CompileRunner(limits=CompileLimits(), work_root=tmp_path)
    alice = runner.scratch("cmp_a", ("acme", "alice")).root
    bob = runner.scratch("cmp_b", ("acme", "bob")).root
    other = runner.scratch("cmp_c", ("other", "alice")).root
    for path in (alice, bob, other):
        path.mkdir(parents=True)
    runner.purge_owner("acme", "alice")
    assert not alice.exists() and bob.exists()
    runner.purge_owner("acme")
    assert not bob.exists() and other.exists()


@pytest.mark.asyncio
async def test_nothing_published_keeps_conflicts_on_failure(tmp_path, stub_pipeline):
    client = _Client()
    conflict = {"uri": PAGE, "code": "CONFLICT", "message": "changed"}
    client.batch_write = AsyncMock(
        return_value={"created": [], "updated": [], "unchanged": [], "conflicts": [conflict]}
    )
    attempt, _ = _run(tmp_path, client, _request())
    with pytest.raises(CompileFailure) as raised:
        await attempt
    assert raised.value.code == "COMPILE_INCOMPLETE"
    assert raised.value.result["conflicts"] == [conflict]


class _SkillClient:
    """In-memory Skill namespace for Skill-target publishing."""

    def __init__(self, existing=None):
        self.existing = existing
        self.published = None

    async def stat(self, uri):
        from openviking_cli.exceptions import NotFoundError

        if self.existing is None:
            raise NotFoundError(uri, "skill")
        return {"isDir": True}

    async def get_skill(self, name, *, target_uri):
        return {"content": self.existing, "files": []}

    async def _capture(self, path):
        root = Path(path)
        self.published = {
            str(f.relative_to(root)): f.read_text() for f in root.rglob("*") if f.is_file()
        }

    async def add_skill(self, path, *, target_uri, wait):
        await self._capture(path)
        return {"root_uri": f"{target_uri}/demo"}

    async def update_skill(self, name, path, *, target_uri, wait):
        await self._capture(path)
        return {"root_uri": f"{target_uri}/demo"}


SKILL_MD = "---\nname: demo\ndescription: Demo skill for tests.\n---\n# Demo\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [None, "old"])
async def test_skill_target_publishes_one_validated_package(tmp_path, existing):
    from openviking.compile.hashing import content_hash

    target = "viking://agent/skills"
    operation = {"uri": f"{target}/demo/SKILL.md", "content": SKILL_MD, "mode": "create"}
    if existing is not None:
        operation.update(mode="replace", expected_sha256=content_hash(existing.encode()))
    client = _SkillClient(existing)
    runner = runner_module.CompileRunner(limits=CompileLimits(), work_root=tmp_path)
    result = await runner._write_skill_bundle(
        client=client, target_uri=target, rendered=RenderedBundle(operations=[operation])
    )
    assert result["updated" if existing else "created"] == [f"{target}/demo"]
    assert client.published == {"SKILL.md": SKILL_MD}


@pytest.mark.asyncio
async def test_skill_target_rejects_create_over_existing_file(tmp_path):
    # Upstream dropped per-file revision hashes; creating an existing file still conflicts.
    target = "viking://agent/skills"
    operation = {
        "uri": f"{target}/demo/SKILL.md",
        "content": SKILL_MD,
        "mode": "create",
    }
    client = _SkillClient("someone else's edit")
    runner = runner_module.CompileRunner(limits=CompileLimits(), work_root=tmp_path)
    with pytest.raises(CompileFailure) as raised:
        await runner._write_skill_bundle(
            client=client, target_uri=target, rendered=RenderedBundle(operations=[operation])
        )
    assert raised.value.code == "WRITE_CONFLICT"
    assert client.published is None


@pytest.mark.asyncio
async def test_missing_target_directory_is_created(tmp_path, stub_pipeline):
    from openviking_cli.exceptions import NotFoundError

    client = _Client()
    target = "viking://resources/wiki"
    created = []
    original_stat = client.stat

    async def stat(uri):
        if uri == target and not created:
            raise NotFoundError(uri, "file")
        return await original_stat(uri)

    async def mkdir(uri, *, description=None):
        created.append((uri, description))

    client.stat, client.mkdir = stat, mkdir
    attempt, _ = _run(tmp_path, client, _request())
    result = await attempt
    assert created == [(target, "compile target folder")]
    assert result["created"] == [PAGE]


@pytest.mark.asyncio
async def test_target_that_is_a_file_fails(tmp_path, stub_pipeline):
    client = _Client()

    async def stat(uri):
        return {"isDir": False}

    client.stat = stat
    attempt, _ = _run(tmp_path, client, _request())
    with pytest.raises(CompileFailure) as raised:
        await attempt
    assert raised.value.code == "INVALID_ARGUMENT"
