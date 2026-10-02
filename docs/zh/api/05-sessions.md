# 會話

會話用於管理對話狀態、跟蹤上下文使用情況，並提取長期記憶。會話採用分層儲存（L0/L1/L2）來最佳化 token 使用：
- L0（abstract）: 會話概覽摘要
- L1（overview）: 關鍵決策和總結
- L2（messages）: 完整消息

會話儲存在當前使用者名稱空間下：

```text
viking://user/{user_id}/sessions/{session_id}
```

Session API 按認證使用者作用域訪問會話，並返回 canonical user session URI。
基於 URI 的 API 也可以接受向後相容的 `viking://session/{session_id}` 別名，
該別名會在同一個使用者上下文中解析。

## API 參考

### create_session()

#### 1. API 實現介紹

建立新會話。會話是對話的容器，用於儲存訊息、跟蹤上下文使用情況，並支援提交以提取長期記憶。

**處理流程**：
1. 生成或使用提供的 session_id
2. 初始化會話後設資料（建立時間、使用者資訊等）
3. 在儲存中建立會話目錄結構
4. 返回會話資訊

**程式碼入口**：
- `openviking/session/session.py:Session.__init__()` - Session 核心類
- `openviking/session/auto_commit_policy.py:AutoCommitPolicy` - 自動 commit 策略的預設值與校驗
- `openviking/server/routers/sessions.py:create_session()` - HTTP 路由
- `sdk/python/openviking_sdk/client.py:AsyncHTTPClient.create_session()` - Python SDK
- `crates/ov_cli/src/commands/session.rs:new_session()` - CLI 命令

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| session_id | str | 否 | None | 會話 ID。如果為 None，則建立一個自動生成 ID 的新會話 |
| memory_policy | object | 否 | None | 會話預設的記憶抽取策略。可選的 `self` 和 `peer` 開關控制寫入目標；可選的 `working_memory.enabled=false` 跳過 archive summary；可選的頂層 `memory_types` 將抽取限制為指定的 enabled memory schema。包含 `experiences` 時會自動啟用 `cases` 和 `trajectories`；不包含 `experiences` 時，顯式傳入的 `cases` 和 `trajectories` 會被忽略。所有 `enabled` 值都應使用 JSON 布林值。舊版 boolean-like 值暫時仍相容（字串 `"false"` 會正確解析為 false），但會產生棄用警告。未傳或為 `null` 時允許所有 enabled memory schema。非法結構或未知 memory type 會以 `InvalidArgumentError` 拒絕。 |
| auto_commit_policy | object | 否 | None | 可選的自動 commit 策略（見下表）。傳入的欄位會被校驗並 clamp 到取值範圍，然後合併到預設值之上；最終生效的策略會在響應的 `result.auto_commit_policy` 中返回，並持久化到 session meta。省略時，新 Session 先繼承 `server.user_config_defaults.auto_commit_policy`，再沿用現有 `memory.session_auto_commit.default_enabled` 行為。之後可通過 `update_session_config()` 部分更新或停用該策略。 |

`auto_commit_policy` 欄位（均為可選；存在 policy 時，未傳欄位回退到預設值）：

| 欄位 | 型別 | 預設值 | 上限 | 說明 |
|------|------|--------|------|------|
| `pending_token_threshold` | int | 150000 | 1000000 | 當未提交的 pending token 超過該值（嚴格大於）時，會在訊息寫入後觸發一次自動 commit。 |
| `message_count_threshold` | int | 100 | 1000 | 當未提交的 live message 數量超過該值（嚴格大於）時，會在訊息寫入後觸發一次自動 commit。 |
| `idle_timeout_seconds` | int | 86400 | 604800 | 有未提交內容的 session 在空閒這麼多秒後，進入服務端 idle scheduler 的處理範圍。idle 觸發的 commit 會歸檔全部積壓訊息，並忽略 `keep_recent_count`。 |
| `keep_recent_count` | int | 0 | 500 | 閾值觸發的自動 commit 後保留（不歸檔）的最近 live message 數量。idle 超時觸發的 commit 會忽略該值並歸檔所有訊息。 |
| `min_commit_interval_seconds` | int | 0 | 604800 | 兩次自動 commit 之間的最小間隔秒數（節流）。 |

所有欄位最小值為 `0`，會被 clamp 到 `[0, 上限]`。未知欄位會以 `InvalidArgumentError` 拒絕。

#### 3. 使用示例

**HTTP API**

```http
POST /api/v1/sessions
```

```bash
# 建立新會話（自動生成 ID）
curl -X POST http://localhost:1933/api/v1/sessions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key"

# 建立指定 ID 的新會話
curl -X POST http://localhost:1933/api/v1/sessions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"session_id": "my-custom-session-id"}'

# 建立帶自定義自動 commit 策略的新會話
curl -X POST http://localhost:1933/api/v1/sessions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "auto_commit_policy": {
      "pending_token_threshold": 8000,
      "message_count_threshold": 40,
      "idle_timeout_seconds": 600,
      "keep_recent_count": 10,
      "min_commit_interval_seconds": 0
    }
  }'
```

**Python SDK**

```python
import openviking_sdk as ov

# 使用 HTTP 客戶端
client = ov.AsyncHTTPClient(url="http://localhost:1933", api_key="your-key")
await client.initialize()

# 建立新會話（自動生成 ID）
result = await client.create_session()
print(f"Session ID: {result['session_id']}")

# 建立指定 ID 的新會話
result = await client.create_session(session_id="my-custom-session-id")
print(f"Session ID: {result['session_id']}")

# 建立帶自定義自動 commit 策略的新會話
result = await client.create_session(
    options={
        "auto_commit_policy": {
            "pending_token_threshold": 8000,
            "message_count_threshold": 40,
            "idle_timeout_seconds": 600,
            "keep_recent_count": 10,
            "min_commit_interval_seconds": 0,
        },
    },
)
print(result["auto_commit_policy"])
```

**TypeScript SDK**

```typescript
const session = await client.createSession();
console.log(session);
```

**Go SDK**

