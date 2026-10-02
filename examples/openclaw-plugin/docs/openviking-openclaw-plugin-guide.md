# Business Data Platform OpenClaw 外掛幫助文件

> 本文件面向外掛使用者、整合方、排障同學和後續維護者，系統梳理 `@openviking/openclaw-plugin` 的實現原理、執行流程、核心功能、安裝配置、構建測試、Debug、釋出上線與驗證方式，以及它與火山 Business Data Platform 的聯動機制。

## 1. 一句話結論

`@openviking/openclaw-plugin` 是一個 OpenClaw `context-engine` 外掛。它把 OpenClaw 的會話生命週期、上下文組裝、記憶召回、會話歸檔、工具結果回讀、資源/技能匯入等能力，通過 HTTP API 接到遠端 Business Data Platform 服務上，讓 Agent 擁有長期記憶、工作記憶、歷史壓縮、語義檢索和 RAG 能力。

它不負責啟動本地 Business Data Platform Server，也不替代 OpenClaw Runtime；OpenClaw 仍負責 Agent 執行、prompt 編排和工具呼叫，Business Data Platform 負責上下文資料庫、長期記憶、session/archive、resource/skill 檢索與服務端抽取。

---

## 2. 外掛解決的問題

| 問題 | 沒有外掛時的表現 | 外掛提供的能力 |
| --- | --- | --- |
| 長對話上下文膨脹 | 會話越來越長，token 成本和模型輸入風險持續上升 | 通過 Business Data Platform session/archive 把長曆史壓縮為工作記憶，並在 `assemble` 時重建可控上下文 |
| 過去偏好/事實容易遺忘 | Agent 需要使用者反覆提醒 | `autoRecall` 自動搜尋長期記憶並注入當前 user message |
| 會話歷史壓縮後細節丟失 | summary 不含原命令、路徑、配置值時難以追溯 | `ov_archive_search` / `ov_archive_expand` 回查歸檔原文 |
| 大工具結果汙染上下文 | 大量工具輸出擠佔模型視窗 | Business Data Platform 支援 tool result 外接儲存，外掛提供讀/搜/列工具 |
| 文件、倉庫、URL 無法沉澱為知識庫 | Agent 臨時讀取，跨會話不可複用 | 手動 `/add-resource` 匯入 resource，`ov_search` / `ov_read` 檢索消費；Agent 可見 `add_resource` 預設停用 |
| Skill 難以沉澱和語義發現 | 技能依賴本地或手工注入 | `add_skill` 匯入到 Business Data Platform agent skill 空間 |
| 多租戶/多 Agent 記憶串用 | 不同 session/agent 可能共用錯誤上下文 | 外掛按 `sessionId/sessionKey/agentId/peer_prefix` 解析 `X-OpenViking-Actor-Peer`，並支援 account/user header 與 peer identity routing |

---

## 3. 架構定位

### 3.1 外掛在 OpenClaw 中的形態

外掛清單聲明瞭它是 `context-engine` 外掛，並在啟動時啟用 hook/tool 能力：`openclaw.plugin.json:2`、`openclaw.plugin.json:4`、`openclaw.plugin.json:6`。

包元資訊中，外掛通過 OpenClaw 擴充入口載入 `./dist/index.js`，並提供 setup CLI 入口 `./dist/commands/setup.js`：`package.json:57`。

外掛在執行時主要承擔四個角色：

1. **Context Engine**：實現 `assemble`、`afterTurn`、`compact`，並宣告自己擁有 compaction。
2. **Hook 整合層**：監聽 `session_start`、`session_end`、`before_reset` 等事件。
3. **Tool Provider**：註冊 memory、archive、resource、skill、tool-result 相關工具。
4. **Runtime/Setup 管理層**：提供 `openclaw openviking setup/status`，並在服務啟動時做 health check。

### 3.2 核心檔案職責

| 檔案 | 主要職責 |
| --- | --- |
| `index.ts` | 外掛註冊入口；解析配置；註冊工具、命令、hook、context engine 和 service |
| `context-engine.ts` | 實現 ContextEngine：`assemble`、`afterTurn`、`compact`、session ID 對映、訊息轉換、工作記憶組裝 |
| `client.ts` | Business Data Platform HTTP Client；統一新增認證/租戶/agent header；封裝 session、search、resource、skill、tool-result API |
| `config.ts` | 外掛配置 schema、預設值、環境變數解析、peer identity routing 配置 |
| `auto-recall.ts` | 自動召回查詢清洗、召回超時控制、記憶塊構建與注入 |
| `memory-ranking.ts` | 顯式 `memory_recall` 的結果去重、閾值過濾和本地重排；自動召回由服務端組裝 |
| `text-utils.ts` | 會話文本清洗、metadata/心跳/命令過濾、增量 turn 訊息提取、bypass session pattern |
| `commands/setup.ts` | setup/status CLI，配置寫入、health check、root/user key 探測、slot 啟用 |
| `session-transcript-repair.ts` | 修復 toolCall/toolResult 配對、去重、孤兒 tool result 等 transcript 結構問題 |

---

## 4. 執行流程總覽

### 4.1 外掛載入流程

1. OpenClaw 根據外掛入口載入 `index.ts` 的預設匯出。
2. `register(api)` 讀取 `api.pluginConfig`，用 `memoryOpenVikingConfigSchema.parse` 解析配置；解析失敗時只註冊 setup CLI，提示使用者執行 setup：`index.ts:558`、`index.ts:576`。
3. 建立 `OpenVikingClient`，注入 `baseUrl`、`apiKey`、`peer_prefix`、超時、租戶與 peer policy：`index.ts:625`。
4. 註冊工具、slash command、hook、context engine 與 service：`index.ts:872`、`index.ts:962`、`index.ts:1913`、`index.ts:1945`、`index.ts:1970`。
5. Service 啟動時呼叫 `/health` 做一次非阻塞 health check，並輸出初始化日誌：`index.ts:1970`。

### 4.2 會話 ID 與 Agent 路由流程

OpenClaw 的 `sessionId/sessionKey` 不能總是直接作為 Business Data Platform 儲存路徑。外掛用 `openClawSessionToOvStorageId` 生成安全穩定的 Business Data Platform session id：

- 如果 `sessionId` 是 UUID，直接小寫複用。
- 如果有 `sessionKey`，用 SHA-256 生成穩定 id。
- 如果非 UUID 的 `sessionId` 包含 Windows 路徑不安全字元，也用 SHA-256。
- 否則使用原 `sessionId`。

實現位置：`context-engine.ts:342`。

Agent 路由由 `createSessionAgentResolver` 維護，優先從 session context 解析/記憶 agent，然後根據 `peer_prefix` 生成 `X-OpenViking-Actor-Peer`：`index.ts:470`。字元會經過 `sanitizeOpenVikingAgentIdHeader` 清洗，保證只包含 `[a-zA-Z0-9_-]`：`index.ts:226`。

### 4.3 `assemble`：回覆前組裝上下文

OpenClaw 會在 context engine 上呼叫 `assemble`。當前實現把 assemble 分成兩類：

| 呼叫形態 | 判斷方式 | 外掛行為 |
| --- | --- | --- |
| 主 assemble / preflight | 引數帶 `prompt`、`availableTools` 或 `citationsMode` | 從 Business Data Platform 獲取 session context，回放 archive summary + active messages |
| transformContext assemble | 不帶上述欄位，通常最後一條已經是當前 user | 執行 auto recall，把長期記憶塊 prepend 到最新 user message |

判斷邏輯在 `context-engine.ts:1097`。

主 assemble 流程：

1. 解析 session 身份，計算 token budget，記錄診斷日誌。
2. 呼叫 `GET /api/v1/sessions/{sessionId}/context?token_budget=...`：`context-engine.ts:1193`、`client.ts:873`。
3. 如果 Business Data Platform 沒有可用 archive/session 資料，直接 passthrough，不影響主鏈路。
4. 將 `latest_archive_overview` 轉成 `[Session History Summary]`。
5. 將 Business Data Platform parts 訊息轉換為 OpenClaw `AgentMessage`，包括 tool part → `toolCall` + `toolResult`。
6. 修復 transcript：合併連續 user/assistant、修復 toolCall/toolResult 配對，必要時插入佔位 user 以滿足 provider 交替約束。
7. 返回組裝後的 messages 和可選 `systemPromptAddition`。

transformContext auto recall 流程：

1. 從最新 user message 提取查詢文本。
2. 清洗 metadata、心跳、已注入記憶塊等噪音。
3. 快速 precheck，Business Data Platform 不可用時跳過召回，避免拖慢模型請求。
4. 向 `POST /api/v1/search/search` 傳送一次 `mode="context"` 請求，並把對映後的 Business Data Platform session ID、Actor Peer 和 `recallTargetTypes` 一併傳入。
5. 服務端結合 session 歷史擴充查詢，完成閾值過濾、排序、5 輪跨輪去重和內容層級選擇。
6. `recallMaxInjectedChars` 按 4 字元/token 轉成服務端 `max_tokens`，由服務端在預算內生成 `rendered` 上下文。
7. 外掛只保留 `<relevant-memories>` 外層標記並 prepend 到最新 user message，不再逐條 `read` 或本地重排。

自動召回實現入口：`services/context-lifecycle-service.ts` 的 transformContext assemble 路徑，以及 `auto-recall.ts` 的 `buildAutoRecallContext()`。

### 4.4 `afterTurn`：每輪對話後自動捕獲

`afterTurn` 負責把本輪新增訊息寫入 Business Data Platform session，並在 `pending_tokens` 超過閾值時非同步 commit。

流程：

1. 若 `autoCapture=false`、heartbeat 或 session 被 bypass，直接跳過。
2. 根據 `prePromptMessageCount` 只提取本輪新增訊息，不重寫全量 transcript。
3. `extractNewTurnMessages` 將 user/assistant 文本和 toolResult 轉成 Business Data Platform parts：`text-utils.ts:342`。
4. 清理 `<relevant-memories>`、metadata、時間戳、心跳等噪音。
5. 逐條呼叫 `POST /api/v1/sessions/{sessionId}/messages`：`context-engine.ts:1378`、`client.ts:703`。
6. 調 `GET /api/v1/sessions/{sessionId}` 讀取 `pending_tokens`：`context-engine.ts:1389`、`client.ts:770`。
7. 若 `pending_tokens < tokenBudget × commitTokenThresholdRatio`，本輪結束。
8. 否則呼叫 `commitSession(wait=false, keepRecentCount=cfg.commitKeepRecentCount)`；服務端 Phase 2 記憶抽取非同步繼續執行：`context-engine.ts:1403`。
9. 開啟 `logFindRequests` 時，外掛輪詢 task 結果並列印 Phase 2 抽取狀態：`context-engine.ts:1424`。

### 4.5 `compact`：主動壓縮邊界

`compact` 是同步邊界，用於 `/compact` 或 OpenClaw 觸發壓縮時阻塞等待服務端 commit 完成。

流程：

1. 解析 Business Data Platform session id。
2. 呼叫 `commitSession(wait=true, keepRecentCount=0)`，要求服務端歸檔所有當前訊息：`context-engine.ts:1500`。
3. 如果 Phase 2 failed/timeout，返回失敗原因。
4. 如果沒有生成 archive，返回 `commit_no_archive`。
5. 如果歸檔成功，再回讀 `getSessionContext`，獲取最新 `latest_archive_overview` 作為 summary：`context-engine.ts:1605`。
6. 返回 tokensBefore/tokensAfter、latest archive id 和 summary。

### 4.6 `before_reset`：重置前保護性提交

外掛監聽 `before_reset`，在 reset 前儘量 commit 當前 Business Data Platform session，避免對話被重置時未歸檔內容丟失：`index.ts:1919`。

---

## 5. 核心功能

### 5.1 長期記憶自動召回

預設開啟 `autoRecall`。模型回覆前，外掛會根據當前使用者問題搜尋長期記憶，並注入相關上下文。

關鍵配置：

