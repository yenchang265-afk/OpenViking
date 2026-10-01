# OpenViking Vector Backend 性能 Benchmark

這個 benchmark 用來快速驗收新的 VectorDB storage backend 在 OpenViking 場景下的表現。
它不直接呼叫 `CollectionAdapter`，而是走 `VikingVectorIndexBackend`：

- 建表使用 `CollectionSchemas.context_collection`
- 寫入使用 `VikingVectorIndexBackend.upsert_many(..., ctx=...)`
- 查詢使用 `VikingVectorIndexBackend.search_in_tenant(...)`
- 目錄範圍使用 `target_directories`，內部會編譯成 `PathScope("uri", ..., depth=-1)`

它仍然不經過 OpenViking Server、AGFS、embedding 服務和 rerank；向量直接來自模擬資料或
dir-vector-dataset 的 `.fvecs` 文件。

## 先選模式

| 模式 | 引數 | 資料來源 | 適合場景 |
| --- | --- | --- | --- |
| 模擬資料 | `--workload synthetic` | runner 生成向量和目錄路徑 | 新 storage backend 首次接入、穩定復現、CI smoke |
| 真實資料 | `--workload dir-vector` | dir-vector-dataset 的 metadata、fvecs、ground truth | 目錄過濾 + 向量檢索的真實 workload 驗收 |

預設是 `synthetic`。

## 再選規模

| 規模 | 引數 | synthetic 行為 | dir-vector 行為 |
| --- | --- | --- | --- |
| 少量 smoke | `--profile smoke` | 生成 128 行、8 個 query | 抽樣前 128 行、前 8 個 query |
| 常規 standard | `--profile standard` | 生成 10000 行、100 個 query | 抽樣前 10000 行、前 100 個 query |
| 壓力 stress | `--profile stress` | 生成 100000 行、500 個 query | 抽樣前 100000 行、前 500 個 query |
| 全量真實資料 | `--workload dir-vector --full` | 不適用 | 讀取 dataset 全量 corpus 和 query |

`--rows`、`--queries`、`--batch-size`、`--concurrency`、`--top-k` 可以覆蓋 profile 預設值。
`--full` 只對 `dir-vector` 生效；真實資料的向量維度從 `.fvecs` 讀取，`--dim` 隻影響 synthetic。

## 再選讀寫階段

| 階段模式 | 引數 | 行為 |
| --- | --- | --- |
| 讀寫一體 | `--mode read-write` | 預設模式；建立 collection、寫入 OV context row，然後跑 count/get/search |
| 只寫不讀 | `--mode write-only` | 建立 collection 並 upsert；不跑 count、get、向量檢索、過濾檢索 |
| 只讀不寫 | `--mode read-only` | 不建立 collection、不 upsert；直接連線同名 collection 跑 count/get/search |

`read-only` 用於壓測一個已經準備好的 collection。它必須和寫入階段使用相同的 `--config`、
配置裡的 `vectordb.name`、`--run-id`、`--workload`、`--dataset` / `--full` / 抽樣引數和
`--distance`，否則 runner 可能連到不同 collection，或用不同 query/ground truth 口徑算報告。

`read-only` 不允許 `--drop-at-end`。如果想先準備資料再反覆測讀效能，先固定 `--run-id` 跑一次
`write-only`，後續用同一個 `--run-id` 跑 `read-only`。

## 快速開始

先準備一個 `ov.conf`，最小本地配置如下：

```json
{
  "storage": {
    "workspace": "./benchmark/results/vectordb_perf/local_data",
    "vectordb": {
      "backend": "local",
      "name": "vectordb_perf",
      "project": "default",
      "index_name": "default",
      "distance_metric": "cosine"
    }
  }
}
```

模擬資料少量 smoke：

```bash
.venv/bin/python -m benchmark.vectordb_perf.run \
  --config ./ov.conf \
  --workload synthetic \
  --profile smoke
```

模擬資料常規 benchmark：

```bash
.venv/bin/python -m benchmark.vectordb_perf.run \
  --config ./ov.conf \
  --workload synthetic \
  --profile standard
```

真實資料必須先下載。`--workload dir-vector` 預設會跑 `wiki` 和 `arxiv` 兩個真實資料集，
runner 不會自動下載資料，也不會從 GitHub clone 後直接生成 `.fvecs`。先到
dir-vector-dataset 倉庫 README 的 File Download 連結下載這兩組資料檔案：

https://github.com/KurtPatrickHere/dir-vector-dataset

下載後把檔案解壓或移動到同一個本地目錄，例如：

```bash
mkdir -p benchmark/data/dir-vector-dataset-files
# 把下載得到的 corpus/query/vector/ground-truth 檔案放進這個目錄
```

