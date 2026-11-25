# Usage/Audit 使用說明

Usage/Audit 是 OpenViking Server 給 Console 使用的產品統計與請求審計模組。它複用
OpenViking 已有的 observability 事件，不要求 Console 直接依賴 Prometheus，也不會在正常
API 請求鏈路裡同步寫統計庫。

## 適用場景

當前模組主要服務 Console P0 頁面：

- 總覽頁首屏：上下文資料量、今日 Token、今日檢索、Agent 概覽
- Token 趨勢：按日期範圍查詢模型 Token 消耗
- 上下文提交熱力圖：按日期和小時段查詢上下文寫入活動
- 請求日誌：分頁查詢請求明細、狀態、耗時和成功率

這套資料是產品語義資料，不是運維指標。QPS、latency histogram、queue depth、cache
hit/miss 等仍然應該看 Prometheus metrics。

## 工作方式

資料流如下：

```text
業務請求 / 模型呼叫
        |
        v
Observability Event Bus
        |
        +--> Metrics subscriber
        |
        +--> Usage/Audit subscriber
                  |
                  v
            Usage/Audit worker
                  |
                  v
            Usage/Audit store
                  |
                  v
          /api/v1/console/* BFF
```

關鍵點：

- Usage/Audit 訂閱共享事件匯流排，不重複散落 Console 專用打點。
- `server.observability.metrics.enabled=false` 不影響 Usage/Audit。
- 請求路徑只做非阻塞事件投遞；寫庫由後臺 worker 批次完成。
- worker 使用 bounded queue；佇列滿時會丟棄統計事件並增加 `dropped_count`。
- 服務關閉時會盡量 flush 剩餘事件；如果已有 batch 正在寫入，會等待它完成，避免尾部審計丟失或重複寫入。

## 配置

預設啟用 Usage/Audit。最小配置可以不寫任何欄位。

完整配置示例：

```json
{
  "server": {
    "observability": {
      "usage_audit": {
        "enabled": true,
        "backend": "sqlite",
        "sqlite_path": "/path/to/usage_audit.sqlite3",
        "queue_size": 10000,
        "batch_size": 500,
        "flush_interval_seconds": 1.0,
        "shutdown_flush_timeout_seconds": 3.0,
        "usage_retention_days": 14,
        "audit_retention_days": 7,
        "audit_retention_per_account": 1000,
        "timezone": "local",
        "inventory_ttl_seconds": 10.0
      }
    }
  }
}
```

欄位說明：

| 欄位 | 預設值 | 說明 |
| --- | --- | --- |
| `enabled` | `true` | 是否啟用 Usage/Audit |
| `backend` | `"sqlite"` | `sqlite`（本地檔案）或 `postgres`（共享 PostgreSQL） |
| `postgres` | `{}` | PostgreSQL 連線引數，選擇 `postgres` 時必填；見下方示例 |
| `sqlite_path` | `null` | SQLite 檔案路徑；為空時使用當前 OpenViking workspace 下的 `_system/usage_audit/usage_audit.sqlite3` |
| `queue_size` | `10000` | 後臺寫入佇列大小 |
| `batch_size` | `500` | 單次批次寫入的最大事件數 |
| `flush_interval_seconds` | `1.0` | worker 定時 flush 間隔 |
| `shutdown_flush_timeout_seconds` | `3.0` | 服務關閉時 flush 等待時間 |
| `usage_retention_days` | `14` | 統計聚合資料保留天數，包含 Token、檢索、上下文寫入熱力圖、Agent 活躍；`0` 表示不按天裁剪 |
| `audit_retention_days` | `7` | 請求審計日誌保留天數；`0` 表示不按天裁剪 |
| `audit_retention_per_account` | `1000` | 每個 account 保留的最新請求審計條數；`0` 表示不按條數裁剪 |
| `timezone` | `"local"` | Console 請求未傳 `timezone` 時的兜底查詢時區；寫入始終按 UTC 儲存。`"local"` 表示 server 程序所在機器/容器的本地時區 |
| `inventory_ttl_seconds` | `10.0` | 上下文當前資料量查詢快取時間 |

本地版預設使用 SQLite。多例項同時提供 Console 時，可選擇共享 PostgreSQL 後端。
所有例項使用相同的 database 和 schema，各自執行後臺 worker。

### PostgreSQL

