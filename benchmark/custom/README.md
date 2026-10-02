# Business Data Platform Server 壓測指令碼使用指南

本目錄包含面向 Business Data Platform 本地 Server 的自定義壓測指令碼。當前主要指令碼是：

- `session_contention_benchmark.py`：通用 Server 壓測框架，覆蓋 SDK、CLI HTTP 封裝和真實 `ov` 子程序三種呼叫路徑。

## 壓測目標

`session_contention_benchmark.py` 用來請求已經啟動的 Business Data Platform Server，驗證多類介面在併發和混合負載下的吞吐、延遲、失敗率和後臺任務積壓情況。

指令碼不會啟動或停止 Server，只負責：

1. 生成本地 Markdown 測試文件。
2. 每次執行前預設清空上一次壓測寫入的資料目錄。
3. 併發請求資源新增、檢索、session 寫入、session commit、任務輪詢和觀測介面。
4. 輸出中文壓測報告和機器可讀明細檔案。

## 前置條件

先在另一個終端啟動 Business Data Platform Server：

```bash
openviking-server
```

如果 Server 啟用了 API Key 或多租戶，請準備好以下資訊：

- Server 地址，例如 `http://127.0.0.1:1935`
- API Key，預設引數會使用 `test-root-api-key`
- Account，預設 `default`
- User，預設 `default`

真實 CLI 子程序模式還要求當前環境能執行 `ov`：

```bash
ov health
```

## 快速開始

在倉庫根目錄執行 smoke 壓測：

```bash
.venv/bin/python benchmark/custom/session_contention_benchmark.py \
  --server-url http://127.0.0.1:1935 \
  --profile smoke
```

只測試 Python SDK 路徑：

```bash
.venv/bin/python benchmark/custom/session_contention_benchmark.py \
  --server-url http://127.0.0.1:1935 \
  --profile smoke \
  --adapters sdk
```

同時測試 SDK、CLI HTTP 封裝和真實 `ov` 子程序：

```bash
.venv/bin/python benchmark/custom/session_contention_benchmark.py \
  --server-url http://127.0.0.1:1935 \
  --profile standard \
  --adapters sdk,cli-http,cli-subprocess
```

## 呼叫路徑說明

指令碼支援三種 adapter：

| Adapter | 含義 | 適用場景 |
| --- | --- | --- |
| `sdk` | 通過 `openviking.AsyncHTTPClient` 請求 Server | 評估 Python SDK 的 HTTP 呼叫表現 |
| `cli-http` | 直接使用 `openviking_cli.client.http.AsyncHTTPClient` | 評估 CLI 共用 HTTP client 層表現 |
| `cli-subprocess` | 每次請求真實執行一次 `ov ... --output json` | 評估真實 CLI 程序啟動、配置讀取、上傳和輸出解析成本 |

預設會同時執行三種路徑：

```bash
--adapters sdk,cli-http,cli-subprocess
```

如果只關心 Server 吞吐，建議先跑 `sdk` 或 `cli-http`。如果關心使用者實際執行 CLI 命令的端到端成本，再加入 `cli-subprocess`。

## 壓測場景

每個 adapter 會依次執行以下階段：

| 階段 | 內容 |
| --- | --- |
| `warmup` | 健康檢查預熱 |
| `add_resources` | 併發新增多個生成的 Markdown 文件 |
| `session_messages` | 併發向不同 session 寫入多輪 user / assistant 訊息 |
| `retrieval` | 併發執行 `find`、`search`、`grep`、`glob` |
| `session_commit` | 併發 commit 不同 session，並輪詢後臺任務 |
| `mixed` | 混合資源新增、檢索、session 寫入、commit、觀測介面和任務輪詢 |

這些階段不是隻壓單個介面，目的是觀察 Business Data Platform 在真實組合負載下的退化情況。

## 資料清理策略

預設每次執行前會清理：

- Server 側資源目錄：`viking://resources/bench/load_test`
- 舊 session：所有 `bench-load-` 字首的 session
- 本地生成資料目錄：`benchmark/results/openviking_server_load/data`

預設執行結束後保留本次寫入的資料，方便人工複查。下一次執行前會再次清空。

如果不想在執行前清理：

```bash
--no-clear-before-run
```

如果希望執行結束後也清理：

```bash
--cleanup-at-end
```

## 常用引數

