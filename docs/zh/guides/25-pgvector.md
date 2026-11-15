# PostgreSQL + pgvector

設定 `storage.vectordb.backend="pgvector"` 後，collection 後設資料、dense 向量、
標量欄位和 sparse 倒排記錄儲存在 PostgreSQL 中。OpenViking 通過有連線數上限的
psycopg2 連線池訪問資料庫，向量檢索在 PostgreSQL 程序內執行。
Embedding 仍由配置的模型提供方生成。

## 安裝與配置

安裝客戶端可選依賴：

```bash
pip install 'openviking[pgvector]'
```

在 PostgreSQL 服務端安裝 **0.8.0 或更新版本**的 pgvector，然後在 OpenViking
使用的資料庫內啟用擴充套件：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
SELECT extversion FROM pg_extension WHERE extname = 'vector';
```

擴充套件需安裝在 `public` schema。連線帳號需要訪問該 schema、建立 collection
表和索引、讀寫資料的許可權。併發初始化通過 PostgreSQL advisory lock 序列化。
後設資料使用 `_ov_collection_meta` 和 `_ov_index_<collection>` 表。
獨立部署應使用不同資料庫或 collection 名稱，不能複用 openGauss collection 的名稱。

在服務端環境變數中設定 DSN；可按 PostgreSQL DSN 規範配置 `sslmode`、
`sslrootcert` 等連線引數：

```bash
export OV_POSTGRES_DSN='host=127.0.0.1 port=5432 dbname=openviking user=ov password=CHANGE_ME'
```

將下面片段合併到現有配置，向量維度需與 embedding 模型輸出一致：

```json
{
  "storage": {
    "vectordb": {
      "backend": "pgvector",
      "name": "context",
      "dimension": 4096,
      "distance_metric": "cosine",
      "pgvector": {
        "dsn_env": "OV_POSTGRES_DSN",
        "index_type": "flat",
        "connection_pool_min_size": 1,
        "connection_pool_max_size": 10
      }
    }
  }
}
```

這是 Cluster 級後端配置；Account 獨立 `vectordb` 配置目前僅接受
`http`。

## 檢索和索引引數

| `pgvector` 引數 | 預設值 | 說明 |
| --- | --- | --- |
| `dsn_env` | `OV_POSTGRES_DSN` | 儲存連線 DSN 的環境變數名稱 |
| `index_type` | `flat` | 精確 dense 檢索，或原生 `hnsw` ANN |
| `connection_pool_min_size` | `1` | 每個 adapter 的最小連線數 |
| `connection_pool_max_size` | `10` | 每個 adapter 的最大連線數，不能小於最小值 |
| `m` | `16` | HNSW 每層連線數，範圍 2–100 |
| `ef_construction` | `64` | HNSW 構建候選列表，範圍 4–1000，至少是 `m` 的兩倍 |
| `ef_search` | `100` | HNSW 檢索候選列表，範圍 1–1000 |
| `candidate_limit` | `1000` | sparse/hybrid 或時間衰減排序中每路候選預算，範圍 1–10000 |

Dense 使用全精度 `vector` 型別，支援 1–16000 維；該型別的原生 HNSW
最多支援 **2000 維**。4096 維模型需使用 `index_type="flat"`，不會自動截斷
或量化 embedding。當前未實現 `halfvec`、二進位制量化和 IVFFlat。

不超過 2000 維的模型可選擇：

```json
{
  "dsn_env": "OV_POSTGRES_DSN",
  "index_type": "hnsw",
  "m": 16,
  "ef_construction": 64,
  "ef_search": 100
}
```

`distance_metric` 支援 `cosine`、`l2`、`ip`、`l1`，結果遵循 OpenViking
分數越高排名越靠前的約定。標量、租戶、ACL 和 URI 範圍過濾轉換為引數化 SQL。
HNSW 開啟 strict iterative scanning 來改善帶過濾的召回，但不保證 ANN
召回率或過濾後 TopK 數量；需用真實過濾條件驗證召回率和 p99。
pgvector HNSW 的 cosine 索引不包含零向量。

即使表中額外存在 ANN 索引，flat 檢索仍保持精確。重新連線時會校驗配置與
持久化後設資料中的維度、距離和索引型別，ANN 索引缺失或無效會明確報錯。
修改 `ef_search` 在重新連線後生效，不需要重建索引；修改索引型別或構建引數
需要安排索引/collection 重建。

Sparse term 以 JSONB 和倒排表儲存。Sparse-only 只召回有正向 term overlap
的記錄；hybrid 合併有限 dense/sparse 候選，在候選並集中補齊分數後排序，
不保證全域融合 TopK。`sparse_weight` 與 embedding 配置仍沿用既有語義。

## 目錄過濾調優

大規模 collection 的歸一化 URI 範圍過濾可評估租戶與路徑的 B-tree
複合表示式索引。索引 SQL、level/depth 語義、百萬行實測和部署邊界見
[pgvector 目錄過濾索引最佳化](26-pgvector-directory-filtering.md)。
該索引目前需要手工評估和部署，後端不會自動建立。

## 資料與部署邊界

批次 upsert 和 sparse 倒排更新在同一事務中完成，失敗時整批迴滾。
資料與索引後設資料在服務重啟後保留。配置 PostgreSQL 複製、備份和 PITR 後，
這些資料庫記錄可獲得相應的保護。

當前不支援 TTL 寫入和原生 BM25/full-text 檢索。`content` 欄位儲存在
PostgreSQL 中（服務寫入鏈路仍沿用現有的 1 MB content payload 限制），
grep 沿用檔案系統回退。初始化會執行 collection DDL；
當前不提供自動 schema 遷移或損壞索引自動修復。

修改 backend 配置不會匯入原有 local 向量。需要建立新 collection 並重新索引
資源，或單獨執行經過核驗的遷移；在完成核驗前保留舊向量庫。

資原始檔、佇列、Account/Task 儲存和 PathLock 各自獨立配置。僅共享 pgvector
不能讓本地 workspace 安全地供多個 OpenViking 程序使用。
共享儲存和協調配置請參考[部署指南](03-deployment.md)；
PostgreSQL PathLock 是獨立功能。

## 整合測試

測試使用隨機 collection 名稱，完成後刪除測試資料。請使用啟用了 pgvector 的
測試資料庫：

```bash
export OV_PGVECTOR_TEST_DSN='host=127.0.0.1 port=5432 dbname=ov_test user=ov'
pytest tests/storage/test_pgvector_adapter.py
```
