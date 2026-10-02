# `ov compile` 技術設計

| 專案 | 資訊 |
| --- | --- |
| 狀態 | 歷史設計，現行方案見下方說明 |
| 目標版本 | v1 |
| 更新日期 | 2026-08-28 |

> 本文保留最初由 VikingBot 直接託管任務的歷史設計。現行方案由 Business Data Platform 託管 TaskRecord、QueueFS、查詢和取消，外部 Server 只負責執行。

## 1. 概述

`ov compile` 使用指定 Skill 整理 Business Data Platform 中的材料，並在目標目錄生成或更新 Wiki 頁面。

命令由 VikingBot 執行。`ov` CLI 通過 Business Data Platform 的 Bot 代理呼叫 VikingBot，VikingBot 執行 AgentLoop，並使用當前使用者身份讀取和寫入 Business Data Platform 資料。

```text
ov compile
  -> Business Data Platform /bot/v1/compile
  -> VikingBot Compile AgentLoop
  -> Business Data Platform content APIs
```

v1 的核心目標：

- 支援一個或多個來源目錄；
- 載入使用者指定的 OV Skill；
- 根據任務描述生成一個或多個 Wiki 頁面；
- 增量更新已有 Wiki；
- 通過非同步任務返回進度和結果。

## 2. 使用者介面

### 2.1 命令格式

```bash
ov compile \
  --from viking://resources/週報 \
  --to viking://resources/團隊知識庫 \
  --instruction "按月整理團隊的成本最佳化進展" \
  --skill viking://agent/skills/monthly_wiki \
  --args '{"model_name":"your-model-endpoint-id"}'
```

| 引數 | 規則 |
| --- | --- |
| `--from` | 必填，可重複，也可使用逗號分隔多個目錄 |
| `--to` | 必填，目標 Wiki 目錄 |
| `--skill` | 必填，Skill 目錄或 `SKILL.md` 的 Viking URI |
| `--instruction` | 可選，本次整理任務的描述 |
| `--args` | 可選，Provider 擴充引數 JSON 物件；`model_name` 可傳模型 Endpoint ID |

引數在 Business Data Platform 使用者身份下 canonicalize 後滿足以下約束：

- `from` 必須是一個或多個可讀目錄；重複項去重，空項報錯；
- `to` 必須是可寫的 resource 或 memory 目錄，不能是 namespace 根、檔案、Skill 目錄或 Business Data Platform 派生目錄；
- `skill` 必須解析為 Skill root，目錄 URI 和其 `SKILL.md` URI 視為同一個 Skill；
- `from`、`to` 和 `skill` 的許可權最終仍由 Business Data Platform Server 校驗，CLI 不根據 URI 文本推斷許可權。

`--instruction` 為空時，VikingBot 使用以下預設任務描述：

```text
Follow the loaded Skill's instructions to transform the provided source materials into the outputs required by the Skill.
```

### 2.2 返回結果

CLI 在任務建立後立即返回：

```text
task_id: cmp_01...
status: accepted
to: viking://resources/團隊知識庫
```

CLI 不等待任務完成。使用者通過 `ov task status <task_id>` 查詢狀態和結果，通過 `ov task cancel <task_id>` 取消任務。

Task 結果中的 `created`、`updated` 和 `unchanged` 只統計 Agent 本次提交的頁面；未被草稿觸達的目標頁面不計入 `unchanged`。`page_count` 等於三者之和，`link_count` 只統計最終正文中實際渲染出的 bundle 內 WikiLink。

## 3. 架構

```text
┌──────────────┐
│ ov CLI       │
└──────┬───────┘
       │ POST /bot/v1/compile
       ▼
┌────────────────────────────┐
│ Business Data Platform Bot Proxy       │
│ auth + identity forwarding │
└──────────────┬─────────────┘
               ▼
┌────────────────────────────┐
│ VikingBot                  │
│                            │
│ Compile Task               │
│   ├─ Skill Loader          │
│   ├─ Context Tools         │
│   ├─ AgentLoop             │
│   ├─ Wiki Renderer         │
│   └─ Business Data Platform Writer     │
└──────────────┬─────────────┘
               │ read / search / batch-write
               ▼
┌────────────────────────────┐
│ Business Data Platform Data APIs       │
└────────────────────────────┘
```

職責劃分：

| 模組 | 職責 |
| --- | --- |
| `crates/ov_cli` | 引數解析、HTTP 呼叫、任務輪詢和結果展示 |
| `openviking/server/routers/bot.py` | 認證請求並代理到 VikingBot |
| `bot/vikingbot/compile` | Compile 任務、Skill、AgentLoop、渲染和寫入編排 |
| Business Data Platform content service | 資料許可權、內容讀寫和索引重新整理 |

Business Data Platform Server 必須啟用 Bot 服務。未啟用時，命令返回與 `ov chat` 一致的 503 錯誤。

### 3.1 現有能力複用

Compile 只增加任務編排和領域規則，基礎能力使用現有實現：

| 步驟 | 複用實現 | Compile 適配 |
| --- | --- | --- |
| CLI | `CliContext`、`HttpClient`、全域認證、`OutputFormat`、`output_success()` | compile request、狀態輪詢和 human formatter |
| Bot proxy | `get_bot_url()`、`_create_bot_proxy_client()`、`_attach_openviking_connection()` | create/status 路由 |
| Gateway 認證 | `OpenAPIChannel` 的 Gateway Token dependency、`OpenVikingConnection` 和 principal scope | compile request model 和 task owner 繫結 |
| URI 與許可權 | `fs/attrs` 返回的 canonical URI、請求邊界 URI 校驗與簡寫展開、`context_type_for_uri()`、VikingFS access check | 使用者上下文中的目錄約束和 target containment |
| Skill | Business Data Platform Skills API、`SkillLoader.parse()`、VikingBot `SkillsLoader`、`SandboxManager` | OV bundle 快照和 task-local materialization |
| Agent | `AgentLoop._run_agent_loop()`、`ToolRegistry`、`register_default_tools()` | structured wrapper、scope guard 和 `submit_wiki_bundle` |
| 內容讀取 | `openviking_list/search/grep/glob/multi_read` | 限定允許的 URI roots；不增加同義讀取工具 |
| Link 與 metadata | `WikiLink`、`StoredLink`、`LinkRenderer`；Memory 目標額外複用 `MemoryFileUtils`、`next_memory_version()` 和 resource refs helper | OKF path、citation 和嚴格校驗 |
| 寫入與重新整理 | `ContentWriteCoordinator` 的校驗/refresh helper、`LockManager`、`VikingFS.write_file(..., lock_handle=...)`、`RequestWaitTracker` | batch mode 和多檔案編排 |

