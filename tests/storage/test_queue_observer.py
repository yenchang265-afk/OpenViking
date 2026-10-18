# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Tests for QueueObserver health semantics."""

import json
from datetime import datetime

from openviking.server.identity import RequestContext, Role
from openviking.storage.observers.queue_observer import QueueObserver
from openviking.storage.queuefs.named_queue import QueueError, QueueStatus
from openviking_cli.session.user_id import UserIdentifier


class _FakeQueueManager:
    SEMANTIC = "Semantic"

    def __init__(self, statuses: dict[str, QueueStatus]):
        self._statuses = statuses
        self._queues = {}

    async def check_status(self) -> dict[str, QueueStatus]:
        return self._statuses


def test_historical_queue_errors_do_not_make_drained_queue_unhealthy() -> None:
    observer = QueueObserver(
        _FakeQueueManager(
            {
                "Semantic": QueueStatus(
                    pending=0,
                    in_progress=0,
                    processed=69,
                    requeue_count=1,
                    error_count=1,
                )
            }
        )
    )

    assert observer.has_errors() is False
    assert observer.is_healthy() is True

    table = observer.get_status_table()
    assert "Semantic" in table
    assert "Warnings:" not in table


def test_queue_errors_make_pending_queue_unhealthy() -> None:
    observer = QueueObserver(
        _FakeQueueManager(
            {
                "Semantic": QueueStatus(
                    pending=1,
                    in_progress=0,
                    processed=69,
                    error_count=1,
                )
            }
        )
    )

    assert observer.has_errors() is True
    assert observer.is_healthy() is False

    table = observer.get_status_table()
    assert "Warnings:" not in table


def test_queue_errors_make_in_progress_queue_unhealthy() -> None:
    observer = QueueObserver(
        _FakeQueueManager(
            {
                "Semantic": QueueStatus(
                    pending=0,
                    in_progress=1,
                    processed=69,
                    error_count=1,
                )
            }
        )
    )

    assert observer.has_errors() is True
    assert observer.is_healthy() is False


class _TreeStats:
    total_nodes = 9
    pending_nodes = 1
    in_progress_nodes = 0
    done_nodes = 8


class _FakeSemanticHandler:
    @staticmethod
    def get_tree_stats():
        return _TreeStats()


class _FakeSemanticQueue:
    _dequeue_handler = _FakeSemanticHandler()


def test_status_json_summary_matches_table_totals() -> None:
    queue_manager = _FakeQueueManager(
        {
            "Semantic": QueueStatus(
                pending=0,
                in_progress=0,
                processed=2,
                error_count=0,
            )
        }
    )
    queue_manager._queues = {queue_manager.SEMANTIC: _FakeSemanticQueue()}
    observer = QueueObserver(queue_manager)

    status = observer.get_status_json()

    assert status["queues"][-1] == {
        "queue": "Semantic-Nodes",
        "pending": 1,
        "in_progress": 0,
        "processed": 8,
        "requeued": 0,
        "errors": 0,
        "total": 9,
    }
    assert status["summary"] == {
        "pending": 0,
        "in_progress": 0,
        "processed": 2,
        "requeued": 0,
        "errors": 0,
        "total": 2,
    }


def _ctx(account_id: str, role: str) -> RequestContext:
    return RequestContext(user=UserIdentifier(account_id, "alice"), role=Role(role))


def _queue_error(message: str, account_id: str, minute: int = 0) -> QueueError:
    payload = {"account_id": account_id, "uri": f"viking://resources/{account_id}"}
    return QueueError(
        timestamp=datetime(2026, 10, 18, 13, minute, 0),
        message=message,
        data={"id": "msg-1", "data": json.dumps(payload)},
    )


def _active_semantic_errors(*errors: QueueError) -> _FakeQueueManager:
    return _FakeQueueManager(
        {
            "Semantic": QueueStatus(
                in_progress=1,
                error_count=len(errors),
                errors=list(errors),
            ),
            "Embedding": QueueStatus(processed=3),
        }
    )


