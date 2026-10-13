# 會話管理

Session 負責管理對話訊息、記錄上下文使用、提取長期記憶。

## 概覽

**生命週期**：建立 → 互動 → 提交

通過 session_id 獲取會話時不會建立會話。請先建立會話，再通過
`client.session(session_id=...)` 追加訊息或提交會話。

```python
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(url="http://localhost:1933", api_key="your-key")
session_info = client.create_session(session_id="chat_001")
session = client.session(session_id=session_info["session_id"])
session.add_message(role="user", content="...")
session.commit()
```

## 核心 API

| 方法 | 說明 |
|------|------|
| `add_message(role, content=None, parts=None, options=None, peer_id=None)` | 添加消息 |
| `commit()` | 提交：歸檔（同步） + 摘要生成和記憶提取（非同步後臺） |
| `client.get_task(task_id)` | 查詢後臺任務狀態 |

### add_message

```python
from openviking_sdk import ContextPart, ImagePart, TextPart

session.add_message(
    role="user",
    content="How to configure embedding?",
)

session.add_message(
    role="assistant",
    parts=[
        TextPart(text="Here's how..."),
        ContextPart(
            uri="viking://~/memories/profile.md",
            context_type="memory",
            abstract="User profile",
        ),
    ]
)

session.add_message(
    role="user",
    parts=[
        TextPart(text="Remember this studio layout."),
        ImagePart(url="https://example.com/studio.png", detail="auto"),
    ]
)
```

### commit

```python
result = session.commit()
# {
#   "status": "accepted",
#   "task_id": "uuid-xxx",
#   "archive_uri": "viking://user/{user_id}/sessions/.../history/archive_001",
#   "archived": True
# }

# 產生歸檔時才有後臺任務；無可歸檔訊息時返回 skipped 和 task_id: null
task_id = result.get("task_id")
if task_id:
    task = client.get_task(task_id=task_id)
    print(task)  # 單次查詢，不代表任務已完成
```

## 訊息結構

### Message

```python
@dataclass
class Message:
    id: str              # msg_{UUID}
    role: str            # "user" | "assistant"
    parts: List[Part]    # 消息部分
    created_at: datetime
```

### Part 型別

| 型別 | 說明 |
|------|------|
| `TextPart` | 文本內容 |
| `ImagePart` | 圖片 URL 內容。記憶提取時，OpenViking 可以使用已配置的 VLM 將其描述為文本。 |
| `ContextPart` | 上下文引用（URI + 摘要） |
| `ToolPart` | 工具呼叫（輸入 + 輸出） |

## 壓縮策略

### 歸檔流程

commit() 分兩階段執行：

**Phase 1（請求內完成歸檔準備）**：
1. 在路徑鎖保護下分配歸檔編號，劃分歸檔訊息和保留訊息
2. 寫入歸檔訊息（`messages.jsonl`），將後續處理加入持久化佇列
3. 更新當前訊息列表；預設歸檔全部訊息，也可通過提交引數保留最近的訊息或輪次
4. 產生歸檔時返回 `task_id`，用於跟蹤後臺處理

**Phase 2（非同步後臺）**：
5. 生成結構化摘要（LLM）→ 寫入 `.abstract.md` 和 `.overview.md`
6. 提取長期記憶
7. 寫入 `memory_diff.json`（記憶變更審計日誌）到歸檔目錄
8. 寫入 `.done` 完成標記

### 摘要格式

```markdown
# 會話摘要

**一句話概述**: [主題]: [意圖] | [結果] | [狀態]

## Analysis
關鍵步驟列表

## Primary Request and Intent
使用者的核心目標

## Key Concepts
關鍵技術概念

## Pending Tasks
未完成的任務
```

## 記憶提取

### 記憶型別

提交會話後，OpenViking 會根據對話內容和當前記憶策略，提取對後續互動有價值的資訊，並儲存到當前使用者的記憶空間。當對話涉及穩定的 Peer 時，相關記憶也可以儲存到對應的 Peer 空間。

OpenViking 內建 `profile`、`preferences`、`entities`、`events`、`identity`、`soul`、`cases`、`trajectories` 和 `experiences` 等記憶型別，也支援根據業務需要自定義。完整用途與路徑見 [上下文型別](./02-context-types.md)。

在 `memory_policy.memory_types` 中，`experiences` 會啟用完整的 Agent Evolution 流程，並自動啟用 `cases` 和 `trajectories`。如果沒有 `experiences`，顯式傳入的 `cases` 和 `trajectories` 會被靜默忽略，不會報錯。

