# Codex 記憶外掛

本外掛旨在為 [Codex](https://developers.openai.com/codex) 提供持久化的跨會話（session）記憶功能。只需安裝一次，即可實現：在會話開始時載入 OpenViking profile、記憶索引和 skill 清單，在每次使用者輸入前自動召回相關記憶，在每輪對話結束後進行增量捕獲，並在上下文壓縮（compaction）前將完整記錄提交給記憶抽取器。同時，該外掛將 Codex 連線至 OpenViking 的 `/mcp` 端點，使模型能夠直接呼叫 `find`、`search`、`read`、`remember` 等工具來主動管理記憶。

原始碼：[examples/codex-memory-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/codex-memory-plugin) | [部落格：動機與效果展示](https://blog.openviking.ai/post/openviking-coding-agent/)

## 安裝

Claude Code 和 Codex 共用同一個安裝指令碼。它會依次詢問介面語言（English/中文）、要安裝的 harness、下載源和 OpenViking 憑據；所有步驟冪等，可安全地重複執行。

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/volcengine/OpenViking/main/examples/memory-plugin-shared/install.sh)
```

TraeCode CLI 2.0 可以直接安裝這一 Codex 格式外掛，預設安裝入口是 `--harness trae-cli`：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/volcengine/OpenViking/main/examples/memory-plugin-shared/install.sh) \
  --harness trae-cli
```

GitHub 訪問受限的地區，從火山引擎 TOS 映象運行同一個安裝指令碼（或在下載源提問時選擇「TOS 映象」）。Codex 走 TOS 時安裝自 TOS 託管的 git 倉庫，保留遠端更新能力：

```bash
bash <(curl -fsSL https://ovrelease.tos-cn-beijing.volces.com/memory-plugin-shared/install.sh)
```

現在不再需要任何 shell wrapper——外掛自帶的 stdio MCP 代理會在執行時讀取 `~/.openviking/ovcli.conf`（或 `OPENVIKING_*` 環境變數），與 hooks 使用同一套配置鏈。安裝完成後啟動 Codex（TraeCode CLI 2.0 是 `trae-cli`）：

```bash
codex
```

### 首次啟動：信任 hooks

外掛的 hooks 對 Codex 是新的，啟動時會先停在一次信任確認上，選 **Trust all and continue**；想先看一眼 hook 命令就選 Review hooks：

```text
Hooks need review
6 hooks are new or changed.
Hooks can run outside the sandbox after you trust them.

  1. Review hooks
> 2. Trust all and continue
  3. Continue without trusting (hooks won't run)
```

全新安裝會一次列出外掛註冊的全部 6 個 hook。之後每次外掛更新只要動了 hook，Codex 都會再攔一次，數字是這次新增或改動的條數（比如只改了一個就是 `1 hook is new or changed`），同樣選 Trust all and continue。

選第 3 項或錯過這一步，hooks 就不會執行：MCP 工具仍能呼叫，但自動召回和捕獲全部停擺。要恢復，得讓兩個彼此獨立的開關都處於開啟狀態：

- `/hooks` — hook 的信任與開關，把標著 *New hook - review required* 或 *Modified since last trusted* 的條目信任並開啟。
- `/plugins` — 外掛本身的啟用狀態，確認 `openviking-memory` 是 enabled。

任何一邊是關著的，自動召回和捕獲都不會發生。

<details>
<summary><b>手動安裝</b></summary>

前置條件：需安裝 Node.js >= 22、Codex >= 0.130.0，並啟用 `plugin_hooks` 特性。

1. **配置連線** — 手寫 `~/.openviking/ovcli.conf`（`url`、`api_key`，可選 `account`/`user`），或裝完後執行外掛自帶嚮導 `node <外掛目錄>/scripts/setup.mjs`。

2. **從遠端 marketplace 安裝外掛**：

   ```bash
   codex plugin marketplace add volcengine/OpenViking
   codex plugin add openviking-memory@openviking
   ```

   若你的 Codex 版本未預設啟用 plugin hooks，在 `~/.codex/config.toml` 中加上 `[features]` → `plugin_hooks = true`。之後可用 `codex plugin marketplace upgrade openviking` 更新。

</details>

## 驗證

啟動 `codex` 後，當前會話首次提交 prompt 時觸發的 `SessionStart` 會載入 profile，之後外掛將在每次使用者輸入前自動召回相關記憶。若設定環境變數 `OPENVIKING_DEBUG=1`，則會將相關事件日誌寫入 `~/.openviking/logs/codex-hooks.log`。
TraeCode CLI 2.0 使用者啟動 `trae-cli`，並可用 `trae-cli plugin list` 確認外掛已啟用。

## 工作原理

本外掛深度掛載於 Codex 的生命週期之中：在 `SessionStart`（`startup`、`clear` 或 `resume`）階段，它會複用其他 coding-agent 整合共用的 CJK-aware profile 構建邏輯，注入 `profile.md`、`preferences/` 與 `entities/` 的 URI 和摘要索引，以及列出你的 OpenViking skill 的 `<available-skills>` 清單；在每次使用者輸入前，它會搜尋 OpenViking 並注入相關的記憶（觸發 `UserPromptSubmit`）；在每輪對話結束後，會將新的對話追加至當前會話（觸發 `Stop`）；在上下文壓縮前，補齊並提交（commit）完整的對話記錄（觸發 `PreCompact`）；線上程正常退出時提交整段會話（觸發 `SessionEnd`），以確保記憶抽取器能夠在完整的上下文環境中執行。shell 命令執行前（`Bash` 上的 `PreToolUse`），外掛會檢查命令裡是否帶 `viking://` URI：命令照常執行，模型會收到一條提示，建議改用 OpenViking MCP 工具；如果該 URI 是有意傳入的資料（例如 `ov` 命令引數），模型可以忽略這條提示。此外，在啟動新會話時，外掛還會清掃前次執行遺留的孤兒會話（orphan session）。恢復已有會話時，固定 profile 背景還會與最新的 archive digest 合併注入。

> **已知侷限**：`SessionEnd` 需要 Codex 0.145 及以上版本，且只在正常退出時觸發（`/quit`、`/exit`、連按兩次 `Ctrl-C`、EOF、`codex exec` 執行結束）。`SIGTERM`、直接關閉終端、`kill -9` 或崩潰都不會觸發；當 TUI 掛在 `codex app-server` 守護程序上時，該事件會被延後。這些會話——以及 Codex 低於 0.145 的所有會話（以及沒有該事件的 TraeCode CLI 版本）——由下一次 `SessionStart` 的閒置 TTL（生存時間，預設為 30 分鐘）清掃回收。

`<available-skills>` 清單先列你自己的 skill，再列 `viking://agent/skills` 下共享給整個帳號的 skill；共享 skill 與你自己的某個 skill 同名時不再列出。清單有獨立的 token 預算，不佔 profile 預算：放不下描述時只列名稱，連一個名稱都放不下時縮成一行總數。清單第一行提示模型：按某個 skill 操作前，先用 OpenViking `read` 工具讀取它的 `SKILL.md`。外掛在 `openviking-memory`、`ov-experience-memory` 之外還自帶 `openviking-skills` skill，告訴模型如何查詢 skill、用 MCP `add_skill` 工具新建或替換 skill、從 Git 或本地資料夾安裝 skill、把 skill 共享給整個帳號，以及在你要求時把本地 skill 遷移到 OpenViking。

工具呼叫和結果會作為獨立的 `tool` part 捕獲，`tool_output` 原樣上報。截斷由服務端負責：超過 `tool_output_externalization.threshold_chars`（預設 `20000`）的輸出會寫入 session 的 tool-result 儲存，part 中只保留 synopsis stub 和 `tool_output_ref`，原文仍可通過 [`/api/v1/sessions/{id}/tool-results`](../api/05-sessions.md#read-tool-result) 讀回。

<details>
<summary><b>配置</b></summary>

憑據來源：預設環境變數優先——只要設定了任一 `OPENVIKING_*` 憑據環境變數（`OPENVIKING_URL`/`OPENVIKING_BASE_URL`、`OPENVIKING_BEARER_TOKEN`/`OPENVIKING_API_KEY`、`OPENVIKING_ACCOUNT`、`OPENVIKING_USER`、`OPENVIKING_PEER_ID`），其取值就會覆蓋當前啟用的 `ovcli.conf`。只有在這些環境變數都未設定時，才由啟用的 `ovcli.conf`（`OPENVIKING_CLI_CONFIG_FILE` 或 `~/.openviking/ovcli.conf`）統一驅動 hook、MCP 代理和 Codex 內部執行的 `ov` 命令，此時 `ov config switch <name>` 會在下次啟動時生效。若希望在設定了憑據環境變數的情況下仍強制使用 ovcli 配置，可設定 `OPENVIKING_CREDENTIAL_SOURCE=cli`。兩者都未覆蓋的欄位依次回退到 `ovcli.conf`、`ov.conf` 和內建預設值。

| 環境變數 | 預設值 | 說明 |
|---------|--------|------|
| `OPENVIKING_URL` / `OPENVIKING_BASE_URL` | — | 完整的伺服器 URL |
| `OPENVIKING_API_KEY` | — | API 金鑰（將通過 `Authorization: Bearer` 標頭髮送） |
| `OPENVIKING_CLI_CONFIG_FILE` | `~/.openviking/ovcli.conf` | hook、MCP 和 Codex 內部 `ov` 命令共同使用的當前 CLI 配置 |
| `OPENVIKING_CREDENTIAL_SOURCE` | `auto` | `auto` 下已設定的憑據環境變數優先；設為 `cli` 強制使用啟用的 ovcli 配置；設為 `env` 只讀環境變數，兩個配置檔案都不讀 |
| `OPENVIKING_NO_AUTO_INJECT` | `false` | 關閉會話啟動階段的固定 profile/背景注入（包括 skill 清單），但不關閉逐 prompt 語義召回 |
| `OPENVIKING_PROFILE_TOKEN_BUDGET` | `10000` | `profile.md` 及 `preferences/`、`entities/` 索引共用的 CJK-aware token 預算 |
| `OPENVIKING_SKILL_CATALOG` | `true` | 在會話啟動注入中加入 `<available-skills>` 清單；設為 `false` 則不加 |
| `OPENVIKING_SKILL_CATALOG_TOKEN_BUDGET` | `1200` | `<available-skills>` 清單的 CJK-aware token 預算，獨立於 `OPENVIKING_PROFILE_TOKEN_BUDGET`；設為 `0` 同樣不加清單 |
| `OPENVIKING_SESSION_START_MAX_BYTES` | `9500` | SessionStart 注入的總位元組上限，保證低於 Codex 預設的 hook 輸出上限（約 10,000 位元組），模型拿到的是全文而不是截斷預覽；resume 時會話歸檔最多佔一半。設為 `0` 取消上限 |
| `OPENVIKING_CODEX_IDLE_TTL_MS` | `1800000` | `SessionStart` 閒置 TTL 清理閾值（毫秒） |
| `OPENVIKING_CODEX_LOCK_WAIT_MS` | `120000`（SessionEnd）、`40000`（PreCompact） | 捕獲類 hook 等待單會話狀態鎖的時長（毫秒） |
| `OPENVIKING_CODEX_COMMITTED_TTL_MS` | `2592000000` | 已提交會話的轉錄游標保留時長（毫秒），過期後刪除狀態檔案 |
| `OPENVIKING_RECALL_QUERY_FILTERS` | `""` | CSV 格式的 sed 風格正則規則，在 prompt 變成檢索 query 前生效（[語法與示例](https://github.com/volcengine/OpenViking/blob/main/examples/codex-memory-plugin/README.md#input-filters)） |
| `OPENVIKING_CAPTURE_FILTERS` | `""` | CSV 格式的 sed 風格正則規則，作用於每個被捕獲的回合（同一套語法） |
| `OPENVIKING_DEBUG` | `false` | 是否將日誌寫入 `~/.openviking/logs/codex-hooks.log` |

這些旋鈕大多也可以寫在 `ovcli.conf` 的 `plugin` 段下——見[外掛配置](../configuration/02-client.md#外掛配置)。兩個過濾器 knob 尤其建議寫在那裡，用 JSON 陣列，因為環境變數形式會按逗號切分。

如果更看重召回響應速度，請參閱[低延遲召回](./01-overview.md#低延遲召回)，其中說明了如何通過環境變數或 `ovcli.conf` 關閉查詢擴充與 Codex 本地結果壓縮。

更多調參說明（如 `OPENVIKING_RECALL_LIMIT`、`OPENVIKING_CAPTURE_ASSISTANT_TURNS` 等），請參考 [外掛 README](https://github.com/volcengine/OpenViking/blob/main/examples/codex-memory-plugin/README.md#tuning-the-plugin)。

</details>

## 工作區 peer

記憶按你所在倉庫派生出的 peer 歸檔，因此同一個專案在不同 clone、worktree 和子目錄下共用同一份記憶。預設的 `peer.source: "git"` 取倉庫歸一化後的 `origin` URL——`origin` 為 `git@github.com:volcengine/OpenViking.git` 時，peer 就是 `github.com-volcengine-openviking`——其次是倉庫根路徑；不在倉庫中則完全不傳送 peer，在那裡記下的內容進入使用者級空間 `viking://user/<you>/memories`。fork 的 `origin` 不同，因此預設是獨立的 peer。

可通過 `OPENVIKING_PEER_SOURCE`、`ovcli.conf` 中的 `plugin.peerSource`，或工作區 `.openviking/config.json`（`"version": 1` 的配置檔案，可提交給團隊共用）中的 `peer.source` 修改：`"cwd"` 恢復此前的行為——把工作目錄路徑中的非字母數字字元全部替換成 `-`；`"none"` 表示不傳送 peer；也可以用 `"team-{dir}"` 這樣的模板自定義。要[讓一個不是倉庫的目錄擁有獨立記憶](../configuration/02-client.md#讓一個目錄擁有獨立記憶)，在該目錄下建立 `.openviking/config.json`，內容為 `{"version": 1, "peer": {"id": "my-project"}}`。此前按工作目錄派生的 peer 下寫入的記憶仍能被召回，無需遷移。分層優先順序和工作區配置檔案的完整 schema 見[客戶端配置 → 工作區配置](../configuration/02-client.md#工作區配置)。

## 故障排查

| 現象 | 可能原因 | 修復方法 |
|------|------|------|
| MCP 工具呼叫報認證錯誤 | 當前 ovcli 配置沒有 authenticated server 所需的有效 `api_key` | 修正 `~/.openviking/ovcli.conf`（或執行 `node <外掛目錄>/scripts/setup.mjs`）後重啟 Codex；stdio 代理會在啟動時和認證失敗後重新讀取配置 |
| MCP 工具呼叫報連線錯誤 | 伺服器不可達或 URL 配置錯誤 | 執行 `curl "$(jq -r '.url' ~/.openviking/ovcli.conf)/health"` 檢查伺服器狀態 |
| `6 hooks need review`，或外掛已裝但 hook 不生效 | 全新安裝要信任全部 6 個 hook，之後每次外掛更新改動到 hook 時還會再問一次；當時選了 *Continue without trusting* 或直接跳過，hooks 就一直不會執行 | `/hooks` 裡信任並開啟相關條目，`/plugins` 裡確認 `openviking-memory` 已啟用——兩個開關相互獨立，都要是開著的 |
| `ov config switch` 後外掛仍指向舊伺服器 | 上個會話的代理程序仍在執行 | 重啟 Codex；代理在啟動時解析憑據 |
| Hook 與 MCP 指向不同伺服器 | 某一側殘留了過期的 `OPENVIKING_*` 憑據環境變數（預設環境變數優先於 ovcli.conf） | 清除過期環境變數（讓 ovcli.conf 同時驅動兩者）、設定 `OPENVIKING_CREDENTIAL_SOURCE=cli`，或保證環境變數一致 |

## 參見

- [整合能力參考](./16-capability-reference.md)
- [部落格：在 Claude Code / Codex 中接入 OpenViking](https://blog.openviking.ai/post/openviking-coding-agent/) — 為什麼以及如何給你的 Coding Agent 加上長期記憶
- [外掛 README](https://github.com/volcengine/OpenViking/blob/main/examples/codex-memory-plugin/README.md) — 完整的環境變數說明與架構圖
- [DESIGN.md](https://github.com/volcengine/OpenViking/blob/main/examples/codex-memory-plugin/DESIGN.md) — 提交（commit）決策樹
- [MCP 客戶端](./06-mcp-clients.md) — MCP 協議、工具列表及其他客戶端
- [部署指南 → CLI](../guides/03-deployment.md#cli) — `ovcli.conf` 配置說明

### 召回壓縮

設定 `OPENVIKING_RECALL_COMPRESS=server` 可讓 OpenViking 服務端壓縮召回內容，Codex 不啟動本地壓縮排程。`client` 僅用本地壓縮，`auto`（預設）在本地壓縮器不可用時走服務端，`off` 關閉壓縮。服務端已有摘要時直接使用；明確返回無相關記憶時不注入。

Codex 通過共享 `buildRecallBlockDetailed()` 執行召回、排序、預算和舊服務端回退，僅保留會話對映、模型呼叫與 hook 輸出適配。本地壓縮失敗保留預算內的檢索結果；原始檢索回退在不使用本地壓縮時遵循 `recallPreferAbstract`，不再固定讀取所有葉子全文。預算包含正文、URI 和包裝文本。配置詳見 [共享外掛說明](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/README.md#cloud-recall-compression)。
