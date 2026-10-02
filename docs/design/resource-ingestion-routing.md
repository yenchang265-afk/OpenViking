# 新增資源後的解析路由

本文描述當前 `add_resource` 從收到資源到落盤、建索引的真實執行鏈。重點回答四個問題：入口在哪裡分流、資源型別在哪裡確定、Understanding 與 Connector 分別做什麼，以及 `wait` 到底等待什麼。

## 先記住五條規則

1. 對外只有一個資源新增入口：`ResourceService.add_resource`。SDK、HTTP API、MCP 最終都應呼叫它；Worker 不再拿後臺任務冒充一次新的資源新增請求。
2. Connector 是一條獨立的端到端匯入鏈；Understanding 只是標準鏈裡的一個 Parser 後端。
3. 普通檔案只做一次 Parser 選擇。選擇依據是 Accessor 獲取資源後凍結的 `resolved_extension`，不是臨時檔名，也不會在佇列消費者裡重新猜；Understanding 可直接接收的原始 URL 是一個顯式例外，可在 Accessor 前按配置直達 Understanding。
4. 目錄、網站目錄以及內部 Parser 遍歷出的子檔案不逐個呼叫 Understanding，統一留在內建 Parser 鏈內處理。
5. Watch 是一次新的來源重新整理，會重新走提交分流，但不會建立、取消或覆蓋自身的 Watch 任務。

## 總流程

```text
SDK / HTTP API / MCP
        |
        v
ResourceService.add_resource                  對外入口
        |
        v
ResourceService._submit_resource_ingestion    階段一：對新請求選擇執行方式
        |
        +-- Connector 命中且引數受支援 ------> Connector doc/add
        |                                         |
        |                                         +--> 輪詢 Connector task/info
        |                                         +--> Connector 自己解析並寫入資源
        |
        +-- Git && wait=false ----------------> 預檢 + AddResource 佇列 --> 返回 task_id
        |
        +-- HTTP 服務遠端資源 && wait=false && Understanding 已啟用
        |       |
        |       +-- 原始 URL 可直達 -----------> 提交 Understanding --> ExternalParse 佇列
        |       |                                                        |
        |       |                                                        +--> 返回 task_id --> Worker
        |       |
        |       +-- 需要先確定本地型別 --------> Accessor 下載並識別
        |               |
        |               +-- 命中 Understanding --> 上傳同一檔案 --> ExternalParse 佇列
        |               |                                             |
        |               |                                             +--> 返回 task_id --> Worker
        |               |
        |               +-- 未命中 ------------> 複用 LocalResource，進入當前請求標準鏈
        |
        +-- 其餘場景（包括所有 wait=true） -----> _execute_resource_ingestion

_execute_resource_ingestion                    階段二：執行標準鏈
        |
        v
ResourceProcessor.process_resource
        |
        v
UnifiedResourceProcessor
        |
        +-- 已有 understanding_response_id ----> ParserRouter --> Understanding 恢復任務
        |
        +-- 原始 URL 可直達 Understanding -----> ParserRouter --> Understanding 提交併等待
        |
        +-- 原始文本 --------------------------> 內建 ParserRegistry
        |
        +-- 路徑 / URL --> AccessorRegistry.access（選擇資料訪問器）
                                  |
                                  v
                              LocalResource
                                  |
                                  +-- 目錄 --> DirectoryParser（內建）
                                  |
                                  +-- 檔案 --> ParserRouter.parse（選擇 Parser，只選一次）
                                                  |
                                                  +-- 內建 ParserRegistry
                                                  +-- Understanding 上傳並等待
        |
        v
     ParseResult --> TreeBuilder 落盤
        |
        v
階段三：返回策略
        |
        +-- wait=true  --> 繼續等待摘要 / 語義佇列 / 向量索引後返回
        |
        +-- wait=false --> 普通標準鏈落盤後進入 AddResource 佇列並返回

後臺佇列 Worker
        |
        +-- source job -----------------------> _execute_resource_ingestion(wait=true)
        |                                      使用訊息中凍結的 backend / response_id / extension
        |
        +-- prepared job ---------------------> finish_prepared_resource
        |
        +-- 不再呼叫 add_resource，也不再重做 Connector / Git 頂層分類

WatchScheduler
        |
        +-- refresh_resource -----------------> _submit_resource_ingestion(manage_watch=false)
                                               重新獲取和解析來源，但不修改 Watch 任務
```

