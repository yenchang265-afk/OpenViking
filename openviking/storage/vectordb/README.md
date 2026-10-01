# VikingVectorIndex

OpenViking 專案的高效能向量資料庫模組，專為 AI Agent 場景設計，提供向量儲存、檢索和聚合分析能力。

## 特性

- **混合向量檢索**：支援密集向量（Dense）和稀疏向量（Sparse）的混合搜尋
- **多模態支援**：支援文本、影像、影片的向量化和檢索
- **豐富的搜尋方式**：向量搜尋、ID搜尋、標量搜尋、隨機搜尋、關鍵詞搜尋
- **資料聚合分析**：支援總計數、分組計數、過濾聚合等分析操作
- **靈活的儲存模式**：支援記憶體模式（Volatile）和持久化模式（Persistent）
- **TTL 自動過期**：支援資料生存時間管理，自動清理過期資料
- **索引自動重建**：後臺任務自動檢測和重建索引
- **高效能**：核心引擎基於 C++ 實現，使用 Python abi3 擴充繫結
- **執行緒安全**：關鍵資料結構支援併發訪問

## 架構原理

### 整體架構

VikingVectorIndex 採用分層架構設計：

```
Application Layer (使用者程式碼/API)
         ↓
Collection Layer (集合管理、資料操作、索引協調)
         ↓
   ┌─────┴─────┐
   ↓           ↓
Index Layer  Storage Layer
(向量檢索)    (三表儲存)
   ↓           ↓
C++ Engine (abi3 繫結)
```

### 三表儲存模型

VikingVectorIndex 使用三張表分離不同職責：

**C 表 (Candidate Table)**
- 儲存最新的向量和標量資料
- Key: `label` (uint64)
- Value: 向量 + 欄位 + 過期時間

**D 表 (Delta Table)**
- 記錄資料變更歷史 (PUT/DELETE)
- 用於索引增量更新和崩潰恢復
- Key: `timestamp_label`
- 定期清理：保留最舊索引版本之後的記錄

**T 表 (TTL Table)**
- 按過期時間排序，加速 TTL 清理
- Key: `expire_timestamp_label`
- 後臺任務定期掃描並刪除過期資料

### 索引機制

**VolatileIndex (記憶體索引)**
- 資料全部在記憶體，重啟後丟失
- 支援增量更新，定期重建壓縮空間
- 適合：測試環境、臨時資料

**PersistentIndex (持久化索引)**
- 多版本快照機制，每次持久化建立新版本目錄
- 崩潰恢復：載入最新版本 + 應用增量更新
- 後臺定期持久化和清理舊版本

版本目錄結構：
```
versions/
  1704067200000000000/           # 版本快照
  1704067200000000000.write_done # 完成標記
```

### 核心資料流

**插入流程**：
```
使用者資料 → 驗證 → 生成label → 向量化
  ↓
寫入C/D/T表 → 通知所有索引更新
  ↓
C++引擎更新向量索引和標量索引
```

**搜索流程**：
```
查詢向量 → 索引檢索 + 標量過濾
  ↓
返回labels和scores → 從C表批次獲取完整資料
  ↓
構造SearchResult返回
```

### 效能最佳化

- **批次操作**：減少 I/O 次數
- **增量更新**：避免全量重建索引
- **C++ 加速**：向量計算使用 SIMD 最佳化
- **多版本快照**：寫入不阻塞讀取
- **延遲清理**：批量回收空間

## 快速開始

### 完整示例：從零開始

