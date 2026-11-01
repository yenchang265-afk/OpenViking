# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Compile API models and the in-process, queue-backed Compile executor."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from openviking.core.namespace import classify_uri, uri_parts
from openviking.core.path_variables import resolve_path_variables
from openviking.core.uri_validation import validate_request_viking_uri
from openviking.server.identity import RequestContext
from openviking.service import task_tracker as task_tracker_module
from openviking.service.compile_targets import CompileLifecycle, UpdateSchedule, split_control_args
from openviking.service.external_task_service import (
    ExternalTaskError,
    ExternalTaskService,
    ExternalTaskSnapshot,
    TaskCancelled,
    TaskProgress,
)
from openviking.service.fs_service import FSService
from openviking.service.memory_compile import MemoryCompileRunner
from openviking.service.task_tracker import TaskRecord
from openviking.service.task_tracker_concurrency import KeyedAsyncLockPool
from openviking.session.memory.utils.memory_fields import strip_memory_fields_trailer
from openviking.storage.acl import AclAction
from openviking_cli.exceptions import (
    ConflictError,
    InvalidArgumentError,
    NotFoundError,
    PermissionDeniedError,
    ResourceExhaustedError,
    UnavailableError,
)
from openviking_cli.utils.config.open_viking_config import CompileApiConfig
from openviking_cli.utils.logger import get_logger

logger = get_logger(__name__)

# Task states that occupy a user's Compile capacity.
_ACTIVE_TASK_STATUSES = ("pending", "running", "cancelling")
# Provider-independent args Compile understands; everything else is rejected.
# Control args (mode, auto_update, update_schedule) are split off before these.
# wiki_links is accepted for older clients and queued tasks but no longer has an
# effect: upstream removed navigation processing from the Skill pipeline.
_COMPILE_ARGS = frozenset({"last_compile_time", "wiki_links"})

# Sentinel --skill value that routes a Compile request to memory consolidation
# instead of the Skill pipeline. It is not a real Skill URI.
MEMORY_COMPILE_SKILL = "memory"


