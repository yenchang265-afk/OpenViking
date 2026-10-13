# API 文件編寫規範

本文件定義 `docs/zh/api/` 目錄下各 API 模組文件的統一結構和編寫規範。

## 保持文件可用與及時

- 在同一 PR 中更新中英文頁面、導航和示例。相同內容保留一個主要說明入口，相關頁面通過連結引用。
- 先寫讀者任務、前置條件、可執行示例和預期結果，實現細節放在使用說明之後。
- 根據當前實現核驗預設值和支援的選項。區分已釋出行為、`main` 上的實現和後續計劃，必要時連結到對應 release 或 PR。
- 可複製配置使用合法 JSON；片段或虛擬碼需明確標註，不在 `json` 程式碼塊中混入註釋。
- 外部工具和服務引用官方文件，只介紹當前任務需要的配置，不復制整套手冊。
- 提交前在 `docs/` 執行 `npm run check:docs`、`npm run check:api` 和 `npm run docs:build`。自動檢查覆蓋結構與示例，不能替代事實核驗和翻譯 review。

## 文案標準

- 先說明介面做什麼、適用條件和呼叫結果，再解釋實現。讀者應能據此決定下一步。
- 用具體動作和物件代替“賦能”“閉環”“智慧升級”等空泛表述。術語保留準確含義，不為縮短句子省掉前提。
- 不寫無依據的效果、效能、費用或安全承諾。預設值、支援範圍和失敗行為以當前實現為準；示例值明確標註。
- 區分已提交與已完成、可選與必需、當前能力與規劃。總覽、參數列、示例和排障說明應一致。
- 中文按自然語序寫，英文按英文習慣寫；兩者保持相同的事實和限制，不逐詞硬譯。
- 保留有用的章節連結；改標題時檢查舊錨點，必要時新增相容錨點。

## 目錄結構

API 文件按模組組織，每個模組一個檔案，使用兩位數字序號字首。

## 檔案統一結構

每個 API 模組文件應遵循以下結構：

````markdown
# <模組名稱>

<簡短介紹，說明本模組的主要功能和用途>

## <可選的概念/介紹章節>

（如需要，介紹本模組涉及的核心概念、工作流程等）

## API 參考

### <API 方法名 1>

#### 1. 用途與前置條件

<說明介面的操作、適用場景，以及需要的許可權、配置或已有資源>

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| <引數名> | <型別> | <是/否> | <預設值> | <詳細說明> |
| ... | ... | ... | ... | ... |

**<可選的補充說明章節>**

（如需要，說明特殊行為、注意事項、使用場景等）

#### 3. 使用示例

**Python SDK**

```text
<SDK 呼叫示例>
```

**TypeScript SDK**

```typescript
<SDK 呼叫示例>
```

**Go SDK**

```go
<SDK 呼叫示例>
```

**HTTP API**

```
<HTTP 方法> <路徑>
```

```bash
<curl 示例>
```

**CLI**

```bash
<CLI 命令示例>
```

**響應示例**

```json
<JSON 響應示例>
```

#### 4. 響應契約（必填）與錯誤處理（可選）

每個公開操作都必須說明成功返回值。JSON 介面至少給出一個與實現一致的響應包示例；檔案下載、SSE、WebDAV 等非 JSON 介面必須說明 HTTP 狀態、關鍵響應頭、響應體或事件格式。不能只寫“返回某些欄位”而不展示結構。錯誤和異常處理示例可按需補充。

#### 5. 實現細節（可選）

按需解釋處理流程，並連結到核心實現、HTTP 路由或 CLI 處理函式，幫助讀者理解行為或排查問題。

---

### <API 方法名 2>

（重複上述結構）

---

## <可選的其他章節>

## 相關文件

- [<文件標題>](<相對路徑>) - <簡短說明>
````

## 結構詳解

### 標題與簡介

- 一級標題是模組名稱
- 簡介用一段話說明該模組的用途和主要功能

### API 參考章節

每個介面按以下章節組織。實現細節放在響應契約之後，僅保留有助於理解行為或排障的內容。現有頁面仍使用舊的“API 實現介紹”章節和程式碼入口；新頁面及遷移頁面時按本結構編寫。

#### 1. 用途與前置條件

- 說明介面做什麼、適合什麼場景。
- 列出必需的許可權、配置和已有資源。
- 提前說明呼叫會產生的影響，包括覆蓋或刪除已有資料。

#### 2. 介面和引數說明

- 參數列：包含引數名、型別、是否必填、預設值、說明
- 補充說明（可選）：特殊行為、注意事項、使用場景等

#### 3. 使用示例

