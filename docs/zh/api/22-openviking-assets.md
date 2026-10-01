# OpenViking Assets Resolver

OpenViking Assets Resolver 用於解析並校驗
[`openviking-assets/1`](../guides/18-openviking-assets.md) Manifest——既支持在
`catalog` 欄位中直接定義資產的單檔案 Manifest，也支援搭配單獨 Catalog 檔案的
Manifest——並返回可供客戶端執行的標準化資產計劃。它不會克隆倉庫、建立資源或啟動
同步任務。

通常應直接使用 `ov add-resource --manifest <file>`；CLI 會自動呼叫 Resolver 和
許可權預檢介面。只有在開發自定義客戶端時，才需要直接請求這些介面。

## 解析 Manifest

```http
POST /api/v1/openviking-assets/resolve
```

### 鑑權

介面沿用 OpenViking Server 的標準鑑權方式。啟用 API Key 時，請在請求中傳入：

```http
X-API-Key: <your-api-key>
```

### 請求體

| 欄位 | 型別 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `manifest_yaml` | string | 是 | — | Manifest 的完整 YAML 內容，長度為 1～4,000,000 字元 |
| `catalog_yaml` | string | 否 | — | Catalog 的完整 YAML 內容，長度為 1～4,000,000 字元。Manifest 按名稱選擇資產時必填；Manifest 在 `catalog` 中定義資產時必須省略。 |
| `manifest_label` | string | 否 | `manifest.yaml` | Manifest 的來源標籤，用於錯誤資訊，長度為 1～1,024 字元 |
| `catalog_label` | string | 否 | `catalog.yaml` | Catalog 的來源標籤，用於錯誤資訊，長度為 1～1,024 字元 |

單檔案 Manifest 示例：

```bash
curl -X POST "${OPENVIKING_BASE_URL}/api/v1/openviking-assets/resolve" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${OPENVIKING_API_KEY}" \
  --data-binary @- <<'JSON'
{
  "manifest_yaml": "protocol: openviking-assets/1\ncatalog:\n  - name: openviking\n    connector: git\n    watch_interval: 1440\n    params:\n      repo_url: https://github.com/volcengine/OpenViking\n      branch: main\n",
  "manifest_label": "manifest.yaml"
}
JSON
```

Manifest 按名稱選擇資產時，把 Catalog YAML 放入 `catalog_yaml`，來源標籤放入
`catalog_label` 一併傳送。

### 成功響應

```json
{
  "status": "ok",
  "result": {
    "protocol": "openviking-assets/1",
    "manifest": "manifest.yaml",
    "catalog": "manifest.yaml",
    "assets": [
      {
        "name": "openviking",
        "connector": "git",
        "repo_url": "https://github.com/volcengine/OpenViking",
        "branch": "main",
        "auth_ref": null,
        "watch_interval": 1440.0,
        "locator": "github.com/volcengine/OpenViking",
        "git_ref": "main",
        "asset_id": "a1b2c3d4e5f6"
      }
    ]
  }
}
```

其中：

- `locator` 是規範化後的倉庫定位符。
- `git_ref` 是最終解析出的 Git 引用。
- `asset_id` 是由連接器、規範化定位符與 Git 引用生成的 12 位穩定標識；示例值僅作格式說明。
- `watch_interval` 的單位是分鐘。
- `catalog` 回顯 `catalog_label`；單檔案 Manifest 時與 Manifest 標籤相同。

### 錯誤響應

協議或內容校驗失敗時返回 HTTP `400`，錯誤碼為 `INVALID_ARGUMENT`。常見原因包括：

- YAML 無法解析或包含未知欄位；
- `protocol` 不是 `openviking-assets/1`，或 Manifest 定義了 `catalog` 卻沒有宣告 `protocol`；
- Manifest 使用了 v1 尚不支持的非空 `include`；
- Manifest 定義了 `catalog`，請求卻同時傳入了 `catalog_yaml`；
- Manifest 按名稱選擇資產，請求卻沒有提供 `catalog_yaml`；
- Manifest 引用了 Catalog 中不存在的資產；
- 連接器、倉庫 URL、Git 引用或資產身份不合法；
- 同一份 Manifest 中出現重複資產身份。

請求欄位為空、型別錯誤或超過長度限制時，由請求模型返回 HTTP `422`。

## 預檢 Git 倉庫許可權

```http
POST /api/v1/openviking-assets/preflight
```

該介面在 OpenViking Server 的實際執行環境執行只讀 `git ls-remote`，校驗倉庫和可選 ref
是否可讀。它不會克隆倉庫、建立資源或啟動任務。Manifest 模式在 dry-run 和正式提交之前
都會呼叫該介面。

### 請求體

| 欄位 | 型別 | 必填 | 說明 |
| --- | --- | --- | --- |
| `name` | string | 是 | 資產名稱 |
| `connector` | string | 是 | 當前必須是 `git` |
| `repo_url` | string | 是 | Git clone URL |
| `branch` | string | 否 | 要驗證的 branch 或 tag；省略時驗證遠端 `HEAD` |
| `auth_config.username` | string | 否 | HTTP Basic 使用者名稱，預設 `oauth2` |
| `auth_config.token` | string | 否 | 一次性 Git token，不持久化 |

```bash
curl -X POST "${OPENVIKING_BASE_URL}/api/v1/openviking-assets/preflight" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${OPENVIKING_API_KEY}" \
  -d '{
    "name": "private-repository",
    "connector": "git",
    "repo_url": "https://github.com/example/private-repository",
    "branch": "main",
    "auth_config": {
      "username": "oauth2",
      "token": "<github-token>"
    }
  }'
```

顯式傳入 token 時，preflight 不會回退到服務端 Git credential helper。token 通過子程序
環境傳遞，不出現在 Git 命令引數和響應中。

### 成功響應

```json
{
  "status": "ok",
  "result": {
    "name": "private-repository",
    "connector": "git",
    "locator": "github.com/example/private-repository",
    "git_ref": "main",
    "accessible": true
  }
}
```

### 錯誤響應

| HTTP 狀態 | 錯誤碼 | 說明 |
| --- | --- | --- |
| `403` | `PERMISSION_DENIED` | 倉庫不存在、憑據無效或當前身份沒有讀取許可權 |
| `404` | `NOT_FOUND` | 倉庫可訪問，但指定 branch/tag 不存在 |
| `503` | `UNAVAILABLE` | DNS、連線或 Git 執行檔不可用 |
| `504` | `DEADLINE_EXCEEDED` | 許可權預檢超過 15 秒 |

## 相關文件

- [OpenViking Assets 協議與執行指南](../guides/18-openviking-assets.md)
- [資源管理 API](02-resources.md)