`--dataset-root` 必須指向“直接包含資料檔案”的目錄，不是 GitHub repo 目錄，也不是一個空目錄。
runner 會先校驗 `wiki` 和 `arxiv` 所需檔案；缺檔案時會直接列出 missing files 和下載地址。
除錯時可以用 `--dataset wiki` 或 `--dataset arxiv` 只跑單個數據集。各 dataset 對應檔案見下方“真實資料檔案”。

真實資料少量抽樣（Wiki 公開檔案）：

```bash
.venv/bin/python -m benchmark.vectordb_perf.run \
  --config ./ov.conf \
  --workload dir-vector \
  --dataset wiki \
  --dataset-root benchmark/data/dir-vector-dataset-files \
  --dir-vector-query-scope derived_gt_lca_v1 \
  --profile smoke
```

WIKI-Dir 的 corpus 目錄來自單獨釋出的 `dbpedia_dir_2m_corpus_paths.json`，runner 會按
`id` 將它與 corpus metadata 和 fvecs 逐行對齊，並在錯位或缺行時直接報錯。這個檔案約
600 MB，runner 使用流式解析，不會把全部 mapping 一次性載入到記憶體。

當前公開的 Wiki query metadata 沒有包含目錄 constraint，因此預設的 `dataset` 口徑會拒絕
把所有 query 靜默當成根目錄查詢。若要對公開檔案做目錄過濾的診斷性測試，可以顯式使用
`derived_gt_lca_v1`：對每個 query 的最高 relevance ground-truth 文件取目錄最長公共字首，
並跳過只能得到根目錄的 query。這個口徑使用了 ground truth，不代表釋出資料集的官方 query
分佈，也不能用來宣告官方 Directory recall。該選項只改變 Wiki；在 `--dataset all` 中，
其他 dataset 保持現有 loader 行為。

真實資料全量（公開 Wiki 檔案的診斷性目錄口徑）：

```bash
.venv/bin/python -m benchmark.vectordb_perf.run \
  --config ./ov.conf \
  --workload dir-vector \
  --dataset wiki \
  --dataset-root ./benchmark/data/dir-vector-dataset-files \
  --dir-vector-query-scope derived_gt_lca_v1 \
  --full
```

預設保留測試 collection，方便複查。需要執行後清理：

```bash
--drop-at-end
```

runner 會把配置裡的 `name` 改成 `<name>_bench_<run-id>`，避免覆蓋正式 collection。

分離寫入和讀取時要固定 `--run-id`。例如先寫入：

```bash
.venv/bin/python -m benchmark.vectordb_perf.run \
  --config ./ov.conf \
  --workload dir-vector \
  --dataset wiki \
  --dataset-root ./benchmark/data/dir-vector-dataset-files \
  --dir-vector-query-scope derived_gt_lca_v1 \
  --full \
  --run-id ovbench_full_001 \
  --mode write-only
```

再只跑讀取和檢索：

```bash
.venv/bin/python -m benchmark.vectordb_perf.run \
  --config ./ov.conf \
  --workload dir-vector \
  --dataset wiki \
  --dataset-root ./benchmark/data/dir-vector-dataset-files \
  --dir-vector-query-scope derived_gt_lca_v1 \
  --full \
  --run-id ovbench_full_001 \
  --mode read-only \
  --output-dir benchmark/results/vectordb_perf/ovbench_full_001_read
```

## 寫入資料結構

兩種 workload 最終都會轉換成 OV context row，寫入欄位如下：

| 欄位 | 示例 | 說明 |
| --- | --- | --- |
| `id` | `syn-1` | 主鍵；真實資料使用原始 doc id |
| `uri` | `viking://resources/bench/synthetic/d0_1/d1_0/syn-1` | OV URI；目錄過濾只看這個欄位 |
| `type` | `file` | OV context type 內的資源型別 |
| `context_type` | `resource` | 固定按資源檢索 |
| `vector` | `[0.1, ...]` | dense vector；synthetic 生成，dir-vector 讀取 `.fvecs` |
| `created_at` / `updated_at` | `2026-01-01T00:00:01Z` | 確定性時間戳 |
| `active_count` | `0` | OV 訪問計數 |
| `level` | `2` | L2 detail/content 層；查詢也限制 `level=[2]` |
| `name` | `syn-1` | 展示名 |
| `description` / `tags` / `search_tags` | `cat_1` | 標量欄位 |
| `abstract` | `source_id:syn-1 category:cat_1` | 檢索返回欄位，也用於 ground truth 輕量匹配 |
| `content` | `benchmark content ...` | text 欄位，匹配真實 OV schema |
| `account_id` | `bench_account` | 用於 backend tenant filter |
| `owner_user_id` | `bench_user` | OV owner 字段 |

