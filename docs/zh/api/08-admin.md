# 多租戶

Admin API 用於多租戶環境下的帳戶、使用者和使用者組管理。包括工作區（account）的建立與刪除、使用者註冊與移除、使用者組成員、角色變更、API Key 重新生成。

該 API 適用於 `api_key` 和 `trusted` 兩種模式下的管理鏈路：
- 在 `api_key` 模式下，角色始終從 API Key 推導。
- 在 `trusted` 模式下，普通請求仍然不依賴 user key 註冊流程；當請求 `/api/v1/admin/*` 並攜帶已配置的 `root_api_key` 時，受信上游會按 ROOT 授權。

對於 `/api/v1/admin/*`，`trusted` 模式允許不攜帶顯式身份頭；也允許攜帶與 URL 中 account/user 匹配的目標身份頭。只要部署級 `root_api_key` 校驗通過，這類請求都會按 ROOT 處理。普通 trusted 資料 API 的身份和角色仍然來自 `X-OpenViking-Account` + `X-OpenViking-User`。

## 角色與許可權

| 角色 | 說明 |
|------|------|
| ROOT | 系統管理員，擁有全部許可權 |
| ADMIN | 工作區管理員，管理本 account 內的使用者 |
| USER | 普通使用者 |

| 操作 | ROOT | ADMIN | USER |
|------|------|-------|------|
| 建立/刪除工作區 | Y | N | N |
| 列出工作區 | Y | N | N |
| 註冊/移除使用者 | Y | Y（本 account） | N |
| 管理使用者組和成員 | Y | Y（本 account） | N |
| 列出 agents（已廢棄，返回空列表） | Y | Y（本 account） | N |
| 重新生成 User Key（僅 API Key 模式） | Y | Y（本 account） | N |
| 將使用者提升為 ADMIN | Y | Y（本 account） | N |

## CLI `--sudo` 選項

使用 `ov` CLI 執行需要 ROOT 許可權的管理操作時，可以使用 `--sudo` 選項。該選項會使用配置檔案 `~/.openviking/ovcli.conf` 中的 `root_api_key` 而非普通 `api_key`。

### 配置要求

在 `~/.openviking/ovcli.conf` 中配置 `root_api_key`：

```json
{
  "url": "http://localhost:1933",
  "api_key": "alice-user-key",
  "root_api_key": "your-root-api-key"
}
```

### 支持 `--sudo` 的命令

- `ov --sudo admin` - 帳戶和使用者管理
- `ov --sudo system` - 系統工具命令
- `ov --sudo reindex` - 重建索引
- `ov --sudo admin migrate` - 舊 Session 遷移和清理
- `ov --sudo task status/list` - 查詢 root/system 後臺任務，例如遷移任務

### 使用限制

- `--sudo` 僅適用於上面的命令，用於普通資料命令會報錯
- 必須配置 `root_api_key` 才能使用 `--sudo`

## 使用者組

使用者組屬於單個 account，用於通過一個 ACL principal 授權多個使用者。`group_id` 由呼叫者建立時指定，使用與 `user_id` 相同的識別符號規則，是 account 內唯一且穩定的標識；不存在單獨的組名。組內只能加入當前 account 已存在的使用者，不支援巢狀組。

成員關係由服務端加入每次請求的 `RequestContext.group_ids`。新增或移除成員從下一次請求開始生效，不重寫資源 ACL 或 context 記錄。使用者被刪除時會自動退出所有組；使用者組必須為空才能刪除。

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/v1/admin/accounts/{account_id}/groups` | 建立空組，請求體為 `{"group_id":"engineering"}` |
| GET | `/api/v1/admin/accounts/{account_id}/groups` | 列出組 |
| DELETE | `/api/v1/admin/accounts/{account_id}/groups/{group_id}` | 刪除空組 |
| GET | `/api/v1/admin/accounts/{account_id}/groups/{group_id}/members` | 列出成員 |
| PUT | `/api/v1/admin/accounts/{account_id}/groups/{group_id}/members/{user_id}` | 冪等新增成員；重複呼叫返回 `added=true` |
| DELETE | `/api/v1/admin/accounts/{account_id}/groups/{group_id}/members/{user_id}` | 移除成員；重複呼叫返回 `removed=false` |

```bash
ov --sudo admin create-group acme engineering
ov --sudo admin add-group-member acme engineering alice
ov acl grant viking://resources/project-a \
  --principal group:engineering --level read
ov --sudo admin remove-group-member acme engineering alice
ov --sudo admin delete-group acme engineering
```

Python SDK 提供對應的 `admin_create_group`、`admin_list_groups`、`admin_list_group_members`、`admin_add_group_member`、`admin_remove_group_member` 和 `admin_delete_group`；Go SDK 使用相同名稱的 PascalCase 方法。

## API 參考

### get_agent_evolution_status

返回呼叫方所屬 account 的 Agent 進化即時狀態。ROOT 操作已配置的預設
account，ADMIN 僅操作自己所屬的 account。

**HTTP API**

```
GET /api/v1/admin/agent-evolution
```

```bash
curl http://localhost:1933/api/v1/admin/agent-evolution \
  -H "X-API-Key: <root-key>"
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "enabled": false,
    "account_id": "default"
  }
}
```

`enabled` 依次解析 Account 執行時覆蓋、Cluster 執行時覆蓋，以及
`server.agent_evolution.enabled` 提供的啟動值。

現有介面作為 deprecated 相容介面卡保留：

```http
PUT /api/v1/admin/agent-evolution
Content-Type: application/json

{"enabled": true}
```

### account_settings

該介面已 deprecated。ROOT 可管理任意 account，ADMIN 僅可管理自己所屬的 account。
介面保留原有 ACL 與 Agent Evolution 請求和響應語義：

```http
GET /api/v1/admin/accounts/{account_id}/settings
PATCH /api/v1/admin/accounts/{account_id}/settings
Content-Type: application/json

{
  "agent_evolution": {"enabled": true},
  "acl": {"enabled": true}
}
```

欄位缺失或為 `null` 都表示不修改；傳入物件則整體設定對應存量配置段，
空 ACL 物件表示 `enabled=false`。新接入方應使用下述 configuration 介面。

`acl.enabled` 預設為 `false`。關閉時，共享資源按原有規則完全共享，不執行 ACL
鑑權。開啟後，帳號內新增共享資源會寫入 ACL，並對帶 ACL 的共享資源執行鑑權；
已有且未設定 ACL 的內容不會遷移或改權。重新關閉後，已有 ACL 也不再參與訪問判斷。

```bash
ov --sudo admin set-account-settings acme --acl-enabled true
```

覆蓋已有配置前，核心會先備份到
`/local/{account_id}/_system/setting.backup.json`。

### account_memory_templates

ROOT 可管理任意 Account；ADMIN 僅可管理自己 Account 的模板；普通 User 無權呼叫。
許可權按管理員角色判斷，不按 User 是否叫 `default` 判斷。

| 方法 | 路徑 | 用途 |
|------|------|------|
| GET | `/api/v1/admin/accounts/{account_id}/memory-templates` | 列出六類開放模板、完整預設值及生效值 |
| GET | `/api/v1/admin/accounts/{account_id}/memory-templates/{memory_type}` | 查詢單個模板 |
| PUT | `/api/v1/admin/accounts/{account_id}/memory-templates/{memory_type}` | 補齊併發布單個模板 |
| DELETE | `/api/v1/admin/accounts/{account_id}/memory-templates/{memory_type}` | 刪除該模板覆蓋，恢復部署預設值 |

保留已有自定義內容並更新模板時，按以下步驟操作：

1. GET 目標模板，取出 `effective` 物件。
2. 修改允許編輯的說明或 `content_template`，再 PUT 整個物件。省略的配置會恢復部署預設值。
3. 核對返回的 `status` 和 `effective`。後續開始的抽取使用新模板，已有記憶不會立即重寫。

需要恢復該型別的部署預設值時，呼叫 DELETE。

核心接收原有 Memory YAML 結構對應的 JSON 物件，並在介面層強制校驗以下白名單。
僅開放下列六類別範本；Experience、Cases、Trajectories 等其他型別不開放查詢或編輯，
不支援通過介面新增、刪除或重新命名 Memory Type。DELETE 僅移除自定義覆蓋，不刪除模板型別。

| 模板 | 可編輯項 | 用途 |
|------|----------|------|
| `profile` | `description`；`fields.content.description` | 穩定身份、背景和工作方式的抽取說明；正文內容、語言、Markdown 結構、長度和更新時間要求 |
| `events` | `description`；`fields.event_name.description`、`fields.summary.description`；`content_template` | 事件範圍、原子性與排除項；名稱語言、粒度和格式；摘要事實、日期和語言；Summary、時間、ChatLog 的標題、順序和展示方式 |
| `preferences` | `description`；`fields.topic.description`、`fields.content.description` | 偏好、習慣、反感及與 Profile/Event 的邊界；主題粒度、語言和命名；正文語義、條目和 Markdown 要求 |
| `entities` | `description`；`fields.category.description`、`fields.name.description`、`fields.content.description` | 實體與關係範圍；分類法、語言和粒度；實體命名；卡片事實、章節、語言和長度 |
| `soul` | `description`；`fields.core_truths.description`、`fields.boundaries.description`、`fields.vibe.description`、`fields.continuity.description`；`content_template` | 核心原則、邊界、氣質和連續性的抽取表達；四個欄位的標題、順序和固定文案 |
| `identity` | `description`；`fields.creature.description`、`fields.name.description`、`fields.vibe.description`、`fields.avatar.description`、`fields.emoji.description`、`fields.introduction.description`；`content_template` | 身份資訊範圍；身份、名稱、氣質、頭像、Emoji、自我介紹的欄位要求；正文標籤、順序和固定文案 |

表中 `fields.<name>.description` 表示在 `fields` 陣列中按 `name` 定位並修改
`description`，不是替換整個欄位。JSON 屬性名統一小寫（`description`，不是
`Description`）。Profile 的 `fields.content` 僅開放其 description，不開放欄位本身。

除白名單說明文字和三個正文模板外，所有配置均鎖定為部署預設值，包括：
`memory_type`、`enabled`、`operation_mode`、`stage`、`peer_enabled`、
`directory`、`filename_template`、所有欄位的名稱/型別/`merge_op`/`init_value`、
`embedding_template` 和 `overview_template`，以及未開放的欄位說明。
例如 Profile 保留 `profile.md` 和 content 的 `merge_op=patch`；Events 保留
`add_only` 以及 `goal/ranges` 的說明；Identity 的 Name immutable 規則不變。
Profile、Preferences、Entities 不開放 `content_template`。
改寫 topic/category/name/event_name 的生成說明仍可能間接影響未來的目錄或檔名，
但不允許修改目錄/檔名模板本身。

例如，僅修改型別說明：

```bash
curl -X PUT "$OV_ENDPOINT/api/v1/admin/accounts/acme/memory-templates/profile" \
  -H "X-API-Key: $OV_ADMIN_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"description":"只記住業務相關事實，用簡潔的中文描述。"}'