Understanding 不受 `wait=false` 限制。`wait=true` 在當前請求內完成 Understanding 提交、輪詢、解析和 TreeBuilder，並繼續等待後續佇列；`wait=false` 的遠端服務路徑會先提交 Understanding、將 `response_id` 入隊，再由 Worker 恢復任務。

分類發生的位置：

| 分類內容 | 程式碼位置 | 輸出 |
|---|---|---|
| Connector、非同步 Git、標準執行鏈 | `ResourceService._submit_resource_ingestion` | 選定新請求的頂層執行方式 |
| 非同步 Understanding 或當前請求內執行 | `ResourceService._execute_resource_ingestion` | 根據 `wait`、配置和已識別型別決定提交還是同步執行 |
| Git、Feed、HTTP、本地文件 | `AccessorRegistry.access` | `LocalResource` |
| Understanding 能否直接接收原始 URL | `ParserRouter.should_use_understanding_directly` | 直達 Understanding 或繼續 Accessor |
| Understanding 與內建 Parser | `ParserRouter.parse` | `ParseResult` |

後臺資源任務統一使用可恢復的 `AddResourceMsg`，但按工作型別進入兩個獨立佇列：Understanding 使用受外部解析併發限制的 `ExternalParse`；Git 和已落盤的本地後處理使用 `AddResource`。兩個佇列都由 `AddResourceProcessor` 消費，鎖接管失敗時仍回到原佇列。訊息已經凍結了生產端做出的選擇，例如 `parser_backend`、`understanding_response_id` 和 `resolved_extension`。Worker 直接執行該選擇，不再把任務送回公開 `add_resource` 重新分類。

## 頂層路由表

| 輸入或場景 | 獲取資料 | 解析者 | 是否走標準 `ParseResult -> TreeBuilder` | 返回時機 |
|---|---|---|---|---|
| Connector 配置允許的 TOS 或 Git，提供精確 `to` 且引數受支援 | Connector 服務 | Connector 服務 | 否 | 提交成功立即返回 `task_id`，後臺輪詢狀態 |
| `tos://` 但 Connector 不可用或引數不支援 | 不降級 | 不執行 | 否 | 直接報清晰的引數或配置錯誤 |
| Git 未命中 Connector 或無憑證回退，`wait=false` | GitAccessor 在後臺 clone | 內建目錄/程式碼倉庫 Parser | 是 | 預檢倉庫並預佔 URI 後返回 |
| Git，`wait=true` | GitAccessor | 內建目錄/程式碼倉庫 Parser | 是 | 解析、落盤及語義佇列完成後返回 |
| HTTP 服務請求，`wait=false`，命中 Understanding | HTTPAccessor 識別型別並上傳同一份本地檔案 | Understanding | 是 | 型別識別、Understanding 提交、URI 預佔和入隊後返回 |
| 其他 URL、檔案、目錄、原始文本 | 對應 Accessor；原始文本無需 Accessor | 內建 Parser 或同步 Understanding | 是 | 至少完成解析和落盤後返回 |

Git 是 Connector 與標準鏈共享的來源：未命中 Connector 或引數不受支援時可回退到標準鏈；一旦請求帶有 Connector 專用憑證則禁止回退，避免憑證進入持久化佇列。`tos://` 沒有標準 Accessor，不能回退，否則只會在更深處得到誤導性的解析錯誤。

## Accessor：先把“資料在哪”變成“本地是什麼”

`AccessorRegistry` 按優先順序選擇資料訪問器，當前內建順序是：

```text
GitAccessor (80)
WebFeedAccessor (60)
HTTPAccessor (50)
LocalAccessor (1)
```

