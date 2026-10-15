# OpenViking 閘道器管理 API

管理 API 用來檢視許可權、配置上游和上下文配置、簽發閘道器金鑰、讀取用量和日誌。所有路徑都以 `/gateway/admin/` 開頭，由閘道器直接提供：閘道器在 OpenViking Server 內執行時，訪問 Server 的埠（預設 1933）；獨立執行時，訪問閘道器自己的埠（預設 1935）。示例中的 `SERVER_URL` 指這個地址本身，不帶路徑，例如 `http://127.0.0.1:1933`。

模型客戶端不呼叫這組介面。它們用閘道器金鑰訪問 `/gateway/v1/*`、`/gateway/api/v3/*` 或 `/gateway/api/compatible/v1/*`，見[OpenViking 閘道器](../guides/15-gateway.md#接入客戶端)。

## 憑證和帳號範圍

每個管理請求都要帶 OpenViking API 金鑰，放在 `X-API-Key` 或 `Authorization: Bearer` 中。閘道器向 OpenViking 確認這把金鑰屬於哪個帳號、哪個使用者、什麼角色，確認結果最多快取 30 秒。本地 dev 模式不需要金鑰，呼叫方固定為 root 身份 `default/default`。閘道器不支援 trusted 認證。

上游和上下文配置（API 中叫 `policies`）屬於帳號，同一帳號的使用者共用。請求預設作用於呼叫方所在的帳號；root 可以用 query 引數 `account_id` 指定其他帳號，admin 和 user 只能訪問自己的帳號。

部署者可以另外設定閘道器管理金鑰（配置方法見[閘道器管理金鑰](../guides/22-gateway-operations.md#閘道器管理金鑰)）。設定之後，修改上游和上下文配置的請求必須在 `X-OpenViking-Gateway-Management-Key` 中帶上它，OpenViking 的 admin 和 root 也不例外。請求帶了管理金鑰但值不對時，閘道器直接返回 401 `management_key_invalid`，不會降級成只讀請求。

| 操作 | 未設定管理金鑰 | 已設定管理金鑰 |
| --- | --- | --- |
| 讀取上游和上下文配置、測試上游 | 本帳號的任何使用者 | 本帳號的任何使用者；單獨持有管理金鑰也可以，並能指定任意帳號 |
| 建立、修改、刪除上游或上下文配置 | 本帳號的任何使用者 | 只有帶正確管理金鑰的請求 |
| 匯入 OpenViking 的模型配置 | 嵌入部署中的 root（包括本地 dev） | 只有帶正確管理金鑰的請求，且只限嵌入部署 |
| 簽發、讀取、吊銷閘道器金鑰，重置儲存 | user 只能操作自己的金鑰；admin 操作本帳號；root 操作所選帳號 | 同左，管理金鑰不增加任何許可權 |
| 讀取日誌和概覽 | user 只看自己的；admin 和 root 看整個帳號 | 同左，始終需要 OpenViking 身份 |
| 刪除某個使用者的閘道器資料 | 本帳號的 admin，或 root | 同左 |
| 刪除整個帳號的閘道器資料 | root | 同左 |

管理金鑰可以不帶 OpenViking API 金鑰單獨使用，適合自動化指令碼：它能讀寫上游和上下文配置、呼叫 `/access`，用 `account_id` 指定帳號（省略時為 `default`）。簽發金鑰、讀取日誌和概覽始終需要 OpenViking 身份；兩種憑證同時提供，也不會讓這些操作獲得更高的許可權。設定、更換或去掉管理金鑰都不影響已簽發的閘道器金鑰。

只讀檢視不返回上游的 API Key、請求頭的值和請求頭名稱，只保留 `has_api_key` 和 `auth_mode`。

## 許可權與發現

| 方法 | 路徑 | 返回 |
| --- | --- | --- |
| GET | `/gateway/admin/access` | 呼叫方的許可權：`managed`、`can_write_objects`、`can_import_vlm`、`can_issue_for_others`、`role`、`account_id`、`user_id`、`warnings` |
| GET | `/gateway/admin/overview` | 呼叫方可見的最近 10,000 條日誌彙總：用量、快取命中、召回、儲存異常、OpenViking 狀態和日誌保留期 |
| GET | `/gateway/admin/logs` | 呼叫方可見的最新日誌；`limit` 預設 200，取值 1–1000 |
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

## 上游和上下文配置

| 方法 | 路徑 | 說明 |
| --- | --- | --- |
| GET | `/gateway/admin/upstreams` | 列出上游 |
| GET | `/gateway/admin/upstreams/{identifier}` | 讀取單個上游 |
| PUT | `/gateway/admin/upstreams/{identifier}` | 建立或替換上游 |
| DELETE | `/gateway/admin/upstreams/{identifier}` | 刪除沒有金鑰在用的上游 |
| POST | `/gateway/admin/upstreams/{identifier}/test` | 測試上游連線 |
| POST | `/gateway/admin/upstreams/import-vlm` | 匯入 OpenViking 的模型配置 |
| GET | `/gateway/admin/policies` | 列出上下文配置 |
| GET | `/gateway/admin/policies/{identifier}` | 讀取單個上下文配置 |
| PUT | `/gateway/admin/policies/{identifier}` | 建立或替換上下文配置 |
| DELETE | `/gateway/admin/policies/{identifier}` | 刪除沒有金鑰在用的上下文配置 |

ID 由呼叫方指定。`PUT` 提交完整物件，未知欄位會導致校驗失敗。各欄位的含義、預設值和取值範圍見[配置參考](../guides/22-gateway-operations.md#配置參考)。

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

### 連線測試

`POST /gateway/admin/upstreams/{identifier}/test` 用已存的憑證請求服務商的模型列表，超時 10 秒，返回 `{ok, status, reason, url}`；沒有收到響應時不含 `status`。只讀呼叫方也能使用。Anthropic 上游同時在 `x-api-key` 和 `Authorization: Bearer` 中傳送金鑰，Chat Completions 和 Responses 上游只傳送 Bearer。

| 服務商的響應 | `reason` | `ok` |
| --- | --- | --- |
| 沒有可用的 API Key：沒有儲存，或者上游要求每個客戶端自帶。閘道器不發請求。 | `upstream_key_missing` | `false` |
| 2xx，響應體帶 `data` 陣列 | `passed` | `true` |
| 2xx 但響應體表示失敗，或者 401、403 | `upstream_key_rejected` | `false` |
| 404、405：地址可達，但服務商不提供模型列表，金鑰沒有得到驗證 | `models_unavailable` | `true` |
| 429：地址可達 | `rate_limited` | `true` |
| 網路錯誤或 5xx | `upstream_unavailable` | `false` |

測試通過只說明地址和金鑰可用，不代表某個具體模型可用，也不代表上游允許使用 Coding Plan。

### 匯入 VLM 配置

`POST /gateway/admin/upstreams/import-vlm` 把 OpenViking Server 的 VLM 憑證匯入為所選帳號的上游，只在嵌入部署中可用；獨立閘道器返回 404 `vlm_import_unavailable`。

每個匯入的上游 ID 固定為 `vlm-<credential id>`，重複匯入不會產生重複的上游。再次匯入時，來自服務端的欄位（`base_url`、`api_key`、`headers`、`protocol`、`vendor`、`coding_plan`）按服務端配置重新整理，其他欄位保留在閘道器裡改過的值，包括 `name`、`enabled`、`priority`、`models`、`aliases`、`context_windows` 和 `allow_coding_plan`。路徑中含 `coding` 或 `plan` 段的上游會被標為 Coding Plan，在設定 `allow_coding_plan` 之前歸入 `needs_confirmation`。

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
| `azure` | Azure OpenAI 需要 `api-version` 引數，閘道器不傳送它。 |
| `litellm_no_api_base` | LiteLLM 憑證沒有 `api_base`。在 OpenViking 配置中補上後重新匯入。 |
| `litellm_unsupported_route` | LiteLLM 路由不使用 OpenAI Chat Completions API，例如 `gemini/`、`bedrock/` 或 `vertex_ai/`。請手動把這個服務商新增為上游。 |
| `invalid_configuration` | 憑證構不成有效的上游，例如 base URL 無效。 |

## 閘道器金鑰

| 方法 | 路徑 | 說明 |
| --- | --- | --- |
| GET | `/gateway/admin/keys` | 列出呼叫方可見的金鑰，不含金鑰本身 |
| GET | `/gateway/admin/keys/{identifier}` | 讀取單個可見金鑰 |
| POST | `/gateway/admin/keys` | 簽發金鑰，響應中的 `key` 是唯一一次返回的完整金鑰 |
| DELETE | `/gateway/admin/keys/{identifier}` | 吊銷金鑰，保留使用者資料 |
| POST | `/gateway/admin/keys/{identifier}/capture/reset` | 讓一段對話重新開始儲存 |
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

立即儲存響應中的 `key`，閘道器只保留它的雜湊。`GET` 返回同樣的欄位，但沒有 `key`。閘道器金鑰不能修改，沒有對應的 `PUT`；要換上下文配置、上游、模型或使用者，就簽發新金鑰，再吊銷舊的。

使用者的 OpenViking API 金鑰重新生成或使用者被刪除後，繫結它的閘道器金鑰會失效並被刪除，使用者資料保留，見[閘道器金鑰](../guides/22-gateway-operations.md#閘道器金鑰)。

**重置儲存。** 請求體為 `{"session":"<會話請求頭的值或日誌中的 session>","protocol":"chat"}`，`protocol` 取 `chat`、`anthropic` 或 `responses`。成功返回 `{"status":"ready","message":"…"}`，閘道器會在這段對話的下一個請求裡，把完整歷史寫入一個新的 OpenViking 會話。找不到這段對話時返回 404 `not_found`。

**刪除資料。** 兩個刪除介面會清掉閘道器裡尚未儲存的對話內容和日誌，不影響已經存入 OpenViking 的會話和記憶。保留期和其他刪除途徑見[安全與資料](../guides/22-gateway-operations.md#安全與資料)。

## 錯誤

管理介面的錯誤響應帶穩定的頂層 `reason`，以及一句簡短的英文說明 `detail`；部分錯誤另有附加欄位，例如：

```json
{"reason": "in_use", "detail": "Gateway keys still use this object; revoke them first.", "key_count": 2}
```

請按 `reason` 判斷，不要匹配 `detail` 文本。服務端沒有開啟閘道器時，這組路徑不存在，返回 404；Studio 把這種情況顯示為 `not_enabled`。

| HTTP | `reason` | 含義和處理 |
| --- | --- | --- |
| 401 | `management_key_invalid` | 管理金鑰不正確。向部署者確認當前的管理金鑰。 |
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
| 503 | `openviking_unavailable`、`openviking_unreachable` | 閘道器連不上 OpenViking。檢查 OpenViking 是否執行；獨立閘道器還要檢查 `openviking_url`（`gateway.conf` 或 `OPENVIKING_GATEWAY_OPENVIKING_URL`）。 |
| 503 | `openviking_version_mismatch` | 僅獨立閘道器：OpenViking Server 低於要求的版本，響應中的 `required_version` 給出最低版本。 |

OpenViking 返回的其他 HTTP 錯誤記為 `openviking_http_<status>`；閘道器自身的通用 HTTP 錯誤記為 `gateway_http_<status>`，例如對不支援的方法返回 405 `gateway_http_405`。

模型客戶端收到的 401 不屬於管理 API。原因可能是閘道器金鑰缺失、錯誤或已吊銷，也可能是它繫結的 OpenViking 金鑰已經失效，排查方法見[客戶端收到閘道器返回的錯誤](../guides/22-gateway-operations.md#客戶端收到閘道器返回的錯誤)。
