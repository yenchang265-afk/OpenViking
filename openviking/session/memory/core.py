# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""
Extract Context Provider - 抽象接口

定義 ExtractLoop 使用的 Provider 介面，支援兩種場景：
1. SessionExtractContextProvider - 從會話訊息提取記憶
2. ConsolidationExtractContextProvider - 定時整理已有記憶
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from openviking.server.identity import RequestContext


class ExtractContextProvider(ABC):
    """Extract Context Provider 接口"""

    @abstractmethod
    def instruction(self) -> str:
        """
        指令 - Provider 相關，包含 goal、conversation 等

        Returns:
            完整的指令描述
        """
        pass

    async def prepare_extraction_messages(self) -> None:
        """
        在構建 prompt、ranges 和 ExtractContext 之前準備 extraction-only messages。
        """
        return None

    @abstractmethod
    async def prefetch(
        self,
    ) -> List[Dict]:
        """
        執行 prefetch

        Args:
            ctx: RequestContext
            viking_fs: VikingFS
            transaction_handle: 事務控制代碼
            vlm: VLM 例項

        Returns:
            預取的 tool call messages 列表
        """
        pass

    @abstractmethod
    def get_tools(self) -> List[str]:
        """
        獲取可用的工具列表

        Returns:
            工具名稱列表
        """
        pass

    @abstractmethod
    def get_memory_schemas(self, ctx: RequestContext) -> List[Any]:
        """
        獲取需要參與的 memory schemas

        Args:
            ctx: RequestContext

        Returns:
            需要參與的 MemoryTypeSchema 列表
        """
        pass
