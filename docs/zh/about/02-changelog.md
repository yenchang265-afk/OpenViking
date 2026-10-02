# 更新日誌

Business Data Platform 的所有重要變更都將記錄在此檔案中。
此更新日誌從 [GitHub Releases](https://github.com/volcengine/OpenViking/releases) 自動生成。

## 未釋出

- **Watch API 遷移（不相容變更）**：使用 `watch_interval > 0` 重新匯入不再更新或恢復已有 Watch。
  原生 Watch 暫停後仍獨佔目標，不相容的目標複用返回 `409 Conflict`。
  依賴重新匯入來更新 Watch 的指令碼應改用 `PATCH /api/v1/watches/{task_id}`
  （恢復時設定 `is_active: true`），或先刪除舊 Watch 再建立替代任務。
  Connector Watch 可共享目標，但重複匯入相同來源和目標會建立新的獨立 Watch，重試並不冪等。
  共享目標應通過任務 ID 管理；按 URI 查詢多個可訪問的 Watch 時返回 409。
  一次性 Connector 匯入（`watch_interval <= 0`）不影響已有 Watch，暫停或刪除請使用 watches API。
  詳見[資源任務管理](../api/02-resources.md#任務管理操作)。
- **Session policy 相容性**：字串 `"false"` 現在會正確關閉對應的記憶抽取開關。
  現有 boolean-like 值暫時保持相容併產生棄用警告；新配置應使用 JSON 布林值。
- **工作區 peer 派生規則**：coding agent 外掛不再按工作目錄派生工作區 peer，改為按 git 派生。新的預設值 `peer.source: "git"` 取倉庫歸一化後的 `origin` URL（`github.com-volcengine-openviking`），其次回退到倉庫根路徑，因此同一個倉庫的每個 clone、worktree 和子目錄共用同一個 peer，而 fork 仍是獨立的 peer。不在 git 倉庫中的目錄現在完全不傳送 peer，在那裡記下的內容進入使用者級空間，而不是為每個目錄新建一個名稱空間。要讓這樣的目錄擁有獨立記憶，在其中建立 `.openviking/config.json`，寫入 `{"version": 1, "peer": {"id": "my-project"}}`。無需任何遷移：此前按工作目錄派生的 id 隨時可以在本地重新算出，而預設的 `peer_scope: "all"` 召回本來就會掃描所有 peer，因此寫在舊 id 下的記憶照常召回（`peer_scope: "actor"` 時，Claude Code、Codex、OpenCode 和 DSH 外掛會額外查詢該 id）。設定 `peer.source: "cwd"`（或 `OPENVIKING_PEER_SOURCE=cwd`）即可保持舊行為。
- **pi 擴充的工具面（不相容變更）**：pi 擴充 0.4.0 移除自己手寫的 7 個 `viking_*` REST 工具，改用官方 MCP 客戶端連線服務端，因此工具清單由服務端 `tools/list` 的返回決定，不再來自擴充自帶的目錄。每個工具的名字是 `openviking_` 加服務端的工具名（`viking_search` → `openviking_search`），不保留舊名別名期；pi 的 `--tools` 和 `--exclude-tools` 按名字精確匹配，白名單裡仍寫 `viking_search` 的話，對應工具會靜默消失，需要手動改名。這些工具的行為與其他 MCP harness 一致：`remember` 另開一個會話並立即提交，不再追加到當前 pi 會話；`read` 只返回全文（`level="abstract"` 和 `level="overview"` 兩檔已移除，替代路徑是 `openviking_search(mode="context", detail="overview")`）；`forget` 直接刪除傳入的 URI；`add_resource` 對本地路徑返回一次性上傳 URL，由模型把檔案 POST 上去。root api key 在 `/mcp` 上被拒絕（403），現在會導致整個會話一個工具都沒有，而此前是工具照常註冊、每次呼叫都返回空結果，這類部署需要改用 user 或 admin key。共享開關 `mcpEnabled: false` 現在對 pi 同樣生效，以這種方式關掉工具不計作故障。以上各種情況下，recall、會話採集和上下文接管都照常工作，其他 harness 不受影響。完整的改名對照和升級說明見擴充 README 的 [Upgrading from 0.3.x](https://github.com/volcengine/OpenViking/blob/main/examples/pi-coding-agent-extension/README.md#upgrading-from-03x)。
- **外部 peer identity 遷移**：日誌匯入中的混合文字標識改用無損的
  `ext-<base64>` id。`ext-` 名稱空間為編碼身份保留，因此原本會進入該名稱空間的
  ASCII 身份也會被編碼。系統不會自動讀取舊的有損 peer 目錄，因為多個身份可能彼此衝突，
  也可能與真實 ASCII peer 衝突；遷移這些歸屬不明確的歷史資料需要運維人員明確確認歸屬。

## v0.4.9 (2026-07-10)

### 重點更新

- **Agent 工作區隔離**：Codex、Claude Code、OpenCode 和 Pi 整合支援從工作區派生 peer identity，實現專案級記憶隔離，並擴充共享安裝器與混合 MCP 支援。
- **檢索與記憶正確性**：新增圖片搜尋，正確處理 agent-only / peer-only 記憶範圍，並避免生成巢狀的記憶連結。
- **儲存與安全加固**：序列化本地 collection 懶載入，按後端約束 VikingDB content 寫入，並阻止 Git submodule SSRF。
- **VikingBot 與平臺修復**：新增統一 gateway 路由和 Business Data Platform 鑑權，並修復渠道 sender metadata、僅 VLM 配置、Windows 向量後端和 benchmark 併發問題。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.4.8...v0.4.9)

## v0.4.8 (2026-07-08)

### 重點更新

- **NVIDIA cuVS 向量後端**：支援 opt-in 的 GPU 精確/近似檢索，以及本地後端的視訊記憶體感知回退。
- **遞迴網頁匯入**：基於 Scrapy 和 trafilatura，支援深度、頁數、路徑和下載連結限制的同站爬取。
- **記憶 v3 與訓練**：啟用 v3 抽取鏈路、流式 patch-merge 更新和 session train/eval。
- **Agent 外掛安裝**：Codex / Claude Code 支援遠端 marketplace，stdio MCP 代理與 hooks 共享 `ovcli.conf` 憑據。
- **檔案系統與 RAGFS**：支援後端分頁 glob、穩定的目錄優先排序和標準相對路徑匹配。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.4.7...v0.4.8)

## v0.4.7 (2026-07-02)

### 重點更新

- **MCP 本地檔案鏈路**：compact 工具描述降低上下文開銷，簽名 `temp_upload` token 支援本地檔案自動入庫。
- **檔案系統與版本管理**：新增 filesystem attrs 和帳號級 `.ovgitignore` 規則。
- **SDK 與鑑權**：Go SDK 新增 skill scope 和 grep 深度控制，OAuth client scope 持久化，並支援 seeded API key。
- **Studio 與初始化體驗**：重做 Connection & Identity 頁面，修正 assumed account，並新增 TUI 風格初始化嚮導。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.4.6...v0.4.7)

## v0.4.6 (2026-06-29)

### 重點更新

- **VikingFS 快照版本管理**：HTTP、Python SDK 和 CLI 支持 Git-backed `commit`、`log`、`show`、`restore`。
- **整站匯入**：支援 sitemap、sitemap index、RSS 和 Atom，並可生成持續重新整理的資源樹。
- **共享 Agent Skills**：恢復 `viking://agent/skills` 帳號級共享根，使用者私有 skill 仍為預設目標。
- **VikingDB BM25 grep 與 Studio 指標**：增強關鍵詞檢索與使用者可見的使用指標。

