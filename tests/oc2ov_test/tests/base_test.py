"""
測試基類
"""

import logging
import time
import unittest

from config.settings import TEST_CONFIG
from utils.assertions import AssertionHelper
from utils.openclaw_client import OpenClawClient


class BaseOpenClawTest(unittest.TestCase):
    """
    OpenClaw 測試基類
    """

    @classmethod
    def setUpClass(cls):
        """
        測試類初始化
        """
        cls.client = OpenClawClient()
        cls.logger = logging.getLogger(cls.__name__)
        cls.wait_time = TEST_CONFIG["wait_time"]
        cls.assertion = AssertionHelper()
        cls.logger.info("=" * 60)
        cls.logger.info(f"測試類 {cls.__name__} 開始")
        cls.logger.info("=" * 60)

    def setUp(self):
        """
        每個測試用例開始前
        """
        self.logger.info("\n" + "-" * 60)
        self.logger.info(f"開始測試: {self._testMethodName}")

    def wait_for_sync(self, seconds: int = None):
        """
        等待記憶同步
        """
        wait_seconds = seconds or self.wait_time
        self.logger.info(f"等待 {wait_seconds} 秒，確認記憶同步...")
        time.sleep(wait_seconds)

    def send_and_log(self, message: str, agent_id: str = None):
        """
        傳送訊息並記錄日誌
        """
        self.logger.info("\n" + "▸" * 40)
        self.logger.info("📨 測試步驟 - 傳送訊息")
        self.logger.info("▸" * 40)
        self.logger.info(f"訊息內容: {message}")
        if agent_id:
            self.logger.info(f"Agent ID: {agent_id}")

        response = self.client.send_message(message, agent_id)

        self.logger.info("\n" + "◂" * 40)
        self.logger.info("📩 測試步驟 - 響應接收")
        self.logger.info("◂" * 40)

        # 提取並顯示響應文本
        response_text = self.assertion.extract_response_text(response)
        self.logger.info(f"響應文本: {response_text}")

        self.logger.info("◂" * 40 + "\n")
        return response

    def assertKeywordsInResponse(
        self, response, keywords, require_all=True, case_sensitive=False, msg=None
    ):
        """
        斷言響應中包含指定關鍵詞
        """
        success = self.assertion.assert_keywords_in_response(
            response, keywords, require_all, case_sensitive
        )
        self.assertTrue(success, msg or f"關鍵詞斷言失敗，期望關鍵詞: {keywords}")

    def assertSimilarity(self, response, expected_text, min_similarity=0.6, msg=None):
        """
        斷言響應文本與期望文本的相似度
        """
        success = self.assertion.assert_similarity(response, expected_text, min_similarity)
        self.assertTrue(success, msg or f"相似度斷言失敗，期望相似度 >= {min_similarity:.0%}")

    def assertAnyKeywordInResponse(self, response, keyword_groups, case_sensitive=False, msg=None):
        """
        斷言響應中包含任意一組關鍵詞中的任意一個
        """
        success = self.assertion.assert_any_keyword_in_response(
            response, keyword_groups, case_sensitive
        )
        self.assertTrue(success, msg or "未在任何關鍵片語中找到匹配")

    def tearDown(self):
        """
        每個測試用例結束後
        """
        self.logger.info(f"測試完成: {self._testMethodName}")

    @classmethod
    def tearDownClass(cls):
        """
        測試類結束
        """
        cls.logger.info("\n" + "=" * 60)
        cls.logger.info(f"測試類 {cls.__name__} 結束")
        cls.logger.info("=" * 60)