```

PUT 從**部署預設模板**補齊未傳入的配置，不從上一次 Account 自定義值補齊，最終儲存
**完整 YAML 模板**。`fields` 按已有欄位名合併，只覆蓋白名單允許的說明文字，
未傳入的欄位和屬性全部保留預設值；不能新增、刪除或重新命名欄位，提交空列表不會刪除欄位。
完整 GET `effective` 物件可以回傳：鎖定欄位值與預設值相同則接受，任何鎖定值變更、
未知配置項、未知欄位或重複欄位名均返回 `INVALID_ARGUMENT`，當前生效檔案不變。
若僅調整一個 description 且需保留其他自定義內容，應先 GET，修改 `effective` 物件後
整體 PUT。補齊並校驗後的完整配置若與部署預設值完全一致（不含釋出時間後設資料），
PUT 會移除該型別的自定義覆蓋，返回 `status=system_default`、`updated_at=null`。
這包括提交空物件、原樣提交預設表單，以及在編輯頁逐項恢復預設後儲存；只要還有任意配置
不同，就繼續返回 `custom`。比較不忽略說明或正文中的空格、換行等內容差異。
移除覆蓋後，後續抽取跟隨部署預設模板；此前已取得的抽取快照不變。
DELETE 始終移除該型別的覆蓋；重複 PUT 預設配置或 DELETE 都是冪等的。

返回包含 `memory_type`、`status`（`system_default` / `custom`）、
`updated_at`（UTC 釋出時間，預設狀態為 null），以及完整的 `defaults` / `effective`。
物件使用 YAML 欄位名，例如 `fields[].type`。列表介面返回 `result.account_id` 和
`result.templates`；單模板操作返回 `result.account_id` 及上述模板結果。

::: details 釋出、儲存與併發抽取的處理方式

按 Account、按模板獨立儲存：

```text
/local/{account_id}/_system/memory_templates/
  profile.yaml
  preferences.yaml
  events.yaml
  ...
```

僅釋出自定義時建立對應檔案。檔案包含完整 Schema 和內部 `_updated_at` 時間戳，
不再使用集中式 `memory_templates.json`。更新前備份至 `{type}.yaml.backup`。
讀寫經過 AGFS，沿用當前部署的加密和儲存配置，不能直接編輯加密後的底層檔案。
不修改 Account 的 `setting.json` 或 User 的 `user_config.json`。
個人版使用預設 Account；企業版使用指定 Account，核心不區分兩套檔案結構。

模板讀取不加鎖。釋出先在同目錄寫完唯一臨時檔案，再通過 AGFS 切換到正式路徑：
LocalFS 使用檔案重新命名，S3 使用完整物件複製替換目標後再刪除臨時物件，不先刪除目標。
讀者允許看到完整舊版或新版；首次釋出之前、恢復預設之後讀取部署預設值，不讀取臨時檔案。
這是單檔案釋出語義，不保證一次列表/Registry 讀取中的所有模板來自同一釋出時刻。
釋出與 DELETE 仍使用跨程序寫鎖；釋出鎖同時覆蓋正式路徑和臨時路徑。鎖衝突採用零等待嘗試和
協程退避，最多等待 10 秒，避免鎖等待佔滿執行後續 I/O 的預設執行緒池。
臨時寫入失敗不修改當前檔案；切換後清理失敗只記警告，不覆蓋回滾已釋出版本。
若切換返回錯誤，會核驗目標內容：確認已釋出則保留新版本；無法確認則返回錯誤且不盲目回滾，呼叫方可 GET 確認狀態。
取消等待鎖的請求會停止重試；已下發的 native 操作不能強行中斷，會完成收尾並釋放鎖後再傳播取消。
因此取消已開始釋出的請求不保證撤銷釋出。程序異常退出或清理失敗可能留下 `.tmp` 檔案，但讀取不會使用它們。

普通 Session 記憶抽取在篩選 Schema 和初始化記憶檔案之前讀取 Account 模板。
同一份 Registry 快照貫穿模型抽取、補丁合併和記憶檔案更新；釋出新模板不改變已開始
抽取的快照。流式更新直接比較當前記憶型別的 Schema 值（含渲染模式），不比較整個
Registry；無關型別變更不會觸發拆批。不同 Schema 分開合併、渲染；若這些組在補丁
合併前或合併後指向同一檔案，會在應用該合併批次的任何記憶操作前丟擲衝突。
此時需按當前模板和檔案內容重新抽取後再重試，不能直接重放舊 patch。
這是衝突提前報錯，不是自動 rebase，也不是整個 Commit 的原子事務；其他記憶型別
或 append-only 路徑可能已經完成寫入。排隊任務按**抽取開始時**取值，
不是按 HTTP Commit 受理時間取值。同一 Account 下符合記憶策略的 User/Peer 共用模板，
不同 Account 不串用，也不修改共享的部署 Registry。釋出或恢復預設不會主動重寫歷史
記憶，後續 Commit 可按生效規則更新已有記憶。

:::

白名單內提交的說明和正文模板必須是非空字串；單檔案序列化後不超過 1 MiB。
`description`（型別說明及 `fields[].description`）統一支援受限 Jinja，不因來自部署預設值或帳戶覆蓋而改變規則，不再記錄或檢查說明來源標誌。
僅開放已有上下文中的 `language`，不開放正文變數、`extract_context` 或任意物件。語法複用下節受限正文的條件、區域性變數、有界字面量迴圈、安全字串方法、白名單字串過濾器及測試；不支援任意呼叫。
例如已有 Schema 渲染上下文提供 `language=en` 時，<code v-pre>請使用 {{ language.upper() }}。</code> 會展開為 `請使用 EN。`，使用者修改文字不會讓變數停止展開。
渲染使用呼叫路徑傳入的語言，Python 和 JSON 協議均使用該上下文渲染欄位說明。缺失語言時保留原來的 undefined/空字串行為，可用 `language or '中文'` 提供回退；上下文值中的 Jinja 不會被遞迴執行。
越界的自定義表示式在儲存前拒絕，已儲存說明在抽取載入時重新校驗；部署說明渲染也受同樣限制，已有部署若使用白名單外語法，需要調整，不能憑來源繞過限制。
每條說明最多 2048 個 AST 節點，渲染結果最多 1 MiB。正文 `content_template` 的變數、原始碼大小及預設正文相容規則仍按下節處理。
每個可編輯 `description` 最多 50,000 個 Unicode 碼點，按提交的原文計數，包含空格、換行和模板樣式的文字，不按 UTF-8 位元組或渲染後的長度計數。各說明獨立計數，不合並計算；整個配置仍受 1 MiB 上限約束。超過上限返回 400，不修改當前配置。
釋出不呼叫 LLM。儲存錯誤或檔案損壞明確報錯，不偽裝成系統預設。這些介面暫無 SDK/CLI 封裝，讀取、釋出和恢復模板均使用 HTTP API。

#### content_template 的編輯與執行邊界

以下受限規則僅用於與當前部署預設正文不同的帳戶自定義正文。釋出和抽取載入時，
伺服器將完整 `content_template` 字串與自己載入的部署預設值比較；完全相同時，
沿用原部署渲染器及其過濾器、helper，不採信客戶端或持久化檔案中的“可信”標記。
因此，僅改 description、空 PUT、正文未變的 GET `effective` → PUT 都不要求遷移預設正文。
帳戶覆蓋仍可顯示 `status=custom`，但正文走繼承路徑。內建 Events YAML 及其原有日期表示式不變。

比較是精確字串比較，包含空白字元；修改過的正文即使以預設模板為基礎，也必須通過受限校驗。
部署預設值後續變更時，下次抽取載入會重新比較，舊帳戶檔案不會永久保留信任。
不再匹配且超出白名單的正文需重新發布或恢復預設後才能參與提取；已開始的提取仍保留原快照。

正文模板用於將已抽取/合併的欄位組織為 Markdown，不是抽取 Prompt。
允許修改標題、順序、固定文案，按條件顯示/隱藏欄位。不要求保留預設標題或輸出全部欄位；
但隱藏欄位不等於停止抽取/刪除該欄位，也不會刪除原始 Session 或系統儲存的欄位後設資料。
Events 的預設 embedding 模板引用正文，因此正文變化也可能影響後續檢索輸入。
路徑、檔名、欄位定義、merge_op（包括 Identity name 的 immutable）仍鎖定。

| 型別 | 正文中可引用的欄位 |
| --- | --- |
| events | event_name、goal、summary、ranges |
| soul | core_truths、boundaries、vibe、continuity |
| identity | name、creature、vibe、emoji、avatar、introduction |

`language` 屬於說明模板的變數，不屬於上述正文變數。
正文不要引用其他 Account/User、請求上下文或任意 Python 物件。
僅 Events 可呼叫以下 `extract_context` 只讀方法（位置引數）：

- `get_resource_event_content(ranges, summary)`：資源新增事件正文；非資源事件為空。
- `get_first_message_time_from_ranges(ranges)`：第一條來源訊息日期。
- `get_first_message_time_with_weekday_from_ranges(ranges)`：日期及星期。
- `get_event_content(ranges, summary[, ratio_threshold])`：按已有邏輯選擇 ChatLog/摘要；省略閾值為 0.2，顯式 0 表示存在原文時優先原文。
- `get_year(ranges)`、`get_month(ranges)`、`get_day(ranges)`：來源日期分量。

首個引數可使用統一語法白名單內的表示式，包括區域性變數、條件表示式及允許的過濾器鏈。
每次實際呼叫方法前，引數求值結果必須是普通字串，且與當前記憶原始 `ranges` 完全相等，或為空字串（不讀取來源訊息）。
例如 `ranges | default('') | trim` 在結果未改變時可用；也可先 `{% set selected = ranges %}`，再呼叫 `get_year(selected)`。
比較範圍時不做歸一化；缺失欄位本來就會傳入空字串。釋出時僅校驗語法，不執行方法；改變範圍或傳入非字串會在實際渲染時返回 `content_template: invalid_ranges`，在方法讀取訊息前拒絕，並停止該次記憶檔案寫入。
閾值只能為 0～1 的數字字面量。
允許去掉 ChatLog 或資源事件分支，但去掉後不再自動展示這些正文/資源連結；原始 Session 仍保留。

支持的 Jinja 子集：

- `if/elif/else`、比較/布林條件、`set` 區域性變數（不能覆蓋內建欄位、extract_context、loop）。
- `for` 遍歷模板中顯式寫出的列表/元組，最多 32 項；支援標題/欄位二元組和 `loop.index/index0/first/last/length`。不支援巢狀/遞迴迴圈、range() 或遍歷訊息/長字串。
- 字串方法：`.upper()`、`.lower()`、`.strip()`，均不接受位置引數或關鍵字引數。可用於字串欄位、區域性變數、字面量、Events 白名單方法返回的字串，並支援鏈式呼叫，例如 `summary.strip().upper()`。
- 方法語法與部署模板一致，但帳戶正文只開放上述少數方法；讀取屬性前先檢查接收者必須是普通字串，其他物件（包括字串子類）的同名方法/屬性不能借此被呼叫。也不允許只取出方法引用、儲存後再呼叫。
- 字串過濾器：`| upper`、`| lower`、`| trim`，分別等價於 `.upper()`、`.lower()`、`.strip()`。同樣只接受普通字串，不接受位置引數或關鍵字引數。支援鏈式呼叫及與方法混用，例如 `summary | trim | upper` 或 `summary.strip() | upper`。
- `default` 過濾器：支援無引數或一個字串字面量，例如 `| default` / `| default()` / `| default('N/A')`。只替換未定義值，不替換空字串或 `None`，與內建 Events 模板保持一致。接收者僅允許普通字串、`None` 或未定義值，不轉換任意物件；不支援第二個布林引數、關鍵字引數或展開／動態引數。空值回退使用 `summary or '待補充'` 或條件表示式。
- 其他過濾器仍不支援，包括 `| length`、`| d(...)`、`| attr(...)`。
- 測試：`defined`、`undefined`、`none`、`string`。
- 不支援模板匯入/繼承、宏、任意函式/物件屬性訪問、下標訪問、算術或字串倍增/拼接。不能注入系統保留的 `<!-- MEMORY_FIELDS ... -->` 後設資料。

模板 UTF-8 大小 ≤ 64 KiB，AST 節點 ≤ 2048，渲染正文 ≤ 1 MiB（不含系統追加後設資料）。
與部署預設值不同的 Account 正文在釋出時和抽取載入時驗證，執行時使用受限 Jinja 環境，只提供白名單欄位/方法。
內建 Events、Soul、Identity 正文也滿足受限語法；僅修改標題、末尾換行或 CRLF 換行後仍可校驗釋出。這些改動不會繞過校驗，也不會被標記為部署原樣正文。
受限路徑渲染失敗會報告錯誤並停止該次檔案寫入，不走舊的空正文 fallback。
原樣繼承的正文繼續使用部署渲染器，包括原有錯誤/fallback 語義，不受上述受限渲染器的原始碼、AST、正文輸出上限約束；
完整帳戶 YAML 仍受 1 MiB 上限約束。
這些保護不代替 Worker 的 CPU/記憶體配額，也不評估記憶效果或做前端 Markdown/HTML 安全過濾。
說明與受限正文複用語法沙箱，但可用變數及原始碼大小限制不同。

校驗失敗返回 `INVALID_ARGUMENT`，`error.details` 含 `field=description`、`fields.<name>.description` 或 `content_template`、受控 `reason` 和可用時的 `line`。
失敗不修改當前釋出配置。此前儲存的、結構有效但使用不支援 Jinja 的模板仍可讀取、重新發布或恢復預設；
不會繞過新規則繼續執行，抽取載入時提示修復。損壞 YAML 仍明確報錯。

示例：以下 `events` 的 PUT 請求體只展示事件名稱和摘要，不輸出 ChatLog：

```json
{"content_template": "# {{ event_name.strip() }}\n\n## 事件摘要\n{{ summary.strip() or '待補充' }}"}
```

示例：Soul 的分節展示：

```jinja
{% for title, text in [('核心價值', core_truths), ('邊界', boundaries), ('氣質', vibe), ('連續性', continuity)] %}
{% if text.strip() %}
## {{ title }}
{{ text.strip() }}
{% endif %}
{% endfor %}
```

### Runtime Configuration

ROOT 可管理 Cluster 配置和任意 Account 配置；ADMIN 只能管理所屬帳號的 Account 層。

```http
GET /api/v1/admin/configuration
PATCH /api/v1/admin/configuration

