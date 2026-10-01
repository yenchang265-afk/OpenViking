# 檢索

OpenViking 提供多種檢索方法，包括簡單的向量相似度搜索、帶會話上下文的智慧檢索、正規表示式匹配搜尋和檔案模式匹配。

## find 與 search 對比

| 方面 | find | search |
|------|------|--------|
| 意圖分析 | 否 | 是 |
| 會話上下文 | 否 | 是 |
| 查詢擴充 | 否 | 是 |
| 預設結果數 | 10 | 10 |
| 使用場景 | 簡單查詢 | 對話式搜尋 |

## 檢索流程

檢索的核心流程如下：

```
查詢 → 意圖分析（僅search）→ 向量搜尋（L0）→ 重排序（L1）→ 結果
```

1. **意圖分析**（僅 search）：理解查詢意圖，擴充查詢
2. **向量搜尋**：使用 Embedding 查詢候選項
3. **重排序**：使用內容重新評分以提高準確性
4. **結果**：返回 top-k 上下文

## API 參考

### find()

基本向量相似度搜索，無需會話上下文。

#### 1. API 實現介紹

`find()` 方法執行純向量相似度搜索，適用於簡單的查詢場景。它使用分層檢索器（HierarchicalRetriever）在 L0 摘要層進行初步搜尋，然後在 L1/L2 層進行詳細匹配。

**處理流程**：
1. 將查詢文本轉換為向量
2. 在指定的目標 URI 範圍內執行全域向量搜尋
3. 使用分層檢索策略遞迴搜尋相關目錄和檔案
4. 可選：使用重排序模型最佳化結果排序
5. 返回匹配的上下文列表

**程式碼入口**：
- `openviking_cli/client/sync_http.py:SyncHTTPClient.find()` - Python SDK 入口（HTTP）
- `openviking/retrieve/hierarchical_retriever.py:HierarchicalRetriever.retrieve()` - 核心檢索實現
- `openviking/server/routers/search.py:find()` - HTTP 路由
- `crates/ov_cli/src/commands/search.rs:find()` - Rust CLI 命令

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| query | str | 否 | "" | 搜尋查詢字串；未提供 `image_url` 時必填 |
| image_url | str | 否 | None | 圖片查詢，支援 `data:image/...;base64,...`、`http(s)://` 或 `viking://` URI；需要 multimodal embedding 模型 |
| target_uri | str \| List[str] | 否 | "" | 限制搜尋範圍到指定的 URI 字首 |
| context_type | str \| List[str] | 否 | None | 限定一個或多個 `ContextType` 取值：`memory`、`resource` 或 `skill` |
| tags | List[str] | 否 | None | 顯式檢索標籤，必須是嚴格的 `k=v` 格式。多個 tags 之間是 AND 關係，結果必須同時包含所有請求的標籤 |
| limit | int | 否 | 10 | 最大返回結果數 |
| node_limit | int | 否 | None | 可選 HTTP 別名；如果提供，會覆蓋 limit |
| score_threshold | float | 否 | None | 最低相關性分數閾值 |
| filter | Dict | 否 | None | 後設資料過濾器 |
| since | str | 否 | None | 時間下界，支援 `2h` 或 ISO 8601 / `YYYY-MM-DD`。不帶時區的值按 UTC 解釋。CLI `--after` 會對映到這個欄位 |
| until | str | 否 | None | 時間上界，支援 `30m` 或 ISO 8601 / `YYYY-MM-DD`。不帶時區的值按 UTC 解釋。CLI `--before` 會對映到這個欄位 |
| time_field | "updated_at" \| "created_at" | 否 | "updated_at" | since/until 使用的後設資料時間欄位 |
| level | str | 否 | None | 限定結果的層級範圍，例如 `0`、`1`、`2` 或 `0,1,2`。CLI `--level`/`-L` 會對映到這個欄位 |
| include_provenance | bool | 否 | False | 在序列化結果中附帶 provenance / query-plan 細節 |
| read_content | bool | 否 | False | 按可見內容 read 語義讀取每個最終命中的 URI，並以內聯 `content` 返回。單個讀取失敗時保留原命中，不附加內容。 |
| telemetry | bool \| object | 否 | False | 在響應中附帶遙測資料 |

