<a id="agent-整合能力對照"></a>

# Agent 整合能力

本頁對比各 OpenViking Agent 整合安裝後的實際行為。依賴某個整合之前，可以先用本頁回答三個問題：

- Agent 能自己呼叫哪些 OpenViking 工具？
- 哪些事情不需要 Agent 請求就會發生：每次提問前的召回、會話開場注入的上下文、對話捕獲，以及把對話變成長期記憶的提交？
- Agent 退出、崩潰、壓縮上下文或連不上服務端時，哪些內容會保留，哪些會丟失？

安裝請從[選擇 Agent 接入方式](./01-overview.md)開始。下文的對比基於[原始碼依據](#原始碼依據)中列出的實現；一個整合能用哪些 MCP 工具，由所連的服務端決定。

## 兩類能力

**Agent 可呼叫的工具**由模型決定是否呼叫，例如 `search`、`read`、`remember`。模型不呼叫，就不會發生任何事。只接 MCP 時，只有這一類能力。

**自動生命週期行為**由宿主事件觸發，不需要模型請求，包括：提問到達模型前的召回、會話開場注入的 profile 和 skill 上下文、把每輪對話捕獲到 OpenViking 會話，以及提交。hook、外掛和原生擴充提供這類能力。

長期記憶只在**提交**（commit）之後才會從會話中抽取。已捕獲但未提交的訊息留在服務端會話裡，要等之後的某次提交才會變成記憶。[捕獲與提交](#捕獲與提交)說明每個整合何時提交，以及退出時可能留下什麼。

<a id="導讀"></a><a id="_1-能力總覽"></a><a id="_1-2-自動-hook-面-通過-harness-自動實現"></a><a id="_1-3-形態分組"></a>

## 一覽

### 可呼叫工具

“服務端 MCP 工具”指服務端 `tools/list` 返回的工具：當前服務端有 21 個，列在[服務端 MCP 工具](#服務端-mcp-工具)。

| 整合 | 接入方式 | Agent 可呼叫的工具 |
|---|---|---|
| [Claude Code](#claude-code) | 外掛：hook + MCP 代理 | 服務端 MCP 工具 |
| [Codex、TraeCode CLI 2.0](#codex-與-traecode-cli-2-0) | Codex 外掛：hook + MCP 代理 | 服務端 MCP 工具 |
| [Cursor](#cursor) | hook 與 MCP 配置，外加一條 rule | 服務端 MCP 工具 |
| [TRAE、TRAE CN](#trae-與-trae-cn) | hook 與 MCP 配置 | 服務端 MCP 工具 |
| [ZCode](#zcode) | hook 與 MCP 配置 | 服務端 MCP 工具 |
| [Kimi Code](#kimi-code) | Kimi Code 外掛：hook + MCP 代理 | 服務端 MCP 工具 |
| [OpenCode](#opencode) | npm 外掛，自動新增 MCP 條目 | 服務端 MCP 工具，名為 `openviking_<tool>` |
| [DSH](#dsh) | 同進程 Cordis 外掛 + MCP 代理 | 服務端 MCP 工具，名為 `mcp__openviking__<tool>` |
| [pi](#pi) | 原生擴充，內建 MCP 客戶端 | 服務端 MCP 工具；MCP 握手成功後註冊為 `openviking_<tool>` |
| [OpenClaw](#openclaw) | context-engine 外掛 | 15 個原生工具，預設啟用 14 個 |
| [Hermes](#hermes) | Hermes memory provider | 6 個原生 `viking_*` 工具 |
| [MCP 客戶端、Agent Plugins](#其他整合) | 僅 MCP | 服務端 MCP 工具 |
| [ov CLI](#ov-cli) | 命令列客戶端 | 每個操作都是顯式命令，不經過 Agent |

### 自動行為

| 整合 | 每次提問前召回 | 會話開場上下文 | 會話中的提交 | 正常退出時提交 | 宿主壓縮 |
|---|---|---|---|---|---|
| Claude Code | 是，帶會話 | profile、記憶索引、skill | 待提交 token 達到 20,000 | 是 | 先提交，再由宿主摘要 |
| Codex | 是，帶會話 | profile、記憶索引、skill | 待提交 token 達到 20,000 | Codex 0.145+；否則下次啟動時 | 先提交，再由宿主摘要 |
| TraeCode CLI 2.0 | 是，帶會話 | profile、記憶索引、skill | 待提交 token 達到 20,000 | 僅當版本帶 `SessionEnd`；否則下次啟動時 | 同 Codex |
| Cursor | 是，帶會話 | profile、記憶索引、skill | 每捕獲 8 條訊息 | 否 | 先提交，再由宿主摘要 |
| TRAE、TRAE CN | 是，帶會話 | profile、記憶索引、skill | 每輪 | 沒有退出事件；每輪已提交 | 沒有壓縮前事件 |
| ZCode | 是，帶會話 | profile、記憶索引、skill | 每輪 | 沒有退出事件；每輪已提交 | 沒有壓縮前事件 |
| Kimi Code | 是，帶會話 | profile、記憶索引、skill，在首次提問時 | 每捕獲 8 條訊息 | 僅當 `SessionEnd` 捕獲到新訊息 | 提交新捕獲的訊息 |
| OpenCode | 是，帶會話 | profile、記憶索引、skill、已索引的倉庫 | 空閒時，待提交 token 達到 20,000 | 是，在宿主的清理時限內 | 在壓縮前後提交 |
| DSH | 是，帶會話 | profile、記憶索引、skill，每個會話一次 | 待提交 token 達到 20,000 | 是，預算 3 秒 | 先提交，再由宿主摘要 |
| pi | 是，帶會話 | profile、記憶索引、skill，每輪 | takeover 開：約 30,000 token；關：20,000 | takeover 開：否；關：是 | takeover 替換 pi 的摘要 |
| OpenClaw | 是，帶會話 | profile，每輪 | token 預算的一半（預設 64,000） | 否 | 外掛接管壓縮 |
| Hermes（內建） | 是，帶會話，有回退路徑 | profile 與記憶清單 | 否；只在會話邊界 | 是，前提是待上傳內容在 10 秒內完成 | fork 型壓縮時提交 |
| ov CLI | 否 | 否 | 只有 `ov session commit` | 不適用 | 不適用 |

標為 **Hermes（內建）** 的行描述舊版 Hermes 中固定提交的內建 provider。
使用目錄外掛的版本會載入外部外掛，其不同的生命週期行為見 [Hermes](#hermes)。

表格說明：

- **帶會話的召回**會發送會話 ID，服務端藉助對話內容理解查詢。共享外掛的 context 模式還會擴寫查詢，並記錄最近注入過的記憶，避免重複注入。Hermes 用 list 模式，沒有注入臺帳。OpenClaw 用 context search 併發送會話 ID，但關閉去重，因為它注入的上下文每輪重建，不寫入歷史。請求路徑和回退見[召回請求如何到達服務端](#召回請求如何到達服務端)。
- **待提交 token** 是服務端統計的、已捕獲但未提交的訊息量。多數閾值是客戶端設定，見[各整合何時提交](#各整合何時提交)。
- **正常退出時提交**指整合會發出提交請求。網路錯誤、宿主的退出時限或程序被終止仍可能打斷它。Ctrl+C、訊號和崩潰見[退出時會發生什麼](#退出時會發生什麼)。

<a id="_1-1-主動工具面-agentic-呼叫能力"></a><a id="_2-公共能力核"></a>

## Agent 可呼叫的工具

<a id="_2-1-服務端-mcp-工具面"></a>

### 服務端 MCP 工具

所有基於 MCP 的整合都暴露同一組由服務端定義的工具，自己不維護工具目錄。本地代理（pi 則是內建 MCP 客戶端）讀取 `~/.openviking/ovcli.conf`，連線服務端的 `/mcp`，原樣轉發 `tools/list` 的結果。服務端升級可以直接增加工具，不需要外掛發版；客戶端重新連線後即可看到。各工具的引數見 [MCP 工具與協議](../guides/06-mcp-integration.md#可用的-mcp-工具)。

| 分組 | 工具 |
|---|---|
| 檢索與瀏覽 | `find`、`search`、`read`、`download`、`list`、`tree`、`grep`、`glob` |
| 寫入 | `remember`、`write`、`edit`、`add_resource`、`add_skill` |
| 刪除 | `forget` |
| 監聽資源 | `list_watches`、`cancel_watch`（商業版暫不支援） |
| 帳戶與許可權 | `list_users`、`list_groups`、`get_acl`、`set_acl` |
| 狀態 | `health` |

使用前需要了解的行為：

- **`remember`** 會建立一個名為 `mcp-store-<id>` 的一次性會話，寫入訊息後立即提交。它是唯一會提交的 MCP 工具。提交被接受後它立刻返回，結果裡帶後臺記憶提取任務的 `task_id`；提取過程再決定新建或更新哪些記憶。沒有任何 MCP 工具會提交 Agent 當前的對話，那是自動 hook 的工作。
- **`find` 與 `search`**：`find` 是不帶會話上下文的快速檢索。`search` 可以傳 `session_id`，並做意圖分析（`retrieval.enable_intent`，預設開啟）。`find` 傳 `context_type="skill"` 時，每個 skill 包只返回一條命中，指向它的 `SKILL.md`，範圍包括使用者自己的和帳戶共享的 skill。
- **`write` 與 `edit`** 只能寫 `viking://resources`、`viking://user` 和 `viking://agent`。新檔案的副檔名必須是 `.md`、`.txt`、`.json`、`.yaml`、`.yml`、`.toml`、`.py`、`.js` 或 `.ts`。使用者的 `skills/`、`peers/`、`privacy/` 和 `sessions/` 目錄只讀。寫入 `viking://agent/skills` 不會被拒絕，但會跳過 skill 安裝流程，skill 請用 `add_skill`。
- **`add_resource` 傳本地路徑**時返回一個簽名上傳 URL（預設 600 秒有效）。模型需要把檔案上傳到這個 URL，例如用一條 shell 命令；上傳後自動開始入庫。遠端 URL 會直接入庫。
- **`forget`** 刪除傳入的任意 URI，預設不遞迴。它不檢查 URI 是記憶、資源還是 skill，見[寫入與刪除限制](#寫入與刪除限制)。
- **Schema** 在服務端啟動時被展平，只接受 OpenAPI 3.0 子集的客戶端（如 Gemini）也能載入。校驗仍按原始簽名進行，例如 `read` 也接受單個字串。所有客戶端拿到的 schema 相同。
- **身份**的解析方式與 REST 請求相同，見[認證](../guides/04-authentication.md)。

各宿主的差異：

- **OpenCode** 給工具加 `openviking_` 字首；**DSH** 把工具命名為 `mcp__openviking__<tool>`。
- **DSH** 每個 DSH profile 只執行一個 MCP 代理，所以工具呼叫帶的是程序級 actor peer，`remember` 也不繫結 DSH 會話。召回、捕獲和提交仍按會話解析 peer。
- **pi** 只在以下條件都滿足時註冊工具：會話未被 bypass、健康檢查通過、OpenViking 會話存在、`/mcp` 握手返回了工具列表。握手失敗時，本次會話沒有 OpenViking 工具，但召回、同步和 takeover 照常進行，後續輪次會重試握手。`mcpEnabled: false` 會關閉這條橋接。root API key 訪問 `/mcp` 會得到 403，所以憑據鏈最終落到 `ov.conf` 的 `server.root_api_key` 時，會話裡沒有工具。
- **Codex** 只把 `.mcp.json` 的 `env_vars` 中列出的環境變數傳給 MCP 服務。

### OpenClaw 工具

OpenClaw 註冊自己的工具，不轉發 MCP 工具。

| 分組 | 工具 | 說明 |
|---|---|---|
| 記憶 | `memory_recall`、`memory_store`、`memory_forget` | `memory_recall` 檢索記憶；`memory_store` 通過臨時會話提交 |
| 資源與 skill | `ov_search`、`ov_read`、`ov_multi_read`、`ov_list`、`add_skill`、`add_resource` | `ov_search` 預設檢索資源和使用者的 skill。`add_resource` 預設關閉，還需要開啟 `enableAddResourceTool` |
| 會話歸檔 | `ov_archive_search`、`ov_archive_expand` | 檢索並展開已歸檔的歷史 |
| 大塊工具輸出 | `openviking_tool_result_read`、`openviking_tool_result_search`、`openviking_tool_result_list` | 讀取服務端單獨存放的工具輸出 |
| 診斷 | `ov_recall_trace` | 檢視自動召回是如何構建的 |

### Hermes 工具

Hermes 有 6 個工具：`viking_search`、`viking_read`、`viking_browse`、`viking_remember`、`viking_forget` 和 `viking_add_resource`，沒有 skill 工具。`viking_remember` 通過獨立會話提交一條事實，在抽取完成前就返回；抽取可能新增、合併或跳過這條事實。內建 provider 與外部外掛的區別見 [Hermes](#hermes)。

<a id="_3-5-寫入與刪除的型別邊界"></a><a id="_3-5-1-寫入邊界"></a><a id="_3-5-2-刪除邊界"></a>

### 寫入與刪除限制

無論刪除來自哪個工具或命令，服務端都做同樣的檢查：

- 呼叫方需要對該 URI 有 manage 許可權；正在被刪除的使用者會被拒絕。
- `viking://`、`viking://user` 和 `viking://agent` 不能刪除。刪除 `viking://resources` 或整個使用者根（如 `viking://user/<id>`）需要 ROOT 角色。非 root 呼叫方不能寫 `viking://temp` 根。
- 呼叫方的 actor-peer 檢視中不可見的 URI 會被拒絕。

這些檢查保護的是名稱空間，不區分內容型別。按型別的限制來自客戶端：

| 入口 | 能刪除 | 客戶端限制 |
|---|---|---|
| MCP `forget`（所有 MCP 整合，含 DSH 與 pi） | 傳入的任意 URI | 除非 `recursive=true`，否則不遞迴；不檢查型別或分數 |
| `ov rm` | 任意 URI | 不確認；`-r` 遞迴刪除 |
| `ov tui` 的 `d` 鍵 | 根目錄和 scope 目錄以外的任意 URI | 需要確認 |
| OpenClaw `memory_forget` | 只能刪記憶檔案 | URI 必須匹配使用者、peer 或 agent 的記憶路徑。按搜尋刪除時，只有唯一候選且分數不低於 0.85 才執行，否則列出候選。始終不遞迴 |
| Hermes `viking_forget` | 一個使用者記憶 `.md` 檔案 | 拒絕目錄、非 `.md` 檔案、自動生成的 `.abstract.md` 和 `.overview.md`，以及帶 query 或 fragment 的 URI |
| LangChain `viking_forget` | 任意 URI | 只在 `profile="admin"` 或 `allow_forget=True` 時提供；`recursive` 由模型決定 |
| Open WebUI | 無 | 沒有刪除工具 |

skill 走單獨的路徑。建立、安裝或替換 skill 用 MCP `add_skill` 工具、OpenClaw 的 `add_skill`、`ov add-skill` 或 `POST /api/v1/skills`；`add_resource` 拒絕 skill URI。刪除 skill 用 `ov skills remove` 或 `DELETE /api/v1/skills/{name}`。MCP `forget` 和 `ov rm` 也能刪掉 skill 目錄，但會留下該 skill 的 privacy 配置。見[技能](../api/04-skills.md)。

<a id="_3-維度詳解"></a><a id="_3-2-自動召回與注入"></a>

## 自動召回與會話開場上下文

<a id="_3-2-1-機制底座-一條共享管線-兩條服務端路徑"></a>

### 召回請求如何到達服務端

除 OpenClaw 和 Hermes 外，所有整合都使用共享外掛程式碼，最多依次嘗試三種請求：

1. **context 檢索**。`POST /api/v1/search/search`，帶 `mode: "context"`、`purpose: "coding"` 和會話 ID。預算、配額、查詢擴寫和摘要選項只在你配置後才傳送；否則使用服務端預設值，包括 1,600 token 的注入預算（`max_tokens`）。
2. **舊版 recall**。服務端版本較舊、拒絕 context 模式時，外掛在 `~/.openviking/state/context-face.json` 中記錄這一結果，有效 6 小時，並改調 `/api/v1/search/recall`。這個檔案由本機所有整合共享，一個整合的判斷對所有整合生效。
3. **普通 find**。最後一步，外掛對 `viking://~/memories` 和 `viking://~/skills` 執行 `find`，在本地排序，並按自己的 token 預算裝填。`recallTokenBudget`、`recallMaxContentChars` 和 `recallPreferAbstract` 只在這一步生效。

共享外掛的召回不包含資源；資源文件由模型自己呼叫 `search` 檢索。Hermes 開啟資源召回選項後可以包含資源。

服務端對會話 ID 有兩種處理方式：

- **context 模式**（context 檢索和舊版 recall）根據對話擴寫查詢，併為每個會話維護一份已注入記憶的臺帳。擴寫需要同時滿足：`retrieval.enable_intent` 開啟（預設開啟）、會話中已有訊息、存在歸檔概覽或當前訊息。原始查詢始終排第一，後面最多追加三條規劃出的查詢。
- **list 模式**（不傳 `mode` 時的預設值）由意圖分析替換查詢，原始查詢不一定保留，也不使用臺帳。Codex 的第二級回退、Hermes 的 `viking_search(mode="deep")` 以及 Hermes 召回的首選路徑都走這裡。它們會發送會話 ID，但得不到擴寫和去重。

跨輪去重（`dedup_turns`）：

- 服務端在 context 模式下的預設值是 **0**，即關閉。共享外掛傳送 5（`recallDedupTurns`）。直接呼叫 API 時必須自己傳送 `dedup_turns`，只帶會話 ID 不會開啟去重。
- 視窗按訊息條數計算，不按對話輪。同時捕獲使用者和助手訊息時，5 大約覆蓋兩輪。
- 關閉自動捕獲但開啟召回時，訊息數不會增長，已注入過的記憶會在整個會話裡一直被抑制。設定 `OPENVIKING_RECALL_DEDUP_TURNS=0` 可以關閉去重。

<a id="_3-2-2-判定矩陣"></a>

### 各整合的召回方式

下表是預設路徑。開啟[召回摘要](#召回摘要)後，請求會有變化。

| 整合 | 觸發時機 | 查詢內容 | 上下文放在哪裡 |
|---|---|---|---|
| Claude Code | 每次 `UserPromptSubmit` | 去掉首尾空白的提問 | `additionalContext` 中的 `<openviking-context>` |
| Codex、TraeCode CLI 2.0 | 每次 `UserPromptSubmit`；整個 hook 有 120 秒截止時間 | 提問 | `<openviking-context source="auto-recall">` |
| Cursor | `beforeSubmitPrompt` | 提問；500 ms 內的重複事件複用上次結果 | `additional_context` |
| TRAE、TRAE CN | `UserPromptSubmit` | 去掉之前注入塊的提問 | `additionalContext` |
| ZCode | `UserPromptSubmit` | 去掉三類注入塊（含 `<system-reminder>`）的提問 | `additionalContext`，嚴格 JSON |
| Kimi Code | `UserPromptSubmit` | 提問 | 純文本上下文，不是 JSON |
| OpenCode | v1：每次 `chat.message`；v2：每次提問 | 訊息的文本部分 | v1 在訊息前插入一個合成 part。v2 把結果存進訊息 metadata，每個模型 step 在該訊息前注入，不發新請求 |
| DSH | `agent/pre-step` | 本批認領的所有訊息，去掉自身注入的內容 | 追加為一條使用者訊息 |
| pi | 在 `before_agent_start` 排隊，在 `context` 事件中執行 | 提問 | 前置到最後一條真實使用者訊息，本輪提問拿到本輪的記憶 |
| OpenClaw | 上下文組裝時 | 傳入的提問，清洗後截到 4,000 字元 | `<relevant-memories>`，放在 system prompt 中，每輪重建。宿主不傳提問時前置到最後一條使用者訊息 |
| Hermes | 每次模型呼叫前 | 5 個字元及以上的使用者輸入，去掉 skill 腳手架 | `<memory-context>`，只追加到本次請求中的當前使用者訊息，不寫入儲存 |

<a id="_3-2-3-profile-開場注入"></a>

### 會話開場上下文

使用共享外掛程式碼的整合會在會話開始時注入一個 `<openviking-context>` 塊，包含使用者 profile（`viking://user/<space>/memories/profile.md`）、`preferences/` 和 `entities/` 記憶的索引，以及 `<available-skills>` skill 清單：

```text
<openviking-context source="startup">
<user-profile uri="viking://user/default/memories/profile.md">...</user-profile>
<available-memories>...</available-memories>
<available-skills>
  OpenViking skills (stored in OpenViking, not local files). Before following one, read <dir>/<name>/SKILL.md with the OpenViking read tool.
  viking://user/default/skills/
    - pr-review — Review a pull request against the team checklist.
  viking://agent/skills/
    - deploy-runbook — Shared deployment runbook for the payments service.
</available-skills>
</openviking-context>
```

各整合的注入時機：

| 整合 | 時機 |
|---|---|
| Claude Code | `SessionStart`，所有 source |
| Codex | `SessionStart` 的 startup、clear 和 resume |
| Cursor、TRAE、TRAE CN、ZCode | `SessionStart` |
| Kimi Code | 首次提問時；失敗後在後續提問中重試，直到成功 |
| OpenCode | 每個會話的第一條訊息；失敗後不重試，子代理會話跳過。已索引倉庫的列表同時進入 system prompt |
| DSH | 每個會話一次；壓縮後不再發送 |
| pi | 放在 system prompt 中，每輪重建 |
| OpenClaw | 放在 system prompt 中，每輪重建：`<user-profile>` 包含使用者的 profile，設定了 `peer_role` 時還包含當前 actor peer 的 profile。不注入記憶索引和 skill 清單 |
| Hermes | 用自己的讀取邏輯載入 profile 及 preferences、entities 清單，預設預算 6,000 token |

預算與限制：

- `profileTokenBudget`（預設 10,000 token）覆蓋 profile 和記憶索引，profile 佔一半。profile 超長時保留前 8 行和結尾；清單超長時以 `... +N more` 結尾。token 估算中，CJK 字元按 1.5 token 計，其他文本按每 4 個字元 1 token 計。
- `skillCatalogTokenBudget`（預設 1,200 token，`OPENVIKING_SKILL_CATALOG_TOKEN_BUDGET`）是 skill 清單的獨立預算。`skillCatalog`（`OPENVIKING_SKILL_CATALOG`）或把預算設為 0 都會關閉清單。
- 清單來自一次 `GET /api/v1/skills` 請求。使用者自己的 skill 排在前面，與使用者 skill 同名的帳戶 skill 不再列出。每條描述截到約 40 token。描述放不下時只列名稱；名稱也放不下時以 `... +N more` 結尾，或縮成一行數量。服務端沒有該介面時不注入清單。
- `sessionStartMaxBytes` 按 UTF-8 位元組限制整個塊：Claude Code 和 Codex 為 9,500，因為這兩個宿主會把超過約 10,000 字元的 hook 輸出存成檔案，只顯示預覽；ZCode 為 20,000，因為它會丟棄超過 32 KB 的輸出；其他整合不設上限。超出上限時，先去掉記憶索引，再去掉 skill 清單。

恢復會話時，部分整合還會注入上一次歸檔的摘要，預算 32,000 token：Claude Code 在 resume 和 compact 時，Codex 在本地會話已清空後的 resume 時，OpenCode 在會話開始時，pi 在 takeover 關閉時。Claude Code 和 Codex 遇到與本會話已注入內容相同的 profile 塊時會跳過。

<a id="_3-2-4-超時與預算鏈"></a>

### 超時與預算

服務端的查詢擴寫在 5 秒後停止（`retrieval.recall_intent_timeout_s`），摘要改寫在 30 秒後停止（`retrieval.recall_rewrite_timeout_s`）。共享外掛在開啟擴寫時把 context 請求超時提高到至少 15 秒，請求摘要時至少 45 秒，讓客戶端能等完服務端的每個階段。宿主的截止時間仍可能先結束 hook。修改這些值見[調整召回延遲](./19-recall-tuning.md#請求超時)。

| 整合 | 召回超時 |
|---|---|
| Claude Code | 15 秒，hook 上限 60 秒 |
| Codex | 整個 hook 120 秒截止，包括最長 110 秒的本地壓縮器 |
| Cursor、TRAE、TRAE CN、ZCode | 15 秒，宿主上限 20 秒 |
| OpenCode | 30 秒 |
| DSH | 10 秒，開啟查詢擴寫時至少 15 秒。召回會阻塞 pre-step |
| pi | 15 秒 |
| OpenClaw | context search 預設 15 秒（`autoRecallTimeoutMs`），之前有一次 500 ms 健康檢查 |
| Hermes | 總計 4 秒，單請求 3 秒；可配置 |

OpenClaw 和 Hermes 把注入的召回內容限制在 4,000 字元，放不下的條目整條跳過，不截斷。

<a id="_3-2-5-召回再摘要"></a>

### 召回摘要

召回摘要讓模型先把召回結果改寫成一份帶引用的簡短要點，再交給 Agent。

**服務端**。context 檢索接受 `rewrite`（`false`、`true` 或 `"auto"`，預設 `false`）和 `rewrite_max_bullets`（預設 6，範圍 1–20）。服務端使用 `query_planner` 模型；`rewrite=true` 且未配置 `query_planner` 時回退到主 `vlm`，`"auto"` 只在配置了 `query_planner` 時執行。摘要以 `OpenViking memory digest:` 開頭，每個要點一行 `- `。每個要點最多 500 字元，必須引用結果中的一個 `viking://` URI；沒有有效引用的要點會被丟棄。模型判斷沒有相關內容時，服務端返回 `stats.rewrite="no_relevant"` 和空塊，這一輪不記入去重臺帳。超過 30 秒時，服務端返回未改寫的塊。

**外掛**。`OPENVIKING_RECALL_COMPRESS` 或共享配置中的 `recallCompress` 選擇模式，`recallRewrite` 仍可作為別名使用。

| 模式 | 行為 |
| --- | --- |
| `off` | 不生成摘要 |
| `server` | 傳送 `rewrite: true`，優先使用服務端摘要 |
| `client` | 使用本地壓縮器；僅 Claude Code 和 Codex |
| `auto` | Claude Code 和 Codex 有本地壓縮器時使用它，否則傳送 `rewrite: "auto"`。其他整合傳送 `rewrite: "auto"` |

Claude Code 和 Codex 預設 `auto`，其他整合預設 `off`。支援服務端摘要的有 Claude Code、Codex、OpenCode、DSH、pi、Cursor、TRAE、TRAE CN、ZCode、OpenClaw 和 Hermes 外部外掛，且需要服務端支援 context-search rewrite。Hermes 內建 provider 不支援召回摘要。舊值 `1` 和 `0` 分別等同於 `auto` 和 `off`。`no_relevant` 結果會取消本輪注入，外掛不能回退到原始塊。

本地壓縮器：

- **Claude Code** 用 `claude --version` 檢測 `claude`（結果快取 7 天），執行 `claude -p --model sonnet --effort low --strict-mcp-config`。子程序超時預設 110 秒（`recallCompressTimeoutMs`），但 60 秒的提問 hook 可能更早結束它。少於 1,500 字元的輸入不壓縮。引用的 URI 按編輯距離匹配回真實的結果 URI，無法匹配的要點會被丟棄。失敗時注入本地格式化的結果，或注入渲染好的塊。
- **Codex** 從 `~/.codex/models_cache.json` 選擇模型（優先 `gpt-5.3-codex-spark`，其次低 effort 的 `gpt-5.6-luna`；快取 7 天），在只讀的臨時沙箱中執行 `codex exec`，預設超時 110 秒。執行失敗一次後，本地壓縮停用到下一次 `SessionStart`。輸出上限 4,000 字元；失敗時的回退方式與 Claude Code 相同。

這些設定只作用於自動召回。模型顯式呼叫 MCP `search` 時，使用它自己傳入的引數。舊服務端的回退和宿主時間預算見[共享外掛說明](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/README.md#cloud-recall-compression)和[調整召回延遲](./19-recall-tuning.md)。

<a id="_3-2-6-注入迴流防護"></a>

### 避免注入內容被重複捕獲

注入的上下文用固定標籤包裹，例如 `<openviking-context>`。捕獲時先去掉這些塊再發送，召回的記憶就不會被當成新對話再次儲存。共享捕獲程式碼還會去掉摘要塊、後設資料圍欄和時間戳字首。TRAE 和 ZCode 使用各自的清理函式，ZCode 的清理函式會去掉三類注入塊。OpenClaw 在捕獲一輪對話和構造下一次召回查詢時都會去掉 `<relevant-memories>`。Hermes 從捕獲批次中丟棄三個只讀工具的呼叫和結果，保留寫入類工具的呼叫。

<a id="_3-3-會話與-commit-生命週期"></a>

## 捕獲與提交

<a id="_2-3-服務端會話與-commit-語義"></a><a id="_3-3-1-機制底座"></a>

### 服務端會話與提交機制

- **會話隱式建立**。服務端收到某個會話的第一條訊息時建立該會話；帶該會話 ID 的第一次 context 模式召回也會建立。DSH 是唯一顯式建立會話的整合。
- **提交分兩個階段**。`POST /api/v1/sessions/{id}/commit` 在第一階段歸檔訊息後返回。響應中帶有第二階段（記憶抽取）的 `task_id`，抽取在後臺執行。提交請求成功不代表抽取已經完成。
- **`keep_recent_count`** 決定提交後會話中保留多少條最近的訊息。服務端預設 0，即全部歸檔。Claude Code、Codex、OpenCode、DSH、Cursor、TRAE、TRAE CN、ZCode 和 Hermes 傳送 0；pi 在 takeover 模式下發送最近 3 個使用者輪對應的確切訊息數，其他情況傳送 0；OpenClaw 在閾值提交時傳送 10，在 reset、`memory_store` 和壓縮時傳送 0。
- **服務端自動提交預設關閉**。`memory.session_auto_commit.enabled` 預設 `false`，關閉時空閒掃描器不會啟動。新會話仍可以從 `server.user_config_defaults.auto_commit_policy` 獲得策略，也可以通過 `POST /api/v1/sessions`、`PATCH /api/v1/sessions/{id}/config`、SDK，或 `ov session new --auto-commit-policy-json` 與 `ov session config set` 顯式設定。策略的預設值是：待提交 token 150,000（嚴格大於）、100 條訊息、86,400 秒空閒超時、`keep_recent_count` 0、無最小間隔。空閒超時還需要 `memory.session_auto_commit.enabled=true`。記憶外掛不傳送策略，所以沒有上述設定時，只有客戶端會提交。
- **批次寫入**。共享外掛每次 `POST /messages/batch` 最多傳送 100 條訊息，與服務端上限一致；批次介面返回 404 或 405 時改為逐條傳送。
- **大塊工具輸出單獨存放**。服務端把超過 20,000 字元的工具輸出移到單獨的記錄中，留下 `tool_output_ref`。外掛把自己的上限（`captureToolMaxChars`）提高到 1,000,000，只作為兜底。
- **部分寫入在後臺執行**。Claude Code、Codex 和 ZCode 預設把 `Stop` 的寫入交給一個分離的 worker（`OPENVIKING_WRITE_PATH_ASYNC`），宿主不用等待。worker 啟動後，關閉終端不影響它，但網路錯誤或程序被終止仍可能打斷它。開啟這項設定時，`Stop` 不再輸出 `appended N turn(s)` 提示。

<a id="_3-3-2-常規-commit-觸發條件"></a>

### 各整合何時提交

表中的閾值都在客戶端判斷；除非另有說明，讀取的是服務端的待提交 token 數。

| 整合 | 會話中 | 顯式操作或會話邊界 | 壓縮前後 |
|---|---|---|---|
| Claude Code | `Stop` 時待提交 token 達到 20,000 | `SessionEnd` 和 `SubagentStop` 總是提交；`SessionStart` 重放排隊的寫入 | `PreCompact` 總是同步提交 |
| Codex | `Stop` 時待提交 token 達到 20,000 | `SessionEnd`（Codex 0.145+）補齊漏掉的輪次，然後在分離的 worker 中提交。startup 或 clear 的 `SessionStart` 會提交已標記結束或空閒超過 30 分鐘的會話 | `PreCompact` 補齊後提交全部內容 |
| TraeCode CLI 2.0 | 同 Codex | 同 Codex；沒有 `SessionEnd` 時只有啟動時的掃描 | 同 Codex |
| Cursor | 距上次提交捕獲滿 8 條訊息時，在 `stop` 提交（`commitTurnThreshold`），本地計數 | `sessionEnd` 已註冊，但實際不會執行 | `preCompact` 總是提交 |
| TRAE、TRAE CN | 每個捕獲到內容的 `Stop` | 無 | 沒有壓縮前事件 |
| ZCode | 每個 `Stop`；漏掉的 `Stop` 對應的輪次，在下一個 `Stop` 從 rollout 檔案補齊 | 無 | 沒有壓縮前事件 |
| Kimi Code | 距上次提交捕獲滿 8 條訊息時，在 `Stop` 提交 | `SessionEnd` 和 `Interrupt` 捕獲到新訊息時提交 | `PreCompact` 捕獲到新訊息時提交 |
| OpenCode | v1 `session.idle`、v2 執行結束時：待提交 token 達到 20,000 | 刪除會話、v1 `session.error`、v1 dispose 和 v2 cleanup 強制提交 | v1 在壓縮前後各一次；v2 在壓縮結束後一次 |
| DSH | `turn/end` 時待提交 token 達到 20,000 | Cordis teardown 提交每個會話 | `compaction/start` 提交，跳過閾值檢查 |
| pi，takeover 開（預設） | 本地估算達到 30,000 token，且使用者輪多於 3 個 | `/viking commit` | `session_before_compact` |
| pi，takeover 關 | 每次同步後待提交 token 達到 20,000 | `session_shutdown` 和 `/viking commit` | `session_before_compact` |
| OpenClaw | 每輪結束後達到 `tokenBudget × commitTokenThresholdRatio`（預設 128,000 × 0.5） | `/new`、`/reset` 和 `memory_store` 提交併等待 | `compact()` 提交，並最多等待 5 分鐘完成抽取 |
| Hermes（內建） | 無 | 會話結束、會話切換（`/new`、`/resume`、`/branch`、fork 型壓縮）、gateway 快取驅逐，以及退出處理器；`/undo` 和原地壓縮不提交 | 只在 fork 型壓縮時 |
| ov CLI | 無 | `ov session commit`；`ov add-memory` 會建立、寫入並提交自己的會話 | 不適用 |

<a id="_3-3-3-關閉方式-×-harness-終局矩陣"></a>

### 退出時會發生什麼

“提交”指退出路徑會發出提交請求，“視情況”取決於最後一列的說明。已經寫入的訊息留在服務端會話中，由同一會話的下一次提交歸檔。本表假設服務端自動提交關閉。

| 整合 | 正常退出 | Ctrl+C | SIGTERM | 關閉終端或視窗 | `kill -9` 或崩潰 | 剩餘內容如何回收 |
|---|---|---|---|---|---|---|
| Claude Code | 提交 | 提交 | 提交 | 提交 | 否 | `SessionEnd` 把提交交給自成程序組的分離 worker，SIGHUP 不會終止它。否則等下次閾值、`/compact` 或 `SessionEnd` |
| Codex | 提交 | 視情況 | 否 | 否 | 否 | 連按兩次 Ctrl+C 屬於正常退出，會觸發 `SessionEnd`；只按一次不會。漏掉的內容在下一次 startup 或 clear 的 `SessionStart` 提交：結束標記還在就立即提交，否則等空閒 30 分鐘後提交 |
| TraeCode CLI 2.0 | 否，除非版本帶 `SessionEnd` | 否 | 否 | 否 | 否 | 下一次 `SessionStart` 的 30 分鐘空閒掃描 |
| Cursor | 否 | 否 | 否 | 否 | 否 | 關閉或切換對話不觸發任何事件。`sessionEnd` 只在關閉視窗時觸發，而此時宿主已停止執行 hook 命令。不足 8 條訊息閾值的部分要等同一會話的後續訊息 |
| TRAE、TRAE CN | 否 | 否 | 否 | 否 | 否 | 每個 `Stop` 已經提交，最多丟失正在進行的那一輪 |
| ZCode | 否 | 視情況 | 否 | 否 | 否 | 按 Ctrl+C 時如果該輪的 `Stop` 已觸發，分離的 worker 會寫完。每個 `Stop` 都提交，漏掉的輪次在下一個 `Stop` 補齊 |
| Kimi Code | 視情況 | 視情況 | 未驗證 | 未驗證 | 否 | `SessionEnd` 和 `Interrupt` 只在捕獲到新訊息時提交；已被 `Stop` 捕獲的尾部等待下一次提交 |
| OpenCode | 視情況 | 視情況 | 視情況 | 視情況 | 否 | v1 1.15.11+ 的 `dispose` 和 v2 cleanup 會提交所有會話，但宿主留給清理的時間有限，慢請求或會話較多時可能被截斷。v2 cleanup 還會在空閒 60 分鐘和外掛熱過載時執行 |
| DSH | 提交 | 提交 | 提交 | 否 | 否 | teardown 給每個會話一次 3 秒的提交，排在慢寫入之後，整體處於 5 秒的程序寬限期內。第二次 Ctrl+C 會強制退出，跳過提交。Web 形態下關閉瀏覽器標籤頁不會觸發 teardown |
| pi，takeover 開 | 否 | 否 | 否 | 否 | 否 | `session_shutdown` 儲存 takeover 狀態但不提交。等下次執行達到閾值，或執行 `/viking commit` |
| pi，takeover 關 | 提交 | 提交 | 提交 | 提交 | 否 | 失敗的提交進入離線佇列 |
| OpenClaw | 否 | 否 | 否 | 否 | 否 | `session_end` 處理器不提交。歸檔依賴 `/new`、`/reset` 和閾值 |
| Hermes（內建） | 視情況 | 視情況 | 視情況 | 視情況 | 否 | 退出處理器最多用 10 秒等待上傳完成，然後提交；上傳沒有完成就跳過提交，不提交半個會話。SIGTERM 和 SIGHUP 預設有 1.5 秒寬限期，Hermes 的退出看門狗可能中斷較慢的提交 |
| LangChain、Open WebUI、Agent Plugins、MCP 客戶端 | 否 | 否 | 否 | 否 | 否 | 沒有會話 hook。MCP 代理退出時傳送的 `DELETE /mcp` 只關閉協議會話。LangChain 依賴呼叫方的 `close()` |

這張表的實際含義：

- **正常退出時會提交**：Claude Code、Codex 0.145+、OpenCode、DSH、takeover 關閉的 pi，以及 Hermes。其他整合依賴最後一列的回收方式。
- **`kill -9` 之後沒有任何整合會提交**。已寫入的訊息保持未提交，直到該會話的下一次提交。帶空閒超時的服務端自動提交策略是唯一的服務端兜底，而外掛不會配置它。
- **TRAE、TRAE CN 和 ZCode** 的退出行為最簡單，因為每輪都提交；代價是每個 `Stop` 都要做一次完整的歸檔和抽取。

<a id="_3-3-4-pending-queue-離線補償對照"></a>

### 離線重試

| 整合 | 寫入失敗時 |
|---|---|
| Claude Code、Cursor、TRAE、TRAE CN、ZCode、Kimi Code、OpenCode、DSH、pi | 可重試的失敗進入 `~/.openviking/pending` 下的磁碟佇列，在會話開始時重放：每次最多 50 條，每條最多 3 次，保留 7 天。網路錯誤、408、429 和 5xx 可重試；其他 4xx（含 401 和 403）不入隊。某條訊息重放失敗時停止，以保證順序 |
| Codex、TraeCode CLI 2.0 | 新捕獲的內容不入隊。transcript 游標只越過服務端已接受的訊息，下次捕獲或啟動掃描會重發剩餘部分。`SessionStart` 仍會重放已排隊的條目 |
| OpenClaw | 沒有佇列，失敗的輪次不會重發 |
| Hermes（內建） | 上傳在程序內執行緒中執行，不從磁碟重放。`$HERMES_HOME/openviking/pending_sessions/` 下的待提交標記讓之後的啟動能提交已退出程序留下的會話（僅 POSIX） |
| LangChain | 提交失敗時在下一次 record 時重試，只儲存在記憶體中。部分寫入會丟擲 `OpenVikingPartialWriteError`，附帶計數，呼叫方可據此重試剩餘訊息 |
| 日誌匯入 | SQLite 游標庫在傳送前記錄每批資料。崩潰後，下次執行根據服務端的訊息數判斷這批資料是否已送達 |

<a id="_3-3-5-subagent-會話對照"></a>

### 子代理

| 整合 | 子代理處理 |
|---|---|
| Claude Code | 每個子代理有自己的會話 `cc-<id>__subagent-<agent_id>`。`SubagentStop` 傳送它的 transcript 並提交 |
| Codex、TraeCode CLI 2.0 | 子代理輸出併入主會話 |
| OpenCode | 子代理使用 `oc-<parent>__subagent-<child>` 會話。會話開場上下文對它們跳過，召回不跳過 |
| DSH | 每個子代理是單獨的 `dsh-<id>` 會話，與父會話沒有關聯，各自獲得會話開場上下文 |
| Hermes | 委派任務以 `skip_memory=True` 執行，子代理沒有 OpenViking 會話、召回或工具，輸出也不會被捕獲 |
| Cursor、TRAE、ZCode、Kimi Code、pi、OpenClaw | 沒有特殊處理。有獨立會話 ID 的子代理有自己的會話，否則訊息併入主會話。OpenClaw 可以用 `bypassSessionPatterns` 排除會話 |
| 日誌匯入 | Claude Code 介面卡跳過 sidechain 和 meta 記錄，子代理對話不會匯入 |

<a id="_3-4-壓縮-compaction-接管"></a><a id="_3-4-1-判定矩陣"></a>

## 宿主壓縮

宿主縮減上下文時，多數整合只確保被丟棄的訊息已經提交，摘要由宿主生成。pi 和 OpenClaw 可以用 OpenViking 的歸檔替換宿主的摘要。

| 整合 | 方式 | 壓縮前 | 壓縮後 |
|---|---|---|---|
| Claude Code | 宿主摘要 | `PreCompact` 同步提交；這是唯一不在後臺執行的寫入，因為宿主緊接著就會重寫 transcript | `source="compact"` 的 `SessionStart` 注入歸檔概覽和最多 5 條摘要 |
| Codex、TraeCode CLI 2.0 | 宿主摘要 | `PreCompact` 補齊未捕獲的輪次，提交全部內容，並開始一個新的 OpenViking 會話。補齊不完整時不提交，稍後重試 | resume 時注入歸檔摘要 |
| Cursor | 宿主摘要 | `preCompact` 提交 | 無 |
| TRAE、TRAE CN、ZCode | 宿主摘要 | 沒有壓縮前事件 | 無 |
| Kimi Code | 宿主摘要 | `PreCompact` 提交新捕獲的訊息 | 無 |
| OpenCode | 宿主摘要 | v1 重新整理並提交；v2 捕獲 transcript | v1 在 `session.compacted` 時再提交一次；v2 在 `session.compaction.ended` 後提交 |
| DSH | 宿主摘要 | `compaction/start` 無論 token 閾值如何都會提交。注入的上下文是一條使用者訊息，隨宿主壓縮一起縮減；profile 不再發送 | 無 |
| pi | takeover，預設開啟 | 提交併等待歸檔概覽 | 用概覽替換 pi 的摘要；失敗時 pi 照常壓縮 |
| OpenClaw | 外掛接管壓縮 | `compact()` 提交併等待 | 下一次上下文組裝從服務端重建歷史 |
| Hermes（內建） | 宿主摘要 | fork 型壓縮提交舊會話；原地壓縮不做任何處理 | 無 |

<a id="_3-4-2-pi-takeover"></a>

### pi takeover

- **改變了什麼**。pi 自己的歷史不會被修改。擴充改寫每次 `context` 事件中傳送的訊息：邊界之前的內容合併成一條合成使用者訊息 `[OpenViking Session Context]`，內容是截到 3,000 token 的歸檔概覽。它的時間戳取第一條保留訊息之前的時刻，讓發給 provider 的請求保持穩定，prompt 快取繼續生效。
- **何時執行**。由 token 壓力觸發，而不是 pi 的壓縮事件：約 30,000 token，保留最近 3 個使用者輪。提交時把這 3 輪對應的確切訊息數作為 `keep_recent_count` 傳送。
- **摘要來源**。該次提交產生的歸檔概覽，每 2 秒輪詢一次，最多 15 次。邊界作為 `ov-takeover` 條目存在 pi 的 branch 中，重啟後仍然有效。
- **何時回退**。指紋不匹配、歷史短於邊界或缺少概覽時，pi 使用完整歷史。如果概覽一直為空，邊界不移動，待提交計數歸零，重新累積後再試。
- **pi 自己的壓縮**。takeover 成功時，`session_before_compact` 把 OpenViking 摘要返回給 pi。沒有 `firstKeptEntryId` 時，pi 執行預設壓縮。

<a id="_3-4-3-openclaw-contextengine"></a>

### OpenClaw 上下文引擎

- OpenClaw 把外掛註冊為上下文引擎，並設定 `ownsCompaction: true`，宿主不再自己生成摘要。
- 上下文組裝分兩部分。`transformContext` 只新增召回，前面有五道 passthrough 檢查。主組裝呼叫 `getSessionContext(tokenBudget)`，用服務端的返回替換宿主的即時歷史，按四檔預算切分，前面有三道 passthrough 檢查和一個訊息清洗步驟。
- `compact()` 以 `keep_recent_count` 0 提交，每 500 ms 輪詢一次，最多 5 分鐘，然後把歸檔概覽作為摘要返回。
- `ingest()` 和 `ingestBatch()` 有意不做任何事；對話在每輪結束後捕獲。
- 存在歸檔時，system prompt 會加入一段簡短指引，要求模型在回答“沒有相關資訊”之前先重讀摘要，並用 `ov_archive_search` 至少嘗試兩組關鍵詞。

<a id="_3-4-4-pi-與-openclaw-接管方式對照"></a>

### pi 與 OpenClaw 接管對比

| | pi takeover | OpenClaw 上下文引擎 |
|---|---|---|
| 宿主契約 | 在 `context` 事件中改寫訊息 | 上下文引擎，`ownsCompaction: true` |
| 歷史來源 | pi 本地的 branch | 服務端的會話上下文 |
| 觸發 | 客戶端 token 閾值（30,000，保留最近 3 個使用者輪） | 宿主每次呼叫 assemble 或 compact |
| 結果 | 一條合成使用者訊息，最多 3,000 token | 重建的訊息列表，加上壓縮摘要 |
| 失敗時 | 完整歷史 | 宿主的即時訊息 |
| 召回 | 帶會話 ID 的 context 檢索 | 不帶會話 ID 的 `/find`，沒有擴寫和去重 |

<a id="_3-6-降級與容錯"></a><a id="_3-6-1-判定矩陣"></a>

## 服務端不可用時

召回出錯時，宿主可以在沒有注入記憶的情況下繼續。但請求仍可能讓提問一直等到請求結束或到達截止時間；出錯後能繼續，不代表不用等待。

| 整合 | 服務端不可達 | 快取的失敗狀態 | 等待與錯誤傳遞 |
|---|---|---|---|
| Claude Code | 每個 hook 捕獲錯誤並讓宿主繼續；會話開始時跳過佇列重放 | context 檢索標記 6 小時，本地 CLI 檢測 7 天，健康狀態 5 秒 | 召回等到請求結束或截止時間後再繼續。URI guard 的拒絕是有意設計，與召回失敗無關 |
| Codex、TraeCode CLI 2.0 | 每個 hook 捕獲錯誤，不做任何處理 | context 檢索標記；本地壓縮器失敗後停用到下次啟動 | 召回等到請求結束或截止時間，然後提問繼續 |
| Cursor、TRAE、TRAE CN、ZCode | 請求錯誤被吞掉，不注入任何內容。5 秒內拿不到鎖的 hook 靜默跳過 | 只有 context 檢索標記，所以每輪都要等滿 15 秒召回超時 | 每輪最多等到召回超時 |
| OpenCode | 召回、捕獲和清理的錯誤被捕獲並記錄日誌 | context 檢索標記；健康檢查不快取 | 召回會等待網路請求；清理也可能等到截止時間 |
| DSH | 外掛吞掉錯誤。會話初始化失敗不快取，所以每個 pre-step 會發兩次 5 秒的健康檢查 | context 檢索標記；使用者空間查詢結果在程序生命週期內快取 | pre-step 依次執行 profile 和召回，會話 flush 會阻塞 |
| pi | 啟動時健康檢查失敗則不註冊工具，之後的提問靜默重試。只有 MCP 握手失敗時，召回、同步和 takeover 不受影響；狀態列顯示 `tools ✗`，`/viking` 列印錯誤 | context 檢索標記。MCP 握手每輪重試一次，召回開始前可能用掉 5 秒的握手預算 | 召回等到請求結束或截止時間。不開 takeover 時 `session_shutdown` 最多等 30 秒；`turn_end` 遇到網路錯誤時每條訊息等 10 秒 |
| OpenClaw | 500 ms 健康檢查失敗時跳過召回 | 無；每輪一次健康檢查 | 只有 `memory_store` 的錯誤會返回給模型；`compact()` 最多可能等 5 分鐘 |
| Hermes（內建） | 失敗的連線在 30 秒內不重試，除非連線設定改變 | 記住失敗的設定 | 召回在 4 秒總預算內等待，然後不帶上下文繼續 |
| ov CLI | 多數命令以狀態碼 1 退出；表格模式的 `ov status` 和 `ov health` 即使不健康也退出 0 | 無 | 不適用 |

<a id="_3-6-2-通用超時"></a>

### 共享超時與鎖

共享外掛的 HTTP 超時為 15 秒（最小 1 秒）。MCP 代理請求 15 秒超時，退出時傳送的 `DELETE /mcp` 為 2 秒。跨程序鎖等待 5 秒，60 秒後視為過期；正在重放的佇列條目 10 分鐘後被回收。MCP 代理不處理 SIGHUP，關閉終端時不會發送 `DELETE /mcp`；服務端以無狀態方式執行 MCP，不會留下殘留狀態。

<a id="_3-1-接入形態、安裝與配置體系"></a><a id="_3-1-1-判定矩陣"></a>

## 安裝、會話與配置

從會話 ID 字首可以看出服務端上的會話由哪個整合寫入。

| 整合 | 安裝方式 | 會話 ID | 配置來源 |
|---|---|---|---|
| Claude Code | 統一安裝器（`--harness claude`）或外掛市場 | `cc-<session id>`；子代理 `cc-<id>__subagent-<agent_id>` | 共享配置，`plugin.claude_code` |
| Codex | 統一安裝器（`--harness codex`）或 `codex plugin marketplace add` | `cx-<id>`，由 Codex 會話推導 | 共享配置，`plugin.codex` |
| TraeCode CLI 2.0 | 統一安裝器（`--harness trae-cli`），對 `traecli` 執行 Codex 的安裝流程 | 同 Codex | 同 Codex |
| Cursor | 統一安裝器；寫入 `~/.cursor/hooks.json` 和 `mcp.json` | `cu-<conversation id>` | 共享配置，`plugin.cursor` |
| TRAE、TRAE CN | 統一安裝器；寫入 `~/.trae/` 或 `~/.trae-cn/` 下的 hook 與 MCP 檔案 | `tr-` 或 `trcn-` | 共享配置，`plugin.trae` 或 `plugin.trae_cn` |
| ZCode | 統一安裝器；合併進 `~/.zcode/cli/config.json` 並開啟 hook | `zc-<id>` | 共享配置，`plugin.zcode` |
| Kimi Code | 統一安裝器；Kimi Code 託管外掛 | `kc-<id>` | 共享配置，`plugin.kimicode` |
| OpenCode | 統一安裝器、npm（`@openviking/opencode-plugin`）或原始碼 | `oc-<id>`；子代理 `oc-<parent>__subagent-<child>` | 共享配置，`plugin.opencode` |
| DSH | 統一安裝器或 `dsh plugin add @openviking/dsh-memory-plugin` | `dsh-<id>` | 共享配置，`plugin.dsh`，然後是 Cordis patch |
| pi | 統一安裝器，裝入 pi 的擴充目錄 | `pi-<id>` | 共享配置，`plugin.pi` |
| OpenClaw | ClawHub、npm 安裝器或離線包；之後執行 `openclaw openviking setup` | 會話 UUID，或會話 key 的 SHA-256 | `openclaw.json` 和少量環境變數 |
| Hermes（內建） | 隨 Hermes 釋出；執行 `hermes memory setup openviking` | Hermes 自己的會話 ID | `.env`、關聯的 `ovcli.conf` 和 Hermes `config.yaml` |
| ov CLI | npm、`uv tool install`、cargo 或 GitHub Releases | 不管理 | `ovcli.conf` profile |

“共享配置”指[配置與工作區檔案](#配置與工作區檔案)中分層的外掛配置。

<a id="_3-1-2-統一安裝器"></a>

### 統一安裝器

`examples/memory-plugin-shared/install.sh` 安裝 Claude Code、Codex、TraeCode CLI 2.0、Cursor、TRAE、TRAE CN、ZCode、Kimi Code、OpenCode、pi 和 DSH。OpenClaw 和 Hermes 有各自的安裝渠道。需要知道的幾點：

- 不帶 `--harness` 時顯示多選選單。各外掛自帶的 setup 指令碼會替你傳入 `--harness`。通過 `curl` 管道執行時，從 `/dev/tty` 讀取輸入。
- 從文件站下載；在倉庫 checkout 中執行時，使用本地 checkout。
- hook 和 MCP 條目帶有 `OPENVIKING_INTEGRATION_ID` 標記，重新執行只替換自己的條目，不動其他工具的條目。每個被修改的檔案先備份為 `.bak`，再以 `0600` 許可權原子替換。
- 憑據步驟為本地服務端、OpenViking Service 或自定義 URL 寫入 `~/.openviking/ovcli.conf`。已有配置會先顯示當前值（API key 打碼），再讓你選擇保留或修改。
- `--uninstall` 支援 Cursor、TRAE、TRAE CN、ZCode 和 Kimi Code。其他整合通過宿主自己的外掛管理解除安裝。
- 需要 Node.js 18 或更高版本。

<a id="_3-1-3-憑據體系"></a>

### 憑據來源

一共有四套憑據體系，各自使用不同的變數名和請求頭。連線失敗時，先確認整合用的是哪一套。

| 使用方 | 服務端 URL | API key | 身份 | 認證頭 |
|---|---|---|---|---|
| 共享外掛程式碼：Claude Code、Codex、Cursor、TRAE、ZCode、Kimi Code、OpenCode、DSH、pi、Agent Plugins | `OPENVIKING_URL`，其次 `OPENVIKING_BASE_URL` | `OPENVIKING_BEARER_TOKEN`，其次 `OPENVIKING_API_KEY` | `OPENVIKING_ACCOUNT`、`OPENVIKING_USER`、`OPENVIKING_PEER_ID` | 只有 `Authorization: Bearer` |
| OpenClaw | `OPENVIKING_BASE_URL`，其次 `OPENVIKING_URL` | `OPENVIKING_API_KEY` 或 SecretRef | `OPENVIKING_ACCOUNT_ID`、`OPENVIKING_USER_ID` | `X-API-Key` |
| Hermes | `OPENVIKING_ENDPOINT` | `OPENVIKING_API_KEY` | `OPENVIKING_ACCOUNT`、`OPENVIKING_USER`、`OPENVIKING_AGENT` | 同時傳送 `X-API-Key` 和 `Bearer`。有 key 時不發租戶頭，服務端要求時補發並重試一次 |
| ov CLI | `ovcli.conf` | `ovcli.conf` | `--account`、`--user`、`--actor-peer-id` | `X-API-Key`；按 `auth_mode` 使用 Basic 或 Bearer。含兩個及以上點號的 key 也會以 Bearer 傳送 |

共享外掛程式碼的規則：

- `OPENVIKING_CREDENTIAL_SOURCE`（`env`、`cli` 或 `auto`，預設 `auto`）決定憑據來源。`auto` 下，環境中只要有任一憑據變數就以環境為準；只有一個都沒設、且 `ovcli.conf` 中有憑據時，外掛才改用該檔案。`env` 不讀任何檔案，URL 預設為 `http://127.0.0.1:1933`。
- hook 和 MCP 代理用同一個函式解析連線，且都不讀取工作目錄，所以從外掛目錄啟動的代理與 hook 連到同一個服務端，使用同一身份。
- `X-OpenViking-Account` 和 `X-OpenViking-User` 只在 trusted 模式下發送。使用 API key 時，服務端從 key 中讀取身份。

完整的解析順序見[客戶端配置欄位](../configuration/02-client.md#連線與鑑權)和[外掛開發指南](./18-plugin-development.md#_4-2-憑據不是普通-workspace-配置)。

<a id="_3-1-4-配置體系分層"></a>

### 配置與工作區檔案

基於共享外掛程式碼的整合按以下優先順序（從高到低）讀取行為配置：`OPENVIKING_*` 環境變數、每機工作區登錄檔、倉庫的 `.openviking/config.local.json` 和 `.openviking/config.json`、`ovcli.conf` 的 `plugin.<harness>`、`ovcli.conf` 的 `plugin`，以及 `ov.conf` 中舊的 harness 段。工作區檔案不能設定 URL、key 或其他憑據。見[外掛配置](../configuration/02-client.md#外掛配置)和[工作區配置](../configuration/02-client.md#工作區配置)。OpenClaw 讀取 `openclaw.json`，Hermes 讀取自己的 `.env` 和 `config.yaml`。

**工作區 peer**。這些整合預設用倉庫規範化後的 `origin` URL 推導一個 peer 來標記記憶，所以同一倉庫的所有 clone 共用一個 peer。不在倉庫中時不傳送 peer，記憶進入使用者自己的空間。可以用 `peer.source` 和 `.openviking/config.json` 修改，見[工作區 peer](../configuration/02-client.md#工作區-peer)。OpenClaw 根據 `peer_role` 和 `peer_prefix` 推導 peer；`peer_role=sender` 時，如果宿主沒有提供傳送者，工具呼叫會失敗。Hermes 預設不設助手 peer，除非由 `OPENVIKING_AGENT`、關聯的 OpenViking peer 或 YAML 的 `agent` 鍵設定。Agent Plugins 不傳送 peer。

只對部分整合生效的設定：

- `OPENVIKING_COMMIT_TURN_THRESHOLD`：Cursor 和 Kimi Code。TRAE、TRAE CN 和 ZCode 每輪都提交。
- `OPENVIKING_WRITE_PATH_ASYNC`：Claude Code、Codex 和 ZCode。
- `OPENVIKING_RECALL_COMPRESS=client`：Claude Code 和 Codex。`server` 和 `auto` 適用於[召回摘要](#召回摘要)中列出的所有整合。
- 工作區檔案、`ovcli.conf` 的 `plugin` 段、`OPENVIKING_RECALL_DEDUP_TURNS`、`OPENVIKING_RECALL_QUERY_EXPANSION`、`OPENVIKING_PEER_SOURCE` 和 skill 清單相關設定：所有基於共享外掛程式碼的整合，不包括 OpenClaw 和 Hermes。

<a id="_3-7-附加-ux-對照"></a>

## 其他宿主功能

| 整合 | 狀態列 | 命令 | 附帶的 skill | 配置嚮導 |
|---|---|---|---|---|
| Claude Code | 有 | `/openviking-memory:ov` 顯示服務端狀態、身份和注入內容的來源 | `openviking-memory`、`openviking-skills`、`ov-experience-memory`、`ov-memory-doctor` | 有 |
| Codex、TraeCode CLI 2.0 | 無 | 無 | 與 Claude Code 相同的四個 | 有 |
| Cursor | 無 | 無 | 一條常駐 rule，加上 `openviking-memory`、`openviking-skills`、`ov-experience-memory` | 安裝器選單 |
| TRAE、TRAE CN、ZCode | 無 | 無 | 無 | 安裝器選單 |
| OpenCode | 無 | 無 | 與 Cursor 相同的三個，僅在外掛註冊自己的 MCP 服務時提供 | 有 |
| DSH | 無 | 無 | 與 Cursor 相同的三個 | 無 |
| pi | 有 | `/viking`、`/viking commit` | 與 Cursor 相同的三個，`mcpEnabled` 為 `false` 時不提供 | 有 |
| OpenClaw | 無 | `/add-resource`、`/add-skill`、`/ov-search`、`/ov-query-config`、`/ov-recall-trace` | 三個外掛 skill | 有；檢查 key 的角色和版本相容性 |
| Hermes（內建） | 無 | 無 | 無 | 有；`hermes memory status` 列出環境變數覆蓋項 |
| ov CLI | 無 | CLI 本身 | 無 | `ov config` |

Claude Code、Codex、Cursor、TRAE、ZCode、Kimi Code、DSH 和 pi 還會安裝 **URI guard**：檔案工具的路徑是 `viking://` URI 時，呼叫會被拒絕，並提示改用 OpenViking 工具；shell 命令中包含這種 URI 時照常執行，但附帶一條提示。各宿主檢查哪些工具不同，見[各整合說明](#各整合說明)。

<a id="_4-harness-檔案卡"></a>

## 各整合說明

這裡只寫每個整合特有的內容，共享行為見上文各節。

### Claude Code

[Claude Code](./02-claude-code.md)。外掛市場外掛，包含 9 個 hook、一個 MCP 代理、一個斜槓命令、狀態列和 4 個 skill。

- 註冊的 hook 比其他整合都多：`SessionStart`、`UserPromptSubmit`、`PostToolUse:Read`（skill 經驗 hook，預設關閉）、作用於 Read、Glob、Grep、Edit、Write 和 Bash 的 `PreToolUse`（URI guard）、`Stop`、`PreCompact`、`SessionEnd`、`SubagentStart` 和 `SubagentStop`。
- 召回摘要預設通過本地 `claude -p` 生成，服務端摘要作為回退。
- 除 `kill -9` 外，所有退出方式都會發出提交。
- 捕獲游標儲存在 `/tmp` 下。系統清理後，整個會話會重新發送。
- 外掛自身的開關關閉時，URI guard 仍然執行。

<a id="codex"></a><a id="trae-cli-traecode-cli-2-0"></a>

### Codex 與 TraeCode CLI 2.0

[Codex](./04-codex.md)、[TRAE](./13-trae.md)。外掛市場外掛，包含 6 個 hook（`SessionStart`、`UserPromptSubmit`、`PreToolUse:Bash`、`Stop`、`SessionEnd`、`PreCompact`）、一個 MCP 代理，以及與 Claude Code 相同的 4 個 skill。

- `SessionEnd` 只在乾淨退出且 Codex 0.145 及以上時觸發。訊號、崩潰、舊版本和 `codex app-server` 延後的情況都交給啟動時的掃描，掃描使用 30 分鐘空閒超時。
- `Stop` 和 `SessionEnd` 在分離的 worker 中寫入。每個會話一把鎖，按順序處理 `Stop` worker、`PreCompact`、`SessionEnd` worker 和掃描。
- Codex 用 `apply_patch` 編輯檔案，它沒有路徑引數，所以 Bash 上的 URI guard 只附加提示，從不拒絕。
- Codex 為每個 hook 儲存信任記錄。升級新增 hook 後，需要在 `/hooks` 中批准新的 hook。
- TraeCode CLI 2.0（執行檔 `traecli`，配置 `~/.trae/traecli.toml`）是 Codex 系 CLI，安裝同一個外掛。只支援 2.0；早期面向 1.0 的獨立外掛已移除，`--harness trae-cli --uninstall` 仍可刪除舊安裝留下的副本。不帶 `SessionEnd` 的版本會忽略該 hook。

### Cursor

[Cursor](./12-cursor.md)。hook 與 MCP 配置，包含 6 個 hook（`sessionStart`、`beforeSubmitPrompt`、`beforeReadFile`、`stop`、`preCompact`、`sessionEnd`）、一條常駐 rule 和 3 個 skill。

- URI guard 只在 `beforeReadFile` 執行，不受外掛開關影響。shell 命令不檢查，升級會移除舊版本註冊的 `beforeShellExecution` 條目。
- 只捕獲文本，所以 `ov-experience-memory` 能檢索和應用 Experience，但無法把讀取關聯回所用的 Experience。
- `sessionEnd` 只在關閉視窗時觸發，此時 Cursor 已停止執行 hook 命令，因此實際不會提交。
- 服務端不可達時，每輪都要等滿 15 秒召回超時。

<a id="trae-trae-cn-ide-版"></a>

### TRAE 與 TRAE CN

[TRAE](./13-trae.md)。hook 與 MCP 配置，包含 4 個 hook：`SessionStart`、`UserPromptSubmit`、`PreToolUse` 和 `Stop`。MCP 服務名為 `openviking`。

- `PreToolUse` 拒絕對 `viking://` 路徑執行 Read、Glob 和 Grep；Bash 和 RunCommand 命令中包含這種路徑時附加提示。
- 每個有內容的 `Stop` 都會提交，退出時最多丟失正在進行的那一輪。
- TRAE 和 TRAE CN 只有會話字首和安裝路徑不同。同樣的工作在兩個客戶端中會產生不同的會話，要等抽取完成後才共享記憶。
- 不處理壓縮，沒有狀態列和 skill，也不單獨處理子代理。

### ZCode

[社群外掛：ZCode](./08-community-plugins.md#zcode-記憶整合)。hook 與 MCP 配置，包含 4 個 hook：`SessionStart`、`UserPromptSubmit`、作用於 Read、Glob 和 Grep 的 `PreToolUse`，以及 `Stop`。

- 捕獲的輪次來自 rollout 檔案 `~/.zcode/cli/rollout/model-io-<sid>.jsonl`；漏掉的 `Stop` 對應的輪次在下一個 `Stop` 補齊。
- 第一次捕獲讀取整個 rollout，所以在長時間執行的會話中安裝會產生一次大上傳。
- 捕獲只去掉注入塊，不做其他文本清理。
- `Stop` 預設在分離的 worker 中寫入。

<a id="kimicode"></a>

### Kimi Code

[社群外掛：Kimi Code](./08-community-plugins.md#kimi-code-記憶整合)。Kimi Code 託管外掛，包含 7 個 hook（`SessionStart`、`UserPromptSubmit`、作用於 Read、Glob 和 Grep 的 `PreToolUse`、`Stop`、`PreCompact`、`SessionEnd`、`Interrupt`）和一個 MCP 代理。安裝器在 `$KIMI_CODE_HOME/plugins/managed/openviking-memory` 下構建一份自包含的副本。

- 捕獲的輪次來自 `wire.jsonl`。一輪對話只有在傳送成功或存入離線佇列後才會推進游標。
- 會話開場上下文在首次提問時注入，失敗後在後續提問中重試，直到成功。
- `Stop`、`PreCompact` 和 `SessionEnd` 可以在後臺寫入。`Interrupt` 保持同步，請求預算 2 秒。
- `UserPromptSubmit` 返回純文本上下文，不是 JSON。
- 安裝時保留其他外掛記錄，不修改舊的 `config.toml` 或 `mcp.json`。

### OpenCode

[OpenCode](./10-opencode.md)。npm 外掛 `@openviking/opencode-plugin` 用同一個入口支援 OpenCode v1（1.15.7 及以上）和 v2（2.0.15 及以上）。

- v2 每次提問只召回一次，把結果存進使用者訊息的 metadata；後續模型 step 直接複用，不發新請求，prompt 快取因此保持穩定。每次執行結束時，v2 讀取完整的使用者、助手和工具訊息用於捕獲。
- v2 在每次執行結束後檢查提交閾值，包括失敗和被中斷的執行，這些執行會保留狀態。v2 只處理本 location 的會話，游標存在外掛 storage 中。v2 沒有 toast API，改為寫日誌。
- MCP 工具保留 `openviking_` 字首；v2 設定 `codemode: false`。3 個 skill 只在外掛註冊自己的 MCP 服務時加入，hook-only 模式或關閉 `mcp.openviking` 時不加入。
- 提交超時 30 秒。

<a id="dsh-deepseek-harness"></a>

### DSH

[DeepSeek Harness](./17-dsh.md)。唯一的同進程 Cordis 外掛。hook 直接呼叫 REST API；工具通過 `@deepseek-ai/dsh-mcp-client` 和共享的 stdio 代理接入。

- 監聽 `agent/session-start`、`agent/pre-step`、`session/event`、`session/flush`、`tools/pre-execute` 和 `tools/post-execute`。
- `ctx.provide("openvikingMemory")` 讓其他 Cordis 外掛可以在它之上構建功能。
- 安裝器預設使用 `web` profile，可以用 `--dsh-profile` 指定其他 profile。除 `dev` 外的所有模式都安裝已釋出的 npm 包。
- 預設捕獲工具結果（`captureToolResults: true`），所以 `ov-experience-memory` 能完整執行；關閉捕獲後，只能檢索和應用 Experience。
- URI guard 先把工具名轉成小寫，在 `tools/pre-execute` 拒絕對 `viking://` 路徑的檔案工具呼叫，在 `tools/post-execute` 為包含這種路徑的 `bash` 命令附加提示。
- Cordis patch 中寫明的憑據優先於其他所有來源；對行為配置來說，patch 是優先順序最低的一層。

<a id="pi-pi-coding-agent-extension"></a>

### pi

[pi](./11-pi.md)。原生擴充，包含 9 個事件處理器和 `/viking` 命令。召回、同步、會話開場上下文和 takeover 使用 REST；工具使用 pi 內建的 MCP 客戶端。

- 工具就是服務端 `tools/list` 返回的內容，重新命名為 `openviking_<tool>`。服務端增刪工具後，pi 在下一個會話生效，不需要擴充發版。
- 從 0.3.x 升級時，所有工具都從 `viking_*` 改了名，沒有別名過渡期。請更新 `--tools` 或 `--exclude-tools` 列表，否則工具會靜默消失。
- `openviking_read` 返回檔案內容，支援 `offset` 和 `limit`。目錄 URI 會返回錯誤。舊的 `level="abstract"` 和 `"overview"` 讀取在 MCP 中沒有對應工具，可改用 `openviking_search(mode="context", detail="overview")` 或 `openviking_tree(include_abstract=true)`。
- 工具呼叫 15 秒超時（`OPENVIKING_TIMEOUT_MS`）。超時或按 ESC 只讓本地呼叫失敗，已發出的請求會繼續執行，寫入仍可能生效。
- `tool_call` 拒絕對 `viking://` 路徑執行 read、grep、find、ls、write 和 edit；`tool_result` 為包含這種路徑的 `bash` 輸出附加提示。
- takeover 關閉時，用 `pi -c` 恢復會話會重新發送整個 branch。
- bypass 使用 `bypassSessionPatterns`；舊的 `bypassPatterns` 仍然有效。

### OpenClaw

[OpenClaw](./03-openclaw.md)。接管壓縮的 context-engine 外掛，包含 15 個工具、5 個斜槓命令、生命週期 hook、Gateway HTTP 路由，以及受功能開關控制的 RPC 方法。

- `memory_recall` 檢索記憶，`ov_search` 檢索資源和使用者的 skill；通過顯式引數，兩個工具都能查另一類內容。
- 召回通過 `/find` 進行，不帶會話 ID，所以沒有查詢擴寫和去重，長會話中同一條記憶可能被重複注入。預設每條召回的記憶多一次 read（`recallPreferAbstract=false`）。
- 退出不提交。歸檔依賴 `/new`、`/reset` 和閾值。沒有離線佇列，失敗的輪次不會重發。
- `compact()` 最多可能阻塞 5 分鐘。
- 配置嚴格校驗：有未知鍵或非法值時，外掛進入 setup-only 模式。
- 提交閾值是 `tokenBudget`（預設 128,000）乘以 `commitTokenThresholdRatio`（預設 0.5）。

<a id="hermes-nous-research"></a>

### Hermes

[Hermes](./05-hermes.md)。Hermes 通過兩種分發方式提供名為 `openviking` 的
memory provider：

- **目錄外掛**在本倉庫的
  [`examples/hermes-plugin`](https://github.com/volcengine/OpenViking/tree/main/examples/hermes-plugin)
  中維護。先執行 `hermes plugins install openviking --enable`，再執行
  `hermes memory setup openviking`。
- **內建 provider** 存在於舊版 Hermes 的 `plugins/memory/openviking` 中，
  無需安裝。本頁的 Hermes 行描述
  [Hermes 提交 `989798c`](https://github.com/NousResearch/hermes-agent/tree/989798cd5e691230b54b2ea72e5937b68133014c/plugins/memory/openviking)
  時的內建 provider。

仍包含內建 provider 的版本會優先載入內建副本。當更新移除內建副本時，已配置
OpenViking 的 profile 會自動嘗試安裝目錄外掛。provider 名、配置和已存資料均保持不變。

兩者是獨立的程式碼庫。行為差異如下：

| | 內建 provider（Hermes `989798c`） | 外部外掛（本倉庫） |
|---|---|---|
| 會話中的提交 | 無，只在會話邊界 | 待提交 token 達到 20,000 時後臺提交（`commit_token_threshold`） |
| 召回摘要 | 不支援 | 可選的服務端摘要（`recall_compress`） |
| 映象 Hermes 內建記憶 | 只同步新增 | 同步新增、替換和刪除，用 URI 登錄檔跟蹤 |
| `viking_forget` | 帶明確使用者 ID 的使用者記憶檔案 | 還接受 `viking://~/`，拒絕不帶使用者 ID 的路徑，刪除前檢查歸屬 |
| cron、子代理和 flush 上下文 | 該提交中沒有說明 | 召回可用；跳過自動寫入和映象 |

上述固定提交中內建 provider 的行為：

- 每次模型呼叫前召回，走帶會話的 `search/search`，以 `/find` 作為回退。預設值：6 條結果、分數閾值 0.15、4,000 字元、總計 4 秒、單請求 3 秒。
- `viking_remember` 把事實原樣通過獨立會話傳送並提交，返回 `status: submitted`。
- 提交不保留訊息（`keep_recent_count` 0）。上傳不持久化，但在 POSIX 上，待提交標記讓之後的啟動能提交已退出程序留下的會話。
- 記憶寫入 `viking://user/<uid>/memories/`；設定了 peer 時寫入 `viking://user/<uid>/peers/<peer>/memories/`。
- 關聯 OpenViking 的 `ovcli.conf` profile 會清除 Hermes `.env` 中的 5 個連線變數。`hermes backup` 會包含 `$HOME` 下預設或由環境變數指定的 `ovcli.conf`；通過 YAML 關聯的檔案需要單獨備份。

<a id="_5-ov-cli-命令參考"></a><a id="_5-1-命令樹"></a><a id="_5-2-全域選項與獨有機制"></a><a id="_5-3-cli-獨有於外掛面的能力"></a>

### ov CLI

[安裝與使用 CLI](../getting-started/05-cli-setup.md)。`ov` 是 REST API 的 Rust 客戶端，沒有宿主事件、自動召回或壓縮處理；每個動作都是由你或指令碼執行的命令。執行 `ov --help` 檢視命令列表，JSON 輸出見 [CLI 輸出格式](../api/01-overview.md#cli-輸出格式)。

CLI 提供而外掛沒有的能力：多個 `ovcli.conf` profile、帳戶與使用者管理（`ov admin`）、用 `--sudo` 執行 root 操作、隱私策略管理（`ov privacy`）、快照、備份與恢復、匯出與匯入、`ov reindex`、在本地生成 root key（`ov system crypto init-key`）、`ov tui` 檔案瀏覽器，以及會話自動提交策略（`ov session new --auto-commit-policy-json`、`ov session config set`）。其中的服務端操作也可以通過 HTTP API 和 SDK 完成。

在指令碼中需要注意：

- `ov rm` 不確認就刪除；`-r` 遞迴刪除。
- 服務端報告不健康時 `ov health` 仍退出 0，表格模式的 `ov status` 始終退出 0。
- `echo_command` 開啟時（預設開啟），`find`、`search`、`ls`、`tree`、`grep` 和 `glob` 會先在標準輸出列印一行 `cmd: …` 再輸出結果，使用 `-o json` 時也是如此。
- 大多數命令在 compact JSON 模式下輸出 `{"ok": true, "result": …}` 或 `{"ok": false, "error": …}`；`ov config` 系列命令輸出 `{"status": "ok", "result": …}`。
- 執行命令前必須配置顯示語言；在非互動 shell 中未配置時，CLI 以狀態碼 2 退出。
- `ov doctor` 只存在於用 `uv tool install openviking` 安裝的 Python 包中，用於檢查服務端的 `ov.conf`。npm 和 cargo 安裝的二進位制不包含它。

<a id="_6-自定義-agent-接入指南"></a><a id="_6-1-接入路徑-×-能獲得的能力"></a>

## 自建整合

如果你的 Agent 不在上面的列表中，按需要的行為選擇工作量最小的方式：

| 方式 | 工作量 | Agent 可用的工具 | 自動召回與捕獲 | 提交 |
|---|---|---|---|---|
| [通過 MCP 連線](#通過-mcp-連線) | 幾分鐘 | 服務端 MCP 工具 | 無；由模型自己呼叫工具 | 只有 `remember`，在它自己的會話中 |
| [Agent Plugins 外掛包](./15-agent-plugins.md) | 幾分鐘 | 服務端 MCP 工具，外加一個教模型使用這些工具的 skill | 無 | 只有 `remember` |
| [HTTP API、SDK 或 LangChain](#呼叫-http-api-或-sdk) | 幾小時 | 取決於你呼叫的介面 | 自己實現，或使用 LangChain 中介軟體 | 由你決定 |
| [複用共享外掛程式碼](#複用共享外掛程式碼) | 幾天 | 通過代理使用服務端 MCP 工具 | 召回、捕獲、提交和離線佇列 | 取決於你接入的宿主事件 |

<a id="_6-2-路徑1-通用-mcp-直連-推薦起步"></a>

### 通過 MCP 連線

支援 Streamable HTTP 的客戶端可以連線服務端的 `/mcp`。下面的示例使用常見的 `mcpServers` 格式；其他客戶端的欄位見 [MCP 客戶端](./06-mcp-clients.md)。

```json
{
  "mcpServers": {
    "openviking": {
      "url": "http://127.0.0.1:1933/mcp",
      "headers": {
        "Authorization": "Bearer <api_key>"
      }
    }
  }
}
```

使用使用者或管理員 API key，服務端從 key 中讀取帳戶和使用者。`X-OpenViking-Account` 和 `X-OpenViking-User` 只在 trusted 身份模式下生效，不能覆蓋普通 key 的身份。需要工作區 peer 上下文時，新增 `X-OpenViking-Actor-Peer`，見[認證](../guides/04-authentication.md)。只支援 stdio 的客戶端可以使用 [Agent Plugins 代理](./15-agent-plugins.md)。直接通過 MCP 連線沒有自動召回、捕獲或提交。

<a id="_6-3-路徑2-程式化接入"></a>

### 呼叫 HTTP API 或 SDK

- **REST**。召回用 `POST /api/v1/search/search`；查詢擴寫和去重需要 `mode: "context"`、`session_id` 和 `dedup_turns`（見[召回請求如何到達服務端](#召回請求如何到達服務端)），`rewrite` 用於請求[召回摘要](#召回摘要)。寫入用 `POST /api/v1/sessions/{id}/messages/batch`（最多 100 條，會自動建立會話），提交用 `POST /api/v1/sessions/{id}/commit`，讀取用 `GET /api/v1/content/read`。見[會話](../api/05-sessions.md)和[檢索](../api/06-retrieval.md)。服務端自動提交見[服務端會話與提交機制](#服務端會話與提交機制)。
- **LangChain 與 LangGraph**（`pip install langchain-openviking`）。`OpenVikingContextMiddleware` 在模型呼叫前把召回內容注入 `<openviking_context>`，在 Agent 執行後按 `CommitPolicy`（預設 `never`）捕獲並提交。只讀呼叫重試一次，寫入從不重試。部分寫入會丟擲 `OpenVikingPartialWriteError`，附帶重試剩餘部分所需的計數。見 [LangChain / LangGraph](./07-langchain-langgraph.md)。
- **Open WebUI**。`python -m openviking_openwebui` 啟動一個獨立的 OpenAPI 工具伺服器，提供 7 個工具，沒有刪除工具和 hook。見[其他整合](#其他整合)。

<a id="_6-4-路徑3-要自動-hook-面時複用參考實現"></a><a id="_2-2-memory-plugin-shared-共享層"></a>

### 複用共享外掛程式碼

需要自動召回、捕獲、提交和離線重試時，複用現有程式碼，不必重寫：

- **`examples/memory-plugin-shared/lib/`**（Node.js）包含共享模組：帶回退的召回、會話開場上下文、捕獲清理、離線佇列、批次傳送、MCP 代理、會話 ID 和憑據。通過 hook 檔案配置的宿主可以在 `examples/agent-hook-plugin/hosts/` 下新增介面卡，Cursor、TRAE、ZCode 和 Kimi Code 都是這樣接入的。
- **Agent Plugins 外掛包**（`agent-plugins/`）由可移植的 `plugin.json`、`skills/` 和 `mcp.json` 組成，帶 stdio 到 HTTP 的代理，沒有 hook。它的 `plugin.test.mjs` 檢查是否符合 Agent Plugins 規範，可以作為你自己外掛包的 lint 基線。

[外掛開發指南](./18-plugin-development.md)介紹模組職責、配置、生成副本、安裝器和測試。無論構建什麼，都遵守以下三條規則，讓它的行為與現有整合一致：

1. 使用帶會話 ID 和 `dedup_turns` 的 context 模式召回，讓服務端能擴寫查詢並跨輪去重。
2. 不要讓介面卡自己的超時截斷共享程式碼計算出的截止時間。
3. 在關閉時提交。否則低於閾值的對話尾部會一直未提交，直到其他事件觸發提交。如果宿主沒有關閉事件，開啟 `memory.session_auto_commit.enabled` 併為會話設定策略。完成後，在真實宿主中檢查退出事件是否觸發、寫入是否完成。

<a id="_7-附錄-非-coding-整合速覽"></a>

## 其他整合

| 整合 | 是什麼 | 工具 | 會話與提交 | 失敗處理 | 何時生效 |
|---|---|---|---|---|---|
| [Open WebUI](./08-community-plugins.md#open-webui-tool-server) | 獨立的 OpenAPI 工具伺服器 | 7 個：`ov_search`、`ov_recall_memories`、`ov_add_memory`、`ov_list_memories`、`ov_read_resource`、`ov_add_resource`、`ov_session_status`；沒有刪除工具 | 沒有會話 | 不重試，不快取失敗。它的 `/health` 只回顯配置，不連線 OpenViking | 你啟動程序後 |
| [LangChain 與 LangGraph](./07-langchain-langgraph.md) | Python SDK 適配層：retriever、tools、store、middleware、recorder | `create_openviking_tools()` 提供 12 個工具；`viking_forget` 不在預設 agent profile 中 | 會話 ID 和 thread ID 由呼叫方提供；`CommitPolicy` 預設 `never` | 讀取重試一次，寫入不重試；部分寫入丟擲結構化錯誤 | 你構造它之後 |
| [Agent Plugins](./15-agent-plugins.md) | 帶 stdio 到 HTTP MCP 代理的可移植外掛包 | 服務端 MCP 工具；沒有 hook，由 skill 告訴模型何時呼叫 | 只有 `remember` | 代理在 401 或 403 後用新憑據重試一次，在 400 或 404 後用新 MCP 會話重試一次 | 客戶端載入後 |
| [MCP 客戶端](./06-mcp-clients.md) | 直連 `/mcp` | 服務端 MCP 工具 | 只有 `remember` | 由客戶端決定 | 服務端始終提供 |
| [日誌匯入](./09-log-ingestion.md) | `openviking-server ingest`，在日誌所在的機器上執行 | 無，只匯入 | 會話 ID `{prefix}__{harness}__{id}`；待提交 token 達到 6,000 或空閒 5 秒時提交，`keep_recent_count` 0 | 游標庫、單例項鎖，崩潰後核對服務端訊息數 | 預設關閉；`ingest.enabled` 和各介面卡的 `enabled` 都要開啟。介面卡：Claude Code、Codex、Hermes、OpenCode、OpenClaw、Cursor |
| [OpenViking Helper](./14-openviking-helper.md) | 閉源桌面應用 | 本頁不涉及 | 本頁不涉及 | 本頁不涉及 | 本頁不涉及 |

## 原始碼依據

以上對比依據以下位置核對。需要確認某項限制在你的版本中是否成立時，可以檢視這些位置。

- 服務端 MCP 工具：`openviking/server/mcp_endpoint.py`，以其中的 `@mcp.tool` 註冊為準。
- 寫入與刪除檢查：`openviking/storage/content_write.py` 和 `openviking/storage/viking_fs/_access.py`。
- 服務端自動提交：`openviking_cli/utils/config/memory_config.py` 和 `openviking/session/auto_commit_policy.py`。
- 外掛配置與預設值：`examples/memory-plugin-shared/lib/config-schema.mjs`。
- hook 宿主：`examples/agent-hook-plugin/hosts/`，對應 Cursor、TRAE、ZCode 和 Kimi Code。
- pi takeover：`examples/pi-coding-agent-extension/lib/takeover-core.mjs`。
- OpenClaw 工具和生命週期 hook：`examples/openclaw-plugin/registries/openviking-tools.ts` 和 `examples/openclaw-plugin/plugin/openviking-lifecycle-hooks.ts`。
- Hermes：[Hermes](#hermes) 中連結的舊版內建 provider 固定提交，以及目錄外掛的
  [README](https://github.com/volcengine/OpenViking/blob/main/examples/hermes-plugin/README.md)。

## 參見

- [選擇 Agent 接入方式](./01-overview.md)
- [調整召回延遲](./19-recall-tuning.md)
- [開發與維護 Agent 外掛](./18-plugin-development.md)
- [MCP 客戶端](./06-mcp-clients.md)
- [MCP 工具與協議](../guides/06-mcp-integration.md)
- [客戶端配置欄位](../configuration/02-client.md)
- [檢索 API](../api/06-retrieval.md)
- [會話 API](../api/05-sessions.md)
- [認證](../guides/04-authentication.md)