GET /api/v1/admin/accounts/{account_id}/configuration
PATCH /api/v1/admin/accounts/{account_id}/configuration
Content-Type: application/json

{"settings": {"agent_evolution": {"enabled": true}}}
```

`settings` 始終表示目標層的顯式設定值。PATCH 為三態語義：欄位缺失表示不修改，
`null` 表示刪除當前層配置，具體值表示更新。

當前 Cluster 執行時配置面僅包含 `agent_evolution`。Account 配置麵包含
`agent_evolution`、`github`、`acl`、`vlm` 和 `query_planner`，
這些配置均可動態修改。Account 的
`vlm`、`query_planner`、`embedding` 和 `vectordb` 僅 ROOT 可讀寫，ADMIN 的讀取
響應過濾這些配置，寫入請求在讀取配置前拒絕。每段已配置的 `vlm` 或
`query_planner` 都必須包含 `model` 和非空 `credentials` 陣列，`timeout` 可選。
`memory` 不在當前 API 範圍內。
`vectordb` 只能隨 Account 建立時的 `settings` 提交，建立後包括 ROOT 在內均不可
新增、修改或重置。Cluster 的 `embedding`、`vlm`、`query_planner`、
`memory`、儲存、解析器和檢索配置沒有宣告為執行時欄位，因此仍然只能
在啟動配置中修改。

Account `embedding` 和 `vectordb` 使用獨立白名單模型。Account 與 Cluster
配置分別釋出，向量配置解析器按業務規則應用 Cluster 預設值。模型服務的連線欄位
只允許出現在 `credentials` 中，陣列整體替換完整服務繫結，不能拼接 Cluster
連線或鑑權欄位。每組憑證必須獨立提供 `provider` 和必需的連線、鑑權引數；
憑證未設定 `model` 時可以使用有效外層 `model`。VectorDB 不開放本地路徑、
cuVS 調優和自定義介面卡引數。

存量 Account 可 PATCH 完整的模型憑證與部署繫結、重試、併發、故障回切和熔斷引數。
將 `max_retries` 等可選執行引數設為 `null`，會從 Account 配置刪除該值，
隨後由向量配置解析器應用 Cluster 預設值；已配置模型模式中的必需憑證不能刪除。
外層模型身份、模式、`dimension`、`input`、`query_param`、`document_param`、
`version`、`text_source` 和 `max_input_tokens` 為建立期欄位。
`credentials` 之外的 provider 欄位、`batch_size`、`encoding_format`、`extra_body`、
本地模型路徑、融合/影片引數和 `allow_metadata_override` 不在 Account API 範圍內。
每次更新都在持久化前聯合校驗有效 Embedding 和 VectorDB，失敗保留原配置。

顯式 `embedding: {}` 是合法配置，表示未宣告 Account 模型模式或執行策略。
作為 PATCH 提交時，`{}` 會與現有配置合併，不會清空已有值。未配置 Account
模型模式時使用 Cluster 模型繫結。顯式 Account VectorDB 配置會替換 Cluster
的連線與鑑權欄位，即使後端型別相同也不會拼接；僅支援 `http` 遠端後端。

```json
{"settings":{"embedding":{"dense":{"credentials":[{"provider":"openai","model":"compatible-deployment","api_base":"https://embedding.example/v1","api_key":"account-key"}]}}}}
```

查詢、佇列寫入、Reindex 和 OVPack 都使用目標 Account 配置，ROOT 也遵守此規則。
服務端點更新作用於後續 Embedding 呼叫，在途呼叫安全完成。呼叫方負責保證模型空間相容：
維度相同不能證明權重相同，本功能不會自動重建歷史向量。遠端集合、索引和授權由
外部控制面建立，執行失敗不會切換到其他 Account 或 Cluster 向量庫。

Account 與 Cluster 配置分別儲存。Agent Evolution 僅為相容舊行為保留已廢棄的
Cluster 整段回退。GitHub 和 ACL 不回退到 Cluster。

VLM 業務解析器在 Account 未配置 VLM 時使用 Cluster VLM。Account 已配置時，
模型身份、服務端點和憑證僅來自 Account，部分執行引數按業務規則使用 Cluster
配置。Account 設定 `timeout` 時覆蓋 Cluster 的值，未設定或重置後使用 Cluster
的值。Query Planner 的選擇順序為 Account `query_planner`、Account `vlm`、
Cluster `query_planner`、Cluster `vlm`；這是 VLM 業務規則，不是配置框架的隱式繼承。

PATCH 會先做結構校驗，再構造合併後的配置：未知路徑和執行時配置面之外的欄位會被拒絕。
物件遞迴合併，陣列整體替換；巢狀 null 只刪除對應葉子。刪除整個物件覆蓋需要在父路徑
傳 null，傳空物件仍表示顯式空物件。

兩個 GET 介面只返回目標作用域持久化的配置，不返回業務解析後的預設值。配置持久化後會釋出新配置並等待
匹配的程序內 Consumer；Consumer 失敗會記錄日誌但不會回滾已持久化的配置，因此介面成功只表示
配置層更新成功，不保證所有派生客戶端都已完成切換。配置儲存和過載行為見[執行時配置來源與過載行為](../guides/01-configuration.md#runtime-configuration-source)。

檔案儲存始終提交完整 `content` 和舊 `revision`。
草稿預覽（`source=file&dry_run=true`）可附帶 VLM/Embedding 表單 `settings`；
其他配置節通過完整檔案編輯。

檔案含美元符號、Windows `%VAR%` 引用或轉義的美元/百分號時，讀取和預覽返回 `form_readonly: true`，不返回模型表單資料，並拒絕表單修改。請使用檔案模式編輯原文，包括帶引號和未帶引號的環境變數引用。驗證沿用啟動時對原文展開環境變數的流程，儲存不會重新序列化文件。檔案校驗會應用 CLI 啟動引數覆蓋，與重啟時的處理一致。

#### 服務端重啟

僅 ROOT 可以重啟通過單 worker `openviking-server` CLI 啟動的程序。
多 worker 和嵌入式 ASGI 啟動模式不支援遠端重啟。

```http
POST /api/v1/admin/restart
Content-Type: application/json
X-API-Key: <root-api-key>

