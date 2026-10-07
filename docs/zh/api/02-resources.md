# 資源管理

資源是智慧體可以引用的外部知識。本模組提供資源的新增、匯入/匯出、臨時檔案上傳等功能。

## 核心概念

### 資源型別

OpenViking 支援多種資源型別，按照功能分類如下：

文件類
| 型別 | 副檔名 | 說明 |
|------|--------|------|
| PDF | `.pdf` | 支援本地解析和 MinerU API 轉換 |
| Markdown | `.md`, `.markdown`, `.mdown`, `.mkd` | 原生支援，會提取結構並分段儲存 |
| HTML | `.html`, `.htm` | 清理導航/廣告後提取內容，轉換為 Markdown |
| Word | `.doc`, `.docx`, `.docm`, `.odt`, `.rtf` | 基於 anydoc 提取文本、標題、表格和嵌入圖片並轉換為 Markdown |
| 純文本 | `.txt`, `.text` | 直接匯入處理 |
| EPUB | `.epub` | 基於 anydoc 將電子書內容和嵌入圖片轉換為 Markdown |

表格類
| 型別 | 副檔名 | 說明 |
|------|--------|------|
| Excel | `.xlsx`, `.xls`, `.xlsm`, `.xlsb`, `.ods`, `.csv` | 基於 anydoc 按工作表轉換為 Markdown 表格 |
| PowerPoint | `.pptx`, `.ppt`, `.pptm`, `.pps`, `.ppsx`, `.ppsm`, `.pot`, `.odp` | 基於 anydoc 按幻燈片提取內容和嵌入圖片並轉換為 Markdown |

程式碼類
| 型別 | 資源名 | 說明 |
|------|--------|------|
| 程式碼檔案 | `*.py`, `*.js`, ... | 支援常見程式語言（Python, JavaScript, Go, Rust, Java 等） |
| Git 協議程式碼倉庫 | `git://...` | Git URL, 本地目錄, `.zip` 包，遵循 `.gitignore` 並自動過濾 `.git`, `node_modules` 等目錄 |
| Git 程式碼託管平臺 | `https://github.com/{org}/{repo}` | GitHub, GitLab, Bitbucket 等程式碼託管平臺的 URL |
| Git 程式碼託管平臺上的 raw 檔案 | `https://github.com/{org}/{repo}/raw/{branch}/{path}` | GitHub, GitLab, Bitbucket 等程式碼託管平臺的 raw 檔案下載 URL |

媒體類
| 型別 | 資源名 | 說明 |
|------|--------|------|
| 圖片 | `*.jpg`, `*.jpeg`, `*.png`, `*.gif` ... | 多種圖片格式，通過 VLM 生成描述（實驗特性） |
| 影片 | `*.mp4`, `*.avi`, `*.mov` ... | 儲存原檔案；可選 VLM 內容理解需要相容的媒體配置 |
| 音訊 | `*.mp3`, `*.wav`, `*.m4a` ... | 儲存原檔案；可選 VLM 內容理解需要相容的媒體配置 |

音影片解析器負責校驗並儲存原檔案。內容理解在後續語義處理階段執行，預設關閉（`vlm.media.enabled=false`），需啟用相容的供應商和模型；理解支援的格式與大小限制和匯入格式不同。這不代表內建了 Whisper 轉寫或本地關鍵幀提取流程。詳見[音影片配置](../guides/01-configuration.md)。

網頁類（遞迴網頁爬蟲）
| 型別 | 資源名 | 說明 |
|------|--------|------|
| 單頁 / 遞迴抓取 | `https://host/path` | 預設僅抓入口頁；設定 `args.depth > 0` 後，沿同域連結 BFS 遞迴展開，`args.max_pages` 只限制最多收集的頁面數。每頁用 trafilatura 抽成 Markdown。可選 `args`：`depth`、`max_pages`、`include_paths`、`exclude_paths`、`allow_external_links`、`skip_download_links`。頁面中發現的下載連結預設跳過（`skip_download_links=true`），避免匯入 `llms.txt` 等 sidecar 檔案造成重複；設為 `false` 時會下載同域檔案連結，並計入 `max_pages`。`include_paths`/`exclude_paths` 按**路徑字首**匹配（例如 `/docs/` 僅匹配以 `/docs/` 開頭的路徑，不會誤命中 `/blog/docs-tips`）。|

> 路由說明：`https://host/sitemap.xml`、`https://host/feed.xml`、`*.atom` 等 sitemap-looking URL 和顯式 `args.site=true` 讓出給下表的整站匯入；`https://github.com/{org}/{repo}` 等 Git 託管平臺 URL 讓出給上文的程式碼匯入。

網站類（sitemap / RSS / Atom 整站匯入）
| 型別 | 資源名 | 說明 |
|------|--------|------|
| 站點地圖 Sitemap | `https://host/sitemap.xml`、`https://host/sitemap-index.xml` | 解析 sitemap，將站點所有頁面抓取為**一棵資源樹**（每頁一個子節點），支援巢狀 `<sitemapindex>` 遞迴。整站只生成一個資源，落在 `viking://resources/<host>`。 |
| RSS / Atom 訂閱源 | `https://host/rss.xml`、`https://host/atom.xml`、`https://host/feed` | 解析 RSS 2.0 / Atom，逐條把文章正文抓成樹節點（feed 內含全文則直接使用，省一次抓取）。 |
| 整站自動發現 | `https://host` + `args.site=true` | 對裸域名/普通頁面強制整站匯入：自動通過 robots.txt、HTML `<link rel="alternate">` autodiscovery、常見路徑發現 sitemap/RSS，再整站抓取。 |

抓取**有界、非遞迴**（不會超出所列頁面繼續爬），受 `parsers.webfeed` 配置約束（`max_pages`、`max_concurrency`、`politeness_delay`、`same_host_only`、`respect_robots`、`max_depth`），並遵守 robots.txt。對 sitemap/feed URL 設定 `watch_interval` 即可讓**整站**週期重新整理：每次執行自動納入新增頁面、移除已刪除頁面。新增單個首頁（未帶 `args.site`）時，返回資訊可能附帶一行"整站匯入"提示——**只提示，絕不自動爬全站**。

