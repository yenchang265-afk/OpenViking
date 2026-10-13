# 安裝與使用 CLI

`ov` 是 OpenViking 的命令列客戶端。OpenViking 把 Agent 的上下文存成一個檔案系統：資源、記憶和技能都是 `viking://` 下的目錄和檔案。用 `ov` 可以瀏覽、讀取、檢索和寫入這些內容。Agent 也用同樣的命令操作這些內容。

`ov` 連線一個已有的 OpenViking 服務。還沒有服務時，先完成[快速開始](02-quickstart.md)的第 1 步。

## 讓 Agent 配置

點選下方的**複製**，把提示詞貼上給你使用的程式設計 Agent，例如 Claude Code、Codex 或 Cursor。Agent 會安裝 `ov`，向你確認要連線的服務，然後儲存配置並檢查連線。

<AgentPrompt>

````markdown
# openviking-cli

> `ov` 是 OpenViking 的命令列客戶端。OpenViking 是面向 AI Agent 的上下文資料庫。`ov` 連線已有的 OpenViking 服務端，或連線火山引擎上的 OpenViking 服務。

我希望你為我安裝並配置 OpenViking CLI（`ov`）。自主執行下面的全部步驟。只在步驟標註 ASK 的地方停下來問我。

OBJECTIVE：安裝 `ov`，為我的 OpenViking 服務儲存一個命名配置，並把它設為當前配置。

DONE WHEN：`ov config validate` 的檢查項全部通過（配置檔案有效、伺服器可連線、認證已通過、健康），並且 `ov health -o json` 返回 `"healthy": true`。

## TODO

- [ ] 安裝 `ov` 並設定顯示語言
- [ ] 確認要連線的服務
- [ ] 儲存並激活命名配置
- [ ] 驗證連線

## 規則

- 你不能猜測連線目標。已有配置、本地檔案、開放埠和正在執行的服務都不代表我的同意。
- 切換、替換或刪除配置，探測或啟動本地服務，或寫入資料之前，你必須先 ASK 我。
- API Key 不能出現在命令文本、shell 歷史、日誌、記憶或打印出的配置檔案中。只能通過 stdin 或已經存在的環境變數傳入 key。
- 如果你無法用這兩種方式傳入 key，ASK 我自己執行 `ov config` 並輸入 key。
- 執行 `ov config add` 時必須傳 `--name`，這樣重試會更新同一個配置。
- `ov config add|edit|list|switch|delete` 必須加 `-o json`。根據退出碼和 `error.code` 判斷結果，不要解析說明文字。
- 如果本機 `ov --help` 與本文不一致，以本機幫助為準，並告訴我差異。

## 第 1 步：安裝 ov

需要 Node.js 和 npm。

```bash
command -v ov || npm i -g @openviking/cli
ov language zh-CN
ov --version
```

如果我用英文和你交流，改用 `ov language en`。未儲存顯示語言時，大多數 `ov` 命令在非互動式 shell 中以退出碼 2 退出。

安裝後仍找不到 `ov` 時，把 `$(npm prefix -g)/bin` 加入 `PATH`。不要使用 `sudo npm`。沒有 npm 時，先 ASK 我，再用 `cargo install --git https://github.com/volcengine/OpenViking ov_cli` 從原始碼構建。

檢視要用到的命令幫助：

```bash
ov config add ov-service --help
ov config add custom --help
```

## 第 2 步：確認連線目標

執行 `ov config list -o json`。如果已有配置與目標一致，先 ASK 我，再用 `ov config switch <NAME> -o json` 啟用它。

否則，除非我已經說明，ASK 我要連線哪種目標：

