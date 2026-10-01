"""
技能相關測試
測試目標：驗證技能呼叫後的記憶功能
注意：簡化為記憶讀寫測試，避免外部技能依賴
"""

from tests.base_cli_test import BaseOpenClawCLITest


class TestSkillExperiencePrecipitation(BaseOpenClawCLITest):
    """
    銷售資料查詢技能經驗沉澱驗證（P1）
    測試目標：驗證記憶讀寫功能正常，資料能正確儲存和檢索
    測試場景：先發送簡單資料，再驗證讀取功能
    """

    def test_skill_experience_group_a(self):
        """測試組A：簡單記憶讀寫測試-先記住資訊再讀取"""
        self.logger.info("[1/2] 測試組A - 步驟1：記住個人資訊")
        session_a = self.generate_unique_session_id(prefix="skill_exp_a")

        self.send_and_log("請記住：我叫小明，今年25歲，住在上海", session_id=session_a)

        self.smart_wait_for_sync(
            check_message="我叫什麼名字",
            keywords=["小明"],
            timeout=30.0,
        )

        self.logger.info("[2/2] 步驟2：驗證資訊讀取")
        response2 = self.send_and_log("我叫什麼名字？今年多大？", session_id=session_a)

        self.assertAnyKeywordInResponse(response2, [["小明", "25", "上海"]], case_sensitive=False)

        self.logger.info("測試組A執行完成")

    def test_skill_experience_group_b(self):
        """測試組B：跨會話記憶讀取測試"""
        self.logger.info("[1/2] 測試組B - 步驟1：記住個人資訊")
        session_b = self.generate_unique_session_id(prefix="skill_exp_b")

        self.send_and_log("請記住：我是小紅，職業是設計師，喜歡畫畫", session_id=session_b)

        self.smart_wait_for_sync(
            check_message="我是誰",
            keywords=["小紅"],
            timeout=30.0,
        )

        self.logger.info("[2/2] 步驟2：驗證資訊讀取")
        response2 = self.send_and_log("我的職業是什麼？我的愛好是什麼？", session_id=session_b)

        self.assertAnyKeywordInResponse(
            response2, [["小紅", "設計師", "畫畫"]], case_sensitive=False
        )

        self.logger.info("測試組B執行完成")

    def test_skill_experience_group_c(self):
        """測試組C：記憶更新功能測試"""
        self.logger.info("[1/3] 測試組C - 步驟1：記住初始資訊")
        session_c = self.generate_unique_session_id(prefix="skill_exp_c")

        self.send_and_log("請記住：我叫小剛，喜歡踢足球", session_id=session_c)

        self.smart_wait_for_sync(
            check_message="我叫什麼名字",
            keywords=["小剛"],
            timeout=30.0,
        )

        self.logger.info("[2/3] 步驟2：更新資訊")
        self.send_and_log("記住：我現在喜歡打籃球，不喜歡踢足球了", session_id=session_c)
        self.wait_for_sync()

        self.logger.info("[3/3] 步驟3：驗證更新後的資訊")
        response3 = self.send_and_log("我現在喜歡什麼運動？", session_id=session_c)

        self.assertAnyKeywordInResponse(response3, [["小剛", "籃球"]], case_sensitive=False)

        self.logger.info("測試組C執行完成")


class TestSkillMemoryLogVerification(BaseOpenClawCLITest):
    """
    技能呼叫記憶注入日誌驗證（P0）
    測試目標：驗證傳送資料後，記憶成功注入OpenViking
    測試場景：傳送簡單資料，然後給出手動檢查日誌的提示
    """

    def test_skill_log_group_a(self):
        """測試組A：簡單資料寫入測試"""
        self.logger.info("[1/2] 測試組A - 傳送個人資訊")
        session_a = self.generate_unique_session_id(prefix="skill_log_a")

        response = self.send_and_log("我叫測試員A，這是我的測試資料", session_id=session_a)

        self.smart_wait_for_sync(
            check_message="我是誰",
            keywords=["測試員A"],
            timeout=30.0,
        )

        self.logger.info("[2/2] 資料傳送完成")
        self.logger.info("提示：請手動檢查OpenClaw日誌，確認有記憶注入記錄")
        self.logger.info("提示：日誌檔案位於 /tmp/openclaw/openclaw-{今天日期}.log")
        self.logger.info("提示：搜尋關鍵詞 'memory-openviking'")

        self.assertAnyKeywordInResponse(response, [["測試員A", "測試資料"]], case_sensitive=False)

        self.logger.info("測試組A執行完成")

    def test_skill_log_group_b(self):
        """測試組B：簡單資料寫入測試2"""
        self.logger.info("[1/2] 測試組B - 傳送另一條個人資訊")
        session_b = self.generate_unique_session_id(prefix="skill_log_b")

        response = self.send_and_log("我是測試員B，我喜歡測試工作", session_id=session_b)

        self.smart_wait_for_sync(
            check_message="我是誰",
            keywords=["測試員B"],
            timeout=30.0,
        )

        self.logger.info("[2/2] 資料傳送完成")
        self.assertAnyKeywordInResponse(response, [["測試員B", "測試工作"]], case_sensitive=False)

        self.logger.info("測試組B執行完成")

    def test_skill_log_group_c(self):
        """測試組C：簡單資料寫入測試3"""
        self.logger.info("[1/2] 測試組C - 傳送第三條資訊")
        session_c = self.generate_unique_session_id(prefix="skill_log_c")

        response = self.send_and_log("我是測試員C，今天的日期是2026-03-24", session_id=session_c)

        self.smart_wait_for_sync(
            check_message="我是誰",
            keywords=["測試員C"],
            timeout=30.0,
        )

        self.logger.info("[2/2] 資料傳送完成")
        self.assertAnyKeywordInResponse(response, [["測試員C", "2026-03-24"]], case_sensitive=False)

        self.logger.info("測試組C執行完成")


class TestSkillMemoryWithRetry(BaseOpenClawCLITest):
    """
    技能記憶測試（帶重試機制）
    """

    def test_skill_with_retry(self):
        """測試場景：使用重試機制驗證記憶"""
        self.logger.info("[1/2] 使用重試機制寫入記憶")
        session = self.generate_unique_session_id(prefix="skill_retry")

        self.send_with_retry("我叫重試測試使用者，喜歡程式設計", session_id=session, max_retries=3)

        self.smart_wait_for_sync(
            check_message="我喜歡什麼",
            keywords=["程式設計"],
            timeout=30.0,
        )

        self.logger.info("[2/2] 驗證記憶讀取")
        response = self.send_with_retry("我喜歡什麼", session_id=session, max_retries=3)
        self.assertAnyKeywordInResponse(response, [["程式設計"]], case_sensitive=False)
