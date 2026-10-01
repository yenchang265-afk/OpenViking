# VikingBot：基於 OpenViking 的多渠道 AI Agent

VikingBot 是 OpenViking 提供的多渠道 AI Agent。OpenViking 負責統一管理 Resource、Memory 和 Skill 等長期上下文；VikingBot 負責接收使用者訊息、組織上下文、呼叫模型和工具，並把任務結果交付回命令列、聊天平臺或 HTTP 客戶端。

兩者組合後，Agent 不僅能完成當前任務，還能持續積累使用者記憶、會話摘要和任務經驗，在後續任務中再次使用。

## VikingBot 與 OpenViking 的分工

| 元件 | 主要職責 | 典型能力 |
|------|----------|----------|
| **OpenViking** | 上下文儲存、組織和檢索 | Resource、Memory、Skill、Session、語義檢索、記憶與經驗提取 |
| **VikingBot** | Agent 執行和互動 | 多渠道訊息、模型推理、工具呼叫、Skill 執行、沙箱、自動化、結果交付 |

## 系統概覽

```text
CLI / Slack / Telegram / Discord / Email / HTTP API
                              │
                              ▼
                    Channel + MessageBus
                              │
                              ▼
                         AgentLoop
                 上下文 → 模型 → 工具 → 模型
                    │                   │
          ┌─────────┴─────────┐         ▼
          ▼                   ▼       回覆與事件
  OpenViking Context     Tools / Skills
  Resource / Memory      Files / Shell / Web
  Experience / Session   MCP / Cron / Subagent
          │                   │
          └─────────┬─────────┘
                    ▼
             Session 同步與經驗沉澱
```

所有入口最終使用同一套 AgentLoop。渠道差異被轉換為統一訊息，模型和工具無需感知訊息來自命令列、聊天平臺還是 HTTP API。

## 核心能力

### 多入口與多渠道

VikingBot 支援三類入口：

- `vikingbot chat` 和 `ov chat`：單次呼叫或互動式命令列對話；
- Slack、Telegram、Discord、WhatsApp、DingTalk、QQ、Email 和 MoChat：長期執行的聊天機器人；
- `/bot/v1` HTTP API：同步 Chat、SSE 流式事件、Session 和反饋介面。

每個渠道負責平臺鑑權、傳送者白名單、媒體解析、回覆格式和會話路由。VikingBot 使用 `type + channel_id + chat_id` 隔離不同渠道例項和會話。

### Agent 執行迴圈

AgentLoop 是 VikingBot 的執行核心。每輪訊息會經過：

1. 載入身份、工作區規則、Skill、會話歷史和 OpenViking 上下文；
2. 呼叫配置的模型；
3. 如果模型返回工具呼叫，由 ToolRegistry 校驗引數並執行；
4. 將工具結果加入上下文，再次呼叫模型；
5. 生成最終回覆，儲存 Session，並投遞迴原渠道。

模型 Provider 層統一處理文本、reasoning、流式增量、工具呼叫和 token usage。Bot 預設繼承 OpenViking 根級 `vlm`，也可以通過 `bot.agents` 使用獨立模型。

### 工具、Skill 與子 Agent

VikingBot 內建檔案、Shell、Web、圖片、定時任務和 OpenViking 工具，也可以連線外部 MCP Server。

| 能力 | 作用 |
|------|------|
| **Tool** | 執行檔案讀寫、命令、搜尋、訊息傳送等具體操作 |
| **Skill** | 向 Agent 提供完成一類任務的流程、約束和配套資源 |
| **MCP** | 將外部服務能力註冊為普通 Agent 工具 |
| **Subagent** | 在後臺執行可獨立完成的複雜任務，並將結果返回主 Agent |

Skill 採用漸進式載入，只有需要時才讀取完整指令。工具是否可見由執行模式、渠道配置、請求引數和沙箱共同決定。

### 沙箱與工作區

檔案和 Shell 工具通過 SandboxManager 執行。工作區可以由所有會話共享，也可以按 Session 或 Channel 隔離。

VikingBot 支援 Direct、SRT、OpenSandbox 和 AIO Sandbox 等後端。`direct` 直接使用 Bot 程序許可權，不是強隔離環境；面向不可信使用者時，應選擇隔離後端並配置檔案和網路策略。

### 自動化與主動任務

VikingBot 提供兩種主動執行機制：

- **Cron**：按一次性時間、固定間隔或 cron 表示式觸發 Agent；
- **Heartbeat**：週期讀取工作區中的 `HEARTBEAT.md`，檢查持續性任務。

兩者最終都呼叫同一個 AgentLoop，並可以把結果交付回原 Session 和渠道。

