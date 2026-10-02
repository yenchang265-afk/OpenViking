#!/usr/bin/env python3
"""
Business Data Platform 記憶演示指令碼 — 工具呼叫和Skill呼叫記憶測試

測試 assistant 呼叫工具和使用 skill 的記憶是否被正確提取和召回
"""

import argparse
import time

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import openviking as ov
try:
    from openviking_live_auth import API_KEY_HELP, resolve_api_key
except ModuleNotFoundError:  # pytest/package import path
    from tests.integration.openviking_live_auth import API_KEY_HELP, resolve_api_key

# ── 常量 ───────────────────────────────────────────────────────────────────

DISPLAY_NAME = "測試使用者"
DEFAULT_URL = "http://localhost:1934"
PANEL_WIDTH = 78
DEFAULT_API_KEY = None
DEFAULT_SESSION_ID = "tool-skill-memory-test"


console = Console()

# ── 對話資料 (工具呼叫 + Skill呼叫) ─────────────────────────────────────────
# 模擬 assistant 呼叫工具（read/write_file/bash/Glob）讀取 SKILL.md 等檔案
# 注意：tool_calls 需要傳入真正的工具呼叫資訊

CONVERSATION = [
    # ===== Skill 呼叫：assistant 呼叫 read 工具讀取 SKILL.md =====
    {
        "user": "幫我建立一個PPT簡報，主題是季度工作報告。",
        "assistant": "好的，我先讀取一下 ppt skill 的 SKILL.md 瞭解如何建立PPT。",
        "tool_calls": [
            {
                "tool_name": "Read",
                "tool_uri": "tools:Read",
                "input": {"file_path": "/skills/ppt/SKILL.md"},
            }
        ],
    },
    {
        "user": "PPT需要包含三個部分：業績回顧、業務分析和下季度計劃。",
        "assistant": "好的，我根據 SKILL.md 的指引來建立這三個部分的PPT。",
        "tool_calls": [
            {
                "tool_name": "Read",
                "tool_uri": "tools:Read",
                "input": {"file_path": "/skills/ppt/SKILL.md"},
            }
        ],
    },
    {
        "user": "把PPT的模板換成藍色主題。",
        "assistant": "好的，我來修改PPT模板為藍色主題。",
        "tool_calls": [
            {
                "tool_name": "write_file",
                "tool_uri": "tools:write_file",
                "input": {"path": "template.pptx", "content": "藍色主題模板"},
            }
        ],
    },
    # ===== 工具呼叫：write_file =====
    {
        "user": "幫我寫一個Python函式，計算斐波那契數列。",
        "assistant": "我來寫一個計算斐波那契數列的函式並儲存到檔案。",
        "tool_calls": [
            {
                "tool_name": "write_file",
                "tool_uri": "tools:write_file",
                "input": {
                    "path": "fibonacci.py",
                    "content": "def fib(n):\n    if n <= 1:\n        return n\n    return fib(n-1) + fib(n-2)\nprint(fib(10))",
                },
            }
        ],
    },
    # ===== 工具呼叫：bash =====
    {
        "user": "執行一下這個Python檔案，看看結果對不對。",
        "assistant": "我來執行這個檔案。",
        "tool_calls": [
            {
                "tool_name": "Bash",
                "tool_uri": "tools:Bash",
                "input": {"command": "python fibonacci.py"},
            }
        ],
    },
    # ===== Skill 呼叫：PDF =====
    {
        "user": "幫我把這份PDF檔案提取文字內容。",
        "assistant": "好的，我先讀取一下 pdf skill 的 SKILL.md。",
        "tool_calls": [
            {
                "tool_name": "Read",
                "tool_uri": "tools:Read",
                "input": {"file_path": "/skills/pdf/SKILL.md"},
            }
        ],
    },
    {
        "user": "PDF有多少頁？",
        "assistant": "這份PDF有15頁。",
    },
    # ===== 工具呼叫：Glob =====
    {
        "user": "搜尋一下專案裡有哪些Python檔案。",
        "assistant": "我來搜尋專案裡的Python檔案。",
        "tool_calls": [
            {"tool_name": "Glob", "tool_uri": "tools:Glob", "input": {"pattern": "**/*.py"}}
        ],
    },
    # ===== 工具呼叫：Read =====
    {
        "user": "檢視一下這個檔案的內容。",
        "assistant": "好的，我讀取一下這個檔案。",
        "tool_calls": [
            {"tool_name": "Read", "tool_uri": "tools:Read", "input": {"file_path": "main.py"}}
        ],
    },
    # ===== Skill 呼叫：Email =====
    {
        "user": "幫我寫一封郵件給客戶，主題是專案進度彙報。",
        "assistant": "好的，我先讀取一下 email skill 的 SKILL.md 瞭解郵件格式。",
        "tool_calls": [
            {
                "tool_name": "Read",
                "tool_uri": "tools:Read",
                "input": {"file_path": "/skills/email/SKILL.md"},
            }
        ],
    },
    {
        "user": "郵件內容要包含本週完成的工作和下週計劃。",
        "assistant": "好的，我來編寫郵件內容。",
    },
]