{"revision": "<已儲存檔案的版本>"}
```

`revision` 是必填的非空字串。通過
`GET /api/v1/admin/configuration?source=file` 獲取當前檔案版本和重啟能力；
`result.restart` 包含 `supported`、`instance_id` 和 `restarting`。
重啟介面不儲存配置。修改配置時，先通過
`PATCH /api/v1/admin/configuration?source=file` 提交 `content` 和舊 `revision`，
再將儲存響應中的新版本提交給重啟介面。

服務端接受重啟前會核對當前檔案版本並校驗配置。
版本過期或檔案無效返回 `INVALID_ARGUMENT`；啟動模式不支援或檔案不可讀返回
`FAILED_PRECONDITION`。這些檢查失敗時不會請求重啟。

接受請求後，在優雅關閉前返回 **HTTP 202**：

```json
{
  "status": "ok",
  "result": {
    "supported": true,
    "instance_id": "current-instance-id",
    "restarting": true
  }
}
```

CLI 等待現有請求結束，停止其管理的 Bot，再使用原直譯器、啟動引數、環境變數和
工作目錄替換當前程序。接受重啟後拒絕檔案儲存請求。HTTP 202 只表示請求已接受，
不代表服務已恢復；應輪詢檔案配置讀取介面，直到 `instance_id` 改變且
`restarting` 為 false。外部依賴仍可能阻止啟動。如果地址、埠或 ROOT 憑證發生
變化，需要先更新客戶端連線設定再輪詢。詳見[服務端配置](../configuration/01-server.md)。

CLI 在接受重啟前儲存當前程序啟動時實際載入的檔案原文，作為獨立的私有恢復備份
（0600，包含敏感配置）。新程序在配置載入、Bot 啟動、應用初始化或監聽埠時失敗，
會原子恢復此前執行的配置並重新啟動一次；恢復後的配置讀取響應中
`result.restart.rolled_back` 為 true，Studio 會提示已回滾。
應用初始化和埠繫結成功後刪除恢復備份，不對後續執行期故障自動回滾。
遠端重啟不能切換為多 worker；應通過部署平臺執行這種變更。

恢復備份與每次儲存生成的 `.studio.bak` 不同：後者僅保留上一次儲存前的檔案，
未必曾成功啟動。自動恢復只回滾配置檔案，不撤銷儲存或外部系統中的副作用，
也不處理啟動卡死、程序被強制終止或機器故障。若重啟後文件被外部修改，拒絕覆蓋；
若恢復後的配置仍無法啟動，不再重試，需要管理員在伺服器上恢復服務。

#### Account Configuration 介面參考

Account 配置通過建立介面的 `settings` 初始化，並通過 configuration 介面讀取和更新：

| 方法 | 路徑 | 許可權 | 返回值 |
| --- | --- | --- | --- |
| `POST` | `/api/v1/admin/accounts` | ROOT | 新 Account；可接受建立期 `settings` |
| `GET` | `/api/v1/admin/accounts/{account_id}/configuration` | ROOT；或目標 Account 的 ADMIN | 該 Account 顯式持久化的 `settings` |
| `PATCH` | `/api/v1/admin/accounts/{account_id}/configuration` | ROOT；或目標 Account 的 ADMIN | 合併後的顯式 `settings` |

`vlm`、`query_planner`、`embedding` 和 `vectordb` 是敏感基礎設施配置：只有 ROOT
可以建立、讀取或修改。ADMIN 對自己的 Account 呼叫 GET 時，響應會移除這四段；若
PATCH body 包含其中任一段，立即返回 `403 PERMISSION_DENIED`。ADMIN 也不能管理
其他 Account。所有結構或業務校驗錯誤返回 `400 INVALID_ARGUMENT`，不存在的 Account
返回 `404 NOT_FOUND`。

建立期欄位只能隨 `POST /api/v1/admin/accounts` 的 `settings` 寫入。建立後 PATCH
觸及這些欄位，包括把父物件設為 `null`，都會返回 `400 INVALID_ARGUMENT`，且不會
持久化任何部分更新。建立請求會在建立帳號目錄前校驗 `settings`；後續 PATCH 則先合併
當前 Account 顯式值，再校驗完整有效配置。

**其他 Account 配置段**

除模型與向量配置外，以下 `settings` object 均為動態欄位，ROOT 和目標 Account 的 ADMIN
都可讀寫：

| 路徑 | 型別和約束 | 含義 |
| --- | --- | --- |
| `acl.enabled` | boolean，預設 `false` | 是否啟用該 Account 的 ACL |
| `agent_evolution.enabled` | boolean，預設 `false` | 是否啟用 Agent Evolution；Account 未設定整個 section 時，為相容舊行為使用完整 Cluster `agent_evolution` section |
| `github.token` | string，預設空字串 | GitHub 訪問 token；空字串表示該 Account 未提供 token |

`github` 和 `acl` 不回退到 Cluster。

**讀取 Account 顯式配置**

```bash
curl http://localhost:1933/api/v1/admin/accounts/acme/configuration \
  -H "X-API-Key: <root-key>"
```

```json
{
  "status": "ok",
  "result": {
    "account_id": "acme",
    "settings": {
      "embedding": {
        "max_retries": 5
      }
    }
  }
}
```

響應不會展開 Cluster 值、預設值或最終生效的 Embedding/VectorDB 組合。例如上例沒有
Account 模型 binding 時，實際呼叫仍會使用 Cluster 模型 binding。

**修改動態 Account 配置**

以下示例假定 Account 已在建立時聲明瞭包含 `model` 與 `dimension` 的 `dense`
binding；PATCH 只輪換其 credentials 並更新動態執行引數。

```bash
curl -X PATCH http://localhost:1933/api/v1/admin/accounts/acme/configuration \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <root-key>" \
  -d '{
    "settings": {
      "embedding": {
        "max_retries": 5,
        "dense": {
          "credentials": [{
            "id": "primary",
            "provider": "openai",
            "model": "embed-deployment-v2",
            "api_key": "<new-api-key>",
            "api_base": "https://embedding.example/v1"
          }]
        }
      }
    }
  }'
```

```json
{
  "status": "ok",
  "result": {
    "account_id": "acme",
    "settings": {
      "embedding": {
        "max_retries": 5,
        "dense": {
          "model": "text-embedding-3-large",
          "dimension": 3072,
          "credentials": [{
            "id": "primary",
            "provider": "openai",
            "model": "embed-deployment-v2",
            "api_key": "<new-api-key>",
            "api_base": "https://embedding.example/v1"
          }]
        }
      }
    }
  }
}
```

物件遞迴合併，陣列整體替換。因此上例會替換 `dense.credentials` 的全部 failover
鏈，而不是按 `id` 合併。動態葉子設為 `null` 會刪除該 Account 值，例如
`{"settings":{"embedding":{"max_retries":null}}}`；之後由向量解析器採用 Cluster
對應值。空物件不會清空已有物件。

**Account VLM 與 Query Planner 欄位**

`vlm` 和 `query_planner` 使用相同 schema，均為動態段：

| 路徑 | 型別和約束 | 含義 |
| --- | --- | --- |
| `*.model` | 非空 string，必填 | 預設模型名 |
| `*.credentials` | 非空 array，必填，整體替換 | 按陣列順序使用的 provider/failover binding |
| `*.timeout` | number，`> 0`，可選 | Account 請求超時秒數；刪除後使用 Cluster timeout |
| `*.credentials[].id` | string，可選 | credential 標識 |
| `*.credentials[].provider` | string，必填 | `volcengine`、`openai`、`azure`、`kimi`、`glm`、`litellm` 或 `openai-codex` |
| `*.credentials[].model` | string，可選 | 覆蓋外層 `model`，可用於 endpoint/deployment ID |
| `*.credentials[].api_key` | string，可選 | provider API Key；除 `litellm` 外通常必需，`openai-codex` 可使用本機 Codex OAuth |
| `*.credentials[].api_base` | string，可選 | API endpoint |
| `*.credentials[].api_version` | string，可選 | Azure 等 API 的版本 |
| `*.credentials[].forward_api_key` | boolean，可選 | 是否把 API Key 透傳給 LiteLLM |
| `*.credentials[].extra_headers` | `map<string, string>`，可選 | 請求附加 HTTP headers；map key 為 header 名，value 為 header 值 |
| `*.credentials[].extra_request_body` | `map<string, JSON value>`，可選 | 原樣追加到 OpenAI-compatible completion 請求 body 的 provider 擴充欄位；頂層 `stream` 不允許 |
| `*.credentials[].reasoning_effort` | string，可選 | OpenAI-compatible reasoning 強度 |
| `*.credentials[].keepalive_expiry` | number，`>= 0`，可選 | HTTP 空閒連線存活秒數 |
| `*.credentials[].max_tokens` | integer，`> 0`，可選 | 覆蓋外層輸出 token 上限 |

Account 未配置 `vlm` 時使用 Cluster VLM。配置 Account `vlm` 後，模型、provider、
endpoint 與憑據只取 Account 值；Cluster 僅提供未歸屬 Account 的通用執行行為。
Query Planner 優先順序為 Account `query_planner`、Account `vlm`、Cluster
`query_planner`、Cluster `vlm`。

`extra_headers` 與 `extra_request_body` 的 key 不由 OpenViking 列舉，必須遵循目標
provider 的 API 契約。它們僅屬於該 credential，不會與 Cluster 同名 object 或其他
credential 合併；不能用 `extra_request_body` 設定 `stream`，因為 OpenViking VLM 介面
只返回完整響應。

**Account Embedding 欄位**

未設定的欄位不寫入 Account；向量解析器在執行時按需使用 Cluster 的相應值。若 Account
建立時宣告 `dense`、`sparse` 或 `hybrid`，該 mode 必須是完整的 Account binding。
`hybrid` 不能與 `dense` 或 `sparse` 同時出現。

| 路徑 | 生命週期 | 型別和約束 | 含義 |
| --- | --- | --- | --- |
| `embedding.dense` / `sparse` / `hybrid` | mode 存在性建立期 | object/null | 三種模型輸出模式；建立後不能新增、刪除或切換 |
| `embedding.max_concurrent` | 動態 | integer，`>= 1` | 該 Account 的 provider 呼叫併發上限 |
| `embedding.max_retries` | 動態 | integer，`>= 0` | 瞬時 provider 錯誤重試次數 |
| `embedding.circuit_breaker.failure_threshold` | 動態 | integer，`>= 1` | 熔斷前的連續失敗次數 |
| `embedding.circuit_breaker.reset_timeout` | 動態 | number，`> 0` | 熔斷恢復基礎等待秒數 |
| `embedding.circuit_breaker.max_reset_timeout` | 動態 | number，`> 0` | 熔斷恢復等待上限秒數 |
| `embedding.text_source` | 建立期 | `content_only` / `summary_first` | 寫入向量使用的文本來源 |
| `embedding.max_input_tokens` | 建立期 | integer，`>= 100` | 單次向量化的輸入 token 上限 |
| `embedding.*.model` | 建立期 | 非空 string，mode 首次宣告時必填 | 模型身份 |
| `embedding.*.dimension` | 建立期 | integer，`> 0`，mode 首次宣告時必填 | 向量維度；必須與有效 VectorDB 一致 |
| `embedding.*.input` | 建立期 | `text` / `multimodal`，可選 | 輸入模式 |
| `embedding.*.query_param` / `document_param` | 建立期 | string，可選 | 非對稱檢索的 query/document 引數 |
| `embedding.*.version` | 建立期 | string，可選 | 模型版本 |
| `embedding.*.credentials` | 動態 | 非空 array，整體替換 | Account provider/failover binding |
| `embedding.*.failback_timeout_seconds` | 動態 | number，`> 0` | 回切主 credential 前的等待秒數 |
| `embedding.*.failback_request_count` | 動態 | integer，`>= 1` | 使用備用 credential 後嘗試回切的請求數 |

`embedding.*.credentials` 是有序陣列，陣列首項優先；失敗時按陣列順序嘗試後續
credential。每個元素的 schema 如下：

| 欄位 | 型別和約束 | 含義 |
| --- | --- | --- |
| `id` | string，可選 | credential 穩定標識；未設定時執行時生成按陣列下標命名的標識 |
| `provider` | string，必填 | 小寫 provider 名：`openai`、`azure`、`volcengine`、`vikingdb`、`jina`、`ollama`、`gemini`、`voyage`、`dashscope`、`minimax`、`cohere`、`litellm` 或 `local` |
| `model` | 非空 string，可選 | 覆蓋該 mode 的外層 `model`；未設定時使用外層 `model`，常用於 endpoint/deployment ID |
| `api_key` | string，可選 | API Key。具體 provider 是否必填見下表 |
| `api_base` | string，可選 | OpenAI-compatible 或 Azure endpoint |
| `api_version` | string，可選 | Azure 等 API 的版本引數 |
| `ak` | string，可選 | VikingDB Embedding provider 的 Access Key |
| `sk` | string，可選 | VikingDB Embedding provider 的 Secret Key |
| `region` | string，可選 | VikingDB Embedding provider 的區域 |
| `host` | string，可選 | provider endpoint 或路由 host |
| `extra_headers` | `map<string, string>`，可選 | 發往 provider 的附加 HTTP headers |

每個 credential 都必須獨立完成 provider 所需的連線與鑑權，不能從 Cluster 或同一陣列
的其他 credential 借用欄位：

| provider | 必填或可替代欄位 | 說明 |
| --- | --- | --- |
| `openai` | `api_key` 或 `api_base` | `api_base` 可用於不要求 API Key 的本地 OpenAI-compatible 服務 |
| `azure` | `api_key` 和 `api_base` | `api_version` 可按 Azure endpoint 要求補充 |
| `volcengine`、`jina`、`gemini`、`voyage`、`dashscope`、`minimax`、`cohere` | `api_key` | 其他連線欄位按對應 provider 的呼叫方式選填 |
| `vikingdb` | `ak`、`sk` 和 `region` | 三項必須同時提供 |
| `ollama`、`litellm`、`local` | 無強制鑑權欄位 | 仍必須有外層或 credential `model`；實際 endpoint、環境變數或本地模型要求由對應 provider 處理 |

credential 的 `model` 可以省略並使用該 mode 的外層 `model`。憑據陣列一旦提供，不會
拼接 Cluster 的 provider、endpoint、鑑權或 provider-specific 欄位。`batch_size`、
`encoding_format`、`extra_body`、`model_path`、`cache_dir`、融合/影片引數、
`allow_metadata_override` 及 credentials 外層 provider/auth 欄位均不在 Account API
範圍內。

存量 Account 可以更新動態執行引數；但不能借 PATCH 首次建立 model mode，因為 `model`、
`dimension` 和 mode 組合都是建立期契約。`embedding: {}` 合法，表示沒有 Account
Embedding 覆蓋；作為 PATCH 提交時只會合併，不會清空已有設定。

**Account VectorDB 欄位**

`vectordb` 只能作為 Account 建立請求的 `settings.vectordb` 提交，所有欄位均為建立期。
未提交時該 Account 使用 Cluster VectorDB；已提交時 Account 連線與鑑權完整替換 Cluster
連線與鑑權，即使 backend 型別相同也不會合並。

| 路徑 | 型別和約束 | 含義 |
| --- | --- | --- |
| `vectordb.backend` | 必填：`http` | Account 僅支援遠端 backend |
| `vectordb.name` | 非空 string，必填 | collection 名 |
| `vectordb.url` | string；`http` 時必填 | HTTP backend endpoint |
| `vectordb.project` | 非空 string，預設 `default` | project 名；`project_name` 為內部欄位名 |
| `vectordb.index_name` | 非空 string，必填 | index 名 |
| `vectordb.distance_metric` | `cosine`、`l2`、`ip`，預設 `cosine` | 距離度量 |
| `vectordb.dimension` | integer，`> 0`，必填 | 必須與有效 Embedding dimension 一致 |
| `vectordb.sparse_weight` | number，`>= 0`，預設 `0` | sparse/hybrid 檢索權重 |

VectorDB 子物件也全部為建立期欄位：

| 路徑 | 型別和約束 | 含義 |
| --- | --- | --- |

不支援 Account `local`、`cuvs`、`path`、cuVS 調優或 `custom_params`。遠端 collection、
index、schema 和授權由外部控制面預先建立；介面只做本地配置與 Embedding/VectorDB 聯合
校驗，不探測遠端資源。配置有效後，查詢、匯入、佇列寫入、Reindex 和 OVPack 都按目標
Account 路由，ROOT 代表某個 Account 執行業務時也遵守這一規則。

每次 Embedding 建立或更新都會校驗有效 Embedding/VectorDB pair，包括向量維度、輸出
模式、稀疏權重、distance metric、provider 配置與鑑權完整性。校驗失敗不會發布新配置；
執行時連線、鑑權、collection/index 不存在或 schema 漂移只會使當前 Account 操作失敗，
不會回退到其他 Account 或 Cluster VectorDB。憑據或 endpoint 動態更新僅影響後續呼叫，
在途呼叫會完成；系統不會自動遷移或重建歷史向量，呼叫方必須保證模型語義相容。

### user_settings

ROOT 可管理任意 User，ADMIN 僅可管理所屬 account 內的 User。User 配置介面當前
僅允許修改 `memory_policy`。頂層統一的 `memory_types` 控制允許抽取的記憶型別。
使用者記憶根據每條 Message 的 `peer_id` 自動寫入 Self 或 Peer；Agent 記憶始終只寫入
Self。

```http
GET /api/v1/admin/accounts/{account_id}/users/{user_id}/settings
PATCH /api/v1/admin/accounts/{account_id}/users/{user_id}/settings
Content-Type: application/json

