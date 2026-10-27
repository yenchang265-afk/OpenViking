# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Custom provider: token-exchange auth, gateway envelope and configuration."""

import base64
import json
import struct
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from pydantic import ValidationError

from openviking.config.account_vector import AccountEmbeddingModelConfig
from openviking.models.embedder import CustomDenseEmbedder, RetryEmbedder
from openviking.models.embedder.custom_embedders import CustomGatewayError, TokenExchangeAuth
from openviking.models.model_error import ModelErrorKind
from openviking_cli.utils.config.custom_embedding_gateway_config import CustomGatewayConfig
from openviking_cli.utils.config.embedding_config import EmbeddingConfig, EmbeddingModelConfig

TOKEN_URL = "https://token.example.test/exchange"
EMBEDDING_URL = "https://embed.example.test/v1/embeddings"
HEADER = "X-Example-Access-Token"
DIMENSION = 3
GATEWAY = {
    "token_exchange_url": TOKEN_URL,
    "embedding_url": EMBEDDING_URL,
    "auth_header": HEADER,
    "api_token": "api-secret",
}


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for field in CustomGatewayConfig.model_fields:
        monkeypatch.delenv("GATEWAY_" + field.upper(), raising=False)


class FakeGateway:
    """Token endpoint plus embedding gateway; only the latest access token is accepted."""

    def __init__(self):
        self.lock = threading.Lock()
        self.exchanges = 0
        self.token_requests = []
        self.embedding_requests = []
        self.valid = set()
        self.envelope = None

    def __call__(self, request):
        with self.lock:
            if request.url == TOKEN_URL:
                self.exchanges += 1
                self.token_requests.append(request)
                token = f"access-{self.exchanges}"
                self.valid = {token}
                return httpx.Response(200, json={"token": token})
            self.embedding_requests.append(request)
            if request.headers.get(HEADER) not in self.valid:
                return httpx.Response(401)
            texts = json.loads(request.content)["texts"]
        if self.envelope is not None:
            return httpx.Response(200, json=self.envelope)
        data = [{"index": i, "embedding": [i + 0.5] * DIMENSION} for i in range(len(texts))]
        return httpx.Response(
            200, json={"returnCode": 0, "returnMessage": "ok", "returnData": data[::-1]}
        )


def make_embedder(handler, **overrides):
    gateway = CustomGatewayConfig(**{**GATEWAY, **overrides.pop("gateway", {})})
    embedder = CustomDenseEmbedder("any-model", DIMENSION, gateway, **overrides)
    embedder.client = httpx.Client(
        transport=httpx.MockTransport(handler), **embedder._client_kwargs
    )
    return embedder


def test_token_is_exchanged_once_and_sent_raw():
    fake = FakeGateway()
    embedder = make_embedder(fake)

    assert embedder.embed("hello").dense_vector == [0.5] * DIMENSION
    embedder.embed("again")

    assert fake.exchanges == 1
    assert json.loads(fake.token_requests[0].content) == {"key": "api-secret"}
    assert fake.token_requests[0].extensions["timeout"] == httpx.Timeout(30).as_dict()
    assert [r.headers[HEADER] for r in fake.embedding_requests] == ["access-1", "access-1"]
    assert json.loads(fake.embedding_requests[0].content) == {
        "texts": ["hello"],
        "model": "any-model",
        "encoding-format": "float",
    }


def test_token_refreshes_at_lifetime_minus_margin():
    fake = FakeGateway()
    now = [0.0]
    auth = TokenExchangeAuth(TOKEN_URL, "api-secret", HEADER, clock=lambda: now[0])
    client = httpx.Client(transport=httpx.MockTransport(fake), auth=auth)

    client.post(EMBEDDING_URL, json={"texts": ["a"]})
    now[0] = 1139.0
    client.post(EMBEDDING_URL, json={"texts": ["a"]})
    assert fake.exchanges == 1
    now[0] = 1140.0
    client.post(EMBEDDING_URL, json={"texts": ["a"]})
    assert fake.exchanges == 2


