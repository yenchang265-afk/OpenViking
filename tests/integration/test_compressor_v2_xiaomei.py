#!/usr/bin/env python3
"""
OpenViking 記憶演示指令碼 — 使用者: 小美（日常生活記錄）
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

DISPLAY_NAME = "小美"
DEFAULT_URL = "http://localhost:1934"
PANEL_WIDTH = 78
DEFAULT_API_KEY = None
DEFAULT_SESSION_ID = "xiaomei-demo"
ASSISTANT_PEER_ID = "xiaomei-demo-assistant"


console = Console()

# ── 對話資料 (10 輪 user + assistant 模擬) ─────────────────────────────────
# user 訊息取自原始 demo，assistant 訊息為模擬回覆（用於填充 session 上下文）

CONVERSATION = [
    {
        "user": "嗨！我是小美，剛畢業不久，現在在一家網際網路公司做運營。我想找個能幫我記錄日常生活的小助手，比如記一下每天發生的事情、我的想法、還有想做的事情。你能幫幫我嗎？",
        "assistant": "你好小美！當然可以，我很樂意當你的生活小助手。你可以隨時跟我聊天，我會幫你記住重要的事情。",
    },
    {
        "user": "今天心情還不錯！早上在地鐵上看到了一個超級可愛的小貓咪，它主人帶著它坐車，只露出個小腦袋，太萌了！對了，今天部門開會說下個月要做 618 大促，我負責寫活動文案，有點緊張，這是我第一次獨立負責這麼重要的專案。",
        "assistant": "看到可愛的貓咪真的很治癒！618 大促是個很好的鍛鍊機會，第一次獨立負責確實會緊張，但這說明領導信任你。你可以先列個文案大綱，慢慢來。",
    },
    {
        "user": "說到吃，中午我跟同事小麗一起去吃了樓下那家麻辣燙，超級好吃！我喜歡多放醋和麻醬，不太能吃辣。不過最近在減肥，不敢吃太多主食。你有沒有什麼好吃又不胖的推薦呀？",
        "assistant": "麻辣燙多放醋和麻醬是很經典的搭配。減肥期間可以試試輕食沙拉，或者選麻辣燙裡多加蔬菜和豆腐，少放粉絲和麵條。",
    },
    {
        "user": "對了，我辦了一張健身卡，就在我家小區旁邊。上週去了一次，跑了 30 分鐘步，還練了會兒瑜伽。結果第二天腿痠得不行，下樓都費勁。教練說讓我每週去三次，我怕堅持不下來...",
        "assistant": "剛開始運動肌肉痠痛是正常的。不用一下子每週三次，先從每週兩次開始適應，跑步和瑜伽交替練習，慢慢增加頻率。",
    },
    {
        "user": "這個週末你有什麼建議嗎？我想跟我男朋友一起出去。我們之前想過去看櫻花，但好像花期快過了。要不看電影？最近有什麼好看的電影嗎？或者去探店？我知道有一家咖啡館好像很不錯。",
        "assistant": "花期快過了的話可以抓緊最後的機會去看。也可以先去那家咖啡館探店，下午再看場電影，安排一個輕鬆的約會日。",
    },
    {
        "user": "說起來，我平時喜歡追劇，尤其是那種甜寵劇，最近在看《歸路》，太甜了！我還喜歡畫畫，雖然畫得不太好，但挺解壓的。偶爾也會看看書，最近在看《被討厭的勇氣》，挺有啟發的。",
        "assistant": "甜寵劇確實很解壓。畫畫也是個很好的放鬆方式，不用在意畫得好不好。《被討厭的勇氣》是本好書，裡面關於課題分離的理念很有用。",
    },
    {
        "user": "哎呀，我差點忘了提醒你！我對芒果過敏，吃了會起疹子。上次在公司同事給了我一個芒果蛋糕，我不知道，吃了一口就進醫院了，還好不嚴重。還有，我每天晚上睡覺前都要喝一杯熱牛奶，不然會失眠。",
        "assistant": "芒果過敏一定要注意，我記住了，以後推薦食物會避開芒果相關的。睡前喝熱牛奶是個好習慣，有助於睡眠。",
    },
    {
        "user": "最近我種草了一個拍立得，就是富士的 mini12，粉色那款，顏值超級高！但有點貴，要 700 多塊錢，還在猶豫要不要買。對了，我還想買一個投影儀，這樣週末可以在家看電影。",
        "assistant": "富士 mini12 粉色確實很好看，適合記錄生活。700 多塊不算特別貴，可以等促銷入手。投影儀也很實用，在家看電影很有氛圍。",
    },
    {
        "user": "說到同事，小麗人超好，她說會幫我一起想 618 的文案點子。還有，我閨蜜下週要結婚了！她是我們宿舍第一個結婚的，真為她開心。我還在想送什麼禮物好呢，紅包肯定要包，但想再加點特別的。",
        "assistant": "小麗是個好搭檔。閨蜜結婚的話，除了紅包可以送一本定製相簿，把你們大學的照片整理進去，很有紀念意義。",
    },
    {
        "user": "好的，謝謝你聽我說了這麼多！以後跟我聊天的時候，輕鬆一點就好，像朋友一樣。如果我不開心了，多安慰安慰我；如果我開心，就跟我一起開心。對了，多給我推薦好吃的好玩的，謝謝啦！",
        "assistant": "沒問題小美！以後就當朋友一樣聊天，我會記住你的喜好和習慣。有什麼開心的或不開心的都可以找我聊。",
    },
]

# ── 驗證查詢 ──────────────────────────────────────────────────────────────

VERIFY_QUERIES = [
    {
        "query": "小美的工作情況",
        "expected_keywords": ["618", "文案", "運營", "小麗"],
    },
    {
        "query": "小美的飲食偏好和注意事項",
        "expected_keywords": ["芒果過敏", "麻辣燙", "減肥"],
    },
    {
        "query": "小美的愛好",
        "expected_keywords": ["追劇", "畫畫", "看書"],
    },
    {
        "query": "小美想買什麼",
        "expected_keywords": ["拍立得", "投影儀"],
    },
    {
        "query": "小美的運動計劃",
        "expected_keywords": ["健身", "瑜伽", "跑步"],
    },
]


# ── Phase 1: 寫入對話並提交 ────────────────────────────────────────────────


def run_ingest(client: ov.SyncHTTPClient, session_id: str, wait_seconds: float):
    console.print()
    console.rule(f"[bold]Phase 1: 寫入對話 — {DISPLAY_NAME} ({len(CONVERSATION)} 輪)[/bold]")

    # 獲取 session；若不存在則由服務端按 session_id 自動建立
    session = client.create_session()
    session_id = session.get("session_id")
    print(f"session_id={session_id}")
    console.print(f"  Session: [bold cyan]{session_id}[/bold cyan]")
    console.print()

    # 設定一個測試用的會話時間（2023年4月2日）
    session_time = datetime(2023, 4, 2, 9, 36)
    session_time_str = session_time.isoformat()

    # 逐輪新增訊息
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
            peer_id=ASSISTANT_PEER_ID,
        )

    console.print()
    console.print(f"  共新增 [bold]{total * 2}[/bold] 條訊息")

    # 提交 session — 觸發記憶抽取
    console.print()
    console.print("  [yellow]提交 Session（觸發記憶抽取）...[/yellow]")
    commit_result = client.commit_session(session_id)
    task_id = commit_result.get("task_id")
    trace_id = commit_result.get("trace_id")
    console.print(f"  [bold cyan]trace_id: {trace_id}[/bold cyan]")
    console.print(f"  Commit 結果: {commit_result}")

    # 輪詢後臺任務直到完成
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

    # 等待向量化佇列處理完成
    console.print("  [yellow]等待向量化完成...[/yellow]")
    client.wait_processed()

    if wait_seconds > 0:
        console.print(f"  [dim]額外等待 {wait_seconds:.0f}s...[/dim]")
        time.sleep(wait_seconds)

    session_info = client.get_session(session_id)
    console.print(f"  Session 詳情: {session_info}")

    return session_id


# ── Phase 2: 驗證記憶召回 ─────────────────────────────────────────────────


def run_verify(client: ov.SyncHTTPClient):
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

            # 收集所有召回內容
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

            # 檢查關鍵詞命中
            all_text = " ".join(recall_texts)
            hits = [kw for kw in expected if kw in all_text]
            hit_str = ", ".join(hits) if hits else "[dim]無[/dim]"

            results_table.add_row(str(i), query, str(count), hit_str)

        except Exception as e:
            console.print(f"    [red]ERROR: {e}[/red]")
            results_table.add_row(str(i), query, "[red]ERR[/red]", str(e)[:40])

    console.print()
    console.print(results_table)


# ── 入口 ───────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description=f"OpenViking 記憶演示 — {DISPLAY_NAME}")
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
    parser.add_argument("--wait", type=float, default=5.0, help="提交後額外等待秒數 (預設: 5)")
    args = parser.parse_args()

    console.print(
        Panel(
            f"[bold]OpenViking 記憶演示 — {DISPLAY_NAME}[/bold]\n"
            f"Server: {args.url}  |  Phase: {args.phase}",
            style="magenta",
            width=PANEL_WIDTH,
        )
    )

    client = ov.SyncHTTPClient(url=args.url, api_key=resolve_api_key(args.api_key), timeout=180)

    try:
        client.initialize()
        console.print(f"  [green]已連線[/green] {args.url}")

        if args.phase in ("all", "ingest"):
            run_ingest(client, session_id=args.session_id, wait_seconds=args.wait)

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
        import traceback

        traceback.print_exc()

    finally:
        client.close()


if __name__ == "__main__":
    main()
