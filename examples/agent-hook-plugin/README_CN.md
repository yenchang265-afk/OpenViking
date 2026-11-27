# OpenViking 記憶：輕量 Hook 宿主

Cursor、TRAE、TRAE CN 與 ZCode 使用宿主配置檔案；Kimi Code 使用原生託管外掛目錄，CodeBuddy Code 與 Qoder CLI 使用本地外掛 marketplace，Antigravity 使用 `~/.gemini/config/plugins/` 下的外掛目錄。它們共用同一個 dispatcher 和記憶執行時，安裝指令碼在安裝時組裝依賴，不在倉庫裡為每個宿主提交共享程式碼副本。

```bash
curl -fsSL https://openviking.ai/install | bash
```

安裝指令碼會詢問要安裝哪些宿主以及 OpenViking 連線資訊。要從倉庫 checkout 安裝，在倉庫根目錄執行 `bash examples/memory-plugin-shared/install.sh --harness <cursor|trae|trae-cn|zcode|kimicode|codebuddy|qoder|antigravity>`。

> **需要支援 `viking://~` home alias 的 OpenViking 服務端。** 召回通過 `viking://~/memories` 與 `viking://~/skills` 指向呼叫者自己的上下文空間；不帶 uid 的 `viking://user/memories` 簡寫會被較新的服務端拒絕。

## Hook 做什麼

- **會話開始** — 注入使用者畫像與偏好，外加 `<available-skills>` 清單，列出使用者自己的和帳號內共享的 OpenViking skill；同時重放離線會話排隊的寫入。Kimi 啟動時只重放一個有界小批次，並在第一次成功的 prompt hook 注入畫像。
- **提交 prompt** — 搜尋與 prompt 相關的記憶和 skill 並注入，按事件 id 與 500ms 視窗去重。
- **工具呼叫前** — 攔截本地檔案工具對 `viking://` 虛擬路徑的訪問，引導回 OpenViking MCP 工具。在 TRAE 和 Qoder CLI 上，帶 `viking://` URI 的 shell 命令照常執行，並附加一條指向同一組工具的提示。
- **Stop** — 捕獲完成的回合並按宿主策略提交 OpenViking 會話。Kimi 還使用 PreCompact、SessionEnd 與同步 Interrupt 訊號。
- **壓縮之後** — 追加一段簡短的 `<openviking-context source="session-history">` 說明，給出會話的 OpenViking id，以及如何用服務端的 `session_history` MCP 工具查回確切細節。Qoder 在壓縮或恢復後的 SessionStart 中返回，TRAE 在 PostCompact 中返回；Cursor、CodeBuddy 和 Kimi Code 在 PreCompact 記下壓縮（CodeBuddy 也在壓縮後的 SessionStart 記下，CodeBuddy 和 Kimi Code 也記下恢復），在下一次 prompt 時注入。恢復只給還沒收到過說明的會話注入，因為恢復後的 transcript 裡仍有之前那段說明。ZCode 沒有壓縮訊號，Antigravity 沒有 OpenViking MCP 服務，兩者都不注入。模型沒傳 `session` 時，Cursor 的 `preToolUse` 與 Qoder 的 `PreToolUse` hook 會改寫呼叫補上它，CodeBuddy 和 TRAE 由 MCP 代理從呼叫的 `_meta` 補上；Kimi Code 和 TRAE 的說明會要求模型自己傳。設定 `OPENVIKING_SESSION_HISTORY_POINTER=0` 或 `sessionHistoryPointer: false` 關閉這段說明。

## 目錄結構

`scripts/hook.mjs` 是所有 hook 命令的唯一入口，持有五家共用的狀態機——防抖、prompt 去重、召回快取、跨程序鎖——差異部分向 `hosts/` 下的介面卡索取：事件詞彙、響應信封、如何從 payload 讀出 prompt、如何採集完成的回合。`scripts/uri-guard.mjs` 與 `servers/mcp-proxy.mjs` 同樣各只有一份，按安裝器傳入的 client id 選擇宿主。

根目錄的 `plugin.json` 是宿主無關的包後設資料，只用於版本檢查和診斷。Kimi 的原生 manifest 位於 `hosts/kimicode/`，安裝組裝時複製到外掛根目錄。

`hosts/<host>/` 只放宿主配置或原生 manifest；可執行介面卡放在上一層。`../../memory-plugin-shared/lib` 這條相對路徑在原始碼樹、配置型安裝和 Kimi 組裝後的原生外掛裡都成立。

`examples/memory-plugin-shared/sync.mjs` 把 `examples/skills` 下的共享 skill（包括 `ov-memory-doctor`）複製到各個 `hosts/<host>/skills`。

記憶邏輯本身不在這裡：召回、批次寫入、待處理佇列、憑據解析與 MCP 代理都來自 `examples/memory-plugin-shared/lib`，由安裝指令碼複製到 `~/.openviking/agent-integrations/memory-plugin-shared/lib`。

## 各宿主差異

