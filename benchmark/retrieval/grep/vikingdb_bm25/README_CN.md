# VikingDB BM25 Grep 基準測試

用於評估 OpenViking grep 檢索配合 VikingDB BM25 引擎的基準測試套件。

執行匯入、重建索引或基準測試前，需要先啟動 `openviking-server`。

## 目錄結構

```
vikingdb_bm25/
├── ai_wiki.txt              # 合成數據生成的原始文本
├── effectiveness/            # 檢索效果測試（召回率/精確率/F1）
│   ├── step1_add_resource.py
│   └── step2_quality.py
└── performance/              # 檢索效能測試（延遲 + 大規模返回匹配數）
    ├── step0_prepare_data.py
    ├── step1_add_resource.py
    ├── step2_reindex.py
    └── step3_benchmark.py
```

## Effectiveness — 檢索效果

測試 grep 在真實程式碼倉庫中是否能找到**所有**匹配檔案。

**資料來源：** 真實程式碼倉庫（手動下載，放置於 `~/.openviking/data/benchmark/`）。

| 步驟 | 指令碼 | 說明 |
|------|------|------|
| 1 | `step1_add_resource.py` | 匯入程式碼倉庫（含建索引，一次性匯入） |
| 2 | `step2_quality.py` | SDK grep 與 fs 引擎 ground truth 對比（快取） |

### 使用方法

```bash
# 步驟 1：匯入程式碼倉庫（含建索引，一次性匯入）
cd effectiveness/
python3 step1_add_resource.py --source ~/.openviking/data/benchmark/OpenViking-main

# 步驟 2：評估檢索質量
#   首次執行必須使用 engine=fs 生成 ground truth 快取：
#     1. 設定 ov.conf: "grep": {"engine": "fs"}
#     2. 重啟服務
python3 step2_quality.py --keywords grep reindex SyncHTTPClient

#   後續執行可使用任意引擎（ground truth 從快取讀取）：
#     1. 設定 ov.conf: "grep": {"engine": "auto", "switch_to_remote_threshold": 0}
#     2. 重啟服務
python3 step2_quality.py --keywords grep reindex SyncHTTPClient

# 可選引數：--regenerate-ground-truth  （強制重算，需 engine=fs）
```

## Performance — 檢索延遲

在大規模合成數據集（預設 20 萬檔案）上測試 grep 速度和返回匹配數。

**資料來源：** 從 `ai_wiki.txt` 生成，按已知機率注入目標單詞。

| 步驟 | 指令碼 | 說明 |
|------|------|------|
| 0 | `step0_prepare_data.py` | 生成合成資料集（dir_xxx/wiki_xxx.txt） |
| 1 | `step1_add_resource.py` | 通過 HTTP SDK 匯入資料（`vectors_only`，不執行 VLM） |
| 2 | `step2_reindex.py` | 可選：通過 openviking-server 非同步重建索引（併發=16，輪詢） |
| 3 | `step3_benchmark.py` | 使用 `node_limit=256` 測量延遲和返回匹配數 |

### 目標單詞

15 個單詞，分 5 個機率層級：

這些片語定義在 `performance/step0_prepare_data.py` 中，並由 `performance/step3_benchmark.py` 複用。

| 機率 | 單詞 | 預期命中數（每 20 萬檔案） |
|------|------|---------------------------|
| 1% | heliofract, prismcache, fluxkernel | ~2,000 |
| 0.1% | auroracode, kiteshade, glyphvector | ~200 |
| 0.1% | cortexmint, latticewave, spiralsync | ~200 |
| 0.05% | ripplehash, embertrace, novaframe | ~100 |
| 0.01% | zephyrloom, quartzrelay, nebulaindex | ~20 |

### 使用方法

```bash
cd performance/

# 步驟 0：生成資料（預設：200 目錄 x 1000 檔案 = 20 萬檔案）
python3 step0_prepare_data.py

# 可選：追加更多資料，用於水平擴容，不覆蓋已有目錄
python3 step0_prepare_data.py --start-dir 100 --num-dirs 100

# 步驟 1：僅生成向量，不執行 VLM 語義處理
python3 step1_add_resource.py

# 步驟 2（可選）：重建向量索引
python3 step2_reindex.py
# 可選引數：--concurrency N  （預設：16）

# 步驟 3：基準測試 — 用不同引擎配置各跑一次
#   執行 A：fs 引擎
#     1. 設定 ov.conf: "grep": {"engine": "fs"}
#     2. 重啟服務
python3 step3_benchmark.py --engine-label fs

#   執行 B：auto 引擎（bm25）
#     1. 設定 ov.conf: "grep": {"engine": "auto", "switch_to_remote_threshold": 0}
#     2. 重啟服務
python3 step3_benchmark.py --engine-label auto --compare step3_result_fs.json
```

## 核心概念

- **Effectiveness（效果測試）** 將 grep 結果與 fs 引擎的 ground truth 對比（本地快取）
- **Performance（效能測試）** 對比不同引擎的延遲和返回匹配數，不生成 ground truth
- **Effectiveness** 直接一次性匯入真實程式碼倉並建索引，然後執行效果評估
- **Performance** 通過 HTTP SDK 以 `vectors_only` 模式匯入合成數據，可選非同步重建索引，最後執行延遲基準測試
- **Performance** 的匯入與 reindex 步驟支援**斷點續傳**（各有獨立進度檔案）
- 切換 grep 引擎需修改 `ov.conf` 並重啟服務，在不同執行之間對比
- 如需水平擴充合成數據集，可用新的 `--start-dir` 再執行步驟 0，然後重跑步驟 1 和步驟 2。