### 資源處理流程

資源新增經過以下處理階段：

```
源輸入 → 解析 → 資源樹構建 → 持久化 → 語義處理
  ↓        ↓         ↓          ↓          ↓
URL/文件  Parser  TreeBuilder  AGFS    Summarizer/Vector
```

#### 階段 1：源解析 (Parse)
- 使用 `UnifiedResourceProcessor` 根據資源型別解析內容
- 支援多種格式：文件（PDF/Markdown/Word）、表格（Excel/PPT）、程式碼、媒體檔案等
- 解析結果寫入臨時 VikingFS 目錄
- 媒體檔案通過 VLM（視覺語言模型）生成描述

#### 階段 2：資源樹構建 (TreeBuilder)
- `TreeBuilder.finalize_from_temp()` 掃描臨時目錄結構
- 構建資源樹節點，處理 URI 衝突（自動重新命名）
- 建立目錄與資源的關聯關係

#### 階段 3：持久化儲存 (Persist)
- 檢查目標 URI 是否已存在
- 新資源：移動臨時檔案到正式 AGFS 位置
- 已存在資源：保留臨時樹用於後續差異比較
- 獲取生命週期鎖防止併發修改
- 清理臨時目錄

#### 階段 4：語義處理 (Semantic Processing)
- **摘要生成**：`Summarizer` 生成 L0（摘要）和 L1（概述）
- **向量索引**：將內容向量化用於語義搜尋
- 通過 `SemanticQueue` 非同步處理，使用返回的 `task_id` 查詢完成狀態

#### 非等待 Git 倉庫匯入
- 對 Git 倉庫來源使用 `wait=false` 時，OpenViking 會先校驗倉庫、解析目標 URI、預佔最終 `root_uri`，然後在 clone/parse/finalize 完成前返回。
- 立即響應包含 `status`、`root_uri` 和 `task_id`；抓取、解析、finalize 以及佇列等待會在持久化後臺任務中繼續執行。
- 可通過 `GET /api/v1/tasks/{task_id}` 查詢任務狀態。Git 資源匯入任務的階段包括 `queued`、`fetching`、`parsing`、`finalizing`、`processing_queue`。
- 其他資源來源使用 `wait=false` 時，會在響應前完成抓取/解析/finalize；返回的 `task_id` 只用於跟蹤 semantic 和 embedding 佇列完成情況。

### 資源的增量更新

資源增量更新通過**監控任務 (Watch Task)** 機制實現：

#### 監控任務建立
- 呼叫 `add_resource` 時，為 URL、sitemap、RSS 等可重新讀取的來源設定 `watch_interval > 0`（單位：分鐘），即可建立監控任務
- `temp_file_id` 引用的上傳內容是一次性快照，不能建立監控任務。Python HTTP SDK 也會將本地檔案/目錄上傳為快照，因此本地路徑不能與 `watch_interval > 0` 組合使用；本地來源變化後請重新新增
- 可指定 `to` 引數確定目標 URI；未指定時，系統會使用本次匯入返回的 `root_uri` 作為監控目標
- 把監控物件設為 sitemap/RSS/Atom URL，即可讓**整站**保持同步：每次重新整理重新讀取 feed 並重建資源樹，新發布的頁面自動入庫、已刪除的頁面自動移除
- `WatchManager` 負責任務持久化儲存
- 支援多租戶許可權控制（ROOT/ADMIN/USER 許可權分級）

#### 目標占用規則

- 同一帳戶內，原生 Watch 獨佔解析後的目標，暫停後仍然佔用。新建原生 Watch 要求目標未被佔用，Connector Watch 也不能與原生 Watch 共享目標。
- 多個 Connector Watch 可以共享目標。重複匯入相同來源和目標會建立新的獨立 Watch，不會更新或恢復已有任務；同一來源匯入不同目標也會建立獨立 Watch。
- Connector Watch 在首次匯入前建立，排程器會等待首次匯入記錄結果後再執行定時任務。

#### 任務排程執行
- `WatchScheduler` 每 60 秒檢查到期任務
- 預設併發控制，避免重複執行
- 到期任務自動重新呼叫 `add_resource` 處理
- 更新任務的最後執行時間和下次執行時間

#### 任務管理操作
- **建立**：`watch_interval > 0` 時按上述目標占用規則建立新任務；不相容的佔用返回 `409 Conflict`。
- **更新或恢復**：通過 `PATCH /api/v1/watches/{task_id}` 修改引數或設定 `is_active: true`；重新匯入不會更新或恢復已有任務。
- **暫停或刪除**：通過 `PATCH /api/v1/watches/{task_id}` 設定 `is_active: false` 暫停任務，或通過 `DELETE /api/v1/watches/{task_id}` 刪除任務以釋放目標。原生匯入顯式指定 `to` 且 `watch_interval <= 0` 時，會暫停該目標上唯一可訪問的 Watch；存在多個可訪問的 Watch 時返回 `409 Conflict`。一次性 Connector 匯入不影響已有 Watch。
- **查詢**：通過任務 ID 查詢；目標 URI 僅在對應唯一可訪問的 Watch 時可用於定位。存在多個可訪問的 Watch 時，按 URI 查詢返回 `409 Conflict`，需通過 `task_id` 查詢、更新或刪除指定任務。

## API 參考

### add_resource

向知識庫新增資源，支援本地檔案/目錄、URL 等多種來源。通過 `temp_file_id` 引用的上傳內容是一次性快照，因此不能與 `watch_interval > 0` 組合使用。

#### 1. API 實現介紹

此介面是資源管理的核心入口，支援多種來源的資源新增，預設返回 `task_id` 供呼叫方查詢處理狀態。SDK 可直接處理本地檔案/目錄、URL 等來源；直接 HTTP 呼叫只通過 `path` 接受遠端 URL，或通過 `temp_file_id` 引用先上傳的本地檔案。

