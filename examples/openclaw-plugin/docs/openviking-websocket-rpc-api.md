# Business Data Platform WebSocket RPC Guide

This document explains how to call the Business Data Platform OpenClaw plugin through the OpenClaw Gateway WebSocket RPC surface.

The plugin does not start its own WebSocket server. Business Data Platform tools are registered through the OpenClaw plugin API, and the Gateway exposes them through standard tool RPC methods.

## Supported Flow

1. Connect to the OpenClaw Gateway WebSocket endpoint.
2. Call `tools.effective` for a real `sessionKey` to inspect tools available in the current session.
3. Call `tools.invoke` with a Business Data Platform tool name and JSON arguments.

Typical endpoint:

```text
ws://127.0.0.1:<gateway-port>
```

If TLS is enabled, use `wss://`.

## Connect

The first message is a `connect` request. Exact auth fields depend on the Gateway deployment.

```json
{
  "type": "req",
  "id": "connect-1",
  "method": "connect",
  "params": {
    "minProtocol": 3,
    "maxProtocol": 4,
    "client": {
      "id": "openviking-rpc-client",
      "version": "1.0.0",
      "platform": "macos",
      "mode": "operator"
    },
    "role": "operator",
    "scopes": ["operator.read", "operator.write"],
    "auth": {
      "token": "<OPENCLAW_GATEWAY_TOKEN>"
    },
    "locale": "zh-CN",
    "userAgent": "openviking-rpc-client/1.0.0"
  }
}
```

The Gateway returns `hello-ok` when the connection is accepted.

## Discover Tools

Use the current OpenClaw session key. Do not invent a synthetic session key for production debugging.

```json
{
  "type": "req",
  "id": "tools-1",
  "method": "tools.effective",
  "params": {
    "sessionKey": "main"
  }
}
```

Business Data Platform plugin tools are entries with `source="plugin"` and `pluginId="openviking"`.

## Invoke Tools

All Business Data Platform tools use `tools.invoke`.

```json
{
  "type": "req",
  "id": "invoke-1",
  "method": "tools.invoke",
  "params": {
    "name": "ov_search",
    "sessionKey": "main",
    "args": {
      "query": "Business Data Platform installation",
      "limit": 5
    }
  }
}
```

`params.sessionKey` is the Gateway/session routing field. It tells OpenClaw which session context the tool call belongs to.

`params.args.sessionKey` is a tool argument only when a specific Business Data Platform tool defines it. For example, `ov_recall_trace` can use it as an explicit trace filter. For the current session's trace, pass only the outer `params.sessionKey` unless you intentionally want a different filter.

## Common Tools

### `ov_search`

Search Business Data Platform resources, skills, and memories.

```json
{
  "name": "ov_search",
  "sessionKey": "main",
  "args": {
    "query": "runtime query config",
    "limit": 5,
    "uri": "viking://resources"
  }
}
```

### `ov_read`

Read an exact `viking://` URI.

```json
{
  "name": "ov_read",
  "sessionKey": "main",
  "args": {
    "uri": "viking://resources/project/spec.md"
  }
}
```

### `ov_multi_read`

Read multiple exact URIs in one tool call.

```json
{
  "name": "ov_multi_read",
  "sessionKey": "main",
  "args": {
    "uris": [
      "viking://resources/project/spec.md",
      "viking://resources/project/faq.md"
    ]
  }
}
```

### `memory_recall`

Recall semantic memories and resources. Current semantic recall target types are `user`, `agent`, and `resource`. Session history is not a vector recall target; use `ov_archive_search` and `ov_archive_expand` for archived session history.

```json
{
  "name": "memory_recall",
  "sessionKey": "main",
  "args": {
    "query": "what did we decide about install verification",
    "limit": 5,
    "resourceTypes": ["user", "agent", "resource"]
  }
}
```

