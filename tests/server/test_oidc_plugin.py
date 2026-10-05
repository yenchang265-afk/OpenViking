# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""OIDC plugin token validation against a locally served JWKS."""

import base64
import hashlib
import hmac
import json
import time
from types import SimpleNamespace

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

from openviking.server.auth.oidc_config import OIDCConfig
from openviking.server.auth.plugins.oidc import OIDCAuthPlugin
from openviking.server.identity import Role
from openviking_cli.exceptions import UnauthenticatedError

ISSUER = "https://idp.example.com"
AUDIENCE = "openviking"
JWKS_URI = "https://idp.example.com/jwks"

RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
EC_KEY = ec.generate_private_key(ec.SECP256R1())


def _jwks() -> dict:
    rsa_jwk = RSAAlgorithm.to_jwk(RSA_KEY.public_key(), as_dict=True)
    ec_jwk = ECAlgorithm.to_jwk(EC_KEY.public_key(), as_dict=True)
    return {
        "keys": [
            {**rsa_jwk, "kid": "rsa-1", "alg": "RS256", "use": "sig"},
            {**ec_jwk, "kid": "ec-1", "alg": "ES256", "use": "sig"},
        ]
    }


def _token(
    *,
    key=RSA_KEY,
    alg: str = "RS256",
    kid: str | None = "rsa-1",
    **claims,
) -> str:
    now = int(time.time())
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "auth0|123456",
        "iat": now,
        "exp": now + 300,
        **claims,
    }
    headers = {"kid": kid} if kid else {}
    return jwt.encode(payload, key, algorithm=alg, headers=headers)


def _request(token: str):
    return SimpleNamespace(headers={"Authorization": f"Bearer {token}"}, query_params={})


@pytest.fixture
def jwks_requests(monkeypatch):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if str(request.url) == JWKS_URI:
            return httpx.Response(200, json=_jwks())
        return httpx.Response(404)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    return calls


@pytest.fixture
async def plugin(jwks_requests):
    instance = OIDCAuthPlugin()
    config = SimpleNamespace(oidc=OIDCConfig(issuer=ISSUER, audience=AUDIENCE, jwks_uri=JWKS_URI))
    await instance.initialize(app=None, service=None, config=config)
    return instance


async def test_valid_rs256_token_maps_identity(plugin):
    identity = await plugin.resolve_identity(_request(_token()))

    assert identity.role == Role.USER
    assert identity.user_id == "auth0_123456"
    assert identity.account_id == "default"


async def test_valid_es256_token_is_accepted(plugin):
    identity = await plugin.resolve_identity(_request(_token(key=EC_KEY, alg="ES256", kid="ec-1")))

    assert identity.user_id == "auth0_123456"


async def test_jwks_is_fetched_once_and_cached(plugin, jwks_requests):
    await plugin.resolve_identity(_request(_token()))
    await plugin.resolve_identity(_request(_token()))

    assert jwks_requests == [JWKS_URI]


@pytest.mark.parametrize(
    ("token_kwargs", "message"),
    [
        ({"exp": int(time.time()) - 60}, "expired"),
        ({"aud": "another-client"}, "Invalid OIDC token"),
        ({"iss": "https://evil.example.com"}, "Invalid OIDC token"),
        ({"kid": "missing-kid"}, "Unknown key ID"),
        ({"kid": None}, "missing 'kid'"),
    ],
)
async def test_invalid_tokens_are_rejected(plugin, token_kwargs, message):
    with pytest.raises(UnauthenticatedError, match=message):
        await plugin.resolve_identity(_request(_token(**token_kwargs)))


async def test_malformed_token_is_rejected(plugin):
    with pytest.raises(UnauthenticatedError):
        await plugin.resolve_identity(_request("not.a.jwt"))


def _b64url(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


async def test_hmac_token_signed_with_rsa_public_key_is_rejected(plugin):
    """Algorithm confusion: HS256 keyed with the published RSA key must fail."""
    public_pem = RSA_KEY.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    header = {"alg": "HS256", "typ": "JWT", "kid": "rsa-1"}
    payload = {"iss": ISSUER, "aud": AUDIENCE, "sub": "attacker", "exp": int(time.time()) + 300}
    signing_input = b".".join(
        [_b64url(json.dumps(header).encode()), _b64url(json.dumps(payload).encode())]
    )
    signature = hmac.new(public_pem, signing_input, hashlib.sha256).digest()
    token = (signing_input + b"." + _b64url(signature)).decode()

    with pytest.raises(UnauthenticatedError):
        await plugin.resolve_identity(_request(token))
