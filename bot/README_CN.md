# VikingBot

VikingBot 是 OpenViking 內建的多渠道 AI Agent。它可以在命令列中直接使用，也可以作為長期執行的 Gateway 接入 Slack、Telegram 等平臺；連線 OpenViking 後，還能使用資源檢索、使用者記憶、經驗記憶和會話沉澱能力。

## 主要能力

- **多入口對話**：支援 `vikingbot chat`、`ov chat`、HTTP API 和多個聊天平臺。
- **Agent 工具**：內建檔案、Shell、Web、圖片生成、定時任務和 OpenViking 工具。
- **Skill 與子 Agent**：按需載入 Skill，可使用後臺子 Agent 處理獨立任務。
- **長期上下文**：從 OpenViking 召回 Resource、Peer Memory 和 Experience，並自動提交會話。
- **安全執行**：支援 Direct、SRT、OpenSandbox 和 AIO Sandbox 後端。
- **服務化執行**：Gateway 提供同步 Chat API、SSE 流式事件、反饋和 OpenViking API 代理。

## 安裝

> **OpenViking Server 要求**：VikingBot 通過 `viking://~` Home 別名訪問呼叫方自己的上下文空間（例如 `viking://~/memories/`），因此需要一個支援 `viking://~` 的 Server。不帶 uid 的舊寫法 `viking://user/memories` 已不再產生，且會被新版 Server 拒絕。

### 從 PyPI 安裝

```bash
pip install "openviking[bot]"
```

### 從原始碼安裝