引數：

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `query` | string | 是 | 召回查詢文本 |
| `limit` | number | 否 | 最終返回條數，預設使用外掛配置 |
| `scoreThreshold` | number | 否 | 最低分數，範圍 0-1 |
| `targetUri` | string | 否 | 指定單一搜索範圍，例如 `viking://user/memories` |
| `resourceTypes` | string[] | 否 | 未指定 `targetUri` 時使用，當前支援 `resource`、`user`、`agent`；session 歷史走 `ov_archive_search` / `ov_archive_expand` |

### `memory_store`

把文本寫入 Business Data Platform session，並立即觸發記憶抽取。

```json
{
  "type": "req",
  "id": "memory-store-1",
  "method": "tools.invoke",
  "params": {
    "name": "memory_store",
    "sessionKey": "main",
    "args": {
      "text": "使用者偏好使用 TypeScript 編寫 OpenClaw 外掛。",
      "role": "user"
    }
  }
}
```

引數：

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `text` | string | 是 | 作為記憶來源的文本 |
| `role` | string | 否 | session 訊息角色，預設 `user` |
| `sessionId` | string | 否 | 指定已有 Business Data Platform session；不傳則使用臨時 session |

### `memory_forget`

刪除記憶。可以傳精確 URI，也可以先按 query 搜尋候選。

按 URI 刪除：

```json
{
  "type": "req",
  "id": "memory-forget-1",
  "method": "tools.invoke",
  "params": {
    "name": "memory_forget",
    "sessionKey": "main",
    "args": {
      "uri": "viking://user/default/memories/memory_123"
    }
  }
}
```

按 query 查詢候選：

```json
{
  "type": "req",
  "id": "memory-forget-2",
  "method": "tools.invoke",
  "params": {
    "name": "memory_forget",
    "sessionKey": "main",
    "args": {
      "query": "偏好 Python 後端",
      "targetUri": "viking://user/memories",
      "limit": 5,
      "scoreThreshold": 0.85
    }
  }
}
```

引數：

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `uri` | string | 否 | 精確記憶 URI，僅允許當前 user/peer 記憶 URI |
| `query` | string | 否 | 未提供 `uri` 時用於搜尋候選 |
| `targetUri` | string | 否 | 搜尋範圍，預設使用外掛配置 |
| `limit` | number | 否 | 候選展示數量，預設 5 |
| `scoreThreshold` | number | 否 | 候選最低分數 |

### `add_skill`

匯入 Agent Skill 到當前使用者/peer 的 Business Data Platform skill namespace。

```json
{
  "type": "req",
  "id": "add-skill-1",
  "method": "tools.invoke",
  "params": {
    "name": "add_skill",
    "sessionKey": "main",
    "args": {
      "source": "/absolute/path/to/my-skill",
      "wait": true,
      "timeout": 120
    }
  }
}
```

也可以傳原始 skill 內容或 MCP tool dict：

```json
{
  "type": "req",
  "id": "add-skill-2",
  "method": "tools.invoke",
  "params": {
    "name": "add_skill",
    "sessionKey": "main",
    "args": {
      "data": "# My Skill\n\nSkill content...",
      "wait": true
    }
  }
}
```

引數：

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `source` | string | 二選一 | 本地 `SKILL.md` 檔案或 skill 目錄 |
| `data` | any | 二選一 | 原始 `SKILL.md` 內容或 MCP tool dict |
| `wait` | boolean | 否 | 是否等待服務端處理完成 |
| `timeout` | number | 否 | `wait=true` 時的超時時間，單位秒 |

### `add_resource`

匯入文件、目錄、URL 或 Git 倉庫到 Business Data Platform resources。

注意：該工具預設不暴露給 Agent，必須在外掛配置中設定 `enableAddResourceTool=true`，並且工具策略允許它，才能通過 `tools.invoke` 呼叫。未啟用時可使用 slash command `/add-resource`。

