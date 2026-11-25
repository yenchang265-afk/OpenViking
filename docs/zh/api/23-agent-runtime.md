# Agent Runtime API

OpenViking 管理 Compile 配置、執行任務、快照和恢復。它把任務持久化為佇列工作，並在伺服器程序內執行，因此中斷的任務會在重啟後恢復。

**程式碼入口**：

- `openviking/server/routers/compile.py` - Compile 配置與執行
- `openviking/server/routers/tasks.py` - 查詢和取消任務
- `openviking/service/compile_service.py` - 請求校驗與任務執行
- `openviking/service/external_task_service.py` - 基於持久佇列的任務生命週期
- `openviking/compile/` - Skill 流水線（plan、map、shuffle、reduce、finalize）

## Compile 配置與執行

`compile_name` 由呼叫者提供，標識持久配置及其成功增量基線。名稱由漢字、ASCII 字母、數字、下劃線或連字元組成，純 ASCII 名稱最多 64 個字元，含漢字的名稱總長最多 32 個字元，首字元不能是連字元，區分大小寫，在同一 account 的同一使用者內唯一；不同使用者或不同 account 可以使用相同名稱。空白字元直接拒絕，不會自動去除。`task_id` 標識一次已受理的執行，使用 `cmp_` 字首。同一個配置可以多次執行；多個配置可以指向同一個 `to`，各自維護獨立基線和歷史。

普通 Compile 在建立或更新配置、手動或定時提交新執行時，統一校驗規範化後的目錄 URI：

- 每個 `from` 都不能與 `to` 相同，也不能互為祖先或後代。
- `to` 的任何嚴格祖先或後代目錄帶有 `compile_target=true` 時拒絕請求；`to` 自身已有該 tag 時允許複用。
- `to` 不能是 `viking://user/{user_id}/memories/experiences` 或其任意層級子目錄。`~/` 別名和末尾斜槓不能繞過限制；`experiences2` 等相似名稱不被這條規則拒絕。

建立時先取得按帳號隔離的 Compile 專用虛擬樹鎖，再檢查可見索引標籤。補標期間，嚴格父子目標拒絕建立；相同目標共享獨立持有憑證，執行仍按現有流程序列處理。鎖競爭最多等待 1 秒，不等待 Compile 或索引完成。鎖不覆蓋真實產物路徑，由現有補標佇列接管，直到 tag 可查詢或目標路徑消失。服務中斷期間租約可能過期，恢復前仍可能出現受理空窗；租約不提供永久佔位。索引檢查遵循當前請求的租戶和許可權範圍。不傳 `from` 的獨立 `skill="memory"` 就地整理模式不應用這些目錄約束或目標打標流程。

### 建立配置

```http
POST /api/v1/compile/create
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `compile_name` | string | 是 | 呼叫者指定的配置名稱，原樣返回 |
| `from` | string[] | 是 | 非空來源目錄列表 |
| `to` | string | 是 | 呼叫者可寫、與來源不重疊的輸出目錄 |
| `skill` | string | 是 | 可讀的 Skill 目錄或其 `SKILL.md` URI |
| `instruction` | string | 否 | 補充指令；null 使用 Skill 預設行為 |
| `args` | object | 否 | 可選 `wiki_links`、`owner_user_id` 和 `auto_update` / `update_schedule` 控制；其他鍵返回 `400 INVALID_ARGUMENT` |

```bash
curl -X POST http://localhost:1933/api/v1/compile/create \
  -H 'Content-Type: application/json' -H 'X-API-Key: your-key' \
  -d '{
    "compile_name": "research-summary",
    "from": ["viking://resources/research"],
    "to": "viking://resources/research-wiki",
    "skill": "viking://agent/skills/llm-wiki",
    "instruction": "整理成保留證據引用的中文知識庫。",
    "args": {
      "auto_update": true,
      "update_schedule": {"frequency": "daily", "hour": 10, "minute": 0}
    }
  }'
