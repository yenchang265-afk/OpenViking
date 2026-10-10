# 技能

技能是供智慧體讀取的任務指令與配套資源。OpenViking 負責儲存、檢索和管理技能；讀取後的啟用、工具許可權與執行由使用它的 Agent/Harness 負責。本文以當前倉庫的 HTTP API、SDK 和 `ov` CLI 實現為準。

## 核心概念

### 技能型別

OpenViking 支援多種技能定義格式：

1. **結構化技能資料**：包含 name、description、content 等欄位的字典
2. **SKILL.md 檔案**：帶有 YAML frontmatter 的 Markdown 檔案
3. **MCP Tool 格式**：自動檢測並轉換為技能文件，不會連線 MCP Server 或註冊可執行工具
4. **Skill 包與集合**：包含 `SKILL.md` 和輔助檔案的目錄、ZIP，或 Git 倉庫 / GitHub tree URL

### 技能儲存結構

技能支援當前使用者私有根 `viking://user/{user_id}/skills/` 和帳戶內共享根 `viking://agent/skills/`。新增時的目標優先順序為：請求 `target_uri` → 使用者 `add_targets.skill_uri` → 服務端 `user_config_defaults.add_targets.skill_uri` → 當前使用者私有根。所有訪問仍受當前身份和許可權約束。

家目錄別名 `viking://~/skills/` 始終按認證身份展開為當前使用者的私有根，不隨預設新增目標改變。無 uid 的 `viking://user/skills/` 和 peer-scoped skills 均不支援。私有根的包結構如下；共享根使用相同結構：

```
viking://user/{user_id}/skills/
+-- search-web/
|   +-- .abstract.md      # L0：簡要描述
|   +-- .overview.md      # L1：引數和使用概覽
|   +-- SKILL.md          # L2：完整文件
|   +-- [auxiliary files] # 其他輔助檔案
+-- calculator/
|   +-- .abstract.md
|   +-- .overview.md
|   +-- SKILL.md
+-- ...
```

### 整包處理與索引

新增 Skill 預設處理整個包，不需要額外開關。主目錄 L0 仍來自技能後設資料，L1 仍只根據 `SKILL.md` 生成；子目錄沿用 resource 的方式生成 L0、L1。目錄 L0、L1 和支援的檔案 L2 都建立索引，包內巢狀的 `SKILL.md` 作為普通附件處理。

輔助檔案會進入已有的摘要和 embedding 處理流程，受現有隱藏檔案過濾、長度上限和媒體配置約束。圖片使用模型支援的圖片或文字輸入；音影片使用文字摘要，無法理解時沿用檔名回退。`wait=true` 等待整個包處理完成。升級不會自動重建舊 Skill；首次補齊應使用 `semantic_and_vectors` 重建，僅重建向量不會生成缺失的目錄摘要。

### SKILL.md 格式

技能可以使用帶有 YAML frontmatter 的 SKILL.md 檔案來定義：

```markdown
---
name: skill-name
description: Brief description of the skill
allowed-tools: Read Bash(python3 *)
tags:
  - tag1
  - tag2
metadata:
  author: example-team
  vikingbot:
    requires:
      bins: [python3]
---

# Skill Name

Full skill documentation in Markdown format.

## Parameters
- **param1** (type, required): Description
- **param2** (type, optional): Description

## Usage
When and how to use this skill.

## Examples
Concrete examples of skill invocation.
```

**必填字段**：

| 欄位 | 型別 | 說明 |
|------|------|------|
| name | str | 非空，最多 64 個 ASCII 字母、數字、下劃線或連字元；建議 kebab-case |
| description | str | 簡要描述 |

**可選欄位**：

| 欄位 | 型別 | 說明 |
|------|------|------|
| allowed-tools | str / List[str] | 空格分隔的工具宣告，也相容字串列表；括號內可含空格，由消費方解釋和執行策略 |
| tags | List[str] | 用於分類的標籤 |
| metadata | object | 原樣保留的擴充欄位，如 `metadata.vikingbot.requires`；OpenViking 不自動安裝這些依賴 |

`SKILL.md` 使用帶連字元的 **`allowed-tools`**，解析後的結構化資料和 API 摘要使用 **`allowed_tools`**。不要在 frontmatter 中用下劃線拼寫替代它。未宣告和顯式空宣告可能在 Harness 中有不同許可權含義，摘要裡的 `allowed_tools: []` 不能區分二者；執行前應讀取完整 `SKILL.md`。正文與擴充欄位的消費方式見 [VikingBot Skills](../../../bot/docs/zh/concepts/06-skills.md)。

### MCP 格式自動轉換

OpenViking 會自動檢測並將 MCP Tool 定義轉換為技能格式。

**檢測規則**：如果字典包含 `inputSchema` 欄位，則被視為 MCP 格式。

