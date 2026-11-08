"""Image evidence in in-server Compile: loading, batching, evidence reads and transport."""

import asyncio
import base64
from collections import Counter
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from openviking.compile import media
from openviking.compile.agent_loop import agent_runner
from openviking.compile.llm import ChatResponse, CompileProvider, ToolCallRequest
from openviking.compile.models import CompileFailure, CompileLimits
from openviking.compile.pipeline_io import JsonModel, TaskFiles
from openviking.compile.plan import ReviewDecision
from openviking.compile.scratch import ScratchDir
from openviking.compile.skill_resources import EvidenceReader
from openviking.compile.sources import CompileSourceRange, pack_source_batches, read_source
from openviking.models.vlm.base import VLMResponse

PNG = b"\x89PNG\r\n\x1a\n" + b"pixels"
URI = "viking://resources/raw/diagram.png"


def image_client(data: bytes, *, size: int | None = None):
    return SimpleNamespace(
        stat=AsyncMock(return_value={"uri": URI, "size": len(data) if size is None else size}),
        download_bytes=AsyncMock(return_value=data),
        read_raw=AsyncMock(side_effect=AssertionError("images must not be read as text")),
    )


def image_part(data: bytes = PNG) -> dict:
    encoded = base64.b64encode(data).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}}


async def test_image_source_becomes_one_evidence_range_with_its_bytes():
    source = await read_source(image_client(PNG), URI)

    assert isinstance(source, CompileSourceRange)
    assert source.uri == URI and source.content == ""
    assert source.image == image_part()
    assert len(source.sha256) == 64


@pytest.mark.parametrize(
    "uri,client,code",
    [
        ("viking://resources/raw/scan.bmp", image_client(b"BM..."), "INVALID_ARGUMENT"),
        (URI, image_client(b"not an image"), "SOURCE_READ_FAILED"),
        (URI, image_client(PNG, size=media.MAX_INLINE_MEDIA_BYTES + 1), "SOURCE_READ_FAILED"),
    ],
    ids=["unsupported-format", "wrong-bytes", "oversized"],
)
async def test_unusable_images_fail_their_source(uri, client, code):
    with pytest.raises(CompileFailure) as raised:
        await read_source(client, uri)
    assert raised.value.code == code


async def test_text_sources_are_still_read_as_text():
    client = SimpleNamespace(read_raw=AsyncMock(return_value="# Notes\n"))
    assert await read_source(client, "viking://resources/raw/notes.md") == "# Notes\n"


def test_source_batches_hold_at_most_four_images():
    images = [
        (
            f"viking://resources/raw/{i}.png",
            CompileSourceRange(
                f"viking://resources/raw/{i}.png",
                0,
                0,
                0,
                0,
                "",
                image=image_part(),
                sha256="0" * 64,
            ),
        )
        for i in range(media.MAX_INLINE_IMAGES + 1)
    ]

    batches = pack_source_batches(images, CompileLimits())

    assert [len(batch) for batch in batches] == [media.MAX_INLINE_IMAGES, 1]


async def evidence_files(tmp_path):
    files = TaskFiles(ScratchDir(tmp_path / "scratch"))
    await files.put("sources/img-1", {"uri": URI, "media_kind": "image", "image": image_part()})
    return files


async def test_image_evidence_reaches_the_model_as_an_image_part(tmp_path):
    files = await evidence_files(tmp_path)
    reader = EvidenceReader(
        files, {"inputs": [{"id": "img-1", "payload": {"source_ranges": ["img-1"]}}]}
    )

    result = await reader.execute(source_range="img-1")

    assert isinstance(result, media.MultimodalToolResult)
    assert result.content[1] == image_part()
    assert "base64" not in result.text
    with pytest.raises(ValueError, match="no text line ranges"):
        await reader.execute(source_range="img-1", start_line=1, end_line=1)


async def test_agent_loop_sends_image_tool_results_to_the_model(tmp_path):
    files = await evidence_files(tmp_path)
    seen = []

    async def model_call(stage, messages, tools, *, max_tokens):
        seen.append([dict(m) for m in messages])
        if len(seen) == 1:
            return ChatResponse(
                None,
                [ToolCallRequest("read", "read_evidence", {"source_range": "img-1"})],
                "tool_calls",
            )
        return ChatResponse(
            None,
            [ToolCallRequest("emit", "emit", {"action": "continue"})],
            "tool_calls",
        )

    model = SimpleNamespace(
        files=files,
        fits=lambda *args: True,
        resources=None,
        metrics=Counter(),
        max_tokens=1000,
        call=model_call,
    )
    data = {"inputs": [{"id": "img-1", "payload": {"source_ranges": ["img-1"]}}]}

    result = await agent_runner(CompileLimits())("system", data, ReviewDecision, None, model)

    assert result.action == "continue"
    tool_message = seen[1][-1]
    assert tool_message["role"] == "tool"
    assert tool_message["content"][1] == image_part()


async def test_requests_over_the_inline_media_budget_are_rejected():
    big = image_part(b"x" * (media.MAX_INLINE_MEDIA_BYTES + 3))
    messages = [{"role": "tool", "tool_call_id": "read", "content": [big]}]

    with pytest.raises(CompileFailure) as raised:
        await JsonModel.call(SimpleNamespace(), "map", messages, [], max_tokens=1)
    assert raised.value.code == "MEDIA_LIMIT"


@pytest.mark.parametrize("mode", ["native", "user_message", None])
async def test_provider_adapts_tool_images_to_the_vlm_transport(mode):
    vlm = SimpleNamespace(
        model="vision-model",
        thinking=None,
        tool_result_media_mode=lambda: mode,
        get_completion_async=AsyncMock(return_value=VLMResponse(content="ok")),
    )
    messages = [
        {"role": "user", "content": "inspect"},
        {
            "role": "tool",
            "tool_call_id": "read",
            "content": [{"type": "text", "text": "{}"}, image_part()],
        },
    ]

    await CompileProvider(vlm, asyncio.Semaphore(1)).chat(messages=messages)

    sent = vlm.get_completion_async.await_args.kwargs["messages"]
    if mode == "native":
        assert sent == messages
    else:
        # Models without native tool-result media receive the image as a user message.
        assert [m["role"] for m in sent] == ["user", "tool", "user"]
        assert sent[-1]["content"][-1] == image_part()
        assert not any(
            isinstance(part, dict) and part.get("type") == "image_url"
            for part in sent[1]["content"]
            if isinstance(sent[1]["content"], list)
        )


@pytest.mark.parametrize("with_image", [True, False])
async def test_rejected_image_requests_name_the_likely_cause(with_image):
    from openviking.models.model_error import ModelError, ModelErrorKind

    vlm = SimpleNamespace(
        model="text-only-model",
        thinking=None,
        tool_result_media_mode=lambda: "native",
        get_completion_async=AsyncMock(
            side_effect=ModelError(ModelErrorKind.INVALID_REQUEST, "image_url is not supported")
        ),
    )
    content = [{"type": "text", "text": "{}"}, *([image_part()] if with_image else [])]
    messages = [{"role": "tool", "tool_call_id": "read", "content": content}]

    response = await CompileProvider(vlm, asyncio.Semaphore(1)).chat(messages=messages)

    assert response.finish_reason == "error"
    assert response.error_kind == ModelErrorKind.INVALID_REQUEST
    assert ("vision-capable vlm model" in response.content) is with_image
