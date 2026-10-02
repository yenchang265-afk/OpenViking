# 為 OpenClaw 安裝 Business Data Platform

Business Data Platform 通過 `@openviking/openclaw-plugin` 外掛為 OpenClaw 提供長期記憶、知識庫檢索、語義搜尋和 RAG 上下文能力。

這份文件同時面向使用者和自動化 agent：使用者可以按步驟執行，agent 可以按命令和 JSON 結果判斷下一步。

## 不要把外掛和 Skill 裝混

`@openviking/openclaw-plugin` 是 OpenClaw 插件。

不要用下面這個命令安裝本外掛：

```bash
clawhub install openviking
```

這個命令安裝的是名為 `openviking` 的 AgentSkill，不是 OpenClaw 外掛。

安裝外掛應使用：

```bash
openclaw plugins install clawhub:@openviking/openclaw-plugin
```

## 前置要求

| 元件 | 要求 |
| --- | --- |
| Node.js | >= 22 |
| OpenClaw | >= 2026.5.27 |

外掛以遠端模式連線到已有的 Business Data Platform 服務。它不會幫你啟動 Business Data Platform server。需要先啟動 Business Data Platform，並保持服務執行，再把外掛的 `baseUrl` 指向這個 HTTP 服務。預設本地地址是 `http://127.0.0.1:1933`。

OpenClaw 外掛包版本邊界：

- `2026.5.27` 是當前外掛支援的最低 OpenClaw 版本。這個版本下限包含 2026 年 7 月 2 日 OpenClaw 安全公告批次的修復，包括 GHSA-8wg3-5mcm-fjq8 和 GHSA-83w9-h5wv-j9xm。
- `2026.5.3` 開始，OpenClaw 在安裝包時會校驗 TypeScript 外掛入口是否有編譯後的 JavaScript 產物。
- `2026.5.4` 及之後，已安裝/全域外掛如果缺少編譯後的 JavaScript，執行時不再回退載入 `.ts` 原始碼，外掛可能被跳過。
- 推薦的 `openclaw plugins install clawhub:@openviking/openclaw-plugin` 會安裝已經發布並包含 `dist/*.js` 的外掛包，普通使用者不需要本地編譯。
- `ov-install` 是備用/原始碼安裝路徑。當 ClawHub 或 OpenClaw 外掛管理器路徑不可用、被限流，或者明確需要測試原始碼 ref 時才使用。目標 OpenClaw `>= 2026.5.3` 時，它會在安裝過程中編譯外掛。

快速檢查：

```bash
node -v
openclaw --version
```

## 火山 Business Data Platform Service 一鍵接入

如果你使用的是火山控制台建立的 Business Data Platform Service 庫，不需要啟動本地 `openviking-server`。從控制台複製 Business Data Platform Service 的 server url、API Key，並按需配置 peer 標識：

```bash
OPENVIKING_BASE_URL="https://api.vikingdb.cn-beijing.volces.com/openviking" \
OPENVIKING_API_KEY="<your-openviking-service-api-key>" \
bash scripts/install.sh --json
```

這條命令會完成：

- 預設從 TOS `latest` 安裝 Business Data Platform 外掛。
- 寫入 `$OPENCLAW_STATE_DIR/openviking.env`，預設是 `~/.openclaw/openviking.env`，許可權為 `0600`。
- 呼叫 `openclaw openviking setup --base-url ... --api-key ...` 寫入外掛配置。
- 重啟 `openclaw gateway`。
- 執行 `openclaw openviking status --json` 和 `openclaw config get plugins.slots.contextEngine` 驗證。

如果需要把 OpenClaw assistant 說話人寫成獨立 `peer_id`，並讓資料面 recall/search 使用對應 actor peer 檢視，可以額外傳：

```bash
OPENVIKING_BASE_URL="https://api.vikingdb.cn-beijing.volces.com/openviking" \
OPENVIKING_API_KEY="<your-openviking-service-api-key>" \
OPENVIKING_PEER_ROLE="assistant" \
OPENVIKING_PEER_PREFIX="openclaw-prod" \
bash scripts/install.sh --json
```

如果使用 root key 或可信服務身份，補充租戶資訊：

