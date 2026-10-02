# OpenViking Eval 模組

OpenViking 的評估模組，提供 RAG 系統的多維度評估能力。

## 模組作用

Eval 模組支援對 RAG 系統進行全面評估：

- **檢索質量評估**：精確度、召回率、相關性
- **生成質量評估**：忠實度、答案相關性
- **效能評估**：檢索速度、端到端延遲
- **框架整合**：支援 RAGAS等主流評測工具
- **儲存層評估**：IO 操作錄製與回放，對比不同儲存後端效能

## 模組設計

```
openviking/eval/
├── ragas/           # RAGAS 框架整合模組（包含所有評估相關程式碼）
│   ├── __init__.py  # RAGAS 評估器與核心型別匯出
│   ├── base.py      # 評估器基類：BaseEvaluator
│   ├── types.py     # 資料型別：EvalSample, EvalDataset, EvalResult
│   ├── generator.py # 資料集生成器
│   ├── pipeline.py  # RAG 查詢流水線
│   ├── playback.py  # Playback 回放器
│   ├── record_analysis.py  # Record 分析器
│   ├── rag_eval.py  # CLI 評估工具
│   ├── play_recorder.py # Playback CLI 工具
│   └── analyze_records.py # Record 分析 CLI 工具
├── recorder/        # IO 錄製器模組
│   ├── __init__.py  # IORecorder 錄製器
│   ├── wrapper.py   # 儲存層包裝器
│   ├── async_writer.py # 非同步寫入器
│   ├── recording_client.py # AGFS 客戶端包裝器
│   └── playback.py  # 向後相容的 playback 模組
└── datasets/        # 示例資料集
```

### 核心型別

```python
# 評估樣本
EvalSample(
    query="問題",
    context=["檢索上下文"],
    response="生成答案",
    ground_truth="標準答案"
)

# 評估資料集
EvalDataset(name="dataset", samples=[...])

# 評估結果
EvalResult(sample=..., scores={"faithfulness": 0.85})
```

### 評估器介面

```python
class BaseEvaluator(ABC):
    async def evaluate_sample(self, sample: EvalSample) -> EvalResult
    async def evaluate_dataset(self, dataset: EvalDataset) -> SummaryResult
```

## 安裝方法

```bash
# 基礎安裝
pip install openviking --upgrade --force-reinstall

# RAGAS 評估支援
pip install ragas datasets
```

## 用法示例

### 示例 1：RAGAS 評估

```python
import asyncio
from openviking.eval import EvalSample, EvalDataset, RagasEvaluator

async def main():
    # 準備評估資料
    samples = [
        EvalSample(
            query="OpenViking 是什麼？",
            context=["OpenViking 是上下文資料庫..."],
            response="OpenViking 是 AI Agent 資料庫",
            ground_truth="OpenViking 是開源上下文資料庫"
        ),
    ]
    dataset = EvalDataset(name="eval", samples=samples)
    
    # 執行評估（可配置效能引數）
    evaluator = RagasEvaluator(
        max_workers=8,      # 併發數
        batch_size=5,       # 批處理大小
        timeout=120,        # 超時時間（秒）
        max_retries=2,      # 最大重試次數
    )
    summary = await evaluator.evaluate_dataset(dataset)
    
    # 輸出結果
    for metric, score in summary.mean_scores.items():
        print(f"{metric}: {score:.2f}")

asyncio.run(main())
```

### 示例 2：CLI 工具評估

```bash
# 基礎評估
# --docs_dir 評估前會將指定的路徑載入到 OpenViking 中
python -m openviking.eval.ragas.rag_eval \
    --docs_dir ./docs \
    --question_file ./questions.jsonl \
    --config ./ov.conf \
    --output ./results.json

# 直接評估，不載入文件庫
# 啟用 RAGAS 指標
python -m openviking.eval.ragas.rag_eval \
    --question_file ./questions.jsonl \
    --ragas \
    --output ./results.json

# 啟用 IO 錄製（用於儲存層評估）
python -m openviking.eval.ragas.rag_eval \
    --docs_dir ./docs \
    --question_file ./questions.jsonl \
    --recorder \
    --output ./results.json
```

### 示例 3：基於本倉庫的評估

在 OpenViking 倉庫根目錄下執行：

```bash
# 評估文件檢索效果
python -m openviking.eval.ragas.rag_eval \
    --docs_dir ./docs \
    --docs_dir ./README.md \
    --question_file ./openviking/eval/datasets/local_doc_example_glm5.jsonl \
    --output ./eval_results.json
```

## 儲存層評估

### IO Recorder 錄製器

IO Recorder 用於錄製評估過程中的所有 IO 操作（FS、VikingDB），記錄請求引數、響應結果、耗時等資訊。

```python
from openviking.eval.recorder import init_recorder, get_recorder

# 初始化錄製器
init_recorder(enabled=True)

# 進行評估操作...
# 操作會自動記錄到 ./records/io_recorder_YYYYMMDD.jsonl

# 獲取統計資訊
recorder = get_recorder()
stats = recorder.get_stats()
print(f"Total operations: {stats['total_count']}")
print(f"FS operations: {stats['fs_count']}")
print(f"VikingDB operations: {stats['vikingdb_count']}")
```

### Record Analysis 分析器

Record Analysis 用於分析錄製的 IO 操作，提供全面的統計資訊。

