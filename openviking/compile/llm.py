"""Compile's chat interface over the OpenViking VLM backend."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from openviking.models.model_error import ModelErrorKind, model_error_kind
from openviking_cli.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResponse:
    content: str | None = None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    error_kind: ModelErrorKind | None = None


def _usage_value(raw: Any, key: str) -> int:
    value = raw.get(key) if isinstance(raw, dict) else getattr(raw, key, None)
    return value if isinstance(value, int) else 0


def normalize_usage(raw: Any) -> dict[str, int]:
    """Return integer token counters, including cached and reasoning tokens when reported."""
    if not raw:
        return {}
    usage = {
        key: _usage_value(raw, key)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    prompt_details = (
        raw.get("prompt_tokens_details")
        if isinstance(raw, dict)
        else getattr(raw, "prompt_tokens_details", None)
    )
    completion_details = (
        raw.get("completion_tokens_details")
        if isinstance(raw, dict)
        else getattr(raw, "completion_tokens_details", None)
    )
    cached = _usage_value(prompt_details, "cached_tokens") if prompt_details else 0
    reasoning = _usage_value(completion_details, "reasoning_tokens") if completion_details else 0
    if cached:
        usage["cache_read_input_tokens"] = cached
    if reasoning:
        usage["reasoning_tokens"] = reasoning
    return usage


class CompileProvider:
    """Bound concurrent model calls for one server and convert VLM responses.

    Transport failures become ``finish_reason="error"`` with an ``error_kind`` so
    ``JsonModel.call`` applies its existing error classification.
    """

    def __init__(self, vlm: Any, semaphore: asyncio.Semaphore):
        self._vlm = vlm
        self._semaphore = semaphore

    @property
    def model(self) -> str | None:
        return getattr(self._vlm, "model", None)

    @property
    def temperature(self) -> float | None:
        return getattr(self._vlm, "temperature", None)

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        thinking: bool | None = None,
        **_: Any,
    ) -> ChatResponse:
        # Model and temperature come from the VLM configuration, as in the bot adapter.
        response_tools = tools or []
        try:
            async with self._semaphore:
                result = await self._vlm.get_completion_async(
                    messages=messages,
                    thinking=thinking
                    if thinking is not None
                    else getattr(self._vlm, "thinking", None),
                    tools=response_tools,
                    tool_choice="auto" if response_tools else None,
                    max_tokens=max_tokens,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[COMPILE] VLM call failed: %s", exc)
            return ChatResponse(
                content=f"Error calling VLM: {exc}",
                finish_reason="error",
                error_kind=model_error_kind(exc),
            )
        if isinstance(result, str):
            return ChatResponse(content=result)
        return ChatResponse(
            content=result.content,
            tool_calls=[
                ToolCallRequest(id=call.id, name=call.name, arguments=call.arguments)
                for call in result.tool_calls
            ],
            finish_reason=result.finish_reason,
            usage=normalize_usage(result.usage),
        )
