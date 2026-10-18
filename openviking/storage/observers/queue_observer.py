# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""
QueueObserver: Queue system observability tool.

Provides methods to observe and report queue status in various formats.
"""

import json
from typing import Any, Dict, List, Optional

from openviking.server.identity import RequestContext, Role
from openviking.storage.observers.base_observer import BaseObserver
from openviking.storage.queuefs.named_queue import QueueError, QueueStatus
from openviking.storage.queuefs.queue_manager import QueueManager
from openviking_cli.utils import run_async
from openviking_cli.utils.logger import get_logger

logger = get_logger(__name__)


class QueueObserver(BaseObserver):
    """
    QueueObserver: System observability tool for queue management.

    Provides methods to query queue status and format output.
    """

    MAX_REPORTED_ERRORS = 5
    MAX_ERROR_MESSAGE_CHARS = 300

    def __init__(self, queue_manager: QueueManager, ctx: Optional[RequestContext] = None):
        # Queues are shared by all accounts, so error reasons are reported only
        # for a request context: root sees all, other roles their own account.
        self._queue_manager = queue_manager
        self._ctx = ctx

    async def get_status_table_async(self) -> str:
        statuses = await self._queue_manager.check_status()
        tree_stats = self._get_semantic_tree_stats()
        table = self._format_status_as_table(statuses, tree_stats)
        active_errors = self._active_errors(statuses)
        if not active_errors:
            return table
        lines = [
            f"{error['queue']} ({error['timestamp'].replace('T', ' ')}): {error['message']}"
            for error in active_errors
        ]
        return "\n\n".join([table, "\n".join(["Active errors:", *lines])])

    async def get_status_json_async(self) -> dict:
        statuses = await self._queue_manager.check_status()
        tree_stats = self._get_semantic_tree_stats()
        queues = []
        total_pending = 0
        total_in_progress = 0
        total_processed = 0
        total_requeues = 0
        total_errors = 0

        for queue_name, status in statuses.items():
            total = status.pending + status.in_progress + status.processed
            queues.append(
                {
                    "queue": queue_name,
                    "pending": status.pending,
                    "in_progress": status.in_progress,
                    "processed": status.processed,
                    "requeued": status.requeue_count,
                    "errors": status.error_count,
                    "total": total,
                }
            )
            total_pending += status.pending
            total_in_progress += status.in_progress
            total_processed += status.processed
            total_requeues += status.requeue_count
            total_errors += status.error_count

        semantic = {
            "queue": "Semantic-Nodes",
            "pending": getattr(tree_stats, "pending_nodes", 0) if tree_stats else 0,
            "in_progress": getattr(tree_stats, "in_progress_nodes", 0) if tree_stats else 0,
            "processed": getattr(tree_stats, "done_nodes", 0) if tree_stats else 0,
            "requeued": 0,
            "errors": 0,
            "total": getattr(tree_stats, "total_nodes", 0) if tree_stats else 0,
        }
        queues.append(semantic)

        result = {
            "queues": queues,
            "summary": {
                "pending": total_pending,
                "in_progress": total_in_progress,
                "processed": total_processed,
                "requeued": total_requeues,
                "errors": total_errors,
                "total": total_pending + total_in_progress + total_processed,
            },
        }
        if self._ctx is not None:
            result["active_errors"] = self._active_errors(statuses)
        return result

    def get_status_table(self) -> str:
        return run_async(self.get_status_table_async())

    def get_status_json(self) -> dict:
        return run_async(self.get_status_json_async())

    def __str__(self) -> str:
        return self.get_status_table()

    def _format_status_as_table(
        self, statuses: Dict[str, QueueStatus], tree_stats: Optional[object]
    ) -> str:
        """
        Format queue statuses as a table using tabulate.

        Args:
            statuses: Dict mapping queue names to QueueStatus

        Returns:
            Formatted table string
        """
        from tabulate import tabulate

        if not statuses:
            return "No queue status data available."

        data = []
        total_pending = 0
        total_in_progress = 0
        total_processed = 0
        total_requeues = 0
        total_errors = 0

        for queue_name, status in statuses.items():
            total = status.pending + status.in_progress + status.processed
            data.append(
                {
                    "Queue": queue_name,
                    "Pending": status.pending,
                    "In Progress": status.in_progress,
                    "Processed": status.processed,
                    "Requeued": status.requeue_count,
                    "Errors": status.error_count,
                    "Total": total,
                }
            )
            total_pending += status.pending
            total_in_progress += status.in_progress
            total_processed += status.processed
            total_requeues += status.requeue_count
            total_errors += status.error_count

        data.append(
            {
                "Queue": "Semantic-Nodes",
                "Pending": getattr(tree_stats, "pending_nodes", 0) if tree_stats else 0,
                "In Progress": getattr(tree_stats, "in_progress_nodes", 0) if tree_stats else 0,
                "Processed": getattr(tree_stats, "done_nodes", 0) if tree_stats else 0,
                "Requeued": 0,
                "Errors": 0,
                "Total": getattr(tree_stats, "total_nodes", 0) if tree_stats else 0,
            }
        )

        # Add total row
        total_total = total_pending + total_in_progress + total_processed
        data.append(
            {
                "Queue": "TOTAL",
                "Pending": total_pending,
                "In Progress": total_in_progress,
                "Processed": total_processed,
                "Requeued": total_requeues,
                "Errors": total_errors,
                "Total": total_total,
            }
        )

        return tabulate(data, headers="keys", tablefmt="pretty")

    def _active_errors(self, statuses: Dict[str, QueueStatus]) -> List[Dict[str, str]]:
        """Newest error reasons from queues whose errors currently affect health."""
        if self._ctx is None:
            return []
        candidates = [
            (queue_name, error)
            for queue_name, status in statuses.items()
            if status.error_count > 0 and not status.is_complete
            for error in reversed(status.errors)
            if self._can_see_error(error)
        ]
        candidates.sort(key=lambda item: item[1].timestamp, reverse=True)
        return [
            {
                "queue": queue_name,
                "timestamp": error.timestamp.isoformat(timespec="seconds"),
                "message": " ".join(error.message.split())[: self.MAX_ERROR_MESSAGE_CHARS],
            }
            for queue_name, error in candidates[: self.MAX_REPORTED_ERRORS]
        ]

    def _can_see_error(self, error: QueueError) -> bool:
        if self._ctx.role == Role.ROOT:
            return True
        return _message_account_id(error.data) == self._ctx.account_id

    def _get_semantic_tree_stats(self) -> Optional[object]:
        semantic_queue = self._queue_manager._queues.get(self._queue_manager.SEMANTIC)
        if not semantic_queue:
            return None
        handler = getattr(semantic_queue, "_dequeue_handler", None)
        if handler and hasattr(handler, "get_tree_stats"):
            return handler.get_tree_stats()
        return None

    def is_healthy(self) -> bool:
        return not self.has_errors()

    def has_errors(self) -> bool:
        return run_async(self.has_active_errors_async())

    async def has_active_errors_async(self) -> bool:
        statuses = await self._queue_manager.check_status()
        return self._has_active_errors(statuses)

    @staticmethod
    def _has_active_errors(statuses: Dict[str, QueueStatus]) -> bool:
        return any(
            status.error_count > 0 and not status.is_complete for status in statuses.values()
        )


def _message_account_id(data: Optional[Dict[str, Any]]) -> Optional[str]:
    """Read account_id from a queue delivery, which may wrap its payload as JSON."""
    if not isinstance(data, dict):
        return None
    payload: Any = data.get("data", data)
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return None
    if not isinstance(payload, dict):
        return None
    # Embedding messages keep the account in context_data, nested under payload.
    for scope in (payload, payload.get("payload")):
        if not isinstance(scope, dict):
            continue
        context = scope.get("context_data")
        for source in (scope, context if isinstance(context, dict) else {}):
            account_id = source.get("account_id")
            if isinstance(account_id, str):
                return account_id
    return None
