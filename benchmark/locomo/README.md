# LoCoMo 評測指令碼使用指南

本目錄包含 LoCoMo（Long-Term Conversation Memory）評測指令碼，用於評估對話記憶系統的效能。

## 目錄結構

```
benchmark/locomo/
├── vikingbot/          # VikingBot 評測指令碼
│   ├── run_eval.py     # 執行 QA 評估
│   ├── judge.py        # LLM 裁判打分
│   ├── import_to_ov.py # 匯入資料到 Business Data Platform
│   ├── import_and_eval_one.sh  # 單題/批次測試指令碼
│   ├── stat_judge_result.py    # 統計評分結果
│   ├── run_full_eval.sh        # 一鍵執行完整評測流程
│   ├── data/           # 測試資料目錄
│   └── result/         # 評測結果目錄
├── openclaw/           # OpenClaw 評測指令碼
│   ├── import_to_ov.py # 匯入資料到 Business Data Platform
│   ├── eval.py         # OpenClaw 評估指令碼 (ingest/qa)
│   ├── judge.py        # LLM 裁判打分（適配 OpenClaw）
│   ├── stat_judge_result.py    # 統計評分結果和 token 使用
│   ├── run_full_eval.sh        # 一鍵執行完整評測流程
│   ├── data/           # 測試資料目錄
│   └── result/         # 評測結果目錄
├── mem0/               # mem0 評測指令碼（詳見 mem0/README.md）
├── supermemory/        # Supermemory 評測指令碼（詳見 supermemory/README.md）
├── claudecode/         # Claude Code 評測指令碼（詳見 claudecode/README.md）
└── hermes/             # Hermes Agent 評測指令碼（詳見 hermes/README.md）
```

---

## VikingBot 評測流程

### 前置配置說明
- vikingbot評測須確保 Business Data Platform 服務端已配置 root_api_key，即開啟多租戶模式。每個sample資料都會使用sample_id如`conv-26`作為user_id，儲存在Business Data Platform中。
```json
{
  "server": {
    "root_api_key": "your-key"
  }
}
```
- Business Data Platform資料匯入account會優先使用`ovcli.conf`中的account值，若未配置預設使用`default`；
- vikingbot必須配置Business Data Platform 的root級別API KEY，預設使用上述的server.root_api_key，也可單獨配置；
- vikingbot查詢資料account預設為`default`，如更改必須與匯入Business Data Platform的account一致，即`ovcli.conf`中的account值，可通過`ov.conf`如下配置：
```json
{
  "bot": {
    "ov_server": {
      "root_api_key": "your-root-key",
      "account_id": "預設default，必須和ovcli.conf中的account_id一致"
    }
  }
}
```

### 完整一鍵評測

使用 `run_full_eval.sh` 可以一鍵執行完整評測流程：

```bash
cd benchmark/locomo/vikingbot
bash run_full_eval.sh        # 完整流程
bash run_full_eval.sh --skip-import  # 跳過匯入，僅評測
```

### 單題/批次測試

使用 `import_and_eval_one.sh` 可以快速測試單個問題或批次測試某個 sample：

```bash
cd benchmark/locomo/vikingbot
```

**單題測試：**
```bash
./import_and_eval_one.sh 0 2          # sample 索引 0, question 2
./import_and_eval_one.sh conv-26 2    # sample_id conv-26, question 2
./import_and_eval_one.sh conv-26 2 --skip-import  # 跳過匯入
```

**批次測試單個 sample：**
```bash
./import_and_eval_one.sh conv-26       # conv-26 所有問題
./import_and_eval_one.sh conv-26 --skip-import
```

### 分步使用說明

#### 步驟 1: 匯入對話資料

使用 `import_to_ov.py` 將 LoCoMo 資料集匯入到 Business Data Platform：

```bash
python import_to_ov.py --input <資料檔案路徑> [選項]
```

**引數說明：**
- `--input`: 輸入檔案路徑（JSON 或 TXT 格式），預設 `./data/locomo10.json`
- `--sample`: 指定樣本索引（0-based），預設處理所有樣本
- `--sessions`: 指定會話範圍，例如 `1-4` 或 `3`，預設所有會話
- `--parallel`: 併發匯入數，預設 5
- `--force-ingest`: 強制重新匯入，即使已匯入過
- `--clear-ingest-record`: 清除所有匯入記錄
- `--openviking-url`: Business Data Platform 服務地址，預設 `http://localhost:1933`
- `--account`: 匯入時使用的 account，預設 `default`

**示例：**
```bash
# 匯入第一個樣本的 1-4 會話
python import_to_ov.py --input ./data/locomo10.json --sample 0 --sessions 1-4

# 強制重新匯入所有資料
python import_to_ov.py --input ./data/locomo10.json --force-ingest
```

