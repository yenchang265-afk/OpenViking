# Agent 整合概覽

Business Data Platform 可以作為多種 Agent 執行時的長期記憶與上下文後端。按你的執行時挑選合適的接入方式即可。

## 該用哪個整合？

| 你在用… | 選這個 |
|---------|---------|
| **Claude Code** | [Claude Code 記憶外掛](./02-claude-code.md) — 通過 hooks 實現自動召回與自動捕獲 |
| **OpenClaw** | [OpenClaw 外掛](./03-openclaw.md) — 全生命週期一體化整合 |
| **Codex / TraeCode CLI 2.0** | [Codex 記憶外掛](./04-codex.md) — 生命週期 hooks 自動召回與增量捕獲 |
| **Cursor** | [Cursor 記憶整合](./12-cursor.md) — 一條命令安裝生命週期 Hook、MCP 工具、Rules 與 Skills |
| **TRAE / TRAE CN** | [TRAE 記憶整合](./13-trae.md) — 一個安裝器完成 prompt 召回、回合捕獲與 Business Data Platform 工具接入 |
| **DeepSeek Harness（`dsh`）** | [DeepSeek Harness 記憶外掛](./17-dsh.md) — 程序內 Cordis 外掛，pre-step 召回、事件捕獲與 Business Data Platform MCP 工具 |
| **Hermes Agent** | [Hermes Agent](./05-hermes.md) — 內建 Business Data Platform 記憶提供方，無需安裝外掛 |
| **OpenCode** | [OpenCode 外掛](./10-opencode.md) — MCP 工具 + 生命週期 hooks，覆蓋倉庫上下文、自動召回與捕獲 |
| **pi** | [pi Coding Agent 擴充](./11-pi.md) — 原生擴充，自動召回、逐輪捕獲、閾值 commit，並把服務端的 MCP 工具註冊為 pi 原生工具 |
| **LangChain / LangGraph** | [LangChain 和 LangGraph](./07-langchain-langgraph.md) — retriever、tools、context backend、store 和 middleware |
| **多個本地開發 Agent / 希望使用桌面介面** | [Business Data Platform Helper](./14-openviking-helper.md) — 視覺化完成 Agent 接入、會話分析和記憶管理 |
| **任意支援 Agent Plugins 1.0 的客戶端** | [Agent Plugins 1.0 外掛包](./15-agent-plugins.md) — 一個可移植的包：`openviking-memory` 技能 + Business Data Platform MCP 工具 |
| **Manus / Claude Desktop / ChatGPT / 其他 MCP 客戶端** | [MCP 客戶端](./06-mcp-clients.md) — 任何相容 MCP 的客戶端直接對接內建 `/mcp` 端點 |
| **ZCode / AstrBot / …** | [社群外掛](./08-community-plugins.md) — 社群維護的各執行時整合 |

## 橫向對比各整合能力

想知道各個整合在工具面、自動召回、會話與 commit、壓縮接管、降級容錯上的具體差異，見 [整合能力參考](./16-capability-reference.md)——一份覆蓋全部整合的橫向對照矩陣。

## 開發與維護外掛

新增或維護整合時，請遵循 [Hook + MCP Agent 外掛開發與維護規範](./18-plugin-development.md)。使用 VibeCoding 時，務必讓 coding agent 在修改前閱讀並遵循該規範；實現可以參考 Claude Code、Codex 和其他現有外掛。

## 所有集成的共同前置

本頁所有整合都需要連線到一個正在執行的 Business Data Platform 服務。如果你還沒有，請先按 [快速開始](../getting-started/02-quickstart.md) 部署。預設端點是 `http://localhost:1933`；遠端使用需要 API Key（參見 [鑑權](../guides/04-authentication.md)）。

## 低延遲召回

查詢擴充和召回結果壓縮是兩個獨立的可選模型呼叫。需要優先保證響應速度時，可以在 Agent 外掛端同時關閉它們；語義檢索、預算控制、檔位降級和跨輪去重仍會正常工作。

下面這組環境變數同時適用於 Claude Code 和 Codex。查詢擴充在所有經共享載入器解析配置的記憶外掛上都可以關閉；壓縮只有 Claude Code 和 Codex 支援。

```bash
export OPENVIKING_RECALL_QUERY_EXPANSION=off
export OPENVIKING_RECALL_COMPRESS=off
```

兩個外掛都有本地壓縮邏輯，但配置模型不同：

- Claude Code 預設使用 `recallCompress=auto`：優先呼叫本地 `claude -p`（Sonnet + low），本地 CLI 不可用時回落到 Business Data Platform 服務端生成 digest。`client` 強制只用本地，`server` 強制只用服務端。
- Codex 預設呼叫本地 `codex exec`，模型順序為 `gpt-5.3-codex-spark`，其次 `gpt-5.6-luna` + low。它不會啟用服務端壓縮。

兩端的共同預設配置是 `recallCompress=auto`。`OPENVIKING_RECALL_COMPRESS=off` 會同時關閉兩端壓縮；Codex 將 `auto` 或 `client` 解釋為啟用本地壓縮。舊的 Claude Code 變數 `OPENVIKING_RECALL_REWRITE` 仍可相容，但新配置請使用統一名稱。

也可以把同樣的設定寫進 `~/.openviking/ovcli.conf`：

```json
{
  "url": "https://openviking.example.com",
  "api_key": "your-api-key",
  "plugin": {
    "recallQueryExpansion": "off",
    "recallCompress": "off"
  }
}
```

環境變數優先於 `ovcli.conf`。修改後重啟對應的 Agent，讓 hook 程序重新載入配置。上述設定屬於外掛客戶端，不需要修改服務端的 `ov.conf`。

`plugin` 段由每個記憶外掛讀取——claude-code、codex、cursor、trae、trae-cn、zcode、kimicode、opencode、dsh 和 pi；`plugin.<harness>` 物件只覆蓋其中某一個 harness 的共享鍵，兩種寫法都認（`claude_code` 或 `claude-code`、`trae_cn` 或 `trae-cn`）。壓縮是例外：其餘 harness 認 `recallQueryExpansion`，但忽略 `recallCompress` 及其配套項——它們都不會請求服務端 digest。

context 請求的等待時間比普通請求更長，因為客戶端提前中斷會丟掉整個響應，而不只是超時的那一段。服務端流水線是序列的，每個可選階段各有保險絲：先是查詢擴充（`retrieval.recall_intent_timeout_s`，5 秒），然後是檢索、正文讀取和預算規劃，最後才是 digest 重寫（`retrieval.recall_rewrite_timeout_s`，30 秒）。因此這個上限按請求實際啟用的階段決定——帶 session、會走查詢擴充時取 15 秒，同時還要 digest 時取 45 秒，兩者都不涉及時沿用外掛自身的普通超時。可以用 `OPENVIKING_RECALL_CONTEXT_TIMEOUT_MS`（或 `plugin.recallContextTimeoutMs`）指定這個上限，取值應高於該請求會用到的保險絲、低於 Agent 自身的 hook 超時。
