# 使用 Prometheus 和 Grafana 檢視 OpenViking 指標

這份文件給出一條從零開始的完整鏈路：

1. 啟動 OpenViking 並確認 `/metrics` 可訪問
2. 啟動 Prometheus 抓取 OpenViking 指標
3. 啟動 Grafana 並連線 Prometheus 資料來源
4. 匯入 OpenViking 自帶 dashboard 或在 Explore 中直接查詢

如果你已經能訪問 `http://<host>:<port>/metrics`，可以直接從本文的“啟動 Prometheus”開始。

## 架構關係

OpenViking 不直接提供 Grafana 頁面。標準鏈路是：

```text
OpenViking -> /metrics -> Prometheus -> Grafana
```

其中：

- OpenViking 負責暴露 Prometheus exposition 文本
- Prometheus 負責定時抓取 `/metrics`
- Grafana 負責讀取 Prometheus 並展示 dashboard

## 前置條件

開始前請確認：

- OpenViking Server 已安裝並可正常啟動
- Docker 已安裝，可用於快速啟動 Prometheus 和 Grafana
- 你知道 OpenViking 當前監聽的 HTTP 地址，例如 `http://localhost:30300`

## 第 1 步：確認 OpenViking 已暴露 `/metrics`

OpenViking 需要先啟用 metrics。最小配置參考：

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

配置寫入 `~/.openviking/ov.conf` 後，重啟 OpenViking Server。

如果你還沒有啟動服務，可參考：

```bash
openviking-server doctor
openviking-server --port 30300
```

然後驗證：

```bash
curl http://localhost:30300/metrics
```

如果返回包含 `openviking_` 字首的文本，說明 metrics 已經啟用。例如：

```text
# HELP openviking_http_requests_total Total number of HTTP requests
# TYPE openviking_http_requests_total counter
openviking_http_requests_total{method="GET",route="/api/v1/system/status",status="200"} 12
```

如果返回 `Prometheus metrics are disabled.`，說明配置未生效或服務未重啟。

## 第 2 步：使用倉庫自帶 compose 檔案部署

倉庫裡已經提供了一套可直接啟動的觀測示例，檔案位於：

- `examples/grafana/docker-compose.yml`
- `examples/grafana/prometheus.yml`
- `examples/grafana/grafana/provisioning/datasources/prometheus.yml`
- `examples/grafana/grafana/provisioning/dashboards/openviking.yml`

另外，針對 Linux 上 OpenViking 繼續監聽 `127.0.0.1` / `localhost` 的場景，倉庫還提供了一套 localhost 專用示例：

- `examples/grafana/docker-compose.localhost.yml`
- `examples/grafana/prometheus.localhost.yml`
- `examples/grafana/grafana/provisioning-localhost/datasources/prometheus.yml`
- `examples/grafana/grafana/provisioning-localhost/dashboards/openviking.yml`

兩套方案的區別是：

- `docker-compose.yml`：通用方案，Prometheus 從容器網路訪問宿主機，適合 OpenViking 監聽 `0.0.0.0`
- `docker-compose.localhost.yml`：Linux localhost 方案，Prometheus 和 Grafana 直接使用宿主機網路，適合 OpenViking 繼續監聽 `127.0.0.1`

如果你當前不想把 OpenViking 暴露到 `0.0.0.0`，推薦優先使用 `docker-compose.localhost.yml`。

這套配置預設會做幾件事：

- 啟動 Prometheus，並把宿主機埠對映到 `30909`
- 啟動 Grafana，並把宿主機埠對映到 `13000`
- 自動把 Grafana 資料來源配置為 `http://127.0.0.1:30909`
- 自動載入倉庫裡的 OpenViking demo dashboard
- 自動載入 `OpenViking - Feedback Baseline`，方便直接檢視 `openviking_feedback_*` 與 `openviking_feedback_channel_*` 的基線指標

### 方案 A：通用方案

直接執行：

```bash
docker compose -f examples/grafana/docker-compose.yml up -d
```

啟動完成後可訪問：

```text
Prometheus: http://localhost:30909
Grafana:    http://localhost:13000
```

Grafana 預設帳號密碼在這個示例裡固定為：

- 使用者名稱：`admin`
- 密碼：`admin`

### 方案 B：Linux localhost 方案

如果你的 OpenViking 繼續監聽在 `127.0.0.1:30300`，並且你不想為了 Prometheus 抓取而把 OpenViking 改成 `0.0.0.0`，請使用下面這套 compose：

```bash
docker compose -f examples/grafana/docker-compose.localhost.yml up -d
```

這套方案的特點是：

- Prometheus 使用宿主機網路，直接抓取 `127.0.0.1:30300/metrics`
- Grafana 也使用宿主機網路，並直接連線 `http://127.0.0.1:30909`
- 不需要把 OpenViking 改成 `0.0.0.0`
- 不會觸發“非 localhost 監聽必須配置 `root_api_key`”這條安全限制

