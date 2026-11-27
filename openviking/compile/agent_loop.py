"""Run focused pipeline workers: a bounded tool loop writing Markdown into a private directory.

Upstream runs workers through VikingBot's AgentLoop (``agent_runner`` in upstream's
pipeline_agent.py). In-server Compile runs them here with task-scratch file tools and
no command execution. The contract matches upstream: a worker writes deliverable
Markdown with file tools relative to the publication destination and finishes with a
natural completion message; only then is its private output directory returned.
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from collections.abc import Mapping
from typing import Any

from openviking.compile.media import MultimodalToolResult
from openviking.compile.models import COMPILE_DRAFT_ROOT, COMPILE_STAGING_ROOT
from openviking.compile.pipeline_agent import TargetReader
from openviking.compile.pipeline_io import retry_allowed
from openviking.compile.renderer import validate_relative_file_path
from openviking.compile.skill_resources import EvidenceReader
from openviking.compile.tool import Tool

# Lines returned by one read_file call when no limit is given.
READ_FILE_DEFAULT_LINES = 400
# Finish reasons of a completed model turn; anything else is a failed or cut-off reply.
_TOOL_FINISH = frozenset({"tool_calls", "tool_use", "function_call"})
_FINAL_FINISH = frozenset({"stop", "end_turn"})

_WORKER_INSTRUCTIONS = (
    "\nRead assignment.json with read_file. "
    "Read all assigned materials. assignment.json and assigned inputs/ paths "
    "are read-only. Use write_file and edit_file for deliverable Markdown, "
    "with paths relative to the publication destination. Read and edit your "
    "outputs using the same paths. Write only deliverables, without scratch files. "
    "Finish with a brief completion message after all writes succeed. "
    "A completion message alone does not produce files."
)


class ScratchFileTool(Tool):
    """read_file/write_file/edit_file bound to one worker's private output directory.

    Paths are relative to the publication destination and land under ``root``.
    ``readonly_paths`` maps assigned input aliases (assignment.json, inputs/N.md) to
    task-owned files that only read_file may open; other inputs/ paths are reserved.
    Viking URIs, absolute paths, traversal and staging directories are rejected.
    """

    _SCHEMAS = {
        "read_file": (
            "Read a UTF-8 file. offset/limit select zero-based lines.",
            {
                "path": {"type": "string"},
                "offset": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1},
            },
            ["path"],
        ),
        "write_file": (
            "Create or replace a UTF-8 file.",
            {"path": {"type": "string"}, "content": {"type": "string"}},
            ["path", "content"],
        ),
        "edit_file": (
            "Replace one exact occurrence of old_text with new_text in a file.",
            {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            ["path", "old_text", "new_text"],
        ),
    }

    def __init__(
        self,
        name: str,
        sandbox: Any,
        root: str,
        readonly_paths: Mapping[str, str] | None = None,
    ):
        description, properties, required = self._SCHEMAS[name]
        properties = {key: dict(value) for key, value in properties.items()}
        properties["path"]["description"] = (
            "Output path relative to the publication destination. Use the same path to "
            "write, read and edit an output. assignment.json and the assigned inputs/ "
            "paths are read-only inputs; other workspace paths are unavailable."
        )
        self.name, self.description = name, description
        self.parameters = {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }
        self.sandbox, self.root = sandbox, root
        self.readonly_paths = dict(readonly_paths or {})

    def _path(self, path: str) -> str:
        raw = str(path)
        if raw.startswith("viking://"):
            raise ValueError("File tools only access this worker's own outputs")
        relative = raw.strip()
        while relative.startswith("./"):
            relative = relative[2:]
        if relative in self.readonly_paths:
            if self.name != "read_file":
                raise ValueError(f"Assigned input is read-only: {relative}")
            return self.readonly_paths[relative]
        relative = validate_relative_file_path(relative)
        if relative == "inputs" or relative.startswith("inputs/"):
            raise ValueError(f"Input path is not assigned: {relative}")
        if COMPILE_STAGING_ROOT.casefold() in relative.casefold().split("/"):
            raise ValueError("Use paths relative to the destination, without staging directories")
        return f"{self.root}/{relative}"

    async def execute(self, tool_context: Any = None, **kwargs: Any) -> str:
        path = self._path(kwargs["path"])
        if self.name == "write_file":
            await self.sandbox.write_file(path, kwargs["content"])
            return f"Successfully wrote {kwargs['path']}"
        try:
            text = (await self.sandbox.read_file_bytes(path)).decode("utf-8")
        except FileNotFoundError as exc:
            raise ValueError(f"No such file: {kwargs['path']}") from exc
        if self.name == "read_file":
            lines = text.splitlines(keepends=True)
            offset = kwargs.get("offset", 0)
            end = offset + kwargs.get("limit", READ_FILE_DEFAULT_LINES)
            body = "".join(lines[offset:end])
            remaining = max(0, len(lines) - end)
            return body + (
                f"\n[{remaining} more lines; continue with offset={end}]" if remaining else ""
            )
        count = text.count(kwargs["old_text"])
        if count != 1:
            raise ValueError(f"old_text must occur exactly once; found {count}")
        await self.sandbox.write_file(path, text.replace(kwargs["old_text"], kwargs["new_text"]))
        return f"Successfully edited {kwargs['path']}"


class _ScopedSearch(Tool):
    """The target search tool, always scoped to this task's publication destination."""

    def __init__(self, search: Tool, target: str):
        self.search, self.target = search, target
        self.name, self.description = search.name, search.description
        self.parameters = search.parameters

    async def execute(self, tool_context: Any = None, **kwargs: Any) -> str:
        kwargs["target_uri"] = self.target
        return await self.search.execute(tool_context, **kwargs)


