# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Dense embedder for an HTTP embedding gateway behind a token exchange.

The gateway takes ``{texts, model, encoding-format}`` and answers with an envelope
``{returnCode, returnMessage, returnData: [{index, embedding}]}``. Its access token comes
from exchanging a long-lived API token and is sent as the raw value of a configured header.
"""

import base64
import binascii
import struct
import threading
import time
from pathlib import Path
from typing import Any, Callable, Generator, List, Optional, cast

import httpx

from openviking.models.embedder.base import DenseEmbedderBase, EmbeddingInput, EmbedResult
from openviking.models.model_error import (
    ModelError,
    ModelErrorKind,
    model_error_boundary,
    model_error_from_status,
)
from openviking.models.network import (
    create_optional_async_httpx_client,
    create_optional_sync_httpx_client,
)
from openviking.telemetry import get_current_telemetry
from openviking.utils.async_client_cache import LoopScopedAsyncClientCache
from openviking_cli.utils import get_logger
from openviking_cli.utils.config.custom_embedding_gateway_config import CustomGatewayConfig

logger = get_logger(__name__)

PROVIDER = "custom"


class CustomGatewayError(ModelError):
    """The single error type of the custom gateway: token exchange, transport and envelope."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        kind: Optional[ModelErrorKind] = None,
    ) -> None:
        if kind is None:
            kind = (
                model_error_from_status(status_code, message, provider=PROVIDER).kind
                if status_code is not None
                else ModelErrorKind.UNKNOWN
            )
        super().__init__(kind, message, provider=PROVIDER, status_code=status_code)


def _read_token_file(token_file: Optional[str]) -> str:
    if not token_file:
        raise CustomGatewayError(
            "Custom gateway needs an API token: set GATEWAY_API_TOKEN or GATEWAY_TOKEN_FILE",
            kind=ModelErrorKind.AUTHENTICATION_ERROR,
        )
    path = Path(token_file).expanduser()
    try:
        token = path.read_text().strip()
    except OSError as error:
        raise CustomGatewayError(
            f"Cannot read custom gateway token file {path}: {error.strerror}",
            kind=ModelErrorKind.AUTHENTICATION_ERROR,
        ) from error
    if not token:
        raise CustomGatewayError(
            f"Custom gateway token file {path} is empty",
            kind=ModelErrorKind.AUTHENTICATION_ERROR,
        )
    return token


