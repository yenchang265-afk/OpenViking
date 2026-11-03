# 規則（Beta）

::: warning Beta 提示
規則功能目前處於 Beta 階段，本頁介紹的介面、引數和使用流程在後續版本中可能發生不相容調整。升級前，請查閱版本說明和最新文件，並在測試環境中驗證現有接入流程。
:::

Rule 用來儲存 Agent 在特定條件下需要遵守的明確要求，例如釋出前的檢查項、程式碼規範中的禁止項。OpenViking 將這些要求編譯為規則，按當前任務召回；Agent 再結合原文證據，檢查行動或回答是否滿足要求。

本次體驗為 Lighthouse 演示專案儲存一條釋出規則，再檢查兩份釋出說明。完成後，你可以看到規則原文、召回結果，以及補齊材料前後的檢查差異。

## 適用場景

| 場景 | 可以儲存的規則 | Agent 如何使用 |
| --- | --- | --- |
| 釋出檢查 | 專案釋出說明必須包含回滾步驟 | 釋出前核對說明，指出缺少的內容 |
| 程式碼審查 | 團隊禁止在業務程式碼中記錄訪問金鑰 | 對照變更內容檢查，並標註相關程式碼 |
| 協議核查 | 使用者提供的協議義務、適用條件與例外 | 逐條核對材料，區分已滿足、違反和證據不足 |

Skill 說明“怎樣做”，Rule 說明“在什麼條件下需要遵守哪些要求”。明確的義務和禁止項適合儲存為 Rule；個人偏好和普通建議可以繼續放在記憶中。

## 準備環境

準備已啟用 Rule 功能的 OpenViking 服務，以及 Python 環境；安裝入口見[快速開始](02-quickstart.md#準備工作)。服務端需要可用的 Embedding 和 Compiler 模型，Compiler 預設複用 VLM，配置見 [Rules 配置](../configuration/01-server.md#rules)。編譯和檢索會呼叫模型，並將演示規則儲存在當前使用者的規則庫中，適合使用測試使用者體驗。

在 Python 環境中安裝 SDK：

```bash
python -m pip install --upgrade openviking-sdk
```

本例使用支援 `rule_compile()` 和 `rule_search()` 的 Python HTTP SDK；服務端與 SDK 都需要包含 Rule（Beta）能力。使用託管服務時，可先向服務提供方確認支援情況。連線與身份配置見 [API 約定](../api/01-overview.md)。

將下面的 Python 片段依次放入同一個 `rule_demo.py` 檔案，填寫服務地址和當前使用者的 API Key；本地未啟用鑑權時可省略 `api_key`。

## 儲存規則

使用一條僅針對演示專案的要求，明確觸發條件和需要完成的檢查：

```python
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(url="http://localhost:1933", api_key="your-key")
task = client.rule_compile(
    instruction="檢查 Lighthouse 演示專案的釋出說明時，釋出說明必須包含回滾步驟。",
)
print("Compile task:", task["task_id"])
```

服務會返回後臺任務 ID。接下來等待編譯和關聯索引任務完成，再讀取實際生成的規則：

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


result = wait_for_task(task["task_id"])["result"]
print("Operations:", result["operations"])
write_task_id = result.get("write_result", {}).get("task_id")
if write_task_id:
    wait_for_task(write_task_id)
for uri in result["written_uris"]:
    print(uri)
    print(client.read(uri))
```

檢查規則是否保留了“Lighthouse 演示專案”“檢查釋出說明時”和“必須包含回滾步驟”。重複提交可能得到 `NOOP`，表示已有規則覆蓋輸入，可以繼續檢索；`UNCERTAIN` 或 `REJECT` 會給出未寫入原因，先按原因調整輸入。等待超時後，可用已列印的任務 ID 繼續查詢進度。

## 按任務召回

以下是固定的虛構樣例：Lighthouse 演示專案的釋出說明全文為“本次釋出新增匯出進度提示。”將這段證據和檢查目標一起提交：

```python
matches = client.rule_search(
    task_context=(
        "檢查 Lighthouse 演示專案的釋出說明。"
        "已讀取釋出說明全文：本次釋出新增匯出進度提示。"
        "計劃核對釋出要求，並列出需要補充的內容。"
    ),
)
print(matches["rendered"])
print("Warning:", matches.get("warning"))
print("Scenario selection:", matches.get("scenario_selection"))
```

儲存檔案後執行：

```bash
python rule_demo.py
```

在輸出中找到規則正文及 URI，核對它是否包含剛才的回滾要求。`rendered` 是可交給 Agent 的完整規則文本；搜尋負責找到可能適用的規則，具體是否滿足要求由 Agent 對照材料檢查。

## 核對檢查結果

把上一步完整的 `rendered` 輸出附在下面的提示詞後，交給你的 Agent。兩份說明均為演示材料，Agent 只需閱讀並返回檢查結果：

```text
請依據附後的規則，分別檢查 Lighthouse 演示專案的兩份釋出說明。

版本 A 全文：本次釋出新增匯出進度提示。
版本 B 全文：本次釋出新增匯出進度提示。回滾步驟：停止新版本服務，
切換到上一版本映象，使用上一版本配置啟動服務，並檢查健康介面。

請逐條核對規則的適用條件和例外，引用規則 URI 與釋出說明原文，
分別說明要求是已滿足、違反還是證據不足，並列出需要補充的內容。
本次只做文本檢查。

以下是檢索得到的完整規則：
（貼上 rendered 輸出）
```

| 核對項 | 預期觀察 |
| --- | --- |
| 規則適用 | 兩份材料都屬於 Lighthouse 演示專案的釋出說明 |
| 版本 A | 缺少回滾步驟，Agent 指出需要補充 |
| 版本 B | 包含回滾步驟，滿足這條規則；步驟是否實際可行還需部署驗證 |
| 結論可追溯 | 回答引用了規則 URI 和對應的說明原文 |

這張表是樣例的驗收標準，實際執行結果以你的模型輸出為準。沒有召回規則時，可先檢查編譯與索引任務、使用者身份和任務描述。出現 `warning` 時，結合提示檢查模型配置，並讓 Agent 逐條核對條件；空結果或放行分數都需要結合材料繼續檢查。

## 繼續使用

接入 [VikingBot](11-vikingbot.md) 後，可以讓它主動呼叫 `openviking_rule_search` 工具完成召回。當前 Beta 由使用者或 Agent 主動觸發編譯與搜尋，普通會話提交不會自動生成 Rule。

需要批次匯入規範或接入自己的 Agent 時，繼續閱讀[規則校驗](../workflows/02-rule-validation.md)；暫停、更新和歸檔規則的方法見[規則生命週期](../concepts/17-rule-scenarios.md#生命週期)。
