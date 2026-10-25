"""Read-only OpenViking tools for direct Compile: snapshot changes, target reads and search.

They replace the bot's openviking_* tools with the same names and argument shapes,
backed by the task's in-process client. ``execute`` takes the (unused) tool context
first, as the pipeline's reader wrappers call it.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from openviking.compile.tool import Tool

# Reads per multi_read call run concurrently up to this bound.
_READ_CONCURRENCY = 8


class DiffPathsTool(Tool):
    name = "openviking_diff_paths"
    description = (
        "List added, modified and deleted file URIs under directories between snapshots. "
        "Omit base or pass null to list all files at head. Results include has_more and "
        "next_offset; query all pages to enumerate the complete change set. "
        "Read required file contents separately with openviking_multi_read."
    )
    parameters = {
        "type": "object",
        "properties": {
            "paths": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "minItems": 1,
                "description": "Source directory Viking URIs to compare.",
            },
            "base": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "description": "Base commit ID; omitted or null means an empty tree.",
            },
            "head": {"type": "string", "description": "Required target snapshot commit ID."},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
        },
        "required": ["paths", "head"],
    }

    def __init__(self, client: Any):
        self.client = client

    async def execute(
        self,
        _tool_context: Any = None,
        *,
        paths: list[str],
        head: str,
        base: str | None = None,
        offset: int = 0,
        limit: int = 100,
        **_: Any,
    ) -> str:
        result = await self.client.diff_paths(
            paths, base=base, head=head, offset=offset, limit=limit
        )
        return json.dumps(result, ensure_ascii=False)


class MultiReadTool(Tool):
    name = "openviking_multi_read"
    description = (
        "Read UTF-8 text files by Viking URI. offset/limit select zero-based lines "
        "(limit -1 reads to the end). with_revision returns each file's base_hash."
    )
    parameters = {
        "type": "object",
        "properties": {
            "uris": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "minItems": 1,
                "description": "File Viking URIs to read.",
            },
            "offset": {"type": "integer", "minimum": 0, "default": 0},
            "limit": {"type": "integer", "minimum": -1, "default": -1},
            "with_revision": {"type": "boolean", "default": False},
        },
        "required": ["uris"],
    }

    def __init__(self, client: Any):
        self.client = client

    async def execute(
        self,
        _tool_context: Any = None,
        *,
        uris: list[str],
        offset: int = 0,
        limit: int = -1,
        with_revision: bool = False,
        **_: Any,
    ) -> str:
        """Return one JSON result per URI; failures are reported per file, not raised."""
        if offset < 0 or (limit != -1 and limit < 1):
            raise ValueError("Reads require valid line ranges")
        semaphore = asyncio.Semaphore(_READ_CONCURRENCY)

        async def read(uri: str) -> dict[str, Any]:
            async with semaphore:
                try:
                    raw = await self.client.download_bytes(uri)
                    lines = raw.decode("utf-8").splitlines(keepends=True)
                except Exception as exc:
                    return {"uri": uri, "success": False, "error": str(exc)[:400]}
            item = {
                "uri": uri,
                "content": "".join(
                    lines[offset:] if limit == -1 else lines[offset : offset + limit]
                ),
                "success": True,
            }
            if with_revision:
                item["base_hash"] = hashlib.sha256(raw).hexdigest()
            return item

        results = await asyncio.gather(*(read(uri) for uri in uris))
        return json.dumps(results, ensure_ascii=False)


class SearchTool(Tool):
    name = "openviking_search"
    description = "Semantic search for related existing content in the compile target."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1},
            "limit": {
                "type": "integer",
                "description": "Maximum candidates; increase if needed.",
                "minimum": 1,
                "default": 10,
            },
        },
        "required": ["query"],
    }

    def __init__(self, client: Any):
        self.client = client

    async def execute(
        self,
        _tool_context: Any = None,
        *,
        query: str,
        target_uri: str,
        limit: int = 10,
        **_: Any,
    ) -> str:
        result = await self.client.find(query, target_uri=target_uri, limit=limit)
        if hasattr(result, "to_dict"):
            result = result.to_dict()
        return json.dumps(result, ensure_ascii=False, default=str)


def target_tools(client: Any) -> dict[str, Tool]:
    """Tools the direct Compile stage wraps with target and source scoping."""
    tools: list[Tool] = [SearchTool(client), MultiReadTool(client), DiffPathsTool(client)]
    return {tool.name: tool for tool in tools}
