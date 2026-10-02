# Business Data Platform Working Memory v2 — 設計文件

## 文件目標

本文描述 Business Data Platform Working Memory v2（以下簡稱 WM v2）的當前實現：設計原則、資料結構、協議、流程，以及對應程式碼位置。

---

## 當前能力

### afterTurn（每輪對話後自動歸檔）

| 能力 | 說明 |
|---|---|
| 自動檢測歸檔時機 | `pending_tokens` 滑動視窗，O(1) 計算 |
| 增量更新 WM | tool_call + JSON schema + 服務端 Guards |
| 歸檔後保留最近訊息 | `keep_recent_count`，保持上下文連貫 |

### compact（主動上下文壓縮）

| 能力 | 說明 |
|---|---|
| 全量重寫 WM 並歸檔 | `keep_recent_count=0`，徹底壓縮 |

### assemble（構建 LLM 上下文）

| 能力 | 說明 |
|---|---|
| WM overview 作為會話摘要 | 結構化 7 段模板 + 舊格式自動升級 |
| 按 archive_id 展開歸檔原文 | `ov_archive_expand` 工具 / API 讀取單個 completed archive 的原始訊息 |
| 按關鍵詞跨 archive 回查 | `ov_archive_search` 工具，服務端 grep 命中訊息 + archive 標籤 |

### 通用

| 能力 | 說明 |
|---|---|
| 資訊保留 Guards | 5 個段級保護函式 |

---

## 一、設計方案

### 1.1 設計原則

**原則 1：archive 本體就是 working memory，用固定的結構化模板承載**

archive 的 `.overview.md` 是**固定 7 段結構化模板**（Session Title / Current State / Task & Goals / Key Facts & Decisions / Files & Context / Errors & Corrections / Open Issues）。每段有明確的職責，LLM 不能隨意增刪段落。

有結構才能做增量更新——LLM 對每個段獨立發 `KEEP` / `UPDATE` / `APPEND` 操作，未變化的段發 `KEEP` 由服務端原樣複製（零 token 消耗、零資訊丟失），變化的段走校驗後合併。

向後相容性的 3 條保證：

- `assemble()` 消費的仍然是 `latest_archive_overview`，無新增資料通路
- `getSessionContext()` 返回欄位不變
- 儲存結構（`archive_NNN/.overview.md`）不變

**原則 2：資訊保留是系統責任，不是 LLM 責任**

LLM 只負責「判斷變了什麼」，服務端 guard 函式負責「保證不丟資訊」。具體機制見 §1.4。

**原則 3：向後相容與平滑升級**

- 不配置新欄位時行為完全不變，`keep_recent_count=0` 等價於全量歸檔
- 已有舊格式 overview 的會話：服務端自動檢測 overview 是否包含 WM 7 段 header。如果是 legacy 格式，走建立路徑全量生成 WM，不走 tool_call 增量更新——下一次 commit 時自動完成格式升級，無需手動遷移

### 1.2 WM 資料結構

WM 是一份 Markdown 文件，固定 7 個 section，順序不變：

```markdown
# Working Memory

## Session Title
_簡短獨特的 5-10 詞標題，資訊密集_

## Current State
_當前工作狀態、待完成任務、下一步_

## Task & Goals
_使用者目標、關鍵設計決策、解釋性上下文_

## Key Facts & Decisions
_重要結論、技術選擇及理由、使用者偏好與約束_

## Files & Context
_重要檔案 / 函式 / 模組及路徑_

## Errors & Corrections
_遇到的錯誤及修復、使用者糾正、失敗方案_

## Open Issues
_未解決問題、阻塞項、後續風險_
```

每段上限 ~2000 tokens，總 WM 上限 ~12000 tokens（prompt 指引層面的預算約束）。服務端 guard 在單段 ≥ 25 bullets 或 ≥ 1500 tokens 時觸發 consolidation 提醒。

### 1.3 增量更新協議

WM 更新通過 **tool_call（function calling）+ JSON schema** 實現：LLM 呼叫 `update_working_memory` 工具，以結構化 JSON 提交對 7 個段的逐段操作。JSON schema 強約束保證漏段、多段、格式錯誤在 schema 層直接攔截。

#### tool schema 定義

