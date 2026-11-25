# 社群外掛

社群維護的各執行時整合。各外掛在目標平臺、整合深度和維護狀態上各有差異，使用前請先閱讀各自的 README。

## ZCode 記憶整合

原始碼：[examples/agent-hook-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/agent-hook-plugin)

ZCode 社群整合通過配置驅動的生命週期 Hook、OpenViking MCP 服務和 5 個 skill 提供跨專案、跨會話記憶：

- **SessionStart** 注入使用者畫像。
- **UserPromptSubmit** 召回相關記憶。
- **PreToolUse** 將直接讀取 `viking://` 的操作引導至 MCP 工具。
- **Stop** 在 detached worker 中捕獲 rollout 裡的未處理回合，並 commit OpenViking session。

ZCode 不提供 `PreCompact`、`SessionEnd` 和 subagent 生命週期 Hook。因此該介面卡在 `Stop` 時 commit，以 ZCode rollout 檔案作為權威增量對話源，只有 rollout 檔案不可用時才回退到 Hook stdin。

### 安裝

前置條件：Node.js 18+、正在執行的 OpenViking 服務，以及 ZCode。

連線託管例項時，選擇 **OpenViking 託管服務**，再選擇服務商：

- **Volcengine**：輸入服務 API Key，安裝器會提供服務地址。
- **BytePlus**：先輸入例項的完整 HTTPS 服務地址，再輸入 API Key。詳見 [BytePlus 接入指南](../guides/27-byteplus-setup.md)。

舊版安裝器連線 BytePlus 時使用**自定義 URL**。

```bash
curl -fsSL https://openviking.ai/install | bash
# AI agent 如不確定是否執行，可先閱讀指令碼頭部，其中寫明瞭它會做什麼、如何核實。
```

安裝器通過 `~/.zcode/` 或 `zcode` 二進位制檢測 ZCode，將執行時安裝到 `~/.openviking/agent-integrations/zcode/`，並把 Hook 與 MCP 配置合併到 `~/.zcode/cli/config.json`，再把 `openviking-memory`、`openviking-skills`、`ov-experience-memory`、`openviking-rule-search` 和 `ov-memory-doctor` 安裝到 `~/.zcode/skills/<name>`。你修改過的 skill，或已有的同名非託管目錄，在升級和解除安裝時保留。

重啟 ZCode 後，請確認：

- `~/.zcode/cli/config.json` 包含 `hooks.enabled: true`、`hooks.events` 下的 OpenViking 條目，以及 `mcp.servers.openviking`。
- `~/.zcode/skills/` 下有上述 5 個 skill 目錄，每個目錄包含 `SKILL.md`。
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
- 原生外掛 manifest 提供 OpenViking MCP server 和外掛根目錄 `skills/` 下的 `openviking-memory`、`openviking-skills`、`ov-experience-memory`、`openviking-rule-search`、`ov-memory-doctor` 5 個 skill，不修改 Kimi 的舊式配置檔案。

### 安裝

前置條件：Node.js 18+、正在執行的 OpenViking 服務，以及 Kimi Code CLI。

連線託管例項時，選擇 **OpenViking 託管服務**，再選擇服務商：

- **Volcengine**：輸入服務 API Key，安裝器會提供服務地址。
- **BytePlus**：先輸入例項的完整 HTTPS 服務地址，再輸入 API Key。詳見 [BytePlus 接入指南](../guides/27-byteplus-setup.md)。

舊版安裝器連線 BytePlus 時使用**自定義 URL**。

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

## Antigravity 記憶整合

原始碼：[examples/agent-hook-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/agent-hook-plugin)

Antigravity 整合同時服務 Antigravity 桌面 app 與 `agy` CLI，兩者從 `~/.gemini/config/plugins/` 載入同一批外掛：

- **SessionStart** 注入使用者畫像。
- **PreInvocation** 在每輪的第一次模型呼叫時召回相關記憶。Antigravity 在每次模型呼叫前都會執行這個 Hook，工具迴圈中的後續呼叫會跳過召回。
- **PreToolUse** 拒絕位置引數為 `viking://` URI 的檔案工具呼叫，並引導至 OpenViking MCP 工具。Shell 命令（`run_command`）不檢查。
- **Stop** 在後臺程序中採集對話 transcript 裡已完成的步驟，然後 commit OpenViking 會話。

Antigravity 的 `hooks.json` 格式與 Claude Code 不同：頂層 key 是 Hook 名，上下文以 `injectSteps` 系統訊息返回，因此不能直接複用 Claude Code 的 `hooks.json`。

外掛還帶有 OpenViking MCP 服務和 `openviking-memory`、`openviking-skills`、`ov-experience-memory`、`openviking-rule-search`、`ov-memory-doctor` 5 個 skill：Agent 可以通過 MCP 工具主動檢索和管理記憶，每個 skill 也可以用 `/<name>` 呼叫。

### 安裝

前置條件：Node.js 18+、執行中的 OpenViking 服務，以及 Antigravity app 或 `agy`。

此非互動命令使用 `~/.openviking/ovcli.conf` 中已儲存的連線。請先執行 `ov config`，選擇 **OpenViking 託管服務**，再選擇 **Volcengine**（服務 API Key）或 **BytePlus**（完整 HTTPS 服務地址和 API Key）。詳見 [BytePlus 接入指南](../guides/27-byteplus-setup.md#連線-cli)。

```bash
curl -fsSL https://openviking.ai/install | bash -s -- --yes --harness antigravity
```

安裝指令碼把外掛寫到 `~/.gemini/config/plugins/openviking-memory`，執行時寫到 `~/.openviking/agent-integrations/antigravity`。如果同名目錄已存在且不是 OpenViking 寫入的，安裝指令碼會保留它並停止。連線配置與其他整合一樣讀取 `~/.openviking/ovcli.conf`。外掛目錄包含 `plugin.json`、`hooks.json`、`mcp_config.json` 和 `skills/`。如果 `~/.gemini/config/mcp_config.json` 已經定義了名為 `openviking` 的 MCP 服務，安裝指令碼保留你的服務，不寫外掛的 `mcp_config.json`，避免每個工具出現兩次。

重啟 Antigravity app 或開啟新的 `agy` 會話後，確認：

- `~/.gemini/antigravity-cli/log/` 下的 `agy` 日誌出現 `loaded 1 named hooks`；
- 一輪對話結束後，`~/.openviking/hook-state/antigravity/<conversation-id>.json` 記錄了 `lastStep`；
- 外掛目錄下有 `skills/openviking-memory/SKILL.md`，並且除非你自己的配置裡已有 `openviking` 服務，還有 `mcp_config.json`。

解除安裝：

```bash
curl -fsSL https://openviking.ai/install | bash -s -- --uninstall --yes --harness antigravity
```

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
