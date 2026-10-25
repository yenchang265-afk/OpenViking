"""Focused pipeline children: a bounded tool loop over task-private scratch files."""

from __future__ import annotations

import inspect
import json
import uuid
from collections import Counter
from typing import Any

import json_repair

from openviking.compile import file_ops
from openviking.compile.hashing import content_hash
from openviking.compile.models import COMPILE_DRAFT_ROOT
from openviking.compile.pipeline_io import ROOT, TaskFiles, retry_allowed
from openviking.compile.renderer import validate_relative_file_path
from openviking.compile.results import FileResponse, RecordResponse
from openviking.compile.schemas import result_schema
from openviking.compile.skill_resources import EvidenceReader
from openviking.compile.tool import Tool

# Lines returned by one read_file call when no limit is given.
READ_FILE_DEFAULT_LINES = 400


async def prepare_assignment(data, sandbox, root):
    """Store an oversized assignment in private scratch, replacing source bodies with read handles.

    The caller retains the full data for lineage validation and enables evidence reads.
    Candidate bodies use text files so line-based reads do not expand an entire JSON string.
    """
    assignment = {k: v for k, v in data.items() if k != "original_evidence"}
    assignment["inputs"] = []
    for item in data.get("inputs", []):
        payload = item.get("payload", {})
        if "text" in payload and "uri" in payload:
            payload = {k: v for k, v in payload.items() if k != "text"}
            payload["source_ranges"] = [item["id"]]
        assignment["inputs"].append({**item, "payload": payload})
    if "candidates" in data:
        assignment["candidates"] = []
        for index, candidate in enumerate(data["candidates"]):
            if candidate.get("binary"):
                assignment["candidates"].append(candidate)
                continue
            path = f"candidate-{index}.txt"
            await sandbox.write_file(f"{root}/{path}", candidate["content"])
            assignment["candidates"].append(
                {**{k: v for k, v in candidate.items() if k != "content"}, "content_file": path}
            )
    await sandbox.write_file(
        f"{root}/assignment.json", json.dumps(assignment, ensure_ascii=False, indent=2)
    )
    return {
        "assignment_file": "assignment.json",
        "instructions": "Read assignment.json with read_file offset/limit. Read source_ranges with read_evidence; "
        "source text is not included. Read candidate content_file paths in ranges. "
        "Process all assigned inputs before submitting the complete result.",
    }


