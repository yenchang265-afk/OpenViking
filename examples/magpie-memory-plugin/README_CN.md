# OpenViking for Magpie

一個外掛提供兩項可獨立控制的能力：

- **記憶**：為經過 Magpie 的模型請求召回 OpenViking 上下文，按需採集對話並提供記憶工具。
- **模型管理**：在 **Agents → OpenViking** 切換 OV/VikingBot 使用的模型，自動儲存配置、重啟並驗證生效。Query Planner 可通過外掛 Options 的 `queryMode` / `queryModel` 單獨指定模型，預設保留現有 Query 配置。

市場展示名稱為 **OpenViking**，統一 npm 包名為 `@openviking/magpie-plugin`。發現頁歸為「閘道器中介軟體」；已安裝頁可同時識別 Agent 與請求 Hook。沒有額外頁面或設定面板，不修改 Magpie 宿主。

## 功能開關與遷移

在 Magpie 的外掛 Options 中分別設定 `memoryEnabled`、`modelsEnabled`（均預設為 true）：

```json
{ "memoryEnabled": false, "modelsEnabled": true, "restartOnChange": true }
```

上例只啟用模型管理；記憶關閉時不會召回、採集或註冊記憶工具。`modelsEnabled: false` 暫停模型同步；需要恢復原模型時，先在 Agent 行斷開接入。現有記憶配置和憑據讀取規則保持相容，Root 憑據只用於模型管理。

從兩個外掛合併時，將原記憶外掛的啟用狀態遷為 `memoryEnabled`，將原模型外掛的狀態遷為 `modelsEnabled`，合併保留各自 Options。不要僅因為新外掛整體開啟，就把原先關閉的記憶功能開啟。

舊的 `@openviking/magpie-models-plugin` 已停止單獨打包。通用手動遷移方式：備份 Options，在舊模型 Agent 行斷開並等待恢復完成，移除兩個舊安裝項，安裝統一包並寫回功能開關和原選項，再重新選擇模型。不要同時保留新舊模型外掛，以免重複註冊 Agent。如採用原地遷移，需保留 Agent ID、安裝路徑、選擇檔案和恢復日誌，並核對遷移前後的 `ov.conf` 與 OV 例項未變化。

模型配置 API、Root 許可權、Bot 檢測、自動重啟和恢復限制見 [模型管理說明](models/README_CN.md)。模型管理不是長期記憶功能，不會自動啟用 Bot。

## 安裝

統一版本 0.2.0 尚未釋出；當前請按下文從原始碼安裝。釋出後可安裝：

```sh
magpie plugin add @openviking/magpie-plugin
```

按 Magpie 當前的工具命名規則，通過 npm 安裝時，工具名為
`magpie-plugin_status`、`magpie-plugin_find`、`magpie-plugin_read`、`magpie-plugin_ls` 和 `magpie-plugin_remember`。
本地目錄安裝的工具字首使用目錄名。

從原始碼安裝時，在 OpenViking 倉庫根目錄執行：

```sh
node examples/memory-plugin-shared/sync.mjs
magpie plugin add ./examples/magpie-memory-plugin
```

本地目錄安裝需要先生成共享模組。`npm pack` 會自動生成並打包這些模組。
按 npm 包名安裝需要對應版本已釋出；直接將整個 OpenViking 倉庫作為外掛安裝不會選中此子目錄。

需要支援非同步閘道器 Hook 和宿主 `origin` 分類的 Magpie，以及支援
`POST /api/v1/search/search` 的 `mode: "context"` 的 OV 服務。
`magpie-key` 分類需要 Magpie v0.1.2208 或更新版本，舊版本的未知來源會跳過召回。

## 配置

預設只讀 `~/.openviking/ovcli.conf`。可在 **Magpie 程序的環境變數** 中通過
`OPENVIKING_CLI_CONFIG_FILE` 指定其他路徑。遠端執行時讀取遠端機器上的檔案。
修改檔案後下一次操作生效；修改環境變數需要重啟 Magpie。

在現有配置的 `plugin` 下增加：

```json
{
  "magpie": {
    "enabled": true,
    "autoRecall": true,
    "autoCapture": true,
    "recallContextTimeoutMs": 2000,
    "recallMaxTokens": 1600,
    "recallPeerScope": "all",
    "mcpEnabled": false
  }
}
```