### 升級說明

- 從 0.3.x 升級且仍有 legacy agent/session 資料時，應先在 v0.4.5 完成遷移和 cleanup，再升級到 v0.4.6 或更高版本。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.4.5...v0.4.6)

## v0.4.5 (2026-06-24)

### 重點更新

- **認證角色序列化與 trusted 模式**：請求身份中的角色現在會在 storage、resource、session、queue、watch、summarizer 和語義處理路徑中統一序列化為字串角色；Business Data Platform 後端的 VikingBot 流程也補充了 trusted `auth_mode` 支援。
- **CLI、Web Studio 與 Bot 配置可靠性**：CLI 配置嚮導中的使用者管理設定更清晰，Web Studio 帳號選擇更穩定，VikingBot 認證處理更簡單，失敗的 session archive 現在可以跳過。
- **Agent 整合召回與 OpenCode 文件**：Codex / OpenCode 整合新增 session-aware recall，OpenCode 外掛文件收斂到單一維護中的外掛。
- **儲存與 Session 穩定性加固**：QueueFS 語義處理支援非目錄 memory URI，glob URI scheme 會被保留，event summary fallback、memory abstract 截斷和 path-lock 進度日誌更加穩健。
- **CLI / SDK 介面打磨**：CLI 校驗錯誤更清晰，舊服務端請求會避免傳送較新的欄位，Go SDK 暴露 `set_tags`，並納入獨立 Python HTTP SDK 提取。
- **新增整合示例**：補充 OpenWebUI 與 Pi coding-agent 整合示例。

### 升級說明

- 執行認證或 trusted-mode 多租戶部署時，建議升級到此版本以獲得角色序列化修復。
- Python 包版本由 `v0.4.5` tag 推導。
- Docker 映象由 release workflow 釋出 `v0.4.5` 和 `latest` 標籤。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.4.4...v0.4.5)

## v0.4.4 (2026-06-18)

### 重點更新

- **外掛化認證架構**：認證內部重構為 plugin-based 架構，為後續擴充和維護 auth mode 打下基礎。
- **Go SDK 搜尋過濾**：Go SDK 暴露 search date 與 level filters，客戶端可以更精確地約束檢索範圍。
- **RAGFS 加密帳號修復**：修正 RAGFS 根目錄獲取 encryption account ID 的異常路徑。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.4.3...v0.4.4)

## v0.4.3 (2026-06-18)

### 重點更新

- **RAGFS 快取與遷移可靠性**：新增 CachedFileSystem，並支援 Redis、Mooncake、Yuanrong cache providers；legacy shape probe 會跳過 zero-byte 檔案和 path locks，S3 head-object 錯誤返回更清晰，加密讀取遷移路徑增加 plaintext fallback。
- **Go SDK 與程式碼導航**：支援 Go HTTP SDK 並補充檔案系統示例文件，同時為 OpenCode 外掛新增 code navigation endpoints。
- **文件搜尋與本地化**：新增 Business Data Platform-powered 文件搜尋，並補齊本地化、SDK 和 Hermes wording 更新。
- **Parser、Session 與 Task 修復**：修復 session ID encode、飛書 URL host 匹配、task tracker 加密繫結和 event overview refresh 等問題。
- **安全依賴更新**：提升 `python-multipart` 和 `cryptography` 版本下限以修復高危公告，並讓 UnderstandingAPI zip 下載使用 safe extraction 規避 Zip Slip 風險。
- **外掛與 Memory 後續修復**：更新 memory plugin recall/auth handling、OpenClaw 外掛 release metadata、session skill YAML 規則和 tag-setting 支援。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.4.2...v0.4.3)

## v0.4.2 (2026-06-17)

### 重點更新

- **OpenClaw 安裝與執行時文件加固**：補充 OpenClaw installer 流程、執行時 setup/routing 模組和相關文件測試，確保外掛安裝契約持續受覆蓋。
- **Wiki 與 RAGFS 後續修復**：修正 wiki 連結，並讓 RAGFS shape probe 忽略 legacy task 記錄。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.4.1...v0.4.2)

## v0.4.1 (2026-06-16)

### 重點更新

- **User / Peer 身份模型**：Business Data Platform 將資料 owner (`user`) 與互動物件 (`peer`) 分離，`agent_id` 僅作為 legacy 過渡配置對映到請求級 `actor_peer_id`。
- **0.3.x legacy 遷移路徑**：舊的 `viking://agent/...` 與 `viking://session/...` 資料可以相容讀取、遷移到新的 `viking://user/...` 佈局、驗證，並在確認不需要回滾後清理。
- **多模態入庫擴充**：會話與資源入庫支援圖片訊息、Markdown 圖片 URI 改寫、飛書使用者 token、外部 ParserRouter，以及更完整的圖片向量化鏈路。
- **OpenClaw 與檢索診斷**：檢索支援 `context_type`，OpenClaw 增加 Recall Trace、runtime query config、feature gates 和 actor peer scope wiring。
- **Skills 與外掛生命週期更新**：Skills 成為 user-scoped 上下文資產，Codex / Claude Code 外掛路徑補齊安裝、pending queue、recall cache 和 failure cache 能力。
- **模型與儲存可靠性**：ordered VLM/Embedding credentials、failover/failback 錯誤分類、RAGFS multi-write、S3 content-type autodetect、vector migration 修復和 task 持久化提升生產可用性。

### 升級說明

- 新寫入應遷移到 `viking://user/...`；`viking://agent/...` 仍可讀取舊資料，但不再作為新的 memory、resource、session 或 skill 寫入目標。
- `agent_id` 是 legacy 過渡配置，會對映到請求級 `actor_peer_id`；不要同時配置 `agent_id` 與 `actor_peer_id`，legacy `agent_id` client 也不要再顯式傳 message-level `peer_id`。
- legacy `role_id` 記憶隔離不再支援；請用 User / Peer 模型表達隔離邊界。
- 0.3.x 部署升級前應先備份資料，升級 server / CLI / SDK 到 0.4.1，驗證 legacy 讀取，再執行 `ov --sudo admin migrate --output json`，檢查 task 結果後再 cleanup。
- 使用新檢索、skills、遷移或 OpenClaw surface 的整合，應重新生成固定的 client 或 schema。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.3.24...v0.4.1)

## v0.3.24 (2026-06-05)

### 重點更新

- **CLI 配置體驗與非互動式配置**：`ov config` 重構配置嚮導並最佳化結果輸出，同時新增非互動式配置命令，可在自動化場景中無需互動提示即可指令碼化完成配置。
- **非同步資源匯入持久化**：非同步執行的 `add_resource` 任務現在會被持久化，進行中的匯入在服務重啟後不再丟失。
- **儲存內部最佳化**：最佳化快照 tree 函式，並移除已廢棄的 agfs HTTP 模式客戶端。
- **MiniMax 預設模型升級為 M3**：MiniMax 預設模型現為 M3。
- **更精確的 embedding 錯誤分類**：`classify_api_error` 對數字錯誤碼採用詞邊界匹配，減少對服務商錯誤碼的誤判。

### 升級說明

- agfs HTTP 模式客戶端已移除；如果你依賴 HTTP 模式，請改用受支援的 agfs 接入方式。
- MiniMax 預設模型現為 M3；如需此前的預設模型，請在配置中顯式指定模型。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.3.23...v0.3.24)