```json
{
  "type": "req",
  "id": "add-resource-1",
  "method": "tools.invoke",
  "params": {
    "name": "add_resource",
    "sessionKey": "main",
    "args": {
      "source": "/absolute/path/to/docs",
      "parent": "viking://resources/project-docs",
      "reason": "匯入專案文件",
      "instruction": "保留 API 示例和配置說明",
      "wait": true,
      "timeout": 300
    }
  }
}
```

引數：

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `source` | string | 是 | 本地檔案、目錄、OpenClaw media path、公開 URL 或 Git URL |
| `to` | string | 否 | 精確目標 URI，不能和 `parent` 同時使用 |
| `parent` | string | 否 | 父級 URI，不能和 `to` 同時使用 |
| `reason` | string | 否 | 匯入原因或說明 |
| `instruction` | string | 否 | 服務端處理指令 |
| `wait` | boolean | 否 | 是否等待服務端處理完成 |
| `timeout` | number | 否 | `wait=true` 時的超時時間，單位秒 |

### `ov_archive_search`

在當前 session 已歸檔的原始訊息中做關鍵詞 grep。

```json
{
  "type": "req",
  "id": "archive-search-1",
  "method": "tools.invoke",
  "params": {
    "name": "ov_archive_search",
    "sessionKey": "main",
    "args": {
      "query": "tcpdump",
      "archiveId": "archive_003"
    }
  }
}
```

引數：

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `query` | string | 是 | 單個關鍵詞或短語 |
| `archiveId` | string | 否 | 限定某個 archive，例如 `archive_003` |

### `ov_archive_expand`

展開某個歸檔，讀取原始訊息。

```json
{
  "type": "req",
  "id": "archive-expand-1",
  "method": "tools.invoke",
  "params": {
    "name": "ov_archive_expand",
    "sessionKey": "main",
    "args": {
      "archiveId": "archive_003"
    }
  }
}
```

引數：

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `archiveId` | string | 是 | archive ID，例如 `archive_003` |

### `ov_recall_trace`

Inspect recall traces when `traceRecall` is enabled.

```json
{
  "name": "ov_recall_trace",
  "sessionKey": "main",
  "args": {
    "turn": "latest",
    "limit": 5,
    "includeContent": false
  }
}
```

引數：

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `turn` | string | 否 | `latest` 或 `all`，預設 `latest` |
| `traceId` | string | 否 | 精確 trace id |
| `sessionId` | string | 否 | OpenClaw session id |
| `sessionKey` | string | 否 | OpenClaw session key |
| `ovSessionId` | string | 否 | Business Data Platform session id |
| `source` | string | 否 | `auto_recall`、`memory_recall`、`ov_search` 或 `ov_archive_search` |
| `resourceTypes` | string[] | 否 | `resource`、`user`、`agent` |
| `since` | number | 否 | Unix timestamp 毫秒下界 |
| `until` | number | 否 | Unix timestamp 毫秒上界 |
| `includeContent` | boolean | 否 | 是否按需讀取 URI 內容預覽 |
| `limit` | number | 否 | 最多返回 trace 數量，預設 20 |

### `openviking_tool_result_list`

列出當前 session 中被 Business Data Platform 外接的大工具結果。

```json
{
  "type": "req",
  "id": "tool-result-list-1",
  "method": "tools.invoke",
  "params": {
    "name": "openviking_tool_result_list",
    "sessionKey": "main",
    "args": {
      "tool_name": "RunCommand",
      "limit": 20
    }
  }
}
```

引數：

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `tool_name` | string | 否 | 按工具名過濾，也相容 `toolName` |
| `limit` | number | 否 | 最多返回數量，預設 50 |

### `openviking_tool_result_search`

在外接的大工具結果中搜索關鍵詞。

```json
{
  "type": "req",
  "id": "tool-result-search-1",
  "method": "tools.invoke",
  "params": {
    "name": "openviking_tool_result_search",
    "sessionKey": "main",
    "args": {
      "tool_output_ref": "viking://session/<session_id>/tool-results/<tool_result_id>",
      "query": "error",
      "limit": 10,
      "context_chars": 300
    }
  }
}
```

