# Web Studio VikingBot 產品與實現方案

狀態：設計與首期實現說明。首期支援網頁對話；IM 渠道接入通過 provider 擴充，當前已註冊 Telegram provider，其他 IM 在 Studio 中標註“開發中”。

## 當前分支實現說明

- 頁面入口 `/vikingbot`；新增管理介面集中在 `/api/v1/admin`，網頁聊天繼續複用原有介面。
- IM 連線和收發時間線持久化到 Bot 資料目錄的 `studio.sqlite3`，檔案許可權 0600。它含應用與專用使用者憑證，備份需按服務端配置處理。
- Studio 管理的 IM 會話僅開放帶繫結身份的 OpenViking 查詢與記憶工具；Shell、本地檔案、定時任務及未顯式批准的 MCP 工具預設不可用。
- 首期僅服務管理員可管理渠道；按當前 account 隔離連線及 IM 歷史。接入時選擇同帳戶普通使用者，由服務端繫結現有憑證；瀏覽器無需接收或輸入使用者 API Key。管理員身份不可選，僅儲存雜湊而無法自動繫結憑證的使用者顯示不可用。
- 受管啟動時自動為父子程序生成內部管理令牌，不寫回配置檔案。獨立 Gateway 需要額外的管理部署支援。
- 連線生命週期支援憑證更新、暫停/恢復、重啟恢復連線與群內驗證；具體接入方式（掃碼、手動表單等）由各平臺 provider 實現。
- IM 時間線展示 Studio 連線建立後捕獲的訊息，不自動接管原 ov.conf 渠道或補錄它們的舊歷史。既有渠道的遷移需要後續顯式繫結與身份確認。
- 支援暫停連線並保留歷史，也支援確認後刪除連線及其本地收發記錄。刪除不會刪除外部平臺應用或平臺中的訊息。IM 會話首期只讀。
- 受管 Agent 會話以連線 ID 隔離；刪除重建後不繼承舊連線上下文，也不傳送舊連線未完成的回覆。同一連線暫停恢復或重啟後仍可續接。此前未按連線隔離的 Agent 歷史不自動遷移，Studio 已捕獲的只讀訊息記錄不受影響。
- 自動化和模擬介面瀏覽器驗證不等同真實 IM 群驗收；真實收發仍需部署後使用應用憑證與測試群驗證。


## 介面範圍與複用依據

路由遵循倉庫管理介面約定：`/api/v1/admin` 為管理字首，帳號在 URL 中指定，router 自身宣告 prefix/tags，並由 `routers/__init__.py` 匯出、`app.py` 統一掛載。業務管理仍僅允許 ROOT，不能因掛入 admin 字首而放寬為帳號 ADMIN。

以下表格用 `B` 代表 `/api/v1/admin/accounts/{account_id}/bot`：

| HTTP 路由 | 呼叫場景與契約 |
| --- | --- |
| `GET /api/v1/admin/bot/capabilities` | 判斷 Bot 啟用及 ROOT 管理能力；與執行健康檢查職責不同。 |
| `GET /api/v1/admin/accounts/{account_id}/users?role=user&include_credentials=false` | **複用現有介面**。返回 `user_id`、`role`、`api_key_available`，不返回金鑰或字首。預設引數保持原有介面行為。 |
| `GET B/connections` | 渠道列表、混合會話來源、掃碼完成後載入連線。 |
| `POST B/connections` | 手動連線；請求包含 `type`、`user_id`、平臺自有的 `credentials` 物件。 |
| `PATCH B/connections/{id}` | 更新 `enabled`；提交 `revision` 保留併發保護。 |
| `DELETE B/connections/{id}?revision=N` | 刪除連線及其本地記錄；不刪除外部平臺應用。 |
| `POST B/connections/{id}/credentials` | 更新平臺憑證，包含 `credentials`、`user_id`、`revision`；服務端重新繫結身份。 |
| `POST B/connections/{id}/verifications` | 發起可選群驗證，提交 `revision`。 |
| `GET B/connections/{id}/conversations` | 連線下的收發會話列表。 |
| `GET B/connections/{id}/messages?conversation=...&before=...` | 捕獲訊息及傳送狀態；平臺會話標識保留在查詢引數中。 |
| `POST B/onboarding-runs` | 建立自動接入任務，顯式傳 `type`、`user_id`、`request_id` 和可選 `name`。 |
| `GET B/onboarding-runs/current?type=...` | 查詢指定平臺當前未完成任務；沒有任務時返回 null。不是全量任務列表。 |
| `GET B/onboarding-runs/{id}` | 輪詢指定任務。 |
| `POST B/onboarding-runs/{id}/actions` | 請求體 `action` 嚴格限定為 `retry`、`cancel`、`manual`，保留各操作的狀態校驗。 |

