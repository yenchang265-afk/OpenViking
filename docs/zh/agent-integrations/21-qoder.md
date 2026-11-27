# Qoder CLI

為 Qoder CLI 新增跨專案、跨會話的長期記憶。安裝完成後，OpenViking Hook 會在會話啟動和使用者提交問題時注入相關上下文，在回覆結束後捕獲新對話；MCP 用於主動搜尋、讀取和管理記憶。

## 安裝

前置條件：macOS 或 Linux、Node.js 18+，以及 `qodercli`（或國內版 `qoderclicn`）在 `PATH` 中的 Qoder CLI。安裝過程中會引導配置 OpenViking 連線資訊；詢問要接入哪些 Agent 時選擇 **Qoder CLI**。

連線託管例項時，選擇 **OpenViking 託管服務**，再選擇服務商：

- **Volcengine**：輸入服務 API Key，安裝器會提供服務地址。
- **BytePlus**：先輸入例項的完整 HTTPS 服務地址，再輸入 API Key。詳見 [BytePlus 接入指南](../guides/27-byteplus-setup.md)。

舊版安裝器連線 BytePlus 時使用**自定義 URL**。

服務執行在本機時選擇 **自建 / 本地**（`http://127.0.0.1:1933`）。遠端自建服務選擇**自定義 URL**並填寫其地址；已有連線時，此選項顯示為**自定義 URL / 保持當前**。

```bash
curl -fsSL https://openviking.ai/install | bash
# AI agent 如不確定是否執行，可先閱讀指令碼頭部，其中寫明瞭它會做什麼、如何核實。
```

安裝後新建一個 `qodercli` 會話生效。

安裝完成後，在 Qoder 中新開一個會話，讓它按 https://docs.openviking.net/agents/zh/onboarding.md 執行。它會檢查連線，並帶你完成首次使用，詳見[一鍵接入](../getting-started/07-agent-onboarding.md)。

如果之前從 OpenViking 的 GitHub marketplace 把 Claude Code 外掛裝進了 Qoder，安裝器會替換這個 `openviking` marketplace，兩個外掛不會重複捕獲同一會話。

## 安裝內容

安裝器在 `~/.openviking/agent-integrations/qoder/marketplace/openviking-memory/` 下組裝自包含外掛（共享 hook 執行時與介面卡同目錄），將其註冊為名為 `openviking` 的本地 marketplace，並用 `qodercli plugins install` 安裝。外掛包含：

- 生命週期 Hook：載入畫像、提問時召回、捕獲對話、提交 session，以及 `viking://` URI 保護。
- 以 stdio 代理形式提供的 OpenViking MCP 服務，含 `search`、`read`、`remember`、`add_skill` 等工具。
- `openviking-memory`、`openviking-skills`、`ov-experience-memory`、`openviking-rule-search`、`ov-memory-doctor` 五個 skill，以外掛名為字首列出，例如 `openviking-memory:openviking-skills`。

`PATH` 中的每個 Qoder CLI 版本都會裝上外掛：`qodercli` 裝在 `~/.qoder`（`QODER_CONFIG_DIR`），國內版 `qoderclicn` 裝在 `~/.qoder-cn`（`QODERCN_CONFIG_DIR`）。解除安裝時兩處都會移除。

## 驗證

1. 執行 `qodercli plugins list`，確認 `openviking-memory@openviking` 已啟用。
2. 新建會話，確認 `openviking` MCP 服務已連線。
3. 告訴 Qoder 一條測試偏好並正常結束會話。記憶抽取完成後，在同一工作區新建會話詢問它。

## 工作原理

- **SessionStart** 注入使用者畫像，並重放離線佇列中暫存的寫入。
- **UserPromptSubmit** 召回相關記憶，以 `additionalContext` 中的 `<openviking-context>` 塊注入。
- **PreToolUse** 拒絕把 `viking://` URI 當本地路徑讀寫，並引導 Agent 改用 OpenViking MCP 工具。Bash 命令中包含這種 URI 時照常執行，並附加一條指向同一組工具的提示，`ov` 呼叫與字面量 `viking://` 引數照常可用。`mcp_call` 上的第二個 `PreToolUse` 條目在 `session_history` 呼叫沒傳 `session` 引數時補上當前會話。
- 壓縮或恢復之後，**SessionStart** 還會追加一段簡短說明，給出會話的 OpenViking id 以及用來查回之前確切細節的 `session_history` MCP 工具。
- **Stop**、**PreCompact** 和 **SessionEnd** 在分離的 worker 中增量捕獲 transcript 中的新輪次。`Stop` 每捕獲 8 條訊息（`commitTurnThreshold`）提交一次 OpenViking session；`PreCompact` 和 `SessionEnd` 提交所有尚未提交的訊息，包括 `Stop` 已經發送的。

hook 與 MCP 從 `~/.openviking/ovcli.conf` 讀取同一份憑據，不會在服務端、帳號或使用者上各說各話。`OPENVIKING_URL` 與 `OPENVIKING_API_KEY` 可覆蓋該檔案，按外掛的配置位於 `plugin.qoder` 下（見[外掛配置](../configuration/02-client.md#外掛配置)）。會話在 OpenViking 中記為 `qd-<session id>`。

### 宿主決定的行為

`UserPromptSubmit` 與 `SessionEnd` 在 TUI 和 headless `-p` 執行中都會觸發，因此 headless 會話同樣會召回並提交。Qoder 把注入的上下文作為獨立的 attachment 記錄寫進 transcript；捕獲只讀取對話記錄，召回的記憶不會被再次捕獲。每次 `-p` 執行結束時還會結束一個沒有 transcript 的輔助會話，它的 `SessionEnd` 會被忽略。

Qoder 通過 `mcp_call` 懶載入 MCP 工具。在預設許可權模式的 headless 執行中，MCP 工具需要許可權規則或更寬鬆的許可權模式。外掛相關命令請使用 `qodercli`：`qoder` 遇到某些引數會開啟 Qoder IDE。

暫不支援子代理採集：宿主會觸發 `SubagentStart`/`SubagentStop`，但共享 dispatcher 還沒有子代理階段。經過實測的宿主契約與 transcript 格式記錄在 [`hosts/qoder/DESIGN.md`](https://github.com/volcengine/OpenViking/blob/main/examples/agent-hook-plugin/hosts/qoder/DESIGN.md)。

## 升級與解除安裝

重新執行安裝命令即可升級。解除安裝：

```bash
curl -fsSL https://openviking.ai/install | bash -s -- --uninstall --yes --harness qoder
```

解除安裝會移除外掛、其本地 marketplace、Qoder 快取的副本以及執行時檔案，其他配置保持不變。

## 故障排查

| 現象 | 原因與處理 |
|------|------------|
| `-p` 執行中 MCP 工具請求授權 | 為 `openviking` MCP 服務新增許可權規則，或使用更寬鬆的許可權模式。 |
| 外掛列表中沒有它 | 重新執行安裝器並確認 `qodercli` 在 `PATH` 中，然後新建會話。 |
| MCP 連不上 | 檢查 `~/.openviking/ovcli.conf` 中的 URL/API Key，然後新建會話。 |
| 需要詳細診斷 | 以 `OPENVIKING_DEBUG=1` 啟動 Qoder，檢視 `~/.openviking/logs/qoder-hooks.log`。 |

## 參見

- [能力參考](./16-capability-reference.md)
- [認證](../guides/04-authentication.md)
- [原始碼：examples/agent-hook-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/agent-hook-plugin)
- [Qoder CLI 外掛](https://docs.qoder.com/cli/plugins)
