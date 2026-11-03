# 內容

內容 API 負責讀取 L0/L1/L2 內容、寫入文本，以及維護內容對應的語義和向量索引。

## API 參考

### abstract()

讀取 L0 摘要，不包括 OKF 檔案頭。目錄摘要的預設字元上限為 256；字元數不等於 token 數。

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| uri | str | 是 | - | Viking URI（必須是目錄） |


**Python SDK**

```python
abstract = client.abstract(uri="viking://resources/docs/")
print(f"Abstract: {abstract}")
# Output: "Documentation for the project API, covering authentication, endpoints..."
```

**TypeScript SDK**

```typescript
const abstract = await client.abstract("viking://resources/docs/");
console.log(abstract);
```

**Go SDK**

```go
abstract, err := client.Abstract(ctx, "viking://resources/docs/")
if err != nil {
    return err
}
fmt.Println(abstract)
```

**HTTP API**

```
GET /api/v1/content/abstract?uri={uri}
```

```bash
curl -X GET "http://localhost:1933/api/v1/content/abstract?uri=viking://resources/docs/" \
  -H "X-API-Key: your-key"
```

**CLI**

```bash
ov abstract viking://resources/docs/
```


**響應**

```json
{
  "status": "ok",
  "result": "Documentation for the project API, covering authentication, endpoints..."
}
```

---

### overview()

讀取 L1 概覽，適用於目錄，不包括 okf 檔案頭。

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| uri | str | 是 | - | Viking URI（必須是目錄） |


**Python SDK**

```python
overview = client.overview(uri="viking://resources/docs/")
print(f"Overview:\n{overview}")
```

**TypeScript SDK**

```typescript
const overview = await client.overview("viking://resources/docs/");
console.log(overview);
```

**Go SDK**

```go
overview, err := client.Overview(ctx, "viking://resources/docs/")
if err != nil {
    return err
}
fmt.Println(overview)
```

**HTTP API**

```
GET /api/v1/content/overview?uri={uri}
```

```bash
curl -X GET "http://localhost:1933/api/v1/content/overview?uri=viking://resources/docs/" \
  -H "X-API-Key: your-key"
```

**CLI**

```bash
ov overview viking://resources/docs/
```


**響應**

```json
{
  "status": "ok",
  "result": "## docs/\n\nContains API documentation and guides..."
}
```

---

### read()

讀取 L0/L1/L2 檔案完整文本內容。

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| uri | str | 是 | - | Viking URI（如 `viking://resources/docs/api.md`）或 32 字元十六進位制向量記錄 `id`（由 `stat()` 返回） |
| offset | int | 否 | 0 | 起始行號（0 開始） |
| limit | int | 否 | -1 | 讀取的行數，`-1` 表示讀到結尾 |
| raw | bool | 否 | false | 跳過預設脫敏和 MEMORY_FIELDS 過濾，並嘗試還原佔位符；Python 中使用 `client.read_raw(uri)`。 |

**說明**

- `read()` 只接受檔案 URI。傳入已存在的目錄時返回 `INVALID_ARGUMENT`（HTTP `400`）。HTTP 響應的 `details` 包含 `expected: "file"`、`actual: "directory"` 和目標 `resource` URI，客戶端可據此改用目錄列表介面，無需解析錯誤訊息。
- 除 Viking URI 外，還可以傳入 `stat()` 返回的 32 字元十六進位制檔案 `id`。服務端通過向量索引查詢對應 URI 並執行相同的許可權校驗。由於索引是非同步生成的，新返回的 ID 可能暫時無法解析；對應向量記錄被刪除後，按 ID 查詢也會失敗。這兩種情況下，服務端都會返回 `NOT_FOUND`，並提示資料可能尚未索引或已經刪除。
- 公開 URI 引數接受 `resources`、`user` 和 `agent` 作用域。訪問 session 檔案時，使用 `viking://user/{user_id}/sessions/{session_id}/messages.jsonl`，或表示當前使用者的 `viking://~/sessions/{session_id}/messages.jsonl`。舊的 `viking://session/...` 以及 `temp`、`queue` 等內部作用域會返回 `INVALID_URI`。
- 敏感資訊的處理：預設讀取（`raw=false`）保留已有佔位符，並對殘留的已登記明文脫敏；`raw=true` 跳過預設脫敏，返回載入還原後的內容，該還原隻影響返回內容，不修改儲存檔案，詳見[隱私配置](../concepts/13-privacy.md)。