async def _write_assignment(sandbox: Any, root: str, data: Mapping[str, Any]):
    """Copy assigned documents to read-only inputs and write assignment.json."""
    assignment = dict(data)
    assignment["documents"] = []
    readonly_paths = {"assignment.json": f"{root}/assignment.json"}
    for index, document in enumerate(data.get("documents", [])):
        path = f"inputs/{index}.md"
        await sandbox.write_file(
            f"{root}/{path}", await sandbox.read_file_bytes(document["workspace_path"])
        )
        assignment["documents"].append({"path": document["path"], "content_file": path})
        readonly_paths[path] = f"{root}/{path}"
    await sandbox.write_file(f"{root}/assignment.json", json.dumps(assignment, ensure_ascii=False))
    return readonly_paths


def agent_runner(limits):
    """Bind isolated worker loops; queueing and cancellation remain owned by Pipeline.

    Each call has fresh history, a private directory and the subagent iteration limit.
    Every model request goes through the task's bounded, metered JsonModel.call.
    """

    async def run(system, data, model, *, stage, runtime):
        """Return the private output root only after natural completion; failures expose no files."""
        sandbox = model.files.sandbox
        root = f"{COMPILE_DRAFT_ROOT}/{uuid.uuid4().hex}"
        output_root = f"{root}/output"
        readonly_paths = await _write_assignment(sandbox, root, data)
        tools: dict[str, Tool] = {
            name: ScratchFileTool(name, sandbox, output_root, readonly_paths)
            for name in ("read_file", "write_file", "edit_file")
        }
        evidence = EvidenceReader(
            model.files,
            data,
            recovery_evidence=(
                runtime.recovery_evidence
                if (getattr(runtime, "changes", None) or {}).get("recovery_sources")
                else None
            ),
        )
        if evidence.allowed:
            tools[evidence.name] = evidence
        if runtime.resources is not None:
            tools[runtime.resources.name] = runtime.resources
        reader = TargetReader(runtime)
        tools[reader.name] = reader
        search = runtime.tools.get("openviking_search")
        if search is not None:
            tools[search.name] = _ScopedSearch(search, runtime.target)
        schemas = [tool.to_schema() for tool in tools.values()]
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system + _WORKER_INSTRUCTIONS},
            {
                "role": "user",
                "content": "Process assignment.json and write the requested Markdown files.",
            },
        ]
        failures: Counter = Counter()
        for _ in range(limits.subagent_iterations):
            response = await model.call(stage, messages, schemas, max_tokens=model.max_tokens)
            finish = response.finish_reason
            calls = response.tool_calls or []
            if finish in {"length", "max_tokens"}:
                # Never execute incomplete tool calls from truncated output.
                error = "Agent output was truncated; use smaller writes and complete tool calls"
                if not retry_allowed(failures, error):
                    raise ValueError(error)
                model.metrics["repairs"] += 1
                messages.append({"role": "user", "content": error})
                continue
            if not calls:
                if finish not in _FINAL_FINISH:
                    raise ValueError(f"Model did not complete its turn ({finish})")
                if not (response.content or "").strip():
                    raise ValueError("Model returned an empty final reply")
                return output_root
            if finish not in _TOOL_FINISH | _FINAL_FINISH:
                raise ValueError(f"Model did not complete its turn ({finish})")
            messages.append(
                {
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments, ensure_ascii=False),
                            },
                        }
                        for call in calls
                    ],
                }
            )
            for call in calls:
                tool = tools.get(call.name)
                try:
                    if tool is None:
                        raise ValueError(f"Unknown tool: {call.name}")
                    result = await tool.execute(None, **call.arguments)
                except (ValueError, TypeError, KeyError, OSError) as exc:
                    result = "Error: " + str(exc)[:800]
                # Image evidence keeps its content parts; the provider adapts the transport.
                content = result.content if isinstance(result, MultimodalToolResult) else result
                messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
        raise ValueError("Compile worker exhausted its tool rounds before completion")

    return run
