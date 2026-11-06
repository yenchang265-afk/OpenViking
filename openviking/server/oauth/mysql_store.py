"""Shared OAuth grants, with transaction-owned one-shot consumption.

Provision ``mysql_schema.sql`` before enabling this backend. Each deployment
is isolated by service_name; tokens are indexed only by their SHA-256 hashes.
"""

from __future__ import annotations

import secrets
import time
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Index,
    MetaData,
    String,
    Table,
    delete,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.ext.asyncio import create_async_engine

from openviking.server.account_stores.mysql import MySQLAccountStore
from openviking.server.oauth.otp import hash_secret
from openviking.storage.mysql_runtime import (
    get_shared_mysql_runtime,
    mysql_runtime_store,
    wait_mysql_cleanup,
)
from openviking_cli.utils.config.config_utils import normalize_service_name

metadata = MetaData()
records = Table(
    "ov_oauth_records",
    metadata,
    Column("service_name", String(64), primary_key=True),
    Column("kind", String(16), primary_key=True),
    Column("record_id", String(128), primary_key=True),
    Column("payload", JSON, nullable=False),
    Column("expires_at", BigInteger, nullable=False),
    Column("used", Boolean, nullable=False, default=False),
    Column("account_id", String(128)),
    Column("user_id", String(128)),
    Column("display_code", String(64)),
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_bin",
)
Index("ix_ov_oauth_expiry", records.c.service_name, records.c.kind, records.c.expires_at)
Index("ix_ov_oauth_owner", records.c.service_name, records.c.account_id, records.c.user_id)
Index("ix_ov_oauth_display", records.c.service_name, records.c.kind, records.c.display_code)


