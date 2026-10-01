# 可觀測性與排障

這份指南把 OpenViking 當前和“觀測”有關的入口放在一起介紹，包括：

- 服務健康檢查與元件狀態
- 請求級 `telemetry`
- 終端側 `ov tui`
- Web 側 `Web Studio`（同 OV server，路徑 `/studio`）
- `/metrics` 時序指標

如果你只想快速判斷“該看哪裡”，先看下面這張表。

## 先選哪個入口

| 入口 | 適合看什麼 | 典型場景 |
| --- | --- | --- |
| `/health`、`observer/*` | 服務是否健康、佇列是否堆積、VikingDB/VLM 狀態 | 部署驗收、值班巡檢 |
| `ov tui` | `viking://` 檔案樹、目錄摘要、檔案正文、向量記錄、受支援圖片檔案的預覽 | 開發除錯、核對資源是否真正落庫 |
| `Web Studio`（`/studio`） | 同 OV server 的 Web UI：Home 看 token / 檢索 / context commits 趨勢，Resources 瀏覽 URI，Retrieval 直接發 find，Request Logs 看審計日誌 | 不想手敲命令時做互動式排查 |
| `telemetry` | 單次請求耗時、token、向量檢索、資源處理階段 | 排查一次具體呼叫為什麼慢、為什麼結果異常 |
| `/metrics` | 請求量趨勢、錯誤率、時延分佈、佇列與探針狀態 | Prometheus 抓取、Grafana 看板、告警規則 |

## 服務健康與元件狀態

### 健康檢查

`/health` 提供簡單的存活檢查，不需要認證。

```bash
curl http://localhost:1933/health
```

```json
{"status": "ok"}
```

### 整體系統狀態

**Python HTTP SDK**

```python
status = client.get_status()
print(f"Healthy: {status['is_healthy']}")
print(f"Errors: {status['errors']}")
```

**HTTP API**

```bash
curl http://localhost:1933/api/v1/observer/system \
  -H "X-API-Key: your-key"
```

```json
{
  "status": "ok",
  "result": {
    "is_healthy": true,
    "errors": [],
    "components": {
      "queue": {"name": "queue", "is_healthy": true, "has_errors": false, "status": "..."},
      "vikingdb": {"name": "vikingdb", "is_healthy": true, "has_errors": false, "status": "..."},
      "models": {"name": "models", "is_healthy": true, "has_errors": false, "status": "..."},
      "lock": {"name": "lock", "is_healthy": true, "has_errors": false, "status": "..."},
      "retrieval": {"name": "retrieval", "is_healthy": true, "has_errors": false, "status": "..."},
      "filesystem": {"name": "filesystem", "is_healthy": true, "has_errors": false, "status": "..."}
    }
  }
}
```

### 元件狀態

| 端點 | 元件 | 描述 |
| --- | --- | --- |
| `GET /api/v1/observer/queue` | Queue | 處理佇列狀態 |
| `GET /api/v1/observer/vikingdb` | VikingDB | 向量資料庫狀態 |
| `GET /api/v1/observer/models` | Models | VLM、Embedding 和 Rerank 模型狀態 |
| `GET /api/v1/observer/lock` | Lock | 鎖和事務狀態 |
| `GET /api/v1/observer/retrieval` | Retrieval | 檢索質量指標 |
| `GET /api/v1/observer/filesystem` | Filesystem | 檔案系統操作指標 |

例如：

```bash
curl http://localhost:1933/api/v1/observer/queue \
  -H "X-API-Key: your-key"
```

### 快速健康檢查

**Python HTTP SDK**

```python
if client.is_healthy():
    print("System OK")
```

**HTTP API**

```bash
curl http://localhost:1933/api/v1/debug/health \
  -H "X-API-Key: your-key"
```

```json
{"status": "ok", "result": {"healthy": true}}
```

### 響應時間