需要 Python 3.11 或更高版本，並建議使用 [uv](https://github.com/astral-sh/uv)：

```bash
git clone https://github.com/volcengine/OpenViking.git
cd OpenViking
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[bot]"
```

Windows 啟用虛擬環境：

```powershell
.venv\Scripts\activate
```

## 快速開始：先選擇使用場景

VikingBot 有三種主要使用方式。它們不是互相替代的模式，而是面向不同需求的入口。

| 場景 | 適合誰                             | 啟動命令 | OpenViking                    |
|------|---------------------------------|----------|-------------------------------|
| **A. OpenViking + Bot 一體啟動** | 本地完整體驗資源、記憶和 Agent              | `openviking-server --with-bot` | bot將使用當前啟動的 OpenViking Server |
| **B. 本地除錯 Agent** | 想快速測試 Bot、開發 Tool/Skill         | `vikingbot chat` | 可選；未配置時，bot無法使用OpenViking功能   |
| **C. Gateway 統一入口** | 單獨啟動bot，並配置已有的OpenViking Server | `vikingbot gateway` | 可顯式配置或不配置                     |

### 場景 A：OpenViking + Bot 一體啟動

適合本地完整體驗。OpenViking Server 和 VikingBot Gateway 一起啟動，`ov chat` 先訪問 OpenViking Server，再由 Server 的 `/bot/v1` 路由轉發到 VikingBot。

```text
ov chat → OpenViking Server → VikingBot Gateway → Agent
```

#### 1. 準備配置

先按照 [OpenViking 快速開始](../docs/zh/getting-started/03-quickstart-server.md)配置好 OpenViking 所需的模型和儲存。Bot 預設繼承根級 `vlm` 作為 Agent 模型；如需使用獨立模型，再配置 `bot.agents`。

一體啟動時，Bot 固定使用當前啟動的 OpenViking Server；`bot.ov_server.server_url` 會被忽略，但顯式配置的 `bot.ov_server.api_key` 和其他 Bot 側 OpenViking 設定會保留。`api_key` 模式下，該 key 必須是 User/Admin key。OpenViking Server 會為每個 Chat 請求向 Bot 注入已經認證的 request-scoped 身份。

#### 2. 一體啟動

```bash
openviking-server --with-bot
```

該命令會啟動當前 OpenViking Server，並啟動一個受管的 VikingBot Gateway。此時 Bot 使用當前 Server，不會連線 `bot.ov_server.server_url` 指向的另一套服務。

#### 3. 配置並使用 `ov` CLI

執行互動式配置：

```bash
ov config
```

讓當前 CLI 配置指向 OpenViking Server，例如 `http://127.0.0.1:1933`；如果 Server 開啟了鑑權，再填寫呼叫者的 User/Admin API Key。然後：

```bash
ov chat
ov chat -m "記住我更喜歡簡潔的回答"
ov find "我的回答偏好"
```

這裡的身份關係是：

- `ovcli.conf.api_key` 是當前呼叫者身份；
- OpenViking Server 校驗該身份後，將 request-scoped 連線傳給 Bot；
- 該請求身份優先於任何程序級預設身份，避免多個呼叫者共享同一個 Bot 使用者。

### 場景 B：本地除錯 Agent

適合快速試用 VikingBot，或者開發 Agent、Tool、Skill。`vikingbot chat` 在當前程序內啟動 Agent，不需要先啟動 Gateway，也不讀取 `ovcli.conf` 作為 Bot 配置。

#### 1. 配置模型

編輯 `~/.openviking/ov.conf`：

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

也可以只配置根級 `vlm`，VikingBot 會繼承其中的模型、Provider、API Key、API Base、超時和輸出 Token 配置。`bot.agents.max_tokens` 是可選項；不配置時由模型服務決定輸出上限。單個 credential 上的 `max_tokens` 會覆蓋 Agent 級值。

#### 2. 開始對話

```bash
# 單次呼叫
vikingbot chat -m "幫我總結當前目錄的專案結構"

# 互動式多輪對話
vikingbot chat

# 指定會話
vikingbot chat --session my-session
```

沒有可用 OpenViking Server 時，VikingBot 會以 standalone 方式執行：檔案、Shell、Web、Skill 等能力仍可使用，但不會提供 OpenViking 記憶和檔案工具。

如果希望除錯時連線 OpenViking，可在同一個 `ov.conf` 中配置 `server`，或顯式配置 `bot.ov_server.server_url`，參見[連線 OpenViking](#連線-openviking)。

### 場景 C：Gateway 統一入口

適合長期執行、遠端訪問和多渠道接入。`ovcli.conf.url` 可以直接指向 VikingBot Gateway：

```text
ov chat                  → Gateway /bot/v1/chat
ov ls/find/session/...   → Gateway /api/v1/* → OpenViking Server
```

Gateway 與 OpenViking 有三種連線狀態：

| 狀態 | 條件 | 行為 |
|------|------|------|
| **Explicit** | 配置 `bot.ov_server.server_url` | 連線指定 OpenViking；不可達時啟動失敗 |
| **Inherited** | 未顯式配置 URL，但同一 `ov.conf` 有 `server` | 連線該 OpenViking；不可達時降級為 standalone |
| **Standalone** | 沒有可用 OpenViking | Chat 可用；OpenViking 工具停用，`/api/v1/*` 返回 503 |

#### 1. 配置 Gateway 和 OpenViking

下面是顯式連線遠端 OpenViking 的示例：

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
      "api_key": "<bot-openviking-user-api-key>"
    }
  }
}
```

如果遠端 OpenViking 使用 `trusted` 模式，應設定 `api_key_type: "root"`，並在 `api_key` 中填寫 Root Key。

#### 2. 啟動 Gateway

```bash
vikingbot gateway
```

啟動日誌會顯示 `openviking_explicit`、`openviking_inherited` 或 `standalone_local` 等實際狀態。

#### 3. 讓 `ov` CLI 指向 Gateway

可以使用 `ov config`，也可以編輯 `~/.openviking/ovcli.conf`：

```json
{
  "url": "http://127.0.0.1:18790",
  "api_key": "<caller-openviking-user-or-admin-api-key>",
  "actor_peer_id": "cli"
}
```

隨後 Chat 和其他 OpenViking 命令都使用同一個入口：

```bash
ov chat -m "檢索專案資料並給我一個結論"
ov ls viking://resources/
ov find "專案釋出流程"
```

#### 4. 對外監聽時配置 Gateway Token

Gateway 預設只監聽 `127.0.0.1`。改成 `0.0.0.0` 或其他非 localhost 地址時，必須配置 Token，否則拒絕啟動：

```json
{
  "bot": {
    "gateway": {
      "host": "0.0.0.0",
      "port": 18790,
      "token": "<strong-random-token>"
    }
  }
}
```

客戶端在 `ovcli.conf` 中增加：

```json
{
  "url": "https://bot.example.com",
  "api_key": "<caller-openviking-user-or-admin-api-key>",
  "gateway_token": "<strong-random-token>",
  "actor_peer_id": "cli"
}
```

Gateway Token 只保護 Gateway 入口；OpenViking API Key 表示呼叫者身份，兩者不能互相替代。Gateway Token 不會轉發給 OpenViking。

## 接入聊天平臺

需要 Slack、Telegram、Discord、WhatsApp、釘釘、QQ、Email 或 MoChat 時，在場景 C 的基礎上配置 `bot.channels`，然後啟動 Gateway。

以 Slack 為例：

```json
{
  "bot": {
    "channels": [
      {
        "type": "slack",
        "enabled": true,
        "bot_token": "<slack-bot-token>",
        "app_token": "<slack-app-token>",
        "allow_from": [],
        "ov_tools_enable": true
      }
    ]
  }
}
```

```bash
vikingbot gateway
vikingbot channels status
```

同一種渠道可以配置多個例項。VikingBot 使用 `type + channel_id + chat_id` 隔離會話和路由回覆。各平臺的憑證、事件訂閱和許可權配置見 [渠道配置](docs/zh/concepts/05-channel.md)。

## 連線 OpenViking

VikingBot 與 OpenViking 共用 `~/.openviking/ov.conf`。連線優先順序和行為如下：

1. `openviking-server --with-bot` 啟動的受管 Bot 使用當前 Server；
2. 普通 `vikingbot gateway/chat` 優先使用顯式 `bot.ov_server.server_url`；
3. 沒有顯式 URL 時，從同一份 `ov.conf.server` 推導地址；
4. 沒有可用地址時以 standalone 執行。

鑑權要求：

| OpenViking `auth_mode` | Bot 憑證 | Gateway 請求 |
|------------------------|----------|----------------|
| `dev` | 本地使用 | Gateway 必須監聽 localhost |
| `api_key` | `bot.ov_server.api_key` 必須是 User/Admin Key | Chat 呼叫者也必須提供有效 User/Admin Key；Root Key 不可用於資料介面 |
| `trusted` | 顯式連線使用 Root Key；繼承連線可讀取 `server.root_api_key` | 非本地入口還必須先通過 Gateway Token |

Gateway 會在啟動時校驗 upstream 和 Bot 憑證，並在每個請求中檢查 OpenViking 當前鑑權模式。執行時模式發生變化時會 fail closed，要求修正配置或重啟 Gateway。

VikingBot 使用 OpenViking 完成：

- 讀取當前 Peer Profile；
- 按型別召回 events、entities 和 preferences；
- 檢索 Agent Experience；
- 瀏覽、搜尋和讀取 Resource；
- 增量同步並提交 Session，提取長期記憶與經驗。

詳細呼叫鏈見 [VikingBot 與 OpenViking 整合](docs/zh/concepts/04-openviking-integration.md)。Gateway 入口與鑑權邊界來自 [RFC #3042](https://github.com/volcengine/OpenViking/discussions/3042)。

## 配置說明

配置檔案預設為 `~/.openviking/ov.conf`，可通過環境變數指定：

```bash
export OPENVIKING_CONFIG_FILE=/path/to/ov.conf
```

修改配置後需要重啟 `vikingbot gateway`。

### 常用配置

| 配置 | 預設值 | 說明 |
|------|--------|------|
| `bot.agents.temperature` | `0.7` | 模型取樣溫度 |
| `bot.agents.thinking` | `true` | Provider 支援時啟用 reasoning/thinking |
| `bot.agents.timeout` | 繼承 `vlm.timeout` | 單次模型請求超時 |
| `bot.agents.max_tool_iterations` | `50` | 單輪最大工具迭代數 |
| `bot.agents.memory_window` | `50` | 本地歷史視窗和會話提交訊息閾值 |
| `bot.agents.subagent_enabled` | `true` | 是否提供 `spawn` 工具 |
| `bot.agents.subagent_max_concurrency` | `4` | 同時執行的後臺子 Agent 數量上限 |
| `bot.gateway.host` | `127.0.0.1` | Gateway 監聽地址 |
| `bot.gateway.port` | `18790` | Gateway 監聽埠 |
| `bot.sandbox.backend` | `direct` | 執行後端 |
| `bot.sandbox.mode` | `shared` | 工作區隔離方式 |
| `bot.sandbox.backends.direct.allow_compile_exec` | `true` | 如需關閉可顯式設為 `false` |
| `bot.heartbeat.enabled` | `true` | 是否週期檢查 `HEARTBEAT.md` |
| `bot.heartbeat.interval_seconds` | `600` | 心跳間隔 |
| `bot.mode` | `normal` | 可選 `normal`、`readonly`、`debug` |

### OpenViking 召回配置

| 配置 | 預設值 | 說明 |
|------|--------|------|
| `bot.ov_server.memory_recall_events_limit` | `10` | 每輪 events 記憶條數 |
| `bot.ov_server.memory_recall_entities_limit` | `10` | 每輪 entities 記憶條數 |
| `bot.ov_server.memory_recall_preferences_limit` | `3` | 每輪 preferences 記憶條數 |
| `bot.ov_server.memory_recall_max_chars` | `4000` | Peer 記憶注入字元預算 |
| `bot.ov_server.exp_recall_limit` | `5` | Experience 召回條數 |
| `bot.ov_server.exp_recall_max_chars` | `10000` | Experience 注入字元預算 |
| `bot.ov_server.exp_write_tools` | `write_file`,`edit_file` | 寫操作前觸發經驗召回的工具 |

## Workspace 與 Agent 定製

Workspace 是 VikingBot 的本地工作目錄。它儲存 Agent 啟動指令、Skill、Heartbeat 任務以及檔案和 Shell 工具操作的內容；OpenViking Workspace 則通過 `openviking_*` 工具訪問 Resource、Memory 和 Skill，兩者不是同一個目錄。

### 找到當前 Workspace

Workspace 根目錄由 `storage.workspace` 決定：

```text
<storage.workspace>/bot/workspace
```

未配置 `storage.workspace` 時，預設為 `~/.openviking/data/bot/workspace`。可以執行以下命令確認：

```bash
vikingbot status
```

使用託管 OpenSandbox（`backend=opensandbox`、`managed=true`）時，活動 Workspace 根目錄
改為 `<storage.workspace>/bot/runtime/opensandbox/workspaces`，並掛載進容器，詳見下方沙箱配置。

Agent 實際使用的活動目錄還取決於 `bot.sandbox.mode`：

| 模式 | 活動 Workspace |
|------|----------------|
| `shared`（預設） | `<workspace>/shared` |
| `per-session` | `<workspace>/<session-key>` |
| `per-channel` | `<workspace>/<channel-key>` |

例如，預設配置下應修改 `~/.openviking/data/bot/workspace/shared/SOUL.md`。

### 定製 Agent

首次使用某個活動 Workspace 時，VikingBot 會從內建 `bot/workspace` 模板複製初始檔案。常用定製入口如下：

| 檔案或目錄 | 作用 | 載入方式 |
|------------|------|----------|
| `SOUL.md` | 人格、價值觀和表達風格 | 每輪自動加入系統提示 |
| `AGENTS.md` | 全域工作規則和任務約束；可按需建立 | 每輪自動加入系統提示 |
| `IDENTITY.md` | Agent 名稱、角色和身份背景；可按需建立 | 每輪自動加入系統提示 |
| `TOOLS.md` | 工具選擇、呼叫邊界和安全規則 | 每輪自動加入系統提示 |
| `skills/<name>/SKILL.md` | 某類任務的操作流程和配套資源 | 先注入摘要，需要時漸進載入全文 |
| `HEARTBEAT.md` | 週期檢查的任務清單 | 僅由 Heartbeat 讀取 |

例如，可以修改活動 Workspace 中的 `SOUL.md`：

```markdown
# Soul