新增能力保持在以下邊界內：

- Bot 側 Compile request/task/result 和最小 task store；
- `submit_wiki_bundle` 工具及其 schema；
- Compile 特有的 OKF/path/citation 規則；
- `/bot/v1/compile` API family 和 `/api/v1/content/batch-write` 資料介面。

## 4. Compile API

### 4.1 建立任務

```http
POST /bot/v1/compile
```

```json
{
  "from": ["viking://resources/週報"],
  "to": "viking://resources/團隊知識庫",
  "instruction": "按月整理團隊的成本最佳化進展",
  "skill": "viking://agent/skills/monthly_wiki"
}
```

成功時返回 HTTP 202：

```json
{
  "task_id": "cmp_01...",
  "status": "accepted",
  "to": "viking://resources/團隊知識庫"
}
```

VikingBot 負責規範化引數並計算實際任務描述：

```python
effective_instruction = (request.instruction or "").strip() or DEFAULT_COMPILE_INSTRUCTION
```

### 4.2 查詢任務

```http
GET /bot/v1/compile/{task_id}
```

```json
{
  "task_id": "cmp_01...",
  "status": "running",
  "stage": "agent",
  "created_at": "2026-07-20T10:00:00Z",
  "updated_at": "2026-07-20T10:01:12Z"
}
```

任務狀態：

| status | stage |
| --- | --- |
| `accepted` | `queued` |
| `running` | `loading_skill`、`collecting_context`、`agent`、`rendering` |
| `committing` | `writing`、`refreshing`、`salvaging` |
| `completed` | `completed`、`salvaged` |
| `failed` | 失敗時所在階段 |

完成結果：

```json
{
  "task_id": "cmp_01...",
  "status": "completed",
  "result": {
    "from": ["viking://resources/週報"],
    "to": "viking://resources/團隊知識庫",
    "skill": "viking://agent/skills/monthly_wiki",
    "okf_version": "0.1",
    "created": ["viking://resources/團隊知識庫/成本最佳化月度進展.md"],
    "updated": [],
    "unchanged": [],
    "page_count": 1,
    "link_count": 0,
    "warnings": []
  }
}
```

任務只能由建立它的使用者查詢。

失敗結果使用同一查詢介面返回穩定結構：

```json
{
  "task_id": "cmp_01...",
  "status": "failed",
  "stage": "writing",
  "error": {
    "code": "WRITE_CONFLICT",
    "message": "Target Wiki changed while the compile task was running."
  }
}
```

建立請求繼續通過 body 中的 `openviking_connection` 傳遞當前使用者身份。查詢請求是 GET，沒有 body；Business Data Platform proxy 轉發原認證憑證，並從已認證的 `RequestContext` 設定 canonical `X-OpenViking-Account/User` header。VikingBot 先做現有 Gateway Token/loopback 校驗，再通過 `_resolve_request_principal()` 向 Business Data Platform 驗證憑證並計算 principal scope。無權查詢與 task 不存在統一返回 `NOT_FOUND`，避免洩露其他使用者的 task ID。

## 5. 執行流程

VikingBot 建立非同步任務後依次執行：

1. 計算 `effective_instruction`，並對 `from`、`to` 和 `skill` 做 URI 語法校驗。
2. 通過 Business Data Platform 現有 `fs/attrs` 取得來源和目標的 canonical URI，再用 stat/list/read 路徑驗證形狀與許可權；Skill API 直接返回 canonical Skill root。VikingBot 後續只使用這些響應中的 canonical URI。
3. 通過 Skills API 取得 Skill root、定義和檔案清單，通過現有 content read/download 路徑讀取輔助檔案，在 task workspace 中物化快照，並交給 `SkillsLoader` 載入。
4. 為每個來源建立 `source_id + directory_uri + overview` 描述，並使用現有 list/tree 能力建立目標 Wiki 的有界輕量 catalog。
5. 從現有 `ToolRegistry` 構建 request-local 工具集，用顯式 Compile Prompt 和 selected Skill 正文執行 structured AgentLoop；不載入普通 chat history、自動 memory recall 或其他 workspace Skill。
6. 接收 Agent 提交的結構化 `WikiBundleDraft`。
7. 對草稿中的每個 `update_uri` 讀取一次最新 raw content，生成 base hash；新頁面不需要預讀全部目標正文。
8. 校驗並渲染最終 Wiki 檔案，區分 created、updated 和 unchanged。
9. 有 write operation 時通過 batch-write 一次提交併等待索引重新整理；空 bundle 或全部 unchanged 時跳過寫入介面。
10. 儲存任務結果並清理 task workspace。

其中 AgentLoop 是唯一的內容生成階段。後續校驗、路徑生成和寫入都是確定性操作。

## 6. Skill 與上下文

### 6.1 Skill 載入

`--skill` 支援 Skill 目錄或目錄內的 `SKILL.md`。