```bash
# 分析所有記錄
python -m openviking.eval.ragas.analyze_records \
    --record_file ./records/io_recorder_20260214.jsonl

# 只分析 FS 操作
python -m openviking.eval.ragas.analyze_records \
    --record_file ./records/io_recorder_20260223.jsonl \
    --fs

# 只分析 VikingDB 操作
python -m openviking.eval.ragas.analyze_records \
    --record_file ./records/io_recorder_20260214.jsonl \
    --vikingdb

# 過濾特定操作型別
python -m openviking.eval.ragas.analyze_records \
    --record_file ./records/io_recorder_20260214.jsonl \
    --io-type fs \
    --operation read

# 儲存結果到檔案
python -m openviking.eval.ragas.analyze_records \
    --record_file ./records/io_recorder_20260214.jsonl \
    --output analysis.json
```

### Playback 回放器

Playback 用於回放錄製的 IO 操作，對比不同儲存後端的效能差異。

```bash
# 使用遠端配置回放
python -m openviking.eval.ragas.play_recorder \
    --record_file ./records/io_recorder_20260223.jsonl \
    --config_file ./.local/s3/ov-local.conf \
    --output ./records/playback_results.json

# 只測試 FS 操作
python -m openviking.eval.ragas.play_recorder \
    --record_file ./records/io_recorder_20260214.jsonl \
    --config_file ./ov.conf \
    --fs

# 只測試 VikingDB 操作
python -m openviking.eval.ragas.play_recorder \
    --record_file ./records/io_recorder_20260214.jsonl \
    --config_file ./ov.conf \
    --vikingdb

# 過濾特定操作型別
python -m openviking.eval.ragas.play_recorder \
    --record_file ./records/io_recorder_20260214.jsonl \
    --config_file ./ov.conf \
    --io-type fs \
    --operation read
```

### 儲存層評估流程

1. **錄製階段**：使用 `--recorder` 引數執行評估，記錄所有 IO 操作
2. **分析階段**：使用 `analyze_records` 分析錄製的記錄
3. **回放階段**：使用不同的配置檔案回放，對比效能差異
4. **分析結果**：檢視各操作的耗時對比，識別效能瓶頸

```bash
# 步驟 1：使用本地儲存錄製
python -m openviking.eval.ragas.rag_eval \
    --docs_dir ./docs \
    --question_file ./questions.jsonl \
    --recorder \
    --config ./ov-local.conf

# 步驟 2：分析錄製的記錄
python -m openviking.eval.ragas.analyze_records \
    --record_file ./records/io_recorder_20260215.jsonl

# 步驟 3：使用遠端儲存回放
python -m openviking.eval.ragas.play_recorder \
    --record_file ./records/io_recorder_20260215.jsonl \
    --config_file ./ov.conf

# 步驟 4：對比分析
# 輸出會顯示各操作的原始耗時 vs 回放耗時
```

## 評估指標

### RAGAS 指標

| 類別 | 指標 | 說明 |
|------|------|------|
| 檢索質量 | context_precision | 上下文精確度 |
| | context_recall | 上下文召回率 |
| 生成質量 | faithfulness | 答案忠實度 |
| | answer_relevance | 答案相關性 |

### 效能指標

| 指標 | 說明 |
|------|------|
| retrieval_time | 檢索耗時 |
| total_latency | 端到端延遲 |

### 儲存層指標

| 操作型別 | 說明 |
|----------|------|
| fs.read | 檔案讀取 |
| fs.write | 檔案寫入 |
| fs.ls | 目錄列表 |
| fs.stat | 文件信息 |
| fs.tree | 目錄樹遍歷 |
| vikingdb.search | 向量搜索 |
| vikingdb.upsert | 向量寫入 |
| vikingdb.filter | 標量過濾 |

## RAGAS 性能配置

RAGAS 評估支援以下效能配置引數：

| 引數 | 預設值 | 環境變數 | 說明 |
|------|--------|----------|------|
| max_workers | 16 | RAGAS_MAX_WORKERS | 併發 worker 數量 |
| batch_size | 10 | RAGAS_BATCH_SIZE | 批處理大小 |
| timeout | 180 | RAGAS_TIMEOUT | 超時時間（秒） |
| max_retries | 3 | RAGAS_MAX_RETRIES | 最大重試次數 |

```bash
# 通過環境變數配置
export RAGAS_MAX_WORKERS=8
export RAGAS_BATCH_SIZE=5
export RAGAS_TIMEOUT=120
export RAGAS_MAX_RETRIES=2

python -m openviking.eval.ragas.rag_eval --docs_dir ./docs --question_file ./questions.jsonl --ragas
```

## 相關檔案

- CLI 工具：[rag_eval.py](./ragas/rag_eval.py)
- RAGAS 集成：[ragas/__init__.py](./ragas/__init__.py)
- 評估器基類：[ragas/base.py](./ragas/base.py)
- 資料型別：[ragas/types.py](./ragas/types.py)
- 資料集生成器：[ragas/generator.py](./ragas/generator.py)
- RAG 查詢流水線：[ragas/pipeline.py](./ragas/pipeline.py)
- 記錄分析器：[ragas/record_analysis.py](./ragas/record_analysis.py)
- 分析 CLI：[ragas/analyze_records.py](./ragas/analyze_records.py)
- 回放器：[ragas/playback.py](./ragas/playback.py)
- 回放 CLI：[ragas/play_recorder.py](./ragas/play_recorder.py)
- IO 錄製器：[recorder/__init__.py](./recorder/__init__.py)
- 示例資料：[datasets/local_doc_example_glm5.jsonl](./datasets/local_doc_example_glm5.jsonl)
- 測試檔案：[tests/eval/](../../tests/eval/)、[tests/storage/test_recorder.py](../../tests/storage/test_recorder.py)
