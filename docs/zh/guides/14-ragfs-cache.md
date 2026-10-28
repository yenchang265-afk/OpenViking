# RAGFS 快取

RAGFS 快取是 OpenViking 的可選讀快取層，用於加速檔案全量讀取和目錄讀取。它只作為加速層，不作為事實資料來源；資料仍以 backend filesystem 為準。

CachedFileSystem 適用前提：

- 多個 OpenViking / RAGFS 程序共用同一 cache namespace（同一快取 Provider 上的相同 `service_name`）時，每個程序都要設定 `storage.agfs.cachefs.multi_instance: true`。見下文「多實例部署」。
- 檔案和目錄變更都經過 RAGFS。
- backend 不被外部繞過 RAGFS 直接修改。
- 所有實例看到同一個 backend，且 backend 寫入返回後，所有實例都能讀到。S3 或 SeaweedFS、MariaDB 小檔案分層符合要求；每個 pod 各自的本機磁碟不符合。
- 快取 Provider 的同一 key 寫入、刪除或遞增成功後，後續讀取不會返回舊值。

這些前提只適用於讀快取層。QueueFS 和 PathLock 也複用 CacheRuntime，但有各自的一致性規則。

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
      "default_ttl_seconds": 3600
    }
  },
  "storage": {
    "workspace": "./data",
    "agfs": {
      "backend": "local",
      "cachefs": {
        "backend": "cache",
        "max_file_size_bytes": 1048576,
        "bypass_prefixes": ["/queue", "/tmp"]
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
`service_name`。Cache PathLock 只支援內建 Redis Provider。CachedFileSystem 的快取一致性不依賴 PathLock，而是使用自己的版本計數器（見「一致性與失效」）。

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

CacheFS key 由 `ov:cache:v1` 改為 `ov:cache:v2`，快取 envelope 改為格式版本 2。升級後快取會清空一次。新舊版本不會讀取對方的條目，但舊實例不會遞增新版本的計數器，因此**不要讓新舊版本同時使用同一個 namespace**。升級整個叢集時：先在每個實例上把 `storage.agfs.cachefs.backend` 設為 `local`，部署新版本，再重新啟用 CacheFS。也可以先停止所有舊實例，再啟動新實例。

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
| `max_file_size_bytes` | int | `1048576` | 允許進入快取的最大完整檔案大小 |
| `traversal_mode` | str | `"backend"` | 遞迴 API 使用 backend 遍歷或 `cached_traversal` |
| `bypass_prefixes` | list[str] | `[]` | 強制繞過快取的路徑字首 |
| `multi_instance` | bool | `false` | 多個程序共用快取 namespace 時，在每個實例上設定。需要 `backend="cache"`、支援原子 `incrby` 的 Provider，使用 Redis 時還需要 `default_ttl_seconds > 0` |

`storage.agfs.pathlock` 控制 PathLock 儲存：

| 引數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `provider` | str | `"filesystem"` | `filesystem`、`memory` 或 `cache` |
| `lock_expire_secs` | float | `30.0` | 鎖 stale 超時；不得小於 `1.0` |

Redis 配置：

| 引數 | 預設值 | 說明 |
|------|--------|------|
| `mode` | `"standalone"` | Redis 部署模式 |
| `endpoints` | `["redis://127.0.0.1:6379"]` | Redis 連線地址；`redis://` 使用明文傳輸，`rediss://` 使用 TLS |
| `username` | `""` | Redis ACL 使用者名稱 |
| `password_env` | `""` | 存放 Redis 密碼的環境變數名 |
| `pool_size` | `32` | 命令併發數 |
| `connect_timeout_ms` | `1000` | 連線超時 |
| `command_timeout_ms` | `20` | 命令超時 |
| `default_ttl_seconds` | `3600` | 預設 TTL；`0` 表示不設定 TTL |
| `tls_insecure_skip_verify` | `false` | 跳過 `rediss://` 證書校驗，僅用於受控測試環境 |

所有 Redis 讀命令均傳送到主節點，避免 QueueFS 讀取到延遲的佇列狀態。需要傳輸加密時使用 Redis TLS，CacheRuntime 不額外增加應用層資料加密格式。

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

- `CachedFileSystem`：實現檔案系統語義，包括 cache hit/miss、backend 回源、回填、失效、版本校驗和指標。
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

RAGFS 主要快取三類物件。

### 檔案快取

檔案 key 使用穩定名稱空間和路徑 hash：

```text
<service_name>:ov:cache:v2:file:<hash(path)>
```

檔案 value 是 `CacheEnvelope`，包含檔案內容、物件型別、路徑，以及它所依賴的版本計數器快照。全量讀取命中後，RAGFS 會先校驗 envelope 和每個記錄的計數器，再返回內容。

預設策略會優先快取 `.abstract.md` 和 `.overview.md` 這類摘要檔案；超過 `max_file_size_bytes` 的檔案不會進入快取。非全量 range read 也會繞過快取。

### 目錄快取

目錄 key：

```text
<service_name>:ov:cache:v2:dir:<hash(path)>
```

目錄快取儲存 backend 原始 `read_dir` entries，而不是許可權過濾後的最終結果。許可權、角色和 agent context 仍在 OpenViking 上層即時處理。

這樣同一份目錄快取可以服務 `ls`、`tree`、`glob`、`grep` 的檔案收集階段，以及刪除或移動前的路徑收集。

### 版本計數器

兩類計數器決定 envelope 是否仍然有效：

```text
<service_name>:ov:cache:v2:ver:<hash(path)>       單一路徑的物件版本
<service_name>:ov:cache:v2:subtree:<hash(scope)>  單一目錄 scope 的 generation
```

`path` 的 envelope 會記錄 `path` 的物件版本，以及每個祖先 scope（含 `path` 本身）的 subtree generation。計數器以十進位整數儲存，因此 Provider 可以用原子 `INCRBY` 遞增。遺失的計數器（過期或被淘汰）會以隨機值通過 `SET NX` 重建，所有實例都會採用同一個值，舊 envelope 也不會意外匹配。

`remove_all` 和目錄 `rename` 可能讓 Provider 中殘留子孫 key。RAGFS 會 bump subtree generation，讓所有子孫 envelope 校驗失敗，後續真實讀取會回源並重建快取。

## 一致性與失效

RAGFS 用兩條規則維持快取正確：

1. **先快照再讀取。** miss 時，RAGFS 在讀取 backend *之前*先讀取 envelope 需要的計數器，並把快照存入 envelope。
2. **先變更再遞增。** 每次 backend 變更之後，RAGFS 遞增受影響的計數器。只有所有記錄的計數器都仍是記錄值時，才返回快取命中。

因此與變更競爭的回填永遠不會通過校驗：快照若早於遞增，就不再匹配；快照若晚於遞增，backend 讀取已經包含該變更。這在多個程序之間同樣成立，不需要分散式寫鎖。

各操作遞增的計數器：

| 操作 | 遞增的計數器 |
|------|--------------|
| `create`、`write`、`write_from_path`、`truncate`、`chmod` | `ver(path)`、`ver(parent)` |
| `mkdir`、`remove`、`remove_all` | `subtree(path)`、`ver(path)`、`ver(parent)` |
| `rename`、`replace` | 兩個路徑的 `subtree` 和 `ver`，以及兩個父目錄的 `ver` |
| `ensure_parent_dirs` | 每個祖先 scope 的 `ver` |

變更後 RAGFS 仍會刪除受影響的 `file` 和 `dir` key，但只是為了釋放空間；真正讓條目失效的是計數器遞增。

典型寫入順序：

```text
獲取程序內操作鎖
-> 執行 backend 變更
-> 遞增受影響的計數器（INCRBY）
-> 刪除受影響的 file/dir key
-> 返回結果
```

### 多實例部署

多個 OpenViking 實例可以共用同一個 cache namespace（相同 `service_name`、相同 Redis）。每個實例都能命中其他實例回填的快取，每次遞增也會作用於所有實例。請在每個實例上設定 `multi_instance: true`：

```json
{
  "storage": {
    "agfs": {
      "cachefs": {"backend": "cache", "multi_instance": true}
    }
  }
}
```

多實例模式改變兩件事：

- 完整寫入不再用寫入的位元組回填快取。否則兩個實例寫入同一檔案時，回填順序可能與 backend 寫入順序相反。改由下一次讀取回填。
- Provider 必須支援原子 `incrby`，否則啟動失敗（內建 Redis Provider 支援；DynamicProvider 必須匯出該函式）。使用 Redis 時，`default_ttl_seconds` 必須大於 `0`。

前提與剩餘風險：

- backend 必須讓所有實例具備寫後可讀的一致性（見本頁開頭的前提）。
- 計數器遞增在重試（10、50、200 ms）後仍失敗時，寫入仍會成功，失敗的實例會對該路徑繞過快取，並累加 `invalidation_failures`。**其他實例可能繼續返回舊條目，直到其 TTL 到期。** 請對此計數器設定告警，並在命中率允許的範圍內縮短 `default_ttl_seconds`。
- Redis Sentinel 和 Cluster 採用非同步複製。故障切換可能遺失舊主節點已確認的遞增，影響同樣以 TTL 為上限。可考慮在主節點設定 `min-replicas-to-write`。
- Redis Cluster 模式下，同一路徑的計數器位於不同 slot，miss 時會逐個 key 讀取。

未啟用 `multi_instance` 時，同一程序內的寫入由操作鎖序列化，完整寫入也會回填快取。不支援 `incrby` 的 Provider 會退回 GET+SET 遞增，僅適用於單一程序。

## 請求合併

當多個請求同時讀取同一個未快取的小檔案或目錄時，`CachedFileSystem` 會用程序內 inflight 表合併請求：

```text
第一個 miss 請求成為 leader，負責回源和回填。
後續相同 key 的請求成為 follower，等待 leader 結果。
請求完成後刪除 inflight 條目。
```

這隻減少同一 OpenViking 程序內的重複 backend 訪問，不改變 Provider 的一致性邊界。

## 快取策略

RAGFS 會自動繞過不適合快取的路徑：

- 鎖檔案：`.path.ovlock`、`*.lock`、`*.lck`
- 控制文件：`enqueue`、`dequeue`、`peek`、`ack`
- 瞬時狀態：`heartbeat`、`lease`、`cursor`、`offset`、`pid`
- 使用者通過 `bypass_prefixes` 指定的路徑字首

許可權敏感目錄建議加入 `bypass_prefixes`。如果目錄原始 entries 本身就依賴呼叫者許可權，不應快取該目錄。

## 故障與觀測

快取層不能影響檔案系統正確性：

- `get` 失敗：回源 backend。
- `put` 失敗：記錄錯誤，路徑進入 bypass。
- `delete` 失敗：記錄錯誤，路徑或 scope 進入 bypass。
- 計數器遞增失敗：重試後仍失敗則累加 invalidation failure，並讓該路徑在本實例上進入 bypass。
- Provider 不可用：不返回舊快取，以 backend 結果為準。

建議重點觀察：

- cache hit / miss / bypass
- stale versions（計數器已變動而被拒絕的條目）
- invalidation failures（重試後仍失敗的計數器遞增）
- provider get / put / delete 延遲
- cache set / delete 失敗
- inflight leader / follower / backend saved
- backend fallback 位元組數

啟用 CacheFS 後，OpenViking Studio 會在首頁儀表板顯示整體快取命中率，並在「監控 → 快取」中依操作（`read`、`read_dir`、`tree`、`grep`）顯示明細。兩者都讀取 `GET /api/v1/console/cache`，統計自伺服器啟動以來的計數。命中率為 `hits / (hits + misses)`，因策略而略過的讀取另行統計。同一端點也會回報 `stale_versions` 和 `invalidation_failures`。同樣的計數也以 `openviking_ragfs_cache_requests_total`、`openviking_ragfs_cache_operation_requests_total`、`openviking_ragfs_cache_stale_versions_total` 和 `openviking_ragfs_cache_invalidation_failures_total` 指標匯出。

## 推薦使用順序

1. 關閉快取驗證 backend 基線行為。
2. 用內建 `redis` 驗證真實遠端快取收益。
3. 對高效能或閉源快取系統使用獨立釋出的 DynamicProvider `.so`。
4. 先快取摘要檔案和 raw `read_dir`，再擴充到更多普通小檔案。
5. 將鎖、控制面和許可權敏感路徑加入 `bypass_prefixes`。

RAGFS 快取負責按檔案系統語義失效，Provider 負責決定快取物件放在哪裡。backend 仍是事實來源，快取命中必須先通過 envelope 和版本校驗才會返回。

啟用後，將重複讀取和檔案更新後的失效行為與基線比較。確認返回內容保持最新，再判斷命中率提升是否帶來收益。
