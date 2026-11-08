# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Names upstream's bot Compile imports from VikingBot, backed by in-server code.

``scripts/compile_upstream_sync.py`` rewrites imports from ``vikingbot.agent.loop``,
``vikingbot.agent.tools.base``, ``vikingbot.agent.tools.ov_file`` and
``vikingbot.utils.helpers`` to this module, so the shared pipeline files keep
upstream's spelling. Add a name here when upstream starts importing a new one.
"""

from __future__ import annotations

from typing import Any

from openviking.compile import media
from openviking.compile.media import MultimodalToolResult
from openviking.compile.tool import Tool
from openviking.utils.token_estimation import estimate_text_tokens

__all__ = [
    "MultimodalToolResult",
    "Tool",
    "VikingMultiReadTool",
    "_inline_media_bytes",
    "cal_str_tokens",
]


def _inline_media_bytes(messages: list[dict[str, Any]]) -> int:
    """Decoded bytes of inline images across message content parts."""
    return media.inline_media_bytes(messages)


def cal_str_tokens(text: str, text_type: str = "mixed") -> int:
    """Estimate prompt tokens; the server's CJK-aware estimator ignores ``text_type``."""
    return estimate_text_tokens(text)


class VikingMultiReadTool:
    """The image-reading helpers upstream's Compile calls on VikingBot's multi-read tool."""

    _MAX_INLINE_IMAGES = media.MAX_INLINE_IMAGES
    _MAX_INLINE_MEDIA_BYTES = media.MAX_INLINE_MEDIA_BYTES

    @staticmethod
    def _media_kind(uri: str) -> str | None:
        return "image" if media.is_inline_image(uri) else None

    @staticmethod
    async def _read_image(client: Any, uri: str) -> dict[str, Any]:
        return await media.read_image(client, uri)
