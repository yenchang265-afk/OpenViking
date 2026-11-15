# RAGFS 快取

RAGFS 快取是 OpenViking 的可選查詢結果與檔案內容快取層，用於加速完整檔案 `read`、`stat`、`read_dir`、`tree_directory`、`glob_directory` 和 `grep`。它只作為加速層，不作為事實資料來源；資料仍以 backend filesystem 為準。

CachedFileSystem 適用前提：

- 多個 OpenViking / RAGFS 程序共用同一 cache namespace（同一快取 Provider 上的相同 `service_name`）時，每個程序都設定 `storage.agfs.cachefs.multi_instance: true`。詳見下方「多實例」。
- 檔案和目錄變更都經過 RAGFS。
- backend 不被外部繞過 RAGFS 直接修改。
- 所有實例看到同一個 backend，且 backend 寫入返回後對每個實例都可見。S3 或 SeaweedFS 以及 MariaDB 小檔案層符合要求；每個 pod 各自的本機磁碟不符合。
- 快取 Provider 的同一 key 寫入或刪除成功後，後續讀取不會返回舊值。

這些前提只適用於讀快取層。QueueFS 和 PathLock 在選擇 cache 後端時複用
CacheRuntime，但有各自的一致性規則。PostgreSQL PathLock 使用獨立的資料庫連線。

## 快速開始

首次配置仍建議先完成基礎配置：

```bash
openviking-server init
openviking-server doctor
```

然後在 `~/.openviking/ov.conf` 中配置頂層 `cache` Provider，並在 `storage.agfs.cachefs` 選擇 `backend=cache`：

```json
{
  "service_name": "openviking-server",
  "cache": {
    "provider": "redis",
    "params": {
      "mode": "standalone",
      "endpoints": ["redis://127.0.0.1:6379"],
      "pool_size": 32,
      "connect_timeout_ms": 1000,
      "command_timeout_ms": 1000,
      "default_ttl_seconds": 300
    }
  },
  "storage": {
    "workspace": "./data",
    "agfs": {
      "backend": "local",
      "cachefs": {
        "backend": "cache"
      },
      "pathlock": {
        "provider": "cache",
        "lock_expire_secs": 30.0
      }
    }
  }
}
```

啟動 Redis 和 OpenViking：

```bash
redis-server
```

在另一個終端啟動 OpenViking：

```bash
openviking-server --config ~/.openviking/ov.conf
```

如果配置檔案在預設路徑 `~/.openviking/ov.conf`，也可以直接執行：

```bash
openviking-server
```

可用 Provider：

| Provider | 適用場景 | 備註 |
|----------|----------|------|
| `redis` | 預設交付、普通網路環境 | 內置於 RAGFS，支援 standalone、Cluster 和 Sentinel |
| `dynamic` | YuanRong、Mooncake 或閉源快取系統 | 通過版本化 C ABI 從外部動態庫載入 |

`MemoryMockProvider` 只用於單元測試和 smoke test，不是生產配置項。

### Cache PathLock

將 `storage.agfs.pathlock.provider` 設為 `cache`，即可通過共享 Redis
CacheRuntime 協調多個 OpenViking 程序的路徑鎖。OpenViking 會從頂層
`service_name` 生成 PathLock Redis namespace。獨立部署應使用不同
`service_name`。Cache PathLock 只支援內建 Redis Provider；多個實例共用 CacheFS 時，分散式路徑鎖不能取代 `storage.agfs.cachefs.multi_instance`。