**目標解析說明**：
- `target_uri` 為空時，非 ROOT 檢索預設搜尋當前使用者根 `viking://user/{user}` 和公共 `viking://resources`。
- 如需在檔案系統和檢索操作中把當前使用者的 peer 集合過濾到某一個 peer，傳送 `X-OpenViking-Actor-Peer: <peer_id>`，或用 SDK/CLI client 的 `actor_peer_id` 初始化。見 [多租戶：Peer 集合過濾](../concepts/11-multi-tenant.md#peer-restricted-view)。
- `viking://~/memories`、`viking://~/resources`、`viking://~/skills` 等家目錄別名 target URI 會按認證請求身份展開為 canonical 路徑。無 uid 的寫法 `viking://user/memories`（以及 `resources`、`skills`、`peers`、`privacy`、`sessions` 的同類寫法）會被拒絕，並提示改用 `viking://~/...`。

**圖片搜尋說明**：
- 圖片查詢會以圖片向量作為 query，預設檢索目標範圍內的 L2 resource 葉子節點；結果不限於圖片檔案，圖片與文本/圖片資源的相似度由 multimodal embedding 模型決定。
- 純文本 embedding 模型仍會索引圖片 summary，但會拒絕圖片查詢輸入。
- 已有圖片資源保持現有向量不變；圖片向量召回只作用於開啟該能力後向量化的圖片，或之後手動 reindex 的圖片。

**FindResult 結構**

設定 `read_content=true` 後，每個成功讀取的命中都會額外包含 `content`。這是完整檔案讀取，請用 `limit` 控制響應大小。`search(mode="context")` 會拒絕該引數，因為 context 組裝已有自己的 token 預算。

```python
class FindResult:
    memories: List[MatchedContext]   # 記憶上下文
    resources: List[MatchedContext]  # 資源上下文
    skills: List[MatchedContext]     # 技能上下文
    query_plan: Optional[QueryPlan]  # 查詢計劃（僅 search）
    query_results: Optional[List[QueryResult]]  # 詳細結果
    total: int                       # 總數（自動計算）
```

**MatchedContext 結構**

```python
class MatchedContext:
    uri: str                         # Viking URI
    context_type: ContextType        # "resource"、"memory" 或 "skill"
    level: int                       # 層級 (0=L0, 1=L1, 2=L2)
    abstract: str                    # L0 內容
    overview: Optional[str]          # L1 概覽（非葉子節點時可選）
    category: str                    # 分類
    score: float                     # 相關性分數 (0-1)
    match_reason: str                # 匹配原因
```

#### 3. 使用示例

**HTTP API**

```
POST /api/v1/search/find
```

```bash
curl -X POST http://localhost:1933/api/v1/search/find \
    -H "Content-Type: application/json" \
    -H "X-API-Key: your-key" \
    -d '{
        "query": "how to authenticate users",
        "limit": 10
    }'
```

**使用 Target URI 和時間過濾**

```bash
curl -X POST http://localhost:1933/api/v1/search/find \
    -H "Content-Type: application/json" \
    -H "X-API-Key: your-key" \
    -d '{
        "query": "authentication",
        "target_uri": "viking://resources",
        "since": "7d",
        "time_field": "created_at"
    }'
```

**按 Context Type 搜索**

```bash
curl -X POST http://localhost:1933/api/v1/search/find \
    -H "Content-Type: application/json" \
    -H "X-API-Key: your-key" \
    -d '{
        "query": "authentication",
        "context_type": ["memory", "resource"]
}'
```

**圖片搜尋**

```bash
curl -X POST http://localhost:1933/api/v1/search/find \
    -H "Content-Type: application/json" \
    -H "X-API-Key: your-key" \
    -d '{
        "image_url": "viking://resources/images/cat.png",
        "limit": 10
    }'
```

**按顯式檢索標籤搜尋**

```bash
curl -X POST http://localhost:1933/api/v1/search/find \
    -H "Content-Type: application/json" \
    -H "X-API-Key: your-key" \
    -d '{
        "query": "rollback runbook",
        "tags": ["env=prod", "team=search"]
    }'
```

Tags 必須使用嚴格的 `k=v` 字串。傳入多個 tags 時，`find()` 會要求全部命中；上面的例子只返回顯式檢索標籤同時包含 `env=prod` 和 `team=search` 的上下文。

**Python SDK**

```python
import openviking_sdk as ov
from openviking_sdk import TextPart

client = ov.SyncHTTPClient(url="http://localhost:1933", api_key="your-key")
client.initialize()

# 基礎搜尋
results = client.find(query="how to authenticate users")

# 帶過濾和時間範圍的搜尋
recent_emails = client.find(
    query="invoice",
    target_uri="viking://resources/email",
    options={
        "since": "7d",
        "time_field": "created_at",
    },
)

# 僅搜尋 memories 和 resources
typed_results = client.find(
    query="authentication",
    options={"context_type": ["memory", "resource"]},
)

# 按本地圖片、bytes、data URI、HTTP URL 或 viking:// URI 搜尋
image_results = client.find(query="", image="/path/to/photo.png")

# 按顯式檢索標籤搜尋。多個 tags 之間是 AND 關係。
tagged_results = client.find(
    query="rollback runbook",
    options={"tags": ["env=prod", "team=search"]},
)

# 遍歷結果
for context in results.get("resources", []):
    print(f"URI: {context['uri']}")
    print(f"Score: {context.get('score', 0.0):.3f}")
    print(f"Type: {context.get('context_type')}")
    print(f"Abstract: {context.get('abstract', '')[:100]}...")
    print("---")
```

**使用 Target URI 限定搜尋範圍**

```python
# 僅在資源中搜索
results = client.find(
    query="authentication",
    target_uri="viking://resources",
)

# 僅在使用者記憶中搜索
results = client.find(
    query="preferences",
    target_uri="viking://~/memories"
)

# 僅在當前使用者資源中搜索
results = client.find(
    query="private docs",
    target_uri="viking://~/resources"
)

# 檢索時把 peer 集合過濾到一個 peer
peer_client = ov.SyncHTTPClient(
    url="http://localhost:1933",
    api_key="your-key",
    actor_peer_id="web-visitor-alice",
)
peer_results = peer_client.find(query="invoice follow-up")

# 僅在技能中搜索
results = client.find(
    query="web search",
    target_uri="viking://~/skills"
)

# 在特定專案中搜索
results = client.find(
    query="API endpoints",
    target_uri="viking://resources/my-project",
)
```

**TypeScript SDK**

```typescript
console.log(await client.find("authentication", { targetUri: "viking://resources/docs/" }));
```

**Go SDK**

```go
result, err := client.Find(ctx, "how to authenticate users", &openviking.FindOptions{
    TargetURI:   "viking://resources/docs",
    Limit:       10,
    ContextType: []string{"resource"},
})
if err != nil {
    return err
}
for _, item := range result.Resources {
    fmt.Println(item.URI, item.Score)
}
```

**CLI**

```bash
# 基礎搜尋
openviking find "how to authenticate users"

# 指定 URI 範圍
openviking find "how to authenticate users" --uri "viking://resources"

# 限定上下文型別
openviking find "authentication" --context-type memory,resource

# 帶時間過濾
openviking find "invoice" --after 7d

# 帶限制數量
openviking find "how to authenticate users" --limit 20

# 限定層級範圍 (僅 L0)
openviking find "how to authenticate users" --level 0

# 限定層級範圍 (L1 和 L2)，使用短選項
openviking find "how to authenticate users" -L 1,2

# 圖片查詢統一使用 --image；可傳本地路徑、viking://、http(s):// 或 data:image URI
openviking find --image ./query.png --uri "viking://resources/images" --limit 5

# 使用已入庫圖片搜尋
openviking find --image "viking://resources/images/cat.png" --uri "viking://resources/images" --limit 5

# 使用公網圖片 URL 搜尋
openviking find --image "https://example.com/images/cat.png" --uri "viking://resources/images" --limit 5

# 圖文聯合檢索
openviking find "紅色海報風格" --image ./poster.png --uri "viking://resources/images"
```

**響應示例**

```json
{
    "status": "ok",
    "result": {
        "memories": [],
        "resources": [
            {
                "context_type": "resource",
                "uri": "viking://resources/01-overview/API_Overview/Documentation_Reading_P_2c6ae38b.md",
                "level": 2,
                "score": 0.12808319406977778,
                "category": "",
                "match_reason": "",
                "abstract": "This document is an API documentation reading plan that outlines the structure of subsequent API reference materials organized by functional module. Main sections or topics covered include resource management API, search API, file system operations, ses...",
                "overview": null
            },
            {
                "context_type": "resource",
                "uri": "viking://resources/01-overview/API_Overview/API_Endpoints/.abstract.md",
                "level": 0,
                "score": 0.12054087276495282,
                "category": "",
                "match_reason": "",
                "abstract": "This directory contains structured API reference documentation for the OpenViking platform, compiling detailed HTTP endpoint specifications for core and extended platform capabilities. It covers functional modules including system health checks, semanti...",
                "overview": null
            }
        ],
        "skills": [],
        "total": 2
    }
}
```

---

### search()

帶會話上下文和意圖分析的智慧檢索。

#### 1. API 實現介紹

`search()` 方法在 `find()` 的基礎上增加了會話上下文理解和意圖分析能力。它可以根據歷史對話更好地理解使用者查詢意圖，執行查詢擴充，提供更相關的搜尋結果。

**處理流程**：
1. 載入會話上下文（如果提供了 session_id）
2. 分析查詢意圖，結合對話歷史理解真實需求
3. 擴充查詢以提高召回率
4. 執行與 `find()` 相同的分層檢索流程
5. 返回帶查詢計劃的搜尋結果

**程式碼入口**：
- `openviking_cli/client/sync_http.py:SyncHTTPClient.search()` - Python SDK 入口（HTTP）
- `openviking/retrieve/hierarchical_retriever.py:HierarchicalRetriever.retrieve()` - 核心檢索實現
- `openviking/server/routers/search.py:search()` - HTTP 路由
- `crates/ov_cli/src/commands/search.rs:search()` - Rust CLI 命令

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| query | str | 否 | "" | 搜尋查詢字串；未提供 `image_url` 時必填 |
| image_url | str | 否 | None | 圖片查詢，支援 `data:image/...;base64,...`、`http(s)://` 或 `viking://` URI；需要 multimodal embedding 模型 |
| target_uri | str \| List[str] | 否 | "" | 限制搜尋範圍到指定的 URI 字首 |
| session | Session | 否 | None | 用於上下文感知搜尋的會話（SDK）|
| session_id | str | 否 | None | 用於上下文感知搜尋的會話 ID（HTTP）|
| context_type | str \| List[str] | 否 | None | 限定一個或多個 `ContextType` 取值：`memory`、`resource` 或 `skill` |
| tags | List[str] | 否 | None | 顯式檢索標籤，必須是嚴格的 `k=v` 格式。多個 tags 之間是 AND 關係，結果必須同時包含所有請求的標籤 |
| limit | int | 否 | 10 | 最大返回結果數 |
| node_limit | int | 否 | None | 可選 HTTP 別名；如果提供，會覆蓋 limit |
| score_threshold | float | 否 | None | 最低相關性分數閾值 |
| filter | Dict | 否 | None | 後設資料過濾器 |
| since | str | 否 | None | 時間下界，支援 `2h` 或 ISO 8601 / `YYYY-MM-DD`。不帶時區的值按 UTC 解釋。CLI `--after` 會對映到這個欄位 |
| until | str | 否 | None | 時間上界，支援 `30m` 或 ISO 8601 / `YYYY-MM-DD`。不帶時區的值按 UTC 解釋。CLI `--before` 會對映到這個欄位 |
| time_field | "updated_at" \| "created_at" | 否 | "updated_at" | since/until 使用的後設資料時間欄位 |
| level | str | 否 | None | 限定結果的層級範圍，例如 `0`、`1`、`2` 或 `0,1,2`。CLI `--level`/`-L` 會對映到這個欄位 |
| include_provenance | bool | 否 | False | 在序列化結果中附帶 provenance / query-plan 細節 |
| read_content | bool | 否 | False | 按可見內容 read 語義讀取每個最終命中的 URI，並以內聯 `content` 返回。單個讀取失敗時保留原命中，不附加內容；僅支援 `mode="list"`。 |
| telemetry | bool \| object | 否 | False | 在響應中附帶遙測資料 |

`search()` 使用和 `find()` 相同的目標解析和顯式標籤過濾規則，包括由 `X-OpenViking-Actor-Peer` 或 SDK `actor_peer_id` 選擇的 peer 集合過濾。提供 `image_url` 時，`search()` 會直接執行圖片檢索並跳過會話 query planning。

#### 3. 使用示例

**HTTP API**

```
POST /api/v1/search/search
```

```bash
curl -X POST http://localhost:1933/api/v1/search/search \
    -H "Content-Type: application/json" \
    -H "X-API-Key: your-key" \
    -d '{
        "query": "best practices",
        "session_id": "abc123",
        "context_type": "skill",
        "since": "2h",
        "time_field": "updated_at",
        "limit": 10
    }'
```

**不帶會話的搜尋（仍會進行意圖分析）**

```bash
curl -X POST http://localhost:1933/api/v1/search/search \
    -H "Content-Type: application/json" \
    -H "X-API-Key: your-key" \
    -d '{
        "query": "how to implement OAuth 2.0 authorization code flow"
}'
```

**圖片搜尋**

```bash
curl -X POST http://localhost:1933/api/v1/search/search \
    -H "Content-Type: application/json" \
    -H "X-API-Key: your-key" \
    -d '{
        "query": "similar poster",
        "image_url": "data:image/png;base64,...",
        "limit": 10
    }'
```

**Python SDK**

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(url="http://localhost:1933", api_key="your-key")
client.initialize()

# 建立帶對話上下文的會話
session_info = client.create_session()
session = client.session(session_id=session_info["session_id"])
session.add_message(
    role="user",
    parts=[TextPart(text="I'm building a login page with OAuth")],
)
session.add_message(
    role="assistant",
    parts=[TextPart(text="I can help you with OAuth implementation.")],
)

# 搜尋能夠理解對話上下文
results = client.search(
    query="best practices",
    session_id=session.session_id,
    options={
        "context_type": "skill",
        "since": "2h",
    },
)

for context in results.get("resources", []):
    print(f"Found: {context['uri']}")
    print(f"Abstract: {context.get('abstract', '')[:200]}...")
```

**不使用會話的搜尋**

```python
# search 也可以在沒有會話的情況下使用
# 它仍然會對查詢進行意圖分析
results = client.search(
    query="how to implement OAuth 2.0 authorization code flow"
)

for context in results.get("resources", []):
    print(f"Found: {context['uri']} (score: {context.get('score', 0.0):.3f})")
```

**圖片搜尋**

```python
results = client.search(
    query="similar poster",
    image="/path/to/poster.png",
)
```

**TypeScript SDK**

```typescript
console.log(await client.search("authentication", { targetUri: "viking://resources/docs/" }));
```

**Go SDK**

```go
result, err := client.Search(ctx, "best practices", &openviking.SearchOptions{
    SessionID:   "abc123",
    ContextType: "skill",
    Limit:       10,
})
if err != nil {
    return err
}
fmt.Println(result.Total)
```

**CLI**

```bash
# 帶會話 ID 的搜尋
openviking search "best practices" --session-id abc123

# 限定上下文型別
openviking search "best practices" --context-type skill

# 帶時間過濾的搜尋
openviking search "watch vs scheduled" --after 2026-03-15 --before 2026-03-20

# 不帶會話的搜尋（仍進行意圖分析）
openviking search "how to implement OAuth 2.0 authorization code flow"

# 限定層級範圍（僅 L0）
openviking search "best practices" --level 0

# 限定層級範圍（L1 和 L2），使用短選項
openviking search "how to implement OAuth" -L 1,2

# 圖片查詢同樣使用 --image；會直接檢索並跳過 session planning
openviking search "similar poster" --image ./poster.png --uri "viking://resources/images"
```

**響應示例**

```json
{
    "status": "ok",
    "result": {
        "memories": [],
        "resources": [
            {
                "context_type": "resource",
                "uri": "viking://resources/docs/oauth-best-practices",
                "level": 1,
                "score": 0.95,
                "category": "",
                "match_reason": "Context-aware match: OAuth login best practices",
                "abstract": "OAuth 2.0 best practices for login pages...",
                "overview": "This guide covers OAuth 2.0 best practices including secure token handling, redirect URI validation, and state parameter usage..."
            }
        ],
        "skills": [],
        "query_plan": {
            "reasoning": "User is asking about OAuth implementation best practices, expanding to related security topics",
            "queries": [
                {
                    "query": "OAuth 2.0 best practices",
                    "context_type": "resource",
                    "intent": "Find OAuth 2.0 implementation guidelines",
                    "priority": 3
                },
                {
                    "query": "login page security",
                    "context_type": "resource",
                    "intent": "Find login page security recommendations",
                    "priority": 2
                }
            ]
        },
        "total": 1
    }
}
```

---

### search(mode="context")

把檢索結果直接組裝成可注入的上下文塊。`mode="list"`（預設）返回排序命中列表，行為與舊版 `search()` 完全一致；`mode="context"` 開啟組裝面：預算控制、檔位降級、跨輪去重和可選的 LLM 摘要都在服務端一次請求內完成。

#### 1. API 實現介紹

Agent 外掛每輪注入上下文時，過去需要按型別逐個檢索、再逐條回讀全文，在客戶端拼裝。組裝收斂到服務端後，外掛只發一次請求，所有 Harness 外掛共享同一套預算、降級與去重實現。

**處理流程**：
1. **L1 查詢理解**：可選，結合 Session 最近訊息做有界意圖擴充（最多 3 條查詢，超時熔斷，失敗回退原查詢）
2. **L0 檢索**：按 `quotas` 分桶獨立檢索，或不設配額時全域檢索一次
3. **L2 組裝**：token 預算內填充檔位（全員先落到各自類別的預設檔，再用剩餘預算按分數序加深），超限退檔不截斷
4. **L3 重寫**：可選，把組裝結果壓成帶 URI 引用的 digest（超時熔斷，失敗仍返回未重寫的 `rendered`；精確返回 `NO_RELEVANT_MEMORY` 時記為 `stats.rewrite="no_relevant"`，Coding Agent 客戶端不會再回退注入 `rendered`）

**程式碼入口**：
- `openviking/server/routers/search.py:_search_context()` - HTTP 路由分支
- `openviking/retrieve/context_assembler/pipeline.py:assemble_context()` - 組裝編排
- `openviking/retrieve/context_assembler/budget.py:plan_entries()` - 預算與檔位填充
- `openviking/retrieve/context_assembler/tiers.py` - 各來源型別的概覽檔提取

#### 2. 介面和引數說明

**L0 檢索域**：`query`、`image_url`、`context_type`、`limit`、`score_threshold`、`filter`、`tags`、`since`/`until` 與 list 模式一致。`limit` 只約束 quota-free 檢索；一旦 `purpose` 或顯式 `quotas` 啟用分桶檢索，各分類配額就是唯一候選上限。`target_uri` 在 context 模式下暫不支援（返回 400）；`level` 被忽略，檔位由 `detail` 決定。

**L1 查詢理解**

| 引數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `session_id` | str | None | 提供後才能啟用查詢擴充與服務端去重 |
| `query_expansion` | `off` \| `auto` | `auto` | `auto` 時結合 Session 做有界擴充；無 session 或失敗時自動回退為原查詢 |

**L2 組裝**

| 引數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `limit` | int | 10 | 僅作為 quota-free 檢索的候選條目上限；`purpose` 或 `quotas` 啟用分桶後被忽略 |
| `max_tokens` | int | 1600 | 唯一的預算引數，採用感知 CJK 的啟發式估算（codepoint ≥ 0x3000 記 1.5 token/字，其餘按 chars/4） |
| `quotas` | object | None | 各桶絕對條數上限；鍵取 `events`/`entities`/`preferences`/`experiences`/`resources`/`skills`。顯式傳入後忽略 `limit` |
| `purpose` | `chat` \| `coding` | None | 按下表的絕對分類配額啟用六域分桶取樣；僅在未顯式傳 `quotas` 時生效 |
| `detail` | `abstract` \| `overview` \| `full` \| object | None | 為每條結果請求同一個起始檔和最高檔；請求檔不可用或裝不進預算時仍逐檔退檔而不截斷。省略時按類別取預設檔（見下）。也可傳按類別的物件，如 `{"events":"overview","preferences":"abstract"}`，未列出的類別仍取預設檔。`"auto"` 是已廢棄的寫法，等價於省略 |
| `dedup_turns` | int | 0 | 跨輪冷卻輪數，需要 `session_id`；帳本存在 `{session_uri}/.recall_log.json` |
| `exclude_uris` | string[] | [] | 無狀態去重兜底，最多 200 條，與 `dedup_turns` 取並集 |
| `peer_scope` | `actor` \| `all` | `all` | `actor` 排除其他 peer，但仍保留全域、User 自有和當前 Actor Peer 內容 |
| `other_peer_penalty` | number \| object | 按型別預設值 | 對其他 peer 結果施加的分數折損 |

**L3 重寫**

| 引數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `rewrite` | bool \| `auto` | `false` | 服務端 digest 重寫；`auto` 時僅在配置了 query_planner 模型時啟用 |
| `rewrite_max_bullets` | int | 6 | digest 條數上限（1–20） |

**檔位規則**

- **Purpose 預設**：`chat` 使用 `events:3, entities:3, preferences:1, experiences:1, resources:1, skills:1`；`coding` 使用 `events:1, entities:2, preferences:1, experiences:1, resources:3, skills:2`。這些值是每個分類的絕對上限，不是權重。各桶結果彙總後仍會去重並全域排序，但不會再被第二個全域 `limit` 截斷
- **按類別的預設檔**：省略 `detail` 時，各類別落在下表的檔位；只有 `events` 會因此讀檔案，其餘類別零 I/O

  | 類別 | 預設檔 | 剩餘預算可加深到 | 原因 |
  |------|--------|------------------|------|
  | `events` | 概覽檔 | 全文件 | 唯一正文足夠長、`# Summary` 抽取能真正壓縮的型別 |
  | `entities` / `preferences` / `experiences` | 摘要檔 | 摘要檔 | 正文本身很短，且寫入側把整篇正文存進了摘要標量，摘要檔即完整內容 |
  | `resources` / `skills` | 摘要檔 | 摘要檔 | 資源取語義處理生成的 256 字元摘要，skill 取 `SKILL.md` frontmatter 生成的 name/description；正文可能很大或含憑據，加深需顯式指定 |
  | `memories` | 摘要檔 | 摘要檔 | 四個具名型別之外的內建記憶型別——`cases`、`patterns`、`tools`、`trajectories`、技能使用記憶。只有 quota-free 檢索會命中它們；它們沒有自己的檢索桶，`quotas` 不能指定，但 `detail` 和 `other_peer_penalty` 可以 |
  | 目錄命中 | 概覽檔 | 概覽檔 | 目錄沒有摘要，讀 `.overview.md` 側車；全文件對目錄無意義。skill 包命中除外：它們歸一到 `<包根>/SKILL.md`，按上面的檔案檔位處理 |

- **Skill 包**：一個包的每個檔案、每層目錄各存一條向量記錄，它們在配額生效之前先合併成一條——不管命中的是包裡哪個檔案，每個包只出一條 entry、只佔一個名額。這條 entry 的 `uri` 是 `<包根>/SKILL.md`，和 `/skills/find` 返回的 `skill_md_uri` 是同一條路徑，正文是包自己的摘要；包的摘要還沒生成時退成裸 `uri`，不拿命中的那個檔案的摘要頂替。因此 `dedup_turns` 是按包冷卻的：某個包以摘要檔或更深的檔位注入過之後，冷卻視窗內命中包裡任何檔案都會被排除
- **保底**：每條結果至少給出 `uri`。記憶類摘要缺失或超出單條上限時回落到概覽檔：寫入側把整篇正文存進了摘要標量，所以對記憶類別而言概覽檔在內容階梯上位於摘要檔*之下*，這次替換披露得更少。而 `resources` / `skills` 的摘要是語義處理生成的短摘要，同樣的替換會去讀呼叫方沒有請求的正文，因此這兩類直接退成裸 `uri`，不向上加深
- **顯式 `detail`**：把該檔作為全部結果請求的起點和上限；裝不下的條目仍逐檔退檔而不截斷。上述記憶類概覽檔替換是實際檔位唯一可能高於指定檔的情況，且僅因為它比指定檔攜帶的內容更少
- **概覽檔按來源取骨架**：記憶檔案取開頭的 `# Summary` 段，程式碼檔案取函式與類簽名（複用 `code_outline`），長文件取標題樹加首段
- **單條上限**：`max_tokens ÷ 候選條數 × 2`，對除裸 `uri` 外的所有檔位一律生效；某一檔超出該上限時退回上一檔，不做截斷。預算仍有剩餘時，最後一輪加深不受該上限約束，只受 `max_tokens` 約束

#### 3. 使用示例

**HTTP API**

```bash
# 基礎上下文組裝
curl -X POST http://localhost:1933/api/v1/search/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENVIKING_API_KEY" \
  -d '{"query":"這個分支改了什麼","mode":"context","max_tokens":1600}'

# 會話感知：查詢擴充 + 跨輪去重
curl -X POST http://localhost:1933/api/v1/search/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENVIKING_API_KEY" \
  -d '{
    "query":"繼續剛才的重構",
    "mode":"context",
    "session_id":"cc-1a2b3c",
    "query_expansion":"auto",
    "dedup_turns":5,
    "purpose":"coding",
    "max_tokens":3000
  }'

# 開啟服務端 digest 重寫
curl -X POST http://localhost:1933/api/v1/search/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENVIKING_API_KEY" \
  -d '{"query":"檔位設計","mode":"context","max_tokens":3000,"rewrite":true}'
```

**響應**

```json
{
  "status": "ok",
  "result": {
    "entries": [
      {
        "uri": "viking://user/default/memories/events/2026/07/14/tier_design.md",
        "category": "events",
        "score": 0.45,
        "detail": "full",
        "text": "# Summary\n檔位模型改為按類別定義預設檔\n...",
        "origin": "self"
      },
      {
        "uri": "viking://user/default/memories/entities/software/openviking_fs.md",
        "category": "entities",
        "score": 0.43,
        "detail": "abstract",
        "text": "OpenViking FS 儲存層……",
        "origin": "self"
      }
    ],
    "rendered": "<memory uri=\"viking://user/default/memories/events/2026/07/14/tier_design.md\" type=\"events\" score=\"0.45\" detail=\"full\">\n# Summary\n...\n</memory>",
    "digest": "",
    "stats": {
      "candidates": 13,
      "returned": 13,
      "dropped": 0,
      "deduped": 0,
      "max_tokens": 3000,
      "used_tokens": 2510,
      "per_entry_cap": 462,
      "detail": null,
      "tier_counts": {"full": 4, "overview": 2, "abstract": 7},
      "fill": {"floor_tokens": 1890, "overview_upgrades": 0, "full_upgrades": 4, "spare_upgrades": 0},
      "query_expansion": "used",
      "rewrite": "off",
      "rewrite_usage": null,
      "excluded": 0,
      "dedup": {"turns": 5, "status": "ok", "cooled": 2, "turn": 34}
    }
  }
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `entries[].uri` | string | 條目 URI，任何檔位都必然存在，可用 MCP `read` 下鑽 |
| `entries[].category` | string | `events`/`entities`/`preferences`/`experiences`/`resources`/`skills`，或 `memories`（四個具名型別之外的內建記憶型別） |
| `entries[].detail` | string | 實際檔位：`full`、`overview`、`abstract` 或 `uri` |
| `entries[].text` | string | 該檔位的正文；`uri` 檔為空 |
| `rendered` | string | 扁平 XML 上下文塊，可直接注入；重寫返回 `no_relevant` 時為空 |
| `digest` | string | 重寫成功時的摘要；失敗或壓縮器判定無相關記憶時為空字串 |
| `stats` | object | 預算用量、檔位分佈、擴充與重寫狀態（`off`、`ok`、`no_relevant`、`failed` 或 `timeout`）、去重帳本狀態；某個檢索域失敗時附帶 `retrieval_errors`，用於區分「檢索壞了」和「確實沒有相關記憶」 |

當 `stats.rewrite` 為 `no_relevant` 時，響應仍保留 `entries` 供檢查，但 `digest` 和
`rendered` 都為空字串。這樣即使客戶端尚未識別新狀態，也不會回退注入原文。本輪
沒有交付任何內容，因此這些 URI 也不會進入 `dedup_turns` 帳本，之後真正相關的那一輪
仍能召回它們。

**校驗規則**

- `mode="list"` 下顯式攜帶任何 context 專用引數 → 400
- `mode="context"` 下傳 `target_uri` → 400
- `quotas` 出現未知鍵 → 400
- context 模式下被忽略的欄位（`level`、`purpose` 或顯式配額生效時的 `limit`）會記錄在 `stats.ignored`

---

### grep()

通過模式（正規表示式）搜尋內容。

#### 1. API 實現介紹

`grep()` 方法在檔案系統中執行正規表示式匹配搜尋，用於查詢包含特定模式的檔案和內容行。與語義搜尋不同，grep 是精確的模式匹配。

**處理流程**：
1. 從指定 URI 開始遍歷檔案系統
2. 對每個檔案內容進行正規表示式匹配
3. 收集匹配行、位置資訊及可選的前後文
4. 返回匹配結果列表

**程式碼入口**：
- `openviking_cli/client/sync_http.py:SyncHTTPClient.grep()` - Python SDK 入口（HTTP）
- `openviking/server/routers/search.py:grep()` - HTTP 路由
- `crates/ov_cli/src/commands/search.rs:grep()` - Rust CLI 命令

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| uri | str | 是 | - | 要搜索的 Viking URI |
| pattern | str | 是 | - | 搜尋模式（正規表示式）|
| case_insensitive | bool | 否 | False | 忽略大小寫 |
| node_limit | int | 否 | 256 | 最大返回節點數。省略時預設使用 256；如需更多結果，請顯式傳入更大的整數 |
| exclude_uri | str | 否 | None | 要排除在搜尋之外的 URI 字首 |
| level_limit | int | 否 | Python SDK: 5；HTTP API / CLI / Go SDK: 10 | 最大目錄遍歷深度。Go SDK 當前使用 HTTP API 預設值。 |
| tags | string[] | 否 | 未設定 | 僅搜尋同時匹配全部 `k=v` 檢索標籤的檔案 |
| include_tags | bool | 否 | `false` | 不過濾時也在每條命中中返回檢索標籤 |
| before_context | int | 否 | 0 | 每條匹配行之前返回的上下文行數；僅 HTTP API 和 CLI 支援 |
| after_context | int | 否 | 0 | 每條匹配行之後返回的上下文行數；僅 HTTP API 和 CLI 支援 |

`tags` 使用 AND 語義，並在內容匹配與 `node_limit` 截斷之前過濾候選檔案。例如 `["team=search", "env=prod"]` 只匹配同時具有兩個標籤的檔案。

使用 `tags` 過濾或傳 `include_tags=true` 時，`matches` 中的命中會返回檔案的 `tags`；沒有檢索標籤的檔案返回空陣列 `[]`。普通 grep 會省略 `tags`，避免不必要的 VectorDB 讀取。

#### 3. 使用示例

**HTTP API**

```
POST /api/v1/search/grep
```

```bash
curl -X POST http://localhost:1933/api/v1/search/grep \
    -H "Content-Type: application/json" \
    -H "X-API-Key: your-key" \
    -d '{
        "uri": "viking://resources",
        "pattern": "authentication",
        "case_insensitive": true,
        "before_context": 1,
        "after_context": 1,
        "tags": ["team=search", "env=prod"]
    }'
