---
description: 根據現象、Studio 標籤或錯誤碼，找到 OpenViking 閘道器問題的原因和解決辦法。
---

# OpenViking 閘道器排障

客戶端報錯、記憶沒有補充或對話沒有儲存、Studio 標出異常時，都可以從這一頁查起。先看三個地方：**概覽**標籤頁上的 **OpenViking** 卡片、篩選為**異常**的**請求日誌**標籤頁，以及 Server 日誌（Docker Compose 部署用 `docker compose logs openviking`，獨立閘道器看它自己的輸出）。然後在下面的表格裡找到對應現象；每一節都能單獨閱讀，並連結到相關設定。

## 常見現象 {#common-symptoms}

| 現象 | 可能原因 | 處理 |
| --- | --- | --- |
| 開啟閘道器後 Server 隨即停止 | 嵌入閘道器沒有通過啟動檢查。 | [閘道器無法啟動](#the-gateway-does-not-start) |
| Studio 顯示一張卡片，看不到閘道器標籤頁 | 閘道器沒有開啟、OpenViking API 金鑰缺失或無效，或者閘道器連不上 OpenViking。 | [Studio 顯示設定卡片](#studio-shows-a-setup-card) |
| “上游”和“上下文配置”標籤頁只讀 | 部署者設定了閘道器管理金鑰。 | [解鎖編輯](06-manage-in-studio.md#unlock-editing)；沒人記得金鑰時，見[忘記閘道器管理金鑰](../guides/22-gateway-operations.md#lost-the-management-key) |
| **無法簽發金鑰** | 新閘道器金鑰要繫結的 OpenViking API 金鑰沒有通過校驗。 | [簽發金鑰失敗](#issuing-a-key-fails) |
| 客戶端報錯，請求日誌裡卻沒有這條請求 | 請求在到達服務商之前就被閘道器拒絕了。 | [客戶端收到閘道器返回的錯誤](#clients-get-an-error-from-the-gateway) |
| 請求日誌中某條請求的狀態碼為 400 及以上 | 服務商拒絕了請求或呼叫失敗。 | [上游返回錯誤](#the-upstream-returned-an-error) |
| 某段對話沒有召回，也沒有儲存 | 檢測到 OpenViking 外掛，閘道器把召回、儲存和工具都讓給了外掛。 | 正常行為，避免同一份內容被補充、儲存兩次，見[兩者同時使用時](../guides/15-gateway.md#when-both-are-in-use)。 |
| 請求不帶記憶 | OpenViking 無法訪問或超時、預算用完、沒有相關內容等。 | [沒有補充記憶](#no-memory-is-added) |
| 儲存顯示**重試中**，之後變成**已暫停** | OpenViking 拒絕儲存或無法訪問；或者這段對話的閘道器金鑰已被吊銷（`gateway_key_revoked`），例如使用者的 OpenViking 金鑰被重新生成過。 | OpenViking 恢復後閘道器會自動恢復儲存。金鑰被吊銷時，重新簽發閘道器金鑰，使用者的下一個請求會恢復儲存。見[OpenViking 中看不到對話](#conversations-do-not-appear-in-openviking)。 |
| 上下文配置開啟了工具，對話裡卻沒有 | 還沒有能用工具的請求，第一個能用的請求載入工具清單失敗，客戶端沒有回傳完整歷史，或者客戶端自己接了 OpenViking 工具。 | 在請求日誌裡檢視原因，見[什麼時候不提供工具](04-openviking-tools.md#when-tools-are-not-offered)。客戶端接了 OpenViking MCP 伺服器時出現**客戶端已接入 OpenViking 工具**（`tool_name_collision`）是正常的；其他原因修正後開始新對話。 |
| **首次呼叫快取命中率**下降，或者概覽提示快取連續未命中 | 記憶無法原樣放回、對話換了上游，或者客戶端、中轉服務改動了請求開頭的內容。 | [首次呼叫快取命中率下降](#the-first-call-cache-hit-rate-dropped) |
| 長對話被服務商以過長為由拒絕 | 閘道器不知道模型的實際視窗，壓縮得太晚。 | [長對話超出上下文長度](#long-conversations-hit-the-context-limit) |
| 檔案匯入或下載連結失敗 | 沒有設定 `public_url` 或設定有誤，或者代理沒有轉發檔案相關路徑。 | [檔案匯入或下載失敗](#file-imports-or-downloads-fail) |
| 請求被標上了異常名稱 | 閘道器沒能完整處理這條請求。 | [降級請求的異常](#issues-on-degraded-requests) |

## 閘道器無法啟動 {#the-gateway-does-not-start}

嵌入閘道器無法啟動時，整個 OpenViking Server 都會停止。請在 Server 日誌中找到啟動錯誤（Compose 中用 `docker compose logs openviking`），再對照下表處理。

| 問題（日誌原文） | 原因和處理 |
| --- | --- |
| v0.5 資料缺少舊金鑰（`holds data encrypted by OpenViking Gateway 0.5`） | 儲存目錄裡有 v0.5 閘道器加密的資料，但既沒有 `OPENVIKING_GATEWAY_ENCRYPTION_KEY`，`storage_path` 下也沒有 `encryption.key`。提供原來的金鑰，見[遷移](../guides/22-gateway-operations.md#migration)第 5 步。 |
| 已移除的引數或欄位（`unrecognized argument --…`、`Extra inputs are not permitted`） | 獨立閘道器啟動時用了已移除的 `openviking-gateway` 引數，或者 `gateway.conf` 裡還留著它不接受的欄位，例如 `enabled`。把這些設定移到 `gateway.conf` 或環境變數中，見[遷移](../guides/22-gateway-operations.md#migration)第 2 步。`ov.conf` 的 `gateway` 段裡殘留的舊欄位只會列印 `Ignoring removed gateway settings`，不會阻止啟動。 |
| 管理金鑰太短（`management_key must resolve to at least 32 characters`） | [閘道器管理金鑰](../guides/22-gateway-operations.md#gateway-management-key)至少要 32 個字元；用 `$VAR` 引用的環境變數沒有設定時，也會報這個錯。 |
| 加密設定（`Gateway data is encrypted; configure the encryption settings it was written with`，或加密配置錯誤） | Server 的 `encryption` 段（嵌入）或 `gateway.conf` 的 `encryption` 塊（獨立）缺失、不合法，或者載入不了加密根金鑰。見[加密指南](../guides/08-encryption.md)。 |
| 儲存格式不相容（`Unsupported gateway schema`） | 儲存目錄由不相容的閘道器版本寫入（更舊的版本，或降級前更新的版本）。換一個空的 `storage_path`。 |
| 獨立執行缺少 OpenViking 地址（`OpenViking Gateway needs an OpenViking server URL`） | 執行 `openviking-gateway init`，或者設定 `OPENVIKING_GATEWAY_OPENVIKING_URL`。 |
| 獨立執行找不到配置檔案（`Gateway config file not found`） | `--config` 或 `OPENVIKING_GATEWAY_CONFIG_FILE` 指定的檔案不存在。改正路徑，或者用 `openviking-gateway init --config <路徑>` 生成它。 |
| 獨立執行繫結非迴環地址（`A publicly bound OpenViking Gateway requires a successful synchronous probe`） | 啟動檢查必須連上 OpenViking 並確認它使用 `api_key` 認證，否則閘道器退出。先啟動 OpenViking（在容器中要等它就緒），或者繫結 `127.0.0.1`。 |
| OpenViking 處於 Trusted 模式（`OpenViking Gateway does not support trusted authentication`） | 僅獨立執行：無論繫結什麼地址，啟動檢查都拒絕 OpenViking 的 Trusted 模式。把 OpenViking Server 改為 `api_key` 認證（`server.auth_mode`），見[啟動檢查](../guides/22-gateway-operations.md#startup-checks)。 |

## Studio 顯示設定卡片 {#studio-shows-a-setup-card}

Studio 無法為你載入閘道器時，會用一張設定卡片代替閘道器標籤頁。卡片標題說明了問題所在：

| 卡片 | 處理 |
| --- | --- |
| **這臺 OpenViking 沒有開啟閘道器**（404） | 執行 `openviking-server init` → **Update gateway**，或者在 `ov.conf` 中設定 `gateway.enabled: true` 後重啟，見[在 Server 中啟用](../guides/22-gateway-operations.md#enable-it-in-the-server)。使用 API 金鑰的服務端上，root 也可以直接在卡片上點**開啟閘道器**。帳號管理員和普通使用者看到的卡片只提示聯絡部署者開啟閘道器。 |
| **先連線 OpenViking**，或者 **OpenViking API 金鑰無效**（401） | 點**開啟連線設定**，填入當前的 OpenViking API 金鑰。 |
| **閘道器不支援 Trusted 模式**（`trusted_mode_unsupported`） | 把 Server 改為 `api_key` 認證。 |
| **閘道器連不上 OpenViking**（`openviking_unreachable`） | 只出現在獨立閘道器：檢查 `openviking_url`（`gateway.conf` 或 `OPENVIKING_GATEWAY_OPENVIKING_URL`）和網路。 |
| **無法載入 OpenViking 閘道器** | 其他各種失敗。卡片會顯示閘道器返回的提示；點**重試**，再根據提示到本頁對應的小節排查。 |

**上游**和**上下文配置**標籤頁只讀不屬於設定卡片：這是因為部署者設定了[閘道器管理金鑰](../guides/22-gateway-operations.md#gateway-management-key)（`management_key_required`），而 帳號管理員或 root 的 API 金鑰並不能解鎖編輯。點**輸入閘道器管理金鑰**，見[解鎖編輯](06-manage-in-studio.md#unlock-editing)。服務端更換管理金鑰後（`management_key_invalid`），Studio 會重新鎖定；沒人記得金鑰時，見[忘記閘道器管理金鑰](../guides/22-gateway-operations.md#lost-the-management-key)。

## 簽發金鑰失敗 {#issuing-a-key-fails}

簽發[閘道器金鑰](09-gateway-keys.md#issue-a-key)之前，閘道器會先向 OpenViking 校驗要繫結的 OpenViking API 金鑰。校驗不通過時，**簽發閘道器金鑰**對話方塊會顯示原因，括號裡是管理 API 返回的 `reason`。

| Studio 中的提示 | 原因和處理 |
| --- | --- |
| 服務端只儲存了這個使用者 API 金鑰的雜湊，無法自動讀取。請貼上該使用者的使用者 API 金鑰。（`user_key_unreadable`） | OpenViking Server 只儲存了金鑰雜湊（`encryption.api_key_hashing.enabled`）。在**貼上使用者 API 金鑰**中填入該使用者自己的金鑰。 |
| 這是 Root API 金鑰，請改用本帳號中某個使用者的使用者 API 金鑰。（`root_key_not_allowed`） | root API 金鑰不能繫結到閘道器金鑰，改用某個使用者或帳號管理員的 API 金鑰。本地 dev 模式的 `default/default` 不受此限。 |
| root API 金鑰不屬於任何使用者，請選擇這把金鑰對應的使用者。（`user_required`） | 你以 root 身份登入 Studio，既沒有選擇使用者，也沒有貼上金鑰。選擇使用者，或者貼上該使用者的金鑰。 |
| 這個 OpenViking API 金鑰屬於其他帳號。（`other_account`） | 金鑰所屬的帳號不是你在 Studio 中管理的帳號。 |
| OpenViking 拒絕了這個金鑰。（`openviking_http_401`、`openviking_http_403`） | 金鑰不完整、已被重新生成，或者使用者已被刪除。使用該使用者當前的金鑰。 |
| OpenViking 無法識別這個金鑰所屬的使用者（`openviking_identity_missing`） | OpenViking 沒有返回這個金鑰對應的使用者。使用本帳號中某個使用者的金鑰。 |
| 閘道器連不上 OpenViking，無法校驗這個金鑰。（`openviking_unavailable`） | 閘道器訪問不到 OpenViking；獨立閘道器檢查 `openviking_url`。 |
| OpenViking 版本低於閘道器的要求。（`openviking_version_mismatch`） | 僅獨立閘道器：OpenViking Server 低於 `min_server_version`（0.4.16），請升級。從原始碼安裝、沒有版本標籤的服務可能報告 `0.1.dev123` 這樣的開發版本號；請安裝正式版本，或者把 `min_server_version` 改成與之匹配的值。 |
| 沒有執行此操作的許可權。（`forbidden`） | 貼上的 OpenViking API 金鑰不屬於對話方塊中選中的使用者，例如管理員貼上了自己的金鑰，而不是所選使用者的。請貼上所選使用者自己的金鑰，或者改選金鑰所屬的使用者。普通使用者貼上的金鑰不是自己的，也會報這個錯。 |
| 這個使用者已不在本帳號中，請重新選擇。（`unknown_user`） | 對話方塊開啟期間，所選使用者被移出了本帳號。`unknown_policy` 和 `unknown_upstream` 同理，分別表示所選的上下文配置或上游已被刪除。重新整理後重新選擇。 |

## 客戶端收到閘道器返回的錯誤 {#clients-get-an-error-from-the-gateway}

閘道器在轉發每個客戶端請求之前，會先檢查閘道器金鑰、模型和是否有匹配的上游。下面這些拒絕都發生在請求到達服務商之前，所以不會出現在請求日誌裡。服務商自己返回的錯誤見[上游返回錯誤](#the-upstream-returned-an-error)。

| 狀態碼和提示 | 原因和處理 |
| --- | --- |
| 401 "Invalid gateway key. It may have been revoked, or removed because its OpenViking API key was regenerated…" | 客戶端沒有傳送閘道器金鑰，傳送了已吊銷的金鑰或服務商的 API Key，或者使用者的 OpenViking API 金鑰重新生成後，閘道器刪除了這把金鑰。檢查客戶端實際傳送的金鑰，必要時[重新簽發](09-gateway-keys.md#issue-a-key)。 |
| 403 "Claude subscription OAuth credentials are not supported" | 客戶端傳送了 Claude 訂閱令牌，例如 Claude Code 用訂閱帳號登入且沒有設定 `ANTHROPIC_AUTH_TOKEN`；或者上游儲存的就是訂閱令牌。請改用 API Key。 |
| 403 "Model is not allowed by this key" | 模型不在金鑰[允許的模型](09-gateway-keys.md#allowed-models)範圍內。簽發一把允許這個模型的金鑰。 |
| 400 "Request model is missing"、415 "Compressed request bodies are not supported" | 只出現在限定了模型的金鑰上：請求體必須寫明模型，且不能經過壓縮編碼。 |
| 404 "This upstream is an exact endpoint for … only" | 金鑰繫結的上游關閉了**拼接協議介面路徑**（見[直接發往完整請求地址](07-upstreams.md#exact-endpoint)），只接受該協議的介面地址，而客戶端呼叫了別的路徑，例如 `/v1/models`。 |
| 404 "No allowed upstream matches this protocol and model" | 金鑰繫結的已啟用上游中，沒有一個使用客戶端呼叫的 API 並提供所請求的模型。檢查上游的協議、模型和別名、是否啟用，以及金鑰綁定了哪些上游。 |
| 401 "Upstream API key is missing" | 上游要求每個客戶端在 `X-OpenViking-Upstream-Key` 中自帶 API Key，或者由閘道器保管 API Key 的上游沒有填寫。見[憑證](07-upstreams.md#credentials)。 |
| 403 "Coding Plan upstreams are disabled; configure a model API key" | 上游被標記為 [Coding Plan 金鑰](07-upstreams.md#coding-plan-keys)。改用模型 API Key，或者有意勾選**允許通過閘道器使用這個套餐**。 |
| 403 "Context policy is unavailable" | 金鑰繫結的上下文配置已不存在。用現有的上下文配置重新簽發金鑰。 |
| 404 "Unknown response for this key"、403 "Response upstream is no longer allowed" | 查詢的 Responses 響應不是這把金鑰建立的，或者建立它的上游已停用、不再繫結到這把金鑰。 |
| 413 "Request exceeds configured body limit" | 請求體超過了 `max_body_bytes`（見[請求大小上限](05-long-conversations.md#side-effects)），或者超過了代理自己的上限。 |
| 426 | 對 Responses API 發起了 WebSocket 連線。這是預期行為，Codex 會改用 HTTP。 |
| 502 "Model upstream is unavailable" | 閘道器連不上服務商，或者呼叫超過了 `upstream_timeout_seconds`。在上游上點**測試**（見[測試和刪除](07-upstreams.md#test-and-delete)）。 |

"Hidden tool request timed out"（504）發生在呼叫服務商之後，會記入請求日誌，見[失敗處理](04-openviking-tools.md#failure-handling)。

## 上游返回錯誤 {#the-upstream-returned-an-error}

上游錯誤是服務商自己返回的錯誤。它在**請求日誌**標籤頁中的那一行，HTTP 狀態碼為 400 及以上，又沒有閘道器異常，詳情裡寫著**上游返回了 HTTP …，客戶端收到了這個錯誤。**閘道器把服務商的錯誤原樣交給了客戶端。

常見原因有 API Key 填錯或過期、服務商不認識這個模型名、觸發限流或額度用完、對話超出了模型的上下文視窗，或者服務商故障。在[上游](07-upstreams.md#test-and-delete)上點**測試**，再和客戶端收到的錯誤對照。上下文長度相關的錯誤見[長對話超出上下文長度](#long-conversations-hit-the-context-limit)。

## OpenViking 異常 {#openviking-is-degraded}

“概覽”標籤頁上的 **OpenViking** 卡片顯示閘道器最近一次檢查 OpenViking 的結果。**已連線**表示正常，其他狀態如下：

- **啟動中**：閘道器還沒完成第一次檢查。嵌入閘道器每秒檢查一次，直到 OpenViking 啟動。稍後重新整理即可。
- **異常**：最近一次檢查失敗，卡片會寫明原因：

| 原因 | 處理 |
| --- | --- |
| OpenViking 無法訪問或響應超時（`openviking_unavailable`） | OpenViking 沒有執行或無法訪問。獨立閘道器檢查 `openviking_url` 和網路。 |
| OpenViking 返回了 HTTP …（`openviking_http_<status>`），或 OpenViking 報告了錯誤 …（`openviking_<CODE>`） | OpenViking 返回了錯誤。檢視 OpenViking Server 的日誌。 |
| `trusted_mode_unsupported` | OpenViking 使用 Trusted 模式。把它改為 `api_key` 認證。 |

OpenViking 異常期間，請求照常發給模型，只是不帶記憶；儲存對話會一直重試，直到 OpenViking 恢復。閘道器會以逐漸拉長的間隔重新檢查，最長間隔為 `health_interval_seconds`（預設 60 秒）。

## 沒有補充記憶 {#no-memory-is-added}

[召回](08-context-profiles.md#recall-memory)會在每條新的使用者訊息到達時檢索 OpenViking，把找到的內容補充進去；沒有補充時，請求日誌會寫明原因。先在**請求日誌**標籤頁裡找到這個請求。找不到，說明客戶端沒有經過閘道器，或者請求被閘道器拒絕了（見[客戶端收到閘道器返回的錯誤](#clients-get-an-error-from-the-gateway)）。找到後展開它，檢視詳情中的**召回**：

| 召回結果 | 含義 | 處理 |
| --- | --- | --- |
| **沒有找到相關內容**（`empty`） | 新使用者通常如此。對話提交、OpenViking 提取之後才會有記憶。 | 繼續使用即可；一直沒有記憶時，見[OpenViking 中看不到對話](#conversations-do-not-appear-in-openviking)。 |
| **召回已關閉或預算已用完**（`disabled`） | 上下文配置關閉了召回，當前上下文視窗剩下的召回預算不足 64 token，或者訊息短於 3 個字元。 | 召回被關閉時，在上下文配置中開啟。 |
| **剩餘預算不足，未補充記憶**（`budget`） | 這條訊息的召回預算扣掉記憶塊的包裝後，留給檢索結果的不足 64 token，所以沒有檢索。可能是這段對話快用完了**單個上下文視窗預算**（進入下一個上下文視窗後重新計算，例如壓縮之後），也可能是**單條訊息預算**設得太低，接近 64 token 的下限。 | **單條訊息預算**接近下限時，調大它。 |
| **OpenViking 無法訪問或響應超時**（`openviking_unavailable`）、**召回超時**（`recall_timeout`） | 檢索沒有完成。 | 檢視 OpenViking 卡片（見[OpenViking 異常](#openviking-is-degraded)）。OpenViking 在執行但響應慢時，調長**超時時間**。 |
| **OpenViking 拒絕了這個金鑰**（`openviking_http_401`） | 使用者的 OpenViking 金鑰已失效。 | 用當前的金鑰簽發新的閘道器金鑰，見[使用者的 OpenViking API 金鑰變了](09-gateway-keys.md#when-the-openviking-key-changes)。 |
| **OpenViking 返回了 HTTP …**（`openviking_http_<status>`）或 **OpenViking 報告了錯誤 …**（`openviking_<CODE>`） | 檢索在 OpenViking 內部失敗。OpenViking Server 低於 `min_server_version` 時也可能這樣失敗。 | 檢視 OpenViking Server 的日誌。 |
| **檢測到 OpenViking 外掛**（`plugin_present`） | 閘道器發現了 OpenViking 外掛，讓出了這段對話。 | 正常行為，見[兩者同時使用時](../guides/15-gateway.md#when-both-are-in-use)。 |
| **型別**不是**新訊息** | 工具步驟、輔助請求和子 Agent 請求從不檢索，它們放回之前的訊息得到的記憶。 | 無需處理，見[請求型別](10-overview-and-requests.md#request-types)。 |

檢索失敗的訊息之後也不會補上記憶；下一條訊息會重新檢索。

## OpenViking 中看不到對話 {#conversations-do-not-appear-in-openviking}

[儲存](08-context-profiles.md#save-conversations)會把每一輪完成的對話寫進名為 `gateway-…` 的 OpenViking 會話，會話屬於閘道器金鑰背後的 OpenViking 使用者。預期中的某一輪沒有出現時，對照下表：

| 看到的情況 | 原因 | 處理 |
| --- | --- | --- |
| 缺少最新的一輪 | 儲存晚一輪：下一條訊息到達時，上一輪才會出現；最後一輪要等**最新回覆等待時長**（預設 10 分鐘）。 | 稍等，或者傳送下一條訊息。 |
| **儲存**列顯示**已關閉** | 上下文配置不儲存對話。 | 在上下文配置中開啟儲存；修改只對新對話生效（見[修改何時生效](06-manage-in-studio.md#when-changes-take-effect)）。 |
| **重試中**或**已暫停** | 儲存失敗，展開的行會顯示原因。 | 修復原因（例如讓 OpenViking 恢復訪問）後，閘道器會在 5 分鐘內重試。原因為 `gateway_key_revoked` 時，重新簽發閘道器金鑰，下一個請求會恢復儲存。對話一直暫停時，用**重新同步對話…**（見[重新同步對話](10-overview-and-requests.md#resync-a-conversation)）。 |
| **檢測到 OpenViking 外掛**（`plugin_present`） | 檢測到 OpenViking 外掛的對話，閘道器不儲存任何內容。 | 正常行為；同一個客戶端在外掛和閘道器之間二選一。 |
| 會話裡只有部分對話 | 以下情況下，閘道器會把當前歷史寫進新的 `gateway-…` 會話：客戶端編輯、重新生成或壓縮了歷史（`history_changed`、`history_changed_during_delivery`），已在**最新回覆等待時長**之後儲存的一輪又繼續了（`continued_after_idle`），或者有人用了**重新同步對話…**（`manual_reset`）。之前的輪次留在舊會話裡。 | 到舊會話裡找，見[儲存狀態](10-overview-and-requests.md#saving-status)。 |
| 完全看不到 `gateway-…` 會話 | 你檢視時用的 OpenViking 使用者，不是閘道器金鑰背後的那個使用者。 | 換成那個使用者檢視。 |
| 會話出現了，記憶還沒有 | OpenViking 在提交之後才在後臺提取記憶。 | 等提取完成。 |

## 首次呼叫快取命中率下降 {#the-first-call-cache-hit-rate-dropped}

“概覽”標籤頁上的**首次呼叫快取命中率**，是每條新使用者訊息的第一次模型呼叫中，命中服務商[提示詞快取](01-how-it-works.md#replay)的輸入 token 所佔的比例。正常情況下它接近不經過閘道器時服務商能達到的水平，所以先和這個水平比較，再看最近請求上標出的異常和概覽上的提示：

| 看到的情況 | 原因 | 處理 |
| --- | --- | --- |
| **記憶記錄缺失**（`missing_injection_record`） | 閘道器儲存丟失、從舊備份恢復，或者記錄已過期，之前補充的記憶無法放回。 | 無需處理，進行中的對話在一次未命中之後就會恢復。 |
| **上游已切換**（`upstream_changed`） | 對話原來的上游被停用、沒有繫結到客戶端當前用的金鑰，或者不再提供這個模型，於是對話轉到了另一個上游。 | 重新啟用這個上游，或者讓客戶端改用包含它的金鑰，見[路由](07-upstreams.md#routing)。 |
| **快取引數有變化**（`ark_cache_parameters_changed`） | 在火山方舟或 BytePlus 方舟上，客戶端在同一段對話裡改變了模型、思考模式、取樣引數、系統提示詞或工具。 | 在同一段對話裡保持這些引數不變。 |
| 沒有標出異常 | 客戶端本身可能每輪都在改動之前的訊息或系統提示詞，例如插入當前時間，閘道器無法修正。每次壓縮、模型每次開啟新的上下文視窗，也都會造成一次未命中，這是預期內的。 | 檢查客戶端的系統提示詞裡有沒有每次都變的內容。 |
| **有 … 段長對話連續沒有命中提示詞快取**，或者命中率一直是 0%，而服務商或中轉服務後臺的快取記錄有命中 | 上游沒有把快取用量傳回閘道器，例如中轉服務轉換協議時丟掉了快取欄位。閘道器讀取 `cache_read_input_tokens`、`prompt_tokens_details.cached_tokens`、`input_tokens_details.cached_tokens`、`prompt_cache_hit_tokens` 等常見欄位。 | 讓中轉服務把快取用量原樣傳回。 |
| 同上，或者提示**上游 … 最近沒有返回過快取命中**，而服務商後臺也沒有命中 | 根本沒有用上快取。 | 檢查服務商是否支援提示詞快取、Anthropic 客戶端是否設定了 `cache_control`，以及中轉服務是否在多個帳號或渠道之間輪換。 |

## 長對話超出上下文長度 {#long-conversations-hit-the-context-limit}

[壓縮](05-long-conversations.md#long-conversations)會在長對話佔滿模型上下文視窗之前，用一份摘要替換較早的歷史。服務商仍以對話過長為由拒絕請求時，通常是下面三種原因之一：

| 原因 | 處理 |
| --- | --- |
| 閘道器不知道模型的視窗大小：上游的**上下文視窗**裡沒有這個模型，上下文配置也沒有設定**預設上下文視窗**，閘道器就按預設的 1,000,000 token 計算，對視窗更小的模型壓縮得太晚。 | 補上模型的視窗大小，見[設定模型的上下文視窗](05-long-conversations.md#context-window)。 |
| 對話所用的上下文配置關閉了壓縮。 | 開啟壓縮；修改上下文配置只對新對話生效（見[修改何時生效](06-manage-in-studio.md#when-changes-take-effect)）。 |
| 壓縮失敗。請求詳情會顯示**壓縮失敗**及下表中的某個原因。 | 見下表。 |

| 原因 | 說明和處理 |
| --- | --- |
| `summary_incomplete` | 摘要回復沒有正常結束，通常是碰到了長度上限。調大**摘要長度上限**。 |
| `summary_http_<status>` | 摘要請求被拒絕，可能來自上游，也可能是閘道器在傳送前就攔下了（沒有上游 API Key，或 Coding Plan 檢查不通過）。檢查上游的 API Key、模型和 Coding Plan 設定。狀態碼為 400 時，閘道器已經去掉額外的輸出餘量重試過一次。 |
| `summary_unavailable` | 上游無法訪問、超時（`upstream_timeout_seconds`），或者返回的不是 JSON。 |
| `summary_tool_call`、`summary_empty` | 模型呼叫了工具，或者沒有返回文本，而不是寫出摘要。 |
| `cut_not_found` | 客戶端最新的訊息和閘道器存下的歷史對不上，閘道器無法確定截斷點。通常是暫時的。 |
| `summary_failed` | 意外的內部錯誤。在閘道器日誌裡查詢 "OpenViking Gateway summary failed"。 |
| `still_over_threshold` | 摘要已經寫好並保留，但用量仍達到**壓縮時機**：系統提示詞、工具和摘要本身就佔滿了大部分視窗。調小**摘要長度上限**，或者檢查模型的上下文視窗設定。 |

除 `still_over_threshold` 外，其他原因下這次請求都傳送了完整歷史。無論哪種原因，閘道器都會等 60 秒再嘗試壓縮這段對話。

## 檔案匯入或下載失敗 {#file-imports-or-downloads-fail}

[匯入檔案](04-openviking-tools.md#import-files-and-skills)時，閘道器會在自己的[對外地址](../guides/22-gateway-operations.md#public-address)上給客戶端生成上傳和下載連結。對照看到的錯誤處理：

| 錯誤 | 處理 |
| --- | --- |
| "Set gateway.public_url for client uploads and downloads" | 把 `public_url` 設為客戶端能訪問的地址，或者把 `mcp_file_links` 設為 `direct`。 |
| 上傳或下載連結無法訪問或返回 404 | 確認 `public_url` 不是舊的 `:1935` 地址，也沒有以 `/gateway` 結尾，並且代理像其他路徑一樣轉發 `/gateway/uploads` 和 `/gateway/downloads`。`mcp_file_links` 設為 `direct` 時，改查 Server 的 `OPENVIKING_PUBLIC_BASE_URL`。 |
| 413 "Upload exceeds configured body limit" | 檔案超過了 `max_body_bytes` 或代理的上限。 |
| 502 "OpenViking upload is unavailable" 或 "OpenViking download is unavailable" | 閘道器連不上 OpenViking Server。 |
| 模型沒有匯入工具 | OpenViking 服務沒有提供該工具，上下文配置沒有勾選，或者當前請求不能使用閘道器工具。檢查工具清單和請求詳情。 |

## 降級請求的異常 {#issues-on-degraded-requests}

降級請求是閘道器沒能完整處理的請求，“請求日誌”和“概覽”標籤頁會把它標出來。Studio 顯示異常名稱，括號裡是管理 API 中對應的值：

| 異常 | 發生了什麼 | 怎麼處理 |
| --- | --- | --- |
| 記憶不可用（`memory_store_failure`） | 閘道器無法讀寫自己的儲存，或者該使用者的閘道器資料剛被刪除。請求不帶記憶發給了模型；Claude 對話中之前的思考內容被去掉。 | 檢查磁碟空間、許可權和閘道器日誌。剛[刪除過該使用者的閘道器資料](09-gateway-keys.md#delete-a-users-gateway-data)時出現屬於正常。 |
| 原樣轉發（`unsafe_json`） | 請求中有無法精確重新編碼的數字或重複的鍵，閘道器逐位元組原樣轉發，沒有補充記憶。 | 通常只與某個客戶端有關，閘道器這邊無需調整。 |
| 上游已切換（`upstream_changed`） | 對話原來的上游無法再服務，轉到了另一個上游，造成一次快取未命中，之前的 Claude 思考內容也被去掉。 | 重新啟用這個上游，或者讓客戶端改用包含它的金鑰；也可以接受這次切換。 |
| 記憶記錄缺失（`missing_injection_record`） | Claude 對話中，之前補充的記憶已經沒有記錄，之前的思考內容被去掉一次。 | 儲存丟失後，或者在很久以前的對話裡出現，都在預期之內。反覆出現時，開始新對話。 |
| 檢測到 OpenViking 外掛（`plugin_present`） | 檢測到 OpenViking 外掛，這段對話不再使用閘道器記憶。 | 使用外掛時出現屬於正常。同一個客戶端在外掛和閘道器之間二選一。 |
| 快取引數有變化（`ark_cache_parameters_changed`） | 在火山方舟或 BytePlus 方舟上，影響快取的引數與對話的第一個請求不同，提示詞快取很可能沒有命中。 | 在同一段對話裡保持模型、思考模式、取樣引數、系統提示詞和工具不變。 |
| 工具歷史無法繼續使用（`hidden_tool_history_unavailable`） | Claude 對話用過 OpenViking 工具，但當前請求不能使用這些工具，之前的思考內容已被去掉。 | 檢視請求詳情中的工具停用原因，恢復原設定，或者開始新對話。 |
| OpenViking 工具呼叫失敗（`hidden_tool_loop_failed`） | 模型使用 OpenViking 工具時未能完成回答，客戶端收到錯誤。 | 見[失敗處理](04-openviking-tools.md#failure-handling)。 |
| 模型未返回回答（`hidden_reply_without_anchor`） | 模型在這次請求中使用了 OpenViking 工具，但沒有返回可用於繼續對話的內容。客戶端仍收到了回覆，但下一輪無法沿用這次工具呼叫的結果。 | 重試本次提問，或開始一段新對話。 |
| 回覆未儲存（`capture_parse_failure`） | 流式回覆無法解析，這條回覆沒有儲存，客戶端不受影響。 | 無需處理，僅供瞭解。 |
| 金鑰未校驗（`revocation_check_unavailable`） | OpenViking 無法確認這把閘道器金鑰，請求在沒有檢查是否已吊銷的情況下照常處理。 | 檢查 OpenViking 是否可達、執行是否正常。 |

## 下一步 {#next-steps}

- [閘道器概覽與請求日誌](10-overview-and-requests.md#requests)：瞭解請求日誌中每一列、每個標籤和每種儲存狀態的含義。
- [觀測](../guides/22-gateway-operations.md#monitoring)：用 `/health` 檢查存活，通過管理 API 檢視閘道器狀態，在使用者發現問題之前先察覺。
- [配置參考](13-configuration.md#gateway-fields)：查詢本頁提到的 `max_body_bytes`、`public_url`、`min_server_version` 等欄位。
