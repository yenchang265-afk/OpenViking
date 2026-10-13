# 執行觀測

Observer API 提供佇列、向量庫、模型、鎖、檢索和檔案系統等元件的即時狀態。

## Observer API

以下 Python 示例使用 `SyncHTTPClient`。Observer 介面是返回字典的屬性，使用 `client.observer.queue`，不加括號。每次訪問都會請求服務端；需要讀取多個欄位時，先儲存返回值。

### observer.queue

#### 1. API 實現介紹

獲取佇列系統狀態（embedding 和語義處理佇列）。顯示各佇列的待處理、進行中、已完成和錯誤數量。

**程式碼入口**:
- `openviking/server/routers/observer.py:observer_queue` - HTTP 路由
- `openviking/service/debug_service.py:ObserverService.queue` - 核心實現
- `openviking/storage/observers/queue_observer.py` - 佇列觀察者

#### 2. 介面和引數說明

無引數。

#### 3. 使用示例

**HTTP API**

```
GET /api/v1/observer/queue
```

```bash
curl -X GET http://localhost:1933/api/v1/observer/queue \
  -H "X-API-Key: your-key"
```

**Python SDK**

```python
status = client.observer.queue
print(status["is_healthy"])
print(status["status"])
```

**TypeScript SDK**

```typescript
console.log(await client.queueStatus());
```

**Go SDK**

```go
status, err := client.QueueStatus(ctx)
if err != nil {
    return err
}
fmt.Println(status["is_healthy"])
```

**CLI**

```bash
ov observer queue
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "name": "queue",
    "is_healthy": true,
    "has_errors": false,
    "status": "Queue                 Pending  In Progress  Processed  Errors  Total\nEmbedding             0        0            10         0       10\nSemantic              0        0            10         0       10\nTOTAL                 0        0            20         0       20"
  }
}
```

---

### observer.vikingdb

#### 1. API 實現介紹

獲取 VikingDB 狀態。結構化響應還會在後端能夠從已載入索引中確定時，返回實際向量 metric 和純 dense 分數尺度。

**程式碼入口**:
- `openviking/server/routers/observer.py:observer_vikingdb` - HTTP 路由
- `openviking/service/debug_service.py:ObserverService.account_vikingdb` - 核心實現
- `crates/ov_cli/src/commands/observer.rs` - CLI 命令

#### 2. 介面和引數說明

| 引數 | 型別 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `format` | string | 否 | `table` | `table` 返回原有可讀狀態；`json` 返回結構化執行時詳情。 |

#### 3. 使用示例

**HTTP API**

```
GET /api/v1/observer/vikingdb?format=json
```

```bash
curl -X GET 'http://localhost:1933/api/v1/observer/vikingdb?format=json' \
  -H "X-API-Key: your-key"
```

**Python SDK**

```python
status = client.observer.vikingdb
print(status["is_healthy"])
print(status["status"])
```

**TypeScript SDK**

```typescript
console.log(await client.vikingDBStatus());
```

**Go SDK**

```go
status, err := client.VikingDBStatus(ctx)
if err != nil {
    return err
}
fmt.Println(status["is_healthy"])
```

**CLI**

```bash
ov observer vikingdb
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "name": "vikingdb",
    "is_healthy": true,
    "has_errors": false,
    "status": {
      "backend": "local",
      "collection": "context",
      "index": "default",
      "dimension": 1024,
      "vector_count": 55,
      "distance_metric": "cosine",
      "pure_dense_score_scale": "cosine_affine_0_1"
    }
  }
}
```

對於 local 後端，cosine、IP 和 L2 對應的 `pure_dense_score_scale` 分別為 `cosine_affine_0_1`、`inner_product` 和 `one_minus_squared_l2`。其他後端返回 `backend_defined`；如果已載入的後設資料沒有暴露 metric，`distance_metric` 為 `null`。

該欄位只描述純 dense 向量分數。稀疏融合、時間衰減、rerank 等檢索階段可能產生不同尺度的最終 `score`。從 v0.4.22 起，local 純 dense cosine 使用 `clamp((cosine_similarity + 1) / 2, 0, 1)`，已有索引也適用。

---

### observer.models

#### 1. API 實現介紹

獲取當前帳號的 VLM、Embedding 配置和 token 用量資訊。觀察器解析帳號模型資訊時未發生錯誤，`is_healthy` 才為 true；它不會逐一探測提供者是否可達。Embedding 連通性可檢視 `/ready`，其他模型應結合實際請求錯誤排查。

**程式碼入口**:
- `openviking/server/routers/observer.py:observer_models` - HTTP 路由
- `openviking/service/debug_service.py:ObserverService.models` - 核心實現
- `openviking/storage/observers/models_observer.py` - 模型觀察者
- `crates/ov_cli/src/commands/observer.rs` - CLI 命令

#### 2. 介面和引數說明

無引數。

#### 3. 使用示例

**HTTP API**

```
GET /api/v1/observer/models
```

```bash
curl -X GET http://localhost:1933/api/v1/observer/models \
  -H "X-API-Key: your-key"
```

**Python SDK**

```python
status = client.observer.models
print(status["is_healthy"])
print(status["status"])
```

**TypeScript SDK**

```typescript
console.log(await client.modelsStatus());
```

