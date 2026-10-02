# 後臺任務

任務 API 用於跟蹤資源匯入、會話提交、索引維護和快照恢復等非同步操作。

推薦先提交操作、儲存返回的 `task_id`，再通過獨立請求查詢狀態。收到任務 ID 只表示任務已提交；狀態為 `completed` 才表示處理成功。`pending`、`running`、`cancelling` 都不是終態。停止輪詢不會取消後臺任務。

## API 參考

### get_task()

#### 1. API 實現介紹

查詢返回 `task_id` 的後臺任務狀態，例如 session commit、`add_resource` 和 admin reindex。

**任務狀態**：
- `pending`: 任務等待執行
- `running`: 任務執行中
- `cancelling`: 已請求取消，正在等待該任務的持久化佇列訊息和程序內工作結束
- `completed`: 任務成功完成
- `failed`: 任務失敗
- `cancelled`: 任務已取消

**程式碼入口**：
- `openviking/server/routers/tasks.py:get_task()` - HTTP 路由

任務記錄會持久化到 AGFS，服務重啟後仍可查詢，但仍受任務保留清理策略影響。

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| task_id | str | 是 | - | 後臺 API 返回的任務 ID |
| include_events | bool | 否 | false | 在 HTTP 響應中包含持久化的執行事件 |

#### 3. 使用示例

**HTTP API**

```http
GET /api/v1/tasks/{task_id}
```

```bash
curl -X GET http://localhost:1933/api/v1/tasks/uuid-xxx \
  -H "X-API-Key: your-key"
```

**Python SDK**

```python
import asyncio

from openviking_sdk import AsyncHTTPClient

client = AsyncHTTPClient(url="http://localhost:1933", api_key="your-key")
await client.initialize()

try:
    submitted = await client.add_resource("https://example.com/guide.md")
    task_id = submitted["task_id"]
    print(f"Import task: {task_id}")
    while True:
        task = await client.get_task(task_id)
        if task is None:
            raise RuntimeError(f"Task {task_id} is no longer available")
        if task["status"] == "completed":
            break
        if task["status"] in {"failed", "cancelled"}:
            raise RuntimeError(f"Import task {task_id}: {task['status']} ({task.get('error')})")
        await asyncio.sleep(2)
    print(task["result"])
finally:
    await client.close()
```

**TypeScript SDK**

```typescript
console.log(await client.getTask("task-id"));
```

**Go SDK**

```go
task, err := client.GetTask(ctx, "uuid-xxx")
if err != nil {
    return err
}
if task != nil {
    fmt.Println(task["status"])
}
```

**CLI**

```bash
ov task status uuid-xxx
```

**響應示例（資源匯入進行中）**

```json
{
  "status": "ok",
  "result": {
    "task_id": "uuid-xxx",
    "task_type": "add_resource",
    "status": "running",
    "resource_id": "viking://resources/guide",
    "stage": "processing_queue"
  }
}
```

`stage` 可以為 `null`。Git 倉庫資源匯入任務可能報告 `queued`、`fetching`、`parsing`、`finalizing`、`processing_queue`；其他任務型別可能將其留空。即時佇列計數不會出現在任務狀態中；需要即時數量時使用 observer queue，任務完成後可讀取 `result.queue_status`。

**執行事件記錄（HTTP）**

請求 `GET /api/v1/tasks/{task_id}?include_events=true`，即可獲得額外的 `result.execution_events` 欄位。預設詳情響應和任務列表不包含此欄位。事件沿用任務記錄的許可權和保留策略。

```json
{
  "items": [
    {
      "seq": 1,
      "recorded_at": "2026-09-09T01:00:00.123456+00:00",
      "kind": "created",
      "status": "pending",
      "stage": null,
      "operation": null,
      "error": null
    }
  ],
  "dropped_count": 0,
  "started_mid_task": false
}
```