VikingBot 從 canonical Skill URI 拆出 `skill_name` 和 `target_uri`，呼叫現有 Skills API 取得 Skill root、`SKILL.md` 和檔案列表，再通過同一使用者連線呼叫現有 content read/download 路徑讀取輔助檔案；確定性載入階段不呼叫 Agent tool，也不解析 `openviking_multi_read` 的展示文本。`SKILL.md` 使用現有 `openviking.core.skill_loader.SkillLoader.parse()` 校驗並取得 `allowed_tools`；該 parser 增加 `allowed_tools_declared` 布林值，以保留“未宣告”和“顯式空陣列”的區別，Compile 不為此再解析一遍 YAML。快照物化到 task-local workspace 後，使用現有 `vikingbot.agent.skills.SkillsLoader` 載入正文和 VikingBot metadata。requirements 使用 `SkillsLoader` 解析出的 `requires.bins/env`，但在實際 task sandbox 中做存在性檢查，避免使用 Bot host 環境誤判。

該層只負責遠端 bundle 的快照和物化，不實現新的 frontmatter parser、Skill 目錄規範或 requirements 協議。Business Data Platform 派生檔案和 Skill source metadata 不進入快照；載入過程限制檔案數量、單檔案大小和總大小，並拒絕逃逸 Skill root 的相對路徑。task workspace 只包含本次選擇的 Skill，selected Skill 正文直接加入 structured system prompt。任務結束後先呼叫 `SandboxManager.cleanup_session()` 停止 backend，再刪除 compile 專屬 workspace；現有 `cleanup_session()` 本身不會刪除 direct-backend 目錄，不能把它當成檔案清理。

Skill package 內的檔案使用 `read_file` 讀取 task workspace 路徑 `skills/<skill-name>/...`；`openviking_*` 工具只讀取任務範圍內的 `viking://` URI。

Skill 用於描述整理方法，例如：

- 應關注哪些資訊；
- 頁面如何分層；
- 使用什麼表達風格；
- 何時生成索引頁或專題頁。

### 6.2 來源上下文

VikingBot 按 canonical `from` 順序為每個來源分配穩定的 request-local ID：

```text
source_id, directory_uri, overview
```

`source_id` 只標識使用者傳入的來源目錄，例如 `src_1`；它不是檔案讀取追蹤 ID。Agent 首先獲得這些來源描述和有界輕量目錄資訊，再通過 VikingBot 已有 Business Data Platform 工具按需讀取：

- `openviking_list`：瀏覽來源目錄；
- `openviking_search`：語義檢索；
- `openviking_grep` / `openviking_glob`：按內容或路徑查詢；
- `openviking_multi_read`：讀取具體內容和 overview。

Compile 不註冊另一組 source tools。它在現有工具執行前增加 request-local URI scope guard：所有 URI 引數必須位於 `from`、`to` 或 Skill root 內；`openviking_search/list/grep/glob` 不能省略 scope 後退化為全庫查詢；`multi_read` 的 URI 數量、遞迴 list 的節點數、單次結果和任務累計工具結果位元組數受 Compile 上限約束。原工具沒有上限的地方由這個 guard 補齊，但實際讀取和許可權判斷仍由原工具完成。

### 6.3 目標上下文

執行 Agent 前，VikingBot 使用現有 list/tree/read API 將 Resource 目標完整物化到任務工作區：

```text
__compile_staging__/target_checkout/<target-relative-path>
```

Agent 直接在該目錄內新增、修改和重構最終檔案，不需要宣告 create/update，也不維護 target manifest 或 baseline hash。提交時 Compile 掃描完整 checkout、執行確定性 Wiki 內鏈處理，再將全部檔案以 `upsert` 寫回；checkout 中沒有出現的目標檔案不會被刪除。

### 6.4 工具集合

`request_tools` 從 `register_default_tools()` 建立的 task-local registry 中篩選：

```text
compile_tools = available_tools ∩ (_COMPILE_CORE_TOOLS ∪ _OV_READ_TOOLS)
request_tools = compile_tools + submit_wiki_bundle
```

`_COMPILE_CORE_TOOLS` 固定為 `read_file`、`write_file`、`edit_file` 和 `exec`；`_OV_READ_TOOLS` 固定為 `openviking_list`、`openviking_search`、`openviking_grep`、`openviking_glob`、`openviking_multi_read` 和 `openviking_export`。Business Data Platform 工具仍受使用者許可權和 Compile URI scope 限制，本地檔案和 shell 工具仍受 task workspace 與 sandbox policy 限制。

Compile 不使用 Skill 的 `allowed-tools` 推導、授權或限制工具，也不為 Skill 連線 MCP。該欄位可作為其他 Skill 宿主的相容 metadata 保留。Skill 需要方舟等外部能力時，通過 `exec` 呼叫 task sandbox 中預裝的 CLI；可選的 `requires.bins/env` 只用於提前檢查執行條件，不負責安裝 CLI 或依賴。

固定 allowlist 已排除 `message`、`cron`、`spawn`、Web、image、MCP 和 Business Data Platform 寫入/提交工具，無需維護額外 blocklist。`exec` 仍可能產生外部副作用；現有 `direct` sandbox 只提供 task cwd，不是 OS 級隔離。`bot.sandbox.backends.direct.allow_compile_exec` 預設為 `true`（Compile 工具鏈開源，`exec` 預設直接以使用者 shell 許可權執行），使用 `direct` 時 Compile 工具集預設註冊 `exec`；普通整理任務仍可通過檔案工具完成。宣告 `requires.bins` 或 `requires.env` 的 Skill 會先探測命令；如需關閉 `exec`，可顯式設為 `false`，此時此類 Skill 會在執行任何命令探測前返回 `SKILL_CAPABILITY_UNAVAILABLE`。生產或多使用者部署應使用配置了檔案系統和網路 policy 的隔離 backend。

### 6.5 結構感知探索（survey → 定向精讀）

Compile 不採用“每個檔案讀開頭 N 行”的線性掃描（開頭幾行通常是 `session_meta`/檔案頭/import，幾乎不含訊號，還會誤導 Agent 把中段內容判為低價值）。它也不在程式碼裡實現確定性結構取樣器，而是改為 **純 prompt 教會模型用已有工具做 survey → 定向精讀**，與 Claude Code / Codex 探索陌生語料的方式一致：