對於返回後臺任務的操作，預設示例優先使用“提交任務 → 查詢狀態”，儘量不主動設定 `wait`、`timeout`，也不使用全域 `wait_processed()` 代替任務狀態。完整引數參考應保留受支援引數及其真實預設值。後續操作依賴非同步產物時，應展示按 `task_id` 輪詢至 `completed`，並處理 `failed`、`cancelled`；不能僅刪除等待引數後立即讀取結果。

當一個介面並列展示所有呼叫方式時，建議按以下順序提供：
- Python SDK 示例
- TypeScript SDK 示例
- Go SDK 示例（當它能補充說明該介面的呼叫形態，且可以保持簡短時）
- HTTP API（方法 + 路徑 + curl 示例）
- CLI 示例
- 響應示例

示例切換由加粗標籤自動生成。呼叫方式標籤必須單獨成段，並使用以下固定基礎寫法：
`**Python SDK**`、`**TypeScript SDK**`、`**Go SDK**`、`**HTTP API**`、`**CLI**`。
需要區分呼叫形態時，把限定詞用半形括號寫在同一個加粗標籤內，例如
`**Python SDK (HTTP)**`；不要把限定詞寫在加粗標籤外，也不要使用全形括號。`**Python HTTP SDK**` 這類寫法匹配不到 Tab 規則，只會渲染成普通文本。
只展示實現中真實存在的呼叫方式；某個 SDK 或 CLI 沒有對應能力時應省略該 Tab，並簡短說明
可用的替代入口。不要把手寫 HTTP 請求包裝成不存在的 SDK 方法。

如果現有介面因工作流說明採用了特殊結構，應保持該區域性結構穩定，並將 TypeScript 放在其他
SDK 示例附近。

API 文件應按 API 模組和具體介面組織，而不是按客戶端語言組織。SDK 片段只作為對應介面
“使用示例”中的簡短呼叫示例出現。語言專屬 quick reference、完整 walkthrough 或跨介面串聯流程
應放在該 SDK 自己的文件中，不應新增到 API 模組頁面裡。

## 示例：完整介面文件

````markdown
### add_resource()

#### 1. 用途與前置條件

向知識庫新增資源，支援本地檔案、目錄、URL 等多種來源。

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| path | str | 是 | - | 本地路徑、目錄路徑或 URL |
| to | str | 否 | None | 最終資源 URI；目標已存在時會覆蓋 |
| reason | str | 否 | "" | 新增該資源的原因 |
| wait | bool | 否 | False | 是否等待語義處理完成 |

**說明**

- SDK/CLI 可直接傳本地路徑；裸 HTTP 需要先用 `temp_upload` 上傳
- 已存在的 `to` 目標會被覆蓋。目標為目錄時，本次匯入未生成的舊檔案可能被刪除；未變化的內容在語義和向量處理中會複用。向已有目錄新增資源時使用 `parent`。

#### 3. 使用示例

**HTTP API**

```
POST /api/v1/resources
```

```bash
curl -X POST http://localhost:1933/api/v1/resources \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "path": "https://example.com/guide.md",
    "reason": "User guide documentation"
  }'
```

**Python SDK**

```python
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(url="http://localhost:1933", api_key="your-key")

result = client.add_resource(
    path="./documents/guide.md",
    options={"reason": "User guide documentation"},
)
print(f"Task ID: {result['task_id']}")

print(client.get_task(result["task_id"]))
```

**CLI**

```bash
ov add-resource ./documents/guide.md --reason "User guide documentation"
```

#### 4. 響應契約

```json
{
  "status": "ok",
  "result": {
    "status": "success",
    "root_uri": "viking://resources/guide",
    "task_id": "uuid-xxx"
  }
}
```

#### 5. 實現細節

**處理流程**：
1. 識別資源型別（本地檔案/目錄/URL）
2. 呼叫對應 Parser 解析內容
3. 構建目錄樹並寫入 AGFS
4. 非同步生成 L0/L1 語義摘要
5. 建立向量索引

**程式碼入口**：
- `sdk/python/openviking_sdk/client.py:AsyncHTTPClient.add_resource()` - 非同步 SDK 入口
- `sdk/python/openviking_sdk/client.py:SyncHTTPClient.add_resource()` - 同步 SDK 入口
- `openviking/service/resource_service.py:ResourceService.add_resource()` - 核心實現
- `openviking/server/routers/resources.py:add_resource()` - HTTP 路由
- `crates/ov_cli/src/handlers.rs:handle_add_resource()` - CLI 處理函式

---
````

## 文件維護清單

新增或修改 API 文件時，請檢查：

- [ ] 用途、前置條件和呼叫影響清楚，引用的程式碼入口路徑正確
- [ ] 參數列完整且準確
- [ ] 示例程式碼簡潔且可執行
- [ ] 呼叫示例使用固定加粗標籤，並且每個 SDK/CLI Tab 都有真實實現
- [ ] HTTP 方法和路徑正確
- [ ] 每個公開操作都有成功響應契約，且示例與實際返回一致
