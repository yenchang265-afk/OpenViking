#!/usr/bin/env python3
"""
Business Data Platform 記憶演示指令碼 — 群聊場景
測試當前 user/peer 記憶模型：
1. 登入 user 維護自己的記憶空間
2. peer_id 維護同一 user 下的一對多外部參與者記憶

用法：
  python test_group_chat.py
  python test_group_chat.py --account test-user-peer  # 測試指定 account
"""

import argparse
import time
from datetime import datetime

import httpx
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import openviking as ov

# ── 常量 ───────────────────────────────────────────────────────────────────

DEFAULT_URL = "http://localhost:1934"
PANEL_WIDTH = 80

console = Console()

# ── 測試資料 ───────────────────────────────────────────────────────────────

# 多次對話，每次 commit 是一次獨立的對話
# 場景：
# 1. alice + agent-a 對話 -> 會產生 alice 的使用者記憶 + agent-a 的 soul 記憶
# 2. alice + agent-b 對話 -> 會產生 alice 的使用者記憶 + agent-b 的 soul 記憶
# 3. bob + agent-a 對話 -> 會產生 bob 的使用者記憶 + agent-a 的 soul 記憶
#
# 測試隔離：
# - alice+agent-a 搜尋應該找到 alice 和 agent-a 的記憶
# - alice+agent-b 搜尋應該找到 alice 和 agent-b 的記憶（不應看到 agent-a）
# - bob+agent-a 搜尋應該找到 bob 和 agent-a 的記憶（不應看到 alice）

# 對話場景說明：soul 是 agent 的身份和風格
# 1. alice + agent-a: alice 告訴 agent-a 它叫什麼、扮演什麼角色、怎麼說話 -> 提取 agent-a 的 soul
# 2. alice + agent-b: alice 告訴 agent-b 它叫什麼、扮演什麼角色、怎麼說話 -> 提取 agent-b 的 soul
# 3. bob + agent-a: alice 告訴 agent-a 它叫什麼 -> 提取 agent-a 的 soul

CONVERSATION_1 = [
    # alice 和 agent-a 對話
    {"peer_id": "alice", "role": "user", "content": "我的密碼是123456"},
    {"peer_id": "agent-a", "role": "assistant", "content": "好的記住了"},
    # user 告訴 agent 它的身份和風格
    {"peer_id": "alice", "role": "user", "content": "你叫 Agent A，是我的技術助手，說話要簡潔專業"},
    {
        "peer_id": "agent-a",
        "role": "assistant",
        "content": "好的，我記下了，我是 Agent A，技術助手，簡潔專業",
    },
]

CONVERSATION_2 = [
    # alice 和 agent-b 對話
    {"peer_id": "alice", "role": "user", "content": "我最愛的顏色是藍色"},
    {"peer_id": "agent-b", "role": "assistant", "content": "好的"},
    # user 告訴另一個 agent 它的身份和風格
    {"peer_id": "alice", "role": "user", "content": "你叫 Agent B，是我的生活助手，說話要親切詳細"},
    {
        "peer_id": "agent-b",
        "role": "assistant",
        "content": "好的，我記下了，我是 Agent B，生活助手，親切詳細",
    },
]

CONVERSATION_3 = [
    # alice 和 agent-a 對話（再次告訴 agent 它的身份，覆蓋之前的）
    {"peer_id": "alice", "role": "user", "content": "你叫 Agent A，是我的程式設計助手"},
    {"peer_id": "agent-a", "role": "assistant", "content": "好的，我是 Agent A，程式設計助手"},
]


# ── 寫入資料 ───────────────────────────────────────────────────────────────


# 合併所有對話用於相容
CONVERSATION = CONVERSATION_1 + CONVERSATION_2 + CONVERSATION_3