class CompileConfigUpdate(BaseModel):
    """Whole update settings for one Compile target (POST /compile/config/update)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    to: str = Field(min_length=1)
    from_: list[str] = Field(alias="from", min_length=1)
    skill: str = Field(min_length=1)
    instruction: str | None = None
    auto_update: bool
    update_schedule: UpdateSchedule | None = None

    @property
    def instruction_sent(self) -> bool:
        return "instruction" in self.model_fields_set


class CompileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: list[str] = Field(default_factory=list, alias="from")
    to: str = Field(min_length=1)
    skill: str = Field(min_length=1)
    instruction: str | None = None
    args: dict[str, Any] | None = None
    # Explicit instruction/reason updates the saved instruction only when the
    # request also configures scheduling; ordinary manual instructions are per-run.
    _instruction_sent: bool = PrivateAttr(default=False)

    @property
    def is_memory_mode(self) -> bool:
        return self.skill == MEMORY_COMPILE_SKILL

    @model_validator(mode="before")
    @classmethod
    def _accept_reason(cls, data: Any) -> Any:
        if isinstance(data, dict) and "reason" in data:
            data = dict(data)
            data.setdefault("instruction", data.pop("reason"))
        return data

    @model_validator(mode="wrap")
    @classmethod
    def _track_instruction(cls, data: Any, handler: Any) -> "CompileRequest":
        model = handler(data)
        if isinstance(data, dict):
            model._instruction_sent = "instruction" in data or "reason" in data
        return model

    @model_validator(mode="after")
    def _normalize(self) -> "CompileRequest":
        sources: list[str] = []
        for source in self.from_:
            normalized = source.strip().rstrip("/")
            if not normalized:
                raise ValueError("from must not contain empty values")
            if normalized not in sources:
                sources.append(normalized)
        self.from_ = sources
        self.to = self.to.strip().rstrip("/")
        self.skill = self.skill.strip().rstrip("/")
        self.instruction = (
            self.instruction.strip() if self.instruction and self.instruction.strip() else None
        )
        self.args = dict(self.args) if self.args else None
        if not self.to:
            raise ValueError("to must not be empty")
        if not self.skill:
            raise ValueError("skill must not be empty")
        # Memory mode consolidates the --to space in place and takes no sources;
        # every other skill still requires at least one --from directory.
        if not self.is_memory_mode and not self.from_:
            raise ValueError("from must contain at least one directory")
        if self.is_memory_mode and self.from_:
            raise ValueError("--skill memory consolidates --to in place and takes no --from")
        return self


class CompileService:
    """Validate Compile requests and run them as durable, queue-backed tasks.

    Like add_resource, a task is a QueueFS message that is acknowledged only after
    its outcome is persisted, so a restart re-runs interrupted tasks from the start.
    """

    task_type = "compile"
    task_id_prefix = "cmp_"

    def __init__(
        self,
        config: CompileApiConfig,
        tasks: ExternalTaskService,
        fs: FSService,
    ) -> None:
        self._config = config
        self._tasks = tasks
        self._fs = fs
        self._memory_runner: MemoryCompileRunner | None = None
        self._service: Any = None
        self._vlm_resolver: Any = None
        self._runner: Any = None
        self._model_concurrency = 1
        self._model_slots: asyncio.Semaphore | None = None
        self._model_slots_loop: asyncio.AbstractEventLoop | None = None
        self._capacity_locks = KeyedAsyncLockPool[tuple[str, str]]()
        self._lifecycle: CompileLifecycle | None = None
        # Keep submission history tasks alive until their storage operations finish.
        self._history_tasks: set[asyncio.Task[None]] = set()

    def configure_lifecycle(self, lifecycle: CompileLifecycle) -> None:
        """Enable target registry, incremental planning and scheduled updates."""
        self._lifecycle = lifecycle

    @property
    def lifecycle(self) -> CompileLifecycle | None:
        return self._lifecycle

    def configure_memory_runner(self, vikingdb: Any = None) -> None:
        """Install the in-process memory-consolidation runner for `--skill memory`."""
        self._memory_runner = MemoryCompileRunner(self._fs, vikingdb=vikingdb)

    def configure_runtime(
        self,
        *,
        service: Any,
        vlm_resolver: Any,
        work_root: Path,
        model_concurrency: int,
    ) -> None:
        """Install the Skill pipeline runtime once the core service is initialized."""
        from openviking.compile.models import CompileLimits
        from openviking.compile.runner import CompileRunner

        if model_concurrency < 1:
            raise ValueError("Compile requires vlm.max_concurrent >= 1")
        limits = CompileLimits(
            source_concurrency=self._config.map_concurrency or model_concurrency,
            shuffle_concurrency=self._config.shuffle_concurrency or model_concurrency,
            shuffle_batch_size=self._config.shuffle_batch_size,
            merge_concurrency=self._config.reduce_concurrency or model_concurrency,
        )
        self._service = service
        self._vlm_resolver = vlm_resolver
        self._model_concurrency = model_concurrency
        self._runner = CompileRunner(limits=limits, work_root=work_root)

    def serialization_key(self, payload: Mapping[str, Any]) -> str:
        return payload["to"]

    def capabilities(self, ctx: RequestContext) -> dict[str, Any]:
        if self._runner is None:
            return {"configured": False, "can_create": False, "reason_code": "NOT_CONFIGURED"}
        return {"configured": True, "can_create": True, "reason_code": None}

    async def create(
        self,
        request: CompileRequest,
        *,
        ctx: RequestContext,
        idempotency_key: str | None = None,
    ) -> TaskRecord | dict[str, Any]:
        """Save explicit update settings synchronously, or queue one immediate Compile run."""
        control, _ = split_control_args(request.args)
        configures_schedule = "auto_update" in control or "update_schedule" in control
        if request.is_memory_mode:
            if configures_schedule:
                raise InvalidArgumentError("Scheduled updates do not support --skill memory")
            if self._memory_runner is None:
                raise UnavailableError(
                    "memory compile", "memory consolidation runner is not configured"
                )
            payload = await self._memory_runner.prepare(
                target=request.to, instruction=request.instruction, ctx=ctx
            )
            if idempotency_key:
                # A retried submission returns its task without counting against capacity.
                existing = await self._tasks.recover_submission(
                    self.task_type, payload, {}, ctx, idempotency_key
                )
                if existing is not None:
                    return existing
            return await self._submit(payload, payload["to"], ctx, idempotency_key)
        request = self._normalize_request_uris(request, ctx)
        self._validate_args(split_control_args(request.args)[1])
        CompileLifecycle.validate_layout(request.to, request.from_)
        if configures_schedule:
            # Explicit update settings are saved without queueing an immediate run.
            lifecycle = self._require_lifecycle()
            normalized = await self._normalize_request(request, ctx)
            submitted = self._payload(normalized)
            control, runtime_args = split_control_args(submitted.get("args"))
            record = await lifecycle.save_submission(
                submitted, control, runtime_args, request._instruction_sent, ctx
            )
            return self._config_view(record)
        if idempotency_key:
            # Recovering an accepted submission needs neither its sources nor the runtime.
            existing = await self._tasks.recover_submission(
                self.task_type, self._payload(request), {}, ctx, idempotency_key
            )
            if existing is not None:
                self._schedule_history(existing)
                return existing
        if self._runner is None:
            raise UnavailableError("compile", "the Compile runtime is not configured")
        normalized = await self._normalize_request(request, ctx)
        submitted = self._payload(normalized)
        payload = submitted
        preparation = None
        if self._lifecycle is not None:
            # Reject at capacity before prepare() saves sources, schedule and key.
            # _submit re-checks under the owner lock; holding that lock across
            # prepare() would invert the scheduler's target-then-owner lock order.
            await self._ensure_capacity(ctx)
            control, runtime_args = split_control_args(submitted.get("args"))
            payload = {key: value for key, value in submitted.items() if key != "args"}
            if runtime_args:
                payload["args"] = runtime_args
            payload["compile"] = {
                "mode": control.get("mode", "incremental"),
                "trigger": "manual",
            }
            # Target state is saved in the background; on_start waits for it.
            preparation = asyncio.create_task(
                self._lifecycle.prepare(submitted, ctx, instruction_set=request._instruction_sent)
            )
        return await self._submit(
            payload,
            ", ".join(normalized.from_),
            ctx,
            idempotency_key,
            submitted=submitted,
            preparation=preparation,
        )

    async def create_scheduled(
        self,
        record: dict[str, Any],
        *,
        ctx: RequestContext,
        connection: Mapping[str, Any],
        idempotency_key: str,
    ) -> TaskRecord:
        """Submit an incremental task from a locked target record (see CompileScheduler).

        ``connection`` carries the scheduler's verified key; in-process tasks run
        as ``ctx`` and do not forward it.
        """
        assert self._lifecycle is not None
        request = CompileRequest.model_validate(
            {
                "from": record["from"],
                "to": record["to"],
                "skill": record["skill"],
                "instruction": record["instruction"],
                "args": {"mode": "incremental", **record["execution_context"]["args"]},
            }
        )
        normalized = await self._normalize_request(self._normalize_request_uris(request, ctx), ctx)
        submitted = self._payload(normalized)
        payload = await self._lifecycle.prepare(
            submitted, ctx, instruction_set=False, scheduled_record=record
        )
        return await self._submit(
            payload,
            ", ".join(normalized.from_),
            ctx,
            idempotency_key,
            submitted=submitted,
            locked_record=record,
        )

    async def _submit(
        self,
        payload: dict[str, Any],
        resource_id: str,
        ctx: RequestContext,
        idempotency_key: str | None,
        *,
        submitted: dict[str, Any] | None = None,
        locked_record: dict[str, Any] | None = None,
        preparation: asyncio.Task[Any] | None = None,
    ) -> TaskRecord:
        """Enqueue work, recording scheduled history before releasing its caller-owned state lock.

        ``submitted`` (default ``payload``) is what idempotent retries must match.
        """
        # Serialize per owner so concurrent submissions cannot all pass the cap.
        async with self._capacity_locks.acquire((ctx.account_id, ctx.user.user_id)):
            await self._ensure_capacity(ctx)
            task = await self._tasks.create(
                self.task_type,
                resource_id=resource_id,
                payload=payload,
                ctx=ctx,
                **(
                    {"idempotency_key": idempotency_key, "submission_payload": submitted}
                    if idempotency_key
                    else {}
                ),
            )
        if self._lifecycle is None or "compile" not in payload:
            return task
        if locked_record is not None:
            await self._lifecycle.record_queued(task, locked_record=locked_record)
        else:
            self._schedule_history(task, preparation=preparation)
        return task

    def _schedule_history(
        self, task: TaskRecord, *, preparation: asyncio.Task[Any] | None = None
    ) -> None:
        """Record history after optional preparation, logging background failures."""
        lifecycle = self._lifecycle
        if lifecycle is None:
            return

        async def record_history() -> None:
            try:
                if preparation is not None:
                    await preparation
                await lifecycle.record_queued(task)
            except Exception:
                logger.exception(
                    "Failed to record Compile submission history task_id=%s", task.task_id
                )

        background = asyncio.create_task(record_history())
        self._history_tasks.add(background)
        background.add_done_callback(self._history_tasks.discard)

    async def on_start(self, task: TaskRecord) -> Any:
        if self._lifecycle is None:
            return "proceed"
        return await self._lifecycle.on_start(task)

    async def on_finish(self, task: TaskRecord, snapshot: ExternalTaskSnapshot) -> Any:
        if self._lifecycle is None:
            return snapshot
        return await self._lifecycle.on_finish(task, snapshot)

    async def run(
        self,
        task: TaskRecord,
        payload: Mapping[str, Any],
        ctx: RequestContext,
        *,
        progress: TaskProgress,
        cancelled: TaskCancelled,
    ) -> dict[str, Any]:
        """Run one Compile attempt in this process; failures raise ExternalTaskError."""
        if payload.get("skill") == MEMORY_COMPILE_SKILL:
            if self._memory_runner is None:
                raise ExternalTaskError("UNAVAILABLE", "Memory compile is not configured")
            await progress("consolidating", {})
            return await self._memory_runner.run(task.task_id, dict(payload), ctx)
        if self._runner is None:
            raise ExternalTaskError("UNAVAILABLE", "The Compile runtime is not configured")
        from openviking.compile.llm import CompileProvider
        from openviking.compile.models import CompileFailure
        from openviking.compile.ov_client import InProcessVikingClient

        try:
            # Tasks queued by older versions skipped today's submit-time checks.
            self._validate_target(payload["to"])
            self._validate_args(payload.get("args"))
            changes = (
                await self._lifecycle.runtime_changes(payload, ctx.account_id, task.task_id)
                if self._lifecycle is not None
                else None
            )
            request = self._sanitized_request(payload, changes)
            vlm = await self._vlm_resolver.get_vlm(ctx.account_id)
            return await self._runner.run(
                task.task_id,
                request,
                client=InProcessVikingClient(
                    self._service,
                    ctx,
                    skill_snapshot=(changes or {}).get("skill_snapshot"),
                    # Lifecycle-managed runs index and version output when they finish.
                    edit_source="compile" if "compile" in payload else None,
                ),
                provider=CompileProvider(vlm, self._slots()),
                progress=progress,
                cancelled=cancelled,
                owner=(ctx.account_id, ctx.user.user_id),
            )
        except InvalidArgumentError as exc:
            raise ExternalTaskError("INVALID_ARGUMENT", str(exc)) from exc
        except CompileFailure as exc:
            raise ExternalTaskError(exc.code, str(exc), result=exc.result) from exc

    # ---------- update settings and run history ----------

    def _require_lifecycle(self) -> CompileLifecycle:
        if self._lifecycle is None:
            raise UnavailableError("compile settings", "Compile target registry is not configured")
        return self._lifecycle

    async def _target(
        self,
        to: str,
        ctx: RequestContext,
        *,
        include_deleted: bool = False,
        action: AclAction = AclAction.READ,
    ) -> dict[str, Any]:
        """Resolve an account's registered target after checking the requested ACL action."""
        lifecycle = self._require_lifecycle()
        target = validate_request_viking_uri(resolve_path_variables(to), ctx, field_name="to")
        await lifecycle._fs._ensure_access(target.rstrip("/"), ctx, action=action)
        record = await lifecycle.store.get_by_to(
            ctx.account_id, target.rstrip("/"), include_deleted=include_deleted
        )
        if record is None:
            raise NotFoundError(to, "compile target")
        return record

    @staticmethod
    def _config_view(record: Mapping[str, Any]) -> dict[str, Any]:
        from openviking.service.compile_scheduler import next_run_at

        return {
            "status": record["status"],
            "to": record["to"],
            "initialized": record["initialized"],
            "initial_actor": record.get("initial_actor"),
            "from": record["from"],
            "skill": record["skill"],
            "instruction": record["instruction"],
            "auto_update": record["auto_update"],
            "update_schedule": record["update_schedule"],
            "next_run_at": next_run_at(dict(record)),
            "last_run": record["last_run"],
            "last_error": record["last_error"],
            "content_updated_at": record.get("content_updated_at"),
            "first_compile_created_at": record.get("first_compile_created_at"),
            "compile_type": record.get("compile_type", "compile"),
            "conflicts_num": record.get("conflicts_num", 0),
        }

    async def get_config(self, to: str, ctx: RequestContext) -> dict[str, Any]:
        return self._config_view(await self._target(to, ctx))

    async def update_config(self, body: "CompileConfigUpdate", ctx: RequestContext) -> dict:
        lifecycle = self._require_lifecycle()
        record = await self._target(body.to, ctx, action=AclAction.WRITE)
        identity = (record["to"], record["deleted_at"])
        request = await self._normalize_request(
            self._normalize_request_uris(
                CompileRequest.model_validate(
                    {"from": body.from_, "to": record["to"], "skill": body.skill}
                ),
                ctx,
            ),
            ctx,
        )
        lifecycle.validate_layout(record["to"], request.from_)
        async with lifecycle.store.edit(ctx.account_id, record["to"]) as record:
            if record["status"] != "active" or (record["to"], record["deleted_at"]) != identity:
                raise ConflictError(
                    "Compile target changed during configuration", resource="COMPILE_TARGET"
                )
            lifecycle.apply_sources(record, request.from_, request.skill)
            if body.instruction_sent:
                record["instruction"] = (body.instruction or "").strip() or None
            await lifecycle.apply_schedule(
                record,
                ctx,
                body.auto_update,
                body.update_schedule.model_dump() if body.update_schedule is not None else None,
            )
            if lifecycle.reschedule is not None:
                await lifecycle.reschedule(ctx.account_id, record, raise_on_error=True)
        return self._config_view(record)

    async def list_configs(
        self, ctx: RequestContext, *, limit: int, cursor: str | None
    ) -> dict[str, Any]:
        """Read active target states lazily in SHA256(to) order, with one readable lookahead."""
        from openviking.service.compile_scheduler import next_run_at

        lifecycle = self._require_lifecycle()
        items = []
        async for item in lifecycle.store.iter_summaries(ctx.account_id, cursor=cursor):
            if item["status"] == "deleted":
                continue
            try:
                await lifecycle._fs._ensure_access(item["to"], ctx)
            except PermissionDeniedError:
                continue
            items.append(
                {
                    "status": item["status"],
                    "to": item["to"],
                    "initialized": item["initialized"],
                    "running": item["running"],
                    "auto_update": item["auto_update"],
                    "update_schedule": item["update_schedule"],
                    "next_run_at": next_run_at(item),
                    "content_updated_at": item.get("content_updated_at"),
                    "first_compile_created_at": item.get("first_compile_created_at"),
                    "compile_type": item.get("compile_type", "compile"),
                    "conflicts_num": item.get("conflicts_num", 0),
                }
            )
            if len(items) > limit:
                break
        page = items[:limit]
        return {
            "targets": page,
            "next_cursor": page[-1]["to"] if len(items) > limit else None,
        }

    async def list_operations(
        self, to: str, ctx: RequestContext, *, limit: int, cursor: str | None
    ) -> dict[str, Any]:
        """Page authorized target operations with public Compile metadata only.

        Common operation fields retain their stored structure. Compile checkpoints
        remain private even when they share the persisted metadata dictionary.
        """
        record = await self._target(to, ctx, include_deleted=True)
        operations = await self._require_lifecycle().store.list_operations(
            ctx.account_id, record["to"], limit=limit + 1, cursor=cursor
        )
        page = operations[:limit]
        public = [self._operation_view(operation) for operation in page]
        next_cursor = page[-1]["operation_id"] if len(operations) > limit else None
        return {"operations": public, "next_cursor": next_cursor}

    @staticmethod
    def _operation_view(operation: Mapping[str, Any]) -> dict[str, Any]:
        """Expose operation fields and public metadata while excluding private checkpoints."""
        return {
            key: operation[key]
            for key in (
                "operation_id",
                "operation_type",
                "actor",
                "created_at",
                "status",
                "started_at",
                "finished_at",
                "params",
                "result",
                "error",
            )
        } | {
            "meta": {
                key: operation["meta"][key]
                for key in (
                    "task_id",
                    "trigger",
                    "execution",
                    "skill_snapshot",
                    "base",
                    "head",
                    "changes",
                )
                if key in operation["meta"]
            },
        }

    async def get_operation(
        self,
        to: str,
        operation_id: str,
        ctx: RequestContext,
    ) -> dict[str, Any]:
        """Read one authorized operation, including deleted targets and public metadata only."""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:._-]{0,127}", operation_id):
            raise InvalidArgumentError("Invalid operation_id")
        record = await self._target(to, ctx, include_deleted=True)
        operation = await self._require_lifecycle().store.get_operation(
            ctx.account_id, record["to"], operation_id
        )
        if operation is None:
            raise NotFoundError(operation_id, "operation")
        return self._operation_view(operation)

    async def operation_outputs(
        self,
        to: str,
        operation_id: str,
        ctx: RequestContext,
        *,
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]:
        """Read one authorized operation's immutable-path version references, ordered by URI."""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:._-]{0,127}", operation_id):
            raise InvalidArgumentError("Invalid operation_id")
        record = await self._target(to, ctx)
        store = self._require_lifecycle().store
        if await store.get_operation(ctx.account_id, record["to"], operation_id) is None:
            raise NotFoundError(operation_id, "operation")
        manifest = await store.get_outputs(ctx.account_id, record["to"], operation_id)
        if manifest is None:
            raise NotFoundError(operation_id, "operation outputs not recorded")
        outputs = sorted(manifest["outputs"], key=lambda item: item["uri"])
        if cursor:
            outputs = [item for item in outputs if item["uri"] > cursor]
        page = outputs[:limit]
        return {"outputs": page, "next_cursor": page[-1]["uri"] if len(outputs) > limit else None}

    async def file_versions(
        self, uri: str, ctx: RequestContext, *, limit: int, before: str | None
    ) -> dict[str, Any]:
        return await self._require_lifecycle().versions.versions(
            uri, ctx, limit=limit, before=before
        )

    async def restore_file_version(
        self, uri: str, restore_version: str, current_version: str, ctx: RequestContext
    ) -> dict[str, Any]:
        """Restore a file version, retaining current metadata for memory files.

        Return version metadata after refresh; mismatches or active Compile raise ConflictError.
        """

        async def write(content: bytes, commit_content: Any) -> None:
            # Use normal refresh while recording a restore version.
            try:
                body: str | bytes = content.decode("utf-8")
            except UnicodeDecodeError:
                body = content
            if isinstance(body, str) and classify_uri(uri).is_memory:
                body = strip_memory_fields_trailer(body)
            await self._fs.write(
                uri,
                body,
                ctx,
                edit_source="compile",
                commit_content=commit_content,
            )

        return await self._require_lifecycle().versions.restore(
            uri=uri,
            restore_version=restore_version,
            current_version=current_version,
            ctx=ctx,
            write=write,
        )

    async def _ensure_capacity(self, ctx: RequestContext) -> None:
        """Bound queued work per user; each queued task also re-runs after a restart.

        Only tasks with live queue work count. Records left active by older
        versions or by a lost outcome write never run again, and must not lock
        the user out; cancelling them settles them immediately.
        """
        limit = self._config.max_active_tasks_per_user
        tracker = task_tracker_module.get_task_tracker()
        owner = {"account_id": ctx.account_id, "user_id": ctx.user.user_id}
        active = 0
        for status in _ACTIVE_TASK_STATUSES:
            for task in await tracker.list_tasks(
                task_type=self.task_type, status=status, limit=None, **owner
            ):
                if await tracker.has_work(task.task_id, **owner):
                    active += 1
        if active >= limit:
            raise ResourceExhaustedError(
                f"Too many active Compile tasks ({active}); wait for some to finish",
                details={"limit": limit},
            )

    async def purge_scratch(self, account_id: str, user_id: str | None = None) -> None:
        """Remove Compile scratch (source copies) of a deleted user or account."""
        if self._runner is not None:
            await asyncio.to_thread(self._runner.purge_owner, account_id, user_id)

    def _slots(self) -> asyncio.Semaphore:
        """Share model-call capacity across Compile tasks on the worker's event loop."""
        loop = asyncio.get_running_loop()
        if self._model_slots is None or self._model_slots_loop is not loop:
            self._model_slots = asyncio.Semaphore(self._model_concurrency)
            self._model_slots_loop = loop
        return self._model_slots

    @staticmethod
    def _payload(request: CompileRequest) -> dict[str, Any]:
        return request.model_dump(mode="json", by_alias=True, exclude_none=True)

    @staticmethod
    def _validate_args(args: Mapping[str, Any] | None) -> None:
        from openviking.compile.runner import compile_time

        args = args or {}
        unknown = sorted(set(args) - _COMPILE_ARGS)
        if unknown:
            raise InvalidArgumentError(f"Unsupported Compile args: {', '.join(unknown)}")
        if not isinstance(args.get("wiki_links", False), bool):
            raise InvalidArgumentError("args.wiki_links must be a boolean")
        if "last_compile_time" in args:
            try:
                compile_time(args["last_compile_time"])
            except ValueError as exc:
                raise InvalidArgumentError(
                    "args.last_compile_time must be an ISO timestamp or Unix time"
                ) from exc

    @staticmethod
    def _sanitized_request(
        payload: Mapping[str, Any], changes: Mapping[str, Any] | None = None
    ) -> Any:
        from openviking.compile.models import DEFAULT_COMPILE_INSTRUCTION, SanitizedCompileRequest
        from openviking.compile.runner import compile_time

        args = payload.get("args") or {}
        instruction = (payload.get("instruction") or "").strip()
        if changes is not None:
            _validate_changes(changes, list(payload["from"]), payload["skill"])
        return SanitizedCompileRequest(
            **{
                "from": list(payload["from"]),
                "to": payload["to"],
                "instruction": instruction or DEFAULT_COMPILE_INSTRUCTION,
                "instruction_provided": bool(instruction),
                "skill": payload["skill"],
                # A kernel change plan supersedes the modification-time cutoff.
                "last_compile_time": (
                    compile_time(args["last_compile_time"])
                    if "last_compile_time" in args and changes is None
                    else None
                ),
                "changes": dict(changes) if changes is not None else None,
            }
        )

    def _normalize_request_uris(
        self, request: CompileRequest, ctx: RequestContext
    ) -> CompileRequest:
        """Normalize identity-bound names without requiring live resources."""
        sources = list(
            dict.fromkeys(
                validate_request_viking_uri(
                    resolve_path_variables(source), ctx, field_name=f"from[{index}]"
                ).rstrip("/")
                for index, source in enumerate(request.from_)
            )
        )
        for source in sources:
            if classify_uri(source).is_system:
                raise InvalidArgumentError("Compile source must not be in the system namespace")
        skill = request.skill.removesuffix("/SKILL.md")
        skill = validate_request_viking_uri(
            resolve_path_variables(skill), ctx, field_name="skill"
        ).rstrip("/")
        if not classify_uri(skill).is_skill_root:
            raise InvalidArgumentError("skill must resolve to a Skill directory or SKILL.md")
        target = validate_request_viking_uri(
            resolve_path_variables(request.to), ctx, field_name="to"
        ).rstrip("/")
        self._validate_target(target)
        return request.model_copy(update={"from_": sources, "to": target, "skill": skill})

    async def _normalize_request(
        self, request: CompileRequest, ctx: RequestContext
    ) -> CompileRequest:
        request = self._normalize_request_uris(request, ctx)
        for uri in request.from_:
            stat = await self._fs.stat(uri, ctx, skip_count=True)
            if not stat.get("isDir"):
                raise InvalidArgumentError(f"Compile source must be a directory: {uri}")
        skill_stat = await self._fs.stat(request.skill, ctx, skip_count=True)
        if not skill_stat.get("isDir"):
            raise InvalidArgumentError("skill must resolve to a Skill directory or SKILL.md")
        skill_file = await self._fs.stat(f"{request.skill}/SKILL.md", ctx, skip_count=True)
        if skill_file.get("isDir"):
            raise InvalidArgumentError("Skill directory must contain a SKILL.md file")
        await self._fs.ensure_write_access(request.to, ctx)
        try:
            target_stat = await self._fs.stat(request.to, ctx, skip_count=True)
        except NotFoundError:
            pass
        else:
            if not target_stat.get("isDir"):
                raise InvalidArgumentError("Compile target must be a directory")
        return request

    @staticmethod
    def _validate_target(target: str) -> None:
        classification = classify_uri(target)
        parts = uri_parts(target)
        if classification.is_system:
            raise InvalidArgumentError("Compile target must not be in the system namespace")
        if classification.context_type == "skill":
            if (
                not classification.is_skill_namespace
                or classification.scope not in {"user", "agent"}
                or (classification.scope == "agent" and parts != ["agent", "skills"])
            ):
                raise InvalidArgumentError(
                    "Compile Skill target must be a supported skills namespace"
                )
            return
        if classification.context_type == "memory":
            raise InvalidArgumentError(
                "Skill Compile cannot target memory directories; use --skill memory"
            )
        if classification.context_type != "resource":
            raise InvalidArgumentError("Compile target must be a resource or skills directory")
        if parts == ["resources"] or (
            classification.content_index is not None
            and len(parts) <= classification.content_index + 1
        ):
            raise InvalidArgumentError("Compile target must be inside a resource directory")


