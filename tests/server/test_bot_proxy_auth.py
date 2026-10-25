# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0

"""Regression tests for bot proxy endpoint auth enforcement."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

import openviking.server.routers.bot as bot_router_module
import openviking.server.routers.compile as compile_router_module
from openviking.server.auth.plugins import DevAuthPlugin, TrustedAuthPlugin
from openviking.server.config import ServerConfig
from openviking.server.identity import AuthMode
from openviking.service.task_tracker import TaskRecord, TaskStatus


def test_set_bot_api_key_updates_module_state():
    bot_router_module.set_bot_api_key("gateway-secret")
    assert bot_router_module.BOT_API_KEY == "gateway-secret"

    bot_router_module.set_bot_api_key("")
    assert bot_router_module.BOT_API_KEY == ""


async def test_create_bot_proxy_client_disables_env_proxy():
    async with bot_router_module._create_bot_proxy_client() as client:
        assert isinstance(client, httpx.AsyncClient)
        assert client._trust_env is False


@pytest.mark.asyncio
async def test_feedback_proxy_forwards_request(monkeypatch):
    forwarded = {}

    class FakeResponse:
        def __init__(self):
            self.status_code = 200
            self.text = '{"accepted": true}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"accepted": True, "response_id": "resp-123"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json, headers, timeout):
            forwarded["url"] = url
            forwarded["json"] = json
            forwarded["headers"] = headers
            forwarded["timeout"] = timeout
            return FakeResponse()

    monkeypatch.setattr(bot_router_module, "BOT_API_URL", "http://127.0.0.1:18790")
    monkeypatch.setattr(bot_router_module, "BOT_API_KEY", "gateway-secret")
    monkeypatch.setattr(bot_router_module, "_create_bot_proxy_client", lambda: FakeClient())

    app = FastAPI()
    app.state.config = SimpleNamespace(get_effective_auth_mode=lambda: AuthMode.DEV)
    app.state.auth_plugin = DevAuthPlugin()
    app.include_router(bot_router_module.router, prefix="/bot/v1")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/bot/v1/feedback",
            json={
                "session_id": "session-1",
                "response_id": "resp-123",
                "feedback_type": "thumb_up",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"accepted": True, "response_id": "resp-123"}
    assert forwarded["url"] == "http://127.0.0.1:18790/bot/v1/feedback"
    assert forwarded["json"]["response_id"] == "resp-123"
    assert forwarded["headers"]["X-Gateway-Token"] == "gateway-secret"
    assert forwarded["timeout"] == 30.0


@pytest.mark.asyncio
async def test_interrupt_proxy_forwards_session_interrupt(monkeypatch):
    forwarded = {}

    class FakeResponse:
        status_code = 200
        text = '{"interrupted": true}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"interrupted": True}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, headers, timeout):
            forwarded["url"] = url
            forwarded["headers"] = headers
            forwarded["timeout"] = timeout
            return FakeResponse()

    monkeypatch.setattr(bot_router_module, "BOT_API_URL", "http://127.0.0.1:18790")
    monkeypatch.setattr(bot_router_module, "BOT_API_KEY", "gateway-secret")
    monkeypatch.setattr(bot_router_module, "_create_bot_proxy_client", lambda: FakeClient())

    app = FastAPI()
    app.state.config = SimpleNamespace(get_effective_auth_mode=lambda: AuthMode.DEV)
    app.state.auth_plugin = DevAuthPlugin()
    app.include_router(bot_router_module.router, prefix="/bot/v1")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/bot/v1/sessions/session%201/interrupt")

    assert response.status_code == 200
    assert response.json() == {"interrupted": True}
    assert forwarded["url"] == "http://127.0.0.1:18790/bot/v1/sessions/session%201/interrupt"
    assert forwarded["headers"]["X-Gateway-Token"] == "gateway-secret"
    assert forwarded["timeout"] == 30.0


@pytest.mark.asyncio
async def test_steer_proxy_forwards_message_body(monkeypatch):
    forwarded = {}

    class FakeResponse:
        status_code = 200
        text = '{"accepted": true}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"accepted": True}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json, headers, timeout):
            forwarded["url"] = url
            forwarded["json"] = json
            forwarded["headers"] = headers
            forwarded["timeout"] = timeout
            return FakeResponse()

    monkeypatch.setattr(bot_router_module, "BOT_API_URL", "http://127.0.0.1:18790")
    monkeypatch.setattr(bot_router_module, "BOT_API_KEY", "gateway-secret")
    monkeypatch.setattr(bot_router_module, "_create_bot_proxy_client", lambda: FakeClient())

    app = FastAPI()
    app.state.config = ServerConfig(
        auth_mode="trusted",
        host="127.0.0.1",
        port=1944,
        root_api_key="active-user-key",
    )
    app.state.auth_plugin = TrustedAuthPlugin()
    app.include_router(bot_router_module.router, prefix="/bot/v1")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/bot/v1/sessions/session%201/steer",
            headers={
                "X-API-Key": "active-user-key",
                "X-OpenViking-Account": "acct",
                "X-OpenViking-User": "alice",
            },
            json={"message": "follow up", "user_id": "ignored"},
        )

    assert response.status_code == 200
    assert response.json() == {"accepted": True}
    assert forwarded["url"] == "http://127.0.0.1:18790/bot/v1/sessions/session%201/steer"
    assert forwarded["json"]["message"] == "follow up"
    assert forwarded["json"]["openviking_connection"]["api_key"] == "active-user-key"
    assert forwarded["json"]["openviking_connection"]["user_id"] == "alice"
    assert forwarded["headers"]["X-Gateway-Token"] == "gateway-secret"
    assert forwarded["timeout"] == 30.0


@pytest.mark.asyncio
async def test_chat_proxy_attaches_authenticated_openviking_connection(monkeypatch):
    forwarded = {}

    class FakeResponse:
        status_code = 200
        text = '{"session_id": "session-1", "message": "ok"}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"session_id": "session-1", "message": "ok"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json, headers, timeout):
            forwarded["url"] = url
            forwarded["json"] = json
            forwarded["headers"] = headers
            forwarded["timeout"] = timeout
            return FakeResponse()

    monkeypatch.setattr(bot_router_module, "BOT_API_URL", "http://127.0.0.1:18790")
    monkeypatch.setattr(bot_router_module, "BOT_API_KEY", "gateway-secret")
    monkeypatch.setattr(bot_router_module, "_create_bot_proxy_client", lambda: FakeClient())

    app = FastAPI()
    app.state.config = ServerConfig(
        auth_mode="trusted", root_api_key="active-root-key", host="127.0.0.1", port=1944
    )
    app.state.auth_plugin = TrustedAuthPlugin()
    app.include_router(bot_router_module.router, prefix="/bot/v1")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/bot/v1/chat",
            headers={
                "X-API-Key": "active-root-key",
                "X-OpenViking-Account": "acct",
                "X-OpenViking-User": "alice",
            },
            json={"message": "hello", "user_id": "ignored-by-proxy-identity"},
        )

    assert response.status_code == 200
    assert forwarded["url"] == "http://127.0.0.1:18790/bot/v1/chat"
    assert forwarded["json"]["openviking_connection"] == {
        "api_key": "active-root-key",
        "account_id": "acct",
        "user_id": "alice",
        "agent_id": "web-playground",
        "role": "user",
        "api_key_type": "root",
        "server_url": "http://127.0.0.1:1944",
    }
    assert forwarded["headers"]["X-Gateway-Token"] == "gateway-secret"
    assert forwarded["timeout"] == 300.0


@pytest.mark.asyncio
async def test_compile_route_uses_ov_owned_task_and_rejects_legacy_routes(monkeypatch):
    calls = {}

    class FakeCompileService:
        async def create(self, body, *, ctx):
            calls["request"] = body.model_dump(mode="json", by_alias=True)
            calls["owner"] = (ctx.account_id, ctx.user.user_id)
            return TaskRecord(
                task_id="cmp_1",
                task_type="compile",
                status=TaskStatus.PENDING,
                stage="queued",
                resource_id="viking://resources/source",
                account_id="acct",
                user_id="alice",
                meta={"request": {"to": "viking://resources/wiki"}},
            )

    service = SimpleNamespace(compile=FakeCompileService())
    monkeypatch.setattr(compile_router_module, "get_service", lambda: service)

    app = FastAPI()
    app.state.config = ServerConfig(
        auth_mode="trusted", root_api_key="active-root-key", host="127.0.0.1", port=1944
    )
    app.state.auth_plugin = TrustedAuthPlugin()
    app.include_router(compile_router_module.router)
    app.include_router(bot_router_module.router, prefix="/bot/v1")
    transport = httpx.ASGITransport(app=app)
    headers = {
        "X-API-Key": "active-root-key",
        "X-OpenViking-Account": "acct",
        "X-OpenViking-User": "alice",
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        created = await client.post(
            "/api/v1/compile",
            headers=headers,
            json={
                "from": ["viking://resources/source"],
                "to": "viking://resources/wiki",
                "skill": "viking://agent/skills/wiki",
                "instruction": "  Keep supporting evidence.  ",
            },
        )
        assert calls["request"]["instruction"] == "Keep supporting evidence."
        legacy_created = await client.post("/bot/v1/compile", headers=headers, json={})
        legacy_status = await client.get("/bot/v1/compile/cmp_1", headers=headers)
        legacy_cancel = await client.post(
            "/bot/v1/compile/cmp_1/cancel",
            headers=headers,
        )

    assert created.status_code == 202
    assert created.json()["result"]["task_id"] == "cmp_1"
    assert legacy_created.status_code == 400
    assert "POST /api/v1/compile" in legacy_created.json()["detail"]
    assert "GET /api/v1/tasks/{task_id}" in legacy_created.json()["detail"]
    assert legacy_status.status_code == 400
    assert "GET /api/v1/tasks/{task_id}" in legacy_status.json()["detail"]
    assert legacy_cancel.status_code == 400
    assert "POST /api/v1/tasks/{task_id}/cancel" in legacy_cancel.json()["detail"]
    assert calls["owner"] == ("acct", "alice")


@pytest.mark.asyncio
async def test_chat_proxy_strips_client_openviking_connection_in_dev_mode(monkeypatch):
    """Dev/no-API-key proxy must not forward a browser-supplied connection.

    The Bot gateway trusts loopback openviking_connection from this proxy, so
    leaving a client-claimed identity intact would let Studio forge account/user
    /actor_peer on the --with-bot path (#4650 trust-model follow-up).
    """
    forwarded = {}

    class FakeResponse:
        status_code = 200
        text = '{"session_id": "session-1", "message": "ok"}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"session_id": "session-1", "message": "ok"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json, headers, timeout):
            forwarded["json"] = json
            return FakeResponse()

    monkeypatch.setattr(bot_router_module, "BOT_API_URL", "http://127.0.0.1:18790")
    monkeypatch.setattr(bot_router_module, "BOT_API_KEY", "")
    monkeypatch.setattr(bot_router_module, "_create_bot_proxy_client", lambda: FakeClient())

    app = FastAPI()
    app.state.config = SimpleNamespace(get_effective_auth_mode=lambda: AuthMode.DEV)
    app.state.auth_plugin = DevAuthPlugin()
    app.include_router(bot_router_module.router, prefix="/bot/v1")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/bot/v1/chat",
            json={
                "message": "hello",
                "openviking_connection": {
                    "account_id": "forged-acct",
                    "user_id": "forged-user",
                    "actor_peer_id": "forged-peer",
                    "agent_id": "forged-agent",
                    "role": "root",
                    "api_key_type": "root",
                    "server_url": "http://evil.example",
                },
            },
        )

    assert response.status_code == 200
    assert "openviking_connection" not in forwarded["json"]
    assert forwarded["json"].get("user_id") == "default"


@pytest.mark.asyncio
async def test_chat_stream_proxy_preserves_sse_event_boundaries(monkeypatch):
    payload = (
        'data: {"event":"reasoning_delta","data":"thinking"}\n\n'
        'data: {"event":"response","data":{"content":"done"}}\n\n'
    )

    class FakeResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self):
            return None

        async def aiter_text(self):
            yield payload[:30]
            yield payload[30:]

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(bot_router_module, "BOT_API_URL", "http://127.0.0.1:18790")
    monkeypatch.setattr(bot_router_module, "_create_bot_proxy_client", lambda: FakeClient())

    app = FastAPI()
    app.state.config = SimpleNamespace(get_effective_auth_mode=lambda: AuthMode.DEV)
    app.state.auth_plugin = DevAuthPlugin()
    app.include_router(bot_router_module.router, prefix="/bot/v1")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/bot/v1/chat/stream",
            json={"message": "hello"},
        )

    assert response.status_code == 200
    assert response.text == payload