| 配置 | 預設值 | 說明 |
| --- | --- | --- |
| `autoRecall` | `true` | 是否啟用自動召回 |
| `recallLimit` | `6` | 最終注入記憶條數上限 |
| `recallScoreThreshold` | `0.15` | 候選過濾閾值 |
| `recallMaxInjectedChars` | `4000` | 注入總字元上限；單條記憶不截斷，不完整則跳過 |
| `recallPreferAbstract` | `false` | 是否優先使用 abstract，而非讀取 leaf 記憶全文 |
| `recallTargetTypes` | `["user","agent"]` | 自動召回和預設顯式召回目標型別；可選 `resource`、`user`、`agent` |
| `recallResources` | `false` | 舊相容開關；僅在未顯式配置 `recallTargetTypes` 時把 `resource` 追加到預設 `user` + `agent` |

配置預設值在 `config.ts:58`。

### 5.2 會話歸檔與 Working Memory

外掛把 OpenClaw turn 持續寫入 Business Data Platform session，由服務端維護 `pending_tokens` 與 archive。超過閾值時：

- `afterTurn` 路徑：`wait=false`，非同步 Phase 2，預設保留最近 10 條訊息。
- `compact` 路徑：`wait=true`，同步等待 Phase 2，`keepRecentCount=0`，形成明確壓縮邊界。

`commitKeepRecentCount` 預設 10，`commitTokenThresholdRatio` 預設 0.5（模型上下文視窗的 50%）：`config.ts`。

### 5.3 顯式記憶工具

外掛註冊了三個長期記憶工具：

| 工具 | 用途 | 典型場景 |
| --- | --- | --- |
| `memory_recall` | 顯式搜尋長期記憶 | 使用者問“你還記得我之前說過什麼嗎” |
| `memory_store` | 把文本立即寫入 session 並同步 commit | 使用者明確說“記住…” |
| `memory_forget` | 按 URI 刪除，或搜尋唯一高置信候選後刪除 | 使用者要求忘記某條資訊 |

註冊位置：`index.ts:1022`、`index.ts:1190`、`index.ts:1309`。

### 5.4 Archive 回查工具

| 工具 | 用途 | 注意事項 |
| --- | --- | --- |
| `ov_archive_search` | 在當前 session 的 archive 原始訊息中關鍵詞 grep | 用於 summary 沒有具體細節時；建議嘗試 2-3 個關鍵詞 |
| `ov_archive_expand` | 展開某個 archive 的原始訊息 | 需要 archive id，例如 `archive_005` |

註冊位置：`index.ts:1421`、`index.ts:1522`。

### 5.5 Resource / Skill 匯入與檢索

| 工具/命令 | 用途 | 落點 |
| --- | --- | --- |
| `/add-resource`（手動）/ `add_resource`（opt-in） | 匯入本地檔案、目錄、URL、Git 倉庫、媒體附件；`add_resource` 預設不註冊，需 `enableAddResourceTool=true` | `viking://resources/...` |
| `add_skill` / `/add-skill` | 匯入 `SKILL.md` 或 skill 目錄 | `viking://user/skills/...` |
| `ov_search` / `/ov-search` | 搜尋 resources 和 skills | 默認同時搜 resources + agent skills |
| `ov_read` | 讀取 `ov_search` / trace 命中的完整內容 | 只接受精確 `viking://...` Business Data Platform 虛擬 URI |

本地檔案/目錄不會把原路徑直接傳給服務端，而是先 temp upload；目錄會用純 JS zip 打包後上傳：`client.ts:609`、`client.ts:552`。

### 5.6 外接 Tool Result 回讀

當 Business Data Platform 服務端將大工具結果外接為 `viking://session/.../tool-results/...` 時，外掛提供：

| 工具 | 用途 |
| --- | --- |
| `openviking_tool_result_list` | 列出當前 session 已外接的 tool result |
| `openviking_tool_result_search` | 在某個外接 tool result 內關鍵詞搜尋，返回 offset 和上下文片段 |
| `openviking_tool_result_read` | 按 offset/limit 讀取完整或分頁內容 |

註冊位置：`index.ts:1601`、`index.ts:1698`、`index.ts:1802`。外掛會拒絕跨 session 讀取 tool result，避免越權或串會話：`index.ts:1639`、`index.ts:1735`。

---

## 6. 與火山 Business Data Platform 的聯動方式

### 6.1 HTTP Client 與認證頭

外掛是 Business Data Platform 的純 HTTP Client。所有請求統一走 `OpenVikingClient.request`：`client.ts:313`。

請求頭邏輯：

| Header | 來源 | 說明 |
| --- | --- | --- |
| `X-API-Key` | `apiKey` / `OPENVIKING_API_KEY` | Business Data Platform API Key |
| `X-OpenViking-Account` | `accountId` / `OPENVIKING_ACCOUNT_ID` | Root key 或 trusted 部署需要的租戶 account |
| `X-OpenViking-User` | `userId` / `OPENVIKING_USER_ID` | Root key 或 trusted 部署需要的使用者 |
| `X-OpenViking-Actor-Peer` | 當前 session 解析出的 agentId | 用於 peer scope 隔離 |

注意：配置說明中歷史文件可能提到 `X-OpenViking-Key`，當前程式碼實際傳送的是 `X-API-Key`：`client.ts:325`。

### 6.2 Business Data Platform 官方 API 完整清單與外掛對映

官方 HTTP API 統一字首為 `/api/v1/`，成功響應一般為 `{ "status": "ok", "result": ..., "time": ... }`，錯誤響應為 `{ "status": "error", "error": { "code", "message" }, "time" }`。外掛只做 HTTP Client，不嵌入 Business Data Platform SDK；統一封裝點是 `OpenVikingClient.request`：`client.ts:313`。

#### 6.2.1 System / Observer

| API | 官方用途 | 當前外掛對映 | 說明 |
| --- | --- | --- | --- |
| `GET /health` | 無認證健康檢查 | `healthCheck`、`openclaw openviking status` | 用於判斷服務是否可達：`client.ts:365` |
| `GET /ready` | 無認證 readiness probe | 暫未直接封裝 | K8s/負載均衡可用；會檢查 AGFS、VectorDB、API key manager |
| `GET /api/v1/system/status` | 獲取初始化狀態和當前 user | `getRuntimeIdentity` | 外掛用返回的 `user` 參與 canonical URI 展開：`client.ts:369` |
| `POST /api/v1/system/wait` | 等待 semantic/vector 佇列處理完成 | 暫未單獨封裝；`/add-resource`、opt-in `add_resource`、`add_skill` 可用 `wait=true` | 匯入後馬上檢索時建議等待 |
| `GET /api/v1/observer/queue` | 佇列指標 | 暫未封裝 | 排查資源/skill 處理積壓 |
| `GET /api/v1/observer/vikingdb` | VikingDB collection/vector 狀態 | 暫未封裝 | 排查向量庫連線和索引數量 |
| `GET /api/v1/observer/models` | 模型狀態 | 暫未封裝 | 觀測 VLM、Embedding 和 Rerank 模型狀態 |
| `GET /api/v1/observer/system` | 彙總 observer 狀態 | 暫未封裝 | 生產監控推薦項 |
| `GET /api/v1/debug/health` | 認證版健康檢查 | 暫未封裝 | 返回 `{ healthy: true/false }` |

#### 6.2.2 Retrieval / Search

| API | 官方用途 | 當前外掛對映 | 關鍵引數 / 返回 |
| --- | --- | --- | --- |
| `POST /api/v1/search/find` | 快速語義檢索，不依賴 session context | 自動召回、`memory_recall`、`ov_search`、`memory_forget` | body: `query`、`target_uri`、`limit`、`score_threshold`；返回 `memories[]`、`resources[]`、`skills[]`，每項含 `uri`、`level`、`abstract`、`score`、`category`：`client.ts:428` |
| `POST /api/v1/search/search` | 帶 session context 和 intent analysis 的檢索 | 暫未使用 | body 可帶 `session_id`；返回 `query_plan` / `query_results`。當前外掛為了穩定和低延遲統一用 `find()`，session context 由外掛自己組裝 |
| `POST /api/v1/search/grep` | 正則/關鍵詞內容搜尋 | `ov_archive_search` | body: `uri`、`pattern`、`case_insensitive`、`node_limit`；外掛限定在 `viking://session/{id}/history` 內搜 archive：`client.ts:897` |
| `POST /api/v1/search/glob` | glob 檔案匹配 | 暫未封裝 | body: `pattern`、`uri`、`node_limit`；適合按 `**/*.md`、`src/**/*.ts` 找資源路徑 |

#### 6.2.3 Filesystem / Content

| API | 官方用途 | 當前外掛對映 | 關鍵引數 / 返回 |
| --- | --- | --- | --- |
| `GET /api/v1/fs/ls?uri=...` | 列目錄 | skill 列表官方頁本質也複用該 API；外掛暫未通用封裝 | 支援 `simple`、`recursive`、`output=agent/original`、`abs_limit`、`show_all_hidden`、`node_limit` |
| `GET /api/v1/fs/tree?uri=...` | 遞迴樹 | 暫未封裝 | 支援 `level_limit`、`node_limit`，返回 flat array + `rel_path` |
| `GET /api/v1/fs/stat?uri=...` | 查元資訊/是否存在 | 暫未封裝 | 返回 `name`、`size`、`mode`、`isDir`、`uri`、`mtime`、`ctime` |
| `POST /api/v1/fs/mkdir` | 建立目錄 | 暫未封裝 | body: `uri`，父目錄自動建立 |
| `POST /api/v1/fs/mv` | 移動/重新命名 | 暫未封裝 | body: `from_uri`、`to_uri`，會保留後設資料 |
| `DELETE /api/v1/fs?uri=...&recursive=...` | 刪除資源/目錄 | `memory_forget`、`deleteUri` | 外掛預設 `recursive=false`，用於刪除具體 memory URI：`client.ts:934` |
| `GET /api/v1/content/abstract?uri=...` | 讀取 L0 abstract | 暫未封裝 | 約 100 token 摘要，適合快速判斷目錄/檔案主題 |
| `GET /api/v1/content/overview?uri=...` | 讀取 L1 overview | 暫未封裝 | 目錄級結構化概覽，適合介於 abstract 和 full content 之間的排查 |
| `GET /api/v1/content/read?uri=...&offset=...&limit=...` | 讀取 L2 full content | 顯式 `memory_recall`、`ov_read` | 自動召回的分層讀取已由服務端 context search 完成；`ov_read` 暴露 `uri` 引數，未暴露 `offset/limit`。 |

#### 6.2.4 Resources / Skills Import

| API | 官方用途 | 當前外掛對映 | 關鍵引數 / 返回 |
| --- | --- | --- | --- |
| `POST /api/v1/resources/temp_upload` | 臨時上傳本地檔案 | `/add-resource`、opt-in `add_resource`、`add_skill` 的本地檔案/目錄路徑 | 外掛本地目錄會先 zip，再上傳，服務端返回 `temp_file_id`：`client.ts:533`、`client.ts:552` |
| `POST /api/v1/resources` | 匯入檔案、目錄、URL、Git 倉庫等 resource | `/add-resource` 命令；`add_resource` 工具僅在 `enableAddResourceTool=true` 時註冊 | body 官方欄位包括 `path`/`temp_file_id`、`target`/外掛相容 `to`、`parent`、`reason`、`instruction`、`wait`、`timeout`、`strict`、`ignore_dirs`、`include`、`exclude`；返回 `root_uri`、`source_path`、`errors`、`queue_status`：`client.ts:609` |
| `POST /api/v1/skills` | 匯入 skill，支援 dict、MCP tool、SKILL.md 字串、檔案/目錄 | `add_skill` 工具、`/add-skill` 命令 | body: `data` 或 `temp_file_id`、`wait`、`timeout`；返回 `uri`/`skill_uri`、`name`、`auxiliary_files`、`queue_status`：`client.ts:663` |
| `POST /api/v1/pack/export` | 匯出 `.ovpack` | 暫未封裝 | 官方 API Overview 有列出；當前外掛沒有 pack 管理工具 |
| `POST /api/v1/pack/import` | 匯入 `.ovpack` | 暫未封裝 | 官方 API Overview 有列出；當前外掛沒有 pack 管理工具 |

#### 6.2.5 Sessions / Working Memory