def test_401_refreshes_the_token_and_retries_once():
    fake = FakeGateway()
    embedder = make_embedder(fake)
    embedder.embed("hello")
    fake.valid = set()  # The gateway revokes the cached token.

    assert embedder.embed("hello").dense_vector == [0.5] * DIMENSION
    assert fake.exchanges == 2
    assert len(fake.embedding_requests) == 3


def test_second_401_is_reported_after_one_retry():
    fake = FakeGateway()
    embedder = make_embedder(
        lambda request: fake(request) if request.url == TOKEN_URL else httpx.Response(401)
    )

    with pytest.raises(CustomGatewayError) as raised:
        embedder.embed("hello")

    assert raised.value.status_code == 401
    assert raised.value.kind == ModelErrorKind.AUTHENTICATION_ERROR
    assert fake.exchanges == 2


def raise_connect_error(request):
    raise httpx.ConnectError("refused", request=request)


@pytest.mark.parametrize(
    "token_response",
    [
        lambda request: httpx.Response(500),
        lambda request: httpx.Response(200, text="not json"),
        lambda request: httpx.Response(200, json={"unexpected": "field"}),
        raise_connect_error,
    ],
    ids=["http-error", "invalid-json", "missing-field", "transport-error"],
)
def test_token_endpoint_failures_raise_the_gateway_error(token_response):
    fake = FakeGateway()
    embedder = make_embedder(
        lambda request: token_response(request) if request.url == TOKEN_URL else fake(request)
    )

    with pytest.raises(CustomGatewayError) as raised:
        embedder.embed("hello")
    assert not isinstance(raised.value, httpx.HTTPError)
    assert "api-secret" not in str(raised.value)


def test_shared_token_cache_is_thread_safe():
    fake = FakeGateway()
    embedder = make_embedder(fake)

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda i: embedder.embed(f"text {i}"), range(64)))

    assert all(result.dense_vector == [0.5] * DIMENSION for result in results)
    assert 1 <= fake.exchanges <= 16


def test_token_file_is_read_when_no_token_is_set(tmp_path):
    token_file = tmp_path / "api-token"
    token_file.write_text("file-secret\n")
    fake = FakeGateway()
    embedder = make_embedder(fake, gateway={"api_token": None, "token_file": str(token_file)})

    embedder.embed("hello")
    assert json.loads(fake.token_requests[0].content) == {"key": "file-secret"}

    token_file.write_text("")
    with pytest.raises(CustomGatewayError, match="is empty"):
        TokenExchangeAuth(TOKEN_URL, None, HEADER, str(token_file))
    with pytest.raises(CustomGatewayError, match="Cannot read"):
        TokenExchangeAuth(TOKEN_URL, None, HEADER, str(tmp_path / "missing"))
    with pytest.raises(CustomGatewayError, match="GATEWAY_TOKEN_FILE"):
        TokenExchangeAuth(TOKEN_URL, None, HEADER)


def test_base64_embeddings_are_decoded():
    fake = FakeGateway()
    packed = base64.b64encode(struct.pack("<3f", 0.5, -2.0, 1.5)).decode()
    fake.envelope = {"returnCode": "0", "returnData": [{"index": 0, "embedding": packed}]}
    embedder = make_embedder(fake, encoding_format="base64")

    assert embedder.embed("hello").dense_vector == [0.5, -2.0, 1.5]
    assert json.loads(fake.embedding_requests[0].content)["encoding-format"] == "base64"