```

**Python SDK**

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(url="http://localhost:1933", api_key="your-key")
client.initialize()

results = client.grep(
    uri="viking://resources",
    pattern="authentication",
    case_insensitive=True,
    node_limit=1024,
    tags=["team=search", "env=prod"],
)

print(f"Found {results['count']} matches")
for match in results['matches']:
    print(f"  {match['uri']}:{match['line']}")
    print(f"    {match['content']}")
```

**TypeScript SDK**

```typescript
console.log(await client.grep("viking://resources/docs/", "authentication", {
  tags: ["team=search", "env=prod"],
}));
```

**Go SDK**

```go
nodeLimit := 1024
result, err := client.Grep(ctx, "viking://resources", "authentication", &openviking.GrepOptions{
    CaseInsensitive: true,
    NodeLimit:       &nodeLimit,
    Tags:            []string{"team=search", "env=prod"},
})
if err != nil {
    return err
}
fmt.Println(result["count"])
```

**CLI**

```bash
# 基礎搜尋
openviking grep "authentication" --uri viking://resources

# 忽略大小寫
openviking grep "authentication" --uri viking://resources --ignore-case

# 指定深度限制
openviking grep "TODO" --uri viking://resources --level-limit 3

# 返回匹配行前後各 2 行上下文
openviking grep "authentication" --uri viking://resources -b 2 -a 2

# 只搜尋同時匹配所有 tags 的檔案
openviking grep "TODO" --uri viking://resources --tags team=search,env=prod

# 不過濾、但在人類可讀結果中顯示 tags
openviking grep "TODO" --uri viking://resources --fields tags
```

