# Claude Code 記憶外掛

為 [Claude Code](https://docs.claude.com/zh-CN/docs/claude-code/overview) 新增跨專案、跨會話（session）的長期記憶功能。安裝完成後，每輪對話均會自動召回相關記憶並捕獲新內容，無需模型主動呼叫任何工具。

原始碼：[examples/claude-code-memory-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/claude-code-memory-plugin) | [部落格：動機與效果展示](https://blog.openviking.ai/post/openviking-coding-agent/)

## 安裝

Claude Code 和 Codex 共用同一個安裝指令碼。它會依次詢問介面語言（English/中文）、要安裝的 harness、下載源和 Business Data Platform 憑據；所有步驟冪等，重複執行安全。

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/volcengine/OpenViking/main/examples/memory-plugin-shared/install.sh)
```

GitHub 訪問受限的地區，從火山引擎 TOS 映象運行同一個安裝指令碼（或在下載源提問時選擇「TOS 映象」）：

```bash
bash <(curl -fsSL https://ovrelease.tos-cn-beijing.volces.com/memory-plugin-shared/install.sh)
```

> **Claude Code 走 TOS 的注意事項**：TOS 渠道註冊的是本地目錄 marketplace，**無法自動更新**——更新請重跑安裝指令碼。（Codex 走 TOS 時安裝自 TOS 託管的 git 倉庫，保留遠端更新能力。）

現在不再需要任何 shell wrapper：外掛自帶的 stdio MCP 代理會在執行時讀取 `~/.openviking/ovcli.conf`（或 `OPENVIKING_*` 環境變數），與 hooks 使用同一套配置鏈。

使用一段時間後，即便在全新的對話中提及過往的話題，Claude Code 也能準確回憶起來。

<details>
<summary><b>手動安裝</b></summary>

如果您傾向於手動安裝：

1. **配置連線** — 手寫 `~/.openviking/ovcli.conf`（`url`、`api_key`，可選 `account`/`user`），或裝完後執行外掛自帶嚮導 `node <外掛目錄>/scripts/setup.mjs`。

2. **從遠端 marketplace 安裝外掛**（無需 clone 倉庫）：

   ```bash
   claude plugin marketplace add https://raw.githubusercontent.com/volcengine/OpenViking/main/.claude-plugin/marketplace.json
   claude plugin install openviking-memory@openviking
   ```

   開發場景也可註冊本地 checkout：`claude plugin marketplace add "<倉庫路徑>/examples"`，外掛 id 相同。

3. **啟動 Claude Code** — 執行後輸入 `/mcp` 命令，確認 Business Data Platform 條目已連線。

> 尚未建立 `ovcli.conf`？請先按照 [部署指南 → CLI](../guides/03-deployment.md#cli) 的說明進行配置。
>
> 使用純本地模式（`http://127.0.0.1:1933`，無鑑權）？您可以跳過第 1 步，外掛將直接使用本地預設值。
>
> 使用 Claude Code < 2.0 版本？安裝指令碼會自動識別並回退到 `claude mcp add` + hooks 合併；詳見 [外掛 README 的相容模式章節](https://github.com/volcengine/OpenViking/blob/main/examples/claude-code-memory-plugin/README_CN.md#相容模式claude-code--20)。

</details>

## 驗證

啟動 `claude`，隨後：

- 輸入 `/plugins` → 在 Installed 列表中應能找到 **openviking-memory**（其子項 **openviking** MCP 應顯示為已連線狀態）。
- 輸入 `/mcp` → Business Data Platform 對應的條目應顯示您的伺服器 URL 及有效的認證資訊。
- 輸入 `/openviking-memory:ov` → 檢視伺服器狀態、身份資訊、召回/注入的統計資料以及功能開關狀態。

若外掛未正常工作，可設定環境變數 `OPENVIKING_DEBUG=1`，並檢視日誌檔案 `~/.openviking/logs/cc-hooks.log` 以排查問題。

## 工作原理

外掛通過掛載到 Claude Code 的不同生命週期節點來發揮作用：

- **每次使用者輸入前** — 搜尋 Business Data Platform 資料庫並注入相關記憶。
- **每輪迴復後** — 自動捕獲並存儲新的對話內容。
- **會話（session）啟動時** — 注入使用者畫像、記憶索引和 skill 清單。
- **上下文壓縮（compact）前及會話結束時** — 提交所有待處理的訊息記錄。
- **啟動子代理（subagent）時** — 為其分配相互隔離的記憶會話。
- **原生檔案工具訪問 `viking://` 路徑前** — 攔截該呼叫，並提示改用對應的 Business Data Platform MCP 工具；對 skill 路徑的 `Write` 或 `Edit` 會被引導到 `add_skill`。

所有資料寫入操作均為非同步執行，不會阻塞當前的對話程序。

skill 清單就是 `<available-skills>` 塊，列出存放在 Business Data Platform 中的 skill：先列你自己在 `viking://~/skills` 下的，再列帳號內共享在 `viking://agent/skills` 下的，每個附一句簡短描述。要照清單裡的 skill 執行前，Claude 會先用 Business Data Platform 的 `read` 工具讀取它的 `SKILL.md`。清單有獨立的 Token 預算：放不下描述時只列名稱，連一個名稱都放不下時縮成一行總數。外掛自帶的 `openviking-skills` skill 告訴 Claude 如何查詢和使用 Business Data Platform 中的 skill，如何用 `add_skill` MCP 工具建立、安裝和共享 skill，如何刪除 skill，以及在你要求時如何把 `~/.claude/skills` 等本地 skill 遷入 Business Data Platform。

工具呼叫和結果會作為獨立的 `tool` part 捕獲，`tool_output` 原樣上報。截斷由服務端負責：超過 `tool_output_externalization.threshold_chars`（預設 `20000`）的輸出會寫入 session 的 tool-result 儲存，part 中只保留 synopsis stub 和 `tool_output_ref`，原文仍可通過 [`/api/v1/sessions/{id}/tool-results`](../api/05-sessions.md#read-tool-result) 讀回。

<details>
<summary><b>配置</b></summary>

配置項的讀取優先順序為：環境變數 > `ovcli.conf` > `ov.conf` > 內建預設值（`http://127.0.0.1:1933`，無鑑權）。

| 環境變數 | 預設值 | 說明 |
|---------|--------|------|
| `OPENVIKING_AUTO_RECALL` | `true` | 每次使用者輸入前自動觸發記憶召回 |
| `OPENVIKING_RECALL_LIMIT` | `10` | 遺留寬度覆蓋，會轉換為各分類 coding 配額 |
| `OPENVIKING_RECALL_TOKEN_BUDGET` | `2000` | 最終 raw-find fallback 的內聯 Token 預算 |
| `OPENVIKING_AUTO_CAPTURE` | `true` | 每輪對話結束後自動捕獲新記憶 |
| `OPENVIKING_SKILL_CATALOG` | `true` | 會話啟動時注入 `<available-skills>` skill 清單 |
| `OPENVIKING_SKILL_CATALOG_TOKEN_BUDGET` | `1200` | `<available-skills>` 的 Token 預算，與使用者畫像的預算相互獨立；設為 `0` 即關閉清單 |
| `OPENVIKING_SESSION_START_MAX_BYTES` | `9500` | SessionStart 注入的總位元組上限，保證整塊低於 Claude Code 的 10,000 字元限制、直接進入上下文而不是被存成檔案；resume 或 compact 時會話歸檔最多佔一半。設為 `0` 取消上限 |
| `OPENVIKING_BYPASS_SESSION` | `false` | 停用當前會話的所有 Hook |
| `OPENVIKING_BYPASS_SESSION_PATTERNS` | `""` | 通過 CSV 格式的 glob 模式匹配並自動跳過特定會話 |
| `OPENVIKING_RECALL_QUERY_FILTERS` | `""` | CSV 格式的 sed 風格正則規則，在 prompt 變成檢索 query 前生效（[語法與示例](https://github.com/volcengine/OpenViking/blob/main/examples/claude-code-memory-plugin/README.md#input-filters)） |
| `OPENVIKING_CAPTURE_FILTERS` | `""` | CSV 格式的 sed 風格正則規則，作用於每個被捕獲的回合（同一套語法） |
| `OPENVIKING_MEMORY_ENABLED` | (auto) | 強制開啟或關閉外掛 |
| `OPENVIKING_DEBUG` | `false` | 將除錯日誌輸出至 `~/.openviking/logs/cc-hooks.log` |

這些旋鈕大多也可以寫在 `ovcli.conf` 的 `plugin` 段下——見[外掛配置](../configuration/02-client.md#外掛配置)。兩個過濾器 knob 尤其建議寫在那裡，用 JSON 陣列，因為環境變數形式會按逗號切分。

如果更看重召回響應速度，請參閱[低延遲召回](./01-overview.md#低延遲召回)，其中說明了如何通過環境變數或 `ovcli.conf` 關閉查詢擴充與結果壓縮。

在多租戶場景下，請額外配置 `OPENVIKING_ACCOUNT` 和 `OPENVIKING_USER`。完整的環境變數列表請參閱 [外掛 README](https://github.com/volcengine/OpenViking/blob/main/examples/claude-code-memory-plugin/README.md#configuration)。

</details>

## 工作區 peer

記憶按你所在倉庫派生出的 peer 歸檔，因此同一個專案在不同 clone、worktree 和子目錄下共用同一份記憶。預設的 `peer.source: "git"` 取倉庫歸一化後的 `origin` URL——`origin` 為 `git@github.com:volcengine/OpenViking.git` 時，peer 就是 `github.com-volcengine-openviking`——其次是倉庫根路徑；不在倉庫中則完全不傳送 peer，在那裡記下的內容進入使用者級空間 `viking://user/<you>/memories`。fork 的 `origin` 不同，因此預設是獨立的 peer。

可通過 `OPENVIKING_PEER_SOURCE`、`ovcli.conf` 中的 `plugin.peerSource`，或工作區 `.openviking/config.json`（`"version": 1` 的配置檔案，可提交給團隊共用）中的 `peer.source` 修改：`"cwd"` 恢復此前的行為——把工作目錄路徑中的非字母數字字元全部替換成 `-`；`"none"` 表示不傳送 peer；也可以用 `"team-{dir}"` 這樣的模板自定義。要[讓一個不是倉庫的目錄擁有獨立記憶](../configuration/02-client.md#讓一個目錄擁有獨立記憶)，在該目錄下建立 `.openviking/config.json`，內容為 `{"version": 1, "peer": {"id": "my-project"}}`。此前按工作目錄派生的 peer 下寫入的記憶仍能被召回，無需遷移。分層優先順序和工作區配置檔案的完整 schema 見[客戶端配置 → 工作區配置](../configuration/02-client.md#工作區配置)。

## 狀態行

外掛會在 Claude Code 的輸入框下方顯示一行 Business Data Platform 狀態列，用於指示：連線狀態、召回條數、捕獲進度以及當前會話狀態。關於狀態列各部分的詳細含義與自定義配置方法，請參閱 [STATUSLINE.md](https://github.com/volcengine/OpenViking/blob/main/examples/claude-code-memory-plugin/STATUSLINE.md)。

## 故障排查

| 現象 | 原因 | 修復 |
|------|------|------|
| 外掛未啟用 | 未找到 `ov.conf` 或 `ovcli.conf` 配置檔案 | 執行 [安裝指令碼](#安裝)，或手動設定 `OPENVIKING_MEMORY_ENABLED=1` 配合 URL/API_KEY 使用。 |
| Hook 已觸發但召回結果為空 | 伺服器未啟動或 URL 配置錯誤 | 執行命令測試連通性：`curl "$(jq -r '.url' ~/.openviking/ovcli.conf)/health"` |
| MCP 工具連線到了 `127.0.0.1` 而非遠端伺服器 | `~/.openviking/ovcli.conf` 中沒有 `url`（代理回退到本地預設值） | 修正 `ovcli.conf`（或執行 `node <外掛目錄>/scripts/setup.mjs`）後重啟 Claude Code |
| MCP 工具呼叫報認證錯誤 | 當前 ovcli 配置沒有 authenticated server 所需的有效 `api_key` | 更新 `ovcli.conf` 中的 `api_key`；stdio 代理在認證失敗後會重新讀取配置 |
| 遠端認證失敗 (401 / 403) | API Key 錯誤或缺少租戶 Header | 檢查 `OPENVIKING_API_KEY` 是否正確；多租戶環境下還需核對 `OPENVIKING_ACCOUNT` 和 `OPENVIKING_USER` |

## 參見

- [整合能力參考](./16-capability-reference.md)
- [部落格：在 Claude Code / Codex 中接入 Business Data Platform](https://blog.openviking.ai/post/openviking-coding-agent/) — 探討為 Coding Agent 新增長期記憶的動機與實際效果。
- [外掛 README](https://github.com/volcengine/OpenViking/blob/main/examples/claude-code-memory-plugin/README.md) — 檢視完整的環境變數列表、Hook 執行細節及系統架構圖。
- [MCP 客戶端](./06-mcp-clients.md) — 瞭解 MCP 工具引數及其他客戶端整合指南。
- [部署指南 → CLI](../guides/03-deployment.md#cli) — 學習 `ovcli.conf` 的具體配置方法。
