# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Per-mount circuit breakers for storage calls.

While a storage backend (e.g. S3) is down, every call still waits for its full
deadline before failing. After a run of consecutive timeout/network failures
in one scope (an account's data, or a mount), calls in that scope fail
immediately (HTTP 503) until a probe after the reset timeout succeeds. Other
scopes are unaffected.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Awaitable, Callable, TypeVar

from .exceptions import (
    AGFSCircuitOpenError,
    AGFSNetworkError,
    AGFSStorageSaturatedError,
    AGFSTimeoutError,
)

if TYPE_CHECKING:
    from openviking.utils.circuit_breaker import CircuitBreaker

_ResultT = TypeVar("_ResultT")

DEFAULT_FAILURE_THRESHOLD = 5
DEFAULT_RESET_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_RESET_TIMEOUT_SECONDS = 120.0

_UNSCOPED = "<unscoped>"

_lock = threading.Lock()
_enabled = True
_settings = {
    "failure_threshold": DEFAULT_FAILURE_THRESHOLD,
    "reset_timeout": DEFAULT_RESET_TIMEOUT_SECONDS,
    "max_reset_timeout": DEFAULT_MAX_RESET_TIMEOUT_SECONDS,
}
_breakers: dict[str, "CircuitBreaker"] = {}


class _StorageFailure(Exception):
    """Neutral failure record.

    The shared breaker classifies errors by message for model APIs; storage
    error text (object keys, codes) must not be read as e.g. an auth failure.
    """


def configure_storage_breaker(
    *,
    enabled: bool,
    failure_threshold: int,
    reset_timeout_seconds: float,
    max_reset_timeout_seconds: float,
) -> None:
    """Set breaker policy; resets the state of all mounts."""
    global _enabled
    if failure_threshold < 1:
        raise ValueError(f"failure_threshold must be >= 1, got {failure_threshold}")
    if not 0 < reset_timeout_seconds <= max_reset_timeout_seconds:
        raise ValueError(
            "expected 0 < reset_timeout_seconds <= max_reset_timeout_seconds, got "
            f"{reset_timeout_seconds} and {max_reset_timeout_seconds}"
        )
    with _lock:
        _enabled = enabled
        _settings.update(
            failure_threshold=failure_threshold,
            reset_timeout=reset_timeout_seconds,
            max_reset_timeout=max_reset_timeout_seconds,
        )
        _breakers.clear()


def reset_storage_breakers() -> None:
    """Close every mount's circuit, keeping the configured policy."""
    with _lock:
        _breakers.clear()


def mount_key(path: object) -> str:
    """The breaker scope a storage path belongs to.

    Account data under ``/local/{account_id}/...`` is scoped per account, so one
    tenant's failing calls (e.g. oversized reads that time out) cannot open a
    circuit that pauses storage for every account. Other paths use their mount
    root, e.g. ``/queue``.
    """
    if not isinstance(path, str) or not path.startswith("/"):
        return _UNSCOPED
    parts = path.strip("/").split("/", 2)
    if parts[0] == "local" and len(parts) > 1 and parts[1]:
        return f"/local/{parts[1]}"
    return f"/{parts[0]}"


def _breaker_for(key: str) -> "CircuitBreaker | None":
    # Imported lazily: openviking.utils.model_retry imports pyagfs exceptions.
    from openviking.utils.circuit_breaker import CircuitBreaker

    with _lock:
        if not _enabled:
            return None
        breaker = _breakers.get(key)
        if breaker is None:
            breaker = _breakers[key] = CircuitBreaker(**_settings)
        return breaker


async def guard_storage_call(path: object, call: Callable[[], Awaitable[_ResultT]]) -> _ResultT:
    """Run ``call`` through the breaker of the mount ``path`` belongs to."""
    from openviking.utils.circuit_breaker import CircuitBreakerOpen

    key = mount_key(path)
    breaker = _breaker_for(key)
    if breaker is None:
        return await call()
    try:
        breaker.check()
    except CircuitBreakerOpen as exc:
        raise AGFSCircuitOpenError(
            f"storage backend for {key} is failing; calls are paused ({exc})"
        ) from None
    try:
        result = await call()
    except AGFSStorageSaturatedError:
        # Local thread-pool overload says nothing about the backend; counting it
        # would let request floods open the circuit. Leave the state unchanged.
        raise
    except (AGFSTimeoutError, AGFSNetworkError) as exc:
        breaker.record_failure(_StorageFailure(type(exc).__name__))
        raise
    except Exception:
        # Any other answer (not found, permission, ...) means the backend responded.
        breaker.record_success()
        raise
    breaker.record_success()
    return result
