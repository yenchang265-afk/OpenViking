# 檢索機制

OpenViking 使用全域向量檢索，並可在召回完成後對候選結果執行一次 Rerank。會話意圖分析是獨立的前置階段。

## 概覽

```
查詢 → 意圖分析（可選）→ 全域向量檢索 → Rerank（可選）→ 結果
```

## find() vs search()

| 特性 | find() | search() |
|------|--------|----------|
| 會話上下文 | 不使用 | 可選，傳入 `session_id` 時使用 |
| 意圖分析 | 不使用 | 有會話內容且啟用時使用 LLM |
| 查詢數量 | 單一查詢 | 零個或多個 TypedQuery |
| 延遲 | 通常較低 | 取決於意圖分析、查詢數量和是否 Rerank |
| 適用場景 | 簡單查詢 | 複雜任務 |

`search` 的 `limit` 用於每條規劃查詢；多條查詢合併後的總數可能超過它，當前也不保證跨查詢去重。

### 使用示例

以下示例使用已配置的同步 Python SDK 客戶端 `client`。

```python
# find(): 簡單查詢
results = client.find(
    query="OAuth 認證",
    target_uri="viking://resources/",
)

# search(): 複雜任務（需要會話上下文）
session_info = client.create_session()
client.add_message(
    session_id=session_info["session_id"], role="user",
    content="我們正在為專案設計 OAuth 登入流程。",
)
results = client.search(
    query="幫我建立一個 RFC 文件",
    session_id=session_info["session_id"],
)
```

## 意圖分析

當 `retrieval.enable_intent=true` 且會話包含摘要或訊息時，IntentAnalyzer 使用 LLM 分析查詢意圖，生成零個或多個 TypedQuery。該階段使用的模型可通過 [`query_planner`](../guides/01-configuration.md#query-planner) 配置項單獨指定，未設定時回退到 `vlm`。

### 輸入

- 會話壓縮摘要
- 最近 5 條訊息
- 當前查詢

### 輸出

```python
@dataclass
class TypedQuery:
    query: str              # 重寫後的查詢
    context_type: ContextType  # MEMORY/RESOURCE/SKILL
    intent: str             # 查詢目的
    priority: int           # 1-5 優先順序
```

### 查詢風格

| 型別 | 風格 | 示例 |
|------|------|------|
| **skill** | 動詞開頭 | "建立 RFC 文件"、"提取 PDF 表格" |
| **resource** | 名詞短語 | "RFC 文件模板"、"API 使用指南" |
| **memory** | "使用者XX" | "使用者的程式碼規範偏好" |

### 特殊情況

- **0 個查詢**：閒聊、問候等不需要檢索的場景
- **多個查詢**：複雜任務可能需要技能 + 資源 + 記憶

## 全域檢索

`HierarchicalRetriever` 對每條查詢執行一次全域向量檢索。目標目錄、上下文型別、許可權、後設資料過濾和 `level` 一起限定搜尋範圍。未指定 `level` 時，文本查詢可直接命中 L0/L1/L2；不再先定位目錄再逐層搜尋。

### 檢索模式

| 模式 | 向量候選數 | Rerank |
|------|------------|--------|
| QUICK | `limit` | 不執行 |
| THINKING，且配置了可用的 Rerank | `2 × limit` | 對召回候選統一執行一次，返回最多 `limit` 條 |
| THINKING，未配置可用的 Rerank | `limit` | 不執行 |

`find()` 使用 QUICK。`search()` 配置了可用的 Rerank 時自動使用 THINKING，否則使用 QUICK。這是內部檢索模式，不是 LLM 的思考引數，也不控制會話意圖分析。意圖分析生成的多條查詢仍分別檢索和排序，再按現有方式彙總。

影像查詢跳過文本 Rerank，候選數為 `limit`；未指定 `level` 時預設搜尋 L2。

## Rerank 策略

Rerank 只處理本次全域召回的候選，不會觸發下一輪檢索。例如 `limit=10`，啟用 Rerank 時先召回向量分數最高的 20 條，再按 Rerank 結果返回最多 10 條；未啟用時直接召回 10 條。

- 使用候選索引記錄的 `abstract` 欄位作為 Rerank 文本。
- 分數與排序使用 Rerank 分數，否則使用向量分數；訪問頻次、更新時間和父目錄分數不參與加權。
- 分數閾值在 Rerank 後應用；未啟用 Rerank 時使用向量分數。
- Rerank 請求失敗或返回無效結果時，保留已有的向量分數回退行為。
- 不再使用目錄優先佇列、父子分數傳播或多輪收斂判斷。

支援的 provider 和配置見 [Rerank 配置](../guides/01-configuration.md#rerank)。

## 檢索結果

以下是服務端內部型別的欄位節選；HTTP/SDK 響應欄位以[檢索 API](../api/06-retrieval.md)為準。

### MatchedContext

```python
@dataclass
class MatchedContext:
    uri: str                # 資源 URI
    context_type: ContextType
    level: int              # 0=摘要，1=概覽，2=詳情
    abstract: str           # L0 摘要
    score: float            # 最終分數
```

### FindResult

```python
@dataclass
class FindResult:
    memories: List[MatchedContext]
    resources: List[MatchedContext]
    skills: List[MatchedContext]
    query_plan: Optional[QueryPlan]      # search() 時有
    query_results: Optional[List[QueryResult]]
    total: int
```

## 相關文件

- [架構概述](./01-architecture.md) - 系統整體架構
- [儲存架構](./05-storage.md) - 向量庫索引
- [上下文層級](./03-context-layers.md) - L0/L1/L2 模型
- [上下文型別](./02-context-types.md) - 三種上下文型別
