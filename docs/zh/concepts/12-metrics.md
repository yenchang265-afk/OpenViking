# 指標與 Metrics

Business Data Platform 提供一套面向機器抓取的指標體系，用於暴露系統執行態、請求質量、模型呼叫情況、資源處理吞吐、探針健康狀態等資訊。

與人類排障用的 `/api/v1/observer/*` 和業務分析用的 `/api/v1/stats/*` 不同，Metrics 的目標是：

- 供 Prometheus、Grafana Agent 等系統**高頻抓取**
- 使用低基數、可聚合的指標模型
- 服務於監控、告警、容量觀察與迴歸排查

## 概述

### 為什麼需要 Metrics

Metrics 適合回答這類問題：

- 最近一段時間 HTTP 請求是否異常升高？
- 資源匯入、檢索、模型呼叫是否變慢？
- 佇列是否堆積？
- 關鍵依賴（儲存、模型、VikingDB、加密、非同步系統）當前是否可用？
- 某些租戶是否出現異常流量或異常錯誤率？

相比日誌和 observer 狀態，metrics 更適合做：

- 持續抓取
- 時間序列聚合
- Dashboard 展示
- 告警規則

### 與 Observer / Stats 的區別

| 能力 | 適合什麼 | 輸出形式 | 典型使用場景 |
|------|----------|----------|--------------|
| `/metrics` | 線上監控、告警、聚合趨勢 | Prometheus exposition 文本 | Grafana 看板、Prometheus 抓取 |
| `/api/v1/observer/*` | 人工檢視元件瞬時狀態 | JSON / 狀態表 | 排障、健康檢查 |
| `/api/v1/stats/*` | 分析型統計 | JSON | memory health、staleness、session extraction 等 |

設計邊界是：

- `/metrics` 只承載**低基數、低成本**指標
- `/api/v1/stats/*` 繼續承載分析型統計，不為了 Prometheus 抓取模型犧牲表達能力

## 指標體系架構

Business Data Platform 當前的 metrics 體系由四層組成：

```text
業務邏輯 / HTTP 請求 / 後臺任務
          │
          ▼
      DataSource
  （事件發射 / 狀態讀取）
          │
          ▼
      Collector
 （語義分流、標籤決定）
          │
          ▼
    MetricRegistry
   （程序內指標註冊中心）
          │
          ▼
      Exporter
 （Prometheus 文本匯出）
          │
          ▼
       /metrics
```

### DataSource

DataSource 負責提供指標輸入，主要有兩種方式：

- **事件型**：業務程式碼在關鍵路徑發射事件，例如檢索完成、模型呼叫成功、資源匯入階段完成
- **讀取型**：在 `/metrics` 抓取前讀取當前狀態，例如佇列狀態、鎖狀態、探針狀態

### Collector

Collector 負責把輸入轉成指標語義：

- 決定寫哪個指標
- 決定攜帶哪些標籤
- 決定失敗時如何暴露（例如 `valid=1/0`）

### MetricRegistry

MetricRegistry 是程序內的指標註冊中心，用於儲存當前指標值，並在匯出時統一讀取。

### Exporter

當前首個落地匯出器是 Prometheus Exporter，用於把 registry 中的指標渲染成 Prometheus exposition 文本。

## 使用方式

### 訪問 `/metrics`

當前實現中，`/metrics` 未接入 `get_request_context` 等鑑權依賴，因此從程式碼行為上看，它當前等價於公開抓取端點。

```bash
curl http://localhost:1933/metrics
```

如果你的部署環境通過閘道器、反向代理或服務發現層對 `/metrics` 做了保護，則應按部署方式附加鑑權。

### Prometheus 抓取示例

```yaml
scrape_configs:
  - job_name: openviking
    metrics_path: /metrics
    static_configs:
      - targets: ["localhost:1933"]
```

### 如何理解常見標籤