安裝 `openviking[postgres]`，由管理員一次性執行
[`sql/001_usage_audit_postgres.sql`](sql/001_usage_audit_postgres.sql)。
執行時只校驗版本、列型別、主鍵、文本排序規則及 identity，不建立或遷移表。
PostgreSQL schema 版本獨立管理，當前為 `2`，不使用 SQLite 的版本號。
已使用預覽版 v1 schema 時，由管理員執行
[`sql/002_usage_audit_deletion_fence.sql`](sql/002_usage_audit_deletion_fence.sql)；
升級前停止所有寫入例項，遷移後全部部署新版本，不混跑舊 writer。

```json
{
  "server": {
    "observability": {
      "usage_audit": {
        "backend": "postgres",
        "postgres": {
          "host": "127.0.0.1",
          "port": 5432,
          "user": "openviking_runtime",
          "password": "<password>",
          "database": "openviking",
          "schema": "openviking_usage_audit",
          "maxsize": 10,
          "connect_timeout": 10,
          "lock_timeout_ms": 1000,
          "sslmode": "verify-full",
          "sslrootcert": "/path/to/ca.pem"
        }
      }
    }
  }
}
```

`user` 和 `database` 必填，`host` 預設 `127.0.0.1`，`port` 預設 `5432`。
`schema` 預設 `openviking_usage_audit`，只接受 1–63 字元的小寫 SQL 識別符號；
自定義 schema 時先替換建表指令碼中所有同名 schema。
連線引數還支援 `sslcert`、`sslkey`，不接受 DSN。`sslmode` 預設 `prefer`，
生產環境應按資料庫 TLS 配置設定校驗模式。
`lock_timeout_ms` 預設 `1000`，範圍 `1..60000`，在每個寫入/刪除事務中限制
advisory lock 和表/行鎖的單次等待時間。超時回滾整批寫入，worker 按現有 best-effort
語義記錄失敗並丟棄該批；刪除超時向呼叫者報錯。關閉仍等待已開始的事務完成，
該配置限制資料庫鎖等待，不將 shutdown timeout 改為強制取消期限。
runtime role 需要 schema 的 `USAGE`、表的 `SELECT/INSERT/UPDATE/DELETE`，
以及 sequence 的 `USAGE/SELECT`，無需 `CREATE` 許可權。

四類投影的累加和裁剪在同一事務中完成，並使用 account 級事務 advisory lock
協調多例項寫入與刪除。Usage 按當前 batch 中各 account 最新 UTC 日期裁剪；
Audit 按已持久化的最新 UTC 日期裁剪，再按插入 ID 保留最近 N 條，
與 SQLite 口徑一致。查詢始終限制 account，支援 user 過濾及讀端時區轉換。
Audit 分頁的計數和明細使用同一資料庫快照。

刪除還會在同一事務中遞增共享刪除版本並儲存帳號或使用者範圍的 fence。
事件入隊時捕獲 writer 已觀察到的版本；其他例項隨後寫入舊佇列時會先比較版本，
拒絕已刪除範圍的舊事件，再生成投影。判斷不依賴事件時間或機器時鐘。
writer 每次寫入會重新整理版本；遠端刪除後、重新整理前接收的同範圍新事件也會保守丟棄，
重新整理後接收的事件可以正常寫入，包括重新建立的同名身份。
fence 不隨投影保留策略或帳號資料刪除而清理，以防止舊佇列重新寫回。

切換 backend 不會自動遷移已有 SQLite 資料。事件佇列仍是程序內 bounded queue，
不提供重啟恢復或 exactly-once 投遞；資料庫事務只保證一個 batch 的原子寫入。

## 資料口徑

### Token

來自模型呼叫事件：

| 事件 | 當前 Console 展示口徑 |
| --- | --- |
| `vlm.call` | `prompt_tokens` 計入 `vlm_input`，`completion_tokens` 計入 `vlm_output` |
| `embedding.call` | `prompt_tokens` 計入 `embedding_input` |
| `rerank.call` | 已可落庫，當前 Console summary/series 暫不展示 |
| `bot.call` | VikingBot（聊天與 Compile）的模型呼叫；Bot 以獨立程序執行，經 `POST /api/v1/console/usage/bot` 以請求使用者身分回報；僅接受本伺服器以 `--with-bot` 管理的 Bot（以共用的 `X-Gateway-Token` 驗證）。`prompt_tokens` 計入 `bot_input`，`completion_tokens` 計入 `bot_output` |

