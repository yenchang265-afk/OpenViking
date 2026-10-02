# OVPack 匯入匯出

OVPack 是 Business Data Platform 的可恢復內容包格式，用來遷移或備份 `viking://` 下的公開內容樹。
它儲存檔案內容、語義側邊檔案、可遷移的索引標量，以及可選的 dense 向量快照。

OVPack 不是裸 ZIP 複製，也不是可信釋出格式。匯入會校驗 manifest、檔案列表、目錄列表和
checksum，保證包內容沒有偏離 manifest；如果攻擊者能同時篡改檔案和 manifest，仍需要依賴
外部簽名、傳輸安全和訪問控制。

儲存加密不會加密匯出的備份包。匯出會經過透明解密層讀取檔案，再把明文內容寫入普通 ZIP 歸檔。應獨立保護 `.ovpack` 檔案的儲存和傳輸；拿到歸檔即可讀取內容，無需源儲存的金鑰。

## 支援範圍

普通 `export/import` 處理一個包根：

- `viking://resources/...`
- `viking://user/...`

全量遷移使用單獨的 `backup/restore`，它會把公開 scope root 一起打進備份包：

- `viking://resources`
- 當前帳號下所有 `viking://user/{user_id}` 內容

`backup/restore` 僅允許 ROOT 或 ADMIN 呼叫，並以帳號為邊界訪問所有使用者內容。備份包不包含
使用者帳號、API Key 或其他鑑權資料。

Session 通過 user 名稱空間一起遷移，路徑為
`viking://user/{user_id}/sessions/{session_id}`。`viking://session/...`
別名不屬於 OVPack v3 的匯入/匯出 scope。

`temp`、`queue`、`upload`、鎖檔案、watch control 檔案、`.relations.json` 等內部或執行態資料
不屬於 OVPack 遷移範圍。

## 與多寫儲存配合

多寫儲存只複製啟用之後的新寫入，不會自動同步啟用之前已經存在的歷史檔案。如需同時為 primary 和副本寫入存量，應在**空目標環境恢復之前**啟用多寫：

1. 暫停業務寫入，按源 account 分別匯出或備份。
2. 配置目標 primary、backup backend 及其寫策略，啟動目標服務並建立恢復身份。
3. 通過該服務恢復或匯入，使存量內容經過已配置的多寫分發。
4. 對每個恢復的 scope 檢查同步狀態，並在切流前驗證各副本中的檔案。恢復返回時，非同步複製仍可能未完成。
5. 驗證內容和索引完整性後再恢復業務寫入；驗證完成前保留源資料和備份。

例如，使用目標 account 的 admin key 檢查：

```bash
ov system backend sync-status viking://resources
ov system backend sync-status viking://user
```

先恢復再啟用 backups 只會複製後續寫入，不能把歷史內容補到副本。

更多說明見 [多寫儲存指南](./13-multi-write-storage.md)。

## 快速開始

### 匯出和匯入資源目錄

```bash
ov export viking://resources/my-project ./exports/my-project.ovpack
ov import ./exports/my-project.ovpack viking://resources/imported/
```

匯入引數是目標父目錄，不是最終 root。假設包根名是 `my-project`，上面的匯入結果是：

```text
viking://resources/imported/my-project
```

覆蓋已有 root：

```bash
ov import ./exports/my-project.ovpack viking://resources/imported/ --on-conflict overwrite
```

### 匯出向量快照

預設匯出不儲存 dense 向量，匯入後由目標環境重新向量化：

```bash
ov export viking://resources/my-project ./exports/my-project.ovpack
ov import ./exports/my-project.ovpack viking://resources/imported/
```

如果確認匯出環境和匯入環境使用同一 embedding 配置，可以顯式匯出 dense 向量快照：

```bash
ov export viking://resources/my-project ./exports/my-project.ovpack --include-vectors
ov import ./exports/my-project.ovpack viking://resources/imported/ --vector-mode auto
```

`--vector-mode` 控制匯入時如何處理包內向量：

| 值 | 行為 |
| --- | --- |
| `auto` | 預設值。若包內有 dense 快照且 embedding 後設資料相容，則直接恢復；否則重新向量化。 |
| `recompute` | 忽略包內 dense 快照，始終重新向量化。 |
| `require` | 必須恢復相容 dense 快照；沒有快照、快照不完整、模型或維度不相容都會報錯。 |

