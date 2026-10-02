#!/usr/bin/env python3
"""
OpenClaw 記憶鏈路完整端到端測試

================================================================================
一、用例設計思路
================================================================================

驗證 Business Data Platform 記憶外掛的完整鏈路，覆蓋訊息寫入到記憶召回的每個環節:

  afterTurn → commit → assemble → sessionId 一致性 → 新使用者記憶召回

各環節驗證目標:
  1. afterTurn: 本輪訊息無損寫入 OV session，sessionId 一致
  2. commit: 歸檔訊息 + 提取長期記憶（cards/events/profile 等）
  3. assemble: 同用戶繼續對話時，從 latest_archive_overview + active
     messages 正確重組上下文
  4. budget trimming: 小 token budget 下 archive overview 被合理裁剪
  5. sessionId 一致性: 整條鏈路使用統一的 OV sessionId，無 sessionKey 殘留
  6. 新使用者記憶召回: 不同使用者發問時，auto-recall 注入相關記憶

對話資料設計:
  12 輪對話涵蓋：個人背景、技術棧、專案細節、快取方案討論、團隊資訊、
  訊息佇列選型、監控體系、偏好設定等，確保記憶提取能覆蓋多種類別。

斷言策略:
  - 確定性檢查 (hard): afterTurn 寫入、commit_count、sessionId、overview 存在性
  - LLM 依賴檢查 (soft): Assemble/Recall 的關鍵詞命中率 >= 50%

================================================================================
二、測試流程
================================================================================

  Phase 1: 多輪對話 (12 輪) — 寫入對話資料
  Phase 2: afterTurn 驗證 — 檢查 OV session 存在性和訊息內容
  Phase 3: Commit 驗證 — 觸發 commit, 檢查歸檔結構和記憶提取
  Phase 4: Assemble 驗證 — 同用戶繼續對話, 驗證上下文重組 + budget trimming
  Phase 5: SessionId 一致性驗證 — 無 sessionKey 殘留
  Phase 6: 新使用者記憶召回 (3 問) — 驗證 auto-recall

================================================================================
三、環境前提
================================================================================

  1. Business Data Platform 服務已啟動
  2. OpenClaw Gateway 已啟動並配置了 Business Data Platform 外掛
  3. LLM 後端可達（Gateway 需要呼叫 LLM 生成回覆）
  4. 有效的 Gateway auth token

  關鍵 openclaw.json 配置（影響測試行為）:
    - plugins.slots.contextEngine = "openviking"   # 使用 OV 作為 context engine
    - plugins.slots.memory = "none"                # 不使用內建 memory-core
    - plugins.entries.openviking.enabled = true     # 啟用 OV 外掛
    - plugins.entries.openviking.config.autoCapture = true  # afterTurn 自動捕獲
    - plugins.entries.openviking.config.autoRecall = true   # 新使用者自動召回記憶
    - plugins.entries.openviking.config.commitTokenThresholdRatio = 0
      ↑ 此值控制 auto-commit 觸發時機，按模型上下文視窗的比例計算。
        設為 0 時每輪都 commit；若比例較大（如 0.8），測試中 auto-commit
        不會提前發生，Phase 3 的 commit 驗證行為會不同。指令碼已相容兩種場景。

================================================================================
四、使用方法
================================================================================

  安裝依賴:
    pip install requests rich

  完整測試:
    python test-memory-chain.py --phase all \\
        --gateway http://127.0.0.1:19789 \\
        --openviking http://127.0.0.1:2934 \\
        --token <your_gateway_token>

  分階段執行:
    python test-memory-chain.py --phase chat        # 僅多輪對話
    python test-memory-chain.py --phase afterTurn   # 僅 afterTurn 驗證
    python test-memory-chain.py --phase commit      # 僅 commit 驗證
    python test-memory-chain.py --phase assemble    # 僅 assemble 驗證
    python test-memory-chain.py --phase session-id  # 僅 sessionId 檢查
    python test-memory-chain.py --phase recall      # 僅記憶召回

  其他選項:
    --user-id <id>      固定使用者 ID（預設隨機生成）
    --delay <seconds>    輪次間等待秒數（預設 3s）
    --verbose / -v       詳細輸出

  注意:
    - 完整測試約需 8-12 分鐘
    - 首次執行前建議清理 OV 資料和 session 資料

================================================================================
五、已知限制
================================================================================

  1. LLM 回覆非確定性:
     Assemble 和 Recall 階段的關鍵詞命中依賴 LLM 回覆內容。不同模型、不同
     temperature 設定下可能產生不同結果。關鍵詞命中率閾值已設為 50% 以容忍
     表述差異，但仍可能偶發失敗。

  2. auto-commit 時序:
     Gateway 的 afterTurn 可能觸發 auto-commit，導致手動 commit 時無新內容。
     指令碼已處理此場景（auto_committed=True 時條件性通過）。

  3. 記憶提取質量:
     不同 LLM 對同一對話提取的記憶類別和內容可能不同，影響 Recall 階段的
     關鍵詞匹配。建議使用支援中文的高質量模型。

  4. sessionId 映射:
     Gateway 內部使用 UUID 作為 OV sessionId，不等於傳入的 user_id。指令碼
     通過 OV sessions 列表介面自動發現實際 sessionId。

================================================================================
六、預期結果
================================================================================

  29/29 斷言全部通過:
    - Phase 1: 12 輪對話全部成功
    - Phase 2~3: afterTurn 寫入正確, commit 歸檔正常
    - Phase 4: Assemble Q1/Q2 關鍵詞命中率 >= 50%
    - Phase 5: sessionId 一致，無殘留
    - Phase 6: Recall Q1/Q2/Q3 關鍵詞命中率 >= 50%
"""

import argparse
import io
import json
import os
import sys
import time
import uuid
from datetime import datetime
from typing import Any

import requests
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── 常量 ───────────────────────────────────────────────────────────────────

