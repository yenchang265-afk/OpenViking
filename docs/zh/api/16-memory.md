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

## 規則

規則是編譯生成的行為約束，以 Markdown 儲存在 `viking://user/{user_id}/memories/rules` 下，按當前認證的帳號和使用者隔離。

### 編譯規則

```http
POST /api/v1/rules/compile
Content-Type: application/json
```

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| instruction | string | 否 | null | 規則指令，最多 64,000 個字元；自動去除首尾空白 |
| sources | object[] | 否 | [] | 最多 16 個來源，每項為已匯入資源的 `{"resource_uri":"viking://resources/policy"}`，或[資源匯入請求](02-resources.md) |

必須提供非空 `instruction` 或至少一個來源。來源必須能解析為可讀文本，不支援多模態來源。不接受未知的頂層欄位。

```json
{
  "instruction": "刪除檔案前必須徵求確認。",
  "sources": []
}
```

返回 HTTP `202 Accepted`，響應格式為 `{"status":"ok","result":...}`，其中 `result` 是任務記錄，`task_type="rule_compile"`，任務 ID 以 `rul_` 開頭。通過[任務 API](17-tasks.md) 的 `GET /api/v1/tasks/{task_id}` 輪詢狀態。完成後的任務結果包含 `rules_root`、`source_uris`、`plan_reason`、`batch_count`、`operations`、`written_uris` 和 `write_result`。內容索引作為獨立後臺工作執行，可通過 `write_result` 定位。

### 檢索適用規則

```http
POST /api/v1/rules/search
Content-Type: application/json
```

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| task_context | string | 是 | - | 當前任務事實，1–64,000 個字元；去除首尾空白後必須非空 |
| rule_probability_threshold | number | 否 | 0.65 | 最低規則適用機率，取值範圍為 0 到 1，包含端點 |

```json
{
  "task_context": "刪除工作區中自動生成的檔案。",
  "rule_probability_threshold": 0.65
}
```

返回 HTTP `200 OK`，響應格式為 `{"status":"ok","result":...}`。僅檢索 active 狀態的規則。不接受未知請求欄位。

| 結果欄位 | 說明 |
|----------|------|
| rules | 匹配規則，每項包含 `atomic_id`、`revision`、`scenario_id`、`probability`、`uri` 和完整 Markdown `content` |
| scenarios | 召回的場景 ID |
| rendered | 可供 Agent 上下文使用的規則正文和應用指引 |
| delivery | `complete`、`rule_count` 和 `rendered_chars` 描述交付內容 |
| scenario_selection | 場景篩選診斷資訊，可為 null |
| judge、warning | 可選的判定器標識和降級警告 |

## 相關文件

- [會話](05-sessions.md) - commit 與 extract
- [檢索](06-retrieval.md) - 搜尋記憶
- [內容](12-content.md) - 讀取記憶內容
