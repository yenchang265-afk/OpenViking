# RAG

## 中文版

[English Version README](./README.md)

RAG 是一個獨立的 RAG（檢索增強生成）系統評估框架，完全相容最新版本的 OpenViking。

### 專案結構

```
benchmark/RAG/
├── src/                        # 原始碼
│   ├── __init__.py
│   ├── pipeline.py              # 評估核心流水線
│   ├── adapters/                # 資料集介面卡
│   │   ├── __init__.py
│   │   ├── base.py              # 基礎介面卡類
│   │   ├── locomo_adapter.py    # Locomo 資料集介面卡
│   │   ├── syllabusqa_adapter.py # SyllabusQA 資料集介面卡
│   │   ├── qasper_adapter.py    # Qasper 資料集介面卡
│   │   └── financebench_adapter.py # FinanceBench 資料集介面卡
│   └── core/                    # 核心元件
│       ├── __init__.py
│       ├── logger.py            # 日誌模組
│       ├── vector_store.py      # 向量儲存包裝器
│       ├── llm_client.py        # LLM 客戶端包裝器
│       ├── metrics.py           # 指標計算
│       ├── judge_util.py        # LLM 評判工具
│       └── monitor.py           # 監控工具
├── config/                      # 配置文件
│   ├── config.yaml              # 主配置文件
│   ├── locomo_config.yaml       # Locomo 資料集配置
│   ├── syllabusqa_config.yaml   # SyllabusQA 資料集配置
│   ├── qasper_config.yaml       # Qasper 資料集配置
│   └── financebench_config.yaml # FinanceBench 資料集配置
├── scripts/                     # 工具指令碼
│   ├── __init__.py
│   ├── download_dataset.py      # 資料集下載指令碼
│   ├── sample_dataset.py        # 資料集抽樣指令碼
│   ├── prepare_dataset.py       # 統一資料集準備指令碼
│   └── run_sampling.py          # 自定義抽樣指令碼
├── raw_data/                    # 原始資料集目錄（下載）
├── datasets/                    # 抽樣資料集目錄
├── Output/                      # 輸出結果目錄
├── run.py                       # 主執行指令碼
└── README.md
```

### 快速開始

#### 1. 安裝依賴

```bash
cd OpenViking
uv pip install -e ".[benchmark]"
source .venv/bin/activate
```

#### 2. 準備資料集

本專案提供完整的資料集準備工作流，包括下載、抽樣和配置。

##### 資料集準備工作流

資料集準備包括兩個主要步驟：

1. **下載**：從官方源下載原始資料集到 `raw_data/` 目錄
2. **抽樣**：從原始資料集抽樣（可選）到 `datasets/` 目錄

```
原始資料來源 → 下載 → raw_data/{dataset_name}/ → 抽樣 → datasets/{dataset_name}/
```

##### 下載資料集

使用 `download_dataset.py` 下載資料集：

```bash
cd benchmark/RAG

# 下載所有配置的資料集
python scripts/download_dataset.py

# 下載特定資料集
python scripts/download_dataset.py --dataset Locomo

# 強制重新下載，即使已存在
python scripts/download_dataset.py --dataset Locomo --force
```

##### 抽樣資料集

使用 `sample_dataset.py` 抽樣資料集：

```bash
# 抽樣所有資料集（使用完整資料集，不抽樣）
python scripts/sample_dataset.py

# 抽樣特定資料集（使用完整資料集，不抽樣）
python scripts/sample_dataset.py --dataset Locomo

# 按 QA 數量抽樣
python scripts/sample_dataset.py --dataset Locomo --sample-size 100

# 按文件數量抽樣（推薦）
python scripts/sample_dataset.py --dataset Locomo --num-docs 5

# 使用完整資料集（顯式，不抽樣）
python scripts/sample_dataset.py --dataset Locomo --full

# 指定隨機種子（可重現）
python scripts/sample_dataset.py --dataset Locomo --num-docs 5 --seed 42
```

**抽樣策略：**