引數：

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `tool_output_ref` | string | 是 | `viking://session/.../tool-results/...` URI，也兼容 `ref` 或 `uri` |
| `query` | string | 是 | 搜尋關鍵詞或精確文本 |
| `limit` | number | 否 | 最多匹配數，預設 20 |
| `context_chars` | number | 否 | 每個命中周圍保留字元數，預設 300，也相容 `contextChars` |

### `openviking_tool_result_read`

讀取外接的大工具結果全文或片段。

```json
{
  "type": "req",
  "id": "tool-result-read-1",
  "method": "tools.invoke",
  "params": {
    "name": "openviking_tool_result_read",
    "sessionKey": "main",
    "args": {
      "tool_output_ref": "viking://session/<session_id>/tool-results/<tool_result_id>",
      "offset": 0,
      "limit": 4000
    }
  }
}
```

引數：

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `tool_output_ref` | string | 是 | `viking://session/.../tool-results/...` URI，也兼容 `ref` 或 `uri` |
| `offset` | number | 否 | 起始字元偏移，預設 0 |
| `limit` | number | 否 | 最多返回字元數 |

## Response Shape

Successful tool invocation usually returns a Gateway response whose payload contains the plugin tool output.

```json
{
  "type": "res",
  "id": "invoke-1",
  "ok": true,
  "payload": {
    "ok": true,
    "toolName": "ov_search",
    "source": "plugin",
    "output": {
      "content": [
        {
          "type": "text",
          "text": "Found 2 Business Data Platform results ..."
        }
      ],
      "details": {
        "action": "searched",
        "total": 2
      }
    }
  }
}
```

If the Gateway accepted the RPC request but the tool failed, the outer `ok` can still be `true` while `payload.ok` is `false`.

```json
{
  "type": "res",
  "id": "invoke-1",
  "ok": true,
  "payload": {
    "ok": false,
    "toolName": "ov_search",
    "error": {
      "code": "not_found",
      "message": "Tool not available: ov_search"
    }
  }
}
```

## Notes

- Use `tools.effective` before invoking a tool in a live session.
- Use exact `viking://` URIs with `ov_read` and `ov_multi_read`.
- Do not use deprecated agent URI paths for memory routing. Current routing is based on Business Data Platform context type and actor peer identity.
- For recall trace HTTP routes, see `openviking-recall-trace-api.md`.

## 本機驗證記錄（2026-06-05）

本節保留 #2613 中的 WebSocket RPC 實測記錄和可複製命令，但按當前主線語義調整：

- 不使用舊 `agent_prefix` / `X-OpenViking-Agent` / `viking://agent/...` 路徑。
- Business Data Platform 外掛仍通過 OpenClaw Gateway 暴露工具，外掛自身不啟動 WebSocket server。
- 語義召回目標使用 `user`、`agent`、`resource`；session 歷史不作為 vector recall target，應走 `ov_archive_search` / `ov_archive_expand`。
- 當前主線通過 Business Data Platform `context_type` 與 `X-OpenViking-Actor-Peer` 做檢索和 actor peer 路由。

驗證環境：

- OpenClaw：`2026.5.28`
- Gateway 節點：`SuperOpsByteDance.local`，macOS gateway mode
- CLI：`openclaw gateway call <method> --params '<json>' --json`

### Gateway RPC 基礎介面

