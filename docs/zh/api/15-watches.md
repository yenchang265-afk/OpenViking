# 資源 Watch

Watch API 管理資源的週期檢查、暫停、恢復和手動觸發。

## API 參考

### Watch Management（監控任務管理）

列出、檢視、更新和觸發通過 [`add_resource`](02-resources.md#add-resource) 配合 `watch_interval > 0` 建立的監控任務。REST（`/api/v1/watches`）和 `ov task watch` 提供完整管理操作；MCP 提供 `list_watches` 和 `cancel_watch`，用於列出和刪除 Watch。

#### 1. API 實現介紹

通過 `task_id` 定位任務，或通過 `to_uri` 查詢唯一可訪問的任務。多個 Connector Watch 可以共享目標；此時按 URI 操作會返回 `409 Conflict`，需要改用 `task_id`。同時提供兩個引數時，它們必須指向同一任務，否則返回 `400`。

**操作**：
- **列出**（`GET /api/v1/watches`）— 返回 `{tasks, total}`；可傳 `?active_only=true` 過濾、`?limit=100` 分頁，或 `?to_uri=...` 查詢單個任務
- **檢視**（`GET /api/v1/watches/{task_id}`）— 檢視單個任務；可選 `?to_uri=` 做跨鍵一致性校驗
- **更新**（`PATCH /api/v1/watches/{task_id}` 或 `PATCH /api/v1/watches?to_uri=...`）— 部分更新 `watch_interval`、`is_active`、`reason`、`instruction`。`is_active` 與 `watch_interval` 獨立：修改 `is_active` 可在不丟失配置週期的前提下暫停/恢復任務。
- **刪除**（`DELETE /api/v1/watches/{task_id}` 或 `DELETE /api/v1/watches?to_uri=...`）
- **觸發**（`POST /api/v1/watches/{task_id}/trigger` 或 `POST /api/v1/watches/trigger?to_uri=...`）— 觸發即返回（fire-and-forget），重新攝取在後臺非同步執行

**程式碼入口**：
- `openviking/server/routers/watches.py` — `/api/v1/watches` REST 路由
- `crates/ov_cli/src/commands/watch.rs` — `ov task watch` CLI 子命令組
- `openviking/server/mcp_endpoint.py` — MCP `list_watches` / `cancel_watch` 工具，以及 `add_resource` 上的 `watch_interval` / `to` 引數
- `openviking/resource/watch_manager.py:WatchManager` — 任務持久化與排程原語

#### 2. 介面和引數說明

對每個單任務端點，路徑中的 `{task_id}` 都可用查詢引數 `?to_uri=` 替代。CLI 的 `<key>` 引數會自動分類：任何以 `viking://` 開頭的值走 by-URI 路徑，其他值視為 task_id（其它 scheme 如 `http://` 會在本地直接報錯，避免靜默 404）。

**`GET /watches` 分頁**

| 引數 | 型別 | 說明 |
|------|------|------|
| limit | integer | 每頁 1–200 條；傳入後啟用分頁。 |
| cursor | string | 使用上一頁返回的 `next_cursor`；單獨傳 cursor 時每頁預設 100 條。 |
| active_only | boolean | 預設 false；後續頁需保持同一過濾條件。 |

分頁返回 `{tasks, total, has_more, next_cursor}`。`total` 是當前可見且符合過濾條件
的 Watch 總數；末頁 `next_cursor` 為 `null`。按 `created_at DESC, task_id DESC`
排序。使用相同服務和表的 MySQL 節點可共享游標；請求身份和過濾條件必須一致。
非法游標、分頁與 `to_uri` 單任務查詢混用返回 `400`。不傳 `limit/cursor` 時
保留原來的不分頁響應。

每頁讀取當前資料，不提供跨請求快照；首頁之後新增且排在游標之前的 Watch 需從
首頁重新查詢，刪除游標對應的 Watch 不影響繼續翻頁。MySQL 使用游標條件和
`LIMIT`，只把公開欄位讀入應用，不讀取鑑權和 checkpoint。File 從已有記憶體快取
掃描並選出一頁，不重讀磁碟快照，也不排序整個列表。精確總數仍需統計匹配記錄。

**`PATCH /watches` 請求體**（欄位均可選，至少需提供一個）

| 欄位 | 型別 | 說明 |
|------|------|------|
| watch_interval | float | 新的檢查週期（分鐘），必須 `> 0`；如需暫停而保留週期請改用 `is_active=false`。 |
| is_active | bool | 切換啟用狀態而保留配置週期（暫停 / 恢復）。 |
| reason | string | 更新該監控任務的記錄原因。 |
| instruction | string | 更新語義處理指令。 |

自動排程在目標鎖內讀取當前引數並佔用 Watch，凍結本輪引數後才完成 due 選取。
佔用後的引數修改從下一輪生效。暫停阻止後續自動選取，已選取或正在執行的任務繼續執行；暫停期間
仍可手動觸發。

託管 Connector 的控制面還可獨立提交 `credential_state` 通知，不能與上述欄位組合。該物件包含引用歸屬欄位 `account_id`、`resource_id`、`user_id`、`ov_user_id`、`ov_account_id`、`type`、`platform`，以及正整數儲存版本 `version` 和布林值 `authorized`。核心核對 watch 私有引用並忽略過期或重複通知；撤銷時記錄自動暫停，重新授權時僅恢復自動暫停的任務。手動暫停/恢復清除自動暫停標記，執行歷史保留。通知水位和暫停標記只儲存在私有 watch 資料中，不出現在查詢響應；歷史無標記的暫停任務保留原狀態。

未識別字段會被拒絕，並返回 HTTP `400` 和 `INVALID_ARGUMENT`（請求模型使用 `extra="forbid"`）。未傳欄位保留原值。

#### 3. 使用示例

**HTTP API**

```bash
# 列出活躍監控任務（去掉 ?active_only 可同時包含已暫停的任務）
curl -s "http://localhost:1933/api/v1/watches?active_only=true" \
  -H "X-API-Key: your-key"

# 首頁；後續頁攜帶返回的 next_cursor，並保持過濾條件
curl -s "http://localhost:1933/api/v1/watches?active_only=true&limit=100" \
  -H "X-API-Key: your-key"
curl -sG "http://localhost:1933/api/v1/watches" \
  -H "X-API-Key: your-key" \
  --data-urlencode "active_only=true" --data-urlencode "limit=100" \
  --data-urlencode "cursor=<next_cursor>"

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

以下使用 `SyncHTTPClient`；使用 `AsyncHTTPClient` 時，每次呼叫都需加 `await`。

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

**MCP**

```text
list_watches()                                            # 每個任務一行；只暴露 URI，不暴露 task_id
cancel_watch(to_uri="viking://resources/guide.md")        # 按 URI 冪等刪除
```

刪除 Watch 會移除定時任務，已匯入的資源保留。MCP 只提供列出和刪除 Watch。建立 Watch 時，使用 [`add_resource`](02-resources.md#add-resource) 並設定 `watch_interval`；暫停、恢復、觸發和調整已有 Watch 的週期使用 CLI 或 REST。重複匯入不會更新已有 Watch。

---

## 相關文件

- [資源](02-resources.md) - 建立帶 watch_interval 的資源
- [後臺任務](17-tasks.md) - 查詢後臺處理狀態
