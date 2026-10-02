# Business Data Platform OpenClaw 外掛參考文件

> 本文件彙總當前分支提供的外掛配置引數、安裝/配置命令、Slash 命令、Agent 可見 Tools、Gateway API 以及外掛呼叫的 Business Data Platform 後端 API。適用於接入、運維、排障和二次開發。

## 1. 外掛入口與執行結構

Business Data Platform 外掛以 OpenClaw context-engine plugin 方式執行：

- 插件入口：`dist/index.js`
- Setup CLI 入口：`dist/commands/setup.js`
- 插件 ID：`openviking`
- Context engine slot：`plugins.slots.contextEngine = "openviking"`

執行期主要能力分為 6 層：

1. **配置層**：解析 `plugins.entries.openviking.config`，並支援部分環境變數兜底。
2. **Context Engine 層**：負責 session assemble、afterTurn 寫入、compact、auto-recall、auto-capture。
3. **Agent Tools 層**：向模型暴露記憶、資源查詢、歸檔檢索、工具結果恢復等工具。
4. **Slash Commands 層**：向用戶暴露 `/add-resource`、`/add-skill`、`/ov-search`、`/ov-recall-trace`。
5. **Gateway API 層**：向外提供 recall trace 查詢介面。
6. **Business Data Platform Client 層**：封裝 Business Data Platform Server HTTP API。

## 2. 配置檔案位置與基本結構

預設配置檔案：

```text
~/.openclaw/openclaw.json
```

如果設定了 `OPENCLAW_STATE_DIR`，則使用：

```text
$OPENCLAW_STATE_DIR/openclaw.json
```

典型配置結構：

```json
{
  "plugins": {
    "slots": {
      "contextEngine": "openviking"
    },
    "entries": {
      "openviking": {
        "config": {
          "mode": "remote",
          "baseUrl": "http://127.0.0.1:1933",
          "apiKey": "${OPENVIKING_API_KEY}",
          "autoCapture": true,
          "autoRecall": true,
          "recallTargetTypes": ["user", "agent"]
        }
      }
    }
  }
}
```

## 3. 配置引數參考

### 3.1 連線與認證

| 引數 | 型別 | 預設值 | 環境變數 | 說明 |
| --- | --- | --- | --- | --- |
| `mode` | string | `"remote"` | — | 當前僅支援遠端模式。舊的 local mode 會被遷移到 remote。 |
| `baseUrl` | string | `http://127.0.0.1:1933` | `OPENVIKING_BASE_URL` / `OPENVIKING_URL` | Business Data Platform Server HTTP 地址；末尾 `/` 會自動去掉。 |
| `apiKey` | string | 空 | `OPENVIKING_API_KEY` | Business Data Platform API Key；請求時寫入 `X-API-Key`。 |
| `accountId` | string | 空 | `OPENVIKING_ACCOUNT_ID` | 進階租戶路由欄位；請求時寫入 `X-OpenViking-Account`。Root key 或 trusted 部署通常需要。 |
| `userId` | string | 空 | `OPENVIKING_USER_ID` | 進階租戶路由欄位；請求時寫入 `X-OpenViking-User`。Root key 或 trusted 部署通常需要。 |
| `timeoutMs` | number | `15000` | — | Business Data Platform HTTP 請求超時，最低會 clamp 到 `1000`。 |

### 3.2 Peer 身份與資料面路由

| 引數 | 型別 | 預設值 | 環境變數 | 說明 |
| --- | --- | --- | --- | --- |
| `peer_role` | `"none"` \| `"assistant"` \| `"sender"` \| `"person"` (legacy) | `none` | — | 記憶歸屬。`none`：共享 `viking://user/<user_id>/memories`（預設）；`assistant`：assistant 歸因記憶位於 `.../peers/<assistant_id>/memories`；`sender`：sender 歸因記憶位於 `.../peers/<sender_id>/memories`。舊值 `person` 作為 `sender` 的別名相容。Session message 使用 body `peer_id`；資料面 recall/search 使用 `X-OpenViking-Actor-Peer`。 |
| `peer_prefix` | string | 空 | — | `peer_role=assistant` 時 assistant `peer_id` / actor peer 值的可選字首。互動式 setup 僅允許字母、數字、`_`、`-`。 |