# ── 驗證查詢 ──────────────────────────────────────────────────────────────

VERIFY_QUERIES = [
    {
        "query": "建立了什麼PPT",
        "expected_keywords": ["PPT", "季度工作", "業績回顧", "業務分析", "下季度計劃", "藍色主題"],
    },
    {
        "query": "執行了什麼程式碼",
        "expected_keywords": ["Python", "斐波那契", "fibonacci", "函式"],
    },
    {
        "query": "處理了什麼PDF",
        "expected_keywords": ["PDF", "文字", "15頁"],
    },
    {
        "query": "搜尋了什麼檔案",
        "expected_keywords": ["Python", "文件", "搜索"],
    },
    {
        "query": "寫了什麼郵件",
        "expected_keywords": ["郵件", "客戶", "專案進度", "工作", "計劃"],
    },
    {
        "query": "使用了哪些skill",
        "expected_keywords": ["ppt", "pdf", "email"],
    },
    {
        "query": "使用了哪些工具",
        "expected_keywords": ["Python", "檔案", "搜尋", "讀取"],
    },
]

# ── 輔助函式 ──────────────────────────────────────────────────────────────


def run_ingest(client: ov.SyncHTTPClient, session_id: str, wait_seconds: float):
    """寫入對話並提交"""
    console.print()
    console.rule(f"[bold]Phase 1: 寫入對話 — {DISPLAY_NAME} ({len(CONVERSATION)} 輪)[/bold]")

    session = client.create_session()
    session_id = session.get("session_id")
    console.print(f"  Session: [bold cyan]{session_id}[/bold cyan]")
    console.print()

    total = len(CONVERSATION)
    for i, turn in enumerate(CONVERSATION, 1):
        tool_calls = turn.get("tool_calls", [])
        if tool_calls:
            tool_info = f" [blue](tools: {[tc['tool_name'] for tc in tool_calls]})[/blue]"
        else:
            tool_info = ""
        console.print(f"  [dim][{i}/{total}][/dim] 添加 user + assistant 消息{tool_info}...")

        # 添加 user 消息
        client.add_message(session_id, role="user", parts=[{"type": "text", "text": turn["user"]}])

        # 添加 assistant 消息，包含 tool_calls
        assistant_parts = [{"type": "text", "text": turn["assistant"]}]
        for tc in tool_calls:
            tool_part = {
                "type": "tool",
                "tool_name": tc["tool_name"],
                "tool_uri": tc.get("tool_uri", f"tools:{tc['tool_name']}"),
                "tool_input": tc.get("input", {}),
                "tool_status": "completed",
            }
            assistant_parts.append(tool_part)
            print(f"  [DEBUG] Adding tool part: {tool_part}")
        result = client.add_message(session_id, role="assistant", parts=assistant_parts)
        print(f"  [DEBUG] add_message result: {result}")

    console.print()
    console.print(f"  共新增 [bold]{total * 2}[/bold] 條訊息")

    console.print()
    console.print("  [yellow]提交 Session（觸發記憶抽取）...[/yellow]")
    commit_result = client.commit_session(session_id)
    task_id = commit_result.get("task_id")
    console.print(f"  Commit 結果: {commit_result}")

    if task_id:
        now = time.time()
        console.print(f"  [yellow]等待記憶提取完成 (task_id={task_id})...[/yellow]")
        while True:
            task = client.get_task(task_id)
            if not task or task.get("status") in ("completed", "failed"):
                break
            time.sleep(1)
        elapsed = time.time() - now
        status = task.get("status", "unknown") if task else "not found"
        console.print(f"  [green]任務 {status}，耗時 {elapsed:.2f}s[/green]")
        console.print(f"  Task 詳情: {task}")

    console.print("  [yellow]等待向量化完成...[/yellow]")
    client.wait_processed()

    if wait_seconds > 0:
        console.print(f"  [dim]額外等待 {wait_seconds:.0f}s...[/dim]")
        time.sleep(wait_seconds)

    session_info = client.get_session(session_id)
    console.print(f"  Session 詳情: {session_info}")

    return session_id


