"""Report VikingBot model-call token usage to the OpenViking server dashboard.

The server's Usage/Audit dashboard only sees model calls made in its own process.
VikingBot runs separately, so each `vlm.call` event in the bot process is queued here
under the identity of the request that caused it and sent in batches to the server's
bot usage endpoint. Reporting is best-effort: it never blocks or fails a model call.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

import httpx
from loguru import logger

from openviking.observability.events import ObservabilityEvent, register_event_subscriber

REPORT_PATH = "/api/v1/console/usage/bot"
FLUSH_INTERVAL_SECONDS = 5.0
REPORT_TIMEOUT_SECONDS = 10.0
# Bound on the final flush when the bot shuts down.
SHUTDOWN_FLUSH_SECONDS = 3.0
# Calls kept per identity while the server is unreachable; the oldest are dropped first.
# Also the server's per-report limit.
MAX_PENDING_CALLS = 1000
# The server's per-call token limit; larger provider counts are clamped, not rejected.
MAX_CALL_TOKENS = 100_000_000
# Errors raised before the request reached the server, so a retry cannot double-count.
_UNSENT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)

# Business Data Platform identity of the request whose model calls are being made.
_connection: ContextVar[Mapping[str, Any] | None] = ContextVar("bot_usage_connection", default=None)
_reporter: BotUsageReporter | None = None


@contextmanager
def usage_connection(connection: Mapping[str, Any] | None) -> Iterator[None]:
    """Attribute model calls made in this context, and tasks it starts, to `connection`."""
    token = _connection.set(connection or None)
    try:
        yield
    finally:
        _connection.reset(token)


def configure(ov_server: Any, gateway_token: str) -> BotUsageReporter:
    """Report this process's `vlm.call` events to the configured Business Data Platform.

    Every VLM backend publishes `vlm.call` from the instance that answered, so failover
    calls carry the model actually used. Subscribers run in the caller's context, which
    keeps the request identity of `usage_connection`. The server accepts reports only
    from the gateway it manages, so nothing is queued without its gateway token.
    """
    global _reporter
    _reporter = BotUsageReporter(ov_server, gateway_token=gateway_token)
    register_event_subscriber("bot_usage", _on_event)
    return _reporter


async def aclose() -> None:
    """Send calls still queued; called when the bot shuts down."""
    if _reporter is not None:
        await _reporter.aclose()


def _on_event(event: ObservabilityEvent) -> None:
    if event.event_name != "vlm.call" or _reporter is None:
        return
    try:
        payload = event.payload
        _reporter.record(
            provider=payload.get("provider"),
            model_name=payload.get("model_name"),
            usage=payload,
        )
    except Exception as exc:  # noqa: BLE001 - usage reporting must never break a model call
        logger.debug("Bot usage record failed: {}", exc)


class BotUsageReporter:
    """Batch calls per identity and send them to the server in the background."""

    def __init__(
        self,
        ov_server: Any,
        *,
        gateway_token: str,
        flush_interval: float = FLUSH_INTERVAL_SECONDS,
    ):
        self._ov_server = ov_server
        self._gateway_token = gateway_token
        self._flush_interval = flush_interval
        self._pending: dict[tuple[tuple[str, str], ...], list[dict[str, Any]]] = {}
        self._task: asyncio.Task[None] | None = None
        self._failing = False

    def record(self, *, provider: Any, model_name: Any, usage: Mapping[str, Any]) -> None:
        prompt_tokens = min(max(int(usage.get("prompt_tokens") or 0), 0), MAX_CALL_TOKENS)
        completion_tokens = min(max(int(usage.get("completion_tokens") or 0), 0), MAX_CALL_TOKENS)
        if not prompt_tokens and not completion_tokens:
            return
        headers = self._headers(_connection.get())
        if headers is None:
            return
        calls = self._pending.setdefault(tuple(sorted(headers.items())), [])
        calls.append(
            {
                "provider": str(provider or "")[:128],
                "model_name": str(model_name or "")[:256],
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        del calls[:-MAX_PENDING_CALLS]
        self._ensure_flusher()

    def _headers(self, connection: Mapping[str, Any] | None) -> dict[str, str] | None:
        """Return the server auth headers for the request identity, as VikingClient sends them.

        Calls without a request connection are reported as the bot's configured user; a
        root key names that user only in trusted mode, like VikingClient's root-key mode.
        Returns None when no server or gateway token is configured.
        """
        config = self._ov_server
        if not self._gateway_token or not str(getattr(config, "server_url", "") or "").strip():
            return None
        auth_mode = str(getattr(config, "effective_auth_mode", "") or "").lower()
        if auth_mode not in {"trusted", "api_key", "dev"}:
            root = str(getattr(config, "api_key_type", "") or "").lower() == "root"
            auth_mode = "trusted" if root else "api_key"
        if auth_mode == "dev":
            return {}
        headers: dict[str, str] = {}
        if connection:
            values = (
                ("X-API-Key", connection.get("api_key")),
                ("X-OpenViking-Account", connection.get("account_id")),
                ("X-OpenViking-User", connection.get("user_id")),
            )
        else:
            trusted = auth_mode == "trusted"
            values = (
                ("X-API-Key", getattr(config, "api_key", None)),
                ("X-OpenViking-Account", config.account_id if trusted else None),
                ("X-OpenViking-User", config.admin_user_id if trusted else None),
            )
        for name, value in values:
            if value:
                headers[name] = str(value)
        return headers

    def _ensure_flusher(self) -> None:
        if self._task is not None and not self._task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._task = loop.create_task(self._run(), name="bot-usage-reporter")

    async def _run(self) -> None:
        while self._pending:
            await asyncio.sleep(self._flush_interval)
            await self.flush()

    async def aclose(self) -> None:
        """Stop the background flusher and send what is queued, within a short bound."""
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        try:
            await asyncio.wait_for(self.flush(), SHUTDOWN_FLUSH_SECONDS)
        except Exception as exc:  # noqa: BLE001 - shutdown must not fail on reporting
            logger.warning("Bot usage final report failed: {}", exc)

    async def flush(self) -> None:
        """Send every queued batch once; keep batches the server never received."""
        pending, self._pending = self._pending, {}
        if not pending:
            return
        url = str(self._ov_server.server_url).rstrip("/") + REPORT_PATH
        # Like the bot's other direct server calls, never route through an env proxy.
        async with httpx.AsyncClient(timeout=REPORT_TIMEOUT_SECONDS, trust_env=False) as client:
            for key, calls in pending.items():
                try:
                    response = await client.post(
                        url,
                        headers={**dict(key), "X-Gateway-Token": self._gateway_token},
                        json={"calls": calls},
                    )
                except _UNSENT_ERRORS as exc:
                    self._retry(key, calls, f"{type(exc).__name__}: {exc}")
                    continue
                except Exception as exc:  # noqa: BLE001 - the server may have recorded it
                    self._warn(f"failed ({type(exc).__name__}: {exc}); calls dropped")
                    continue
                if response.status_code in {429, 502, 503, 504}:
                    self._retry(key, calls, f"HTTP {response.status_code}")
                    continue
                if response.status_code >= 400:
                    # The server will not accept this batch on retry either, for example
                    # a server without the bot usage endpoint.
                    self._warn(f"rejected with HTTP {response.status_code}; calls dropped")
                    continue
                self._failing = False

    def _retry(self, key: tuple[tuple[str, str], ...], calls: list[dict[str, Any]], error: str):
        self._warn(f"failed, will retry: {error}")
        merged = calls + self._pending.get(key, [])
        self._pending[key] = merged[-MAX_PENDING_CALLS:]

    def _warn(self, problem: str) -> None:
        """Log the first failure of a streak only; reports repeat every few seconds."""
        if not self._failing:
            logger.warning("Bot usage report {}", problem)
            self._failing = True