| API | 官方用途 | 當前外掛對映 | 關鍵引數 / 返回 |
| --- | --- | --- | --- |
| `POST /api/v1/sessions` | 建立新 session | 暫未顯式呼叫 | 官方建立後返回 `session_id`；當前外掛用 OpenClaw session id 對映成 Business Data Platform storage id，服務端 `GET`/寫訊息可自動建立 |
| `GET /api/v1/sessions` | 列出當前使用者 session | 暫未封裝 | 返回 `session_id`、`uri`、`is_dir` |
| `GET /api/v1/sessions/{sessionId}` | 獲取 session 元資訊 | `afterTurn` 元資訊檢查 | 返回 `message_count`，外掛相容讀取 `commit_count`、`pending_tokens`、`llm_token_usage`：`client.ts:770` |
| `DELETE /api/v1/sessions/{sessionId}` | 刪除 session | `deleteSession`（內部能力，未暴露普通使用者工具） | 刪除 active messages、archives、tools、後設資料；不刪除已抽取 memories：`client.ts:931` |
| `POST /api/v1/sessions/{sessionId}/messages` | 追加 user/assistant 訊息 | `afterTurn` 增量提交 | body 支援 `role`、`content` 或 `parts`；外掛使用 `parts` 儲存 text/tool/context，另擴充 tool result 外接欄位：`client.ts:703` |
| `POST /api/v1/sessions/{sessionId}/commit` | 歸檔訊息、抽取長期記憶、清空/保留 active buffer | `afterTurn` 非同步 commit、`compact` 同步 wait | 外掛會傳 `keep_recent_count`；若服務端返回 `task_id`，外掛可輪詢 Phase 2：`client.ts:798` |
| `GET /api/v1/tasks/{taskId}` | 查詢非同步任務 | commit Phase 2 輪詢 | 官方導航未單列，但外掛依賴該端點判斷 memory extraction 完成/失敗：`client.ts:864` |
| `GET /api/v1/sessions/{sessionId}/context?token_budget=...` | 獲取 session working memory 上下文 | `assemble` / `compact` | 返回 latest archive overview、pre archive abstracts、active messages 和 token 估算：`client.ts:873` |
| `GET /api/v1/sessions/{sessionId}/archives/{archiveId}` | 展開 archive 原文 | `ov_archive_expand` | 用於從有損 summary 回查原始訊息：`client.ts:885` |
| `GET /api/v1/sessions/{sessionId}/tool-results` | 列外接工具結果 | `openviking_tool_result_list` | 支援 `tool_name`、`limit`：`client.ts:517` |
| `GET /api/v1/sessions/{sessionId}/tool-results/{toolResultId}` | 分頁讀取外接工具結果 | `openviking_tool_result_read` | 支援 `offset`、`limit`、`include_metadata`：`client.ts:478` |
| `GET /api/v1/sessions/{sessionId}/tool-results/{toolResultId}/search?q=...` | 搜尋外接工具結果 | `openviking_tool_result_search` | 支援 `limit`、`context_chars`：`client.ts:498` |

#### 6.2.6 Skills Runtime

| API | 官方用途 | 當前外掛對映 | 說明 |
| --- | --- | --- | --- |
| `GET /api/v1/fs/ls?uri=viking://user/skills/` | 列 skill | `ov_search` 預設會搜 skills；未單獨 list | 官方 `List Skills` 頁面本質複用 `fs/ls` |
| `POST /api/v1/skills` | Add Skill / MCP tool conversion | `add_skill` | 與資源匯入章節相同 |
| 讀取 `viking://user/skills/{name}/SKILL.md` | 讀 skill 全文 | `ov_read` 或 `content/read` 手工讀取 | 官方建議按 L0/L1/L2 逐級讀取 |
| `call-skill` 頁面 | 官方導航存在但當前內容實際為 Add Skill | 外掛不通過 Business Data Platform 執行 skill | OpenClaw 自己負責工具執行，Business Data Platform 主要儲存/檢索 skill 文件 |

#### 6.2.7 Admin / Authentication

| API | 角色 | 官方用途 | 外掛關係 |
| --- | --- | --- | --- |
| `POST /api/v1/admin/accounts` | ROOT | 建立 workspace/account 和首個 admin | 部署初始化時使用；外掛執行期不呼叫 |
| `GET /api/v1/admin/accounts` | ROOT | 列出 workspaces | 運維使用 |
| `DELETE /api/v1/admin/accounts/{account_id}` | ROOT | 刪除 workspace 及全部資料 | 高風險運維操作，外掛不呼叫 |
| `POST /api/v1/admin/accounts/{account_id}/users` | ROOT/ADMIN | 註冊使用者並生成 user key | 為 OpenClaw agent 預置 API key 時使用 |
| `GET /api/v1/admin/accounts/{account_id}/users` | ROOT/ADMIN | 列使用者 | 運維排查租戶/使用者 |
| `DELETE /api/v1/admin/accounts/{account_id}/users/{user_id}` | ROOT/ADMIN | 移除使用者並吊銷 key | 運維使用 |
| `PUT /api/v1/admin/accounts/{account_id}/users/{user_id}/role` | ROOT | 修改角色 | 運維使用 |
| `POST /api/v1/admin/accounts/{account_id}/users/{user_id}/key` | ROOT/ADMIN | 重置使用者 API key | key 洩露/輪換時使用 |

認證方式：Business Data Platform HTTP 支援 `X-API-Key: <key>` 和 `Authorization: Bearer <key>`；外掛固定使用 `X-API-Key`。如果服務端啟用了多租戶且當前 key 需要顯式租戶上下文，外掛還會附加 `X-OpenViking-Account`、`X-OpenViking-User`、`X-OpenViking-Actor-Peer`。

### 6.3 URI 與名稱空間

外掛使用 Business Data Platform 的 filesystem paradigm，常見 URI：

| URI | 含義 |
| --- | --- |
| `viking://user/memories` | 當前使用者長期記憶別名 |
| `viking://resources` | account/resource 知識庫 |
| `viking://user/skills` | 當前 agent skill 空間 |
| `viking://session/{sessionId}/history` | session archive 歷史 |
| `viking://session/{sessionId}/tool-results/{id}` | 外接工具結果 |

外掛通過 `viking://user/...` 寫入和檢索 user-scoped memory；Business Data Platform 會根據請求裡的租戶身份和 actor peer context 解析這個別名。agent 維度通過 `peer_id` / `X-OpenViking-Actor-Peer` 表達，不再使用舊 agent URI namespace。

---

## 7. 安裝與使用

### 7.0 五分鐘快速路徑

如果你只想先把外掛跑起來，按這 4 步執行：

```bash
# 1. 確認 Business Data Platform Server 已啟動
curl http://127.0.0.1:1933/health

# 2. 安裝外掛
openclaw plugins install clawhub:@openviking/openclaw-plugin

# 3. 寫入 Business Data Platform 連線配置並激活 contextEngine slot
openclaw openviking setup --base-url http://127.0.0.1:1933 --api-key <OPENVIKING_API_KEY> --json

# 4. 重啟並驗證
openclaw gateway restart
openclaw openviking status --json
openclaw config get plugins.slots.contextEngine
```

期望結果：`status` 中 `configured=true`、`slotActive=true`、`health.ok=true`，並且 `plugins.slots.contextEngine` 輸出 `openviking`。

如果你安裝的是 TOS release 包，而不是 ClawHub 包，使用一鍵安裝指令碼：

```bash
# 安裝 prod 最新版本
curl -fsSL https://arkclaw-openviking.tos-cn-beijing.volces.com/prod/latest.json
bash install.sh --source tos --channel prod --latest \
  --openviking-base-url http://127.0.0.1:1933 \
  --openviking-api-key <OPENVIKING_API_KEY>

# 安裝指定版本 / 回滾到指定版本
bash install.sh --source tos --channel prod --version 2026.6.2
```

`scripts/install.sh` 會下載 `latest.json` / `manifest.json`、校驗 `openviking.tgz` SHA256、展開外掛到 `~/.openclaw/extensions/openviking`、部署隨包 skills、更新 `~/.openclaw/openclaw.json`，然後自動嘗試 `openclaw gateway restart` 和 `openclaw openviking status --json`：`scripts/install.sh:300`、`scripts/install.sh:175`、`scripts/install.sh:468`。

### 7.1 前置要求

| 元件 | 要求 |
| --- | --- |
| Node.js | >= 22 |
| OpenClaw | >= 2026.5.27 |
| Business Data Platform Server | >= 0.4.1 |

相容性宣告在 `install-manifest.json` 的 `compatibility` 欄位。

### 7.2 啟動 Business Data Platform Server

外掛只連線遠端 Business Data Platform，不啟動服務端。先啟動服務端：

```bash
pip install openviking --upgrade --force-reinstall
openviking-server init
openviking-server doctor
openviking-server --host 0.0.0.0 --port 1933
```

`openviking-server init` 會生成 Business Data Platform 服務端配置；`openviking-server doctor` 會檢查模型 provider、embedding provider、workspace 許可權等基礎依賴；`openviking-server` 才是真正啟動 HTTP API 的程序。OpenClaw 使用外掛期間，這個服務程序需要一直執行。

驗證服務：

```bash
curl http://127.0.0.1:1933/health
```

後臺啟動可以用：

```bash
mkdir -p ~/.openviking/data/log
nohup openviking-server > ~/.openviking/data/log/openviking.log 2>&1 &
```

如果 Business Data Platform 跑在另一臺機器或容器中，需要監聽可訪問地址：

```bash
openviking-server --host 0.0.0.0 --port 1933
```

此時 OpenClaw 外掛的 `baseUrl` 要配置為呼叫方可訪問的地址，例如 `http://your-server:1933`，而不是服務端本機視角的 `127.0.0.1`。

### 7.3 Business Data Platform 服務端配置檔案

Business Data Platform 服務端配置與 OpenClaw 外掛配置是兩層配置，位置不同、作用也不同：

| 配置層 | 預設位置 | 作用 | 常見寫入方式 |
| --- | --- | --- | --- |
| Business Data Platform 服務端 | `~/.openviking/ov.conf` | 配置服務端 workspace、日誌、embedding、VLM/model provider | `openviking-server init` 互動生成；也可提前建立檔案 |
| Business Data Platform 服務端自定義路徑 | `OV_CONFIG=/path/to/ov.conf` | 指定非預設配置檔案 | 啟動 `openviking-server` 前匯出環境變數 |
| OpenClaw 外掛層 | `~/.openclaw/openclaw.json` | 配置外掛連線哪個 Business Data Platform HTTP 服務、API key、account/user、召回/捕獲策略 | `openclaw openviking setup` 或 `openclaw config set` |
| 一鍵安裝指令碼環境檔案 | `~/.openclaw/openviking.env` | 儲存一鍵安裝指令碼使用過的 Business Data Platform 連線引數，便於排查/複用 | `scripts/volcengine-openviking-install.sh` |

最小 `~/.openviking/ov.conf` 示例：

```json
{
  "storage": {
    "workspace": "/Users/bytedance/.openviking/data"
  },
  "log": {
    "level": "INFO",
    "output": "stdout"
  },
  "embedding": {
    "dense": {
      "provider": "volcengine",
      "api_base": "https://ark.cn-beijing.volces.com/api/v3",
      "api_key": "$ARK_API_KEY",
      "model": "doubao-embedding-vision-250615",
      "dimension": 2048
    },
    "max_concurrent": 10
  },
  "vlm": {
    "provider": "volcengine",
    "api_base": "https://ark.cn-beijing.volces.com/api/v3",
    "api_key": "$ARK_API_KEY",
    "model": "doubao-seed-2-0-lite-260428",
    "max_concurrent": 20
  }
}
```

也可以使用 OpenAI / LiteLLM 等 provider，例如：

```json
{
  "storage": {
    "workspace": "/Users/bytedance/.openviking/data"
  },
  "embedding": {
    "dense": {
      "provider": "openai",
      "api_base": "https://api.openai.com/v1",
      "api_key": "$OPENAI_API_KEY",
      "model": "text-embedding-3-large",
      "dimension": 1536
    }
  },
  "vlm": {
    "provider": "openai",
    "api_base": "https://api.openai.com/v1",
    "api_key": "$OPENAI_API_KEY",
    "model": "gpt-4o"
  }
}
```

提前設定方式：

```bash
mkdir -p ~/.openviking
$EDITOR ~/.openviking/ov.conf

# 不建議把真實 key 寫進文件或命令歷史；優先通過環境變數注入
export ARK_API_KEY=<your-ark-key>
# 或 OpenAI provider：export OPENAI_API_KEY=<your-openai-key>

openviking-server doctor
openviking-server --host 127.0.0.1 --port 1933
```

