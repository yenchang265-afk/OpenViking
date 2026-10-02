# OpenViking cuVS benchmark plan

相關文件：[整合計劃](./openviking-cuvs-integration-plan.md)、
[初步結果](../../benchmark/cuvs/PRELIMINARY_RESULTS.md)。

## 目標

本 benchmark 不追求單個“最高 QPS”數字，而是回答四個對整合決策更有用的問題：

1. 在精確檢索下，cuVS brute-force 相比 OpenViking native flat 的延遲和吞吐拐點在哪裡？
2. 在相同 Recall@K 下，CAGRA 能提供多少延遲、吞吐和容量收益？
3. 標量過濾、Python 呼叫和記錄回表後，GPU 優勢還剩多少？
4. 當前延遲重建策略對冷啟動和寫後首查造成多大代價？

cuVS 官方建議從 build time、search quality 和 search performance 三個維度比較向量索引；
本方案沿用這個原則，並增加 OpenViking 整合層與 mutation lifecycle 的測量。

參考：

- [cuVS: comparing vector search index performance](https://docs.rapids.ai/api/cuvs/stable/getting_started/)
- [cuVS Bench](https://docs.rapids.ai/api/cuvs/stable/cuvs_bench/)

## 被測後端

| 名稱 | OpenViking 配置 | 作用 |
| --- | --- | --- |
| Native exact | `backend=local`, `IndexType=flat` | CPU flat 基線；精確性相對於其實際儲存表示定義 |
| cuVS exact | `backend=cuvs`, `algorithm=brute_force` | GPU 在配置的 device dtype（預設 float32，可顯式選擇 float16）表示上的精確檢索 |
| cuVS ANN | `backend=cuvs`, `algorithm=cagra` | 在固定 Recall@K 下比較 ANN 效能 |

可以使用 `cuvs-bench` 的 HNSWlib 或其他演算法作為演算法級參考，但不能把它們當作
OpenViking 端到端基線，因為它們沒有經過相同的過濾、label mapping 和記錄回表路徑。

### Dtype 與非侵入性原則

cuVS 是 opt-in dense-search sidecar，不修改預設 backend，也不改變 native CPU
索引的預設 `int8` 量化。cuVS host shadow 儲存預處理後的 Python 浮點值；僅在建立
device dataset 和 query 時將它們 cast 為配置的 `dtype`，預設是 float32，也可以
顯式選擇 float16。因此：

- L1 index-only harness 在隔離 kernel 時顯式鎖定 float32 CPU / float32 GPU；評估低精度
  frontier 時另跑配置為 float16 的 cuVS，並相對於 exact reference 報告 Recall@K；
- L2/L3 保留真實應用行為，即 native int8 / cuVS 配置的 device dtype，並同時報告實際
  dtype、Recall@K 和記憶體佔用；
- L2/L3 不能表述為等 dtype、等記憶體或完全相同數值語義的比較；
- native fallback 始終繼續使用原有 int8 CPU index，啟用 cuVS 不觸發遷移或重寫。

低精度 GPU 路線作為顯式配置分開評估：使用 `dtype=float16` 將 cuVS dataset/query
cast 為 float16，並與 float32 exact ground truth 比較 Recall@K、延遲和視訊記憶體；隨後再
評估 CAGRA int8 或 VPQ。native 的逐向量 scale int8 不能直接對映到 cuVS
brute-force，若要求數值相容，需要自定義 int8 distance/top-k 或候選召回後按 scale
rerank，不能用簡單 cast 代替。

## 與 agent-memory benchmark 的關係

OpenViking 倉庫已經包含多類 benchmark，它們可以作為 cuVS 整合的質量與端到端 guardrail：

| 倉庫目錄 | 主要問題 | 在 cuVS 評測中的用途 |
| --- | --- | --- |
| `benchmark/locomo/` | 長期對話記憶、跨 session QA | memory quality 迴歸；比較 local exact、cuVS exact、CAGRA |
| `benchmark/longmemeval/openviking/` | 資訊提取、多 session/時間推理、更新與拒答 | 首選的長期記憶質量 benchmark |
| `benchmark/RAG/` | LoCoMo、Qasper、FinanceBench、SyllabusQA | 檢查通用 RAG 質量和領域差異 |
| `benchmark/tau2/llm/` | memory 對 agent tool-task success 的貢獻 | 端到端任務收益，不用於隔離 vector-search 效能 |
| `benchmark/custom/session_contention_benchmark.py` | Server 混合負載的 QPS、延遲、錯誤率和積壓 | 擴充為 `local`/`cuvs` backend matrix，測真實服務退化 |

這些質量 benchmark 不能替代 ANN benchmark。LoCoMo 只有少量長對話，LongMemEval-S 也以
500 個問題和每題有限 session 為主；單個 user 的向量規模通常不足以讓 GPU 展現優勢。它們最適合
驗證“替換後端後答案質量不下降”，而不是證明最大 QPS。

領域內建議優先考慮以下公開 benchmark：

1. [LoCoMo（ACL 2024）](https://aclanthology.org/2024.acl-long.747/)：使用廣泛，覆蓋長期對話
   QA、事件總結和多模態對話；適合作為相容性基線。
2. [LongMemEval（ICLR 2025）](https://github.com/xiaowu0162/LongMemEval)：覆蓋資訊提取、
   multi-session reasoning、時間推理、knowledge update 和 abstention；官方 harness 同時支援
   retrieval 與 QA 評測，適合做主要 memory-quality 結果。
3. [MemBench（Findings of ACL 2025）](https://aclanthology.org/2025.findings-acl.989/)：同時考慮
   factual/reflective memory、participation/observation 場景，以及 accuracy、recall、capacity、
   temporal efficiency，適合補充系統容量與效率。
4. [MemoryAgentBench（ICLR 2026）](https://github.com/HUST-AI-HYZ/MemoryAgentBench)：覆蓋
   accurate retrieval、test-time learning、long-range understanding 和 conflict resolution，適合
   評估更廣義的 agent memory 能力。
5. [LongMemEval-V2](https://github.com/xiaowu0162/LongMemEval-V2)：面向 agent trajectory memory，
   最大 haystack 達到約 1.15 億 token，並同時考察 answer accuracy 和 query latency；它是後續
   展示“大規模 agent memory + cuVS”價值最匹配的公開方向。

推薦最終報告採用三張相互獨立的 scoreboard：

- **Vector index performance**：本方案的 L1/L2，展示 latency、QPS、recall、build 和 memory。
- **Memory quality**：LongMemEval 為主、LoCoMo 為輔，固定 embedder、reader、judge、top-k 和
  context budget，只改變 vector backend。
- **Agent task utility**：TAU-2 或 MemoryAgentBench，比較 no-memory、native-memory 和
  cuVS-memory 的任務成功率與總成本。

為了讓公開 memory benchmark 達到能夠體現 GPU 的規模，不應簡單複製相同 memory。建議使用
LongMemEval 的可擴充 filler sessions、LongMemEval-V2 trajectory haystack，或者獨立的真實噪聲
corpus，把總索引擴充到 100K/1M/5M/10M，同時保留原題 evidence 作為 retrieval ground truth。

## 三層 benchmark

### L1：索引層

只測 native flat、cuVS brute-force 和 CAGRA 的 build/search，不包含 embedding、HTTP、
持久化寫入和結果回表。這一層最容易解釋 GPU kernel 與演算法本身的收益。

測量：

- build wall time，其中單獨記錄 host-to-device transfer；
- warm search 的 p50、p95、p99 和 QPS；
- Recall@10、Recall@100；
- peak host RSS、peak GPU memory 和 index size。

### L2：OpenViking collection 層

通過 `search_by_vector()` 發起查詢，包含 Python adapter、filter translation、label mapping
和記錄回表，但使用預先生成的 query vectors，避免 embedding 服務掩蓋檢索差異。

這一層應作為當前 feature integration 的主要結果，因為它測量了使用者實際經過的程式碼路徑。

### L3：服務層

通過 OpenViking server 發起請求，分別報告：

- vector-ready 請求：客戶端直接提供 query vector；
- full retrieval 請求：包含 embedding 和其他業務處理。

full retrieval 只用於判斷向量檢索在總延遲中的佔比，不用於證明 cuVS kernel 的加速比。

## 資料集矩陣

先跑能夠代表 OpenViking 的 synthetic workload，再用公開 ANN 資料集交叉驗證。

| 維度 | 建議取值 | 說明 |
| --- | --- | --- |
| Vector count | 10K、100K、1M、5M、10M | 用來找到 GPU break-even point |
| Dimension | 128、768、1024 | 128 對齊 SIFT；768/1024 接近常見 embedding |
| Metric | cosine/IP，補充 L2 | cosine 在兩端使用相同的 L2 normalization |
| K | 10、100 | 同時覆蓋常見 retrieval 與較大候選集 |
| Query batch | 1、8、32、128、512 | 區分低延遲與吞吐場景 |

公開資料集優先使用 cuVS Bench 已支援且帶 ground truth 的資料：

- SIFT-1M，128D，L2；
- GloVe-1.1M，100D，angular；
- Deep-10M，96D，angular；
- Wiki-all 1M/10M，768D，用於更接近 RAG embedding 的場景。

## 公平性與正確性

- 同一份 base vectors、query vectors、metric、K 和 normalization 輸入所有後端。
- 用 native exact 或 cuVS brute-force 生成 ground truth；精確後端必須達到 Recall@K = 1.0。
- CAGRA 只在固定 recall bucket 下比較，例如 Recall@10 >= 0.95 和 >= 0.99。
- CAGRA 引數至少掃描：`graph_degree={32,64}`、
  `intermediate_graph_degree={64,96}`、`itopk_size={32,64,128}`。
- 固定 CPU threads、NUMA placement 和 GPU 數量，並在結果中記錄硬體、軟體版本和配置。
- 每組先 warm up，再至少執行 10K queries；重複五輪，報告中位數與離散程度。
- cold build、cold first query 和 warm steady state 分開報告。

## 過濾 benchmark

過濾會影響 CAGRA 的搜尋路徑，也是本整合區別於裸 cuVS benchmark 的關鍵部分。

每個規模測試以下 selectivity：100%、10%、1%、0.1%，並包含兩種分佈：

- uniform：符合條件的 label 在資料集中均勻分佈；
- clustered/skewed：符合條件的資料集中在少數類別或路徑字首。

每個過濾場景重新生成 filtered ground truth，同時報告 Recall@K、p95 和 QPS。不能用未過濾
ground truth 計算 recall。

## 生命週期 benchmark

當前實現保留 host shadow，並在 upsert/delete 後把 GPU index 標髒；下一次查詢執行批次重建。
因此必須獨立測量：

- 首次建庫時間；
- 程序重啟後的 rehydrate + rebuild 時間；
- 1、100、10K 和 1% 資料變更後的 write latency；
- 從 write 返回到下一次成功查詢的總時間；
- rebuild 期間的 peak host/GPU memory。

這個結果決定延遲重建適合的 workload 邊界。steady-state search 圖不能把 rebuild 時間平均掉，
否則會對寫密集 workload 產生誤導。

## 當前整合的吞吐限制

預設路徑仍按一次公開 API 請求提交一個 query。當前已提供預設關閉、僅適用於 brute-force 的
request micro-batching：它可把相容的併發單 query 請求合併為最多 8 行的 matrix-query。
對於當前 generation 的 clean immutable snapshot，無 filter 或 device filter cache hit 可通過
warm fast path 直接入隊，不獲取 caller 側 device gate；dirty/cold snapshot、filter cache miss
和 device filter preparation 仍先走序列的 gated preparation。入隊後只有 micro-batch worker
會在持有 device-search gate 時執行 GPU matrix search，caller 不會持 gate 等待結果。

這消除了舊版“一次 GPU search 全程持有 caller/index lock”的主要併發瓶頸，但每次 dispatch
仍會建立 query/result device array，並在返回前把結果同步到 host。因此：

- batch > 1 的 L1 結果仍代表顯式 vector-index batch 的能力上限，不等同於公開 API 吞吐；
- L2/L3 應繼續以單 query 請求為主，同時分別測預設關閉和 opt-in micro-batching，並記錄
  實際 batch-size 分佈、`batch_wait`、`gpu_gate_queue`、QPS 與 P95；
- 下一階段優先評估 persistent query/result buffers、allocator reuse 和 host 同步最佳化，再決定
  是否支援 CAGRA micro-batching 或多個並行 batch dispatch；OpenViking 的 scheduler 與 cuVS
  官方的 Dynamic Batching 元件不是同一實現。

## 主要圖表

1. p50/p95 latency vs vector count：native exact 對比 cuVS exact，展示 break-even point。
2. QPS vs Recall@10 frontier：CAGRA 引數掃描結果，並標出 0.95/0.99 recall bucket。
3. build/rebuild/first-query time vs vector count：展示冷啟動和延遲重建代價。
4. p95/QPS vs filter selectivity：分別展示 uniform 和 skewed filter。
5. host RSS/GPU memory vs vector count：說明容量上限和 host shadow 成本。

## 第一階段最小矩陣

先用較小但足以觀察趨勢的矩陣建立可重複 harness：

- synthetic 1024D cosine，100K/1M/5M vectors；
- K=10，batch=1 和 128；
- native exact、cuVS exact、CAGRA；
- CAGRA Recall@10 >= 0.95 和 >= 0.99；
- 無過濾、1% uniform filter；
- 記錄 build、warm p50/p95/p99、QPS、recall、host RSS 和 GPU memory；
- 額外執行一次 100-record update，記錄 write + next-query rebuild latency。

第一階段結束後再決定是否下載 10M/100M 公開資料集，避免在 harness 尚未穩定時消耗大量
儲存和 GPU 時間。

## 建議的實現結構

```text
benchmark/cuvs/
├── README.md
├── generate_dataset.py
├── run_index_benchmark.py
├── run_collection_benchmark.py
├── configs/
│   ├── smoke.yaml
│   └── scale.yaml
└── plot_results.py
```

每次執行輸出一個自描述 JSON/JSONL 檔案，至少包含 git revision、backend、algorithm、全部引數、
dataset hash、hardware metadata、軟體版本、raw latency samples 和 summary。圖表必須能夠只依賴
這些結果檔案離線重建。