```go
session, err := client.CreateSession(ctx, &openviking.CreateSessionOptions{
    SessionID: "my-custom-session-id",
})
if err != nil {
    return err
}
fmt.Println(session["session_id"])
```

**CLI**

```bash
ov session new
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "session_id": "a1b2c3d4",
    "uri": "viking://user/alice/sessions/a1b2c3d4",
    "user": {
      "account_id": "default",
      "user_id": "alice"
    },
    "auto_commit_policy": null
  },
  "time": 0.1
}
```

---

### list_sessions()

#### 1. API 實現介紹

列出當前使用者的所有會話。返回會話 ID 和 URI 資訊，用於進一步操作會話。

**程式碼入口**：
- `openviking/server/routers/sessions.py:list_sessions()` - HTTP 路由
- `sdk/python/openviking_sdk/client.py:AsyncHTTPClient.list_sessions()` - Python SDK
- `crates/ov_cli/src/commands/session.rs:list_sessions()` - CLI 命令

#### 2. 介面和引數說明

**引數**

無引數。

#### 3. 使用示例

**HTTP API**

```http
GET /api/v1/sessions
```

```bash
curl -X GET http://localhost:1933/api/v1/sessions \
  -H "X-API-Key: your-key"
```

**Python SDK**

```python
from openviking_sdk import AsyncHTTPClient

client = AsyncHTTPClient(url="http://localhost:1933", api_key="your-key")
await client.initialize()

sessions = await client.list_sessions()
for s in sessions:
    print(f"{s['session_id']} -> {s['uri']}")
```

**TypeScript SDK**

```typescript
console.log(await client.listSessions());
```

**Go SDK**

```go
sessions, err := client.ListSessions(ctx)
if err != nil {
    return err
}
for _, session := range sessions {
    fmt.Println(session)
}
```

**CLI**

```bash
ov session list
```

**響應示例**

```json
{
  "status": "ok",
  "result": [
    {
      "session_id": "a1b2c3d4",
      "uri": "viking://user/alice/sessions/a1b2c3d4",
      "is_dir": true
    },
    {
      "session_id": "e5f6g7h8",
      "uri": "viking://user/alice/sessions/e5f6g7h8",
      "is_dir": true
    }
  ],
  "time": 0.1
}
```

---

### get_session()

#### 1. API 實現介紹

獲取會話詳情，包括後設資料、訊息統計、提交歷史等。支援在會話不存在時自動建立。

**返回欄位說明**：
- `message_count`: 當前 live session 中尚未歸檔的訊息數
- `total_message_count`: 已歸檔訊息與當前 live 訊息的累計總數（舊會話可能不返回此欄位）
- `commit_count`: 成功提交的次數
- `memories_extracted`: 各類記憶的提取數量統計
- `last_commit_at`: 最後一次提交的時間
- `auto_commit_policy`: 填充預設值後的生效自動 commit 策略；未啟用時為 `null`

**程式碼入口**：
- `openviking/session/session.py:Session.load()` - 會話載入
- `openviking/server/routers/sessions.py:get_session()` - HTTP 路由
- `sdk/python/openviking_sdk/client.py:AsyncHTTPClient.get_session()` - Python SDK
- `crates/ov_cli/src/commands/session.rs:get_session()` - CLI 命令

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| session_id | str | 是 | - | 會話 ID |
| auto_create | bool | 否 | False | 會話不存在時是否自動建立 |

#### 3. 使用示例

**HTTP API**

```http
GET /api/v1/sessions/{session_id}?auto_create=false
```

```bash
curl -X GET http://localhost:1933/api/v1/sessions/a1b2c3d4 \
  -H "X-API-Key: your-key"
```

**Python SDK**

```python
import openviking_sdk as ov

client = ov.AsyncHTTPClient(url="http://localhost:1933", api_key="your-key")
await client.initialize()

# 獲取已有會話（不存在時拋 NotFoundError）
info = await client.get_session(session_id="a1b2c3d4")
print(f"Live Messages: {info['message_count']}")
print(f"Total Messages: {info.get('total_message_count', 'n/a')}")
print(f"Commits: {info['commit_count']}")

# 獲取或建立會話
info = await client.get_session(session_id="a1b2c3d4", auto_create=True)
```

**TypeScript SDK**

```typescript
console.log(await client.getSession("session-id"));
```

**Go SDK**

```go
// 獲取已有會話
info, err := client.GetSession(ctx, "a1b2c3d4", nil)
if err != nil {
    return err
}
fmt.Println(info["message_count"])

// 獲取或建立會話
info, err = client.GetSession(ctx, "a1b2c3d4", &openviking.GetSessionOptions{
    AutoCreate: true,
})
if err != nil {
    return err
}
fmt.Println(info["session_id"])
```

**CLI**

```bash
ov session get a1b2c3d4
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "session_id": "a1b2c3d4",
    "created_at": "2026-03-23T10:00:00+08:00",
    "updated_at": "2026-03-23T11:30:00+08:00",
    "message_count": 5,
    "total_message_count": 20,
    "commit_count": 3,
    "memories_extracted": {
      "profile": 1,
      "preferences": 2,
      "entities": 3,
      "events": 1,
      "identity": 1,
      "soul": 1,
      "cases": 2,
      "trajectories": 1,
      "experiences": 2,
      "tools": 0,
      "skills": 0,
      "total": 14
    },
    "last_commit_at": "2026-03-23T11:00:00+08:00",
    "llm_token_usage": {
      "prompt_tokens": 5200,
      "completion_tokens": 1800,
      "total_tokens": 7000,
      "cached_tokens": 1200,
      "reasoning_tokens": 800
    },
    "user": {
      "account_id": "default",
      "user_id": "alice"
    },
    "pending_tokens": 450,
    "auto_commit_policy": {
      "pending_token_threshold": 150000,
      "message_count_threshold": 100,
      "idle_timeout_seconds": 86400,
      "keep_recent_count": 0,
      "min_commit_interval_seconds": 0
    }
  }
}
```

---

### update_session_config()

#### 1. API 實現介紹

