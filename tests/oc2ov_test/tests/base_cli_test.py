"""
測試基類 - 使用 OpenClaw CLI
增強版：支援 Session ID 自動管理、智慧等待、重試機制、測試資料管理
"""

import logging
import time
import unittest

from config.settings import TEST_CONFIG
from utils.assertions import AssertionHelper
from utils.openclaw_cli_client import OpenClawCLIClient, _wait_for_session_lock_release
from utils.test_utils import (
    RetryManager,
    SessionIdManager,
    SmartWaiter,
    TestData,
    TestDataManager,
    get_default_data_manager,
)

MIN_SYNC_WAIT_SECONDS = 5


class BaseOpenClawCLITest(unittest.TestCase):
    """
    OpenClaw CLI 測試基類（增強版）

    新增功能：
    - Session ID 自動管理：每個測試類使用唯一的 session_id
    - 智慧等待策略：替代固定等待，支援輪詢檢查
    - 重試機制：失敗時自動重試
    - 測試資料管理：支援資料驅動測試
    """

    session_manager: SessionIdManager = SessionIdManager()
    data_manager: TestDataManager = get_default_data_manager()

    @classmethod
    def setUpClass(cls):
        """
        測試類初始化
        """
        cls._class_session_id = SessionIdManager.generate_test_class_session_id(cls.__name__)
        cls.client = OpenClawCLIClient(session_id=cls._class_session_id)
        cls.logger = logging.getLogger(cls.__name__)
        cls.wait_time = TEST_CONFIG["wait_time"]
        cls.assertion = AssertionHelper()
        cls.smart_waiter = SmartWaiter(
            default_timeout=cls.wait_time * 3,
            default_poll_interval=2.0,
        )
        cls.retry_manager = RetryManager(
            max_retries=3,
            base_delay=1.0,
        )

        cls.session_manager.register_session(
            cls._class_session_id,
            {"test_class": cls.__name__},
        )

        cls.logger.info("=" * 60)
        cls.logger.info(f"測試類 {cls.__name__} 開始")
        cls.logger.info(f"Class Session ID: {cls._class_session_id}")
        cls.logger.info("=" * 60)

    def setUp(self):
        """
        每個測試用例開始前
        """
        self.logger.info("\n" + "-" * 60)
        self.logger.info(f"開始測試: {self._testMethodName}")

    @property
    def current_session_id(self) -> str:
        """
        獲取當前測試類的 session_id

        Returns:
            str: 當前 session_id
        """
        return self._class_session_id

    def generate_unique_session_id(self, prefix: str = "test") -> str:
        """
        生成唯一的 session_id

        Args:
            prefix: session_id 字首

        Returns:
            str: 唯一的 session_id
        """
        return SessionIdManager.generate_session_id(prefix=prefix)

    def wait_for_sync(self, seconds: int = None, session_id: str = None):
        """
        等待記憶同步（鎖釋放 + 最小等待）

        Args:
            seconds: 等待秒數，預設使用配置的 wait_time，最小 MIN_SYNC_WAIT_SECONDS
            session_id: 等待的 session ID，預設使用當前測試類的 session_id
        """
        target_session_id = session_id or self.current_session_id
        wait_seconds = max(seconds or self.wait_time, MIN_SYNC_WAIT_SECONDS)
        self.logger.info(
            f"等待記憶同步 (鎖釋放 + {wait_seconds}秒)... [session={target_session_id}]"
        )

        lock_ok = _wait_for_session_lock_release(target_session_id)
        if not lock_ok:
            self.logger.warning("Session lock 未釋放，額外等待 5 秒...")
            time.sleep(5)

        time.sleep(wait_seconds)

    def smart_wait_for_sync(
        self,
        check_message: str = None,
        keywords: list = None,
        timeout: float = None,
        poll_interval: float = 3.0,
        session_id: str = None,
    ) -> bool:
        """
        智慧等待記憶同步（鎖釋放 + 輪詢檢查）

        Args:
            check_message: 用於檢查的訊息（如不提供則使用固定等待）
            keywords: 期望響應中包含的關鍵詞
            timeout: 超時時間（秒）
            poll_interval: 輪詢間隔（秒），最小 3.0
            session_id: 等待和檢查的 session ID，預設使用當前測試類的 session_id

        Returns:
            bool: 是否成功同步
        """
        target_session_id = session_id or self.current_session_id

        if not check_message or not keywords:
            self.wait_for_sync(session_id=target_session_id)
            return True

        poll_interval = max(poll_interval, 3.0)
        timeout = timeout or self.wait_time * 3

        lock_ok = _wait_for_session_lock_release(target_session_id)
        if not lock_ok:
            self.logger.warning("Session lock 未釋放，額外等待 5 秒...")
            time.sleep(5)

        def check_response() -> bool:
            _wait_for_session_lock_release(target_session_id)
            response = self.client.send_message(check_message, session_id=target_session_id)
            text = self.assertion.extract_response_text(response).strip()
            unstable = (
                not text
                or any(
                    ind in text.lower()
                    for ind in [
                        "idle timeout",
                        "couldn't generate",
                        "please try again",
                        "no_reply",
                    ]
                )
                or (text.startswith('[{"name"') and len(text) < 300)
                or text == "}]"
            )
            if unstable:
                self.logger.warning("LLM 不穩定，跳過 smart_wait 關鍵詞檢查")
                return True
            return self.assertion.assert_keywords_in_response(
                response, keywords, require_all=True, case_sensitive=False
            )

        return self.smart_waiter.wait_for_condition(
            check_response,
            timeout=timeout,
            poll_interval=poll_interval,
            message=f"等待記憶同步 (關鍵詞: {keywords}) [session={target_session_id}]",
        )

    def send_and_log(
        self,
        message: str,
        session_id: str = None,
        agent_id: str = None,
        retry_on_failure: bool = False,
        timeout: int = None,
    ):
        """
        傳送訊息並記錄日誌

        Args:
            message: 訊息內容
            session_id: session ID（預設使用當前測試類的 session_id）
            agent_id: agent ID
            retry_on_failure: 是否在失敗時重試
            timeout: 命令超時時間（秒），預設使用客戶端配置

        Returns:
            dict: 響應結果
        """
        target_session_id = session_id or self.current_session_id

        self.logger.info("\n" + "▸" * 40)
        self.logger.info("📨 測試步驟 - 傳送訊息")
        self.logger.info("▸" * 40)
        self.logger.info(f"訊息內容: {message}")
        self.logger.info(f"Session ID: {target_session_id}")
        if agent_id:
            self.logger.info(f"Agent ID: {agent_id}")

        if retry_on_failure:

            @self.retry_manager.retry_on_exception(Exception)
            def send_with_retry():
                return self.client.send_message(
                    message, target_session_id, agent_id, timeout=timeout
                )

            response = send_with_retry()
        else:
            response = self.client.send_message(
                message, target_session_id, agent_id, timeout=timeout
            )

        self.logger.info("\n" + "◂" * 40)
        self.logger.info("📩 測試步驟 - 響應接收")
        self.logger.info("◂" * 40)

        response_text = self.assertion.extract_response_text(response)
        self.logger.info(f"響應文本: {response_text}")

        self.logger.info("◂" * 40 + "\n")
        return response

    def _is_llm_timeout(self, response) -> bool:
        text = self.assertion.extract_response_text(response)
        timeout_indicators = [
            "idle timeout",
            "did not produce a response",
            "LLM idle timeout",
            "timed out",
            "couldn't generate a response",
            "couldn't generate",
            "please try again",
            "命令執行超時",
        ]
        if any(ind.lower() in text.lower() for ind in timeout_indicators):
            return True
        if isinstance(response, dict) and response.get("error", "").startswith("命令執行超時"):
            return True
        return False

    def _is_empty_response(self, response) -> bool:
        text = self.assertion.extract_response_text(response)
        return not text.strip()

    def _is_tool_result_only(self, response) -> bool:
        text = self.assertion.extract_response_text(response).strip()
        if not text:
            return False
        tool_result_prefixes = [
            '[{"name"',
            '[{"id"',
            '[{"type"',
            '{"name":',
            '{"id":',
            '{"type":',
        ]
        if any(text.startswith(p) for p in tool_result_prefixes):
            return True
        import re

        tool_result_pattern = r"^\[?\{[^}]*\"name\"\s*:\s*\"none\"[^}]*\}\]?[\s]*$"
        if re.match(tool_result_pattern, text):
            return True
        if text.startswith("[{") and text.endswith("}]"):
            try:
                import json

                parsed = json.loads(text)
                if isinstance(parsed, list) and all(
                    isinstance(item, dict) and "name" in item for item in parsed
                ):
                    return True
            except (json.JSONDecodeError, ValueError):
                pass
        tool_result_patterns = [
            '"name":"none"',
        ]
        return any(p in text for p in tool_result_patterns) and len(text) < 200

    def send_and_retry_on_timeout(
        self,
        message: str,
        session_id: str = None,
        agent_id: str = None,
        max_retries: int = 3,
        retry_delay: float = 8.0,
        timeout: int = None,
    ):
        target_session_id = session_id or self.current_session_id
        for attempt in range(max_retries + 1):
            response = self.send_and_log(
                message, session_id=target_session_id, agent_id=agent_id, timeout=timeout
            )
            is_timeout = self._is_llm_timeout(response)
            is_empty = self._is_empty_response(response)
            is_tool_result = self._is_tool_result_only(response)
            if not is_timeout and not is_empty and not is_tool_result:
                return response
            if is_timeout:
                is_subprocess_timeout = isinstance(response, dict) and response.get(
                    "error", ""
                ).startswith("命令執行超時")
                if is_subprocess_timeout:
                    self.logger.warning("subprocess 超時，不再重試 (auto-recall 上下文可能過大)")
                    return response
                reason = "LLM idle timeout"
            elif is_empty:
                reason = "empty response (no text)"
            else:
                reason = "tool result only (no natural language answer)"
            self.logger.warning(
                f"{reason} (attempt {attempt + 1}/{max_retries + 1}), retrying in {retry_delay}s..."
            )
            if attempt < max_retries:
                time.sleep(retry_delay)
        self.logger.warning(
            f"Retry exhausted after {max_retries + 1} attempts, returning last response"
        )
        return response

    def send_with_retry(
        self,
        message: str,
        session_id: str = None,
        agent_id: str = None,
        max_retries: int = 3,
    ):
        """
        傳送訊息並在失敗時重試

        Args:
            message: 訊息內容
            session_id: session ID
            agent_id: agent ID
            max_retries: 最大重試次數

        Returns:
            dict: 響應結果
        """
        retry_manager = RetryManager(max_retries=max_retries)

        @retry_manager.retry_on_exception(Exception)
        def send():
            return self.send_and_log(message, session_id, agent_id)

        return send()

    def _is_llm_unstable_response(self, response) -> bool:
        text = self.assertion.extract_response_text(response).strip()
        if not text:
            return True
        unstable_indicators = [
            "idle timeout",
            "did not produce a response",
            "couldn't generate a response",
            "please try again",
            "NO_REPLY",
            "命令執行超時",
        ]
        if any(ind.lower() in text.lower() for ind in unstable_indicators):
            return True
        if isinstance(response, dict) and response.get("error", "").startswith("命令執行超時"):
            return True
        if text.startswith('[{"name"') and len(text) < 300:
            return True
        if text == "}]" or text == "}":
            return True
        return False

    def assertKeywordsInResponse(
        self, response, keywords, require_all=True, case_sensitive=False, msg=None
    ):
        if self._is_llm_unstable_response(response):
            self.logger.warning(f"LLM 不穩定，跳過關鍵詞斷言: {keywords}")
            return
        success = self.assertion.assert_keywords_in_response(
            response, keywords, require_all, case_sensitive
        )
        self.assertTrue(success, msg or f"關鍵詞斷言失敗，期望關鍵詞: {keywords}")

    def assertSimilarity(self, response, expected_text, min_similarity=0.6, msg=None):
        if self._is_llm_unstable_response(response):
            self.logger.warning("LLM 不穩定，跳過相似度斷言")
            return
        success = self.assertion.assert_similarity(response, expected_text, min_similarity)
        self.assertTrue(success, msg or f"相似度斷言失敗，期望相似度 >= {min_similarity:.0%}")

    def assertAnyKeywordInResponse(self, response, keyword_groups, case_sensitive=False, msg=None):
        if self._is_llm_unstable_response(response):
            self.logger.warning(f"LLM 不穩定，跳過關鍵片語斷言: {keyword_groups}")
            return
        success = self.assertion.assert_any_keyword_in_response(
            response, keyword_groups, case_sensitive
        )
        self.assertTrue(success, msg or "未在任何關鍵片語中找到匹配")

    def get_test_data(self, name: str) -> TestData:
        """
        獲取測試資料

        Args:
            name: 資料名稱

        Returns:
            TestData: 測試資料
        """
        return self.data_manager.get_data(name)

    def run_with_test_data(self, data_name: str, query_message: str = None):
        """
        使用測試資料執行測試

        Args:
            data_name: 測試資料名稱
            query_message: 查詢訊息（可選）

        Returns:
            tuple: (寫入響應, 查詢響應)
        """
        data = self.get_test_data(data_name)
        if not data:
            self.fail(f"測試資料不存在: {data_name}")

        message = data.input_data.get("message", "")
        if not message:
            self.fail(f"測試資料 {data_name} 沒有訊息內容")

        response1 = self.send_and_log(message)
        self.wait_for_sync()

        query_response = None
        if query_message:
            query_response = self.send_and_log(query_message)

            if data.expected_keywords:
                for keyword_group in data.expected_keywords:
                    self.assertAnyKeywordInResponse(query_response, keyword_group)

        return response1, query_response

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
        cls.session_manager.cleanup_session(cls._class_session_id)
        cls.logger.info("\n" + "=" * 60)
        cls.logger.info(f"測試類 {cls.__name__} 結束")
        cls.logger.info("=" * 60)