行為配置沿用共享外掛欄位名，`plugin.magpie` 覆蓋 `plugin` 的同名設定；
全域 `plugin.enabled: false` 同時關閉記憶功能、模型自動同步和自動重啟；顯式執行的恢復 CLI 仍可使用。連線讀取頂層的 `url`、`api_key`、
`account`、`user`、`actor_peer_id`、`timeout`（秒）、`extra_headers`（或 CLI 別名 `extra_header`），支援身份欄位的已有別名。
帳戶、使用者請求頭沿用共享客戶端的身份處理方式，需要與服務端認證模式匹配。
自定義請求頭不能覆蓋鑑權、身份或傳輸請求頭，包括 `X-API-Key`。
已有 LDAP 配置按 `auth_mode`、`ldap_username`（或 `user`）、`ldap_password` 構造 Basic 鑑權；
OIDC 配置使用 `oidc_token`（或 `api_key`）作為 Bearer Token。兩者由服務端解析身份，不斷言帳戶或使用者。
配置型別、別名、範圍和召回請求體複用已有共享模組；檔案讀取策略、宿主超時、工具預設關閉等適配放在 Magpie 自身目錄，不改變其他外掛。
Magpie 的檔案讀取策略排除環境變數和 workspace 層。
工具仍需 `plugin.magpie.mcpEnabled: true` 顯式開啟。採集預設開啟；宿主選項或客戶端配置中顯式設定的 `autoCapture: false` 仍然生效。優先順序為宿主選項、Magpie 專屬配置、共享配置。

Magpie 的“選項”支援 `autoRecall`、`autoCapture`、`mcpEnabled`、`recallMaxTokens`、
`recallContextTimeoutMs`、`captureWithoutSession`、`nativeAgents`，優先於本外掛的檔案行為配置；Hook 和工具使用同一套設定。
服務連線、憑據和身份仍只從檔案讀取。`gatewayTimeoutMs` 控制宿主 Hook 預算。
包內示例不會自動儲存；未填寫的欄位繼續沿用檔案設定或預設值。記憶工具預設關閉，設定 `mcpEnabled: true` 可開啟。自動採集預設開啟，無需額外配置；如需關閉，設定 `autoCapture: false`。

`captureWithoutSession` 是 Magpie 專屬的布林配置，預設 `false`。客戶端無法傳遞穩定會話 ID 時，
可在 Magpie“選項”中顯式開啟：

```json
{
  "autoCapture": true,
  "captureWithoutSession": true
}
```

也可在 `ovcli.conf` 的 `plugin.magpie` 或共享 `plugin` 中設定，優先順序仍為宿主選項、專屬配置、共享配置。
有真實會話 ID 時優先使用真實 ID。派生 ID 僅用於採集，無宿主會話時召回仍然無狀態。
派生輸入為 Agent、工作目錄、協議和經過現有采集清洗/過濾的首條使用者訊息；切換模型不會改變 ID，
OV 連線和憑據仍按現有規則隔離。

同一客戶端作用域內，相同開場的獨立對話可能合併。如果兩段歷史出現分歧，採集會跳過與已寫入歷史
衝突的快照。改寫或刪除開場訊息可能拆分會話，或因歷史無法識別而跳過採集。開啟後請新建對話，
不回填未知的已有歷史。
`autoCapture: false` 仍關閉所有自動採集。通過檔案配置且無宿主覆蓋時，關閉本開關會暫停派生會話的
待同步佇列，重新開啟後可恢復。與 `autoCapture` 一樣，已入隊快照保留入隊時的宿主選項覆蓋。

不會修改檔案、合併環境變數中的憑據，或回退讀取 `ov.conf`、Root Key、Gateway Token。
配置缺失、損壞或服務不可用時，召回跳過，模型請求繼續；不會沿用舊配置。

在檔案中設定 `plugin.magpie.bypassSession: true`，或通過 `bypassSessionPatterns`
匹配 Magpie 會話 ID、工作目錄，可跳過該會話的自動召回和採集。
已有待同步快照會暫停投遞，取消 bypass 後可繼續恢復；worker 在追加和 commit 前重新檢查，
無法撤銷已在途的操作。顯式記憶工具仍由 `mcpEnabled` 單獨控制。

## 自動召回

- 首輪使用者訊息同時讀取當前認證使用者的 `viking://~/memories/profile.md`，避免職業、郵箱等穩定資料依賴語義檢索排名。
  資料讀取與檢索在召回超時預算內並行執行；任一路失敗時仍可使用另一路結果。
  資料遵守 `profileTokenBudget`，且最多佔 `recallMaxTokens` 的一半，使用共享的中日韓字元 token 估算器；
  資料與檢索結果合計不超過 `recallMaxTokens`，與首輪決策一起持久化；重試和後續輪次回放原始快照。