部分更新已有 session 的可變配置。修改會在後續訊息寫入、idle 掃描和 commit
中生效。只有 `/api/v1/sessions/{session_id}/config` 子路徑接受 `PATCH`；基礎
`/api/v1/sessions/{session_id}` 端點不支援該方法。

**程式碼入口**：
- `openviking/server/routers/sessions.py:update_session_config()` - HTTP 路由
- `openviking/service/session_service.py:SessionService.update_config()` - 配置校驗與更新
- `sdk/python/openviking_sdk/client.py:update_session_config()` - Python SDK
- `sdk/typescript/src/client.ts:updateSessionConfig()` - TypeScript SDK
- `sdk/go/sessions.go:UpdateSessionConfig()` - Go SDK
- `crates/ov_cli/src/commands/session.rs:set_session_config()` - CLI 命令

#### 2. 介面和引數說明

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| session_id | string | 是 | - | URL 路徑中的 session ID |
| memory_extraction_config | object | 否 | 未傳 | 可變的抽取配置。目前支援 `events.tags`，其值為嚴格 `key=value` 字串陣列。省略時保留現有 tags；傳 `events.tags=[]` 時清空。系統會 trim、轉為小寫並去重。 |
| auto_commit_policy | object 或 null | 否 | 未傳 | object 只把已提供的策略欄位合併到現有策略中，並沿用 `create_session()` 記錄的校驗、clamp、預設值和上限。傳 `null` 停用自動 commit；省略該欄位則保持策略不變。策略內部的單個欄位不能為 `null`。 |
| telemetry | boolean 或 object | 否 | `false` | 傳 `true` 或 `{"summary": true}` 時在響應中包含本次操作的 telemetry summary；`false` 時省略。 |

空請求物件是合法的 no-op，並會返回當前生效配置。未知請求欄位會被拒絕。
響應始終返回補齊預設值後的生效策略；自動 commit 已停用時返回 `null`。

#### 3. 使用示例

**HTTP API**

```http
PATCH /api/v1/sessions/{session_id}/config
```

```bash
# 合併一個策略欄位，並替換事件記憶的預設 tags
curl -X PATCH http://localhost:1933/api/v1/sessions/a1b2c3d4/config \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "memory_extraction_config": {
      "events": {"tags": ["team=search", "channel=app"]}
    },
    "auto_commit_policy": {"message_count_threshold": 25},
    "telemetry": true
  }'

# 停用自動 commit，同時不修改事件記憶 tags
curl -X PATCH http://localhost:1933/api/v1/sessions/a1b2c3d4/config \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"auto_commit_policy": null}'
```

**Python SDK**

```python
result = client.update_session_config(
    session_id="a1b2c3d4",
    options={
        "memory_extraction_config": {
            "events": {"tags": ["team=search", "channel=app"]}
        },
        "auto_commit_policy": {"message_count_threshold": 25},
    },
)
```

**TypeScript SDK**

```typescript
const result = await client.updateSessionConfig("a1b2c3d4", {
  memoryExtractionConfig: {
    events: { tags: ["team=search", "channel=app"] },
  },
  autoCommitPolicy: { message_count_threshold: 25 },
});
```

**Go SDK**

```go
policy := map[string]any{"message_count_threshold": 25}
result, err := client.UpdateSessionConfig(ctx, "a1b2c3d4", &openviking.UpdateSessionConfigOptions{
    MemoryExtractionConfig: map[string]any{
        "events": map[string]any{"tags": []string{"team=search", "channel=app"}},
    },
    AutoCommitPolicy: &policy,
})
```

**CLI**

```bash
ov session config set a1b2c3d4 \
  --event-tags team=search,channel=app \
  --auto-commit-policy-json '{"message_count_threshold":25}'

# 清空預設 tags，或停用自動 commit
ov session config set a1b2c3d4 --no-event-tags
ov session config set a1b2c3d4 --no-auto-commit
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "session_id": "a1b2c3d4",
    "auto_commit_policy": {
      "pending_token_threshold": 150000,
      "message_count_threshold": 25,
      "idle_timeout_seconds": 86400,
      "keep_recent_count": 0,
      "min_commit_interval_seconds": 0
    },
    "memory_extraction_config": {
      "events": {
        "tags": ["team=search", "channel=app"]
      }
    }
  },
  "telemetry": {
    "id": "tm_xxx",
    "summary": {
      "operation": "session.update_config",
      "status": "ok",
      "duration_ms": 4.2
    }
  }
}
```

---

### list_tool_results()

列出會話中因體積較大而外接儲存的工具結果。

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `session_id` | string | 是 | - | 會話 ID |
| `tool_name` | string | 否 | - | 按工具名過濾 |
| `limit` | integer | 否 | `50` | 最大返回數量 |

**HTTP API**

```http
GET /api/v1/sessions/{session_id}/tool-results
```

```bash
curl --get http://localhost:1933/api/v1/sessions/session-id/tool-results \
  -H "X-API-Key: your-key" \
  --data-urlencode "tool_name=search" \
  --data-urlencode "limit=50"
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "tool_results": [
      {
        "tool_result_id": "tr_search_a1b2c3",
        "tool_name": "search",
        "original_chars": 48210,
        "preview_chars": 2000,
        "mime_type": "text/plain",
        "synopsis_kind": "text",
        "storage_uri": "viking://user/default/sessions/session-id/tool-results/tr_search_a1b2c3",
        "offset_unit": "unicode_code_point"
      }
    ]
  }
}
```

### read_tool_result()

按 Unicode 字元範圍讀取一個外接工具結果。

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `session_id` | string | 是 | - | 會話 ID |
| `tool_result_id` | string | 是 | - | 工具結果 ID |
| `offset` | integer | 否 | `0` | 起始字符位置 |
| `limit` | integer | 否 | `20000` | 最大字元數；`-1` 表示讀取到結尾 |
| `include_metadata` | boolean | 否 | `true` | 是否返回後設資料 |

**HTTP API**

```http
GET /api/v1/sessions/{session_id}/tool-results/{tool_result_id}
```

