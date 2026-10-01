# 資源 Watch

Watch API 管理資源的週期檢查、暫停、恢復和手動觸發。

## API 參考

### Watch Management（監控任務管理）

列出、檢視、更新和觸發通過 [`add_resource`](02-resources.md#add-resource) 配合 `watch_interval > 0` 建立的監控任務。控制面在 REST（`/api/v1/watches`）、`ov task watch` CLI 子命令組以及面向 Agent 的最小閉包 MCP 介面（`list_watches` / `cancel_watch`）三處映象。

#### 1. API 實現介紹

此控制面封裝了 `WatchManager` 原語，未改動任何服務端行為。每個端點和 CLI 命令都支援通過 `task_id`（路徑）或 `to_uri`（查詢引數）定位目標任務，兩種鍵可以互換；如果同時提供，二者必須指向同一任務，否則返回 400。

**操作**：
- **列出**（`GET /api/v1/watches`）— 返回 `{tasks, total}`；可傳 `?active_only=true` 過濾；傳 `?to_uri=...` 時降級為單任務查詢
- **檢視**（`GET /api/v1/watches/{task_id}`）— 檢視單個任務；可選 `?to_uri=` 做跨鍵一致性校驗
- **更新**（`PATCH /api/v1/watches/{task_id}` 或 `PATCH /api/v1/watches?to_uri=...`）— 部分更新 `watch_interval`、`is_active`、`reason`、`instruction`。`is_active` 與 `watch_interval` 正交：翻轉 `is_active` 可在不丟失配置週期的前提下暫停/恢復任務。
- **刪除**（`DELETE /api/v1/watches/{task_id}` 或 `DELETE /api/v1/watches?to_uri=...`）
- **觸發**（`POST /api/v1/watches/{task_id}/trigger` 或 `POST /api/v1/watches/trigger?to_uri=...`）— 觸發即返回（fire-and-forget），重新攝取在後臺非同步執行

**程式碼入口**：
- `openviking/server/routers/watches.py` — `/api/v1/watches` REST 路由
- `crates/ov_cli/src/commands/watch.rs` — `ov task watch` CLI 子命令組
- `openviking/server/mcp_endpoint.py` — MCP `list_watches` / `cancel_watch` 工具，以及 `add_resource` 上的 `watch_interval` / `to` 引數
- `openviking/resource/watch_manager.py:WatchManager` — 任務持久化與排程原語

#### 2. 介面和引數說明

對每個單任務端點，路徑中的 `{task_id}` 都可用查詢引數 `?to_uri=` 替代。CLI 的 `<key>` 引數會自動分類：任何以 `viking://` 開頭的值走 by-URI 路徑，其他值視為 task_id（其它 scheme 如 `http://` 會在本地直接報錯，避免靜默 404）。

**`PATCH /watches` 請求體**（欄位均可選，至少需提供一個）

| 欄位 | 型別 | 說明 |
|------|------|------|
| watch_interval | float | 新的檢查週期（分鐘），必須 `> 0`；如需暫停而保留週期請改用 `is_active=false`。 |
| is_active | bool | 切換啟用狀態而保留配置週期（暫停 / 恢復）。 |
| reason | string | 更新該監控任務的記錄原因。 |
| instruction | string | 更新語義處理指令。 |

未識別字段會被拒絕，並返回 HTTP `400` 和 `INVALID_ARGUMENT`（請求模型使用 `extra="forbid"`）。未傳欄位保留原值。

#### 3. 使用示例

**HTTP API**

```bash
# 列出活躍監控任務（去掉 ?active_only 可同時包含已暫停的任務）
curl -s "http://localhost:1933/api/v1/watches?active_only=true" \
  -H "X-API-Key: your-key"

# 暫停一個監控任務而保留其檢查週期
curl -X PATCH "http://localhost:1933/api/v1/watches/<task_id>" \
  -H "X-API-Key: your-key" -H "Content-Type: application/json" \
  -d '{"is_active": false}'

# 觸發一次立即重新整理（fire-and-forget，立即返回，再次攝取在後臺執行）
curl -X POST "http://localhost:1933/api/v1/watches/<task_id>/trigger" \
  -H "X-API-Key: your-key"

# 按 URI 而非 task_id 定位任務
curl -X DELETE "http://localhost:1933/api/v1/watches?to_uri=viking://resources/guide.md" \
  -H "X-API-Key: your-key"
```

**Python SDK**

```python
watches = client.list_watches(active_only=True)
client.update_watch(to_uri="viking://resources/guide.md", is_active=False)
client.trigger_watch(to_uri="viking://resources/guide.md")
client.delete_watch(to_uri="viking://resources/guide.md")
```

**TypeScript SDK**

```typescript
const watches = await client.listWatches({ activeOnly: true });
await client.updateWatch(
  { toUri: "viking://resources/guide.md" },
  { isActive: false },
);
await client.triggerWatch({ toUri: "viking://resources/guide.md" });
await client.deleteWatch({ toUri: "viking://resources/guide.md" });
```

**Go SDK**

```go
watches, err := client.ListWatches(ctx, &openviking.ListWatchesOptions{
    ActiveOnly: true,
})
updated, err := client.UpdateWatch(ctx, openviking.UpdateWatchOptions{
    ToURI:    "viking://resources/guide.md",
    IsActive: openviking.Bool(false),
})
triggered, err := client.TriggerWatch(ctx, openviking.WatchRef{
    ToURI: "viking://resources/guide.md",
})
deleted, err := client.DeleteWatch(ctx, openviking.WatchRef{
    ToURI: "viking://resources/guide.md",
})
_, _, _, _ = watches, updated, triggered, deleted
```

**CLI**

以下示例使用 `ov task watch` 子命令：

```bash
# 列出活躍監控任務（去掉 --active-only 可同時包含已暫停的任務）
ov task watch ls --active-only

# 檢視單個監控任務（key 可以是 viking:// URI 或 task_id）
ov task watch show viking://resources/guide.md

# 暫停 / 恢復，不丟失配置週期
ov task watch pause viking://resources/guide.md
ov task watch resume viking://resources/guide.md

# 更新週期（或 --active / --reason / --instruction 的任意組合）
ov task watch update viking://resources/guide.md --interval 30

# 觸發一次立即重新整理（fire-and-forget）
ov task watch trigger viking://resources/guide.md

# 刪除監控任務
ov task watch rm viking://resources/guide.md
```

**響應**

列出任務時返回：

```json
{
  "status": "ok",
  "result": {
    "tasks": [
      {
        "task_id": "7f02e980-8df9-4f27-a570-4d8428cbed8a",
        "path": "https://example.com/guide.md",
        "source_type": "url",
        "to_uri": "viking://resources/guide.md",
        "parent_uri": "viking://resources",
        "reason": "keep documentation current",
        "instruction": "",
        "watch_interval": 30,
        "build_index": true,
        "summarize": false,
        "processor_kwargs": {},
        "created_at": "2026-07-24T10:00:00",
        "last_execution_time": null,
        "last_task_id": null,
        "last_status": null,
        "last_error": null,
        "next_execution_time": "2026-07-24T10:30:00",
        "is_active": true,
        "account_id": "default",
        "user_id": "default",
        "original_role": "user"
      }
    ],
    "total": 1
  }
}
```

`source_type` 是可選的來源後設資料。顯式 Connector `add_type` 優先（例如 `tos`）；
原生匯入返回 `git`、`url` 或 `local`。歷史任務或
無法分類的任務返回 `null`。

首次執行前，`last_task_id`、`last_status` 和 `last_error` 均為 `null`。執行後，
`last_task_id` 指向對應的普通匯入任務（預檢查失敗時可能為 `null`），`last_status`
為 `completed`、`failed` 或 `cancelled`；失敗時 `last_error` 返回經過憑證脫敏且最多
500 字元的錯誤資訊。可用 `ov task status <last_task_id>` 檢視對應匯入任務詳情。

檢視單個任務以及成功更新時，`result` 直接是同一結構的任務物件。刪除和觸發分別返回：

```json
{
  "status": "ok",
  "result": {
    "task_id": "7f02e980-8df9-4f27-a570-4d8428cbed8a",
    "to_uri": "viking://resources/guide.md",
    "deleted": true
  }
}
```

```json
{
  "status": "ok",
  "result": {
    "task_id": "7f02e980-8df9-4f27-a570-4d8428cbed8a",
    "to_uri": "viking://resources/guide.md",
    "scheduled": true
  }
}
```

`scheduled=true` 只表示後臺執行已排程，不表示重新攝取已經完成；應再次檢視任務，直到
`last_execution_time` 更新，並檢查 `last_status` 和 `last_error`。

**MCP**（Agent 控制面——僅最小閉包）

```text
list_watches()                                            # 每個任務一行；只暴露 URI，不暴露 task_id
cancel_watch(to_uri="viking://resources/guide.md")        # 按 URI 冪等刪除
```

暫停 / 恢復 / 觸發 / 更新故意不通過 MCP 暴露——這些 power-user 操作放在 CLI/REST 一側，以保持 Agent 系統提示詞的緊湊。Agent 側若需建立監控任務或調整週期，仍走 [`add_resource`](02-resources.md#add-resource) 配合 `watch_interval`；可顯式傳 `to`，也可讓系統繫結本次匯入返回的 `root_uri`。

---

## 相關文件

- [資源](02-resources.md) - 建立帶 watch_interval 的資源
- [後臺任務](17-tasks.md) - 查詢後臺處理狀態
