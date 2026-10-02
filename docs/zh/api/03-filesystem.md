# 檔案系統

OpenViking 提供類 Unix 的檔案系統操作來管理上下文。

<a id="webdav"></a><a id="webdav-phase-1"></a>

## API 參考

<a id="abstract"></a><a id="overview"></a><a id="read"></a><a id="write"></a>

### ls()

列出目錄內容。

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| uri | str | 是 | - | Viking URI |
| simple | bool | 否 | False | 僅返回相對路徑 |
| recursive | bool | 否 | False | 遞迴列出所有子目錄 |
| output | str | 否 | HTTP：`agent`；SDK：`original` | 輸出格式：`agent` 或 `original` |
| abs_limit | int | 否 | 256 | `agent` 輸出中的摘要長度限制 |
| show_all_hidden | bool | 否 | False | 像 `-a` 一樣包含隱藏檔案 |
| node_limit | int | 否 | 1000 | 最大返回節點數 |
| offset | int | 否 | 0 | 跳過的可見節點數 |
| limit | int | 否 | None | `node_limit` 的別名 |
| sort_by | str | 否 | None | 在分頁前，分別按 `name` 或 `mtime` 排序目錄組和檔案組；目錄仍優先 |
| sort_order | str | 否 | `asc` | 排序方向：`asc` 或 `desc` |
| extra_fields | list[str] | 否 | None | 額外返回的欄位：`locked`、`id`、`count` |
| tags | string[] | 否 | 未設定 | 僅返回同時匹配全部 `k=v` 檢索標籤的條目 |

`tags` 使用 AND 語義，並在 `offset` 和 `limit` 前應用。帶 tags 過濾的響應會返回 `tags`；未過濾時需傳 `include_tags=true`（CLI：`-f tags`）才返回它們。HTTP 的 `simple=true` 保持僅返回路徑；CLI 同時指定 `--simple` 和 `--fields` 時會獲取條目物件，再按指定列輸出。

**條目結構**

```python
{
    "name": "docs",           # 檔案/目錄名稱
    "size": 4096,             # 大小（位元組）
    "mode": 16877,            # 文件模式
    "modTime": "2024-01-01T00:00:00Z",  # ISO 時間戳
    "isDir": True,            # 如果是目錄則為 True
    "uri": "viking://resources/docs/",  # Viking URI
    "meta": {},               # 可選後設資料
    "tags": ["team=search"] # 顯式檢索標籤；未設定時為空陣列
}
```

如果呼叫方可以讀取父目錄，但沒有某個直接子項的讀取許可權，`ls` 仍會返回該
子項的名稱佔位，但不會返回大小、修改時間、摘要或儲存後設資料：

```python
{
    "name": "restricted",
    "isDir": True,
    "uri": "viking://resources/restricted",
    "access": "denied"
}
```

對這個 URI 呼叫 `stat`、`read` 等內容介面會返回 HTTP 403 `PermissionDenied`。遞迴
列舉會保留無許可權目錄本身，但不會繼續展開其內容，搜尋結果也不會包含無權讀取的
內容。該行為只適用於共享的
`viking://resources` 名稱空間；個人和 peer 私有名稱空間仍按原有規則隱藏。


**Python HTTP SDK**

```python
entries = client.ls(
    uri="viking://resources/",
    offset=100,
    limit=100,
    sort_by="mtime",
    sort_order="desc",
    tags=["team=search", "env=prod"],
)
for entry in entries:
    type_str = "dir" if entry['isDir'] else "file"
    print(f"{entry['name']} - {type_str}")
```

**TypeScript SDK**

```typescript
const entries = await client.list("viking://resources/docs/", {
  tags: ["team=search", "env=prod"],
});
console.log(entries);
```

**Go SDK**

```go
entries, err := client.List(ctx, "viking://resources/", &openviking.ListOptions{
    Tags: []string{"team=search", "env=prod"},
})
if err != nil {
    return err
}
for _, entry := range entries {
    fmt.Println(entry)
}
```

**HTTP API**

```
GET /api/v1/fs/ls?uri={uri}&offset={int}&limit={int}
```

