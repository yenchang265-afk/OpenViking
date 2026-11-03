# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Managed Connector credential-reference contract checks.

Fork note: upstream's Feishu/Lark, Meego and Confluence OAuth-reference tests
are omitted because this fork removed those integrations.
"""

import pytest

from openviking.connector import auth
from openviking.connector.client import ConnectorClient
from openviking.server.identity import RequestContext, Role
from openviking_cli.exceptions import InternalError, InvalidArgumentError
from openviking_cli.session.user_id import UserIdentifier


def _credential_reference(**changes):
    return {
        "account_id": "acct",
        "resource_id": "ov-resource",
        "user_id": "cloud-user",
        "ov_user_id": "ov-user",
        "type": "oauth",
        "platform": "dingtalk",
        "binding_version": 3,
        **changes,
    }


def test_extract_credential_reference_returns_none_without_reference():
    assert auth.extract_credential_reference(None) is None
    assert auth.extract_credential_reference({}) is None


def test_extract_credential_reference_normalizes_and_validates():
    ref = auth.extract_credential_reference(
        {"openviking_credential_ref": _credential_reference(account_id=" acct ")}
    )
    assert ref == _credential_reference()
    # binding_version is optional (some platforms omit it).
    unversioned_ref = _credential_reference(platform="other")
    unversioned_ref.pop("binding_version")
    resolved = auth.extract_credential_reference({"openviking_credential_ref": unversioned_ref})
    assert "binding_version" not in resolved


@pytest.mark.parametrize(
    "config",
    [
        {"openviking_credential_ref": _credential_reference(), "extra": 1},
        {"openviking_credential_ref": _credential_reference(type="static")},
        {"openviking_credential_ref": _credential_reference(account_id="")},
        {"openviking_credential_ref": {**_credential_reference(), "unknown": "x"}},
        {"openviking_credential_ref": {**_credential_reference(), "binding_version": "3"}},
        "not-a-dict",
    ],
)
def test_extract_credential_reference_rejects_invalid(config):
    with pytest.raises(InvalidArgumentError):
        auth.extract_credential_reference(config)


@pytest.mark.asyncio
async def test_resolve_connector_auth_config_uses_unified_resolver(monkeypatch):
    monkeypatch.setattr(
        auth, "credential_resolve_url", lambda: "https://connector.example/credential/resolve"
    )
    captured = {}

    def fake_resolve(_self, url, api_key, reference):
        captured.update(url=url, api_key=api_key, reference=reference)
        return {"auth_config": {"user_access_token": "live", "client_id": "c"}}

    monkeypatch.setattr(ConnectorClient, "resolve_connector_credential", fake_resolve)
    ctx = RequestContext(
        user=UserIdentifier("acct", "cloud-user"), role=Role.USER, api_key="user-key"
    )

    result = await auth.resolve_connector_auth_config(_credential_reference(), ctx)

    assert result == {"user_access_token": "live", "client_id": "c"}
    assert captured["url"] == "https://connector.example/credential/resolve"
    assert captured["api_key"] == "user-key"
    assert captured["reference"] == _credential_reference()


@pytest.mark.asyncio
async def test_resolve_connector_auth_config_requires_config_and_key(monkeypatch):
    ctx = RequestContext(user=UserIdentifier("acct", "cloud-user"), role=Role.USER, api_key="k")
    monkeypatch.setattr(auth, "credential_resolve_url", lambda: "")
    with pytest.raises(InvalidArgumentError, match="connector.auth is required"):
        await auth.resolve_connector_auth_config(_credential_reference(), ctx)

    monkeypatch.setattr(auth, "credential_resolve_url", lambda: "https://connector.example/resolve")
    no_key = RequestContext(user=UserIdentifier("acct", "cloud-user"), role=Role.USER, api_key="")
    with pytest.raises(InvalidArgumentError, match="requires an API key"):
        await auth.resolve_connector_auth_config(_credential_reference(), no_key)


@pytest.mark.asyncio
async def test_resolve_connector_auth_config_rejects_empty_auth_config(monkeypatch):
    monkeypatch.setattr(auth, "credential_resolve_url", lambda: "https://connector.example/resolve")
    monkeypatch.setattr(
        ConnectorClient,
        "resolve_connector_credential",
        lambda *_: {"auth_config": {}},
    )
    ctx = RequestContext(user=UserIdentifier("acct", "cloud-user"), role=Role.USER, api_key="k")
    with pytest.raises(InternalError, match="no auth_config"):
        await auth.resolve_connector_auth_config(_credential_reference(), ctx)
