# 服務端配置欄位

首次配置建議使用 `openviking-server init`，儲存後執行 `openviking-server doctor`。

OpenViking 服務端讀取 `ov.conf`。預設路徑是：

```text
~/.openviking/ov.conf
```

也可以通過環境變數或啟動引數指定其他檔案：

```bash
export OPENVIKING_CONFIG_FILE=/path/to/ov.conf
openviking-server --config /path/to/ov.conf
```

服務端啟動時讀取配置。修改模型、檢索、儲存或 `server` 配置後，需要重啟服務；重啟後建議執行 `openviking-server doctor`。

通過單 worker 的 `openviking-server` 啟動時，Studio 的「服務端配置」頁面提供「儲存並重啟」。重啟能力和例項標識複用現有 ROOT 配置讀取介面（`GET /api/v1/admin/configuration?source=file`）返回；只有 ROOT 可以請求重啟（`POST /api/v1/admin/restart`，請求體為 `{"revision":"<已儲存檔案的版本>"}`）。服務校驗當前檔案和版本後返回 HTTP 202，等待現有請求結束，停止其管理的 Bot，再使用原直譯器、啟動引數、環境變數和工作目錄替換當前程序。頁面確認新的服務例項恢復後才顯示成功。單獨點選「儲存配置」仍只儲存檔案。

多 worker 或嵌入式 ASGI 啟動不支援頁面重啟，需要通過部署平臺重啟。配置通過校驗後，外部依賴仍可能導致啟動失敗。如果修改了地址、埠或 ROOT 憑證，請更新 Studio 連線設定。帳號和叢集覆蓋配置仍優先於檔案預設配置。

配置含環境變數引用時，Studio 表單只讀，請使用檔案模式編輯原文。帶引號或未帶引號的引用、轉義和格式按提交內容儲存。Windows `%VAR%` 引用和美元/百分號字面值（包括 `\u0024`、`\u0025`）也使用檔案模式，避免表單序列化引入新的引用。

## 配置結構

