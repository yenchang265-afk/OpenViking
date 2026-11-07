---
description: 接入遠端 MCP Server，將工具掛載為即時上下文，並使用 CLI、SDK、Studio 和 Context as Code 編排節點。
---

# 即時上下文接入與編排

即時上下文（Live Context）把遠端 MCP Tool 掛載為 `viking://resources/...` 下的 Markdown 節點。Agent 不需要了解上游地址、鑑權方式和固定引數，只需像讀取普通上下文一樣讀取節點；OpenViking 會執行繫結的 Tool，並透明返回上游結果。

本頁面向實現和維護上下文編排的開發者，說明 MCP 註冊、Tool Catalog、即時節點、Agent Gateway、Studio 和 Context as Code（CaC）之間的關係。MCP 客戶端連線方式和 OpenViking 內建 MCP Tool 的完整清單見 [MCP 工具與協議](06-mcp-integration.md)。

## 核心模型

這套能力分為控制面和資料面：

| 層次 | 職責 | 主要入口 |
| --- | --- | --- |
| MCP 註冊與同步 | 儲存 MCP Server 連線資訊，將 Tool 定義同步進 OpenViking | `ov mcps add/validate/sync/status`、REST、SDK |
| Tool Catalog | 讓 Tool 定義可檢索、可讀取，並儲存完整定義和輸入版本 | `viking://~/tools/<server>/<tool>.json` 或 `viking://agent/tools/<server>/<tool>.json` |
| 即時上下文 | 將一個 Tool、固定引數和目標 URI 繫結為可讀節點 | `ov mcps mount/unmount/mounts`、REST、SDK |
| Agent Gateway | 按意圖發現低頻 Tool，並安全代理呼叫 | MCP `find_mcp_tools`、`invoke_mcp_tool` |
| 上下文編排 | 宣告一組期望節點，計算差異並持續收斂 | Studio Arranger、Python `ContextArranger` |

典型鏈路如下：

```text
Remote MCP Server
        |
        | validate / add / sync
        v
viking://~/tools/<server>/<tool>.json
or viking://agent/tools/<server>/<tool>.json
        |
        | mount + preset arguments
        v
viking://resources/<project>/<node>.md
        |
        | complete read
        v
OpenViking resolves credentials -> calls upstream Tool -> returns native Tool result
```

高頻、引數穩定的場景適合預先掛載為即時上下文；低頻或引數依賴當前問題的場景適合由 Agent 使用 `find_mcp_tools` 和 `invoke_mcp_tool` 動態發現並呼叫。

## 前提和安全邊界

- 僅支援 Streamable HTTP MCP Server。
- 地址可以使用 HTTP 或 HTTPS。HTTP 不提供傳輸加密，使用方需自行評估憑證和工具資料的暴露風險。
- MCP Server 名稱只能包含字母、數字、`_` 和 `-`，最長 64 個字元。
- Tool 名稱必須能作為 OpenViking 檔名。
- 註冊時會連線上游並執行 Tool discovery；無法連線或 Tool 定義不合法時不會寫入註冊資訊。
- Header 由 OpenViking 服務端儲存並用於上游呼叫。CLI 示例應從環境變數構造配置，不要把真實憑證提交到倉庫。
- `invoke` 和即時節點讀取可能產生外部副作用。OpenViking 不會自動重試未知結果的 Tool 呼叫。
- 掛載引數會按 Tool 的 `inputSchema` 校驗；缺少必填引數或型別不匹配時掛載失敗。
- 使用者空間 `viking://~/tools` 和帳號共享空間 `viking://agent/tools` 都是受管目錄，不能使用普通 `mkdir`、`rm`、`cp` 或 `mv` 修改。

## 使用 `ov mcps`

### 驗證並註冊 Server

先驗證連線和 Tool discovery，不寫入配置：

```bash
MCP_TOKEN='replace-me'
ov mcps validate "$(jq -cn \
  --arg token "$MCP_TOKEN" \
  '{mcpServers:{weather:{url:"https://mcp.example.com/mcp",headers:{Authorization:("Bearer " + $token)}}}}')"
```

驗證通過後註冊。`add` 預設寫入當前使用者的 `viking://~/tools`，會立即寫入發現到的 Tool Catalog，並讓摘要和索引在後臺繼續處理：

