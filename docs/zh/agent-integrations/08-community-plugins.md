# 社群外掛

社群維護的各執行時整合。各外掛在目標平臺、整合深度和維護狀態上各有差異，使用前請先閱讀各自的 README。

## ZCode 記憶整合

原始碼：[examples/agent-hook-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/agent-hook-plugin)

ZCode 社群整合通過配置驅動的生命週期 Hook 和 OpenViking MCP 服務提供跨專案、跨會話記憶：

- **SessionStart** 注入使用者畫像。
- **UserPromptSubmit** 召回相關記憶。
- **PreToolUse** 將直接讀取 `viking://` 的操作引導至 MCP 工具。
- **Stop** 在 detached worker 中捕獲 rollout 裡的未處理回合，並 commit OpenViking session。

ZCode 不提供 `PreCompact`、`SessionEnd` 和 subagent 生命週期 Hook。因此該介面卡在 `Stop` 時 commit，以 ZCode rollout 檔案作為權威增量對話源，只有 rollout 檔案不可用時才回退到 Hook stdin。

### 安裝

前置條件：Node.js 18+、正在執行的 OpenViking 服務，以及 ZCode。

```bash
curl -fsSL https://openviking.ai/install | bash
# AI agent 如不確定是否執行，可先閱讀指令碼頭部，其中寫明瞭它會做什麼、如何核實。
```

安裝器通過 `~/.zcode/` 或 `zcode` 二進位制檢測 ZCode，將執行時安裝到 `~/.openviking/agent-integrations/zcode/`，並把 Hook 與 MCP 配置合併到 `~/.zcode/cli/config.json`。

重啟 ZCode 後，請確認：

- `~/.zcode/cli/config.json` 包含 `hooks.enabled: true`、`hooks.events` 下的 OpenViking 條目，以及 `mcp.servers.openviking`。
- 設定 `OPENVIKING_DEBUG=1` 後，可在 `~/.openviking/logs/zcode-hooks.log` 檢視診斷日誌。

| 現象 | 原因 | 處理方式 |
|------|------|----------|
| Hook 未執行 | Hook 配置被停用或已過期 | 重跑安裝器並重啟 ZCode |
| 召回為空 | OpenViking 不可用或記憶尚未提取 | 檢查 `curl http://127.0.0.1:1933/health`，並等待提取完成 |
| MCP 工具未出現 | MCP proxy 啟動失敗 | 檢查 `~/.zcode/cli/config.json` 中 `mcp.servers.openviking` 的絕對路徑命令 |
| 重複捕獲 | 舊安裝留下了重複 Hook 條目 | 先執行 `curl -fsSL https://openviking.ai/install \| bash -s -- --uninstall --yes --harness zcode`，再重新安裝 |

