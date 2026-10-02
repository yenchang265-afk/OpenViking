# 安裝 OpenViking OpenCode 統一外掛

這個外掛新增了一個面向 OpenCode 的統一 OpenViking 外掛：

- 面向 memory、resources 和 code context 的 OpenViking MCP 工具
- 長期記憶、session 同步、生命週期邊界 commit、自動 recall

這是倉庫中唯一繼續維護的 OpenCode 外掛示例。這個外掛不再安裝 `skills/openviking/SKILL.md`，也不要求 agent 使用 `ov` 命令。模型工具由 Claude Code 和 Codex 記憶外掛同款的 stdio MCP proxy 提供。

## 前置條件

需要先準備：

- OpenCode
- OpenViking HTTP Server
- Node.js 18+
- 如果服務端啟用了認證，需要可用的 OpenViking API Key

建議先啟動 OpenViking：

```bash
openviking-server --config ~/.openviking/ov.conf
```

檢查服務：

```bash
curl http://localhost:1933/health
```

## 安裝方式一：釋出包安裝

普通使用者推薦通過 OpenCode 的 package plugin 機制啟用：

```json
{
  "plugin": ["@openviking/opencode-plugin"]
}
```

## 安裝方式二：原始碼安裝

用於開發除錯或 PR 測試。OpenCode 推薦外掛目錄：

```bash
~/.config/opencode/plugins
```

在倉庫根目錄執行：

```bash
node examples/memory-plugin-shared/sync.mjs
mkdir -p ~/.config/opencode/plugins/openviking
cp examples/opencode-plugin/wrappers/openviking.js ~/.config/opencode/plugins/openviking.js
cp examples/opencode-plugin/index.mjs examples/opencode-plugin/package.json ~/.config/opencode/plugins/openviking/
cp -r examples/opencode-plugin/lib ~/.config/opencode/plugins/openviking/
cp -r examples/opencode-plugin/servers ~/.config/opencode/plugins/openviking/
```

`sync.mjs` 會生成 `lib/shared/`，外掛和 MCP 代理都從這裡 import 共享模組。這個目錄不在 git 裡，所以複製前要先執行；之後每次 `git pull` 也要重新執行再複製。

安裝後結構應類似：

```text
~/.config/opencode/plugins/
├── openviking.js
└── openviking/
    ├── index.mjs
    ├── package.json
    ├── lib/
    └── servers/
```

頂層 `openviking.js` 只負責把 OpenCode 能發現的一級 `.js` 入口轉發到外掛目錄：

```js
export { OpenVikingPlugin, default } from "./openviking/index.mjs"
```

這個 wrapper 只用於上面這種原始碼安裝目錄結構。npm 包安裝會通過 `package.json` 直接載入 `index.mjs`。
原始碼安裝請使用 `.js` wrapper；OpenCode 的本地外掛掃描器會發現 JavaScript/TypeScript 外掛檔案。

如果你使用 npm 包方式安裝，也可以將 `examples/opencode-plugin` 作為一個普通 OpenCode 外掛包使用。

## 配置

行為旋鈕寫在共享的客戶端配置檔案裡：

```bash
~/.openviking/ovcli.conf
```

示例配置：

```json
{
  "url": "http://127.0.0.1:1933",
  "api_key": "your-api-key-here",
  "plugin": {
    "recallLimit": 6,
    "opencode": {
      "enabled": true,
      "mcpEnabled": true,
      "timeoutMs": 30000,
      "repoContext": true,
      "repoContextCacheTtlMs": 60000,
      "autoRecall": true,
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
      "resumeContextBudget": 32000
    }
  }
}
```

`plugin` 裡的鍵對所有 harness 生效；`plugin.opencode` 裡的鍵只對本外掛生效，並覆蓋前者。解析順序是 `OPENVIKING_*` 環境變數 → 工作區的 `.openviking/config.json`、`.openviking/config.local.json` 和本機 registry 條目 → `plugin.opencode` → `plugin` → 內建預設值。每個旋鈕的型別、預設值、取值範圍、環境變數名和相容的舊拼寫都宣告在 [`examples/memory-plugin-shared/lib/config-schema.mjs`](../memory-plugin-shared/lib/config-schema.mjs)。

`recallLimit` 是遺留的配額縮放輸入，不是最終結果上限。顯式設定為
1 到 5 時，有效總配額仍為 6，因為六個 coding 分類會各保留一個檢索槽位。