你是團隊的研發助手。

- 預設使用中文回答
- 先給結論，再補充必要細節
- 修改程式碼前先確認現狀，修改後執行相關驗證
- 不確定時明確說明假設，不編造結果
```

儲存後通常會在下一輪 Agent 對話中生效，無需重啟 Gateway。`SOUL.md` 只能改變提示行為，不能繞過 Channel 許可權、工具可見性或 Sandbox 限制。

> [!NOTE]
> 請修改活動 Workspace 中的檔案。倉庫或安裝包中的 `bot/workspace` 是初始化模板，不會覆蓋已經存在的 Workspace。不要在啟動檔案中儲存 API Key 等秘密。

完整載入順序、檔案職責和定製邊界見 [Agent 能力體系](docs/zh/concepts/02-agent-capabilities.md#workspace-與-agent-定製)。

## Agent 工具

### 內建工具

| 類別 | 工具 |
|------|------|
| 檔案與命令 | `read_file`、`write_file`、`edit_file`、`list_dir`、`exec` |
| Web | `web_search`、`web_fetch` |
| OpenViking | `openviking_list`、`openviking_search`、`openviking_grep`、`openviking_glob`、`openviking_multi_read`、`openviking_add_resource`、`openviking_memory_commit` |
| 其他 | `message`、`generate_image`、`cron`、`spawn` |

`readonly` 模式不會註冊 `openviking_add_resource`。渠道設定 `ov_tools_enable: false` 時，該渠道不顯示 OpenViking 工具，也不注入 Profile、Memory 和 Experience。

### 定時任務配置

定時任務預設關閉。在 `ov.conf` 中設定 `bot.tools.cron.enabled` 為 `true`，即可開啟：

```json
{
  "bot": {
    "tools": {
      "cron": {
        "enabled": true
      }
    }
  }
}
```

此開關同時控制 `cron` 工具註冊和定時排程服務，適用於 Gateway 和本地 Chat。設為 `false` 或省略此配置時，不註冊 `cron` 工具，也不啟動排程服務；已有任務保留在磁碟上，但不會自動執行。

修改後需要重啟 Bot。已有部署升級後，如需繼續自動執行定時任務，必須顯式設定 `enabled: true`。子 Agent 和 `--eval` 模式仍不提供定時任務能力。

`vikingbot cron` 命令仍可手動管理任務，此開關不限制 CLI 管理操作。

### MCP 工具

第三方 MCP Server 配置在 `bot.tools.mcp_servers`：

```json
{
  "bot": {
    "tools": {
      "mcp_servers": {
        "filesystem": {
          "type": "stdio",
          "command": "npx",
          "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
          "tool_timeout": 30,
          "enabled_tools": ["*"]
        },
        "remote": {
          "type": "streamableHttp",
          "url": "https://example.com/mcp",
          "headers": {"Authorization": "Bearer $MCP_TOKEN"},
          "enabled_tools": ["search"]
        }
      }
    }
  }
}
```

支援 `stdio`、`sse` 和 `streamableHttp`。工具註冊名為 `mcp_<server>_<tool>`；單個 MCP 連線失敗不會阻斷其他 Agent 能力。

## 沙箱

| 後端 | 說明 |
|------|------|
| `direct` | 預設，直接在 Bot 宿主機執行，不是強隔離環境 |
| `srt` | 支援網路和檔案允許/拒絕策略 |
| `opensandbox` | 連線 OpenSandbox Server |
| `aiosandbox` | 連線 AIO Sandbox 服務 |

工作區模式支援：

- `shared`：所有會話共享工作區；
- `per-session`：每個 Session 獨立；
- `per-channel`：同一渠道例項共享。

DirectBackend 預設 `restrict_to_workspace: false`。對不可信使用者開放 Gateway 時，應選擇隔離後端，並設定渠道白名單和網路/檔案策略。

```json
{
  "bot": {
    "sandbox": {
      "backend": "srt",
      "mode": "per-session"
    }
  }
}
```

### Gateway 自動管理 Docker 沙箱

預設仍為 `direct`，不會檢查 Docker 或啟動 OpenSandbox。若希望命令和檔案工具在獨立
Linux 容器中執行，先安裝並啟動 Docker（macOS 使用 Docker Desktop；Windows 推薦
Docker Desktop + WSL2，並在 WSL2 內執行 Bot），然後在實際使用的 `ov.conf` 中配置：

```json
{
  "bot": {
    "sandbox": {
      "backend": "opensandbox",
      "mode": "per-session"
    }
  }
}
```

`vikingbot gateway --config /path/to/ov.conf` 和 OpenViking `--with-bot` 共用啟動流程：
檢查 SDK、Server、Docker 服務及 Linux 容器模式 → 準備映象 → 生成服務配置和管理金鑰 →
啟動 OpenSandbox Server → 驗證命令執行和檔案往返 → Gateway 就緒。初始化失敗會退出，
不會回退到 `direct`。`--with-bot` 等待真實就緒，不再把子程序存活當作啟動成功。

使用者不需要維護 `~/.sandbox.toml`。生成檔案及日誌位於
`{storage.workspace}/bot/runtime/opensandbox/gateway-*/`；生成的配置檔案在正常退出時刪除，
日誌保留。管理服務預設只監聽本機 `127.0.0.1:18792`，金鑰不傳入工作負載容器。
Bot 託管的服務程序還會將 Docker 釋出的沙箱埠限制為 `127.0.0.1`；這是對
OpenSandbox Server 0.1.6 預設繫結所有網絡卡的適配，不會修改外部 Server。

可選引數位於 `bot.sandbox.backends.opensandbox`：

| 引數 | 預設值 | 說明 |
|------|--------|------|
| `managed` | `true` | Bot 啟停本機 OpenSandbox Server；設為 `false` 連線已有服務 |
| `server_url` | `http://localhost:18792` | 託管模式只允許本機 HTTP 地址，可調整埠 |
| `api_key` | 空 | 託管模式自動生成；外部服務填寫其管理金鑰 |
| `startup_timeout` | `600` | 初始化總超時（秒），首次拉取映象較慢時可調大 |
| `use_server_proxy` | `true` | 經 Server 訪問沙箱，避免客戶端必須直連容器 IP |
| `default_image` | `opensandbox/code-interpreter:v1.0.1` | 執行映象，需包含 shell、Python 3 |
| `execd_image` | `opensandbox/execd:v1.0.6` | 執行服務映象 |
| `egress_image` | `opensandbox/egress:v1.0.1` | 出站網路策略元件映象 |
| `pids_limit` | `256` | 託管 Docker 沙箱的程序數限制 |
| `runtime.cpu` / `runtime.memory` | `500m` / `1Gi` | 每個執行沙箱的資源限制 |
| `runtime.timeout` | `300` | 沙箱生命週期（秒），再次使用時續期 |
| `network.allowed_domains` | `[]` | 預設拒絕出站，按需允許依賴下載或業務域名 |
| `network.denied_domains` | `[]` | 在允許規則之前匹配的拒絕域名 |