def test_root_sees_active_error_reasons_in_table_and_json() -> None:
    observer = QueueObserver(
        _active_semantic_errors(_queue_error("lock lease expired", "acme", minute=12)),
        ctx=_ctx("acme", Role.ROOT),
    )

    table = observer.get_status_table()
    assert "Active errors:" in table
    assert "Semantic (2026-10-18 13:12:00): lock lease expired" in table

    status = observer.get_status_json()
    assert status["active_errors"] == [
        {
            "queue": "Semantic",
            "timestamp": "2026-10-18T13:12:00",
            "message": "lock lease expired",
        }
    ]


def test_non_root_only_sees_errors_from_own_account() -> None:
    observer = QueueObserver(
        _active_semantic_errors(
            _queue_error("acme failure", "acme"),
            _queue_error("other tenant secret", "globex"),
        ),
        ctx=_ctx("acme", Role.ADMIN),
    )

    table = observer.get_status_table()
    assert "acme failure" in table
    assert "other tenant secret" not in table
    assert [e["message"] for e in observer.get_status_json()["active_errors"]] == ["acme failure"]


def test_non_root_sees_own_errors_across_message_shapes() -> None:
    def error(message: str, data: dict) -> QueueError:
        return QueueError(timestamp=datetime(2026, 10, 18), message=message, data=data)

    embedding = {"action": "upsert", "payload": {"context_data": {"account_id": "acme"}}}
    observer = QueueObserver(
        _active_semantic_errors(
            error("embedding", {"id": "1", "data": json.dumps(embedding)}),
            error("legacy", {"id": "2", "data": {"context_data": {"account_id": "acme"}}}),
            error("dict envelope", {"id": "3", "data": {"account_id": "acme"}}),
            error("bad json", {"id": "4", "data": "{not json"}),
            error("non-object", {"id": "5", "data": "[1]"}),
        ),
        ctx=_ctx("acme", Role.USER),
    )

    messages = {e["message"] for e in observer.get_status_json()["active_errors"]}
    assert messages == {"embedding", "legacy", "dict envelope"}


def test_errors_without_account_are_hidden_from_non_root() -> None:
    error = QueueError(timestamp=datetime(2026, 10, 18), message="unscoped", data=None)
    observer = QueueObserver(_active_semantic_errors(error), ctx=_ctx("acme", Role.USER))

    assert "Active errors:" not in observer.get_status_table()
    assert observer.get_status_json()["active_errors"] == []


def test_error_reasons_omitted_without_request_context() -> None:
    observer = QueueObserver(_active_semantic_errors(_queue_error("boom", "acme")))

    assert "Active errors:" not in observer.get_status_table()
    assert "active_errors" not in observer.get_status_json()


def test_drained_queue_errors_are_not_reported_as_active() -> None:
    observer = QueueObserver(
        _FakeQueueManager(
            {
                "Semantic": QueueStatus(
                    processed=5,
                    error_count=1,
                    errors=[_queue_error("old failure", "acme")],
                )
            }
        ),
        ctx=_ctx("acme", Role.ROOT),
    )

    assert "Active errors:" not in observer.get_status_table()
    assert observer.get_status_json()["active_errors"] == []


def test_active_error_messages_are_single_line_and_bounded() -> None:
    errors = [_queue_error(f"failure {i}\n  detail " + "x" * 500, "acme") for i in range(8)]
    observer = QueueObserver(_active_semantic_errors(*errors), ctx=_ctx("acme", Role.ROOT))

    reported = observer.get_status_json()["active_errors"]
    assert len(reported) == QueueObserver.MAX_REPORTED_ERRORS
    assert reported[0]["message"].startswith("failure 7 detail ")
    assert all("\n" not in e["message"] for e in reported)
    assert all(len(e["message"]) <= QueueObserver.MAX_ERROR_MESSAGE_CHARS for e in reported)
