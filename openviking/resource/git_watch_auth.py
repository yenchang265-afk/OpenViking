# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Private authentication state for watched HTTPS Git repositories."""

from __future__ import annotations

from typing import Any, Dict, Optional

from openviking.utils.git_auth import GitHttpAuthConfig, parse_git_http_auth_config
from openviking_cli.exceptions import InvalidArgumentError

GIT_HTTP_AUTH_PROVIDER = "git_http_basic"


def create_git_http_auth_state(
    config: GitHttpAuthConfig,
    repo_url: str,
) -> Dict[str, Any]:
    """Create private, repository-bound auth state for a Git watch task."""
    state: Dict[str, Any] = {"provider": GIT_HTTP_AUTH_PROVIDER}
    if config.token is not None:
        state["username"] = config.username
        state["token"] = config.token
    if config.proxy is not None:
        state["proxy"] = config.proxy
    state["repo_url"] = repo_url.strip()
    return state


def is_git_http_auth_state(auth_state: Optional[Dict[str, Any]]) -> bool:
    return isinstance(auth_state, dict) and auth_state.get("provider") == GIT_HTTP_AUTH_PROVIDER


def git_http_auth_config_from_state(
    auth_state: Dict[str, Any],
    repo_url: str,
) -> Dict[str, str]:
    """Restore request-local Git auth after validating its repository binding."""
    bound_repo_url = auth_state.get("repo_url")
    if not isinstance(bound_repo_url, str) or bound_repo_url.strip() != repo_url.strip():
        raise InvalidArgumentError(
            "Stored Git watch credentials do not match the watched repository."
        )

    stored = {
        key: auth_state[key]
        for key in ("username", "token", "proxy")
        if auth_state.get(key) is not None
    }
    config = parse_git_http_auth_config(stored, repo_url)
    if config is None:  # pragma: no cover - the mapping above is never None
        raise InvalidArgumentError("Stored Git watch credentials are invalid.")
    restored: Dict[str, str] = {}
    if config.token is not None:
        restored["username"] = config.username
        restored["token"] = config.token
    if config.proxy is not None:
        restored["proxy"] = config.proxy
    return restored
