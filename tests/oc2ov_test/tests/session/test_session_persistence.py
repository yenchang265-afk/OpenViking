"""
Session 持久化測試
測試目標：驗證跨會話的記憶持久化功能
測試場景：寫入使用者資訊，使用不同 session-id 模擬新會話，驗證記憶讀取
"""

from tests.base_cli_test import BaseOpenClawCLITest


class TestMemoryPersistence(BaseOpenClawCLITest):
    """
    記憶跨會話讀取驗證
    測試目標：驗證OpenClaw重啟後，可從OpenViking正常讀取歷史記憶，記憶持久化生效
    測試場景：寫入使用者資訊，使用不同session-id模擬新會話，驗證記憶讀取
    """

    def test_memory_persistence_group_a(self):
        """測試組A：我喜歡吃櫻桃，日常喜歡喝美式咖啡"""
        self.logger.info("[1/5] 測試組A - 寫入記憶資訊")

        self.run_with_test_data(
            data_name="fruit_cherry",
            query_message="我喜歡吃什麼水果？平時愛喝什麼？",
        )

        self.logger.info("[3/5] 使用新的 session-id 模擬新會話")
        new_session = self.generate_unique_session_id(prefix="persistence_new_a")

        self.wait_for_sync()

        self.logger.info("[4/5] 在新會話中查詢記憶")
        response3 = self.send_and_log("我喜歡吃什麼水果？平時愛喝什麼？", session_id=new_session)

        self.logger.info("[5/5] 驗證記憶持久化讀取")
        self.assertAnyKeywordInResponse(
            response3, [["櫻桃"], ["美式", "咖啡"]], case_sensitive=False
        )

        self.logger.info("測試組A執行完成")

    def test_memory_persistence_group_b(self):
        """測試組B：我喜歡吃芒果，日常喜歡喝拿鐵咖啡"""
        self.logger.info("[1/5] 測試組B - 寫入記憶資訊")

        self.run_with_test_data(
            data_name="fruit_mango",
            query_message="我喜歡吃什麼水果？平時愛喝什麼？",
        )

        self.logger.info("[3/5] 使用新的 session-id 模擬新會話")
        new_session = self.generate_unique_session_id(prefix="persistence_new_b")

        self.wait_for_sync()

        self.logger.info("[4/5] 在新會話中查詢記憶")
        response3 = self.send_and_log("我喜歡吃什麼水果？平時愛喝什麼？", session_id=new_session)

        self.logger.info("[5/5] 驗證記憶持久化讀取")
        self.assertAnyKeywordInResponse(
            response3, [["芒果"], ["拿鐵", "咖啡"]], case_sensitive=False
        )

        self.logger.info("測試組B執行完成")

    def test_memory_persistence_group_c(self):
        """測試組C：我喜歡吃草莓，日常喜歡喝抹茶拿鐵"""
        self.logger.info("[1/5] 測試組C - 寫入記憶資訊")

        self.run_with_test_data(
            data_name="fruit_strawberry",
            query_message="我喜歡吃什麼水果？平時愛喝什麼？",
        )

        self.logger.info("[3/5] 使用新的 session-id 模擬新會話")
        new_session = self.generate_unique_session_id(prefix="persistence_new_c")

        self.wait_for_sync()

        self.logger.info("[4/5] 在新會話中查詢記憶")
        response3 = self.send_and_log("我喜歡吃什麼水果？平時愛喝什麼？", session_id=new_session)

        self.logger.info("[5/5] 驗證記憶持久化讀取")
        self.assertAnyKeywordInResponse(
            response3, [["草莓"], ["抹茶", "拿鐵"]], case_sensitive=False
        )

        self.logger.info("測試組C執行完成")


class TestMemoryPersistenceWithRetry(BaseOpenClawCLITest):
    """
    記憶持久化測試（帶重試機制）
    """

    def test_persistence_with_retry(self):
        """測試場景：使用重試機制驗證持久化"""
        self.logger.info("[1/3] 寫入記憶資訊")
        message = "我叫重試測試使用者，喜歡游泳"

        self.send_with_retry(message, max_retries=3)

        self.smart_wait_for_sync(
            check_message="我喜歡什麼運動",
            keywords=["游泳"],
            timeout=30.0,
        )

        self.logger.info("[2/3] 使用新會話查詢")
        new_session = self.generate_unique_session_id(prefix="retry_persistence")

        response = self.send_with_retry(
            "我喜歡什麼運動",
            session_id=new_session,
            max_retries=3,
        )

        self.logger.info("[3/3] 驗證記憶持久化")
        self.assertAnyKeywordInResponse(response, [["游泳"]], case_sensitive=False)
