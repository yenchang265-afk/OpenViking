# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Validation for ``code.egress_proxies``: admin-managed proxies per source host.

Validation runs when config loads, so the admin config editor rejects a bad
route before a restart can stop the server. Errors never echo a password.
"""

from __future__ import annotations

import os
import re
import ssl
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote, urlparse

_HOST_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
_ROUTE_FIELDS = frozenset({"url", "username", "password", "ca_file"})


@dataclass(frozen=True)
class EgressProxyRoute:
    """One validated HTTP proxy for a source host."""

    url: str
    username: Optional[str] = None
    password: Optional[str] = field(default=None, repr=False)
    ca_file: Optional[str] = None

    @property
    def proxy_host(self) -> str:
        """Return ``host:port``, the only part of a route that is safe to display."""
        return urlparse(self.url).netloc

    @property
    def authenticated_url(self) -> str:
        """Return the proxy URL with percent-encoded credentials, for child processes."""
        if self.username is None:
            return self.url
        credentials = quote(self.username, safe="")
        if self.password is not None:
            credentials = f"{credentials}:{quote(self.password, safe='')}"
        return f"http://{credentials}@{self.proxy_host}"

    def ssl_context(self) -> Optional[ssl.SSLContext]:
        """Return a context trusting only ``ca_file``, or None for system defaults."""
        return ssl.create_default_context(cafile=self.ca_file) if self.ca_file else None


def _normalize_host(raw_host: object) -> str:
    host = raw_host.rstrip(".").lower() if isinstance(raw_host, str) else ""
    if not _HOST_PATTERN.match(host):
        raise ValueError(
            f"code.egress_proxies: host {raw_host!r} must be a bare host name, "
            "without scheme, port, path, or wildcard"
        )
    return host


def _validate_proxy_url(host: str, url: object) -> str:
    # Errors below never echo the URL, which may contain credentials.
    prefix = f"code.egress_proxies[{host}].url"
    if not isinstance(url, str):
        raise ValueError(f"{prefix} must be a string")
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{prefix} is not a valid URL") from exc
    # HTTPS proxies are rejected: urllib cannot speak TLS to a proxy and would
    # send Proxy-Authorization in cleartext to the proxy port.
    if parsed.scheme.lower() != "http" or not hostname or port is None:
        raise ValueError(f"{prefix} must look like http://host:port")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{prefix} must not contain credentials; use username and password")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError(f"{prefix} must not contain a path, query, or fragment")
    return f"http://{parsed.netloc}"


def _optional_string(host: str, name: str, value: object) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"code.egress_proxies[{host}].{name} must be a non-empty string")
    return value


def _parse_route(host: str, raw: object) -> EgressProxyRoute:
    if not isinstance(raw, dict):
        raise ValueError(f"code.egress_proxies[{host}] must be an object")
    unknown = sorted(set(raw) - _ROUTE_FIELDS)
    if unknown:
        raise ValueError(f"code.egress_proxies[{host}] has unknown fields: {unknown}")

    username = _optional_string(host, "username", raw.get("username"))
    password = _optional_string(host, "password", raw.get("password"))
    ca_file = _optional_string(host, "ca_file", raw.get("ca_file"))
    if password is not None and username is None:
        raise ValueError(f"code.egress_proxies[{host}].password requires username")
    if ca_file is not None and not os.path.isfile(ca_file):
        raise ValueError(f"code.egress_proxies[{host}].ca_file is not a readable file")
    return EgressProxyRoute(
        url=_validate_proxy_url(host, raw.get("url")),
        username=username,
        password=password,
        ca_file=ca_file,
    )


def parse_egress_proxies(raw: object) -> dict[str, EgressProxyRoute]:
    """Validate ``code.egress_proxies``; raises ValueError without echoing secrets."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("code.egress_proxies must be an object keyed by source host")
    routes: dict[str, EgressProxyRoute] = {}
    for raw_host, raw_route in raw.items():
        host = _normalize_host(raw_host)
        routes[host] = _parse_route(host, raw_route)
    return routes