**轉換過程**：
1. 將名稱中的下劃線替換為連字元（不會自動轉換 camelCase）
2. 描述保持不變
3. 從 `inputSchema.properties` 中提取引數
4. 從 `inputSchema.required` 中標記必填欄位
5. 生成 Markdown 內容

**轉換示例**：

輸入（MCP 格式）：
```json
{
    "name": "search_web",
    "description": "Search the web",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query"
            },
            "limit": {
                "type": "integer",
                "description": "Max results"
            }
        },
        "required": ["query"]
    }
}
```

輸出（Python 字典形式）：
```python
{
    "name": "search-web",
    "description": "Search the web",
    "content": """---
name: search-web
description: Search the web
---

# search-web

Search the web

## Parameters

- **query** (string) (required): Search query
- **limit** (integer) (optional): Max results

## Usage

This tool wraps the MCP tool `search-web`. Call this when the user needs functionality matching the description above.
"""
}
```

## API 參考

### add_skill

向知識庫新增技能。

#### 1. API 實現介紹

技能是一種特殊的資源，用於定義智慧體可以執行的操作或工具。

**處理流程**：
1. 接收技能資料或上傳的臨時檔案
2. 檢測資料格式（結構化資料、SKILL.md 內容、MCP 格式）
3. 解析技能定義
4. 將包儲存到選定的使用者私有或帳戶共享 skills 根
5. 預設返回 `task_id`，用於查詢後臺向量化任務

**程式碼入口**：
- `sdk/python/openviking_sdk/client.py:AsyncHTTPClient.add_skill` - Python SDK 入口
- `openviking_cli/client/http.py` - 相容匯入入口，轉發到 Python SDK
- `openviking/server/routers/resources.py:add_skill` - HTTP 路由
- `openviking/server/mcp_endpoint.py:add_skill` - MCP 工具
- `openviking/server/skill_ingest.py:install_skills` - HTTP 路由、MCP 工具與 skill 簽名上傳共用的安裝實現
- `openviking/service/resource_service.py:ResourceService.add_skill` - 核心服務實現
- `openviking/server/routers/skills.py` - 列表、檢索、讀取、校驗、更新和刪除
- `crates/ov_cli/src/commands/skills.rs` - CLI Skill 命令處理

#### 2. 介面和引數說明

**HTTP 請求體引數**（`POST /api/v1/skills`）：

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| data | Any | 否 | - | 內聯 SKILL.md、結構化/MCP 資料或 Git URL；與 `temp_file_id` 選擇一個 |
| temp_file_id | string | 否 | - | 臨時上傳檔案 ID（通過 `temp_upload` 獲取）；與 `data` 選擇一個 |
| wait | bool | 否 | False | 是否等待技能處理完成 |
| timeout | float | 否 | None | 超時時間（秒），僅 `wait=True` 時生效 |
| telemetry | TelemetryRequest | 否 | False | 是否返回遙測資料 |
| target_uri | string | 否 | 按目標優先順序解析 | 目標 skills 根，例如 `viking://~/skills` 或 `viking://agent/skills` |
| skills | List[str] | 否 | `[]` | 從目錄/Git 集合按目錄名選擇 Skill；空列表或 `["*"]` 選擇全部 |
| list_only | bool | 否 | False | 只列出來源中的 Skill，不安裝；需可解析的檔案、目錄或 Git 來源，不能使用內聯字典 |
| source_metadata | object | 否 | 自動生成 | 來源跟蹤資訊，儲存在 `.source.json`；不是 frontmatter 的 `metadata` |

至少提供 `data` 或 `temp_file_id`。當前服務端兩者同時存在時優先消費臨時上傳；客戶端應只傳一種，避免來源混淆。請求體不接受未知欄位。

**補充說明**：

- **本地檔案處理**：
  - Python SDK 和 CLI 可以直接接收本地 `SKILL.md` 檔案或目錄。處於 HTTP 模式時，它們會先自動上傳，再呼叫服務端 API。
  - 裸 HTTP 呼叫可以：
    1. 在 `data` 中直接傳結構化 skill 資料
    2. 在 `data` 中直接傳原始 `SKILL.md` 內容
    3. 直接傳 Git 倉庫或 GitHub tree URL，讓服務端解析來源
    4. 先呼叫 `POST /api/v1/resources/temp_upload` 上傳本地 `SKILL.md` 或目錄 ZIP，再呼叫 `POST /api/v1/skills` 並傳入 `temp_file_id`
  - `temp_upload` 預設使用本地臨時儲存；只有在明確需要分散式共享臨時上傳時，才傳 `upload_mode=shared`。Python HTTP client 可以在 `ovcli.conf` 中設定 `upload.mode = "shared"`；Rust `ov` CLI 則使用 `OPENVIKING_UPLOAD_MODE=shared`。
  - `POST /api/v1/skills` 不接受在 `data` 中直接傳宿主機本地路徑。
  - MCP 客戶端使用 `add_skill` 工具：`data` 傳 SKILL.md 文本，`path` 傳 Git URL 或本地路徑。傳本地路徑時工具返回一次性的簽名 `temp_upload` URL；客戶端把 SKILL.md 或 ZIP POST 上去後，服務端按 token 繫結的 `target_uri`、`skills`、`list_only` 完成安裝，上傳響應裡就是安裝結果。

