"""In-process Compile execution: collect sources, run the pipeline, publish to the target.

The runner owns one attempt. Durability, retries after restart, cancellation and
per-target serialization belong to the queue-backed task service that calls it;
an interrupted attempt is simply run again from the beginning.
"""

from __future__ import annotations

import asyncio
import shutil
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp
from typing import Any
from urllib.parse import quote

from pydantic import TypeAdapter

from openviking.compile import file_ops
from openviking.compile.hashing import content_hash
from openviking.compile.llm import CompileProvider
from openviking.compile.models import (
    CompileErrorInfo,
    CompileFailure,
    CompileLimits,
    CompileResult,
    SanitizedCompileRequest,
)
from openviking.compile.ops import finalize as finalize_op
from openviking.compile.pipeline import Pipeline
from openviking.compile.pipeline_agent import agent_runner
from openviking.compile.renderer import RenderedBundle
from openviking.compile.scratch import ScratchDir
from openviking.compile.sources import pack_source_batches
from openviking.core.namespace import classify_uri, relative_uri_path
from openviking.core.skill_loader import validate_skill_format
from openviking.service.external_task_service import TaskCompletedDuringCancel
from openviking.service.task_tracker_concurrency import run_to_completion
from openviking.service.task_work_index import detach_task_context
from openviking.utils.path_safety import sanitize_relative_viking_path
from openviking_cli.exceptions import OpenVikingError
from openviking_cli.utils.logger import get_logger

logger = get_logger(__name__)

# Report a stage and public metadata for the task record.
Progress = Callable[[str, dict[str, Any]], Awaitable[None]]
# Return True once the caller asked to cancel; checked before publishing.
CancelCheck = Callable[[], Awaitable[bool]]

_SKILL_EXCLUDED_FILES = frozenset(
    {".abstract.md", ".overview.md", ".relations.json", ".source.json"}
)
# Scratch of failed or cancelled attempts is kept this long for diagnosis.
SCRATCH_RETENTION_SECONDS = 7 * 24 * 60 * 60
EMPTY_OUTPUT_MESSAGE = (
    "Compile finished without writing any output files. The model may be too small "
    "to follow this Skill; configure a more capable vlm model in ov.conf and run "
    "the compile again."
)


def compile_time(value: Any) -> datetime:
    """Parse ISO/Unix timestamps; naive values use UTC and invalid values raise ValueError."""
    parsed = TypeAdapter(datetime).validate_python(value)
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def pipeline_incomplete_error(
    *, published: bool, conflicts: list[Any], failures: list[str]
) -> CompileErrorInfo | None:
    """The task error for a pipeline compile that published nothing.

    With no conflicts or failures to explain it, the model itself wrote nothing,
    so point the user at a more capable model.
    """
    if published:
        return None
    if not conflicts and not failures:
        return CompileErrorInfo(code="COMPILE_INCOMPLETE", message=EMPTY_OUTPUT_MESSAGE)
    return CompileErrorInfo(code="COMPILE_INCOMPLETE", message="No output was acknowledged.")


def unexpected_error_code(exc: Exception, *, stage: str) -> str:
    writing = stage in {"writing", "refreshing"}
    if isinstance(exc, OpenVikingError):
        if exc.code == "CONFLICT" and writing:
            return "WRITE_CONFLICT"
        return "WRITE_FAILED" if writing else exc.code
    return "WRITE_FAILED" if writing else "INTERNAL"


async def ensure_target_directory(client: Any, target: str) -> None:
    """Create a missing target directory, as submission did under the bot runtime."""
    try:
        stat = await client.stat(target)
    except OpenVikingError as exc:
        if exc.code != "NOT_FOUND":
            raise
        await client.mkdir(target)
        return
    if not stat.get("isDir", stat.get("is_dir", False)):
        raise CompileFailure(
            "INVALID_ARGUMENT", f"Compile target must be a directory: {target}", stage="queued"
        )


