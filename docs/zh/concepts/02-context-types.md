# 上下文型別

基於對人類認知模式的簡化對映與工程化思考，OpenViking 將上下文抽象為 **資源、記憶、能力三種**基本型別，每種型別在 Agent 中有不同的用途。

## 概覽

| 型別 | 用途 | 生命週期 | 主動性 |
|------|------|----------|--------|
| **Resource** | 知識和規則 | 長期，相對靜態 | 使用者新增 |
| **Memory** | Agent 的認知 | 長期，動態更新 | Agent 記錄 |
| **Skill** | 可宣告的 agent 能動性配置（AgentDefinedContextType） | 長期，靜態 | 使用者或系統新增 |

## Resource（資源）

資源是 Agent 可以引用的外部知識。

### 特點

- **使用者主動**：由使用者主動新增的資源類資訊，用於補充大模型的知識，比如產品手冊、程式碼倉庫
- **靜態內容**：新增後內容很少發生變化，通常為使用者主動修改
- **結構化儲存**：將按照專案或主題以目錄層級組織，並提取出多層資訊。

### 示例

- API 文件、產品手冊
- FAQ 資料庫、程式碼倉庫
- 研究論文、技術規範

### 使用

```python
# 新增資源
client.add_resource(
    path="https://docs.example.com/api.pdf",
    options={"reason": "API 文件"},
)

# 搜尋資源
results = client.find(
    query="認證方法",
    target_uri="viking://resources/",
)
```

## Memory（記憶）

記憶是 Agent 從互動和任務執行中學到的持久化知識。記憶儲存在當前使用者或 Peer 名稱空間，不使用獨立的 `viking://agent/memories` 目錄。

### 特點

- **Agent 主動：**由 Agent 主動提取和記錄的記憶資訊
- **動態更新：**由 Agent 從互動中持續更新
- **個性化：**針對特定使用者和穩定 peer 學習記錄

### 內建記憶型別

| 型別 | 預設位置 | 說明 |
|------|----------|------|
| **profile** | `~/memories/profile.md` | 使用者基本資訊 |
| **preferences** | `~/memories/preferences/` | 按主題組織的使用者偏好 |
| **entities** | `~/memories/entities/` | 人物、專案、組織等實體知識 |
| **events** | `~/memories/events/` | 決策、里程碑等事件記錄 |
| **identity** | `~/memories/identity.md` | 助手的名稱、形象、氣質和自我介紹 |
| **soul** | `~/memories/soul.md` | 助手的核心原則、邊界、風格和連續性 |
| **cases** | `~/memories/cases/` | 用於訓練和評估的任務案例 |
| **trajectories** | `~/memories/trajectories/` | 可複用的任務執行軌跡 |
| **experiences** | `~/memories/experiences/` | 從執行結果中提煉的可複用經驗 |

表中的 `~/...` 使用家目錄別名 `viking://~`，服務端會按認證身份將其展開為 `viking://user/{user_id}/...`。當記憶策略允許 Peer 記憶時，支援 Peer 的型別會寫入 `viking://user/{user_id}/peers/{peer_id}/memories/...`。記憶型別可通過自定義模板擴充或調整。

Schema 定義的 `memories/tools/` 和 `memories/skills/` 型別已停用。它們與存放在 `viking://user/{user_id}/skills/{skill_name}/SKILL.md` 下的獨立 Skill 不同，後者仍然保留並受支援。

### 使用

```python
from openviking_sdk import TextPart

# 記憶從會話中自動提取
session_info = await client.create_session()
session = client.session(session_id=session_info["session_id"])
await session.add_message(
    role="user",
    parts=[TextPart(text="我喜歡深色模式")],
)
commit = await session.commit()  # 啟動後臺記憶提取
task = await client.get_task(task_id=commit["task_id"])  # 輪詢直到 task["status"] == "completed"

# 搜尋記憶
results = await client.find(
    query="使用者介面偏好",
    target_uri="viking://~/memories/"
)
```

## Skill（技能 / AgentDefinedContextType）

技能（Skill）是 Agent 可以呼叫的能力，屬於 AgentDefinedContextType 範疇。包括傳統工作流定義、通訊端點、工具配置和支付能力等。它們的共同特徵是：**定義了 agent 如何與外部系統互動**，執行時定義相對靜態，但呼叫經驗會在 Memory 中更新。

### 特點

- **定義的能力：**用於完成某項工作的工具定義
- **相對靜態：**執行時技能定義不變，但和工具相關的使用記憶會在記憶中更新
- **可呼叫：**Agent 決定何時使用哪種技能

### 儲存位置

```
viking://~/skills/{skill-name}/  # 預設儲存路徑
├── .abstract.md          # L0: 簡短描述
├── .overview.md          # L1: 目錄概覽（生成後）
├── SKILL.md              # L2: 技能定義
└── scripts               # L2: 附加實現

viking://agent/skills/{skill-name}/  # 通過 --uri 覆蓋，公開共享（account 全域）
├── .abstract.md          # L0: 簡短描述
├── .overview.md          # L1: 目錄概覽（生成後）
├── SKILL.md              # L2: 技能定義
└── scripts               # L2: 附加實現
```

### AgentDefinedContextType 子型別

AgentDefinedContextType 包含以下子型別，均儲存於 `viking://agent/` 作用域：

| 子型別 | 位置 | 說明 |
|--------|------|------|
| **Skill** | `agent/skills/` | 傳統工作流定義，如搜尋、程式碼生成 |
| **Endpoint** | `agent/endpoints/` | 通訊端點配置（a2a, anp 等）（規劃中） |
| **Tool** | `agent/tools/` | 工具配置（mcp 等）（規劃中） |
| **Payment** | `agent/payments/` | 支付能力配置（ap2 等）（規劃中） |

### 使用

```python
# 新增技能（預設寫入 viking://~/skills/）
await client.add_skill(
    data={
        "name": "search-web",
        "description": "搜尋網路獲取資訊",
        "content": "# search-web\n...",
    },
)

# 通過 -p 指定寫入全域 agent 技能根（公開共享）
ov skills add search-web -p viking://agent/skills

# 搜尋使用者技能
results = await client.find(
    query="網路搜尋",
    target_uri="viking://~/skills/"
)

# 搜索全局 agent 技能
results = await client.find(
    query="網路搜尋",
    target_uri="viking://agent/skills/",
)
```

## 統一檢索

根據Agent的需求需求，支援對三種上下文型別統一搜索，提供全面資訊：

```python
# 跨所有上下文型別搜尋
results = await client.find(query="使用者認證")

for context in results.get("memories", []):
    print(f"記憶: {context['uri']}")
for context in results.get("resources", []):
    print(f"資源: {context['uri']}")
for context in results.get("skills", []):
    print(f"技能: {context['uri']}")
```

## 相關文件

- [架構概述](./01-architecture.md) - 系統整體架構
- [上下文層級](./03-context-layers.md) - L0/L1/L2 模型
- [Viking URI](./04-viking-uri.md) - URI 規範
- [會話管理](./08-session.md) - 記憶提取機制