class EmitResult(Tool):
    """Validate child results with independent retry allowances for distinct errors."""

    name = "emit"
    description = "Submit the complete typed transformation result."

    def __init__(
        self,
        schema,
        validate,
        sandbox=None,
        root="",
        data=None,
        metrics=None,
    ):
        self.schema, self.validate = schema, validate
        self.sandbox, self.root = sandbox, root
        self.result = None
        self.failures = Counter()
        self.can_retry = True
        self.last_error = ""
        self.data = data or {}
        self.metrics = metrics

    async def read_content(self, relative: str) -> bytes:
        """Read private scratch or an assigned ready snapshot; foreign snapshots are not accessible."""
        supplied = {
            item.get("ready_file", {}).get("content_ref") for item in self.data.get("inputs", [])
        }
        supplied.update(item.get("content_ref") for item in self.data.get("candidates", []))
        if relative in supplied:
            saved = await TaskFiles(self.sandbox).get(relative)
            raw = file_ops.file_bytes(saved)
            actual = content_hash(raw)
            if saved.get("sha256", actual) != actual:
                raise ValueError("Stored file hash mismatch")
            return raw
        return await self.sandbox.read_file_bytes(f"{self.root}/{relative}")

    @property
    def parameters(self):
        parameters = result_schema(self.schema, self.data)
        if self.sandbox is None:
            return parameters
        parameters["properties"]["result_ref"] = {
            "type": "string",
            "description": "Relative path used with write_file for a JSON file containing the "
            "complete emit arguments, without result_ref. Submit result_ref alone instead of "
            "inline fields. Use for large results.",
        }
        parameters["required"] = []
        return parameters

    async def execute(self, **kwargs):
        """Return bounded validation feedback; only valid output terminates the child."""
        try:
            if (
                set(kwargs) == {"raw"}
                and isinstance(kwargs["raw"], str)
                and "raw" not in self.schema.model_fields
            ):
                kwargs = json_repair.loads(kwargs["raw"], stream_stable=True)
            if isinstance(kwargs, dict) and "result_ref" in kwargs:
                if self.sandbox is None:
                    raise ValueError(
                        "result_ref is unavailable; submit inline emit arguments, without a result file"
                    )
                if len(kwargs) != 1:
                    raise ValueError("result_ref is an alternative to all inline result fields")
                relative = validate_relative_file_path(kwargs["result_ref"])
                raw = await self.sandbox.read_file_bytes(f"{self.root}/{relative}")
                kwargs = json_repair.loads(raw.decode("utf-8"), stream_stable=True)
            result = self.schema.model_validate(kwargs)
            if isinstance(result, RecordResponse):
                for draft in result.records:
                    if draft.ready_content_ref is not None:
                        if (
                            self.sandbox is None
                            or draft.ready_content is not None
                            or draft.ready_content_base64 is not None
                        ):
                            raise ValueError(
                                "Ready file reference requires scratch access without inline text"
                            )
                        relative = validate_relative_file_path(draft.ready_content_ref)
                        raw = await self.read_content(relative)
                        body = file_ops.encode_content(raw)
                        draft.ready_content = body["content"]
                        draft.ready_content_base64 = body["content_base64"]
                        draft.ready_content_ref = None
            if isinstance(result, FileResponse):
                for draft in result.files:
                    if draft.content_ref is not None:
                        if (
                            self.sandbox is None
                            or draft.content is not None
                            or draft.content_base64 is not None
                            or draft.patches
                        ):
                            raise ValueError(
                                "File reference requires scratch access without content/patches"
                            )
                        relative = validate_relative_file_path(draft.content_ref)
                        raw = await self.read_content(relative)
                        actual = content_hash(raw)
                        if draft.content_sha256 and draft.content_sha256 != actual:
                            raise ValueError("Scratch artifact hash mismatch")
                        body = file_ops.encode_content(raw)
                        draft.content, draft.content_base64 = (
                            body["content"],
                            body["content_base64"],
                        )
                        draft.content_sha256 = actual
                        draft.content_ref = None
            if self.validate:
                checked = self.validate(result)
                if inspect.isawaitable(checked):
                    await checked
            self.result = result
            return "Result accepted."
        except (ValueError, TypeError, OSError) as exc:
            self.last_error = str(exc)[:1600]
            self.can_retry = retry_allowed(self.failures, self.last_error)
            if self.metrics is not None:
                self.metrics["validation_failures"] += 1
                if self.can_retry:
                    self.metrics["repairs"] += 1
            feedback = "Error: " + self.last_error
            if (
                self.can_retry
                and self.sandbox is not None
                and isinstance(kwargs, dict)
                and "result_ref" not in kwargs
            ):
                # Keep complete rejected data private; edits still pass every emit validator.
                candidate = f"rejected-{uuid.uuid4().hex}.json"
                try:
                    content = (
                        kwargs["raw"]
                        if set(kwargs) == {"raw"} and isinstance(kwargs["raw"], str)
                        else json.dumps(kwargs, ensure_ascii=False)
                    )
                    await self.sandbox.write_file(f"{self.root}/{candidate}", content)
                    feedback += (
                        f"\nRepair {candidate} with edit_file, then emit only "
                        f'{{"result_ref":"{candidate}"}}.'
                    )
                except (OSError, ValueError):
                    pass
            return feedback


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

    async def execute(self, **kwargs: Any) -> str:
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
    model request goes through the task's bounded, metered JsonModel.call. Final
    review can browse task files, with writes confined to its staged outputs.
    """

    async def run(system, data, schema, validate, model, *, stage="agent"):
        sandbox = model.files.sandbox
        final_review = stage == "final_review_agent"
        root = ROOT if final_review else f"{COMPILE_DRAFT_ROOT}/{uuid.uuid4().hex}"
        evidence = EvidenceReader(model.files, data)
        submit = EmitResult(
            schema, validate, None if final_review else sandbox, root, data, model.metrics
        )
        assignment = data
        if not model.fits(system, data, schema):
            assignment = await prepare_assignment(data, sandbox, root)
            evidence.delivered.clear()
        tools: dict[str, Tool] = {"emit": submit}
        if model.resources:
            tools[model.resources.name] = model.resources
        if evidence.allowed - evidence.delivered:
            tools[evidence.name] = evidence
        for name in (
            "read_file",
            "write_file",
            "edit_file",
            *(["list_dir"] if final_review else []),
        ):
            tools[name] = ScratchFileTool(
                name, sandbox, root, data["artifact_directory"] if final_review else None
            )
        schemas = [tool.to_schema() for tool in tools.values()]
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                # These stages define their own file access and submission rules.
                "content": system
                + ("" if stage == "map_agent" or final_review else _AGENT_INSTRUCTIONS),
            },
            {"role": "user", "content": json.dumps(assignment, ensure_ascii=False)},
        ]
        failures: Counter = Counter()
        iterations = limits.final_review_iterations if final_review else limits.subagent_iterations
        for _ in range(iterations):
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
                    result = await tool.execute(**call.arguments)
                except (ValueError, TypeError, KeyError, OSError) as exc:
                    result = "Error: " + str(exc)[:800]
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
            if submit.result is not None:
                return submit.result
            if not submit.can_retry:
                break
        raise ValueError(
            "Required agent transform ended without validated output: "
            + (submit.last_error or "No emit result was submitted")
        )

    return run
