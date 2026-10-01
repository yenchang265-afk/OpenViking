# 路線圖

本頁區分當前 `main` 分支的實現與後續方向，不承諾釋出時間或優先順序。已釋出版本請查閱 [release notes](https://github.com/volcengine/OpenViking/releases)。

## main 已實現

- **上下文與檢索：** L0/L1/L2 分層、Viking URI、語義搜尋和上下文感知檢索。[概念說明](../concepts/03-context-layers.md)
- **資源：** 文件、程式碼、網頁和媒體匯入，可重複讀取來源的定時更新。音影片檔案可儲存；內容理解需要啟用相容的 VLM。[資源管理](../api/02-resources.md)
- **更新與歷史：** 根據 freshness 重新整理父目錄摘要，以及基於 Git 的快照提交、歷史查詢和恢復。父目錄重新整理可能延後；快照需顯式提交，恢復的是檔案內容，不含歷史 ACL 或向量索引。[上下文分層](../concepts/03-context-layers.md) · [快照指南](../guides/15-snapshot.md)
- **會話與記憶：** 對話追蹤、記憶提取和會話歸檔。[會話說明](../concepts/08-session.md)
- **接入與整合：** HTTP API、SDK、CLI、MCP 和 Agent 外掛。[API 概覽](../api/01-overview.md) · [MCP 指南](../guides/06-mcp-integration.md)
- **運維：** JSON 配置（`ov.conf`）、多模型供應商、租戶隔離、加密、可觀測性和本地/S3 儲存。[配置指南](../guides/01-configuration.md) · [部署指南](../guides/03-deployment.md)

## 後續方向

- 繼續完善分散式儲存。
- 接入更多 Agent 框架。

提案與範圍討論見 [GitHub issues](https://github.com/volcengine/OpenViking/issues)，參與開發見[貢獻指南](https://github.com/volcengine/OpenViking/blob/main/CONTRIBUTING_CN.md)。