| 標籤 | 含義 | 示例 |
|------|------|------|
| `account_id` | 租戶維度標籤 | `test-account`、`__unknown__`、`__overflow__` |
| `route` | HTTP 路由模板 | `/api/v1/search/find` |
| `method` | HTTP 方法 | `GET`、`POST` |
| `status` | 請求或階段狀態 | `200`、`ok`、`error` |
| `operation` | 操作名稱 | `search.find`、`resources.add_resource` |
| `context_type` | 檢索上下文型別 | `resource` |
| `provider` | 模型或外部服務提供方 | `volcengine` |
| `model_name` | 模型名稱 | `doubao-seed-1-8-251228` |
| `stage` | 階段標籤（按指標族定義） | 資源階段：`parse`；Token 歸因階段：`embed_query` |
| `valid` | 當前樣本是否為有效新鮮值 | `1` / `0` |

其中：

- `account_id` 只在受控白名單指標上啟用，避免高基數失控
- `valid=0` 表示該狀態/探針的當前樣本是失敗回退值或 stale fallback，不代表標籤本身錯誤
- `stage` 的語義依賴指標族：
  - `openviking_resource_stage_*`：資源匯入流水線階段（如 `parse/persist/process`）
  - `openviking_operation_tokens_total`：Token Attribution 的歸因階段（如 `embed_query/rerank/vlm`）

## 關鍵指標說明

下面的指標說明基於當前實際暴露的代表性指標輸出（整理自 `openviking/metrics/collectors/`）。

### 請求與操作

| 指標族 | 型別 | 常見標籤 | 含義 |
|--------|------|----------|------|
| `openviking_http_requests_total` | Counter | `account_id, method, route, status` | HTTP 請求總量 |
| `openviking_http_request_duration_seconds` | Histogram | `account_id, method, route, status` | HTTP 請求耗時分佈 |
| `openviking_http_inflight_requests` | Gauge | `account_id, route` | 當前 inflight 請求數（程序內近似值） |
| `openviking_operation_requests_total` | Counter | `account_id, operation, status` | 結構化操作總量 |
| `openviking_operation_duration_seconds` | Histogram | `account_id, operation, status` | 結構化操作耗時分佈 |

適用場景：

- 看 `/api/v1/search/find`、`/api/v1/resources` 是否異常變慢
- 看某個 `operation` 是否錯誤率升高

### 檢索與資源處理

| 指標族 | 型別 | 常見標籤 | 含義 |
|--------|------|----------|------|
| `openviking_retrieval_requests_total` | Counter | `account_id, context_type` | 檢索請求次數 |
| `openviking_retrieval_results_total` | Counter | `account_id, context_type` | 檢索返回結果數量累計 |
| `openviking_retrieval_latency_seconds` | Histogram | `account_id, context_type` | 檢索耗時分佈 |
| `openviking_retrieval_zero_result_total` | Counter | `account_id, context_type` | 檢索零結果次數 |
| `openviking_retrieval_rerank_used_total` | Counter | `account_id` | 檢索中使用 rerank 的次數 |
| `openviking_retrieval_rerank_fallback_total` | Counter | `account_id` | 檢索 rerank 回退次數 |
| `openviking_resource_stage_total` | Counter | `account_id, stage, status` | 資源匯入各階段執行次數 |
| `openviking_resource_stage_duration_seconds` | Histogram | `account_id, stage, status` | 資源匯入階段耗時分佈 |
| `openviking_resource_wait_duration_seconds` | Histogram | `account_id, operation` | 資源匯入等待耗時分佈（例如佇列等待） |

典型 `stage` 包括：

- `request`
- `parse`
- `summarize`
- `persist`
- `finalize`
- `process`

### 向量檢索、記憶與語義節點