USER_ID = f"test-chain-{uuid.uuid4().hex[:8]}"
DISPLAY_NAME = "測試使用者"
DEFAULT_GATEWAY = "http://127.0.0.1:19789"
DEFAULT_OPENVIKING = "http://127.0.0.1:2934"
AGENT_ID = "main"

console = Console(force_terminal=True)

# ── 測試結果收集 ──────────────────────────────────────────────────────────

assertions: list[dict] = []


def check(label: str, condition: bool, detail: str = ""):
    """記錄一個斷言結果。"""
    assertions.append({"label": label, "ok": condition, "detail": detail})
    icon = "[green]PASS[/green]" if condition else "[red]FAIL[/red]"
    msg = f"  {icon} {label}"
    if detail:
        msg += f"  [dim]({detail})[/dim]"
    console.print(msg)


# ── 對話資料 ──────────────────────────────────────────────────────────────

CHAT_MESSAGES = [
    "你好，我是一個軟體工程師，我叫張明，在一家科技公司工作。我主要負責後端服務開發，使用的技術棧是 Python 和 Go。最近我們在重構一個訂單系統，遇到了不少挑戰。",
    "關於訂單系統的問題，主要是效能瓶頸。我們發現在高峰期，資料庫連線池經常被耗盡。目前用的是 PostgreSQL，連線池大小設定的是100，但每秒峰值請求量有5000。你有什麼建議嗎？",
    "謝謝你的建議。我還想問一下，我們目前的快取策略用的是 Redis，但快取擊穿的問題很嚴重。熱點資料過期後，大量請求直接打到資料庫。我們嘗試過加互斥鎖，但效能下降很多。",
    "對了，關於程式碼風格，我們團隊更傾向於使用函數語言程式設計的思想，儘量避免副作用。變數命名用 snake_case，文件用中文寫。程式碼審查很嚴格，每個 PR 至少需要兩人 review。",
    "說到工作流程，我們每天早上9點站會，週三下午技術分享會。我一般上午寫程式碼，下午處理 code review 和會議。晚上如果不加班，會看看技術書籍或者寫寫部落格。",
    "我最近在學習分散式系統的設計，正在看《資料密集型應用系統設計》這本書。之前看完了《深入理解計算機系統》，收穫很大。你有什麼好的分散式系統學習資料推薦嗎？",
    "目前訂單系統重構的進度大概完成了60%，還剩下支付模組和庫存同步模組。支付模組比較複雜，需要對接多個支付渠道。我們打算用訊息佇列來解耦庫存同步。",
    "訊息佇列我們在 Kafka 和 RabbitMQ 之間猶豫。Kafka 吞吐量高，但運維複雜；RabbitMQ 功能豐富，但效能稍差。我們的訊息量大概每天1000萬條，你覺得選哪個好？",
    "我們團隊有8個人，3個後端、2個前端、1個測試、1個運維，還有1個產品經理。後端老王經驗最豐富，遇到難題都找他。測試小李很細心，bug檢出率很高。",
    "對了，跟我聊天的時候注意幾點：我喜歡簡潔直接的回答，不要太囉嗦；技術問題最好帶程式碼示例；如果不確定的問題要說明，不要瞎編。謝謝！",
    "補充一下，我們的監控用的是 Prometheus + Grafana，日誌用 ELK Stack。最近在考慮引入鏈路追蹤，OpenTelemetry 看起來不錯，但不知道跟現有系統整合麻不麻煩。",
    "昨天線上出了個詭異的 bug，某個介面偶發超時，但日誌裡看不出什麼問題。後來發現是下游服務的連線數滿了，但監控指標沒配好，沒報警。這種問題怎麼預防比較好？",
]

# assemble 階段: 同用戶繼續對話，用於驗證 assemble 是否攜帶了摘要上下文
ASSEMBLE_FOLLOWUP_MESSAGES = [
    {
        "question": "對了，我之前提到的訂單系統重構進展到哪了？支付模組開始了嗎？",
        "anchor_keywords": ["訂單系統", "支付模組", "60%"],
        "hook": "assemble — latest_archive_overview 重組",
    },
    {
        "question": "我之前跟你說過選訊息佇列的事，Kafka 和 RabbitMQ 各有什麼優缺點來著？",
        "anchor_keywords": ["Kafka", "RabbitMQ"],
        "hook": "assemble — latest_archive_overview 重組",
    },
]

# 新使用者記憶召回
RECALL_QUESTIONS = [
    {
        "question": "請根據本輪測試標記 {marker} 回答：張明是做什麼工作的？用什麼技術棧？請簡潔回答",
        "expected_keywords": ["張明", "軟體工程師", "Python", "Go"],
    },
    {
        "question": "請根據本輪測試標記 {marker} 回答：張明最近在做什麼專案？遇到了什麼技術挑戰？請簡潔回答",
        "expected_keywords": ["訂單系統", "效能瓶頸", "快取"],
    },
    {
        "question": "請根據本輪測試標記 {marker} 回答：張明團隊有多少人？團隊裡誰經驗最豐富？請簡潔回答",
        "expected_keywords": ["8", "老王"],
    },
]


def test_marker(user_id: str) -> str:
    return f"OV-E2E-MARKER:{user_id}"


def chat_message_for_turn(user_id: str, index: int, message: str) -> str:
    if index == 1:
        return f"{message}\n\n本輪 Business Data Platform e2e 測試標記：{test_marker(user_id)}。"
    return message


def flatten_message_text(value: Any) -> str:
    chunks: list[str] = []
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for item in value:
            chunks.append(flatten_message_text(item))
        return "\n".join(part for part in chunks if part)
    if isinstance(value, dict):
        for key in ("text", "content", "summary", "latest_archive_overview"):
            raw = value.get(key)
            if isinstance(raw, str):
                chunks.append(raw)
        for key in ("parts", "messages", "content"):
            raw = value.get(key)
            if isinstance(raw, list):
                chunks.append(flatten_message_text(raw))
        return "\n".join(part for part in chunks if part)
    return ""


