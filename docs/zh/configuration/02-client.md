# ovcli 配置

`ovcli.conf` 是 `ov` CLI 的客戶端配置檔案，用於儲存服務端連線、鑑權身份和命令預設行為。

Codex、Claude Code、OpenCode 等 Agent 外掛還會讀取各自的 `OPENVIKING_*` 環境變數，用於控制 Recall、Capture、除錯等行為；這些不屬於 `ovcli.conf`，請在對應的 [Agent 整合](../agent-integrations/01-overview.md)文件中配置。

建議使用 `ov config` 建立和維護配置；使用 `ov config show` 檢視脫敏後的當前配置。

預設路徑：

```text
~/.openviking/ovcli.conf
```

也可以指定其他文件：

```bash
export OPENVIKING_CLI_CONFIG_FILE=/path/to/ovcli.conf
```

## 完整示例

```json
{
  "url": "https://openviking.example.com",
  "api_key": "<user-or-admin-key>",
  "root_api_key": "<root-key>",
  "account": "acme",
  "user": "alice",
  "actor_peer_id": "agent:research-assistant",
  "timeout": 60,
  "output": "table",
  "echo_command": true,
  "show_progress": false,
  "verbose": false,
  "profile": false,
  "upload": {
    "ignore_dirs": "node_modules,.cache,dist",
    "include": "*.md,*.pdf",
    "exclude": "*.tmp,*.log"
  },
  "extra_headers": {
    "X-Tenant": "acme"
  },
  "gateway_token": "<gateway-token>"
}
```

不需要的字段可以省略。本地 `dev` 模式通常只需要 `url`。

## 連線與鑑權

```json
{
  "url": "https://openviking.example.com",
  "api_key": "<user-or-admin-key>",
  "root_api_key": "<root-key>",
  "account": "acme",
  "user": "alice",
  "actor_peer_id": "agent:research-assistant",
  "extra_headers": {
    "X-Tenant": "acme"
  },
  "gateway_token": "<gateway-token>"
}
```

| 欄位 | 型別 / 可選值 | 預設值 | 作用 |
|---|---|---|---|
| `url` | HTTP(S) URL | `http://127.0.0.1:1933` | Business Data Platform 服務端地址 |
| `api_key` | string / `null` | `null` | 普通資料操作使用的 user/admin key |
| `root_api_key` | string / `null` | `null` | `ov --sudo` 管理操作使用的 root key |
| `account` | string / `null` | `null` | trusted 部署使用的帳號身份 |
| `user` | string / `null` | `null` | trusted 部署使用的使用者身份 |
| `actor_peer_id` | string / `null` | `null` | 預設 Actor Peer 標識 |
| `agent_id` | string / `null` | `null` | 相容欄位；新配置使用 `actor_peer_id`，兩者不能同時設定 |
| `extra_headers` | object / `null` | `null` | 每個 HTTP 請求附加的自定義請求頭；`extra_header` 是相容別名 |
| `gateway_token` | string / `null` | `null` | 閘道器挑戰重試時使用的 `X-Gateway-Token` |

### API Key 選擇

| 配置方式 | 普通命令 | `ov --sudo` |
|---|---|---|
| 僅 `api_key` | 使用 user/admin key | 不可用 |
| 僅 `root_api_key`，並配置 `account`、`user` | trusted 模式使用 root key 和顯式身份；api_key 模式禁止訪問租戶資料 | 使用 root key |
| 同時配置兩種 key | 使用 `api_key` | 使用 `root_api_key` |
| 兩種 key 都不配置 | 僅適用於未開啟鑑權的本地服務 | 不可用 |

`ov.conf` 中的 `server.root_api_key` 是服務端接受的憑證；CLI 管理該服務端時，`ovcli.conf` 中的 `root_api_key` 需要與其一致。

## 命令列為

```json
{
  "timeout": 120,
  "echo_command": true,
  "show_progress": true,
  "verbose": false,
  "profile": false
}
```

| 欄位 | 型別 / 可選值 | 預設值 | 作用 |
|---|---|---|---|
| `timeout` | number，秒，`> 0` | `60` | HTTP 請求超時 |
| `echo_command` | boolean | `true` | 是否顯示 `find`、`search`、`ls` 等命令的實際請求引數 |
| `show_progress` | boolean | `false` | 上傳時是否預設顯示進度 |
| `verbose` | boolean | `false` | 上傳時是否預設輸出診斷資訊 |
| `profile` | boolean | `false` | 是否請求效能 profile；服務端還需啟用 `server.profile_enabled` |
| `output` | `"table"` / `"json"` | `"table"` | 預設輸出格式；當前命令的 `-o table` 或 `-o json` 會覆蓋它 |

