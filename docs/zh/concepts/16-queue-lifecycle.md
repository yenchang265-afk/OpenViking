# 任務狀態

QueueFS 通過同一份後端狀態快照判斷佇列是否完成：只有 `pending` 和 `processing` 都為零，佇列才為空。僅檢查待出隊訊息數不能證明處理已結束。

佇列為空只描述當前沒有未確認的訊息，不證明每個業務操作成功，也不保證之後不會入隊新任務。需要確認一次匯入或會話提交是否成功，請查詢對應 [task](../api/17-tasks.md)，檢查最終狀態及錯誤。

## 問題

舊實現通過兩個相互獨立的資料來源推斷完成狀態：

- QueueFS `/size`：返回仍可被 dequeue 的 pending 訊息數。
- Python `NamedQueue._in_progress`：返回當前程序觀察到的執行中任務數。

這兩個值無法原子讀取或更新。QueueFS 將訊息從 `pending` 移到
`processing` 後，另一個執行緒、event loop 或程序可能同時觀察到 `size == 0`，
且其讀取到的 `_in_progress == 0`，從而在訊息 ACK 前錯誤地判斷佇列已經完成。

將本地計數放到 task 建立之前或之後，只能縮小部分時序視窗。它無法讓 backend
狀態遷移與本地計數更新成為同一個原子操作，因此無法嚴格解決跨執行緒、跨 event loop
或跨程序的併發判斷問題。

## ACK 生命週期

SQLite 和快取後端實現了 ACK 生命週期：

```text
enqueue -> pending -> dequeue -> processing -> ack -> removed
```

MemoryBackend 也維護 `processing` 集合：dequeue 將訊息移入該集合，ACK 再移除訊息。它與其他後端使用相同的完成條件，但不提供程序重啟後的持久化恢復。

## 狀態模型

佇列長度不是單一數字。QueueFS 維護以下當前狀態指標：

| 欄位 | 含義 |
| --- | --- |
| `pending` | 尚未 dequeue 的訊息數，包含暫時因分組佔用而不可投遞的訊息 |
| `processing` | 已 dequeue、尚未 ACK 的訊息數 |
| `unacked` | `pending + processing` |

佇列完成條件必須是：

```text
pending == 0 && processing == 0
```

等價於 `unacked == 0`。

當 handler 失敗、ACK 失敗或 worker 退出時，只要訊息仍未 ACK，就不能視為完成。
訊息可通過 `/retry` 或恢復流程重新進入 pending，或通過成功 ACK 離開佇列。

## 狀態歸屬

QueueFS 是佇列生命週期狀態的 Owner。各 backend 必須在 enqueue、dequeue、ACK、
retry、clear 和 recovery 操作中維護 `pending` 與 `processing`。

Python 不應再組合 backend 的 `pending` 和程序內計數來判斷完成。本地 worker
計數仍可作為執行時觀測指標，但它不屬於佇列長度，也不是完成狀態的權威來源。

以下累計計數同樣不屬於佇列長度：

- `processed`
- `requeue_count`
- `error_count`

它們描述的是處理結果，而不是當前佇列佔用。由處理層或指標層維護。如果需要將它們下沉到 QueueFS，必須先定義顯式的處理結果協議，因為 backend
無法僅根據 dequeue 或 ACK 推斷 handler 的處理結果。

## Backend 契約

QueueFS `/status` 返回同一次原子讀取取得的狀態：

```json
{
  "pending": 3,
  "processing": 2
}
```

`unacked` 由 `pending + processing` 派生。為保持相容和 worker 排程語義，現有
`/size` 可以繼續表示 `pending`。
QueueFS 控制檔名屬於保留路徑段，佇列名不能以 `enqueue`、`enqueue_ext`、`dequeue`、`peek`、
`size`、`status`、`messages`、`clear`、`ack` 或 `retry` 結尾。

各後端要求：

- **SQLite：** 在同一個資料庫快照中讀取兩個計數。
- **Cache：** 通過一個 Lua 指令碼返回 `ZCARD(pending)` 和
  `ZCARD(processing)`。
- **Memory：** 維護 processing 集合；dequeue 將訊息移入該集合，ACK 從該集合
  刪除訊息。

`NamedQueue.get_status()` 只消費 backend 返回的狀態快照。`wait_complete()` 和
`is_all_complete()` 只使用 backend 維護的 `pending` 與 `processing` 判斷完成。

