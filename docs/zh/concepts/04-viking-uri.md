# Viking URI

Viking URI 是 Business Data Platform 中所有內容的統一資源識別符號。

## 格式

```
viking://{scope}/{path}
```

- **scheme**: 始終為 `viking`
- **scope**: 頂級名稱空間（`resources`、`user`、`agent`；`temp`、`queue` 和 `upload` 為內部作用域）
- **path**: 作用域內的資源路徑

## 作用域

| 作用域 | 說明 | 生命週期 | 可見性 |
|--------|------|----------|--------|
| **resources** | 獨立資源/客觀知識 | 長期 | account 全域 |
| **user** | 使用者級資料，包括 session | 長期 / 會話生命週期 | 當前使用者 |
| **agent** | agent 能力與配置（技能、端點、工具、支付等） | 長期 | account 全域 |
| **queue** | 處理佇列 | 臨時 | 內部 |
| **temp** | 臨時檔案 | 解析期間 | 內部 |
| **upload** | 臨時上傳檔案 | 臨時 | 內部 |

公開 API 和 CLI 的檔案系統/內容操作接受公開作用域 `resources`、`user` 和 `agent`，
以及根 URI `viking://`。`session` 保留為 user session 路徑的向後相容別名；
新 session 資料位於 `viking://user/{user_id}/sessions`。
`temp`、`queue` 和 `upload` 是內部實現作用域，不能通過公開 API 的 URI 引數直接訪問。

### Home 別名 `~`

`~` 是當前呼叫方使用者根目錄的服務端別名。`viking://~` 展開為 `viking://user/{user_id}`，
`viking://~/memories/note.md` 展開為 `viking://user/{user_id}/memories/note.md`，
其中 `{user_id}` 取自請求的認證身份——同一個字串對不同調用方指向不同目錄。

- 通用：所有控制面（REST API、`ov` CLI、SDK、MCP）都接受，可用於任何接受公開作用域 URI 的位置。
- 僅識別第 0 段：`viking://resources/~/x` 和 `viking://user/alice/~/x` 中的 `~` 仍是字面路徑段。
- 接受但不宣傳：`~` 不屬於公開作用域列表，`Invalid scope ... Must be one of:` 錯誤資訊中不會出現它。
- 響應始終回顯展開後的 canonical URI，不會返回 `viking://~`；持久化資料（向量記錄、watch key）
  同樣保持 canonical 形式。
- 需要認證請求身份。所有請求角色（包括 root）都使用該身份的有效 `user_id` 展開；要求 URI
  已是 canonical 形式的場景（內部儲存路徑、沒有請求上下文的後臺任務）仍會直接拒絕該別名，
  而不會猜測使用者。
- 取代已移除的無 uid 短寫：`memories`、`resources`、`skills`、`peers`、`privacy`、`sessions`
  的 `viking://user/<segment>/...` 寫法會在 USER / ADMIN 請求入口被拒絕，錯誤資訊中會給出
  `viking://~/...` 的替代寫法。

## 初始目錄

摒棄傳統的扁平化資料庫思維，將所有上下文組織為一套檔案系統。Agent 不再僅是通過向量搜尋來找資料，而是可以通過確定性的路徑和標準檔案系統指令來定位和瀏覽資料。每個上下文或目錄分配唯一的 URI 標識字串，格式為 viking://{scope}/{path}，讓系統能精準定位並訪問儲存在不同位置的資源。

## 文件 ID

除 URI 之外，每個檔案會被自動分配一個穩定的 `id`，作為其在 VikingDB 中向量記錄的主鍵。對於 level 2（常規檔案）記錄，該 id 按 `md5(f"{account_id}:{uri}")` 確定性計算，由 `stat()` 等後設資料介面返回。呼叫方可憑此 id 直接交叉引用向量索引條目，無需額外查詢。id 以 account 為作用域，當檔案被移動到其他 URI 時 id 會隨之改變（URI 遷移過程中向量記錄會重新計算主鍵）。目錄不返回單一 `id`，因為一個目錄在多個語義層（L0 abstract、L1 overview、L2）下可能對應多條記錄，每條各有自己的 id。