訪問地址仍然是：

```text
Prometheus: http://localhost:30909
Grafana:    http://localhost:13000
```

如果宿主機上的 `30909` 或 `13000` 已經被佔用：

- Prometheus 埠改 `examples/grafana/docker-compose.localhost.yml` 裡的 `--web.listen-address=0.0.0.0:30909`
- Grafana 埠改 `examples/grafana/docker-compose.localhost.yml` 裡的 `GF_SERVER_HTTP_PORT=13000`
- 同時把 `examples/grafana/grafana/provisioning-localhost/datasources/prometheus.yml` 中的 `http://127.0.0.1:30909` 改成新埠

如果你只想快速部署，做到這裡就可以先跳到“如何判斷鏈路已經完全打通”。

## 第 3 步：理解 Prometheus 抓取配置

compose 示例裡使用的 `examples/grafana/prometheus.yml` 內容如下：

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: openviking
    metrics_path: /metrics
    static_configs:
      - targets: ["host.docker.internal:30300"]
```

說明：

- 如果 Prometheus 執行在 Docker 容器裡，而 OpenViking 執行在宿主機，`targets` 推薦寫成 `host.docker.internal:30300`
- 如果 Prometheus 也執行在宿主機，改成 `localhost:30300`
- 如果 `host.docker.internal` 在你的 Linux Docker 環境中不可用，就改成宿主機實際 IP，例如 `192.168.1.10:30300`

如果你的 OpenViking 不是監聽在 `30300`，就把這個檔案裡的目標地址改成你的實際埠，然後重新執行：

```bash
docker compose -f examples/grafana/docker-compose.yml up -d
```

如果你使用的是 Linux localhost 方案，對應修改的是：

- `examples/grafana/prometheus.localhost.yml`

例如 OpenViking 實際監聽 `127.0.0.1:1933`，就改成：

```yaml
targets: ["127.0.0.1:1933"]
```

然後重新執行：

```bash
docker compose -f examples/grafana/docker-compose.localhost.yml up -d
```

## 第 4 步：可選，手動部署時建立 Docker 網路

如果你使用的是上面的 compose 檔案，這一步不需要手動執行，因為 Compose 會自動建立預設網路。

只有在你堅持使用 `docker run` 分開啟動 Prometheus 和 Grafana 時，才需要先建立一個獨立網路：

```bash
docker network create openviking-observability
```

如果提示網路已存在，可以忽略。

## 第 5 步：可選，手動啟動 Prometheus

如果你已經用了 `docker compose -f examples/grafana/docker-compose.yml up -d`，這一節可以跳過。

很多機器上 `9090` 已經被別的服務佔用。為了減少衝突，這裡建議把宿主機埠對映到 `30909`：

```bash
docker run -d \
  --name prometheus \
  --network openviking-observability \
  -p 30909:9090 \
  -v "$PWD/prometheus.yml:/etc/prometheus/prometheus.yml:ro" \
  prom/prometheus
```

啟動後，在瀏覽器開啟：

```text
http://localhost:30909
```

進入 Prometheus UI 後，在查詢框中輸入：

```promql
openviking_http_requests_total
```

或者：

```promql
openviking_service_readiness
```

如果能查到時間序列，說明 Prometheus 已經成功抓到 OpenViking 指標。

### 如果 Prometheus 容器啟動失敗

常見原因：宿主機埠被佔用，例如：

```text
Bind for 0.0.0.0:9090 failed: port is already allocated
```

處理方式：

- 改宿主機埠，例如繼續使用 `30909:9090`
- 不要改容器內埠 `9090`
- 訪問時用新的宿主機埠，例如 `http://localhost:30909`

## 第 6 步：可選，手動啟動 Grafana

如果你已經用了 `docker compose -f examples/grafana/docker-compose.yml up -d`，這一節可以跳過。

同樣地，很多機器上的 `3000` 也常被佔用。建議把 Grafana 對映到宿主機的 `13000`：

```bash
docker run -d \
  --name grafana \
  --network openviking-observability \
  -p 13000:3000 \
  grafana/grafana
```

啟動後開啟：

```text
http://localhost:13000
```

Grafana 預設初始帳號通常是：

- 使用者名稱：`admin`
- 密碼：`admin`

如果你的環境已修改預設憑據，以實際值為準。

## 第 7 步：可選，手動在 Grafana 中新增 Prometheus 資料來源

如果你使用的是倉庫自帶 compose 檔案，這一步通常也可以跳過，因為資料來源會自動 provision。

在 Grafana 頁面中操作：

1. 開啟左側 `Connections` 或 `Data sources`
2. 點選 `Add data source`
3. 選擇 `Prometheus`
4. 在 `URL` 中填寫：`http://prometheus:9090`
5. 點選 `Save & test`

這裡填寫 `http://prometheus:9090` 的原因是：

- Grafana 和 Prometheus 執行在同一個 Docker 網路 `openviking-observability` 中
- 兩個容器可以直接通過容器名通訊

