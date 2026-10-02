# Business Data Platform Recall Trace API 使用文件

> 面向外掛使用者、排障同學和整合方，專門說明 Business Data Platform OpenClaw 外掛中與 recall trace 相關的配置、Agent 工具、Slash 命令、Gateway HTTP API、返回結構和排障方式。

## 1. 功能概覽

Recall Trace 是 Business Data Platform 外掛的召回可觀測能力。啟用後，外掛會把每一次自動召回、顯式記憶召回、資源搜尋、歸檔搜尋記錄成結構化 trace，便於回答以下問題：

- 本輪到底搜尋了哪些範圍：`resource`、`user`、`agent`？
- 每個範圍請求的目標 URI、limit、閾值和耗時是多少？
- 候選結果有哪些？最終哪些被注入 prompt 或展示給使用者？
- 為什麼沒有召回？是沒有 session 上下文、低於分數閾值、預算不足，還是搜尋失敗？
- Gateway 重啟後，是否還能從 JSONL 持久化檔案查到近期 trace？

核心實現位於 `recall-trace.ts:20`、`index.ts:704`、`index.ts:774` 和 `index.ts:784`。

## 2. 啟用方式與配置項

### 2.1 最小啟用配置

> 關鍵點：必須顯式設定 `traceRecall: true`。只配置 `recallResources` 或 `recallTargetTypes` 只會改變召回範圍，不會啟用 trace 記錄。

```json
{
  "plugins": {
    "entries": {
      "openviking": {
        "config": {
          "traceRecall": true
        }
      }
    }
  }
}
```

`traceRecall` 在配置解析中只有等於布林值 `true` 才會啟用：`config.ts:430`。外掛註冊階段也只有啟用後才建立 `RecallTraceRecorder`：`index.ts:704`。

### 2.2 推薦排障配置

```json
{
  "plugins": {
    "entries": {
      "openviking": {
        "config": {
          "traceRecall": true,
          "traceRecallPersist": true,
          "traceRecallDir": "~/.openclaw/openviking/recall-traces",
          "traceRecallRetentionDays": 14,
          "traceRecallMaxEntries": 1000,
          "traceRecallMaxResultsPerSearch": 20,
          "traceRecallPreviewChars": 240,
          "traceRecallQueryMaxChars": 4000,
          "traceRecallQueryMaxDays": 14,
          "recallTargetTypes": ["user", "agent", "resource"]
        }
      }
    }
  }
}
```

### 2.3 Trace 配置項

| 配置項 | 型別 | 預設值 | 取值/限制 | 說明 |
| --- | --- | --- | --- | --- |
| `traceRecall` | boolean | `false` | 必須為 `true` 才啟用 | 總開關；關閉時不記錄 trace，查詢介面返回空並帶 `traceRecall is disabled` warning。實現見 `config.ts:430`、`index.ts:778`。 |
| `traceRecallPersist` | boolean | `false` | `true`/`false` | 是否寫入本地 JSONL；關閉時只保留記憶體環形快取。實現見 `config.ts:431`、`recall-trace.ts:407`。 |
| `traceRecallDir` | string | `~/.openclaw/openviking/recall-traces` | 支援 `~` 展開 | JSONL 檔案目錄；按 UTC 日期寫入 `YYYY-MM-DD.jsonl`。實現見 `config.ts:432`、`recall-trace.ts:214`。 |
| `traceRecallRetentionDays` | number | `14` | `1` 到 `3650` | 寫入新 trace 時清理超過保留期的 JSONL 檔案。實現見 `config.ts:436`、`recall-trace.ts:301`。 |
| `traceRecallLoadRecentDays` | number | `2` | `0` 到 `3650` | 配置已解析保留，當前查詢路徑主要通過記憶體 + 持久化 fallback 獲取資料。實現見 `config.ts:442`。 |
| `traceRecallMaxEntries` | number | `1000` | `1` 到 `1000000` | 記憶體 ring buffer 最大條數，超出後淘汰最舊記錄。實現見 `config.ts:448`、`recall-trace.ts:180`。 |
| `traceRecallMaxResultsPerSearch` | number | `20` | `1` 到 `1000` | 每次子搜尋最多儲存多少候選結果摘要。實現見 `config.ts:454`、`auto-recall.ts:284`。 |
| `traceRecallPreviewChars` | number | `240` | `20` 到 `10000` | 候選摘要、選中摘要的預覽字元數。實現見 `config.ts:460`、`index.ts:724`。 |
| `traceRecallQueryMaxChars` | number | `4000` | `200` 到 `200000` | trace 中儲存的 trigger query 最大長度，超出會截斷並設定 `queryTruncated`。實現見 `config.ts:466`、`index.ts:239`。 |
| `traceRecallQueryMaxDays` | number | `14` | `1` 到 `3650` | 查詢持久化 trace 且未傳 `since/until` 時最多掃描最近多少天。實現見 `config.ts:472`、`recall-trace.ts:350`。 |
| `traceRecallIncludeContentByDefault` | boolean | `false` | `true`/`false` | 查詢 trace 時是否預設讀取 selected URI 的內容預覽；也可通過查詢引數 `includeContent` 單次開啟。實現見 `config.ts:478`、`index.ts:744`。 |
| `traceRecallIncludeRawUserPreview` | boolean | `false` | `true`/`false` | 是否允許把原始使用者輸入預覽持久化到 JSONL；預設會脫敏刪除。實現見 `config.ts:479`、`recall-trace.ts:271`。 |