### 3.3 自動捕獲與提交

| 引數 | 型別 | 預設值 | 環境變數 | 說明 |
| --- | --- | --- | --- | --- |
| `autoCapture` | boolean | `true` | — | 是否在會話過程中自動將訊息寫入 Business Data Platform session 並觸發記憶抽取。 |
| `captureMode` | `"semantic"` \| `"keyword"` | `"semantic"` | — | 捕獲模式。非法值會導致配置解析失敗。 |
| `captureMaxLength` | number | `24000` | — | 自動捕獲文本最大長度，範圍 `200` 到 `200000`。 |
| `commitTokenThreshold` | number | 已廢棄 | — | 舊的絕對 token 閾值，已被 `commitTokenThresholdRatio` 取代；為相容老配置保留（可解析但被忽略，不再生效）。 |
| `commitTokenThresholdRatio` | number | `0.5` | — | afterTurn 中 pending tokens 達到「模型上下文視窗 × 該比例」時觸發 commit（0-1，例 `0.5`=50%）；`0` 表示每輪都提交。 |
| `commitKeepRecentCount` | number | `10` | — | afterTurn commit 後保留最近訊息數，範圍 `0` 到 `1000`。compact 路徑始終使用 `0`。 |

### 3.4 自動召回與顯式召回

| 引數 | 型別 | 預設值 | 環境變數 | 說明 |
| --- | --- | --- | --- | --- |
| `autoRecall` | boolean | `true` | — | 是否在 assemble 階段自動召回並注入上下文。 |
| `autoRecallTimeoutMs` | number | `15000` | — | 服務端組裝 context search 的總超時，範圍 `1000` 到 `300000` ms。 |
| `targetUri` | string | `viking://user/memories` | — | `memory_recall` / `memory_forget` 預設搜尋範圍。 |
| `recallTargetTypes` | string[] | `["user", "agent"]` | — | 自動召回和預設 `memory_recall` 的搜尋型別。允許 `resource`、`user`、`agent`。 |
| `recallResources` | boolean | `false` | `OPENVIKING_RECALL_RESOURCES` | 舊相容開關；僅在未顯式配置 `recallTargetTypes` 時追加 `resource`。 |
| `recallLimit` | number | `6` | — | 自動召回按共享 context-search 契約對映為 coding quotas；顯式 `memory_recall` 保留本地候選擴充。 |
| `recallScoreThreshold` | number | `0.15` | — | 自動召回交給服務端過濾；顯式 `memory_recall` 保留本地後處理。範圍 `0` 到 `1`。 |
| `recallMaxInjectedChars` | number | `4000` | — | 自動召回按 4 字元/token 換算為服務端 `max_tokens`；顯式召回仍使用字元預算。範圍 `100` 到 `50000`。 |
| `recallPreferAbstract` | boolean | `false` | — | 自動召回為 true 時請求服務端 abstract detail；否則由服務端按類別選擇層級。 |
| `recallMaxContentChars` | number | `5000` | — | 已廢棄相容項。 |
| `recallTokenBudget` | number | 跟隨 `recallMaxInjectedChars` | — | 已廢棄別名；未配置 `recallMaxInjectedChars` 時可作為 fallback。 |

### 3.5 Recall Trace