1. **先看目錄結構**：用 `openviking_list`（recursive）或 `openviking_glob` 拿檔案清單（路徑/大小/副檔名）。
2. **分層取樣幾個檔案**：跨目錄/副檔名/大小，用 `openviking_multi_read` 的 offset/limit 讀 **head + middle + tail 三個視窗**（不是隻讀頭幾行），理解每個檔案的格式、正文分佈與內容大致區間。
3. **推斷結構（靠模型自己，不靠程式碼代勞）**：JSONL 每行一條記錄、判別欄位是什麼、哪些欄位承載長文本；Markdown 的 heading 結構等。
4. **定向精讀**：用 `openviking_grep` 定位訊號、`openviking_multi_read` 視窗讀，或（已物化到 `compile_resources/` 的）用 `exec` 跑 jq/grep/sed/python 讀中段；明確禁止只憑檔案頭幾行判斷價值。
5. **一次性寫輸出**：所有輸出檔案儘量在一個回覆裡用多個 `write_file` 寫完。

覆蓋語義與 Codex 對齊：**沒有任何逐檔案覆蓋門禁或讀取追蹤**。物化檔案與未物化檔案都不做執行時“是否讀過”校驗；模型在 prompt 指導下自行保證“未物化（二進位制/下載失敗）的原始檔提交前用 `openviking_*` 讀工具讀過”。

### 6.6 物化與來源取樣

物化與 `to` 型別解耦：只要有 sandbox（`--to` 為 resource/memory/skill 均滿足），`--from` 的所有原始檔都會 eager 物化到 `compile_resources/<source_id>/...`（無單檔案/總位元組上限；二進位制與下載失敗檔案記為未物化，URI → 本地路徑對映記錄在 `compile_resources/_manifest.tsv`）。物化讓模型能用 `exec` 本地 grep/jq/python 掃檔案，而不是逐個 round-trip 到 Business Data Platform server。memory/skill 目標同樣物化。salvage 仍僅 resource 目標（memory 只支援 Wiki pages、skill 走原子 add/update，均無“撈 workspace 產物”語義）。

來源清單（`_build_sources`）生成每源緊湊清單（檔案數、位元組數、副檔名分佈，作為 prompt 裡的 Source inventory），模型據此在 prompt 指導下自行完成 survey 與定向精讀。

## 7. AgentLoop 輸出協議

Compile 不實現第二套 loop。VikingBot 在現有 `AgentLoop._run_agent_loop()` 上提供薄的 `run_structured_task()` 入口，並複用已有引數：

```python
await agent_loop.run_structured_task(
    system_prompt=compile_system_prompt,
    user_prompt=compile_user_prompt,
    session_key=SessionKey(type="compile", channel_id=task_id, chat_id=task_id),
    tool_registry=request_tools,
    openviking_tool_names=openviking_read_tool_names,
    stop_tool_names=["submit_wiki_bundle"],
    openviking_connection=connection,
)
```

BotCompileService 使用當前 provider/config、`workspace=task_workspace` 和 task-local `SandboxManager` 建立 request-local `AgentLoop`。`run_structured_task()` 用顯式的 system/user prompt 建立 messages 後委託給 `_run_agent_loop()`；後者增加可選 `tool_registry` 和 `openviking_tool_names` 引數，並以選定 registry 同時生成 definitions 和執行工具。只有名稱屬於 `openviking_tool_names` 的現有 OV adapter 才在 `ToolContext`/post-call hook 中收到使用者 connection；file 和 shell tool 收到 `None`。普通 chat 未傳這些引數時仍使用 `self.tools` 和現有 connection 行為。

該入口不使用普通 chat history、自動 memory/experience recall 或普通最終回答。只有 `submit_wiki_bundle` 成功執行並儲存合法 bundle 後才能結束；引數校驗或領域校驗返回 `Error:` 時繼續同一 loop 修復。只有自然語言而沒有 submit 時，wrapper 追加提交提醒後繼續；達到 `bot.agents.max_tool_iterations` 配置的 iteration limit（預設 50）時，不執行現有聊天路徑的“停用工具後再回答一次”。Resource 目標會先在獨立、受限的 salvage 階段嘗試儲存符合條件的 workspace 產物：存在可儲存產物時任務以 `completed/salvaged` 結束，否則返回 `AGENT_OUTPUT_INVALID`；Memory 和 Skill 目標直接返回 `AGENT_OUTPUT_INVALID`。模型呼叫、工具執行和 token usage 仍沿用現有實現。

現有 `_run_agent_loop()` 的 stop 判定需要從“出現 stop tool name”改成“該 stop tool 的結果通過 `_is_tool_result_success()`”；這是 structured task 正確重試的必要條件，預設聊天未傳 `stop_tool_names`，行為不變。

`request_tools` 仍使用現有 `ToolRegistry` 中的工具例項；Business Data Platform 許可權不在 Bot 中模擬，實際呼叫繼續由 Server 校驗。`submit_wiki_bundle` 最後註冊。Skill 的檔案操作和 CLI 命令繼續在 task-local `SandboxManager` 中執行；Prompt 明確要求將 Bash、shell 或 CLI 指令交給 `exec`。

當 `write_file` 可用時，artifact 必須先由 `write_file` 或 `exec` 生成到 task workspace，再通過 `workspace_path` 提交；Wiki page body 同樣先寫到 `__compile_staging__/wiki_pages/`，再通過 `body_workspace_path` 提交。此時 `submit_wiki_bundle` 的動態 schema 不暴露內聯 `content` / `body_markdown`，執行時也執行相同校驗，避免大型多檔案產物被拼進單次 tool call。

Agent 必須通過 `submit_wiki_bundle` 提交最終結果。

核心結構：