1. **文件級抽樣（推薦）**：使用 `--num-docs N` 首先抽樣 N 個文件，保留文件中的所有 QA
2. **QA 級抽樣**：使用 `--sample-size N` 隨機選擇文件，直到 QA 計數達到 N
3. **完整資料集**：使用 `--full` 或不指定抽樣引數來使用完整資料集

##### 一鍵準備

使用 `prepare_dataset.py` 一步完成下載和抽樣：

```bash
# 準備所有資料集（使用完整資料集，不抽樣）
python scripts/prepare_dataset.py

# 準備特定資料集，抽樣 5 個文件
python scripts/prepare_dataset.py --dataset Locomo --num-docs 5

# 使用完整資料集（顯式，不抽樣）
python scripts/prepare_dataset.py --dataset Locomo --full

# 跳過下載，只抽樣現有資料
python scripts/prepare_dataset.py --dataset Locomo --num-docs 5 --skip-download

# 跳過抽樣，只下載
python scripts/prepare_dataset.py --dataset Locomo --skip-sampling
```

##### 更新配置文件

準備資料集後，需要更新評估配置檔案中的 `dataset_path`。

**配置文件位置：**

```
benchmark/RAG/config/
├── config.yaml          # 主配置文件
├── locomo_config.yaml
├── syllabusqa_config.yaml
├── qasper_config.yaml
└── financebench_config.yaml
```

**資料集配置示例：**

- **Locomo**：
  ```yaml
  dataset_name: "Locomo"
  paths:
    dataset_path: "datasets/Locomo/locomo10.json"
  ```
- **SyllabusQA**：
  ```yaml
  dataset_name: "SyllabusQA"
  paths:
    dataset_path: "datasets/SyllabusQA"
  ```
- **Qasper**：
  ```yaml
  dataset_name: "Qasper"
  paths:
    dataset_path: "datasets/Qasper"
  ```
- **FinanceBench**：
  ```yaml
  dataset_name: "FinanceBench"
  paths:
    dataset_path: "datasets/FinanceBench/financebench_open_source.jsonl"
  ```

**注意：** 對於像 SyllabusQA 和 Qasper 這樣有多個檔案的資料集，`dataset_path` 應設定為目錄路徑，介面卡會自動查詢並載入所有相關檔案。

#### 3. 配置 LLM

在 `config/*.yaml` 中編輯 LLM 配置。此配置用於：

- **答案生成**：從檢索的上下文生成答案
- **LLM 作為評判者評估**：使用 LLM 評估生成答案的質量

#### 4. 配置 OpenViking

如果需要使用自定義 OpenViking 配置（用於資料攝取和檢索），在 benchmark/RAG 目錄中建立 `ov.conf` 檔案。這將覆蓋預設的 OpenViking 設定。

您可以參考 OpenViking 根目錄中的 `examples/ov.conf.example` 瞭解配置格式。

#### 5. 執行評估

```bash
cd benchmark/RAG

# 執行完整評估（資料攝取、答案生成、評估和資料刪除）
python run.py --config config/locomo_config.yaml

# 只執行資料攝取和答案生成階段
python run.py --config config/locomo_config.yaml --step gen

# 只執行評估階段（需要前一步生成的答案）
python run.py --config config/locomo_config.yaml --step eval

# 只執行資料刪除階段
python run.py --config config/locomo_config.yaml --step del
```

### 支援的資料集

| 資料集              | 型別   | 文件數  | 問題數  | 特點                                             |
| ---------------- | ---- | ---- | ---- | ---------------------------------------------- |
| **Locomo**       | 多輪對話 | 10   | 1540 | 長對話理解，4 種問題型別（事實性、時間性、推理、理解）                   |
| **SyllabusQA**   | 教學大綱 | 39   | 5078 | 教育領域，6 種問題型別（單一事實、多事實、單一推理、多推理、總結、是/否）         |
| **Qasper**       | 學術論文 | 1585 | 5049 | 研究領域，1585 篇 NLP 論文，3 種答案型別（抽取式、自由形式、是/否）       |
| **FinanceBench** | 金融領域 | 84   | 150  | 金融領域，開源子集包含 150 個 QA 對，3 種問題型別（領域相關、指標生成、新穎生成） |

