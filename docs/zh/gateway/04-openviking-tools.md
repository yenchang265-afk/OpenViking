---
description: 讓模型通過 OpenViking 閘道器代為執行的工具檢索、讀取和寫入 OpenViking 記憶，適用於任意客戶端。
---

# 閘道器中的 OpenViking 工具

開啟 OpenViking 工具後，模型在回答過程中自己檢索、讀取和寫入 OpenViking 記憶，工具呼叫由閘道器替客戶端執行。這項功能面向接不了 OpenViking MCP 伺服器的聊天應用和 API 應用；Claude Code、Codex 這類支援 MCP 或有外掛的客戶端，用 MCP 或外掛更合適，因為它們會顯示每次工具呼叫和結果，並在呼叫前請求確認。在 Studio 中的位置：**上下文配置** → **OpenViking 工具**，以及每個上游的**允許 OpenViking 工具**。

## 讓任意客戶端擁有 Agentic 記憶 {#agentic-memory-for-any-client}

自動召回是閘道器替模型猜它需要什麼；開啟 OpenViking 工具後，由模型自己決定查什麼、讀什麼、記什麼。工具由閘道器執行，客戶端的請求裡一個工具都沒有也能用。

![開啟 OpenViking 工具後的一條回覆：閘道器在客戶端的請求上附加召回的記憶和 OpenViking 工具定義，模型呼叫 OpenViking 工具時由閘道器用該使用者的 OpenViking 金鑰執行，再把結果接回請求繼續詢問模型，直到模型給出最終回答；客戶端收到的是一條帶提示行的連貫回覆，工具往返在下一輪被原樣放回](../../images/gateway/tool-loop.zh.svg)