| 指標族 | 型別 | 常見標籤 | 含義 |
|--------|------|----------|------|
| `openviking_vector_searches_total` | Counter | `operation` | 向量檢索次數 |
| `openviking_vector_scored_total` | Counter | `operation` | 向量候選打分數量累計 |
| `openviking_vector_passed_total` | Counter | `operation` | 向量候選通過數量累計 |
| `openviking_vector_returned_total` | Counter | `operation` | 向量候選返回數量累計 |
| `openviking_vector_scanned_total` | Counter | `operation` | 向量候選掃描數量累計 |
| `openviking_memory_extracted_total` | Counter | `operation`, `memory_type` | memory extracted 數量累計，按記憶 schema 型別拆分 |
| `openviking_semantic_nodes_total` | Counter | `status` | semantic nodes 數量累計 |

### 模型呼叫與 Token

| 指標族 | 型別 | 常見標籤 | 含義 |
|--------|------|----------|------|
| `openviking_model_calls_total` | Counter | `model_type, provider, model_name` | 模型呼叫總量（統一視角） |
| `openviking_model_tokens_total` | Counter | `model_type, provider, model_name, token_type` | 模型 token 累計量 |
| `openviking_vlm_calls_total` | Counter | `account_id, provider, model_name` | VLM 呼叫次數 |
| `openviking_vlm_tokens_input_total` | Counter | `account_id, provider, model_name` | VLM 輸入 token |
| `openviking_vlm_tokens_output_total` | Counter | `account_id, provider, model_name` | VLM 輸出 token |
| `openviking_vlm_tokens_total` | Counter | `account_id, provider, model_name` | VLM 總 token |
| `openviking_vlm_call_duration_seconds` | Histogram | `account_id, provider, model_name` | VLM 呼叫耗時分佈 |
| `openviking_embedding_requests_total` | Counter | `account_id, status` | embedding 請求數 |
| `openviking_embedding_latency_seconds` | Histogram | `account_id, status` | embedding 耗時分佈 |
| `openviking_embedding_errors_total` | Counter | `account_id, error_code` | embedding 錯誤次數 |
| `openviking_embedding_calls_total` | Counter | `account_id, provider, model_name` | embedding provider 呼叫次數（per-call） |
| `openviking_embedding_call_duration_seconds` | Histogram | `account_id, provider, model_name` | embedding provider 呼叫耗時分佈（per-call） |
| `openviking_embedding_tokens_input_total` | Counter | `account_id, provider, model_name` | embedding 輸入 token（per-call 聚合） |
| `openviking_embedding_tokens_output_total` | Counter | `account_id, provider, model_name` | embedding 輸出 token（per-call 聚合；若長期為 0 可能不出現） |
| `openviking_embedding_tokens_total` | Counter | `account_id, provider, model_name` | embedding 總 token（per-call 聚合） |
| `openviking_rerank_calls_total` | Counter | `account_id, provider, model_name` | rerank provider 呼叫次數（per-call） |
| `openviking_rerank_call_duration_seconds` | Histogram | `account_id, provider, model_name` | rerank provider 呼叫耗時分佈（per-call） |
| `openviking_rerank_tokens_input_total` | Counter | `account_id, provider, model_name` | rerank 輸入 token（per-call 聚合） |
| `openviking_rerank_tokens_output_total` | Counter | `account_id, provider, model_name` | rerank 輸出 token（per-call 聚合；若長期為 0 可能不出現） |
| `openviking_rerank_tokens_total` | Counter | `account_id, provider, model_name` | rerank 總 token（per-call 聚合） |
| `openviking_operation_tokens_total` | Counter | `account_id, operation, stage, token_type` | Operation Token 彙總（含 token attribution 歸因階段） |

說明：

- `openviking_model_*` 是統一模型視角，便於同時看 embedding / vlm
- `openviking_vlm_*` 和 `openviking_embedding_*` 更適合業務側針對性看板
  - `*_requests_*` 更偏“業務請求視角”
  - `*_calls_* / *_call_duration_* / *_tokens_*` 更偏“模型呼叫視角”（按 `provider/model_name` 聚合）
 - `openviking_operation_tokens_total` 不存 `token_type="all/total"` 這類預聚合標籤，總帳建議在 TSDB 查詢側用 `sum(...)` 聚合得到

