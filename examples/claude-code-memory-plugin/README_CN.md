# Business Data Platform Memory Plugin for Claude Code

為 Claude Code 提供長期語義記憶，由 [Business Data Platform](https://github.com/volcengine/OpenViking) 驅動。每次使用者輸入前自動召回相關記憶，每輪對話結束後自動捕獲上下文——模型不需要主動呼叫任何 MCP 工具。

> 外掛可直接從倉庫自帶的 marketplace catalog 安裝，無需單獨的分發倉庫。兩條命令的遠端安裝方式見下文[手動安裝](#手動安裝)。

## 快速開始

### 一行安裝（推薦）

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/volcengine/OpenViking/main/examples/memory-plugin-shared/install.sh) --harness claude
```

僅支援 macOS 和 Linux。Claude Code 和 Codex 共用這一個安裝指令碼（去掉 `--harness claude` 可互動勾選）：它會依次詢問介面語言（English/中文）、下載源（GitHub，或 GitHub 受限地區用 TOS 映象——傳 `--dist tos`）和 Business Data Platform 憑據，然後從遠端 marketplace 安裝 `openviking-memory`。stdio MCP 代理執行時讀取 `ovcli.conf`，不再需要 shell wrapper 或 `.mcp.json` 渲染。重複執行安全。

如果你更喜歡手動操作，按下面四步走。

### 手動安裝

#### 1. 準備一個可用的 Business Data Platform 伺服器

本地起一個或者指向遠端：[快速開始指南](../../docs/zh/getting-started/02-quickstart.md) 涵蓋兩種模式，也講了遠端使用時怎麼簽發 API key。預設埠 `1933`；本地模式無需鑑權。

驗證服務能通：

```bash
curl http://localhost:1933/health   # 或者你的遠端 URL
```

#### 2. 告訴外掛伺服器在哪

最簡單的方式——寫 `~/.openviking/ovcli.conf`（也是 `ov` CLI 用的同一個檔案）：

```json
{
  "url": "https://your-openviking-server.example.com",
  "api_key": "<your-api-key>",
  "account": "my-team",
  "user": "alice"
}
```

如果是純本地模式（`http://127.0.0.1:1933`，無鑑權），這一步可以跳過——外掛會靜默走本地預設值。

如果你已經在維護 `ov.conf`，外掛也讀它——完整優先順序鏈和按欄位覆蓋見下方 [配置](#配置)。

#### 3. 安裝外掛

**遠端 marketplace（推薦）** —— 無需 clone 倉庫。倉庫根目錄自帶 `.claude-plugin/marketplace.json`，其條目通過 `git-subdir` 拉取本外掛：

```bash
claude plugin marketplace add https://raw.githubusercontent.com/volcengine/OpenViking/main/.claude-plugin/marketplace.json
claude plugin install openviking-memory@openviking
```

（`claude plugin marketplace add volcengine/OpenViking` 也可以，但會把整個倉庫 clone 下來作為 marketplace。）

如果跳過了第 2 步，裝完後再配置連線：手寫 `~/.openviking/ovcli.conf`、執行外掛自帶的交互向導 `node <外掛目錄>/scripts/setup.mjs`，或直接跑一行安裝指令碼。

**本地目錄（開發用）** —— 註冊當前 checkout，`scripts/`、`hooks/` 的修改下次 hook 觸發即生效、無需重灌。在 Business Data Platform 倉庫根目錄：

```bash
claude plugin marketplace add "$(pwd)/examples"
claude plugin install openviking-memory@openviking
```

> 兩條命令預設都裝在 user scope —— 外掛在任何目錄下都生效。這裡**不顯式傳 `--scope user`**，因為老的 Claude Code 2.0.x（比如 2.0.76）不識別這個 flag 會直接報錯。在支援 `--scope` 的新版本上，如果裝完發現落到了 local scope，可以跑一次 `claude plugin enable openviking-memory@openviking --scope user` 提升到 user scope。
>
> 目錄模式注意：移動 / 重新命名 / 刪除原始碼目錄，或 `git checkout` 到不含這些檔案的分支，會立刻讓外掛失效。兩種模式註冊的 marketplace 都叫 `openviking`，外掛 id 恆為 `openviking-memory@openviking`；切換模式時先移除 marketplace 再新增另一個來源（安裝指令碼會自動處理）。

##### 兼容模式（Claude Code < 2.0）

`claude plugin` 子命令是 Claude Code 2.0（2025-10）才引入的。再老的版本只有 `claude mcp add` 和 hooks 系統，但仍然能手動接出同樣的功能：

```bash
PLUGIN_DIR="$(pwd)/examples/claude-code-memory-plugin"

# stdio MCP 代理 —— 自己讀 ovcli.conf / OPENVIKING_*，不再需要拼 header。
claude mcp remove openviking -s user 2>/dev/null
claude mcp add --scope user openviking -- node "$PLUGIN_DIR/servers/mcp-proxy.mjs"

# 把外掛 hooks 合併進 ~/.claude/settings.json（自動備份）
mkdir -p ~/.claude && [ -f ~/.claude/settings.json ] || echo '{}' > ~/.claude/settings.json
cp -p ~/.claude/settings.json ~/.claude/settings.json.bak.$(date +%s)
sed "s|\${CLAUDE_PLUGIN_ROOT}|$PLUGIN_DIR|g" "$PLUGIN_DIR/hooks/hooks.json" > /tmp/ov-hooks.json
jq --slurpfile h /tmp/ov-hooks.json '.hooks = ((.hooks // {}) * $h[0].hooks)' \
  ~/.claude/settings.json > /tmp/ov-settings.json
jq -e . /tmp/ov-settings.json >/dev/null && mv /tmp/ov-settings.json ~/.claude/settings.json
rm -f /tmp/ov-hooks.json
```

一行安裝指令碼在檢測到 2.0 之前的版本時會自動執行以上流程（並在 `~/.openviking/openviking-repo` 保留一份原始碼 checkout 供上面的絕對路徑引用）。

#### 4. 啟動 Claude Code

```bash
claude
```

如果外掛似乎沒在工作，開 `OPENVIKING_DEBUG=1` 看 `~/.openviking/logs/cc-hooks.log`。

## 配置 MCP

外掛的 hook 和 MCP 條目現在使用同一條配置鏈。倉庫裡的 `.mcp.json` 會把 `servers/mcp-proxy.mjs` 作為本地 stdio MCP server 啟動；這個代理讀取 `OPENVIKING_*`、`~/.openviking/ovcli.conf` 和 `~/.openviking/ov.conf`，再把 JSON-RPC 轉發到 Business Data Platform 服務端原生 `/mcp` endpoint，並補齊認證與身份頭。

正常外掛安裝不需要額外 export，也不需要渲染 `.mcp.json`。更新 `ovcli.conf` 或相關 `OPENVIKING_*` 環境變數後重啟 Claude Code，代理會和 hook 指令碼命中同一個 Business Data Platform 目標。

代理要求 Node.js 18+。只有在 `OPENVIKING_DEBUG=1` 或 `claude_code.debug=true` 時才寫 debug log；stdout 嚴格保留給 MCP 協議輸出。

## 配置

### 解析優先順序

每個外掛欄位按從高到低：

1. **環境變數**（`OPENVIKING_*`——見下方表格）
2. **`ovcli.conf`** — CLI 客戶端配置（`~/.openviking/ovcli.conf` 或 `OPENVIKING_CLI_CONFIG_FILE`）；只承載連線欄位（`url`、`api_key`、`account`、`user`）
3. **`ov.conf`** — 伺服器配置（`~/.openviking/ov.conf` 或 `OPENVIKING_CONFIG_FILE`）；外掛讀 `server.url`、`server.root_api_key`，以及可選的遺留 `claude_code` 塊（見 [遺留 `claude_code` 塊](#遺留-claude_code-塊在-ovconf-裡)）
4. **內建預設值**（`http://127.0.0.1:1933`，無鑑權）

同一組連線與身份欄位也會被 stdio MCP 代理使用。

### 環境變數

外掛全部行為均可通過 env vars 配置。連線 / 身份變數同時影響 hook 和 MCP 代理；調優變數僅影響 hook。

#### 連線 / 身份

| 環境變數                                          | 說明                                                                |
|--------------------------------------------------|--------------------------------------------------------------------|
| `OPENVIKING_URL` / `OPENVIKING_BASE_URL`         | 完整伺服器 URL（如 `https://remote.example.com`）                  |
| `OPENVIKING_API_KEY` / `OPENVIKING_BEARER_TOKEN` | API key；以 `Authorization: Bearer <key>` 傳送                     |
| `OPENVIKING_ACCOUNT`                             | 多租戶 account（`X-OpenViking-Account` 頭）                        |
| `OPENVIKING_USER`                                | 多租戶 user（`X-OpenViking-User` 頭）                              |
| `OPENVIKING_PEER_ID`                             | 可選的穩定 peer，用於自動召回和 session message 寫入               |

設定 `OPENVIKING_PEER_ID` 後，資料面的 recall/profile 請求會把它作為 `X-OpenViking-Actor-Peer` 傳送；捕獲到 session message 時仍寫入 body `peer_id`。未顯式配置 peer 時，subagent 捕獲會回退到 Claude 的 `agent_id`，讓不同 subagent 預設落到不同 peer memory。

#### 召回調優

| 環境變數                                | 預設值        | 說明                                                                |
|----------------------------------------|---------------|--------------------------------------------------------------------|
| `OPENVIKING_AUTO_RECALL`               | `true`        | 啟用每輪自動召回                                                   |
| `OPENVIKING_RECALL_LIMIT`              | `10`          | 遺留配額縮放輸入；轉換為六類 coding 配額，不是最終結果上限          |
| `OPENVIKING_RECALL_TOKEN_BUDGET`       | `2000`        | 僅用於最終 raw-find fallback 的內聯 token 預算                      |
| `OPENVIKING_RECALL_MAX_CONTENT_CHARS`  | `500`         | 單條記憶內容字元上限                                               |
| `OPENVIKING_RECALL_PREFER_ABSTRACT`    | `true`        | 有 abstract 時優先用 abstract 而非完整 body                        |
| `OPENVIKING_SCORE_THRESHOLD`           | `0.35`        | 最低相關度得分（0–1）                                               |
| `OPENVIKING_MIN_QUERY_LENGTH`          | `3`           | 短於此長度的 query 跳過召回                                        |
| `OPENVIKING_RECALL_QUERY_FILTERS`      | `""`          | 逗號分隔的正則規則，在 prompt 變成檢索 query 前生效 —— 見[輸入過濾器](#輸入過濾器) |
| `OPENVIKING_LOG_RANKING_DETAILS`       | `false`       | 每候選打分日誌（很囉嗦）                                           |
| `OPENVIKING_RECALL_MAX_TOKENS`         | `1600`        | 服務端組裝上下文塊的 token 預算（與本地壓縮輸入上限相互獨立）         |
| `OPENVIKING_RECALL_DEDUP_TURNS`        | `5`           | 跨輪冷卻：最近 N 輪已注入過的 URI 本輪跳過                           |
| `OPENVIKING_RECALL_QUERY_EXPANSION`    | `auto`        | `auto` 讓服務端結合會話上下文擴充短提問；`off` 關閉                   |
| `OPENVIKING_RECALL_COMPRESS`           | `auto`        | digest 壓縮：`off`、`client`（本地宿主 CLI）、`server`、`auto`（本地優先、失敗回落服務端） |
| `OPENVIKING_RECALL_COMPRESS_MAX_BULLETS` | `6`         | digest 條數上限                                                     |

召回的不只是記憶，也包括 skill：服務端組裝的上下文塊可能帶有 skill 條目（`type="skills"`），既有你自己的 skill，也有帳號內共享的 skill。

#### 捕獲調優

| 環境變數                                | 預設值        | 說明                                                                |
|----------------------------------------|---------------|--------------------------------------------------------------------|
| `OPENVIKING_AUTO_CAPTURE`              | `true`        | 啟用自動捕獲；同時 gate 寫 hook（PreCompact / SessionEnd / SubagentStop） |
| `OPENVIKING_CAPTURE_MODE`              | `semantic`    | `semantic`（總是捕獲）或 `keyword`（基於觸發詞）                   |
| `OPENVIKING_CAPTURE_MAX_LENGTH`        | `24000`       | 捕獲判定時 sanitized 文本的長度上限                                |
| `OPENVIKING_CAPTURE_ASSISTANT_TURNS`   | `true`        | 捕獲 assistant 回合(文本 + tool 輸入/輸出)。設為 `0` 可退回僅使用者   |
| `OPENVIKING_COMMIT_TOKEN_THRESHOLD`    | `20000`       | client-driven commit 的 pending-token 閾值                         |
| `OPENVIKING_RESUME_CONTEXT_BUDGET`     | `32000`       | resume 時拉取 archive overview 的 token 預算                       |
| `OPENVIKING_CAPTURE_FILTERS`           | `""`          | 逗號分隔的正則規則，作用於每個被捕獲的回合 —— 見[輸入過濾器](#輸入過濾器) |

#### 會話啟動注入

| 環境變數                                  | 預設值    | 說明                                                                |
|------------------------------------------|-----------|--------------------------------------------------------------------|
| `OPENVIKING_NO_AUTO_INJECT`              | `false`   | 會話啟動時不注入使用者畫像、記憶索引和 skill 清單；resume/compact 的 archive overview 和逐輪召回照常進行 |
| `OPENVIKING_PROFILE_TOKEN_BUDGET`        | `10000`   | `profile.md` 及 `preferences/`、`entities/` 索引共用的 CJK-aware token 預算 |
| `OPENVIKING_SKILL_CATALOG`               | `true`    | 在會話啟動塊里加入 `<available-skills>` skill 清單                 |
| `OPENVIKING_SKILL_CATALOG_TOKEN_BUDGET`  | `1200`    | `<available-skills>` 的 token 預算（0–20000），不佔使用者畫像的預算；設為 `0` 即不注入清單 |
| `OPENVIKING_SESSION_START_MAX_BYTES`    | `9500`    | SessionStart 注入的總位元組上限，保證低於 Claude Code 10,000 字元的內聯限制；resume/compact 時歸檔最多佔一半；`0` 取消上限 |

在 `ovcli.conf` 裡，這幾項對應 `plugin` 或 `plugin.claude_code` 下的 `noAutoInject`、`profileTokenBudget`、`skillCatalog` 和 `skillCatalogTokenBudget`。

每次 `SessionStart`（`startup`、`clear`、`resume`、`compact`）都會注入一個 `<openviking-context>` 塊，依次包含 `<user-profile>`、`<available-memories>` 和 `<available-skills>`；`resume`/`compact` 時後面還會接上最新的 archive overview。skill 清單來自一次 `GET /api/v1/skills?node_limit=200` 呼叫：先列你自己的 skill，再列帳號內共享在 `viking://agent/skills` 下的 skill，與你自己某個 skill 同名的共享 skill 不再列出。每條描述截到約 40 個 token，描述裡出現的 `<openviking-context>` 等注入塊標籤會被轉義。完整清單超出預算時只列名稱，名稱也放不全時以 `... +N more, search Business Data Platform skills to find the rest` 收尾；連一個名稱都放不下時，整塊縮成一行 `<available-skills>N Business Data Platform skills; search Business Data Platform skills to find them.</available-skills>`。沒有任何 skill，或服務端不支援 `GET /api/v1/skills` 時，不注入清單。

```text
<openviking-context source="startup">
<user-profile uri="viking://user/default/memories/profile.md">...</user-profile>
<available-memories>...</available-memories>
<available-skills>
  Business Data Platform skills (stored in Business Data Platform, not local files). Before following one, read <dir>/<name>/SKILL.md with the Business Data Platform read tool.
  viking://user/default/skills/
    - pr-review — Review a pull request against the team checklist.
  viking://agent/skills/
    - deploy-runbook — Shared deployment runbook for the payments service.
</available-skills>
</openviking-context>
```

外掛自帶的 `openviking-skills` skill 告訴 Claude 拿到清單後怎麼做：查詢和使用 skill，用 MCP `add_skill` 工具建立、安裝或共享 skill，刪除 skill，以及在你要求時把 `~/.claude/skills` 或 `<repo>/.claude/skills` 下的本地 skill 遷入 Business Data Platform。依賴本機環境的 skill（由外掛分發、由 CLI 安裝器軟連結進來，或需要本地二進位制）留在本地，每個 skill 都要經你確認後才會上傳。

#### 生命週期 / 行為 / 雜項

| 環境變數                                | 預設值        | 說明                                                                |
|----------------------------------------|---------------|--------------------------------------------------------------------|
| `OPENVIKING_TIMEOUT_MS`                | `15000`       | 召回 + 通用請求 HTTP 超時（ms）                                    |
| `OPENVIKING_CAPTURE_TIMEOUT_MS`        | `30000`       | 捕獲路徑 HTTP 超時（須低於 `Stop` hook 超時）                      |
| `OPENVIKING_WRITE_PATH_ASYNC`          | `true`        | 把寫 hook detach 到後臺 worker，避免 CC 等待 commit RTT            |
| `OPENVIKING_BYPASS_SESSION`            | `false`       | 一次性：`1`/`true`=當前程序所有 hook 直接放行                      |
| `OPENVIKING_BYPASS_SESSION_PATTERNS`   | `""`          | CSV 的 glob 模式，匹配 `session_id` 或 `cwd`                       |
| `OPENVIKING_MEMORY_ENABLED`            | (auto)        | `0`/`false`/`no`=強制停用；`1`/`true`/`yes`=強制啟用               |
| `OPENVIKING_DEBUG`                     | `false`       | `1`/`true`=向 `~/.openviking/logs/cc-hooks.log` 輸出 debug 日誌    |
| `OPENVIKING_DEBUG_LOG`                 | `~/.openviking/logs/cc-hooks.log` | 覆蓋日誌路徑                                  |
| `OPENVIKING_CONFIG_FILE`               | `~/.openviking/ov.conf`           | 覆蓋 `ov.conf` 路徑                          |
| `OPENVIKING_CLI_CONFIG_FILE`           | `~/.openviking/ovcli.conf`        | 覆蓋 `ovcli.conf` 路徑                       |

純環境變數啟動（無需配置檔案）：

```bash
OPENVIKING_MEMORY_ENABLED=1 \
OPENVIKING_URL=https://openviking.example.com \
OPENVIKING_API_KEY=sk-xxx \
OPENVIKING_ACCOUNT=my-team \
OPENVIKING_USER=alice \
OPENVIKING_RECALL_LIMIT=8 \
claude
```

### 啟用 / 停用

1. **`OPENVIKING_MEMORY_ENABLED` 環境變數** — `0`/`false`/`no` 強制停用；`1`/`true`/`yes` 強制啟用（無配置檔案時強制啟用，連線資訊須由環境變數提供）
2. **`ov.conf` 的 `claude_code.enabled`** — `false` 禁用
3. **配置檔案存在性** — `ov.conf` 或 `ovcli.conf` 存在則啟用；否則**靜默停用**（不報錯，hook 直接放行）

### 跳過某些會話

在 `/tmp` PoC 目錄裡用 Claude Code 而不汙染長期記憶：

```bash
# 持久：任何 session_id 或 cwd 命中模式的會話
export OPENVIKING_BYPASS_SESSION_PATTERNS='/tmp/**,**/scratch/**,/Users/me/Dev/throwaway/*'

# 或一次性：
OPENVIKING_BYPASS_SESSION=1 claude
```

bypass 命中時所有 hook 直接放行，不聯絡 Business Data Platform。

### 輸入過濾器

兩個配置項在外掛送出文本之前加了一層有序的正則規則：

- `recallQueryFilters` / `OPENVIKING_RECALL_QUERY_FILTERS` —— 作用於 prompt，在它變成檢索 query 之前。
- `captureFilters` / `OPENVIKING_CAPTURE_FILTERS` —— 作用於寫路徑（`Stop`、`PreCompact`、`SessionEnd`、`SubagentStop`）上的每個回合，在它被存下來之前。

規則是 sed 風格的字串，按順序作用於同一段文本：

| 寫法 | 含義 |
|------|------|
| `s<d>模式<d>替換<d>[flags]` | 替換；替換串裡可以用 `$1`、`$&`、`$$` |
| `d<d>模式<d>[flags]` | 命中則丟棄這段文本 |
| `k<d>模式<d>[flags]` | 只有命中才保留（多條串聯即 AND） |
| `user:` / `assistant:` 字首 | 該規則只對這個角色生效 |

`<d>` 是任意標點分隔符（`/`、`|`、`#`、`:`），模式裡用 `\` 轉義它。flags 支援 `i`、`m`、`s`、`u`、`g`（`g` 表示替換全部；對 `d`/`k` 沒有意義，會被去掉）。

| 規則 | 效果 |
|------|------|
| `s/^\s*(ultrathink\|think harder?)\s+//i` | 去掉 query 前面的思考關鍵詞 |
| `d\|^\s*[/!]\|` | slash 命令和 `!` bash 模式的 prompt 不觸發召回（用 `\|` 當分隔符，`/` 就不必轉義） |
| `k/^\?ov\b/` 配 `s/^\?ov\s*//` | 改成顯式觸發：只有以 `?ov` 開頭才召回，並去掉這個觸發詞 |
| `s/\b(sk\|ghp\|xoxb)_[A-Za-z0-9_-]+/[redacted]/g` | 存進記憶前把 token 打碼 |
| `user:d/^\s*\/(clear\|compact)\b/` | 這類命令回合永不入庫，且只針對使用者側 |
| `s/^(請\|麻煩)(你\|幫我)?//` | 去掉中文客套字首 |

寫進 `ovcli.conf` 時是 JSON 陣列，所以反斜槓要寫兩遍：

```json
{
  "plugin": {
    "claude_code": {
      "recallQueryFilters": ["s/^\\s*ultrathink\\s+//i", "d|^\\s*[/!]|"],
      "captureFilters": ["s/\\b(sk|ghp)_[A-Za-z0-9_-]{10,}/[redacted]/g"]
    }
  }
}
```

- **環境變數是逗號分隔的列表**，先按逗號切分再解析，所以需要字面逗號的規則（比如帶下界的 `{10,}`）只能寫進上面的陣列。（`\x2c` 能表示模式裡其它位置的字面逗號，但它不是量詞語法。）
- **順序有意義，丟棄優先。** 第一條命中的 `d`（或未命中的 `k`）就決定了結果。過濾發生在 `OPENVIKING_MIN_QUERY_LENGTH` 和內建的應答語／slash 命令啟發式之前，所以剝掉字首後只剩「好的」的文本會按應答語丟棄。被替換成空串不算丟棄 —— query 空了只是長度不夠。
- **過濾只管送出去的內容，管不到已經存下的。** 會話中途新增 `d`/`k` 規則還會讓捕獲游標計數的回合列表變短，這會被當成 transcript 被改寫、從最後一個使用者回合重放 —— 和切換 `OPENVIKING_CAPTURE_ASSISTANT_TURNS` 是同一個現象。
- **壞規則只會被跳過，不會讓 hook 掛掉。** `ov-memory-doctor` 會列出生效的規則，並對編譯失敗的那條給出確切的解析或 RegExp 報錯。

### 插件配置放在 `ovcli.conf`

客戶端側的調優應寫在 `~/.openviking/ovcli.conf` 的 `plugin` 區域。共享鍵對所有 harness 生效，分 harness 的物件可覆蓋它：

```json
{
  "url": "http://127.0.0.1:1933",
  "plugin": {
    "recallCompress": "auto"
  }
}
```

解析順序：env vars → `plugin.claude_code` → `plugin` → `ov.conf` 裡遺留的 `claude_code` 塊 → 內建預設值。
除非使用者顯式覆蓋，外掛不會發送 `limit=10`、`max_tokens=1600`、
`query_expansion="auto"` 等由服務端擁有的 Context 預設值。
顯式設定遺留 `recallLimit` 時，外掛會將其轉換為各分類 coding 配額，而不會作為
最終結果上限執行。因此值為 1 到 5 時，有效總配額仍為 6，即六個 coding 域各一個
檢索槽位。新的直接 API 接入應優先配置 `quotas`。

### digest 壓縮

`recallCompress` 決定 digest 在哪裡生成，預設值為 `auto`。`client` 始終通過 `claude -p` 在本地壓縮（預設 Sonnet + 低推理檔——Haiku 不支援 effort 旋鈕，時延不可控），token 成本留在你自己的訂閱額度裡。`server` 讓 Business Data Platform 生成 digest。`auto` 優先本地，探測不到可用的宿主 CLI 時回落到服務端。壓縮器執行失敗或輸出校驗失敗時會退回未壓縮的上下文塊；任一壓縮器精確返回 `NO_RELEVANT_MEMORY` 都是成功的空結果，不注入任何內容。壓縮子程序執行時所有 Business Data Platform hook 均被停用，不會遞迴。舊的環境變數 `OPENVIKING_RECALL_REWRITE` 和配置鍵 `recallRewrite` 仍作為低優先順序相容別名保留。

### 遺留 `claude_code` 塊（在 `ov.conf` 裡）

早期外掛版本把調優欄位配在 `~/.openviking/ov.conf` 的 `claude_code` 塊裡。出於向後相容，這種方式仍能用——上面每個 env var 都有對應的 camelCase 欄位（`OPENVIKING_RECALL_LIMIT` → `claude_code.recallLimit`、`OPENVIKING_BYPASS_SESSION_PATTERNS` → `claude_code.bypassSessionPatterns` JSON 陣列等）。env vars 優先順序更高。新部署應優先使用 env vars + shell rc——服務端配置檔案不應承載每開發機自己的調優偏好。

## Hook 超時

`hooks/hooks.json` 預設值：

| Hook                | 超時   | 備註                                                                                          |
|---------------------|--------|----------------------------------------------------------------------------------------------|
| `SessionStart`      | `120s` | 充裕，因為 resume / compact 可能拉一個較大的 archive overview                                |
| `UserPromptSubmit`  | `60s`  | 給預設本地壓縮器留出完成時間；其自身超時更短，失敗時可在 hook 截止前安全降級                  |
| `Stop`              | `45s`  | 自動捕獲要解析 transcript + 推 turn；async detach 讓使用者感知接近 0                          |
| `PreCompact`        | `30s`  | 同步 commit，CC 緊接著會改 transcript                                                        |
| `SessionEnd`        | `30s`  | 最終 commit；async detach                                                                    |
| `SubagentStart`     | `10s`  | 輕量：只持久化隔離 state                                                                     |
| `SubagentStop`      | `45s`  | 讀子 agent transcript 並 commit；async detach                                                |

`claude_code.captureTimeoutMs` 須低於 `Stop` hook 超時，讓指令碼能優雅失敗並仍能更新增量 state。

## Statusline 狀態行

外掛會在 Claude Code 輸入框下方渲染一行 Business Data Platform 狀態。安裝指令碼會把它註冊到 `~/.claude/settings.json`（CC 外掛 manifest 不支援 `statusLine` 欄位，必須走這條路）。

示例：

```text
OV ✓ │ Fable 5 · ctx 42% │ ↩ 6 mem · 50ms          注入 6 條記憶；模型 + 上下文佔比
OV ⚠ slow                                  探針超過 1s 預算（伺服器可能在抽風）
OV ✗ offline                               伺服器不可達
OV ⚡ bypass │ Fable 5 · ctx 42%            命中 OPENVIKING_BYPASS_SESSION*
OV ✓ │ ✎ 573/20k · 2 arch                  待提交進度 + 本 session 已歸檔 2 次
OV ✓ │ 🔗 resumed │ +3 today               session 已恢復上下文；今日累計歸檔 3 次
```

`ctx` 百分比復刻 Claude Code 原生上下文指示器（自定義 statusLine 會替換掉原生那條），配色閾值與原生一致：`<70%` 灰、`70–89%` 黃、`≥90%` 紅。不想顯示可設 `OPENVIKING_STATUSLINE_CTX=off`。

完整段位說明 + 個性化 recipe（隱藏段位、改色、與已有 statusline 組合、自定義段位），見 [`STATUSLINE.md`](./STATUSLINE.md)。

資料來源：

- `auto-recall.mjs` / `auto-capture.mjs` / `session-start.mjs` 每輪寫快照到 `~/.openviking/state/{last-recall,last-capture,last-session-event,daily-stats}.json`。
- `scripts/statusline.mjs` 讀快照，再加 5 秒共享快取的 `GET /health`。
- 網路呼叫 1s 硬超時；多個 CC session 共享快取避免風暴。

關閉 / 調整：

- `OPENVIKING_STATUSLINE=off` ——不刪註冊，僅靜默。
- `NO_COLOR=1` 或非 TTY ——自動去 ANSI 顏色。
- 徹底解除安裝：`jq 'del(.statusLine)' ~/.claude/settings.json > t && mv t ~/.claude/settings.json`。
- 已有自定義 statusline？安裝時會詢問替換 / 跳過 / 稍後手動 compose。

## 除錯日誌

設定 `claude_code.debug: true` 或 `OPENVIKING_DEBUG=1`，hook 日誌寫到 `~/.openviking/logs/cc-hooks.log`。

- `auto-recall` 預設輸出關鍵階段 + 緊湊的 `ranking_summary`
- 僅在排查每候選打分時才把 `claude_code.logRankingDetails` 設為 `true`，否則非常囉嗦

## 故障排除

先跑內建的體檢指令碼——它會檢查安裝（marketplace、啟用狀態、hooks、MCP 接線）、解析後的配置（哪個檔案生效、API key 脫敏展示）、連線（可達性、鑑權、`/mcp`）和最近的 hook 活動，並給每個問題附上修復建議：

```bash
node "$(jq -r '.plugins["openviking-memory@openviking"][0].installPath' ~/.claude/plugins/installed_plugins.json)/scripts/ov-memory-doctor.mjs"
```

也可以直接讓 Claude 檢查外掛：`ov-memory-doctor` skill 會運行同一個指令碼並解讀報告。當 server 與外掛在同一臺機器上（loopback url）時，報告還會多一節 Server health：埠上是否有 server 在監聽、ov.conf 裡只有外掛會讀而 server 會拒絕啟動的鍵、以及 `GET /ready`；其餘 server 端檢查（配置校驗、實際 embedding 探測、native engine、磁碟）仍由 `openviking-server doctor` 負責。

| 症狀                                         | 原因                                                  | 解決方案                                                                                       |
|----------------------------------------------|------------------------------------------------------|-----------------------------------------------------------------------------------------------|
| 外掛沒啟用                                    | 找不到 `ov.conf` / `ovcli.conf`                       | 建立一個；或設 `OPENVIKING_MEMORY_ENABLED=1` 加上 URL/API_KEY 等環境變數                       |
| Hook 觸發但召回為空                           | Business Data Platform 伺服器沒起 / URL 不對                      | `curl http://localhost:1933/health`（或你的遠端 URL）                                          |
| 自動捕獲抽取出 0 條記憶                        | `ov.conf` 裡 embedding/extraction 模型配錯            | 檢查 `embedding` / `vlm` 配置；看伺服器日誌                                                    |
| MCP 工具命中了錯誤的伺服器                    | `ovcli.conf` / 環境變數過期，或改完配置沒有重啟 Claude Code | 見 [配置 MCP](#配置-mcp)，核對 `~/.openviking/ovcli.conf` 後重啟 Claude Code                    |
| 遠端鑑權 401 / 403                            | API key / account / user 頭錯配                      | 核對 `OPENVIKING_API_KEY`、`OPENVIKING_ACCOUNT`、`OPENVIKING_USER`（或 `ov.conf` 對應欄位）    |
| `Stop` hook 超時                              | 伺服器慢 + 同步寫路徑                                 | 保持 `writePathAsync: true`（預設），或調大 `hooks/hooks.json` 裡的 `Stop` 超時               |
| 舊上下文反覆出現在 OV 裡                      | 早期版本把召回塊當成使用者訊息回寫了                    | 升級到當前版本——`auto-capture` 現在推送前會剝離 `<openviking-context>`                      |
| 日誌太吵                                      | `logRankingDetails: true` 沒關                        | 設為 `false`；日誌裡仍保留緊湊的 `ranking_summary`                                             |

## 與 Claude Code 內建記憶的對比

Claude Code 自帶 `MEMORY.md` 檔案系統，本外掛**與之互補**：

| 特性     | 內建 `MEMORY.md`            | Business Data Platform 外掛                                |
|----------|-----------------------------|-----------------------------------------------|
| 儲存     | 扁平 markdown               | 向量資料庫 + 結構化抽取                        |
| 搜尋     | 整體載入進上下文            | 語義相似度 + 排序 + token 預算                |
| 範圍     | 單專案                      | 跨專案、跨會話、peer 維度                      |
| 容量     | ~200 行（受上下文限制）     | 不受限（服務端儲存）                           |
| 抽取     | 手寫規則                    | LLM 驅動的實體 / 偏好 / 事件抽取               |
| 子 agent | 與父共享                    | 隔離 session + peer 維度捕獲                   |

---

## 架構

```
┌────────────────────────────────────────────────────────────┐
│                      Claude Code                           │
│                                                            │
│  SessionStart   UserPromptSubmit   Stop   PreCompact       │
│  SessionEnd     SubagentStart      SubagentStop            │
└────┬───────────────┬───────────────┬───────────┬───────────┘
     │               │               │           │
     │   ┌───────────▼───────────┐   │           │
     │   │  hook 指令碼 (.mjs)     │   │           │     ┌──────────────┐
     │   │  讀 transcript +      │───┼───────────┼────►│              │
     │   │  調 OV HTTP API       │   │           │     │  Business Data Platform  │
     │   └───────────────────────┘   │           │     │  Server      │
     │                               │           │     │  (Python)    │
     │                  ┌────────────▼───────────▼───►│              │
     │                  │  MCP tools (stdio proxy→/mcp)              │
     │                  │ find/search/recall/remember/… │              │
     └─────────────────►│                             │              │
        OV session      └─────────────────────────────►              │
        context inject                                └──────────────┘
```

沒有 TypeScript 編譯步驟，也沒有執行時 npm 引導。Hook 都是直接走 HTTP 調 Business Data Platform 的 `.mjs` 檔案；MCP 使用 `servers/mcp-proxy.mjs` 作為零依賴 stdio 橋接，轉發到 Business Data Platform 伺服器自身的 `/mcp` endpoint。

首次接觸時建立一個持久化的 Business Data Platform session，整個 Claude Code 會話期間複用。OV session ID 是 `cc-<cc_session_id>`（CC session_id 原樣保留，不做雜湊），所以 resume / compact / 多 hook 事件都打到同一個 session。歸檔與記憶抽取由客戶端觸發：`Stop` hook 在服務端報告的 pending tokens 超過 `commitTokenThreshold`（預設 20000）時 commit，`PreCompact` / `SessionEnd` / `SubagentStop` 則無條件 commit。

### 各 hook 職責

| Hook                  | 觸發時機                              | 行為                                                                                              |
|-----------------------|--------------------------------------|--------------------------------------------------------------------------------------------------|
| `UserPromptSubmit`    | 每個使用者回合                          | 搜 OV → 排序 → 在 token 預算內注入 `<openviking-context>` 塊                                      |
| `Stop`                | Claude 完成一次響應                   | 解析 transcript → 把新的使用者回合推到 OV session → pending tokens 超閾值時 commit                  |
| `SessionStart`        | 新建 / resume / compact 後的會話      | 注入 `profile.md`、記憶索引和 `<available-skills>`；`resume`/`compact` 時再注入最新的 archive overview |
| `PreCompact`          | Claude Code 重寫 transcript 之前      | 在 CC 改 transcript 之前先把 pending 提交為歸檔                                                  |
| `SessionEnd`          | Claude Code 會話關閉                  | 最後一次 commit                                                                                  |
| `SubagentStart`       | 父 session 通過 Task 工具孵化子 agent | 為子 agent 派生隔離的 OV session ID，寫 start state                                              |
| `SubagentStop`        | 子 agent 結束                         | 讀子 agent transcript → 推到帶子 agent peer 身份的隔離 session → commit                          |
| `PreToolUse`          | 原生 `Read` / `Glob` / `Grep` / `Edit` / `Write` 的路徑是 `viking://` URI | 拒絕該呼叫，提示 Claude 改用對應的 Business Data Platform MCP 工具；對 skill URI（`viking://~/skills/...`、`viking://user/<id>/skills/...`、`viking://agent/skills/...`）的 `Write` / `Edit` 會被引導到 `add_skill` |
| `PreToolUse`          | `Bash` 命令裡帶 `viking://` URI | 照常執行命令，並附一條提醒：如果本意是訪問 Business Data Platform 內容，應改用 Business Data Platform MCP 工具 |
| `PostToolUse`         | `Read` 讀到 `SKILL.md` 檔案           | 可選（預設關閉）：OV 有相關 skill 經驗記憶時注入經驗塊                                           |

### 非同步寫路徑

`Stop`、`SessionEnd`、`SubagentStop` 用 detach-worker 模式：父 hook drain stdin，立刻向 stdout 輸出 `{decision:"approve"}` 解封 Claude Code，然後 spawn 一個 detached 子程序做 HTTP commit。使用者從不等 OV。`PreCompact` 必須保持同步，因為 Claude Code 緊接著會改 transcript。

除錯時如果需要嚴格順序，把 `claude_code.writePathAsync` 設為 `false`。

### 防止記憶自汙染

`auto-capture` 在把每個 turn 推給 OV 之前，會剝掉 `<openviking-context>`、`<system-reminder>`、`<relevant-memories>`、`[Subagent Context]` 這些注入塊。否則外掛本輪注入的召回上下文會在下一輪被當成"使用者訊息"再次寫回 OV，形成自我引用的汙染迴路。

### 伺服器暴露的 MCP 工具

外掛的 `.mcp.json` 啟動本地 stdio 代理，代理再連到 Business Data Platform 伺服器原生 HTTP MCP endpoint `/mcp`。Claude 可按需呼叫伺服器提供的檢索、記憶、資源、skill、watch 和檔案系統工具。建立或替換 skill 用 `add_skill`：`write` 和 `edit` 會拒絕你自己的 `skills/` 子樹，`add_resource` 也不接受 skill 目標路徑。

完整工具清單和引數詳見 [MCP 整合指南](../../docs/zh/guides/06-mcp-integration.md)。

### 外掛結構

```
claude-code-memory-plugin/
├── .claude-plugin/
│   └── plugin.json          # plugin manifest
├── hooks/
│   └── hooks.json           # 9 個 hook 註冊
├── commands/
│   └── ov.md                # /ov 狀態命令
├── skills/
│   ├── openviking-memory/   # 記憶工具使用指南
│   ├── openviking-skills/   # 查詢、新增、共享和遷移 Business Data Platform skill
│   ├── ov-experience-memory/
│   └── ov-memory-doctor/    # 安裝 / 配置 / 連線 / 本機 server 排障
├── servers/
│   └── mcp-proxy.mjs        # stdio -> Business Data Platform /mcp 橋接
├── scripts/
│   ├── config.mjs           # 共享配置載入（env > ovcli.conf > ov.conf）
│   ├── debug-log.mjs        # 寫 ~/.openviking/logs/cc-hooks.log
│   ├── auto-recall.mjs      # UserPromptSubmit
│   ├── auto-capture.mjs     # Stop
│   ├── session-start.mjs    # SessionStart
│   ├── session-end.mjs      # SessionEnd
│   ├── pre-compact.mjs      # PreCompact
│   ├── subagent-start.mjs   # SubagentStart
│   ├── subagent-stop.mjs    # SubagentStop
│   ├── ov-status.mjs        # /ov 狀態報告
│   ├── ov-memory-doctor.mjs # 體檢指令碼（ov-memory-doctor skill）
│   └── lib/
│       ├── ov-session.mjs   # OV HTTP 客戶端 + session 幫助 + bypass 檢查
│       └── async-writer.mjs # 寫路徑 detach-worker 幫助
├── .mcp.json                # MCP 配置（本地 stdio 代理）
├── package.json             # 僅 type:module 標記，無執行時依賴
└── README.md
```

## License

Apache-2.0 — 同 [Business Data Platform](https://github.com/volcengine/OpenViking)。