async def list_source_files(
    client: Any, roots: list[str], *, cutoff: datetime | None = None
) -> list[str]:
    """List unique sources, excluding files strictly older than the UTC cutoff.

    Unknown file times are retained; directory times never prune descendants.
    Listing failures propagate. Empty sources raise only without a cutoff.
    """

    async def inventory(root: str) -> list[dict[str, Any]]:
        entry = await client.stat(root)
        if not entry.get("isDir", entry.get("is_dir", False)):
            return [{**entry, "uri": root}]
        entries = []
        pending, seen = [root], {root}
        while pending:
            directory = pending.pop()
            offset = 0
            while True:
                page = await client.list_resources(directory, node_limit=500, offset=offset)
                for item in page:
                    uri = str(item.get("uri") or "").rstrip("/")
                    if not uri or (uri != root and not relative_uri_path(root, uri)):
                        raise ValueError(f"Source inventory returned an out-of-scope URI: {uri}")
                    entries.append(item)
                    if item.get("isDir", item.get("is_dir", False)) and uri not in seen:
                        pending.append(uri)
                        seen.add(uri)
                offset += len(page)
                if len(page) < 500:
                    break
        return entries

    files: set[str] = set()
    for root in dict.fromkeys(roots):
        for entry in await inventory(root):
            uri = str(entry.get("uri") or "").rstrip("/")
            if entry.get("isDir", entry.get("is_dir", False)):
                continue
            if cutoff is not None:
                try:
                    if compile_time(entry.get("modTime", entry.get("mtime"))) < cutoff:
                        continue
                except ValueError:
                    pass
            files.add(uri)
    if not files and cutoff is None:
        raise ValueError("Compile sources contain no files")
    return sorted(files)


