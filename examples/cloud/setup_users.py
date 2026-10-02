#!/usr/bin/env python3
"""
建立租戶和使用者，獲取 API Key

前置條件:
    1. 按照 GUIDE.md 完成雲服務開通和配置
    2. 啟動 OpenViking Server:
         export OPENVIKING_CONFIG_FILE=examples/cloud/ov.conf
         openviking-server

獲取使用者 API Key 的流程:
    1. 在 ov.conf 中設定 server.root_api_key（管理員金鑰）
    2. 用 root_api_key 呼叫 POST /api/v1/admin/accounts 建立租戶，返回管理員使用者的 API Key
    3. 用管理員 API Key 呼叫 POST /api/v1/admin/accounts/{id}/users 註冊使用者，返回使用者的 API Key
    4. 每個使用者拿到自己的 API Key 後即可獨立使用所有資料介面

本指令碼自動完成上述流程，建立一個租戶 "demo-team"，註冊 alice 和 bob 兩個使用者。

執行:
    uv run setup_users.py
    uv run setup_users.py --url http://localhost:1933 --root-key test
"""

import argparse
import json
import sys

import httpx


def main():
    parser = argparse.ArgumentParser(description="建立租戶和使用者")
    parser.add_argument("--url", default="http://localhost:1933", help="Server URL")
    parser.add_argument("--root-key", default="test", help="ov.conf 中的 root_api_key")
    args = parser.parse_args()

    base = args.url.rstrip("/")
    headers = {"X-API-Key": args.root_key, "Content-Type": "application/json"}

    # 健康檢查
    resp = httpx.get(f"{base}/health")
    if not resp.is_success:
        print(f"Server 不可用: {resp.status_code}")
        sys.exit(1)
    print(f"Server 正常: {resp.json()}")

    # 建立租戶，alice 作為管理員
    print("\n== 建立租戶 demo-team ==")
    resp = httpx.post(
        f"{base}/api/v1/admin/accounts",
        headers=headers,
        json={"account_id": "demo-team", "admin_user_id": "alice"},
    )
    if not resp.is_success:
        print(f"建立失敗: {resp.status_code} {resp.text}")
        sys.exit(1)
    result = resp.json()["result"]
    alice_key = result["user_key"]
    print("  租戶: demo-team")
    print("  管理員: alice (admin)")
    print(f"  Alice API Key: {alice_key}")

    # alice 註冊 bob
    print("\n== 註冊使用者 bob ==")
    alice_headers = {"X-API-Key": alice_key, "Content-Type": "application/json"}
    resp = httpx.post(
        f"{base}/api/v1/admin/accounts/demo-team/users",
        headers=alice_headers,
        json={"user_id": "bob", "role": "user"},
    )
    if not resp.is_success:
        print(f"註冊失敗: {resp.status_code} {resp.text}")
        sys.exit(1)
    result = resp.json()["result"]
    bob_key = result["user_key"]
    print("  使用者: bob (user)")
    print(f"  Bob API Key: {bob_key}")

    # 輸出彙總
    keys = {
        "url": args.url,
        "account_id": "demo-team",
        "alice_key": alice_key,
        "bob_key": bob_key,
    }
    print("\n== 彙總 ==")
    print(json.dumps(keys, indent=2))

    # 寫入檔案供後續指令碼使用
    keys_file = "examples/cloud/user_keys.json"
    with open(keys_file, "w") as f:
        json.dump(keys, f, indent=2)
    print(f"\n已寫入 {keys_file}，後續指令碼可直接讀取。")


if __name__ == "__main__":
    main()