#### 步驟 2: 執行 QA 評估

使用 `run_eval.py` 執行問答評估：

```bash
python run_eval.py <輸入資料> [選項]
```

**引數說明：**
- `input`: 輸入 JSON/CSV 檔案路徑，預設 `./data/locomo10.json`
- `--output`: 輸出 CSV 檔案路徑，預設 `./result/locomo_qa_result.csv`
- `--sample`: 指定樣本索引
- `--count`: 執行的 QA 問題數量，預設全部
- `--threads`: 併發執行緒數，預設 5

**示例：**
```bash
# 使用預設引數執行
python run_eval.py

# 指定輸入輸出檔案，使用 20 執行緒
python run_eval.py ./data/locomo_qa_1528.csv --output ./result/my_result.csv --threads 20
```

#### 步驟 3: LLM 裁判打分

使用 `judge.py` 對評估結果進行打分：

```bash
python judge.py [選項]
```

**引數說明：**
- `--input`: QA 結果 CSV 檔案路徑，預設 `./result/locomo_qa_result.csv`
- `--token`: API Token（也可通過 `ARK_API_KEY` 或 `OPENAI_API_KEY` 環境變數設定）
- `--base-url`: API 基礎 URL，預設 `https://ark.cn-beijing.volces.com/api/v3`
- `--model`: 裁判模型名稱，預設 `doubao-seed-2-0-pro-260215`
- `--parallel`: 併發請求數，預設 5

**示例：**
```bash
python judge.py --input ./result/locomo_qa_result.csv --token <your_token> --parallel 10
```

#### 步驟 4: 統計結果

使用 `stat_judge_result.py` 統計評分結果：

```bash
python stat_judge_result.py --input <評分結果檔案>
```

**引數說明：**
- `--input`: 評分結果 CSV 檔案路徑

**輸出統計資訊包括：**
- 正確率（Accuracy）
- 平均耗時
- 平均迭代次數
- Token 使用情況

---

## OpenClaw 評測流程

### 完整一鍵評測

使用 `openclaw/run_full_eval.sh` 可以一鍵執行完整評測流程：

```bash
cd benchmark/locomo/openclaw
bash run_full_eval.sh                      # 只匯入 Business Data Platform（跳過已匯入的）
bash run_full_eval.sh --with-claw-import   # 同時匯入 Business Data Platform 和 OpenClaw（並行執行）
bash run_full_eval.sh --skip-import        # 跳過匯入步驟，直接執行 QA 評估
bash run_full_eval.sh --force-ingest       # 強制重新匯入所有資料
bash run_full_eval.sh --sample 0           # 只處理第 0 個 sample
```

**指令碼引數說明：**

| 引數 | 說明 |
|------|------|
| `--skip-import` | 跳過匯入步驟，直接執行 QA 評估 |
| `--with-claw-import` | 同時匯入 Business Data Platform 和 OpenClaw（並行執行） |
| `--force-ingest` | 強制重新匯入所有資料（忽略已匯入記錄） |
| `--sample <index>` | 只處理指定的 sample（0-based） |

**指令碼執行流程：**
1. 匯入資料到 Business Data Platform（可選同時匯入 OpenClaw）
2. 等待 60 秒確保資料匯入完成
3. 執行 QA 評估（`eval.py qa`，輸出到 `result/qa_results.csv`）
4. 裁判打分（`judge.py`，並行度 40）
5. 統計結果（`stat_judge_result.py`，同時統計 QA 和 Import 的 token 使用）

**指令碼內部配置引數：**

在 `run_full_eval.sh` 指令碼頂部可以修改以下配置：

| 變數 | 說明 | 預設值                       |
|------|------|---------------------------|
| `INPUT_FILE` | 輸入資料檔案路徑 | `../data/locomo10.json`   |
| `RESULT_DIR` | 結果輸出目錄 | `./result`                |
| `GATEWAY_TOKEN` | OpenClaw Gateway Token | 需要設定為實際 openclaw 閘道器 token |

### 分步使用說明

OpenClaw 評測包含以下指令碼：
- `import_to_ov.py`: 匯入資料到 Business Data Platform
- `eval.py`: OpenClaw 評估指令碼（ingest/qa 兩種模式）
- `judge.py`: LLM 裁判打分
- `stat_judge_result.py`: 統計評分結果和 token 使用

---

#### import_to_ov.py - 匯入對話資料到 Business Data Platform

```bash
python import_to_ov.py [選項]
```