每個 API 響應都包含一個 `X-Process-Time` 請求頭，表示服務端處理時間（單位為秒）：

```bash
curl -v http://localhost:1933/api/v1/fs/ls?uri=viking:// \
  -H "X-API-Key: your-key" 2>&1 | grep X-Process-Time
# < X-Process-Time: 0.0023
```

這部分解決的是“服務現在是不是活著、是不是堵了、哪個元件有問題”。如果你要看某一次請求內部發生了什麼，請繼續看 telemetry。

## 用 `ov tui` 看資料面

`ov` CLI 裡有一個獨立的 TUI 檔案瀏覽器命令：

```bash
ov tui /
```

也可以從某個 scope 直接進入：

```bash
ov tui viking://resources
```

使用前提：

- OpenViking Server 已啟動
- 已配置好 `ovcli.conf`
- 當前 `X-API-Key` 有權讀取對應租戶資料

這個 TUI 適合做兩類觀測：

- 看 `viking://resources` 和 `viking://user` 下實際落了哪些資料
  （session 位於 `viking://user/{user_id}/sessions`）
- 看某個 URI 對應的向量記錄是否已經寫入，以及數量是否符合預期

常用按鍵：

- `q`：退出
- `Tab`：在左側樹和右側內容面板之間切換焦點
- `j` / `k`：上下移動
- `.`：展開或摺疊目錄
- `g` / `G`：跳到頂部或底部
- `v`：切換到向量記錄檢視
- `n`：在向量記錄視圖裡載入下一頁
- `c`：在向量記錄視圖裡統計當前 URI 的向量總數

一個常見排查流程是：

1. 用 `ov tui viking://resources` 找到目標文件或目錄。
2. 確認右側能看到 `abstract` / `overview` / 正文內容（受支援的圖片檔案 —— `png` / `jpg` / `jpeg` / `gif` / `bmp` / `webp` / `tiff` / `tif` —— 會直接渲染預覽）。
3. 按 `v` 進入向量記錄檢視，確認該 URI 下是否已經有向量資料。
4. 按 `c` 檢視總量，必要時按 `n` 翻頁繼續核對。

TUI 更偏“資料面排查”。它適合回答“資源到底有沒有進去”“向量到底有沒有寫進去”，但不直接展示單次請求的 token 或階段耗時。

## 用 Web Studio 做 Web 觀測

OV server 自身在 `/studio` 提供 Web Studio 前端 —— 不需要單獨程序，跟著 `openviking-server` 一起起來就行。

```text
http://127.0.0.1:1933/studio
```

第一次使用時，在右上角 Connection 對話方塊裡填入 `X-API-Key`，base URL 預設就是當前同源（也就是 `/studio` 來自哪個域名，API 就走那個域名）。

當前比較適合觀測的頁面有：

- `Home`（`/studio`）：今日 token 消耗、檢索次數、context commits 趨勢、agent 訪問彙總 —— 直接讀 `/api/v1/console/*` BFF
- `Request Logs`（`/studio/request-logs`）：審計日誌、按 account / user / agent / route 過濾，對應 `/api/v1/console/audit`
- `Resources`（`/studio/resources`）：瀏覽 URI、檢視目錄和檔案、上傳資源
- `Retrieval`（`/studio/retrieval`）：直接發 find / search / grep 請求並檢視結果
- `Sessions`（`/studio/sessions`）：瀏覽 session 歷史、檢視 message / memory 提交流程

寫操作（`Add Resource`、`Add Memory`、租戶/使用者管理）通過當前已登入的 API key 鑑權，沒有額外的 `--write-enabled` 開關需要開啟。

從觀測角度看，Studio 的一個優點是直接呼叫 `/api/v1/console/*` BFF 的統計介面（dashboard summary、token series、context commits、audit logs），跟舊 console 複用同一套資料，只是 UI 換了。對於 `find`、`add-resource` 和 `session commit` 這類操作，結果面板可以展開看 `telemetry.summary`。

