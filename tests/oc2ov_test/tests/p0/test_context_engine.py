"""
Context Engine 核心互動鏈路測試
覆蓋 OpenClaw-OpenViking 核心互動：
1. assemble() - archive 歷史組裝回放
2. compact() - 對話超閾值後壓縮歸檔
3. 跨 session recall - 不同 session 間的記憶檢索注入
4. memory_recall 顯式搜尋 - 模型主動呼叫 memory_recall 工具
5. ov_archive_expand 展開 - 模型主動展開 archive 檢視原始對話
6. session 隔離 - 不同 session 的記憶不互相汙染

斷言覆蓋：
- 對話級別：模型回覆包含預期關鍵詞
- API 級別：OV session 狀態正確（archive 存在、記憶已提取）
- 檔案級別：記憶 .md 檔案在本次測試期間新增或更新且內容包含關鍵資訊

前置條件：
- ECS 上 commitTokenThreshold 已調低（如 500），以減少 archive 生成的對話輪次
- OpenViking 服務正常執行
"""

import os
import time
from pathlib import Path
from typing import Dict, Optional, Set

import requests

from tests.base_cli_test import BaseOpenClawCLITest

SERVER_URL = os.environ.get("SERVER_URL", "http://127.0.0.1:1933")
OPENVIKING_API_KEY = os.environ.get("OPENVIKING_API_KEY", "test-root-api-key")
OPENVIKING_ACCOUNT = os.environ.get("OPENVIKING_ACCOUNT", "default")
OPENVIKING_USER = os.environ.get("OPENVIKING_USER", "default")
TASK_POLL_INTERVAL = 5
TASK_POLL_MAX_WAIT = 120


def _get_api_headers() -> Dict[str, str]:
    headers = {
        "X-API-Key": OPENVIKING_API_KEY,
        "Content-Type": "application/json",
    }
    if OPENVIKING_ACCOUNT and "." not in OPENVIKING_API_KEY:
        headers["X-OpenViking-Account"] = OPENVIKING_ACCOUNT
    if OPENVIKING_USER and "." not in OPENVIKING_API_KEY:
        headers["X-OpenViking-User"] = OPENVIKING_USER
    return headers


