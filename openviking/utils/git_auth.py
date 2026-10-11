# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Request-local HTTP authentication for Git subprocesses."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from typing import Mapping, Optional
from urllib.parse import urlparse

from openviking_cli.exceptions import InvalidArgumentError, OpenVikingError

GIT_AUTH_FAILED = "GIT_AUTH_FAILED"


_GIT_PROXY_SCHEMES = frozenset({"http", "https", "socks5", "socks5h"})


def raise_git_auth_error(stderr: bytes) -> None:
    """Preserve explicit Git authentication failures without exposing credentials."""
    error = stderr.decode(errors="replace").lower()
    if "received http code 407 from proxy" in error:
        raise OpenVikingError(
            "Git proxy authentication failed. Check the proxy credentials.",
            code=GIT_AUTH_FAILED,
        )
    if any(
        marker in error
        for marker in (
            "authentication failed",
            "authentication failure",
            "http basic: access denied",
            "invalid username or password",
            "invalid username or token",
            "permission denied (publickey",
            "permission denied (password",
            "the requested url returned error: 401",
            "could not read username",
            "could not read password",
        )
    ):
        raise OpenVikingError(
            "Git authentication failed. Check your SSH keys or credentials.",
            code=GIT_AUTH_FAILED,
        )


def is_git_proxy_failure(stderr: bytes) -> bool:
    """Return whether Git's stderr reports a proxy connection failure."""
    error = stderr.decode(errors="replace").lower()
    return any(
        marker in error
        for marker in (
            "could not resolve proxy",
            "failed to connect to proxy",
            "from proxy after connect",
            "proxy connect aborted",
            "can't complete socks",
        )
    )


@dataclass(frozen=True)
class GitHttpAuthConfig:
    """Validated request-local HTTP access settings for one Git operation.

    ``token`` enables HTTP Basic auth (HTTPS only); ``proxy`` routes the Git
    HTTP(S) traffic through a proxy URL that may embed its own credentials.
    """

    username: str = "oauth2"
    token: Optional[str] = field(default=None, repr=False)
    proxy: Optional[str] = field(default=None, repr=False)


def is_git_https_url(repo_url: object) -> bool:
    """Return whether HTTP token authentication is valid for this Git URL."""
    return isinstance(repo_url, str) and repo_url.strip().lower().startswith("https://")


def reject_git_http_userinfo(repo_url: str) -> None:
    """Require HTTP(S) Git credentials to travel through ``auth_config``."""
    parsed = urlparse(repo_url)
    if parsed.scheme.lower() in {"http", "https"} and (
        parsed.username is not None or parsed.password is not None
    ):
        raise InvalidArgumentError(
            "HTTP(S) Git URLs cannot contain userinfo; use args.auth_config instead."
        )


def _has_whitespace_or_control(value: str) -> bool:
    return any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value)


def _validate_git_https_auth_url(repo_url: str) -> str:
    normalized = repo_url.strip() if isinstance(repo_url, str) else ""
    # The URL becomes part of a Git config key, so it must be a single token.
    if _has_whitespace_or_control(normalized):
        raise InvalidArgumentError(
            "Git URLs used with args.auth_config must not contain whitespace."
        )
    if not is_git_https_url(normalized):
        raise InvalidArgumentError(
            "args.auth_config token authentication requires an HTTPS Git URL."
        )
    return normalized


def _validate_git_http_proxy_url(repo_url: str) -> str:
    normalized = repo_url.strip() if isinstance(repo_url, str) else ""
    if _has_whitespace_or_control(normalized):
        raise InvalidArgumentError(
            "Git URLs used with args.auth_config must not contain whitespace."
        )
    if urlparse(normalized).scheme.lower() not in {"http", "https"}:
        raise InvalidArgumentError("args.auth_config.proxy requires an HTTP(S) Git URL.")
    return normalized