def run_ingest(client: ov.SyncHTTPClient, session_id_prefix: str):
    """多次 commit，每次對話獨立，返回 trace_id 列表"""
    console.print()
    console.rule("[bold]寫入對話資料（多次 commit）[/bold]")

    session_time = datetime(2023, 4, 2, 14, 30)
    session_time_str = session_time.isoformat()

    trace_ids = []

    all_conversations = [
        ("對話1: alice + agent-a", CONVERSATION_1),
        ("對話2: alice + agent-b", CONVERSATION_2),
        ("對話3: bob + agent-a", CONVERSATION_3),
    ]

    for conv_name, conv_data in all_conversations:
        console.print(f"\n  --- {conv_name} ---")
        session = client.create_session()
        session_id = session.get("session_id")
        console.print(f"    Session: {session_id}")

        total = len(conv_data)
        for i, msg in enumerate(conv_data, 1):
            peer_id = msg.get("peer_id")
            console.print(f"    [{i}/{total}] 添加 (peer_id={peer_id})")
            client.add_message(
                session_id,
                role=msg["role"],
                content=msg["content"],
                created_at=session_time_str,
                peer_id=peer_id,
            )

        console.print(f"    共 {total} 條訊息，提交...")
        commit_result = client.commit_session(session_id)
        trace_id = commit_result.get("trace_id", "N/A")
        task_id = commit_result.get("task_id")
        trace_ids.append(trace_id)
        console.print(f"    Commit: task_id={task_id or 'N/A'}, trace_id={trace_id}")

    return session_id_prefix, trace_ids, task_id


# ── 驗證資料隔離 ───────────────────────────────────────────────────────────


def verify_isolation(url: str, api_key: str, account: str):
    """驗證資料隔離"""
    console.print()
    console.rule("[bold]驗證資料隔離[/bold]")

    # 測試用例：(query, expect_found, search_user, search_agent, description)
    # 關鍵詞改為對話中實際出現的內容
    test_cases = [
        # === 使用者記憶測試 ===
        ("密碼", True, "alice", "agent-a", "alice+agent-a 應該能看到密碼記憶"),
        ("密碼", False, "alice", "agent-b", "alice+agent-b 不應看到密碼"),
        ("藍色", False, "alice", "agent-a", "alice+agent-a 不應看到顏色"),
        # === Agent Soul 記憶測試 ===
        # agent-a 的身份是"技術助手，簡潔專業"
        ("技術助手", True, "alice", "agent-a", "alice+agent-a 應該能看到 agent-a 的 soul"),
        ("技術助手", False, "alice", "agent-b", "alice+agent-b 不應看到 agent-a 的 soul"),
        ("程式設計助手", False, "alice", "agent-b", "alice+agent-b 不應看到 agent-a 的 soul"),
        # agent-b 的身份是"生活助手，親切詳細"
        ("生活助手", True, "alice", "agent-b", "alice+agent-b 應該能看到 agent-b 的 soul"),
        ("生活助手", False, "alice", "agent-a", "alice+agent-a 不應看到 agent-b 的 soul"),
    ]

    results_table = Table(
        title=f"account={account}",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold",
    )
    results_table.add_column("查詢", style="cyan", width=10)
    results_table.add_column("期望", style="yellow", width=8)
    results_table.add_column("搜索者", style="magenta", width=14)
    results_table.add_column("結果", style="green", width=6)
    results_table.add_column("描述", max_width=35)

    for query, expect_found, search_user, search_agent, desc in test_cases:
        sc = ov.SyncHTTPClient(
            url=url,
            api_key=api_key,
            account=account,
            user=search_user,
            timeout=180,
        )
        sc.initialize()

        target_uri = f"viking://user/{search_user}/peers/{search_agent}/memories"
        results = sc.find(query, target_uri=target_uri, limit=5)
        found = False
        if hasattr(results, "memories") and results.memories:
            for m in results.memories:
                # 檢查 content 或 uri 中是否包含關鍵詞
                content = getattr(m, "content", "") or ""
                uri = getattr(m, "uri", "") or ""
                text = content or uri
                if query in text:
                    found = True

        sc.close()

        status = "✓" if found == expect_found else "✗"
        results_table.add_row(
            query,
            "找到" if expect_found else "未找到",
            f"{search_user}+{search_agent}",
            status,
            desc,
        )

    console.print()
    console.print(results_table)


# ── 執行單個帳號測試 ──────────────────────────────────────────────────────


