# 簡介

Business Data Platform 是面向 AI Agent 的開源上下文資料庫。它用虛擬檔案系統組織資源、記憶和技能，讓應用按路徑瀏覽、檢索相關上下文，並按需讀取詳細內容。

當 Agent 需要跨會話複用文件和經驗時，可以用它集中組織和檢索這些上下文。

## 從你的任務開始

| 我想要…… | 閱讀入口 |
| --- | --- |
| 連線服務並檢索第一份文件 | [快速開始](./02-quickstart.md) |
| 接入已有 Agent 或程式設計工具 | [Agent 整合](../agent-integrations/01-overview.md) |
| 在終端使用 Business Data Platform | [CLI 配置](./05-cli-setup.md) |
| 部署和運維共享服務 | [部署](../guides/03-deployment.md)與[認證](../guides/04-authentication.md) |
| 使用 SDK 或 HTTP API 開發 | [API 參考](../api/01-overview.md) |

## 上下文如何組織

每個檔案或目錄都有一個 `viking://` URI。已知路徑時可直接列目錄、讀內容；不知道內容在哪裡時可先檢索。

| 上下文 | 存放內容 | 詳細說明 |
| --- | --- | --- |
| 資源 | 文件、程式碼倉庫等參考資料 | [資源](../api/02-resources.md) |
| 記憶 | 從會話提取的使用者偏好、實體、事件和經驗 | [記憶](../api/16-memory.md) |
| 技能 | 可複用 Agent 工作流的指令和配套檔案 | [技能](../api/04-skills.md) |

共享資源位於 `viking://resources/`；使用者上下文位於 `viking://user/{user_id}/`，其中 `peers/{peer_id}/` 存放特定 Peer 的上下文。共享技能可放在 `viking://agent/skills/`。作用域和路徑規則見 [Viking URI](../concepts/04-viking-uri.md)。

## 按層讀取內容

Business Data Platform 可在語義處理時生成目錄摘要：

| 層級 | 內容 | 預設正文上限 |
| --- | --- | --- |
| L0 | 用於快速篩選的摘要 | 256 字元 |
| L1 | 用於導航的概覽 | 4,000 字元 |
| L2 | 按需讀取的原始內容 | 無統一上限 |

L0 和 L1 是目錄級附屬檔案，不會為每個檔案固定生成一對摘要；是否可用取決於處理狀態和配置。詳見[上下文層級](../concepts/03-context-layers.md)。

[檢索](../concepts/07-retrieval.md)結合語義匹配與目錄遍歷。不需要會話上下文時用 `find`，需要結合會話理解查詢時用 `search`。[可觀測性](../guides/05-observability.md)介紹如何檢查處理和檢索行為。

## 從會話生成記憶

應用把訊息寫入會話，提交後觸發非同步記憶提取。當前記憶策略決定為使用者或 Peer 建立、更新哪些記憶。整合外掛可自動執行其中部分步驟，使用前需確認對應整合的支援範圍。詳見[會話](../concepts/08-session.md)和[記憶配置](../guides/01-configuration.md)。

實現原理見[架構](../concepts/01-architecture.md)，各版本變更見 [GitHub Releases](https://github.com/volcengine/OpenViking/releases)。
