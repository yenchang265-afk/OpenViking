# 規則（Beta）

規則 API 將使用者提供的強約束編譯為持久 Rule，並按任務上下文召回適用規則。當前提供 Python HTTP SDK 和 HTTP 介面；沒有對應的專用 CLI、TypeScript SDK 或 Go SDK 方法。VikingBot 提供[規則搜尋工具（Beta）](../guides/17-vikingbot.md)。

編譯和搜尋使用當前認證使用者的規則庫 `viking://user/<user_id>/memories/rules/`。規則概念見[規則（Beta）](../concepts/17-rule-scenarios.md)，完整操作流程見[規則校驗（Beta）](../workflows/02-rule-validation.md)。

## API 參考

### rule_compile()

#### 1. 用途與前置條件

提交規則文本或來源材料，後臺編譯後新增、更新或按使用者明確指令變更規則狀態。需配置可用的 Compiler 模型；預設複用服務端 VLM，也可設定 `rules.compiler`。

來源可以是已匯入的資源，也可以是待匯入的檔案、目錄或 URL。新來源先走資源匯入流程，再提煉約束。編譯不會從普通會話提交中自動觸發。

#### 2. 介面和引數說明

```text
POST /api/v1/rules/compile
```

| 引數 | 型別 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `instruction` | string | 與 `sources` 至少提供一項 | `null` | 規則文本或明確的變更要求；最多 64,000 字元。沒有來源時，去除首尾空白後必須非空 |
| `sources` | array | 與 `instruction` 至少提供一項 | `[]` | 最多 16 個來源；Python SDK 放在 `options["sources"]` 中 |

每個 HTTP 來源只能使用以下一種形式：

| 來源 | 格式 | 說明 |
| --- | --- | --- |
| 已有資源 | `{"resource_uri": "viking://resources/standards"}` | 直接讀取資源正文，不重複匯入 |
| 新遠端來源 | `{"path": "https://example.com/standards.md"}` | 複用資源匯入請求；可用欄位見[資源 API](./02-resources.md) |
| 新本地來源 | `{"temp_file_id": "upload-id", "source_name": "standards.md"}` | 先通過資源臨時上傳介面上傳；目錄先打包為 ZIP |

Python SDK 還支援來源字串：本地檔案或目錄路徑、URL、`viking://` 資源 URI；會自動上傳本地來源並轉換為 HTTP 物件。

編譯器生成變更計劃，呼叫者不直接提交 Mutation：

| 操作 | 行為 |
| --- | --- |
| `NEW` | 建立 active Rule，複用或新建 Scenario |
| `UPDATE` | 更新單條規則，保留標識和 active/paused 狀態 |
| `REPLACE` | 使用者明確完整替代單條舊規則時，建立新標識並歸檔舊規則 |
| `NOOP` | 已有 active Rule 完整覆蓋輸入，不寫入 |
| `UNCERTAIN` / `REJECT` | 記錄歧義或拒絕原因，不寫入 Rule |
| `PAUSE` | 使用者明確暫停或禁用 active Rule |
| `RESTORE` | 使用者明確恢復 paused Rule |
| `ARCHIVE` | 使用者明確刪除、丟棄或移入回收站；授權必須來自 `instruction` |

當前編譯候選只包含 active 和 paused；沒有恢復 archived 的公開入口，也沒有按 ID 直接提交生命週期操作的專用介面。

#### 3. 使用示例

**Python SDK (HTTP)**

```python
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(url="http://localhost:1933", api_key="your-key")
task = client.rule_compile(
    instruction="倉庫宣告自己是開源專案時，必須提供完整的專案許可證文本。",
)
print(task["task_id"])

# 單次查詢；完整等待與索引檢查見規則校驗教程。
print(client.get_task(task["task_id"]))
```

**HTTP API**

```bash
curl -X POST http://localhost:1933/api/v1/rules/compile \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "instruction": "倉庫宣告自己是開源專案時，必須提供完整的專案許可證文本。"
  }'
```

#### 4. 響應契約與錯誤處理

HTTP 返回 **202 Accepted** 和後臺任務記錄。Python SDK 返回外層 `result` 中的任務物件。以下示例省略時間和後設資料：

```json
{
  "status": "ok",
  "result": {
    "task_id": "rule_compile_example",
    "task_type": "rule_compile",
    "status": "pending",
    "resource_id": "viking://user/alice/memories/rules",
    "stage": "queued",
    "result": null,
    "error": null
  }
}
```

收到任務不表示編譯完成。通過[後臺任務 API](./17-tasks.md)查詢至 `completed`，處理 `failed`、`cancelled`；任務剛返回時也可能已進入 `running`。完成後的 `task.result` 包含：

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `rules_root` | string | 當前使用者規則庫 URI |
| `source_uris` | array | 本次來源資源 URI；純文本輸入時可為空 |
| `plan_reason` | string | 編譯計劃說明 |
| `batch_count` | integer | 輸入編譯批次數 |
| `operations` | array | 實際變更或未寫入原因；欄位隨操作型別變化 |
| `written_uris` | array | 本次寫入的 Rule 和 Scenario URI |
| `write_result` | object | 批次寫入結果；有寫入時可包含獨立 `task_id`，用於跟蹤索引處理 |

任務完成結果示例（省略任務物件的其他欄位及寫入統計）：

