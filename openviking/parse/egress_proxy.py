# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Route parser traffic for configured source hosts through admin-managed proxies.

Routes come only from server config (``code.egress_proxies``). They are never
accepted from API requests, because a caller-chosen proxy could steer server
traffic to arbitrary internal addresses and observe source credentials.

The route is chosen by the source URL and covers everything that fetch touches,
including redirects, and pages on other hosts that a web crawl follows.
"""

from __future__ import annotations

import base64
import urllib.request
from threading import RLock
from typing import Any, Mapping, Optional
from urllib.parse import urlparse

import httpx

from openviking.parse.network import (
    ParserNetworkContext,
    ParserNetworkOperation,
    current_parser_network_adapter,
    register_parser_network_adapter,
    reset_parser_network_adapter,
)
from openviking_cli.utils.config.egress_proxy_config import (
    EgressProxyRoute,
    parse_egress_proxies,
)


def _source_host(source: object) -> Optional[str]:
    """Return the host of an HTTP(S) source; SSH sources cannot use an HTTP proxy."""
    if not isinstance(source, str):
        return None
    try:
        parsed = urlparse(source.strip())
        hostname = parsed.hostname
    except ValueError:
        return None
    if parsed.scheme.lower() not in ("http", "https") or not hostname:
        return None
    return hostname.rstrip(".").lower()


class _RouteProxyHandler(urllib.request.BaseHandler):
    """Send every request through one proxy, ignoring the process's NO_PROXY."""

    handler_order = 100  # Same slot as urllib.request.ProxyHandler.

    def __init__(self, route: EgressProxyRoute) -> None:
        self._hostport = route.proxy_host
        self._authorization: Optional[str] = None
        if route.username is not None:
            raw = f"{route.username}:{route.password or ''}".encode()
            self._authorization = f"Basic {base64.b64encode(raw).decode('ascii')}"

    def _route(self, request: urllib.request.Request) -> None:
        if self._authorization is not None:
            # For HTTPS, urllib moves this header to the CONNECT request only.
            request.add_header("Proxy-authorization", self._authorization)
        request.set_proxy(self._hostport, "http")
        return None

    http_open = _route
    https_open = _route


class EgressProxyAdapter:
    """Parser network adapter that selects a proxy by exact source host."""

    def __init__(self, routes: Mapping[str, EgressProxyRoute]) -> None:
        self._routes = dict(routes)

    def route_for(self, source: object) -> Optional[EgressProxyRoute]:
        host = _source_host(source)
        return self._routes.get(host) if host else None

    def _require_route(self, context: ParserNetworkContext) -> EgressProxyRoute:
        route = self.route_for(context.source_url)
        if route is None:
            raise RuntimeError("Egress proxy adapter called for an unsupported source")
        return route

    def supports(self, context: ParserNetworkContext) -> bool:
        return self.route_for(context.source_url) is not None

    def create_httpx_transport(self, context: ParserNetworkContext) -> httpx.AsyncBaseTransport:
        route = self._require_route(context)
        ssl_context = route.ssl_context()
        auth = (route.username, route.password or "") if route.username is not None else None
        return httpx.AsyncHTTPTransport(
            proxy=httpx.Proxy(route.url, auth=auth),
            verify=ssl_context if ssl_context is not None else True,
        )

    def create_urllib_opener(self, context: ParserNetworkContext) -> urllib.request.OpenerDirector:
        route = self._require_route(context)
        # An empty ProxyHandler stops build_opener adding the environment one.
        handlers: list[urllib.request.BaseHandler] = [
            urllib.request.ProxyHandler({}),
            _RouteProxyHandler(route),
        ]
        ssl_context = route.ssl_context()
        if ssl_context is not None:
            handlers.append(urllib.request.HTTPSHandler(context=ssl_context))
        return urllib.request.build_opener(*handlers)

    def subprocess_env_overlay(self, context: ParserNetworkContext) -> Mapping[str, str]:
        # Never set GIT_CONFIG_* here: overlay values replace base values, which
        # would discard the source credentials build_git_http_auth_env() added.
        route = self._require_route(context)
        proxy_url = route.authenticated_url
        overlay = {
            "HTTP_PROXY": proxy_url,
            "HTTPS_PROXY": proxy_url,
            "http_proxy": proxy_url,
            "https_proxy": proxy_url,
            "NO_PROXY": "",
            "no_proxy": "",
        }
        if route.ca_file and context.operation is ParserNetworkOperation.GIT_COMMAND:
            overlay["GIT_SSL_CAINFO"] = route.ca_file
        return overlay


_installed: Optional[EgressProxyAdapter] = None
_lock = RLock()


def configure_egress_proxies(code_config: Any) -> None:
    """Make the process-wide adapter match ``code_config.egress_proxies``.

    Pass None to remove this module's routes. Fails on invalid config, or when
    routes are configured while another extension already owns parser egress.
    Without routes, another extension's adapter is left alone.
    """
    global _installed
    routes = parse_egress_proxies(getattr(code_config, "egress_proxies", None))
    with _lock:
        if _installed is not None and current_parser_network_adapter() is _installed:
            reset_parser_network_adapter()
        _installed = None
        if routes:
            adapter = EgressProxyAdapter(routes)
            register_parser_network_adapter(adapter)
            _installed = adapter


def egress_proxy_host_for(source: object) -> Optional[str]:
    """Return the display ``host:port`` of the proxy routing ``source``, if any."""
    with _lock:
        adapter = _installed
    # Report only what traffic really uses, even if the adapter was reset elsewhere.
    if adapter is None or current_parser_network_adapter() is not adapter:
        return None
    route = adapter.route_for(source)
    return route.proxy_host if route is not None else None


__all__ = [
    "EgressProxyAdapter",
    "EgressProxyRoute",
    "configure_egress_proxies",
    "egress_proxy_host_for",
    "parse_egress_proxies",
]
