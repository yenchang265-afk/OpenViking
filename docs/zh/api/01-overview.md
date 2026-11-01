# SDK、HTTP 與 CLI 約定

本頁介紹如何連線 OpenViking 以及所有 API 端點共享的約定。

## 連線模式

OpenViking 客戶端通過 HTTP 連線 OpenViking Server。

| 模式 | 適用場景 | 說明 |
|------|----------|------|
| **HTTP** | 連線 OpenViking 伺服器 | 通過 HTTP API 連線遠端伺服器 |
| **CLI** | Shell 指令碼、Agent 工具使用 | 通過 CLI 命令連線伺服器 |

### Client-Server 模式

Client-Server 模式通過 HTTP API 連線 OpenViking 伺服器，支援多租戶、遠端訪問等特性。OpenViking 的伺服器啟動方式請參見相關部署文件。

#### Python SDK 客戶端

先在執行程式碼的 Python 環境中安裝獨立 SDK：

```bash
python -m pip install --upgrade openviking-sdk
```

```python
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(
    url="http://localhost:1933",
    api_key="your-key",
    timeout=120.0,
)
client.initialize()
```

#### Go SDK 客戶端

Go SDK 是 Client-Server 模式下的 HTTP-only 客戶端，作為主倉庫的 `sdk/go` 獨立 Go module 釋出。

```bash
go get github.com/volcengine/OpenViking/sdk/go
```

```go
client, err := openviking.NewClient(openviking.Config{
    BaseURL: "http://localhost:1933",
    APIKey:  "your-key",
})
if err != nil {
    return err
}
defer client.CloseIdleConnections()
```

Go SDK 傳送的身份請求頭與 Python HTTP client 一致：

| Config 字段 | HTTP Header |
|-------------|-------------|
| `APIKey` | `X-API-Key` |
| `Account` | `X-OpenViking-Account` |
| `User` | `X-OpenViking-User` |
| `ActorPeerID` | `X-OpenViking-Actor-Peer` |

普通 `api_key` 部署下只需要設定 `APIKey`，服務端會從 API key 推導租戶身份。只有在 trusted 部署或閘道器顯式透傳租戶身份時，才需要設定 `Account` 和 `User`。