實現細節與當前已驗證的 ZCode 假設見外掛目錄中的 [README](https://github.com/volcengine/OpenViking/tree/main/examples/agent-hook-plugin) 和 [DESIGN.md](https://github.com/volcengine/OpenViking/blob/main/examples/agent-hook-plugin/DESIGN.md)。

安裝完成後，在 ZCode 中新開一個會話，讓它按 https://docs.openviking.net/agents/zh/onboarding.md 執行。它會檢查連線，並帶你完成首次使用，詳見[一鍵接入](../getting-started/07-agent-onboarding.md)。

## Kimi Code 記憶整合

原始碼：[examples/agent-hook-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/agent-hook-plugin)

Kimi Code 整合是原生 managed plugin。它複用 OpenViking 的共享 Hook 執行時，只在適配層保留 Kimi 特有的事件對映、wire transcript 解碼、輸出格式和 commit 策略：

- **UserPromptSubmit** 召回記憶，並輸出 Kimi 可直接注入的原始文本。
- **PreToolUse** 拒絕 Read/Glob/Grep 直接訪問 `viking://` URI。
- **Stop**、**PreCompact** 和 **SessionEnd** 增量捕獲 `wire.jsonl` 回合；**Interrupt** 同步執行同一捕獲流程，全部 OpenViking 請求共用 2 秒總預算。
- 原生外掛 manifest 提供 OpenViking MCP server，不修改 Kimi 的舊式配置檔案。

### 安裝

前置條件：Node.js 18+、正在執行的 OpenViking 服務，以及 Kimi Code CLI。

```bash
curl -fsSL https://openviking.ai/install | bash
# AI agent 如不確定是否執行，可先閱讀指令碼頭部，其中寫明瞭它會做什麼、如何核實。
```

安裝器會在 `$KIMI_CODE_HOME/plugins/managed/openviking-memory/`
下組裝自包含執行時（Kimi home 預設為 `~/.kimi-code/`），並且只更新
`plugins/installed.json` 中的 `openviking-memory` 記錄，不動其他外掛。
重跑同一命令可升級。只解除安裝該外掛：

```bash
curl -fsSL https://openviking.ai/install | bash -s -- --uninstall --yes --harness kimicode
```

已驗證的宿主契約和版本見
[`hosts/kimicode/DESIGN.md`](https://github.com/volcengine/OpenViking/blob/main/examples/agent-hook-plugin/hosts/kimicode/DESIGN.md)。

安裝完成後，在 Kimi Code 中新開一個會話，讓它按 https://docs.openviking.net/agents/zh/onboarding.md 執行。它會檢查連線，並帶你完成首次使用，詳見[一鍵接入](../getting-started/07-agent-onboarding.md)。

## CodeBuddy Code 記憶整合

原始碼：[examples/agent-hook-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/agent-hook-plugin)

CodeBuddy Code 整合是 `agent-hook-plugin` 的宿主介面卡：複用共享的 OpenViking hook 執行時，只新增 CodeBuddy 特有的事件對映、transcript 解碼、輸出信封與提交策略：

- **SessionStart** 注入使用者畫像，並重放離線佇列中暫存的寫入。
- **UserPromptSubmit** 召回相關記憶，以 `additionalContext` 中的 `<openviking-context>` 塊注入。宿主自動生成的續寫輪次會被跳過，因此宿主自己產生的輪次不會觸發檢索。
- **PreToolUse** 拒絕把 `viking://` URI 當本地路徑讀寫，並引導 Agent 改用 OpenViking MCP 工具。Shell 命令不做檢查，`ov` 呼叫與字面量 `viking://` 引數照常可用。
- **Stop**、**PreCompact** 和 **SessionEnd** 在分離的 worker 中增量捕獲 transcript 中的新輪次。`Stop` 每捕獲 8 條訊息（`commitTurnThreshold`）提交一次 OpenViking session；`PreCompact` 和 `SessionEnd` 提交所有尚未提交的訊息，包括 `Stop` 已經傳送的。

外掛 manifest 還把 OpenViking MCP 服務以 stdio 代理的形式暴露出來，走同一份解析後的配置，並附帶 `openviking-memory`、`openviking-skills`、`ov-experience-memory` 三個 skill。hook 與 MCP 讀取同一份憑據，不會在服務端、帳號或使用者上各說各話。與其他社群介面卡一致，v1 不支援子代理採集：宿主會觸發 `SubagentStart`/`SubagentStop`，但共享 dispatcher 目前還沒有子代理階段。

### 安裝

前置條件：CodeBuddy Code、Node.js 18+，以及正在執行的 OpenViking 服務。

```bash
curl -fsSL https://openviking.ai/install | bash -s -- --yes --harness codebuddy
# AI agents: not sure about running this? The script's header says what it does and how to verify it.
```

安裝器在 `~/.openviking/agent-integrations/codebuddy/marketplace/openviking-memory/` 下組裝自包含外掛（共享 hook 執行時與各介面卡同目錄），將其註冊為名為 `openviking` 的本地 marketplace，並通過 CodeBuddy CLI 完成安裝。只移除本整合：

```bash
curl -fsSL https://openviking.ai/install | bash -s -- --uninstall --yes --harness codebuddy
```

外掛從 `~/.openviking/ovcli.conf` 讀取連線資訊；`OPENVIKING_URL` 與 `OPENVIKING_API_KEY` 可覆蓋該檔案，按外掛的配置位於 `plugin.codebuddy` 下（見[外掛配置](../configuration/02-client.md#外掛配置)）。安裝後新建會話生效（執行中的會話可用 `/reload-plugins`），並用 `codebuddy plugin list` 確認 `openviking-memory@openviking` 已啟用。

### 宿主決定的行為

`UserPromptSubmit` 與 `SessionEnd` **只在互動式 TUI 觸發**——headless 執行（`-p`、`--input-format stream-json`）不會觸發它們，因此 headless 會話只在 `Stop` 捕獲，永遠不發收尾提交。`SessionStart` 不帶 `cwd`，且同一會話內可能投遞兩次，因此該 hook 是冪等的，並以程序工作目錄兜底。hook 超時會被殺，但其子程序不會，這正是提交能在 hook 程序返回後由分離的 worker 完成的原因。

經過實測的宿主契約、transcript 格式以及本介面卡 v1 的範圍，記錄在 [`hosts/codebuddy/DESIGN.md`](https://github.com/volcengine/OpenViking/blob/main/examples/agent-hook-plugin/hosts/codebuddy/DESIGN.md)。

## AstrBot 插件

[AstrBot](https://github.com/AstrBotDevs/AstrBot) 是一個多平臺 IM Bot 框架，支援 QQ、Telegram、Discord 等 20+ 平臺。

原始碼：[astrbot_plugin_openviking_memory](https://github.com/t0saki/astrbot_plugin_openviking_memory)

為 AstrBot 提供群聊/私聊的自動捕獲、LLM 請求前的語義召回，以及可配置的 venue 記憶隔離。

**安裝**：在 AstrBot WebUI → 外掛市場搜尋 **OpenViking Memory** 並安裝；或從連結安裝：`https://github.com/t0saki/astrbot_plugin_openviking_memory.git`

當前外掛要求 AstrBot 4.23.1+ 和相容的 OpenViking 服務。`global` 使用 User Key；`venue` 需要 Admin Key 建立使用者。遷移舊配置前，先核對上方外掛 README。

**主要特性**：

- 基於 hooks 的自動召回與捕獲，模型不需要主動呼叫工具
- `self_scope=global` 共用一個 Bot 身份，`venue` 為群/私聊分別建立使用者；每個人以 peer 表示。舊版 `isolation_mode` 會對映到這兩種範圍。
- 按訊息數、token 閾值或空閒超時自動 commit
- 首次接入群聊時自動拉取平臺歷史訊息入庫

## Open WebUI tool server

[Open WebUI](https://github.com/open-webui/open-webui) 是一個自託管的 AI 聊天介面。

原始碼：[examples/openwebui-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/openwebui-plugin)

一個獨立的 FastAPI server，把 OpenViking 的一組精選端點以 OpenAPI tools 形式暴露，讓 Open WebUI 作為原生工具呼叫。部署與端點說明見 README。

## 更多示例

[examples/](https://github.com/volcengine/OpenViking/tree/main/examples) 目錄下還有 Agent 外掛之外的部署與整合示例——Grafana 面板、Kubernetes Helm chart、多租戶配置、快照流程和 SDK 片段等。

## 參見

- [整合能力參考](./16-capability-reference.md)