每個 session 的第一條訊息會帶上一個隱藏的 `<openviking-context source="session-start">` 塊，裡面有你的 `profile.md`、`preferences/` 和 `entities/` 記憶索引，以及 `<available-skills>` skill 清單：先列你自己的 skill，再列 `viking://agent/skills` 下帳號共享的 skill；共享 skill 與你自己的 skill 同名時不再列出。`profileTokenBudget` 只管 profile 和記憶索引，skill 清單有獨立的預算 `skillCatalogTokenBudget`（預設 `1200`，環境變數 `OPENVIKING_SKILL_CATALOG_TOKEN_BUDGET`）。放不下描述時只列 skill 名，名字也列不全時末尾註明 `... +N more`；連一個名字都放不下時，只寫一行 skill 總數。設定 `skillCatalog: false`（`OPENVIKING_SKILL_CATALOG=0`）或把預算設為 `0` 即可關閉 skill 清單；沒有 skill，或服務端沒有 `GET /api/v1/skills` 介面時，這一塊會直接省略。

推薦通過環境變數提供 API Key，而不是寫入配置檔案：

```bash
export OPENVIKING_API_KEY="your-api-key-here"
```

API key 會從環境變數或 `~/.openviking/ovcli.conf` 讀取，並由 hooks 和 MCP proxy 作為 `Authorization: Bearer ...` 傳送。`account` 和 `user` 是 trusted mode
身份頭，會作為 `X-OpenViking-Account`、`X-OpenViking-User` 傳送；`api_key`
模式的服務端從 key 裡取身份，外掛在那裡不發這兩個頭。
`peerId` 會作為 `X-OpenViking-Actor-Peer` 用於資料面的 memory/resource 請求；捕獲 session message 時仍寫入 body `peer_id`。需要 peer 維度路由時請顯式配置。

`OPENVIKING_API_KEY`、`OPENVIKING_ACCOUNT`、`OPENVIKING_USER`、
`OPENVIKING_PEER_ID`
優先順序高於 `ovcli.conf` 裡的同名配置。

進階場景可以用 `OPENVIKING_CLI_CONFIG_FILE` 指向其他路徑的 `ovcli.conf`。

### 僅 Hooks 模式

如果其他 MCP server 已經提供 OpenViking，可以關閉本外掛附帶的 MCP 註冊，同時保留生命週期 hooks：

```json
{
  "plugin": {
    "opencode": { "mcpEnabled": false }
  }
}
```

repository context、自動 recall、訊息 capture 和生命週期 commit 會繼續工作，也不會新增或覆蓋
OpenCode 的 `mcp.openviking` 配置。

## 驗證

修改外掛或 OpenViking 配置後，需要重啟 OpenCode。

進入新的 OpenCode session 後，可以讓 agent 瀏覽 OpenViking memory，或搜尋一個已索引的資源。外掛應暴露 OpenViking MCP server，OpenCode 中的工具名會帶 `openviking_` 字首：

- `openviking_search`、`openviking_find`
- `openviking_read`、`openviking_list`、`openviking_tree`、`openviking_grep`、`openviking_glob`
- `openviking_remember`、`openviking_write`、`openviking_edit`、`openviking_add_resource`、`openviking_add_skill`
- `openviking_list_watches`、`openviking_cancel_watch`、`openviking_forget`、`openviking_health`

如果行為異常，先檢視執行時檔案：

```bash
ls ~/.config/opencode/openviking/
tail -n 100 ~/.config/opencode/openviking/openviking-memory.log
```

如果使用本地 server，也確認 OpenViking 可訪問：

```bash
curl http://localhost:1933/health
```

## 可用 MCP 工具

外掛會通過 OpenCode config 註冊 OpenViking stdio MCP proxy。服務端實際返回的 `tools/list` 是最終工具清單；當前 OpenViking server 暴露：