| 引數 | 預設值 | 說明 |
| --- | --- | --- |
| `--server-url` | `http://127.0.0.1:1935` | Business Data Platform Server 地址 |
| `--api-key` | `test-root-api-key` | 請求使用的 API Key |
| `--account` | `default` | 請求使用的 account |
| `--user` | `default` | 請求使用的 user |
| `--adapters` | `sdk,cli-http,cli-subprocess` | 要測試的呼叫路徑 |
| `--profile` | `standard` | 壓測規模：`smoke`、`standard`、`stress` |
| `--resource-count` | 跟隨 profile | 每個 adapter 新增的初始文件數 |
| `--session-count` | 跟隨 profile | 每個 adapter 使用的 session 數 |
| `--phase-seconds` | 跟隨 profile | 單類持續壓測階段時長 |
| `--mixed-seconds` | 跟隨 profile | 混合壓測階段時長 |
| `--drain-timeout` | `60` | 等待後臺任務完成的最大秒數 |
| `--data-root-uri` | `viking://resources/bench/load_test` | Server 側壓測資源根目錄 |
| `--output-dir` | 自動生成 | 報告輸出目錄 |
| `--ov-bin` | `ov` | 真實 CLI 子程序使用的執行檔 |

## Profile 說明

| Profile | 用途 | 特點 |
| --- | --- | --- |
| `smoke` | 快速驗證指令碼、配置和 Server 可用性 | 時間短、併發低、資料少 |
| `standard` | 常規壓測 | 預設推薦配置 |
| `stress` | 高壓力壓測 | 併發和資料量更高，耗時更長 |

建議先跑 `smoke`，確認報告正常生成後再跑 `standard` 或 `stress`。

## 報告輸出

預設輸出目錄類似：

```text
benchmark/results/openviking_server_load/20260511T120000Z/
```

主要文件：

| 檔案 | 內容 |
| --- | --- |
| `summary_zh.md` | 中文壓測報告，優先閱讀 |
| `run_summary.json` | 彙總結果，便於自動分析 |
| `request_events.jsonl` | 每次請求的明細事件 |
| `task_events.jsonl` | 後臺任務完成和積壓明細 |
| `request_summary.csv` | 按 adapter / 階段 / 介面聚合的 QPS、成功率、延遲 |
| `request_windows.csv` | 按時間視窗聚合的請求表現 |
| `adapter_comparison.csv` | SDK / CLI 路徑對比 |
| `errors.csv` | 錯誤 Top 明細 |

報告會重點展示：

- 總請求量、失敗數和成功率。
- 各介面 p50 / p95 / p99 / max 延遲。
- `retrieval` 階段到 `mixed` 階段的檢索延遲變化。
- SDK、CLI HTTP 封裝、真實 CLI 子程序之間的差異。
- commit / add_resource 後臺任務是否積壓。
- Top 錯誤型別和發生位置。

## 示例：指定認證資訊

```bash
.venv/bin/python benchmark/custom/session_contention_benchmark.py \
  --server-url http://127.0.0.1:1935 \
  --api-key your-root-api-key \
  --account default \
  --user default \
  --profile standard
```

也可以通過環境變數傳入：

```bash
export OPENVIKING_SERVER_URL=http://127.0.0.1:1935
export OPENVIKING_API_KEY=your-root-api-key
export OPENVIKING_ACCOUNT=default
export OPENVIKING_USER=default

.venv/bin/python benchmark/custom/session_contention_benchmark.py --profile smoke
```

## 示例：降低真實 CLI 子程序開銷

真實 `cli-subprocess` 會為每個請求啟動一次 `ov` 程序，開銷明顯高於 SDK 路徑。若只想壓 Server 本身，可以先排除它：

```bash
.venv/bin/python benchmark/custom/session_contention_benchmark.py \
  --profile standard \
  --adapters sdk,cli-http
```

若必須測試真實 CLI，但本地 `ov` 不在 PATH 中，可以指定執行檔：

```bash
.venv/bin/python benchmark/custom/session_contention_benchmark.py \
  --profile smoke \
  --adapters cli-subprocess \
  --ov-bin .venv/bin/ov
```

## 常見問題

### 1. Server 連線失敗

先確認 Server 已啟動：

```bash
curl http://127.0.0.1:1935/health
```

如果埠不同，請設定 `--server-url`。

### 2. 認證失敗

確認 `--api-key`、`--account`、`--user` 與當前 Server 配置一致。多租戶模式下，root key 請求通常還需要 account 和 user。

### 3. `cli-subprocess` 失敗

確認 `ov` 可執行：

```bash
ov health
```

如果不可用，使用 `--ov-bin .venv/bin/ov` 或只執行 `sdk,cli-http`。

### 4. 後臺任務沒有在 drain 內完成

這通常說明資源處理或 session commit 的後臺任務積壓。可以：

- 增大 `--drain-timeout`
- 降低併發引數
- 查看 `task_events.jsonl`
- 檢視 Server 日誌和 observer queue 狀態

### 5. 多次執行結果差異較大

壓測會受本機 CPU、磁碟、模型配置、佇列積壓和真實 CLI 程序啟動開銷影響。建議：

1. 先跑 `smoke` 驗證環境。
2. 連續跑多次 `standard`。
3. 對比 `adapter_comparison.csv` 和 `request_windows.csv`。
4. 避免在已有大量後臺任務未完成時啟動下一輪。
