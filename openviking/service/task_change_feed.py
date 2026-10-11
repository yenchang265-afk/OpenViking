# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Push notifications for committed task mutations.

The TaskTracker publishes every committed mutation here so HTTP clients can
follow task progress over Server-Sent Events instead of polling. Delivery is
process-local: with several server workers a subscriber only sees mutations
committed by its own worker, so clients must keep a fallback in that mode.
"""

import asyncio
import threading
from typing import Any, Callable, Dict, Set, Union

from openviking_cli.utils.logger import get_logger

logger = get_logger(__name__)

# Delivered instead of the dropped backlog when a subscriber falls behind;
# the client must re-read the task list to recover the missed state.
RESYNC = object()

TaskPredicate = Callable[[Any], bool]
TaskPayload = Dict[str, Any]


class TaskSubscription:
    """One listener bound to the event loop that created it."""

    def __init__(
        self, predicate: TaskPredicate, loop: asyncio.AbstractEventLoop, max_pending: int
    ) -> None:
        self._predicate = predicate
        self._loop = loop
        self._queue: "asyncio.Queue[Union[TaskPayload, object]]" = asyncio.Queue(
            maxsize=max_pending
        )

    def matches(self, task: Any) -> bool:
        return self._predicate(task)

    def offer(self, payload: TaskPayload) -> None:
        """Hand a payload to the subscriber loop from any thread."""
        self._loop.call_soon_threadsafe(self._enqueue, payload)

    def _enqueue(self, payload: TaskPayload) -> None:
        try:
            self._queue.put_nowait(payload)
        except asyncio.QueueFull:
            while not self._queue.empty():
                self._queue.get_nowait()
            self._queue.put_nowait(RESYNC)

    async def next(self, timeout: float) -> Union[TaskPayload, object]:
        """Return the next payload or RESYNC; raise TimeoutError when idle."""
        return await asyncio.wait_for(self._queue.get(), timeout)


class TaskChangeFeed:
    """Thread-safe fan-out of task snapshots to matching subscribers."""

    def __init__(self, max_pending: int = 256) -> None:
        self._max_pending = max_pending
        self._lock = threading.Lock()
        self._subscriptions: Set[TaskSubscription] = set()

    def subscribe(self, predicate: TaskPredicate) -> TaskSubscription:
        """Register a listener on the running event loop."""
        subscription = TaskSubscription(predicate, asyncio.get_running_loop(), self._max_pending)
        with self._lock:
            self._subscriptions.add(subscription)
        return subscription

    def unsubscribe(self, subscription: TaskSubscription) -> None:
        with self._lock:
            self._subscriptions.discard(subscription)

    def has_subscribers(self) -> bool:
        with self._lock:
            return bool(self._subscriptions)

    def publish(self, task: Any, build_payload: Callable[[], TaskPayload]) -> None:
        """Deliver one task snapshot; the payload is built once, only if needed."""
        with self._lock:
            subscriptions = list(self._subscriptions)
        payload = None
        for subscription in subscriptions:
            try:
                if not subscription.matches(task):
                    continue
            except Exception:
                logger.warning("[TaskChangeFeed] Subscriber filter failed", exc_info=True)
                continue
            if payload is None:
                payload = build_payload()
            try:
                subscription.offer(payload)
            except RuntimeError:
                # The subscriber's event loop is closed; it can never drain.
                self.unsubscribe(subscription)
