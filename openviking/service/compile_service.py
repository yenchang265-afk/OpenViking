# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Compile API models and the in-process, queue-backed Compile executor."""

from __future__ import annotations

import asyncio
import base64
import json
import re
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from openviking.concurrency import bounded_map
from openviking.core.identifiers import validate_user_id
from openviking.core.namespace import classify_uri, uri_parts
from openviking.core.path_variables import resolve_path_variables
from openviking.core.uri_validation import validate_request_viking_uri
from openviking.pyagfs.exceptions import AGFSInternalError
from openviking.server.identity import RequestContext, Role
from openviking.service.compile_targets import (
    CompileLifecycle,
    CompileName,
    UpdateSchedule,
    execution_signature,
    is_versioned,
    new_record,
    parse_schedule,
    split_control_args,
    validate_compile_name,
)
from openviking.service import task_tracker as task_tracker_module
from openviking.service.external_task_service import (
    ENQUEUE_FAILURE,
    ExternalTaskError,
    ExternalTaskService,
    ExternalTaskSnapshot,
    TaskCancelled,
    TaskProgress,
)
from openviking.service.fs_service import FSService
from openviking.service.memory_compile import MemoryCompileRunner
from openviking.service.task_domain import sanitize_task_result
from openviking.service.task_tracker import TaskRecord
from openviking.service.task_tracker_concurrency import KeyedAsyncLockPool
from openviking.storage.acl import AclAction
from openviking.utils.path_safety import normalize_storage_target_uri
from openviking_cli.exceptions import (
    FailedPreconditionError,
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
# Skill execution args in-server Compile understands; everything else is rejected.
# wiki_links is accepted for older clients and queued tasks but no longer has an
# effect: upstream removed navigation processing from the Skill pipeline. Scheduling
# controls are split off and configuration ownership is removed before this check;
# mode, last_compile_time and changes are server-owned (see split_control_args).
_COMPILE_ARGS = frozenset({"wiki_links"})

# Sentinel --skill value that routes a Compile request to memory consolidation
# instead of the Skill pipeline. It is not a real Skill URI.
MEMORY_COMPILE_SKILL = "memory"


def _lost_state_lease(error: AGFSInternalError | ValueError) -> bool:
    """Match lease loss, requiring chained write and release errors to name the same lease."""
    release = None
    write: BaseException = error
    if isinstance(error, ValueError):
        release = re.fullmatch(
            r"invalid lock request: owned lease capability does not match ref '([^']+)'", str(error)
        )
        if release is None:
            return False
        if error.__context__ is None:
            return True
        write = error.__context__
    if not isinstance(write, AGFSInternalError):
        return False
    lost = re.fullmatch(
        r"internal error: (?:encrypted write lock context error|lock lease error): "
        r"invalid lock request: unknown pathlock lease ref '([^']+)'",
        str(write),
    )
    return lost is not None and (release is None or release[1] == lost[1])


class CompileInputs(BaseModel):
    """Complete compile inputs; scheduling controls are accepted only when saving a configuration."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: list[str] = Field(default_factory=list, alias="from")
    to: str = Field(min_length=1)
    skill: str = Field(min_length=1)
    instruction: str | None = None
    args: dict[str, Any] | None = None

    @property
    def is_memory_mode(self) -> bool:
        return self.skill == MEMORY_COMPILE_SKILL

    @model_validator(mode="after")
    def _normalize(self) -> "CompileInputs":
        sources: list[str] = []
        for source in self.from_:
            normalized = source.strip().rstrip("/")
            if not normalized:
                raise ValueError("from must not contain empty values")
            if normalized not in sources:
                sources.append(normalized)
        self.from_ = sources
        if self.to is not None:
            self.to = self.to.strip().rstrip("/")
        self.skill = self.skill.strip().rstrip("/")
        self.instruction = (
            self.instruction.strip() if self.instruction and self.instruction.strip() else None
        )
        self.args = dict(self.args) if self.args else None
        reserved = {"mode", "last_compile_time", "changes"}.intersection(self.args or {})
        if reserved:
            raise ValueError(
                f"Compile execution controls are server-owned: {', '.join(sorted(reserved))}"
            )
        if self.to is not None and not self.to:
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


class CompileCreateRequest(CompileInputs):
    """Save complete inputs under a caller-supplied configuration name unique to its creator within the account."""

    compile_name: CompileName = Field(
        description="Case-sensitive name using Han characters, ASCII letters, digits, underscores or hyphens, with no leading hyphen. Maximum length: 64 characters for ASCII-only names, 32 for names containing Han characters.",
    )


class CompileRequest(BaseModel):
    """Execute saved inputs for an optional owner, or full one-off inputs."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    compile_name: CompileName | None = Field(
        default=None,
        description="Saved configuration name; omit for a one-off execution with complete inputs.",
    )
    from_: list[str] = Field(default_factory=list, alias="from")
    to: str | None = None
    skill: str | None = None
    instruction: str | None = None
    args: dict[str, Any] | None = Field(
        default=None,
        description="Named runs use only owner_user_id; other args are ignored.",
    )

    @property
    def is_memory_mode(self) -> bool:
        return self.skill == MEMORY_COMPILE_SKILL

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        """Check the request shape before parsing fields and normalize one-off execution inputs."""
        if not isinstance(data, Mapping):
            return data
        if "compile_name" in data:
            if set(data) - {"compile_name", "args"}:
                raise ValueError(
                    "To run a saved configuration, send compile_name and optional args.owner_user_id "
                    "to POST /api/v1/compile. "
                    "Save the execution inputs with compile_name using POST /api/v1/compile/create. "
                    "See https://docs.openviking.ai/en/api/23-agent-runtime"
                )
            if data["compile_name"] is None:
                raise ValueError("compile_name must not be null")
            args = data.get("args")
            if args is not None:
                if not isinstance(args, Mapping):
                    raise ValueError("Named Compile args must be a JSON object")
                if "owner_user_id" in args:
                    error = validate_user_id(args["owner_user_id"])
                    if error:
                        raise ValueError(f"Invalid args.owner_user_id: {error}")
                data = {**data, "args": {k: args[k] for k in ("owner_user_id",) if k in args}}
            return data
        inputs = CompileInputs.model_validate(data)
        if "owner_user_id" in (inputs.args or {}):
            raise ValueError("args.owner_user_id requires compile_name")
        scheduling = {"auto_update", "update_schedule"}.intersection(inputs.args or {})
        if scheduling:
            raise ValueError(
                f"ov compile (POST /api/v1/compile) does not accept scheduling options "
                f"{', '.join(sorted(scheduling))}. Remove them from args for a one-off run. "
                "To schedule a new configuration, use 'ov compile create --compile-name <name>' "
                "or POST /api/v1/compile/create with these options in args. "
                "For an existing configuration, send them as top-level fields "
                "to POST /api/v1/compile/config/update. "
                "See https://docs.openviking.ai/en/api/23-agent-runtime"
            )
        return inputs.model_dump(by_alias=True)


