"""
長程對話相關測試
測試目標：驗證長程對話記憶功能
"""

from tests.base_cli_test import BaseOpenClawCLITest


class TestLongTermMemoryTarget(BaseOpenClawCLITest):
    """
    長程對話核心目標記憶驗證
    測試目標：驗證多輪對話後，核心資訊記憶不丟失
    測試場景：先記住核心資訊，插入多輪簡單對話，然後驗證核心資訊
    """

    def test_long_term_target_group_a(self):
        """測試組A：記住關鍵資訊，多輪對話後驗證"""
        self.logger.info("[1/3] 測試組A - 步驟1：記住關鍵資訊")
        message1 = "請記住：我的名字是張三，我的工號是1001，我的部門是技術部"
        session_a = self.generate_unique_session_id(prefix="long_term_a")

        self.send_and_log(message1, session_id=session_a)

        self.smart_wait_for_sync(
            check_message="我叫什麼名字",
            keywords=["張三"],
            timeout=30.0,
        )

        self.logger.info("[2/3] 步驟2：插入多輪簡單對話")
        simple_messages = [
            "1 + 1 等於幾？",
            "2 + 3 等於幾？",
            "5 + 7 等於幾？",
            "10 - 4 等於幾？",
            "8 + 9 等於幾？",
        ]

        for i, msg in enumerate(simple_messages, 1):
            self.logger.info(f"  簡單對話 {i}/{len(simple_messages)}: {msg}")
            self.send_and_log(msg, session_id=session_a)
            self.wait_for_sync(2)

        self.logger.info("[3/3] 步驟3：提問並驗證核心資訊")
        response = self.send_and_log("我叫什麼名字？工號是多少？部門是什麼？", session_id=session_a)

        self.assertAnyKeywordInResponse(
            response, [["張三", "1001", "技術部"]], case_sensitive=False
        )

        self.logger.info("測試組A執行完成")

    def test_long_term_target_group_b(self):
        """測試組B：記住關鍵資訊，多輪對話後驗證"""
        self.logger.info("[1/3] 測試組B - 步驟1：記住關鍵資訊")
        message1 = "請記住：我的名字是李四，我的工號是1002，我的部門是產品部"
        session_b = self.generate_unique_session_id(prefix="long_term_b")

        self.send_and_log(message1, session_id=session_b)

        self.smart_wait_for_sync(
            check_message="我叫什麼名字",
            keywords=["李四"],
            timeout=30.0,
        )

        self.logger.info("[2/3] 步驟2：插入多輪簡單對話")
        simple_messages = [
            "請記住：蘋果是紅色的",
            "請記住：香蕉是黃色的",
            "請記住：葡萄是紫色的",
            "請記住：橙子是橙色的",
            "請記住：西瓜是綠色的",
        ]

        for i, msg in enumerate(simple_messages, 1):
            self.logger.info(f"  簡單對話 {i}/{len(simple_messages)}: {msg}")
            self.send_and_log(msg, session_id=session_b)
            self.wait_for_sync(2)

        self.logger.info("[3/3] 步驟3：提問並驗證核心資訊")
        response = self.send_and_log("我叫什麼名字？工號是多少？部門是什麼？", session_id=session_b)

        self.assertAnyKeywordInResponse(
            response, [["李四", "1002", "產品部"]], case_sensitive=False
        )

        self.logger.info("測試組B執行完成")

    def test_long_term_target_group_c(self):
        """測試組C：記住關鍵資訊，多輪對話後驗證"""
        self.logger.info("[1/3] 測試組C - 步驟1：記住關鍵資訊")
        message1 = "請記住：我的名字是王五，我的工號是1003，我的部門是設計部"
        session_c = self.generate_unique_session_id(prefix="long_term_c")

        self.send_and_log(message1, session_id=session_c)

        self.smart_wait_for_sync(
            check_message="我叫什麼名字",
            keywords=["王五"],
            timeout=30.0,
        )

        self.logger.info("[2/3] 步驟2：插入多輪簡單對話")
        simple_messages = [
            "請重複：今天是2026年3月24日",
            "請重複：今天是星期三",
            "請重複：今天天氣晴朗",
            "請重複：現在是測試時間",
            "請重複：正在進行記憶測試",
        ]

        for i, msg in enumerate(simple_messages, 1):
            self.logger.info(f"  簡單對話 {i}/{len(simple_messages)}: {msg}")
            self.send_and_log(msg, session_id=session_c)
            self.wait_for_sync(2)

        self.logger.info("[3/3] 步驟3：提問並驗證核心資訊")
        response = self.send_and_log("我叫什麼名字？工號是多少？部門是什麼？", session_id=session_c)

        self.assertAnyKeywordInResponse(
            response, [["王五", "1003", "設計部"]], case_sensitive=False
        )

        self.logger.info("測試組C執行完成")