```bash
# 基本列表
curl -X GET "http://localhost:1933/api/v1/fs/ls?uri=viking://resources/" \
  -H "X-API-Key: your-key"

# 簡單路徑列表
curl -X GET "http://localhost:1933/api/v1/fs/ls?uri=viking://resources/&simple=true" \
  -H "X-API-Key: your-key"

# 遞迴列表
curl -X GET "http://localhost:1933/api/v1/fs/ls?uri=viking://resources/&recursive=true" \
  -H "X-API-Key: your-key"

# 按全部 tags 過濾（重複 query 引數）
curl -G "http://localhost:1933/api/v1/fs/ls" \
  -H "X-API-Key: your-key" \
  --data-urlencode "uri=viking://resources/" \
  --data-urlencode "tags=team=search" \
  --data-urlencode "tags=env=prod"

# 不過濾、但在結果中攜帶 tags
curl -G "http://localhost:1933/api/v1/fs/ls" \
  -H "X-API-Key: your-key" \
  --data-urlencode "uri=viking://resources/" \
  --data-urlencode "include_tags=true"
```

**CLI**

```bash
openviking ls viking://resources/ [--simple] [--recursive] [--tags team=search,env=prod] [-f FIELDS]
openviking tree viking://resources/my-project/ [--simple] [--tags team=search,env=prod] [-f FIELDS]
openviking glob "**/*.md" [--uri viking://resources/] [--simple] [--tags team=search,env=prod] [-f FIELDS]

# 在對齊的表格中顯示名稱和 tags
openviking ls viking://resources/ --fields name,tags

# 無表頭，每行輸出逗號分隔的 URI 和 tags
openviking ls viking://resources/ --simple --fields uri,tags
```

`-f` / `--fields` 接受逗號分隔的列名。在預設的 table 輸出模式下，結果為帶表頭、按列對齊的表格。支援的欄位為 `name`、`uri`、`path`、`type`、`size`、`mode`、`mtime`、`locked`、`id`、`count`、`abstract`、`tags`。同時指定 `--simple` 和 `-f` 時，每行輸出逗號分隔的欄位值，不帶表頭或樹縮排；僅使用 `--simple` 時仍每行輸出一個 URI。若未選擇 `name`、`uri` 或 `path`，列表會自動補充 `name` 列，樹會補充 `path` 列。

CLI 會按所選列請求 `extra_fields`（`locked`、`id`、`count`）；選擇 `tags` 列時會請求 `include_tags=true`。這些列選擇不改變 `tags` 的 AND 過濾語義。


**響應**

```json
{
  "status": "ok",
  "result": [
    {
      "name": "docs",
      "size": 4096,
      "mode": 16877,
      "modTime": "2024-01-01T00:00:00Z",
      "isDir": true,
      "uri": "viking://resources/docs/",
      "tags": ["team=search"]
    }
  ],
  "time": 0.1
}
```

---

### tree()

獲取目錄樹結構。

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| uri | str | 是 | - | Viking URI |
| output | str | 否 | HTTP：`agent`；SDK：`original` | 輸出格式：`agent` 或 `original` |
| abs_limit | int | 否 | HTTP：256；SDK：128 | `agent` 輸出中的摘要長度限制 |
| show_all_hidden | bool | 否 | False | 像 `-a` 一樣包含隱藏檔案 |
| node_limit | int | 否 | 1000 | 最大返回節點數 |
| offset | int | 否 | 0 | 跳過的可見節點數 |
| limit | int | 否 | None | `node_limit` 的別名 |
| level_limit | int | 否 | 3 | 最大目錄遍歷深度 |
| extra_fields | list[str] | 否 | None | 額外返回的欄位：`locked`、`id`、`count` |
| tags | string[] | 否 | 未設定 | 僅保留同時匹配全部 `k=v` 檢索標籤的節點 |

`tags` 使用 AND 語義，並在 `offset` 和 `limit` 前應用。帶 tags 過濾的響應會返回 `tags`；未過濾時需傳 `include_tags=true` 才返回它們，否則會省略 tags 以避免額外的向量庫讀取。


**Python HTTP SDK**

```python
entries = client.tree(
    uri="viking://resources/",
    offset=100,
    limit=100,
    tags=["team=search", "env=prod"],
)
for entry in entries:
    type_str = "dir" if entry['isDir'] else "file"
    print(f"{entry['rel_path']} - {type_str}")
```