分散式 PathLock 也可選擇 `provider="postgres"`，通過共享 PostgreSQL 主庫協調，
無需 Redis 或 CacheRuntime。它獨立於 `cache.provider` 配置，不會啟用 CacheFS
或改變 QueueFS。詳見 [PostgreSQL PathLock 配置](../configuration/01-server.md#postgresql-pathlock)。
無論使用哪種 PathLock，CachedFileSystem 都保留單寫者前提。

Redis HASH key 按邏輯路徑 scope 拆分：

```text
{service_name}:ov:pathlock:global:tokens
{service_name}:ov:pathlock:scope:_system:tokens
{service_name}:ov:pathlock:scope:account:{account}:tokens
```

`{service_name}` 是 Redis Cluster hash tag，因此同一部署的 PathLock key
仍位於同一 slot。Tree 衝突檢查只掃描請求所屬 scope 的 HASH。`/` 和
`/local` 使用 global HASH，但不會掃描 account 或 `_system` HASH。
跨 scope batch 會被拒絕。

不要混部仍使用舊單 HASH key 的版本和使用 scope key 的版本。先停止舊版本
寫入，至少等待 `2 * lock_expire_secs` 讓舊 key 過期，再啟動新版本。

## 配置破壞性變更

舊快取配置不再相容，升級前需要完成遷移：

| 已刪除配置 | 標準替代配置 |
|-----------|-------------|
| `storage.agfs.cache` | 頂層 `cache.provider` + `cache.params`，並設定 `storage.agfs.cachefs.backend="cache"` |
| `storage.agfs.queuefs.backend="redis"` 和 `queuefs.redis` | `storage.agfs.queuefs.backend="cache"`，並複用頂層 `cache` 配置 |
| Redis `mode="singleton"` | `mode="standalone"` |
| `tls_enabled=true` | endpoint 使用 `rediss://` |
| `read_from_replica` | 已刪除，所有讀命令統一訪問主節點 |

## DynamicProvider

OpenViking 已內建 DynamicProvider 載入器和版本化 C ABI。預設 wheel 不攜帶第三方 SDK 或 Provider 動態庫；需要接入外部快取系統時，獨立部署 Provider 動態庫並配置 `provider=dynamic`。

動態庫必須匯出以下版本化入口：

```text
openviking_cache_provider_v1
```

C 介面契約定義在 `crates/ragfs/include/openviking_cache_provider_v1.h`。Provider 返回的資料必須使用 Host allocator 分配，遵守文件中的記憶體所有權和關閉語義，禁止異常穿過 C ABI，並保證 handle 可以安全併發呼叫。

Provider 釋出物應註明 ABI 版本、目標 OS/CPU、最低執行時版本、外部 SDK 版本、動態依賴和 SHA256。依賴外部原生庫時，由 Provider 釋出方通過 RPATH、`LD_LIBRARY_PATH` 或部署說明保證動態連結器能夠找到依賴。

外部 Provider 可以獨立升級，不需要重新構建預設 OpenViking wheel；只有 DynamicProvider ABI 不相容時，才需要同步升級 OpenViking。

## 配置項

頂層 `service_name` 預設是 `"openviking-server"`，會為 CacheFS、QueueFS cache backend、
Cache PathLock 和 cache-backed 多寫 metadata 提供 Redis namespace。

頂層 `cache` 與 `storage` 並列：

| 引數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `provider` | str | 無 | Provider 名稱，支援 `redis` 和 `dynamic` |
| `params` | object | `{}` | Provider 自有引數 |

`storage.agfs.cachefs` 支援以下業務配置：

| 引數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `backend` | str | `"local"` | `local` 沿用原邏輯；`cache` 啟用 CachedFileSystem |
| `max_file_size_bytes` | int | `1048576` | CacheFS 快取完整內容的單檔案上限。部分讀取與更大的檔案直接讀取 backend；`0` 停用檔案內容快取 |
| `multi_instance` | bool | `false` | 多個實例共用此 cache namespace：每次寫入返回前刪除受影響的 bucket。需要 `backend: "cache"` 且快取預設 TTL 大於 `0`。詳見「多實例」 |
| `shared_redis_ttl_seconds` | int | `0` | 當 CacheFS 與 QueueFS、cache PathLock 或 expiry 排程共用同一個 Redis 服務時，統一覆蓋查詢 bucket 的 TTL；`0` 表示沿用 Provider 預設 TTL |

`shared_redis_ttl_seconds` 統一作用於 `stat`、`read_dir`、`tree_directory`、`glob_directory`、`grep` 和檔案內容 `read` bucket，不表達檔案級優先順序。共享 Redis 時可將該值設為低於 Provider 的 `default_ttl_seconds`，以縮短快取保留時間。CacheFS 使用獨立 Redis 服務時，OpenViking 會忽略該選項。

`storage.agfs.pathlock` 控制 PathLock 儲存：

| 引數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `provider` | str | `"filesystem"` | `filesystem`、`memory`、`sqlite`、`postgres` 或 `cache`；見 [SQLite 配置](../configuration/01-server.md#storage) 和 [PostgreSQL 配置](../configuration/01-server.md#postgresql-pathlock) |
| `postgres_dsn_env` | str / null | `null` | `postgres` 必填；儲存 DSN 的服務程序環境變數名 |
| `lock_expire_secs` | float | `30.0` | 鎖 stale 超時；不得小於 `1.0` |

Redis 配置：

| 引數 | 預設值 | 說明 |
|------|--------|------|
| `mode` | `"standalone"` | Redis 部署模式 |
| `endpoints` | `["redis://127.0.0.1:6379"]` | Redis 連線地址；`redis://` 使用明文傳輸，`rediss://` 使用 TLS |
| `username` | `""` | Redis ACL 使用者名稱 |
| `password_env` | `""` | 存放 Redis 密碼的環境變數名 |
| `pool_size` | `32` | 命令併發數 |
| `connect_timeout_ms` | `10000` | 連線超時，單位為毫秒 |
| `command_timeout_ms` | `0` | 命令超時，單位為毫秒；`0` 表示不設定命令超時 |
| `default_ttl_seconds` | `300` | CacheFS query bucket 使用的 runtime 預設 TTL；`0` 表示不設定 TTL |
| `tls_insecure_skip_verify` | `false` | 跳過 `rediss://` 證書校驗，僅用於受控測試環境 |

所有 Redis 讀命令均傳送到主節點，避免 QueueFS 讀取到延遲的佇列狀態。需要傳輸加密時使用 Redis TLS，CacheRuntime 不額外增加應用層資料加密格式。

當 `command_timeout_ms=0` 時，CacheRuntime 不會主動中斷慢 Redis 命令。它也不會在固定時長後自動回源。

DynamicProvider 配置：

`cache.params.library` 由 OpenViking 用於載入動態庫，其餘欄位由外部 Provider 定義並作為 JSON 傳入 `create`。實際引數以 Provider 釋出說明為準。

```json
{
  "cache": {
    "provider": "dynamic",
    "params": {
      "library": "/opt/openviking/providers/libopenviking_cache_provider.so",
      "endpoint": "127.0.0.1:31501",
      "request_timeout_ms": 5000
    }
  }
}
```

## 整體架構

RAGFS 將 Provider 訪問和各業務消費者分開：

- `CachedFileSystem`：實現檔案系統語義，包括 cache hit/miss、backend 回源、回填、失效、request 校驗和指標。
- `CacheRuntime`：向業務層提供統一基礎操作，啟動時繫結內建 RedisProvider 或外部 DynamicProvider。
- `QueueFS` 和 `RedisPathLockProvider`：複用共享 CacheRuntime 儲存佇列和分散式鎖。RedisPathLockProvider 要求使用內建 RedisProvider。

呼叫關係：

```text
OpenViking
  -> RAGFS / MountableFS
       |-> CachedFileSystem ------\
       |-> QueueFS cache backend --+-> shared CacheRuntime -> RedisProvider
       `-> RedisPathLockProvider --/                     `-> DynamicProvider
       `-> Backend FileSystem
```

CachedFileSystem 和 QueueFS 可以使用 RedisProvider 或 DynamicProvider。
RedisPathLockProvider 依賴 Redis Lua，因此只使用 RedisProvider。檔案系統語義
保留在 CachedFileSystem；外部 Provider 只通過穩定 C ABI 提供 key-value
基礎操作。

## 快取物件

RAGFS 快取只讀查詢結果。不再儲存舊的路徑物件快取。

### Query Bucket

每個路徑和操作對應一個 HASH bucket：

```text
{<service_name>}:ov:cache:v1:<path_key>:<op>
```

每個 bucket 保留 `__epoch` field，用於儲存隨機版本 token。查詢 field 使用
`xxh3_128(canonical_request_json)`，value 是 `QueryCacheEnvelope`，包含：

- `request`
- `payload`

RAGFS 返回快取前會比較已存 `request` 和當前請求。這樣可以防止 hash 碰撞或請求編碼變化導致誤讀。

支援的操作：

- `read`（不超過 `max_file_size_bytes` 的完整檔案讀取）
- `stat`
- `read_dir`
- `tree_directory`
- `glob_directory`
- `grep`

### Query Index

所有活躍 bucket 會註冊到一個 ZSET：

```text
{<service_name>}:ov:cacheidx:v1
```

ZSET member 是 bucket key。score 是 `expire_at_ms`。Redis hash tag 會讓 bucket 和 index 落在同一個 cluster slot，CacheFS 可以用一個 Lua 指令碼同時更新兩者。寫入發生時，RAGFS 通過這個 index 找到受影響 bucket，不掃描全部 Redis key。

## 一致性與失效

RAGFS 不需要分散式寫鎖。每次寫入後，RAGFS 物理刪除受影響的 query bucket。

普通路徑變更會在記憶體中構造受影響 bucket：

- 精確路徑 bucket：`read`、`stat`、`read_dir`、`tree_directory`、`glob_directory`、`grep`
- 父目錄 bucket：`read_dir(parent)`
- 祖先遞迴 bucket：`tree_directory`、`glob_directory`、`grep`

然後對每個 bucket 執行一個指令碼，原子完成 `UNLINK` bucket 和 `ZREM` index member。

對遞迴路徑操作，如 `remove_all`、`rename`、`replace`，RAGFS 還會掃描 query index：

```text
ZSCAN {<service_name>}:ov:cacheidx:v1 MATCH '{<service_name>}:ov:cache:v1:<path_key>/*:*' COUNT 1000
```

命中的後代 bucket 會通過同一個 bucket/index 指令碼刪除。
快取 miss 後，原子指令碼會在回源前取得 `__epoch` 並註冊 bucket。
另一個指令碼只在 epoch 未變化時寫入 query field 並重新整理 index。
`UNLINK` 成功後會刪除 epoch，因此舊查詢無法重新寫入陳舊資料。
無 TTL 配置下，未完成回填的 epoch 在 300 秒後過期；成功回填仍永久保留。

未啟用 `multi_instance` 時的典型寫入順序：

```text
執行 backend 變更
-> 投遞非同步失效任務
-> 返回結果
後臺任務 -> ZSCAN 獲取後代 bucket
後臺任務 -> 構造精確路徑和祖先 bucket
後臺任務 -> 對每個 bucket 執行 bucket/index 刪除指令碼
```

啟用 `multi_instance` 時，相同步驟在返回結果前執行。bucket 刪除並行執行，失敗時以帶抖動的 10、20、40 ms 退避重試三次。

如果 Provider 失敗，RAGFS 會以當前請求的 backend 結果為準，記錄快取錯誤，並且不快取這次結果。

### 多實例

多個 OpenViking 實例可以共用一個 cache namespace（相同 `service_name`、相同 Redis）。每個實例都能命中其他實例回填的快取，每次失效也會作用到所有實例。在每個實例上設定 `multi_instance: true`：

```json
{
  "storage": {
    "agfs": {
      "cachefs": {"backend": "cache", "multi_instance": true}
    }
  }
}
```

未設定時，失效在寫入返回後於背景執行。單一程序內這段時間很短，但另一個實例若在寫入後立即讀取（例如寫入方通知了它），仍可能拿到舊的目錄列表或 `stat`。設定 `multi_instance` 後，寫入要等受影響的 bucket 刪除後才返回，因此寫入返回後才開始的讀取都會未命中並讀取 backend。已在進行中的讀取由上述 epoch 檢查保護。

此模式下寫入耗時較長：每次寫入都要等待 bucket 刪除（每批 16 個 bucket 約一次 Redis 往返，遞迴操作另加一次 `ZSCAN`）。

快取預設 TTL 必須大於 `0`（使用 Redis 時為 `default_ttl_seconds`），否則啟動失敗。

要求與剩餘風險：

- backend 必須為每個實例提供寫後讀一致性（見本頁開頭的前提）。
- bucket 刪除重試後仍失敗時，寫入照樣成功，`invalidation_failures` 會增加。**其他實例在 bucket TTL 到期前可能返回舊結果。** 請對此計數器設定告警，並在命中率允許的範圍內盡量縮短 `default_ttl_seconds`。
- Redis Sentinel 和 Cluster 為非同步複製。故障切換可能遺失舊主節點已確認的刪除，影響同樣以 TTL 為上限。可考慮在主節點設定 `min-replicas-to-write`。
- 下方的請求合併僅限單一程序。多個實例同時未命中同一查詢時，各自會讀取一次 backend。

從先前的版本計數器 CacheFS 升級：其 `traversal_mode` 和 `bypass_prefixes` 選項會被忽略（`max_file_size_bytes` 意義不變），其 `ov:cache:v2:*` 鍵也不再讀取。這些鍵會隨 TTL 到期，或以 `redis-cli --scan --pattern '<service_name>:ov:cache:v2:*' | xargs redis-cli unlink` 刪除。

## 請求合併

當多個請求同時讀取同一個未快取查詢時，`CachedFileSystem` 會用程序內 inflight 表合併請求：

```text
第一個 miss 請求成為 leader，負責回源和回填。
後續相同 key 的請求成為 follower，等待 leader 結果。
請求完成後刪除 inflight 條目。
```

這隻減少同一 OpenViking 程序內的重複 backend 訪問，不改變 Provider 的一致性邊界。

### 檔案內容

不超過 `max_file_size_bytes` 的完整檔案 `read`（offset 為 0、未指定 size）使用該檔案路徑上的 `read` bucket。它沿用與查詢 bucket 相同的 epoch、回填與失效規則，因此寫入、`truncate`、`rename`、`replace` 或 `remove_all` 會像刪除該檔案的 `stat` 一樣刪除它。欄位內容是原始位元組，前面加一個記錄路徑的小型二進位標頭，而不是 JSON。

部分讀取、超過上限的檔案與執行期內部檔案直接讀取 backend，並計為 `read` 略過。`read_to_path` 下載直接從 backend 串流。

在單一 backend 且啟用加密的 mount 上，CacheFS 位於加密層之下，因此快取中存的是密文，每次命中都會解密。多寫入 mount 在每個 backend 內加密，CacheFS 因此位於加密層之上；在這種 mount 上，只要設定了加密，就永遠不快取檔案內容。

請依允許快取的檔案估算 Redis 容量：每個快取的檔案在 TTL 到期前最多佔用 `max_file_size_bytes`。

## 快取範圍

CacheFS 快取不超過 `max_file_size_bytes` 的完整檔案內容，以及 `stat`、`read_dir`、`tree_directory`、`glob_directory` 和 `grep` 的查詢結果。快取鍵由路徑、操作型別和查詢引數生成。寫操作成功後會主動刪除受影響的查詢 bucket。`.path.ovlock`、`.exact.ovlock.*` 等 PathLock 內部檔案不會進入查詢快取；直接查詢這些檔案時繞過 CacheFS。

## 故障與觀測

快取層不能影響檔案系統正確性：

- `get` 失敗：回源 backend。
- `put` 失敗：記錄錯誤，保留 backend 結果。
- `delete` 失敗：重試後記錄錯誤並累計 `invalidation_failures`，TTL 兜底。
- Provider 不可用：不返回舊快取，以 backend 結果為準。

建議重點觀察：

- query hit / miss
- provider get / put / delete 延遲
- cache set / delete 失敗
- `invalidation_failures`（啟用 `multi_instance` 時，其他實例在 TTL 到期前可能返回過期結果）
- backend fallback 次數

## 共享 Redis 部署

CacheFS 查詢 bucket 可以與 QueueFS、cache PathLock 和 expiry 排程共用同一個 Redis 服務。Redis 的 `maxmemory` 和淘汰策略作用於整個服務，因此 `shared_redis_ttl_seconds` 只是快取保留時間的上限，不是容量預留，也不能保證有狀態 key 一定不被淘汰。

- 當快取應為有狀態負載讓出容量時，將 `shared_redis_ttl_seconds` 設為低於 `cache.redis.default_ttl_seconds`。
- 保持 `shared_redis_ttl_seconds=0` 可沿用 Provider 預設 TTL。
- 如果需要硬性的容量隔離，請使用獨立 Redis 服務；僅切換邏輯 database 不會隔離 `maxmemory` 或淘汰策略。
- 共用同一個服務時，應同時觀察 `used_memory`、`evicted_keys` 和快取 hit/miss 指標。

## 推薦使用順序

1. 關閉快取驗證 backend 基線行為。
2. 用內建 `redis` 驗證真實遠端快取收益。
3. 對高效能或閉源快取系統使用獨立釋出的 DynamicProvider `.so`。
4. 快取完整檔案讀取以及 `stat`、`read_dir`、`tree_directory`、`glob_directory` 和 `grep` 查詢結果。

RAGFS 快取負責按檔案系統語義失效，Provider 負責決定快取物件放在哪裡。backend 仍是事實來源，快取命中必須先通過 request 校驗才會返回。

啟用後，將重複讀取和檔案更新後的失效行為與基線比較。確認返回內容保持最新，再判斷命中率提升是否帶來收益。