Studio 更適合“邊點邊看”的互動式排查；如果你要把觀測資料接到自己的日誌系統或自動化鏈路，建議直接呼叫 HTTP API 或 SDK，並顯式請求 telemetry。

## 請求級 Telemetry

OpenViking 的請求級追蹤能力對外名稱是 `operation telemetry`。它會在響應裡附帶一份結構化摘要，用來說明這次呼叫裡發生了什麼，例如：

- 總耗時
- LLM / embedding token 消耗
- 向量檢索次數、掃描量、返回量
- 資源匯入階段耗時
- `session.commit` 的 memory 提取統計

最常見的請求方式是在 body 裡顯式傳：

```json
{"telemetry": true}
```

例如：

```bash
curl -X POST http://localhost:1933/api/v1/search/find \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "query": "memory dedup",
    "limit": 5,
    "telemetry": true
  }'
```

完整欄位、支援範圍和更多示例見：

- [操作級 Telemetry 參考](07-operation-telemetry.md)

## 產生本地 Trace 並提交排查

如果一次問題無法只靠響應裡的 `telemetry.summary` 判斷，可以讓 OpenViking 把 OpenTelemetry trace 寫到本地 JSONL 檔案。使用者把 JSONL 檔案和有問題的 `trace_id` 提交給管理員/支援人員，由管理員上傳到排查環境並繼續分析。這個方式適合離線客戶環境、無法直連 OTLP 後端的環境，或者需要把復現過程打包給支援人員分析的場景。

### 1. 開啟本地 trace 檔案

在執行 OpenViking Server 的機器上，編輯 `~/.openviking/ov.conf`（或你啟動時通過 `--config` 指定的配置檔案），加入或調整：

```json
{
  "server": {
    "observability": {
      "traces": {
        "enabled": true,
        "protocol": "local",
        "service_name": "openviking-server",
        "local_path": "~/.openviking/logs/traces.jsonl",
        "local_rotation_mb": 40,
        "local_backup_count": 2
      }
    }
  }
}
```

改完後需要**重啟 OpenViking Server**。預設檔案路徑是：

```text
~/.openviking/logs/traces.jsonl
```

當檔案達到 `local_rotation_mb` 後會輪轉，例如：

```text
~/.openviking/logs/traces.jsonl.2
~/.openviking/logs/traces.jsonl.1
~/.openviking/logs/traces.jsonl
```

### 2. 復現問題並確認 trace 已產生

啟動服務後，執行能復現問題的操作，例如一次 `find`、資源匯入、`session commit` 或 agent 呼叫。操作完成後等待幾秒，或優雅停止服務以便 batch exporter 刷盤，然後檢查檔案：

```bash
ls -lh ~/.openviking/logs/traces.jsonl*
tail -n 3 ~/.openviking/logs/traces.jsonl
```

如果沒有檔案或檔案為空，優先檢查：

- Server 是否已重啟並載入了新的 `ov.conf`
- `server.observability.traces.enabled` 是否為 `true`
- `server.observability.traces.protocol` 是否為 `"local"`
- 當前程序是否有許可權寫入 `~/.openviking/logs`

### 3. 提交 trace 檔案給管理員

這一步通常由**使用者提交材料，管理員/支援人員上傳並排查**：

1. 使用者不要直接上傳到排查環境，只需要把本地 JSONL 檔案交給管理員/支援人員。
2. 如果已經知道有問題的 `trace_id`，請和 JSONL 一起提交。
3. 如果不確定具體 `trace_id`，請至少提供復現時間段、操作步驟和相關請求/錯誤日誌，方便管理員從檔案中定位。

建議提交當前檔案和輪轉檔案：

```text
~/.openviking/logs/traces.jsonl
~/.openviking/logs/traces.jsonl.1
~/.openviking/logs/traces.jsonl.2
```