@mysql_runtime_store
class MySQLOAuthStore:
    """OAuthStore contract backed by shared MySQL rows."""

    def __init__(self, *, service_name: str, params: dict[str, Any]):
        self._service_name = normalize_service_name(service_name)
        self._url, self._options = MySQLAccountStore._connection_options(dict(params))
        self._mysql_runtime = get_shared_mysql_runtime()
        self._engine = None
        self._mysql_lease = False

    async def initialize(self):
        if self._engine is not None:
            return
        await self._mysql_runtime.acquire()
        self._mysql_lease = True
        try:
            self._engine = create_async_engine(self._url, **self._options)
            async with self._engine.connect() as connection:
                await connection.execute(select(records).limit(0))
        except BaseException:
            await wait_mysql_cleanup(self._close())
            raise

    async def close(self):
        await self._close()

    async def _close(self):
        try:
            if self._engine is not None:
                await wait_mysql_cleanup(self._engine.dispose())
        finally:
            self._engine = None
            if self._mysql_lease:
                self._mysql_lease = False
                await self._mysql_runtime.release()

    def _where(self, kind, record_id=None):
        clauses = [records.c.service_name == self._service_name, records.c.kind == kind]
        if record_id is not None:
            clauses.append(records.c.record_id == record_id)
        return clauses

    async def _insert(self, kind, record_id, payload, *, expires_at, display_code=None):
        async with self._engine.begin() as connection:
            await connection.execute(
                insert(records).values(
                    service_name=self._service_name,
                    kind=kind,
                    record_id=record_id,
                    payload=payload,
                    expires_at=expires_at,
                    used=False,
                    account_id=payload.get("account_id"),
                    user_id=payload.get("user_id"),
                    display_code=display_code,
                )
            )

    async def _load(self, kind, record_id, *, include_used=False):
        conditions = [*self._where(kind, record_id), records.c.expires_at > int(time.time())]
        if not include_used:
            conditions.append(records.c.used.is_(False))
        async with self._engine.connect() as connection:
            return (
                await connection.execute(select(records.c.payload).where(*conditions))
            ).scalar_one_or_none()

    async def _consume(self, kind, record_id, *, changes=None):
        conditions = [
            *self._where(kind, record_id),
            records.c.used.is_(False),
            records.c.expires_at > int(time.time()),
        ]
        async with self._engine.begin() as connection:
            row = (
                await connection.execute(
                    select(records.c.payload).where(*conditions).with_for_update()
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            payload = {**row, **(changes or {})}
            values = {"used": True, "payload": payload}
            if kind == "pending" and changes:
                values.update(
                    account_id=payload["verified_account_id"], user_id=payload["verified_user_id"]
                )
            await connection.execute(update(records).where(*conditions).values(**values))
            return payload

    async def register_client(
        self,
        *,
        client_id=None,
        redirect_uris,
        client_name=None,
        token_endpoint_auth_method="none",
        grant_types=None,
        response_types=None,
        client_secret=None,
        scope=None,
    ):
        if not redirect_uris:
            raise ValueError("redirect_uris must be non-empty")
        payload = {
            "client_id": client_id or secrets.token_urlsafe(16),
            "client_secret_hash": hash_secret(client_secret) if client_secret else None,
            "redirect_uris": list(redirect_uris),
            "client_name": client_name,
            "token_endpoint_auth_method": token_endpoint_auth_method,
            "grant_types": grant_types or ["authorization_code", "refresh_token"],
            "response_types": response_types or ["code"],
            "scope": scope,
            "created_at": int(time.time()),
        }
        await self._insert("client", payload["client_id"], payload, expires_at=2**63 - 1)
        return payload

    async def get_client(self, client_id):
        return await self._load("client", client_id)

    async def insert_auth_code(self, *, code_plain, ttl_seconds, **claims):
        now = int(time.time())
        claims.update(created_at=now, expires_at=now + ttl_seconds)
        await self._insert("code", hash_secret(code_plain), claims, expires_at=claims["expires_at"])
        return claims["expires_at"]

    async def consume_auth_code(self, code_plain):
        return await self._consume("code", hash_secret(code_plain))

    async def peek_auth_code(self, code_plain):
        return await self._load("code", hash_secret(code_plain))

    async def insert_refresh(self, *, token_plain, ttl_seconds, **claims):
        now = int(time.time())
        claims.update(created_at=now, expires_at=now + ttl_seconds)
        await self._insert(
            "refresh", hash_secret(token_plain), claims, expires_at=claims["expires_at"]
        )
        return claims["expires_at"]

    async def peek_refresh(self, token_plain):
        return await self._load("refresh", hash_secret(token_plain))

    async def consume_refresh(self, *, token_plain, replaced_by_plain):
        claims = await self._consume(
            "refresh",
            hash_secret(token_plain),
            changes={
                "replaced_by": hash_secret(replaced_by_plain) if replaced_by_plain else None,
            },
        )
        if claims is not None:
            claims.pop("replaced_by", None)
        return claims

    async def is_refresh_known_but_consumed(self, token_plain):
        async with self._engine.connect() as connection:
            used = (
                await connection.execute(
                    select(records.c.used).where(*self._where("refresh", hash_secret(token_plain)))
                )
            ).scalar_one_or_none()
            return bool(used)

    async def insert_access(self, *, token_plain, ttl_seconds, **claims):
        now = int(time.time())
        claims.update(created_at=now, expires_at=now + ttl_seconds)
        await self._insert(
            "access", hash_secret(token_plain), claims, expires_at=claims["expires_at"]
        )
        return claims["expires_at"]

    async def load_access(self, token_plain):
        return await self._load("access", hash_secret(token_plain))

    async def revoke_access(self, token_plain):
        async with self._engine.begin() as connection:
            result = await connection.execute(
                update(records)
                .where(
                    *self._where("access", hash_secret(token_plain)),
                    records.c.used.is_(False),
                )
                .values(used=True)
            )
            return result.rowcount > 0

    async def revoke_tokens(self, *, account_id, user_id=None):
        scope = [records.c.service_name == self._service_name, records.c.account_id == account_id]
        if user_id is not None:
            scope.append(records.c.user_id == user_id)
        counts = {}
        async with self._engine.begin() as connection:
            for kind, name in (
                ("access", "access_tokens_revoked"),
                ("refresh", "refresh_tokens_revoked"),
                ("code", "codes_revoked"),
            ):
                result = await connection.execute(
                    update(records)
                    .where(
                        *scope,
                        records.c.kind == kind,
                        records.c.used.is_(False),
                    )
                    .values(used=True)
                )
                counts[name] = result.rowcount
            result = await connection.execute(
                delete(records).where(
                    *scope,
                    records.c.kind == "pending",
                )
            )
            counts["pending_authorizations_revoked"] = result.rowcount
        return counts

    async def create_pending_authorization(self, *, ttl_seconds=600, **claims):
        pending_id = secrets.token_urlsafe(16)
        now = int(time.time())
        claims.update(
            pending_id=pending_id,
            created_at=now,
            expires_at=now + ttl_seconds,
            verified=False,
            verified_account_id=None,
            verified_user_id=None,
            verified_role=None,
            verified_key_fp=None,
        )
        await self._insert(
            "pending",
            pending_id,
            claims,
            expires_at=claims["expires_at"],
            display_code=claims["display_code"],
        )
        return pending_id

    async def load_pending_authorization(self, pending_id):
        return await self._load("pending", pending_id, include_used=True)

    async def find_pending_by_display_code(self, display_code):
        if not display_code:
            return None
        async with self._engine.connect() as connection:
            return (
                await connection.execute(
                    select(records.c.payload)
                    .where(
                        *self._where("pending"),
                        records.c.display_code == display_code.strip().upper(),
                        records.c.used.is_(False),
                        records.c.expires_at > int(time.time()),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()

    async def mark_pending_verified(
        self,
        *,
        pending_id,
        account_id,
        user_id,
        role,
        verified_key_fp,
    ):
        return (
            await self._consume(
                "pending",
                pending_id,
                changes={
                    "verified": True,
                    "verified_account_id": account_id,
                    "verified_user_id": user_id,
                    "verified_role": role,
                    "verified_key_fp": verified_key_fp,
                },
            )
            is not None
        )

    async def delete_pending_authorization(self, pending_id):
        async with self._engine.begin() as connection:
            await connection.execute(delete(records).where(*self._where("pending", pending_id)))

    async def gc_expired(self):
        counts = {}
        async with self._engine.begin() as connection:
            for kind, name in (
                ("code", "codes_deleted"),
                ("refresh", "refresh_tokens_deleted"),
                ("access", "access_tokens_deleted"),
                ("pending", "pending_authorizations_deleted"),
            ):
                expired = records.c.expires_at < int(time.time())
                if kind in ("code", "access"):
                    expired = or_(expired, records.c.used.is_(True))
                result = await connection.execute(
                    delete(records).where(*self._where(kind), expired)
                )
                counts[name] = result.rowcount
        return counts
