# 操作級 Telemetry 參考

操作級 telemetry 用來讓 OpenViking 在請求結果裡額外返回一份結構化摘要，幫助你瞭解這次操作實際發生了什麼，例如耗時、token 消耗、向量檢索情況、佇列處理進度，以及資源匯入階段統計。

適合這些場景：

- 排查請求為什麼變慢
- 觀察 token 或檢索行為
- 把結構化執行摘要接入你自己的日誌或觀測系統

更完整的觀測入口說明，包括健康檢查、`ov tui` 和 `OpenViking Console`，請先看 [可觀測性與排障](05-observability.md)。

## 基本說明

Telemetry 是按需返回的。只有你顯式請求時，OpenViking 才會在響應頂層返回 `telemetry` 欄位。

典型響應結構如下：

```json
{
  "status": "ok",
  "result": {"...": "..."},
  "telemetry": {
    "id": "tm_xxx",
    "summary": {
      "operation": "search.find",
      "status": "ok",
      "duration_ms": 31.2,
      "tokens": {
        "total": 24,
        "llm": {
          "input": 12,
          "output": 6,
          "total": 18
        }
      },
      "vector": {
        "searches": 3,
        "scored": 26,
        "passed": 8,
        "returned": 5
      }
    }
  }
}
```

說明：

- `telemetry.id` 是不透明的關聯 ID
- `telemetry.summary` 是面向呼叫方的結構化摘要
- 只有本次操作實際產出的分組才會返回
- 數值型 `0` 預設不會出現在響應裡

## 當前支援範圍

### HTTP API

當前這些介面支援 operation telemetry：

- `POST /api/v1/search/find`
- `POST /api/v1/search/search`
- `POST /api/v1/resources/temp_upload`
- `POST /api/v1/resources`
- `POST /api/v1/skills`
- `POST /api/v1/sessions`
- `POST /api/v1/sessions/{session_id}/messages`
- `POST /api/v1/sessions/{session_id}/commit`

### Python SDK

Python 客戶端裡，下面這些呼叫支援相同的 telemetry 語義：

- `add_resource(...)`
- `add_skill(...)`
- `find(...)`
- `search(...)`
- `create_session(...)`
- `add_message(...)`
- `commit_session(...)`
- `Session.commit(...)`

## 如何請求 telemetry

### JSON 請求

對於 JSON body，`telemetry` 支援下面兩種常用寫法：

```json
{"telemetry": true}
```

```json
{"telemetry": {"summary": true}}
```

`true` 和 `{"summary": true}` 的效果相同，都會返回 `telemetry.id + telemetry.summary`。

物件形態當前只開放 `summary` 這個開關。

如果不想返回 telemetry，可以省略該欄位，或者顯式傳：

```json
{"telemetry": false}
```

```json
{"telemetry": {"summary": false}}
```

### Multipart 上傳請求

`POST /api/v1/resources/temp_upload` 是 multipart form 介面。這個介面需要把 telemetry 當作表單欄位傳入：

```bash
curl -X POST http://localhost:1933/api/v1/resources/temp_upload \
  -H "X-API-Key: your-key" \
  -F "file=@./notes.md" \
  -F "telemetry=true"
```

這個介面當前只支援布林形態的表單引數。
這個介面的 `upload_mode` 也是表單欄位；預設值為 `local`，只有在明確需要分散式共享臨時上傳時，才應設定為 `shared`。Python HTTP client 也可以在 `ovcli.conf` 中設定 `upload.mode = "shared"`；Rust `ov` CLI 則使用 `OPENVIKING_UPLOAD_MODE=shared`。

## 常見 summary 分組

summary 頂層這 3 個基礎欄位總會存在：

- `operation`
- `status`
- `duration_ms`

根據不同操作，還可能出現這些分組：

- `tokens`：LLM 和 embedding 的 token 統計
- `vector`：向量檢索與過濾統計
- `resource`：資源匯入與處理階段摘要
- `queue`：等待模式下的佇列處理統計
- `semantic_nodes`：語義節點提取統計
- `memory`：記憶提取或去重摘要
- `errors`：聚合後的錯誤資訊

如果某個分組對本次操作不適用，就不會返回。

## 欄位說明

只有這次操作實際產出的欄位才會返回。某個分組缺失時，應理解為“不適用”，而不是預設等於 0。