如果要使用自定義配置檔案：

```bash
export OV_CONFIG=/path/to/ov.conf
openviking-server doctor
openviking-server --host 127.0.0.1 --port 1933
```

注意事項：

- `ov.conf` 是服務端模型與儲存配置，決定服務端如何做 embedding、VLM 抽取、resource 解析和 session archive；外掛不會讀取或修改這個檔案。
- `api_key` 欄位建議寫成 `$ARK_API_KEY`、`$OPENAI_API_KEY` 這類環境變數佔位，並在啟動服務前匯出真實 key，避免金鑰落盤或進入 Git。
- 切換 embedding 模型或 `dimension` 後，歷史向量索引可能不相容；本地測試環境可清理 workspace 後重建，生產環境需要按服務端遷移/重建索引方案處理。
- `workspace` 要放在服務端程序有讀寫許可權且磁碟容量足夠的位置，長期記憶、資源索引、歸檔和日誌都會持續增長。

### 7.4 本機拉起單機版測試

本機單機版適合開發、除錯和端到端驗證。推薦最小鏈路如下：

```bash
# 1. 安裝 Business Data Platform Python 包
python3 -m pip install openviking --upgrade --force-reinstall

# 2. 初始化服務端配置
openviking-server init

# 3. 匯出模型 provider key，或提前寫入自定義 ov.conf
export ARK_API_KEY=<your-ark-key>

# 4. 檢查服務端配置和 provider 可用性
openviking-server doctor

# 5. 啟動本地 HTTP 服務
openviking-server --host 127.0.0.1 --port 1933
```

另開一個終端驗證：

```bash
curl http://127.0.0.1:1933/health
```

然後配置 OpenClaw 外掛連線本機服務：

```bash
openclaw openviking setup \
  --base-url http://127.0.0.1:1933 \
  --api-key <OPENVIKING_API_KEY> \
  --json

openclaw gateway restart
openclaw openviking status --json
```

如果本機 Business Data Platform 服務沒有開啟 API key 校驗，可按服務端實際策略傳空 key 或測試 key；如果使用火山 Business Data Platform Service / root key / trusted server 流程，則按服務端要求補充 `--account-id` 和 `--user-id`。

單機版聯調檢查點：

1. `curl /health` 返回正常。
2. `openclaw openviking status --json` 中 `configured=true`、`health.ok=true`。
3. `openclaw config get plugins.slots.contextEngine` 輸出 `openviking`。
4. 與 Agent 對話一輪後，服務端日誌 `~/.openviking/data/log/openviking.log` 或前臺輸出能看到 session/message/commit 相關請求。
5. 觸發 `/compact` 或等待 `pending_tokens` 超過閾值後，在 Business Data Platform Console/TUI 或外掛工具中能檢索到 archive/memory。

### 7.5 安裝外掛

```bash
openclaw plugins install clawhub:@openviking/openclaw-plugin
```

不要使用 `clawhub install openviking` 安裝本外掛；那是另一個 AgentSkill，不是 OpenClaw 外掛。

### 7.6 配置插件

交互式：

```bash
openclaw openviking setup
```

非交互式：

```bash
openclaw openviking setup \
  --base-url http://127.0.0.1:1933 \
  --api-key sk-xxx \
  --json
```

如果使用 root key：

```bash
openclaw openviking setup \
  --base-url http://127.0.0.1:1933 \
  --api-key <ROOT_API_KEY> \
  --account-id <ACCOUNT_ID> \
  --user-id <USER_ID> \
  --json
```

如果已有別的 context engine 佔用 slot，確認要替換時才加：

```bash
openclaw openviking setup --base-url <URL> --api-key <KEY> --force-slot --json
```

### 7.7 重啟與驗證

```bash
openclaw gateway restart
openclaw openviking status --json
openclaw config get plugins.slots.contextEngine
```

期望：

- `configured=true`
- `slotActive=true`
- `health.ok=true`
- `plugins.slots.contextEngine` 輸出 `openviking`

### 7.8 TOS release 安裝指令碼用法

`scripts/install.sh` 支援四種來源，適合正式安裝、灰度、回滾、本地包驗證：

| 來源 | 命令 | 適用場景 |
| --- | --- | --- |
| `tos` | `bash install.sh --source tos --channel prod --latest` | 從 TOS 安裝某環境最新 release |
| `tos + version` | `bash install.sh --source tos --channel prod --version 2026.6.2` | 安裝或回滾到指定版本 |
| `tarball` | `bash install.sh --tarball ./output/openviking.tgz` | 安裝本地構建產物 |
| `local` | `bash install.sh --source local --tarball ./output/openviking.tgz` | 本地包除錯，等價 tarball 路徑 |
| `existing` | `bash install.sh --source existing --openviking-base-url ... --openviking-api-key ...` | 不覆蓋外掛檔案，只寫配置並重啟驗證 |

常用引數：

| 引數 | 說明 |
| --- | --- |
| `--channel stg|ppe|prod` | 選擇 release 環境 / TOS 字首，預設 `prod` |
| `--latest` | 使用 `<channel>/latest.json` 指向的版本，預設行為 |
| `--version <version>` / `--rollback-to <version>` | 使用 `<channel>/releases/<version>/manifest.json` |
| `--manifest-url <url>` | 直接指定 manifest 地址，用於臨時驗證 |
| `--verify-only` | 只下載並校驗，不部署、不重啟 |
| `--dry-run` | 列印將執行的命令，不真實執行 setup/restart |
| `--openviking-base-url` / `--openviking-api-key` | 安裝後直接執行非互動 setup |
| `--recall-target-types resource` | 安裝時把預設召回切到 resource-only |
| `--force-slot` | 已有其他 context engine 時強制切換到 `openviking` |

安裝指令碼會強校驗包內執行時依賴 `node_modules/@sinclair/typebox`，避免 OpenClaw 載入外掛時報缺失依賴：`scripts/install.sh:187`、`scripts/install.sh:193`。

---

## 8. 常用命令與工具用法

### 8.1 插件命令

```bash
# 配置
openclaw openviking setup

# 非交互配置
openclaw openviking setup --base-url http://127.0.0.1:1933 --api-key sk-xxx --json

# 狀態檢查
openclaw openviking status --json

# 查看配置
openclaw config get plugins.entries.openviking.config
openclaw config get plugins.slots.contextEngine
```

### 8.2 Slash Commands

```text
/add-resource ./README.md --to viking://resources/openviking-readme --wait
/add-resource https://example.com/spec.html --parent viking://resources/project-docs --wait
/add-skill ./skills/install-openviking-memory --wait
/ov-search "Business Data Platform install" --uri viking://resources/openviking-readme
/ov-search "memory install skill" --uri viking://user/skills
```

### 8.3 Agent 工具觸發場景

| 使用者意圖 | 推薦工具 |
| --- | --- |
| “記住這條偏好/事實” | `memory_store` |
| “你還記得我之前說過什麼嗎” | `memory_recall` |
| “忘掉那條記憶” | `memory_forget` |
| “把這個文件/目錄/URL/倉庫加入知識庫” | 手動 `/add-resource`；只有顯式開啟 `enableAddResourceTool=true` 時才使用 `add_resource` |
| “把這個 skill 匯入 Business Data Platform” | `add_skill` |
| “在 Business Data Platform 裡搜一下資源/技能” | `ov_search` |
| “讀取這個 Business Data Platform 命中 URI 的完整內容” | `ov_read` |
| “summary 裡沒有細節，回查歷史” | `ov_archive_search` / `ov_archive_expand` |
| “這個 tool result 被截斷了，讀取完整內容” | `openviking_tool_result_read` / `search` / `list` |

---

## 9. 配置引數說明

| 引數 | 預設值 | 說明 |
| --- | --- | --- |
| `mode` | `remote` | 相容欄位；當前僅支援 remote |
| `baseUrl` | `http://127.0.0.1:1933` | Business Data Platform HTTP 地址 |
| `apiKey` | 環境變數或空 | Business Data Platform API Key |
| `accountId` | 空 | Root key/trusted 部署需要 |
| `userId` | 空 | Root key/trusted 部署需要 |
| `peer_role` | `none` | 記憶歸屬：`none`、`assistant` 或 `sender`；舊值 `person` 作為 `sender` 的別名相容 |
| `peer_prefix` | 空 | Peer 路由字首；非空時形成 `<prefix>_<ctx.agentId>` |
| `targetUri` | `viking://user/memories` | 預設 memory search 目標 |
| `timeoutMs` | `15000` | HTTP 請求超時 |
| `autoCapture` | `true` | 是否每輪後寫入 Business Data Platform session |
| `captureMode` | `semantic` | `semantic` 全量候選；`keyword` 先過觸發詞 |
| `captureMaxLength` | `24000` | 自動捕獲文本最大長度 |
| `autoRecall` | `true` | 是否回覆前自動召回 |
| `autoRecallTimeoutMs` | `15000` | 服務端組裝自動召回的總超時；為 session query expansion 和檢索留出預算 |
| `recallTargetTypes` | `["user","agent"]` | 自動召回和預設顯式召回目標型別；可選 `resource`、`user`、`agent` |
| `recallResources` | `false` | 舊相容開關；僅在未顯式配置 `recallTargetTypes` 時追加 `resource` |
| `recallLimit` | `6` | 召回條數 |
| `recallScoreThreshold` | `0.15` | 召回閾值 |
| `recallMaxInjectedChars` | `4000` | 注入字元預算 |
| `commitTokenThresholdRatio` | `0.5` | `pending_tokens` 達到「模型上下文視窗 × 該比例」觸發 afterTurn commit（0-1，例 0.5=50%）；設 0 可每輪 commit |
| `commitKeepRecentCount` | `10` | afterTurn commit 後保留最近訊息數；compact 固定 0 |
| `bypassSessionPatterns` | `[]` | 匹配 sessionKey/sessionId 時完全繞過 Business Data Platform |
| `emitStandardDiagnostics` | `false` | 輸出 `openviking: diag {...}` 結構化診斷日誌 |
| `logFindRequests` | `false` | 輸出 routing/search/session 寫入日誌；也可用 `OPENVIKING_LOG_ROUTING=1` 或 `OPENVIKING_DEBUG=1` |
| `traceRecall` | `false` | Recall trace 總開關；不開啟時不記錄、不建目錄、查詢只返回未啟用提示 |
| `traceRecallPersist` | `false` | 是否把 trace 按日期追加寫入 JSONL |
| `traceRecallDir` | `~/.openclaw/openviking/recall-traces` | trace JSONL 儲存目錄 |
| `traceRecallRetentionDays` | `14` | trace 檔案保留天數 |
| `traceRecallLoadRecentDays` | `2` | gateway 啟動時預載入最近多少天 trace |
| `traceRecallMaxEntries` | `1000` | 記憶體 ring buffer 最大 trace 條數 |
| `traceRecallMaxResultsPerSearch` | `20` | 每個 search 儲存的候選結果上限 |
| `traceRecallPreviewChars` | `240` | trace 摘要 preview 截斷長度 |
| `traceRecallQueryMaxChars` | `4000` | trace 中儲存 query 的最大長度 |
| `traceRecallQueryMaxDays` | `14` | 查詢持久化 trace 時預設最多掃描多少天 |
| `traceRecallIncludeContentByDefault` | `false` | 查詢 trace 時是否預設讀取完整內容 |
| `traceRecallIncludeRawUserPreview` | `false` | 是否把原始使用者訊息 preview 寫入持久化層 |

環境變數解析邏輯在 `config.ts:139`、`config.ts:147`。

`peer_role` 決定 `viking://user/<user_id>` 下是否按互動物件建立 peer 記憶：

| 值 | 歸因與路徑 | 案例 |
| --- | --- | --- |
| `none`（預設） | user / assistant message 都不寫 `peer_id`；新增長期記憶位於 `viking://user/<user_id>/memories/...` | 通用場景，所有對話共享 user-level 記憶 |
| `assistant` | assistant message 寫入 `peer_id=<assistant_id>`；助手歸因記憶位於 `.../peers/<assistant_id>/memories/...` | **人是 Business Data Platform user**：Alice 使用 `main` 和 `research` 兩個助手，分別使用 `.../peers/main/...` 和 `.../peers/research/...` |
| `sender` | user message 寫入 `peer_id=<sender_id>`；傳送者歸因記憶位於 `.../peers/<sender_id>/memories/...` | **Agent 是 Business Data Platform user**：`support-agent` 面向 `customer-42` 和 `customer-99`，將兩人的 peer 記憶分開 |

