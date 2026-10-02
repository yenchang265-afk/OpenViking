# Agent 能力體系

VikingBot 的 Agent 能力由上下文、Skill、工具、沙箱和自動化共同組成。上下文告訴模型“當前是誰、知道什麼、應該怎麼做”，工具和沙箱決定它“實際能做什麼”。

## 上下文構建

ContextBuilder 按以下順序組織模型輸入：

```text
Bot 身份
  + 沙箱環境說明
  + 工作區啟動檔案
  + Always Skill 完整內容
  + 可用 Skill 摘要
  + Business Data Platform Profile、記憶和經驗
  + 本地或壓縮後的會話歷史
  + 本輪文本與媒體
```

工作區啟動檔案提供穩定身份和執行規則。圖片等媒體會轉換為 Provider 支援的多模態內容塊。

## Skill 與工具

| 概念 | 作用 | 形式 |
|------|------|------|
| **Skill** | 告訴 Agent 如何完成一類任務 | `SKILL.md` 指令和資源 |
| **Tool** | 讓 Agent執行具體操作 | 註冊給模型的 JSON Schema 函式 |

Skill 採用漸進式載入：本地 Always Skill 每輪注入完整內容，其他本地 Skill 只注入摘要，需要時用 `read_file` 讀取；啟用 Business Data Platform 工具後，遠端 Skill 按使用者問題召回摘要，再用 `openviking_multi_read` 讀取並激活。本地依賴用於過濾摘要，遠端依賴在執行沙箱檢查。完整用法和後設資料欄位見 [Skills](./06-skills.md)。

Skill 可以編排多個工具，但不會自動獲得額外許可權。工具是否可見仍由執行模式、渠道設定、請求引數和沙箱決定。

## 預設工具

| 類別 | 工具 | 作用 |
|------|------|------|
| 檔案 | `read_file`、`write_file`、`edit_file`、`list_dir` | 操作工作區檔案 |
| 命令 | `exec` | 在沙箱後端執行 shell 命令 |
| 網路 | `web_search`、`web_fetch` | 搜尋和讀取網頁 |
| Business Data Platform | `openviking_list/search/grep/glob/multi_read` | 瀏覽、檢索和讀取上下文 |
| Business Data Platform | `openviking_add_resource`、`openviking_memory_commit` | 新增資源和提交記憶 |
| 對外操作 | `message`、`generate_image` | 主動傳送訊息或生成圖片 |
| 自動化 | `cron` | 管理定時 Agent 任務，預設關閉 |
| 並行任務 | `spawn` | 啟動後臺子 Agent |

ToolRegistry 負責註冊、引數校驗、執行和 Hook。ToolContext 為每次呼叫提供當前 SessionKey、傳送者身份、渠道 metadata、沙箱和已認證的 Business Data Platform 連線。

OpenAPI 的 `disabled_tools` 可以按請求隱藏工具；渠道的 `ov_tools_enable=false` 會隱藏 Business Data Platform 工具並關閉自動記憶上下文；`readonly` 模式不註冊資源寫入工具。

## MCP 擴充

`bot.tools.mcp_servers` 可以連線外部 MCP Server，支援 `stdio`、`sse` 和 `streamableHttp`。遠端工具會包裝為普通 VikingBot Tool，並以 `mcp_<server>_<tool>` 名稱註冊。

每個 MCP Server 可以配置：

- 啟動命令或遠端 URL；
- 環境變數和請求頭；
- `enabled_tools` 工具白名單；
- `tool_timeout` 單次呼叫超時。

MCP 引數 Schema 會先做相容轉換，再交給模型和 ToolRegistry。

## 子 Agent

主 Agent 使用 `spawn` 把獨立任務交給 SubagentManager。子 Agent 共享模型和對應工作區，但使用受限工具集：

