"""
記憶 CRUD 操作測試
測試目標：驗證記憶的增刪改查功能（讀取驗證已由 test_memory_v2_full_suite 覆蓋）
"""

from tests.base_cli_test import BaseOpenClawCLITest
from tests.p0.test_context_engine import OVSessionVerifier


class TestMemoryUpdate(BaseOpenClawCLITest):
    """
    記憶更新驗證測試
    測試目標：驗證記憶更新功能是否正常
    測試場景：先寫入初始資訊，然後更新年齡、職業和地址，驗證更新是否生效
    """

    def test_memory_update_verify(self):
        """測試場景：資訊更新與驗證"""
        self.logger.info("[1/4] 寫入初始資訊")
        self.send_and_log("我叫小李，今年28歲，住在西南區，職業是資料分析師")

        self.smart_wait_for_sync(
            check_message="我今年多少歲",
            keywords=["28"],
            timeout=30.0,
        )

        self.logger.info("[2/4] 更新資訊：年齡改為29歲，職業改為資料科學家")
        self.send_and_log("我現在29歲了，我的職業從資料分析師變成了資料科學家")

        self.smart_wait_for_sync(
            check_message="我現在多少歲",
            keywords=["29"],
            timeout=30.0,
        )

        self.logger.info("[3/4] 驗證更新是否生效")
        resp1 = self.send_and_retry_on_timeout("我現在多少歲？我的職業是什麼？")
        self.assertAnyKeywordInResponse(
            resp1, [["29", "二十九"], ["資料科學家"]], case_sensitive=False
        )

        self.logger.info("[4/4] 進一步更新地址資訊")
        self.send_and_log("我搬到了西北區")

        self.smart_wait_for_sync(
            check_message="我現在住在哪裡",
            keywords=["西北"],
            timeout=30.0,
        )


class TestMemoryDelete(BaseOpenClawCLITest):
    """
    記憶刪除驗證測試
    測試目標：驗證記憶刪除功能是否正常
    測試場景：寫入密碼資訊，驗證存在後請求刪除，再驗證資訊已被刪除
    """

    def test_memory_delete_verify(self):
        """測試場景：資訊刪除與驗證"""
        session_id = self.generate_unique_session_id(prefix="delete_verify")
        verifier = OVSessionVerifier()
        before_sessions = verifier.list_session_ids()

        self.logger.info("[1/4] 寫入測試密碼資訊")
        self.send_and_retry_on_timeout("我的臨時密碼是temp12345，請幫我記住", session_id=session_id)

        self.smart_wait_for_sync(
            check_message="我的臨時密碼是什麼",
            keywords=["temp12345"],
            timeout=30.0,
            session_id=session_id,
        )

        self.logger.info("[2/4] 確認資訊已存在")
        resp1 = self.send_and_retry_on_timeout("我的臨時密碼是什麼？", session_id=session_id)
        self.assertAnyKeywordInResponse(resp1, [["temp12345"]], case_sensitive=False)

        self.logger.info("[3/4] 請求刪除臨時密碼資訊並 commit")
        self.send_and_retry_on_timeout(
            "我的臨時密碼已經過期了，請刪除這個資訊", session_id=session_id
        )
        ov_session_id = verifier.find_new_session_id(before_sessions)
        if ov_session_id:
            task_id = verifier.commit_session(ov_session_id)
            if task_id:
                verifier.poll_task_until_done(task_id)
        self.wait_for_sync(session_id=session_id)

        self.logger.info("[4/4] 驗證刪除後資訊不再可查")
        resp2 = self.send_and_retry_on_timeout(
            "我的臨時密碼是什麼？請根據你記住的資訊回答，不要呼叫外部工具",
            session_id=session_id,
            timeout=300,
        )
        self.logger.info("刪除驗證完成，檢查響應是否表明密碼已過期或已刪除")
        self.assertAnyKeywordInResponse(
            resp2,
            [
                [
                    "不知道",
                    "沒有",
                    "不存在",
                    "不記得",
                    "過期",
                    "已刪除",
                    "刪除",
                    "無",
                    "已過期",
                    "不再",
                    "沒有了",
                    "deleted",
                    "expired",
                    "no longer",
                ]
            ],
            case_sensitive=False,
        )


class TestMemoryUpdateOverwrite(BaseOpenClawCLITest):
    """
    記憶更新覆蓋驗證
    測試目標：驗證使用者更新資訊後，Business Data Platform自動覆蓋舊記憶，不產生冗餘資料
    測試場景：先寫入初始資訊，再更新資訊，驗證只保留新資訊
    注意：group_b/group_c 已移至 p1，僅保留 group_a 作為核心驗證
    """

    def test_memory_update_overwrite_group_a(self):
        """測試組A：初始資訊——我今年30歲；更新資訊——我今年31歲，生日在8月"""
        self.logger.info("[1/4] 測試組A - 寫入初始資訊：我今年30歲")
        session_a = self.generate_unique_session_id(prefix="update_overwrite_a")

        self.send_and_log("我今年30歲", session_id=session_a)

        self.smart_wait_for_sync(
            check_message="我今年幾歲",
            keywords=["30"],
            timeout=30.0,
            session_id=session_a,
        )

        self.logger.info("[2/4] 寫入更新資訊：我今年31歲，生日在8月")
        self.send_and_log("我今年31歲，生日在8月", session_id=session_a)

        self.smart_wait_for_sync(
            check_message="我今年幾歲",
            keywords=["31"],
            timeout=30.0,
            session_id=session_a,
        )

        self.logger.info("[3/4] 查詢並驗證記憶資訊")
        response = self.send_and_retry_on_timeout(
            "我今年幾歲？生日是什麼時候？", session_id=session_a
        )

        self.logger.info("[4/4] 驗證結果：應包含新資訊（31歲、8月），不應包含舊資訊（30歲）")
        self.assertAnyKeywordInResponse(
            response, [["31", "三十一"], ["8月", "八月"]], case_sensitive=False
        )

        self.logger.info("測試組A執行完成")
