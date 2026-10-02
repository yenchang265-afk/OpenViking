# 多寫儲存指南

本指南介紹如何配置 OpenViking 的多寫儲存能力。多寫儲存允許一個 primary 後端同時複製寫入多個 backup 後端，用於高可用、跨區域副本、讀加速和儲存遷移。

多寫能力位於 RAGFS 內部。OpenViking 的 Python SDK、HTTP API 和 CLI 使用方式保持不變。

## 前置條件

- 已有可用的 `ov.conf`。
- 已確認 primary backend 可以正常讀寫。
- 如果要接入 S3 相容儲存，已準備好 bucket、endpoint 和訪問憑據。
- 如需遷移已有資料，請遵循 [OVPack 多寫遷移流程](./09-ovpack.md#與多寫儲存配合)；僅啟用 backups 不會複製歷史檔案。

## 最小配置

下面示例使用本地目錄作為 primary，並把寫入複製到另一個本地目錄。

```json
{
  "storage": {
    "workspace": "./data",
    "agfs": {
      "backend": "local",
      "backups": {
        "sync_type": "async",
        "items": [
          {
            "name": "local-backup",
            "backend": "local",
            "local": {
                "workspace": "./data/backup"
            }
          }
        ]
      }
    }
  }
}
```

說明：

- 頂層 `backend` 是 primary。
- `backups.items[]` 是 backup 列表。
- `name` 是 backup 的穩定身份，後續同步後設資料會引用它。
- `backend = "local"` 的 backup 使用 `local.workspace` 指定本地目錄。
- `sync_type` 不配置時預設按非同步模式理解。

## 多 Backup 配置

可以配置多個 backup。下面示例同時寫入本地副本和 S3 相容物件儲存。

```json
{
  "storage": {
    "workspace": "./data",
    "agfs": {
      "backend": "local",
      "backups": {
        "sync_type": "async",
        "items": [
          {
            "name": "local-az2",
            "backend": "local",
            "local": {
                "workspace": "./data/local-az2"
            }
          },
          {
            "name": "object-store",
            "backend": "s3",
            "s3": {
              "bucket": "openviking-backup",
              "region": "us-east-1",
              "endpoint": "https://s3.example.com",
              "access_key": "your-access-key",
              "secret_key": "your-secret-key",
              "prefix": "openviking",
              "directory_marker_mode": "none"
            }
          }
        ]
      }
    }
  }
}
```

建議：

- `name` 不要使用會頻繁變化的機器名或臨時編號。
- backup 的底層路徑或 bucket 應避免與 primary 指向同一物理位置。
- 修改 backup `name` 會影響歷史同步後設資料的識別，生產環境應謹慎變更。

### S3 相容儲存注意事項

使用 S3 相容服務（MinIO、RustFS、Ceph 等）時，`s3` 段需要額外配置以下欄位：

| 欄位 | 是否必填 | 說明 |
| --- | --- | --- |
| `use_path_style` | 大多數 S3 相容服務必填 | 設定為 `true` 使用路徑風格 URL（`http://host/bucket/key`）。大多數 S3 相容服務需要此配置。 |
| `directory_marker_mode` | S3 相容服務必填 | **必須顯式設定為 `"none"`**。如果不配置，RAGFS Rust binding 啟動時會報 `AGFSConfigError: invalid directory_marker_mode: null` 並靜默崩潰。 |
| `use_ssl` | 可選 | HTTP 端點（如 `http://localhost:9000`）需要設定為 `false`。 |

**S3 相容儲存最小示例（RustFS/MinIO）：**

```json
{
  "name": "s3-backup",
  "backend": "s3",
  "s3": {
    "bucket": "my-bucket",
    "endpoint": "http://localhost:9000",
    "access_key": "your-access-key",
    "secret_key": "your-secret-key",
    "prefix": "openviking",
    "use_ssl": false,
    "use_path_style": true,
    "directory_marker_mode": "none"
  }
}
```

> **為什麼需要 `directory_marker_mode`？**
>
> S3 相容儲存服務對"目錄"的處理方式與 AWS S3 不同。RAGFS Rust binding 必須知道建立目錄時是否需要寫入目錄標記物件。合法取值為 `"none"`、`"empty"` 和 `"nonempty"`。對於不使用目錄標記的 S3 相容服務（RustFS、MinIO、Ceph 等），設定為 `"none"`。如果省略，Rust binding 預設值為 `null`（不合法），導致服務端在啟動時靜默崩潰，報錯 `AGFSConfigError: invalid directory_marker_mode: null`。

### Docker 網路配置

在 Docker 中執行 OpenViking 並配置同主機的 S3 備份時，需要注意：

- **Linux Docker**：使用 `--network host` 或宿主機區域網 IP。Docker bridge 網路可通過閘道器 IP（如 `172.17.0.1:9000`）訪問宿主機區域網。
- **macOS/Windows Docker Desktop**：`--network host` **不支援**。S3 端點使用 `host.docker.internal`（對映為宿主機的 localhost），或使用宿主機區域網 IP。

如果啟用 S3 備份後服務靜默崩潰，請優先排查 Docker 網路。RAGFS Rust binding 在容器內無法訪問 S3 端點時會報 `dispatch failure` 錯誤。

## 同步模式選擇

### 非同步模式

非同步模式適合大多數場景。

```json
{
  "backups": {
    "sync_type": "async",
    "items": []
  }
}
```

特點：

- primary 寫入成功後立即返回。
- backup 寫入在後臺執行。
- 寫入延遲低。
- backup 可能短暫落後。

適合：

- 寫入吞吐優先。
- backup 主要用於災備。
- 可以接受最終一致性。

### 同步模式

同步模式會等待 backup 確認。

```json
{
  "backups": {
    "sync_type": "sync",
    "write_ack_count": 1,
    "write_ack_timeout_ms": 5000,
    "items": []
  }
}
```

引數說明：

| 引數 | 說明 |
| --- | --- |
| `write_ack_count` | 寫入返回前至少需要多少個 backup 確認 |
| `write_ack_timeout_ms` | 等待 backup 確認的超時時間，單位毫秒 |

特點：

- 寫入確認更強。
- 寫入延遲受 backup 影響。
- 未確認的 backup 會繼續由後臺重試修復。
- primary 已寫成功但 backup 未達確認數時，客戶端可能收到錯誤；此時 primary 中可能已經存在資料。

適合：

- 希望儘量減少 primary 與 backup 的確認視窗。
- backup 延遲可控。
- 呼叫方能接受同步寫入帶來的額外延遲。

## 配置讀加速

backup 預設不參與讀取。要讓 backup 服務讀取，需要顯式配置 `operations`。

```json
{
  "name": "cache-backend",
  "backend": "memfs",
  "operations": [
    {
      "operation": "read",
      "priority": 10
    }
  ]
}
```

讀取優先順序規則：

- `priority` 越小越優先。
- 只有宣告 `read` 的 backup 才參與讀取。
- primary 始終作為最終兜底。
- 冷備 backup 不建議配置讀能力。

如果一個 backup 只配置了 `read`，沒有配置 `write`，它不會接收普通多寫複製。只有在你明確知道該 backend 的資料來源時，才應使用這種配置。

## Redirect 配置

Redirect 用於把匹配的檔案寫入指定 backup，而不是寫入 primary。

按副檔名重定向：

```json
{
  "storage": {
    "agfs": {
      "backend": "local",
      "redirects": [
        {
          "type": "FileExtensionPolicy",
          "extensions": ["(pdf|ppt|zip)"],
          "target": ["object-store"]
        }
      ],
      "backups": {
        "items": [
          {
            "name": "object-store",
            "backend": "s3",
            "s3": {
              "bucket": "openviking-large-files",
              "endpoint": "https://s3.example.com"
            }
          }
        ]
      }
    }
  }
}
```

按大小重定向：

```json
{
  "type": "FileOverSizePolicy",
  "max_size_mb": 100,
  "target": ["object-store"]
}
```

注意：

- `target` 必須引用已有 backup 的 `name`。
- redirect 檔案仍會通過普通 API 呈現為可讀、可列舉、可查詢狀態。
- redirect 對映儲存在 primary 的內部後設資料中。

## Exclude 配置

Exclude 用於讓某個 backup 跳過匹配檔案。

```json
{
  "name": "cache-backend",
  "backend": "memfs",
  "excludes": [
    {
      "type": "FileOverSizePolicy",
      "max_size_mb": 50
    },
    {
      "type": "FileExtensionPolicy",
      "extensions": ["(mp4|zip)"]
    }
  ]
}
```

常見用法：

- 快取 backend 排除大檔案。
- 低成本備份排除無需儲存的檔案型別。
- 某個 backup 只儲存文本或配置類資源。

如果 redirect 的目標 backup 同時 exclude 了該檔案，說明配置互相沖突。請優先修正配置，不要依賴系統自動猜測其他目標。

## 加密配置

多寫儲存複用 OpenViking 的透明靜態加密能力。

全域加密開啟示例：

```json
{
  "encryption": {
    "enabled": true,
    "provider": "local",
    "local": {
      "key_file": "~/.openviking/master.key"
    }
  },
  "storage": {
    "workspace": "./data",
    "agfs": {
      "backend": "local",
      "backups": {
        "items": [
          {
            "name": "plain-cache",
            "backend": "memfs",
            "encryption": {
              "enabled": false
            }
          },
          {
            "name": "encrypted-backup",
            "backend": "local",
            "local": {
                "workspace": "./data/encrypted-backup"
            },
            "encryption": {
              "enabled": true
            }
          }
        ]
      }
    }
  }
}
```

規則：

- 全域 `encryption.enabled=true` 時，primary 必須加密。
- backup 可以通過 `encryption.enabled` 單獨控制是否加密。
- Python SDK、HTTP API 和 CLI 不需要處理加解密。
- `.redirect.json` 和 `.sync_log.json` 等內部後設資料會跟隨 primary 加密策略。

## 存量資料遷移

多寫只複製啟用之後的新寫入，不會自動複製歷史檔案。

使用 OVPack 遷移時，請遵循 [與多寫儲存配合](./09-ovpack.md#與多寫儲存配合)：先在乾淨目標配置多寫，再通過該服務恢復，驗證各副本後恢復業務寫入。目標 account 初始化和恢復衝突處理也在該流程中說明。

## 驗證配置

啟動前建議執行：

```bash
openviking-server doctor
```

啟動後可以用普通檔案 API 驗證：

```bash
openviking write viking://resources/multiwrite-check.txt \
  --content "multi-write check"

openviking read viking://resources/multiwrite-check.txt
```

如果使用本地 backup，可以直接檢查 backup 目錄中是否出現對應檔案。生產環境更推薦使用系統健康檢查和同步狀態命令。

## 常見問題

### 為什麼 backup 沒有參與讀取？

backup 預設只參與寫入，不參與讀取。需要在 backup 上顯式配置：

```json
{
  "operations": [
    {
      "operation": "read",
      "priority": 10
    }
  ]
}
```

### 為什麼啟用多寫後歷史檔案沒有出現在 backup？

多寫只處理啟用後的新寫入。歷史檔案請按 [OVPack 遷移流程](./09-ovpack.md#與多寫儲存配合) 處理；啟用 backups 不會自動補齊。

### 非同步模式下能否保證立即讀到 backup 的最新資料？

不能。非同步模式只保證最終一致。需要強讀一致時，應讓讀取回退到 primary，或避免讓可能滯後的 backup 參與讀路由。

### 內部後設資料檔案會出現在使用者列表裡嗎？

不會。`.redirect.json` 和 `.sync_log.json` 是內部檔案，會被普通目錄列表隱藏。

### sync 模式返回失敗是否表示 primary 一定沒寫入？

不是。primary 寫成功但 backup 未達到確認數時，客戶端可能收到失敗。此時 primary 資料可能已經存在，落後的 backup 會由後臺重試修復。

## 相關文件

- [多寫儲存](../concepts/14-multi-write-storage.md)
- [儲存架構](../concepts/05-storage.md)
- [配置指南](./01-configuration.md)
- [加密指南](./08-encryption.md)
- [OVPack 匯入匯出](./09-ovpack.md)