## v0.3.23 (2026-06-03)

### 重點更新

- **原生 `ov` CLI 體驗重構**：`ov config` 現在是配置管理入口，可互動式新增、編輯、刪除、切換配置；`ov config show`、`ov config validate`、`ov config switch` 保留為顯式子命令。新增 `ov language` / `ov lang` 選擇顯示語言，`ov status [--verbose]` 提供聚合診斷檢視，`ov health` 與錯誤提示改為更可讀的渲染。
- **Web Studio Playground 與身份管理**：Studio 側邊欄新增 Playground，可檢視上下文樹、執行 Terminal 操作並與 Agent 面板互動；Connection & Identity 頁面支援儲存連線、選擇 account/user 身份、建立 account/user、複製或重新生成 API key。
- **VikingBot 經驗召回配置化**：新增 `bot.ov_server.exp_recall_limit`、`exp_recall_max_chars`，用於調整 agent experience 召回；本地與遠端模式都按傳入 `agent_id` 做經驗名稱空間隔離。
- **資源 Watch 更易用**：`add_resource` 設定 `watch_interval > 0` 時不再強制要求顯式 `to`；如果匯入結果返回穩定 `root_uri`，watch task 會自動繫結到該 URI，CLI/MCP/文件示例同步更新。
- **外掛結構化工具結果與 CJK token 估算**：Claude Code / OpenClaw 外掛改為向 Business Data Platform 寫入結構化 tool parts，工具呼叫與結果不再只能內聯到文本；CJK-aware token 估算覆蓋 Python 與外掛側，降低中文、日文、韓文會話的預算低估風險。

### 升級說明

- `ov config setup-cli` 已移除，請使用裸 `ov config` 進行配置。首次使用新 CLI 時，互動環境會提示選擇顯示語言；非互動自動化應先執行 `ov language en` 或 `ov language zh-CN`。
- `ov status` 預設展示整理後的診斷檢視；需要原始元件資料時使用 `ov status --verbose` 或 `-o json`。
- `ovcli.conf` 預設 URL 統一為 `http://127.0.0.1:1933`，配置序列化會跳過預設值和空欄位。
- 語義處理預設併發從 100 調整為 64，文件中 `vlm.max_concurrent` 預設值同步修正為 64；本地目錄上傳現在會跳過 symlink。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.3.22...v0.3.23)

## v0.3.22 (2026-05-29)

### 重點更新

- **檢索 query planner 可配置**：新增輕量 query planner 配置，可選擇並調整檢索階段意圖分析所用的模型。
- **移除 legacy Memory V1**：刪除已廢棄的 memory v1 路徑，memory `version` 欄位現在會拒絕 `v1` 負載。
- **LangChain 可靠性**：自動恢復失效的 Business Data Platform client，並支援 LangChain 整合的本地批次訊息寫入。
- **VikingDB 健壯性**：向量檢索會跳過 fields 損壞的候選，併為 VikingDB 增加 `ap-southeast-1` region host 對映。
- **CLI 與 server 打磨**：`ov` CLI 在向 server 發請求前先報告缺失的 CLI 配置，server mode 術語從 `dev-implicit` 統一為 `dev`，並統一 embedding 輸入截斷邏輯。

### 升級說明

- Memory V1 已移除；呼叫方需使用當前的 memory `version`，`v1` 負載會被拒絕。
- server mode 術語由 `dev-implicit` 改為 `dev`；請更新匹配舊術語的指令碼或儀表盤。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.3.21...v0.3.22)

## v0.3.21 (2026-05-27)

### 重點更新

- **Trajectory 記憶更適合檢索與復盤**：trajectory schema 新增 `retrieval_anchor` 和 `embedding_template`，索引文本從完整內容收斂為 `trajectory_name + retrieval_anchor`；experience 與 trajectory 之間改為系統維護的 `derived_from` `StoredLink`，寫入正向 `links` 與反向 `backlinks`，替代易丟失的 `source_trajectories` 後設資料。
- **會話訊息支援批次寫入**：REST API 新增 `POST /api/v1/sessions/{session_id}/messages/batch`，CLI 新增 `ov session add-messages`，適合匯入歷史對話或一次寫入多輪訊息；`ov add-memory` 也複用同一套嚴格 JSON 訊息解析。
- **OpenClaw 搜尋工具改名為 `ov_search`**：Business Data Platform OpenClaw 外掛不再註冊 `memory_search`，避免與 OpenClaw 內建工具衝突；匯入 resource/skill 後統一使用 `ov_search` 和 `/ov-search`。
- **資源解析與二進位制 URL 判斷增強**：HTTP accessor 擴充圖片、音訊、影片和 Office/EPUB/zip 文件型別識別；當 `HEAD` 不可靠時會在 `GET` 後用響應頭重新判斷。Word、PowerPoint、Excel、EPUB、legacy doc 等本地轉換路徑改為執行緒中執行，不再阻塞事件迴圈。
- **Web Studio 隨 Python 安裝包分發**：`setup`/`build` 會構建並打包 Web Studio 靜態資源，pip/pipx 安裝後 `/studio` 可直接使用，無需 Docker。
- **LiteLLM VLM 增加 NVIDIA NIM 路由**：模型名中包含 `nvidia_nim` 或 `nemotron` 時可自動走 NVIDIA NIM 的 LiteLLM 字首和 `NVIDIA_NIM_API_KEY` 環境變數。
- **tau2/VikingBot 評測升級**：新增 `benchmark/tau2/vikingbot` 端到端 runner，支援 cold start、train trajectory commit、test 多次平均和跨 epoch 自改進評測；原 tau2 LLM harness 移到 `benchmark/tau2/llm`。

### 升級說明

- OpenClaw 使用者需要把舊的 `/memory-search` 和 `memory_search` 呼叫遷移到 `/ov-search` 與 `ov_search`。
- pip/pipx 和 Docker 構建鏈路現在統一通過 Python build 流程產出 Web Studio bundle；本地開發若不希望構建 Studio，可使用 `OV_SKIP_STUDIO_BUILD=1` 跳過。
- `content.read` 新增 `raw=true` 引數；預設行為仍會隱藏 memory 內部欄位，相容已有呼叫方。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.3.20...v0.3.21)

## v0.3.20 (2026-05-25)

### 重點更新

- **請求級 HTTP profiling**：服務端新增 `server.profile_enabled` 開關。開啟後，請求帶 `profile=1` 時會對當前 HTTP 請求啟用 `cProfile`，並在 JSON 響應中追加 `profile` 行陣列。`ov` CLI 新增 `--profile` 入口並能保留、展示 profile 輸出。
- **批次 Session 訊息寫入**：新增 `POST /api/v1/sessions/{session_id}/messages/batch` 和 Python HTTP client / Session wrapper 的 `batch_add_messages`，一次請求最多寫入 100 條訊息，減少 LangChain/LangGraph 等整合連續寫訊息時的 HTTP 往返。
- **記憶向量化輸入模板**：記憶 schema 新增頂層 `embedding_template`，替代欄位級 `searchable` 標記。預設的 `entities`、`events`、`preferences` 模板現在會把關鍵欄位和正文一起用於 embedding，提高語義召回命中。
- **語義索引與鎖穩定性**：resource 處理會先把 temp source 同步到 target 後再執行語義 DAG，diff 結果使用 target URI；語義鎖 handoff 失效時會嘗試重新獲取 tree lock，鎖衝突類錯誤會重排隊而不是誤觸發 API circuit breaker。
- **Embedding 輸入保護**：embedding 佇列會按 `embedding.max_input_tokens` 截斷輸入，並把過大輸入錯誤分類為 `input_too_large`，避免對不可恢復的大輸入反覆重試。

