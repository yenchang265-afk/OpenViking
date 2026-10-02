# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Elasticsearch client construction.

The ``elasticsearch`` package is an optional dependency:
``pip install "openviking[elasticsearch]"``.
"""

from __future__ import annotations

from typing import Any

from openviking_cli.utils.config.vectordb_config import ElasticsearchConfig


def import_elasticsearch() -> Any:
    try:
        import elasticsearch  # noqa: PLC0415
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise ImportError(
            "The Elasticsearch vector backend requires the 'elasticsearch' package. "
            'Install it with: pip install "openviking[elasticsearch]"'
        ) from error
    major = int(str(elasticsearch.__versionstr__).split(".")[0])
    if major != 8:
        raise ImportError(
            f"The Elasticsearch vector backend requires elasticsearch-py 8.x, found "
            f"{elasticsearch.__versionstr__}"
        )
    return elasticsearch


def create_client(config: ElasticsearchConfig) -> Any:
    elasticsearch = import_elasticsearch()
    kwargs: dict[str, Any] = {
        "hosts": list(config.hosts),
        "request_timeout": config.request_timeout,
        "verify_certs": config.verify_certs,
        "retry_on_timeout": True,
        "max_retries": 3,
    }
    if config.ca_certs:
        kwargs["ca_certs"] = config.ca_certs
    if config.api_key:
        kwargs["api_key"] = config.api_key
    elif config.username is not None:
        kwargs["basic_auth"] = (config.username, config.password or "")
    return elasticsearch.Elasticsearch(**kwargs)


def is_not_found(error: BaseException) -> bool:
    """True for an elasticsearch-py ApiError carrying HTTP 404."""
    return getattr(error, "status_code", None) == 404


def is_already_exists(error: BaseException) -> bool:
    """True when index creation lost a race with another creator."""
    return getattr(error, "error", None) == "resource_already_exists_exception"