{
  "memory_policy": {
    "memory_types": ["profile", "preferences", "events", "entities", "experiences"]
  }
}
```

響應直接返回 User 級 `memory_policy`，並展開預設記憶型別和 Agent 記憶依賴；配置
`experiences` 時會展開為 `cases`、`trajectories`、`experiences`；
該結果不受 account 級 Agent 進化開關影響，Account 開關由獨立介面管理。
更新前會備份到該 User 的 `settings/user_config.backup.json`。未顯式配置策略的
Session 在 commit 時讀取該 User 最新策略；User 未覆蓋時，依次回退到
`server.user_config_defaults.memory_policy` 和核心預設策略。若要清除已持久化的
User override 並重新繼承上述預設值，請 PATCH `{"memory_policy": null}`。
`{"memory_policy": {}}` 表示顯式策略，不會清除 override。

---

### create_account

#### 1. API 實現介紹

建立新工作區及其首個管理員使用者。

**處理流程：**
1. 驗證請求者具有 ROOT 許可權
2. 使用 API Key Manager 建立帳戶和初始管理員使用者
3. 初始化帳戶級目錄結構
4. 初始化管理員使用者的個人目錄
5. 寫入可選的初始管理員使用者配置
6. 返回帳戶資訊和使用者金鑰（非 trusted 模式下）

**程式碼入口：**
- `openviking/server/routers/admin.py:create_account` - HTTP 路由
- `openviking/server/api_keys/new.py:APIKeyManager.create_account` - 核心實現
- `sdk/python/openviking_sdk/client.py:SyncHTTPClient.admin_create_account` - Python SDK

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| account_id | str | 是 | - | 工作區 ID；新建檔案儲存帳戶不超過 255 個 UTF-8 位元組 |
| admin_user_id | str | 是 | - | 首個管理員使用者 ID |
| seed | str | 否 | `null` | 可選的確定性 API Key seed。傳入後，key secret 為 `sha256(user_id + "\0" + seed)` |
| user_config | object | 否 | `null` | 首個管理員使用者的初始配置。支援 `add_targets.resource_uri`、`add_targets.skill_uri` 和 `memory_policy` |
| settings | object | 否 | `null` | Account 執行時初始配置。僅 ROOT 可提交；支援 `github`、`acl`、`agent_evolution`、`vlm`、`query_planner`、`embedding` 和 `vectordb`。其中 `vectordb` 及 Embedding 建立期欄位只能在這裡設定 |

**說明：**
- 檔案儲存帳戶建立時，超過 255 個 UTF-8 位元組的 `account_id` 會在寫入帳戶登錄檔前返回 `INVALID_ARGUMENT`。新持久化的 user ID 在所有帳戶儲存 Provider 中最多 255 個字元。trusted 模式會在加入自動註冊佇列前拒絕超長的新 user ID 和新建的超長帳戶，避免無效身份阻塞其他身份註冊；已有的超長 File user 和 account 仍可讀取。
- 在 `trusted` 模式下，只建立身份和角色，不生成個人金鑰、金鑰雜湊或金鑰索引；響應不包含 `user_key`，`seed` 不參與處理。
- 省略 `seed` 時隨機生成 API Key。執行確定性示例前，將 `OV_KEY_SEED` 設為安全生成的秘密值；Go 示例還需匯入 `os`。不要使用短字串或可預測內容作為 seed。
- `settings` 在帳號和目錄建立前完成結構與有效 Embedding/VectorDB 聯合校驗。校驗失敗不會留下 Account、使用者或配置檔案。
- Account `vlm`、`query_planner`、`embedding` 和 `vectordb` 是 ROOT-only 配置；欄位 schema、生命週期和校驗見上文 [Account Configuration 介面參考](#account-configuration-介面參考)。當前 Python SDK、CLI 及其他 SDK 的建立帳號封裝尚未暴露 `settings` 引數，使用此能力請直接呼叫 HTTP API。
- 不再支援 account 級 namespace 隔離配置。使用者記憶使用 user-scoped namespace，一對多外部參與者通過 `peer_id` 表達。
- `user_config.add_targets.resource_uri` 必須是可寫資源目錄 URI：`viking://resources` 或 `viking://resources/...`、`viking://~/resources` 或 `viking://~/resources/...`、`viking://user/{user_id}/resources` 或 `viking://user/{user_id}/resources/...`、`viking://user/{user_id}/peers/{peer_id}/resources` 或 `viking://user/{user_id}/peers/{peer_id}/resources/...`。
- `user_config.add_targets.skill_uri` 只能是 `viking://~/skills` 或 `viking://agent/skills`。v1 不支援顯式寫成 `viking://user/{user_id}/skills`。
- 舊寫法相容：`viking://user/resources[/...]` 和 `viking://user/skills` 在這裡仍會被接受，並歸一化為 `viking://~/...` 形式（服務端會列印一條 info 日誌）。在其他位置，無 uid 的寫法會在請求入口被拒絕——新配置請直接寫 `viking://~/...`。

#### 3. 使用示例

**HTTP API**

```
POST /api/v1/admin/accounts
```

```bash
curl -X POST http://localhost:1933/api/v1/admin/accounts \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <root-key>" \
  -d '{
    "account_id": "acme",
    "admin_user_id": "alice"
  }'
```