瀏覽器管理介面共 13 個，加上覆用的使用者列表介面。掃碼任務的重試、取消和轉手動共用一個 actions 介面，連線生命週期保持獨立方法。Studio 管理路由及 Gateway 內部 dispatch 均不進入 OpenAPI schema；介面仍正常註冊並保留原鑑權。舊的 `PATCH {action: ...}` 和 `X-OpenViking-Studio-Account` 已移除。該變更調整當前未釋出 PR 內的介面，前後端需一起更新；不為舊的臨時瀏覽器介面保留相容入口。

網頁會話建立、列表、歷史、刪除、Bot 聊天流式響應和健康狀態繼續複用既有 API。平臺收發記錄按連線歸屬並儲存傳送狀態，不能直接替換為 OpenViking 上下文會話歷史。

`POST /bot/v1/studio/dispatch` 僅在 Bot Gateway 內部保留，用內部令牌及 loopback 限制服務端呼叫。瀏覽器不直接呼叫；帳號和繫結使用者仍在 OpenViking 服務端校驗。

### 後續接入釘釘等平臺

- URL 按連線和接入任務組織，不含具體平臺名稱。平臺由顯式 `type` 決定；未知平臺由 provider registry 拒絕，不能預設為任何平臺。
- 平臺憑證放入 `credentials` 物件，例如 `app_id/app_secret`，各平臺可以使用自己的欄位。具體校驗、連線執行、憑證更新及公開配置欄位由 provider 負責；瀏覽器不能借憑證欄位替換服務端身份。
- 暫停、恢復、刪除、收發記錄和任務查詢共享資源介面。各平臺的授權實現與前端表單放入 provider 目錄；平臺特有能力不應直接加入全域路徑或假設所有平臺支援掃碼/群驗證。
- 當前已註冊 Telegram provider：管理員貼上 @BotFather 生成的 Bot Token，服務端通過 `getMe` 校驗並以長輪詢收發訊息，無需公網地址。Telegram Bot 可被任何人搜尋到，因此 Studio 接入必須填寫允許對話的 Telegram 使用者 ID 或 @使用者名稱（`settings.allow_from`，可在設定中修改），名單外的訊息不進入 Agent 與歷史記錄。更換 Token 時必須屬於同一個 Bot。
- 新增釘釘等平臺需要實現它的鑑權、連線、訊息轉換和 UI，並驗證其接入狀態流；通用路由不是釘釘功能已完成的證明。

未使用的定時任務介面及 UI、舊獨立 IM 會話列表、舊 `step` 操作已刪除，既有 CLI/Agent 定時任務功能不受影響。

## 1. 使用者目標與首期範圍

使用者可以在 Web Studio 中直接與 VikingBot 對話、查閱歷史，並在 IM provider 可用時通過引導將同一個 Bot 接入 IM 群。網頁和各個群的對話上下文獨立；共用 Bot 不代表共享所有會話或個人記憶。

首期交付：

- 一級導航新增 **VikingBot**，包含“對話”和“渠道”兩個頁面。
- 網頁新建對話、流式回覆、停止生成、繼續歷史對話。
- 檢視有許可權訪問的網頁會話，以及已接入 IM 的單聊、普通群、話題群歷史。
- IM 渠道的連線檢查、群內驗證、暫停和恢復連線（接入嚮導由 provider 提供）。
- Slack、釘釘、Discord 等尚無 provider 的平臺展示“開發中”，無配置表單、無可點選的接入按鈕。文案說明“Studio 接入管理開發中”，避免誤稱底層完全不支援。

首期不提供從 Studio 代發群訊息、匯入機器人入群前的 IM 歷史、跨群共享上下文。網頁聊天不依賴 IM 配置完成。

## 2. 頁面結構

```text
VikingBot                         Bot 執行正常
  對話 | 渠道

對話頁
┌──────────────────┬──────────────────────────────────┐
│ 新建對話          │ 需求分析 · 網頁                   │
│ 搜尋對話          │ 問題、回覆與流式輸出               │
│ 全部 / 網頁 / IM   │ 姓名、時間、正文、傳送狀態           │
│                  │                                  │
│ 今天             │ 工具呼叫預設摺疊                   │
│ 需求分析 · 網頁   │                                  │
│ 專案討論群 · IM   │ IM 會話只讀，請前往原平臺繼續對話     │
└──────────────────┴──────────────────────────────────┘
```

“對話”預設選中最近一次開啟且仍有許可權的會話，否則顯示歡迎頁。窄屏先顯示列表，選擇後進入詳情，提供返回列表操作。