### 佇列、鎖與系統執行態

| 指標族 | 型別 | 常見標籤 | 含義 |
|--------|------|----------|------|
| `openviking_queue_processed_total` | Counter | `queue` | 佇列累計處理量 |
| `openviking_queue_errors_total` | Counter | `queue` | 佇列累計錯誤量 |
| `openviking_queue_pending` | Gauge | `queue` | 佇列待處理數 |
| `openviking_queue_in_progress` | Gauge | `queue` | 佇列執行中數量 |
| `openviking_executor_max_workers` | Gauge | `pool, process_role, worker` | asyncio 預設 executor 最大 worker 數 |
| `openviking_executor_threads` | Gauge | `pool, process_role, worker` | asyncio 預設 executor 已建立執行緒數 |
| `openviking_executor_active_tasks` | Gauge | `pool, process_role, worker` | 預設 executor 當前執行中的任務數 |
| `openviking_executor_pending_tasks` | Gauge | `pool, process_role, worker` | 預設 executor 當前等待執行的任務數 |
| `openviking_executor_submitted_total` | Counter | `pool, process_role, worker` | 預設 executor 累計提交任務數 |
| `openviking_executor_completed_total` | Counter | `pool, process_role, worker` | 預設 executor 累計執行結束任務數，失敗也計入 |
| `openviking_executor_failed_total` | Counter | `pool, process_role, worker` | 預設 executor callable 拋異常次數 |
| `openviking_lock_active` | Gauge | 無 | 當前已釋出的鎖租約數 |
| `openviking_lock_waiting` | Gauge | 無 | 當前等待鎖的請求數 |
| `openviking_lock_stale` | Gauge | 無 | 累計已清理的過期鎖 token 數 |
| `openviking_lock_conflicts_total` | Counter | 無 | 累計鎖衝突次數 |
| `openviking_lock_stale_leases_released_total` | Counter | 無 | 已釋放的過期租約數 |
| `openviking_lock_descendant_scans_total` | Counter | 無 | 已完成的後代鎖掃描次數 |
| `openviking_lock_descendant_scan_duration_seconds_total` | Counter | 無 | 後代鎖掃描累計耗時 |

這些指標適合回答：

- 是否有佇列堆積？
- 是否有鎖競爭或 stale lock？
- 預設 executor 是否接近執行緒上限或出現排隊？

executor 指標只統計 `loop.run_in_executor(None, ...)` 和 `asyncio.to_thread(...)`。
顯式傳入自定義 executor 的呼叫、Rust / RAGFS 內部 runtime 或執行緒不計入。
`failed_total` 統計 callable 拋異常的次數。如果異常被上層捕獲並作為正常分支處理，
也會計入該指標，因此它不等同於業務請求失敗數。


### RAGFS

RAGFS 通過一次原生 `metrics()` 呼叫讀取檔案系統、Cache、multi-backend
和 Lock 指標。Collector 直接覆蓋 Registry 當前值，不計算差分。
內部以整數納秒取樣，匯出為小數秒，例如 `123 ns = 0.000000123 seconds`。

