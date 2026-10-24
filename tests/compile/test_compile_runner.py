"""CompileRunner attempt lifecycle around a stubbed pipeline."""

import asyncio
from datetime import datetime, timezone
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
    )
    return attempt, progress


@pytest.mark.asyncio
async def test_attempt_publishes_and_removes_scratch(tmp_path, stub_pipeline):
    client = _Client()
    stale = tmp_path / "cmp_test" / "left-from-crash.json"
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
    assert not (tmp_path / "cmp_test").exists()


@pytest.mark.asyncio
async def test_cancellation_stops_before_any_write(tmp_path, stub_pipeline):
    client = _Client()
    attempt, _ = _run(tmp_path, client, _request(), cancelled=True)
    with pytest.raises(asyncio.CancelledError):
        await attempt
    client.batch_write.assert_not_awaited()
    assert (tmp_path / "cmp_test").exists()


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
    assert (tmp_path / "cmp_test").exists()


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
    old, recent, current = (tmp_path / name for name in ("cmp_old", "cmp_recent", "cmp_now"))
    for path in (old, recent, current):
        path.mkdir()
    stale = time.time() - runner_module.SCRATCH_RETENTION_SECONDS - 60
    os.utime(old, (stale, stale))
    os.utime(current, (stale, stale))
    runner.prune_scratch(keep="cmp_now")
    assert not old.exists()
    assert recent.exists() and current.exists()
