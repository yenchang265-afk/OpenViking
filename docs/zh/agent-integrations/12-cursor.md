# Cursor

為 Cursor 新增跨專案、跨會話的長期記憶。安裝完成後，OpenViking Hook 會在會話啟動和使用者提交問題時注入相關上下文，在回覆結束後捕獲新對話；MCP 僅用於主動搜尋、讀取和管理記憶。

## 安裝

前置條件：macOS 或 Linux、Node.js 18+，並建議使用最新穩定版 Cursor。安裝過程中會引導配置 OpenViking 連線資訊。

安裝器詢問連線方式時，火山引擎雲服務使用者請選擇 **火山引擎 OpenViking 雲服務** 並填寫 API Key。服務執行在本機時選擇 **自建 / 本地**（`http://127.0.0.1:1933`）；遠端自建服務請選擇 **自定義 URL / 保持當前** 並填寫其 URL。

```bash
curl -fsSL https://openviking.ai/install | bash
# AI agent 如不確定是否執行，可先閱讀指令碼頭部，其中寫明瞭它會做什麼、如何核實。
```

安裝完成後完全退出並重新啟動 Cursor。

安裝完成後，在 Cursor 中新開一個會話，讓它按 https://docs.openviking.net/agents/zh/onboarding.md 執行。它會檢查連線，並帶你完成首次使用，詳見[一鍵接入](../getting-started/07-agent-onboarding.md)。

## 安裝內容

- 生命週期 Hook：自動載入畫像、按問題召回、捕獲對話、提交會話並保護 `viking://` URI。
- OpenViking MCP Server：提供 `search`、`read`、`remember`、`add_skill` 等工具；`search` 的 `mode="context"` 可返回組裝後的上下文。
- always-on Rule 和 `openviking-memory` Skill：告訴 Agent 如何使用已注入的上下文和記憶工具；另有 `openviking-skills` Skill，講如何查詢、使用、建立（`add_skill`）、共享和遷移存放在 OpenViking 裡的 skill。
- `ov-experience-memory` Skill：讓 Agent 在執行類任務前檢索並應用以往任務的 Experience。成功的 OpenViking MCP `read` 會與對話一起上報；包含該讀取記錄的 `session commit` 生成軌跡後，可查詢經驗的應用軌跡。

## 驗證

1. 重啟 Cursor 並新建 Agent 會話。
2. 開啟 **Cursor Settings → Hooks**，確認 OpenViking 生命週期 Hook 執行了 `scripts/hook.mjs`，URI 保護 Hook 執行了 `scripts/uri-guard.mjs`。
3. 檢視 `beforeSubmitPrompt` 輸出，確認存在 `additional_context`；這表示當前問題的召回結果已直接交給 Agent，無需先呼叫 MCP。
4. 開啟 **Cursor Settings → Tools & MCPs**，確認 `openviking` 已連線。
5. 告訴 Cursor 一個測試偏好，正常結束會話，並在 Hook 日誌中確認捕獲和提交。等待記憶提取完成後，在同一工作區新建會話並詢問該偏好。

## 工作原理

- `sessionStart`：載入使用者畫像、當前專案的記憶索引，以及 OpenViking skill 清單 `<available-skills>`。
- `beforeSubmitPrompt`：根據當前問題召回上下文並通過 `additional_context` 注入，召回範圍包括你自己的 skill 和帳號內共享在 `viking://agent/skills` 下的 skill。
- `beforeReadFile`：阻止把 `viking://` 虛擬路徑當作本地檔案讀取，並提示改用 OpenViking MCP 工具；shell 命令不做檢查。
- `afterMCPExecution`：將 `openviking` MCP 服務的工具完成記錄追加到本地工具日誌，保留真實呼叫 ID、輸入、輸出和成功或失敗狀態；此時不向服務端寫入訊息，也不重寫此前的結果。
- `stop`：將新增對話與本地工具記錄一起通過 `add message` 上報；成功後才推進捕獲位置，達到原有訊息閾值時執行 `session commit`。工具記錄不額外增加該閾值的訊息計數。
- `preCompact` / `sessionEnd`：提交尚未處理的訊息，觸發記憶抽取。

工具採集要求 `afterMCPExecution` 提供 `tool_use_id`、`mcp_server_name`、`tool_name`、`tool_input` 和 `result_json`。缺少身份或結果的事件會跳過，不會推斷為成功。上傳失敗時保留本地記錄，等待同一會話的後續採集重試；訊息未傳完整時不提交。

工具日誌與會話狀態檔案放在同一目錄。Stop 只讀取尚未確認的日誌尾部；狀態檔案保留位元組位置和已確認的呼叫 ID，去重時不需要重讀舊結果正文。收到確認後才推進上傳位置，工具呼叫不佔用文本的去重額度。

skill 清單先列你自己的 skill，再列帳號內共享的 skill；共享 skill 與你自己的 skill 重名時不列出。每條描述截到約 40 token。清單有獨立的 token 預算 `skillCatalogTokenBudget`（預設 `1200`），不佔用畫像預算。描述放不下時只列名稱，名稱也列不全時末尾附 `... +N more`；連一個名稱都放不下時，只寫一行 skill 數量。把 `skillCatalog` 設為 `false` 或把預算設為 `0` 即可關閉，既可以寫在 `~/.openviking/ovcli.conf` 的 `plugin` 或 `plugin.cursor` 段（見[外掛配置](../configuration/02-client.md#外掛配置)），也可以用環境變數 `OPENVIKING_SKILL_CATALOG` 和 `OPENVIKING_SKILL_CATALOG_TOKEN_BUDGET`。沒有任何 skill，或服務端不提供 `GET /api/v1/skills` 時，不注入這份清單。

專案身份優先使用 Cursor 提供的 `workspace_roots`，因此不同專案會使用不同的 workspace peer。連線資訊統一讀取 `~/.openviking/ovcli.conf`。

## 升級與解除安裝

重複執行安裝命令即可升級。解除安裝時執行：

```bash
curl -fsSL https://openviking.ai/install | bash -s -- --uninstall --yes --harness cursor
```

解除安裝僅移除 OpenViking 管理的 Cursor Hook、MCP、Rule、Skill 和執行檔案，保留其他配置。

## 故障排查

| 現象 | 原因與處理 |
|------|-----------|
| Hook 沒有觸發 | 完全退出 Cursor 後重新啟動，並新建 Agent 會話。 |
| Hook 返回召回內容，但回答未使用 | 更新到最新穩定版 Cursor；舊版本可能不支援 `beforeSubmitPrompt.additional_context`。 |
| 同一事件出現多個 OpenViking Hook | Cursor 可能匯入了舊 Claude Code 外掛。升級或移除安裝器列出的舊 OpenViking plugin id，然後重啟 Cursor。 |
| MCP 未連線 | 檢查 `~/.openviking/ovcli.conf` 中的 URL/API Key，並重啟 Cursor。 |
| 經驗已讀取，但應用軌跡為空 | 檢查 `afterMCPExecution` 是否已安裝且提供上述欄位，並確認 `session commit` 已完成軌跡提取。舊版 Cursor 缺少呼叫 ID 時需升級；自動注入本身不計為讀取。 |
| 需要詳細日誌 | 設定 `OPENVIKING_DEBUG=1` 後啟動 Cursor，檢視 `~/.openviking/logs/cursor-hooks.log`。 |

## 參見

- [整合能力參考](./16-capability-reference.md)
- [鑑權](../guides/04-authentication.md)
- [Cursor Hooks 文件](https://cursor.com/docs/hooks)