列表顯示標題、來源、最後訊息摘要和時間；IM 話題顯示“群名 / 話題摘要”。不向普通使用者暴露群 ID、訊息 ID 或內部 SessionKey。名稱暫不可用時顯示“群聊（名稱待同步）”，技術 ID 僅在管理員診斷詳情中展示。

“渠道”頁包含網頁渠道、已連線的 IM 應用、由已註冊 provider 提供的新增入口，以及其他 IM 的開發中卡片。一個應用可以服務多個群；應用連線和群會話分別展示，不把一個群建成一個渠道。

## 3. 首次啟用與網頁對話

### 3.1 進入頁面

頁面分別檢測 Bot 服務、模型配置和當前身份許可權：

| 狀態 | 頁面文案與操作 |
|---|---|
| Bot 未啟用 | “先啟用 VikingBot”；管理員看到 `openviking-server --with-bot` 與部署說明，普通使用者看到“請聯絡管理員啟用” |
| 服務不可達 | “暫時無法連線 VikingBot”；顯示重試與管理員診斷入口，不清除已有歷史 |
| 模型未配置 | “配置對話模型後即可開始”；連結現有模型配置說明，說明預設繼承根級 `vlm` |
| 可以使用 | “開始與 VikingBot 對話”；主按鈕“新建對話”；有可用 IM provider 時顯示次按鈕“連線 IM” |

讀取配置只代表模型已配置，不代表呼叫成功。首次正常對話成功後記錄模型可用；模型呼叫失敗保留輸入並提供重試。

### 3.2 開始與繼續對話

1. 點選“新建對話”，輸入問題。
2. 首次傳送時建立持久會話；提交接受前保留輸入、阻止重複傳送。
3. 流式展示回答，工具呼叫摺疊展示，支援停止生成。
4. 左側立即出現新會話，標題取首條問題，可重新命名。
5. 重新整理、重新登入或服務重啟後，可重新開啟歷史繼續對話。

切換會話、取消或解除安裝頁面時，舊請求不能覆蓋新會話內容。停止瀏覽器流不自動錶示服務端任務已取消；產品只有在服務端確認取消後才顯示“已停止”，否則顯示“已停止接收，任務可能仍在執行”。

## 4. 身份、許可權和上下文

- 渠道配置及金鑰修改僅管理員可用；服務端逐介面鑑權，不能僅隱藏按鈕。
- 首期群歷史僅對該連線所屬管理範圍內的管理員開放。普通 Studio 使用者只查看自己的網頁會話；後續另行實現 IM 成員身份繫結與按群授權。
- 外部應用必須繫結明確的 OpenViking account/workspace 與執行身份；無繫結或無許可權時拒絕啟用，不回退 root 身份。
- 群會話不得繼承管理員私人網頁會話或個人記憶。群可訪問資源與記憶範圍使用受限的渠道身份配置。
- 列表、搜尋、詳情、附件、流事件均使用同一服務端許可權過濾；禁止先全量返回再由前端過濾。
- 群歷史中的文字只是訊息內容，不作為 Studio 管理指令執行。

## 5. 當前可複用能力與需要補齊的能力

基於當前倉庫程式碼核對：

| 能力 | 現狀 | 實現工作 |
|---|---|---|
| 網頁聊天 | Studio 已有 `useChat`、Composer、MessageList，Server 代理 Bot 流式介面 | 複用元件與請求生命週期，增加獨立入口 |
| 網頁歷史 | Studio 當前讀取 OpenViking Session 與歸檔 | 複用持久歷史，避免另建重複會話 |
| Bot 歷史 | Bot SessionManager 持久化並可列舉；OpenAPI `/sessions` 使用執行時記憶體索引 | 新增持久化的統一會話索引和許可權過濾 |
| @識別 | 當前基於 `bot_name` 匹配 mention 名稱 | 改為機器人穩定身份匹配，相容已配置名稱 |
| 渠道生命週期 | 配置載入與啟動已有；文件要求修改配置後重啟 | 新增單渠道受控應用配置、替換、暫停、恢復與回滾 |
| 執行狀態 | `_running` 與啟動日誌不能證明連線和訊息收發正常 | 增加實際連線、入站、出站的獨立狀態與時間戳 |

## 6. 建議介面與資料契約

以下均為擬新增能力，不代表現有 API 已提供。Studio 統一訪問 OpenViking Server，由 Server 進行鑑權並呼叫受管 Bot。

