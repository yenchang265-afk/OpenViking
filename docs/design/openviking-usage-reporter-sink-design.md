# OpenViking Usage Reporter / Sink 技術方案

## 1. 背景

OpenViking 在 session commit 時會收到完整的 session messages。Agent runtime 呼叫 tool 後，會在 session messages 中留下 tool parts。部分 tool parts 可以表達某個記憶檔案被檢索、讀取、注入等行為。

OpenViking 需要從 session 中解析出這些使用行為，並將結構化事件交給可擴充的下游。核心不繫結具體訊息佇列、Webhook、日誌系統或資料庫，而是提供通用的 Usage Reporter / Sink 擴充機制。

## 2. 業界做法

這種模式是開源基礎設施裡常見的設計。

OpenTelemetry Collector 把資料鏈路拆成 receivers、processors、exporters、pipelines。exporters 專門負責把資料傳送到不同 backend 或 destination，例如 OTLP、Kafka、Prometheus、file 等。配置 exporter 本身不代表啟用，需要在 pipeline 中宣告。

參考：https://opentelemetry.io/docs/collector/configuration/

Vector 使用 sinks 概念，把 observability data 投遞到不同目的地，例如 File、HTTP、Kafka、S3、ClickHouse、Prometheus remote write 等。

參考：https://vector.dev/docs/reference/configuration/sinks/

Fluent Bit 使用 Outputs 概念。官方定義裡，Outputs 用來定義資料目的地，常見目的地包括遠端服務、本地檔案系統或標準介面，並且 Outputs 以 plugin 形式實現。

參考：https://docs.fluentbit.io/manual/data-pipeline/outputs

所以 OpenViking 採用“核心定義事件 + 外掛式 Sink 輸出”是合理的。它的核心價值是把“事件產生”和“事件去哪”解耦。

## 3. 設計目標

- OpenViking 核心只定義 UsageEvent 標準結構。
- OpenViking 核心負責從 session commit 中解析 UsageEvent。
- OpenViking 核心不繫結具體下游及其依賴。
- 部署方可以通過自定義 Sink 接入目標系統。
- Sink 失敗預設不影響 session commit。
- 預設不上報完整 session，只上報結構化事件，並保留定位原始 session ToolPart 所需的證據資訊。

## 4. 總體架構

資料流：

```text
Agent runtime 呼叫 tool
-> session message 留下 tool part
-> client 上傳 session 並 commit
-> OpenViking archive session
-> UsageExtractor 從 session messages 解析 UsageEvent
-> UsageReporter 分發 UsageEvent
-> UsageSink 寫入目標系統
```

模組拆分：

```text
UsageExtractor：負責從 session 裡解析事件
UsageEvent：標準結構化事件
UsageReporter：負責分發事件
UsageSink：負責寫入不同下游
```

## 5. UsageEvent

UsageEvent 是 OpenViking 核心和外部 Sink 之間的穩定協議。

示例：

```json
{
  "schema_version": "v1",
  "event_id": "ue_<sha256>",
  "event_type": "memory.injected",
  "resource_uri": "viking://user/test/memories/experiences/xxx.md",
  "resource_type": "experience",
  "account_id": "new",
  "user_id": "test",
  "session_id": "510bb5f9-4671-498e-adf4-27bb1b3691fe",
  "task_id": "b174eb56-e7d4-4fee-98a6-c53c0ddf62ed",
  "occurred_at": "2026-07-09T12:00:00Z",
  "evidence": {
    "archive_uri": "viking://user/test/sessions/510bb5f9/history/archive_001",
    "message_id": "msg_xxx",
    "tool_call_id": "call_xxx",
    "tool_name": "mcp__openviking__read"
  },
  "attributes": {}
}
```

預設只上報結構化事件，不上報完整 session 內容。

`resource_uri` 和 `resource_type` 描述被使用的資源，不限定為記憶檔案；事件型別特有的資料寫入 `attributes`。當前 `MemoryUsageExtractor` 只接受屬於 `UsageContext.user_id` 的規範 experience URI，其他使用者 URI 不生成 UsageEvent。ToolPart 必須包含非空 `tool_id`，無法穩定標識具體呼叫的 ToolPart 不進入統計。