```bash
curl --get http://localhost:1933/api/v1/sessions/session-id/tool-results/tool-result-id \
  -H "X-API-Key: your-key" \
  --data-urlencode "offset=0" \
  --data-urlencode "limit=20000"
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "tool_result_id": "tr_search_a1b2c3",
    "content": "工具返回的文本片段……",
    "offset": 0,
    "limit": 20000,
    "offset_unit": "unicode_code_point",
    "total_chars": 48210,
    "has_more": true,
    "metadata": {
      "tool_name": "search",
      "mime_type": "text/plain",
      "sha256": "..."
    }
  }
}
```

`include_metadata=false` 時省略 `metadata`。繼續讀取時，將下一次請求的 `offset` 設為當前 `offset` 加上 `content` 的 Unicode 字元數。

### search_tool_result()

在一個外接工具結果中搜索文本，並返回命中位置附近的上下文。

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `q` | string | 是 | - | 搜索文本 |
| `limit` | integer | 否 | `20` | 最大命中數 |
| `context_chars` | integer | 否 | `300` | 每個命中前後的上下文字元數 |

**HTTP API**

```http
GET /api/v1/sessions/{session_id}/tool-results/{tool_result_id}/search?q={query}
```

```bash
curl --get http://localhost:1933/api/v1/sessions/session-id/tool-results/tool-result-id/search \
  -H "X-API-Key: your-key" \
  --data-urlencode "q=authentication" \
  --data-urlencode "limit=20"
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "tool_result_id": "tr_search_a1b2c3",
    "matches": [
      {
        "offset": 1284,
        "offset_unit": "unicode_code_point",
        "snippet": "...authentication failed because..."
      }
    ]
  }
}
```

外接工具結果端點當前由 Server 和 Web Studio 使用，公共 SDK 與 CLI 暫未提供封裝，因此以上小節只展示 HTTP Tab。

---

### get_session_context()

#### 1. API 實現介紹

獲取供上下文組裝使用的會話上下文。該介面返回最新的歸檔摘要和當前活躍訊息，用於 LLM 上下文構建。

**返回欄位說明**：
- `latest_archive_overview`: 最新一個已完成歸檔的 overview 文本，在 token budget 足夠時返回
- `pre_archive_abstracts`: 保持 API 向下相容，返回空陣列
- `messages`: 最新已完成歸檔之後的所有未完成歸檔訊息，再加上當前 live session 訊息
- `estimatedTokens`: 預估總 token 數
- `stats`: 統計資訊

**token budget 分配策略**：
1. 先分配給當前活躍訊息
2. 剩餘預算優先給最新歸檔的 overview
3. pre_archive_abstracts 目前不返回

**程式碼入口**：
- `openviking/session/session.py:Session.get_session_context()` - 核心實現
- `openviking/server/routers/sessions.py:get_session_context()` - HTTP 路由
- `sdk/python/openviking_sdk/client.py:AsyncHTTPClient.get_session_context()` - Python SDK
- `crates/ov_cli/src/commands/session.rs:get_session_context()` - CLI 命令

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| session_id | str | 是 | - | 會話 ID |
| token_budget | int | 否 | 128000 | active messages 之後留給 assembled archive payload 的非負 token 預算 |

#### 3. 使用示例

**HTTP API**

```http
GET /api/v1/sessions/{session_id}/context?token_budget=128000
```

```bash
curl -X GET "http://localhost:1933/api/v1/sessions/a1b2c3d4/context?token_budget=128000" \
  -H "X-API-Key: your-key"
```

**Python SDK**

```python
import openviking_sdk as ov

client = ov.AsyncHTTPClient(url="http://localhost:1933", api_key="your-key")
await client.initialize()

context = await client.get_session_context(session_id="a1b2c3d4", token_budget=128000)
print(context["latest_archive_overview"])
print(len(context["messages"]))
```

**TypeScript SDK**

```typescript
console.log(await client.getSessionContext("session-id"));
```

**Go SDK**

```go
contextPayload, err := client.GetSessionContext(ctx, "a1b2c3d4", 128000)
if err != nil {
    return err
}
fmt.Println(contextPayload["latest_archive_overview"])
```

**CLI**

```bash
ov session get-session-context a1b2c3d4 --token-budget 128000
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "latest_archive_overview": "# Session Summary\n\n**Overview**: User discussed deployment and auth setup.",
    "pre_archive_abstracts": [],
    "messages": [
      {
        "id": "msg_pending_1",
        "role": "user",
        "parts": [
          {"type": "text", "text": "Pending user message"}
        ],
        "created_at": "2026-03-24T09:10:11Z"
      },
      {
        "id": "msg_live_1",
        "role": "assistant",
        "parts": [
          {"type": "text", "text": "Current live message"}
        ],
        "created_at": "2026-03-24T09:10:20Z"
      }
    ],
    "estimatedTokens": 160,
    "stats": {
      "totalArchives": 2,
      "includedArchives": 1,
      "droppedArchives": 0,
      "failedArchives": 0,
      "activeTokens": 98,
      "archiveTokens": 62
    }
  }
}
```

---

### get_session_archive()

#### 1. API 實現介紹

獲取某次已完成歸檔的完整內容。該介面通常配合 `get_session_context()` 使用，當需要檢視更早的歸檔詳情時呼叫。

**程式碼入口**：
- `openviking/session/session.py:Session.get_session_archive()` - 核心實現
- `openviking/server/routers/sessions.py:get_session_archive()` - HTTP 路由
- `sdk/python/openviking_sdk/client.py:AsyncHTTPClient.get_session_archive()` - Python SDK
- `crates/ov_cli/src/commands/session.rs:get_session_archive()` - CLI 命令

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| session_id | str | 是 | - | 會話 ID |
| archive_id | str | 是 | - | 歸檔 ID，例如 `archive_002` |

#### 3. 使用示例

**HTTP API**

```http
GET /api/v1/sessions/{session_id}/archives/{archive_id}
```

```bash
curl -X GET "http://localhost:1933/api/v1/sessions/a1b2c3d4/archives/archive_002" \
  -H "X-API-Key: your-key"
```

**Python SDK**