- **目標規則**：
  - 新增使用 `target_uri` 指定 skills 根，不接受 `to`、`parent` 或 `root_uri` 作為 HTTP 請求欄位。CLI 的 `-p/--parent-auto-create` 對映到 `target_uri`。
  - 不支援 peer-scoped skill 根；actor peer 過濾只作用於 peer memories/resources，不作用於 peer skills。
  - 列出、讀取、刪除或搜尋技能時，使用家目錄別名 `viking://~/skills/...` 訪問自己的技能；無 uid 的 `viking://user/skills/...` 寫法會報錯並提示正確寫法。

- **支援的資料格式**：
  1. **字典（技能格式）**：包含 `name`、`description`、`content` 等字段
  2. **字典（MCP Tool 格式）**：包含 `name`、`description`、`inputSchema` 欄位，會自動檢測並轉換
  3. **字串（SKILL.md 內容）**：完整的 SKILL.md 內容
  4. **路徑（SDK/CLI 自動上傳）**：SKILL.md 檔案、Skill 目錄/集合或 ZIP；單個 Markdown 檔案不包含同目錄輔助檔案
  5. **Git URL**：倉庫或 Skill 子目錄；集合中的 `skills` 選擇器使用目錄名，非 frontmatter 名稱。已發現 `SKILL.md` 的目錄擁有整個子樹，內部巢狀 `SKILL.md` 作為附件保留，不再單獨發現

本地 `.json` 檔案不會自動解碼成結構化 Skill。應先解析 JSON 並把物件傳入 `data`，或改用帶 frontmatter 的 `SKILL.md`。

#### 3. 使用示例

單個 Skill 匯入預設返回 `task_id`。通過 [任務 API](17-tasks.md) 查詢狀態，任務為 `completed` 後再檢索；`wait=true` 則等待佇列處理並返回 `queue_status`。多 Skill 匯入返回 `installed` 陣列，每個結果獨立攜帶任務資訊，不保證批次原子性。`list_only=true` 只返回來源中的 `skills` 與 `total`，不建立匯入任務。

HTTP 欄位和 SDK 引數並非同名同層級：Python `add_skill(data, wait=False, timeout=None, options=None)` / `update_skill(skill_name, data, ...)` 將 `target_uri`、`telemetry` 放在 `options` 中；`skills`、`list_only`、`source_metadata`（新增）及 `from_source`（更新）等欄位放在 `options["extra"]` 中。TypeScript 使用 `targetUri` 和 `extra`，Go 使用 `TargetURI` 和 `Extra`。TypeScript 的本地路徑自動上傳僅適用於 Node.js。

```python
# 預覽本地集合；不寫入 OpenViking
listing = client.add_skill(
    "./skills",
    options={"extra": {"list_only": True}},
)
print(listing["skills"])

# 選擇目錄名，並安裝到共享根（需相應許可權）
result = client.add_skill(
    "./skills",
    wait=True,
    options={
        "target_uri": "viking://agent/skills",
        "extra": {"skills": ["search-web", "calculator"]},
    },
)
```

**TypeScript SDK**

```typescript
const result = await client.addSkill("./my-skill");
console.log(result.task_id);
```

**HTTP API**：

```
POST /api/v1/skills
Content-Type: application/json
```

```bash
# 使用內聯結構化資料
curl -X POST http://localhost:1933/api/v1/skills \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "data": {
      "name": "search-web",
      "description": "Search the web for current information",
      "content": "# search-web\n\nSearch the web for current information.\n\n## Parameters\n- **query** (string, required): Search query\n- **limit** (integer, optional): Max results, default 10"
    }
  }'

# 使用內聯 SKILL.md 內容
curl -X POST http://localhost:1933/api/v1/skills \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "data": "---\nname: my-skill\ndescription: My custom skill\n---\n\n# My Skill\n\nSkill content here."
  }'

# 使用 MCP Tool 格式（自動檢測並轉換）
curl -X POST http://localhost:1933/api/v1/skills \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "data": {
      "name": "calculator",
      "description": "Perform mathematical calculations",
      "inputSchema": {
        "type": "object",
        "properties": {
          "expression": {
            "type": "string",
            "description": "Mathematical expression to evaluate"
          }
        },
        "required": ["expression"]
      }
    }
  }'

# 使用本地檔案（需先使用 temp_upload 上傳）
TEMP_FILE_ID=$(
  curl -s -X POST http://localhost:1933/api/v1/resources/temp_upload \
    -H "X-API-Key: your-key" \
    -F "file=@./skills/my-skill/SKILL.md" \
  | jq -r '.result.temp_file_id'
)

curl -X POST http://localhost:1933/api/v1/skills \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d "{
    \"temp_file_id\": \"$TEMP_FILE_ID\"
  }"
```

