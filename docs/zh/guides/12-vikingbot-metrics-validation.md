# 使用真實問答驗證 Vikingbot 指標

完成 [Prometheus 和 Grafana 配置](11-grafana-prometheus.md) 後，用本文驗證完整鏈路：

```text
問答 → bot 會話持久化 → feedback / follow-up → /metrics → Prometheus → Grafana
```

## 前提條件

- 啟用 `server.observability.metrics.enabled=true`，通過 `openviking-server --with-bot --port 30300` 啟動服務。
- 確認 `/bot/v1/health` 返回 HTTP 200，`/metrics` 返回 Prometheus exposition 文本。
- 確認 Prometheus 能抓取 OpenViking，Grafana 使用該 Prometheus 資料來源。

上一篇的 localhost 方案使用 OpenViking `http://127.0.0.1:30300`、Prometheus `http://127.0.0.1:30909` 和 Grafana `http://127.0.0.1:13000`。如果啟用了認證，請為每個請求新增部署要求的憑據，參見 [認證](04-authentication.md)。

## 指標口徑

反饋指標是 **snapshot gauge**，包括以 `_total` 結尾的指標。`FeedbackCollector` 從 `<bot_data_path>/sessions/*.jsonl` 的 `metadata.feedback_events` 和 `metadata.response_outcomes` 聚合快照。預設重新整理 TTL 為 30 秒，多次 scrape 可能複用同一份快照。對比結果前，需要等待 collector 重新整理和下一次 Prometheus 抓取。