**Go SDK**

```go
status, err := client.ModelsStatus(ctx)
if err != nil {
    return err
}
fmt.Println(status["is_healthy"])
```

**CLI**

```bash
ov observer models
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "name": "models",
    "is_healthy": true,
    "has_errors": false,
    "status": "Account: default\nEmbedding dimension: 1024\nNo model usage data available."
  }
}
```

---

### observer.lock

#### 1. API 實現介紹

獲取分散式鎖系統狀態。

**程式碼入口**:
- `openviking/server/routers/observer.py:observer_lock` - HTTP 路由
- `openviking/service/debug_service.py:ObserverService.lock` - 核心實現
- `crates/ov_cli/src/commands/observer.rs` - CLI 命令

#### 2. 介面和引數說明

無引數。

#### 3. 使用示例

**HTTP API**

```
GET /api/v1/observer/lock
```

```bash
curl -X GET http://localhost:1933/api/v1/observer/lock \
  -H "X-API-Key: your-key"
```

公開 SDK 和 CLI 目前沒有單獨的 lock observer 方法。請使用 HTTP API 查詢該元件；`ov observer system` 會在彙總狀態中包含它。

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "name": "lock",
    "is_healthy": true,
    "has_errors": false,
    "status": "..."
  }
}
```

---

### observer.retrieval

#### 1. API 實現介紹

獲取已記錄的查詢次數、結果數、分數、Rerank 使用情況和延遲。這些資料用於診斷，不能直接衡量結果相關性；空結果也是有效結果，不會使該元件被判定為不健康。

**程式碼入口**:
- `openviking/server/routers/observer.py:observer_retrieval` - HTTP 路由
- `openviking/service/debug_service.py:ObserverService.retrieval` - 核心實現
- `openviking/storage/observers/retrieval_observer.py` - 檢索觀察者
- `crates/ov_cli/src/commands/observer.rs` - CLI 命令

#### 2. 介面和引數說明

無引數。

#### 3. 使用示例

**HTTP API**

```
GET /api/v1/observer/retrieval
```

```bash
curl -X GET http://localhost:1933/api/v1/observer/retrieval \
  -H "X-API-Key: your-key"
```

**CLI**

```bash
ov observer retrieval
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "name": "retrieval",
    "is_healthy": true,
    "has_errors": false,
    "status": "..."
  }
}
```

---

### observer.filesystem

#### 1. API 實現介紹

獲取檔案系統操作指標。

**程式碼入口**:
- `openviking/server/routers/observer.py:observer_filesystem` - HTTP 路由
- `openviking/service/debug_service.py:ObserverService.filesystem` - 核心實現
- `openviking/storage/observers/filesystem_observer.py` - 檔案系統觀察者
- `crates/ov_cli/src/commands/observer.rs` - CLI 命令

#### 2. 介面和引數說明

無引數。

#### 3. 使用示例

**HTTP API**

```
GET /api/v1/observer/filesystem
```

```bash
curl -X GET http://localhost:1933/api/v1/observer/filesystem \
  -H "X-API-Key: your-key"
```

**CLI**

```bash
ov observer filesystem
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "name": "filesystem",
    "is_healthy": true,
    "has_errors": false,
    "status": "..."
  }
}
```

---

### observer.system

#### 1. API 實現介紹

獲取整體系統狀態，包括所有元件（queue、vikingdb、models、lock、retrieval、filesystem）。

**程式碼入口**:
- `openviking/server/routers/observer.py:observer_system` - HTTP 路由
- `openviking/service/debug_service.py:ObserverService.system` - 核心實現
- `crates/ov_cli/src/commands/observer.rs` - CLI 命令

#### 2. 介面和引數說明

無引數。

#### 3. 使用示例

**HTTP API**

```
GET /api/v1/observer/system
```

```bash
curl -X GET http://localhost:1933/api/v1/observer/system \
  -H "X-API-Key: your-key"
```

**Python SDK**

```python
status = client.observer.system
print(status["is_healthy"])
print(status["components"])
```

**TypeScript SDK**

```typescript
console.log(await client.getStatus());
```

**Go SDK**

```go
status, err := client.GetStatus(ctx)
if err != nil {
    return err
}
fmt.Println(status["is_healthy"])
```

**CLI**

```bash
ov observer system
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "is_healthy": true,
    "errors": [],
    "components": {
      "queue": {
        "name": "queue",
        "is_healthy": true,
        "has_errors": false,
        "status": "..."
      },
      "vikingdb": {
        "name": "vikingdb",
        "is_healthy": true,
        "has_errors": false,
        "status": "..."
      },
      "models": {
        "name": "models",
        "is_healthy": true,
        "has_errors": false,
        "status": "..."
      },
      "lock": {
        "name": "lock",
        "is_healthy": true,
        "has_errors": false,
        "status": "..."
      },
      "retrieval": {
        "name": "retrieval",
        "is_healthy": true,
        "has_errors": false,
        "status": "..."
      },
      "filesystem": {
        "name": "filesystem",
        "is_healthy": true,
        "has_errors": false,
        "status": "..."
      }
    }
  }
}
```

---

## 相關文件

- [Metrics](09-metrics.md) - Prometheus 指標抓取
- [系統狀態](07-system.md) - 健康檢查和一致性檢查