**Python SDK**：

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(url="http://localhost:1933", api_key="your-key")
client.initialize()

# 方式 1：使用結構化技能資料
skill = {
    "name": "search-web",
    "description": "Search the web for current information",
    "content": """# search-web

Search the web for current information.

## Parameters
- **query** (string, required): Search query
- **limit** (integer, optional): Max results, default 10
"""
}
result = client.add_skill(data=skill)
print(f"Added: {result['root_uri']}")

# 方式 2：使用 MCP Tool 格式（自動檢測並轉換）
mcp_tool = {
    "name": "calculator",
    "description": "Perform mathematical calculations",
    "inputSchema": {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Mathematical expression to evaluate"
            }
        },
        "required": ["expression"]
    }
}
result = client.add_skill(data=mcp_tool)
print(f"Added: {result['uri']}")

# 方式 3：從本地 SKILL.md 檔案新增
result = client.add_skill(data="./skills/search-web/SKILL.md")
print(f"Added: {result['uri']}")

# 方式 4：從包含 SKILL.md 的目錄新增（輔助檔案會一併包含）
result = client.add_skill(data="./skills/code-runner/")
print(f"Added: {result['uri']}")
print(f"Auxiliary files: {result['auxiliary_files']}")

# 查詢上一次匯入任務的狀態
print(client.get_task(result["task_id"]))
```

**Go SDK**

```go
result, err := client.AddSkill(ctx, "./skills/my-skill/", nil)
if err != nil {
    return err
}
fmt.Println(result["task_id"])
```

**CLI**：

`ov add-skill` 與 `ov skills add` 使用同一套引數和匯入流程。
技能集合可以用 `--list` 檢視、`--skill` 選擇；批次匯入需要確認，或使用 `--yes`。

```bash
# 從獨立 skills 分支匯入一個技能；也可以寫成 ov skills add
ov add-skill https://github.com/volcengine/OpenViking/tree/skills/llm-wiki

# 檢視本地技能集合，再選擇匯入
ov add-skill ./openviking/builtin_skills/compile --list
ov add-skill ./openviking/builtin_skills/compile --skill llm-wiki daily-report --yes

# 新增技能（從檔案或目錄）
ov add-skill ./skills/search-web/SKILL.md
ov add-skill ./skills/code-runner/

# 指定共享目標，並等待處理完成
ov skills add ./skills/code-runner/ -p viking://agent/skills --wait

# 使用提交時返回的 task_id 查詢進度
ov task status TASK_ID

# 使用 JSON 輸出格式
ov add-skill ./skills/my-skill/ -o json
```

**響應示例**：

**HTTP API 響應 (JSON)**：
```json
{
  "status": "ok",
  "result": {
    "status": "success",
    "root_uri": "viking://user/alice/skills/my-skill",
    "uri": "viking://user/alice/skills/my-skill",
    "name": "my-skill",
    "auxiliary_files": 2,
    "task_id": "uuid-xxx"
  }
}
```

**CLI 響應（預設表格格式）**：
```
Note: Skill processing may continue in the background.
Use 'ov task status <task_id>' to check progress, or 'ov task list' to see all tasks.
status          success
root_uri        viking://user/alice/skills/my-skill
uri             viking://user/alice/skills/my-skill
name            my-skill
auxiliary_files 2
task_id         uuid-xxx
```

**CLI 響應（JSON 格式，使用 -o json）**：
```json
{
  "status": "success",
  "root_uri": "viking://user/alice/skills/my-skill",
  "uri": "viking://user/alice/skills/my-skill",
  "name": "my-skill",
  "auxiliary_files": 2,
  "task_id": "uuid-xxx"
}
```

**欄位說明**：

| 欄位 | 型別 | 說明 |
|------|------|------|
| `status` | string | 成功匯入結果為 `success`；同步失敗使用 HTTP 錯誤響應 |
| `root_uri` | string | 技能在 OpenViking 中的 canonical 最終 URI（同 `uri`）|
| `uri` | string | 技能在 OpenViking 中的 canonical 最終 URI（同 `root_uri`）|
| `name` | string | 技能名稱 |
| `auxiliary_files` | number | 技能附帶的輔助檔案數量 |
| `task_id` | string | 預設非同步模式下返回的後臺處理任務 ID；通過任務 API 查詢最終狀態 |
| `queue_status` | object | `wait=True` 時按佇列名（如 `Semantic`、`Embedding`）返回 `processed`、`requeue_count`、`error_count` 和 `errors` |

#### 4. 錯誤處理

**同步處理錯誤**：

如果 skill 解析或處理同步失敗，裸 HTTP 會返回標準錯誤 envelope，並使用非 2xx HTTP 狀態碼：

```json
{
  "status": "error",
  "error": {
    "code": "PROCESSING_ERROR",
    "message": "Skill parse error: invalid skill metadata"
  }
}
```

Python HTTP SDK 會把該響應對映為對應異常（`ProcessingError`）。

具體錯誤碼取決於失敗階段，例如名稱或目標引數無效為 `INVALID_ARGUMENT` / `INVALID_URI`，找不到 Skill 為 `NOT_FOUND`，完整性清單超限為 `RESOURCE_EXHAUSTED`，等待超時為 `DEADLINE_EXCEEDED`。`wait=false` 返回成功只表示同步匯入階段完成，後臺失敗需通過任務狀態確認。標準響應可能帶可選 `telemetry` / `profile`，沒有通用 `time` 欄位；SDK 通常直接返回 `result` 物件。

## 技能管理操作

Python HTTP SDK 和 Go SDK 都暴露專用技能管理方法。Python 方法包括
`list_skills`、`find_skills`、`validate_skill`、`get_skill`、`update_skill`
和 `delete_skill`；Go 方法包括 `ListSkills`、`FindSkills`、`ValidateSkill`、
`GetSkill`、`UpdateSkill` 和 `DeleteSkill`。通用檔案系統、內容和檢索方法仍可用於 URI 級訪問。

### 列出技能

`GET /api/v1/skills` 的查詢引數為 `node_limit=1000` 和可選 `target_uri`。省略目標時合併私有與共享根，同名 Skill 都保留，以 `root_uri` 區分。當前服務端實際固定每個根的目錄掃描 `node_limit=1000`，尚未把請求的 `node_limit` 傳到掃描層，不應依賴它作為全域條數限制或分頁引數。

**Python SDK**：

```python
skills = client.list_skills(node_limit=1000)
for skill in skills["skills"]:
    print(skill["name"])