**Python SDK**

```python
content = client.read(uri="viking://resources/docs/api.md")
print(f"Content:\n{content}")
```

**TypeScript SDK**

```typescript
const content = await client.read("viking://resources/docs/api.md", 0, -1);
console.log(content);
```

**Go SDK**

```go
content, err := client.Read(ctx, "viking://resources/docs/api.md", 0, -1)
if err != nil {
    return err
}
fmt.Println(content)
```

**HTTP API**

```
GET /api/v1/content/read?uri={uri}
```

```bash
curl -X GET "http://localhost:1933/api/v1/content/read?uri=viking://resources/docs/api.md" \
  -H "X-API-Key: your-key"
```

**CLI**

```bash
ov read viking://resources/docs/api.md
```


**響應**

```json
{
  "status": "ok",
  "result": "# API Documentation\n\nFull content of the file..."
}
```

---

### write()

寫入檔案，並自動重新整理相關語義與向量。

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| uri | str | 是 | - | 要寫入的檔案 URI |
| content | str | 是 | - | 要寫入的新內容 |
| mode | str | 否 | `replace` | `replace` 覆蓋已有檔案、缺失時建立；`append` 追加已有檔案、缺失時建立；`create` 是 `replace` 的相容別名 |
| wait | bool | 否 | `false` | 是否等待後臺語義/向量重新整理完成 |
| timeout | float | 否 | None | 已廢棄：僅為相容舊請求保留，傳入值會被忽略；HTTP 超時使用客戶端配置 |
| tags | string[] | 否 | 未設定 | 寫入檔案的顯式檢索標籤，例如 `["team=search", "env=prod"]` |
| tag_mode | string | 否 | `replace` | 標籤更新方式：`replace` 覆蓋、`append` 按 key 合併、`clear` 清空已有標籤且不要求傳 `tags` |
| resolve_conflicts | bool | 否 | false | 解決衝突 |

**說明**

- `replace`、`append` 和作為相容別名的 `create` 都會在目標缺失時建立檔案；`append` 會以傳入內容作為新檔案的初始內容，其他情況下 `create` 與 `replace` 完全相同。目錄始終會被拒絕。
- 使用任意模式建立缺失檔案時，都只允許以下文本類副檔名：`.md`、`.txt`、`.json`、`.yaml`、`.yml`、`.toml`、`.py`、`.js`、`.ts`。所有寫入模式都會自動建立父目錄。
- 已存在的 `.abstract.md` / `.overview.md` 可以修改正文，但不能通過公共 API 建立；只提交正文時會保留現有 OKF metadata，提交完整 OKF 時 metadata 必須與存量值一致。未知 metadata 欄位會靜默丟棄。sidecar 正文寫入只重建該目錄實際存在的 L0/L1 向量，不觸發語義重新生成。
- 檔案內容會在 API 返回前完成更新；`wait` 只控制是否等待語義/向量重新整理完成。
- 正文提交後，如果後續語義/向量任務入隊失敗，不會回滾已寫正文；介面會返回錯誤，呼叫方應重試同一次 write 以重新派發派生維護。顯式 write 始終重新提交最終位元組，因此在向量索引暫時落後於檔案時也能安全重試。
- 公共 API 已不再接受 `regenerate_semantics` 或 `revectorize`；寫入後會自動排程相關語義與向量處理。
- 資源寫入附帶的父目錄 L0/L1 重新整理採用盡力更新：父目錄鎖衝突時跳過本次目錄重新整理，保留原文寫入及檔案自身的摘要、向量處理。跳過 L0/L1 寫回時也跳過目錄向量更新，不保證自動補刷；原文檔案本身的鎖衝突仍報錯。提交任務前發現衝突時返回 `semantic_status: "skipped"`；後臺執行期間的跳過記錄在日誌中，`wait=true` 也不保證父目錄摘要更新。
- 提供非空 `tags` 時，標籤會在該檔案首次向量 upsert 時寫入，而非在處理完成後再單獨更新。省略 `tags`，或顯式傳 `tags: []` 配合 `tag_mode: "replace"`，都不會修改已有標籤。使用 `tag_mode: "clear"` 可清空全部已有標籤，且 `clear` 會忽略同時傳入的標籤值。
- `resolve_conflicts=true` 表示編輯目的是進行衝突解決。