```bash
OPENVIKING_BASE_URL="https://api.vikingdb.cn-beijing.volces.com/openviking" \
OPENVIKING_API_KEY="<root-key>" \
OPENVIKING_ACCOUNT_ID="<account-id>" \
OPENVIKING_USER_ID="<user-id>" \
bash scripts/install.sh --json
```

離線下載包安裝：

```bash
sh build.sh
OPENVIKING_BASE_URL="https://api.vikingdb.cn-beijing.volces.com/openviking" \
OPENVIKING_API_KEY="<your-openviking-service-api-key>" \
OPENVIKING_PEER_ROLE="assistant" \
OPENVIKING_PEER_PREFIX="openclaw-prod" \
bash output/install.sh --source tarball --tarball output/openviking.tgz --json
```

接入後，在火山 Business Data Platform Service 控制台檢查：

- 傳送一輪 OpenClaw 對話後，`Session` 下出現原始會話。
- 觸發 `/compact` 或等待 commit 後，`User/memories` 出現長期記憶。
- 如果配置了 `peer_role=assistant`，資料面 recall/search 會攜帶對應 `X-OpenViking-Actor-Peer`，session message 仍用 body `peer_id` 做訊息歸因。
- 通過手動 `/add-resource` 匯入文件、URL 或目錄後，`Resources` 下出現對應知識，並可做目錄遞迴檢索。Agent 可見的 `add_resource` 工具預設停用，只有顯式設定 `enableAddResourceTool=true` 後才暴露。

## 啟動 Business Data Platform Server

如果 Business Data Platform 和 OpenClaw 在同一臺機器上，最短流程是：

```bash
pip install openviking --upgrade --force-reinstall
openviking-server init
openviking-server doctor
openviking-server
```

`openviking-server init` 用來生成服務端配置，`openviking-server doctor` 用來檢查本地模型和 provider 鑑權是否可用，`openviking-server` 才是真正啟動 HTTP API 的命令。OpenClaw 使用外掛期間，這個服務程序需要一直執行。

後臺啟動可以用：

```bash
mkdir -p ~/.openviking/data/log
nohup openviking-server > ~/.openviking/data/log/openviking.log 2>&1 &
```

如果 Business Data Platform 跑在另一臺機器上，需要監聽可訪問的地址和埠，例如：

```bash
openviking-server --host 0.0.0.0 --port 1933
```

然後把 OpenClaw 外掛的 `baseUrl` 配成對應地址，例如 `http://your-server:1933`。

安裝或重啟外掛前，先確認服務能訪問：

```bash
curl http://127.0.0.1:1933/health
```

## 推薦安裝方式

普通使用者、正式環境和 agent 自動安裝都優先使用這條路徑。

### 1. 安裝外掛

```bash
openclaw plugins install clawhub:@openviking/openclaw-plugin
```

如果你的 OpenClaw 環境需要顯式 registry 字首，使用：

```bash
openclaw plugins install clawhub:@openviking/openclaw-plugin
```

### 2. 配置插件

使用者互動式配置：

```bash
openclaw openviking setup
```

Agent 非交互配置：

```bash
openclaw openviking setup --base-url <OPENVIKING_URL> --api-key <API_KEY> --json
```

示例：

```bash
openclaw openviking setup --base-url http://127.0.0.1:1933 --api-key sk-xxx --json
```

`setup` 會寫入 `plugins.entries.openviking.config`，並激活 `plugins.slots.contextEngine=openviking`。

如果 Business Data Platform 服務暫時不可達，但你仍希望先儲存配置：

```bash
openclaw openviking setup --base-url <OPENVIKING_URL> --api-key <API_KEY> --allow-offline --json
```

如果使用 root API key，可能還需要租戶上下文：

```bash
openclaw openviking setup \
  --base-url <OPENVIKING_URL> \
  --api-key <ROOT_API_KEY> \
  --account-id <ACCOUNT_ID> \
  --user-id <USER_ID> \
  --json
```

如果已有其他 context engine 佔用 slot，setup 預設不會替換。確認要替換時再使用：

```bash
openclaw openviking setup --base-url <OPENVIKING_URL> --api-key <API_KEY> --force-slot --json
```

