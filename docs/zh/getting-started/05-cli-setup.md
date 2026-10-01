# OpenViking CLI 配置指南

本文介紹如何安裝 OpenViking CLI、完成配置，並驗證它可以連線到 OpenViking。

`ov` 是客戶端 CLI。它連線到已經存在的 OpenViking 服務端，或連線到 OpenViking Service（火山引擎雲）。它不是服務端安裝命令。如果你還沒有安裝或啟動自定義 OpenViking 服務端，請先閱讀[快速開始](02-quickstart.md)。

你可以用兩種方式閱讀本文：

- 如果你自己手動配置 `ov`，請閱讀[手動配置](#手動配置)。
- 如果你讓 Agent 幫你配置，請把本文發給 Agent，並讓它閱讀 [Agent 輔助配置](#agent-輔助配置)。

CLI 會持續演進。請把 `ov --help` 和 `ov <command> --help` 作為當前安裝版本的命令準確資訊來源。

## 本文配置什麼

CLI 使用 `~/.openviking/ovcli.conf` 作為 active 客戶端連線配置。

建立命名配置時，`ov` 會把配置儲存為 `~/.openviking/ovcli.conf.<name>`。切換配置時，`ov` 會把選中的已儲存配置複製到 `~/.openviking/ovcli.conf`。

`ov config` 是面向人的互動式配置管理器，可以新增、編輯、刪除、校驗和切換配置。

`ov config add`、`ov config edit`、`ov config list`、`ov config switch <name>` 和 `ov config delete` 是面向指令碼和 Agent 的確定性命令。

## 選擇連線目標

執行配置命令前，先選擇要連線的 OpenViking 目標。

除非使用者已經明確說明，Agent 應先詢問使用者要連線哪種目標。已有配置、active 配置、本地檔案、預設埠和正在執行的服務可以幫助 Agent 追問細節，但不代表使用者同意 Agent 選擇目標、切換或替換配置、探測本地服務、啟動服務端，或寫入資料。

### OpenViking Service（火山引擎雲）

如果你希望使用火山引擎雲上的 OpenViking 託管服務，選擇此項。

- `ov` 使用的服務端端點：`https://api.vikingdb.cn-beijing.volces.com/openviking`
- 管理 API Key 的控制台頁面：https://console.volcengine.com/vikingdb/openviking/region:openviking+cn-beijing
- 在控制台進入 User Management → API Key，檢視並複製你的 key。
- API Key 必填。
- 標準配置只需要 API Key。除非使用者的管理員明確提供身份覆蓋值，否則不要詢問 `--account` 或 `--user`。

### 遠端自定義

如果你要連線不在當前機器上的自定義 OpenViking 服務端，選擇此項。

- 服務端 URL 由使用者或服務端管理員提供。
- 可能需要 API Key。
- 僅用 root key 訪問資料需要服務端採用 `trusted` 模式，並顯式配置 `--account` 和 `--user`；`api_key` 模式的資料訪問需要 user/admin key。

### 本地自定義

只有當用戶要連線當前機器上的自定義 OpenViking 服務端時，才選擇此項。

- 本地預設 URL：`http://127.0.0.1:1933`
- 本地無鑑權服務通常不需要 API Key。
- 除非使用者選擇本地自定義配置，否則 Agent 不應探測本地埠、curl 本地 health endpoint，或執行啟動服務端的命令。

> **注意：** 最近的 CLI 版本（v0.3.23+）要求在執行大多數命令前先儲存一個顯示語言。在互動式終端中，CLI 會在首次使用時提示你選擇；在非互動式 shell（Agent 或 CI）中，任何非豁免命令都會以 `2` 退出，直到你執行 `ov language en` 或 `ov language zh-CN`。只有 `ov language`/`ov lang`、`ov config add|edit|delete|list` 和 `ov config switch <name>` 是豁免的，因此請在下面的 `ov config validate`、`ov health` 和 `ov status` 檢查之前先執行 `ov language <code>`。

## 開始前

你需要準備：

- 一種安裝 CLI 的方式：
  - 使用 Node.js 和 npm 安裝獨立的 `@openviking/cli` 包，或
  - 使用 Python 工具安裝完整的 `openviking` 包。
- 一個可訪問的 OpenViking 目標：
  - OpenViking Service（火山引擎雲），或
  - 自定義 OpenViking 服務端。
- 如果目標需要鑑權，需要準備 API Key。

API Key 是敏感憑證。手動配置時優先通過 `ov config` 的互動式輸入框輸入。只有當你明確相信當前渠道時，才把 API Key 提供給 Agent。Agent 應通過 stdin 傳入 key，不能把 key 寫進 shell 命令、日誌、長期記憶或原始配置輸出。只有當 key 已經存在於當前 shell 環境變數中時，才使用環境變數。

## 安裝 `ov`

先檢查是否已經安裝：

```bash
command -v ov
ov --version
```

如果 `ov --version` 或任何其他 `ov` 命令提示 OpenViking 需要顯示語言，請先選擇語言再重試：

```bash
ov language en
# 或
ov language zh-CN
```

安裝或升級 npm 包：

```bash
npm i -g @openviking/cli
```

也可以從原始碼構建 Rust CLI：

```bash
cargo install --git https://github.com/volcengine/OpenViking ov_cli
```

npm 包是最輕量的獨立 CLI 安裝方式。Python SDK 是獨立的包——只在有 Python 程式碼要 import 的地方安裝 `openviking-sdk`，它不提供 `ov` 命令。如果這臺機器本身跑服務端（`uv tool install openviking`），該安裝自帶 `ov`，無需再裝 CLI。

驗證：

```bash
ov --help
```

如果仍然找不到 `ov`，關閉並重新開啟 shell，或檢查 npm 全域 prefix：

```bash
npm prefix -g
```

在 macOS 和 Linux 上，全域 npm binary 目錄通常是 `$(npm prefix -g)/bin`。確認該目錄已經加入 `PATH`。

## 金鑰型別

OpenViking CLI 配置可以包含 user key、root key，或同時包含兩者。

- User key：用於普通資料命令，例如 `ov add-resource`、`ov find` 和 `ov tree`。服務端會從 key 推導身份，所以通常不需要傳 `--account` 或 `--user`。這是大多數使用者需要的方式。
- Root key：用於管理操作和需要 `--sudo` 的命令。`api_key` 模式下，即使傳入 `--account` 和 `--user`，root key 也不能訪問租戶資料。只有 `trusted` 服務端接受 root key 認證的資料請求通過這些 header 指定身份。
- User key + root key：適合一個配置同時支援日常資料操作和偶爾的管理操作。普通命令使用 user key，`--sudo` 命令使用 root key，並帶上配置中的 account 和 user。

## 手動配置

如果你正在閱讀本文，並準備自己配置 `ov`，使用這個路徑。

執行：

```bash
ov config
```

然後選擇：

1. `Add config`
2. `OpenViking Service（火山引擎雲）` 或 `自定義`
3. 配置名稱，或留空自動生成
4. 上面選擇的目標所需的 URL 和 API Key
5. 校驗成功後儲存配置

如果你維護多個 OpenViking 目標，之後可以使用：

```bash
ov config switch
```

切換 active 配置。

配置完成後，繼續閱讀[驗證配置](#驗證配置)。

## Agent 輔助配置

如果 Agent 正在替使用者配置 `ov`，使用這個路徑。Agent 應該閱讀整篇文件。當確定性命令不適合使用者環境時，上面的手動配置流程就是回退路徑。

### Agent 檢查清單

1. 除非使用者已經明確說明，先詢問使用者要連線哪種目標：OpenViking Service（火山引擎雲）、遠端自定義，還是本地自定義。
2. 不要根據已有配置、active 配置、本地檔案、預設埠或正在執行的服務推斷使用者想要的 setup。
3. 切換配置、替換配置、探測本地服務、啟動服務端或寫入資料前，都要先詢問使用者。
4. 在選擇命令前，執行 `ov --help`、`ov config --help` 和相關 config 子命令的幫助。
5. 如果你具備長期記憶能力，並且使用者允許，可以記錄當前 `ov --help` 命令面的簡要摘要。不要記錄 API Key 或其他金鑰。
6. 當必需資訊明確時，使用非互動式 `ov config` 命令。
7. Agent 配置時始終傳 `--name`，這樣重試會命中同一個 saved config。
8. 如果 Agent 已經通過可信渠道拿到 API Key，使用 `--api-key-stdin` 或 `--root-api-key-stdin`，並且只把 key 內容寫入 stdin。只有當環境變數已經存在時，才使用 `--api-key-env` 或 `--root-api-key-env`。不要要求使用者額外開啟一個 shell 只為了給 Agent export 一個 key。
9. 使用 `-o json`，並根據 JSON 結果和程序退出碼分支處理。
10. 使用 `ov config validate` 校驗 active 配置，然後執行 `ov health` 和 `ov status`。
11. 如果非互動式配置因為資訊缺失、鑑權不明確或終端輸入更安全而失敗，請引導使用者使用 `ov config` 互動式嚮導。

### 檢視當前安裝的 CLI

執行：

```bash
ov --help
ov config --help
ov config add --help
ov config add ov-service --help
ov config add custom --help
ov config edit --help
```

以當前安裝版本的 CLI 幫助為準。如果本文與本地幫助不一致，請遵循本地幫助，並告訴使用者差異是什麼。

如果 help 命令提示 OpenViking 需要顯示語言，請執行 `ov language en`；如果使用者希望使用中文，則執行 `ov language zh-CN`，然後重試。`ov config add`、`ov config list`、`ov config edit`、`ov config switch <name>` 和 `ov config delete` 等非互動式 config 子命令可以在設定顯示語言前執行。

### 使用穩定名稱便於重試

Agent 建立配置時始終傳 `--name`。如果省略名稱，`ov` 會隨機生成名稱；重試時可能建立第二個 saved config，而不是更新預期的配置。

當傳入相同 `--name` 且配置內容完全一致時，`ov config add` 可以安全重複執行。它會以 `0` 退出，`--activate` 也會再次把該 saved config 設為 active。如果同名配置已經存在但內容不同，命令會以 `3` 退出，並要求只有在確認替換時才使用 `--force`。

下面示例中的 `<CONFIG-NAME>` 和 `<REMOTE-OPENVIKING-URL>` 等佔位符需要替換成使用者確認過的值再執行。執行時不要保留尖括號。

### 讀取結果

對非互動式 config 命令使用 `-o json` 時，成功結果會輸出到 stdout：

```json
{"status":"ok","result":{"action":"add","name":"<CONFIG-NAME>"}}
```

`result` 物件會隨子命令變化。`add` 和 `edit` 還會包含 `kind`、`url`、`saved_path`、`active_path`、`activated` 和 `validation` 等欄位，因此 Agent 不應該假設結果裡只有 `action` 和 `name`。

錯誤結果會輸出到 stderr：

```json
{"status":"error","error":{"code":"bad_input","message":"..."}}
```

Agent 應該根據程序退出碼和 JSON 中的 `error.code` 分支處理，不要解析面向人的說明文字。

| 退出碼 | 含義 |
|--------|------|
| `0` | 成功，或已經處於目標狀態 |
| `2` | 輸入錯誤、缺少引數、名稱非法、無法讀取金鑰來源，或在非互動式 shell 中尚未選擇顯示語言（請先執行 `ov language <code>`） |
| `3` | 同名配置已經存在但內容不同；只有確認要替換時才傳 `--force` |
| `4` | 服務端不可達，或配置校驗失敗 |
| `5` | 鑑權或 key 角色不匹配，例如把 root key 傳到了需要 user key 的位置 |
| `6` | 操作被拒絕，例如刪除 active 配置 |

### 列出已有配置

```bash
ov config list -o json
```

列表輸出形狀如下：

```json
{"status":"ok","result":[{"name":"<CONFIG-NAME>","kind":"OpenViking Service","url":"https://api.vikingdb.cn-beijing.volces.com/openviking","active":true}]}
```

做存在性檢查時，讀取 `result[].name`。判斷是否還需要切換 active config 時，讀取匹配項的 `active` 標記。

如果已經存在合適的 saved config，可以按名稱啟用：

```bash
ov config switch <CONFIG-NAME> -o json
```

然後執行驗證命令。

### 添加 OpenViking Service

如果 Agent 已經通過可信渠道拿到 API Key，執行：

```bash
ov config add ov-service --name <CONFIG-NAME> --api-key-stdin --activate -o json
```

shell pipe 形式如下：

```bash
printf '%s' "$API_KEY" | ov config add ov-service --name <CONFIG-NAME> --api-key-stdin --activate -o json
```

`$API_KEY` 表示可信的執行時金鑰來源，不是字面量 key。Agent 能在不把 key 寫進命令文本、shell history、日誌或長期 export 的環境變數時提供 key，就應使用 stdin。

只把 API Key 內容寫入 stdin，不要把 key 放進 shell 命令本身。這會寫入一個 OpenViking Service 配置，並使用固定端點：`https://api.vikingdb.cn-beijing.volces.com/openviking`。`ov-service` 目標不接受自定義服務端 URL。

只有當環境變數已經存在時，才使用環境變數：

```bash
ov config add ov-service --name <CONFIG-NAME> --api-key-env <API-KEY-ENV-VAR> --activate -o json
```

標準 OpenViking Service 配置不要傳 `--account` 或 `--user`。只有當用戶或 OpenViking 管理員提供身份覆蓋值時，才使用它們。

### 新增本地自定義服務

只有當用戶選擇本地自定義時，才使用這個路徑。

對於本地無鑑權服務：

```bash
ov config add custom --name <CONFIG-NAME> --url http://127.0.0.1:1933 --activate -o json
```

如果本地服務沒有執行，請先引導使用者啟動服務端。參見[部署指南](../guides/03-deployment.md)。

### 新增遠端自定義服務

對於使用普通 API Key 的遠端自定義服務：

```bash
ov config add custom --name <CONFIG-NAME> --url <REMOTE-OPENVIKING-URL> --api-key-stdin --activate -o json
```

stdin pipe 形式如下：

```bash
printf '%s' "$API_KEY" | ov config add custom --name <CONFIG-NAME> --url <REMOTE-OPENVIKING-URL> --api-key-stdin --activate -o json
```

把 API Key 寫入 stdin。如果 key 已經存在於當前 shell 環境變數中，可以改用 `--api-key-env <API-KEY-ENV-VAR>`。

對於 `trusted` 模式的自建服務，僅配置 root key 時還需提供目標 account 和 user。若服務端採用 `api_key` 模式，普通資料命令應改用 user/admin key：

```bash
ov config add custom --name <CONFIG-NAME> --url <REMOTE-OPENVIKING-URL> --root-api-key-stdin --account <ACCOUNT-ID> --user <USER-ID> --activate -o json
```

把 trusted 部署的 root API key 寫入 stdin；account 和 user 用於指定 trusted 資料請求的呼叫者身份。

如果使用者同時擁有 user key 和 root key，可以把兩者放在同一個配置裡：

```bash
ov config add custom --name <CONFIG-NAME> --url <REMOTE-OPENVIKING-URL> --api-key-stdin --root-api-key-env <ROOT-API-KEY-ENV-VAR> --account <ACCOUNT-ID> --user <USER-ID> --activate -o json
```

這樣普通命令使用 user key，需要 `--sudo` 的命令使用 root key。因為一個命令只有一個 stdin 流，第二個 key 必須來自已經存在的環境變數。如果兩個 key 都不在環境變數中，請使用 `ov config` 並引導使用者完成互動式流程。

### 編輯或替換配置

先列出配置：

```bash
ov config list -o json
```

重新命名並激活 saved config：

```bash
ov config edit <CONFIG-NAME> --new-name <NEW-CONFIG-NAME> --activate -o json
```

替換 API Key：

```bash
ov config edit <CONFIG-NAME> --api-key-stdin --activate -o json
```

把新的 API Key 寫入 stdin。

替換自定義服務 URL：

```bash
ov config edit <CONFIG-NAME> --url <CUSTOM-OPENVIKING-URL> --activate -o json
```

只有在你明確要覆蓋已有 saved config 名稱時，才使用 `--force`。

### 刪除 saved config

只刪除非 active 的 saved config：

```bash
ov config delete <OLD-CONFIG-NAME> -o json
```

如果該配置正處於 active 狀態，先切換到另一個配置：

```bash
ov config switch <CONFIG-NAME> -o json
ov config delete <OLD-CONFIG-NAME> -o json
```

## 驗證配置

執行：

```bash
ov config show
ov config list -o json
ov config validate
ov health
ov status
```

檢查配置時優先使用 `ov config show`，因為它會隱藏金鑰。

除非你理解配置檔案可能包含金鑰，否則不要列印原始配置檔案。

如果驗證命令提示 OpenViking 需要顯示語言，請執行 `ov language en`；如果使用者希望使用中文，則執行 `ov language zh-CN`，然後重新驗證。

`ov status` 包含更寬泛的服務端和資料診斷。如果 `ov config validate` 和 `ov health` 通過，`ov status` 中的 warning 不一定代表 CLI 配置失敗。

## 學習其他 CLI 命令

配置成功後，用內建幫助繼續瞭解 `ov` 的其他能力：

```bash
ov --help
ov config --help
ov add-resource --help
```

Agent 在執行不熟悉的命令前，應該重新檢視幫助。如果 Agent 為使用者維護長期記憶，並且使用者允許，可以記錄當前命令面的簡要摘要，方便之後繼續工作。不要記錄金鑰、原始配置檔案或私有服務詳情，除非使用者明確要求。

## 憑證安全

- API Key 可能允許訪問你的 OpenViking 資料。
- 手動配置時，優先使用 `ov config` 的互動式輸入框。
- Agent 輔助配置時，只有通過你明確相信的渠道提供 API Key。
- Agent 應通過 stdin 傳入 key。只有當環境變數已經存在於當前 shell 中時，才使用環境變數。
- 不要把 API Key 直接寫進可能被 shell history 儲存的命令。
- 不要打印原始 `~/.openviking/ovcli.conf`。
- 不要分享包含 API Key 的截圖。
- 演示和試用建議使用臨時或可撤銷的 key。

## 常見問題

### 找不到 `ov`

執行：

```bash
npm i -g @openviking/cli
npm prefix -g
```

然後重新開啟 shell，或把 npm 全域 binary 目錄加入 `PATH`。在 macOS 和 Linux 上，該目錄通常是 `$(npm prefix -g)/bin`。

### npm 全域安裝失敗

如果 npm 報許可權錯誤，請按你平時管理 Node.js 的方式處理。除非你本來就用 sudo 管理全域 npm 包，否則不要直接執行 `sudo npm i -g`。

### 本地服務端沒有執行

只有當用戶選擇本地自定義時才使用此項。先驗證服務端：

```bash
curl http://127.0.0.1:1933/health
```

如果失敗，先啟動服務端再配置 `ov`。參見[部署指南](../guides/03-deployment.md)。

### API Key 校驗失敗

重新執行 `ov config` 並編輯配置。對於 OpenViking Service，確認 API Key 來自上面的 OpenViking 控制台地址。對於自定義服務，確認服務端是否要求鑑權。

Agent 不應該反覆重試未知 key。請讓使用者確認目標型別、服務端 URL、key 型別、account 和 user。

### active 配置不對

檢查並切換：

```bash
ov config show
ov config list
ov config switch
ov config validate
```

Agent 可以按名稱切換：

```bash
ov config list -o json
ov config switch <CONFIG-NAME> -o json
```

### 非互動式配置不適合當前情況

使用互動式嚮導：

```bash
ov config
```

當金鑰應由使用者直接在終端輸入、連線目標不明確，或校驗結果需要人工判斷時，這是合適的回退路徑。

### 舊配置命令

使用 `ov config`。不要使用舊的或已移除的配置命令，例如 `ov config setup-cli`。

## 下一步

CLI 配置完成後，使用 `ov --help` 和 `ov <command> --help` 繼續瞭解其他命令。

新增資源會把資料寫入 active OpenViking 服務端。如果你想做一個小演示，請選擇你願意存入服務端的資源。Agent 執行這類演示命令前，必須先徵得使用者同意。

```bash
ov add-resource https://github.com/volcengine/OpenViking
# 使用返回的 task_id 查詢狀態；completed 後再檢索
ov task status TASK_ID
ov find "what is OpenViking"
ov tree viking://resources/ -L 2
```

查看全部命令：

```bash
ov --help
ov config --help
ov add-resource --help
```

## 重建索引

`ov reindex <uri>` 用於重建已匯入內容的索引，支援三種模式：

- `--mode vectors_only` —— 只刷新向量。
- `--mode semantic_and_vectors` —— 先重新生成語義產物（`.abstract.md`、`.overview.md`），再重新整理向量。
- `--mode prune_orphans` —— 清理原始檔已不存在的向量記錄，加 `--dry-run` 可預覽而不實際執行。

`semantic_and_vectors` 預設遞迴處理整個子樹。對已經具有下級摘要、只需要重新生成目標目錄 `.abstract.md` / `.overview.md` 的場景，可新增 `--recursive=false`；此時僅重新整理目標目錄語義產物和該目錄的 L0/L1 向量。

沒有 `semantic` 或 `full` 這樣的模式別名。
