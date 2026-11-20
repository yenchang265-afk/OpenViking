---
description: 讀懂 Studio 中 OpenViking 閘道器的“概覽”和“請求日誌”標籤頁：卡片、列、請求型別和儲存狀態。
---

# 閘道器概覽與請求日誌

本頁逐一說明閘道器**概覽**和**請求日誌**兩個標籤頁裡的卡片、列、標籤和儲存狀態，以及哪些數值說明閘道器執行正常。在 Studio 中開啟 **OpenViking 閘道器**，選擇**概覽**或**請求日誌**標籤頁即可。客戶端通過閘道器發出第一個請求之前，這兩個標籤頁都沒有資料，接入方法見[接入客戶端](03-connect-clients.md#connect-clients)。

## 誰能看到哪些請求 {#requests-and-overview}

兩個標籤頁讀的都是閘道器的請求日誌：每個經過閘道器的模型請求對應一條記錄。普通使用者只看到自己的請求，帳號管理員和 root 看到整個帳號的請求。概覽裡的數字也是從這些記錄算出來的，所以統計範圍和請求日誌一致。

設定 `request_log_sink: "stdout"` 後，新記錄只寫到 stdout。全新部署的請求日誌頁和概覽中的請求統計保持為空；之前已儲存的記錄仍可見，直到過期。新請求請通過 [stdout 觀測流程](../guides/22-gateway-operations.md#monitoring)檢視。

日誌只記後設資料，從不儲存提示詞、回覆或記憶內容，詳見[請求日誌記什麼](11-security-and-data.md#what-request-logs-record)。儲存中的記錄預設保留 30 天；stdout 的保留期限由日誌採集系統管理。見[保留期限](11-security-and-data.md#retention)。

## 概覽 {#overview}

**概覽**標籤頁彙總請求日誌中最新的 10,000 條請求。收到第一個請求之前，頁面上還會顯示**快速開始**清單，見[快速開始清單和快速模式](06-manage-in-studio.md#get-started-checklist)。

| 卡片 | 顯示什麼 | 正常時 | 不正常時看 |
| --- | --- | --- | --- |
| **請求數** | 模型請求的數量、最近一次請求的時間，以及這些請求的輸出 token | 隨客戶端發請求而增長 | [檢查接入是否生效](03-connect-clients.md#check-the-connection) |
| **首次呼叫快取命中率** | 每條新使用者訊息的第一次模型呼叫中，命中服務商[提示詞快取](01-how-it-works.md#replay)的輸入 token 所佔比例 | 接近不經過閘道器時服務商能達到的水平。這是判斷閘道器是否健康最重要的指標。 | [首次呼叫快取命中率下降](12-troubleshooting.md#the-first-call-cache-hit-rate-dropped) |
| **輪內快取命中率** | 同一輪裡後續呼叫的同一比例，例如工具步驟和 OpenViking 工具的往返 | 通常很高 | — |
| **召回的記憶條數** | 補充到新訊息中的記憶條數，以及每次檢索 OpenViking 的平均耗時（只統計實際檢索了的訊息） | 使用者在 OpenViking 中有記憶後開始增長；全新帳號為 0 屬於正常 | [沒有補充記憶](12-troubleshooting.md#no-memory-is-added) |
| **OpenViking** | **已連線**、**異常**或**啟動中**，OpenViking 的版本，以及異常時的原因。卡片中的**儲存對話**一欄統計最近一輪沒有儲存成功的對話數。 | **已連線**，且最近的請求中沒有儲存失敗的對話 | [OpenViking 異常](12-troubleshooting.md#openviking-is-degraded)、[OpenViking 中看不到對話](12-troubleshooting.md#conversations-do-not-appear-in-openviking) |
| **降級請求** | 每種異常出現的次數，附說明和建議操作 | **沒有降級請求** | [降級請求的異常](12-troubleshooting.md#issues-on-degraded-requests) |
| **最近請求** | 最新的幾條請求，以及前往**請求日誌**標籤頁的連結 | — | [請求日誌](#requests) |

首次呼叫快取命中率明顯下降，通常說明閘道器傳送的歷史和上一次對不上了。OpenViking 連不上期間，請求照常發給模型，只是不帶記憶，結束的輪次也儲存失敗；OpenViking 恢復後，每段對話的下一輪結束時補上缺的內容。**儲存對話**一欄或**降級請求**卡片報告問題時，點**在請求日誌中檢視**會開啟**請求日誌**標籤頁，並篩選出**異常**。

### 長對話沒有命中快取 {#long-conversations-missing-the-cache}

某段對話最近連續 3 次模型呼叫的輸入都不少於 32,000 token、相鄰兩次相隔不到 5 分鐘，而服務商返回的快取命中每次都是 0 時，頂部四張數字卡片（**請求數**、**首次呼叫快取命中率**、**輪內快取命中率**和**召回的記憶條數**）下方會出現“有 2 段長對話連續沒有命中提示詞快取”這樣的警告，並列出每段對話的模型、上游和連續未命中次數。如果這些都是 Anthropic 對話，而且上游也從沒寫入過快取，警告會建議檢查客戶端是否設定了 `cache_control`。

下面這些變化之後快取本來就無法命中，所以連續次數會從頭算起：

- 一次[壓縮](05-long-conversations.md#long-conversations)，或者模型開啟了新的上下文視窗
- 切換到別的模型或上游
- 閘道器工具在請求中時有時無

某個上游最近從沒返回過快取命中時，顯示的是一條提示：經過它的長對話快取命中率一直是 0%。原因和處理方法見[首次呼叫快取命中率下降](12-troubleshooting.md#the-first-call-cache-hit-rate-dropped)。

## 請求日誌 {#requests}

**請求日誌**標籤頁按時間倒序列出日誌中最新的 1,000 條記錄，停留在第一頁時每 30 秒重新整理一次。篩選和搜尋也只覆蓋這 1,000 條。

每個模型請求都會記錄，包括閘道器自己拒絕的請求（例如模型不在金鑰允許的範圍內、沒有匹配的上游、請求體超限），以及在服務商處失敗、或因客戶端離開而結束的請求。金鑰確認之前就被拒絕的請求（例如閘道器金鑰無效）不屬於任何帳戶，不會列出。在準備記憶之前就被拒絕的請求顯示為**直接轉發**。見[客戶端收到閘道器返回的錯誤](12-troubleshooting.md#clients-get-an-error-from-the-gateway)。

### 篩選和搜尋 {#filter-and-search}

| 篩選 | 顯示 |
| --- | --- |
| **全部** | 所有記錄 |
| **新訊息** | 以一條新使用者訊息開啟一輪的請求 |
| **工具步驟** | 延續同一輪的請求，例如帶著工具結果繼續 |
| **異常** | 降級請求、**儲存失敗**的請求，以及狀態碼為 HTTP 400 及以上的請求，無論來自服務商（見[上游返回錯誤](12-troubleshooting.md#the-upstream-returned-an-error)）還是閘道器（見[客戶端收到閘道器返回的錯誤](12-troubleshooting.md#clients-get-an-error-from-the-gateway)） |
| **請求型別** | 某一種[請求型別](#request-types) |

搜尋範圍包括模型、對話 ID、請求 ID、金鑰名稱或字首，以及上游名稱。日誌只儲存對話 ID 的雜湊，所以 Studio 會先在瀏覽器裡對貼上的對話 ID 求雜湊再匹配。這要求 Studio 通過 HTTPS 或 localhost 開啟；用普通 HTTP 開啟時，按對話 ID 搜尋什麼也找不到。

### 各列含義 {#columns}

| 列 | 顯示 |
| --- | --- |
| **時間** | 請求到達的時間 |
| **型別** | [請求型別](#request-types) |
| **模型** | 客戶端傳送的模型名稱 |
| **狀態** | 客戶端收到的 HTTP 狀態碼：服務商的狀態碼，或者閘道器拒絕或處理失敗時閘道器自己的狀態碼 |
| **Token** | 輸入 token、其中命中快取的比例，以及輸出 token |
| **記憶** | 這次請求中[召回](../guides/15-gateway.md#key-terms)做了什麼（見下表） |
| **儲存** | 這次請求的[儲存狀態](#saving-status)；滑鼠懸停可以看到原因 |
| **異常** | 降級請求的異常 |

**記憶**列的寫法：

| 顯示 | 含義 |
| --- | --- |
| `+3` | 這次檢索補充了 3 條記憶，旁邊附檢索耗時。 |
| `↺ 4` | 之前 4 條訊息補充的記憶被原樣放回。 |
| **召回失敗** | 這次請求的記憶檢索沒有完成，例如 OpenViking 連不上、拒絕了金鑰，或者沒有在上下文配置的**超時時間**內返回。滑鼠懸停可以看到原因，另見[沒有補充記憶](12-troubleshooting.md#no-memory-is-added)。 |

### 請求詳情 {#request-details}

展開一行可以看到：

- 對話 ID、上游、閘道器金鑰和耗時
- token 明細
- 記憶檢索結果
- 上下文視窗用量，以及歷史是否經過壓縮、模型是否開啟了新視窗
- 儲存狀態；這次請求儲存了一輪時，還有寫入的訊息數和 OpenViking 會話 ID
- OpenViking 工具詳情，包括沒有提供工具的原因
- 客戶端在 `X-OpenViking-Context` 中傳入的配置項，只記名稱；它們只在對話的第一個請求中生效

有異常的請求，展開後還會說明發生了什麼、該怎麼處理。

### 請求型別 {#request-types}

每條記錄都屬於一種型別。型別決定這次請求是否檢索記憶、所在的輪次是否儲存。

| 型別 | 含義 | 記憶 |
| --- | --- | --- |
| 新訊息 | 最後一條是新使用者訊息的請求 | 檢索一次，並放回之前的記憶；回覆結束這一輪時儲存這一輪 |
| 工具步驟 | 同一輪的延續，例如帶著工具結果繼續 | 放回之前的記憶；結束這一輪的那個請求儲存整輪 |
| 輔助請求 | 生成標題、摘要、壓縮、建議和許可權檢查的請求；對話帶過客戶端工具後，同一對話裡不帶工具、也不帶之前回復的單獨請求，例如 Claude Code 彙總抓取的網頁。運維可以在[客戶端規則](13-configuration.md#client-rules)裡補充某個客戶端自己的請求 | 放回之前的記憶；從不儲存，但 Claude Code 或 Codex 在一輪中間的壓縮請求會寫入它之前的歷史 |
| 子 Agent | 客戶端的子 Agent 發出的請求 | 放回之前的記憶；從不儲存 |
| Token 計數 | token 計數請求（`/gateway/v1/messages/count_tokens`） | 放回之前的記憶，計數才和實際傳送的內容一致 |
| 直接轉發 | 原樣轉發、不帶記憶的請求：其他介面、依賴服務商端狀態的 Responses 請求、壓縮過或無法解析的請求體 | 無 |

## 儲存狀態 {#saving-status}

**儲存**列顯示這次請求所在對話是否儲存到 OpenViking，以及結束一輪的請求有沒有把這一輪[儲存](../guides/15-gateway.md#key-terms)成功。正常情況下顯示**正常**。

| 狀態 | 含義 | 閘道器怎麼做 |
| --- | --- | --- |
| **正常**（`active`） | 儲存已開啟；這次請求結束了一輪時，這一輪已寫入 OpenViking。 | 結束一輪的請求在回覆之後把這一輪寫入 OpenViking。 |
| **已關閉**（`disabled`） | 這段對話的[上下文配置](08-context-profiles.md#save-conversations)不儲存對話。 | 不儲存任何內容。 |
| **儲存失敗**（`failed`） | 這次請求結束了一輪，但寫入 OpenViking 失敗。每一輪只嘗試一次，最多等 30 秒。 | 不重試。客戶端在下一輪原樣發回歷史時，閘道器在下一輪結束時把缺的內容一起寫入；沒有下一輪時，這一輪不會儲存。 |

展開的行和**儲存**標記的懸停提示會顯示原因：

| 顯示的原因 | 程式碼 | 含義 |
| --- | --- | --- |
| OpenViking 拒絕了這個金鑰，它可能填錯了或已被吊銷。 | `openviking_http_401` | 使用者的 OpenViking 金鑰已失效。 |
| OpenViking 無法訪問或響應超時 | `openviking_unavailable` | OpenViking 沒有執行或連不上。 |
| OpenViking 響應超時 | `openviking_timeout` | OpenViking 響應太慢。 |
| OpenViking 對這個帳號持續無響應，暫時跳過 | `openviking_circuit_open` | 這個帳號的 OpenViking 呼叫正被跳過，見[OpenViking 異常](12-troubleshooting.md#openviking-is-degraded)。 |
| OpenViking 返回了 HTTP …，或 OpenViking 報告了錯誤 … | `openviking_http_<status>`、`openviking_<CODE>` | OpenViking 拒絕了寫入，例如 `402`（未訂購）、`429`（限流），或者 `400`（`capture_memory_types` 中有 OpenViking 不認識的記憶型別）。 |
| 儲存到 OpenViking 超時 | `save_timeout` | 寫入沒有在 30 秒內完成。 |
| 儲存到 OpenViking 失敗 | `save_failed` | 其他錯誤。閘道器日誌中有一條 "could not save a finished turn" 警告，附帶呼叫棧。 |
| 管理員已手動重新同步 | `manual_reset` | 不是失敗：有人用了**重新同步對話…**（見下文），狀態仍為**正常**，這段對話之後的記錄會一直顯示這個原因。 |

在更早版本的閘道器中開始的對話，可能一直帶著當時記下的原因（例如 `history_changed`），狀態為**正常**時不需要處理。儲存一直失敗時，見[OpenViking 中看不到對話](12-troubleshooting.md#conversations-do-not-appear-in-openviking)。

### 重新同步對話 {#resync-a-conversation}

重新同步會為一段對話新建一個 OpenViking 會話，這段對話下一輪結束時，閘道器把完整歷史寫進去。儲存一直失敗、修復原因後想補全整段對話，或者想要一份乾淨、完整的對話副本時，可以用它。已經儲存的內容留在舊會話裡，所以 OpenViking 可能會把部分記憶提取兩次。

1. 在**請求日誌**標籤頁展開這段對話的一條記錄。重新同步需要記錄上顯示的那把金鑰；它已被吊銷時，請選同一段對話裡更新的一條記錄。
2. 點選**重新同步對話…**，再點**重新同步**。頁面會提示“這段對話會在下一輪結束時重新儲存。”
3. 等使用者在這段對話裡完成下一輪。在此之前什麼都不會發生；這一輪結束時，閘道器把完整歷史儲存到新會話，這段對話的記錄會顯示原因“管理員已手動重新同步”。

## 下一步 {#next-steps}

- [OpenViking 閘道器排障](12-troubleshooting.md#common-symptoms)：根據卡片、標籤或狀態找到原因和處理方法。
- [記憶原樣放回與提示詞快取](01-how-it-works.md#replay)：為什麼首次呼叫快取命中率這麼重要。
- [觀測](../guides/22-gateway-operations.md#monitoring)：在 Studio 之外檢查閘道器的執行狀態。
- [安全與資料](11-security-and-data.md#what-request-logs-record)：日誌記錄什麼、保留多久。
