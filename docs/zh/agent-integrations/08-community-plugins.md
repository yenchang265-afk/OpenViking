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
bash <(curl -fsSL https://raw.githubusercontent.com/volcengine/OpenViking/main/examples/memory-plugin-shared/install.sh) \
  --harness zcode
```

GitHub 不可用的地區可使用 TOS 映象：

```bash
bash <(curl -fsSL https://ovrelease.tos-cn-beijing.volces.com/memory-plugin-shared/install.sh) \
  --harness zcode --dist tos
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
| 重複捕獲 | 舊安裝留下了重複 Hook 條目 | 先執行 `install.sh --harness zcode --uninstall`，再重新安裝 |

實現細節與當前已驗證的 ZCode 假設見外掛目錄中的 [README](https://github.com/volcengine/OpenViking/tree/main/examples/agent-hook-plugin) 和 [DESIGN.md](https://github.com/volcengine/OpenViking/blob/main/examples/agent-hook-plugin/DESIGN.md)。

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
bash <(curl -fsSL https://raw.githubusercontent.com/volcengine/OpenViking/main/examples/memory-plugin-shared/install.sh) \
  --harness kimicode
```

GitHub 不可用的地區可使用 TOS 映象：

```bash
bash <(curl -fsSL https://ovrelease.tos-cn-beijing.volces.com/memory-plugin-shared/install.sh) \
  --harness kimicode --dist tos
```

安裝器會在 `$KIMI_CODE_HOME/plugins/managed/openviking-memory/`
下組裝自包含執行時（Kimi home 預設為 `~/.kimi-code/`），並且只更新
`plugins/installed.json` 中的 `openviking-memory` 記錄，不動其他外掛。
重跑同一命令可升級；加上 `--uninstall` 只解除安裝該外掛。

已驗證的宿主契約和版本見
[`hosts/kimicode/DESIGN.md`](https://github.com/volcengine/OpenViking/blob/main/examples/agent-hook-plugin/hosts/kimicode/DESIGN.md)。

## AstrBot 插件

[AstrBot](https://github.com/AstrBotDevs/AstrBot) 是一個多平臺 IM Bot 框架，支援 QQ、Telegram、Discord 等 20+ 平臺。

原始碼：[astrbot_plugin_openviking_memory](https://github.com/t0saki/astrbot_plugin_openviking_memory)

為 AstrBot 提供群聊/私聊的自動捕獲、LLM 請求前的語義召回，以及可配置的 venue 記憶隔離。

**安裝**：在 AstrBot WebUI → 外掛市場搜尋 **OpenViking Memory** 並安裝；或從連結安裝：`https://github.com/t0saki/astrbot_plugin_openviking_memory.git`

**主要特性**：

- 基於 hooks 的自動召回與捕獲，模型不需要主動呼叫工具
- 三檔隔離模式：`venue_user`（群/私聊各自獨立）、`venue_user_fanout`（跨群共享）、`global_user`（全域共享）
- 四觸發器自動 commit：訊息計數、token 閾值、空閒超時、程序退出 flush
- 首次接入群聊時自動拉取平臺歷史訊息入庫

## Open WebUI tool server

[Open WebUI](https://github.com/open-webui/open-webui) 是一個自託管的 AI 聊天介面。

原始碼：[examples/openwebui-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/openwebui-plugin)

一個獨立的 FastAPI server，把 OpenViking 的一組精選端點以 OpenAPI tools 形式暴露，讓 Open WebUI 作為原生工具呼叫。部署與端點說明見 README。

## 更多示例

[examples/](https://github.com/volcengine/OpenViking/tree/main/examples) 目錄下還有 Agent 外掛之外的部署與整合示例——Grafana 面板、Kubernetes Helm chart、多租戶配置、快照流程和 SDK 片段等。

## 參見

- [整合能力參考](./16-capability-reference.md)