### 升級說明

- 自定義 memory schema 如果還在欄位上使用 `searchable: true`，應遷移到頂層 `embedding_template`。欄位級 `searchable` 已不再參與 embedding 文本生成。
- 配置項 `memory.enable_role_id_memory_isolate` 已統一為 `memory.role_id_memory_isolation_enabled`，請更新自定義 `ov.conf`。
- `profile=1` 是除錯能力，不建議在高流量生產路徑預設開啟；返回內容最多保留約 16 KiB profile 文本。
- 批次訊息 API 單次最多接受 100 條訊息。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.3.19...v0.3.20)

## v0.3.19 (2026-05-22)

### 重點更新

- **Console BFF 時區語義 breaking change**：`/api/v1/console/dashboard/summary`、`/tokens`、`/context-commits` 現在支援 IANA `timezone` 查詢引數，並由服務端按 viewer timezone 返回分桶；呼叫方應把返回的 `date` / `hour` 視為已本地化，不再在客戶端二次 shift。
- **Usage/Audit 統一按 UTC 寫入**：Token、檢索、上下文提交、Agent 活躍和請求審計 rollup 現在寫入 UTC `date_utc`、`hour_utc`、`created_at`，查詢時再通過 `zoneinfo` 按使用者時區重分桶，覆蓋 DST 和半小時時區場景。
- **本地 Usage/Audit schema reset**：SQLite store 新增 schema version v3，升級時會重置不相容的本地 Usage/Audit 表，避免短保留、pre-GA 資料裡混入 local/UTC 欄位或半遷移的日/小時表。
- **Web Studio heatmap 對齊新語義**：Web Studio 會把瀏覽器時區傳給 Console BFF，heatmap 直接使用服務端返回的 bucket date，修復 UTC+ 使用者下“今天”被二次平移到“明天”的問題。
- **相鄰更新**：新增通過 `memory.session_skill_extraction_enabled` 控制的 session skill 提取鏈路，補充 Hermes Business Data Platform LoCoMo benchmark scripts，修正 Studio OAuth setup 入口文件，並重新整理 LiteLLM 依賴範圍。

### 升級說明

- 本版本包含 BFF breaking change：自定義 Console 客戶端、生成 SDK 或儀表盤如果呼叫 `/api/v1/console/*`，應按需傳入 `timezone=<IANA name>`，並移除客戶端側 UTC 到本地時區的二次分桶邏輯。
- `tokens` 和 `context-commits` 返回的 `date` / `hour` 已是 viewer timezone 下的 bucket；`audit.created_at` 仍為 UTC ISO，僅在展示層格式化。
- 首次使用新的 Usage/Audit SQLite schema 啟動時，不相容的本地 usage/audit 表會被刪除並重建；已有短保留 usage rollup 和 request audit 記錄可能被丟棄。
- 如果自動化側固定了 OpenAPI client 或 Console API 型別，需要重新生成，以包含新的 `timezone` 引數。
- 未傳 `timezone` 時，Console BFF 會回退到 `server.observability.usage_audit.timezone`（預設 `local`）；服務端整合若需要穩定的使用者日邊界，應顯式配置或傳參。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.3.18...v0.3.19)

## v0.3.18 (2026-05-22)

### 重點更新

- **Web Studio 成為預設 Console**：新增 `web-studio` 前端 console workspace，隨 Docker 與 pip 分發並通過 `/studio` 提供服務；OAuth authorize UI 遷入 Web Studio，legacy console 下線，同時保留 favicon 相容路由。
- **MCP / API / CLI 自動化能力**：Watch Management 覆蓋 REST、`ov` CLI 與 MCP；新增本地檔案 progressive single-entrypoint upload；增加 `code_outline`、`code_search`、`code_expand` 程式碼導航工具，並修正 upload-only 與 zip `--ignore-dirs` 的作用域處理。
- **Agent 與 OpenClaw 生態**：OpenClaw setup helper 支援 npm 外掛安裝，外掛文件對齊 ClawHub package metadata，新增 `ov_dream` OpenClaw skill，並支援將過大的 OpenClaw tool result externalize 到 Business Data Platform。
- **Memory 與檢索**：升級 trajectory extraction，新增 memory link 能力，支援通過開關啟用 Vaka memory templates，修復缺失 tool-call 計數和訊息 peer 檢索缺失問題，並行化 hierarchical child search。
- **Storage、VectorDB 與模型鏈路穩定性**：儲存鎖與 IO 非同步化，非同步客戶端按 event loop 隔離；修復 semantic lock ownership、`mv not found` 誤報、URI remapping、S3 grep 效能、VectorDB Unicode recovery、超大 bytes row、embedding 錯誤透出和 VLM LiteLLM native routes 等問題。
- **可觀測性、文件與部署打磨**：新增 VikingBot feedback observability，集中化 metric registry，usage audit SQLite 遷入 system data，重新整理 Helm chart 預設配置，更新品牌資產與二維碼，並補齊 public base URL、signed upload TTL、Watch API、MCP code tools、ready 探針和 `/studio` 遷移文件。

### 升級說明

- 舊 console 與 `8020` 引用應遷移到 `/studio` 的 Web Studio；自定義反代、書籤和部署文件需要同步更新。
- Docker 與 pip 包現在包含 Web Studio 靜態資產；使用自定義 Dockerfile、Caddy 或 Helm overlay 的部署應先複核新的預設配置。
- Usage audit SQLite 現在存放在 system data 目錄；手動管理本地 audit 檔案的部署需要確認新路徑和保留策略。
- Embedding 上游失敗不再被靜默超時掩蓋；呼叫方和健康探針應按顯式 provider 錯誤處理。
- Watch Management、MCP upload 與程式碼導航工具擴充了公共整合面；如自動化側固化了 API/MCP schema，需要同步重新生成。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.3.17...v0.3.18)

## v0.3.17 (2026-05-15)

### 重點更新

- **Agent 整合**：新增 LangChain 與 LangGraph 整合 `openviking.integrations.langchain`（`OpenVikingRetriever`、`with_openviking_context()`、`OpenVikingChatMessageHistory`、`OpenVikingContextMiddleware`、`OpenVikingStore`（LangGraph store）、`create_openviking_tools()`）；Codex / OpenCode 外掛改造為通過生命週期 hooks 做自動召回、逐輪捕獲和 PreCompact 前提交，並直接連線 Business Data Platform 原生 `/mcp` 端點。
- **OVPack v2 與完整備份恢復**：`ov export` / `ov import` 支援 v2 manifest、檔案校驗、portable index scalar、可選 dense vector snapshot 和衝突策略；新增 `ov backup` / `ov restore` 用於公共 scope 的完整遷移。
- **原生 CLI 分發**：新增 `@openviking/cli` npm 包，可通過 `npm i -g @openviking/cli` 使用 `ov`；Rust CLI 釋出流水線擴充 Linux musl 構建、npm trusted publishing 和 CLI 整合測試。
- **檢索與檔案系統能力**：`find` / `search` 新增 `level` 過濾，可限定 L0 abstract、L1 overview 或 L2 檔案命中；資源檔案增加 Phase 1 WebDAV 適配；`observer.filesystem` 暴露檔案系統觀測入口。
- **Console 與 Usage/Audit**：新增 Usage/Audit 模組和 `/api/v1/console/*` BFF，基於現有 observability event bus 統計 token、檢索次數、上下文提交熱力圖、請求審計和上下文庫存。
- **儲存與併發可靠性**：增強精確路徑鎖和生命週期鎖修復內容寫入併發覆蓋；阻塞後端呼叫移出 event loop；QueueFS SQLite 持久化擴充；task 記錄現在會持久化以支援多例項查詢；Git 倉庫 `add_resource(wait=false)` 會返回已預佔的 `root_uri`，並在匯入完成前提供持久化 task 進度。

