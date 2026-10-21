# 隱私配置

隱私配置用於按 `category + target_key` 管理敏感欄位版本（如 skill 的 `api_key`、`base_url`）。

配置值變化時會生成版本快照，可查詢歷史版本並切換生效版本。提交與當前版本相同的值不會建立新版本。

以下示例使用當前使用者的 API Key。trusted 模式需補充部署要求的身份頭。讀取值的介面和 CLI 命令會返回實際值；樹總覽和欄位後設資料介面不返回值。下文的 `***` 僅為示例佔位符，不表示介面自動脫敏。

啟用版本只改變 OpenViking 儲存的配置，不會替外部服務輪換、撤銷或恢復金鑰。

## 典型場景

- 為某個 skill 儲存金鑰等敏感配置
- 輪換金鑰（新版本）
- 回滾到歷史版本
- 在讀取 skill 內容時按佔位符自動恢復配置值

---

## 介面總覽

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/v1/privacy-configs` | 列出隱私配置分類 |
| GET | `/api/v1/privacy-configs/tree` | 樹形列出當前目標和欄位後設資料，不返回值 |
| POST | `/api/v1/privacy-configs/scan` | 掃描或修復已儲存正文中的登記值 |
| GET | `/api/v1/privacy-configs/{category}` | 列出分類下目標 |
| GET | `/api/v1/privacy-configs/{category}/{target_key}` | 獲取當前生效配置（meta + current） |
| GET | `/api/v1/privacy-configs/{category}/{target_key}/fields` | 列出不含明文值的安全欄位後設資料 |
| GET | `/api/v1/privacy-configs/{category}/{target_key}/field?field={field}` | 獲取單欄位引用；顯式選擇時返回值 |
| POST | `/api/v1/privacy-configs/resolve` | 按欄位 reference/URI 顯式讀取值 |
| POST | `/api/v1/privacy-configs/{category}/{target_key}` | 寫入新版本並激活 |
| PATCH | `/api/v1/privacy-configs/{category}/{target_key}` | 原子合併欄位；目標不存在時建立 |
| DELETE | `/api/v1/privacy-configs/{category}/{target_key}` | 刪除目標及全部版本 |
| DELETE | `/api/v1/privacy-configs/{category}/{target_key}/field?field={field}` | 刪除當前生效配置中的欄位 |
| DELETE | `/api/v1/privacy-configs/selector` | 按 target URI 或欄位 reference/URI 刪除 |
| GET | `/api/v1/privacy-configs/{category}/{target_key}/versions` | 列出版本號 |
| GET | `/api/v1/privacy-configs/{category}/{target_key}/versions/{version}` | 獲取指定版本詳情 |
| POST | `/api/v1/privacy-configs/{category}/{target_key}/activate` | 激活指定版本 |

---

## 資料結構

### current（當前生效版本）

```json
{
  "version": 3,
  "category": "skill",
  "target_key": "byted-viking-search-knowledgebase",
  "values": {
    "api_key": "***",
    "base_url": "https://example.com"
  },
  "created_at": "2026-04-27T10:00:00+08:00",
  "created_by": "alice",
  "change_reason": "rotate key"
}
```

### meta（元信息）

```json
{
  "category": "skill",
  "target_key": "byted-viking-search-knowledgebase",
  "active_version": 3,
  "latest_version": 5,
  "created_at": "2026-04-21T10:00:00+08:00",
  "updated_at": "2026-04-27T10:00:00+08:00",
  "updated_by": "alice",
  "last_accessed_at": "2026-04-27T10:00:00+08:00",
  "labels": {
    "env": "prod"
  }
}
```

### 輸入格式與容量限制

服務端對 HTTP、CLI、Embedded 和內部寫入執行同一套驗證：

| 專案 | 限制 |
|------|------|
| `category` / `target_key` | 非空、最多 255 個 ASCII 字元；僅允許字母、數字、`_`、`-`、`.`、`@`；禁止 `.`、`..`，`@` 最多一個 |
| values 頂層欄位 | 最多 128 個 |
| 欄位名 | 非空、最多 255 UTF-8 位元組、禁止控制字元 |
| 單個字串值 | 最多 64 KiB UTF-8 |
| values 序列化總量 | 最多 1 MiB |
| JSON 巢狀 | 最多 16 層；單個物件或陣列最多 4096 項 |
| labels | 最多 64 項，序列化總量最多 64 KiB |
| `change_reason` | 最多 1024 個字元 |

違反限制時返回 `INVALID_ARGUMENT`，`details` 包含欄位、原因、實際大小和允許上限。錯誤資訊不會包含敏感值正文。

---

## API 參考

### scan_privacy_content()

顯式掃描一個已經持久化的檔案或目錄。預設 dry-run，不返回命中的原值；`fix=true` 時替換無歧義命中，並非同步重新整理相應內容。

```text
POST /api/v1/privacy-configs/scan
```

```json
{
  "uri": "viking://~/resources/project-a",
  "fix": false,
  "node_limit": 1000
}
```

`uri` 必填，服務端刻意不支援按 scope 發起全域掃描。`node_limit` 只能在 1–1000 之間。服務端還強制限制為每個程序同時一個掃描、每秒最多讀取 20 個檔案、單檔案最多 1 MiB、總輸入最多 16 MiB、單檔案最多記錄 1000 個替換、每個命中檔案最多返回 32 條引用詳情、單次最多修復 100 個檔案，並使用協作式 60 秒掃描預算；第二個併發請求返回 `RESOURCE_EXHAUSTED`。修復不會等待語義和向量重新整理完成。響應會返回跳過檔案計數、截斷狀態、停止原因和實際生效的限制。重複值對應多個 Privacy 欄位時報告 `ambiguous`，不會任意選取引用。

---

### list_privacy_categories()

列出當前使用者下已有隱私配置的分類。

**HTTP API**

```
GET /api/v1/privacy-configs
```

```bash
curl -X GET http://localhost:1933/api/v1/privacy-configs \
  -H "X-API-Key: your-key"