### 如何使用不同的資料集

每個資料集在 `config/` 目錄中都有自己的配置檔案。要使用特定資料集：

1. **選擇資料集配置檔案**：
   - `config/locomo_config.yaml` - 用於 Locomo 資料集
   - `config/syllabusqa_config.yaml` - 用於 SyllabusQA 資料集
   - `config/qasper_config.yaml` - 用於 Qasper 資料集
   - `config/financebench_config.yaml` - 用於 FinanceBench 資料集
2. **使用選定的配置執行評估**：
   ```bash
   # 使用 Locomo 資料集評估
   python run.py --config config/locomo_config.yaml

   # 使用 SyllabusQA 資料集評估
   python run.py --config config/syllabusqa_config.yaml

   # 使用 Qasper 資料集評估
   python run.py --config config/qasper_config.yaml

   # 使用 FinanceBench 資料集評估
   python run.py --config config/financebench_config.yaml
   ```
3. **自定義配置（可選）**：
   您可以複製資料集配置檔案並修改它以滿足您的需求：
   ```bash
   cp config/locomo_config.yaml config/my_custom_config.yaml
   # 編輯 config/my_custom_config.yaml 以滿足您的偏好
   python run.py --config config/my_custom_config.yaml
   ```

### 配置指南

RAG 使用 YAML 配置檔案來控制評估過程。每個資料集在 `config/` 目錄中都有自己的配置檔案。

**關鍵配置部分：**

1. **基本配置**：
   - `dataset_name`：正在評估的資料集名稱
2. **介面卡配置**：
   - `adapter.module`：資料集介面卡的 Python 模組路徑
   - `adapter.class_name`：資料集介面卡的類名
3. **執行配置**：
   - `max_workers`：併發工作執行緒數
   - `ingest_workers`：文件攝取的工作執行緒數
   - `retrieval_topk`：要檢索的文件數
   - `max_queries`：限制要處理的查詢數（null = 全部）
   - `skip_ingestion`：跳過文件攝取（使用現有索引）
   - `ingest_mode`：文件攝取模式（"directory" 或 "per\_file"）
   - `retrieval_instruction`：檢索的自定義指令（預設為空）
4. **路徑配置**：
   - `dataset_dir`：資料集檔案或目錄的路徑
   - `doc_output_dir`：處理文件的目錄
   - `output_dir`：評估結果的目錄
   - `log_file`：日誌檔案的路徑
5. **LLM 配置**：
   - `llm.model`：LLM 模型名稱
   - `llm.temperature`：生成溫度
   - `llm.base_url`：API 基礎 URL
   - `llm.api_key`：API 金鑰（保持安全）

### 評估流程概述

評估過程包括 5 個主要階段：

1. **資料準備**
   - 將原始資料集轉換為 OpenViking 友好格式
   - 處理文件以進行攝取
2. **資料攝取**
   - 將處理後的文件攝取到 OpenViking 向量儲存中
   - 為文件建立嵌入
   - 儲存向量索引以進行檢索
3. **答案生成**
   - 對於每個問題，從向量儲存中檢索相關文件
   - 使用檢索的上下文和問題構建提示
   - 使用 LLM 生成答案
4. **評估**
   - 使用 LLM 作為評判者評估生成的答案與黃金答案的質量
   - 計算指標（召回率、F1、準確率）
5. **資料刪除**
   - 清理向量儲存並刪除攝取的文件

### 評估指標

- **Recall**：檢索召回率
- **F1 Score**：答案 F1 分數
- **Accuracy**：LLM 評判分數（0-4）
- **Latency**：檢索延遲
- **Token Usage**：令牌使用量

### 輸出檔案

評估結果儲存在 `Output/` 目錄中，結構如下：

```
Output/
└── {dataset_name}/
    └── experiment_{experiment_name}/
        ├── generated_answers.json       # LLM 生成的答案
        ├── qa_eval_detailed_results.json # 詳細評估結果
        ├── benchmark_metrics_report.json # 聚合指標報告
        ├── docs/                         # 處理後的文件（如果 skip_ingestion=false）
        └── benchmark.log                 # 日誌檔案
```

