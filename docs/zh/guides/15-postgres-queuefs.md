# PostgreSQL QueueFS

QueueFS 可以將佇列、訊息和消費者租約持久化到 PostgreSQL，保留 `/enqueue`、`/enqueue_ext`、`/dequeue`、`/peek`、`/size`、`/status`、`/messages`、`/clear`、`/ack`、`/retry` 控制檔案介面。多個例項連線同一個可寫主庫並使用相同 `service_name` 時，可以競爭消費同一佇列。

## 初始化與配置

由管理員或 migration role 在目標資料庫執行一次：

```sh
psql "$OV_QUEUE_PG_DSN" -v ON_ERROR_STOP=1 \
  -f crates/ragfs/src/plugins/queuefs/postgres_schema.sql
```

指令碼建立版本表和三個業務表，執行時只檢查版本及持久化屬性，並執行 DML，不建表或遷移。初始化指令碼不是可重複執行的遷移工具；已安裝的版本無需重新執行。

為專用執行帳號授權，替換下面的 `queue_runtime`：

```sql
GRANT USAGE ON SCHEMA public TO queue_runtime;
GRANT SELECT ON public.ov_queuefs_schema TO queue_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE
  ON public.ov_queuefs_queues, public.ov_queuefs_workers, public.ov_queuefs_messages
  TO queue_runtime;
GRANT USAGE ON SEQUENCE public.ov_queuefs_messages_sequence_seq TO queue_runtime;
```

在每個伺服器或 worker 啟動環境中配置 DSN，例如：

```sh
export OV_QUEUE_PG_DSN='host=pg.example.com port=5432 dbname=openviking user=queue_runtime password=YOUR_PASSWORD sslmode=require'
```

合併以下片段到 `ov.conf`：

```json
{
  "service_name": "production",
  "storage": {
    "agfs": {
      "queuefs": {
        "mode": "shared",
        "backend": "postgres",
        "postgres_dsn_env": "OV_QUEUE_PG_DSN",
        "postgres_lease_seconds": 60
      }
    }
  }
}
```

配置只儲存環境變數名；連線資訊和密碼不寫入外掛配置或資料庫錯誤資訊。獨立 Rust 構建需要啟用 `ragfs` 的 `postgres` 或 `full` feature；Python binding 已啟用 `postgres`。已有的本地訊息不會隨切換自動遷移，應先排空舊佇列或另行遷移。

`service_name` 限制為 1–256 個 UTF-8 位元組，佇列名為 1–1024 位元組。`recover_stale_sec`、`busy_timeout_ms` 和 `db_path` 僅作用於 SQLite。共享消費者應使用 `mode=shared`；`mode=worker` 的佇列名仍按 worker 隔離，其他 worker 不會自動消費舊 worker 的佇列。

## 消費、持久化與恢復

- `enqueue` 提交後才返回。事務使用 `synchronous_commit=on`；資料庫必須開啟 `fsync` 並使用可靠儲存。非同步複製故障切換能否保留已確認提交，取決於 PostgreSQL 複製配置。
- `dequeue` 用佇列級事務 advisory lock 保護排程資格判斷，再通過 `FOR UPDATE SKIP LOCKED` 領取訊息，寫入當前例項的隨機 owner。按遞增 schedule sequence 優先領取，不保證嚴格的完成順序。
- `/enqueue_ext` 保留排程後設資料：同一 `serial_key` 只能有一條訊息 processing，後續訊息需等前序 ACK；同一 `group_key` 可以同時 processing 多條，但全部屬於同一消費者，最後一條 processing 訊息 ACK 或 retry 後釋放歸屬。
- `/retry` 只能由領取訊息的存活例項執行，保留訊息 ID、資料、時間戳及排程 key，將訊息放回 pending 尾部。序列訊息的後繼仍需等待原訊息 ACK。
- 訊息一直保留到 ACK。ACK 必須由領取訊息的同一個 QueueFS 例項提交，並校驗例項租約與訊息 owner；重複 ACK 或其他存活例項的 ACK 返回 false。
- 每個例項使用獨立資料庫連線維持心跳，間隔為租約秒數除以 3 後向下取整。業務任務可以執行超過租約時長，只要例項持續續約。
- 每次 `dequeue` 先檢查該佇列的 processing 訊息，只恢復 owner 已消失或租約過期的訊息。新例項啟動不重置其他存活例項的 processing 訊息。`peek` 和 `status` 不觸發恢復。
- 租約過期的例項不能續約復活，也不能繼續佇列操作，必須重啟。消費者正常關閉前應先排空業務 worker，關閉會刪除其租約；直接 drop 或程序崩潰則等待租約過期。
- `status` 在一個 SQL 快照中返回 pending 和 processing；`size` 僅返回 pending。`clear`、刪除佇列會刪除包括 processing 在內的所有訊息，應在業務側協調在途任務。

這是至少一次投遞：業務寫入完成後、ACK 前崩潰會導致重新投遞。ACK 校驗保護佇列狀態，不能撤銷已發生的業務寫入，也不能阻止失去租約的舊程序繼續執行其他系統中的副作用。業務應使用訊息 ID 做冪等控制。超時或斷連可能發生在提交成功但響應丟失之後；後端不會自動重放這類操作。

存活消費者持有的 processing 訊息不會僅因訊息年齡而恢復。業務處理拋錯、ACK 失敗，或者 dequeue 已提交但呼叫方未收到響應時，訊息可能繼續留在該消費者名下；由原例項按業務結果執行 ACK 或 retry，或停止/重啟原例項後等待租約恢復。重啟另一臺仍在共享同一佇列的伺服器，不會釋放原例項的存活租約。

每個例項使用兩個連線，資料庫操作在阻塞執行緒中執行。連線建立超時為 5 秒，事務 statement timeout 為 5 秒、lock timeout 為 1 秒；這些不是端到端網路超時。不同例項應使用相同的租約配置。錯誤只報告 SQLSTATE，不包含 PostgreSQL detail、訊息正文或 DSN。

過期 worker 行不影響恢復，但崩潰較多時可由維護任務清理：

```sql
DELETE FROM public.ov_queuefs_workers WHERE lease_expires_at <= clock_timestamp();
```

隊列表按 `service_name` 隔離資料，這是協作例項的邏輯名稱空間。執行帳號具有這些表的 DML 許可權，名稱空間不是惡意客戶端之間的資料庫許可權隔離；需要更強隔離時使用不同資料庫及帳號。後端要求普通 logged 表和停用 RLS。

PG QueueFS 只解決佇列持久化與競爭消費。部署多例項時還需分別驗證 PathLock、業務檔案儲存、account store、向量庫和程序內任務狀態的併發語義。

## 驗證

倉庫提供臨時資料庫測試入口，不會連線已有業務例項：

```sh
PG_BIN=/path/to/postgresql/bin python3 scripts/test_postgres_queuefs.py
```

測試包括競爭領取、ACK/retry 所有權、序列順序、group 歸屬、長任務心跳、過期與崩潰恢復、位元組及納秒時間戳保留、異常事務回滾、名稱空間、DML-only 帳號和未初始化資料庫拒絕啟動。完整日誌儲存到 `target/queuefs-postgres-test.log`。
