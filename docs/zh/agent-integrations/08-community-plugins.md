# 社群外掛

社群維護的各執行時整合。各外掛在目標平臺、整合深度和維護狀態上各有差異，使用前請先閱讀各自的 README。

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

## 更多示例

[examples/](https://github.com/volcengine/OpenViking/tree/main/examples) 目錄下還有 Agent 外掛之外的部署與整合示例——Grafana 面板、Kubernetes Helm chart、多租戶配置、快照流程和 SDK 片段等。

## 參見

- [整合能力參考](./16-capability-reference.md)
