#!/usr/bin/env python3
"""
Alice — 技術負責人的使用流程

操作：新增專案文件 → 語義搜尋 → 多輪對話 → 沉澱記憶 → 回顧記憶

獲取 API Key:
    API Key 由管理員通過 Admin API 分配，流程如下：

    1. ov.conf 中配置 server.root_api_key（如 "test"）
    2. 用 root_api_key 建立租戶和管理員:
         curl -X POST http://localhost:1933/api/v1/admin/accounts \
           -H "X-API-Key: test" -H "Content-Type: application/json" \
           -d '{"account_id": "demo-team", "admin_user_id": "alice"}'
       返回中的 user_key 就是 Alice 的 API Key
    3. 或者執行 setup_users.py 自動完成上述步驟，Key 寫入 user_keys.json

執行:
    uv run examples/cloud/alice.py
    uv run examples/cloud/alice.py --url http://localhost:1933 --api-key <alice_key>
"""

import argparse
import json
import sys
import time

import openviking as ov
from openviking_cli.utils.async_utils import run_async


def load_key_from_file(user="alice"):
    try:
        with open("examples/cloud/user_keys.json") as f:
            keys = json.load(f)
        return keys["url"], keys[f"{user}_key"]
    except (FileNotFoundError, KeyError):
        return None, None


def main():
    parser = argparse.ArgumentParser(description="Alice 的使用流程")
    parser.add_argument("--url", default=None, help="Server URL")
    parser.add_argument("--api-key", default=None, help="Alice 的 API Key")
    args = parser.parse_args()

    url, api_key = args.url, args.api_key
    if not api_key:
        url_from_file, key_from_file = load_key_from_file("alice")
        url = url or url_from_file or "http://localhost:1933"
        api_key = key_from_file
    if not url:
        url = "http://localhost:1933"
    if not api_key:
        print("請通過 --api-key 指定 API Key，或先執行 setup_users.py")
        sys.exit(1)

    print(f"Server: {url}")
    print("User:   alice")
    print("Key:    [hidden]")

    client = ov.SyncHTTPClient(url=url, api_key=api_key)
    client.initialize()

    try:
        # ── 1. 新增資源 ──
        print("\n== 1. 新增資源: OpenViking README ==")
        result = client.add_resource(
            path="https://raw.githubusercontent.com/volcengine/OpenViking/refs/heads/main/README.md",
            options={"reason": "專案核心文件"},
        )
        readme_uri = result.get("root_uri", "")
        print(f"  URI: {readme_uri}")
        print("  等待處理...")
        client.wait_processed()
        print("  完成")

        # ── 2. 檢視檔案系統 ──
        print("\n== 2. 檔案系統 ==")
        entries = client.ls("viking://")
        for entry in entries:
            if isinstance(entry, dict):
                kind = "dir " if entry.get("isDir") else "file"
                print(f"  [{kind}] {entry.get('name', '?')}")

        # ── 3. 讀取摘要 ──
        if readme_uri:
            print("\n== 3. 資源摘要 ==")
            abstract = client.abstract(readme_uri)
            print(f"  {abstract[:300]}")

        # ── 4. 語義搜尋 ──
        print("\n== 4. 語義搜尋: 'context database for AI agent' ==")
        results = client.find(query="context database for AI agent", limit=3)
        for index, resource in enumerate(results.get("resources", []), 1):
            print(
                f"  {index}. [{resource.get('score', 0.0):.3f}] "
                f"{resource['uri']}"
            )

        # ── 5. 建立會話，模擬技術討論 ──
        print("\n== 5. 對話: 技術架構討論 ==")
        session_info = client.create_session()
        session = client.session(session_id=session_info["session_id"])
        print(f"  Session: {session.session_id}")

        messages = [
            ("user", "我們的專案選擇用 OpenViking 做 Context Database，主要原因是什麼？"),
            (
                "assistant",
                "選擇 OpenViking 的核心原因：1) 檔案系統範式統一管理上下文 "
                "2) 分層載入（L0/L1/L2）節省 token 3) 目錄遞迴檢索比傳統 RAG 效果好 "
                "4) 內建 session 管理和 memory 自動沉澱。",
            ),
            ("user", "向量資料庫後端我們決定用 VikingDB 還是本地？"),
            (
                "assistant",
                "生產環境決定使用 VikingDB 雲服務。原因：1) 不需要自己運維向量庫 "
                "2) VikingDB 和方舟模型在同一可用區，網路延遲低 "
                "3) 自動擴縮容，不用擔心資料量增長。本地模式只用於開發測試。",
            ),
            ("user", "檔案儲存用 TOS 對吧？prefix 是 ov？"),
            (
                "assistant",
                "是的。AGFS 後端配置為 S3 模式，對接 TOS。"
                "bucket 是 openvikingdata，prefix 設為 ov，所有檔案存在 ov/ 目錄下。"
                "AK/SK 使用 IAM 子使用者的金鑰，許可權範圍限定在這個 bucket。",
            ),
        ]
        for role, content in messages:
            run_async(session.add_message(role=role, content=content))
        print(f"  添加了 {len(messages)} 條訊息")

        # ── 6. 沉澱記憶 ──
        print("\n== 6. 沉澱記憶: commit session ==")
        print("  正在提取（技術決策、架構選型等）...")
        client.commit_session(session.session_id)
        print("  commit 完成")
        time.sleep(2)
        client.wait_processed()
        print("  記憶向量化完成")

        # ── 7. 檢視記憶目錄 ──
        print("\n== 7. 記憶目錄 ==")
        try:
            mem_entries = client.ls("viking://user/alice/memories")
            for entry in mem_entries:
                if isinstance(entry, dict):
                    kind = "dir " if entry.get("isDir") else "file"
                    print(f"  [{kind}] {entry.get('name', '?')}")
        except Exception:
            print("  記憶目錄為空（可能無可提取的記憶）")

        # ── 8. 搜尋回顧記憶 ──
        print("\n== 8. 回顧記憶: '為什麼選擇 VikingDB' ==")
        results = client.find(query="為什麼選擇 VikingDB 作為向量資料庫", limit=3)
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

        print("\nAlice 流程完成")

    finally:
        client.close()


if __name__ == "__main__":
    main()
