---
description: OpenViking 閘道器儲存什麼、誰能訪問、服務商能看到什麼，以及資料如何保留、刪除和備份。
---

# OpenViking 閘道器安全與資料

本頁寫給審批閘道器部署的運維和安全評審人員，也寫給想知道閘道器儲存了自己哪些資料的使用者。會話和記憶始終儲存在 OpenViking 中，按 OpenViking 自己的規則管理；閘道器預設在本地 SQLite 中、也可以在配置的 Redis 後端中儲存自身配置、讓對話繼續所需的狀態，以及只含後設資料的請求日誌。下面每一節回答一個評審問題，都可以單獨連結。

## 按使用者隔離 {#isolation-by-user}

每把[閘道器金鑰](../guides/15-gateway.md#key-terms)繫結一位 OpenViking 使用者。閘道器用這位使用者自己的 OpenViking 金鑰檢索記憶、儲存對話和呼叫工具，所以能做的事不會超出使用者本人的許可權。各使用者的對話狀態互相隔離。設定 `tenancy: key` 後，即使帳號和使用者身份相同，不同 OpenViking 金鑰也有獨立分割槽；輪換金鑰會進入新分割槽。

## 閘道器儲存什麼 {#what-the-gateway-stores}

預設資料儲存在 `storage_path`（預設 `~/.openviking/gateway`）下的兩個 SQLite 資料庫裡。兩個儲存後端都可以分別改用 [Redis](13-configuration.md#storage)：

| 檔案 | 內容 |
| --- | --- |
| `management.sqlite3`（或 Redis management） | 上游、上下文配置、閘道器金鑰、使用預設 `store` sink 時的請求日誌，以及每個 Responses 響應由哪個上游建立 |
| `kernel.sqlite3`（或 Redis kernel） | 每段對話的狀態：補充到訊息中的記憶原文、OpenViking 工具的往返記錄及其結果、摘要、等待儲存的對話文本，以及開啟**補全推理內容回傳**時模型回覆的推理內容 |

其中有些屬於敏感資料：

- `management.sqlite3` 存有上游 API Key、請求頭的值，以及閘道器金鑰繫結的 OpenViking 金鑰。閘道器金鑰本身只存雜湊和一段短字首。
- `kernel.sqlite3` 逐字儲存記憶原文，因為閘道器要靠它把之前幾輪補充的內容[原樣放回](01-how-it-works.md#replay)。

SQLite 檔案只有執行閘道器的系統使用者能讀取；Redis 由網路和 ACL 配置控制訪問。開啟[加密](../guides/22-gateway-operations.md#encryption)後，儲存的每個值也都會加密；加密關閉時，上面這些憑證以明文儲存，由檔案許可權或 Redis 訪問控制保護。所有副本必須從 Secret 掛載同一把加密根金鑰；只讀掛載缺少金鑰條目時會拒絕啟動。Redis 鍵名使用雜湊，但索引可能包含原始帳號、物件和會話標識，除值加密之外也應啟用 TLS。

## 請求日誌記什麼 {#what-request-logs-record}

請求日誌只記後設資料，不記內容：

| 會記錄 | 不會記錄 |
| --- | --- |
| 請求型別、模型、狀態、上游 | 訊息文本 |
| 對話 ID 的雜湊 | 召回的記憶 |
| token 數、記憶條數和耗時 | 工具引數和結果 |
| 儲存狀態和異常 | 任何金鑰 |

閘道器不寫 HTTP 訪問日誌，錯誤資訊也不回顯提交的值。預設的 `store` sink 使請求日誌可在 Studio 中檢視，見[請求日誌](10-overview-and-requests.md#requests)。`stdout` sink 將相同後設資料連同帳號和使用者標識輸出為明文 JSON；儲存加密不作用於 stdout。日誌採集和訪問由部署環境管理，見[觀測](../guides/22-gateway-operations.md#monitoring)。

## 服務商能看到什麼 {#what-providers-see}

每個[上游](../guides/15-gateway.md#key-terms)都收到完整的模型輸入，包括閘道器補充的記憶和 OpenViking 工具的結果。只新增你放心交出這些資料的服務商。

也有一些內容不會離開閘道器：`X-OpenViking-*` 請求頭、客戶端憑證和 Cookie 從不轉發給上游。上游設為由每個客戶端提供自己的服務商金鑰時，這把金鑰只作為該上游的憑證發給服務商。

## 訪問控制 {#access-control}

通過閘道器獲得訪問權的途徑有四種，每種都有需要了解的邊界：

| 憑證 | 允許做什麼 | 注意 |
| --- | --- | --- |
| [閘道器金鑰](09-gateway-keys.md#gateway-keys)，放在 `Authorization: Bearer` 或 `x-api-key` 中 | 以繫結使用者的身份發起模型請求：召回記憶、儲存對話、呼叫 OpenViking 工具 | 隨時可以在**金鑰**頁吊銷 |
| [閘道器管理金鑰](../guides/22-gateway-operations.md#gateway-management-key) | 只能修改上游和上下文配置 | 不授予讀取記憶、日誌或簽發金鑰的許可權 |
| 帳號管理員的簽發權 | 給本帳號的任何使用者簽發閘道器金鑰 | 實際上等於能讀取本帳號所有使用者的記憶 |
| 上傳、下載連結裡的一次性令牌 | 呼叫 `/gateway/uploads` 和 `/gateway/downloads`，這兩個介面不需要閘道器金鑰 | 令牌放在查詢字串裡 |

其中兩項需要特別留意：

- **簽發金鑰。** 拿到閘道器金鑰就能以該使用者的身份召回記憶、呼叫工具，所以簽發權只交給可信的管理員。OpenViking 只存金鑰雜湊時，需要使用者本人提供自己的 OpenViking 金鑰。
- **上傳和下載連結。** 每個連結由 OpenViking 簽發的一次性令牌授權，閘道器只把它轉發到 OpenViking 的上傳或下載介面。不要讓它們的查詢字串出現在代理日誌裡。

包括管理 API 在內的完整規則見[許可權矩陣](../api/25-gateway.md#credentials-and-account-scope)；各角色在 Studio 中能做什麼，見[誰能修改什麼](06-manage-in-studio.md#who-can-change-what)。

## 保留期限 {#retention}

閘道器資料會自動過期。SQLite 每小時執行清理，Redis 使用鍵 TTL：

| 資料 | 保留時長 | 設定 |
| --- | --- | --- |
| 對話狀態 | 最後一次使用後 30 天 | `session_ttl_seconds` |
| 快取的 OpenViking 金鑰及其使用者記錄 | 從建立時起經過配置的 TTL，不續期 | `session_ttl_seconds` |
| 儲存的請求日誌 | 30 天 | `log_retention_days` |
| Responses 響應與上游的對應關係 | 30 天 | `response_ttl_seconds` |
| OpenViking 中的會話和記憶 | 遵循 OpenViking 自己的規則 | — |

OpenViking 金鑰記錄過期，或被使用 `volatile-lru` 的 Redis 後端驅逐後，寫回任務因讀不到憑據而以 `gateway_key_revoked` 暫停。使用者的下一個請求會重建記錄，並在同一 scope 中恢復寫回。如果使用者不再請求，最後一輪待寫回內容不會存入 OpenViking。這些狀態屬於快取，允許丟失。與吊銷一樣，現有的短時程序內快取可能延遲觀察到過期。

Redis 每個帳號最多保留 10,000 條請求日誌。讀取時跳過早於 `log_retention_days` 的條目；這些條目仍留在儲存中，直到被更新的條目擠出上限，或者該帳號連續 `log_retention_days` 沒有新日誌。Redis 不需要每小時清理。Redis Responses 路由記錄按 TTL 過期，刪除使用者時不掃描它們；被吊銷的金鑰無法訪問這些記錄。

這些設定的最小值和配置位置見[閘道器欄位](13-configuration.md#gateway-fields)。 stdout 日誌的保留和刪除由日誌採集器控制，與閘道器清理獨立。

## Redis 對話狀態 {#redis-conversation-state}

配置 `storage.kernel: redis` 後，對話狀態按快取儲存，TTL 使用 `session_ttl_seconds`。寫入會續期，只讀記錄不會續期。

驅逐會產生以下影響：

| 丟失的狀態 | 影響 |
| --- | --- |
| 回放、召回記憶或恢復的推理 | 無法重放之前的決策，下一次請求發生快取未命中。壓縮摘要丟失後可能需要重新摘要，或使請求超過模型上下文限制。 |
| 待投遞的 capture 文件 | 尚未儲存的輪次可能丟失。從客戶端歷史重建時可能重複儲存已經投遞的訊息；持有已丟失文件的 worker 會停止使用舊 lease。 |
| observation 或 thinking 狀態 | 召回帳本歸零，之前的推理可能無法識別。 |
| 另一請求等待期間的工具回執 | 返回超時或結果未知。閘道器不會重試該操作；重試寫操作前應先檢查實際狀態。 |

Redis 非同步主從切換可能丟失最近的寫入或 lease，偶爾導致 capture 重複。應持久化 Redis，以保留待投遞資料和刪除操作；恢復刪除之前的快照會使已刪除的資料重新可見。見 [Redis 記憶體策略](../guides/22-gateway-operations.md#redis-memory-policy)。

開啟加密後，儲存的值會加密。鍵名使用雜湊，但索引成員包含原始 session ID，記錄型別、版本、排程時間和 lease owner 仍是明文，應相應保護 Redis 的訪問許可權和備份。

## 刪除資料 {#deleting-data}

吊銷閘道器金鑰、或者它繫結的 OpenViking 金鑰失效，都不會刪除使用者資料。要刪除，有三種途徑：

| 誰 | 怎麼做 | 刪除什麼 |
| --- | --- | --- |
| 帳號管理員或 root | 在 Studio 中用**刪除該使用者的閘道器資料…**（[操作步驟](09-gateway-keys.md#delete-a-users-gateway-data)），或者呼叫 `DELETE /gateway/admin/users/{user_id}/data` | 單個使用者：吊銷其閘道器金鑰，刪除其對話狀態和日誌，包括尚未儲存的內容 |
| root | 呼叫 `DELETE /gateway/admin/account/data?account_id=<account>` | 整個帳號的閘道器資料 |
| 嵌入部署，自動進行 | 在 OpenViking 中刪除使用者或帳號 | 對應的閘道器資料 |

獨立部署沒有自動刪除這一步，資料會一直保留，直到被顯式刪除或[過期](#retention)。設定 [`management_api: false`](13-configuration.md#gateway-fields) 後，刪除 API 也不可用：在 OpenViking 中刪除使用者不會通知獨立閘道器，對話狀態只能等 `session_ttl_seconds` 到期後清理。請求日誌和響應對映按各自的保留期限過期。按帳號隔離的嵌入部署仍保留 Server 的自動刪除鉤子。按金鑰隔離時，鉤子無法根據 OpenViking 的帳號和使用者 ID 找到 `k_` 分割槽，其快取資料按上述保留期限清理。

已存入 OpenViking 的記憶和會話不受這些操作影響。反過來，在 OpenViking 中刪除一條記憶後，閘道器為進行中的對話儲存的那份副本仍會被原樣放回，直到對話過期；要立即清除，刪除該使用者的閘道器資料。

## 備份與恢復 {#backups}

以下內容要一起備份：

- Redis：啟用 AOF，並把 Redis 持久化資料與加密根金鑰一起備份。未啟用持久化時，重啟 Redis 會丟失管理配置和等待寫回的對話資料。
- SQLite：整個 `storage_path` 目錄：兩個資料庫及其 `-wal`、`-shm` 檔案。
- 開啟加密時，還有 OpenViking 的加密根金鑰（不是 root API 金鑰），按[加密指南](../guides/08-encryption.md)的說明保管。

要得到一致的副本，先停止閘道器，或者在執行中使用 SQLite 的線上備份：

```bash
sqlite3 kernel.sqlite3 ".backup kernel.backup.sqlite3"
sqlite3 management.sqlite3 ".backup management.backup.sqlite3"
```

丟失不同內容的後果：

| 丟失 | 後果 | 怎麼辦 |
| --- | --- | --- |
| `kernel.sqlite3`（或 Redis kernel） | 之前補充的記憶無法放回。每段進行中的對話會有一次服務商快取未命中，Claude 對話會丟掉一次之前的思考內容（[**記憶記錄缺失**](12-troubleshooting.md#issues-on-degraded-requests)），尚未儲存的輪次也會丟失。 | 無需處理，進行中的對話在一次未命中之後就會恢復 |
| `management.sqlite3`（或 Redis management） | 上游、上下文配置、金鑰和請求日誌全部丟失。 | 恢復備份，或重新配置並簽發新金鑰；OpenViking 金鑰記錄會在後續請求中重建 |
| 加密根金鑰（開啟加密時） | 兩個資料庫中已加密的值都無法讀取。 | 從空的 `storage_path`（SQLite），或換用 ACL 鍵模式仍能覆蓋的新 `storage.key_prefix`（例如 `ovgw:2:`），或刪除舊字首下的所有鍵（Redis）後重新開始 |

## 下一步 {#next-steps}

- [加密](../guides/22-gateway-operations.md#encryption)：為已存的憑證和對話狀態開啟加密。
- [刪除使用者的閘道器資料](09-gateway-keys.md#delete-a-users-gateway-data)：在 Studio 中刪除單個使用者資料的步驟。
- [例行檢查](../guides/22-gateway-operations.md#day-to-day-operations)：需要定期檢查的事項，包括備份。
- [許可權矩陣](../api/25-gateway.md#credentials-and-account-scope)：每項操作及其所需的憑證。