```python
import openviking_sdk as ov

client = ov.AsyncHTTPClient(url="http://localhost:1933", api_key="your-key")
await client.initialize()

archive = await client.get_session_archive(
    session_id="a1b2c3d4",
    archive_id="archive_002",
)
print(archive["archive_id"])
print(archive["overview"])
print(len(archive["messages"]))
```

**TypeScript SDK**

```typescript
console.log(await client.getSessionArchive("session-id", "archive-id"));
```

**Go SDK**

```go
archive, err := client.GetSessionArchive(ctx, "a1b2c3d4", "archive_002")
if err != nil {
    return err
}
fmt.Println(archive["archive_id"])
```

**CLI**

```bash
ov session get-session-archive a1b2c3d4 archive_002
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "archive_id": "archive_002",
    "abstract": "使用者討論了部署流程和鑑權配置。",
    "overview": "# Session Summary\n\n**Overview**: 使用者討論了部署流程和鑑權配置。",
    "messages": [
      {
        "id": "msg_archive_1",
        "role": "user",
        "parts": [
          {"type": "text", "text": "這個服務應該怎麼部署？"}
        ],
        "created_at": "2026-03-24T08:55:01Z"
      },
      {
        "id": "msg_archive_2",
        "role": "assistant",
        "parts": [
          {"type": "text", "text": "建議先走分階段部署，再核驗鑑權鏈路。"}
        ],
        "created_at": "2026-03-24T08:55:18Z"
      }
    ]
  }
}
```

**錯誤響應**

如果 archive 不存在、未完成，或者不屬於該 session，介面返回 404：

```json
{
  "status": "error",
  "error": {
    "code": "NOT_FOUND",
    "message": "Archive archive_002 not found"
  }
}
```

---

### delete_session()

#### 1. API 實現介紹

刪除會話及其所有資料，包括訊息、歸檔歷史、記憶等。刪除操作不可逆。

**程式碼入口**：
- `openviking/server/routers/sessions.py:delete_session()` - HTTP 路由
- `sdk/python/openviking_sdk/client.py:AsyncHTTPClient.delete_session()` - Python SDK
- `crates/ov_cli/src/commands/session.rs:delete_session()` - CLI 命令

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| session_id | str | 是 | - | 要刪除的會話 ID |

#### 3. 使用示例

**HTTP API**

```http
DELETE /api/v1/sessions/{session_id}
```

```bash
curl -X DELETE http://localhost:1933/api/v1/sessions/a1b2c3d4 \
  -H "X-API-Key: your-key"
```

**Python SDK**

```python
import openviking_sdk as ov

client = ov.AsyncHTTPClient(url="http://localhost:1933", api_key="your-key")
await client.initialize()

# 刪除會話
await client.delete_session(session_id="a1b2c3d4")
```

**TypeScript SDK**

```typescript
await client.deleteSession("session-id");
```

**Go SDK**

```go
if err := client.DeleteSession(ctx, "a1b2c3d4"); err != nil {
    return err
}
```

**CLI**

```bash
ov session delete a1b2c3d4
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "session_id": "a1b2c3d4"
  },
  "time": 0.1
}
```

---

### add_message()

#### 1. API 實現介紹

向會話中新增訊息。支援兩種模式：簡單文本模式和 Parts 模式（支援文本、上下文引用、工具呼叫等）。

**Part 型別**：
- `TextPart`: 純文本內容
- `ContextPart`: 上下文引用，指向資源或記憶
- `ToolPart`: 工具呼叫和結果

**程式碼入口**：
- `openviking/session/session.py:Session.add_message()` - 核心實現
- `openviking/server/routers/sessions.py:add_message()` - HTTP 路由
- `sdk/python/openviking_sdk/client.py:AsyncHTTPClient.add_message()` - Python SDK
- `crates/ov_cli/src/commands/session.rs:add_message()` - CLI 命令

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| session_id | str | 是 | - | 會話 ID |
| role | str | 是 | - | 消息角色："user" 或 "assistant" |
| parts | List[dict \| MessagePart] | 條件必填 | - | SDK 可傳訊息片段字典或 `TextPart`/`ContextPart`/`ImagePart`/`ToolPart` 物件；HTTP API 僅接受字典；與 content 二選一 |
| content | str | 條件必填 | - | 訊息文本內容（簡單模式，與 parts 二選一） |
| peer_id | str | 否 | None | 可選的穩定互動物件 ID |
| options | AddMessageOptions | 否 | None | 進階訊息選項，例如 `created_at`、`telemetry`、`turn_id`、`message_kind` 和 `source_message_ids` |

> **注意**：HTTP API 支援兩種模式：
> 1. **簡單模式**：使用 `content` 字串（向後相容）
> 2. **Parts 模式**：使用 `parts` 陣列（完整 Part 支援）
>
> 如果同時提供 `content` 和 `parts`，`parts` 優先。

**Part 型別（Python SDK）**

```python
from openviking_sdk import ContextPart, ImagePart, TextPart, ToolPart

# 文本內容
TextPart(text="Hello, how can I help?")

# 上下文引用
ContextPart(
    uri="viking://resources/docs/auth/",
    context_type="resource",  # "resource"、"memory" 或 "skill"
    abstract="Authentication guide...",
)

# 工具呼叫
ToolPart(
    tool_id="call_123",
    tool_name="search_web",
    skill_uri="viking://~/skills/search-web/",
    tool_input={"query": "OAuth best practices"},
    tool_status="pending",  # "pending"、"running"、"completed"、"error"
)
```

如果需要與 HTTP、Go 或 TypeScript 程式碼複用同一 payload 結構，也可以傳等價的字典。

#### 3. 使用示例

**HTTP API**

```http
POST /api/v1/sessions/{session_id}/messages
```

**簡單模式（向後相容）**

```bash
# 新增使用者訊息
curl -X POST http://localhost:1933/api/v1/sessions/a1b2c3d4/messages \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "role": "user",
    "content": "How do I authenticate users?"
  }'
```

**Parts 模式（完整 Part 支持）**

