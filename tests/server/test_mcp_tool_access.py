# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0

"""Per-user MCP tool allowlists: admin API and /mcp enforcement."""

from types import SimpleNamespace

import pytest
from mcp.server.fastmcp.exceptions import ToolError

import openviking.server.mcp_endpoint as mcp_endpoint
from openviking.config.account_config import AccountConfig
from openviking.config.binding import manager_over_source
from openviking.config.source import MemoryConfigSource
from openviking.server.dependencies import set_service
from openviking.server.identity import RequestContext, Role
from openviking_cli.session.user_id import UserIdentifier
from tests.server import test_admin_api as admin_api
from tests.server.test_admin_api import _uid, _wait_for_task, root_headers

# Shared Admin API fixtures.
admin_service = admin_api.admin_service
admin_app = admin_api.admin_app
admin_client = admin_api.admin_client
lightweight_admin_app = admin_api.lightweight_admin_app
lightweight_admin_client = admin_api.lightweight_admin_client
template_account = admin_api.template_account


def _url(account_id: str, user_id: str) -> str:
    return f"/api/v1/admin/accounts/{account_id}/users/{user_id}/mcp-tools"


async def _add_user(client, account_id: str, user_id: str, role: str = "user") -> dict:
    created = await client.post(
        f"/api/v1/admin/accounts/{account_id}/users",
        json={"user_id": user_id, "role": role},
        headers=root_headers(),
    )
    assert created.status_code == 200, created.text
    return {"X-API-Key": created.json()["result"]["user_key"]}


# ---------------------------------------------------------------------------
# AccountConfig model
# ---------------------------------------------------------------------------


def test_account_config_normalizes_mcp_tool_lists():
    config = AccountConfig.model_validate(
        {"mcp_tools": {"users": {"bob": ["read", "find", "read"], "eve": []}}}
    )
    assert config.mcp_tools.users == {"bob": ["find", "read"], "eve": []}


@pytest.mark.parametrize(
    "users",
    [
        {"bob": [""]},
        {"bob": [" "]},
        {"bad/user": ["find"]},
        {"bob": ["x" * 129]},
    ],
)
def test_account_config_rejects_invalid_mcp_tool_entries(users):
    with pytest.raises(ValueError):
        AccountConfig.model_validate({"mcp_tools": {"users": users}})


# ---------------------------------------------------------------------------
# Admin API
# ---------------------------------------------------------------------------