**TypeScript SDK**

```typescript
const tree = await client.tree("viking://resources/docs/", {
  nodeLimit: 100,
  tags: ["team=search", "env=prod"],
});
console.log(tree);
```

**Go SDK**

```go
entries, err := client.Tree(ctx, "viking://resources/", &openviking.TreeOptions{
    Tags: []string{"team=search", "env=prod"},
})
if err != nil {
    return err
}
for _, entry := range entries {
    fmt.Println(entry["rel_path"], entry["isDir"])
}
```

**HTTP API**

```
GET /api/v1/fs/tree?uri={uri}&offset={int}&limit={int}
```

```bash
curl -X GET "http://localhost:1933/api/v1/fs/tree?uri=viking://resources/" \
  -H "X-API-Key: your-key"

# 僅返回同時包含 team=search 和 env=prod 的節點
curl -G "http://localhost:1933/api/v1/fs/tree" \
  -H "X-API-Key: your-key" \
  --data-urlencode "uri=viking://resources/" \
  --data-urlencode "tags=team=search" \
  --data-urlencode "tags=env=prod"
```

**CLI**

```bash
openviking tree viking://resources/my-project/ --fields path,type,tags

# 與 ls、glob 一樣支援 --simple 和列選擇組合
openviking tree viking://resources/my-project/ --simple --fields path,tags
```


**響應**

```json
{
  "status": "ok",
  "result": [
    {
      "name": "docs",
      "size": 4096,
      "isDir": true,
      "rel_path": "docs/",
      "uri": "viking://resources/docs/",
      "tags": ["team=search"]
    },
    {
      "name": "api.md",
      "size": 1024,
      "isDir": false,
      "rel_path": "docs/api.md",
      "uri": "viking://resources/docs/api.md",
      "tags": ["team=search", "env=prod"]
    }
  ],
  "time": 0.1
}
```

---

### stat()

獲取檔案或目錄的狀態資訊。對於目錄，會返回目錄下的專案計數。

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| uri | str | 是 | - | Viking URI（如 `viking://resources/docs/api.md`）或 32 字元十六進位制向量記錄 `id` |


**Python HTTP SDK**

```python
info = client.stat(uri="viking://resources/docs/api.md")
print(f"Size: {info['size']}")
print(f"Is directory: {info['isDir']}")

# 對於目錄，會返回專案計數
dir_info = client.stat(uri="viking://resources/docs")
if dir_info.get('isDir'):
    print(f"Item count: {dir_info.get('count')}")
```

**TypeScript SDK**

```typescript
const metadata = await client.stat("viking://resources/docs/api.md");
console.log(metadata);
```

**Go SDK**

```go
info, err := client.Stat(ctx, "viking://resources/docs/api.md")
if err != nil {
    return err
}
fmt.Println(info["size"], info["isDir"])
```

**HTTP API**

```
GET /api/v1/fs/stat?uri={uri}
```

```bash
curl -X GET "http://localhost:1933/api/v1/fs/stat?uri=viking://resources/docs/api.md" \
  -H "X-API-Key: your-key"
```

**CLI**

```bash
openviking stat viking://resources/my-project/docs/api.md
openviking stat viking://resources/my-project/docs
```


**響應（檔案）**

```json
{
  "status": "ok",
  "result": {
    "name": "api.md",
    "size": 1024,
    "mode": 33188,
    "modTime": "2024-01-01T00:00:00Z",
    "isDir": false,
    "isLocked": false,
    "id": "a1b2c3d4e5f678901234567890abcdef",
    "uri": "viking://resources/docs/api.md"
  },
  "time": 0.1
}
```

**響應（目錄）**

```json
{
  "status": "ok",
  "result": {
    "name": "docs",
    "size": 4096,
    "mode": 16877,
    "modTime": "2024-01-01T00:00:00Z",
    "isDir": true,
    "isLocked": false,
    "uri": "viking://resources/docs",
    "count": 42
  },
  "time": 0.1
}
```

`isLocked` 欄位反映路徑當前是否被路徑鎖持有：路徑自身存在有效鎖（包括目標路徑對應的 exact-path lock），或者任一祖先目錄持有 TreeLock。當 LockManager 不可用或查詢失敗時返回 `false`，呼叫方可據此避免先寫入再觀察到 `ResourceBusyError`。

