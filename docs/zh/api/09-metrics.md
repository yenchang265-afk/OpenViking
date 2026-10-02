# 指標與 Metrics

Business Data Platform 提供 `/metrics` 端點，用於向 Prometheus、Grafana Agent 等監控系統匯出執行時指標。

與 `/api/v1/observer/*` 不同，`/metrics` 的定位是：

- 面向機器抓取，而不是面向人工閱讀
- 返回 Prometheus exposition 文本，而不是統一 JSON 包裝
- 偏系統執行態與服務執行質量，不承擔業務分析介面職責

## API 參考

### metrics()

匯出當前程序內的 Prometheus 指標文本。

該端點通常被 Prometheus 定時抓取，也可以用於本地除錯或手工排查。

**認證**

- 當前實現中，`/metrics` 未接入 `get_request_context` 等鑑權依賴，因此可直接訪問。
- 也就是說，從程式碼實現角度看，`/metrics` 當前等價於公開抓取端點。
- 如果後續通過閘道器、反向代理或服務端策略收緊訪問控制，應以實際部署配置為準。

**HTTP API**

```
GET /metrics
```

```bash
curl -X GET http://localhost:1933/metrics
```

如果你的部署環境在閘道器或代理層要求鑑權，可以按閘道器要求附加請求頭，例如：

```bash
curl -X GET http://localhost:1933/metrics \
  -H "Authorization: Bearer your-key"
```

**響應格式**

成功時返回 `text/plain; version=0.0.4; charset=utf-8`，內容為 Prometheus exposition 格式文本，例如：

```text
# HELP openviking_http_requests_total Total number of HTTP requests
# TYPE openviking_http_requests_total counter
openviking_http_requests_total{method="GET",route="/api/v1/system/status",status="200"} 12

# HELP openviking_http_inflight_requests Number of inflight HTTP requests
# TYPE openviking_http_inflight_requests gauge
openviking_http_inflight_requests{route="/api/v1/system/status"} 0
```

當指標系統未啟用時，返回：

- HTTP 狀態碼：`404`
- 響應體：

```text
Prometheus metrics are disabled.
```

**示例：Prometheus 抓取配置**

```yaml
scrape_configs:
  - job_name: openviking
    metrics_path: /metrics
    static_configs:
      - targets: ["localhost:1933"]
```

如果你的部署環境對 `/metrics` 做了閘道器鑑權，可以通過反向代理、service discovery，或 Prometheus 支援的鑑權方式為該抓取任務配置請求頭。

**注意事項**

- `/metrics` 適合高頻抓取，因此其中的指標應保持低基數、低成本。
- `/metrics` 返回的是 Prometheus 文本，不是標準 Business Data Platform API 的 `{status, result, time}` JSON 結構。
- 人工檢視元件瞬時狀態更適合使用 `/api/v1/observer/*`。
- `/metrics` 現在也包含 VikingBot feedback observability 指標，這些指標來自對持久化 session 資料的 scrape-time 聚合；具體指標族與示例可參見 Metrics 概念文件中的 feedback 章節。

## 相關文件

- [指標與 Metrics](../concepts/12-metrics.md) - 指標族、標籤、feedback 指標與 PromQL 示例
- [VikingBot 問答效果反饋觀測方案設計](https://github.com/volcengine/OpenViking/blob/main/bot/docs/zh/design/vikingbot-feedback-observability-design.md) - feedback 指標與階段性落地背景
- [系統與監控](07-system.md) - 健康檢查、系統狀態與 Observer API
- [API 概覽](01-overview.md) - 所有 API 端點共享約定
