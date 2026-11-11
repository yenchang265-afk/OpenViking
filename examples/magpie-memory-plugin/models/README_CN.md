# OpenViking 模型管理外掛（Magpie）

[English](README.md)

在 Magpie 的 **Agents → OpenViking** 中選擇模型，讓 OpenViking 與 VikingBot 使用 Magpie 的供應商、帳號和路由。供應商金鑰留在 Magpie，OV 儲存閘道器地址、閘道器 Key 和完整模型 ID。

這是統一外掛 `@openviking/magpie-plugin` 的模型管理模組，不再作為獨立外掛安裝。安裝和遷移見 [統一外掛說明](../README_CN.md)。本文的 `node cli.mjs ...` 在 `models/` 目錄執行。已用官方 Linux Magpie 0.1.3528 完成隔離模型切換、自動重啟和恢復驗證，Windows 尚未驗證。

## 連線和管理範圍

進階選項可通過 Plugins → Options 或以下本地檔案配置。日常使用只需在 Agent 行切換模型。外掛 Options 優先於本地檔案。

`~/.config/magpie-openviking-models/adapter.json`：

```json
{
  "serverUrl": "http://127.0.0.1:1933",
  "rootApiKeyFile": "~/.config/magpie-openviking-models/root.key",
  "manageVlm": true,
  "botMode": "follow",
  "pollMs": 2000
}
```

`root.key` 中只放 OV Root API Key，檔案許可權建議設為 `0600`。這是 **OV 管理憑據**，與 Magpie 閘道器 Key、普通記憶訪問 Key 分開。

外掛先執行 `ov config show -o json` 發現當前 CLI 連線。該命令輸出脫敏 Key，因此只使用其中的地址；Root Key 仍從同一 CLI 配置檔案私下讀取，不把掩碼當作憑據。CLI 不可用時回退到配置檔案。未指定地址時，讀取 `OPENVIKING_CLI_CONFIG_FILE` 或 `~/.openviking/ovcli.conf` 的 `url`，最後使用 `http://127.0.0.1:1933`。憑據優先讀取 `rootApiKeyFile`，其次 `OPENVIKING_ROOT_API_KEY`、`ovcli.conf` 的 `root_api_key`；不會自動把普通 `api_key` 當作 Root。GUI 啟動的 Magpie 可能不繼承終端環境變數，建議使用本地檔案。無認證開發服務可省略 Key。

| 設定 | 行為 |
| --- | --- |
| `manageVlm: true`（預設） | 接管啟動檔案的 `vlm` 模型服務繫結 |
| `queryMode: "preserve"`（預設） | 保留 Query Planner 原配置 |
| `queryMode: "follow"` | 移除可選的 `query_planner` 配置，恢復 OV 原生的 VLM 回退；需要開啟 `manageVlm` |
| `queryMode: "independent"` | 給 Query Planner 指定獨立的 Magpie 模型連線 |
| `queryModel` | 獨立模式下的完整 `provider/model` 或 `group/name`；留空使用 Agent 選擇的模型 |
| `botMode: "preserve"`（預設） | 保留 Bot 現有配置；原本繼承 VLM 的 Bot 會在重新載入後繼續繼承 |
| `botMode: "follow"` | 刪除 Bot 顯式模型和憑據繫結，恢復繼承完整根 VLM；需要開啟 `manageVlm` |
| `botMode: "independent"` | 給 Bot 寫入獨立的 Magpie 連線；預設使用 Agents 中選擇的模型 |
| `botModel` | 獨立模式下，可指定另外一個完整的 `provider/model` 或 `group/name` |
| `manageVlm: false` | 保留根 VLM；仍可獨立管理 Query 和／或 Bot |
| `ovcliConfig` | 顯式指定用於解析服務地址和 Root 憑據的 `ovcli.conf` |
| `restartOnChange` | 預設 true；切換模型或恢復配置後自動重啟並驗證新例項 |
| `pollMs` | 同步間隔，500–60000 毫秒；預設 2000 |

獨立 Bot 示例：

```json
{
  "manageVlm": true,
  "botMode": "independent",
  "botModel": "your-provider/your-tool-capable-model"
}
```

外掛通過 `/bot/v1/health` 檢測原本是否啟用受管 Bot。未啟用或未檢測到時不會建立 Bot 配置、修改啟動引數或開啟 Bot；顯式選擇 Bot 管理模式會報錯。獨立 Bot 不在 OV 的重啟生命週期中，外掛不會為它擅自啟動新程序。修改角色範圍時，會先恢復不再接管的欄位。Bot 的上下文視窗會使用所選模型目錄中的已知值；未知時保留原值，需要自行核對。