```bash
# 新增帶有上下文引用的助手訊息
curl -X POST http://localhost:1933/api/v1/sessions/a1b2c3d4/messages \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "role": "assistant",
    "parts": [
      {"type": "text", "text": "Based on the authentication guide..."},
      {"type": "context", "uri": "viking://resources/docs/auth/", "context_type": "resource", "abstract": "Auth guide"}
    ]
  }'

# 新增帶有工具呼叫的助手訊息
curl -X POST http://localhost:1933/api/v1/sessions/a1b2c3d4/messages \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "role": "assistant",
    "parts": [
      {"type": "text", "text": "Let me search for that..."},
      {"type": "tool", "tool_id": "call_123", "tool_name": "search_web", "tool_input": {"query": "OAuth"}, "tool_status": "completed", "tool_output": "Results..."}
    ]
  }'
```

**Python SDK**

```python
import openviking_sdk as ov
from openviking_sdk import ContextPart, TextPart

client = ov.AsyncHTTPClient(url="http://localhost:1933", api_key="your-key")
await client.initialize()

# 簡單模式：新增使用者訊息
await client.add_message(
    session_id="a1b2c3d4",
    role="user",
    content="How do I authenticate users?",
)

# Parts 模式：新增帶有上下文引用的助手訊息
await client.add_message(
    session_id="a1b2c3d4",
    role="assistant",
    parts=[
        TextPart(text="Based on the documentation, you can configure embedding..."),
        ContextPart(
            uri="viking://resources/docs/auth/",
            context_type="resource",
            abstract="Authentication guide",
        ),
    ],
)
```

**TypeScript SDK**

```typescript
await client.addMessage("session-id", { role: "user", content: "Hello" });
```

**Go SDK**

```go
result, err := client.AddMessage(ctx, "a1b2c3d4", "user", openviking.AddMessageOptions{
    Content: openviking.String("How do I authenticate users?"),
    PeerID:  "web-visitor-alice",
})
if err != nil {
    return err
}
fmt.Println(result["message_count"])
```

**CLI**

```bash
ov session add-message a1b2c3d4 --role user --content "How do I authenticate users?"
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "session_id": "a1b2c3d4",
    "message_count": 2
  },
  "time": 0.1
}
```

---

### batch_add_messages()

#### 1. API 實現介紹

向會話中批次新增多條訊息。適用於需要一次性寫入大量訊息的場景（如歷史對話匯入、記憶抽取），相比逐條呼叫 `add_message()` 可顯著提升效能。

**與 `add_message()` 的區別**：
- `add_message()`：單次請求新增 1 條訊息
- `batch_add_messages()`：單次請求新增多條訊息（上限 100 條），減少網路往返和檔案 I/O

**程式碼入口**：
- `openviking/session/session.py:Session.add_messages()` - 核心實現
- `openviking/server/routers/sessions.py:batch_add_messages()` - HTTP 路由
- `sdk/python/openviking_sdk/client.py:AsyncHTTPClient.batch_add_messages()` - Python SDK
- `crates/ov_cli/src/commands/session.rs:add_messages()` - CLI 命令

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| session_id | str | 是 | - | 會話 ID |
| messages | List[AddMessageRequest] | 是 | - | 訊息列表，每條訊息格式與 `add_message()` 相同，最多 100 條 |
| options | BatchAddMessagesOptions | 否 | None | 進階批次選項，例如 `telemetry`；傳入 `options={"telemetry": True}` 可附加操作遙測資料 |

> **注意**：每條訊息的格式與 `add_message()` 完全一致，支援 `content`（簡單模式）和 `parts`（Parts 模式）。超過 100 條需分批呼叫。

#### 3. 使用示例

**HTTP API**

```http
POST /api/v1/sessions/{session_id}/messages/batch
```

```bash
# 批次新增多條訊息
curl -X POST http://localhost:1933/api/v1/sessions/a1b2c3d4/messages/batch \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "messages": [
      {"role": "user", "content": "How do I authenticate users?"},
      {"role": "assistant", "content": "You can use OAuth 2.0 for authentication."},
      {"role": "user", "content": "Any specific recommendations?"}
    ]
  }'
```

**Python SDK**

```python
from openviking_sdk import AsyncHTTPClient

client = AsyncHTTPClient(url="http://localhost:1933", api_key="your-key")
await client.initialize()

# 批量添加消息
result = await client.batch_add_messages(
    session_id="a1b2c3d4",
    messages=[
        {"role": "user", "content": "How do I authenticate users?"},
        {"role": "assistant", "content": "You can use OAuth 2.0 for authentication."},
        {"role": "user", "content": "Any specific recommendations?"},
    ],
)
print(f"Added: {result['added']}, Total: {result['message_count']}")
```

**TypeScript SDK**

```typescript
await client.batchAddMessages("session-id", [
  { role: "user", content: "Hello" },
  { role: "assistant", content: "Hi" },
]);
```

**Go SDK**

```go
result, err := client.BatchAddMessages(ctx, "a1b2c3d4", []openviking.Message{
    {Role: "user", Content: openviking.String("How do I authenticate users?")},
    {Role: "assistant", Content: openviking.String("You can use OAuth 2.0 for authentication.")},
    {Role: "user", Content: openviking.String("Any specific recommendations?")},
}, nil)
if err != nil {
    return err
}
fmt.Println(result["added"], result["message_count"])
```

**CLI**

```bash
# 向會話中批次新增訊息
ov session add-messages a1b2c3d4 '[{"role":"user","content":"Hello"},{"role":"assistant","content":"Hi"}]'

# ov add-memory 內部也自動使用批次介面
ov add-memory '[{"role":"user","content":"Hello"},{"role":"assistant","content":"Hi"}]'
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "session_id": "a1b2c3d4",
    "message_count": 5,
    "added": 3
  },
  "time": 0.1
}
```

---

### commit()

#### 1. API 實現介紹

提交會話。歸檔訊息（Phase 1）立即完成；有訊息被歸檔時，摘要生成和記憶提取（Phase 2）在後臺非同步執行。產生歸檔的 commit 返回 `status: "accepted"` 和 `task_id`；沒有可歸檔內容的 no-op commit 返回 `status: "skipped"` 和 `task_id: null`。