| ID | 方法 | 引數 | 預期 | 實測結果 | 結論 |
|---|---|---|---|---|---|
| WS-RPC-01 | `health` | `{}` | Gateway 健康檢查成功 | `ok=true`、`runtimeVersion=2026.5.28`、`eventLoop.degraded=false` | 通過 |
| WS-RPC-02 | `status` | `{}` | 返回執行時和 session 狀態 | `defaultAgentId=main`、`mainHeartbeatEnabled=true`、`eventLoopDegraded=false` | 通過 |
| WS-RPC-03 | `system-presence` | `{}` | 返回當前 Gateway/CLI presence | 返回 macOS gateway 節點與 CLI probe 節點 | 通過 |
| WS-RPC-04 | `tools.catalog` | `{"agentId":"main"}` | agent 工具目錄包含 Business Data Platform 工具 | `group_count=14`、Business Data Platform 工具可見 | 通過 |
| WS-RPC-05 | `tools.effective` | `{"sessionKey":"<真實 sessionKey>"}` | 當前 session 可用工具包含 Business Data Platform 工具 | `agentId=main`、`profile=full`、Business Data Platform 工具可見 | 通過 |

常見 Business Data Platform 工具包括：

```text
add_skill, memory_forget, memory_recall, memory_store,
openviking_tool_result_list, openviking_tool_result_read, openviking_tool_result_search,
ov_archive_expand, ov_archive_search, ov_list, ov_multi_read, ov_read, ov_recall_trace, ov_search
```

注意：`add_resource` 預設不是 agent-visible tool；只有配置 `enableAddResourceTool=true` 並且工具策略允許時才會出現在 agent 工具集中。手動匯入仍可走 slash command `/add-resource`。

### 獲取真實 sessionKey

線上排障時不要人為構造 `sessionKey` 來代表真實會話。優先使用 OpenClaw 當前狀態或呼叫方上下文裡的真實 session key。

```bash
SK="$(openclaw status --json | jq -r '
  .sessionKey //
  .session.key //
  .currentSession.key //
  .current_session.key //
  empty
')"

if [ -z "$SK" ]; then
  echo "未從 openclaw status --json 取到 sessionKey" >&2
  openclaw status --json | jq .
  exit 1
fi

echo "$SK"
```

### Business Data Platform 工具呼叫

#### `ov_search`

```bash
PARAMS="$(jq -cn \
  --arg sk "$SK" \
  '{
    name: "ov_search",
    sessionKey: $sk,
    args: {
      query: "openclaw plugin config",
      limit: 2
    }
  }'
)"

openclaw gateway call tools.invoke \
  --params "$PARAMS" \
  --json | jq .
```

預期：

- `payload.ok=true`
- `toolName=ov_search`
- 返回 `viking://resources/...`、`viking://user/skills/...` 或 memory 相關結果，取決於當前 query config / target URI

#### `ov_read`

```bash
URI="viking://resources/openclaw-plugin-config/.abstract.md"

PARAMS="$(jq -cn \
  --arg sk "$SK" \
  --arg uri "$URI" \
  '{
    name: "ov_read",
    sessionKey: $sk,
    args: {
      uri: $uri
    }
  }'
)"

openclaw gateway call tools.invoke \
  --params "$PARAMS" \
  --json | jq .
```

`ov_read` 只接受完整 `viking://` URI。不要傳帶 `...` 或 `…` 的展示截斷 URI，也不要把 `viking://` URI 當成本地檔案路徑交給檔案讀取工具。

#### `memory_recall`

```bash
PARAMS="$(jq -cn \
  --arg sk "$SK" \
  '{
    name: "memory_recall",
    sessionKey: $sk,
    args: {
      query: "openclaw plugin config",
      limit: 2,
      resourceTypes: ["resource"]
    }
  }'
)"

openclaw gateway call tools.invoke \
  --params "$PARAMS" \
  --json | jq .
```

當前主線支援的 semantic recall target types：

| target | 說明 |
|---|---|
| `user` | 使用者/peer 相關長期記憶 |
| `agent` | 相容預設 memory context search 語義；當前實現不會恢復舊 `viking://agent/...` 路徑 |
| `resource` | 資源知識庫內容 |

`session` 不作為 semantic recall target。要查 session 歷史，請使用：

- `ov_archive_search`
- `ov_archive_expand`

#### `ov_archive_search`

```bash
PARAMS="$(jq -cn \
  --arg sk "$SK" \
  '{
    name: "ov_archive_search",
    sessionKey: $sk,
    args: {
      query: "tcpdump"
    }
  }'
)"

openclaw gateway call tools.invoke \
  --params "$PARAMS" \
  --json | jq .
```

