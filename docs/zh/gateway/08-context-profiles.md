---
description: 建立上下文配置，決定 OpenViking 閘道器為每個閘道器金鑰如何召回和儲存記憶。
---

# 管理閘道器上下文配置

在 Studio 中：**上下文配置**標籤頁。上下文配置決定 OpenViking 閘道器如何為使用它的閘道器金鑰召回記憶、儲存對話、處理長對話和提供 OpenViking 工具。本頁按配置編輯頁的分組逐一說明各項設定及預設值；修改配置需要寫許可權，見[誰能修改什麼](06-manage-in-studio.md#who-can-change-what)。

## 什麼是上下文配置 {#context-profiles}

[上下文配置](../guides/15-gateway.md#key-terms)是一組有名字的記憶設定。每個[閘道器金鑰](09-gateway-keys.md#gateway-keys)在簽發時選定一份配置，一份配置可以供多個金鑰使用。[直接使用 OpenViking API 金鑰](09-gateway-keys.md#openviking-keys)的客戶端使用帳號中 ID 為 `default` 的配置（快速模式建立的那份），沒有時使用部署的 `default_profile`；它們不計入使用這份配置的金鑰。比如準備一份“Coding”配置，召回記憶、資源和技能；再準備一份“Chat”配置，只召回記憶，預算也小一些。

嵌入式 dev 模式在啟動時將 `default_profile` 一次性寫入 `default` 帳號；之後修改 `ov.conf` 不會改變已儲存的配置，請在 Studio 中修改。

除了名稱和[允許客戶端覆蓋設定](#client-overrides)開關，一份配置分為四個部分，下表中的預設值也就是推薦設定：

| 部分 | 作用 | 主要設定和預設值 |
| --- | --- | --- |
| 召回記憶 | 用每條新的使用者訊息檢索 OpenViking，把相關內容附加到這條訊息上。 | 檢索範圍：記憶、資源、技能 · 單條訊息預算：1,600 token · 單個上下文視窗預算：30,000 token · 相關度閾值：0.35 · 超時時間：2 秒 |
| 儲存對話 | 把完成的輪次寫入 OpenViking 會話並提交，供 OpenViking 提取記憶。 | 空閒提交時間：600 秒 · 提交閾值：20,000 token · 保留最近訊息：10 |
| 長對話 | 對話接近上下文視窗時，讓同一個模型寫摘要，替換之前的訊息。 | 壓縮：開啟 · 壓縮時機：視窗的 0.9 · 摘要長度上限：8,000 token · Agent 自管上下文視窗：關閉 |
| OpenViking 工具 | 讓模型在回答時使用 OpenViking 的工具。 | 開啟 · 勾選全部工具，見 [OpenViking 工具](04-openviking-tools.md) |

每個部分都有自己的開關，長對話部分的壓縮和 Agent 自管上下文視窗各有一個。召回和儲存相互獨立，只召回不儲存、只儲存不召回都可以。

儲存後的修改只對之後開始的對話生效，見[修改何時生效](06-manage-in-studio.md#when-changes-take-effect)。

### 建立、複製或刪除配置 {#manage-profiles}

1. 開啟 **上下文配置** 標籤頁。標籤頁為空時，選擇**使用推薦設定建立**可一鍵建立一份名為“預設”的配置，選擇**自定義**則先開啟編輯頁。已有配置後，改用**新建配置**。
2. 在編輯頁填寫**名稱**，為閘道器金鑰選擇配置時會顯示這個名稱。名稱下方的**允許客戶端覆蓋設定**預設開啟，見[允許客戶端覆蓋設定](#client-overrides)。再按本頁的說明調整各部分。
3. 選擇**建立配置**；編輯已有配置時選擇**儲存**。之後能看到這份配置的卡片，上面概括了各部分的設定和使用它的金鑰數（剛建立時顯示**沒有金鑰在用**）。

其他操作：

- **複製一份**：在卡片上或編輯頁的**更多操作**（⋯）選單中，開啟一份名為“… 副本”的複製。想做一份變體，這樣最快。
- **恢復推薦設定**：在同一個選單中，把四個部分恢復為推薦設定，名稱和**允許客戶端覆蓋設定**保持不變，儲存後生效。
- 有金鑰在用的配置不能刪除。先吊銷這些金鑰；如果還需要它們，先簽發使用其他配置的新金鑰來替換。
- Studio 處於只讀狀態時，卡片上顯示**檢視**而不是**編輯**，也不能建立、複製或刪除配置，見[解鎖編輯](06-manage-in-studio.md#unlock-editing)。

## 召回記憶 {#recall-memory}

**召回記憶**部分（預設開啟）控制[召回](../guides/15-gateway.md#key-terms)：每收到一條新的使用者訊息，閘道器就用它檢索 OpenViking，把相關內容附加到這條訊息上。模型最終收到什麼，見[模型看到什麼](01-how-it-works.md#what-the-model-sees)。各項設定按編輯頁中的順序排列：

| 設定 | 預設值 | 控制什麼 |
| --- | --- | --- |
| **會話開頭提供使用者畫像** | 開啟 | 新對話開始時，向模型提供你的 OpenViking 使用者畫像。 |
| **會話開頭提供 soul.md** | 開啟 | 新對話開始時，向模型提供你儲存在 OpenViking 的 `soul.md`，也就是你給模型的長期指令，並告訴模型遵循它。soul 全文提供。 |
| **開頭內容預算** | 4,000 token | 開頭的使用者畫像、記憶目錄和技能目錄最多佔用多少。soul 不計入。 |
| **顯示召回摘要** | 關閉 | 在回覆開頭加一行摘要，見[召回摘要](#recall-summary)。 |
| **檢索範圍** | 記憶、資源、技能 | 召回時檢索哪些內容。 |
| **單條訊息預算** | 1,600 token | 一條訊息最多附加多少記憶。 |
| **單個上下文視窗預算** | 30,000 token | 一個上下文視窗內累計最多附加多少記憶。 |
| **相關度閾值** | 0.35 | 只附加相關度不低於該值的結果，取值 0 到 1。值越高，附加的內容越少、越貼切。 |
| **超時時間** | 2 秒 | 一次檢索最多等多久。 |
| **檢索文本長度**（在**進階設定**中） | 8,000 個字元 | 取訊息的多少字元作為檢索文本。 |
| **Peer 範圍**（在**進階設定**中） | 所有 Peer，當前 Peer 優先 | 除使用者自己的記憶外，召回和 OpenViking 工具能看到哪些 Peer 的記憶。 |
| **按分類限量**（在**進階設定**中） | 關閉 | 每個分類最多附加多少條。 |

這些設定如何配合：

- **開頭內容。** **會話開頭提供使用者畫像**和**會話開頭提供 soul.md** 獨立於召回，彼此也互不影響。提供 OpenViking 的 `read` 工具（`openviking_read`）時，開頭還會提供記憶目錄和技能目錄。技能最多佔**開頭內容預算**的四分之一，預算設為 0 時省略畫像和目錄。soul 全文提供，不計入這份預算，只有它自己的開關能關掉它。這份預算不佔召回預算，見[對話開頭的內容](01-how-it-works.md#the-opening-context)。
- **補充什麼。** 召回內容由 OpenViking 在預算內選取和排版，也可能只給出 URI，供模型之後讀取。
- **檢索文本。** 檢索文本是去掉客戶端噪聲後的使用者訊息，最多取**檢索文本長度**個字元。少於 3 個字元的訊息不檢索。
- **預算。** 每條訊息最多補充**單條訊息預算**和**單個上下文視窗預算**剩餘額度中較小的那個；剩餘額度不足 64 token 時跳過檢索。無論是閘道器還是客戶端壓縮了對話，單個上下文視窗預算都重新計算。這裡的 token 數是偏保守的估算，不是服務商的計費數。
- **關閉召回。** 把**單個上下文視窗預算**設為 0 就等於關閉召回；**單條訊息預算**最小為 64。
- **超時。** OpenViking 在**超時時間**內沒有返回時，這條訊息不帶記憶發給模型，之後也不會補上，客戶端重試也一樣。
- **Peer 範圍。** 主要用於請求會帶 [Peer](03-connect-clients.md#peer) 的金鑰。**所有 Peer，當前 Peer 優先**在使用者自己的記憶之外加上這個請求的 Peer 的記憶，其他 Peer 的記憶仍可能被召回，只是分數略有扣減。**僅當前 Peer**讓召回和 OpenViking 工具都查不到、讀不到其他 Peer 的記憶；不帶 Peer 的請求與預設值相同。見[只召回當前 Peer](03-connect-clients.md#peer-scope)。
- **按分類限量。** 可以給事件、實體、偏好、經驗、資源和技能六類分別設條數上限，只檢索上限大於 0 的類別。關閉時，所有來源放在一起排序。

### 召回摘要 {#recall-summary}

召回摘要是回覆開頭的一段簡短說明，寫明 OpenViking 為這條新使用者訊息補充了什麼，或者召回為什麼失敗。它預設關閉，在[上下文配置](#context-profiles)的**召回記憶**部分開啟**顯示召回摘要**即可。模型看不到摘要。示例：

```text
> OpenViking context: soul, user profile, memory index, skill list, earlier sessions
> OpenViking recall: 4 items (3 memories, 1 resource) — booking_duplicate_handling, user_lang_pref, +2 more
```

- `context` 行只出現在對話的第一條回覆裡，列出開頭實際提供的內容：soul、使用者畫像、記憶目錄、技能目錄，以及這段對話較早部分在 OpenViking 中的位置。
- `recall` 行按類別統計召回條數，最多列出三個條目名。檢索失敗時改為說明原因，例如 `> OpenViking recall failed: OpenViking unavailable`。沒有找到內容、召回已關閉或預算用完時不顯示這一行，所以第一條回覆之後，這類訊息沒有摘要。
- 工具步驟等後續請求不顯示摘要；客戶端重試同一條訊息時，摘要和第一次相同。
- 摘要在 Anthropic Messages 中單獨佔一個文本塊，在 Responses 中單獨佔一條助手訊息，在 Chat Completions 中位於回覆文本開頭。要求結構化輸出的請求，以及 `n` 大於 1 的 Chat Completions 請求，不顯示摘要。
- 客戶端隨下一條訊息把回覆發回來時，閘道器先刪掉摘要再轉發，也不會把它儲存到 OpenViking。

## 儲存對話 {#save-conversations}

**儲存對話**部分（預設開啟）控制[儲存](../guides/15-gateway.md#key-terms)：每一輪結束時，閘道器把它寫入 OpenViking 會話，再按下面的設定提交會話，供 OpenViking 歸檔已儲存的訊息並從中提取記憶。閘道器什麼時候寫入，見[對話什麼時候儲存](01-how-it-works.md#when-conversations-are-saved)。

| 設定 | 預設值 | 控制什麼 |
| --- | --- | --- |
| **空閒提交時間** | 600 秒 | 最後一輪結束後多久沒有新的一輪結束，就提交剩下的全部訊息。 |
| **提交閾值** | 20,000 token | 一輪結束時，待提交的內容達到多少 token 就提交一次。 |
| **保留最近訊息** | 10 | 按提交閾值提交時，會話中留下最近多少條訊息。 |

- 預設由閘道器提交，任何 OpenViking Server 都適用。閘道器建立 OpenViking 會話時關閉 OpenViking 自己的自動提交，在每一輪結束時檢查**提交閾值**，併為每段對話計時**空閒提交時間**；更新的一輪結束時重新計時，一輪中間的截斷儲存和失敗的儲存不影響正在等待的提交。每次提交後，OpenViking 在後臺提取記憶。
- 空閒提交歸檔全部訊息，不保留最近訊息；按提交閾值提交時，**保留最近訊息**按訊息條數計算。
- 空閒提交失敗時，到期時間保留，閘道器每分鐘再試一次，直到成功；OpenViking 被標記為不可用期間暫停重試。被 OpenViking 拒絕的空閒提交（金鑰被拒絕，或會話已不存在，即 HTTP 401、403、404）不再重試，等這段對話的下一輪結束後重新計時。按提交閾值提交失敗時不單獨重試，由之後的空閒提交或下一輪的閾值檢查補上。提交失敗只記在閘道器日誌裡（`could not commit`），不改變請求記錄。
- 空閒提交的到期時間和要使用的金鑰記錄 ID 隨儲存進度記在閘道器儲存裡，不含對話文本，所以閘道器重啟、崩潰或 Pod 被終止都不會丟掉等待中的提交：每個閘道器程序每分鐘檢查一次，把到期已滿一分鐘、還沒有提交的補上，因此這類提交會比到期時間晚一兩分鐘。空閒提交總是在執行時才從這份金鑰記錄裡取 OpenViking 金鑰：到那時記錄已不存在（金鑰被吊銷或過期）的，這次提交不再執行，等這段對話的下一輪結束後重新計時。停機時閘道器不執行、也不等待空閒提交。
- 會話已經存在時（例如由更早版本的閘道器或另一種提交方式建立），閘道器在這段對話第一次寫入前，以及修改 `openviking_auto_commit` 之後的第一次寫入前，把它的自動提交策略（`auto_commit_policy`）改成當前方式的設定。
- OpenViking Server 0.5.0 及以上版本預設繼承使用者的記憶策略，包括[記憶型別](../api/16-memory.md)限制，閘道器的提交不生成 Working Memory；更早版本的 Server 上，閘道器建立會話時關閉 Working Memory。要為會話策略指定型別，用管理 API 或 `X-OpenViking-Context` 請求頭把 `capture_memory_types` 設為這些型別的名稱，例如 `["preferences","events"]`；設為空列表時只儲存對話，不提取記憶。Studio 中沒有這項設定，在 Studio 中儲存配置時保留原值。OpenViking 不認識的名稱會使這段對話的每次儲存都失敗，見[配置參考](13-configuration.md#profile-saving)。

**交給 OpenViking 提交。** 閘道器配置 `openviking_auto_commit: true`（見[閘道器欄位](13-configuration.md#gateway-fields)）時，閘道器不提交，也不計時，而是把這三項寫入會話的 `auto_commit_policy`，由 OpenViking 的會話自動提交完成，適合開啟了會話自動提交的 OpenViking Server。唯一的例外是剛開啟這項設定時：之前已經在等待的空閒提交仍由閘道器執行，因為這些會話要等對話再儲存一輪之後，OpenViking 才會自動提交。三項設定的含義不變，與預設方式的區別如下：

- 按提交閾值提交在任何 Server 上都有效；如果之前的一次提交還在提取記憶，OpenViking 跳過這次提交，由之後的寫入或空閒提交補上。
- 空閒提交只在 OpenViking Server 開啟 `memory.session_auto_commit.enabled`（0.4.x 版本為 `memory.session_auto_commit.idle_enabled`）時發生，開源版 Server 預設關閉，見[配置指南](../guides/01-configuration.md#session-auto-commit-配置)。沒有開啟時，達不到提交閾值的對話只儲存為訊息，不會歸檔，也不會提取記憶。
- OpenViking 要求空閒提交時間至少 300 秒，低於 300 秒的值按 300 秒處理。Server 使用預設的本地掃描（`idle_backend: local`）時，每隔 `check_interval_seconds`（預設 600 秒）檢查一次，提交最多再晚一個間隔；`redis` 後端按時提交。
- OpenViking Server 0.5.0 及以上版本按使用者自己的記憶策略決定是否生成 Working Memory（預設關閉）；預設方式下閘道器的每次提交都不生成 Working Memory。

## 長對話和 OpenViking 工具 {#long-conversations-and-tools}

編輯頁的最後兩個部分各有專門的頁面：

- **長對話**部分包括**壓縮**及其**壓縮時機**和**摘要長度上限**、實驗性的 **Agent 自管上下文視窗**及其**軟提醒時機**和**硬提醒時機**，以及**進階設定**中的**預設上下文視窗**。詳見[閘道器中的長對話](05-long-conversations.md#long-conversations)；視窗較小的模型需要設定視窗大小，見[設定模型的上下文視窗](05-long-conversations.md#context-window)。
- **OpenViking 工具**部分包括**工具**清單和**顯示工具呼叫**，**進階設定**中還有**每次請求的工具輪數**、**單次呼叫超時**、**結果大小上限**、**總時長**和 **Token 預算**。詳見[選擇工具](04-openviking-tools.md#choose-tools)和[上限](04-openviking-tools.md#limits)。閘道器執行所選工具時不經過客戶端的許可權確認，決定讓模型使用會修改資料的工具之前，請先閱讀[風險和控制點](04-openviking-tools.md#risks-and-controls)。

每項設定的 API 名稱和取值範圍見[配置參考](13-configuration.md#context-profile-settings)。

## 允許客戶端覆蓋設定 {#client-overrides}

**允許客戶端覆蓋設定**位於配置的**名稱**下方，預設開啟。開啟後，客戶端可以為對話修改這份配置的設定：在 `X-OpenViking-Context` 請求頭裡用 JSON 物件傳入要修改的欄位，欄位名使用[配置參考](13-configuration.md#context-profile-settings)中的 API 名稱。例如：

```text
X-OpenViking-Context: {"recall":false,"max_tokens":800,"context_types":["memory"]}
```

- **能改什麼。** 除 `name` 和 `client_overrides` 以外的所有設定。請求頭沒有給出的欄位沿用配置中的值。工具許可權只能收窄：請求頭裡的 `disabled_tools` 會追加到配置已取消勾選的工具上，`gateway_tools` 只能關閉 OpenViking 工具、不能重新開啟，所以 `{"disabled_tools":[]}` 或 `{"gateway_tools":true}` 不會提供配置不提供的工具。
- **何時生效。** 與儲存配置的修改一樣，對話會沿用開始時的設定：只有對話第一個請求裡的請求頭決定設定。之後的請求頭仍會校驗，所以無效的請求頭，或開關關閉後的任何請求頭，仍會報錯。
- **錯誤。** 開關關閉時，帶這個請求頭的請求一律返回 403 `context_override_not_allowed`，而不是按已儲存的設定處理。開關開啟時，請求頭有下列情況之一會返回 400 `context_override_invalid`：
  - 不是 JSON 物件；
  - 出現未知欄位或 `name`、`client_overrides`；
  - 取值越界。
- **請求日誌。** [請求詳情](10-overview-and-requests.md#request-details)中列出客戶端在請求頭裡傳入了哪些欄位，只記名稱，不記取值。

這個開關預設開啟，所以持有使用這份配置的金鑰的人可以修改任意欄位，包括預算，也可以再排除更多工具。對 `default` 配置來說，這也包括所有[直接使用 OpenViking API 金鑰](09-gateway-keys.md#openviking-keys)的客戶端。需要鎖定的配置請關閉它。各客戶端如何傳送這個請求頭，見[覆蓋上下文配置](03-connect-clients.md#override-profile-settings)。

## 下一步 {#next-steps}

- [簽發一個閘道器金鑰](09-gateway-keys.md#issue-a-key)，讓它使用這份配置。
- 在[請求日誌](10-overview-and-requests.md#requests)中逐條檢視召回和儲存情況。
- 始終沒有補充記憶時，見[沒有補充記憶](12-troubleshooting.md#no-memory-is-added)。
- 在[OpenViking 閘道器的工作原理](01-how-it-works.md#what-happens-once-you-connect)中完整走一遍一輪對話。