**Python SDK**

```python
result = client.write(
    uri="viking://resources/docs/api.md",
    content="# Updated API\n\nFresh content.",
    mode="replace",
    options={"tags": ["team=search", "env=prod"], "tag_mode": "replace"},
)
print(result["root_uri"])
```

**TypeScript SDK**

```typescript
await client.write("viking://resources/docs/new.md", "# New document\n", {
  tags: ["team=search", "env=prod"],
  tagMode: "replace",
});
```

**Go SDK**

```go
result, err := client.Write(
    ctx,
    "viking://resources/docs/api.md",
    "# Updated API\n\nFresh content.",
    &openviking.WriteOptions{
        Mode: "replace",
        Tags: []string{"team=search", "env=prod"},
        TagMode: "replace",
    },
)
if err != nil {
    return err
}
fmt.Println(result["root_uri"])
```

**HTTP API**

```
POST /api/v1/content/write
```

```bash
curl -X POST "http://localhost:1933/api/v1/content/write" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "uri": "viking://resources/docs/api.md",
    "content": "# Updated API\n\nFresh content.",
    "mode": "replace",
    "tags": ["team=search", "env=prod"],
    "tag_mode": "replace"
  }'
```

**CLI**

```bash
ov write viking://resources/docs/api.md \
  --content $'# Updated API\n\nFresh content.' \
  --tags team=search,env=prod \
  --tag-mode replace
```


**`wait=true` 且重新整理完成時的響應**

```json
{
  "status": "ok",
  "result": {
    "uri": "viking://resources/docs/api.md",
    "root_uri": "viking://resources/docs",
    "context_type": "resource",
    "mode": "replace",
    "written_bytes": 29,
    "content_updated": true,
    "semantic_status": "complete",
    "vector_status": "complete",
    "queue_status": {
      "Semantic": {
        "processed": 1,
        "error_count": 0,
        "errors": []
      },
      "Embedding": {
        "processed": 2,
        "error_count": 0,
        "errors": []
      }
    }
  }
}
```

---

### batch_write()

在一個 Resource 或 Memory 目錄下寫入多個檔案；全部寫完後，再統一重新整理一次受影響的語義與向量索引。

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `root_uri` | string | 是 | - | 包含所有寫入目標的已存在 Resource 或 Memory 目錄 |
| `operations` | array | 是 | - | 要校驗並執行的檔案寫入 |
| `wait` | boolean | 否 | `true` | 是否等待語義/向量重新整理 |
| timeout | float | 否 | None | 已廢棄：僅為相容舊請求保留，傳入值會被忽略；HTTP 超時使用客戶端配置 |
| `telemetry` | boolean/object | 否 | `false` | 是否返回操作遙測資訊 |
| `processing_mode` | string | 否 | `semantic_and_vectors` | 整批統一的處理模式：`semantic_and_vectors` 或 `vectors_only` |
| `defer_processing` | boolean | 否 | `false` | 只儲存檔案，不派發語義和向量處理；後處理由呼叫方安排 |

每個 operation 包含：

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `uri` | string | 是 | 位於 `root_uri` 下的目標檔案 URI |
| `content` | string | 條件必填 | UTF-8 文本；與 `content_base64` 必須且只能提供一個 |
| `content_base64` | string | 條件必填 | Base64 編碼的位元組；Memory 目標不支援 |
| `mode` | string | 否 | `replace`（預設）、`append`、`create` 或 `upsert` |
| `tags` | string[] | 否 | - | 該檔案的顯式檢索標籤 |
| `tag_mode` | string | 否 | `replace` | 該檔案標籤寫入方式：`replace`、`append` 或 `clear` |
| `acl` | object | 否 | - | 該檔案的直接 ACL；需要該檔案的 manage 許可權 |

**說明**

