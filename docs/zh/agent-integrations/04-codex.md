# Codex

為 [Codex](https://developers.openai.com/codex) 提供跨會話記憶。外掛通過 hooks 自動召回、捕獲和提交對話，通過 MCP 提供檢索、讀取和記憶管理工具。

原始碼：[examples/codex-memory-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/codex-memory-plugin) | [部落格：動機與效果展示](https://blog.openviking.ai/post/openviking-coding-agent/)

## 安裝

Claude Code 和 Codex 共用同一個安裝指令碼。它會詢問要安裝的 harness 和 OpenViking 憑據；所有步驟冪等，可安全地重複執行。

```bash
curl -fsSL https://openviking.ai/install | bash
# AI agent 如不確定是否執行，可先閱讀指令碼頭部，其中寫明瞭它會做什麼、如何核實。
```

Codex 從隨 OpenViking 釋出的 git 倉庫安裝外掛，保留遠端更新能力。TraeCode CLI 2.0 可以直接安裝這一 Codex 格式外掛：安裝器詢問要安裝的 harness 時，勾選 **TraeCode CLI 2.0** 即可。

現在不再需要任何 shell wrapper——外掛自帶的 stdio MCP 代理會在執行時讀取 `~/.openviking/ovcli.conf`（或 `OPENVIKING_*` 環境變數），與 hooks 使用同一套配置鏈。安裝完成後啟動 Codex（TraeCode CLI 2.0 是 `trae-cli`）：

```bash
codex
```

### 首次啟動：信任 hooks

安裝外掛不會自動信任它的 hooks。首次啟動時 Codex 會顯示類似下面的審閱提示，具體介面隨 Codex 版本變化。選 **Trust all and continue**，或先選 **Review hooks** 檢視命令。選 *Continue without trusting* 後 hooks 不會執行，直到在 `/hooks` 中開啟。

```text
Hooks need review
6 hooks are new or changed.
Hooks can run outside the sandbox after you trust them.

  1. Review hooks
> 2. Trust all and continue
  3. Continue without trusting (hooks won't run)
```

也可以在 `/hooks` 中檢查 OpenViking 命令，信任並啟用準備使用的條目；同時在 `/plugins` 中確認 `openviking-memory` 已啟用。當前外掛聲明瞭 6 個 hook，新增或修改定義後需要重新審閱，規則見[官方 hook 信任說明](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks)。

Hook 關閉時，MCP 工具仍可能正常使用。自動召回需要 `UserPromptSubmit`，捕獲需要 `Stop`，其餘生命週期提交見下表。之前跳過設定的，可以回到 `/hooks` 啟用相關條目。

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

## OpenViking 來源彙總

memory 外掛預設內建 OV-Usage。報告彙總自動召回和顯式 OpenViking MCP、`ov` CLI 查詢，統計本輪可用來源，不能證明回答實際採用了每個來源。缺失或無法識別的 rollout 記錄可能省略自動召回歸因。

設定 `OPENVIKING_USAGE_OUTPUT=terminal` 時，只通過 Stop hook 輸出一條資訊訊息；設定為 `desktop` 時，通過模型生成回答頁尾，Stop 不再重複輸出。預設 `auto` 在存在 `TERM_PROGRAM` 或非 `dumb` 的 `TERM` 時選擇 terminal，否則選擇 desktop。這是啟發式判斷，桌面客戶端繼承終端環境變數時可顯式覆蓋。設定 `OPENVIKING_USAGE_VIEW=expanded` 檢視來源詳情，設定為 `off` 關閉報告及其本地後設資料寫入。用 `/hooks` 審閱更新後的 hooks。頁尾遵循更高優先順序的格式要求。報告失敗不會阻斷召回或捕獲，尚未實現互動式展開/摺疊按鈕。

## 工作原理

外掛按以下事件處理記憶：

| Codex 事件 | 外掛行為 |
| --- | --- |
| `SessionStart`（`startup`、`clear`、`resume`） | 注入 `profile.md`、`preferences/` 和 `entities/` 的 URI 與摘要索引，以及 `<available-skills>` 清單。複用支援中日韓文本的公共 profile 構建邏輯；恢復會話時還可注入最新 archive digest。 |
| `UserPromptSubmit` | 搜尋並注入與當前輸入相關的記憶。 |
| `Stop` | 將新增對話追加到 OpenViking 會話。 |
| `PreCompact` | 補齊並提交壓縮前的完整對話記錄。 |
| `SessionEnd` | 正常退出時提交會話，觸發後續記憶提取。 |

新會話啟動時還會清理上次執行遺留、已超過閒置 TTL 的孤兒會話。

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

這些配置大多也可以寫在 `ovcli.conf` 的 `plugin` 段下——見[外掛配置](../configuration/02-client.md#外掛配置)。兩個過濾器建議使用 JSON 陣列，避免環境變數中的逗號被當作分隔符。

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
| 提示審閱 hook，或外掛已裝但沒有自動召回/捕獲 | 相關 hook 未信任、未啟用，或外掛被停用 | 在 `/hooks` 審閱並啟用相關條目，再到 `/plugins` 確認外掛已啟用。 |
| `ov config switch` 後外掛仍指向舊伺服器 | 原代理仍保留連線，或憑據環境變數覆蓋了選中的配置 | 重啟 Codex，並檢查憑據環境變數與 `OPENVIKING_CLI_CONFIG_FILE`。遠端呼叫會在認證失敗後檢查檔案變化，不會在每次成功請求時過載 |
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
