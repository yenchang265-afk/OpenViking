# 應用開發路徑

先完成[第一次匯入與檢索](../getting-started/02-quickstart.md)，再選擇下面的任務。已有 Agent 的使用者從[接入 Agent](../agent-integrations/01-overview.md)開始；自己編寫應用時，用 [SDK、HTTP 與 CLI 約定](../api/01-overview.md)選擇呼叫方式。

| 要完成的任務 | 閱讀順序 | 用什麼確認結果 |
| --- | --- | --- |
| 讓應用檢索文件或程式碼 | [匯入資源](../api/02-resources.md) → [檢索](../api/06-retrieval.md) → [讀取內容](../api/12-content.md) | 用已知答案的問題查詢，讀取命中 URI，核對原文 |
| 跨會話複用記憶 | [會話與記憶模型](../concepts/08-session.md) → [會話 API](../api/05-sessions.md) → [記憶 API](../api/16-memory.md) | 提交會話並確認後臺任務完成，再檢查記憶內容和歸屬 |
| 讓 Agent 複用技能 | [技能 API](../api/04-skills.md) → [隱私模型](../concepts/13-privacy.md) | 檢查安裝後的技能內容、可見範圍和呼叫方式 |
| 從已有資料產出 Wiki、圖譜或日報 | [上下文編譯](../context-compilation/01-overview.md) → 選擇產物教程 | 檢查任務狀態、產物目錄，以及產物與輸入來源的對應關係 |
| 同步或遷移已有上下文 | [專案資源同步](../guides/18-openviking-assets.md)、[OVPack](../guides/09-ovpack.md)或[版本恢復](../guides/15-snapshot.md) | 按對應指南核對同步狀態、匯入結果或恢復後的內容 |

## 先驗證檢索，再接入應用

使用一份內容已知的小文件，走完匯入、等待處理、檢索、讀取原文的流程。`health` 成功只說明服務可以響應；空結果也不能單獨證明匯入失敗。檢視[後臺任務](../api/17-tasks.md)與[觀測入口](../guides/05-observability.md)，區分處理狀態和檢索結果。

需要持續更新遠端資源時，再接入 [Resource Watch](../api/15-watches.md)。需要調整內容處理方式時，檢視 [Prompt 自定義](../guides/10-prompt-guide.md)。

## 再驗證跨會話記憶

先確定[使用者、Peer 與共享上下文的邊界](../concepts/11-multi-tenant.md)，再寫入訊息並提交會話。記憶提取受配置和策略控制，提交成功不等於一定產生某條記憶。用[會話 API](../api/05-sessions.md)與[記憶 API](../api/16-memory.md)檢查實際產物；接入已有工具時，先查[整合能力對照](../agent-integrations/16-capability-reference.md)，確認哪些步驟由外掛自動執行。

## 上線前補齊訪問與運維

共享服務需要配置[身份認證](../guides/04-authentication.md)和 [ACL](../concepts/15-acl.md)。部署路徑、觀測與升級入口集中在[部署運維](../guides/00-overview.md)。查引數、響應和錯誤時，進入[參考文件](../reference/01-overview.md)。
