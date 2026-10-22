"""Bot model-call token reporting to the Business Context Platform usage dashboard."""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from vikingbot.observability import bot_usage
from vikingbot.observability.bot_usage import BotUsageReporter, usage_connection
from vikingbot.providers.vlm_adapter import VLMProviderAdapter

from openviking.models.vlm.backends.openai_vlm import OpenAIVLM
from openviking.observability.events import try_publish_event, unregister_event_subscriber


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
        if isinstance(self.status, Exception):
            raise self.status
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
    reporter = BotUsageReporter(_ov_server(), gateway_token="gw", flush_interval=3600)
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


def test_root_key_fallback_names_the_configured_user_only_in_trusted_mode():
    trusted = BotUsageReporter(
        _ov_server(api_key_type="root", effective_auth_mode="trusted"), gateway_token="gw"
    )

    assert trusted._headers(None) == {
        "X-API-Key": "bot-key",
        "X-OpenViking-Account": "bot-acct",
        "X-OpenViking-User": "bot-user",
    }
    # Like VikingClient, api_key mode treats the key as a user key.
    api_key_mode = BotUsageReporter(_ov_server(api_key_type="root"), gateway_token="gw")
    assert api_key_mode._headers(None) == {"X-API-Key": "bot-key"}
    # Without an effective mode, a root key type means trusted.
    unset = BotUsageReporter(
        _ov_server(api_key_type="root", effective_auth_mode=""), gateway_token="gw"
    )
    assert "X-OpenViking-User" in unset._headers(None)
    assert (
        BotUsageReporter(_ov_server(effective_auth_mode="dev"), gateway_token="gw")._headers(None)
        == {}
    )
    assert BotUsageReporter(_ov_server(server_url=""), gateway_token="gw")._headers(None) is None


async def test_calls_without_tokens_or_server_are_not_queued(server):
    reporter = BotUsageReporter(_ov_server(), gateway_token="gw", flush_interval=3600)
    reporter.record(provider="p", model_name="m", usage={"prompt_tokens": 0})
    BotUsageReporter(_ov_server(server_url=""), gateway_token="gw").record(
        provider="p", model_name="m", usage={"prompt_tokens": 1}
    )
    await reporter.flush()

    assert server.requests == []


async def test_server_errors_are_retried_and_rejections_dropped(server):
    reporter = BotUsageReporter(_ov_server(), gateway_token="gw", flush_interval=3600)
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
    reporter = BotUsageReporter(_ov_server(), gateway_token="gw", flush_interval=0.01)

    reporter.record(provider="p", model_name="m", usage={"completion_tokens": 7})
    for _ in range(100):
        if server.requests:
            break
        await asyncio.sleep(0.01)

    assert len(server.requests) == 1


async def test_unconfigured_process_ignores_events_and_closes_cleanly(monkeypatch):
    monkeypatch.setattr(bot_usage, "_reporter", None)

    bot_usage._on_event(
        bot_usage.ObservabilityEvent(event_name="vlm.call", payload={"prompt_tokens": 1})
    )
    await bot_usage.aclose()


async def test_repeated_failures_warn_once(server, monkeypatch):
    warnings = []
    monkeypatch.setattr(bot_usage.logger, "warning", lambda *args: warnings.append(args))
    reporter = BotUsageReporter(_ov_server(), gateway_token="gw", flush_interval=3600)
    server.status = 404

    for _ in range(3):
        reporter.record(provider="p", model_name="m", usage={"prompt_tokens": 1})
        await reporter.flush()

    assert len(warnings) == 1


async def test_only_unsent_reports_are_retried(server):
    reporter = BotUsageReporter(_ov_server(), gateway_token="gw", flush_interval=3600)

    reporter.record(provider="p", model_name="m", usage={"prompt_tokens": 1})
    server.status = httpx.ConnectError("refused")
    await reporter.flush()
    assert reporter._pending

    # A timeout after sending may already be recorded; resending would double-count.
    server.status = httpx.ReadTimeout("slow")
    await reporter.flush()
    assert not reporter._pending

    reporter.record(provider="p", model_name="m", usage={"prompt_tokens": 1})
    server.status = httpx.InvalidURL("bad url")
    await reporter.flush()
    assert not reporter._pending


def test_oversized_counts_are_clamped_to_the_server_limit():
    reporter = BotUsageReporter(_ov_server(), gateway_token="gw")

    reporter.record(provider="p", model_name="m", usage={"prompt_tokens": 10**12})

    [calls] = reporter._pending.values()
    assert calls[0]["prompt_tokens"] == bot_usage.MAX_CALL_TOKENS


async def test_aclose_sends_queued_calls(server):
    reporter = BotUsageReporter(_ov_server(), gateway_token="gw", flush_interval=3600)
    reporter.record(provider="p", model_name="m", usage={"prompt_tokens": 3})

    await reporter.aclose()

    assert len(server.requests) == 1
    assert not reporter._pending


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(bot_usage, "_reporter", None)
    reporter = bot_usage.configure(_ov_server(), gateway_token="gw")
    reporter._flush_interval = 3600
    yield reporter
    unregister_event_subscriber("bot_usage")


def test_vlm_call_events_are_recorded_with_the_request_identity(configured):
    connection = {"api_key": "user-key", "account_id": "acct-1", "user_id": "user-1"}

    with usage_connection(connection):
        try_publish_event(
            "vlm.call",
            {"provider": "openai", "model_name": "m", "prompt_tokens": 9, "completion_tokens": 2},
        )
    try_publish_event("embedding.call", {"prompt_tokens": 50})
    try_publish_event("vlm.call", {"prompt_tokens": 0, "completion_tokens": 0})

    [(key, calls)] = configured._pending.items()
    assert dict(key)["X-OpenViking-User"] == "user-1"
    assert [(c["model_name"], c["prompt_tokens"], c["completion_tokens"]) for c in calls] == [
        ("m", 9, 2)
    ]


async def test_adapter_chat_reaches_the_reporter(configured, monkeypatch):
    raw_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="hi", tool_calls=None), finish_reason="stop"
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=13,
            completion_tokens=5,
            total_tokens=18,
            prompt_tokens_details=None,
            completion_tokens_details=None,
        ),
    )

    async def create(**_kwargs):
        return raw_response

    vlm = OpenAIVLM({"provider": "openai", "model": "gpt-test"})
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(vlm, "get_async_client", lambda: client)
    disabled_langfuse = SimpleNamespace(enabled=False, _client=None)
    adapter = VLMProviderAdapter(vlm, "gpt-test", langfuse_client=disabled_langfuse)

    await adapter.chat(messages=[{"role": "user", "content": "hello"}])

    [calls] = configured._pending.values()
    assert [(c["provider"], c["model_name"], c["prompt_tokens"]) for c in calls] == [
        ("openai", "gpt-test", 13)
    ]


async def test_reports_carry_the_gateway_token_and_need_one(server):
    reporter = BotUsageReporter(_ov_server(), gateway_token="gw", flush_interval=3600)
    reporter.record(provider="p", model_name="m", usage={"prompt_tokens": 1})
    await reporter.flush()

    [request] = server.requests
    assert request.headers["X-Gateway-Token"] == "gw"
    # The server only accepts the gateway it manages; without its token nothing is queued.
    tokenless = BotUsageReporter(_ov_server(), gateway_token="")
    tokenless.record(provider="p", model_name="m", usage={"prompt_tokens": 1})
    assert not tokenless._pending
