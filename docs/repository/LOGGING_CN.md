# 開發者日誌規範

按記錄用途選擇級別。規則適用於 OpenViking 自有程式碼，第三方依賴保留原有級別語義。日誌改動不新增審計介面或儲存。

配置見[配置指南](../zh/guides/01-configuration.md)，Python 輸出實現見 [logger.py](../../openviking_cli/utils/logger.py)，安全欄位工具見 [log_safety.py](../../openviking/observability/log_safety.py)。

## 1. 選擇級別

| 級別 | 用途 | 示例 |
| --- | --- | --- |
| `CRITICAL` | 程序無法繼續 | 啟動致命失敗、程序狀態不可恢復 |
| `ERROR` | 需要介入的最終失敗 | 請求或任務失敗、重試耗盡、資料丟失風險、安全防護失效 |
| `WARNING` | 僅用於安全審計 | 認證失敗、許可權或成員變更、金鑰生命週期、敏感配置與資料操作 |
| `INFO` | 自愈、狀態變化與預期拒絕 | 重試退避、兜底、熔斷切換、啟動關閉、遷移、批次彙總、4xx 拒絕 |
| `DEBUG` | 業務過程與排障明細 | 決策依據、中間結果、快取行為、成功操作細節 |

- 單次重試記 `INFO`，最終失敗只記一條 `ERROR`。在實際執行兜底的邊界記錄所用方案和結果；結果不完整時標記 `degraded=true`。
- 模型回覆成功不能兜住對話或記憶寫入失敗。恢復若依賴客戶端後續輪次重發歷史，仍記 `ERROR`。
- 預期的 4xx 響應記 `INFO`，不帶堆疊；認證失敗或越權拒絕另留一條安全審計 `WARNING`。
- `api_key` 模式下，ROOT 身份的每次呼叫都必須留審計 `WARNING`，含只讀呼叫，禁止取樣。dev/trusted 模式、未認證路由和程序內構造的 ROOT 上下文不適用此規則。
- 觀測/指標失敗不得影響業務：首次 `ERROR`，後續 `INFO`。普通重試、兜底、慢呼叫和髒資料跳過不使用審計 `WARNING`。

## 2. 寫有用、適量的日誌

- 最終結果由決定處理方式的邊界記錄一次；中間層傳播異常或提供 `DEBUG` 明細。
- 使用穩定英文模板，小寫開頭、不加句號。模組由日誌頭標識，避免手寫模組字首和沒有資訊量的“開始/完成”。
- Python 使用 `get_logger(__name__)` 和惰性引數：`logger.info("retry attempt=%d", attempt)`。不通過 f-string、字串拼接、`%` 插值或 `.format()` 構造訊息。其他執行時使用自身的結構化/惰性介面。
- 需要檢索、聚合的維度放在 `extra`，使用統一欄位名，如 `operation`、`http_route`、`http_status_code`、`duration_ms`、`error_code`、`error_type`、`total`、`failed`、`skipped`。
- 迴圈與批次降級使用一條帶計數的 `INFO` 彙總，加 `DEBUG` 明細；高頻過程資訊記 `DEBUG`。昂貴的日誌專用計算先檢查 `isEnabledFor()`，簡單計數和 hash 可直接計算。
- 訊息不超過 2 KB，欄位值不超過 1 KB。截斷保留有效 UTF-8，並標記 `truncated=true`、`original_length`。

## 3. 保證內容安全

訊息、`extra`、Trace 屬性、審計記錄和子程序診斷遵守同一規則。格式化或憑證模式過濾不能保證任意文本安全。

| 內容 | 規則 |
| --- | --- |
| 可信身份/關聯 ID、任務 ID/狀態、固定操作/錯誤碼、異常型別、數量、耗時、檔案型別 | 使用已校驗 ID、固定列舉或基礎型別；未明確允許的欄位預設禁止。 |
| 路由與入口後設資料 | 路由只用模板，不輸出真實路徑或查詢串。IP 來自校驗後的連線或可信代理資訊；User-Agent 只保留白名單產品/版本摘要，最多 256 位元組。不安全的值不輸出。 |
| 路徑、URI、資源定位 | 使用 `safe_path_for_log()` / `safe_uri_for_log()` 或 `short_hash()`。僅可信且不敏感的名稱可原樣輸出；使用者控制或租戶路徑必須轉換。 |
| 異常 | 優先記錄 `type(exc).__name__` 和穩定 `error_code`。不輸出原始異常文本或物件；`sanitize_error()`、`sanitize_public_http_error()` 僅提供部分保護。 |
| 憑證、Privacy 明文、`peer_id`、絕對路徑、提示詞、訊息、文件/記憶/Skill 正文、模型輸入輸出、工具引數/結果、完整請求響應體 | 禁止輸出，改用數量、長度、型別或 hash。URI 中的 peer 段同樣受限。 |
| 完整物件與任務 `meta` | 不用 `%s`、`%r`、`asdict()`、`model_dump()` 整體輸出。選取安全欄位，排除任意後設資料值；`repr=False` 不能保護序列化。 |