託管 Docker 使用 bridge 網路、裁剪 capabilities、禁止新增特權。僅將專用工作目錄
讀寫掛載到容器 `/workspace`，不會掛載 Bot 配置、服務金鑰、Docker socket 或其他會話目錄：

執行容器和其中的 execd 服務使用專用工作目錄所有者的數值 UID/GID，`HOME` 指向
`/workspace`。因此在 Linux 上也能讀寫普通使用者擁有的 `0755` 目錄和 `0644` 檔案，
無需擴大目錄許可權或恢復 `CAP_DAC_OVERRIDE`；網路元件和映象快取容器不使用這個使用者覆蓋。

```text
{storage.workspace}/bot/runtime/opensandbox/
├── gateway-*/                  # 服務配置和日誌，不掛載
└── workspaces/
    ├── shared/                 # shared 模式 → 容器 /workspace
    ├── <session/channel-key>/  # 按會話或渠道隔離 → 各容器 /workspace
    └── compile/<task-id>/      # Compile 獨立任務工作區
```

Mac 上可在 Finder 直接檢視這些工作檔案，宿主機和容器的修改立即作用於同一目錄。
聊天沙箱銷燬或過期後文件保留，重建時複用；首次建立目錄時初始化引導檔案和本地 Skill，
之後不會覆蓋使用者修改。Compile 仍按原有任務生命週期清理任務目錄。
舊的 `bot/workspace/shared` 不自動遷移；啟用後應在上面的新工作目錄編輯引導檔案。

