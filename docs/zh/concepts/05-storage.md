# 儲存架構

OpenViking 採用雙層儲存架構，分離內容儲存和索引儲存。

## 概覽

```
┌─────────────────────────────────────────┐
│            VikingFS (URI 抽象層)         │
│            URI 對映 · 層級訪問           │
└────────────────┬────────────────────────┘
        ┌────────┴────────┐
        │                 │
┌───────▼────────┐  ┌─────▼───────────┐
│   向量庫索引    │  │      AGFS       │
│   (語義搜尋)    │  │   (內容儲存)    │
└────────────────┘  └─────────────────┘
```

## 雙層儲存

| 儲存層 | 職責 | 儲存內容 |
|--------|------|----------|
| **AGFS** | 內容儲存 | L0/L1/L2 完整內容、多媒體檔案 |
| **向量庫** | 索引儲存 | URI、向量、後設資料（不存檔案內容） |

### 設計優勢

1. **職責清晰**：向量庫只負責檢索，AGFS 負責儲存
2. **記憶體最佳化**：向量庫不儲存檔案內容，節省記憶體
3. **單一資料來源**：所有內容從 AGFS 讀取，向量庫只存引用
4. **獨立擴充**：向量庫和 AGFS 可分別擴充
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

### 單後端與多寫模式

預設情況下，AGFS 使用一個後端作為內容儲存。配置 `storage.agfs.backups` 後，OpenViking 會啟用多寫模式：

- 頂層 `storage.agfs.backend` 是 primary，作為權威寫入目標。
- `storage.agfs.backups.items[]` 是 backup，用於副本、遷移或讀加速。
- Python SDK、HTTP API 和 CLI 的檔案系統介面保持不變。
- 多寫內部使用 `.redirect.json` 和 `.sync_log.json` 維護 redirect 對映與同步進度，這些檔案對使用者不可見。

更多概念說明見 [多寫儲存](./14-multi-write-storage.md)，配置示例見 [多寫儲存指南](../guides/13-multi-write-storage.md)。

### 後端型別

| 後端 | 說明 | 配置 |
|------|------|------|
| `localfs` | 本地檔案系統 | `path` |
| `s3fs` | S3 相容儲存 | `bucket`, `endpoint` |
| `memory` | 記憶體儲存（測試用） | - |

### 目錄結構

每個上下文目錄遵循統一結構：

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
| `volcengine` | 火山引擎 VikingDB |

## 向量同步

VikingFS 自動維護向量庫與 AGFS 的一致性。

### 刪除同步

```python
viking_fs.rm("viking://resources/docs/auth", recursive=True)
# 自動遞迴刪除向量庫中所有 uri 以此開頭的記錄
```

### 移動同步

```python
viking_fs.mv(
    "viking://resources/docs/auth",
    "viking://resources/docs/authentication"
)
# 自動更新向量庫中的 uri 和 parent_uri 欄位
```

## 相關文件

- [架構概述](./01-architecture.md) - 系統整體架構
- [上下文層級](./03-context-layers.md) - L0/L1/L2 模型
- [Viking URI](./04-viking-uri.md) - URI 規範
- [多寫儲存](./14-multi-write-storage.md) - primary/backup、多寫路由與一致性
- [檢索機制](./07-retrieval.md) - 檢索流程詳解
