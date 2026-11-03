# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Task-scoped access to centrally managed external Connector credentials.

Fork note: upstream also carries a Feishu/Lark (and Confluence/Meego) OAuth
``args.openviking_oauth_ref`` channel here. This fork removed Feishu/Lark
support, so only the platform-agnostic credential-reference resolver remains.
"""

import asyncio
from typing import Any, Dict, Optional

from openviking.connector.client import ConnectorClient
from openviking.server.identity import RequestContext
from openviking_cli.exceptions import InternalError, InvalidArgumentError

CONNECTOR_AUTH_CONFIG_FIELD = "connector_auth_config"
CREDENTIAL_REF_KEY = "openviking_credential_ref"
_CREDENTIAL_REF_REQUIRED_KEYS = (
    "account_id",
    "resource_id",
    "user_id",
    "ov_user_id",
    "platform",
    "type",
)


def credential_resolve_url() -> str:
    from openviking_cli.utils.config.open_viking_config import get_openviking_config

    return get_openviking_config().connector.credential_resolve_url()


def extract_credential_reference(
    connector_auth_config: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Return the private credential reference, or None when absent.

    The top-level ``connector_auth_config`` is managed by OpenViking and only
    ever carries one key, ``openviking_credential_ref``. A present reference is
    the single platform-agnostic signal that this import resolves credentials
    through the unified resolver.
    """
    if not connector_auth_config:
        return None
    if not isinstance(connector_auth_config, dict):
        raise InvalidArgumentError("connector_auth_config must be an object.")
    reference = connector_auth_config.get(CREDENTIAL_REF_KEY)
    if reference is None:
        return None
    if set(connector_auth_config) != {CREDENTIAL_REF_KEY}:
        raise InvalidArgumentError("connector_auth_config contains unexpected fields.")
    return validate_credential_reference(reference)


def validate_credential_reference(value: Any) -> Dict[str, Any]:
    """Validate the OpenViking-managed credential reference shape.

    ``binding_version`` is optional (DingTalk sends a positive integer). All
    other fields are non-empty strings and ``type`` is ``oauth``. The reference
    is forwarded verbatim to the unified resolver, so the kernel never inspects
    platform-specific credential fields here.
    """
    if not isinstance(value, dict):
        raise InvalidArgumentError(
            "connector_auth_config contains an invalid credential reference."
        )
    extra = set(value) - set(_CREDENTIAL_REF_REQUIRED_KEYS) - {"binding_version"}
    if extra or any(key not in value for key in _CREDENTIAL_REF_REQUIRED_KEYS):
        raise InvalidArgumentError(
            "connector_auth_config contains an invalid credential reference."
        )
    reference: Dict[str, Any] = {}
    for key in _CREDENTIAL_REF_REQUIRED_KEYS:
        field = value[key]
        if not isinstance(field, str) or not field.strip():
            raise InvalidArgumentError(
                "connector_auth_config contains an invalid credential reference."
            )
        reference[key] = field.strip()
    if reference["type"] != "oauth":
        raise InvalidArgumentError(
            "connector_auth_config credential reference must be an OAuth type."
        )
    if "binding_version" in value:
        binding_version = value["binding_version"]
        if isinstance(binding_version, bool) or not isinstance(binding_version, int):
            raise InvalidArgumentError("connector_auth_config binding_version must be an integer.")
        reference["binding_version"] = binding_version
    return reference


async def resolve_connector_auth_config(
    reference: Dict[str, Any], ctx: RequestContext
) -> Dict[str, Any]:
    """Resolve the current Connector ``auth_config`` for a credential reference.

    Each import and each watch round resolves credentials just before use so a
    refreshed token is always current; the resolver assembles the full
    ``auth_config`` for the target Connector, and the kernel forwards it
    verbatim without persisting any token or application secret.
    """
    resolve_url = credential_resolve_url()
    if not resolve_url:
        raise InvalidArgumentError(
            "connector.auth is required to resolve external Connector credentials."
        )
    api_key = ctx.api_key or ""
    if not api_key:
        raise InvalidArgumentError("External Connector authorization requires an API key.")
    client = ConnectorClient("", "", account_id=reference.get("account_id", ""))
    data = await asyncio.to_thread(
        client.resolve_connector_credential, resolve_url, api_key, reference
    )
    auth_config = data.get("auth_config")
    if not isinstance(auth_config, dict) or not auth_config:
        raise InternalError("External Connector credential resolution returned no auth_config.")
    return {str(key): value for key, value in auth_config.items()}
