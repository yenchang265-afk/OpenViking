# Agent Runtime API

Agent Runtime Server 負責執行 Agent 任務，當前支援 Compile。應用通過 Business Data Platform 的 Compile API 提交任務，Business Data Platform 負責校驗請求、持久化任務和管理生命週期，再呼叫 Runtime 執行介面；內建 VikingBot 也實現了同一執行協議，可用於本地部署。

**程式碼入口**：

- `openviking/server/routers/compile.py` - 建立 Compile 任務
- `openviking/server/routers/tasks.py` - 查詢和取消任務
- `openviking/service/compile_service.py` - Runtime 呼叫與任務狀態收斂

## Compile 任務介面

### 建立任務

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `from` | string[] | 是 | - | 一個或多個來源目錄 |
| `to` | string | 是 | - | 目標 Resource 或 Memory 目錄，或受支援的 Skill namespace |
| `skill` | string | 是 | - | Skill 目錄或其 `SKILL.md` URI |
| `instruction` | string | 否 | Skill 驅動的預設值 | 本次 Compile 的補充指令 |
| `args` | object | 否 | - | 執行端擴充引數；`model_name` 可傳模型 Endpoint ID |

`args` 整體可省略，模型 Endpoint ID 也不是頂層欄位。需要指定模型時使用 `args.model_name`；不傳時由執行端使用其預設模型配置。

**HTTP API**

```http
POST /api/v1/compile
```

```bash
curl -X POST http://localhost:1933/api/v1/compile \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "from": ["viking://resources/research"],
    "to": "viking://resources/research-wiki",
    "skill": "viking://user/default/skills/research-compiler",
    "instruction": "追蹤歷史進展，並保留支撐證據。",
    "args": {"model_name": "your-model-endpoint-id"}
  }'
```

接口返回 `202 Accepted` 和 OV TaskRecord：

```json
{
  "status": "ok",
  "result": {
    "task_id": "cmp_01abc",
    "task_type": "compile",
    "status": "pending",
    "stage": "queued",
    "resource_id": "viking://resources/research"
  }
}
```

**CLI**

```bash
ov compile \
  --from viking://resources/research \
  --to viking://resources/research-wiki \
  --skill viking://user/default/skills/research-compiler \
  --instruction "追蹤歷史進展，並保留支撐證據。" \
  --args '{"model_name":"your-model-endpoint-id"}'
```

`--args` 必須是 JSON object。命令提交後立即返回 Task ID。

**SDK**

Python、TypeScript 和 Go SDK 都通過各自的 Compile options 傳遞 `instruction` 和 `args`：

::: code-group

```python [Python]
task = client.compile(
    ["viking://resources/research"],
    "viking://resources/research-wiki",
    "viking://user/default/skills/research-compiler",
    {"args": {"model_name": "your-model-endpoint-id"}},
)
```

```ts [TypeScript]
const task = await client.compile(
  ["viking://resources/research"],
  "viking://resources/research-wiki",
  "viking://user/default/skills/research-compiler",
  { args: { model_name: "your-model-endpoint-id" } },
);
```

```go [Go]
task, err := client.Compile(
    ctx,
    []string{"viking://resources/research"},
    "viking://resources/research-wiki",
    "viking://user/default/skills/research-compiler",
    &openviking.CompileOptions{
        Args: map[string]any{"model_name": "your-model-endpoint-id"},
    },
)
```

:::

### 檢查 Compile 可用性

```http
GET /api/v1/compile/capabilities
```

使用當前認證上下文，無需請求引數。返回 `200 OK`：

```json
{
  "status": "ok",
  "result": {
    "configured": true,
    "can_create": true,
    "reason_code": null
  }
}
```

| 欄位 | 含義 |
|------|------|
| `configured` | 是否已配置 Compile 執行端點 |
| `can_create` | 當前認證上下文是否允許向該端點提交任務 |
| `reason_code` | 未配置端點時為 `NOT_CONFIGURED`；遠端端點需要可轉發的 OV API Key 時為 `API_KEY_REQUIRED`；其他情況為 `null` |

配置不可用時，在結果中返回 `can_create: false`，不會因此返回 HTTP 錯誤。此介面僅檢查配置和憑證，不探測執行後端的健康狀態，也不校驗具體 Compile 請求。

### 按提交鍵查詢任務

```http
GET /api/v1/compile/submissions/{key}
```

建立任務的響應丟失或超時時，可通過此介面找回任務。傳入的鍵必須與 `POST /api/v1/compile` 請求中可選的 `Idempotency-Key` 請求頭一致。