建立獨立 Embedding 與 VectorDB 的 Account：

```bash
curl -X POST http://localhost:1933/api/v1/admin/accounts \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <root-key>" \
  -d '{
    "account_id": "acme-isolated",
    "admin_user_id": "alice",
    "settings": {
      "embedding": {
        "dense": {
          "model": "text-embedding-3-large",
          "dimension": 3072,
          "credentials": [{
            "provider": "openai",
            "api_key": "<embedding-api-key>"
          }]
        }
      },
      "vectordb": {
        "backend": "http",
        "name": "acme_context",
        "index_name": "default",
        "dimension": 3072,
        "url": "https://vectordb.example"
      }
    }
  }'
```

**trusted 模式**

配置 `server.root_api_key` 後，直接用 root key 呼叫 Admin API；無需先註冊閘道器使用者，也無需切換到 `api_key` 模式。這類請求可以省略身份頭，避免與 URL 中的目標 account/user 不匹配。

```bash
curl -X POST http://localhost:1933/api/v1/admin/accounts \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <root-key>" \
  -d '{
    "account_id": "acme",
    "admin_user_id": "alice"
  }'
```

**Python SDK**

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(api_key="<root-key>")
client.initialize()

result = client.admin_create_account(
    account_id="acme",
    admin_user_id="alice",
)
print(f"Account created: {result['account_id']}")
print(f"Admin user: {result['admin_user_id']}")
print(f"User key: {result.get('user_key', '(not exposed in trusted mode)')}")

result = client.admin_create_account(
    account_id="acme-private",
    admin_user_id="alice",
    user_config={
        "add_targets": {
            "resource_uri": "viking://~/resources",
            "skill_uri": "viking://~/skills",
        }
    },
)
```

**TypeScript SDK**

```typescript
console.log(await client.adminCreateAccount("account-id", "admin-user-id"));
```

**Go SDK**

```go
result, err := client.AdminCreateAccount(ctx, "acme", "alice")
if err != nil {
    return err
}
fmt.Println(result["account_id"])

seed := os.Getenv("OV_KEY_SEED")
result, err = client.AdminCreateAccountWithOptions(ctx, "acme-private", "alice", &openviking.AdminCreateAccountOptions{
    Seed: &seed,
    UserConfig: map[string]any{
        "add_targets": map[string]any{
            "resource_uri": "viking://~/resources",
            "skill_uri":    "viking://~/skills",
        },
    },
})
```

**CLI**

```bash
# 需要 ROOT 許可權，使用 --sudo
ov --sudo admin create-account acme --admin alice
ov --sudo admin create-account acme --admin alice --seed "$OV_KEY_SEED"

ov --sudo admin create-account acme-private --admin alice \
  --user-config-json '{"add_targets":{"resource_uri":"viking://~/resources","skill_uri":"viking://~/skills"}}'
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "account_id": "acme",
    "admin_user_id": "alice",
    "user_key": "7f3a9c1e..."
  }
}
```

---

### list_accounts

#### 1. API 實現介紹

列出所有工作區（僅 ROOT）。

**處理流程：**
1. 驗證請求者具有 ROOT 許可權
2. 呼叫 API Key Manager 獲取所有帳戶列表（按建立順序排列）
3. 應用可選的 `name` 過濾
4. 應用可選的 `limit`/`page` 分頁
5. 返回包含帳戶 ID、建立時間和使用者數量的列表

**程式碼入口：**
- `openviking/server/routers/admin.py:list_accounts` - HTTP 路由
- `openviking/server/api_keys/new.py:APIKeyManager.get_accounts` - 核心實現
- `sdk/python/openviking_sdk/client.py:SyncHTTPClient.admin_list_accounts` - Python SDK

#### 2. 介面和引數說明

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| name | str | 否 | null | 按帳戶 ID 過濾（萬用字元 `*` 和 `?` 匹配） |
| limit | int | 否 | null | 每頁數量（≥1）。省略則返回所有匹配項 |
| page | int | 否 | 1 | 從 1 開始的頁碼；僅在設定了 `limit` 時生效 |
| query | str | 否 | null | 對帳戶 ID 做不區分大小寫的子串匹配 |

結果按建立順序返回。

#### 3. 使用示例

**HTTP API**

```
GET /api/v1/admin/accounts
```

```bash
# 列出所有帳戶
curl -X GET http://localhost:1933/api/v1/admin/accounts \
  -H "X-API-Key: <root-key>"

# 帶過濾條件（萬用字元 name 匹配）
curl -X GET "http://localhost:1933/api/v1/admin/accounts?name=*acme*" \
  -H "X-API-Key: <root-key>"

# 不區分大小寫的子串搜尋
curl -X GET "http://localhost:1933/api/v1/admin/accounts?query=acme" \
  -H "X-API-Key: <root-key>"

# 分頁（每頁 50，取第 2 頁）
curl -X GET "http://localhost:1933/api/v1/admin/accounts?limit=50&page=2" \
  -H "X-API-Key: <root-key>"
```

**Python SDK**

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(api_key="<root-key>")
client.initialize()

accounts = client.admin_list_accounts(name="*acme*", limit=50, page=1)
for account in accounts:
    print(f"Account: {account['account_id']}, created: {account['created_at']}, users: {account['user_count']}")
```

**TypeScript SDK**

```typescript
console.log(await client.adminListAccounts({ name: "*acme*", limit: 50, page: 1 }));
```

**Go SDK**

```go
accounts, err := client.AdminListAccounts(ctx)
if err != nil {
    return err
}
fmt.Println(accounts)
```

**CLI**

```bash
# 需要 ROOT 許可權，使用 --sudo
ov --sudo admin list-accounts

# 按萬用字元 name 過濾
ov --sudo admin list-accounts --name '*acme*'

# 分頁
ov --sudo admin list-accounts --limit 50 --page 2
```

**響應示例**

```json
{
  "status": "ok",
  "result": [
    {"account_id": "default", "created_at": "2026-02-12T10:00:00Z", "user_count": 1},
    {"account_id": "acme", "created_at": "2026-02-13T08:00:00Z", "user_count": 2}
  ]
}
```

---

### delete_account

#### 1. API 實現介紹

非同步刪除工作區及其所有關聯使用者和資料（僅 ROOT）。介面返回 HTTP `202` 和 `task_id`，不等待資料清理完成。

**處理流程：**
1. 驗證 ROOT 許可權，持久化帳號刪除標記，立即拒絕帳號金鑰和普通請求；建立系統作用域的 `account_delete` Task 並持久化入隊，返回 `status=deleting` 和 `task_id`
2. 後臺停止該帳號的 Watch 和業務任務，清理向量、OAuth 授權、用量審計資料和整個帳號 AGFS 目錄（包含帳號內的任務記錄）
3. 清理成功後移除帳號註冊記錄，將 Task 標記為 `completed`

帳號和使用者清理共用一個序列消費的資料清理佇列。帳號任務直接清理整個帳號。後續使用者清理任務發現目標已刪除時，完成並跳過；舊任務也不會清理重建的同名帳號或使用者。歸屬該帳號的任務記錄一併刪除，後續訊息不會重建這些記錄；系統作用域的清理 Task 仍可查詢。

**程式碼入口：**
- `openviking/server/routers/admin.py:delete_account` - HTTP 路由
- `openviking/service/deletion.py:DeletionService.delete` - 核心實現
- `sdk/python/openviking_sdk/client.py:SyncHTTPClient.admin_delete_account` - Python SDK

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| account_id | str | 是 | - | 要刪除的工作區 ID |

**說明：**
- 刪除操作是不可逆的，會級聯刪除該帳戶下的所有資料
- 清理失敗時，Task 標記為 `failed` 並記錄錯誤原因；帳號保持 `deleting`
- 正在刪除時重複請求返回同一個 Task；失敗後再次請求會建立重試 Task，處理剩餘資料
- 服務重啟後恢復未完成任務；刪除期間不能重建同名帳號，也不能恢復帳號使用
- 向量先按帳號條件分頁列舉 ID，再分批提交刪除，每次刪除請求最多 100 條，不受原來的單次 10 萬條總量上限限制
- 向量刪除以刪除介面成功為準，不要求即時 Count 歸零或回讀為空；即使 Task 已完成，遠端索引仍可能因同步延遲短暫返回舊資料
- 帳號列表中的 `status` 為 `active` 或 `deleting`；刪除中的帳號同時返回 `task_id`
- 使用 ROOT 呼叫 `GET /api/v1/tasks/{task_id}` 檢視狀態和錯誤；清理任務只使用 `pending`、`running`、`completed`、`failed` 狀態，不細分清理階段，只有 `completed` 表示清理完成

#### 3. 使用示例

**HTTP API**

```
DELETE /api/v1/admin/accounts/{account_id}
```

```bash
curl -X DELETE http://localhost:1933/api/v1/admin/accounts/acme \
  -H "X-API-Key: <root-key>"
```

**Python SDK**

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(api_key="<root-key>")
client.initialize()

result = client.admin_delete_account(account_id="acme")
print(f"Cleanup task: {result['task_id']}")
```

**TypeScript SDK**

```typescript
await client.adminDeleteAccount("account-id");
```

**Go SDK**

```go
result, err := client.AdminDeleteAccount(ctx, "acme")
if err != nil {
    return err
}
fmt.Println(result["task_id"])
```

**CLI**

```bash
# 需要 ROOT 許可權，使用 --sudo
ov --sudo admin delete-account acme
ov --sudo task status <task_id>
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "account_id": "acme",
    "status": "deleting",
    "task_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

---

### register_user

#### 1. API 實現介紹

在工作區中註冊新使用者。

**處理流程：**
1. 驗證請求者具有 ROOT 許可權，或為本帳戶的 ADMIN
2. 呼叫 API Key Manager 註冊新使用者
3. 初始化新使用者的個人目錄
4. 寫入可選的初始使用者配置
5. 返回使用者資訊和使用者金鑰（非 trusted 模式下）

**程式碼入口：**
- `openviking/server/routers/admin.py:register_user` - HTTP 路由
- `openviking/server/api_keys/new.py:APIKeyManager.register_user` - 核心實現
- `sdk/python/openviking_sdk/client.py:SyncHTTPClient.admin_register_user` - Python SDK

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| account_id | str | 是 | - | 工作區 ID |
| user_id | str | 是 | - | 使用者 ID |
| role | str | 否 | "user" | 要分配的角色。`ROOT` 和同 account 的 `ADMIN` 可直接註冊 `"user"` 或 `"admin"`。ROOT 身份只來自 `server.root_api_key`。 |
| seed | str | 否 | `null` | 可選的確定性 API Key seed。傳入後，key secret 為 `sha256(user_id + "\0" + seed)` |
| user_config | object | 否 | `null` | 新使用者的初始配置。支援 `add_targets.resource_uri`、`add_targets.skill_uri` 和 `memory_policy` |