```python
class WikiPageDraft(BaseModel):
    page_id: int
    title: str
    page_type: str
    summary: str
    body_markdown: str
    source_ids: list[str]
    tags: list[str] = Field(default_factory=list)
    path_hint: str | None = None
    update_uri: str | None = None

class WikiBundleDraft(BaseModel):
    pages: list[WikiPageDraft]
    links: list[WikiLink] = Field(default_factory=list)
```

`WikiLink` 直接複用 `openviking.session.memory.dataclass.WikiLink` 做執行時校驗，使用其 `f/t/link_type/weight/match_text/description` 欄位，不定義 compile 專屬 link model。`submit_wiki_bundle` 的 tool schema 將 `match_text` 描述覆蓋為“必須出現在來源草稿正文中的錨點”，避免沿用 Memory 模型中“original conversation”的提示語義。

約束：

- `pages=[]` 表示沒有足夠依據生成可靠頁面，此時 `links` 必須為空，任務成功但返回 warning；
- `page_id` 在 bundle 內唯一；
- `update_uri` 必須來自目標 catalog；
- update 保持原 URI，不能通過 `path_hint` rename 或 move；create 的 `path_hint` 只能是 `to` 下的相對 Markdown 路徑；
- create 的最終 canonical path 不能與 catalog 中的已有檔案或本 bundle 的其他頁面衝突；
- link 的 `f/t` 必須非空、非 self-link，並引用 bundle 中的頁面；
- `pages` 非空時，每個頁面至少引用一個 `source_id`，且必須來自本次請求的來源描述；
- Agent 不提供最終檔案 URI，也不能直接寫入 Business Data Platform。

Pydantic model 使用 `extra="forbid"`；欄位校驗和 CompileLimits 都在 `submit_wiki_bundle` 內執行。校驗失敗時，工具將錯誤返回給 Agent 修復。達到迭代上限仍未提交合法結果時，Resource 目標按上述規則嘗試 salvage；其他目標或沒有合格 workspace 產物的 Resource 任務失敗。

頁面數量由 instruction、Skill 和材料決定。高層總結可以只生成一個頁面，`link_count=0` 是合法結果。

## 8. Wiki 渲染與寫入

VikingBot renderer 將 `WikiBundleDraft` 轉成最終寫入計劃。Compile 新程式碼只負責 OKF、目標路徑和 citation 規則，其餘複用現有內容模型：

1. 解析已有 OKF frontmatter；Memory 目標先用 `MemoryFileUtils.read()` 分離可見文件與 hidden metadata，Resource 目標不生成 `MEMORY_FIELDS`。
2. 將現有 `ExtractLoop._resolve_links()` 中 page ID 解析、self-link 和去重的純邏輯提取為共享 helper；Compile 使用嚴格校驗模式。
3. 使用 `LinkRenderer` 已有的 anchor 查詢、競爭處理和 escaping 生成相對 WikiLink，並補充 canonical target-root 相對路徑與 Markdown protected span 兩個純 helper。
4. 確定性生成 OKF v0.1 concept frontmatter、目標路徑和 citation section，Agent 不直接生成 YAML。
5. Memory 目標把 resolved `StoredLink` 合併到 `links/backlinks`、複用 resource refs helper，並用 `MemoryFileUtils` round-trip metadata；Resource 目標只儲存 OKF Markdown。
6. Resource checkout 直接形成最終寫入集合；服務端以 `upsert` 寫回，不在 Compile 層計算 hash 或區分 create/update。

### 8.1 OKF 與 metadata

v1 以 [Open Knowledge Format v0.1 Draft](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) 為格式基線。每個 Compile 頁面都是 UTF-8 Markdown concept document：YAML frontmatter 中 `type` 必填；Business Data Platform 額外要求 `title` 和單行 `description` 非空，`tags` 可選。

欄位對映固定為：

| Draft | OKF frontmatter |
| --- | --- |
| `page_type` | `type` |
| `title` | `title` |
| `summary` | `description` |
| `tags` | `tags`，trim、去空並穩定去重；空列表不輸出 |

renderer 使用 `yaml.safe_dump(allow_unicode=True, sort_keys=False)` 生成 YAML，拒絕 `body_markdown` 中的第二份 frontmatter。`title`、`page_type` 和 `summary` trim 後必須非空，`summary` 不允許換行。update 保留不與上述平臺欄位衝突的未知 frontmatter 欄位；不自動生成 `timestamp`，避免重複執行僅因時間變化產生更新。

只有 Memory 目標使用 `MemoryFileUtils` round-trip `MEMORY_FIELDS`。create 寫入 `category=page_type` 和 `version=1`；update 保留未知欄位、同步 `category`，先以原 version 生成 candidate，除 version 外的最終 raw bytes 發生變化時才通過 `next_memory_version()` 推進 version。為避免 hidden links 再次命中 frontmatter，`MemoryFileUtils.write()` 增加預設保持現狀的 `render_links=True` 引數，Compile 在已經渲染可見正文後以 `render_links=False` 呼叫。Resource 目標不寫 `category`、`version` 或其他 Memory metadata。

concept 頁面不寫 `okf_version`；該欄位按 OKF 只能出現在 bundle-root `index.md`。v1 不生成或修改 `index.md`、`log.md`，但保留目標中已有的這些檔案。API/result 中的 `okf_version: "0.1"` 表示本次 renderer 的目標規範版本。

### 8.2 路徑、連結與 Citations

create 的目標路徑通過 `sanitize_relative_viking_path()` 和 `safe_join_viking_uri()` 約束在 canonical `to` 下；`path_hint` 為空時使用 `VikingURI.sanitize_segment(title)`，並自動追加 `.md`。點號檔案、`index.md`、`log.md`、Business Data Platform 派生檔名和清洗後的重複路徑均拒絕。update 始終使用已有 URI。

bundle link 的兩端必須是本次提交的頁面。`match_text` 必須實際命中來源頁面的 `body_markdown`，且命中位置不能位於 YAML、程式碼塊、inline code、已有 Markdown link 或 Citations section；renderer 只對正文做 link rendering，再拼接 frontmatter 和 Citations。它使用 target-root-aware 相對路徑生成標準 Markdown link，未渲染出的 link 不計入 `link_count`。Resource 目標只保留可見連結；Memory 目標還將 resolved link/backlink 合併進 `MEMORY_FIELDS`，但 v1 不寫獨立 relation store。