### 升級說明

- `storage.task_tracker` 已廢棄並會被忽略。Task 記錄始終持久化到各帳號的 `_system/tasks` 目錄。
- `vlm.backup` 只支援一層 backup，且只在 rate limit、`5xx`、連線失敗和 timeout 等可重試錯誤上觸發；認證、許可權和計費類錯誤不會自動切換。
- `vlm.extra_request_body` 會合併到 OpenAI SDK / LiteLLM 的 `extra_body`，適合接入 Ollama、OpenAI-compatible gateway 或其他需要額外 JSON 欄位的 provider。
- Codex 外掛新部署建議使用 `OPENVIKING_*` 環境變數調優；舊的 `ov.conf` 中 `codex.*` 配置仍保留相容，但不再推薦作為首選。
- OVPack dense vector snapshot 只支援純 dense index；embedding provider、model、input、引數和 dimension 不相容時，在 `--vector-mode auto` 下回退重算，在 `--vector-mode require` 下失敗。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.3.16...v0.3.17)

## v0.3.14 (2026-04-30)

### 重點更新

- **可觀測性**：OTLP 匯出支援自定義 `headers`，覆蓋 traces、logs、metrics 三條鏈路，便於直連需要額外鑑權頭或 gRPC metadata 的觀測後端。
- **上傳**：本地目錄掃描和上傳現在遵循根目錄及子目錄中的 `.gitignore` 規則，減少構建產物和臨時檔案被誤匯入。
- **檢索**：`search` / `find` 支援一次傳入多個 target URI，適合跨目錄、跨倉庫範圍檢索。
- **多租戶**：OpenClaw 外掛明確 `peer_prefix` 僅作為 peer metadata 使用；OpenCode memory plugin 補上 tenant headers 透傳。
- **管理**：廢棄的 agent namespace 發現入口已刪除。

### 升級說明

- OTLP 後端接入可通過 `headers` 統一配置鑑權資訊（gRPC 模式為 metadata，HTTP 模式為請求頭）。
- 本地目錄上傳預設遵循 `.gitignore` 規則，此前被匯入的臨時/生成檔案升級後可能被自動過濾。
- OpenClaw 外掛執行時身份通過 `peer_prefix` peer metadata 表達，不再對應 Business Data Platform agent namespace。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.3.13...v0.3.14)

## v0.3.13 (2026-04-29)

### 重點更新

- **內建 MCP 端點**：`openviking-server` 在同一程序、同一埠暴露 `/mcp`，複用 REST API 的 API-Key 鑑權，提供 `search`、`read`、`list`、`store`、`add_resource`、`grep`、`glob`、`forget`、`health` 9 個工具。
- **使用者級隱私配置**：新增 `/api/v1/privacy-configs` API 和 `openviking privacy` CLI，按 `category + target_key` 儲存、輪換、回滾 skill 等敏感配置。
- **可觀測性升級**：統一 `server.observability` 配置，支援 Prometheus `/metrics` 和 OpenTelemetry metrics/traces/logs 匯出。
- **檢索調優**：新增 `embedding.text_source`、`embedding.max_input_tokens`、`retrieval.hotness_alpha`、`retrieval.score_propagation_alpha` 等配置。
- **API 語義收斂**：搜尋空 query 提前拒絕；公開 `viking://` URI 校驗更嚴格；錯誤統一進入標準 error envelope。
- **Docker 體驗**：持久化狀態收斂到 `/app/.openviking`；缺少 `ov.conf` 時容器存活並返回 503 初始化指引。
- **安全**：bot 圖片工具禁止讀取沙箱外檔案；health check 無憑證時跳過身份解析；API key 欄位雜湊拆分為獨立開關。

### 升級說明

- `encryption.api_key_hashing.enabled` 需要顯式配置（預設 `false`）。如依賴舊的隱式雜湊行為，需手動開啟。
- OpenClaw 外掛僅保留遠端模式，不再啟動本地子程序；執行時 agent 身份遷移為 peer metadata，`recallTokenBudget` → `recallMaxInjectedChars`。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.3.12...v0.3.13)

## v0.3.12 (2026-04-24)

### 重點更新

- **新整合**：新增 Azure DevOps Git 託管支援和 larkoffice.com 飛書文件 URL 解析。
- **安全**：API Key 管理重構與安全增強，修復 account name 暴露問題，解決 trusted-mode proxy role 查詢 500 回退。
- **文件**：上線 VitePress 文件站並部署到 GitHub Pages，新增 llms.txt 支援和 Copy Markdown 按鈕。
- **Bug 修復**：修正飛書 config 限制校驗、SSH 倉庫 host 的 userinfo 識別、AGFS URI 錯誤對映、pending tool parts token 計數。
- **開發者體驗**：新增 maintainer routing map 貢獻文件，RAGFS 新增 S3 key normalization encoding。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.3.10...v0.3.12)

## v0.3.10 (2026-04-23)

### 重點更新

- 新增 Codex、Kimi、GLM VLM provider，並支援 `vlm.timeout` 配置。
- 新增 VikingDB `volcengine.api_key` 資料面模式，可通過 API Key 訪問已建立好的雲上 VikingDB collection/index。
- `write()` 新增 `mode="create"`，支援建立新的文本類 resource 檔案，並自動觸發語義與向量重新整理。
- OpenClaw 外掛新增 ClawHub 釋出、互動式 setup 嚮導和 `OPENCLAW_STATE_DIR` 支援。
- QueueFS 新增 SQLite backend，支援持久化佇列、ack 和 stale processing 訊息恢復。
- Locomo / VikingBot 評測鏈路新增 preflight 檢查和結果校驗。

### 體驗與相容性改進

- 調整 `recallTokenBudget` 和 `recallMaxContentChars` 預設值，降低 OpenClaw 自動召回注入過長上下文的風險。
- `ov add-memory` 在非同步 commit 場景下返回 `OK`，避免誤判後臺任務仍在執行時的狀態。
- `ov chat` 會從 `ovcli.conf` 讀取鑑權配置並自動傳送必要請求頭。
- OpenClaw 外掛預設遠端連線行為、鑑權、namespace 和 `peer_id` 處理更貼合服務端多租戶模型。

### 修復

- 修復 Bot API channel 鑑權檢查、啟動前埠檢查和已安裝版本上報。
- 修復 OpenClaw 工具呼叫訊息格式不相容導致的孤兒 `toolResult`。
- 修復 console `add_resource` target 欄位、repo target URI、filesystem `mkdir`、reindex maintenance route 等問題。
- 修復 Windows `.bat` 環境讀寫、shell escaping、`ov.conf` 校驗和硬編碼路徑問題。
- 修復 Gemini + tools 場景下 LiteLLM `cache_control` 導致的 400 錯誤，並支援 OpenAI reasoning model family。
- 修復 S3FS 目錄 mtime 穩定性、Rust native build 環境汙染、SQLite 資料庫副檔名解析等問題。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.3.9...v0.3.10)

