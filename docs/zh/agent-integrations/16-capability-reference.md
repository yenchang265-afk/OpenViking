# 整合能力參考

## 導讀

| 你想知道 | 去哪裡 |
|---|---|
| 特定 harness 下，agent 可主動呼叫的工具列表 | [§1.1](#_1-1-主動工具面-agentic-呼叫能力) 主動工具面 + [§2.1](#_2-1-服務端-mcp-工具面)（MCP 面）+ 各檔案卡 |
| 不同關閉方式下，記憶歸檔的時機 | **[§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣) 關閉方式 × harness 終局矩陣** |
| 自動召回是否攜帶 session_id 及其影響 | [§3.2.2](#_3-2-2-判定矩陣) / [§3.2.3](#_3-2-3-profile-開場注入) |
| 如何開啟召回再摘要，以及服務端與客戶端的職責劃分 | [§3.2.5](#_3-2-5-召回再摘要) |
| `forget` 操作與刪除功能的型別邊界 | [§3.5](#_3-5-寫入與刪除的型別邊界) |
| 特定環境變數在不同 harness 下的生效情況 | [§3.1.4](#_3-1-4-配置體系分層) 配置體系分層 + 各檔案卡"配置" |
| 服務端是否具備自動 commit 兜底機制 | [§2.3](#_2-3-服務端會話與-commit-語義) |
| ov CLI 命令全集 | [§5](#_5-ov-cli-命令參考) |
| 自定義 agent 如何接入 OpenViking | [§6](#_6-自定義-agent-接入指南) |
| 某個整合怎麼安裝、怎麼配、怎麼排障 | 該整合的單獨頁面（[§4](#_4-harness-檔案卡) 各檔案卡首行給出連結） |

---

# 1. 能力總覽

## 1.1 主動工具面（Agentic 呼叫能力）

- **MCP 型 harness（claude-code、codex/trae-cli、cursor、trae/trae-cn、zcode、kimicode、opencode、dsh、pi）的主動工具面完全一致，共 16 個工具**：這些工具由服務端統一定義，各外掛讀取 `~/.openviking/ovcli.conf` 並連線服務端 MCP 工具；pi 在擴充中使用官方 MCP 客戶端，再把發現的工具註冊成 pi 原生工具。

- trae-cli 指 TraeCode CLI 2.0（僅支援 2.0），經 codex 外掛別名安裝，外掛與 codex 格式相容，下文矩陣併入 codex 行。

| harness | 工具面形態 | 工具數（預設開） | 搜 memory | 搜 resource | 搜 skill | 寫 memory | 寫 resource | 寫 skill | 刪除型別邊界 |
|---|---|---|---|---|---|---|---|---|---|
| claude-code | MCP 透傳 | 16 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ `add_skill`¹ | 無型別區分² |
| codex / trae-cli | MCP 透傳 | 16 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ `add_skill`¹ | 無型別區分² |
| cursor | MCP 透傳 | 16 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ `add_skill`¹ | 無型別區分² |
| trae / trae-cn | MCP 透傳 | 16 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ `add_skill`¹ | 無型別區分² |
| zcode | MCP 透傳 | 16 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ `add_skill`¹ | 無型別區分² |
| kimicode | MCP 透傳 | 16 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ `add_skill`¹ | 無型別區分² |
| opencode | MCP 透傳（宿主加 `openviking_` 字首） | 16 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ `add_skill`¹ | 無型別區分² |
| dsh | MCP 透傳 | 16 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ `add_skill`¹ | 無型別區分² |
| pi | MCP 映象（官方客戶端；擴充加 `openviking_` 字首） | 16，即 `tools/list` 返回什麼就是什麼（註冊有前置條件³） | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ `add_skill`¹ | 無型別區分² |
| openclaw | 原生註冊（15 個 `memory_*`/`ov_*` 等） | 15（預設開 14⁴） | ✅ `memory_recall` | ✅ `ov_search`（預設雙 scope） | ✅ `ov_search` | ✅ `memory_store` | 預設關⁴ | ✅ `add_skill` | memory-only 白名單 + 單候選 score≥0.85 才自動刪 |
| hermes | 原生註冊（6 個 `viking_*`） | 6（provider 啟用即全開） | ✅ | ✅ | ✅ | ✅ `viking_remember`（直寫檔案，不走抽取） | ✅ 多協議攝取（HTTP/Git/SSH/本地檔案/目錄 zip） | ❌ | memory-only + `.md` 葉子校驗 |
| ov CLI | CLI 命令 | ~40 命令組 | ✅ `ov find` | ✅ `ov find` | ✅ `ov find` | ✅ `ov add-memory` | ✅ `ov add-resource` | ✅ `ov add-skill` | `ov rm` 直接執行（TUI 刪除有確認 + root/scope 禁刪） |

¹ MCP `write` 拒絕寫使用者自己的 `skills/` 子樹；寫 `viking://agent/skills` 時會生成一個繞過 skill 安裝流程的普通檔案（沒有 frontmatter abstract，也不做 privacy 抽取），所以共享 skill 同樣要走 `add_skill`。skill 的新建、安裝和替換走 MCP `add_skill` 工具（內聯 SKILL.md 文本、Git URL，或本地目錄/zip 的簽名上傳），它和 REST `POST /api/v1/skills` 共用同一套安裝實現。
² MCP `forget` 不區分 memory/resource/skill 型別；儲存層保留了名稱空間根保護機制（裸 `viking://`、`viking://user`、`viking://agent` 根拒刪），詳見 [§3.5](#_3-5-寫入與刪除的型別邊界)。
³ pi 工具註冊前置：需未命中 `bypassSessionPatterns`、`client.health()` 通過、`ensureSession` 成功，且 `/mcp` 握手取回工具清單（`index.ts:150-205`）；共享鍵 `mcpEnabled: false` 則整個橋接都不發起，不算失敗。握手失敗只讓本次會話沒有 OpenViking 工具，召回、會話同步與 takeover 照常，`before_agent_start` 會在後續輪次重試（`index.ts:252-255`），因此 pi 啟動之後才拉起的 server 不必重啟 pi 就能接上。詳見 [§3.6](#_3-6-降級與容錯)。
⁴ openclaw 的 `add_resource` 需經過雙重 opt-in 後方可開啟。

**skill 的增刪邊界**：新增入口包含 MCP `add_skill`、openclaw `add_skill`（預設開）、`ov add-skill` 與 REST；刪除邊界分四檔，詳見 [§3.5](#_3-5-寫入與刪除的型別邊界)。

## 1.2 自動 hook 面（通過 Harness 自動實現）

| harness | 接入方式 | 自動召回 | 召回帶 session_id | 再摘要（客戶端）* | profile 注入 | 接管宿主壓縮 | 離線補償（pending queue） | statusline |
|---|---|---|---|---|---|---|---|---|
| claude-code | 9 hook + MCP 代理 + slash + statusline + skill | ✅ | ✅ | ✅ 本地 `claude -p` / 服務端 rewrite（預設 auto） | ✅（10000）+ `<available-skills>`（1200） | ❌（PreCompact 只 commit） | ✅ | ✅ |
| codex / trae-cli | 6 hook + MCP 代理 + skill | ✅ | ✅ | ✅ 本地 `codex exec`（預設開） | ✅（10000）+ `<available-skills>`（1200） | ❌ | ✅ | ❌ |
| cursor | 6 hook + MCP 代理 + rule + skill | ✅ | ✅ | ❌ | ✅（10000）+ `<available-skills>`（1200） | ❌ | ✅ | ❌ |
| trae / trae-cn | 4 hook + MCP 代理 | ✅ | ✅ | ❌ | ✅（10000）+ `<available-skills>`（1200） | ❌ | ✅ | ❌ |
| zcode | 4 hook + MCP 代理 | ✅ | ✅ | ❌ | ✅（10000）+ `<available-skills>`（1200） | ❌ | ✅ | ❌ |
| kimicode | 7 個原生 plugin hook + MCP 代理 | ✅ | ✅ | ❌ | ✅（10000）+ `<available-skills>`（1200），首次成功 prompt 載入 | ❌（PreCompact 只捕獲/commit） | ✅ | ❌ |
| opencode | 8 plugin hook + MCP 代理 | ✅ | ✅ | ❌ | ✅（10000）+ `<available-skills>`（1200） + repo 列表進 system prompt | ❌（compacting 前後各 commit 一次） | ✅ | ❌（有 toast） |
| dsh | Cordis 原生外掛（同進程）+ MCP 代理 + skill | ✅ | ✅ | ❌ | ✅（10000）+ `<available-skills>`（1200），每 session 一次 | ❌ | ✅ | ❌ |
| pi | 原生擴充（9 事件） | ✅ | ✅ | ❌ | ✅（10000）+ `<available-skills>`（1200），進 systemPrompt 每輪重拼 | ✅ **takeover**（預設開） | ✅ | ✅ |
| openclaw | context-engine 外掛（`ownsCompaction:true`） | ✅ | ❌（走 `/find`，該介面無 session_id 欄位） | ❌ | ❌ | ✅ **ContextEngine 全接管** | ❌ 失敗輪次不重放 | ❌ |
| hermes | MemoryProvider 原生外掛 | ✅ | 部分（僅 `search/search` 首選路徑；降級 `/find` 不帶） | ❌ | ❌（靜態工具指引塊） | ❌ | ✅ 程序內佇列（不落盤） | ❌ |
| ov CLI | 一次性命令 | ❌（`ov find/search` 是顯式命令） | —（`ov search --session-id` 為顯式引數） | ❌ | ❌ | ❌ | ❌ | ❌ |

\* 此列指客戶端是否內建了針對召回結果的本地壓縮；服務端則在 context 檢索面上，統一為所有呼叫方提供 digest 能力（`rewrite` 引數，[§3.2.5](#_3-2-5-召回再摘要)）。

profile 注入列裡，第一個數字是 `profileTokenBudget` 的預設值，`<available-skills>` 後面的數字是它單獨的 `skillCatalogTokenBudget` 預設值（[§3.2.3](#_3-2-3-profile-開場注入)）。

**session_id 攜帶現狀**：除 openclaw（其呼叫的 `/find` 介面無該欄位）與 hermes 的降級路徑外，其餘所有 harness 的自動召回均顯式攜帶 session_id，並有跨外掛迴歸測試釘死（`examples/memory-plugin-shared/recall-session-wiring.test.mjs:16-39`）。

## 1.3 形態分組

- **全家桶型**（hook 自動化 + MCP 工具面 + 周邊 UX 齊全）：claude-code、codex（trae-cli 經別名安裝同屬此檔）。
- **瘦 hook 型**（共享 agent-hook-runtime，核心行為基本一致，差異僅體現在宿主事件、transcript 解碼與閾值上）：cursor、trae/trae-cn、zcode、kimicode。
- **plugin 事件型**：opencode（宿主事件面最豐富，dispose 覆蓋關閉）。
- **同進程原生型**：dsh（Cordis）、pi（擴充 + takeover 壓縮接管）、openclaw（context-engine 全接管）、hermes（MemoryProvider）。
- **工具型**：ov CLI（所有操作均為顯式呼叫，不存在任何自動行為）。
- **非 coding**：Open WebUI（工具伺服器）、LangChain（SDK 庫）、Agent Plugins 便攜包（MCP+skill 規範包）、通用 MCP 直連、log ingestion（日誌反向匯入）、Helper（桌面端）。

---

# 2. 公共能力核

per-harness 章節（檔案卡）只寫差異；所有共享事實均在本章一次性說明完畢。

## 2.1 服務端 MCP 工具面

這些工具定義在服務端，後續更新也會在服務端統一發布，Harness 只需通過外掛代理 MCP 拿到最新的 `~/.openviking/ovcli.conf` 即可。

| # | 工具名 | 功能 | 引數要點（定義行號） |
|---|---|---|---|
| 1 | `find` | 不依賴會話上下文的快速語義檢索 | `query, target_uri="", limit=10, min_score=0.35, level, context_type, read_content`；只傳 `context_type="skill"` 時改調 `SearchService.find_skills`（包級檢索，`skill_package_retriever.py`）：一個 skill 包一條命中，URI 改寫為 `<包根>/SKILL.md`，摘要取包自身的 abstract，`read_content` 也讀這個檔案；不傳 `target_uri` 時同時檢索 `viking://~/skills` 與 `viking://agent/skills`。其它 `context_type` 組合，以及不帶 query 只給 filter 的呼叫，仍走通用檢索路徑；渲染時的 URI 改寫和「一個包一條」合併照常生效（`:262`） |
| 2 | `search` | 深檢索，可帶 `session_id` + 意圖分析 | `session_id` 僅在服務端 `retrieval.enable_intent`（預設 true）開啟時才會載入會話（`:315`）。這裡按條目檢索 skill，只在渲染時合併，所以一個包在多個檔案上命中會佔掉多個 `limit` 名額，摘要也取自實際命中的檔案 |
| 3 | `read` | 讀取單個或多個 `viking://` 檔案全文 | 併發訊號量 10；單條失敗返回 `(nothing found at <uri>)` 不拋錯（`:643`） |
| 4 | `list` | 列目錄（函式名 `ls`，註冊名顯式改寫為 `list`） | `recursive=False`（`:784`） |
| 5 | `tree` | 遞迴目錄樹 | `level_limit=3, node_limit=1000, include_abstract=False`；`include_abstract=true` 時列印每個目錄的 abstract（最長 1024 字元），因此 `tree(uri="viking://~/skills", level_limit=1, include_abstract=true)` 能列出全部 skill 及其描述（`:862`） |
| 6 | `remember` | 寫長期記憶 | 內部建一次性會話 `mcp-store-<uuid12>` 並立即 `commit_async`（`:940`）——這是 MCP 面唯一的 commit 入口；MCP 沒有顯式 commit 工具 |
| 7 | `write` | 寫 `viking://` 檔案 | `mode=replace\|append\|create`：replace 覆蓋或在缺失時建立，append 追加或在缺失時建立，create 僅建立缺失檔案且已存在時返回衝突；顯式 create 的副檔名白名單為 `.md .txt .json .yaml .yml .toml .py .js .ts`；可寫域 `resources/user/agent`；使用者根下 `skills/ peers/ privacy/ sessions/` 只讀；已存在的 `.abstract.md/.overview.md` sidecar 可改正文，但公共 API 不能建立；寫 `viking://agent/skills` 不會被拒絕，但會繞過 skill 安裝流程，skill 請改用 `add_skill`，詳見 [§3.5](#_3-5-寫入與刪除的型別邊界)（`:965`；`content_write.py:60-81`） |
| 8 | `edit` | 精確字串替換 | `old_string` 空/0 命中/多命中且非 replace_all 均報錯，且檔案內容不變；編輯 skill 包內的檔案不會重新觸發 skill 安裝流程，詳見 [§3.5](#_3-5-寫入與刪除的型別邊界)（`:1005`） |
| 9 | `add_resource` | 資源攝取（遠端 URL / 本地檔案簽名上傳 / Connector） | `watch_interval` 單位為分鐘（0=不 watch）；本地路徑分支返回簽名上傳 URL（TTL 預設 600s），上傳後自動入庫，無需二次呼叫（`:1161`） |
| 10 | `add_skill` | 新建、安裝或替換 skill | `data`（完整 SKILL.md 文本）或 `path`（Git URL / GitHub tree URL，或本地 SKILL.md、目錄、zip——本地分支和 `add_resource` 一樣返回簽名上傳 URL）；`skills=[...]` 從多 skill 源裡挑選，`list_only=true` 只預覽；`target_uri="viking://agent/skills"` 表示帳戶共享。與 REST `POST /api/v1/skills` 共用安裝程式碼。工具描述裡寫明它是新建和更新 skill 的唯一入口，刪除請走 `ov skills remove` 或 Studio（`:1452`） |
| 11 | `list_watches` | 列 watch 訂閱，商業版尚未支援 | scheduler 未執行時返回錯誤串（`:1621`） |
| 12 | `cancel_watch` | 按 `to_uri` 取消，商業版尚未支援 | 刻意不暴露 pause/resume/trigger/update（`:1653`） |
| 13 | `grep` | 正則內容檢索 | 多 pattern 併發（訊號量 10），`node_limit=10`（`:1696`） |
| 14 | `glob` | 文件名 glob | `node_limit=100`（`:1765`） |
| 15 | `forget` | 刪除 URI（不可恢復） | 預設 `recursive=False`；型別邊界詳見 [§3.5](#_3-5-寫入與刪除的型別邊界)（`:1791`） |
| 16 | `health` | 健康檢查 | 無參（`:1808`） |

配套機制：

- **可移植 schema 重寫**（`:1149-1218`）：模組匯入時把所有工具的 `anyOf`/`$ref` 折成扁平型別，以相容 Gemini 等 OpenAPI 3.0 子集客戶端；執行時校驗仍用原始 Python 簽名（例如 `read` 廣播的 schema 是 array，但仍接受裸字串）。所有 MCP 客戶端拿到的 schema 都由服務端統一產出，客戶端無差異。
- **身份中介軟體**（`:149-233`）：與 REST 共用 `resolve_identity`，依次讀 `x-api-key` / `authorization` / `x-openviking-account` / `x-openviking-user` / `x-openviking-actor-peer`；account/user 預設回落 `"default"`。

## 2.2 memory-plugin-shared 共享層

`examples/memory-plugin-shared/lib/` 下共 25 個 `.mjs` 模組，是 JS 系 harness 的唯一事實源。兩種消費形態：

1. **Vendoring（複製）**：由 `sync.mjs` 分發到 7 個目標，每個檔案首行加 `// GENERATED FROM ... DO NOT EDIT.`（因此 vendored 副本行號 = lib 源行號 + 1）。分發清單不再手寫：每個目標拿的是自身程式碼實際 import 的傳遞閉包。claude-code、codex、agent-plugins 由宿主直接指向倉庫目錄安裝，openclaw 的 `ov-install` 可以按 git ref 逐個檔案下載外掛，所以這四個的生成副本提交進 git，並由 main 上的推送重新生成；opencode、dsh 以 npm 包釋出，pi 由安裝指令碼打包，這三個在打包時生成副本，git 中不保留。
2. **相對路徑直接 import（不復制）**：cursor / trae / trae-cn / zcode 直接 `import "../../memory-plugin-shared/lib/..."`；安裝器把包與這些 hook 傳遞 import 到的共享模組一起復制到 `~/.openviking/agent-integrations/{<client>,memory-plugin-shared}/`，保持相對層級。這份安裝集合對 import 閉合，包括 hook 執行時所需的 workspace 配置層。執行期幾個 harness 共用該目錄，任一重灌都會整體覆蓋。

核心模組速覽（細節在各維度章展開）：

| 模組 | 職責 | 消費方 |
|---|---|---|
| `recall-core.mjs` | 召回請求構造 + 三級降級 + 本地兜底排序注入 | 全部 JS 系 harness |
| `agent-hook-runtime.mjs` | "瘦 hook"一體化執行時（配置經共享 schema 解析、session id 派生、跨程序鎖、fetch、commit） | cc / codex / cursor / trae / trae-cn / zcode |
| `mcp-proxy-core.mjs` | stdio↔streamable-HTTP MCP 代理核心 | 使用子程序通訊的 MCP 整合與 agent-plugins；pi 直接使用官方客戶端 |
| `ov-http.mjs` | hook 到 OpenViking 服務端的唯一齣網路徑：請求頭、AbortController、信封解析 | 全部 JS 系 + agent-plugins |
| `pending-queue.mjs` | 磁碟離線佇列 + 會話啟動重放 | cc / codex / cursor / trae×2 / zcode / opencode / dsh / pi |
| `batch-send.mjs` | 100 條/批寫入 + 404/405 逐條降級 + 連續字首入隊 | cc / codex / opencode + agent-hook 系 |
| `profile-inject.mjs` | session-start 的 profile + 可用記憶清單 + `<available-skills>` skill 清單注入 | 9 個 harness（openclaw / hermes 除外） |
| `recall-compress-core.mjs` | 召回壓縮 prompt + URI 編輯距離修復 + 快取 | claude-code |
| `capture-utils.mjs` | 訊息歸一 + 注入迴流防護 + 內建捕獲啟發式（應答語、slash 命令、資訊量下限） | cc / codex / opencode / dsh / pi / zcode / cursor / trae×2 |
| `input-filters.mjs` | 編譯並執行操作員自己配的 sed 風格規則 —— `s` 替換、`d` 丟棄、`k` 僅保留，可限定角色 —— 作用於召回 query 與每個被捕獲的回合；解析失敗的規則會被報告並跳過，不拋異常（[語法](https://github.com/volcengine/OpenViking/blob/main/examples/claude-code-memory-plugin/README_CN.md#輸入過濾器)） | 所有 hook 外掛；`recallQueryFilters` / `captureFilters` 兩個 knob 目前由 claude-code / codex 提供 |
| `credentials.mjs` | 憑據解析鏈（詳見 [§3.1.3](#_3-1-3-憑據體系)） | 全部 JS 系 |
| `session-model.mjs` | 會話 id 字首派生 + bypass glob | 全部 JS 系 |
| `async-writer.mjs` | 寫路徑 detach（drain stdin → spawn → approve → write → unref；spawn 失敗回落同步） | cc / codex / zcode |
| `workspace-peer.mjs` | 按 `peer.source` 解析 actor peer（預設 / 模板 / 保留用於雙讀的舊 peer id，詳見 [§3.1.3](#_3-1-3-憑據體系)） | 全部 JS 系 |
| `workspace-identity.mjs` | workspace 根目錄 + git 身份（歸一化 `origin`、倉庫根路徑、worktree/submodule 型別），純檔案系統上溯、不起 `git` 子程序，按 cwd 快取 | 全部 JS 系 |
| `workspace-config.mjs` | 分層 workspace 配置：讀 `<root>/.openviking/config.json` 與 `config.local.json`，帶來源（provenance）合併各層，剝離連線與憑據類 key | cc / codex / cursor / trae×2 / zcode / opencode / dsh / pi |
| `workspace-registry.mjs` | 每機登錄檔 `~/.openviking/workspaces/<slot>.json`——一個 workspace 一個檔案，由人工建立、外掛只讀，優先順序高於任何已提交的檔案 | cc / codex / cursor / trae×2 / zcode / opencode / dsh / pi |
| `uri-guard.mjs` | 檔案工具的路徑引數是 `viking://` URI 時拒絕呼叫；shell 命令帶 `viking://` URI 時照常執行，並給模型附加提示；grep 的 `pattern` 是搜尋文本，不當作路徑；目標是 skill URI（`isSkillUri()`）時，write 與 edit 的提示改為 `add_skill`，不再指向 `write` / `edit` | 拒絕：各 harness 的 PreToolUse/tool.execute.before 類 hook；提示：PreToolUse，或執行後的 hook（dsh `tools/post-execute`、pi `tool_result`、opencode `tool.execute.after`） |
| `config-schema.mjs` | 全部旋鈕的唯一宣告：規範名、型別、預設值、取值範圍、`OPENVIKING_*` 變數、可接受的舊拼寫、workspace 鍵。doctor 的已知鍵集合與 workspace 檔案的點分鍵對映都是它的投影 | cc / codex / cursor / trae×2 / zcode / opencode / dsh / pi |
| `plugin-config.mjs` | 按層解析全部已宣告旋鈕：env → workspace 各層 → ovcli.conf `plugin.<harness>` → ovcli.conf `plugin` → ov.conf 的 harness 段 → 預設值 | cc / codex / cursor / trae×2 / zcode / opencode / dsh / pi |
| `setup-wizard.mjs` | 互動式寫 ovcli.conf | cc / codex / opencode / pi 暴露入口 |
| `retryable.mjs` | 可重試判定：status 0/408/429/≥500，或 409 且 `error.details.retryable===true`；4xx（含 401/403）不重試 | 全部 JS 系 |

## 2.3 服務端會話與 commit 語義

- **會話隱式建立**：外掛普遍不顯式呼叫 `POST /sessions`（dsh 例外，它會發一個只含 `session_id` 的 create）；首次 `POST /sessions/{id}/messages(/batch)` 時由服務端 `auto_create=True` 建會話。召回側 `mode="context"` 的 `_load_session(auto_create=True)` 也會建（第一次召回即在服務端建立會話）。
- **commit 兩階段**：`POST /sessions/{id}/commit` 的 Phase 1（歸檔 archive）同步完成後才返回，Phase 2（記憶抽取）作為後臺任務返回 `task_id`。`keep_recent_count` 服務端預設 **0**（全量歸檔，不留 live tail）。
- **服務端自動 commit 預設關閉，除非顯式策略或部署級預設策略將其啟用**：
  - `memory.session_auto_commit.default_enabled = false`、`idle_enabled = false`（`memory_config.py:15-16`）；無儲存 policy 的會話自動 commit 關閉（`session_service.py:637-638`）；idle 掃描器在 `idle_enabled=false` 時根本不建立（`core.py:440-448`），構成雙重門控。
  - `POST /messages` 的 auto_create 不接受 policy 引數，但配置後會繼承 `server.user_config_defaults.auto_commit_policy`；`POST /sessions`（create）與 `PATCH /sessions/{id}/config` 仍是顯式的 Session 級控制面。
  - 當前沒有外掛下發 `auto_commit_policy`；第一方客戶端中會下發該欄位的是 **ov CLI**（`ov session new --auto-commit-policy-json` / `--no-auto-commit`、`ov session config set`）。
  - policy 顯式啟用時，服務端預設閾值是 `pending_token_threshold=150000（嚴格大於）/ message_count_threshold=100 / idle_timeout_seconds=86400 / keep_recent_count=0 / min_commit_interval_seconds=0`。注意這組服務端預設值與各外掛客戶端的 20000/10 是相互獨立的兩層配置。
- **由此**：外掛可通過 `server.user_config_defaults.auto_commit_policy` 繼承新 Session 的 token/message 閾值；idle timeout 兜底還需開啟 `memory.session_auto_commit.idle_enabled=true`。未配置該 fallback 時，客戶端仍需自行安排 commit 路徑（[§3.3](#_3-3-會話與-commit-生命週期)）。
- **tool output 外接**：服務端 `tool_output_externalization.enabled=True`、`threshold_chars=20000`（`server/config.py:257-258`）——客戶端普遍把 `captureToolMaxChars` 設到 1000000 僅作兜底，真正的截斷/外接在服務端做，externalized 結果通過 `tool_output_ref` 引用（openclaw 有三個專門工具讀它）。
- **服務端召回相關熔斷**：`retrieval.recall_intent_timeout_s=5.0`（query expansion）、`recall_rewrite_timeout_s=30.0`（digest，[§3.2.5](#_3-2-5-召回再摘要)）、`enable_intent=true`。客戶端超時預算按這兩條推導（[§3.2.4](#_3-2-4-超時與預算鏈)）。

---

# 3. 維度詳解

## 3.1 接入形態、安裝與配置體系

### 3.1.1 判定矩陣

| harness | 整合形態 | 安裝通道 | 會話 id 字首/格式 | 配置來源 | 獨立 setup 嚮導 |
|---|---|---|---|---|---|
| claude-code | CC 外掛（marketplace）：包含 9 hook + MCP 代理 + slash + statusline + skill | 一鍵 `install.sh --harness claude`（支援現代 plugin 路徑與 legacy `claude mcp add` 相容路徑）/ 手動 marketplace / TOS 映象 | `cc-<CC session_id 原文>`；subagent 格式為 `…__subagent-<agent_id>` | env + ovcli.conf `plugin.claude_code` + ov.conf `claude_code` | ✅ `scripts/setup.mjs` |
| codex | Codex 外掛（marketplace）：包含 6 hook + MCP 代理 + skill | 一鍵 `--harness codex` / `codex plugin marketplace add`（TOS 走 dumb-HTTP git 以保留遠端更新能力） | `cx-<safeId>`（確定性推導，不讀取 state） | env + ovcli.conf `plugin.codex` + ov.conf `codex` | ✅ |
| trae-cli | **codex 外掛別名安裝**（TraeCode CLI 2.0，僅支援 2.0；Codex 系：binary `traecli`、配置 `~/.trae/traecli.toml`；能力面與 codex 一致） | 一鍵 `--harness trae-cli`（複用 codex 安裝流程；marketplace 命令會隨指向的 binary 執行，如 `traecli plugin marketplace add`） | 與 codex 的派生規則一致 | 與 codex 一致（env + ovcli.conf `plugin.codex` + ov.conf） | ✅（同 codex） |
| cursor | 配置驅動（寫入 `~/.cursor/hooks.json`+`mcp.json`）+ rule + skill | 一鍵 `--harness cursor` | `cu-<conversation_id>` | env + ovcli.conf `plugin.cursor` | ❌（共用安裝器 TUI） |
| trae / trae-cn | 配置驅動（`~/.trae{,-cn}/hooks.json` + 平臺相關 mcp.json） | 一鍵 `--harness trae,trae-cn` | `tr-` / `trcn-` | env + ovcli.conf `plugin.trae` / `plugin.trae_cn` | ❌ |
| zcode | 配置驅動（合併進 `~/.zcode/cli/config.json`，並強制 `hooks.enabled=true`） | 一鍵 `--harness zcode` | `zc-<sess_…>` | env + ovcli.conf `plugin.zcode` | ❌ |
| kimicode | Kimi Code 原生外掛（`kimi.plugin.json`，managed copy + `installed.json`） | 一鍵 `--harness kimicode` | `kc-<session_id>` | env + ovcli.conf `plugin.kimicode` + workspace 檔案 | ❌ |
| opencode | npm 外掛 `@openviking/opencode-plugin`（config hook 自注入 MCP 條目） | 一鍵 `--harness opencode`（npm 註冊 + 代理快照兜底）/ 手動 npm / 原始碼 | `oc-<id>`；subagent 格式為 `oc-<parent>__subagent-<child>` | env + ovcli.conf `plugin.opencode` | ✅ |
| dsh | Cordis 同進程外掛（`cordis.patch.yml` plugin group） | 統一安裝器（會詢問 profile，預設 `web`），或執行 `dsh plugin --profile web add @openviking/dsh-memory-plugin` | `dsh-<session.id 原樣>`；subagent 各自獨立會話 | env + ovcli.conf `plugin.dsh` + cordis patch config（行為旋鈕的最低層；憑據仍以 patch 優先） | ❌ |
| pi | pi 原生擴充（目錄裝載，jiti 直譯 TS） | 一鍵 `--harness pi`（複製到自動發現目錄，無需 `pi install`） | `pi-<piSessionId>` | env + ovcli.conf `plugin.pi`（憑據欄位由憑據鏈統一解析） | ✅ |
| openclaw | context-engine 外掛（`ownsCompaction:true`）+ 15 工具 + 5 slash + 4 hook + HTTP 路由 | ClawHub 執行 `openclaw plugins install clawhub:@openviking/openclaw-plugin` 搭配 `openclaw openviking setup` / npm 安裝器 / TOS 離線包 | UUID 原樣小寫，否則 `sha256(sessionKey)`；`memory_store` 臨時會話 `memory-store-<ts>-<rand>` | `openclaw.json` 的 `plugins.entries.openviking.config`（嚴格校驗：存在未知鍵/非法值時外掛進入 setup-only 模式）+ 少量 env | ✅ `openclaw openviking setup`（互動/非互動 + key 角色探測 + 版本相容檢查） |
| hermes | Hermes bundled MemoryProvider（隨 Hermes 釋出，無需裝外掛） | 執行 `hermes memory setup openviking`（curses 嚮導）或手動 `config set memory.provider openviking` + `.env` | 由 Hermes 生成 `%Y%m%d_%H%M%S_<hex6>`，外掛原樣使用 | `.env`（`OPENVIKING_*`）或 ovcli.conf 聯動（`use_ovcli_config` 模式會清空 .env 裡的 5 個對應變數）+ config.yaml | ✅（多層選單） |
| ov CLI | Rust 原生二進位制 | npm `@openviking/cli` / `uv tool install openviking` / cargo / GitHub Releases | 無自有會話（`ov chat` 預設使用 machine-uid） | `ovcli.conf`（多 profile）+ 少量 env | ✅ `ov config`（TUI 嚮導） |

### 3.1.2 統一安裝器

統一安裝指令碼 `examples/memory-plugin-shared/install.sh` 覆蓋 11 個 harness id：`claude, codex, cursor, trae, trae-cn, trae-cli, zcode, kimicode, opencode, pi, dsh`（其中 openclaw 走自有渠道；`trae-cli` 則複用 codex 安裝流程，[§3.1.1](#_3-1-1-判定矩陣)）。要點如下：

- 雙分發：`--dist github|tos`；三源：`--source remote|archive|dev`。以 `bash <(curl …)` 方式執行時會從 `/dev/tty` 讀取輸入，從而保留互動。
- 官方 docs 的規範一鍵命令是不帶 `--harness` 的裸命令（執行後進入 TUI 多選）；而各外掛自帶的 setup-helper 轉發指令碼在呼叫時會自動補 `--harness`。
- 冪等合併：hooks/mcp 條目按 `OPENVIKING_INTEGRATION_ID` 標記識別自有條目，做到剔舊追新的同時不動第三方；寫入採用原子操作——先備份 `.bak`，寫 tmp 後 rename 覆蓋，許可權 0600。
- 憑據嚮導寫 `~/.openviking/ovcli.conf`：三選一（本地 `http://127.0.0.1:1933` / 火山雲 `https://api.vikingdb.cn-beijing.volces.com/openviking` / 自定義），已有配置先展示當前值再問"沿用/重配"，API key 掩碼。
- 解除安裝：`--uninstall` 覆蓋 cursor / trae / trae-cn / zcode / kimicode，並順帶清理 trae-cli 遺留的舊 hook 配置；其他 Codex 格式或宿主託管外掛通過各自宿主的外掛管理解除安裝。
- 安裝後自檢：grep 配置 + `node --check` + 一次 `OPENVIKING_MEMORY_ENABLED=0` 的 smoke run。
- Node 門檻：安裝器檢查 18+。

### 3.1.3 憑據體系

程式碼中並存著四套並行的憑據解析體系，env 變數名與認證頭各不相同，排障時先分清物件：

| 家族 | 消費者 | URL env | Key env | 身份 env | 認證頭 |
|---|---|---|---|---|---|
| **A. JS 共享核**（`credentials.mjs`） | claude-code / codex（含 trae-cli）/ cursor / trae×2 / zcode / opencode / pi / dsh / agent-plugins | `OPENVIKING_URL` → `OPENVIKING_BASE_URL` | `OPENVIKING_BEARER_TOKEN` → `OPENVIKING_API_KEY` | `OPENVIKING_ACCOUNT` / `OPENVIKING_USER` / `OPENVIKING_PEER_ID` | 只發 `Authorization: Bearer`；本家族任何 harness 都不發 `X-API-Key` |
| **B. openclaw**（自有 `config.ts`） | openclaw | `OPENVIKING_BASE_URL` → `OPENVIKING_URL` | `OPENVIKING_API_KEY`（支援 SecretRef env/file） | `OPENVIKING_ACCOUNT_ID` / `OPENVIKING_USER_ID`（注意此處帶 `_ID`） | `X-API-Key`（指向 OV Cloud 時注意其實際採用 Bearer 認證） |
| **C. hermes**（Python） | hermes | `OPENVIKING_ENDPOINT` | `OPENVIKING_API_KEY` | `OPENVIKING_ACCOUNT` / `OPENVIKING_USER` / `OPENVIKING_AGENT`（=actor peer） | `X-API-Key` + `Bearer` 雙發；有 key 時預設不發租戶頭（被服務端以 trusted 報錯拒絕時會自動補頭重試一次） |
| **D. ov CLI**（Rust） | ov | conf 檔案為主 | conf | `--account/--user/--actor-peer-id` | `X-API-Key`；LDAP Basic / OIDC Bearer 按 `auth_mode` 切換；api_key 含 ≥2 個 `.` 時自動附加 Bearer（JWT 兜底） |

家族 A 的解析鏈如下（其餘家族見檔案卡）：

1. 模式由 `OPENVIKING_CREDENTIAL_SOURCE`（別名 `_CREDENTIALS_SOURCE`）控制，取值 ∈ `env|cli|auto`（預設 auto）。強制為 `env` 時，連線不讀兩個檔案：沒設的變數就是空，URL 預設 `http://127.0.0.1:1933`。`peerId` 配置仍按它自己的分層解析。
2. **auto 語義是 env 優先**：只要任一 env 憑據欄位（`URL`、`BASE_URL`、`MCP_URL`、`BEARER_TOKEN`、`API_KEY`、`ACCOUNT`、`USER`、`PEER_ID`）存在，就從環境變數開始往下解析；只有這些全空、且 ovcli.conf 存在並含憑據欄位時，鏈條才釘在這個檔案上：跳過環境變數裡的憑據，`apiKey` 仍會依次回落到 `plugin` 鍵和 ov.conf `<harness>.apiKey`（Claude Code 與 agent-plugins 再回落到 `server.root_api_key`），`account` / `user` 只回落到 `plugin` 鍵。`OPENVIKING_AUTH_MODE` 不算憑據欄位，單獨設定不會解除釘定。
3. baseUrl：env → ovcli `url` → ov.conf `server.url` → `http://{server.host|127.0.0.1}:{server.port|1933}`（其中 `0.0.0.0` 歸一為 `127.0.0.1`）；兜底 `http://127.0.0.1:1933`。
4. apiKey：嵌入宿主傳入的值（dsh 的 Cordis patch）排在所有層之上，URL、account、user、auth mode 同理；其後是 `BEARER_TOKEN` → `API_KEY` → ovcli `api_key` → ovcli `plugin.<harness>.apiKey` → ovcli `plugin.apiKey` → ov.conf `<harness>.apiKey` → `server.root_api_key`。`<harness>` 是呼叫方 harness 自己的那段（snake_case，如 `trae_cn`；`claude-code` 與 `claude_code` 指向同一段）；account / user / peerId 在各自鏈條的同一位置讀同一段。
5. mcpUrl：`OPENVIKING_MCP_URL`（非 cli 模式）→ `${baseUrl}/mcp`。
6. 統一請求頭：`Authorization: Bearer` + `X-OpenViking-Account/User`（僅 trusted 模式）+ `X-OpenViking-Actor-Peer` + `User-Agent: openviking-memory-<harness>/<version>`。`api_key` 模式的服務端從 key 裡取身份、忽略這兩個頭，所以那裡不發，免得把身份報給鏈路上的每一層代理。模式解析順序：`OPENVIKING_AUTH_MODE`（任何模式下都讀）→ `ovcli` `plugin.<harness>.authMode` → `plugin.authMode` → `ov.conf` `<harness>.authMode` → `ov.conf` `server.auth_mode` → 只要解析出了 account 或 user 就算 trusted。
7. **hook 與 MCP 共用一份連線**：以上規則都由 `credentials.mjs` 的 `resolveConnection()` 實現。hook 的 loader（`buildPluginConfig()`）和每個 MCP proxy（經各自 harness 的 loader，agent-plugins 經 `buildProxyConnection()`）都呼叫它，而且它不讀當前目錄，所以從外掛目錄啟動的 proxy 與 hook 解析結果相同。跨程序邊界只有兩種做法：Codex 只把 `.mcp.json` `env_vars` 列出的變數交給 MCP 程序，這份名單必須包含 `MCP_PROXY_ENV_VARS`；dsh 直接轉發解析好的連線，每個憑據變數都顯式寫出（空值也寫），並帶上 `OPENVIKING_CREDENTIAL_SOURCE=env`，所以檔案和子程序繼承到的變數都改變不了它。`mcp-hook-parity.test.mjs` 斷言兩邊發出的 URL、key 和身份一致。

**workspace peer**（家族 A 各 harness 均適用；agent-plugins 包既不派生 workspace peer，也不轉發任何 peer——它沒有能把 `recallPeerScope` 設成 `actor` 的旋鈕層，代理始終不發這個頭）：無顯式 peerId 且 `OPENVIKING_WORKSPACE_PEER≠0` 時由 workspace 派生，隨 `X-OpenViking-Actor-Peer` 傳送（服務端會對該頭校驗，含 `/` 或 `\` 返回 400）。派生規則由 `peer.source` 決定，**預設 `git`**：先取歸一化後的 `origin` URL，取不到回落到倉庫根路徑；不在倉庫中則什麼都不傳送，在那裡記下的內容進入使用者級空間 `viking://user/<you>/memories`。例如在 `/Users/x/Dev/OpenViking/examples/codex-memory-plugin` 下、origin 為 `git@github.com:volcengine/OpenViking.git` 時，peer 是 `github.com-volcengine-openviking`——任意子目錄、任意 worktree、任意機器、任意 clone 都是同一個值。`peer.source` 的讀取層為 env `OPENVIKING_PEER_SOURCE`、ovcli.conf `plugin.peerSource` / `plugin.<harness>.peerSource`、workspace 檔案的 `peer.source`；家族 A 的每個 harness 都會讀這幾層。

| `peer.source` | 展開為 | 得到的 peer |
|---|---|---|
| `git`（預設） | `["{git_remote}", "{git_root}"]` | 歸一化 origin → 倉庫根路徑；不在倉庫中則什麼都不傳送，預設一律不加字首 |
| `cwd` | `["{cwd}"]` | 舊行為，逐位元組等價：路徑中所有非字母數字字元替換成 `-`（`/Users/x/Dev/OpenViking` → `-Users-x-Dev-OpenViking`） |
| `none` | `[]` | 完全不發 peer；`OPENVIKING_WORKSPACE_PEER=0` 仍是同一含義 |
| 模板串（如 `"git-{git_remote}"`、`"team-{dir}"`） | 自身 | 自由形式；也可給一組模板（如 `["team-{dir}", "{cwd}"]`）按順序嘗試，變數為空的模板跳過、落到下一個 |

| 變數 | 取值 | 何時為空 |
|---|---|---|
| `{git_remote}` | 歸一化後的 `origin`，形如 `github.com-org-repo`；host 與 path 轉小寫，`.git` 字尾與 userinfo 一併丟棄，因此同一倉庫的 ssh / https 兩種寫法結果一致，且 URL 裡內嵌的 token 不可能進入 peer id | 非 git 倉庫，或未配 `origin` |
| `{git_root}` | 倉庫根路徑，按上述舊 sanitation 處理 | 不在 git 倉庫中。倉庫內某個子目錄放了標記檔案時，它仍然是倉庫自己的根，因此標記子目錄不會拆散預設 peer |
| `{cwd}` | 當前工作目錄，按上述舊 sanitation 處理 | 從不為空——它也不在任何預設鏈裡，裸路徑只有在你明確要求時才會成為 peer |
| `{dir}` | 工作區根目錄的目錄名：倉庫根，或放著 `.openviking/config.json` 的那個目錄 | 該目錄不是工作區 |
| `{harness}` | 當前 agent 的名字，與 User-Agent 裡那個一致 | 從不為空——但 MCP proxy 不參與推導（它的 cwd 不是可靠身份），只走 proxy 的讀路徑解析不出它 |

要讓一個不是倉庫的目錄擁有獨立 peer，在該目錄下建立 `.openviking/config.json`，寫上 `{"version": 1, "peer": {"id": "my-project"}}`，或者為它設定顯式的 `OPENVIKING_PEER_ID`。

**身份語義**：同一倉庫的所有 clone 共用一個 peer，專案記憶跟著專案走而非跟著 checkout 走。fork 的 `origin` 不同，因此預設就是另一個 peer；用 `gh pr checkout` 評審外部 PR 不改 `origin`，身份也就不受影響。派生是純檔案系統操作（`workspace-identity.mjs`），不起 `git` 子程序，因此能塞進最緊的 hook 預算，也能在 `git` 不在 `PATH` 上、或因 dubious ownership 拒絕該倉庫時照常工作。worktree 經 `commondir` 收斂回主倉庫，submodule 保留自己的身份，`$HOME` 與 `/` 永遠不會被當作 workspace 根。

**遷移**（無需使用者操作）：舊 peer id 是 cwd 的純函式，客戶端隨時可以本地重算，召回仍能覆蓋到寫在它名下的記憶。預設 `peer_scope: "all"` 下，服務端本就有的跨 peer 掃描零成本地把它包含在內；`peer_scope: "actor"` 下外掛會另外向該 peer 發一次召回並拼接結果。此事沒有截止期限。

openclaw 的 peer 由 `peer_role`/`peer_prefix` 推導（`peer_role=sender` 時需保證 sender 資訊可用，否則工具呼叫報錯；舊值 `person` 作為別名相容）；hermes 的 peer 就是 `OPENVIKING_AGENT`（預設 `hermes`）。

### 3.1.4 配置體系分層

| 配置層 | 生效範圍 | 備註 |
|---|---|---|
| env `OPENVIKING_*` | 各家族見上；行為旋鈕見各檔案卡 | 唯一橫跨所有 JS 系的層 |
| workspace 層：每機登錄檔 `~/.openviking/workspaces/<slot>.json` > `<repo-root>/.openviking/config.local.json`（私有，gitignore）> `<repo-root>/.openviking/config.json`（提交進倉庫、團隊共享） | claude-code / codex / cursor / trae / trae-cn / zcode / opencode / dsh / pi | schema v1，必須寫 `version: 1`，宣告其他版本的檔案會被跳過並告警。可用 key：`peer.source`、`peer.id`、`recall.{enabled,peer_scope,dedup_turns,max_items,score_threshold}`、`capture.{enabled,commit_token_threshold}`、`bypass.session_patterns`、`labels`。列表類跨層取並集，首元素寫 `"!reset"` 可清空繼承來的內容；不認識的 key 原樣保留但不生效。hook 是非互動的，這些檔案因此無提示直接信任，換來的是結構性的拒絕：連線與憑據類 key（`url`、`api_key`、`account`、`user`、`extra_headers` 等）一律剝離並告警，這些檔案裡的 `${VAR}` 永不展開。登錄檔目前沒有寫入方：條目由人工建立，`ov-memory-doctor` 會列印該放到哪個 slot 路徑。提交進倉庫的檔案關掉了什麼，由 `ov-memory-doctor` 播報而不是攔截 |
| ovcli.conf `plugin` 段（共享標量，可被 `plugin.<harness>` 物件覆蓋） | claude-code / codex / cursor / trae / trae-cn / zcode / opencode / dsh / pi | 每個 harness 鍵兩種寫法都認——`claude_code` 或 `claude-code`、`trae_cn` 或 `trae-cn`。注意：`ov config add/edit` 會以 Rust Config 結構重寫整個檔案，從而丟棄其不識別的 `plugin` 段；而 `ov config switch` 為位元組複製，不受影響 |
| ov.conf harness 段（`<harness>.*`，legacy） | 每個 harness 讀與自己同名的那段 | 憑據欄位（`apiKey`/`accountId`/`userId`/`peerId`）與調優旋鈕都按呼叫方 harness 取自己的段。兩種寫法指向同一段 |
| harness 自有配置檔案 | dsh cordis patch（會被 `plugin` 段壓過）、openclaw `openclaw.json`、hermes `config.yaml`+`.env` | |

**配置項生效範圍速查**（這些旋鈕只在列出的 harness 上生效）：

- `OPENVIKING_COMMIT_TURN_THRESHOLD`：僅 cursor（trae×2/zcode 每 Stop 必 commit，不走該閾值）。
- `OPENVIKING_WRITE_PATH_ASYNC`：claude-code / codex / zcode。
- 召回再摘要相關（`OPENVIKING_RECALL_COMPRESS` / `OPENVIKING_RECALL_REWRITE` 及配套項）：claude-code / codex（服務端 `rewrite` 引數本身對所有呼叫方可用，[§3.2.5](#_3-2-5-召回再摘要)）。
- `OPENVIKING_RECALL_DEDUP_TURNS`、`OPENVIKING_RECALL_QUERY_EXPANSION`、`OPENVIKING_PEER_SOURCE`、`OPENVIKING_SKILL_CATALOG`、`OPENVIKING_SKILL_CATALOG_TOKEN_BUDGET`、workspace 配置檔案與 ovcli.conf `plugin` 段：經共享載入器解析配置的每個 harness——claude-code / codex / cursor / trae / trae-cn / zcode / opencode / dsh / pi；openclaw 與 hermes 各有自己的配置體系。

## 3.2 自動召回與注入

### 3.2.1 機制底座：一條共享管線，兩條服務端路徑

JS 系 harness 的召回邏輯均由 `recall-core.mjs` 中的三級降級鏈處理：

1. **context face**：呼叫 `POST /api/v1/search/search`，引數設定為 `mode:"context"` 且 `purpose:"coding"`。其核心設計原則為"只宣告意圖，機制交服務端"：對於 `quotas`/`max_tokens`/`query_expansion`/`rewrite_max_bullets` 等引數，僅在使用者顯式配置時（帶有 configured 哨兵欄位）才會傳送，否則直接採用服務端的預設設定。
2. **legacy `/recall`**：若 context face 請求返回 400/422 錯誤，且響應報文包含 `extra`/`mode`/`unexpected` 等特徵欄位，則判定對接了舊版服務端。此時會在本地寫入 6 小時的負快取（路徑為 `~/.openviking/state/context-face.json`，該檔案全機共享，一旦被任一 harness 標記，同機所有 JS 系 harness 均會跳過 context face 階段）。隨後降級呼叫已棄用的 `/api/v1/search/recall` 介面；若 `peer_scope` 被拒，則去掉該引數重試一次。
3. **raw find 兜底**：併發請求 `viking://~/memories` 與 `viking://~/skills`，呼叫兩次 `POST /search/find`（注意：resources 被刻意排除在自動召回之外，資源類文件由模型主動呼叫 `search` 獲取）。客戶端收到結果後進行本地重排（權重規則為：leaf +0.12 / 時間意圖 +0.10 / 偏好意圖 +0.08 / 詞面重疊 ≤0.2）、去重，最後按客戶端 token 預算裝填。`recallTokenBudget`、`recallMaxContentChars` 與 `recallPreferAbstract` 三個旋鈕只在這一級生效；而在 context face 下，注入預算由服務端 `max_tokens`（預設 1600）決定。

服務端在處理 session_id 時，分為兩條截然不同的執行路徑：

- **路徑 A：`mode="context"`**（適用於 context face 與 `/recall` preset）。此路徑負責 query expansion 與跨輪去重臺帳。expansion 設有三重閘門：`retrieval.enable_intent` 需開啟（預設 true） → 會話必須已物化（即 `messages.jsonl` 檔案存在） → `latest_archive_overview` 或 `current_messages` 不能為空。擴寫後原 query 永遠排第一，追加的 planned queries 上限為 3。臺帳（`.recall_log.json`）按 `dedup_turns` 冷卻已發正文的 URI；若"當輪只發了 URI 沒發正文"，該記錄則不參與冷卻；digest 判定 no_relevant 時亦不記帳。
- **路徑 B：`mode="list"`**（不寫 mode 時的預設行為）。此路徑下，IntentAnalyzer 會整體替換 typed_queries（原 query 不保證保留），無臺帳、無原-query 保底。實際落在這條路徑上的呼叫方包括：codex 的第二級降級 `searchScope`、hermes 的 `viking_search(mode="deep")` 以及 prefetch 的首選路徑。儘管它們帶了 session_id，但拿不到 context 面的 expansion 與去重機制。

**`dedup_turns` 的三點說明**：① 服務端 context 面的預設值是 **0**，常見的"5"實則源自客戶端 `recall-core.mjs` 兜底與 `/recall` preset（後者僅當帶 session_id）——不經共享庫直接打 API 的第三方即使帶了 session_id，也要顯式發 `dedup_turns` 才有跨輪去重；② "turn"的計數單位是訊息條數而非對話輪（`_resolve_turn` 用 `total_message_count`），對同時推 user+assistant 的 harness，預設 5 ≈ 1-2 個真實對話輪；③ 注意：`autoCapture=0` 且 `autoRecall=1` 時訊息數恆 0 → 臺帳時鐘不走 → 已發過正文的 URI 在本會話內持續冷卻；可用 `OPENVIKING_RECALL_DEDUP_TURNS=0` 關閉去重。

### 3.2.2 判定矩陣

| harness | 觸發點 | query 構造 | session_id | 服務端路徑 | 注入格式 / 位置 | 再摘要（客戶端）* |
|---|---|---|---|---|---|---|
| claude-code | 每輪 `UserPromptSubmit` | prompt 原文 trim | ✅ `cc-` | A（context face） | `<openviking-context>` → `hookSpecificOutput.additionalContext` | ✅ 本地/服務端（預設 auto，[§3.2.5](#_3-2-5-召回再摘要)） |
| codex / trae-cli | 每輪 `UserPromptSubmit`（整 hook 120s 硬截止） | prompt 原文 | ✅ `cx-`（確定性推導，不讀 state） | A；二級降級 searchScope 落入 B | `<openviking-context source="auto-recall" format="digest">` | ✅ 本地 `codex exec`（[§3.2.5](#_3-2-5-召回再摘要)） |
| cursor | `beforeSubmitPrompt` | prompt 原文；基於事件 id 與 500ms 視窗去重，同 promptHash 複用快取塊 | ✅ `cu-` | A | `additional_context` | ❌ |
| trae / trae-cn | `UserPromptSubmit` | 剝離歷史注入塊後的 prompt（只認 `input.prompt`） | ✅ `tr-`/`trcn-` | A | `additionalContext` | ❌ |
| zcode | `UserPromptSubmit` | 剝離三類注入塊（含 `<system-reminder>`） | ✅ `zc-` | A | `additionalContext`（嚴格 JSON） | ❌ |
| opencode | 每條 `chat.message` 中的 user 訊息 | 拼接非 synthetic text part；若正文已含 `<openviking-context` 則跳過本輪召回 | ✅ `oc-` | A（timeoutMs=30000） | 合成 synthetic part 並 `unshift` 到 parts 最前 | ❌ |
| dsh | `agent/pre-step` waterfall（先 await next 再 append） | claimed batch 全部訊息（過濾自身注入的內容） | ✅ `dsh-` | A | 藉由 `createUserMessage` append 到 `decision.messages` 尾部（source: plugin/openviking-memory） | ❌ |
| pi | `before_agent_start` 階段排隊；在 `context` 事件內檢索（當前輪 prompt 拿當前輪記憶） | prompt 原文 | ✅ `pi-`（會話未建立時不帶） | A | 前置到最後一條真實 user 訊息（通過 `<openviking-context` 冪等檢測） | ❌ |
| openclaw | context-engine transformContext assemble（設有 7 道 passthrough 門） | 最後一條 user 訊息純 text，清洗後截 4000 字元 | ❌（`/find` 無該欄位） | `/find` | 以 `<relevant-memories>` + `Source: openviking-auto-recall` 格式前置進最後一條 user 訊息 | ❌ |
| hermes | 每輪 API 呼叫前同步執行 `prefetch` | 原始使用者輸入，雙層剝 skill 腳手架；<5 字元跳過 | 部分攜帶（僅 `search/search` 首選路徑，落 B；降級 `/find` 時不帶） | B / find | `<memory-context>` fenced 塊追加到當輪 user 訊息（只進 API 請求體，不寫回持久化） | ❌ |

\* 同 [§1.2](#_1-2-自動-hook-面-通過-harness-自動實現)：此列的"再摘要"特指客戶端本地壓縮，而服務端 digest 對所有呼叫方均可用（[§3.2.5](#_3-2-5-召回再摘要)）。ov CLI 無自動召回，不在本表。

### 3.2.3 profile / 開場注入

- **實現**：`profile-inject.mjs`——讀 `viking://user/<space>/memories/profile.md` 全文 + `preferences/`、`entities/` 遞迴清單（abs_limit=512）。預算估算引入 CJK 感知（≥U+3000 記 1.5 token/字，其餘 chars/4）；profile 佔一半預算，超限則採用"頭 8 行 + 尾部"的中段省略；清單超限時會再撤掉幾條，直到放得下 `... +N more` 提示。
- **誰注入、何時、預算**：claude-code（SessionStart 全部 source，10000）；codex（SessionStart startup/clear/resume，10000）；cursor/trae×2/zcode（SessionStart，10000，2s 去抖）；opencode（每會話首條 chat.message 一次，10000，程序內 Set 去重，subagent 會話跳過；注意開場注入每會話只嘗試一次，失敗後本程序內不重試）；dsh（每 session 投一次 `profileDelivered`，10000；compaction 之後不重投）；pi（進 systemPrompt，每個 prompt 重拼，10000 常駐）。openclaw、hermes 無 profile 注入。
- **skill 清單**（`<available-skills>`）：由 `buildProfileBlock()` 追加在同一個 `<openviking-context>` 信封裡，排在 `<user-profile>` 和 `<available-memories>` 之後，所以上面每個 harness 都會隨 profile 一起注入它（codex 覆蓋 trae-cli）。資料來自一次 `GET /api/v1/skills?node_limit=200`，包含使用者自己的 skill 和帳戶共享的 `viking://agent/skills`：自己的排在前面，和自己某個 skill 同名的共享 skill 不再列出。每條描述按同一套 CJK 感知估算截到約 40 token，描述裡出現的信封標籤會被轉義。
  - **預算與開關**：`skillCatalogTokenBudget`（預設 1200 token，取值 0-20000，env `OPENVIKING_SKILL_CATALOG_TOKEN_BUDGET`）是這一塊自己的預算，不佔 `profileTokenBudget`。`skillCatalog`（預設 true，env `OPENVIKING_SKILL_CATALOG`）控制開關，預算設為 0 同樣關閉。兩者都在 `config-schema.mjs` 中宣告，因此和其他旋鈕一樣，也能在 ovcli.conf 的 `plugin` / `plugin.<harness>` 段裡設定。
  - **降級**：放得下時每條都帶描述；放不下就只列名稱，名稱也列不全時以 `... +N more, search OpenViking skills to find the rest` 收尾；連一個名稱都放不下時，只剩一行 `<available-skills>N OpenViking skills; search OpenViking skills to find them.</available-skills>`。沒有任何 skill，或服務端沒有 `GET /api/v1/skills` 時，整塊省略。
  - **總量上限**：`sessionStartMaxBytes`（env `OPENVIKING_SESSION_START_MAX_BYTES`）按 UTF-8 位元組限制整個會話開場注入：claude-code 和 codex 為 9500，因為這兩個宿主會把超過約 10,000 字元或位元組的 hook 上下文存成檔案、只給模型看預覽；zcode 為 20000，因為它會丟棄超過 32 KB 的 stdout；其餘不設上限。在上限內各項預算相應收縮，仍放不下時先去掉記憶索引，再去掉 skill 清單。resume/compact 時會話歸檔最多佔一半，截斷處附 `viking://~/sessions/<id>/history/` 指標；resume 時 claude-code 和 codex 若 profile 塊與本會話上次注入的相同就不再重複注入。
  - **示例**（claude-code，`source="startup"`）：
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
- **archive 注入**（resume 場景把上次歸檔摘要拉回來）：claude-code（source=resume/compact，`token_budget=32000`）；codex（resume 且本地 ovSessionId 已清時，32000/截 6000 字元）；opencode（開場注入 B 部分，32000）；pi 非 takeover 模式（32000）。
- **repo 上下文注入**：opencode 獨有——通過 `experimental.chat.system.transform` 把已索引倉庫列表放進 system prompt。

### 3.2.4 超時與預算鏈

- 家族 A 客戶端推導：帶 rewrite → `max(timeoutMs, 45000)`；帶 expansion → `max(timeoutMs, 15000)`；對應服務端熔斷 5s（expansion）/30s（rewrite）——設計上讓客戶端預算覆蓋服務端各階段，防止客戶端提前 abort 丟掉整個響應。
- 實際值：cc 15s（hook 預算 60s）；codex 召回整 hook 120s 硬截止 + 壓縮子程序 110s；cursor/trae×2/zcode 15s（宿主 hook 預算 20s）；opencode 30s；dsh 15s（阻塞 pre-step）；pi 15s；openclaw 整個召回流程外層 5s 硬超時（500ms health precheck；預設 `recallPreferAbstract=false` 時每條 leaf 記憶多一次 read，預算內最多 1 find + 6 read + 1 health）；hermes 總預算 4s / 單請求 3s（可配）。
- 注入體預算：服務端 `max_tokens` 預設 1600（家族 A 預設不發、由服務端決定）；openclaw / hermes 用字元預算 4000（兩家都是"裝不下整條跳過"而非截斷）。

### 3.2.5 召回再摘要

**服務端實現（對所有呼叫方可用）**：context 檢索面（涵蓋 REST 的 `mode="context"` 與 legacy 的 `/recall`）支援傳入 `rewrite` 引數——可選值為 `false | true | "auto"`，預設為 `false`；並配套提供 `rewrite_max_bullets`（預設 6，1-20）。開啟後，服務端會用 `query_planner` 模型（`rewrite=true` 時未配置則回落主 `vlm`；`"auto"` 僅在顯式配置了 `query_planner` 時生效）把召回結果改寫成帶引用的 digest：`OpenViking memory digest:` 頭 + `- ` bullets，每條 ≤500 字元且必須引用一條本次命中的 `viking://` URI（無引用或引用越界的 bullet 被丟棄）；判定無相關記憶時輸出哨兵並清空注入塊（該輪不記入去重臺帳）。模型呼叫受 `retrieval.recall_rewrite_timeout_s=30s` 熔斷，超時回落未改寫的 rendered 塊（`rewrite.py:78-141`、`pipeline.py:122-130`、`search.py:195-196`）。

**客戶端側現狀**：

- **claude-code**：`recallRewrite` 四態 `off|client|server|auto`，預設 **auto**——先探測本地壓縮器是否可用（`claude --version` 探測，快取 7 天），若可用則在本地起 `claude -p --model sonnet --effort low --strict-mcp-config` 子程序壓縮（30s 超時，輸入 <1500 字不壓縮，digest 單條快取；子程序環境強制降級防遞迴；失敗回落未壓縮塊；URI 編輯距離吸附回真實 URI，修不回的整條丟棄）。若本地不可用，則下發 `rewrite:"auto"` 交服務端。這是唯一接入服務端 rewrite 的 harness。
- **codex**：布林 `recallCompress` 預設 **true**，完全依賴本地壓縮（不使用服務端 rewrite）：模型 profile 從 `~/.codex/models_cache.json` 讀，候選 `gpt-5.3-codex-spark` → `gpt-5.6-luna`，快取 7 天；命令 `codex --sandbox read-only --ask-for-approval never exec --ephemeral --ignore-user-config --skip-git-repo-check --output-last-message <tmp> -`，超時 110s；執行期失敗後同一會話內跳過壓縮、下次 SessionStart 自愈重測；輸出規範化截 4000 字元；壓縮關閉或失敗時用確定性 `fallbackDigest` 兜底。
- **其餘 harness**：均不傳送 `rewrite`、無本地壓縮，而是直接注入服務端返回的原始召回塊。直連 API 的第三方可自行傳 `rewrite` 獲得服務端 digest。

### 3.2.6 注入迴流防護

為防止注入內容被二次捕獲，注入時會加確定性包裝（`<openviking-context>` 等），捕獲時再機械剝離：capture-utils 的 `sanitizeCapturedText` 剝注入塊、digest 塊、後設資料圍欄與時間戳字首。各端的特殊處理包括：trae/zcode 用各自的 clean 函式（其中 zcode 剝三類注入塊）；openclaw 在 afterTurn 寫回與下輪 query 構造時各剝一次 `<relevant-memories>`；hermes 則更徹底，直接把三個召回類工具的 tool_call/result 從 sync batch 裡整條剔除（寫類工具保留）。

## 3.3 會話與 commit 生命週期

### 3.3.1 機制底座

- **寫入路徑**：JS 系統一通過 `batch-send.mjs` 處理（對應介面 `POST /messages/batch`，每批最多 100 條，與服務端的 `max_length=100` 限制保持一致；若遇 404/405 錯誤則降級為逐條傳送）。增量游標由各家自行實現（cc 按 transcript turn 序號計算，codex 機制相同；cursor 採用 `sha256(index+role+content)`；zcode 基於 rollout 的 `turn_id`；opencode 依賴事件流 Map；dsh 基於事件白名單；pi 依據 branch 條目水位；hermes 則按當前輪切片）。
- **commit 是客戶端觸發的**（詳見 [§2.3](#_2-3-服務端會話與-commit-語義)）：服務端預設不自動 commit。下表所有的"閾值/觸發"條件，均指客戶端邏輯。
- **keep_recent_count 差異**（即 commit 後給宿主留多少 live tail）：服務端預設值為 0。各家傳參如下：cc/codex 閾值提交傳 10；cursor、trae×2、zcode 發空 body `{}`，即傳 0（每次均為全量歸檔）；opencode 傳 10；dsh 傳 10；pi 在非 takeover 模式傳 10，takeover 模式傳 3（本地含義是"保留 3 個使用者輪"，而服務端按訊息條數解釋，實際保留更少）；openclaw 在 afterTurn 閾值觸發時傳 10，在 compact/reset/memory_store 操作時傳 0；hermes 恆定傳 0。
- **寫路徑 detach**（`async-writer.mjs`，cc/codex/zcode 的 Stop 預設開）：drain stdin → spawn detached worker → approve → write payload → unref（注：spawn 失敗時尚未 approve，回落同步恰好只輸出一次）。detached worker 自成程序組，不受終端訊號波及——這是保證 cc 在關閉鏈路時具有高可靠性、zcode 在按下 Ctrl+C 時不丟失寫入資料的關鍵機制。附帶效果：執行 detach 後，Stop 的 `appended N turn(s)` 提示將不再展示（設定 `OPENVIKING_WRITE_PATH_ASYNC=0` 可恢復該提示）。

### 3.3.2 常規 commit 觸發條件

| harness | 輪內閾值觸發 | 顯式/邊界觸發 | 壓縮觸發 |
|---|---|---|---|
| claude-code | Stop：`pending_tokens ≥ 20000`（讀服務端值），keep 10 | SessionEnd：無條件觸發；SubagentStop：無條件觸發（無閾值）；SessionStart：重放 pending | PreCompact：無條件觸發（同步執行，不 detach） |
| codex / trae-cli | Stop：同上，20000 / keep 10 | SessionEnd（Codex ≥ 0.145）：無條件觸發，先補齊 Stop 漏掉的輪次再 commit——父 hook 只寫 `.ended` 標記並 detach worker（Codex 預設給 1s，`timeout` 上限 3s）；SessionStart(startup\|clear)：兜底掃描，提交帶 `.ended` 標記或閒置超過 30min 的 state。trae-cli 若無 `SessionEnd` 則只走掃描 | PreCompact：全量 commit（發空 body `{}`），隨後置 `ovSessionId=null` |
| cursor | stop：`capturedSinceCommit ≥ 8`（按訊息條數計算，≈4 輪問答；純客戶端計數），keep 0 | sessionEnd：已註冊該事件（但實踐中不觸達，見 [§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣)） | preCompact：無條件觸發 |
| trae / trae-cn | 每個有內容的 Stop 都 commit（無閾值），keep 0 | — | 無（上游無 PreCompact 事件） |
| zcode | 同 trae（每 Stop 都 commit，keep 0；rollout 增量游標保守推進，若有漏掉的輪次，將在同會話的下個 Stop 補齊） | — | 無（上游無 PreCompact 事件） |
| opencode | `session.idle` 路徑：flush 執行後，需滿足 `pending_tokens ≥ 20000` 才 commit，keep 10 | `session.deleted` / `session.error`：強制 commit；dispose：強制 commit | 在 `experimental.session.compacting` 前與 `session.compacted` 後各觸發一次（即一次宿主壓縮 = 兩次 commit） |
| dsh | `turn/end`：`pending_tokens ≥ 20000`（30s 超時），keep 10 | teardown（見 [§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣)） | 無（不監聽 compaction 事件） |
| pi（takeover 預設開） | `onTurnSynced`：本地估算 `pendingTokens ≥ 30000` 且 `lastSeenUserTurns > 3` 時，執行 commitAndAdvance（keep 3；overview 15×2s 輪詢，拿不到則邊界不推進，但 pendingTokens 會清零，重新累計後重試） | 手動執行 `/viking commit` | `session_before_compact`（需 `firstKeptEntryId` 非空） |
| pi（takeover off） | syncBranch 執行後：服務端 `pending_tokens ≥ 20000`，keep 10 | `session_shutdown`：無條件 commit；手動執行 `/viking commit` | `session_before_compact`：無條件 commit |
| openclaw | afterTurn：`pending_tokens ≥ floor(tokenBudget × 0.5)`（ratio 預設 0.5，tokenBudget 預設 128000，即閾值 ~64000），wait=false，keep 10 | `before_reset`（執行 `/new` `/reset`）：wait=true，keep 0；`memory_store` 工具：wait=true，keep 0 | `compact()`：wait=true，keep 0（Phase2 輪詢上限 5 分鐘） |
| hermes | 無閾值 commit——觸發面全是會話邊界：`on_session_end`（drain 10s，drain 不淨則本次不 commit）、`on_session_switch`（涉及 `/new`、`/resume`、`/branch` 或壓縮 fork，非同步 drain 預算 65s）、gateway 快取驅逐；`/undo` 與原地壓縮不 commit。用冪等集合防二次 commit；keep 0 | atexit 兜底 | fork 型壓縮邊界 commit；原地壓縮不 commit |
| ov CLI | 無 | `ov session commit`；`ov add-memory` 第三步固定 commit | — |
| ingest | `pending ≥ 6000` 或 idle 5s，keep 0；backfill 在每個會話結束時執行 `commit_if_needed` | 退出時執行 `_flush_all()` | — |
| LangChain | `CommitPolicy.mode` 預設 `never`；`pending_tokens` 模式閾值為 8000；`always` 模式每次 record 均觸發 | 呼叫方自理 | — |

### 3.3.3 關閉方式 × harness 終局矩陣

圖例：**C** = 會 commit；**C\*** = 會 commit 但有前提（見注）；**—** = 不 commit（已 POST 的訊息仍留在服務端 live 區：不丟訊息本體，等待後續觸發歸檔與抽取）；**n/a** = 無此形態。所有行的服務端側行為一律為 **—**（[§2.3](#_2-3-服務端會話與-commit-語義)）。

| harness | 正常退出 | Ctrl+C | SIGTERM | SIGHUP/關終端/關視窗·tab | kill -9/崩潰 | 補救路徑 |
|---|---|---|---|---|---|---|
| claude-code | **C**（SessionEnd → detach 子程序 commit，使用者不等待） | **C** | **C** | **C**（detached worker 自成程序組，不受 SIGHUP 波及） | **—** | 下次 Stop 越閾值 / `/compact` / 下次 SessionEnd |
| codex | **C**（SessionEnd → detach worker commit，使用者不等待；需 Codex ≥ 0.145） | **C\*** | **—** | **—** | **—** | C\* 前提：連按兩次 `Ctrl-C` 屬於正常退出、會觸發 SessionEnd，單次不會。未 commit 的一律由下次 `SessionStart(startup\|clear)` 回收：標記仍在則 `ended_retry`，否則等 30min idle-TTL 掃描 |
| trae-cli | **—**（除非 TraeCode CLI 版本已帶 `SessionEnd`） | **—** | **—** | **—** | **—** | 下次 `SessionStart(startup\|clear)` 的 30min idle-TTL 掃描 |
| cursor | **—**（chat 關閉 / new-chat 無事件） | **—** | **—** | **—**（`sessionEnd` 已註冊且僅 window_close 觸發，但此時宿主已銷燬 shell-exec host，hook 在 spawn 前中止） | **—** | 結束在 <8 條訊息水位的會話，尾部依賴同一會話的後續訊息觸發 commit |
| trae / trae-cn | **—**（無 session-end 類事件） | **—** | **—** | **—** | **—** | 每 Stop 已 commit，最大待歸檔量 = 最後一輪 in-flight |
| zcode | **—**（無 session-end 類事件） | **C\*** | **—** | **—** | **—** | C\* 前提：Ctrl+C 時該輪 Stop 已觸發（detached worker 照常寫完）；每 Stop 已 commit，漏掉的輪次靠 rollout 游標在同一會話的下個 Stop 補回 |
| opencode | **C\***（≥1.15.11 的 `dispose` → `flushAll({commit:true})`，覆蓋全部四種關閉；<1.15.11 無該 hook → —） | **C\*** | **C\*** | **C\*** | **—** | C\* 前提：宿主 shutdown 預算 5s，單會話最壞 health 5s + batch 10s + commit 30s，多會話序列累加——超預算的 commit 會被截斷，且 pending queue 不覆蓋此場景（fetch 未 settle 不入隊）；重啟後 `init()` 不主動 flush 遺留會話 |
| dsh | **C**（Cordis teardown → 每 session 一次 3s 超時 commit，無閾值） | **C**（第一次；第二次 Ctrl+C 強退 → —） | **C** | **—**（無 SIGHUP 監聽） | **—** | teardown commit 與閾值 commit 共享同一條序列寫鏈，5s 程序 grace 內前方有慢請求時可能擠不進；web 形態關瀏覽器 tab 不觸發 teardown |
| pi（takeover 預設） | **—**（`session_shutdown` 全關閉方式都觸發且被 await，handler 持久化本地 takeover 狀態，不 commit） | **—** | **—** | **—** | **—** | 下次續跑攢滿 30000，或手動 `/viking commit` |
| pi（takeover off） | **C**（`await sync.commit()`，失敗入 pending 佇列） | **C** | **C** | **C** | **—** | — |
| openclaw | **—**（上游發 awaited `session_end(reason=shutdown\|restart)`，handler 快取 agentId 後返回，不觸發 commit；`gateway_stop` 未註冊；無訊號處理） | **—** | **—** | **—** | **—** | 顯式 `/new` `/reset` 與 ~50% 閾值；低於閾值的會話依賴這兩條路徑歸檔 |
| hermes | **C**（atexit `_run_cleanup` → flush 10s → on_session_end） | **C**（互動與非互動最終都走 atexit） | **C**（`_signal_handler`，grace 預設 1.5s → 乾淨退出 → atexit） | **C**（SIGHUP 同 SIGTERM 路徑） | **—**（atexit 不執行） | drain 不淨時本次不 commit（避擴音交半截資料）；退出看門狗 30s 終止慢 commit |
| ov CLI | n/a（一次性命令） | n/a | n/a | n/a | n/a | 無 pending queue；命令失敗重跑即可 |
| ingest | **C**（`finally _flush_all`） | **C**（SIGINT → stop） | **C** | **—**（無 SIGHUP handler） | **—** | 唯一有崩潰恢復的寫路徑：`needs_commit` 持久化在游標庫，下次執行 reconcile 補 commit |
| LangChain / Open WebUI / Agent Plugins / 通用 MCP | **—**（無會話生命週期掛鉤；MCP 代理退出時的 `DELETE /mcp` 只釋放協議會話，與記憶 commit 無關） | — | — | — | — | LangChain 靠呼叫方 `close()`；程序內 pending-commit 集合隨程序消失 |

**三點閱讀提示**：

1. 正常退出即 commit 的有五家：claude-code、opencode(≥1.15.11)、dsh、pi(takeover off)、hermes；其餘各家均依賴表中"補救路徑"列的回收機制。
2. kill -9 場景所有整合都不觸發 commit——已提交的訊息保留在服務端 live 區，後續同一會話再觸發 commit 時一併歸檔；服務端提供 per-session idle 兜底能力（[§2.3](#_2-3-服務端會話與-commit-語義)），當前外掛預設不下發該 policy。
3. 每輪必 commit 的 trae×2 / zcode 關閉語義最簡單（即最大待歸檔量 = 最後一個未走到 Stop 的回合），代價是每個 Stop 都觸發一次全量歸檔 + 記憶抽取（keep 0）。

### 3.3.4 pending queue / 離線補償對照

| harness | 機制 | 要點 |
|---|---|---|
| cc / codex / cursor / trae×2 / zcode / opencode / dsh / pi | 磁碟佇列 `~/.openviking/pending`（0700/0600） | 僅可重試的失敗入隊（4xx 含 401/403 判為不可重試，不入隊，debug 日誌可見）；重放在會話啟動時執行：≤50 條/次、≤3 次/條、TTL 7 天；`.processing` 原子認領，10min 陳舊回收；addMessage 失敗即 break 保序 |
| openclaw | 無本地佇列 | addSessionMessage 失敗被 catch，該輪訊息不重放 |
| hermes | 程序內 daemon 執行緒佇列 | drain 有預算（10s/65s）；不落盤 |
| LangChain | 程序內 `_pending_commit_sessions` 集合 | commit 失敗下次 record 自動重試；不落盤。部分成功時拋 `OpenVikingPartialWriteError`（攜帶 `messages_written`、`input_messages_consumed`、`context_attached`，呼叫方可按位置切片重試字尾）——全部整合裡唯一的部分成功上報協議 |
| ingest | SQLite 游標庫 + 單例項鎖 | append 前持久化意圖，崩潰後 reconcile 按服務端訊息數判定該批是否落地——唯一有崩潰恢復語義的寫路徑 |

### 3.3.5 subagent 會話對照

| harness | 處理方式 |
|---|---|
| claude-code | 隔離最完整：SubagentStart 派生 `cc-<sid>__subagent-<agent_id>` 獨立會話，SubagentStop 讀 subagent transcript 推送後無條件 commit 並清 state |
| codex / trae-cli | 不單獨建會話：subagent 輸出（`agent_message` / `sub_agent_activity`）摺疊進主會話的 assistant/tool part |
| opencode | `oc-<parent>__subagent-<child>` 掛在父名稱空間下；開場注入跳過 subagent（召回不跳過）；ID 派生依賴事件順序——`chat.message` 先於 `session.created` 到達時會丟 `__subagent-` 字尾 |
| dsh | 每個 subagent = 獨立 `dsh-<id>` 會話，父子關係不保留；N 個 subagent = N 份 profile 注入 + N 個獨立會話 |
| hermes | `delegate_task` 傳 `skip_memory=True` → subagent 不接 OV（無會話/召回/工具面）；子任務產出不回灌 |
| cursor / trae×2 / zcode / pi / openclaw | 無 subagent 處理（有獨立會話 id 就各自成會話，否則混入主會話；openclaw 可用 `bypassSessionPatterns` 遮蔽） |
| ingest | claude_code 介面卡跳過 `isSidechain` / `isMeta` 記錄——subagent 對話不入庫 |

## 3.4 壓縮 / compaction 接管

### 3.4.1 判定矩陣

| harness | 對宿主壓縮的姿態 | 壓縮前動作 | 壓縮後動作 |
|---|---|---|---|
| claude-code | 不接管 | PreCompact 同步 commit（唯一不 detach 的寫路徑，因為 CC 隨後立刻重寫 transcript） | `source="compact"` 的 SessionStart 會把 OV 的 `latest_archive_overview` + ≤5 條 abstracts 重新注回 |
| codex / trae-cli | 不接管 | PreCompact 補齊未捕獲輪次 → 全量 commit → `ovSessionId=null`（補齊不全時不 commit，留待重試）；無 PostCompact 接線，依靠 Stop 的轉錄收縮做防禦性糾偏 | resume 時注入 archive digest |
| cursor / trae×2 / zcode | 不接管 | cursor：preCompact 無條件 commit（trae×2/zcode 上游無該事件） | — |
| opencode | 不接管 | compacting 前 flush+commit | `session.compacted` 觸發後再 flush+commit（共兩次） |
| dsh | 不感知（不監聽 compaction 事件；注入走 pre-step user 訊息，隨宿主壓縮一起收縮，profile 不重投） | — | — |
| pi | **takeover 雙層接管**（預設開，[§3.4.2](#_3-4-2-pi-takeover)） | `session_before_compact`：flush → commit → pollOverview。成功則返回自定義 compaction 摘要覆蓋 pi 的；失敗則 fail-open 回退到 pi 預設壓縮 | 成功後 resetBoundary |
| openclaw | **全接管**：`ownsCompaction: true`，宿主不再跑自己的摘要（[§3.4.3](#_3-4-3-openclaw-contextengine)） | `compact()` = commit(wait=true, keep 0) → 讀回 overview 當 summary | 主 assemble 用 `[Session History Summary]` 重建上下文 |
| hermes | 不接管（`on_pre_compress` 介面預留，當前不參與壓縮摘要） | fork 型壓縮邊界會觸發舊會話 commit；原地壓縮不動 | — |

### 3.4.2 pi takeover

- 接管面是 `context` 事件的 messages 改寫，不接管 pi 的歷史儲存。觸發是 token 壓力（30000 + 保留 3 輪），而非 pi 的壓縮事件。
- 替換動作：先定位邊界，再把邊界前的全部訊息替換成一條合成 user 訊息 `[OpenViking Session Context]`。其中 overview 按 3000 token 截斷；timestamp 取保留首條 -1，以穩定 provider payload 吃 prompt cache。
- 資料來源是 `GET /sessions/{id}/context` 的 `latest_archive_overview`（輪詢 15×2s）；狀態持久化在 pi 自己的 branch custom entry `ov-takeover`。
- 失敗姿態 = fail-open 回完整歷史（指紋不匹配 / 歷史短於邊界 / overview 拿不到三重回退）。
- 與 pi 原生壓縮的關係：`session_before_compact` 成功時返回 `{compaction:{summary, firstKeptEntryId, …, details:{source:"openviking"}}}` 覆蓋 pi 摘要；缺 `firstKeptEntryId` 時走 pi 預設壓縮。

### 3.4.3 openclaw ContextEngine

- 實現宿主 `ContextEngine` 介面，`assemble()` 分兩個分支：transformContext（只做召回前置注入，5 道 passthrough 守衛）與 main-assemble（`getSessionContext(tokenBudget)` → 用服務端返回替換宿主 live 歷史，四層預算切分，3 道 passthrough 保護 + provider 訊息 sanitize 管線）。
- `compact()` = `commit(wait=true, keep 0)`（500ms 輪詢，Phase2 上限 5 分鐘）→ `latest_archive_overview` 當 summary、`archive_uri` 末段當 `firstKeptEntryId`。`customInstructions`/`compactionTarget` 保留介面，當前不參與壓縮產物。
- `ingest()/ingestBatch()` 是刻意 no-op，寫入全走 `afterTurn`。
- 有歸檔時額外注入 20 行 "Session Context Guide" systemPromptAddition，指示模型在說"沒有資訊"之前先重讀摘要，並用 `ov_archive_search` 嘗試至少 2 組關鍵詞。

### 3.4.4 pi 與 openclaw 接管方式對照

| 維度 | pi takeover | openclaw ContextEngine |
|---|---|---|
| 宿主契約 | 一個 context 鉤子的 messages 改寫 | 註冊 ContextEngine，`ownsCompaction: true` |
| 歷史真相源 | 仍是 pi 本地 branch | OV 服務端 getSessionContext |
| 觸發 | 客戶端 token 閾值 30000 + 保留 3 輪 | 宿主呼叫 assemble/compact |
| 壓縮產物 | 一條合成 user 訊息（3000 token 截斷） | 重建後的整個 messages 陣列 + compaction summary |
| 失敗姿態 | fail-open 回完整歷史 | passthrough 回宿主 live 訊息 |
| 召回與 session | context face 帶 session_id | `/find` 不帶（expansion/臺帳不參與） |

## 3.5 寫入與刪除的型別邊界

### 3.5.1 寫入邊界

MCP `write` / REST `content/write` 的三道 guard（`content_write.py`）：可寫域限 `viking://resources|user|agent`；新建副檔名需符合白名單 `.md .txt .json .yaml .yml .toml .py .js .ts`；使用者根下 `skills/ peers/ privacy/ sessions/` 四個託管子樹只讀（`_USER_MANAGED_SUBTREES`）。已存在的 `.abstract.md/.overview.md` sidecar 可以改正文，但公共寫入 API 不能建立它們。

### 3.5.2 刪除邊界

**第一檔：服務端通用防線（所有刪除入口共享）**。`VikingFS.rm` 第一句 `_ensure_delete_access`（`_access.py:182-229`）實施 5 道檢查：名稱空間可訪問性；使用者刪除進行中 → FailedPrecondition；actor-peer 隱藏檢視 → PermissionDenied；名稱空間根保護：裸 `viking://`、`viking://user` 根、`viking://agent` 根一律拒刪；非 ROOT 刪 `viking://temp` 拒。這一檔按名稱空間根設防，不區分 memory/resource/skill 型別——型別級差異由後三檔在客戶端實施。

**第二檔：客戶端零附加（MCP 面——dsh 與 pi 現在也走它——外加 langchain/ov rm）**。差異只在引數面：MCP `forget` 按給定 URI 刪除，`recursive` 預設 false，沒有任何分數門檻；dsh 與 pi 都已經把自己手寫的 `viking_forget` 撤下工具面（舊實現把 `recursive` 固定為 false，按 query 刪除還要求匹配分 >0.8），這一檔因此不再有客戶端附加。LangChain `viking_forget` 的 `recursive` 是模型可控引數（但預設不在工具面）；`ov rm -r` 則顯式開遞迴、無確認提示（TUI 的 `d` 鍵有 y/n 確認 + root/scope 目錄禁刪）。

**第三檔：memory-only 的兩個刪除面**。

- openclaw `memory_forget`：三條白名單正則只放行 `viking://user/[…/]memories`、`viking://user/<u>/peers/<p>/memories`、`viking://agent/[…/]memories`；顯式 uri 不匹配直接拒絕；搜尋路徑候選先過同一 guard，且只有在候選唯一且 score≥0.85 時才自動刪，否則列出候選讓 agent 指名；底層 URL 固定 `recursive=false`。
- hermes `viking_forget`：六道順序校驗——非 str / 空拒；scheme≠viking 拒；帶 query/fragment 拒；目錄或非 `.md` 結尾拒；必須命中 4 種 memories 路徑形狀之一，且 `memories` 段後至少還有 2 段（不刪除 `memories/` 與分類目錄本身）；檔名不能是 `.abstract.md/.overview.md`。

**第四檔：預設不提供刪除（LangChain / Open WebUI）**。LangChain `viking_forget` 需配置 `profile="admin"` 或 `allow_forget=True` 才加入工具面；Open WebUI 則完全不提供刪除工具。

**skill 的增刪邊界**：新增入口是 MCP `add_skill`、openclaw `add_skill`（預設開）、`ov add-skill` 與 REST；`add_resource` 拒絕 skill URI，MCP `write` 拒絕使用者自己的 `skills/` 子樹（`_USER_MANAGED_SUBTREES`）；`viking://agent/skills` 下的 `write` 目前沒有攔截，但會繞過 skill 安裝流程。對 skill 完全只讀（不增不刪）的刪除面是 openclaw `memory_forget` 與 hermes `viking_forget`。MCP `forget`、dsh、pi、`ov rm` 能刪掉 skill 目錄，因為刪除路徑不檢查該集合，但只有 `ov skills remove` 和 REST `DELETE /api/v1/skills/{name}` 會同時清理該 skill 的 privacy 配置。

## 3.6 降級與容錯

### 3.6.1 判定矩陣

| harness | 服務端不可達時 | 負快取 | HTTP 重試 | 失敗阻塞宿主 |
|---|---|---|---|---|
| claude-code | 各 hook catch→approve，不阻塞；session-start 時連 pending 重放都跳過 | context-face 6h + host-cli 探測 7d + health 5s | 無（靠 pending 重放）；peer_scope 降級 1 次；batch→逐條 | 否（uri-guard deny 是設計意圖） |
| codex / trae-cli | 各 hook catch→noop | context-face 6h + 壓縮器 runtime_failed（至下次啟動） | 同上（靠 pending 重放，SessionStart 觸發） | 否 |
| cursor/trae×2/zcode | fetch 吞成 status:0，catch 返回空注入；鎖 5s 拿不到則靜默跳過 | context-face 6h（服務端整體不可達時無負快取，每輪等滿 15s） | 無 | 否 |
| opencode | 各路徑 catch→WARN；`event`/`dispose` hook 無 try/catch（不可重試的 commit 失敗會冒泡宿主） | 僅 context-face 6h；`/health` 無快取（每輪一次往返） | 無同步重試；MCP 代理 401/403、400/404 各一次 | 基本否（event/dispose 例外） |
| dsh | client 全吞異常；`ensureState` 失敗不快取（服務端不可達時每 pre-step 兩次 health 各 5s） | context-face 6h + user-space 快取程序內不過期 | 無；pending 跨程序重放 3 次 | 是（pre-step 序列 profile+recall；session/flush 阻塞） |
| pi | health 失敗時 start() 提前返回，本輪也不註冊工具，此後每 prompt 靜默重試連線；`/mcp` 握手單獨失敗（401/403、超時、server 無 `/mcp`）不影響啟動：召回、同步、takeover 照常，狀態列顯示 `tools ✗`，`/viking` 列印完整錯誤 | context-face 6h；握手沒有負快取，一直失敗就每輪重試一次，最多佔滿 5s 握手預算才輪到排隊召回 | hook 側無，只有 pending queue；傳輸失敗後丟棄當前 MCP 連線，下次呼叫重新連線；失敗的工具呼叫不會自動重放 | 部分（session_shutdown 被 await：takeover 近 0、非 takeover 最壞 30s，外加關閉 MCP 客戶端；turn_end 網路異常時逐條各等 10s） |
| openclaw | client 構造永不失敗；health 吞異常；召回 500ms precheck 失敗跳過 | 無負快取（每輪一次 500ms health 預檢） | 無（單次 fetch）；commit/afterTurn 的 Phase2 輪詢 | 否（`memory_store` 重拋例外；`compact()` 最長阻塞 5 分鐘） |
| hermes | `_client=None` 即執行期負快取（本程序不再重試，除本地自啟 waiter 外） | 無獨立結構（`_client=None` 承擔） | trusted 補身份 1 次、sync 全新 client 1 次、多檔降級；commit 失敗不重試 | 否（後臺單 worker + 逐 provider try/except） |
| ov CLI | 多數 exit 1；`ov status` 表格模式始終退 0；`ov health` 即使 unhealthy 也退 0 | 無 | 僅閘道器 401 挑戰重試 1 次 | n/a（無宿主） |

### 3.6.2 通用超時

通用 HTTP 15000ms（下限 1000）；MCP 代理請求 15000ms、DELETE 固定 2000ms；跨程序鎖等待 5s、陳舊 60s；pending `.processing` 陳舊回收 10min。需注意 MCP 代理未註冊 SIGHUP（關終端不發 `DELETE /mcp`；但服務端 `stateless_http=True`，影響有限）。

## 3.7 附加 UX 對照

| harness | statusline | slash command | rule/skill | setup 嚮導 | 其他 |
|---|---|---|---|---|---|
| claude-code | ✅ 獨立程序寫 settings.json（段位豐富，1min TTL） | ✅ `/openviking-memory:ov`（服務狀態 + 身份 + 注入溯源） | 4 個 skill（`openviking-memory`、`openviking-skills`、`ov-experience-memory`、`ov-memory-doctor`） | ✅ 行式問答 | uri-guard 不受外掛開關門控 |
| codex / trae-cli | ❌ | ❌ | 與 claude-code 相同的 4 個 skill | ✅ | README.md Testing 一節的 live 檢查 |
| cursor | ❌ | ❌ | rule（alwaysApply）+ 2 個 skill（`openviking-memory`、`openviking-skills`） | ❌（共用安裝器 TUI） | 獨立 uri-guard，不受外掛開關控制 |
| trae/trae-cn | ❌ | ❌ | 無 | ❌ | — |
| zcode | ❌ | ❌ | 無 | ❌ | — |
| opencode | ❌（有 toast） | ❌ | 無（設計上不提供） | ✅ | — |
| dsh | ❌ | ❌ | 2 個 skill：`openviking-memory` 與 `openviking-skills`（獨立的 `ctx.skills` provider） | ❌ | `ctx.provide("openvikingMemory")` 供其他 Cordis 外掛二次開發 |
| pi | ✅ `ctx.ui.setStatus` | ✅ `/viking` `/viking commit` | 無 | ✅ | e2e-live.sh |
| openclaw | ❌ | ✅ 5 個（/add-resource /add-skill /ov-search /ov-query-config /ov-recall-trace） | 3 skill 隨外掛分發 | ✅（key 角色探測 + 版本相容檢查 + `status` 命令） | Gateway HTTP 路由做 recall trace 視覺化；feature-gate RPC；健康檢查指令碼 |
| hermes | ❌ | ❌ | 無 | ✅ curses 多層選單 | `hermes memory status`（含 env 覆蓋列表）；`hermes backup` 帶 ovcli.conf |
| ov CLI | ❌ | ❌（自身即命令） | 無 | ✅ TUI 嚮導 | 完整 help 系統（63 條 curated）；語言門禁；`ov tui` 全屏檔案瀏覽器（含終端內圖片預覽） |

---

# 4. Harness 檔案卡

每卡都是檢索入口，只寫該 harness 的獨有事實與差異，共享機制回鏈維度章。統一欄位：形態 / 能力亮點 / 行為要點 / 配置 / 維度索引。

## claude-code

- **整合文件**：[Claude Code 記憶外掛](./02-claude-code.md)
- **形態**：CC 外掛（marketplace），採用四合一架構：9 hook + MCP 代理（16 工具透傳）+ slash command + statusline + 4 個 skill（`openviking-memory`、`openviking-skills`、`ov-experience-memory`、`ov-memory-doctor`）。版本 0.6.1。
- **能力亮點**：hook 覆蓋最全的 harness——SessionStart(120s) / UserPromptSubmit(60s) / PostToolUse:Read(5s，預設關的 skill-experience) / PreToolUse:Read\|Glob\|Grep\|Edit\|Write\|Bash(5s，uri-guard：檔案工具的路徑是 `viking://` URI 時拒絕，針對 skill URI 的 Write/Edit 會被引導到 `add_skill`；Bash 命令帶 `viking://` URI 時附加提示) / Stop(45s) / PreCompact(30s) / SessionEnd(30s) / SubagentStart(10s) / SubagentStop(45s)；預設啟用召回再摘要（本地 `claude -p`，本地不可用時自動回落服務端 rewrite，[§3.2.5](#_3-2-5-召回再摘要)）；支援 SubagentStart/Stop 的完整子會話隔離（[§3.3.5](#_3-3-5-subagent-會話對照)）；statusline + slash + uri-guard；關閉鏈路除 kill -9 外全部 commit（[§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣)）。
- **行為要點**：session id 為 `cc-<CC session_id 原文>`，subagent 為 `…__subagent-<agent_id>`；Stop 閾值 commit 20000/keep 10，PreCompact 同步 commit；自動召回排除 resources（[§3.2.1](#_3-2-1-機制底座-一條共享管線-兩條服務端路徑)）；增量游標存於 `/tmp`（被系統清理後，同一會話會整段重推）。
- **配置**：env + ovcli.conf `plugin.claude_code` + ov.conf `claude_code`（[§3.1.4](#_3-1-4-配置體系分層)），約 70 個旋鈕；壓縮器命令與模型固定為 `claude`/`sonnet`/`low`/30s。
- **維度索引**：工具面 [§2.1](#_2-1-服務端-mcp-工具面) ｜召回 [§3.2](#_3-2-自動召回與注入) ｜commit [§3.3.2](#_3-3-2-常規-commit-觸發條件)/[§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣) ｜壓縮 [§3.4](#_3-4-壓縮-compaction-接管) ｜降級 [§3.6](#_3-6-降級與容錯) ｜UX [§3.7](#_3-7-附加-ux-對照)。

## codex

- **整合文件**：[Codex 記憶外掛](./04-codex.md)
- **形態**：Codex 外掛（marketplace），6 hook（SessionStart 70s / UserPromptSubmit 130s / Stop 30s / SessionEnd 3s / PreCompact 60s / PreToolUse:Bash 5s）+ MCP 代理 + 與 claude-code 相同的 4 個 skill。版本 0.10.1。
- **能力亮點**：本地召回壓縮管線（`codex exec`，[§3.2.5](#_3-2-5-召回再摘要)）；SessionEnd（Codex ≥ 0.145）在正常退出時補齊 Stop 漏掉的輪次並 commit，SessionStart 的兜底掃描回收那些沒觸發 SessionEnd 的退出所遺留的未歸檔訊息（[§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣)）；PreToolUse:Bash（uri-guard）放行帶 `viking://` URI 的 shell 命令，並附加提示，建議改用 OpenViking MCP 工具；Codex 通過 `apply_patch` 編輯檔案，輸入裡沒有路徑引數，因此 guard 不會拒絕任何呼叫。
- **行為要點**：session id 為 `cx-<safeId>`（確定性推導，不讀 state）；SessionEnd 只在正常退出、且 Codex 0.145+ 時觸發，訊號、崩潰、舊版本以及 `codex app-server` 延後的場景都落到掃描路徑；不使用磁碟 pending queue（離線靠游標不推進、下一輪重發補償，[§3.3.4](#_3-3-4-pending-queue-離線補償對照)）；idle-TTL 1800000ms、鎖等待 120000ms（env 配置）；Stop 與 SessionEnd 預設 detach（`appended N turn(s)` 提示預設不展示）；單會話 mkdir 鎖序列化 Stop worker、PreCompact、SessionEnd worker 與掃描。新增的 hook 在 Codex 側沒有信任記錄，升級後需在 `/hooks` 中批准這次升級新增的 hook（SessionEnd、PreToolUse）。
- **配置**：env + ovcli.conf `plugin.codex` + ov.conf `codex`；hooks 只用 `Authorization: Bearer` 認證（[§3.1.3](#_3-1-3-憑據體系)）。
- **維度索引**：工具面 [§2.1](#_2-1-服務端-mcp-工具面) ｜召回 [§3.2](#_3-2-自動召回與注入) ｜commit [§3.3.2](#_3-3-2-常規-commit-觸發條件)/[§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣) ｜降級 [§3.6](#_3-6-降級與容錯)。

## trae-cli（TraeCode CLI 2.0）

- **整合文件**：[TRAE 記憶整合](./13-trae.md)
- **形態**：TraeCode CLI 2.0 是 Codex 系 CLI（binary `traecli`，使用者配置 `~/.trae/traecli.toml`，TUI 支援 `/plugins` `/skills` `/mcp`）。OpenViking 經 **codex 外掛別名安裝**接入：`--harness trae-cli` 複用 codex 安裝流程，僅安裝引數（binary / home / 配置路徑）指向 TraeCode CLI。
- **能力面**：與 codex 同一套外掛——6 個已註冊 hook + MCP 代理 + 同樣的 4 個 skill、本地召回壓縮、idle-TTL commit 回收、resume archive 注入等，詳見 codex 檔案卡。若 TraeCode CLI 所基於的 Codex 版本沒有 `SessionEnd`，該 hook 會被忽略，關閉時的 commit 全部依賴 idle-TTL 掃描。
- **版本支援**：僅支援 TraeCode CLI 2.0。1.0 與 2.0 不是同一套 CLI，2.0 才是 Codex 系、才能走 codex 外掛別名安裝；早期面向 1.0 的獨立外掛（`~/.trae/cli/hooks.json` + `[mcp_servers."openviking-memory"]` 方案）已隨倉庫移除；安裝器仍保留 `--harness trae-cli --uninstall`，用於清掉舊安裝留在磁碟上的那份。
- **維度索引**：同 codex 卡。

## cursor

- **整合文件**：[Cursor 記憶整合](./12-cursor.md)
- **形態**：配置驅動（寫 `~/.cursor/hooks.json`+`mcp.json`）+ MCP 代理 + always-on rule + 2 個 skill（`openviking-memory`、`openviking-skills`）。6 hook：sessionStart(30s) / beforeSubmitPrompt(20s) / beforeReadFile(5s) / stop(30s) / preCompact(30s) / sessionEnd(30s)。相對 import 共享 lib（不 vendoring）。版本 0.5.0。
- **能力亮點**：beforeReadFile 上的 uri-guard 拒絕讀取 `viking://` 路徑（不受外掛開關控制）；shell 命令不做檢查，升級時會移除舊版本註冊的 beforeShellExecution 條目；rule 與兩個 skill 隨裝。
- **行為要點**：session id 為 `cu-<conversation_id>`；stop 每 8 條訊息 commit（`commitTurnThreshold=8`，訊息條數計數，keep 0）；`sessionEnd` 僅 window_close 觸發，且此時宿主已銷燬 shell-exec host，實踐中不執行（[§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣)）——結束在 <8 條訊息水位的會話，尾部依賴後續同會話訊息觸發歸檔（[§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣)）；服務端不可達時，每輪等滿 15s 召回超時。
- **配置**：env + ovcli.conf `plugin.cursor` + workspace 檔案（[§3.1.4](#_3-1-4-配置體系分層)）。
- **維度索引**：工具面 [§2.1](#_2-1-服務端-mcp-工具面) ｜召回 [§3.2](#_3-2-自動召回與注入) ｜commit [§3.3.2](#_3-3-2-常規-commit-觸發條件)/[§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣) ｜降級 [§3.6](#_3-6-降級與容錯)。

## trae / trae-cn（IDE 版）

- **整合文件**：[TRAE 記憶整合](./13-trae.md)
- **形態**：配置驅動（`~/.trae{,-cn}/hooks.json` + 平臺相關 mcp.json）+ MCP 代理。4 hook：SessionStart(30s) / UserPromptSubmit(20s) / PreToolUse:Read\|Glob\|Grep\|Bash\|RunCommand(5s) / Stop(30s)。PreToolUse 對路徑是 `viking://` URI 的 Read/Glob/Grep 直接拒絕；Bash/RunCommand 命令帶 `viking://` URI 時照常執行，並附加提示。相對 import 共享 lib。MCP server 名為 `openviking`。版本 0.5.0。
- **能力亮點**：行為最簡單直接的一檔——每個有內容的 Stop 都 commit（keep 0），關閉場景下最大待歸檔量只有最後一輪 in-flight（[§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣)）。
- **行為要點**：trae 與 trae-cn 的差異是 session id 字首 `tr-` / `trcn-` 與安裝路徑——同一份記憶在兩個客戶端落到兩組不同 session，跨客戶端共享靠服務端抽取後的記憶空間而非 session 複用；無 PreCompact/statusline/skill/subagent 處理。
- **配置**：env + ovcli.conf `plugin.trae` / `plugin.trae_cn` + workspace 文件。
- **維度索引**：工具面 [§2.1](#_2-1-服務端-mcp-工具面) ｜召回 [§3.2](#_3-2-自動召回與注入) ｜commit [§3.3.2](#_3-3-2-常規-commit-觸發條件)/[§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣)。

## zcode

- **整合文件**：[社群外掛 → ZCode](./08-community-plugins.md)
- **形態**：配置驅動（合併進 `~/.zcode/cli/config.json`，強制 `hooks.enabled=true`）+ MCP 代理。4 hook：SessionStart(30s) / UserPromptSubmit(20s) / PreToolUse:Read\|Glob\|Grep(5s) / Stop(30s)。自身不 vendoring 任何共享模組：安裝器按 cursor / trae 同樣的方式為它拼裝共享執行時。版本 0.5.0。
- **能力亮點**：以 rollout 檔案 `~/.zcode/cli/rollout/model-io-<sid>.jsonl` 為增量真相源（`lastTurnId` 差集補齊漏掉的 Stop）；Stop 預設 detach（Ctrl+C 不丟寫入）。
- **行為要點**：每 Stop commit（keep 0）；捕獲路徑僅剝離三類注入塊（不做額外文本清洗，[§3.2.6](#_3-2-6-注入迴流防護)）；首次捕獲會一次性讀取整個 rollout（長會話首裝時單次推送量大）。
- **配置**：env + ovcli.conf `plugin.zcode` + workspace 檔案；`OPENVIKING_WRITE_PATH_ASYNC` 對 zcode 生效。
- **維度索引**：工具面 [§2.1](#_2-1-服務端-mcp-工具面) ｜召回 [§3.2](#_3-2-自動召回與注入) ｜commit [§3.3.2](#_3-3-2-常規-commit-觸發條件)/[§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣)。

## kimicode

- **整合文件**：[社群外掛 → Kimi Code](./08-community-plugins.md)
- **形態**：原生 managed plugin，包含 7 個 hook 和 MCP 代理。安裝器在 `$KIMI_CODE_HOME/plugins/managed/openviking-memory` 下組裝一份自包含副本，不向倉庫提交 Kimi 的共享執行時副本。版本 0.5.0；已在 Kimi Code CLI 0.43.1 契約上驗證。
- **能力亮點**：`wire.jsonl` 作為穩定的增量回合來源；profile 在 prompt hook 上重試，直到首次成功。Stop、PreCompact 和 SessionEnd 可 detached；Interrupt 保持同步，所有 OpenViking 請求共用 2 秒總預算。
- **行為要點**：UserPromptSubmit 輸出原始上下文文本，不輸出 JSON 字串。只有在傳送成功或已持久化入隊後才推進增量游標。安裝時保留其他外掛記錄，不修改舊式 `config.toml` 或 `mcp.json`。
- **配置**：env + ovcli.conf `plugin.kimicode` + workspace 文件。
- **維度索引**：工具面 [§2.1](#_2-1-服務端-mcp-工具面) ｜召回 [§3.2](#_3-2-自動召回與注入) ｜commit [§3.3.2](#_3-3-2-常規-commit-觸發條件)/[§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣) ｜降級 [§3.6](#_3-6-降級與容錯)。

## opencode

- **整合文件**：[OpenCode 外掛](./10-opencode.md)
- **形態**：npm 外掛 `@openviking/opencode-plugin`，config hook 自注入 MCP 條目（工具帶 `openviking_` 字首）。8 個 plugin hook：config / event / tool.execute.before / tool.execute.after / experimental.chat.system.transform / chat.message / experimental.session.compacting / dispose。tool.execute.before 拒絕路徑是 `viking://` URI 的 read/glob/grep；bash 命令帶 `viking://` URI 時，tool.execute.after 在輸出末尾追加提示。版本 0.4.1。
- **能力亮點**：`dispose` hook 覆蓋全部四種常規關閉方式（宿主 ≥1.15.11）；repo 列表進 system prompt（[§3.2.3](#_3-2-3-profile-開場注入)）；宿主事件面最豐富（session.idle/compacted/deleted/error 各有語義）。
- **行為要點**：`commitTokenThreshold=20000`（取正數，0 回落預設值）；commit 超時 30000ms；一次宿主壓縮 = 兩次 commit；dispose 的 5s 宿主預算下，多會話慢 commit 可能被截斷，且 pending queue 不覆蓋此場景（[§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣)）；<1.15.11 無 dispose 時關閉不 commit；重啟後不主動 flush 遺留會話；開場注入每會話嘗試一次（[§3.2.3](#_3-2-3-profile-開場注入)）；`bypassSessionPatterns` 的目錄匹配在 opencode 上不適用（input 無 cwd）。
- **配置**：env + ovcli.conf `plugin.opencode` + workspace 文件。
- **維度索引**：工具面 [§2.1](#_2-1-服務端-mcp-工具面) ｜召回 [§3.2](#_3-2-自動召回與注入) ｜commit [§3.3.2](#_3-3-2-常規-commit-觸發條件)/[§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣) ｜subagent [§3.3.5](#_3-3-5-subagent-會話對照)。

## dsh（DeepSeek Harness）

- **形態**：唯一同程序 Cordis 原生外掛（`export function apply`），工具面就是服務端的 MCP 面，經 `@deepseek-ai/dsh-mcp-client` 與共享 stdio 代理接入（以 `mcp__openviking__*` 釋出），hook 側 REST 直連。6 事件：agent/session-start（emit）/ agent/pre-step（waterfall）/ session/event / session/flush / tools/pre-execute / tools/post-execute。版本 0.5.1。
- **能力亮點**：`ctx.provide("openvikingMemory")` 供其他 Cordis 外掛二次開發；pre-step 注入走 user 訊息，適配 DSH persona 的 `complete:true` 渲染模式。
- **行為要點**：統一安裝器已覆蓋 dsh，會詢問裝到哪個 profile（預設 `web`，可用 `--dsh-profile` 指定）；npm 是該外掛唯一的分發渠道，因此 github/tos 選擇對它不適用，除 `dev` 外的模式一律裝已釋出的包；`dev` 會先把 checkout 打包再裝——`dsh plugin` 轉發給 pnpm，link 一個原始碼目錄無法解析外掛 import 的 dsh peer；teardown commit 3s 無閾值，SIGHUP/二次 Ctrl+C 不觸發（[§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣)）；compaction 不感知（注入內容隨宿主壓縮收縮，profile 不重投）；subagent 各自獨立會話（[§3.3.5](#_3-3-5-subagent-會話對照)）；工具面即服務端自身的 MCP 面，經與其他整合同一個 stdio 代理接入、以 `mcp__openviking__*` 釋出，服務端升級即可增加工具而無需發版；代價是代理每個 profile 只起一個程序，因此工具呼叫帶的是程序級 actor peer、`remember` 也不綁當前會話（召回/捕獲/commit 仍按會話解析 peer）；另隨包附帶共享的 `openviking-memory` 與 `openviking-skills` 兩個 skill；uri-guard 先把工具名轉成小寫再匹配，tools/pre-execute 拒絕路徑是 `viking://` URI 的檔案工具（針對 skill URI 的 write/edit 會被引導到 `mcp__openviking__add_skill`），bash 命令帶 `viking://` URI 時由 tools/post-execute 附加提示（`form: "notice"`）。
- **配置**：env + ovcli.conf `plugin.dsh` + workspace 檔案 + cordis patch（行為旋鈕的最低層）；憑據是例外，patch 裡寫的 endpoint / key / account / user / peer 仍然壓過憑據鏈。
- **維度索引**：工具面 [§1.1](#_1-1-主動工具面-agentic-呼叫能力) ｜召回 [§3.2](#_3-2-自動召回與注入) ｜commit [§3.3.2](#_3-3-2-常規-commit-觸發條件)/[§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣) ｜降級 [§3.6](#_3-6-降級與容錯)。

## pi（pi Coding Agent Extension）

- **整合文件**：[pi Coding Agent 擴充](./11-pi.md)
- **形態**：pi 原生擴充（目錄裝載，jiti 直譯 TS）。擴充使用 `@modelcontextprotocol/client`，把服務端 `tools/list` 的每個描述符註冊成名為 `openviking_<tool>` 的 pi 工具，當前 16 個（[§2.1](#_2-1-服務端-mcp-工具面)）。擴充裡沒有任何工具目錄，服務端增刪工具，pi 下一次會話即跟上，不需要發外掛版本。召回、會話同步、profile 注入與 takeover 仍走 REST。9 事件 + `/viking` 命令；tool_call 攔截路徑是 `viking://` URI 的 read/grep/find/ls/write/edit，bash 命令帶 `viking://` URI 時，tool_result 在結果末尾追加提示。版本 0.4.1。
- **能力亮點**：takeover 壓縮接管（預設開，[§3.4.2](#_3-4-2-pi-takeover)）；兩段式召回（before_agent_start 排隊 + context 事件同步檢索，當前輪 prompt 拿當前輪記憶）；statusline；`session_shutdown` 在所有關閉方式下都觸發且被 await。
- **行為要點**：預設 takeover 下退出不 commit（handler 持久化本地狀態，歸檔靠下次續跑攢滿閾值或 `/viking commit`，[§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣)）；takeover 閾值 30000 token + 保留 3 輪（keep 3，服務端按訊息條數解釋）；非 takeover 閾值 20000/keep 10、退出無條件 commit；工具註冊需 health、ensureSession 與 `/mcp` 握手三項前置（[§1.1](#_1-1-主動工具面-agentic-呼叫能力)），ROOT 角色的 API key 訪問 `/mcp` 會被 403 拒絕，憑據鏈最終落到 `ov.conf` 的 `server.root_api_key` 時本次會話就沒有工具——0.4.0 之前是 REST 工具照常註冊、每次呼叫靜默返回 "No results found."；`openviking_remember` 走 MCP 面，即自建一次性會話並立即提交，不再併入 pi 的會話（[§2.1](#_2-1-服務端-mcp-工具面)）；`openviking_add_resource` 可直接攝取遠端 URL，本地路徑則由服務端返回一條上傳指引，需要模型用 `bash` 把檔案 POST 上去，與其他 MCP harness 一致；`openviking_read` 只返回全文，目錄 URI 會得到 `Cannot render …: URI points to a directory`，舊的 `level="abstract"/"overview"` 兩檔在 MCP 面沒有對應工具，替代路徑是 `openviking_search(mode="context", detail="overview")` 或 `openviking_tree(include_abstract=true)`，takeover 的歸檔 overview 仍由擴充自己經 REST 注入；單次工具呼叫受共享的 `timeoutMs` 約束（15000ms，`OPENVIKING_TIMEOUT_MS` 可調），`write`/`edit` 帶 `wait=true` 或 `add_resource` 同步 ingest 有可能超過，而超時或 ESC 只讓本地呼叫失敗，已經發出的請求會跑完，寫入仍可能已經生效；從 0.3.x 升級時全部工具改名且沒有別名期，`--tools` / `--exclude-tools` 白名單裡寫死的 `viking_*` 必須手工替換，否則工具會靜默消失；非 takeover 模式下 `pi -c` 續跑會重新上報整條 branch。
- **配置**：env + ovcli.conf `plugin.pi` + workspace 檔案（憑據統一走憑據鏈，[§3.1.3](#_3-1-3-憑據體系)）；bypass 走共享 `isBypassed` 的 glob 匹配，鍵名 `bypassSessionPatterns`（舊名 `bypassPatterns` 仍可讀）；共享鍵 `mcpEnabled: false` 現在對 pi 也生效：不發起橋接、不註冊工具，`/viking` 標註成配置而非故障。
- **維度索引**：工具面 [§1.1](#_1-1-主動工具面-agentic-呼叫能力) ｜召回 [§3.2](#_3-2-自動召回與注入) ｜takeover [§3.4.2](#_3-4-2-pi-takeover) ｜commit [§3.3.2](#_3-3-2-常規-commit-觸發條件)/[§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣)。

## openclaw

- **整合文件**：[OpenClaw 外掛](./03-openclaw.md)
- **形態**：唯一 context-engine 全接管型（`ownsCompaction:true`）。15 原生工具（預設開 14）+ 5 slash + 4 hook + Gateway HTTP 路由 + feature-gate RPC。remote-only。版本 2026.6.18。
- **能力亮點**：檢索拆兩個預設不重疊入口——`memory_recall` 預設搜 memory、`ov_search` 預設搜 resource+user skills（都可顯式引數越界）；`add_skill` 預設開；`memory_forget` memory-only 白名單（[§3.5](#_3-5-寫入與刪除的型別邊界)）；三個 tool-result 工具讀服務端外接輸出（跨會話 guard）；ContextEngine 全接管（[§3.4.3](#_3-4-3-openclaw-contextengine)）；setup 嚮導帶 key 角色探測與版本相容檢查。
- **行為要點**：召回走 `/find` 不帶 session_id（expansion/去重臺帳不參與，長會話中同一記憶可能重複注入）；關閉不觸發 commit，歸檔依賴顯式 `/new`/`/reset` 與 ~50% 閾值（[§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣)）；無本地 pending queue（失敗輪次不重放）；`compact()` 最長阻塞 5 分鐘；召回預設對每條 leaf 記憶多一次 read（`recallPreferAbstract=false`）；配置嚴格校驗，存在未知鍵/非法值時外掛進入 setup-only 模式。
- **配置**：`openclaw.json` 的 `plugins.entries.openviking.config` + 少量 env；認證頭 `X-API-Key`（[§3.1.3](#_3-1-3-憑據體系)）；commit 閾值由 `commitTokenThresholdRatio` 控制（預設 0.5）；召回字元預算 4000。
- **維度索引**：工具面 [§1.1](#_1-1-主動工具面-agentic-呼叫能力) ｜召回 [§3.2](#_3-2-自動召回與注入) ｜ContextEngine [§3.4.3](#_3-4-3-openclaw-contextengine) ｜刪除 [§3.5](#_3-5-寫入與刪除的型別邊界) ｜commit [§3.3.2](#_3-3-2-常規-commit-觸發條件)/[§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣)。

## hermes（Nous Research）

- **整合文件**：[Hermes Agent](./05-hermes.md)
- **形態**：Hermes bundled MemoryProvider（Python 單檔案實現，共 3725 行，隨 Hermes 一同釋出）。通過 `httpx` 直連，無需額外安裝外掛。提供 6 工具及 10+ 生命週期 hook（prefetch/sync_turn/on_session_end/on_session_switch/on_memory_write/…）。基線為發行版 `e12626b3`（= brew 2026.7.7.2）。
- **能力亮點**：具備最全面的資源攝取面——`viking_add_resource` 支援 HTTP、Git、SSH、`file://`、本地檔案 temp_upload 以及本地目錄 zip 打包上傳（跳過 symlink + 越界檔案）；`viking_remember` 直寫記憶檔案（不依賴 session commit/抽取）；支援本地服務端自啟（當 endpoint 位於本地且不可達時，通過 `subprocess.Popen openviking-server` 拉起）；支援 trusted 補身份重試；無論正常退出還是接收到 Ctrl+C、SIGTERM、SIGHUP 訊號，均能保證完成 commit（詳見 [§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣)）。
- **行為要點**：在召回上，僅有 `search/search` 的首選路徑攜帶 session_id 並落到路徑 B（`mode="deep"`；而 `auto`/`fast` 走 `/find` 且不帶 session_id，詳見 [§3.2.2](#_3-2-2-判定矩陣)）。`queue_prefetch` 為同步實現，無預熱；subagent 傳入 `skip_memory=True` 時不接 OV（詳見 [§3.3.5](#_3-3-5-subagent-會話對照)）。無 profile 注入/statusline/slash；commit 恆 keep 0，drain 不淨則本次不 commit；程序內佇列不落盤。session id 格式為 `%Y%m%d_%H%M%S_<hex6>`。召回引數：6 條/閾值 0.15/字元預算 4000/總超時 4s。記憶 URI 為 `viking://~/peers/{agent}/memories/{subdir}/mem_<uuid12>.md`。退出機制包含 SIGTERM grace 1.5s 與退出看門狗 30s。互補路徑支援 `openviking-server ingest hermes`（離線重放，預設關，詳見 [§7](#_7-附錄-非-coding-整合速覽) E）。
- **配置**：通過 `OPENVIKING_ENDPOINT`（非 `_URL`）、8 個 `OPENVIKING_RECALL_*` env 以及 `config.yaml` 進行配置。在 `use_ovcli_config` 模式下，系統會清空 `.env` 裡的對應變數。
- **維度索引**：工具面 [§1.1](#_1-1-主動工具面-agentic-呼叫能力) ｜召回 [§3.2](#_3-2-自動召回與注入) ｜commit [§3.3.2](#_3-3-2-常規-commit-觸發條件)/[§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣) ｜刪除 [§3.5](#_3-5-寫入與刪除的型別邊界)。

## ov CLI

- **整合文件**：[部署指南 → CLI](../guides/03-deployment.md#cli)
- **形態**：Rust 原生二進位制，把服務端 REST 包成命令列；無宿主事件、無自動召回、不接管壓縮。
- **能力亮點**：唯一會下發 `auto_commit_policy` 的第一方客戶端（`ov session new --auto-commit-policy-json`、`ov session config set`）；提供多 profile、admin、privacy、snapshot、TUI 等外掛面沒有的能力（詳見 [§5.3](#_5-3-cli-獨有於外掛面的能力)）。
- **維度索引**：完整命令參考請見 [§5](#_5-ov-cli-命令參考)。

---

# 5. ov CLI 命令參考

`ov`（clap 內部名 `openviking`）是 Rust HTTP 客戶端，所有能力都在服務端，CLI 只做引數拼裝、本地打包上傳、輸出渲染與多 profile 管理。它不是 harness 整合——沒有宿主事件、不自動召回、不接管壓縮；本章覆蓋它作為"人/指令碼直接使用 OV"的完整命令面，以及它獨有於外掛面的能力（TUI、多 profile、admin、`--sudo`、privacy、snapshot 等）。

> 版本說明：以 HEAD 原始碼為準（HEAD tag 已到 `cli@0.4.14`），0.4.10 等舊版本的差異處已標註。需要注意的是，`ov doctor` 不在 Rust 二進位制裡——pip 裝的 Python wrapper 會攔截 `argv[1]=="doctor"` 並走 `openviking_cli.doctor`，讀取的是服務端 `ov.conf` 而非 `ovcli.conf`；npm/cargo 裝的純 Rust `ov` 無該子命令。

## 5.1 命令樹

命令 doc-comment 字首 `[Data]`/`[Interactive]`/`[Admin]`/`[Experimental]` 等隻影響 help 渲染，不影響執行時——即使是 `[Experimental]` 命令，預設也可用。

**資料寫入**：`add-resource`（支援本地檔案/目錄/URL/Git/sitemap/RSS；目標 `--to`/`--parent`/`-p` 三選一；manifest 模式 `-m`；Connector `--add-type`；注意本地路徑 + watch>0 會報錯）｜`add-skill`｜`write`（`--content`/`--from-file` 互斥）｜`mkdir`｜`rm`（別名 del/delete，無確認提示，`-r` 顯式遞迴）｜`mv`（別名 rename）｜`set-tags`（頂層隱藏，用 `attrs set-tags`）｜`add-memory`（實驗性；執行邏輯為建 session → 批次 add → commit 三步序列）

**讀取/檢索**：`ls`（別名 list）｜`tree`（`-L` 預設 3）｜`stat`／`attrs get`｜`read`／`abstract`／`overview`（分別對應 L2/L0/L1）｜`get`（下載）｜`find`（query 或 `--image` 至少一個非空；`--image` 支援本地路徑、data URI、http、viking://）｜`search`（實驗性，比 find 多一個 `--session-id`）｜`grep`｜`glob`

**Skills**：`skills add`（支援本地路徑、git 及 GitHub tree URL，`-s` 選裝、`*` 全裝，有互動確認）｜`skills list/find/show/update/remove`｜`skills validate`（唯一完全離線的命令）

**會話/記憶**：`session new`（`--auto-commit-policy-json` 與 `--no-auto-commit` 互斥——唯一下發 policy 的第一方客戶端）｜`session list/get/delete`｜`session get-session-context`（`--token-budget` 預設 128000）｜`session get-session-archive`｜`session add-message(s)`｜`session config set`（改可變配置）｜`session commit`

**匯入匯出/快照**：`export`／`backup`／`import`／`restore`（.ovpack）｜`snapshot commit/restore/show/log/diff/ignore-*`（工作區快照，前向 commit 回滾）

**隱私**：`privacy categories/list/get/versions/version/activate/upsert`（`--key-<name>` 語法糖）

**狀態/可觀測**：`health`（healthy=false 時仍退 0）｜`status`（表格模式始終退 0）｜`observer {queue,vikingdb,models,retrieval,filesystem,system}`｜`wait`｜`task status/cancel/list`｜`task watch {ls,show,rm,pause,resume,update,trigger}`｜`version`（獨立 3s 超時探服務端）

**配置/互動**：`config`（TUI 嚮導，5 項選單含 User Management）｜`config show`（固定 json+compact 輸出）｜`config validate`｜`config list/switch/add/edit/delete`（面向 Agent，退出碼 2-6 語義化）｜`config add ov-service`（雲）／`config add custom`｜`language`（別名 lang）｜`tui`（全屏檔案瀏覽器 + 終端內圖片預覽 + 向量檢視 + 刪除確認）｜`chat`（VikingBot，300s 超時）｜`compile`（用 Skill 整理素材，`--wait` 本地輪詢）

**管理（多為 ROOT/`--sudo`）**：`admin create-account/list-accounts/delete-account/set-role/migrate/register-user/list-users/remove-user/regenerate-key`｜`system wait/status/health/consistency`｜`system crypto init-key`（純本地生成 32 位元組 root key，許可權 0600）｜`system backend sync-status/sync-retry`｜`reindex`（`--mode` 預設 vectors_only；`--wait` 預設 true，全 CLI 唯一）｜`doctor`（僅 Python wrapper）

## 5.2 全域選項與獨有機制

- `-o/--output table|json`（預設取 conf `output`）｜`-c/--compact`（預設 true）｜`--account`/`--user`/`--actor-peer-id`｜`--sudo`（用 root_api_key，只允許 admin/system/reindex/task status/task list）｜`--profile`（隱藏）
- **多 profile**：active 為 `~/.openviking/ovcli.conf`，命名規範為 `ovcli.conf.<name>`；`switch` 是位元組複製（保留 `plugin` 段），而 `add/edit` 走 serde 重寫（會丟棄 Rust Config 不識別的鍵，含 `plugin` 段，見 [§3.1.4](#_3-1-4-配置體系分層)）。
- **語言門禁**：跑任何命令前要求先存顯示語言（未存 + 非互動 → exit 2）；HEAD 起 `--help` 在門禁前豁免（0.4.10 尚無此豁免），但 `--version` 仍需先過門禁。
- **三種 JSON 輸出格式（按命令組不同）**：普通命令 compact 下輸出 `{"ok":true,"result":…}`，`-c false` 輸出裸 payload，失敗輸出 `{"ok":false,"error":…}`；config 係為 `{"status":"ok","result":…}`；帶 profile 時追加 `"profile":[…]`。指令碼解析時需注意；此外 `echo_command` 預設 true 且不受 `-o json` 抑制（stdout 第一行是 `cmd: …`）。
- **env**：`OPENVIKING_CLI_CONFIG_FILE`、`OPENVIKING_UPLOAD_MODE`（local/shared）、`OPENVIKING_ASSETS_CREDENTIALS_FILE`、`OPENVIKING_LANG`/`LC_*`/`LANG`，以及 chat 用的 `VIKINGBOT_ENDPOINT`/`VIKINGBOT_API_KEY`/`OPENVIKING_URL`。

## 5.3 CLI 獨有於外掛面的能力

以下是外掛面拿不到、只有 CLI/TUI 能做的：多 profile 切換與嚮導、`admin` 全套帳號/使用者管理、`--sudo` root 操作、`privacy` 隱私策略 CRUD + 版本、`snapshot`/`backup`/`restore`/`export`/`import` 資料搬運、`reindex` 重建索引、`system crypto init-key` 生成 root key、`ov tui` 互動瀏覽、依賴 VikingBot 能力的 `ov chat`／`ov compile`，以及 `ov session config set` 顯式設 `auto_commit_policy`（唯一能開服務端自動 commit 的第一方入口）。

---

# 6. 自定義 agent 接入指南

如果你使用的 agent/harness 不在上面 11 家裡，可以參考以下三條接入路徑（按投入成本從低到高排列）。

## 6.1 接入路徑 × 能獲得的能力

| 路徑 | 投入 | agent 主動工具面 | 自動召回/捕獲 hook | 會話/commit | 壓縮接管 |
|---|---|---|---|---|---|
| ① [通用 MCP 直連](./06-mcp-clients.md) | 分鐘級（填寫一段 config 即可） | ✅ 16 工具全量 | ❌ 由模型主動呼叫 | 僅 `remember` 建臨時會話 | ❌ |
| ② HTTP API / SDK / [LangChain](./07-langchain-langgraph.md) | 小時級（需寫程式碼） | 自選（按需調 REST） | 自己實現 | 自己實現（或用 LangChain middleware） | ❌ |
| ③ 複用 shared-core / [Agent Plugins 便攜包](./15-agent-plugins.md) | 天級（需寫 hook 適配） | ✅ 16 工具（經 MCP 代理） | ✅ 召回/捕獲/commit/pending 全套 | ✅ | 視接入哪些事件而定 |

## 6.2 路徑①：通用 MCP 直連（推薦起步）

任何支援 MCP 的 agent，只需在其 `mcpServers` 配置裡指向服務端 `/mcp`（各客戶端的具體配置位置見 [MCP 客戶端](./06-mcp-clients.md)），即可立刻獲得全部 16 個工具（[§2.1](#_2-1-服務端-mcp-工具面)）。最小配置如下：

```json
{
  "mcpServers": {
    "openviking": {
      "url": "http://127.0.0.1:1933/mcp",
      "headers": {
        "Authorization": "Bearer <api_key>",
        "X-OpenViking-Account": "<account>",
        "X-OpenViking-User": "<user>",
        "X-OpenViking-Actor-Peer": "<workspace-peer>"
      }
    }
  }
}
```

後三個 header 可選，預設時沒有 workspace peer 隔離與租戶路由。stdio-only 的客戶端可用便攜代理（路徑③）把 stdio 橋到 streamable-HTTP。該路徑得到的是純工具面——無自動召回、無捕獲、無 commit（除非模型主動調 `remember`）。

## 6.3 路徑②：程式化接入

- **直連 REST**：召回用 `POST /api/v1/search/search`（必須 `mode:"context"` + `session_id` 才有 expansion/去重，[§3.2.1](#_3-2-1-機制底座-一條共享管線-兩條服務端路徑)；可傳 `rewrite` 獲得服務端 digest，[§3.2.5](#_3-2-5-召回再摘要)）；寫入用 `POST /api/v1/sessions/{id}/messages/batch`（≤100 條/批，auto_create）；提交用 `POST /api/v1/sessions/{id}/commit`；讀取用 `GET /api/v1/content/read` 等。自動 commit policy 可來自 `server.user_config_defaults.auto_commit_policy`、`POST /api/v1/sessions` 或 `PATCH /{id}/config`（[§2.3](#_2-3-服務端會話與-commit-語義)）。
- **LangChain / LangGraph SDK**（`pip install langchain-openviking`）：`OpenVikingContextMiddleware` 提供 `wrap_model_call`（把召回內容注入 `<openviking_context>`）與 `after_agent`（捕獲 + 按 `CommitPolicy` 提交，預設 `never`）。這是本組唯一帶 session + token 預算的現成自動召回；容錯是"只讀方法重試一次、寫方法不重試"，部分成功時拋 `OpenVikingPartialWriteError`（可按 `input_messages_consumed` 切片重試）。參考 [§7](#_7-附錄-非-coding-整合速覽) B。
- **Open WebUI**（OpenAPI 工具伺服器）：`python -m openviking_openwebui` 起獨立程序，在 Open WebUI 裡新增 Tool Server URL，即可得 7 個工具（無刪除、無 hook）。參考 [§7](#_7-附錄-非-coding-整合速覽) A。
## 6.4 路徑③：要自動 hook 面時複用參考實現

如果希望實現召回、捕獲、commit、pending 的全套自動化，完全不必從零開始編寫。建議直接參考並複用以下兩個現成的實現：

- **`examples/memory-plugin-shared/lib/`**（Node）：包含完整的核心功能模組，例如 `recall-core`（三級降級召回）、`profile-inject`、`capture-utils`（訊息歸一 + 注入迴流防護）、`pending-queue`（離線重放）、`batch-send`、`mcp-proxy-core`（stdio↔HTTP 代理）、`session-model`（會話 id 派生）以及 `credentials`。構建瘦 harness 時，只需實現一個適配層，把宿主生命週期事件對映到這些模組即可（例如 `agent-hook-runtime.mjs` 就是 cursor、trae、zcode 共用的現成一體化執行時，接新宿主時的主要工作只是解析其 stdin JSON 欄位名）。
- **Agent Plugins 1.0 便攜包**（位於 `agent-plugins/`）：採用 `plugin.json` + `skills/` + `mcp.json`（stdio→HTTP 代理）的規範化便攜格式。該方案刻意不含 hooks（召回/沉澱靠 skill 教模型自調工具），非常適合符合 Agent Plugins 規範的客戶端直接載入；此外，`plugin.test.mjs` 定義了規範一致性校驗（schema URL、name 規則、靜態 headers 不含機密、`mcp.json` 引用不逃逸外掛根等），可作為自行打包的 lint 依據。

**接入時務必對齊的三個約定**（與現有 harness 保持一致的行為）：① 召回呼叫點必須轉發 `session_id`，這樣才有服務端 expansion + 跨輪去重（詳見 [§3.2.1](#_3-2-1-機制底座-一條共享管線-兩條服務端路徑)）；② 介面卡不要用自己的超時壓過 helper 下發的 deadline；③ 關閉時要安排一條 commit 路徑，否則未達閾值的尾部對話需等待後續觸發才能歸檔（詳見 [§3.3.3](#_3-3-3-關閉方式-×-harness-終局矩陣)）——若宿主沒有關閉事件，需開啟 `memory.session_auto_commit.idle_enabled`，並提供 Session 級或部署級預設 policy。這三條正是 `recall-session-wiring.test.mjs` 用跨外掛正則釘死的。

---

# 7. 附錄：非 coding 整合速覽

| 整合 | 形態 | 工具面 | 會話/commit | 容錯 | 預設狀態 |
|---|---|---|---|---|---|
| **A. [Open WebUI](./08-community-plugins.md)** | 獨立的 FastAPI OpenAPI 工具伺服器 | 7 個本地 OpenAPI 路由（`ov_search`/`ov_recall_memories`/`ov_add_memory`/`ov_list_memories`/`ov_read_resource`/`ov_add_resource`/`ov_session_status`），無刪除工具 | 無會話概念 | 最薄：裸 httpx，無 retry/負快取；`/health` 僅回顯配置，不探測 OV | 程序不啟動即不存在 |
| **B. [LangChain/LangGraph](./07-langchain-langgraph.md)** | Python SDK 適配層（retriever/tools/store/middleware/recorder） | `create_openviking_tools()` 提供 12 個 StructuredTool（`viking_forget` 預設不在 agent profile 中） | `thread_id`/`session_id` 由呼叫方給；`CommitPolicy` 預設 `never` | 本組最穩：只讀方法自動重試 1 次、寫方法不重試（防重複）、部分成功拋結構化異常可切片重試 | 需全部顯式構造才生效 |
| **C. [Agent Plugins 1.0](./15-agent-plugins.md)** | 便攜包 `plugin.json` + `skills/` + `mcp.json`（stdio→HTTP 代理） | MCP 透傳 16 工具；刻意無 hooks（召回靠 skill 教模型） | 僅 `remember` 建臨時會話 | MCP 代理層重試（401/403 換憑據、400/404 重初始化各 1 次） | 客戶端載入後工具即用 |
| **D. [通用 MCP 直連](./06-mcp-clients.md)** | 零本地元件，直連 `/mcp` | 同 C（16 工具） | 同 C | 由客戶端自定 | `/mcp` 常駐 |
| **E. [log ingestion](./09-log-ingestion.md)** | `openviking-server ingest` CLI（跑在日誌所在機器，反向匯入） | 無（只寫不召回） | 會話 id `{prefix}__{harness}__{sanitized native id}`；commit token 6000/idle 5s/keep 0 | 唯一有崩潰恢復：SQLite 游標庫 + 單例項鎖 + reconcile 判定批次落地 | 雙重預設關（`ingest.enabled` + 每 harness `enabled` 都 false）；支援 claude_code/codex/hermes/opencode/openclaw/cursor 介面卡 |
| **F. [OpenViking Helper](./14-openviking-helper.md)** | 閉源桌面 App | — | — | — | 不在本文程式碼基線內 |

---

*各整合的安裝、配置與排障以對應的單獨整合頁面為準；當本頁與單獨頁面不一致時，以單獨頁面為準。*

## 參見

- [Agent 整合概覽](./01-overview.md)
- [MCP 客戶端](./06-mcp-clients.md)
- [MCP 集成指南](../guides/06-mcp-integration.md)
- [檢索 API](../api/06-retrieval.md)
- [會話 API](../api/05-sessions.md)
- [鑑權](../guides/04-authentication.md)