- 金鑰、Token、Cookie、簽名頭、預簽名 URL、連線串憑證及可重建金鑰的片段禁止輸出。顯式啟用的金鑰診斷展示可通過 `mask_api_key()` 僅顯示末四位。
- 堆疊僅限顯式本地排障時以 `ERROR` 輸出，且須先清理異常訊息、原始碼和路徑；`exc_info=True` 不能繞過這一要求。
- 欄位允許輸出不代表可以把原始內容拼入訊息。即使在 `DEBUG` 或啟用 `log_payloads` 時，也優先使用安全摘要。

```python
from openviking.observability.log_safety import safe_uri_for_log
from openviking_cli.utils import get_logger

logger = get_logger(__name__)
logger.info(
    "resource read failed; using cached result error_type=%s",
    type(exc).__name__,
    extra={"target_id": safe_uri_for_log(uri), "error_type": type(exc).__name__, "degraded": True},
)
```

## 4. 使用統一輸出

```text
2026-11-13T22:56:01.028Z INFO openviking.server.bootstrap pid=452394 request_id=- trace_id=- message="server started"
```

- 順序為 `ts level logger pid request_id trace_id message`，其後追加結構化欄位。時間取事件發生時刻，使用 UTC、固定毫秒精度；PID 和模組/元件名屬於事件來源。
- 級別名統一為 `DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`；對映 `TRACE→DEBUG`、`WARN→WARNING`、`FATAL→CRITICAL`，不改變第三方事件語義。Rust 沒有原生 `CRITICAL`，將其閾值對映到 `ERROR` 無法只篩選致命事件。
- 每條事件佔一行 UTF-8，不帶 ANSI 顏色、Rich 佈局、自動換行或進度條。訊息和字串按 JSON 規則引用、轉義；數字和布林值保留型別。缺失 ID 在文本中為 `-`，結構化記錄中為 `null`；控制字元必須轉義。
- 關聯 ID 由統一適配層注入。業務異常後設資料不得用 provider request ID 覆蓋請求/後臺任務的 `request_id`。
- server 入口統一管理 root、Uvicorn、MCP、APScheduler 和原生輸出的 handler、閾值與格式。業務模組不安裝 `basicConfig`、獨立 handler 或 loguru sink。僅支援統一格式；worker 初始化和配置過載不得重複輸出；原生設定需要重啟時須明確說明。
- SDK 匯入不接管宿主 root logger。合併到服務日誌的子程序輸出保留自身 PID/元件名並遵守同一格式；未適配的輸出寫入有明確來源的獨立檔案。
- **bootstrap 進度、依賴檢查、啟動結果和失敗直接 `print(..., flush=True)`**，不受日誌閾值或檔案輸出影響。失敗寫 stderr，其餘狀態寫 stdout，內容仍遵守第 3 節。
- 互動式 CLI 的結果/進度及協議輸出使用各自展示方式；診斷資訊不得汙染機器可讀 stdout 或 stdio 協議。

## 5. 安全審計要求

審計覆蓋帳號/成員、ACL 與許可權、金鑰生命週期和身份繫結、認證/越權失敗、敏感配置與資料寫入、刪除/匯出，以及第 1 節約定的 ROOT 呼叫。

- 執行後記錄一次真實成功或失敗，禁止取樣。審計副本同時按 `logger=openviking.audit` 和已登記的 `audit.*` 事件識別，不能只按 `WARNING` 路由。
- 完整記錄包含 `ts`、`event`、`action`、`result`、`actor_id`、`actor_role`、`actor_type`、`account_id`、`target_type`、`target_id`、`request_id`、`trace_id`、`source_ip`、`user_agent`、`error_code`。`action` 取事件名末段，`result` 為 `success`/`failure`，主體型別為 `user`/`admin`/`root`/`service`。
- 未知身份、缺失上下文、成功時的 `error_code` 使用 `null`，不把請求中自報的值當已認證身份。ROOT 記錄還含路由模板、HTTP 方法/狀態，高風險操作標記 `sensitive=true`；root API key 使用 `actor_id=root-key`，不虛構使用者或帳號。
- 日誌副本和可查詢的持久審計事件使用同一組安全欄位，並核實已持久化；best-effort 事件釋出或 Usage/Audit HTTP 記錄不等於安全事件已落庫。審計設施失敗記安全的 `ERROR`，不回滾業務操作。

## 6. 合入前檢查

- 級別符合實際結果；重試、兜底和批次降級可見；最終失敗只記錄一次。
- 訊息、欄位、異常和巢狀物件不含禁止值，ID 來自可信上下文。
- 對修改的 Python 日誌執行 Ruff `G` 檢查；它檢查呼叫寫法，不判斷級別語義或內容安全。
- 複用現有迴歸測試，必要時調整日誌斷言；避免新增測試檔案和 Mock 呼叫測試。失敗路徑可用臨時輸出捕獲驗證。
- 初始化/原生適配改動須檢查實際輸出：UTC 與 Asia/Shanghai、重定向/非 TTY、重複初始化/過載、多 worker、不同閾值。驗證時間、級別、欄位、單行格式、重複記錄和上下文隔離；bootstrap print 單獨驗收。