## v0.3.9 (2026-04-18)

### 重點更新

- **Memory**：Memory V2 設為預設，包含完整測試套件、session 行遷移，修復併發場景下的檔案鎖衝突。
- **OpenClaw**：上下文分割槽重構為 Instruction/Archive/Session 層，外掛統一 `ov_import` 和 `ov_search`，延長 Phase 2 commit 等待超時。
- **Bot & MCP**：從 HKUDS/nanobot v0.1.5 移植 MCP client 支援，新增單 channel 停用 Business Data Platform 配置，修復心跳可靠性。
- **檢索與搜尋**：通過跳過冗餘 scope 檢查最佳化大目錄搜尋效能，修復 sparse embedder 非同步初始化，新增 rerank extra-headers 支援。
- **部署與上手**：新增互動式 `openviking-server init` 嚮導支援本地 Ollama 部署，`ovcli.conf` 新增預設檔案/目錄忽略配置。
- **基礎設施**：新增度量系統，更新預設 Doubao embedding 模型，提升 RAGFS Docker 構建的 Rust toolchain，解析器拆分為 accessor 和 parser 兩層。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.3.8...v0.3.9)

## v0.3.8 (2026-04-15)

### Memory V2 專題

Memory V2 現在作為預設記憶管線，採用全新格式、重構的抽取與去重流程，長期記憶質量顯著提升。

### 重點更新

- Memory V2 預設開啟，格式與抽取管線全面重構。
- 本地部署與初始化體驗增強（`openviking-server init`）。
- 外掛與 Agent 生態增強（Codex、OpenClaw、OpenCode 示例）。
- 配置與部署體驗改進（S3 批次刪除開關、OpenRouter `extra_headers`）。
- Memory、Session、儲存層效能與穩定性改進。

### 升級提示

- 如果你經常通過 CLI 匯入目錄資源，建議在 `ovcli.conf` 中配置 `upload.ignore_dirs`。
- 舊版 memory v1 已移除；記憶抽取現在僅使用 v2。
- `ov init` / `ov doctor` 請改用 `openviking-server init` / `openviking-server doctor`。
- OpenRouter 或其他 OpenAI 相容 rerank/VLM 服務可通過 `extra_headers` 注入平臺要求的 Header。
- S3 相容實現批次刪除有相容問題時，可開啟 `storage.agfs.s3.disable_batch_delete`。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.3.5...v0.3.8)

## v0.3.5 (2026-04-10)

### 重點更新

- **儲存**：S3FS 新增 `disable_batch_delete` 選項相容 OSS，改進 RAGFS 路徑 scope 回退到 prefix filters。
- **Session & Memory**：修復首條訊息時缺失 session 的自動建立，解決 Memory V2 config 初始化順序問題。
- **Bot**：修復多使用者 memory commit、響應語言處理，確保 `afterTurn` 以正確角色儲存訊息並跳過心跳條目。
- **安全 & CI**：移除 settings.py 中洩露的 token，bot proxy 響應中清除內部錯誤細節，CI 最佳化為條件 OS 矩陣。
- **開發者體驗**：新增場景化 API 測試，queue status 中暴露 re-enqueue 計數便於除錯。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.3.4...v0.3.5)

## v0.3.4 (2026-04-09)

### 版本亮點

- OpenClaw 外掛預設配置調整（`recallPreferAbstract` 和 `ingestReplyAssist` 預設 `false`），新增 eval 指令碼和 recall 查詢清洗。
- Memory 和會話執行時穩定性增強：request-scoped 寫等待、PID lock 回收、孤兒 compressor 引用、async contention 修復。
- 安全邊界收緊：HTTP 資源匯入 SSRF 防護、無 API key 時 trusted mode 僅允許 localhost、可配置 embedding circuit breaker。
- 生態擴充：Volcengine Vector DB STS Token、MiniMax-M2.7 provider、Lua parser、Bot channel mention。
- CI/Docker：釋出時自動更新 `main` 並 Docker Hub push，Gemini optional dependency 納入映象。

### 升級說明

- OpenClaw `recallPreferAbstract` 和 `ingestReplyAssist` 現在預設 `false`，如需舊行為需顯式配置。
- HTTP 資源匯入預設啟用私網 SSRF 防護。
- 無 API key 的 trusted mode 僅允許 localhost 訪問。
- 寫介面引入 request-scoped wait，如有外部編排依賴舊時序需複核。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.3.3...v0.3.4)

## v0.3.3 (2026-04-03)

### 重點更新

- 新增 RAG benchmark 評測框架、OpenClaw LoCoMo eval 指令碼、內容寫入介面。
- OpenClaw 外掛：架構文件補充、安裝器不再覆蓋 `gateway.mode`、端到端 healthcheck 工具、bypass session patterns、Business Data Platform 故障隔離。
- 測試覆蓋：OpenClaw 外掛單測、e2e 測試、oc2ov 整合測試與 CI。
- Session 支援指定 `session_id` 建立；CLI 聊天端點優先順序與 `grep --exclude-uri/-x` 增強。
- 安全：任務 API ownership 洩露修復、stale lock 統一處理、ZIP 編碼修復、embedder 維度透傳。

### 升級說明

- OpenClaw 安裝器不再寫入 `gateway.mode`，升級後需顯式管理。
- `--with-bot` 失敗時返回錯誤碼，依賴"失敗但繼續"行為的指令碼需調整。
- OpenAI Dense Embedder 自定義維度現正確傳入 `embed()`。
- 基於 tags metadata 的 cross-subtree retrieval 已在本版本視窗內回滾，非最終能力。
- `litellm` 依賴更新為 `>=1.0.0,<1.83.1`。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.3.2...v0.3.3)

## v0.3.2 (2026-04-01)

### 重點更新

- **Docker**：新增 VikingBot 和 Console 服務到 Docker 配置；示例更新為使用 latest 映象標籤。
- **OpenClaw 外掛**：新增 ingest reply assist 的 session-pattern guard；統一測試目錄結構。
- **VLM**：回滾 ResponseAPI 到 Chat Completions 同時保留 tool call 支援。
- **穩定性**：修復 HTTPX SOCKS5 代理導致的崩潰；改進安裝器 PyPI 映象回退；Windows 上跳過 FUSE 不相容的檔案系統測試。
- **文件**：新增中英文 OVPack 指南；重組可觀測性文件；下線過時的整合示例。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.3.1...v0.3.2)

## v0.3.1 (2026-03-31)

### 重點更新

- **語言支援**：新增 PHP tree-sitter AST 解析。
- **儲存**：語義摘要生成引入自動語言檢測；修復 legacy 記錄的 parent URI 相容性。
- **CI**：API 測試擴充到 5 個平臺；切換為按架構原生構建 Docker 映象；重新整理 uv.lock 用於釋出構建。
- **配置**：新增可配置 prompt 模板目錄；統一 session 管理中的 archive context 處理。
- **OpenClaw 外掛**：簡化安裝流程、加固輔助工具、自動安裝時保留已有 `ov.conf`。
- **Memory**：應用 memory 最佳化改進。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.2.14...v0.3.1)

## v0.2.14 (2026-03-30)

### 重點更新