**兩階段提交流程**：
- **Phase 1（同步）**: 快照當前訊息，清空 live session，建立歸檔目錄，寫入原始訊息
- **Phase 2（非同步）**: 生成摘要（L0/L1），提取長期記憶並更新關係

**注意事項**：
- 同一 session 的多次快速連續 commit 會被接受；每次請求都會拿到獨立的 `task_id`
- 空 session，或所有訊息都仍在 `keep_recent_count` 保留視窗內時，會同步完成並返回 `archived: false`
- 後臺 Phase 2 會按 archive 順序序列推進：`archive_N+1` 會等待 `archive_N` 寫出 `.done` 後再繼續
- 如果更早的 archive 已失敗且沒有 `.done`，後續 commit 會直接返回錯誤，直到該失敗被處理
- 如果提交的訊息中包含帶 `viking://resources/...` 的長期事實、評價、偏好或事件，記憶抽取會把資源保留為 markdown 連結，並寫入 `MEMORY_FIELDS.resource_refs`

**程式碼入口**：
- `openviking/session/session.py:Session.commit_async()` - 核心實現
- `openviking/server/routers/sessions.py:commit_session()` - HTTP 路由
- `sdk/python/openviking_sdk/client.py:AsyncHTTPClient.commit_session()` - Python SDK
- `crates/ov_cli/src/commands/session.rs:commit_session()` - CLI 命令

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| session_id | str | 是 | - | 要提交的會話 ID |
| keep_recent_count | int | 否 | 0 | 提交後保留為 live 狀態的最近訊息數 (保持 live, 不歸檔)。`0` (預設) 歸檔全部訊息。 |
| reset_context | bool | 否 | false | HTTP API：歸檔全部 live messages 後追加只含 `.done`（帶 `context_reset`）的邊界 archive，目錄內沒有訊息檔案。保留 session ID 和原始歷史，清空注入上下文，並阻止後續摘要繼承 reset 前的 overview。要求 `keep_recent_count=0`，且不設定 `retention_mode`。 |

`reset_context` 供 OpenClaw 外掛 reset hook 和 `Session.commit_async()` 使用；沒有 live messages 時也會建立邊界；若最新 archive 已是 reset 邊界則不重複建立。舊 archive 的記憶提取可以繼續完成，長期記憶保留。本次未增加 SDK/CLI 的專用引數。


有效策略按 Session `.meta.json`、最新 `settings/user_config.json`、核心預設值的
順序解析。Phase 2 開始前會將完整有效策略固化到非同步任務。

#### 3. 使用示例

**HTTP API**

```http
POST /api/v1/sessions/{session_id}/commit
```

```bash
# 提交會話（立即返回）
curl -X POST http://localhost:1933/api/v1/sessions/a1b2c3d4/commit \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key"

# 查詢任務狀態
curl -X GET http://localhost:1933/api/v1/tasks/{task_id} \
  -H "X-API-Key: your-key"
```

**Python SDK**

```python
from openviking_sdk import AsyncHTTPClient

client = AsyncHTTPClient(url="http://localhost:1933", api_key="your-key")
await client.initialize()

# commit 立即返回 task_id，後臺非同步執行摘要生成和記憶提取
result = await client.commit_session(session_id="a1b2c3d4")
print(f"Status: {result['status']}")
print(f"Task ID: {result['task_id']}")

# 查詢後臺任務狀態
task = await client.get_task(task_id=result["task_id"])
if task["status"] == "completed":
    memories = task["result"]["memories_extracted"]
    total = sum(memories.values())
    print(f"Memories extracted: {total}")
```

**TypeScript SDK**

```typescript
console.log(await client.commitSession("session-id"));
```

**Go SDK**

```go
commit, err := client.CommitSession(ctx, "a1b2c3d4", &openviking.CommitSessionOptions{
    KeepRecentCount: 0,
})
if err != nil {
    return err
}
fmt.Println(commit["status"], commit["task_id"])

taskID, _ := commit["task_id"].(string)
task, err := client.GetTask(ctx, taskID)
if err != nil {
    return err
}
fmt.Println(task["status"])
```

**CLI**

```bash
ov session commit a1b2c3d4
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "session_id": "a1b2c3d4",
    "status": "accepted",
    "task_id": "uuid-xxx",
    "archive_uri": "viking://user/alice/sessions/a1b2c3d4/history/archive_001",
    "archived": true
  }
}
```

**No-op 響應示例**

```json
{
  "status": "ok",
  "result": {
    "session_id": "a1b2c3d4",
    "status": "skipped",
    "task_id": null,
    "archive_uri": null,
    "archived": false,
    "reason": "no_messages"
  }
}
```

---

### extract()

#### 1. API 實現介紹

立即對已有會話觸發一次記憶提取，不會額外建立新的 commit 任務。

**程式碼入口**：
- `openviking/server/routers/sessions.py:extract_session()` - HTTP 路由

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| session_id | str | 是 | - | 要提取記憶的會話 ID |

#### 3. 使用示例

**HTTP API**

```http
POST /api/v1/sessions/{session_id}/extract
```

```bash
curl -X POST http://localhost:1933/api/v1/sessions/a1b2c3d4/extract \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key"
```

**響應示例**

該介面會直接返回本次提取產生的記憶寫入結果列表。列表項的具體結構取決於該會話實際提取出了哪些記憶。

<a id="get_task"></a><a id="list_tasks"></a>

## 會話屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| uri | str | 會話 Viking URI（`viking://user/{user_id}/sessions/{session_id}/`） |
| messages | List[Message] | 會話中的當前訊息 |
| stats | SessionStats | 會話統計資訊 |
| summary | str | 壓縮摘要 |

---

## 會話儲存結構

```
viking://user/{user_id}/sessions/{session_id}/
├── .abstract.md              # L0：會話概覽
├── .overview.md              # L1：關鍵決策
├── .meta.json                # 後設資料
├── messages.jsonl            # 當前訊息
├── tools/                    # 工具執行記錄
│   └── {tool_id}/
│       └── tool.json
└── history/                  # 歸檔歷史
    ├── archive_001/
    │   ├── messages.jsonl    # Phase 1 寫入
    │   ├── .abstract.md      # Phase 2 寫入（後臺）
    │   ├── .overview.md      # Phase 2 寫入（後臺）
    │   ├── .meta.json        # 歸檔後設資料
    │   ├── memory_diff.json  # 長記憶抽取完成時寫入
    │   ├── .done             # Phase 2 完成標記
    │   └── .failed.json      # Phase 2 失敗標記
    └── archive_002/
```

