# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Single-use transfer credentials for MCP uploads and downloads.

Issued by the MCP ``add_resource`` tool when a caller passes a local-file path; consumed by
``POST /api/v1/resources/temp_upload`` when the request carries a ``?token=`` instead of an
API key. Tokens are 10-character base62 strings indexed in memory or Redis.
Both backends consume and burn a token atomically, without a signing key.

The token carries the identity bound at issue time (account/user/role and OAuth origin),
the caller's actor peer scope (``actor_peer_id``), and the business params
(``to``/``parent``/``reason``/``parse_mode``) so the server can
finish ingestion automatically once the file lands — the caller does not re-invoke
``add_resource``, and the ingest keeps the original peer scope. Tokens minted by the MCP
``add_skill`` tool carry ``kind="skill"`` plus the skill install params instead, and the upload
is installed as skills rather than ingested as a resource. The ``temp_file_id`` is minted by
:class:`openviking.server.temp_upload_store.TempUploadStore` at upload time, so the token
does not pre-bind a filename and the upload can flow through either the local or shared
TempUploadStore mode without a side-channel.

``download_token_store`` is a separate instance used by the MCP ``download`` tool: its tokens
carry the resolved ``uri`` of one file and are consumed by ``GET /api/v1/content/download``.
Keeping the two stores apart means an upload token can never be redeemed for a download, or
the reverse.

Local deployments keep credentials in memory. The Redis backend shares them across
workers and replicas, using SET NX with expiry and atomic GETDEL consumption.
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import string
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from threading import RLock
from typing import Any, Optional, Tuple

from pydantic import TypeAdapter

from openviking.resource.processing_mode import DEFAULT_PROCESSING_MODE, ProcessingMode
from openviking.server.identity import Role
from openviking.storage.acl import AclSpec

_TOKEN_ALPHABET = string.ascii_letters + string.digits  # base62
_TOKEN_LENGTH = 10


class UploadTokenError(Exception):
    """Raised when an upload token is unknown or expired."""


@dataclass(frozen=True)
class _TokenInfo:
    account_id: str
    user_id: str
    role: str
    to: str
    parent: str
    reason: str
    actor_peer_id: str
    processing_mode: ProcessingMode
    tags: Optional[list[str]]
    tag_mode: str
    parse_mode: str
    expires_at: float
    kind: str = "resource"
    skill_target_uri: str = ""
    skill_names: Optional[list[str]] = None
    list_only: bool = False
    acl: AclSpec | None = None
    from_oauth: bool = False
    uri: str = ""


@dataclass(frozen=True)
class ConsumedUploadToken:
    """Identity and business params bound to an upload token, returned by ``consume``."""

    account_id: str
    user_id: str
    role: Role
    to: str
    reason: str
    actor_peer_id: str
    parent: str = ""
    processing_mode: ProcessingMode = DEFAULT_PROCESSING_MODE
    tags: Optional[list[str]] = None
    tag_mode: str = "replace"
    parse_mode: str = "default"
    kind: str = "resource"
    skill_target_uri: str = ""
    skill_names: Optional[list[str]] = None
    list_only: bool = False
    acl: AclSpec | None = None
    from_oauth: bool = False
    uri: str = ""