- 僅處理宿主確認為本機的 `local`、`magpie-key` 請求。沒有會話 ID 時，新使用者請求使用無狀態召回：不讀寫持久化召回帳本、不重放 Profile 快照；除非顯式設定 `captureWithoutSession: true`，否則不採集對話。重複請求可能獲得不同的召回結果。
  開啟採集但未開啟雜湊相容時，首次符合條件卻缺少會話 ID 的使用者請求，會在 Magpie 外掛宿主日誌中輸出
  `OpenViking capture: no-session`，建議客戶端傳遞穩定的會話 ID 請求頭，或瞭解會話誤合併限制後顯式開啟 `captureWithoutSession`。
  每個外掛宿主程序只提示一次，不含對話正文或憑據，也不覆蓋召回狀態。
  當前 Magpie 會忽略自定義 `report()` 狀態碼，獨立的 UI 採集狀態仍需宿主支援。
  原生外掛接管、關閉、bypass、輔助請求不會觸發此提示。
  共享閘道器 Key、轉發請求或身份缺失時跳過，始終使用檔案中配置的 OV 身份。
- 只有新的文本使用者訊息觸發檢索。工具續輪只回放已有記憶；重試複用首次決策，
  包括無結果和失敗的決策。同樣的問題出現在後續新輪次時仍可重新檢索。
- 記憶附加到對應的**使用者訊息**，不修改系統指令。先持久化每條訊息字首對應的注入決策，
  後續請求在原位置恢復同樣的內容，保持舊上下文穩定。
- 保留 Chat Completions、Anthropic Messages、Gemini 的系統指令、圖片、工具、模型和流式設定。
  Responses 必須使用 `store: false` 並回傳完整 `input`；服務商儲存歷史、後臺請求和
  `item_reference` 均跳過。
- 狀態按 OV 連線身份、peer 範圍、配置檔案位置，以及 Magpie Agent、會話、workspace、
  協議和模型隔離。憑據輪換不復用舊狀態。分支和歷史匹配使用完整字首雜湊，
  不根據相同文本猜測歸屬。未知的截斷或壓縮歷史跳過增強；單條新使用者訊息可建立新字首。
- 根據已知 OV 上下文塊或顯式 `nativeAgents` 配置避讓自動增強；這不是外掛安裝檢測，不能保證所有場景零重複。
  Magpie 自身跳過內部標題/分類請求；外掛也跳過明確標記的輔助、壓縮、標題和子 Agent 請求。
- `autoRecall: false` 關閉新檢索，但仍回放已知歷史；外掛整體關閉則停止兩者。
  查詢過濾、召回引數、預算和結果相關性使用共享模組。
- 預設 2000ms 檢索預算，可在 Magpie“選項”或 `plugin.magpie` 中配置
  `recallContextTimeoutMs`；已有顯式配置繼續生效。實際 HTTP 超時還受客戶端 `timeout`、
  9000ms 上限及宿主預算限制：從宿主預算扣除已耗費的準備時間，並預留 200ms 用於結果組裝、
  狀態讀寫和序列化。檢索與 Profile 共用內部截止訊號，一路超時仍可使用另一路已完成的結果。
  剩餘不足 100ms 時不再發起 HTTP 請求；宿主取消時仍放棄本次注入。
  宿主沒有提供整個 Hook 鏈的剩餘截止時間，因此預留時間不能保證避開更早的外部取消。
  Actor 範圍需要明確填寫 `actor_peer_id`，缺失時跳過。

連線託管或遠端服務時，請在 Magpie 的“選項”中同時儲存兩個預算（合併到已有選項）：

```json
{
  "recallContextTimeoutMs": 2000,
  "gatewayTimeoutMs": 3000
}
```

包內選項示例包含這組值，但升級不會重寫已儲存的選項。未設定 `gatewayTimeoutMs` 時，
Magpie 仍預設使用 1000ms 的宿主預算，外掛會自動縮短 HTTP 等待以適配該預算。
已有安裝如需使用完整 2000ms 檢索預算，仍須顯式提高宿主預算。宿主預算應高於檢索預算，
為配置和狀態讀寫留餘量（Magpie 允許的上限為 10000ms）。如需繼續增加檢索預算，
請同步調整兩個值，並確保 `ovcli.conf` 頂層的 `timeout`（秒）足夠。召回失敗仍會放行模型請求。

### 本機回放狀態