- 不設定 operation 數量、單檔案大小或總內容大小的應用層上限。
- 所有目標必須是 `root_uri` 下的檔案、屬於同一 context type，且 canonical URI 不能重複。
- Resource 目標允許任意安全副檔名；Memory 目標仍使用文本副檔名白名單，且不接受二進位制內容。
- `create`、`replace`、`upsert` 是“寫成請求最終正文”的相容寫法：檔案存在時覆蓋，缺失時建立。`append` 在檔案存在時追加，檔案缺失時以請求正文建立檔案。
- `processing_mode` 對整個 batch 生效，不能在不同 operation 中混用語義模式；`vectors_only` 不重新整理父目錄語義，只維護變化檔案的向量。
- `tags`、`tag_mode` 與 `acl` 按 operation 生效；tags 會隨該檔案首次向量 upsert 寫入，`clear` 不要求傳 `tags` 並會忽略同時傳入的標籤值。
- 整批先獲取所有目標檔案的精確鎖，再校驗檔案狀態並寫入；同一目錄下不涉及相同檔案的寫入可以並行，重疊檔案的寫入或父目錄刪除、移動仍會衝突。未啟用延遲模式時，非同步處理持有檔案鎖直到關聯工作結束，統一重新整理受影響的 `.overview.md` / `.abstract.md`。
- 資源父目錄重新整理與 `write()` 一樣採用盡力更新：L0/L1 鎖衝突時跳過目錄重新整理及對應目錄向量更新，保留原文和檔案自身的處理，不保證自動補刷。
- 底層 I/O 中途失敗時，本批次較早完成的寫入仍可能已經可見。
- 已存在的 `.abstract.md` / `.overview.md` 可以 replace 或 append；系統會保留並校驗受保護的 OKF metadata，並只重建對應目錄實際存在的 L0/L1 向量。
- 響應體中，通過 `semantic_status`（`queued`、`complete`、`deferred` 或 `skipped`）表達按直接父目錄聚合的狀態；只有所有父目錄都未入隊時才為 `skipped`，某一個目錄因鎖衝突跳過不會掩蓋其他目錄已入隊的工作。`vector_status` 表達變化檔案的向量維護狀態。
- 若正文已提交但非同步重新整理入隊失敗，正文不會回滾。可使用相同最終正文通過 `replace`、`create` 或 `upsert` 重寫；不要直接重放已經成功過的 `append`，否則會重複追加。

**Python SDK**

```python
result = client.batch_write(
    root_uri="viking://resources/wiki",
    operations=[
        {
            "uri": "viking://resources/wiki/new.md",
            "content": "# 新頁面\n",
            "mode": "upsert",
        },
        {
            "uri": "viking://resources/wiki/existing.md",
            "content": "# 更新後的頁面\n",
            "mode": "upsert",
        },
    ],
    wait=True,
)
```

**TypeScript SDK**

```typescript
const result = await client.batchWrite("viking://resources/wiki", [
  {
    uri: "viking://resources/wiki/new.md",
    content: "# New page\n",
    mode: "upsert",
  },
]);
console.log(result);
```

**Go SDK**

```go
content := "# New page\n"
result, err := client.BatchWrite(ctx, "viking://resources/wiki", []openviking.BatchWriteOperation{
    {URI: "viking://resources/wiki/new.md", Content: &content, Mode: "upsert"},
}, nil)
if err != nil {
    return err
}
fmt.Println(result)
```

**HTTP API**

```
POST /api/v1/content/batch-write
```

```bash
curl -X POST http://localhost:1933/api/v1/content/batch-write \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "root_uri": "viking://resources/wiki",
    "operations": [
      {
        "uri": "viking://resources/wiki/new.md",
        "content": "# 新頁面\n",
        "mode": "upsert"
      }
    ],
    "wait": true
  }'
```

**`wait=true` 且重新整理完成時的響應**

```json
{
  "status": "ok",
  "result": {
    "root_uri": "viking://resources/wiki",
    "created": ["viking://resources/wiki/new.md"],
    "updated": [],
    "unchanged": [],
    "semantic_status": "complete",
    "vector_status": "complete",
    "queue_status": {
      "Semantic": {
        "processed": 1,
        "error_count": 0,
        "errors": []
      }
    }
  }
}
```