相容性校驗會比較包內記錄的 embedding provider、model、input、query/document 引數和維度。
當前 OVPack 向量快照只支援純 dense 索引；如果底層向量索引的 `VectorIndex.IndexType` 是 hybrid，`--include-vectors` 會直接拒絕匯出。匯入到 hybrid index 環境時，`auto` 會重新向量化，`require` 會報錯。

匯出 dense 向量快照前，Business Data Platform 會先做資料一致性檢查。也就是檢查匯出範圍內按系統規則
應該進入向量索引的內容，是否已經有對應索引記錄。缺失時會拒絕匯出，避免生成不完整的
遷移包。

可以單獨呼叫一致性檢查來除錯當前資料狀態：

```bash
ov system consistency viking://resources/my-project
```

介面只返回摘要和最多 20 條缺失記錄，不返回完整 expected 列表。`--include-vectors`
匯出失敗時，錯誤 details 只攜帶 1 條缺失 key，避免錯誤日誌過大。

Python SDK：

```python
report = await client.check_consistency(uri="viking://resources/my-project")
print(report["ok"], report["missing_records"])
```

Go SDK：

```go
report, err := client.CheckConsistency(ctx, "viking://resources/my-project")
if err != nil {
    return err
}
fmt.Println(report["ok"], report["missing_records"])
```

HTTP API：

```bash
curl -X POST http://localhost:1933/api/v1/system/consistency \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-admin-key" \
  -d '{"uri":"viking://resources/my-project"}'
```

### 全量備份和恢復

全量遷移不要用 `export viking://`；使用專門的備份包：

```bash
ov backup ./backups/openviking.ovpack
ov restore ./backups/openviking.ovpack --on-conflict overwrite
```

備份包只能通過 `restore` 恢復，不能通過普通 `import` 匯入到任意父目錄。

備份是線上逐檔案讀取，不是同一時刻的原子快照。備份期間仍在變化的內容可能來自不同時間點；
需要嚴格一致性時，應由使用方在備份視窗暫停寫入。

API Key 模式下，新目標必須在恢復**之前**具備 account 和管理員身份。root key 可以建立這個身份，但不能呼叫租戶級 pack API。先將 `OPENVIKING_ROOT_API_KEY` 設定為目標 root key，再呼叫目標服務建立 account，並選擇一個不在備份包中的使用者 ID 作為恢復操作使用者：

```bash
curl -f -X POST http://localhost:1933/api/v1/admin/accounts \
  -H "X-API-Key: $OPENVIKING_ROOT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"account_id": "acme", "admin_user_id": "restore-operator"}'
```

把返回的 `user_key` 作為 `api_key` 寫入專用的目標客戶端配置，例如 `restore.ovcli.conf`：

```json
{
  "url": "http://localhost:1933",
  "api_key": "<target-admin-user-key>"
}
```

建立 account 已會生成 scope 目錄。因此，即使新 account 還沒有業務資料，`fail` 也會拒絕恢復；使用不同的恢復操作使用者不能避開這個 scope 級檢查。確認目標**只有新建 account 的預置內容**後，再使用 `overwrite`：

```bash
OPENVIKING_CLI_CONFIG_FILE=./restore.ovcli.conf \
  ov restore ./backups/openviking.ovpack --on-conflict overwrite
```

如果目標 account 已存在，使用它的 admin key，不要重複建立。如果其中已有業務資料，不要直接照抄這條恢復命令：先暫停寫入、備份目標，並比對包內路徑和目標內容，明確允許覆蓋的內容，或使用獨立的乾淨目標。`overwrite` 會替換同路徑內容；檔案與目錄的型別衝突可能刪除已有子樹。`fail` 檢查 scope 根是否存在，不是逐檔案衝突預檢；`skip` 在 scope 已存在時跳過整次恢復。每次備份/恢復均以 account 為邊界；其他 account 需要使用對應身份分別處理。

恢復內容後，再按備份中的相同 `user_id` 註冊其餘使用者。使用者目錄已存在不代表使用者帳號已建立。目標會生成新 API Key，不會恢復源 key；切換客戶端前，應使用各目標使用者的 key 驗證讀取。

## Python SDK

```python
from openviking_sdk import AsyncHTTPClient


async def migrate_project():
    client = AsyncHTTPClient(url="http://localhost:1933", api_key="your-key")
    await client.initialize()
    try:
        await client.export_ovpack(
            uri="viking://resources/my-project",
            to="./exports/my-project.ovpack",
            include_vectors=False,
        )

        imported_uri = await client.import_ovpack(
            file_path="./exports/my-project.ovpack",
            parent="viking://resources/imported/",
            on_conflict="overwrite",
            vector_mode="auto",
        )
        print(imported_uri)
        await client.wait_processed()
    finally:
        await client.close()
```

