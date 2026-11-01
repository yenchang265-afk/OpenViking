# 多寫儲存指南

V2 多寫在 primary 成功後返回，metadata 和 backup 在後臺非同步更新。primary
是唯一直接讀取來源。

## 最小配置

```json
{
  "storage": {
    "workspace": "./data",
    "agfs": {
      "backend": "local",
      "backups": {
        "initial_partitions": 16,
        "checkpoint_interval_secs": 86400,
        "reconcile_existing_data": false,
        "provider": "filesystem",
        "items": [
          {
            "name": "local-backup",
            "backend": "local",
            "params": {
              "workspace": "./data/backup"
            }
          }
        ]
      }
    }
  }
}
```

V2 的頂層配置是：

| 欄位 | 預設值 | 含義 |
| --- | --- | --- |
| `initial_partitions` | `16` | 為 account 建立的 metadata partition 數量 |
| `checkpoint_interval_secs` | `86400` | Checkpoint 掃描間隔，最小值為 `60` |
| `reconcile_existing_data` | `false` | 掃描 primary 已存在檔案並寫入 V2 metadata |
| `provider` | `"filesystem"` | Metadata segment provider：`filesystem` 或 `cache` |

每個 `items[]` 需要 `name`、`backend` 和 backend 專用 `params`。
`encryption` 可選。backup 名稱必須唯一，且不能為 `primary`。

`provider` 為 `cache` 時，多寫複用頂層 CacheRuntime。實際實現由頂層
`cache.provider` 選擇；多寫沒有獨立 Cache Provider 連線配置。

Python 配置層仍接受 V1 的 sync、ack、retry、operations、excludes 和
redirects 欄位，輸出 warning 後會在呼叫 Rust 前刪除，欄位不生效。

## 執行行為

- primary 是唯一直接讀取來源和業務真相。
- primary 成功後立即返回，不等待 metadata 或 backup。
- 多寫 metadata 只儲存在 primary。
- backup 在後臺最終收斂。
- 不提供同步狀態或手工重試 API 和 CLI 命令。

程序可能在 primary 成功和事件持久化之間崩潰，導致一次複製事件丟失。此時
需要從 primary 重建受影響的 backup。

## Partition 數量

`initial_partitions` 僅在 account 的 partition manifest 首次建立時生效。
已有 account 在配置變化後繼續使用持久化的 partition 數量和 routes。
本期不支援擴容或縮容。

## 首次啟用與回滾

`.multiwrite.json` 不存在時，mount 先啟用前臺 V2 事件提交，並初始化 V2
metadata。若 `reconcile_existing_data=true`，啟動流程還會掃描 primary 當前檔案
並寫入 V2 metadata。該流程不會刪除 backup 中多餘的舊檔案。

預設 `reconcile_existing_data=false` 時，primary 上啟用前已存在的檔案不會作為
V2 write event 記錄。只有在 backup 已與 primary 對齊，或明確跳過歷史回填時
才保持預設值。

舊多寫協議和舊遷移欄位直接拒絕。啟用多寫前必須建立完整備份；回滾二進位制
前必須先恢復該備份。

## 驗證

使用普通檔案 API 驗證 primary 讀寫。使用[指標](../concepts/12-metrics.md)
監控佇列深度、worker 失敗、backup lag、協議版本和協議狀態。

## 相關文件

- [多寫儲存](../concepts/14-multi-write-storage.md)
- [配置指南](./01-configuration.md)
- [OVPack 匯入匯出](./09-ovpack.md)