CLI 當前不直接提供批次寫入命令。

---

### download()

以原始位元組流下載檔案，適用於圖片、PDF 和其他非文本內容。響應使用 `application/octet-stream`，並通過 `Content-Disposition` 返回檔名。

| 引數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `uri` | string | 是 | 要下載的檔案 URI |

**Python SDK**

```python
from pathlib import Path

Path("logo.png").write_bytes(
    client.download_bytes("viking://resources/images/logo.png")
)
```

**TypeScript SDK**

```typescript
import { writeFile } from "node:fs/promises";

const bytes = await client.downloadBytes("viking://resources/images/logo.png");
await writeFile("logo.png", bytes);
```

**Go SDK**

```go
// Requires the os package.
data, err := client.DownloadBytes(ctx, "viking://resources/images/logo.png")
if err != nil {
    return err
}
if err := os.WriteFile("logo.png", data, 0600); err != nil {
    return err
}
```

**HTTP API**

```http
GET /api/v1/content/download?uri={uri}
```

```bash
curl --get http://localhost:1933/api/v1/content/download \
  -H "X-API-Key: your-key" \
  --data-urlencode "uri=viking://resources/images/logo.png" \
  --output logo.png
```

**CLI**

```bash
ov get viking://resources/images/logo.png ./logo.png
```

**響應**

成功時返回 HTTP `200` 和檔案原始位元組，不使用標準 JSON 響應包：

```http
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Disposition: attachment; filename*=UTF-8''logo.png

<binary body>
```

`ov get <uri> <local-path>` 通過上述 HTTP API 下載檔案並寫入本地路徑。

---

### ensure_directory_index()

確保一個既有目錄的語義索引就緒，保留已有 L0/L1 內容和標籤。僅當 `.abstract.md` 和 `.overview.md` 都不存在時，使用 `fallback_abstract` 建立 L0。已有摘要保持不變，只補缺失索引，不呼叫 LLM。目標為檔案、namespace 不支援語義索引、摘要為空或格式損壞、無許可權時返回錯誤。

**Python SDK**

```python
result = client.ensure_directory_index(
    uri="viking://resources/project/",
    fallback_abstract="This is the compile generated folder",
    wait=True,
)
client.set_tags(
    uri="viking://resources/project/",
    tags=["compile_target=true"],
    mode="append",
    recursive=False,
)
```

TypeScript 對應 `client.ensureDirectoryIndex(uri, fallbackAbstract, { wait: true })`；Go 對應 `client.EnsureDirectoryIndex(ctx, uri, fallbackAbstract, nil)`，預設等待索引就緒。

**HTTP API**

```http
POST /api/v1/content/ensure_directory_index
Content-Type: application/json

{
  "uri": "viking://resources/project/",
  "fallback_abstract": "This is the compile generated folder",
  "wait": true
}
```

`uri` 和非空的 `fallback_abstract` 必填。`wait` 預設 `true`，返回時確認已有摘要對應的全部索引層可讀取。`wait=false` 時缺失索引進入佇列，結果包含 `task_id`；`indexed_levels` 只列出響應時已經可讀取的層。介面檢查目錄寫許可權，不處理子目錄。

**響應**

```json
{
  "status": "ok",
  "result": {
    "uri": "viking://resources/project",
    "created_abstract": true,
    "indexed_levels": [0],
    "vector_status": "complete"
  }
}
```

---

### set_tags()

設定用於檢索過濾的顯式 `k=v` 標籤。`replace` 替換已有標籤，`append` 追加標籤，`clear` 顯式清空已有標籤；對目錄設定 `recursive=true` 時會更新目錄下的檔案。省略 `tags` 或傳入空陣列配合 `replace` 都是 no-op；只有 `clear` 會清空，且會忽略同時傳入的標籤值。

**Python SDK**

```python
result = client.set_tags(
    uri="viking://resources/project/",
    tags=["team=search", "env=prod"],
    mode="replace",
    recursive=True,
)
```

**TypeScript SDK**

```typescript
const result = await client.setTags(
  "viking://resources/project/",
  ["team=search", "env=prod"],
  { mode: "replace", recursive: true },
);
```

**Go SDK**