全量備份：

```python
await client.backup_ovpack(
    to="./backups/openviking.ovpack",
    include_vectors=True,
)
await client.restore_ovpack(
    file_path="./backups/openviking.ovpack",
    on_conflict="overwrite",
    vector_mode="auto",
)
```

## Go SDK

```go
outPath, err := client.ExportOVPack(
    ctx,
    "viking://resources/my-project",
    "./exports/my-project.ovpack",
    &openviking.PackOptions{IncludeVectors: false},
)
if err != nil {
    return err
}

importedURI, err := client.ImportOVPack(
    ctx,
    outPath,
    "viking://resources/imported/",
    &openviking.ImportPackOptions{
        OnConflict: "overwrite",
        VectorMode: "auto",
    },
)
if err != nil {
    return err
}
fmt.Println(importedURI)
```

全量備份：

```go
backupPath, err := client.BackupOVPack(
    ctx,
    "./backups/openviking.ovpack",
    &openviking.PackOptions{IncludeVectors: true},
)
if err != nil {
    return err
}

restoredURI, err := client.RestoreOVPack(
    ctx,
    backupPath,
    &openviking.ImportPackOptions{
        OnConflict: "overwrite",
        VectorMode: "auto",
    },
)
if err != nil {
    return err
}
fmt.Println(restoredURI)
```

## HTTP API

HTTP 匯出介面直接返回檔案流；HTTP 匯入和恢復必須先上傳本地 `.ovpack`，再用
`temp_file_id` 呼叫 pack 介面。

匯出：

```bash
curl -X POST http://localhost:1933/api/v1/pack/export \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-admin-key" \
  -d '{"uri":"viking://resources/my-project","include_vectors":false}' \
  --output my-project.ovpack
```

匯入：

```bash
TEMP_FILE_ID=$(
  curl -sS -X POST http://localhost:1933/api/v1/resources/temp_upload \
    -H "X-API-Key: your-admin-key" \
    -F "file=@./exports/my-project.ovpack" \
  | jq -r ".result.temp_file_id"
)

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

全量備份：

```bash
curl -X POST http://localhost:1933/api/v1/pack/backup \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-admin-key" \
  -d '{"include_vectors":true}' \
  --output openviking-backup.ovpack
```

## 衝突策略

`on_conflict` 只在匯入 root 已存在時生效。

| 值 | 行為 |
| --- | --- |
| `fail` | 預設值。目標 root 已存在時返回 `409 CONFLICT`。 |
| `overwrite` | 刪除已有 root，再寫入包內容和重建索引。 |
| `skip` | 目標 root 已存在時直接返回該 URI，不寫入任何包內容。 |

`skip` 是 root 級跳過，不是檔案級補齊匯入。

檔案和目錄型別衝突是合併覆蓋的例外：如果包內檔案替換目標目錄（或反向替換），恢復會先刪除衝突目標；該目錄已有的後代也會被刪除。

上表描述普通 `import`。全量 `restore` 的 `overwrite` 使用合併覆蓋：包內不存在的目標路徑會
建立，同路徑內容會覆蓋，目標環境中僅有而備份中沒有的路徑會保留。恢復不會刪除整個
`viking://resources` 或 `viking://user`，也不會建立或寫入 `viking://user` 聚合目錄本身。
向量只恢復或重建包內新增、覆蓋的內容，目標環境獨有內容的向量保持不變。

無論使用哪種衝突策略，都會先完整校驗 manifest、檔案、checksum 和向量後設資料。損壞的包
即使使用 `skip` 也會報錯，不會返回成功。

## 包結構

OVPack v3 是標準 ZIP。ZIP 內部有一個包根目錄：

```text
my-project/
my-project/files/
my-project/files/notes.txt
my-project/files/.abstract.md
my-project/files/.overview.md
my-project/_ovpack/
my-project/_ovpack/index_records.jsonl
my-project/_ovpack/dense.f32                # 僅 --include-vectors 且存在可匯出向量時出現
my-project/_ovpack/manifest.json
```

`files/` 下儲存使用者內容，路徑與 Business Data Platform 中的相對路徑完全一致，不再對點檔案做 `_._` 轉義。
`_ovpack/` 下儲存 OVPack 內部檔案，不參與使用者內容匯入。

manifest 只儲存包結構、檔案 checksum 和內部索引檔案的 checksum，不直接內嵌每個檔案的索引記錄：

