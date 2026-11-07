# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""External OAuth contract, lifetime and identity regression checks."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from openviking.connector import auth
from openviking.connector.client import ConnectorClient
from openviking.server.identity import RequestContext, Role
from openviking_cli.exceptions import InternalError, InvalidArgumentError
from openviking_cli.session.user_id import UserIdentifier

REFERENCE = {
    "account_id": "cloud-account",
    "user_id": "cloud-user",
    "ov_user_id": "alice",
    "platform": "dingtalk",
    "type": "oauth",
}


@pytest.fixture(autouse=True)
def external_endpoint(monkeypatch):
    monkeypatch.setattr(
        auth, "external_auth_url", lambda: "https://connector.example/oauth/access_token"
    )


@pytest.mark.parametrize(
    "reference", [None, {}, {**REFERENCE, "ov_user_id": "bob"}, {**REFERENCE, "platform": "git"}]
)
def test_reference_identity_is_checked(reference):
    with pytest.raises(InvalidArgumentError):
        auth.validate_oauth_ref(reference, "alice")


def _credential_reference(**changes):
    return {
        "account_id": "acct",
        "resource_id": "ov-resource",
        "user_id": "cloud-user",
        "ov_user_id": "ov-user",
        "ov_account_id": "default",
        "type": "oauth",
        "platform": "dingtalk",
        "binding_version": 3,
        **changes,
    }


def test_extract_credential_reference_returns_none_without_reference():
    assert auth.extract_credential_reference(None) is None
    assert auth.extract_credential_reference({}) is None


@pytest.mark.parametrize(
    "config",
    [
        {"openviking_credential_ref": _credential_reference(), "extra": 1},
        {"openviking_credential_ref": _credential_reference(type="static")},
        {"openviking_credential_ref": _credential_reference(account_id="")},
        {"openviking_credential_ref": {**_credential_reference(), "unknown": "x"}},
        {"openviking_credential_ref": {**_credential_reference(), "binding_version": "3"}},
        {"openviking_credential_ref": _credential_reference(binding_version=0)},
        {"openviking_credential_ref": _credential_reference(ov_account_id=" ")},
        {"openviking_credential_ref": _credential_reference(ov_account_id=123)},
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
        user=UserIdentifier("default", "ov-user"), role=Role.USER, api_key="user-key"
    )

    result = await auth.resolve_connector_auth_config(_credential_reference(), ctx)

    assert result == {"user_access_token": "live", "client_id": "c"}
    assert captured["url"] == "https://connector.example/credential/resolve"
    assert captured["api_key"] == "user-key"
    assert captured["reference"] == _credential_reference()


@pytest.mark.asyncio
async def test_resolve_connector_auth_config_requires_config_and_key(monkeypatch):
    ctx = RequestContext(user=UserIdentifier("default", "ov-user"), role=Role.USER, api_key="k")
    monkeypatch.setattr(auth, "credential_resolve_url", lambda: "")
    with pytest.raises(InvalidArgumentError, match="connector.auth is required"):
        await auth.resolve_connector_auth_config(_credential_reference(), ctx)

    monkeypatch.setattr(auth, "credential_resolve_url", lambda: "https://connector.example/resolve")
    no_key = RequestContext(user=UserIdentifier("default", "ov-user"), role=Role.USER, api_key="")
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
    ctx = RequestContext(user=UserIdentifier("default", "ov-user"), role=Role.USER, api_key="k")
    with pytest.raises(InternalError, match="no auth_config"):
        await auth.resolve_connector_auth_config(_credential_reference(), ctx)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("space", "user", "legacy"),
    [("space-b", "ov-user", False), ("default", "other-user", False), ("space-b", "ov-user", True)],
)
async def test_dingtalk_reference_rejects_cross_space_or_user_before_network(
    monkeypatch, space, user, legacy
):
    fetch = Mock()
    monkeypatch.setattr(ConnectorClient, "resolve_connector_credential", fetch)
    reference = _credential_reference()
    if legacy:
        reference.pop("ov_account_id")
    ctx = RequestContext(user=UserIdentifier(space, user), role=Role.USER, api_key="k")
    with pytest.raises(InvalidArgumentError, match="does not belong"):
        await auth.resolve_connector_auth_config(reference, ctx)
    fetch.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("space", ["default", "space-b"])
async def test_dingtalk_reference_preserves_target_space(monkeypatch, space):
    monkeypatch.setattr(auth, "credential_resolve_url", lambda: "https://connector.example/resolve")
    fetch = Mock(return_value={"auth_config": {"user_access_token": "live-token"}})
    monkeypatch.setattr(ConnectorClient, "resolve_connector_credential", fetch)
    ctx = RequestContext(user=UserIdentifier(space, "ov-user"), role=Role.USER, api_key="k")
    reference = _credential_reference(ov_account_id=space)
    if space == "default":
        reference.pop("ov_account_id")
    await auth.resolve_connector_auth_config(reference, ctx)
    assert fetch.call_args.args[-1]["ov_account_id"] == space


@pytest.mark.asyncio
async def test_confluence_credentials_use_bearer_token_and_validate_reference(monkeypatch):
    ctx = SimpleNamespace(user=SimpleNamespace(user_id="alice"), api_key="caller-key")
    reference = {**REFERENCE, "platform": "confluence"}
    fetch = Mock(return_value={"access_token": " token ", "expires_at": 4102444800})
    monkeypatch.setattr(ConnectorClient, "get_oauth_access_token", fetch)
    args = {auth.OAUTH_REF_ARG: reference}

    assert await auth.confluence_auth_config(args, ctx) == {"access_token": "token"}

    fetch.assert_called_once_with(auth.external_auth_url(), "caller-key", reference)
    assert args == {auth.OAUTH_REF_ARG: reference}
    with pytest.raises(InvalidArgumentError):
        auth.validate_oauth_ref(reference, "alice")
    for invalid in (None, REFERENCE, {**reference, "ov_user_id": "bob"}):
        with pytest.raises(InvalidArgumentError):
            await auth.confluence_auth_config({auth.OAUTH_REF_ARG: invalid}, ctx)
    for extra in (
        {"auth_config": {"api_token": "token"}},
        {"access_token": "token"},
        {"api_token": "token"},
        {"email": "user@example.com"},
    ):
        with pytest.raises(InvalidArgumentError):
            await auth.confluence_auth_config({**args, **extra}, ctx)
    assert fetch.call_count == 1