如果 `Save & test` 失敗，請先執行：

```bash
docker ps
```

確認 `prometheus` 和 `grafana` 兩個容器都在執行。

## 第 8 步：先在 Grafana Explore 中直接查詢

新增完資料來源後，先不要急著匯入 dashboard，建議先在 `Explore` 中驗證基礎查詢。

推薦先試這些查詢：

請求量：

```promql
rate(openviking_http_requests_total[5m])
```

按路由檢視請求量與狀態碼：

```promql
sum by (route, status) (rate(openviking_http_requests_total[5m]))
```

P95 延遲：

```promql
histogram_quantile(0.95, sum by (le, route) (rate(openviking_http_request_duration_seconds_bucket[5m])))
```

佇列積壓：

```promql
openviking_queue_pending
```

模型呼叫量：

```promql
rate(openviking_model_calls_total[5m])
```

Token 用量：

```promql
rate(openviking_operation_tokens_total[5m])
```

如果你還不確定有哪些指標名，可以先查：

```promql
{__name__=~"openviking_.*"}
```

## 第 9 步：匯入 OpenViking 自帶 Dashboard

如果你使用的是倉庫自帶 compose 檔案，這兩個 dashboard 會在 Grafana 啟動後自動載入到 `OpenViking` 資料夾下。

如果你想手動匯入，繼續按下面步驟操作即可。

倉庫中已經提供了可直接匯入的 Grafana dashboard：

- `examples/grafana/openviking_demo_dashboard.json`
- `examples/grafana/openviking_token_demo_dashboard.json`

匯入步驟：

1. 進入 Grafana 左側 `Dashboards`
2. 點選右上角 `New` 或 `Import`
3. 上傳 `examples/grafana/openviking_demo_dashboard.json`
4. 在匯入頁面選擇剛剛建立的 Prometheus 資料來源
5. 點選 `Import`

說明：

- `openviking_demo_dashboard.json` 適合作為基礎總覽 dashboard
- `openviking_token_demo_dashboard.json` 依賴 `tim012432-calendarheatmap-panel` 外掛，未安裝前部分面板可能無法正常顯示

## 第 10 步：如何判斷鏈路已經完全打通

你可以按下面的順序驗證：

1. `curl http://localhost:30300/metrics` 能返回指標文本
2. 開啟 `http://localhost:30909`，在 Prometheus 中能查到 `openviking_http_requests_total`
3. 開啟 `http://localhost:13000`，能看到 `Prometheus` 資料來源已經存在，或手動 `Save & test` 成功
4. Grafana Explore 中執行 `rate(openviking_http_requests_total[5m])` 能出圖
5. 匯入 demo dashboard 後面板開始顯示資料

只要這五步都通過，說明整條鏈路已經打通。

## 常見問題

### 1. `/metrics` 能訪問，但 Prometheus 查不到資料

優先檢查：

- `prometheus.yml` 的 `targets` 是否寫對
- Prometheus 是否真的重新載入了新的配置
- Docker 容器內是否能訪問宿主機上的 `30300`

如果你使用的是倉庫自帶 compose 檔案，優先檢查：

```bash
docker compose -f examples/grafana/docker-compose.yml logs prometheus
```

如果懷疑容器訪問宿主機有問題，可以把 `host.docker.internal` 改成宿主機實際 IP。

### 2. Prometheus 宿主機埠被佔用

報錯示例：

```text
Bind for 0.0.0.0:9090 failed: port is already allocated
```

處理方式：改成別的宿主機埠，例如：

```bash
  -p 30909:9090
```

### 3. Grafana 宿主機埠被佔用

處理方式：改成別的宿主機埠，例如：

```bash
-p 13000:3000
```

### 4. Grafana 裡沒有任何 OpenViking 指標

優先檢查：

- Grafana 資料來源是否真的連到 Prometheus
- Prometheus 中是否已經有 `openviking_*` 指標
- 時間範圍是否過短，導致近期沒有樣本

如果你使用的是 compose 自動匯入方案，還可以先確認 dashboard 是否已經被載入：

- 左側進入 `Dashboards`
- 檢視 `OpenViking` 資料夾是否存在

### 5. Dashboard 匯入成功但面板為空

這通常不是 dashboard 檔案損壞，而是：

- Prometheus 裡還沒有對應指標樣本
- 過濾條件和當前環境不匹配
- 選擇了錯誤的資料來源

建議先回到 Explore 手動執行 PromQL，確認基礎查詢確實有資料。

## 相關文件

- [可觀測性與排障](05-observability.md)
- [使用真實問答驗證 Vikingbot 指標](12-vikingbot-metrics-validation.md)
- [指標與 Metrics](../concepts/12-metrics.md)
- [Metrics API](../api/09-metrics.md)
- [服務端部署](03-deployment.md)
- [快速開始](../getting-started/02-quickstart.md)
