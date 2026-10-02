# TRAE、TRAE CN 與 TraeCode CLI 2.0 記憶整合

為 TRAE、TRAE CN 和 TraeCode CLI 2.0 新增跨專案、跨會話的長期記憶。安裝後，OpenViking Hook 會自動載入相關上下文、捕獲每輪對話並提交給記憶抽取器；MCP 用於主動搜尋、讀取和管理記憶。

## 安裝

前置條件：macOS 或 Linux、Node.js 18+，以及支援 `SessionStart`、`UserPromptSubmit`、`PreToolUse`、`Stop` Hook 的 TRAE/TRAE CN 版本。TraeCode CLI 2.0 直接使用相容 Codex 的外掛格式。安裝過程中會引導配置 OpenViking 連線資訊。

安裝器詢問連線方式時，火山引擎雲服務使用者請選擇 **火山引擎 OpenViking 雲服務** 並填寫 API Key。只有本機已執行 OpenViking 服務時才選擇 **自建 / 本地**。

```bash
# TRAE
bash <(curl -fsSL https://raw.githubusercontent.com/volcengine/OpenViking/main/examples/memory-plugin-shared/install.sh) \
  --harness trae

# TRAE CN
bash <(curl -fsSL https://raw.githubusercontent.com/volcengine/OpenViking/main/examples/memory-plugin-shared/install.sh) \
  --harness trae-cn

# 同時安裝
bash <(curl -fsSL https://raw.githubusercontent.com/volcengine/OpenViking/main/examples/memory-plugin-shared/install.sh) \
  --harness trae,trae-cn

# TraeCode CLI 2.0
bash <(curl -fsSL https://raw.githubusercontent.com/volcengine/OpenViking/main/examples/memory-plugin-shared/install.sh) \
  --harness trae-cli
```

GitHub 訪問受限時使用 TOS 映象：

```bash
bash <(curl -fsSL https://ovrelease.tos-cn-beijing.volces.com/memory-plugin-shared/install.sh) \
  --harness trae,trae-cn --dist tos

# TraeCode CLI 2.0
bash <(curl -fsSL https://ovrelease.tos-cn-beijing.volces.com/memory-plugin-shared/install.sh) \
  --harness trae-cli --dist tos
```

安裝後完全退出並重啟對應客戶端。

### TraeCode CLI 2.0：首次啟動信任 hooks

TraeCode CLI 2.0 的 hooks 要先信任才會執行。啟動 `trae-cli` 時會停在這個確認上，選 **Trust all and continue**；想先看一眼 hook 命令就選 Review hooks：

```text
Hooks need review
6 hooks are new or changed.
Hooks can run outside the sandbox after you trust them.

  1. Review hooks
> 2. Trust all and continue
  3. Continue without trusting (hooks won't run)
```

全新安裝會一次列出外掛註冊的全部 6 個 hook。之後每次外掛更新只要動了 hook，啟動時都會再攔一次，數字是這次新增或改動的條數（比如只改了一個就是 `1 hook is new or changed`），同樣選 Trust all and continue。

選第 3 項或錯過這一步，hooks 就不會執行：MCP 工具仍能呼叫，但自動召回和捕獲全部停擺。要恢復，得讓兩個彼此獨立的開關都處於開啟狀態：

- `/hooks` — hook 的信任與開關，把標著 *New hook - review required* 或 *Modified since last trusted* 的條目信任並開啟。
- `/plugins` — 外掛本身的啟用狀態，確認 `openviking-memory` 是 enabled。

TRAE 和 TRAE CN 走 `hooks.json`，重啟客戶端後直接生效，沒有這一步。

## 安裝內容