```bash
ov mcps add "$(jq -cn \
  --arg token "$MCP_TOKEN" \
  '{mcpServers:{weather:{url:"https://mcp.example.com/mcp",headers:{Authorization:("Bearer " + $token)}}}}')"
```

共享給帳號內所有使用者時顯式選擇帳號空間：

```bash
ov mcps add -p viking://agent/tools "$(jq -cn \
  --arg token "$MCP_TOKEN" \
  '{mcpServers:{weather:{url:"https://mcp.example.com/mcp",headers:{Authorization:("Bearer " + $token)}}}}')"
```

需要確認 Tool 摘要和索引處理完成後再返回時，加 `-w` 或 `--wait`：

```bash
ov mcps add -p viking://agent/tools --wait "$(jq -cn \
  --arg token "$MCP_TOKEN" \
  '{mcpServers:{weather:{url:"https://mcp.example.com/mcp",headers:{Authorization:("Bearer " + $token)}}}}')"
```

檢視註冊狀態和 Tool 定義：

```bash
ov mcps list
ov mcps show -p viking://agent/tools weather
ov mcps status -p viking://agent/tools weather
```

相關命令：

| 命令 | 用途 |
| --- | --- |
| `ov mcps validate <json>` | 驗證連線和 Tool discovery，不持久化 |
| `ov mcps add <json> [-p <tools-root>] [-w\|--wait]` | 註冊一個或多個 Server；`-p` 預設 `viking://~/tools` |
| `ov mcps list [-p <tools-root>]` | 預設合併列出使用者與共享 Server；`-p` 限定空間 |
| `ov mcps show <name> [-p <tools-root>]` | 檢視 Server；名稱型操作預設使用者空間 |
| `ov mcps status <name> [-p <tools-root>]` | 即時檢查連線狀態；名稱型操作預設使用者空間 |
| `ov mcps remove <name> [-p <tools-root>]` | 刪除指定空間的 Server 註冊和 Tool Catalog |

### 查詢和直接呼叫 Tool

Tool Catalog 支援語義檢索：

```bash
ov mcps find "查詢北京的天氣" --limit 5
```

`list` 和 `find` 未傳 `-p` 時會合並用戶與共享空間；其他名稱型管理命令未傳 `-p` 時使用使用者空間。同名 Server 可以同時存在於兩個空間，通過返回的 `root_uri` 和 `-p` 消歧。

根據結果中的 Tool URI 和引數定義直接呼叫：

```bash
ov mcps invoke \
  viking://agent/tools/weather/current.json \
  --args '{"city":"Beijing"}'
```

`invoke` 由服務端解析 MCP Server 地址和 Header，並保留上游 Tool 的原生 `content`、`structuredContent` 和 `isError`。

### 掛載即時上下文

將固定引數繫結到一個 Markdown URI：

```bash
ov mcps mount \
  viking://agent/tools/weather/current.json \
  viking://resources/arrange/beijing-weather.md \
  --title "北京天氣" \
  --description "北京地區的即時天氣。" \
  --args '{"city":"Beijing"}' \
  --timeout-seconds 60 \
  --wait
```

讀取節點會執行上游 Tool：

```bash
ov read viking://resources/arrange/beijing-weather.md
```

檢視和刪除掛載：

```bash
ov mcps mounts -p viking://agent/tools --mcp weather
ov mcps mounts -p viking://agent/tools --mcp weather --tool current
ov mcps unmount viking://resources/arrange/beijing-weather.md --wait
```

`mount` 對同一個 `node_uri` 是收斂式寫入：再次執行會更新 Tool、引數、標題和描述，並保留最初的 `created_at`。刪除節點應使用 `ov mcps unmount`，使 Markdown 節點和掛載記錄一起刪除。

### 同步 Tool Catalog

上游 Tool 定義變化後執行：

```bash
ov mcps sync -p viking://agent/tools weather
```

摘要和索引預設在後臺繼續處理。需要等待 Tool Catalog 的新增、更新、刪除及索引重新整理全部完成時執行：

```bash
ov mcps sync -p viking://agent/tools weather --wait
```

同步結果把 Tool 分為 `added`、`changed`、`unchanged` 和 `removed`，並列出受影響的即時節點：