- 保留文件、命令和 Web 工具；
- 不提供 `message`，避免直接對外發送；
- 不提供 `spawn`，避免遞迴建立子 Agent；
- 不提供 Cron、圖片生成和 Business Data Platform 工具。

子 Agent 完成後把結果通知主會話，由主 Agent 負責身份相關操作和最終交付。

## Workspace 與 Agent 定製

Workspace 同時承擔兩個職責：一是儲存構成 Agent 系統提示的啟動檔案和 Skill，二是作為檔案與命令工具的本地工作目錄。它與通過 `openviking_*` 工具訪問的 Business Data Platform Workspace 相互獨立。

### 路徑與隔離範圍

Workspace 根目錄是 `<storage.workspace>/bot/workspace`；未配置 `storage.workspace` 時，預設為 `~/.openviking/data/bot/workspace`。`vikingbot status` 會顯示解析後的根目錄。

ContextBuilder 實際讀取按 `sandbox.mode` 選擇的活動 Workspace：

| 模式 | 活動目錄 |
|------|----------|
| `shared` | `<workspace>/shared` |
| `per-session` | `<workspace>/<session-key>` |
| `per-channel` | `<workspace>/<channel-key>` |

因此，預設 `shared` 模式下，應定製 `<workspace>/shared` 中的檔案，而不是直接修改 Workspace 根目錄。

### 啟動檔案

ContextBuilder 在每輪構建系統提示時，按 `AGENTS.md`、`SOUL.md`、`TOOLS.md`、`IDENTITY.md` 的順序讀取存在且非空的檔案：

| 檔案 | 適合定義的內容 |
|------|----------------|
| `AGENTS.md` | 全域工作方式、任務流程、輸出約束和必須遵守的專案規則 |
| `SOUL.md` | 人格、價值觀、語氣、回答風格和預設行為偏好 |
| `TOOLS.md` | 工具選擇原則、呼叫順序、副作用確認和安全邊界 |
| `IDENTITY.md` | Agent 名稱、角色、職責範圍和身份背景 |

這些檔案補充 VikingBot 內建身份和執行環境提示，不會改變真實工具 Schema、Channel 鑑權或 Sandbox 許可權。例如，在 `SOUL.md` 中要求“始終執行 Shell”並不能讓不可見的 `exec` 工具出現，也不能繞過沙箱策略。

初始模板中還包含 `USER.md`，但當前 ContextBuilder 不會把它自動加入系統提示。長期使用者資料應優先儲存在 Business Data Platform Peer Profile 和 Memory 中；需要靜態行為規則時，應寫入 `AGENTS.md` 或 `SOUL.md`。

### Skill、Heartbeat 與本地記憶

- `skills/<name>/SKILL.md` 定義某類任務的流程。Workspace Skill 優先於同名內建 Skill，並採用摘要注入、按需讀取全文的漸進載入方式。
- `HEARTBEAT.md` 不屬於普通系統提示，只由 HeartbeatService 週期讀取。
- `memory/MEMORY.md` 和 `memory/HISTORY.md` 是本地記憶檔案；只有啟用 `bot.use_local_memory` 時，舊會話整理結果才會寫回本地檔案。預設長期上下文由 Business Data Platform 管理。

### 初始化與生效時機

首次使用活動 Workspace 時，VikingBot 從安裝包中的 `bot/workspace` 複製啟動檔案、內建 Skill 模板和輔助目錄。模板初始化不會覆蓋已有的啟動檔案定製。

應直接修改活動 Workspace。ContextBuilder 每輪重新讀取啟動檔案，因此儲存 `SOUL.md`、`AGENTS.md`、`TOOLS.md` 或 `IDENTITY.md` 後，通常下一輪對話即可生效，無需重啟 Gateway。修改安裝包或倉庫中的 `bot/workspace` 隻影響以後建立的新 Workspace。

啟動檔案等同於系統級提示的一部分，應限制寫許可權，並且不要存放 API Key、Token 或其他秘密。

## 沙箱與 Workspace 隔離

