# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
from typing import Any, Dict

from pydantic import Field, model_validator

from .backend_config import BackendSelectorConfig


class CacheConfig(BackendSelectorConfig):
    """Global cache Provider configuration shared by RAGFS modules."""

    provider: str = Field(alias="backend", description="Cache backend name")
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-owned configuration parameters",
        repr=False,
    )

    @model_validator(mode="after")
    def validate_config(self):
        if not self.provider.strip():
            raise ValueError("cache provider must not be empty")
        return self
