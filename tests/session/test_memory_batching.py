# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0

import asyncio
import logging
import os
from unittest.mock import MagicMock, patch

import pytest

from openviking.storage.queuefs.semantic_msg import SemanticMsg
from openviking.storage.queuefs.semantic_processor import SemanticProcessor

# 設定手動測試標記：RUN_MANUAL=1 pytest tests/session/test_manual_memory_batching.py
skip_if_not_manual = pytest.mark.skipif(
    os.environ.get("RUN_MANUAL") != "1", reason="手動執行測試，需設定 RUN_MANUAL=1 執行"
)

logger = logging.getLogger(__name__)

# 西北大環線 10 天行程模板
TRIP_DAYS = [
    {"day": 1, "route": "西寧 - 青海湖", "highlights": "青海湖、騎行、油菜花"},
    {"day": 2, "route": "青海湖 - 茶卡鹽湖 - 大柴旦", "highlights": "天空之境、鹽層、戈壁"},
    {"day": 3, "route": "大柴旦 - 翡翠湖 - 青海雅丹", "highlights": "綠寶石湖泊、雅丹地貌"},
    {"day": 4, "route": "大柴旦 - 阿克塞 - 敦煌", "highlights": "石油小鎮、無人區"},
    {"day": 5, "route": "敦煌 - 莫高窟 - 鳴沙山", "highlights": "壁畫、月牙泉、沙漠"},
    {"day": 6, "route": "敦煌 - 瓜州 - 嘉峪關 - 張掖", "highlights": "雄關、長城、祁連雪山"},
    {"day": 7, "route": "張掖丹霞 - 扁都口 - 祁連", "highlights": "七彩丹霞、祁連山"},
    {"day": 8, "route": "祁連 - 卓爾山 - 祁連山草原 - 門源", "highlights": "東方瑞士、油菜花海"},
    {"day": 9, "route": "門源 - 達坂山 - 西寧", "highlights": "大通河、塔爾寺、美食"},
    {"day": 10, "route": "西寧 - 返程", "highlights": "回味無窮、離別感悟"},
]


class NorthwestTripMockVLM:
    """模擬 LLM 生成西北大環線旅行日記和摘要。"""

    def __init__(self):
        self.is_available = MagicMock(return_value=True)
        self.call_count = 0
        self.max_concurrent = 20

    async def get_completion_async(self, prompt: str) -> str:
        self.call_count += 1
        # 根據 prompt 內容模擬不同的生成結果
        if "summary" in prompt.lower() or "摘要" in prompt:
            return f"【生成摘要】：這份日記詳細記錄了西北大環線第 {self.call_count % 10 + 1} 天的旅程。重點包括了該地的自然景觀與人文感悟，字數充足，情感真摯。"

        # 構造約 1000 字的詳細日記
        day_info = TRIP_DAYS[self.call_count % 10]
        content = f"今天是西北大環線的第 {day_info['day']} 天，行程是 {day_info['route']}。 "
        content += f"主要景點有 {day_info['highlights']}。 "
        content += "西北的景色真是讓人震撼，廣袤的戈壁，潔白的鹽湖，還有那一抹抹翠綠的翡翠湖，每一處都像是上帝打翻的調色盤。 "
        content += "在路上，我們感受到了大自然的鬼斧神工，也體會到了生命的頑強。那些在荒漠中佇立的雅丹，彷彿在訴說著千年的孤獨。 "
        content += "每一步都是風景，每一眼都是永恆。這裡的風帶著沙土的味道，陽光灼熱卻不刺眼。 "
        # 擴充到約 1000 字
        return (content * 10)[:2000]


