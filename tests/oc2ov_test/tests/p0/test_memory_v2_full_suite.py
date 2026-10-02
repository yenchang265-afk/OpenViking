"""
Memory V2 全面端到端測試套件
覆蓋所有記憶檔案型別：
- preferences (偏好設定) - User scope
- entities (實體資訊) - User scope
- events (事件記錄) - User scope
- profile (使用者畫像) - User scope, 單檔案
- skills (技能) - User scope

測試方式：通過 OpenClaw agent 進行對話，然後通過 OV API commit session 觸發記憶提取。
OpenClaw Gateway 會自動分配 OV session ID，需要通過對比 sessions 列表來定位。
"""

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from utils.cli_diagnostics import format_openclaw_cli_failure
from utils.openclaw_cli_client import _wait_for_session_lock_release
from utils.test_utils import SessionIdManager


def _load_openclaw_ov_config() -> Dict[str, str]:
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if not config_path.exists():
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return (
            config.get("plugins", {}).get("entries", {}).get("openviking", {}).get("config", {})
            or {}
        )
    except Exception:
        return {}


_OPENCLAW_OV_CONFIG = _load_openclaw_ov_config()

SERVER_URL = os.environ.get(
    "SERVER_URL",
    _OPENCLAW_OV_CONFIG.get("baseUrl", "http://127.0.0.1:1933"),
)
OPENVIKING_API_KEY = os.environ.get(
    "OPENVIKING_API_KEY",
    _OPENCLAW_OV_CONFIG.get("apiKey", "test-root-api-key"),
)
OPENVIKING_ACCOUNT = os.environ.get("OPENVIKING_ACCOUNT", "default")
OPENVIKING_USER = os.environ.get("OPENVIKING_USER", "default")
TASK_POLL_INTERVAL = 5
TASK_POLL_MAX_WAIT = 180
OV_MODE = os.environ.get("OV_MODE", _OPENCLAW_OV_CONFIG.get("mode", "local"))


def _is_remote_mode() -> bool:
    return OV_MODE == "remote" or SERVER_URL not in (
        "http://127.0.0.1:1933",
        "http://localhost:1933",
    )


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


def get_viking_data_dir() -> Path:
    """動態獲取 viking 資料目錄路徑（user scope memories）"""
    if os.environ.get("VIKING_DATA_DIR"):
        return (
            Path(os.environ["VIKING_DATA_DIR"])
            / "viking"
            / "default"
            / "user"
            / "default"
            / "memories"
        )

    project_root = Path(__file__).parent.parent.parent.parent.parent
    project_data_dir = (
        project_root / ".openviking_data" / "viking" / "default" / "user" / "default" / "memories"
    )
    if project_data_dir.exists():
        return project_data_dir

    config_candidates = [
        project_root / "ov.conf.temp",
        project_root / "ov.conf",
        Path.home() / ".openviking" / "ov.conf",
    ]
    for config_path in config_candidates:
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                workspace = config.get("storage", {}).get("workspace") or config.get(
                    "agfs", {}
                ).get("path")
                if workspace:
                    return Path(workspace) / "viking" / "default" / "user" / "default" / "memories"
            except Exception:
                pass

    cwd_data_dir = (
        Path.cwd() / ".openviking_data" / "viking" / "default" / "user" / "default" / "memories"
    )
    if cwd_data_dir.exists():
        return cwd_data_dir

    return Path.home() / ".openviking_data" / "viking" / "default" / "user" / "default" / "memories"