### 今日檢索

來自 HTTP 請求完成事件 `http.request`：

| API route | operation |
| --- | --- |
| `POST /api/v1/search/find` | `find` |
| `POST /api/v1/search/search` | `search` |

`2xx` 和 `3xx` 記為 `success`，`4xx/5xx` 記為 `error`。Dashboard 今日檢索只展示成功請求數。

`usage_retrieval_hourly.result_count` 累加成功 HTTP 響應中的最終結果條數：列表模式使用
`total`，`search` 的 context 模式使用 `entries` 長度。失敗請求只增加請求數。
該值隨 `http.request` 寫入，不累加內部 `retrieval.completed` 的結果數；一次 HTTP 請求
可能觸發多個內部檢索並去重、截斷，因此不能直接與程序啟動以來的 retrieval observer
計數對齊。現有統計範圍仍為上表兩個端點，不包含 MCP 或已棄用的 `/recall`。

結果總數不是零結果請求數，僅憑 `request_count` 和 `result_count` 無法還原零結果率。
修復前已有桶中的結果數仍為歷史零值，不會回填。

### 上下文提交熱力圖

來自成功的公開寫請求：

| API route | operation |
| --- | --- |
| `POST /api/v1/resources` | `add_resource` |
| `POST /api/v1/skills` | `add_skill` |
| `POST /api/v1/sessions/{session_id}/messages` | `session_add_message` |
| `POST /api/v1/sessions/{session_id}/commit` | `session_commit` |

只有 `2xx/3xx` 會進入上下文提交統計。

### 上下文資料量

Dashboard 首屏的上下文資料量是當前狀態查詢，不是歷史事件累加：

- `files`：讀取 `viking://resources` 的 `stat.count`
- `skills`：讀取當前 Agent `skills` 根目錄的 `stat.count`
- `memories`：讀取當前 User 和當前 Agent 的 `memories` 根目錄 `stat.count` 後求和

`stat.count` 是底層 `VikingFS.stat()` 暴露的目錄計數字段。Usage/Audit 不自己拼
vector filter，也不從歷史寫入事件累計當前庫存。

這部分會走 `inventory_ttl_seconds` 快取，避免 Console 重新整理頻繁打到底層儲存。業務根目錄
不存在時按 0 處理，避免新環境或空租戶反覆刷 warning。

### 請求審計

請求審計來自 `http.request`，保留欄位：

- `request_id`
- `account_id`
- `user_id`
- `method`
- `route`
- `api_type`
- `status_code`
- `duration_ms`
- `error_code`（僅標準錯誤響應）
- `error_message`（僅標準錯誤響應）
- `error_details`（僅標準錯誤響應，可空）
- `created_at`

錯誤欄位來自 OpenViking 已返回給呼叫方的標準錯誤結構，不讀取或快取 HTTP response
body。`error_details` 經過憑據脫敏和大小限制；它可能包含被拒絕的引數值，但不會額外儲存
原始 request body、header、query string、stack trace 或 exception text。

以下 route 不進入審計：

- `/metrics`
- `/health`
- `/ready`
- `/docs`
- `/docs/oauth2-redirect`
- `/redoc`
- `/openapi.json`
- `/favicon.ico`
- `/favicon.png`
- `/apple-touch-icon.png`
- `/api/v1/console/*`

## Console BFF API

所有介面都在 OV Server 側：

```text
/api/v1/console/*
```

Console 前端通過 Console server 的 allowlist proxy 訪問：

```text
/console/api/v1/ov/console/dashboard/summary
/console/api/v1/ov/console/tokens
/console/api/v1/ov/console/context-commits
/console/api/v1/ov/console/audit
```

許可權要求：

- `ROOT` 和 `ADMIN` 可以訪問
- 普通 `USER` 返回 `403 PERMISSION_DENIED`

### Dashboard Summary

```text
GET /api/v1/console/dashboard/summary
```

引數：

| 引數 | 必填 | 說明 |
| --- | --- | --- |
| `timezone` | 否 | IANA 時區名（如 `Asia/Shanghai`）；省略時回退到 server 時區，用於確定"今日"的時區邊界 |

返回示例：