### 2.4 召回範圍配置與 Trace 的關係

Trace 會記錄實際召回範圍，但召回範圍本身由 `recallTargetTypes` / `recallResources` 決定：

| 配置 | 預設/行為 | 說明 |
| --- | --- | --- |
| `recallTargetTypes` | 預設 `['user', 'agent']` | 允許值：`resource`、`user`、`agent`；空值回退預設集合。實現見 `config.ts:176`、`recall-trace.ts:113`。 |
| `recallResources` | 預設 `false` | 相容舊配置；僅在未顯式配置 `recallTargetTypes` 時，把 `resource` 追加到預設召回集合。實現見 `config.ts:363`。 |

目標型別會被解析為 context type 搜尋計劃；自動召回把該計劃合併進一次服務端 context search：

| resourceType | context type | 說明 |
| --- | --- | --- |
| `resource` | `resource` | 資源庫。 |
| `user` | `memory` | 當前使用者長期記憶。 |
| `agent` | `memory` | 當前 actor 的長期記憶；與 `user` 合併為一個 memory context type，由 actor routing 限定範圍。 |

## 3. Trace 記錄來源

| source | operationType | 觸發方式 | selected 語義 | 關鍵實現 |
| --- | --- | --- | --- | --- |
| `auto_recall` | `semantic_find`（相容值） | Context Engine 在回覆前發起服務端 context search | 服務端組裝並注入 `<relevant-memories>` 的記憶或資源，`injected: true` | `auto-recall.ts` 的 `buildAutoRecallContext()` |
| `memory_recall` | `semantic_find` | Agent 呼叫 `memory_recall` 工具 | 工具返回給模型的記憶，通常 `injected: true` 且 `displayed: true` | `index.ts:1391`、`index.ts:1542` |
| `ov_search` | `semantic_find` | Agent 呼叫 `ov_search` 工具或使用者執行 `/ov-search` | 搜尋結果列表中展示的資源/技能/記憶，`displayed: true` | trace 記錄在 `index.ts` 的 `searchOpenViking` 流程中，工具註冊見 `index.ts:1371` |
| `ov_archive_search` | `archive_grep` | Agent 呼叫 `ov_archive_search` 工具 | 展示的歸檔匹配行，包含 `line`，`displayed: true` | `index.ts:1992`、`index.ts:2008` |

## 4. Trace 資料結構

### 4.1 `RecallTraceEntry`

