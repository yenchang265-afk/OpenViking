# 概念與原理

這裡按學習順序組織 OpenViking 的上下文模型、處理機制、架構與治理。尚未執行過 OpenViking，可以先[匯入並檢索第一份文件](../getting-started/02-quickstart.md)，再回到這裡理解結果如何產生。

## 先理解上下文模型

按順序閱讀前三篇，回答“存什麼、在哪裡、讀多少”：

1. [上下文型別](02-context-types.md)：資源、記憶與技能各自承擔什麼職責。
2. [Viking URI](04-viking-uri.md)：如何定位上下文，如何區分使用者、Peer 與共享空間。
3. [上下文層級（L0/L1/L2）](03-context-layers.md)：摘要、概覽與原文的關係，以及按層讀取的邊界。

## 再看處理與記憶

沿著資料匯入和會話積累兩條路徑閱讀：

- [上下文提取](06-extraction.md)：原始資料如何經過解析、組織與語義處理。
- [檢索機制](07-retrieval.md)：如何查詢相關上下文，`find` 與 `search` 有什麼區別。
- [會話管理](08-session.md)：訊息、會話提交與記憶提取如何銜接。

準備寫應用時，回到[應用開發路徑](../workflows/01-overview.md)選擇操作流程；引數和響應查[參考文件](../reference/01-overview.md)。

## 按問題深入架構與治理

| 想理解的問題 | 閱讀路徑 |
| --- | --- |
| 模組如何協作，資料存在哪裡？ | [架構概述](01-architecture.md) → [儲存架構](05-storage.md) |
| 處理何時結束，失敗後如何恢復？ | [任務狀態](16-queue-lifecycle.md) → [路徑鎖與崩潰恢復](09-transaction.md) |
| 主備寫入、讀取和觀測有什麼語義？ | [主備儲存](14-multi-write-storage.md) → [指標與 Metrics](12-metrics.md) |
| 誰能看到什麼，許可權如何繼承？ | [多租戶](11-multi-tenant.md) → [資源訪問控制（ACL）](15-acl.md) |
| 資料如何加密，Skill 和 Session 隱私如何處理？ | [資料加密](10-encryption.md) → [隱私配置與自動管理](13-privacy.md) |

配置和部署步驟集中在[部署運維](../guides/00-overview.md)。原理頁說明行為與約束，操作指南說明如何設定和驗證，兩者通過連結連線。

## 看一個應用示例

[VikingBot](15-vikingbot.md)展示 Agent、上下文與多渠道互動如何組合。需要執行它時，繼續閱讀[VikingBot 安裝與配置](../guides/17-vikingbot.md)；接入其他現成工具時，先[選擇 Agent 接入方式](../agent-integrations/01-overview.md)。
