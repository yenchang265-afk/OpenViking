# VikingBot API

Business Data Platform Server 啟用 `--with-bot` 後，會在 `/bot/v1` 下代理 VikingBot 的核心互動介面。未啟用 Bot 時，這些端點返回 `503`。

**程式碼入口**：

- `openviking/server/routers/bot.py` - Business Data Platform Server 代理與身份轉發
- `bot/vikingbot/channels/openapi.py` - VikingBot Gateway 路由實現
- `bot/vikingbot/channels/openapi_models.py` - 請求、響應和 SSE 事件模型

## API 參考

### health()

檢查 Bot Gateway 是否可用。

**HTTP API**

```bash
curl http://localhost:1933/bot/v1/health
```

**響應示例**

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2026-07-24T09:00:00"
}
```

### chat()

傳送文本和/或圖片並等待完整回覆。`session_id` 可省略；省略時 Gateway 會建立新會話。

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `message` | string | 條件必填 | `""` | 使用者文本；`images` 為空時必填 |
| `images` | array | 條件必填 | `[]` | 最多 4 個 OpenAI 風格的 `image_url`；`message` 為空時必填 |
| `session_id` | string | 否 | 自動生成 | 繼續已有會話時傳入 |
| `context` | array | 否 | `null` | 額外上下文訊息，每項包含 `role` 和 `content` |
| `need_reply` | boolean | 否 | `true` | 是否需要 Bot 回覆 |
| `disabled_tools` | string[] | 否 | `[]` | 本次請求停用的工具名 |
| `channel_id` | string | 否 | `null` | 多 Channel 路由標識 |

**HTTP API**

```bash
curl -X POST http://localhost:1933/bot/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"message":"總結我的專案進展","session_id":"optional-session-id"}'
```

圖片可以使用模型可訪問的 HTTPS URL，或內聯 Base64 Data URL：

```bash
curl -X POST http://localhost:1933/bot/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "message": "描述這張圖片",
    "images": [{
      "type": "image_url",
      "image_url": {
        "url": "https://example.com/photo.png"
      }
    }]
  }'
```

內聯 Base64 圖片支援 JPEG、PNG、GIF 和 WebP，解碼後單張最大 10 MiB；內聯 SVG 和 MIME
簽名不匹配的圖片會被拒絕。對於 HTTPS URL，Gateway 只校驗 URL 結構，不會下載或檢查遠端
資源，因此遠端格式支援及相關錯誤由具體 provider 決定。本地檔案路徑仍會被拒絕。可選的
`detail` 支援 `auto`、`low`、`high`；為獲得最好的模型相容性，建議省略。

**CLI**

```bash
ov chat -m "總結我的專案進展"
```

**響應示例**

```json
{
  "session_id": "session-id",
  "response_id": "response-id",
  "message": "這是當前專案進展摘要……",
  "events": null,
  "relevant_memories": null,
  "token_usage": {
    "prompt_tokens": 120,
    "completion_tokens": 42,
    "total_tokens": 162
  },
  "timestamp": "2026-07-24T09:00:00"
}
```

### chat_stream()

以 Server-Sent Events 返回推理、工具呼叫、增量內容和最終響應事件。請求欄位與 `chat()` 相同；Gateway 會自動啟用流式模式。

**HTTP API**

```bash
curl -N -X POST http://localhost:1933/bot/v1/chat/stream \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"message":"分析當前知識庫"}'
```

**CLI**

```bash
ov chat -m "分析當前知識庫"
```

**SSE 響應示例**

每條訊息使用 `data: <json>` 格式，響應頭 `X-VikingBot-Session-ID` 包含本次會話 ID。

```text
data: {"event":"reasoning_delta","data":"正在檢查知識庫…","timestamp":"2026-07-24T09:00:00"}

data: {"event":"content_delta","data":"當前知識庫包含","timestamp":"2026-07-24T09:00:01"}

data: {"event":"response","data":{"content":"當前知識庫包含……","response_id":"response-id"},"timestamp":"2026-07-24T09:00:02"}
```

`event` 可能為 `reasoning`、`reasoning_delta`、`tool_call`、`tool_result`、`content_delta`、`iteration` 或 `response`。

### feedback()

對已經生成的回覆提交顯式反饋。

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `session_id` | string | 是 | 產生目標回覆的會話 ID |
| `response_id` | string | 是 | 目標助手回覆 ID |
| `feedback_type` | string | 是 | `thumb_up`、`thumb_down` 或 `rating` |
| `feedback_score` | number | 條件必填 | `feedback_type=rating` 時必須提供 |
| `feedback_reason` | string | 否 | 反饋原因標籤 |
| `feedback_text` | string | 否 | 自由文本反饋 |
| `channel_id` | string | 否 | 多 Channel 路由標識 |

**HTTP API**

```bash
curl -X POST http://localhost:1933/bot/v1/feedback \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "session_id":"session-id",
    "response_id":"response-id",
    "feedback_type":"thumb_up"
  }'
```

**響應示例**

```json
{
  "accepted": true,
  "response_id": "response-id",
  "session_id": "session-id",
  "feedback_type": "thumb_up",
  "feedback_delay_sec": 8.42,
  "timestamp": "2026-07-24T09:00:08"
}
```

目標回覆不存在時返回 `404`；`rating` 缺少 `feedback_score` 時返回請求校驗錯誤。

## 客戶端範圍

標準 Business Data Platform Python、TypeScript 和 Go SDK 當前不封裝 Bot 代理介面；Chat 可通過 `ov` CLI 與 HTTP 使用。VikingBot Gateway 自身還提供 Session 和 Channel API，詳見 [VikingBot 文件](https://github.com/volcengine/OpenViking/blob/main/bot/README_CN.md#http-api)。

## 相關文件

- [VikingBot 概念](../concepts/15-vikingbot.md) - 架構和互動流程
- [VikingBot 指標驗證](../guides/12-vikingbot-metrics-validation.md) - Chat、Feedback 和指標鏈路