| 引數 | 型別 | 預設值 | 環境變數 | 說明 |
| --- | --- | --- | --- | --- |
| `traceRecall` | boolean | `false` | — | 是否記錄 recall/search trace。 |
| `traceRecallPersist` | boolean | `false` | — | 是否將 trace 寫入本地 JSONL。 |
| `traceRecallDir` | string | `~/.openclaw/openviking/recall-traces` | — | trace 檔案目錄，支援 `~` 展開。 |
| `traceRecallRetentionDays` | number | `14` | — | 持久化 trace 保留天數，範圍 `1` 到 `3650`。 |
| `traceRecallLoadRecentDays` | number | `2` | — | 啟動時預載入最近 trace 天數，範圍 `0` 到 `3650`。 |
| `traceRecallMaxEntries` | number | `1000` | — | 記憶體 ring buffer 最大條數，範圍 `1` 到 `1000000`。 |
| `traceRecallMaxResultsPerSearch` | number | `20` | — | 每個子搜尋最多記錄候選數，範圍 `1` 到 `1000`。 |
| `traceRecallPreviewChars` | number | `240` | — | trace 預覽字元數，範圍 `20` 到 `10000`。 |
| `traceRecallQueryMaxChars` | number | `4000` | — | trace 中儲存 query 的最大字元數，範圍 `200` 到 `200000`。 |
| `traceRecallQueryMaxDays` | number | `14` | — | 查詢持久化 trace 時預設最多掃描天數，範圍 `1` 到 `3650`。 |
| `traceRecallIncludeContentByDefault` | boolean | `false` | — | 查詢 trace 時預設是否讀取 selected URI 的內容預覽。 |
| `traceRecallIncludeRawUserPreview` | boolean | `false` | — | 是否允許把原始使用者輸入預覽持久化。預設關閉以降低隱私風險。 |

### 3.6 診斷、繞過與工具開關

| 引數 | 型別 | 預設值 | 環境變數 | 說明 |
| --- | --- | --- | --- | --- |
| `bypassSessionPatterns` | string[] \| string | `[]` | — | 匹配 sessionId / sessionKey 後繞過 Business Data Platform 鏈路；支援 `*` 和 `**`。 |
| `emitStandardDiagnostics` | boolean | `false` | — | 是否輸出標準診斷日誌。 |
| `logFindRequests` | boolean | `false` | `OPENVIKING_LOG_ROUTING` / `OPENVIKING_DEBUG` | 列印 find/session/commit 路由日誌，不列印 API Key。 |
| `enableAddResourceTool` | boolean | `false` | — | Agent 可見 `add_resource` 的二級開關；手動 `/add-resource` 不受影響。 |
| `enabledTools` | string[] \| string | 預設 12 個 tools；若 `enableAddResourceTool=true` 則預設追加 `add_resource` | — | Agent 可見工具白名單，支援工具名或分組。 |
| `disabledTools` | string[] \| string | `[]`；當 `enableAddResourceTool=false` 時解析結果會包含 `add_resource` | — | Agent 可見工具黑名單，在 `enabledTools` 之後應用。 |

## 4. Agent Tools 開關

### 4.1 工具分組

`enabledTools` / `disabledTools` 支援以下分組：

| 分組 | 包含工具 |
| --- | --- |
| `default` | 預設 14 個 Agent tools。 |
| `all` | `add_resource` + 預設 14 個 Agent tools。注意 `add_resource` 仍需 `enableAddResourceTool=true`。 |
| `memory` | `memory_recall`、`memory_store`、`memory_forget`。 |
| `resource_query` | `ov_search`、`ov_read`、`ov_multi_read`、`ov_list`。 |
| `import` | `add_resource`、`add_skill`。 |
| `recall_trace` | `ov_recall_trace`。 |
| `archive` | `ov_archive_search`、`ov_archive_expand`。 |
| `tool_result` | `openviking_tool_result_read`、`openviking_tool_result_search`、`openviking_tool_result_list`。 |

### 4.2 只保留資源查詢工具

適用於“停用記憶，但允許 Agent 查詢 Business Data Platform 知識庫資源”的場景：

```json
{
  "autoCapture": false,
  "autoRecall": false,
  "enabledTools": ["resource_query"]
}
```

註冊結果：

- `ov_search`
- `ov_read`
- `ov_multi_read`
- `ov_list`

不會註冊：

- `memory_recall`
- `memory_store`
- `memory_forget`
- 其他預設 tools

### 4.3 保留預設工具但停用記憶 Tools

```json
{
  "disabledTools": ["memory"]
}
```

會停用：

- `memory_recall`
- `memory_store`
- `memory_forget`

保留預設工具中的資源查詢、歸檔、trace、tool result 能力。

### 4.4 啟用 `add_resource` Agent Tool

`add_resource` 需要雙重 opt-in：

```json
{
  "enabledTools": ["add_resource"],
  "enableAddResourceTool": true
}
```

如果配置為：

```json
{
  "enabledTools": ["all"]
}
```

但沒有設定 `enableAddResourceTool=true`，`add_resource` 仍不會註冊。