```python
from openviking.storage.vectordb.collection.local_collection import get_or_create_local_collection
import random

# Step 1: 定義集合後設資料
collection_meta_data = {
    "CollectionName": "demo_collection",
    "Fields": [
        {"FieldName": "id", "FieldType": "int64", "IsPrimaryKey": True},
        {"FieldName": "embedding", "FieldType": "vector", "Dim": 128},
        {"FieldName": "text", "FieldType": "text"},
        {"FieldName": "category", "FieldType": "text"},
        {"FieldName": "score", "FieldType": "float32"},
        {"FieldName": "priority", "FieldType": "int64"},
    ],
}

# Step 2: 建立集合（記憶體模式）
collection = get_or_create_local_collection(meta_data=collection_meta_data)
# 或建立持久化模式
# collection = get_or_create_local_collection(meta_data=collection_meta_data, path="./demo_db/")

# Step 3: 準備測試資料
data_list = []
categories = ["tech", "science", "art", "sports", "music"]
for i in range(1, 101):
    data_list.append({
        "id": i,
        "embedding": [random.random() for _ in range(128)],
        "text": f"This is document number {i}",
        "category": categories[i % 5],
        "score": round(random.uniform(0.5, 1.0), 2),
        "priority": random.randint(1, 10)
    })

# Step 4: 插入資料
result = collection.upsert_data(data_list)
print(f"Successfully inserted {len(result.ids)} documents")

# Step 5: 建立索引
index_meta_data = {
    "IndexName": "demo_index",
    "VectorIndex": {
        "IndexType": "flat",
        "Distance": "ip"
    },
    "ScalarIndex": ["category", "priority"],
}
collection.create_index("demo_index", index_meta_data)
print("Index created successfully")

# Step 6: 向量搜索
query_vector = [random.random() for _ in range(128)]
search_result = collection.search_by_vector(
    index_name="demo_index",
    dense_vector=query_vector,
    limit=5
)

print("\n=== Search Results ===")
for item in search_result.data:
    print(f"ID: {item.id}, Score: {item.score:.4f}")

# Step 7: 帶過濾條件的搜尋
search_result = collection.search_by_vector(
    index_name="demo_index",
    dense_vector=query_vector,
    limit=5,
    filters={"op": "must", "field": "category", "conds": ["tech", "science"]},
    output_fields=["text", "category", "score"]
)

print("\n=== Filtered Search Results (tech or science) ===")
for item in search_result.data:
    print(f"ID: {item.id}, Category: {item.fields.get('category')}, "
          f"Score: {item.score:.4f}, Text: {item.fields.get('text')}")

# Step 8: 清理資源
collection.close()
```

## Collection API 詳細用例

### 1. 建立和管理集合

#### 1.1 建立記憶體集合

```python
from openviking.storage.vectordb.collection.local_collection import get_or_create_local_collection

# 定義集合後設資料
meta_data = {
    "CollectionName": "my_collection",
    "Fields": [
        {"FieldName": "id", "FieldType": "int64", "IsPrimaryKey": True},
        {"FieldName": "vector", "FieldType": "vector", "Dim": 128},
        {"FieldName": "text", "FieldType": "text"},
    ],
}

# 建立記憶體集合（程序結束後資料丟失）
collection = get_or_create_local_collection(meta_data=meta_data)
print(f"Collection '{collection.get_meta_data()['CollectionName']}' created in memory")
```

#### 1.2 建立持久化集合

```python
import os

# 建立持久化集合
persist_path = "./vectordb_data/my_persistent_collection"
os.makedirs(persist_path, exist_ok=True)

collection = get_or_create_local_collection(
    meta_data=meta_data,
    path=persist_path
)
print(f"Persistent collection created at: {persist_path}")

# 關閉集合
collection.close()

# 重新開啟集合（資料自動恢復）
collection = get_or_create_local_collection(path=persist_path)
print("Collection reopened with all data restored")
```

#### 1.3 配置 TTL 和索引維護間隔

```python
# 自定義 TTL 清理和索引維護間隔
config = {
    "ttl_cleanup_seconds": 10,        # TTL 清理間隔 10 秒
    "index_maintenance_seconds": 60   # 索引維護間隔 60 秒
}

collection = get_or_create_local_collection(
    meta_data=meta_data,
    path="./vectordb_data/",
    config=config
)
print(f"Collection created with custom config: TTL cleanup every {config['ttl_cleanup_seconds']}s")
```