| 指標族 | 型別 | 常見標籤 | 含義 |
|--------|------|----------|------|
| `openviking_ragfs_operation_results_total` | Counter | `plugin, operation, status` | 操作成功和失敗次數 |
| `openviking_ragfs_operation_duration_seconds` | Histogram | `plugin, operation` | 操作耗時分佈 |
| `openviking_ragfs_cache_requests_total` | Counter | `kind, result` | 檔案和目錄快取命中、未命中次數 |
| `openviking_ragfs_cache_backend_fallbacks_total` | Counter | 無 | 快取未命中後的後端讀取次數 |
| `openviking_ragfs_cache_operations_total` | Counter | `operation` | 快取 put/delete 嘗試次數 |
| `openviking_ragfs_cache_invalidations_total` | Counter | 無 | 已完成的快取失效次數 |
| `openviking_ragfs_cache_errors_total` | Counter | 無 | 旁路模式下忽略的快取錯誤數 |
| `openviking_ragfs_cache_policy_bypasses_total` | Counter | 無 | 繞過快取的讀取次數 |
| `openviking_ragfs_cache_bytes_total` | Counter | `source` | 來自後端和快取的位元組數 |
| `openviking_ragfs_cache_operation_duration_seconds_total` | Counter | `operation` | get/put/delete 累計耗時 |
| `openviking_ragfs_cache_inflight_events_total` | Counter | `event` | leader/follower/backend_saved 次數 |
| `openviking_ragfs_multiwrite_background_tasks` | Gauge | 無 | 後臺任務數，包含重試迴圈 |
| `openviking_ragfs_multiwrite_read_routes_total` | Counter | `route` | primary/backup/redirect/miss 路由選擇次數 |

這些指標不帶 `mount` 和 `account_id` 標籤。未啟用 Cache 或 multi-backend
時，不生成對應指標族。`status` 為 `success` 或 `error`。
`exists=false` 計為成功；`replace` 使用 `rename` 操作標籤。
Histogram 包含全部操作結果，有限桶邊界範圍為 0.0001 至 10 秒。
Python `get_stats()` 保留原有微秒字段。

### 任務與 Task Tracker

| 指標族 | 型別 | 常見標籤 | 含義 |
|--------|------|----------|------|
| `openviking_task_pending` | Gauge | `task_type` | task tracker 待執行任務數 |
| `openviking_task_running` | Gauge | `task_type` | task tracker 執行中任務數 |
| `openviking_task_completed` | Gauge | `task_type` | task tracker 已完成任務數 |
| `openviking_task_failed` | Gauge | `task_type` | task tracker 失敗任務數 |

### Cache

| 指標族 | 型別 | 常見標籤 | 含義 |
|--------|------|----------|------|
| `openviking_cache_hits_total` | Counter | `level` | Cache 命中次數 |
| `openviking_cache_misses_total` | Counter | `level` | Cache 未命中次數 |

### Session

| 指標族 | 型別 | 常見標籤 | 含義 |
|--------|------|----------|------|
| `openviking_session_lifecycle_total` | Counter | `account_id, action, status` | session 生命週期事件次數 |
| `openviking_session_archive_total` | Counter | `account_id, status` | session archive 次數 |

### Feedback

這組 feedback 指標會在 scrape 時對持久化的 VikingBot session 檔案進行聚合，彙總反饋事件與 outcome 資料。它們以 gauge 形式匯出，因為 collector 每次都會重新計算當前聚合快照，而不是線上持續累加 counter。