renderer 把每頁 `source_ids` 對映為使用者傳入的 canonical source directory URI，並在可見正文末尾合併成唯一的頂層 `# Citations`。已有 citation 先保留，再按 canonical target 去重追加本次來源；最終統一渲染為連續的 `[n] [label](target)` 列表，來源目錄使用 canonical URI 的末級目錄名作為 label，無法取得時回退為 `Source src_n`。程式碼塊中的同名標題不視為 citation section。Agent 也可以在正文中引用來源範圍內的具體檔案 URI，這些 Markdown citation 的 label 和 target 會被保留並參與去重。`viking://` 是 Business Data Platform 對 citation target 的內部擴充，其他 OKF consumer 未必能夠解析該 scheme。

寫入使用通用內容介面。它是現有內容寫入能力的批次入口，不實現新的儲存或索引協議：

```http
POST /api/v1/content/batch-write
```

```json
{
  "root_uri": "viking://resources/團隊知識庫",
  "wait": false,
  "timeout": 300,
  "operations": [
    {
      "uri": "viking://resources/團隊知識庫/成本最佳化月度進展.md",
      "content": "...",
      "mode": "upsert"
    },
    {
      "uri": "viking://resources/團隊知識庫/既有頁面.md",
      "content": "...",
      "mode": "upsert"
    }
  ]
}
```

`content` 是 checkout 中的最終 UTF-8 儲存內容。介面支援 `replace`、`append`、`create` 和 `upsert`，不支援 delete；請求限制 operation 數量、單檔案位元組數和總位元組數。

Batch write 負責：

- 要求 `root_uri` 和 operation URI 都是規範 URI，且 `root_uri` 是已存在的可寫目錄；拒絕空 operations、重複 URI、跨 context type 以及 root 之外的目標，並按 URI 穩定排序；
- 校驗使用者對每個目標 URI 的寫許可權；
- 保證目標 URI 位於 `root_uri` 下；
- 在目標 tree lock 內按每個 operation 的 mode 呼叫與單檔案 `write()` 相同的底層寫入邏輯；`upsert` 對已有檔案執行 replace，對缺失檔案執行 create；
- 完成全部底層寫入後，以整批 `changed_uris` 重新整理語義和向量索引；
- resource/skill 按 refresh root 合併變更，每個 root 只提交一個包含全部變更的 `SemanticMsg`，由現有 semantic pipeline 自底向上更新 `.abstract.md` 和 `.overview.md`；
- memory 為變更檔案分別更新 embedding，但每個受影響目錄只調用一次 `refresh_schema_overview()`；
- 將本批次產生的 refresh 工作繫結到同一個 `RequestWaitTracker`，當 `wait=true` 時統一等待一次。

實現呼叫鏈：

```text
content.batch-write router
  -> validate_viking_uri / current-user shorthand expansion / existing target-shape check
  -> LockManager target tree lease
  -> resolve each operation mode (`upsert` -> `replace` or `create`)
  -> for each operation: shared write-in-place helper
  -> collect changed_uris and group them by refresh scope
  -> release target tree lease
  -> register one request in RequestWaitTracker
  -> existing ContentWriteCoordinator / MemoryUpdater refresh helpers
  -> one RequestWaitTracker waits for the batch's semantic and embedding work
```

Batch coordinator 放在現有 `openviking/storage/content_write.py` 附近，並從 `ContentWriteCoordinator` 下沉雙方共同使用的 target validation、SemanticMsg 構造和 refresh helper。單檔案 `write()` 與 batch 使用同一組底層實現，不復制 namespace、鎖、Memory、semantic 或 embedding 邏輯。Batch coordinator 不得針對每個 operation 迴圈呼叫高層 `ContentWriteCoordinator.write()`，否則每個檔案都會獨立觸發並等待 refresh；它必須先完成所有底層寫入、釋放 tree lock，再對彙總後的變更執行一次批次 refresh 編排，避免 semantic processor 與請求持有的 tree lock 相互阻塞。

Memory 現有 `refresh_schema_overview()` / `refresh_file_embedding()` 會記錄 warning 後吞掉部分異常。Batch 路徑需要為共享 helper 增加保持舊呼叫行為的 `strict=False` 預設值，並以 `strict=True` 呼叫；overview、semantic 或 embedding 任一登記工作失敗，或 `wait=true` 得到 failed queue status 時，batch 返回失敗，Compile task 不能標記 completed。

該介面不是跨檔案原子儲存事務：底層 I/O 在中途失敗時可能已有少量檔案可見。錯誤路徑必須釋放 tree lock，併為已成功寫入的 `changed_uris` 觸發一次 refresh；呼叫方可重試同一組 `upsert` operation。

成功響應使用 Business Data Platform 標準 envelope：

```json
{
  "status": "ok",
  "result": {
    "created": ["viking://resources/團隊知識庫/新頁面.md"],
    "updated": ["viking://resources/團隊知識庫/既有頁面.md"],
    "unchanged": [],
    "queue_status": {}
  }
}
```

Bot 以該響應為最終提交事實，不根據請求計劃假定所有檔案都已寫入；最終 Compile result 將 renderer 預先識別的 unchanged 與 batch 響應中的 unchanged 合併、穩定去重。

任一頁面在讀取後被其他請求修改時，本次寫入以 `WRITE_CONFLICT` 失敗，不覆蓋新內容。

## 9. 身份與安全

Business Data Platform Bot proxy 認證 CLI 請求，並將當前使用者的 Business Data Platform connection 轉交給 VikingBot。VikingBot 使用同一身份完成所有讀取和寫入。

