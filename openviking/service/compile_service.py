# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Compile API models and the in-process, queue-backed Compile executor."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from openviking.core.namespace import classify_uri, uri_parts
from openviking.core.path_variables import resolve_path_variables
from openviking.core.uri_validation import validate_request_viking_uri
from openviking.server.identity import RequestContext
from openviking.service import task_tracker as task_tracker_module
from openviking.service.external_task_service import (
    ExternalTaskError,
    ExternalTaskService,
    TaskCancelled,
    TaskProgress,
)
from openviking.service.fs_service import FSService
from openviking.service.memory_compile import MemoryCompileRunner
from openviking.service.task_tracker import TaskRecord
from openviking.service.task_tracker_concurrency import KeyedAsyncLockPool
from openviking_cli.exceptions import (
    InvalidArgumentError,
    NotFoundError,
    ResourceExhaustedError,
    UnavailableError,
)
from openviking_cli.utils.config.open_viking_config import CompileApiConfig

# Task states that occupy a user's Compile capacity.
_ACTIVE_TASK_STATUSES = ("pending", "running", "cancelling")
# Provider-independent args Compile understands; everything else is rejected.
_COMPILE_ARGS = frozenset({"last_compile_time", "wiki_links"})

# Sentinel --skill value that routes a Compile request to memory consolidation
# instead of the Skill pipeline. It is not a real Skill URI.
MEMORY_COMPILE_SKILL = "memory"


class CompileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: list[str] = Field(default_factory=list, alias="from")
    to: str = Field(min_length=1)
    skill: str = Field(min_length=1)
    instruction: str | None = None
    args: dict[str, Any] | None = None

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
    ) -> TaskRecord:
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
            return await self._submit(payload, payload["to"], ctx, idempotency_key)
        request = self._normalize_request_uris(request, ctx)
        self._validate_args(request.args)
        if idempotency_key:
            # Recovering an accepted submission needs neither its sources nor the runtime.
            existing = await self._tasks.recover_submission(
                self.task_type, self._payload(request), {}, ctx, idempotency_key
            )
            if existing is not None:
                return existing
        if self._runner is None:
            raise UnavailableError("compile", "the Compile runtime is not configured")
        normalized = await self._normalize_request(request, ctx)
        return await self._submit(
            self._payload(normalized), ", ".join(normalized.from_), ctx, idempotency_key
        )

    async def _submit(
        self,
        payload: dict[str, Any],
        resource_id: str,
        ctx: RequestContext,
        idempotency_key: str | None,
    ) -> TaskRecord:
        # Serialize per owner so concurrent submissions cannot all pass the cap.
        async with self._capacity_locks.acquire((ctx.account_id, ctx.user.user_id)):
            await self._ensure_capacity(ctx)
            return await self._tasks.create(
                self.task_type,
                resource_id=resource_id,
                payload=payload,
                ctx=ctx,
                **({"idempotency_key": idempotency_key} if idempotency_key else {}),
            )

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
            request = self._sanitized_request(payload)
            vlm = await self._vlm_resolver.get_vlm(ctx.account_id)
            return await self._runner.run(
                task.task_id,
                request,
                client=InProcessVikingClient(self._service, ctx),
                provider=CompileProvider(vlm, self._slots()),
                progress=progress,
                cancelled=cancelled,
                owner=(ctx.account_id, ctx.user.user_id),
            )
        except InvalidArgumentError as exc:
            raise ExternalTaskError("INVALID_ARGUMENT", str(exc)) from exc
        except CompileFailure as exc:
            raise ExternalTaskError(exc.code, str(exc), result=exc.result) from exc

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
    def _sanitized_request(payload: Mapping[str, Any]) -> Any:
        from openviking.compile.models import DEFAULT_COMPILE_INSTRUCTION, SanitizedCompileRequest
        from openviking.compile.runner import compile_time

        args = payload.get("args") or {}
        instruction = (payload.get("instruction") or "").strip()
        return SanitizedCompileRequest(
            **{
                "from": list(payload["from"]),
                "to": payload["to"],
                "instruction": instruction or DEFAULT_COMPILE_INSTRUCTION,
                "instruction_provided": bool(instruction),
                "skill": payload["skill"],
                "last_compile_time": (
                    compile_time(args["last_compile_time"]) if "last_compile_time" in args else None
                ),
                "wiki_links": args.get("wiki_links", False),
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
            stat = await self._fs.stat(uri, ctx)
            if not stat.get("isDir"):
                raise InvalidArgumentError(f"Compile source must be a directory: {uri}")
        skill_stat = await self._fs.stat(request.skill, ctx)
        if not skill_stat.get("isDir"):
            raise InvalidArgumentError("skill must resolve to a Skill directory or SKILL.md")
        skill_file = await self._fs.stat(f"{request.skill}/SKILL.md", ctx)
        if skill_file.get("isDir"):
            raise InvalidArgumentError("Skill directory must contain a SKILL.md file")
        await self._fs.ensure_write_access(request.to, ctx)
        try:
            target_stat = await self._fs.stat(request.to, ctx)
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
        if classification.context_type == "skill":
            if not classification.is_skill_namespace or (
                classification.scope == "agent" and parts != ["agent", "skills"]
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


__all__ = [
    "CompileRequest",
    "CompileService",
]
