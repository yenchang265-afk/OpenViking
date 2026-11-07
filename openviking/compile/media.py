# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Image evidence for in-server Compile: loading, tool results and model transport.

Ports the checks upstream's bot runtime applies to Compile images (its multi-read
image loader, inline media budget and tool-result transport) without importing
the bot. Images reach the model as ``image_url`` data parts; models that cannot
take images inside tool results receive them as a following user message.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, NamedTuple

from openviking.utils.media_limits import MAX_INLINE_TOOL_RESULT_MEDIA_BYTES
from openviking.utils.message_format import tool_images_as_user_messages

# One read or source batch carries at most this many images.
MAX_INLINE_IMAGES = 4
# Total inline image bytes per model request (and per image).
MAX_INLINE_MEDIA_BYTES = MAX_INLINE_TOOL_RESULT_MEDIA_BYTES
INLINE_IMAGE_EXTENSIONS = frozenset({".gif", ".jpeg", ".jpg", ".png", ".webp"})
INLINE_IMAGE_MIME_TYPES = frozenset({"image/gif", "image/jpeg", "image/png", "image/webp"})
_IMAGE_PART_TYPES = frozenset({"image_url", "input_image"})


class ImageFormat(NamedTuple):
    extension: str
    mime_type: str


@dataclass
class MultimodalToolResult:
    """A tool result with model-facing content parts and a text-only representation."""

    text: str
    content: list[dict[str, Any]]

    def __str__(self) -> str:
        return self.text


def sniff_image_format(data: bytes) -> ImageFormat | None:
    """Detect an inline-capable image format from its magic bytes."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ImageFormat("png", "image/png")
    if data.startswith(b"\xff\xd8\xff"):
        return ImageFormat("jpg", "image/jpeg")
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ImageFormat("gif", "image/gif")
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ImageFormat("webp", "image/webp")
    return None


def is_inline_image(uri: str) -> bool:
    """Return whether the URI names an image format the model can receive inline."""
    path = uri.split("#", 1)[0].split("?", 1)[0]
    return PurePosixPath(path).suffix.lower() in INLINE_IMAGE_EXTENSIONS


async def read_image(client: Any, uri: str) -> dict[str, Any]:
    """Load one image as an ``image_url`` part, checking size and actual format.

    Returns ``{"success": False, "content": reason}`` instead of raising, so callers
    can fail one source without failing the task.
    """
    stat = await client.stat(uri)
    size = stat.get("size") if isinstance(stat, dict) else None
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        return {"success": False, "content": "Image size is unavailable; cannot attach it safely."}
    if size > MAX_INLINE_MEDIA_BYTES:
        return {
            "success": False,
            "content": f"Image is {size} bytes; the inline limit is {MAX_INLINE_MEDIA_BYTES} bytes.",
        }
    data = await client.download_bytes(uri)
    if len(data) > size:
        return {"success": False, "content": "Image changed after its size was checked; retry."}
    image_format = sniff_image_format(data)
    if image_format is None or image_format.mime_type not in INLINE_IMAGE_MIME_TYPES:
        return {
            "success": False,
            "content": "File bytes do not match a supported PNG, JPEG, GIF, or WebP image.",
        }
    encoded = base64.b64encode(data).decode("ascii")
    return {
        "success": True,
        "content": f"Image resource ({image_format.mime_type}, {len(data)} bytes).",
        "image": {
            "type": "image_url",
            "image_url": {"url": f"data:{image_format.mime_type};base64,{encoded}"},
        },
        "media_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _data_url_bytes(url: str) -> int:
    marker = ";base64,"
    index = url.find(marker) if url.startswith("data:") else -1
    if index < 0:
        return 0
    encoded = len(url) - index - len(marker)
    if encoded <= 0:
        return 0
    padding = 2 if url.endswith("==") else 1 if url.endswith("=") else 0
    return max(0, encoded * 3 // 4 - padding)


def inline_media_bytes(messages: list[dict[str, Any]]) -> int:
    """Count decoded bytes of inline images across message content parts."""
    total = 0
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict) or part.get("type") not in _IMAGE_PART_TYPES:
                continue
            image_url = part.get("image_url")
            url = image_url.get("url") if isinstance(image_url, dict) else image_url
            if isinstance(url, str):
                total += _data_url_bytes(url)
    return total


def tool_result_media_mode(vlm: Any) -> str:
    """``native`` when the VLM takes images inside tool results, else ``user_message``."""
    capability = getattr(vlm, "tool_result_media_mode", None)
    mode = capability() if callable(capability) else None
    return "native" if mode == "native" else "user_message"


def prepare_messages(vlm: Any, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Adapt tool-result images to what the VLM's transport accepts."""
    if tool_result_media_mode(vlm) == "user_message":
        return tool_images_as_user_messages(messages)
    return messages
