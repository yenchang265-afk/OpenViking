"""
示例測試 - 展示增強版測試基類的用法
演示：Session ID 管理、智慧等待、重試機制、測試資料管理
"""

from tests.base_cli_test import BaseOpenClawCLITest
from utils.test_utils import TestData


class TestEnhancedFeatures(BaseOpenClawCLITest):
    """
    增強功能演示測試
    展示如何使用 Session ID 管理、智慧等待、重試機制、測試資料管理
    """

    def test_auto_session_id(self):
        """
        演示：自動 Session ID 管理
        - 每個測試方法自動獲得唯一的 session_id
        - 通過 self.current_session_id 訪問
        """
        self.logger.info(f"當前測試自動生成的 Session ID: {self.current_session_id}")

        message = "我叫測試使用者，今年25歲"
        response = self.send_and_log(message)

        self.wait_for_sync()

        response2 = self.send_and_log("我是誰")
        self.assertAnyKeywordInResponse(response2, [["測試使用者", "25歲"]])

    def test_custom_session_id(self):
        """
        演示：自定義 Session ID
        - 使用 generate_unique_session_id() 生成自定義 session_id
        - 可以指定字首
        """
        custom_session = self.generate_unique_session_id(prefix="custom_test")
        self.logger.info(f"自定義 Session ID: {custom_session}")

        message = "我喜歡吃蘋果"
        response = self.send_and_log(message, session_id=custom_session)

        self.wait_for_sync()

        response2 = self.send_and_log("我喜歡吃什麼", session_id=custom_session)
        self.assertAnyKeywordInResponse(response2, [["蘋果"]])

    def test_smart_wait(self):
        """
        演示：智能等待
        - 使用 smart_wait_for_sync() 替代固定等待
        - 輪詢檢查記憶是否同步完成
        """
        message = "我的愛好是打籃球和游泳"
        self.send_and_log(message)

        success = self.smart_wait_for_sync(
            check_message="我的愛好是什麼",
            keywords=["籃球", "游泳"],
            timeout=30.0,
            poll_interval=2.0,
        )

        self.assertTrue(success, "智慧等待超時，記憶未同步")

    def test_retry_on_failure(self):
        """
        演示：重試機制
        - 使用 send_with_retry() 在失敗時自動重試
        - 使用 send_and_log(retry_on_failure=True) 啟用重試
        """
        message = "我在北京工作"

        response = self.send_with_retry(
            message,
            max_retries=3,
        )

        self.wait_for_sync()

        response2 = self.send_and_log("我在哪裡工作", retry_on_failure=True)
        self.assertAnyKeywordInResponse(response2, [["北京"]])

    def test_data_driven_with_default_data(self):
        """
        演示：使用預設測試資料
        - 使用 get_test_data() 獲取預定義的測試資料
        - 使用 run_with_test_data() 快速執行測試
        """
        _, query_response = self.run_with_test_data(
            data_name="user_xiaoming",
            query_message="我是誰，今年多大",
        )

        self.assertIsNotNone(query_response)

    def test_data_driven_with_custom_data(self):
        """
        演示：使用自定義測試資料
        - 建立 TestData 物件
        - 註冊到 data_manager
        """
        custom_data = TestData(
            name="custom_user",
            description="自定義測試使用者",
            input_data={
                "message": "我叫自定義使用者，職業是資料分析師",
            },
            expected_keywords=[
                ["自定義使用者"],
                ["資料分析師"],
            ],
            tags=["custom", "user"],
        )

        self.data_manager.register_data(custom_data)

        _, query_response = self.run_with_test_data(
            data_name="custom_user",
            query_message="我的職業是什麼",
        )

        self.assertIsNotNone(query_response)

    def test_combined_features(self):
        """
        演示：組合使用多個增強功能
        - 自動 Session ID
        - 智能等待
        - 重試機制
        - 測試資料
        """
        data = self.get_test_data("fruit_cherry")
        self.assertIsNotNone(data, "測試資料不存在")

        message = data.input_data.get("message")
        self.send_and_log(message, retry_on_failure=True)

        success = self.smart_wait_for_sync(
            check_message="我喜歡吃什麼水果",
            keywords=data.expected_keywords[0],
            timeout=30.0,
        )

        self.assertTrue(success, "智慧等待超時")


class TestDataDrivenTests(BaseOpenClawCLITest):
    """
    資料驅動測試示例
    使用預定義的測試資料執行多個測試用例
    """

    def test_fruit_cherry(self):
        """測試水果偏好 - 櫻桃"""
        _, response = self.run_with_test_data(
            data_name="fruit_cherry",
            query_message="我喜歡吃什麼水果，平時愛喝什麼",
        )
        self.assertIsNotNone(response)

    def test_fruit_mango(self):
        """測試水果偏好 - 芒果"""
        _, response = self.run_with_test_data(
            data_name="fruit_mango",
            query_message="我喜歡吃什麼水果，平時愛喝什麼",
        )
        self.assertIsNotNone(response)

    def test_fruit_strawberry(self):
        """測試水果偏好 - 草莓"""
        _, response = self.run_with_test_data(
            data_name="fruit_strawberry",
            query_message="我喜歡吃什麼水果，平時愛喝什麼",
        )
        self.assertIsNotNone(response)
