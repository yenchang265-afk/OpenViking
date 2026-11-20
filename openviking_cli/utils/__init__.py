# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Utility functions and helpers."""

from openviking_cli.utils.async_utils import run_async
from openviking_cli.utils.logger import default_logger, get_logger
from openviking_cli.utils.uri import VikingURI

# StructuredLLM, parse_json_from_response and parse_json_to_model stay importable
# from here through __getattr__ below; they are loaded lazily, so they are not
# listed in __all__ (a star import would otherwise initialize the LLM helpers).
__all__ = [
    "VikingURI",
    "get_logger",
    "default_logger",
    "run_async",
]


def __getattr__(name):
    # Importing logging must not initialize the application configuration through LLM helpers.
    if name in {"StructuredLLM", "parse_json_from_response", "parse_json_to_model"}:
        from openviking_cli.utils import llm

        return getattr(llm, name)
    raise AttributeError(name)