Go SDK 不保留舊 `agent_id` 相容路徑。更多示例見 [`sdk/go/README_CN.md`](https://github.com/volcengine/OpenViking/blob/main/sdk/go/README_CN.md)。

#### JavaScript/TypeScript SDK 客戶端

JavaScript/TypeScript SDK 是面向 Node.js 18+ 的 HTTP-only 客戶端，同時釋出
ESM、CommonJS 和 TypeScript 型別宣告。

```bash
npm install @openviking/sdk
```

```ts
import { OpenVikingClient } from "@openviking/sdk";

const client = new OpenVikingClient({
  baseUrl: "http://localhost:1933",
  apiKey: "your-key",
});

const results = await client.search("部署文件", {
  targetUri: "viking://resources",
});
```

它與 Python、Go HTTP Client 使用相同的身份請求頭和響應信封。更多示例見
[`sdk/typescript/README_CN.md`](https://github.com/volcengine/OpenViking/blob/main/sdk/typescript/README_CN.md)。

Python HTTP 客戶端從 `ovcli.conf` 讀取連線資訊，顯式傳入的構造引數覆蓋對應配置。`ovcli.conf` 是 HTTP 客戶端和 CLI 共享的配置檔案，預設路徑 `~/.openviking/ovcli.conf`，也可通過環境變數指定：

```bash
export OPENVIKING_CLI_CONFIG_FILE=/path/to/ovcli.conf
```

使用 user/admin key 的配置檔案示例：

```json
{
  "url": "http://localhost:1933",
  "api_key": "your-user-or-admin-key"
}
```

配置欄位說明：

| 欄位 | 說明 | 預設值 |
|------|------|--------|
| `url` | 服務端地址 | （必填） |
| `api_key` | API Key | `null`（無認證） |
| `account` | 帳戶請求頭；trusted 和 dev 模式使用，api_key 模式忽略 | `null` |
| `user` | 使用者請求頭；trusted 和 dev 模式使用，api_key 模式忽略 | `null` |
| `timeout` | HTTP 請求超時時間（秒） | `60.0` |
| `output` | 預設輸出格式：`"table"` 或 `"json"` | `"table"` |

詳細內容請參見 [配置指南](../guides/01-configuration.md#ovcli-conf)。

#### 完全不依賴配置檔案使用 Python SDK 客戶端

`SyncHTTPClient` 和 `AsyncHTTPClient` 可以在沒有 `ovcli.conf` 檔案時使用。先在執行程式碼的 Python 環境中安裝獨立 SDK：

```bash
python -m pip install --upgrade openviking-sdk
```

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(
    url="http://localhost:1933",
    api_key="your-key",
    timeout=30.0,
    extra_headers={},
)
client.initialize()
```

即使顯式傳入引數，SDK 仍會讀取已有的 `ovcli.conf`。顯式值覆蓋對應配置，其他設定可能來自環境變數或配置檔案，因此無效配置仍會導致客戶端構造失敗。預設超時為 60 秒。檔案位置見[客戶端配置](../configuration/02-client.md)。

#### HTTP 呼叫示例

- CLI、`SyncHTTPClient`、`AsyncHTTPClient` 遇到本地檔案或目錄時，會先自動上傳，再呼叫服務端 API。
- Python HTTP client 可以通過 `ovcli.conf` 啟用 shared 臨時上傳（設定 `upload.mode = "shared"`）。Rust `ov` CLI 不讀取這個欄位；使用 `ov` 時請設定 `OPENVIKING_UPLOAD_MODE=shared`。
- 裸 HTTP 呼叫沒有這層封裝。使用 `curl` 或其他 HTTP 客戶端時，需要先呼叫 `POST /api/v1/resources/temp_upload`，再把返回的 `temp_file_id` 傳給目標 API。
- `temp_upload` 預設使用 `upload_mode=local`。只有在你顯式需要分散式共享臨時上傳時，才應傳 `upload_mode=shared`。
- 裸 HTTP 如果匯入本地目錄，需要先自行打成 `.zip` 再通過上述方法上傳；服務端不接受直接傳宿主機目錄路徑。
- `POST /api/v1/resources` 可以直接接收遠端 URL，但不接受 `./doc.md`、`/tmp/doc.md` 這類宿主機本地路徑。

直接 HTTP（curl）呼叫示例如下

```bash
curl http://localhost:1933/api/v1/fs/ls?uri=viking:// \
    -H "X-API-Key: your-key"
```

#### CLI 模式

OpenViking CLI 的命令是 `ov`（通過 `npm install -g @openviking/cli` 安裝），連線到 OpenViking 服務端，提供常用操作的 Shell 命令。CLI 同樣從 `ovcli.conf` 讀取連線資訊（與 HTTP 客戶端共享）。

基本用法：

```bash
ov [全域選項] <command> [引數] [命令選項]
```

全域選項（必須放在命令名之前）：

| 選項 | 說明 |
|------|------|
| `--output`, `-o` | 輸出格式：`table`（預設）、`json` |
| `--version` | 顯示 CLI 版本 |

示例：

```bash
ov -o json ls viking://resources/
```

## 生命週期

### Client-Server 模式

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(url="http://localhost:1933")
client.initialize()

# ... 使用 client ...

client.close()
```

CLI 則直接通過命令列呼叫，需要先配置 ovcli.conf 檔案，無需額外初始化客戶端：

```
ov -o json ls viking://resources/
```

## 認證

詳見 [認證指南](../guides/04-authentication.md)。

- **Authorization Bearer** 請求頭：`Authorization: Bearer your-key` （建議的方式）
- **X-API-Key** 請求頭：`X-API-Key: your-key`
- 只有 dev 模式跳過認證；未設定 `auth_mode` 且未設定 `server.root_api_key` 時自動選擇 dev 模式。其他模式（api_key、trusted、OIDC、LDAP）按各自配置解析身份。
- `/health` 和 `/ready` 端點始終不需要認證。

## 響應格式

常規 JSON API 響應遵循以下格式；檔案下載、SSE、Metrics 和 WebDAV 使用各介面說明的格式：

### 成功響應

```json
{
  "status": "ok",
  "result": { ... }
}
```

頂層 `status` 表示本次 HTTP API 請求是否成功。某些成功響應會在 `result` 中返回業務狀態，例如 `"status": "success"`、`"status": "accepted"` 或任務狀態。這些欄位不是 API 傳輸層錯誤。

### 錯誤響應

```json
{
  "status": "error",
  "error": {
    "code": "NOT_FOUND",
    "message": "Resource not found: viking://resources/nonexistent/"
  }
}
```

HTTP 錯誤始終使用頂層錯誤 envelope。資源解析、同步 reindex 等同步處理失敗會返回非 2xx 響應，頂層為 `status="error"`，並包含 `error` 物件。客戶端不應通過 `result.status="error"` 判斷請求失敗。

請求校驗失敗，包括 JSON 格式錯誤、缺少必填欄位和引數值非法，統一返回 HTTP `400`，並使用 `error.code="INVALID_ARGUMENT"`。響應不會使用 FastAPI 原生的 `{"detail": ...}` 錯誤格式；當存在欄位級校驗資訊時，會通過 `error.details.validation_errors` 返回。

Python HTTP SDK（`SyncHTTPClient` 和 `AsyncHTTPClient`）會把該 envelope 對映為對應的 `OpenVikingError` 子類。例如 `PROCESSING_ERROR` 會丟擲 `ProcessingError`。

## CLI 輸出格式

### Table 模式（預設）

列表資料渲染為表格，非列表資料 fallback 到格式化 JSON：

```bash
ov ls viking://resources/
# name          size  mode  isDir  uri
# .abstract.md  100   420   false  viking://resources/.abstract.md
```

### JSON 模式（`--output json`）

`-o json` 預設使用緊湊輸出，並帶有 `{ok, result}` 包裝：

```bash
ov -o json ls viking://resources/
# {"ok":true,"result":[{"name":"...","size":100,...},...]}
```

使用 `--compact=false` 返回不帶包裝的格式化 JSON：

```bash
ov -o json --compact=false ls viking://resources/
```

可在 `ovcli.conf` 中設定預設輸出格式：

```json
{
  "url": "http://localhost:1933",
  "output": "json"
}
```

### 緊湊模式（`--compact`, `-c`，預設開啟）

- 當 `--output=json` 時：緊湊 JSON 格式 + `{ok, result}` 包裝，適用於指令碼
- 當 `--output=table` 時：對錶格輸出採取精簡表示（如去除空列等）

JSON 輸出 - 成功：

```json
{"ok": true, "result": ...}
```

JSON 輸出 - 錯誤：

```json
{"ok": false, "error": {"code": "NOT_FOUND", "message": "...", "details": {}}}
```

### 特殊情況

- Table 模式下，`read`、`abstract`、`overview` 直接列印文本，`mkdir`、`rm`、`mv` 列印操作確認資訊。
- JSON 模式下，這些命令按上文的 JSON 格式輸出。

### 退出碼

**注：退出碼是 CLI（命令列工具）的返回碼，不是 HTTP API 的狀態碼。**

| 退出碼 | 說明 | 觸發場景 |
|--------|------|----------|
| 0 | 成功 | 命令執行成功 |
| 1 | 執行錯誤 | 命令執行失敗，包括 API 呼叫錯誤或連線錯誤 |
| 2 | 引數或配置錯誤 | 命令列引數無效、配置載入失敗、缺少必要憑據，或將 `--sudo` 用於不支援的命令 |

當前 Rust CLI 的連線失敗返回退出碼 `1`，不使用單獨的連線錯誤退出碼 `3`。

## 錯誤碼

| 錯誤碼 | HTTP 狀態碼 | 說明 |
|--------|-------------|------|
| `OK` | 200 | 成功 |
| `INVALID_ARGUMENT` | 400 | 無效引數 |
| `INVALID_URI` | 400 | 無效的 Viking URI 格式 |
| `NOT_FOUND` | 404 | 資源未找到 |
| `ALREADY_EXISTS` | 409 | 資源已存在 |
| `UNAUTHENTICATED` | 401 | 缺少或無效的 API Key |
| `PERMISSION_DENIED` | 403 | 許可權不足 |
| `RESOURCE_EXHAUSTED` | 429 | 超出速率限制 |
| `FAILED_PRECONDITION` | 412 | 前置條件不滿足 |
| `CONFLICT` | 409 | 操作與正在進行的任務或已有狀態衝突 |
| `DEADLINE_EXCEEDED` | 504 | 操作超時 |
| `UNAVAILABLE` | 503 | 服務不可用 |
| `PROCESSING_ERROR` | 500 | 資源或語義處理失敗 |
| `INTERNAL` | 500 | 內部伺服器錯誤 |
| `UNIMPLEMENTED` | 501 | 功能未實現 |
| `EMBEDDING_FAILED` | 500 | Embedding 生成失敗 |
| `VLM_FAILED` | 500 | VLM 呼叫失敗 |
| `SESSION_EXPIRED` | 410 | 會話已過期 |
| `NOT_INITIALIZED` | - | 服務或元件未初始化（需要先呼叫 initialize()） |

檔案／目錄型別不符合操作要求、複製或刪除目錄時缺少 `recursive=true`，以及 HTTP 來源域名明確不存在，均返回 `INVALID_ARGUMENT`（400）。正常路徑鎖競爭（包括加密寫入）返回 `CONFLICT`（409）；鎖令牌損壞、鎖 I/O 故障和落盤資料解密失敗返回 `INTERNAL`（500）。HTTP 來源站不可用或發生臨時網路故障時返回 `UNAVAILABLE`（503），抓取超時返回 `DEADLINE_EXCEEDED`（504）。

---

## API 端點總覽

以下目錄以服務端實際掛載路由為準。每組標題會跳轉到詳細文件；詳細頁只為真實存在的 HTTP、Python SDK、TypeScript SDK、Go SDK 或 CLI 能力顯示對應 Tab，不會用等價的裸 HTTP 呼叫冒充 SDK。

### [系統狀態](07-system.md)

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/health` | 基礎健康檢查（無需認證） |
| GET | `/ready` | AGFS、VectorDB、API Key 管理器和 Embedding 就緒檢查（無需認證） |
| GET | `/api/v1/system/status` | 系統狀態 |
| POST | `/api/v1/system/wait` | 等待後臺處理完成 |
| POST | `/api/v1/system/consistency` | 檔案系統與向量索引一致性檢查 |

### [資源](02-resources.md)與[檔案系統](03-filesystem.md)

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/v1/resources/temp_upload` | 上傳後續匯入所需的臨時檔案 |
| GET | `/api/v1/uploads/limits` | 獲取伺服器上傳限制 |
| POST | `/api/v1/uploads` | 建立分片上傳工作階段 |
| PUT | `/api/v1/uploads/{upload_id}/files/{file_index}/parts/{part_number}` | 上傳檔案的一個分片 |
| GET | `/api/v1/uploads/{upload_id}` | 獲取上傳工作階段已收到的分片 |
| POST | `/api/v1/uploads/{upload_id}/complete` | 完成上傳工作階段 |
| DELETE | `/api/v1/uploads/{upload_id}` | 中止上傳工作階段 |
| POST | `/api/v1/resources` | 從 URL 或臨時檔案新增資源 |
| GET | `/api/v1/fs/ls` | 列出目錄 |
| GET | `/api/v1/fs/tree` | 獲取目錄樹 |
| GET | `/api/v1/fs/stat` | 獲取資源狀態 |
| GET | `/api/v1/fs/attrs` | 獲取邏輯擴充屬性 |
| POST | `/api/v1/fs/attrs/set_tags` | 設定檢索標籤（相容別名） |
| POST | `/api/v1/fs/mkdir` | 建立目錄 |
| DELETE | `/api/v1/fs` | 刪除資源 |
| POST | `/api/v1/fs/cp` | 複製檔案或目錄及其向量記錄 |
| POST | `/api/v1/fs/mv` | 移動或重新命名資源 |

### [ACL](12-acl.md)

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/v1/acl` | 獲取資源的直接、繼承和有效 ACL |
| PUT | `/api/v1/acl` | 替換資源的直接 ACL |
| DELETE | `/api/v1/acl` | 清空資源的直接 ACL |
| POST | `/api/v1/acl/grant` | 設定一個 principal 的直接許可權級別 |
| POST | `/api/v1/acl/revoke` | 刪除一個 principal 的直接授權 |

### [內容](12-content.md)

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/v1/content/read` | 讀取完整內容（L2） |
| GET | `/api/v1/content/abstract` | 讀取摘要（L0） |
| GET | `/api/v1/content/overview` | 讀取概覽（L1） |
| GET | `/api/v1/content/download` | 下載原始檔案位元組 |
| POST | `/api/v1/content/write` | 寫入內容並重新整理語義索引 |
| POST | `/api/v1/content/batch-write` | 寫入多個檔案並重新整理索引 |
| POST | `/api/v1/content/set_tags` | 設定檢索標籤 |
| POST | `/api/v1/content/ensure_directory_index` | 確保既有目錄的索引就緒，僅在兩層摘要都缺失時建立 L0 |
| POST | `/api/v1/content/reindex` | 重建語義或向量索引 |

### [技能](04-skills.md)

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/v1/skills` | 列出技能 |
| POST | `/api/v1/skills` | 添加技能 |
| POST | `/api/v1/skills/find` | 搜索技能 |
| POST | `/api/v1/skills/validate` | 校驗技能資料 |
| GET | `/api/v1/skills/{skill_name}` | 獲取技能 |
| PUT | `/api/v1/skills/{skill_name}` | 更新技能 |
| DELETE | `/api/v1/skills/{skill_name}` | 刪除技能 |

### [會話](05-sessions.md)、[記憶](16-memory.md)與 [Agent 進化](19-agent-evolution.md)

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/v1/sessions` | 建立會話 |
| GET | `/api/v1/sessions` | 列出會話 |
| GET | `/api/v1/sessions/{session_id}` | 獲取會話 |
| PATCH | `/api/v1/sessions/{session_id}/config` | 更新可變的會話配置 |
| GET | `/api/v1/sessions/{session_id}/tool-results` | 列出工具結果 |
| GET | `/api/v1/sessions/{session_id}/tool-results/{tool_result_id}` | 讀取工具結果 |
| GET | `/api/v1/sessions/{session_id}/tool-results/{tool_result_id}/search` | 在工具結果內搜尋 |
| GET | `/api/v1/sessions/{session_id}/context` | 獲取組裝後的上下文 |
| GET | `/api/v1/sessions/{session_id}/archives/{archive_id}` | 獲取會話歸檔 |
| DELETE | `/api/v1/sessions/{session_id}` | 刪除會話 |
| POST | `/api/v1/sessions/{session_id}/commit` | 歸檔會話並提取記憶 |
| POST | `/api/v1/sessions/{session_id}/messages` | 新增單條訊息 |
| POST | `/api/v1/sessions/{session_id}/messages/batch` | 批量添加消息 |
| POST | `/api/v1/search/recall` | 已棄用：search 介面 `mode="context"` 之上的輕量預設 |
| POST | `/api/v1/rules/compile` | 非同步編譯使用者規則 |
| POST | `/api/v1/rules/search` | 檢索適用於當前任務的完整規則 |
| GET | `/api/v1/agent-evolution/experiences/trajectories` | 分頁查詢應用過指定 Experience 的 Trajectory |
| GET | `/api/v1/agent-evolution/experiences/outcomes` | 聚合應用過指定 Experience 的 Trajectory 結果分佈 |

### [規則（Beta）](26-rules.md)

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/v1/rules/compile` | 提交規則編譯後臺任務 |
| POST | `/api/v1/rules/search` | 按任務上下文召回適用的 active 規則 |

### [檢索](06-retrieval.md)

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/v1/search/find` | 語義搜尋 |
| POST | `/api/v1/search/search` | 上下文感知搜尋；`mode="context"` 返回可注入的組裝上下文 |
| POST | `/api/v1/search/grep` | 內容模式搜尋 |
| POST | `/api/v1/search/glob` | 文件模式匹配 |

### [Watch](15-watches.md)、[快照](11-snapshot.md)與 [OVPack](14-ovpack.md)

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/v1/watches` | 列出 watch，或按 `to_uri` 查詢 |
| GET | `/api/v1/watches/{task_id}` | 按任務 ID 獲取 watch |
| PATCH | `/api/v1/watches` | 按 `to_uri` 更新 watch |
| PATCH | `/api/v1/watches/{task_id}` | 按任務 ID 更新 watch |
| DELETE | `/api/v1/watches` | 按 `to_uri` 刪除 watch |
| DELETE | `/api/v1/watches/{task_id}` | 按任務 ID 刪除 watch |
| POST | `/api/v1/watches/trigger` | 按 `to_uri` 觸發 watch |
| POST | `/api/v1/watches/{task_id}/trigger` | 按任務 ID 觸發 watch |
| POST | `/api/v1/snapshot/commit` | 建立快照 |
| GET | `/api/v1/snapshot/log` | 檢視快照歷史 |
| GET | `/api/v1/snapshot/versions` | 列出 Compile 產出檔案的版本 |
| POST | `/api/v1/snapshot/restore` | 恢復歷史快照 |
| GET | `/api/v1/snapshot/show` | 查看快照或其中的文件 |
| GET | `/api/v1/snapshot/diff` | 對比快照 |
| GET | `/api/v1/snapshot/diff-paths` | 分頁列出變化的原始檔 |
| GET | `/api/v1/snapshot/ignore` | 讀取快照忽略規則 |
| PUT | `/api/v1/snapshot/ignore` | 替換快照忽略規則 |
| DELETE | `/api/v1/snapshot/ignore` | 清空快照忽略規則 |
| POST | `/api/v1/pack/export` | 匯出 `.ovpack` |
| POST | `/api/v1/pack/import` | 匯入 `.ovpack` |
| POST | `/api/v1/pack/backup` | 備份公開作用域 |
| POST | `/api/v1/pack/restore` | 恢復備份包 |

### [後臺任務](17-tasks.md)、[執行觀測](18-observer.md)與 [Metrics](09-metrics.md)

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/v1/compile` | 建立由 OV 託管的 Compile 任務 |
| GET | `/api/v1/compile/capabilities` | 檢查 Compile 可用性 |
| GET | `/api/v1/compile/submissions/{key}` | 按提交鍵查詢任務 |
| GET | `/api/v1/tasks/{task_id}` | 獲取後臺任務 |
| POST | `/api/v1/tasks/{task_id}/cancel` | 取消後臺任務 |
| GET | `/api/v1/tasks` | 列出後臺任務 |
| GET | `/api/v1/tasks/events` | 串流推送後臺任務變更（SSE） |
| GET | `/api/v1/observer/queue` | 佇列狀態 |
| GET | `/api/v1/observer/vikingdb` | VikingDB 狀態 |
| GET | `/api/v1/observer/models` | 模型狀態 |
| GET | `/api/v1/observer/lock` | 鎖狀態 |
| GET | `/api/v1/observer/retrieval` | 檢索狀態 |
| GET | `/api/v1/observer/filesystem` | 檔案系統狀態 |
| GET | `/api/v1/observer/system` | 聚合執行狀態 |
| GET | `/metrics` | Prometheus 指標 |

### [管理員](08-admin.md)與[隱私配置](10-privacy.md)

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/v1/admin/configuration` | 獲取 Cluster 層顯式執行時配置 |
| PATCH | `/api/v1/admin/configuration` | 更新 Cluster 層執行時配置 |
| POST | `/api/v1/admin/configuration/test-model` | 測試草稿模型或 Embedding 連線，不儲存配置 |
| POST | `/api/v1/admin/restart` | 請求支援該能力的服務程序優雅重啟（僅 ROOT） |
| GET | `/api/v1/admin/accounts/{account_id}/configuration` | 獲取 Account 層顯式執行時配置 |
| PATCH | `/api/v1/admin/accounts/{account_id}/configuration` | 更新 Account 層執行時配置 |
| GET | `/api/v1/admin/agent-evolution` | 獲取 Agent 進化狀態（deprecated） |
| PUT | `/api/v1/admin/agent-evolution` | 更新 Agent 進化狀態（deprecated） |
| GET | `/api/v1/admin/accounts/{account_id}/settings` | 獲取存量帳號配置（deprecated） |
| PATCH | `/api/v1/admin/accounts/{account_id}/settings` | 更新存量帳號配置（deprecated） |
| GET | `/api/v1/admin/accounts/{account_id}/memory-templates` | 列出可編輯記憶模板、預設值及生效值 |
| GET | `/api/v1/admin/accounts/{account_id}/memory-templates/{memory_type}` | 查詢單個記憶模板 |
| PUT | `/api/v1/admin/accounts/{account_id}/memory-templates/{memory_type}` | 補齊併發布單個記憶模板 |
| DELETE | `/api/v1/admin/accounts/{account_id}/memory-templates/{memory_type}` | 刪除記憶模板覆蓋，恢復部署預設值 |
| POST | `/api/v1/admin/accounts` | 建立帳號及首個管理員 |
| GET | `/api/v1/admin/accounts` | 列出帳號 |
| POST | `/api/v1/admin/migrate` | 預留遷移入口；僅 ROOT 可呼叫，當前返回 400 INVALID_ARGUMENT |
| GET | `/api/v1/admin/accounts/{account_id}` | 獲取單個帳號的無憑據後設資料 |
| DELETE | `/api/v1/admin/accounts/{account_id}` | 刪除帳號 |
| POST | `/api/v1/admin/accounts/{account_id}/users` | 註冊使用者 |
| GET | `/api/v1/admin/accounts/{account_id}/users` | 列出使用者 |
| GET | `/api/v1/admin/accounts/{account_id}/users/{user_id}` | 獲取單個使用者的無憑據成員資訊（user_id、role） |
| GET | `/api/v1/admin/accounts/{account_id}/users/{user_id}/settings` | 獲取使用者記憶策略 |
| PATCH | `/api/v1/admin/accounts/{account_id}/users/{user_id}/settings` | 更新使用者記憶策略 |
| DELETE | `/api/v1/admin/accounts/{account_id}/users/{user_id}` | 移除使用者 |
| PUT | `/api/v1/admin/accounts/{account_id}/users/{user_id}/role` | 在 USER 與 ADMIN 之間變更使用者角色 |
| POST | `/api/v1/admin/accounts/{account_id}/users/{user_id}/key` | 重新生成使用者 Key |
| POST | `/api/v1/admin/accounts/{account_id}/groups` | 建立使用者組 |
| GET | `/api/v1/admin/accounts/{account_id}/groups` | 列出使用者組 |
| DELETE | `/api/v1/admin/accounts/{account_id}/groups/{group_id}` | 刪除使用者組 |
| GET | `/api/v1/admin/accounts/{account_id}/groups/{group_id}/members` | 列出使用者組成員 |
| PUT | `/api/v1/admin/accounts/{account_id}/groups/{group_id}/members` | 批次新增使用者組成員 |
| DELETE | `/api/v1/admin/accounts/{account_id}/groups/{group_id}/members/{user_id}` | 移除使用者組成員 |
| GET | `/api/v1/privacy-configs` | 列出隱私配置分類 |
| GET | `/api/v1/privacy-configs/tree` | 樹形列出當前目標和欄位後設資料，不返回值 |
| POST | `/api/v1/privacy-configs/scan` | 掃描或修復正文中的登記值 |
| GET | `/api/v1/privacy-configs/{category}` | 列出分類目標 |
| GET | `/api/v1/privacy-configs/{category}/{target_key}` | 獲取生效配置 |
| GET | `/api/v1/privacy-configs/{category}/{target_key}/fields` | 列出不含明文值的安全欄位後設資料 |
| GET | `/api/v1/privacy-configs/{category}/{target_key}/field` | 獲取單欄位引用或顯式讀取值 |
| POST | `/api/v1/privacy-configs/resolve` | 按欄位 reference/URI 顯式讀取值 |
| GET | `/api/v1/privacy-configs/{category}/{target_key}/versions` | 列出配置版本 |
| GET | `/api/v1/privacy-configs/{category}/{target_key}/versions/{version}` | 獲取指定版本 |
| POST | `/api/v1/privacy-configs/{category}/{target_key}` | 寫入並激活新版本 |
| PATCH | `/api/v1/privacy-configs/{category}/{target_key}` | 原子合併欄位；不存在時建立 |
| POST | `/api/v1/privacy-configs/{category}/{target_key}/activate` | 啟用指定版本 |
| DELETE | `/api/v1/privacy-configs/{category}/{target_key}` | 刪除目標及全部版本 |
| DELETE | `/api/v1/privacy-configs/{category}/{target_key}/field` | 刪除當前欄位 |
| DELETE | `/api/v1/privacy-configs/selector` | 按 URI/reference 刪除目標或欄位 |

### [OpenViking 閘道器管理](25-gateway.md)

閘道器在 Server 內執行時，從 Server 埠訪問；獨立執行時，從閘道器自己的埠訪問。OpenViking API 金鑰決定呼叫方能訪問哪個帳號；部署者設定了閘道器管理金鑰時，修改上游和上下文配置還需要這把金鑰。每個使用者都能給自己簽發閘道器金鑰。許可權矩陣和錯誤原因見[閘道器管理 API](25-gateway.md)。

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/gateway/admin/access` | 讀取呼叫方的許可權和部署告警 |
| GET | `/gateway/admin/guides` | 讀取客戶端使用的閘道器地址 |
| GET | `/gateway/admin/tools` | 列出呼叫方可用的 OpenViking 工具 |
| GET | `/gateway/admin/upstreams/{identifier}` | 讀取單個上游 |
| GET | `/gateway/admin/policies/{identifier}` | 讀取單個上下文配置 |
| GET | `/gateway/admin/keys/{identifier}` | 讀取單個閘道器金鑰（不含金鑰本身） |
| GET | `/gateway/admin/overview` | 讀取呼叫方可見範圍內的用量概覽 |
| GET | `/gateway/admin/logs` | 讀取呼叫方可見的請求日誌 |
| GET | `/gateway/admin/upstreams` | 列出本帳號的上游 |
| PUT / DELETE | `/gateway/admin/upstreams/{identifier}` | 建立/替換或刪除上游 |
| POST | `/gateway/admin/upstreams/{identifier}/test` | 測試上游連線或模型 |
| POST | `/gateway/admin/upstreams/import-vlm` | 把 Server 的 VLM 配置匯入為上游（僅嵌入部署） |
| GET | `/gateway/admin/policies` | 列出本帳號的上下文配置 |
| PUT / DELETE | `/gateway/admin/policies/{identifier}` | 建立/替換或刪除上下文配置 |
| GET / POST | `/gateway/admin/keys` | 列出呼叫方可見的閘道器金鑰，或簽發新金鑰 |
| DELETE | `/gateway/admin/keys/{identifier}` | 吊銷閘道器金鑰 |
| POST | `/gateway/admin/keys/{identifier}/capture/reset` | 讓一段對話重新開始儲存 |
| DELETE | `/gateway/admin/users/{user_id}/data` | admin 或 root：刪除某個使用者的閘道器資料 |
| DELETE | `/gateway/admin/account/data` | root：刪除整個帳號的閘道器資料 |

### [OpenViking Assets](22-openviking-assets.md)、[WebDAV](20-webdav.md)、[Agent Runtime API](23-agent-runtime.md) 與 [VikingBot API](24-vikingbot.md)

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/v1/openviking-assets/resolve` | 解析並校驗 Catalog 與 Manifest，返回標準化資產計劃 |
| POST | `/api/v1/openviking-assets/preflight` | 只讀校驗 Git 倉庫和 ref 的訪問許可權 |
| OPTIONS | `/webdav/resources`、`/webdav/resources/{resource_path}` | 查詢 WebDAV 能力 |
| PROPFIND | `/webdav/resources`、`/webdav/resources/{resource_path}` | 查詢資源屬性 |
| GET / HEAD | `/webdav/resources`、`/webdav/resources/{resource_path}` | 讀取檔案或目錄 |
| PUT | `/webdav/resources`、`/webdav/resources/{resource_path}` | 寫入 UTF-8 文本檔案 |
| DELETE | `/webdav/resources`、`/webdav/resources/{resource_path}` | 刪除檔案或目錄 |
| MKCOL | `/webdav/resources`、`/webdav/resources/{resource_path}` | 建立目錄 |
| MOVE | `/webdav/resources`、`/webdav/resources/{resource_path}` | 移動或重新命名資源 |
| POST | `/api/v1/compile` | 建立非同步 Compile 任務 |
| GET | `/api/v1/compile/config` | 讀取目標配置 |
| POST | `/api/v1/compile/config/update` | 更新目標配置 |
| GET | `/api/v1/compile/configs` | 列出可見目標 |
| GET | `/api/v1/compile/operations` | 列出目標操作記錄 |
| GET | `/api/v1/compile/operations/{operation_id}` | 讀取單條操作詳情 |
| GET | `/api/v1/compile/operations/{operation_id}/outputs` | 列出操作產出及版本引用 |
| POST | `/api/v1/compile/embeddings` | 生成 Compile 臨時路由文本的向量 |
| GET | `/api/v1/compile/capabilities` | 檢查 Compile 可用性 |
| GET | `/api/v1/compile/submissions/{key}` | 按提交鍵查詢任務 |
| GET | `/bot/v1/health` | VikingBot 健康檢查 |
| POST | `/bot/v1/chat` | VikingBot 非流式對話 |
| POST | `/bot/v1/chat/stream` | VikingBot 流式對話 |
| POST | `/bot/v1/feedback` | 提交 VikingBot 回答反饋 |
| POST | `/bot/v1/sessions/{session_id}/interrupt` | 中斷活躍或排隊中的 VikingBot 會話 |
| POST | `/bot/v1/sessions/{session_id}/steer` | 向活躍流式會話傳送追加輸入 |
| POST | `/bot/v1/compile` | 已停用；返回新介面遷移提示 |
| GET | `/bot/v1/compile/{task_id}` | 已停用；返回 Task 介面遷移提示 |
| POST | `/bot/v1/compile/{task_id}/cancel` | 已停用；返回 Task 取消介面遷移提示 |

---

## 按任務查詢介面

按操作型別選擇對應文件：

| 分組 | 適合查詢的內容 |
|------|----------------|
| 核心資料 | 資源、內容、檔案系統、技能、會話、記憶 |
| 檢索 | 語義檢索、程式碼檢索 |
| 資料生命週期 | Watch、快照、OVPack |
| 運維與觀測 | 系統、任務、Observer、Metrics |
| 身份與治理 | 管理員、ACL、隱私配置 |
| 協議與擴充 | OpenViking Assets、WebDAV、Agent Runtime API、VikingBot API |