```

**TypeScript SDK**

```typescript
const skills = await client.listSkills();
console.log(skills);
```

**Go SDK**：

```go
skills, err := client.ListSkills(ctx, nil)
_ = skills
```

**HTTP API**：

```bash
curl -X GET "http://localhost:1933/api/v1/skills?node_limit=1000" \
  -H "X-API-Key: your-key"
```

### 讀取技能

`GET /api/v1/skills/{skill_name}`：

| 查詢引數 | 預設值 | 含義 |
|----------|--------|------|
| `target_uri` | 未指定 | 優先查詢的 skills 根 |
| `level` | 未指定 | `0` 返回 abstract，`1` 返回 overview，`2` 返回 SKILL.md；未指定時返回三個層級 |
| `include_content` | 未指定 | `true` 額外返回正文；`false` 在未指定 level 時關閉正文；`level=2` 始終返回正文 |
| `include_files` | `true` | 返回檔案和目錄清單，預設不計算雜湊 |
| `include_integrity` | `false` | 在樹鎖內讀取快照；與 `include_files=true` 一起使用才生成檔案雜湊與 revision |
| `include_source` | `false` | 返回 `.source.json` 來源資訊；沒有記錄時 `source.tracked=false` |

按名稱讀取、更新、刪除共用查詢邏輯：預設先找使用者私有 Skill，再找共享 Skill；顯式指定 `target_uri` 時先找目標根，未找到時仍會回退到私有/共享根。當前 `target_uri` 對這三個操作不是嚴格的“僅限該根”保證。處理同名 Skill 時，應先讀取並檢查返回的 `root_uri`。

**Python SDK**：

```python
skill = client.get_skill(
    skill_name="search-web",
    include_content=True,
    include_files=True,
)
print(skill["name"])
print(skill.get("content"))
```

**TypeScript SDK**

```typescript
const skill = await client.getSkill("my-skill");
console.log(skill);
```

**Go SDK**：

```go
skill, err := client.GetSkill(ctx, "search-web", &openviking.GetSkillOptions{
    IncludeContent: openviking.Bool(true),
    IncludeFiles:   openviking.Bool(true),
})
_ = skill
```

**HTTP API**：

```bash
curl -X GET "http://localhost:1933/api/v1/skills/search-web?include_content=true&include_files=true" \
  -H "X-API-Key: your-key"
```

### 完整性清單與遠端使用

遠端 Harness 需要下載指令碼或二進位制檔案時，可先請求完整性清單：

```python
skill = client.get_skill(
    "search-web",
    target_uri="viking://~/skills",
    include_content=True,
    include_files=True,
    include_integrity=True,
)
print(skill["root_uri"], skill["revision"], skill["content_sha256"])
for entry in skill["files"]:
    if not entry["is_dir"]:
        print(entry["path"], entry["uri"], entry["size"], entry["sha256"])
