# 使用 NVIDIA cuVS 進行本地向量檢索

Business Data Platform 的 `cuvs` 後端保留本地後端的記錄持久化、標量索引、稀疏檢索和故障恢復，只把 dense vector search 交給 NVIDIA cuVS。這樣可以先驗證 GPU 檢索鏈路，而不需要重新實現一個完整的向量資料庫。

## 環境要求

- Linux x86_64 或 aarch64
- 受支持的 NVIDIA GPU，以及兼容的 CUDA driver
- Python 3.11+（cuVS 26.06 的 Python wheel 要求）

按所選版本核對 [cuVS 安裝要求](https://docs.nvidia.com/cuvs/installation) 和 [Python 包安裝指南](https://docs.nvidia.com/cuvs/installation/python)。當前 cuVS 原始碼構建要求 CUDA Toolkit 12.2+ 和 Ampere 或更新架構的 GPU；安裝包要求取決於所選版本。

CUDA 12：

```bash
pip install -e .
pip install cuvs-cu12 'cupy-cuda12x[ctk]' --extra-index-url=https://pypi.nvidia.com
```

CUDA 13：

```bash
pip install -e .
pip install cuvs-cu13 'cupy-cuda13x[ctk]' --extra-index-url=https://pypi.nvidia.com
```

CuPy 的 `[ctk]` extra 會安裝 cuVS Python 互操作路徑所需的 CUDA toolkit
headers；即使宿主機已有 CUDA driver、但沒有完整 toolkit，也建議保留該 extra。

## 配置

先用 `brute_force` 跑通精確檢索：

```json
{
  "storage": {
    "workspace": "/data/openviking",
    "vectordb": {
      "backend": "cuvs",
      "distance_metric": "cosine",
      "cuvs": {
        "algorithm": "brute_force",
        "dtype": "float32",
        "max_concurrent_gpu_searches": 1,
        "micro_batching_enabled": false,
        "fallback_to_native": true,
        "filter_cache_size": 16
      }
    }
  }
}
```

資料量增大後可以切換到 CAGRA，並直接傳入 cuVS 的構建與查詢引數：

```json
{
  "storage": {
    "vectordb": {
      "backend": "cuvs",
      "cuvs": {
        "algorithm": "cagra",
        "build_params": {
          "graph_degree": 64,
          "intermediate_graph_degree": 128,
          "build_algo": "nn_descent"
        },
        "search_params": {
          "itopk_size": 64,
          "search_width": 1
        }
      }
    }
  }
}
```

### 視訊記憶體感知自動模式

如果希望保留 `local` 為預設 backend、只在 GPU 有足夠空閒視訊記憶體時自動啟用 cuVS，
可以開啟以下開關：

```json
{
  "storage": {
    "vectordb": {
      "backend": "local",
      "cuvs": {
        "auto_enable": true,
        "algorithm": "brute_force",
        "auto_memory_reserve_mb": 1024,
        "auto_memory_safety_factor": 2.0,
        "auto_filter_native_threshold": 2000,
        "auto_path_filter_native_threshold": 200,
        "auto_background_rebuild": true,
        "auto_rebuild_debounce_ms": 500
      }
    }
  }
}
```

每次 lazy build/rebuild 前，auto 模式會讀取當前空閒視訊記憶體，並根據配置的 `dtype`
估算 device vector payload、CAGRA graph/intermediate graph（如適用）和
filter-bitset cache，再乘以 `auto_memory_safety_factor`，同時保留
`auto_memory_reserve_mb`。如果預算不足，
或者 cuVS/GPU 不可用，本次查詢繼續使用未改變的 native index；cuVS index 保持
dirty，後續查詢會在視訊記憶體釋放後重新嘗試。通過 admission 後若仍遇到 GPU allocation
failure，也會回退 native。顯式配置 `backend: "cuvs"` 時仍保持 fail-fast，不經過
這層自動判斷。

同一程序內的 local collection 會按 GPU 協調 build 和 admission，避免兩個併發
build 都基於同一份過期 free-memory 觀測通過准入。不同 GPU 彼此獨立，warmed
search 也不會被這個協調器序列化。

auto 模式還會使用 native scalar index 返回的候選數做 filtered query 延遲路由：
候選數不超過 `auto_filter_native_threshold` 時使用 native vector recall；路徑過濾
採用更低的 `auto_path_filter_native_threshold`，因為寬 URI 子樹的 Trie 遍歷和
bitmap union 本身可能佔主要開銷。預設閾值分別為 2,000 和 200，設為 0 可關閉
對應路由。閾值與硬體、維度和工作負載有關。顯式 `backend: "cuvs"` 對支援的
dense query 仍固定使用 cuVS。

`auto_background_rebuild` 預設關閉。開啟後，連續 mutation 會按
`auto_rebuild_debounce_ms` 合併，worker 在不持有跨後端 mutation 鎖的情況下構建
新的 immutable GPU snapshot。預設 500 ms 用於避免普通 ingest 的中間 batch
反覆觸發構建。對於邊界明確、由多次呼叫組成的 bulk load，可把所有寫入放在
`async with backend.bulk_ingest(ctx=ctx):` scope 內：native 可見性和持久化仍按
每次呼叫推進，但 derived GPU maintenance 會延遲到最外層 scope 退出後只調度一次。
該 scope 只是 maintenance hint，不提供事務或原子性；退出 scope 只負責排程 rebuild，
本身不等待 GPU ready。vector backend benchmark 會額外在正式計時 search 前顯式等待
最終 snapshot；無法識別 bulk 邊界的呼叫方仍可按實際 batch 間隔調整 debounce。Auto
仍為顯式啟用；未開啟 Auto/background rebuild 時，該 scope 對派生維護為 no-op，不改變
原生 CPU 檢索、寫入與 dtype 行為。snapshot dirty 期間查詢直接使用當前 native index，
不會把 GPU build 時間轉化成請求排隊時間。worker 只在 record generation 仍匹配時
原子提交 label layout 和 GPU snapshot；過期 build 會被丟棄，並只重建最新一代。

## GPU 視訊記憶體佔用

使用預設的 `dtype: "float32"` 時，brute-force 的主要常駐 device payload 為
`N * dimension * 4` bytes。顯式設定 `dtype: "float16"` 後，device payload
降為 `N * dimension * 2` bytes。CAGRA 還需要約 `N * graph_degree * 4` bytes
儲存 graph，構建期間可能需要 `N * intermediate_graph_degree * 4` bytes 的
intermediate graph。每個快取 filter bitset 約佔 `ceil(N / 32) * 4` bytes。

之前的 index-only 測試使用 `cudaMemGetInfo` 記錄 build 前後的視訊記憶體增量；下表每項
均為 5 個乾淨程序的中位數：

| 資料集 | cuVS 演算法 | 實測 GPU 增量 |
| --- | --- | ---: |
| 100K x 768D | brute-force | 294 MiB |
| 1M x 768D | brute-force | 2.9 GiB |
| 100K x 1024D | brute-force | 392 MiB |
| 1M x 1024D | brute-force | 3.9 GiB |
| 1,183,514 x 100D | brute-force | 452 MiB |
| 1,183,514 x 100D | CAGRA | 872 MiB |

這些數值是 build 完成後的常駐增量，不是取樣得到的 peak VRAM。allocator 狀態、
cuVS 版本、CAGRA 引數、query batch 和並行 GPU workload 都可能進一步提高峰值；
它們也不包含這些程序在 build 前觀測到的約 327 MiB CUDA runtime/context 基線。
因此 auto 模式會先初始化 runtime、讀取剩餘空閒視訊記憶體，再應用保守 safety factor
和獨立 reserve，而不會只按 vector payload 准入。

距離語義與原本的 Business Data Platform 本地後端保持一致：cosine 會先做 L2 歸一化再執行 inner product；L2 的返回分數仍為 `1 - squared_l2`，分數越大越相似。

## 資料型別與原生索引行為

啟用 cuVS 不會改變 Business Data Platform 的預設後端，也不會重寫原生 CPU 索引。正常的
collection metadata 仍為 `VectorIndex.Quant=int8`，因此 native fallback
繼續使用現有的、帶逐向量 scale 的 int8 量化。與此同時，cuVS device dataset
和 query 使用配置的 `dtype`：預設是 float32，也可以顯式選擇 float16。host
record shadow 儲存預處理後的 Python 浮點值；僅在建立 device dataset 和 query
時將它們 cast 為配置的 dtype。cuVS Python brute-force API 支援這兩種 device
表示，但不能直接表示 Business Data Platform 的 scaled-int8 record 格式。

所以兩條 dense search 路徑不是等記憶體、等數值語義的比較：native 是在 CPU
量化表示上的精確檢索，cuVS brute-force 是在保留的 float32 或 float16 device
表示上的精確檢索，兩者可能出現少量 score 或 neighbor ordering 差異。
Benchmark 必須同時報告兩邊的資料型別和 Recall@K，不能將結果描述為
equal-dtype 或 equal-memory。
這是首版 opt-in 整合的有意邊界，現有 CPU 行為保持不變。auto 模式會根據 filter
候選閾值在兩種表示之間選擇；要求固定數值表示的應用應使用顯式 backend，或將
native 路由閾值設為 0。

GPU 低精度儲存是顯式能力，不做隱式 cast。設定 `dtype: "float16"` 會把 cuVS
dataset 和每個 query 同時 cast 為 float16，brute-force 與 CAGRA 都不使用混合
query/index dtype。這是儲存 cast，不是逐向量量化，必須以預設 float32 為 ground
truth 報告 Recall@K。與 native 相容的 int8 仍需單獨設計，因為 Business Data Platform 使用
逐向量 scale，而 cuVS brute-force 不能直接接收這種 scaled-int8 表示。CAGRA
int8 或 PQ compression 也應作為近似模式，單獨報告 recall/latency/memory frontier。

整合使用 immutable GPU snapshot 和可複用的 cuVS resource/CUDA stream。host 側
filter 與 snapshot 工作可以並行，但 `max_concurrent_gpu_searches` 預設是 1：
單 query brute-force 通常受視訊記憶體頻寬限制，併發 kernel 可能互相爭搶頻寬、反而降低
吞吐。只有在目標 GPU 與真實 workload 上測得收益後，才建議顯式調大該值。

### 可選的請求微批處理

精確 brute-force 路徑可以把相容的併發請求合併為一次 cuVS matrix-query 呼叫：

```json
{
  "storage": {
    "vectordb": {
      "backend": "cuvs",
      "cuvs": {
        "algorithm": "brute_force",
        "max_concurrent_gpu_searches": 1,
        "micro_batching_enabled": true,
        "micro_batching_max_batch_size": 8,
        "micro_batching_max_wait_ms": 1.0
      }
    }
  }
}
```

scheduler 只會合併使用同一個 immutable GPU snapshot、同一個 prepared filter、
同一個實際 top-k 的請求；GPU 返回的每一行會映射回原請求，因此標量/路徑過濾和
結果條數語義不變。

當 immutable snapshot clean、屬於當前 generation，且請求沒有 filter 或命中已準備好的
device filter cache 時，可走 warm admission fast path。該路徑會 pin snapshot/filter，
並在 caller 不獲取 device-search gate 的情況下直接入隊。dirty、cold 或 stale snapshot，
device filter cache miss/eviction、rebuild 和 device filter materialization 仍走 gated
preparation。準備完成後，caller 先入隊並釋放 gate，再等待結果；只有 micro-batch worker
會在持有 device-search gate 時執行 matrix search，所以 caller 不會持 gate 等待 worker。

collection window 是延遲與吞吐的權衡。它只限制 scheduler 為收集相容請求而主動等待的
時間：從最早的 compatible request 起最多主動等待配置值；它不是 enqueue-to-dispatch
latency 上限。worker 排程、前一個 GPU call 或 gated device preparation 都可能使實際
dispatch 更晚。併發充足時，最多由配置上限數量的 query 共用一次 GPU call。

引數約束如下：

- `micro_batching_max_batch_size` 範圍為 1 到 8；
- `micro_batching_max_wait_ms` 範圍為 0 到 100 ms；設為 `0` 表示不主動等待，但仍可
  opportunistically 合併已經同時在佇列中的相容請求；
- micro-batching 僅支援 `algorithm: "brute_force"`，並要求
  `max_concurrent_gpu_searches: 1`。

該能力預設關閉，是 Business Data Platform 自己的 micro-batcher，不等同於 cuVS 官方名為
Dynamic Batching 的元件。首版只支援 exact brute-force；CAGRA 和併發 dispatch 多個
batch 會在獨立驗證後再開放。Auto 模式也可使用這些選項，但被路由到原生 CPU 的請求
不會進入 GPU batch queue。single-row 與 matrix-query 在近似並列分數處可能有順序
差異，調參時應同時驗證結果集合重合度和 score。

## 最小功能驗證

倉庫提供的 smoke test 不依賴 embedding 或 VLM 服務：

```bash
python examples/cuvs_smoke.py

# 驗證 CAGRA 圖索引
python examples/cuvs_smoke.py --algorithm cagra

# 驗證顯式 float16 路徑
python examples/cuvs_smoke.py --dtype float16
```

核心呼叫方式如下：

```python
from openviking.storage.vectordb.collection.local_collection import (
    get_or_create_local_collection,
)

collection = get_or_create_local_collection(
    meta_data={
        "CollectionName": "cuvs_smoke",
        "Fields": [
            {"FieldName": "id", "FieldType": "string", "IsPrimaryKey": True},
            {"FieldName": "vector", "FieldType": "vector", "Dim": 4},
            {"FieldName": "account_id", "FieldType": "string"},
            {"FieldName": "uri", "FieldType": "path"},
        ],
    },
    config={
        "dense_search": {
            "backend": "cuvs",
            "algorithm": "brute_force",
            "fallback_to_native": True,
        }
    },
)
collection.create_index(
    "default",
    {
        "IndexName": "default",
        "VectorIndex": {"IndexType": "flat", "Distance": "cosine"},
        "ScalarIndex": ["account_id", "uri"],
    },
)
collection.upsert_data(
    [
        {"id": "a", "vector": [1, 0, 0, 0], "account_id": "demo", "uri": "/docs/a"},
        {"id": "b", "vector": [0, 1, 0, 0], "account_id": "demo", "uri": "/docs/b"},
    ]
)
result = collection.search_by_vector(
    "default",
    dense_vector=[1, 0, 0, 0],
    limit=2,
    filters={"op": "must", "field": "account_id", "conds": ["demo"]},
)
assert [item.id for item in result.data] == ["a", "b"]
collection.close()
```

## 當前階段的限制

- cuVS 只接管 pure dense search；sparse/hybrid query 在 `fallback_to_native=true` 時走原生本地索引。
- local 整合通過 native scalar/path index 生成 prefilter，因此繼承原生 DSL、`date_time`、`geo_point` 和 path depth 的過濾語義，而不是在 Python 重複實現。
- 每次 GPU rebuild 會向 native engine 註冊一次 cuVS label 順序。新過濾條件直接複用 native scalar/path index 的 bitmap，再投影為 cuVS row bitset，不再用 Python 掃描所有 host-side records。
- `filter_cache_size` 會保留最近使用的 GPU bitset 或 native 路由決策，並在資料更新時失效；auto 模式在進入 cuVS search 前預判候選數，不同的首次過濾條件可通過 native engine 的共享讀路徑平行計算，命中已快取的 native 路由時則直接進入 native index。generation 校驗會阻止跨 mutation 計算出的舊結果寫入路由快取。
- GPU index 使用 immutable snapshot 和可複用的 cuVS resources/CUDA stream；預設關閉的 micro-batching 可讓 compatible warm request 繞過 caller 側 gate 入隊，並由唯一持有 device-search gate 執行 matrix search 的 worker 合批。mutation 和 snapshot commit 使用跨後端寫鎖。
- 預設情況下，每次 upsert/delete 後仍由下一次查詢同步重建；開啟 `auto_background_rebuild` 後，dirty 期間查詢走 native，連續寫被合併為後臺重建。
- cuVS 索引不作為權威持久化資料；程序重啟時會從 Business Data Platform 本地 store 重建，因此不受 cuVS 跨版本序列化格式變化影響。
- `brute_force` 適合功能對齊和 ground truth；CAGRA 的 graph/search 引數需要在後續結合召回率、QPS、延遲和視訊記憶體進行調優。