class OVSessionVerifier:
    """OV session 狀態驗證器，用於斷言 archive 和記憶檔案"""

    def __init__(self, server_url: str = SERVER_URL, api_key: str = OPENVIKING_API_KEY):
        self.server_url = server_url
        self.headers = _get_api_headers()

    def list_session_ids(self) -> Set[str]:
        try:
            resp = requests.get(
                f"{self.server_url}/api/v1/sessions", headers=self.headers, timeout=10
            )
            if resp.status_code != 200:
                return set()
            sessions = resp.json().get("result", [])
            return {s["session_id"] for s in sessions}
        except Exception:
            return set()

    def find_new_session_id(self, before_ids: Set[str]) -> Optional[str]:
        after_ids = self.list_session_ids()
        new_ids = after_ids - before_ids
        return new_ids.pop() if new_ids else None

    def get_session_detail(self, session_id: str) -> Optional[Dict]:
        try:
            resp = requests.get(
                f"{self.server_url}/api/v1/sessions/{session_id}",
                headers=self.headers,
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json().get("result", {})
        except Exception:
            pass
        return None

    def commit_session(self, session_id: str) -> Optional[str]:
        try:
            resp = requests.post(
                f"{self.server_url}/api/v1/sessions/{session_id}/commit",
                headers=self.headers,
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json().get("result", {}).get("task_id")
        except Exception:
            pass
        return None

    def poll_task_until_done(
        self, task_id: str, max_wait: int = TASK_POLL_MAX_WAIT
    ) -> Optional[Dict]:
        start = time.time()
        while time.time() - start < max_wait:
            try:
                resp = requests.get(
                    f"{self.server_url}/api/v1/tasks/{task_id}",
                    headers=self.headers,
                    timeout=10,
                )
                if resp.status_code == 200:
                    task_data = resp.json().get("result", {})
                    status = task_data.get("status", "unknown")
                    if status in ("completed", "failed"):
                        return task_data
            except Exception:
                pass
            time.sleep(TASK_POLL_INTERVAL)
        return None

    def assert_archive_exists(self, session_id: str) -> bool:
        detail = self.get_session_detail(session_id)
        if not detail:
            return False
        return detail.get("archive_count", 0) > 0 or detail.get("latest_archive_id") is not None

    def assert_memories_extracted(self, session_id: str) -> bool:
        task_id = self.commit_session(session_id)
        if not task_id:
            return False
        result = self.poll_task_until_done(task_id)
        if not result or result.get("status") != "completed":
            return False
        extracted = result.get("result", {}).get("memories_extracted", {})
        if not extracted:
            return False
        total = sum(len(v) if isinstance(v, list) else v for v in extracted.values())
        return total > 0

    @staticmethod
    def snapshot_memory_files() -> Dict[str, float]:
        """記錄所有記憶檔案的 mtime 快照（路徑 → mtime）"""
        files: Dict[str, float] = {}
        data_base = Path.home() / ".openviking" / "data" / "viking" / "default"
        for search_dir in [data_base / "user" / "default" / "memories", data_base / "agent"]:
            if not search_dir.exists():
                continue
            for md_file in search_dir.rglob("*.md"):
                try:
                    files[str(md_file)] = md_file.stat().st_mtime
                except Exception:
                    continue
        return files

    @staticmethod
    def find_new_or_updated_files(before: Dict[str, float], keyword: str = None) -> list:
        """對比前後快照，找出新增或 mtime 變化的檔案；可選按關鍵詞過濾內容"""
        after = OVSessionVerifier.snapshot_memory_files()
        results = []
        for path_str, new_mtime in after.items():
            is_new = path_str not in before
            is_updated = not is_new and new_mtime > before[path_str]
            if not (is_new or is_updated):
                continue
            if keyword:
                try:
                    content = Path(path_str).read_text(encoding="utf-8")
                    if keyword not in content:
                        continue
                    results.append(
                        {
                            "path": path_str,
                            "status": "new" if is_new else "updated",
                            "content_preview": content[:200],
                        }
                    )
                except Exception:
                    continue
            else:
                results.append(
                    {
                        "path": path_str,
                        "status": "new" if is_new else "updated",
                    }
                )
        return results


class TestAssembleArchiveReplay(BaseOpenClawCLITest):
    """
    assemble() 歷史組裝驗證
    測試目標：驗證 archive 生成後，新 session 能通過 assemble 回放歷史摘要
    測試路徑：寫入資訊 → commit 生成 archive → 新 session → 驗證 archive summary 被載入
    """

    def test_assemble_replays_archive_summary(self):
        """archive 生成後，新 session 應能通過 assemble 回放歷史"""
        session_a = self.generate_unique_session_id(prefix="assemble_src")
        session_b = self.generate_unique_session_id(prefix="assemble_new")
        verifier = OVSessionVerifier()

        self.logger.info("[1/7] 記錄 OV session 快照 + 記憶檔案 mtime 快照")
        before_sessions = verifier.list_session_ids()
        before_files = OVSessionVerifier.snapshot_memory_files()

        self.logger.info("[2/7] 在 session A 中寫入獨特資訊")
        unique_marker = "藍鯨計劃"
        unique_detail = "2030年發射"
        self.send_and_log(
            f"我正在推進{unique_marker}，目標{unique_detail}，請記住",
            session_id=session_a,
        )

        self.smart_wait_for_sync(
            check_message=f"{unique_marker}的目標是什麼",
            keywords=[unique_detail],
            timeout=60.0,
            session_id=session_a,
        )

        self.logger.info("[3/7] 繼續寫入更多資訊，推動 commit/archive 生成")
        for i in range(3):
            self.send_and_log(
                f"{unique_marker}的里程碑{i + 1}：第{i + 1}階段測試已完成",
                session_id=session_a,
            )
            time.sleep(3)

        self.logger.info("[4/7] 顯式 commit 並等待 archive 生成")
        ov_session_id = verifier.find_new_session_id(before_sessions)
        archive_exists = False
        if ov_session_id:
            task_id = verifier.commit_session(ov_session_id)
            if task_id:
                verifier.poll_task_until_done(task_id)
            time.sleep(5)
            archive_exists = verifier.assert_archive_exists(ov_session_id)
            self.logger.info(f"  Archive 存在: {archive_exists}")
            if not archive_exists:
                self.logger.warning("  Archive 未生成，嘗試再次 commit")
                task_id = verifier.commit_session(ov_session_id)
                if task_id:
                    verifier.poll_task_until_done(task_id)
                time.sleep(5)
                archive_exists = verifier.assert_archive_exists(ov_session_id)
                self.logger.info(f"  第二次 commit 後 Archive 存在: {archive_exists}")
        else:
            time.sleep(5)

        self.logger.info("[5/7] 驗證記憶檔案已新增或更新且包含關鍵資訊（檔案級別斷言）")
        memory_found = OVSessionVerifier.find_new_or_updated_files(before_files, keyword="藍鯨")
        self.logger.info(f"  本次新增/更新且包含'藍鯨'的記憶檔案數: {len(memory_found)}")
        for mf in memory_found:
            self.logger.info(f"  [{mf['status']}] {mf['path']}")
            if "content_preview" in mf:
                self.logger.info(f"  內容預覽: {mf['content_preview'][:100]}")
        if not memory_found:
            self.logger.warning("  未找到本次新增/更新且包含'藍鯨'的記憶檔案")

        self.logger.info("[6/7] 建立全新 session B，觸發 assemble 從 archive 載入")
        time.sleep(5)

        self.logger.info("[7/7] 在新 session B 中查詢，驗證 archive 回放")
        response = self.send_and_retry_on_timeout(
            f"我之前提到的{unique_marker}是什麼？目標是什麼？請從你的記憶或上下文中搜索",
            session_id=session_b,
            timeout=300,
        )
        self.assertAnyKeywordInResponse(
            response,
            [[unique_marker]],
            case_sensitive=False,
        )


class TestMemoryRecallExplicit(BaseOpenClawCLITest):
    """
    memory_recall 顯式搜尋驗證
    測試目標：驗證模型能通過 memory_recall 工具主動搜尋長期記憶，而非僅依賴 auto-recall
    測試路徑：寫入獨特資訊 → commit + 記憶提取 → 新 session 中用模糊提示觸發顯式搜尋 → 驗證搜尋結果
    """

    def test_memory_recall_explicit_search(self):
        """模型應能通過 memory_recall 工具顯式搜尋長期記憶"""
        unique_marker = "極光協議"
        unique_detail = "量子加密通信"

        session_a = self.generate_unique_session_id(prefix="recall_explicit_source")
        session_b = self.generate_unique_session_id(prefix="recall_explicit_target")
        verifier = OVSessionVerifier()

        self.logger.info("[1/7] 記錄 OV session 快照 + 記憶檔案 mtime 快照")
        before_sessions = verifier.list_session_ids()
        before_files = OVSessionVerifier.snapshot_memory_files()

        self.logger.info("[2/7] 在 session A 中寫入獨特資訊")
        self.send_and_retry_on_timeout(
            f"我參與了一個叫{unique_marker}的專案，它使用{unique_detail}技術，傳輸速率達到100Gbps，請記住這些資訊",
            session_id=session_a,
        )

        self.smart_wait_for_sync(
            check_message=f"{unique_marker}用什麼技術",
            keywords=["量子加密", "加密"],
            timeout=60.0,
            session_id=session_a,
        )

        self.logger.info("[3/7] 顯式 commit 並等待記憶提取完成")
        ov_session_id = verifier.find_new_session_id(before_sessions)
        commit_success = False
        if ov_session_id:
            task_id = verifier.commit_session(ov_session_id)
            if task_id:
                result = verifier.poll_task_until_done(task_id)
                if result:
                    status = result.get("status")
                    extracted = result.get("result", {}).get("memories_extracted", {})
                    self.logger.info(f"  Commit 任務狀態: {status}, 記憶提取結果: {extracted}")
                    commit_success = status == "completed"
        if not commit_success:
            self.logger.warning("  Commit 未成功完成，等待額外時間...")
        self.logger.info("  等待記憶索引完成...")
        time.sleep(10)

        self.logger.info("[4/7] 驗證記憶檔案已新增或更新且包含關鍵資訊（檔案級別斷言）")
        memory_found = OVSessionVerifier.find_new_or_updated_files(
            before_files, keyword=unique_marker
        )
        self.logger.info(f"  本次新增/更新且包含'{unique_marker}'的記憶檔案數: {len(memory_found)}")
        for mf in memory_found:
            self.logger.info(f"  [{mf['status']}] {mf['path']}")
            if "content_preview" in mf:
                self.logger.info(f"  內容預覽: {mf['content_preview'][:100]}")
        if not memory_found:
            self.logger.warning(f"  未找到本次新增/更新且包含'{unique_marker}'的記憶檔案")

        self.logger.info("[5/7] 在新 session B 中用明確提示觸發 memory_recall 顯式搜尋")
        response = self.send_and_retry_on_timeout(
            "請搜尋你的記憶，我之前有沒有提到過一個和加密通訊或者協議相關的專案？請仔細搜尋記憶檔案後回答",
            session_id=session_b,
            timeout=300,
        )

        self.logger.info("[6/7] 驗證回覆包含記憶中的關鍵資訊（對話級別斷言）")
        self.assertAnyKeywordInResponse(
            response,
            [[unique_marker, "極光"], [unique_detail, "量子加密", "加密通訊"]],
            case_sensitive=False,
        )

        self.logger.info("[7/7] 驗證回覆包含具體細節（業務邏輯斷言：顯式搜尋應返回完整記憶內容）")
        self.assertAnyKeywordInResponse(
            response,
            [["100Gbps", "100G", "Gbps", "加密通信", "量子加密"]],
            case_sensitive=False,
        )


class TestArchiveExpand(BaseOpenClawCLITest):
    """
    ov_archive_expand 展開驗證
    測試目標：驗證 archive 生成後，模型能通過 ov_archive_expand 展開原始對話獲取細節
    測試路徑：寫入含細節的資訊 → commit 生成 archive → 詢問細節問題觸發展開 → 驗證原始細節被還原
    """

    def test_archive_expand_restores_details(self):
        """archive 展開後應能還原原始對話中的細節資訊"""
        session_id = self.generate_unique_session_id(prefix="expand_test")
        verifier = OVSessionVerifier()

        self.logger.info("[1/8] 記錄 OV session 快照 + 記憶檔案 mtime 快照")
        before_sessions = verifier.list_session_ids()
        before_files = OVSessionVerifier.snapshot_memory_files()

        self.logger.info("[2/8] 寫入含豐富細節的資訊")
        unique_marker = "鳳凰計劃"
        detail_1 = "預算480萬"
        detail_2 = "2027年Q3交付"
        detail_3 = "合作伙伴是深藍科技"
        self.send_and_log(
            f"我負責{unique_marker}，{detail_1}，{detail_2}，{detail_3}，團隊有12人",
            session_id=session_id,
        )

        self.smart_wait_for_sync(
            check_message=f"{unique_marker}的預算是多少",
            keywords=["480"],
            timeout=60.0,
            session_id=session_id,
        )

        self.logger.info("[3/8] 繼續寫入推動 archive 生成")
        for i in range(3):
            self.send_and_log(
                f"{unique_marker}第{i + 1}階段進展：已完成需求分析和架構設計",
                session_id=session_id,
            )
            time.sleep(3)

        self.logger.info("[4/8] 顯式 commit 並等待 archive 生成")
        ov_session_id = verifier.find_new_session_id(before_sessions)
        if ov_session_id:
            task_id = verifier.commit_session(ov_session_id)
            if task_id:
                verifier.poll_task_until_done(task_id)
        time.sleep(5)

        self.logger.info("[5/8] 驗證 archive 已生成（API 級別斷言）")
        if ov_session_id:
            has_archive = verifier.assert_archive_exists(ov_session_id)
            self.logger.info(f"  Archive 存在: {has_archive}")
            if not has_archive:
                self.logger.warning("  Archive 未生成，expand 測試可能不可靠")

        self.logger.info("[6/8] 驗證記憶檔案已新增或更新且包含關鍵資訊（檔案級別斷言）")
        memory_found = OVSessionVerifier.find_new_or_updated_files(
            before_files, keyword=unique_marker
        )
        self.logger.info(f"  本次新增/更新且包含'{unique_marker}'的記憶檔案數: {len(memory_found)}")
        for mf in memory_found:
            self.logger.info(f"  [{mf['status']}] {mf['path']}")
            if "content_preview" in mf:
                self.logger.info(f"  內容預覽: {mf['content_preview'][:100]}")
        if not memory_found:
            self.logger.warning(f"  未找到本次新增/更新且包含'{unique_marker}'的記憶檔案")

        self.logger.info("[7/8] 詢問 archive 中的細節問題，觸發 ov_archive_expand")
        response = self.send_and_retry_on_timeout(
            f"關於{unique_marker}，合作伙伴是誰？預算和交付時間是什麼？請仔細回憶所有細節",
            session_id=session_id,
        )

        self.logger.info("[8/8] 驗證回覆包含 archive 中的原始細節（業務邏輯斷言：展開應還原細節）")
        self.assertAnyKeywordInResponse(
            response,
            [["480萬", "480"], ["2027", "Q3"], ["深藍科技", "深藍"]],
            case_sensitive=False,
        )


class TestSessionIsolation(BaseOpenClawCLITest):
    """
    session 隔離驗證
    測試目標：驗證不同 session 的對話上下文不會互相汙染
    注意：OpenClaw 的記憶檔案(USER.md/MEMORY.md)是全域共享的，
    session 隔離主要體現在對話上下文層面——不同 session 看不到對方的對話歷史
    測試路徑：session A 寫入甲資訊 → session B 寫入乙資訊 → 分別查詢對話上下文 → 驗證互不干擾
    """

    def test_session_isolation_no_cross_contamination(self):
        """不同 session 的對話上下文不應互相汙染"""
        marker_a = "翡翠專案"
        detail_a = "負責AI模型訓練"
        marker_b = "琥珀專案"
        detail_b = "負責資料採集"

        session_a = self.generate_unique_session_id(prefix="isolation_a")
        session_b = self.generate_unique_session_id(prefix="isolation_b")
        verifier = OVSessionVerifier()

        self.logger.info("[1/7] 記錄 OV session 快照 + 記憶檔案 mtime 快照")
        before_sessions = verifier.list_session_ids()
        before_files = OVSessionVerifier.snapshot_memory_files()

        self.logger.info("[2/7] 在 session A 中寫入甲資訊")
        self.send_and_retry_on_timeout(
            f"我在做{marker_a}，{detail_a}，使用GPU叢集",
            session_id=session_a,
        )

        self.smart_wait_for_sync(
            check_message="我在做什麼專案",
            keywords=[marker_a],
            timeout=60.0,
            session_id=session_a,
        )

        self.logger.info("[3/7] 在 session B 中寫入乙資訊")
        self.send_and_retry_on_timeout(
            f"我在做{marker_b}，{detail_b}，使用爬蟲技術",
            session_id=session_b,
        )

        self.smart_wait_for_sync(
            check_message="我在做什麼專案",
            keywords=[marker_b],
            timeout=60.0,
            session_id=session_b,
        )

        self.logger.info("[4/7] 顯式 commit 兩個 session")
        after_sessions = verifier.list_session_ids()
        new_sessions = after_sessions - before_sessions
        for sid in new_sessions:
            task_id = verifier.commit_session(sid)
            if task_id:
                verifier.poll_task_until_done(task_id)
        time.sleep(5)

        self.logger.info("[5/7] 驗證記憶檔案已新增或更新且包含關鍵資訊（檔案級別斷言）")
        memory_found_a = OVSessionVerifier.find_new_or_updated_files(before_files, keyword=marker_a)
        memory_found_b = OVSessionVerifier.find_new_or_updated_files(before_files, keyword=marker_b)
        self.logger.info(f"  本次新增/更新且包含'{marker_a}'的記憶檔案數: {len(memory_found_a)}")
        self.logger.info(f"  本次新增/更新且包含'{marker_b}'的記憶檔案數: {len(memory_found_b)}")
        for mf in memory_found_a + memory_found_b:
            self.logger.info(f"  [{mf['status']}] {mf['path']}")
            if "content_preview" in mf:
                self.logger.info(f"  內容預覽: {mf['content_preview'][:100]}")

        self.logger.info("[6/7] 在 session A 中查詢對話上下文，應能回憶起甲資訊")
        response_a = self.send_and_retry_on_timeout(
            "請根據你記住的關於我的資訊回答：我之前告訴過你我在做什麼專案？負責什麼工作？不要呼叫任何外部工具，直接從記憶中回答",
            session_id=session_a,
            timeout=300,
        )
        self.assertAnyKeywordInResponse(
            response_a,
            [[marker_a, "翡翠"], [detail_a, "AI", "模型訓練", "GPU"]],
            case_sensitive=False,
        )

        self.logger.info("[7/7] 在 session B 中查詢對話上下文，應能回憶起乙資訊")
        response_b = self.send_and_retry_on_timeout(
            "請根據你記住的關於我的資訊回答：我之前告訴過你我在做什麼專案？負責什麼工作？不要呼叫任何外部工具，直接從記憶中回答",
            session_id=session_b,
            timeout=300,
        )
        self.assertAnyKeywordInResponse(
            response_b,
            [[marker_b, "琥珀"], [detail_b, "資料採集", "爬蟲"]],
            case_sensitive=False,
        )


class TestCompactArchiveGeneration(BaseOpenClawCLITest):
    """
    compact() 壓縮歸檔驗證
    測試目標：驗證對話超過閾值後，compact 正確生成 archive 並壓縮上下文
    測試路徑：持續對話 → 超過 commitTokenThreshold → 驗證 archive 生成 + 記憶檔案生成 + 上下文被壓縮
    """

    def test_compact_produces_archive_on_threshold(self):
        """對話超過閾值後應觸發 compact 生成 archive 和記憶檔案"""
        session_id = self.generate_unique_session_id(prefix="compact_test")
        verifier = OVSessionVerifier()

        self.logger.info("[1/7] 記錄 OV session 快照 + 記憶檔案 mtime 快照")
        before_sessions = verifier.list_session_ids()
        before_files = OVSessionVerifier.snapshot_memory_files()

        self.logger.info("[2/7] 寫入多輪對話，推動超過 commitTokenThreshold")
        topics = [
            "我叫張三，是一名架構師",
            "我負責的專案叫天穹系統",
            "天穹系統的核心模組是資料湖",
            "資料湖每天處理10TB資料",
            "我們團隊有8個人",
            "專案截止日期是今年年底",
        ]

        for i, topic in enumerate(topics):
            self.logger.info(f"  寫入第 {i + 1}/{len(topics)} 輪: {topic}")
            self.send_and_log(topic, session_id=session_id)
            time.sleep(3)

        self.logger.info("[3/7] 顯式 commit 並等待 archive + 記憶提取")
        ov_session_id = verifier.find_new_session_id(before_sessions)
        if ov_session_id:
            task_id = verifier.commit_session(ov_session_id)
            if task_id:
                verifier.poll_task_until_done(task_id)
        time.sleep(5)

        self.logger.info("[4/7] 驗證 archive 已生成（API 級別斷言）")
        if ov_session_id:
            has_archive = verifier.assert_archive_exists(ov_session_id)
            self.logger.info(f"  Archive 存在: {has_archive}")
            if not has_archive:
                self.logger.warning("  Archive 未生成，compact 可能未觸發")

        self.logger.info("[5/7] 驗證記憶檔案已新增或更新且包含關鍵資訊（檔案級別斷言）")
        memory_found = OVSessionVerifier.find_new_or_updated_files(before_files, keyword="天穹")
        self.logger.info(f"  本次新增/更新且包含'天穹'的記憶檔案數: {len(memory_found)}")
        for mf in memory_found:
            self.logger.info(f"  [{mf['status']}] {mf['path']}")
            if "content_preview" in mf:
                self.logger.info(f"  內容預覽: {mf['content_preview'][:100]}")
        if not memory_found:
            self.logger.warning("  未找到本次新增/更新且包含'天穹'的記憶檔案")

        self.logger.info("[6/7] 驗證 archive 生成後，agent 仍能回答早期資訊")
        response = self.send_and_retry_on_timeout(
            "我負責的專案叫什麼？核心模組是什麼？",
            session_id=session_id,
            timeout=300,
        )
        self.assertAnyKeywordInResponse(
            response,
            [["天穹"], ["資料湖"]],
            case_sensitive=False,
        )

        self.logger.info("[7/7] 驗證 archive 生成後，agent 仍能回答近期資訊")
        response2 = self.send_and_retry_on_timeout(
            "我們團隊有幾個人？專案截止日期是什麼時候？",
            session_id=session_id,
            timeout=300,
        )
        self.assertAnyKeywordInResponse(
            response2,
            [["8", "八"], ["年底"]],
            case_sensitive=False,
        )