| 事件型別 | 記錄的事實 |
|----------|------------|
| `created` | TaskTracker 建立了任務記錄 |
| `status_changed` | TaskTracker 接受了新的任務狀態，包括取消過程和終態 |
| `stage_changed` | 執行路徑在任務活躍期間上報了不同的階段 |
| `error_recorded` | TaskTracker 接受了任務的首個脫敏錯誤 |
| `waiting_for_descendants` | 等待路徑發現任務仍有未結束的佇列工作，已排除自身 work ID |

`recorded_at` 是 TaskTracker 記錄事件的 UTC 時間，不是瀏覽器輪詢時間，也不一定是底層異常發生的時間。事件與任務狀態在同一次寫入成功後才對外發布。`seq` 確定任務內的事件順序，即使多個事件時間相同也不會混淆。`stage` 表示任務最後上報的階段；並行工作可能在其他階段產生錯誤。`operation` 存在時標識上報事件的工作項。錯誤沿用現有脫敏和長度限制；這裡不包含完整元件日誌或 Python 堆疊。

每個任務最多保留 64 條事件，序列化事件資料不超過 32 KiB。超限時優先刪除較早事件，`dropped_count` 記錄刪除數量，保留事件的序號不重置。事件隨任務過期清理。舊任務返回 `execution_events: null`；若舊的活躍任務後來產生事件，則 `started_mid_task` 為 true，不會重建此前的歷史。舊版本服務即使收到引數也可能不返回該欄位。Studio 會說明這些情況，並保留任務後設資料、結果和錯誤展示。

擴充執行事件時，在 `openviking/service/task_events.py` 註冊事件型別、補充 Studio 翻譯，然後在實際執行點呼叫 `await tracker.record_event(task_id, kind, account_id=..., user_id=..., operation=...)`。這個內部介面不修改任務狀態或階段，只接受有長度限制的操作標識，不接受任意日誌內容。現有生命週期方法會自動記錄它們接受的狀態變化。

持久化任務檔案新增 `execution_events` 欄位。回滾目標需要具備未知任務欄位的保留能力（提交 `a5166386` 或之後的版本）；更早的讀取實現可能拒絕這些檔案。回滾期間也會停止上報事件，因此跨降級執行的任務歷史可能不完整。

**響應示例（完成）**

```json
{
  "status": "ok",
  "result": {
    "task_id": "uuid-xxx",
    "task_type": "session_commit",
    "status": "completed",
    "result": {
      "session_id": "a1b2c3d4",
      "archive_uri": "viking://user/alice/sessions/a1b2c3d4/history/archive_001",
      "memory_diff_uri": "viking://user/alice/sessions/a1b2c3d4/history/archive_001/memory_diff.json",
      "memories_extracted": {
        "profile": 1,
        "preferences": 2,
        "entities": 1,
        "cases": 1
      },
      "token_usage": {
        "llm": {
          "prompt_tokens": 5200,
          "completion_tokens": 1800,
          "total_tokens": 7000
        },
        "embedding": {
          "total_tokens": 1500
        },
        "total": {
          "total_tokens": 8500
        }
      }
    }
  }
}
```

---

### cancel_task()

#### 1. API 實現介紹

請求協作式取消後臺任務。介面會立即阻止該任務產生新的 QueueFS work，並取消仍在執行的程序內工作；已經完成的寫入不會回滾。當任務仍有待處理的持久化訊息或程序內工作時，介面先返回 `cancelling`，全部收斂後任務才進入 `cancelled`。

重複取消處於 `cancelling` 或 `cancelled` 狀態的任務是冪等的。

**支援的任務型別**：
- `add_resource`
- `session_commit`
- `admin_reindex`
- `snapshot_restore_reindex`

**程式碼入口**：
- `openviking/server/routers/tasks.py:cancel_task()` - HTTP 路由
- `openviking/service/task_tracker.py:TaskTracker.cancel()` - 任務生命週期
- `crates/ov_cli/src/commands/task.rs:cancel()` - CLI 命令

#### 2. 介面和引數說明

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| task_id | str | 是 | - | 要取消的後臺任務 ID |

只有任務所屬的當前使用者可以取消任務。ROOT 身份不能執行取消操作。

#### 3. 使用示例

**Python SDK**

```python
task = await client.cancel_task(task_id="uuid-xxx")
print(task["status"])
```