**說明：**
- 在 `trusted` 模式下，只建立身份和角色，不生成個人金鑰、金鑰雜湊或金鑰索引；響應不包含 `user_key`，`seed` 不參與處理。
- 省略 `seed` 時隨機生成 API Key。執行確定性示例前，將 `OV_KEY_SEED` 設為安全生成的秘密值；Go 示例還需匯入 `os`。不要使用短字串或可預測內容作為 seed。
- ADMIN 只能在自己所屬的 account 中註冊使用者
- 無法通過使用者註冊介面直接建立 `"root"` 角色
- `user_config.add_targets.resource_uri` 必須是可寫資源目錄 URI：`viking://resources` 或 `viking://resources/...`、`viking://~/resources` 或 `viking://~/resources/...`、`viking://user/{user_id}/resources` 或 `viking://user/{user_id}/resources/...`、`viking://user/{user_id}/peers/{peer_id}/resources` 或 `viking://user/{user_id}/peers/{peer_id}/resources/...`。
- `user_config.add_targets.skill_uri` 只能是 `viking://~/skills` 或 `viking://agent/skills`。v1 不支援顯式寫成 `viking://user/{user_id}/skills`。
- 舊寫法相容：`viking://user/resources[/...]` 和 `viking://user/skills` 在這裡仍會被接受，並歸一化為 `viking://~/...` 形式（服務端會列印一條 info 日誌）。在其他位置，無 uid 的寫法會在請求入口被拒絕——新配置請直接寫 `viking://~/...`。

#### 3. 使用示例

**HTTP API**

```
POST /api/v1/admin/accounts/{account_id}/users
```

```bash
curl -X POST http://localhost:1933/api/v1/admin/accounts/acme/users \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <root-or-admin-key>" \
  -d '{
    "user_id": "bob",
    "role": "user"
  }'
```

**Python SDK**

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(api_key="<root-or-admin-key>")
client.initialize()

result = client.admin_register_user(
    account_id="acme",
    user_id="bob",
    role="user",
)
print(f"User registered: {result['user_id']}")
print(f"User key: {result.get('user_key', '(not exposed in trusted mode)')}")

result = client.admin_register_user(
    account_id="acme",
    user_id="bob-private",
    role="user",
    user_config={"add_targets": {"resource_uri": "viking://~/resources/project-a"}},
)
```

**TypeScript SDK**

```typescript
console.log(await client.adminRegisterUser("account-id", "user-id", "user"));
```

**Go SDK**

```go
result, err := client.AdminRegisterUser(ctx, "acme", "bob", "user")
if err != nil {
    return err
}
fmt.Println(result["user_id"])

seed := os.Getenv("OV_KEY_SEED")
result, err = client.AdminRegisterUserWithOptions(ctx, "acme", "bob-private", "user", &openviking.AdminRegisterUserOptions{
    Seed: &seed,
    UserConfig: map[string]any{
        "add_targets": map[string]any{"resource_uri": "viking://~/resources/project-a"},
    },
})
```

**CLI**

```bash
# ROOT 或本帳戶的 ADMIN 都可以執行
# 如果使用普通使用者的 api_key 但該使用者是 acme 的 ADMIN：
ov admin register-user acme bob --role user
ov admin register-user acme bob --role user --seed "$OV_KEY_SEED"
# 如果使用 root_api_key（--sudo）：
ov --sudo admin register-user acme bob --role user

ov admin register-user acme bob-private --role user \
  --user-config-json '{"add_targets":{"resource_uri":"viking://~/resources/project-a"}}'
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "account_id": "acme",
    "user_id": "bob",
    "user_key": "d91f5b2a..."
  }
}
```

---

### list_users

#### 1. API 實現介紹

列出工作區中的活躍使用者。正在刪除中的使用者不會返回。

**處理流程：**
1. 驗證請求者具有 ROOT 許可權，或為本帳戶的 ADMIN
2. 呼叫 API Key Manager 獲取活躍使用者列表（按建立順序排列）
3. 應用可選的過濾條件（name、role）
4. 應用可選的 `limit`/`page` 分頁
5. 返回使用者列表（trusted 模式下不包含 user_key）

**程式碼入口：**
- `openviking/server/routers/admin.py:list_users` - HTTP 路由
- `openviking/server/api_keys/new.py:APIKeyManager.get_users` - 核心實現
- `sdk/python/openviking_sdk/client.py:SyncHTTPClient.admin_list_users` - Python SDK

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| account_id | str | 是 | - | 工作區 ID |
| name | str | 否 | null | 按使用者 ID 過濾（萬用字元 `*` 和 `?` 匹配） |
| role | str | 否 | null | 按角色過濾 |
| query | str | 否 | null | 僅 HTTP，按使用者 ID 做不區分大小寫的字面包含匹配 |
| include_summary | bool | 否 | false | 僅 HTTP，以物件返回分頁使用者和帳號統計 |
| include_credentials | bool | 否 | true | 僅 HTTP。設為 false 時僅返回 `user_id`、`role` 和 `api_key_available`，不返回金鑰或字首；僅當服務端能讀取完整 key 並用於服務端繫結時 `api_key_available` 才為 true，僅存雜湊的憑據返回 false；預設保持現有按鑑權模式返回欄位的行為。 |
| limit | int | 否 | null | 每頁數量（≥1）。省略則返回所有匹配項 |
| page | int | 否 | 1 | 從 1 開始的頁碼；僅在設定了 `limit` 時生效 |

**說明：**
- 結果按建立順序返回
- ADMIN 只能列出自己所屬的 account 中的使用者
- 在 `trusted` 模式下，響應中不會包含 `user_key` 欄位
- 使用者刪除開始後，不再出現在該列表中

**帶統計的響應（HTTP）：** 設定 `include_summary=true` 後，`result` 返回物件：`users` 為當前頁，`total` 為匹配人數，`account_total` 為帳號總人數，`manager_count` 為 admin/root 人數，`key_count` 為具有可見金鑰或字首的使用者數。帳號統計不受搜尋和角色過濾影響，並排除正在刪除的使用者；停用金鑰展示時 `key_count` 為零。預設仍返回使用者陣列，相容現有呼叫。

`query` 對使用者 ID 做去除首尾空格、不區分大小寫的字面包含匹配，可與已有的 `name` 萬用字元、`role` 過濾組合。例如：

```text
GET /api/v1/admin/accounts/acme/users?limit=20&page=1&query=alice&include_summary=true
```

#### 3. 使用示例

**HTTP API**

```
GET /api/v1/admin/accounts/{account_id}/users
```

```bash
# 列出所有使用者
curl -X GET http://localhost:1933/api/v1/admin/accounts/acme/users \
  -H "X-API-Key: <root-or-admin-key>"

# 帶過濾條件（萬用字元 name 匹配）
curl -X GET "http://localhost:1933/api/v1/admin/accounts/acme/users?name=*ali*&role=admin" \
  -H "X-API-Key: <root-or-admin-key>"

# 分頁（每頁 50，取第 2 頁）
curl -X GET "http://localhost:1933/api/v1/admin/accounts/acme/users?limit=50&page=2" \
  -H "X-API-Key: <root-or-admin-key>"
```

**Python SDK**

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(api_key="<root-or-admin-key>")
client.initialize()

users = client.admin_list_users(account_id="acme", name="*ali*", limit=50, page=1)
for user in users:
    print(f"User: {user['user_id']}, role: {user['role']}")
```

**TypeScript SDK**

```typescript
console.log(await client.adminListUsers("account-id", { name: "*ali*", limit: 50, page: 1 }));
```

**Go SDK**

```go
users, err := client.AdminListUsers(ctx, "acme")
if err != nil {
    return err
}
fmt.Println(users)
```

**CLI**

```bash
# ROOT 或本帳戶的 ADMIN 都可以執行
# 如果使用普通使用者的 api_key 但該使用者是 acme 的 ADMIN：
ov admin list-users acme
# 如果使用 root_api_key（--sudo）：
ov --sudo admin list-users acme
# 按萬用字元 name 過濾
ov admin list-users acme --name '*ali*'
# 分頁
ov admin list-users acme --limit 50 --page 2
```

**響應示例**

```json
{
  "status": "ok",
  "result": [
    {"user_id": "alice", "role": "admin"},
    {"user_id": "bob", "role": "user"}
  ]
}
```

---

### remove_user

#### 1. API 實現介紹

從工作區中移除使用者。使用者 API Key 會立即失效，其擁有的資料清理非同步執行。

**處理流程：**
1. 驗證請求者具有 ROOT 許可權，或為本帳戶的 ADMIN
2. 寫入刪除 fence，並使使用者 API Key 失效
3. 提交一個持久化清理任務，刪除該使用者擁有的資料
4. 返回刪除任務 ID

**程式碼入口：**
- `openviking/server/routers/admin.py:remove_user` - HTTP 路由
- `openviking/service/deletion.py:DeletionService.delete` - 核心實現
- `sdk/python/openviking_sdk/client.py:SyncHTTPClient.admin_remove_user` - Python SDK

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| account_id | str | 是 | - | 工作區 ID |
| user_id | str | 是 | - | 要移除的使用者 ID |

**說明：**
- ADMIN 只能移除自己所屬的 account 中的使用者
- 不能刪除帳戶的最後一個 admin 使用者
- 刪除開始後，使用者 key 立即失效，list_users 不再返回該使用者
- 向量刪除以刪除介面成功為準，不等待遠端索引同步；Task 完成後，Count 或查詢結果仍可能短暫滯後

#### 3. 使用示例

**HTTP API**

```
DELETE /api/v1/admin/accounts/{account_id}/users/{user_id}
```

```bash
curl -X DELETE http://localhost:1933/api/v1/admin/accounts/acme/users/bob \
  -H "X-API-Key: <root-or-admin-key>"
```

**Python SDK**

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(api_key="<root-or-admin-key>")
client.initialize()

result = client.admin_remove_user("acme", "bob")
print(f"User deletion task: {result['task_id']}")
```

**TypeScript SDK**

```typescript
await client.adminRemoveUser("account-id", "user-id");
```

**Go SDK**

```go
result, err := client.AdminRemoveUser(ctx, "acme", "bob")
if err != nil {
    return err
}
fmt.Println(result["task_id"])
```

**CLI**

```bash
# ROOT 或本帳戶的 ADMIN 都可以執行
# 如果使用普通使用者的 api_key 但該使用者是 acme 的 ADMIN：
ov admin remove-user acme bob
# 如果使用 root_api_key（--sudo）：
ov --sudo admin remove-user acme bob
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "account_id": "acme",
    "user_id": "bob",
    "status": "deleting",
    "task_id": "..."
  }
}
```

---

### set_role

#### 1. API 實現介紹

將帳戶使用者提升為 ADMIN。ROOT 可以操作任意帳戶；ADMIN 只能操作自己的帳戶。

**處理流程：**
1. 驗證請求者具有 ROOT 或 ADMIN 許可權，並限制 ADMIN 只能操作自己的帳戶
2. 呼叫 API Key Manager 更新使用者角色
3. 返回更新後的使用者資訊

**程式碼入口：**
- `openviking/server/routers/admin.py:set_user_role` - HTTP 路由
- `openviking/server/api_keys/new.py:APIKeyManager.set_role` - 核心實現
- `sdk/python/openviking_sdk/client.py:SyncHTTPClient.admin_set_role` - Python SDK

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| account_id | str | 是 | - | 工作區 ID |
| user_id | str | 是 | - | 使用者 ID |
| role | str | 是 | - | 固定為 "admin" |

**說明：**
- ROOT 和 ADMIN 可以將使用者提升為 ADMIN；ADMIN 只能操作自己的帳戶
- 該介面不支援設定 "user" 或 "root"；ROOT 身份只來自 `server.root_api_key`

#### 3. 使用示例

**HTTP API**

```
PUT /api/v1/admin/accounts/{account_id}/users/{user_id}/role
```

```bash
curl -X PUT http://localhost:1933/api/v1/admin/accounts/acme/users/bob/role \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <root-key>" \
  -d '{"role": "admin"}'