#### 1.4 更新集合後設資料

```python
# 添加新字段
collection.update(
    fields=[
        {
            "FieldName": "timestamp",
            "FieldType": "int64",
            "DefaultValue": 0
        },
        {
            "FieldName": "tags",
            "FieldType": "text",
            "DefaultValue": ""
        }
    ]
)

# 驗證新欄位
meta = collection.get_meta_data()
print(f"Collection now has {len(meta['Fields'])} fields")
for field in meta['Fields']:
    print(f"  - {field['FieldName']}: {field['FieldType']}")
```

### 2. 資料操作

#### 2.1 插入/更新資料（Upsert）

```python
import time

# 準備資料
data_list = [
    {
        "id": 1,
        "vector": [0.1] * 128,
        "text": "First document",
        "timestamp": int(time.time()),
        "tags": "important"
    },
    {
        "id": 2,
        "vector": [0.2] * 128,
        "text": "Second document",
        "timestamp": int(time.time()),
        "tags": "review"
    },
    {
        "id": 3,
        "vector": [0.3] * 128,
        "text": "Third document",
        "timestamp": int(time.time()),
        "tags": "archive"
    }
]

# 插入資料
result = collection.upsert_data(data_list)
print(f"Inserted IDs: {result.ids}")

# 更新資料（相同 ID）
update_data = [
    {
        "id": 1,
        "vector": [0.15] * 128,
        "text": "Updated first document",
        "timestamp": int(time.time()),
        "tags": "updated"
    }
]
result = collection.upsert_data(update_data)
print(f"Updated IDs: {result.ids}")
```

#### 2.2 插入帶 TTL 的資料

```python
import time

# 插入 5 秒後過期的資料
ttl_data = [
    {
        "id": 100,
        "vector": [1.0] * 128,
        "text": "Temporary document",
        "timestamp": int(time.time()),
        "tags": "temp"
    }
]

result = collection.upsert_data(ttl_data, ttl=5)
print(f"Inserted temporary data with ID: {result.ids}")

# 立即獲取資料（成功）
fetch_result = collection.fetch_data([100])
print(f"Immediately fetched: {len(fetch_result.items)} items")

# 等待 TTL 過期
print("Waiting 10 seconds for TTL expiration...")
time.sleep(10)

# 再次獲取（失敗）
fetch_result = collection.fetch_data([100])
print(f"After TTL expiration: {fetch_result.ids_not_exist}")
```

#### 2.3 批次獲取資料

```python
# 獲取多條資料
primary_keys = [1, 2, 3, 999]  # 999 不存在
fetch_result = collection.fetch_data(primary_keys)

print(f"Found {len(fetch_result.items)} items")
for item in fetch_result.items:
    print(f"  ID: {item.fields['id']}, Text: {item.fields['text']}")

print(f"Not found IDs: {fetch_result.ids_not_exist}")
```

#### 2.4 刪除資料

```python
# 刪除單條資料
collection.delete_data(primary_keys=[2])
print("Deleted ID: 2")

# 刪除多條資料
collection.delete_data(primary_keys=[3, 100])
print("Deleted IDs: 3, 100")

# 驗證刪除
fetch_result = collection.fetch_data([1, 2, 3])
print(f"Remaining items: {len(fetch_result.items)}")
print(f"Not found: {fetch_result.ids_not_exist}")
```

#### 2.5 清空所有資料

```python
# 刪除所有資料（保留集合和索引結構）
collection.delete_all_data()
print("All data deleted")

# 驗證
fetch_result = collection.fetch_data([1])
print(f"Items after delete_all: {len(fetch_result.items)}")
```

### 3. 索引管理

#### 3.1 建立不同型別的索引