```json
{
  "status": "ok",
  "result": {
    "context_counts": {
      "files": 12,
      "skills": 3,
      "memories": 8,
      "total": 23
    },
    "today_tokens": {
      "vlm_input": 1000,
      "vlm_output": 500,
      "embedding_input": 200,
      "total": 1700
    },
    "today_retrievals": {
      "find": 10,
      "search": 4,
      "total": 14
    },
    "tokens_per_minute": {
      "vlm_input": 10.0,
      "vlm_output": 5.0,
      "embedding_input": 1.7,
      "total": 16.7,
      "window_minutes": 90
    }
  }
}
```

`tokens_per_minute` 是從上一個 UTC 整點到現在的平均每分鐘 Token 數（視窗 60–120 分鐘）。Token 以 UTC 小時粒度落庫，因此無法提供精確的滑動 60 分鐘視窗；`window_minutes` 為實際的分母。

如果 Usage/Audit 被關閉或尚未初始化，返回：

```json
{
  "status": "ok",
  "result": {
    "enabled": false,
    "message": "Usage/Audit is disabled or not initialized."
  }
}
```

### Token Series

```text
GET /api/v1/console/tokens?start_date=2026-05-01&end_date=2026-05-12&bucket=day
```

引數：

| 引數 | 必填 | 說明 |
| --- | --- | --- |
| `start_date` | 是 | 開始日期，格式 `YYYY-MM-DD`（按 `timezone` 指定的時區解釋） |
| `end_date` | 是 | 結束日期，格式 `YYYY-MM-DD`（按 `timezone` 指定的時區解釋） |
| `bucket` | 否 | 當前僅支援 `day` |
| `timezone` | 否 | IANA 時區名（如 `Asia/Shanghai`）；省略時回退到 server 時區，返回的 `date` 分桶按該時區 |

返回中會補齊日期範圍內沒有資料的日期。

### Token Rate (TPM)

```text
GET /api/v1/console/tokens/rate?window=24h
```

`window` 可選 `1h`、`6h`、`24h`（預設）、`7d`，對應分桶 1、1、5、60 分鐘。資料來自分鐘粒度表 `usage_token_minute`（與小時表一同寫入、按 `usage_retention_days` 清理），只有升級後產生的 Token 才有分鐘資料。

返回示例：

```json
{
  "window": "24h",
  "bucket_minutes": 5,
  "start": "2026-05-11T10:35:00+00:00",
  "end": "2026-05-12T10:35:00+00:00",
  "items": [
    {
      "start": "2026-05-12T10:20:00+00:00",
      "vlm_input": 100.0,
      "vlm_output": 0.0,
      "embedding_input": 0.0,
      "rerank": 0.0,
      "total": 100.0,
      "peak_total": 400
    }
  ],
  "peak": {
    "minute": "2026-05-12T10:21:00+00:00",
    "vlm_input": 400,
    "vlm_output": 0,
    "embedding_input": 0,
    "rerank": 0,
    "total": 400
  },
  "average_total": 0.3
}
```

- `items[].vlm_input/vlm_output/embedding_input/rerank/total`：該分桶的平均每分鐘 Token（只除以已經過去的分鐘數）。`rerank` 為 rerank 輸入與輸出之和，並計入 `total`、`peak_total`、`peak` 與 `average_total`。
- `items[].peak_total`：該分桶內最忙那一分鐘的 Token 總數。
- `peak`：整個區間內最忙的一分鐘（UTC 分鐘起點），沒有 Token 時為 `null`。適合用來評估供應商 TPM 限額。
- `average_total`：整個區間的平均每分鐘 Token。

### Context Commits

```text
GET /api/v1/console/context-commits?start_date=2026-05-01&end_date=2026-05-12&bucket=4h
```

引數：

| 引數 | 必填 | 說明 |
| --- | --- | --- |
| `start_date` | 是 | 開始日期，格式 `YYYY-MM-DD`（按 `timezone` 指定的時區解釋） |
| `end_date` | 是 | 結束日期，格式 `YYYY-MM-DD`（按 `timezone` 指定的時區解釋） |
| `bucket` | 否 | `hour` 或 `4h`，預設 `hour` |
| `timezone` | 否 | IANA 時區名（如 `Asia/Shanghai`）；省略時回退到 server 時區，返回的 `date` / `hour` 分桶按該時區 |

返回中會補齊日期和小時段範圍內沒有資料的 bucket。

### Audit Logs

```text
GET /api/v1/console/audit?page=1&page_size=20&status=success,error&api_type=search.find
```

引數：