def flatten_context_text(ctx: dict | None) -> str:
    if not isinstance(ctx, dict):
        return ""
    chunks = [
        str(ctx.get("latest_archive_overview") or ""),
        flatten_message_text(ctx.get("pre_archive_abstracts")),
        flatten_message_text(ctx.get("messages")),
    ]
    return "\n".join(part for part in chunks if part)


# ── Token 自動發現 ────────────────────────────────────────────────────────

_gateway_token: str = ""


def discover_gateway_token() -> str:
    """從常見路徑自動發現 gateway auth token。"""
    import pathlib

    candidates = [
        pathlib.Path.cwd() / "config" / ".openclaw" / "openclaw.json",
        pathlib.Path.home() / ".openclaw" / "openclaw.json",
    ]
    state_dir = os.environ.get("OPENCLAW_STATE_DIR")
    if state_dir:
        candidates.insert(0, pathlib.Path(state_dir) / "openclaw.json")

    for p in candidates:
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
            token = cfg.get("gateway", {}).get("auth", {}).get("token", "")
            if token:
                return token
        except Exception:
            continue
    return ""


def set_gateway_token(token: str):
    global _gateway_token
    _gateway_token = token


# ── Gateway / Business Data Platform API ─────────────────────────────────────────────


def send_message(gateway_url: str, message: str, user_id: str) -> dict:
    """通過 OpenClaw Responses API 傳送訊息。"""
    headers = {"Content-Type": "application/json"}
    if _gateway_token:
        headers["Authorization"] = f"Bearer {_gateway_token}"
    resp = requests.post(
        f"{gateway_url}/v1/responses",
        headers=headers,
        json={"model": "openclaw", "input": message, "user": user_id},
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()


def extract_reply_text(data: dict) -> str:
    """從 Responses API 響應中提取助手回覆文本。"""
    for item in data.get("output", []):
        if item.get("type") == "message" and item.get("role") == "assistant":
            for part in item.get("content", []):
                if part.get("type") in ("text", "output_text"):
                    return part.get("text", "")
    return "(無回覆)"


class OpenVikingInspector:
    """Business Data Platform 內部狀態檢查器。"""

    def __init__(self, base_url: str, api_key: str = "", agent_id: str = AGENT_ID):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.agent_id = agent_id

    def _headers(self) -> dict:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            h["X-API-Key"] = self.api_key
        if self.agent_id:
            h["X-OpenViking-Actor-Peer"] = self.agent_id
        return h

    def _get(self, path: str, timeout: int = 10) -> dict | None:
        try:
            resp = requests.get(f"{self.base_url}{path}", headers=self._headers(), timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result", data)
            return None
        except Exception as e:
            console.print(f"[dim]GET {path} 失敗: {e}[/dim]")
            return None

    def _post(self, path: str, body: dict | None = None, timeout: int = 30) -> dict | None:
        try:
            resp = requests.post(
                f"{self.base_url}{path}",
                headers=self._headers(),
                json=body or {},
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result", data)
            return None
        except Exception as e:
            console.print(f"[dim]POST {path} 失敗: {e}[/dim]")
            return None

    def health_check(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def get_session(self, session_id: str) -> dict | None:
        return self._get(f"/api/v1/sessions/{session_id}")

    def get_session_messages(self, session_id: str) -> list | None:
        result = self._get(f"/api/v1/sessions/{session_id}/messages")
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("messages", [])
        return None

    def get_session_context(self, session_id: str, token_budget: int = 128000) -> dict | None:
        return self._get(f"/api/v1/sessions/{session_id}/context?token_budget={token_budget}")

    def commit_session(self, session_id: str, wait: bool = True) -> dict | None:
        result = self._post(f"/api/v1/sessions/{session_id}/commit", timeout=120)
        if not result:
            return None

        if wait and result.get("task_id"):
            task_id = result["task_id"]
            deadline = time.time() + 120
            while time.time() < deadline:
                time.sleep(0.5)
                task = self._get(f"/api/v1/tasks/{task_id}")
                if not task:
                    continue
                if task.get("status") == "completed":
                    result["status"] = "completed"
                    result["memories_extracted"] = task.get("result", {}).get(
                        "memories_extracted", {}
                    )
                    return result
                if task.get("status") == "failed":
                    result["status"] = "failed"
                    result["error"] = task.get("error")
                    return result

        return result

    def search_memories(
        self, query: str, target_uri: str = "viking://~/memories", limit: int = 10
    ) -> list:
        result = self._post(
            "/api/v1/search/find",
            {"query": query, "target_uri": target_uri, "limit": limit},
        )
        if isinstance(result, dict):
            return result.get("memories", [])
        return []

    def list_sessions(self) -> list:
        result = self._get("/api/v1/sessions")
        if isinstance(result, list):
            return result
        return []

    def find_session_for_user(self, user_hint: str) -> str | None:
        """通過遍歷 OV session 列表找到與當前測試關聯的 session。
        Gateway 可能使用內部 UUID 而非 user_id 作為 OV session_id，
        因此必須檢查本輪唯一 marker，不能回退到歷史 session。"""
        sessions = self.list_sessions()
        real_sessions = [
            s
            for s in sessions
            if isinstance(s, dict) and not s.get("session_id", "").startswith("memory-store-")
        ]
        if not real_sessions:
            return None

        marker = test_marker(user_hint)
        best_id: str | None = None
        best_score = 0
        for s in real_sessions:
            sid = s.get("session_id", "")
            if not sid:
                continue
            if sid == user_hint:
                return sid
            ctx = self.get_session_context(sid)
            text = flatten_context_text(ctx)
            messages = self.get_session_messages(sid)
            text += "\n" + flatten_message_text(messages)
            score = 0
            if marker in text:
                score += 100
            if user_hint in text:
                score += 20
            if "張明" in text:
                score += 5
            if "PostgreSQL" in text:
                score += 5
            if score > best_score:
                best_score = score
                best_id = sid

        return best_id if best_score >= 100 else None

    def list_fs(self, uri: str) -> list:
        result = self._get(f"/api/v1/fs/ls?uri={uri}&output=original")
        return result if isinstance(result, list) else []

    def read_fs(self, uri: str) -> str | None:
        """讀取 fs 中某個檔案的內容。"""
        result = self._get(f"/api/v1/content/read?uri={uri}")
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            return result.get("content")
        return None


# ── 渲染函式 ──────────────────────────────────────────────────────────────


def render_reply(text: str, title: str = "回覆"):
    lines = text.split("\n")
    if len(lines) > 25:
        text = "\n".join(lines[:25]) + f"\n\n... (共 {len(lines)} 行，已截斷)"
    console.print(Panel(Markdown(text), title=f"[green]{title}[/green]", border_style="green"))


def render_json(data: Any, title: str = "JSON"):
    console.print(
        Panel(json.dumps(data, indent=2, ensure_ascii=False, default=str)[:2000], title=title)
    )


def render_session_info(info: dict, title: str = "Session 信息"):
    table = Table(title=title, show_header=True)
    table.add_column("屬性", style="cyan")
    table.add_column("值", style="green")
    for key, value in info.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        table.add_row(str(key), str(value)[:120])
    console.print(table)


# ── Phase 1: 多輪對話 ────────────────────────────────────────────────────


def run_phase_chat(gateway_url: str, user_id: str, delay: float, verbose: bool) -> tuple[int, int]:
    """Phase 1: 多輪對話 — 測試 afterTurn 寫入。"""
    console.print()
    console.rule(f"[bold]Phase 1: 多輪對話 ({len(CHAT_MESSAGES)} 輪) — afterTurn 寫入[/bold]")
    console.print(f"[yellow]使用者ID:[/yellow] {user_id}")
    console.print(f"[yellow]Gateway:[/yellow] {gateway_url}")
    console.print()

    total = len(CHAT_MESSAGES)
    ok = fail = 0

    for i, base_msg in enumerate(CHAT_MESSAGES, 1):
        msg = chat_message_for_turn(user_id, i, base_msg)
        console.rule(f"[dim]Turn {i}/{total}[/dim]", style="dim")
        console.print(
            Panel(
                msg[:200] + ("..." if len(msg) > 200 else ""),
                title=f"[bold cyan]使用者 [{i}/{total}][/bold cyan]",
                border_style="cyan",
            )
        )
        try:
            data = send_message(gateway_url, msg, user_id)
            reply = extract_reply_text(data)
            render_reply(reply[:500] + ("..." if len(reply) > 500 else ""))
            ok += 1
        except Exception as e:
            console.print(f"[red][ERROR][/red] {e}")
            fail += 1

        if i < total:
            time.sleep(delay)

    console.print()
    console.print(f"[yellow]對話完成:[/yellow] {ok} 成功, {fail} 失敗")

    wait = max(delay * 2, 5)
    console.print(f"[yellow]等待 {wait:.0f}s 讓 afterTurn 處理完成...[/yellow]")
    time.sleep(wait)

    return ok, fail


# ── Phase 2: afterTurn 驗證 ──────────────────────────────────────────────


def run_phase_after_turn(openviking_url: str, user_id: str, verbose: bool) -> tuple[bool, str]:
    """Phase 2: afterTurn 驗證 — 檢查 OV session 內部狀態確認訊息已寫入。
    返回 (success, resolved_session_id)。"""
    console.print()
    console.rule("[bold]Phase 2: afterTurn 驗證 — 檢查 OV session 訊息寫入[/bold]")
    console.print()
    console.print("[dim]驗證點:[/dim]")
    console.print("[dim]- afterTurn 應將每輪訊息寫入 OV session[/dim]")
    console.print("[dim]- session.message_count > 0[/dim]")
    console.print("[dim]- pending_tokens > 0 (消息尚未 commit)[/dim]")
    console.print()

    inspector = OpenVikingInspector(openviking_url)

    # 2.1 健康檢查
    console.print("[bold]2.1 Business Data Platform 健康檢查[/bold]")
    healthy = inspector.health_check()
    check("Business Data Platform 服務可達", healthy)
    if not healthy:
        return False, user_id

    # 2.2 Session 發現: Gateway 可能使用內部 UUID 而非 user_id
    console.print("\n[bold]2.2 Session 發現 & 訊息計數[/bold]")
    resolved_id = inspector.find_session_for_user(user_id)

    if resolved_id and resolved_id != user_id:
        console.print(f"  [yellow]Gateway 使用內部 session_id: {resolved_id} (非 user_id)[/yellow]")

    check("Session 存在", resolved_id is not None, f"resolved_id={resolved_id}")

    if not resolved_id:
        console.print("[red]OV 中沒有找到任何相關 session，無法繼續驗證[/red]")
        return False, user_id

    session_info = inspector.get_session(resolved_id)
    if not session_info:
        console.print("[red]Session 詳情獲取失敗[/red]")
        return False, resolved_id

    if verbose:
        render_session_info(session_info, f"Session: {resolved_id}")

    msg_count = session_info.get("message_count", 0)
    commit_count = session_info.get("commit_count", 0)
    # Gateway 可能在對話過程中 auto-commit，所以 message_count 可能為 0
    # 但 commit_count > 0 表明 afterTurn 已經處理並提交了訊息
    has_activity = msg_count > 0 or commit_count > 0
    check(
        "afterTurn 已處理 (message_count > 0 或 commit_count > 0)",
        has_activity,
        f"message_count={msg_count}, commit_count={commit_count}",
    )

    pending = session_info.get("pending_tokens", 0)
    if commit_count == 0:
        check(
            "pending_tokens > 0 (有待 commit 的內容)",
            pending > 0,
            f"pending_tokens={pending}",
        )
    else:
        console.print(
            f"  [dim]auto-commit 已觸發 (commit_count={commit_count})，"
            f"pending_tokens={pending} 屬正常[/dim]"
        )

    auto_committed = commit_count > 0

    # 2.3 檢查訊息內容: 通過 context API 檢查（相容 auto-commit 場景）
    console.print("\n[bold]2.3 訊息內容抽樣校驗[/bold]")
    ctx = inspector.get_session_context(resolved_id)
    if ctx:
        ctx_messages = ctx.get("messages", [])
        overview = ctx.get("latest_archive_overview", "")
        all_text = flatten_context_text(ctx)

        check(
            "context 返回內容 (messages 或 overview)",
            len(ctx_messages) > 0 or bool(overview),
            f"messages={len(ctx_messages)}, overview_len={len(overview)}",
        )

        sample_text = "張明"
        # 如果已 auto-commit, 資訊可能在 overview 裡而非 messages 中
        check(
            f"內容包含特徵文本「{sample_text}」",
            sample_text in all_text,
            "驗證 afterTurn 寫入的內容與傳送一致",
        )

        sample_text_2 = "PostgreSQL"
        check(
            f"內容包含特徵文本「{sample_text_2}」",
            sample_text_2 in all_text,
            "驗證多輪訊息寫入",
        )

        marker = test_marker(user_id)
        check(
            f"內容包含本輪唯一標記「{marker}」",
            marker in all_text,
            "確保未誤選歷史 session",
        )

        if verbose and ctx.get("stats"):
            console.print(f"  [dim]stats: {ctx['stats']}[/dim]")
    else:
        # 回退到 messages API
        messages = inspector.get_session_messages(resolved_id)
        if messages is not None:
            check("能獲取到 session 訊息列表", True, f"共 {len(messages)} 條訊息")
        else:
            check("能獲取到 session 訊息列表", False, "GET messages 返回 None")

    return True, resolved_id, auto_committed


# ── Phase 3: Commit 驗證 ─────────────────────────────────────────────────


def run_phase_commit(
    openviking_url: str,
    session_id: str,
    verbose: bool,
    auto_committed: bool = False,
) -> bool:
    """Phase 3: Commit 驗證 — 觸發 commit, 檢查歸檔結構和記憶提取。"""
    console.print()
    console.rule("[bold]Phase 3: Commit 驗證 — 觸發 session.commit()[/bold]")
    console.print()
    console.print("[dim]驗證點:[/dim]")
    console.print("[dim]- commit 返回 status=completed/accepted[/dim]")
    console.print("[dim]- 訊息被歸檔或已經歸檔 (auto-commit)[/dim]")
    console.print("[dim]- 提取出記憶 (memories_extracted > 0)[/dim]")
    console.print(f"[dim]- 使用 session_id: {session_id}[/dim]")
    if auto_committed:
        console.print("[yellow]注: Gateway 已觸發 auto-commit, 手動 commit 可能無新內容[/yellow]")
    console.print()

    inspector = OpenVikingInspector(openviking_url)

    # 3.1 執行 commit
    console.print("[bold]3.1 執行 session.commit()[/bold]")
    console.print("[dim]正在等待 commit 完成 (可能需要 1-2 分鐘)...[/dim]")

    commit_result = inspector.commit_session(session_id, wait=True)
    if auto_committed and not commit_result:
        check(
            "commit 返回結果",
            True,
            "auto-commit 已處理, 手動 commit 無新內容屬正常",
        )
    else:
        check("commit 返回結果", commit_result is not None)

    if not commit_result:
        if auto_committed:
            console.print("[yellow]auto-commit 已處理, 手動 commit 無新內容屬正常[/yellow]")
        else:
            console.print("[red]Commit 失敗，無法繼續[/red]")
            return False

    if commit_result:
        if verbose:
            render_json(commit_result, "Commit 結果")

        status = commit_result.get("status", "unknown")
        check(
            "commit status 為 completed 或 accepted",
            status in ("completed", "accepted"),
            f"status={status}",
        )

        archived = commit_result.get("archived", False)
        if auto_committed and not archived:
            check(
                "歸檔狀態合理 (auto-commit 已處理)",
                True,
                "auto-commit 已歸檔, 本次 commit 無新內容",
            )
        else:
            check("archived=true (訊息已歸檔)", archived is True, f"archived={archived}")

        memories = commit_result.get("memories_extracted", {})
        total_mem = sum(memories.values()) if memories else 0
        if auto_committed and total_mem == 0:
            check(
                "記憶提取狀態合理 (auto-commit 已處理)",
                True,
                "auto-commit 已提取記憶",
            )
        else:
            check(
                "memories_extracted > 0 (提取出記憶)",
                total_mem > 0,
                f"total={total_mem}, categories={memories}",
            )

    # 3.2 commit 後 session 狀態
    console.print("\n[bold]3.2 Session 歸檔狀態[/bold]")
    post_session = inspector.get_session(session_id)
    if post_session:
        commit_count = post_session.get("commit_count", 0)
        check(
            "commit_count >= 1",
            commit_count >= 1,
            f"commit_count={commit_count}",
        )

        total_memories = post_session.get("memories_extracted", {})
        total_mem_count = sum(total_memories.values()) if isinstance(total_memories, dict) else 0
        check(
            "累計提取記憶 > 0",
            total_mem_count > 0,
            f"total={total_mem_count}, categories={total_memories}",
        )

        post_pending = post_session.get("pending_tokens", 0)
        console.print(f"  [dim]commit 後 pending_tokens={post_pending}[/dim]")

    # 3.3 檢查歸檔目錄結構
    console.print("\n[bold]3.3 歸檔目錄結構檢查[/bold]")
    ctx_after = inspector.get_session_context(session_id)
    if ctx_after:
        has_summary_archive = bool(ctx_after.get("latest_archive_overview"))
        check(
            "context 返回 latest_archive_overview",
            has_summary_archive,
            f"overview={'有' if has_summary_archive else '無'}",
        )

        if has_summary_archive:
            overview = ctx_after.get("latest_archive_overview", "")
            check(
                "latest_archive_overview 非空 (摘要已生成)",
                len(overview) > 10,
                f"overview 長度={len(overview)} chars",
            )
            if verbose:
                console.print(f"  [dim]overview 前 200 字: {overview[:200]}...[/dim]")
    else:
        check("context 可呼叫", False)

    # 3.4 檢查 estimatedTokens 合理性
    if ctx_after:
        stats = ctx_after.get("stats", {})
        archive_tokens = stats.get("archiveTokens", 0)
        check(
            "archiveTokens > 0 (歸檔 token 計數合理)",
            archive_tokens > 0,
            f"archiveTokens={archive_tokens}",
        )

    return True


# ── Phase 4: Assemble 驗證 ───────────────────────────────────────────────


def run_phase_assemble(
    gateway_url: str,
    openviking_url: str,
    user_id: str,
    session_id: str,
    delay: float,
    verbose: bool,
) -> bool:
    """Phase 4: Assemble 驗證 — 同用戶繼續對話，驗證上下文從 latest archive overview 重組。"""
    console.print()
    console.rule("[bold]Phase 4: Assemble 驗證 — 同用戶繼續對話[/bold]")
    console.print()
    console.print("[dim]驗證點:[/dim]")
    console.print(
        "[dim]- 同用戶對話觸發 assemble(): 從 OV latest_archive_overview + active messages 重組上下文[/dim]"
    )
    console.print("[dim]- 回覆應能引用 Phase 1 中已被歸檔的資訊[/dim]")
    console.print("[dim]- context 應返回 latest_archive_overview (證明 assemble 有資料來源)[/dim]")
    console.print(f"[dim]- OV session_id: {session_id}[/dim]")
    console.print()

    inspector = OpenVikingInspector(openviking_url)

    # 4.1 確認 assemble 的資料來源 (latest_archive_overview) 就緒
    console.print("[bold]4.1 確認 assemble 資料來源[/bold]")
    ctx = inspector.get_session_context(session_id)
    if ctx:
        has_summary_archive = bool(ctx.get("latest_archive_overview"))
        check(
            "context 返回 latest_archive_overview",
            has_summary_archive,
            f"latest_archive_overview={'有' if has_summary_archive else '無'}",
        )
    else:
        check("context 可用", False)

    # 4.2 assemble budget trimming: 用極小 budget 驗證裁剪
    console.print("\n[bold]4.2 Assemble budget trimming[/bold]")
    tiny_ctx = inspector.get_session_context(session_id, token_budget=1)
    if tiny_ctx:
        stats = tiny_ctx.get("stats", {})
        total_archives = stats.get("totalArchives", 0)
        included = stats.get("includedArchives", 0)
        dropped = stats.get("droppedArchives", 0)
        check(
            "budget=1 時 latest_archive_overview 被裁剪",
            included == 0 or dropped > 0,
            f"total={total_archives}, included={included}, dropped={dropped}",
        )
        active_tokens = stats.get("activeTokens", 0)
        console.print(
            f"  [dim]activeTokens={active_tokens}, archiveTokens={stats.get('archiveTokens', 0)}[/dim]"
        )
    else:
        check("tiny budget context 可呼叫", False)

    # 4.3 同用戶繼續對話 — assemble 應重組歸檔上下文
    console.print("\n[bold]4.3 同用戶繼續對話 — 驗證 assemble 重組歸檔內容[/bold]")
    console.print(f"[yellow]使用者ID:[/yellow] {user_id} (同一使用者，繼續對話)")
    console.print()

    total = len(ASSEMBLE_FOLLOWUP_MESSAGES)
    for i, item in enumerate(ASSEMBLE_FOLLOWUP_MESSAGES, 1):
        q = item["question"].format(marker=test_marker(user_id))
        keywords = item["anchor_keywords"]

        console.rule(f"[dim]Assemble 驗證 {i}/{total}[/dim]", style="dim")
        console.print(
            Panel(
                f"{q}\n\n[dim]錨點關鍵詞: {', '.join(keywords)}[/dim]\n[dim]Hook: {item['hook']}[/dim]",
                title=f"[bold cyan]Assemble Q{i}[/bold cyan]",
                border_style="cyan",
            )
        )

        try:
            data = send_message(gateway_url, q, user_id)
            reply = extract_reply_text(data)
            render_reply(reply)

            reply_lower = reply.lower()
            hits = [kw for kw in keywords if kw.lower() in reply_lower]
            hit_rate = len(hits) / len(keywords) if keywords else 0
            check(
                f"Assemble Q{i}: 回覆包含歸檔內容 (命中率 >= 50%)",
                hit_rate >= 0.5,
                f"命中={hits}, 未命中={[k for k in keywords if k not in hits]}, rate={hit_rate:.0%}",
            )
        except Exception as e:
            check(f"Assemble Q{i}: 傳送成功", False, str(e))

        if i < total:
            time.sleep(delay)

    # 4.4 對話後驗證 afterTurn 繼續寫入 (新訊息進入 active messages)
    console.print("\n[bold]4.4 Assemble 後 afterTurn 繼續寫入[/bold]")
    time.sleep(3)
    post_ctx = inspector.get_session_context(session_id)
    if post_ctx:
        post_msg_count = len(post_ctx.get("messages", []))
        check(
            "繼續對話後 active messages 增加",
            post_msg_count > 0,
            f"active messages={post_msg_count}",
        )

    return True


# ── Phase 5: SessionId 一致性驗證 ────────────────────────────────────────


def run_phase_session_id(
    openviking_url: str,
    user_id: str,
    session_id: str,
    verbose: bool,
) -> bool:
    """Phase 5: SessionId 一致性驗證 — 確認整條鏈路使用統一的 sessionId。"""
    console.print()
    console.rule("[bold]Phase 5: SessionId 一致性驗證[/bold]")
    console.print()
    console.print("[dim]驗證點:[/dim]")
    console.print("[dim]- 整條鏈路使用同一個 OV session_id[/dim]")
    console.print("[dim]- 不存在以 sessionKey 變體為 ID 的殘留 session[/dim]")
    console.print("[dim]- context 用 session_id 可查到資料[/dim]")
    console.print(f"[dim]- resolved session_id: {session_id}[/dim]")
    console.print()

    inspector = OpenVikingInspector(openviking_url)

    # 5.1 resolved session_id 可查到
    console.print("[bold]5.1 OV session 可查到[/bold]")
    session = inspector.get_session(session_id)
    check(
        f"OV session (id={session_id[:24]}...) 存在",
        session is not None,
        f"user_id={user_id}",
    )

    # 5.2 不存在以 sessionKey 變體為 ID 的 session
    console.print("\n[bold]5.2 無 sessionKey 殘留[/bold]")
    stale_variants = [
        f"sk:{user_id}",
        f"sessionKey:{user_id}",
        f"key:{user_id}",
    ]
    for variant in stale_variants:
        stale = inspector.get_session(variant)
        is_absent = stale is None or stale.get("message_count", 0) == 0
        check(
            f"不存在殘留 session「{variant}」",
            is_absent,
            "舊 sessionKey 對映應已移除" if is_absent else f"發現殘留: {stale}",
        )

    # 5.3 context 用 session_id 能查到資料
    console.print("\n[bold]5.3 同一 sessionId 查詢歸檔[/bold]")
    ctx = inspector.get_session_context(session_id)
    if ctx:
        has_data = bool(ctx.get("latest_archive_overview")) or len(ctx.get("messages", [])) > 0
        check(
            "context(session_id) 返回資料",
            has_data,
            f"overview={'有' if ctx.get('latest_archive_overview') else '無'}, messages={len(ctx.get('messages', []))}",
        )
    else:
        check("context(session_id) 可呼叫", False)

    # 5.4 驗證 commit 也是用同一 sessionId (session 有 commit_count > 0)
    console.print("\n[bold]5.4 Commit 使用同一 sessionId[/bold]")
    if session:
        cc = session.get("commit_count", 0)
        check(
            "session 有 commit 記錄",
            cc > 0,
            f"commit_count={cc}",
        )

    return True


# ── Phase 6: 新使用者記憶召回 ──────────────────────────────────────────────


def run_phase_recall(gateway_url: str, user_id: str, delay: float, verbose: bool) -> list:
    """Phase 6: 新使用者記憶召回 — 驗證 before_prompt_build auto-recall。"""
    console.print()
    console.rule(f"[bold]Phase 6: 新使用者記憶召回 ({len(RECALL_QUESTIONS)} 輪) — auto-recall[/bold]")
    console.print()
    console.print("[dim]驗證點:[/dim]")
    console.print("[dim]- 新使用者 (新 session) 傳送問題[/dim]")
    console.print("[dim]- before_prompt_build 通過 memory search 注入相關記憶[/dim]")
    console.print("[dim]- 回覆應包含 Phase 1 對話中的關鍵資訊[/dim]")
    console.print()

    verify_user = f"{user_id}-recall-{uuid.uuid4().hex[:4]}"
    console.print(f"[yellow]驗證使用者:[/yellow] {verify_user} (新 session)")
    console.print()

    results = []
    total = len(RECALL_QUESTIONS)

    for i, item in enumerate(RECALL_QUESTIONS, 1):
        q = item["question"].format(marker=test_marker(user_id))
        expected = item["expected_keywords"]

        console.rule(f"[dim]Recall {i}/{total}[/dim]", style="dim")
        console.print(
            Panel(
                f"{q}\n\n[dim]期望關鍵詞: {', '.join(expected)}[/dim]",
                title=f"[bold cyan]Recall Q{i}[/bold cyan]",
                border_style="cyan",
            )
        )

        try:
            data = send_message(gateway_url, q, verify_user)
            reply = extract_reply_text(data)
            render_reply(reply)

            reply_lower = reply.lower()
            hits = [kw for kw in expected if kw.lower() in reply_lower]
            hit_rate = len(hits) / len(expected) if expected else 0
            success = hit_rate >= 0.5

            check(
                f"Recall Q{i}: 關鍵詞命中率 >= 50%",
                success,
                f"命中={hits}, rate={hit_rate:.0%}",
            )
            results.append({"question": q, "hits": hits, "hit_rate": hit_rate, "success": success})
        except Exception as e:
            check(f"Recall Q{i}: 傳送成功", False, str(e))
            results.append({"question": q, "hits": [], "hit_rate": 0, "success": False})

        if i < total:
            time.sleep(delay)

    return results


# ── 完整測試 ──────────────────────────────────────────────────────────────


def run_full_test(gateway_url: str, openviking_url: str, user_id: str, delay: float, verbose: bool):
    console.print()
    console.print(
        Panel.fit(
            f"[bold]OpenClaw 記憶鏈路完整測試[/bold]\n\n"
            f"Gateway: {gateway_url}\n"
            f"Business Data Platform: {openviking_url}\n"
            f"User ID: {user_id}\n"
            f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            title="測試資訊",
        )
    )

    # Phase 1: Chat
    chat_ok, chat_fail = run_phase_chat(gateway_url, user_id, delay, verbose)

    # Phase 2: afterTurn — 返回實際的 OV session_id
    _, resolved_session_id, auto_committed = run_phase_after_turn(openviking_url, user_id, verbose)

    # Phase 3: Commit
    run_phase_commit(openviking_url, resolved_session_id, verbose, auto_committed)

    console.print("\n[yellow]等待 10s 讓記憶提取完成...[/yellow]")
    time.sleep(10)

    # Phase 4: Assemble (同用戶繼續)
    run_phase_assemble(gateway_url, openviking_url, user_id, resolved_session_id, delay, verbose)

    # Phase 5: SessionId 一致性
    run_phase_session_id(openviking_url, user_id, resolved_session_id, verbose)

    # Phase 6: 新使用者召回
    run_phase_recall(gateway_url, user_id, delay, verbose)

    # ── 彙總報告 ──────────────────────────────────────────────────────────
    console.print()
    console.rule("[bold]測試報告[/bold]")

    passed = sum(1 for a in assertions if a["ok"])
    failed = sum(1 for a in assertions if not a["ok"])
    total = len(assertions)

    table = Table(title=f"斷言結果: {passed}/{total} 通過")
    table.add_column("#", style="bold", width=4)
    table.add_column("狀態", width=6)
    table.add_column("斷言", max_width=60)
    table.add_column("詳情", style="dim", max_width=50)

    for i, a in enumerate(assertions, 1):
        status = "[green]PASS[/green]" if a["ok"] else "[red]FAIL[/red]"
        table.add_row(str(i), status, a["label"][:60], (a.get("detail") or "")[:50])

    console.print(table)

    # 按階段彙總
    tree = Tree(f"[bold]通過: {passed}/{total}, 失敗: {failed}[/bold]")
    tree.add(f"Phase 1: 多輪對話 — {chat_ok} 成功 / {chat_fail} 失敗")

    fail_list = [a for a in assertions if not a["ok"]]
    if fail_list:
        fail_branch = tree.add(f"[red]失敗斷言 ({len(fail_list)})[/red]")
        for a in fail_list:
            fail_branch.add(f"[red]FAIL[/red] {a['label']}")

    console.print(tree)

    if failed == 0:
        console.print("\n[green bold]全部通過！端到端鏈路驗證成功。[/green bold]")
    else:
        console.print(f"\n[red bold]有 {failed} 個斷言失敗，請檢查上方詳情。[/red bold]")


# ── 入口 ───────────────────────────────────────────────────────────────────


def main():
    global AGENT_ID
    parser = argparse.ArgumentParser(
        description="OpenClaw 記憶鏈路完整測試",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python test-memory-chain.py
    python test-memory-chain.py --gateway http://127.0.0.1:18790
    python test-memory-chain.py --phase chat
    python test-memory-chain.py --phase afterTurn --user-id test-chain-abc123
    python test-memory-chain.py --phase assemble --user-id test-chain-abc123
    python test-memory-chain.py --verbose
        """,
    )
    parser.add_argument(
        "--gateway",
        default=DEFAULT_GATEWAY,
        help=f"OpenClaw Gateway 地址 (預設: {DEFAULT_GATEWAY})",
    )
    parser.add_argument(
        "--openviking",
        default=DEFAULT_OPENVIKING,
        help=f"Business Data Platform 服務地址 (預設: {DEFAULT_OPENVIKING})",
    )
    parser.add_argument(
        "--user-id",
        default=USER_ID,
        help="測試使用者ID (預設: 隨機生成)",
    )
    parser.add_argument(
        "--phase",
        choices=["all", "chat", "afterTurn", "commit", "assemble", "session-id", "recall"],
        default="all",
        help="執行階段 (預設: all)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="輪次間等待秒數 (預設: 2)",
    )
    parser.add_argument(
        "--token",
        default="",
        help="Gateway auth token (預設: 自動從 openclaw.json 發現)",
    )
    parser.add_argument(
        "--agent-id",
        default=AGENT_ID,
        help=f"Business Data Platform agent ID (預設: {AGENT_ID})",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="詳細輸出",
    )
    args = parser.parse_args()

    gateway_url = args.gateway.rstrip("/")
    openviking_url = args.openviking.rstrip("/")
    user_id = args.user_id

    token = args.token or discover_gateway_token()
    set_gateway_token(token)

    AGENT_ID = args.agent_id

    console.print("[bold]OpenClaw 記憶鏈路測試[/bold]")
    console.print(f"[yellow]Gateway:[/yellow] {gateway_url}")
    console.print(f"[yellow]Business Data Platform:[/yellow] {openviking_url}")
    console.print(f"[yellow]User ID:[/yellow] {user_id}")

    if args.phase == "all":
        run_full_test(gateway_url, openviking_url, user_id, args.delay, args.verbose)
    elif args.phase == "chat":
        run_phase_chat(gateway_url, user_id, args.delay, args.verbose)
    elif args.phase == "afterTurn":
        _, _, _ = run_phase_after_turn(openviking_url, user_id, args.verbose)
    elif args.phase == "commit":
        inspector = OpenVikingInspector(openviking_url, agent_id=AGENT_ID)
        sid = inspector.find_session_for_user(user_id) or user_id
        session_info = inspector.get_session(sid)
        ac = (session_info.get("commit_count", 0) > 0) if session_info else False
        run_phase_commit(openviking_url, sid, args.verbose, ac)
    elif args.phase == "assemble":
        inspector = OpenVikingInspector(openviking_url, agent_id=AGENT_ID)
        sid = inspector.find_session_for_user(user_id) or user_id
        run_phase_assemble(gateway_url, openviking_url, user_id, sid, args.delay, args.verbose)
    elif args.phase == "session-id":
        inspector = OpenVikingInspector(openviking_url, agent_id=AGENT_ID)
        sid = inspector.find_session_for_user(user_id) or user_id
        run_phase_session_id(openviking_url, user_id, sid, args.verbose)
    elif args.phase == "recall":
        run_phase_recall(gateway_url, user_id, args.delay, args.verbose)

    # 列印最終斷言統計
    if assertions:
        passed = sum(1 for a in assertions if a["ok"])
        failed = sum(1 for a in assertions if not a["ok"])
        total = len(assertions)
        console.print(f"\n[yellow]斷言統計: {passed}/{total} 通過[/yellow]")
        if failed:
            sys.exit(1)

    console.print("\n[yellow]測試結束。[/yellow]")


if __name__ == "__main__":
    main()