```
viking://
├── user/
│   └── {user_id}/
│       ├── profile.md        # 使用者畫像
│       ├── memories/         # 使用者記憶
│       ├── resources/        # 使用者私有資源
│       ├── skills/           # 使用者技能
│       ├── peers/
│       │   └── {peer_id}/
│       │       ├── memories/  # 關於某個互動物件的記憶
│       │       └── resources/ # 歸屬於該 peer 的資源
│       └── sessions/         # 使用者會話
│           └── {session_id}/
│               ├── .abstract.md
│               ├── .overview.md
│               ├── .meta.json
│               ├── messages.jsonl
│               ├── tools/
│               └── history/
│
├── agent/                     # agent 能力與配置（全域）
│   ├── skills/                # 技能定義
│   ├── endpoints/             # 通訊端點（a2a, anp 等）（規劃中）
│   ├── tools/                 # 工具配置（mcp 等）（規劃中）
│   └── payments/              # 支付配置（ap2 等）（規劃中）
│
└── resources/{project}/      # 資源工作區
```

## URI 示例

### 資源

```
viking://resources/                           # 所有資源
viking://resources/my-project/                # 專案根目錄
viking://resources/my-project/docs/           # 文件目錄
viking://resources/my-project/docs/api.md     # 具體檔案
```

### 使用者資料

```
viking://user/                                # 所有使用者空間的容器（user key 只能列出自己的空間）
viking://~/                                   # 自己的使用者根目錄（展開為 viking://user/{user_id}/）
viking://~/memories/                          # 自己的所有記憶
viking://~/memories/preferences/              # 使用者偏好
viking://~/memories/preferences/coding        # 具體偏好
viking://~/memories/entities/                 # 實體記憶
viking://~/memories/events/                   # 事件記憶
viking://~/resources/                         # 自己的私有資源
viking://~/resources/docs/                    # 自己的私有資源目錄
viking://user/{user_id}/memories/             # 顯式使用者路徑（可寫自己的 id；訪問他人需 admin/root）
```

`viking://resources/...` 是當前 account 的共享區，可通過 [資源訪問控制（ACL）](./15-acl.md) 細化目錄或檔案許可權。`viking://user/{user}/resources/...` 是個人私有區；分享資源需要將其移動到共享區。

### 使用者技能和 peer 內容

```
viking://~/skills/                            # 自己的技能
viking://~/skills/search-web                  # 某個技能
viking://~/memories/                          # 自己的記憶
viking://~/memories/cases/                    # 用於訓練和評估的任務案例
viking://~/memories/trajectories/             # 可複用的任務執行軌跡
viking://~/memories/experiences/              # 從執行結果中提煉的經驗
viking://user/{user_id}/peers/{peer_id}/memories/
viking://user/{user_id}/peers/{peer_id}/resources/
```

家目錄別名 `viking://~/...` 會按當前請求身份解析。Business Data Platform 會在儲存和檢索前將它
展開為顯式名稱空間路徑 `viking://user/{user_id}/...`，響應中始終回顯展開後的形式。

舊的無 uid 寫法——`viking://user/memories/...` 以及 `resources`、`skills`、`peers`、
`privacy`、`sessions` 的同類寫法——在請求入口不再被接受，這類請求會報錯，並在錯誤資訊中
提示改用 `viking://~/...`。`viking://user` 本身是所有使用者空間的容器，而不是自己根目錄的
快捷方式：使用 user key 列出它時只會看到自己的空間。

`{user_id}` 和 `{peer_id}` 等身份路徑片段必須是安全的單段標識，例如
`alice` 或 `web-visitor-alice`。

### agent 能力與配置

```
viking://agent/skills/search-web                    # 某個技能定義
viking://agent/skills/                              # 所有技能定義
viking://agent/endpoints/                           # 通訊端點（a2a, anp 等）（規劃中）
viking://agent/tools/mcp/                           # MCP 工具配置（規劃中）
viking://agent/payments/ap2/                        # 支付配置（規劃中）
```