```json
{
  "status": "ok",
  "result": {
    "task_id": "rule_compile_example",
    "task_type": "rule_compile",
    "status": "completed",
    "result": {
      "rules_root": "viking://user/alice/memories/rules",
      "source_uris": [],
      "plan_reason": "建立專案許可證要求。",
      "batch_count": 1,
      "operations": [
        {
          "operation": "NEW",
          "atomic_id": "project-license",
          "uri": "viking://user/alice/memories/rules/repository-license/project-license.md"
        }
      ],
      "written_uris": [
        "viking://user/alice/memories/rules/repository-license/abstract.md",
        "viking://user/alice/memories/rules/repository-license/project-license.md"
      ],
      "write_result": {"task_id": "write_example"}
    },
    "error": null
  }
}
```

先檢查實際操作和生成內容，再等待 `write_result.task_id` 對應任務完成後檢索。請求結構或長度不合法返回 HTTP 422；後臺解析、模型或校驗失敗記錄在任務 `error` 中，規則編譯失敗以 `RULE_COMPILE_FAILED` 標識。

---

### rule_search()

#### 1. 用途與前置條件

根據當前任務召回 active 規則，返回完整約束及適用性資訊。應先確認規則編譯和關聯索引任務完成，並以相同使用者身份搜尋。

任務上下文應包含目標、物件、計劃動作和已知事實。搜尋判定適用性，Agent 負責核驗事實和是否違反規則。

#### 2. 介面和引數說明

```text
POST /api/v1/rules/search
```

| 引數 | 型別 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `task_context` | string | 是 | — | 非空任務上下文，最多 64,000 字元 |
| `rule_probability_threshold` | number | 否 | `0.65` | `0`–`1`，包含邊界；返回分數大於等於該值的規則。SDK 放在 `options` 中 |

公開介面沒有 `limit`、`scenario_limit` 或 `target_uri` 引數。搜尋先語義召回 Scenario，再過濾無關場景並讀取其中的 active Rule。

#### 3. 使用示例

**Python SDK (HTTP)**

```python
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(url="http://localhost:1933", api_key="your-key")
result = client.rule_search(
    task_context="只讀核查倉庫許可證；README 宣告開源，計劃檢查 LICENSE 正文。",
    options={"rule_probability_threshold": 0.65},
)
print(result["rendered"])
print(result.get("warning"))
```

**HTTP API**

```bash
curl -X POST http://localhost:1933/api/v1/rules/search \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "task_context": "只讀核查倉庫許可證；README 宣告開源，計劃檢查 LICENSE 正文。",
    "rule_probability_threshold": 0.65
  }'
```

#### 4. 響應契約與錯誤處理

HTTP 返回 **200 OK** 和結果包；Python SDK 直接返回外層 `result`。

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `rules` | array | 命中規則；每項包含 `atomic_id`、`revision`、`scenario_id`、`probability`、`uri`、`content` |
| `rules[].content` | string | 完整的儲存 Rule Markdown，含後設資料和約束；不是隻有約束句子 |
| `scenarios` | array | 進入規則讀取階段的 Scenario 標識 |
| `rendered` | string | 應用步驟和完整規則塊，供 Agent 使用 |
| `delivery` | object | `complete`、`rule_count`、`rendered_chars`；描述命中規則的交付完整性 |
| `scenario_selection` | object / null | Scenario 篩選資訊，包括後端、放行或過濾詳情及可能的 warning |
| `judge` | string，可選 | `jev_noul` 或 `pass`；無候選時可省略 |
| `warning` | string，可選 | Rule 判斷不可用時的放行說明 |

無 Scenario 候選時的響應示例：

```json
{
  "status": "ok",
  "result": {
    "rules": [],
    "scenarios": [],
    "rendered": "# Applicable OpenViking Rules\n\nThese Rules are behavioral constraints.\n\nApplication protocol:\n1. Evaluate every Rule independently against concrete facts from the current task.\n2. Check the applicability boundary and exception before applying a Rule. An empty\n   applies_when means the Rule applies in every situation except its exception.\n   For a non-empty applies_when, topic similarity alone does not establish applicability.\n3. Do not infer facts that are absent.\n4. Before acting or answering, validate the planned action or answer against every\n   returned Rule. Returned Rules are mandatory when their applicability conditions hold.\n\nMatched 0 active Rule(s).\n\nNo active compiled Rule met the current retrieval thresholds.",
    "scenario_selection": null,
    "delivery": {"complete": true, "rule_count": 0, "rendered_chars": 730}
  }
}
```

即使沒有命中，`rendered` 仍包含應用步驟和空匹配提示。`delivery.complete=true` 表示選中規則未被截斷，不證明全庫召回；空結果不能當作合規結論。

Jev 未配置或判斷失敗時，受影響候選放行。Rule 判斷失敗返回 `judge="pass"`、`probability=1.0` 和 `warning`；分數不是估算機率。Scenario 判斷異常的提示位於 `scenario_selection`。Agent 必須逐條檢查適用條件與例外。

空白上下文、超長文本、閾值越界或多餘引數返回 HTTP 422。Rule 檔案讀取失敗可能使請求失敗；呼叫方應處理介面錯誤，不能視為無規則。通用認證和錯誤格式見[API 總覽](./01-overview.md)。

## 相關文件

- [規則（Beta）](../concepts/17-rule-scenarios.md)
- [規則校驗（Beta）](../workflows/02-rule-validation.md)
- [後臺任務](./17-tasks.md)
- [服務端 Rules 配置](../configuration/01-server.md#rules)