```json
{
  "kind": "openviking.ovpack",
  "format_version": 3,
  "root": {
    "name": "my-project",
    "uri": "viking://resources/my-project",
    "scope": "resources"
  },
  "entries": [
    {"path": "", "kind": "directory"},
    {
      "path": "notes.txt",
      "kind": "file",
      "size": 5,
      "sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    }
  ],
  "content_sha256": "b2a6e9582119c7510d68e3446de3e71a486934bf450d68f65596259ed1cf7997",
  "index": {
    "records": {
      "path": "_ovpack/index_records.jsonl",
      "count": 2,
      "sha256": "..."
    },
    "dense": {
      "path": "_ovpack/dense.f32",
      "count": 1,
      "dtype": "float32",
      "byte_order": "little",
      "dimensions": 1024,
      "sha256": "...",
      "embedding": {
        "provider": "volcengine",
        "model": "doubao-embedding-vision-251215",
        "input": "multimodal",
        "dimensions": 1024
      }
    }
  }
}
```

`entries[].path == ""` 表示包根目錄本身。多層目錄使用相對路徑，例如：

```json
[
  {"path": "", "kind": "directory"},
  {"path": "docs", "kind": "directory"},
  {"path": "docs/a.md", "kind": "file", "size": 12, "sha256": "..."}
]
```

`index_records.jsonl` 一行一條索引記錄，覆蓋檔案、目錄、根目錄：

```jsonl
{"record_id":"r000001","path":"","kind":"directory","level":0,"text":"root abstract","scalars":{"abstract":"root abstract","context_type":"resource","level":0}}
{"record_id":"r000002","path":"notes.txt","kind":"file","level":2,"scalars":{"abstract":"note summary","tags":"demo"},"vector":{"dense":{"offset":0,"dimensions":1024}}}
```

`dense.f32` 是連續 little-endian float32 陣列。`index_records.jsonl` 中的 `vector.dense.offset`
是 float 陣列偏移，不是位元組偏移。示例中 `offset=0, dimensions=1024` 表示從第 0 個 float
開始讀取 1024 個 float。

## 索引字段

預設會匯出可遷移的索引標量：

```text
type, context_type, level, name, description, tags, abstract
```

這些欄位不會從包裡直接恢復，而是在目標環境重新生成：

```text
id, uri, account_id, owner_user_id, owner_space,
created_at, updated_at, active_count
```

使用者歸屬從 `viking://user/{user_id}` 路徑重建；使用者帳號和 API Key 不屬於 OVPack 內容。

如果使用 `--include-vectors`，會額外匯出純 dense 向量和 embedding 後設資料。匯入時即使恢復
dense 快照，也會按目標 URI、目標帳號和當前時間重建執行態欄位。hybrid index 當前不支援
向量快照匯出。

## 匯入校驗

匯入會先完整校驗，再寫入目標環境。核心校驗包括：

1. ZIP 成員必須都在同一個包根下，不能包含絕對路徑、反斜槓、磁碟機代號或 `..`。
2. 必須存在 `<root>/_ovpack/manifest.json`。
3. `kind` 必須是 `openviking.ovpack`，`format_version` 必須等於當前支援版本。
4. `root.name` 必須和 ZIP 根目錄一致，`root.uri` 的末段也必須和 `root.name` 一致。
5. manifest 宣告的檔案集合、目錄集合必須和 ZIP 內容一致，不能缺失也不能混入額外內容。
6. 每個檔案的 `size` 和 `sha256` 必須匹配實際內容。
7. `content_sha256` 必須匹配按路徑排序後的檔案清單。
8. `_ovpack/index_records.jsonl` 和可選 `_ovpack/dense.f32` 必須匹配 manifest 中的 hash、數量和維度。
9. source scope 和 target scope 必須一致；`user` 這類結構化 scope 還要求 root 層級一致。
10. 校驗通過前不會寫入包內容；衝突策略也在寫入前處理。

典型拒絕示例：

```text
INVALID_ARGUMENT: Missing ovpack manifest
INVALID_ARGUMENT: ovpack file sha256 does not match manifest
INVALID_ARGUMENT: ovpack entries do not match manifest
INVALID_ARGUMENT: ovpack source scope does not match target scope
INVALID_ARGUMENT: ovpack package does not contain a dense vector snapshot
```

## 匯入路徑規則

普通子樹包匯入到同 scope 的父目錄，並保留包根：

```bash
ov export viking://resources/a ./exports/a.ovpack
ov import ./exports/a.ovpack viking://resources/imported/
```