優先檢視當前值或短時間內的變化，不要按 counter 使用 `rate()`。查詢過濾 `valid="1"`；`valid="0"` 是採集失敗後的 fallback 快照，不適合作為驗收依據。gauge 與 counter 的區別見 [Prometheus 指標型別](https://prometheus.io/docs/concepts/metric_types/)。

每個場景使用新的 session ID。指標覆蓋全部持久化會話，其他流量也會影響結果；歷史樣本多時，單次操作帶來的比例變化可能很小。已有 response 的 outcome 被重新分類時，相應 outcome total 可以下降。

## 記錄基線

在 Prometheus 或 Grafana Explore 的表格檢視中逐條執行：

```promql
openviking_service_readiness{valid="1"}
openviking_component_health{valid="1"}
openviking_queue_pending
openviking_vikingdb_collection_vectors{valid="1"}
openviking_model_usage_available{valid="1"}
```

readiness 應為 `1`，健康元件通常為 `1`，佇列積壓應為零或較小值。向量數和模型統計可用性取決於服務配置，不要求在問答過程中變化。

同時記錄反饋快照：

```promql
{__name__=~"openviking_feedback.*",valid="1"}
```

## 1. 發起問答，確認持久化

```bash
curl -sS -X POST "http://127.0.0.1:30300/bot/v1/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "realcase-01-chat",
    "user_id": "metrics-validation-user",
    "message": "請用一句話介紹 OpenViking。"
  }'
```

預期 HTTP 200，返回 `session_id`、`response_id` 和非空 `message`。儲存 response ID，後續反饋需要使用。

重新整理後，`openviking_feedback_responses_total{valid="1"}` 通常增加 `1`。新 session 檔案也會使 `openviking_feedback_sessions_scanned_total{valid="1"}` 增加。普通問答本身不會產生顯式反饋事件。

## 2. 提交正向反饋

使用 `session_id: "realcase-02-thumb-up"` 再發起一次問答，將下面的 `<response_id>` 替換為該輪返回的 ID：

```bash
curl -sS -X POST "http://127.0.0.1:30300/bot/v1/feedback" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "realcase-02-thumb-up",
    "response_id": "<response_id>",
    "feedback_type": "thumb_up",
    "feedback_text": "helpful"
  }'
```

預期返回 `accepted: true`。對於此前沒有反饋的 response，以下 gauge 通常各增加 `1`：

```promql
openviking_feedback_events_total{valid="1"}
openviking_feedback_thumb_up_total{valid="1"}
openviking_feedback_responses_with_feedback_total{valid="1"}
openviking_feedback_positive_outcomes_total{valid="1"}
```

`coverage`、`thumbs_up_rate` 和 `one_turn_resolution_rate` 也可能變化。當前實現將 `resolved` 和 `positive_feedback` 都計入一輪解決率。優先核對 total，比例取決於全部歷史 response 和 outcome。

## 3. 提交負向反饋

用新 session `realcase-03-thumb-down` 發起問答，再按上面的方式提交反饋，使用該輪 response ID，並設定 `feedback_type: "thumb_down"`、`feedback_text: "not helpful"`。

重新整理後，以下 total 通常各增加 `1`：

```promql
openviking_feedback_events_total{valid="1"}
openviking_feedback_thumb_down_total{valid="1"}
openviking_feedback_negative_outcomes_total{valid="1"}
```

`openviking_feedback_thumbs_down_rate` 和 `openviking_feedback_negative_feedback_rate` 也可能變化。僅這次操作不應增加正向反饋或 reask total。

## 4. 十分鐘內追問

用 `realcase-04-reask` 發起問答，不提交反饋，在 assistant 回覆後的十分鐘內向同一 session 傳送第二條訊息：

```bash
curl -sS -X POST "http://127.0.0.1:30300/bot/v1/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "realcase-04-reask",
    "user_id": "metrics-validation-user",
    "message": "請解釋得更具體一些。"
  }'
```

**上一條** assistant response 會被分類為 `reasked`。該判斷依據時間，不會檢查兩次問題的語義相似度。

```promql
openviking_feedback_reasked_outcomes_total{valid="1"}
openviking_feedback_reask_rate{valid="1"}
```

reasked total 通常增加 `1`。第二次 assistant 回覆也會增加 `responses_total`，顯式反饋 total 應保持不變。

## 5. 超過十分鐘再追問

用 `realcase-05-followup-no-feedback` 發起問答，不提交反饋，在 assistant 回覆後等待 **超過十分鐘**，再向同一 session 傳送訊息。

```promql
openviking_feedback_follow_up_without_feedback_outcomes_total{valid="1"}
```

上一條 response 應被分類為 `follow_up_without_feedback`，對應 total 增加 `1`。恰好十分鐘或更早的 follow-up 仍屬於 `reasked`；顯式反饋 total 保持不變。

## 6. 理解 `resolved`

沒有後續 user 訊息的 response 會在 **outcome evaluator 執行時** 被分類為 `resolved`。metrics collector 只讀取已儲存的 outcome，不會執行靜默計時器，也不會在十分鐘後自動生成 resolved outcome。

```promql
openviking_feedback_resolved_outcomes_total{valid="1"}
```

因此，發起問答後保持靜默不能作為該指標的確定性驗收用例。如果預期存在 resolved 樣本，請檢查持久化的 `metadata.response_outcomes`。可重複驗收應使用上面的正向、負向和追問場景。

## 7. 驗證 channel 維度

此場景要求已啟用 ID 為 `demo` 的 `bot_api` channel。通過 `/bot/v1/chat/channel` 發起問答：

```bash
curl -sS -X POST "http://127.0.0.1:30300/bot/v1/chat/channel" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "realcase-07-channel-demo",
    "user_id": "metrics-validation-user",
    "channel_id": "demo",
    "message": "請簡要介紹 OpenViking。"
  }'
```

使用返回的 response ID 提交反饋，並帶上相同的 `channel_id`：

```bash
curl -sS -X POST "http://127.0.0.1:30300/bot/v1/feedback" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "realcase-07-channel-demo",
    "response_id": "<response_id>",
    "channel_id": "demo",
    "feedback_type": "thumb_down",
    "feedback_text": "not helpful"
  }'
```

查詢目標 channel：

```promql
openviking_feedback_channel_events_total{channel="bot_api__demo",valid="1"}
openviking_feedback_channel_negative_outcomes_total{channel="bot_api__demo",valid="1"}
openviking_feedback_channel_thumbs_down_rate{channel="bot_api__demo",valid="1"}
```

該 channel 的 event 和 negative-outcome total 應增加；其他 channel 不應因這次請求變化。未配置對應 channel 時會返回 `404`；普通 `/bot/v1/chat` 不經過此 channel 路由。

## 驗收與排障

最小驗收要求 readiness 為 `1`、問答已持久化、正負反饋 total 增加，以及十分鐘內追問後 reasked total 增加。使用 channel 的部署再單獨驗證 channel total。

| 現象 | 檢查項 |
| --- | --- |
| 問答成功，反饋 total 不變 | 是否提交了顯式反饋；普通問答不會建立反饋事件。 |
| 看不到剛提交的事件 | 等待 30 秒 collector TTL、後臺重新整理和下一次 Prometheus 抓取，再檢查會話持久化。 |
| total 變化，比例幾乎不變 | 歷史樣本會稀釋單次變化，先在表格檢視比較當前 total。 |
| 只有 `valid="0"` | 檢查 collector 錯誤和 bot session 目錄的訪問許可權。 |
| 沒有 `bot_api__demo` | 檢查 channel 是否啟用、是否呼叫 `/chat/channel`，以及反饋中的 `channel_id` 是否一致。 |

## 相關文件

- [可觀測性與排障](05-observability.md)
- [Prometheus 和 Grafana 配置](11-grafana-prometheus.md)
- [指標與 Metrics](../concepts/12-metrics.md)
- [Metrics API](../api/09-metrics.md)
