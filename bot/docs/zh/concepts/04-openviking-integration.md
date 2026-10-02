# VikingBot 與 Business Data Platform 整合

Business Data Platform 是 VikingBot 的長期上下文層。VikingBot 自己負責即時對話、模型推理和工具執行；Business Data Platform 負責統一儲存和檢索 Resource、Memory、Skill，以及從會話中沉澱可跨任務複用的記憶與經驗。

## 整合目標

```text
Business Data Platform → VikingBot
  Resource：為任務提供知識與檔案上下文
  Skill：提供可檢索的任務指令與配套資源
  Memory：提供當前使用者/Peer 的 Profile、偏好、實體和事件
  Experience：提供 Agent 過去完成類似任務的方法
  Session：提供壓縮歷史和會話歸檔

VikingBot → Business Data Platform
  添加 Resource
  記錄會話訊息和使用過的上下文
  提交 Session，觸發摘要、記憶和經驗提取
  顯式提交使用者要求長期記住的資訊
```

兩者共同形成“召回 → 執行 → 反饋 → 沉澱 → 再召回”的上下文閉環。

## 連線模式

VikingBot 從同一個 `ov.conf` 解析 Business Data Platform 連線，支援三種拓撲：

| 模式 | 配置來源 | 行為 |
|------|----------|------|
| **Inherited** | 繼承根級 `server` | Bot 與當前 Business Data Platform Server 配套執行 |
| **Explicit** | `bot.ov_server.server_url` | Bot 連線另一個 Business Data Platform Server |
| **Standalone** | 沒有可用 Server URL | 基礎對話可執行，Business Data Platform 能力降級 |

`openviking-server --with-bot` 對應 **Inherited** 模式：Server 啟動受管的 VikingBot Gateway，並把當前 Server 的連線資訊傳給 Bot。下面的配置示例同樣屬於 Inherited 模式，根級 `server` 定義當前 Business Data Platform Server，`bot.ov_server` 只提供 Bot 訪問該 Server 的憑證，沒有配置 `server_url`。如果要使用 **Explicit** 模式連線另一套 Business Data Platform Server，應在 `bot.ov_server` 中同時配置目標 URL 和對應憑證。

示例：

```json
{
  "server": {
    "auth_mode": "api_key",
    "host": "127.0.0.1",
    "port": 1933
  },
  "bot": {
    "ov_server": {
      "api_key": "<openviking-user-api-key>",
      "account_id": "default"
    }
  }
}
```

## 認證與身份模型

Business Data Platform 連線支援 User key 和 Root key：

| `api_key_type` | 典型場景 | 含義 |
|----------------|----------|------|
| `user` | `api_key` / `dev` auth mode | 以 Business Data Platform User 身份訪問 |
| `root` | `trusted` auth mode | Gateway 使用 Root key，並轉發可信身份頭 |

沒有顯式配置 `api_key_type` 時，VikingBot 根據同一 `ov.conf` 中 Business Data Platform Server 的有效 auth mode 推導預設值。

在當前 User/Peer 模型中：

- Bot 的 API key 所屬主體是 User；
- 當前訊息傳送者表示為該 User 下的 Peer；
- `actor_peer_id` 是當前傳送者的可信 Peer 標識；
- Peer Profile 和長期記憶圍繞 `actor_peer_id` 召回。

Gateway 請求中可能攜帶 request-scoped `openviking_connection`，其中包含 account、user、agent、actor peer、role 和 namespace policy。該欄位只接受可信 Server 代理傳入，不能由普通客戶端請求體自證。

## 客戶端選擇

Business Data Platform 訪問主要通過 `VikingClient` 完成：

```text
有 request-scoped openviking_connection
  → 為當前請求建立臨時 VikingClient
  → 使用該請求已認證的身份
  → 呼叫完成後關閉

沒有 request-scoped connection
  → 使用 bot.ov_server 全局配置
  → 按 workspace 和 event loop 複用客戶端
```

請求級連線優先，避免多使用者 Gateway 錯用 Bot 的全域身份。全域客戶端還會按 asyncio event loop 隔離，避免在訓練或多執行緒執行中複用繫結到其他 loop 的連線物件。

