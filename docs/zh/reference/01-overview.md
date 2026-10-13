# 選擇參考文件

這裡用於查介面約定、協議和配置欄位。系統行為與設計約束見[概念與原理](../concepts/00-overview.md)。第一次使用請走[快速開始](../getting-started/02-quickstart.md)；還沒確定呼叫哪些介面，請先選[應用開發任務](../workflows/01-overview.md)。

| 要查什麼 | 入口 |
| --- | --- |
| SDK 連線、HTTP 認證、響應格式、錯誤碼 | [SDK、HTTP 與 CLI 約定](../api/01-overview.md) |
| 服務端或客戶端配置欄位 | [服務端配置](../configuration/01-server.md)、[客戶端配置](../configuration/02-client.md) |
| MCP 工具、引數與上傳協議 | [MCP 工具與協議](../guides/06-mcp-integration.md)；安裝客戶端看[連線 MCP 客戶端](../agent-integrations/06-mcp-clients.md) |
| 資源、檔案和檢索介面 | [資源](../api/02-resources.md)、[檔案系統](../api/03-filesystem.md)、[內容](../api/12-content.md)、[檢索](../api/06-retrieval.md) |
| 會話、記憶與技能介面 | [會話](../api/05-sessions.md)、[記憶](../api/16-memory.md)、[技能](../api/04-skills.md) |
| 管理、許可權與後臺狀態 | [Admin](../api/08-admin.md)、[ACL](../api/12-acl.md)、[後臺任務](../api/17-tasks.md)、[Observer](../api/18-observer.md) |
| 資料一致性、隔離和處理完成的含義 | [系統架構](../concepts/01-architecture.md)、[事務與恢復](../concepts/09-transaction.md)、[多租戶](../concepts/11-multi-tenant.md)、[任務狀態](../concepts/16-queue-lifecycle.md) |

側邊欄按介面所屬物件排列；同一主題的操作指南保留在“開發應用”或“部署運維”，通過文內連結互相連線。配置步驟見[配置模型與服務](../guides/01-configuration.md)，整合之間的差異見[整合能力對照](../agent-integrations/16-capability-reference.md)。
