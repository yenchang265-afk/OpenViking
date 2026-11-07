# MCP 與即時上下文 API

本模組用於註冊 Streamable HTTP MCP Server、同步和檢索工具目錄、通過 OpenViking 呼叫工具，以及把工具掛載為即時上下文節點。只讀掛載工具可通過 `read` 透明執行；顯式宣告為非只讀或破壞性的工具必須顯式呼叫。所有 REST 路徑都以 `/api/v1/mcps` 開頭，並使用[通用響應信封](01-overview.md#響應格式)。

> **適用範圍**
>
> 本文只描述 **OpenViking-registered MCP Servers**：在 OpenViking 註冊、用於工具發現、代理呼叫
> 和即時上下文掛載的 MCP 服務。本文不描述 OpenViking 對外提供給 MCP Client 的
> **OpenViking MCP Interface**，也不描述通過 `bot.tools.mcp_servers` 直接配置的
> **VikingBot-connected MCP Servers**。

## 使用前提與約束

- MCP Server 只支援 Streamable HTTP，地址可以使用 HTTP 或 HTTPS。HTTP 不提供傳輸加密，使用方需自行評估憑證和工具資料的暴露風險。
- Server 名稱只能包含字母、數字、`_` 和 `-`，最長 64 個字元。工具名必須能作為 OpenViking 檔名使用。
- 註冊時提交的 HTTP Header 按帳號儲存，但 API 只返回按字母排序的 `header_names`，不會返回 Header 值。
- 工具目錄可以位於使用者空間 `viking://~/tools/<server>/<tool>.json`，也可以位於帳號共享空間 `viking://agent/tools/<server>/<tool>.json`。呼叫和掛載引數會按工具的 `inputSchema` 校驗。
- `target_uri` 只接受 `viking://~/tools` 或 `viking://agent/tools`。註冊及名稱型操作未指定時使用使用者空間；列出和檢索未指定時合併兩個空間。同名 Server 可以同時存在於兩個空間。
- 兩個 tools 目錄都是受管目錄，不能通過普通 `mkdir`、`rm`、`cp` 或 `mv` 修改，應使用 MCP 管理介面。
- 即時上下文節點 URI 必須是當前帳號可訪問的 Viking URI，並以 `.md` 結尾。
- `wait` 只控制目錄或節點寫入是否等待後臺處理完成，不是 MCP 工具呼叫超時。`timeout_seconds` 是每次即時工具呼叫的超時時間。

## 端點總覽

| 方法 | 路徑 | 用途 |
|------|------|------|
| POST | `/api/v1/mcps/validate` | 校驗連線並發現工具，不儲存配置 |
| POST | `/api/v1/mcps` | 註冊 Server 併發布工具目錄 |
| GET | `/api/v1/mcps` | 列出已註冊 Server |
| GET | `/api/v1/mcps/{name}` | 檢視 Server 和當前工具定義 |
| GET | `/api/v1/mcps/status?name=...` | 檢查 Server 是否可訪問 |
| POST | `/api/v1/mcps/{name}/sync` | 同步工具目錄並報告受影響掛載 |
| DELETE | `/api/v1/mcps/{name}` | 刪除 Server 和工具目錄 |
| POST | `/api/v1/mcps/find` | 語義檢索工具 |
| POST | `/api/v1/mcps/invoke` | 呼叫工具 |
| POST | `/api/v1/mcps/mount` | 建立或替換一個即時上下文節點 |
| POST | `/api/v1/mcps/batch-mount` | 批次建立或替換即時上下文節點 |
| DELETE | `/api/v1/mcps/mount` | 刪除一個掛載及其節點 |
| POST | `/api/v1/mcps/batch-unmount` | 批次刪除掛載及其節點 |
| GET | `/api/v1/mcps/mounts` | 查詢 Server 或工具的掛載 |

## MCP Server 生命週期

### 校驗和註冊

`POST /api/v1/mcps/validate` 會連線 Server、完成 MCP 初始化並列出工具，但不會寫入登錄檔或工具目錄。`POST /api/v1/mcps` 執行相同校驗，然後註冊 Server 併發布工具定義。預設釋出到 `viking://~/tools/<name>/`；通過 `target_uri` 可以選擇 `viking://agent/tools/<name>/`。同一空間內的同名 Server 已存在時註冊失敗。

**請求體**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `name` | string | 是 | - | Server 名稱 |
| `url` | string | 是 | - | Streamable HTTP 地址 |
| `headers` | object | 否 | `{}` | 發往上游的 HTTP Header |
| `target_uri` | string | 否 | `viking://~/tools` | 使用者或共享 tools 根目錄 |
| `wait` | boolean | 否 | `false` | 僅註冊介面使用；是否等待工具目錄處理完成 |

未知欄位會返回 `INVALID_ARGUMENT`。憑證應從環境變數或金鑰系統注入請求，不要寫入資原始檔或提交到程式碼倉庫。

**Python SDK**

```python
import os
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(url="http://localhost:1933", api_key="your-key")

headers = {"Authorization": f"Bearer {os.environ['WEATHER_MCP_TOKEN']}"}
client.validate_mcp("weather", "https://mcp.example.com/mcp", headers=headers)
result = client.add_mcp(
    "weather",
    "https://mcp.example.com/mcp",
    headers=headers,
    target_uri="viking://agent/tools",
    wait=True,
)
```

**TypeScript SDK**

```typescript
const headers = { Authorization: `Bearer ${process.env.WEATHER_MCP_TOKEN}` };
await client.validateMCP("weather", "https://mcp.example.com/mcp", headers);
const result = await client.addMCP(
  "weather",
  "https://mcp.example.com/mcp",
  headers,
  { wait: true, targetUri: "viking://agent/tools" },
);
```

**Go SDK**

```go
headers := map[string]string{
    "Authorization": "Bearer " + os.Getenv("WEATHER_MCP_TOKEN"),
}
_, err := client.ValidateMCP(ctx, "weather", "https://mcp.example.com/mcp", headers)
if err != nil {
    return err
}
result, err := client.AddMCP(
    ctx,
    "weather",
    "https://mcp.example.com/mcp",
    headers,
    &openviking.WaitOptions{Wait: true, TargetURI: "viking://agent/tools"},
)
```

**HTTP API**

```bash
curl -X POST http://localhost:1933/api/v1/mcps/validate \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "weather",
    "url": "https://mcp.example.com/mcp",
    "headers": {"Authorization": "Bearer <token>"}
  }'

curl -X POST http://localhost:1933/api/v1/mcps \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "weather",
    "url": "https://mcp.example.com/mcp",
    "headers": {"Authorization": "Bearer <token>"},
    "target_uri": "viking://agent/tools",
    "wait": true
  }'
```

**CLI**

```bash
ov mcps validate '{"mcpServers":{"weather":{"url":"https://mcp.example.com/mcp","headers":{"Authorization":"Bearer <token>"}}}}'
ov mcps add -p viking://agent/tools --wait '{"mcpServers":{"weather":{"url":"https://mcp.example.com/mcp","headers":{"Authorization":"Bearer <token>"}}}}'
```

**校驗響應**

```json
{
  "status": "ok",
  "result": {
    "name": "weather",
    "root_uri": "viking://agent/tools",
    "valid": true,
    "protocol_version": "2025-03-26",
    "server_info": {"name": "weather-server", "version": "1.0.0"},
    "tool_count": 1
  }
}
```

**註冊響應**

```json
{
  "status": "ok",
  "result": {
    "name": "weather",
    "url": "https://mcp.example.com/mcp",
    "created_at": "2026-10-21T08:00:00+00:00",
    "updated_at": "2026-10-21T08:00:00+00:00",
    "header_names": ["Authorization"],
    "tool_count": 1,
    "protocol_version": "2025-03-26"
  }
}
```

`wait=false` 時，註冊響應還可能包含底層目錄寫入返回的 `processing` 物件。

### 列出、檢視和檢查狀態

`GET /api/v1/mcps` 未指定 `target_uri` 時合併使用者空間和共享空間的 Server，每項用 `root_uri` 標識所屬空間。`GET /api/v1/mcps/{name}` 和狀態介面預設操作使用者空間；使用同名共享 Server 時必須指定 `target_uri=viking://agent/tools`。連線失敗仍是成功的 HTTP 響應，但 `result.status` 為 `error`。

**SDK 與 CLI**

```python
servers = client.list_mcps()
server = client.get_mcp("weather", target_uri="viking://agent/tools")
status = client.get_mcp_status("weather", target_uri="viking://agent/tools")
```

```typescript
const servers = await client.listMCPs();
const server = await client.getMCP("weather", "viking://agent/tools");
const status = await client.getMCPStatus("weather", "viking://agent/tools");
```

```bash
ov mcps list
ov mcps show -p viking://agent/tools weather
ov mcps status -p viking://agent/tools weather
```

**HTTP API**

```bash
curl -H "X-API-Key: your-key" http://localhost:1933/api/v1/mcps
curl -H "X-API-Key: your-key" \
  "http://localhost:1933/api/v1/mcps/weather?target_uri=viking%3A%2F%2Fagent%2Ftools"
curl -H "X-API-Key: your-key" \
  "http://localhost:1933/api/v1/mcps/status?name=weather&target_uri=viking%3A%2F%2Fagent%2Ftools"
```

**列表響應**

```json
{
  "status": "ok",
  "result": {
    "servers": [{
      "name": "weather",
      "root_uri": "viking://agent/tools",
      "url": "https://mcp.example.com/mcp",
      "created_at": "2026-10-21T08:00:00+00:00",
      "updated_at": "2026-10-21T08:00:00+00:00",
      "header_names": ["Authorization"],
      "tool_count": 1
    }],
    "total": 1
  }
}
```

檢視響應在同一 Server 物件中增加 `tools`。每項包含 `uri`、`server`、`address`、`revision`、`input_revision` 和上游 MCP `tool` 定義。`revision` 跟蹤完整 Tool 定義；`input_revision` 根據工具名稱和 `inputSchema` 跟蹤掛載相容性。

**狀態響應**

```json
{
  "status": "ok",
  "result": {
    "name": "weather",
    "status": "running",
    "protocol_version": "2025-03-26",
    "tool_count": 1
  }
}
```

連線失敗時，`result` 為 `{"name":"weather","status":"error","error":"...","tool_count":1}`。客戶端應同時檢查 HTTP 信封和這個業務狀態。

### 同步工具目錄

`POST /api/v1/mcps/{name}/sync` 重新發現上游工具，只重寫新增或 `revision` 變化的工具，並刪除目錄中上游已移除的工具。`changed` 和 `unchanged` 分類使用 `input_revision`，因此僅描述、annotations 或輸出 schema 變化時會重新整理目錄，但仍歸類為 `unchanged`。同步不會自動改寫或刪除已有即時上下文節點，而是在 `affected_mounts` 中報告：

| 狀態 | 含義 |
|------|------|
| `REVIEW` | 工具 input revision 已變化，現有預設引數仍符合新 schema，需要人工確認行為 |
| `INVALID` | 工具 input revision 已變化，現有預設引數不再符合新 schema |
| `REMOVED` | 上游不再提供該工具 |

**請求體**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `wait` | boolean | 否 | `false` | 是否等待工具目錄處理完成；也可以省略整個請求體 |
| `target_uri` | string | 否 | `viking://~/tools` | Server 所屬 tools 根目錄 |

**SDK、HTTP 與 CLI**

```python
result = client.sync_mcp("weather", target_uri="viking://agent/tools", wait=True)
```

```typescript
const result = await client.syncMCP("weather", {
  targetUri: "viking://agent/tools",
  wait: true,
});
```

```bash
curl -X POST http://localhost:1933/api/v1/mcps/weather/sync \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"target_uri":"viking://agent/tools","wait":true}'

ov mcps sync -p viking://agent/tools --wait weather
```

**響應契約**

```json
{
  "status": "ok",
  "result": {
    "name": "weather",
    "synced": true,
    "protocol_version": "2025-03-26",
    "tool_count": 1,
    "changes": {
      "added": [],
      "changed": ["current"],
      "unchanged": [],
      "removed": ["forecast"]
    },
    "affected_mounts": [{
      "node_uri": "viking://resources/weather/current.md",
      "tool_uri": "viking://agent/tools/weather/current.json",
      "tool": "current",
      "mounted_input_revision": "old-input-revision",
      "current_input_revision": "new-input-revision",
      "status": "REVIEW",
      "reason": "Tool input revision changed; mounted arguments remain valid under the current input schema"
    }]
  }
}
```

### 刪除 Server

`DELETE /api/v1/mcps/{name}` 刪除指定空間中的註冊資訊和工具目錄。它不刪除已掛載的即時上下文節點；這些節點之後無法執行，應先查詢並解除安裝掛載。

```python
result = client.remove_mcp("weather", target_uri="viking://agent/tools")
```

```bash
ov mcps mounts -p viking://agent/tools --mcp weather
ov mcps remove -p viking://agent/tools weather
```

```json
{
  "status": "ok",
  "result": {"name": "weather", "removed": true}
}
```

## 工具發現與呼叫

### 語義檢索工具

`POST /api/v1/mcps/find` 未指定 `target_uri` 時合併檢索使用者空間和共享空間；指定後只檢索對應 tools 根目錄。REST 和 SDK 響應包含完整 `tool` 定義，可據此只補充 `inputSchema` 要求的引數。

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `query` | string | 是 | - | 非空的自然語言查詢 |
| `limit` | integer | 否 | `10` | 返回上限，範圍 1-100 |
| `target_uri` | string | 否 | 合併兩個空間 | 限定使用者或共享 tools 根目錄 |

```python
result = client.find_mcp_tools("查詢城市當前天氣", limit=5)
```

```typescript
const result = await client.findMCPTools("current weather for a city", 5);
```

```bash
ov mcps find --limit 5 "查詢城市當前天氣"
```

```json
{
  "status": "ok",
  "result": {
    "tools": [{
      "uri": "viking://agent/tools/weather/current.json",
      "server": "weather",
      "name": "current",
      "description": "Get current weather",
      "revision": "sha256-revision",
      "input_revision": "sha256-input-revision",
      "score": 0.87,
      "tool": {
        "name": "current",
        "description": "Get current weather",
        "inputSchema": {
          "type": "object",
          "properties": {"city": {"type": "string"}},
          "required": ["city"]
        }
      }
    }],
    "total": 1
  }
}
```

### 呼叫工具

`POST /api/v1/mcps/invoke` 通過已註冊 Server 呼叫工具。OpenViking 注入儲存的上游 Header，不向呼叫方暴露憑證。當前呼叫不會自動重試；連線斷開或超時時，錯誤會說明執行結果可能未知。

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `uri` | string | 是 | - | `viking://agent/tools/<server>/<tool>.json` |
| `arguments` | object | 否 | `{}` | 符合工具 `inputSchema` 的引數 |

```python
result = client.invoke_mcp_tool(
    "viking://agent/tools/weather/current.json",
    {"city": "Beijing"},
)
```

```typescript
const result = await client.invokeMCPTool(
  "viking://agent/tools/weather/current.json",
  { city: "Beijing" },
);
```

```bash
ov mcps invoke viking://agent/tools/weather/current.json \
  --args '{"city":"Beijing"}'
```

```json
{
  "status": "ok",
  "result": {
    "content": [{"type": "text", "text": "Beijing: 18 C, clear"}],
    "isError": false
  }
}
```

`result` 保留 MCP `CallToolResult`，可能包含 `content`、`structuredContent` 和 `isError`。上游返回 `isError=true` 仍表示 HTTP 呼叫成功，呼叫方必須檢查該欄位。

## 即時上下文掛載

### 建立或替換掛載

`POST /api/v1/mcps/mount` 建立或替換一個 Markdown 即時上下文節點。`POST /api/v1/mcps/batch-mount` 逐項校驗引數和目標寫許可權，跳過不合格的節點，按請求順序寫入有效節點並立即儲存掛載記錄。空批次和重複 `node_uri` 會在任何修改前拒絕整批請求。

任何工具都可以掛載。為相容未提供 annotations 的工具，annotations 缺失或為空時預設按只讀處理。完整讀取會拒絕執行 `annotations.readOnlyHint: false` 或 `destructiveHint: true` 的工具；錯誤會返回當前整合執行顯式呼叫所需的 `tool_uri` 和已儲存引數。

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `tool_uri` | string | 是 | - | 已註冊工具 URI |
| `node_uri` | string | 是 | - | 以 `.md` 結尾的目標 URI |
| `title` | string | 是 | - | 非空節點標題 |
| `description` | string/null | 否 | `null` | 節點說明 |
| `timeout_seconds` | integer | 否 | `60` | 單次工具呼叫超時，必須大於 0 |
| `arguments` | object | 否 | `{}` | 固定注入並按工具 schema 校驗的引數 |
| `tags` | string[]/null | 否 | `null` | 節點檢索標籤；省略或傳 `[]` 均保留原標籤，清空標籤需呼叫 `set_tags` 的 clear 模式 |
| `wait` | boolean | 否 | `false` | 是否等待節點處理完成；批次介面位於最外層 |

**Python SDK**

```python
result = client.mount_mcp_tool(
    "viking://agent/tools/weather/current.json",
    "viking://resources/live/weather-beijing.md",
    "北京即時天氣",
    description="查詢北京當前天氣",
    arguments={"city": "Beijing"},
    tags=["source=mcp"],
    wait=True,
)
```

**TypeScript SDK**

```typescript
const result = await client.mountMCPTool(
  "viking://agent/tools/weather/current.json",
  "viking://resources/live/weather-beijing.md",
  "Beijing live weather",
  {
    description: "Query current weather in Beijing",
    arguments: { city: "Beijing" },
    tags: ["source=mcp"],
    wait: true,
  },
);
```

**HTTP API**

```bash
curl -X POST http://localhost:1933/api/v1/mcps/mount \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "tool_uri": "viking://agent/tools/weather/current.json",
    "node_uri": "viking://resources/live/weather-beijing.md",
    "title": "北京即時天氣",
    "description": "查詢北京當前天氣",
    "arguments": {"city": "Beijing"},
    "tags": ["source=mcp"],
    "wait": true
  }'
```

**CLI**

```bash
ov mcps mount \
  viking://agent/tools/weather/current.json \
  viking://resources/live/weather-beijing.md \
  --title "北京即時天氣" \
  --description "查詢北京當前天氣" \
  --args '{"city":"Beijing"}' \
  --wait
```

當前 CLI 的 `mount` 不提供 `--tags`；需要標籤時使用 SDK 或 HTTP。

**響應契約**

```json
{
  "status": "ok",
  "result": {
    "node_uri": "viking://resources/live/weather-beijing.md",
    "mcp": "weather",
    "tool": "current",
    "tool_uri": "viking://agent/tools/weather/current.json",
    "input_revision": "sha256-input-revision",
    "title": "北京即時天氣",
    "description": "查詢北京當前天氣",
    "timeout_seconds": 60,
    "arguments": {"city": "Beijing"},
    "created_at": "2026-10-21T08:30:00+00:00",
    "mounted": true
  }
}
```

批次請求體為 `{"mounts":[<不含 wait 的單項引數>],"wait":false}`，至少包含一項。Python、TypeScript 和 Go SDK 分別提供 `batch_mount_mcp_tools`、`batchMountMCPTools` 和 `BatchMountMCPTools`。響應為：

```json
{
  "status": "ok",
  "result": {
    "mounts": [{"node_uri": "viking://resources/live/weather-beijing.md", "mounted": true}],
    "total": 1,
    "succeeded": ["viking://resources/live/weather-beijing.md"],
    "failed": [],
    "not_attempted": []
  }
}
```

每個 `mounts` 項的完整欄位與單項掛載響應一致。
兩個批次介面均跳過失敗項並繼續處理獨立節點，保留已完成的檔案操作和掛載記錄。響應仍為 HTTP 200；呼叫方必須檢查 `failed`，其中也包含單節點引數和許可權檢查錯誤。`succeeded` 為成功節點 URI，`failed` 為錯誤項（`node_uri`、`code`、`message`、`applied`），兩者均保持請求順序。正常完成時 `not_attempted` 為空。空批次和重複 URI 返回 `INVALID_ARGUMENT`，且不會修改檔案。

`failed[].applied=true` 表示檔案修改已經生效並已儲存對應掛載記錄，但後續處理失敗；該節點也出現在 `mounts` 或 `unmounts` 中，`total` 為實際生效的項數，後續節點仍會執行。批次解除安裝不會重建已刪除節點，避免正文補償改變原有 ACL。掛載記錄儲存失敗時只重試當前資料庫快照一次，不重新執行檔案操作；如果仍失敗，則停止整批並返回 `PROCESSING_ERROR`，錯誤詳情包含 `node_uri`、`reconciliation_required=true`，以及 `succeeded`、`failed` 和 `not_attempted`。需要核對該節點與記錄；`not_attempted` 列出後續尚未開始檔案操作的有效節點。
掛載響應不返回 `tags`，因為向量索引處理可能仍在非同步進行。需要當前標籤時應呼叫查詢掛載介面，以向量索引中的標籤為準。

### 查詢掛載

`GET /api/v1/mcps/mounts` 的 `mcp` 查詢引數必填，`tool` 可選，`target_uri` 用於選擇同名 Server 所屬空間；未指定時使用使用者空間。Server 必須仍處於已註冊狀態。
響應中的 `tags` 從向量索引讀取，掛載資料庫不再儲存獨立副本。

```python
result = client.list_mcp_mounts("weather", tool="current")
```

```bash
ov mcps mounts --mcp weather --tool current
```

```json
{
  "status": "ok",
  "result": {
    "mounts": [{
      "node_uri": "viking://resources/live/weather-beijing.md",
      "mcp": "weather",
      "tool": "current",
      "tool_uri": "viking://agent/tools/weather/current.json",
      "input_revision": "sha256-input-revision",
      "arguments": {"city": "Beijing"},
      "title": "北京即時天氣",
      "description": "查詢北京當前天氣",
      "timeout_seconds": 60,
      "tags": ["source=mcp"],
      "created_at": "2026-10-21T08:30:00+00:00"
    }],
    "total": 1
  }
}
```

### 讀取即時上下文

掛載後使用普通內容讀取介面或 `ov read`。OpenViking 識別節點的 `OpenViking Live Context` 後設資料，並對符合只讀策略的工具按節點儲存的 `tool_uri`、`arguments` 和 `timeout_seconds` 發起呼叫。

```bash
ov read viking://resources/live/weather-beijing.md
```

即時讀取支援 MCP 文本結果和 `structuredContent`。多個文本塊用換行連線；只有結構化結果時返回格式化 JSON。上游 `isError=true`、只有圖片或音訊等非文本內容，或者工具顯式宣告為非只讀或破壞性時，讀取返回 `PROCESSING_ERROR`。直接呼叫 `/invoke` 可以執行寫工具，並仍會保留原生 MCP 內容。

### 刪除掛載

`DELETE /api/v1/mcps/mount` 刪除一個掛載記錄和對應 Markdown 節點。批次介面 `POST /api/v1/mcps/batch-unmount` 接收至少一個且不重複的 `node_uris`；掛載不存在或刪除許可權不足時，將該節點記入 `failed`，其他節點繼續執行。每刪除一個節點立即儲存記錄，部分失敗使用上文的 `succeeded`、`failed` 和 `not_attempted` 契約，實際完成項位於 `unmounts`。

```python
client.unmount_mcp_tool(
    "viking://resources/live/weather-beijing.md",
    wait=True,
)
```

```bash
ov mcps unmount viking://resources/live/weather-beijing.md --wait
```

```bash
curl -X DELETE \
  "http://localhost:1933/api/v1/mcps/mount?node_uri=viking%3A%2F%2Fresources%2Flive%2Fweather-beijing.md&wait=true" \
  -H "X-API-Key: your-key"
```

```json
{
  "status": "ok",
  "result": {
    "node_uri": "viking://resources/live/weather-beijing.md",
    "mcp": "weather",
    "tool": "current",
    "tool_uri": "viking://agent/tools/weather/current.json",
    "unmounted": true
  }
}
```

批次請求體為 `{"node_uris":["viking://resources/live/weather-beijing.md"],"wait":true}`，響應包含 `unmounts` 和 `total`，每個 `unmounts` 項與單項響應欄位一致。

## 常見錯誤

| 錯誤碼 | 常見原因 |
|--------|----------|
| `INVALID_ARGUMENT` | 名稱或 URL 不合法、查詢為空、URI 格式錯誤、節點不是 `.md`、引數不符合工具 schema、批次 URI 重複 |
| `ALREADY_EXISTS` | 註冊了同名 MCP Server |
| `NOT_FOUND` | Server、工具或掛載不存在 |
| `UNAVAILABLE` | 無法連線 MCP Server、初始化失敗、工具呼叫失敗或工具呼叫超時 |

工具呼叫失敗不會自動重試。收到 `UNAVAILABLE` 或超時後，不應假設上游沒有執行具有副作用的操作。

## 相關文件

- [即時上下文接入和編排](../guides/24-live-context-arrangement.md)
- [MCP 整合](../guides/06-mcp-integration.md)
- [內容 API](12-content.md)
- [SDK、HTTP 與 CLI 約定](01-overview.md)
