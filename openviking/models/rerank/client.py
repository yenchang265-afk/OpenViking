# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Rerank client factory.

Dispatches a RerankConfig to the matching provider client.
"""

from typing import Optional

from openviking.models.rerank.base import RerankBase


class RerankClient:
    """Factory for rerank provider clients (cohere, litellm, openai, jev)."""

    @classmethod
    def from_config(cls, config) -> Optional[RerankBase]:
        """Create a provider client from RerankConfig, or None if unavailable."""
        if not config or not config.is_available():
            return None

        provider = config._effective_provider()

        if provider == "cohere":
            from openviking.models.rerank.cohere_rerank import CohereRerankClient

            return CohereRerankClient.from_config(config)

        if provider == "litellm":
            from openviking.models.rerank.litellm_rerank import LiteLLMRerankClient

            return LiteLLMRerankClient.from_config(config)

        if provider == "openai":
            from openviking.models.rerank.openai_rerank import OpenAIRerankClient

            return OpenAIRerankClient.from_config(config)

        if provider == "jev":
            from openviking.models.rerank.jev_rerank import JevRerankClient

            return JevRerankClient.from_config(config)

        return None