HTTP `POST /api/v1/search/grep` 在不做過濾時可傳 `include_tags: true` 返回 tags；傳入 `tags` 過濾時會始終返回命中檔案的 tags。

**響應示例**

```json
{
    "status": "ok",
    "result": {
        "matches": [
            {
                "uri": "viking://resources/docs/auth.md",
                "line": 15,
                "content": "User authentication is handled by...",
                "before_context": [
                    {"line": 14, "content": "## Authentication"}
                ],
                "after_context": [
                    {"line": 16, "content": "Configure an API key before sending requests."}
                ],
                "tags": ["team=search", "env=prod"]
            }
        ],
        "count": 1
    },
    "time": 0.1
}
```

---

### glob()

通過 glob 模式匹配檔案。

#### 1. API 實現介紹

`glob()` 方法使用檔案萬用字元模式匹配 URI，類似於 Unix shell 的 glob 功能。用於按名稱模式查詢檔案和目錄。

**支援的模式語法**：
- `*` 匹配任意字元（除路徑分隔符）
- `**` 遞迴匹配任意目錄
- `?` 匹配單個字元
- `[]` 匹配字元範圍

**程式碼入口**：
- `sdk/python/openviking_sdk/client.py:SyncHTTPClient.glob()` - Python SDK 入口（HTTP）
- `openviking/server/routers/search.py:glob()` - HTTP 路由
- `crates/ov_cli/src/commands/search.rs:glob()` - Rust CLI 命令

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| pattern | str | 是 | - | Glob 模式（例如 `**/*.md`）|
| uri | str | 否 | "viking://" | 起始 URI |
| node_limit | int | 否 | 256 | 最大返回匹配數。省略時預設使用 256；如需更多結果，請顯式傳入更大的整數 |
| extra_fields | list[str] | 否 | None | 每條命中的額外欄位。省略時返回 URI 字串；提供後 `result.matches` 返回條目物件 |
| tags | string[] | 否 | 未設定 | 僅保留同時匹配全部 `k=v` 檢索標籤的結果 |
| include_tags | bool | 否 | `false` | 不過濾時也在每條命中中返回檢索標籤 |