def _parse_git_proxy(value: object) -> str:
    """Validate a proxy URL without echoing it: it may carry credentials."""

    if not isinstance(value, str) or not value.strip():
        raise InvalidArgumentError("args.auth_config.proxy must be a non-empty string.")
    proxy = value.strip()
    if _has_whitespace_or_control(proxy):
        raise InvalidArgumentError("args.auth_config.proxy must not contain whitespace.")
    parsed = urlparse(proxy)
    if parsed.scheme.lower() not in _GIT_PROXY_SCHEMES:
        raise InvalidArgumentError(
            "args.auth_config.proxy must be an http://, https://, socks5:// or socks5h:// URL."
        )
    if not parsed.hostname:
        raise InvalidArgumentError("args.auth_config.proxy must include a host.")
    try:
        _ = parsed.port
    except ValueError:
        raise InvalidArgumentError("args.auth_config.proxy has an invalid port.") from None
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise InvalidArgumentError(
            "args.auth_config.proxy must not include a path, query, or fragment."
        )
    return proxy


def parse_git_http_auth_config(
    value: object,
    repo_url: str,
) -> GitHttpAuthConfig | None:
    """Validate an ``args.auth_config`` value for an HTTP(S) Git source."""

    if value is None:
        return None
    if not isinstance(value, dict):
        raise InvalidArgumentError("args.auth_config must be an object.")

    if set(value) - {"username", "token", "proxy"}:
        raise InvalidArgumentError("args.auth_config contains unsupported fields.")

    proxy = None
    if value.get("proxy") is not None:
        proxy = _parse_git_proxy(value["proxy"])
        _validate_git_http_proxy_url(repo_url)

    token = value.get("token")
    if token is None and proxy is not None:
        if "username" in value:
            raise InvalidArgumentError("args.auth_config.username requires a token.")
        return GitHttpAuthConfig(proxy=proxy)
    if not isinstance(token, str) or not token.strip():
        raise InvalidArgumentError("args.auth_config.token must be a non-empty string.")

    username = value.get("username", "oauth2")
    if not isinstance(username, str) or not username.strip():
        raise InvalidArgumentError("args.auth_config.username must be a non-empty string.")

    _validate_git_https_auth_url(repo_url)

    return GitHttpAuthConfig(username=username.strip(), token=token, proxy=proxy)


def git_http_basic_auth_header(config: GitHttpAuthConfig) -> str:
    """Return the Git ``http.extraHeader`` value for validated credentials."""

    credential = f"{config.username}:{config.token}".encode()
    encoded = base64.b64encode(credential).decode("ascii")
    return f"Authorization: Basic {encoded}"


def _append_git_process_config(env: dict[str, str], key: str, value: str) -> None:
    """Append a process-local Git config entry without putting it in argv."""

    try:
        count = int(env.get("GIT_CONFIG_COUNT", "0"))
    except ValueError:
        count = 0
    env[f"GIT_CONFIG_KEY_{count}"] = key
    env[f"GIT_CONFIG_VALUE_{count}"] = value
    env["GIT_CONFIG_COUNT"] = str(count + 1)


def build_git_http_auth_env(
    config: GitHttpAuthConfig,
    repo_url: str,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build an isolated child-process environment containing Git HTTP auth."""

    if config.token is not None:
        normalized_repo_url = _validate_git_https_auth_url(repo_url)
    else:
        normalized_repo_url = _validate_git_http_proxy_url(repo_url)
    env = dict(os.environ if base_env is None else base_env)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "Never"
    _append_git_process_config(env, "credential.helper", "")
    _append_git_process_config(env, f"credential.{normalized_repo_url}.helper", "")
    # Clear inherited extraHeader values before adding the one request-local
    # Authorization value. Git treats extraHeader as multi-valued otherwise.
    _append_git_process_config(env, "http.extraHeader", "")
    scoped_extra_header = f"http.{normalized_repo_url}.extraHeader"
    _append_git_process_config(env, scoped_extra_header, "")
    if config.token is not None:
        _append_git_process_config(
            env,
            scoped_extra_header,
            git_http_basic_auth_header(config),
        )
    # Refuse redirects at the same URL-specific precedence as the header, so
    # inherited per-repository config cannot move it to another host or HTTP.
    _append_git_process_config(
        env,
        f"http.{normalized_repo_url}.followRedirects",
        "false",
    )
    if config.proxy is not None:
        # URL-scoped so it outranks inherited http.proxy and *_proxy env vars
        # for this repository only.
        _append_git_process_config(env, f"http.{normalized_repo_url}.proxy", config.proxy)
    return env
