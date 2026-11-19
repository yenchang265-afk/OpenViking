"""Core regressions for advisory Compile execution."""

import asyncio
from collections import Counter
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from openviking.compile import review
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
        output_format=contract.output_format,
        model=SimpleNamespace(ask=ask),
        files=SimpleNamespace(put=AsyncMock()),
        resources=SimpleNamespace(name="read_skill_resource"),
        failures=[],
        warnings=[],
        metrics=Counter(),
    )
    if failure == "record":
        runtime.files.put.side_effect = OSError("Record failed")
    args = (runtime, Node("mapped", "map", "sources", task="extract"), [], "", set(), 0, {})
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await review.run(*args, completed_ops=set())
    elif failure == "record":
        # A failed diagnostic write does not discard an accepted revision.
        accepted, nodes = await review.run(*args, completed_ops=set())
        assert accepted is decision and [n.op for n in nodes] == ["finalize"]
    else:
        assert await review.run(*args, completed_ops=set()) is None
    assert runtime.contract is contract
