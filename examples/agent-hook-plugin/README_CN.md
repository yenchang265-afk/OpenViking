# OpenViking 記憶：輕量 Hook 宿主

Cursor、TRAE、TRAE CN 與 ZCode 使用宿主配置檔案；Kimi Code 使用原生託管外掛目錄。它們共用同一個 dispatcher 和記憶執行時，安裝指令碼在安裝時組裝依賴，不在倉庫裡為每個宿主提交共享程式碼副本。

```bash
bash examples/memory-plugin-shared/install.sh --harness cursor
bash examples/memory-plugin-shared/install.sh --harness trae,trae-cn
bash examples/memory-plugin-shared/install.sh --harness zcode
bash examples/memory-plugin-shared/install.sh --harness kimicode
```

> **需要支援 `viking://~` home alias 的 OpenViking 服務端。** 召回通過 `viking://~/memories` 與 `viking://~/skills` 指向呼叫者自己的上下文空間；不帶 uid 的 `viking://user/memories` 簡寫會被較新的服務端拒絕。

## Hook 做什麼

- **會話開始** — 注入使用者畫像與偏好，外加 `<available-skills>` 清單，列出使用者自己的和帳號內共享的 OpenViking skill；同時重放離線會話排隊的寫入。Kimi 啟動時只重放一個有界小批次，並在第一次成功的 prompt hook 注入畫像。
- **提交 prompt** — 搜尋與 prompt 相關的記憶和 skill 並注入，按事件 id 與 500ms 視窗去重。
- **工具呼叫前** — 攔截本地檔案工具對 `viking://` 虛擬路徑的訪問，引導回 OpenViking MCP 工具。在 TRAE 上，帶 `viking://` URI 的 shell 命令照常執行，並附加一條指向同一組工具的提示。
- **Stop** — 捕獲完成的回合並按宿主策略提交 OpenViking 會話。Kimi 還使用 PreCompact、SessionEnd 與同步 Interrupt 訊號。

## 目錄結構

`scripts/hook.mjs` 是所有 hook 命令的唯一入口，持有五家共用的狀態機——防抖、prompt 去重、召回快取、跨程序鎖——差異部分向 `hosts/` 下的介面卡索取：事件詞彙、響應信封、如何從 payload 讀出 prompt、如何採集完成的回合。`scripts/uri-guard.mjs` 與 `servers/mcp-proxy.mjs` 同樣各只有一份，按安裝器傳入的 client id 選擇宿主。

根目錄的 `plugin.json` 是宿主無關的包後設資料，只用於版本檢查和診斷。Kimi 的原生 manifest 位於 `hosts/kimicode/`，安裝組裝時複製到外掛根目錄。

`hosts/<host>/` 只放宿主配置或原生 manifest；可執行介面卡放在上一層。`../../memory-plugin-shared/lib` 這條相對路徑在原始碼樹、配置型安裝和 Kimi 組裝後的原生外掛裡都成立。

記憶邏輯本身不在這裡：召回、批次寫入、待處理佇列、憑據解析與 MCP 代理都來自 `examples/memory-plugin-shared/lib`，由安裝指令碼複製到 `~/.openviking/agent-integrations/memory-plugin-shared/lib`。

## 各宿主差異

- **Cursor** — 六個事件，其中 `preCompact` 與 `sessionEnd` 是本外掛裡獨有的。Stop 時 `capturedSinceCommit` 達到閾值才 commit，壓縮前無條件 commit。會話字首 `cu-`。見 [Cursor 接入文件](../../docs/zh/agent-integrations/12-cursor.md)。
- **TRAE / TRAE CN** — 採集直接讀 Stop 事件的 `prompt`、`text_content`、`last_assistant_message`，不解析 transcript；每次帶內容的 Stop 都 commit。會話字首 `tr-` 與 `trcn-`。見 [TRAE 接入文件](../../docs/zh/agent-integrations/13-trae.md)。
- **ZCode** — rollout 檔案是權威增量對話源：穩定的 host `turnId` 用於去重，也讓後續 Stop 能補回漏掉的回合，hook stdin 只是兜底。ZCode 不支援 `PreCompact` 與 `SessionEnd`，因此每次 Stop 都 commit 來補足這兩個訊號。它的輸出 schema 是嚴格的，所以放行時不寫任何內容。會話字首 `zc-`。已驗證的擴充面記錄在 [DESIGN.md](./DESIGN.md)。
- **Kimi Code** — `wire.jsonl` 是權威 transcript；UserPromptSubmit 輸出原始上下文文本。Stop、PreCompact、SessionEnd 可後臺寫入，Interrupt 保持同步並共享 2 秒的 OpenViking 請求預算。安裝指令碼生成自包含原生外掛，不修改舊的 `config.toml` 或 `mcp.json`。會話字首 `kc-`。

## 體檢

```bash
node ~/.openviking/agent-integrations/<client>/scripts/ov-memory-doctor.mjs --offline
```

Kimi 的 managed plugin 需要使用它的實際安裝路徑：

```bash
node "${KIMI_CODE_HOME:-$HOME/.kimi-code}/plugins/managed/openviking-memory/agent-integrations/kimicode/scripts/ov-memory-doctor.mjs" kimicode --offline
```

對於配置型安裝副本，client 預設取安裝時對應的宿主；傳 `cursor`、`trae`、`trae-cn` 或 `zcode` 可以覆蓋。去掉 `--offline` 會連帶探測服務端，加 `--json` 輸出機器可讀報告。

## 測試

```bash
node --test examples/agent-hook-plugin/tests/*.test.mjs
```