- `SessionStart`：載入使用者畫像、當前專案記憶，以及 OpenViking skill 清單 `<available-skills>`。
- `UserPromptSubmit`：根據當前問題召回並注入相關內容，召回範圍包括你自己的 skill 和帳號內共享在 `viking://agent/skills` 下的 skill。
- `PreToolUse`：在 TRAE 和 TRAE CN 上，`Read`、`Glob`、`Grep` 的路徑是 `viking://` URI 時拒絕呼叫，並提示改用 OpenViking MCP 工具；`Bash` 或 `RunCommand` 命令帶 `viking://` URI 時照常執行，同時附加改用建議。TraeCode CLI 2.0 使用 Codex 外掛，它的 `PreToolUse` 只匹配 `Bash`，只附加同樣的提示，不拒絕呼叫。
- `Stop`：捕獲本輪訊息並立即提交，使短會話也能進入記憶抽取流程。
- OpenViking MCP Server：透傳服務端完整 MCP 工具集（16 個工具）：`find`、`search`、`read`、`list`、`tree`、`remember`、`write`、`edit`、`add_resource`、`add_skill`、`list_watches`、`cancel_watch`、`grep`、`glob`、`forget`、`health`。其中 `search` 的 `mode="context"` 可返回組裝後的上下文。
skill 清單先列你自己的 skill，再列帳號內共享的 skill，每條描述截到約 40 token。清單的預算 `skillCatalogTokenBudget`（預設 `1200` token）獨立於畫像預算；描述放不下時只列名稱。把 `skillCatalog` 設為 `false` 或把預算設為 `0` 即可關閉，既可以寫在 `~/.openviking/ovcli.conf` 的 `plugin` 段（見[外掛配置](../configuration/02-client.md#外掛配置)），也可以用環境變數 `OPENVIKING_SKILL_CATALOG` 和 `OPENVIKING_SKILL_CATALOG_TOKEN_BUDGET`。

## 驗證

1. 重啟 TRAE、TRAE CN 或 TraeCode CLI 2.0，並新建 Agent 會話。
2. 在客戶端的 MCP 設定中確認 `openviking` 已連線。
3. 提問一個與已有專案或個人偏好相關的問題，確認回答使用了已有記憶。
4. 告訴 Agent 一個臨時偏好，等待回覆完成；新建會話後再次詢問，確認捕獲、提交和跨會話召回均生效。
5. 對 TraeCode CLI 2.0，執行 `trae-cli plugin list` 確認 `openviking-memory` 已啟用，並在會話裡輸入 `/hooks`，確認 OpenViking 的條目已信任且處於開啟狀態。

需要排查 Hook 時，設定 `OPENVIKING_DEBUG=1` 後啟動客戶端，並檢視：

- TRAE：`~/.openviking/logs/trae-hooks.log`
- TRAE CN：`~/.openviking/logs/trae-cn-hooks.log`
- TraeCode CLI 2.0：`~/.openviking/logs/codex-hooks.log`

## 升級與解除安裝

重複執行對應安裝命令即可升級。解除安裝時也應使用原安裝渠道：

```bash
# GitHub，以 TRAE CN 為例
bash <(curl -fsSL https://raw.githubusercontent.com/volcengine/OpenViking/main/examples/memory-plugin-shared/install.sh) \
  --harness trae-cn --uninstall --yes

# TOS，以 TRAE CN 為例
bash <(curl -fsSL https://ovrelease.tos-cn-beijing.volces.com/memory-plugin-shared/install.sh) \
  --harness trae-cn --uninstall --yes
```

將 `trae-cn` 替換為 `trae` 可管理 TRAE 整合。TraeCode CLI 2.0 請執行 `trae-cli plugin uninstall openviking-memory@openviking`。安裝器的 `--harness trae-cli --uninstall` 只用於移除舊安裝中已棄用的獨立 Hooks 整合。

## 故障排查

| 現象 | 原因與處理 |
|------|-----------|
| 安裝後沒有自動召回 | 完全退出客戶端後重新啟動，並新建 Agent 會話。 |
| TraeCode CLI 2.0 外掛已裝，但召回和捕獲都不發生 | 啟動時的 hook 信任確認被跳過，或當時選了 *Continue without trusting*；外掛更新動了 hook 後也會重新要求信任。`/hooks` 裡信任並開啟 OpenViking 的條目，`/plugins` 裡確認 `openviking-memory` 已啟用——兩個開關相互獨立，都要是開著的。 |
| MCP 未連線 | 檢查 `~/.openviking/ovcli.conf` 中的 URL/API Key，然後重啟客戶端。 |
| 新會話無法回憶上一輪內容 | 檢視 Hook 日誌，確認 `Stop` 已執行且 `/commit` 沒有連線或鑑權錯誤。 |
| 同一內容被捕獲多次 | 檢查使用者級與專案級 Hook 中是否仍有舊版 `trae-auto-recall.mjs` 或 `trae-auto-capture.mjs`；重跑安裝器會移除由 OpenViking 管理的舊條目。 |
| TraeCode CLI 2.0 未列出外掛 | 執行 `trae-cli plugin list`；若沒有 `openviking-memory`，使用 `--harness trae-cli` 重跑安裝器。 |

## 參見

- [整合能力參考](./16-capability-reference.md)
- [鑑權](../guides/04-authentication.md)
