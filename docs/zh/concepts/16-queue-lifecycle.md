# 佇列狀態與完成語義

## 問題

當前佇列完成狀態由兩個相互獨立的資料來源推斷：

- QueueFS `/size`：返回仍可被 dequeue 的 pending 訊息數。
- Python `NamedQueue._in_progress`：返回當前程序觀察到的執行中任務數。

這兩個值無法原子讀取或更新。QueueFS 將訊息從 `pending` 移到
`processing` 後，另一個執行緒、event loop 或程序可能同時觀察到 `size == 0`，
且其讀取到的 `_in_progress == 0`，從而在訊息 ACK 前錯誤地判斷佇列已經完成。

將本地計數放到 task 建立之前或之後，只能縮小部分時序視窗。它無法讓 backend
狀態遷移與本地計數更新成為同一個原子操作，因此無法嚴格解決跨執行緒、跨 event loop
或跨程序的併發判斷問題。

## 改動前的後端行為

SQLite 和快取後端實現了 ACK 生命週期：

```text
enqueue -> pending -> dequeue -> processing -> ack -> removed
```

改動前，MemoryBackend 沒有實現相同的生命週期。它的 `dequeue` 會直接從唯一的
佇列中刪除訊息。雖然介面上存在 `ack` 方法，但被 dequeue 的訊息已經不再儲存，
後續 ACK 通常找不到可刪除的訊息。因此，MemoryBackend 實際上沒有有效的
`processing` 狀態和 ACK 生命週期。

## 狀態模型

佇列長度不是單一數字。QueueFS 必須維護以下當前狀態指標：

| 欄位 | 含義 |
| --- | --- |
| `pending` | 尚未 dequeue、可被 worker 獲取的訊息數 |
| `processing` | 已 dequeue、尚未 ACK 的訊息數 |
| `unacked` | `pending + processing` |

佇列完成條件必須是：

```text
pending == 0 && processing == 0
```

等價於 `unacked == 0`。

當 handler 失敗、ACK 失敗或 worker 退出時，只要訊息仍未 ACK，就不能視為完成。
訊息只能通過恢復流程重新進入 pending，或通過成功 ACK 離開佇列。

## 狀態歸屬

QueueFS 是佇列生命週期狀態的 Owner。各 backend 必須在 enqueue、dequeue、ACK、
clear 和 recovery 操作中維護 `pending` 與 `processing`。

Python 不應再組合 backend 的 `pending` 和程序內計數來判斷完成。本地 worker
計數仍可作為執行時觀測指標，但它不屬於佇列長度，也不是完成狀態的權威來源。

以下累計計數同樣不屬於佇列長度：

- `processed`
- `requeue_count`
- `error_count`

它們描述的是處理結果，而不是當前佇列佔用。本次修復中可以繼續由處理層或指標層
維護。如果需要將它們下沉到 QueueFS，必須先定義顯式的處理結果協議，因為 backend
無法僅根據 dequeue 或 ACK 推斷 handler 的處理結果。

## Backend 契約

QueueFS 應提供一個原子狀態操作：

```json
{
  "pending": 3,
  "processing": 2
}
```

`unacked` 由 `pending + processing` 派生。為保持相容和 worker 排程語義，現有
`/size` 可以繼續表示 `pending`。
QueueFS 控制檔名屬於保留路徑段，佇列名不能以 `enqueue`、`dequeue`、`peek`、
`size`、`status`、`messages`、`clear` 或 `ack` 結尾。

各後端要求：

- **SQLite：** 在同一個資料庫快照中讀取兩個計數。
- **Cache：** 通過一個 Lua 指令碼返回 `LLEN(pending)` 和
  `ZCARD(processing)`。
- **Memory：** 增加 processing 集合；dequeue 將訊息移入該集合，ACK 從該集合
  刪除訊息。

`NamedQueue.get_status()` 只消費 backend 返回的狀態快照。`wait_complete()` 和
`is_all_complete()` 只使用 backend 維護的 `pending` 與 `processing` 判斷完成。