`shared` 在啟動時建立並保留一個共享沙箱；`per-session` / `per-channel` 在啟動時使用
臨時探測沙箱，後續按需建立例項。Compile 單獨按任務建立和回收。Gateway 退出時先取消
任務並清理沙箱，再停止自己啟動的 Server。SIGKILL 或斷電無法保證即時清理；託管 Server
停止期間不會執行到期清理，重啟後需確認遺留容器已回收。

`managed=false` 使用檔案 API，不掛載 Bot 本機目錄、不檢查本機 Docker、不啟停外部服務；外部服務需自行配置 Docker、egress
元件和許可權策略。當前自動託管範圍是 Gateway / `--with-bot`，獨立 `vikingbot chat` 使用
OpenSandbox 時需要提前啟動服務並配置地址。

可顯式執行 Docker 許可權迴歸測試（需要 Docker 和上述映象）。該測試使用 Linux 原生卷，
覆蓋 UID 1000 的 `0755` 目錄、`0644` 檔案、命令與檔案 API 寫入及容器重建，避免
Docker Desktop 的宿主機檔案共享許可權轉換掩蓋 Linux 許可權問題：

```bash
VIKINGBOT_TEST_DOCKER=1 PYTHONPATH=bot python -m pytest -q -o addopts='' bot/tests/test_opensandbox_docker_permissions.py
```