`RecallTraceEntry` 的完整型別定義在 `recall-trace.ts:20`。

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `schemaVersion` | `'1.0'` | Trace schema 版本。 |
| `traceId` | string | Trace 唯一 ID，通常形如 `<source>-<timestamp>-<random>`。生成邏輯見 `index.ts:235`。 |
| `ts` | number | Unix timestamp，毫秒。 |
| `sessionId` | string? | OpenClaw session ID。 |
| `sessionKey` | string? | OpenClaw session key。 |
| `ovSessionId` | string? | 對映後的 Business Data Platform session ID。 |
| `agentId` | string? | 實際傳送到 Business Data Platform 的 agent ID。 |
| `source` | enum | `auto_recall`、`memory_recall`、`ov_search`、`ov_archive_search`。 |
| `operationType` | enum | `semantic_find` 或 `archive_grep`。 |
| `resourceTypes` | array | 本次 trace 覆蓋的召回型別：`resource`、`user`、`agent`。 |
| `trigger.query` | string | 觸發搜尋的查詢文本，受 `traceRecallQueryMaxChars` 限制。 |
| `trigger.derivedKeywords` | string[]? | 派生關鍵詞；歸檔搜尋通常儲存原 query。 |
| `trigger.rawUserTextPreview` | string? | 原始使用者輸入預覽；預設不持久化。 |
| `trigger.queryTruncated` | boolean? | `query` 是否因過長被截斷。 |
| `searches` | array | 本次 trace 中每個邏輯 context type 的搜尋明細。 |
| `selected` | array | 最終被注入或展示的結果。 |
| `stats` | object | 候選數、選中數、注入數、估算 token。 |

### 4.2 `searches[]`

欄位定義見 `recall-trace.ts:37`。

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `resourceType` | `resource` \| `user` \| `agent` \| `archive` | 當前子搜尋型別。 |
| `targetUriInput` | string? | 輸入或計劃中的目標 URI。 |
| `targetUriResolved` | string? | 解析後的目標 URI。 |
| `limit` | number | 請求 limit。自動召回直接使用 `recallLimit`；顯式 `memory_recall` 可先擴大候選數。 |
| `scoreThreshold` | number? | 分數閾值。自動召回由服務端應用；顯式 `memory_recall` 仍可在本地後處理。 |
| `durationMs` | number | 子搜尋耗時，毫秒。 |
| `total` | number | Business Data Platform 返回或外掛統計的候選總數。 |
| `results` | array | 候選結果摘要，最多 `traceRecallMaxResultsPerSearch` 條。 |
| `archiveId` | string? | 歸檔搜尋指定 archive 時存在。 |
| `caseInsensitive` | boolean? | 歸檔 grep 是否大小寫不敏感。 |
| `error` | string? | 子搜尋失敗或跳過原因。 |

### 4.3 `results[]`

欄位定義見 `recall-trace.ts:10`。

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `uri` | string | 候選 URI。 |
| `resourceType` | string? | 候選型別。歸檔匹配為 `archive`。 |
| `category` | string? | Business Data Platform 返回的分類。 |
| `score` | number? | 相似度分數。 |
| `level` | number? | Business Data Platform memory 層級；外掛優先選 leaf memory。 |
| `abstractPreview` | string? | 摘要預覽。 |
| `resultType` | enum | `memory`、`resource`、`skill`、`archive_match`。 |

### 4.4 `selected[]`

欄位定義見 `recall-trace.ts:50`。

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `uri` | string | 選中結果 URI。 |
| `resourceType` | string? | 選中結果型別。 |
| `category` | string? | 分類。 |
| `score` | number? | 分數。 |
| `line` | number? | 歸檔匹配所在行號。 |
| `abstractPreview` | string? | 選中結果摘要預覽。 |
| `contentPreview` | string? | 僅當查詢時開啟 `includeContent`，併成功讀取 URI 內容後出現。 |
| `readError` | string? | 開啟 `includeContent` 但讀取內容失敗時出現。 |
| `injected` | boolean? | 是否注入模型上下文。 |
| `displayed` | boolean? | 是否展示給使用者或工具呼叫結果。 |
| `skippedReason` | enum? | 預留跳過原因：`score_threshold`、`dedupe`、`non_leaf`、`budget`、`not_top_k`、`search_error`。 |

### 4.5 返回示例