Agent Evolution 還要求生效的 `agent_evolution.enabled` 開關已開啟。選擇 `experiences` 後，流程將任務組織為 case，將執行記錄為 trajectory，再提煉可複用的 experiences。經驗使用情況和執行結果分佈通過 [Agent Evolution API](../api/19-agent-evolution.md) 查詢。`openviking/session/train/` 中的離線訓練框架屬於內部實現，不是公開訓練 API。

### 提取流程

<MemoryExtractionDiagram />

已有記憶會參與提取，更新可以合併或修改現有檔案，也可能建立或刪除檔案。實際操作受記憶 schema、寫入許可權和輸出校驗約束，不能把每次提交理解成必然新增記憶。只有產生 case 時，後續訓練才會生成 trajectory、experience 或已啟用的 session skill。

### 如何檢查更新結果

先等待 commit 對應任務完成，再檢視 `memory_diff.json`。其中新增、修改、刪除是實際檔案變更；`skipped_operations` 表示提取提出了操作，但校驗或策略使其跳過。無實際變化的更新不會計入 diff；正文未變但後設資料發生變化時，仍可能記錄為更新。

## 記憶變更記錄

提交後的後臺處理會在歸檔目錄寫入 `memory_diff.json`，記錄本次提交的記憶變更，便於審計和回溯。收到 `task_id` 時檔案可能尚未生成，先按[會話 API](../api/05-sessions.md)查詢任務完成狀態。

```json
{
  "archive_uri": "viking://user/{user_id}/sessions/{session_id}/history/archive_001",
  "extracted_at": "2026-04-21T10:00:00Z",
  "operations": {
    "adds": [
      {
        "uri": "viking://user/alice/memories/identity.md",
        "memory_type": "identity",
        "after": "新建立的檔案內容"
      }
    ],
    "updates": [
      {
        "uri": "viking://user/alice/memories/entities/project.md",
        "memory_type": "entities",
        "before": "修改前的檔案內容",
        "after": "修改後的檔案內容"
      }
    ],
    "deletes": [
      {
        "uri": "viking://user/alice/memories/entities/old.md",
        "memory_type": "entities",
        "deleted_content": "被刪除的檔案內容"
      }
    ]
  },
  "skipped_operations": [
    {
      "memory_type": "events",
      "page_id": 101,
      "reason_code": "invalid_ranges",
      "reason": "無法解析出有效的事件範圍"
    }
  ],
  "summary": {
    "total_adds": 1,
    "total_updates": 1,
    "total_deletes": 1,
    "total_skipped": 1
  }
}
```

| 欄位 | 說明 |
|------|------|
| `archive_uri` | 本次提交的歸檔目錄 URI |
| `extracted_at` | 提取時間的 ISO 8601 格式 |
| `operations.adds` | 新增的記憶（無 `before`） |
| `operations.updates` | 修改的記憶（含 `before` 和 `after`） |
| `operations.deletes` | 刪除的記憶（含 `deleted_content`） |
| `skipped_operations` | 策略性跳過的操作及穩定原因碼；不代表檔案變更 |
| `summary` | 各操作型別的計數 |

如果沒有實際變更或策略性跳過，也會寫入空結構的 `memory_diff.json`（所有計數為零）。

## 儲存結構

```
viking://user/{user_id}/sessions/{session_id}/
├── messages.jsonl            # 當前訊息
├── .abstract.md              # 當前摘要
├── .overview.md              # 當前概覽
├── history/
│   ├── archive_001/
│   │   ├── messages.jsonl    # Phase 1 寫入
│   │   ├── .abstract.md      # Phase 2 寫入（後臺）
│   │   ├── .overview.md      # Phase 2 寫入（後臺）
│   │   ├── memory_diff.json  # Phase 2 寫入（後臺，記憶變更審計）
│   │   └── .done             # Phase 2 完成標記
│   └── archive_NNN/
└── tools/
    └── {tool_id}/tool.json

viking://~/memories/
├── profile.md
├── identity.md
├── soul.md
├── preferences/
├── entities/
├── events/
├── cases/
├── trajectories/
└── experiences/
```

`viking://~/sessions/{session_id}` 使用家目錄別名，服務端會按認證身份將其展開為
`viking://user/{user_id}/sessions/{session_id}`。無 uid 的寫法
`viking://user/sessions/{session_id}` 不再被接受，請求會報錯並提示改用 `viking://~/...`。
`viking://session/{session_id}` 仍會作為同一個 session 路徑的向後相容別名被接受，
不是獨立的儲存根。

## 相關文件

- [架構概述](./01-architecture.md) - 系統整體架構
- [上下文型別](./02-context-types.md) - 三種上下文型別
- [上下文提取](./06-extraction.md) - 提取流程
- [上下文層級](./03-context-layers.md) - L0/L1/L2 模型
