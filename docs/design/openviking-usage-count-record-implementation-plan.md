# File Usage Event Log Implementation Plan

**Goal:** 將 Usage Reporter 生成的 `UsageEvent` 轉換為穩定的
計量日誌協議，供部署側日誌採集系統讀取並投遞到下游。

**Architecture:** `MemoryUsageExtractor` 繼續生成內部 `UsageEvent`。
`FileLogUsageSink` 在寫入專用日誌檔案前執行單向轉換，每行儲存一個扁平 JSON
計量事件。`object_id` 作為穩定事件標識，供下游在 best-effort 投遞發生重複時
與 `tenant_id` 組成複合鍵去重。

**Tech Stack:** Python 3.10+、dataclasses、標準庫
`datetime` / `json` / `logging`、pytest、Ruff。

---

## 檔案結構

- `openviking/usage_reporter/file_log_sink.py`
  - 定義 `UsageEvent -> 計量日誌` 私有轉換。
  - 構造資源歸屬 `tenant_id`。
  - 將記錄追加到按 UTC 小時滾動的專用日誌檔案。
- `tests/unit/usage_reporter/test_file_log_sink.py`
  - 固定 recall/inject 欄位對映、UTC 時間、租戶欄位和未知事件行為。
  - 驗證多 worker 共享檔案時的寫入和滾動行為。
- `docs/design/openviking-usage-reporter-sink-design.md`
  - 定義 Usage Reporter、Sink 擴充點和檔案日誌協議。

## 計量日誌對映契約

`memory.recalled` 事件對映為：

```json
{
  "event_time": "2026-08-05 11:30:00",
  "tenant_id": "resource_id:ov-resource-id;account_id:2101858484;user_id:user-1;resource_uri:viking://user/user-1/memories/experiences/exchange.md",
  "event_name": "experience.recall.count",
  "object_id": "ue_recall",
  "count": 1,
  "tags": {
    "resource_type": "experience"
  }
}
```

對映規則：

- `memory.recalled` 對映為 `event_name=experience.recall.count`。
- `memory.injected` 對映為 `event_name=experience.inject.count`。
- `count` 固定為 `1`。
- `occurred_at` 轉換為 UTC `YYYY-MM-DD HH:MM:SS`。
- `event_id` 寫入 `object_id`，為空時拒絕寫入。
- `tenant_id` 拼接部署 `resource_id`、`account_id`、`user_id` 和 `resource_uri`。
- `resource_id` 從 `resource_id_env` 指定的環境變數讀取，未配置時拒絕啟動 Sink。
- `tags.resource_type` 記錄資源型別。
- 未知 `event_type` 拒絕寫入，避免產生無法解釋的計量記錄。

## 檔案日誌協議

日誌行格式：

```text
{"event_time":"<UTC time>","tenant_id":"resource_id:<resource>;account_id:<account>;user_id:<user>;resource_uri:<uri>","event_name":"<event>","object_id":"<event_id>","count":1,"tags":{"resource_type":"experience"}}
```

日誌檔案不復用 OpenViking stdout，按 UTC 小時滾動，並保留配置數量的歷史
檔案。多個 server worker 寫入同一路徑時，檔案追加和滾動通過程序間鎖序列化。

檔案落盤及後續採集均採用 best-effort 語義。下游必須按
`(tenant_id, object_id)` 複合鍵去重，不能跨 tenant 僅按 `object_id` 全域去重。
次數查詢按 `tenant_id`、`event_name` 和 `event_time` 範圍過濾，並計算
`sum(count)`。

## 驗證

```bash
uv run pytest -q --no-cov tests/unit/usage_reporter
uv run ruff check \
  openviking/usage_reporter/file_log_sink.py \
  tests/unit/usage_reporter/test_file_log_sink.py
uv run ruff format --check \
  openviking/usage_reporter/file_log_sink.py \
  tests/unit/usage_reporter/test_file_log_sink.py
git diff --check
```