```json
{
  "schemaVersion": "1.0",
  "traceId": "ov_search-1780329600000-a1b2c3d4",
  "ts": 1780329600000,
  "sessionId": "test-session",
  "sessionKey": "agent:main:example",
  "ovSessionId": "8d6e...",
  "agentId": "main",
  "source": "ov_search",
  "operationType": "semantic_find",
  "resourceTypes": ["resource"],
  "trigger": {
    "query": "Business Data Platform trace API"
  },
  "searches": [
    {
      "resourceType": "resource",
      "targetUriInput": "viking://resources",
      "targetUriResolved": "viking://resources",
      "limit": 20,
      "scoreThreshold": 0,
      "durationMs": 35,
      "total": 1,
      "results": [
        {
          "uri": "viking://resources/project/spec.md",
          "resourceType": "resource",
          "score": 0.88,
          "abstractPreview": "Recall trace design spec",
          "resultType": "resource"
        }
      ]
    }
  ],
  "selected": [
    {
      "uri": "viking://resources/project/spec.md",
      "resourceType": "resource",
      "score": 0.88,
      "abstractPreview": "Recall trace design spec",
      "displayed": true
    }
  ],
  "stats": {
    "candidateCount": 1,
    "selectedCount": 1,
    "injectedCount": 0
  }
}
```

## 5. Agent 工具：`ov_recall_trace`

### 5.1 用途

`ov_recall_trace` 用於在 Agent 內部查詢已記錄的 trace。它不會重新呼叫 Business Data Platform 搜尋介面，只查詢外掛記錄；僅當傳入 `includeContent: true` 或配置了 `traceRecallIncludeContentByDefault: true` 時，才會額外呼叫 Business Data Platform `read` 給 selected 結果補充內容預覽。工具註冊見 `index.ts:1637`。

### 5.2 引數

引數型別定義見 `index.ts:167`，工具引數宣告見 `index.ts:1642`。

| 引數 | 型別 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `turn` | `'latest'` \| `'all'` | `'latest'` | `latest` 只返回過濾後最新 1 條；`all` 返回最多 `limit` 條。解析見 `index.ts:732`、`recall-trace.ts:187`。 |
| `traceId` | string | 無 | 精確查詢某條 trace。 |
| `sessionId` | string | 當前 session | 按 OpenClaw session ID 過濾；未傳時預設當前工具上下文 session。解析見 `index.ts:734`。 |
| `sessionKey` | string | 無 | 按 OpenClaw session key 過濾。 |
| `ovSessionId` | string | 當前 session 對映值 | 按 Business Data Platform session ID 過濾。解析見 `index.ts:736`。 |
| `source` | string | 無 | `auto_recall`、`memory_recall`、`ov_search`、`ov_archive_search`。 |
| `resourceTypes` | string[] 或逗號分隔 string | 無 | 按 trace 的 `resourceTypes` 過濾；允許 `resource`、`user`、`agent`。歸一化見 `recall-trace.ts:113`。 |
| `since` | number | 無 | 毫秒時間戳下界，包含。 |
| `until` | number | 無 | 毫秒時間戳上界，包含。 |
| `includeContent` | boolean | `false` | 是否讀取 selected URI 的內容預覽；可能帶來額外讀請求。實現見 `index.ts:747`。 |
| `limit` | number | `20` | 最大返回條數；僅 `turn: 'all'` 時返回多條。解析見 `index.ts:741`。 |

> 當前介面不支援自由文本模糊查詢 trace trigger。需要按 `source`、`sessionId`、`ovSessionId`、`resourceTypes`、`traceId` 或時間範圍過濾。

### 5.3 呼叫示例

查詢當前 session 最新一條 trace：

```json
{
  "turn": "latest"
}
```

查詢當前 session 內最近 10 條 `ov_search` trace：

```json
{
  "turn": "all",
  "source": "ov_search",
  "limit": 10
}
```

查詢某條 trace 並補充 selected 內容預覽：

```json
{
  "traceId": "ov_search-1780329600000-a1b2c3d4",
  "includeContent": true
}
```

按時間範圍和召回型別查詢：