- 多租戶與身份管理：CLI 租戶身份預設值與覆蓋、`agent-only` memory scope、多租戶使用指南。
- 解析與匯入：圖片 OCR 文本提取、`.cc` 檔案識別、重複標題檔名衝突修復、upload-id 方式 HTTP 上傳。
- OpenClaw 外掛：統一安裝器/升級流程、預設按最新 Git tag 安裝、session API 與 context pipeline 重構、Windows/compaction/子程序相容性修復。
- Bot 與 Feishu：proxy 鑑權修復、Moonshot 相容性改進、Feishu interactive card markdown 升級。
- 儲存與執行時：queuefs embedding tracker 加固、vector store `parent_uri` 移除、Docker doctor 對齊、eval token 指標。

### 升級說明

- Bot proxy 介面 `/bot/v1/chat` 和 `/bot/v1/chat/stream` 已補齊鑑權。
- HTTP 匯入推薦按 `temp_upload → temp_file_id` 方式接入。
- OpenClaw 插件 compaction delegation 要求 `openclaw >= v2026.3.22`。
- OpenClaw 安裝器預設跟隨最新 Git tag，如需固定版本可顯式指定。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.2.13...v0.2.14)

## v0.2.13 (2026-03-26)

### 重點更新

- **測試**：新增核心工具的全面單元測試；改進 API 測試基礎設施支援雙模式 CI。
- **平臺**：修復 Windows engine wheel 執行時打包。
- **VLM**：LiteLLM thinking 引數限定為 DashScope provider。
- **OpenClaw 外掛**：加固重複註冊 guard。
- **文件**：新增基礎用法示例和中文文件。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.2.12...v0.2.13)

## v0.2.12 (2026-03-25)

此補丁版本通過正確處理 `CancelledError` 穩定了伺服器 shutdown 序列，回滾了一個 bot 配置回退，並通過切換到 `uv sync --locked` 加強 Docker 構建的依賴一致性。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.2.11...v0.2.12)

## v0.2.11 (2026-03-25)

### 版本亮點

- 模型與檢索生態擴充：MiniMax embedding、Azure OpenAI embedding/VLM、GeminiDenseEmbedder、LiteLLM embedding 和 rerank、OpenAI-compatible rerank、Tavily 搜尋後端。
- 內容接入：Whisper ASR 音訊解析、飛書/Lark 雲文件解析器、可配置檔案向量化策略、搜尋結果 provenance 後設資料。
- 服務端運維：`ov reindex`、`ov doctor`、Prometheus exporter、記憶體健康統計 API、可信租戶頭模式、Helm Chart。
- 多租戶與安全：多租戶檔案加密和文件加密、租戶上下文透傳修復、ZIP Slip 修復、trusted auth API key 強制校驗。
- 穩定性：向量檢索 NaN/Inf 分數鉗制、非同步/併發 session commit 修復、Windows stale lock 和 TUI 修復、代理相容、API 重試風暴保護。

### 升級提示

- `litellm` 安全策略調整：先臨時停用，後恢復為 `<1.82.6` 版本範圍。建議顯式鎖定依賴版本。
- trusted auth 模式需同時配置服務端 API key。
- Helm 預設配置切換為 Volcengine 場景預設值，升級時建議重新審閱 values。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.2.10...v0.2.11)

## v0.2.10 (2026-03-24)

### LiteLLM 安全熱修復

由於上游依賴 `LiteLLM` 出現公開供應鏈安全事件，本次熱修復臨時停用所有 LiteLLM 相關入口。

### 建議操作

1. 檢查執行環境中是否安裝 `litellm`
2. 解除安裝可疑版本並重建虛擬環境、容器映象或釋出產物
3. 對近期安裝過可疑版本的機器輪換 API Key 和相關憑證
4. 升級到本熱修復版本

LiteLLM 相關能力會暫時不可用，直到上游給出可信的修復版本和完整事故說明。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.2.9...v0.2.10)

## v0.2.9 (2026-03-19)

此版本聚焦於穩定性和開發者體驗改進。關鍵修復包括：通過在 account backend 間共享單一 adapter 解決 RocksDB 鎖競爭、恢復之前合併中丟失的外掛 bug fix、改善 vector store 增量更新。新功能包括 bot 除錯模式和 `/remember` 命令、semantic pipeline 中基於 summary 的檔案 embedding、CI 中全面的 PR-Agent 評審規則。文件新增 Docker Compose 和 Mac 埠轉發指引。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.2.8...v0.2.9)

## v0.2.8 (2026-03-19)

### 重點更新

- OpenClaw 外掛升級到 2.0（context engine），新增 OpenCode memory plugin，多智慧體 memory isolation 基於 peer metadata。
- Memory 冷熱分層 archival 和 hotness scoring、長記憶 chunked vectorization、`used()` 使用追蹤介面。
- 分層檢索整合 rerank、RetrievalObserver 檢索質量觀測。
- 資源 watch scheduling、reindex endpoint、legacy `.doc`/`.xls` 解析支援、path locking 和 crash recovery。
- 請求級 trace metrics、memory extract telemetry breakdown、OpenAI VLM streaming、`<think>` 標籤自動清理。
- 跨平臺修復（Windows zip、Rust CLI）、AGFS Makefile 重構、CPU variant vectordb engine、Python 3.14 wheel 支援。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.2.6...v0.2.8)

## v0.2.6 (2026-03-11)

### 重點更新

- CLI 體驗：`ov chat` 基於 `rustyline` 行編輯、Markdown 渲染、聊天曆史。
- 非同步能力：session commit `wait` 引數、可配置 worker count。
- 新增 Business Data Platform Console Web 控制台，方便除錯和 API 探索。
- Bot 增強：eval 能力、`add-resource` 工具、飛書進度通知。
- OpenClaw memory plugin 大幅升級：npm 安裝、統一安裝器、穩定性修復。
- 平臺支援：Linux ARM、Windows UTF-8 BOM 修復、CI runner OS 固定。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.2.5...v0.2.6)

## v0.2.5 (2026-03-06)

### 重點更新

- **PDF & 解析**：基於字型的標題檢測和書籤提取為結構化 markdown 標題；`add_resource` 支援索引控制並重構 embedding 邏輯，正確處理 ZIP 容器格式。
- **Session & Memory**：`add_message()` 新增 `parts` 引數支援；memory 抽取後為父目錄觸發語義索引。
- **URI 處理**：短格式 `VikingURI` 支援、CLI 中 `git@` SSH URL 格式、GitHub `tree/<ref>` URL 程式碼倉庫匯入。
- **Bot & 整合**：VikingBot 重構包含新評測模組、飛書多使用者和 channel 增強、OpenAPI 標準化；Telegram Claude 崩潰修復。
- **基礎設施**：`agfs` 新增 ripgrep 加速的 grep 和 async grep，可選 binding client 模式；使用 Doubao 模型的自動 PR 評審工作流和嚴重度分級。
- **安裝**：curl 方式安裝在 Ubuntu/Debian 上不再觸發系統保護錯誤；修復 `uv pip install -e .` 的 Rust 編譯。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.2.3...v0.2.5)

## v0.2.3 (2026-03-03)

### Breaking Change

升級後，歷史版本生成的 datasets/indexes 與新版本不相容，無法直接複用。升級後需要全量重建資料集以避免檢索異常、過濾結果不一致或執行時錯誤。停止服務，刪除 workspace 目錄（`rm -rf ./your-openviking-workspace`），然後用 `openviking-server` 重啟。

此版本提供 CLI 最佳化，包括 `glob -n` 標誌支援和 `cmd echo`，以及中英文 README 更新。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.2.2...v0.2.3)