## HTTP API

Gateway 的 Bot API 字首為 `/bot/v1`：

| 方法 | 路徑 | 用途 |
|------|------|------|
| POST | `/bot/v1/chat` | 同步對話 |
| POST | `/bot/v1/chat/stream` | SSE 流式對話 |
| POST | `/bot/v1/feedback` | 提交回復反饋 |
| GET/POST | `/bot/v1/sessions` | 查詢或建立 API Session |
| GET/DELETE | `/bot/v1/sessions/{id}` | 查詢或刪除 Session |

配置 OpenViking upstream 後，`/api/v1/*` 會代理到 OpenViking Server。

## 運維命令

| 命令 | 用途 |
|------|------|
| `vikingbot status` | 檢視模型、配置和執行狀態 |
| `vikingbot channels status` | 檢視渠道狀態 |
| `vikingbot channels login` | 登入 WhatsApp bridge |
| `vikingbot cron list` | 檢視定時任務 |
| `vikingbot cron add` | 新增定時任務 |
| `vikingbot cron run` | 手動執行任務 |
| `vikingbot feedback-stats` | 彙總回覆反饋與結果指標 |

啟用 Langfuse：

```json
{
  "bot": {
    "langfuse": {
      "enabled": true,
      "secret_key": "<langfuse-secret-key>",
      "public_key": "<langfuse-public-key>",
      "base_url": "http://localhost:3000"
    }
  }
}
```

