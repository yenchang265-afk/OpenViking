# 會話管理

Session 負責管理對話訊息、記錄上下文使用、提取長期記憶。

## 概覽

**生命週期**：建立 → 互動 → 提交

通過 session_id 獲取會話時不會建立會話。請先建立會話，再通過
`client.session(session_id=...)` 追加訊息或提交會話。

```python
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
| `get_task(task_id)` | 查詢後臺任務狀態 |

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

# 查詢後臺任務進度
task = client.get_task(task_id=result["task_id"])
# task["status"]: "pending" | "running" | "completed" | "failed"
# sum(task["result"]["memories_extracted"].values()): 3
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

**Phase 1（同步，立即完成）**：
1. 遞增 compression_index
2. 寫入訊息到歸檔目錄（`messages.jsonl`）
3. 清空當前訊息列表
4. 返回 `task_id`

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

### 提取流程

```
訊息 → LLM 提取 → 候選記憶
         ↓
向量預過濾 → 找相似記憶
         ↓
LLM 去重決策 → candidate(skip/create/none) + item(merge/delete)
         ↓
寫入 AGFS → 向量化
```

### 去重決策

| 層級 | 決策 | 說明 |
|------|------|------|
| Candidate | `skip` | 候選記憶重複，直接跳過 |
| Candidate | `create` | 建立候選記憶；必要時先刪除衝突舊記憶 |
| Candidate | `none` | 不建立候選記憶，只處理已有記憶 |
| Existing item | `merge` | 將候選內容合併到指定已有記憶 |
| Existing item | `delete` | 刪除衝突的已有記憶 |

## 記憶變更記錄

每次 `session.commit()` 會在歸檔目錄寫入 `memory_diff.json`，記錄本次提交的所有記憶變更，便於審計和回溯。

```json
{
  "archive_uri": "viking://user/{user_id}/sessions/{session_id}/history/archive_001",
  "extracted_at": "2026-04-21T10:00:00Z",
  "operations": {
    "adds": [
      {
        "uri": "memory/user/xxx/identity.md",
        "memory_type": "identity",
        "after": "新建立的檔案內容"
      }
    ],
    "updates": [
      {
        "uri": "memory/user/xxx/context/project.md",
        "memory_type": "context",
        "before": "修改前的檔案內容",
        "after": "修改後的檔案內容"
      }
    ],
    "deletes": [
      {
        "uri": "memory/user/xxx/context/old.md",
        "memory_type": "context",
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