- `openviking_search`：跨 memories/resources/skills 的深度語義檢索；使用 `mode="context"` 獲取面向當前任務、可直接注入的平衡上下文
- `openviking_find`：快速語義檢索
- `openviking_remember`：儲存重要事實或決策，供記憶提取
- `openviking_read`：讀取一個或多個 `viking://` 檔案
- `openviking_list`：列出 `viking://` 目錄
- `openviking_tree`：展示 `viking://` 目錄樹
- `openviking_grep`：精確文本或正則搜尋
- `openviking_glob`：glob 文件匹配
- `openviking_write`：建立、覆蓋或追加 `viking://` 檔案
- `openviking_edit`：對 `viking://` 檔案做精確字串替換
- `openviking_add_resource`：添加 URL、本地文件、sitemap 或 feed
- `openviking_add_skill`：用完整的 `SKILL.md` 文本（`data`）建立或替換 skill，或從 Git URL、本地 `SKILL.md`、skill 目錄或 `.zip`（`path`）安裝；傳 `target_uri="viking://agent/skills"` 則共享給整個帳號
- `openviking_forget`：在使用者明確確認後刪除 `viking://` URI
- `openviking_list_watches` / `openviking_cancel_watch`：檢視或取消資源 watch
- `openviking_health`：檢查 OpenViking server 健康狀態

使用建議：

- 概念性問題用 `openviking_search`
- 精確符號、函式名、類名、報錯字串用 `openviking_grep`
- 列舉檔案用 `openviking_glob`
- 讀取內容用 `openviking_read`
- 探索目錄結構用 `openviking_list`
- 照 `<available-skills>` 裡的某個 skill 做事之前，先用 `openviking_read` 讀它的 `SKILL.md`；建立、安裝或共享 skill 用 `openviking_add_skill`
- 刪除前必須先獲得使用者明確確認，再呼叫 `openviking_forget`
- 如果 agent 誤用 OpenCode 本地 `read`、`glob`、`grep` 工具訪問 `viking://` URI，外掛會阻止這次本地檔案系統呼叫，並提示改用 MCP 工具。
- `bash` 命令裡帶 `viking://` URI 時照常執行，外掛會在輸出末尾附一段提示，建議改用 MCP 工具；URI 本來就是命令引數時，agent 可以忽略這段提示。

## `openviking_add_resource` 本地文件

`openviking_add_resource` 支援三類輸入：

- 遠端 `http(s)` URL：直接呼叫 `/api/v1/resources`
- 本地檔案路徑：先呼叫 `/api/v1/resources/temp_upload`，再用返回的 `temp_file_id` 新增資源
- `file://` URL：按本地檔案處理

相對路徑會按 OpenCode 當前專案目錄解析。示例：

```text
openviking_add_resource(path="https://example.com/spec.md", to="viking://resources/spec")
openviking_add_resource(path="./docs/notes.md", to="viking://resources/notes.md")
openviking_add_resource(path="file:///home/alice/project/notes.md", description="project notes")
```

當前仍不支援本地目錄自動打 zip 上傳；傳入目錄時會返回明確錯誤。

## 執行時檔案

外掛預設會把執行時檔案寫入：

```bash
~/.config/opencode/openviking/
```

可能包含：

- `openviking-memory.log`
- `openviking-session-state.json`

可以通過 `plugin.opencode` 裡的 `dataDir` 修改這個目錄。

這些是本地執行時檔案，不建議提交到版本庫。

## 故障排查

| 問題 | 排查方向 |
|------|----------|
| 外掛沒有載入 | package 安裝檢查 `~/.config/opencode/opencode.json` 是否包含 `@openviking/opencode-plugin`；原始碼安裝檢查 `~/.config/opencode/plugins/openviking.js` 是否存在 |
| 載入時報找不到 `lib/shared/*.mjs` | 原始碼複製前沒有執行 `sync.mjs`。在倉庫根目錄執行 `node examples/memory-plugin-shared/sync.mjs` 後重新複製 `lib/` |
| MCP tools 連到了錯誤的 server | 檢查 `~/.openviking/ovcli.conf`，或用 `OPENVIKING_*` 環境變數 / `OPENVIKING_CLI_CONFIG_FILE` 指向正確配置 |
| OpenViking 返回 401 / 403 | 檢查 `OPENVIKING_API_KEY`；trusted-mode 部署還要檢查 `OPENVIKING_ACCOUNT` 和 `OPENVIKING_USER` |
| recall 為空 | 確認 OpenViking 中已有 memories/resources，並且 `autoRecall` 為 `true` |
| 本地 `openviking_add_resource` 失敗 | 傳入檔案路徑而不是目錄；目前還不支援自動上傳本地目錄 |