所以這個 benchmark 不是“普通向量庫 row + filter”，而是 OV 的 context collection row。

## 測試階段

每次執行會建立一個帶 run id 字尾的測試 collection，然後執行：

| 階段 | 內容 |
| --- | --- |
| `setup` | 建立 collection 和索引 schema |
| `ingest` | 通過 backend upsert OV context row |
| `prepare` | Auto background 模式等待最終 derived GPU index ready；不計入 search QPS |
| `validate` | count、get、過濾 count |
| `vector_search` | `search_in_tenant`，無指定目錄 |
| `filtered_vector_search` | `search_in_tenant`，帶 `target_directories` |
| `cleanup` | 僅在傳 `--drop-at-end` 時刪除測試 collection |

功能錯誤會導致非零退出碼；效能慢只記錄到報告裡。

`ingest` 會把每個 `--batch-size` 分組通過一次 backend `upsert_many` 呼叫寫入，
而不是逐行呼叫 `upsert`。對本地後端，這會把每批記錄合併到一次 store 持久化操作；
store 與 vector index 之間不提供跨元件事務。遠端 adapter 還可根據請求上限進一步拆批，
因此一次 `upsert_many` 也不代表一個遠端請求或跨子批事務。批次介面只提供完整記錄
upsert；需要保留未提供欄位的 partial update 仍使用單條 `upsert`。runner 會在整個多批
ingest 外層使用 `bulk_ingest` maintenance scope：native index 和資料持久化仍逐批更新，
但 Auto background cuVS rebuild 會延遲到最外層 scope 退出後再合併觸發一次。這個 scope
不是事務或原子性邊界，退出時只調度 rebuild，本身不等待 GPU ready。正式計時 search 前，
runner 還會顯式等待該最終 GPU snapshot ready；
readiness wait 單獨記錄為 `prepare/wait_for_auto_derived_index`，失敗時不會繼續產出可能混合
CPU fallback 的 search QPS。當前 runner 是這些批次介面在倉庫內的首個呼叫方；本改動不
自動改變現有 embedding、migration 或 ovpack 寫入流程。

`--mode write-only` 只會出現 `setup` / `ingest` / 可選 `cleanup` 階段。
`--mode read-only` 不執行 `setup` / `ingest`；Auto background 配置下會先出現 `prepare`，
隨後執行 `validate` / `vector_search` / `filtered_vector_search`。
執行中會向 stderr 輸出進度，包括當前 collection、寫入條數、查詢條數和速率。

進度輸出示例：

```text
[vectordb_perf] start run_id=ovbench_full_001 workload=dir-vector:wiki mode=write-only records=1941679 base_queries=456 directory_queries=217 dim=1024
[vectordb_perf] collection=vectordb_perf_bench_ovbench_full_001_wiki
[vectordb_perf] setup: create collection
[vectordb_perf] setup: collection ready
[vectordb_perf] ingest: start batch_size=1000
[vectordb_perf] ingest: 120000/1941679 (6.2%), 3950.4/s
[vectordb_perf] ingest: 240000/1941679 (12.4%), 4021.7/s
```

## 真實資料檔案