**處理流程**：
1. 識別並校驗資源來源（URL 或上傳的臨時檔案）
2. 解析目標 URI
3. 呼叫對應格式 Parser；`args.parse_mode` 控制轉換後的 Markdown 正文是否允許拆分
4. 構建目錄樹並寫入 AGFS
5. 按 `processing_mode` 執行入庫後的處理：`semantic_and_vectors` 生成語義產物和向量；`vectors_only` 跳過語義理解，只提交檔案向量化
6. 預設返回 `task_id`；呼叫方通過任務 API 確認處理完成
7. 如果 `reason` 非空，將其追加到固定的資源 reason session 並 commit，複用常規記憶抽取鏈路，讓合適的使用者記憶引用該資源 URI
8. 如指定 `--watch-interval`，設定定時更新任務

**程式碼入口**：
- `sdk/python/openviking_sdk/client.py:AsyncHTTPClient.add_resource` - Python SDK 入口
- `openviking/server/routers/resources.py:add_resource` - HTTP 路由
- `openviking/service/resource_service.py` - 核心服務實現
- `crates/ov_cli/src/handlers.rs:handle_add_resource` - CLI 處理

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| path | string | 否 | - | 遠端資源 URL（HTTP/HTTPS/Git）。與 `temp_file_id` 二選一 |
| temp_file_id | string | 否 | - | 臨時上傳檔案 ID。與 `path` 二選一 |
| to | string | 否 | - | 本次匯入的最終儲存位置。目標已存在時會覆蓋該目標；與 `parent` 互斥 |
| parent | string | 否 | - | 父級 Viking URI（資源放入此目錄下）。與 `to` 互斥 |
| create_parent | bool | 否 | False | 如果父目錄不存在，自動建立父目錄（服務端標誌） |
| reason | string | 否 | "" | 新增資源的原因；非空時會隨資源 URI 進入常規 session 記憶抽取鏈路，並在生成的記憶中記錄資源引用 |
| instruction | string | 否 | "" | 語義提取的處理指令（實驗特性） |
| wait | bool | 否 | False | 是否等待語義處理和向量化完成才返回 |
| timeout | float | 否 | None | 超時時間（秒），僅 `wait=true` 時生效 |
| strict | bool | 否 | False | 是否使用嚴格模式 |
| ignore_dirs | string | 否 | None | 要忽略的目錄名（逗號分隔） |
| include | string | 否 | None | 包含的文件模式（glob） |
| exclude | string | 否 | None | 排除的文件模式（glob） |
| directly_upload_media | bool | 否 | True | 是否直接上傳媒體檔案 |
| preserve_structure | bool | 否 | None | 是否保留目錄結構 |
| args | object | 否 | `{}` | 傳給特定 parser/accessor 的匯入引數。原生 HTTPS Git 匯入和 Watch 可通過 `args.auth_config={"username":"oauth2","token":"..."}` 在 TLS 上傳遞 HTTP Basic 憑據；`username` 預設為 `oauth2`。Git 的 `branch` 或 `commit` 仍放在 `args` 頂層。通過 HTTP(S) URL 匯入私有 TOS 物件時，二選一傳入非空字串：`args.tos_signature`（對映為 `X-Tos-Signature`）或 `args.tos_access`（對映為 `X-Tos-Access`）。TOS 憑證只用於當前 HEAD/GET 抓取；資源會先儲存為快照，憑證不會寫入資源後設資料或佇列任務。`args.parse_mode` 支援 `default`（保持現有拆分行為）和 `no_split`（正常解析並將每個源文件正文儲存為一個 Markdown 檔案）。例如 `args.site=true/false` 強制/停用整站（sitemap/RSS）匯入，`args.max_pages` 等可覆蓋 `webfeed` 配置；遞迴網頁爬蟲支援 `args.depth`、`args.max_pages`、`args.include_paths`、`args.exclude_paths`、`args.allow_external_links`、`args.skip_download_links`。`path`、`to`、`watch_interval`、`include`、`exclude` 等 `add_resource` 核心欄位不能放入 `args` |
| watch_interval | float | 否 | 0 | 定時更新間隔（分鐘）。>0 按目標占用規則為可重新讀取的來源建立新 Watch；通過 `temp_file_id` 上傳的一次性快照不能建立 Watch。≤0 不建立 Watch：原生匯入顯式指定 `to` 時暫停唯一可訪問的任務（存在歧義時返回 409），Connector 匯入不影響已有 Watch。顯式 `to` 優先，否則繫結本次匯入的 `root_uri`。 |
| is_active | bool | 否 | True | Watch 初始排程狀態。設為 `false` 時要求 `watch_interval > 0`，並在 `to`、`parent` 中二選一。`parent` 支援原生 Git 匯入；Connector 仍要求精確的 `to`。首次匯入仍執行一次，隨後保持暫停 |
| processing_mode | string | 否 | `semantic_and_vectors` | 入庫後的處理模式。`semantic_and_vectors` 是預設流程：生成語義產物（`.abstract.md`、`.overview.md`）並生成向量。`vectors_only` 跳過語義理解/VLM 總結，只對當前資源檔案生成向量 |
| tags | string[] | 否 | None | 匯入時寫入向量檢索記錄的顯式檢索標籤，格式必須是 `k=v`，例如 `["team=search", "env=test"]`。搜尋介面可用同名 `tags` 引數過濾召回 |
| tag_mode | string | 否 | `"replace"` | 標籤寫入模式：`replace` 覆蓋、`append` 按 key 合併、`clear` 清空。`clear` 不要求傳 `tags`；`replace` 配合空陣列不會修改已有標籤。匯入時標籤會隨本次生成的每條向量記錄寫入；不會在完成後額外呼叫 `set_tags`，響應也不返回 `tags_result` |
| acl | object | 否 | None | 設定最終匯入根節點的直接 ACL，要求 manage；省略時保留已有許可權。見 [ACL API](12-acl.md)。 |
| telemetry | TelemetryRequest | 否 | False | 是否返回遙測資料 |