### 頂層 telemetry 欄位

| 欄位 | 含義 |
| --- | --- |
| `telemetry.id` | 本次操作的不透明關聯 ID |
| `summary.operation` | 操作名，例如 `search.find`、`resources.add_resource`、`session.commit` |
| `summary.status` | telemetry 最終狀態，通常是 `ok` 或 `error` |
| `summary.duration_ms` | 本次操作的端到端總耗時，單位毫秒 |

### `summary.tokens`

| 欄位 | 含義 |
| --- | --- |
| `summary.tokens.total` | 本次操作累計 token 總量 |
| `summary.tokens.llm.input` | LLM 輸入 token 總量 |
| `summary.tokens.llm.output` | LLM 輸出 token 總量 |
| `summary.tokens.llm.total` | LLM token 總量 |
| `summary.tokens.embedding.total` | embedding 模型 token 總量 |

### `summary.vector`

| 欄位 | 含義 |
| --- | --- |
| `summary.vector.searches` | 向量檢索呼叫次數 |
| `summary.vector.scored` | 被打分的候選數量 |
| `summary.vector.passed` | 通過閾值或後續過濾的候選數量 |
| `summary.vector.returned` | 最終返回給上層邏輯的結果數量 |
| `summary.vector.scanned` | 底層實際掃描的向量數量 |
| `summary.vector.scan_reason` | 本次掃描策略或掃描原因說明 |

配置 cuVS 後，`summary.vector.cuvs` 會聚合本次 operation 內所有 dense search 的
CPU/GPU 路由和分階段耗時；併發 query 的完成順序不會改變結果。其中不會包含
查詢向量、filter 值或 URI 內容，未知的維度值會統一歸入有界的 `other` bucket。

| 欄位 | 含義 |
| --- | --- |
| `summary.vector.cuvs.searches` | 本次聚合包含的 dense search 數量 |
| `summary.vector.cuvs.algorithms.<algorithm>` | 按 cuVS 演算法統計的 search 數，例如 `brute_force` 或 `cagra` |
| `summary.vector.cuvs.dtypes.<dtype>` | 按 GPU dataset/query dtype 統計的 search 數：`float32` 或 `float16` |
| `summary.vector.cuvs.max_concurrent_gpu_searches` | 觀測到的單 index in-flight GPU search 配置上限最大值 |
| `summary.vector.cuvs.auto_mode_searches` | 啟用自動 CPU/GPU 路由的 search 數量 |
| `summary.vector.cuvs.micro_batching_searches` | 使用 OpenViking 可選 micro-batch scheduler 的 search 數量 |
| `summary.vector.cuvs.micro_batched_searches` | 其中以多於一行 query 共同 dispatch 的 search 數量 |
| `summary.vector.cuvs.micro_batching_warm_fast_path_searches` | 使用 micro-batch scheduler、從 clean current snapshot 入隊且未經過 caller 側 device-gate admission 的 search 數量 |
| `summary.vector.cuvs.batch_size_max` | 單次共享 cuVS call 觀測到的最大 query 行數 |
| `summary.vector.cuvs.searches_by_batch_size.<size>` | 按 1 到 8 的有界 batch size 統計 search 數量 |
| `summary.vector.cuvs.routes.<reason>` | 按路由原因統計的 search 數，例如 `cuvs`、`native_filter_threshold`、`native_rebuild_pending` 或 `native_memory_budget` |
| `summary.vector.cuvs.filter_kinds.<kind>` | 按低基數 filter 型別統計的 search 數：`none`、`scalar` 或 `path` |
| `summary.vector.cuvs.filter_cache_hits` | 複用 prepared/preflight filter 的 search 數量 |
| `summary.vector.cuvs.native_filter_reuses` | native recall 複用 preflight bitmap 的次數 |
| `summary.vector.cuvs.builds` | 執行 GPU index build 的 search 數量 |
| `summary.vector.cuvs.eligible_count_max` | native filter 後觀測到的最大候選數 |
| `summary.vector.cuvs.records_generation_max` | 觀測到的最大 record generation |
| `summary.vector.cuvs.index_size_max` | 觀測到的最大 cuVS host snapshot 行數 |
| `summary.vector.cuvs.memory.estimated_peak_bytes_max` | auto build 准入使用的最大峰值視訊記憶體估算 |
| `summary.vector.cuvs.memory.free_bytes_min` | 單 GPU 准入協調器內觀測到的最小空閒視訊記憶體 |
| `summary.vector.cuvs.memory.usable_bytes_min` | 扣除配置 reserve 後觀測到的最小可用視訊記憶體 |
| `summary.vector.cuvs.timings_ms.<stage>.sum` | `total`、`preflight`、`queue`、`gpu_gate_queue`、`build`、`filter_prepare`、`batch_wait`、`gpu_search` 或 `native_search` 階段跨 search 的耗時總和 |
| `summary.vector.cuvs.timings_ms.<stage>.max` | 同一階段單次 search 的最大耗時 |