def run_verify(client: ov.SyncHTTPClient):
    """驗證記憶召回"""
    console.print()
    console.rule(
        f"[bold]Phase 2: 驗證記憶召回 — {DISPLAY_NAME} ({len(VERIFY_QUERIES)} 條查詢)[/bold]"
    )

    results_table = Table(
        title=f"記憶召回驗證 — {DISPLAY_NAME}",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold",
    )
    results_table.add_column("#", style="bold", width=4)
    results_table.add_column("查詢", style="cyan", max_width=30)
    results_table.add_column("召回數", justify="center", width=8)
    results_table.add_column("命中關鍵詞", style="green")

    total = len(VERIFY_QUERIES)
    for i, item in enumerate(VERIFY_QUERIES, 1):
        query = item["query"]
        expected = item["expected_keywords"]

        console.print(f"\n  [dim][{i}/{total}][/dim] 搜索: [cyan]{query}[/cyan]")
        console.print(f"  [dim]期望關鍵詞: {', '.join(expected)}[/dim]")

        try:
            results = client.find(query, limit=5)

            recall_texts = []
            count = 0
            if hasattr(results, "memories") and results.memories:
                for m in results.memories:
                    text = getattr(m, "content", "") or getattr(m, "text", "") or str(m)
                    print(f"  [DEBUG] memory text: {repr(text)}")
                    recall_texts.append(text)
                    uri = getattr(m, "uri", "")
                    score = getattr(m, "score", 0)
                    console.print(f"    [green]Memory:[/green] {uri} (score: {score:.4f})")
                    console.print(
                        f"    [dim]{text[:120]}...[/dim]"
                        if len(text) > 120
                        else f"    [dim]{text}[/dim]"
                    )
                count += len(results.memories)

            if hasattr(results, "resources") and results.resources:
                for r in results.resources:
                    text = getattr(r, "content", "") or getattr(r, "text", "") or str(r)
                    print(f"  [DEBUG] resource text: {repr(text)}")
                    recall_texts.append(text)
                    console.print(f"    [blue]Resource:[/blue] {r.uri} (score: {r.score:.4f})")
                count += len(results.resources)

            if hasattr(results, "skills") and results.skills:
                count += len(results.skills)

            all_text = " ".join(recall_texts)
            hits = [kw for kw in expected if kw in all_text]
            # 格式化關鍵詞，命中的綠色，未命中的紅色
            formatted_keywords = []
            for kw in expected:
                if kw in hits:
                    formatted_keywords.append(f"[green]{kw}[/green]")
                else:
                    formatted_keywords.append(f"[red]{kw}[/red]")

            keyword_str = ", ".join(formatted_keywords)

            results_table.add_row(str(i), query, str(count), keyword_str)

        except Exception as e:
            console.print(f"    [red]ERROR: {e}[/red]")
            results_table.add_row(str(i), query, "[red]ERR[/red]", str(e)[:40])

    console.print()
    console.print(results_table)


def main():
    """入口函式"""
    parser = argparse.ArgumentParser(description="Business Data Platform 記憶演示 — 工具呼叫和Skill呼叫")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"Server URL (預設: {DEFAULT_URL})")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help=API_KEY_HELP)
    parser.add_argument(
        "--phase",
        choices=["all", "ingest", "verify"],
        default="all",
        help="all=全部, ingest=僅寫入, verify=僅驗證 (預設: all)",
    )
    parser.add_argument(
        "--session-id", default=DEFAULT_SESSION_ID, help=f"Session ID (預設: {DEFAULT_SESSION_ID})"
    )
    parser.add_argument("--wait", type=float, default=2, help="寫入後等待秒數 (預設: 2)")

    args = parser.parse_args()

    client = ov.SyncHTTPClient(url=args.url, api_key=resolve_api_key(args.api_key), timeout=180)

    try:
        client.initialize()
        console.print(f"  [green]已連線[/green] {args.url}")

        if args.phase in ("all", "ingest"):
            run_ingest(client, args.session_id, args.wait)

        if args.phase in ("all", "verify"):
            run_verify(client)

        console.print(
            Panel(
                "[bold green]演示完成[/bold green]",
                style="green",
                width=PANEL_WIDTH,
            )
        )

    except Exception as e:
        console.print(Panel(f"[bold red]Error:[/bold red] {e}", style="red", width=PANEL_WIDTH))


if __name__ == "__main__":
    main()