### 分別選擇 VLM、Query 與 Bot 模型

VLM 繼續在 **Agents → OpenViking** 選擇。在 **Plugins → OpenViking → Options** 中將以下欄位合併到現有選項，保留原有連線配置和功能開關：

```json
{
  "queryMode": "independent",
  "queryModel": "your-provider/your-query-model",
  "queryParameters": { "max_tokens": 2048, "timeout": 90 },
  "botMode": "preserve"
}
```

模型 ID 須來自 Magpie 模型目錄，也可以填寫路由組 `group/name`。`queryMode: "preserve"` 會釋放 Query 接管並恢復原配置；`"follow"` 移除整個可選配置，繼承 VLM 模型及生成引數。`queryParameters` 僅在獨立模式生效。Query 配置段整體儲存恢復記錄：接管期間手動修改其中任意欄位都會阻止恢復，不會覆蓋使用者修改。原本為 `null` 或不存在的配置段也會準確還原。預設不啟用 Bot，不改變 Query。

僅修改 Query 同樣通過現有生命週期重啟並驗證 OV。帳號覆蓋不在管理範圍：帳號顯式 Query 配置可覆蓋啟動配置；帳號未配置 Query、但有自己的 VLM 時，帳號 VLM 也可能優先於服務端 Query。不能僅憑啟動檔案判斷所有帳號的實際模型。

### 輸出預算和生成引數

未指定的模型引數沿用現有配置；輸出預算仍按所選模型的已知上限校驗。

Options / `adapter.json` 中對應 `vlmParameters`、`queryParameters`（僅獨立 Query）與 `botParameters`，使用統一的 snake_case 欄位：

```json
{
  "vlmParameters": { "max_concurrent": 4, "max_tokens": 8192, "temperature": 0.2, "thinking": false, "timeout": 600 },
  "botParameters": { "max_tokens": 4096, "thinking": true, "timeout": 120 }
}
```

省略引數保留原值；`max_tokens: null` 讓 OV 使用供應商預設限制。Bot 獨立模式下同樣使用模型預設值；跟隨 OV 時，Bot 的空值繼續使用 OV 的輸出限制。Bot 的非空輸出預算會覆蓋繼承值，因此兩邊分別校驗。

`vlmParameters.max_concurrent` 可配置 OV 語義處理及 Compile 使用的併發容量，必須為正整數；預設沿用原值，修改後需要重啟 OV。它不是閘道器或 VikingBot 的全域請求併發限制，多條處理路徑可能疊加負載。Bot 不支援同名的 `bot.agents.max_concurrent`，外掛不會寫入這個無效欄位。訂閱模型可先從 2–4 這樣的小併發觀察耗時和取消情況，這不是供應商保證的配額。

切換模型時，若目錄提供 `max_output_tokens`，外掛將請求的 `max_tokens` 限制在其範圍內，不會把上下文視窗誤當作最大輸出。比如原配置 32768、新模型輸出上限 8192，會儲存為 8192，並在 `adjustments` 列出原因；原主憑據上的輸出限制也會保留並校驗。換回容量更大的模型時會重新使用原請求預算；斷開時恢復原引數。目錄缺失上限時不猜測，保留預算並在 `warnings` 提示核對；配置中的環境變數輸出預算需要通過引數選項提供明確數值。外掛日誌也會展示重啟要求、預算調整和相容性提示。

若目錄明確標識不支援 temperature，會清除原取樣值；使用者顯式請求不支援的 temperature 則停止同步。`thinking` 保留使用者選擇並提示驗證協議相容性。重試策略保持原設定；僅在引數選項顯式指定時調整 timeout 和 VLM 的 max_concurrent。配置儲存仍需相應程序重啟後生效。

Embedding、Rerank、Bot 渠道、工具、生圖模型等保持原配置。Query 預設保持不變，顯式設定後才接管。本版本只管理啟動檔案；遇到受管 VLM 或 Query 的 Cluster 執行覆蓋時停止接管，不會聲稱檔案修改已影響實際模型。Account 模型覆蓋不在本外掛管理範圍內。

## 遠端和容器

通過 Root 配置 API 操作伺服器的真實 `ov.conf`，不會嘗試修改客戶端電腦上的同名檔案。除迴環地址外，OV 管理地址和 Magpie 閘道器均要求 HTTPS，禁止重定向和 URL 中嵌入憑據。