@skip_if_not_manual
@pytest.mark.asyncio
async def test_manual_memory_batching_100_files(monkeypatch):
    """
    西北大環線 100 個檔案壓力測試。

    1. 模擬 10 天行程，每天 10 篇日記，共 100 個檔案。
    2. 每個檔案約 1000 字，模擬流水帳。
    3. 驗證分批處理（Batching）邏輯是否能平滑處理 100 個檔案的併發摘要生成。
    """
    file_count = 100
    mock_vlm = NorthwestTripMockVLM()

    # 1. 模擬配置
    mock_config = MagicMock()
    mock_config.vlm = mock_vlm
    mock_config.language_fallback = "zh-CN"
    mock_config.semantic.max_file_content_chars = 30000
    mock_config.semantic.max_skeleton_chars = 5000
    mock_config.semantic.max_overview_prompt_chars = 60000
    mock_config.semantic.overview_batch_size = 50
    mock_config.semantic.abstract_max_chars = 256
    mock_config.semantic.overview_max_chars = 4000
    mock_config.semantic.max_concurrent_llm = 10

    # 2. 模擬 AGFS/VikingFS 中的 100 個檔案
    class MockVikingFS:
        def __init__(self):
            self.files = []
            for i in range(file_count):
                day = (i // 10) + 1
                entry = (i % 10) + 1
                self.files.append(
                    {
                        "name": f"day_{day:02d}_entry_{entry:02d}.txt",
                        "isDir": False,
                        "uri": f"viking://user/memories/northwest_trip/day_{day:02d}_entry_{entry:02d}.txt",
                    }
                )

        async def ls(self, uri, ctx=None):
            return self.files

        async def read_file(self, uri, ctx=None):
            # 模擬讀取 1000 字的流水帳（由 LLM 構造）
            return await mock_vlm.get_completion_async(f"Generate diary for {uri}")

        async def write_file(self, uri, content, ctx=None):
            return True

        def _uri_to_path(self, uri, ctx=None):
            return uri.replace("viking://", "/")

    mock_fs = MockVikingFS()

    # 使用 patch.multiple 來模擬多個 get_xxx 方法
    with (
        patch(
            "openviking.storage.queuefs.semantic_processor.get_openviking_config",
            return_value=mock_config,
        ),
        patch("openviking.storage.queuefs.semantic_processor.get_viking_fs", return_value=mock_fs),
    ):
        # 4. 初始化 Processor 並設定併發
        processor = SemanticProcessor(max_concurrent_llm=10)

        # --- 增加併發監控邏輯 ---
        active_concurrency = 0
        max_observed_concurrency = 0
        generate_summary_calls = []
        _generate_single_file_summary = processor._generate_single_file_summary

        async def mock_generate_summary(*args, **kwargs):
            nonlocal active_concurrency, max_observed_concurrency, generate_summary_calls
            # 增加 LLM 呼叫計數以滿足後續斷言
            try:
                active_concurrency += 1
                # 進入方法：併發計數增加
                max_observed_concurrency = max(max_observed_concurrency, active_concurrency)
                # 模擬 I/O 耗時，給事件迴圈排程其他協程的機會
                await asyncio.sleep(0.01)
                return await _generate_single_file_summary(*args, **kwargs)
            finally:
                active_concurrency -= 1

        # 將增強後的 mock 應用到 processor
        monkeypatch.setattr(processor, "_generate_single_file_summary", mock_generate_summary)

        # 5. 構造訊息
        msg = SemanticMsg(
            uri="viking://user/memories/northwest_trip",
            context_type="memory",
            telemetry_id="tel-stress-northwest-100",
            changes={"added": [f["uri"] for f in mock_fs.files], "modified": [], "deleted": []},
        )

        # 6. 執行測試
        print(f"\n[Manual Test] 正在處理 {file_count} 個西北大環線旅行記憶檔案（分批模式）...")
        await processor._process_memory_directory(msg)

    # 7. 驗證結果
    print(f"[Manual Test] 處理完成。LLM 總呼叫次數: {mock_vlm.call_count}")
    print(f"[Verification] 峰值併發數: {max_observed_concurrency}")

    # 斷言峰值併發不超過 batch_size (10)
    assert max_observed_concurrency <= 10, (
        f"併發數過高: {max_observed_concurrency}，分批邏輯可能失效！"
    )
    assert max_observed_concurrency > 0

    # 100次 摘要生成 + 1次 overview(L1) + 1次 abstract(L0)
    # 因為 read_file 也被 mock 了，所以構造過程不再消耗 call_count
    assert mock_vlm.call_count >= 102

    print("[Manual Test] 分批邏輯壓力測試及併發驗證成功。")


if __name__ == "__main__":
    # 方便直接執行此指令碼
    os.environ["RUN_MANUAL"] = "1"
    import sys

    sys.exit(pytest.main([__file__]))
