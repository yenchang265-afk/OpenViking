# VikingBot Skills

Skill 用 `SKILL.md` 描述一類任務的觸發條件、操作步驟和配套資源。模型讀取這些指令，再呼叫 VikingBot 已註冊的工具完成任務。Skill 本身不註冊工具，也不提供新的執行後端。

VikingBot 支援活動 Workspace 中的本地 Skill，以及儲存在 Business Data Platform 中的遠端 Skill。本文按當前程式碼說明行為；遠端方案的設計背景見 [RFC #3656](https://github.com/volcengine/OpenViking/discussions/3656)。

## 本地與遠端

| 專案 | 本地 Skill | Business Data Platform 遠端 Skill |
|------|------------|----------------------|
| 儲存 | `<active-workspace>/skills/<name>/` | Business Data Platform 返回的 canonical Skill URI |
| 發現 | 掃描工作區 Skill 目錄 | 按當前使用者問題呼叫 `find_skills`，只召回 L0 摘要 |
| 預設上下文 | 名稱、描述、本地路徑 | 名稱、描述、`SKILL.md` URI、讀取工具 |
| 讀取正文 | `read_file` | `openviking_multi_read`；讀取定義後啟用 |
| `always` | 可每輪注入完整正文 | 不支援自動常駐啟用 |
| 依賴檢查 | 在 Bot 程序環境檢查，缺失時隱藏摘要 | 啟用後、首次普通工具呼叫前在實際執行沙箱檢查 |
| `allowed-tools` | 本地載入器不據此限制工具 | 執行時強制限制當前 Turn 的工具集 |
| 配套資源 | 已在工作區內 | 文本按 URI 讀取；工具需要本地路徑時下載整個包 |
| 生命週期 | 檔案持續保留，每輪重新構建上下文 | 每條使用者訊息獨立啟用；Turn 結束清理執行副本 |

兩種 Skill 都受 Bot、渠道、請求的工具可見性和沙箱策略約束。關閉 Business Data Platform 工具不影響本地 Skill 載入。

## 使用本地 Skill

將 Skill 放到**活動 Workspace**，例如預設 `shared` 模式下的 `<workspace>/shared/skills/`。根目錄解析與隔離模式見 [Workspace 與 Agent 定製](./02-agent-capabilities.md#workspace-與-agent-定製)。

```text
<active-workspace>/skills/report-summary/
├── SKILL.md
├── scripts/
│   └── summarize.py
├── references/
│   └── report-format.md
└── assets/
    └── template.md
```

只有直接子目錄中存在 `SKILL.md` 的 Skill 才會被列出；本地名稱來自目錄名。預設每輪只注入滿足依賴的 Skill 摘要，模型選擇後讀取 `skills/report-summary/SKILL.md`。`always: true` 的本地 Skill 會直接注入去掉 frontmatter 的正文，輔助檔案仍需按需讀取。

`bot.skills` 是從內建模板複製到活動 Workspace 的 Skill 名稱列表，不是執行時掃描的白名單。初始化時只複製名單中的模板，並跳過已有的同名目錄；自行放入活動 Workspace 的 Skill 無需加入該列表。顯式按名稱載入時，工作區檔案優先於內建模板；正常摘要列表掃描的是工作區目錄。

本地 Skill 中的工具路徑以工作區為基準，例如 `python3 skills/report-summary/scripts/summarize.py`；不能假設讀取 `SKILL.md` 會切換工作目錄。

## 使用遠端 Skill

### 準備與啟用

1. 按 [Business Data Platform 整合](./04-openviking-integration.md#連線模式) 配置可用連線，並確保 Bot 當前身份有權讀取目標 Skill。
2. 將 Skill 上傳到同一 Business Data Platform 服務。有輔助檔案時上傳目錄，保留整個包：

   ```bash
   ov add-skill ./skills/report-summary/
   ```

   CLI 應連線目標服務並使用具有相應許可權的身份。儲存返回的 URI；若返回後臺 `task_id`，可用 `ov task status TASK_ID` 檢查處理進度。完整匯入方式見 [Business Data Platform Skills API](../../../../docs/zh/api/04-skills.md)。
3. 當前渠道保持 `ov_tools_enable: true`，並且 `openviking_multi_read` 已註冊、未被 `disabled_tools` 停用。
4. 向 Bot 描述任務，讓它從遠端摘要中選擇 Skill；也可以明確要求讀取某個 `SKILL.md` 的 canonical URI。

不需要額外的 Remote Skill 開關或 `load_skill` 工具。`bot.remote_skills` 只調整檢索和快取等引數，不提供 `enabled`、`default_materialize` 或 `materialize_mode`。

### 發現、啟用和執行

每條需要回復的普通使用者訊息建立一個 `SkillRuntimeContext`，覆蓋本條訊息的全部模型與工具迭代：

```text
使用者問題 → find_skills → 本地 + 遠端摘要
  → openviking_multi_read(SKILL.md) → 校驗並激活
  → 更新工具 Schema → 依賴檢查 → 按需解析資源 → 執行工具
  → 儲存結果和使用記錄 → 關閉執行時、清理請求副本
```

同名候選優先順序是本地工作區、Business Data Platform 使用者 Skill、Business Data Platform 共享 Skill（`viking://agent/skills/`）。本地目錄即使因缺少依賴未出現在摘要中，也會遮蔽同名遠端候選。顯式 URI 不走名稱選擇，應使用服務實際返回的 canonical URI；不要把名稱當作跨使用者唯一標識。

例如，對服務返回的使用者 Skill URI 發起工具呼叫：

```json
{
  "name": "openviking_multi_read",
  "arguments": {
    "uris": ["viking://user/alice/skills/report-summary/SKILL.md"]
  }
}
```

啟用會解析 frontmatter，並通過 `get_skill(include_integrity=true)` 校驗正文、canonical URI、revision 和檔案清單。此時不下載輔助檔案。模型收到的正文附帶包內相對路徑與 canonical URI 的對映。啟用需要完整正文；當前讀取工具預設拒絕完整返回超過 512 KiB 的檔案，因此應將大段參考資料拆到輔助檔案，不能通過分段讀取來啟用定義。

如果模型在同一批中同時請求讀取定義和執行其他工具，執行時先處理啟用，其餘呼叫返回 `SKILL_CONTEXT_UPDATED`，由模型在新 Schema 下重試；啟用失敗時返回 `SKILL_ACTIVATION_FAILED`，不執行同批普通工具。

## SKILL.md 與後設資料

建議使用 YAML frontmatter，並將 VikingBot 擴充放在 `metadata.vikingbot` 下。下面的遠端 Skill 示例聲明瞭 Python 命令許可權和依賴；`scripts/summarize.py`、`references/report-format.md` 必須實際存在於包中。

```markdown
---
name: report-summary
description: Summarize a report when the user requests a report review.
allowed-tools: Bash(python3 *)
tags: [reporting]
metadata:
  author: example-team
  version: "1.0"
  vikingbot:
    always: false
    requires:
      bins: [python3]
---

# Report summary

Read references/report-format.md with openviking_multi_read.
Run python3 scripts/summarize.py and summarize its output.
```

### 欄位參考

| 欄位 | 型別 / 預設 | 當前行為 |
|------|-------------|----------|
| `name` | 字串；遠端必填 | 遠端啟用時必須與 URI 中的 Skill 名稱一致；本地仍以目錄名標識 Skill，建議兩者一致 |
| `description` | 字串；遠端必填 | 描述適用任務，供模型選擇；本地未提供時摘要回退到目錄名 |
| `allowed-tools` | 空格分隔字串，也相容字串列表；預設未宣告 | 遠端工具策略，詳見下一節；本地載入器不執行該策略 |
| `tags` | 字串列表；預設 `[]` | Business Data Platform 保留的分類資訊，不改變 Bot 工具許可權或觸發方式 |
| `metadata` | YAML 物件，也相容 JSON 字串 | 擴充後設資料容器 |
| `metadata.vikingbot` | 物件 | VikingBot 識別的擴充作用域；存在時從此物件讀取擴充欄位 |
| `metadata.vikingbot.always` | 布林值；預設 `false` | 僅本地：依賴滿足時，每輪注入完整正文 |
| `always` | 頂層布林值；預設 `false` | 本地相容寫法，與 scoped `always` 按“或”判斷；遠端執行時不讀取 |
| `metadata.vikingbot.requires.bins` | 命令名列表；預設 `[]` | 所有命令都必須可用；不會自動安裝 |
| `metadata.vikingbot.requires.env` | 環境變數名列表；預設 `[]` | 所有變數都必須滿足環境檢查；宣告變數名，不在 Skill 中寫值 |
| `metadata.vikingbot.emoji` | 字串；可選 | 部分內建模板使用的說明資訊，當前 Skill 摘要生成器不讀取 |
| `metadata.vikingbot.os` | 字串列表；可選 | 部分模板宣告的平臺資訊，如 `[darwin, linux]`；當前載入器不據此過濾平臺 |
| `metadata.vikingbot.install` | 物件列表；可選 | 部分模板中的安裝說明，常含 `id`、`kind`、`bins`、`label`、`formula` 或 `package`；當前 Bot 不自動執行 |
| 其他 metadata，如 `author`、`version` | 自定義 | 可作說明資訊，當前 Bot 不據此控制執行或快取版本 |

frontmatter 的許可權欄位必須是 **`allowed-tools`**。`allowed_tools` 是 Business Data Platform 解析後的結構化資料欄位，不能替代 `SKILL.md` 中帶連字元的欄位。用真正的 YAML 布林值 `true` / `false`，不要寫字串 `"false"`。

以下兩種舊 metadata 寫法也受支援；新 Skill 建議採用上面的作用域形式，避免其他系統的擴充欄位與 Bot 混在一起：

```yaml
metadata:
  requires:
    bins: [python3]
```

```yaml
metadata: '{"vikingbot":{"requires":{"bins":["python3"]}}}'
```

### 依賴檢查的區別

本地載入器用 Bot 程序的 `PATH` 查詢命令，並要求環境變數值非空。缺少依賴的 Skill 不進入摘要或 Always 內容；這屬於發現過濾，不是執行沙箱中的許可權檢查。

遠端執行時在真正執行工具的沙箱內檢查命令；環境變數只檢查是否已定義，空值也算存在，不讀取或記錄值。環境變數名必須符合 `[A-Za-z_][A-Za-z0-9_]*`。每個啟用 Skill 在本 Turn 首次普通工具呼叫前檢查一次，與是否下載檔案無關；`openviking_multi_read` 作為讀取通道不觸發這項檢查。遠端也接受單個字串形式的 `bins` / `env`，但統一使用列表可相容本地載入器。

### 遠端 allowed-tools

| 宣告 | 含義 |
|------|------|
| 不寫 `allowed-tools` | 不額外收窄已有工具集 |
| `allowed-tools: []` 或 `allowed-tools: ""` | 不允許普通任務工具；保留 `openviking_multi_read` 讀取通道 |
| `allowed-tools: Read Bash` | 允許 `read_file` 和 `exec` |
| `allowed-tools: Bash(python3 *)` | 只允許匹配該模式的單條 `exec` 命令 |
| `allowed-tools: Bash(git:*)` | 相容冒號寫法，可匹配 `git ...` |

執行時支援的別名如下；也可以直接填寫已註冊的工具名，如 `openviking_search` 或 `mcp_<server>_<tool>`。

| Skill 寫法 | VikingBot 工具 |
|------------|---------------|
| `Bash` / `exec` | `exec` |
| `Read` / `read_file` | `read_file` |
| `Write` / `write_file` | `write_file` |
| `Edit` / `edit_file` | `edit_file` |
| `Glob` | `openviking_glob` |
| `Grep` | `openviking_grep` |
| `WebFetch` / `web_fetch` | `web_fetch` |
| `WebSearch` / `web_search` | `web_search` |
| `spawn` | `spawn` |

多個遠端 Skill 同時啟用時，普通工具許可權取所有已啟用 Skill 的交集，再受原有 Bot/渠道/請求策略限制。限制覆蓋本 Turn 後續的普通工具呼叫，不僅是引用該包檔案的呼叫。Skill 無法恢復已停用工具；`openviking_multi_read` 豁免 Skill 策略交集，但仍須在 Bot 中可用。

同一個 Skill 的多個 Bash 模式按“或”匹配，不同 Skill 之間按“且”匹配。模式匹配完整命令字串；帶引數約束時拒絕管道、重定向、命令連線、換行、反引號和 `$()` 等複合 shell 語法。無引數約束的 `Bash` 不增加這層命令匹配。其他工具暫不支援括號引數約束，例如 `Read(...)` 會被拒絕。需要執行指令碼時應顯式使用 `python3`、`bash` 等直譯器，不依賴下載後的可執行位。

## 遠端資源與本地路徑

啟用之後，文本說明仍用 `openviking_multi_read` 讀取。`exec` 引用包內檔案，或普通工具宣告的輸入引數需要本地檔案/目錄時，執行時才把 Skill 包下載到沙箱並改寫引數。

| 輸入示例 | 處理 |
|----------|------|
| `openviking_multi_read` 讀取 `references/report-format.md` | 唯一匹配已啟用包後轉換為 canonical URI，遠端讀取 |
| `exec` 執行 `python3 scripts/summarize.py` | 匹配清單，下載整個包，改寫指令碼路徑 |
| 已啟用包內的完整 `viking://.../assets/template.md` | 按消費工具要求遠端讀取或轉成本地路徑 |
| 多個包都有 `scripts/summarize.py` | 拒絕模糊路徑，要求完整 canonical URI |
| 普通工作區檔案 `workspace:input/report.csv` | 去掉 `workspace:` 字首，傳給原本地檔案工具或 `exec` |
| 當前沙箱的原生絕對路徑、HTTP / Data URL | 原樣交給消費工具 |
| 未匹配的裸相對檔案路徑、目錄逃逸或未啟用包的資源 | 拒絕；先確認來源或讀取對應 `SKILL.md` |

`workspace:` 用於本地檔案引數與 `exec`；它不是 `openviking_multi_read` 的工作區讀取協議。輸出也應儲存在普通工作區，例如命令引數使用 `workspace:output/summary.md`，避免 Turn 結束時跟隨臨時 Skill 包被刪除。

執行時保留包內目錄結構，但不會把工具工作目錄切到包根。指令碼應根據自己的檔案位置解析相鄰模板和模組；模型直接使用返回的資源繫結，不應手工複製資源或把 `working_dir` 設定成遠端 URI、快取路徑或物化目錄。執行失敗不會自動補下載並重跑原命令。

工具開發者通過 `Tool.resource_inputs` 宣告本地輸入引數，例如 `{"path": "local_file", "/files/*/workspace_path": "local_file"}`。支援 `local_file`、`local_directory` 和帶 `*` 的 JSON Pointer 風格路徑。未宣告的引數不會僅因名字像路徑而自動處理；輸出引數不應宣告成輸入。此宣告屬於工具實現，不是 Skill metadata。

## 生命週期、快取與配置

每條使用者訊息重新發現、啟用遠端 Skill；同一 Session 下一輪不會繼承候選、許可權交集或依賴檢查結果。工具使用記錄包含真實 `skill_uri` / `skill_uris` 和解析後的 `resolved_args`。當前程式碼沿用普通工具結果的 Session、事件和 Trace 記錄流程，讀取到的 Skill 正文也可能進入這些記錄；RFC 提出的獨立脫敏檢視和正文不持久化不能視為當前實現保證。

檔案分為兩層儲存：

| 層級 | 當前路徑 | 生命週期 |
|------|----------|----------|
| Bot 主機快取 | `<bot-data>/remote_skill_cache/` | 按許可權域、canonical 根 URI 和服務端 revision 隔離，TTL/LRU 淘汰 |
| 工具執行副本 | `<sandbox>/.remote-skill/<request-id>/<root-uri-sha256>/<skill-name>/` | 當前 Turn 內複用，結束時清理；不會直接執行主快取檔案 |

這裡的 `.remote-skill/` 是當前程式碼路徑。快取命中仍需當前身份成功讀取、啟用並複查 manifest；隨後逐檔案校驗大小和 SHA-256，複製到請求沙箱。版本變化或檔案校驗失敗時拒絕繼續使用該快照。快取減少重複下載，不跳過 Business Data Platform ACL，也不以 `metadata.version` 作為快取版本。

以下欄位位於 `ov.conf` 的 **`bot.remote_skills`** 物件中，都是部署配置，不是 frontmatter：

| 欄位 | 預設值 | 作用 |
|------|--------|------|
| `discovery_limit` | `8` | 最多注入的遠端候選數，範圍 1–50 |
| `score_threshold` | `0.35` | 最低召回分數，範圍 0–1 |
| `discovery_timeout_seconds` | `2.0` | 發現超時秒數，須大於 0 且不超過 30 |
| `max_files` | `128` | 單包物化檔案數，包含 `SKILL.md` |
| `max_file_bytes` | `8388608`（8 MiB） | 單檔案大小；讀取啟用的 `SKILL.md` 也受此限制 |
| `max_total_bytes` | `33554432`（32 MiB） | 單包物化總大小 |
| `cache_idle_ttl_seconds` | `600` | 主快取空閒 TTL，命中後重新整理 |
| `cache_max_entries` | `32` | 主快取最多保留的快照數 |
| `cache_max_bytes` | `268435456`（256 MiB） | 主快取總大小上限 |

檔案數、大小和快取容量須為正數。過期快取會在後續快取活動時清理；容量不足按 LRU 淘汰未佔用條目。服務端完整性 API 的限制也會生效，調大 Bot 限額不能繞過服務端限制。

## 子 Agent 與常見問題

子 Agent 使用工作區本地 Skill 摘要和 Always 內容。當前子 Agent 不註冊 Business Data Platform 工具，因此不發現、啟用或繼承主 Agent 的遠端 Skill 執行時與快照。

| 現象或錯誤 | 檢查方式 |
|------------|----------|
| 本地 Skill 未出現在摘要 | 檢查活動 Workspace、直接子目錄中的 `SKILL.md`，以及 Bot 程序的命令和環境變數 |
| 無遠端候選 | 檢查連線、渠道開關、工具停用、檢索分數/超時、同名本地目錄；發現失敗時繼續使用本地上下文 |
| `SKILL_NOT_ACTIVE` | 先用 `openviking_multi_read` 讀取該包的 `SKILL.md` |
| `SKILL_TOOL_NOT_ALLOWED` | 檢查所有已啟用 Skill 的許可權交集，以及 Bash 命令約束 |
| `SKILL_CAPABILITY_UNAVAILABLE` | 在實際執行沙箱提供宣告的命令/環境變數，確認沙箱可用 |
| `SKILL_RESOURCE_NOT_FOUND` / `SKILL_RESOURCE_AMBIGUOUS` | 使用返回的 canonical 資源 URI；普通工作區輸入使用 `workspace:` |
| `SKILL_INTEGRITY_UNAVAILABLE` / `SKILL_REVISION_CHANGED` | 確認服務端支援完整性清單；Skill 更新完成後在新 Turn 重新讀取 |
| `SKILL_PACKAGE_TOO_LARGE` | 精簡包內資源，或核對 Bot 與服務端限制 |

## 實現位置

| 內容 | 路徑（相對 `bot/`，另有說明除外） |
|------|------------------------------------------------|
| 本地載入、metadata 和依賴過濾 | `vikingbot/agent/skills.py` |
| 主 Agent / 子 Agent 的 Skill 上下文 | `vikingbot/agent/context.py`、`vikingbot/agent/subagent.py` |
| 請求執行時、啟用、策略與資源解析 | `vikingbot/agent/remote_skills.py` |
| 快取與工作區初始化 | `vikingbot/agent/remote_skill_cache.py`、`vikingbot/sandbox/manager.py` |
| 工具批次、Schema 與呼叫處理 | `vikingbot/agent/loop.py`、`vikingbot/agent/tools/registry.py` |
| 遠端讀取與 Experience Hook | `vikingbot/agent/tools/ov_file.py`、`vikingbot/hooks/builtins/openviking_hooks.py` |
| 配置預設值 | `vikingbot/config/schema.py` |
| Business Data Platform frontmatter 解析 | 倉庫根目錄 `openviking/core/skill_loader.py` |

## 相關文件

- [Agent 能力體系](./02-agent-capabilities.md)
- [VikingBot 與 Business Data Platform 整合](./04-openviking-integration.md)
- [Business Data Platform Skills API](../../../../docs/zh/api/04-skills.md)