| 指標族 | 型別 | 常見標籤 | 含義 |
|--------|------|----------|------|
| `openviking_feedback_sessions_scanned_total` | Gauge | `valid` | 當前快照掃描到的 bot session 數量 |
| `openviking_feedback_responses_total` | Gauge | `valid` | 當前快照納入統計的 assistant response 總數，包含尚未接入新觀測契約的歷史 response |
| `openviking_feedback_tracked_responses_total` | Gauge | `valid` | 已被當前 feedback 觀測契約覆蓋的 response 總數（來自 `metadata.feedback_events` 或 `metadata.response_outcomes`） |
| `openviking_feedback_responses_with_feedback_total` | Gauge | `valid` | 至少帶有一個顯式反饋事件的 response 數量 |
| `openviking_feedback_events_total` | Gauge | `valid` | 顯式反饋事件總數 |
| `openviking_feedback_thumb_up_total` | Gauge | `valid` | thumb-up 事件數 |
| `openviking_feedback_thumb_down_total` | Gauge | `valid` | thumb-down 事件數 |
| `openviking_feedback_positive_outcomes_total` | Gauge | `valid` | 被歸類為 positive outcome 的 response 數量 |
| `openviking_feedback_negative_outcomes_total` | Gauge | `valid` | 被歸類為 negative outcome 的 response 數量 |
| `openviking_feedback_reasked_outcomes_total` | Gauge | `valid` | 被歸類為 reask outcome 的 response 數量 |
| `openviking_feedback_resolved_outcomes_total` | Gauge | `valid` | 被歸類為 resolved outcome 的 response 數量 |
| `openviking_feedback_follow_up_without_feedback_outcomes_total` | Gauge | `valid` | 有 follow-up 但沒有顯式反饋的 outcome 數量 |
| `openviking_feedback_coverage` | Gauge | `valid` | 已跟蹤 response 中帶顯式反饋的佔比 |
| `openviking_feedback_thumbs_up_rate` | Gauge | `valid` | feedback event 中 thumb-up 的佔比 |
| `openviking_feedback_thumbs_down_rate` | Gauge | `valid` | feedback event 中 thumb-down 的佔比 |
| `openviking_feedback_positive_feedback_rate` | Gauge | `valid` | 已跟蹤 response 中 positive feedback outcome 的佔比 |
| `openviking_feedback_negative_feedback_rate` | Gauge | `valid` | 已跟蹤 response 中 negative feedback outcome 的佔比 |
| `openviking_feedback_reask_rate` | Gauge | `valid` | 已跟蹤 response 中導致 reask 的佔比 |
| `openviking_feedback_one_turn_resolution_rate` | Gauge | `valid` | 已跟蹤 response 中一輪解決的佔比 |
| `openviking_feedback_channel_*` | Gauge | `channel, valid` | 按 channel 細分的 response 數量、feedback 數量、negative outcome、reask、coverage、thumb rate 與 one-turn resolution |

對於新舊歷史資料混合的場景，rate 類圖表應優先結合 `openviking_feedback_tracked_responses_total` 理解分母。`openviking_feedback_responses_total` 仍然保留，用於觀察包含歷史遺留 response 在內的整體 assistant 響應體量。

適用場景：

- 在 Grafana 中繪製 feedback coverage、thumbs-down rate、one-turn resolution rate 的時間趨勢
- 對比不同 channel（如 `cli__default`、`bot_api__demo`）之間的反饋質量差異
- 當 `valid="0"` 持續出現時告警，表示 collector 在重新整理失敗後回退到了上一次成功快照

PromQL / Grafana 示例：

- 總體 feedback coverage：

```promql
openviking_feedback_coverage{valid="1"}
```

- 總體 thumbs-down rate：

```promql
openviking_feedback_thumbs_down_rate{valid="1"}
```

- 總體 one-turn resolution rate：

```promql
openviking_feedback_one_turn_resolution_rate{valid="1"}
```

- 按 channel 對比 coverage 與 resolution：

```promql
openviking_feedback_channel_coverage{valid="1"}
```

```promql
openviking_feedback_channel_one_turn_resolution_rate{valid="1"}
```

- 檢查 stale / fallback snapshot：

```promql
max by (job) (openviking_feedback_events_total{valid="0"})
```

因為這些指標本質上是 scrape-time snapshot gauge，所以很適合直接做 Grafana 時間序列面板，以及按 channel 並排對比的視覺化。

關於 `/metrics` 端點行為與抓取方式，可參見 [Metrics API](../api/09-metrics.md)。

### 探針與健康狀態