### memory_diff.json 資料結構

長記憶抽取成功執行時，會在歸檔目錄寫入 `memory_diff.json`，記錄所有記憶變更，便於審計和回溯：

```json
{
  "archive_uri": "viking://user/{user_id}/sessions/{session_id}/history/archive_001",
  "extracted_at": "2026-04-21T10:00:00Z",
  "operations": {
    "adds": [
      {
        "uri": "memory/user/xxx/identity.md",
        "memory_type": "identity",
        "after": "新建立的檔案內容"
      }
    ],
    "updates": [
      {
        "uri": "memory/user/xxx/context/project.md",
        "memory_type": "context",
        "before": "修改前的檔案內容",
        "after": "修改後的檔案內容"
      }
    ],
    "deletes": [
      {
        "uri": "memory/user/xxx/context/old.md",
        "memory_type": "context",
        "deleted_content": "被刪除的檔案內容"
      }
    ]
  },
  "skipped_operations": [
    {
      "memory_type": "events",
      "page_id": 101,
      "reason_code": "invalid_ranges",
      "reason": "無法解析出有效的事件範圍"
    }
  ],
  "summary": {
    "total_adds": 1,
    "total_updates": 1,
    "total_deletes": 1,
    "total_skipped": 1
  }
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `archive_uri` | str | 本次提交的歸檔目錄 URI |
| `extracted_at` | str | 提取時間的 ISO 8601 格式 |
| `operations.adds` | array | 新增記憶（`uri`、`memory_type`、`after`） |
| `operations.updates` | array | 修改記憶（`uri`、`memory_type`、`before`、`after`） |
| `operations.deletes` | array | 刪除記憶（`uri`、`memory_type`、`deleted_content`） |
| `skipped_operations` | array | 策略性跳過的操作及穩定原因碼；不代表檔案變更 |
| `summary.total_adds` | int | 新增記憶數 |
| `summary.total_updates` | int | 修改記憶數 |
| `summary.total_deletes` | int | 刪除記憶數 |
| `summary.total_skipped` | int | 策略性跳過的運算元 |

如果長記憶抽取已執行但沒有產生實際變更或策略性跳過，也會寫入空結構的 `memory_diff.json`（所有計數為零）。

<a id="內建記憶型別"></a>

## 完整示例

**Python SDK**

```python
from openviking_sdk import AsyncHTTPClient, ContextPart, TextPart

# 初始化客戶端
client = AsyncHTTPClient(url="http://localhost:1933", api_key="your-key")
await client.initialize()

# 建立新會話
session_result = await client.create_session()
session_id = session_result["session_id"]
print(f"Session created: {session_id}")

# 新增使用者訊息
await client.add_message(
    session_id=session_id,
    role="user",
    content="How do I configure embedding?",
)

# 使用會話上下文進行搜尋
results = await client.search(
    query="embedding configuration",
    session_id=session_id,
)

# 新增帶有上下文引用的助手回覆
resources = results.get("resources", [])
if resources:
    resource = resources[0]
    await client.add_message(
        session_id=session_id,
        role="assistant",
        parts=[
            TextPart(text="Based on the documentation, you can configure embedding..."),
            ContextPart(
                uri=resource["uri"],
                context_type="resource",
                abstract=resource.get("abstract", ""),
            ),
        ],
    )
# 提交會話（立即返回，後臺執行摘要生成和記憶提取）
commit_result = await client.commit_session(session_id=session_id)
print(f"Task ID: {commit_result['task_id']}")

# 可選：等待後臺任務完成
task = await client.get_task(task_id=commit_result["task_id"])
if task and task["status"] == "completed":
    memories = task["result"]["memories_extracted"]
    total = sum(memories.values())
    print(f"Memories extracted: {total}")
```

**HTTP API**

```bash
# 步驟 1：建立會話
curl -X POST http://localhost:1933/api/v1/sessions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key"
# 返回：{"status": "ok", "result": {"session_id": "a1b2c3d4"}}

# 步驟 2：新增使用者訊息
curl -X POST http://localhost:1933/api/v1/sessions/a1b2c3d4/messages \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"role": "user", "content": "How do I configure embedding?"}'

# 步驟 3：使用會話上下文進行搜尋
curl -X POST http://localhost:1933/api/v1/search/search \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"query": "embedding configuration", "session_id": "a1b2c3d4"}'

# 步驟 4：新增助手訊息
curl -X POST http://localhost:1933/api/v1/sessions/a1b2c3d4/messages \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"role": "assistant", "content": "Based on the documentation, you can configure embedding..."}'

# 步驟 5：提交會話（立即返回 task_id）
curl -X POST http://localhost:1933/api/v1/sessions/a1b2c3d4/commit \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key"
# 返回：{"status": "ok", "result": {"status": "accepted", "task_id": "uuid-xxx", ...}}

# 步驟 7：查詢後臺任務狀態（可選）
curl -X GET http://localhost:1933/api/v1/tasks/uuid-xxx \
  -H "X-API-Key: your-key"
```

## 最佳實踐

### 定期提交

```python
# 在重要互動後提交
session_info = await client.get_session(session_id=session_id)
if session_info["message_count"] > 10:
    await client.commit_session(session_id=session_id)
```

### 使用會話上下文進行搜尋

```python
# 結合對話上下文可獲得更好的搜尋結果
results = await client.search(query=query, session_id=session_id)
```

---

## 相關文件

- [上下文型別](../concepts/02-context-types.md) - 記憶型別
- [記憶](16-memory.md) - 記憶型別與型別配額召回
- [檢索](06-retrieval.md) - 結合會話進行搜尋
- [資源管理](02-resources.md) - 資源管理
- [後臺任務](17-tasks.md) - 跟蹤 commit 任務