```

返回 `200 OK`：

```json
{"status":"ok","result":{"compile_name":"research-summary"}}
```

缺少 `compile_name` 或名稱非法時直接報錯，服務端不會生成備用名稱。同一 account 的同一使用者重名建立（包括併發建立）返回衝突，不覆蓋配置或增量基線；不同使用者可以建立同名配置。配置名稱不支援修改。

`args.owner_user_id` 可選，用於選擇當前 account 內的配置歸屬使用者，省略時使用當前認證使用者。建立、更新和按名稱執行統一使用該引數；它只決定配置歸屬或定位，不改變執行身份、不授予資料訪問許可權，也不進入儲存的 Runtime 引數。`args.owner_id` 不再用於選擇配置歸屬使用者。

建立介面同步校驗輸入、許可權及可見的目錄標籤，必要時建立 `to`，並持久入隊獨立的內部補標 Task；不等待目錄索引、embedding 或 tag 可見性。`to` 是檔案或內部任務未能持久入隊時返回錯誤。QueueFS 消費者負責根目錄索引和 `compile_target=true` 補齊，失敗後重試，不遞迴標記子目錄，並保留已有內容、摘要和其他 tag。目標路徑不存在時停止該路徑的補標，不重建目錄。建立配置本身不執行 Compile、不建立 run、不拍來源快照。

排程控制與 Runtime 引數分開儲存。非空計劃預設開啟自動更新，除非顯式指定 `auto_update=false`。計劃必填 `frequency`（`daily` 或 `weekly`），使用北京時間（`Asia/Shanghai`）。

只傳頻率時，服務端在 00:00–03:59 中為計劃分配固定時間。每週計劃省略 `weekday` 時也會分配固定執行日（1 為週一，7 為週日）。只傳 `hour`（0–23）時，在該小時內分配固定分鐘，例如 `hour: 10` 對應 10:00–10:59。只傳 `minute`（0–59）時，小時取 0。查詢配置的 `update_schedule` 可檢視分配結果。

定時執行要求開啟 `compile_api.scheduler_enabled=true` 並配置 Redis expiry 服務。憑據加密儲存，每次觸發時重新驗證憑據及當前使用者組許可權。排程未啟用或不可用時返回錯誤，不會退化為立即執行。停用計劃後 `next_triggered_slot` 為 null。

### 執行編譯

```http
POST /api/v1/compile
```

只接受以下兩種互斥請求：

```json
{"compile_name":"research-summary"}
```

```json
{
  "from":["viking://resources/research"],
  "to":"viking://resources/research-wiki",
  "skill":"viking://agent/skills/llm-wiki",
  "instruction":"整理成保留證據引用的中文知識庫。",
  "args":{}
}
```

執行 Compile 時傳入 `compile_name`，會複用該配置中已儲存的 `from`、`to`、`skill` 和 `instruction`。

直接提交 `from`、`to` 和 Skill URI 的寫法已棄用。受理時，`Deprecation` 和 `Link` 響應頭提供棄用日期和遷移指南。請先將這些輸入連同 `compile_name` 提交到 `POST /api/v1/compile/create`，再向 `POST /api/v1/compile` 僅提交 `compile_name`。

傳完整輸入時始終執行一次性全量編譯，即使同一輸出目錄已有持久配置，也不查詢、複用或更新配置。不讀寫 compile 配置和 run 檔案、不拍來源快照；目標開始/結束快照、取消和失敗恢復仍然執行。`skill="memory"` 保留不傳 `from` 的獨立就地整理行為，不支援通過建立介面儲存配置或開啟定時執行。

兩種普通執行形式都先完成目標校驗、必要的目錄建立及獨立補標任務持久入隊，再提交 Compile 執行任務。後臺索引或 tag 延遲不阻塞 Compile 提交、產物寫入或收尾，也不使 Compile 因補標失敗而失敗。受理成功不代表 tag 已可查詢，補標期間由上述虛擬樹鎖保護目標。Compile 的顯式開始/結束快照、產物 `snapshot_id`、Outputs 和回滾流程保持原有語義。該 tag 是目錄檢索標記，任務完成、失敗或取消不會自動移除它。

執行介面拒絕排程控制。`args.mode`、`last_compile_time`、`changes` 和 `operation_id` 不是公開執行引數；執行計劃由 OpenViking 生成。

每次成功受理均返回 `202 Accepted` 和通用 TaskRecord：

```json
{
  "status":"ok",
  "result":{
    "task_id":"cmp_0123456789abcdef",
    "task_type":"compile",
    "status":"pending",
    "stage":"queued",
    "resource_id":"viking://resources/research-wiki"
  }
}
```

執行重試可使用 `Idempotency-Key`；查詢和取消使用 `/api/v1/tasks/{task_id}`。手動執行使用當前呼叫者的許可權和連線，不借用儲存的排程憑據。

源目錄被刪除或移動後，新執行在建立任務前返回 HTTP `404` / `NOT_FOUND`。錯誤標明缺失的 Viking URI，`details.type="compile source directory"`，並提示修改配置中的源目錄後重試；許可權錯誤保持獨立。使用相同 `Idempotency-Key` 恢復已有提交時，不重新校驗源目錄。

### CLI 與 SDK

```bash
ov compile create --compile-name research-summary --from viking://resources/research \
  --to viking://resources/research-wiki --skill viking://agent/skills/llm-wiki \
  --args '{"auto_update":true,"update_schedule":{"frequency":"daily","hour":10}}'
