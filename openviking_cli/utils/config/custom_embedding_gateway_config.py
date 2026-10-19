# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Settings for the ``custom`` embedding provider's token-exchange gateway."""

import os
from typing import Any, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

ENVIRONMENT_PREFIX = "GATEWAY_"
REQUIRED_FIELDS = ("token_exchange_url", "embedding_url", "auth_header")


class CustomGatewayConfig(BaseModel):
    """Gateway endpoints, credentials and wire field names.

    Every field can be overridden by a non-empty ``GATEWAY_<FIELD>`` environment variable,
    which wins over ov.conf. Completeness is checked by ``validate_complete`` only when the
    ``custom`` provider is selected.
    """

    model_config = ConfigDict(extra="forbid")

    token_exchange_url: Optional[str] = None
    embedding_url: Optional[str] = None
    auth_header: Optional[str] = None
    api_token: Optional[str] = Field(default=None, repr=False)
    token_file: Optional[str] = None
    timeout: float = Field(default=30, gt=0)
    token_request_field: str = Field(default="key", min_length=1)
    token_response_field: str = Field(default="token", min_length=1)
    # The token endpoint reports no expiry, so a fixed lifetime is assumed.
    token_lifetime: float = Field(default=1200, gt=0)
    token_refresh_margin: float = Field(default=60, ge=0)
    success_code: str = "0"
    texts_field: str = Field(default="texts", min_length=1)
    model_field: str = Field(default="model", min_length=1)
    encoding_format_field: str = Field(default="encoding-format", min_length=1)
    code_field: str = Field(default="returnCode", min_length=1)
    message_field: str = Field(default="returnMessage", min_length=1)
    data_field: str = Field(default="returnData", min_length=1)

    @model_validator(mode="before")
    @classmethod
    def apply_environment(cls, value: Any) -> Any:
        if value is None:
            value = {}
        if not isinstance(value, dict):
            return value
        value = dict(value)
        for field in cls.model_fields:
            # An empty variable, such as a compose default, never overrides the file.
            if override := os.environ.get(ENVIRONMENT_PREFIX + field.upper(), ""):
                value[field] = override
        return value

    @model_validator(mode="after")
    def validate_values(self) -> "CustomGatewayConfig":
        if self.token_refresh_margin >= self.token_lifetime:
            raise ValueError("custom.token_refresh_margin must be smaller than token_lifetime")
        return self

    def validate_complete(self, label: str) -> None:
        """Raise one error naming every missing or invalid setting of the custom provider."""
        missing = [
            f"{ENVIRONMENT_PREFIX}{field.upper()} (custom.{field})"
            for field in REQUIRED_FIELDS
            if not getattr(self, field)
        ]
        if not self.api_token and not self.token_file:
            missing.append(
                f"{ENVIRONMENT_PREFIX}API_TOKEN or {ENVIRONMENT_PREFIX}TOKEN_FILE "
                "(custom.api_token or custom.token_file)"
            )
        if missing:
            raise ValueError(f"{label}: custom provider requires {', '.join(missing)}")
        for field in ("token_exchange_url", "embedding_url"):
            parsed = urlsplit(getattr(self, field))
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError(f"{label}: custom.{field} must be an http(s) URL")
