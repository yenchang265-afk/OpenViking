"""Startup connection defaults shared by storage subsystems."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import quote, urlencode

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .backend_config import backend_name


class MySQLTLSConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    ca: str | None = None
    cert: str | None = None
    key: str | None = None
    check_hostname: bool = True

    @model_validator(mode="after")
    def require_certificate_pair(self):
        if bool(self.cert) != bool(self.key):
            raise ValueError("MySQL TLS cert and key must be configured together")
        return self


class MySQLConnectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=3306, ge=1, le=65535)
    user: str = Field(min_length=1)
    password: str = Field(repr=False)
    database: str = Field(min_length=1)
    ssl: bool | MySQLTLSConfig | None = None

    def params(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)

    def tiered_dsn(self) -> str:
        """Encode the same endpoint, credentials and TLS policy for native SQLx."""
        host = self.host
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        query = {"ssl-mode": "DISABLED"}
        if self.ssl is True:
            query["ssl-mode"] = "VERIFY_IDENTITY"
        elif isinstance(self.ssl, MySQLTLSConfig):
            query["ssl-mode"] = "VERIFY_IDENTITY" if self.ssl.check_hostname else "VERIFY_CA"
            for name in ("ca", "cert", "key"):
                if value := getattr(self.ssl, name):
                    query[f"ssl-{name}"] = value
        return (
            f"mysql://{quote(self.user, safe='')}:{quote(self.password, safe='')}"
            f"@{host}:{self.port}/{quote(self.database, safe='')}?{urlencode(query)}"
        )


class ConnectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    def params(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class RedisConnectionConfig(ConnectionConfig):
    endpoints: list[str] = Field(min_length=1)
    mode: str = "standalone"
    username: str | None = None
    password: str | None = Field(default=None, repr=False)
    password_env: str | None = None
    db: int = 0
    master_name: str | None = None
    sentinel_username: str | None = None
    sentinel_password: str | None = Field(default=None, repr=False)
    sentinel_password_env: str | None = None
    tls_insecure_skip_verify: bool = False

    @model_validator(mode="after")
    def validate_connection(self):
        from .agfs_config import RedisCacheConfig

        RedisCacheConfig.model_validate(self.params())
        return self


class S3ConnectionConfig(ConnectionConfig):
    endpoint: str = Field(min_length=1)
    region: str = Field(min_length=1)
    bucket: str = Field(min_length=1)
    access_key: str = Field(min_length=1, repr=False)
    secret_key: str = Field(min_length=1, repr=False)
    use_ssl: bool | None = None
    use_path_style: bool = True


class ElasticsearchConnectionConfig(ConnectionConfig):
    hosts: list[str] = Field(min_length=1)
    username: str | None = None
    password: str | None = Field(default=None, repr=False)
    api_key: str | None = Field(default=None, repr=False)
    ca_certs: str | None = None
    verify_certs: bool = True

    @model_validator(mode="after")
    def validate_connection(self):
        from .vectordb_config import ElasticsearchConfig

        ElasticsearchConfig.model_validate(self.params())
        return self


class ConnectionsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    mysql: MySQLConnectionConfig | None = Field(default=None, repr=False)
    redis: RedisConnectionConfig | None = Field(default=None, repr=False)
    s3: S3ConnectionConfig | None = Field(default=None, repr=False)
    elasticsearch: ElasticsearchConnectionConfig | None = Field(default=None, repr=False)


_CONNECTION_FIELDS = frozenset(
    {"host", "port", "user", "password", "database", "ssl", "unix_socket"}
)


def resolve_connections(data: dict[str, Any]) -> dict[str, Any]:
    """Fill selected storage backends without mutating the input or environment.

    Complete legacy inline connections remain independent overrides. Pool/table
    options inherit central connection details; partial endpoint/credential
    overrides are rejected rather than accidentally mixing credentials.
    """
    raw = data.get("connections")
    if raw is None:
        return data
    connections = (
        raw if isinstance(raw, ConnectionsConfig) else ConnectionsConfig.model_validate(raw)
    )
    result = deepcopy(data)
    defaults = connections.mysql.params() if connections.mysql else {}

    def block(parent: dict, name: str, path: str) -> dict:
        value = parent.get(name)
        if value is None:
            return {}
        if isinstance(value, BaseModel):
            value = value.model_dump()
            parent[name] = value
        if not isinstance(value, dict):
            raise ValueError(f"{path} must be an object")
        return value

    def fill(section: dict, field: str, path: str):
        if connections.mysql is None:
            return
        local = section.get(field, {})
        if not isinstance(local, dict):
            raise ValueError(f"{path} must be an object")
        if _CONNECTION_FIELDS.intersection(local):
            if not {"user", "password", "database"}.issubset(local):
                raise ValueError(
                    f"{path} contains a partial MySQL connection; use connections.mysql "
                    "or specify a complete inline user/password/database connection"
                )
            return
        section[field] = {**deepcopy(defaults), **local}

    storage = block(result, "storage", "storage")
    task_store = block(storage, "task_store", "storage.task_store")
    if str(backend_name(task_store) or "").strip().lower() == "mysql":
        fill(task_store, "params", "storage.task_store.params")

    watch_store = block(storage, "watch_store", "storage.watch_store")
    if str(backend_name(watch_store) or "").strip().lower() == "mysql":
        fill(watch_store, "params", "storage.watch_store.params")

    server = block(result, "server", "server")
    account = block(server, "account_store", "server.account_store")
    provider = str(backend_name(account) or "").strip().lower()
    if provider == "mysql":
        fill(account, "params", "server.account_store.params")
    elif provider == "redis_mysql":
        params = account.setdefault("params", {})
        if not isinstance(params, dict):
            raise ValueError("server.account_store.params must be an object")
        fill(params, "mysql", "server.account_store.params.mysql")
    observability = block(server, "observability", "server.observability")
    usage = block(observability, "usage_audit", "server.observability.usage_audit")
    if usage.get("backend") == "mysql":
        fill(usage, "mysql", "server.observability.usage_audit.mysql")
    oauth = block(result, "oauth", "oauth")
    if oauth.get("backend") == "mysql":
        fill(oauth, "mysql", "oauth.mysql")

    def inherit(section: dict, field: str, kind: str, required: set[str], path: str):
        connection = getattr(connections, kind)
        if connection is None:
            return
        local = section.get(field, {})
        if local is None:
            local = {}
        if isinstance(local, BaseModel):
            local = local.model_dump(exclude_unset=True)
        if not isinstance(local, dict):
            raise ValueError(f"{path} must be an object")
        defaults = connection.params()
        fields = set(type(connection).model_fields)
        if fields.intersection(local):
            if not required.issubset(local):
                raise ValueError(
                    f"{path} contains a partial {kind} connection; use connections.{kind} or a complete inline connection"
                )
            return
        if kind == "s3" and path == "git.s3":
            defaults.pop("use_ssl", None)
        section[field] = {**defaults, **local}

    cache = block(result, "cache", "cache")
    if backend_name(cache) == "redis":
        inherit(cache, "params", "redis", {"endpoints"}, "cache.params")
    if provider == "redis_mysql":
        params = account.setdefault("params", {})
        account_cache = block(params, "cache", "server.account_store.params.cache")
        if backend_name(account_cache) == "redis":
            inherit(
                account_cache,
                "params",
                "redis",
                {"endpoints"},
                "server.account_store.params.cache.params",
            )
    agfs = block(storage, "agfs", "storage.agfs")
    s3_required = {"endpoint", "region", "bucket", "access_key", "secret_key"}
    if agfs.get("backend") == "s3":
        inherit(agfs, "s3", "s3", s3_required, "storage.agfs.s3")
    git = block(result, "git", "git")
    if git.get("backend") == "s3":
        inherit(git, "s3", "s3", s3_required, "git.s3")
    vectordb = block(storage, "vectordb", "storage.vectordb")
    if vectordb.get("backend") == "elasticsearch":
        inherit(
            vectordb, "elasticsearch", "elasticsearch", {"hosts"}, "storage.vectordb.elasticsearch"
        )
    return result


def resolve_mysql_connections(data: dict[str, Any]) -> dict[str, Any]:
    """Compatibility entry point for callers predating central storage connections."""
    return resolve_connections(data)