`person` 是 `sender` 的舊別名；新配置統一使用 `sender`。Business Data Platform 會為每個使用者初始化受管的 `peers/` 容器，`none` 只表示不使用具體的 `peers/<peer_id>/memories` 子樹。在 peer 模式下，共享／自身記憶仍位於使用者根記憶目錄，召回範圍是共享記憶 + 當前 peer 記憶，不包含其他 peer。切換 scope 不會搬遷已有記憶。Session 路徑不受影響，始終位於 `viking://user/<user_id>/sessions/<session_id>`。

### 9.1 搜尋 / 召回相關配置總表

如果你關注的是“外掛裡的搜尋能力可以怎麼從外部設定”，可以按下面這張表看。這裡的“搜尋”包括三類：

- 自動召回：回覆前自動查長期記憶 / resources 並注入 `<relevant-memories>`
- 顯式檢索：`memory_recall`、`ov_search`、`ov_archive_search`
- 搜尋診斷：開啟 routing / find 日誌，排查“為什麼沒搜到 / 搜到了但沒注入”

| 配置項 | 作用範圍 | 預設值 | 可否寫入外掛配置檔案 | 可否用環境變數 | 環境變數名 | 說明 |
| --- | --- | --- | --- | --- | --- | --- |
| `baseUrl` | 所有搜尋/召回請求 | `http://127.0.0.1:1933` | 是 | 是 | `OPENVIKING_BASE_URL` / `OPENVIKING_URL` | Business Data Platform 服務地址；所有 context search、`find/read/grep/session` 都依賴它：`config.ts:139` |
| `apiKey` | 所有搜尋/召回請求 | 空 | 是 | 是 | `OPENVIKING_API_KEY` | HTTP 認證 key；不配通常只能訪問關閉認證的本地服務：`config.ts:202` |
| `accountId` | 多租戶搜尋路由 | 空 | 是 | 是 | `OPENVIKING_ACCOUNT_ID` | Root key / trusted 部署下顯式指定 account，影響搜尋命中空間：`config.ts:212` |
| `userId` | 多租戶搜尋路由 | 空 | 是 | 是 | `OPENVIKING_USER_ID` | Root key / trusted 部署下顯式指定 user，影響 user memory 檢索範圍：`config.ts:216` |
| `peer_role` | session peer 歸因和 actor-peer 路由 | `none` | 是 | 安裝指令碼/setup 引數支援 | `OPENVIKING_PEER_ROLE`（安裝指令碼寫入 setup 引數） | `none` 使用共享 user memory（預設）；`assistant` 用 runtime agent 歸因到 `peers/<assistant_id>`；`sender` 用 sender 身份歸因到 `peers/<sender_id>`；舊值 `person` 等價於 `sender` |
| `peer_prefix` | assistant peer 字首 | 空 | 是 | 間接支援 | 可通過配置值寫 `${ENV}` | 非空時拼成 `<prefix>_<ctx.agentId>`，用於 assistant `peer_id` 與 `X-OpenViking-Actor-Peer` |
| `targetUri` | `memory_recall` / `memory_forget` 預設搜尋範圍 | `viking://user/memories` | 是 | 否 | — | 未顯式傳 `targetUri` 時的預設 memory 搜尋位置：`config.ts:275`、`index.ts:1366` |
| `timeoutMs` | 所有搜尋/讀取請求超時 | `15000` | 是 | 否 | — | 控制 context search、`find/read/grep/session` 等 HTTP 請求超時：`config.ts:276` |
| `autoRecall` | 自動召回總開關 | `true` | 是 | 否 | — | 關閉後外掛不再在 `assemble()` 階段自動發起 recall：`config.ts:283`、`context-engine.ts:1132` |
| `autoRecallTimeoutMs` | 自動召回總超時 | `15000` | 是 | 否 | — | 覆蓋單次服務端 context search；預設值為最長 5 秒的 session query expansion 及後續檢索保留餘量。顯式配置的值仍會按 `1000..300000` ms 限制。 |
| `recallTargetTypes` | 自動召回 + 預設 `memory_recall` 資源型別集合 | `["user","agent"]` | 是 | 安裝指令碼/setup 引數支援 | `OPENVIKING_RECALL_TARGET_TYPES`（安裝指令碼寫入 setup 引數） | 當前預設只查 `user` + `agent` 記憶。設定為 `["resource"]` 才會切成 resource-only；可組合 `resource,user,agent`：`config.ts:174`、`config.ts:360` |
| `recallResources` | 自動召回 + 預設 `memory_recall` resources 相容開關 | `false` | 是 | 是 | `OPENVIKING_RECALL_RESOURCES` | 舊相容欄位；只有未顯式配置 `recallTargetTypes` 時才把 `resource` 追加到預設 `user` + `agent`，不會覆蓋顯式 resource-only：`config.ts:360` |
| `recallLimit` | 自動召回 / `memory_recall` 返回條數 | `6` | 是 | 否 | — | 自動召回按共享 context-search 契約對映為 coding quotas；顯式 `memory_recall` 仍按該值做最終選擇。 |
| `recallScoreThreshold` | 自動召回 / `memory_recall` 過濾閾值 | `0.15` | 是 | 否 | — | 自動召回交給服務端過濾；顯式 `memory_recall` 保留本地後處理。 |
| `recallMaxInjectedChars` | 自動召回 / `memory_recall` 注入預算 | `4000` | 是 | 否 | — | 自動召回按 4 字元/token 換算為服務端 `max_tokens`；顯式 `memory_recall` 仍使用字元預算。 |
| `recallPreferAbstract` | 自動召回讀取策略 | `false` | 是 | 否 | — | 為 `true` 時把服務端 detail 固定為 `abstract`；否則由服務端按類別選擇預設層級。 |
| `recallTokenBudget` | 自動召回預算舊別名 | 跟隨 `recallMaxInjectedChars` | 是 | 否 | — | 已廢棄，僅相容舊配置；解析時會摺疊為 `recallMaxInjectedChars`：`config.ts:257`、`config.ts:299` |
| `recallMaxContentChars` | 舊版單條截斷相容項 | `5000` | 是 | 否 | — | 已廢棄；當前自動召回不再裁剪單條 memory 內容：`config.ts:290` |
| `captureMode` | 間接影響可搜尋記憶的入庫方式 | `semantic` | 是 | 否 | — | 雖然不是“搜尋引數”，但它決定哪些使用者內容會先被寫入 session 並進入後續可檢索空間：`config.ts:203`、`config.ts:278` |
| `captureMaxLength` | 間接影響可搜尋記憶來源長度 | `24000` | 是 | 否 | — | 超過該長度的使用者文本不會完整進入自動捕獲鏈路：`config.ts:279` |
| `bypassSessionPatterns` | 繞過搜尋/召回 | `[]` | 是 | 否 | — | 命中指定 sessionId / sessionKey 時，外掛整條 Business Data Platform 鏈路直接跳過，包括 recall、store、archive search：`config.ts:311` |
| `logFindRequests` | 搜尋除錯日誌 | `false` | 是 | 是 | `OPENVIKING_LOG_ROUTING` / `OPENVIKING_DEBUG` | 開啟後會記錄 context search、`find`、session 寫入和 commit 路由資訊，便於排查檢索空間錯誤。 |
| `enabledTools` | Agent 可見工具白名單 | `default` 工具組 | 是 | 否 | — | 支援工具名或分組：`default`、`all`、`memory`、`resource_query`、`import`、`recall_trace`、`archive`、`tool_result`。例如只保留資源查詢：`["resource_query"]`。`add_resource` 即使被選中仍需 `enableAddResourceTool=true`：`config.ts:119`、`index.ts:688` |
| `disabledTools` | Agent 可見工具黑名單 | `[]`（`add_resource` 預設仍停用） | 是 | 否 | — | 在 `enabledTools` 之後應用，支援同樣的工具名或分組。例如保留預設工具但隱藏記憶相關工具：`["memory"]`，會停用 `memory_recall` / `memory_store` / `memory_forget`：`config.ts:136`、`config.ts:268` |

### 9.2 哪些配置只能走配置檔案，哪些可以直接走環境變數

#### 9.2.1 可直接通過環境變數生效的搜尋相關項

| 環境變數 | 對應配置項 | 作用 |
| --- | --- | --- |
| `OPENVIKING_BASE_URL` | `baseUrl` | 指定 Business Data Platform 服務地址 |
| `OPENVIKING_URL` | `baseUrl` | `baseUrl` 的相容別名 |
| `OPENVIKING_API_KEY` | `apiKey` | 指定 Business Data Platform API key |
| `OPENVIKING_ACCOUNT_ID` | `accountId` | 指定租戶 account |
| `OPENVIKING_USER_ID` | `userId` | 指定租戶 user |
| `OPENVIKING_PEER_ROLE` | `peer_role` | 安裝指令碼/setup 寫入的記憶歸屬（`none` / `assistant` / `sender`；相容舊值 `person`） |
| `OPENVIKING_PEER_PREFIX` | `peer_prefix` | 安裝指令碼/setup 寫入的 assistant peer 字首 |
| `OPENVIKING_RECALL_RESOURCES` | `recallResources` | 是否把 resources 納入自動召回和預設 memory_recall |
| `OPENVIKING_LOG_ROUTING` | `logFindRequests` | 開啟檢索/路由日誌 |
| `OPENVIKING_DEBUG` | `logFindRequests` | 同時作為除錯總開關，當前也會開啟 routing/find 日誌 |

#### 9.2.2 只能通過外掛配置檔案設定的搜尋行為項

這些項當前**沒有獨立環境變數**，需要寫到 `~/.openclaw/openclaw.json` 裡的 `plugins.entries.openviking.config`：

- `targetUri`
- `timeoutMs`
- `autoRecall`
- `recallTargetTypes`（可通過安裝指令碼 `--recall-target-types` 或 setup CLI 引數寫入配置，但執行時不是直接讀環境變數）
- `recallLimit`
- `recallScoreThreshold`
- `recallMaxInjectedChars`
- `recallPreferAbstract`
- `recallTokenBudget`（廢棄相容）
- `recallMaxContentChars`（廢棄相容）
- `captureMode`
- `captureMaxLength`
- `bypassSessionPatterns`

### 9.3 推薦配置示例

#### 9.3.1 Resource-only 召回配置

當前預設召回目標是使用者記憶 + Agent 記憶：`["user","agent"]`。如果你的場景主要是“匯入文件 / 知識庫問答”，並希望預設召回只查 `viking://resources`，需要顯式配置 `recallTargetTypes`：

```bash
openclaw config set plugins.entries.openviking.config.recallTargetTypes '["resource"]'
openclaw gateway restart
```

安裝時也可以直接寫入：

```bash
bash install.sh --source tos --channel prod --latest \
  --openviking-base-url http://127.0.0.1:1933 \
  --openviking-api-key <OPENVIKING_API_KEY> \
  --recall-target-types resource
```

注意：`recallResources=true` 是舊相容加法開關，只會在未顯式配置 `recallTargetTypes` 時把 `resource` 追加到預設 `user` + `agent`，不會把預設召回改成 resource-only。

#### 9.3.2 僅通過環境變數快速開啟“額外可搜 resources 的自動召回”

```bash
export OPENVIKING_BASE_URL="http://127.0.0.1:1933"
export OPENVIKING_API_KEY="<YOUR_KEY>"
export OPENVIKING_RECALL_RESOURCES=1
```

適合：你已經有穩定的 `openclaw.json`，只想臨時把 `viking://resources` 追加到自動召回和預設 `memory_recall`，同時保留預設 `user` + `agent` 記憶召回。

#### 9.3.3 通過外掛配置檔案精細控制召回和 trace

```json
{
  "plugins": {
    "entries": {
      "openviking": {
        "config": {
          "baseUrl": "${OPENVIKING_BASE_URL}",
          "apiKey": "${OPENVIKING_API_KEY}",
          "targetUri": "viking://user/memories",
          "autoRecall": true,
          "recallTargetTypes": ["user", "agent", "resource"],
          "recallLimit": 8,
          "recallScoreThreshold": 0.2,
          "recallMaxInjectedChars": 6000,
          "recallPreferAbstract": true,
          "logFindRequests": true,
          "traceRecall": true,
          "traceRecallPersist": true
        }
      }
    }
  }
}
```

