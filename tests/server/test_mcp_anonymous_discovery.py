# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0

"""Unauthenticated MCP clients may discover tools but not call them.

The /mcp identity middleware lets a request without valid credentials through
only when every JSON-RPC message in it is part of the handshake or the tool
listing. Every other request keeps the 401 it got before.
"""

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from starlette.routing import Route

import openviking.server.mcp_endpoint as mcp_endpoint
from openviking.server.identity import AuthMode
from openviking.server.mcp_endpoint import _IdentityASGIMiddleware, _mcp_ctx
from openviking_cli.exceptions import UnauthenticatedError


class _RejectingAuthPlugin:
    """Stands in for API-key mode with no key presented."""

    auth_mode = AuthMode.API_KEY.value

    async def resolve_identity(self, request, **_kwargs):
        raise UnauthenticatedError("Missing API Key")


def _app(endpoint) -> FastAPI:
    app = FastAPI()
    app.state.config = SimpleNamespace(get_effective_auth_mode=lambda: AuthMode.API_KEY)
    app.state.auth_plugin = _RejectingAuthPlugin()
    app.routes.append(Route("/mcp", endpoint=endpoint, methods=["POST"]))
    return app


def _recording_downstream(seen: dict):
    async def downstream(scope, receive, send):
        seen["ctx"] = _mcp_ctx.get()
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body"):
                break
        seen["body"] = body
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": b'{"ok": true}'})

    return downstream


async def _post(app, content: bytes) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://ov.test") as client:
        return await client.post(
            "/mcp", content=content, headers={"content-type": "application/json"}
        )


def _rpc(method: str, **extra) -> dict:
    return {"jsonrpc": "2.0", "id": 1, "method": method, **extra}


@pytest.mark.parametrize(
    "payload",
    [
        _rpc("tools/list"),
        _rpc("initialize", params={"protocolVersion": "2025-06-18"}),
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        [_rpc("initialize"), _rpc("tools/list")],
    ],
    ids=["tools_list", "initialize", "initialized_notification", "batch"],
)
async def test_anonymous_discovery_reaches_mcp_without_identity(payload):
    seen: dict = {}
    content = json.dumps(payload).encode()

    response = await _post(_app(_IdentityASGIMiddleware(_recording_downstream(seen))), content)

    assert response.status_code == 200
    assert seen["ctx"] is None
    # The middleware consumed the body to inspect it; the MCP app must still get all of it.
    assert seen["body"] == content


@pytest.mark.parametrize(
    "content",
    [
        json.dumps(_rpc("tools/call", params={"name": "health", "arguments": {}})).encode(),
        json.dumps(_rpc("resources/list")).encode(),
        json.dumps(_rpc("ping")).encode(),
        json.dumps([_rpc("tools/list"), _rpc("tools/call")]).encode(),
        json.dumps([]).encode(),
        json.dumps({"jsonrpc": "2.0", "id": 1}).encode(),
        json.dumps({"jsonrpc": "2.0", "result": {}, "method": "tools/list"}).encode(),
        b"not json",
        b"",
    ],
    ids=[
        "tools_call",
        "resources_list",
        "ping",
        "batch_with_call",
        "empty_batch",
        "no_method",
        "response_shaped",
        "malformed",
        "empty_body",
    ],
)
async def test_anonymous_non_discovery_requests_stay_unauthorized(content):
    async def downstream(scope, receive, send):
        raise AssertionError("unauthenticated request must not reach the MCP app")

    response = await _post(_app(_IdentityASGIMiddleware(downstream)), content)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == -32001


async def test_anonymous_oversized_body_stays_unauthorized():
    async def downstream(scope, receive, send):
        raise AssertionError("oversized unauthenticated request must not reach the MCP app")

    padding = "x" * (mcp_endpoint._ANONYMOUS_MCP_BODY_LIMIT + 1)
    content = json.dumps(_rpc("tools/list", params={"pad": padding})).encode()

    response = await _post(_app(_IdentityASGIMiddleware(downstream)), content)

    assert response.status_code == 401


async def test_anonymous_client_lists_real_tools_but_cannot_call_them(monkeypatch):
    # FastMCP's session manager is single-use; give this test its own.
    monkeypatch.setattr(mcp_endpoint.mcp, "_session_manager", None)
    app = _app(mcp_endpoint.create_mcp_app())
    headers = {"accept": "application/json, text/event-stream"}

    async with mcp_endpoint.mcp_lifespan():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://ov.test") as client:
            listed = await client.post("/mcp", json=_rpc("tools/list"), headers=headers)
            called = await client.post(
                "/mcp",
                json=_rpc("tools/call", params={"name": "health", "arguments": {}}),
                headers=headers,
            )

    assert listed.status_code == 200
    data_line = next(line for line in listed.text.splitlines() if line.startswith("data:"))
    names = {tool["name"] for tool in json.loads(data_line[5:])["result"]["tools"]}
    assert {"find", "read", "health", "list"} <= names
    assert called.status_code == 401