#### `ov_archive_expand`

```bash
PARAMS="$(jq -cn \
  --arg sk "$SK" \
  '{
    name: "ov_archive_expand",
    sessionKey: $sk,
    args: {
      archiveId: "archive_003"
    }
  }'
)"

openclaw gateway call tools.invoke \
  --params "$PARAMS" \
  --json | jq .
```

### Trace RPC 專項驗證

以下命令均通過 `tools.invoke` 呼叫 Business Data Platform 工具 `ov_recall_trace`。

外層 `params.sessionKey` 是 Gateway 的執行上下文，也是預設 trace 查詢身份。`args.sessionKey` 只用於“按 trace 記錄裡的 sessionKey 精確過濾”的場景；日常排查當前 session 時，優先只傳外層 `sessionKey`。

```bash
# 1. 查詢最新 trace
openclaw gateway call tools.invoke \
  --params "$(jq -cn --arg sk "$SK" '{name:"ov_recall_trace",sessionKey:$sk,args:{turn:"latest",limit:5}}')" \
  --json | jq .

# 2. 按 source 查詢 ov_search trace
openclaw gateway call tools.invoke \
  --params "$(jq -cn --arg sk "$SK" '{name:"ov_recall_trace",sessionKey:$sk,args:{turn:"all",source:"ov_search",limit:10}}')" \
  --json | jq .

# 3. 按 traceId 精確查詢
TRACE_ID="ov_search-1780635606119-h2fl11l5"
openclaw gateway call tools.invoke \
  --params "$(jq -cn --arg sk "$SK" --arg trace "$TRACE_ID" '{name:"ov_recall_trace",sessionKey:$sk,args:{traceId:$trace,limit:1}}')" \
  --json | jq .

# 4. 按 traceId 查詢並展開 selected 內容預覽
openclaw gateway call tools.invoke \
  --params "$(jq -cn --arg sk "$SK" --arg trace "$TRACE_ID" '{name:"ov_recall_trace",sessionKey:$sk,args:{traceId:$trace,includeContent:true,limit:1}}')" \
  --json | jq .

# 5. 按當前 sessionKey 過濾 trace
openclaw gateway call tools.invoke \
  --params "$(jq -cn --arg sk "$SK" '{name:"ov_recall_trace",sessionKey:$sk,args:{turn:"all",sessionKey:$sk,limit:20}}')" \
  --json | jq .

# 6. 查詢不存在的 traceId，驗證空結果邊界
openclaw gateway call tools.invoke \
  --params "$(jq -cn --arg sk "$SK" '{name:"ov_recall_trace",sessionKey:$sk,args:{traceId:"not-exist-trace-20260605",limit:1}}')" \
  --json | jq .

# 7. 查詢不匹配的 sessionKey，驗證空結果邊界
openclaw gateway call tools.invoke \
  --params "$(jq -cn --arg sk "$SK" '{name:"ov_recall_trace",sessionKey:$sk,args:{turn:"all",sessionKey:"agent:main:no-trace-session-20260605",limit:5}}')" \
  --json | jq .

# 8. 查詢不匹配的 source，驗證空結果邊界
openclaw gateway call tools.invoke \
  --params "$(jq -cn --arg sk "$SK" '{name:"ov_recall_trace",sessionKey:$sk,args:{turn:"all",source:"not_a_source",limit:5}}')" \
  --json | jq .

# 9. limit=0 邊界驗證
openclaw gateway call tools.invoke \
  --params "$(jq -cn --arg sk "$SK" '{name:"ov_recall_trace",sessionKey:$sk,args:{turn:"all",limit:0}}')" \
  --json | jq .
```

