# VikingBot 安裝與配置

先了解 [VikingBot 的用途與架構](../concepts/15-vikingbot.md)，再按本頁完成安裝。

VikingBot 是 OpenViking 內建的多渠道 AI Agent。它既可以和 OpenViking 一起啟動，也可以在本地獨立除錯，或作為長期執行的 Gateway 接入聊天平臺。

本指南介紹安裝方式，以及三種主要使用場景的配置和啟動方法。Agent 工具、聊天渠道、架構等完整說明請參見 [VikingBot 中文文件](https://github.com/volcengine/OpenViking/blob/main/bot/README_CN.md)。

## 安裝

VikingBot 建議使用 Python 3.11 或更高版本。

### 從 PyPI 安裝

選擇你常用的 Python 包管理工具安裝 VikingBot：

::: code-group

```bash [uv（推薦）]
uv tool install "openviking[bot]" --upgrade
```

```bash [pip]
pip install "openviking[bot]" --upgrade
```

```bash [pipx]
# 安裝
pipx install "openviking[bot]"

# 更新
pipx upgrade openviking
```

:::

安裝後檢查版本：

```bash
vikingbot --version
```

使用 pip 時先啟用虛擬環境。原始碼安裝還需要準備[開發構建依賴](https://github.com/volcengine/OpenViking/blob/main/CONTRIBUTING.md)。

### 從原始碼安裝

```bash
git clone https://github.com/volcengine/OpenViking.git
cd OpenViking

uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[bot]"
```

Windows 使用以下命令啟用虛擬環境：

```powershell
.venv\Scripts\activate
```

## 配置文件

VikingBot 與 OpenViking 共用 `~/.openviking/ov.conf`。如果配置檔案位於其他路徑，通過環境變數指定：

```bash
export OPENVIKING_CONFIG_FILE=/path/to/ov.conf
```

修改配置後，需要重啟 VikingBot 或 OpenViking Server 才會生效。

## 選擇使用場景

| 場景 | 適用情況 | 啟動命令 | OpenViking |
|------|----------|----------|------------|
| **A. OpenViking + Bot 一體啟動** | 完整體驗資源、記憶和 Agent | `openviking-server --with-bot` | 使用當前啟動的 Server |
| **B. 本地除錯 Agent** | 快速試用 Bot，開發 Tool 或 Skill | `vikingbot chat` | 可選 |
| **C. Gateway 統一入口** | 長期執行、遠端訪問或接入聊天平臺 | `vikingbot gateway` | 可連線已有 Server，也可 standalone 執行 |

三種場景是不同的執行入口，可以共用同一份 `ov.conf`。

## 場景 A：OpenViking + Bot 一體啟動

這是本地完整體驗的推薦方式。OpenViking Server 和 VikingBot Gateway 會一起啟動：

```text
ov chat → OpenViking Server → VikingBot Gateway → Agent
```

### 1. 配置 OpenViking

首次使用時執行初始化嚮導，並檢查模型和儲存配置：

```bash
openviking-server init
openviking-server doctor
```

詳細配置見 [OpenViking 配置指南](01-configuration.md)。VikingBot 預設繼承根級 `vlm` 作為 Agent 模型，因此通常不需要重複配置 `bot.agents`。

Server 使用 `api_key` 模式時，先註冊 User/Admin Key 並寫入 `bot.ov_server.api_key`；不能把 root API 金鑰當作使用者 Key 使用。操作見[認證指南](04-authentication.md)。繼承 `trusted` 模式時，Bot 使用服務端的可信身份配置。

### 2. 一體啟動

```bash
openviking-server --with-bot
```

在此模式下，Bot 固定連線當前啟動的 OpenViking Server，不使用 `bot.ov_server.server_url` 指向其他服務。

### 3. 配置並使用 `ov` CLI

```bash
ov config
ov chat
ov chat -m "記住我更喜歡簡潔的回答"
ov find "我的回答偏好"
```

`ov config` 中的 URL 應指向當前 OpenViking Server，預設是 `http://127.0.0.1:1933`。如果 Server 開啟了鑑權，還需要配置當前呼叫者的 User/Admin API Key。

記憶在 commit 後非同步提取，立即執行 `ov find` 可能還沒有結果。用檢索驗證記憶是否儲存前，先確認記憶任務已完成。

## 場景 B：本地除錯 Agent

適合快速試用 VikingBot，或開發 Agent、Tool 和 Skill。`vikingbot chat` 會在當前程序中直接執行 Agent，不需要先啟動 Gateway。

### 1. 配置 Agent 模型

如果 `ov.conf` 已經配置根級 `vlm`，VikingBot 會直接繼承。也可以使用獨立的 Agent 模型：

```json
{
  "bot": {
    "agents": {
      "provider": "openai",
      "model": "gpt-4o-mini",
      "api_key": "<your-model-api-key>",
      "max_tokens": 8192
    }
  }
}
```

`bot.agents` 可以配置自己的有序 `credentials` 主備鏈；每項都配置 `model` 時，
外層 `bot.agents.model` 可以省略：

```json
{
  "bot": {
    "agents": {
      "max_tokens": 8192,
      "credentials": [
        {
          "id": "bot-primary",
          "provider": "volcengine",
          "model": "bot-primary-model",
          "api_key": "${BOT_PRIMARY_API_KEY}",
          "max_tokens": 4096
        },
        {
          "id": "bot-backup",
          "provider": "openai",
          "model": "bot-backup-model",
          "api_key": "${BOT_BACKUP_API_KEY}"
        }
      ],
      "failback_timeout_seconds": 600,
      "failback_request_count": 50
    }
  }
}
```

優先順序是確定的：存在非空的 `bot.agents.model` 或 `bot.agents.credentials` 時，
使用 Bot 自己的模型/credentials；兩者都省略時，完整繼承根級 `vlm` 的模型、
credentials 和 failover/failback 設定。配置 Bot credentials 但省略外層 model
時，每個 credential 都必須配置自己的 `model`。兩條 credentials 鏈不會混用。
`max_tokens` 是可選項：credential 自己的值優先於 `bot.agents.max_tokens`，未配置
時繼承 Agent 級值；兩層都未配置時，VikingBot 不傳送該請求欄位，由模型服務決定
預設輸出上限。

### 2. 啟動對話

```bash
# 單次呼叫
vikingbot chat -m "幫我總結當前目錄的專案結構"

# 互動式多輪對話
vikingbot chat

# 指定會話
vikingbot chat --session my-session
```

本地 chat 未顯式配置 `bot.ov_server.server_url` 時，連線繼承的服務失敗可降級為 standalone。顯式配置的服務不可用時停止啟動。繼承的認證模式不匹配也會停止啟動；顯式配置遠端服務時，Bot 會採用服務端報告的模式，再驗證憑據。認證失敗或收到不健康的 HTTP 響應都會停止啟動。一體啟動由服務端管理時，Bot 會保留繼承的上游配置並等待服務啟動。

standalone 模式下，本地檔案、Shell、Web 和 Skill 等能力仍可使用，但不會提供 OpenViking 資源檢索和長期記憶能力。

## 場景 C：Gateway 統一入口

適合長期執行、遠端訪問和接入 Slack、Telegram 等聊天平臺。Gateway 提供 Bot HTTP API，也可以代理 OpenViking API，讓 `ov` CLI 使用同一個入口。

### 1. 配置 Gateway 和 OpenViking

下面的示例讓 Gateway 連線一個已有的 OpenViking Server：

```json
{
  "bot": {
    "agents": {
      "provider": "openai",
      "model": "gpt-4o-mini",
      "api_key": "<your-model-api-key>"
    },
    "gateway": {
      "host": "127.0.0.1",
      "port": 18790
    },
    "ov_server": {
      "server_url": "https://openviking.example.com",
      "api_key_type": "user",
      "api_key": "<bot-openviking-user-api-key>"
    }
  }
}
```

Gateway 有三種 OpenViking 連線狀態：

- 配置 `bot.ov_server.server_url`：連線指定的 OpenViking Server；連線失敗時拒絕啟動。
- 未配置該 URL，但同一份 `ov.conf` 配置了 `server`：繼承該 Server 地址；不可用時降級為 standalone。
- 沒有可用 Server：Chat 仍可使用，但 OpenViking 工具和 API 代理不可用。

### 2. 啟動 Gateway

```bash
vikingbot gateway
```

### 3. 讓 `ov` CLI 使用 Gateway

編輯 `~/.openviking/ovcli.conf`：

```json
{
  "url": "http://127.0.0.1:18790",
  "api_key": "<caller-openviking-user-or-admin-api-key>",
  "actor_peer_id": "cli"
}
```

隨後 Chat 和 OpenViking 命令都可以通過 Gateway：

```bash
ov chat -m "檢索專案資料並給出結論"
ov ls viking://resources/
ov find "專案釋出流程"
```

Gateway 預設只監聽 `127.0.0.1`。如果改為 `0.0.0.0` 或其他非 localhost 地址，必須配置 `bot.gateway.token`，並在客戶端設定對應的 `gateway_token`。

聊天平臺的憑證和許可權配置見 [VikingBot 渠道配置](https://github.com/volcengine/OpenViking/blob/main/bot/docs/zh/concepts/05-channel.md)。

## 通過 Web Studio 管理

開啟 Web Studio 的 `/vikingbot` 頁面，可使用網頁對話或管理 Server 受管 Bot 的 Telegram 連線。渠道管理和對話歷史僅允許 ROOT 訪問，並按 Studio 當前選擇的 account 隔離；Account ADMIN Key 不具備該許可權。Studio 使用 `GET /api/v1/admin/bot/capabilities`，以及 `/api/v1/admin/accounts/{account_id}/bot` 下的連線、會話、驗證和接入任務介面。

Telegram 接入分三步：

1. 選擇同帳戶普通使用者作為連線的執行身份。服務端繫結可用憑證，瀏覽器無需接收該使用者的 API Key。
2. 貼上從 @BotFather 取得的 bot token，並列出允許與 bot 對話的 Telegram 使用者（1–100 個）。服務端儲存前會先向 Telegram 驗證 token。
3. 向 bot 傳送訊息，驗證訊息接收和回覆。

連線和捕獲的訊息儲存在 Bot 資料目錄的 `studio.sqlite3`，檔案許可權為 `0600`。資料庫含 bot token 和繫結使用者的憑證，備份需按服務端配置處理。Studio 管理的會話只開放繫結身份允許的 OpenViking 查詢和記憶工具；Shell、本地檔案、定時任務和未批准的 MCP 工具不可用。

暫停連線保留歷史。刪除連線會移除本地記錄，不會刪除 Telegram bot 或其中的訊息。對話歷史在 Studio 中只讀，從該 Studio 連線捕獲的訊息開始；不會自動遷入 `ov.conf` 中已有的渠道及其舊歷史。同一連線暫停恢復或重啟後保留上下文；刪除並重建連線會建立新的上下文。

## 更多文件

- [VikingBot 完整使用說明](https://github.com/volcengine/OpenViking/blob/main/bot/README_CN.md)
- [VikingBot 架構](https://github.com/volcengine/OpenViking/blob/main/bot/docs/zh/concepts/01-architecture.md)
- [Agent 能力體系](https://github.com/volcengine/OpenViking/blob/main/bot/docs/zh/concepts/02-agent-capabilities.md)
- [渠道、Gateway 與執行管理](https://github.com/volcengine/OpenViking/blob/main/bot/docs/zh/concepts/03-channels-and-gateway.md)
- [VikingBot 與 OpenViking 整合](https://github.com/volcengine/OpenViking/blob/main/bot/docs/zh/concepts/04-openviking-integration.md)
- [聊天渠道配置](https://github.com/volcengine/OpenViking/blob/main/bot/docs/zh/concepts/05-channel.md)