```json
{
  "turn": "all",
  "resourceTypes": ["user"],
  "since": 1780320000000,
  "until": 1780406399999,
  "limit": 50
}
```

### 5.4 返回值

工具返回 OpenClaw ToolResult：

```json
{
  "content": [
    {
      "type": "text",
      "text": "## Trace 1: ov_search\ntraceId: ...\nquery: ..."
    }
  ],
  "details": {
    "action": "queried",
    "count": 1,
    "lookupLayer": "memory",
    "warnings": [],
    "entries": []
  }
}
```

| 欄位 | 說明 |
| --- | --- |
| `content[0].text` | 人類可讀摘要，由 `formatRecallTraceText` 生成，格式見 `index.ts:845`。 |
| `details.count` | 本次返回條數。 |
| `details.lookupLayer` | `memory` 表示來自記憶體環形快取；`persistent` 表示記憶體未命中後從 JSONL 檔案 fallback 查詢。實現見 `recall-trace.ts:431`。 |
| `details.warnings` | 讀取 JSONL 或 selected 內容失敗等 warning。 |
| `details.entries` | 完整結構化 trace 陣列。 |

## 6. Slash 命令：`/ov-recall-trace`

### 6.1 用途

使用者可以在 OpenClaw 會話中直接執行 `/ov-recall-trace` 查詢 trace。命令註冊見 `index.ts:1676`。

### 6.2 引數

Slash 命令使用 `--kebab-case` 引數，解析邏輯見 `index.ts:1687`。

| 引數 | 對應工具引數 | 示例 |
| --- | --- | --- |
| `--turn` | `turn` | `--turn all` |
| `--trace-id` | `traceId` | `--trace-id ov_search-1780329600000-a1b2c3d4` |
| `--session-id` | `sessionId` | `--session-id test-session` |
| `--session-key` | `sessionKey` | `--session-key agent:main:xxx` |
| `--ov-session-id` | `ovSessionId` | `--ov-session-id 8d6e...` |
| `--source` | `source` | `--source auto_recall` |
| `--resource-types` | `resourceTypes` | `--resource-types user,agent` |
| `--since` | `since` | `--since 1780320000000` |
| `--until` | `until` | `--until 1780406399999` |
| `--include-content` | `includeContent` | `--include-content` |
| `--limit` | `limit` | `--limit 20` |

### 6.3 示例

```bash
/ov-recall-trace --turn all --source auto_recall --limit 5
```

```bash
/ov-recall-trace --trace-id ov_search-1780329600000-a1b2c3d4 --include-content
```

```bash
/ov-recall-trace --turn all --resource-types user,agent --since 1780320000000 --until 1780406399999
```

### 6.4 返回值

Slash 命令返回：

```json
{
  "text": "## Trace 1: auto_recall\ntraceId: ...",
  "details": {
    "count": 1,
    "lookupLayer": "memory",
    "warnings": [],
    "entries": []
  }
}
```

返回結構與 `ov_recall_trace` 的 `details` 基本一致；`text` 是人類可讀摘要，`details.entries` 是機器可讀資料。

## 7. Gateway HTTP API

外掛 service 啟動時會嘗試註冊 Recall Trace Gateway 路由：`index.ts:2540`。如果當前 Gateway 不支援 route adapter，日誌會提示使用 `ov_recall_trace` 工具或 `/ov-recall-trace` 命令替代：`index.ts:2548`。

### 7.1 `GET /api/openviking/recall-traces`

#### 用途

查詢多條 trace。路由註冊見 `index.ts:830`。

#### Query 引數

| 引數 | 型別 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `turn` | `latest` \| `all` | `latest` | 是否只返回最新一條。 |
| `traceId` | string | 無 | 精確過濾 trace ID。 |
| `sessionId` | string | 無 | OpenClaw session ID。 |
| `sessionKey` | string | 無 | OpenClaw session key。 |
| `ovSessionId` | string | 無 | Business Data Platform session ID。 |
| `source` | string | 無 | `auto_recall`、`memory_recall`、`ov_search`、`ov_archive_search`。 |
| `resourceTypes` | string | 無 | 逗號或換行分隔，如 `user,agent`。 |
| `since` | number | 無 | 毫秒時間戳下界。 |
| `until` | number | 無 | 毫秒時間戳上界。 |
| `includeContent` | boolean/string | 配置預設值 | 支援 `1`、`true`、`yes`。解析見 `index.ts:799`。 |
| `limit` | number | `20` | 最大返回條數。 |

