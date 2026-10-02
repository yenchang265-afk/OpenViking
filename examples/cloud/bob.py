#!/usr/bin/env python3
"""
Bob — 新入職成員的使用流程

操作：瀏覽團隊資源 → 回顧團隊記憶 → 新增自己的資源 → 對話 → 沉澱記憶 → 帶上下文搜尋

獲取 API Key:
    API Key 由租戶管理員分配，流程如下：

    1. 管理員（如 Alice）用自己的 Key 註冊 Bob:
         curl -X POST http://localhost:1933/api/v1/admin/accounts/demo-team/users \
           -H "X-API-Key: <alice_key>" -H "Content-Type: application/json" \
           -d '{"user_id": "bob", "role": "user"}'
       返回中的 user_key 就是 Bob 的 API Key
    2. 或者執行 setup_users.py 自動完成，Key 寫入 user_keys.json

執行（建議在 alice.py 之後執行，這樣可以看到 Alice 沉澱的團隊記憶）:
    uv run examples/cloud/bob.py
    uv run examples/cloud/bob.py --url http://localhost:1933 --api-key <bob_key>
"""

import argparse
import json
import sys
import time

import openviking as ov
from openviking_cli.utils.async_utils import run_async


def load_key_from_file(user="bob"):
    try:
        with open("examples/cloud/user_keys.json") as f:
            keys = json.load(f)
        return keys["url"], keys[f"{user}_key"]
    except (FileNotFoundError, KeyError):
        return None, None