class UploadTokenStore:
    def __init__(self, *, redis: Any = None, namespace: str = "") -> None:
        self._store: dict[str, _TokenInfo] = {}
        self._redis = redis
        self._namespace = namespace
        self._lock = RLock()

    def configure(self, *, redis: Any = None, namespace: str = "") -> None:
        """Select a backend at startup; never fall back locally on backend errors."""
        with self._lock:
            self._store.clear()
            self._redis = redis
            self._namespace = namespace

    def _key(self, token: str) -> str:
        # Do not store bearer credentials in Redis key names or diagnostics.
        return self._namespace + hashlib.sha256(token.encode()).hexdigest()

    async def aissue(self, *args: Any, **kwargs: Any) -> Tuple[str, float]:
        if self._redis is None:
            return self.issue(*args, **kwargs)
        return await asyncio.to_thread(self.issue, *args, **kwargs)

    async def aconsume(self, token: str) -> ConsumedUploadToken:
        if self._redis is None:
            return self.consume(token)
        return await asyncio.to_thread(self.consume, token)

    def issue(
        self,
        account_id: str,
        user_id: str,
        ttl_seconds: int,
        *,
        role: Role,
        to: str = "",
        parent: str = "",
        reason: str = "",
        actor_peer_id: str = "",
        processing_mode: ProcessingMode = DEFAULT_PROCESSING_MODE,
        tags: Optional[list[str]] = None,
        tag_mode: str = "replace",
        parse_mode: str = "default",
        kind: str = "resource",
        skill_target_uri: str = "",
        skill_names: Optional[list[str]] = None,
        list_only: bool = False,
        acl: AclSpec | None = None,
        from_oauth: bool = False,
        uri: str = "",
    ) -> Tuple[str, float]:
        """Mint a fresh token bound to the caller identity and ingestion parameters.

        ``actor_peer_id`` is captured from the minting request's context so server-side
        auto-ingest keeps the caller's peer scope (reason-memory routing) — it is NOT taken
        from the later upload request's headers, which could be spoofed. Returns
        (token, expires_at).
        """
        with self._lock:
            self._purge_expired()
        expires_at = time.time() + max(1, ttl_seconds)
        info = _TokenInfo(
            account_id,
            user_id,
            role,
            to,
            parent,
            reason,
            actor_peer_id,
            processing_mode,
            tags,
            tag_mode,
            parse_mode,
            expires_at,
            kind,
            skill_target_uri,
            skill_names,
            list_only,
            acl,
            from_oauth,
            uri,
        )
        for _ in range(8):
            token = "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(_TOKEN_LENGTH))
            if self._redis is not None:
                payload = _TOKEN_ADAPTER.dump_json(info)
                inserted = self._redis.set(
                    self._key(token), payload, nx=True, ex=max(1, ttl_seconds)
                )
            else:
                with self._lock:
                    inserted = token not in self._store
                    if inserted:
                        self._store[token] = info
            if inserted:
                return token, expires_at
        raise RuntimeError("upload_token_store: failed to mint a unique token after 8 attempts")

    def consume(self, token: str) -> ConsumedUploadToken:
        """Pop the token and validate it. Returns the bound identity + business params."""
        if not token:
            raise UploadTokenError("missing upload token")
        if self._redis is not None:
            raw = self._redis.getdel(self._key(token))
            info = _TOKEN_ADAPTER.validate_json(raw) if raw is not None else None
        else:
            with self._lock:
                info = self._store.pop(token, None)
        if info is None:
            raise UploadTokenError("unknown or already-consumed upload token")
        if info.expires_at < time.time():
            raise UploadTokenError("upload token expired")
        return ConsumedUploadToken(
            account_id=info.account_id,
            user_id=info.user_id,
            role=info.role,
            to=info.to,
            parent=info.parent,
            reason=info.reason,
            actor_peer_id=info.actor_peer_id,
            processing_mode=info.processing_mode,
            tags=info.tags,
            tag_mode=info.tag_mode,
            parse_mode=info.parse_mode,
            kind=info.kind,
            skill_target_uri=info.skill_target_uri,
            skill_names=info.skill_names,
            list_only=info.list_only,
            acl=info.acl,
            from_oauth=info.from_oauth,
            uri=info.uri,
        )

    def peek(self, token: str) -> Optional[_TokenInfo]:
        """Read a token without consuming. Test helper only."""
        if self._redis is not None:
            raw = self._redis.get(self._key(token))
            return _TOKEN_ADAPTER.validate_json(raw) if raw is not None else None
        with self._lock:
            return self._store.get(token)

    def clear(self) -> None:
        """Reset state. Test helper only."""
        if self._redis is not None:
            raise RuntimeError(
                "Shared transfer tokens expire automatically; bulk clear is disabled"
            )
        with self._lock:
            self._store.clear()

    def _purge_expired(self) -> None:
        now = time.time()
        for token, info in list(self._store.items()):
            if info.expires_at < now:
                self._store.pop(token, None)


_TOKEN_ADAPTER = TypeAdapter(_TokenInfo)

upload_token_store = UploadTokenStore()
download_token_store = UploadTokenStore()


@asynccontextmanager
async def transfer_token_lifespan(config):
    """Own the shared connection for the lifetime of one server worker."""
    handle = None
    try:
        if config.transfer_tokens.provider == "redis":
            from openviking.server.account_stores.redis_client import create_redis_client
            from openviking_cli.utils.config.open_viking_config import get_openviking_config

            ov_config = get_openviking_config()
            if ov_config.cache is None or ov_config.cache.provider != "redis":
                raise ValueError(
                    "server.transfer_tokens.provider=redis requires cache.provider=redis"
                )
            handle = create_redis_client(ov_config.cache.params, asynchronous=False)
            await asyncio.to_thread(handle.client.ping)
            prefix = f"openviking:{ov_config.service_name}:transfer:"
            upload_token_store.configure(redis=handle.client, namespace=prefix + "upload:")
            download_token_store.configure(redis=handle.client, namespace=prefix + "download:")
        else:
            upload_token_store.configure()
            download_token_store.configure()
        yield
    finally:
        upload_token_store.configure()
        download_token_store.configure()
        if handle is not None:
            # redis-py's synchronous clients own synchronous connection pools.
            await asyncio.to_thread(handle.client.close)
            for sentinel in handle.sentinel_clients:
                await asyncio.to_thread(sentinel.close)