`id` 欄位（僅檔案）是 VikingDB 中向量記錄的確定性主鍵，對 level 2（常規檔案）記錄按 `md5(f"{account_id}:{uri}")` 計算。該值與向量集合 schema 中的 `id` 欄位一致，可用於直接交叉引用向量記錄而無需額外查詢。目錄不返回此欄位，因為一個目錄在多個語義層（L0 abstract、L1 overview、L2）下可能對應多條向量記錄，id 不唯一。由於索引是非同步生成的，新返回的 ID 可能暫時無法解析；對應向量記錄被刪除後，按 ID 查詢也會失敗。這兩種情況下，`stat(id)` 都會返回 `NOT_FOUND`，並在原因中提示資料可能尚未索引或已經刪除。

`count` 欄位（僅目錄）包含該目錄下的專案（檔案和子目錄）估計數量（來自向量索引）。

---

### attrs()

獲取檔案或目錄的邏輯擴充屬性。

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| uri | str | 是 | - | Viking URI |


**Python SDK (HTTP)**

```python
attrs = client.attrs(uri="viking://resources/docs/api.md")
print(attrs["attrs"]["tags"])
```

**TypeScript SDK**

```typescript
const attributes = await client.attrs("viking://resources/docs/api.md");
console.log(attributes);
```

**Go SDK**

```go
attrs, err := client.Attrs(ctx, "viking://resources/docs/api.md")
if err != nil {
    return err
}
metadata := attrs["attrs"].(map[string]any)
fmt.Println(metadata["tags"])
```

**HTTP API**

```
GET /api/v1/fs/attrs?uri={uri}
POST /api/v1/fs/attrs/set_tags
```

```bash
curl -X GET "http://localhost:1933/api/v1/fs/attrs?uri=viking://resources/docs/api.md" \
  -H "X-API-Key: your-key"

curl -X POST "http://localhost:1933/api/v1/fs/attrs/set_tags" \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"uri":"viking://resources/docs","tags":["team=search"],"mode":"append","recursive":true}'
```

**CLI**

```bash
openviking attrs get viking://resources/docs/api.md
openviking attrs get viking://resources/docs/api.md tags
openviking attrs get viking://user/alice/memories/experiences/foo.md memory.resource_refs
openviking attrs set-tags viking://resources/docs/api.md --tags team=search,env=prod
openviking attrs set-tags viking://resources/docs --tags team=search --mode append --recursive
```

目錄目標會更新目錄語義記錄；`recursive=true` 還會更新已有子檔案和子目錄語義記錄。


**響應（Resource）**

```json
{
  "status": "ok",
  "result": {
    "uri": "viking://resources/docs/api.md",
    "context_type": "resource",
    "attrs": {
      "tags": ["team=search", "env=prod"]
    }
  }
}
```

**響應（Memory）**

```json
{
  "status": "ok",
  "result": {
    "uri": "viking://user/alice/memories/experiences/foo.md",
    "context_type": "memory",
    "attrs": {
      "memory": {
        "memory_type": "experiences",
        "name": "foo",
        "tags": ["ui"],
        "resource_refs": ["viking://resources/docs/api.md"]
      },
      "tags": ["team=search"]
    }
  }
}
```

`attrs.memory` 來自 `MEMORY_FIELDS` 元資訊，已去掉正文內容。`attrs.tags` 是 `attrs set-tags` 和搜尋過濾使用的顯式檢索標籤。

---

### mkdir()

建立目錄。

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| uri | str | 是 | - | 新目錄的 Viking URI |
| description | str | 否 | `null` | 目錄初始說明。未傳入時使用目錄名作為預設 L0；傳入後使用該說明。兩種情況都會寫入 `.abstract.md` 並進入 L0 向量化佇列。 |


**Python HTTP SDK**

```python
client.mkdir(uri="viking://resources/new-project/")
client.mkdir(uri="viking://resources/new-project/", description="介面文件目錄")
```

**TypeScript SDK**

```typescript
await client.mkdir("viking://resources/docs/guides/", "Project guides");
```

**Go SDK**

```go
if err := client.Mkdir(ctx, "viking://resources/new-project/", "介面文件目錄"); err != nil {
    return err
}
```

