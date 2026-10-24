# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Durable, queue-backed execution of long-running in-process tasks.

Like add_resource, each task is a QueueFS message that stays unacknowledged
until the task outcome is persisted. After a crash or restart the message is
redelivered and the provider runs the task again from the beginning.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Mapping, Protocol
from uuid import uuid4

from openviking.server.identity import RequestContext, Role
from openviking.service.task_tracker import TaskRecord, TaskStatus, get_task_tracker
from openviking.service.task_tracker_concurrency import (
    KeyedAsyncLockPool,
    OwnerLoopDispatcher,
    run_to_completion,
)
from openviking.service.task_work_index import bind_task_context
from openviking.storage.queuefs import QueueManager, get_queue_manager
from openviking_cli.exceptions import ConflictError
from openviking_cli.session.user_id import UserIdentifier
from openviking_cli.utils.logger import get_logger

logger = get_logger(__name__)

_ACTIVE_STATUSES = frozenset({"pending", "running", "cancelling"})
# Started attempts per task, counting re-runs after restarts. A task that keeps
# dying with the process must not crash-loop and re-spend model tokens forever.
MAX_TASK_ATTEMPTS = 3


class ExternalTaskError(RuntimeError):
    """A classified task failure recorded as the task's error."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        transient: bool = False,
        result: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.transient = transient
        # Partial output retained on the failed task, e.g. per-item errors.
        self.result = result


@dataclass(frozen=True)
class ExternalTaskSnapshot:
    """Provider-independent task outcome applied to the task record."""

    status: str
    stage: str | None = None
    result: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None


# Report a stage and public metadata for the running task.
TaskProgress = Callable[[str, dict[str, Any]], Awaitable[None]]
# Return True once cancellation of the running task was requested.
TaskCancelled = Callable[[], Awaitable[bool]]
# Return the owner's current (role, group_ids), or None when the user no longer exists.
IdentityResolver = Callable[[str, str], Awaitable[tuple[str, tuple[str, ...]] | None]]


class ExternalTaskProvider(Protocol):
    """Executor contract for one durable task type."""

    task_type: str
    task_id_prefix: str

    def serialization_key(self, payload: Mapping[str, Any]) -> str | None: ...

    async def run(
        self,
        task: TaskRecord,
        payload: Mapping[str, Any],
        ctx: RequestContext,
        *,
        progress: TaskProgress,
        cancelled: TaskCancelled,
    ) -> dict[str, Any]:
        """Run one attempt and return its result; raise ExternalTaskError on failure."""
        ...


class ExternalTaskService:
    """Own durable task state while registered providers perform the work in-process."""

    def __init__(self) -> None:
        self._providers: dict[str, ExternalTaskProvider] = {}
        # Restored before workers start, then accessed only by the ExternalTask
        # queue's loop. Restored owners may include multiple
        # tasks submitted before target serialization was enabled.
        self._owners: dict[tuple[str | None, str, str], set[str]] = {}
        self._executing: set[str] = set()
        self._submission_locks = KeyedAsyncLockPool[str]()
        self._submission_dispatcher = OwnerLoopDispatcher()
        self._identity_resolver: IdentityResolver | None = None

    def set_identity_resolver(self, resolver: IdentityResolver | None) -> None:
        """Re-check each task owner before every attempt (key-backed auth only)."""
        self._identity_resolver = resolver

    async def _current_identity(self, ctx: RequestContext) -> RequestContext:
        """Never run with more access than the owner has now.

        The submit-time identity is narrowed to the owner's current role and groups,
        so revoked access also stops queued tasks and re-runs after a restart.
        """
        if self._identity_resolver is None:
            return ctx
        current = await self._identity_resolver(ctx.account_id, ctx.user.user_id)
        if current is None:
            raise ExternalTaskError("UNAUTHENTICATED", "The task owner no longer exists")
        current_role, current_groups = current
        stored, now = Role(ctx.role), Role(current_role or Role.USER)
        return dataclasses.replace(
            ctx,
            role=stored if stored.rank <= now.rank else now,
            group_ids=tuple(group for group in ctx.group_ids if group in set(current_groups)),
        )

    def register(self, provider: ExternalTaskProvider) -> None:
        if provider.task_type in self._providers:
            raise ValueError(f"External task provider already registered: {provider.task_type}")
        self._providers[provider.task_type] = provider

    def _provider(self, task_type: str) -> ExternalTaskProvider:
        provider = self._providers.get(task_type)
        if provider is None:
            raise ExternalTaskError(
                "UNAVAILABLE",
                f"External task provider is not registered: {task_type}",
                transient=False,
            )
        return provider

    def _serialization_key(self, task: TaskRecord) -> tuple[str | None, str, str] | None:
        key = self._provider(task.task_type).serialization_key(task.meta["request"])
        return (task.account_id, task.task_type, key) if key is not None else None

    async def restore_tasks(self, tasks: Iterable[TaskRecord]) -> None:
        """Reserve submitted work before any recovered queue delivery can run."""
        for task in tasks:
            if (
                task.task_type not in self._providers
                or task.result is not None
                or task.error is not None
            ):
                continue
            if task.status not in {TaskStatus.RUNNING, TaskStatus.CANCELLING}:
                continue
            if task.status == TaskStatus.CANCELLING and task.stage in {None, "queued"}:
                continue
            key = self._serialization_key(task)
            if key is not None:
                self._owners.setdefault(key, set()).add(task.task_id)

    def _release(self, task: TaskRecord) -> None:
        key = self._serialization_key(task)
        if key is not None and key in self._owners:
            self._owners[key].discard(task.task_id)
            if not self._owners[key]:
                del self._owners[key]

    async def create(
        self,
        task_type: str,
        *,
        resource_id: str | None,
        payload: Mapping[str, Any],
        private_payload: Mapping[str, Any] | None = None,
        ctx: RequestContext,
        idempotency_key: str | None = None,
    ) -> TaskRecord:
        async def create_task():
            return await self._create(
                task_type,
                resource_id=resource_id,
                payload=payload,
                private_payload=private_payload,
                ctx=ctx,
                idempotency_key=idempotency_key,
            )

        if not idempotency_key:
            return await create_task()
        key = submission_task_id(ctx, task_type, "", idempotency_key)

        async def serialized():
            async with self._submission_locks.acquire(key):
                return await run_to_completion(create_task)

        return await self._submission_dispatcher.run(serialized)

    async def _create(
        self,
        task_type: str,
        *,
        resource_id: str | None,
        payload: Mapping[str, Any],
        private_payload: Mapping[str, Any] | None = None,
        ctx: RequestContext,
        idempotency_key: str | None = None,
    ) -> TaskRecord:
        provider = self._provider(task_type)
        tracker = get_task_tracker()
        request_hash = submission_request_hash(payload, private_payload)
        token = uuid4().hex
        task_id = (
            submission_task_id(ctx, task_type, provider.task_id_prefix, idempotency_key)
            if idempotency_key
            else f"{provider.task_id_prefix}{token}"
        )
        task = await tracker.create(
            task_type,
            resource_id=resource_id,
            account_id=ctx.account_id,
            user_id=ctx.user.user_id,
            task_id=task_id,
            meta={
                "request": dict(payload),
                **(
                    {"submission_hash": request_hash, "submission_token": token}
                    if idempotency_key
                    else {}
                ),
            },
            auth={
                "request_identity": request_identity(ctx),
                "external_request_private": dict(private_payload or {}),
            },
        )
        if idempotency_key and task.meta.get("submission_hash") != request_hash:
            raise ConflictError("Idempotency-Key was already used with different parameters")
        if idempotency_key and task.meta.get("submission_token") != token:
            # Recover a creation interrupted before queue delivery. Duplicate
            # deliveries are safe: execute claims each task before submitting.
            await self._resume_submission(task, ctx)
            return task
        enqueued = False
        try:
            await tracker.update_stage(
                task.task_id,
                "queued",
                account_id=ctx.account_id,
                user_id=ctx.user.user_id,
            )
            with bind_task_context(task.task_id, ctx.account_id, ctx.user.user_id):
                await get_queue_manager().enqueue(
                    QueueManager.EXTERNAL_TASK,
                    {
                        "task_id": task.task_id,
                        "account_id": ctx.account_id,
                        "user_id": ctx.user.user_id,
                    },
                )
            enqueued = True
            current = await tracker.get(
                task.task_id,
                account_id=ctx.account_id,
                user_id=ctx.user.user_id,
            )
            if current is not None:
                task = current
        except BaseException:
            if not enqueued:
                await tracker.fail(
                    task.task_id,
                    "Failed to enqueue external task",
                    account_id=ctx.account_id,
                    user_id=ctx.user.user_id,
                )
            raise
        return task

    async def recover_submission(
        self,
        task_type: str,
        payload: Mapping[str, Any],
        private_payload: Mapping[str, Any],
        ctx: RequestContext,
        key: str,
    ) -> TaskRecord | None:
        async def recover():
            provider = self._provider(task_type)
            task = await get_task_tracker().get(
                submission_task_id(ctx, task_type, provider.task_id_prefix, key),
                account_id=ctx.account_id,
                user_id=ctx.user.user_id,
            )
            if task is None:
                return None
            if task.meta.get("submission_hash") != submission_request_hash(
                payload, private_payload
            ):
                raise ConflictError("Idempotency-Key was already used with different parameters")
            await self._resume_submission(task, ctx)
            return task

        async def serialized():
            async with self._submission_locks.acquire(submission_task_id(ctx, task_type, "", key)):
                return await run_to_completion(recover)

        return await self._submission_dispatcher.run(serialized)

    async def _resume_submission(self, task: TaskRecord, ctx: RequestContext) -> None:
        if task.status == TaskStatus.PENDING:
            with bind_task_context(task.task_id, ctx.account_id, ctx.user.user_id):
                await get_queue_manager().enqueue(
                    QueueManager.EXTERNAL_TASK,
                    {
                        "task_id": task.task_id,
                        "account_id": ctx.account_id,
                        "user_id": ctx.user.user_id,
                    },
                )

    async def execute(self, task_id: str, account_id: str, user_id: str) -> bool:
        """Return False when this delivery must rotate behind other target work."""
        tracker = get_task_tracker()
        claimed = False
        try:
            task = await tracker.get(task_id, account_id=account_id, user_id=user_id)
            if task is None or task.status in {
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            }:
                return True
            # The outcome is persisted before QueueFS ACK removes the owned work.
            # After a crash in that window, let the recovered delivery ACK without
            # resubmitting credentials that have already been cleared.
            if task.result is not None or task.error is not None:
                return True

            provider = self._provider(task.task_type)
            payload = task.meta.get("request")
            if not isinstance(payload, dict):
                await tracker.fail(
                    task_id,
                    "INVALID_ARGUMENT: External task request is missing",
                    account_id=account_id,
                    user_id=user_id,
                )
                return True
            key = self._serialization_key(task)
            owners = self._owners.get(key, set()) if key is not None else set()
            if task_id in self._executing or (owners and task_id not in owners):
                return False
            # No await between checking and claiming: concurrent deliveries on the
            # queue loop cannot both acquire an unoccupied target.
            if key is not None:
                self._owners.setdefault(key, set()).add(task_id)
            self._executing.add(task_id)
            claimed = True
            await self._execute_task(task, provider, payload, account_id, user_id)
            return True
        except asyncio.CancelledError:
            if not await tracker.is_cancellation_requested(
                task_id, account_id=account_id, user_id=user_id
            ):
                raise
            await run_to_completion(lambda: self.cancel_recovered(task_id, account_id, user_id))
            raise
        finally:
            # An interrupted delivery keeps ownership until recovery confirms
            # the Runtime has stopped; it must not admit another target writer.
            if claimed:
                self._executing.remove(task_id)

    async def _execute_task(
        self,
        task: TaskRecord,
        provider: ExternalTaskProvider,
        payload: Mapping[str, Any],
        account_id: str,
        user_id: str,
    ) -> None:
        """Run one attempt; a redelivered task after restart simply runs again."""
        tracker = get_task_tracker()
        task_id = task.task_id

        async def progress(stage: str, meta: dict[str, Any]) -> None:
            await tracker.update_stage(
                task_id, stage, account_id=account_id, user_id=user_id, meta=meta
            )

        async def cancelled() -> bool:
            return await tracker.is_cancellation_requested(
                task_id, account_id=account_id, user_id=user_id
            )

        try:
            # Any failure before or during the attempt must become a recorded outcome;
            # an escaped exception would leave the message unacked and the target claimed.
            attempt = int(task.meta.get("attempts") or 0) + 1
            if attempt > MAX_TASK_ATTEMPTS:
                raise ExternalTaskError(
                    "INTERRUPTED",
                    f"Task was interrupted {attempt - 1} times before finishing; not retrying",
                )
            # Persist the count before running so a crash during the attempt still counts.
            await tracker.update_meta(
                task_id, {"attempts": attempt}, account_id=account_id, user_id=user_id
            )
            auth = await self._task_auth(task_id, account_id, user_id)
            ctx = await self._current_identity(restore_request_context(auth, account_id, user_id))
            await tracker.start(task_id, account_id=account_id, user_id=user_id, stage="running")
            result = await provider.run(task, payload, ctx, progress=progress, cancelled=cancelled)
        except ExternalTaskError as exc:
            snapshot = ExternalTaskSnapshot(
                status="failed", result=exc.result, error_code=exc.code, error_message=str(exc)
            )
        except Exception as exc:
            logger.exception("Durable task %s failed", task_id)
            snapshot = ExternalTaskSnapshot(
                status="failed", error_code="INTERNAL", error_message=str(exc)
            )
        else:
            snapshot = ExternalTaskSnapshot(status="completed", result=result)
        await self._apply_snapshot(
            snapshot, task_id=task_id, account_id=account_id, user_id=user_id
        )

    async def cancel_recovered(self, task_id: str, account_id: str, user_id: str) -> None:
        """Record cancellation once the in-process attempt has stopped."""
        tracker = get_task_tracker()
        task = await tracker.get(task_id, account_id=account_id, user_id=user_id)
        if task is None:
            return
        if (
            task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
            or task.result is not None
            or task.error is not None
        ):
            self._release(task)
            return
        await self._apply_snapshot(
            ExternalTaskSnapshot(status="cancelled"),
            task_id=task_id,
            account_id=account_id,
            user_id=user_id,
        )

    @staticmethod
    async def _task_auth(task_id: str, account_id: str, user_id: str) -> dict[str, Any]:
        return await get_task_tracker().get_task_auth(
            task_id,
            account_id=account_id,
            user_id=user_id,
        )

    @staticmethod
    def _mapping(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    async def _apply_snapshot(
        self,
        snapshot: ExternalTaskSnapshot,
        *,
        task_id: str,
        account_id: str,
        user_id: str,
    ) -> bool:
        tracker = get_task_tracker()
        task = await tracker.get(task_id, account_id=account_id, user_id=user_id)
        if snapshot.stage is not None or snapshot.meta:
            stage = snapshot.stage or snapshot.status
            meta = snapshot.meta or {}
            if task is not None and (
                task.stage != stage
                or any(
                    key not in task.meta or task.meta[key] != value for key, value in meta.items()
                )
            ):
                await tracker.update_stage(
                    task_id,
                    stage,
                    account_id=account_id,
                    user_id=user_id,
                    meta=meta,
                )
        if snapshot.status in _ACTIVE_STATUSES:
            return False
        if snapshot.status not in {"completed", "failed", "cancelled"}:
            raise ExternalTaskError(
                "INVALID_RESPONSE",
                f"Unknown external task status: {snapshot.status}",
                transient=False,
            )

        async def finalize() -> None:
            if snapshot.status == "failed":
                await tracker.fail(
                    task_id,
                    self._format_error(
                        snapshot.error_code or "UNKNOWN",
                        snapshot.error_message or "External task failed",
                    ),
                    account_id=account_id,
                    user_id=user_id,
                    **({"result": snapshot.result} if snapshot.result else {}),
                )
            elif snapshot.status == "completed":
                await tracker.complete(
                    task_id,
                    snapshot.result or snapshot.meta or {},
                    account_id=account_id,
                    user_id=user_id,
                )
            else:
                await tracker.record_cancelled(
                    task_id,
                    account_id=account_id,
                    user_id=user_id,
                )
            if task is not None:
                self._release(task)

        await run_to_completion(finalize)
        return True

    @staticmethod
    def _format_error(code: str, message: str) -> str:
        return f"{code}: {message}"


__all__ = [
    "ExternalTaskError",
    "ExternalTaskProvider",
    "ExternalTaskService",
    "ExternalTaskSnapshot",
    "TaskCancelled",
    "TaskProgress",
]


def request_identity(ctx: RequestContext) -> dict[str, Any]:
    """Persist the caller's server-resolved identity, never forwarded credentials."""
    return {
        "role": str(getattr(ctx.role, "value", ctx.role)),
        "group_ids": list(ctx.group_ids),
        "actor_peer_id": ctx.actor_peer_id,
    }