預設儲存在 `~/.openviking/magpie/recall/`，可用 `plugin.magpie.dataDir` 修改父目錄。
檔案僅儲存訊息錨點雜湊、注入的記憶原文及空結果/失敗狀態，不儲存原始憑據或客戶端完整對話。
記憶原文可能含敏感內容；目錄許可權為 0700，檔案為 0600。通過會話鎖和原子替換支援多個宿主程序，
宿主意外退出留下的鎖在一分鐘後可回收。

本版本不自動刪除回放檔案。活躍會話應保留狀態；刪除、損壞或無法匹配歷史時，已有對話跳過增強，
新建對話後可重新建立狀態。帶簽名推理的恢復依賴完整歷史及其回放狀態，尚未驗證真實模型服務的簽名行為。
單會話狀態上限 1 MiB，請求 JSON 上限 2 MiB、最多 2,000 條訊息；超限或狀態不可用時放行原請求。
診斷只記錄固定狀態和位元組數，不記錄憑據或記憶正文。

外掛直接連線 OV 的普通 REST/MCP 服務，**不要求 OV 開啟閘道器**。
自動召回本身不建立 OV Session。

Anthropic 協議內容塊的快取註解不參與召回錨點計算；原始請求欄位和工具輸入中的業務資料保持不變。

## 自動採集與原生外掛避讓

有可靠會話 ID 的請求預設開啟採集。在 `ovcli.conf` 中設定 `plugin.magpie.autoCapture: false`，或在 Magpie 的“選項”中儲存
`"autoCapture": false` 可關閉。已有顯式關閉設定繼續生效；未配置該項的安裝或升級將開啟採集，把完整對話提交到配置的 OpenViking 服務。完整對話先寫入本地佇列，再由獨立後臺任務增量寫入按連線、Agent、
會話、workspace、協議隔離的 OV Session；不儲存系統指令、注入記憶、宿主提醒和私有推理。
啟用後應新建會話：首輪會繫結當前連線和第一條使用者訊息，且該使用者訊息之前不能存在可採集的助手或工具內容。未知的已有歷史，包括切換憑據後的舊對話，
會跳過採集，避免把之前的私有內容複製到新身份。
工具呼叫和結果成對儲存；未完成的工具續輪、失敗和截斷的回覆不作為完整輪次入庫。
若完成回呼丟失，下一條使用者請求攜帶的完整歷史可以補齊此前已經結束的對話。
已知失敗或截斷的輪次會以摘要標記持久化，後續歷史不能將其重新補採；成功重試的完成回呼可以解除拒絕狀態。
工具續輪不作為失敗處理。已知標題、記憶壓縮交換在補採、最終快照和召回歷史錨點中統一排除，原始訊息保持不變。
拒絕狀態的修訂號會使已被 worker 讀取的舊快照失效，舊 worker 也不會刪除隨後釋出的成功重試快照。

完整輪次寫入後，由後臺任務呼叫普通 OV Session 的 `commit` 介面，`keep_recent_count` 為零。
關閉該 Session 自身的自動提交，避免兩個提交方競爭，也不依賴服務端空閒排程器或 OV 閘道器。
重複回呼不會再次 commit；返回結果代表歸檔並提交了提取任務，不代表已經生成新記憶。
若 commit 響應丟失，先核對會話後設資料，再繼續追加；無法確認時暫停佇列，不重複請求提取。

自動召回或採集前，Magpie 僅將系統、使用者文本中獨立成行、完整閉合且內容非空的
`<openviking-context>`、`<relevant-memory>` 或 `<relevant-memories>` 塊作為避讓訊號。
Markdown 圍欄程式碼、引用塊、縮排程式碼、行內提及、未閉合標籤，以及助手、工具和非文本欄位均不參與判定。
舊版 `[OpenViking memory context]` 單獨出現時不再自動觸發避讓。

這只是訊息內容啟發式判斷，**不能檢測外掛安裝，也不能證明原生採集正在執行**。
未加引用、格式與真實注入完全相同的示例仍無法可靠區分；已知由原生外掛管理的 Agent 應顯式配置 `nativeAgents`。
命中後，該連線和會話同時跳過自動召回與採集，並立即清理待同步原文，無需等待 worker；判定持久化，避免標記從後續歷史消失後再次啟用。
worker 在追加訊息或 commit 前重新讀取配置，檢查連線身份、採集開關和歸屬；本地清理無法撤銷已經在途的 HTTP 操作或已送達的記錄。
已有歸屬記錄會保留；移除原生外掛或糾正歷史誤判後應新建會話。顯式工具不受自動能力讓出的影響。

