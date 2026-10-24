# Agent Runtime API

應用通過 OpenViking 的 Compile API 提交 Compile 任務。OpenViking 校驗請求，把任務持久化為佇列工作，並在伺服器程序內執行，因此中斷的任務會在重啟後恢復。

**程式碼入口**：

- `openviking/server/routers/compile.py` - 建立 Compile 任務
- `openviking/server/routers/tasks.py` - 查詢和取消任務
- `openviking/service/compile_service.py` - 請求校驗與任務執行
- `openviking/service/external_task_service.py` - 基於持久佇列的任務生命週期
- `openviking/compile/` - Skill 流水線（plan、map、shuffle、reduce、finalize）

## Compile 任務介面

### 建立任務

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `from` | string[] | 是 | - | 一個或多個來源目錄 |
| `to` | string | 是 | - | 目標 Resource 目錄或受支援的 Skill namespace；Memory 目錄請使用 `--skill memory` |
| `skill` | string | 是 | - | Skill 目錄或其 `SKILL.md` URI |
| `instruction` | string | 否 | Skill 驅動的預設值 | 本次 Compile 的補充指令 |
| `args` | object | 否 | - | 可選的 `last_compile_time` 與 `wiki_links`（見下表） |

`args` 只接受以下鍵，其他鍵返回 `400 INVALID_ARGUMENT`：

| 鍵 | 型別 | 說明 |
|----|------|------|
| `last_compile_time` | ISO 8601 時間或 Unix 秒 | 增量編譯：只處理在此時間點及之後修改的來源檔案；沒有更新的檔案時，任務不呼叫模型也不寫入，直接完成 |
| `wiki_links` | boolean | 按實際 Markdown 路徑重建 resource 的 `index.md` |

Compile 使用帳號配置的 `vlm` 模型。Python 示例使用 `SyncHTTPClient`；使用 `AsyncHTTPClient` 時需 `await compile()`。

**HTTP API**

```http
POST /api/v1/compile
```

```bash
curl -X POST http://localhost:1933/api/v1/compile \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -H "Idempotency-Key: studio-compile-001" \
  -d '{
    "from": ["viking://resources/research"],
    "to": "viking://resources/research-wiki",
    "skill": "viking://user/default/skills/research-compiler",
    "instruction": "追蹤歷史進展，並保留支撐證據。",
    "args": {"wiki_links": true}
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
  --args '{"wiki_links":true}'
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
    {"args": {"wiki_links": True}},
)
```

```ts [TypeScript]
const task = await client.compile(
  ["viking://resources/research"],
  "viking://resources/research-wiki",
  "viking://user/default/skills/research-compiler",
  { args: { wiki_links: true } },
);
```

```go [Go]
task, err := client.Compile(
    ctx,
    []string{"viking://resources/research"},
    "viking://resources/research-wiki",
    "viking://user/default/skills/research-compiler",
    &openviking.CompileOptions{
        Args: map[string]any{"wiki_links": true},
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
| `configured` | 伺服器的 Compile 執行環境是否已初始化 |
| `can_create` | 當前認證上下文是否可以提交 Compile 任務 |
| `reason_code` | 執行環境尚未初始化時為 `NOT_CONFIGURED`；其他情況為 `null` |

執行環境不可用時，在結果中返回 `can_create: false`，不會因此返回 HTTP 錯誤。此介面不探測模型健康狀態，也不校驗具體 Compile 請求。

### Compile 路由向量

`POST /api/v1/compile/embeddings` 使用當前認證上下文生成臨時路由文本的向量，不建立索引或保留文本。Compile 本身在程序內呼叫同一邏輯。

請求體：必填 `target_uri`（已存在且有讀取許可權的資源或 Skill 名稱空間目標）；可選 `texts`（字串陣列，預設 `[]`，最多 32 條，每條 1–1024 個字元且不能僅含空白）；可選 `expected_model`（模型指紋，非空值必須與當前模型一致）。

返回 `200 OK`，包含 `status: "ok"` 和 `result: {"model": "...", "vectors": [...]}`。向量按輸入順序排列；`texts` 為空時僅返回模型指紋和空向量陣列。

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

返回 `200 OK`，其中 `status` 為 `"ok"`，`result` 為已有的 OV 任務記錄，結構與上方建立任務響應一致。查詢範圍限定為當前帳號和使用者，不會建立任務。提交不存在（包括鍵僅被其他使用者使用）時返回 `404`；鍵格式不合法時返回 `400 INVALID_ARGUMENT`。

需要安全重試建立請求時，應複用相同的 `Idempotency-Key` 和請求引數。使用同一鍵提交不同引數會返回 `409`。未傳入該請求頭的建立請求，不提供用於此查詢的提交鍵。

### 查詢任務

普通使用者只能查詢自己建立的任務；任務不存在或屬於其他使用者時均返回 `404`。ROOT 查詢使用獨立的管理可見範圍，且不能取消任務。

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

任務會先進入 `cancelling`，待當前程序內工作和清理完成後進入 `cancelled`。Compile 在寫入目標前會檢查取消，因此已取消的任務通常不會寫入；已經完成的寫入不會回滾。重複取消已經 `cancelled` 的任務是冪等的。

| Status | 常見 Stage |
|--------|------------|
| `pending` | `queued` |
| `running` | `running`、`collecting_context`、`pipeline`、`writing`；memory 模式為 `consolidating` |
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

## 執行與重啟恢復

Compile 在 OpenViking 伺服器內執行，方式與 `add_resource` 的處理相同：

- 每個任務是 `ExternalTask` 佇列上的一條持久 QueueFS 訊息，任務結果儲存後才確認（ack）該訊息。
- 任務執行中伺服器停止或崩潰時，下次啟動會重新投遞訊息，任務**從頭重新執行**。中斷那次的部分工作會被丟棄；只有在一次執行結束時才寫入目標，未變化的頁面保持不變。
- 同一目標的任務逐個執行，其他任務在佇列中等待。
- 模型呼叫使用帳號的 `vlm` 配置，並共用伺服器級的 `vlm.max_concurrent` 容量。單任務的各階段並行度在 [`compile_api`](../guides/01-configuration.md#compile_api) 下設定。
- 每個任務最多執行 3 次，`meta.attempts` 記錄次數；被中斷三次的任務以 `INTERRUPTED` 失敗，不會在每次重啟時重新執行。
- 任務以建立者的身份和權限執行，不會隨任務儲存 API Key 或其他憑證。使用 API Key 鑑權時，每次執行前會重新檢查建立者：取提交時與當前角色中較低者，只保留使用者仍所屬的群組；使用者已被刪除時以 `UNAUTHENTICATED` 失敗。
- 每個使用者最多同時有 `compile_api.max_active_tasks_per_user`（預設 10）個待執行或執行中的 Compile 任務，超出返回 `429 RESOURCE_EXHAUSTED`。

`queue_workers.external_task.max_concurrent` 控制同時執行的 Compile 任務數。

## 相關文件

- [後臺任務](17-tasks.md) - 通用任務查詢、取消和列表介面
- [上下文編譯](../context-compilation/01-overview.md) - Compile 使用場景和示例
- [Skills API](04-skills.md) - 管理 Compile 使用的 Skill