class TestLongTermSummaryGeneration(BaseOpenClawCLITest):
    """
    長程對話總結生成驗證
    測試目標：驗證多輪資訊後，能記住並整合所有資訊
    測試場景：先記住多條資訊，然後要求複述
    """

    def test_summary_generation_group_a(self):
        """測試組A：記住多條個人資訊，然後複述"""
        self.logger.info("[1/4] 測試組A - 步驟1：記住第一條資訊")
        session_a = self.generate_unique_session_id(prefix="summary_a")

        self.send_and_log("請記住：我的名字叫測試A，今年28歲", session_id=session_a)
        self.wait_for_sync()

        self.logger.info("[2/4] 步驟2：記住第二條資訊")
        self.send_and_log("請記住：我住在北京，職業是工程師", session_id=session_a)
        self.wait_for_sync()

        self.logger.info("[3/4] 步驟3：記住第三條資訊")
        self.send_and_log("請記住：我喜歡程式設計，喜歡閱讀", session_id=session_a)
        self.wait_for_sync()

        self.logger.info("[4/4] 步驟4：要求複述所有資訊")
        response = self.send_and_log("請複述一下剛才記住的所有關於我的資訊", session_id=session_a)

        self.assertAnyKeywordInResponse(
            response, [["測試A", "28", "北京", "工程師", "程式設計", "閱讀"]], case_sensitive=False
        )

        self.logger.info("測試組A執行完成")

    def test_summary_generation_group_b(self):
        """測試組B：記住多條個人資訊，然後複述"""
        self.logger.info("[1/4] 測試組B - 步驟1：記住第一條資訊")
        session_b = self.generate_unique_session_id(prefix="summary_b")

        self.send_and_log("請記住：我的名字叫測試B，今年30歲", session_id=session_b)
        self.wait_for_sync()

        self.logger.info("[2/4] 步驟2：記住第二條資訊")
        self.send_and_log("請記住：我住在上海，職業是設計師", session_id=session_b)
        self.wait_for_sync()

        self.logger.info("[3/4] 步驟3：記住第三條資訊")
        self.send_and_log("請記住：我喜歡畫畫，喜歡旅行", session_id=session_b)
        self.wait_for_sync()

        self.logger.info("[4/4] 步驟4：要求複述所有資訊")
        response = self.send_and_log("請複述一下剛才記住的所有關於我的資訊", session_id=session_b)

        self.assertAnyKeywordInResponse(
            response, [["測試B", "30", "上海", "設計師", "畫畫", "旅行"]], case_sensitive=False
        )

        self.logger.info("測試組B執行完成")

    def test_summary_generation_group_c(self):
        """測試組C：記住多條個人資訊，然後複述"""
        self.logger.info("[1/4] 測試組C - 步驟1：記住第一條資訊")
        session_c = self.generate_unique_session_id(prefix="summary_c")

        self.send_and_log("請記住：我的名字叫測試C，今年32歲", session_id=session_c)
        self.wait_for_sync()

        self.logger.info("[2/4] 步驟2：記住第二條資訊")
        self.send_and_log("請記住：我住在廣州，職業是產品經理", session_id=session_c)
        self.wait_for_sync()

        self.logger.info("[3/4] 步驟3：記住第三條資訊")
        self.send_and_log("請記住：我喜歡音樂，喜歡運動", session_id=session_c)
        self.wait_for_sync()

        self.logger.info("[4/4] 步驟4：要求複述所有資訊")
        response = self.send_and_log("請複述一下剛才記住的所有關於我的資訊", session_id=session_c)

        self.assertAnyKeywordInResponse(
            response, [["測試C", "32", "廣州", "產品經理", "音樂", "運動"]], case_sensitive=False
        )

        self.logger.info("測試組C執行完成")