## 核心分組排程

`/enqueue_ext` 按訊息提供可選、互斥的 key，同一佇列可以混用三類訊息：

| 訊息後設資料 | 同一佇列內的語義 |
| --- | --- |
| 兩個 key 都沒有 | 普通訊息，獨立投遞 |
| `serial_key` | 同 key 同時只處理一條訊息，最終 ACK 後才能投遞下一條 |
| `group_key` | 同 key 可以併發處理多條訊息，但全部歸屬同一個消費者例項 |

兩個 key 的名稱空間及不同佇列相互獨立，不承諾嚴格 FIFO。退出恢復保留原訊息 ID；
`serial_key` 的原訊息 ACK 前，同 key 後續訊息仍阻塞。`group_key` 在最後一條
在途訊息 ACK 後釋放消費者歸屬。重複 ACK 不改變其他訊息的佔用。

- **Redis/Cache：** 相同 `service_name` 和佇列路徑下支援跨 backend 例項約束，
  消費者身份為 backend 例項，退出恢復沿用心跳機制。
- **Memory：** 支援單 backend 例項內的兩種 key，退出後丟失狀態。
- **SQLite：** 僅支援單消費者程序；`group_key` 保留後設資料、按普通訊息分發，
  `serial_key` 約束程序內併發，啟動時重投未 ACK 訊息。

SQLite 自動補齊可空 `serial_key` 列與索引，舊訊息該列為 `NULL`；
補齊 `schedule_seq` 排程序號並按原行 ID 初始化，替換原 status 索引。
存量訊息的 ID、payload 和原始順序保持不變。
Redis 佈局與舊版不相容：升級前須排空 service 下共享佇列、統一升級生產者與消費者，
不支援新舊版本混用或自動遷移積壓。

擴充套件入隊使用 `QFSE` v1 大端幀（固定頭、TLV、原始 payload），header 上限 64 KiB。
`group_key` / `serial_key` 的 TLV type 為 `2` / `3`，flags 為 `1`，
key 長度為 1–4096 UTF-8 bytes；拒絕互斥欄位並存、重複或無效 key、未知必選欄位，
跳過未知可選欄位。完整幀定義見原始碼樹中的
`crates/ragfs/src/plugins/queuefs/enqueue_protocol.rs`。

舊 `/enqueue` 仍接收原始 payload；dequeue、peek、messages 和 ACK 格式不變。
無可投遞訊息時 `/dequeue` 返回 `{}`，即使 pending 非零。擴充套件 write 返回位元組數，
UUID 由呼叫方持有；同隊列尚存 ID 重複入隊返回 `AlreadyExists`，ACK 後不保留去重記錄。
`clear` 和刪除佇列同時清理排程狀態。業務處理、合併及寫回結束後才 ACK。

Python `enqueue(..., serial_key=..., group_key=...)` 在註冊 Work 前校驗 key，
擴充套件入隊返回實際 UUID；無 key 時保持舊路徑。ExternalTask 使用帳號、任務型別和
provider 顯式返回的 key 生成 `serial_key`；返回 `None` 時不啟用序列排程。
同帳號跨使用者的相同 key 共享序列約束。
admission busy 或本地 finalization 未完成時返回 `ProcessResult.retry()`；
通用 middleware 先儲存 Work 為 pending，再寫 `/retry`，釋放 worker 槽位。
原訊息 ID、payload、時間戳和 key 不變，無 delay 排程；
同 serial key 的後續訊息仍須等待原訊息最終 ACK，其他 key 可繼續投遞。
`/retry` 只移動 processing 訊息，重複 retry 和 pending ACK 均為空操作。
舊 `ProcessResult.requeued()` 仍表示 handler 已釋出替代訊息，原訊息照常 ACK。
External 業務結果儲存最多嘗試三次；向外傳播的執行、清理及
Task/Work 儲存異常均不 ACK，已處理的業務失敗在 Work 結算後 ACK。
取消沿用通用 Task middleware 契約；ACK 沿用通用佇列行為，寫入失敗記錄
warning，訊息留待恢復，消費繼續。本版本 ExternalTaskService 保留基線的目標
佔用和執行保護，並在 worker 啟動前恢復佔用，以相容未攜帶 key 的舊訊息；
這些過渡保護計劃在下個版本移除。