**OpenViking 儲存：**
Benchmark 使用 Python HTTP SDK 所配置的 OpenViking Server。內容和向量索引的儲存位置由 Server 管理，而不是由 Benchmark 程序管理。

#### 文件描述和示例

**1.** **`benchmark_metrics_report.json`** **- 摘要報告**

- **包含內容**：聚合指標報告，包含整體效能分數

示例：

```json
{
    "Insertion Efficiency (Total Dataset)": {
        "Total Insertion Time (s)": 131.98,
        "Total Input Tokens": 142849,
        "Total Output Tokens": 52077,
        "Total Embedding Tokens": 95626
    },
    "Query Efficiency (Average Per Query)": {
        "Average Retrieval Time (s)": 0.17,
        "Average Input Tokens": 3364.46,
        "Average Output Tokens": 15.5
    },
    "Dataset": "Locomo",
    "Total Queries Evaluated": 100,
    "Performance Metrics": {
        "Average F1 Score": 0.318,
        "Average Recall": 0.724,
        "Average Accuracy (Hit 0-4)": 2.36,
        "Average Accuracy (normalization)": 0.59
    }
}
```

**字段描述：**

- `Insertion Efficiency`：文件攝取效能統計
- `Query Efficiency`：每個查詢的效能平均值
- `Performance Metrics`：核心評估分數（Accuracy 為 0-4 分制）

***

**2.** **`generated_answers.json`** **- 生成的答案**

- **包含內容**：所有問題、檢索的上下文和 LLM 生成的答案

示例（單個結果）：

```json
{
  "_global_index": 0,
  "sample_id": "conv-26",
  "question": "Would Caroline pursue writing as a career option?",
  "gold_answers": ["LIkely no; though she likes reading, she wants to be a counselor"],
  "category": "3",
  "evidence": ["D7:5", "D7:9"],
  "retrieval": {
    "latency_sec": 0.288,
    "uris": ["viking://resources/...", "viking://resources/..."]
  },
  "llm": {
    "final_answer": "Not mentioned"
  },
  "metrics": {
    "Recall": 1.0
  },
  "token_usage": {
    "total_input_tokens": 2643,
    "llm_output_tokens": 2
  }
}
```

**字段描述：**

- `_global_index`：唯一查詢識別符號
- `question`：正在詢問的問題
- `gold_answers`：真實答案
- `retrieval.uris`：檢索文件的 URI
- `llm.final_answer`：LLM 生成的答案
- `metrics.Recall`：檢索召回分數（0-1）
- `token_usage`：令牌消耗統計

***

**3.** **`qa_eval_detailed_results.json`** **- 詳細評估**

- **包含內容**：每個問題的評估，包括 LLM 評判者的推理和分數

示例（單個結果）：

```json
{
  "_global_index": 18,
  "question": "When did Melanie sign up for a pottery class?",
  "gold_answers": ["2 July 2023"],
  "llm": {
    "final_answer": "2 July 2023 (mentioned in the conversation on 3 July 2023)"
  },
  "metrics": {
    "Recall": 1.0,
    "F1": 0.375,
    "Accuracy": 4
  },
  "llm_evaluation": {
    "prompt_used": "Locomo_0or4",
    "reasoning": "The generated answer explicitly includes the exact date 2 July 2023 that matches the gold answer...",
    "normalized_score": 4
  }
}
```

**字段描述：**

- `metrics.F1`：答案 F1 分數（0-1）
- `metrics.Accuracy`：LLM 評判分數（0-4，4 = 完美）
- `llm_evaluation.reasoning`：LLM 評判者對分數的推理
- `llm_evaluation.normalized_score`：最終標準化分數

***

**4.** **`benchmark.log`** **- 執行日誌**

- **包含內容**：詳細的執行日誌，帶有時間戳、警告和錯誤
- **如何檢視**：在任何文本編輯器中直接開啟

***

**5.** **`docs/`** **- 處理後的文件**

- **包含內容**：Markdown 格式的處理文件（如果 `skip_ingestion=false`）
- **如何檢視**：在任何 Markdown 檢視器或文本編輯器中直接開啟 `.md` 檔案