```

**響應**

```json
{
  "status": "ok",
  "result": ["skill"]
}
```

---

### list_privacy_tree()

一次請求列出當前使用者的分類、目標、當前生效版本號和欄位後設資料。
不返回歷史版本或任何儲存的值，沒有 current 快照的目標會被跳過。

**HTTP API**

```text
GET /api/v1/privacy-configs/tree
```

可選查詢引數 `category` 將結果限制在一個分類。非法識別符號返回 `INVALID_ARGUMENT`。
空存量返回 `categories: []`；過濾的分類不存在時返回該分類和 `targets: []`。

```bash
curl "http://localhost:1933/api/v1/privacy-configs/tree?category=credential" \
  -H "X-API-Key: your-key"
```

**響應**

```json
{
  "status": "ok",
  "result": {
    "owner_user_id": "alice",
    "categories": [{
      "category": "credential",
      "targets": [{
        "target_key": "github",
        "version": 3,
        "fields": [{
          "field": "pat",
          "configured": true,
          "reference": "{{ov_privacy:alice:viking://~/privacy/credential/github#/values/pat}}"
        }]
      }]
    }]
  }
}
```

值為 `null` 或空字串時，`configured` 為 false；其他值（包括 `false` 和 `0`）均為已配置。
API 始終返回綁定當前 owner 的 reference。CLI 的表格輸出僅在設定 `--references`
時展示引用；JSON 輸出保留全部後設資料。

---

### list_privacy_targets()

列出分類下的 target_key。

**HTTP API**

```
GET /api/v1/privacy-configs/{category}
```

```bash
curl -X GET http://localhost:1933/api/v1/privacy-configs/skill \
  -H "X-API-Key: your-key"
```

**響應**

```json
{
  "status": "ok",
  "result": ["byted-viking-search-knowledgebase"]
}
```

---

### get_privacy_current()

獲取 target 當前生效配置（`meta + current`）。

**HTTP API**

```
GET /api/v1/privacy-configs/{category}/{target_key}
```

```bash
curl -X GET "http://localhost:1933/api/v1/privacy-configs/skill/byted-viking-search-knowledgebase" \
  -H "X-API-Key: your-key"