| 接口 | 用途 |
|---|---|
| `GET /bot/v1/capabilities` | 當前使用者許可權、Bot 狀態、支援的渠道與管理能力 |
| `GET /bot/v1/conversations` | 按來源、關鍵詞及游標列出有許可權的持久會話 |
| `GET /bot/v1/conversations/{id}/messages` | 分頁讀取統一時間線 |
| 當前管理介面 | 以本文“介面範圍與複用依據”的表格為準；不存在獨立的 validate/apply/status HTTP 介面。 |

網頁傳送繼續複用現有 chat/stream 介面；統一 conversation ID 必須能對映到原 Session ID。IM 會話不提供網頁傳送介面。

Conversation 索引儲存：許可權作用域、來源、連線、原始會話引用、群/話題顯示資訊、最近活動時間。原始身份標識僅服務端儲存。歷史正文沿用現有儲存，索引不復制兩份訊息；同一 Bot 會話關聯的 OpenViking 會話必須去重對映。

歷史訊息區分 generated、send_failed、sent 等狀態；不能把模型輸出視為已傳送。舊歷史缺少傳送證據時標註“傳送狀態未知”。已有會話遷移時不能推測擁有者；無法確定許可權歸屬的記錄暫不對普通使用者開放。

連線使用 draft、connecting、connected、degraded、paused、error 等執行狀態；配置驗證、群內測試另設獨立結果。重新整理頁面和服務重啟不丟失引導步驟，但執行狀態須重新探測。

首期管理能力限定為 Server 受管 Bot。外接 Gateway 未實現管理協議時顯示“當前部署暫不支援在 Studio 配置渠道”，仍可使用已授權的網頁聊天，並提供配置檔案說明；不顯示註定失敗的表單。

金鑰只在寫請求中提交，響應、日誌及診斷匯出均不回顯。沿用服務端配置位置，採用嚴格檔案許可權、原子寫入與版本校驗，保留不相關配置。只讀配置部署返回明確原因與管理員操作指引。

## 7. 實施順序與驗收

第一階段：獨立入口和網頁閉環。複用聊天元件、完成可持久的會話索引與身份契約。驗證首條傳送失敗可恢復、切換無串話、重啟後歷史可讀、多身份隔離。

第二階段：IM provider 嚮導和連線管理。完成配置草稿、憑證校驗、單渠道應用、身份匹配、真實連線狀態、群內驗證碼收發。驗證錯誤金鑰、未釋出、未訂閱、斷網、重複事件、配置失敗回滾與重新整理續接。

第三階段：IM 歷史與完整驗收。展示群名、成員名、話題、附件佔位、回覆結果；新增其他 IM 開發中卡片。通過真實 IM 群完成一次正常 @問答，核對 Studio 歷史和平臺回覆一致。

首期釋出必須同時滿足：

1. 新使用者能從服務未啟用狀態沿引導走到一次網頁成功對話。
2. 有可用 provider 時，管理員可從零完成 IM 應用連線、入群和真實問答；中斷後可繼續。
3. 改名後的機器人仍可正確識別 @；普通群與不同話題不串上下文。
4. 頁面過載及 Bot 重啟後歷史和配置仍可恢復；無記憶體索引依賴導致的歷史消失。
5. 群訊息傳送失敗不會顯示成功；憑證正確不會直接顯示“接入完成”。
6. 無許可權使用者無法通過介面列舉群歷史或讀取金鑰；群問答無法讀取管理員私人記憶。
7. 其他渠道清楚顯示“Studio 接入管理開發中”，不提供虛假可用入口。

## 8. 依據

- 倉庫：`web-studio/src/lib/sessions/api.ts`、`web-studio/src/routes/playground/-components/agent-panel.tsx`。
- 倉庫：`bot/vikingbot/channels/openapi.py`、`bot/vikingbot/session/manager.py`、`openviking/server/routers/bot.py`。
- 倉庫：`bot/vikingbot/channels/manager.py`、`bot/vikingbot/config/schema.py`、`bot/docs/zh/concepts/05-channel.md`。


## 多 IM 目錄邊界

- `bot/vikingbot/studio/service.py`：帳號隔離、持久化、版本衝突和連線生命週期。
- `bot/vikingbot/studio/providers/registry.py`：按連線 `type` 選擇平臺介面卡；未知型別拒絕接入。
- `web-studio/src/routes/vikingbot/-providers/registry.ts`：註冊各平臺的引導和憑證元件。
- 公共會話、歷史記錄和渠道列表保留在 `-components/`。

新增 Slack 等平臺時，新增對應 provider 目錄並註冊，複用連線生命週期和歷史儲存。平臺特有許可權、掃碼或 OAuth 狀態不進入公共服務。每個 provider 目錄負責平臺憑證校驗、引導動作、訊息接收和連線協議。當前僅註冊 Telegram provider，其他平臺保持“開發中”。
