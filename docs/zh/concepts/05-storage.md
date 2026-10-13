# 儲存架構

OpenViking 採用雙層儲存架構，分離內容儲存和索引儲存。

## 概覽

<StorageLayersDiagram />

## 雙層儲存

| 儲存層 | 職責 | 儲存內容 |
|--------|------|----------|
| **AGFS** | 內容儲存 | L0/L1/L2 完整內容、多媒體檔案 |
| **向量庫** | 索引儲存 | URI、向量、後設資料和摘要等檢索文本 |

### 設計優勢

AGFS 儲存原始檔，向量庫儲存檢索需要的 URI 引用、向量、後設資料和摘要。記憶記錄會把正文儲存在向量記錄的 abstract 欄位（上限 50,000 位元組），因此向量庫中也可能包含可讀文本。

兩類後端可以分別配置。檔案 API 從 AGFS 讀取內容，檢索則可直接返回索引中的文本，無需逐個回讀原始檔。備份和訪問控制需要覆蓋兩類儲存。

> 注：AGFS 已經重寫為 Rust 實現（RAGFS）

## VikingFS 虛擬檔案系統

VikingFS 是統一的 URI 抽象層，遮蔽底層儲存細節。

### URI 映射

```
viking://resources/docs/auth  →  /local/{account_id}/resources/docs/auth
viking://~/memories        →  /local/{account_id}/user/{user_id}/memories
viking://~/skills          →  /local/{account_id}/user/{user_id}/skills
```

### 核心 API

| 方法 | 說明 |
|------|------|
| `read(uri)` | 讀取檔案內容 |
| `write(uri, data)` | 寫入檔案 |
| `mkdir(uri)` | 建立目錄 |
| `rm(uri)` | 刪除檔案/目錄（同步刪除向量） |
| `mv(old, new)` | 移動/重新命名（同步更新向量 URI） |
| `abstract(uri)` | 讀取 L0 摘要 |
| `overview(uri)` | 讀取 L1 概覽 |
| `find(query, uri)` | 語義搜尋 |

## AGFS 底層儲存

AGFS 提供 POSIX 風格的檔案操作，支援多種後端。

### 單後端與主備模式

預設情況下，AGFS 使用一個後端作為內容儲存。配置 `storage.agfs.backups` 後，OpenViking 會啟用主備模式：

- 頂層 `storage.agfs.backend` 是 primary，也是唯一直接讀取來源。
- `storage.agfs.backups.items[]` 是後臺非同步更新的 backup。
- Python SDK、HTTP API 和 CLI 的檔案系統介面保持不變。
- V2 metadata 分割槽儲存，並且只儲存在 primary。

更多概念說明見 [主備儲存](./14-multi-write-storage.md)，配置示例見 [主備儲存指南](../guides/13-multi-write-storage.md)。

### 後端型別

| 後端 | 說明 | 配置 |
|------|------|------|
| `localfs` | 本地檔案系統 | `path` |
| `s3fs` | S3 相容儲存 | `bucket`, `endpoint` |
| `memory` | 記憶體儲存（測試用） | - |

### 目錄結構

完成語義處理的目錄通常有以下結構。處理前或僅建立 L0 時，部分摘要檔案可能尚不存在：

```
viking://resources/docs/auth/
├── .abstract.md          # L0 摘要
├── .overview.md          # L1 概覽
└── *.md                  # L2 詳細內容
```

## 向量庫索引

向量庫儲存語義索引，支援向量搜尋和標量過濾。

### 本地記錄格式相容

本地後端將非向量欄位打包成 JSON。新寫入的當前記錄和 Delta 日誌使用帶 32 位位元組長度的
`text` 儲存這份 JSON，解除原先整個 JSON 合計 65,535 位元組的限制，不截斷內容。

新記錄帶有格式版本。已有的無版本記錄繼續可讀，更新時寫入新格式；本次格式升級不需要
全庫重寫、重建索引或重新計算 embedding。Delta 恢復也支援新舊格式混存。

相容方向為新版讀取舊資料：舊版程式無法讀取新格式。需要降級時，應恢復首次寫入新格式
之前的備份，不能只替換回舊版程式。

### Context 集合 Schema

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | string | 主鍵 |
| `uri` | string | 資源 URI |
| `parent_uri` | string | 父目錄 URI |
| `context_type` | string | resource/memory/skill |
| `is_leaf` | bool | 是否葉子節點 |
| `vector` | vector | 密集向量 |
| `sparse_vector` | sparse_vector | 稀疏向量 |
| `abstract` | string | L0 摘要文本 |
| `name` | string | 名稱 |
| `description` | string | 描述 |
| `created_at` | string | 建立時間 |
| `active_count` | int64 | 使用次數 |

### 索引策略

以下為索引後設資料示例；可用選項取決於向量後端：

```python
index_meta = {
    "IndexType": "flat_hybrid",  # 混合索引
    "Distance": "cosine",        # 餘弦距離
    "Quant": "int8",             # 量化方式
}
```

### 後端支援

| 後端 | 說明 |
|------|------|
| `local` | 本地持久化 |
| `http` | HTTP 遠端服務 |
| `cuvs` | 本地持久化 + NVIDIA cuVS dense search |
| `opengauss` | openGauss DataVec |
| `elasticsearch` | Elasticsearch 8.x dense_vector kNN |

## 向量同步

檔案系統操作協調檔案與向量記錄的變更。目錄摘要可能繼續非同步重新整理，失敗也可能留下部分變更；各操作的具體行為見[檔案系統 API](../api/03-filesystem.md)。下面的示例使用已初始化的同步 Python SDK 客戶端。

### 刪除同步

```python
client.rm("viking://resources/docs/auth", recursive=True)
# 自動遞迴刪除向量庫中所有 uri 以此開頭的記錄
```

### 移動同步

```python
client.mv(
    "viking://resources/docs/auth",
    "viking://resources/docs/authentication"
)
# 自動更新向量庫中的 uri 和 parent_uri 欄位
```

## 相關文件

- [架構概述](./01-architecture.md) - 系統整體架構
- [上下文層級](./03-context-layers.md) - L0/L1/L2 模型
- [Viking URI](./04-viking-uri.md) - URI 規範
- [多寫儲存](./14-multi-write-storage.md) - V2 primary 與 backup 一致性
- [檢索機制](./07-retrieval.md) - 檢索流程詳解
