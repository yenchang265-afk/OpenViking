"""
進階場景測試
測試目標：驗證複雜記憶場景
"""

from tests.base_cli_test import BaseOpenClawCLITest
from utils.test_utils import TestData


class TestComplexScenarioMultiUsers(BaseOpenClawCLITest):
    """
    複雜場景1：多使用者切換
    測試目標：驗證多使用者記憶切換
    """

    def test_multi_users_switch(self):
        """多使用者記憶切換測試"""
        users = [
            {"name": "使用者A", "age": 22, "region": "東北區", "job": "學生"},
            {"name": "使用者B", "age": 35, "region": "西北區", "job": "醫生"},
            {"name": "使用者C", "age": 45, "region": "中南區", "job": "教師"},
        ]

        for user in users:
            session_id = self.generate_unique_session_id(prefix=f"user_{user['name']}")
            self.logger.info(f"寫入使用者資訊: {user} (session: {session_id})")
            msg = f"我叫{user['name']}，今年{user['age']}歲，住在{user['region']}，職業是{user['job']}"
            self.send_and_log(msg, session_id=session_id)

            self.smart_wait_for_sync(
                check_message="請介紹一下我自己",
                keywords=[user["name"], str(user["age"]), user["region"], user["job"]],
                timeout=30.0,
            )


class TestComplexScenarioIncrementalInfo(BaseOpenClawCLITest):
    """
    複雜場景2：增量資訊新增
    測試目標：驗證增量資訊新增
    """

    def test_incremental_info(self):
        """增量資訊新增測試"""
        steps = [
            "我叫增量測試使用者",
            "我今年33歲",
            "我住在華中區",
            "我的職業是架構師",
            "我喜歡程式設計和閱讀",
            "我擅長Python和Go語言",
            "我有10年工作經驗",
        ]

        self.logger.info("分多次新增使用者資訊...")
        for i, step in enumerate(steps, 1):
            self.logger.info(f"[{i}/{len(steps)}] 添加: {step}")
            self.send_and_log(step)
            self.wait_for_sync(3)

        self.logger.info("\n[最終驗證] 彙總所有資訊")
        resp = self.send_and_log(
            "請詳細介紹一下我，包括姓名、年齡、地區、職業、興趣愛好、技能和工作經驗"
        )

        self.assertAnyKeywordInResponse(
            resp,
            [
                ["增量測試使用者"],
                ["33", "三十三"],
                ["華中"],
                ["架構師"],
                ["程式設計", "閱讀"],
                ["Python", "Go"],
                ["10", "十年"],
            ],
            case_sensitive=False,
        )


class TestComplexScenarioSpecialCharacters(BaseOpenClawCLITest):
    """
    複雜場景3：特殊字元和邊界情況
    測試目標：驗證特殊字元處理
    """

    def test_special_characters(self):
        """特殊字元和邊界情況測試"""
        special_messages = [
            "我叫測試-特殊字元@#$%^&*()",
            "我的備註是：測試'引號\"和\\反斜槓",
            "我的愛好是：🎵音樂、🎨繪畫、📚閱讀（emoji測試）",
            "我的地址是：測試換行\n第二行\n第三行",
        ]

        for msg in special_messages:
            self.logger.info(f"測試資訊: {repr(msg)}")
            self.send_and_log(msg)
            self.wait_for_sync()

        self.logger.info("\n[驗證特殊字元記憶]")
        resp = self.send_and_log("請告訴我關於我的所有資訊，包括名字、備註、愛好和地址")

        self.assertAnyKeywordInResponse(
            resp, [["測試-特殊字元"], ["音樂", "繪畫", "閱讀"], ["測試換行"]], case_sensitive=False
        )


class TestComplexScenarioDataDriven(BaseOpenClawCLITest):
    """
    複雜場景4：資料驅動測試
    測試目標：使用測試資料管理執行多個測試
    """

    def test_data_driven_users(self):
        """資料驅動使用者測試"""
        test_data_names = ["user_xiaoming", "user_xiaohong"]

        for data_name in test_data_names:
            self.logger.info(f"測試資料: {data_name}")
            session_id = self.generate_unique_session_id(prefix=data_name)
            data = self.get_test_data(data_name)

            if data:
                message = data.input_data.get("message", "")
                self.send_and_log(message, session_id=session_id)

                self.smart_wait_for_sync(
                    check_message="我是誰",
                    keywords=data.expected_keywords[0] if data.expected_keywords else [],
                    timeout=30.0,
                )