**補充說明**：
- `to` 和 `parent` 不能同時使用。`to` 是最終儲存位置：目標不存在就建立，目標已存在就覆蓋該目標；如果目標是目錄，目錄裡本次匯入沒有生成的舊檔案或子目錄會被刪除。`parent` 是儲存目錄，適合向已有目錄追加新資源；父目錄不存在時使用 `create_parent=true` 或 CLI 的 `--parent-auto-create`。當匯入後的 `root_uri` 與 `to` 相同時，語義與向量處理會複用未變化內容，只處理變化部分。
- 建立新資源要求目標父目錄可寫；顯式更新已有 `to` 要求該目標可寫。許可權校驗在任務入隊前完成。自動命名按實際 URI 佔用判斷，即使同名資源不可讀也會選擇 `_1`、`_2` 等字尾，而不會嘗試覆蓋。
- `wait=false` 返回的 `status=accepted` 表示任務已通過預檢查併入隊，不表示資源處理已經完成；最終狀態以對應 `task_id` 為準。
- 如果同時省略 `to` 和 `parent`，服務端會先嚐試使用當前使用者的 `add_targets.resource_uri` 覆蓋配置，再使用 `server.user_config_defaults.add_targets.resource_uri`。兩者都沒有配置時，保持舊的目標解析行為。
- 資源目標可以使用公共 `viking://resources/...`、家目錄別名 `viking://~/resources/...`、顯式使用者 `viking://user/{user_id}/resources/...`，或 peer 級 `viking://user/{user_id}/peers/{peer_id}/resources/...`。家目錄別名會按請求身份展開為 canonical 路徑；無 uid 的寫法 `viking://user/resources/...` 會被拒絕，並提示改用 `viking://~/resources/...`。
- `user_id` 和 `peer_id` 路徑片段必須是安全的單段標識，例如 `alice` 或 `web-visitor-alice`。包含路徑分隔符、`.`、`..`、`:` 或 `+` 的值會被拒絕。
- `path` 和 `temp_file_id` 不能同時指定，上傳本地檔案需要先通過 [temp_upload](#temp-upload) 上傳獲取 `temp_file_id`，在 SDK 和 CLI 中已經封裝好。
- `tags` 會在資源解析後、向量記錄寫入時同步寫入底層向量庫。`add_resource(tags=...)` 不返回 `tags_result`；需要驗證時，可在 `/api/v1/search/find` 或 `/api/v1/search/search` 中傳相同 `tags` 過濾召回。
- 只有 Git 倉庫來源在 `wait=false` 時使用完整後臺匯入；OpenViking 會先完成倉庫 preflight 和目標規劃，再返回 `task_id`。
- 原生 HTTPS Git 的 `args.auth_config` 在 `watch_interval <= 0` 時只用於本次請求；當 `watch_interval > 0` 時，OpenViking 會把與倉庫 URL 繫結的 username/token 儲存到 Watch 私有鑑權狀態，並只在後續 Git 拉取時恢復使用。憑據不會進入普通持久佇列，也不會出現在 Watch API/MCP/CLI 返回中。Git PAT 沒有通用重新整理流程，過期或撤銷後需要重建 Watch 來更換 token。為相容已有用法，系統仍接受 `https://user:token@host/repo.git` 形式的 URL 內嵌憑據並原樣傳遞；由於該 URL 同時也是資源來源標識，它可能被記錄到程序引數、日誌、佇列、資源後設資料和 Watch 狀態中。新接入建議使用 `args.auth_config`。`args.auth_config` 的明文 HTTP 鑑權和帶鑑權重定向仍會被拒絕。
- token 會放在 HTTPS 請求體中傳輸。生產環境應保持診斷請求體 dump 關閉；顯式啟用該功能可能記錄秘密。
- `reason` 觸發的記憶生成複用 `session.commit` 的抽取鏈路，只使用 `reason`、資源 URI、可用的資源名稱和目錄摘要，不會讀取或展開完整資源正文；系統會寫入 `entities`、`events`、`preferences` 等已有記憶型別，不建立獨立的資源記憶目錄。
- 刪除資源時，系統會在刪除前掃描本次上下文對應的 self 或 peer 記憶中的 `resource_refs`，清理對應資源 URI 和由該 `reason` 引入的內容，並重新重新整理相關記憶的語義索引。
- 其他來源在 `wait=false` 時會在響應前完成來源解析、目標解析和 AGFS 寫入，僅 semantic 與 embedding 佇列繼續非同步處理。
- `processing_mode=vectors_only` 不呼叫 VLM 語義理解階段，也不會生成或重新整理 `.abstract.md` / `.overview.md`。對已存在目標，它會保留舊的語義產物和舊的語義向量；仍會更新資源樹，在 `build_index=true` 時向量化當前非隱藏檔案，並清理由本次重新整理刪除的檔案 detail 向量。
- `processing_mode` 只屬於 `add_resource`。管理員維護已有資料時，`reindex` API/CLI 仍使用 `mode`（`vectors_only`、`semantic_and_vectors`、`prune_orphans`）。
- `watch_interval > 0` 時，如果指定了 `to`，監控任務繫結該目標；如果未指定 `to`，監控任務繫結本次匯入返回的 `root_uri`。如果無法得到穩定 `root_uri`，請求會報錯並要求顯式傳 `to`。
- Connector 匯入設定 `is_active=false` 時會在提交前建立暫停狀態的 Watch；原生 Git 匯入會通過資源佇列透傳 `is_active`，解析出最終資源 URI 後再建立 Watch。兩種情況下首次匯入均執行一次，週期排程保持關閉。
- Watch task 的憑據狀態（例如 Git `args.auth_config`）儲存在內部控制檔案 `viking://resources/.watch_tasks.json` 中，不會出現在 watch API/MCP/CLI 返回裡。若啟用了 VikingFS 檔案加密，該控制檔案會靜態加密；否則服務端控制檔案中會包含這些明文私有狀態。
- 本地目錄輸入會遵循 `.gitignore`（根目錄和子目錄，標準 Git 語義）；`ignore_dirs`、`include`、`exclude` 會在此基礎上進一步過濾。
- 目錄匯入僅在至少一個入選檔案成功時採用 best-effort：失敗檔案寫入 `meta.failed_files`，成功檔案正常提交。巢狀 ZIP 的葉子失敗使用 `bundle.zip/path/to/file` 形式的歸檔限定路徑，並保留遠端任務 ID。如果沒有任何檔案成功，或篩選後沒有可處理檔案，任務會失敗且不會保留空資源目錄。
- `args.parse_mode=no_split` 仍呼叫正常的格式 Parser。PDF、Word、PowerPoint、HTML 等受支援文件會轉換為 Markdown，但跳過按標題、段落和長度拆分。目錄匯入會對每個受支援文件分別應用該規則，並繼續遵循 `.gitignore`、篩選引數和 `preserve_structure`。該模式下，配置為走 Understanding 的目錄檔案會回退到對應的原生 Parser；沒有原生解析能力的檔案會寫入 `meta.failed_files`，但不會阻止其他入選檔案成功匯入。
- 對單檔案輸入使用 `no_split` 時，如果解析結果恰好只有一個可見檔案且未指定 `to`，該檔案會直接放到解析出的父目錄下（例如 `guide.md` 寫入 `viking://resources/guide.md`），不會建立同名上層目錄，也不會生成目錄級 `.abstract.md` / `.overview.md`。如果解析結果還包含圖片等其他可見檔案，則保留上層目錄。顯式指定的 `to` 始終作為最終 URI 原樣保留。
- `no_split` 只改變 Markdown 正文的儲存佈局，不改變語義處理、檔案向量化和內部 embedding 分塊。Markdown 相對連結會按同一個 no-split 輸出佈局解析，不會再指向僅拆分模式存在的路徑。該模式下不會為目錄檔案呼叫 Understanding。
- 如果要直接建立或更新純文本內容，請使用 [content/write](03-filesystem.md#write)，不要使用 `add_resource`。資源匯入和內容寫入後都會自動重新整理語義與 embedding。

#### 3. 使用示例

以下示例使用預設非同步模式，不設定等待引數。提交後儲存 `task_id`，通過 [任務 API](17-tasks.md) 查詢狀態；只有任務為 `completed` 時，才讀取摘要或檢索本次匯入的內容。

**HTTP API**

```
POST /api/v1/resources
Content-Type: application/json
```

```bash
# 從 URL 新增資源
curl -X POST http://localhost:1933/api/v1/resources \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "path": "https://example.com/guide.md",
    "reason": "User guide documentation"
  }'

# 匯入並定時同步 HTTPS 私有 Git 倉庫
curl -X POST http://localhost:1933/api/v1/resources \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "path": "https://git.example.com/team/private-repo.git",
    "to": "viking://resources/private-repo",
    "watch_interval": 60,
    "args": {
      "branch": "main",
      "auth_config": {
        "username": "oauth2",
        "token": "replace-with-your-token"
      }
    }
  }'

# 新增資源但只生成向量，不走 VLM 語義理解
curl -X POST http://localhost:1933/api/v1/resources \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "path": "https://example.com/guide.md",
    "to": "viking://resources/guide",
    "processing_mode": "vectors_only"
  }'

# 遞迴抓取網頁：從入口頁沿同域連結展開，depth 控制層數，max_pages 限制頁數
curl -X POST http://localhost:1933/api/v1/resources \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "path": "https://docs.openviking.ai/zh/getting-started/01-introduction",
    "args": { "depth": 1, "max_pages": 10 }
  }'

# 從本地檔案新增（需先使用 temp_upload 上傳）
TEMP_FILE_ID=$(
  curl -s -X POST http://localhost:1933/api/v1/resources/temp_upload \
    -H "X-API-Key: your-key" \
    -F "file=@./documents/guide.md" \
  | jq -r '.result.temp_file_id'
)

curl -X POST http://localhost:1933/api/v1/resources \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d "{
    \"temp_file_id\": \"$TEMP_FILE_ID\",
    \"to\": \"viking://resources/guide.md\",
    \"reason\": \"User guide\"
  }"

# 新增到當前使用者私有資源根
curl -X POST http://localhost:1933/api/v1/resources \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d "{
    \"temp_file_id\": \"$TEMP_FILE_ID\",
    \"parent\": \"viking://~/resources/docs\",
    \"create_parent\": true
  }"

# 匯入時設定檢索標籤；標籤隨本次生成的向量記錄寫入，可用於 search/find 過濾
curl -X POST http://localhost:1933/api/v1/resources \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d "{
    \"temp_file_id\": \"$TEMP_FILE_ID\",
    \"to\": \"viking://resources/tagged-guide.md\",
    \"tags\": [\"team=search\", \"env=test\"],
    \"tag_mode\": \"replace\"
  }"
```

**Python SDK**

```python
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(url="http://localhost:1933", api_key="your-key")
client.initialize()

## 添加本地文件
result = client.add_resource(
    path="./documents/guide.md",
    options={"reason": "User guide documentation"},
)
print(f"Task ID: {result['task_id']}")

## 正常解析並轉換為 Markdown，但每個文件正文不拆分
result = client.add_resource(
    path="./documents",
    options={"args": {"parse_mode": "no_split"}},
)

## 從 URL 新增到指定位置
result = client.add_resource(
    path="https://example.com/api-docs.md",
    to="viking://resources/external/api-docs.md",
    options={"reason": "External API docs"},
)

## 遞迴抓取網頁（同域 BFS，depth 層數、max_pages 頁數上限）
result = client.add_resource(
    path="https://docs.openviking.ai/zh/getting-started/01-introduction",
    options={
        "args": {"depth": 1, "max_pages": 10},
    },
)

## 遞迴抓取並按路徑字首過濾，同時下載頁面中的檔案連結
result = client.add_resource(
    path="https://docs.openviking.ai/",
    options={
        "args": {
            "depth": 2,
            "max_pages": 50,
            "include_paths": ["/zh/"],
            "exclude_paths": ["/changelog"],
            "skip_download_links": False,
        },
    },
)

## 新增到當前使用者私有資源根
result = client.add_resource(
    path="./documents/guide.md",
    parent="viking://~/resources/docs",
    options={
        "create_parent": True,
    },
)

## 查詢最近一次匯入任務；狀態為 completed 後再使用處理結果
print(client.get_task(result["task_id"]))

## 為可重複讀取的 URL 開啟定時更新
client.add_resource(
    path="https://example.com/guide.md",
    to="viking://resources/guide.md",
    options={
        "watch_interval": 60,  # 每60分鐘更新一次
    },
)
```

**TypeScript SDK**

```typescript
const task = await client.addResource("https://example.com/docs", {
  to: "viking://resources/docs/",
  args: { parse_mode: "no_split" },
});
console.log(task.task_id);
```

**Go SDK**

```go
result, err := client.AddResource(ctx, "./documents/guide.md", &openviking.AddResourceOptions{
    Reason: "User guide documentation",
    Args:   map[string]any{"parse_mode": "no_split"},
})
if err != nil {
    return err
}
fmt.Println(result["task_id"])
```

**CLI**

```bash
# 添加本地文件
ov add-resource ./documents/guide.md --reason "User guide"

# 正常解析，每個源文件只生成一個 Markdown 正文
ov add-resource ./documents --args parse_mode:no_split

# 從 URL 新增
ov add-resource https://example.com/guide.md --to viking://resources/guide.md

# 遞迴抓取網頁：預設只抓入口頁，depth>0 才沿同域連結展開
ov add-resource "https://docs.openviking.ai/zh/getting-started/01-introduction" \
  --args="depth:1,max_pages:10"

# 遞迴抓取並按路徑字首過濾（只抓 /zh/，排除 changelog）
ov add-resource "https://docs.openviking.ai/" \
  --args='{"depth":2,"max_pages":50,"include_paths":["/zh/"],"exclude_paths":["/changelog"]}'

# 預設跳過頁面裡的下載連結；如需一併下載 PDF/TXT/MD 等，顯式關閉跳過
ov add-resource "https://example.com/docs" \
  --args="depth:1,max_pages:20,skip_download_links:false"

# 使用提交時返回的 task_id 查詢進度
ov task status TASK_ID

# 開啟定時更新（每60分鐘檢測一次）
ov add-resource https://github.com/example/repo.git --to viking://resources/my_repo --watch-interval 60

# 開啟定時更新並自動繫結本次匯入生成的 URI
ov add-resource https://github.com/example/repo.git --watch-interval 60

# 通過 PATCH /api/v1/watches/{task_id} 提交 {"is_active": false} 暫停 Watch。
# 原生匯入也可通過 --watch-interval 0 暫停目標上唯一可訪問的 Watch。
# 一次性 Connector 匯入不會影響已有 Watch。

# 新增到指定父目錄（父目錄必須存在）
ov add-resource ./documents/guide.md --parent viking://resources/docs

# 新增到當前使用者私有資源根
ov add-resource ./documents/guide.md --parent viking://~/resources/docs

# 新增到指定 peer 的私有資源根
ov add-resource ./documents/guide.md \
  --parent viking://user/alice/peers/web-visitor-alice/resources/docs

# 新增到指定父目錄（父目錄不存在時自動建立）
ov add-resource ./documents/guide.md -p viking://resources/docs/2026/05/07
# 或使用完整引數名
ov add-resource ./documents/guide.md --parent-auto-create viking://resources/docs/2026/05/07

# 使用路徑變數配合自動建立父目錄
ov add-resource ./documents/guide.md -p viking://resources/docs/{calendar:today}
```

#### 4. 響應示例

**HTTP API 響應（預設非同步模式）**

```json
{
  "status": "ok",
  "result": {
    "status": "accepted",
    "root_uri": "viking://resources/guide",
    "task_id": "uuid-xxx"
  }
}
```

使用返回的 `task_id` 輪詢 `/api/v1/tasks/{task_id}` 可檢視佇列完成情況。對於 `wait=false` 的 Git 倉庫來源，同一個端點會跟蹤完整後臺匯入，任務完成後的 `result` 會包含完整匯入結果，包括 `queue_status`。

**CLI 響應 (預設表格格式)**

```
Note: Resource is being processed in the background.
Use 'ov task status <task_id>' to check progress, or 'ov task list' to see all tasks.
status       accepted
root_uri     viking://resources/01-overview
task_id      uuid-xxx
```

**CLI 響應 (JSON 格式，使用 -o json)**

```json
{
  "status": "accepted",
  "root_uri": "viking://resources/01-overview",
  "task_id": "uuid-xxx"
}
```

**欄位說明**

| 欄位 | 型別 | 說明 |
|------|------|------|
| `status` | string | 處理狀態：`accepted` 表示已入隊，`success` 表示成功，`error` 表示失敗 |
| `root_uri` | string | 資源在 OpenViking 中的最終 URI |
| `task_id` | string | （可選，僅當 `wait=false` 時）可輪詢 `/api/v1/tasks/{task_id}` 的任務 ID。非 Git 匯入用於佇列跟蹤；Git 倉庫匯入用於完整後臺匯入跟蹤。 |
| `temp_uri` | string | 匯入過程中生成的臨時 URI |
| `source_path` | string | 原始原始檔路徑或 URL |
| `meta` | object | 資源解析過程中的後設資料（如檔案型別、大小等） |
| `errors` | array | 處理過程中的錯誤列表 |
| `warnings` | array | （可選）處理過程中的警告列表（僅在 `strict=False` 時可能出現） |
| `queue_status` | object | （可選，僅當 `wait=true` 時）佇列處理狀態，包含 `pending`、`processing`、`completed` 計數 |
| `memory_linking` | object | （可選，僅當 `reason` 觸發記憶生成時）本次資源 URI 與使用者記憶的關聯結果 |

**完成後的資源新增任務結果**

對於 `wait=false` 的 Git 倉庫來源，後臺任務的 `task_type="add_resource"`，`resource_id` 等於返回的 `root_uri`。執行中的任務記錄可能包含 `stage`。輪詢 `/api/v1/tasks/{task_id}` 直到任務完成。完成後，任務內層的 `result` 會包含最終佇列彙總和 `context_count`：

```json
{
  "status": "ok",
  "result": {
    "task_id": "uuid-xxx",
    "task_type": "add_resource",
    "status": "completed",
    "resource_id": "viking://resources/guide",
    "result": {
      "status": "success",
      "root_uri": "viking://resources/guide",
      "queue_status": {
        "Embedding": {
          "processed": 11,
          "requeue_count": 0,
          "error_count": 0,
          "errors": []
        }
      },
      "context_count": 11
    }
  }
}
```

`context_count` 是本次上傳任務成功生成並完成索引的上下文數量。每條上下文對應的嵌入記錄成功寫入後，計數增加一次。該值不是 `root_uri` 下已有上下文的總數。如果伺服器在任務持久化最終指標前重啟，該欄位會被省略，以避免返回不完整的計數。

---

<a id="watch-management監控任務管理"></a>

<a id="add_skill"></a>

### temp_upload

上傳臨時檔案，用於後續通過 [add_resource](#add-resource) 或 [add_skill](04-skills.md#add-skill) 匯入本地檔案。

#### 1. API 實現介紹

此介面用於把本地檔案上傳到服務端託管的臨時儲存中，返回 `temp_file_id` 供後續 API 使用。這是一個輔助介面，通常不直接呼叫，而是通過 SDK 或 CLI 自動使用。

**處理流程**：
1. 接收上傳的檔案
2. 根據 `upload_mode` 選擇臨時上傳後端
3. 儲存檔案並記錄原始檔名
4. 返回臨時檔案 ID

**程式碼入口**：
- `openviking/server/routers/resources.py:temp_upload` - HTTP 路由
- `openviking/service/resource_service.py` - 服務實現

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| file | UploadFile | 是 | - | 上傳的檔案（multipart/form-data） |
| telemetry | bool | 否 | False | 是否返回遙測資料 |
| upload_mode | string | 否 | `"local"` | 臨時上傳模式。`local` 保持現有單機行為；`shared` 將檔案上傳到共享臨時儲存，適用於分散式部署。 |

說明：

- 預設值是 `local`，所以現有客戶端在不改動的情況下仍保持原有行為。
- 只有在你明確需要分散式共享臨時上傳時，才應顯式使用 `upload_mode=shared`。
- `shared` 模式下返回的 `temp_file_id` 形如 `shared_<upload_id>`；同一 account 在檔案保留期間可以重複消費。
- 新的 shared 上傳會建立內部目錄 `viking://upload/<created_at_ms>-<uuid>/`，目錄內包含 `content` 和 `meta`。目錄名中的 13 位 Unix 毫秒時間戳即上傳建立時間；`meta` 最後寫入，代表上傳已完整完成。這些物件不屬於普通檔案系統瀏覽空間。
- shared 上傳會保留 `server.temp_upload.ttl_seconds` 指定的時長（預設 12 小時）。每次新的 shared 上傳會對內部上傳根目錄執行一次列舉，從每個一級上傳目錄名解析建立時間戳，並遞迴刪除過期目錄，不依賴檔案系統修改時間。

#### 3. 使用示例

**HTTP API**

```
POST /api/v1/resources/temp_upload
Content-Type: multipart/form-data
```

```bash
curl -X POST http://localhost:1933/api/v1/resources/temp_upload \
  -H "X-API-Key: your-key" \
  -F "file=@./documents/guide.md"
```

分散式 / shared 上傳：

```bash
curl -X POST http://localhost:1933/api/v1/resources/temp_upload \
  -H "X-API-Key: your-key" \
  -F "file=@./documents/guide.md" \
  -F "upload_mode=shared"
```

**Python SDK**

Python SDK 中的 `add_resource`、`add_skill` 等介面會自動處理本地檔案上傳，無需手動呼叫此介面。在 Python HTTP client 模式下，如果要啟用分散式 shared 臨時上傳，可以在 `ovcli.conf` 中設定 `upload.mode = "shared"`。

**Go SDK**

`client.AddResource`、`client.AddSkill`、`client.ImportOVPack` 和
`client.RestoreOVPack` 會為本地檔案自動呼叫 `temp_upload`。如需 shared 臨時上傳，設定
`openviking.Config{UploadMode: "shared"}`。

**CLI**

CLI 命令也會自動處理本地檔案上傳，無需手動呼叫此介面。

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "temp_file_id": "upload_abc123def456.md"
  },
  "telemetry": {
    "operation_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

shared 模式的響應示例：

```json
{
  "status": "ok",
  "result": {
    "temp_file_id": "shared_7f3c1b8d4f2e4b1bb0f6e8b2d9a4c123"
  }
}
```

---

### upload_limits

返回伺服器的上傳限制（`server.upload`），讓客戶端在上傳前先檢查檔案。

#### 1. API 實現介紹

Web Studio、各 SDK 與 CLI 會讀取這些限制，而不是寫死在程式中。服務端會強制執行相同的數值：[temp_upload](#temp-upload) 會拒絕大於 `max_file_bytes` 的檔案。

**程式碼入口**：
- `openviking/server/routers/uploads.py:get_upload_limits` - HTTP 路由
- `openviking/server/config.py:UploadConfig` - 設定（`ov.conf` 中的 `server.upload`）

#### 2. 介面和引數說明

此介面沒有引數。

**響應欄位**

| 欄位 | 型別 | 說明 |
|------|------|------|
| max_file_bytes | int | 單一檔案的大小上限 |
| max_session_bytes | int | 單次上傳（例如一個資料夾）的總大小上限 |
| max_files | int | 單次上傳的檔案數量上限 |
| part_size_bytes | int | 分片上傳時客戶端使用的分片大小 |

#### 3. 使用示例

**HTTP API**

```
GET /api/v1/uploads/limits
```

```bash
curl http://localhost:1933/api/v1/uploads/limits \
  -H "X-API-Key: your-key"
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "max_file_bytes": 2147483648,
    "max_session_bytes": 5368709120,
    "max_files": 10000,
    "part_size_bytes": 8388608
  }
}
```

---

### upload_sessions

把一個大檔案，或整個資料夾（不需壓縮），按檔案切成編號的分片上傳。分片可以重送、中斷的上傳可以續傳，客戶端與服務端都不會把整個檔案載入記憶體。完成工作階段後會返回 `temp_file_id`，可像其他臨時上傳一樣傳給 [add_resource](#add-resource)；資料夾工作階段的匯入結果與對應的 zip 上傳完全相同。

Python SDK、Go SDK、TypeScript SDK（Node.js）、`ov add-resource` 與 Web Studio 會自動使用工作階段，伺服器不支援時會退回 [temp_upload](#temp-upload)。

#### 1. API 實現介紹

| 方法 | 路徑 | 用途 |
|------|------|------|
| POST | `/api/v1/uploads` | 為一個檔案或一個資料夾建立工作階段 |
| PUT | `/api/v1/uploads/{upload_id}/files/{file_index}/parts/{part_number}` | 以原始請求主體儲存某檔案的一個分片（從 1 開始編號） |
| GET | `/api/v1/uploads/{upload_id}` | 查詢已收到的分片，用於續傳 |
| POST | `/api/v1/uploads/{upload_id}/complete` | 組裝所有分片並返回 `temp_file_id` |
| DELETE | `/api/v1/uploads/{upload_id}` | 中止並丟棄工作階段 |

**程式碼入口**：
- `openviking/server/routers/uploads.py` - HTTP 路由
- `openviking/server/upload_sessions.py` - 工作階段儲存

**限制與規則**：
- 每個檔案不得超過 `server.upload.max_file_bytes`，總大小不得超過 `max_session_bytes`，檔案數不得超過 `max_files`（見 [upload_limits](#upload-limits)）；超過限制的上傳或分片會返回 HTTP 413。
- 除了每個檔案的最後一個分片外，每個分片都必須剛好是 `part_size_bytes`（建立工作階段時返回）；最後一個分片為剩餘部分。空檔案沒有分片。
- 路徑必須是相對路徑、使用正斜線，並在建立時檢查：絕對路徑、`..`、磁碟代號、NUL、空白或 `.` 路徑段，以及互相衝突的路徑（包括大小寫不同或同時作為檔案與資料夾）都會被拒絕並返回 HTTP 400。
- 工作階段屬於建立它的 account 與 user，並在 `server.temp_upload.ttl_seconds` 後過期。
- 分片暫存在接收請求的伺服器磁碟上，因此工作階段需要 `server.temp_upload.default_mode` 為 `"local"`。在 `shared` 模式下，`POST /api/v1/uploads` 會返回 HTTP 409，客戶端應改用 `temp_upload`。

#### 2. 介面和引數說明

**建立工作階段的請求主體**

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| kind | string | 是 | `"file"` 或 `"directory"` |
| name | string | 是 | 檔名或資料夾名稱（作為 `source_name`），必須是單一路徑段 |
| files | array | 是 | `[{"path": "...", "size": <bytes>}]`；`kind="file"` 時只能有一個項目，且 path 必須等於 `name` |

**上傳分片**：以 `Content-Type: application/octet-stream` 將位元組作為原始請求主體送出。重送同一分片會覆蓋原內容。

#### 3. 使用示例

**HTTP API**

```bash
# 1. 為包含一個 10 MiB 檔案與一個小檔案的資料夾建立工作階段
curl -X POST http://localhost:1933/api/v1/uploads \
  -H "X-API-Key: your-key" -H "Content-Type: application/json" \
  -d '{"kind": "directory", "name": "docs", "files": [{"path": "big.pdf", "size": 10485760}, {"path": "notes/a.md", "size": 120}]}'

# 2. 逐一送出分片（檔案 0 有兩個分片，檔案 1 有一個）
curl -X PUT http://localhost:1933/api/v1/uploads/9f1c2e7a/files/0/parts/1 \
  -H "X-API-Key: your-key" -H "Content-Type: application/octet-stream" \
  --data-binary @part-0-1.bin
curl -X PUT http://localhost:1933/api/v1/uploads/9f1c2e7a/files/0/parts/2 \
  -H "X-API-Key: your-key" -H "Content-Type: application/octet-stream" \
  --data-binary @part-0-2.bin
curl -X PUT http://localhost:1933/api/v1/uploads/9f1c2e7a/files/1/parts/1 \
  -H "X-API-Key: your-key" -H "Content-Type: application/octet-stream" \
  --data-binary @docs/notes/a.md

# 3. 中斷後，查詢已收到的分片，只補送缺少的部分
curl http://localhost:1933/api/v1/uploads/9f1c2e7a \
  -H "X-API-Key: your-key"

# 4. 完成工作階段，再把 temp_file_id 傳給 add_resource
curl -X POST http://localhost:1933/api/v1/uploads/9f1c2e7a/complete \
  -H "X-API-Key: your-key"

# 若要放棄，則中止工作階段
curl -X DELETE http://localhost:1933/api/v1/uploads/9f1c2e7a \
  -H "X-API-Key: your-key"
```

**響應示例**（建立）

```json
{
  "status": "ok",
  "result": {
    "upload_id": "9f1c2e7a",
    "part_size_bytes": 8388608,
    "expires_at": 1791370000.0,
    "files": [
      {"index": 0, "path": "big.pdf", "size": 10485760, "total_parts": 2},
      {"index": 1, "path": "notes/a.md", "size": 120, "total_parts": 1}
    ]
  }
}
```

**響應示例**（完成）

```json
{
  "status": "ok",
  "result": {
    "temp_file_id": "session_9f1c2e7a"
  }
}
```

---

## 相關文件

- [檔案系統](03-filesystem.md) - 檔案和目錄操作
- [技能](04-skills.md) - 技能管理 API
- [檢索](06-retrieval.md) - 搜尋和上下文獲取
- [ovpack 指南](../guides/09-ovpack.md) - ovpack 匯入匯出詳細說明
- [OpenViking Assets](../guides/18-openviking-assets.md) - 宣告式資源集合協議和執行指南