async def test_admin_sets_and_clears_user_mcp_tools(lightweight_admin_client, template_account):
    client = lightweight_admin_client
    account_id, admin_headers = template_account
    await _add_user(client, account_id, "bob")

    initial = await client.get(_url(account_id, "bob"), headers=admin_headers)
    assert initial.status_code == 200, initial.text
    result = initial.json()["result"]
    assert result["allowed_tools"] is None
    names = {tool["name"] for tool in result["available_tools"]}
    assert {"find", "read", "write", "list"} <= names
    assert all("read_only" in tool for tool in result["available_tools"])

    updated = await client.put(
        _url(account_id, "bob"),
        headers=admin_headers,
        json={"allowed_tools": ["read", "find", "read"]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["result"]["allowed_tools"] == ["find", "read"]
    loaded = await client.get(_url(account_id, "bob"), headers=admin_headers)
    assert loaded.json()["result"]["allowed_tools"] == ["find", "read"]

    cleared = await client.put(
        _url(account_id, "bob"), headers=admin_headers, json={"allowed_tools": None}
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["result"]["allowed_tools"] is None


async def test_root_can_set_user_mcp_tools(lightweight_admin_client, template_account):
    client = lightweight_admin_client
    account_id, _ = template_account
    await _add_user(client, account_id, "bob")
    updated = await client.put(
        _url(account_id, "bob"), headers=root_headers(), json={"allowed_tools": []}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["result"]["allowed_tools"] == []


async def test_user_mcp_tools_keep_other_users(lightweight_admin_client, template_account):
    client = lightweight_admin_client
    account_id, admin_headers = template_account
    await _add_user(client, account_id, "bob")
    await _add_user(client, account_id, "carol")
    for user_id, tools in (("bob", ["find"]), ("carol", ["read"])):
        response = await client.put(
            _url(account_id, user_id), headers=admin_headers, json={"allowed_tools": tools}
        )
        assert response.status_code == 200, response.text
    bob = await client.get(_url(account_id, "bob"), headers=admin_headers)
    carol = await client.get(_url(account_id, "carol"), headers=admin_headers)
    assert bob.json()["result"]["allowed_tools"] == ["find"]
    assert carol.json()["result"]["allowed_tools"] == ["read"]


async def test_user_cannot_change_own_mcp_tools_but_can_read_them(
    lightweight_admin_client, template_account
):
    client = lightweight_admin_client
    account_id, admin_headers = template_account
    user_headers = await _add_user(client, account_id, "bob")
    await _add_user(client, account_id, "carol")
    await client.put(
        _url(account_id, "bob"), headers=admin_headers, json={"allowed_tools": ["find"]}
    )

    denied = await client.put(
        _url(account_id, "bob"), headers=user_headers, json={"allowed_tools": None}
    )
    assert denied.status_code == 403, denied.text
    own = await client.get(_url(account_id, "bob"), headers=user_headers)
    assert own.status_code == 200, own.text
    assert own.json()["result"]["allowed_tools"] == ["find"]
    other = await client.get(_url(account_id, "carol"), headers=user_headers)
    assert other.status_code == 403, other.text


async def test_user_cannot_lift_restriction_through_account_configuration(
    lightweight_admin_client, template_account
):
    client = lightweight_admin_client
    account_id, _ = template_account
    user_headers = await _add_user(client, account_id, "bob")
    response = await client.patch(
        f"/api/v1/admin/accounts/{account_id}/configuration",
        headers=user_headers,
        json={"settings": {"mcp_tools": None}},
    )
    assert response.status_code == 403, response.text


async def test_admin_cannot_set_other_account_mcp_tools(lightweight_admin_client, template_account):
    client = lightweight_admin_client
    account_id, admin_headers = template_account
    other_account = _uid()
    created = await client.post(
        "/api/v1/admin/accounts",
        json={"account_id": other_account, "admin_user_id": "zed"},
        headers=root_headers(),
    )
    assert created.status_code == 200, created.text
    response = await client.put(
        _url(other_account, "zed"), headers=admin_headers, json={"allowed_tools": []}
    )
    assert response.status_code == 403, response.text


async def test_user_mcp_tools_reject_unknown_tool_and_user(
    lightweight_admin_client, template_account
):
    client = lightweight_admin_client
    account_id, admin_headers = template_account
    await _add_user(client, account_id, "bob")
    unknown_tool = await client.put(
        _url(account_id, "bob"), headers=admin_headers, json={"allowed_tools": ["nope"]}
    )
    assert unknown_tool.status_code == 400, unknown_tool.text
    assert "nope" in unknown_tool.text
    missing_user = await client.put(
        _url(account_id, "ghost"), headers=admin_headers, json={"allowed_tools": []}
    )
    assert missing_user.status_code == 404, missing_user.text


async def test_deleting_user_clears_their_mcp_tools(admin_client, admin_app):
    client = admin_client
    account_id = _uid()
    created = await client.post(
        "/api/v1/admin/accounts",
        json={"account_id": account_id, "admin_user_id": "alice"},
        headers=root_headers(),
    )
    assert created.status_code == 200, created.text
    for user_id, tools in (("bob", ["find"]), ("carol", ["read"])):
        await _add_user(client, account_id, user_id)
        response = await client.put(
            _url(account_id, user_id), headers=root_headers(), json={"allowed_tools": tools}
        )
        assert response.status_code == 200, response.text

    deleted = await client.delete(
        f"/api/v1/admin/accounts/{account_id}/users/bob", headers=root_headers()
    )
    assert deleted.status_code == 202, deleted.text
    task = await _wait_for_task(client, deleted.json()["result"]["task_id"])
    assert task["status"] == "completed", task

    config = admin_app.state.deletion_service._service.runtime_config_manager
    stored = await config.get_account(account_id, "mcp_tools")
    assert stored.users == {"carol": ["read"]}
    await _add_user(client, account_id, "bob")
    recreated = await client.get(_url(account_id, "bob"), headers=root_headers())
    assert recreated.json()["result"]["allowed_tools"] is None


# ---------------------------------------------------------------------------
# /mcp enforcement
# ---------------------------------------------------------------------------


@pytest.fixture
async def restricted_service():
    manager = manager_over_source(MemoryConfigSource())
    await manager.initialize()
    await manager.patch_account("acme", {"mcp_tools": {"users": {"bob": ["health", "find"]}}})
    set_service(SimpleNamespace(runtime_config_manager=manager))
    return manager


def _as(user_id: str, role: Role = Role.USER):
    ctx = RequestContext(user=UserIdentifier("acme", user_id), role=role)
    return mcp_endpoint._mcp_ctx.set(ctx)


async def test_mcp_lists_only_allowed_tools(restricted_service):
    token = _as("bob")
    try:
        names = {tool.name for tool in await mcp_endpoint.mcp.list_tools()}
    finally:
        mcp_endpoint._mcp_ctx.reset(token)
    assert names == {"health", "find"}


async def test_mcp_lists_all_tools_for_unrestricted_user(restricted_service):
    every = {tool.name for tool in mcp_endpoint.mcp._tool_manager.list_tools()}
    for user_id, role in (("carol", Role.USER), ("alice", Role.ADMIN)):
        token = _as(user_id, role)
        try:
            names = {tool.name for tool in await mcp_endpoint.mcp.list_tools()}
        finally:
            mcp_endpoint._mcp_ctx.reset(token)
        assert names == every


async def test_mcp_anonymous_discovery_lists_all_tools(restricted_service):
    assert mcp_endpoint._mcp_ctx.get() is None
    every = {tool.name for tool in mcp_endpoint.mcp._tool_manager.list_tools()}
    assert {tool.name for tool in await mcp_endpoint.mcp.list_tools()} == every


async def test_mcp_rejects_call_to_disallowed_tool(restricted_service, monkeypatch):
    calls = []

    async def fake_call(name, arguments, *, context, convert_result):
        calls.append(name)
        return []

    monkeypatch.setattr(mcp_endpoint.mcp._tool_manager, "call_tool", fake_call)
    token = _as("bob")
    try:
        with pytest.raises(ToolError, match="not available"):
            await mcp_endpoint.mcp.call_tool("write", {"uri": "viking://x", "content": "y"})
        await mcp_endpoint.mcp.call_tool("health", {})
    finally:
        mcp_endpoint._mcp_ctx.reset(token)
    assert calls == ["health"]


async def test_mcp_empty_allowlist_blocks_every_tool(restricted_service):
    await restricted_service.patch_account("acme", {"mcp_tools": {"users": {"bob": []}}})
    token = _as("bob")
    try:
        assert await mcp_endpoint.mcp.list_tools() == []
        with pytest.raises(ToolError):
            await mcp_endpoint.mcp.call_tool("health", {})
    finally:
        mcp_endpoint._mcp_ctx.reset(token)