`tags` 使用 AND 語義，並在 `node_limit` 截斷前應用。傳入 `tags` 或 `include_tags=true` 時，響應返回帶 `tags` 陣列的條目物件；普通 glob 繼續返回 URI 字串，且不會為了 tags 讀取 VectorDB。

#### 3. 使用示例

**HTTP API**

```
POST /api/v1/search/glob
```

```bash
curl -X POST http://localhost:1933/api/v1/search/glob \
    -H "Content-Type: application/json" \
    -H "X-API-Key: your-key" \
    -d '{
        "pattern": "**/*.md",
        "uri": "viking://resources",
        "tags": ["team=search", "env=prod"],
        "include_tags": true
    }'
```

**Python SDK**

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(url="http://localhost:1933", api_key="your-key")
client.initialize()

# 查詢所有 markdown 檔案（預設最多返回 256 條）
results = client.glob(pattern="**/*.md", uri="viking://resources")
print(f"Found {results['count']} markdown files:")
for uri in results['matches']:
    print(f"  {uri}")

# 查詢同時匹配全部 tags 的 Markdown 檔案
results = client.glob(
    pattern="**/*.md",
    uri="viking://resources",
    tags=["team=search", "env=prod"],
)
print(f"Found {results['count']} tagged markdown files")
```

**TypeScript SDK**

```typescript
console.log(await client.glob("**/*.md", "viking://resources/docs/", {
  tags: ["team=search", "env=prod"],
}));
```

**Go SDK**

```go
result, err := client.Glob(ctx, "**/*.md", "viking://resources", &openviking.GlobOptions{
    NodeLimit: openviking.Int(1024),
    Tags:      []string{"team=search", "env=prod"},
})
if err != nil {
    return err
}
fmt.Println(result["count"])
```

**CLI**

```bash
# 查找所有 markdown 文件
openviking glob "**/*.md" --uri viking://resources