`viking://agent/...` 是 account 內公共能力與配置目錄，可包含 skills、endpoints、tools、payments 等子目錄。
目錄名不表示 Agent 身份，`actor_peer_id` 不過濾該目錄；共享範圍限於當前帳號。
Peer 資料使用 `viking://user/<user_id>/peers/<peer_id>/...`。

### 會話資料

```
viking://user/{user_id}/sessions/{session_id}/          # 會話根目錄
viking://user/{user_id}/sessions/{session_id}/messages  # 會話訊息
viking://user/{user_id}/sessions/{session_id}/tools     # 工具執行
viking://user/{user_id}/sessions/{session_id}/history   # 歸檔歷史
viking://~/sessions/{session_id}/                       # 自己的會話（家目錄別名寫法）
```

`viking://session/{session_id}` 會作為當前使用者 session 路徑的向後相容別名被接受。
它不是新會話資料的獨立儲存根。

## 路徑變數

Viking URI 支援路徑變數用於動態路徑生成。這對於按時間序列組織資料（如郵件、日誌、日報等）特別有用。

### 變數語法

```
{namespace:key}
```

- **namespace**: 變數提供者名稱空間（如 `calendar`、`env`、`user`）
- **key**: 名稱空間內的變數名

### 日曆變數

`calendar` 名稱空間提供日期相關變數：

| 變數 | 說明 | 示例（2026-05-07） |
|------|------|----------------------|
| `{calendar:today}` | 完整日期路徑 | `2026/05/07` |
| `{calendar:yesterday}` | 昨天的日期路徑 | `2026/05/06` |
| `{calendar:tomorrow}` | 明天的日期路徑 | `2026/05/08` |
| `{calendar:year}` | 年份 | `2026` |
| `{calendar:month}` | 月份（帶前導零） | `05` |
| `{calendar:day}` | 日期（帶前導零） | `07` |
| `{calendar:ym}` | 年/月 | `2026/05` |
| `{calendar:quarter}` | 季度（Q1-Q4） | `Q2` |
| `{calendar:yq}` | 年/季度 | `2026/Q2` |
| `{calendar:week}` | ISO 週數（帶前導零） | `18` |
| `{calendar:yw}` | 年/ISO 周 | `2026/w18` |

### 使用示例

```python
# 按日期組織郵件
viking://resources/emails/{calendar:today}/inbox
# 渲染為：viking://resources/emails/2026/05/07/inbox

# 檢視昨天的日誌
viking://resources/logs/{calendar:yesterday}/app.log
# 渲染為：viking://resources/logs/2026/05/06/app.log

# 預上傳明天的任務
viking://resources/tasks/{calendar:tomorrow}/todo.md
# 渲染為：viking://resources/tasks/2026/05/08/todo.md

# 月度日誌
viking://resources/logs/{calendar:year}/{calendar:month}/app.log
# 渲染為：viking://resources/logs/2026/05/app.log

# 每日快照
viking://resources/snapshots/{calendar:today}/
# 渲染為：viking://resources/snapshots/2026/05/07/
```

### 解析過程

路徑變數在 API 執行時**伺服器端**進行解析。CLI/SDK 原樣傳遞 URI 模板，伺服器根據當前上下文（時間、認證使用者等）渲染為具體路徑。

### CLI 使用

```bash
# 新增今天的郵件 --parent-auto-create 可以簡寫為 -p
ov add-resource --parent-auto-create "viking://resources/emails/{calendar:today}/inbox" ./emails/*.eml

# 讀取昨天的日誌
ov read "viking://resources/logs/{calendar:yesterday}/app.log"

# 準備明天的任務
ov write "viking://resources/tasks/{calendar:tomorrow}/todo.md" --content "規劃一天"

# 上傳月度報告 --parent-auto-create 可以簡寫為 -p
ov add-resource --parent-auto-create "viking://resources/reports/{calendar:ym}" ./report.pdf
```

## 目錄結構

