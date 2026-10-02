# VikingBot 架構

VikingBot 是 Business Data Platform 倉庫內的多渠道 AI Agent 執行時。它將命令列、聊天平臺和 HTTP API 的輸入轉換為統一訊息，由 Agent 完成上下文構建、模型推理和工具呼叫，再把結果交付回原渠道。

## 系統概覽

```text
┌──────────────────────────────────────────────────────────────────┐
│ CLI │ Slack │ Telegram │ Discord │ Email │ HTTP API            │
└─────────────────────────────┬────────────────────────────────────┘
                              │ InboundMessage
                    ┌─────────▼─────────┐
                    │    MessageBus     │
                    │   入站/出站佇列     │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │     AgentLoop     │
                    │ 上下文 → 模型 → 工具 │
                    └───┬─────┬─────┬───┘
                        │     │     │
                ┌───────▼┐ ┌──▼───┐ ┌▼───────────────┐
                │Session │ │Tools │ │  Business Data Platform    │
                │對話歷史 │ │Skills│ │資源/記憶/經驗   │
                └────────┘ └──┬───┘ └────────────────┘
                              │
                        ┌─────▼─────┐
                        │  Sandbox  │
                        │ 檔案與命令 │
                        └───────────┘
```

## 核心模組

| 模組 | 職責 | 主要實現 |
|------|------|----------|
| **Channels** | 適配平臺事件、媒體、許可權和回覆格式 | `vikingbot/channels/` |
| **MessageBus** | 解耦訊息接收、Agent 執行和結果交付 | `vikingbot/bus/` |
| **AgentLoop** | 驅動模型與工具多輪迭代 | `vikingbot/agent/loop.py` |
| **Context** | 組裝身份、工作區、Skill、記憶與歷史 | `vikingbot/agent/context.py` |
| **Providers** | 統一模型、流式輸出和工具呼叫協議 | `vikingbot/providers/` |
| **Tools & Sandbox** | 提供可執行能力及其執行邊界 | `vikingbot/agent/tools/`、`vikingbot/sandbox/` |
| **Session** | 快取並持久化 Bot 對話狀態 | `vikingbot/session/` |
| **Business Data Platform** | 提供資源、長期記憶、經驗和會話沉澱 | `vikingbot/openviking_mount/`、`vikingbot/hooks/` |
| **Gateway** | 執行多渠道服務並提供 HTTP API | `vikingbot/channels/openapi.py` |

## 一條訊息的主鏈路

```text
平臺事件
  → Channel 鑑權並提取文字/媒體
  → 生成 SessionKey 和 InboundMessage
  → MessageBus 入站佇列
  → AgentLoop 載入 Session
  → ContextBuilder 構建系統提示和歷史
  → Provider 呼叫模型
      ├─ 返回文本：形成最終回覆
      └─ 返回工具呼叫：ToolRegistry 執行後繼續呼叫模型
  → 儲存本地 Session，並按策略同步 Business Data Platform
  → MessageBus 出站佇列
  → Channel 交付回覆
```

Agent 處理過程中還會產生 reasoning、content delta、tool call、tool result 和 iteration 等中間事件。OpenAPI 可以把它們作為 SSE 流返回，普通渠道可以只交付最終回覆。

## 訊息與會話標識

所有渠道共享兩個訊息結構：

| 結構 | 主要內容 |
|------|----------|
| `InboundMessage` | 傳送者、文本、媒體、SessionKey、渠道 metadata、Business Data Platform 身份 |
| `OutboundMessage` | 文本、事件型別、回覆目標、媒體、token usage、response ID |

`SessionKey` 由 `type + channel_id + chat_id` 組成，既是會話隔離鍵，也是出站路由和工作區選擇依據。持久化時編碼為 `type__channel_id__chat_id`。

## Agent 執行迴圈

每次模型呼叫可能返回普通文本或一個/多個工具呼叫。AgentLoop 會：

1. 根據當前渠道和請求計算可見工具；
2. 呼叫 Provider，併發布流式事件；
3. 將工具名和引數交給 ToolRegistry 校驗；
4. 在 ToolContext 中注入 SessionKey、傳送者、沙箱和 Business Data Platform 連線；
5. 把工具結果追加到當前訊息上下文；
6. 再次呼叫模型，直到生成最終回答或達到 `max_tool_iterations`。

佇列模式由單個 AgentLoop 消費者按入站順序處理訊息。CLI、Cron 和 Heartbeat 也可以通過 `process_direct()` 直接觸發相同的執行邏輯。

## 模型適配

Provider 層向 AgentLoop 提供統一的 `chat()` 和 `chat_stream()` 介面，並歸一化：

- 最終文本和 reasoning；
- 流式文本、推理和工具引數增量；
- Provider 特有的 system message 和 thinking 引數；
- `prompt_tokens`、`completion_tokens` 和 `total_tokens`。

所有模型統一通過 VLMProviderAdapter 接入 Business Data Platform VLM，包括其 LiteLLM 後端。模型預設讀取根級 `vlm` 配置，`bot.agents` 可以覆蓋 Bot 專用引數。

舊 `bot.providers` 已移除：載入包含此欄位的 `ov.conf` 時會提示並忽略其中的模型配置，不覆蓋 `vlm` 或 `bot.agents`，也不改寫原檔案；再次儲存 Bot 配置時不再寫入該欄位。請將模型憑證配置到 `vlm` 或 `bot.agents`。根級 `vlm.providers` 不受此清理影響。唯一保留的舊用途是 Telegram 語音轉寫：舊 `bot.providers.groq.api_key` 會在載入時遷入各 Telegram 渠道的 `groq_api_key`，但不會覆蓋顯式配置的新欄位（包括空字串）。

## 本地 Session

本地 Session 儲存 user、assistant、tool 和分析事件，使用 JSONL 持久化到 Bot 資料目錄的 `sessions/`。SessionManager 維護記憶體快取，並使用 SessionKey 級非同步鎖保護寫入。

本地 Session 與 Business Data Platform Session 職責不同：前者保證 Bot 對話可以繼續執行，後者用於歸檔、摘要、長期記憶和經驗提取。詳見 [與 Business Data Platform 整合](./04-openviking-integration.md)。

## 執行入口

| 入口 | 用途 | 啟動內容 |
|------|------|----------|
| `vikingbot chat` / `ov chat` | 單次或互動式對話 | CLI Channel、AgentLoop、Session、Sandbox |
| `vikingbot gateway` | 長期執行服務 | Gateway、配置渠道、AgentLoop、Cron、Heartbeat、OpenAPI |

VikingBot 與 Business Data Platform 共用 `ov.conf`。Bot 配置位於 `bot` 欄位，`OPENVIKING_CONFIG_FILE` 可以指定其他配置檔案。

## 執行模式

| 模式 | 行為 |
|------|------|
| `normal` | 正常執行模型、工具和記憶流程 |
| `readonly` | 不註冊 Business Data Platform 資源寫入工具，不執行主動記憶固化 |
| `debug` | 只記錄收到的使用者訊息，不執行模型推理和回覆 |

## 相關文件

- [Agent 能力體系](./02-agent-capabilities.md)
- [渠道、Gateway 與執行管理](./03-channels-and-gateway.md)
- [與 Business Data Platform 整合](./04-openviking-integration.md)
