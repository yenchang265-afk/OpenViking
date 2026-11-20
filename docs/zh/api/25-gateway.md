# OpenViking 閘道器管理 API

管理 API 用來檢視許可權、配置上游和上下文配置、簽發閘道器金鑰、讀取用量和日誌。所有路徑都以 `/gateway/admin/` 開頭，由閘道器直接提供：閘道器在 OpenViking Server 內執行時，訪問 Server 的埠（預設 1933）；獨立執行時，訪問閘道器自己的埠（預設 1935）。示例中的 `SERVER_URL` 指這個地址本身，不帶路徑，例如 `http://127.0.0.1:1933`。

模型客戶端不呼叫這組介面。它們用閘道器金鑰訪問 `/gateway/v1/*`、`/gateway/api/v3/*` 或 `/gateway/api/compatible/v1/*`，見[OpenViking 閘道器](../gateway/03-connect-clients.md#connect-clients)。

## 憑證和帳號範圍 {#credentials-and-account-scope}

每個管理請求都要帶 OpenViking API 金鑰，放在 `X-API-Key` 或 `Authorization: Bearer` 中。閘道器向 OpenViking 確認這把金鑰屬於哪個帳號、哪個使用者、什麼角色，確認結果最多快取 30 秒。本地 dev 模式不需要金鑰，呼叫方固定為 root 身份 `default/default`。閘道器不支援 trusted 認證。

上游和上下文配置（API 中叫 `policies`）屬於帳號，同一帳號的使用者共用。請求預設作用於呼叫方所在的帳號；root 可以用 query 引數 `account_id` 指定其他帳號，admin 和 user 只能訪問自己的帳號。

部署者可以另外設定閘道器管理金鑰（配置方法見[閘道器管理金鑰](../guides/22-gateway-operations.md#gateway-management-key)）。設定之後，修改上游和上下文配置的請求必須在 `X-OpenViking-Gateway-Management-Key` 中帶上它，OpenViking 的 admin 和 root 也不例外。請求帶了管理金鑰但值不對時，閘道器直接返回 401 `management_key_invalid`，不會降級成只讀請求。

| 操作 | 未設定管理金鑰 | 已設定管理金鑰 |
| --- | --- | --- |
| 讀取上游和上下文配置 | 本帳號的任何使用者 | 本帳號的任何使用者；單獨持有管理金鑰也可以，並能指定任意帳號 |
| 建立、修改或刪除上游和上下文配置；測試上游 | 本帳號的任何使用者 | 只有帶正確管理金鑰的請求 |
| 匯入 OpenViking 的模型配置 | 嵌入部署中的 root（包括本地 dev） | 只有帶正確管理金鑰的請求，且只限嵌入部署 |
| 簽發、讀取、吊銷閘道器金鑰，重置儲存 | user 只能操作自己的金鑰；admin 操作本帳號；root 操作所選帳號 | 同左，管理金鑰不增加任何許可權 |
| 讀取日誌和概覽 | user 只看自己的；admin 和 root 看整個帳號 | 同左，始終需要 OpenViking 身份 |
| 刪除某個使用者的閘道器資料 | 本帳號的 admin，或 root | 同左 |
| 刪除整個帳號的閘道器資料 | root | 同左 |

管理金鑰可以不帶 OpenViking API 金鑰單獨使用，適合自動化指令碼：它能讀寫上游和上下文配置、呼叫 `/access`，用 `account_id` 指定帳號（省略時為 `default`）。簽發金鑰、讀取日誌和概覽始終需要 OpenViking 身份；兩種憑證同時提供，也不會讓這些操作獲得更高的許可權。設定、更換或去掉管理金鑰都不影響已簽發的閘道器金鑰。

只讀檢視不返回上游的 API Key、請求頭的值和請求頭名稱，只保留 `has_api_key` 和 `auth_mode`。

## 許可權與發現 {#access-and-discovery}

| 方法 | 路徑 | 返回 |
| --- | --- | --- |
| GET | `/gateway/admin/access` | 呼叫方的許可權：`managed`、`can_write_objects`、`can_import_vlm`、`can_issue_for_others`、`role`、`account_id`、`user_id`、`warnings` |
| GET | `/gateway/admin/overview` | 呼叫方可見的最近 10,000 條日誌彙總：用量、快取命中、召回、儲存異常、OpenViking 狀態和日誌保留期 |
| GET | `/gateway/admin/logs` | 呼叫方可見的最新日誌，以 JSON 陣列返回，最新的在前；`limit` 預設 200，取值 1–1000。欄位見[日誌記錄](#log-records)。 |
| GET | `/gateway/admin/guides` | 客戶端接入地址 `base_url`，以及 `public_url_configured`；`base_url` 是 `public_url` 加 `/gateway`，未設定 `public_url` 時取請求的來源地址加 `/gateway` |
| GET | `/gateway/admin/tools` | 呼叫方能用的 OpenViking 工具：名稱、描述和 annotations，用呼叫方自己的 OpenViking 金鑰讀取（OpenViking 拒絕 root 訪問 `/mcp`，所以 root 改用本帳號已簽發閘道器金鑰對應的 OpenViking 金鑰，沒有時返回上次讀到的目錄） |

Studio 只根據 `/access` 決定顯示哪些按鈕，自己寫的管理工具也應這樣做。獨立閘道器連線公共 OpenViking 服務且沒有設定管理金鑰時，`warnings` 中會出現 `public_openviking_without_management_key`。它只是告警，不限制任何操作。

```bash
curl "$SERVER_URL/gateway/admin/access" \
  -H "X-API-Key: $OPENVIKING_API_KEY"
```

```json
{
  "managed": true,
  "can_write_objects": false,
  "can_import_vlm": false,
  "can_issue_for_others": true,
  "role": "admin",
  "account_id": "team",
  "user_id": "alice",
  "warnings": []
}
```

OpenViking 拒絕 API 金鑰時，返回 401 `openviking_http_401`。

### 日誌記錄 {#log-records}

日誌只記後設資料，不含訊息內容、金鑰和錯誤資訊。發往模型路由的每個請求（`.../models` 除外）無論怎樣結束都恰好寫一條記錄：正常回復、被閘道器拒絕、服務商失敗、流式回覆中途斷開，或者客戶端提前離開。使用預設的 `request_log_sink: store` 時，金鑰確認之前就失敗的請求沒有帳戶，不會儲存；`stdout` 和 `file` 輸出會照常寫出，`account` 和 `user_id` 為 `null`。欄位不適用時省略。

| 欄位 | 含義 |
| --- | --- |
| `time` | 記錄寫入時間，Unix 時間戳（秒） |
| `event`、`schema` | 請求記錄為 `request` 和 `2` |
| `request_id` | 閘道器為請求分配的 ID；模型路由的錯誤響應體裡也帶有它 |
| `received_at`、`method`、`endpoint` | 閘道器收到請求的時間（Unix 時間戳，秒）、HTTP 方法，以及 `messages`、`count_tokens`、`chat`、`responses`、`responses_item` 或 `other` |
| `kind` | `user`、`continuation`、`auxiliary`、`subagent`、`count` 或 `passthrough`，見[請求日誌](../gateway/10-overview-and-requests.md#requests) |
| `model`、`stream` | 客戶端傳送的模型名，以及是否要求流式回覆 |
| `status` | 客戶端收到的 HTTP 狀態碼：閘道器轉發的是服務商的狀態碼，閘道器自身的錯誤是閘道器的狀態碼，客戶端在收到任何響應前離開時為 `499` |
| `upstream_attempted`、`upstream_status` | 閘道器是否向服務商發出了請求（包括壓縮摘要請求），以及服務商應答時的 HTTP 狀態碼 |
| `error_reason`、`error_origin`、`error_class` | 任何失敗（包括已返回 `200` 後中斷的流）的[原因](#model-route-errors)、來源（`gateway`、`openviking`、`upstream` 或 `client`）和大類（`api_key_invalid`、`quota_or_order`、`openviking_unavailable`、`config_error`、`gateway_internal`、`timeout`、`model_error` 或 `client_cancelled`）。閘道器原樣轉發的服務商錯誤為 `upstream_error` |
| `upstream_error_code` | 服務商錯誤響應體或其流中錯誤事件的 `code`（沒有時取 `type`），僅當它是簡短識別符號時記錄；從不記錄錯誤資訊 |
| `stream_error`、`client_disconnected` | 已開始的響應體沒有正常結束的原因（`upstream_timeout`、`upstream_disconnected`、服務商傳送了錯誤事件時為 `upstream_event`、`client_disconnected`、某個 `tool_*` 原因或 `internal_error`）；客戶端離開時後者為 `true` |
| `upstream_id`、`credential_id`、`openviking_account` | 處理請求的上游、發出請求的閘道器金鑰，以及金鑰背後的 OpenViking 帳戶 |
| `session`、`protocol` | 對話及其協議，[重置儲存](#gateway-keys)時要用 |
| `peer` | 請求的 [Peer](../gateway/03-connect-clients.md#peer)，來自 `X-OpenViking-Actor-Peer` 或金鑰的預設 Peer |
| `degradation` | 異常程式碼，見[降級請求的異常](../gateway/12-troubleshooting.md#issues-on-degraded-requests) |
| `degradations` | 請求的全部異常，按發生順序。還可能含 `recall_failed`：記憶檢索沒有得到 OpenViking 的應答（原因見 `recall_reason`），它不會寫入 `degradation`；以及 `prepare_timeout`：補充記憶超過了 `prepare_timeout_seconds` |
| `revocation_reason` | 出現 `revocation_check_unavailable` 時，OpenViking 無法確認金鑰的原因 |
| `session_source` | 對話是怎樣確定的：`header`（`X-OpenViking-Session`）、`reply_match`（歷史延續了某個對話的回覆）或 `new` |
| `recall_reason`、`recall_count`、`recall_ms` | 記憶檢索的結果程式碼、補充的條數和檢索耗時，見[沒有補充記憶](../gateway/12-troubleshooting.md#no-memory-is-added) |
| `replay_hits` | 原樣放回記憶的歷史訊息數 |
| `capture_status`、`capture_reason` | 儲存狀態：`active`、`disabled`，或者這次請求結束了一輪、寫入 OpenViking 卻失敗時為 `failed`；以及原因：失敗時為失敗原因（例如 `openviking_http_503`、`openviking_unavailable`、`openviking_circuit_open`、`save_timeout` 或 `save_failed`），否則為對話記下的原因（例如 `manual_reset`）。見[儲存狀態](../gateway/10-overview-and-requests.md#saving-status) |
| `capture_messages`、`openviking_session` | 這次請求儲存了一輪時，寫入 OpenViking 的訊息數和 OpenViking 會話 ID |
| `tool_skip_reason` | 請求沒有拿到 OpenViking 工具的原因，見[什麼時候不提供工具](../gateway/04-openviking-tools.md#when-tools-are-not-offered) |
| `tool_stop_reason` | 工具 Token 預算用完、後續呼叫被拒絕時為 `token_budget`，見[上限](../gateway/04-openviking-tools.md#limits) |
| `compaction_failed` | 壓縮失敗的原因（`still_over_threshold` 時摘要已保留），見[長對話超出上下文長度](../gateway/12-troubleshooting.md#long-conversations-hit-the-context-limit) |
| `context_tokens`、`context_window` | 估算的上下文大小，以及用來比較的上下文視窗 |
| `input_tokens`、`output_tokens`、`cached_tokens`、`cache_write_tokens` | 本次請求所有服務商呼叫（含 OpenViking 工具輪次）的 token 用量合計。`input_tokens` 已包含快取命中和快取寫入的 token。 |
| `duration_ms` | 從把請求發給服務商到回覆結束的耗時 |
| `read_ms`、`auth_ms`、`route_ms`、`prepare_ms` | 讀取請求體、檢查金鑰（含向 OpenViking 確認）、選擇上游、準備記憶（含檢索和壓縮）的耗時 |
| `added_ms`、`upstream_ttfb_ms`、`first_chunk_ms`、`total_ms` | 從收到請求到開始請求服務商、從開始請求到收到服務商響應頭、從收到請求到第一段流式資料送達客戶端、從收到請求到寫入記錄的耗時 |
| `compaction_ms` | 壓縮耗時，壓縮失敗時也記錄 |
| `bookkeeping_failed` | 回覆發出後失敗的步驟：`completed`（記下這次回覆的用量和狀態）或 `responses`（記住 Responses ID）。儲存失敗不在這裡，見 `capture_status` |

以 `first_upstream_` 和 `hidden_upstream_` 開頭的欄位把 token 用量拆成首次服務商呼叫和 OpenViking 工具輪次兩部分，首次呼叫快取命中率按前者計算。

`/overview` 由這些記錄彙總而來。除用量和快取資料外，還返回 `degradations`（異常程式碼 → 次數）、`capture_issues`（`{"failed": n}`：最新一條記錄顯示這一輪沒有儲存成功的對話數）、`cache_alerts`、`openviking`（OpenViking 的 `status`，降級時另有 `reason`）和 `log_retention_days`。

### 狀態行 {#status-line}

`snapshot_interval_seconds` 大於零時，每個閘道器程序按這個間隔寫一行 JSON；寫到哪裡見[狀態行](../guides/22-gateway-operations.md#status-line)。使用 `store` 輸出時，由 `openviking_gateway.snapshot` logger 以 INFO 級別輸出，宿主沒有配置日誌 handler 時寫到 stderr。計數覆蓋同一程序距上一行的這段時間。狀態行從不包含帳戶、使用者、會話、模型或請求 ID。

```json
{"event": "snapshot", "schema": 1, "time": 1794787200.0, "interval_s": 60.0,
 "uptime_s": 8640.2, "version": "0.5.6",
 "inflight_requests": 12, "inflight_streams": 9,
 "requests": 480, "errors": {"upstream_timeout": 2, "store_unavailable": 1},
 "degradations": {"recall_failed": 4},
 "stream_errors": {"client_disconnected": 3},
 "rejected_overload": 0,
 "records_unlogged": 0, "records_failed": 0, "records_dropped": 0,
 "store_errors": 1,
 "openviking": {"state": "ok", "reason": "", "open_circuits": 0},
 "capture": {"delivered": 18, "failed": 0}}
```

| 欄位 | 含義 |
| --- | --- |
| `time`、`interval_s`、`uptime_s`、`version` | 寫入時間（epoch 秒）、距上一行的秒數、程序已執行的秒數，以及安裝的 OpenViking 版本 |
| `inflight_requests`、`inflight_streams` | 寫入時從收到到響應結束之間的模型請求數，以及其中正在流式回覆的請求數 |
| `requests` | 這段時間寫出的請求記錄數 |
| `errors`、`degradations`、`stream_errors` | 這些記錄按 `error_reason`、按 `degradations` 的每一項、按 `stream_error` 的計數 |
| `rejected_overload` | 程序達到 `max_inflight_requests` 而以 `gateway_overloaded` 拒絕的請求 |
| `records_unlogged` | 因請求沒有帳戶而未被 `store` 輸出儲存的記錄 |
| `records_failed`、`records_dropped` | 輸出寫入失敗的記錄，以及 `file` 輸出因佇列已滿而丟棄的記錄 |
| `store_errors` | 因狀態儲存出錯而失敗或失去記憶的請求（`store_unavailable`，或異常 `memory_store_failure`） |
| `openviking.state`、`openviking.reason` | 閘道器最近一次 OpenViking 狀態檢查的結果：`ok`、`degraded` 或 `starting`，降級時附原因 |
| `openviking.open_circuits` | 因持續無響應、呼叫正被跳過的 OpenViking 帳號數；見[OpenViking 異常](../gateway/12-troubleshooting.md#openviking-is-degraded) |
| `capture.delivered` | 本區間內本程序寫入 OpenViking 的已完成輪次數 |
| `capture.failed` | 本區間內本程序寫入 OpenViking 失敗的已完成輪次數。`capture.delivered` 和 `capture.failed` 按程序統計，可以跨程序相加 |

## 上游和上下文配置 {#upstreams-and-context-profiles}

| 方法 | 路徑 | 說明 |
| --- | --- | --- |
| GET | `/gateway/admin/upstreams` | 列出上游 |
| GET | `/gateway/admin/upstreams/{identifier}` | 讀取單個上游 |
| PUT | `/gateway/admin/upstreams/{identifier}` | 建立或替換上游 |
| DELETE | `/gateway/admin/upstreams/{identifier}` | 刪除沒有金鑰在用的上游 |
| POST | `/gateway/admin/upstreams/{identifier}/test` | 測試上游連線或模型 |
| POST | `/gateway/admin/upstreams/import-vlm` | 匯入 OpenViking 的模型配置 |
| GET | `/gateway/admin/policies` | 列出上下文配置 |
| GET | `/gateway/admin/policies/{identifier}` | 讀取單個上下文配置 |
| PUT | `/gateway/admin/policies/{identifier}` | 建立或替換上下文配置 |
| DELETE | `/gateway/admin/policies/{identifier}` | 刪除沒有金鑰在用的上下文配置 |

ID 由呼叫方指定。`PUT` 提交完整物件，未知欄位會導致校驗失敗。各欄位的含義、預設值和取值範圍見[配置參考](../gateway/13-configuration.md#configuration-reference)。

上游的 `api_key` 和 `headers` 只寫不讀：

- `base_url` 不變時，`api_key` 留空或省略就保留已存的金鑰；省略 `headers` 保留全部已存請求頭；提交 `headers` 物件則替換整個集合，其中值為空的項沿用這個名稱已存的值。
- **修改 `base_url` 會清除已存的 API Key 和全部請求頭值。** 新地址需要的憑證要隨這次請求重新提交，這樣已存的金鑰不會被髮往另一個地址。
- 可編輯檢視返回 `has_api_key` 和 `header_names`，不返回值。

```bash
curl -X PUT "$SERVER_URL/gateway/admin/upstreams/openai?account_id=team" \
  -H "X-OpenViking-Gateway-Management-Key: $GATEWAY_MANAGEMENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"OpenAI","protocol":"chat","base_url":"https://api.openai.com/v1","api_key":"<provider-key>"}'
```

刪除仍有閘道器金鑰在用的物件，返回 409 `in_use` 和 `key_count`。先吊銷這些金鑰；只是想讓請求立即停止發往某個上游，可以停用它而不刪除。

### 上游測試 {#upstream-tests}

`POST /gateway/admin/upstreams/{identifier}/test` 支援兩種模式：空請求體 `{}` 通過 `GET /v1/models` 檢查連線；`{"model":"<模型名>"}` 使用已存的憑證和請求頭傳送一次很小的非流式生成請求。模型名會先經過上游的別名對映。模型請求使用已配置的 Chat Completions、Responses 或 Anthropic Messages 介面；關閉路徑拼接時，也會遵循配置的完整介面 URL。上游允許 OpenViking 工具時，請求會帶上當前帳號的 OpenViking 工具，並按預設上下文配置篩選；工具目錄暫時不可用時，降級為不帶工具繼續測試。模型測試不設定 reasoning effort，由模型使用預設值。

響應包含 `{ok, kind, status, reason, url}`，其中 `kind` 為 `connection` 或 `model`。測試失敗時還會在 `response` 中返回完整的上游 HTTP 響應，包括 `http_version`、`status`、`reason`、`headers`、`body` 和可選的 `truncated` 標記。響應體最多 16 KiB；沒有收到響應時不含 `status`。超時時間取已配置上游超時與 60 秒中的較小值。兩種測試都需要寫許可權；模型測試會真實請求服務商並可能產生少量費用。

Anthropic 測試同時在 `x-api-key` 和 `Authorization: Bearer` 中傳送金鑰；上游請求頭未設定 `anthropic-version` 時，預設使用 `2023-06-01`。Chat Completions 和 Responses 測試只傳送 Bearer 鑑權。`key_header` 不是 `authorization`，或者 `base_url` 含 `{api_key}` 時，按[憑證](../gateway/07-upstreams.md#credentials)中的規則傳送；返回的 `url` 保留 `{api_key}` 佔位符。

兩種測試對服務商響應的判斷不同：

| 測試 | 服務商的響應 | `reason` | `ok` |
| --- | --- | --- | --- |
| 連線 | 上游是完整請求地址（`append_endpoint_path` 為 `false`），沒有模型列表。閘道器不發請求，請改用模型測試。 | `exact_endpoint_untestable` | `false` |
| 模型 | Coding Plan 上游尚未授權閘道器使用。閘道器不發請求。 | `coding_plan_blocked` | `false` |
| 兩者 | 沒有可用的 API Key：沒有儲存，或者上游要求每個客戶端自帶。閘道器不發請求。 | `upstream_key_missing` | `false` |
| 連線 | 2xx，響應是帶 `data` 列表的 JSON 物件 | `passed` | `true` |
| 連線 | 其他 2xx：不是合法 JSON、響應體超過 16 KiB、沒有 `data` 列表，或帶 `error` 欄位 | `upstream_key_rejected` | `false` |
| 連線 | 404 或 405：服務商不提供模型列表，API Key 未經驗證 | `models_unavailable` | `true` |
| 連線 | 429：地址有響應，但 API Key 未經驗證 | `rate_limited` | `true` |
| 模型 | 2xx，響應符合已配置的模型協議 | `passed` | `true` |
| 模型 | 其他 2xx：不是合法 JSON、響應體超過 16 KiB，或不符合已配置的協議 | `invalid_response` | `false` |
| 模型 | 429 | `rate_limited` | `false` |
| 模型 | 404 或 405 | `model_request_rejected` | `false` |
| 兩者 | 400 或 422 | `model_request_rejected` | `false` |
| 兩者 | 401 或 403 | `upstream_key_rejected` | `false` |
| 兩者 | 網路錯誤、超時、重定向、5xx 或其他狀態碼 | `upstream_unavailable` | `false` |

連線測試返回 `passed`，說明地址可達，已存憑證也有效。`models_unavailable` 和 `rate_limited` 只能說明地址可達，Studio 顯示為中性色的 **連線可用**；要驗證 API Key，請再做一次模型測試。Coding Plan 授權只攔截模型測試，未授權的 Coding Plan 上游照樣可以做連線測試。模型測試通過說明所選模型完成了本次請求，不代表其他模型也可用，也不會授權使用 Coding Plan。

### 匯入 VLM 配置 {#import-vlm-settings}

`POST /gateway/admin/upstreams/import-vlm` 把 OpenViking Server 的 VLM 憑證匯入為所選帳號的上游，只在嵌入部署中可用；獨立閘道器返回 404 `vlm_import_unavailable`。

每個匯入的上游 ID 固定為 `vlm-<credential id>`，重複匯入不會產生重複的上游。再次匯入時，來自服務端的欄位（`base_url`、`api_key`、`headers`、`protocol`、`vendor`、`coding_plan`、`append_endpoint_path`、`key_header`）按服務端配置重新整理，其他欄位保留在閘道器裡改過的值，包括 `name`、`enabled`、`priority`、`models`、`aliases`、`context_windows` 和 `allow_coding_plan`。路徑中含 `coding` 或 `plan` 段的上游會被標為 Coding Plan，在設定 `allow_coding_plan` 之前歸入 `needs_confirmation`。

```json
{
  "imported": [{"id": "vlm-default", "name": "default"}],
  "needs_confirmation": [{"id": "vlm-coding", "name": "coding"}],
  "skipped": [{"id": "vlm-codex", "reason": "openai_codex"}]
}
```

| 跳過原因 `reason` | 說明 |
| --- | --- |
| `openai_codex` | Codex OAuth 令牌會定期重新整理，閘道器無法長期使用。 |
| `litellm_no_api_base` | LiteLLM 憑證沒有 `api_base`。在 OpenViking 配置中補上後重新匯入。 |
| `litellm_unsupported_route` | LiteLLM 路由不使用 OpenAI Chat Completions API，例如 `gemini/`、`bedrock/` 或 `vertex_ai/`。請手動把這個服務商新增為上游。 |
| `invalid_configuration` | 憑證構不成有效的上游，例如 base URL 無效。 |

## 閘道器金鑰 {#gateway-keys}

| 方法 | 路徑 | 說明 |
| --- | --- | --- |
| GET | `/gateway/admin/keys` | 列出呼叫方可見的金鑰，不含金鑰本身 |
| GET | `/gateway/admin/keys/{identifier}` | 讀取單個可見金鑰 |
| POST | `/gateway/admin/keys` | 簽發金鑰，響應中的 `key` 是唯一一次返回的完整金鑰 |
| DELETE | `/gateway/admin/keys/{identifier}` | 吊銷金鑰，保留使用者資料 |
| POST | `/gateway/admin/keys/{identifier}/capture/reset` | 讓一段對話改存到新的 OpenViking 會話，下一輪結束時寫入完整歷史 |
| DELETE | `/gateway/admin/users/{user_id}/data` | admin 或 root：吊銷該使用者的全部金鑰，刪除其對話狀態和日誌 |
| DELETE | `/gateway/admin/account/data` | root：刪除帳號的全部閘道器物件、金鑰、對話狀態和日誌 |

簽發請求體：

| 欄位 | 必填 | 說明 |
| --- | --- | --- |
| `name` | 是 | 顯示名稱。 |
| `policy_id` | 是 | 使用的上下文配置。 |
| `upstream_ids` | 是 | 可用的上游，至少一個。 |
| `models` | 否 | 允許的模型名（客戶端傳送的名稱，包括別名）；空列表表示不限。 |
| `user_id` | 否 | 金鑰歸屬的 OpenViking 使用者，預設是呼叫方自己。root 不是帳號裡的使用者，必須指定使用者（或提供 `openviking_key`）。user 只能填自己。 |
| `openviking_key` | 否 | 該使用者的 OpenViking API 金鑰。通常不用填，見下文。 |
| `default_peer_id` | 否 | 請求沒帶 `X-OpenViking-Actor-Peer` 請求頭時使用的 Peer，見[按 Peer 區分記憶](../gateway/03-connect-clients.md#peer)。規則與訊息的 `peer_id` 相同；空白表示不設定。 |

閘道器需要拿到目標使用者的 OpenViking API 金鑰，之後以這個使用者的身份檢索和儲存記憶：

- 給自己簽發時，直接使用呼叫方的金鑰（user 或 admin）。
- admin 或 root 給別人簽發時，閘道器用呼叫方的憑證向 OpenViking 讀取該使用者的金鑰。OpenViking 只儲存金鑰雜湊時讀不出來，返回 409 `user_key_unreadable`，這時要在 `openviking_key` 中提供該使用者的金鑰。
- 閘道器會向 OpenViking 核實這把金鑰：它必須屬於所選帳號；提供了 `user_id` 時，還必須屬於這個使用者。
- root API 金鑰不能繫結到閘道器金鑰，本地 dev 的 `default/default` 例外。

```bash
curl -X POST "$SERVER_URL/gateway/admin/keys?account_id=team" \
  -H "X-API-Key: $OPENVIKING_API_KEY" -H "Content-Type: application/json" \
  -d '{"name":"Alice laptop","user_id":"alice","policy_id":"default","upstream_ids":["openai"]}'
```

```json
{
  "id": "3f9c…",
  "name": "Alice laptop",
  "user_id": "alice",
  "policy_id": "default",
  "upstream_ids": ["openai"],
  "models": [],
  "prefix": "ovgw_Xk2pQ7a",
  "created_at": 1760000000.0,
  "revision": 1,
  "key": "ovgw_Xk2pQ7a…"
}
```

立即儲存響應中的 `key`，閘道器只保留它的雜湊。`GET` 返回同樣的欄位，但沒有 `key`。閘道器金鑰不能修改，沒有對應的 `PUT`；要換上下文配置、上游、模型、預設 Peer 或使用者，就簽發新金鑰，再吊銷舊的。

使用者的 OpenViking API 金鑰重新生成或使用者被刪除後，繫結它的閘道器金鑰會失效並被刪除，使用者資料保留，見[閘道器金鑰](../gateway/09-gateway-keys.md#gateway-keys)。

**重置儲存。** 請求體為 `{"session":"<會話請求頭的值或日誌中的 session>","protocol":"chat"}`，`protocol` 取 `chat`、`anthropic` 或 `responses`。成功返回 `{"status":"ready","message":"…"}`，這段對話下一輪結束時，閘道器把完整歷史寫入一個新的 OpenViking 會話。找不到這段對話時返回 404 `not_found`。

**刪除資料。** 兩個刪除介面會清掉閘道器裡的對話狀態和日誌，不影響已經存入 OpenViking 的會話和記憶。保留期和其他刪除途徑見[安全與資料](../gateway/11-security-and-data.md)。

## 錯誤 {#errors}

管理介面的錯誤響應帶穩定的頂層 `reason`，以及一句簡短的英文說明 `detail`；部分錯誤另有附加欄位，例如：

```json
{"reason": "in_use", "detail": "Gateway keys still use this object; revoke them first.", "key_count": 2}
```

請按 `reason` 判斷，不要匹配 `detail` 文本。服務端沒有開啟閘道器時，這組路徑不存在，返回 404；Studio 把這種情況顯示為 `not_enabled`。

| HTTP | `reason` | 含義和處理 |
| --- | --- | --- |
| 401 | `management_key_invalid` | 管理金鑰不正確。向部署者確認當前的管理金鑰，或者見[忘記閘道器管理金鑰](../guides/22-gateway-operations.md#lost-the-management-key)。 |
| 403 | `management_key_required` | 已設定管理金鑰，修改上游或上下文配置時必須帶上它。 |
| 401 | `openviking_http_401` | OpenViking 拒絕了 API 金鑰。換用當前有效的金鑰。 |
| 401 | `openviking_identity_missing` | OpenViking 沒有返回這把金鑰對應的使用者。 |
| 403 | `trusted_mode_unsupported` | OpenViking 使用 trusted 認證。改用 `api_key` 認證。 |
| 403 | `other_account` | 金鑰或請求的帳號不在呼叫方的許可權範圍內。 |
| 403 | `forbidden` | 操作超出呼叫方的角色或使用者範圍。 |
| 403 | `root_key_not_allowed` | root API 金鑰不能繫結到閘道器金鑰。改用某個使用者的 API 金鑰。 |
| 409 | `user_key_unreadable` | OpenViking 只儲存了該使用者金鑰的雜湊。在 `openviking_key` 中提供該使用者的金鑰。 |
| 409 | `in_use` | 還有 `key_count` 個閘道器金鑰在用這個物件。 |
| 400 | `unknown_user`、`unknown_policy`、`unknown_upstream` | 指定的使用者、上下文配置或上游不存在。 |
| 400 | `user_required` | root 簽發金鑰時沒有提供 `user_id` 或 `openviking_key`。指定金鑰歸屬的使用者。 |
| 404 | `not_found` | 物件不存在，或者呼叫方看不到它。 |
| 422 | `invalid_configuration` | 請求體或 Base URL 不合法。錯誤資訊不會回顯提交的憑證。 |
| 403 | `vlm_import_forbidden` | 呼叫方沒有匯入許可權，以 `/access` 的 `can_import_vlm` 為準。 |
| 404 | `vlm_import_unavailable` | 獨立閘道器讀不到服務端的模型配置，請手動新增上游。 |
| 503 | `openviking_unavailable`、`openviking_unreachable`、`openviking_timeout` | 閘道器連不上 OpenViking，或它沒有及時應答。檢查 OpenViking 是否執行；獨立閘道器還要檢查 `openviking_url`（`gateway.conf` 或 `OPENVIKING_GATEWAY_OPENVIKING_URL`）。 |
| 503 | `openviking_version_mismatch` | 僅獨立閘道器：OpenViking Server 低於要求的版本，響應中的 `required_version` 給出最低版本。 |

OpenViking 返回的其他 HTTP 錯誤記為 `openviking_http_<status>`；閘道器自身的通用 HTTP 錯誤記為 `gateway_http_<status>`，例如對不支援的方法返回 405 `gateway_http_405`。這些名稱適用於管理 API、`/uploads` 和 `/downloads`；模型路由使用下面的原因。

### 模型路由的錯誤 {#model-route-errors}

閘道器在模型路由（`/gateway/v1/*`、`/gateway/api/v3/*`、`/gateway/api/compatible/v1/*`）上產生的錯誤，響應體為 `{"reason": "...", "detail": "...", "request_id": "..."}`；`openviking_version_mismatch` 另有 `required_version`。服務商自己的錯誤原樣轉發，狀態碼和響應體都不變。請求記錄的 `error_reason` 記同樣的原因。

| 狀態碼 | 原因 | 來源 | 含義 |
| --- | --- | --- | --- |
| 401 | `gateway_key_invalid` | gateway | 閘道器金鑰缺失、錯誤或已吊銷。 |
| 401 | `openviking_key_invalid` | openviking | OpenViking 拒絕了客戶端傳送的 OpenViking API 金鑰，或閘道器金鑰背後的 OpenViking 金鑰。 |
| 401 | `openviking_identity_missing` | openviking | OpenViking 沒有返回這把金鑰的身份。 |
| 402 | `openviking_not_ordered` | openviking | 這把金鑰未訂購 OpenViking 服務。 |
| 403 | `openviking_forbidden` | openviking | OpenViking 拒絕了這把金鑰。 |
| 403 | `root_key_not_allowed`、`trusted_mode_unsupported` | openviking | root 金鑰不能用於閘道器金鑰；閘道器不支援 trusted 認證。 |
| 429 | `openviking_rate_limited` | openviking | OpenViking 對金鑰檢查限流。 |
| 503 | `openviking_unavailable` | openviking | 閘道器首次檢查一把金鑰時，OpenViking 無法訪問或出錯。 |
| 503 | `openviking_timeout` | openviking | OpenViking 沒有及時應答這次檢查。 |
| 503 | `openviking_version_mismatch` | openviking | OpenViking Server 版本低於閘道器要求。 |
| 不定 | `openviking_error` | openviking | 這次檢查中 OpenViking 的其他錯誤，狀態碼與 OpenViking 相同。 |
| 403 | `oauth_credential_unsupported` | gateway | 客戶端或上游使用了 Claude 訂閱令牌。 |
| 413 | `body_too_large` | gateway | 請求體超過 `max_body_bytes`。 |
| 415 | `compressed_body_unsupported` | gateway | 限定了模型的金鑰收到了經過壓縮編碼的請求體。 |
| 400 | `model_missing` | gateway | 限定了模型的金鑰收到的請求體沒有寫明模型。 |
| 403 | `model_not_allowed` | gateway | 模型不在金鑰允許的範圍內。 |
| 400、403 | `context_override_invalid`、`context_override_not_allowed` | gateway | `X-OpenViking-Context` 無效，或金鑰的上下文配置不接受它。 |
| 400 | `peer_invalid` | gateway | `X-OpenViking-Actor-Peer` 不是合法的 Peer ID。 |
| 403 | `policy_unavailable` | gateway | 金鑰繫結的上下文配置已不存在。 |
| 403 | `upstream_url_not_allowed` | gateway | `X-OpenViking-Upstream-URL` 不是金鑰繫結的任何上游。 |
| 404 | `no_matching_upstream` | gateway | 金鑰繫結的已啟用上游中，沒有一個提供這個協議和模型。 |
| 404 | `upstream_endpoint_mismatch` | gateway | 上游是另一路徑的完整請求地址。 |
| 404、403 | `response_unknown`、`response_upstream_disallowed` | gateway | 查詢的 Responses 響應不屬於這把金鑰，或它的上游已不再允許使用。 |
| 401 | `upstream_key_missing` | gateway | 上游沒有儲存 API Key，請求也沒有在 `X-OpenViking-Upstream-Key` 中攜帶。 |
| 403 | `coding_plan_disabled` | gateway | 上游是不允許通過閘道器使用的 Coding Plan 金鑰。 |
| 503 | `store_unavailable` | gateway | 閘道器的狀態儲存出錯。響應帶 `Retry-After: 1`。 |
| 503 | `gateway_overloaded` | gateway | 程序正在處理的模型請求已達 `max_inflight_requests`。請求沒有發給服務商。響應帶 `Retry-After: 1`。 |
| 500 | `internal_error` | gateway | 閘道器意外出錯。錯誤詳情是通用文本，呼叫棧在閘道器日誌裡。 |
| 504 | `upstream_timeout` | upstream | 服務商沒有在 `upstream_timeout_seconds` 內開始回覆，或者非流式回覆中途這麼久沒有資料。 |
| 502 | `upstream_unreachable` | upstream | 閘道器連不上服務商（DNS、連線被拒絕、TLS）。 |
| 502 | `upstream_disconnected` | upstream | 服務商在回覆完成前關閉了連線。 |
| 502 | `tool_upstream_invalid`、`tool_upstream_incomplete`、`tool_upstream_stream_error`、`tool_call_invalid` | upstream | OpenViking 工具輪次中，服務商的回覆無法使用、不完整或是錯誤，或者模型呼叫了不允許的工具。 |
| 502 | `tool_loop_limit` | gateway | OpenViking 工具輪次達到上限。 |
| 504 | `tool_loop_timeout` | gateway | OpenViking 工具輪次超時。 |

對 Responses 路由發起的 WebSocket 請求仍然收到空的 426，記錄裡寫 `websocket_unsupported`。模型路由上出現 `gateway_http_<status>` 原因，表示閘道器還沒有歸類的錯誤。

模型客戶端收到的 401 不屬於管理 API。原因可能是閘道器金鑰缺失、錯誤或已吊銷，也可能是它繫結的 OpenViking 金鑰已經失效，排查方法見[客戶端收到閘道器返回的錯誤](../gateway/12-troubleshooting.md#clients-get-an-error-from-the-gateway)。
