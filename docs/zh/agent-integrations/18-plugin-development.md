# Hook + MCP Agent 外掛開發與維護規範

本文規定如何新增和維護通過生命週期 hook 自動讀寫記憶、通過 MCP 提供工具的 OpenViking Agent 外掛，涵蓋模組職責、協議、狀態、安裝、測試和釋出。宿主是指承載 Agent 的客戶端或執行時，程式碼中也稱 harness。

新增宿主時，應主要實現事件、訊息格式、上下文注入和安裝方式的差異。配置解析、鑑權、召回、捕獲過濾、網路請求和離線重試應複用共享實現。Claude Code、Codex 和其他外掛可作為參考，但仍需核對目標宿主的實際契約。MCP-only 或原生工具整合可採用相關規則，不必補齊不適用的 hook 能力。

## 使用 VibeCoding 開發外掛

使用 VibeCoding 或其他 AI 輔助程式設計方式新增、修復、重構 Agent 外掛時，**必須讓 coding agent 在修改前完整閱讀並遵循本文**。將文件路徑和具體任務一起交給 Agent，要求它先核實宿主契約，再實施，並按驗收檢查單報告結果。生成了程式碼或測試通過，都不能替代對協議、恢復和安裝產物的驗證。

優先參考 [Claude Code](./02-claude-code.md) 和 [Codex](./04-codex.md) 外掛，瞭解共享能力如何接入原生 hook 與 MCP；配置檔案式宿主可參考 `agent-hook-plugin`，常駐擴充可參考 OpenCode、DSH 和其他外掛。參考其職責劃分和已驗證行為，不要讓 Agent 整目錄複製，也不要要求所有宿主照搬同一套事件。

下面的提示詞可以直接交給 coding agent；把最後一行替換為具體任務：

```text
Before changing any OpenViking agent plugin, read and follow
docs/en/agent-integrations/18-plugin-development.md
(Chinese: docs/zh/agent-integrations/18-plugin-development.md).

Inspect examples/memory-plugin-shared/lib/ and the Claude Code and Codex
plugins. Also inspect agent-hook-plugin, OpenCode, DSH, or another existing
integration when its host model matches the task. Verify the target host's
events, payloads, output schema, time limits, and installation contract.

Keep shared behavior in the shared modules and host differences in the
adapter. Do not copy a whole plugin or edit generated shared files. Cover
configuration, hook/MCP identity, capture acknowledgements, commit recovery,
installation, versioning, and bilingual documentation as applicable.

Before finishing, use the guide's acceptance checklist and report what was
changed, what was verified, and any remaining limitations.

Task: <describe the plugin addition, fix, or maintenance change>
```

## 1. 設計原則

共享庫存在，並不代表各外掛真正共享行為。配置只有在共同的執行鏈上解析和消費，才能保持一致；各宿主分別解釋開關，會導致不同拼寫、不同預設值，甚至配置能讀到卻不起作用。分發檔案也應從依賴關係推導，避免原始碼通過測試，安裝後卻缺少 import 所需檔案。

因此，本規範要求：

1. **同一行為有一個權威實現**。共享模組擁有規則，介面卡提供宿主事實；不允許在介面卡中複製一套“略有不同”的規則。
2. **統一必須發生在執行鏈上**。呼叫 `buildPluginConfig()`、`buildRecallBlockDetailed()` 或共享傳送器，才構成複用。複製檔案、匯出同名函式、約定大家保持一致，都不足以防止分叉。
3. **能推導的清單不手寫**。配置鍵、診斷鍵、workspace 對映來自 schema；執行時檔案集合來自 import 閉包；安裝包必需檔案來自入口和 manifest。
4. **保留真實差異**。Claude Code 的子代理事件、Codex 的退出補償、ZCode 的嚴格輸出格式，各有明確原因。統一它們的公共能力，不強迫它們擁有相同的生命週期。
5. **交付方式決定生成時機**。使用者直接載入倉庫目錄時，目錄必須已經完整；使用者安裝構建產物時，在打包前生成依賴。不為減少 diff 破壞安裝，也不為方便開發提交不需要的生成物。
6. **每次抽象都減少維護點**。新介面應讓後續修復少改一個地方。若只是多了一層轉發、更多布林引數或第二套配置表，應重新考慮。