def restore_request_context(
    auth: Mapping[str, Any], account_id: str, user_id: str
) -> RequestContext:
    """Rebuild the task owner's context; tasks from older versions run as a user."""
    identity = auth.get("request_identity")
    identity = identity if isinstance(identity, dict) else {}
    try:
        role = Role(identity.get("role") or Role.USER)
    except ValueError:
        role = Role.USER
    return RequestContext(
        user=UserIdentifier(account_id, user_id),
        role=role,
        group_ids=tuple(identity.get("group_ids") or ()),
        actor_peer_id=identity.get("actor_peer_id"),
    )


def key_store_identity_resolver(manager: Any) -> IdentityResolver:
    """Resolve task owners through the API key store used by key-based auth."""

    async def resolve(account_id: str, user_id: str) -> tuple[str, tuple[str, ...]] | None:
        user = await manager.get_user(account_id, user_id)
        if not user:
            return None
        groups: tuple[str, ...] = ()
        if hasattr(manager, "get_user_group_ids"):
            groups = tuple(await manager.get_user_group_ids(account_id, user_id))
        return str(user.get("role") or Role.USER), groups

    return resolve


def submission_task_id(ctx: RequestContext, task_type: str, prefix: str, key: str) -> str:
    scope = json.dumps([ctx.account_id, ctx.user.user_id, task_type, key])
    return prefix + hashlib.sha256(scope.encode()).hexdigest()


def submission_request_hash(
    payload: Mapping[str, Any], private_payload: Mapping[str, Any] | None
) -> str:
    return hashlib.sha256(
        json.dumps(
            {"payload": dict(payload), "private": dict(private_payload or {})},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