```

HTTP 對應查詢為 `GET /api/v1/skills/search-web?include_content=true&include_files=true&include_integrity=true`。當前 Python SDK 暴露 `include_integrity`；TypeScript、Go 的 `getSkill` / `GetSkill` options 及 `ov skills show` 暫無此選項，需要此能力時使用 HTTP 或 Python SDK。

| 返回欄位 | 含義 |
|----------|------|
| `content_sha256` | 返回的 SKILL.md 正文的 SHA-256；只要返回 `content` 就有該欄位，不要求開啟完整性模式 |
| `revision` | 根據排序後的包清單（路徑、目錄標記、檔案大小與雜湊）計算的版本標識，不是 Git commit 或 metadata.version |
| `files[].name/path/uri` | 條目名稱、包內相對路徑、canonical URI |
| `files[].is_dir/kind` | 目錄標記；kind 為 `definition`、`summary`、`auxiliary` 或 `directory` |
| `files[].size/sha256` | 完整性模式下非目錄檔案的位元組數與 SHA-256；普通清單不包含這些欄位 |

清單包含 `SKILL.md`、摘要和輔助檔案/目錄，不包含 `.source.json`。完整性 API 上限為 **512 個條目（包含目錄）、單檔案 16 MiB、總檔案位元組數 64 MiB**，讀取併發為 8；超限返回 `RESOURCE_EXHAUSTED`。正文、清單和 revision 在同一次樹鎖保護的讀取中取得，但後續下載仍可能遇到更新，消費方應校驗檔案雜湊並複查 revision。

檢索與 `get_skill` 只返回內容和清單，不會執行指令碼或把檔案安裝到 Agent 沙箱。Harness 可按需遠端讀文本，在工具需要本地路徑時下載資源。VikingBot 的完整流程見 [Skills](../../../bot/docs/zh/concepts/06-skills.md)。MCP 客戶端通過 `find` 工具傳 `context_type="skill"` 得到同樣的包級行為，見 [MCP 整合](../guides/06-mcp-integration.md)。

### 搜索技能

`POST /api/v1/skills/find` 請求體：

| 引數 | 預設值 | 含義 |
|------|--------|------|
| `query` | 必填 | 檢索文本 |
| `limit` | `10` | 最多返回的不同 Skill 數量，包含私有與共享空間的合併結果 |
| `score_threshold` | `null` | 最低分數，未指定時使用底層檢索預設行為 |
| `level` | `null` | 參與匹配的層級列表，例如 `[0]`；未指定時不限制層級，與讀取介面的單個整數不同 |
| `target_uri` | `null` | 限定檢索範圍；省略時分別檢索私有與共享根 |
| `telemetry` | `false` | 遙測配置 |

包內命中按完整 Skill 根 URI 合併，使用最高最終得分排序，再擷取 `limit` 個 Skill。不同空間的同名 Skill 分別保留。`total` 是本次返回陣列長度，不是所有匹配項的總數。

每個 Skill 返回包內最終得分最高的一條命中。`uri`、`level`、`score`、`abstract` 直接使用該命中的原有欄位，不增加額外返回欄位。按 Skill 合併和補頁用於專用 `skills/find`，以及只傳 `context_type="skill"` 的 MCP `find` 工具；REST `find` / `search` 仍按命中內容返回。MCP `search` 同樣按命中內容檢索，只在渲染答案時把同一個包合成一條。

| 返回欄位 | 含義 |
| --- | --- |
| `uri` / `level` | 實際命中地址及層級：L0 指向 `.abstract.md`，L1 指向 `.overview.md`，L2 指向具體檔案 |
| `score` | 該命中的最終得分，也是所屬 Skill 的排序得分 |
| `abstract` | 該命中記錄已有的摘要，沿用原搜尋規則 |
| `name` / `description` / `tags` / `allowed_tools` | 專用 `skills/find` 從 Skill 主目錄單獨讀取的後設資料 |
| `root_uri` / `skill_md_uri` | 專用 `skills/find` 返回的 Skill 根目錄和主 `SKILL.md` 地址 |

專用 `skills/find` 的 `uri` 從原先的包根地址調整為實際命中地址；MCP `find` 工具的行為不同，它把每條 Skill 命中改寫成 `<包根>/SKILL.md`。列表和按名稱讀取介面保持原樣。`level=[2]` 只讓檔案參與匹配，返回的 `level` 為 `2`、`uri` 指向包內得分最高的檔案。

通用檢索中 `read_content=true` 繼續讀取實際返回的 `uri`——對只傳 `context_type="skill"` 的 MCP `find` 來說，這個 URI 是包的 `SKILL.md`，不是實際命中的檔案。專用 `skills/find` 不支援該引數。

上表的 URI 規則適用於語義檢索。通用 `find` 僅按 `filter` 篩選時，仍保留索引記錄的 URI、返回 `score=0`，不為 L0、L1 補摘要檔案字尾；MCP `find` 遇到這種呼叫也留在通用路徑上，因為包級檢索必須帶檢索文本，但仍會把每條 skill 命中改寫成它的 `SKILL.md`。

搜尋範圍、層級和許可權限制先作用於包內命中，再合併 Skill；根目錄也必須可訪問。

**Python SDK**：

```python
results = client.find_skills(query="search the internet", limit=5)