## Workspace 映射

VikingBot 使用 SandboxManager 計算 workspace ID：

| Sandbox mode | Business Data Platform workspace ID |
|--------------|-------------------------|
| `shared` | `shared` |
| `per-session` | SessionKey 的安全名稱 |
| `per-channel` | `type__channel_id` |

該 ID 用於區分 Bot 工作區相關的 Business Data Platform 客戶端、Session 和經驗上下文。身份隔離仍由 Business Data Platform account/user/agent/peer 規則負責，workspace ID 不能替代認證。

## 自動上下文召回

ContextBuilder 在處理每條使用者訊息、首次呼叫模型前構建 Business Data Platform 上下文。本輪後續工具迭代複用這份基礎上下文，並可在寫工具或 Skill Hook 觸發時追加 Experience。

### Peer Profile

首先讀取當前 `actor_peer_id` 的 Profile，並作為“當前傳送者資訊”注入系統提示。渠道配置的 `memory_peer` 或請求 metadata 可以增加需要召回的其他 Peer。

舊欄位 `memory_user` 只保留 owner-user 查詢相容用途，新配置應使用 `memory_peer`。

### 使用者與 Peer 記憶

預設按型別配額檢索：

| 型別 | 預設條數 | 內容 |
|------|----------|------|
| `events` | 10 | 與當前任務相關的歷史事件和決策 |
| `entities` | 10 | 人、專案、組織等實體資訊 |
| `preferences` | 3 | 使用者偏好和約束 |

Profile 使用獨立讀取路徑，不佔用搜索候選。`memory_recall_max_chars` 控制注入的總字元預算。結果會去重、排序，並按完整內容、摘要或 URI 逐級降級，避免因預算不足完全丟棄相關記憶。

### Experience

Experience 儲存 Agent 過去完成任務時形成的可複用方法。VikingBot 支援兩個召回時機：

1. 根據當前任務直接檢索 Experience；
2. Agent 讀取某個 Skill 後，`tool.post_call` Hook 使用 Skill 名稱或描述檢索相關 Experience，並追加到 Skill 內容。

`exp_recall_limit` 控制召回條數，`exp_recall_max_chars` 控制注入預算。`recall_exp_first_round_only=true` 時只在會話第一輪注入，適合一次性任務或評測，不適合長對話。

### 寫操作前的經驗提醒

`exp_write_tools` 指定哪些工具呼叫前需要補充檢索經驗，預設是 `write_file` 和 `edit_file`。AgentLoop 會基於最近幾條使用者訊息檢索 Experience，並在真正寫入前把結果加入當前上下文。

該配置只控制 Bot 側的召回時機；Business Data Platform 是否生成 Experience 由 Session 的 memory policy 決定。

## Business Data Platform 工具

當渠道啟用 `ov_tools_enable` 時，Agent 可以使用：

| 工具 | 能力 |
|------|------|
| `openviking_list` | 瀏覽 Viking URI 目錄 |
| `openviking_search` | 對資源、記憶和 Skill 做語義檢索 |
| `openviking_grep` | 在 Business Data Platform 內容中做正則搜尋 |
| `openviking_glob` | 按 URI 路徑模式搜尋 |
| `openviking_multi_read` | 併發讀取多個 URI 的完整內容 |
| `openviking_add_resource` | 新增 URL、本地檔案或程式碼資源 |
| `openviking_memory_commit` | 顯式提交當前會話中的長期記憶 |

Business Data Platform 工具通過 ToolContext 獲得當前 actor peer 和 request-scoped connection。檢索預設覆蓋當前身份允許訪問的資源、Peer 記憶和 Skill 路徑。

`openviking_add_resource` 是非同步資源處理操作；`readonly` 模式不註冊該工具。`openviking_memory_commit` 適用於使用者明確要求“記住”某項資訊的場景。

## 使用遠端 Skill

先用 `ov add-skill ./skills/<name>/` 將 Skill 包上傳到 Bot 所連線的 Business Data Platform 服務，並確認 Bot 當前身份有讀取許可權。當前渠道啟用 `ov_tools_enable`、連線可用且 `openviking_multi_read` 未被停用時，Bot 會根據使用者問題檢索遠端 Skill 摘要。