**HTTP API**

```
POST /api/v1/fs/mkdir
```

```bash
curl -X POST http://localhost:1933/api/v1/fs/mkdir \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "uri": "viking://resources/new-project/",
    "description": "介面文件目錄"
  }'
```

**CLI**

```bash
openviking mkdir viking://resources/new-project/
openviking mkdir viking://resources/new-project/ --description "介面文件目錄"
```


**響應**

```json
{
  "status": "ok",
  "result": {
    "uri": "viking://resources/new-project/"
  },
  "time": 0.1
}
```

---

### rm()

刪除檔案或目錄。遞迴刪除目錄時會返回刪除的專案估計數量。

`rm` 是冪等操作：刪除一個合法但不存在的 URI 仍會成功。
URI 格式非法、scheme 不支援或使用非公開作用域時返回 `INVALID_URI`。

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| uri | str | 是 | - | 要刪除的 Viking URI |
| recursive | bool | 否 | False | 遞迴刪除目錄 |


**Python HTTP SDK**

```python
# 刪除單個檔案
client.rm(uri="viking://resources/docs/old.md")

# 遞迴刪除目錄
client.rm(uri="viking://resources/old-project/", recursive=True)
```

**TypeScript SDK**

```typescript
await client.remove("viking://resources/docs/old.md");
```

**Go SDK**

```go
err := client.Remove(ctx, "viking://resources/old-project/", &openviking.RemoveOptions{
    Recursive: true,
})
if err != nil {
    return err
}
```

**HTTP API**

```
DELETE /api/v1/fs?uri={uri}&recursive={bool}
```

```bash
# 刪除單個檔案
curl -X DELETE "http://localhost:1933/api/v1/fs?uri=viking://resources/docs/old.md" \
  -H "X-API-Key: your-key"

# 遞迴刪除目錄
curl -X DELETE "http://localhost:1933/api/v1/fs?uri=viking://resources/old-project/&recursive=true" \
  -H "X-API-Key: your-key"
```

**CLI**

```bash
openviking rm viking://resources/old.md [--recursive]
```


**響應（單個檔案）**

```json
{
  "status": "ok",
  "result": {
    "uri": "viking://resources/docs/old.md"
  },
  "time": 0.1
}
```

**響應（遞迴刪除）**

```json
{
  "status": "ok",
  "result": {
    "uri": "viking://resources/old-project/",
    "estimated_deleted_count": 42
  },
  "time": 0.1
}
```

`estimated_deleted_count` 欄位（遞迴刪除時）包含刪除的專案（檔案和目錄）估計數量（來自向量索引）。CLI 會在輸出中顯示此資訊。

刪除 `viking://resources/...` 時，響應可能包含 `memory_cleanup`，表示刪除前已清理引用該資源 URI 的使用者記憶。

---

### cp()

把檔案或目錄複製到新的 Viking URI，源內容保持不變。源 URI 下已有的向量記錄會同步複製並改寫為目標 URI，因此無需重新解析複製內容，也無需重新執行檔案級 VLM 或 embedding。

目標父目錄必須已經存在。目標檔案存在時直接覆蓋；目標目錄存在時遞迴合併，保留目標獨有檔案。`to_uri` 就是實際目標位置，不額外追加源目錄名；檔案與目錄型別衝突時拒絕。複製目錄時必須設定 `recursive=true`（CLI 中使用 `-r`）。源、目標不能相同或互為祖先與後代。覆蓋時保留目標原有訪問許可權；新目標繼承目標父級許可權。

檔案使用源、目標雙 Exact Lock，目錄使用雙 Tree Lock，不鎖父目錄整樹。複製失敗可能保留部分目標；向量複製失敗時嘗試清理目標向量和目標資料。舊目標不備份，合併後發生向量失敗可能刪除整個目標目錄，包括其原有內容；該操作不是原子事務。

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| from_uri | str | 是 | - | 源 Viking URI |
| to_uri | str | 是 | - | 目標 Viking URI，必須包含新的檔名或目錄名 |
| recursive | bool | 否 | False | 源為目錄時必須設為 `true` |

**HTTP API**

```
POST /api/v1/fs/cp
```