| 指標族 | 型別 | 常見標籤 | 含義 |
|--------|------|----------|------|
| `openviking_service_readiness` | Gauge | 可含 `valid` | 服務主 readiness |
| `openviking_api_key_manager_readiness` | Gauge | 可含 `valid` | API Key Manager readiness |
| `openviking_storage_readiness` | Gauge | `probe, valid` | 儲存探針，例如 `agfs` |
| `openviking_model_provider_readiness` | Gauge | `provider, valid` | 模型提供方 readiness |
| `openviking_async_system_readiness` | Gauge | `probe, valid` | 非同步系統 readiness |
| `openviking_retrieval_backend_readiness` | Gauge | `probe, valid` | 檢索後端 readiness |
| `openviking_encryption_component_health` | Gauge | `valid` | 加密元件總體健康 |
| `openviking_encryption_root_key_ready` | Gauge | `valid` | 根金鑰是否就緒 |
| `openviking_encryption_kms_provider_ready` | Gauge | `provider, valid` | KMS provider readiness |

`valid` 的意義：

- `valid="1"`：當前樣本是本次成功重新整理得到的結果
- `valid="0"`：當前樣本是失敗回退值或 stale fallback，說明該探針/狀態當前不可完全信任

### 加密（執行指標）

| 指標族 | 型別 | 常見標籤 | 含義 |
|--------|------|----------|------|
| `openviking_encryption_operations_total` | Counter | `account_id, operation, status` | encrypt/decrypt 操作次數 |
| `openviking_encryption_duration_seconds` | Histogram | `account_id, operation, status` | encrypt/decrypt 耗時分佈 |
| `openviking_encryption_bytes_total` | Counter | `account_id, operation` | encrypt/decrypt 處理位元組數累計 |
| `openviking_encryption_payload_size_bytes` | Histogram | `account_id, operation` | encrypt/decrypt payload size 分佈 |
| `openviking_encryption_auth_failed_total` | Counter | `account_id, status` | auth failed 次數 |
| `openviking_encryption_key_derivation_total` | Counter | `account_id, status` | key derivation 次數 |
| `openviking_encryption_key_derivation_duration_seconds` | Histogram | `account_id, status` | key derivation 耗時分佈 |
| `openviking_encryption_key_load_duration_seconds` | Histogram | `account_id, status, provider` | key load 耗時分佈 |
| `openviking_encryption_key_cache_hits_total` | Counter | `account_id, provider` | key cache hits 次數 |
| `openviking_encryption_key_cache_misses_total` | Counter | `account_id, provider` | key cache misses 次數 |
| `openviking_encryption_key_version_usage_total` | Counter | `account_id, key_version` | key version 使用次數 |

### 元件與 Observer 聚合指標

| 指標族 | 型別 | 常見標籤 | 含義 |
|--------|------|----------|------|
| `openviking_component_health` | Gauge | `component, valid` | 元件健康狀態 |
| `openviking_component_errors` | Gauge | `component, valid` | 元件錯誤狀態 |
| `openviking_observer_components_total` | Gauge | `valid` | observer 觀測到的元件數量 |
| `openviking_observer_components_unhealthy` | Gauge | `valid` | 不健康元件數量 |
| `openviking_observer_components_with_errors` | Gauge | `valid` | 有錯誤元件數量 |

典型 `component` 包括：

- `queue`
- `models`
- `lock`
- `retrieval`
- `vikingdb`
- `filesystem`

### VikingDB 與模型使用統計

| 指標族 | 型別 | 常見標籤 | 含義 |
|--------|------|----------|------|
| `openviking_vikingdb_collection_health` | Gauge | `collection, valid` | collection 健康狀態 |
| `openviking_vikingdb_collection_vectors` | Gauge | `collection, valid` | collection 當前向量數 |
| `openviking_model_usage_available` | Gauge | `model_type, valid` | 模型使用統計是否可用 |

其中 `model_type` 可能包括：

- `vlm`
- `embedding`
- `rerank`

## 配置示例

### 啟用 Metrics

在 `ov.conf` 中，可以通過 `server.observability.metrics` 顯式啟用 metrics 子系統：

