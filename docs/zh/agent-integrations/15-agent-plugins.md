# Agent Plugins 1.0 插件包

[Agent Plugins 1.0](https://agent-plugins.org/specification) 是一套與廠商無關的 AI 編碼 Agent 外掛打包規範。一個外掛就是一個普通目錄：`plugin.json` 清單、`skills/` 下自動發現的 Agent Skills，以及可選的 `mcp.json` MCP 服務宣告。所有符合規範的客戶端都以同樣的方式載入它 —— 不再需要為每個客戶端各寫一套接入。

Business Data Platform 的這個外掛包位於倉庫的 [`agent-plugins/`](https://github.com/volcengine/OpenViking/tree/main/agent-plugins) 目錄。

## 目錄結構

```
agent-plugins/
├── plugin.json                          # Agent Plugins 1.0 清單（name: openviking）
├── mcp.json                             # 一個 stdio MCP server："openviking"
├── servers/
│   ├── mcp-proxy.mjs                    # stdio -> streamable-HTTP 代理，轉發到服務端 /mcp
│   └── shared/                          # 由 examples/memory-plugin-shared/lib 生成
├── skills/openviking-memory/SKILL.md    # 教模型完成「召回 + 沉澱」閉環
├── skills/ov-experience-memory/SKILL.md # 檢索並應用以往任務的 Experience
├── skills/ov-memory-troubleshoot/SKILL.md # 追溯記憶問題的會話依據
├── skills/openviking-skills/SKILL.md    # 查詢、使用、建立和共享 Business Data Platform 中的 skill
└── plugin.test.mjs                      # node --test 規範一致性校驗
```

零 npm 依賴 —— 代理和測試只用 Node.js 標準庫（需要 Node 18+ 以獲得全域 `fetch`）。

## 安裝

1. 準備一個可訪問的 Business Data Platform 服務。還沒有的話，先按 [快速開始](../getting-started/02-quickstart.md) 部署；本地預設端點是 `http://127.0.0.1:1933`。
2. 讓你的 Agent Plugins 客戶端指向 `agent-plugins/` 目錄。各客戶端的安裝命令或外掛目錄不同，請查閱其文件。載入時客戶端會：
   - 按 `mcp.json` 註冊名為 `openviking` 的 MCP server，以 stdio 方式執行 `node <plugin>/servers/mcp-proxy.mjs`；
   - 從 `skills/` 發現 `openviking-memory`、`ov-experience-memory`、`ov-memory-troubleshoot` 和 `openviking-skills` 技能。
3. 配置憑據（見下節）後開始會話。模型即可使用 `find` / `search` / `read` / `list` / `grep` / `glob` / `remember` / `add_resource` / `forget` / `health`，較新的服務端還提供 `tree` / `write` / `edit` / `add_skill`。

## 為什麼用 stdio 代理，而不是 `streamable-http`

Business Data Platform 服務端本身在 `/mcp` 上就是 streamable HTTP，但 `mcp.json` 裡直接寫 `streamable-http` 條目無法做到可移植：服務地址因部署而異（有人是 localhost，有人是遠端），而規範禁止把憑據寫進靜態 `headers`。stdio 代理同時解決這兩點 —— 它在執行時從與 `ov` CLI 相同的本地來源解析 URL 和 API Key，逐請求注入，再把 JSON-RPC 原樣通過 streamable HTTP 轉發。

## 憑據解析順序

從高到低 —— 與 `ov` CLI 及其他 Business Data Platform 外掛完全一致：

1. 環境變數：`OPENVIKING_URL`（或 `OPENVIKING_BASE_URL`）、`OPENVIKING_MCP_URL`、`OPENVIKING_API_KEY`（或 `OPENVIKING_BEARER_TOKEN`）、`OPENVIKING_ACCOUNT`、`OPENVIKING_USER`、`OPENVIKING_PEER_ID`、`OPENVIKING_AUTH_MODE`
2. `~/.openviking/ovcli.conf`（`url`、`api_key`、`account` / `account_id`、`user` / `user_id`、`actor_peer_id` / `peer_id`），其後是它的 `plugin.agent_plugins` 與共享 `plugin` 鍵（`apiKey`、`accountId`、`userId`、`authMode`）—— 可用 `OPENVIKING_CLI_CONFIG_FILE` 覆蓋路徑
3. `~/.openviking/ov.conf` 的 `agent_plugins` 段（`apiKey`、`accountId`、`userId`、`peerId`、`authMode`）—— 可用 `OPENVIKING_CONFIG_FILE` 覆蓋路徑
4. `~/.openviking/ov.conf` 的 `server` 段（`url`，或 `host` / `port`，以及 `root_api_key`）
5. 預設值：`http://127.0.0.1:1933`，不鑑權（本地模式）

`OPENVIKING_MCP_URL` 覆蓋的是推匯出的 `<url>/mcp` 端點，而不是 base URL。

`OPENVIKING_CREDENTIAL_SOURCE`（或 `OPENVIKING_CREDENTIALS_SOURCE`）把整條鏈釘在某一端：`env` 只認環境變數，`cli`（同義寫法還有 `ovcli` / `file` / `config`）只認 ovcli.conf。預設的 `auto` 在 ovcli.conf 帶憑據、且上面這些環境變數一個都沒設時釘向 ovcli.conf，否則按整條鏈解析。釘在 ovcli.conf 時，環境變數裡的憑據和 `OPENVIKING_MCP_URL` 會被跳過。key 仍依次回落到 `plugin` 鍵、`agent_plugins` 段，最後是 `server.root_api_key`，所以只寫了 `url` 的舊安裝仍能用原來的 key；account 和 user 只回落到 `plugin` 鍵。`env` 模式兩個檔案都不讀。

`~/.openviking/ovcli.conf`:

```json
{
  "url": "https://openviking.example.com",
  "api_key": "your-api-key"
}
```

配置檔案的改動會被執行中的代理自動讀取，無需重啟。

除錯：設定 `OPENVIKING_DEBUG=1`，日誌以 JSON Lines 寫入 `~/.openviking/logs/agent-plugins.log`（路徑可用 `OPENVIKING_DEBUG_LOG` 覆蓋）。`OPENVIKING_TIMEOUT_MS` 可調整預設 15s 的單請求超時。

## 能力邊界：規範不含 hooks

Agent Plugins 1.0 只覆蓋 skills 和 MCP servers；hooks、commands、agents 被有意排除在本版本之外，因為它們在各客戶端之間語義差異太大。因此這個包提供的是**可移植的召回 + 寫入能力面**，由模型驅動而非生命週期事件驅動：**自動會話捕獲和 prompt 前自動召回不在此範圍內**。

作為補償，內建的 `openviking-memory` 技能直接把這套閉環教給模型 —— 任務開始時用 `find` / `search` + `read` 召回（需要組裝上下文時使用 `search` 的 `mode="context"`），過程中和結束後用 `remember` / `write` / `edit` 沉澱，並給出使用召回內容時的優先順序與安全規則。

內建的 `ov-experience-memory` 技能讓模型在執行類任務前檢索 `viking://~/memories/experiences`，並讀取適用的 Experience 檔案。在這個包裡它只做檢索：沒有會話捕獲，這些讀取不會關聯回所用的 Experience，也不會產生新的軌跡。它檢索到的 Experience 來自會捕獲會話的 harness。

內建的 `openviking-skills` 技能覆蓋存放在 Business Data Platform 裡的 skill 本身：用 `find(context_type="skill")` 查詢、讀取並按 `SKILL.md` 執行、用 `add_skill` 新建或替換、從 Git 或本地資料夾安裝、共享給整個帳號，以及把本地 skill 目錄遷入 Business Data Platform。這裡沒有會話啟動 hook，也就沒有 `<available-skills>` 清單，所以該技能讓模型自己檢索 skill，而不是從清單裡讀。

**如果你的 harness 支援 hooks 機制，推薦使用專屬外掛。** hook 驅動的召回與捕獲不需要模型花費工具呼叫、也不依賴模型「想起來要記」，比技能驅動的閉環更省 token、也更可靠。本 Agent Plugins 包適用於沒有 hooks 的 harness，或你希望用同一個包覆蓋多個客戶端的場景。

Claude Code、Codex、Cursor、TRAE / TRAE CN、ZCode、OpenCode、pi 共用同一個安裝指令碼。它會依次詢問介面語言、要安裝的 harness、下載源和 Business Data Platform 憑據，所有步驟冪等，重複執行安全：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/volcengine/OpenViking/main/examples/memory-plugin-shared/install.sh)
```

GitHub 訪問受限的地區，從火山引擎 TOS 映象運行同一個指令碼：

```bash
bash <(curl -fsSL https://ovrelease.tos-cn-beijing.volces.com/memory-plugin-shared/install.sh)
```

| Harness | 專屬整合 |
|---------|----------|
| Claude Code | [Claude Code 記憶外掛](./02-claude-code.md) |
| Codex | [Codex 記憶外掛](./04-codex.md) |
| OpenCode | [OpenCode 插件](./10-opencode.md) |
| Cursor | [Cursor 記憶整合](./12-cursor.md) |
| TRAE / TRAE CN | [TRAE 記憶整合](./13-trae.md) |
| pi | [pi Coding Agent 擴充](./11-pi.md) — 使用官方 MCP 客戶端，把服務端工具註冊為原生工具 |
| OpenClaw | [OpenClaw 外掛](./03-openclaw.md) — 獨立安裝流程 |
| ZCode | [社群整合](./08-community-plugins.md) |

按規範，客戶端專屬的整合後續也可以放進同一個包裡 —— 使用反向域名命名的目錄（如 `com.example.client/`）或清單的 `extensions` 欄位 —— 且不會影響其他客戶端。

## 開發

```bash
node --test agent-plugins/plugin.test.mjs
```

`plugin.test.mjs` 會校驗：清單的 schema URL 及兩個清單的規範版本一致、外掛 name 規則、清單根欄位閉集、semver、每個 `skills/*` 子目錄都有帶 `name` + `description` frontmatter 且 `name` 與目錄同名的 `SKILL.md`、`mcp.json` 引用的檔案存在且不逃逸外掛根目錄，以及包內所有 `.mjs` 都能通過 `node --check`。

`servers/shared/*.mjs` 是 `examples/memory-plugin-shared/lib` 的生成副本 —— 請改共享庫後重新執行 `node examples/memory-plugin-shared/sync.mjs`；一旦漂移，`examples/memory-plugin-shared/sync.test.mjs` 會失敗。兩個測試檔案都已接入 CI。

## 參見

- [整合能力參考](./16-capability-reference.md)