| 掛載狀態 | 含義 | 建議處理 |
| --- | --- | --- |
| `REVIEW` | Tool input revision 已變化，但現有引數仍符合新 schema | 檢查語義變化後重新掛載確認 |
| `INVALID` | Tool input revision 已變化，現有引數不再符合新 schema | 修正引數並重新掛載 |
| `REMOVED` | 上游不再提供該 Tool | 改綁其他 Tool，或顯式 unmount |

`sync` 不會自動刪除受影響的即時節點。這樣可以避免上游一次臨時變更直接破壞已編排的目錄；節點的清理仍由操作者或 CaC 的 `apply --prune` 決定。

當前 Tool 的 `revision` 覆蓋完整的上游 Tool 定義；`input_revision` 根據 Tool 名稱和 `inputSchema` 計算，用於判斷引數契約是否變化。只修改描述、annotations 或輸出 schema 時，Tool Catalog 會通過 `revision` 重新整理，但不會改變 `input_revision`，也不會觸發掛載檢查。

## 即時節點的資料模型

掛載會生成一個帶 YAML frontmatter 的 Markdown 描述檔案。下面是等價結構的示意：

```markdown
---
type: OpenViking Live Context
title: 北京天氣
description: 北京地區的即時天氣。
x-openviking:
  schema_version: v1
  type: mcp
  definition: viking://agent/tools/weather/current.json
  input_revision: <tool-input-revision>
  args:
    city: Beijing
  timeout_seconds: 60
  retry:
    max_attempts: 3
    backoff_seconds: 1
    backoff_multiplier: 2
    max_backoff_seconds: 5
---
```

不要把這個檔案當作普通 Markdown 手工維護。掛載關係還記錄在帳號級 `live_context_nodes.dat` 中，用於列舉掛載、跟蹤 input revision 和安全解除安裝；只修改檔案會讓描述檔案與掛載記錄失去一致性。

`retry` 是節點格式中的預留策略後設資料。當前執行鏈路不會據此自動重試 Tool 呼叫，避免在結果未知時重複產生外部副作用。

Tool Catalog 與對應空間的登錄檔，以及帳號級掛載資料庫都屬於受管狀態：

```text
viking://~/tools/<server>/<tool>.json
viking://agent/tools/<server>/<tool>.json
<account>/_system/mcps/<user-id>.json
<account>/_system/mcps.json
<account>/_system/live_context_nodes.dat
```

後兩個位置是內部儲存路徑，不是面向使用者的 Viking URI。

## 讀取語義

即時執行只發生在完整讀取：

- REST/CLI：`offset=0` 且 `limit=-1`。
- MCP `read`：預設完整讀取。
- 返回值是上游 MCP Tool 結果，不附加節點 frontmatter 或額外標籤。
- 未宣告 annotations 的工具預設按只讀處理。`readOnlyHint: false` 或 `destructiveHint: true` 的工具不會由 `read` 執行；錯誤會返回掛載 URI 和引數，供當前整合顯式呼叫。
- 分頁讀取只返回已儲存的描述檔案，不呼叫上游 Tool。
- `find`、`search`、`list` 和 `tree` 不會隱式執行即時節點。
- REST `read?raw=true` 返回原始描述檔案，不執行 Tool。

這些規則保證檢索和目錄瀏覽保持無副作用，同時允許把寫工具掛載為 Agent 指引。Agent 應先通過檢索定位節點，再呼叫 `read` 獲取即時結果；寫工具必須通過具備獨立許可權的 `invoke_mcp_tool` 呼叫。

## Agent 動態發現

OpenViking MCP endpoint 額外提供兩個資料面工具：

1. `find_mcp_tools(query, limit=10)`：語義檢索 Tool，返回 `uri`、`score` 和完整 `tool` 定義，包括 `inputSchema` 與 annotations。
2. `invoke_mcp_tool(tool_uri, arguments={})`：代理呼叫選中的 Tool，服務端解析連線資訊和憑證。

典型 Agent 流程：

```text
使用者意圖
  -> find_mcp_tools
  -> 根據 tool.inputSchema 填充 arguments
  -> invoke_mcp_tool
  -> 使用原生 MCP Tool 結果
```

這兩個介面不暴露 Server 註冊、同步和掛載等控制面操作。動態發現適合低頻需求；高頻場景應掛載成語義穩定、引數已預繫結的即時節點，減少 Agent 的決策和試錯。

## SDK 編排

Python、Go 和 TypeScript SDK 都提供 MCP 註冊、發現、呼叫、掛載和同步 API。Python 還提供 `ContextArranger`，用於宣告期望狀態並批次收斂即時節點。