- **Cursor** — 八個事件。`afterMCPExecution` 將 OpenViking 工具結果追加到本地 JSONL 日誌，Stop 時與文本 transcript 一起上報；文本去重與工具上傳位置分別管理，成功後推進捕獲位置，失敗由原記錄重試。`capturedSinceCommit` 達到閾值才 commit，壓縮前在訊息完整上報後 commit。會話字首 `cu-`。見 [Cursor 接入文件](../../docs/zh/agent-integrations/12-cursor.md)。
- **TRAE / TRAE CN** — 採集直接讀 Stop 事件的 `prompt`、`text_content`、`last_assistant_message`，不解析 transcript；每次帶內容的 Stop 都 commit。安裝指令碼把五個 skill（`openviking-memory`、`openviking-skills`、`ov-experience-memory`、`openviking-rule-search`、`ov-memory-doctor`）複製到 `~/.trae/skills` 或 `~/.trae-cn/skills`，使用者改過的 skill 或同名的非託管目錄在升級和解除安裝時保留；TraeCode CLI 也讀取 `~/.trae/skills`，同時裝了它的外掛時，CLI 會把每個 skill 列兩次。會話字首 `tr-` 與 `trcn-`。見 [TRAE 接入文件](../../docs/zh/agent-integrations/13-trae.md)。
- **ZCode** — rollout 檔案是權威增量對話源：穩定的 host `turnId` 用於去重，也讓後續 Stop 能補回漏掉的回合，hook stdin 只是兜底。ZCode 不支援 `PreCompact` 與 `SessionEnd`，因此每次 Stop 都 commit 來補足這兩個訊號。它的輸出 schema 是嚴格的，所以放行時不寫任何內容。五個 skill 安裝到 `~/.zcode/skills`，與 TRAE 一樣記錄歸屬。會話字首 `zc-`。已驗證的擴充面記錄在 [DESIGN.md](./DESIGN.md)。
- **Kimi Code** — `wire.jsonl` 是權威 transcript；UserPromptSubmit 輸出原始上下文文本。Stop、PreCompact、SessionEnd 可後臺寫入，Interrupt 保持同步並共享 2 秒的 OpenViking 請求預算。安裝指令碼生成自包含原生外掛，不修改舊的 `config.toml` 或 `mcp.json`，並在外掛的 `skills/` 下附帶五個 skill，由 `kimi.plugin.json` 宣告。會話字首 `kc-`。
- **Antigravity** — 桌面 app 與 `agy` CLI 讀取 `~/.gemini/config/plugins/` 下的同一個外掛。Antigravity 在每次模型呼叫前都執行 PreInvocation，所以只在一輪的第一次呼叫（`invocationNum` 為 0）召回，上下文以 `injectSteps` 系統訊息返回。Stop 不攜帶文本：捕獲在後臺程序中讀取 `transcriptPath` 裡上次之後已完成的步驟，然後 commit。PreToolUse 拒絕位置引數（名稱以 `Path`、`File` 或 `Directory` 結尾）為 `viking://` URI 的檔案工具，`run_command` 不檢查。外掛目錄裡還有五個 skill（每個都可以用 `/<name>` 呼叫），以及註冊共享 MCP 代理的 `mcp_config.json`；`~/.gemini/config/mcp_config.json` 已定義 `openviking` 服務時，安裝指令碼不寫這個檔案。會話字首為 `ag-`。用 `--harness antigravity` 安裝，指令碼會寫入這個外掛目錄，不是它寫入的同名目錄會保留；見[社群外掛文件](../../docs/zh/agent-integrations/08-community-plugins.md#antigravity-記憶整合)。

Cursor 工具採集依據 [Hooks 契約](https://cursor.com/docs/hooks) 和 [`@cursor/sdk` 1.0.38](https://registry.npmjs.org/@cursor/sdk/-/sdk-1.0.38.tgz) 的 MCP 執行器實現，後者在 `afterMCPExecution` 中提供 `tool_use_id`。舊事件若沒有原生呼叫 ID，只保留文本採集；介面卡不生成呼叫 ID 或推斷完成狀態。

## 體檢

```bash
node ~/.openviking/agent-integrations/<client>/scripts/ov-memory-doctor.mjs --offline
```

`<client>` 為 `cursor`、`trae`、`trae-cn`、`zcode` 或 `antigravity`。Kimi Code、CodeBuddy Code 和 Qoder CLI 執行已安裝外掛裡的副本：

```bash
node "${KIMI_CODE_HOME:-$HOME/.kimi-code}/plugins/managed/openviking-memory/agent-integrations/kimicode/scripts/ov-memory-doctor.mjs" --offline
node ~/.openviking/agent-integrations/codebuddy/marketplace/openviking-memory/agent-integrations/codebuddy/scripts/ov-memory-doctor.mjs --offline
node ~/.openviking/agent-integrations/qoder/marketplace/openviking-memory/agent-integrations/qoder/scripts/ov-memory-doctor.mjs --offline
```

每個副本檢查它安裝時對應的宿主；傳 `cursor`、`trae`、`trae-cn`、`zcode`、`antigravity`、`kimicode`、`codebuddy` 或 `qoder` 可以覆蓋。對 Kimi Code、CodeBuddy Code 和 Qoder CLI，還會檢查外掛自己的 manifest、hooks 和 MCP 檔案，以及宿主是否已載入該外掛。去掉 `--offline` 會連帶探測服務端，加 `--json` 輸出機器可讀報告。在會話中，`ov-memory-doctor` skill 會為當前宿主運行同一個體檢指令碼。

## 測試

```bash
node --test examples/agent-hook-plugin/tests/*.test.mjs
```
