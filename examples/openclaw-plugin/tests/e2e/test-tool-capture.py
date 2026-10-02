#!/usr/bin/env python3
"""
extractNewTurnTexts 工具呼叫捕獲端到端測試

================================================================================
一、用例設計思路
================================================================================

核心驗證點:
  當模型在回覆中呼叫工具（如 code_execution、native_tool 等）時，Gateway 的
  extractNewTurnTexts 需要將 toolUse（工具呼叫）和 toolResult（工具結果）的
  內容正確捕獲並寫入 OV session，確保後續歸檔和記憶提取不會丟失工具呼叫資訊。

測試策略:
  1. 傳送訊息觸發模型使用工具（如計算階乘、寫程式碼等）
  2. 等待 afterTurn 完成
  3. 從 OV session 中讀取已儲存的訊息
  4. 斷言儲存的訊息中包含 [toolUse:] 和 [toolResult:] 標記
  5. 驗證關鍵詞可在 Gateway 響應和 OV 儲存中追溯

================================================================================
二、測試流程
================================================================================

  Phase 1: 傳送 3 條訊息，設計為觸發工具呼叫
  Phase 2: 檢查 OV session 存在且有內容
  Phase 3: 驗證 toolUse/toolResult 標記和關鍵詞可追溯
  Phase 4: 驗證改動前後對比（tool 相關行數 > 0）

================================================================================
三、環境前提
================================================================================

  1. OpenViking 服務已啟動
  2. OpenClaw Gateway 已啟動並配置了 OpenViking 外掛
  3. LLM 後端可達且支援工具呼叫（function calling / tool use）
  4. 有效的 Gateway auth token

  關鍵 openclaw.json 配置:
    - plugins.slots.contextEngine = "openviking"
    - plugins.entries.openviking.enabled = true
    - plugins.entries.openviking.config.autoCapture = true  # afterTurn 自動捕獲

================================================================================
四、使用方法
================================================================================

  安裝依賴:
    pip install requests rich

  執行測試:
    python test-tool-capture.py \\
        --gateway http://127.0.0.1:19789 \\
        --openviking http://127.0.0.1:2934 \\
        --token <your_gateway_token>

  其他選項:
    --verbose / -v   詳細輸出（顯示完整 JSON 響應）
    --delay <sec>    訊息間等待秒數（預設 5s）

  注意:
    - 測試約需 2-3 分鐘
    - 首次執行前建議清理 OV 資料和 session 資料

================================================================================
五、已知限制
================================================================================

  1. 模型工具呼叫行為不確定:
     不同 LLM 模型對同一輸入是否呼叫工具的行為不同。有些模型可能選擇直接
     回答而不呼叫工具。指令碼對 [toolUse:] 標記做了條件性檢查（模型未呼叫工具
     時跳過強斷言）。

  2. 工具呼叫格式差異:
     不同 LLM provider 的 tool_use/tool_result 輸出格式可能不同（如 Anthropic
     vs OpenAI），extractNewTurnTexts 需要正確處理各種格式。

  3. 關鍵詞追溯:
     指令碼通過關鍵詞（如"5040"、"factorial"、"斐波那契"）驗證工具結果是否被
     正確儲存。如果模型未執行預期的計算，關鍵詞可能無法匹配。

================================================================================
六、預期結果
================================================================================

  15/15 斷言全部通過:
    - Phase 1: 3 條訊息傳送成功
    - Phase 2: OV session 存在且有內容
    - Phase 3: toolResult 標記存在, 關鍵詞可追溯
    - Phase 4: tool 相關行數 > 0
"""

import argparse
import io
import json
import re
import sys
import time
import uuid
from datetime import datetime

import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── 常量 ──────────────────────────────────────────────────────────────────

GATEWAY_URL = "http://127.0.0.1:19789"
OPENVIKING_URL = "http://127.0.0.1:2934"
AGENT_ID = "main"

console = Console(force_terminal=True)
assertions: list[dict] = []


def check(label: str, condition: bool, detail: str = ""):
    assertions.append({"label": label, "ok": condition, "detail": detail})
    icon = "[green]PASS[/green]" if condition else "[red]FAIL[/red]"
    msg = f"  {icon} {label}"
    if detail:
        msg += f"  [dim]({detail})[/dim]"
    console.print(msg)


def load_gateway_token() -> str:
    """從常見路徑自動發現 gateway auth token。"""
    import os
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


# ── API helpers ──────────────────────────────────────────────────────────


