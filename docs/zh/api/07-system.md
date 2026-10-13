# 系統狀態

OpenViking 系統 API 提供健康檢查、就緒檢查、一致性檢查和後臺處理狀態。
元件級觀測和 Prometheus 指標分別提供獨立文件。

## API 參考

### health

#### 1. API 實現介紹

基礎存活檢查，無需認證。返回版本號、健康狀態和認證模式。提供憑據後會嘗試解析身份，成功時補充身份欄位；憑據無效時返回認證錯誤。

Trusted 模式下，完整的 `X-OpenViking-Account` 和 `X-OpenViking-User` 請求頭會觸發身份解析，
必須攜帶匹配的 root API key，localhost 也不例外。Trusted 模式的 `root_api_key_required`
始終為 `true`，解析得到的 `role` 表示呼叫者許可權。匿名健康探測返回基礎存活資訊，不包含身份欄位。

**程式碼入口**:
- `openviking/server/routers/system.py:health_check` - HTTP 路由
- `sdk/python/openviking_sdk/client.py:SyncHTTPClient.health` - SDK 入口
- `crates/ov_cli/src/commands/system.rs` - CLI 命令

#### 2. 介面和引數說明

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| profile | string | 否 | - | 傳 `1`、`true`、`yes` 或 `on` 時，為本次請求開啟 `cProfile`，並在 JSON 響應裡追加 `profile` 欄位 |

**profile 行為說明**:
- `profile` 是 HTTP middleware 級能力，對任意返回 JSON 的 OpenViking 介面都生效，不限於 `/health`。
- 僅當服務端在 `ov.conf` 中開啟 `server.profile_enabled = true` 時，請求裡的 `profile=1` 才會生效；否則服務端會忽略該引數。
- `profile` 僅對當前請求生效，請求結束後自動關閉；後續請求預設不會繼承這次 profile 狀態。
- 僅 JSON 響應會追加 `profile` 欄位；純文本、檔案、流式響應不會被改寫。
- `profile` 的返回值是 `list[string]`，每個元素對應一行格式化後的 `pstats` 輸出，便於瀏覽器直接檢視和前端按行渲染。
- `ov` CLI 會顯示返回的 `profile`；Python HTTP client 可以通過 `ovcli.conf.profile = true` 觸發服務端 profile，但大多數 SDK 方法預設只返回業務 `result`，不會把頂層 `profile` 一併暴露給呼叫方。

**profile 表頭欄位說明**:
- `ncalls`: 呼叫次數。若顯示為 `總呼叫次數/原始呼叫次數`，前者是總呼叫數，後者是 primitive calls。
- `tottime`: 函式自身耗時，總時間，不包含其呼叫的子函式耗時。
- `percall`（第一列）: `tottime / ncalls`，即函式自身平均每次呼叫耗時。
- `cumtime`: 累計耗時，包含當前函式及其所有子呼叫耗時。
- `percall`（第二列）: `cumtime / primitive calls`，即按原始呼叫計算的平均累計耗時。
- `filename:lineno(function)`: 函式定義位置。普通 Python 程式碼會顯示為裁剪後的模組路徑；`~:0(...)` 這類條目通常表示 builtin 或 C 擴充呼叫。

#### 3. 使用示例

**HTTP API**

```
GET /health
```

```bash
curl -X GET http://localhost:1933/health
```

```bash
curl -G http://localhost:1933/health \
  --data-urlencode "profile=1"
```

**Python SDK**

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(url="http://localhost:1933")
client.initialize()

healthy = client.health()
print(f"Healthy: {healthy}")
```

**TypeScript SDK**

```typescript
console.log(await client.health());
```

**Go SDK**

```go
healthy, err := client.Health(ctx)
if err != nil {
    return err
}
fmt.Println(healthy)
```

**CLI**

```bash
ov system health
```

```bash
ov --profile health
```

**響應示例**

```json
{
  "status": "ok",
  "healthy": true,
  "version": "0.1.x",
  "auth_mode": "api_key"
}
```

**帶 profile 的響應示例**

```json
{
  "status": "ok",
  "healthy": true,
  "version": "0.1.x",
  "profile": [
    "         325 function calls (310 primitive calls) in 0.004 seconds",
    "",
    "   Ordered by: cumulative time",
    "   List reduced from 87 to 87 due to restriction <100>",
    "",
    "   ncalls  tottime  percall  cumtime  percall filename:lineno(function)",
    "        1    0.000    0.000    0.003    0.003 starlette/middleware/base.py:112(call_next)",
    "        1    0.000    0.000    0.001    0.001 openviking/server/routers/system.py:39(health_check)",
    "        3    0.000    0.000    0.000    0.000 ~:0(<method 'read' of 'builtins.RAGFSBindingClient' objects>)"
  ]
}
```

---

### ready

#### 1. API 實現介紹

部署環境使用的就緒探針。檢查 AGFS、VectorDB、APIKeyManager、Embedding 和 Ollama（如配置）的狀態。當所有配置的子系統都準備完成時返回 200，否則返回 503。無需認證（專為 Kubernetes 探針設計）。

**程式碼入口**:
- `openviking/server/routers/system.py:readiness_check` - HTTP 路由

#### 2. 介面和引數說明

無引數。

**檢查項說明**:
- `agfs`: 包含檔案系統訪問和主備同步狀態的巢狀檢查結果
- `vectordb`: 向量資料庫是否健康
- `api_key_manager`: API 金鑰管理器是否已載入
- `embedding`: 啟動時 Embedding provider 是否已初始化；不發起模型請求
- `ollama`: Ollama 服務是否可達（僅當配置時）

#### 3. 使用示例

**HTTP API**

```
GET /ready
```

```bash
curl -X GET http://localhost:1933/ready
```

**響應示例**

```json
{
  "status": "ready",
  "checks": {
    "agfs": {"status": "ok", "checks": {"filesystem": "ok", "multiwrite_sync": "not_supported"}},
    "vectordb": "ok",
    "api_key_manager": "ok",
    "embedding": "ok",
    "ollama": "not_configured"
  }
}
```

---

### status

#### 1. API 實現介紹

獲取系統狀態，包括初始化狀態和當前認證使用者資訊。`result.user` 是認證請求的 `user_id`（來自 API 金鑰或請求頭），而非程序級服務預設值，客戶端可用於解析多租戶路徑。

**程式碼入口**:
- `openviking/server/routers/system.py:system_status` - HTTP 路由
- `crates/ov_cli/src/commands/system.rs` - CLI 命令

#### 2. 介面和引數說明

無引數。

#### 3. 使用示例

**HTTP API**

```
GET /api/v1/system/status
```

```bash
curl -X GET http://localhost:1933/api/v1/system/status \
  -H "X-API-Key: your-key"