#### 請求示例

```bash
curl 'http://127.0.0.1:<gateway-port>/api/openviking/recall-traces?turn=all&source=ov_search&limit=10'
```

```bash
curl 'http://127.0.0.1:<gateway-port>/api/openviking/recall-traces?turn=all&resourceTypes=user,agent&since=1780320000000&until=1780406399999'
```

#### 返回值

Handler 返回結構見 `index.ts:812`。

```json
{
  "status": 200,
  "body": {
    "ok": true,
    "entries": [],
    "lookupLayer": "memory",
    "warnings": []
  }
}
```

根據 Gateway 適配層，客戶端通常會看到 `body` 中的 JSON：

```json
{
  "ok": true,
  "entries": [],
  "lookupLayer": "memory",
  "warnings": []
}
```

### 7.2 `GET /api/openviking/recall-traces/:traceId`

#### 用途

按 `traceId` 查詢單條 trace。路由註冊見 `index.ts:831`。

#### Path 引數

| 引數 | 型別 | 說明 |
| --- | --- | --- |
| `traceId` | string | 需要查詢的 trace ID。 |

#### Query 引數

除 `traceId` 外，支援與列表介面相同的 query 引數，例如 `includeContent=true`。

#### 請求示例

```bash
curl 'http://127.0.0.1:<gateway-port>/api/openviking/recall-traces/ov_search-1780329600000-a1b2c3d4?includeContent=true'
```

#### 返回值

```json
{
  "ok": true,
  "entries": [
    {
      "traceId": "ov_search-1780329600000-a1b2c3d4",
      "source": "ov_search"
    }
  ],
  "lookupLayer": "memory",
  "warnings": []
}
```

## 8. 查詢與儲存行為

### 8.1 記憶體 Ring Buffer

- `RecallTraceMemoryStore` 儲存最近 N 條 trace，N 由 `traceRecallMaxEntries` 控制。
- 超出容量時刪除最舊記錄。
- 查詢時先過濾，再按 `ts` 降序排序。
- `turn: 'latest'` 返回過濾結果中最新一條；`turn: 'all'` 返回最多 `limit` 條。

實現見 `recall-trace.ts:172`、`recall-trace.ts:187`。

### 8.2 JSONL 持久化

啟用 `traceRecallPersist: true` 後，每條 trace 會追加到 `traceRecallDir/YYYY-MM-DD.jsonl`。

- 文件名使用 trace 的 UTC 日期：`recall-trace.ts:214`。
- 預設不會持久化 `trigger.rawUserTextPreview`，除非設定 `traceRecallIncludeRawUserPreview: true`：`recall-trace.ts:271`。
- 查詢時如果記憶體命中，直接返回記憶體結果；只有記憶體未命中且存在持久化 store，才 fallback 掃描 JSONL：`recall-trace.ts:431`。
- JSONL 中的損壞行會被跳過，並返回 warning：`recall-trace.ts:373`。

### 8.3 `includeContent` 行為

預設 trace 只儲存摘要預覽，不讀取完整內容。查詢時開啟 `includeContent` 後，外掛會對每個 `selected[].uri` 呼叫 Business Data Platform read，並把結果壓縮到 `selected[].contentPreview`：`index.ts:747`。

建議只在定位具體 trace 時使用 `includeContent`，避免一次查詢大量 trace 觸發額外讀請求。

## 9. 常見使用場景

### 9.1 解釋為什麼自動召回沒有注入記憶

1. 開啟 trace：`traceRecall: true`。
2. 復現一輪會話。
3. 查詢最新自動召回：

```bash
/ov-recall-trace --source auto_recall
```

重點檢視：

- `searches[].error` 是否有搜尋失敗。
- `searches[].total` 是否為 0。
- `stats.candidateCount`、`stats.selectedCount`、`stats.injectedCount` 是否逐步變少。
- `trigger.queryTruncated` 是否為 true。