```json
{
  "server": {
    "observability": {
      "metrics": {
        "enabled": true,
        "account_dimension": {
          "enabled": true,
          "max_active_accounts": 100,
          "metric_allowlist": [
            "openviking_http_requests_total",
            "openviking_http_request_duration_seconds",
            "openviking_http_inflight_requests",
            "openviking_operation_requests_total",
            "openviking_operation_duration_seconds",
            "openviking_vlm_calls_total",
            "openviking_vlm_call_duration_seconds",
            "openviking_rerank_*"
          ]
        }
      }
    }
  }
}
```

推薦理解方式：

- `server.observability.metrics.enabled`：指標體系總開關
- `server.observability.metrics.account_dimension`：控制 `account_id` 標籤是否啟用以及啟用範圍

### Exporters 配置

預設情況下，Business Data Platform 會通過 Prometheus exposition 格式在 `/metrics` 輸出指標。
如果希望在保留 `/metrics` 的同時把同一份程序內指標匯出到 OTLP 後端，可以在 `server.observability.metrics.exporters` 下啟用 exporter。

關鍵欄位：

- `server.observability.metrics.exporters.prometheus.enabled`：是否啟用 Prometheus exporter（提供 `/metrics`）
- `server.observability.metrics.exporters.otel.enabled`：是否啟用 OTLP 匯出（複用同一份 registry）
- `server.observability.metrics.exporters.otel.protocol`：`"grpc"` 或 `"http"`
- `server.observability.metrics.exporters.otel.tls.insecure`：僅對 OTLP/gRPC 生效；`true` 表示明文連線（無 TLS）
- `server.observability.metrics.exporters.otel.endpoint`：OTLP 端點（gRPC 用 `host:4317`；HTTP 必須是完整 URL）
- `server.observability.metrics.exporters.otel.service_name`：OTLP `service.name` 資源屬性（預設 `"openviking-server"`）
- `server.observability.metrics.exporters.otel.export_interval_ms`：OTLP 推送間隔，單位毫秒（預設 `10000`）
- `server.observability.metrics.exporters.otel.headers`：可選的自定義 OTLP 請求頭；gRPC 會作為 metadata 傳送，HTTP 會作為 headers 傳送
- 使用 gRPC 時，`headers` 中的 key 需要使用小寫形式，例如 `x-byteapm-appkey`；HTTP 不受該限制

示例：

```json
{
  "server": {
    "observability": {
      "metrics": {
        "enabled": true,
        "exporters": {
          "prometheus": {
            "enabled": true
          },
          "otel": {
            "enabled": true,
            "protocol": "grpc",
            "tls": {
              "insecure": true
            },
            "endpoint": "otel-collector:4317",
            "service_name": "openviking-server",
            "export_interval_ms": 10000,
            "headers": {}
          }
        }
      }
    }
  }
}
```

### `account_id` 標籤的使用建議

- 預設開啟，但僅對白名單指標啟用（`metric_allowlist` 為空時仍會輸出為 `__unknown__`）
- 不要把 `user_id`、`session_id`、`resource_uri` 這類高基數字段做成標籤
- 對於看板和告警，只對少量關鍵指標族開啟租戶維度
- `metric_allowlist` 支援有限萬用字元：僅支援**末尾 `*` 的字首匹配**（例如 `openviking_rerank_*`、`openviking_embedding_*`）
- 不支援單獨的 `*`（空字首），也不支援中間通配、完整 glob 或正則


## 相關文件

- [架構概述](./01-architecture.md) - Business Data Platform 總體架構
- [多租戶](./11-multi-tenant.md) - `account/user/peer` 隔離模型
- [資料加密](./10-encryption.md) - 儲存層加密與隔離
- [Metrics API](../api/09-metrics.md) - `/metrics` 端點用法
- [VikingBot 問答效果反饋觀測方案設計](https://github.com/volcengine/OpenViking/blob/main/bot/docs/zh/design/vikingbot-feedback-observability-design.md) - feedback 指標與階段性落地背景
- [指標體系設計](../../design/metric-design.md) - 指標體系設計細節