對於共享 micro-batch，`gpu_search` 表示每個成員請求所感知的同一次 cuVS call
service latency，因此會按請求各記錄一次。`gpu_search.sum` 適合解釋請求側累計延遲，
但不等同於 GPU busy time；它可能約為物理 call 時長乘以 batch size。`batch_wait`
表示請求從進入 scheduler 到 GPU dispatch 的等待時間，包括 worker 排程和等待當前 device
work 完成的時間。`gpu_gate_queue` 表示 caller 在 gated rebuild/filter preparation、入隊或
非 batch GPU search 前，等待進入序列 device gate 的時間。warm fast path 會跳過這次 caller
admission，所以其 `gpu_gate_queue` 為零；worker 側等待仍計入 `batch_wait`。更寬泛的 `queue`
階段會在適用時包含這兩類請求可感知的排隊時間。

### `summary.resource`

這個分組常見於 `resources.add_resource` 這類資源匯入操作。

| 欄位 | 含義 |
| --- | --- |
| `summary.resource.total.duration_ms` | add-resource 操作總耗時 |
| `summary.resource.source_execute.duration_ms` | 執行源操作的耗時 |
| `summary.resource.source_prepare.duration_ms` | 準備持久化 source 的耗時 |
| `summary.resource.parse_artifact.duration_ms` | 生成 parser artifact 的耗時 |
| `summary.resource.target_resolve.duration_ms` | 解析最終資源目標的耗時 |
| `summary.resource.update_plan.duration_ms` | 構建增量更新計劃的總耗時 |
| `summary.resource.update_plan.artifact_inventory.duration_ms` | 掃描並歸一化 parser artifact 的耗時 |
| `summary.resource.update_plan.rnfv_snapshot.duration_ms` | 讀取 R/N/F/V 快照的耗時 |
| `summary.resource.update_plan.diff_and_compile.duration_ms` | 計算 diff 並編譯動作的耗時 |
| `summary.resource.content_commit.duration_ms` | 把內容動作應用到正式樹的耗時 |
| `summary.resource.derived_enqueue.duration_ms` | 將 semantic 和 index 工作入隊的耗時 |
| `summary.resource.semantic.queue_wait.duration_ms` | semantic 工作在 QueueFS 中等待的耗時 |
| `summary.resource.semantic.execute.duration_ms` | semantic 工作執行耗時 |
| `summary.resource.embedding.queue_wait.duration_ms` | embedding 工作在 QueueFS 中等待的耗時 |
| `summary.resource.embedding.execute.duration_ms` | embedding 工作執行耗時 |
| `summary.resource.flags.wait` | 本次請求是否使用了 `wait=true` |
| `summary.resource.flags.build_index` | 本次請求是否啟用了 `build_index` |
| `summary.resource.flags.summarize` | 本次請求是否顯式啟用了 `summarize` |
| `summary.resource.flags.watch_enabled` | 本次請求是否啟用了 watch 管理 |

### `summary.queue`

這個分組常見於需要等待佇列任務完成的操作。

| 欄位 | 含義 |
| --- | --- |
| `summary.queue.semantic.processed` | 已處理的 semantic queue 訊息數 |
| `summary.queue.semantic.requeue_count` | 為重試而重新入隊的 semantic 訊息數 |
| `summary.queue.semantic.error_count` | semantic queue 錯誤數 |
| `summary.queue.embedding.processed` | 已處理的 embedding queue 訊息數 |
| `summary.queue.embedding.requeue_count` | 為重試而重新入隊的 embedding 訊息數 |
| `summary.queue.embedding.error_count` | embedding queue 錯誤數 |

### `summary.semantic_nodes`

