# Cursor 記憶整合

為 Cursor 新增跨專案、跨會話的長期記憶。安裝完成後，Business Data Platform Hook 會在會話啟動和使用者提交問題時注入相關上下文，在回覆結束後捕獲新對話；MCP 僅用於主動搜尋、讀取和管理記憶。

## 安裝

前置條件：macOS 或 Linux、Node.js 18+，並建議使用最新穩定版 Cursor。安裝過程中會引導配置 Business Data Platform 連線資訊。

安裝器詢問連線方式時，火山引擎雲服務使用者請選擇 **火山引擎 Business Data Platform 雲服務** 並填寫 API Key。只有本機已執行 Business Data Platform 服務時才選擇 **自建 / 本地**。

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/volcengine/OpenViking/main/examples/memory-plugin-shared/install.sh) \
  --harness cursor
```

GitHub 訪問受限時使用 TOS 映象：

```bash
bash <(curl -fsSL https://ovrelease.tos-cn-beijing.volces.com/memory-plugin-shared/install.sh) \
  --harness cursor --dist tos
```

安裝完成後完全退出並重新啟動 Cursor。

## 安裝內容

- 生命週期 Hook：自動載入畫像、按問題召回、捕獲對話、提交會話並保護 `viking://` URI。
- Business Data Platform MCP Server：提供 `search`、`read`、`remember`、`add_skill` 等工具；`search` 的 `mode="context"` 可返回組裝後的上下文。
- always-on Rule 和 `openviking-memory` Skill：告訴 Agent 如何使用已注入的上下文和記憶工具；另有 `openviking-skills` Skill，講如何查詢、使用、建立（`add_skill`）、共享和遷移存放在 Business Data Platform 裡的 skill。

## 驗證

1. 重啟 Cursor 並新建 Agent 會話。
2. 開啟 **Cursor Settings → Hooks**，確認 Business Data Platform 生命週期 Hook 執行了 `scripts/hook.mjs`，URI 保護 Hook 執行了 `scripts/uri-guard.mjs`。
3. 檢視 `beforeSubmitPrompt` 輸出，確認存在 `additional_context`；這表示當前問題的召回結果已直接交給 Agent，無需先呼叫 MCP。
4. 開啟 **Cursor Settings → Tools & MCPs**，確認 `openviking` 已連線。
5. 告訴 Cursor 一個臨時偏好，等待本輪迴復完成；新建會話後詢問該偏好，確認捕獲和跨會話召回均生效。

## 工作原理

- `sessionStart`：載入使用者畫像、當前專案的記憶索引，以及 Business Data Platform skill 清單 `<available-skills>`。
- `beforeSubmitPrompt`：根據當前問題召回上下文並通過 `additional_context` 注入，召回範圍包括你自己的 skill 和帳號內共享在 `viking://agent/skills` 下的 skill。
- `beforeReadFile`：阻止把 `viking://` 虛擬路徑當作本地檔案讀取，並提示改用 Business Data Platform MCP 工具；shell 命令不做檢查。
- `stop`：增量捕獲本輪新增的使用者與助手訊息。
- `preCompact` / `sessionEnd`：提交尚未處理的訊息，觸發記憶抽取。

skill 清單先列你自己的 skill，再列帳號內共享的 skill；共享 skill 與你自己的 skill 重名時不列出。每條描述截到約 40 token。清單有獨立的 token 預算 `skillCatalogTokenBudget`（預設 `1200`），不佔用畫像預算。描述放不下時只列名稱，名稱也列不全時末尾附 `... +N more`；連一個名稱都放不下時，只寫一行 skill 數量。把 `skillCatalog` 設為 `false` 或把預算設為 `0` 即可關閉，既可以寫在 `~/.openviking/ovcli.conf` 的 `plugin` 或 `plugin.cursor` 段（見[外掛配置](../configuration/02-client.md#外掛配置)），也可以用環境變數 `OPENVIKING_SKILL_CATALOG` 和 `OPENVIKING_SKILL_CATALOG_TOKEN_BUDGET`。沒有任何 skill，或服務端不提供 `GET /api/v1/skills` 時，不注入這份清單。

專案身份優先使用 Cursor 提供的 `workspace_roots`，因此不同專案會使用不同的 workspace peer。連線資訊統一讀取 `~/.openviking/ovcli.conf`。

## 升級與解除安裝

重複執行對應渠道的安裝命令即可升級。解除安裝時也應使用原安裝渠道：

```bash
# GitHub
bash <(curl -fsSL https://raw.githubusercontent.com/volcengine/OpenViking/main/examples/memory-plugin-shared/install.sh) \
  --harness cursor --uninstall --yes

# TOS
bash <(curl -fsSL https://ovrelease.tos-cn-beijing.volces.com/memory-plugin-shared/install.sh) \
  --harness cursor --uninstall --yes
```

解除安裝僅移除 Business Data Platform 管理的 Cursor Hook、MCP、Rule、Skill 和執行檔案，保留其他配置。

## 故障排查

| 現象 | 原因與處理 |
|------|-----------|
| Hook 沒有觸發 | 完全退出 Cursor 後重新啟動，並新建 Agent 會話。 |
| Hook 返回召回內容，但回答未使用 | 更新到最新穩定版 Cursor；舊版本可能不支援 `beforeSubmitPrompt.additional_context`。 |
| 同一事件出現多個 Business Data Platform Hook | Cursor 可能匯入了舊 Claude Code 外掛。升級或移除安裝器列出的舊 Business Data Platform plugin id，然後重啟 Cursor。 |
| MCP 未連線 | 檢查 `~/.openviking/ovcli.conf` 中的 URL/API Key，並重啟 Cursor。 |
| 需要詳細日誌 | 設定 `OPENVIKING_DEBUG=1` 後啟動 Cursor，檢視 `~/.openviking/logs/cursor-hooks.log`。 |

## 參見

- [整合能力參考](./16-capability-reference.md)
- [鑑權](../guides/04-authentication.md)
- [Cursor Hooks 文件](https://cursor.com/docs/hooks)