class TokenExchangeAuth(httpx.Auth):
    """Exchange an API token for a short-lived access token and attach it to each request.

    One instance serves sync and async clients alike: the flow only yields requests and the
    client performs the I/O. The lock guards the cached token and is never held across a
    request, so callers holding a valid token never wait. Callers that find the token
    expired at the same moment may each exchange once; every result is valid and the last
    one is kept.
    """

    requires_response_body = True

    def __init__(
        self,
        token_exchange_url: str,
        api_token: Optional[str],
        auth_header: str,
        token_file: Optional[str] = None,
        *,
        request_field: str = "key",
        response_field: str = "token",
        token_lifetime: float = 1200,
        refresh_margin: float = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not auth_header:
            raise CustomGatewayError("Custom gateway auth_header is required")
        if refresh_margin >= token_lifetime:
            raise CustomGatewayError("Custom gateway refresh_margin must be below token_lifetime")
        self._url = token_exchange_url
        self._api_token = api_token or _read_token_file(token_file)
        self._auth_header = auth_header
        self._request_field = request_field
        self._response_field = response_field
        # The token endpoint reports no expiry: assume a fixed lifetime, refreshed early.
        self._valid_for = token_lifetime - refresh_margin
        self._clock = clock
        self._lock = threading.Lock()
        self._token: Optional[str] = None
        self._expires_at = 0.0

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        token = self._cached_token()
        if token is None:
            token = yield from self._exchange(request)
        request.headers[self._auth_header] = token
        response = yield request
        if response.status_code != 401:
            return
        # Keep a token another caller refreshed meanwhile; retry exactly once.
        self._invalidate(token)
        token = self._cached_token()
        if token is None:
            token = yield from self._exchange(request)
        request.headers[self._auth_header] = token
        yield request

    def _cached_token(self) -> Optional[str]:
        with self._lock:
            if self._token is not None and self._clock() < self._expires_at:
                return self._token
            return None

    def _invalidate(self, token: str) -> None:
        with self._lock:
            if self._token == token:
                self._token = None

    def _exchange(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, str]:
        # Yielded requests do not inherit the client's timeout; reuse the gateway call's.
        extensions = (
            {"timeout": request.extensions["timeout"]} if "timeout" in request.extensions else {}
        )
        response = yield httpx.Request(
            "POST",
            self._url,
            json={self._request_field: self._api_token},
            extensions=extensions,
        )
        if response.is_error:
            raise CustomGatewayError(
                f"Custom gateway token exchange failed: HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise CustomGatewayError(
                "Custom gateway token exchange returned invalid JSON"
            ) from error
        token = payload.get(self._response_field) if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise CustomGatewayError(
                f"Custom gateway token exchange response has no '{self._response_field}'"
            )
        with self._lock:
            self._token = token
            self._expires_at = self._clock() + self._valid_for
        return token


def _decode_embedding(value: Any) -> List[float]:
    if isinstance(value, str):
        try:
            raw = base64.b64decode(value, validate=True)
        except binascii.Error as error:
            raise CustomGatewayError(
                "Custom gateway returned an invalid base64 embedding"
            ) from error
        if len(raw) % 4:
            raise CustomGatewayError("Custom gateway base64 embedding is not float32 data")
        # OpenAI-style base64: little-endian float32 values.
        return list(struct.unpack(f"<{len(raw) // 4}f", raw))
    if isinstance(value, list) and all(
        isinstance(item, (int, float)) and not isinstance(item, bool) for item in value
    ):
        return [float(item) for item in value]
    raise CustomGatewayError("Custom gateway embedding must be a number list or a base64 string")


def parse_embeddings(data: Any, count: int) -> List[List[float]]:
    """Return the vectors ordered by ``index``; indexes must be exactly ``0..count-1``."""
    if not isinstance(data, list):
        raise CustomGatewayError("Custom gateway response data is not a list")
    items = []
    for item in data:
        index = item.get("index") if isinstance(item, dict) else None
        if not isinstance(index, int) or isinstance(index, bool):
            raise CustomGatewayError("Custom gateway embedding has no integer index")
        items.append((index, item.get("embedding")))
    items.sort(key=lambda pair: pair[0])
    if [index for index, _ in items] != list(range(count)):
        raise CustomGatewayError(
            f"Custom gateway returned {len(items)} embeddings for {count} inputs"
        )
    return [_decode_embedding(embedding) for _, embedding in items]


class CustomDenseEmbedder(DenseEmbedderBase):
    """Dense embedder for any OpenAI-compatible model served through the custom gateway.

    Token usage comes from the envelope's optional ``usage`` object. When the gateway reports
    none, usage is an estimate (about 4 characters per token), not a billed count.
    """

    def __init__(
        self,
        model_name: str,
        dimension: int,
        gateway: CustomGatewayConfig,
        encoding_format: Optional[str] = None,
        config: Optional[dict] = None,
    ):
        super().__init__(model_name, config)
        self.provider = PROVIDER
        self.dimension = dimension
        self.gateway = gateway
        self.encoding_format = encoding_format or "float"
        gateway.validate_complete("Custom embedder")
        self._embedding_url = cast(str, gateway.embedding_url)
        auth = TokenExchangeAuth(
            cast(str, gateway.token_exchange_url),
            gateway.api_token,
            cast(str, gateway.auth_header),
            gateway.token_file,
            request_field=gateway.token_request_field,
            response_field=gateway.token_response_field,
            token_lifetime=gateway.token_lifetime,
            refresh_margin=gateway.token_refresh_margin,
        )
        pool_limit = max(1, self.max_concurrent)
        self._client_kwargs: dict[str, Any] = {
            "auth": auth,
            "timeout": gateway.timeout,
            "limits": httpx.Limits(
                max_connections=pool_limit,
                max_keepalive_connections=pool_limit,
                keepalive_expiry=5.0,
            ),
        }
        self.client = create_optional_sync_httpx_client(
            self._embedding_url, **self._client_kwargs
        ) or httpx.Client(**self._client_kwargs)
        self._async_client_cache = LoopScopedAsyncClientCache()

    def _get_async_client(self) -> httpx.AsyncClient:
        return self._async_client_cache.get(
            lambda: (
                create_optional_async_httpx_client(self._embedding_url, **self._client_kwargs)
                or httpx.AsyncClient(**self._client_kwargs)
            )
        )

    def _body(self, texts: List[str]) -> dict[str, Any]:
        gateway = self.gateway
        return {
            gateway.texts_field: texts,
            gateway.model_field: self.model_name,
            gateway.encoding_format_field: self.encoding_format,
        }

    def _texts(self, content: EmbeddingInput) -> List[str]:
        return [str(self.prepare_embedding_input(content))]

    def _result(self, response: httpx.Response, texts: List[str]) -> EmbedResult:
        gateway = self.gateway
        if response.is_error:
            raise CustomGatewayError(
                f"Custom gateway embedding failed: HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            envelope = response.json()
        except ValueError as error:
            raise CustomGatewayError("Custom gateway embedding returned invalid JSON") from error
        if not isinstance(envelope, dict):
            raise CustomGatewayError("Custom gateway embedding response is not an object")
        code = envelope.get(gateway.code_field)
        if str(code) != gateway.success_code:
            message = str(envelope.get(gateway.message_field) or "")[:200]
            raise CustomGatewayError(
                f"Custom gateway embedding failed: {gateway.code_field}={code!r} {message}".rstrip()
            )
        vectors = parse_embeddings(envelope.get(gateway.data_field), len(texts))
        for vector in vectors:
            if len(vector) != self.dimension:
                raise CustomGatewayError(
                    f"Custom gateway returned a {len(vector)}-dimension embedding; "
                    f"expected {self.dimension}"
                )
        self._record_usage(envelope.get("usage"), texts)
        return EmbedResult(dense_vector=vectors[0])

    def _record_usage(self, usage: Any, texts: List[str]) -> None:
        prompt_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
        if isinstance(prompt_tokens, int) and not isinstance(prompt_tokens, bool):
            total_tokens = usage.get("total_tokens")
            if not isinstance(total_tokens, int) or isinstance(total_tokens, bool):
                total_tokens = prompt_tokens
        else:
            # The gateway reported no usage: this is an estimate, not a billed count.
            prompt_tokens = total_tokens = sum(self._estimate_tokens(text) for text in texts)
        completion_tokens = max(total_tokens - prompt_tokens, 0)
        get_current_telemetry().add_token_usage_by_source(
            "embedding", prompt_tokens, completion_tokens
        )
        self.update_token_usage(
            model_name=self.model_name,
            provider=PROVIDER,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    @model_error_boundary
    def embed(self, content: EmbeddingInput, is_query: bool = False) -> EmbedResult:
        texts = self._texts(content)

        def _call() -> EmbedResult:
            try:
                response = self.client.post(self._embedding_url, json=self._body(texts))
            except httpx.HTTPError as error:
                raise _transport_error(error) from error
            return self._result(response, texts)

        return self._run_once(_call, logger=logger, operation_name="Custom gateway embedding")

    @model_error_boundary
    async def embed_async(self, content: EmbeddingInput, is_query: bool = False) -> EmbedResult:
        client = self._get_async_client()
        texts = self._texts(content)

        async def _call() -> EmbedResult:
            try:
                response = await client.post(self._embedding_url, json=self._body(texts))
            except httpx.HTTPError as error:
                raise _transport_error(error) from error
            return self._result(response, texts)

        return await self._run_once_async(
            _call, logger=logger, operation_name="Custom gateway async embedding"
        )

    def get_dimension(self) -> int:
        return self.dimension

    def close(self) -> None:
        self.client.close()
        self._async_client_cache.close_all_with_aclose()


def _transport_error(error: httpx.HTTPError) -> CustomGatewayError:
    kind = (
        ModelErrorKind.TRANSIENT_NETWORK_ERROR
        if isinstance(error, httpx.TransportError)
        else ModelErrorKind.UNKNOWN
    )
    return CustomGatewayError(f"Custom gateway request failed: {error!r}", kind=kind)
