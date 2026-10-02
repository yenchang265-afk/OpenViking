# 記憶

記憶由會話提交或顯式提取生成，儲存在使用者記憶名稱空間中，並可通過內容、檔案系統和檢索 API 使用。

## 內建記憶型別

| 分類 | 位置 | 說明 |
|------|------|------|
| profile | `user/memories/profile.md` | 使用者個人資訊 |
| preferences | `user/memories/preferences/` | 按主題分類的使用者偏好 |
| entities | `user/memories/entities/` | 重要實體（人物、專案等） |
| events | `user/memories/events/` | 重要事件 |
| identity | `user/memories/identity.md` | 助手身份與自我介紹 |
| soul | `user/memories/soul.md` | 助手原則、邊界、風格和連續性 |
| cases | `user/memories/cases/` | 可訓練、可評估的任務案例 |
| trajectories | `user/memories/trajectories/` | 可複用的操作契約 |
| experiences | `user/memories/experiences/` | 可複用的執行經驗 |
| tools | `user/memories/tools/` | 工具使用經驗與最佳實踐 |
| skills | `user/memories/skills/` | 技能執行經驗與工作流策略 |

以上是當前啟用的內建型別；部署可以通過自定義記憶模板擴充或覆蓋。

---

## API 參考

### recall()

> **已棄用**：`/api/v1/search/recall` 現在只是 [`/api/v1/search/search` 的 `mode="context"`](06-retrieval.md#search-mode-context) 之上的輕量預設，自身不再包含獨立的組裝邏輯。新接入請直接使用 context 面；v1 欄位別名僅在本端點保留，將在下一個 minor 版本移除。響應會帶上 `Deprecation: true` 頭。

按記憶型別分別檢索，並在預算內組合成可直接注入 Agent 上下文的記憶塊。相對 context 面，`/recall` 會疊加 `purpose="coding"`、相容 v1 的 `score_threshold=0.1`、帶 `session_id` 時 `dedup_turns=5`、`query_expansion="auto"`。Coding Agent 外掛會顯式傳送 `score_threshold=0.35`；公共 `/recall` 預設值仍為 `0.1`，避免相同請求在升級後靜默減少結果。省略 `quotas` 時沿用 v1 的分桶預設值（`events=10, entities=10, preferences=3, experiences=0`）；顯式傳 `"quotas": null` 才改用 `purpose` 預設配比。

**v1 欄位摺疊**

| v1 欄位 | 摺疊為 | 說明 |
|---------|--------|------|
| `max_chars` | `max_tokens = max_chars / 4` | `6500` → `1625`；顯式傳 `max_tokens` 時以後者為準 |
| `min_score` | `score_threshold` | 都未提供時取相容 v1 的預設值 `0.1` |
| `render: true` | 不釘檔位 | 預設行為：各類別取自己的預設檔 |
| `render: false` | 只返回 `entries`，`rendered` 為空 | |
| `render: "compact"` | `detail="abstract"` | 原型期的緊湊模式；把所有類別釘在摘要檔 |
| v1 `quotas` 鍵 | 疊加在 v1 分桶預設值之上 | 鍵名未變；只傳一部分鍵時其餘桶保留預設值 |

context 面的引數（`max_tokens`、`detail`、`dedup_turns`、`session_id`、`query_expansion`、`exclude_uris`、`purpose`、`rewrite`、`rewrite_max_bullets`）在本端點同樣接受，便於外掛在尚未升級的部署上平滑過渡。

**HTTP API**

```http
POST /api/v1/search/recall
Content-Type: application/json
```

```bash
curl -X POST http://localhost:1933/api/v1/search/recall \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENVIKING_API_KEY" \
  -d '{
    "query":"Business Data Platform API 文件偏好",
    "quotas":{"events":5,"entities":5,"preferences":3,"experiences":2},
    "max_chars":6500,
    "peer_scope":"all"
  }'
```

**MCP**

```text
recall(
  query="Business Data Platform API 文件偏好",
  quotas={"events": 5, "entities": 5, "preferences": 3, "experiences": 2},
  max_chars=6500,
  peer_scope="all"
)
```

**響應**

響應形狀與 context 面一致（entries 扁平化、`rendered` 為扁平 XML）：

```json
{
  "status": "ok",
  "result": {
    "entries": [
      {
        "uri": "viking://user/default/memories/preferences/api-docs.md",
        "category": "preferences",
        "score": 0.82,
        "detail": "full",
        "text": "使用者偏好在 API 文件中同時提供 HTTP、SDK 和 CLI 示例。",
        "origin": "self"
      }
    ],
    "rendered": "<memory uri=\"viking://user/default/memories/preferences/api-docs.md\" type=\"preferences\" score=\"0.82\" detail=\"full\">\n使用者偏好在 API 文件中同時提供 HTTP、SDK 和 CLI 示例。\n</memory>",
    "digest": "",
    "stats": {
      "quotas": {"events": 5, "entities": 5, "preferences": 3, "experiences": 2},
      "candidates": 4,
      "returned": 1,
      "dropped": 0,
      "max_tokens": 1625,
      "used_tokens": 96,
      "tier_counts": {"full": 1},
      "peer_scope": "all",
      "origins": {"actor_peer": 0, "self": 1, "other_peer": 0},
      "deprecated": {
        "endpoint": "/api/v1/search/recall",
        "successor": "/api/v1/search/search",
        "successor_body": {"mode": "context"},
        "aliases_used": ["max_chars"]
      }
    }
  }
}
```

欄位含義見 [檢索 - search(mode="context")](06-retrieval.md#search-mode-context)。相對 v1 的形狀變化：`type` → `category`、`mode` → `detail`、`content`/`summary` → `text`，`rendered` 由三層巢狀改為扁平 `<memory>` 標籤，`rank` 不再返回。

公共 Python、TypeScript、Go SDK 和 `ov` CLI 當前尚未封裝該端點，因此本節只展示 HTTP Tab，並補充實際存在的 MCP 呼叫。

## 相關文件

- [會話](05-sessions.md) - commit 與 extract
- [檢索](06-retrieval.md) - 搜尋記憶
- [內容](12-content.md) - 讀取記憶內容
