---
description: 把任何使用 API Key 的模型客戶端指向 OpenViking 閘道器，讓它用上 OpenViking 記憶。
---

# OpenViking 閘道器

OpenViking 閘道器是一個模型 API 代理：客戶端只要能修改 Base URL，接上它就能用上 OpenViking 記憶。接入只改兩處：Base URL 換成閘道器地址，模型服務商的 API Key 換成閘道器金鑰。不用裝外掛，也不用改程式碼或提示詞。

閘道器在轉發請求時完成三件事：

| 能力 | 閘道器做什麼 |
| --- | --- |
| 自動召回 | 使用者每發一條新訊息，閘道器先檢索 OpenViking，把相關記憶附加到這條訊息上，再交給模型。 |
| 主動使用記憶 | 模型可以呼叫 OpenViking 工具檢索、讀取、寫入和匯入資料。工具由閘道器執行，客戶端不用宣告或實現任何工具。 |
| 沉澱與壓縮 | 閘道器把對話儲存回 OpenViking，由 OpenViking 從中提取新記憶。對話接近模型的上下文視窗時，閘道器讓同一個模型寫摘要，替換較早的內容。 |

想先直觀瞭解閘道器的工作原理，可以看官網的動畫演示：[openviking.ai/gateway](https://openviking.ai/gateway)。想馬上接入客戶端，直接看[把客戶端接入 OpenViking 閘道器](../gateway/03-connect-clients.md)；其他任務或 Studio 標籤頁對應哪一頁，見[下一步去哪](#next-steps)。

> **注意**：OpenViking 閘道器目前處於 Beta 階段。它和 VikingBot Gateway（`vikingbot gateway`）是兩個元件，後者負責遠端訪問和聊天平臺接入。

## 適合誰 {#who-it-is-for}

- **適合**：裝不了外掛或 MCP 的客戶端，例如聊天應用、SDK 指令碼和低程式碼平臺；以及想集中管理模型服務商、金鑰和記憶設定的團隊。
- **不適用**：直接用訂閱帳號登入的客戶端（可以改用[訂閱反代上游](../gateway/07-upstreams.md#custom-upstreams)，Codex 就可以這樣使用 ChatGPT 訂閱，見[使用 ChatGPT 訂閱](../gateway/03-connect-clients.md#codex-chatgpt-subscription)），以及 Cursor、Trae 這類從廠商伺服器發起模型呼叫的客戶端。

閘道器支援三種模型 API：Anthropic Messages、OpenAI Chat Completions 和 OpenAI Responses（要求每個請求帶完整歷史，見[客戶端要求](../gateway/04-openviking-tools.md#client-requirements)）。請求轉發到你配置的模型服務地址，稱為**上游**。請求用哪種 API 發來，閘道器就用同一種 API 轉發，不做協議轉換。

## 關鍵術語 {#key-terms}

閘道器文件的各個頁面都按下表的含義使用這些術語。同一 OpenViking 帳號的使用者共用上游和上下文配置；閘道器金鑰和請求日誌歸各個使用者自己。

| 術語 | 含義 | 詳見 |
| --- | --- | --- |
| 上游 | 閘道器把請求轉發過去的模型服務地址，連同它的 API Key；每個上游只使用三種 API 中的一種。 | [上游](../gateway/07-upstreams.md#upstreams) |
| 上下文配置 | 一組有名字的記憶設定，例如召回預算、是否儲存對話、是否開放 OpenViking 工具；每個閘道器金鑰使用一份。 | [上下文配置](../gateway/08-context-profiles.md#context-profiles) |
| 閘道器金鑰 | 客戶端用來代替服務商 API Key 的金鑰（`ovgw_…`），繫結一位 OpenViking 使用者、一份上下文配置和一組上游。 | [閘道器金鑰](../gateway/09-gateway-keys.md#gateway-keys) |
| OpenViking API 金鑰 | 你在 OpenViking 的使用者金鑰：用它登入 Studio，它也決定以哪個帳號、哪個使用者的身份讀寫記憶。 | [金鑰和憑證](22-gateway-operations.md#keys-and-credentials) |
| 閘道器管理金鑰 | 可選的金鑰（`ovgm_…`）；設定後，只有帶上它的請求才能修改上游和上下文配置。誰能修改什麼，見[許可權矩陣](../api/25-gateway.md#credentials-and-account-scope)。 | [閘道器管理金鑰](22-gateway-operations.md#gateway-management-key) |
| 對話 | 閘道器認定屬於同一次聊天的一組請求；一段對話沿用開始時的上下文配置和上游。它的輪次儲存到一個 OpenViking 會話，某些情況下改存到新會話，例如客戶端改寫歷史時（見[儲存狀態](../gateway/10-overview-and-requests.md#saving-status)）。 | [閘道器如何識別對話](../gateway/03-connect-clients.md#how-conversations-are-recognized) |
| 召回 | 從 OpenViking 搜出和當前訊息相關的記憶，附加到這條訊息上。 | [模型看到什麼](../gateway/01-how-it-works.md#what-the-model-sees) |
| 儲存 | 把已完成的輪次寫入 OpenViking 會話（晚一輪進行），供之後的提交從中提取新記憶。 | [對話什麼時候儲存](../gateway/01-how-it-works.md#when-conversations-are-saved) |
| 提交 | 告訴 OpenViking 會話裡已儲存的輪次可以處理了：OpenViking 歸檔較早的輪次（會話中只留最新的訊息），並在後臺從中提取記憶。已儲存的輪次要等提交之後才會變成記憶。 | [對話什麼時候儲存](../gateway/01-how-it-works.md#when-conversations-are-saved) |
| 壓縮 | 對話接近模型的上下文視窗時，讓同一個模型寫一份摘要，替換截斷點之前的全部內容。 | [閘道器中的長對話](../gateway/05-long-conversations.md#long-conversations) |
| 提示詞快取 | 服務商的計費機制：請求開頭和上一次請求相同的部分按快取價計費（通常只有原價的一小部分），從第一個不同的位元組起按原價計費。 | [記憶原樣放回與提示詞快取](../gateway/01-how-it-works.md#replay) |
| 本地 dev 模式 | 以 dev 模式執行的 OpenViking 服務：繫結 `127.0.0.1`、未配置 `root_api_key`，開啟 Studio 不需要 API 金鑰，所有操作都以 `default` 使用者身份進行。 | [本地服務](../gateway/02-quickstart.md#local-server-no-api-key) |
| OpenViking 工具 | 你的 OpenViking 服務提供的工具（名為 `openviking_…`），由閘道器提供給模型，並在模型回答時由閘道器自己執行。 | [OpenViking 工具](../gateway/04-openviking-tools.md#agentic-memory-for-any-client) |

## 一張圖看懂架構 {#architecture-at-a-glance}

![OpenViking 閘道器的兩種執行形態。嵌入：客戶端訪問 OpenViking Server 的埠，Server 把 /gateway 下的所有路徑（模型 API、上傳和閘道器管理）交給同一程序裡的閘道器，閘道器通過本機迴環 HTTP、用使用者本人的 OpenViking 金鑰檢索和儲存記憶。獨立：openviking-gateway 用自己的埠提供同樣的 /gateway 路徑和只含閘道器頁面的 Studio，通過 HTTP(S) 呼叫已有的 OpenViking 服務。兩種形態下，閘道器都用同一種 API 把請求轉發給上游模型服務商；會話和記憶的正本在 OpenViking，閘道器自身的資料預設存在本機兩個 SQLite 檔案中，也可以存在共享的 Redis 中，開啟 OpenViking 加密時加密儲存](../../images/gateway/architecture.zh.svg)

- **執行在哪**：開啟後嵌入 OpenViking Server，和 Server 共用埠；也可以用 `openviking-gateway` 獨立執行，連線已有的 OpenViking 服務（開源版或商業版）。兩種方式下閘道器的所有 URL 都在 `/gateway` 下（例如 `/gateway/v1`），客戶端路徑相同，見[選擇部署方式](22-gateway-operations.md#deployment-options)。
- **和 OpenViking 的關係**：閘道器只呼叫 OpenViking 的公開介面，向量化和記憶提取都在 OpenViking 中完成。
- **資料在哪**：會話和記憶的正本在 OpenViking。閘道器預設使用兩個 SQLite 檔案，多副本部署可以改用共享 Redis。開啟 OpenViking 加密後，兩種後端中儲存的值都會加密。見[安全與資料](../gateway/11-security-and-data.md)。
- **出故障時**：OpenViking 不可用時，對話照常進行，只是不帶記憶，儲存會自動重試。閘道器停止服務時，經過它的模型呼叫全部失敗。

## 能得到什麼，代價是什麼 {#what-you-get-and-what-it-costs}

接入後你會得到：

- 每條新訊息都補上相關記憶；
- 新對話開頭帶上你的使用者畫像；
- 對話儲存回 OpenViking，並提取成新記憶；
- 長對話自動壓縮；
- 開啟 OpenViking 工具後，模型還能主動檢索、讀取和寫入記憶（見[讓任意客戶端擁有 Agentic 記憶](../gateway/04-openviking-tools.md#agentic-memory-for-any-client)）。

代價有三項：

- 每條新訊息的第一次模型呼叫最多多等 2 秒；
- 補充的記憶按輸入 token 計費，後續請求裡大部分按快取價計費；
- 觸發壓縮的那一輪多一次模型呼叫。

每一項在一輪對話裡具體怎麼發生，見[OpenViking 閘道器的工作原理](../gateway/01-how-it-works.md)。

## 閘道器還是外掛 {#gateway-or-plugin}

OpenViking 也能以外掛形式接入 Agent，例如 Claude Code、Codex、Cursor、TRAE、OpenCode、pi、DSH、OpenClaw 和 Hermes（見 [Agent 整合概覽](../agent-integrations/01-overview.md)）。兩者讀寫的是同一份 OpenViking 記憶，區別在於執行位置：閘道器位於模型呼叫的鏈路上，改的是模型收到的請求；外掛執行在某個 Agent 內部，靠這個 Agent 的事件工作。沒有哪一種總是更好，下面的差別大多由這一點決定，有些還因外掛而異。

### 逐項對比 {#gateway-and-plugin-compared}

| | OpenViking 閘道器 | Agent 外掛 |
| --- | --- | --- |
| 執行位置 | 客戶端和模型服務商之間的一個共享服務，只看得到模型請求。 | 通過 hook 或擴充介面執行在每個 Agent 內部，看得到 Agent 的會話、事件和工作區。 |
| 適用客戶端 | 能設定 Base URL 和 API Key、使用 Anthropic Messages、Chat Completions 或 Responses 的客戶端：聊天應用、SDK 指令碼、低程式碼平臺和程式設計 Agent。Cursor 和 TRAE 不行，它們的模型呼叫從廠商伺服器發出。 | 只有帶 OpenViking 外掛的 Agent。其他 MCP 客戶端可以接入 OpenViking 工具，但沒有自動召回和儲存。 |
| 模型登入方式 | 需要服務商的 API Key，由閘道器保管，或[由客戶端各自傳送](../gateway/03-connect-clients.md#bring-your-own-provider-key)。客戶端不能用訂閱帳號登入，可以改用[訂閱反代上游](../gateway/07-upstreams.md#custom-upstreams)。Codex 可以通過 [CLIProxyAPI](../gateway/03-connect-clients.md#codex-chatgpt-subscription) 使用 ChatGPT 訂閱；其他訂閱服務請自行確認其使用條款。 | 不經手模型呼叫，Agent 原來怎麼登入就怎麼登入，訂閱也可以。 |
| 召回 | 每條新的使用者訊息召回一次，結果附加在這條訊息末尾；檢索預設最多等 2 秒。預設檢索記憶、資源和技能。 | 在 Agent 的提問事件裡進行。多數外掛會帶上會話 ID，讓服務端結合對話擴充查詢；自動召回不含資源。 |
| 儲存 | 晚一輪儲存已完成的輪次，連同客戶端自己的工具呼叫和結果。子 Agent 請求和雜項請求不儲存。 | 跟隨 Agent 的事件，通常在每輪結束時。子 Agent 各不相同：Claude Code、OpenCode 和 DSH 存成單獨的會話，Codex 併入主會話，Hermes 不儲存。 |
| OpenViking 工具 | 由閘道器在回覆過程中執行，不支援工具或 MCP 的客戶端也能用。預設只開放只讀工具。呼叫[不經過客戶端的許可權確認](../gateway/04-openviking-tools.md#risks-and-controls)，每次呼叫顯示一行提示。 | 由 Agent 當作自己的工具執行，呼叫和結果出現在對話記錄裡，遵循 Agent 的工具許可權設定。 |
| 提示詞快取 | 在後續請求裡把每個記憶塊逐位元組原樣放回，快取字首保持不變。**概覽**頁顯示快取命中率。 | 因外掛而異。基於 hook 的外掛把記憶塊交給 Agent，由 Agent 儲存在自己的歷史裡；pi 和 OpenCode v2 也會讓之前的召回保持不變；OpenClaw 每輪在系統提示詞裡重建召回內容。 |
| 長對話 | 接近模型上下文視窗時由閘道器壓縮，任何客戶端都適用，包括從不壓縮的應用。[實驗性的 Agent 自管上下文視窗](../gateway/05-long-conversations.md#experimental-agent-managed-context-windows)讓模型自己決定何時開啟新視窗。 | 由 Agent 自己壓縮，多數外掛會先提交已捕獲的內容。pi 和 OpenClaw 可以用 OpenViking 的摘要替換 Agent 的摘要。 |
| 按專案區分記憶 | 看不到工作目錄。要按專案隔離，就給每個專案一個繫結不同 OpenViking 使用者的閘道器金鑰。 | 基於共享外掛程式碼的外掛會自動給記憶標上當前程式碼倉庫。 |
| 可見性 | 補充的記憶在客戶端裡看不到，除非上下文配置開啟了[召回摘要](../gateway/08-context-profiles.md#recall-summary)。Studio 的請求日誌記錄條數和儲存狀態，不記錄內容。 | Claude Code 的狀態列和 `/openviking-memory:ov` 命令顯示召回條數和補充內容的來源；pi 的狀態列顯示連線狀態。其他外掛沒有自己的狀態顯示。 |
| 部署與運維 | 一個服務，嵌入 OpenViking Server 或獨立執行。使用者只改 Base URL 和金鑰；上游、上下文配置和金鑰都在 Studio 裡管理。 | 每臺機器分別安裝和升級，各自配置 OpenViking 憑證。 |
| 團隊使用 | 管理員給每人簽發一個閘道器金鑰，可以單獨吊銷。閘道器保管服務商 API Key 時，使用者看不到它。 | 每人用自己的 OpenViking API 金鑰安裝外掛。行為設定可以寫進程式碼倉庫的 `.openviking/config.json`，按倉庫共享。 |
| 出故障時 | OpenViking 不可用時，請求照常發出，只是不帶記憶，儲存會自動重試。閘道器本身停止服務時（嵌入形態即 OpenViking Server 停止時），經過它的模型呼叫全部失敗。服務商 API Key 和尚未儲存的對話文本集中存放在閘道器，每次模型呼叫也多經過一跳。 | OpenViking 不可用時，Agent 等到外掛的召回超時（多數為 15 秒，Hermes 為 4 秒）後不帶記憶繼續；多數外掛會把寫入失敗的內容排隊存到磁碟。模型呼叫從不依賴 OpenViking。 |

各外掛的細節見 [Agent 整合能力](../agent-integrations/16-capability-reference.md)，閘道器的細節見 [OpenViking 閘道器的工作原理](../gateway/01-how-it-works.md)。

### 怎麼選 {#which-to-choose}

以下情況選閘道器：

- 客戶端沒有 OpenViking 外掛：聊天應用、SDK 指令碼、低程式碼平臺，或者你自己寫的、呼叫模型 API 的應用；
- 多人或多個客戶端要共用一套配置：服務商、記憶設定和每人的金鑰都在 Studio 裡管理，使用者的機器上什麼都不用裝；
- 客戶端自己沒有記憶工具或壓縮功能，閘道器可以把兩者都補上；
- 你的客戶端本來就用服務商 API Key，或者模型流量本來就經過一個集中代理。

以下情況選外掛：

- 你用 Claude 訂閱帳號登入 Claude Code；
- 你用 Cursor 或 TRAE，只有外掛能接入；
- 你希望記憶不用配置就按程式碼倉庫標記，或者希望每次 OpenViking 工具呼叫都在 Agent 裡展示並經過確認；
- 你希望儲存跟隨 Agent 的事件，例如子 Agent 的會話、Agent 壓縮前的儲存、退出時的提交；
- 你不想在模型呼叫鏈路上多加一個服務。

用 ChatGPT 訂閱的 Codex 兩種方式都行：裝它的外掛，或者經閘道器接 [CLIProxyAPI 上游](../gateway/03-connect-clients.md#codex-chatgpt-subscription)。

兩者也可以混用：程式設計 Agent 用各自的外掛，其他客戶端都走閘道器。同一個客戶端兩者都裝時，見下一節。

> **搶先試用新功能**：閘道器掌控整個模型請求，因此能做到外掛通過 Agent 擴充介面做不到的功能。[Agent 自管上下文視窗](../gateway/05-long-conversations.md#experimental-agent-managed-context-windows)是第一個，由模型自己決定何時開啟新的上下文視窗；之後還會有更多這類功能加入閘道器。想搶先試用，就把客戶端接入閘道器。

### 兩者同時使用時 {#when-both-are-in-use}

請求中出現 OpenViking 外掛的跡象時，閘道器會讓路：不再為這段[對話](#key-terms)補充記憶、儲存對話或提供 OpenViking 工具，只做轉發，避免同一份內容被補充兩次、儲存兩次。判斷依據有兩類：

- 外掛插入的記憶塊：`<openviking-context>`（基於共享外掛程式碼的外掛，例如 Claude Code、Codex、OpenCode、pi 和 DSH）、`<relevant-memories>`（OpenClaw）、`<memory-context>`（Hermes）或 `<relevant-memory>`；
- `X-OpenViking-Plugin` 請求頭。外掛和應用的作者可以傳送它，明確告訴閘道器不要補充記憶。

這個判斷對整段對話有效，其他對話不受影響；想重新用上閘道器記憶，需要不帶外掛開始新對話。Studio 的請求日誌會把這些請求標為**檢測到 OpenViking 外掛**。實際效果是記憶由外掛負責，閘道器只做轉發；客戶端仍然需要閘道器金鑰，以及配有服務商 API Key 的上游。

只接了 OpenViking MCP 工具、沒裝外掛的客戶端不算：閘道器照常補充記憶和儲存對話，只是不再提供自己的 OpenViking 工具，免得模型看到兩套同名工具。這時在**請求日誌**標籤頁的請求詳情裡，**OpenViking 工具**一項顯示**未提供：客戶端已接入 OpenViking 工具**，見[什麼時候不提供工具](../gateway/04-openviking-tools.md#when-tools-are-not-offered)。

## 下一步去哪 {#next-steps}

### 按任務查詢 {#by-task}

| 我想… | 去看 |
| --- | --- |
| 弄清一輪對話裡發生什麼、模型看到什麼、為什麼這樣設計 | [OpenViking 閘道器的工作原理](../gateway/01-how-it-works.md) |
| 從拿到閘道器金鑰到確認記憶生效，完整走一遍 | [快速上手](../gateway/02-quickstart.md) |
| 接入 Claude Code、Codex、聊天應用或 SDK | [把客戶端接入 OpenViking 閘道器](../gateway/03-connect-clients.md) |
| 讓模型使用記憶工具，或處理長對話 | [OpenViking 工具](../gateway/04-openviking-tools.md)和[閘道器中的長對話](../gateway/05-long-conversations.md) |
| 部署、對外暴露、升級和監控閘道器 | [部署與運維](22-gateway-operations.md) |
| 審查存了哪些資料、誰能看到、怎麼刪除 | [安全與資料](../gateway/11-security-and-data.md) |
| 排查報錯、警告或記憶沒有生效 | [排障](../gateway/12-troubleshooting.md) |
| 查某項設定的名稱、預設值或取值範圍 | [配置參考](../gateway/13-configuration.md) |
| 通過 HTTP 管理閘道器 | [管理 API](../api/25-gateway.md) |

### 按 Studio 標籤頁查詢 {#by-studio-tab}

在 Studio 側邊欄開啟 **OpenViking 閘道器**，每個標籤頁都有對應的文件：

| 標籤頁 | 用途 | 文件 |
| --- | --- | --- |
| **概覽** | 一眼看清請求量、提示詞快取、記憶召回和 OpenViking 的執行狀態 | [概覽](../gateway/10-overview-and-requests.md#overview) |
| **上游** | 閘道器轉發請求的模型服務地址 | [上游](../gateway/07-upstreams.md) |
| **上下文配置** | 對話如何使用記憶和工具 | [上下文配置](../gateway/08-context-profiles.md) |
| **金鑰** | 簽發和吊銷閘道器金鑰 | [閘道器金鑰](../gateway/09-gateway-keys.md) |
| **請求日誌** | 每次模型請求，以及其中記憶的處理情況 | [請求日誌](../gateway/10-overview-and-requests.md#requests) |
| **接入** | 閘道器地址和每種客戶端的具體設定 | [把客戶端接入 OpenViking 閘道器](../gateway/03-connect-clients.md) |

如果**上游**或**上下文配置**是隻讀的，或者 Studio 要求你**輸入閘道器管理金鑰**，見[誰能修改什麼](../gateway/06-manage-in-studio.md#who-can-change-what)。

### 相關文件 {#related-docs}

- [認證](04-authentication.md)：建立帳號、使用者和他們的金鑰。
- [公網訪問與反向代理](12-public-access.md)：為 OpenViking 配置 HTTPS。
- [Agent 整合概覽](../agent-integrations/01-overview.md)：為支援外掛的 Agent 安裝外掛。
- [MCP 整合](06-mcp-integration.md)：讓 MCP 客戶端直接使用 OpenViking 工具。
