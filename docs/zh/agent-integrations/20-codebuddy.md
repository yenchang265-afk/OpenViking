# CodeBuddy Code

為 CodeBuddy Code 新增跨專案、跨會話的長期記憶。安裝完成後，OpenViking Hook 會在會話啟動和使用者提交問題時注入相關上下文，在回覆結束後捕獲新對話；MCP 用於主動搜尋、讀取和管理記憶。

## 安裝

前置條件：macOS 或 Linux、Node.js 18+，以及 `codebuddy` CLI 在 `PATH` 中的 CodeBuddy Code。安裝過程中會引導配置 OpenViking 連線資訊；詢問要接入哪些 Agent 時選擇 **CodeBuddy Code**。

安裝器詢問連線方式時，火山引擎雲服務使用者請選擇 **火山引擎 OpenViking 雲服務** 並填寫 API Key。服務執行在本機時選擇 **自建 / 本地**（`http://127.0.0.1:1933`）；遠端自建服務請選擇 **自定義 URL / 保持當前** 並填寫其 URL。

```bash
curl -fsSL https://openviking.ai/install | bash
# AI agent 如不確定是否執行，可先閱讀指令碼頭部，其中寫明瞭它會做什麼、如何核實。
```

安裝後新建 CodeBuddy 會話生效；執行中的會話可用 `/reload-plugins` 載入。

安裝完成後，在 CodeBuddy 中新開一個會話，讓它按 https://docs.openviking.net/agents/zh/onboarding.md 執行。它會檢查連線，並帶你完成首次使用，詳見[一鍵接入](../getting-started/07-agent-onboarding.md)。

## 安裝內容

安裝器在 `~/.openviking/agent-integrations/codebuddy/marketplace/openviking-memory/` 下組裝自包含外掛（共享 hook 執行時與介面卡同目錄），將其註冊為名為 `openviking` 的本地 marketplace，並通過 CodeBuddy CLI 完成安裝。外掛包含：

- 生命週期 Hook：載入畫像、提問時召回、捕獲對話、提交 session，以及 `viking://` URI 保護。
- 以 stdio 代理形式提供的 OpenViking MCP 服務，含 `search`、`read`、`remember`、`add_skill` 等工具。
- `openviking-memory`、`openviking-skills`、`ov-experience-memory`、`openviking-rule-search` 四個 skill。

## 驗證

1. 執行 `codebuddy plugin list`，確認 `openviking-memory@openviking` 已啟用。
2. 新建一個互動式會話，確認 `openviking` MCP 服務已連線。
3. 告訴 CodeBuddy 一條測試偏好並正常結束會話。記憶抽取完成後，在同一工作區新建會話詢問它。

## 工作原理

- **SessionStart** 注入使用者畫像，並重放離線佇列中暫存的寫入。
- **UserPromptSubmit** 召回相關記憶，以 `additionalContext` 中的 `<openviking-context>` 塊注入。宿主自動生成的續寫輪次會被跳過，因此宿主自己產生的輪次不會觸發檢索。
- **PreToolUse** 拒絕把 `viking://` URI 當本地路徑讀寫，並引導 Agent 改用 OpenViking MCP 工具。Shell 命令不做檢查，`ov` 呼叫與字面量 `viking://` 引數照常可用。
- **Stop**、**PreCompact** 和 **SessionEnd** 在分離的 worker 中增量捕獲 transcript 中的新輪次。`Stop` 每捕獲 8 條訊息（`commitTurnThreshold`）提交一次 OpenViking session；`PreCompact` 和 `SessionEnd` 提交所有尚未提交的訊息，包括 `Stop` 已經發送的。

hook 與 MCP 從 `~/.openviking/ovcli.conf` 讀取同一份憑據，不會在服務端、帳號或使用者上各說各話。`OPENVIKING_URL` 與 `OPENVIKING_API_KEY` 可覆蓋該檔案，按外掛的配置位於 `plugin.codebuddy` 下（見[外掛配置](../configuration/02-client.md#外掛配置)）。會話在 OpenViking 中記為 `cb-<session id>`。

### 宿主決定的行為

`UserPromptSubmit` 與 `SessionEnd` **只在互動式 TUI 觸發**。headless 執行（`-p`、`--input-format stream-json`）不會觸發它們，因此 headless 會話只在 `Stop` 捕獲，不發收尾提交。`SessionStart` 不帶 `cwd`，且同一會話內可能投遞兩次，因此該 hook 是冪等的，並以程序工作目錄兜底。hook 超時會被殺，但其子程序不會，這正是提交能在 hook 程序返回後由分離的 worker 完成的原因。

暫不支援子代理採集：宿主會觸發 `SubagentStart`/`SubagentStop`，但共享 dispatcher 還沒有子代理階段。經過實測的宿主契約與 transcript 格式記錄在 [`hosts/codebuddy/DESIGN.md`](https://github.com/volcengine/OpenViking/blob/main/examples/agent-hook-plugin/hosts/codebuddy/DESIGN.md)。

## 升級與解除安裝

重新執行安裝命令即可升級。解除安裝：

```bash
curl -fsSL https://openviking.ai/install | bash -s -- --uninstall --yes --harness codebuddy
```

解除安裝會移除外掛、其本地 marketplace、CodeBuddy 快取的副本以及執行時檔案，其他配置保持不變。

## 故障排查

| 現象 | 原因與處理 |
|------|------------|
| headless 執行沒有召回 | `UserPromptSubmit` 只在互動式 TUI 觸發，請使用互動式會話。 |
| 外掛列表中沒有它 | 重新執行安裝器並確認 `codebuddy` 在 `PATH` 中，然後新建會話。 |
| MCP 連不上 | 檢查 `~/.openviking/ovcli.conf` 中的 URL/API Key，然後新建會話。 |
| 需要詳細診斷 | 以 `OPENVIKING_DEBUG=1` 啟動 CodeBuddy，檢視 `~/.openviking/logs/codebuddy-hooks.log`。 |

## 參見

- [能力參考](./16-capability-reference.md)
- [認證](../guides/04-authentication.md)
- [原始碼：examples/agent-hook-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/agent-hook-plugin)