### 直接使用 SDK

```python
import os

from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(
    url=os.environ.get("OPENVIKING_URL", "http://127.0.0.1:1933"),
    api_key=os.environ.get("OPENVIKING_API_KEY"),
)
client.initialize()

client.mount_mcp_tool(
    tool_uri="viking://agent/tools/weather/current.json",
    node_uri="viking://resources/arrange/beijing-weather.md",
    title="北京天氣",
    arguments={"city": "Beijing"},
    tags=["project=weather"],
    wait=True,
)
```

批次場景使用 `batch_mount_mcp_tools` 和 `batch_unmount_mcp_tools`。批次介面先校驗整批宣告，再按資源根目錄寫入，減少網路往返；同一批次不能重複宣告 `node_uri`。

### Context as Code

```python
import os

from openviking_sdk import ContextArranger, SyncHTTPClient

client = SyncHTTPClient(
    url=os.environ.get("OPENVIKING_URL", "http://127.0.0.1:1933"),
    api_key=os.environ.get("OPENVIKING_API_KEY"),
)
client.initialize()

arranger = ContextArranger(
    client,
    name="weather-live-context",
    root_uri="viking://resources/arrange",
)

arranger.live_context(
    "beijing-weather.md",
    tool_uri="viking://agent/tools/weather/current.json",
    title="北京天氣",
    arguments={"city": "Beijing"},
    tags=["domain=weather"],
)

raise SystemExit(arranger.main())
```

指令碼自帶 CLI：

```bash
python arrange.py plan
python arrange.py plan --output json
python arrange.py apply --dry-run
python arrange.py apply --wait
python arrange.py apply --prune --wait
```

`ContextArranger` 的行為：

- `plan` 始終展示 `CREATE`、`UPDATE`、`DELETE`、`UNCHANGED` 和 `CONFLICT`。
- `apply` 預設只建立和更新；待刪除項顯示為 `PENDING DELETE`。
- `apply --prune` 才刪除由當前 arrangement 擁有、但不再宣告的節點。
- `--dry-run` 不修改遠端狀態；`--wait` 等待索引處理完成。
- 預設輸出適合人閱讀的表格，`--output json` 適合自動化。
- 通過 `ov-cac-owner`、`ov-cac-kind` 和規格指紋標籤識別所有權與漂移。
- 目標 URI 已存在但不歸當前 arrangement 管理時返回衝突，不會覆蓋。
- `root_uri` 可以位於帳號共享的 `viking://resources` 下，也可以位於規範化的使用者私有
  `viking://user/<user_id>/resources` 下；呼叫方必須具備所選根目錄的訪問許可權。

一個 `ContextArranger` 只管理自己 `root_uri` 下、帶有其 owner 標籤的即時節點。不要讓兩個 arrangement 使用同一個 name 和重疊的 root 管理不同宣告。

## Studio Arranger

OpenViking Studio 的 **Arranger** 頁面提供同一模型的視覺化入口：

- 瀏覽和語義檢索已同步的 MCP Tool。
- 根據 `inputSchema` 配置固定引數。
- 建立、更新和刪除即時上下文節點。
- 在上下文圖中檢視 Tool 與目標節點的關係。
- 在執行變更前檢查目標路徑和已有即時節點，避免覆蓋不相關資源。

Studio、CLI、REST 和 SDK 共用同一組服務端 API 和掛載資料庫，因此可以組合使用；但長期維護的一組節點建議選擇一個宣告式來源作為事實源。

## REST API

SDK 和 Studio 使用以下介面：

| 方法 | 路徑 | 用途 |
| --- | --- | --- |
| `POST` | `/api/v1/mcps` | 註冊 MCP Server |
| `DELETE` | `/api/v1/mcps/{name}` | 刪除 MCP Server |
| `GET` | `/api/v1/mcps` | 列出 Server |
| `GET` | `/api/v1/mcps/{name}` | 檢視 Server 和 Tool |
| `POST` | `/api/v1/mcps/validate` | 驗證連線 |
| `POST` | `/api/v1/mcps/{name}/sync` | 同步 Tool Catalog |
| `GET` | `/api/v1/mcps/status?name=...` | 檢查上游狀態 |
| `POST` | `/api/v1/mcps/find` | 語義檢索 Tool |
| `POST` | `/api/v1/mcps/invoke` | 呼叫 Tool |
| `POST` | `/api/v1/mcps/mount` | 掛載單個即時節點 |
| `POST` | `/api/v1/mcps/batch-mount` | 批次掛載 |
| `DELETE` | `/api/v1/mcps/mount?node_uri=...` | 解除安裝單個節點 |
| `POST` | `/api/v1/mcps/batch-unmount` | 批次解除安裝 |
| `GET` | `/api/v1/mcps/mounts?mcp=...&tool=...` | 查詢掛載 |

