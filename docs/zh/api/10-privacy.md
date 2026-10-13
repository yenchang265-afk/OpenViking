# 隱私配置

隱私配置用於按 `category + target_key` 管理敏感欄位版本（如 skill 的 `api_key`、`base_url`）。

配置值變化時會生成版本快照，可查詢歷史版本並切換生效版本。提交與當前版本相同的值不會建立新版本。

以下示例使用當前使用者的 API Key。trusted 模式需補充部署要求的身份頭。讀取介面和 CLI 會返回儲存的實際值；下文的 `***` 僅為示例佔位符，不表示介面自動脫敏。

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
| GET | `/api/v1/privacy-configs/{category}` | 列出分類下目標 |
| GET | `/api/v1/privacy-configs/{category}/{target_key}` | 獲取當前生效配置（meta + current） |
| POST | `/api/v1/privacy-configs/{category}/{target_key}` | 寫入新版本並激活 |
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

---

## API 參考

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

# 當前生效配置（支援快捷形式）
ov privacy get skill byted-viking-search-knowledgebase
ov privacy skill byted-viking-search-knowledgebase

# 更新（整包 JSON）
ov privacy upsert skill byted-viking-search-knowledgebase \
  --values-json '{"api_key":"secret-2","base_url":"https://example.com"}'

# 從本地 JSON 檔案讀取值，避免把值直接寫入命令引數
ov privacy upsert skill byted-viking-search-knowledgebase --values-file ./privacy-values.json

# 僅更新部分 key（先讀取 current 再合併）
ov privacy upsert skill byted-viking-search-knowledgebase \
  --key-api_key secret-3

# 版本查詢與切換
ov privacy versions skill byted-viking-search-knowledgebase
ov privacy version skill byted-viking-search-knowledgebase 2
ov privacy activate skill byted-viking-search-knowledgebase 2
```

---

## 相關文件

- [技能](04-skills.md) - 技能寫入與讀取
- [檔案系統](03-filesystem.md) - `read`/`write`/`ls` 等
- [系統](07-system.md) - 服務狀態與可觀測性