```python
# 建立基本向量索引
basic_index_meta = {
    "IndexName": "basic_index",
    "VectorIndex": {
        "IndexType": "flat",
        "Distance": "ip"
    }
}
collection.create_index("basic_index", basic_index_meta)

# 建立帶標量索引的向量索引
scalar_index_meta = {
    "IndexName": "scalar_index",
    "VectorIndex": {
        "IndexType": "flat",
        "Distance": "l2"
    },
    "ScalarIndex": ["category", "priority", "timestamp"]
}
collection.create_index("scalar_index", scalar_index_meta)

# 建立混合索引（密集+稀疏向量）
hybrid_index_meta = {
    "IndexName": "hybrid_index",
    "VectorIndex": {
        "IndexType": "flat_hybrid",
        "Distance": "ip",
        "SearchWithSparseLogitAlpha": 1.0
    }
}
collection.create_index("hybrid_index", hybrid_index_meta)

# 列出所有索引
indexes = collection.list_indexes()
print(f"Total indexes: {len(indexes)}")
for idx_name in indexes:
    print(f"  - {idx_name}")
```

#### 3.2 更新索引

```python
# 更新索引的標量欄位和描述
collection.update_index(
    index_name="basic_index",
    scalar_index=["text", "tags"],
    description="Updated basic index with text and tags fields"
)

# 獲取索引後設資料
index_meta = collection.get_index_meta_data("basic_index")
print(f"Index: {index_meta['IndexName']}")
print(f"Description: {index_meta.get('Description', 'N/A')}")
print(f"Scalar Index: {index_meta.get('ScalarIndex', [])}")
```

#### 3.3 刪除索引

```python
# 刪除索引（不影響資料）
collection.drop_index("hybrid_index")
print("Index 'hybrid_index' dropped")

# 驗證
remaining_indexes = collection.list_indexes()
print(f"Remaining indexes: {remaining_indexes}")
```

### 4. 向量搜索

#### 4.1 基本向量搜索

```python
import random

# 準備測試資料
test_data = [
    {"id": i, "vector": [random.random() for _ in range(128)],
     "text": f"Document {i}", "category": ["tech", "science", "art"][i % 3]}
    for i in range(1, 51)
]
collection.upsert_data(test_data)

# 建立索引
collection.create_index("test_index", {
    "IndexName": "test_index",
    "VectorIndex": {"IndexType": "flat", "Distance": "ip"},
    "ScalarIndex": ["category"]
})

# 執行向量搜尋
query_vector = [random.random() for _ in range(128)]
result = collection.search_by_vector(
    index_name="test_index",
    dense_vector=query_vector,
    limit=10
)

print("=== Top 10 Similar Documents ===")
for i, item in enumerate(result.data, 1):
    print(f"{i}. ID: {item.id}, Score: {item.score:.4f}")
```

#### 4.2 帶過濾條件的向量搜尋

```python
# 過濾特定類別
result = collection.search_by_vector(
    index_name="test_index",
    dense_vector=query_vector,
    limit=5,
    filters={"op": "must", "field": "category", "conds": ["tech"]},
    output_fields=["text", "category"]
)

print("\n=== Tech Category Results ===")
for item in result.data:
    print(f"ID: {item.id}, Category: {item.fields['category']}, "
          f"Text: {item.fields['text']}, Score: {item.score:.4f}")
```

#### 4.3 範圍過濾搜尋

```python
# 新增帶優先順序的資料
priority_data = [
    {"id": i, "vector": [random.random() for _ in range(128)],
     "text": f"Priority doc {i}", "priority": i}
    for i in range(1, 21)
]
collection.upsert_data(priority_data)

# 搜尋優先順序在 5-15 之間的文件
result = collection.search_by_vector(
    index_name="test_index",
    dense_vector=query_vector,
    limit=10,
    filters={"op": "range", "field": "priority", "gte": 5, "lte": 15},
    output_fields=["text", "priority"]
)

print("\n=== Priority Range [5, 15] Results ===")
for item in result.data:
    print(f"ID: {item.id}, Priority: {item.fields['priority']}, "
          f"Score: {item.score:.4f}")
```