## 5. Setup / CLI 命令

### 5.1 `openclaw openviking setup`

用途：配置外掛連線 Business Data Platform Server，並激活 context-engine slot。

```bash
openclaw openviking setup [options]
```

引數：

| 引數 | 說明 |
| --- | --- |
| `--reconfigure` | 強制重新錄入已有配置。 |
| `--zh` | 使用中文提示。 |
| `--base-url <url>` | Business Data Platform Server URL。傳入後進入非互動模式。 |
| `--api-key <key>` | API Key。 |
| `--peer-role <role>` | 記憶歸屬：`none`、`assistant` 或 `sender`；舊值 `person` 作為 `sender` 的別名相容。 |
| `--peer-prefix <prefix>` | Peer 路由字首。 |
| `--account-id <id>` | Root API Key 場景下的 Account ID。 |
| `--user-id <id>` | Root API Key 場景下的 User ID。 |
| `--recall-target-types <types>` | 逗號分隔的召回型別，例如 `resource` 或 `user,agent,resource`。 |
| `--allow-offline` | 即使 Server 不可達也寫入配置。 |
| `--force-slot` | 如果 contextEngine slot 已被其他外掛佔用，強制替換。 |
| `--json` | 輸出 JSON。非互動模式下推薦使用；如果未傳 `--base-url`，`--json` 會報錯。 |

常見示例：

```bash
openclaw openviking setup --base-url http://127.0.0.1:1933 --api-key sk-xxx --json
```

Root key 場景：

```bash
openclaw openviking setup \
  --base-url http://127.0.0.1:1933 \
  --api-key root-xxx \
  --account-id acc_123 \
  --user-id user_456 \
  --json
```

只召回資源：

```bash
openclaw openviking setup \
  --base-url http://127.0.0.1:1933 \
  --api-key sk-xxx \
  --recall-target-types resource \
  --json
```

Server 暫不可達但仍寫配置：

```bash
openclaw openviking setup \
  --base-url http://127.0.0.1:1933 \
  --api-key sk-xxx \
  --allow-offline \
  --json
```

替換已有 context-engine slot owner：

```bash
openclaw openviking setup \
  --base-url http://127.0.0.1:1933 \
  --api-key sk-xxx \
  --force-slot \
  --json
```

### 5.2 `openclaw openviking status`

用途：檢視當前配置、連線狀態、slot 是否啟用。

```bash
openclaw openviking status [--zh] [--json]
```

引數：

| 引數 | 說明 |
| --- | --- |
| `--zh` | 使用中文輸出。 |
| `--json` | 輸出 JSON。 |

示例：

```bash
openclaw openviking status --json
```

### 5.3 Runtime Slash Alias

Manifest 中聲明瞭 runtime slash alias：

| Alias | CLI 對映 | 說明 |
| --- | --- | --- |
| `setup` | `openviking setup` | 開啟配置嚮導或執行配置。 |
| `status` | `openviking status` | 檢視狀態。 |

具體可用性取決於當前 OpenClaw runtime 是否支援該 alias 型別。

## 6. Slash Commands

### 6.1 `/add-resource`

用途：手動把檔案、目錄、URL、Git 倉庫或 OpenClaw media attachment 匯入 Business Data Platform resources。

```text
/add-resource <source> [--to URI] [--parent URI] [--reason TEXT] [--instruction TEXT] [--wait] [--timeout SEC]
```

引數：

| 引數 | 必填 | 說明 |
| --- | --- | --- |
| `<source>` | 是 | 本地檔案、目錄、URL、Git URL 或 media attachment 路徑。 |
| `--to URI` | 否 | 目標 resource URI。 |
| `--parent URI` | 否 | 父目錄 URI。不能和 `--to` 同時使用。 |
| `--reason TEXT` | 否 | 匯入原因。 |
| `--instruction TEXT` | 否 | 匯入處理指令。 |
| `--wait` | 否 | 等待服務端處理完成。 |
| `--timeout SEC` | 否 | `--wait` 時的等待超時秒數。 |

示例：

```text
/add-resource ./README.md --to viking://resources/project-readme --reason "project docs" --wait
```

