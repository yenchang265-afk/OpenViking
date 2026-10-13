# 記憶

記憶由會話提交或顯式提取生成，儲存在使用者記憶名稱空間中，並可通過內容、檔案系統和檢索 API 使用。

## 內建記憶型別

| 分類 | 位置 | 說明 |
|------|------|------|
| profile | `viking://user/{user_id}/memories/profile.md` | 使用者個人資訊 |
| preferences | `viking://user/{user_id}/memories/preferences/` | 按主題分類的使用者偏好 |
| entities | `viking://user/{user_id}/memories/entities/` | 重要實體（人物、專案等） |
| events | `viking://user/{user_id}/memories/events/` | 重要事件 |
| identity | `viking://user/{user_id}/memories/identity.md` | 助手身份與自我介紹 |
| soul | `viking://user/{user_id}/memories/soul.md` | 助手原則、邊界、風格和連續性 |
| cases | `viking://user/{user_id}/memories/cases/` | 可訓練、可評估的任務案例 |
| trajectories | `viking://user/{user_id}/memories/trajectories/` | 從 Agent 任務軌跡提煉的可複用操作契約 |
| experiences | `viking://user/{user_id}/memories/experiences/` | 可複用的執行經驗 |
| tools | `viking://user/{user_id}/memories/tools/` | 工具使用經驗與最佳實踐 |
| skills | `viking://user/{user_id}/memories/skills/` | 技能執行經驗與工作流策略 |

以上是隨部署提供的內建型別，`tools` 和 `skills` 預設關閉；實際抽取還取決於生效的記憶策略和 Agent 進化設定。表中為 Self 路徑，支援 Peer 的型別也可存放在 `viking://user/{user_id}/peers/{peer_id}/memories/` 下。部署模板可以擴充或覆蓋 Registry；Account 模板 API 只允許修改其列出的欄位和型別。

---

## 記憶召回

用 [`search(mode="context")`](06-retrieval.md#search-mode-context) 檢索記憶並組裝可直接注入的記憶塊。服務端 MCP 以 `search(mode="context")` 提供同一能力，沒有單獨的 `recall` 工具。

```http
POST /api/v1/search/recall
Content-Type: application/json
```

`/api/v1/search/recall` 已棄用。它只是 `search(mode="context")` 疊加 `purpose="coding"` 和 v1 預設值的預設，為現有呼叫方保留；響應帶 `Deprecation: true` 頭。新接入不要使用。

## 相關文件

- [會話](05-sessions.md) - commit 與 extract
- [檢索](06-retrieval.md) - 搜尋記憶
- [內容](12-content.md) - 讀取記憶內容
