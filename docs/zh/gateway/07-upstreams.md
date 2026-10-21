---
description: 新增和配置 OpenViking 閘道器轉發請求的模型服務地址。
---

# 管理閘道器上游

本頁面向負責新增和修復上游（OpenViking 閘道器轉發請求的模型服務介面）的人：先照步驟新增一個一次就能用的上游，再按 Studio 編輯頁的順序查閱每個欄位。在 Studio 中：**上游**標籤頁。新增、修改和測試上游需要寫許可權，見[誰能修改什麼](06-manage-in-studio.md#who-can-change-what)。

## 什麼是上游 {#upstreams}

上游是閘道器轉發請求的一個模型服務介面，只使用一種 API。閘道器不在 API 之間轉換，所以客戶端用到幾種 API，就要新增幾個上游，即使它們來自同一家服務商：

| 協議 | 使用者 |
| --- | --- |
| Anthropic Messages | Claude Code 和 Anthropic SDK |
| Chat Completions | 大多數聊天應用和 SDK |
| Responses | Codex CLI，前提是每個請求都攜帶完整歷史（見[客戶端要求](04-openviking-tools.md#client-requirements)） |

上游由整個帳號共享，但一個[閘道器金鑰](09-gateway-keys.md#gateway-keys)只能訪問簽發時選中的上游。

在編輯頁選擇服務商後，會自動填入它的預設 Base URL：

| 服務商 | 協議 | 預設 Base URL |
| --- | --- | --- |
| 通用 | 三種都有 | 無，自己填寫 |
| Anthropic | Anthropic Messages | `https://api.anthropic.com` |
| OpenAI | Chat Completions、Responses | `https://api.openai.com/v1` |
| DeepSeek | 三種都有 | `https://api.deepseek.com`；Anthropic Messages 為 `https://api.deepseek.com/anthropic` |
| 火山方舟 | 三種都有 | Chat Completions 和 Responses 為 `https://ark.cn-beijing.volces.com/api/v3`；Anthropic Messages 為 `https://ark.cn-beijing.volces.com/api/compatible` |
| BytePlus 方舟（海外站） | 三種都有 | Chat Completions 和 Responses 為 `https://ark.ap-southeast.bytepluses.com/api/v3`；Anthropic Messages 為 `https://ark.ap-southeast.bytepluses.com/api/compatible` |

## 新增上游 {#add-an-upstream}

1. 在**上游**標籤頁點**新增上游**，開啟**新建上游**編輯頁。頁面分為**介面**、**憑證**、**模型**和**路由**四部分。
2. 在**介面**中填寫**名稱**，選擇**服務商**和客戶端所用的**協議**。**Base URL** 下方的**請求將發往**應顯示服務商介面的完整地址，例如 `https://api.openai.com/v1/chat/completions`。
3. 在**憑證**中保持**由閘道器保管 API Key**，貼上服務商的 **API Key**。
4. 在**模型**中列出客戶端會請求的模型名，留空則接受任意模型名。視窗小於預設值的模型，要在**上下文視窗**里加一項，見[設定模型的上下文視窗](05-long-conversations.md#context-window)。
5. 點**新增上游**。應看到提示**已新增“<名稱>”**，列表裡出現新上游。如果編輯頁底部顯示**還需填寫或修正**，按提示修改對應欄位。
6. 在新上游這一行點**測試**，再選擇模型並點**執行測試**。應先看到**連線可用**，再看到**模型可用**；否則見[測試和刪除](#test-and-delete)。
7. [簽發一個閘道器金鑰](09-gateway-keys.md#issue-a-key)並選中這個上游。已有的金鑰只能訪問簽發時選中的上游。

## 介面 {#endpoint}

**介面**部分決定閘道器把請求發到哪裡，以及[上游](#upstreams)使用哪種 API。新建的上游預設服務商為*通用*、協議為 *Chat Completions*。

| 欄位 | 作用 |
| --- | --- |
| **名稱** | 在 Studio 中和簽發閘道器金鑰時顯示。 |
| **服務商** | 決定可選的協議，以及閘道器如何適配這家服務商的差異（見下文）。 |
| **協議** | 上游接受哪種 API。Anthropic 上游同時傳送 `x-api-key` 和 `Authorization: Bearer`，Chat Completions 和 Responses 上游只傳送 Bearer。 |
| **Base URL** | 服務商地址，閘道器在後面拼接介面路徑（見[Base URL 的拼接規則](#base-url)）。 |
| **拼接協議介面路徑** | 預設開啟。只有 Base URL 已經是完整請求地址時才關閉（見[直接發往完整請求地址](#exact-endpoint)）。 |

### 各服務商的差異 {#provider-differences}

列表裡沒有的服務商、LiteLLM 和 new-api 這類相容代理，以及 [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) 這類把訂閱帳號包裝成 API 的反向代理，都選*通用*，見[自定義上游](#custom-upstreams)。

- *通用*、*Anthropic* 和 *OpenAI* 轉發請求的方式相同。
- *DeepSeek*：請求帶工具時，DeepSeek 要求歷史中之前每條回覆都帶推理內容，而很多聊天應用不回傳它。DeepSeek 上游預設開啟[**補全推理內容回傳**](#restore-reasoning)，所以請求保持思考模式也能用 OpenViking 工具。關閉這項後，只有請求關閉了思考模式（`"thinking": {"type": "disabled"}`）才提供 OpenViking 工具；標準 Responses 請求沒有 `thinking` 欄位，這時也得不到工具。記憶照常補充。
- *火山方舟*和 *BytePlus 方舟*行為相同：Chat Completions 和 Responses 的每段對話使用一個固定的 `prompt_cache_key`，方舟的字首快取就能跟著對話走。請求的模型、思考模式、取樣引數、系統提示詞或工具和對話的第一個請求不同時，方舟會重建快取，請求被標為**快取引數有變化**（見[降級請求的異常](12-troubleshooting.md#issues-on-degraded-requests)）。

### Base URL 的拼接規則 {#base-url}

Base URL 按服務商 SDK 文件填寫，閘道器在後面拼接協議的介面路徑：

| 協議 | 拼接的路徑 | 說明 |
| --- | --- | --- |
| Chat Completions | `/chat/completions` | 只填域名時不會自動補 `/v1`，OpenAI 要寫 `https://api.openai.com/v1`。 |
| Responses | `/responses` | 同 Chat Completions。 |
| Anthropic Messages | `/v1/messages` | Base URL 不能以 `/v1` 結尾，否則儲存時被拒絕。 |

- 末尾的斜槓會被去掉。`/api/paas/v4` 這類帶版本路徑的地址可以直接使用。
- Base URL 可以帶查詢引數，例如 `?api-version=…`。客戶端的查詢引數接在後面，同名引數以 Base URL 裡的為準。
- 客戶端用方舟路徑（`/gateway/api/v3/`、`/gateway/api/compatible/v1/`）發來的請求，按同樣的規則拼接。
- 一個上游只有一個 Base URL。同一服務商的不同協議地址不同時，要分別建上游。

編輯頁會即時預覽最終的請求地址；OpenAI、方舟這類地址漏掉路徑，或者 Anthropic 地址多了 `/v1` 時，會給出提示和一鍵修正。

一些沒有預設的服務商的 Base URL，同樣按上面的規則拼接：

| 服務 | 協議 | Base URL |
| --- | --- | --- |
| Azure OpenAI（v1 介面） | Chat Completions 或 Responses | `https://RES.openai.azure.com/openai/v1` |
| Microsoft Foundry 上的 Claude | Anthropic Messages | `https://RES.services.ai.azure.com/anthropic` |
| Gemini（OpenAI 相容介面） | Chat Completions | `https://generativelanguage.googleapis.com/v1beta/openai` |
| 智譜 | Chat Completions | `https://open.bigmodel.cn/api/paas/v4` |
| 智譜 | Responses | `https://open.bigmodel.cn/api/v1` |
| 方舟 Coding Plan | Chat Completions、Responses | `…/api/coding/v3` |
| 方舟 Coding Plan | Anthropic Messages | `…/api/coding` |

### 直接發往完整請求地址 {#exact-endpoint}

如果 Base URL 已經是完整的請求地址，就關閉**拼接協議介面路徑**。以 Azure OpenAI 部署為例：

- **協議**選 *Chat Completions*，**服務商**選*通用*
- **Base URL** 填 `https://RES.openai.azure.com/openai/deployments/DEPLOYMENT/chat/completions?api-version=2024-10-21`
- 關閉**拼接協議介面路徑**
- **金鑰傳送方式**選 *api-key 請求頭*

關閉後，閘道器把該協議的請求直接發往這個 URL，不再拼接協議路徑。子路徑接在後面：Anthropic 的 Token 計數發往 `…/count_tokens`。Embeddings、模型列表等其他介面不會路由到這樣的上游，連線測試也會跳過它。

## 憑證 {#credentials}

**憑證**部分決定閘道器用什麼憑證訪問服務商。預設由閘道器保管服務商的 API Key，客戶端只需要[閘道器金鑰](09-gateway-keys.md#gateway-keys)。

- **API Key 由誰提供**：
  - **由閘道器保管 API Key**（預設）：閘道器傳送上游的 API Key。
  - **每個客戶端自帶 API Key**：每個請求除了閘道器金鑰，還要在 `X-OpenViking-Upstream-Key` 請求頭裡帶上客戶端自己的服務商 API Key，缺少時返回 401 "Upstream API key is missing"。閘道器按**金鑰傳送方式**轉發這個 API Key，Base URL 含 `{api_key}` 時則填進地址；`X-OpenViking-*` 請求頭本身從不轉發。各客戶端怎麼加這個請求頭，見[客戶端自帶服務商 API Key 時](03-connect-clients.md#bring-your-own-provider-key)。
- **金鑰傳送方式**（僅服務商為*通用*時）：`Authorization: Bearer`（預設）、`api-key` 請求頭（Azure OpenAI）或 `x-api-key` 請求頭。
- **金鑰放在地址裡**：服務商要求把金鑰寫在地址裡時，在 Base URL 的路徑或查詢引數中寫 `{api_key}`，例如 `?key={api_key}`。閘道器傳送時填入 URL 編碼後的金鑰，並且不再傳送鑑權請求頭。不要把金鑰本身寫進地址：能檢視上游的人都能看到 Base URL。
- **API Key**：加密儲存，之後不再顯示。留空表示保留已存的金鑰。
- **額外請求頭**加在發往這個上游的每個請求上，例如服務商的版本或組織請求頭，並覆蓋客戶端傳送的同名請求頭。取值和 API Key 一樣只寫不讀：留空表示保留已存的值，刪除這一行就刪除這個請求頭。不能設定 `Host`、`Content-Length`、`Transfer-Encoding` 和 `Connection`。

> **修改 Base URL 會清除已存的 API Key 和請求頭取值。** 每次改地址都要重新填寫，已存的金鑰不會被髮往新地址。

### Coding Plan 和訂閱金鑰 {#coding-plan-keys}

服務商通常只允許 Coding Plan 這類訂閱金鑰用在自家的程式設計工具裡，通過共享閘道器使用可能導致訂閱被封禁。閘道器無法從金鑰本身分辨它是不是訂閱金鑰，需要你自己勾選**這是 Coding Plan 或訂閱金鑰**來標記。

標記後，發往這個上游的請求一律被拒絕，返回 403 "Coding Plan upstreams are disabled; configure a model API key"，除非同時勾選**允許通過閘道器使用這個套餐**。請先確認套餐條款允許在服務商自己的工具之外使用，再勾選這一項。

Claude 訂閱令牌（`sk-ant-oat…`）無論怎麼勾選都會被拒絕，見[使用須知](01-how-it-works.md#what-to-expect)。

## 模型 {#models}

**模型**部分決定[上游](#upstreams)提供哪些模型名，以及它們在服務商那邊叫什麼。預設列表為空，表示接受任何模型名。

| 欄位 | 作用 |
| --- | --- |
| **模型** | 這個上游提供的模型名。只有列出的名稱和別名會出現在模型列表（`/gateway/v1/models`）裡。 |
| **模型別名** | 把客戶端使用的名稱對映為發給上游的模型，例如把 Claude Code 請求的 Claude 模型名對映到服務商提供的模型。別名出現在模型列表中，請求日誌顯示客戶端使用的名稱。 |
| **上下文視窗** | 按模型記錄視窗大小（token，至少 1,024），鍵是別名轉換之後、實際發給上游的模型名。 |

長對話按上下文視窗的比例觸發壓縮，所以視窗小於預設值的模型都要列出來，見[設定模型的上下文視窗](05-long-conversations.md#context-window)。

## 路由 {#routing}

**路由**部分決定有多個上游可選時閘道器如何選擇。對每個請求，閘道器在金鑰繫結的已啟用[上游](#upstreams)中，找出使用這種 API 並提供所請求模型的上游，選**優先順序**最高的一個。對話一旦開始，只要原來的上游還能服務就一直用它。

| 欄位 | 預設值 | 作用 |
| --- | --- | --- |
| **優先順序** | 0 | 數值大的優先。修改隻影響新對話，見[修改何時生效](06-manage-in-studio.md#when-changes-take-effect)。 |
| **啟用** | 開啟 | 停用的上游不接收請求，也不出現在模型列表裡。 |
| **允許 OpenViking 工具** | 開啟 | 決定能否通過這個上游提供 [OpenViking 工具](04-openviking-tools.md#choose-tools)。關閉後立即生效，已經帶工具的對話也受影響。 |
| **補全推理內容回傳** | 取決於服務商 | 把客戶端丟掉的推理內容放回後續請求（見下文）。 |
| **最小可快取長度** | 1,024 token | 僅火山方舟和 BytePlus 方舟：模型能快取的最短提示詞長度，隻影響請求日誌如何報告快取資格。 |

停用一個上游後，原本使用它的對話會轉到下一個候選上游，造成一次服務商快取未命中，並丟掉之前的 Claude 思考塊，這些請求被標為**上游已切換**（見[降級請求的異常](12-troubleshooting.md#issues-on-degraded-requests)）。想保留恢復的餘地，就停用而不是刪除。

閘道器不做故障轉移：選中的上游出錯時，客戶端收到這個錯誤；服務商無法訪問時返回 502 "Model upstream is unavailable"。

### 補全推理內容回傳 {#restore-reasoning}

客戶端回傳歷史時，常常丟掉模型之前回復裡的推理內容。**補全推理內容回傳**在 DeepSeek、火山方舟和 BytePlus 方舟上預設開啟，其他服務商預設關閉。

開啟後，閘道器記下經它轉發的每條回覆的推理內容，在後續請求中放回原處：

- Chat Completions：補回 `reasoning_content`。
- Anthropic Messages：放回 thinking 塊。
- Responses：把帶明文內容的 reasoning 項放回對應條目之前。

補回的內容每次逐位元組相同，服務商的提示詞快取照常命中，但計入輸入 token。客戶端自己回傳了推理內容的回覆保持不變。

有些請求即使開啟也補不回推理內容：對話換了上游（**上游已切換**）、Claude 對話丟了記憶記錄（**記憶記錄缺失**），或者客戶端把思考內容當作正文發回。DeepSeek 上游的這類請求同樣得不到 OpenViking 工具。

### 所有請求都失敗的上游 {#blocked-upstreams}

上游列表會用兩個標記提示發往該上游的請求都會失敗：

| 標記 | 原因 | 客戶端收到 |
| --- | --- | --- |
| **缺少 API Key** | 由閘道器保管 API Key，卻沒有儲存金鑰，例如改過 Base URL 之後。 | 401 "Upstream API key is missing" |
| **請求被拒絕** | [Coding Plan 上游](#coding-plan-keys)未獲準通過閘道器使用。 | 403 |

這樣的上游照樣參與路由：如果它在匹配的上游中優先順序最高，請求會直接失敗，不會轉到優先順序更低的上游。請修好它，或者停用它。

## 測試和刪除 {#test-and-delete}

**測試**檢查[上游](#upstreams)已儲存的介面地址、金鑰、模型和協議能否一起正常工作。測試的始終是已儲存的設定，改動後要先儲存。

1. 在上游列表或上游編輯頁的頁頭點**測試**。閘道器先檢查已儲存配置的連線，應看到**連線可用**。完整請求地址沒有模型列表可查，會跳過這一步。
2. 選擇或輸入模型名，點**執行測試**。閘道器使用已存的憑證傳送一次很小的生成請求，應看到**模型可用**。服務商可能對這次請求計費。

模型測試在上游允許 OpenViking 工具時會帶上這些工具，reasoning effort 使用模型預設值。各種結果的含義見[上游測試](../api/25-gateway.md#upstream-tests)。

以下情況不能測試：

- 沒有寫許可權，這時**測試**按鈕不顯示；
- 上游設為**每個客戶端自帶 API Key**，閘道器沒有可用於測試的金鑰；
- 上游還沒儲存 API Key。

Coding Plan 上游在勾選**允許通過閘道器使用這個套餐**之前，仍會阻止模型測試。

**刪除**會連同儲存的 API Key 和請求頭一起刪掉上游。有金鑰在用的上游不能刪除：刪除對話方塊會改為提供**停用**，也可以先吊銷這些金鑰。

## 匯入 OpenViking 模型配置 {#import-openviking-model-settings}

匯入把 OpenViking 服務端的 VLM 憑證轉成當前帳號的上游，省去重新填寫，只在嵌入部署中可用。在上游頁頭點**從 OpenViking 匯入**；上游列表還是空的時候，這個按鈕叫**使用 OpenViking 的模型配置**。沒有設定管理金鑰時只有 root（包括本地 dev）能匯入；設定了管理金鑰時需要先[解鎖編輯](06-manage-in-studio.md#unlock-editing)。

結果分三組顯示：已匯入、需要確認、未匯入。

- **需要確認**：Base URL 路徑中有一段名為 `coding` 或 `plan`（例如 `/api/coding/v3`）的上游會被標為 [Coding Plan](#coding-plan-keys)。確認服務商條款允許後，勾選**允許通過閘道器使用這個套餐**才能使用。
- **Azure OpenAI** 憑證（服務商 `azure`，或 LiteLLM 的 `azure/<deployment>`）會匯入為完整請求地址的上游，帶上配置的 `api_version`，金鑰放在 `api-key` 請求頭裡傳送。
- **未匯入**：Codex OAuth 憑證、缺少 `api_base` 的 LiteLLM 憑證，以及不使用 OpenAI Chat Completions API 的 LiteLLM 路由。原因見[匯入 VLM 配置](../api/25-gateway.md#import-vlm-settings)。

重複匯入不會產生重複的上游：

| 按服務端配置重新整理 | 保留你在閘道器裡的修改 |
| --- | --- |
| 地址、API Key、請求頭、協議、服務商、Coding Plan 標記、**拼接協議介面路徑**、**金鑰傳送方式** | 名稱、啟用狀態、優先順序、模型、別名、上下文視窗、**允許通過閘道器使用這個套餐** |

如果你取消了某個匯入上游的 Coding Plan 標記，下次匯入時會重新標上，在你勾選**允許通過閘道器使用這個套餐**之前，這個上游的請求都會被拒絕。

## 自定義上游：代理與訂閱額度 {#custom-upstreams}

任何相容這三種 API 之一的服務都能新增為上游，不一定是模型服務商本身。兩種常見用法：

- **計費、配額和負載均衡。** 閘道器不做這些。需要時在閘道器後面接一層 LiteLLM、new-api 這類服務，把它新增為上游。
- **使用訂閱額度。** 客戶端不能用訂閱帳號登入閘道器，但可以把 [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) 這類反向代理新增為上游。它把 ChatGPT（Codex）、Claude 等訂閱帳號包裝成 API，例如 Codex 就能經閘道器使用 ChatGPT 訂閱額度。Codex 的這種用法得到了 OpenAI 的認可：OpenAI Codex 負責人 Tibo 曾[公開介紹](https://x.com/thsottiaux/status/2076119366647894371)過用 CLIProxyAPI 接入 Codex 訂閱的做法，具體步驟見[使用 ChatGPT 訂閱](03-connect-clients.md#codex-chatgpt-subscription)。**其他訂閱服務能否這樣使用，請自行確認其使用條款。**

新增時服務商選*通用*，然後按[新增上游](#add-an-upstream)操作。

每個欄位的 API 名稱、預設值和取值範圍見[上游設定](13-configuration.md#upstream-settings)。

## 下一步 {#next-steps}

- [簽發閘道器金鑰](09-gateway-keys.md#issue-a-key)，選中你的上游。
- [接入客戶端](03-connect-clients.md#connect-clients)。
- [建立上下文配置](08-context-profiles.md#context-profiles)，設定召回和儲存。
- 請求失敗時，見[上游返回錯誤](12-troubleshooting.md#the-upstream-returned-an-error)。