Accessor 的產物統一是 `LocalResource`，包含本地檔案或目錄路徑、`source_type`、原始來源、是否需要清理，以及檢測後設資料。標準 Parser 不再負責 clone 或下載；只有 Understanding 可直接接收的原始 URL 會在 Accessor 前被消費。

`UnifiedResourceProcessor.prepare` 隨後凍結兩個欄位：

- `resolved_extension`：本次 Parser 路由唯一使用的副檔名。
- `resolved_name`：用於展示、預設資源命名和 Understanding 上傳檔名，不參與 HTTP 資源的型別覆蓋。

HTTP 資源以 HTTPAccessor 檢出的 `meta.extension` 為準；本地檔案或上傳的臨時檔案可優先使用顯式 `source_name` 的副檔名。這樣既不會拿隨機臨時檔名選 Parser，也不會讓使用者提供的 URL 名稱覆蓋實際下載內容型別。

本地檔案進入 Understanding 時，ParserRouter 將凍結的 `resolved_name` 和 `resolved_extension` 一起傳給上傳層。上傳層使用來源名稱的 basename；如果末尾沒有已識別的副檔名（忽略大小寫），則追加該副檔名，保留名稱中的編號和版本資訊。例如無後綴 URL `/export?id=123` 返回 `Content-Type: application/pdf` 時，上傳檔名為 `export.pdf`；`2601.00014` 會補成 `2601.00014.pdf`，`report.PDF` 保持原樣。內部的 MPEG-TS 路由標記轉換為真實的 `.ts` 字尾。

普通上傳、分片上傳和 MIME 型別推斷統一使用補全後的上傳檔名，本地路徑用於讀取檔案。同步解析、提前提交解析和僅上傳獲取 `file_id` 使用相同規則。`resource_name` 只控制外層資源目錄，例如 `README.md` 下載為 `/tmp/tmpABC.md` 後，上傳檔名仍為 `README.md`。

## 無後綴 URL 怎麼判斷型別

HTTPAccessor 按以下順序收集和修正型別：

1. URL path 中受支援的顯式副檔名。
2. HEAD 響應的 `Content-Disposition` 檔名。
3. HEAD 響應的 `Content-Type`。
4. GET 響應的 `Content-Disposition` 和 `Content-Type`，用於修正之前的模糊網頁判斷。
5. GET 內容的 magic bytes，例如 PDF、圖片、音影片、Office/EPUB/ZIP 簽名。
6. 仍無法識別時按網頁處理。

最終副檔名寫入 `LocalResource.meta.extension`，然後凍結為 `resolved_extension`。`ParserRouter` 只讀取這個結果。URL 上已有明確副檔名時，不用 magic bytes 擅自覆蓋它。

因此，`wait=false` 不等於“完全不碰源站就返回”。HTTP 服務收到無後綴遠端 URL、且 Understanding 已啟用時，必須先下載或探測一次，才能知道應進入外部解析佇列還是內建 Parser。命中 Understanding 後，生產端直接上傳這份已檢測的本地檔案並取得 `response_id`，然後才清理臨時檔案；Worker 只恢復該 response，不會重新下載可能已過期或內容已變化的 URL。

## Parser：只回答“本地內容怎麼解析”

標準執行鏈分四類：

- 原始文本：直接進入內建 `ParserRegistry`。
- 可由 Understanding 直接接收的原始 URL：在 Accessor 前進入 `ParserRouter`。
- 本地目錄：直接進入 `DirectoryParser`；Git 倉庫由目錄鏈委派給程式碼倉庫 Parser。
- 本地檔案：進入 `ParserRouter`，根據 `resolved_extension` 在內建 `ParserRegistry` 與 Understanding 之間選一次。

ParserRegistry 只註冊專案內建 Parser，不再提供自定義 Parser 類、回呼註冊或可選模組註冊入口。新增資料來源優先實現 Accessor；新增檔案格式則直接增加內建 Parser 和對應測試。