下面只展示常用頂層分組，不是可直接執行的完整配置。首次啟動可從本頁的[最小示例](#最小示例)開始，填寫實際模型與憑據；後續示例中的片段應合併到同一個 `ov.conf`。

```json
{
  "embedding": {},
  "vlm": {},
  "query_planner": {},
  "rerank": {},
  "rules": {},
  "retrieval": {},
  "storage": {},
  "server": {},
  "memory": {},
  "parsers": {},
  "encryption": {},
  "log": {},
  "telemetry": {}
}
```

未配置的可選模組使用預設值。`ov.conf` 及帳戶配置會忽略未知欄位（`gateway` 部分除外），相容舊版本遺留配置；已知欄位仍校驗型別和取值。欄位名拼寫錯誤也會被忽略，但服務端會輸出 WARNING，逐項列出未被採用的欄位。

## 頂層配置

| 配置項 | 型別 / 可選值 | 預設值 | 作用 |
|---|---|---|---|
| `default_account` | string | `"default"` | Service context 使用的預設帳號 |
| `default_user` | string | `"default"` | Service context 使用的預設使用者 |
| `embedding` | object | 內建本地 Dense 模型 | 向量化模型和稀疏/混合檢索配置；預設使用 `local` / `bge-small-zh-v1.5-f16` |
| `vlm` | object | 空配置 | 內容理解、摘要和記憶抽取使用的模型；使用相關能力前需要配置可用模型 |
| `query_planner` | object / `null` | `null` | 檢索意圖分析和召回改寫使用的模型。未配置或為空時回退到 `vlm`；`auto` 模式的召回改寫要求配置叢集級 `query_planner`，或帳戶級 `query_planner` / `vlm` 覆蓋項 |
| `rerank` | object | disabled | 檢索結果重排模型 |
| `rules` | object | 空配置 | 規則編譯和適用性判斷使用的可選專用模型 |
| `retrieval` | object | 見下表 | 檢索排序和意圖分析策略 |
| `storage` | object | 本地儲存 | 工作目錄、檔案系統和向量資料庫 |
| `queue_workers` | object | 見下表 | QueueFS 消費 worker 的執行時併發配置 |
| `server` | object | 本地開發模式 | HTTP 服務、鑑權、上傳和可觀測性 |
| `memory` | object | 見下表 | 會話提交後的記憶與技能抽取 |
| `parsers` | object | 各解析器預設值 | PDF、程式碼、圖片、音影片等解析行為 |
| `semantic` | object | 內建預設值 | abstract 和 overview 的生成限制 |
| `parser_api` | object | disabled | 第三方文件解析 API |
| `compile_api` | object | built-in defaults | 伺服器內 Compile 流水線併發配置 |
| `connector` | object | disabled | 外部 Connector 資料匯入服務 |
| `encryption` | object | disabled | 文件和敏感字段加密 |
| `git` | object | local | 版本管理後端，可使用 `local`、`s3` 或 `agfs`（S3 分層儲存時的預設） |
| `log` | object | 控制台日誌 | 日誌級別、格式和檔案輸出 |
| `telemetry` | object | disabled | OpenTelemetry trace 上報 |
| `oauth` | object | disabled | MCP OAuth 2.1 配置 |
| `gateway` | object | disabled | OpenViking 閘道器配置，閘道器為使用 API Key 的模型客戶端補充 OpenViking 記憶。這一部分的未知欄位會直接報錯，見[配置參考](../gateway/13-configuration.md#configuration-reference) |
| `prompts` | object | 內建模板 | 自定義 Prompt 模板目錄 |
| `ingest` | object | 內建預設值 | 會話日誌匯入配置 |
| `output_language_override` | string | `""` | 強制摘要和記憶輸出語言，僅接受 `en` 或 `zh-TW`；空值表示自動識別：中文內容 → `zh-TW`，其他語言或無法識別 → `en` |
| `allow_private_networks` | boolean | `false` | 是否允許抓取內網或私有地址資源 |

`auto_generate_l0`、`auto_generate_l1`、`default_search_mode` 和 `default_search_limit` 是已棄用的相容欄位。舊配置檔案仍可載入這些欄位，但它們不會影響執行時行為。

## 模型配置

API 型 `embedding`、`vlm`、`query_planner` 和 `rerank` 配置會複用部分欄位名，但各模組使用獨立 schema。請只使用下表中對應模組支援的欄位。

```json
{
  "embedding": {
    "dense": {
      "provider": "volcengine",
      "model": "doubao-embedding-vision-251215",
      "api_base": "https://ark.cn-beijing.volces.com/api/v3",
      "api_key": "<your-ark-api-key>",
      "dimension": 1024,
      "input": "multimodal"
    }
  },
  "vlm": {
    "provider": "volcengine",
    "model": "doubao-seed-2-0-code-preview-260215",
    "api_base": "https://ark.cn-beijing.volces.com/api/v3",
    "api_key": "<your-ark-api-key>",
    "temperature": 0,
    "max_retries": 3,
    "thinking": false
  },
  "query_planner": {
    "provider": "volcengine",
    "model": "doubao-seed-2-0-code-preview-260215",
    "api_base": "https://ark.cn-beijing.volces.com/api/v3",
    "api_key": "<your-ark-api-key>",
    "thinking": false
  },
  "rerank": {
    "provider": "vikingdb",
    "ak": "<your-volcengine-ak>",
    "sk": "<your-volcengine-sk>",
    "host": "api-vikingdb.vikingdb.cn-beijing.volces.com",
    "model_name": "doubao-seed-rerank",
    "model_version": "251028",
    "threshold": 0.1,
    "max_input_tokens": 0
  }
}
```

| 欄位 / 路徑 | 適用模組 | 作用 |
|---|---|---|
| `provider`、`model`、`api_base`、`api_key` | Embedding、VLM、Query Planner、Rerank | 模型服務、地址和憑證 |
| `api_version` | Embedding、VLM、Query Planner | Azure 等服務的 API 版本 |
| `extra_headers` | Embedding、VLM、Query Planner、Rerank | 附加請求頭 |
| `extra_request_body` | VLM、Query Planner | 附加的 Completion 請求引數 |
| `extra_body` | `embedding.dense` / `sparse` / `hybrid` | 附加的 Embedding 請求引數 |
| `timeout` | VLM、Query Planner、Rerank | 單次請求超時，單位為秒 |
| `embedding.max_retries`、`vlm.max_retries`、`query_planner.max_retries` | Embedding、VLM、Query Planner | 請求失敗重試次數；Rerank 沒有 `max_retries` 欄位 |

### `embedding.dense`

| 欄位 | 型別 / 可選值 | 作用 |
|---|---|---|
| `provider` | `openai`、`volcengine`、`azure`、`ollama`、`local` 等 | Dense Embedding 服務 |
| `dimension` | integer，`> 0` | 向量維度，必須與模型輸出及已有集合一致 |
| `input` | `"text"` / `"multimodal"` | 輸入型別 |
| `encoding_format` | `"float"` / `"base64"` | OpenAI 相容介面的向量編碼格式 |

更換模型或 `dimension` 可能與已有向量集合不相容，需要遷移或重建索引。

### `rules`

Compiled Rule 的可選模型與生命週期配置：

```json
{
  "rules": {
    "jev_rule_matcher": {
      "provider": "typesafe",
      "api_key": "${JEV_API_KEY}"
    },
    "compiler": {
      "provider": "openai",
      "model": "gpt-4o"
    },
    "compiler_context_window": 0
  }
}
```

| 欄位 | 型別 / 可選值 | 預設值 | 作用 |
|---|---|---|---|
| `jev_rule_matcher` | Jev Noul 配置 / `null` | `null` | Scenario 過濾和 Rule 適用性判斷使用的 Jev Noul 模型 |
| `compiler` | VLM 配置 / `null` | `null` | 專用 Rule Compiler |
| `compiler_context_window` | `0` 或 integer `>= 2048` | `0` | Compiler 上下文視窗；`0` 表示自動探測並使用保守回退值 |
| `scenario_irrelevance_threshold` | number，`0.5`-`1.0` | `0.9` | Scenario 無關機率達到該值時跳過 |
| `archived_retention_days` | integer，`>= 1` | `30` | archived Rule 的物理刪除保留天數 |
| `archived_cleanup_interval_seconds` | integer，`>= 60` | `2592000` | archived Rule 清理週期 |
| `archived_cleanup_enabled` | boolean | `true` | 是否定期清理 archived Rule |

Rule 編譯始終以 `thinking=true` 呼叫專用 Compiler 或回退的帳戶預設 VLM，
並覆蓋其配置預設值。請使用支援思考模式的模型，否則編譯可能失敗。

#### `rules.jev_rule_matcher`

該配置用於 Scenario 過濾和 Rule 適用性的獨立 Jev System One 判斷，不用於檢索結果重排。

| 欄位 | 型別 / 可選值 | 預設值 | 作用 |
|---|---|---|---|
| `provider` | `typesafe`、`vercel`、`openrouter`、`custom` | `typesafe` | 選擇 endpoint 和 model 預設值 |
| `api_key` | string | 必填 | 所選 provider 的 API Key |
| `api_base` | URL / `null` | provider 預設值 | 完整的 System One 請求 URL；顯式配置的值會原樣使用 |
| `model` | string / `null` | provider 預設值 | 模型名或 Endpoint ID；`custom` 必填 |
| `timeout` | number | `30` | HTTP 請求超時秒數 |
| `extra_headers` | object / `null` | `null` | 附加 HTTP 請求頭 |
| `log_payloads` | boolean | `false` | 是否記錄完整請求和響應；日誌可能包含任務與 Rule 內容 |

| Provider | 預設請求 URL | 預設 model | 說明 |
|---|---|---|---|
| `typesafe` | `https://api.typesafe.ai/v1/systemone` | `jev-latest` | TypeSafe 直連 |
| `vercel` | `https://ai-gateway.vercel.sh/typesafe/v1/systemone` | `typesafe-ai/jev` | Vercel AI Gateway 的 TypeSafe 相容 API |
| `openrouter` | `https://openrouter.ai/api/v1/systemone` | `jev-latest` | OpenRouter System One API |
| `custom` | 無 | 無 | 必須同時配置 `api_base` 和 `model` |

`api_base` 和 `model` 可分別覆蓋 provider 預設值。顯式配置的 `api_base` 是完整
POST URL，任何 provider（包括 `custom`）都不會修改它或追加字尾。
`extra_headers` 會擴充 provider 請求頭，也可以覆蓋預設請求頭。Rule 匹配固定使用
獨立 Noul 判斷，因此不再包含 `mode`、`threshold` 或 `max_input_tokens` 配置。
Scenario 過濾閾值由 `rules.scenario_irrelevance_threshold` 配置；
Rule 適用性使用 Rule 搜尋請求中的 `rule_probability_threshold`（預設 `0.65`）。

Rule 狀態為 `active`、`paused`、`archived`。`PAUSE` 暫停檢索但不設定清理期限；
`ARCHIVE` 從 `archived_at` 開始計算保留期；`RESTORE` 將 paused Rule 恢復為
active。編譯候選只包含 active 和 paused Rule；archived Rule 視為邏輯刪除，不是
編譯候選，也無法通過 Rule 編譯恢復。`ARCHIVE` 必須由使用者指令明確表達刪除、丟棄
或移入回收站；不包含刪除語義的停用請求使用 `PAUSE`。

Rule 按 Scenario 直接存放在 `memories/rules/<scenario_id>/`：`abstract.md`
儲存場景元資訊，`<atomic_id>.md` 儲存規則。儲存格式見
[規則（Beta）](../concepts/17-rule-scenarios.md)。

`jev_rule_matcher` 未配置、不可用、呼叫失敗或返回無效結果時，Scenario 和 Rule 判斷
直接放行，不呼叫 VLM。Scenario 診斷記錄 `decision=pass`；Rule 返回 `judge=pass`
和 warning，以 `1.0` 作為通過閾值的放行分數，
該值不是模型評估的適用機率。Agent 仍需根據具體事實核驗適用條件和例外。
規則編譯從 `compiler` 回退到帳戶預設 VLM。原 `rule_matcher` 配置已移除，不再讀取。

Rule 的 `applies_when` 可以為空，預設空值；為空時表示任何情況都適用，除非
`exception` 條件成立。沒有適用條件和例外的候選 Rule 適用機率直接取 `1.0`。
Compiler 會優先忠實提煉原文中的物件、操作、前提和場景，儘量生成非空且可判定的
`applies_when`，不得編造條件或丟棄原文已有的限制。空條件不表示未知或不適用。

### `rerank`

| 欄位 | 型別 / 可選值 | 預設值 | 作用 |
|---|---|---|---|
| `provider` | `vikingdb`、`cohere`、`openai`、`litellm`、`jev` / `null` | `null` | Rerank 服務型別；省略時根據憑證欄位推斷 |
| `model` | string / `null` | `null` | OpenAI 相容、LiteLLM 或 Jev Rerank 模型 |
| `mode` | `noul`、`choice` 或 `null` | `noul` | Jev Rerank 模式；`null` 同樣使用 `noul` |
| `threshold` | number | `0.1` | 判定結果相關的最低 Rerank 分數；只過濾模型產出的 Rerank 分數，不過濾向量分數；請求中的 `score_threshold` 優先 |
| `max_input_tokens` | integer；`0` 或 `>= 128` | `0` | 每個 query-document pair 的最大估算 token；`0` 表示不截斷 |
| `log_payloads` | boolean | `false` | 記錄完整 rerank 請求和響應；日誌可能包含 query 和文件內容 |

Rerank 沒有單獨的 `enabled` 欄位；配置了對應 provider 所需的憑證後才會啟用。

`jev` 通過現有 `api_base` 和 `model` 欄位同時支援 TypeSafe 直連（`https://api.typesafe.ai/v1/systemone`，模型 `jev-latest`）和 Vercel AI Gateway 的 TypeSafe 相容端點（`https://ai-gateway.vercel.sh/typesafe/v1/systemone`，模型 `typesafe-ai/jev`），兩者協議相同。Rerank 的 `api_base` 可以是服務根地址或完整 System One URL；缺少 `/v1/systemone` 時會自動追加。預設 `noul` 模式獨立評估每個候選；可選的 `choice` 模式橫向比較所有候選並返回相對機率，使用時應將 `threshold` 設為 `0`。顯式指定 `provider` 時必須提供該 provider 所需的憑證：`vikingdb` 需要 `ak` 和 `sk`，`cohere` 和 `jev` 需要 `api_key`，`openai` 需要 `api_key` 和 `api_base`，`litellm` 需要 `model`。憑證不全的配置在載入時即被拒絕。

## 檢索配置

```json
{
  "retrieval": {
    "enable_intent": true,
    "apply_rerank_to_context": false
  }
}
```

### `retrieval`

| 欄位 | 型別 / 可選值 | 預設值 | 作用 |
|---|---|---|---|
| `enable_intent` | boolean | `true` | 有 `session_id` 時是否進行意圖分析和查詢規劃 |
| `apply_rerank_to_context` | boolean | `false` | 是否用已配置的 `rerank` 模型重排 `search(mode="context")` 的候選 |

Search 和 Find 請求的預設 `limit` 為 `10`，可以在每次 API 或 SDK 請求中覆蓋。`retrieval.enable_intent` 控制帶 Session 的 Search 是否執行 LLM 查詢規劃；只有配置了可用的 `rerank` provider 時才會執行結果重排。Context 模式使用 Find 的向量分數召回；開啟 `retrieval.apply_rerank_to_context` 且 `rerank` 可用時，會在配額和 token 預算之前，用原始查詢及其擴充查詢對合並後的候選統一重排一次，每個請求多一次 Rerank 呼叫。

## 儲存配置

```json
{
  "storage": {
    "workspace": "./data",
    "skip_process_lock": false,
    "agfs": {
      "backend": "local"
    },
    "vectordb": {
      "backend": "local"
    },
    "parse_output": {
      "mode": "agfs"
    }
  },
  "parsers": {
    "download_temp_dir": "/data/openviking/parser-tmp"
  }
}
```

### `storage`

| 欄位 | 型別 / 常用值 | 預設值 | 作用 |
|---|---|---|---|
| `workspace` | path | `"./data"` | OpenViking 工作目錄 |
| `agfs.backend` | `local`、`memory`、`s3` | `local` | 檔案與後設資料儲存後端 |
| `agfs.pathlock.provider` | `filesystem`、`memory`、`sqlite`、`cache` | `filesystem` | 路徑鎖儲存 |
| `agfs.pathlock.sqlite_path` | 本地檔案絕對路徑 | 使用 `sqlite` 時為 `{workspace}/_system/pathlock/pathlock.db` | SQLite 共享鎖資料庫，可顯式覆蓋 |
| `vectordb.backend` | `local`、`cuvs`、`http`、`opengauss`、`elasticsearch` | `local` | 向量資料庫後端 |
| `vectordb.dimension` | integer | 跟隨 Embedding | 向量集合維度 |
| `parse_output.mode` | `agfs`、`local` | `agfs` | parser 中間產物的儲存後端 |
| `parse_output.local_root` | 路徑或 `null` | 系統臨時目錄 | local parser artifact 的根目錄 |
| `skip_process_lock` | boolean | `false` | 是否跳過 workspace 程序鎖；僅在明確接受併發寫風險時啟用 |
| `staged_source_ttl_seconds` | integer，0–15552000（180 天） | `604800`（7 天） | 留在 `viking://temp` 的 add-resource 暫存來源超過此秒數即被清除（使用者暫存新來源時順帶檢查，每位使用者最多每小時一次；該使用者仍在執行的任務所用的暫存不會被清除）；`0` 表示停用 |

同機本地磁碟上的路徑鎖可通過 SQLite 避免遞迴掃描業務目錄。將 `storage.agfs.pathlock` 設定為
`{"provider":"sqlite"}`。資料庫預設位於
`{storage.workspace}/_system/pathlock/pathlock.db`，初始化執行時 binding 時
根據最終 workspace 解析為絕對路徑。顯式指定的絕對路徑 `sqlite_path` 優先，
資料庫父目錄會自動建立。
直接通過 `RAGFSBindingClient(config_path=..., config={"service_name": ...})` 構造時，
省略 `sqlite_path` 或將其設為 `null` 也會使用上述預設路徑。
所有參與程序必須訪問同一個實際的本地資料庫檔案，並使用相同的頂層 `service_name` 和鎖過期配置。
同一主機上的容器必須共享該本地檔案；不同容器檔案系統中相同的路徑字串指向獨立資料庫，
不能互相協調路徑鎖。
SQLite 是鎖狀態的唯一儲存，通過路徑索引查詢，並在事務中原子檢查及獲取 Exact/Tree 鎖；
資料庫阻塞操作在非同步執行器之外執行。
SQLite 每次嘗試對瞬時資料庫寫競爭最多等待 100 毫秒，即使邏輯鎖等待超時為零也會執行該等待。
僅 Busy 會在 provider 內重試，最多嘗試 3 次，重試前分別退避 1、4 毫秒；
資料庫等待可累計約 300 毫秒，另加 5 毫秒退避及執行、排程開銷。
重試耗盡仍向 manager 返回 Busy；邏輯鎖 Conflict 不重試。
WAL 使用 `synchronous=FULL` 保證崩潰後已提交鎖記錄的永續性，
代價是比 `NORMAL` 更多的同步 I/O。
租約心跳在一次 SQLite 事務中批次重新整理所屬路徑，大租約按有限大小分批執行。
`stale_locks_removed` 包含 SQLite/Redis 原子加鎖事務實際回收的鎖數量，
失敗並回滾的事務不會增加計數。

SQLite 加鎖會完整刪除其他 owner 持有、已過期且與本次請求衝突的記錄：
目標路徑、祖先 Tree 鎖，以及請求 Tree 鎖時的全部後代鎖。
清理與加鎖在同一事務內完成，舊 owner 在接管後無法通過續租恢復這些記錄。
全域增量清理每次加鎖最多刪除 256 條記錄；衝突記錄清理不受此上限限制，
因此過期子樹較大時仍會增加事務開銷。

不能將資料庫放在 EFS、NFS 或 SMB 上。SQLite WAL 要求參與者位於同一主機，不支援網路檔案系統；
頻繁更新鎖記錄還會增加同步 I/O。如果 `storage.workspace` 位於 EFS，預設資料庫路徑也會落在 EFS。
將資料庫改到各容器本地磁碟會形成獨立的鎖狀態，無法協調多個副本。

多個容器或主機共享 EFS 時，使用共享 Redis PathLock：
設定 `storage.agfs.pathlock.provider="cache"` 和頂層 `cache.provider="redis"`。
所有副本必須連線同一個 Redis 部署，並使用相同的頂層 `service_name` 和鎖過期配置。
參見[共享 Redis 配置示例](../guides/01-configuration.md)。
共享 QueueFS 也需選擇適合該部署的後端，例如 `storage.agfs.queuefs.backend="cache"`；
僅修改 PathLock 不會改變預設的 SQLite 佇列後端。

切換 provider 前需停止全部參與程序，
SQLite 與 filesystem 鎖檔案不共享協議。程序執行期間不能刪除資料庫及其 WAL/SHM 檔案。
崩潰程序的鎖在 `lock_expire_secs`（預設 30 秒）後可被接管。
此配置不會改變 workspace 程序鎖或其他後端的併發限制。

遠端儲存後端還需要配置 endpoint、bucket/collection、鑑權和超時等欄位。完整後端示例見[配置指南](../guides/01-configuration.md#storage)。

`parse_output.mode=local` 可避免把 parser 中間產物寫入共享 AGFS。當前 worker
必須在下游任務入隊前把所需位元組提交到正式資源樹。產物會在內容提交後清理；
請為 `local_root` 預留足夠空間以容納併發匯入。

### `parsers`

| 欄位 | 型別 / 常用值 | 預設值 | 作用 |
|---|---|---|---|
| `download_temp_dir` | 路徑或 `null` | 系統臨時目錄 | 內建 parser 下載檔案、Git checkout 和壓縮包解壓使用的臨時目錄 |

配置後，parser 會在該目錄下建立帶有 `ov_git_`、`ov_zip_` 等字首的臨時目錄；未配置時繼續使用系統臨時目錄。

## 佇列 Worker 配置

### `queue_workers.external_parse`

| 欄位 | 型別 | 預設值 | 說明 |
|---|---|---:|---|
| `max_concurrent` | integer | `4` | 同時消費的完整 ExternalParse 作業數，必須大於 `0`；修改後需重啟服務 |

該配置控制佇列作業併發，不等同於 `vlm.media.max_concurrent` 的音影片 VLM 呼叫併發，也不限制 Understanding API 的單獨 HTTP 請求數。

### `queue_workers.add_resource`

| 欄位 | 型別 | 預設值 | 說明 |
|---|---|---:|---|
| `max_concurrent` | integer | `4` | 同時消費的完整 AddResource 作業數，必須大於 `0`；修改後需重啟服務 |
| `file_operation_concurrency` | integer | `16` | 單個 AddResource 作業內檔案級提交和 fallback 比較操作的最大併發數，必須大於 `0`；修改後需重啟服務 |
| `file_vectorization_concurrency` | integer | `8` | 當目錄 AddResource 使用 `processing_mode="vectors_only"` 時，單個作業內併發讀取、準備併入隊的檔案數，必須大於 `0`；超過內部安全上限 `64` 的值會被截斷；修改後需重啟服務 |

`max_concurrent` 控制相互獨立的 AddResource 作業併發，`file_operation_concurrency` 控制單個 AddResource 作業內檔案提交和 fallback 比較操作的併發，`file_vectorization_concurrency` 控制單個 vectors-only 目錄作業內的檔案併發。

### `queue_workers.reindex`

| 欄位 | 型別 | 預設值 | 說明 |
|---|---|---:|---|
| `max_concurrent` | integer | `4` | 同時消費的完整 Reindex root 作業數，必須大於 `0`；修改後需重啟服務 |

該配置限制相互獨立的非同步 reindex 請求併發。URI 範圍重疊的請求仍由 path lock 保護；VLM 和 embedding 仍分別遵守各自的併發限制。

### `queue_workers.session_commit`

| 欄位 | 型別 | 預設值 | 說明 |
|---|---|---:|---|
| `max_concurrent` | integer | `8` | 同時消費的 SessionCommit 作業數，必須大於 `0`；修改後需重啟服務 |

### `queue_workers.external_task`

| 欄位 | 型別 | 預設值 | 說明 |
|---|---|---:|---|
| `max_concurrent` | integer | `10` | 同時消費的外部非同步任務數，必須大於 `0`；修改後需重啟服務 |

## Compile API 配置

| 欄位 | 型別 | 預設值 | 說明 |
|---|---|---:|---|
| `base_url` | string | `""` | 外部服務地址，必須包含 `http://` 或 `https://`；非空即啟用外部 Compile |
| `gateway_token` | string | `""` | OV 呼叫 Compile Gateway 使用的可選服務憑證 |
| `http_timeout_seconds` | number | `10` | 單次 HTTP 請求超時 |
| `poll_interval_ms` | integer | `30000` | 外部任務狀態輪詢間隔 |

配置 `base_url` 後，OV 通過 `X-API-Key` 傳遞當前使用者的 OV API Key；僅在配置 `gateway_token` 時傳送 `X-Gateway-Token`。

## Reindex 配置

### `reindex`

| 欄位 | 型別 | 預設值 | 說明 |
|---|---|---:|---|
| `file_vectorization_concurrency` | integer | `8` | 單個 resource/skill reindex 任務內併發讀取、計算指紋和準備檔案的數量，必須大於 `0`；超過內部安全上限 `64` 的值會被截斷；修改後需重啟服務 |

## HTTP 服務配置

```json
{
  "server": {
    "host": "127.0.0.1",
    "port": 1933,
    "workers": 1,
    "executor_threads": 0,
    "auth_mode": "dev",
    "cors_origins": ["http://localhost:5173"],
    "profile_enabled": false,
    "temp_upload": {
      "default_mode": "local"
    }
  }
}
```

### `server`

| 欄位 | 型別 / 可選值 | 預設值 | 作用 |
|---|---|---|---|
| `host` | IP / hostname | `"127.0.0.1"` | HTTP 監聽地址 |
| `port` | integer | `1933` | HTTP 監聽埠 |
| `workers` | integer | `1` | 服務程序數量 |
| `executor_threads` | 非負整數 | `0` | 每個服務程序的 asyncio 預設 executor 最大執行緒數；`0` 表示沿用 Python 預設策略 |
| `timeout_keep_alive` | integer（秒） | `5` | 空閒 HTTP keep-alive 超時；應調大到超過上游空閒連線壽命 |
| `ready_probe_timeout_seconds` | number（秒） | `5.0` | `/ready` 每項儲存探測（檔案系統、向量資料庫）的最長等待時間，逾時回傳 `503`；編排器探針逾時（如 Kubernetes `timeoutSeconds`）應大於此值 |
| `auth_mode` | `dev`、`api_key`、`trusted` / `null` | `null` | 鑑權模式；空值根據 `root_api_key` 自動判斷 |
| `root_api_key` | string / `null` | `null` | Root API Key；配置後預設啟用 `api_key` 模式 |
| `cors_origins` | string[] | `["*"]` | 允許的跨域來源 |
| `profile_enabled` | boolean | `false` | 是否允許請求返回效能 profile |
| `with_bot` | boolean | `false` | 是否啟用 VikingBot API 代理 |
| `bot_api_url` | URL | `http://localhost:18790` | VikingBot OpenAPI 地址 |
| `public_base_url` | URL / `null` | `null` | 外部訪問使用的服務基準地址 |
| `upload_signed_ttl_seconds` | integer | `600` | 簽名上傳、下載 URL 有效期 |
| `temp_upload.default_mode` | `"local"` / `"shared"` | `"local"` | 臨時上傳儲存模式 |

### 檔案加密與 API Key 雜湊

檔案加密和 API Key 雜湊在頂層 `encryption` 中配置，不屬於 `server`：

```json
{
  "encryption": {
    "enabled": false,
    "api_key_hashing": {
      "enabled": false
    }
  }
}
```

| 欄位 | 型別 / 可選值 | 預設值 | 作用 |
|---|---|---|---|
| `encryption.enabled` | boolean | `false` | 是否啟用檔案級 AES 加密 |
| `encryption.api_key_hashing.enabled` | boolean | `false` | 是否使用 Argon2id 保存 API Key |

Provider 和金鑰管理配置見[加密指南](../guides/08-encryption.md)。

### 鑑權模式

| 值 | 使用場景 |
|---|---|
| `dev` | 僅監聽本機地址的開發環境，不要求 API Key |
| `api_key` | 服務端校驗 root/user/admin key |
| `trusted` | 由受信任網關注入 account/user 身份 |

## 記憶配置

```json
{
  "memory": {
    "custom_templates_dir": "",
    "experimental_memory_switch": false,
    "eager_prefetch": true,
    "prefetch_search_topn": 5,
    "extraction_enabled": true,
    "session_skill_extraction_enabled": false,
    "link_enabled": false
  }
}
```

### `memory`

| 欄位 | 型別 / 可選值 | 預設值 | 作用 |
|---|---|---|---|
| `custom_templates_dir` | path | `""` | 自定義記憶模板目錄；同名 `memory_type` 覆蓋已載入模板 |
| `experimental_memory_switch` | boolean | `false` | 是否啟用實驗性記憶模板 |
| `eager_prefetch` | boolean | `true` | 是否在抽取前預取並讀取記憶內容 |
| `prefetch_search_topn` | integer，`>= 1` | `5` | 預取時讀取的檢索結果數量 |
| `extraction_enabled` | boolean | `true` | session commit 時是否抽取長期記憶 |
| `session_skill_extraction_enabled` | boolean | `false` | 是否同時抽取可複用 Skill |
| `link_enabled` | boolean | `false` | 是否生成和解析記憶連結 |

自動提交還需要單獨設定策略：記憶抽取開關不會讓會話自動提交。詳見[配置指南](../guides/01-configuration.md)的 `memory.session_auto_commit` 和[會話 API](../api/05-sessions.md)。模板目錄的載入順序和生效方式見 [Prompt 指南](../guides/10-prompt-guide.md)。

## 解析器配置

解析器放在 `parsers` 下：

```json
{
  "parsers": {
    "pdf": {},
    "code": {
      "code_summary_mode": "ast",
      "extract_functions": true,
      "extract_classes": true,
      "max_token_limit": 50000
    },
    "image": {},
    "audio": {},
    "video": {},
    "markdown": {},
    "anydoc": {
      "enabled": true
    },
    "html": {},
    "text": {},
    "directory": {
      "preserve_structure": true,
      "max_files": null,
      "max_depth": 10,
      "max_concurrent": 4
    },
    "webfeed": {}
  }
}
```

`parsers.directory.max_files` 預設是 `null`，表示不限檔案數；
設為正整數可限制單次目錄匯入的檔案數。

`parsers.directory.max_concurrent` 由服務事件迴圈中的所有目錄匯入共享。預設值為
`4` 時，單個目錄可以併發執行 4 個 Understanding 任務；多個目錄同時匯入時，合計仍最多
執行 4 個。

啟用 Understanding 目錄路由時，`max_files` 和 `max_depth` 才約束目錄匯入。每次
`DirectoryParser` 掃描會在提交該層 Understanding 請求前獨立應用限制；巢狀 ZIP 會啟動
新的目錄掃描，不與外層共享檔案數量和深度預算。關閉 Understanding 時，OpenViking
原生目錄解析不應用這兩個限制。

客戶端匯入本地目錄時，完整目錄 ZIP 受 `/resources/temp_upload` 上傳大小限制。ZIP
解壓後，`DirectoryParser` 不再設定統一的單檔案位元組限制；每個入選檔案遵循對應內建
Parser 或 Understanding API 後端自身的限制和上傳行為。

| 配置項 | 作用 |
|---|---|
| `pdf` | PDF 文本、圖片和版面解析 |
| `code` | 程式碼倉庫檔案型別、忽略規則和安全限制 |
| `image` | 圖片理解和 OCR |
| `audio`、`video` | 音影片內容解析 |
| `markdown`、`html`、`text` | 文本文件分段 |
| `anydoc` | Office 和 EPUB 轉換；`enabled=false` 時拒絕這些格式 |
| `directory` | 目錄掃描和忽略規則 |
| `webfeed` | Sitemap、RSS 和 Atom 匯入 |

各模型 provider、解析器、儲存後端和加密後端包含較多專用欄位，完整欄位表和配置示例見[配置指南](../guides/01-configuration.md)。

## 最小示例

```json
{
  "embedding": {
    "dense": {
      "provider": "volcengine",
      "model": "doubao-embedding-vision-251215",
      "api_base": "https://ark.cn-beijing.volces.com/api/v3",
      "api_key": "<your-ark-api-key>",
      "dimension": 1024,
      "input": "multimodal"
    }
  },
  "vlm": {
    "provider": "volcengine",
    "model": "doubao-seed-2-0-code-preview-260215",
    "api_base": "https://ark.cn-beijing.volces.com/api/v3",
    "api_key": "<your-ark-api-key>",
    "thinking": false
  },
  "storage": {
    "workspace": "./data"
  },
  "server": {
    "host": "127.0.0.1",
    "port": 1933
  }
}
```