class CompileRunner:
    """Execute one Compile attempt against an in-process OpenViking client."""

    def __init__(self, *, limits: CompileLimits, work_root: Path):
        self.limits = limits
        self.work_root = work_root

    def _owner_root(self, account_id: str, user_id: str | None = None) -> Path:
        """Group scratch by owner so identity deletion can purge it."""
        root = self.work_root / quote(account_id, safe="")
        return root if user_id is None else root / quote(user_id, safe="")

    def scratch(self, task_id: str, owner: tuple[str, str]) -> ScratchDir:
        return ScratchDir(self._owner_root(*owner) / task_id)

    def prune_scratch(
        self, *, keep: Path, max_age_seconds: float = SCRATCH_RETENTION_SECONDS
    ) -> None:
        """Remove scratch kept by old failed or cancelled attempts; it holds source copies."""
        cutoff = time.time() - max_age_seconds
        for entry in self.work_root.glob("*/*/*"):
            try:
                if entry != keep and entry.is_dir() and entry.stat().st_mtime < cutoff:
                    shutil.rmtree(entry, ignore_errors=True)
            except OSError:
                continue

    def purge_owner(self, account_id: str, user_id: str | None = None) -> None:
        """Delete all scratch of a deleted user, or of a whole account."""
        shutil.rmtree(self._owner_root(account_id, user_id), ignore_errors=True)

    async def run(
        self,
        task_id: str,
        request: SanitizedCompileRequest,
        *,
        client: Any,
        provider: CompileProvider,
        progress: Progress,
        cancelled: CancelCheck,
        owner: tuple[str, str],
    ) -> dict[str, Any]:
        """Return the public CompileResult; raise CompileFailure on a reportable failure.

        The scratch directory is reset first so a re-delivered task starts clean.
        It is removed after success and kept after failure for diagnosis.
        """
        scratch = self.scratch(task_id, owner)
        await asyncio.to_thread(self.prune_scratch, keep=scratch.root)
        await asyncio.to_thread(scratch.reset)
        succeeded = False
        stage = "collecting_context"
        try:
            await progress(stage, {})
            await ensure_target_directory(client, request.to)
            source_files = None
            if request.last_compile_time is not None:
                source_files = await list_source_files(
                    client, request.from_, cutoff=request.last_compile_time
                )
                if not source_files:
                    # An incremental no-op finishes without model calls or target writes.
                    succeeded = True
                    return CompileResult(
                        from_=request.from_, to=request.to, skill=request.skill
                    ).model_dump(by_alias=True)
            skill_text = await client.read_raw(f"{request.skill}/SKILL.md")
            if not skill_text.strip():
                raise CompileFailure("SKILL_INVALID", "Compile Skill is empty", stage=stage)
            stage = "pipeline"
            result = await self._run_pipeline(
                request,
                client=client,
                provider=provider,
                scratch=scratch,
                skill_text=skill_text,
                source_files=source_files,
                progress=progress,
                cancelled=cancelled,
            )
            succeeded = True
            return result
        except TaskCompletedDuringCancel:
            succeeded = True
            raise
        except CompileFailure:
            raise
        except OpenVikingError as exc:
            code = "WRITE_CONFLICT" if exc.code in {"CONFLICT", "ALREADY_EXISTS"} else exc.code
            raise CompileFailure(code, str(exc), stage=stage) from exc
        except Exception as exc:
            logger.exception("Compile task %s failed in stage %s", task_id, stage)
            raise CompileFailure(
                unexpected_error_code(exc, stage=stage), str(exc), stage=stage
            ) from exc
        finally:
            if succeeded:
                await asyncio.to_thread(scratch.remove)

    async def _run_pipeline(
        self,
        request: SanitizedCompileRequest,
        *,
        client: Any,
        provider: CompileProvider,
        scratch: ScratchDir,
        skill_text: str,
        source_files: list[str] | None,
        progress: Progress,
        cancelled: CancelCheck,
    ) -> dict[str, Any]:
        usage: dict[str, int] = {}
        pipeline = Pipeline(
            client=client,
            sandbox=scratch,
            provider=provider,
            model=provider.model,
            temperature=provider.temperature,
            limits=self.limits,
            request=request,
            skill=skill_text,
            usage=usage,
        )
        pipeline.model.agent_runner = agent_runner(self.limits)

        def metrics() -> dict[str, Any]:
            """Expose token totals and existing error summaries, without per-call counters."""
            return {
                "pipeline": {
                    "tokens": {
                        "input": usage.get("prompt_tokens", 0),
                        "output": usage.get("completion_tokens", 0),
                        "cached": usage.get("cache_read_input_tokens", 0),
                    },
                    "errors": list(
                        dict.fromkeys(e[:300] for e in pipeline.failures + pipeline.warnings)
                    ),
                }
            }

        await progress("pipeline", {})
        ordered = (
            source_files
            if source_files is not None
            else await list_source_files(client, request.from_)
        )
        await pipeline.files.put("inputs", dict.fromkeys(ordered, "pending"))

        async def source_batches():
            """Retain at most one read batch of source bodies while seeding task shards."""
            for start in range(0, len(ordered), 8):
                uris = ordered[start : start + 8]
                contents = await asyncio.gather(
                    *(client.read_raw(uri) for uri in uris), return_exceptions=True
                )
                readable = []
                for uri, content in zip(uris, contents, strict=True):
                    if isinstance(content, Exception):
                        manifest = await pipeline.files.get("inputs")
                        manifest[uri] = "failed"
                        await pipeline.files.put("inputs", manifest)
                        pipeline.failures.append(f"Source read failed: {uri}: {str(content)[:400]}")
                    elif isinstance(content, BaseException):
                        raise content
                    else:
                        readable.append((uri, content))
                for batch in pack_source_batches(readable, self.limits):
                    yield batch

        stage = "pipeline"
        try:
            try:
                rendered = await pipeline.run(source_batches())
            except (CompileFailure, TimeoutError) as exc:
                if not pipeline.artifacts or getattr(exc, "code", None) == "SKILL_REPAIR_FAILED":
                    raise
                pipeline.warnings.append(
                    f"Partial output; Compile did not finish: {str(exc)[:500]}"
                )
                async with asyncio.timeout(self.limits.salvage_grace_seconds):
                    rendered = await finalize_op.run(
                        pipeline, list(dict.fromkeys(pipeline.artifacts))
                    )
            # Cancellation must stop the attempt before any target write.
            if await cancelled():
                raise asyncio.CancelledError()
            stage = "writing"
            await progress(stage, metrics())

            published: dict[str, Any] = {}

            async def publish() -> dict[str, Any]:
                # Index refresh for written pages belongs to its own write task, as
                # with an HTTP batch write, not to this Compile task's lifecycle.
                with detach_task_context():
                    published["result"] = await self._publish(
                        request, pipeline, rendered, client=client
                    )
                    return published["result"]

            # A cancel or shutdown after this point lands once publishing settles, so
            # written pages always get their index refresh queued.
            try:
                return await run_to_completion(publish)
            except asyncio.CancelledError:
                if "result" in published:
                    # The output is live; record it instead of re-running the compile.
                    raise TaskCompletedDuringCancel(published["result"]) from None
                raise
        except OpenVikingError as exc:
            code = "WRITE_CONFLICT" if exc.code in {"CONFLICT", "ALREADY_EXISTS"} else exc.code
            if stage == "writing" and exc.code in {"REFRESH_FAILED", "DEADLINE_EXCEEDED"}:
                stage = "refreshing"
            raise CompileFailure(code, str(exc), stage=stage) from exc
        finally:
            await progress(stage, metrics())

    async def _publish(
        self,
        request: SanitizedCompileRequest,
        pipeline: Pipeline,
        rendered: RenderedBundle,
        *,
        client: Any,
    ) -> dict[str, Any]:
        skill_target = classify_uri(request.to).context_type == "skill"
        result: dict[str, Any] = {"created": [], "updated": [], "unchanged": []}
        if skill_target:
            result = await self._write_skill_bundle(
                client=client, target_uri=request.to, rendered=rendered
            )
        elif rendered.operations:
            result = await client.batch_write(
                root_uri=request.to,
                operations=rendered.operations,
                wait=False,
                skip_conflicts=True,
            )
        conflicts = result.get("conflicts", [])
        for conflict in conflicts:
            pipeline.warnings.append(
                f"Target left unchanged due to conflict: {conflict['uri']}: {conflict['message']}"
            )
        published = (
            [*rendered.created, *rendered.updated, *rendered.unchanged]
            if skill_target
            else [
                *result.get("created", []),
                *result.get("updated", []),
                *result.get("unchanged", []),
                *rendered.unchanged,
            ]
        )
        await pipeline.write_coverage(published)
        summary = await pipeline.files.get("summary")
        summary["committed"] = True
        summary["warnings"] = pipeline.warnings
        summary["conflicts"] = conflicts
        await pipeline.files.put("summary", summary)
        compiled = CompileResult(
            from_=request.from_,
            to=request.to,
            skill=request.skill,
            created=result.get("created", rendered.created),
            updated=result.get("updated", rendered.updated),
            conflicts=conflicts,
            unchanged=list(
                dict.fromkeys(
                    [*([] if skill_target else rendered.unchanged), *result.get("unchanged", [])]
                )
            ),
            page_count=len(set(rendered.wiki_uris) & set(published)),
            link_count=rendered.link_count,
            link_report=rendered.link_report,
            warnings=pipeline.warnings,
        ).model_dump(by_alias=True)
        error = pipeline_incomplete_error(
            published=bool(published), conflicts=conflicts, failures=pipeline.failures
        )
        if error is not None:
            # Keep conflicts and warnings so the user can see why nothing landed.
            raise CompileFailure(error.code, error.message, stage="writing", result=compiled)
        return compiled

    async def _materialize_skill_package(
        self, *, client: Any, skill_result: Mapping[str, Any], skill_dir: Path
    ) -> None:
        await asyncio.to_thread(
            _write_local,
            skill_dir / "SKILL.md",
            str(skill_result.get("content") or "").encode("utf-8"),
        )
        for item in skill_result.get("files") or []:
            if not isinstance(item, Mapping) or item.get("is_dir"):
                continue
            relative = str(item.get("path") or "")
            if relative == "SKILL.md" or Path(relative).name in _SKILL_EXCLUDED_FILES:
                continue
            try:
                relative = sanitize_relative_viking_path(relative)
                local = (skill_dir / relative).resolve()
                if skill_dir.resolve() not in local.parents:
                    raise ValueError("path escapes Skill root")
            except ValueError as exc:
                raise CompileFailure("SKILL_INVALID", str(exc), stage="writing") from exc
            data = await client.download_bytes(str(item.get("uri") or ""))
            await asyncio.to_thread(_write_local, local, data)

    async def _write_skill_bundle(
        self, *, client: Any, target_uri: str, rendered: RenderedBundle
    ) -> dict[str, list[str]]:
        """Publish one validated package, retaining untouched existing attachments.

        Pipeline operations contain target-relative file revisions. Recheck those
        revisions against the materialized package before invoking the Skill API;
        Skill updates replace the whole package and do not offer atomic file CAS.
        The returned URIs identify Skill roots, as required by Compile's Skill result.
        """
        result: dict[str, list[str]] = {"created": [], "updated": [], "unchanged": []}
        uris = [*(op["uri"] for op in rendered.operations), *rendered.unchanged]
        if not uris:
            return result
        paths = [relative_uri_path(target_uri, uri) for uri in uris]
        if any(not path or "/" not in path for path in paths):
            raise CompileFailure(
                "AGENT_OUTPUT_INVALID", "Skill files require <skill-name>/ paths", stage="rendering"
            )
        names = {sanitize_relative_viking_path(path).split("/")[0] for path in paths}
        if len(names) != 1:
            raise CompileFailure(
                "AGENT_OUTPUT_INVALID", "Compile requires one Skill package", stage="rendering"
            )
        skill_name = names.pop()
        root_uri = f"{target_uri.rstrip('/')}/{skill_name}"
        if not rendered.operations:
            result["unchanged"].append(root_uri)
            return result
        # Package files are staged off the event loop shared by concurrent Compile tasks.
        temp_dir = await asyncio.to_thread(mkdtemp, prefix="openviking-compile-skill-")
        try:
            temp_root = Path(temp_dir).resolve()
            skill_dir = temp_root / skill_name
            try:
                stat = await client.stat(root_uri)
                if not stat.get("isDir"):
                    raise CompileFailure(
                        "WRITE_CONFLICT",
                        f"Skill target is not a directory: {root_uri}",
                        stage="writing",
                    )
                exists = True
            except OpenVikingError as exc:
                if exc.code != "NOT_FOUND":
                    raise
                exists = False
            if exists:
                await self._materialize_skill_package(
                    client=client,
                    skill_result=await client.get_skill(skill_name, target_uri=target_uri),
                    skill_dir=skill_dir,
                )
            await asyncio.to_thread(
                _stage_skill_operations,
                temp_root,
                skill_name,
                target_uri,
                rendered.operations,
            )
            if exists:
                published = await client.update_skill(
                    skill_name, str(skill_dir), target_uri=target_uri, wait=True
                )
            else:
                published = await client.add_skill(str(skill_dir), target_uri=target_uri, wait=True)
            result["updated" if exists else "created"].append(
                str(published.get("root_uri") or published.get("uri") or root_uri)
            )
            return result
        finally:
            await asyncio.to_thread(shutil.rmtree, temp_dir, ignore_errors=True)