Business Data Platform proxy 複用 `bot.py` 現有 Bot URL、httpx client、Gateway Token、身份附加和錯誤對映。VikingBot compile router 複用 `OpenAPIChannel._verify_gateway_request()` 和 `OpenVikingConnection`，不定義第二套 Gateway 認證或 principal 格式。

安全要求：

- task 查詢校驗建立者身份；
- API key 只存在於執行中任務的記憶體，不寫入 task store 和日誌；
- Agent 的 Business Data Platform 讀取範圍只包含 `from`、`to` 和 Skill；
- Business Data Platform adapter 的寫入和刪除工具不進入 request registry；Compile 管理的 Wiki 寫入只能由 batch-write 完成；
- 使用者 connection 只注入 scope-guarded Business Data Platform read adapter，不傳給 file 或 shell tool；
- Compile 忽略 Skill 的 `allowed-tools`，固定工具集合中的 `exec` 可能產生 Compile 之外的副作用，不納入 batch-write 的一致性保證；
- Compile Prompt 明確把來源正文、catalog 和工具結果視為待整理資料，不能把其中的文本當作指令；只有使用者的 instruction、所選 Skill 和系統 Compile 規則構成指令層；
- file tool 只能訪問 task workspace；shell 的隔離強度取決於 backend，多使用者部署必須關閉 `direct` Compile exec 或使用隔離 backend；
- 最終 URI、寫入條件和 metadata 由可信程式碼生成；
- 日誌不記錄 source 正文、Skill 正文、完整 Prompt 或憑證。

遠端使用時，Bot 執行在 Business Data Platform Server 一側。CLI 不在使用者本機啟動 Bot。

## 10. 任務儲存與併發

Compile task 保存在 VikingBot 的 `bot_data_path/compile_tasks/`，包含：

```text
task_id, principal_scope, sanitized_request, status, stage, timestamps, result, error
```

Bot 當前沒有通用的持久化後臺工作管理員，因此這裡實現一個最小 JSON task store，使用 per-task lock 和臨時檔案原子替換。程序內以有界的 `asyncio.Task` 集合和 semaphore 承載 accepted task；全域和單 principal admission 在任務建立前計數，超限同步返回 `RESOURCE_EXHAUSTED`。現有 `SessionManager` 繼續只管理 chat JSONL，不承載 Compile 狀態。

`sanitized_request` 只包含 canonical `from/to/skill` 和 effective instruction；`openviking_connection` 僅由執行中 `asyncio.Task` 持有，不進入 JSON、異常詳情或日誌。

執行中任務目錄可以儲存有大小限制的 Skill 快照、catalog 和 draft，但不能儲存使用者憑證。任務進入終態後刪除 workspace、Skill snapshot 和 draft；task/result/error JSON 最長保留 24 小時且最多保留 1,000 條，啟動和任務結束時都會清理。

VikingBot 使用獨立的 compile 併發限制，並對同一 canonical 目標目錄序列執行。accepted task 最多排隊 60 分鐘，取得 target lock 和全域執行 slot 後持續執行，直到任務完成、失敗或被取消。Agent 階段達到迭代上限時允許 salvage；salvage 與 cleanup 各自受獨立的短 grace deadline 約束。該鎖只減少同一 Bot 程序內的浪費；跨程序或人工寫入衝突仍由 batch-write 的 tree lock 和 content hash 檢查解決。v1 task store 以單個 VikingBot gateway 程序為部署邊界，不承諾多副本共享 task 查詢。

VikingBot 啟動時把 store 中所有非終態任務統一標記為 `BOT_RESTARTED`，包括處於 committing 的任務；因為 API key 不落盤，重啟後不能安全恢復原任務。使用者可以重新提交，batch-write 通過最終 content hash 跳過已落盤內容並繼續收斂。

### 10.1 v1 資源上限

v1 先使用集中定義、可測試的 `CompileLimits`，不把常量散落在 router/tool/renderer 中：

| 專案 | 預設值 |
| --- | --- |
| source roots | 16 |
| source materialization files / 總大小 | 5,000 / 1 GiB |
| Skill files / 單檔案 / 總大小 | 128 / 8 MiB / 32 MiB |
| target inventory entries / relevance catalog pages | 2,000 / 10 |
| initial prompt characters | 200,000 |
| tool URI count / 單次結果 / 任務累計結果 | 32 / 1 MiB / 8 MiB |
| output pages / files / combined operations / 最終總大小 | 128 / 128 / 256 / 4 MiB |
| concurrent Compile tasks / task runtime maximum and default | 10 / 60 min |
| salvage / cleanup grace | 120 sec / 40 sec |
| accepted tasks（全域 / 單 principal）/ queue wait | 40 / 10 / 60 min |
| terminal task retention / records | 24 h / 1,000 |

Business Data Platform batch-write 自己還要設定獨立的 request 上限，至少覆蓋 Compile 的 256 combined operations / 4 MiB，但不能信任 Bot 已經做過限制。超限統一返回 `RESOURCE_EXHAUSTED`。

## 11. 錯誤處理

| code | 場景 |
| --- | --- |
| `INVALID_ARGUMENT` | 引數缺失或 URI 格式錯誤 |
| `UNAVAILABLE` | Bot 未啟用或不可達；與現有 `ov chat` 一致 |
| `PERMISSION_DENIED` | 無權讀取來源或寫入目標 |
| `NOT_FOUND` | 來源、Skill、任務不存在，或 task 不屬於當前使用者 |
| `SKILL_INVALID` | Skill 結構或引用不合法 |
| `SKILL_CAPABILITY_UNAVAILABLE` | Skill 宣告的 requirement 或 tool 不可用 |
| `AGENT_OUTPUT_INVALID` | Agent 未提交合法 bundle |
| `MODEL_UNAVAILABLE` | 模型服務不可用 |
| `WRITE_CONFLICT` | 目標頁面在任務期間發生變化 |
| `WRITE_FAILED` | 內容寫入或索引重新整理失敗 |
| `RESOURCE_EXHAUSTED` | Skill、catalog、工具輸入或輸出超過 Compile 上限 |
| `DEADLINE_EXCEEDED` | Agent、batch refresh 或 CLI 等待超時 |
| `BOT_RESTARTED` | Bot 重啟中斷了非終態 Compile 任務 |