### 基準測試結果參考

以下是基準測試結果（top-5 檢索），僅供參考：

| 資料集              | 評估查詢數 | 平均 F1 分數 | 平均召回率 | 平均準確率（0-4）| 標準化準確率 |
| ---------------- | ------ | -------- | ----- | ------------ | ------- |
| **FinanceBench** | 12     | 0.224    | 0.694 | 2.5          | 0.625   |
| **Locomo**       | 80     | 0.254    | 0.592 | 2.4          | 0.600   |
| **Qasper**       | 60     | 0.293    | 0.614 | 2.12         | 0.529   |
| **SyllabusQA**   | 90     | 0.344    | 0.675 | 2.54         | 0.636   |

**測試配置詳情：**

- **LLM 模型：** `doubao-seed-2-0-pro-260215`
- **API 基礎地址：** `https://ark.cn-beijing.volces.com/api/v3`
- **溫度引數：** 0（確定性輸出）
- **檢索 Top-K：** 5
- **最大工作執行緒數：** 8
- **攝取工作執行緒數：** 8
- **攝取模式：** directory
- **檢索指令：** （空）
- **評估指標：** Recall、F1 分數、Accuracy（0-4 分制）

所有資料集使用相同的 LLM 和執行配置，特定於資料集的介面卡和路徑在各自的 YAML 檔案中配置。

### 復現實驗

要復現基準測試結果，請按照以下步驟操作：

```bash
cd OpenViking/benchmark/RAG

# 1. 安裝依賴（如果尚未安裝）
uv pip install -e ".[benchmark]"
source .venv/bin/activate

# 2. 下載所有資料集
python scripts/download_dataset.py

# 3. 對所有資料集執行一鍵抽樣，使用與基準測試相同的引數
python scripts/run_sampling.py

# 4. 配置您的 LLM API 金鑰
# 編輯 config/ 目錄下的配置檔案，在 llm.api_key 欄位中設定您的 API 金鑰

# 5. 為每個資料集執行評估
python run.py --config config/locomo_config.yaml
python run.py --config config/syllabusqa_config.yaml
python run.py --config config/qasper_config.yaml
python run.py --config config/financebench_config.yaml

# 6. 在 Output/{dataset_name}/experiment_test_top_5/ 中檢視結果
```

**注意：** `run_sampling.py` 指令碼將進行以下抽樣：
- Locomo：3 個文件，80 個 QA
- SyllabusQA：7 個文件，90 個 QA
- Qasper：8 個文件，60 個 QA
- FinanceBench：3 個文件，12 個 QA
所有抽樣使用 seed=42 以確保可重現性。

### 進階配置

#### 檢索指令配置

您可以在 `config.yaml` 檔案中配置自定義檢索指令，以指導檢索過程。此指令在檢索期間新增到每個查詢的前面。

**配置示例：**

```yaml
# ===========Execution Configuration============
# Instruction for retrieval, empty by default
# Recommended format: "Target_modality: xxx.\nInstruction:xxx.\nQuery:"
retrieval_instruction: "Target_modality: text.\nInstruction:Locate the part of the conversation where the speakers discuss.\nQuery:"
```

**推薦格式：**

- `Target_modality: xxx.` - 指定目標模態（例如，文本、影像、音訊）
- `Instruction: xxx.` - 為檢索提供具體指令
- `Query:` - 標記實際查詢的開始

當 `retrieval_instruction` 為空時，系統將使用原始問題進行檢索。

#### 自定義提示

RAG 使用特定於資料集和問題型別的提示來指導 LLM 答案生成。您可以在 `src/adapters/` 下的介面卡檔案中自定義這些提示，以提高評估結果。

##### Locomo 資料集提示（src/adapters/locomo\_adapter.py）

Locomo 有 4 個問題類別，每個類別都有特定的指令：

- **類別 1（事實提取）**：
  ```
  從對話中提取準確的事實答案。
  - 儘可能使用上下文中的確切詞語
  - 如果有多個專案，用逗號分隔
  ```