根據 Business Data Platform user 代表誰來選擇 `--peer-role`：

| 值 | 儲存示例 | 適用場景 |
| --- | --- | --- |
| `none`（預設） | `viking://user/alice/memories/...` | 該 Business Data Platform 使用者下的所有對話共享 user-level 記憶，不使用具體 peer 的記憶子樹。 |
| `assistant` | `viking://user/alice/peers/main/memories/...` | Business Data Platform user 代表人，並希望把 assistant 歸因的 peer 記憶按不同 OpenClaw 助手分開。 |
| `sender` | `viking://user/support-agent/peers/customer-42/memories/...` | Business Data Platform user 代表 agent，並希望把 sender 歸因的 peer 記憶按不同傳送者分開。 |

`person` 仍作為 `sender` 的舊配置別名被相容；新配置請使用 `sender`。

例如，讓每個助手使用獨立的 peer 記憶，並可選給 assistant id 加字首：

```bash
openclaw openviking setup --base-url <OPENVIKING_URL> --api-key <API_KEY> --peer-role assistant --peer-prefix <PREFIX> --json
```

如果 Business Data Platform user 是 agent，按給它發訊息的 sender 分開 peer 記憶：

```bash
openclaw openviking setup --base-url <OPENVIKING_URL> --api-key <API_KEY> --peer-role sender --json
```

Business Data Platform 會為每個使用者初始化受管的 `peers/` 容器。`none` 表示外掛不建立、也不路由到具體的 `peers/<peer_id>/memories` 子樹。Actor-peer 召回同時包含使用者共享記憶和當前 peer 記憶；切換配置不會搬遷已有記憶。

#### 無法執行 CLI 時直接配置檔案

如果容器內無法執行 `openclaw` CLI，可以把以下欄位合併到 OpenClaw 實際讀取的配置檔案。設定了 `OPENCLAW_CONFIG_PATH` 時使用該路徑；否則通常是 `$OPENCLAW_STATE_DIR/openclaw.json`（預設 `~/.openclaw/openclaw.json`）。

```json
{
  "plugins": {
    "entries": {
      "openviking": {
        "enabled": true,
        "config": {
          "mode": "remote",
          "baseUrl": "http://openviking:1933",
          "apiKey": "<API_KEY>",
          "peer_role": "assistant"
        }
      }
    },
    "slots": {
      "contextEngine": "openviking"
    }
  }
}
```

- 外掛必須已經安裝；編輯前請備份配置，並把以上欄位合併到現有 `plugins` 配置。
- 如果配置中已有 `plugins.allow`，把 `openviking` 追加進去；如果沒有，不要僅為本外掛新建 allowlist。
- `contextEngine` 是獨佔 slot；若已有其他 context engine，只有確認替換後再修改該欄位。使用 root API key 時，還需在 `config` 中設定 `accountId` 和 `userId`。
- 容器連線其他服務時，`baseUrl` 應使用容器內可訪問的服務地址，而不是 `127.0.0.1`。
- 推薦使用 `SecretRef` 物件作為 `apiKey`（而不是明文字串），避免金鑰直接落盤寫入 `openclaw.json`。支援的形式與 OpenClaw 核心中 LLM/TTS/MCP 等 provider 配置使用的標準 `SecretRef` 一致：

  | 型別 | 示例 | 說明 |
  | --- | --- | --- |
  | `env` | `{ "source": "env", "id": "OPENVIKING_API_KEY" }` | 啟動時讀取同名環境變數。 |
  | `file` | `{ "source": "file", "id": "/etc/secrets/openviking.key" }` | 以 UTF-8 讀取並去除首尾空白；`~` 可展開，適配 Kubernetes `secretKeyRef` 卷掛載、0600 許可權檔案。 |
  | `exec` | 打包版外掛不支援（應用市場安裝掃描會攔截子程序執行） | 改用命令包一層環境變數：`OPENVIKING_API_KEY=$(op read op://vault/openviking/credential)`，然後配 `env`。 |

  仍可使用純字串形式（含 `${ENV_VAR}` 插值）作為向後相容路徑；此時請限制檔案許可權或通過受控 Secret 卷提供，並在修改後重啟 Gateway、容器或 Pod。