同步引數和服務錯誤沿用 Business Data Platform 標準 HTTP error code。任務執行錯誤通過 task 的 `status=failed` 和 `error` 返回；其中 batch API 的標準 `CONFLICT` 在 Compile task 中對映為更具體的 `WRITE_CONFLICT`。

## 12. 程式碼改動

### CLI

- `crates/ov_cli/src/main.rs`：註冊 `compile` 子命令；
- `crates/ov_cli/src/commands/compile.rs`：使用 `CliContext`/`HttpClient` 請求和輪詢，使用全域 `OutputFormat`/`output_success()` 輸出；
- `crates/ov_cli/src/commands/mod.rs`：匯出 command；
- `crates/ov_cli/src/client.rs`：增加 compile create/status 的 typed request 方法；
- `crates/ov_cli/src/help_ui.rs`：增加命令說明和示例。

### Business Data Platform

- `openviking/server/routers/bot.py`：基於現有 Bot proxy helper 增加 compile 建立和查詢請求；
- `openviking/server/routers/content.py`：提供 batch write API；
- `openviking/service/fs_service.py`：暴露 batch coordinator，保持 router 不直接操作 VikingFS；
- `openviking/core/skill_loader.py`：繼續相容解析 `allowed-tools`，Compile 不消費該欄位；
- `openviking/storage/content_write.py`：在現有 target validation、鎖和 refresh helper 上增加 batch coordinator；
- `openviking/session/memory/`：僅下沉 Link、Memory 或 refresh 雙方共用的小型純 helper，為 `MemoryFileUtils.write()` 增加相容預設值的 link-render 開關，併為 refresh 增加預設關閉的 strict 失敗傳播；
- `sdk/python/openviking_sdk/client.py`：為 Bot 使用的現有 async/sync HTTP client 增加 `batch_write()` 和 Skill 輔助檔案 download 方法。

### VikingBot

```text
bot/vikingbot/compile/
  models.py
  router.py
  service.py
  store.py
  renderer.py
```

`service.py` 只編排現有 Skills API/loader、Business Data Platform tools、AgentLoop 和 batch-write client；不為這些能力增加一層同義 wrapper。只有某部分出現獨立狀態或被第二個呼叫者複用時再拆檔案。

同時對現有模組做小型擴充：

- `bot/vikingbot/agent/loop.py`：為 `_run_agent_loop()` 增加可選 request registry，並提供薄的 `run_structured_task()`；
- `bot/vikingbot/channels/openapi.py`：接收 `BotCompileService` 並用現有 Gateway auth/principal resolver 註冊 compile router；
- `bot/vikingbot/agent/tools/`：增加 `submit_wiki_bundle` 和 request-local URI scope guard；
- `bot/vikingbot/openviking_mount/ov_server.py`：在現有 request-scoped `VikingClient` 上薄封裝 Skills/read/download/batch-write 呼叫；
- `bot/vikingbot/cli/commands.py`：gateway 先構造共享 provider/config 所屬的 AgentLoop，再建立 `BotCompileService` 並注入 OpenAPIChannel；不增加全域 service holder。

## 13. 測試與驗收

至少覆蓋：

- CLI 引數展開、預設 instruction 和 Task ID 返回；
- Bot proxy 的建立/GET 查詢身份轉交、未啟用 Bot 的 503 和上游錯誤；
- Skill 複用現有 parser/loader、相對引用、requirements 和路徑逃逸檢查；`allowed-tools` 可正常解析但不影響 Compile 工具集合；
- request registry 固定包含本地核心工具、scope-guarded Business Data Platform 只讀工具和 `submit_wiki_bundle`，不包含 message/cron/spawn/Web/image/MCP/OV write，使用者 connection 只進入 OV read adapter；
- Agent structured wrapper 複用原 loop；失敗 submit 不停止、plain text 會修復、iteration limit 不額外生成普通回答，Resource 目標只 salvage 合格產物，普通 chat 行為不迴歸；
- Business Data Platform 工具的 URI scope、預設全庫引數和數量/單次/累計輸出上限，並確認沒有註冊第二組 source tools；
- 非法 bundle 的 loop 內修復、空 bundle no-op 和最終失敗；
- 單頁面零 link、多頁面互鏈和已有頁面更新；
- OKF frontmatter、保留未知欄位、Resource/Memory 格式差異、protected anchor、路徑 containment、citation merge、WikiLink、Memory version 和 resource refs；
- batch-write 複用現有鎖/write/refresh helper，覆蓋 canonical URI/重複 operation、許可權、content hash conflict、響應丟失/refresh 失敗/部分寫入後的安全重試，並驗證釋放 tree lock 後才 refresh；
- 多檔案 resource 每個 refresh root 只產生一個 SemanticMsg，memory 每個目錄只重新整理一次 overview，strict refresh 失敗不會返回成功；
- task owner 隔離、同目標併發、終態 workspace 清理和 Bot 重啟時所有非終態任務失敗。

驗收命令：

```bash
ov compile \
  --from viking://resources/週報 \
  --to viking://resources/團隊知識庫 \
  --instruction "按月整理團隊的成本最佳化進展" \
  --skill viking://agent/skills/monthly_wiki
```

驗收結果：

1. VikingBot 載入指定 Skill 並執行 Compile AgentLoop。
2. 目標目錄生成符合 OKF v0.1 的 Wiki 頁面。
3. 重複執行只建立或更新發生變化的頁面；最終 raw bytes 相同時不 write、不推進 Memory version。
4. 未觸達的已有頁面保持不變。
5. 多頁面通過一次 batch-write 提交，並按 refresh scope 合併重新整理。
6. 未啟用 Bot 時命令返回與 `ov chat` 一致的明確錯誤。