介面使用當前 OpenViking 使用者的身份上下文。使用者空間的 Server 註冊和 Tool Catalog 按使用者隔離，共享空間及掛載資料庫按帳號隔離；目標資源 URI 仍按正常的身份和 ACL 規則校驗。註冊、刪除、檢視、同步、狀態和掛載查詢支援 `target_uri`，列出和檢索在未指定時合併兩個空間。

## 運維建議

- 註冊前先執行 `validate`，註冊後執行 `status` 和一次無副作用 Tool 呼叫。
- 上游升級後執行 `sync`，重點處理 `INVALID` 和 `REMOVED` 掛載。
- 自動化環境使用 JSON 輸出，並保留 `plan` 作為變更審計記錄。
- 生產 CaC 執行先 `plan` 或 `apply --dry-run`，確認後再 `apply --prune`。
- 需要讀取結果後立刻檢索到最新節點時使用 `--wait`；批次釋出但不依賴即時索引時可非同步處理。
- 刪除 Server 前先查詢並處理其掛載。刪除 Server 會移除 Tool Catalog，但不會代替業務方重新編排節點。
- 定期備份 OpenViking 帳號資料；MCP 註冊和掛載記錄與其他帳號資料一起持久化。

## 故障排查

| 現象 | 常見原因 | 處理 |
| --- | --- | --- |
| 註冊或驗證失敗 | URL 無效、網路不可達、Header 錯誤、不是 Streamable HTTP | 檢查 URL 和 Header，並用 `ov mcps validate` 重試 |
| `find` 沒有結果 | Tool Catalog 未釋出、索引尚未完成、查詢不匹配 | `ov mcps show` 確認 Tool，執行 `sync`，必要時等待索引完成 |
| 掛載提示引數不合法 | 引數不符合當前 `inputSchema` | 從 `show` 或 `find` 結果重新生成引數 |
| `read` 返回描述檔案 | 使用了分頁讀取或 `raw=true` | 使用預設完整讀取 |
| `read` 呼叫失敗且結果未知 | 上游超時或連線在呼叫中斷開 | 先確認上游實際狀態；OpenViking 不會自動重試可能有副作用的呼叫 |
| `sync` 返回 `REVIEW` | Tool input revision 改變但引數仍合法 | 檢查 Tool 語義後重新掛載 |
| `sync` 返回 `INVALID` | 新 schema 不再接受已繫結引數 | 修改引數並重新掛載 |
| `sync` 返回 `REMOVED` | Tool 已從上游刪除 | 繫結替代 Tool，或顯式 unmount |
| CaC 返回 `CONFLICT` | 目標已存在但不歸當前 arrangement 所有 | 更換 URI，或先確認並遷移現有節點 |
| 普通 `apply` 沒刪除節點 | 刪除預設受保護 | 檢視 `PENDING DELETE`，確認後執行 `apply --prune` |

## 設計取捨

| 設計 | 原因 | 代價 |
| --- | --- | --- |
| Tool 定義釋出到 VikingFS | Tool 可被統一檢索、讀取和版本化 | 上游變化後需要顯式 `sync` |
| 引數在掛載時預繫結 | 高頻場景呼叫穩定，Agent 不需重複推斷固定引數 | 引數變化需要重新掛載 |
| 完整 `read` 才執行 | 檢索、列表和分頁瀏覽保持無副作用 | 除錯描述檔案需要分頁或 raw 讀取 |
| 同步不自動刪除節點 | 上游變化不會直接破壞業務目錄 | 操作者必須處理 `REVIEW/INVALID/REMOVED` |
| CaC 預設不 prune | 避免宣告遺漏造成意外刪除 | 清理需要顯式 `--prune` |
| 呼叫不自動重試 | 避免未知結果下重複產生副作用 | 瞬時故障需要業務側判斷後重試 |