也可以先打包後再提交：

```bash
cd ~/.openviking/logs
tar czf /tmp/openviking-traces.tgz traces.jsonl*
```

提交給管理員/支援人員的資訊建議包括：

- `traces.jsonl*` 檔案或打包後的 `openviking-traces.tgz`
- 有問題的 `trace_id`（如果已知）
- 復現問題的時間段和操作步驟
- OpenViking 版本/commit、啟動命令、關鍵配置（去掉金鑰和 token）
- 相關錯誤日誌或請求 id（如果有）

#### 管理員上傳參考

管理員在有 OpenViking 原始碼、且能訪問遠端 OTLP 排查環境的機器上，從倉庫根目錄執行：

```bash
python tests/upload_offline_trace.py \
  --file /path/to/traces.jsonl
```

上傳指令碼會讀取當前環境的 `ov.conf` 作為**上傳目標配置**，因此該配置裡的 trace exporter 必須是遠端 OTLP，例如：

```json
{
  "server": {
    "observability": {
      "traces": {
        "enabled": true,
        "protocol": "grpc",
        "tls": {
          "insecure": true
        },
        "endpoint": "otel-collector:4317",
        "service_name": "openviking-server",
        "headers": {}
      }
    }
  }
}
```

如果當前 `ov.conf` 不是上傳目標配置，請準備一個單獨的上傳配置，並通過 `--config` 指定：

```bash
python tests/upload_offline_trace.py \
  --file /path/to/traces.jsonl \
  --config /path/to/upload-ov.conf
```

預設會按從舊到新的順序一併上傳輪轉檔案（例如 `traces.jsonl.2`、`traces.jsonl.1`、`traces.jsonl`）。如果只想上傳當前檔案：

```bash
python tests/upload_offline_trace.py \
  --file /path/to/traces.jsonl \
  --no-include-rotated
```

上傳成功後，指令碼會列印本次上傳的 trace id 列表；管理員可結合使用者提交的 `trace_id` 或復現時間段繼續排查：

```text
Uploaded:
  batches: 12
  spans: 345
  trace_ids: 3
    0123456789abcdef0123456789abcdef
    ...
```

## 用 `/metrics` 做時序觀測

`/metrics` 是 OpenViking 面向 Prometheus 抓取模型提供的時序指標端點，適合回答這類問題：

- 最近一段時間 HTTP 請求量是不是突然升高了
- 某個介面或操作的錯誤率是不是在持續上升
- 請求耗時分佈是否變差
- 佇列是否開始堆積
- 關鍵依賴、探針或模型提供方是否進入不健康狀態

和前面的 `observer/*` 相比，`/metrics` 更適合看**趨勢、聚合和告警**；而 `observer/*` 更適合人工檢視某一時刻的瞬時狀態。

和前面的 `telemetry` 相比，`/metrics` 關注的是**聚合後的時間序列**；`telemetry` 關注的是**某一次請求內部到底發生了什麼**。

### 快速開啟 metrics

`/metrics` 預設是關閉的：當指標體系未啟用時，訪問會返回 `404`，並提示 `Prometheus metrics are disabled.`。

開啟方式不需要完整配置，只需要在 `ov.conf` 的 `server` 段開啟總開關即可。

**最小配置（推薦）**

在 `~/.openviking/ov.conf`（或你啟動時通過 `--config` 指定的路徑）里加入：

```json
{
  "server": {
    "observability": {
      "metrics": {
        "enabled": true
      }
    }
  }
}
```
改完配置後需要**重啟 OpenViking Server** 才會生效。

### observability 配置層級

OpenViking 將訊號級別的可觀測性配置統一放在 `server.observability` 下：

