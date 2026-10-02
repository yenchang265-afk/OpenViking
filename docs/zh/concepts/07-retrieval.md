# 檢索機制

OpenViking 採用兩階段檢索：意圖分析 + 層級檢索 + Rerank。

## 概覽

```
查詢 → 意圖分析 → 層級檢索 → Rerank → 結果
         ↓           ↓          ↓
     TypedQuery  目錄遞迴    精排評分
```

## find() vs search()

| 特性 | find() | search() |
|------|--------|----------|
| 會話上下文 | 不需要 | 需要 |
| 意圖分析 | 不使用 | 使用 LLM 分析 |
| 查詢數量 | 單一查詢 | 0-5 個 TypedQuery |
| 延遲 | 低 | 較高 |
| 適用場景 | 簡單查詢 | 複雜任務 |

### 使用示例

```python
# find(): 簡單查詢
results = await client.find(
    query="OAuth 認證",
    target_uri="viking://resources/",
)

# search(): 複雜任務（需要會話上下文）
session_info = await client.create_session()
results = await client.search(
    query="幫我建立一個 RFC 文件",
    session_id=session_info["session_id"],
)
```

## 意圖分析

IntentAnalyzer 使用 LLM 分析查詢意圖，生成 0-5 個 TypedQuery。該階段使用的模型可通過 [`query_planner`](../guides/01-configuration.md#query-planner) 配置項單獨指定，未設定時回退到 `vlm`。

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

## 層級檢索

HierarchicalRetriever 使用優先佇列遞迴搜尋目錄結構。

### 流程

```
Step 1: 根據 context_type 確定根目錄
        ↓
Step 2: 全域向量搜尋定位起始目錄
        ↓
Step 3: 合併起始點 + Rerank 評分
        ↓
Step 4: 遞迴搜尋（優先佇列）
        ↓
Step 5: 轉換為 MatchedContext
```

### 根目錄對映

| context_type | 根目錄 |
|--------------|--------|
| MEMORY | `viking://~/memories` |
| RESOURCE | `viking://resources` |
| SKILL | `viking://~/skills` 與 `viking://agent/skills` |

### 遞迴搜尋演算法

```python
while dir_queue:
    current_uri, parent_score = heapq.heappop(dir_queue)

    # 搜尋子節點
    results = await search(parent_uri=current_uri)

    for r in results:
        # 分數傳播
        final_score = score_propagation_alpha * embedding_score + (1 - score_propagation_alpha) * parent_score

        if final_score > threshold:
            collected.append(r)

            if not r.is_leaf:  # 目錄繼續遞迴
                heapq.heappush(dir_queue, (r.uri, final_score))

    # 收斂檢測
    if topk_unchanged_for_3_rounds:
        break
```

### 關鍵引數

| 引數 | 值 | 說明 |
|------|-----|------|
| `retrieval.score_propagation_alpha` | 1.0 | 分數傳播混合中子節點自身分數的權重；`1.0` 表示僅使用子節點自身分數，忽略父節點分數 |
| `MAX_CONVERGENCE_ROUNDS` | 3 | 收斂檢測輪數 |
| `GLOBAL_SEARCH_TOPK` | 10 | 全域搜尋候選數 |

## Rerank 策略

Rerank 在 THINKING 模式下對候選結果精排。

### 觸發條件

- 配置了 Rerank AK/SK
- 使用 THINKING 模式（search() 預設）
- 如果 rerank 返回無效結果或 API 呼叫失敗，會回退到向量分數

### 評分方式

```python
if rerank_client and mode == THINKING:
    scores = rerank_client.rerank_batch(query, documents)
else:
    scores = [r["_score"] for r in results]  # 向量分數
```

### 使用位置

1. **起始點評估**：評估全域搜尋的候選目錄
2. **遞迴搜尋**：評估每層的子節點

### 後端支援

| 後端 | 模型 |
|------|------|
| Volcengine | doubao-seed-rerank |

## 檢索結果

### MatchedContext

```python
@dataclass
class MatchedContext:
    uri: str                # 資源 URI
    context_type: ContextType
    is_leaf: bool           # 是否文件
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