```

**響應**

```json
{
  "status": "ok",
  "result": {
    "meta": {
      "category": "skill",
      "target_key": "byted-viking-search-knowledgebase",
      "active_version": 3,
      "latest_version": 5
    },
    "current": {
      "version": 3,
      "category": "skill",
      "target_key": "byted-viking-search-knowledgebase",
      "values": {
        "api_key": "***",
        "base_url": "https://example.com"
      }
    }
  }
}
```

> 若 target 不存在，返回 `NOT_FOUND`。

---

### list_privacy_fields()

列出當前生效欄位的名稱、配置狀態和 owner-bound reference，不返回任何明文值。CLI 在 `reference` 或 `resolve` 的 category 形式省略欄位時使用該介面：僅當 target 恰好有一個欄位時自動推斷；存在多個欄位時列出可選項並要求顯式指定。

```text
GET /api/v1/privacy-configs/{category}/{target_key}/fields
```

```json
{
  "status": "ok",
  "result": {
    "owner_user_id": "alice",
    "category": "credential",
    "target_key": "github-prod",
    "version": 1,
    "fields": [
      {
        "field": "pat",
        "configured": true,
        "reference": "{{ov_privacy:alice:viking://~/privacy/credential/github-prod#/values/pat}}"
      }
    ]
  }
}
```

---

### get_privacy_field()

獲取當前生效版本中的單個欄位。預設只返回帶 owner 的引用和配置狀態，不返回實際值；`reveal=true` 是供立即使用場景顯式讀取單欄位的介面。

**HTTP API**

```text
GET /api/v1/privacy-configs/{category}/{target_key}/field?field={field}&reveal=false
```

預設響應：

```json
{
  "status": "ok",
  "result": {
    "owner_user_id": "alice",
    "category": "credential",
    "target_key": "github-prod",
    "field": "api_key",
    "version": 1,
    "configured": true,
    "reference": "{{ov_privacy:alice:viking://~/privacy/credential/github-prod#/values/api_key}}"
  }
}
```

傳入 `reveal=true` 時，響應額外包含該欄位的 `value`。介面不會返回同一 target 的其他欄位。target 或 field 不存在時返回 `NOT_FOUND`。

也可以將 owner-bound reference 或欄位 URI 傳給統一解析介面：

```text
POST /api/v1/privacy-configs/resolve
```

```json
{"selector":"{{ov_privacy:alice:viking://~/privacy/credential/github-prod#/values/api_key}}"}
```

欄位 URI 支援 `viking://~/privacy/...#/values/...` 和顯式 `viking://user/{user_id}/privacy/...#/values/...`。顯式 owner 與當前身份不一致時返回 `PERMISSION_DENIED`。

OpenViking 生成、儲存和返回的 canonical reference 始終不帶空格。解析器相容雙左花括號後和雙右花括號前的空格或 Tab，例如 <code>&#123;&#123; ov_privacy:alice:... &#125;&#125;</code>，解析後仍規範化為 <code>&#123;&#123;ov_privacy:alice:...&#125;&#125;</code>；owner、URI 和路徑欄位內部不允許插入空白。

---

### upsert_privacy_config()

寫入新版本並將其設為當前生效版本。

**行為說明**

- `values` 完整替換該版本的鍵值；本次省略的 key 不會出現在新快照中
- 傳入新 key 會直接寫入（允許新增）
- 若與當前版本完全一致，則複用當前版本號，不新建版本

**HTTP API**

```
POST /api/v1/privacy-configs/{category}/{target_key}
```

**請求體**

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| values | object | 是 | - | 隱私配置鍵值 |
| change_reason | string | 否 | "" | 變更原因 |
| labels | object | 否 | null | 元資訊標籤 |

```bash
curl -X POST "http://localhost:1933/api/v1/privacy-configs/skill/byted-viking-search-knowledgebase" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "values": {
      "api_key": "secret-2",
      "base_url": "https://example.com",
      "region": "cn"
    },
    "change_reason": "rotate key",
    "labels": {
      "env": "prod"
    }
  }'
```

**響應**

```json
{
  "status": "ok",
  "result": {
    "version": 4,
    "category": "skill",
    "target_key": "byted-viking-search-knowledgebase",
    "values": {
      "api_key": "secret-2",
      "base_url": "https://example.com",
      "region": "cn"
    },
    "change_reason": "rotate key"
  }
}
```

---

### patch_privacy_config()

在服務端 target 鎖內將 `values` 合併到當前配置。target 不存在時以空物件為基礎建立版本 1；target 已存在時保留未涉及的欄位並建立新版本。讀取、合併和寫入在同一把鎖內完成，併發更新不同欄位不會因客戶端 read-modify-write 丟失。

```text
PATCH /api/v1/privacy-configs/{category}/{target_key}
```

```json
{
  "values": {"pat": "github_pat_..."},
  "change_reason": "configure GitHub PAT"
}
```

CLI 規範引數 `--field` 與 `--field-*` 使用該介面，不在 CLI 中預讀 current；`--key` 與 `--key-*` 繼續作為相容別名：

```bash
ov privacy upsert credential github --field-pat 'github_pat_...'
```

---

### delete_privacy_config()

刪除一個 target 的當前值、元資訊和完整版本歷史。重複刪除是安全的：目標不存在時返回 `deleted: false`。

```text
DELETE /api/v1/privacy-configs/{category}/{target_key}
```

```json
{
  "status": "ok",
  "result": {
    "category": "credential",
    "target_key": "github-prod",
    "deleted": true
  }
}
```

欄位刪除隻影響當前生效配置，對外不要求指定版本。刪除後仍有欄位時，實現會發佈一個移除該欄位的新 active 快照，已有歷史版本繼續保留；刪除最後一個欄位時會直接刪除整個 target，包括當前值、元資訊和全部歷史，並返回 `target_deleted: true`。

```text
DELETE /api/v1/privacy-configs/{category}/{target_key}/field?field={field}
```

