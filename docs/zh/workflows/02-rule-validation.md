# 規則校驗（Beta）

把協議、程式碼規範等材料中的強約束批次編譯為 Rule，再讓 Agent 根據具體任務召回規則、核對證據並調整行動。本教程以使用者提供的開源許可證要求為例。

OpenViking 負責規則編譯和適用性召回。是否滿足或違反規則由 Agent 判斷，搜尋介面本身不返回合規結論。概念和生命週期見[規則（Beta）](../concepts/17-rule-scenarios.md)。

## 前置條件

- 執行包含 Rule 功能的 OpenViking Server，配置可用的 Compiler 模型和 Embedding 模型。Compiler 預設複用服務端 VLM，也可以通過 `rules.compiler` 指定。
- 使用包含 `rule_compile()` 和 `rule_search()` 的 Python HTTP SDK，並配置當前使用者的認證身份。編譯和搜尋應使用同一使用者。
- 準備使用者確認的強約束材料，保留原文的條件、例外和閾值。不要把普通建議或偏好當作規則。

模型配置見[服務端 Rules 配置](../configuration/01-server.md#rules)，連線約定見[API 總覽](../api/01-overview.md)。以下程式碼按順序執行，URL 和 API Key 替換為自己的配置。

## 第一步：提交規則材料

```python
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(url="http://localhost:1933", api_key="your-key")
task = client.rule_compile(
    instruction=(
        "倉庫宣告自己是開源專案時，"
        "必須提供明確、完整且可定位的專案許可證文本。"
    ),
)
print(task["task_id"])
```

批次匯入檔案或目錄時，將上面的呼叫替換為：

```python
task = client.rule_compile(options={"sources": ["./compliance-rules/"]})
```

SDK 會上傳本地來源。已匯入的資源可以直接使用 `{"sources": ["viking://resources/compliance-rules"]}`，避免重複匯入。HTTP 來源格式見[規則 API](../api/26-rules.md)。

## 第二步：等待完成並檢查產物

```python
import time


def wait_for_task(task_id, timeout=300):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = client.get_task(task_id)
        if current is None:
            raise RuntimeError(f"Task not found: {task_id}")
        if current["status"] == "completed":
            return current
        if current["status"] in {"failed", "cancelled"}:
            raise RuntimeError(current)
        time.sleep(1)
    raise TimeoutError(f"Task still running: {task_id}")


completed = wait_for_task(task["task_id"])
result = completed["result"]
print(result["operations"])
print(result["written_uris"])

# 編譯完成與寫入後的索引處理可能屬於不同任務。
write_task_id = result.get("write_result", {}).get("task_id")
if write_task_id:
    wait_for_task(write_task_id)

for uri in result["written_uris"]:
    print(client.read(uri))
```

檢查生成規則是否保留了主體、義務、條件和例外，以及原文證據。`UNCERTAIN` 和 `REJECT` 只記錄原因；`NOOP` 表示已有規則覆蓋輸入。超時只停止本地等待，不取消服務端任務。

## 第三步：按具體任務搜尋

先讀取審查物件，再把目標、物件、計劃動作和已有證據組織為 `task_context`。以下內容是示例事實，使用時替換為實際讀取的內容：

```python
matches = client.rule_search(
    task_context=(
        "只讀檢查一個倉庫的開源許可證。"
        "已讀取 README.md，其中宣告專案開源；"
        "根目錄存在 LICENSE，尚未檢查其正文。"
        "接下來計劃讀取許可證文本並核對完整性。"
    ),
)
print(matches["rendered"])
print(matches.get("warning"))
```

把完整的 `rendered` 交給 Agent；直接對接 API 的應用還應檢查 `judge`、`warning` 和 `scenario_selection`。Jev 不可用時可能放行候選，不能把放行分數當作已確認適用的機率。

## 第四步：Agent 逐條核驗

Agent 對每條返回規則執行以下步驟：

1. 用當前任務證據檢查 `applies_when`，不推斷缺失的事實；空條件表示除例外外均適用。
2. 檢查明確例外，再對照 `content` 核驗擬執行動作或回答。
3. 對於審查任務，記錄規則標識、來源與物件證據，區分已滿足、違反和證據不足。規則已滿足也應納入適用規則。
4. 新事實實質改變適用場景時，再次搜尋。

本例中，README 的宣告觸發規則；LICENSE 檔案存在還不足以確認文本完整，應繼續讀取。空結果不代表沒有相關規則，也不構成“校驗通過”。

## 接入已有 Agent

[VikingBot](../guides/17-vikingbot.md) 已提供 `openviking_rule_search` 工具（Beta），連線 OpenViking 後可按需呼叫。

其他 Agent 可以使用 Python HTTP SDK 或 HTTP API，並安裝配套 Skill。將完整目錄放入 Agent 配置的 Skills 目錄，再讓 Agent 載入：

| 任務 | 配套 Skill |
| --- | --- |
| 準備來源、編譯並檢查結果 | [add-rules](https://github.com/volcengine/OpenViking/tree/main/examples/skills/add-rules) |
| 組織任務上下文、召回並核驗規則 | [openviking-rule-search](https://github.com/volcengine/OpenViking/tree/main/examples/skills/openviking-rule-search) |

Skill 提供操作與行為要求；Agent 仍需具備可呼叫的介面。當前 Beta 通過使用者或 Agent 主動呼叫使用。

## 相關文件

- [規則（Beta）](../concepts/17-rule-scenarios.md)
- [規則 API（Beta）](../api/26-rules.md)
- [後臺任務](../api/17-tasks.md)
- [應用開發路徑](./01-overview.md)
