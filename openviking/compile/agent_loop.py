"""Run focused pipeline children: a bounded tool loop over task-private scratch files.

Upstream runs children through VikingBot's AgentLoop (see pipeline_agent.py there).
In-server Compile runs them here, with scratch-confined file tools and no command
execution. Only naturally completed workers expose their output directories.
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from typing import Any

from openviking.compile.media import MultimodalToolResult
from openviking.compile.models import COMPILE_DRAFT_ROOT
from openviking.compile.pipeline_agent import TargetReader
from openviking.compile.pipeline_io import retry_allowed
from openviking.compile.renderer import validate_relative_file_path
from openviking.compile.skill_resources import EvidenceReader
from openviking.compile.tool import Tool

# Lines returned by one read_file call when no limit is given.
READ_FILE_DEFAULT_LINES = 400


class ScratchFileTool(Tool):
    """read_file/write_file/edit_file confined to one child's private scratch root.

    Viking URIs, absolute paths and traversal are rejected; skills and sources are
    read through read_skill_resource and read_evidence instead. Final review reads
    the whole task tree but may only write below ``write_prefix``.
    """

    _SCHEMAS = {
        "read_file": (
            "Read a UTF-8 file in your scratch directory. offset/limit select zero-based lines.",
            {
                "path": {"type": "string"},
                "offset": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1},
            },
            ["path"],
        ),
        "write_file": (
            "Create or replace a UTF-8 file in your scratch directory.",
            {"path": {"type": "string"}, "content": {"type": "string"}},
            ["path", "content"],
        ),
        "edit_file": (
            "Replace one exact occurrence of old_text with new_text in a scratch file.",
            {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            ["path", "old_text", "new_text"],
        ),
        "list_dir": (
            "List entries of a directory in your scratch directory ('.' for its root).",
            {"path": {"type": "string"}},
            ["path"],
        ),
    }

    def __init__(
        self,
        name: str,
        sandbox: Any,
        root: str,
        write_prefix: str | None = None,
        readonly_paths: dict[str, str] | None = None,
    ):
        description, properties, required = self._SCHEMAS[name]
        self.name, self.description = name, description
        self.parameters = {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }
        self.sandbox, self.root, self.write_prefix = sandbox, root, write_prefix
        self.readonly_paths = readonly_paths or {}

    def _path(self, path: str) -> str:
        if str(path).startswith("viking://"):
            raise ValueError("Scratch file tools only access your own scratch directory")
        if self.name == "list_dir" and str(path).strip() in {"", "."}:
            return self.root
        relative = validate_relative_file_path(path)
        if relative in self.readonly_paths:
            if self.name != "read_file":
                raise ValueError("Assigned input files are read-only")
            return self.readonly_paths[relative]
        if (
            self.write_prefix is not None
            and self.name in {"write_file", "edit_file"}
            and not relative.startswith(self.write_prefix + "/")
        ):
            raise ValueError(
                f"Write only inside {self.write_prefix}/; use the same path as read_file"
            )
        return f"{self.root}/{relative}"

    async def execute(self, tool_context: Any = None, **kwargs: Any) -> str:
        path = self._path(kwargs["path"])
        if self.name == "list_dir":
            try:
                entries = await self.sandbox.list_dir(path)
            except FileNotFoundError as exc:
                raise ValueError(f"No such scratch directory: {kwargs['path']}") from exc
            return "\n".join(entries) or "(empty)"
        if self.name == "write_file":
            await self.sandbox.write_file(path, kwargs["content"])
            return f"Wrote {kwargs['path']}."
        try:
            text = (await self.sandbox.read_file_bytes(path)).decode("utf-8")
        except FileNotFoundError as exc:
            raise ValueError(f"No such scratch file: {kwargs['path']}") from exc
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
        return f"Edited {kwargs['path']}."


_AGENT_INSTRUCTIONS = (
    "\nRead assignment.json with read_file. Read all assigned materials. "
    "assignment.json and inputs/ paths are read-only. "
    "Use write_file and edit_file for deliverable Markdown, with paths relative "
    "to the publication destination. Read and edit outputs using the same paths. "
    "Write only deliverables, without scratch files. Read existing target files "
    "with read_target_file before updating them. "
    "Finish with a brief completion message after all writes succeed. "
    "A completion message alone does not produce files."
)


def agent_runner(limits):
    """Bind isolated file workers with bounded calls and natural completion.

    Inputs are immutable and separate from outputs; failed or exhausted workers
    never return an output root for publication.
    """

    async def run(system, data, model, *, stage="agent", runtime):
        sandbox = model.files.sandbox
        root = f"{COMPILE_DRAFT_ROOT}/{uuid.uuid4().hex}"
        output_root = f"{root}/output"
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
        await sandbox.write_file(
            f"{root}/assignment.json", json.dumps(assignment, ensure_ascii=False)
        )
        tools: dict[str, Tool] = {}
        if model.resources:
            tools[model.resources.name] = model.resources
        evidence = EvidenceReader(model.files, data)
        if evidence.allowed:
            tools[evidence.name] = evidence
        target_reader = TargetReader(runtime)
        tools[target_reader.name] = target_reader
        search = runtime.tools.get("openviking_search")
        if search is not None and runtime.tool_context is not None:
            from copy import copy

            async def search_target(tool_context=None, **arguments):
                arguments["target_uri"] = runtime.target
                return await search.execute(runtime.tool_context, **arguments)

            scoped = copy(search)
            scoped.execute = search_target
            tools[scoped.name] = scoped
        for name in ("read_file", "write_file", "edit_file"):
            tools[name] = ScratchFileTool(name, sandbox, output_root, readonly_paths=readonly_paths)
        schemas = [tool.to_schema() for tool in tools.values()]
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system + _AGENT_INSTRUCTIONS},
            {
                "role": "user",
                "content": "Process assignment.json and write the requested Markdown files.",
            },
        ]
        failures: Counter = Counter()
        for _ in range(limits.subagent_iterations):
            response = await model.call(stage, messages, schemas, max_tokens=model.max_tokens)
            if response.finish_reason in {"length", "max_tokens"}:
                error = "Agent output was truncated; use smaller writes and complete tool calls"
                if not retry_allowed(failures, error):
                    raise ValueError(error)
                model.metrics["repairs"] += 1
                messages.append({"role": "user", "content": error})
                continue
            if getattr(response, "error_kind", None) or response.finish_reason not in {
                "stop",
                "end_turn",
                "tool_calls",
                "tool_use",
                "function_call",
            }:
                raise ValueError(response.content or "Compile worker model failed")
            calls = response.tool_calls or []
            if not calls:
                if (
                    response.finish_reason not in {"stop", "end_turn"}
                    or not (response.content or "").strip()
                ):
                    raise ValueError("Compile worker ended without natural completion")
                return output_root
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
                content = result.content if isinstance(result, MultimodalToolResult) else result
                messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
        raise ValueError("Compile worker exhausted its tool rounds before completion")

    return run