for skill in results["skills"]:
    print(skill["name"], skill["score"])
```

**TypeScript SDK**

```typescript
const skills = await client.findSkills("database migration");
console.log(skills);
```

**Go SDK**：

```go
results, err := client.FindSkills(ctx, "search the internet", &openviking.FindSkillsOptions{
    Limit: 5,
})
_ = results
```

**HTTP API**：

```bash
curl -X POST http://localhost:1933/api/v1/skills/find \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "query": "search the internet",
    "limit": 5
  }'
```

### 校驗和更新技能

`POST /api/v1/skills/validate` 接收 `data`（必填的結構化資料或完整 SKILL.md 文本）、`strict=false`、`source_path=null`、`skill_dir_name=null` 和 `target_uri=null`。`source_path` 僅作為報告資訊，不會讓服務端讀取本地檔案；當前 `target_uri` 被接受但不參與格式校驗。SDK 的 `validate_skill` 也不自動上傳路徑，應先讀取檔案內容。

缺少名稱/描述和無效 YAML 會產生 errors。名稱/目錄不一致、名稱長度或字元不合規、描述超過 1024 字元在普通模式為 warnings，`strict=true` 時升級為 errors；正文超過 500 行在嚴格模式仍只是 warning。該介面不安裝 Skill、不驗證工具是否已註冊或依賴是否可執行，不能替代實際匯入與 Harness 檢查。

`PUT /api/v1/skills/{skill_name}` 替換整個包，接收以下請求體：

| 引數 | 預設值 | 含義 |
|------|--------|------|
| `data` / `temp_file_id` | 未指定 | 新內容或上傳包，使用方式與新增相同 |
| `from_source` | `false` | 根據已記錄的 Git 來源更新；不能與 data/temp_file_id 同用 |
| `target_uri` | 未指定 | 優先查詢的 skills 根，參見讀取介面的回退規則 |
| `source_metadata` | 自動生成 | 更新來源資訊 |
| `wait` / `timeout` | `false` / `null` | 是否等待後臺處理及超時秒數 |
| `telemetry` | `false` | 遙測配置 |

必須提供新內容/上傳包，或設 `from_source=true`。新內容的名稱必須與 URL 中的 `skill_name` 一致；更新不是重新命名或區域性 patch。先解析並檢查新包，再備份替換；同步失敗會嘗試恢復舊包。需保留的輔助檔案應隨新包一起提交。

更新的檔案、隱私配置和任務準備完成後才啟動後臺。需要恢復舊包時，包括 `wait=true` 超時，先取消本次摘要和索引任務，確認已開始的寫入退出，再恢復原檔案、索引及隱私配置；恢復失敗會明確報告。超時響應可能晚於 `timeout`，但只等待取消收尾，不繼續處理完整包。`wait=false` 已成功返回後的後臺失敗不自動恢復；新增 Skill 的等待超時仍只結束等待。

**Python SDK**：

```python
validated = client.validate_skill(data={"name": "search-web", "description": "..."})
print(validated["valid"], validated["errors"], validated["warnings"])
updated = client.update_skill(
    skill_name="search-web",
    data="./skills/search-web",
)
```

**TypeScript SDK**

```typescript
const result = await client.validateSkill({
  name: "search-web",
  description: "Search the web for current information",
  content: "# search-web\n\nSearch the web for current information.",
});
console.log(result);
```

**Go SDK**：

```go
validated, err := client.ValidateSkill(ctx, map[string]any{
    "name":        "search-web",
    "description": "...",
}, nil)
updated, err := client.UpdateSkill(ctx, "search-web", "./skills/search-web", nil)
_, _ = validated, updated
```

**HTTP API**：

```bash
# 校驗技能資料
curl -X POST http://localhost:1933/api/v1/skills/validate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"data": {"name": "search-web", "description": "..."}}'

# 使用新的技能內容替換現有技能
curl -X PUT http://localhost:1933/api/v1/skills/search-web \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "data": {
      "name": "search-web",
      "description": "Search the web for current information",
      "content": "# search-web\n\nUpdated instructions."
    }
  }'