**TypeScript SDK**

```typescript
const task = await client.cancelTask("uuid-xxx");
console.log(task.status);
```

**Go SDK**

```go
task, err := client.CancelTask(ctx, "uuid-xxx")
if err != nil {
    return err
}
fmt.Println(task["status"])
```

**HTTP API**

```http
POST /api/v1/tasks/{task_id}/cancel
```

```bash
curl -X POST http://localhost:1933/api/v1/tasks/uuid-xxx/cancel \
  -H "X-API-Key: your-key"
```

**CLI**

```bash
ov task cancel uuid-xxx
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "task_id": "uuid-xxx",
    "task_type": "add_resource",
    "status": "cancelling",
    "resource_id": "viking://resources/guide",
    "stage": "processing_queue",
    "result": null,
    "error": null
  }
}
```

如果任務沒有剩餘 work，響應中的狀態可以直接為 `cancelled`。否則繼續通過 `get_task()` 查詢，直到狀態變為 `cancelled`。

**錯誤處理**：
- `NOT_FOUND`（404）：任務不存在、已過期或不屬於當前使用者
- `PERMISSION_DENIED`（403）：ROOT 身份請求取消任務
- `FAILED_PRECONDITION`（412）：任務型別不支援取消，或任務已經 `completed`/`failed`

---

### list_tasks()

#### 1. API 實現介紹

列出當前呼叫方可見的後臺任務，支援按型別、狀態、資源過濾。

**程式碼入口**：
- `openviking/server/routers/tasks.py:list_tasks()` - HTTP 路由
- `sdk/python/openviking_sdk/client.py:AsyncHTTPClient.list_tasks()` - Python SDK

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| task_type | str | 否 | None | 按任務型別過濾，例如 `session_commit` |
| status | str | 否 | None | 按任務狀態過濾：`pending`、`running`、`cancelling`、`completed`、`failed`、`cancelled` |
| resource_id | str | 否 | None | 按資源 ID 過濾，例如會話 ID |
| include_internal | bool | 否 | false | 是否包含 Connector 匯入產生的內部子任務 |
| limit | int | 否 | 50 | 最多返回的任務條數 |

預設僅返回使用者可見任務；排查 Connector 匯入時可傳 `include_internal=true` 檢視其內部 `add_resource` 子任務。

#### 3. 使用示例

**HTTP API**

```http
GET /api/v1/tasks?task_type=session_commit&status=running&limit=20
```

```bash
curl -X GET "http://localhost:1933/api/v1/tasks?task_type=session_commit&status=running&limit=20" \
  -H "X-API-Key: your-key"
```

**Python SDK**

```python
from openviking_sdk import AsyncHTTPClient

client = AsyncHTTPClient(url="http://localhost:1933", api_key="your-key")
await client.initialize()

tasks = await client.list_tasks(
    task_type="session_commit",
    status="running",
    limit=20,
)
for task in tasks:
    print(task["task_id"], task["status"])
await client.close()
```

**TypeScript SDK**

```typescript
console.log(await client.listTasks());
```

**Go SDK**

```go
tasks, err := client.ListTasks(ctx, &openviking.ListTasksOptions{
    TaskType: "session_commit",
    Status:   "running",
    Limit:    20,
})
if err != nil {
    return err
}
for _, task := range tasks {
    fmt.Println(task)
}
```

**CLI**

```bash
# 列出任務
ov task list

# 按任務型別和狀態過濾
ov task list --task-type session_commit --status running
```

**響應示例**

```json
{
  "status": "ok",
  "result": [
    {
      "task_id": "uuid-xxx",
      "task_type": "session_commit",
      "status": "running",
      "resource_id": "a1b2c3d4",
      "created_at": 1770000000.0,
      "updated_at": 1770000005.0,
      "result": null,
      "error": null,
      "stage": null
    }
  ]
}
```

---

## 相關文件

- [會話](05-sessions.md) - 會話提交任務
- [資源](02-resources.md) - 資源匯入任務
- [內容](12-content.md) - 非同步 reindex 任務