UsageEvent 是可獨立傳輸和消費的完整事件。`UsageContext` 只用於 Extractor 構造事件，不再重複傳給 Sink。

### 5.1 Experience 使用事件識別

外掛使用 OpenViking 原生通用工具消費 Experience，不額外註冊 Experience 專用工具：

- 成功的 `find`、`search`、`list` 呼叫結果中出現 Experience URI，產生 `memory.recalled`。
- 成功的 `read`、`multi_read` 呼叫實際讀取 Experience URI，產生 `memory.injected`。
- 支持 OpenCode 的 `openviking_*`、OpenClaw 的 `ov_*` 和
  `mcp__openviking__*` 名稱空間形式；僅按受支援的工具名精確識別。
- 通用工具返回其他記憶型別時，只保留當前使用者 `memories/experiences/` 目錄下的規範檔案 URI。
- 只識別上述正式通用工具，不為未釋出的專用工具名提供解析或配置相容。

## 6. UsageSink 機制

OpenViking 開源包定義統一的 Sink 抽象：

```python
class UsageSink:
    async def write(self, *, events: list[UsageEvent]) -> None:
        ...
```

具體 Sink 可以作為外部擴充通過 `class_path` 動態載入。開源包同時提供不依賴第三方訊息佇列 SDK 的內建檔案日誌 Sink，供日誌採集系統讀取。

配置示例：

```yaml
server:
  usage_reporter:
    enabled: true
    sinks:
      - type: custom
        class_path: example_usage.custom_sink.CustomUsageSink
        config:
          endpoint: https://usage.example.com/events
```

OpenViking 用 `importlib` 動態載入：

```python
import importlib

def load_class(class_path: str):
    module_name, class_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)
```

只有配置了該 Sink 時才 import 對應模組。OpenViking 核心不 import 或安裝具體下游依賴。

每個 Sink 的 `write()` 呼叫最多等待 5 秒。超時或異常只記錄日誌，不影響其他 Sink。Reporter 在應用生命週期內只建立一次，應用退出時呼叫 Sink 可選的 `close()` 方法。同步和非同步 `close()` 均受同一超時限制；同步 hook 在獨立 daemon 執行緒中執行，超時後不會阻塞事件迴圈、後續 Sink 清理或程序退出。

內建檔案日誌 Sink 將事件立即追加到專用日誌檔案，不寫預設 stdout，也不發起
HTTP 請求。日誌檔案使用 UTC 小時滾動，預設保留 168 個小時檔案。部署側應將
專用目錄掛載到日誌採集系統可見的宿主機路徑。多個 server worker 寫入同一路徑
時，通過程序間檔案鎖序列化寫入和滾動；Windows worker 寫入後主動關閉檔案控制代碼，
避免其他程序滾動重新命名失敗。

### 6.1 檔案日誌計量協議

`UsageEvent` 繼續作為 OpenViking 內部抽取結果和自定義 Sink 的穩定協議。內建
檔案日誌 Sink 將 `UsageEvent` 轉換為計量接收端使用的扁平 JSON。每個事件寫成
一行：

```json
{"event_time":"2026-08-05 11:30:00","tenant_id":"resource_id:ov-xxx;account_id:new;user_id:test;resource_uri:viking://user/test/memories/experiences/example.md","event_name":"experience.recall.count","object_id":"ue_<sha256>","count":1,"tags":{"resource_type":"experience"}}
```

字段映射：

- `event_time` 由 `occurred_at` 轉換為 UTC `YYYY-MM-DD HH:MM:SS`。
- `tenant_id` 固定為
  `resource_id:<resource_id>;account_id:<account_id>;user_id:<user_id>;resource_uri:<resource_uri>`。
