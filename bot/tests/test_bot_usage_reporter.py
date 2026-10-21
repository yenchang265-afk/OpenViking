"""Bot model-call token reporting to the Business Data Platform usage dashboard."""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from vikingbot.observability import bot_usage
from vikingbot.observability.bot_usage import BotUsageReporter, usage_connection


def _ov_server(**overrides):
    values = {
        "server_url": "http://ov.test",
        "effective_auth_mode": "api_key",
        "api_key": "bot-key",
        "api_key_type": "user",
        "account_id": "bot-acct",
        "admin_user_id": "bot-user",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _Server:
    """Capture report requests and answer with a configurable status."""

    def __init__(self, status=200):
        self.status = status
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, json={"status": "ok"})


@pytest.fixture
def server(monkeypatch):
    server = _Server()
    transport = httpx.MockTransport(server)
    real_client = httpx.AsyncClient

    monkeypatch.setattr(
        bot_usage.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    return server


async def test_calls_are_reported_as_the_request_user(server):
    reporter = BotUsageReporter(_ov_server(), flush_interval=3600)
    connection = {"api_key": "user-key", "account_id": "acct-1", "user_id": "user-1"}

    with usage_connection(connection):
        reporter.record(
            provider="openai",
            model_name="m",
            usage={"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
        )
    reporter.record(provider="openai", model_name="m", usage={"prompt_tokens": 5})
    await reporter.flush()

    by_user = {request.headers.get("X-OpenViking-User"): request for request in server.requests}
    assert set(by_user) == {"user-1", None}
    user_request = by_user["user-1"]
    assert user_request.url == "http://ov.test/api/v1/console/usage/bot"
    assert user_request.headers["X-API-Key"] == "user-key"
    assert user_request.headers["X-OpenViking-Account"] == "acct-1"
    [call] = json.loads(user_request.content)["calls"]
    assert call["prompt_tokens"] == 120
    assert call["completion_tokens"] == 30
    assert call["model_name"] == "m"
    # Without a request connection, the bot's own configured user key is used.
    assert by_user[None].headers["X-API-Key"] == "bot-key"


def test_root_key_fallback_names_the_configured_user():
    reporter = BotUsageReporter(_ov_server(api_key_type="root"))

    assert reporter._headers(None) == {
        "X-API-Key": "bot-key",
        "X-OpenViking-Account": "bot-acct",
        "X-OpenViking-User": "bot-user",
    }
    assert BotUsageReporter(_ov_server(effective_auth_mode="dev"))._headers(None) == {}
    assert BotUsageReporter(_ov_server(server_url=""))._headers(None) is None


async def test_calls_without_tokens_or_server_are_not_queued(server):
    reporter = BotUsageReporter(_ov_server(), flush_interval=3600)
    reporter.record(provider="p", model_name="m", usage={"prompt_tokens": 0})
    BotUsageReporter(_ov_server(server_url="")).record(
        provider="p", model_name="m", usage={"prompt_tokens": 1}
    )
    await reporter.flush()

    assert server.requests == []


async def test_server_errors_are_retried_and_rejections_dropped(server):
    reporter = BotUsageReporter(_ov_server(), flush_interval=3600)
    reporter.record(provider="p", model_name="m", usage={"prompt_tokens": 1})

    server.status = 503
    await reporter.flush()
    assert reporter._pending
    server.status = 200
    await reporter.flush()
    assert not reporter._pending
    assert len(server.requests) == 2

    reporter.record(provider="p", model_name="m", usage={"prompt_tokens": 1})
    server.status = 401
    await reporter.flush()
    assert not reporter._pending


async def test_background_flush_sends_queued_calls(server):
    reporter = BotUsageReporter(_ov_server(), flush_interval=0.01)

    reporter.record(provider="p", model_name="m", usage={"completion_tokens": 7})
    for _ in range(100):
        if server.requests:
            break
        await asyncio.sleep(0.01)

    assert len(server.requests) == 1


def test_record_usage_is_a_noop_until_configured(monkeypatch):
    monkeypatch.setattr(bot_usage, "_reporter", None)

    bot_usage.record_usage(provider="p", model_name="m", usage={"prompt_tokens": 1})


async def test_repeated_failures_warn_once(server, monkeypatch):
    warnings = []
    monkeypatch.setattr(bot_usage.logger, "warning", lambda *args: warnings.append(args))
    reporter = BotUsageReporter(_ov_server(), flush_interval=3600)
    server.status = 404

    for _ in range(3):
        reporter.record(provider="p", model_name="m", usage={"prompt_tokens": 1})
        await reporter.flush()

    assert len(warnings) == 1