這裡有兩個關鍵點：

- `baseUrl` / `apiKey` 支援在配置檔案裡寫 `${ENV}` 佔位，載入時會做環境變數替換：`config.ts:82`
- 但 `recallTargetTypes` / `recallLimit` / `recallScoreThreshold` / `autoRecall` / `traceRecall` 這類行為項不會從環境變數自動讀取，仍以配置檔案為準。
- 開啟 recall trace 必須顯式設定 `traceRecall=true`；只設置 `recallTargetTypes` 或 `recallResources` 不會啟用 trace。

### 9.4 外部配置生效順序

搜尋相關配置的實際生效順序可以概括為：

1. **顯式工具引數優先**：例如 `memory_recall(limit=3, scoreThreshold=0.4, targetUri=...)`、`/ov-search --limit 20 --uri ...` 會優先覆蓋預設配置：`index.ts:1046`、`index.ts:1050`、`index.ts:1054`、`index.ts:824`、`index.ts:408`
2. **插件配置文件其次**：`plugins.entries.openviking.config.*`
3. **環境變數補預設值**：只對少數支援 env 的項生效，如 `OPENVIKING_BASE_URL`、`OPENVIKING_API_KEY`、`OPENVIKING_RECALL_RESOURCES`：`config.ts:139`、`config.ts:202`、`config.ts:284`
4. **程式碼預設值兜底**：例如 `recallLimit=6`、`recallScoreThreshold=0.15`、`recallMaxInjectedChars=4000`：`config.ts:63`、`config.ts:64`、`config.ts:67`

### 9.5 搜尋相關配置的排查建議

| 現象 | 優先看哪些配置 | 典型原因 |
| --- | --- | --- |
| `memory_recall` 能搜到 memory，但自動回覆前沒有注入 | `autoRecall`、`recallScoreThreshold`、`recallMaxInjectedChars` | recall 命中了，但因閾值或預算被過濾掉 |
| `memory_recall` 預設搜不到 resources | `recallResources` | 預設是 `false`，不會自動查 `viking://resources` |
| 同樣的 query 在不同 agent / user 命中不一致 | `accountId`、`userId`、`peer_role`、`peer_prefix` | actor peer 或租戶身份不一致 |
| `/ov-search` 查不到剛匯入的內容 | `baseUrl`、`apiKey`、服務端佇列狀態 | 匯入後語義/向量處理還沒完成，或連到了錯誤服務 |
| 明明命中結果很多，但注入數量少 | `recallLimit`、`recallMaxInjectedChars`、`recallPreferAbstract` | limit 太小或預算太緊，必要時改成 abstract 優先 |
| 不知道外掛自動召回使用了哪些範圍 | `logFindRequests` | 開啟後檢視外掛日誌中的 context search routing；顯式檢索仍記錄 `find POST` |

---

## 10. Debug 與排障

### 10.1 快速狀態檢查

```bash
openclaw openviking status --json
openclaw plugins list
openclaw config get plugins.entries.openviking.config
openclaw config get plugins.slots.contextEngine
curl http://127.0.0.1:1933/health
```

### 10.2 開啟外掛側路由日誌

配置方式：

```bash
openclaw config set plugins.entries.openviking.config.logFindRequests true
openclaw gateway restart
```

或臨時環境變數：

```bash
OPENVIKING_LOG_ROUTING=1 openclaw gateway restart
```

日誌會列印 `X-OpenViking-Actor-Peer`、account/user header 是否設定、target_uri、query preview、session commit 等資訊，但不會列印 apiKey。

### 10.3 開啟標準診斷日誌

```bash
openclaw config set plugins.entries.openviking.config.emitStandardDiagnostics true
openclaw gateway restart
```

然後在日誌中搜索：

```text
openviking: diag {"stage":"assemble_entry"...}
openviking: diag {"stage":"assemble_result"...}
openviking: diag {"stage":"afterTurn_entry"...}
openviking: diag {"stage":"afterTurn_commit"...}
openviking: diag {"stage":"compact_result"...}
```

### 10.4 對話時觀測召回與文件命中

如果需要在與 OpenClaw 對話時確認“本輪到底從 Business Data Platform 召回了哪些資料、用了哪些文件、對應路徑是什麼”，推薦按以下順序排查。

#### 10.4.0 啟用 recall trace

Recall trace 是獨立的可觀測能力，必須開啟 `traceRecall=true` 才會記錄；只設置 `recallResources` 或 `recallTargetTypes` 只會改變召回範圍，不會自動啟用 trace。

```bash
# 只保留當前 gateway 程序內的記憶體 trace
openclaw config set plugins.entries.openviking.config.traceRecall true

# 如需 gateway 重啟後還能查歷史 trace，再開啟持久化
openclaw config set plugins.entries.openviking.config.traceRecallPersist true
openclaw config set plugins.entries.openviking.config.traceRecallDir ~/.openclaw/openviking/recall-traces

openclaw gateway restart
```

查詢方式：

```text
# Agent tool
ov_recall_trace(query="使用者問題關鍵詞", limit=10)

# Slash command
/ov-recall-trace --query "使用者問題關鍵詞" --limit 10

# Gateway route adapter 可用時
GET /api/openviking/recall-traces
GET /api/openviking/recall-traces/<traceId>
```

排查邊界：

| 配置狀態 | 行為 |
| --- | --- |
| `traceRecall=false` | 不記錄 trace，不建立 trace 目錄；查詢工具返回 trace 未啟用提示 |
| `traceRecall=true && traceRecallPersist=false` | 只查當前 gateway 程序內的 ring buffer；重啟後丟失 |
| `traceRecall=true && traceRecallPersist=true` | trace 追加寫入按日期分片的 JSONL；重啟後按配置預載入最近記錄，並可查詢 retention 範圍內檔案 |

#### 10.4.0.1 安裝後驗證真實 session 的 trace 查詢

安裝或升級後，建議用 OpenClaw 當前真實 `sessionKey` 驗證 `ov_recall_trace`，不要用日期或時間戳人為拼一個 session key 代替線上會話。真實 web session 的 trace 通常同時儲存：

- `entry.sessionKey`：OpenClaw 會話 key，例如 `agent:main:web-...`。
- `entry.sessionId` / `entry.ovSessionId`：OpenClaw 會話 UUID。

驗證命令：

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

TRACE_PARAMS="$(jq -cn \
  --arg sk "$SK" \
  '{
    name: "ov_recall_trace",
    sessionKey: $sk,
    args: {
      turn: "all",
      limit: 5
    }
  }'
)"

TRACE_RESULT="$(openclaw gateway call tools.invoke \
  --params "$TRACE_PARAMS" \
  --json
)"

echo "$TRACE_RESULT" | jq .
COUNT="$(echo "$TRACE_RESULT" | jq -r '.output.details.count // 0')"

if [ "$COUNT" -gt 0 ]; then
  echo "trace 查詢驗證成功，count=$COUNT"
else
  echo "trace 查詢驗證失敗，count=$COUNT" >&2
  exit 1
fi
```

如果升級前線上仍是舊版本，可臨時把業務過濾引數也顯式帶上，繞過舊版本沒有預設使用外層 `params.sessionKey` 的問題：

```json
{
  "name": "ov_recall_trace",
  "sessionKey": "<real-session-key>",
  "args": {
    "turn": "all",
    "limit": 5,
    "sessionKey": "<real-session-key>"
  }
}
```

當前版本預設使用外層 `params.sessionKey` 查詢當前 session trace；如果未命中且呼叫方沒有顯式設定 `args.sessionKey/sessionId/ovSessionId/traceId`，會繼續 fallback 到當前 session 的 `sessionId/ovSessionId`，以相容已落盤的歷史 JSONL。

#### 10.4.1 先開啟外掛側可觀測配置

```bash
# 打印 Business Data Platform search/session 路由、target_uri、query、agent/account/user header 等
openclaw config set plugins.entries.openviking.config.logFindRequests true

# 列印 assemble/afterTurn/compact 標準診斷
openclaw config set plugins.entries.openviking.config.emitStandardDiagnostics true

# 如果希望自動召回只查匯入的文件/URL/目錄資源，設定 resource-only
openclaw config set plugins.entries.openviking.config.recallTargetTypes '["resource"]'

# 如果希望保留預設 user/agent 記憶，同時額外查 resources，也可使用舊相容加法開關
openclaw config set plugins.entries.openviking.config.recallResources true

# 如果希望記錄本輪召回詳情，必須顯式開啟 trace
openclaw config set plugins.entries.openviking.config.traceRecall true

openclaw gateway restart
```

也可以臨時用環境變數開啟路由日誌：

```bash
OPENVIKING_LOG_ROUTING=1 openclaw gateway restart
# 或
OPENVIKING_DEBUG=1 openclaw gateway restart
```

#### 10.4.2 看日誌中的關鍵欄位

一次自動召回通常會產生三類可觀測資訊：

| 日誌/欄位 | 含義 | 關鍵路徑 |
| --- | --- | --- |
| `openviking: context search POST .../api/v1/search/search {...}` | 自動召回向 Business Data Platform 發起服務端組裝檢索 | `purpose` / `quotas` / `session_id` / `context_type` / `query_expansion` / `max_tokens` / `peer_scope` / actor 與租戶路由 |
| `openviking: find POST .../api/v1/search/find {...}` | 顯式 recall/search 工具發起底層語義檢索 | `target_uri` / `target_uri_input` / `query` / `X_OpenViking_Agent` |
| `openviking: injecting N memories ...` | 外掛決定向本輪 prompt 注入 N 條召回內容 | `N`、注入字元數、估算 token |
| `openviking: inject-detail {...}` | 本輪實際注入模型的服務端組裝條目摘要 | `entries[].uri`、`category`、`score`、`detail` |
| `openviking: diag {"stage":"assemble_result"...}` | assemble 階段是否發生自動召回 | `phase=transform_context`、`autoRecallMemoryCount` |

其中 `inject-detail` 是排查“本輪模型實際看到了哪些 Business Data Platform 召回內容”的首選入口。它會列出每條被注入內容的 `uri`，例如：

```text
openviking: inject-detail {"count":2,"memories":[{"uri":"viking://user/default/memories/preferences/...","category":"preferences","abstract":"...","score":0.82,"is_leaf":true},{"uri":"viking://resources/project-docs/api.md#chunk-3","category":"resource","abstract":"...","score":0.71,"is_leaf":true}]}
```

注意：自動注入到模型輸入裡的 `<relevant-memories>` 塊預設只包含類別和內容，不直接暴露 URI；URI/路徑主要從外掛日誌、`memory_recall` / `ov_search` 工具 `details`、或 Business Data Platform API 返回中獲取。

#### 10.4.3 用 OpenClaw 工具顯式復現召回

如果想把“命中的路徑”直接展示給 Agent 或使用者，可以讓 Agent 顯式呼叫工具：

```text
# 查長期記憶，預設查 user/agent memories；recallTargetTypes 可切換預設範圍
memory_recall(query="使用者問題關鍵詞", limit=10)

# 查匯入的文件、URL、目錄、倉庫資源
ov_search(query="使用者問題關鍵詞", uri="viking://resources", limit=10)

# 查 agent skills
ov_search(query="使用者問題關鍵詞", uri="viking://user/skills", limit=10)
```

`ov_search` 的文本結果會顯示 `type`、`uri`、`level`、`score` 和摘要；工具 `details` 裡也會保留原始 `resources[]` / `skills[]` / `memories[]` 陣列。

注意：這些 `uri` 是 Business Data Platform 虛擬 URI，不是本地檔案路徑。需要完整內容時，讓 Agent 呼叫 `ov_read(uri="viking://...")`，不要把 `viking://...` 或歷史相容展示裡的 `openviking://...` 當作本地路徑交給檔案讀取工具。

#### 10.4.4 直接呼叫 Business Data Platform API 獲取路徑和內容

外掛呼叫 Business Data Platform 時統一攜帶認證和路由 header。手工排查時也要保持一致：