@pytest.mark.parametrize(
    "envelope, message",
    [
        ({"returnCode": 7, "returnMessage": "quota", "returnData": []}, "returnCode=7 quota"),
        ({"returnCode": 0, "returnData": [{"index": 1, "embedding": [1.0] * 3}]}, "1 embeddings"),
        (
            {"returnCode": 0, "returnData": [{"index": 0, "embedding": [1.0] * 3}] * 2},
            "2 embeddings",
        ),
        ({"returnCode": 0, "returnData": [{"index": 0, "embedding": [1.0]}]}, "expected 3"),
        ({"returnCode": 0, "returnData": None}, "not a list"),
    ],
    ids=["return-code", "index-gap", "count", "dimension", "data"],
)
def test_invalid_envelopes_raise_the_gateway_error(envelope, message):
    fake = FakeGateway()
    fake.envelope = envelope
    with pytest.raises(CustomGatewayError, match=message):
        make_embedder(fake).embed("hello")


def test_usage_is_reported_or_estimated(monkeypatch):
    fake = FakeGateway()
    embedder = make_embedder(fake)
    recorded = []
    monkeypatch.setattr(
        embedder, "update_token_usage", lambda **usage: recorded.append(usage["prompt_tokens"])
    )

    embedder.embed("x" * 40)
    vector = [0.5] * DIMENSION
    fake.envelope = {
        "returnCode": 0,
        "returnData": [{"index": 0, "embedding": vector}],
        "usage": {"prompt_tokens": 3},
    }
    embedder.embed("x" * 40)

    assert recorded == [10, 3]


async def test_async_embedding_shares_the_token():
    fake = FakeGateway()
    embedder = make_embedder(fake)
    client = httpx.AsyncClient(transport=httpx.MockTransport(fake), **embedder._client_kwargs)
    embedder._get_async_client = lambda: client

    embedder.embed("sync")
    result = await embedder.embed_async("async")

    assert result.dense_vector == [0.5] * DIMENSION
    assert fake.exchanges == 1
    await client.aclose()


def test_configuration_from_file_and_environment(monkeypatch):
    monkeypatch.setenv("GATEWAY_EMBEDDING_URL", "https://other.example.test/embed")
    config = EmbeddingConfig(
        dense=EmbeddingModelConfig(provider="custom", model="m", dimension=3, custom=GATEWAY)
    )
    assert config.dense.custom.embedding_url == "https://other.example.test/embed"
    embedder = config.get_embedder()
    assert isinstance(embedder, RetryEmbedder)
    assert isinstance(embedder.inner, CustomDenseEmbedder)

    for field, value in GATEWAY.items():
        monkeypatch.setenv("GATEWAY_" + field.upper(), value)
    monkeypatch.setenv("GATEWAY_TIMEOUT", "5")
    env_only = EmbeddingModelConfig(provider="custom", model="m", dimension=3)
    assert env_only.custom.timeout == 5


@pytest.mark.parametrize(
    "values, message",
    [
        ({"custom": {}}, "GATEWAY_TOKEN_EXCHANGE_URL.*GATEWAY_AUTH_HEADER.*GATEWAY_TOKEN_FILE"),
        ({"custom": {**GATEWAY, "api_token": None}}, "GATEWAY_API_TOKEN or GATEWAY_TOKEN_FILE"),
        ({"custom": {**GATEWAY, "embedding_url": "ftp://x"}}, "http"),
        ({"custom": GATEWAY, "dimension": None}, "dimension"),
        ({"custom": GATEWAY, "api_key": "k"}, "remove api_key"),
        ({"custom": GATEWAY, "credentials": [{"provider": "custom"}]}, "failover"),
        ({"provider": "openai", "api_key": "k", "custom": GATEWAY}, "require provider 'custom'"),
    ],
    ids=["missing", "no-token", "url", "dimension", "api-key", "credentials", "other-provider"],
)
def test_invalid_configuration_fails_with_a_clear_error(values, message):
    with pytest.raises(ValidationError, match=message):
        EmbeddingModelConfig(**{"provider": "custom", "model": "m", "dimension": 3, **values})


def test_account_level_custom_provider_is_rejected():
    with pytest.raises(ValidationError, match="cluster-wide"):
        AccountEmbeddingModelConfig(model="m", dimension=3, credentials=[{"provider": "custom"}])
