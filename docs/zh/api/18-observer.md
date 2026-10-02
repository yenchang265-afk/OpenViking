# 執行觀測

Observer API 提供佇列、向量庫、模型、鎖、檢索和檔案系統等元件的即時狀態。

## Observer API

Observer API 提供詳細的元件級監控。

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
print(client.observer.queue())
# 輸出:
# [queue] (healthy)
# Queue                 Pending  In Progress  Processed  Errors  Total
# Embedding             0        0            10         0       10
# Semantic              0        0            10         0       10
# TOTAL                 0        0            20         0       20
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
  },
  "time": 0.1
}
```

---

### observer.vikingdb

#### 1. API 實現介紹

獲取 VikingDB 狀態（集合、索引、向量數量）。

**程式碼入口**:
- `openviking/server/routers/observer.py:observer_vikingdb` - HTTP 路由
- `openviking/service/debug_service.py:ObserverService.vikingdb` - 核心實現
- `openviking/storage/observers/vikingdb_observer.py` - VikingDB 觀察者
- `crates/ov_cli/src/commands/observer.rs` - CLI 命令

#### 2. 介面和引數說明

無引數。

#### 3. 使用示例

**HTTP API**

```
GET /api/v1/observer/vikingdb
```

```bash
curl -X GET http://localhost:1933/api/v1/observer/vikingdb \
  -H "X-API-Key: your-key"
```

**Python SDK**

```python
print(client.observer.vikingdb())
# 輸出:
# [vikingdb] (healthy)
# Collection  Index Count  Vector Count  Status
# context     1            55            OK
# TOTAL       1            55

# 訪問特定屬性
print(client.observer.vikingdb().is_healthy)  # True
print(client.observer.vikingdb().status)      # 狀態表字串
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
    "status": "Collection  Index Count  Vector Count  Status\ncontext     1            55            OK\nTOTAL       1            55"
  },
  "time": 0.1
}
```

---

### observer.models

#### 1. API 實現介紹

獲取模型子系統的聚合狀態（VLM、embedding、rerank）。檢查各模型提供者是否健康可用。

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
print(client.observer.models())
# 輸出:
# [models] (healthy)
# provider_model         healthy  detail
# dense_embedding        yes      ...
# rerank                 yes      ...
# vlm                    yes      ...
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
    "status": "provider_model         healthy  detail\ndense_embedding        yes      ...\nrerank                 yes      ...\nvlm                    yes      ..."
  },
  "time": 0.1
}
```

---

### observer.lock

#### 1. API 實現介紹

獲取分散式鎖系統狀態。

**程式碼入口**:
- `openviking/server/routers/observer.py:observer_lock` - HTTP 路由
- `openviking/service/debug_service.py:ObserverService.lock` - 核心實現
- `openviking/storage/observers/lock_observer.py` - 鎖觀察者
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
  },
  "time": 0.1
}
```

---

### observer.retrieval

#### 1. API 實現介紹

獲取檢索質量指標。

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
  },
  "time": 0.1
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
  },
  "time": 0.1
}
```

---

### observer.system

#### 1. API 實現介紹

獲取整體系統狀態，包括所有元件（queue、vikingdb、models、lock、retrieval）。

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
print(client.observer.system())
# 輸出:
# [queue] (healthy)
# ...
#
# [vikingdb] (healthy)
# ...
#
# [models] (healthy)
# ...
#
# [system] (healthy)
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
      }
    }
  },
  "time": 0.1
}
```

---

## 相關文件

- [Metrics](09-metrics.md) - Prometheus 指標抓取
- [系統狀態](07-system.md) - 健康檢查和一致性檢查