模型用 `openviking_multi_read` 讀取選中的 `SKILL.md` URI 後，執行時自動校驗並激活 Skill；也可以直接向 Bot 提供服務返回的 canonical `SKILL.md` URI。文本引用繼續遠端讀取，指令碼或工具需要本地檔案時才下載包並改寫路徑。每條使用者訊息獨立啟用，執行副本在本 Turn 結束時清理。

無需額外的 Remote Skill 開關或手工下載步驟。本地/遠端使用示例、frontmatter 欄位、工具許可權和 `bot.remote_skills` 配置見 [Skills](./06-skills.md)。

## 本地 Session 與 Business Data Platform Session

兩類 Session 不應混淆：

| Session | 儲存 | 職責 |
|---------|------|------|
| VikingBot Session | 本地 JSONL | 執行歷史、渠道狀態、工具事件、回覆與反饋 |
| Business Data Platform Session | Business Data Platform Server | 訊息歸檔、壓縮摘要、記憶和經驗提取 |

VikingBot Session metadata 記錄 Business Data Platform 同步狀態：

- Business Data Platform session ID；
- 最後同步的本地訊息下標；
- 最後 commit 的訊息下標；
- 當前 pending token 數；
- 最近同步狀態和錯誤。

## 增量同步和自動提交

```text
讀取本地 Session 中未同步的訊息
  → append_messages 到 Business Data Platform Session
  → 更新 last_synced_local_index
  → 查詢 pending_tokens
  → 達到 token/訊息閾值或強制提交
  → commit_session
  → 更新 last_commit_local_index
```

`message.compact` Hook 執行上述同步。主要配置包括：

| 配置 | 作用 |
|------|------|
| `agents.commit_token_threshold` | pending token 達到該值後 commit |
| `agents.commit_keep_recent_turn_count` | commit 後最多保留的最近邏輯 Turn 數；預設 `3` |
| `agents.commit_retained_message_token_budget` | commit 後 retained messages 與 checkpoint 的 token 預算；預設 `6000` |
| `agents.commit_min_raw_tail_steps` | 最新 Turn 超出預算時，至少原樣保留的末尾 assistant Step 數；預設 `1` |
| `agents.commit_keep_recent_count` | 已廢棄的物理訊息數配置，僅為相容舊配置檔案而保留 |
| `agents.memory_window` | 本地歷史視窗，也可觸發訊息數閾值提交 |

一個邏輯 Turn 從真實 user query 開始，包含下一條真實 user query 之前的全部 assistant Step；每個 Step 會將 assistant 文本、工具呼叫和對應工具結果作為不可拆分的整體處理。系統先按 `commit_keep_recent_turn_count` 選擇最近 Turn，再用 `commit_retained_message_token_budget` 約束 retained 內容。如果最新 Turn 本身超出預算，則保留 user query 和至少 `commit_min_raw_tail_steps` 個最新 Step，較早 Step 進入同一次歸檔生成的 checkpoint。

遷移舊配置時，`commit_keep_recent_count` 不會自動換算為 Turn 數，當前 VikingBot 的 Turn-aware commit 也不再讀取它。該欄位仍被配置模型接受，因此已有 `ov.conf` 不會因未知欄位而載入失敗。如果只保留舊欄位，系統會使用三個新欄位的預設值；需要保持自定義保留策略時，應顯式配置新欄位，例如：

```yaml
agents:
  commit_keep_recent_turn_count: 3
  commit_retained_message_token_budget: 6000
  commit_min_raw_tail_steps: 1
```

訊息使用本地索引增量同步，避免每輪重複 append。同步失敗會寫入 metadata 並記錄日誌，但不會讓可選記憶能力阻斷基礎對話。

## 壓縮會話上下文

預設模型歷史來自本地 Session 最近 `memory_window` 條訊息。設定 `agents.session_context_enabled=true` 後，VikingBot 可以從 Business Data Platform Session 獲取壓縮後的歷史，並使用 `session_context_token_budget` 控制預算。