target URI、欄位 URI 和 owner-bound reference 也可以通過以下介面刪除：

```text
DELETE /api/v1/privacy-configs/selector
```

```json
{"selector":"viking://~/privacy/credential/github-prod#/values/api_key"}
```

---

### list_privacy_versions()

列出 target 的所有版本號。

**HTTP API**

```
GET /api/v1/privacy-configs/{category}/{target_key}/versions
```

```bash
curl -X GET "http://localhost:1933/api/v1/privacy-configs/skill/byted-viking-search-knowledgebase/versions" \
  -H "X-API-Key: your-key"
```

**響應**

```json
{
  "status": "ok",
  "result": [1, 2, 3, 4]
}
```

> 若 target 不存在，返回 `NOT_FOUND`。

---

### get_privacy_version()

獲取某個歷史版本詳情。

**HTTP API**

```
GET /api/v1/privacy-configs/{category}/{target_key}/versions/{version}
```

```bash
curl -X GET "http://localhost:1933/api/v1/privacy-configs/skill/byted-viking-search-knowledgebase/versions/2" \
  -H "X-API-Key: your-key"
```

**響應**

```json
{
  "status": "ok",
  "result": {
    "version": 2,
    "category": "skill",
    "target_key": "byted-viking-search-knowledgebase",
    "values": {
      "api_key": "secret-1",
      "base_url": "https://example.com"
    }
  }
}
```

> 若 target/version 不存在，返回 `NOT_FOUND`。

---

### activate_privacy_version()

切換當前生效版本。

**HTTP API**

```
POST /api/v1/privacy-configs/{category}/{target_key}/activate
```

**請求體**

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| version | int | 是 | 要啟用的版本號 |

```bash
curl -X POST "http://localhost:1933/api/v1/privacy-configs/skill/byted-viking-search-knowledgebase/activate" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"version": 2}'
```

**響應**

```json
{
  "status": "ok",
  "result": {
    "version": 2,
    "category": "skill",
    "target_key": "byted-viking-search-knowledgebase",
    "values": {
      "api_key": "secret-1",
      "base_url": "https://example.com"
    }
  }
}
```

> 若 target/version 不存在，返回 `NOT_FOUND`。

---

## CLI 快速操作

```bash
# 分類/目標
ov privacy categories
ov privacy list skill

# 樹形盤點當前目標和欄位，不顯示值
ov privacy tree
ov privacy tree --category credential --references
ov privacy tree --output json

# 當前生效配置（支援快捷形式）
ov privacy get skill byted-viking-search-knowledgebase
ov privacy skill byted-viking-search-knowledgebase

# 預設只取得 owner 繫結引用，不返回實際值；僅有一個欄位時可省略 field
ov privacy reference credential github-prod
ov privacy reference credential github-prod api_key

# 顯式讀取當前生效版本中的一個欄位，省略規則相同
ov privacy resolve credential github-prod
ov privacy resolve credential github-prod api_key
ov privacy resolve '{{ov_privacy:alice:viking://~/privacy/credential/github-prod#/values/api_key}}'
ov privacy resolve 'viking://~/privacy/credential/github-prod#/values/api_key'

# 更新（整包 JSON）
ov privacy upsert skill byted-viking-search-knowledgebase \
  --values-json '{"api_key":"secret-2","base_url":"https://example.com"}'

# 從本地 JSON 檔案讀取值，避免把值直接寫入命令引數
ov privacy upsert skill byted-viking-search-knowledgebase --values-file ./privacy-values.json

# 更新單個 field；target 不存在時直接建立，存在時在服務端原子合併
ov privacy upsert skill byted-viking-search-knowledgebase \
  --field-api_key secret-3

# 版本查詢與切換
ov privacy versions skill byted-viking-search-knowledgebase
ov privacy version skill byted-viking-search-knowledgebase 2
ov privacy activate skill byted-viking-search-knowledgebase 2

# 刪除目標及全部版本；非互動環境必須顯式 --yes
ov privacy delete credential github-prod --yes
ov privacy delete 'viking://~/privacy/credential/github-prod' --yes

# 刪除當前欄位；歷史快照仍保留
ov privacy delete credential github-prod api_key --yes
ov privacy delete '{{ov_privacy:alice:viking://~/privacy/credential/github-prod#/values/api_key}}' --yes

# 存量內容掃描必須指定一個 URI，預設為 dry-run；--fix 才會改寫
ov privacy scan --uri viking://~/resources/project-a
ov privacy scan --uri viking://~/resources/project-a --fix --node-limit 500
```

---

## 相關文件

- [技能](04-skills.md) - 技能寫入與讀取
- [檔案系統](03-filesystem.md) - `read`/`write`/`ls` 等
- [系統](07-system.md) - 服務狀態與可觀測性