結果：

```text
viking://resources/imported/a
```

頂級 scope 包只能匯入到 `viking://`：

```bash
ov export viking://resources ./exports/resources.ovpack
ov import ./exports/resources.ovpack viking:// --on-conflict overwrite
```

以下匯入會被拒絕：

```bash
# resources 包不能匯入 user
ov import ./exports/a.ovpack viking://user/alice/

# user session 子樹不能匯入 resources
ov import ./exports/sess_123.ovpack viking://resources/

# session 子樹不能把自身路徑當父目錄，否則會變成 sessions/sess_123/sess_123
ov import ./exports/sess_123.ovpack viking://user/alice/sessions/sess_123/
```

## 記憶和 Session

記憶目錄有固定結構。匯入時把包匯入到對應目錄的父目錄，避免產生重複路徑。

使用者記憶：

```bash
ov export viking://user/default/memories ./exports/user-memories.ovpack
ov import ./exports/user-memories.ovpack viking://user/default/ --on-conflict overwrite
```

Session 資料：

```bash
ov export viking://user/alice/sessions/sess_123 ./exports/sess_123.ovpack
ov import ./exports/sess_123.ovpack viking://user/alice/sessions/ --on-conflict overwrite
```

Session 只恢復檔案狀態，不觸發向量化。

結果：

```text
viking://user/alice/sessions/sess_123
```

## 舊包和未來版本

當前實現只接受 OVPack v3。舊版無 manifest 包沒有檔案集合、目錄集合和 checksum 資訊，無法判斷
是否被刪改或混入內容，因此預設拒絕。需要遷移舊包時，應先在可信舊環境中匯入，再用當前版本
重新匯出為 OVPack v3。

OVPack v2 包也會被當前 Business Data Platform 拒絕。匯入舊包前，需要先用當前版本服務重新匯出。

未來版本包也不會靜默相容。處理方式是升級 Business Data Platform，或在支援該版本的環境中重新匯出為當前
支持格式。

## 常見錯誤

| 錯誤 | 常見原因 | 處理方式 |
| --- | --- | --- |
| `Missing ovpack manifest` | 舊版無 manifest 包 | 在可信環境重新匯出為 v3。 |
| `Unsupported ovpack format_version` | 包格式版本不是當前支援版本 | 升級 Business Data Platform 或重新匯出。 |
| `sha256 does not match manifest` | 檔案或內部索引內容被改動 | 丟棄該包，或從可信源重新匯出。 |
| `ovpack entries do not match manifest` | ZIP 中缺檔案/目錄，或混入額外檔案/目錄 | 丟棄該包，或重新匯出。 |
| `source scope does not match target scope` | 跨 scope 匯入，例如 user 匯入 resources | 匯入到同 scope 的父目錄。 |
| `source path is incompatible with target path` | 結構化 scope 的 root 層級會改變 | 匯入到正確系統父目錄。 |
| `Top-level scope ovpack packages must be imported to viking://` | 將頂級 scope 包匯入了非根父目錄 | 改為匯入 `viking://`。 |
| `Backup ovpack packages must be restored` | 用普通 import 匯入 backup 包 | 使用 `ov restore`。 |
| `Resource already exists` | 目標 root 已存在 | 使用 `--on-conflict overwrite` 或 `--on-conflict skip`。 |
| `incomplete Business Data Platform vector index snapshot` | 使用 `--include-vectors` 時，匯出範圍內應索引內容缺少索引記錄 | 先執行 `ov system consistency <uri>` 定位問題，再等待處理完成或重新 reindex。 |
| `dense vector snapshot is incompatible` | 包內 embedding 後設資料和當前配置不一致 | 用 `--vector-mode recompute`，或換到相容配置。 |

## 常見問題

**OVPack 可以手動解壓檢視嗎？**

可以。OVPack 是 ZIP 檔案，可以用普通解壓工具檢視。不要手動修改後再匯入，修改會破壞
manifest 校驗；如果同時修改 manifest 和內容，則需要依賴外部簽名和可信來源判斷。

**為什麼不預設匯出向量？**

向量只在 embedding 模型、輸入模式、引數和維度完全相容時才可直接複用。預設重新向量化更穩；
需要冷遷移加速時，再顯式使用 `--include-vectors` 和 `--vector-mode auto/require`。

**大包匯入很慢怎麼辦？**

預設匯入會重建目標環境的語義和向量。大包遷移可以使用 `--include-vectors` 減少重算，或按目錄
拆成多個 OVPack 分批匯入。