```
viking://
├── resources/                    # 獨立資源（客觀知識，禁止儲存非知識類配置）
│   └── {project}/
│       ├── .abstract.md          # 摘要
│       ├── .overview.md          # 概述
│       └── {files...}
│
├── agent/                        # agent 能力與配置（全域共享，account 粒度）
│   ├── skills/                   # 技能定義
│   ├── endpoints/                # 通訊端點（a2a, anp 等）（規劃中）
│   ├── tools/                    # 工具配置（mcp 等）（規劃中）
│   └── payments/               # 支付配置（ap2 等）（規劃中）
│
├── user/{user_id}/
│   ├── profile.md                # 使用者基本資訊
│   ├── memories/
│   │   ├── preferences/          # 按主題
│   │   ├── entities/             # 每條獨立
│   │   └── events/               # 每條獨立
│   ├── resources/
│   │   └── {project}/
│   ├── skills/                   # 使用者技能（與 viking://agent/skills/ 相容）
│   └── peers/{peer_id}/
│       ├── memories/
│       └── resources/
│
└── user/{user_id}/sessions/{session_id}/
    ├── messages.jsonl
    ├── tools/
    └── history/
```

`viking://agent/...` 是 account 內公共目錄，不包含 Agent ID 身份層。
`actor_peer_id` 只過濾當前使用者的 `peers` 集合，公共目錄仍按帳號隔離。

## URI 操作

### 解析

```python
from openviking_cli.utils.uri import VikingURI

uri = VikingURI("viking://resources/docs/api")
print(uri.scope)      # "resources"
print(uri.full_path)  # "resources/docs/api"
```

### 構建

```python
# 拼接路徑
base = "viking://resources/docs/"
full = VikingURI(base).join("api.md").uri  # viking://resources/docs/api.md

# 父目錄
uri = "viking://resources/docs/api.md"
parent = VikingURI(uri).parent.uri  # viking://resources/docs
```

## API 使用

### 指定作用域搜索

```python
# 僅在資源中搜索
results = client.find(
    query="認證",
    target_uri="viking://resources/",
)

# 僅在自己的資源中搜索
results = client.find(
    query="私有專案筆記",
    target_uri="viking://~/resources/"
)

# 僅在自己的記憶中搜索
results = client.find(
    query="編碼偏好",
    target_uri="viking://~/memories/"
)

# 僅在自己的技能中搜索
results = client.find(
    query="網路搜尋",
    target_uri="viking://~/skills/"
)
```

### 檔案系統操作

```python
# 列出目錄
entries = await client.ls(uri="viking://resources/")

# 讀取檔案
content = await client.read(uri="viking://resources/docs/api.md")

# 獲取摘要
abstract = await client.abstract(uri="viking://resources/docs/")

# 獲取概覽
overview = await client.overview(uri="viking://resources/docs/")
```

## 特殊文件

每個目錄可能包含特殊檔案：

| 文件 | 用途 |
|------|------|
| `.abstract.md` | L0 摘要（~100 tokens） |
| `.overview.md` | L1 概覽（~2k tokens） |
| `` | 相關資源 |
| `.meta.json` | 後設資料 |

## 最佳實踐

### 目錄使用尾部斜槓

```python
# 目錄
"viking://resources/docs/"

# 文件
"viking://resources/docs/api.md"
```

### 作用域特定操作

```python
# 新增到 account 共享資源作用域
await client.add_resource(url, to="viking://resources/project/")

# 新增到自己的私有資源根
await client.add_resource(path, parent="viking://~/resources/project/")

# 技能預設新增到自己的技能根
await client.add_skill(skill)  # 預設根目錄：viking://~/skills/

# 通過 -p 指定寫入全域 agent 技能根（公開共享）
ov skills add xxx -p viking://agent/skills/
```

### resources 作用域約束

`resources` 作用域僅用於儲存客觀知識類資料（文件、程式碼、規範、論文等）。
禁止在 `viking://resources/` 下儲存非知識類資料，包括但不限於：
工具配置、通訊端點定義、支付配置、技能定義等。
此類資料應使用 `viking://agent/` 作用域。

## 相關文件

- [架構概述](./01-architecture.md) - 系統整體架構
- [上下文型別](./02-context-types.md) - 三種上下文型別
- [上下文層級](./03-context-layers.md) - L0/L1/L2 模型
- [儲存架構](./05-storage.md) - VikingFS 和 AGFS
- [會話管理](./08-session.md) - 會話儲存結構