```

**Python SDK**

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(api_key="<root-key>")
client.initialize()

result = client.admin_set_role(account_id="acme", user_id="bob", role="admin")
print(f"User: {result['user_id']}, new role: {result['role']}")
```

**TypeScript SDK**

```typescript
await client.adminSetRole("account-id", "user-id", "admin");
```

**Go SDK**

```go
result, err := client.AdminSetRole(ctx, "acme", "bob", "admin")
if err != nil {
    return err
}
fmt.Println(result["role"])
```

**CLI**

```bash
# ROOT 呼叫示例；acme 的 ADMIN 可用 ov admin set-role，無需 --sudo
ov --sudo admin set-role acme bob admin
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "account_id": "acme",
    "user_id": "bob",
    "role": "admin"
  }
}
```

---

### regenerate_key

#### 1. API 實現介紹

生成並儲存使用者的 API Key。預設隨機生成時，更新成功後舊 Key 失效。同一 account、user 和 seed 會生成相同的 Key；輪換金鑰時應使用新 seed，或省略 seed。

**處理流程：**
1. 驗證請求者具有 ROOT 許可權，或為本帳戶的 ADMIN
2. 呼叫 API Key Manager 重新生成使用者金鑰
3. 隨機生成或使用新 seed 時，舊金鑰立即失效
4. 返回新的使用者金鑰

**程式碼入口：**
- `openviking/server/routers/admin.py:regenerate_key` - HTTP 路由
- `openviking/server/api_keys/new.py:APIKeyManager.regenerate_key` - 核心實現
- `sdk/python/openviking_sdk/client.py:SyncHTTPClient.admin_regenerate_key` - Python SDK

#### 2. 介面和引數說明

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| account_id | str | 是 | - | 工作區 ID |
| user_id | str | 是 | - | 使用者 ID |
| seed | str | 否 | `null` | JSON request body 中可選的確定性 API Key seed。傳入後，key secret 為 `sha256(user_id + "\0" + seed)` |

**說明：**
- `trusted` 模式拒絕此操作，返回 HTTP 412（`FAILED_PRECONDITION`），不生成或修改金鑰。
- ADMIN 只能為自己所屬的 account 中的使用者重新生成金鑰
- 隨機生成或使用新 seed 時，舊金鑰立即失效，需要更新使用該金鑰的客戶端
- 省略 `seed` 時隨機生成新金鑰。確定性示例使用 `OV_KEY_SEED` 或 `OV_NEW_KEY_SEED`，執行前需將其設為安全生成的秘密值；Go 示例需匯入 `os`。不要把示例變數名直接當作 seed。

#### 3. 使用示例

**HTTP API**

```
POST /api/v1/admin/accounts/{account_id}/users/{user_id}/key
```

```bash
curl -X POST http://localhost:1933/api/v1/admin/accounts/acme/users/bob/key \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <root-or-admin-key>" \
  -d '{}'
```

**Python SDK**

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(api_key="<root-or-admin-key>")
client.initialize()

result = client.admin_regenerate_key(
    account_id="acme",
    user_id="bob",
)
print(f"New user key: {result['user_key']}")
```

**TypeScript SDK**

```typescript
console.log(await client.adminRegenerateKey("account-id", "user-id"));
```

**Go SDK**

```go
result, err := client.AdminRegenerateKey(ctx, "acme", "bob")
if err != nil {
    return err
}
fmt.Println(result["user_key"])

seed := os.Getenv("OV_NEW_KEY_SEED")
result, err = client.AdminRegenerateKeyWithOptions(ctx, "acme", "bob", &openviking.AdminRegenerateKeyOptions{
    Seed: &seed,
})
```

**CLI**

```bash
# ROOT 或本帳戶的 ADMIN 都可以執行
# 如果使用普通使用者的 api_key 但該使用者是 acme 的 ADMIN：
ov admin regenerate-key acme bob
ov admin regenerate-key acme bob --seed "$OV_NEW_KEY_SEED"
# 如果使用 root_api_key（--sudo）：
ov --sudo admin regenerate-key acme bob
```

**響應示例**

```json
{
  "status": "ok",
  "result": {
    "user_key": "e82d4e0f..."
  }
}
```

---

### migrate_legacy_data

#### 1. API 實現介紹

將舊 `viking://session/...` 資料遷移到 `viking://user/<user_id>/sessions/...`，或在確認遷移結果後清理舊 Session 目錄。該介面僅 ROOT 可呼叫，並以後臺 task 執行。`agent` 是帳號內公共目錄，不參與遷移或 cleanup。

**處理流程：**
1. 驗證請求者具有 ROOT 許可權
2. `action=migrate` 時執行 preflight，檢查 account registry、session owner 等前置條件
3. 建立 root 級後臺 task
4. 遷移時複製 Session 檔案；cleanup 時先刪除舊 Session 向量記錄，再刪除舊 Session AGFS 目錄

遷移保留目標路徑中已有的檔案。cleanup 不刪除 `agent` 公共目錄或已遷移的使用者資料。

**程式碼入口：**
- `openviking/server/routers/admin.py:migrate_legacy_data` - HTTP 路由
- `openviking/service/legacy_migration.py:LegacyDataMigration` - 遷移實現

#### 2. 介面和引數說明

**HTTP API**

```
POST /api/v1/admin/migrate
```

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| action | str | 否 | migrate | `migrate` 執行遷移；`cleanup` 清理舊 namespace |

**遷移結果欄位**

| 欄位 | 說明 |
|------|------|
| migrated.files / migrated.directories | 複製的檔案和目錄數量 |
| migrated.operations | Session 遷移運算元量（`sessions`） |
| skipped / created_users | 跳過的檔案、自動建立的使用者 |

**Cleanup 結果欄位**

| 欄位 | 說明 |
|------|------|
| cleanup.directories | 刪除的 legacy 目錄數量 |
| cleanup.vector_records | 刪除的舊向量記錄數量 |
| cleanup.targets | 已清理的 legacy scope |
| skipped / warnings | 跳過項和告警 |

#### 3. 使用示例

**HTTP API**

```bash
# 執行遷移
curl -X POST http://localhost:1933/api/v1/admin/migrate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <root-key>" \
  -d '{"action": "migrate"}'

# 遷移任務完成並核對目標資料後，再清理舊 namespace
curl -X POST http://localhost:1933/api/v1/admin/migrate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <root-key>" \
  -d '{"action": "cleanup"}'
```

**Python SDK**

```python
print(client.admin_migrate(cleanup=False))
```

**TypeScript SDK**

```typescript
console.log(await client.adminMigrate(false));
```

**Go SDK**

```go
result, err := client.AdminMigrate(ctx, &openviking.AdminMigrateOptions{
    Cleanup: false,
})
if err != nil {
    return err
}
fmt.Println(result["task_id"])
```

**CLI**

```bash
ov --sudo admin migrate --output json
# 先用 ov --sudo task status <task_id> 查詢返回的任務，再核對遷移結果。
ov --sudo admin migrate --cleanup --output json
```

**CLI 響應示例（預設 compact 輸出）**

```json
{
  "ok": true,
  "result": {"task_id": "6de05fc3-0334-40d6-ba9b-dd317eb4d351"}
}
```

---

<a id="使用者新增位置設定"></a>

## 完整示例

### 典型管理流程

示例包含刪除使用者和工作區的步驟，只應在測試工作區完整執行；為真實使用者開通帳號時跳過刪除步驟。

```bash
# 步驟 1：ROOT 建立工作區，指定 alice 為首個 admin（需要 --sudo）
ov --sudo admin create-account acme --admin alice
# 返回 alice 的 user_key

# 步驟 2：alice（admin）註冊普通使用者 bob
# 配置檔案中的 api_key 設為 alice 的 user_key，不需要 --sudo
ov admin register-user acme bob --role user
# 返回 bob 的 user_key

# 步驟 3：檢視帳戶下所有使用者
ov admin list-users acme

# 步驟 4：ROOT 將 bob 提升為 admin（需要 --sudo）
ov --sudo admin set-role acme bob admin

# 步驟 5：bob 丟失 key，重新生成（舊 key 立即失效）
# alice 作為 admin 可以執行，不需要 --sudo
ov admin regenerate-key acme bob

# 步驟 6：移除使用者
ov admin remove-user acme bob

# 步驟 7：刪除整個工作區（需要 --sudo）
ov --sudo admin delete-account acme
```

### HTTP API 等效流程

```bash
# 步驟 1：建立工作區
curl -X POST http://localhost:1933/api/v1/admin/accounts \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <root-key>" \
  -d '{"account_id": "acme", "admin_user_id": "alice"}'

# 步驟 2：註冊使用者（使用 alice 的 admin key）
curl -X POST http://localhost:1933/api/v1/admin/accounts/acme/users \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <alice-key>" \
  -d '{"user_id": "bob", "role": "user"}'

# 步驟 3：列出使用者
curl -X GET http://localhost:1933/api/v1/admin/accounts/acme/users \
  -H "X-API-Key: <alice-key>"

# 步驟 4：將使用者提升為 admin
curl -X PUT http://localhost:1933/api/v1/admin/accounts/acme/users/bob/role \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <alice-key>" \
  -d '{"role": "admin"}'

# 步驟 5：重新生成 key
curl -X POST http://localhost:1933/api/v1/admin/accounts/acme/users/bob/key \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <alice-key>"

# 步驟 6：移除使用者
curl -X DELETE http://localhost:1933/api/v1/admin/accounts/acme/users/bob \
  -H "X-API-Key: <alice-key>"

# 步驟 7：刪除工作區
curl -X DELETE http://localhost:1933/api/v1/admin/accounts/acme \
  -H "X-API-Key: <root-key>"
```

---

## 相關文件

- [多租戶](../concepts/11-multi-tenant.md) - 多租戶模型、角色和共享邊界
- [API 概覽](01-overview.md) - 認證與響應格式
- [會話管理](05-sessions.md) - 會話管理
- [系統](07-system.md) - 系統和監控 API
