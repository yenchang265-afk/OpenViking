#!/usr/bin/env python3
"""
Business Data Platform 記憶演示指令碼 — 事件跨多個 turn 的測試
"""

import argparse
import time
from datetime import datetime

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

DISPLAY_NAME = "小明"
DEFAULT_URL = "http://localhost:1934"
PANEL_WIDTH = 78
DEFAULT_API_KEY = None
DEFAULT_SESSION_ID = "event-span-multiple-turns"


console = Console()

# ── 對話資料 (事件跨多個 turn) ─────────────────────────────────────────────
# 使用者訊息描述一個持續多輪的事件（如專案討論、問題解決過程）
# 這裡模擬一個產品需求討論的事件，持續 4 個 user + assistant 輪次

CONVERSATION = [
    {
        "user": "我們公司要做一個新功能，是關於使用者反饋系統的。我需要幫產品經理整理一下需求，你能幫我嗎？",
        "assistant": "當然可以！你可以告訴我產品經理的具體需求，我會幫你記錄和整理。",
    },
    {
        "user": "產品經理說這個反饋系統需要支援文字和圖片上傳，使用者可以匿名提交，還需要有分類功能，比如分為 bug 反饋、功能建議、使用體驗等。",
        "assistant": "好的，我已經記錄了：支援文字和圖片上傳、匿名提交、分類功能（bug、建議、體驗）。",
    },
    {
        "user": "還有，產品經理要求反饋系統要能即時通知，當用戶提交反饋後，相關人員要能立即收到訊息。另外，還需要有反饋處理進度的跟蹤功能。",
        "assistant": "我補充了：即時通知功能、反饋處理進度跟蹤。",
    },
    {
        "user": "最後，產品經理說要在下週之前完成需求文件的編寫，然後開始開發。我現在需要把這些需求整理成一份清晰的文件。",
        "assistant": "明白了，你需要在下週前完成需求文件，然後開始開發。我會幫你記住這些關鍵點。",
    },
    {
        "user": "今天天氣真好！我想下午去公園散步，順便看看有沒有好看的花。",
        "assistant": "天氣好的時候去公園散步是個不錯的選擇。春天的公園應該有很多花盛開。",
    },
    {
        "user": "對了，我上週買的那本書還沒看完。書名是《人類簡史》，寫得很有意思。我計劃這個週末讀完它。",
        "assistant": "《人類簡史》確實是一本很有趣的書。週末讀完應該是可行的。",
    },
    {
        "user": "我們專案的需求文件已經完成了，我昨天加班到很晚才寫完。今天早上已經發給產品經理了，他說寫得不錯。",
        "assistant": "恭喜你完成了需求文件！產品經理認可你的工作，說明你寫得很好。",
    },
    {
        "user": "產品經理說反饋系統的開發工作已經安排好了，下週一開始正式開發。我需要負責前端頁面的設計和實現。",
        "assistant": "開發工作安排好了，下週一開始。你負責前端頁面的設計和實現。",
    },
    {
        "user": "今天中午我和同事一起去吃了新開的那家日料店，味道很不錯。刺身很新鮮，壽司也很好吃。",
        "assistant": "新開的日料店味道不錯，刺身新鮮，壽司好吃。",
    },
    {
        "user": "反饋系統的前端頁面已經設計好了，我昨天和設計師一起討論了很久。現在需要開始寫程式碼實現了。",
        "assistant": "前端頁面設計完成，現在開始程式碼實現。",
    },
]

# ── 驗證查詢 ──────────────────────────────────────────────────────────────

VERIFY_QUERIES = [
    {
        "query": "反饋系統的功能需求",
        "expected_keywords": ["文字", "圖片", "匿名", "分類", "通知", "進度", "需求文件"],
    },
    {
        "query": "反饋系統的開發計劃",
        "expected_keywords": ["下週", "前端", "設計", "實現"],
    },
    {
        "query": "小明的其他活動",
        "expected_keywords": ["公園", "散步", "讀書", "日料"],
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

    # 設定一個測試用的會話時間（2023年4月2日）
    session_time = datetime(2023, 4, 2, 9, 36)
    session_time_str = session_time.isoformat()

    total = len(CONVERSATION)
    for i, turn in enumerate(CONVERSATION, 1):
        console.print(f"  [dim][{i}/{total}][/dim] 添加 user + assistant 消息...")
        client.add_message(
            session_id,
            role="user",
            parts=[{"type": "text", "text": turn["user"]}],
            created_at=session_time_str,
        )
        client.add_message(
            session_id,
            role="assistant",
            parts=[{"type": "text", "text": turn["assistant"]}],
            created_at=session_time_str,
        )

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
            hit_str = ", ".join(hits) if hits else "[dim]無[/dim]"

            results_table.add_row(str(i), query, str(count), hit_str)

        except Exception as e:
            console.print(f"    [red]ERROR: {e}[/red]")
            results_table.add_row(str(i), query, "[red]ERR[/red]", str(e)[:40])

    console.print()
    console.print(results_table)


def main():
    """入口函式"""
    parser = argparse.ArgumentParser(description=f"Business Data Platform 記憶演示 — {DISPLAY_NAME}")
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
