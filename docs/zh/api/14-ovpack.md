# OVPack

OVPack API 用於匯入、匯出、備份和恢復 OpenViking 資料。

## API 參考

### export_ovpack

將資源樹匯出為 `.ovpack` 檔案。

#### 1. API 實現介紹

將指定 URI 下的所有資源打包成 `.ovpack` 格式檔案，用於備份或遷移。ROOT、ADMIN 和 USER 角色均可使用，仍受常規 URI 訪問控制約束。

**處理流程**：
1. 驗證使用者許可權
2. 遍歷指定 URI 下的資源
3. 寫入內容檔案和 OVPack manifest
4. 打包成 zip 格式（.ovpack）
5. 以文件流形式返回

**格式說明**：
- 匯出的 ZIP 會把使用者內容原樣放在 `<root>/files/` 下，並把內部後設資料放在 `<root>/_ovpack/` 下。
- manifest 位於 `<root>/_ovpack/manifest.json`。
- `entries[].path` 是相對匯出 root 的路徑；`""` 表示 root 目錄本身。
- 檔案條目包含 `size` 和 `sha256`；`content_sha256` 覆蓋按路徑排序後的檔案列表（`path`、`size`、`sha256`）。
- `_ovpack/index_records.jsonl` 儲存可遷移的索引標量。`include_vectors=true` 時，`_ovpack/dense.f32` 儲存純 dense float32 向量快照和 embedding 後設資料；底層 `VectorIndex.IndexType` 為 hybrid 時不支援向量快照匯出。
- `id`、`uri`、`account_id`、`created_at`、`updated_at`、`active_count` 等執行態欄位會在目標環境重新生成，不從包內恢復。
- OVPack 不額外設定包大小、檔案數量或目錄深度上限；實際可處理規模由 ZIP、儲存後端和執行環境決定。

**程式碼入口**：
- `openviking/server/routers/pack.py:export_ovpack` - HTTP 路由
- `openviking/service/pack_service.py` - 核心服務實現
- `crates/ov_cli/src/handlers.rs:handle_export` - CLI 處理

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| uri | string | 是 | - | 要匯出的 Viking URI |
| include_vectors | boolean | 否 | false | 匯出純 dense 向量快照；底層 index type 為 hybrid 時會拒絕 |

**許可權要求**：ROOT、ADMIN 或 USER

#### 3. 使用示例


**HTTP API**

```
POST /api/v1/pack/export
Content-Type: application/json
```

```bash
curl -X POST http://localhost:1933/api/v1/pack/export \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-admin-key" \
  -d '{
    "uri": "viking://resources/my-project/",
    "include_vectors": false
  }' \
  --output my-project.ovpack
```

**Python SDK**

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(url="http://localhost:1933", api_key="your-admin-key")
client.initialize()

# 匯出到本地檔案（HTTP SDK 會自動處理下載）
# 注意：匯出功能主要通過 CLI 使用
```

**TypeScript SDK**

```typescript
const outputPath = await client.exportOVPack(
  "viking://resources/docs/",
  "./exports/docs.ovpack",
  true,
);
console.log(outputPath);
```

**Go SDK**

```go
outPath, err := client.ExportOVPack(
    ctx,
    "viking://resources/my-project/",
    "./exports/my-project.ovpack",
    &openviking.PackOptions{IncludeVectors: false},
)
if err != nil {
    return err
}
fmt.Println(outPath)
```

**CLI**

```bash
# 匯出資源
ov export viking://resources/my-project/ ./exports/my-project.ovpack

