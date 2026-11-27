# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Resolve which ``/mcp`` tools one caller may list and call.

ADMIN and ROOT set per-User allowlists in the Account configuration section
``mcp_tools.users``. The section lives in Account runtime configuration, which
only ROOT and ADMIN can write, so a User cannot lift their own restriction.
"""

from __future__ import annotations

from typing import Any, Optional

from openviking.server.dependencies import get_service_or_none
from openviking.server.identity import RequestContext, Role
from openviking_cli.exceptions import InvalidArgumentError


async def allowed_mcp_tools(ctx: Optional[RequestContext]) -> Optional[frozenset[str]]:
    """Return the caller's allowed tool names, or ``None`` when unrestricted.

    Anonymous discovery and ROOT are never restricted. Configuration read errors
    propagate so a broken policy store fails closed instead of exposing tools.
    """
    if ctx is None or ctx.role == Role.ROOT:
        return None
    # Before the service exists no tool can run, so there is no policy to apply.
    manager = getattr(get_service_or_none(), "runtime_config_manager", None)
    if manager is None:
        return None
    config = await manager.get_account(ctx.account_id, "mcp_tools")
    if config is None:
        return None
    allowed = config.users.get(ctx.user.user_id)
    return frozenset(allowed) if allowed is not None else None


def mcp_tool_catalog() -> list[dict[str, Any]]:
    """Describe every registered ``/mcp`` tool for the admin picker."""
    from openviking.server.mcp_endpoint import mcp

    catalog = []
    for tool in mcp._tool_manager.list_tools():
        summary = (tool.description or "").strip().split("\n\n", 1)[0]
        annotations = tool.annotations
        catalog.append(
            {
                "name": tool.name,
                "description": " ".join(summary.split()),
                "read_only": bool(annotations and annotations.readOnlyHint),
            }
        )
    return sorted(catalog, key=lambda item: item["name"])


async def read_user_mcp_tools(manager: Any, account_id: str, user_id: str) -> Optional[list[str]]:
    """Return one User's stored allowlist, or ``None`` when unrestricted."""
    config = await manager.get_account(account_id, "mcp_tools")
    if config is None:
        return None
    allowed = config.users.get(user_id)
    return list(allowed) if allowed is not None else None


async def clear_user_mcp_tools(manager: Any, account_id: str, user_id: str) -> None:
    """Drop a deleted User's allowlist so a later User with that id starts unrestricted."""
    if await read_user_mcp_tools(manager, account_id, user_id) is None:
        return
    await manager.patch_account(account_id, {"mcp_tools": {"users": {user_id: None}}})


async def write_user_mcp_tools(
    manager: Any,
    account_id: str,
    user_id: str,
    allowed_tools: Optional[list[str]],
) -> Optional[list[str]]:
    """Replace one User's allowlist; ``None`` removes the restriction."""
    if allowed_tools is not None:
        known = {tool["name"] for tool in mcp_tool_catalog()}
        unknown = sorted(set(allowed_tools) - known)
        if unknown:
            raise InvalidArgumentError(f"Unknown MCP tools: {', '.join(unknown)}")
    await manager.patch_account(account_id, {"mcp_tools": {"users": {user_id: allowed_tools}}})
    return await read_user_mcp_tools(manager, account_id, user_id)
