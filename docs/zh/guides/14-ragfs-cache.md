# RAGFS 快取

RAGFS 快取是 OpenViking 的可選讀快取層，用於加速檔案全量讀取和目錄讀取。它只作為加速層，不作為事實資料來源；資料仍以 backend filesystem 為準。

CachedFileSystem 適用前提：

- 只有一個 OpenViking / RAGFS 程序寫入同一 namespace。
- 檔案和目錄變更都經過 RAGFS。
- backend 不被外部繞過 RAGFS 直接修改。
- 快取 Provider 的同一 key 寫入或刪除成功後，後續讀取不會返回舊值。

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
        "namespace": "openviking",
        "max_file_size_bytes": 1048576,
        "bypass_prefixes": ["/queue", "/tmp"]
      },
      "pathlock": {
        "provider": "cache",
        "namespace": "openviking",
        "lock_expire_secs": 30.0
      }
    }
  }
}
```

啟動 Redis 和 OpenViking：

```bash
redis-server
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
CacheRuntime 協調多個 OpenViking 程序的路徑鎖。`pathlock.namespace`
為必填項，同一 OpenViking 部署的所有程序必須使用相同值。Cache PathLock
只支援內建 Redis Provider。

Redis HASH key 按邏輯路徑 scope 拆分：

```text
ov:pathlock:{namespace}:global:tokens
ov:pathlock:{namespace}:scope:_system:tokens
ov:pathlock:{namespace}:scope:account:{account}:tokens
```

`{namespace}` 是 Redis Cluster hash tag，因此同一部署的 PathLock key
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
| Redis Provider `key_prefix` | CacheFS 使用 `cachefs.namespace`；QueueFS 使用 `queuefs.cache_key_prefix` |

OpenViking 會對已刪除欄位直接返回遷移錯誤，不再靜默轉換。

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

頂層 `cache` 與 `storage` 並列：

| 引數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `provider` | str | 無 | Provider 名稱，支援 `redis` 和 `dynamic` |
| `params` | object | `{}` | Provider 自有引數 |

`storage.agfs.cachefs` 支援以下業務配置：

| 引數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `backend` | str | `"local"` | `local` 沿用原邏輯；`cache` 啟用 CachedFileSystem |
| `namespace` | str | `"openviking"` | 快取名稱空間，用於隔離不同部署或租戶 |
| `max_file_size_bytes` | int | `1048576` | 允許進入快取的最大完整檔案大小 |
| `traversal_mode` | str | `"backend"` | 遞迴 API 使用 backend 遍歷或 `cached_traversal` |
| `bypass_prefixes` | list[str] | `[]` | 強制繞過快取的路徑字首 |

`storage.agfs.pathlock` 控制 PathLock 儲存：

| 引數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `provider` | str | `"filesystem"` | `filesystem`、`memory` 或 `cache` |
| `namespace` | str 或 null | `null` | `provider=cache` 時必填的 OpenViking 例項名 |
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

- `CachedFileSystem`：實現檔案系統語義，包括 cache hit/miss、backend 回源、回填、失效、generation 校驗和指標。
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
ragfs:v1:{namespace}:file:{hash(path)}
```

檔案 value 是 `CacheEnvelope`，包含檔案內容、物件型別、路徑和 generation 快照。全量讀取命中後，RAGFS 會先校驗 envelope 和 generation，再返回內容。

預設策略會優先快取 `.abstract.md` 和 `.overview.md` 這類摘要檔案；超過 `max_file_size_bytes` 的檔案不會進入快取。非全量 range read 也會繞過快取。

### 目錄快取

目錄 key：

```text
ragfs:v1:{namespace}:dir:{hash(path)}
```

目錄快取儲存 backend 原始 `read_dir` entries，而不是許可權過濾後的最終結果。許可權、角色和 agent context 仍在 OpenViking 上層即時處理。

這樣同一份目錄快取可以服務 `ls`、`tree`、`glob`、`grep` 的檔案收集階段，以及刪除或移動前的路徑收集。

### 子樹 Generation

子樹 generation key：

```text
ragfs:v1:{namespace}:subtree:{hash(scope)}
```

`remove_all` 和目錄 `rename` 可能讓 Provider 中殘留子孫 key。RAGFS 通過 bump subtree generation，讓舊 envelope 的 generation 快照失效，後續真實讀取會回源並重建快取。

## 一致性與失效

單寫者場景下，RAGFS 不需要分散式寫鎖。關鍵是按檔案系統語義維護三類失效：

- 檔案變更：刪除或更新 `file_key(path)`，刪除 `dir_key(parent)`。
- 目錄變更：刪除目錄自身和父目錄的 `dir_key`。
- 子樹變更：對遞迴刪除和目錄 rename bump `subtree` generation。

典型寫入順序：

```text
獲取程序內操作鎖
-> 執行 backend 變更
-> 更新或刪除相關 cache key
-> 必要時 bump subtree generation
-> 返回結果
```

如果 Provider 失敗，RAGFS 會以 backend 為準，並讓受影響路徑進入短期 bypass，避免繼續讀取可能陳舊的快取。

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
- Provider 不可用：不返回舊快取，以 backend 結果為準。

建議重點觀察：

- cache hit / miss / bypass
- stale generation
- provider get / put / delete 延遲
- cache set / delete 失敗
- inflight leader / follower / backend saved
- backend fallback 位元組數

## 推薦使用順序

1. 關閉快取驗證 backend 基線行為。
2. 用內建 `redis` 驗證真實遠端快取收益。
3. 對高效能或閉源快取系統使用獨立釋出的 DynamicProvider `.so`。
4. 先快取摘要檔案和 raw `read_dir`，再擴充到更多普通小檔案。
5. 將鎖、控制面和許可權敏感路徑加入 `bypass_prefixes`。

一句話總結：RAGFS 快取負責“按檔案系統語義正確失效”，Provider 負責“把快取物件放在哪裡”。只要 backend 是事實來源，快取命中就必須先通過 envelope 和 generation 校驗。
