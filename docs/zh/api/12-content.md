# 內容

內容 API 負責讀取 L0/L1/L2 內容、寫入文本，以及維護內容對應的語義和向量索引。

## API 參考

### abstract()

讀取 L0 摘要（約 100 token 的概要），不包括 okf 檔案頭。

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
openviking abstract viking://resources/docs/
```


**響應**

```json
{
  "status": "ok",
  "result": "Documentation for the project API, covering authentication, endpoints...",
  "time": 0.1
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
openviking overview viking://resources/docs/
```


**響應**

```json
{
  "status": "ok",
  "result": "## docs/\n\nContains API documentation and guides...",
  "time": 0.1
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
| raw | bool | 否 | false | 返回未過濾 MEMORY_FIELDS 的原始儲存內容（僅 HTTP API，Python SDK 暫未暴露）。 |

**說明**

- `read()` 只接受檔案 URI。傳入已存在的目錄 URI 時返回 `INVALID_ARGUMENT`（`400`），而不是 `NOT_FOUND`。該錯誤會攜帶結構化的 `details` 欄位——`details.expected` 為 `"file"`，`details.actual` 為 `"directory"`，`details.resource` 為出錯的 URI（HTTP 路徑上會帶上）——客戶端據此即可以程式設計方式判斷"檔案 vs 目錄"不匹配（例如回退到 `list`），而無需對錯誤訊息做字串匹配。
- 除 Viking URI 外，還可以傳入 `stat()` 返回的 32 字元十六進位制檔案 `id`。服務端通過向量索引查詢對應 URI 並執行相同的許可權校驗。由於索引是非同步生成的，新返回的 ID 可能暫時無法解析；對應向量記錄被刪除後，按 ID 查詢也會失敗。這兩種情況下，服務端都會返回 `NOT_FOUND`，並提示資料可能尚未索引或已經刪除。
- 公開 URI 引數接受 `resources` 和 `user` 作用域。訪問 session 檔案時，使用 `viking://user/{user_id}/sessions/{session_id}`，也可以使用向後相容的 `viking://session/{session_id}` 別名。`temp`、`queue` 等內部作用域會返回 `INVALID_URI`。


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
openviking read viking://resources/docs/api.md
```


**響應**

```json
{
  "status": "ok",
  "result": "# API Documentation\n\nFull content of the file...",
  "time": 0.1
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
| mode | str | 否 | `replace` | `replace` 覆蓋已有檔案、缺失時建立；`append` 追加已有檔案、缺失時建立；`create` 僅建立缺失檔案，目標已存在時返回 `409 Conflict` |
| wait | bool | 否 | `false` | 是否等待後臺語義/向量重新整理完成 |
| timeout | float | 否 | `null` | 當 `wait=true` 時的超時時間（秒） |
| tags | string[] | 否 | 未設定 | 寫入檔案的顯式檢索標籤，例如 `["team=search", "env=prod"]` |
| tag_mode | string | 否 | `replace` | 標籤更新方式：`replace` 覆蓋、`append` 按 key 合併、`clear` 清空已有標籤且不要求傳 `tags` |

**說明**

- `replace` 和 `append` 在目標檔案缺失時都會建立檔案；其中 `append` 會以傳入內容作為新檔案的初始內容。`create` 僅用於建立缺失檔案，目標路徑已存在時返回 `409 Conflict`。目錄始終會被拒絕。
- 顯式 `create` 只允許以下文本類副檔名：`.md`、`.txt`、`.json`、`.yaml`、`.yml`、`.toml`、`.py`、`.js`、`.ts`。所有寫入模式都會自動建立父目錄。
- 已存在的 `.abstract.md` / `.overview.md` 可以修改正文，但不能通過公共 API 建立；只提交正文時會保留現有 OKF metadata，提交完整 OKF 時 metadata 必須與存量值一致。未知 metadata 欄位會靜默丟棄。sidecar 正文寫入只重建該目錄實際存在的 L0/L1 向量，不觸發語義重新生成。
- 檔案內容會在 API 返回前完成更新；`wait` 只控制是否等待語義/向量重新整理完成。
- 公共 API 已不再接受 `regenerate_semantics` 或 `revectorize`；寫入後會自動排程相關語義與向量處理。
- 資源寫入附帶的父目錄 L0/L1 重新整理採用盡力更新：父目錄鎖衝突時跳過本次目錄重新整理，保留原文寫入及檔案自身的摘要、向量處理。跳過 L0/L1 寫回時也跳過目錄向量更新，不保證自動補刷；原文檔案本身的鎖衝突仍報錯。提交任務前發現衝突時返回 `semantic_status: "skipped"`；後臺執行期間的跳過記錄在日誌中，`wait=true` 也不保證父目錄摘要更新。
- 提供非空 `tags` 時，標籤會在該檔案首次向量 upsert 時寫入，而非在處理完成後再單獨更新。省略 `tags`，或顯式傳 `tags: []` 配合 `tag_mode: "replace"`，都不會修改已有標籤。使用 `tag_mode: "clear"` 可清空全部已有標籤，且 `clear` 會忽略同時傳入的標籤值。


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
openviking write viking://resources/docs/api.md \
  --content "# Updated API\n\nFresh content." \
  --tags team=search,env=prod \
  --tag-mode replace
```


**響應**

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
| `timeout` | number | 否 | `null` | `wait=true` 時的重新整理超時時間（秒） |
| `telemetry` | boolean/object | 否 | `false` | 是否返回操作遙測資訊 |

每個 operation 包含：

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `uri` | string | 是 | 位於 `root_uri` 下的目標檔案 URI |
| `content` | string | 條件必填 | UTF-8 文本；與 `content_base64` 必須且只能提供一個 |
| `content_base64` | string | 條件必填 | Base64 編碼的位元組；Memory 目標不支援 |
| `mode` | string | 否 | `replace`（預設）、`append`、`create` 或 `upsert` |

**說明**

- 單次請求最多包含 256 個 operation，單檔案不超過 8 MiB，總內容不超過 16 MiB。
- 所有目標必須是 `root_uri` 下的檔案、屬於同一 context type，且 canonical URI 不能重複。
- Resource 目標允許任意安全副檔名；Memory 目標仍使用文本副檔名白名單，且不接受二進位制內容。
- `replace`、`append`、`create` 與 `write()` 語義一致；`upsert` 會覆蓋已有檔案或建立缺失檔案。
- 整批先獲取所有目標檔案的精確鎖，再校驗檔案狀態並寫入；同一目錄下不涉及相同檔案的寫入可以並行，重疊檔案的寫入或父目錄刪除、移動仍會衝突。所有檔案寫完並釋放鎖後才啟動語義處理，統一重新整理受影響的 `.overview.md` / `.abstract.md`。
- 資源父目錄重新整理與 `write()` 一樣採用盡力更新：L0/L1 鎖衝突時跳過目錄重新整理及對應目錄向量更新，保留原文和檔案自身的處理，不保證自動補刷。
- 底層 I/O 中途失敗時，本批次較早完成的寫入仍可能已經可見。
- 已存在的 `.abstract.md` / `.overview.md` 可以 replace 或 append；系統會保留並校驗受保護的 OKF metadata，並只重建對應目錄實際存在的 L0/L1 向量。
- 響應體中，通過 `semantic_status`（`queued`、`complete`、`deferred` 或 `skipped`）表達目錄聚合狀態；提交任務前任一目錄因鎖衝突跳過時為 `skipped`，通過 `vector_status` 表達變化檔案的向量維護狀態。

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
    wait=False,
)
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
    "wait": false
  }'
```

**響應**

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

TypeScript、Go SDK 和 CLI 當前不直接暴露 batch write。

---

### download()

以原始位元組流下載檔案，適用於圖片、PDF 和其他非文本內容。響應使用 `application/octet-stream`，並通過 `Content-Disposition` 返回檔名。

| 引數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `uri` | string | 是 | 要下載的檔案 URI |

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

`ov get <uri> <local-path>` 通過上述 HTTP API 下載檔案並寫入本地路徑。Python、TypeScript 和 Go SDK 當前沒有獨立的原始位元組下載方法。

---

### set_tags()

設定用於檢索過濾的顯式 `k=v` 標籤。`replace` 替換已有標籤，`append` 追加標籤；對目錄設定 `recursive=true` 時會更新目錄下的檔案。

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

對已經儲存在 Business Data Platform 中的現有內容，重新構建語義產物和/或向量索引。這是一個運維維護介面，適用於 embedding 模型更換、VLM 更換、向量庫重刷、版本升級後修復歷史索引等場景。

這個介面面向已有的 `viking://...` 內容，不負責匯入新檔案。常規匯入請使用 [Resources](02-resources.md)。

**認證**

- `api_key` 模式下，共享區 `viking://resources/...` 需要 admin key；普通 user key 只能重建自己的 `viking://user/<user_id>/...`，也可以使用等價的 `viking://~/...` 家目錄別名。root key 不能訪問租戶級資料 API。
- Python HTTP client / CLI：使用當前認證身份發起請求

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| uri | str | 是 | - | 要重新索引的 Viking URI |
| mode | str | 否 | `vectors_only` | 重建模式：`vectors_only`、`semantic_and_vectors` 或 `prune_orphans` |
| wait | bool | 否 | `true` | 是否等待任務完成 |
| dry_run | bool | 否 | `false` | 僅適用於 `mode="prune_orphans"`；只報告 orphan 向量記錄，不實際刪除 |
| recursive | bool | 否 | `true` | 是否遞迴處理下級內容；`false` 僅對 `resource`、`memory` 或 `skill` 目錄的 `semantic_and_vectors` 生效 |
| tags | list[str] | 否 | `null` | 寫入本次成功重建的全部向量記錄。省略或空陣列配合 `replace` 時保留已有 tags |
| tag_mode | str | 否 | `replace` | 標籤寫入模式：`replace`、`append` 或 `clear`；`clear` 不要求傳 `tags` 並清空已有標籤 |

HTTP 請求體不接受未知欄位。`uri` 可以使用其他 content API 支援的 Business Data Platform 路徑變數，服務端會先解析再校驗。

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

**模式說明**

- `vectors_only`：基於當前仍可恢復的源資料重建向量庫記錄，不會重寫 `.abstract.md` 和 `.overview.md`
- `semantic_and_vectors`：先重新生成語義產物，再基於新的語義結果重建向量
- `prune_orphans`：刪除請求 URI 範圍內原始檔已不存在的向量庫記錄。設定 `dry_run=true` 時，只報告會刪除多少記錄，不實際刪除。

對於 `resource` 和 `skill`，`semantic_and_vectors` 會重新整理目錄/檔案語義產物，包括 `.abstract.md` 和 `.overview.md`。對於 `memory`，它會重建當前已持久化 memory 子樹的語義和向量，但不會回放歷史記憶抽取順序。

對於 `semantic_and_vectors`，語義重新整理和向量重建由 reindex executor 序列編排。語義重新整理階段不會再額外向後臺 embedding queue 投遞自己的向量化任務；向量由 reindex 階段統一重建，因此 `wait=true` 表示等待 reindex 操作本身完成。

對 `resource` 或 `memory` 目錄設定 `recursive=false` 時，只重新生成目標目錄的 `.abstract.md`、`.overview.md`，並重建該目錄的 L0/L1 向量；下級目錄不會重新生成語義產物，下級目錄和檔案也不會重新向量化。目標目錄仍會讀取本輪確定性取樣命中的既有下級摘要；若取樣命中直接檔案，仍會為當前目錄聚合準備這些檔案的摘要。對 `skill` 目標設定 `recursive=false` 時，會根據 `SKILL.md` 重新生成 skill 目錄的 L0/L1 語義產物及向量，但不會重建 `SKILL.md` 的 L2 向量。該引數不改變 `vectors_only`、`prune_orphans` 或 namespace 目標的既有行為。

對於 `prune_orphans`，原始檔是否存在以當前檔案系統為準。如果整個目錄已經不存在，該目錄下的正文檔案向量和語義 sidecar 向量（例如 `.abstract.md`、`.overview.md`）會一起清理。`dry_run` 用在其他模式時會被拒絕。

傳入非空 `tags` 時，標籤會隨 reindex 生成的向量記錄在同一次 upsert 中寫入，不會在完成後額外呼叫 `set_tags`。目錄或 namespace reindex 會把標籤應用到本次成功重建的目錄 L0/L1 和葉子 L2 記錄。`replace` 覆蓋已有標籤，`append` 按 key 合併；`replace` 配合空陣列時不修改已有標籤。`clear` 不要求傳 `tags`，會清空已有標籤；即使同時傳入標籤值也會忽略。`prune_orphans` 不生成向量，因此會忽略 `tags` 和 `tag_mode`。

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
    wait=False,
)
print(result["status"])
```

```python
result = client.reindex(
    uri="viking://resources",
    mode="prune_orphans",
    dry_run=True,
)
print(result["would_delete_records"])
```

**TypeScript SDK**

```typescript
console.log(await client.reindex("viking://resources/docs/", {
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
    Tags: []string{"team=search"},
    TagMode: "replace",
})
if err != nil {
    return err
}
fmt.Println(result["status"])
```

```go
result, err := client.Reindex(ctx, "viking://resources", &openviking.ReindexOptions{
    Mode: "prune_orphans",
    DryRun: true,
})
if err != nil {
    return err
}
fmt.Println(result["task_id"])
```

**HTTP API**

```
POST /api/v1/content/reindex
```

不存在 `/api/v1/maintenance/reindex` 端點。請使用 `/api/v1/content/reindex`。

```bash
curl -X POST http://localhost:1933/api/v1/content/reindex \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -H "X-OpenViking-Account: default" \
  -d '{
    "uri": "viking://resources",
    "mode": "vectors_only",
    "wait": false,
    "tags": ["team=search", "env=prod"],
    "tag_mode": "replace"
  }'
```

**CLI**

```bash
openviking reindex viking://resources --mode vectors_only \
  --tags team=search,env=prod --tag-mode replace
```

使用 `--tag-mode clear` 且無需傳 `--tags` 即可清空已有標籤：

```bash
openviking reindex viking://resources --mode vectors_only --tag-mode clear
```

```bash
openviking reindex viking://user/default/skills --mode semantic_and_vectors --wait false
```

```bash
openviking reindex viking://resources --mode prune_orphans --dry-run
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
  },
  "time": 0.1
}
```

使用返回的 task 查詢後臺任務：

```bash
curl -X GET http://localhost:1933/api/v1/tasks/task_xxx \
  -H "X-API-Key: your-key" \
  -H "X-OpenViking-Account: default"
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
| deleted_records | `prune_orphans` 實際刪除的向量記錄數量；`dry_run=true` 時為 `0` |
| would_delete_records | `prune_orphans` dry-run 模式下將會刪除的向量記錄數量 |
| unsupported_records | 因沒有可用向量來源而跳過的記錄數量 |
| failed_records | 重建失敗的記錄數量 |
| duration_ms | 同步執行耗時，單位毫秒 |
| warnings | 可恢復的單條記錄級 warning |
| task_id | 後臺任務 ID，僅 `wait=false` 時返回 |

**行為說明**

- `vectors_only` 和 `semantic_and_vectors` 是非破壞式的，採用重建/覆蓋寫入，不需要先 drop 向量集合。
- `prune_orphans` 除非設定 `dry_run=true`，否則會刪除原始檔已經不存在的向量記錄。
- 對 `viking://` 發起 reindex 時，會向下分發到支援的頂層名稱空間，並顯式排除 `session`。
- 名稱空間級 reindex，例如 `viking://user`，會繼續傳播到其支援的子內容型別。
- 如果只是 embedding 模型或向量索引需要重新整理，應使用 `vectors_only`。
- 如果語義產物本身也需要重建，再做重向量化，應使用 `semantic_and_vectors`。
- 如果檔案系統曾繞過正常 API 發生刪除，向量庫可能還殘留已刪除路徑的記錄，應使用 `prune_orphans`。
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