`--profile`、`--progress`、`--no-progress`、`--verbose` 等命令列引數會覆蓋本次命令的配置。

## 上傳過濾

```json
{
  "upload": {
    "ignore_dirs": "node_modules,.cache,dist",
    "include": "*.md,*.pdf",
    "exclude": "*.tmp,*.log"
  }
}
```

| 欄位 | 型別 / 格式 | 預設值 | 作用 |
|---|---|---|---|
| `upload.ignore_dirs` | 逗號分隔字串 / `null` | `null` | 忽略的目錄名 |
| `upload.include` | 逗號分隔 glob / `null` | `null` | 只上傳匹配的檔案 |
| `upload.exclude` | 逗號分隔 glob / `null` | `null` | 排除匹配的檔案 |

本地目錄上傳還會遵循 `.gitignore`。命令列 `--include`、`--exclude` 會與配置檔案中的規則合併。

## 插件配置

記憶外掛的行為旋鈕寫在 `plugin` 段下。直接掛在它下面的鍵對所有 harness 生效；以 harness 命名的巢狀物件（`claude_code` 或 `codex`）只覆蓋那一個。

```json
{
  "url": "https://openviking.example.com",
  "api_key": "<user 或 admin key>",
  "plugin": {
    "recallCompress": "off",
    "bypassSessionPatterns": ["/tmp/**", "**/scratch/**"],
    "claude_code": {
      "captureAssistantTurns": false
    }
  }
}
```