# 匯出 dense 向量快照
ov export viking://resources/my-project/ ./exports/my-project.ovpack --include-vectors
```


**響應示例**

此介面直接返回檔案流（`Content-Type: application/zip`），不返回 JSON 包裝體。

---

### import_ovpack

匯入 `.ovpack` 檔案。

#### 1. API 實現介紹

將 `.ovpack` 檔案匯入到指定位置，用於恢復或遷移資料。ROOT、ADMIN 和 USER 角色均可使用，仍受常規 URI 訪問控制約束。

**處理流程**：
1. 驗證使用者許可權
2. 解析上傳的 `.ovpack` 檔案
3. 校驗 manifest 後設資料、路徑、檔案和目錄集合、檔案大小和 checksum
4. 應用 `on_conflict`
5. 匯入資源到目標位置，並重建向量

**程式碼入口**：
- `openviking/server/routers/pack.py:import_ovpack` - HTTP 路由
- `openviking/service/pack_service.py` - 核心服務實現
- `crates/ov_cli/src/handlers.rs:handle_import` - CLI 處理

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| temp_file_id | string | 是 | - | 臨時上傳檔案 ID（通過 [temp_upload](02-resources.md#temp-upload) 獲取） |
| parent | string | 是 | - | 目標父級 URI（匯入到此處） |
| on_conflict | string | 否 | fail | 衝突策略：`fail`、`overwrite` 或 `skip` |
| vector_mode | string | 否 | auto | 向量處理方式：`auto`、`recompute` 或 `require` |

**許可權要求**：ROOT、ADMIN 或 USER

**行為說明**：
- API 已不再接受 `vectorize` 或 `force`。
- `vector_mode=auto` 會在存在相容 dense 快照時直接恢復，否則重新向量化；`recompute` 總是忽略包內向量；`require` 要求必須存在相容 dense 快照，否則匯入失敗。
- dense 快照相容性會比較 embedding provider、model、input、query/document 引數和維度。
- Session 檔案屬於 user 名稱空間（`viking://user/{user_id}/sessions/...`），恢復後不觸發向量化。
- `on_conflict=fail` 且目標 root 已存在時，會返回結構化的 `409 CONFLICT`。
- `on_conflict=overwrite` 會替換已有目標 root。`on_conflict=skip` 會保留已有目標 root，並直接返回該路徑，不寫入包內容。`skip` 是 root 級跳過，不是檔案級補齊。
- 預設拒絕沒有 manifest 的包，因為這類包無法提供內容完整性校驗。
- 帶 manifest entries 的包如果缺少內容檔案或目錄、混入額外檔案或目錄、檔案大小不同、單檔案 `sha256` 不同，或整體 `content_sha256` 缺失/不匹配，都會被拒絕匯入。
- manifest `format_version` 不是當前支援版本（`3`）的包會被拒絕。
- `.abstract.md` 和 `.overview.md` 會作為語義側邊檔案恢復；`.relations.json` 和 OVPack 內部檔案會被排除。
- manifest index 標量中的 `context_type` 如果存在，必須和最終匯入路徑語義一致。
- `viking://resources/` 這類頂級 scope 包必須匯入到 `viking://`。
- OVPack 不額外設定匯入包大小、檔案數量或目錄深度上限；實際可處理規模由 ZIP、儲存後端和執行環境決定。

#### 3. 使用示例


**HTTP API**

```
POST /api/v1/pack/import
Content-Type: application/json
```

```bash
# 第一步：上傳 .ovpack 檔案
TEMP_FILE_ID=$(
  curl -s -X POST http://localhost:1933/api/v1/resources/temp_upload \
    -H "X-API-Key: your-admin-key" \
    -F "file=@./exports/my-project.ovpack" \
  | jq -r '.result.temp_file_id'
)

# 第二步：匯入
curl -X POST http://localhost:1933/api/v1/pack/import \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-admin-key" \
  -d "{
    \"temp_file_id\": \"$TEMP_FILE_ID\",
    \"parent\": \"viking://resources/imported/\",
    \"on_conflict\": \"overwrite\",
    \"vector_mode\": \"auto\"
  }"
```

**Python SDK**

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(url="http://localhost:1933", api_key="your-admin-key")
client.initialize()

# 匯入 .ovpack 檔案（HTTP SDK 會自動處理上傳）
# 注意：匯入功能主要通過 CLI 使用
```

**TypeScript SDK**

```typescript
const uri = await client.importOVPack(
  "./exports/docs.ovpack",
  "viking://resources/",
  {
    onConflict: "overwrite",
    vectorMode: "auto",
  },
);
console.log(uri);
```

**Go SDK**

```go
uri, err := client.ImportOVPack(
    ctx,
    "./exports/my-project.ovpack",
    "viking://resources/imported/",
    &openviking.ImportPackOptions{
        OnConflict: "overwrite",
        VectorMode: "auto",
    },
)
if err != nil {
    return err
}
fmt.Println(uri)
```

**CLI**

```bash
# 匯入 .ovpack 檔案
ov import ./exports/my-project.ovpack viking://resources/imported/

# 顯式衝突策略
ov import ./exports/my-project.ovpack viking://resources/imported/ --on-conflict overwrite