- `memory.recalled` 對映為 `event_name=experience.recall.count`。
- `memory.injected` 對映為 `event_name=experience.inject.count`。
- `object_id` 使用穩定的 `event_id`。下游以 `(tenant_id, object_id)` 作為複合去重鍵，
  不跨 tenant 單獨按 `object_id` 去重。
- `count` 固定為 `1`。
- `tags.resource_type` 固定記錄被使用資源的型別；本期只產生
  `experience` 使用事件。

接收端按 `tenant_id`、`event_name` 和 `event_time` 範圍過濾，並通過
`sum(count)` 聚合使用次數。

無法識別的 `event_type` 不生成含義不明確的計量記錄，轉換時丟擲錯誤並由
Reporter 的 best-effort 隔離機制處理。

## 7. 配置設計

預設關閉：

```yaml
server:
  usage_reporter:
    enabled: false
```

自定義 Sink：

```yaml
server:
  usage_reporter:
    enabled: true
    sinks:
      - type: custom
        class_path: example_usage.custom_sink.CustomUsageSink
        config:
          endpoint: https://usage.example.com/events
```

內建檔案日誌 Sink：

```yaml
server:
  usage_reporter:
    enabled: true
    sinks:
      - type: file_log
        config:
          path: /var/log/openviking_usage/usage.log
          resource_id_env: OV_RESOURCE_ID
          rotation_interval_hours: 1
          backup_count: 168
```

部署時必須設定 `resource_id_env` 指定的環境變數。Sink 使用其值構造
`tenant_id`，保證不同 OpenViking resource 的資料相互隔離。

## 8. 對 OpenViking 的侵入

侵入點控制在 4 個地方。

1. 新增 config

增加 `usage_reporter` 配置段。

2. 新增資料模型

增加 `UsageEvent`、`UsageContext`。

3. session commit 增加 hook

在 session archive 成功後觸發：

```text
archive session success
-> usage extractor
-> usage reporter
```

4. 新增 reporter/sink 模組

新增通用擴充點和 custom sink 動態載入能力。

不侵入的地方：

- 不改 `find/search` 語義。
- 不改 `read` 語義。
- 不把具體下游寫死進 session commit。
- 不預設上傳完整 session。
- 不強制寫 MEMORY_FIELDS。
- 不強制寫 search_tags。
- 不影響 snapshot。
- Sink 呼叫具有 5 秒超時邊界，失敗不會中斷 phase2。

整體侵入屬於低到中等，核心主鏈路只增加一個旁路 hook。

## 9. 可靠性策略

Usage Reporter 採用 best-effort 投遞語義：

- Sink 成功：正常返回。
- Sink 失敗或超時：記錄日誌，不影響 session commit。自定義 Sink 是否重試由其實現決定。
- 多個 Sink 相互隔離，某個 Sink 失敗不影響其他 Sink。
- Sink 失敗時事件可能丟失，因此本機制不保證 at-least-once。
- 如果 Sink 已寫入成功，但程序在 phase2 寫入完成標記前退出，phase2 恢復執行時可能重複傳送同一事件。
- 每個事件包含穩定的 `event_id`。Sink 可將其作為 Kafka message key；消費端按
  `(tenant_id, object_id)` 複合鍵去重。
- `event_id` 只用於識別重複事件，不代表事件一定成功送達。

`event_id` 為以下欄位規範序列化後的 SHA-256：

```text
schema_version
+ event_type
+ account_id
+ user_id
+ session_id
+ evidence.message_id
+ evidence.tool_call_id
+ resource_uri
```

`occurred_at`、`task_id`、`archive_uri` 和 `attributes` 不參與計算，避免重放時間差、
任務恢復或附加屬性變化破壞冪等性。同一 session message 中同一 tool call
對同一資源產生的事件，在 phase2 重放後仍得到相同 `event_id`。

內建檔案日誌 Sink 在 `write()` 返回前完成本地追加，但不負責 TLS 採集、Kafka
投遞或下游確認。檔案寫入、TLS 採集和下游消費任一階段都可能在故障時產生丟失
或重複，消費端需按 `(tenant_id, object_id)` 複合鍵去重，整體保持 best-effort 語義。