| 目標 | 服務地址 | API Key |
|---|---|---|
| OpenViking 服務（火山引擎雲） | 固定地址，不要傳 `--url`。 | 必填。我在[控制台](https://console.volcengine.com/vikingdb/openviking/region:openviking+cn-beijing)的“使用者管理 → API Key”中獲取。 |
| 遠端自建服務 | ASK 我。 | ASK 我。 |
| 本機自建服務 | `http://127.0.0.1:1933` | 通常不需要。 |

只有目標是本機自建服務時，才檢查服務是否執行：`curl -fsS http://127.0.0.1:1933/health`。檢查失敗時，ASK 我啟動服務端。參見 https://docs.openviking.ai/zh/guides/03-deployment 。

除非我的管理員提供了 `--account` 和 `--user` 的值，否則不要詢問這兩項。

## 第 3 步：儲存並激活配置

把 `<NAME>`、`<URL>` 和 `<ENV_VAR>` 替換為確認過的值，不保留尖括號。`$OV_API_KEY` 表示可信的執行時金鑰來源，不是字面量 key。

OpenViking 服務：

```bash
printf '%s' "$OV_API_KEY" | ov config add ov-service --name <NAME> --api-key-stdin --activate -o json
```

使用 API Key 的遠端自建服務：

```bash
printf '%s' "$OV_API_KEY" | ov config add custom --name <NAME> --url <URL> --api-key-stdin --activate -o json
```

無鑑權的本機自建服務：

```bash
ov config add custom --name <NAME> --url http://127.0.0.1:1933 --activate -o json
```

特殊金鑰情況：

- key 已經在環境變數中時，用 `--api-key-env <ENV_VAR>` 代替 `--api-key-stdin`。
- 只有 root key，且服務端為 `trusted` 模式：使用 `--root-api-key-stdin --account <ACCOUNT> --user <USER>`。服務端為 `api_key` 模式時，root key 不能讀取資料，ASK 我提供 user 或 admin key。
- 同時有 user key 和 root key：使用 `--api-key-stdin --root-api-key-env <ENV_VAR>`。一條命令只有一個 stdin，所以第二個 key 必須來自已存在的環境變數。

`ov config` 子命令的退出碼：

| 退出碼 | 含義 | 你的操作 |
|---|---|---|
| `0` | 成功，或已經處於目標狀態 | 繼續。 |
| `2` | 輸入錯誤、缺少引數，或未設定顯示語言 | 修正輸入，或執行 `ov language <code>`。 |
| `3` | 同名配置已存在且內容不同 | 先 ASK 我，再加 `--force`。 |
| `4` | 服務端不可達，或配置校驗失敗 | ASK 我確認 URL，以及服務是否執行。 |
| `5` | 鑑權失敗，或 key 角色不匹配 | ASK 我確認 key 和 key 型別。 |
| `6` | 操作被拒絕，例如刪除當前配置 | ASK 我如何繼續。 |

不要用猜測的值重試。

## 第 4 步：驗證

```bash
ov config validate
ov health -o json
```

讀取輸出內容。退出碼為 0 不代表服務健康。檢視配置時使用 `ov config show`，它會隱藏金鑰。不要列印 `~/.openviking/ovcli.conf`。

除非我要求，不要匯入資料做演示。

配置完成後，我可能會讓你用 `ov` 瀏覽、檢索、新增或整理內容。OpenViking 的內容是 `viking://` 下的目錄樹。讀取時，先用 `ov abstract` 或 `ov overview` 讀目錄摘要，再用 `ov read` 讀需要的檔案。執行 `ov --help` 檢視命令分組。使用某條命令前，先執行 `ov <命令> --help`。

EXECUTE NOW：完成上面的 TODO 列表，達到：`ov config validate` 的檢查項全部通過，並且 `ov health -o json` 返回 `"healthy": true`。

需要更多上下文時，閱讀 https://docs.openviking.ai/llms.txt 。
````

</AgentPrompt>

下文是手動配置步驟。

## 準備

需要 Node.js 和 npm。

還需要連線資訊。連線資訊取決於服務型別：

| 服務型別 | 服務地址 | API Key |
|---|---|---|
| OpenViking 服務（火山引擎雲） | 固定地址，無需填寫。 | 必填。在 [OpenViking 控制台](https://console.volcengine.com/vikingdb/openviking/region:openviking+cn-beijing)的**使用者管理 → API Key** 中獲取。 |
| 遠端自建服務 | 向管理員獲取。 | 向管理員獲取。 |
| 本機自建服務 | `http://127.0.0.1:1933` | 預設配置不需要。 |

## 1. 安裝 `ov`

```bash
npm i -g @openviking/cli
ov language zh-CN
ov --version
```

`ov language` 設定顯示語言。英文介面使用 `en`。未設定語言時，大多數命令不能執行。

在執行 OpenViking 服務端的機器上，`ov` 已隨服務端安裝。跳過 `npm i`，只設置語言。

## 2. 新增連線

```bash
ov config
```

按提示操作：

1. 選擇**新增配置**。
2. 選擇服務型別。OpenViking 服務選擇 **OpenViking 服務（火山引擎雲）**；自建服務選擇**自定義**。
3. 輸入配置名稱。留空時，`ov` 自動生成名稱。
4. 按提示輸入服務地址和 API Key。
5. 校驗通過後，選擇**儲存並設為當前配置**。

## 3. 檢查連線

```bash
ov config validate
```

輸出的**檢查項**全部通過時，連線可用：配置檔案“有效”，伺服器“可連線”，認證“已通過”，健康狀態“健康”。

配置到此完成。接下來可以[匯入並檢索第一份文件](02-quickstart.md#_3-匯入文件)。想了解更多，可以繼續往下看。

## `ov` 能做什麼

OpenViking 的內容是一棵目錄樹。執行 `ov ls` 檢視根目錄 `viking://`：

- `viking://resources/`：匯入的文件、程式碼倉庫和網頁。同一帳號內共享。
- `viking://user/<使用者 ID>/`：你的記憶、私有資源、技能和會話。`viking://~/` 指向這個目錄。
- `viking://agent/`：同一帳號內共享的技能和 Agent 配置。

每個目錄有 L0 摘要和 L1 概覽。檔案全文是 L2。先讀目錄的 L0 和 L1，判斷內容是否相關，再讀需要的 L2 檔案。詳見 [Viking URI](../concepts/04-viking-uri.md) 和[上下文層級](../concepts/03-context-layers.md)。

| 任務 | 命令 |
|---|---|
| 瀏覽目錄 | `ov ls`、`ov tree`、`ov stat`。`ov tui` 開啟互動式瀏覽介面。 |
| 按層讀取 | `ov abstract`（L0）、`ov overview`（L1）、`ov read`（L2）。`ov get` 把檔案下載到本地。 |
| 檢索 | `ov find`（語義檢索）、`ov grep`（匹配內容）、`ov glob`（匹配路徑） |
| 匯入資料和技能 | `ov add-resource`、`ov add-skill`、`ov skills` |
| 寫入和整理 | `ov write`、`ov mkdir`、`ov mv`、`ov cp`、`ov rm` |
| 從對話中提取記憶 | `ov session new`、`ov session add-message`、`ov session commit`。`ov add-memory` 一步完成這三步。 |
| 等待後臺處理 | `ov task list`、`ov task status`、`ov wait` |
| 儲存和回滾版本 | `ov snapshot` |
| 備份與遷移 | `ov export`、`ov import`、`ov backup`、`ov restore` |
| 重建索引（`viking://resources` 需要 admin key） | `ov reindex` |
| 管理使用者（需要 admin 或 root key） | `ov admin list-users`、`ov admin register-user`、`ov admin regenerate-key` |
| 檢查服務 | `ov health`、`ov status` |

匯入資料和提交會話後，服務端在後臺處理：解析內容，提取記憶，生成 L0 和 L1，建立索引。處理完成前，`ov find` 檢索不到新內容。

用 `ov <命令> --help` 檢視命令的引數。這些操作也可以直接交給 Agent 完成。

::: warning 注意
`ov rm -r` 會刪除目錄及其中的全部內容。刪除在服務端執行，使用同一服務的其他 Agent 也會失去這些內容。刪除前，先用 `ov ls` 確認 URI。
:::

## 管理多個連線

```bash
ov config list     # 列出已儲存的配置
ov config switch   # 選擇當前配置
ov config show     # 檢視當前配置，金鑰會被隱藏
```

編輯或刪除配置時，執行 `ov config` 並選擇對應操作。在指令碼中新增配置時，使用 `ov config add`，引數見 `ov config add --help`。

當前配置是 `~/.openviking/ovcli.conf`。每個已儲存的配置是 `~/.openviking/ovcli.conf.<名稱>`。設定 `OPENVIKING_CLI_CONFIG_FILE` 後，`ov` 改用該檔案作為當前配置，已儲存的配置位於該檔案所在目錄。全部欄位見[客戶端配置](../configuration/02-client.md)。

## API Key

服務使用 API Key 認證時，key 有三種角色：

- **User key**：用於資料命令，例如 `ov add-resource` 和 `ov find`。大多數使用者只需要這種 key。
- **Admin key**：可以執行資料命令，也可以管理本帳號的使用者。
- **Root key**：管理整個服務，例如建立帳號。在 `api_key` 模式下，root key 不能讀寫帳號資料。

一個配置可以同時儲存 user key 和 root key。普通命令使用 user key。`ov admin`、`ov system`、`ov reindex`、`ov task status` 和 `ov task list` 加 `--sudo` 時使用 root key。詳見[認證](../guides/04-authentication.md)。

保護 API Key：

- 在 `ov config` 的輸入框中輸入 key。不要把 key 寫進命令，shell 歷史會儲存命令。
- 用 `ov config show` 檢視配置，它會隱藏金鑰。不要分享 `~/.openviking/ovcli.conf` 的內容或截圖。
- 演示和試用時，使用可以撤銷的臨時 key。
- 讓 Agent 配置時，不要把 key 貼上到對話中。把 key 放進環境變數，或在 Agent 請求時自己執行 `ov config` 輸入 key。

## 常見問題

### 找不到 `ov`

開啟一個新終端。仍然找不到時，把 npm 全域 binary 目錄加入 `PATH`。在 macOS 和 Linux 上，該目錄通常是 `$(npm prefix -g)/bin`。

### npm 報許可權錯誤

按你平時管理 Node.js 的方式修復許可權，例如使用 nvm。除非你一直用 sudo 管理全域包，否則不要執行 `sudo npm i -g`。

### 命令提示需要顯示語言

執行 `ov language zh-CN` 或 `ov language en`，然後重新執行命令。

### 本機服務沒有響應

檢查服務：

```bash
curl http://127.0.0.1:1933/health
```

檢查失敗時，先啟動服務端。參見[部署](../guides/03-deployment.md)。

### API Key 校驗失敗

執行 `ov config`，選擇**編輯配置**，重新輸入 key。OpenViking 服務的 key 從控制台複製。自建服務的 key 和 key 型別向管理員確認。在 `api_key` 模式下，資料命令需要 user key 或 admin key。

### 當前配置不對

執行 `ov config list` 檢視當前配置。執行 `ov config switch` 選擇其他配置。

## 下一步

- 匯入並檢索第一份文件：[快速開始](02-quickstart.md)。
- 把 OpenViking 接入你日常使用的 Agent：[Agent 接入方式](../agent-integrations/01-overview.md)。
