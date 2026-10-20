# 選擇 Agent 接入方式

OpenViking 可以作為多種 Agent 執行時的長期記憶與上下文後端。按你的執行時挑選合適的接入方式即可。

## 該用哪個整合？

| 你在用… | 選這個 |
|---------|---------|
| **Claude Code** | [Claude Code 記憶外掛](./02-claude-code.md) — 通過 hooks 實現自動召回與自動捕獲 |
| **OpenClaw** | [OpenClaw 外掛](./03-openclaw.md) — 全生命週期一體化整合 |
| **Codex / TraeCode CLI 2.0** | [Codex 記憶外掛](./04-codex.md) — 生命週期 hooks 自動召回與增量捕獲 |
| **Cursor** | [Cursor 記憶整合](./12-cursor.md) — 一條命令安裝生命週期 Hook、MCP 工具、Rules 與 Skills |
| **TRAE / TRAE CN** | [TRAE 記憶整合](./13-trae.md) — 一個安裝器完成 prompt 召回、回合捕獲與 OpenViking 工具接入 |
| **DeepSeek Harness（`dsh`）** | [DeepSeek Harness 記憶外掛](./17-dsh.md) — 程序內 Cordis 外掛，pre-step 召回、事件捕獲與 OpenViking MCP 工具 |
| **Hermes Agent** | [Hermes Agent](./05-hermes.md)。自動捕獲和召回記憶，舊版本使用內建提供方。 |
| **OpenCode** | [OpenCode 外掛](./10-opencode.md) — MCP 工具 + 生命週期 hooks，覆蓋倉庫上下文、自動召回與捕獲 |
| **pi** | [pi Coding Agent 擴充](./11-pi.md) — 原生擴充，自動召回、逐輪捕獲、閾值 commit，並把服務端的 MCP 工具註冊為 pi 原生工具 |
| **LangChain / LangGraph** | [LangChain 和 LangGraph](./07-langchain-langgraph.md) — retriever、tools、context backend、store 和 middleware |
| **多個本地開發 Agent / 希望使用桌面介面** | [OpenViking Helper](./14-openviking-helper.md) — 視覺化完成 Agent 接入、會話分析和記憶管理 |
| **任意支援 Agent Plugins 1.0 的客戶端** | [Agent Plugins 1.0 外掛包](./15-agent-plugins.md) — 一個可移植的包：`openviking-memory` 技能 + OpenViking MCP 工具 |
| **Manus / Claude Desktop / ChatGPT / 其他 MCP 客戶端** | [MCP 客戶端](./06-mcp-clients.md) — 任何相容 MCP 的客戶端直接對接內建 `/mcp` 端點 |
| **聊天客戶端 / SDK 與 API 應用 / 其他沒有外掛的客戶端** | [OpenViking 閘道器](../guides/15-gateway.md) — 能填 Base URL 和 API Key 的客戶端都能接入閘道器，由閘道器召回記憶、儲存對話，客戶端裡不用裝任何東西 |
| **ZCode / AstrBot / …** | [社群外掛](./08-community-plugins.md) — 社群維護的各執行時整合 |

Claude Code、Codex、OpenCode、pi、DSH 等 Agent 既能用自己的外掛，也能接入 OpenViking 閘道器。兩者怎麼選，見[閘道器還是外掛](../guides/15-gateway.md#gateway-or-plugin)。

## 橫向對比各整合能力

想知道各個整合在工具面、自動召回、會話與 commit、壓縮接管、降級容錯上的具體差異，見 [整合能力參考](./16-capability-reference.md)——一份覆蓋全部整合的橫向對照矩陣。

## 開發與維護外掛

新增或維護整合時，請遵循 [Hook + MCP Agent 外掛開發與維護規範](./18-plugin-development.md)。使用 VibeCoding 時，務必讓 coding agent 在修改前閱讀並遵循該規範；實現可以參考 Claude Code、Codex 和其他現有外掛。

## 所有集成的共同前置

本頁所有整合都需要連線到一個正在執行的 OpenViking 服務。如果你還沒有，請先按 [快速開始](../getting-started/02-quickstart.md) 部署。預設端點是 `http://localhost:1933`；遠端使用需要 API Key（參見 [鑑權](../guides/04-authentication.md)）。

## 低延遲召回

接入並驗證外掛後，可按[調整召回延遲](19-recall-tuning.md)配置查詢擴充、結果壓縮與超時。