```go
result, err := client.SetTags(
    ctx,
    "viking://resources/project/",
    []string{"team=search", "env=prod"},
    &openviking.SetTagsOptions{Mode: "replace", Recursive: true},
)
```

**HTTP API**

```http
POST /api/v1/content/set_tags
Content-Type: application/json
```

```bash
curl -X POST http://localhost:1933/api/v1/content/set_tags \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "uri":"viking://resources/project/",
    "tags":["team=search","env=prod"],
    "mode":"replace",
    "recursive":true
  }'
```

`POST /api/v1/fs/attrs/set_tags` 是等價相容路徑，當前 Python、TypeScript、Go SDK 和 CLI 使用該路徑。

**CLI**

```bash
ov set-tags viking://resources/project/ \
  --tags team=search,env=prod \
  --mode replace \
  --recursive
```

**響應**

```json
{
  "status": "ok",
  "result": {
    "uri": "viking://resources/project/",
    "updated_uris": [
      "viking://resources/project/guide.md"
    ],
    "root_uri": "viking://resources/project/",
    "context_type": "resource",
    "tags": [
      "team=search",
      "env=prod"
    ],
    "mode": "replace",
    "success_count": 1,
    "skipped_count": 0,
    "failed_count": 0,
    "tags_updated": true
  }
}
```

`updated_uris` 是實際更新的語義記錄 URI；目錄遞迴更新時，`success_count`、`skipped_count` 和 `failed_count` 彙總各目標的處理結果。

---

### reindex()

對已經儲存在 OpenViking 中的現有內容，校驗並修復語義產物和/或向量索引。對於 resource 和 skill，reindex 會比較正式內容與已有向量記錄：缺失或過期的記錄會被重建，內容已不存在的孤兒向量會被刪除，狀態一致的記錄會被跳過。只有完整讀取兩邊狀態後才允許刪除；需要無條件重建現有內容時使用 `force=true`，但完整性檢查仍會執行。

這個介面面向已有的 `viking://...` 內容，不負責匯入新檔案。常規匯入請使用 [Resources](02-resources.md)。

**認證**

- `api_key` 模式下，共享區 `viking://resources/...` 需要 admin key；普通 user key 只能重建自己的 `viking://user/<user_id>/...`，也可以使用等價的 `viking://~/...` 家目錄別名。root key 不能訪問租戶級資料 API。
- Python HTTP client / CLI：使用當前認證身份發起請求

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| uri | str | 是 | - | 要重新索引的 Viking URI |
| mode | str | 否 | `vectors_only` | 重建模式：`vectors_only` 或 `semantic_and_vectors` |
| wait | bool | 否 | `true` | 是否等待任務完成 |
| force | bool | 否 | `false` | 是否跳過內容指紋比較並強制重新處理範圍內全部 resource/skill 檔案和目錄 level |
| recursive | bool | 否 | `true` | 是否遞迴處理下級內容；resource/skill 的兩種重建模式都遵守該引數 |
| tags | list[str] | 否 | `null` | 寫入本次成功重建的全部向量記錄。省略或空陣列配合 `replace` 時保留已有 tags |
| tag_mode | str | 否 | `replace` | 標籤寫入模式：`replace`、`append` 或 `clear`；`clear` 不要求傳 `tags` 並清空已有標籤 |

HTTP 請求體會忽略未知欄位，便於客戶端與服務端在欄位演進期間相容。`uri` 可以使用其他 content API 支援的 OpenViking 路徑變數，服務端會先解析再校驗。

**支援的 URI 範圍**

- `viking://`
- `viking://user`
- `viking://user/<user_id>`
- `viking://resources`
- `viking://resources/...`
- `viking://user/<user_id>/memories/...`
- `viking://user/<user_id>/skills`
- `viking://user/<user_id>/skills/<skill_name>`

`reindex()` 不支援會話名稱空間。請求 `viking://session/...` 或
`viking://user/<user_id>/sessions/...` 會被拒絕；重建更大的 user 名稱空間時，
session 子樹會被跳過。