| 引數 | 必填 | 說明 |
| --- | --- | --- |
| `page` | 否 | 頁碼，從 `1` 開始 |
| `page_size` | 否 | 每頁條數，範圍 `1..100` |
| `request_id` | 否 | 精確匹配 request id |
| `status` | 否 | 可重複傳，也可逗號分隔 |
| `api_type` | 否 | 可重複傳，也可逗號分隔 |

`status` 支持：

- `success` / `ok`：`2xx` 和 `3xx`
- `2xx`
- `3xx`
- `error` / `failed`：`4xx/5xx`
- `4xx`、`5xx` 等通配段
- 具體狀態碼，例如 `404`

返回字段：

```json
{
  "status": "ok",
  "result": {
    "total": 123,
    "success_rate": 0.98,
    "page": 1,
    "page_size": 20,
    "items": []
  }
}
```

`success_rate` 使用當前篩選條件下的 `2xx/3xx` 佔比。

## 本地驗證

啟動 server 後，可以通過請求觸發資料：

```bash
curl -X POST "http://127.0.0.1:1933/api/v1/search/find" \
  -H "Authorization: Bearer $OPENVIKING_API_KEY" \
  -H "X-OpenViking-Account: default" \
  -H "X-OpenViking-User: default" \
  -H "Content-Type: application/json" \
  -d '{"query":"hello","limit":3}'
```

查詢 Console BFF：

```bash
curl "http://127.0.0.1:1933/api/v1/console/dashboard/summary" \
  -H "Authorization: Bearer $OPENVIKING_API_KEY" \
  -H "X-OpenViking-Account: default" \
  -H "X-OpenViking-User: default" \
```

如果使用 Console server，則訪問 `/console/api/v1/ov/console/*` 代理路徑。

## 測試

相關單測：

```bash
.venv/bin/python -m pytest \
  tests/observability/test_events.py \
  tests/observability/test_usage_audit_store.py \
  tests/observability/test_usage_audit_worker.py \
  tests/observability/test_console_router.py \
  tests/observability/test_usage_audit_runtime.py \
  tests/observability/test_usage_audit_inventory.py \
  tests/misc/test_console_proxy.py
```

相關 lint：

```bash
.venv/bin/python -m ruff check \
  openviking/observability/events.py \
  openviking/observability/usage_audit \
  openviking/server/routers/console.py \
  tests/observability
```

## 常見問題

### Console 查詢為什麼返回 `enabled=false`？

通常是 `server.observability.usage_audit.enabled=false`，或者 Usage/Audit runtime 沒有初始化成功。
先看 server 啟動日誌中是否有 `Usage/Audit store initialized with sqlite backend`。

### 為什麼 Dashboard 今天沒有 Token？

確認模型呼叫事件是否觸發：

- VLM 需要產生 `vlm.call`
- Embedding 需要產生 `embedding.call`

統計資料寫入時按 UTC 儲存；Console 查詢會優先使用請求裡的 `timezone` 引數做讀端分桶。
如果請求沒有傳 `timezone`，才會使用 `server.observability.usage_audit.timezone` 作為兜底。

### 為什麼請求日誌裡沒有 Console 自己的請求？

這是預期行為。`/api/v1/console/*` 和 `/console/*` 會被排除，避免 Console 頁面重新整理汙染產品請求審計。

### 為什麼普通使用者訪問 Console BFF 是 403？

Console BFF 查詢的是帳號級聚合和審計明細，當前只允許 `ROOT` / `ADMIN` 訪問。

### SQLite 檔案在哪裡？

如果沒有配置 `sqlite_path`，預設在 OpenViking workspace 下：

```text
<workspace>/_system/usage_audit/usage_audit.sqlite3
```

可以通過 `server.observability.usage_audit.sqlite_path` 顯式指定。

### 生產多例項怎麼部署？

配置 `backend=postgres`，預建 schema，並讓各例項連線同一 database/schema。
該配置只共享 Usage/Audit 投影，業務儲存、鎖及其他多例項條件仍需獨立配置。

真實 PostgreSQL 合同測試使用隨機隔離 schema，測試後自動刪除：

```bash
OV_TEST_USAGE_AUDIT_POSTGRES='host=localhost dbname=testdb user=testuser' \
  python -m pytest tests/observability/test_usage_audit_postgres.py
```

未設定該環境變數時資料庫測試會 skip，不能據此證明真實 PostgreSQL 行為。