目錄、網站和由內建 ZipParser 展開的壓縮包，其“子檔案遍歷”仍屬於當前內建
Parser 的內部實現，不回到頂層 `ResourceService`。`DirectoryParser` 會遞迴掃描
每個葉子檔案，並通過 `ParserRouter` 重新檢查 `parser_api.extensions`：命中的檔案
交給 Understanding，未命中的檔案繼續使用內建 Parser 或直接寫入。該過程在當前
目錄任務內執行，不會把每個子檔案拆成獨立的 `ExternalParse` 佇列任務。頂層壓縮
檔案本身是否直接進入 Understanding，仍由其凍結副檔名和
`parser_api.extensions` 決定。

啟用 Understanding 目錄路由後，每次 `DirectoryParser` 掃描在發起該層遠端請求前執行
預檢，預設限制為 1000 個入選檔案和 10 層目錄深度；關閉 Understanding 時，
Business Data Platform 原生目錄解析不應用這兩個限制。內建 `ZipParser` 遞迴展開壓縮包時會建立新的
目錄掃描，巢狀 ZIP 不與外層共享檔案數量和深度預算。
客戶端匯入本地目錄時，會先將整個目錄壓縮為 ZIP，再由
`/resources/temp_upload` 對整個 ZIP 執行上傳大小限制。ZIP 解壓後的葉子檔案不再由
`DirectoryParser` 設定統一大小限制，而是交給對應內建 Parser 或 Understanding，遵循
各自的格式和上傳限制。這些檔案使用固定 worker 池，預設併發為 4；遠端解析可以併發，
但向目錄臨時樹的合併始終按掃描順序序列執行。目錄限制可通過
`parsers.directory` 配置調整。目錄內部分檔案失敗時仍提交成功檔案並通過
`meta.failed_files` 返回失敗詳情；巢狀 ZIP 的葉子失敗使用 `bundle.zip/path/to/file`
形式的路徑並保留遠端任務 ID。如果沒有任何檔案成功，則在 TreeBuilder 持久化前
終止任務，並清理本次請求新預佔的空目標目錄。

## Understanding 鏈路

Understanding 是“外部解析器”，不是“外部落盤器”：

```text
LocalResource / 遠端源
        |
        v
Understanding API
        |
        v
解析結果 ZIP
        |
        v
解壓到臨時 Viking 目錄
        |
        v
ParseResult
        |
        v
TreeBuilder + 標準摘要/索引鏈
```

同步路徑中，Accessor 已下載的本地檔案會直接上傳給 Understanding，`original_source` 只保留作來源後設資料。普通 HTTP 檔案的非同步路徑也先上傳已檢測檔案，再通過統一的 `AddResourceMsg` 持久化 `understanding_response_id`、凍結的 `resolved_extension` 和 `parser_backend="understanding"`；Worker 直接恢復 response，既不重新下載源 URL，也不因配置變化重新選擇後端。這些凍結欄位是內部任務欄位，公共 `args` 不能指定，避免呼叫方繞過外部解析開關和副檔名白名單。

Understanding 返回 ZIP 時，本地介面卡會安全解壓，並根據 Markdown 的相對圖片引用生成受控的圖片對映 sidecar。TreeBuilder 後續仍使用統一的圖片 URI 改寫鏈。

這條鏈的關鍵特徵是：Understanding 只替代 Parser，後面的 `ParseResult`、URI 規劃、TreeBuilder 落盤、摘要和索引仍屬於 Business Data Platform。

## Connector 鏈路

Connector 是另一套端到端匯入服務：

```text
ResourceService
    |
    +--> Connector doc/add
              |
              +--> Connector 獲取源資料
              +--> Connector 解析
              +--> Connector 寫入目標資源樹
    |
    +--> 後臺輪詢 Connector task/info
              |
              +--> 更新 Business Data Platform TaskRecord
```

Connector 不返回本地 `ParseResult`，也不呼叫當前程序的 `TreeBuilder`。Business Data Platform 只負責校驗這次請求能否無損委派、提交任務、返回 Business Data Platform `task_id`，再把 Connector 的終態同步到任務記錄。

