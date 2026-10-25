"""In-process agent transforms: scratch confinement, child loop and VLM shim."""

import asyncio
from collections import Counter
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from openviking.compile.llm import ChatResponse, CompileProvider, ToolCallRequest
from openviking.compile.models import CompileLimits
from openviking.compile.pipeline_agent import ScratchFileTool, agent_runner
from openviking.compile.pipeline_io import TaskFiles
from openviking.compile.plan import ReviewDecision
from openviking.compile.scratch import ScratchDir
from openviking.models.vlm.base import ToolCall, VLMResponse


def call(name, arguments, finish_reason="tool_calls"):
    return ChatResponse(None, [ToolCallRequest(f"id-{name}", name, arguments)], finish_reason)


def child_model(tmp_path, responses):
    files = TaskFiles(ScratchDir(tmp_path / "scratch"))
    return SimpleNamespace(
        files=files,
        fits=lambda *args: True,
        resources=None,
        metrics=Counter(),
        max_tokens=1000,
        call=AsyncMock(side_effect=responses),
    )


@pytest.mark.parametrize("path", ["../escape.txt", "a/../../escape.txt", "/etc/passwd"])
def test_scratch_rejects_paths_outside_root(tmp_path, path):
    scratch = ScratchDir(tmp_path / "scratch")
    with pytest.raises(ValueError):
        scratch.local_file_path(path)


async def test_scratch_round_trip_and_reset(tmp_path):
    scratch = ScratchDir(tmp_path / "scratch")
    await scratch.write_file("a/b.txt", "hello")
    assert await scratch.read_file_bytes("a/b.txt") == b"hello"
    scratch.reset()
    with pytest.raises(FileNotFoundError):
        await scratch.read_file_bytes("a/b.txt")


async def test_scratch_tools_confine_and_edit(tmp_path):
    scratch = ScratchDir(tmp_path / "scratch")
    write = ScratchFileTool("write_file", scratch, "drafts/x")
    edit = ScratchFileTool("edit_file", scratch, "drafts/x")
    read = ScratchFileTool("read_file", scratch, "drafts/x")
    await write.execute(path="page.md", content="one\ntwo\nthree\n")
    await edit.execute(path="page.md", old_text="two", new_text="TWO")
    assert (
        await read.execute(path="page.md", offset=1, limit=1)
        == "TWO\n\n[1 more lines; continue with offset=2]"
    )
    with pytest.raises(ValueError, match="exactly once"):
        await edit.execute(path="page.md", old_text="missing", new_text="x")
    with pytest.raises(ValueError):
        await read.execute(path="viking://resources/secret.md")
    with pytest.raises(ValueError):
        await read.execute(path="../../outside.md")


async def test_child_writes_result_file_then_emits_reference(tmp_path):
    model = child_model(
        tmp_path,
        [
            call("write_file", {"path": "result.json", "content": '{"action": "continue"}'}),
            call("emit", {"result_ref": "result.json"}),
        ],
    )
    run = agent_runner(CompileLimits())
    result = await run("system", {}, ReviewDecision, None, model, stage="reduce_agent")
    assert result.action == "continue"
    assert model.call.await_count == 2
    # Tool results are fed back with the matching call id.
    messages = model.call.await_args.args[1]
    assert {
        "role": "tool",
        "tool_call_id": "id-write_file",
        "content": "Wrote result.json.",
    } in messages


async def test_child_retries_truncated_output_without_running_tools(tmp_path):
    model = child_model(
        tmp_path,
        [
            call("write_file", {"path": "x", "content": "partial"}, finish_reason="length"),
            call("emit", {"action": "continue"}),
        ],
    )
    result = await agent_runner(CompileLimits())("s", {}, ReviewDecision, None, model)
    assert result.action == "continue"
    assert model.metrics["repairs"] == 1
    with pytest.raises(FileNotFoundError):
        await model.files.sandbox.read_file_bytes("x")


async def test_child_stops_at_iteration_limit(tmp_path):
    model = child_model(tmp_path, [ChatResponse("thinking aloud")] * 3)
    run = agent_runner(CompileLimits(subagent_iterations=3))
    with pytest.raises(ValueError, match="without validated output"):
        await run("s", {}, ReviewDecision, None, model)
    assert model.call.await_count == 3


class _FakeVLM:
    model = "m"
    temperature = 0.0
    thinking = False

    def __init__(self, result):
        self.result = result
        self.kwargs = None

    async def get_completion_async(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


async def test_provider_converts_tool_calls_and_usage():
    vlm = _FakeVLM(
        VLMResponse(
            content=None,
            tool_calls=[ToolCall("1", "emit", {"a": 1})],
            finish_reason="tool_calls",
            usage={
                "prompt_tokens": 5,
                "completion_tokens": 2,
                "prompt_tokens_details": {"cached_tokens": 3},
            },
        )
    )
    provider = CompileProvider(vlm, asyncio.Semaphore(1))
    tools = [{"type": "function", "function": {"name": "emit"}}]
    response = await provider.chat(messages=[], tools=tools, max_tokens=9, thinking=None)
    assert response.tool_calls == [ToolCallRequest("1", "emit", {"a": 1})]
    assert response.usage["cache_read_input_tokens"] == 3
    assert vlm.kwargs["tool_choice"] == "auto" and vlm.kwargs["max_tokens"] == 9
    assert vlm.kwargs["thinking"] is False


async def test_provider_reports_transport_errors():
    provider = CompileProvider(_FakeVLM(ConnectionError("down")), asyncio.Semaphore(1))
    response = await provider.chat(messages=[], tools=[])
    assert response.finish_reason == "error"
    assert "down" in response.content
