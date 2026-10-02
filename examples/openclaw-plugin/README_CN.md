# OpenViking for OpenClaw

將 [OpenViking](https://github.com/volcengine/OpenViking) 作為 OpenClaw 的遠端上下文引擎：會話歸檔、基於閾值或 `/compact` 的記憶抽取、自動召回、resource/skill 檢索、召回鏈路追蹤，以及大工具結果的引用式分頁讀取。

當前實現重點：

- **僅遠端模式**：外掛是已有 OpenViking 服務的 HTTP 客戶端，不會啟動本地 OpenViking server 程序。
- **生命週期整合**：`assemble` 重建壓縮會話歷史並注入相關記憶；`afterTurn` 增量寫入本輪訊息並按閾值非同步 commit；`compact` 執行阻塞 commit 和結果回讀。
- **匯入與檢索**：Agent 可匯入 resources 和 Agent Skills，檢索它們，並在召回中選擇 `resource`、`user`、`agent` 等目標。
- **可除錯性**：可選的 recall trace 可通過 `ov_recall_trace` 或 `/ov-recall-trace` 查詢；超大工具輸出會外接儲存，並可按 ref 列表、搜尋和讀取。

## 快速開始

```bash
openclaw plugins install clawhub:@openviking/openclaw-plugin
openclaw openviking setup --base-url http://my-server:1933 --api-key sk-xxx --json
openclaw gateway restart
openclaw openviking status --json
```

四步完成。`setup` 命令會自動啟用 context-engine slot 並驗證連線。

常用 setup 變體：

```bash
# 可選 agent 名稱空間字首
openclaw openviking setup --base-url http://my-server:1933 --api-key sk-xxx --peer-prefix openclaw-prod --json

# root/trusted key 部署，需要顯式租戶身份 header
openclaw openviking setup --base-url http://my-server:1933 --api-key root-xxx --account-id acc_123 --user-id user_456 --json

# 預設只召回 account 級共享知識資源
openclaw openviking setup --base-url http://my-server:1933 --api-key sk-xxx --recall-target-types resource --json
```

### 火山 OpenViking Service 一鍵接入

如果使用火山控制台託管的 OpenViking Service，可直接注入控制台提供的 server url 和 API Key：

```bash
OPENVIKING_BASE_URL="https://api.vikingdb.cn-beijing.volces.com/openviking" \
OPENVIKING_API_KEY="<your-openviking-service-api-key>" \
OPENVIKING_PEER_PREFIX="openclaw-prod" \
bash scripts/install.sh --json
```

指令碼預設從 TOS `prod/latest` 安裝外掛，並完成 `openviking.env` 寫入、`openclaw openviking setup`、Gateway 重啟和狀態驗證。安裝指令碼依賴 bash，請不要用 `sh` 執行；下載包場景可使用 `bash output/install.sh --source tarball --tarball output/openviking.tgz`。

### 或者直接讓 Agent 安裝

> 幫我安裝 OpenViking 遠端記憶外掛 @openviking/openclaw-plugin。我的伺服器地址是 `http://my-server:1933`，API key 是 `sk-xxx`。

Agent 會自動完成安裝 → 配置 → 重啟 → 驗證。詳見 [INSTALL-AGENT.md](./INSTALL-AGENT.md)。

## 工作原理

| 階段 | 行為 |
|------|------|
| **每輪對話後** (`afterTurn`) | 新訊息追加到 OpenViking session；commit/抽取由閾值觸發 |
| **明確要求記住** (`memory_store`) | 重要長期事實可立即寫入並提交 |
| **`/compact` 時** (`compact`) | 待提交 session 訊息被 commit 並抽取為長期記憶 |
| **回覆前** (`assemble`) | 自動檢索相關記憶並注入上下文 |

## 工具

安裝後，外掛預設為 Agent 提供以下工具：

| 工具 | 用途 |
|------|------|
| `memory_recall` | 在 `user`、`agent`、`resource` 目標中顯式語義召回 |
| `memory_store` | 立即持久化明確的長期事實 |
| `memory_forget` | 按精確 URI 刪除記憶，或搜尋並刪除唯一高置信匹配 |
| `ov_archive_search` | 對當前 session 已歸檔的原始對話訊息做關鍵詞 grep |
| `ov_archive_expand` | 按 archive ID 展開原始訊息 |
| `ov_recall_trace` | 檢視 auto-recall 和顯式 recall/search 記錄的召回鏈路 |
| `add_skill` | 將 `SKILL.md`、skill 目錄、原始 skill 內容或 MCP tool dict 匯入 `viking://user/<uid>/skills/...` |
| `ov_search` | 檢索已匯入的 resources 和 skills |
| `ov_read` | 讀取 `ov_search` / trace 返回的 `viking://...` OpenViking 虛擬 URI 完整內容 |
| `ov_multi_read` | 一次讀取多個精確 `viking://...` URI，適合同時讀取 overview 和同級切片 |
| `ov_list` | 在檢索後列出 OpenViking 目錄，補查同級切片和 `.overview.md` 檔案 |
| `openviking_tool_result_list` | 列出當前 session 中被外接的大工具輸出 |
| `openviking_tool_result_search` | 在外接工具輸出中按關鍵詞搜尋 |
| `openviking_tool_result_read` | 通過 `viking://session/.../tool-results/...` ref 分頁讀取外接工具輸出 |

外掛還提供手動 slash command：`/add-resource`、`/add-skill`、`/ov-search`、`/ov-recall-trace`。Agent 可見的 `add_resource` 工具預設停用（`enableAddResourceTool=false`），避免搜尋/檢索階段誤觸發資源匯入；如確實要允許 Agent 匯入資源，可顯式設定 `enableAddResourceTool=true`，否則使用手動 `/add-resource`。

## 資料流與隱私

- **傳送內容**：每輪 user/assistant 訊息文本（已剝離注入的記憶塊和後設資料噪音）。
- **傳送去向**：僅發往你配置的 OpenViking 服務（`baseUrl`）。外掛本身只與該服務通訊；服務端對 embedding、VLM 等模型的呼叫取決於服務端配置。
- **儲存位置**：所有資料儲存在你的 OpenViking 服務上，名稱空間包括 `viking://user/*`、`viking://session/*`、`viking://resources/*` 等。
- **API Key**：通過 `X-API-Key` header 傳送，不會被日誌記錄或轉發。
- **多租戶隔離**：支援 `accountId`、`userId`。可選的 `peer_role` / `peer_prefix` 控制是否把 OpenClaw 說話人寫入 OpenViking `peer_id`，並在資料面使用 `X-OpenViking-Actor-Peer`。

## 驗證

```bash
openclaw openviking status --json     # 一鍵健康檢查
openclaw config get plugins.slots.contextEngine  # 應輸出：openviking
```

## 文件

| 文件 | 說明 |
|------|------|
| [INSTALL-ZH.md](./INSTALL-ZH.md) | 完整安裝、升級、解除安裝指南 |
| [INSTALL.md](./INSTALL.md) | English install guide |
| [INSTALL-AGENT.md](./INSTALL-AGENT.md) | Agent 專用操作文件 |
| [docs/openviking-websocket-rpc-api.md](./docs/openviking-websocket-rpc-api.md) | 通過 OpenClaw Gateway WebSocket RPC 呼叫 OpenViking 工具 |

> **外掛 vs Skill**：本頁面是 `@openviking/openclaw-plugin`（context-engine 外掛）。**不要**使用 `clawhub install openviking`——那安裝的是另一個 AgentSkill。

---

<details>
<summary><b>技術細節（面向整合方和工程師）</b></summary>

在 OpenClaw 中，此外掛註冊為 `openviking` 上下文引擎。

## 設計定位

- OpenClaw 仍然負責 agent runtime、prompt 編排和工具執行。
- OpenViking 負責長期記憶檢索、session 歸檔、archive summary 和記憶抽取。
- `examples/openclaw-plugin` 不是一個單一職責的"記憶查詢外掛"，而是一組圍繞 OpenClaw 生命週期工作的整合層。

按當前程式碼職責看，外掛同時扮演四個角色：

- `context-engine`：實現 `assemble`、`afterTurn`、`compact`
- Hook 層：接管 `session_start`、`session_end`、`before_reset`
- Tool 提供者：註冊 memory/archive 工具，以及 OpenViking resource 和 skill 匯入工具
- 執行時管理器：連線並監控遠端 OpenViking 服務

## 總體架構

![OpenClaw 與 OpenViking 外掛總體架構](./images/openclaw-plugin-engine-overview.png)

上圖對應的是當前實現裡的整體邊界：

- OpenClaw 在左側，仍然是主執行時；外掛並不接管 agent 執行本身。
- 外掛中間層把 Hook、Context Engine、Tools、Runtime Manager 四部分合並在一個註冊單元裡。
- 所有 HTTP 呼叫最終都走 `OpenVikingClient`，由 client 層統一補 `X-OpenViking-*` 頭和路由日誌。
- OpenViking 服務端承接 session、memory、archive 和 Phase 2 抽取，底層儲存落在 `viking://user/*`（包含 `viking://user/sessions/*`）、`viking://session/*` 和 `viking://resources/*`。

這套拆分的意義，是讓 OpenClaw 繼續專注推理與編排，讓 OpenViking 成為長期上下文的事實源。

## 身份與路由

外掛會把 OpenClaw 會話身份保留在 session 和 peer metadata 裡；OpenViking 的租戶身份仍然是 account/user 級，OpenClaw agent/sender 身份作為 peer 歸因和 actor-peer 資料面路由使用。

核心規則如下：

- `sessionId` 是 UUID 時直接複用。
- `sessionKey` 存在時優先用它生成穩定的 `ovSessionId`。
- 非安全路徑字元會被規整或退化成穩定的 SHA-256。
- `peer_role=none` 是預設值：訊息不寫 peer 歸因，記憶留在使用者共享空間，例如 `viking://user/alice/memories/...`；不使用具體 peer 的記憶子樹。
- `peer_role=assistant` 會讓 assistant message 寫入 `peer_id=<sessionAgent>`，並使用例如 `viking://user/alice/peers/main/memories/...` 的 peer 記憶；如果配置了 `peer_prefix`，peer id 為 `<peer_prefix>_<sessionAgent>`。
- `peer_role=sender` 會讓 user message 用 OpenClaw sender 身份派生 `peer_id`，並使用例如 `viking://user/support-agent/peers/customer-42/memories/...` 的 peer 記憶；assistant message 不寫 `peer_id`。
- `person` 仍作為 `sender` 的舊配置別名被相容；新配置和文件統一使用 `sender`。
- 資料面的 recall/search/read/import/delete 會在 `peer_role=assistant` 或 `peer_role=sender` 時把同一個解析後的 peer 身份作為 `X-OpenViking-Actor-Peer` 傳送。
- OpenClaw 沒有提供 session agent 時，使用其預設 agent `main` 作為本地 session 和 assistant peer metadata。
- 只有顯式配置了 `accountId` / `userId` 時才傳送 `X-OpenViking-Account` / `X-OpenViking-User`。

這樣做是因為 OpenViking 的租戶身份是 account/user 級，OpenClaw agent 身份只作為執行時 metadata 使用。

選擇 scope 時，先看 `viking://user/<user_id>` 代表誰：

| 模型 | 案例 | 結果 |
| --- | --- | --- |
| 通用／共享（`none`） | `user_id=alice` 使用任意 OpenClaw 助手 | 共享使用者記憶位於 `viking://user/alice/memories/...` |
| 人是 OpenViking user（`assistant`） | Alice 同時使用 `main` 和 `research` 兩個 OpenClaw 助手 | 助手 peer 記憶分別位於 `.../peers/main/memories/...` 和 `.../peers/research/memories/...` |
| Agent 是 OpenViking user（`sender`） | `user_id=support-agent` 接收 `customer-42` 和 `customer-99` 的訊息 | 傳送者 peer 記憶分別位於 `.../peers/customer-42/memories/...` 和 `.../peers/customer-99/memories/...` |

OpenViking 會把受管的 `peers/` 容器作為使用者 namespace 的一部分初始化。`none` 表示外掛不建立、也不路由到具體的 `peers/<peer_id>/memories` 子樹。使用 `assistant` 或 `sender` 時，actor-peer 召回同時包含使用者共享記憶和當前 peer 記憶；切換配置不會搬遷已有記憶。

預設推薦的遠端模式配置只有：

- `baseUrl`
- `apiKey`
- 可選 `peer_role`
- `peer_role=assistant` 時可選 `peer_prefix`

其中：

- `apiKey` 推薦使用某個 user 的 user key
- 新安裝預設 `peer_role=none`
- `accountId` / `userId` 僅在部署需要顯式身份 header 時作為進階選項使用，例如 root key 或 trusted server 流程

### User namespace

外掛通過 `viking://user/...` 寫入和檢索 user-scoped memory；OpenViking 會根據請求裡的租戶身份和 actor peer context 解析這個別名。legacy agent URI namespace 已由 OpenViking 廢棄，外掛不再使用。

## assemble 召回鏈路

![Prompt 前的自動召回流程](./images/openclaw-plugin-recall-flow.png)

自動召回現在由 `assemble()` 承接。OpenClaw 會在同一個 context engine 上呼叫兩次 `assemble()`，外掛按呼叫形態區分職責：

1. preflight assemble：呼叫引數裡帶 `prompt`，`messages` 還是舊歷史；外掛從 OpenViking 回讀 archive/session context 並重建歷史。
2. transformContext assemble：呼叫引數裡不帶 `prompt`，最後一條 `messages` 已經是本輪 user；外掛只做長期記憶召回，並把記憶塊 prepend 到這條 user message 的 content 開頭。

召回階段會：

1. 從最後一條 user message 提取查詢文本。
2. 基於當前 `sessionId/sessionKey` 解析本輪的 agent 路由。
3. 先做一次快速可用性檢查，避免在 OpenViking 不可用時拖慢模型請求。
4. 按配置的 `recallTargetTypes` 發起一次帶 session 上下文的 context search（預設 `user,agent`；可選 `resource`；原始 session 歷史仍可用 `ov_archive_search` 和 `ov_archive_expand` 檢視）。
5. 由 OpenViking 服務端結合 session 歷史擴充查詢，完成候選過濾與排序、跨輪去重、內容層級選擇和預算內組裝。
6. 把服務端渲染的上下文以 `<relevant-memories>` 形式 prepend 到當前 user message；不會追加獨立 synthetic user message。

## Session 生命週期

![Session 生命週期與壓縮邊界](./images/openclaw-plugin-session-lifecycle.png)

Session 是這套設計的主軸。當前實現裡，它覆蓋了"歷史組裝、增量寫入、非同步提交、阻塞壓縮回讀"四個動作。

### `assemble()` 負責什麼

preflight 階段的 `assemble()` 並不是簡單地把舊聊天記錄塞回來，而是按 token budget 從 OpenViking 回讀當前 session context，然後重新組裝成 OpenClaw 可消費的訊息：

- `latest_archive_overview` 被改寫成 `[Session History Summary]`
- `pre_archive_abstracts` 被改寫成 `[Archive Index]`
- 當前活躍訊息保持 message block 形式回放
- assistant 的 tool part 會被還原成 `toolCall`（輸入相容 `toolUse`/`input`，輸出統一規範為 `toolCall`/`arguments`）
- tool output 會被拆成獨立的 `toolResult`
- 之後再做一輪 `toolCall/toolResult` 配對修復，降低 transcript 結構不穩定的風險

因此，OpenClaw 拿到的是"壓縮後的歷史摘要 + archive 索引 + 當前活躍訊息"，而不是無限增長的原始 transcript。

### `afterTurn()` 負責什麼

`afterTurn()` 的職責更窄，專門處理本輪增量寫入：

- 只切出本輪新增訊息，不重寫整段對話
- 只保留 `user` / `assistant` 相關文本內容
- 會把 `toolCall` / `toolResult` 格式化進 capture 文本
- 會先剝掉注入過的 `<relevant-memories>` 和後設資料噪音
- 最終把清洗後的增量內容追加到 OpenViking session

之後外掛會讀取 session 的 `pending_tokens`。當它達到「模型上下文視窗（`tokenBudget`）× `commitTokenThresholdRatio`」時，會觸發一次 `commit(wait=false)`：

- archive 和 Phase 2 記憶抽取在服務端非同步繼續跑
- 當前 turn 不會因為等待抽取而阻塞
- 如果開啟 `logFindRequests`，日誌裡能看到 task id 和後續抽取結果

這條自動路徑是 best-effort，並且依賴 commit。短但重要的事實可能會先停留在 live session 裡，直到閾值 commit、`/compact` 或顯式儲存發生後，才進入長期記憶抽取流程。

自動 commit 預設保留最近 10 條訊息（`commitKeepRecentCount`），這個按條數切分的視窗可能從一輪對話中間開始。如果服務端支援按輪保留，可在外掛配置中設定 `"commitRetentionMode": "turn_budget"` 來啟用：

- 忽略 `commitKeepRecentCount`，採用服務端預設值：最多保留最近 3 輪使用者對話、12,000 Token 保留預算，以及至少最後一個 assistant/tool 步驟。
- 最新一輪過長時，服務端保留使用者問題與最近步驟，將更早的步驟歸檔並生成檢查點；必須保留的尾部可能超過保留預算。
- `pending_tokens` 只計算將離開活躍視窗的訊息，不重複計入歸檔與活躍視窗共有的使用者問題。

手動 commit 和 `/compact` 仍然全部歸檔。不設定該選項（或使用 `"message_count"`）即可保持原有行為。

### 顯式長期記憶寫入

當用戶明確要求 Agent “記住”“儲存”“存一下”某個重要長期事實、偏好、專案或決定時，應優先使用 `memory_store`，而不是等待普通 auto-capture 自然觸發。`memory_store` 會把文本寫入 OpenViking session 並呼叫 `commit(wait=true)`，因此是整合側讓重要事實儘快進入長期記憶的可靠路徑。

它是 auto-capture 的補充，不是替代：

- auto-capture 繼續負責普通對話流，並通過批處理平衡成本和延遲
- `memory_store` 面向明確的長期記憶意圖，例如“記住我的主專案是 X”或“儲存這個偏好”
- 如果 `memory_store` 已提交但抽取出 0 條記憶，應檢查 OpenViking 服務端抽取模型/配置；顯式路徑已經觸發抽取，但 extractor 沒有產出記憶

### `compact()` 負責什麼

`compact()` 走的是另一條更嚴格的同步邊界：

- 它呼叫 `commit(wait=true)`，阻塞等待 commit 完成
- 如果有 archive 生成，會再回讀 `latest_archive_overview`
- 返回新的 token 估算、latest archive id 和 summary
- 如果摘要不夠精確，模型可以再呼叫 `ov_archive_expand` 讀取某個 archive 的原始訊息

所以 `afterTurn()` 更像"增量寫入 + 條件觸發非同步提交"，而 `compact()` 才是"明確等待壓縮與歸檔完成"的正式邊界。

## 工具層與可展開能力

這套外掛除了自動行為，預設直接暴露 12 個工具；當 `enableAddResourceTool=true` 時才額外暴露 opt-in 的 `add_resource` 匯入工具。Agent 可見工具可以通過 `enabledTools` 和 `disabledTools` 靈活裁剪：

- `memory_recall`：在 memory/resource 目標上顯式語義召回
- `memory_store`：把明確的長期事實寫入 OpenViking session 並觸發阻塞 commit/抽取
- `memory_forget`：按 URI 刪除，或先搜尋再刪除唯一高置信候選
- `ov_archive_search`：按關鍵詞 grep 已歸檔的原始對話訊息
- `ov_archive_expand`：展開某個 archive 的原始訊息
- `ov_recall_trace`：查詢 auto-recall 和顯式 recall/search 呼叫的召回鏈路記錄
- `add_skill`：匯入或註冊 OpenViking agent skill
- `ov_search`：檢索 OpenViking resources 和 skills，尤其用於匯入後的確認和消費
- `ov_read`：讀取 `ov_search` 或 recall trace 返回的 `viking://...` OpenViking 虛擬 URI 完整內容
- `ov_multi_read`：讀取多個精確 `viking://...` URI，適合同時讀取 overview 和同級切片
- `ov_list`：在 `ov_search` 命中後列出父目錄，用來補齊同級切片、`.overview.md` 和同源文件上下文
- `openviking_tool_result_list`：列出當前 session 中被外接的大工具輸出
- `openviking_tool_result_search`：在外接工具輸出中按關鍵詞搜尋
- `openviking_tool_result_read`：通過 ref 和 offset/limit 分頁讀取外接工具輸出

工具選擇器支援精確工具名，也支援分組：`default`、`all`、`memory`、`resource_query`、`import`、`recall_trace`、`archive`、`tool_result`。Experience 檢索使用 `resource_query` 分組或 `ov_search`、`ov_read` 等當前工具名。例如，停用記憶並只保留資源查詢工具：

```json
{
  "autoCapture": false,
  "autoRecall": false,
  "enabledTools": ["resource_query"]
}
```

如果希望保留預設工具集但移除記憶相關操作，可設定 `"disabledTools": ["memory"]`。`add_resource` 仍然是雙重 opt-in：必須同時被 `enabledTools` 選中並設定 `enableAddResourceTool=true` 才會註冊。

它們各自的作用不同：

- 自動 recall 解決"模型不知道該先查什麼"的預設場景。
- `memory_recall` 給模型一個顯式補查入口。
- `memory_store` 適合在使用者表達長期記憶意圖時，把明確的重要資訊立刻落入記憶管線。
- `ov_archive_search` 和 `ov_archive_expand` 負責在 summary 不夠細時回到 archive 級原文。
- `ov_recall_trace` 用來解釋某次召回/檢索為什麼命中或沒有命中某些內容。
- 手動 `/add-resource` 用於把文件、目錄、URL 或 Git 倉庫匯入為 resource；Agent 可見的 `add_resource` 是 opt-in 工具，不能在搜尋、檢索、URI 讀取或搜尋結果最佳化階段使用。
- `add_skill` 把 skill 匯入 OpenViking。
- `ov_search` 補齊匯入後的確認閉環；它返回的 `viking://...` 是 OpenViking 虛擬 URI，不是本地檔案路徑。
- `ov_read` 通過 OpenViking `/api/v1/content/read` 消費精確的 `viking://...` 命中 URI，避免模型把虛擬 URI 當成本地檔案路徑讀取。
- `ov_multi_read` 能一次讀取 overview 和多個同級切片，適合拆分文件需要補上下文的場景。
- `ov_list` 補齊 `ov_search` 的結構瀏覽能力，避免只拿到某個切片時遺漏同一目錄下的連續步驟。
- `openviking_tool_result_*` 避免超大外部工具輸出撐爆上下文，同時保留完整內容的可恢復能力。

其中 `ov_archive_expand` 是 `assemble()` 的重要補充，因為 `assemble()` 預設給的是壓縮後的索引和摘要，而不是完整歷史正文。

### Resource 與 Skill 匯入

Resource 和 skill 保持兩個入口，因為它們落在不同 OpenViking 名稱空間，並使用不同服務端 API：

- resource 走 `/api/v1/resources`，落到 `viking://resources/...`
- skill 走 `/api/v1/skills`，落到 `viking://user/<uid>/skills/...`

外掛也提供顯式 slash command，方便手動匯入：

```text
/add-resource ./README.md --to viking://resources/openviking-readme --wait
/add-skill ./skills/install-openviking-memory --wait
/ov-search "OpenViking install" --uri viking://resources/openviking-readme
/ov-search "memory install skill" --uri viking://~/skills
/ov-recall-trace --turn latest --include-content
```

Resource 匯入支援遠端 URL、Git URL、本地檔案、本地目錄和 zip。OpenViking 內建 parser 覆蓋常見文件和媒體型別，例如 Markdown、純文本、PDF、HTML、Word、PowerPoint、Excel、EPUB、圖片、音訊和影片。目錄匯入還支援常見程式碼、文件和配置副檔名，例如 `.py`、`.js`、`.ts`、`.go`、`.rs`、`.java`、`.cpp`、`.json`、`.yaml`、`.toml`、`.csv`、`.rst`、`.proto`、`.tf`、`.vue`。

出於 HTTP 安全邊界，外掛不會把本地檔案系統路徑直接傳送給 OpenViking 服務端。本地檔案和目錄會先通過 `/api/v1/resources/temp_upload` 上傳；目錄會先在本地使用純 JavaScript zip 實現打包後再上傳。

### Recall Trace 與工具結果引用

Recall trace 預設關閉。可通過外掛配置 `traceRecall`、`traceRecallPersist`、`traceRecallDir` 等開啟，然後使用 `ov_recall_trace` 或 `/ov-recall-trace` 查詢。持久化 trace 預設寫入 `~/.openclaw/openviking/recall-traces`，並可通過保留天數和查詢上限控制掃描範圍。

當 OpenViking 將超大工具輸出外接時，可見 preview 會包含 `viking://session/<session_id>/tool-results/<tool_result_id>` 引用。使用 `openviking_tool_result_list` 發現 ref，使用 `openviking_tool_result_search` 定位片段，再使用 `openviking_tool_result_read` 結合 `offset`/`limit` 讀取原始內容。

## 執行模式

![執行模式與路由解析](./images/openclaw-plugin-runtime-routing.png)

外掛僅以遠端模式執行，作為純 HTTP 客戶端：

- `baseUrl` 和可選 `apiKey` 由外掛配置提供
- 不會啟動或管理本地子程序
- session context、memory search/read、commit、archive expand 這些行為保持不變

OpenViking 服務需要獨立部署並執行，外掛才能連線到它。

## 與舊設計稿的關係

倉庫裡還有一份更偏"未來演進方向"的設計稿：`docs/design/openclaw-context-engine-refactor.md`。閱讀時需要區分兩者的口徑：

- 本文描述的是當前實現已經落地的行為。
- 舊設計稿討論的是"進一步把更多主鏈路遷入 context-engine 生命週期"的目標態。
- 當前版本里，自動 recall 的主入口已經遷到 `assemble()`：preflight 重建歷史，transformContext 注入長期記憶。
- 當前版本里，`afterTurn()` 已經負責增量寫入 OpenViking session，但它仍然依賴閾值觸發非同步 commit。
- 當前版本里，`compact()` 已經走 `commit(wait=true)`，但它的職責仍以"同步提交 + 結果回讀"為主，而不是承載一切上層編排。

這段區分很重要，否則很容易把未來設計誤讀成現狀。

## 運維與除錯入口

如果你要排查這套外掛，優先看這幾類入口：

### 檢視當前配置

```bash
openclaw openviking status --json
openclaw plugins list
openclaw config get plugins.entries.openviking.config
openclaw config get plugins.slots.contextEngine
```

### 看日誌

OpenClaw 外掛側日誌：

```bash
openclaw logs --follow
```

OpenViking 服務側日誌：

```bash
cat ~/.openviking/data/log/openviking.log
```

### Web Console

```bash
python -m openviking.console.bootstrap --host 0.0.0.0 --port 8020 --openviking-url http://127.0.0.1:1933
```

### `ov tui`

```bash
ov tui
```

### 常見排查點

| 現象 | 更可能的原因 | 優先檢查 |
| --- | --- | --- |
| `plugins.slots.contextEngine` 不是 `openviking` | 外掛槽位未設定或被其他外掛覆蓋 | `openclaw config get plugins.slots.contextEngine` |
| 無法連線 OpenViking 服務 | `baseUrl` 配置錯誤或服務未啟動 | 檢查 `baseUrl` 配置並手動測試連線 |
| recall 在不同 session 間不穩定 | 路由身份和預期不一致 | 開啟 `logFindRequests`，再看 `openclaw logs --follow` |
| 長對話後沒有持續抽取記憶 | `pending_tokens` 未過閾值，或服務端 Phase 2 失敗 | 檢查外掛配置和 `~/.openviking/data/log/openviking.log` |
| summary 太粗，不夠回答細節問題 | 你要的是 archive 級明細，不是摘要 | 用 `[Archive Index]` 裡的 ID 呼叫 `ov_archive_expand` |

---

安裝、升級、解除安裝請檢視 [INSTALL-ZH.md](./INSTALL-ZH.md)。

</details>
