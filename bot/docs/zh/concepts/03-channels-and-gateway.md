# 渠道、Gateway 與執行管理

Channels 負責把不同聊天平臺適配為統一訊息，Gateway 則把 Channels、AgentLoop、HTTP API、定時任務和觀測能力組裝為長期執行服務。

## 支持的渠道

| 型別 | 連線方式 | 主要能力 |
|------|----------|----------|
| `slack` | Socket Mode | 私聊和群聊策略 |
| `telegram` | Bot API | 文本、媒體和音訊轉寫 |
| `discord` | Gateway | 文本與媒體 |
| `whatsapp` | Node.js WebSocket bridge | WhatsApp 訊息轉發 |
| `dingtalk` | Stream SDK | 訊息接收與回覆 |
| `qq` | QQ Bot API | 訊息接收與回覆 |
| `email` | IMAP + SMTP | 輪詢收件和自動回覆 |
| `mochat` | Socket.IO / Watch API | 會話監聽、@ 和延遲迴復 |
| `openapi` / `bot_api` | FastAPI | HTTP Chat API 與 SSE |

CLI 互動使用 ChatChannel，單條命令使用 SingleTurnChannel，它們也沿用統一訊息模型。

Telegram 語音轉寫金鑰配置在對應的 `bot.channels[]` 條目的 `groq_api_key`（也支援 `groqApiKey`），未配置金鑰時仍可使用 `GROQ_API_KEY` 環境變數。該金鑰獨立於聊天模型的 `vlm` / `bot.agents` 配置。

## Channel 的職責

BaseChannel 和具體平臺實現共同負責：

1. 啟停連線和報告執行狀態；
2. 校驗 `allow_from` 等傳送者策略；
3. 提取文本、圖片、附件和回覆 metadata；
4. 生成 SessionKey 和 InboundMessage；
5. 將 OutboundMessage 轉換為平臺原生回覆；
6. 按平臺能力展示處理中狀態或 reaction。

平臺差異留在具體 Channel 內，AgentLoop 不依賴 Slack 等 SDK。

ChannelManager 從 `bot.channels` 建立所有啟用例項，並以 `type__channel_id` 區分同類型的多個 Bot。它消費 MessageBus 出站佇列，根據 SessionKey 將回復路由到原渠道。

## Gateway 執行時

`vikingbot gateway` 在一個 asyncio 程序中啟動：

```text
FastAPI / Uvicorn
  + OpenAPIChannel
  + 配置的聊天 Channels
  + MessageBus
  + AgentLoop
  + CronService
  + HeartbeatService
```

預設監聽 `127.0.0.1:18790`。當 `gateway.host` 不是 localhost 時，必須設定 `bot.gateway.token`，否則 Gateway 拒絕啟動。

`vikingbot status` 展示當前選擇的模型配置來源（繼承根級 `vlm` 或使用 `bot.agents`）、憑證配置順序、各憑證的 Provider/模型，以及 API key 和自定義請求頭是否配置。它不輸出金鑰或請求頭內容，也不發起模型請求；未配置 API key 不代表本地模型或外部鑑權不可用。這是配置摘要，不是 Gateway 健康檢查，也不代表執行中故障切換後的活躍憑證。

## Bot HTTP API

Bot API 位於 `/bot/v1`：

| 方法 | 路徑 | 作用 |
|------|------|------|
| GET | `/bot/v1/health` | Bot 健康狀態 |
| POST | `/bot/v1/chat` | 同步聊天 |
| POST | `/bot/v1/chat/stream` | SSE 流式聊天 |
| POST | `/bot/v1/chat/channel` | 呼叫指定 Bot Channel |
| POST | `/bot/v1/chat/channel/stream` | 流式呼叫指定 Bot Channel |
| POST | `/bot/v1/feedback` | 提交使用者反饋 |
| GET/POST | `/bot/v1/sessions` | 列出或建立 API Session |
| GET/DELETE | `/bot/v1/sessions/{id}` | 查詢或刪除 API Session |

ChatRequest 支援 session ID、是否回覆、請求級停用工具和渠道 ID。`context` 欄位不接受非空訊息；請省略該欄位或傳入空列表，否則 API 返回 HTTP 422。同一個 session 同時只能有一個進行中的請求；使用相同 session ID 的併發請求會返回 HTTP 409，因此客戶端應序列傳送同 session 請求，並在當前請求完成後重試。ChatResponse 返回 response ID、最終文本、中間事件、相關記憶和 token usage。

SSE 會發送 reasoning、content delta、tool call、tool result、iteration 和最終 response 等事件。

## Business Data Platform API 代理

當配置 Business Data Platform Server 時，Gateway 還提供：

| 路徑 | 作用 |
|------|------|
| `/health` | 彙總 Gateway 和 Business Data Platform upstream 狀態 |
| `/api/v1/{path}` | 代理 Business Data Platform API |

代理會過濾 hop-by-hop headers，轉發經過校驗的身份頭，並保持上游響應狀態。詳細連線與身份流程見 [與 Business Data Platform 整合](./04-openviking-integration.md)。

## 訪問控制

Gateway 使用多層安全邊界：

1. 非本地監聽要求 `X-Gateway-Token`；
2. loopback 請求可以使用本地開發邊界；
3. Business Data Platform API key 通過 upstream `/health` 驗證身份和實際 auth mode；
4. 只有可信 Business Data Platform Server 代理才能傳入 `openviking_connection`；
5. API Session 使用認證主體 scope 與外部 session ID 組合隔離。

普通請求欄位中的 `user_id`、account ID 或 connection 資訊不能自行證明 Business Data Platform 身份。

## 反饋與結果評估

每條最終回覆都生成 `response_id`。客戶端可以提交 thumb up、thumb down 或數值 rating，並附帶原因與文本。Gateway 會儲存反饋、計算反饋延遲併發布 `feedback_submitted` 事件。

當用戶繼續對話時，Outcome Evaluator 還可以根據後續行為評估上一條回覆，形成 `response_outcome_evaluated` 事件。`vikingbot feedback-stats` 聚合本地 Session，統計反饋覆蓋率、評分、結果狀態、工具使用和延遲。

## Langfuse 與日誌

設定 `bot.langfuse.enabled=true` 後，模型呼叫、token usage、耗時、工具事件和結果 metadata 會寫入 Langfuse。Langfuse 初始化失敗不會阻斷 Bot 主鏈路。

執行日誌使用 Loguru；Gateway 的 `--verbose` 可以開啟更詳細日誌。分析專用事件與普通回覆分離，不會被誤發到聊天平臺。

## 實現位置

| 內容 | 路徑 |
|------|------|
| 渠道基類與管理 | `vikingbot/channels/base.py`、`manager.py` |
| 平臺適配 | `vikingbot/channels/*.py` |
| Gateway/OpenAPI | `vikingbot/channels/openapi.py` |
| API 資料模型 | `vikingbot/channels/openapi_models.py` |
| 執行時組裝 | `vikingbot/cli/commands.py` |
| 反饋與結果 | `vikingbot/observability/` |
| Langfuse | `vikingbot/integrations/langfuse.py` |

## 相關文件

- [VikingBot 架構](./01-architecture.md)
- [Agent 能力體系](./02-agent-capabilities.md)
- [與 Business Data Platform 整合](./04-openviking-integration.md)
- [渠道配置](../../CHANNEL.md)