- `server.observability.metrics`：metrics 子系統與 exporter 配置
- `server.observability.traces`：trace 匯出配置
- `server.observability.logs`：log 匯出配置
- `server.observability.dump_body`：把 HTTP 請求/響應 body（按 content-type 過濾、按位元組截斷）作為屬性掛到當前 trace span 上，便於在 trace UI 中除錯。預設關閉，因為 body 可能含金鑰/高基數內容
- `server.observability.usage_audit`：按請求記錄用量/成本審計日誌，使用 SQLite 儲存。`sqlite_path` 可覆蓋資料庫位置（多例項部署時設為每例項獨立的本地路徑）；`timezone` 控制時間戳的時區本地化。預設開啟

示例：

```json
{
  "server": {
    "observability": {
      "metrics": {
        "enabled": true,
        "exporters": {
          "prometheus": {
            "enabled": true
          },
          "otel": {
            "enabled": true,
            "protocol": "grpc",
            "tls": {
              "insecure": true
            },
            "endpoint": "otel-collector:4317",
            "service_name": "openviking-server",
            "export_interval_ms": 10000,
            "headers": {}
          }
        }
      },
      "traces": {
        "enabled": true,
        "protocol": "grpc",
        "tls": {
          "insecure": true
        },
        "endpoint": "otel-collector:4317",
        "service_name": "openviking-server",
        "headers": {}
      },
      "logs": {
        "enabled": true,
        "protocol": "grpc",
        "tls": {
          "insecure": true
        },
        "endpoint": "otel-collector:4317",
        "service_name": "openviking-server",
        "headers": {}
      },
      "dump_body": {
        "enabled": false,
        "max_bytes": 4096
      },
      "usage_audit": {
        "enabled": true,
        "sqlite_path": null,
        "timezone": "local"
      }
    }
  }
}
```

說明：

- `headers` 用於給 OTLP exporter 透傳自定義請求頭或 gRPC metadata。
- 常見場景包括直連需要額外鑑權頭的 OTLP 後端；請只配置 header key/value，不要把敏感值寫入日誌或截圖中。
- 對 `traces`、`logs` 和 `metrics.exporters.otel` 三條鏈路，`headers` 的配置方式保持一致。
- 當 `protocol="grpc"` 時，`headers` 會作為 gRPC metadata 傳送，key 需要使用小寫形式，例如 `x-byteapm-appkey`；該限制不適用於 `protocol="http"`。

完整欄位、支援範圍和更多示例見：

- [指標](../concepts/12-metrics.md) 

### 直接訪問 `/metrics`

當前實現中，`/metrics` 未接入 `get_request_context` 等鑑權依賴，因此從程式碼行為上看，它當前等價於公開抓取端點：

```bash
curl http://localhost:1933/metrics
```

如果你的部署環境通過閘道器、反向代理或服務發現層對 `/metrics` 做了保護，則應按部署方式附加鑑權。

### Prometheus 抓取示例

最常見的使用方式是讓 Prometheus 定時抓取：

```yaml
scrape_configs:
  - job_name: openviking
    metrics_path: /metrics
    static_configs:
      - targets: ["localhost:1933"]
```

### 在 Grafana 中匯入和檢視 Dashboard

如果你已經讓 Prometheus 成功抓取 `/metrics`，下一步最常見的做法就是在 Grafana 中匯入 OpenViking 的 demo dashboard。

**第 1 步：先確認 Prometheus 已經抓到 `/metrics`**

在匯入 Grafana dashboard 之前，先確認 Prometheus 資料來源裡已經能查到 OpenViking 指標。最簡單的判斷方式是：

- 在 Prometheus UI 裡執行 `openviking_http_requests_total`
- 或執行 `openviking_service_readiness`
- 如果已經能返回時間序列，說明 Grafana 後續就能正常出圖

如果這一步沒有資料，先回到上面的 Prometheus 抓取配置，確認 `targets`、`metrics_path` 和網路連通性。

**第 2 步：在 Grafana 匯入官方 demo dashboard**

OpenViking 倉庫裡已經提供了可直接匯入的 dashboard JSON：