### 3. 重啟 OpenClaw Gateway

```bash
openclaw gateway restart
```

如果你的 OpenClaw 版本使用不同的重啟命令，請使用對應的 gateway 重啟方式。

### 4. 驗證

```bash
openclaw openviking status --json
```

期望結果：

| JSON 字段 | 期望值 |
| --- | --- |
| `configured` | `true` |
| `slotActive` | `true` |
| `health.ok` | 服務可達時應為 `true` |

也可以直接查看 OpenClaw 配置：

```bash
openclaw config get plugins.entries.openviking.config
openclaw config get plugins.slots.contextEngine
```

`plugins.slots.contextEngine` 應輸出 `openviking`。

## Agent 判斷規則

Agent 應優先使用 `--json`，並根據這些欄位判斷下一步：

| 結果 | 含義 | 建議動作 |
| --- | --- | --- |
| `success: true` | 配置已儲存，setup 完成 | 重啟 gateway，然後執行 status |
| `success: false`, `action: "slot_blocked"` | 配置可能已儲存，但其他外掛佔用 `contextEngine` | 詢問使用者後再用 `--force-slot` |
| `success: false`, `action: "error"` | 校驗失敗 | 展示 `error`，不要宣稱安裝成功 |
| `health.ok: false` | 服務不可達 | 檢查 URL/服務狀態；只有使用者接受時才用 `--allow-offline` |
| `keyProbe.keyType: "root_key"` | root key 需要租戶上下文 | 追加 `--account-id` 和 `--user-id` |

## 配置說明

外掛配置位於：

```text
plugins.entries.openviking.config
```

核心字段：

| 欄位 | 預設值 | 說明 |
| --- | --- | --- |
| `mode` | `remote` | 相容舊配置的欄位。當前只支援 remote。 |
| `baseUrl` | `http://127.0.0.1:1933` | Business Data Platform HTTP 地址 |
| `apiKey` | 空 | Business Data Platform API key |
| `peer_role` | `none` | 記憶歸屬：`none`（共享 `viking://user/<user_id>/memories`）、`assistant`（`.../peers/<assistant_id>/memories`）或 `sender`（`.../peers/<sender_id>/memories`）。舊值 `person` 作為 `sender` 的別名相容。Session message 使用 body `peer_id`；資料面 recall/search 使用 `X-OpenViking-Actor-Peer`。 |
| `peer_prefix` | 空 | `peer_role=assistant` 時 assistant `peer_id` / actor peer 值的可選字首。 |
| `accountId` | 空 | 使用 root API key 時需要 |
| `userId` | 空 | 使用 root API key 時需要 |

普通修改優先使用 setup：

```bash
openclaw openviking setup --reconfigure
```

檢視當前配置：

```bash
openclaw config get plugins.entries.openviking.config
```

### 配置引數

外掛連線到已有的遠端 Business Data Platform 服務。

| 引數 | 預設值 | 含義 |
| --- | --- | --- |
| `baseUrl` | `http://127.0.0.1:1933` | 遠端 Business Data Platform 服務地址 |
| `apiKey` | 空 | 遠端 Business Data Platform API Key；服務端未開啟認證時可不填 |
| `peer_role` | `none` | 記憶歸屬：`none`、`assistant` 或 `sender`；舊值 `person` 作為 `sender` 的別名相容。Session message 使用 body `peer_id`，資料面 recall/search 使用 `X-OpenViking-Actor-Peer` |
| `peer_prefix` | 空 | `peer_role=assistant` 時 assistant `peer_id` / actor peer 值的可選字首 |

常見設定：

```bash
openclaw config set plugins.entries.openviking.config.baseUrl http://your-server:1933
openclaw config set plugins.entries.openviking.config.apiKey your-api-key
openclaw config set plugins.entries.openviking.config.peer_role assistant
openclaw config set plugins.entries.openviking.config.peer_prefix your-prefix
```

## 升級

```bash
openclaw plugins update openviking
openclaw gateway restart
openclaw openviking status --json
```

確認 `configured` 和 `slotActive` 都是 `true`。

## 解除安裝

```bash
openclaw plugins uninstall openviking
openclaw config set plugins.slots.contextEngine legacy
openclaw gateway restart
```