倉庫內提供了 `deploy/docker/deploy_langfuse.sh`，可用於本地部署。

## 安全提示

- 不要把模型 API Key、OpenViking API Key 或 Gateway Token 提交到倉庫。
- 非 localhost Gateway 必須配置高強度隨機 Token，並在網路層啟用 HTTPS。
- `X-Gateway-Token` 只保護 Gateway，不能代替 OpenViking 使用者身份。
- `allow_from: []` 表示不限制傳送者；對外服務建議配置明確白名單。
- `direct` 後端會以 Bot 程序使用者許可權執行檔案和 Shell 操作，不適合不可信呼叫者。
- `openviking_connection` 只能來自可信 Server 代理或本地可信鏈路，不應接受公網請求體自行宣告。

## 更多文件

- [VikingBot 架構](docs/zh/concepts/01-architecture.md)
- [Agent 能力體系](docs/zh/concepts/02-agent-capabilities.md)
- [渠道、Gateway 與執行管理](docs/zh/concepts/03-channels-and-gateway.md)
- [VikingBot 與 OpenViking 整合](docs/zh/concepts/04-openviking-integration.md)
- [渠道配置](docs/zh/concepts/05-channel.md)
- [Skills：本地與遠端技能](docs/zh/concepts/06-skills.md)