| 引數 | 位置 | 型別 | 必填 | 說明 |
|------|------|------|------|------|
| `key` | 路徑 | string | 是 | 長度為 16–128 個字元；僅允許字母、數字、`:`、`.`、`_` 和 `-` |

```bash
curl http://localhost:1933/api/v1/compile/submissions/studio-compile-001 \
  -H "X-API-Key: your-key"
```

返回 `200 OK`，其中 `status` 為 `"ok"`，`result` 為已有的 OV 任務記錄，結構與上方建立任務響應一致。查詢範圍限定為當前帳號和使用者，不會建立任務。提交不存在（包括鍵僅被其他使用者使用）時返回 `404`；鍵格式不合法時返回 `422`。

需要安全重試建立請求時，應複用相同的 `Idempotency-Key` 和請求引數。使用同一鍵提交不同引數會返回 `409`。未傳入該請求頭的建立請求，不提供用於此查詢的提交鍵。

### 查詢任務

任務僅對建立它的 principal 可見；任務不存在或屬於其他 principal 時均返回 `404`。

```http
GET /api/v1/tasks/{task_id}
```

```bash
ov task status cmp_01abc
```

任務進入終態後，響應還會包含結果或錯誤。

### 取消任務

```http
POST /api/v1/tasks/{task_id}/cancel
```

```bash
ov task cancel cmp_01abc
```

任務會先進入 `cancelling`，待當前程序內工作和清理完成後進入 `cancelled`；已經完成的寫入不會回滾。重複取消已經 `cancelled` 的任務是冪等的。

| Status | 常見 Stage |
|--------|------------|
| `pending` | `queued` |
| `running` | 執行端返回的執行 Stage，例如 `agent`、`writing` |
| `cancelling` | 收斂當前程序內工作和清理資源 |
| `completed` | `completed`、`salvaged` |
| `failed` | 失敗發生時的 Stage；響應包含 `error` |
| `cancelled` | `cancelled` |

### 舊介面

OV 上的以下舊 VikingBot 代理路由已經停用，只返回遷移提示：

```http
POST /bot/v1/compile
GET /bot/v1/compile/{task_id}
POST /bot/v1/compile/{task_id}/cancel
```

建立任務使用 `/api/v1/compile`，查詢和取消統一使用 `/api/v1/tasks/{task_id}`。

## Runtime 執行介面

以下介面由 `compile_api.base_url` 指向的執行服務提供，供 OV 呼叫。應用通過前述 Compile API 提交任務。

### 建立執行任務

```http
POST /runtime/v1/tasks
Idempotency-Key: <OV task_id>
```

```json
{
  "task_type": "compile",
  "payload": {
    "from": ["viking://resources/research"],
    "to": "viking://resources/research-wiki",
    "skill": "viking://agent/skills/wiki",
    "instruction": "整理成知識庫",
    "args": {"model_name": "your-model-endpoint-id"}
  }
}
```

`task_type` 和 `payload` 均必填。當前只支援 `task_type="compile"`；`payload` 使用本頁建立任務的欄位及校驗規則，`instruction`、`args` 可省略。內建 VikingBot 不支援非空 `args`。不支援的型別或無效的 payload 返回 `4xx`，不建立執行任務。

OV 通過 `X-API-Key` 傳遞當前使用者的 OV API Key；配置 `compile_api.gateway_token` 時還會發送 `X-Gateway-Token`。這些憑證不能出現在公開任務結果中。

接受請求後返回 `202 Accepted`，響應包含執行端標識：

```json
{"session_id": "session-123"}
```

同一使用者的相同 `Idempotency-Key` 必須返回同一個 `session_id`，不能重複執行。`session_id` 用於執行端查詢和取消；應用查詢 OV 任務時使用 `task_id`。

### 查詢與取消執行任務

```http
POST /runtime/v1/tasks/status
POST /runtime/v1/tasks/cancel
```

兩個介面均使用以下請求體：

```json
{"session_id": "session-123"}
```

兩個介面均返回執行狀態，例如：

```json
{
  "status": "running",
  "stage": "compile: agent",
  "error": null,
  "meta": {},
  "result": null
}
```

`status` 可為 `pending`、`running`、`cancelling`、`completed`、`failed` 或 `cancelled`。取消請求可以先返回 `cancelling`，實際執行停止並完成清理後再返回 `cancelled`；重複取消已結束任務返回其當前終態。查詢和取消均須校驗任務歸屬。

## 相關文件

- [後臺任務](17-tasks.md) - 通用任務查詢、取消和列表介面
- [上下文編譯](../context-compilation/01-overview.md) - Compile 使用場景和示例
- [Skills API](04-skills.md) - 管理 Compile 使用的 Skill