Magpie 寫入的閘道器地址必須能被 **OV / Bot 所在機器** 訪問。遠端或容器中的 `127.0.0.1` 指向自身；需要在 Magpie 中配置可訪問的共享閘道器地址和對應 Key。只更改 `serverUrl` 不能解決閘道器可達性。模型目錄檢查由 Magpie 程序所在機器執行，不代替服務端連通性驗證。

## 斷開和恢復

**解除安裝、停用外掛或退出 Magpie 前，先斷開 Agent，並等待恢復完成。**

```sh
magpie openviking-models default
```

斷開恢復原配置後，同樣需要重啟 OV 和 Bot。橋接宿主已退出時，自動恢復不能保證完成；可從本目錄執行：

```sh
node cli.mjs doctor
node cli.mjs status
node cli.mjs restore
node cli.mjs sync
node cli.mjs apply
```

- `status`：讀取本地最後一次同步結果，不做網路請求，也不輸出金鑰。
- `doctor`：檢查本機 CLI、Root 配置訪問許可權、服務重啟能力及 Bot 狀態。
- `restore`：恢復仍由外掛管理的欄位，暫停當前模型選擇，防止下一次輪詢立即接管。
- `apply`：對已儲存的配置執行現有重啟 API；Root 鑑權、配置版本與服務重啟能力均會檢查。`--with-bot` 的受管 Bot 隨 OV 重啟並檢查健康，獨立 Bot 仍需通過自己的程序管理器重啟。
- `sync`：解除暫停並立即同步。CLI 與後臺同步使用同一套配置解析，自動讀取 Magpie 中本外掛的 Options（包括已關閉的外掛條目），無需重複配置憑據。

`~/.config/magpie-openviking-models/state.json` 儲存欄位原值、待寫值和恢復目標，可能包含原有憑據。目錄許可權 `0700`，選擇、狀態和恢復檔案 `0600`。不要分享或提前刪除恢復檔案。狀態中的 `recoveryPending` 表示仍保留配置所有權／恢復記錄，並不一定表示同步失敗。

恢復 CLI 預設讀取 `$XDG_CONFIG_HOME/magpie/plugins.json`（XDG 路徑須為絕對路徑）或 `~/.config/magpie/plugins.json`；便攜模式或自定義配置目錄可在動作後加 `--magpie-config /path/to/magpie-config`。找不到外掛條目時回退到 `adapter.json` 和所選 OV 客戶端配置，存在多個匹配條目時拒絕猜測。

全域 `plugin.enabled: false` 會在下次輪詢暫停模型自動同步及自動重啟，顯式執行恢復 CLI 不受此開關限制。

配置通過服務端版本號防止覆蓋併發修改。若服務端已有外掛之外的待重啟配置，外掛返回 `external_restart_required`，暫停寫入與自動重啟並保留恢復記錄；先通過原管理方式應用或撤銷這些改動，再繼續模型同步。手動更改外掛管理的欄位後，進入 `conflict`，不會強行覆蓋；狀態只列欄位名。先將衝突欄位改回外掛最後寫入的值，再執行恢復；若決定保留手動配置，請先備份恢復記錄並人工核對。切換 OV 服務地址或伺服器配置檔案位置時，必須先在原目標上恢復。

## 與記憶功能一起使用

OV 和 Bot 繼續使用 `openviking-models` 閘道器身份，統一外掛的記憶層將其識別為原生流量，跳過召回和採集，避免遞迴處理自己的模型請求。

## 開發驗證

```sh
cd .. # 統一外掛目錄
npm run check
npm test
npm pack --dry-run
MAGPIE_BIN=/path/to/magpie node models/tests/magpie-smoke.mjs
```

可通過 `MAGPIE_BUN` 指定已有的 Bun 執行檔，離線驗證原版 Magpie。

宿主測試使用臨時 HOME/XDG 目錄、模擬 OV 與模型供應商，不讀取真實帳號、不修改實際配置，也不發起模型推理。`tests/ov-contract.py` 可在倉庫 Python 環境中讀取標準輸入的臨時配置，檢查真實 OV 與 Bot 配置解析。



## 配置檔案與狀態說明