# 要求恢復相容 dense 向量快照
ov import ./exports/my-project.ovpack viking://resources/imported/ --vector-mode require
```


**響應示例**

```json
{
  "status": "ok",
  "result": {
    "uri": "viking://resources/imported/my-project/"
  },
  "telemetry": {
    "operation_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

**衝突錯誤示例**

```json
{
  "status": "error",
  "error": {
    "code": "CONFLICT",
    "message": "Resource already exists at viking://resources/imported/my-project. Use on_conflict='overwrite' to replace it.",
    "details": {
      "resource": "viking://resources/imported/my-project"
    }
  }
}
```

---

### backup_ovpack

將公開 scope root 備份為只能通過 restore 恢復的 `.ovpack` 檔案。備份包含
`resources` 和當前帳號下所有 `user/{user_id}` 內容；session 會通過 user 名稱空間下的
`user/{user_id}/sessions` 一起包含，不包含 `temp`、`queue` 等內部執行態資料，也不包含
使用者帳號或 API Key。該介面僅允許 ROOT 或 ADMIN 呼叫。
設定 `include_vectors=true` 時，會額外匯出相容的純 dense 向量快照；底層 index type 為 hybrid 時會拒絕匯出向量快照。

備份是線上逐檔案讀取，不保證同一時刻的原子快照。需要嚴格一致性時，呼叫方應在備份視窗暫停寫入。

```
POST /api/v1/pack/backup
```

```bash
curl -X POST http://localhost:1933/api/v1/pack/backup \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-admin-key" \
  -d '{"include_vectors":false}' \
  --output openviking-backup.ovpack
```

Go SDK：

```go
outPath, err := client.BackupOVPack(
    ctx,
    "./backups/openviking.ovpack",
    &openviking.PackOptions{IncludeVectors: true},
)
if err != nil {
    return err
}
fmt.Println(outPath)
```

CLI：

```bash
ov backup ./backups/openviking.ovpack
ov backup ./backups/openviking.ovpack --include-vectors
```

**響應**

HTTP 成功時返回 `application/zip` 位元組流，不使用標準 JSON 響應包：

```http
HTTP/1.1 200 OK
Content-Type: application/zip
Content-Disposition: attachment; filename="openviking-backup.ovpack"

<ovpack binary body>
```

Go SDK 和 CLI 將位元組流寫入指定路徑，並返回或輸出該本地路徑。

---

### restore_ovpack

恢復 `backup_ovpack` 生成的備份包到原始公開 scope root。普通 import 不接受備份包。
向量處理遵循 `vector_mode`；user 名稱空間下的 session 檔案只恢復檔案狀態，不觸發向量化。
該介面僅允許 ROOT 或 ADMIN 呼叫，並恢復當前帳號下包內所有使用者路徑。

`on_conflict=overwrite` 使用合併覆蓋：包內缺失於目標的路徑會建立，同路徑會覆蓋，目標獨有路徑
會保留；不會刪除整個 `viking://resources` 或 `viking://user`。向量只更新包內新增或覆蓋的
內容。`skip` 仍是 scope root 級跳過，但返回前也會完整校驗 manifest、內容 checksum 和向量後設資料。
損壞的備份不會因為 `skip` 而返回成功。

OVPack 不建立使用者帳號或恢復 API Key。新環境恢復後，需要使用包內相同的 `user_id` 建立使用者，
並使用目標環境新生成的 API Key。

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| temp_file_id | string | 是 | - | 臨時上傳檔案 ID |
| on_conflict | string | 否 | fail | 衝突策略：`fail`、`overwrite` 或 `skip` |
| vector_mode | string | 否 | auto | 向量處理方式：`auto`、`recompute` 或 `require` |

```
POST /api/v1/pack/restore
Content-Type: application/json
```

```bash
TEMP_FILE_ID=$(
  curl -s -X POST http://localhost:1933/api/v1/resources/temp_upload \
    -H "X-API-Key: your-admin-key" \
    -F "file=@./backups/openviking.ovpack" \
  | jq -r '.result.temp_file_id'
)

curl -X POST http://localhost:1933/api/v1/pack/restore \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-admin-key" \
  -d "{\"temp_file_id\":\"$TEMP_FILE_ID\",\"on_conflict\":\"overwrite\",\"vector_mode\":\"auto\"}"
```

Go SDK：

```go
uri, err := client.RestoreOVPack(
    ctx,
    "./backups/openviking.ovpack",
    &openviking.ImportPackOptions{
        OnConflict: "overwrite",
        VectorMode: "require",
    },
)
if err != nil {
    return err
}
fmt.Println(uri)
```

CLI：

```bash
ov restore ./backups/openviking.ovpack --on-conflict overwrite
ov restore ./backups/openviking.ovpack --on-conflict overwrite --vector-mode require
```

**響應**

```json
{
  "status": "ok",
  "result": {
    "uri": "viking://"
  }
}
```

`uri` 是備份恢復到的公開 scope root。

---

## 相關文件

- [OVPack 指南](../guides/09-ovpack.md) - 格式、遷移和操作流程
- [快照](11-snapshot.md) - 工作區版本管理
- [臨時上傳](02-resources.md#temp-upload) - 上傳待匯入的包