```bash
export OPENVIKING_BASE_URL="http://127.0.0.1:1933"
export OPENVIKING_API_KEY="<your-api-key>"
export OPENVIKING_AGENT="<X-OpenViking-Actor-Peer-from-log>"

# root key / trusted server 場景按需補充
export OPENVIKING_ACCOUNT_ID="<account-id>"
export OPENVIKING_USER_ID="<user-id>"
```

語義檢索並獲取命中 URI：

```bash
headers=(
  -H "Content-Type: application/json"
  -H "X-API-Key: $OPENVIKING_API_KEY"
  -H "X-OpenViking-Actor-Peer: $OPENVIKING_AGENT"
)

if [ -n "${OPENVIKING_ACCOUNT_ID:-}" ]; then
  headers+=( -H "X-OpenViking-Account: $OPENVIKING_ACCOUNT_ID" )
fi
if [ -n "${OPENVIKING_USER_ID:-}" ]; then
  headers+=( -H "X-OpenViking-User: $OPENVIKING_USER_ID" )
fi

curl -sS "$OPENVIKING_BASE_URL/api/v1/search/find" \
  "${headers[@]}" \
  -d '{
    "query": "使用者問題關鍵詞",
    "target_uri": "viking://resources",
    "limit": 10,
    "score_threshold": 0.15
  }'
```

典型返回中需要關注：

```json
{
  "resources": [
    {
      "uri": "viking://resources/project-docs/api.md#chunk-3",
      "level": 2,
      "score": 0.71,
      "abstract": "命中的段落摘要",
      "category": "resource"
    }
  ],
  "memories": [],
  "skills": [],
  "total": 1
}
```

拿到 `uri` 後讀取完整內容：

```bash
curl -sS "$OPENVIKING_BASE_URL/api/v1/content/read?uri=$(python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=""))' 'viking://resources/project-docs/api.md#chunk-3')" \
  "${headers[@]}"
```

#### 10.4.5 Business Data Platform API 速查表

