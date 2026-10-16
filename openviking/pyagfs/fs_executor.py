# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Dedicated thread pool for blocking storage (RAGFS) calls.

Storage calls block a thread for as long as the backend takes. Running them on
the event loop's default executor lets a slow backend (e.g. high-latency S3)
exhaust the threads that vector-DB, auth and other blocking work also need.
This pool isolates storage calls, and a call that cannot start within the
queue timeout fails fast instead of waiting behind stalled ones.
"""

from __future__ import annotations

import asyncio
import contextvars
import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, TypeVar

from .exceptions import AGFSTimeoutError

_ResultT = TypeVar("_ResultT")

DEFAULT_FS_EXECUTOR_THREADS = 64
DEFAULT_FS_QUEUE_TIMEOUT_SECONDS = 30.0

_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None
_threads = DEFAULT_FS_EXECUTOR_THREADS
_queue_timeout = DEFAULT_FS_QUEUE_TIMEOUT_SECONDS


def configure_fs_executor(*, threads: int, queue_timeout_seconds: float) -> None:
    """Size the storage pool; applies to calls submitted afterwards.

    Calls already running on a previous pool finish there.
    """
    global _executor, _threads, _queue_timeout
    if threads < 1:
        raise ValueError(f"fs executor threads must be >= 1, got {threads}")
    if queue_timeout_seconds <= 0:
        raise ValueError(f"fs queue timeout must be > 0, got {queue_timeout_seconds}")
    with _lock:
        previous = _executor
        _executor = None
        _threads = threads
        _queue_timeout = queue_timeout_seconds
    if previous is not None:
        previous.shutdown(wait=False)


def _reset_after_fork() -> None:
    # A forked child inherits the pool object but none of its threads (and maybe
    # a held lock); start fresh so the child builds its own pool on first use.
    global _lock, _executor
    _lock = threading.Lock()
    _executor = None


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_after_fork)


def _submit(fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> tuple[Future, float]:
    """Submit to the current pool, creating it lazily.

    Holds the lock across submit so a concurrent ``configure_fs_executor`` cannot
    shut the pool down in between.
    """
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=_threads, thread_name_prefix="openviking-fs")
        return _executor.submit(fn, *args, **kwargs), _queue_timeout


async def run_in_fs_executor(fn: Callable[..., _ResultT], /, *args: Any, **kwargs: Any) -> _ResultT:
    """Run a blocking storage call on the storage pool, preserving contextvars.

    Raises ``AGFSTimeoutError`` when the call has not started within the queue
    timeout; it is then removed from the queue and never runs. A call that has
    started runs to completion (its duration is bounded by backend deadlines).
    """
    context = contextvars.copy_context()
    future, queue_timeout = _submit(context.run, fn, *args, **kwargs)
    waiter = asyncio.wrap_future(future)
    try:
        done, _ = await asyncio.wait({waiter}, timeout=queue_timeout)
    except asyncio.CancelledError:
        # Drop the call if it has not started; a running call cannot be stopped.
        future.cancel()
        raise
    # cancel() only succeeds for work still waiting in the queue.
    if not done and future.cancel():
        raise AGFSTimeoutError(
            f"storage call did not start within {queue_timeout:g}s: "
            "all storage threads are busy (backend slow or overloaded)"
        )
    return await waiter