注意：`/add-resource` 是手動命令，不受 `enableAddResourceTool=false` 限制。

### 6.2 `/add-skill`

用途：手動匯入 `SKILL.md` 檔案或 skill 目錄。

```text
/add-skill <source> [--wait] [--timeout SEC]
```

引數：

| 引數 | 必填 | 說明 |
| --- | --- | --- |
| `<source>` | 是 | `SKILL.md` 檔案或 skill 目錄。 |
| `--wait` | 否 | 等待服務端處理完成。 |
| `--timeout SEC` | 否 | `--wait` 時的等待超時秒數。 |

示例：

```text
/add-skill ./skills/my-skill --wait --timeout 30
```

### 6.3 `/ov-search`

用途：搜索 Business Data Platform resources 和 skills。

```text
/ov-search <query> [--uri URI] [--limit N]
```

引數：

| 引數 | 必填 | 說明 |
| --- | --- | --- |
| `<query>` | 是 | 搜尋 query。支援多詞 query。 |
| `--uri URI` | 否 | 搜尋目標 URI。未指定時預設搜尋 resources 和 agent skills。 |
| `--limit N` | 否 | 每個搜尋範圍返回條數，預設 `10`。 |

示例：

```text
/ov-search "Business Data Platform install" --uri viking://resources --limit 5
```

返回的 `viking://...` 是 Business Data Platform 虛擬 URI，不是本地檔案路徑。如需讀取完整內容，請使用 `ov_read` Agent Tool。

### 6.4 `/ov-recall-trace`

用途：查詢 recall trace，排查 auto-recall、`memory_recall`、`ov_search`、`ov_archive_search` 的召回鏈路。

```text
/ov-recall-trace [--turn latest|all] [--trace-id ID] [--session-id ID] [--session-key KEY] [--ov-session-id ID] [--source SOURCE] [--resource-types TYPES] [--since TS] [--until TS] [--include-content] [--limit N]
```

引數：

| 引數 | 說明 |
| --- | --- |
| `--turn latest|all` | 查詢最近一輪或全部，預設通常為 latest。 |
| `--trace-id ID` | 精確 trace id。 |
| `--session-id ID` | OpenClaw session id。 |
| `--session-key KEY` | OpenClaw session key。 |
| `--ov-session-id ID` | Business Data Platform session id。 |
| `--source SOURCE` | `auto_recall`、`memory_recall`、`ov_search`、`ov_archive_search`。 |
| `--resource-types TYPES` | 逗號分隔資源型別，如 `resource,user`。 |
| `--since TS` | 毫秒時間戳下界。 |
| `--until TS` | 毫秒時間戳上界。 |
| `--include-content` | 查詢時讀取 selected/displayed URI 內容預覽。 |
| `--limit N` | 最大返回 trace 數量。 |

示例：

```text
/ov-recall-trace --source ov_search --include-content --limit 10
```

## 7. Agent-visible Tools

### 7.1 預設 Tools

| Tool | 引數 | 用途 |
| --- | --- | --- |
| `add_skill` | `source?`、`data?`、`wait?`、`timeout?` | 匯入或註冊 Business Data Platform agent skill。 |
| `ov_search` | `query`、`uri?`、`limit?` | 搜索 Business Data Platform resources 和 skills。 |
| `ov_read` | `uri` | 讀取精確 `viking://...` Business Data Platform URI 的完整內容。 |
| `ov_multi_read` | `uris` | 一次讀取多個精確 `viking://...` URI，適合 overview + 同級切片。 |
| `ov_list` | `uri`、`recursive?`、`simple?`、`limit?` | 列出 Business Data Platform 目錄，用於補齊同級切片和 `.overview.md`。 |
| `memory_recall` | `query`、`limit?`、`scoreThreshold?`、`targetUri?`、`resourceTypes?` | 顯式召回長期記憶或資源；session 歷史請用 archive 工具。 |
| `ov_recall_trace` | `turn?`、`traceId?`、`sessionId?`、`sessionKey?`、`ovSessionId?`、`source?`、`resourceTypes?`、`since?`、`until?`、`includeContent?`、`limit?` | 查詢 recall trace。 |
| `memory_store` | `text`、`role?`、`sessionId?` | 將文本寫入 session 並觸發記憶抽取。 |
| `memory_forget` | `uri?`、`query?`、`targetUri?`、`limit?`、`scoreThreshold?` | 刪除記憶 URI，或先搜尋後刪除唯一高置信候選。 |
| `ov_archive_search` | `query`、`archiveId?` | 在當前 session 的 archived 原始訊息中關鍵詞搜尋。 |
| `ov_archive_expand` | `archiveId` | 展開某個 archive 的原始訊息。 |
| `openviking_tool_result_read` | `tool_output_ref`、`offset?`、`limit?` | 讀取外接工具結果的完整或分頁內容。 |
| `openviking_tool_result_search` | `tool_output_ref`、`query`、`limit?`、`context_chars?` | 在外接工具結果中搜索關鍵詞。 |
| `openviking_tool_result_list` | `tool_name?`、`limit?` | 列出當前 session 中被外接的工具結果。 |