| 檔案或狀態 | 含義 |
| --- | --- |
| `selection.json` | Magpie 寫入的模型選擇，由外掛橋接程式讀取；OpenViking 本身不讀取它。包含閘道器 Key，不要公開分享 |
| `adapter.json` | 外掛連線和行為配置；Magpie Options 的同名欄位優先 |
| `state.json` | 原配置與恢復記錄，可能包含憑據；恢復完成前不要刪除 |
| `status.json` | 外掛最近一次同步或生效檢查結果 |
| `saved.json` | 外掛儲存目標、完整配置指紋及確認版本；用於限定自動重啟範圍 |
| `activation.json` | 重啟請求與驗證記錄，用於避免重複重啟 |
| `paused.json` | 手動恢復後的暫停標記，防止立刻再次接管 |
| `saved` | 實際服務配置已儲存，仍需檢查重啟狀態 |
| `applied` | 外掛已完成生效檢查；同時核對 `ovRuntime`、`botRuntime`、`restartRequired` |
| `external_restart_required` | 外掛之外的配置修改待重啟；不會自動應用這些修改 |
| `conflict` / `apply_failed` | 存在手動修改衝突或重啟失敗，需要處理後再繼續 |

以上外掛檔案預設位於 `~/.config/magpie-openviking-models/`。實際流程為：Magpie 寫入 `selection.json`，橋接程式呼叫 API 更新服務真正使用的 `ov.conf`，再按設定重啟並驗證。Magpie 行上的“已接入”只表示其接管配置已寫入，不代表 OV 已經切換模型。

自動重啟僅應用外掛自己儲存的版本，發起重啟前還會再次核對伺服器、配置檔案及版本歸屬。外部修改的待重啟狀態單獨提示；儲存響應丟失時，通過完整配置指紋確認歸屬。非獨立模式會忽略保留在介面選項中的 Bot 模型 ID；獨立模式留空則使用 Agent 選擇。

## 常見問題

| 現象 | 處理方式 |
| --- | --- |
| `root_authentication_required` / `root_permission_required` | 核對當前 CLI 配置的 Root Key 或 `rootApiKeyFile`，普通記憶訪問 Key 不具備模型管理許可權 |
| `bot_not_enabled_or_detected` | Bot 未啟用或未檢測到；選擇保留 Bot 配置，或先按原部署方式啟用 Bot |
| `runtime_query_override` | 存在 Cluster Query Planner 執行覆蓋；先明確實際配置來源 |
| `runtime_vlm_override` | 存在 Cluster VLM 執行覆蓋；先明確實際配置來源，不能僅靠修改啟動檔案判斷生效 |
| `adapter_locked` | 其他同步或重啟正在持鎖。若程序在過期鎖回收期間崩潰，先停用介面卡及 CLI，檢查 `adapter.lock.reclaim` 中的 PID；確認該程序已退出後才移除回收鎖，保留恢復記錄 |
| `server_restart_unsupported` | 當前啟動方式不支援重啟 API，使用原來的 systemd / Docker / 程序管理方式重啟 |
| `saved` 後模型看起來沒變化 | 檢查 `restartRequired` 並完成重啟；確認沒有 Account 覆蓋，也沒有連線到另一臺 OV |
| 介面顯示已接入，但仍不確定是否生效 | 檢視外掛日誌，執行 `node cli.mjs doctor` 和 `node cli.mjs status`；不要把 Magpie 的接入標記當作最終狀態 |

## 無重啟介面的範圍

`PATCH /api/v1/admin/accounts/{account_id}/configuration` 可熱更新 Account VLM，後續模型呼叫使用新例項；這不等於熱更新根啟動配置，也不會更新已啟動 VikingBot 的模型例項。當前外掛管理根 `ov.conf`，因此採用儲存後重啟；不會悄悄給某個 Account 新增覆蓋來代替根配置修改。

## 安裝與重啟能力檢測

Agent 行通過 `openviking-server` 命令或 OV 配置目錄發現安裝。`node cli.mjs doctor` 分別報告 PATH 中是否有服務 CLI、當前連線能否通過 Root 配置鑑權、服務是否支援重啟 API，以及 Bot 是否已啟用。本機沒有服務 CLI 不影響連線遠端 OV。

當前 `openviking-server` 提供啟動引數，沒有 `restart` 子命令；再次執行會嘗試啟動另一個服務。因此外掛優先呼叫當前例項公開的重啟 API，保留原 Python 環境、CLI 引數和 `--with-bot` 狀態。例項不支援該 API 時明確報告不支援，交由原來的 systemd / Docker / 程序管理器重啟，不猜測程序並殺掉，也不會新增 Bot 啟動引數。
