# OpenViking 閘道器管理 API

OpenViking Server 在 `/api/v1/admin/gateway` 下轉發 OpenViking 閘道器的管理請求。Studio 的閘道器頁面通過這些端點管理上游、上下文配置和閘道器金鑰，並讀取請求日誌。模型請求不走這組 API，客戶端直接發到閘道器自己的埠（見[OpenViking 閘道器](../guides/15-gateway.md)）。

**前提條件**：

- `ov.conf` 中 `gateway.enabled` 為 `true`，並且閘道器程序可以通過 `gateway.url` 訪問。
- OpenViking Server 和閘道器使用同一個管理令牌（預設讀取 `OPENVIKING_GATEWAY_ADMIN_TOKEN`，至少 32 個字元）。
- 呼叫方使用 ADMIN 金鑰或 root 金鑰。USER 金鑰返回 `403`。

**程式碼入口**：

- `openviking/server/routers/gateway.py` - OpenViking Server 代理、角色檢查和帳號隔離
- `openviking_gateway/app.py` - 閘道器管理路由
- `openviking_gateway/models.py` - 上游、上下文配置和金鑰模型

## 代理方式

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET / POST / PUT / DELETE | `/api/v1/admin/gateway/{path}` | 以呼叫方帳號轉發到 `{gateway.url}/admin/{path}` |

發往 `/api/v1/admin/gateway/{path}` 的請求會以相同的方法、查詢引數和請求體轉發到 `{gateway.url}/admin/{path}`。OpenViking Server 用管理令牌替換呼叫方的憑據，並把 `X-OpenViking-Account` 設為呼叫方所在的帳號，因此每次呼叫只能讀取和修改本帳號的閘道器物件。帳號管理員訪問不到其他帳號的資料，呼叫方也無法指定轉發目標。

只有第一段路徑是 `overview`、`logs`、`guides`、`upstreams`、`policies`、`keys`、`users` 或 `tools` 的請求會被轉發。其他路徑以及包含 `..` 的路徑返回 `404`。閘道器返回的狀態碼和響應體原樣返回給呼叫方。

## API 參考

表格中的路徑都相對於 `/api/v1/admin/gateway/`。管理 API 把上下文配置稱為 `policies`。

### 概覽和日誌

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `overview` | 根據最近 10,000 條日誌彙總用量：請求數、輸出 token、首次呼叫和續寫的快取命中率、降級、召回統計和儲存異常，另附 OpenViking 健康狀態和 `log_retention_days` |
| GET | `logs?limit=200` | 最新的請求日誌；`limit` 取 1–1000，預設 200 |
| GET | `guides` | 客戶端應使用的地址：`base_url` 和 `public_url_configured` |
| GET | `tools` | 上下文配置可以提供的 OpenViking 工具：`name`、`description`，以及存在時的 `annotations` |

`tools` 借用本帳號某個閘道器金鑰繫結的 OpenViking 金鑰讀取工具列表。帳號裡還沒有閘道器金鑰時返回空列表；用哪個金鑰都讀不到時返回錯誤。

**HTTP API**

```bash
curl http://localhost:1933/api/v1/admin/gateway/overview \
  -H "X-API-Key: your-admin-key"
```

**響應示例**

```json
{
  "requests": 128,
  "last_request_at": 1785000000.0,
  "output_tokens": 45210,
  "cache": {
    "first_call": {"requests": 40, "input_tokens": 320000, "cached_tokens": 250000, "cache_hit_ratio": 0.78},
    "continuation": {"requests": 88, "input_tokens": 910000, "cached_tokens": 860000, "cache_hit_ratio": 0.95}
  },
  "degradations": {},
  "recall_count": 96,
  "recall_requests": 40,
  "recall_ms": 182.5,
  "capture_issues": {"retrying": 0, "paused": 0},
  "sample_limit": 10000,
  "openviking": {"status": "ok", "healthy": true, "version": "0.4.16", "auth_mode": "api_key"},
  "log_retention_days": 30
}
```

### 上游和上下文配置

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `upstreams` | 列出上游 |
| PUT | `upstreams/{upstream_id}` | 建立或替換上游 |
| DELETE | `upstreams/{upstream_id}` | 刪除上游 |
| POST | `upstreams/{upstream_id}/test` | 檢查閘道器能否訪問服務商的模型列表 |
| GET | `policies` | 列出上下文配置 |
| PUT | `policies/{policy_id}` | 建立或替換上下文配置 |
| DELETE | `policies/{policy_id}` | 刪除上下文配置 |