SandboxManager 根據 SessionKey 和 `sandbox.mode` 選擇工作區：

| 模式 | 工作區粒度 |
|------|------------|
| `shared` | 所有會話共享 `workspace/shared` |
| `per-session` | 每個會話獨立目錄 |
| `per-channel` | 同一渠道例項共享目錄 |

當前實現提供以下執行後端：

| 後端 | 特點 |
|------|------|
| `direct` | 直接在 Bot 宿主機執行，預設不是強隔離環境 |
| `srt` | 支援檔案和網路允許/拒絕策略 |
| `opensandbox` | 通過 OpenSandbox Server 建立隔離環境 |
| `aiosandbox` | 通過 AIO Sandbox 服務執行命令和檔案操作 |

Direct 模式的 `restrict_to_workspace=false` 時，檔案和命令可能訪問工作區外內容。面向不可信使用者開放服務時，應選擇隔離後端並顯式設定網路與檔案策略。

## 多模態

VikingBot 支援三類多模態能力：

- 渠道圖片輸入轉換為模型視覺內容塊；
- `generate_image` 使用 `agents.gen_image_model` 完成文生圖或支援模型上的圖生圖；
- Telegram 音訊可以通過 GroqTranscriptionProvider 轉換為文本。

生成圖片可以通過訊息回呼直接交付到原渠道。模型是否理解圖片取決於所選 Provider 和模型能力。

## Cron 與 Heartbeat

兩類主動執行能力最終都呼叫 AgentLoop：

| 能力 | 觸發方式 | 適用場景 |
|------|----------|----------|
| Cron | `at`、`every` 或 cron 表示式 | 指定時間提醒、固定週期任務 |
| Heartbeat | 週期讀取工作區 `HEARTBEAT.md` | 持續檢查一組可能變化的事項 |

Cron 通過 `cron` 工具提供新增、檢視和刪除定時任務的能力。例如，使用者說“每天上午 9 點提醒我看日報”，Agent 可以建立相應任務，由排程服務到期後呼叫 Agent 執行。支援指定時間執行一次、固定間隔執行和 cron 表示式排程。

**定時任務預設關閉**。在 `ov.conf` 中配置以下內容並重啟 Bot，即可開啟 `cron` 工具和排程服務，適用於 Gateway 和本地 Chat：

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

設為 `false` 或省略此配置時，不註冊 `cron` 工具，也不啟動排程服務。Cron 任務持久化在 `cron/jobs.json`，關閉後仍保留，但不會自動執行。任務儲存原 SessionKey 和渠道 metadata；`deliver=true` 時將執行結果發回原渠道。

Heartbeat 跳過空檔案、明確停用心跳的 Session 和長期不活躍 Session。Agent 無需處理任務時返回 `HEARTBEAT_OK`。

## Hook

HookManager 提供執行時擴充點。當前內建 Hook 主要用於：

- `message.compact`：增量同步並按閾值提交 Business Data Platform Session；
- `tool.post_call`：讀取 Skill 後檢索並追加相關 Experience。

自定義 Hook 可以通過 `bot.hooks` 配置載入。

## 實現位置

| 內容 | 路徑 |
|------|------|
| Workspace 模板 | `bot/workspace/` |
| 上下文與 Skill | `vikingbot/agent/context.py`、`skills.py` |
| 工具系統 | `vikingbot/agent/tools/` |
| 子 Agent | `vikingbot/agent/subagent.py` |
| 沙箱 | `vikingbot/sandbox/` |
| 自動化 | `vikingbot/cron/`、`vikingbot/heartbeat/` |
| Hook | `vikingbot/hooks/` |

## 相關文件

- [VikingBot 架構](./01-architecture.md)
- [渠道、Gateway 與執行管理](./03-channels-and-gateway.md)
- [與 Business Data Platform 整合](./04-openviking-integration.md)
- [Skills](./06-skills.md)