完整官方 API 清單、引數說明和外掛對映見 [6.2 Business Data Platform 官方 API 完整清單與外掛對映](#62-openviking-官方-api-完整清單與外掛對映)。本節只保留排查“召回了哪些資料 / 用了哪些文件”時最常用的呼叫。

| 目標 | API | 外掛入口 | 用途 |
| --- | --- | --- | --- |
| 健康檢查 | `GET /health` | `openclaw openviking status` | 判斷服務是否可達 |
| 身份/使用者探測 | `GET /api/v1/system/status` | `client.getRuntimeIdentity` | 解析服務端當前 user，輔助 canonical URI 展開 |
| 服務端上下文組裝 | `POST /api/v1/search/search` + `mode="context"` | auto recall | 結合 session 歷史返回 `entries`、`rendered` 和預算/去重統計 |
| 語義檢索 | `POST /api/v1/search/find` | `memory_recall` / `ov_search` | 返回 `memories[]`、`resources[]`、`skills[]`，每項含 `uri`、`score`、`abstract`、`level` |
| 內容讀取 | `GET /api/v1/content/read?uri=...` | `memory_recall` / `ov_read` / 手工排查 | 根據命中的 `viking://...` URI 讀取完整內容 |
| 寫入 session 訊息 | `POST /api/v1/sessions/{sessionId}/messages` | `afterTurn` | 儲存 OpenClaw 本輪 user/assistant/tool 片段 |
| 獲取 session 元資訊 | `GET /api/v1/sessions/{sessionId}` | `afterTurn` | 檢視 `pending_tokens`、message count、commit count |
| 獲取組裝上下文 | `GET /api/v1/sessions/{sessionId}/context?token_budget=...` | 主 assemble / compact | 獲取 archive summary + active messages |
| session commit | `POST /api/v1/sessions/{sessionId}/commit` | `afterTurn` / `compact` | 歸檔會話並觸發 Phase 2 記憶抽取 |
| 查詢非同步任務 | `GET /api/v1/tasks/{taskId}` | Phase 2 輪詢 | 檢視 memory extraction 是否完成、失敗或超時 |
| 展開 archive | `GET /api/v1/sessions/{sessionId}/archives/{archiveId}` | `ov_archive_expand` | 回看某個 archive 的原始訊息 |
| archive grep | `POST /api/v1/search/grep` | `ov_archive_search` | 在 session archive 原文中關鍵詞搜尋 |
| 上傳本地資源 | `POST /api/v1/resources/temp_upload` | `/add-resource`；`add_resource` 僅 opt-in | 本地檔案/目錄先臨時上傳，目錄會先 zip |
| 匯入 resource | `POST /api/v1/resources` | `/add-resource`；`add_resource` 僅 opt-in | 將文件、URL、目錄、倉庫匯入 `viking://resources` |
| 匯入 skill | `POST /api/v1/skills` | `add_skill` / `/add-skill` | 將 skill 寫入 `viking://user/skills` |
| 外接工具結果列表 | `GET /api/v1/sessions/{sessionId}/tool-results` | `openviking_tool_result_list` | 檢視當前 session 外接工具輸出 |
| 外接工具結果搜尋 | `GET /api/v1/sessions/{sessionId}/tool-results/{id}/search?q=...` | `openviking_tool_result_search` | 在大工具結果裡關鍵詞搜尋 |
| 外接工具結果讀取 | `GET /api/v1/sessions/{sessionId}/tool-results/{id}` | `openviking_tool_result_read` | 分頁讀取完整工具輸出 |

#### 10.4.6 判斷“用了哪些文件”的邊界

- 如果文件是通過 **auto recall** 進入模型上下文：看 `inject-detail` 中 `category=resource` 或 `uri` 以 `viking://resources` 開頭的條目。
- 如果文件是通過 **顯式工具** 進入模型上下文：看 `ov_search` 工具結果裡的 `uri` 和工具 `details.resources[]`。
- 如果自動召回只看到了 `context search POST` 但沒有 `injecting` / `inject-detail`：說明請求已發出，但服務端可能沒有返回可注入內容，或發生了超時/檢索錯誤；結合 warning、trace 和返回 stats 排查。
- 如果未顯式配置 `recallTargetTypes`，自動召回預設只查當前使用者及 actor scope 內的 memory，不會把 `viking://resources` 文件自動注入；resource-only 用 `recallTargetTypes=["resource"]`，預設記憶 + resources 用 `recallResources=true` 或 `recallTargetTypes=["user","agent","resource"]`。
- 如果沒查到 recall trace，先檢查 `traceRecall=true` 是否已配置並重啟 Gateway；`recallTargetTypes` / `recallResources` 不負責啟用 trace。
- 當前外掛沒有單獨生成“模型最終引用/採納哪些文件”的 citation 檔案；最可靠的依據是本輪注入內容、工具呼叫結果、Business Data Platform API 返回和模型回覆本身。

### 10.5 常見問題定位

| 現象 | 優先檢查 | 可能原因 |
| --- | --- | --- |
| 外掛未生效 | `plugins.slots.contextEngine` | slot 沒有指向 `openviking` 或被其他外掛覆蓋 |
| `setup` 成功但 gateway 中沒呼叫外掛 | `openclaw gateway restart` | Gateway 未重啟，仍用舊外掛狀態 |
| `status` 服務不可達 | `baseUrl`、`curl /health` | Business Data Platform 未啟動、埠/網路錯誤 |
| Root key 報 tenant 錯誤 | `accountId/userId` | Root key 需要顯式租戶上下文 |
| 不同 peer 記憶串用 | `logFindRequests` 中的 `X-OpenViking-Actor-Peer` | `peer_prefix` 或 session agent 解析不符合預期 |
| 搜不到剛儲存的記憶 | 服務端 task 狀態和日誌 | afterTurn commit 是非同步 Phase 2，記憶抽取可能還未完成或服務端失敗 |
| summary 有但細節沒有 | `ov_archive_search` / `ov_archive_expand` | Working Memory 是有損摘要，需要 archive 回查 |
| auto recall 沒注入 | `autoRecall`、precheck、閾值、預算 | Business Data Platform 不可達、query 太短、閾值太高、記憶超預算 |
| 工具結果缺完整內容 | tool result ref | 用 `openviking_tool_result_read`，不要反覆讀截斷 preview |
| 本地目錄匯入失敗 | 路徑、許可權、zip 打包日誌 | 目錄會先 zip 再 temp upload，需本地可讀 |

### 10.6 Business Data Platform 服務側排查

```bash
# 服務端日誌，路徑以實際部署為準
tail -f ~/.openviking/data/log/openviking.log

# Web Console
python -m openviking.console.bootstrap \
  --host 0.0.0.0 \
  --port 8020 \
  --openviking-url http://127.0.0.1:1933

# TUI
ov tui
```

---

## 11. 驗證與測試

### 11.1 倉庫本地驗證

```bash
npm install
npm run typecheck
npm test
npm run build
```

當前 `package.json` 中提供的指令碼：`build`、`test`、`typecheck`：`package.json:36`。

### 11.2 關鍵單測覆蓋方向

| 測試檔案 | 覆蓋重點 |
| --- | --- |
| `tests/ut/config.test.ts` | 配置預設值、環境變數、peer policy |
| `tests/ut/setup-command.test.ts` / `setup-cli.test.ts` | setup/status、slot 啟用、root key 探測 |
| `tests/ut/context-engine-*.test.ts` | assemble/afterTurn/compact、訊息合併、預算、工具配對 |
| `tests/ut/memory-ranking.test.ts` | 召回排序、去重、閾值 |
| `tests/ut/tools.test.ts` | 工具註冊、memory/resource/skill/tool-result 行為 |
| `tests/ut/tool-round-trip.test.ts` | toolCall/toolResult 往返與外接 ref 保留 |
| `tests/ut/manifest-contracts.test.ts` | manifest/package contract |
| `tests/ut/package-install-contract.test.ts` | 包安裝契約 |

### 11.3 外掛鏈路驗證

```bash
openclaw openviking status --json
openclaw config get plugins.slots.contextEngine
```

如果需要完整鏈路驗證，可以執行健康檢查指令碼：

```bash
python health_check_tools/ov-healthcheck.py
```

該指令碼用於注入真實對話，並在 Business Data Platform 側驗證會話捕獲、提交、歸檔和記憶抽取。說明見 `health_check_tools/HEALTHCHECK-ZH.md`。

### 11.4 手工端到端驗證建議

1. 安裝並配置外掛。
2. 開啟 `logFindRequests` 和 `emitStandardDiagnostics`。
3. 與 Agent 對話輸入一條明確偏好，例如“記住：我喜歡用中文回覆技術文件”。
4. 等待 afterTurn 或手動觸發 `/compact`。
5. 新開一輪問“我之前偏好什麼語言回覆技術文件？”。
6. 觀察最新 user message 是否注入 `<relevant-memories>`，或用 `memory_recall` 顯式查。
7. 用 Business Data Platform Console/TUI 檢查 `viking://user/.../memories` 是否產生 leaf memory。
8. 對長工具輸出場景，確認 preview 中有 `viking://session/.../tool-results/...`，再用 tool-result 工具讀取完整內容。

---

## 12. 注意事項

1. **外掛只支援 remote 模式**：舊 local mode 會被遷移提示，不會啟動本地 Business Data Platform 程序。
2. **必須重啟 Gateway**：安裝或配置後要 `openclaw gateway restart` 才能生效。
3. **不要裝錯包**：`@openviking/openclaw-plugin` 是外掛；`clawhub install openviking` 是 AgentSkill。
4. **API Key 不進日誌**：外掛路由日誌不會列印 key，但仍應避免把 key 寫入公開文件或命令歷史。
5. **Root Key 需要租戶上下文**：若服務端要求 account/user header，必須配置 `accountId` 和 `userId`。
6. **peer 配置要一致**：確認 `peer_role` / `peer_prefix` 與期望的 OpenClaw 會話身份一致，否則寫入和召回會落在不同 actor peer 視角。
7. **afterTurn commit 是非同步抽取**：立即返回不代表長期記憶已可檢索；看 task 或服務端日誌。
8. **compact 是同步邊界**：需要明確壓縮和抽取完成時用 compact，但它會阻塞等待服務端 Phase 2。
9. **記憶注入有預算**：`recallMaxInjectedChars` 會跳過放不下的完整記憶，而不是截斷。
10. **bypassSessionPatterns 會完全繞過 Business Data Platform**：匹配後自動捕獲、召回、工具都會跳過。
11. **tool result 工具限制當前 session**：外掛拒絕讀取其他 session 的外接結果。
12. **本地資源匯入先上傳**：本地檔案/目錄通過 temp upload，不把本地路徑直接交給服務端；目錄會 zip，注意許可權與體積。

---

## 13. 維護者程式碼閱讀路線

建議按以下順序閱讀：

1. `openclaw.plugin.json`：瞭解外掛宣告、工具 contract、配置 schema。
2. `package.json`：瞭解構建、OpenClaw 入口、相容版本。
3. `commands/setup.ts`：瞭解使用者安裝配置如何寫入 OpenClaw config。
4. `index.ts`：瞭解外掛註冊、工具、hook 和 service。
5. `client.ts`：瞭解 Business Data Platform API 封裝和 header/URI 處理。
6. `context-engine.ts`：理解 assemble/afterTurn/compact 主鏈路。
7. `auto-recall.ts` + `memory-ranking.ts`：理解召回注入和排序。
8. `text-utils.ts` + `session-transcript-repair.ts`：理解訊息清洗與 transcript 結構修復。
9. `tests/ut/*`：用測試反向確認 contract。

---

## 14. 快速排障 Checklist

- [ ] Business Data Platform Server `GET /health` 可達。
- [ ] `openclaw openviking status --json` 中 `configured=true`。
- [ ] `slotActive=true`。
- [ ] Gateway 已重啟。
- [ ] `plugins.entries.openviking.config.baseUrl` 指向正確服務。
- [ ] root key 場景已配置 `accountId/userId`。
- [ ] `X-OpenViking-Actor-Peer` 與預期 agent/session 一致。
- [ ] `autoCapture/autoRecall` 未被關閉。
- [ ] 當前 session 沒有命中 `bypassSessionPatterns`。
- [ ] `pending_tokens` 是否達到 `tokenBudget × commitTokenThresholdRatio`。
- [ ] Phase 2 task 是否 completed。
- [ ] 需要細節時是否使用 archive 工具回查。

---

## 15. 構建、測試、釋出、上線全流程

本章面向維護者和釋出同學，按“改程式碼 → 本地驗證 → 打包 → 釋出到 TOS → 安裝/灰度 → 上線驗證 → 回滾”的順序給出最短路徑。

### 15.1 本地開發準備

```bash
git clone <repo-url>
cd arkclaw-openviking-plugin
node -v        # 需要 Node.js >= 22
npm install
```

核心指令碼來自 `package.json`：

| 命令 | 作用 |
| --- | --- |
| `npm run typecheck` | 使用 `tsconfig.json` 做型別檢查 |
| `npm test` | 執行 Vitest 單測 |
| `npm run build` | 使用 `tsconfig.build.json` 生成 `dist/` |
| `bash build.sh` | 完整發布包構建：安裝依賴、型別檢查、單測、編譯、打 tgz、生成安裝指令碼 |

### 15.2 本地測試

最小程式碼質量檢查：

```bash
npm run typecheck
npm test
npm run build
```

完整發布前檢查：

```bash
bash build.sh
```

`build.sh` 會依次執行 `npm install`、`npm run typecheck`、`npm test`、`npm run build`，並要求存在 `dist/index.js`、`dist/commands/setup.js`、`openclaw.plugin.json`、`install-manifest.json`、`skills/` 和安裝指令碼：`build.sh:76`、`build.sh:82`、`build.sh:87`。

打包產物：

| 檔案 | 說明 |
| --- | --- |
| `output/openviking.tgz` | 外掛獨立安裝包 |
| `output/install.sh` | TOS / tarball / local 安裝指令碼 |
| `output/volcengine-install.sh` | 火山一鍵安裝指令碼 |

重要契約：構建包會在 staging package 中安裝生產依賴，並強校驗 `node_modules/@sinclair/typebox` 存在，避免 OpenClaw 執行時載入外掛失敗：`build.sh:114`、`build.sh:116`。

### 15.3 用本地包安裝驗證

```bash
bash build.sh

bash output/install.sh --source tarball --tarball output/openviking.tgz \
  --openviking-base-url http://127.0.0.1:1933 \
  --openviking-api-key <OPENVIKING_API_KEY> \
  --json
```

只想校驗包是否完整，不安裝：

```bash
bash output/install.sh --source tarball --tarball output/openviking.tgz --verify-only
```

安裝後檢查：

```bash
openclaw gateway restart
openclaw openviking status --json
openclaw config get plugins.entries.openviking.config
openclaw config get plugins.slots.contextEngine
```

### 15.4 Release 版本規則

釋出指令碼入口是 `scripts/release-to-tos.sh`。版本解析邏輯由 `scripts/resolve-release-version.mjs` 控制：

| 場景 | 版本結果 |
| --- | --- |
| 預設 beta 釋出 | 從 `package.json` 取基礎版本，例如 `2026.6.2`，在目標環境已有版本基礎上生成下一個 `2026.6.2-beta.N` |
| `--stable` | 釋出基礎版本本身，例如 `2026.6.2` |
| `--version <version>` | 完全使用顯式版本 |
| `--tag <tag>` | 顯式指定 Git tag；預設是 `v<resolved-version>` |

解析規則見 `scripts/resolve-release-version.mjs:28`、`scripts/resolve-release-version.mjs:38`、`scripts/resolve-release-version.mjs:56`。

### 15.5 Dry-run 釋出檢查

釋出前先 dry-run，確認版本、manifest、checksum、latest 指標內容：

```bash
scripts/release-to-tos.sh --env stg --dry-run

# 穩定版本 dry-run
scripts/release-to-tos.sh --env prod --stable --dry-run
```

dry-run 會真實執行 `build.sh` 並生成：

| 檔案 | 說明 |
| --- | --- |
| `output/manifest.json` | release 後設資料，包含環境、版本、Git hash、artifact 路徑和 SHA256 |
| `output/checksums.sha256` | artifact 校驗和 |
| `output/latest.json` | 當前環境 latest 指標候選內容 |
| `output/release-notes.md` | 未傳 `--notes` 時自動生成的 release notes |

dry-run 不上傳 TOS：`scripts/release-to-tos.sh:178`。

### 15.6 釋出到 TOS

非 dry-run 需要 TOS 憑證：

```bash
export TOS_ACCESS_KEY=<tos-access-key>
export TOS_SECRET_KEY=<tos-secret-key>

# 可選，預設如下
export TOS_BUCKET=arkclaw-openviking
export TOS_REGION=cn-beijing
export TOS_ENDPOINT=tos-cn-beijing.volces.com
```

釋出 beta 到 stg / ppe：

```bash
scripts/release-to-tos.sh --env stg --notes ./release-notes.md
scripts/release-to-tos.sh --env ppe --notes ./release-notes.md
```

釋出穩定版本到 prod：

```bash
scripts/release-to-tos.sh --env prod --stable --notes ./release-notes.md
```

指令碼會完成以下動作：

1. 校驗環境只能是 `stg|ppe|prod`。
2. prod 釋出要求 Git 工作區乾淨，防止髒程式碼上線：`scripts/release-to-tos.sh:106`。
3. 解析版本和 tag。
4. 用 `BUILD_VERSION=<version> bash build.sh` 構建包。
5. 生成 manifest / checksums / latest。
6. 上傳 `openviking.tgz`、`install.sh`、`manifest.json`、`checksums.sha256`、`release-notes.md`。
7. 下載遠端物件並校驗 SHA256。
8. 預設更新 `<env>/latest.json`；如傳 `--no-latest` 則只上傳不可變 release 物件，不切 latest。

TOS 物件不可變策略：release artifact、manifest、checksums、release notes 預設拒絕覆蓋；只有 `<env>/latest.json` 是可變指標：`scripts/tos-release-client.mjs:49`、`scripts/tos-release-client.mjs:65`、`scripts/tos-release-client.mjs:80`。

### 15.7 TOS 產物結構

釋出成功後，TOS 中的結構如下：

```text
<env>/latest.json
<env>/releases/<version>/openviking.tgz
<env>/releases/<version>/install.sh
<env>/releases/<version>/manifest.json
<env>/releases/<version>/checksums.sha256
<env>/releases/<version>/release-notes.md
```

`manifest.json` 中每個 artifact 都包含 `path`、`size`、`sha256`；安裝指令碼會讀取 manifest 中 `openviking.tgz` 的路徑和 SHA256 後下載校驗：`scripts/generate-release-manifest.mjs:73`、`scripts/install.sh:315`、`scripts/install.sh:318`。

### 15.8 灰度、上線與回滾

推薦釋出流：

1. **stg**：`scripts/release-to-tos.sh --env stg --dry-run`，確認產物；再去掉 `--dry-run` 釋出。
2. **stg 安裝驗證**：`bash install.sh --source tos --channel stg --latest --verify-only`，再真實安裝到測試 OpenClaw。
3. **ppe**：複用相同 release notes 釋出到 ppe，驗證安裝、setup、gateway、status、一次真實召回。
4. **prod dry-run**：確認 prod 穩定版本、manifest 和最新 Git hash。
5. **prod 釋出**：工作區乾淨後執行 `scripts/release-to-tos.sh --env prod --stable --notes ./release-notes.md`。
6. **線上驗證**：安裝 prod latest 或指定版本，檢查 `openclaw openviking status --json`、slot、Business Data Platform `/health`、一次 `memory_recall` 或 `ov_search`。

回滾方式：

```bash
# 客戶端回滾安裝指定版本
bash install.sh --source tos --channel prod --version <previous-version>

# 或使用別名
bash install.sh --source tos --channel prod --rollback-to <previous-version>
```

如果只想釋出某版本但不更新 latest 指標：

```bash
scripts/release-to-tos.sh --env prod --stable --no-latest --notes ./release-notes.md
```

這種方式適合先上傳不可變產物，待外部審批通過後再單獨更新 latest 指標。

### 15.9 上線後 Debug Checklist

```bash
openclaw openviking status --json
openclaw config get plugins.entries.openviking.config
openclaw config get plugins.slots.contextEngine
curl <OPENVIKING_BASE_URL>/health
```

建議臨時開啟：

```bash
openclaw config set plugins.entries.openviking.config.logFindRequests true
openclaw config set plugins.entries.openviking.config.emitStandardDiagnostics true
openclaw gateway restart
```

如果排查“召回到底用了哪些結果”，再開啟 trace：

```bash
openclaw config set plugins.entries.openviking.config.traceRecall true
openclaw config set plugins.entries.openviking.config.traceRecallPersist true
openclaw gateway restart
```

然後使用 `ov_recall_trace` / `/ov-recall-trace` 查詢。注意：`traceRecall=true` 是 trace 總開關，配置召回範圍（如 `recallTargetTypes=["resource"]`）不會自動開啟 trace。

### 15.10 釋出失敗常見原因

| 現象 | 原因 | 處理 |
| --- | --- | --- |
| prod 釋出被拒絕 | Git 工作區不乾淨 | 提交或還原本地修改後重試 |
| 非 dry-run 提示 TOS 憑證缺失 | 沒有設定 `TOS_ACCESS_KEY` / `TOS_SECRET_KEY` | 匯出憑證後重試 |
| TOS 上傳拒絕覆蓋 | 同版本 release 物件已存在且不可變 | 換新版本；不要覆蓋已釋出物件 |
| 安裝包校驗失敗 | 下載的 `openviking.tgz` SHA256 與 manifest 不一致 | 停止安裝，檢查 TOS 物件和 CDN/代理快取 |
| OpenClaw 載入失敗並提示缺依賴 | 包內缺執行時依賴 | 重新運行當前 `build.sh`，確認包內有 `node_modules/@sinclair/typebox` |
| status 不健康 | Business Data Platform Server 不可達或 key/租戶錯誤 | 檢查 `baseUrl`、`apiKey`、`accountId`、`userId`、服務端 `/health` |

---

## 16. 參考文件

- `README_CN.md`：專案中文快速說明。
- `INSTALL-ZH.md`：安裝、升級、解除安裝指南。
- `INSTALL-AGENT.md`：Agent 自動安裝說明。
- `docs/workmemory-v2-design.md`：Working Memory v2 設計。
- `health_check_tools/HEALTHCHECK-ZH.md`：健康檢查指令碼說明。