Connector 當前要求提供精確 `to`，不接受 `parent`；也不支援 `wait=true`、watch、instruction、關閉建索引、摘要、strict、include/exclude 等。無憑證的 Git 請求可回退到標準鏈；帶 Connector 專用憑證的 Git 和 Connector-only 來源會立即報錯，避免憑證落入本地持久化任務。

## `wait` 的準確含義

| 路徑 | `wait=false` | `wait=true` |
|---|---|---|
| Connector | 提交外部任務後返回 | 不支援；不會假裝同步等待 |
| Git | 預檢並預佔 URI 後啟動後臺標準鏈 | 當前請求內完成標準鏈並等待佇列 |
| HTTP 服務 + 非同步 Understanding | 先識別型別，再預佔 URI、入 `ExternalParse` 後返回 | 當前請求內呼叫 Understanding，再等待後續佇列 |
| 普通標準鏈 | 解析和落盤完成後返回；摘要/語義處理由任務監控 | 解析和落盤完成後繼續等待語義佇列 |

所以普通 `wait=false` 不是“所有工作後臺化”，而是“資源樹已落盤，但不阻塞等待後續語義任務”。Git 與非同步 Understanding 是兩個明確的例外分支。

## 目標 URI、鎖和失敗邊界

- 需要後臺執行的 Git 與普通檔案 Understanding 任務會先規劃並預佔目標 URI，避免返回的 URI 隨後臺競態變化。
- 鎖通過 handoff 交給後臺任務或佇列 Worker；入隊失敗時立即釋放，並把任務標為失敗。
- 臨時 `LocalResource` 由擁有它的呼叫層清理；交給標準處理器後，清理責任隨之轉移。
- Parser 產生 `ParseResult` 後才進入 TreeBuilder。沒有臨時解析產物時標準鏈返回解析錯誤；目錄允許帶 warnings 的部分成功，`strict` 決定是否暴露這些警告。
- Connector 的失敗邊界在外部任務終態，Business Data Platform 不對其內部檔案逐個回滾。

## 程式碼定位

| 職責 | 入口 |
|---|---|
| 公開入口、新請求分流與內部執行 | `openviking/service/resource_service.py`：`ResourceService.add_resource`、`_submit_resource_ingestion`、`_execute_resource_ingestion` |
| Watch 刷新入口 | `openviking/service/resource_service.py`：`ResourceService.refresh_resource`；`openviking/resource/watch_scheduler.py` |
| 標準解析與落盤編排 | `openviking/utils/resource_processor.py`：`ResourceProcessor.process_resource` |
| Accessor 與 Parser 兩層銜接 | `openviking/utils/media_processor.py`：`UnifiedResourceProcessor` |
| 檔案 Parser 單次選擇 | `openviking/parse/parser_router.py`：`ParserRouter` |
| 內建 Parser 註冊 | `openviking/parse/registry.py`：`ParserRegistry` |
| HTTP 型別識別 | `openviking/parse/accessors/http_accessor.py`：`HTTPAccessor`、`URLTypeDetector` |
| Understanding 同步適配 | `openviking/parse/understanding_api.py`：`UnderstandingAPI` |
| 可恢復的後臺資源訊息與雙佇列 Worker | `openviking/storage/queuefs/add_resource_msg.py`、`add_resource_processor.py`、`queue_manager.py` |
| Connector 客戶端 | `openviking/connector/client.py`：`ConnectorClient` |

## 快速自檢

- 無後綴 PDF URL：HTTPAccessor 從響應頭或 PDF 簽名得到 `.pdf`，ParserRouter 再決定是否使用 Understanding。
- Understanding 返回結果：先轉成 `ParseResult`，仍由本地 TreeBuilder 落盤。
- Connector 返回結果：只返回任務標識，不經過本地 `ParseResult`。
- 普通 Markdown 且 `wait=false`：返回前 Markdown 已解析並落盤，只是不等待後續語義佇列。
- 網站抓取出的目錄：進入 DirectoryParser，頁面子檔案不會逐個呼叫 Understanding。
