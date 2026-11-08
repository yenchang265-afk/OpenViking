"""Run focused pipeline children: a bounded tool loop over task-private scratch files.

Upstream runs children through VikingBot's AgentLoop (see pipeline_agent.py there).
In-server Compile runs them here, with scratch-confined file tools and no command
execution; assignments and the emit tool come from pipeline_agent.py unchanged.
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from typing import Any

from openviking.compile.media import MultimodalToolResult
from openviking.compile.models import COMPILE_DRAFT_ROOT
from openviking.compile.pipeline_agent import EmitResult, prepare_assignment
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

    def __init__(self, name: str, sandbox: Any, root: str, write_prefix: str | None = None):
        description, properties, required = self._SCHEMAS[name]
        self.name, self.description = name, description
        self.parameters = {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }
        self.sandbox, self.root, self.write_prefix = sandbox, root, write_prefix

    def _path(self, path: str) -> str:
        if str(path).startswith("viking://"):
            raise ValueError("Scratch file tools only access your own scratch directory")
        if self.name == "list_dir" and str(path).strip() in {"", "."}:
            return self.root
        relative = validate_relative_file_path(path)
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
    "\nUse emit to submit. Supplied Skill attachments are complete; "
    "they fulfill the Skill's reading requirements without a tool call. Do not reread them. "
    "read_skill_resource is available for additional references. "
    "Use assigned evidence, Skill attachments and your scratch files for this job. "
    "Prefer one inline emit for small finished results; scratch writing and rereading "
    "are optional, not mandatory verification steps. "
    "Write large/multiple files using write_file, then emit content_ref paths "
    "relative to your scratch root, without repeating their content. Runtime hashes "
    "the files and validates paths, revisions and source coverage before acceptance. "
    "For a large record collection, build a JSON result file incrementally with file "
    "tools, then emit only result_ref pointing to that file. Finished independent Map "
    "files may use ready_path plus ready_content_ref and concise routing payloads. "
    "Use edit_file to repair existing JSON."
)


def agent_runner(limits):
    """Bind an isolated child loop; queueing/cancellation remain owned by Pipeline.

    Each call has fresh history, a private scratch root and its stage's iteration
    limit. Large files are submitted by reference, then hashed and checked. Every
    model request goes through the task's bounded, metered JsonModel.call.
    """

    async def run(system, data, schema, validate, model, *, stage="agent"):
        sandbox = model.files.sandbox
        root = f"{COMPILE_DRAFT_ROOT}/{uuid.uuid4().hex}"
        evidence = EvidenceReader(model.files, data)
        submit = EmitResult(schema, validate, sandbox, root, data, model.metrics)
        assignment = data
        if not model.fits(system, data, schema):
            assignment = await prepare_assignment(data, sandbox, root)
            evidence.delivered.clear()
        tools: dict[str, Tool] = {"emit": submit}
        if model.resources:
            tools[model.resources.name] = model.resources
        if evidence.allowed - evidence.delivered:
            tools[evidence.name] = evidence
        for name in ("read_file", "write_file", "edit_file"):
            tools[name] = ScratchFileTool(name, sandbox, root)
        schemas = [tool.to_schema() for tool in tools.values()]
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                # Map defines its own file access and submission rules.
                "content": system + ("" if stage == "map_agent" else _AGENT_INSTRUCTIONS),
            },
            {"role": "user", "content": json.dumps(assignment, ensure_ascii=False)},
        ]
        failures: Counter = Counter()
        for _ in range(limits.subagent_iterations):
            response = await model.call(stage, messages, schemas, max_tokens=model.max_tokens)
            if response.finish_reason in {"length", "max_tokens"}:
                # Never execute incomplete tool calls from truncated output.
                error = "Agent output was truncated; use smaller writes or content_ref and complete tool calls"
                if not retry_allowed(failures, error):
                    raise ValueError(error)
                model.metrics["repairs"] += 1
                messages.append({"role": "user", "content": error})
                continue
            calls = response.tool_calls or []
            if not calls:
                messages.append({"role": "assistant", "content": response.content or ""})
                messages.append(
                    {"role": "user", "content": "Submit the result with the emit tool."}
                )
                continue
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
            if submit.result is not None:
                return submit.result
            if not submit.can_retry:
                break
        raise ValueError(
            "Required agent transform ended without validated output: "
            + (submit.last_error or "No emit result was submitted")
        )

    return run