**引數說明：**
- `--input`: 輸入檔案路徑（JSON 或 TXT），預設 `../data/locomo10.json`
- `--sample`: 指定樣本索引（0-based）
- `--sessions`: 指定會話範圍，如 `1-4`
- `--question-index`: 根據 question 的 evidence 自動推斷需要的 session
- `--force-ingest`: 強制重新匯入
- `--no-user-id`: 不傳入 user_id 給 Business Data Platform 客戶端
- `--openviking-url`: Business Data Platform 服務地址，預設 `http://localhost:1933`
- `--success-csv`: 成功記錄 CSV 路徑，預設 `./result/import_success.csv`
- `--error-log`: 錯誤日誌路徑，預設 `./result/import_errors.log`

**示例：**
```bash
# 匯入所有資料（跳過已匯入的）
python import_to_ov.py

# 強制重新匯入，不使用 user id
python import_to_ov.py --force-ingest --no-user-id

# 只匯入第 0 個 sample
python import_to_ov.py --sample 0
```

---

#### eval.py - OpenClaw 評估指令碼

該指令碼有兩種模式：

##### 模式 1: ingest - 匯入對話資料到 OpenClaw

```bash
python eval.py ingest <輸入檔案> [選項]
```

**引數說明：**
- `--sample`: 指定樣本索引
- `--sessions`: 指定會話範圍，如 `1-4`
- `--force-ingest`: 強制重新匯入
- `--agent-id`: Agent ID，預設 `locomo-eval`
- `--token`: OpenClaw Gateway Token

**示例：**
```bash
# 匯入第一個樣本的 1-4 會話到 OpenClaw
python eval.py ingest locomo10.json --sample 0 --sessions 1-4 --token <token>
```

##### 模式 2: qa - 執行 QA 評估

- 該評測指定了 `X-OpenClaw-Session-Key`，確保每次 OpenClaw 使用相同的 session_id
- Token 計算統計 `session.jsonl` 檔案中的所有 assistant 輪次的 Token 消耗
- 每道題目執行完後會歸檔 session 檔案
- 支援併發執行（`--parallel` 引數）
- 問題會自動新增時間上下文（從最後一個 session 提取）

```bash
python eval.py qa <輸入檔案> [選項]
```

**引數說明：**
- `--output`: 輸出檔案路徑（不含 .csv 字尾）
- `--sample`: 指定樣本索引
- `--count`: 執行的 QA 問題數量
- `--user`: 使用者 ID，預設 `eval-1`
- `--parallel`: 併發數，預設 10，最大 40
- `--token`: OpenClaw Gateway Token（或設定 `OPENCLAW_GATEWAY_TOKEN` 環境變數）

**示例：**
```bash
# 執行所有 sample 的 QA 評估
python eval.py qa locomo10.json --token <token> --parallel 15

# 只執行第 0 個 sample
python eval.py qa locomo10.json --sample 0 --output qa_results_sample0
```

---

#### judge.py - LLM 裁判打分

```bash
python judge.py [選項]
```

**引數說明：**
- `--input`: QA 結果 CSV 檔案路徑
- `--parallel`: 併發請求數，預設 40

**示例：**
```bash
python judge.py --input ./result/qa_results.csv --parallel 40
```

---

#### stat_judge_result.py - 統計結果

同時統計 QA 結果和 Business Data Platform Import 的 token 使用：

```bash
python stat_judge_result.py [選項]
```

**引數說明：**
- `--input`: QA 結果 CSV 檔案路徑，預設 `./result/qa_results_sample0.csv`
- `--import-csv`: Import 成功 CSV 檔案路徑，預設 `./result/import_success.csv`

**輸出統計包括：**
- QA 結果統計：正確率、token 使用（no-cache、cacheRead、output）
- Business Data Platform Import 統計：embedding_tokens、vlm_tokens、total_tokens

**示例：**
```bash
python stat_judge_result.py --input ./result/qa_results_sample0.csv --import-csv ./result/import_success.csv
```

---

## 測試資料格式

### LoCoMo JSON 格式

```json
[
  {
    "sample_id": "sample_001",
    "conversation": {
      "speaker_a": "Alice",
      "speaker_b": "Bob",
      "session_1": [
        {
          "speaker": "Alice",
          "text": "你好，我是 Alice",
          "img_url": [],
          "blip_caption": ""
        }
      ],
      "session_1_date_time": "9:36 am on 2 April, 2023"
    },
    "qa": [
      {
        "question": "Alice 叫什麼名字？",
        "answer": "Alice",
        "category": "1",
        "evidence": []
      }
    ]
  }
]
```

### CSV 格式（QA 資料）

必須包含欄位：
- `sample_id`: 樣本 ID
- `question`: 問題
- `answer`: 標準答案

---

## 輸出檔案說明

