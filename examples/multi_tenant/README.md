# Business Data Platform Multi-Tenant 示例

演示 Business Data Platform 多租戶管理功能：帳戶建立、使用者註冊、角色管理、Key 管理、資料訪問。

## 架構

```
                        Admin API (ROOT key)
                       ┌─────────────────────────┐
                       │  Create/Delete Accounts  │
                       │  Register/Remove Users   │
                       │  Set Roles, Regen Keys   │
                       └────────┬────────────────┘
                                │
                                ▼
┌──────────┐  User Key   ┌──────────────────┐  Root Key   ┌──────────┐
│  Alice   │ ──────────► │  Business Data Platform      │ ◄────────── │  Admin   │
│  (ADMIN) │             │  Server          │             │  (ROOT)  │
└──────────┘             │                  │             └──────────┘
┌──────────┐  User Key   │  ov.conf:        │
│  Bob     │ ──────────► │  root_api_key    │
│  (USER)  │             └──────────────────┘
└──────────┘
```

## 認證體系

| Key 型別 | 建立方式 | 角色 | 能力 |
|----------|---------|------|------|
| Root Key | `ov.conf` 中配置 | ROOT | 全部操作 + Admin API |
| User Key | Admin API 建立 | ADMIN 或 USER | 按 account 訪問 |

| 角色 | 作用域 | 能力 |
|------|--------|------|
| ROOT | 全域 | 全部操作 + 建立/刪除 account、管理使用者 |
| ADMIN | 所屬 account | 常規操作 + 管理本 account 的使用者 |
| USER | 所屬 account | 常規操作（ls、read、find、sessions 等） |

## Quick Start

### 1. 配置 Server

複製配置檔案並填入你的模型 API Key：

```bash
cp ov.conf.example ov.conf
# 編輯 ov.conf，填入 embedding 和 vlm 的 api_key
```

關鍵配置項——`root_api_key` 啟用多租戶認證：

```json
{
  "server": {
    "root_api_key": "my-root-key"
  }
}
```

不配置 `root_api_key` 時，認證停用，所有請求以 ROOT 身份訪問（開發模式）。

### 2. 啟動 Server

```bash
# 方式一：指定配置文件
openviking-server --config ./ov.conf

# 方式二：放到預設路徑
cp ov.conf ~/.openviking/ov.conf
openviking-server

# 驗證
curl http://localhost:1933/health
# {"status": "ok"}
```

### 3. 執行示例

**Python SDK：**

```bash
# 安裝依賴
uv sync

# 執行（使用預設引數）
uv run admin_workflow.py

# 自定義引數
uv run admin_workflow.py --url http://localhost:1933 --root-key my-root-key
```

**CLI：**

```bash
# 執行（使用預設引數）
bash admin_workflow.sh

# 自定義引數
ROOT_KEY=my-root-key SERVER=http://localhost:1933 bash admin_workflow.sh
```

## 示例流程

兩個示例（Python SDK 和 CLI）覆蓋完全相同的流程：

```
 1. Health Check              無需認證，驗證服務可用
 2. Create Account            ROOT 建立 account "acme"，同時建立首個 admin "alice"
 3. Register User (ROOT)      ROOT 在 "acme" 下注冊普通使用者 "bob"
 4. Register User (ADMIN)     alice (ADMIN) 在 "acme" 下注冊使用者 "charlie"
 5. List Accounts             ROOT 列出所有 account
 6. List Users                列出 "acme" 下所有使用者及角色
 7. Change Role               ROOT 將 bob 提升為 ADMIN
 8. Regenerate Key            為 charlie 重新生成 key，舊 key 立即失效
 9. Access Data               bob 使用 user key 訪問資料
10. Error Tests               非法 key、許可權不足、重複建立、舊 key 等負面用例
11. Remove User               刪除 charlie，驗證其 key 失效
12. Delete Account            刪除 account "acme"，驗證 alice 的 key 也失效
```

## CLI 命令參考

```bash
# Account 管理
openviking admin create-account <account_id> --admin <admin_user_id>
openviking admin list-accounts
openviking admin delete-account <account_id>

# User 管理
openviking admin register-user <account_id> <user_id> [--role user|admin]
openviking admin list-users <account_id>
openviking admin remove-user <account_id> <user_id>
openviking admin set-role <account_id> <user_id> <role>
openviking admin regenerate-key <account_id> <user_id>
```

## 檔案說明

```
admin_workflow.py    Python SDK 示例（httpx 呼叫 Admin API + SyncHTTPClient 訪問資料）
admin_workflow.sh    CLI 示例（openviking admin 命令，同等流程）
ov.conf.example      Server 配置文件模板（含 root_api_key）
pyproject.toml       專案依賴
README.md            本文件
```

## Admin API 參考

| 方法 | 端點 | 所需角色 | 說明 |
|------|------|---------|------|
| POST | `/api/v1/admin/accounts` | ROOT | 建立 account + 首個 admin |
| GET | `/api/v1/admin/accounts` | ROOT | 列出所有 account |
| DELETE | `/api/v1/admin/accounts/{id}` | ROOT | 刪除 account |
| POST | `/api/v1/admin/accounts/{id}/users` | ROOT, ADMIN | 註冊使用者 |
| GET | `/api/v1/admin/accounts/{id}/users` | ROOT, ADMIN | 列出使用者 |
| DELETE | `/api/v1/admin/accounts/{id}/users/{uid}` | ROOT, ADMIN | 移除使用者 |
| PUT | `/api/v1/admin/accounts/{id}/users/{uid}/role` | ROOT | 修改使用者角色 |
| POST | `/api/v1/admin/accounts/{id}/users/{uid}/key` | ROOT, ADMIN | 重新生成 user key |

## 相關文件

- [認證指南](../../docs/zh/guides/04-authentication.md) - 完整認證說明
- [配置指南](../../docs/zh/guides/01-configuration.md) - 配置檔案參考
- [API 概覽](../../docs/zh/api/01-overview.md) - 完整 API 參考
- [服務端模式快速開始](../../docs/zh/getting-started/03-quickstart-server.md) - 基礎 HTTP 服務接入方式