def _write_local(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _stage_skill_operations(
    temp_root: Path, skill_name: str, target_uri: str, operations: list[dict[str, Any]]
) -> None:
    """Apply rendered revisions to the materialized package and validate its SKILL.md."""
    for operation in operations:
        relative = sanitize_relative_viking_path(relative_uri_path(target_uri, operation["uri"]))
        local = temp_root / relative
        old = local.read_bytes() if local.is_file() else None
        expected = operation.get("expected_sha256")
        if (operation["mode"] == "create" and local.exists()) or (
            operation["mode"] == "replace" and (old is None or content_hash(old) != expected)
        ):
            raise CompileFailure(
                "WRITE_CONFLICT", f"Skill file changed: {operation['uri']}", stage="writing"
            )
        _write_local(local, file_ops.file_bytes(operation))
    skill_md = temp_root / skill_name / "SKILL.md"
    validation = validate_skill_format(
        skill_md.read_text(encoding="utf-8") if skill_md.is_file() else "",
        strict=True,
        skill_dir_name=skill_name,
        source_path=str(skill_md),
    )
    if not validation["valid"]:
        raise CompileFailure(
            "AGENT_OUTPUT_INVALID",
            "; ".join(issue["message"] for issue in validation["errors"]),
            stage="rendering",
        )