def main():
    parser = argparse.ArgumentParser(description="Bob 的使用流程")
    parser.add_argument("--url", default=None, help="Server URL")
    parser.add_argument("--api-key", default=None, help="Bob 的 API Key")
    args = parser.parse_args()

    url, api_key = args.url, args.api_key
    if not api_key:
        url_from_file, key_from_file = load_key_from_file("bob")
        url = url or url_from_file or "http://localhost:1933"
        api_key = key_from_file
    if not url:
        url = "http://localhost:1933"
    if not api_key:
        print("請通過 --api-key 指定 API Key，或先執行 setup_users.py")
        sys.exit(1)

    print(f"Server: {url}")
    print("User:   bob")
    print("Key:    [hidden]")

    client = ov.SyncHTTPClient(url=url, api_key=api_key)
    client.initialize()

    try:
        # ── 1. 瀏覽團隊已有資源 ──
        print("\n== 1. 瀏覽團隊資源 ==")
        entries = client.ls("viking://")
        if not entries:
            print("  （空，Alice 還沒新增資源）")
        for entry in entries:
            if isinstance(entry, dict):
                kind = "dir " if entry.get("isDir") else "file"
                print(f"  [{kind}] {entry.get('name', '?')}")

        # ── 2. 回顧團隊記憶（Alice 沉澱的技術決策） ──
        print("\n== 2. 回顧團隊記憶: '專案技術選型' ==")
        results = client.find(query="專案用了什麼技術棧和架構選型", limit=5)
        memories = results.get("memories", [])
        if memories:
            print("  團隊記憶:")
            for index, memory in enumerate(memories, 1):
                description = (
                    memory.get("abstract")
                    or memory.get("overview")
                    or memory.get("uri", "")
                )
                print(f"  {index}. [{memory.get('score', 0.0):.3f}] {description[:150]}")
        else:
            print("  未找到團隊記憶（Alice 可能還沒執行 commit）")
        resources = results.get("resources", [])
        if resources:
            print("  相關資源:")
            for index, resource in enumerate(resources, 1):
                print(
                    f"  {index}. [{resource.get('score', 0.0):.3f}] "
                    f"{resource['uri']}"
                )

        # ── 3. 搜尋具體決策 ──
        print("\n== 3. 搜尋: '儲存方案 TOS 配置' ==")
        results = client.find(query="檔案儲存方案 TOS bucket 配置", limit=3)
        memories = results.get("memories", [])
        if memories:
            for index, memory in enumerate(memories, 1):
                description = (
                    memory.get("abstract")
                    or memory.get("overview")
                    or memory.get("uri", "")
                )
                print(f"  {index}. [{memory.get('score', 0.0):.3f}] {description[:150]}")
        else:
            print("  未找到相關記憶")

        # ── 4. 新增自己的資源 ──
        print("\n== 4. 新增資源: CONTRIBUTING.md ==")
        result = client.add_resource(
            path="https://raw.githubusercontent.com/volcengine/OpenViking/refs/heads/main/CONTRIBUTING.md",
            options={"reason": "貢獻指南學習筆記"},
        )
        bob_uri = result.get("root_uri", "")
        print(f"  URI: {bob_uri}")
        print("  等待處理...")
        client.wait_processed(timeout=120)
        print("  完成")

        # ── 5. 建立會話，模擬入職學習 ──
        print("\n== 5. 對話: 入職學習 ==")
        session_info = client.create_session()
        session = client.session(session_id=session_info["session_id"])
        print(f"  Session: {session.session_id}")

        messages = [
            ("user", "我剛入職，需要了解 Business Data Platform 的貢獻流程"),
            (
                "assistant",
                "歡迎！貢獻流程主要是：1) Fork 倉庫 2) 建立 feature branch "
                "3) 提交 PR 並通過 CI 4) Code Review 後合併。"
                "程式碼規範見 CONTRIBUTING.md。",
            ),
            ("user", "本地開發環境怎麼搭建？"),
            (
                "assistant",
                "本地開發步驟：1) 安裝 Python 3.10+ 和 uv "
                "2) git clone 後執行 uv sync 安裝依賴 "
                "3) 複製 examples/ov.conf.example 為 ~/.openviking/ov.conf 填入 API Key "
                "4) 執行 openviking-server 啟動開發服務。構建 abi3 C++ 擴充需要 cmake。",
            ),
            ("user", "測試怎麼跑？"),
            (
                "assistant",
                "執行測試：1) uv run pytest 跑全量測試 "
                "2) uv run pytest tests/unit -x 只跑單元測試 "
                "3) CI 會自動跑 lint + test，PR 合併前必須全綠。",
            ),
        ]
        for role, content in messages:
            run_async(session.add_message(role=role, content=content))
        print(f"  添加了 {len(messages)} 條訊息")

        # ── 6. 沉澱記憶 ──
        print("\n== 6. 沉澱記憶: commit session ==")
        print("  正在提取（開發流程、環境配置等）...")
        client.commit_session(session.session_id)
        print("  commit 完成")
        time.sleep(2)
        client.wait_processed(timeout=120)
        print("  記憶向量化完成")

        # ── 7. 回顧自己的記憶 ──
        print("\n== 7. 回顧記憶: '本地開發環境搭建' ==")
        results = client.find(query="本地開發環境搭建步驟", limit=3)
        memories = results.get("memories", [])
        if memories:
            print("  記憶:")
            for index, memory in enumerate(memories, 1):
                description = (
                    memory.get("abstract")
                    or memory.get("overview")
                    or memory.get("uri", "")
                )
                print(f"  {index}. [{memory.get('score', 0.0):.3f}] {description[:150]}")
        resources = results.get("resources", [])
        if resources:
            print("  資源:")
            for index, resource in enumerate(resources, 1):
                print(
                    f"  {index}. [{resource.get('score', 0.0):.3f}] "
                    f"{resource['uri']}"
                )

        # ── 8. 帶會話上下文的搜尋 ──
        print("\n== 8. 帶上下文搜尋: '還有什麼注意事項' ==")
        results = client.search(
            query="還有什麼需要注意的事項",
            session_id=session.session_id,
            limit=3,
        )
        resources = results.get("resources", [])
        if resources:
            for index, resource in enumerate(resources, 1):
                print(
                    f"  {index}. [{resource.get('score', 0.0):.3f}] "
                    f"{resource['uri']}"
                )
        memories = results.get("memories", [])
        if memories:
            for index, memory in enumerate(memories, 1):
                description = (
                    memory.get("abstract")
                    or memory.get("overview")
                    or memory.get("uri", "")
                )
                print(f"  {index}. [{memory.get('score', 0.0):.3f}] {description[:100]}")

        print("\nBob 流程完成")

    finally:
        client.close()


if __name__ == "__main__":
    main()