### 7.2 Opt-in Tool：`add_resource`

| Tool | 引數 | 預設 | 開啟方式 | 用途 |
| --- | --- | --- | --- | --- |
| `add_resource` | `source`、`to?`、`parent?`、`reason?`、`instruction?`、`wait?`、`timeout?` | 不註冊 | `enableAddResourceTool=true`，且被 `enabledTools` 選中 | 允許 Agent 匯入資源。 |

安全邊界：搜尋、讀取、trace 和資源消費路徑應優先使用 `ov_search` / `ov_read`，不要讓 Agent 在檢索階段自動匯入新資源，除非使用者明確授權。

## 8. Gateway API

### 8.1 `GET /api/openviking/recall-traces`

用途：查詢 recall trace 列表。

Query 引數：

| 引數 | 型別 | 說明 |
| --- | --- | --- |
| `turn` | string | `latest` 或 `all`。 |
| `traceId` | string | 精確 trace id。 |
| `sessionId` | string | OpenClaw session id。 |
| `sessionKey` | string | OpenClaw session key。 |
| `ovSessionId` | string | Business Data Platform session id。 |
| `source` | string | `auto_recall`、`memory_recall`、`ov_search`、`ov_archive_search`。 |
| `resourceTypes` | string | 逗號分隔資源型別。 |
| `since` | number | 毫秒時間戳下界。 |
| `until` | number | 毫秒時間戳上界。 |
| `includeContent` | boolean | 是否讀取 selected/displayed URI 內容預覽。 |
| `limit` | number | 最大返回條數。 |

示例：

```bash
curl 'http://127.0.0.1:<gateway-port>/api/openviking/recall-traces?source=ov_search&includeContent=true&limit=10'
```

### 8.2 `GET /api/openviking/recall-traces/:traceId`

用途：按 trace id 查詢單條或相關 trace。

示例：

```bash
curl 'http://127.0.0.1:<gateway-port>/api/openviking/recall-traces/ov_search-1780329600000-a1b2c3d4'
```

### 8.3 Gateway route 不可用時的替代方式

如果當前 OpenClaw Gateway 沒有提供 route adapter，外掛會跳過 HTTP route 註冊。此時可使用：

- Agent Tool：`ov_recall_trace`
- Slash Command：`/ov-recall-trace`

## 9. Business Data Platform 後端 API 封裝

外掛通過 `OpenVikingClient` 呼叫 Business Data Platform Server。統一 Header：

| Header | 來源 | 說明 |
| --- | --- | --- |
| `X-API-Key` | `apiKey` | API Key。 |
| `X-OpenViking-Account` | `accountId` | 租戶 account。 |
| `X-OpenViking-User` | `userId` | 租戶 user。 |
| `X-OpenViking-Actor-Peer` | 當前解析出的 actor peer | Actor peer 資料面路由。 |

後端 API 封裝清單：