| ID | 場景 | 引數摘要 | 預期 / 實測關注點 | 結論 |
|---|---|---|---|---|
| WS-RPC-10 | 最新 trace | `turn=latest`、`limit=5` | 返回最近 trace；無 trace 時 `count=0` 不算失敗 | 通過 |
| WS-RPC-11 | source 過濾 | `turn=all`、`source=ov_search` | 只返回 `ov_search` trace | 通過 |
| WS-RPC-12 | traceId 精確查詢 | `traceId=<id>`、`limit=1` | 返回指定 trace 或空結果 | 通過 |
| WS-RPC-13 | includeContent | `includeContent=true` | selected 項可包含內容預覽 | 通過 |
| WS-RPC-14 | sessionKey 過濾 | `args.sessionKey=$SK` | 返回該 session 的 trace | 通過 |
| WS-RPC-15 | 不存在 traceId | `traceId=not-exist...` | `ok=true`、`count=0`、`entries=[]` | 通過 |
| WS-RPC-16 | 不匹配 sessionKey | `sessionKey=no-trace...` | `ok=true`、`count=0`、`entries=[]` | 通過 |
| WS-RPC-17 | 不匹配 source | `source=not_a_source` | `ok=true`、`count=0`、`entries=[]` | 通過 |
| WS-RPC-18 | `limit=0` 邊界 | `turn=all`、`limit=0` | Gateway 不異常；按工具預設/邊界策略返回 | 通過 |

`ov_recall_trace` 的 RPC 響應中，關鍵結構位於 `output.details`：

```json
{
  "action": "queried",
  "count": 1,
  "lookupLayer": "memory|persistent",
  "warnings": [],
  "entries": ["RecallTraceEntry"]
}
```

無匹配資料時不視為呼叫失敗，而是返回：

```json
{
  "ok": true,
  "toolName": "ov_recall_trace",
  "output": {
    "details": {
      "count": 0,
      "entries": []
    }
  }
}
```

### 邊界用例

| ID | 場景 | 引數 / 命令 | 預期 | 結論 |
|---|---|---|---|---|
| WS-RPC-19 | 未知 RPC method | `openclaw gateway call does.not.exist --params '{}' --json` | Gateway 返回 unknown method | 通過 |
| WS-RPC-20 | 不存在 session key | `tools.effective` + 不存在的 `sessionKey` | Gateway 返回 unknown session key | 通過 |
| WS-RPC-21 | 不存在工具 | `tools.invoke` + `name=not_a_tool` | `payload.ok=false`、`error.code=not_found` | 通過 |
| WS-RPC-22 | 缺少 `ov_search.query` | `tools.invoke` + `name=ov_search` + `args={"limit":2}` | 工具引數錯誤，RPC 不應導致 Gateway 崩潰 | 通過 |
| WS-RPC-23 | `ov_read` 非法 URI | `tools.invoke` + `name=ov_read` + `args={"uri":"not-viking"}` | 工具返回引數錯誤 | 通過 |

### 常見問題

#### `tools.invoke` 返回 `Tool not available`

檢查：

1. Business Data Platform 外掛是否安裝並啟用。
2. Gateway 是否已重啟。
3. `openclaw.plugin.json` 中工具 contract 是否包含該工具。
4. 外掛配置 `enabledTools` / `disabledTools` 是否過濾了該工具。
5. Gateway 工具策略是否允許該工具。
6. `add_resource` 是否已設定 `enableAddResourceTool=true`。

#### `ov_read` 報 URI 無效

`ov_read` 只接受完整 `viking://` URI。不要傳帶 `...` 或 `…` 的展示截斷 URI。

#### `ov_recall_trace` 查詢為空

優先確認：

1. 是否開啟 `traceRecall`。
2. 是否使用真實外層 `sessionKey`。
3. 是否錯誤疊加了 `args.sessionKey`、`sessionId`、`ovSessionId` 等過濾條件。
4. `traceRecallPersist` 開啟時，持久化目錄下是否存在對應 JSONL。
5. 查詢視窗是否被 `since`、`until`、`limit` 或 retention 配置截斷。