# 查找所有 Python 文件
openviking glob "**/*.py"

# 按全部 tags 過濾，或只返回 tags
openviking glob "**/*.md" --tags team=search,env=prod
openviking glob "**/*.md" -f tags
```

**響應示例**

```json
{
    "status": "ok",
    "result": {
        "matches": [
            "viking://resources/docs/api.md",
            "viking://resources/docs/guide.md"
        ],
        "count": 2
    },
    "time": 0.1
}
```

---

## 處理結果

### 漸進式讀取內容

檢索結果通常只包含 L0 摘要，你可以根據需要漸進式載入更多詳細內容。

**Python SDK**

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(url="http://localhost:1933", api_key="your-key")
client.initialize()

results = client.find(query="authentication")

for context in results.get("resources", []):
    # 從 L0（摘要）開始 - 已包含在 context["abstract"] 中
    print(f"Abstract: {context.get('abstract', '')}")

    if context.get("level", 0) < 2:
        # 獲取 L1（概覽）用於目錄
        overview = client.overview(uri=context["uri"])
        print(f"Overview: {overview[:500]}...")
    else:
        # 載入 L2（內容）用於檔案
        content = client.read(uri=context["uri"])
        print(f"File content: {content}")
```

**HTTP API**

```bash
# 步驟 1：搜尋
curl -X POST http://localhost:1933/api/v1/search/find \
    -H "Content-Type: application/json" \
    -H "X-API-Key: your-key" \
    -d '{"query": "authentication"}'

# 步驟 2：讀取目錄結果的概覽
curl -X GET "http://localhost:1933/api/v1/content/overview?uri=viking://resources/docs/auth" \
    -H "X-API-Key: your-key"

# 步驟 3：讀取檔案結果的完整內容
curl -X GET "http://localhost:1933/api/v1/content/read?uri=viking://resources/docs/auth.md" \
    -H "X-API-Key: your-key"
```