每個鍵都是某個 `OPENVIKING_*` 調優變數的 camelCase 對應寫法——`OPENVIKING_RECALL_LIMIT` 對應 `recallLimit`，`OPENVIKING_CAPTURE_ASSISTANT_TURNS` 對應 `captureAssistantTurns`。反過來不成立：少數變數刻意只認環境變數，比如一次性的 `OPENVIKING_BYPASS_SESSION`。完整列表在外掛 README 裡：[Claude Code](https://github.com/volcengine/OpenViking/blob/main/examples/claude-code-memory-plugin/README.md#configuration)、[Codex](https://github.com/volcengine/OpenViking/blob/main/examples/codex-memory-plugin/README.md#tuning-the-plugin)。取列表值的旋鈕（`bypassSessionPatterns`、`recallQueryFilters`、`captureFilters`）在這裡是 JSON 陣列，而它們的環境變數對應物是逗號分隔的字串，所以值裡帶字面逗號的只能寫進陣列。

優先順序從高到低：環境變數 → [工作區各層](#工作區配置) → `plugin.<harness>` → `plugin` → `ov.conf` 裡遺留的按 harness 分塊 → 內建預設值。hook 每次觸發都會重新讀檔案，所以改完下一輪就生效；改 `OPENVIKING_*` 變數則需要重啟 agent，因為 hook 繼承的是它的環境。

目前只有 Claude Code 和 Codex 外掛會讀這一段，用其它 harness 名字建的條目不會生效。`ov-memory-doctor` 會列印它解析到的結果，並對不認識的鍵給出告警和最接近的正確鍵名。

## 工作區配置

倉庫可以自帶外掛配置，這樣專案的記憶行為跟著程式碼走，而不是散落在每位協作者的 home 目錄裡。工作區根目錄下有兩個檔案，另有一層按機器儲存：

```text
<repo-root>/.openviking/config.json         # 提交到倉庫，團隊共享
<repo-root>/.openviking/config.local.json   # 私有，不提交
~/.openviking/workspaces/<slot>.json        # 本機登錄檔，每個工作區一個檔案
```

工作區根目錄是向上查詢時最先遇到的、包含 `.git` 或包含 `.openviking/config.json`（或 `config.local.json`）的目錄；`$HOME` 和檔案系統根目錄永遠不會被當作工作區根。兩者都沒有的目錄不是工作區：沒有配置層，沒有登錄檔條目，也沒有屬於自己的 peer。登錄檔的槽位名由根目錄名加上完整路徑的雜湊組成，因此同一臺機器上同一倉庫的兩個 clone 不會共用同一條記錄。這些層由 Claude Code 和 Codex 外掛讀取，`ov` 命令不讀取。

### 優先順序

從高到低：

| 層 | 生效範圍 |
|---|---|
| `OPENVIKING_*` 環境變數 | 當前程序 |
| `~/.openviking/workspaces/<slot>.json` | 本機的這個工作區 |
| `<repo-root>/.openviking/config.local.json` | 本地這份 checkout，私有 |
| `<repo-root>/.openviking/config.json` | 整個倉庫，隨程式碼提交 |
| `ovcli.conf` [`plugin.<harness>`](#外掛配置) | 本機的單個 harness |
| `ovcli.conf` `plugin` | 本機的所有 harness |
| `ov.conf` harness 段 | 舊部署的相容層 |
| 內建預設值 | |

標量由高優先順序的層直接覆蓋低優先順序的層；列表在各層之間取並集，首元素為 `"!reset"` 時會丟棄低層貢獻的全部條目，即 `["!reset", "*/scratch/*"]` 就是最終列表。

登錄檔檔案沒有任何命令會寫入。按 `ov-memory-doctor` 列印的路徑手工建立即可，寫上 `version: 1`，schema 與工作區檔案相同。

### Schema

必須寫 `version: 1`。宣告其他版本的檔案會被跳過並給出警告，而不是按猜測解析。

```json
{
  "version": 1,
  "peer": { "source": "git" },
  "recall": { "peer_scope": "actor", "max_items": 20 },
  "capture": { "commit_token_threshold": 20000 },
  "labels": { "team": "search" }
}
```

| 鍵 | 型別 / 可選值 | 作用 |
|---|---|---|
| `peer.source` | `"git"` / `"cwd"` / `"none"` / 模板 / 模板列表 | 工作區 peer 的推導方式；預設只有 git 倉庫才會有 peer |
| `peer.id` | string | 直接指定 peer，優先於 `peer.source` |
| `recall.enabled` | boolean | 是否啟用 Recall |
| `recall.peer_scope` | `"all"` / `"actor"` | `all` 會額外掃描該使用者的其他 peer 並對命中降分；`actor` 只讀使用者級記憶和本工作區的 peer |
| `recall.dedup_turns` | integer，`0`–`20` | 與最近多少輪對話去重 |
| `recall.max_items` | integer，`1`–`100` | Recall 結果條數上限 |
| `recall.score_threshold` | number，`0`–`1` | Recall 結果的最低分數 |
| `capture.enabled` | boolean | 是否啟用 Capture |
| `capture.commit_token_threshold` | integer，`1000`–`1000000` | 累計多少 token 後提交一次 Capture |
| `bypass.session_patterns` | glob 列表 | 會話 id 或工作目錄命中時跳過 Recall 與 Capture |
| `labels` | object | 給人看的自由後設資料，外掛不讀取 |

超出範圍的數值會被夾到最近的邊界並給出提示；無法識別的列舉值會被忽略。表中之外的鍵會保留在檔案裡但不生效。

### 工作區 peer

peer 是使用者空間下的一段路徑字首——`viking://user/<you>/peers/<peer>/memories`——把一個專案的記憶歸攏在一起。預設只有 git 倉庫會有 peer：優先用歸一化後的 `origin` URL，其次是倉庫根路徑。不在 git 倉庫中的目錄不傳送任何 peer，在那裡記下的內容進入使用者級空間 `viking://user/<you>/memories`。這是有意為之：每個任務新建一個目錄的應用，否則會為每個任務鑄造一個全新的空 peer。

規則由 `peer.source` 決定。同一項配置在環境變數中寫作 `OPENVIKING_PEER_SOURCE`，在 `ovcli.conf` 中寫作 `plugin.peerSource` 或 `plugin.<harness>.peerSource`。

#### 讓一個目錄擁有獨立記憶

在該目錄下建立 `.openviking/config.json`：

```json
{"version": 1, "peer": {"id": "my-project"}}
```

這個目錄及其下的一切從此寫入 peer `my-project`，是不是倉庫都一樣。這個 id 不含路徑，因此目錄移動、改名、換一臺機器都不會變；兩個目錄寫同一個 id 就共享同一份記憶，這正是合併它們的方式。

其餘寫法，優先順序從高到低：

| 寫在哪 | 作用 |
|---|---|
| `OPENVIKING_PEER_ID=my-project` | 為單個程序釘住 peer，無視配置檔案 |
| `.openviking/config.json` 的 `peer.id` | 指定本工作區的 peer。推薦做法；`config.local.json` 是同一個鍵，只是不提交 |
| 同一檔案的 `peer.source` | 不直接指定，而是推導——`"cwd"` 用目錄路徑，`"team-{dir}"` 用模板 |
| `ovcli.conf` 的 `plugin.peerSource`，或 `OPENVIKING_PEER_SOURCE` | 對本機所有目錄生效；`"cwd"` 可整體恢復 `git` 預設之前的行為 |

| `peer.source` | 含義 |
|---|---|
| `"git"` | 預設值。優先用歸一化後的 `origin` URL，其次是倉庫根路徑，等價於 `["{git_remote}", "{git_root}"]`；不在倉庫中則什麼都不傳送，也不新增任何字首 |
| `"cwd"` | 把工作目錄中所有非字母數字字元替換成 `-`，與舊版本傳送的值逐位元組一致 |
| `"none"` | 完全不傳送 peer；`OPENVIKING_WORKSPACE_PEER=0` 含義相同 |
| 模板 / 模板列表 | 例如 `"git-{git_remote}"` 或 `["{git_remote}", "team-{dir}"]`；按順序嘗試，某個模板的變數為空時落到下一個 |

| 變數 | 取值 | 何時為空 |
|---|---|---|
| `{git_remote}` | 歸一化後的 `origin`，形如 `github.com-org-repo` | 不在 git 倉庫中，或倉庫沒有 `origin` |
| `{git_root}` | 倉庫根路徑，所有非字母數字字元替換成 `-` | 不在 git 倉庫中。倉庫內某個子目錄放了 `.openviking/config.json` 時，它仍然是倉庫自己的根，因此標記子目錄不會拆散預設 peer |
| `{cwd}` | 工作目錄，所有非字母數字字元替換成 `-` | 從不為空——它也不在任何預設鏈裡，裸路徑只有在你明確要求時才會成為 peer |
| `{dir}` | 工作區根目錄的目錄名：倉庫根，或放著 `.openviking/config.json` 的那個目錄 | 該目錄不是工作區 |
| `{harness}` | 當前 agent 的名字（`claude-code`、`codex`、`dsh`、`opencode`、`pi`、`cursor`、`trae`、`trae-cn`、`zcode`） | 從不為空——但 MCP proxy 不參與推導，所以只走 proxy 的讀路徑解析不出它 |

在 `/Users/x/Dev/OpenViking/examples/codex-memory-plugin` 目錄下、`origin` 為 `git@github.com:volcengine/OpenViking.git` 時，peer 是 `github.com-volcengine-openviking`——無論從哪個子目錄、哪個 worktree、哪臺機器、哪份 clone 得到的都是同一個值。因此同一倉庫的所有 clone 共享一個 peer，而 fork 的 `origin` 不同，預設就是獨立的 peer。推導過程直接讀取倉庫檔案而不呼叫 `git`，因此 `PATH` 中沒有 `git` 時同樣可用；URL 會先歸一化，使同一倉庫的 ssh 與 https 寫法收斂到同一個值，URL 中內嵌的 token 也不會進入 peer id。

#### 按場景選擇

| 場景 | 怎麼做 |
|---|---|
| 有 `origin` 的倉庫 | 什麼都不用做。所有 clone、worktree、子目錄共用一個 peer |
| Fork | `origin` 不同，預設與上游分開。要合併兩邊的記憶，就在兩邊寫同一個 `peer.id` |
| 沒有 remote 的本地倉庫 | 預設用倉庫根路徑，換臺機器就會變。長期專案建議寫一個 `peer.id` |
| 長期使用但不是倉庫的目錄 | 建立 `.openviking/config.json`，寫上 `peer.id` |
| monorepo 裡某個子專案要單獨記憶 | 在子目錄放 `config.json`，寫 `peer.source: "{git_remote}-{dir}"`。只放標記檔案仍會沿用倉庫 peer，因為 `{git_remote}` 先解析成功 |
| 一次性任務目錄（應用按日期新建的目錄、臨時解包目錄） | 什麼都不用做，記憶進入使用者級空間 |
| 同一倉庫下各個 agent 想各存各的 | `peer.source: "{git_remote}-{harness}"`。預設不這麼分——跨 agent 共享一份專案記憶通常才是想要的，所以這一檔得自己寫 |
| 幾個目錄共享一份記憶 | 各處寫同一個 `peer.id` |
| 不想按專案區分 | `peer.source: "none"`（等同於 `OPENVIKING_WORKSPACE_PEER=0`） |

### 召回隔離

`peer.source` 決定記憶寫到哪裡，`recall.peer_scope` 決定讀回什麼。peer 是路徑字首，不是租戶邊界。同一項配置在 `ovcli.conf` 中寫作 `plugin.recallPeerScope`，環境變數為 `OPENVIKING_RECALL_PEER_SCOPE`。

| `recall.peer_scope` | 召回讀什麼 |
|---|---|
| `"all"`（預設） | 使用者級記憶與本工作區 peer 全權重參與，再對該使用者的其他 peer 做一次掃描，命中結果按類別降分——服務端 `other_peer_penalty` 預設對 events、entities 為 0.1，對 preferences、experiences、resources、skills 為 0.02。因此其他專案的內容只能墊底 |
| `"actor"` | 只看使用者級記憶和本工作區的 peer。外掛會額外查詢一次此處按 `git` 預設之前的規則推匯出的 peer，因此舊版本寫下的內容不會丟 |

兩檔之下使用者級記憶都是全權重，這也是"不在倉庫中就不發 peer"的代價：一次性任務裡學到的東西，之後在每個專案裡都會參與召回。需要更強隔離時，給這類目錄也寫一個自己的 `peer.id`，或整體切到 `"actor"`。

切換到 `git` 預設值不需要遷移，也不會搬動任何資料：寫在舊的 cwd 派生 peer 下的記憶原地不動，召回仍然讀得到——`"all"` 下靠跨 peer 掃描，`"actor"` 下靠那次額外查詢。`peer_scope` 是逐請求引數；服務端版本過舊、不認識它時，外掛會記錄一次降級並告警，而不是靜默地讀取全部。

### 工作區檔案不能設定的內容

hook 是非互動程序，因此這些檔案不經確認即被信任；被拒絕的是結構性的內容：

- 連線與憑證類的鍵——`url`、`api_key`、`root_api_key`、`account`、`user`、`extra_headers` 等——無論出現在哪一層都會被剝離並給出警告。“資料發往哪個服務端”這個問題始終只看 `ovcli.conf` 和環境變數就能回答。
- 這些檔案中不會展開 `${VAR}`。

提交到倉庫的檔案關掉了什麼，採用提示而不是攔截的方式：外掛的 `ov-memory-doctor` 會列出每一項工作區級配置的值、來源層，以及它覆蓋掉的內容。

`.gitignore` 不能忽略整個 `.openviking/`，否則 `config.json` 永遠無法提交。請把規則收窄到解析器的臨時目錄和私有檔案：

```text
.openviking/media/
.openviking/downloads/
.openviking/config.local.json
```

存在整目錄忽略規則時，`ov-memory-doctor` 會給出警告。

## 相關環境變數

`ov` CLI 直接使用的環境變數只有少量幾個：

| 環境變數 | 作用 |
|---|---|
| `OPENVIKING_CLI_CONFIG_FILE` | 指定要讀取的 `ovcli.conf` 路徑 |
| `OPENVIKING_UPLOAD_MODE` | 指定臨時上傳模式：`local` 或 `shared` |

`ov config add` 和 `ov config edit` 的 `--api-key-env <變數名>`、`--root-api-key-env <變數名>` 可以從指定環境變數讀取金鑰，並寫入配置檔案。

Agent 外掛使用的 `OPENVIKING_AUTO_RECALL`、`OPENVIKING_RECALL_LIMIT`、`OPENVIKING_AUTO_CAPTURE`、`OPENVIKING_DEBUG` 等變數由外掛程序讀取，不是 `ovcli.conf` 欄位。

## 多服務配置

普通 `ov` 命令以及 `ov config show`、`ov config validate` 按以下順序解析實際配置：

1. 設定 `OPENVIKING_CLI_CONFIG_FILE` 後，該路徑具有最高優先順序；檔案不存在時會直接報錯。
2. 未設定該變數時，使用預設 Active 檔案：

```text
~/.openviking/ovcli.conf
```

互動式管理器以及 `ov config list`、`switch`、`add`、`edit`、`delete` 始終管理預設配置倉庫。該倉庫中的命名配置與預設 Active 檔案位於同一目錄：

```text
~/.openviking/ovcli.conf.<name>
```

例如，一份生產環境配置可以寫成：

```json
{
  "url": "https://openviking.example.com",
  "api_key": "<production-api-key>",
  "timeout": 120
}
```

常用命令：

```bash
ov config
ov config list
ov config switch <name>
ov config validate
ov config show
```

`ov config switch <name>` 會把命名配置複製為預設 Active 檔案。如果仍設定了 `OPENVIKING_CLI_CONFIG_FILE`，普通 `ov` 命令會繼續讀取環境變數指定的檔案；需要取消該變數後才會使用剛切換的預設配置。新的 `ov` 命令會重新讀取實際配置檔案；已經執行的 Agent 客戶端需要重啟後才會讀取變更。

互動式配置和 Agent 輔助配置步驟見[Business Data Platform CLI 配置指南](../getting-started/05-cli-setup.md)。