## v0.2.2 (2026-03-03)

### Breaking Change

升級前請先停止 VikingDB Server 並清除 workspace 目錄。舊版本的索引與此版本不向前相容。

此版本新增 C# AST 提取器支援程式碼解析，修復多租戶過濾，規範 Business Data Platform memory target paths，改進 `git@` SSH URL 的 git 倉庫檢測。`agfs` 依賴的 lib/bin 現在預編譯提供，安裝時無需構建步驟。文件新增千問模型使用說明。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.2.1...v0.2.2)

## v0.2.1 (2026-02-28)

### 重點更新

- **多租戶**：API 層多租戶基礎能力，支援多使用者/團隊隔離使用。
- **雲原生**：雲原生 VikingDB 支援，完善雲端部署文件和 Docker CI。
- **OpenClaw/OpenCode**：官方 `openclaw-openviking-plugin` 安裝、`opencode` 外掛引入。
- **儲存**：向量資料庫介面重構、AGFS binding client、AST 程式碼骨架提取、私有 GitLab 域名支援。
- **CLI**：`ov` 命令封裝、`add-resource` 增強、`ovcli.conf` timeout 支援、`--version` 引數。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.1.18...v0.2.1)

## cli@0.2.0 (2026-02-27)

更新的 CLI 二進位制釋出，跨平臺支援 macOS 和 Linux，與 v0.1.18 功能集對齊，包含 Rust 實現和擴充的檔案解析器能力。

[完整變更記錄](https://github.com/volcengine/OpenViking/releases/tag/cli%400.2.0)

## v0.1.18 (2026-02-23)

此版本為 Business Data Platform 帶來重大新能力。引入高效能 Rust CLI 和終端檔案系統瀏覽器 UI。檔案解析大幅擴充，支援 Word、PowerPoint、Excel、EPub 和 ZIP 格式。新增多 provider 支援用於 embedding 和 VLM 後端。Memory 處理重新設計為具有衝突感知的去重和新抽取流程。

### 重點更新

- **Rust CLI**：全新高速 CLI 實現。
- **檔案解析器**：通過 markitdown 風格解析器支援 Word、PowerPoint、Excel、EPub、ZIP。
- **TUI**：基礎終端 UI 檔案系統導航（`ov tui`）。
- **多 Provider**：支援多個 embedding 和 VLM provider。
- **Memory**：重新設計的抽取和去重流程，具備衝突感知能力。
- **Skills**：新增 memory、resource 和 search skills；改進 skill 搜尋排序。
- **目錄解析**：新增目錄級解析支援。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.1.17...v0.1.18)

## cli@0.1.0 (2026-02-14)

初始 CLI 二進位制釋出，跨平臺支援 macOS 和 Linux，提供獨立的 Business Data Platform 服務管理和資源操作執行檔。

[完整變更記錄](https://github.com/volcengine/OpenViking/releases/tag/cli%400.1.0)

## v0.1.17 (2026-02-14)

穩定性修復版本。因不穩定性回滾了 VectorDB 中的動態 project name 配置，修復 CI workspace 清理，解決 tree URI 輸出錯誤並增加啟動時 `ov.conf` 校驗。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.1.16...v0.1.17)

## v0.1.16 (2026-02-13)

聚焦 bug 修復與改進的版本。修復 VectorDB 連線問題和 uvloop 與 nest_asyncio 的伺服器衝突。臨時 URI 現在可讀，resource add 超時增大，為 VectorDB 和 Volcengine 後端引入動態 project name 配置。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.1.15...v0.1.16)

## v0.1.15 (2026-02-13)

此版本聚焦架構重構和可靠性改進。HTTP 客戶端拆分為獨立的嵌入和 HTTP 模式以實現更清晰的關注點分離。通過目錄重組提升 CLI 啟動速度。解決 VectorDB timestamp 和 collection 建立 bug。

### 重點更新

- **重構**：HTTP 客戶端拆分為嵌入和 HTTP 模式；QueueManager 從 VikingDBManager 解耦。
- **CLI**：更快的啟動速度；改進 `ls` 和 `tree` 輸出。
- **VectorDB**：修復 timestamp 格式和 collection 建立問題。
- **解析器**：支援倉庫分支和 commit 引用。
- **OpenClaw**：初步適配 memory 輸出語言管線。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.1.14...v0.1.15)

## v0.1.14 (2026-02-12)

重大基礎設施版本。引入 HTTP Server 和 Python HTTP Client，實現 Business Data Platform 服務的遠端訪問。OpenClaw skill 新增 MCP 整合支援。目錄預掃描校驗、DAG 觸發 embedding 和並行資源新增提升了效能和可靠性。

### 重點更新

- **HTTP Server**：新的服務模式，提供 Python HTTP Client 用於遠端訪問。
- **OpenClaw Skill**：Business Data Platform 的 MCP 集成。
- **CLI**：完整的 Bash CLI 框架和全面的命令實現。
- **Embedding**：DAG 觸發 embedding 和並行 add 支援。
- **目錄掃描**：新增預掃描校驗模組。
- **配置**：預設配置目錄設為 `~/.openviking`。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.1.12...v0.1.14)

## v0.1.12 (2026-02-09)

此版本改進搜尋質量、儲存可靠性和程式碼可維護性。新增 sparse logit alpha 搜尋增強檢索。在 hierarchical retriever 中複用查詢 embedding 提升效能。支援原生 VikingDB 部署。修補了一個嚴重的 Zip Slip 路徑穿越漏洞 (CWE-22)。

### 重點更新

- **搜尋**：Sparse logit alpha 支援和最佳化的查詢 embedding 複用。
- **VikingDB**：原生部署支持。
- **安全**：Zip Slip 路徑穿越修復 (CWE-22)。
- **重構**：統一非同步執行工具；重構 S3 配置。
- **MCP**：新增查詢支援並通過 Kimi 驗證。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.1.11...v0.1.12)

## v0.1.11 (2026-02-05)

新增對小型 GitHub 程式碼倉庫的匯入支援，使 Business Data Platform 能夠直接索引和搜尋公開程式碼庫。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.1.10...v0.1.11)

## v0.1.10 (2026-02-05)

修復編譯錯誤和 Windows 二進位制釋出打包問題的補丁版本。

[完整變更記錄](https://github.com/volcengine/OpenViking/compare/v0.1.9...v0.1.10)

## v0.1.9 (2026-02-05)

Business Data Platform 的初始公開發布。此版本建立了核心專案結構，支援 Linux 和 Intel Mac 跨平臺。引入服務層架構，將 embedding 和 VLM 後端分離為可配置的 provider。改進了 Memory 去重並修復了檢索遞迴 bug。包含 Python 3.13 相容性、S3FS 支援以及 chat 和 memory 工作流的使用示例。

### 重點更新

- **初始釋出**：核心 Business Data Platform server、client 和 CLI 基礎。
- **Provider**：可配置的 embedding 和 VLM 後端，provider 抽象層。
- **架構**：從 async client 中提取 Service 層；ObserverService 從 DebugService 分離。
- **平臺**：Linux 編譯支援、Intel Mac 相容性、Python 3.13 支援。
- **Memory**：簡化去重邏輯並修復檢索遞迴 bug。
- **示例**：Chat 和 chat-with-memory 使用示例。

[完整變更記錄](https://github.com/volcengine/OpenViking/releases/tag/v0.1.9)