def _validate_changes(changes: Mapping[str, Any], sources: list[str], skill: str) -> None:
    """Reject a malformed kernel change plan before any model call.

    The directory plan must partition the request's sources; diff_dirs need an
    incremental base/head, and a missing head snapshot requires full execution.
    """
    from openviking.compile.models import CompileFailure, has_directory_plan

    def invalid(message: str) -> CompileFailure:
        return CompileFailure("INVALID_ARGUMENT", message, stage="queued")

    execution = changes.get("execution") if isinstance(changes, Mapping) else None
    valid = (
        has_directory_plan(dict(changes))
        and "base" in changes
        and "head" in changes
        and all(
            isinstance(changes[key], list)
            and all(isinstance(uri, str) and uri.strip() for uri in changes[key])
            for key in ("diff_dirs", "full_dirs")
        )
        and all(
            changes.get(key) is None or (isinstance(changes[key], str) and changes[key].strip())
            for key in ("base", "head")
        )
        and isinstance(execution, Mapping)
        and execution.get("mode") in ("full", "incremental")
    )
    if not valid:
        raise invalid("Invalid args.changes directory plan")
    if changes["diff_dirs"] and (
        not changes.get("base") or not changes.get("head") or execution["mode"] == "full"
    ):
        raise invalid("diff_dirs require incremental base/head")
    if not changes.get("head") and execution["mode"] != "full":
        raise invalid("Unavailable snapshots require full execution")
    diff_dirs, full_dirs = changes["diff_dirs"], changes["full_dirs"]
    if set(diff_dirs) & set(full_dirs) or set(diff_dirs + full_dirs) != set(sources):
        raise invalid("Directory plan must partition the canonical from list")
    snapshot = changes.get("skill_snapshot")
    if snapshot is not None and (not isinstance(snapshot, Mapping) or snapshot.get("uri") != skill):
        raise CompileFailure("SKILL_INVALID", "Invalid Compile Skill snapshot", stage="agent")


__all__ = [
    "CompileConfigUpdate",
    "CompileRequest",
    "CompileService",
]