#### 4.4 分頁搜尋

```python
# 第一頁（前 10 條）
page1 = collection.search_by_vector(
    index_name="test_index",
    dense_vector=query_vector,
    limit=10,
    offset=0,
    output_fields=["text"]
)

print("\n=== Page 1 (offset=0, limit=10) ===")
for item in page1.data:
    print(f"ID: {item.id}, Text: {item.fields['text']}")

# 第二頁（10-20 條）
page2 = collection.search_by_vector(
    index_name="test_index",
    dense_vector=query_vector,
    limit=10,
    offset=10,
    output_fields=["text"]
)

print("\n=== Page 2 (offset=10, limit=10) ===")
for item in page2.data:
    print(f"ID: {item.id}, Text: {item.fields['text']}")
```

### 5. 其他搜索方式

#### 5.1 通過 ID 搜尋相似文件

```python
# 使用 ID=5 的向量搜尋相似文件
result = collection.search_by_id(
    index_name="test_index",
    id=5,
    limit=5,
    output_fields=["text"]
)

print("\n=== Similar to Document ID=5 ===")
for item in result.data:
    print(f"ID: {item.id}, Text: {item.fields['text']}, Score: {item.score:.4f}")
```

#### 5.2 隨機搜尋

```python
# 隨機獲取 10 條文件
result = collection.search_by_random(
    index_name="test_index",
    limit=10,
    output_fields=["text", "category"]
)

print("\n=== Random 10 Documents ===")
for item in result.data:
    print(f"ID: {item.id}, Category: {item.fields.get('category')}, "
          f"Text: {item.fields['text']}")

# 帶過濾的隨機搜尋
result = collection.search_by_random(
    index_name="test_index",
    limit=5,
    filters={"op": "must", "field": "category", "conds": ["science"]},
    output_fields=["text"]
)

print("\n=== Random 5 Science Documents ===")
for item in result.data:
    print(f"ID: {item.id}, Text: {item.fields['text']}")
```

#### 5.3 標量欄位排序搜尋

```python
# 按優先順序降序排列
result = collection.search_by_scalar(
    index_name="test_index",
    field="priority",
    order="desc",
    limit=5,
    output_fields=["text", "priority"]
)

print("\n=== Top 5 by Priority (Descending) ===")
for item in result.data:
    print(f"ID: {item.id}, Priority: {item.fields['priority']}, "
          f"Score: {item.score}")

# 按優先順序升序排列，帶過濾
result = collection.search_by_scalar(
    index_name="test_index",
    field="priority",
    order="asc",
    limit=5,
    filters={"op": "range", "field": "priority", "gte": 5},
    output_fields=["text", "priority"]
)

print("\n=== Top 5 by Priority (Ascending, priority >= 5) ===")
for item in result.data:
    print(f"ID: {item.id}, Priority: {item.fields['priority']}, "
          f"Score: {item.score}")
```

### 6. 資料聚合分析

#### 6.1 總計數

```python
# 獲取索引中的總文件數
agg_result = collection.aggregate_data(
    index_name="test_index",
    op="count"
)

print(f"\n=== Total Document Count ===")
print(f"Total: {agg_result.total_count}")
```

#### 6.2 分組計數

```python
# 按類別分組統計
agg_result = collection.aggregate_data(
    index_name="test_index",
    op="count",
    field="category"
)

print("\n=== Count by Category ===")
for group in agg_result.groups:
    print(f"{group['value']}: {group['count']}")
```

#### 6.3 帶過濾條件的聚合

```python
# 統計優先順序 >= 10 的文件，按類別分組
agg_result = collection.aggregate_data(
    index_name="test_index",
    op="count",
    field="category",
    filters={"op": "range", "field": "priority", "gte": 10}
)

print("\n=== Count by Category (priority >= 10) ===")
for group in agg_result.groups:
    print(f"{group['value']}: {group['count']}")
```