已知的原生 OpenViking 記憶壓縮和 Claude Code 會話標題生成內部請求，即使沒有注入標記，也會跳過自動召回和採集。這是基於已知提示詞結構的兜底，無法完整識別所有輔助請求。對於已安裝原生 OV 外掛的 Agent，應配置 `nativeAgents`，一併讓出未攜帶標記的內部請求。

遠端閘道器看不到客戶端安裝列表；僅採集、不注入標記的原生外掛也無法靠訊息識別。
這類 Agent 可在選項中設定 `"nativeAgents": ["pi", "codex", "claude"]`，或填寫
`plugin.magpie.nativeAgents`，明確讓出兩項自動能力。名稱應與 Magpie 上報的 Agent ID 一致。
不會根據無關機器上的檔名推斷外掛正在執行。

採集狀態在 `<dataDir>/capture/`，目錄許可權 0700、檔案 0600。**待同步檔案含對話和工具輸出**，
不含連線憑據。單會話最多 32 個快照、單快照 3 MiB、最多 2,000 條訊息。
同步成功後刪除快照，保留進度摘要和歸屬判定。後臺任務有重試預算，後續開啟採集的請求也會觸發恢復。
關閉檔案中的採集設定會暫停相應佇列；更換身份不會將舊佇列傳送給新使用者。

通過穩定字首 ID、持久化進度和程序鎖防止重試或併發重複寫入。OV 的 `source_message_ids` 不等於冪等鍵：
寫入響應丟失時核對當前訊息和最多 32 份歸檔中的來源 ID；無法確認時保留佇列，不盲目重發。
已同步歷史被改寫時暫停該會話，避免把舊對話重複複製；可新建會話繼續。
這些保守處理可能延遲或跳過採集。宿主在完成回呼前崩潰、且再無完整歷史請求時，無法僅靠盡力通知恢復尾訊息。

## 可選工具

工具預設關閉。設定 `plugin.magpie.mcpEnabled: true`，或在 Magpie 選項中儲存 `mcpEnabled: true`，然後在 Magpie Library/MCP 路由
中為需要的 Agent 開啟外掛服務。也可通過 Magpie 的 `/mcp/magpie/tools` 訪問。

提供 `status`、`find`、`rule_search`、`read`、`ls`、`remember`，實際名稱由 Magpie 加外掛字首。
`status` 檢查鑑權後的連線；`read` 最多讀取 200 行，`ls` 最多返回 100 項。

`rule_search` 接收 `task_context` 與可選的 `rule_probability_threshold`（預設 `0.65`），
通過 `POST /api/v1/rules/search` 返回完整 Rule。執行受約束的操作或回覆前，
逐條檢查條件、例外和正文，遵守所有適用規則。npm 安裝時工具名為 `magpie-plugin_rule_search`。

**工具回呼不提供呼叫者的認證身份。開啟工具意味著將當前檔案的 OV 身份授權給能呼叫
該 MCP 服務的呼叫者。** 共享閘道器應保持關閉，除非允許的工具呼叫者都應擁有該訪問許可權。
工具引數不能更換帳戶或憑據，資源許可權仍由 OV 服務端控制。關閉後工具仍會列出，但拒絕呼叫，
`status` 返回 `disabled`。

`remember` 僅在使用者明確要求記住內容時提交文本，建立 Session 並觸發非同步提取。
配置了 `actor_peer_id` 時，也將其寫入訊息的 `peer_id`，保留專案記憶的歸屬。
返回任務 ID 不代表記憶已生成。寫入不自動重試；中斷可能留下未完成的 Session，
結果不明確時應先檢查 OV 再決定是否重試。

工具錯誤保留脫敏的 HTTP 狀態、錯誤類別和追蹤 ID，區分不存在、衝突、限流、超時和取消。
自動召回仍在錯誤時放行原請求，診斷僅記錄固定狀態。

## 市場資訊

[marketplace.json](marketplace.json) 提供待提交的 **OpenViking** 市場條目，包含官方圖示和中英文描述。
`kind: "middleware"` 沿用閘道器記憶外掛的市場分類；外掛實際執行入口仍是非同步 `magpie.hooks`。
`package.json` 的 `magpie.icon` 使用同一圖示，供 npm 搜尋結果和已安裝列表展示。

npm 釋出不會自動加入推薦列表。釋出後，需要將 `plugins` 中的條目提交到
[Magpie 社群登錄檔](https://github.com/magpie-community/plugins/blob/main/registry.json)。
條目不宣告由 Magpie 社群維護。

開發、測試與完整介面說明見 [English README](README.md)。