ov compile --compile-name research-summary
```

`--args` 是 JSON 物件。建立必須傳入 `--compile-name` 並返回該配置名稱；兩種執行方式都返回任務 ID。

::: code-group

```python [Python]
created = client.create_compile_task(
    ["viking://resources/research"],
    "viking://resources/research-wiki",
    "viking://agent/skills/llm-wiki",
    compile_name="research-summary",
)
task = client.compile(compile_name=created["compile_name"])
```

```ts [TypeScript]
const created = await client.createCompileTask({
  compile_name: "research-summary",
  from: ["viking://resources/research"],
  to: "viking://resources/research-wiki",
  skill: "viking://agent/skills/llm-wiki",
});
const task = await client.compile({ compile_name: created.compile_name });
```

```go [Go]
created, err := client.CreateCompileTask(ctx, "research-summary", openviking.CompileInput{
    FromURIs: []string{"viking://resources/research"},
    To: "viking://resources/research-wiki",
    Skill: "viking://agent/skills/llm-wiki",
})
if err != nil { return err }
task, err := client.Compile(ctx, openviking.CompileRequest{CompileName: created["compile_name"].(string)})
```

:::

Python 示例使用 `SyncHTTPClient`；使用 `AsyncHTTPClient` 時新增 `await`。

### 配置與執行歷史

| HTTP API | 結果 |
|----------|------|
| `GET /api/v1/compile/config?compile_name={compile_name}` | 公開配置輸入、排程、建立與執行時間 |
| `POST /api/v1/compile/config/update` | 按請求體 `compile_name` 替換配置 |
| `GET /api/v1/compile/configs` | `configs` 和 `next_cursor`；按配置名稱的字典序劃分頁，每頁內部按 `last_run_time` 倒序排列（null 置後） |
| `GET /api/v1/compile/runs?compile_name={compile_name}` | `runs` 和 `next_cursor`，按 `created_at`、`task_id` 從新到舊排序 |
| `GET /api/v1/compile/runs/{task_id}?compile_name={compile_name}` | 本次執行凍結的 run |
| `GET /api/v1/compile/runs/{task_id}/outputs?compile_name={compile_name}` | 由本次快照推導的變更產出，包含 `outputs` 和 `next_cursor` |

執行歷史查詢按當前帳號和使用者限定範圍。runs 目錄不存在時返回空列表；指定 run 不存在時，詳情和產出介面返回 404。

列表接受 `limit`（1–100，預設 20）及可選 `cursor`。原樣傳遞 `next_cursor`；null 表示結束。產出項包含 `uri`、`snapshot_id`、`latest_snapshot_id`、`change_type`。`snapshot_id` 固定為本次 run 的產出快照；`latest_snapshot_id` 為查詢時該檔案最近變更的 commit，無歷史時為 null。最近變更可能是後續刪除，此時讀取該版本正文返回 404。僅查詢本頁產出的檔案歷史，查詢失敗直接報錯。

配置更新必填 `compile_name`、`from`、`skill` 和頂層 `auto_update`，可選 `instruction`、`args` 替換已儲存值。`to` 可選，省略或為 null 時沿用該配置已儲存的目標目錄；顯式傳入的 `to` 規範化後必須與已儲存的目標目錄一致，修改目標目錄返回 `400 INVALID_ARGUMENT`，配置保持不變；`from`、`skill` 等其他引數仍可修改。頂層 `update_schedule` 省略或為 null 時保留已儲存的計劃。啟用自動更新需要本次提供或已儲存的計劃；關閉時保留計劃，清除執行憑據和下次觸發時間，並取消排程註冊，是否啟用計劃由 `auto_update` 決定。更新請求的 `args` 不接受排程控制。更新配置保留上次成功執行的 `progress`。執行時比較指令、Skill 及其快照、`model_name`，不一致時全量編譯；已有源目錄計算增量，新增源目錄完整處理。更新同樣校驗目錄約束並持久入隊獨立補標任務，不等待 tag 就緒。配置更新不執行編譯、不重置呼叫時間。

建立配置時，`state.json` 的頂層欄位 `updated_by` 記錄配置歸屬使用者的 ID。更新時可在請求體頂層傳入字串 `updated_by` 指定記錄的值，省略時記錄當前認證使用者的 ID。

巢狀 `args` 的私有欄位在公開響應中脫敏並加密儲存供執行使用：公開引數不變時保留私有值，修改含私有欄位的巢狀子樹時須重新傳入這些私有欄位，刪除子樹則同時刪除其儲存的私有值。

建立與執行時間使用 Unix 秒。

- `task_first_create_time` 記錄 `POST /api/v1/compile/create` 儲存配置的時間，儲存後保持固定。
- `last_run_time` 記錄最近一次成功受理的新 task 的 `created_at`。首次受理前為 null。後續失敗或取消不回退，冪等重放不重新整理。

手動與定時提交均更新 `last_run_time`。`last_triggered_slot`、`next_triggered_slot` 僅用於排程，手動執行不推進 slot。

run 凍結儲存 `task_id`、`actor`、`status`、`created_at`、`started_at`、`finished_at`、`params`、`result`、`error`、`meta`。`params` 是本次受理時的完整公開輸入及排程配置；`result` 包含 `created`、`updated`、`deleted` 數量。`meta` 僅包含：

| 欄位 | 含義 |
|------|------|
| `trigger` | 配置的第一次受理執行為 `initial`，與觸發來源和執行結果無關；後續執行為 `manual` 或 `scheduled` |
| `mode` | 實際執行策略：`full` 或 `incremental` |
| `base_snapshot` | 本次採用的成功源基線；完整重算時為 null |
| `start_snapshot` | 執行開始時凍結的來源及目標狀態 |
| `finish_snapshot` | 釋出或回滾完成後保留的目標快照；尚未提交時為 null |
| `skill_snapshot_id` | Skill 快照；系統 Skill 為 null |

無變化時可複用開始快照。失敗、取消不推進成功源基線。執行計劃及必要恢復檢查點儲存在私有 Task 狀態；公共配置、run 和 Task 不暴露執行憑據。

VikingBot 在已知來源、worker 或寫入失敗仍未解決時返回 `result.completion_status: "partial"`。
已確認輸出會保留，命名 Compile 保留原成功源基線，使遺漏且未再次變化的輸入仍能進入下一輪。
其他結果省略該標記；沒有標記不代表語義覆蓋完整或索引成功。

Compile 業務檔案僅有：

```text
/local/{account_id}/_system/compile/tasks/{user_id}/{configuration_directory}/state.json
/local/{account_id}/_system/compile/tasks/{user_id}/{configuration_directory}/runs/{task_id}.json
```

純 ASCII 名稱的小寫十六進位制編碼用作 `configuration_directory`。含漢字的名稱使用 `u-` 加上名稱 UTF-8 位元組的小寫 Base32 編碼作為目錄名，省略末尾的填充符 `=`。兩種目錄格式在不區分大小寫的儲存上都能區分名稱大小寫。

配置按帳號和使用者分目錄儲存，公開 API 使用原始 `compile_name` 定位配置。

state 的精確欄位為 `from`、`to`、`skill`、`instruction`、`args`、`auto_update`、`update_schedule`、`task_first_create_time`、`last_run_time`、`last_triggered_slot`、`next_triggered_slot`、`progress`、`updated_by`、`execution_context`。`progress` 儲存成功增量基線，其中 `model_name` 記錄成功執行請求的模型名，未指定時為空字串；`execution_context` 儲存內部執行上下文和加密引數。

Compile 成功收尾時釋出產物快照。完整交付且目標有檔案新增、修改或刪除時推進增量基線。部分交付後的增量恢復也可在目標零變更時推進基線，但僅限本輪所有新增或修改的來源均已處理，且能核對實際讀取內容與凍結源快照一致。涉及未驗證來源、刪除或全量掃描時，零變更結果保留原基線。回滾後為恢復和刪除的路徑排程索引重建，不等待重建完成。

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

### Compile 路由向量

`POST /api/v1/compile/embeddings` 使用當前認證上下文生成臨時路由文本的向量，不建立索引或保留文本。

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

執行中的 Compile 任務進入 `cancelling`，直到執行停止並完成必要清理。恢復使用凍結的目標開始快照，隻影響 `to`，不恢復來源目錄。釋出或回滾完成後才能收斂終態；失敗或取消不推進成功增量基線。重複取消已經取消的任務是冪等的。

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

## 執行與重啟恢復

Compile 在 OpenViking 伺服器內執行，方式與 `add_resource` 的處理相同：

- 每個任務是 `ExternalTask` 佇列上的一條持久 QueueFS 訊息，任務結果儲存後才確認（ack）該訊息。
- 任務執行中伺服器停止或崩潰時，下次啟動會重新投遞訊息，任務**從頭重新執行**。中斷那次的部分工作會被丟棄；只有在一次執行結束時才寫入目標，未變化的頁面保持不變。
- 同一目標的任務逐個執行，其他任務在佇列中等待。
- 模型呼叫使用帳號的 `vlm` 配置，並共用伺服器級的 `vlm.max_concurrent` 容量。單任務的各階段並行度在 [`compile_api`](../guides/01-configuration.md#compile-api) 下設定。
- 每個任務最多執行 3 次，`meta.attempts` 記錄次數；被中斷三次的任務以 `INTERRUPTED` 失敗，不會在每次重啟時重新執行。
- 任務以建立者的身份和權限執行，不會隨任務儲存 API Key 或其他憑證。使用 API Key 或 trusted 鑑權時，每次執行前會重新檢查建立者：只保留使用者仍所屬的群組；使用者正在刪除或帳號不再處於啟用狀態時以 `UNAUTHENTICATED` 失敗。API Key 鑑權還會取提交時與當前角色中較低者，並在使用者已被刪除時失敗。失敗執行的暫存檔保留 7 天，並隨使用者或帳號一併刪除。重啟後，恢復的任務會等鑑權就緒後再執行。
- 每個使用者最多同時有 `compile_api.max_active_tasks_per_user`（預設 10）個待執行或執行中的 Compile 任務，超出返回 `429 RESOURCE_EXHAUSTED`。

`queue_workers.external_task.max_concurrent` 控制同時執行的 Compile 任務數。

## 相關文件

- [後臺任務](17-tasks.md) - 通用任務查詢、取消和列表介面
- [上下文編譯](../context-compilation/01-overview.md) - Compile 使用場景和示例
- [Skills API](04-skills.md) - 管理 Compile 使用的 Skill