### 9.2 檢視顯式 `memory_recall` 查了哪些空間

```bash
/ov-recall-trace --turn all --source memory_recall --limit 5
```

重點檢視 `resourceTypes` 和 `searches[].targetUriResolved`，確認是否預設查了 `viking://user/memories` 與 `agent recall target`，或是否按請求 `resourceTypes` 改變範圍。

### 9.3 排查 `/ov-search` 或 `ov_search` 為什麼結果不符合預期

```bash
/ov-recall-trace --turn all --source ov_search --include-content --limit 3
```

重點檢視：

- `trigger.query` 是否與預期一致。
- `searches[].targetUriInput` 是否是正確資源目錄。
- `results[]` 候選是否包含預期文件但未進入 `selected[]`。
- `selected[].contentPreview` 是否能讀到真實內容。

### 9.4 排查歸檔搜尋沒有命中

```bash
/ov-recall-trace --turn all --source ov_archive_search --limit 5
```

重點檢視：

- `operationType` 是否為 `archive_grep`。
- `searches[].targetUriResolved` 是否指向正確 session archive。
- `searches[].caseInsensitive` 是否為 true。
- `stats.candidateCount` 與 `selected[].line`。

## 10. 錯誤與排障

| 現象 | 可能原因 | 排查/解決 |
| --- | --- | --- |
| 查詢為空且 warning 包含 `traceRecall is disabled` | 未配置 `traceRecall: true` | 顯式啟用 `traceRecall`，重啟 Gateway 後復現。 |
| 配了 `recallTargetTypes` 但沒有 trace | 召回範圍配置不等於 trace 開關 | 同時設定 `traceRecall: true`。 |
| Gateway 路由不可用 | 當前 Gateway 未提供 `registerRoute` adapter | 使用 Agent 工具 `ov_recall_trace` 或 Slash 命令 `/ov-recall-trace`。日誌見 `index.ts:2548`。 |
| 重啟後查不到歷史 trace | 未開啟 `traceRecallPersist`，或超過 `traceRecallQueryMaxDays` 查詢視窗 | 開啟持久化，必要時傳 `since/until` 或調大 `traceRecallQueryMaxDays`。 |
| `includeContent` 後有 `readError` | selected URI 已不可讀、許可權不足或 Business Data Platform read 失敗 | 檢視 `warnings` 與 `selected[].readError`，再用 `ov_read` 驗證 URI。 |
| JSONL 查詢有 corrupted warning | 持久化檔案存在損壞行 | 外掛會跳過損壞行返回有效記錄；可檢查對應 `YYYY-MM-DD.jsonl`。實現見 `recall-trace.ts:373`。 |

## 11. 測試覆蓋

相關單元測試集中在：

- `tests/ut/recall-trace.test.ts:56`：召回型別歸一化、搜尋計劃、記憶體 ring buffer、JSONL 持久化、隱私控制。
- `tests/ut/tools.test.ts:1021`：`ov_recall_trace` 工具、Slash 命令、Gateway 路由、`includeContent`、顯式召回 trace、查詢不重新觸發搜尋。

建議修改 trace 行為後至少執行：

```bash
npm run typecheck
npm test -- tests/ut/recall-trace.test.ts tests/ut/tools.test.ts
```

## 12. 快速參考

### 開啟 trace

```json
{
  "traceRecall": true,
  "traceRecallPersist": true
}
```

### 查最新 trace

```bash
/ov-recall-trace
```

### 查最近 10 條自動召回

```bash
/ov-recall-trace --turn all --source auto_recall --limit 10
```

### 查指定 trace 詳情

```bash
/ov-recall-trace --trace-id <traceId> --include-content
```

### HTTP 查詢

```bash
curl 'http://127.0.0.1:<gateway-port>/api/openviking/recall-traces?turn=all&source=memory_recall&limit=10'
```

### HTTP 查詢單條

```bash
curl 'http://127.0.0.1:<gateway-port>/api/openviking/recall-traces/<traceId>?includeContent=true'
```
