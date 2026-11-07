"""Startup connection defaults shared by the MySQL-backed subsystems."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import quote, urlencode

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class ConnectionsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    mysql: MySQLConnectionConfig | None = Field(default=None, repr=False)


_CONNECTION_FIELDS = frozenset(
    {"host", "port", "user", "password", "database", "ssl", "unix_socket"}
)


def resolve_mysql_connections(data: dict[str, Any]) -> dict[str, Any]:
    """Fill only selected MySQL backends, without mutating the input or environment.

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
    if connections.mysql is None:
        return data
    result = deepcopy(data)
    defaults = connections.mysql.params()

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
    if str(task_store.get("provider", "")).strip().lower() == "mysql":
        fill(task_store, "params", "storage.task_store.params")

    server = block(result, "server", "server")
    account = block(server, "account_store", "server.account_store")
    provider = str(account.get("provider", "")).strip().lower()
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
    return result