```python
WM_SEVEN_SECTIONS = [
    "Session Title", "Current State", "Task & Goals",
    "Key Facts & Decisions", "Files & Context",
    "Errors & Corrections", "Open Issues",
]

WM_UPDATE_TOOL = {
    "type": "function",
    "function": {
        "name": "update_working_memory",
        "parameters": {
            "type": "object",
            "required": ["sections"],
            "additionalProperties": False,
            "properties": {
                "sections": {
                    "type": "object",
                    "required": list(WM_SEVEN_SECTIONS),     # 7 段全部必填
                    "additionalProperties": False,
                    "properties": {name: _WM_SECTION_OP_SCHEMA
                                   for name in WM_SEVEN_SECTIONS},
                }
            },
        },
    },
}
```

每段的操作（`_WM_SECTION_OP_SCHEMA`）用 `oneOf` 約束為三種形狀之一：

- `{"op": "KEEP"}` — 原樣保留
- `{"op": "UPDATE", "content": "..."}` — 全段替換
- `{"op": "APPEND", "items": ["...", "..."]}` — 追加條目

`op` 欄位使用 `"type": "string", "enum": ["KEEP"]` 形式，相容更多 JSON Schema 版本。`additionalProperties: false` + `required` 把 LLM 輸出嚴格釘在這個 schema 裡。

#### 段級合併

服務端 `_merge_wm_sections(old_wm, ops)` 按 `WM_SEVEN_SECTIONS` 常量遍歷 7 段：

- **KEEP** → 原樣複製舊內容
- **UPDATE** → 用 LLM 提供的 content 替換（先經過該段的 guard 校驗）
- **APPEND** → 舊內容 + LLM 提供的 items（渲染為 `- item`）
- 漏段 / 未知 op → 兜底 KEEP

關鍵實現：`session.py: _merge_wm_sections()` + `_parse_wm_sections()`

### 1.4 服務端 Guards

Guards 是服務端在合併 LLM 提交的操作時按段執行的語義校驗函式：**即使 LLM 說 UPDATE，服務端也根據段的特性決定是否接受**。

7 個段的保護策略：

| 段 | 資料特點 | Guard | 規則 |
|---|---|---|---|
| Session Title | **錨定型**：會話身份標識，不應隨意變更 | `_wm_enforce_title_stability` | UPDATE 與舊 title meaningful-word overlap < 1 → 回退 KEEP |
| Current State | **易變型**：每輪反映當前狀態 | 無 | LLM 可自由 UPDATE |
| Task & Goals | **易變型**：目標隨會話推進自然變化 | 無 | LLM 可自由 UPDATE |
| Key Facts & Decisions | **累積型**：重要結論不斷積累，丟失代價高 | `_wm_enforce_key_facts_consolidation` | 雙閾值驗證：bullet count ≥ 舊 15% 且 lexical anchor coverage ≥ 70%。被拒時提取新 items 做 APPEND |
| Files & Context | **引用型**：檔案路徑一旦提及不應消失 | `_wm_enforce_files_no_regression` | UPDATE 丟失舊路徑 → KEEP + APPEND 新路徑 |
| Errors & Corrections | **只增型**：錯誤記錄只增不刪 | `_wm_enforce_append_only` | UPDATE 降級為 APPEND，去重後只追加新條目 |
| Open Issues | **跟蹤型**：未解決項不應被靜默丟棄 | `_wm_enforce_open_issues_resolved` | silently drop 的 item → 加 `[restored]` 標籤恢復 |

Errors 是純 append-only（UPDATE 總被降級為 APPEND）；Key Facts 允許「受控合併」——LLM 提交的合併 UPDATE 通過雙閾值驗證後可被接受。

關鍵實現：`session.py: _wm_enforce_*()` 5 個函式。單元測試覆蓋在 `tests/unit/session/test_wm_v2_guards.py`（共 107 用例覆蓋 5 個 guard + growth + 通用 schema）。

### 1.5 滑動視窗與 pending_tokens

`SessionMeta` 維護 `pending_tokens: int` 和 `keep_recent_count: int`，持久化到 `.meta.json`。

- `add_message` 時：新訊息進入保留視窗尾部，視窗頭部被擠出的訊息 token 累加到 `pending_tokens`
- `commit` 時 `pending_tokens` 歸零
- `GET /sessions/{id}` 直接讀 meta，O(1)

服務端有防禦性 clamp：`pending_tokens` 與 `keep_recent_count` 都 `max(0, ...)`。`CommitRequest.keep_recent_count` 在 router 層有 `ge=0, le=10_000` 約束。

關鍵實現：`session.py: add_message()` + `SessionMeta`、`routers/sessions.py: CommitRequest`

### 1.6 保留最近消息

commit 歸檔時不全量清空訊息，保留最近 N 條維持上下文連貫。

