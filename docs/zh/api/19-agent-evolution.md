# Agent 進化

Agent Evolution API 用於查詢某條 Experience 被實際應用後的 Trajectory 記錄及結果分佈。當前僅提供 HTTP API。

## API 參考

### 查詢 Experience 應用軌跡

分頁返回成功讀取過指定 Experience 的 Trajectory。查詢僅匹配當前呼叫使用者空間內的 Experience 和 Trajectory。

**程式碼入口**：

- `openviking/server/routers/agent_evolution.py:list_experience_trajectories` - HTTP 路由
- `openviking/service/agent_evolution_service.py:AgentEvolutionService.list_trajectories_by_experience` - 核心實現

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| experience_uri | string | 是 | - | 當前使用者空間內的 Experience 檔案 URI |
| limit | integer | 否 | 50 | 單頁數量，範圍為 1～1000 |
| offset | integer | 否 | 0 | 從零開始的結果偏移量 |
| start_date | string | 否 | - | Trajectory 建立日期下界（包含），UTC `YYYY-MM-DD` |
| end_date | string | 否 | - | Trajectory 建立日期上界（包含），UTC `YYYY-MM-DD` |

**HTTP API**

```
GET /api/v1/agent-evolution/experiences/trajectories?experience_uri={experience_uri}&limit=50&offset=0&start_date=2026-08-01&end_date=2026-08-10
```

```bash
curl -X GET "http://localhost:1933/api/v1/agent-evolution/experiences/trajectories?experience_uri=viking://user/default/memories/experiences/exchange.md&limit=50&offset=0&start_date=2026-08-01&end_date=2026-08-10" \
  -H "X-API-Key: your-key"
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "experience_uri": "viking://user/default/memories/experiences/exchange.md",
    "items": [
      {
        "uri": "viking://user/default/memories/trajectories/exchange_20260805020000.md",
        "name": "exchange_20260805020000.md",
        "description": "處理換貨請求",
        "created_at": "2026-08-05T02:00:00Z",
        "updated_at": "2026-08-05T02:00:00Z"
      }
    ],
    "total": 1,
    "limit": 50,
    "offset": 0,
    "has_more": false
  },
  "time": 0.01
}
```

`items` 中僅返回索引記錄實際存在的 `uri`、`name`、`description`、`created_at` 和 `updated_at` 欄位。

---

### 查詢 Experience 應用結果分佈

統計應用過指定 Experience 的 Trajectory 在五種結果狀態下的數量。該查詢使用精確標量標籤聚合，不讀取全部 Trajectory 檔案。

**程式碼入口**：

- `openviking/server/routers/agent_evolution.py:get_experience_outcome_distribution` - HTTP 路由
- `openviking/service/agent_evolution_service.py:AgentEvolutionService.get_experience_outcome_distribution` - 核心實現

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| experience_uri | string | 是 | - | 當前使用者空間內的 Experience 檔案 URI |
| start_date | string | 否 | - | Trajectory 建立日期下界（包含），UTC `YYYY-MM-DD` |
| end_date | string | 否 | - | Trajectory 建立日期上界（包含），UTC `YYYY-MM-DD` |

**HTTP API**

```
GET /api/v1/agent-evolution/experiences/outcomes?experience_uri={experience_uri}&start_date=2026-08-01&end_date=2026-08-10
```

```bash
curl -X GET "http://localhost:1933/api/v1/agent-evolution/experiences/outcomes?experience_uri=viking://user/default/memories/experiences/exchange.md&start_date=2026-08-01&end_date=2026-08-10" \
  -H "X-API-Key: your-key"
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "experience_uri": "viking://user/default/memories/experiences/exchange.md",
    "outcome_distribution": [
      {"outcome": "success", "count": 4},
      {"outcome": "failure", "count": 1},
      {"outcome": "partial", "count": 0},
      {"outcome": "unknown", "count": 0},
      {"outcome": "unfinished", "count": 0}
    ]
  },
  "time": 0.01
}
```

結果固定包含 `success`、`failure`、`partial`、`unknown` 和 `unfinished`。舊版建立且尚未重新索引的 Trajectory 沒有 outcome 標籤，因此不會計入分佈。

## 相關文件

- [會話](05-sessions.md) - 提交會話並生成 Agent Evolution 記憶
- [記憶](16-memory.md) - 記憶讀取與召回
