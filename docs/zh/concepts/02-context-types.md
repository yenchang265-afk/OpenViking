# 上下文型別

OpenViking 的資源提供參考資料，記憶儲存互動中提取的資訊，技能描述完成任務的方法。[規則（Beta）](./17-rule-scenarios.md)是獨立的強約束型別，表達 Agent 在特定條件下必須遵守的要求。

## 概覽

| 型別 | 用途 | 生命週期 | 主動性 |
|------|------|----------|--------|
| **Resource** | 原始知識與參考資料 | 保留至更新或刪除 | 使用者新增 |
| **Memory** | 偏好、事實和任務經驗 | 長期，動態更新 | 從會話提取或主動記錄 |
| **Skill** | 任務指令和配套資源 | 長期，可更新 | 使用者或系統新增 |
| **Rule（Beta）** | 持久、可執行的強約束 | active / paused / archived | 主動編譯，按需召回 |

## 示例準備

以下示例使用同步 Python SDK，需先啟動服務端。`add_resource` 和 `add_skill` 可傳 `wait=True`，等處理完成後再返回。會話提交會在記憶提取完成前返回，且沒有內建等待引數，因此先用下面的函式查詢提交任務，再檢索新內容。輪詢超時不會取消服務端任務。

```python
import time
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(url="http://localhost:1933", api_key="your-key")


def wait_for_task(task_id):
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        task = client.get_task(task_id)
        if task is None:
            raise RuntimeError(f"Task {task_id} not found")
        if task["status"] == "completed":
            return task
        if task["status"] in {"failed", "cancelled"}:
            raise RuntimeError(task)
        time.sleep(1)
    raise TimeoutError(f"Task {task_id} is still running")
```

## Resource（資源）

資源是 Agent 可以引用的外部知識。

### 特點

- **使用者主動**：由使用者主動新增的資源類資訊，用於補充大模型的知識，比如產品手冊、程式碼倉庫
- **顯式更新**：內容變化後重新匯入；支援 Watch 的遠端來源可定時重新整理
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
    wait=True,
    timeout=300,
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
session_info = client.create_session()
session = client.session(session_id=session_info["session_id"])
session.add_message(
    role="user",
    parts=[TextPart(text="我喜歡深色模式")],
)
commit = session.commit()  # 啟動後臺記憶提取
if commit.get("task_id"):
    wait_for_task(commit["task_id"])

# 搜尋記憶
results = client.find(
    query="使用者介面偏好",
    target_uri="viking://~/memories/"
)
```

## Skill（技能 / AgentDefinedContextType）

技能（Skill）通過 `SKILL.md` 和配套檔案描述一類任務的步驟、約束和資源。Agent 讀取技能後，使用自己的工具執行任務。呼叫經驗可以單獨儲存為記憶。

### 特點

- **任務說明：**記錄完成某項工作的流程和約束
- **可維護：**技能內容可以更新，執行經驗單獨存為記憶
- **按需讀取：**Agent 按當前任務選擇技能

### 儲存位置

```
viking://~/skills/{skill-name}/  # 預設儲存路徑
├── .abstract.md          # L0: 簡短描述
├── .overview.md          # L1: 目錄概覽（生成後）
├── SKILL.md              # L2: 技能定義
└── scripts               # L2: 附加實現

viking://agent/skills/{skill-name}/  # 通過 -p/--parent-auto-create 覆蓋，公開共享（account 全域）
├── .abstract.md          # L0: 簡短描述
├── .overview.md          # L1: 目錄概覽（生成後）
├── SKILL.md              # L2: 技能定義
└── scripts               # L2: 附加實現
```

### AgentDefinedContextType 子型別

下表列出共享能力的設計分類。當前支援 Skill，預設安裝到使用者私有目錄，也可顯式安裝到 `viking://agent/skills/`。其餘分類是規劃，不表示已提供對應介面：

| 子型別 | 位置 | 說明 |
|--------|------|------|
| **Skill** | `agent/skills/` | 傳統工作流定義，如搜尋、程式碼生成 |
| **Endpoint** | `agent/endpoints/` | 通訊端點配置（a2a, anp 等）（規劃中） |
| **Tool** | `agent/tools/` | 工具配置（mcp 等）（規劃中） |
| **Payment** | `agent/payments/` | 支付能力配置（ap2 等）（規劃中） |

### 使用

```python
# 新增技能（預設寫入 viking://~/skills/）
client.add_skill(
    data={
        "name": "search-web",
        "description": "搜尋網路獲取資訊",
        "content": "# search-web\n...",
    },
    wait=True,
    timeout=300,
)

# 搜尋使用者技能
results = client.find(
    query="網路搜尋",
    target_uri="viking://~/skills/"
)

# 搜尋全域 agent 技能
results = client.find(
    query="網路搜尋",
    target_uri="viking://agent/skills/",
)
```

通過 CLI 安裝到帳戶共享技能目錄（需要該路徑的寫入許可權）：

```bash
ov skills add ./skills/search-web -p viking://agent/skills
```

## 統一檢索

一次檢索可返回搜尋範圍內的資源、記憶和技能。預設範圍包含當前使用者空間和共享資源；如需同時查詢共享技能，應顯式加入 `viking://agent/skills`：

```python
# 跨所有上下文型別搜尋
results = client.find(
    query="使用者認證",
    target_uri=["viking://~", "viking://resources", "viking://agent/skills"],
)

for context in results.get("memories", []):
    print(f"記憶: {context['uri']}")
for context in results.get("resources", []):
    print(f"資源: {context['uri']}")
for context in results.get("skills", []):
    print(f"技能: {context['uri']}")
```

操作結束後關閉客戶端：

```python
client.close()
```

## 相關文件

- [架構概述](./01-architecture.md) - 系統整體架構
- [上下文層級](./03-context-layers.md) - L0/L1/L2 模型
- [Viking URI](./04-viking-uri.md) - URI 規範
- [會話管理](./08-session.md) - 記憶提取機制