具體 user 根的 namespace reindex 會處理 `resources`、skill package、memory shard、peer 的 resources/memories，以及其他已索引的直屬檔案和自定義一級目錄。寬範圍操作使用分頁淺層發現，跳過 session、privacy、內部 settings 與儲存控制子樹。帶 actor-peer 檢視的請求應指定明確可見的內容目標，因為更大的 namespace 無法提供完整的正式內容檢視。

namespace 會結合正式內容和已有向量記錄發現目標，並按受支援的 URI 字首一次讀取、複用完整的輕量向量記錄清單，因此可以清理已經缺失的內容根。可重試錯誤或記錄數量變化最多觸發三次整份重讀；讀取不完整時不執行刪除。直接請求已經缺失的目標仍返回 `NOT_FOUND`，應從仍存在的父範圍或 namespace 清理其殘留向量；具體內容請求不會擴大到兄弟範圍。

memory 使用原檔案的 L2，不再生成虛擬 `#chunk_NNNN` 記錄。reindex 會清理全部孤兒記錄和歷史 chunk；顯式檔案請求也會清理自身舊 chunk。原 memory 檔案處理失敗時保留其已有 L2，名稱類似 chunk URI 的真實檔案也不會被誤刪。

memory 目錄 L0/L1 分別要求有效且非空的 `.abstract.md`/`.overview.md` 來源。確認來源缺失或為空時刪除該 level 的舊記錄；IO 或格式錯誤時保留舊記錄，增加 `failed_records` 並報告 warning。另一 level 與健康檔案繼續處理。

`semantic_and_vectors` 模式中，memory 目錄目標先清理孤兒記錄，再複用與 `add_resources` 相同的處理流程，並等待相關語義和向量任務完成。精確 memory 檔案目標只重建自身 L2 和清理歷史 chunk，不重新生成目錄語義。

**模式說明**

- `vectors_only`：比較當前內容指紋與向量記錄指紋，只重建缺失或過期的 L0/L1/L2；不會重寫 `.abstract.md` 和 `.overview.md`
- `semantic_and_vectors`：先修復語義產物，再更新對應的 L0/L1/L2 向量

對於 `resource` 和 `skill`，`semantic_and_vectors` 會重新整理目錄/檔案語義產物，包括 `.abstract.md` 和 `.overview.md`。對於 `memory`，它會重建當前已持久化 memory 子樹的語義和向量。

resource/skill 的兩種模式共用一次正式內容掃描和一次輕量向量記錄讀取。每個來源只讀取一次，並在後續處理中複用。`force=true` 會跳過指紋相等判斷並重新處理範圍內全部可用 level；完整性檢查仍然執行。

對 resource/skill 目錄設定 `recursive=false` 時，兩種模式都只處理目標目錄自身的 L0/L1。直接子項只用於聚合目標目錄，不會被掃描或重建。namespace 容器自身沒有索引記錄，因此 namespace 目標不接受 `recursive=false`，避免請求靜默成為 no-op。memory 仍使用原有 reindex 鏈路。

傳入非空 `tags` 時，標籤會隨 reindex 生成的向量記錄在同一次寫入中儲存，不會在完成後額外呼叫 `set_tags`。目錄或 namespace reindex 會把標籤應用到本次成功重建的目錄 L0/L1 和葉子 L2 記錄。`replace` 覆蓋已有標籤，`append` 按 key 合併；`replace` 配合空陣列時不修改已有標籤。`clear` 不要求傳 `tags`，會清空已有標籤；即使同時傳入標籤值也會忽略。

子樹 reindex 不是事務性操作。如果部分記錄因缺少語義來源或 embedding 失敗而未重建，只有成功寫入的記錄會更新標籤。

**Python SDK**

```python
result = client.reindex(
    uri="viking://resources",
    mode="vectors_only",
    wait=False,
    options={
        "tags": ["team=search", "env=prod"],
        "tag_mode": "replace",
    },
)
print(result)
```

```python
result = client.reindex(
    uri="viking://user/default/skills",
    mode="semantic_and_vectors",
    force=True,
    wait=False,
)
print(result["status"])
```

**TypeScript SDK**

```typescript
console.log(await client.reindex("viking://resources/docs/", {
  force: true,
  tags: ["team=search"],
  tagMode: "append",
}));
```

**Go SDK**