- [openviking_demo_dashboard.json](https://github.com/volcengine/OpenViking/blob/main/examples/grafana/openviking_demo_dashboard.json)
- [openviking_token_demo_dashboard.json](https://github.com/volcengine/OpenViking/blob/main/examples/grafana/openviking_token_demo_dashboard.json) （注意，該 dashboard 依賴 `tim012432-calendarheatmap-panel` grafana 外掛，需要先安裝才能正常工作）

匯入步驟可以按下面做：

1. 登入你的 Grafana。
2. 在左側選單進入 `Dashboards`。
3. 點選右上角的 `New` 或 `Import`。
4. 選擇上傳 JSON 檔案，或把上面連結對應檔案的內容貼上進去。
5. 在匯入頁面選擇 Prometheus 作為資料來源。
6. 點選 `Import` 完成匯入。

如果匯入後面板為空，通常優先檢查兩件事：

- Grafana 繫結的資料來源是不是正確的 Prometheus
- Prometheus 裡是否真的已經抓到了 `openviking_*` 指標

**第 3 步：開啟 dashboard 後重點看什麼**

接入之後，通常就可以在 Grafana 裡重點觀察這些指標族對應的面板：

- `openviking_http_*`：HTTP 請求量、耗時、inflight
- `openviking_operation_*`：結構化操作的成功率和耗時
- `openviking_queue_*`：佇列處理量、積壓和執行中數量
- `openviking_*_readiness`：依賴與探針健康狀態

**第 4 步：最終效果長什麼樣**

匯入成功後，你最終會看到一個以 OpenViking 請求、佇列、探針、模型呼叫和系統狀態為主的總覽 dashboard。效果示意可以參考：

- [grafana-demo-dashboard.png](../../images/grafana-demo-dashboard.png)

這張圖可以幫助你快速確認“匯入後的面板佈局是不是正常”。如果你的 dashboard 基本結構和它一致，但區域性面板沒有資料，通常說明是對應指標當前沒有產生樣本，或者篩選條件與實際流量不匹配。

### 如何理解常見標籤

排查看板時，最常見的幾個標籤是：

- `account_id`：租戶維度標籤。只在受控白名單指標上開啟，未識別請求會被歸到 `__unknown__`，超出活躍租戶預算時會落到 `__overflow__`
- `route`：HTTP 路由模板，例如 `/api/v1/search/find`
- `status`：請求或階段狀態，例如 `200`、`ok`、`error`
- `valid`：當前樣本是否是本次成功重新整理得到的有效值；`valid="0"` 通常表示失敗回退值或 stale fallback

### 什麼時候看 `/metrics`，什麼時候看別的入口

- 看服務是否整體健康、哪個元件當前不通：先看 `/health` 和 `observer/*`
- 看資源是否真的落庫、向量是否真的寫進去：看 `ov tui`
- 看某一次具體請求為什麼慢、token 花在哪、資源處理卡在哪個階段：看 `telemetry`
- 看一段時間內請求量、錯誤率、時延是否持續惡化：看 `/metrics`

## 相關文件

- [使用 Prometheus 和 Grafana 檢視 OpenViking 指標](11-grafana-prometheus.md) - 從 `/metrics` 到 Prometheus、Grafana dashboard 的完整操作流程
- [使用真實問答驗證 Vikingbot 指標](12-vikingbot-metrics-validation.md) - 用 `/bot/v1/chat`、`/bot/v1/feedback` 和真實 follow-up 場景校驗反饋與 outcome 指標
- [部署](03-deployment.md) - 伺服器設定
- [認證](04-authentication.md) - API Key 設定
- [操作級 Telemetry 參考](07-operation-telemetry.md) - 請求級結構化追蹤
- [系統 API](../api/07-system.md) - 系統與 observer 介面參考
- [指標](../concepts/12-metrics.md) - 時序指標與配置
