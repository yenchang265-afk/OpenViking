"""Core regressions for advisory Compile execution."""

import asyncio
from collections import Counter
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from openviking.compile import review
from openviking.compile.llm import ChatResponse, ToolCallRequest
from openviking.compile.models import CompileLimits
from openviking.compile.pipeline_io import JsonModel, ModelCallLimitError
from openviking.compile.plan import Contract, Node, ReviewDecision


@pytest.mark.parametrize("failure", ["model", "record", "cancel"])
async def test_review_failures_preserve_plan_and_cancellation(failure):
    contract = Contract(extract={"instructions": "Copy"})
    decision = ReviewDecision(
        action="revise", contract=contract, plan="p.finalize(mapped, into=target)"
    )

    async def ask(*args, **kwargs):
        args[4](decision)
        if failure != "record":
            error = asyncio.CancelledError() if failure == "cancel" else OSError("Review failed")
            raise error
        return decision

    runtime = SimpleNamespace(
        contract=contract,
        output_format="files",
        model=SimpleNamespace(ask=ask),
        files=SimpleNamespace(put=AsyncMock()),
        resources=SimpleNamespace(name="read_skill_resource"),
        failures=[],
        metrics=Counter(),
    )
    if failure == "record":
        runtime.files.put.side_effect = OSError("Record failed")
    args = (runtime, Node("mapped", "map", "sources", task="extract"), [], "", set(), 0, {})
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await review.run(*args, completed_ops=set())
    else:
        result = await review.run(*args, completed_ops=set())
        assert (result is not None) is (failure == "record")
    assert runtime.contract is contract


def response(name, arguments):
    """Return one scripted reader or final-result tool call."""
    return ChatResponse(None, [ToolCallRequest("call", name, arguments)])


@pytest.mark.parametrize("case", ["repeat", "progress", "error"])
async def test_control_reads_have_bounded_rounds_and_allow_progress(case):
    offsets = [n // 2 for n in range(102)] if case == "progress" else list(range(4))
    files = SimpleNamespace(put=AsyncMock())
    responses = [response("read", {"offset": n}) for n in offsets]
    responses.append(ChatResponse('{"action":"continue"}'))
    provider = SimpleNamespace(thinking=True, chat=AsyncMock(side_effect=responses))
    model = JsonModel(
        provider,
        "test",
        0,
        files,
        CompileLimits(subagent_iterations=110 if case == "progress" else 4),
        {},
        Counter(),
    )
    reader = SimpleNamespace(
        name="read", description="", parameters={}, execute=AsyncMock(return_value="x")
    )
    if case == "progress":
        reader.execute.side_effect = [f"chunk{n}" for n in offsets]
    if case == "error":
        reader.execute.side_effect = OSError("reader unavailable")
    result = model.ask("map", "", {}, ReviewDecision, readers={"read": reader})
    if case == "progress":
        assert (await result).action == "continue"
    else:
        with pytest.raises(ModelCallLimitError, match="round limit|reader unavailable"):
            await result
    assert provider.chat.await_count == (len(offsets) + 1 if case == "progress" else 4)
    assert provider.chat.await_args.kwargs["thinking"] is False