## 最佳實踐

### 使用具體的查詢

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(url="http://localhost:1933", api_key="your-key")
client.initialize()

# 好 - 具體的查詢
results = client.find(query="OAuth 2.0 authorization code flow implementation")

# 效果較差 - 過於寬泛
results = client.find(query="auth")
```

### 限定搜尋範圍

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(url="http://localhost:1933", api_key="your-key")
client.initialize()

# 在相關範圍內搜尋以獲得更好的結果
results = client.find(
    query="error handling",
    target_uri="viking://resources/my-project",
)
```

### 在對話中使用會話上下文

```python
import openviking_sdk as ov
from openviking_sdk import TextPart

client = ov.SyncHTTPClient(url="http://localhost:1933", api_key="your-key")
client.initialize()

# 對於對話式搜尋，使用會話
session_info = client.create_session()
session = client.session(session_id=session_info["session_id"])
session.add_message(
    role="user",
    parts=[TextPart(text="I'm building a login page")],
)

# 搜尋能夠理解上下文
results = client.search(
    query="best practices",
    session_id=session.session_id,
)
```

## 相關文件

- [資源](02-resources.md) - 資源管理
- [會話](05-sessions.md) - 會話上下文
- [上下文層級](../concepts/03-context-layers.md) - L0/L1/L2