class CompileConfigUpdate(CompileCreateRequest):
    """Replace a named configuration while keeping its output directory and execution timestamps."""

    to: str | None = Field(
        default=None,
        min_length=1,
        description="Output directory; omission or null preserves the saved directory.",
    )
    auto_update: bool
    update_schedule: UpdateSchedule | None = None
    updated_by: str | None = Field(
        default=None, description="User credited with this update. Defaults to the requesting user."
    )


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
        self._scheduler: Any = None

    def configure_lifecycle(self, lifecycle: CompileLifecycle) -> None:
        """Install persistent configurations and recoverable full/incremental execution."""
        self._lifecycle = lifecycle

    @property
    def lifecycle(self) -> CompileLifecycle | None:
        return self._lifecycle

    def configure_memory_runner(
        self,
        vikingdb: Any = None,
        *,
        runtime_config_manager: Any = None,
        vlm_resolver=None,
    ) -> None:
        """Install the in-process memory-consolidation runner for `--skill memory`."""
        self._memory_runner = MemoryCompileRunner(
            self._fs,
            vikingdb=vikingdb,
            runtime_config_manager=runtime_config_manager,
            vlm_resolver=vlm_resolver,
        )

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

    def configure_scheduler(self, scheduler: Any) -> None:
        """Install scheduling for saved configurations; execution remains available without it."""
        self._scheduler = scheduler

    async def _encrypt_private_args(
        self, account_id: str, private: dict[str, Any]
    ) -> dict[str, str]:
        """Encrypt private input subtrees; configuration state contains only their ciphertext."""
        try:
            encrypted = await self._tasks._credential_encryptor().encrypt(
                account_id, json.dumps(private, ensure_ascii=False).encode()
            )
        except Exception as exc:
            raise FailedPreconditionError("Cannot encrypt Compile configuration inputs") from exc
        return {"ciphertext": base64.b64encode(encrypted).decode("ascii")}

    async def _private_args(self, account_id: str, value: Mapping[str, Any]) -> dict[str, Any]:
        """Decrypt saved private inputs only for authenticated execution, never for public views."""
        if not value:
            return {}
        try:
            ciphertext = base64.b64decode(value["ciphertext"], validate=True)
            plaintext = await self._tasks._credential_encryptor().decrypt(account_id, ciphertext)
            decoded = json.loads(plaintext)
            if not isinstance(decoded, dict) or not isinstance(decoded.get("args"), dict):
                raise ValueError("Invalid private Compile inputs")
            return decoded
        except Exception as exc:
            raise FailedPreconditionError("Cannot decrypt Compile configuration inputs") from exc

    async def _configure_schedule(
        self, record: dict[str, Any], ctx: RequestContext, auto_update: bool, schedule: dict | None
    ) -> None:
        """Validate credentials and calculate the first future slot without submitting work."""
        from datetime import datetime

        from openviking.service.compile_scheduler import TZ, next_slot

        changed = auto_update != record["auto_update"] or schedule != record["update_schedule"]
        if auto_update:
            if schedule is None:
                raise InvalidArgumentError("update_schedule is required when auto_update is true")
            if self._scheduler is None or self._scheduler._expiry is None:
                raise FailedPreconditionError("Scheduled Compile requires a configured scheduler")
            record["execution_context"]["credential"] = await self._scheduler.save_credential(ctx)
            if changed or record["next_triggered_slot"] is None:
                record["next_triggered_slot"] = next_slot(schedule, datetime.now(TZ)).isoformat()
                record["last_triggered_slot"] = None
        else:
            record["execution_context"]["credential"] = None
            record["next_triggered_slot"] = None
        record["auto_update"] = auto_update
        record["update_schedule"] = schedule

    async def _settings(
        self, request: CompileInputs, ctx: RequestContext, owner_user_id: str, compile_name: str
    ) -> dict[str, Any]:
        """Save the caller's executor identity independently of scheduling."""
        if request.is_memory_mode:
            raise InvalidArgumentError("Persistent Compile does not support skill=memory")
        normalized = await self._normalize_request(request, ctx)
        CompileLifecycle.validate_layout(normalized.to, normalized.from_)
        public, private = self._split_payload(normalized)
        control, runtime_args = split_control_args(public.get("args"))
        # Configuration ownership does not enter the Skill's execution arguments.
        runtime_args.pop("owner_user_id", None)
        schedule = control.get("update_schedule")
        if schedule is not None:
            schedule = parse_schedule(schedule, (ctx.account_id, owner_user_id, compile_name))
        public["args"] = runtime_args
        record = new_record(
            public,
            execution_context={
                "executor": {
                    "account_id": ctx.account_id,
                    "user_id": ctx.user.user_id,
                    "role": str(ctx.role),
                    "group_ids": list(ctx.group_ids),
                }
            },
        )
        if private:
            record["execution_context"]["private_args"] = await self._encrypt_private_args(
                ctx.account_id, private
            )
        await self._configure_schedule(
            record, ctx, control.get("auto_update", schedule is not None), schedule
        )
        return record

    async def create_compile_task(
        self, request: CompileCreateRequest, *, ctx: RequestContext
    ) -> dict[str, str]:
        """Save configuration and enqueue target tagging without executing Compile or snapshots."""
        lifecycle = self._require_lifecycle()
        compile_name = validate_compile_name(request.compile_name)
        owner_user_id = (request.args or {}).get("owner_user_id", ctx.user.user_id)
        record = await self._settings(request, ctx, owner_user_id, compile_name)

        async def prepare_target_and_schedule() -> None:
            await self._fs.ensure_compile_target(record["to"], ctx)
            if self._scheduler is not None:
                await self._scheduler.reschedule(
                    ctx.account_id, owner_user_id, compile_name, record, raise_on_error=True
                )

        await lifecycle.store.create(
            ctx.account_id,
            owner_user_id,
            record,
            compile_name=compile_name,
            before_publish=prepare_target_and_schedule,
        )
        return {"compile_name": compile_name}

    async def create(
        self,
        request: CompileRequest,
        *,
        connection: Mapping[str, Any] | None = None,
        ctx: RequestContext,
        idempotency_key: str | None = None,
        trigger: str = "manual",
        locked_record: dict[str, Any] | None = None,
        scheduled_slot: str | None = None,
    ) -> TaskRecord:
        """Execute frozen configuration inputs or a full request; scheduled callers share this path.

        ``locked_record`` is supplied only by the scheduler while it owns the configuration lock.
        Submission retries recover the original task and do not refresh its invocation timestamps.
        New executions require a search-visible target tag before task creation and enqueueing.
        In-process tasks run as ``ctx``; ``connection`` is accepted for callers that still
        forward one and is not used.
        """
        if trigger not in {"manual", "scheduled"}:
            raise InvalidArgumentError("Invalid Compile trigger")
        if request.is_memory_mode:
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
            async with self._capacity_locks.acquire((ctx.account_id, ctx.user.user_id)):
                await self._ensure_capacity(ctx)
                return await self._tasks.create(
                    self.task_type,
                    resource_id=payload["to"],
                    payload=payload,
                    ctx=ctx,
                    idempotency_key=idempotency_key,
                )
        compile_name = request.compile_name
        owner_user_id = (request.args or {}).get("owner_user_id", ctx.user.user_id)
        if compile_name and locked_record is None:
            lifecycle = self._require_lifecycle()
            await lifecycle.store.require_config_exists(ctx.account_id, owner_user_id, compile_name)
            task = None
            try:
                async with lifecycle.store.edit(
                    ctx.account_id, owner_user_id, compile_name
                ) as record:
                    await lifecycle._fs._ensure_access(record["to"], ctx, action=AclAction.WRITE)
                    task = await self.create(
                        request,
                        connection=connection,
                        ctx=ctx,
                        idempotency_key=idempotency_key,
                        trigger=trigger,
                        locked_record=record,
                        scheduled_slot=scheduled_slot,
                    )
            except (AGFSInternalError, ValueError) as exc:
                if task is None or task.error == ENQUEUE_FAILURE or not _lost_state_lease(exc):
                    raise
                logger.warning(
                    "Queued Compile task %s lost the state.json lease for %s",
                    task.task_id,
                    compile_name,
                    exc_info=True,
                )
            return task
        if compile_name:
            record = locked_record
            inputs = CompileInputs.model_validate(
                {key: record[key] for key in ("from", "to", "skill", "instruction", "args")}
            )
            submitted, submitted_private = {"compile_name": compile_name}, {}
            # Omitted and explicit self owners share a retry identity.
            if owner_user_id != ctx.user.user_id:
                submitted["args"] = {"owner_user_id": owner_user_id}
        else:
            record = None
            inputs = self._normalize_request_uris(request, ctx)
            submitted, submitted_private = self._split_payload(inputs)
        if idempotency_key:
            existing = await self._tasks.recover_submission(
                self.task_type, submitted, submitted_private, ctx, idempotency_key
            )
            if existing is not None:
                if compile_name:
                    await self._require_lifecycle().record_queued(
                        existing, locked_record=locked_record
                    )
                return existing
        if self._runner is None:
            raise UnavailableError("compile", "the Compile runtime is not configured")
        self._validate_args(split_control_args(inputs.args)[1])
        normalized = await self._normalize_request(inputs, ctx)
        assert normalized.to is not None
        CompileLifecycle.validate_layout(normalized.to, normalized.from_)
        payload, private_payload = self._split_payload(normalized)
        payload["compile"] = {"trigger": trigger}
        if trigger == "scheduled":
            payload["compile"]["scheduled_slot"] = scheduled_slot
        if record is not None:
            private_payload = await self._private_args(
                ctx.account_id, record["execution_context"].get("private_args") or {}
            )
            payload["compile"].update(
                compile_name=compile_name,
                owner_user_id=record["execution_context"]["owner_user_id"],
                auto_update=record["auto_update"],
                update_schedule=record["update_schedule"],
                input_signature=execution_signature(record),
            )

        async def record_created(task: TaskRecord) -> None:
            await self._require_lifecycle().record_queued(task, locked_record=locked_record)

        await self._fs.ensure_compile_target(normalized.to, ctx)
        # Serialize per owner so concurrent submissions cannot all pass the cap.
        async with self._capacity_locks.acquire((ctx.account_id, ctx.user.user_id)):
            await self._ensure_capacity(ctx)
            # Private task state retains the executor's role and groups for asynchronous
            # filesystem access; in-process execution forwards no credentials.
            return await self._tasks.create(
                self.task_type,
                resource_id=", ".join(normalized.from_),
                payload=payload,
                private_payload=private_payload,
                connection={"role": str(ctx.role), "group_ids": list(ctx.group_ids)},
                ctx=ctx,
                idempotency_key=idempotency_key,
                submission_payload=submitted if idempotency_key else None,
                submission_private_payload={} if compile_name else None,
                on_task_created=record_created if compile_name else None,
                retry_enqueue=trigger == "scheduled",
            )

    async def on_start(self, task: TaskRecord) -> str | ExternalTaskSnapshot | None:
        if self._lifecycle is None:
            return "proceed"
        return await self._lifecycle.on_start(task)

    async def on_finish(
        self,
        task: TaskRecord,
        snapshot: ExternalTaskSnapshot,
    ) -> ExternalTaskSnapshot:
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
            self._validate_args(split_control_args(payload.get("args"))[1])
            changes = (
                await self._lifecycle.runtime_changes(
                    payload, ctx.account_id, task.task_id, user_id=task.user_id
                )
                if self._lifecycle is not None and "compile" in payload
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

    # ---------- saved configurations and run history ----------

    def _require_lifecycle(self) -> CompileLifecycle:
        if self._lifecycle is None:
            raise UnavailableError("compile settings", "Compile lifecycle is not configured")
        return self._lifecycle

    async def _configuration(
        self,
        compile_name: str,
        ctx: RequestContext,
        *,
        action: AclAction | None = AclAction.READ,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        """Load the selected owner's config. An action of None checks ownership scope only."""
        validate_compile_name(compile_name)
        lifecycle = self._require_lifecycle()
        record = await lifecycle.store.get(
            ctx.account_id,
            ctx.user.user_id if owner_user_id is None else owner_user_id,
            compile_name,
        )
        if record is None:
            raise NotFoundError(compile_name, "compile configuration")
        if action is not None:
            await lifecycle._fs._ensure_access(record["to"], ctx, action=action)
        return record

    @staticmethod
    def _config_view(compile_name: str, record: Mapping[str, Any]) -> dict[str, Any]:
        """Expose configuration inputs and invocation/slot times without private execution context."""
        fields = (
            "from",
            "to",
            "skill",
            "instruction",
            "args",
            "auto_update",
            "update_schedule",
            "task_first_create_time",
            "last_run_time",
            "last_triggered_slot",
            "next_triggered_slot",
        )
        return {"compile_name": compile_name, **{key: record[key] for key in fields}}

    async def get_config(self, compile_name: str, ctx: RequestContext) -> dict[str, Any]:
        return self._config_view(
            compile_name, await self._configuration(compile_name, ctx, action=None)
        )

    async def update_config(self, body: CompileConfigUpdate, ctx: RequestContext) -> dict[str, Any]:
        """Replace mutable settings under the state lock; target changes raise InvalidArgumentError."""
        from copy import deepcopy

        configuration = await self._configuration(
            body.compile_name,
            ctx,
            action=AclAction.WRITE,
            owner_user_id=(body.args or {}).get("owner_user_id", ctx.user.user_id),
        )
        if body.to is None:
            body = body.model_copy(update={"to": configuration["to"]})
        target = self._normalize_request_uris(body, ctx).to
        if target != configuration["to"]:
            raise InvalidArgumentError("to must match the saved compile configuration's directory")
        owner_user_id = configuration["execution_context"]["owner_user_id"]
        args = dict(body.args or {})
        if {"auto_update", "update_schedule"}.intersection(args):
            raise InvalidArgumentError(
                "Use top-level scheduling fields when updating a configuration"
            )
        args.update(
            auto_update=body.auto_update,
            update_schedule=body.update_schedule or configuration["update_schedule"],
        )
        inputs = CompileInputs.model_validate(
            {
                "from": body.from_,
                "to": target,
                "skill": body.skill,
                "instruction": body.instruction,
                "args": args,
            }
        )
        replacement = await self._settings(inputs, ctx, owner_user_id, body.compile_name)
        await self._fs.ensure_compile_target(replacement["to"], ctx)
        lifecycle = self._require_lifecycle()
        async with lifecycle.store.edit(ctx.account_id, owner_user_id, body.compile_name) as record:
            await lifecycle._fs._ensure_access(record["to"], ctx, action=AclAction.WRITE)
            replacement = deepcopy(replacement)
            replacement["updated_by"] = (
                ctx.user.user_id if body.updated_by is None else body.updated_by
            )
            replacement["execution_context"]["owner_user_id"] = owner_user_id
            old_private = await self._private_args(
                ctx.account_id, record["execution_context"].get("private_args") or {}
            )
            new_private = await self._private_args(
                ctx.account_id, replacement["execution_context"].get("private_args") or {}
            )
            retained = dict(new_private.get("args") or {})
            for key, value in (old_private.get("args") or {}).items():
                if key in retained:
                    continue
                if key in record["args"] and replacement["args"].get(key) != record["args"][key]:
                    if key in replacement["args"]:
                        raise InvalidArgumentError(
                            f"Changing args.{key} requires resubmitting its private fields"
                        )
                    continue
                retained[key] = value
            merged_private = {"args": retained} if retained else {}
            if merged_private == old_private:
                replacement["execution_context"]["private_args"] = record["execution_context"].get(
                    "private_args"
                )
            elif merged_private:
                replacement["execution_context"]["private_args"] = await self._encrypt_private_args(
                    ctx.account_id, merged_private
                )
            else:
                replacement["execution_context"].pop("private_args", None)
            for field in ("task_first_create_time", "last_run_time"):
                replacement[field] = record[field]
            if (record["auto_update"], record["update_schedule"]) == (
                replacement["auto_update"],
                replacement["update_schedule"],
            ):
                for field in ("last_triggered_slot", "next_triggered_slot"):
                    replacement[field] = record[field]
            replacement["progress"] = record["progress"]
            if self._scheduler is not None:
                await self._scheduler.reschedule(
                    ctx.account_id,
                    owner_user_id,
                    body.compile_name,
                    replacement,
                    raise_on_error=True,
                )
            record.clear()
            record.update(replacement)
        return self._config_view(body.compile_name, record)

    async def list_configs(
        self,
        ctx: RequestContext,
        *,
        limit: int,
        cursor: str | None,
        scope: str = "user",
        compile_name: str | None = None,
    ) -> dict[str, Any]:
        """Page configurations by owner within the caller's account. Account scope requires ADMIN."""
        if scope not in {"user", "account"}:
            raise InvalidArgumentError("scope must be user or account")
        if scope == "account" and ctx.role != Role.ADMIN:
            raise PermissionDeniedError("Account Compile listing requires ADMIN")
        if compile_name is not None:
            validate_compile_name(compile_name)
        if cursor is not None:
            if scope == "user":
                validate_compile_name(cursor)
            elif ":" not in cursor:
                raise InvalidArgumentError("Account Compile cursor must include an owner")
        lifecycle = self._require_lifecycle()
        items = []
        async for name, record in lifecycle.store.iter_records(
            ctx.account_id,
            user_id=ctx.user.user_id if scope == "user" else None,
            cursor=cursor,
            compile_name=compile_name,
        ):
            context = record["execution_context"]
            items.append(
                {
                    **self._config_view(name, record),
                    "owner_user_id": context["owner_user_id"],
                    "executor_user_id": (context.get("executor") or {}).get("user_id"),
                    "updated_by": record.get("updated_by"),
                }
            )
            if len(items) > limit:
                break
        page = items[:limit]
        next_cursor = None
        if len(items) > limit:
            next_cursor = page[-1]["compile_name"]
            if scope == "account":
                next_cursor += ":" + page[-1]["owner_user_id"]
        # shortcut: time ordering is page-local, use time cursors when global ordering is required.
        page.sort(
            key=lambda item: (item["last_run_time"] is not None, item["last_run_time"]),
            reverse=True,
        )
        return {
            "configs": page,
            "next_cursor": next_cursor,
        }

    async def list_runs(
        self, compile_name: str, ctx: RequestContext, *, limit: int, cursor: str | None
    ) -> dict[str, Any]:
        """Page the caller's run history."""
        runs = await self._require_lifecycle().store.list_runs(
            ctx.account_id, ctx.user.user_id, compile_name, cursor=cursor, limit=limit + 1
        )
        page = runs[:limit]
        return {"runs": page, "next_cursor": page[-1]["task_id"] if len(runs) > limit else None}

    async def get_run(self, compile_name: str, task_id: str, ctx: RequestContext) -> dict[str, Any]:
        """Return the caller's frozen run, raising NotFoundError when the run is absent."""
        run = await self._require_lifecycle().store.get_run(
            ctx.account_id, ctx.user.user_id, compile_name, task_id
        )
        if run is None:
            raise NotFoundError(task_id, "compile run")
        return run

    async def run_outputs(
        self,
        compile_name: str,
        task_id: str,
        ctx: RequestContext,
        *,
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]:
        """Page authorized run outputs with each file's latest commit, or null for no history."""
        run = await self.get_run(compile_name, task_id, ctx)
        start, finish = run["meta"]["start_snapshot"], run["meta"]["finish_snapshot"]
        if not start or not finish:
            return {"outputs": [], "next_cursor": None}
        fs = self._require_lifecycle()._fs
        changes = await fs.diff_paths(dirs=[run["params"]["to"]], base=start, head=finish, ctx=ctx)
        outputs = [
            {"uri": item["uri"], "snapshot_id": finish, "change_type": item["change_type"]}
            for item in sorted(changes, key=lambda item: item["uri"])
            if item["change_type"] != "deleted"
            and is_versioned(item["uri"])
            and (not cursor or item["uri"] > cursor)
        ]
        allowed = await fs._can_access_many([item["uri"] for item in outputs], ctx)
        outputs = [item for item in outputs if allowed.get(item["uri"], False)]
        page = outputs[:limit]

        async def fill_latest_snapshot(item: dict[str, Any]) -> None:
            """Set an output's latest commit in place, using None for no history; errors propagate."""
            history = await fs.log(ctx=ctx, paths=[item["uri"]], limit=1)
            item["latest_snapshot_id"] = history[0]["oid"] if history else None

        await bounded_map(page, fill_latest_snapshot, concurrency=8)
        return {"outputs": page, "next_cursor": page[-1]["uri"] if len(outputs) > limit else None}

    @staticmethod
    def _merge_args(
        payload: Mapping[str, Any] | None,
        private_payload: Mapping[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Recombine saved args without mutation, or return None when absent.

        Private values take precedence. The result can contain credentials and
        is only for Runtime request bodies, never logs or public task metadata.
        """
        public_args = (payload or {}).get("args")
        private_args = (private_payload or {}).get("args")
        if not isinstance(public_args, dict) and not isinstance(private_args, dict):
            return None
        return {
            **(public_args if isinstance(public_args, dict) else {}),
            **(private_args if isinstance(private_args, dict) else {}),
        }

    def _normalize_request_uris(
        self, request: CompileInputs | CompileRequest, ctx: RequestContext
    ) -> CompileInputs | CompileRequest:
        """Resolve identity-bound URIs and sanitize target whitespace before checks or persistence."""
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
            raise InvalidArgumentError(
                "The input skill is not in a supported location. "
                "Select a Skill directory or its SKILL.md, "
                "e.g. viking://user/<user_id>/skills/<skill_name>."
            )
        target = normalize_storage_target_uri(
            validate_request_viking_uri(resolve_path_variables(request.to), ctx, field_name="to")
        )
        self._validate_target(target)
        return request.model_copy(update={"from_": sources, "to": target, "skill": skill})

    async def _normalize_request(
        self, request: CompileInputs | CompileRequest, ctx: RequestContext
    ) -> CompileInputs | CompileRequest:
        """Validate inputs for new admissions without revalidating recovered submissions."""
        request = self._normalize_request_uris(request, ctx)
        assert request.to is not None
        parts = uri_parts(request.to)
        if parts[:1] == ["user"] and parts[2:4] == ["memories", "experiences"]:
            raise InvalidArgumentError(
                "Compile target must not be inside the user memories/experiences subtree"
            )
        for uri in request.from_:
            try:
                stat = await self._fs.stat(uri, ctx, skip_count=True)
            except NotFoundError as exc:
                raise NotFoundError(
                    uri,
                    "compile source directory",
                    reason=(
                        "The source directory is not found. "
                        "Update the Compile configuration's source directories before retrying."
                    ),
                ) from exc
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
        # In-server Skill Compile publishes resources and Skills; memory spaces are
        # consolidated in place with --skill memory.
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

    @staticmethod
    def _split_payload(
        request: CompileInputs | CompileRequest,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = request.model_dump(
            mode="json", by_alias=True, exclude_none=True, exclude={"compile_name"}
        )
        args = payload.get("args")
        if not isinstance(args, dict):
            return payload, {}
        public_args = sanitize_task_result(args)
        private_args = {
            key: value
            for key, value in args.items()
            if key not in public_args or value != public_args[key]
        }
        if not private_args:
            return payload, {}
        if public_args:
            payload["args"] = public_args
        else:
            payload.pop("args", None)
        return payload, {"args": private_args}

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
    def _validate_args(args: Mapping[str, Any] | None) -> None:
        args = args or {}
        unknown = sorted(set(args) - _COMPILE_ARGS)
        if unknown:
            raise InvalidArgumentError(f"Unsupported Compile args: {', '.join(unknown)}")
        if not isinstance(args.get("wiki_links", False), bool):
            raise InvalidArgumentError("args.wiki_links must be a boolean")

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
    "CompileCreateRequest",
    "CompileInputs",
    "CompileRequest",
    "CompileService",
]