```bash
# 複製單個檔案
curl -X POST http://localhost:1933/api/v1/fs/cp \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "from_uri": "viking://resources/docs/guide.md",
    "to_uri": "viking://resources/archive/guide-copy.md",
    "recursive": false
  }'

# 遞迴複製目錄
curl -X POST http://localhost:1933/api/v1/fs/cp \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "from_uri": "viking://resources/docs",
    "to_uri": "viking://resources/docs-backup",
    "recursive": true
  }'
```

**CLI**

```bash
# 複製單個檔案
ov cp viking://resources/docs/guide.md viking://resources/archive/guide-copy.md

# 遞迴複製目錄
ov cp -r viking://resources/docs viking://resources/docs-backup
```

**響應**

```json
{
  "status": "ok",
  "result": {
    "operation_id": "61ec2a80bf5f46a28aa3497fbdcb56dd",
    "operation": "copy",
    "from": "viking://resources/docs/guide.md",
    "to": "viking://resources/archive/guide-copy.md",
    "recursive": false,
    "phase": "completed",
    "files_created": 1,
    "vectors": {
      "scanned": 3,
      "written": 3,
      "deleted": 0,
      "restored": 0,
      "batches": 1
    },
    "semantic_root_uri": "viking://resources/archive",
    "semantic_status": "queued"
  }
}
```

`semantic_status: "queued"` 表示複製已經提交，目標父目錄的 overview 和 abstract 將根據目標目錄中已有的摘要非同步重建，介面不會等待重新整理完成。若語義重新整理入隊失敗，響應可能包含 `semantic_status: "failed"` 和 `semantic_error`；已經完成的檔案和向量複製不會因此回滾。

常見錯誤包括：源或目標父目錄不存在時返回 `NOT_FOUND`；路徑鎖繁忙時返回 `CONFLICT`；複製或刪除目錄但未設定 `recursive=true`、對檔案執行目錄操作、源和目標關係非法或型別衝突時返回 `INVALID_ARGUMENT`（HTTP 400）。

---

### mv()

移動檔案或目錄。目標檔案存在時覆蓋，目標目錄存在時遞迴合併並保留目標獨有內容；`to_uri` 為實際目標位置，不追加源目錄名。檔案與目錄型別衝突、源目標相同或互相包含時拒絕。

檔案使用雙 Exact Lock，目錄使用源、目標雙 Tree Lock，不鎖父目錄整樹。執行順序為複製目標、遷移向量、刪除源。複製失敗不統一清理部分目標；向量遷移或 ACL 更新失敗時嘗試恢復源向量並刪除目標；最後刪除源失敗時保留目標與殘餘源，不重建源。舊目標不備份，合併目標可能在回滾清理中被整體刪除，因此不保證失敗後恢復原狀。

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| from_uri | str | 是 | - | 源 Viking URI |
| to_uri | str | 是 | - | 目標 Viking URI |


**Python HTTP SDK**

```python
client.mv(
    from_uri="viking://resources/old-name/",
    to_uri="viking://resources/new-name/",
)
```

**TypeScript SDK**

```typescript
await client.move(
  "viking://resources/docs/old.md",
  "viking://resources/docs/new.md",
);
```

**Go SDK**

```go
if err := client.Move(ctx, "viking://resources/old-name/", "viking://resources/new-name/"); err != nil {
    return err
}
```

**HTTP API**

```
POST /api/v1/fs/mv
```

```bash
curl -X POST http://localhost:1933/api/v1/fs/mv \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "from_uri": "viking://resources/old-name/",
    "to_uri": "viking://resources/new-name/"
  }'
```

**CLI**

```bash
openviking mv viking://resources/old-name/ viking://resources/new-name/
```


**響應**

```json
{
  "status": "ok",
  "result": {
    "from": "viking://resources/old-name/",
    "to": "viking://resources/new-name/"
  },
  "time": 0.1
}
```

<a id="grep"></a><a id="glob"></a>

<a id="export_ovpack"></a><a id="import_ovpack"></a><a id="backup_ovpack"></a><a id="restore_ovpack"></a>

## 相關文件

- [Viking URI](../concepts/04-viking-uri.md) - URI 規範
- [Context Layers](../concepts/03-context-layers.md) - L0/L1/L2
- [Resources](02-resources.md) - 資源管理