```

公開 SDK 的 `get_status()` / `getStatus()` / `GetStatus()` 返回 Observer 彙總狀態，不是本介面的身份資訊。訪問本介面使用 HTTP；這些 SDK 方法見[執行觀測](18-observer.md)。

**CLI**

```bash
ov system status
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "initialized": true,
    "user": "alice"
  }
}
```

---

### consistency

#### 1. API 實現介紹

檢查指定 URI 子樹的檔案系統內容和向量索引是否一致，用於除錯索引缺失、向量快照匯出失敗等問題。該能力是通用資料一致性檢查，不屬於 OVPack 私有介面；`ov export --include-vectors` 和 `ov backup --include-vectors` 會複用同一檢查。

響應只返回摘要和缺失項，不返回完整 expected 列表。`missing_records` 最多返回前 20 條；如果還有更多缺失項，`missing_records_truncated` 為 `true`。

**程式碼入口**:
- `openviking/server/routers/system.py:check_consistency` - HTTP 路由
- `sdk/python/openviking_sdk/client.py:SyncHTTPClient.check_consistency` - SDK 入口
- `crates/ov_cli/src/commands/system.rs:consistency` - CLI 命令

#### 2. 介面和引數說明

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| uri | string | 是 | - | 要檢查的 Viking URI 子樹 |

#### 3. 使用示例

**HTTP API**

```
POST /api/v1/system/consistency
Content-Type: application/json
```

```bash
curl -X POST http://localhost:1933/api/v1/system/consistency \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"uri":"viking://resources/my-project"}'
```

**Python SDK**

```python
report = client.check_consistency(uri="viking://resources/my-project")
print(report["ok"])
print(report["missing_records"])
```

**TypeScript SDK**

```typescript
console.log(await client.checkConsistency("viking://resources/"));
```

**Go SDK**

```go
report, err := client.CheckConsistency(ctx, "viking://resources/my-project")
if err != nil {
    return err
}
fmt.Println(report["ok"])
```

**CLI**

```bash
ov system consistency viking://resources/my-project
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "ok": false,
    "expected_count": 3,
    "missing_record_count": 1,
    "missing_records_truncated": false,
    "missing_records": [
      {
        "uri": "viking://resources/my-project/README.md",
        "path": "README.md",
        "level": 2,
        "key": "README.md#level=2"
      }
    ]
  }
}
```

---

### wait_processed

#### 1. API 實現介紹

等待處理佇列排空，或在超時後結束。該檢查不限定為呼叫方剛提交的請求，也不覆蓋所有非同步 API。需檢查返回的 `error_count` 和 `errors`，佇列排空不代表所有操作成功。確認某次匯入或 commit 的結果，應查詢它的[任務 ID](17-tasks.md)。

**程式碼入口**:
- `openviking/server/routers/system.py:wait_processed` - HTTP 路由
- `sdk/python/openviking_sdk/client.py:SyncHTTPClient.wait_processed` - SDK 入口
- `crates/ov_cli/src/commands/system.rs` - CLI 命令

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| timeout | float | 否 | None | 超時時間（秒），None 表示無限等待 |

#### 3. 使用示例

**HTTP API**

```
POST /api/v1/system/wait
```

```bash
curl -X POST http://localhost:1933/api/v1/system/wait \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "timeout": 60.0
  }'
```

**Python SDK**

```python
# 等待當前處理佇列排空
status = client.wait_processed(timeout=60.0)
print(status)  # 檢查各佇列的 error_count 和 errors
```

**TypeScript SDK**

```typescript
console.log(await client.waitProcessed(60));
```

**Go SDK**

```go
status, err := client.WaitProcessed(ctx, &openviking.WaitProcessedOptions{
    Timeout: openviking.Float64(60),
})
if err != nil {
    return err
}
fmt.Println(status)
```

**CLI**

```bash
ov system wait --timeout 60
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "Embedding": {
      "processed": 10,
      "requeue_count": 0,
      "error_count": 0,
      "errors": []
    },
    "Semantic": {
      "processed": 10,
      "requeue_count": 0,
      "error_count": 0,
      "errors": []
    }
  }
}
```

---

<a id="reindex"></a><a id="observer-api"></a>

## 相關文件

- [Resources](02-resources.md) - 資源管理
- [Retrieval](06-retrieval.md) - 搜尋與檢索
- [Sessions](05-sessions.md) - 會話管理
- [執行觀測](18-observer.md) - 元件即時狀態
- [Metrics](09-metrics.md) - Prometheus 指標