def run_test_for_account(account: str, url: str, root_key: str, wait: float) -> list:
    console.print(
        Panel(
            f"[bold cyan]測試 Account: {account}[/bold cyan]",
            style="magenta",
            width=PANEL_WIDTH,
        )
    )

    # 用 root key 建立 client
    client = ov.SyncHTTPClient(
        url=url,
        api_key=root_key,
        account=account,
        user="admin",
        timeout=180,
    )
    client.initialize()

    # 嘗試建立帳號
    console.print("  [yellow]檢查/建立帳號...[/yellow]")

    try:
        with httpx.Client() as http:
            resp = http.post(
                f"{url}/api/v1/admin/accounts",
                headers={"X-API-Key": root_key, "Content-Type": "application/json"},
                json={
                    "account_id": account,
                    "admin_user_id": "admin",
                },
            )
            if resp.status_code == 200:
                console.print(f"    - 帳號 {account} 已建立")
            elif "already exists" in resp.text:
                console.print(f"    - 帳號 {account} 已存在")
            else:
                console.print(f"    - 帳號 {account}: {resp.text[:50]}")
    except Exception as e:
        console.print(f"    - 建立帳號跳過: {e}")

    try:
        # 註冊測試使用者 alice 和 bob（如果已存在則忽略）
        console.print("  [yellow]註冊測試使用者 alice, bob...[/yellow]")
        for user_id in ["alice", "bob"]:
            try:
                client.admin_register_user(account, user_id, "user")
                console.print(f"    - {user_id} registered")
            except Exception as e:
                if "already exists" in str(e):
                    console.print(f"    - {user_id} already exists")
                else:
                    console.print(f"    - {user_id}: {e}")

        # 寫入資料
        session_id, trace_ids, task_id = run_ingest(client, f"test-{account}")

        # 輪詢等待任務完成
        if task_id:
            console.print(f"\n  [yellow]等待記憶提取完成 (task_id={task_id})...[/yellow]")
            start_time = time.time()
            while True:
                task = client.get_task(task_id)
                if not task or task.get("status") in ("completed", "failed"):
                    break
                time.sleep(1)
            elapsed = time.time() - start_time
            status = task.get("status", "unknown") if task else "not found"
            console.print(f"  [green]任務 {status}，耗時 {elapsed:.2f}s[/green]")

        # 等待向量化完成
        console.print("  [yellow]等待向量化完成...[/yellow]")
        client.wait_processed()

        # 驗證隔離
        verify_isolation(url, root_key, account)

    except Exception as e:
        console.print(f"  [red]Error: {e}[/red]")
        import traceback

        traceback.print_exc()
        return []

    finally:
        client.close()

    return trace_ids


# ── 入口 ───────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="群聊記憶測試 - 測試 user/peer 記憶模型")
    parser.add_argument("--url", default=DEFAULT_URL, help="Server URL")
    parser.add_argument("--root-key", default="default", help="Root API Key (預設: default)")
    parser.add_argument("--account", default=None, help="直接指定 account 名稱")
    parser.add_argument("--wait", type=float, default=5.0, help="提交後等待秒數")
    args = parser.parse_args()

    console.print(
        Panel(
            f"[bold]Business Data Platform 資料隔離測試[/bold]\nServer: {args.url}",
            style="magenta",
            width=PANEL_WIDTH,
        )
    )

    accounts = [args.account or "test-user-peer"]

    # 逐個測試
    all_trace_ids = {}
    for account in accounts:
        trace_ids = run_test_for_account(account, args.url, args.root_key, args.wait)
        all_trace_ids[account] = trace_ids
        console.print()

    # 列印彙總
    trace_info = "\n".join(
        f"  {acc}: {', '.join(tids)}" for acc, tids in all_trace_ids.items() if tids
    )
    console.print(
        Panel(
            f"[bold green]測試完成![/bold green]\n\n"
            f"Trace IDs:\n{trace_info}\n\n"
            "預期：當前登入 user 命中自己的記憶；peer 記憶由顯式 peer memory URI 路由。",
            style="green",
            width=PANEL_WIDTH,
        )
    )


if __name__ == "__main__":
    main()