### Gateway 與服務化執行

`vikingbot gateway` 將以下能力組合為長期執行服務：

- 已配置的聊天 Channels；
- Bot HTTP API 和 SSE 流式事件；
- AgentLoop、Session、Cron 和 Heartbeat；
- OpenViking API 代理；
- 使用者反饋、結果評估、日誌和可選 Langfuse 觀測。

配置 OpenViking upstream 後，Bot Chat 和 `/api/v1/*` 可以使用同一個 Gateway 地址，但 Gateway Token 與 OpenViking 使用者身份仍是兩個獨立安全邊界。

## OpenViking 如何增強 VikingBot

### Resource：任務知識

Resource 為 Agent 提供文件、程式碼、網頁和其他外部知識。VikingBot 可以語義檢索、按路徑瀏覽、進行 grep/glob 搜尋，並只讀取當前任務真正需要的完整內容。

### Memory：使用者與 Peer 上下文

VikingBot 根據當前可信 `actor_peer_id` 讀取 Peer Profile，並按型別召回：

- `events`：歷史事件和決策；
- `entities`：人、專案和組織等實體資訊；
- `preferences`：使用者偏好、習慣和約束。

這使不同使用者共享同一個 Gateway 時，仍能使用各自隔離的上下文。

### Experience：可複用任務經驗

Experience 儲存 Agent 過去完成類似任務的方法。VikingBot 可以在任務開始、讀取 Skill 後或執行寫操作前召回相關經驗，減少重複試錯。

### Session：從對話到長期上下文

VikingBot 本地 Session 儲存執行歷史和渠道狀態；OpenViking Session 負責訊息歸檔、壓縮摘要、記憶和經驗提取。

```text
當前任務
  → 召回 Resource / Memory / Experience
  → Agent 使用 Skill 和工具執行
  → 保存本地 Session
  → 增量同步並提交 OpenViking Session
  → 提取新的 Memory 和 Experience
  → 後續任務再次召回
```

普通會話會按策略自動同步。只有使用者明確要求長期記住某項資訊時，Agent 才主動呼叫記憶提交工具。

## 三種執行入口

| 入口 | 適用場景 | OpenViking 連線 |
|------|----------|----------------|
| `openviking-server --with-bot` | 本地完整體驗 | 使用當前啟動的 OpenViking Server |
| `vikingbot chat` | 快速試用和 Agent 開發 | 可選；不可用時 standalone 執行 |
| `vikingbot gateway` | 長期服務、遠端訪問和聊天平臺 | 可連線指定或同配置中的 Server，也可 standalone 執行 |

安裝、配置和每種入口的啟動步驟見 [VikingBot 安裝與配置](../guides/17-vikingbot.md)。

## 身份與安全邊界

VikingBot 的訪問控制分為多層：

- Channel 使用 `allow_from` 等策略限制訊息傳送者；
- 非 localhost Gateway 必須配置 Gateway Token；
- OpenViking Server 驗證 User/Admin API Key 或 trusted 身份；
- request-scoped OpenViking 連線只接受可信 Server 代理注入；
- Sandbox 控制檔案、命令和網路訪問邊界。

Gateway Token 只保護 Gateway 入口，不能代替 OpenViking 使用者身份。對於公網或多使用者部署，不應使用 `direct` 後端處理不可信請求。

## 適用場景

- 帶長期記憶的個人或團隊助手；
- 接入企業聊天平臺的知識與任務 Bot；
- 需要文件、Shell、Web、MCP 和 Skill 的通用 Agent；
- 通過統一 Gateway 暴露 Chat 與 OpenViking API；
- 需要記錄反饋、結果和任務經驗的持續學習型 Agent。

## 相關文件

- [VikingBot 安裝與配置](../guides/17-vikingbot.md)
- [VikingBot 完整使用說明](https://github.com/volcengine/OpenViking/blob/main/bot/README_CN.md)
- [VikingBot 架構詳解](https://github.com/volcengine/OpenViking/blob/main/bot/docs/zh/concepts/01-architecture.md)
- [Agent 能力體系](https://github.com/volcengine/OpenViking/blob/main/bot/docs/zh/concepts/02-agent-capabilities.md)
- [渠道、Gateway 與執行管理](https://github.com/volcengine/OpenViking/blob/main/bot/docs/zh/concepts/03-channels-and-gateway.md)
- [VikingBot 與 OpenViking 整合](https://github.com/volcengine/OpenViking/blob/main/bot/docs/zh/concepts/04-openviking-integration.md)
- [OpenViking 上下文型別](./02-context-types.md)
- [OpenViking 會話管理](./08-session.md)