`--workload dir-vector` 使用
[KurtPatrickHere/dir-vector-dataset](https://github.com/KurtPatrickHere/dir-vector-dataset)
釋出的資料檔案。需要先手動下載；下載入口在該倉庫 README 的 File Download / Google Drive
連結裡。

預設真實資料 benchmark 會跑 `wiki` 和 `arxiv` 兩行。`arxiv_category` 不在預設兩資料集裡，
需要時顯式傳 `--dataset arxiv_category`。

預設兩個真實資料集的全量規模如下，行數按 `.fvecs` 檔案統計，也是 runner 的實際讀取口徑：

| `--dataset` | corpus 向量條數 | query 條數 | 向量維度 |
| --- | ---: | ---: | ---: |
| `wiki` | 1,941,679 | 456 | 1024 |
| `arxiv` | 2,763,543 | 1,000 | 1024 |

`--dataset all --full` 會依次跑這兩組資料，合計 4,705,222 條 corpus 向量和 1,456 個 query。

| `--dataset` | 期望文件 |
| --- | --- |
| `wiki` | `dbpedia_dir_2m_corpus.jsonl`、`dbpedia_dir_2m_corpus_paths.json`、`dbpedia_dir_2m_corpus_vectors.fvecs`、`dbpedia_dir_2m_query.jsonl`、`dbpedia_dir_2m_query_vectors.fvecs`、`dbpedia_dir_2m_groundtruth.tsv` |
| `arxiv` | `arxiv_corpus_metadata.json`、`arxiv_corpus_vectors.fvecs`、`arxiv_query_constraint.json`、`arxiv_query_vectors.fvecs`、`arxiv_ground_truth.txt` |
| `arxiv_category` | `arxiv_corpus_metadata.json`、`arxiv_corpus_vectors.fvecs`、`arxiv_category_query_constraint.json`、`arxiv_category_query_vectors.fvecs`、`arxiv_category_ground_truth.txt` |

把這些檔案放到同一個目錄，然後用 `--dataset-root` 指向該目錄。

## 其他 ov.conf 示例

Volcengine VikingDB：

```json
{
  "storage": {
    "vectordb": {
      "backend": "volcengine",
      "name": "vectordb_perf",
      "project": "default",
      "index_name": "default",
      "distance_metric": "cosine",
      "volcengine": {
        "region": "cn-beijing",
        "ak": "YOUR_AK",
        "sk": "YOUR_SK"
      }
    }
  }
}
```

自定義 adapter 類：

```json
{
  "storage": {
    "vectordb": {
      "backend": "my_project.adapters.MyCollectionAdapter",
      "name": "vectordb_perf",
      "project": "default",
      "index_name": "default",
      "custom_params": {
        "endpoint": "http://127.0.0.1:9000",
        "token": "YOUR_TOKEN"
      }
    }
  }
}
```

## 常用引數

| 引數 | 說明 |
| --- | --- |
| `--config` | OpenViking 配置檔案路徑 |
| `--output-dir` | 報告輸出目錄；預設在 `benchmark/results/vectordb_perf/<run-id>/` |
| `--run-id` | 本次執行標識；會進入 collection 名和報告 |
| `--profile` | `smoke`、`standard`、`stress` |
| `--mode` | `read-write`、`write-only`、`read-only`；預設 `read-write` |
| `--workload` | `synthetic` 或 `dir-vector` |
| `--dataset-root` | dir-vector 資料目錄 |
| `--dataset` | `all`、`wiki`、`arxiv`、`arxiv_category`；預設 `all`，即依次跑 `wiki` 和 `arxiv` |
| `--full` | dir-vector 全量讀取 corpus 和 query；不加時按 `--rows` / `--queries` 抽樣 |
| `--rows` | synthetic 行數；dir-vector 抽樣行數 |
| `--queries` | 查詢數 |
| `--dim` | synthetic 向量維度 |
| `--batch-size` | 每次 backend `upsert_many` 呼叫的記錄數；遠端 adapter 可按請求上限再拆分 |
| `--concurrency` | 查詢併發 |
| `--top-k` | 檢索返回條數 |
| `--dir-vector-query-scope` | dir-vector 目錄 query 來源；預設 `dataset`，Wiki 公開檔案可顯式使用診斷口徑 `derived_gt_lca_v1` |
| `--distance` | `ip`、`l2`、`cosine` |
| `--drop-at-end` | 執行結束後刪除測試 collection |

## 報告輸出

主要輸出檔案：

| 檔案 | 內容 |
| --- | --- |
| `summary_zh.md` | 中文摘要，優先看這個；包含資料規模、Recall@K、QPS、延遲和環境 |
| `run_summary.json` | 彙總結果，適合自動化讀取；包含 `workload`、`quality`、`phase_summary` |
| `events.jsonl` | 每次操作的延遲、成功狀態和錯誤 |
| `phase_summary.csv` | 按階段聚合的吞吐和延遲 |
| `environment.json` | runner 本機環境觀測 |
| `run_config.json` | 本次執行引數 |

`summary_zh.md` 裡重點看兩張表：

| 表 | 內容 |
| --- | --- |
| 資料規模 | `records` 是本次計劃讀取的資料條數，`inserted` 是實際寫入 backend 的條數，`queries` 是實際查詢數 |
| 召回與 QPS | `vector_search` 和 `filtered_vector_search` 的 QPS、平均延遲、P95 延遲、gt_recall@K |

gt_recall@K 按 query 的 ground truth 命中率統計。全量 Wiki 的無過濾 `vector_search` 保留
`official_full` 標記；其 `filtered_vector_search` 在診斷模式下標為 `derived_gt_lca_v1`。
非 `--full` 會標成 `sampled_subset`。派生目錄和抽樣口徑只用於診斷，不代表官方 Directory
recall。

## 資源限制口徑

runner 會記錄本機 CPU、記憶體、平臺、GPU 探測和 cgroup 資訊，但不主動限制資源。
如果 backend 連線的是遠端服務，遠端例項規格需要人工記錄或用部署系統控制。

本地要控制資源，建議在 Docker、cgroup 或 CI runner 層限制 CPU/記憶體，然後把報告裡的
`environment.json` 和部署規格一起歸檔。