- 引數 `keep_recent_count` 由外掛在 commit API body 中傳入
- `afterTurn` 路徑預設 10，`compact` 路徑硬編碼 0
- OV 儲存模型保證 `tool_use` / `tool_result` 配對完整性（ToolPart 自包含）

關鍵實現：`session.py: commit_async(keep_recent_count)`、`routers/sessions.py: CommitRequest`、`context-engine.ts`、`client.ts`

---

## 二、流程

### 2.1 afterTurn 流程

外掛端不變，commit 在服務端完成：

```
[插件] afterTurn
  ├── extractNewTurnMessages → 提取新消息
  ├── addSessionMessage → 逐條 POST /sessions/{id}/messages
  │     服務端: append msg + 滑動視窗更新 pending_tokens + save meta
  ├── GET /sessions/{id} → 返回 pending_tokens（O(1)）
  └── pending_tokens >= tokenBudget * commitTokenThresholdRatio?
        │
        YES → commitSession(wait=false, keepRecentCount=cfg.commitKeepRecentCount)
              │
              [服務端 commit_async]
              │
              ├── Phase 1（同步，不阻塞返回）
              │    ├── split_idx = total - keep_recent_count
              │    ├── 歸檔 messages[:split_idx] → archive_NNN/
              │    ├── 保留 messages[split_idx:]
              │    └── pending_tokens = 0, 更新 meta
              │
              └── Phase 2（asyncio.create_task 後臺執行，包在
                  request_wait_tracker.register_request / wait_for_request /
                  cleanup 包絡內，確保所有下游 enqueue 都被等待）
                   ├── 讀舊 WM: _get_latest_completed_archive_overview()
                   ├── 有舊 WM?
                   │   YES → ov_wm_v2_update prompt + tool_call
                   │          → guards 檢查每段決策
                   │          → _merge_wm_sections 段級合併
                   │   NO  → ov_wm_v2 prompt 全量建立
                   ├── 寫入 archive_NNN/.overview.md + .abstract.md + .meta.json
                   ├── 提取 long-term memory（SessionCompressorV3，需 archive_uri 才能寫 memory_diff.json）
                   ├── 等待 embedding / semantic 佇列排空（wait_for_request）
                   └── 寫入 .done（最後寫，標誌該 archive 全部狀態終結）
```

Phase 2 關鍵細節：

- **格式檢測**：讀取舊 overview 後，先檢查是否包含 WM 7 段 header（`any(f"## {s}" in overview for s in WM_SEVEN_SECTIONS)`）。如果是 legacy 格式，走建立路徑而非 tool_call 更新——保證平滑升級
- **Section reminders**：更新路徑中，`_build_wm_section_reminders()` 從舊 WM 提取每段當前狀態摘要，注入到 update prompt 的 `wm_section_reminders` 變數
- **完整回退鏈**：tool_call 缺失 → `_fallback_generate_wm_creation` 重跑（傳入舊 WM 作為上下文）；JSON parse 失敗 → 正則 recovery → 段級 guard 兜底 KEEP；VLM 不可用 → 佔位 summary
- **Phase 2 佇列等待**：`register_request` + `wait_for_request(timeout=_PHASE2_QUEUE_WAIT_TIMEOUT_SECONDS=1800s)` 是必需的——否則下游 `compressor` / `memory_updater` 通過 `register_*_root` 註冊的 embedding / semantic 佇列無人 await，會讓 `tracker.complete()` 與 `.done` 在向量化 / 語義入庫**之前**就觸發，導致呼叫方看到 commit 完成但 memory 不可檢索

### 2.2 compact 流程

```
[插件] compact
  └── commitSession(wait=true, keepRecentCount=0)
        ├── Phase 1: 全部消息 → archive, messages.clear()
        ├── Phase 2: 讀舊 WM → 建立/更新 → 寫入
        └── 返回 → getSessionContext → 回讀最新 WM
```

### 2.3 assemble（上下文組裝）

instruction / archive / session 三分割槽：

```
┌──────────── System Prompt ────────────────────┐
│ systemPromptAddition（語義示意，非逐字）：       │
│   1. [Session History Summary] 是壓縮摘要      │
│   2. Active messages 是最新未壓縮上下文        │
│   3. 二者衝突時優先 active messages            │
│   4. 缺細節時詢問使用者，不要猜                   │
│ + 原始 system prompt                           │
└────────────────────────────────────────────────┘

┌──── Layer 1: Archive Memory (≤8K tokens) ─────┐
│  [user] [Session History Summary]              │
│  # Working Memory                              │
│  ## Session Title                              │
│  ## Current State                              │
│  ## Task & Goals                               │
│  ## Key Facts & Decisions                      │
│  ## Files & Context                            │
│  ## Errors & Corrections                       │
│  ## Open Issues                                │
└────────────────────────────────────────────────┘

┌──── Layer 2: Session Context ─────────────────┐
│  server 側合併後的 ctx.messages:               │
│  - 未完成 archive 的 pending messages          │
│  - 當前 live session messages                  │
└────────────────────────────────────────────────┘

┌──── Layer 3: Reserved (≥20K tokens) ──────────┐
│  LLM 回覆空間                                  │
└────────────────────────────────────────────────┘
```

