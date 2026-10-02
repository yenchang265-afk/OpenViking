# OpenCode 插件

為 [OpenCode](https://opencode.ai/) 提供跨專案、跨會話的長期記憶和已索引倉庫上下文。安裝後，每次對話都會通過 OpenCode plugin hooks 自動召回相關記憶並捕獲新內容；模型可呼叫工具來自 Claude Code / Codex 記憶外掛同款的 Business Data Platform stdio MCP proxy。

原始碼：[examples/opencode-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/opencode-plugin)

工具呼叫和結果會作為獨立的 `tool` part 捕獲，`tool_output` 原樣上報。截斷由服務端負責：超過 `tool_output_externalization.threshold_chars`（預設 `20000`）的輸出會寫入 session 的 tool-result 儲存，part 中只保留 synopsis stub 和 `tool_output_ref`，原文仍可通過 [`/api/v1/sessions/{id}/tool-results`](../api/05-sessions.md#read-tool-result) 讀回。

## 前置條件

- [OpenCode](https://opencode.ai/)
- Node.js 18+
- Business Data Platform HTTP server
- 如果服務端啟用了鑑權，需要一個可用的 Business Data Platform API key

先啟動 Business Data Platform server：

```bash
openviking-server --config ~/.openviking/ov.conf
```

在另一個終端檢查服務：

```bash
curl http://localhost:1933/health
```

## 安裝

### 一鍵安裝（推薦）

OpenCode 與 Claude Code、Codex 共用同一個安裝器。它會詢問語言（English/中文）、要安裝的 harness、下載源和 Business Data Platform 憑據；每一步都是冪等的，重複執行完全安全。

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/volcengine/OpenViking/main/examples/memory-plugin-shared/install.sh) --harness opencode
```

在 GitHub 訪問困難的地區，可從火山引擎 TOS 映象運行同一個安裝器（或在下載源選擇步驟選"TOS mirror"）：

```bash
bash <(curl -fsSL https://ovrelease.tos-cn-beijing.volces.com/memory-plugin-shared/install.sh)
```

安裝器會註冊 npm 外掛（TOS 渠道則安裝本地檔案外掛），把 `openviking` MCP server 條目寫進 `~/.config/opencode/opencode.json`，並配置 `~/.openviking/ovcli.conf`。

### 手動 npm 安裝

已釋出的 npm 包是 `@openviking/opencode-plugin`。首次配置 OpenCode 時：

```bash
mkdir -p ~/.config/opencode
cat > ~/.config/opencode/opencode.json <<'JSON'
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["@openviking/opencode-plugin"]
}
JSON
opencode
```

已有 `~/.config/opencode/opencode.json` 時，不要覆蓋原檔案；只把 `"@openviking/opencode-plugin"` 合併到已有的 `plugin` 陣列。OpenCode 啟動時會自動下載這個 npm 包，外掛會自動註冊它的 MCP server。

### 原始碼安裝

如果當前環境不能通過 package 安裝：

```bash
git clone https://github.com/volcengine/OpenViking.git
cd Business Data Platform
node examples/memory-plugin-shared/sync.mjs
mkdir -p ~/.config/opencode/plugins/openviking
cp examples/opencode-plugin/wrappers/openviking.js ~/.config/opencode/plugins/openviking.js
cp examples/opencode-plugin/index.mjs examples/opencode-plugin/package.json ~/.config/opencode/plugins/openviking/
cp -r examples/opencode-plugin/lib ~/.config/opencode/plugins/openviking/
cp -r examples/opencode-plugin/servers ~/.config/opencode/plugins/openviking/
```

`sync.mjs` 會生成 `lib/shared/`，外掛和 MCP 代理都從這裡 import 共享模組。這個目錄不在 git 裡，所以複製前要先執行；之後每次 `git pull` 也要重新執行再複製。

原始碼安裝後，OpenCode 能發現的目錄結構應類似：

```text
~/.config/opencode/plugins/
├── openviking.js
└── openviking/
    ├── index.mjs
    ├── package.json
    ├── lib/
    └── servers/
```

頂層 `openviking.js` 只是一個 wrapper，用來把 OpenCode 可發現的一級外掛入口轉發到實際安裝目錄。
原始碼安裝請使用 `.js` wrapper；OpenCode 的本地外掛掃描器會發現 JavaScript/TypeScript 外掛檔案。

## 配置

憑據與 Claude Code / Codex 記憶外掛共用。可以在倉庫根目錄執行一次 setup 嚮導，或使用 `OPENVIKING_*` 環境變數。嚮導同樣 import `lib/shared/`，所以要先生成：

```bash
node examples/memory-plugin-shared/sync.mjs
node examples/opencode-plugin/scripts/setup.mjs
```

行為旋鈕寫在 `~/.openviking/ovcli.conf` 的 `plugin` 段，與嚮導寫入的連線欄位同一個檔案。共享鍵對所有記憶外掛生效；`plugin.opencode` 下的鍵只對本外掛生效，並覆蓋共享鍵：

```json
{
  "plugin": {
    "recallLimit": 6,
    "scoreThreshold": 0.35,
    "recallMaxContentChars": 500,
    "recallPreferAbstract": true,
    "recallTokenBudget": 2000,
    "minQueryLength": 3,
    "commitTokenThreshold": 20000,
    "commitKeepRecentCount": 10,
    "profileTokenBudget": 10000,
    "skillCatalog": true,
    "skillCatalogTokenBudget": 1200,
    "resumeContextBudget": 32000,
    "opencode": {
      "timeoutMs": 30000,
      "repoContext": true,
      "repoContextCacheTtlMs": 60000
    }
  }
}
```

配置項按優先順序從高到低解析：`OPENVIKING_*` 環境變數、工作區的 `.openviking/config.json` 與 `config.local.json`、`plugin.opencode`、`plugin`，最後是內建預設值。`autoRecall: false` 關閉自動召回，`autoCapture: false` 讓外掛不再回寫對話。

每個 session 的第一條訊息會帶上一個隱藏的 `<openviking-context source="session-start">` 塊，裡面有你的 `profile.md`、`preferences/` 和 `entities/` 記憶索引，以及 `<available-skills>` skill 清單：先列你自己的 skill，再列 `viking://agent/skills` 下帳號共享的 skill；共享 skill 與你自己的 skill 同名時不再列出。agent 照某個 skill 做事之前，先用 `openviking_read` 讀它的 `SKILL.md`；建立或共享 skill 用 `openviking_add_skill`。`profileTokenBudget` 只管 profile 和記憶索引，skill 清單有獨立的預算 `skillCatalogTokenBudget`（預設 `1200`，環境變數 `OPENVIKING_SKILL_CATALOG_TOKEN_BUDGET`）。放不下描述時只列 skill 名，名字也列不全時末尾註明 `... +N more`；連一個名字都放不下時，只寫一行 skill 總數。設定 `skillCatalog: false`（`OPENVIKING_SKILL_CATALOG=0`）或把預算設為 `0` 即可關閉 skill 清單；沒有 skill，或服務端沒有 `GET /api/v1/skills` 介面時，這一塊會直接省略。

環境變數優先順序高於 `ovcli.conf`：

```bash
export OPENVIKING_API_KEY="your-api-key-here"
export OPENVIKING_ACCOUNT="default"   # 可選，僅 trusted-mode 部署需要
export OPENVIKING_USER="opencode"     # 可選，僅 trusted-mode 部署需要
export OPENVIKING_PEER_ID="opencode"  # 可選，peer 維度記憶路由需要
```

API key 會由 hooks 和 MCP proxy 作為 `Authorization: Bearer ...` 傳送；`account` 和 `user` 是 trusted-mode headers；`peerId` 會作為 `X-OpenViking-Actor-Peer` 和捕獲 session message 的 `peer_id` 使用。

## 驗證

安裝後重啟 OpenCode。進入 OpenCode session 後，外掛應暴露 `openviking` MCP server，透傳服務端完整 MCP 工具集（16 個工具）。OpenCode 會給 MCP 工具加 `openviking_` 字首：

- `openviking_find`、`openviking_search`（`openviking_search` 的 `mode="context"` 替代原 recall 工具）
- `openviking_read`、`openviking_list`、`openviking_tree`、`openviking_grep`、`openviking_glob`
- `openviking_remember`、`openviking_write`、`openviking_edit`、`openviking_add_resource`、`openviking_add_skill`
- `openviking_list_watches`、`openviking_cancel_watch`、`openviking_forget`、`openviking_health`

可以讓 OpenCode 搜尋或瀏覽 Business Data Platform memory。執行時狀態和錯誤日誌會寫入：

```bash
~/.config/opencode/openviking/openviking-memory.log
~/.config/opencode/openviking/openviking-session-state.json
```

## 故障排查

| 問題 | 排查方向 |
|------|----------|
| 外掛沒有載入 | 確認 `~/.config/opencode/opencode.json` 引用了 `@openviking/opencode-plugin`；原始碼安裝時確認 `~/.config/opencode/plugins/openviking.js` 存在 |
| 載入時報找不到 `lib/shared/*.mjs` | 原始碼複製前沒有執行 `sync.mjs`。在倉庫根目錄執行 `node examples/memory-plugin-shared/sync.mjs` 後重新複製 `lib/` |
| MCP tools 連到了錯誤的 server | 檢查 `~/.openviking/ovcli.conf`，或用 `OPENVIKING_*` 環境變數；`OPENVIKING_CLI_CONFIG_FILE` 可讓外掛改讀另一份 ovcli.conf |
| Business Data Platform 返回 401 / 403 | 檢查 `OPENVIKING_API_KEY`；trusted-mode 部署還要檢查 `OPENVIKING_ACCOUNT` 和 `OPENVIKING_USER` |
| recall 為空 | 確認 Business Data Platform server 中已有 memories/resources，且 `autoRecall` 沒有被設成 `false` |
| 本地 `openviking_add_resource` 失敗 | 傳入檔案路徑而不是目錄；目前還不支援自動上傳本地目錄 |

完整 tools、配置欄位和執行時檔案說明見 [外掛 README](https://github.com/volcengine/OpenViking/tree/main/examples/opencode-plugin)。

## 參見

- [整合能力參考](./16-capability-reference.md)
