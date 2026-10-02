# OpenViking Helper

OpenViking Helper 是面向本地開發 Agent 的桌面控制台。它把原本分散在命令列、配置檔案和安裝指令碼中的 OpenViking 接入流程集中到一個介面裡，並提供會話分析、本地記憶和技能管理能力。

Helper 不會替代 Claude Code、Codex、Cursor、TRAE 或 OpenCode 的整合；它使用同一套 OpenViking 配置，幫助你完成安裝、檢查接入狀態，並檢視 OpenViking 在實際會話中是否生效。

OpenViking Helper 目前處於 Beta 階段，支援 macOS 和 Windows x64，應用介面支援中文和 English，可在 **設定 → 通用 → 介面語言** 中隨時切換。

## 下載

| 平臺 | 架構 | 下載 |
|------|------|------|
| macOS | Apple Silicon（arm64） | [下載 DMG](https://lf3-cdn-tos.bytegoofy.com/obj/tron-demo/7654844610543360265/420238785/0.0.19/darwin-arm64/openviking-helper-0.0.19-arm64.dmg) |
| macOS | Intel（x64） | [下載 DMG](https://lf3-cdn-tos.bytegoofy.com/obj/tron-demo/7654844610543360265/420238785/0.0.19/darwin-x64/openviking-helper-0.0.19-x64.dmg) |
| Windows | x64 | [下載安裝程式](https://lf3-cdn-tos.bytegoofy.com/obj/tron-demo/7654844610543360265/420238785/0.0.19/win32-x64/openviking-helper-0.0.19-x64.exe) |

## 開始使用

1. 下載並啟動與你的平臺和架構匹配的安裝包。
2. 開啟 **設定 → 配置**，選擇火山引擎託管服務或自建 OpenViking 服務，填寫連線資訊並執行連線測試。
3. 開啟 **設定 → Agent 接入**。Helper 會檢測本機的 OpenViking CLI、Claude Code、Codex、Cursor、TRAE 和 OpenCode。
4. 為需要使用的 Agent 安裝或配置對應的外掛、MCP、Hook 或 CLI 接入，然後按介面提示重啟 Agent。
5. 在 **會話**、**記憶** 和 **技能** 頁面檢查接入效果與本地資料。

## 視覺化接入 Agent

Helper 會檢測已安裝的本地 Agent，並展示 OpenViking 的接入狀態。你可以在介面中維護多個 OpenViking 服務配置、切換當前配置、測試連線，併為支援的 Agent 執行接入或重新安裝。

![OpenViking Helper 的 Agent 接入頁面](../../images/openviking-helper/agent-access.webp)

Agent 的具體能力仍取決於對應整合。例如，Claude Code、Codex、Cursor、TRAE 和 OpenCode 的生命週期 Hook、MCP 工具及自動召回能力，請以各自的整合文件為準。

## 檢視會話軌跡

Helper 可以解析 Claude Code、Codex 和 TRAE 的本地會話，並按 Agent 和專案展示時間線。通過會話詳情可以檢查 OpenViking 的關鍵動作，例如：

- Prompt 前是否發生記憶召回和上下文注入；
- 本輪是否呼叫 OpenViking MCP 工具；
- 回覆結束後是否捕獲新增對話；
- 上下文壓縮前是否提交會話；
- 會話啟動、結束等生命週期動作是否觸發。

![OpenViking Helper 的會話時間線](../../images/openviking-helper/session-timeline.webp)

這些資訊適合用來確認接入是否真實生效，以及定位配置、Hook 或 MCP 連線問題。

## 管理記憶與技能

Helper 會按 Agent 和專案展示本地 memory、rule 檔案及 `SKILL.md` 技能。你可以檢視檔案內容、路徑、更新時間和同步狀態，並將選中的本地內容同步到當前 OpenViking 服務。

![OpenViking Helper 的本地記憶管理頁面](../../images/openviking-helper/memory-overview.webp)

同步完成後，可以繼續在 Helper 中檢視 OpenViking 服務端的記憶分類與內容。不同 Agent 原本分散儲存的長期資訊，也可以通過 OpenViking 統一檢索和複用。

## 本地資料與隱私

為展示接入狀態、會話和記憶，Helper 會讀取本機對應 Agent 的配置與本地資料。只有執行同步或使用 OpenViking 服務能力時，相關內容才會傳送到當前啟用的服務配置。同步前請確認服務地址，並檢查待同步內容是否包含敏感資訊。

## 參見

- [整合能力參考](./16-capability-reference.md)
- [Agent 整合概覽](./01-overview.md)
- [Claude Code 記憶外掛](./02-claude-code.md)
- [Codex 記憶外掛](./04-codex.md)
- [Cursor 記憶整合](./12-cursor.md)
- [TRAE 記憶整合](./13-trae.md)
- [OpenCode 插件](./10-opencode.md)