| 檔案 | 說明 |
|------|------|
| `result/locomo_qa_result.csv` | QA 評估原始結果 |
| `result/judge_result.csv` | 包含裁判打分的結果 |
| `result/summary.txt` | 統計摘要 |
| `result/import_success.csv` | 匯入成功記錄 |
| `result/import_errors.log` | 匯入錯誤日誌 |

---

## 環境變數

| 變數名 | 說明 |
|--------|------|
| `ARK_API_KEY` | 火山引擎 API Key（用於 judge.py） |
| `OPENAI_API_KEY` | OpenAI API Key（備選） |
| `OPENCLAW_GATEWAY_TOKEN` | OpenClaw Gateway Token |

---

## 常見問題

### Q: 如何中斷後繼續評測？
A: 所有指令碼都支援斷點續傳，重新執行相同命令會自動跳過已處理的專案。

### Q: 如何強制重新執行？
A: 使用 `--force-ingest`（匯入）或刪除結果 CSV 檔案。

### Q: 評測速度慢怎麼辦？
A: 增加 `--threads`（run_eval.py）或 `--parallel`（其他指令碼）引數值。

### Q: 評測效果低，怎麼排查 Business Data Platform 匯入與評測查詢的 account/user 是否一致？
A: 先核對三處是否對齊：`ovcli.conf.account`（匯入 account）、`ov.conf.bot.ov_server.account_id`（Vikingbot 查詢 account）、評測指令碼使用的 user（Vikingbot 按 `sample_id`，OpenClaw 預設 `eval-1`）。這幾項不一致時，常見現象是“匯入看起來成功，但評測回答質量明顯下降或查不到上下文”。

---

## 常見問題排查

### 1. 檢查 Business Data Platform 資料匯入是否成功

匯入完成後，檢視 `import_success.csv`：

```bash
cd benchmark/locomo/openclaw
wc -l result/import_success.csv
```

- **預期結果**：總共約 270+ session（包含表頭）
- **如果數量不符**：
  - 檢查 `result/import_errors.log` 檢視錯誤日誌
  - 使用 `--force-ingest` 重新匯入

### 2. 檢查 QA 回答是否正常

查看 `qa_results.csv` 的 `response` 列：

```bash
cd benchmark/locomo/openclaw
# 檢視前幾行
head -n 5 result/qa_results.csv

# 查看是否有 ERROR
grep -i "error" result/qa_results.csv
```

**檢查內容：**
- `response` 列不應為空或報錯資訊
- `result` 列（judge 後）應有 `CORRECT` 或 `WRONG`

### 3. 驗證 Business Data Platform 記憶是否被正確載入

如果 QA 回答不正常，可以檢查 session 檔案確認記憶是否被載入：

1. 從 `qa_results.csv` 的 `jsonl_filename` 列獲取 session 檔名：
   ```
   jsonl_filename
   5d497c96-9fb6-480c-be06-0c0849e193e9.jsonl.20260408_181433
   ```

2. 在 OpenClaw 工作目錄檢視對應的 session 檔案：
   ```bash
   ls ~/.openclaw/agents/locomo-eval/sessions/
   ```

3. 檢視 session 檔案內容，確認 query 前是否有記憶內容：
   ```bash
   cat ~/.openclaw/agents/locomo-eval/sessions/<jsonl_filename> | grep -A 20 "type.*message"
   ```

**預期結果**：在使用者提問（query）之前，應該有從 Business Data Platform 載入的記憶內容。

### 4. 評測效果低時，先口語化排查 account/user

如果你感覺“明明匯入了，回答還是不對勁”，先按這個順序看：

1. 開啟 `~/.openviking/ovcli.conf`，看 `account` 是不是你這次要用的帳號。
2. 開啟 `~/.openviking/ov.conf`，重點看：
   - `bot.ov_server.account_id`
   - `server.host` / `server.port`
3. 跑 Vikingbot 指令碼時留意 preflight 日誌裡列印的 `account` 和 `Business Data Platform URL`，確認和你配置裡看到的一致。
4. 記住查詢側是誰在查：
   - Vikingbot 評測預設用 `sample_id` 當 user。
   - OpenClaw QA 預設是 `--user eval-1 --agent-id locomo-eval`。
   - 你如果改過 OpenClaw 的 `--user` 或 `--agent-id`，要保證 ingest 和 qa 兩邊用的是同一套值。

一句話：匯入時的 account/user、評測時的 account/user、以及連線的服務地址，這三件事只要有一個沒對齊，就很容易出現效果低或“查不到上下文”。

### 5. Token 統計異常

如果 `stat_judge_result.py` 輸出的 token 數量異常：

- **Import token 為 0**：檢查 `import_success.csv` 是否存在且有資料
- **QA token 為 0**：檢查 `qa_results.csv` 的 `input_tokens`/`output_tokens` 列
- **CacheRead 很高**：說明多次執行相同問題，命中了快取