| Client 方法 | HTTP API | 用途 |
| --- | --- | --- |
| `healthCheck()` | `GET /health` | 健康檢查。 |
| `getRuntimeIdentity()` | `GET /api/v1/system/status` | 獲取執行時使用者身份。 |
| `find()` | `POST /api/v1/search/find` | 語義搜尋 memories/resources/skills。 |
| `read()` | `GET /api/v1/content/read?uri=...` | 讀取 `viking://...` URI 內容。 |
| `readToolResult()` | `GET /api/v1/sessions/{sessionId}/tool-results/{toolResultId}` | 讀取外接工具結果。 |
| `searchToolResult()` | `GET /api/v1/sessions/{sessionId}/tool-results/{toolResultId}/search?q=...` | 搜尋外接工具結果。 |
| `listToolResults()` | `GET /api/v1/sessions/{sessionId}/tool-results` | 列出外接工具結果。 |
| `uploadTempFile()` | `POST /api/v1/resources/temp_upload` | 本地檔案或目錄上傳前的臨時上傳。 |
| `addResource()` | `POST /api/v1/resources` | 匯入 resource。 |
| `addSkill()` | `POST /api/v1/skills` | 匯入 skill。 |
| `addSessionMessage()` | `POST /api/v1/sessions/{sessionId}/messages` | 寫入 session message。 |
| `getSession()` | `GET /api/v1/sessions/{sessionId}` | 獲取 session 狀態。 |
| `commitSession()` | `POST /api/v1/sessions/{sessionId}/commit` | 提交 session，觸發 archive / memory extraction。 |
| `getTask()` | `GET /api/v1/tasks/{taskId}` | 輪詢非同步任務。 |
| `getSessionContext()` | `GET /api/v1/sessions/{sessionId}/context?token_budget=...` | 讀取 session context。 |
| `getSessionArchive()` | `GET /api/v1/sessions/{sessionId}/archives/{archiveId}` | 讀取 archive 詳情。 |
| `grepSessionArchives()` | `POST /api/v1/search/grep` | 在 archive 中 grep。 |
| `deleteSession()` | `DELETE /api/v1/sessions/{sessionId}` | 刪除 session。 |
| `deleteUri()` | `DELETE /api/v1/fs?uri=...&recursive=false` | 刪除指定 URI，主要用於 `memory_forget`。 |

## 10. 常見配置組合

### 10.1 記憶與資源預設模式

```json
{
  "autoCapture": true,
  "autoRecall": true,
  "recallTargetTypes": ["user", "agent"]
}
```

### 10.2 自動召回資源庫，不啟用記憶寫入

```json
{
  "autoCapture": false,
  "autoRecall": true,
  "recallTargetTypes": ["resource"],
  "enabledTools": ["resource_query"]
}
```

### 10.3 完全停用自動記憶，只保留手動資源查詢

```json
{
  "autoCapture": false,
  "autoRecall": false,
  "enabledTools": ["resource_query"]
}
```

### 10.4 開啟 Recall Trace 排障

```json
{
  "traceRecall": true,
  "traceRecallPersist": true,
  "traceRecallDir": "~/.openclaw/openviking/recall-traces",
  "traceRecallRetentionDays": 14,
  "traceRecallMaxEntries": 1000,
  "traceRecallMaxResultsPerSearch": 20,
  "traceRecallPreviewChars": 240
}
```

### 10.5 Root Key / Trusted 部署

```json
{
  "baseUrl": "https://openviking.example.com",
  "apiKey": "${OPENVIKING_API_KEY}",
  "accountId": "${OPENVIKING_ACCOUNT_ID}",
  "userId": "${OPENVIKING_USER_ID}"
}
```

## 11. 注意事項

1. `viking://...` 是 Business Data Platform 虛擬 URI，不是本地檔案路徑。
2. 讀取 Business Data Platform 搜尋結果全文應使用 `ov_read` 或 `/api/v1/content/read`，不要交給本地檔案讀取工具。
3. `add_resource` Agent Tool 預設停用；手動 `/add-resource` 始終可用。
4. 如果只想保留資源查詢能力，優先設定 `autoCapture=false`、`autoRecall=false`、`enabledTools=["resource_query"]`。
5. 如果要排查召回未命中，開啟 `traceRecall=true`，並使用 `/ov-recall-trace` 或 Gateway recall trace API。
6. `logFindRequests` 會輸出路由、target URI、query 等資訊，但不會輸出 API Key。
7. Root key 場景通常必須配置 `accountId` 和 `userId`，否則服務端可能無法確定租戶上下文。