實現要點：

- `pre_archive_abstracts` 欄位保留在 API（向後相容），但服務端固定返回空陣列，外掛側 `buildArchiveMemory()` 只消費 `latest_archive_overview`
- 若需要具體 archive 原文，模型走兩條路徑：按 `archive_id` 用 `ov_archive_expand` 展開；或用 `ov_archive_search` 按關鍵詞跨 archive grep（見 §三）

---

## 三、歸檔對話回查工具

Business Data Platform 在外掛側暴露兩個獨立的 archive 回查工具。

### 3.1 `ov_archive_expand`

- **外掛工具**：`ov_archive_expand`，引數 `archiveId: string`
- **服務端 API**：`GET /api/v1/sessions/{session_id}/archives/{archive_id}`，server 返回 `{archive_id, abstract, overview, messages}`
- **工具輸出給 LLM**：archive header（`## archive_id` + `**Summary**: abstract` + `**Messages**: N`） + 全部原始 messages（faithful 文本格式）。`overview` 不重複輸出（已經在主上下文 `[Session History Summary]` 裡）
- **工具 description 文本**：`"Retrieve original messages from a compressed session archive. Use when a session summary lacks specific details such as exact commands, file paths, code snippets, or config values. Check [Archive Index] to find the right archive ID."`

### 3.2 `ov_archive_search`

- **外掛工具**：`ov_archive_search`，引數 `query: string` + 可選 `archiveId: string`
- **客戶端封裝**：`client.grepSessionArchives(sessionId, pattern, options)`
- **服務端 API**：`POST /api/v1/search/grep`，body `{uri, pattern, case_insensitive}`。`uri` 預設 `viking://session/{sessionId}/history`（覆蓋所有 archive）；指定 `archiveId` 時收窄為 `viking://session/{sessionId}/history/{archiveId}`
- **工具輸出給 LLM**：最多 12 條命中訊息，每條最多 1500 字元，附 archive 標籤（如 `archive_005`）和行號
- **行為約束**：
  - 預設遍歷所有 archive（新到舊）
  - 預設永遠不返回完整 archive 原文
  - case-insensitive；正則元字元自動轉義為字面量匹配
- **工具 description 文本**：`"Keyword-grep across all archived original conversation messages of the current session. Use this whenever the [Session History Summary] does not contain the specific detail the user is asking about. Extract 2-3 concrete entity words from the question (names, places, objects, dates) and search each separately. Only conclude information is unavailable after trying at least 2 different keyword variations."`

---

## 四、關鍵程式碼索引

| 主題 | 路徑 |
|---|---|
| WM 7 段常量與 schema | `openviking/session/session.py: WM_SEVEN_SECTIONS / _WM_SECTION_OP_SCHEMA / WM_UPDATE_TOOL` |
| 段級合併 | `openviking/session/session.py: _merge_wm_sections() / _parse_wm_sections()` |
| 5 個 Guards | `openviking/session/session.py: _wm_enforce_*()` |
| Phase 2 主迴圈 | `openviking/session/session.py: _run_memory_extraction()` |
| 滑動視窗 / pending_tokens | `openviking/session/session.py: SessionMeta / add_message()` |
| commit API + keep_recent_count clamp | `openviking/server/routers/sessions.py: CommitRequest` |
| WM v2 prompt 模板 | `prompts/templates/compression/ov_wm_v2.yaml`、`ov_wm_v2_update.yaml` |
| 插件 commit / afterTurn / compact | `examples/openclaw-plugin/context-engine.ts` |
| 插件 ov_archive_search 工具 | `examples/openclaw-plugin/index.ts: ov_archive_search` |
| 插件 ov_archive_expand 工具 | `examples/openclaw-plugin/index.ts: ov_archive_expand` |
| 單元測試 | `tests/unit/session/test_wm_v2_guards.py`、`test_working_memory_growth.py`、`test_working_memory_v2.py`（共 107 用例） |

---

> **建立**：2026-05-02  