#### 6.4 聚合後過濾

```python
# 統計每個類別的文件數，只返回數量 >= 5 的類別
agg_result = collection.aggregate_data(
    index_name="test_index",
    op="count",
    field="category",
    cond={"gt": 5}
)

print("\n=== Categories with Count > 5 ===")
for group in agg_result.groups:
    print(f"{group['value']}: {group['count']}")
```

### 7. 進階特性

#### 7.1 自動 ID 生成

```python
# 不指定主鍵的集合（使用自動生成的 AUTO_ID）
auto_id_meta = {
    "CollectionName": "auto_id_collection",
    "Fields": [
        {"FieldName": "content", "FieldType": "text"},
        {"FieldName": "embedding", "FieldType": "vector", "Dim": 64},
    ]
}

auto_collection = get_or_create_local_collection(meta_data=auto_id_meta)

# 插入資料（無需指定 ID）
data = [
    {"content": "Document A", "embedding": [random.random() for _ in range(64)]},
    {"content": "Document B", "embedding": [random.random() for _ in range(64)]},
    {"content": "Document C", "embedding": [random.random() for _ in range(64)]}
]

result = auto_collection.upsert_data(data)
auto_ids = result.ids
print(f"Auto-generated IDs: {auto_ids}")

# 使用自動生成的 ID 獲取資料
fetch_result = auto_collection.fetch_data(auto_ids[:2])
print(f"\nFetched {len(fetch_result.items)} items using auto-generated IDs")
for item in fetch_result.items:
    print(f"  Content: {item.fields['content']}")

auto_collection.close()
```

#### 7.2 向量歸一化

```python
import math

# 建立支援向量歸一化的集合
normalized_meta = {
    "CollectionName": "normalized_vectors",
    "Fields": [
        {"FieldName": "id", "FieldType": "int64", "IsPrimaryKey": True},
        {"FieldName": "vector", "FieldType": "vector", "Dim": 128},
    ],
    "VectorIndex": {
        "NormalizeVector": True  # 啟用向量歸一化
    }
}

norm_collection = get_or_create_local_collection(meta_data=normalized_meta)

# 插入非歸一化向量（系統會自動歸一化）
raw_vector = [i * 0.1 for i in range(128)]
norm_collection.upsert_data([{"id": 1, "vector": raw_vector}])

# 建立索引
norm_collection.create_index("norm_index", {
    "IndexName": "norm_index",
    "VectorIndex": {"IndexType": "flat", "Distance": "ip"}
})

# 搜尋時向量也會自動歸一化
query = [i * 0.05 for i in range(128)]
result = norm_collection.search_by_vector(
    index_name="norm_index",
    dense_vector=query,
    limit=1
)

print("Vector normalization enabled")
print(f"Search result score: {result.data[0].score:.4f}")

norm_collection.close()
```

## 過濾條件詳解

### 支持的操作符

#### 1. `must` - 值必須在列表中

```python
# 單個值
filters = {"op": "must", "field": "category", "conds": ["tech"]}

# 多個值（OR 關係）
filters = {"op": "must", "field": "status", "conds": ["active", "pending", "review"]}
```

#### 2. `range` - 範圍查詢

```python
# 大於等於
filters = {"op": "range", "field": "score", "gte": 0.5}

# 小於等於
filters = {"op": "range", "field": "priority", "lte": 10}

# 範圍（閉區間）
filters = {"op": "range", "field": "age", "gte": 18, "lte": 65}

# 大於
filters = {"op": "range", "field": "price", "gt": 100}

# 小於
filters = {"op": "range", "field": "discount", "lt": 0.5}
```

#### 3. `time_range` - 時間範圍查詢（date_time）

`date_time` 字段使用 `datetime.isoformat()` 格式，例如 `2026-02-06T12:34:56.123456`。
不帶時區的時間會按**本地時區**解析。

