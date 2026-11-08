"""Focused pipeline children: assignments and the validated emit tool.

agent_loop.py runs each child; upstream runs it through VikingBot's AgentLoop.
"""

from __future__ import annotations

import inspect
import json
import uuid
from collections import Counter

import json_repair

from openviking.compile import file_ops
from openviking.compile._compat import Tool
from openviking.compile.hashing import content_hash
from openviking.compile.pipeline_io import TaskFiles, retry_allowed
from openviking.compile.renderer import validate_relative_file_path
from openviking.compile.results import FileResponse, RecordResponse
from openviking.compile.schemas import result_schema


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

    async def execute(self, tool_context, **kwargs):
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