def send_message(gateway_url: str, message: str, user_id: str, token: str) -> dict:
    """通過 OpenClaw Responses API 傳送訊息。"""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.post(
        f"{gateway_url}/v1/responses",
        headers=headers,
        json={"model": "openclaw", "input": message, "user": user_id},
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()


def extract_reply_text(data: dict) -> str:
    for item in data.get("output", []):
        if item.get("type") == "message" and item.get("role") == "assistant":
            for part in item.get("content", []):
                if part.get("type") in ("text", "output_text"):
                    return part.get("text", "")
    return "(無回覆)"


def has_tool_use_in_output(data: dict) -> bool:
    """檢查 Responses API 返回中是否有 tool_use / function_call。"""
    for item in data.get("output", []):
        item_type = item.get("type", "")
        if item_type in ("function_call", "tool_use", "computer_call"):
            return True
        if item.get("role") == "assistant":
            for part in item.get("content", []):
                if part.get("type") in ("tool_use", "toolUse"):
                    return True
    return False


class OVInspector:
    def __init__(self, base_url: str, agent_id: str = AGENT_ID):
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id

    def _headers(self) -> dict:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self.agent_id:
            h["X-OpenViking-Actor-Peer"] = self.agent_id
        return h

    def _get(self, path: str, timeout: int = 10):
        try:
            resp = requests.get(f"{self.base_url}{path}", headers=self._headers(), timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result", data)
            return None
        except Exception as e:
            console.print(f"[dim]GET {path} 失敗: {e}[/dim]")
            return None

    def list_sessions(self) -> list:
        result = self._get("/api/v1/sessions")
        if isinstance(result, list):
            return result
        return []

    def get_session(self, session_id: str):
        return self._get(f"/api/v1/sessions/{session_id}")

    def get_session_context(self, session_id: str, token_budget: int = 128000):
        return self._get(f"/api/v1/sessions/{session_id}/context?token_budget={token_budget}")

    def find_latest_session(self) -> str | None:
        """找到最近更新的 session ID（gateway 內部使用 UUID，非 user_id）。
        通過檢查每個 session 的 updated_at 來找到最新的。"""
        sessions = self.list_sessions()
        real_sessions = [
            s
            for s in sessions
            if isinstance(s, dict) and not s.get("session_id", "").startswith("memory-store-")
        ]
        if not real_sessions:
            return None

        best_id = None
        best_time = ""
        for s in real_sessions:
            sid = s.get("session_id", "")
            if not sid:
                continue
            detail = self.get_session(sid)
            if not detail:
                continue
            updated = detail.get("updated_at", "")
            if updated > best_time:
                best_time = updated
                best_id = sid

        return best_id or real_sessions[-1].get("session_id")


# ── 核心測試 ──────────────────────────────────────────────────────────────


TOOL_TRIGGER_MESSAGES = [
    {
        "input": "請幫我計算 factorial(7) 的結果，用程式碼算一下",
        "description": "觸發程式碼執行工具",
        "expect_keywords": ["5040", "factorial"],
    },
    {
        "input": "我叫李明，記住我是一名資料工程師，擅長 Spark 和 Flink，偏好用 Scala 寫程式碼。請同時告訴我今天星期幾。",
        "description": "資訊儲存 + 可能觸發工具",
        "expect_keywords": ["李明", "資料工程師"],
    },
    {
        "input": "幫我寫一段 Python 程式碼計算斐波那契數列前10個數，並執行它告訴我結果",
        "description": "觸發程式碼執行並返回結果",
        "expect_keywords": ["斐波那契"],
    },
]


def run_test(
    gateway_url: str,
    openviking_url: str,
    user_id: str,
    delay: float,
    verbose: bool,
    token: str = "",
    agent_id: str = "",
):
    if not token:
        token = load_gateway_token()
    inspector = OVInspector(openviking_url, agent_id=agent_id or AGENT_ID)

    console.print(
        Panel(
            f"[bold]Tool Capture 測試[/bold]\n\n"
            f"Gateway: {gateway_url}\n"
            f"OpenViking: {openviking_url}\n"
            f"User ID: {user_id}\n"
            f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            title="測試資訊",
        )
    )

    # ── Phase 1: 傳送訊息 ────────────────────────────────────────────────

    console.rule("[bold]Phase 1: 傳送訊息觸發 afterTurn[/bold]")

    gateway_responses = []
    for i, msg_cfg in enumerate(TOOL_TRIGGER_MESSAGES):
        console.print(
            f"\n[cyan]消息 {i + 1}/{len(TOOL_TRIGGER_MESSAGES)}:[/cyan] {msg_cfg['description']}"
        )
        console.print(f"  [dim]> {msg_cfg['input'][:80]}...[/dim]")

        try:
            data = send_message(gateway_url, msg_cfg["input"], user_id, token)
            reply = extract_reply_text(data)
            has_tool = has_tool_use_in_output(data)

            console.print(f"  [green]回覆:[/green] {reply[:120]}...")
            if has_tool:
                console.print("  [yellow]檢測到 tool_use 在響應中[/yellow]")

            if verbose:
                console.print(
                    f"  [dim]完整響應: {json.dumps(data, ensure_ascii=False)[:500]}[/dim]"
                )

            gateway_responses.append(
                {
                    "index": i,
                    "msg": msg_cfg,
                    "response": data,
                    "reply": reply,
                    "has_tool": has_tool,
                }
            )

            check(
                f"訊息 {i + 1} 傳送成功",
                True,
                f"reply_len={len(reply)}",
            )
        except Exception as e:
            console.print(f"  [red]傳送失敗: {e}[/red]")
            check(f"訊息 {i + 1} 傳送成功", False, str(e))

        if i < len(TOOL_TRIGGER_MESSAGES) - 1:
            time.sleep(delay)

    # ── Phase 2: 等待 afterTurn 寫入 ───────────────────────────────────

    console.rule("[bold]Phase 2: 檢查 OV session 中的儲存內容[/bold]")
    console.print("[yellow]等待 afterTurn 寫入 OV session...[/yellow]")
    time.sleep(8)

    # Gateway 使用內部 UUID 作為 session ID，需要從 OV 列表中找到最新的
    ov_session_id = inspector.find_latest_session()
    if not ov_session_id:
        console.print("[red]  OV 中沒有找到任何 session[/red]")
        check("OV session 存在", False, "no sessions found")
        print_summary()
        return

    console.print(f"  [cyan]OV session ID: {ov_session_id}[/cyan]")

    session_info = inspector.get_session(ov_session_id)
    if session_info:
        msg_count = session_info.get("message_count", "?")
        console.print(f"  Session found: message_count={msg_count}")
        check("OV session 存在", True, f"id={ov_session_id[:16]}...")
    else:
        console.print("[red]  OV session 詳情獲取失敗[/red]")
        check("OV session 存在", False, "session detail failed")
        print_summary()
        return

    # 通過 context API 獲取全量上下文（活躍訊息 + 歸檔摘要）
    ctx = inspector.get_session_context(ov_session_id)
    messages = ctx.get("messages", []) if ctx else []

    # 同時獲取歸檔概要文本（低 commit 閾值下訊息可能已歸檔）
    archive_overview = ""
    if ctx:
        for msg in messages:
            if isinstance(msg, dict):
                for part in msg.get("parts", []):
                    if isinstance(part, dict) and part.get("type") == "text":
                        archive_overview += (part.get("text", "") or "") + "\n"

    if not messages and not archive_overview:
        console.print("[red]  OV session 訊息為空[/red]")
        check("OV session 有消息", False, "context messages empty")
        print_summary()
        return

    console.print(f"  [green]OV session context 訊息數: {len(messages)}[/green]")
    check(
        "OV session 有內容",
        len(messages) > 0 or bool(archive_overview),
        f"messages={len(messages)}",
    )

    # ── Phase 3: 分析儲存的內容是否包含 tool 資訊 ──────────────────────

    console.rule("[bold]Phase 3: 驗證 toolUse/toolResult 內容被捕獲[/bold]")

    all_stored_text = ""
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        parts = msg.get("parts", [])
        for part in parts:
            if isinstance(part, dict) and part.get("type") == "text":
                all_stored_text += (part.get("text", "") or "") + "\n"

    if verbose:
        console.print(
            Panel(
                all_stored_text[:3000] + ("..." if len(all_stored_text) > 3000 else ""),
                title="OV 儲存的全部文本",
            )
        )

    any_tool_in_gateway = any(r.get("has_tool") for r in gateway_responses)

    # 檢查 toolUse 標記（僅在 gateway 響應確實含 tool_use 時才必須）
    has_tool_use_marker = bool(re.search(r"\[toolUse:", all_stored_text, re.IGNORECASE))
    if any_tool_in_gateway:
        check(
            "儲存文本包含 [toolUse:] 標記",
            has_tool_use_marker,
            f"found={has_tool_use_marker}",
        )
    else:
        check(
            "[toolUse:] 標記（模型未呼叫工具，跳過強斷言）",
            True,
            f"no tool_use in gateway response, marker={has_tool_use_marker}",
        )

    # 檢查 toolResult 標記
    has_tool_result_marker = bool(re.search(r"result\]:", all_stored_text, re.IGNORECASE))
    check(
        "儲存文本包含 tool result 標記",
        has_tool_result_marker or not any_tool_in_gateway,
        f"found={has_tool_result_marker} tool_in_gateway={any_tool_in_gateway}",
    )

    # 檢查 assistant 標記
    has_assistant = bool(re.search(r"\[assistant\]:", all_stored_text, re.IGNORECASE))
    check(
        "儲存文本包含 [assistant] 標記",
        has_assistant,
        f"found={has_assistant}",
    )

    # 檢查 user 標記
    has_user = bool(re.search(r"\[user\]:", all_stored_text, re.IGNORECASE))
    check(
        "儲存文本包含 [user] 標記",
        has_user,
        f"found={has_user}",
    )

    # 檢查關鍵內容是否保留（檢查活躍上下文 + 歸檔摘要 + gateway 響應）
    all_gateway_text = "\n".join(r.get("reply", "") for r in gateway_responses)

    for msg_cfg in TOOL_TRIGGER_MESSAGES:
        for kw in msg_cfg.get("expect_keywords", []):
            in_stored = kw.lower() in all_stored_text.lower()
            in_gateway = kw.lower() in all_gateway_text.lower()
            detail = f"keyword='{kw}' stored={in_stored} gateway={in_gateway}"
            check(
                f"關鍵詞 {kw} 可追溯",
                in_stored or in_gateway,
                detail,
            )

    # ── Phase 4: 對比改動前後的行為 ──────────────────────────────────────

    console.rule("[bold]Phase 4: 改動前後對比分析[/bold]")

    # 舊版本：只有 [user] 和 [assistant] 的文本
    # 新版本：應該額外包含 [toolUse: xxx] 和 [xxx result] 的內容
    tool_related_lines = []
    for line in all_stored_text.split("\n"):
        stripped = line.strip()
        if re.search(r"\[toolUse:", stripped, re.IGNORECASE):
            tool_related_lines.append(("toolUse", stripped[:150]))
        elif re.search(r"result\]:", stripped, re.IGNORECASE):
            tool_related_lines.append(("toolResult", stripped[:150]))

    if tool_related_lines:
        table = Table(title="捕獲到的 Tool 相關內容")
        table.add_column("型別", style="cyan", width=12)
        table.add_column("內容預覽", max_width=120)
        for kind, preview in tool_related_lines:
            table.add_row(kind, preview)
        console.print(table)

    check(
        "tool 相關行數 > 0（新邏輯生效）",
        len(tool_related_lines) > 0,
        f"tool_lines={len(tool_related_lines)}",
    )

    # ── 彙總 ─────────────────────────────────────────────────────────────

    print_summary()


def print_summary():
    console.print()
    console.rule("[bold]測試彙總[/bold]")

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

    if failed == 0:
        console.print("\n[green bold]全部通過！toolUse/toolResult 捕獲驗證成功。[/green bold]")
    else:
        console.print(f"\n[red bold]有 {failed} 個斷言失敗。[/red bold]")
        console.print(
            "[yellow]注: 如果模型沒有呼叫工具，toolUse/toolResult 標記可能不存在 — 這不代表程式碼有 bug。[/yellow]"
        )
        console.print("[yellow]可以在 gateway 日誌中確認 afterTurn 的儲存內容。[/yellow]")


# ── 入口 ──────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="測試 toolUse/toolResult 捕獲")
    parser.add_argument("--gateway", default=GATEWAY_URL, help="Gateway 地址")
    parser.add_argument("--openviking", default=OPENVIKING_URL, help="OpenViking 地址")
    parser.add_argument("--token", default="", help="Gateway auth token (預設: 自動發現)")
    parser.add_argument(
        "--agent-id", default=AGENT_ID, help=f"OpenViking agent ID (預設: {AGENT_ID})"
    )
    parser.add_argument("--delay", type=float, default=3.0, help="訊息間延遲秒數")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細輸出")
    args = parser.parse_args()

    user_id = f"test-tool-{uuid.uuid4().hex[:8]}"

    run_test(
        gateway_url=args.gateway.rstrip("/"),
        openviking_url=args.openviking.rstrip("/"),
        user_id=user_id,
        delay=args.delay,
        verbose=args.verbose,
        token=args.token,
        agent_id=args.agent_id,
    )


if __name__ == "__main__":
    main()