```python
# 大於等於（ISO 時間字串）
filters = {
    "op": "time_range",
    "field": "created_at",
    "gte": "2026-02-01T00:00:00"
}

# 時間範圍（閉區間）
filters = {
    "op": "time_range",
    "field": "created_at",
    "gte": "2026-02-01T00:00:00",
    "lte": "2026-02-07T23:59:59"
}
```

#### 4. `geo_range` - 地理範圍查詢（geo_point）

`geo_point` 欄位寫入格式為 `"longitude,latitude"`，其中：
- `longitude` ∈ (-180, 180)
- `latitude` ∈ (-90, 90)

`radius` 支援 `m` 和 `km` 單位。

```python
filters = {
    "op": "geo_range",
    "field": "f_geo_point",
    "center": "116.412138,39.914912",
    "radius": "10km"
}
```

### 複雜過濾示例

```python
# 示例1: 查詢特定類別且高優先順序的文件
result = collection.search_by_vector(
    index_name="test_index",
    dense_vector=query_vector,
    filters={
        "op": "must",
        "field": "category",
        "conds": ["tech", "science"]
    },
    limit=10
)

# 示例2: 查詢特定分數範圍的文件
result = collection.search_by_vector(
    index_name="test_index",
    dense_vector=query_vector,
    filters={
        "op": "range",
        "field": "score",
        "gte": 0.7,
        "lte": 0.95
    },
    limit=10
)
```

## 最佳實踐

### 1. 選擇合適的儲存模式

- **記憶體模式**：適合臨時資料、測試環境、效能敏感場景
- **持久化模式**：適合生產環境、資料需要持久儲存的場景

### 2. 索引設計

- 為常用的過濾欄位建立標量索引
- 根據向量型別選擇合適的距離度量（IP 或 L2）
- 歸一化向量時使用 IP 距離

### 3. 效能最佳化

- 使用批次操作減少 I/O 次數
- 合理設定 limit 和 offset 進行分頁
- 避免頻繁的 delete_all 操作
- 對於大數據集，使用過濾條件縮小搜尋範圍

### 4. 資源管理

- 使用完畢後呼叫 `collection.close()` 釋放資源
- 合理設定 TTL 自動清理過期資料
- 定期監控索引大小和記憶體使用

## API 參考

### Collection 方法

| 方法 | 說明 | 返回值 |
|------|------|--------|
| `create_index(name, meta)` | 建立索引 | Index |
| `drop_index(name)` | 刪除索引 | None |
| `list_indexes()` | 列出所有索引 | List[str] |
| `get_index_meta_data(name)` | 獲取索引後設資料 | Dict |
| `update_index(name, scalar_index, description)` | 更新索引 | None |
| `upsert_data(data_list, ttl)` | 插入/更新資料 | UpsertResult |
| `fetch_data(primary_keys)` | 獲取資料 | FetchResult |
| `delete_data(primary_keys)` | 刪除資料 | None |
| `delete_all_data()` | 刪除所有資料 | None |
| `search_by_vector(...)` | 向量搜索 | SearchResult |
| `search_by_id(...)` | ID 搜索 | SearchResult |
| `search_by_random(...)` | 隨機搜尋 | SearchResult |
| `search_by_scalar(...)` | 標量排序搜尋 | SearchResult |
| `search_by_keywords(...)` | 關鍵詞搜尋 | SearchResult |
| `search_by_multimodal(...)` | 多模態搜尋 | SearchResult |
| `aggregate_data(...)` | 資料聚合 | AggregateResult |
| `get_meta_data()` | 獲取集合後設資料 | Dict |
| `update(fields)` | 更新集合字段 | None |
| `close()` | 關閉集合 | None |
| `drop()` | 刪除集合 | None |

## 貢獻

歡迎提交 Issue 和 Pull Request！

## 許可證

本專案遵循 OpenViking 專案的許可證協議。