這些原則與倉庫[貢獻指南的職責與設計要求](https://github.com/volcengine/OpenViking/blob/main/CONTRIBUTING_CN.md#職責與設計)一致。衡量改動是否合理，要看一個新維護者能否沿呼叫關係找到規則、解釋失敗、完成交付。程式碼行數和檔案數量只是結果。

## 2. 接入前先確定宿主契約

開發前必須完成以下接入記錄，放在外掛 README 或必要的 DESIGN 文件中。記錄應引用宿主文件、對應版本原始碼或實測結果，不能用另一款 Agent 的行為補全空白。

| 要確認的內容 | 必須寫清的問題 |
| --- | --- |
| 版本與平臺 | 最低宿主版本、Node.js 版本、已驗證作業系統；較舊版本如何降級 |
| 安裝方式 | 原生外掛、marketplace、配置檔案 hook 或 npm 擴充；宿主實際載入哪些目錄 |
| 事件 | 啟動、提交使用者輸入、輪次結束、壓縮前、會話結束、子代理事件分別是否存在 |
| 輸入 | stdin 是 JSON 還是其他格式；session、cwd、transcript、turn 的欄位名及缺失條件 |
| 輸出 | 注入欄位、允許/拒絕欄位、空結果形式、退出碼；未知欄位是否導致整份輸出被丟棄 |
| 時間限制 | 單位、最大值、宿主是否截斷配置值；超時後殺單程序還是整個程序組 |
| 訊息來源 | transcript 或 rollout 的格式、寫盤時機、穩定訊息 ID、工具呼叫與結果如何關聯 |
| 程序模型 | 是否複用 hook 程序；後臺程序能否存活；多個視窗和會話是否併發 |
| MCP | 配置格式、stdio 支援、根路徑變數、啟動 cwd、環境變數繼承、工具名稱空間 |
| 恢復 | resume、clear、異常退出、壓縮和 transcript 截短後，哪些身份與狀態仍然有效 |

每項能力標記為“已驗證”“有降級實現”或“不支援”，並說明驗證版本。不能把 `Stop` 寫成“會話結束”，也不能註冊一個宿主不會觸發的事件後宣稱能力完整。最低服務端版本由實際使用的 API 和 URI 能力決定；例如當前共享召回要求服務端支援 `viking://~`，區域性的舊介面回退不代表任意舊版本都相容。

### 2.1 選擇最小的接入形態

| 宿主條件 | 應採用的形態 | 參考 |
| --- | --- | --- |
| 通過配置檔案安裝 hook 和 MCP；公共排程足夠表達生命週期 | 在 `agent-hook-plugin/hosts/` 增加介面卡及宿主配置 | [agent-hook-plugin](https://github.com/volcengine/OpenViking/blob/main/examples/agent-hook-plugin/README.md) |
| 原生外掛要求獨立 manifest、目錄和生命週期入口 | 獨立外掛目錄，入口呼叫共享執行時 | [Claude Code](https://github.com/volcengine/OpenViking/blob/main/examples/claude-code-memory-plugin/README.md)、[Codex](https://github.com/volcengine/OpenViking/blob/main/examples/codex-memory-plugin/README.md) |
| 以宿主 SDK 回呼執行，需要常駐狀態或 dispose/idle 回呼 | 使用宿主擴充包，複用共享能力，明確自己的會話排程 | [OpenCode](https://github.com/volcengine/OpenViking/blob/main/examples/opencode-plugin/README.md)、[DSH](https://github.com/volcengine/OpenViking/blob/main/examples/dsh-memory-plugin/README.md) |
| 宿主能註冊原生工具，但自身沒有 MCP 支援 | 使用官方 MCP 客戶端，把服務端的 `tools/list` 註冊成加 `openviking_` 字首的宿主原生工具；不得自行維護工具目錄 | [pi](https://github.com/volcengine/OpenViking/blob/main/examples/pi-coding-agent-extension/README.md) |
| 只有 MCP，沒有自動注入或完整會話記錄 | 交付 MCP-only 整合，明確能力範圍 | [Agent Plugins](https://github.com/volcengine/OpenViking/blob/main/agent-plugins/README.md) |

只因新增宿主名稱，不應複製 Claude Code 或 Codex 的整個目錄。反過來，如果宿主有獨立的會話狀態機，也不應不斷往公共 dispatcher 加 `isFoo`、`specialStop` 一類開關來容納它。

## 3. 模組職責與依賴方向

```text
宿主事件 / transcript                    宿主 MCP 客戶端
          ↓                                     ↓ stdio
事件、訊息、輸出介面卡                    薄 MCP 入口
          ↓                                     ↓
runHookStage + 宿主生命週期排程           buildMcpProxyConfig
          ↓                              createOpenVikingMcpProxy
共享 recall / capture / session 能力             ↓
          ↓ createOvHttp                   共享 MCP transport
          └────────── buildOvHeaders ────────────┘
                               ↓
                         OpenViking Server

buildPluginConfig / credentials 為兩條鏈提供配置和身份
sync / install / pack 負責把這張依賴圖完整交付到機器上
```

共享能力的原始檔位於 [`examples/memory-plugin-shared/lib/`](https://github.com/volcengine/OpenViking/tree/main/examples/memory-plugin-shared/lib/)。下表是定位規則的入口，不是需要在每個外掛重建的目錄模板。

| 責任 | 權威模組 | 宿主可以提供的差異 |
| --- | --- | --- |
| 配置宣告、預設值、別名、範圍 | [config-schema.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/lib/config-schema.mjs) | 有證據的宿主預設值差異，仍在 schema 宣告 |
| 分層配置、完整配置物件 | [plugin-config.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/lib/plugin-config.mjs) | harness ID、manifest、日誌檔名、宿主原生引數 |
| 憑據和鑑權模式 | [credentials.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/lib/credentials.mjs) | 已有相容要求；不得再寫 fallback 鏈 |
| workspace、peer 身份 | [workspace-peer.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/lib/workspace-peer.mjs)、[workspace-identity.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/lib/workspace-identity.mjs) | 當前會話的真實 cwd、宿主明確傳入的 peer |
| hook 初始化、bypass、單次輸出 | [agent-hook-runtime.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/lib/agent-hook-runtime.mjs) | 輸入讀取、session ID 解析、啟用謂詞、輸出 envelope |
| HTTP 頭、超時、錯誤結果 | [ov-http.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/lib/ov-http.mjs) | 請求路徑、正文、呼叫預算、當前 actor peer |
| 召回和上下文構建 | [recall-core.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/lib/recall-core.mjs)、[profile-inject.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/lib/profile-inject.mjs) | 查詢、會話身份、本地壓縮器回呼、宿主顯示 |
| 訊息清洗、角色和結構化內容 | [capture-utils.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/lib/capture-utils.mjs)、[input-filters.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/lib/input-filters.mjs) | transcript 格式解碼、原生工具事件歸一化 |
| 批次傳送、離線重放、重試分類 | [batch-send.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/lib/batch-send.mjs)、[pending-queue.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/lib/pending-queue.mjs)、[retryable.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/lib/retryable.mjs) | 何時呼叫、傳送成功後如何推進宿主游標 |
| 後臺寫入 | [async-writer.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/lib/async-writer.mjs) | 宿主允許的 detach 時機和恢復措施 |
| MCP 配置與協議 | [mcp-proxy-config.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/lib/mcp-proxy-config.mjs)、[mcp-proxy-core.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/lib/mcp-proxy-core.mjs) | 配置投影、日誌工廠、確有必要的本地工具 |
| 虛擬 URI 檢查、診斷 | [uri-guard.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/lib/uri-guard.mjs)、[doctor-core.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/lib/doctor-core.mjs) | 工具名、拒絕與提示 envelope、宿主安裝與狀態檢查 |

依賴必須從宿主介面卡指向共享能力。共享能力不能 import 某個宿主目錄；需要宿主動作時，由呼叫者傳入小而明確的回呼。不要為一次檔案讀取引入通用外掛容器、服務定位器或繼承體系。共享模組也不能反向依賴安裝器、測試程式碼或使用者介面。

### 3.1 介面卡應該有多薄

“薄”指它只擁有宿主差異，不設行數上限。例如 [cc-transcript.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/claude-code-memory-plugin/scripts/cc-transcript.mjs) 負責 Claude 訊息塊和巢狀 `tool_result` 的轉換；[Codex capture-utils.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/codex-memory-plugin/scripts/capture-utils.mjs) 還要展開巢狀工具活動並消除同一呼叫的重複表示，因此可以更長。兩者都應把通用內容處理交給共享程式碼。

新增薄宿主時，優先使用現有 [`HOSTS`](https://github.com/volcengine/OpenViking/blob/main/examples/agent-hook-plugin/hosts/index.mjs) 和 dispatcher 支援的 `stages`、`envelope`、`prompt`、`normalizeInput`、`capture`、`guard`。需要新增介面時，先說明哪一個宿主事實無法表達，再決定是否擴充；不要預先設計覆蓋所有未來 Agent 的介面卡 DSL。

現有 `hosts/cursor.mjs`、`hosts/trae.mjs` 和 `hosts/zcode.mjs` 表明，事件對映適合資料，訊息轉換適合純函式，非同步捕獲適合顯式回呼。不要把這三種東西壓進一個包含網路訪問的“配置物件生成器”。

## 4. 配置、憑據和身份

### 4.1 一次宣告，統一解析

新行為配置必須先在 `config-schema.mjs` 宣告規範名稱、型別、預設值、範圍、所屬能力，以及適用的環境變數、舊別名、workspace 鍵。解析入口使用 `buildPluginConfig(harness, options)`；介面卡只投影宿主需要的欄位。禁止新增外掛私有的 `config.json` 來重複儲存共享預設值，也禁止另寫 doctor 已知鍵表或 workspace 鍵表。

普通行為配置從高到低按以下順序解析：

1. `OPENVIKING_*` 環境變數。
2. 本機 workspace registry。
3. workspace 的 `.openviking/config.local.json`。
4. workspace 的 `.openviking/config.json`。
5. `ovcli.conf` 的 `plugin.<harness>`。
6. `ovcli.conf` 的 `plugin`。
7. 舊 `ov.conf` 中對應宿主的配置段。
8. schema 預設值。

宿主 SDK 直接提供引數時，通過共享 builder 的顯式參數列達，記錄優先順序。現有 DSH 的宿主配置參與相容層，`hostInput` 還能固定連線或 peer；這些有具體含義的入口，不能被解釋為介面卡可以任意覆蓋最終配置。

配置示例只放必要值。例如下面的 `ovcli.conf` 片段為共享 resolver 提供召回預設值，並對 Codex 關閉自動捕獲；環境變數和 workspace 等更高優先順序配置仍可覆蓋：

```json
{
  "plugin": {
    "autoRecall": true,
    "codex": {
      "autoCapture": false
    }
  }
}
```

新增宿主應在 `HARNESS_KEYS` 註冊規範 ID，並驗證連字元與下劃線別名是否按現有約定解析。規範名稱與舊別名同時出現時，由共享 resolver 決定結果；同一層規範名稱優先。不要在介面卡裡再做一輪互相沖突的別名轉換。

必須區分“未設定”“顯式設定為 false”和“最終值等於預設值”。schema 中 `sendOnlyWhenConfigured` 控制的欄位，只有實際配置後才傳送，避免客戶端預設值覆蓋服務端預設值。不要用 `value || default` 處理允許 `false`、`0` 或空字串的欄位；是否允許這些值由欄位語義決定。

開關必須控制對應的真實行為：關閉 recall 後不發起自動召回，關閉 capture 後不新增本會話的自動捕獲和由它觸發的提交。歷史 pending 的恢復是否繼續，要單獨定義並驗證，不能混為“新採集”。共享能力中的 `isRecallEnabled()`、`isCaptureEnabled()` 是最終保護；介面卡可以提前退出，但不能成為唯一檢查點。`mcpEnabled` 等配置只有宿主真正消費後，才可以在該宿主文件中宣稱支援。

### 4.2 憑據不是普通 workspace 配置

連線和身份必須走 `credentials.mjs` 的 `resolveConnection()`，`buildPluginConfig()` 就是呼叫它。`OPENVIKING_CREDENTIAL_SOURCE` 的 `auto`、`cli`、`env` 控制憑據來源，不能簡單套用行為配置優先順序。MCP proxy 匯出 `readProxyConfig(env)`，經與 hook 相同的 loader 解析，再用 `toMcpProxyConfig()` 對映，不手工挑欄位，也不直接呼叫 `credentials.mjs`。宿主若只把白名單裡的環境變數交給 MCP 程序，白名單必須覆蓋 `MCP_PROXY_ENV_VARS`；宿主若給的是封閉環境，就用 `forwardConnectionEnv()` 轉發解析好的連線。新 proxy 必須加入 `mcp-hook-parity.test.mjs`，缺行時該測試會失敗。

workspace 檔案不得包含 URL、API key、使用者憑據等禁止欄位，也不做環境變數插值。規則由 [`workspace-config.mjs`](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/lib/workspace-config.mjs) 執行，不在每個宿主增加自己的白名單。安裝器不得把解析後的 API key 固化到 `.mcp.json`，也不得替換使用者已選擇的雲端連線。

請求頭由 `buildOvHeaders()` 構造：API key 使用 `Authorization: Bearer`，不再另發 `X-API-Key`；只有解析結果 `sendIdentityHeaders` 為真時才傳送 account/user 頭。保留 `User-Agent` 和錯誤中的 `traceId`，便於確認實際執行版本和追蹤請求。不要在健康檢查、狀態列或診斷探針裡另寫鑑權。

診斷中的 `credentialSource` 表示憑據解析模式，`apiKeySource` 表示 key 的實際來源；兩者不能混用。原始碼中存在為舊安裝保留的 `rootKeyFallback`，新宿主不得因為參考外掛啟用了它，就無條件複製這個選項。

### 4.3 會話身份與 peer 分開處理

原生 session ID 標識一次會話，peer 標識專案記憶歸屬，二者不能互換。寫入使用穩定的宿主 session ID 和明確的宿主字首；多個視窗、兩個相同 cwd 的會話、主代理和子代理不能意外共用寫游標。字首和現有會話 ID 演算法屬於資料相容約定，改名時必須說明舊狀態如何繼續讀取。

peer 解析使用共享實現。現狀預設從 Git 身份推導，普通非 Git 目錄不自動分配 peer；標記檔案可顯式指定。worktree、子目錄和 fork 的行為見[共享庫說明](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/README.md#workspace-peers)。hook 必須以 payload 中的真實 cwd 重新解析 workspace 配置，不能把外掛安裝目錄當作專案。

長期執行的 MCP proxy 不能從啟動 cwd 推導當前專案。必須使用 `resolveMcpActorPeerId()`：預設寬範圍讀取不發 actor peer 頭，actor 範圍需要顯式 peer。現有共享實現在缺少顯式 peer 時發出警告並退回寬範圍，文件必須如實說明。peer 是已認證使用者內部的記憶歸屬和檢索範圍，不能把它宣稱為不同使用者之間的授權隔離。

## 5. Hook 生命週期與可靠寫入

### 5.1 通用階段和宿主事件的對應關係

| 階段 | 通用責任 | Claude Code 現狀 | Codex 現狀 |
| --- | --- | --- | --- |
| 會話啟動 | profile 注入、必要的恢復工作 | `SessionStart` | `SessionStart`；區分 startup、clear、resume |
| 使用者提交 | 過濾查詢、召回、注入上下文 | `UserPromptSubmit` | `UserPromptSubmit` |
| 輪次結束 | 從可靠來源補齊新訊息，儲存進度 | `Stop`；另有閾值提交 | `Stop`；通常追加，不等同會話結束 |
| 壓縮前 | 確認壓縮前訊息已寫入，再執行相應提交 | `PreCompact` 提交已有訊息；本入口不補採 transcript | `PreCompact` 補齊 transcript 後提交 |
| 會話結束 | 完成尚未完成的寫入與提交 | `SessionEnd` 提交已有訊息；本入口不補採 transcript | `SessionEnd` 後臺補齊並提交，保留啟動補償 |
| 子代理 | 保留身份和父子關係，避免重複 | `SubagentStart`、`SubagentStop` | 當前 hook manifest 沒有這兩個事件 |
| 本地工具檢查 | 檔案工具的路徑是虛擬 URI 時拒絕；shell 命令帶虛擬 URI 時附加提示 | `PreToolUse` URI guard，匹配 Read、Glob、Grep、Edit、Write、Bash | `PreToolUse` URI guard 只匹配 Bash，只附加提示；檔案編輯走 `apply_patch`，沒有路徑引數 |

以兩份 [Claude Code hooks.json](https://github.com/volcengine/OpenViking/blob/main/examples/claude-code-memory-plugin/hooks/hooks.json) 和 [Codex hooks.json](https://github.com/volcengine/OpenViking/blob/main/examples/codex-memory-plugin/hooks/hooks.json) 為事件註冊依據。相同事件名稱不保證 payload 或輸出格式相同。沒有結束事件的宿主必須選擇並說明替代提交點，例如 ZCode 在 Stop 提交；不能假裝存在一個永遠不會執行的 SessionEnd。

### 5.2 Hook 入口的固定職責

入口使用 `runHookStage()` 處理 stdin、按會話 cwd 過載配置、啟用和 bypass 判斷，並保證只輸出一次。宿主特有 session 欄位通過 resolver 傳入，不能為相容一個欄位名而關閉 bypass。輸出必須嚴格符合當前事件的宿主協議：`decision: "approve"` 不是通用格式，Cursor 的 `additional_context` 與其他宿主的 `hookSpecificOutput.additionalContext` 也不能混用。

stdout 只承載宿主約定的結果，日誌寫 stderr 或共享日誌檔案。無結果、停用、配置不可用、網路失敗時，都應產生該事件合法的空結果，避免讓記憶服務故障阻斷使用者正常互動。URI guard 的明確拒絕則應保留拒絕語義，不能被統一異常處理改成允許。

不要在普通模組 import 時讀 stdin、啟動子程序、聯網或退出程序。這些副作用屬於入口或顯式呼叫的函式。共享函式不能為了方便呼叫者直接 `process.exit()`；可複用入口需要可測試的主函式和明確的啟動條件。

### 5.3 Recall 與 profile 注入

profile 與逐輪召回分別使用 `buildProfileBlock()` 和 `buildRecallBlock()` / `buildRecallBlockDetailed()`。宿主可提供壓縮器、顯示結果和統計資訊，不能重寫檢索目標、排序、token 預算和服務端相容回退。狀態列需要計數時，應消費共享結果和最終注入內容，不能再跑一次召回推算。

會話啟動時的 skill 清單（`<available-skills>`）也由 `buildProfileBlock()` 生成：呼叫方把解析好的外掛配置作為第四個引數傳入，由其中的 `skillCatalog` 和 `skillCatalogTokenBudget` 旋鈕決定開關和預算。介面卡不能自己請求 `GET /api/v1/skills`，也不能自己拼裝 skill 列表。不傳這個引數的宿主，得到的 profile 塊裡沒有 skill 清單。

自動召回必須攜帶正確會話身份和 peer，並遵守 input filter、bypass 和開關。空結果應保持為空，不把服務端的“無相關記憶”佔位文本當成記憶注入。壓縮失敗可退回已有的未壓縮結果；不得憑空補寫摘要。壓縮後的 `viking://` URI 必須仍可讀取，原始使用者問題、召回塊與宿主包裝也必須能在 capture 時區分，避免重複寫入注入的舊記憶。

如果使用宿主 CLI 壓縮內容，必須隔離這次輔助呼叫的自動記憶 hook，限制執行時間，並複用已有壓縮介面。不得啟動一個再次觸發自身 recall/capture 的遞迴 Agent。模型選擇和呼叫方式屬於宿主適配，通用壓縮結果處理屬於共享層。

### 5.4 Capture 的資料與確認規則

優先讀取宿主提供的完整 transcript/rollout，stdin 只在已驗證缺少完整來源時作為補償。Stop payload 不一定有使用者輸入，不得用最後一條助手輸出偽造一輪完整對話。檔案暫時不可讀和“沒有新訊息”必須是不同結果。

宿主解析器先把外部記錄轉換成共享捕獲模型，再呼叫共享清洗和傳送邏輯。文本與結構化工具內容分開保留：工具名、呼叫 ID、輸入、輸出、狀態以及可取得的 turn ID，應來自真實記錄。不要把同一次工具呼叫的原生事件、MCP 結果和巢狀表示重複記成幾次呼叫；也不要僅保留最終助手文本而丟掉工具活動。正文過濾不能意外刪除僅包含工具的有效記錄。

過濾與截斷策略使用 `capture-utils.mjs` 和 `input-filters.mjs`。工具輸出的正文摘要與結構化 `tool_output` 不是同一個欄位；當前實現把大輸出交給服務端外接，客戶端保留防止異常載荷的上限。不要為了壓縮文本摘要把結構化證據一起截掉。

寫入遵守以下順序：

```text
讀取新記錄 → 解碼與過濾 → 按順序傳送
                          ├─ 服務端確認：推進已傳送進度
                          ├─ 已持久化到 pending：可推進交接進度，仍未送達服務端
                          └─ 傳送與入隊均失敗：保留原進度，等待恢復
```

必須保留以下不變數：

- 游標只推進到連續確認的位置。共享傳送器返回 `sent` 與 `queued`；允許按兩者推進的介面卡，必須確認 `queued` 表示已落盤，並保留後續重放責任。不能把嘗試次數當成功次數。
- 去重優先使用穩定訊息 ID、turn ID 或 transcript 位置。相同文本可能是兩個合法輪次，不能只按文本 hash 永久去重。
- 多程序更新同一狀態時必須加會話鎖；狀態寫入使用臨時檔案和原子 rename。鎖等待、陳舊鎖回收和持有時間必須相容。長任務需要能證明所有權與存活的鎖，不能直接套用更短的 stale TTL。
- 訊息傳送成功但狀態儲存失敗後的重放，應有可解釋的重複處理策略。沒有服務端冪等保證，就不能宣稱 exactly-once。
- transcript 截短、resume 或 compaction 不能讓游標永久越過新記錄；必須說明如何識別並恢復。
- 子代理記錄由明確的一方採集。若主 transcript 已包含子代理內容，單獨的子代理 hook 不得重複匯入同一記錄。

### 5.5 Commit、重試和退出

Commit 表示請求服務端歸檔並觸發處理，不代表長期記憶已經提取完畢。HTTP 成功、任務已受理、歸檔完成和提取完成要分別報告，不能把 `task_id` 的出現解釋成所有工作已完成。

同一會話應先補齊訊息，再提交。部分訊息失敗時，應保留活動 session 和未完成狀態；採用 pending 交接的實現，還必須證明 commit 不會越過未重放的訊息。**複用 pending queue 本身，不等於自動獲得訊息與 commit 的事務順序**。接入時要驗證完整失敗序列，並按宿主實際情況選擇延後 commit 或受順序約束的重放。

共享重試分類的現狀是：網路失敗、408、429、5xx 可重試；409 只有明確標記 `error.details.retryable` 時才可重試。401/403 和普通引數錯誤不能不斷入隊。批次傳送由 `sendSessionMessages()` 控制，每批最多 100 條，批次介面返回 404/405 時回退序列傳送。宿主不得另寫一套狀態碼列表或分批迴圈。

入隊時必須保留原始 payload，包括 `keep_recent_count` 等提交引數；重放仍執行原操作。提交失敗不能提前清除活動 ID、結束標記或待補訊息。pending 有重試次數、重放批次和 TTL 限制，屬於有界恢復能力，不能向用戶承諾離線資料永久保留。

退出預算按宿主實測設定。當前 Codex SessionEnd 的上限為 3 秒，入口先寫 `.ended` 標記，再啟動 worker；下次 SessionStart 掃描未完成或過期活動會話。resume 不等於結束，舊 worker 也不能提交已經恢復的新會話，因此標記與清理需要對應同一次結束事件。詳細依據見 [Codex commit design](https://github.com/volcengine/OpenViking/blob/main/examples/codex-memory-plugin/DESIGN.md)。

後臺寫入使用 `maybeDetach()` 和 `readHookStdin()`，必須正確轉交已經讀取的 stdin，防止父子程序各讀一次後丟失 payload。detach 成功只表示 worker 已啟動；還要驗證 worker 在宿主退出後能否存活，失敗時如何通過 transcript、pending 或結束標記恢復。不能把返回合法空結果當成寫入成功。

同步收尾要給鎖等待、訊息補齊和 commit 一個總體時間預算，各步驟使用剩餘時間。不得讓每一步重新獲得整個 hook timeout。後臺 worker 也必須有界，不能讓卡住的網路請求永久持有鎖。

服務端欄位、配置回顯或 API 存在，不足以證明自動提交會在實際訊息路徑觸發。若要把提交職責從外掛交給服務端，必須驗證執行行為、舊服務端降級和不會重複提交；不能僅憑一個 `auto_commit` 配置刪掉外掛的可靠提交點。

## 6. MCP 與模型可見工具

Hook 提供自動生命週期行為，MCP 提供模型主動呼叫的工具。兩者通過同一套配置和身份連線 OpenViking，但職責獨立。外掛啟動時應能回答：哪些內容自動注入，哪些操作必須由模型呼叫，哪些行為停用後仍可使用 MCP。

支援 stdio MCP 的宿主，應採用 Claude Code、Codex 已使用的共享 proxy：入口解析配置，經 `buildMcpProxyConfig()` 整理，再交給 `createOpenVikingMcpProxy()`。HTTP transport 有 MCP 自身的 session、SSE 和協議協商，不能簡單用 REST 的 JSON helper 替換；公共鑑權頭仍由 `buildOvHeaders()` 生成。

proxy 入口不得擁有自己的工具 schema、副本 API client、SSE parser 或重試狀態機。`tools/list` 和 `tools/call` 應以服務端為準，不能為了改工具描述而維護第二套記憶體工具目錄。確需本地工具時，使用共享 `localToolProvider` 介面並限定範圍，工具名不得意外覆蓋服務端工具。

新增宿主必須驗證：

- 從宿主實際工作目錄啟動，所有相對路徑、根路徑變數和環境變數白名單都有效。Codex `.mcp.json` 的 `env_vars` 是具體宿主要求，不能推斷其他宿主會同樣繼承。
- `initialize` 的協議協商、通知無普通響應、JSON 與 SSE 響應、併發響應 ID 均正確，stdout 無日誌汙染。
- MCP session 過期和憑據檔案變更使用共享恢復邏輯；未經限定的工具呼叫不得在網路錯誤後盲目重試，尤其是有寫副作用的操作。
- hooks 與 MCP 在環境變數、預設檔案、自定義檔案和 profile 切換後仍使用預期的 URL 和身份。用實際請求頭和請求目標驗證，不能只看配置檔案內容。
- 診斷和文件列出的工具名與宿主實際顯示一致；`remember` 不能隨意寫成 `store`，工具名稱空間也不能照抄另一宿主。

直接連線遠端 MCP 只有在宿主確有合適的憑據和配置能力時才採用，並記錄與 hook 保持一致的辦法。不要增加 wrapper、環境檔案或安裝時重寫來繞過已經能解決問題的共享 proxy。

## 7. URI guard、Skill 和診斷

`viking://` 是虛擬 URI。本地檔案工具的路徑引數是 `viking://` URI 時必然失敗，所以宿主支援工具執行前檢查時，用 `evaluateUriGuard()` 拒絕這次呼叫。shell 命令裡的 `viking://` URI 可能只是資料（`ov` 命令引數、HTTP 請求體、搜尋模式），所以命令照常執行，再通過宿主的模型可見上下文通道附上 `evaluateUriNotice()` 生成的提示；`PreToolUse` 類宿主直接用 `preToolUseOutput()`，它返回拒絕或提示 envelope。介面卡中只定義替代工具提示和 envelope。檢查器不能擴充成一般命令攔截器；普通檔案路徑應保持原有行為。宿主不支援該事件時，明確限制並通過 Skill 指引模型使用 MCP，不得宣稱具備等效攔截。

共享 Skill 的原始檔放在 [`examples/skills/`](https://github.com/volcengine/OpenViking/tree/main/examples/skills/)，通過 `SKILL_TARGETS` 交付，禁止在多個外掛副本里分別修改同一段指導。Skill 只描述真實可呼叫工具和實際能力；自動 hook 已處理的捕獲、提交不應再要求模型每輪手動重複執行。不同工具集確有不同操作語義時，可以保留獨立 Skill，並說明理由。生成 Skill 時不能在 YAML frontmatter 前插入生成標記。

存放在 OpenViking 裡的 skill 只通過服務端的 `add_skill` MCP 工具新建、安裝、共享和替換，它和 REST `POST /api/v1/skills` 共用同一套安裝程式碼。宿主不得自己實現安裝：介面卡不能把 `SKILL.md` 寫進 skills 子樹，也不能自行解包或上傳 skill 目錄。服務端的 `write`、`edit` 拒絕寫使用者根下的 skills 子樹；本地 write/edit 指向 skill URI 而被拒絕時，URI guard 通過 `isSkillUri()` 把模型引導到 `add_skill`。`openviking-skills` 這個 Skill 負責教模型走這套流程，所以 `SKILL_TARGETS` 只把它交付給自帶 Skill、且 `add_skill` 確實可用的 MCP 宿主。

doctor 使用 `runDoctor(hostSpec)`，宿主只補充安裝位置、manifest、hook 註冊、狀態檔案等檢查。公共配置、憑據、網路和輸出格式由 `doctor-core.mjs` 負責。必須能夠檢查安裝版本、配置來源、生效值、peer、MCP 入口、hook 時間限制和 pending/會話狀態。優先提供離線模式和 JSON 輸出，離線檢查不應偷偷發起網路請求。

排障資訊至少能區分停用、bypass、無結果、超時、鑑權失敗、已入隊、入隊失敗與提交失敗。日誌保留宿主、階段、會話關聯、耗時和 trace ID；預設不寫 API key、完整 Authorization 或整份使用者 transcript。doctor 的建議必須是適用於當前安裝形態的真實命令，不能指向已經刪除的 debug 指令碼。

## 8. 檔案佈局、生成與安裝

### 8.1 推薦佈局

以下是位置約定，尖括號表示接入時填寫的名稱，不要求建立所有檔案：

```text
examples/memory-plugin-shared/
  lib/<capability>.mjs          共享行為原始檔
  lib/<capability>.d.mts        需要時提供，與實現一同維護
  lib/install/                 安裝器專用邏輯，不進入 hook 依賴閉包
  testing/support.mjs          測試輔助，不隨執行時交付
  sync.mjs                     分發目標與閉包生成

examples/agent-hook-plugin/
  hosts/<host>.mjs             宿主介面卡
  hosts/<host>/                宿主宣告、hook/MCP 配置和必要資源
  scripts/hook.mjs             共用排程入口
  servers/mcp-proxy.mjs        共用 MCP 入口

examples/<host>-memory-plugin/ 獨立原生外掛需要時才建立
  <宿主 manifest 目錄>/
  hooks/
  scripts/                    宿主入口、狀態與 transcript 適配
  scripts/shared/             生成物，不手改
  servers/
  skills/
```

模組通過明確的相對 import 連線。公共模組有 TypeScript 消費者時，`.d.mts` 與 `.mjs` 放在同一個權威目錄並一起生成。不要在每個產物目錄手寫一份型別宣告。需要顯式 re-export 時列出名稱，避免 `export *` 與介面卡的同名實現衝突。

### 8.2 按交付方式選擇生成策略

| 交付方式 | 當前例子 | 生成要求 |
| --- | --- | --- |
| 宿主直接載入 Git 中的外掛目錄 | Claude Code、Codex、`agent-plugins`、OpenClaw（`ov-install` 的 GitHub 源） | 共享副本提交到 Git，checkout 後即可載入 |
| npm 包或安裝歸檔 | OpenCode、DSH、Pi | 在 prepack 或 staging 時生成；執行時副本不提交 Git |
| 安裝器組裝相鄰執行時目錄 | Cursor、TRAE、TRAE CN、ZCode | 使用 `ASSEMBLED_ROOTS` 推導 `lib/MANIFEST`，按 manifest 複製共享執行時 |

[`sync.mjs`](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/sync.mjs) 是上述目標的登記處。新增獨立外掛登記 `TARGETS` 的 source root、目標目錄和 `committed`；新增組裝根才擴充 `ASSEMBLED_ROOTS`，普通薄宿主通常已被現有根覆蓋。是否交付 Skill 另外登記 `SKILL_TARGETS`。不要維護一份“需要複製的 20 個模組”清單。

修改共享原始碼後執行：

```bash
node examples/memory-plugin-shared/sync.mjs
```

生成器分析靜態 import 和字面量動態 import；依賴路徑必須可分析，不能用字串拼接隱藏必需模組。組裝後的相對目錄關係必須與原始碼一致，讓同一個 import 在倉庫和安裝目錄都成立。不要用絕對開發路徑、臨時 symlink 或 `NODE_PATH` 讓本機測試僥倖通過。

PR 必須包含應提交的最新生成物，並檢查新出現但未跟蹤的檔案。主線的 [`plugin-shared-sync.yml`](https://github.com/volcengine/OpenViking/blob/main/.github/workflows/plugin-shared-sync.yml) 是額外保障，不能代替 PR 中的完整交付。只修改文件且未改變生成源時，無需為了走流程生成無關副本。

### 8.3 安裝與解除安裝的行為要求

安裝複用 [`install.sh`](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/install.sh)，JSON/JSONC 合併放在 [`lib/install/`](https://github.com/volcengine/OpenViking/tree/main/examples/memory-plugin-shared/lib/install/)，不要在 shell heredoc 內繼續堆放大型 JavaScript。安裝器應做到：

1. 在修改使用者配置前完成解析、校驗和所需檔案準備。壞 JSON/JSONC 必須報錯並保留原檔案，不能將解析失敗當作空配置。
2. 重複安裝冪等，不增加重複 hook/MCP 條目；保留其他外掛和使用者配置，保留格式中有意義的註釋。
3. 路徑有空格、宿主不展開變數、自定義配置路徑等情況都能正確處理；只向宿主寫入它實際支援的欄位。
4. 解除安裝按本外掛擁有的條目刪除，包括 URI guard；保留其他整合、憑據、記憶和會話資料。解除安裝不應要求重新下載原始碼。
5. 單個客戶端解除安裝後，其他客戶端依賴的共享執行時仍可用；失敗時不能留下一半指向舊目錄、一半指向新目錄的配置。

安裝包校驗使用 [`stage-memory-plugin-marketplace.sh`](https://github.com/volcengine/OpenViking/blob/main/.github/scripts/stage-memory-plugin-marketplace.sh) 和 [`check-marketplace-archive.mjs`](https://github.com/volcengine/OpenViking/blob/main/.github/scripts/check-marketplace-archive.mjs)。必需入口、傳遞依賴、Skill 中呼叫的指令碼都必須存在；歸檔排除 `node_modules`、`.git` 和本機秘密。檢查工具不能只相信 staging 提供的目錄列表，還必須驗證預期分發目標沒有整項遺漏。

釋出前至少從最終歸檔或 tarball 解包後執行一次入口和安裝 smoke test。原始碼 import 成功，只能證明原始碼樹完整，不能證明使用者拿到的包完整。

## 9. Code smell 與可維護性評審

評審時應沿“宿主輸入 → 規範模型 → 共享能力 → 狀態確認 → 安裝產物”閱讀。每條規則要能找到唯一實現，每個副作用要能找到明確呼叫者。以下問題應在本次相關修改中解決，或給出具體的相容理由；不能用“以後統一”解釋新增重複。

| 訊號 | 具體問題 | 應採用的處理 |
| --- | --- | --- |
| 複製後改名的 client、recall、doctor | 後續修復必須修改多份，行為逐漸分叉 | 將規則放回現有能力模組，宿主只傳引數 |
| 一個欄位出現在多個預設值表 | 配置、診斷與實際執行不一致 | 在 schema 宣告，其他檢視推導 |
| 配置被讀取但沒有消費者 | 使用者修改開關卻沒有效果 | 沿真實呼叫驗證，缺能力就不宣稱支援 |
| 共享函式中密集判斷 harness 名 | 共享層正在承擔宿主協議 | 將事件、格式和策略移到介面卡 |
| 為消除幾行重複增加一組布林開關 | 呼叫者必須理解多個互斥模式，非法組合增加 | 使用小回調或保留短而直接的宿主程式碼 |
| `utils.mjs` 同時處理解析、聯網和提交 | 規則沒有歸屬，測試也難以隔離 | 按能力拆分，解析儘量純函式化 |
| loader 讀配置同時寫檔案或啟動服務 | 呼叫次數改變系統行為 | 將動作放在顯式安裝或生命週期入口 |
| 返回一個含糊的 `true` 表示“處理過” | 無法區分送達、入隊和跳過 | 返回明確結果，保留錯誤與確認數量 |
| catch 後返回成功或空陣列 | 檔案不可讀、鑑權失敗被偽裝成無資料 | 保留失敗類別，在宿主入口決定合法降級 |
| 用全域變量表示“當前會話” | 併發視窗與子代理相互覆蓋 | 以 session 為鍵持有狀態，傳入當前身份 |
| `export *`、多層同名轉發 | 無法判斷實際呼叫的是哪份實現 | 顯式匯入匯出，刪除無相容價值的薄殼 |
| 註釋承諾可靠提交，程式碼只 `spawn()` | 文案掩蓋未確認的副作用 | 寫清恢復條件，用實際狀態證明完成 |
| 手動編輯 shared 副本或型別宣告 | 下次 sync 覆蓋修復 | 修改權威源並生成 |
| 在釋出指令碼手列所有共享檔案 | 新依賴遺漏只在使用者機器暴露 | 從依賴閉包與 manifest 校驗 |
| 舊設計、未呼叫指令碼和測試副本長期保留 | 搜尋結果誤導維護者，重複測試製造假覆蓋 | 刪除引用後移除；必要歷史留在 Git |

函式名和變數名要反映動作和狀態，例如 `parseTranscript`、`sent`、`queued`、`commitAccepted`，避免 `handleEverything`、`done`、`successLike`。註釋解釋宿主限制、資料不變數和取捨，不復述下一行程式碼。只為日誌或相容保留的 wrapper 應寫清理由。

相似不等於相同。原始碼中呼叫同一個共享 builder 也不自動證明 hook 與 MCP 採用完全相同的憑據投影。遇到這種差異，先驗證其公開行為，再決定修復或保留；不要把當前參考實現的每一行提升為規範。

## 10. 新增一個外掛的實施順序

1. **完成接入記錄**。確認第 2 節的宿主事實，定義支援矩陣、最低版本、缺失事件的替代方案，以及會話 ID 和 commit 時機。
2. **選擇接入形態**。優先增加現有薄宿主介面卡；只有分發或生命週期確有要求才新增獨立包。把決定寫在 README/設計說明中。
3. **先接通配置與 MCP**。註冊 harness ID，使用共享 builder 和 proxy，驗證真實啟動方式下的路徑、環境和鑑權，並用同一配置驅動 hook。
4. **接入自動讀取**。實現啟動 profile 和逐輪 recall 的事件/輸出轉換，驗證停用、bypass、空結果和網路失敗。
5. **接入可靠寫入**。實現 transcript 解碼、穩定身份、增量游標、確認更新、commit 和恢復。優先覆蓋掉線、重複事件和尾部訊息補齊。
6. **接入宿主輔助能力**。按支援情況增加 URI guard、Skill、doctor；不要為不存在的事件放空入口。
7. **完成安裝和分發**。登記生成目標、安裝器、歸檔/marketplace、版本檢查和釋出工作流，確保包裡的入口可直接執行。
8. **驗證並更新文件**。複用現有契約測試，補足宿主差異的驗證，執行最終產物 smoke test，記錄已測版本、平臺與限制。

每一步應有可檢查的產物，不以“目錄已建好”或“工具列表能返回”作為全部完成。過程可以分成獨立提交，但每個提交都應能解釋其行為並保持已有接入可用。

## 11. 測試與驗收證據

測試驗證使用者可觀察的契約和主要失敗情況。遵循貢獻指南，優先擴充現有高價值測試，不為簡單轉發、新檔案或幾行配置機械地增加單測。共享能力測一次，宿主測試只驗證接線和差異；不要複製整套 recall、pending 或 MCP 測試。

公共輔助函式放在 [`testing/support.mjs`](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/testing/support.mjs)，不要從另一個測試檔案 import helper，也不要放進隨外掛交付的 `lib/`。測試使用獨立臨時目錄、隔離的配置和 pending 路徑、動態埠；安裝測試不得修改開發者正在使用的 Agent 配置或與其他測試共享被生成器改寫的目錄。

| 驗證範圍 | 至少覆蓋的真實行為 | 現有入口 |
| --- | --- | --- |
| 配置與開關 | 分層覆蓋、別名衝突、非法值、未配置標記、關閉後無新網路副作用 | `plugin-config.test.mjs`、`plugin-known-keys.test.mjs`、宿主 config 測試 |
| 憑據與 peer | hook/MCP 的請求身份一致；自定義路徑、profile 切換、多 workspace | `credentials.test.mjs`、`mcp-hook-parity.test.mjs`、`wire-headers.test.mjs`、`mcp-proxy-config.test.mjs` |
| Hook 輸出 | 真實 payload、單次合法輸出、空結果、未知/缺失欄位、錯誤路徑 | `agent-hook-runtime.test.mjs`、宿主事件測試 |
| Recall | 開關、bypass、空結果、服務端相容、壓縮失敗、可讀 URI | `recall-core.test.mjs`、宿主 recall 測試 |
| Capture | 完整文本和工具記錄、重複事件、重複文本、巢狀工具、部分成功、截短恢復 | `capture-utils.test.mjs`、`batch-send.test.mjs`、宿主 transcript 測試 |
| 狀態與提交 | 併發 Stop/End、worker 失敗、resume 與舊結束標記、不可讀尾部、入隊失敗、提交引數保留 | `pending-queue.test.mjs`、Codex session 測試、宿主恢復測試 |
| MCP | initialize、協議版本、通知、SSE、過期恢復、錯誤語義、stdout | `mcp-proxy-core.test.mjs`，另加宿主啟動 smoke test |
| 安裝產物 | 冷安裝、重複安裝、保留第三方配置、壞配置不覆蓋、解除安裝不殘留、完整依賴閉包 | `install-agent-hooks.test.mjs`、`release-marketplace.test.mjs`、`sync.test.mjs` |
| 維護約束 | 請求頭不再分叉、schema 與消費者匹配、生成物跟蹤策略正確 | `one-header-builder.test.mjs`、`plugin-known-keys.test.mjs`、`sync.test.mjs` |

這些檔名均相對於共享庫，除非註明宿主。完整命令以 [PR CI](https://github.com/volcengine/OpenViking/blob/main/.github/workflows/pr.yml) 和各外掛 package scripts 為準；不要在新外掛再維護一份容易過期的全倉庫測試清單。原始碼結構檢查用於保護關鍵的單一實現約束，不能代替行為測試，也不應鎖死無關 helper 名稱或行數。

例如，修改配置與 MCP 公共契約後，可先在倉庫根執行以下聚焦檢查，再執行受影響宿主的測試：

```bash
node examples/memory-plugin-shared/sync.mjs
node --test \
  examples/memory-plugin-shared/plugin-config.test.mjs \
  examples/memory-plugin-shared/credentials.test.mjs \
  examples/memory-plugin-shared/mcp-proxy-config.test.mjs \
  examples/memory-plugin-shared/mcp-proxy-core.test.mjs
```

安裝和 marketplace 測試會生成執行時和組裝安裝目錄，按 CI 單獨序列執行：

```bash
node --test --test-concurrency=1 \
  examples/memory-plugin-shared/install-agent-hooks.test.mjs \
  examples/memory-plugin-shared/release-marketplace.test.mjs
```

當前 CI 使用 Node.js 24，其中部分 TypeScript 測試依賴原生型別剝離；測試環境版本和外掛執行時最低版本必須分別說明。Node.js 下通過不代表 Windows 上的 detach、路徑引用和程序回收已經驗證。缺少實測的平臺要明示，不用一個全綠數字替代驗證範圍。

驗收報告應記錄“用哪個產物、在什麼宿主版本、執行什麼場景、觀察到什麼”。對於寫入，至少能確認服務端收到完整尾部訊息和對應提交；對於安裝，至少能確認解包後的入口可以找到依賴。只有文件修改時，檢查語法、相對連結、引用符號和示例即可，無需自動執行整套外掛測試。

## 12. 維護、釋出和文件同步

### 12.1 按改動型別完成維護

| 改動 | 必須跟進的內容 |
| --- | --- |
| 共享行為修復 | 修改權威模組、驗證受影響宿主、生成副本、檢查所有相關分發產物和版本 |
| 宿主 payload 或事件升級 | 更新介面卡、真實格式 fixture、最低版本/降級說明；不修改其他宿主的預設行為 |
| 新增配置項 | schema、真實消費者、configured 語義、診斷來源、使用者文件；不得只加解析 |
| 增加公共模組依賴 | 同目錄型別宣告、sync 閉包、`lib/MANIFEST`、歸檔和離線安裝驗證 |
| 目錄或包名變更 | import、manifest、installer、marketplace、CI path filter、Skill、連結與解除安裝識別 |
| 刪除相容邏輯 | 明確支援版本與遷移說明；不能順手刪除仍承諾支援的配置別名 |
| 純文件改動 | 校驗與現狀一致、相對連結有效；不為說明文字改動無關行為 |

修復應從失敗行為和負責的模組出發。若共享問題在單一宿主暴露，仍應在共享源修復；若只有一個宿主 payload 變化，就保持在該介面卡內。大型重構按可獨立驗證、可回退的步驟推進，避免把行為變更、歷史清理和分發調整混成無法歸因的一次替換。

### 12.2 版本與釋出鏈

版本號決定使用者是否能拿到更新。新增外掛必須接入適用的版本檢查和釋出工作流，不能只新增目錄。現有 [`check-plugin-version-bumps.sh`](https://github.com/volcengine/OpenViking/blob/main/.github/scripts/check-plugin-version-bumps.sh) 會把共享 `lib/` 變化計入其登記的每個外掛；它不是所有分發目標都已自動覆蓋的證明。增加或改變目標時，必須檢查登記範圍。

宿主 manifest、`package.json`、存在的 lockfile 根包版本、安裝 manifest 和安裝器判定版本必須一致。修改版本時使用相應包管理流程，不為一個版本數字重寫無關依賴。`User-Agent` 和 doctor 應報告實際產物版本，避免使用者顯示已升級而程式碼仍舊。

npm/歸檔目標的構建必須從乾淨原始碼生成共享檔案，再打包。當前 [`plugin-npm-release.yml`](https://github.com/volcengine/OpenViking/blob/main/.github/workflows/plugin-npm-release.yml) 的矩陣覆蓋 DSH 和 OpenCode；其他包要核對各自發布流程，不能因使用相同 prepack 就推斷已接入這個矩陣。釋出觸發條件必須關注共享源變化，不能依賴已經不提交的 shared 副本發生 diff 才觸發。

合併前按實際 base 檢查版本，例如在本地 `origin/main` 已更新且確為目標分支時：

```bash
bash .github/scripts/check-plugin-version-bumps.sh origin/main
git diff --check
git status --short --untracked-files=normal -- examples agent-plugins
```

版本檢查按已提交的 `base...HEAD` 識別變更，不會把未提交工作區當作完整 PR；最後一次檢查應針對最終提交。生成器執行後的未跟蹤檔案也要審查，不能僅依賴 `git diff`。釋出後的驗證應檢查使用者實際下載到的包及版本，不以 CI 已啟動作為完成依據。

### 12.3 文件是介面的一部分

外掛 README 至少包含：支援範圍和版本、最快可用的安裝方式、憑據來源、自動行為與 MCP 的分工、核心開關、限制、升級/解除安裝、診斷與測試入口。面向使用者的安裝章節優先寫可直接使用的一鍵命令；GUI 步驟獨立成段，不把 CLI 命令和 TOML 配置混成 GUI 操作。

使用者整合文件與本規範放在 `docs/{en,zh}/agent-integrations/`，英文和中文對應頁同步維護。如果該宿主還存在 `docs/images/agents/{en,zh}/` 的映象說明，也要同步核對；不需要為不存在的映象機械建立多份相同文本。共享配置的完整解釋連結到共享 README，宿主頁只說明差異和常用示例。

設計文件只保留讀程式碼無法直接回答的約束、選擇理由和恢復不變數。支援矩陣、真實命令和入口變化後及時更新，刪除互相矛盾的舊說明。不要把臨時排查記錄、一次性驗證報告或過期測試數字當作長期設計文件。

## 13. 合入前檢查單

- [ ] 宿主版本、輸入輸出、時間限制、訊息來源和結束語義均有證據；不支援的能力已註明。
- [ ] 選擇了合理的接入形態，新增程式碼主要描述宿主差異，共享層不反向依賴宿主。
- [ ] 配置只有一處宣告，開關在執行鏈生效，hook 與 MCP 的實際連線和身份經過驗證。
- [ ] session 與 peer 不混用；多視窗、resume、子代理和 cwd 變化不會誤用狀態。
- [ ] capture 保留文本與工具證據；部分失敗、離線入隊、重複事件和尾部補齊不會錯誤推進游標。
- [ ] commit 順序與恢復責任明確；退出後 worker 失敗也有可驗證的補償辦法。
- [ ] Hook/MCP 輸出合法，URI guard、Skill 和 doctor 只承諾真實能力。
- [ ] 生成目標、安裝、解除安裝、歸檔、型別宣告和釋出觸發條件完整；最終產物已驗證。
- [ ] 版本與相關 manifest 一致；運行了與改動相稱的檢查，並記錄未驗證的平臺或場景。
- [ ] 文件和遷移說明與最終行為一致，沒有新增重複配置、舊路徑引用或無人使用的輔助指令碼。

## 14. 維護者閱讀入口

按問題選擇入口，避免從各外掛生成副本開始追蹤：

- 已有整合的支援範圍：[整合能力參考](./16-capability-reference.md)。
- 配置、peer、生成策略：[Memory Plugin Shared README](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/README.md)。
- Claude Code 的事件接線：[hooks.json](https://github.com/volcengine/OpenViking/blob/main/examples/claude-code-memory-plugin/hooks/hooks.json)；召回適配：[auto-recall.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/claude-code-memory-plugin/scripts/auto-recall.mjs)。
- Codex 的提交、異常退出與恢復：[DESIGN.md](https://github.com/volcengine/OpenViking/blob/main/examples/codex-memory-plugin/DESIGN.md)；實現：[session-end.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/codex-memory-plugin/scripts/session-end.mjs)。
- 新增配置檔案式宿主：[agent-hook-plugin README](https://github.com/volcengine/OpenViking/blob/main/examples/agent-hook-plugin/README.md)；嚴格協議例項：[ZCode DESIGN](https://github.com/volcengine/OpenViking/blob/main/examples/agent-hook-plugin/DESIGN.md)。
- CI 和交付檢查：[pr.yml](https://github.com/volcengine/OpenViking/blob/main/.github/workflows/pr.yml)、[sync.mjs](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/sync.mjs)、[marketplace archive checker](https://github.com/volcengine/OpenViking/blob/main/.github/scripts/check-marketplace-archive.mjs)。