```

從來源更新僅適用於已記錄 Git 來源的 Skill，使用記錄的倉庫、ref 與子目錄重新獲取內容；本地上傳沒有可自動拉取的 Git 來源：

```python
updated = client.update_skill(
    "search-web",
    data=None,
    wait=True,
    options={"extra": {"from_source": True}},
)
```

```bash
curl -X PUT http://localhost:1933/api/v1/skills/search-web \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"from_source": true, "wait": true}'
```

### 刪除技能

`DELETE /api/v1/skills/{skill_name}` 接受可選查詢引數 `target_uri`，遞迴刪除解析到的 Skill 包，並處理關聯 Skill privacy 配置。目標根回退規則與讀取相同。

**Python SDK**：

```python
client.delete_skill(skill_name="old-skill")
```

**TypeScript SDK**

```typescript
await client.deleteSkill("my-skill");
```

**Go SDK**：

```go
deleted, err := client.DeleteSkill(ctx, "old-skill")
_ = deleted
```

**HTTP API**：

```bash
curl -X DELETE "http://localhost:1933/api/v1/skills/old-skill" \
  -H "X-API-Key: your-key"
```

### CLI 管理命令

```bash
ov skills list -p viking://~/skills
ov skills find "search the internet" --level 0 --limit 5 -p viking://~/skills
ov skills show search-web --level 2 --files --source -p viking://~/skills
ov skills validate ./skills/search-web --strict
ov skills update search-web -p viking://~/skills --wait --yes
ov skills remove old-skill -p viking://~/skills --yes
```

`list/find/show` 的 `-p` 長選項為 `--uri`；`add/update/remove` 為 `--parent-auto-create`。`show` 預設返回各文本層級，檔案清單需 `--files`，來源需 `--source`。`validate` 在本地校驗，不安裝；`update` 從記錄的 Git 來源重新整理，非 Git 來源在互動模式可要求補充路徑/URL。

`ov skills update` 不帶名稱時嘗試更新全部已安裝 Skill，並在 `skipped` 中報告無法更新項。`remove` 不帶名稱時進入互動選擇，`--all` 才表示全部。更新和刪除需要確認，指令碼中顯式使用 `--yes`。

### 技能管理響應

列出和搜尋都返回 `skills` 陣列與 `total`。未指定 `target_uri` 時使用 `root_uris` 表示使用者私有與 Agent 共享兩個檢索根；指定後返回單個 `root_uri`。

```json
{
  "status": "ok",
  "result": {
    "root_uris": [
      "viking://user/default/skills",
      "viking://agent/skills"
    ],
    "skills": [
      {
        "type": "skill",
        "name": "search-web",
        "uri": "viking://user/default/skills/search-web",
        "root_uri": "viking://user/default/skills/search-web",
        "skill_md_uri": "viking://user/default/skills/search-web/SKILL.md",
        "description": "Search the web for current information",
        "tags": [],
        "allowed_tools": [],
        "score": 0.87,
        "match_reason": "semantic",
        "level": 0
      }
    ],
    "total": 1
  }
}
```

讀取單個技能時，`result` 返回上述技能後設資料，並按 `level` 與 `include_*` 引數補充 `abstract`、`overview`、`content`、`files` 和 `source`。

校驗返回 `valid`、`strict`、規範化後的後設資料、`body_lines`、`errors` 和 `warnings`。校驗不通過時仍返回成功響應包，但 `valid=false`：

```json
{
  "status": "ok",
  "result": {
    "valid": false,
    "strict": false,
    "name": "search-web",
    "description": "",
    "tags": [],
    "allowed_tools": [],
    "body_lines": 0,
    "errors": [
      {
        "rule": "description_required",
        "message": "description is required",
        "field": "description"
      }
    ],
    "warnings": []
  }
}
```

更新成功時返回與 `add_skill` 相同的處理結果，並額外包含 `"action": "update"`。刪除成功返回：

```json
{
  "status": "ok",
  "result": {
    "name": "old-skill",
    "uri": "viking://user/default/skills/old-skill",
    "root_uri": "viking://user/default/skills/old-skill",
    "estimated_deleted_count": 4,
    "privacy_deleted": false
  }
}
```

`estimated_deleted_count` 僅在底層檔案系統提供刪除數量估算時出現。

## 最佳實踐

### 清晰的描述

```python
# 好 - 具體且可操作
skill = {
    "name": "search-web",
    "description": "Search the web for current information using Google",
    # 其他技能字段
}

# 不夠好 - 過於模糊
skill = {
    "name": "search",
    "description": "Search",
    # 其他技能字段
}
```

### 命名一致性建議

技能名稱使用 kebab-case：

- `search-web`（推薦）
- `searchWeb`（避免）
- `search_web`（避免）

## 相關文件

- [資源管理](02-resources.md) - 資源的新增和管理
- [檔案系統](03-filesystem.md) - 檔案和目錄操作
- [上下文型別](../concepts/02-context-types.md) - 技能概念
- [檢索](06-retrieval.md) - 查詢技能
- [會話](05-sessions.md) - 跟蹤技能使用情況
- [VikingBot Skills](../../../bot/docs/zh/concepts/06-skills.md) - 本地/遠端 Skill 的啟用、metadata 與執行