傳入非 `nil` 的 `ReindexOptions` 時，省略 `Wait` 使用 Go 的布林零值 `false`；
只有 `opts=nil` 時 SDK 才會應用 `wait=true` 的預設值。

```go
result, err := client.Reindex(ctx, "viking://resources", &openviking.ReindexOptions{
    Mode: "vectors_only",
    Force: true,
    Tags: []string{"team=search"},
    TagMode: "replace",
})
if err != nil {
    return err
}
fmt.Println(result["status"])
```

**HTTP API**

```
POST /api/v1/content/reindex
```

不存在 `/api/v1/maintenance/reindex` 端點。請使用 `/api/v1/content/reindex`。

```bash
curl -X POST http://localhost:1933/api/v1/content/reindex \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-admin-key" \
  -d '{
    "uri": "viking://resources",
    "mode": "vectors_only",
    "wait": false,
    "force": true,
    "tags": ["team=search", "env=prod"],
    "tag_mode": "replace"
  }'
```

**CLI**

```bash
ov reindex viking://resources --mode vectors_only \
  --force --tags team=search,env=prod --tag-mode replace
```

使用 `--tag-mode clear` 且無需傳 `--tags` 即可清空已有標籤：

```bash
ov reindex viking://resources --mode vectors_only --tag-mode clear
```

```bash
ov reindex viking://user/default/skills --mode semantic_and_vectors --wait false
```

**非同步響應（`wait=false`）**

```json
{
  "status": "ok",
  "result": {
    "uri": "viking://resources",
    "mode": "vectors_only",
    "object_type": "resource",
    "status": "accepted",
    "task_id": "task_xxx"
  }
}
```

使用返回的 task 查詢後臺任務：

```bash
curl -X GET http://localhost:1933/api/v1/tasks/task_xxx \
  -H "X-API-Key: your-admin-key"
```

Reindex 後臺任務的 `task_type` 為 `admin_reindex`，`resource_id` 等於請求中的 `uri`，也可以這樣列出：

```text
GET /api/v1/tasks?task_type=admin_reindex&resource_id=viking://resources
```

任務記錄持久化在 `/local/{account_id}/_system/tasks/{user_id}/{task_id}.json`，服務重啟後仍可查詢。

**結果欄位**

| 欄位 | 說明 |
|------|------|
| status | 同步完成時為 `completed`，後臺執行時為 `accepted` |
| uri | 解析路徑變數後的請求 URI |
| object_type | 推斷出的目標型別，例如 `resource`、`skill`、`memory`、`user_namespace`、`skill_namespace` 或 `global_namespace` |
| mode | 實際執行的 reindex 模式 |
| scanned_records | 被檢查的記錄或語義源數量 |
| rebuilt_records | 成功重建的向量記錄數量 |
| deleted_records | 已確認沒有對應內容並刪除的向量記錄數量 |
| unsupported_records | 因沒有可用向量來源而跳過的記錄數量 |
| failed_records | 重建失敗的記錄數量 |
| duration_ms | 同步執行耗時，單位毫秒 |
| warnings | 可恢復的單條記錄級 warning |
| task_id | 後臺任務 ID，僅 `wait=false` 時返回 |

**行為說明**

- Reindex 不會刪除整個向量集合；它覆蓋有效內容的向量記錄，並只刪除已確認沒有對應內容的記錄。
- 同一個 URI 和 owner 同時只能執行一個 reindex 任務。對同一目標的併發請求會返回 conflict。
- 對 resource 檔案，文本檔案在沒有 summary 時可以使用檔案正文；非文本檔案需要已生成的 summary 或已有向量記錄 fallback，否則會計為 unsupported。

**當前限制**

- Reindex 會使用當前系統中“儘可能可恢復”的輸入進行重建，不保證所有場景都能逐位元組回放歷史當時的 embedding 輸入。
- Memory 的 semantic reindex 基於當前已持久化的 memory 樹，不會重建最初按時間順序執行的記憶抽取流水線。

---

## 相關文件

- [檔案系統](03-filesystem.md) - 目錄與檔案操作
- [檢索](06-retrieval.md) - 語義搜尋與模式搜尋
- [後臺任務](17-tasks.md) - 跟蹤非同步 reindex 任務