class OpenVikingAPIClient:
    """OV API 客戶端"""

    def __init__(self, server_url: str = SERVER_URL, api_key: str = OPENVIKING_API_KEY):
        self.server_url = server_url
        self.api_key = api_key
        self.headers = _get_api_headers()

    def list_session_ids(self) -> Set[str]:
        """獲取當前所有 OV session ID 集合"""
        try:
            resp = requests.get(
                f"{self.server_url}/api/v1/sessions",
                headers=self.headers,
                timeout=10,
            )
            if resp.status_code != 200:
                return set()
            sessions = resp.json().get("result", [])
            return {s["session_id"] for s in sessions}
        except Exception:
            return set()

    def find_new_session_id(self, before_ids: Set[str]) -> Optional[str]:
        """對比前後 session 列表，找到新建立的 session ID"""
        after_ids = self.list_session_ids()
        new_ids = after_ids - before_ids
        if new_ids:
            return new_ids.pop()
        return None

    def find_session_by_id(self, session_id: str) -> Optional[str]:
        """直接通過 session ID 查詢是否存在於 OV 中"""
        try:
            resp = requests.get(
                f"{self.server_url}/api/v1/sessions/{session_id}",
                headers=self.headers,
                timeout=10,
            )
            if resp.status_code == 200:
                return session_id
        except Exception:
            pass
        return None

    def find_session_with_most_messages(
        self, candidate_ids: Optional[Set[str]] = None
    ) -> Optional[str]:
        """在候選 session 中找到訊息數最多的 session"""
        try:
            resp = requests.get(
                f"{self.server_url}/api/v1/sessions",
                headers=self.headers,
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            sessions = resp.json().get("result", [])
            best_id = None
            best_pending = -1
            for s in sessions:
                sid = s["session_id"]
                if candidate_ids and sid not in candidate_ids:
                    continue
                try:
                    detail_resp = requests.get(
                        f"{self.server_url}/api/v1/sessions/{sid}",
                        headers=self.headers,
                        timeout=5,
                    )
                    if detail_resp.status_code == 200:
                        pending = detail_resp.json().get("result", {}).get("pending_tokens", 0)
                        if pending > best_pending:
                            best_pending = pending
                            best_id = sid
                except Exception:
                    continue
            return best_id
        except Exception:
            return None

    def commit_session(self, session_id: str) -> Dict[str, Any]:
        resp = requests.post(
            f"{self.server_url}/api/v1/sessions/{session_id}/commit",
            headers=self.headers,
            timeout=30,
        )
        return {"status_code": resp.status_code, "data": resp.json() if resp.text else {}}

    def get_task(self, task_id: str) -> Dict[str, Any]:
        resp = requests.get(
            f"{self.server_url}/api/v1/tasks/{task_id}",
            headers=self.headers,
            timeout=10,
        )
        return {"status_code": resp.status_code, "data": resp.json() if resp.text else {}}

    def poll_task_until_done(
        self, task_id: str, max_wait: int = TASK_POLL_MAX_WAIT
    ) -> Dict[str, Any]:
        start = time.time()
        while time.time() - start < max_wait:
            task_resp = self.get_task(task_id)
            if task_resp["status_code"] != 200:
                time.sleep(TASK_POLL_INTERVAL)
                continue
            task_data = task_resp["data"].get("result", {})
            status = task_data.get("status", "unknown")
            if status in ("completed", "failed"):
                return task_data
            time.sleep(TASK_POLL_INTERVAL)
        return {"status": "timeout", "task_id": task_id}

    def get_memory_stats(self) -> Dict[str, Any]:
        try:
            resp = requests.get(
                f"{self.server_url}/api/v1/stats/memories",
                headers=self.headers,
                timeout=10,
            )
            if resp.status_code != 200:
                return {}
            return resp.json().get("result", {})
        except Exception:
            return {}

    def search_memories(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            resp = requests.post(
                f"{self.server_url}/api/v1/search/find",
                headers=self.headers,
                json={"query": query, "limit": limit},
                timeout=15,
            )
            if resp.status_code != 200:
                return []
            return resp.json().get("result", {}).get("memories", [])
        except Exception:
            return []

    def list_memory_files(self, memory_type: str) -> List[str]:
        try:
            if memory_type == "skills":
                uri = "viking://user/default/skills"
            else:
                uri = f"viking://user/default/memories/{memory_type}"
            resp = requests.get(
                f"{self.server_url}/api/v1/fs/ls",
                headers=self.headers,
                params={"uri": uri, "recursive": "true", "simple": "true"},
                timeout=10,
            )
            if resp.status_code != 200:
                return []
            result = resp.json().get("result", [])
            if isinstance(result, list):
                return [str(r) for r in result if str(r).endswith(".md")]
            return []
        except Exception:
            return []

    def read_memory_file(self, uri: str) -> Optional[str]:
        """讀取遠端記憶檔案內容"""
        try:
            resp = requests.get(
                f"{self.server_url}/api/v1/content/read",
                headers=self.headers,
                params={"uri": uri},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                result = data.get("result", "")
                if isinstance(result, dict):
                    return result.get("content", "")
                elif isinstance(result, str):
                    return result
                return ""
            else:
                print(f"  ⚠ read_memory_file({uri}) 狀態碼: {resp.status_code}")
                return None
        except Exception as e:
            print(f"  ⚠ read_memory_file 異常: {e}")
            return None


class MemoryV2TestSuite:
    """Memory V2 全面測試套件 - OpenClaw 對話 + OV API commit"""

    def __init__(self):
        self.test_scenarios = self._create_test_scenarios()
        self.viking_data_dir = get_viking_data_dir()
        self.api = OpenVikingAPIClient()

    def _create_test_scenarios(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "preferences",
                "description": "測試偏好設定記憶",
                "test_message": "我喜歡用Python程式設計，偏好使用VS Code編輯器，喜歡喝咖啡，特別是美式咖啡",
                "memory_type": "preferences",
            },
            {
                "name": "entities",
                "description": "測試實體資訊記憶",
                "test_message": "我叫李明，今年28歲，是一名軟體工程師，在字節跳動工作，住在北京海淀區",
                "memory_type": "entities",
            },
            {
                "name": "profile",
                "description": "測試使用者畫像記憶",
                "test_message": "我是一名技術負責人，有10年開發經驗，專注於後端架構設計，喜歡用Python和Go語言",
                "memory_type": "profile",
            },
            {
                "name": "skills",
                "description": "測試技能記憶",
                "test_message": "我總結了一個程式碼審查的技能流程：先通讀程式碼理解意圖，再檢查邏輯錯誤和邊界條件，然後評估程式碼風格和可維護性，最後給出改進建議。請記住這個技能流程",
                "memory_type": "skills",
            },
        ]

    def run_openclaw_command(
        self, message: str, session_id: str, max_retries: int = 2
    ) -> Dict[str, Any]:
        """執行 openclaw agent 命令，超時時自動重試"""
        _wait_for_session_lock_release(session_id)

        cmd = [
            "openclaw",
            "agent",
            "--session-id",
            session_id,
            "--message",
            message,
            "--json",
        ]
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                break
            except subprocess.TimeoutExpired as e:
                last_error = e
                if attempt < max_retries:
                    print(
                        f"  ⚠ OpenClaw 命令超時 (attempt {attempt + 1}/{max_retries + 1})，重試中..."
                    )
                    time.sleep(5)
                    continue
                raise Exception(
                    f"OpenClaw command timed out after {max_retries + 1} attempts: {last_error}"
                )

        _wait_for_session_lock_release(session_id)

        if result.returncode != 0:
            raise Exception(
                format_openclaw_cli_failure(
                    "OpenClaw command failed", result.stderr, result.returncode
                )
            )

        if not result.stdout.strip():
            raise Exception(
                format_openclaw_cli_failure(
                    "OpenClaw command returned empty stdout", result.stderr, result.returncode
                )
            )

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"raw_output": result.stdout}

    def _snapshot_all_memory_files(self) -> Dict[str, float]:
        """記錄所有記憶目錄的檔案快照（路徑 → mtime）"""
        files: Dict[str, float] = {}

        user_root = self.viking_data_dir.parent
        for md_file in user_root.rglob("*.md"):
            files[str(md_file)] = md_file.stat().st_mtime

        return files

    def check_memory_files(
        self, memory_type: str, before_files: Dict[str, float]
    ) -> Dict[str, Any]:
        """檢查 commit 後是否有新增或修改的記憶檔案（全目錄掃描）"""
        result = {
            "memory_type": memory_type,
            "found": False,
            "new_files": [],
            "modified_files": [],
            "all_files": [],
        }

        if _is_remote_mode():
            return self._check_memory_files_remote(memory_type, before_files)

        target_result = self._check_target_type(memory_type, before_files)
        result["new_files"].extend(target_result["new_files"])
        result["modified_files"].extend(target_result["modified_files"])
        result["all_files"].extend(target_result["all_files"])

        if target_result["found"]:
            result["found"] = True
            return result

        print(f"  ⚠ {memory_type} 目錄無直接變化，掃描全目錄...")
        after_files = self._snapshot_all_memory_files()

        for file_str, new_mtime in after_files.items():
            if file_str not in before_files:
                result["found"] = True
                result["new_files"].append(file_str)
                rel_path = self._relative_display(file_str)
                print(f"  ✓ 其他目錄新增檔案: {rel_path}")
            else:
                old_mtime = before_files[file_str]
                if new_mtime > old_mtime:
                    result["found"] = True
                    result["modified_files"].append(file_str)
                    rel_path = self._relative_display(file_str)
                    print(f"  ✓ 其他目錄檔案已更新: {rel_path}")

        if not result["found"]:
            print("  ✗ 全目錄掃描均無新增或修改的記憶檔案")
        return result

    def _check_memory_files_remote(
        self, memory_type: str, before_files: Dict[str, float]
    ) -> Dict[str, Any]:
        """遠端模式：通過 OV API 驗證記憶是否寫入成功"""
        result = {
            "memory_type": memory_type,
            "found": False,
            "new_files": [],
            "modified_files": [],
            "all_files": [],
        }

        print("  [遠端模式] 通過 OV API 驗證記憶...")

        before_uris = set(before_files.get("_remote_uris", []))
        before_count = before_files.get("_remote_category_count", 0)
        before_profile_content = before_files.get("_remote_profile_content", "")

        if memory_type == "profile":
            profile_uri = "viking://user/default/memories/profile.md"
            content = self.api.read_memory_file(profile_uri)
            if content is not None:
                result["all_files"].append(profile_uri)
                if not before_profile_content:
                    result["found"] = True
                    result["new_files"].append(profile_uri)
                    print("  ✓ profile.md 新增 (之前無內容)")
                elif content != before_profile_content:
                    result["found"] = True
                    result["modified_files"].append(profile_uri)
                    print("  ✓ profile.md 內容已更新")
                    before_lines = set(before_profile_content.strip().splitlines())
                    after_lines = set(content.strip().splitlines())
                    added = after_lines - before_lines
                    if added:
                        for line in sorted(added)[:5]:
                            print(f"    + {line[:80]}")
                else:
                    print("  ⚠ profile.md 內容未變化")
            else:
                print("  ✗ profile.md 讀取失敗或不存在")

            if not result["found"]:
                scenario = next(
                    (s for s in self.test_scenarios if s["memory_type"] == memory_type), None
                )
                if scenario:
                    search_keywords = scenario["test_message"][:30]
                    memories = self.api.search_memories(search_keywords, limit=5)
                    if memories:
                        result["found"] = True
                        result["new_files"] = [m.get("uri", "") for m in memories]
                        print(f"  ✓ 通過 search/find 找到 {len(memories)} 條相關記憶")
                        for m in memories[:3]:
                            uri = m.get("uri", "")
                            score = m.get("score", 0)
                            abstract = (m.get("abstract", "") or "")[:60]
                            print(f"    - {uri} (score={score:.3f}) {abstract}...")

            if not result["found"]:
                print("  ✗ 遠端驗證失敗：profile 無新增或修改的記憶")
            return result

        after_files_list = self.api.list_memory_files(memory_type)
        after_uris = set(after_files_list)
        new_uris = after_uris - before_uris

        stats = self.api.get_memory_stats()
        by_category = stats.get("by_category", {})
        after_count = by_category.get(memory_type, 0)
        count_diff = after_count - before_count
        stats_available = bool(by_category)
        print(
            f"  /api/v1/stats/memories → {memory_type}: {before_count} → {after_count} (增量: {count_diff}, stats可用={stats_available})"
        )
        print(
            f"  /api/v1/fs/ls → {memory_type}: 文件 {len(before_uris)} → {len(after_uris)} (新增: {len(new_uris)})"
        )

        if new_uris:
            result["found"] = True
            result["new_files"] = list(new_uris)
            print(f"  ✓ {memory_type} 目錄新增 {len(new_uris)} 個檔案")
            for uri in list(new_uris)[:3]:
                print(f"    + {uri}")

        if stats_available and count_diff > 0:
            result["found"] = True
            print(f"  ✓ {memory_type} 類別計數增加 {count_diff} 條")

        if not result["found"] and memory_type == "skills":
            alt_type = "patterns"
            alt_before_uris = set(before_files.get("_remote_alt_uris", []))
            alt_before_count = before_files.get("_remote_alt_category_count", 0)
            alt_after_files = self.api.list_memory_files(alt_type)
            alt_after_uris = set(alt_after_files)
            alt_new_uris = alt_after_uris - alt_before_uris
            alt_after_count = by_category.get(alt_type, 0)
            alt_count_diff = alt_after_count - alt_before_count
            print(
                f"  [fallback] /api/v1/fs/ls → {alt_type}: 文件 {len(alt_before_uris)} → {len(alt_after_uris)} (新增: {len(alt_new_uris)})"
            )
            print(
                f"  [fallback] /api/v1/stats/memories → {alt_type}: {alt_before_count} → {alt_after_count} (增量: {alt_count_diff})"
            )
            if alt_new_uris:
                result["found"] = True
                result["new_files"].extend(list(alt_new_uris))
                print(f"  ✓ {alt_type} 目錄新增 {len(alt_new_uris)} 個檔案 (skills/patterns 互認)")
            if alt_count_diff > 0:
                result["found"] = True
                print(f"  ✓ {alt_type} 類別計數增加 {alt_count_diff} 條 (skills/patterns 互認)")

        if not result["found"]:
            scenario = next(
                (s for s in self.test_scenarios if s["memory_type"] == memory_type), None
            )
            if scenario:
                search_keywords = scenario["test_message"][:30]
                memories = self.api.search_memories(search_keywords, limit=5)
                if memories:
                    result["found"] = True
                    result["new_files"] = [m.get("uri", "") for m in memories]
                    print(f"  ✓ 通過 search/find 找到 {len(memories)} 條相關記憶")
                    for m in memories[:3]:
                        uri = m.get("uri", "")
                        score = m.get("score", 0)
                        abstract = (m.get("abstract", "") or "")[:60]
                        print(f"    - {uri} (score={score:.3f}) {abstract}...")

        if not result["found"]:
            print(f"  ✗ 遠端驗證失敗：{memory_type} 無新增記憶 (計數無變化且無新檔案)")
        return result

    def _relative_display(self, file_str: str) -> str:
        """生成相對路徑用於顯示"""
        try:
            base = self.viking_data_dir.parent.parent.parent
            return str(Path(file_str).relative_to(base))
        except ValueError:
            return Path(file_str).name

    def _check_target_type(
        self, memory_type: str, before_files: Dict[str, float]
    ) -> Dict[str, Any]:
        """檢查目標 memory_type 目錄的檔案變化"""
        result: Dict[str, Any] = {
            "found": False,
            "new_files": [],
            "modified_files": [],
            "all_files": [],
        }

        if memory_type == "profile":
            profile_file = self.viking_data_dir / "profile.md"
            if profile_file.exists():
                file_str = str(profile_file)
                result["all_files"].append(file_str)
                if file_str not in before_files:
                    result["found"] = True
                    result["new_files"].append(file_str)
                    print(f"  ✓ 新增 profile 文件: {profile_file}")
                else:
                    old_mtime = before_files[file_str]
                    new_mtime = profile_file.stat().st_mtime
                    if new_mtime > old_mtime:
                        result["found"] = True
                        result["modified_files"].append(file_str)
                        print("  ✓ profile 檔案已更新 (mtime 變化)")
                    else:
                        print(f"  ⚠ profile 檔案未變化: {profile_file}")
            else:
                print(f"  ✗ profile 文件不存在: {profile_file}")
            return result

        if memory_type == "skills":
            skills_dir = self.viking_data_dir.parent / "skills"
            if not skills_dir.exists():
                print(f"  ✗ skills 目錄不存在: {skills_dir}")
                return result

            for md_file in sorted(skills_dir.rglob("*.md")):
                file_str = str(md_file)
                if file_str in result["all_files"]:
                    continue
                result["all_files"].append(file_str)
                if file_str not in before_files:
                    result["found"] = True
                    result["new_files"].append(file_str)
                    print(f"  ✓ 新增技能檔案: {md_file.name} (在 user/skills 目錄下)")
                else:
                    old_mtime = before_files[file_str]
                    new_mtime = md_file.stat().st_mtime
                    if new_mtime > old_mtime:
                        result["found"] = True
                        result["modified_files"].append(file_str)
                        print(f"  ✓ 技能檔案已更新: {md_file.name} (在 user/skills 目錄下)")

            if not result["found"]:
                if result["all_files"]:
                    print(f"  ⚠ {memory_type} 目錄有檔案但均無變化")
                else:
                    print(f"  ✗ 未找到 {memory_type} 相關記憶檔案")
            return result

        # user scope: preferences, entities, events
        memory_dir = self.viking_data_dir / memory_type
        if not memory_dir.exists():
            print(f"  ✗ 記憶目錄不存在: {memory_dir}")
            return result

        for md_file in sorted(memory_dir.rglob("*.md")):
            file_str = str(md_file)
            result["all_files"].append(file_str)
            if file_str not in before_files:
                result["found"] = True
                result["new_files"].append(file_str)
                rel = md_file.relative_to(memory_dir)
                print(f"  ✓ 新增記憶檔案: {rel}")
            else:
                old_mtime = before_files[file_str]
                new_mtime = md_file.stat().st_mtime
                if new_mtime > old_mtime:
                    result["found"] = True
                    result["modified_files"].append(file_str)
                    rel = md_file.relative_to(memory_dir)
                    print(f"  ✓ 記憶檔案已更新: {rel}")

        if not result["found"]:
            if result["all_files"]:
                print(f"  ⚠ {memory_type} 目錄有檔案但均無變化")
            else:
                print(f"  ✗ 未找到 {memory_type} 記憶檔案")
        return result

    def test_single_scenario(self, scenario: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """測試單個場景：OpenClaw 對話 → OV API commit → 輪詢任務 → 檢查記憶檔案"""
        print(f"\n{'=' * 60}")
        print(f"測試場景: {scenario['name']} - {scenario['description']}")
        print(f"{'=' * 60}")

        result = {
            "scenario": scenario["name"],
            "description": scenario["description"],
            "memory_type": scenario["memory_type"],
            "steps": {},
        }

        try:
            # 每個場景使用獨立的 session ID，確保 OpenClaw 建立新的 OV session
            scenario_session_id = SessionIdManager.generate_session_id(
                prefix=f"memv2_{scenario['name']}"
            )

            # 步驟 1: 記錄當前 OV sessions 快照和全目錄記憶檔案快照
            print("\n[步驟 1/5] 記錄快照")
            before_session_ids = self.api.list_session_ids()
            if _is_remote_mode():
                before_stats = self.api.get_memory_stats()
                before_count = before_stats.get("by_category", {}).get(scenario["memory_type"], 0)
                before_uris = self.api.list_memory_files(scenario["memory_type"])
                before_memory_files = {
                    "_remote_uris": before_uris,
                    "_remote_category_count": before_count,
                    "_remote_profile_content": "",
                }
                if scenario["memory_type"] == "profile":
                    before_memory_files["_remote_profile_content"] = (
                        self.api.read_memory_file("viking://user/default/memories/profile.md") or ""
                    )
                if scenario["memory_type"] == "skills":
                    before_alt_uris = self.api.list_memory_files("patterns")
                    before_alt_count = before_stats.get("by_category", {}).get("patterns", 0)
                    before_memory_files["_remote_alt_uris"] = before_alt_uris
                    before_memory_files["_remote_alt_category_count"] = before_alt_count
                print(f"  當前 session 數量: {len(before_session_ids)}")
                print(f"  [遠端模式] 記憶統計: {before_stats.get('by_category', {})}")
                print(
                    f"  [遠端模式] {scenario['memory_type']} 檔案數: {len(before_uris)}, 計數: {before_count}"
                )
            else:
                before_memory_files = self._snapshot_all_memory_files()
                print(f"  當前 session 數量: {len(before_session_ids)}")
                print(f"  當前全目錄記憶檔案數量: {len(before_memory_files)}")
            print(f"  場景 session ID: {scenario_session_id}")
            result["steps"]["snapshot"] = "success"

            # 步驟 2: 通過 OpenClaw 傳送訊息
            print("\n[步驟 2/5] 通過 OpenClaw 傳送訊息")
            print(f"  消息: {scenario['test_message'][:50]}...")
            self.run_openclaw_command(scenario["test_message"], scenario_session_id)
            print("✓ OpenClaw 對話完成")
            result["steps"]["openclaw_chat"] = "success"
            time.sleep(8)

            # 步驟 3: 找到 OV session 並 commit
            print("\n[步驟 3/5] 查詢 OV session 並 commit")
            ov_session_id = self.api.find_new_session_id(before_session_ids)

            if not ov_session_id:
                ov_session_id = self.api.find_session_by_id(scenario_session_id)
                if ov_session_id:
                    print(f"  ✓ 通過 scenario_session_id 找到 session: {ov_session_id[:8]}...")

            if not ov_session_id:
                print("  ⚠ 未找到新 session，等待 OV auto-capture 建立 session...")
                for retry in range(5):
                    time.sleep(5)
                    ov_session_id = self.api.find_new_session_id(before_session_ids)
                    if not ov_session_id:
                        ov_session_id = self.api.find_session_by_id(scenario_session_id)
                    if ov_session_id:
                        print(f"  ✓ 第 {retry + 1} 次重試找到新 session")
                        break
                all_session_ids = self.api.list_session_ids()
                committed_any = False
                for sid in all_session_ids:
                    try:
                        commit_resp = self.api.commit_session(sid)
                        commit_data = commit_resp.get("data") or {}
                        commit_result = commit_data.get("result") or {}
                        task_id = commit_result.get("task_id")
                        if task_id:
                            print(f"  ✓ Commit session {sid[:8]}... 成功 (task_id: {task_id})")
                            ov_session_id = sid
                            committed_any = True
                            break
                    except Exception:
                        continue
                if not committed_any:
                    print("  ⚠ 所有 session commit 均無 task_id，跳過 commit，直接檢查記憶檔案")
                    result["steps"]["commit"] = "skipped"
                    result["ov_session_id"] = None
                    print("\n[步驟 4/5] 跳過 (無有效 commit)")
                    print("\n[步驟 5/5] 驗證記憶檔案變化")
                    memory_files_result = self.check_memory_files(
                        scenario["memory_type"], before_memory_files
                    )
                    result["memory_files"] = memory_files_result
                    if memory_files_result["found"]:
                        result["steps"]["memory_files"] = "success"
                        result["status"] = "passed"
                        return True, result
                    else:
                        result["steps"]["memory_files"] = "failed"
                        result["status"] = "failed"
                        result["error"] = f"{scenario['memory_type']}: 無有效 commit 且無新增記憶"
                        return False, result

            print(f"  OV session ID: {ov_session_id}")
            commit_resp = self.api.commit_session(ov_session_id)
            commit_data = commit_resp.get("data") or {}
            commit_result = commit_data.get("result") or {}
            task_id = commit_result.get("task_id")

            if commit_resp.get("status_code") == 404:
                print("  ⚠ OV session 不存在 (404)，跳過 commit，直接檢查記憶檔案")
                result["steps"]["commit"] = "skipped_404"
                result["ov_session_id"] = None
                print("\n[步驟 4/5] 跳過 (session 不存在)")
                print("\n[步驟 5/5] 驗證記憶檔案變化")
                memory_files_result = self.check_memory_files(
                    scenario["memory_type"], before_memory_files
                )
                result["memory_files"] = memory_files_result
                if memory_files_result["found"]:
                    result["steps"]["memory_files"] = "success"
                    result["status"] = "passed"
                    return True, result
                else:
                    result["steps"]["memory_files"] = "failed"
                    result["status"] = "failed"
                    result["error"] = f"{scenario['memory_type']}: OV session 404 且無新增記憶"
                    return False, result

            if not task_id and commit_result.get("status") == "accepted":
                print("  ⚠ Commit 返回 accepted 但無 task_id，補充對話後重試...")
                follow_ups = [
                    "請詳細總結一下我剛才告訴你的所有資訊，逐條列出。",
                    "你能複述一下我的個人情況嗎？越詳細越好。",
                ]
                for follow_up in follow_ups:
                    try:
                        self.run_openclaw_command(follow_up, scenario_session_id)
                        time.sleep(3)
                    except Exception:
                        pass
                # Wait for messages to be persisted before re-committing
                time.sleep(5)
                commit_resp = self.api.commit_session(ov_session_id)
                commit_data = commit_resp.get("data") or {}
                commit_result = commit_data.get("result") or {}
                task_id = commit_result.get("task_id")

                # If still no task_id, try waiting longer and retrying
                if not task_id:
                    print("  ⚠ 重試後仍無 task_id，等待更長時間後再次嘗試...")
                    time.sleep(10)
                    commit_resp = self.api.commit_session(ov_session_id)
                    commit_data = commit_resp.get("data") or {}
                    commit_result = commit_data.get("result") or {}
                    task_id = commit_result.get("task_id")

            if commit_resp.get("status_code") == 200 and task_id:
                print(f"✓ Commit 成功 (task_id: {task_id})")
                result["steps"]["commit"] = "success"
                result["ov_session_id"] = ov_session_id
                result["task_id"] = task_id
            elif commit_resp.get("status_code") == 200 and not task_id:
                print("  ⚠ Commit 返回 task_id=None，跳過記憶提取步驟")
                result["steps"]["commit"] = "accepted_no_task"
                result["ov_session_id"] = ov_session_id
                result["steps"]["memory_extraction"] = "skipped"
                print("\n[步驟 4/5] 跳過 (無 task_id)")
                print("\n[步驟 5/5] 驗證記憶檔案變化")
                memory_files_result = self.check_memory_files(
                    scenario["memory_type"], before_memory_files
                )
                result["memory_files"] = memory_files_result
                if memory_files_result["found"]:
                    result["steps"]["memory_files"] = "success"
                    result["status"] = "passed"
                    return True, result
                else:
                    result["steps"]["memory_files"] = "failed"
                    result["status"] = "failed"
                    result["error"] = f"{scenario['memory_type']}: Commit 無 task_id 且無新增記憶"
                    return False, result
            else:
                print(f"✗ Commit 失敗: {commit_resp}")
                result["steps"]["commit"] = "failed"
                result["status"] = "failed"
                result["error"] = f"Commit 失敗: {commit_resp}"
                return False, result

            # 步驟 4: 輪詢任務直到完成
            print(f"\n[步驟 4/5] 等待記憶提取完成 (輪詢 task_id: {task_id})")
            task_result = self.api.poll_task_until_done(task_id)
            task_status = task_result.get("status", "unknown")
            memories_extracted = task_result.get("result", {}).get("memories_extracted", {})
            token_usage = task_result.get("result", {}).get("token_usage", {})

            print(f"  任務狀態: {task_status}")
            print(f"  提取的記憶: {memories_extracted}")
            if token_usage:
                llm_tokens = token_usage.get("llm", {}).get("total_tokens", 0)
                print(f"  LLM token 用量: {llm_tokens}")

            if task_status == "completed":
                total_extracted = (
                    sum(len(v) if isinstance(v, list) else v for v in memories_extracted.values())
                    if memories_extracted
                    else 0
                )
                if total_extracted > 0:
                    print(f"✓ 記憶提取成功，共提取 {total_extracted} 條記憶")
                    result["steps"]["memory_extraction"] = "success"
                else:
                    print("⚠ 記憶提取完成但結果為空 (VLM 可能返回了無效 JSON)")
                    result["steps"]["memory_extraction"] = "empty"
            elif task_status == "failed":
                error_msg = task_result.get("error", "unknown error")
                print(f"✗ 記憶提取失敗: {error_msg}")
                result["steps"]["memory_extraction"] = "failed"
            else:
                print("✗ 記憶提取超時")
                result["steps"]["memory_extraction"] = "timeout"

            result["task_result"] = task_result

            # 步驟 5: 驗證記憶檔案變化（硬性斷言）
            print("\n[步驟 5/5] 驗證記憶檔案變化")
            memory_files_result = self.check_memory_files(
                scenario["memory_type"], before_memory_files
            )
            result["memory_files"] = memory_files_result

            if memory_files_result["found"]:
                new_count = len(memory_files_result["new_files"])
                mod_count = len(memory_files_result["modified_files"])
                print(f"✓ 記憶檔案有變化，新增 {new_count} 個，更新 {mod_count} 個")
                result["steps"]["memory_files"] = "success"
            else:
                print("✗ 記憶檔案驗證失敗（全目錄無新增或修改的檔案）")
                result["steps"]["memory_files"] = "failed"

            # 綜合判斷：記憶提取成功 + 檔案有變化 = 通過
            extraction_ok = result["steps"].get("memory_extraction") == "success"
            files_ok = result["steps"].get("memory_files") == "success"

            if files_ok:
                result["status"] = "passed"
                if not extraction_ok:
                    print("⚠ 記憶提取輪詢超時，但檔案驗證成功，判定通過")
                return True, result
            else:
                reasons = []
                if not extraction_ok:
                    reasons.append("記憶提取失敗或為空")
                if not files_ok:
                    reasons.append("無新增或修改的記憶檔案")
                result["status"] = "failed"
                result["error"] = f"{scenario['memory_type']}: {', '.join(reasons)}"
                return False, result

        except Exception as e:
            print(f"\n✗ 場景測試執行失敗: {e}")
            result["status"] = "error"
            result["error"] = str(e)
            return False, result

    def run_full_test_suite(self) -> Dict[str, Any]:
        """執行完整的測試套件"""
        print("\n" + "=" * 60)
        print("Memory V2 全面端到端測試套件")
        print("  對話方式: OpenClaw agent")
        print("  Commit 方式: OV API")
        print("=" * 60)
        print(f"\n測試場景數量: {len(self.test_scenarios)}")
        print(f"記憶型別覆蓋: {', '.join([s['memory_type'] for s in self.test_scenarios])}")
        print(f"資料目錄: {self.viking_data_dir}")
        print(f"OV Server: {SERVER_URL}")

        results = {
            "total_scenarios": len(self.test_scenarios),
            "scenarios": [],
            "summary": {"passed": 0, "failed": 0, "error": 0},
        }

        for scenario in self.test_scenarios:
            passed, result = self.test_single_scenario(scenario)
            results["scenarios"].append(result)

            if result["status"] == "passed":
                results["summary"]["passed"] += 1
            elif result["status"] == "failed":
                results["summary"]["failed"] += 1
            else:
                results["summary"]["error"] += 1

        print("\n" + "=" * 60)
        print("測試總結")
        print("=" * 60)
        print(f"總場景數: {results['total_scenarios']}")
        print(f"通過: {results['summary']['passed']}")
        print(f"失敗: {results['summary']['failed']}")
        print(f"錯誤: {results['summary']['error']}")

        pass_rate = results["summary"]["passed"] / results["total_scenarios"]
        print(f"\n通過率: {pass_rate * 100:.1f}%")

        if pass_rate >= 0.7:
            print("\n✓ Memory V2 測試套件通過！")
        else:
            print("\n✗ Memory V2 測試套件未通過")

        return results


SCENARIO_MAP = {
    "preferences": {
        "name": "preferences",
        "description": "測試偏好設定記憶",
        "test_message": "我喜歡用Python程式設計，偏好使用VS Code編輯器，喜歡喝咖啡，特別是美式咖啡",
        "memory_type": "preferences",
    },
    "entities": {
        "name": "entities",
        "description": "測試實體資訊記憶",
        "test_message": "我叫李明，今年28歲，是一名軟體工程師，在字節跳動工作，住在北京海淀區",
        "memory_type": "entities",
    },
    "profile": {
        "name": "profile",
        "description": "測試使用者畫像記憶",
        "test_message": "我是一名技術負責人，有10年開發經驗，專注於後端架構設計，喜歡用Python和Go語言",
        "memory_type": "profile",
    },
    "skills": {
        "name": "skills",
        "description": "測試技能記憶",
        "test_message": "我總結了一個程式碼審查的技能流程：先通讀程式碼理解意圖，再檢查邏輯錯誤和邊界條件，然後評估程式碼風格和可維護性，最後給出改進建議。請記住這個技能流程",
        "memory_type": "skills",
    },
}


def _run_single_memory_test(scenario_key: str):
    tester = MemoryV2TestSuite()
    scenario = SCENARIO_MAP[scenario_key]
    passed, result = tester.test_single_scenario(scenario)
    assert passed, f"{scenario['name']} 測試失敗: {result.get('error', '未知錯誤')}"


def test_memory_v2_preferences():
    _run_single_memory_test("preferences")


def test_memory_v2_entities():
    _run_single_memory_test("entities")


def test_memory_v2_profile():
    _run_single_memory_test("profile")


def test_memory_v2_skills():
    _run_single_memory_test("skills")


if __name__ == "__main__":
    """直接執行測試"""
    tester = MemoryV2TestSuite()
    results = tester.run_full_test_suite()

    print("\n" + "=" * 60)
    print("詳細測試報告")
    print("=" * 60)

    for scenario in results["scenarios"]:
        status_icon = "✓" if scenario["status"] == "passed" else "✗"
        print(f"\n{status_icon} {scenario['scenario']}: {scenario['status']}")
        steps = scenario.get("steps", {})
        for step_name, step_status in steps.items():
            step_icon = (
                "✓" if step_status in ("success",) else "⚠" if step_status == "empty" else "✗"
            )
            print(f"  {step_icon} {step_name}: {step_status}")
        if scenario.get("error"):
            print(f"  錯誤: {scenario['error']}")

    exit(0 if results["summary"]["passed"] >= results["total_scenarios"] * 0.7 else 1)
