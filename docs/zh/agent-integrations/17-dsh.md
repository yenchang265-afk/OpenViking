# DeepSeek Harness

為 [DeepSeek Harness](https://www.npmjs.com/package/@deepseek-ai/dsh)（`dsh`）及 DeepSeek Harness Desktop 桌面應用接入跨專案、跨會話的長期記憶。安裝後每次對話都會自動召回相關記憶並捕獲新內容，模型也會直接拿到 OpenViking 工具以及 `openviking-memory`、`openviking-skills`、`ov-experience-memory` 三個技能，無需額外配置。

原始碼：[examples/dsh-memory-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/dsh-memory-plugin)

## 安裝

DSH 與其他記憶外掛共用同一個安裝器。它會詢問要安裝的 harness 和 OpenViking 憑據；每一步都是冪等的，重複執行完全安全。

```bash
curl -fsSL https://openviking.ai/install | bash
# AI agent 如不確定是否執行，可先閱讀指令碼頭部，其中寫明瞭它會做什麼、如何核實。
```

安裝器會把外掛裝到 `web` profile。要裝到其他 profile，用 `--dsh-profile <name>` 指定：`curl -fsSL https://openviking.ai/install | bash -s -- --dsh-profile <name>`。使用桌面應用？見 [DeepSeek Harness Desktop](#deepseek-harness-desktop)。

安裝後按下方“驗證”步驟檢查工具接入和跨會話召回。

<details>
<summary><b>手動安裝</b></summary>

1. **配置連線** —— 寫 `~/.openviking/ovcli.conf`（`url`、`api_key`，可選 `account`/`user`），或設定 `OPENVIKING_URL` 和 `OPENVIKING_API_KEY`。如果用純本地模式（`http://127.0.0.1:1933`，無鑑權），這步可以跳過，外掛預設就指向本地。

2. **把外掛裝進 profile**：

   ```bash
   dsh plugin --profile web add @openviking/dsh-memory-plugin
   ```

   `dsh plugin` 會轉發給 profile 目錄下的 pnpm，所以除 `desktop` 外任何 profile 名都可以（`desktop` 歸[桌面應用](#deepseek-harness-desktop)所有）；`web` 是 `dsh` 首次執行時自動建立的那個。

3. **確認 profile 已生效**：

   ```bash
   dsh --profile web --dump-config
   ```

   輸出裡應該能看到 `openviking-memory-runtime` 條目。

> 還沒有 `ovcli.conf`？見[部署指南 → CLI](../guides/03-deployment.md#cli)。
>
> 解除安裝：`dsh plugin --profile web rm @openviking/dsh-memory-plugin`。

</details>

安裝完成後，在 DSH 中新開一個會話，讓它按 https://docs.openviking.net/agents/zh/onboarding.md 執行。它會檢查連線，並帶你完成首次使用，詳見[一鍵接入](../getting-started/07-agent-onboarding.md)。

## 驗證

啟動 `dsh --profile web` 開啟一個會話，會話開頭應該能看到一條 OpenViking 上下文注入，模型也應該具備 `mcp__openviking__*` 工具。問一句更早會話裡聊過的事，確認召回生效。

排查 MCP 代理問題時，在啟動 DSH 前設定 `OPENVIKING_DEBUG=1` 和 `OPENVIKING_DEBUG_LOG=/tmp/ov-dsh.log`，然後檢視該檔案。自動記憶回呼使用 DSH 自身的日誌系統。舊別名 `OV_DEBUG_LOG=/tmp/ov-dsh.log` 仍然支援，並且優先於這兩個規範配置項。

## DeepSeek Harness Desktop {#deepseek-harness-desktop}

外掛同樣可以在 DeepSeek Harness Desktop 桌面應用中執行，支援 macOS 和 Windows；Desktop 沒有 Linux 版本。Desktop 的外掛裝在它專屬的 `desktop` profile（`~/.dsh/profiles/desktop`）裡，與 CLI 的 `web` profile 互不相通：給 `dsh web` 裝的外掛不會出現在 Desktop 裡，反之亦然。兩者讀取同一份 `~/.openviking/ovcli.conf`。

### 用安裝器安裝（macOS） {#desktop-installer}

在 macOS 上，安裝器會檢測到 Desktop，並把它作為單獨的 harness **DeepSeek Harness Desktop**（`dsh-desktop`）列出，預設選中，可以和 `dsh` CLI 一起安裝。修改 Desktop 的 profile 時，應用不應處於執行狀態：

1. 先開啟一次 Desktop，讓它建立 profile，然後用 ⌘Q 退出。關閉視窗只會隱藏它，應用仍在執行。
2. 執行安裝器。把命令末尾的 `bash` 換成 `bash -s -- --harness dsh-desktop` 只安裝 Desktop；`--dsh-profile desktop`（或 `OPENVIKING_DSH_PROFILE=desktop`）選中的也是這個 harness。
3. 重新開啟 Desktop，新開一個會話。

如果 Desktop 正在執行，安裝器會提示你先退出（加 `--yes` 時只警告並繼續）。如果找不到 Desktop 自帶的 `dsh` 命令、profile 還沒建立，或者提示後 Desktop 仍在執行，安裝器不會報錯退出，而是列印外掛頁的安裝步驟。安裝器本身需要 Node.js 18 或更高版本，Desktop 並不提供；在沒有 Node.js 的 Mac 上，它會列印同樣的步驟後退出。

安裝器用的是 Desktop 自帶的 `dsh` 命令，而不是 npm 裝的那個——後者會拒絕 `desktop` profile。它按以下順序查詢：`OPENVIKING_DSH_DESKTOP_CLI`；`/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh`；`~/Applications` 下的同一路徑；PATH 上實際指向 `DeepSeek Harness.app` 內部的 `dsh`（即應用選單 **Manage dsh Command…** 安裝的那個）。

### 手動安裝 {#desktop-plugins-page}

Windows 上安裝器不可用，只能用這種方式；macOS 上不想跑安裝器時也可以用。外掛頁和 Desktop 自帶的 `dsh` 命令只負責新增外掛，都不會詢問 OpenViking 憑據，所以要先配好鑑權。

1. **配置連線。** 寫好 `~/.openviking/ovcli.conf`（Windows 上是 `%USERPROFILE%\.openviking\ovcli.conf`）：

   ```json
   { "url": "https://<你的 OpenViking 服務地址>", "api_key": "<你的 API Key>" }
   ```

   trusted 模式的服務端還要填 `account` 和 `user`；如果用的是 `http://127.0.0.1:1933` 上無鑑權的本地服務端，這步可以跳過。參見[部署指南 → CLI](../guides/03-deployment.md#cli)。

2. **新增外掛**，兩種方式任選：
   - **外掛頁**（macOS 和 Windows）：在 Desktop 中開啟 **外掛** → **新增外掛**，輸入 `@openviking/dsh-memory-plugin`，點選 **安裝**。**安裝源** 選單決定從哪個 npm 源下載；映象源同步新版本可能有延遲。裝好後如果外掛開關是關閉的，把它開啟。
   - **Desktop 自帶的 `dsh` 命令**（macOS）：先用 ⌘Q 退出 Desktop，再執行：

     ```bash
     DSH="/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh"
     "$DSH" plugin --profile desktop add @openviking/dsh-memory-plugin
     ```

     Windows 上對應的命令是 Desktop 安裝目錄下的 `resources\runtime\cli\bin\dsh.cmd`。

3. 新開一個會話。用 `dsh` 命令安裝的，要先重新開啟 Desktop。

### 在 Desktop 中驗證 {#verify-in-desktop}

任何 `dsh` 都無法啟動 `desktop` profile，所以 `--dump-config` 對它不可用。可以用 `"$DSH" plugin --profile desktop ls` 檢查，或者確認 `~/.dsh/profiles/desktop/package.json` 的 `dsh.profile.bundles` 中有 `@openviking/dsh-memory-plugin`。然後在 Desktop 中新開一個會話，按[驗證](#驗證)一節檢查上下文注入和 `mcp__openviking__*` 工具。

### 配置 Desktop {#configure-desktop}

- 連線和行為引數（寫在 `plugin.dsh` 下）優先放在 `~/.openviking/ovcli.conf`。下文 **配置** 中的 patch 塊要寫進 `~/.dsh/profiles/desktop/cordis.patch.yml`，但 Desktop 啟動失敗時，恢復對話方塊（**禁用第三方外掛、備份 profile patch 並重啟**）會把這個檔案挪成 `cordis.patch.yml.bak-<時間戳>`。
- Desktop 看不到在終端裡 export 的變數。macOS 上，它在應用啟動時讀取一次登入 shell 的環境（`~/.zprofile`、`~/.zshrc`），所以改了 `OPENVIKING_*` 變數後要退出並重新開啟 Desktop；`DSH_*` 變數不會從 shell 讀取。Windows 上，它讀取使用者環境變數：用 `setx` 設定後退出並重新開啟 Desktop。
- Desktop 不顯示 DSH 的日誌輸出，而自動記憶回呼的日誌正寫在那裡。排查 MCP 代理時，按上一條的方式設定 `OPENVIKING_DEBUG=1` 和 `OPENVIKING_DEBUG_LOG=<檔案路徑>`，再檢視該檔案。
- Desktop 從 profile 目錄啟動 MCP 代理，因此代理拿不到工作區 peer；自動召回和捕獲仍按每個會話的工作區計算。設定了 `OPENVIKING_RECALL_PEER_SCOPE=actor` 時，在 `ovcli.conf` 中設定 `actor_peer_id` 或設定 `OPENVIKING_PEER_ID`，才能限定 `mcp__openviking__*` 工具的範圍，否則它們會檢索所有 peer。顯式 peer 也會取代每個會話的工作區 peer，用於自動召回和捕獲，因此 Desktop 的所有會話共用這一個 peer。

解除安裝：在外掛頁中該外掛的條目上點選 **解除安裝**；或者退出 Desktop 後執行 `"$DSH" plugin --profile desktop rm @openviking/dsh-memory-plugin`。

## 工作方式

外掛以 Cordis 外掛的形式跑在 DSH 程序內，而不是外掛 hook，因此能貼著會話走。會話開始時注入 OpenViking 畫像塊、可用記憶索引和 OpenViking 技能清單 `<available-skills>`；模型步驟帶有新的使用者輸入時，用使用者輸入的文本做語義檢索，把結果作為持久訊息追加到同一步驟，因此注入會隨會話重放，也對壓縮可見。DSH 或其他外掛注入的上下文（例如 `time-context`、job 通知）和工具結果既不觸發召回，也不拼進檢索文本。它直接從 DSH 的事件流捕獲 user、assistant 以及（可選的）工具結果訊息，並跳過注入的上下文，待同步 token 超過閾值或 DSH 開始壓縮時即 commit，每次 commit 都歸檔全部已捕獲的訊息。寫入失敗會進入待寫佇列，在下次會話開始時重放。

每個 DSH 會話對映為 OpenViking 中的 `dsh-<session-id>`，子 agent 各自擁有獨立會話。

模型看到的工具面就是 OpenViking 的 MCP 工具集，經由與其他記憶整合相同的 stdio 代理接入，以 `mcp__openviking__` 字首釋出。由於該代理每個 profile 只起一個程序，`mcp__openviking__remember` 寫入的是服務端一個短生命週期的會話而不是當前會話（對話本身仍由自動捕獲記錄）。設定 `OPENVIKING_RECALL_PEER_SCOPE=actor` 後，固定的 `OPENVIKING_PEER_ID` 才會把該 profile 的工具呼叫歸屬到同一個 peer；預設 `all` 不傳送 actor-peer 頭。多個工作區需要不同工具身份時，使用獨立 profile/程序。外掛同時附帶三個共享技能：`openviking-memory` 讓模型知道何時該檢索、讀取和寫入，`openviking-skills` 講如何查詢、使用、建立、共享和遷移存放在 OpenViking 裡的技能，`ov-experience-memory` 讓模型在執行類任務前檢索並應用以往任務的 Experience。外掛預設捕獲工具結果（`captureToolResults: true`），服務端據此把該技能的讀取關聯回所用的 Experience；設為 `false` 時，它只檢索和應用 Experience。

檔案工具誤把 `viking://` URI 當本地路徑時，呼叫會被攔截，並提示改用對應的 OpenViking 工具；寫入或編輯的若是 `viking://~/skills/<name>/` 這類技能目錄，提示的工具是 `mcp__openviking__add_skill`，它用完整的 `SKILL.md` 文本建立或替換整個技能。shell 命令帶 `viking://` URI 時照常執行，模型會收到一條改用 OpenViking 工具的提示，URI 是有意傳入的資料時可以忽略。

<details>
<summary><b>配置</b></summary>

憑證解析順序為 `OPENVIKING_*` 環境變數 → `~/.openviking/ovcli.conf` → `~/.openviking/ov.conf`，與 Claude Code、Codex、OpenCode、pi 共用同一條鏈路；這些檔案變更後會自動過載。

| 環境變數 | 預設值 | 說明 |
|---------|--------|------|
| `OPENVIKING_URL` / `OPENVIKING_BASE_URL` | `http://127.0.0.1:1933` | 服務端點 |
| `OPENVIKING_API_KEY` / `OPENVIKING_BEARER_TOKEN` | — | API Key（以 `Authorization: Bearer` 傳送） |
| `OPENVIKING_ACCOUNT` / `OPENVIKING_USER` | — | 可信模式下的 account 與 user |
| `OPENVIKING_PEER_ID` | — | 顯式指定 actor peer |
| `OPENVIKING_WORKSPACE_PEER` | `true` | 按每個會話的工作區推導 peer；設為 `0` 則不傳送 peer |
| `OPENVIKING_RECALL_PEER_SCOPE` | `all` | 設為 `actor` 可將召回限制在當前工作區 |
| `OPENVIKING_DEBUG` | `false` | 啟用 MCP 代理除錯日誌；還需配置日誌路徑 |
| `OPENVIKING_DEBUG_LOG` | `""` | MCP 代理除錯日誌的檔案路徑 |
| `OV_DEBUG_LOG` | — | 舊別名：啟用 MCP 代理日誌，並覆蓋規範的除錯開關和日誌路徑 |

行為引數寫在 profile 的 Cordis patch 條目裡：

```yaml
- id: openviking-memory-runtime
  config:
    recallTokenBudget: 2000
    scoreThreshold: 0.35
    captureToolResults: true
    commitTokenThreshold: 20000
```

同一個 `config` 塊裡的 `syncTurns: false` 關閉自動捕獲、commit 和待寫佇列重放，畫像注入和召回照常。排隊的寫入保留到後續開啟寫入的會話處理；該開關不會撤銷模型的 MCP 寫工具或改變服務端許可權。

同一個 `config` 塊裡的 `peerSource` 決定工作區 peer 的派生方式。預設的 `"git"` 取倉庫歸一化後的 `origin` URL（`git@github.com:volcengine/OpenViking.git` 得到 `github.com-volcengine-openviking`），其次是倉庫根路徑，因此同一個倉庫的每個 clone、worktree 和子目錄共用同一個 peer；不在倉庫中則完全不傳送 peer，在那裡記下的內容進入使用者級空間 `viking://user/<you>/memories`。`"cwd"` 恢復此前的行為——把工作目錄路徑中的非字母數字字元全部替換成 `-`；`"none"` 則完全不傳送 peer。要讓倉庫之外的目錄擁有獨立記憶，請為它設定 `OPENVIKING_PEER_ID`（見[讓一個目錄擁有獨立記憶](../configuration/02-client.md#讓一個目錄擁有獨立記憶)）。

同一個 `config` 塊裡的 `skillCatalog` 和 `skillCatalogTokenBudget` 控制會話開始時注入的技能清單。清單先列你自己的技能，再列帳號內共享在 `viking://agent/skills` 下的技能，每條描述截到約 40 token；它有獨立的預算（預設 `1200` token，不佔用畫像預算），描述放不下時只列名稱。`skillCatalog: false` 或把預算設為 `0` 即可關閉；對應的環境變數是 `OPENVIKING_SKILL_CATALOG` 和 `OPENVIKING_SKILL_CATALOG_TOKEN_BUDGET`。

patch 中寫的憑證優先於環境變數。行為配置按優先順序從高到低解析：`OPENVIKING_*` 環境變數、工作區的 `.openviking/config.json` 與 `config.local.json`、`ovcli.conf` 的 `plugin.dsh`、`ovcli.conf` 的 `plugin`，最後才是這個 patch 塊。完整引數列表見[外掛 README](https://github.com/volcengine/OpenViking/tree/main/examples/dsh-memory-plugin)。

</details>

## 常見問題

| 現象 | 排查方向 |
|------|----------|
| 沒有注入，也沒有 OpenViking 工具 | `dsh --profile web --dump-config` 裡應能看到 `openviking-memory-runtime`；重新執行安裝器或 `dsh plugin --profile web add …`。Desktop 見[在 Desktop 中驗證](#verify-in-desktop) |
| 裝到了錯誤的 profile | 安裝器預設 `web`；用 `--dsh-profile <name>` 重新執行 |
| DSH 提示外掛與當前 dsh 版本不相容 | 外掛接受 `0.1.0-rc.6` 起的所有 `@deepseek-ai/dsh` 0.x 版本（peer 範圍 `>=0.1.0-rc.6 <1.0.0-0`），出現這個提示說明 DSH 已是 1.0 或更高；升級外掛，或者確認風險後用 `dsh plugin allow-version` 放行。所有 `@deepseek-ai/dsh-*` 宿主包要保持同一版本。 |
| 升級 DSH 後外掛啟動失敗 | 已驗證的版本：`0.1.0-rc.6`、`0.1.5-rc.1`、`0.1.5-rc.2`、`0.1.7-rc.2`、`0.2.0-rc.2`、`0.2.1-alpha.1`、`0.2.1-rc.2`、`0.2.1-rc.3`。更新的 0.x 版本不經預先驗證就會被接受；請把 DSH 固定到已驗證的版本，並提 issue。 |
| 安裝時報包「不在 npm registry 中」 | 檢查該 profile 的 pnpm 是否設定了 24 小時的最小發布年齡（`minimumReleaseAge`）。等一等，或把該精確版本加進 profile 的 `pnpm-workspace.yaml` 的 `minimumReleaseAgeExclude` |
| 召不回任何內容 | `curl "<OpenViking 服務地址>/health"`；檢查端點配置，以及 prompt 是否長於最小查詢長度（3 個字元） |
| OpenViking 返回 401 / 403 | 檢查 `OPENVIKING_API_KEY`；可信模式部署還要檢查 `OPENVIKING_ACCOUNT` 與 `OPENVIKING_USER` |
| 串入了其他專案的記憶 | 設定 `OPENVIKING_RECALL_PEER_SCOPE=actor`，將 peer 記憶限定為當前 peer；使用者級記憶仍會共享 |
| 崩潰後沒有 commit | commit 由 token 閾值、壓縮開始和 teardown 觸發；排隊的寫入會在下次會話開始時重放 |
| `profile "desktop" is managed exclusively by the Electron application` | `desktop` profile 不能啟動，也不能 dump 配置，只有 Desktop 自帶的 `dsh` 能修改它的外掛。改用 [Desktop 自帶的 `dsh` 命令](#desktop-plugins-page)，並[不借助 `--dump-config` 驗證](#verify-in-desktop) |
| `Open DeepSeek Harness Desktop once to initialize its profile…` | Desktop 還沒建立 profile。先開啟一次 Desktop，用 ⌘Q 退出，再重新執行安裝器 |
| 給 Desktop 裝好了，但什麼都沒出現 | 用 ⌘Q 退出 Desktop（關閉視窗只會隱藏）後重新開啟；在 **外掛** 頁確認外掛已啟用 |
| Desktop 彈出恢復對話方塊後外掛消失了 | 恢復操作會禁用第三方外掛並備份 `cordis.patch.yml`；到 **外掛** 頁重新啟用，需要的設定從 `.bak-<時間戳>` 檔案挪到 `ovcli.conf` |
| **極簡模式** 下沒有技能 | Web 和 Desktop 的 **極簡模式** agent 預設沒有技能工具，外掛附帶的技能在那裡不可用；自動召回和捕獲照常 |

## 延伸閱讀

- [整合能力參考](./16-capability-reference.md)