`upstream_id` 和 `policy_id` 由呼叫方指定。`PUT` 的請求體是完整物件，未知欄位會被拒絕。各欄位的預設值和取值範圍見[配置參考](../guides/22-gateway-operations.md#配置參考)中的上游設定和上下文配置設定。

上游的 `api_key` 和 `headers` 的值只寫不讀，響應中分別換成 `has_api_key` 和 `header_names`。`PUT` 時 `api_key` 留空會保留已存的金鑰；省略 `headers` 會保留所有已存的請求頭，某個請求頭的值留空則保留這個名字已存的值。

如果還有閘道器金鑰在用某個上游或上下文配置，刪除它會返回 `409`，需要先吊銷或更新這些金鑰。

**HTTP API**

```bash
curl http://localhost:1933/api/v1/admin/gateway/upstreams \
  -H "X-API-Key: your-admin-key"
```

**響應示例**

```json
[
  {
    "id": "openai",
    "revision": 2,
    "name": "OpenAI",
    "protocol": "chat",
    "vendor": "openai",
    "base_url": "https://api.openai.com/v1",
    "auth_mode": "managed",
    "has_api_key": true,
    "header_names": [],
    "models": ["gpt-5"],
    "aliases": {},
    "context_windows": {},
    "priority": 0,
    "enabled": true,
    "allow_gateway_tools": true,
    "coding_plan": false,
    "allow_coding_plan": false,
    "cache_min_tokens": 1024
  }
]
```

`upstreams/{upstream_id}/test` 返回 `{"ok": true, "status": 200}`，其中 `status` 是服務商返回的狀態碼；如果 10 秒內連不上服務商，返回 `{"ok": false, "reason": "upstream_unavailable"}`。

### 閘道器金鑰

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `keys` | 列出閘道器金鑰，不含金鑰本身 |
| POST | `keys` | 簽發閘道器金鑰；金鑰只在這次響應中出現 |
| DELETE | `keys/{key_id}` | 吊銷閘道器金鑰 |
| POST | `keys/{key_id}/capture/reset` | 讓某個會話的對話儲存從下一次請求起重新同步 |

`POST keys` 的請求體：

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `name` | string | 是 | 顯示名稱 |
| `openviking_key` | string | 條件必填 | 閘道器金鑰代表的使用者的 OpenViking 金鑰；與 `user_id` 二選一 |
| `user_id` | string | 條件必填 | 呼叫方帳號中的使用者，由 OpenViking Server 讀取這個使用者的金鑰；僅帳號管理員可用 |
| `policy_id` | string | 是 | 上下文配置 |
| `upstream_ids` | string[] | 是 | 至少一個上游 |
| `models` | string[] | 否 | 允許的模型；為空時允許上游提供的所有模型 |

OpenViking 金鑰必須屬於呼叫方帳號中的 USER 或 ADMIN。只有 OpenViking Server 能讀出已存的使用者金鑰時，`user_id` 才可用；啟用了金鑰雜湊時改傳 `openviking_key`。root 呼叫方也必須傳 `openviking_key`，因為 root 金鑰解析出的帳號可能和 Studio 顯示的帳號不同。

已簽發的金鑰不能修改，`PUT keys/{key_id}` 返回 `405`。需要修改時簽發一個新金鑰，再吊銷舊金鑰。

**HTTP API**

```bash
curl -X POST http://localhost:1933/api/v1/admin/gateway/keys \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-admin-key" \
  -d '{"name":"alice laptop","user_id":"alice","policy_id":"default","upstream_ids":["openai"]}'
```

**響應示例**

```json
{
  "id": "3f6c…",
  "revision": 1,
  "name": "alice laptop",
  "policy_id": "default",
  "upstream_ids": ["openai"],
  "models": [],
  "user_id": "alice",
  "prefix": "ovgw_Xk3p9Q",
  "created_at": 1785000000.0,
  "key": "ovgw_Xk3p9Q…"
}
```

`keys/{key_id}/capture/reset` 的請求體是 `{"session": "<會話>", "protocol": "chat"}`，`protocol` 取 `anthropic`、`chat` 或 `responses`。`session` 可以填客戶端傳送的會話請求頭的值（例如 `X-OpenViking-Session`），也可以填請求日誌裡的 `session` 欄位；沒有會話請求頭的會話只能用後者。成功時返回 `{"status": "ready", "message": "…"}`；金鑰或會話不存在時返回 `404`。

### 使用者資料

| 方法 | 路徑 | 說明 |
|------|------|------|
| DELETE | `users/{user_id}/data` | 吊銷使用者的所有閘道器金鑰，並刪除閘道器中這個使用者的對話狀態 |

已經儲存到 OpenViking 的會話不受影響。

## 錯誤

OpenViking Server 自身產生的錯誤使用標準錯誤響應格式：

| 狀態碼 | 錯誤碼 | 原因 |
|--------|--------|------|
| 400 | `INVALID_ARGUMENT` | root 在 `POST keys` 中傳了 `user_id`；`user_id` 不存在 |
| 400 | `INVALID_ARGUMENT` | `POST keys` 同時傳了 `user_id` 和 `openviking_key`（原始狀態碼 422） |
| 403 | `PERMISSION_DENIED` | 呼叫方不是 ROOT 或 ADMIN |
| 404 | `NOT_FOUND` | 路徑不在轉發範圍內 |
| 409 | `CONFLICT` | 服務端讀不出所選使用者的金鑰 |
| 503 | `UNAVAILABLE` | OpenViking 閘道器未啟用、管理令牌未配置，或連不上閘道器（原始狀態碼 502） |

閘道器返回的錯誤保留閘道器的狀態碼，響應體形如 `{"detail": "Unknown context policy"}`：

| 狀態碼 | 原因 |
|--------|------|
| 400 | `POST keys` 指定的上下文配置或上游不存在 |
| 403 | OpenViking 金鑰屬於其他帳號 |
| 404 | 資源、金鑰或會話不存在 |
| 405 | 呼叫了 `PUT keys/{key_id}` |
| 409 | 刪除仍被金鑰使用的上游或上下文配置 |
| 422 | 請求體無效。提交的值可能包含金鑰，所以錯誤資訊不會回顯它們 |

閘道器無法驗證 OpenViking 金鑰時，響應體是 `{"error": {"message": "<原因>"}}`，原因值見[簽發金鑰失敗](../guides/22-gateway-operations.md#簽發金鑰失敗)。

## 相關文件

- [OpenViking 閘道器](../guides/15-gateway.md) - 閘道器的工作方式和客戶端接入
- [OpenViking 閘道器部署與運維](../guides/22-gateway-operations.md) - 部署、在 Studio 中管理閘道器和配置參考
- [管理員](08-admin.md) - 帳號、使用者和角色