- **一條回覆裡完成多步操作**：閘道器攔下模型發出的 OpenViking 工具呼叫，用該使用者的 OpenViking 金鑰執行，把結果接回再問模型，直到模型不再呼叫。客戶端只收到一條連貫的回覆，流式和非流式都支援。
- **客戶端自己的工具照常可用**：同一條回覆裡，模型可以同時呼叫 OpenViking 工具和客戶端工具（例如 Bash）。客戶端工具的呼叫原樣交給客戶端執行，照常經過客戶端的許可權確認。
- **下一輪還記得**：工具呼叫和結果不在客戶端的歷史裡，閘道器把這些往返存下來，下一輪原樣放回。模型記得自己查到過什麼，[提示詞快取](01-how-it-works.md#replay)也不受影響。

## 不同客戶端得到什麼 {#what-each-kind-of-client-gets}

| 客戶端 | 不經過閘道器時 | 經過閘道器並開啟 OpenViking 工具後 |
| --- | --- | --- |
| 聊天應用，例如 Cherry Studio、Open WebUI | 要用記憶得自己配 MCP 或寫工具，普通對話只收發文本。 | 模型自己檢索記憶、按 URI 讀取原文。勾選 `remember` 後，能記下使用者要求記住的事；勾選 `add_resource` 後，能把使用者附帶的檔案匯入 OpenViking。不帶任何工具的純聊天模式也能用。 |
| SDK 指令碼、低程式碼平臺 | 一問一答，多步操作要自己寫迴圈。 | 一次請求裡完成“檢索 → 讀取 → grep 精確匹配 → 作答”，程式碼不用改。 |
| Claude Code、Codex 等程式設計 Agent（未裝 OpenViking 外掛或 MCP） | 有自己的工具，但沒有 OpenViking。 | OpenViking 工具和 Bash 等客戶端工具在同一條回覆裡混用。需要逐次確認工具呼叫時，仍建議用外掛或 MCP。 |

## 模型能用哪些工具 {#which-tools-the-model-can-use}

工具清單直接來自你的 OpenViking 服務提供的 MCP 工具，名稱加上 `openviking_` 字首，所以 OpenViking 以後新增的工具也會自動可用。模型能做的事不超出該使用者自己的 OpenViking 許可權。常用的幾類：

| 用途 | 工具 | 模型拿來做什麼 |
| --- | --- | --- |
| 檢索 | `find`、`search`、`grep`、`glob` | 語義檢索記憶和資料；按正則或檔名精確查詢。 |
| 瀏覽和讀取 | `list`、`tree`、`read` | 按 URI 展開召回條目的原文，瀏覽記憶和技能目錄。 |
| 寫入 | `remember`、`write`、`edit` | 存一條長期記憶，寫入或區域性修改記憶檔案。 |
| 匯入 | `add_resource`、`add_skill` | 按 URL 匯入網頁或程式碼倉庫，匯入對話附件，用一段文本新建技能，都不需要客戶端有 shell。 |
| 刪除和許可權 | `forget`、`set_acl` 等 | 永久刪除記憶，修改共享資源的訪問許可權。 |

新建的上下文配置預設勾選哪些工具，見[選擇工具](#choose-tools)。另有一項實驗性設定 **Agent 自管上下文視窗**，會再給模型兩個用於開啟新上下文視窗的工具，見[實驗性：Agent 自管上下文視窗](05-long-conversations.md#experimental-agent-managed-context-windows)。

## 使用者看到什麼 {#what-users-see}

模型的文字照常即時流出。開啟**顯示工具呼叫**時（預設開啟，位於[上下文配置](08-context-profiles.md#context-profiles)的 **OpenViking 工具**部分），每次 OpenViking 工具呼叫都會在回覆中呼叫發生的位置留下一行提示：

```text
> OpenViking find: "上次定的釋出日期" — done
> OpenViking read: viking://user/alice/memories/release.md — done
```

- **提示寫什麼**：工具名；閘道器能識別呼叫物件時，還顯示檢索的查詢詞，讀取、列出或寫入的 URI，或者正在匯入的檔案或技能。使用者看不到完整引數和結果。
- **何時出現**：流式回覆中，呼叫一開始提示就出現，匯入這類耗時的呼叫進行時，使用者也能看到閘道器在工作；非流式回覆在最終訊息裡帶上同樣的提示。
- **放在哪裡**：每條提示單獨成段。在 Chat Completions 中，提示是回覆文本的一部分；在 Anthropic Messages 中，同一輪呼叫的提示放在同一個文本塊裡；在 Responses 中，放在同一條助手訊息裡。
- **只給使用者看**：模型看不到這些提示，它收到的是真實的呼叫和結果；閘道器也不把提示儲存到 OpenViking。
- **Token 用量**：客戶端收到的用量是這條回覆中所有模型呼叫之和，包括模型使用工具期間額外發起的呼叫。

### 工具呼叫提示 {#tool-call-notices}

每次呼叫結束後，閘道器在提示末尾補上結果：

| 結果 | 含義 |
| --- | --- |
| `done` | 呼叫完成。 |
| `failed` | 呼叫返回了錯誤。 |
| `skipped` | 閘道器拒絕了這次呼叫、沒有執行，例如工具輪數或 token 預算已經用完。 |

要隱藏提示，關閉**顯示工具呼叫**即可。和上下文配置的其他改動一樣，它隻影響新對話（見[修改何時生效](06-manage-in-studio.md#when-changes-take-effect)）。

## 風險和控制點 {#risks-and-controls}

> **警告**：勾選的工具直接執行，不經過客戶端的許可權確認，寫入和刪除資料的工具也一樣；工具呼叫提示只在呼叫之後報告，不是確認步驟。如果使用者需要逐次確認工具呼叫，請改用 OpenViking 外掛或 MCP 伺服器（見[閘道器還是外掛](../guides/15-gateway.md#gateway-or-plugin)）。模型能做的事以該使用者自己的 OpenViking 許可權為上限。

勾選會修改資料的工具前，先確認能接受這一點。給聊天應用用的配置，建議至少不勾選 `forget` 和 `set_acl`。

管理員能控制的地方：

| 控制點 | Studio 中的位置 | 作用 |
| --- | --- | --- |
| **OpenViking 工具**總開關 | **上下文配置** → **OpenViking 工具** | 為使用該配置的對話開啟或關閉閘道器工具。 |
| **工具**勾選 | **上下文配置** → **OpenViking 工具** | 決定模型能拿到哪些工具，見[選擇工具](#choose-tools)。 |
| **允許 OpenViking 工具** | **上游** → **路由** | 允許上下文配置通過這個上游提供工具。關閉後，進行中的對話也隨即停用。 |
| 工具輪數、總時長和 Token 預算 | **上下文配置** → **OpenViking 工具** → **進階設定** | 限制模型能連續使用工具多久，見[上限](#limits)。 |

## 選擇工具 {#choose-tools}

[上下文配置](08-context-profiles.md#context-profiles)中 **OpenViking 工具**部分的**工具**清單，決定模型能拿到哪些 OpenViking 工具。新建的上下文配置預設開啟 **OpenViking 工具**，用**使用推薦設定建立**新建的也一樣；除了閘道器已知會修改資料的工具，其餘工具預設都勾選：

| 預設狀態 | 工具 |
| --- | --- |
| 勾選 | `find`、`search`、`grep`、`glob`、`list`、`tree`、`read`、`download`、`list_watches`、`get_acl`、`list_users`、`list_groups`、`health` |
| 不勾選（會修改資料） | `remember`、`write`、`edit`、`add_resource`、`add_skill`、`forget`、`set_acl`、`cancel_watch` |

想讓模型儲存記憶就勾選 `remember`，想讓它匯入網頁或附件就勾選 `add_resource`。勾選任何會修改資料的工具之前，請先看[風險和控制點](#risks-and-controls)中的警告。

每個[上游](07-upstreams.md#upstreams)的**允許 OpenViking 工具**預設開啟。兩個開關都開啟時，新對話獲得選中的工具，名稱加上 `openviking_` 字首，例如 `openviking_find`、`openviking_read`。工具定義隨對話中的每個請求傳送，全部工具約佔 3,500 個輸入 token，所以取消用不到的工具也能省 token。

關於工具清單，還有幾點需要知道：

- **清單來源**：**工具**清單來自你的 OpenViking 服務，Studio 會說明每個工具的用途；OpenViking 為工具提供了標註時，還會在旁邊顯示**只讀**或**會修改資料**。OpenViking 把 `search` 標為**會修改資料**，但閘道器仍預設勾選它。
- **以後新增的工具**：OpenViking 以後新增的工具會預設可用，已有對話仍沿用開始時的工具清單。已有的上下文配置保留原來的勾選。
- **root 看到的清單為空**：OpenViking 不允許 root API 金鑰呼叫它的工具，所以 root 檢視時，閘道器用當前帳號中某把[閘道器金鑰](09-gateway-keys.md#gateway-keys)背後的 OpenViking 金鑰讀取清單。帳號裡還沒有閘道器金鑰時，清單可能為空，Studio 顯示提示“**簽發閘道器金鑰後即可載入工具清單。**”請先簽發一把金鑰，或者用使用者、帳號管理員的身份登入後再編輯配置。在此之前儲存的配置沿用預設勾選。
- **`download` 需要 shell**：`download` 返回一條一次性的 `curl` 命令，所以客戶端需要有 shell 工具，而且客戶端要能訪問這條連結。哪些名稱算 shell 工具、連結指向哪裡，見[通過客戶端的 shell 工具](#import-with-a-shell-tool)。

## 客戶端要求 {#client-requirements}

三種模型 API 都支援 OpenViking 工具，流式和非流式請求都可以，前提是客戶端每輪都回傳完整對話：

| 協議 | 客戶端要求 |
| --- | --- |
| Chat Completions | 回傳完整的 `messages` 歷史。 |
| Responses | 使用 `store: false` 和完整的 `input` 歷史；下一輪迴傳本輪返回的全部 `output` 內容，包括 reasoning 和客戶端工具呼叫。`item_reference` 無法還原完整歷史。 |
| Anthropic Messages | 回傳完整的 `messages` 歷史，保留 thinking 和 signature 塊。token 計數請求帶相同的工具定義，但不執行工具。 |

模型在同一條回覆中同時呼叫 OpenViking 工具和客戶端工具時，閘道器處理 OpenViking 呼叫，客戶端照常執行自己的工具並回傳結果。Responses 支援客戶端的 function 和 custom 工具，Anthropic Messages 支援客戶端的 tool_use 呼叫。

依賴服務商端已存狀態的 Responses 請求（`previous_response_id`、`conversation`、`background`），以及沒有設定 `store: false` 的 Responses 請求，原樣轉發：既不補充召回的記憶，也不提供 OpenViking 工具。之後查詢這些響應時，請求仍然發往建立它們的上游。

## 什麼時候不提供工具 {#when-tools-are-not-offered}

即使[上下文配置](08-context-profiles.md#context-profiles)開啟了 OpenViking 工具，個別請求發給模型時也可能不帶工具。這時在**請求日誌**標籤頁中展開該請求，詳情會顯示“**未提供：**”加上原因。Studio 顯示原因名稱，括號裡是管理 API 中對應的值（`tool_skip_reason`）：

| 原因 | 說明 |
| --- | --- |
| **Responses 請求需回傳完整對話，並設定 store: false**（`tools_require_full_history`） | Responses 請求需要 `store: false` 和完整 input 歷史，不能使用 `item_reference`。 |
| **這個上游關閉了 OpenViking 工具**（`upstream_tools_disabled`） | 上游關閉了**允許 OpenViking 工具**。 |
| **請求要求返回多個候選結果（n > 1）**（`tools_multiple_choices`） | 請求要求返回多個候選（`n` 大於 1）。 |
| **請求要求結構化輸出**（`tools_structured_output`） | 請求要求結構化輸出（`response_format`、`text.format` 或 `output_config.format`）。 |
| **客戶端傳入了非函式型別的工具**（`tools_non_function`） | Chat Completions 客戶端傳入了 function 以外型別的工具。 |
| **客戶端指定了必須呼叫的工具**（`tools_forced_choice`） | `tool_choice` 不是 `auto` 或 `none`：例如 `required`、Anthropic 的 `any` 或 `tool`、指定某個函式，或者 Responses 的 `allowed_tools` 這類物件形式。 |
| **DeepSeek 開啟了思考模式，但之前回復的推理內容補不回來**（`deepseek_reasoning_history_required`） | 上游是 DeepSeek，開啟了思考模式（標準 Responses 請求沒有 `thinking` 欄位，按開啟處理），而之前的回覆發到 DeepSeek 時會缺推理內容。在上游的**路由**部分開啟**補全推理內容回傳**（[說明及補不回的情況](07-upstreams.md#restore-reasoning)），或者傳送 `"thinking": {"type": "disabled"}`。 |
| **客戶端已接入 OpenViking 工具**（`tool_name_collision`） | 閘道器在這段對話剩下的部分不再提供自己的工具（回傳的歷史裡模型已經呼叫過閘道器工具的請求仍保留工具）。判斷條件見[客戶端自己接了 OpenViking 工具時](#client-has-openviking-tools)。 |
| **這段對話首次需要工具時無法載入 OpenViking 工具清單**（`tools_unavailable`） | 無法從 OpenViking 載入工具清單，也沒有之前載入成功的清單。連線恢復後開始新對話。 |
| **這段對話沒有 OpenViking 工具**（`tools_not_selected_at_session_start`） | 上下文配置開啟了工具，但這段對話的工具列表為空：配置裡一個工具都沒選，或者對話在閘道器升級前就已開始。開始新對話即可。 |

### 何時決定是否提供 {#when-the-decision-is-made}

對話是否帶工具，由它第一個能用工具的請求決定（生成標題這類輔助請求不算），之後保持不變，所以修改上下文配置隻影響新對話。唯一的例外是關閉：模型還沒呼叫過閘道器工具時，客戶端出現了自己的 OpenViking 工具，例如 MCP 伺服器在第一輪之後才連上。

輔助請求、子 Agent 請求和檢測到 OpenViking 外掛的對話都不帶 OpenViking 工具。這類請求如果回傳了模型用過這些工具的歷史，閘道器仍附上工具定義，讓這段歷史保持有效，但拒絕新的 OpenViking 呼叫。客戶端自己的工具在每個請求裡都照常可用。

### 客戶端自己接了 OpenViking 工具時 {#client-has-openviking-tools}

滿足以下任一條件，閘道器就認為客戶端已經接了 OpenViking 工具（`tool_name_collision`）：

- MCP 服務名（`server_label`、`mcp_server_name`、`mcp_servers[].name`）含單詞 `openviking`。
- 以 OpenViking 工具名結尾的工具名中也含這個單詞，例如 `mcp__claude_ai_OpenViking__search`；聯結器的 `authenticate` 工具不算。獨佔一行列出的延遲載入工具名也算。
- 帶字首、以 OpenViking 工具名結尾的工具（例如 `mcp__ov__read`），定義中出現 `viking://`。
- 任一請求中，客戶端工具和閘道器工具同名，因為上游會拒絕重名工具。

誤判同樣會持續整段對話，開始新對話即可。

## 匯入檔案和技能 {#import-files-and-skills}

OpenViking 服務提供匯入工具（`add_resource`、`add_skill`）、上下文配置也勾選了它們時，模型就能匯入資料。按 URL 匯入不需要額外條件；匯入本地檔案則需要客戶端有 shell 工具，或者使用者訊息帶附件。上傳大小受閘道器的請求大小上限 `max_body_bytes` 限制（預設 32 MiB，見[副作用](05-long-conversations.md#side-effects)）。

### 通過客戶端的 shell 工具 {#import-with-a-shell-tool}

shell 工具指名稱類似 bash、shell、exec_command、terminal 或 run_command 的客戶端工具。匯入工具返回一個一次性上傳連結，模型再用客戶端的 shell 工具上傳檔案，這一步經過客戶端的許可權確認。技能目錄會先打包成 zip。

上傳連結，以及 `download` 返回的下載連結，指向 `public_url` 加 `/gateway/uploads` 或 `/gateway/downloads`。所以 `public_url` 必須是客戶端能訪問的地址（見[對外地址](../guides/22-gateway-operations.md#public-address)），前面的代理也要像其他路徑一樣轉發這兩個路徑。沒有設定 `public_url` 時，匯入失敗並提示 "Set gateway.public_url for client uploads and downloads"。把 `mcp_file_links` 設為 `direct` 後，閘道器原樣透傳 OpenViking 返回的連結，連結直接指向 OpenViking Server，此時 Server 的 `OPENVIKING_PUBLIC_BASE_URL`（或 `server.public_base_url`）必須是客戶端能訪問的地址。

### 通過訊息附件 {#import-from-an-attachment}

沒有 shell 工具時，模型可以匯入使用者訊息裡附帶的檔案，檔案可以是 base64 資料，也可以是附件文本，支援 Chat Completions `file` 內容塊（`file.file_data`，可以是 base64 或 `data:` URL）、Responses `input_file` 和 Anthropic `document.source` 中內嵌的 `base64`、`text` 資料。Open WebUI 通常只傳送提取出的文本，這些文本作為文本檔案匯入。

附件中的 URL 和服務商的檔案 ID 不會被抓取；要匯入遠端資源，請用匯入工具的 URL 引數。

## 上限 {#limits}

工具輪數、總時長和 Token 預算預設都不限：和 Agent 自己的工具迴圈一樣，模型會一直使用 OpenViking 工具直到完成。在 Studio 中，這些上限位於**上下文配置** → **OpenViking 工具** → **進階設定**，欄位留空表示不限：

| 設定 | 預設值 | 達到上限時 |
| --- | --- | --- |
| **每次請求的工具輪數** | 不限 | 拒絕之後的 OpenViking 呼叫，模型用已有結果和客戶端自己的工具繼續。 |
| **單次呼叫超時** | 30 秒 | 這次呼叫向模型返回錯誤。 |
| **結果大小上限** | 65,536 位元組 | 結果被截斷。 |
| **總時長** | 不限 | 請求失敗，報錯 "Hidden tool request timed out"，見[失敗處理](#failure-handling)。 |
| **Token 預算** | 不限 | 拒絕之後的 OpenViking 呼叫，模型用已有結果和客戶端自己的工具繼續。這不是計費上限，最終回答可能超出它。 |

API 名稱和取值範圍見[上下文配置的設定](13-configuration.md#context-profile-settings)。

> **注意**：非流式請求在客戶端斷開後仍會繼續執行，所以客戶端傳送非流式請求時，請設定**總時長**。流式請求中，使用者可以隨時中斷回覆，客戶端斷開後閘道器也會停止。

Token 預算只計算模型使用 OpenViking 工具時新增的呼叫、結果和後續生成內容，客戶端已有的對話、工具定義和圖片不計入。閘道器保留客戶端設定的回答長度上限（`max_tokens`、`max_completion_tokens` 或 `max_output_tokens`）。

想知道某個請求用了多少，在**請求日誌**標籤頁中展開它：**OpenViking 工具**一項會顯示輪數、額外模型呼叫次數和增加的 Token 數；預算用完、後續呼叫被拒絕時，還會顯示**工具 Token 預算已用完**。

這幾項預設值改為“不限”之前儲存的上下文配置仍保留原來的值（5 輪、120 秒、100,000 token），清空欄位即可取消限制。

## 失敗處理 {#failure-handling}

單次 OpenViking 呼叫失敗時，模型收到錯誤結果，可以據此繼續回答。只有以下情況會讓整個回答失敗：

- 服務商拒絕了後續的模型請求。
- 模型呼叫了這段對話裡沒有提供的 OpenViking 工具，或者 OpenViking 呼叫被拒絕後仍堅持呼叫。
- **Hidden tool request timed out**：OpenViking 工具的往返超過了上下文配置中工具的**總時長**；沒有設定總時長時，是往返中某次模型請求超過了 `upstream_timeout_seconds`。

這時客戶端收到錯誤，請求日誌顯示 **OpenViking 工具呼叫失敗**（`hidden_tool_loop_failed`）。錯誤的形式取決於請求型別：

| 請求 | 客戶端收到什麼 |
| --- | --- |
| 流式 | 流以錯誤事件結束：Responses 是 `response.failed`，Chat Completions 和 Anthropic Messages 是型別為 `gateway_tool_error` 的 `error`。此時 HTTP 狀態碼已經是 200。 |
| 非流式，服務商拒絕了後續請求 | 原樣返回服務商的錯誤內容和狀態碼。 |
| 非流式，超時 | 504（`gateway_http_504`）。 |
| 非流式，其他失敗 | 502，響應體為 `{"reason": "gateway_http_502", "detail": "..."}`。 |

另外兩種情況：

- **某個上游反覆失敗**：關閉它的**允許 OpenViking 工具**。用過這些工具的 Claude 對話可能隨之出現**工具歷史無法繼續使用**（`hidden_tool_history_unavailable`）：之前的思考內容無法繼續使用，閘道器已將其去掉。可以按請求詳情中的停用原因恢復設定，或者開始新對話。
- **重試**：重試的工具呼叫複用第一次呼叫的結果，中斷的寫入操作不會自動重做。

## 下一步 {#next-steps}

- [上下文配置](08-context-profiles.md#context-profiles)：為每類客戶端一起配置召回、儲存和工具。
- [檔案匯入或下載失敗](12-troubleshooting.md#file-imports-or-downloads-fail)：排查上傳和下載連結的問題。
- [上下文配置的設定](13-configuration.md#context-profile-settings)：各項工具設定的 API 名稱和取值範圍。