- **類別 2（時間相關）**：
  ```
  回答與時間相關的問題。
  - 密切關注對話中的 DATE 標籤
  - 必要時計算相對時間（例如，"10 年前"）
  - 使用上下文中的確切日期
  ```
- **類別 3（推理）**：
  ```
  基於對話進行推理和推斷。
  - 僅使用上下文中的事實
  - 清楚地陳述您的結論（例如，"可能是"，"可能不是"）
  - 不要解釋您的推理或提供任何依據/理由
  - 只輸出您的最終結論，別無其他
  - 不要編造資訊
  ```
- **類別 4（理解/意義）**：
  ```
  理解含義和意義。
  - 關注說話者的意思，而不僅僅是他們說的話
  - 識別象徵意義或隱含意義
  - 儘可能使用上下文中的措辭
  ```

##### SyllabusQA 資料集提示（src/adapters/syllabusqa\_adapter.py）

SyllabusQA 有 6 種問題型別：

- **single factual**：提取單個事實答案
- **multi factual**：提取多個事實答案
- **single reasoning**：簡單邏輯推理
- **multi reasoning**：複雜推理
- **summarization**：總結相關資訊
- **yes/no**：是/否問題

##### Qasper 資料集提示（src/adapters/qasper\_adapter.py）

Qasper 有 3 種答案型別：

- **extractive**：從論文中提取準確答案
- **free\_form**：用自己的話自由回答
- **yes\_no**：是/否問題

##### FinanceBench 資料集提示（src/adapters/financebench\_adapter.py）

FinanceBench 有 3 種問題型別：

- **domain-relevant**：金融領域問題
- **metrics-generated**：計算金融指標
- **novel-generated**：新穎的金融問題

##### 如何自定義提示

1. 開啟您的資料集的介面卡檔案（例如，`src/adapters/locomo_adapter.py`）
2. 找到 `CATEGORY_INSTRUCTIONS` 字典
3. 修改您想要改進的問題型別的提示文本
4. 使用修改後的提示重新執行評估

### 新增新資料集

1. 在 `src/adapters/` 中建立一個新的介面卡類，繼承自 `BaseAdapter`
2. 在 `config/` 中建立相應的配置檔案
3. 實現必要的方法：
   - `data_prepare()`：資料預處理
   - `load_and_transform()`：載入和轉換資料
   - `build_prompt()`：構建提示
   - `post_process_answer()`：後處理答案

### 與 OpenViking 整合

本專案通過以下方式與 OpenViking 整合：

- 使用 OpenViking Python HTTP SDK 進行資料攝取和檢索
- 通過 `ovcli.conf` 或 SDK 環境變數配置 OpenViking 連線
- 支援動態載入 OpenViking 的最新功能

### 常見問題（FAQ）

**問：如果我已經有向量索引，如何跳過資料攝取階段？**
答：在配置檔案中設定 `skip_ingestion: true`。這將使用現有的向量索引。

**問：我可以只執行評估階段而不重新攝取文件嗎？**
答：可以！首先執行 `--step gen` 生成答案，然後執行 `--step eval` 評估生成的答案。

**問：如果我收到 API 金鑰錯誤，應該怎麼辦？**
答：確保您在配置檔案的 `llm.api_key` 欄位中設定了有效的 API 金鑰。保持您的 API 金鑰安全，不要將其提交到版本控制中。

**問：如何限制測試處理的查詢數量？**
答：在配置檔案中設定 `max_queries` 為您想要處理的查詢數量（例如，`max_queries: 10`）。

**問："directory" 和 "per\_file" 攝取模式有什麼區別？**
答：

- "directory"：將整個目錄視為一個文件
- "per\_file"：將每個檔案視為一個單獨的文件

**問：如何自定義檢索指令？**
答：在配置檔案中設定 `retrieval_instruction`。推薦格式為：
`"Target_modality: xxx.\nInstruction:xxx.\nQuery:"`

**問：我在哪裡可以找到評估結果？**
答：結果儲存在配置檔案中 `output_dir` 指定的目錄中。預設情況下，這是 `Output/{dataset_name}/experiment_{experiment_name}/`。

### 許可證

與 OpenViking 相同的許可證。