| 欄位 | 含義 |
| --- | --- |
| `summary.semantic_nodes.total` | 語義樹節點總數 |
| `summary.semantic_nodes.done` | 已完成節點數 |
| `summary.semantic_nodes.pending` | 待處理節點數 |
| `summary.semantic_nodes.running` | 正在處理中的節點數 |

### `summary.memory`

這個分組常見於 `session.commit` 這類記憶提取流程。

| 欄位 | 含義 |
| --- | --- |
| `summary.memory.extracted` | 本次操作最終抽取出的 memory 數量 |
| `summary.memory.extract.duration_ms` | memory extract 主流程總耗時 |
| `summary.memory.extract.candidates.total` | 最終動作執行前的候選總數 |
| `summary.memory.extract.candidates.standard` | 普通 memory candidate 數量 |
| `summary.memory.extract.actions.created` | 新建 memory 數量 |
| `summary.memory.extract.actions.merged` | 合併到已有 memory 的次數 |
| `summary.memory.extract.actions.deleted` | 刪除舊 memory 的次數 |
| `summary.memory.extract.actions.skipped` | 被跳過的 candidate 數量 |
| `summary.memory.extract.stages.prepare_inputs_ms` | 提取前準備輸入資料的耗時 |
| `summary.memory.extract.stages.llm_extract_ms` | 呼叫 LLM 做提取的耗時 |
| `summary.memory.extract.stages.normalize_candidates_ms` | 解析並歸一化候選的耗時 |
| `summary.memory.extract.stages.profile_create_ms` | 建立或更新 profile memory 的耗時 |
| `summary.memory.extract.stages.dedup_ms` | candidate 去重耗時 |
| `summary.memory.extract.stages.create_memory_ms` | 建立新 memory 的耗時 |
| `summary.memory.extract.stages.merge_existing_ms` | 合併到已有 memory 的耗時 |
| `summary.memory.extract.stages.delete_existing_ms` | 刪除舊 memory 的耗時 |
| `summary.memory.extract.stages.flush_semantic_ms` | flush semantic queue 的耗時 |

### `summary.search`

| 欄位 | 含義 |
| --- | --- |
| `summary.search.target_abstract.duration_ms` | 為目標 URI 預取摘要的耗時 |
| `summary.search.intent_analysis.duration_ms` | 查詢意圖分析耗時 |
| `summary.search.embed_query.duration_ms` | 查詢向量化耗時 |
| `summary.search.vector_retrieval.duration_ms` | 向量召回階段耗時 |
| `summary.search.typed_queries_count` | 解析出的 typed query 數量 |

### `summary.errors`

| 欄位 | 含義 |
| --- | --- |
| `summary.errors.stage` | 記錄錯誤時所在的邏輯階段 |
| `summary.errors.error_code` | 錯誤碼或異常型別 |
| `summary.errors.message` | 人類可讀的錯誤描述 |

## 示例

### 帶 telemetry 的檢索請求

```bash
curl -X POST http://localhost:1933/api/v1/search/find \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "query": "memory dedup",
    "limit": 5,
    "telemetry": true
  }'
```

### 匯入資源並返回 telemetry

```bash
curl -X POST http://localhost:1933/api/v1/resources \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "path": "./docs/readme.md",
    "reason": "telemetry demo",
    "telemetry": true
  }'
```

### Python SDK

```python
from openviking_sdk import AsyncHTTPClient

client = AsyncHTTPClient(url="http://localhost:1933", api_key="your-key")
await client.initialize()

result = await client.find(
    query="memory dedup",
    options={"telemetry": True},
)
print(result["telemetry"]["summary"]["operation"])
print(result["telemetry"]["summary"]["duration_ms"])
```

## 限制與注意事項

- 當前對外只提供 summary-only telemetry
- `{"telemetry": {"events": true}}` 不是當前支援的公開請求形態
- 事件流風格的選擇引數不屬於當前公開介面
- `session.commit` 只有在 `wait=true` 時才支援 telemetry
- 如果 `session.commit` 使用 `wait=false` 並請求 telemetry，服務端會返回 `INVALID_ARGUMENT`
- telemetry 的頂層結構穩定，但具體有哪些 summary 分組取決於實際操作

## 相關文件

- [可觀測性與排障](05-observability.md)
- [認證](04-authentication.md)
- [系統 API](../api/07-system.md)