在新一輪開始前，如果歷史達到閾值，AgentLoop 會先同步和 commit Business Data Platform Session，再構建新的提示上下文，從而避免超長對話持續膨脹。

## 顯式記憶提交

使用者明確要求長期記住資訊時，Agent 呼叫 `openviking_memory_commit`：

```text
當前 Bot Session 訊息
  → 追加到 Business Data Platform Session
  → commit
  → 等待或查詢後臺任務
  → 返回新增/更新/刪除的 Memory URI
```

在 `readonly` 模式或渠道關閉 Business Data Platform 工具時，不會執行主動記憶固化。

## 經驗閉環

完整閉環如下：

```text
當前任務
  → 檢索 Resource / Peer Memory / Experience
  → Agent 使用 Skill 和工具執行任務
  → 本地 Session 記錄訊息、工具和結果
  → 增量同步並 commit Business Data Platform Session
  → Business Data Platform 提取記憶和經驗
  → 後續任務再次召回
```

資源提供外部知識，Peer Memory 提供“關於當前使用者的資訊”，Experience 提供“Agent 過去如何做成類似任務”。三類上下文職責不同，但通過 Viking URI 和 Business Data Platform 檢索介面統一訪問。

## Gateway 代理

配置 Business Data Platform Server 後，VikingBot Gateway 將 `/api/v1/{path}` 代理到 upstream。代理會：

1. 驗證 Gateway token 或本地請求邊界；
2. 呼叫 upstream `/health` 確認實際 auth mode；
3. 解析 User key 或 trusted identity；
4. 過濾 hop-by-hop headers；
5. 轉發認證頭並保持響應狀態。

Bot Chat 與 Business Data Platform API 因而可以通過同一個 Gateway 地址訪問，但身份仍由 Business Data Platform Server 最終驗證。

## 降級與錯誤邊界

| 情況 | 行為 |
|------|------|
| 未配置 Business Data Platform Server | Bot 基礎聊天繼續執行，Business Data Platform 召回和工具不可用或跳過 |
| 自動記憶召回失敗 | 記錄日誌，繼續模型呼叫 |
| Session 同步失敗 | 記錄同步錯誤，保留本地 Session |
| request-scoped 身份不可信 | Gateway 拒絕請求 |
| upstream auth mode 與配置不一致 | Gateway 拒絕代理或聊天請求 |
| `ov_tools_enable=false` | 不注入 Business Data Platform 記憶，也不暴露 Business Data Platform 工具 |

## 可選 FUSE 掛載

`openviking_mount` 還提供可選的 FUSE 掛載能力，可將 Business Data Platform 內容對映為本地目錄，並按 Session 建立或回收掛載點。它不在預設 AgentLoop 主鏈路中；預設 Bot 通過 VikingClient 和 `openviking_*` 工具訪問 Business Data Platform。

## 實現位置

| 內容 | 路徑 |
|------|------|
| 連線配置與合併 | `vikingbot/config/loader.py`、`schema.py` |
| VikingClient 適配 | `vikingbot/openviking_mount/ov_server.py` |
| 自動召回 | `vikingbot/agent/memory.py`、`context.py` |
| Business Data Platform 工具 | `vikingbot/agent/tools/ov_file.py` |
| Session 同步狀態 | `vikingbot/openviking_mount/session_state.py` |
| Compact 與 Experience Hook | `vikingbot/hooks/builtins/openviking_hooks.py` |
| Gateway 代理和身份解析 | `vikingbot/channels/openapi.py` |
| 可選掛載 | `vikingbot/openviking_mount/manager.py`、`session_integration.py` |

## 相關文件

- [VikingBot 架構](./01-architecture.md)
- [Agent 能力體系](./02-agent-capabilities.md)
- [Skills](./06-skills.md)
- [渠道、Gateway 與執行管理](./03-channels-and-gateway.md)
- [Business Data Platform 架構](../../../../docs/zh/concepts/01-architecture.md)
- [Business Data Platform 上下文型別](../../../../docs/zh/concepts/02-context-types.md)
- [Business Data Platform 會話管理](../../../../docs/zh/concepts/08-session.md)