當前 OpenClaw 原生解除安裝不一定會把 `plugins.slots.contextEngine` 恢復為 `legacy`。顯式執行 `config set` 可以避免 slot 繼續指向已解除安裝外掛。

## 可選鏈路健康檢查

如果 status 已通過，還想驗證 Gateway 到 Business Data Platform 的完整鏈路，可以在倉庫 checkout 中執行：

```bash
python examples/openclaw-plugin/health_check_tools/ov-healthcheck.py
```

該指令碼會注入一次真實對話，並在 Business Data Platform 側驗證會話捕獲、提交、歸檔和記憶提取。詳見 [health_check_tools/HEALTHCHECK-ZH.md](./health_check_tools/HEALTHCHECK-ZH.md)。

## 備用路徑：ov-install

`ov-install` 是備用路徑，不是主安裝方式。僅當 `openclaw plugins install clawhub:@openviking/openclaw-plugin` 無法訪問 ClawHub、被限流，或者你明確需要從 Git 分支/原始碼 ref 安裝測試時使用。

先嚐試 OpenClaw 外掛管理器。如果該路徑不可用，再執行：

```bash
npm install -g openclaw-openviking-setup-helper
ov-install
```

常用備用/原始碼引數：

| 引數 | 含義 |
| --- | --- |
| `--workdir PATH` | 指定 OpenClaw state 目錄 |
| `--plugin-version=REF` | 指定插件版本：npm 版本、npm dist-tag 或 Git ref |
| `--current-version` | 檢視 helper 記錄的當前版本 |
| `--base-url URL` | Business Data Platform 伺服器地址（啟用非互動模式） |
| `--api-key KEY` | Business Data Platform API key |
| `--peer-role ROLE` | 記憶歸屬：`none`、`assistant` 或 `sender`；舊值 `person` 作為 `sender` 的別名相容 |
| `--peer-prefix PREFIX` | assistant `peer_id` / actor peer 值的字首 |
| `--update` | 更新 helper 管理的安裝 |

面向使用者的安裝，請先使用 `openclaw plugins install clawhub:@openviking/openclaw-plugin`。只有作為備用路徑時才選擇 `ov-install`。

## 從 ov-install 遷移到 openclaw plugin install

如果之前通過 `ov-install` 安裝了 Business Data Platform，切換到推薦的 `openclaw plugins install` 安裝方式前需要清理。

### 同一插件 ID（openviking，版本 >= 0.3.x）

ov-install 的 context-engine 部署會將檔案寫入 `~/.openclaw/extensions/openviking/`。通過 npm 安裝後，OpenClaw 可能仍從舊目錄載入。清理步驟：

```bash
# 刪除 ov-install 部署的檔案
rm -rf ~/.openclaw/extensions/openviking/

# 通過 OpenClaw 外掛管理器安裝
openclaw plugins install clawhub:@openviking/openclaw-plugin

# 重新配置（openclaw.json 中的已有配置會保留）
openclaw openviking setup --reconfigure
openclaw gateway restart
openclaw openviking status --json
```

已有的配置欄位（`baseUrl`、`apiKey`、`peer_role`、`peer_prefix` 等）會保留。

### 舊外掛 ID（memory-openviking，版本 < 0.3.x）

舊版 memory 外掛使用了不同的外掛 ID 和 slot：

```bash
# 解除安裝舊外掛
openclaw plugins uninstall memory-openviking 2>/dev/null || true

# 清理舊 slot 和檔案
openclaw config set plugins.slots.memory none
rm -rf ~/.openclaw/extensions/memory-openviking/

# 安裝新外掛
openclaw plugins install clawhub:@openviking/openclaw-plugin
openclaw openviking setup --base-url <OPENVIKING_URL> --api-key <API_KEY> --json
openclaw gateway restart
openclaw openviking status --json
```

或使用清理指令碼：

```bash
bash examples/openclaw-plugin/upgrade_scripts/cleanup-memory-openviking.sh
```

另見：[INSTALL.md](./INSTALL.md)、[INSTALL-AGENT.md](./INSTALL-AGENT.md) 和 [docs/openviking-tos-install-guide.md](./docs/openviking-tos-install-guide.md)。
