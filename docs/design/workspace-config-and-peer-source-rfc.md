# RFC: Workspace 分層配置與可配置 Peer 來源

## TL;DR

**問題**：目前 Business Data Platform 使用「當前工作目錄（CWD）」作為專案身份（peer）。這導致工作目錄一旦改變，專案身份也會隨之改變，之前積累的專案記憶便會失效——無論是更換裝置、移動倉庫位置、從子目錄啟動會話，還是使用 git worktree，都會觸發此問題。此外，目前無法將「專案級配置」固化到專案中：使用者只能設定環境變數，這些配置既不落盤持久化，也無法通過 Git 與團隊成員共享。

**提案**：

1. **專案身份改為基於 Git 推導**。使用歸一化後的 origin remote（如 `github.com-volcengine-openviking`）作為 peer id。如此一來，同一個倉庫無論在何臺裝置、哪個克隆副本、哪個子目錄或哪個 worktree 下執行，其專案身份均保持一致。
2. **非 Git 倉庫目錄預設不再分配 peer**，其記憶將寫入使用者級空間——恢復到 peer 功能引入前的預設行為。此舉主要是為了應對 Codex desktop 等場景：該類工具會為每個臨時任務新建一個日期目錄，若按原有規則，每個一次性任務都會生成一個全新的空 peer，既無法檢索歷史記憶，又會在服務端堆積大量僅含零星記憶的名稱空間。若需讓某個非 Git 目錄擁有獨立記憶，只需在其中建立 `.openviking/config.json` 並指定 `peer.id` 即可。
3. **peer 來源調整為可配置項** `peer.source`：內建 `git`（新預設值）、`cwd`（舊行為，保持逐位元組相容）、`none`（徹底停用）三種模式，同時支援諸如 `"{git_remote}-{harness}"` 的自定義模板。
4. **引入三層配置架構**：包括 `<倉庫根>/.openviking/config.json`（提交至 Git，供團隊共享）、`config.local.json`（供個人覆蓋，不提交）、以及 `~/.openviking/workspaces/`（本機私有，使用者對任何倉庫均有最終覆蓋權）。這三層配置共用同一套 Schema 與合併規則，其優先順序高於全域的 `ovcli.conf`，但始終低於環境變數。

**舊記憶處理方案**：無需進行任何資料遷移。舊的 cwd 身份隨時可在本地重新計算，recall 檢索時會自動將其帶入進行雙向讀取（dual-read），且不設截止期限。此外，預設的跨 peer 廣度掃描同樣會召回舊記憶，僅在結果排序時相對靠後。

**邊界界定**：服務端協議保持不變，peer 依舊作為使用者邊界內的檢視過濾，而非租戶級隔離；對提交至倉庫的配置採取「直接信任」原則，僅保留結構性底線（如禁止包含憑證類欄位、不進行變數展開），不設定複雜的授權門檻。

## 概述

Business Data Platform 客戶端目前僅依賴一份全域配置（`~/.openviking/ovcli.conf` 結合環境變數），專案身份（actor peer）由程序工作目錄動態推導：`cwd.replace(/[^A-Za-z0-9]/g, "-")`。這一機制帶來了三個長期存在的問題：

1. **Peer 身份脆弱易變**。更換機器、移動目錄、在倉庫子目錄中啟動會話或使用 Git worktree，都會推匯出截然不同的 Peer，導致此前積累的專案記憶隨之“消失”。外掛文件已將“倉庫移動或重新命名後 recall 內容為空”列為已知故障模式。
2. **缺乏對單個 Workspace 的持久化配置能力**。如果想固定 Peer 或調整某個專案的行為，目前只能設定環境變數，這些配置無法隨專案落盤，更無法通過 Git 在團隊間共享。
3. **配置體系缺乏分層機制**。既沒有專案級配置，也沒有團隊共享配置，更缺少諸如“某個目錄應用哪份連線配置”的使用者級對映能力。

本 RFC 旨在提出一套統一的解決方案，核心是建立**配置分層體系**，而 Peer 身份機制的改造則是該體系落地的首個核心功能：

- **引入三層配置架構**：包括提交到倉庫的 `<root>/.openviking/config.json`（團隊共享）、不提交到倉庫的 `<root>/.openviking/config.local.json`（個人覆蓋），以及使用者級登錄檔 `~/.openviking/workspaces/`（機器本地，按 Workspace 分佈為單檔案）。這三層配置採用統一的 Schema 和合並引擎。
- **將 Peer 來源重構為可配置規則**：引入 `peer.source` 鍵，內建 `git`、`cwd`、`none` 預設，支援變數模板與按序回退。該規則可在任意配置層進行設定，也支援完全停用 Peer。
- **預設策略切換為基於 Git，且只基於 Git**：以歸一化的 origin remote URL 作為專案身份，確保跨機器、跨克隆、跨子目錄、跨 worktree 的穩定性。不在 Git 倉庫裡的目錄預設**不再派生 peer**，其記憶進入使用者級空間——這正是 peer 功能出現之前的基線；按目錄路徑派生 peer 改為顯式 opt-in。舊有基於 cwd 推導的記憶，將由預設的 broad recall 掃描與 dual-read 機制兜底（具體覆蓋範圍與邊界詳見「遷移與資料連續性」）。
- **對倉庫提交的配置採取“直接信任”策略**：不設複雜的授權門檻，僅保留零摩擦的結構性安全底線（如結構性禁止憑證類鍵、不做變數展開）。相關風險評估與未來可選的授權機制詳見「風險與信任取捨」一節。

## 背景與現狀

### Peer 的當前機制

客戶端將 Peer ID 放置在 `X-OpenViking-Actor-Peer` 請求頭（讀路徑）和 Session 訊息體的 `peer_id` 欄位（寫路徑）中。服務端將 Peer 視為**使用者邊界內的路徑字首**：`viking://user/<user>/peers/<peer_id>/{memories,resources}`。目前服務端沒有 Peer 登錄檔，也沒有 Rename、Alias 或 Merge 機制（參考 `openviking/core/retrieval_targets.py:142`）。因此，變更 Peer ID 意味著開啟一個全新的空名稱空間；舊的名稱空間只能通過預設的 broad recall（`peer_scope: "all"`）掃回，且僅覆蓋 memory 分類桶，並因 `other_peer_penalty` 被降分墊底；在 `peer_scope: "actor"` 模式下，舊名稱空間完全不可見。

當前的推導邏輯集中在共享庫 `examples/memory-plugin-shared/lib/workspace-peer.mjs`（15 行程式碼）中，並通過 `sync.mjs` 複製到 7 個 Harness 目標。顯式指定 Peer 的優先順序鏈已經存在：`OPENVIKING_PEER_ID` 環境變數 → `ovcli.conf` 中的 `actor_peer_id` / `peer_id` → 各 Harness 的遺留配置塊 → cwd 推導。

### 配置讀取的當前機制

`ovcli.conf` 在倉庫中存在多個獨立的 Reader（Rust CLI、Python 側有四處、JS 側有五處），其行為已出現細微分歧。例如，`/etc` 回退與 `${VAR}` 展開僅存在於 `openviking_cli` 的 Reader，而 SDK 遇到 BOM 頭會直接報錯。Python 側的 Schema 守門人拒絕未知的頂層鍵：Pydantic 模型設定了 `extra: "forbid"`（`ovcli_config.py:60`），SDK 也有白名單機制。唯一開放的擴充點是 `plugin` 字典（`ovcli_config.py:52`），這也順理成章地成為本方案中所有 `ovcli.conf` 側新鍵的落點——**實現零 Schema 變更**。

但在此之前，必須修復一個前置 Bug：Rust 的 `Config` 結構體缺少 `plugin` 欄位（`crates/ov_cli/src/config.rs:39`），導致 `ov config add|edit` 與交互向導在重寫檔案時會**整段丟棄 `plugin` 配置**（包括現有的 `plugin.claude_code` / `plugin.codex`）。這是一個當前已存在的資料丟失問題，其修復（Rust 寫路徑改用 `serde_json::Value` 級合併以保留未知鍵）需列入 P0 階段。

`${VAR}` 展開目前由 `load_json_config` 對整個檔案文本執行（`openviking_cli/utils/config/config_loader.py:88`）。這種行為對使用者自有檔案固然便利，但對任何可通過倉庫提交的檔案而言，卻是一個可能洩露金鑰的危險機制（參考 pnpm GHSA-3qhv-2rgh-x77r 漏洞：提交的 `.npmrc` 中的 `${CI_JOB_TOKEN}` 在安裝時被展開並外發）。因此，Workspace 檔案必須走獨立的、不涉及變數展開的解析路徑。

## 目標與非目標

目標：

- 建立一套三層、統一 Schema、可擴充的 per-workspace 配置體系，支援團隊通過 Git 共享專案級設定。
- 實現 Peer 來源可配置、可停用；預設切換為 Git 推導機制；避免現有記憶成為“孤兒”資料。
- 產出一份附帶 per-consumer 適配標註的規範優先順序表，以及通過 doctor 輸出 per-key 的解析鏈路，終結“配置到底從哪裡來”的排障黑洞。

非目標：

- 暫不更改服務端協議與鑑權模型（Peer 依然是使用者邊界內的檢視過濾，而非租戶邊界）。
- 暫不實現複雜的授權/信任（Trust）門檻（僅在風險一節預留設計空間）。
- Python SDK 與 VikingBot 不讀取 Workspace 檔案（庫或服務程序的 cwd 沒有意義，詳見適配矩陣）。
- 不涉及 Monorepo 子目錄級的 Peer 細分（留待 v2 議題）。

## 設計：配置分層

### 檔案佈局

| 文件 | 位置 | 提交到 Git | 用途 |
| --- | --- | --- | --- |
| `config.json` | `<workspace-root>/.openviking/` | 是 | 團隊共享的專案級設定 |
| `config.local.json` | `<workspace-root>/.openviking/` | 否(gitignore) | 個人對當前專案的覆蓋配置 |
| `<slot>.json` | `~/.openviking/workspaces/` | 機器本地 | 使用者級的 per-workspace 登錄檔；本次沒有 CLI 寫入器，按外掛 doctor 列印的路徑手工建立 |
| `ovcli.conf` | `~/.openviking/` | 機器本地 | 連線與憑證（維持不變）；新鍵存入 `plugin` 字典 |

Workspace 根目錄的確定規則：從生效的 cwd 向上查詢，最近的一個持有 `.git`（檔案或目錄）**或** `.openviking/config.json` / `config.local.json` 的目錄即為根目錄。`.git` 與標記檔案同在一個目錄時按 Git 處理；標記檔案在倉庫內部的子目錄先被命中時，該子目錄是配置層的根，但 Git 身份仍繼續向上取自外層倉庫（`{git_remote}` / `{git_root}` 不變，因此預設 peer 不會因為子目錄多了一份配置檔案而分裂）。對於 linked worktree，通過 `commondir` 收斂**身份**（因此兩個 worktree 共用同一個 peer 與同一條登錄檔記錄），但各自的 `.openviking/config.json` 仍跟隨所在 checkout——那是分支上的檔案；Submodule 被視為獨立倉庫，不併入父倉庫。既無 `.git` 也無標記檔案的目錄**不是 Workspace**：沒有根目錄、沒有配置層、沒有登錄檔條目，預設也不派生 peer。`$HOME` 與 `/` 不能作為 Workspace 根目錄。

使用者級登錄檔設計採用**目錄制**而非單一 JSON 檔案：每個 Workspace 對應一個許可權為 0600、支援原子寫入的小檔案，以避免多個短生命週期的 Hook 程序對同一檔案執行 read-modify-write 時造成更新丟失。定位條目時以 Workspace 根目錄路徑為依據，條目內部記錄 Git 身份鍵作為**負證據（Negative Evidence）**——當路徑命中但記錄的 Git 身份與當前倉庫衝突時，視為未命中，系統將開啟新的條目，絕不繼承舊條目的 Peer 繫結與設定。這能有效防止“同一路徑先後放置了兩個不同倉庫”時發生身份串臺。

登錄檔條目內容包括：per-workspace settings（與 Workspace 檔案共用 Schema）、`peer` 顯式繫結（手工寫入，CLI 寫入器為後續）、`previous_peer_ids`、`cli_config_profile`（詳見安全底線），以及首次/最近可見時間。

同時需一併處理已知的命名衝突問題：`.openviking` 目前也是解析器的機器本地臨時目錄（`StoragePath.BASE_DIR`，`openviking_cli/utils/storage.py:37`），並且本倉庫的 `.gitignore` 也忽略了整個 `.openviking` 目錄。解決方案：將倉庫自身與文件示例的 `.gitignore` 規則縮小為具體的臨時子路徑（如 `.openviking/media/`、`.openviking/downloads/` 等）而非整個目錄；doctor 增加“存在 `config.json` 但被 Git 忽略”的檢查項。

### 優先順序

針對同一個配置鍵，優先順序從高到低排列如下：

| 層級 | 說明 |
| --- | --- |
| 1. 環境變數 `OPENVIKING_*` | 用於部署期覆蓋，遵循專案慣例，優先順序永遠最高 |
| 2. CLI 標誌引數 | 僅 Rust CLI 存在（如 `--actor-peer-id`） |
| 3. 使用者登錄檔 `~/.openviking/workspaces/<slot>.json` | 使用者針對該 Workspace 的私有最終覆蓋 |
| 4. `<root>/.openviking/config.local.json` | 個人專案層 |
| 5. `<root>/.openviking/config.json` | 團隊專案層（需經過安全底線過濾） |
| 6. `ovcli.conf` 的 `plugin.<harness>` → `plugin` | 現有全域機制保持不變 |
| 7. `ov.conf` 的 `<harness>` 遺留塊 | 僅作向後相容讀取 |
| 8. 內建預設值 | — |

專案層（4、5）優先順序高於全域層（6）的原因在於：專案宣告的約定應當對該專案直接生效，這與 VS Code（workspace > user）和 Claude Code（project > user）的邏輯保持一致；而第 3 層則保證了使用者對任何本地倉庫始終擁有最終否決權。

必須顯式宣告本機制與現有 `OPENVIKING_CREDENTIAL_SOURCE` 開關的關係：該開關對憑證欄位起全有全無的控制作用——在 `cli` 模式下，連 `OPENVIKING_PEER_ID` 都會被忽略（`credentials.mjs:183`），在 `auto` 模式下，只要出現任一憑證類環境變數，整個鏈路就會切換到環境變數優先（`credentials.mjs:119`）。本方案規定：Workspace 身份與行為設定（`peer.source`、登錄檔、兩個 Workspace 檔案中的各個鍵）**不屬於憑證鏈**，不受 credential source 模式的影響。上表優先順序僅約束這些新鍵，憑證與連線鍵繼續維持既有的鏈路與開關語義。

各消費者的適配狀態需在文件中逐列標註（已實現 / 計劃中 / 不適用），避免規範與實現脫節：

| 層級 | JS Hooks | MCP Proxy | Rust CLI | Python SDK |
| --- | --- | --- | --- | --- |
| 環境變數 | 已有 | 已有 | 部分（無 `OPENVIKING_PEER_ID`） | 已有 |
| 登錄檔 | 新增 | 經父程序注入 | 後續（本次不含 Rust CLI） | 不適配 |
| Workspace 檔案 | 新增 | 不直讀（見 Proxy 章節） | 後續 | 不適配 |
| `ovcli.conf` | 已有 | 已有 | 已有 | 已有 |

### 合併語義

- **標量與物件**：高層級覆蓋低層級，物件型別按鍵進行深度合併。
- **列表**：預設跨層做 Union（並集）；若列表首元素為字面量 `"!reset"`，則清空所有低層繼承（參考 EditorConfig 的 `unset` 與 Git 對 `safe.directory` 的空值重置邏輯）。
- **未知鍵**：保留並忽略，永不報錯（保障前向相容性；老版本客戶端不能因遇到新版檔案而崩潰，反之亦然）。已知鍵若出現非法列舉值，則回退到預設值並丟擲一次警告。
- **`version`**：必填整數，當前固定為 1；缺失或遇到不認識的主版本號（Major）時，忽略整個檔案並警告。
- **`$schema`**：可選欄位，供編輯器自動補全與校驗使用；倉庫在 `examples/schemas/workspace-config-v1.json` 提供預留的 JSON Schema（隨 P2 的鍵集一起落地），示例中的 URL 指向其 GitHub raw 地址。客戶端在解析時會忽略該鍵。
- **`min_client_version`**：僅觸發軟警告，不阻斷執行——否則倉庫檔案將獲得對使用者外掛進行拒絕服務攻擊（DoS）的能力。

### Schema (v1)

```jsonc
{
  "$schema": "https://raw.githubusercontent.com/volcengine/OpenViking/main/examples/schemas/workspace-config-v1.json",
  "version": 1,
  "min_client_version": "0.9.0",
  "notes": "本專案的 Business Data Platform 約定,自由文本,僅展示",

  "peer": {
    "source": "git",            // 預設或模板,見「Peer 來源」
    "id": "openviking-core"     // 顯式指定,優先於 source 推導
  },

  "recall": {
    "enabled": true,
    "peer_scope": "all",        // "all" | "actor"
    "dedup_turns": 5,
    "max_items": 12
  },

  "capture": {
    "enabled": true,
    "commit_token_threshold": 20000
  },

  "bypass": {
    "session_patterns": ["*-scratch", "**/tmp/**"]  // union 合併;沿用 isBypassed 語義:對 session id 與 cwd 都匹配,`*` 不跨 `/`,跨層級用 `**`
  },

  "labels": { "project": "Business Data Platform" }
}
```

`config.local.json` 與登錄檔的 `settings` 使用同一個 Schema；登錄檔條目則額外增加 `cli_config_profile` 與 `previous_peer_ids` 等內部登記欄位。數值類配置鍵會在客戶端進行區間鉗制（例如 `commit_token_threshold` 限制在 1000..1000000，`dedup_turns` 限制在 0..20），非法列舉值直接回退為預設值。

對於來自程式碼倉庫的“關閉”類設定（如 `capture.enabled: false` 或 bypass 模式命中），系統將在 Session-start 注入的上下文塊中播報一行提示，並在 doctor 輸出中明確標註其來源——確保行為可見，但不做硬性攔截。

### 結構性安全底線

雖然不設複雜的授權門檻，但以下安全規則必須無條件成立，以確保對日常使用零摩擦：

1. **結構性禁止憑證與連線鍵**。`url`、`mcp_url`、`api_key`、`bearer_token`、`root_api_key`、`gateway_token`、`account`、`user`、`auth_mode`、`extra_headers`、`credential_source`，以及任何指向其他配置檔案的路徑鍵，一律**不允許**出現在兩個 Workspace 檔案中；解析時將直接剔除並觸發警告（非靜默）。連線與憑證資訊唯一的歸宿是：`ovcli.conf` + 環境變數。這是回答“我的資料究竟發往哪臺伺服器”時，不需要去翻閱倉庫檔案的唯一保證，邏輯上對應 Git 的 `protected configuration` 不變式。
2. **變數展開是配置層的屬性，而非解析器的屬性**。Workspace 檔案與新的登錄檔檔案由同一個引擎解析，一律使用原生的 `JSON.parse`，永不經過 `load_json_config` 或任何包含 `${VAR}` 的展開路徑；將在單元測試中斷言 `${HOME}` 在這些檔案中保持字串字面量。“維持現有的展開行為”僅針對舊有的 `ov.conf` / `ovcli.conf`（實際上現狀本身也不統一：Python Reader 會展開，JS Reader 不展開，統一與否不屬於本 RFC 的範疇）。
3. **限制 `cli_config_profile` 僅能作為名稱標識**。它只能從登錄檔（使用者側）選擇 `~/.openviking/ovcli.conf.<name>`（複用 Rust CLI 現有的命名 Profile 佈局），字元集限制為 `^[a-z0-9][a-z0-9._-]{0,63}$`，不允許包含路徑分隔符；如果 Profile 不存在，則觸發硬錯誤而不是靜默回退。此鍵**禁止**出現在倉庫提交檔案中——因為“選擇哪份憑證發往哪臺伺服器”，等價於直接篡改 `url` 的攻擊。
4. Workspace 檔案在解析前的常規防禦機制：必須是常規檔案、realpath 不能逃逸出 Workspace 根目錄、設定檔案大小上限（64 KiB）、頂級節點必須是物件；解析若發生錯誤，則進入 Hook 的 fail-open 路徑（外掛自身的錯誤不應阻塞使用者的會話）。

### Provenance 與診斷

兩個外掛的 doctor 輸出將展示 per-key 的完整解析鏈路：包括生效值、來原始檔、被更高層遮蔽的值，以及因安全底線被剔除的鍵——功能對標 `git config --show-origin --show-scope`。（注：現有的 `ov doctor` 實際上是 Python 側面向服務端環境的診斷工具，不承載此項輸出功能。）在當前三語言技術棧、多 Reader 並存的現狀下，這一診斷輸出與配置體系本身同等重要，並將其作為各 Reader 行為一致性的日常驗收手段。

## 設計：Peer 來源規則

### `peer.source`

這是新增的配置鍵，可出現在任意配置層級中（環境變數形式為 `OPENVIKING_PEER_SOURCE`；`ovcli.conf` 側為 `plugin.peerSource` / `plugin.<harness>.peerSource`）：

- 內建預設 `"git"`：啟用 Git 身份推導（這是新的預設行為），推導鏈路見下文；不在 Git 倉庫裡則不派生。
- 內建預設 `"cwd"`：保持舊行為，做到位元組級一致；這是按目錄路徑派生 peer 的唯一預設，需顯式選擇。
- 內建預設 `"none"`：完全不傳送 Peer 頭，也不寫入 `peer_id`。
- 支持模板字符串：例如 `"git-{git_remote}"`、`"{git_root}"`、`"team-{dir}"`。
- 支援模板陣列：按序嘗試，如果某條模板中的變數解析為空，則整條直接落空並嘗試下一條；全部落空則等價於 `"none"`。

`{harness}` 讓「同一倉庫下不同 agent 各存各的記憶」成為可寫得出來的配置，但**沒有任何預設使用它**：跨 agent 共享一份專案記憶通常才是使用者想要的那一側，所以拆分是 opt-in。此外 MCP proxy 不參與 peer 推導（其 cwd 不是可靠身份，見「實現落點」），因此模板裡用了 `{harness}` 時，只經由 proxy 的讀路徑解析不出該變數。

v1 支援的變數集：

| 變數 | 含義 | 空值條件 |
| --- | --- | --- |
| `{git_remote}` | 歸一化後的 origin URL（`github.com/org/repo` 形式，已清理特殊字元） | 非 Git 倉庫或不存在 origin remote |
| `{git_root}` | 倉庫根路徑（按照 legacy 規則進行字元清理）；標記檔案在倉庫內部命中時仍是倉庫根 | 非 Git 倉庫 |
| `{cwd}` | 生效的 cwd（按照 legacy 規則進行字元清理）；預設鏈路不再使用，僅供 `cwd` 預設與自定義模板 | 無 |
| `{dir}` | Workspace 根目錄的目錄名（已清理特殊字元） | 不是 Workspace |
| `{harness}` | 當前 agent 的名字，與 User-Agent 攜帶的一致（`claude-code`、`codex`、`dsh`、`opencode`、`pi`、`cursor`、`trae`、`trae-cn`、`zcode`） | 從不為空 |

預設 `"git"` 實際上等價於模板陣列 `["{git_remote}", "{git_root}"]`：優先使用 remote，若無 remote 則退回到倉庫根路徑（至少修復了子目錄分裂的問題），若不是 Git 倉庫則**落空**——不傳送 peer 頭，也不寫入 `peer_id`，記憶進入使用者級空間 `viking://user/<u>/memories`。預設情況下不新增任何字首——因為路徑類 ID（`{git_root}` / `{cwd}`）在 POSIX 系統下必然以 `-` 開頭，與 remote 的表現形態天然不衝突；如果使用者需要字首，可以自定義模板（如 `"git-{git_remote}"`）。

### 非 Git 目錄：預設不派生，按路徑派生需 opt-in

初稿的 `"git"` 預設末尾還掛著 `{cwd}` 回退，實測證明這一檔必須去掉。Codex desktop 為每個不屬於任何專案的對話（其狀態檔案裡稱為 projectless thread）新建一個 `~/Documents/Codex/<日期>/<slug>/` 目錄作為 cwd，這些目錄沒有一個是 Git 倉庫；按 cwd 回退，每個一次性任務都會鑄造一個全新的空 peer，既召回不到上一次的東西，又在服務端留下一堆只有幾條記憶的名稱空間。這不是 Codex 獨有的形態——下載解包出來的目錄、臨時目錄、其他 agent 應用生成的任務目錄都一樣。通用的訊號只有一個：它不是 Git 倉庫，也沒有任何東西宣告它是一個專案。

因此規則是：**預設只有 Git 倉庫有 peer**。既不是倉庫、也沒有標記檔案的目錄，走 peer 功能出現之前的基線——不帶 `X-OpenViking-Actor-Peer`，記憶寫進使用者級空間。想讓一個非 Git 目錄擁有自己的記憶，需要使用者主動開啟，三種方式按推薦順序：

1. 在該目錄放 `.openviking/config.json`，寫 `{"version": 1, "peer": {"id": "<名字>"}}`。顯式名字不含路徑，換機器、改目錄名都不變；標記檔案讓任意子目錄向上都能找到這個根。
2. 同一檔案裡改寫 `peer.source`（如 `"cwd"` 或 `"team-{dir}"`），適合想按路徑或目錄名派生的場景；注意 `"cwd"` 在子目錄裡會得到不同的 id，這是它的舊語義。
3. 全域 `plugin.peerSource: "cwd"`（或 `OPENVIKING_PEER_SOURCE=cwd`）恢復舊行為，適合明知自己的專案多數不是 Git 倉庫、且總是從專案根啟動的使用者。

"這裡不是 Workspace"的說明只出現在 doctor，不進入注入模型的上下文——否則 Codex 每個新任務都會吃一行噪音。

已評估並放棄的其他做法見「備選方案」；簡言之，讀 Codex 的私有狀態檔案、按 app 路徑設黑名單、為一次性目錄發固定的 `scratch` peer，都或者不通用，或者只是把問題換了個地方。

### 按場景標註 peer

| 場景 | 建議 |
| --- | --- |
| 有 origin 的倉庫 | 預設即可：所有 clone、worktree、子目錄共用一個 peer |
| Fork | 預設按 origin 與上游分開；要合併記憶，在兩邊的 `config.json` 裡寫同一個 `peer.id` |
| 無 remote 的本地倉庫 | 預設按倉庫根路徑；換機器會變，長期專案建議在 `config.json` 裡寫 `peer.id` |
| 非 Git 的長期專案目錄 | 放 `.openviking/config.json` 寫 `peer.id` |
| Monorepo 裡某個子專案要單獨記憶 | 子目錄放 `config.json`，`peer.source: "{git_remote}-{dir}"`；不寫則沿用倉庫 peer |
| 一次性任務目錄（Codex desktop 的日期目錄、臨時解包目錄） | 什麼都不做，記憶進使用者級空間 |
| 幾個目錄共享一份記憶 | 各處 `peer.id` 寫同一個值 |
| 同一倉庫下各個 agent 要各存各的 | `peer.source: "{git_remote}-{harness}"` |
| 不想按專案分 | `peer.source: "none"`（等價 `OPENVIKING_WORKSPACE_PEER=0`） |

### 更進一步的自定義（記錄方向，不在本 RFC 範圍）

模板變數集與 `peer.source` 的候選鏈是可以繼續加東西的，以下兩條已經評估過可行性，但都不隨本 RFC 交付：

**更多現成變數。** `{git_branch}` 的讀取成本很低：`resolveGitDir` 已經算出了 worktree 自己的 gitdir（linked worktree 的 `HEAD` 在自己的 gitdir 裡而不是 commondir 裡，因此必須用前者，否則讀到的是主 worktree 的分支），只需多讀一次 `HEAD` 並匹配 `ref: refs/heads/<name>`，detached HEAD 取不到名字就按既有的 all-or-nothing 規則整條落空。同理，`normalizeGitRemote` 產出的 `host/path` 再切一刀就能免費得到 `{git_host}` / `{git_owner}` / `{git_repo}`，讓 `"{git_owner}-{git_repo}"` 這類更短的 id 寫得出來。

不做的理由不在實現，而在語義與快取：分支是天天在換的，按分支拆 peer 意味著每開一個 feature 分支就進一個空的記憶名稱空間、切回來才找得到，這與 Session pin「整個會話凍結同一個 peer」的初衷直接衝突；而 identity 結果有 60 秒磁碟快取，`git checkout` 之後最多 60 秒內 peer 仍是舊分支的。若將來交付，應當與 `{harness}` 同級——提供變數，但不進任何預設，並在文件裡寫明這個代價。另需注意：舊客戶端寫下的快取條目不含新鍵，升級後的 60 秒視窗內模板會靜默判空並漂移到回退檔，因此快取讀取需要在鍵集不匹配時視為未命中。

**`peer.command`：由外部指令碼決定 peer。** 做成又一個模板變數 `{command}` 而不是平行的解析路徑，即可自動繼承既有語義：能與別的變數拼接、能放進候選列表、指令碼無輸出就整條落空並試下一條。要點是懶執行（模板裡沒提到 `{command}` 就根本不啟動程序）、定長 argv 不過 shell（沿用 `async-writer` / `doctor-core` / `host-compressor` 既有的執行姿勢）、帶超時且超時即落空、結果與 identity 同一套短 TTL 快取以保證一個 turn 只付一次代價。

它值不值得做，取決於 `peer.id`（顯式命名）與使用者級登錄檔（按 workspace 手工繫結）之外還剩多少訴求——指令碼真正獨有的場景是「對一批還沒訪問過的倉庫自動套一條規則」。此外，該鍵不應從倉庫提交的 `config.json` / `config.local.json` 讀取，只認使用者級來源，否則克隆一個倉庫即等於執行任意程式碼，本 RFC「風險與信任取捨」中列出的三條結構性底線會被一次性拆掉。

### 召回隔離

peer 是路徑字首，不是租戶邊界；隔離程度由召回引數 `peer_scope` 決定，客戶端鍵為 workspace 檔案的 `recall.peer_scope`、`ovcli.conf` 的 `plugin.recallPeerScope` 或環境變數 `OPENVIKING_RECALL_PEER_SCOPE`：

- `"all"`（預設）：召回目標是使用者級記憶 + 當前 peer 的記憶，再對 `viking://user/<u>/peers` 做一次廣度掃描，其他 peer 命中的結果按類別降分（服務端 `other_peer_penalty` 預設 events / entities 0.1，preferences / experiences 0.02），只能墊底、不會搶佔。舊 peer 下的記憶靠這一步自然迴流。
- `"actor"`：不掃描其他 peer，只看使用者級記憶與當前 peer。客戶端在這一檔下會對 Legacy ID 額外發一次查詢（見「遷移與資料連續性」）。
- 使用者級記憶在兩檔下都是全權重目標，這也是"非 Git 目錄進使用者級空間"的代價：一次性任務裡提煉出的內容會在所有專案裡參與召回。需要更強隔離的使用者可以給一次性目錄也放標記檔案，或全域切到 `"actor"`。

`peer_scope` 是逐請求引數，舊版服務端不認識時客戶端會記錄一次降級並告警，不會靜默變成 `"all"`。

顯式指定的 `peer.id` 優先順序始終高於 `source` 推導，其跨層優先順序繼續沿用現有的 explicit 語義：`OPENVIKING_PEER_ID` 環境變數 → CLI 標誌引數（`ov --actor-peer-id`）→ 登錄檔條目（手工建立）→ `config.local.json` → `config.json` → `ovcli.conf` 中的 `actor_peer_id` / `peer_id` → 遺留的 `ov.conf` 塊。出於向後相容的考慮：`OPENVIKING_WORKSPACE_PEER=0` 將繼續等價於 `peer.source: "none"`。

### Git 身份推導（零子程序）

基於熱路徑的效能約束：每個 Hook 都是新啟動的 Node 程序，推導動作發生在每一次提示詞級別的 Hook 路徑上，而且各個 Hook 的超時預算差異極大（例如 Codex `hooks.json` 中，SessionEnd 僅 3 秒，SessionStart 為 70 秒，UserPromptSubmit 為 130 秒）。出於降低延遲、滿足預算極緊場景（如 SessionEnd）的考量，同時保障健壯性（避免因環境缺少 Git 二進位制檔案或觸發 dubious-ownership 告警而失效），推導過程僅執行純檔案系統操作，不啟動 Git 子程序：

1. 向上查詢 `.git` 目錄；若 `.git` 為檔案，則讀取 `gitdir:` 的指向，通過 `commondir` 將 linked worktree 收斂至主倉庫；如果 `gitdir` 路徑包含 `modules/` 則判定為 Submodule，按獨立倉庫處理。
2. 從 `<commondir>/config` 執行純 INI 解析，讀取 `[remote "origin"] url`；不跟隨 `include` / `includeIf` 指令（取不到就直接落空，進入下一級回退邏輯）。
3. 結果寫入 `~/.openviking/state/` 下基於 cwd 的短 TTL 快取中，確保同一個 Turn 內的多個 Hook 程序只需付出一次推導代價（複用現成的 `readJsonState(name, { maxAgeMs })` 狀態檔案機制，見 `examples/claude-code-memory-plugin/scripts/lib/state.mjs:42`）。

`{git_remote}` 的歸一化規則：

```text
SCP 形式    git@github.com:volcengine/OpenViking.git
URL 形式    https://user:token@github.com:8443/volcengine/OpenViking.git/
處理步驟：  → host 提取 hostname（丟棄 userinfo 與埠），轉換為小寫
          → path 移除首尾斜槓與 .git 字尾，轉換為小寫並摺疊
最終結果：  "github.com/volcengine/openviking"；若無法解析（如 file:// 或裸本地路徑）則落空
```

由於 userinfo 在歸一化過程中被丟棄，因此 remote URL 中內嵌 token 的情況不會洩露到 Peer ID 中。大小寫摺疊使得同一倉庫的不同拼寫方式（如 SSH 與 HTTPS、大小寫差異）都能收斂到同一個身份；其代價是，在極少數區分大小寫的 Forge 平臺上，僅大小寫不同的兩個倉庫會合併到同一個名稱空間（原始的拼寫會保留在登錄檔的 `label` 中）。

字元清理（Sanitize）存在兩套規則，嚴禁混用：`{git_root}` 與 `{cwd}` 遵循 **Legacy 規則進行逐位元組替換**（即 `[^A-Za-z0-9]` → `-`，不折疊連續字元、保留前導 `-`），確保與 `peer.source: "cwd"` 在 Legacy ID 重算時達到位元組級完全一致；而 `{git_remote}`、`{dir}` 與 `{harness}` 使用新規則（適配服務端字元集 `^[a-zA-Z0-9_.@-]+$`，詳見 `openviking/core/identifiers.py:8`）：非法字元替換為 `-`，摺疊連續的 `-`，去除首尾的 `-.`，保留 `.` 使得類似 `github.com` 的域名具備可讀性；規避 `__self` 與 `ext-`（實現期核實：二者在服務端校驗層並非保留字——`__self` 只是 `session/memory/memory_isolation_handler.py` 的內部哨兵，`ext-` 只是 `ingest/peer.py` 的客戶端編碼約定；仍然規避，以免與它們撞名）；超過 100 字元時進行截斷，並在末尾追加原文雜湊的前 12 位（遠低於 AGFS 的 255 位元組段上限）。

示例：在 `/Users/x/Dev/OpenViking/examples/codex-memory-plugin` 目錄下，且 origin 為 `git@github.com:volcengine/OpenViking.git` 時，推匯出的 Peer 為 `github.com-volcengine-openviking`——無論是在任何子目錄、任何 worktree、任何機器，還是任何一份克隆，身份都保持絕對一致。

由此確立的身份語義：同一倉庫的多個本地克隆**共享**同一個 Peer（專案記憶跟著專案走）；Fork 倉庫與上游倉庫的 origin 不同，因此**預設分開**（通過 `gh pr checkout` 審查外部 PR 時，origin 依然是自己的倉庫，身份不受影響；若需合併 Fork 與上游的記憶，在兩邊寫同一個 `peer.id`）。

### 實現落點

- **推導與歸一化**：新增共享模組 `workspace-identity.mjs`；`resolveEffectivePeerId` 函式保持 `source ∈ {explicit, workspace, none}` 三值列舉不變，但新增姊妹欄位 `origin`（取值為實際產生該 id 的模板字串，如 `{git_remote}` / `{git_root}` / `{cwd}`，或 `explicit` / `disabled` / `none` / `unresolved`）。因為現有程式碼中有 5 處針對 `source === "workspace"` 的字面量硬編碼比較（Claude Code 的 session pin 兩處、Codex 的 session-start 一處，以及兩個 doctor），新增列舉會靜默破壞 session pinning 邏輯。
- **Session Pin**：Claude Code 的 `ws-peer-<sessionId>.json` 與 Codex 的 `state.workspacePeerId` 繼續在 SessionStart 階段凍結整個會話的 Peer；Pin 檔案新增版本欄位，讀取時忽略舊版本條目（目前的現狀是 pin 永不過期，讀取時沒有 `maxAgeMs` 限制）。
- **身份解析一次、向下傳遞**：每個提示詞級別的 Hook 優先讀取 pin 檔案，避免重複推導。

## 遷移與資料連續性

預設策略切換為 Git 後，已有使用者積累的舊記憶仍然存放在由 cwd 推導的舊 Peer 之下。本方案不依賴使用者執行任何一次性遷移動作：

1. **永久的雙向讀取（Dual-read）兜底**。當前 cwd 對應的 Legacy ID 永遠可以在本地重新計算得出（無需專門登記）：噹噹前生效的 Peer 與 Legacy ID 不一致時——包括非 Git 目錄如今根本沒有 Peer 的情況——recall 操作會自動兼顧舊 Peer。在預設的 `peer_scope: "all"` 模式下，現有的 peers 目錄掃描邏輯已自然覆蓋舊 Peer 的 memory 資料，實現零額外成本；而在 `peer_scope: "actor"` 模式下，recall 會額外發起一次針對 `viking://user/<u>/peers/<legacy>/memories` 的 search 請求，但該請求必須**不帶** `X-OpenViking-Actor-Peer` 頭（帶此請求頭去讀取他人的 Peer 路徑會觸發 403 硬錯誤，參考 `retrieval_targets.py:176`）。Dual-read 機制不設截止期限。需注意其覆蓋範圍：能在本地重算的僅限**當前路徑**的 Legacy ID；若倉庫已移動/改名，或歷史上曾在多個子目錄各自鑄造過 Peer，舊 ID 將無法重算，此類情況由 broad 掃描機制兜底。
2. **本次交付的保證只有第 1 條**：舊 Peer 下的記憶不搬家，recall 靠 `all` scope 的跨 Peer 掃描與 `actor` scope 的額外查詢觸達；顯式繫結與 `cli_config_profile` 通過手工建立的登錄檔條目完成。

已知邊界（需如實寫入文件）：broad 掃描的配額路徑僅覆蓋 `/memories/<bucket>/` 這樣的分類桶（而無配額的扁平路徑可能會帶回 `profile.md` 等非分類檔案），此外，舊 Peer 下的 **resources 檔案在兩條路徑下都不會被自動掃回**——Dual-read 的 actor 分支與手動 migrate 才是徹底的解決方案。服務端的 Alias 對映表（在 `normalize_actor_peer_header` 處做舊→新對映）作為遠期的備選方案，不納入本 RFC 實施範圍；需注意，該函式目前僅覆蓋了讀路徑的 Header，寫路徑中的訊息體 `peer_id` 還需另行處理；並且，專案 Changelog 曾明確決定不對 Legacy 有損 Peer 目錄進行自動回讀（因為多個身份可能發生碰撞，歸屬權應當交由操作者人工裁決），任何自動 Alias 機制都必須在此先例基礎上進行獨立論證。

## 風險與信任取捨

倉庫提交的 `config.json` 本質上是攻擊者可控的輸入（只需克隆一個倉庫即可生效）。在採取“直接信任”策略的前提下，惡意倉庫通過篡改該檔案可能造成以下影響（如實列舉）：

- **通過 `peer.id` 指向受害者的其他專案**：該倉庫產生的會話記憶將被寫入受害者其他專案的名稱空間（構成記憶投毒——記憶本質上是持久化的 Prompt 注入面），同時，其他專案的記憶也會被 recall 進該惡意倉庫控制的上下文中。
- **配置 `peer.source: "none"`**：抑制客戶端傳送 Peer 頭。請注意，傳送 Peer 頭是一個**收窄**預設檢索範圍的保護動作，去掉該 Header 後，預設的目標檢索集將退化回整個 user root——這意味著該倉庫內的會話能夠窺探使用者所有專案的記憶。
- **配置 `capture.enabled: false` 或命中 bypass 模式**：使該倉庫內的活動逃避系統記錄（反取證行為）。
- 放大數值類配置鍵的成本消耗（目前已通過客戶端區間鉗制予以緩解）。

無法越權執行的操作（由結構性底線保障）：惡意倉庫無法篡改資料發往的伺服器地址、無法讀取或外發憑證、無法通過 `${VAR}` 展開來竊取環境變數、無法切換當前使用的 `ovcli.conf` 配置。

接受上述殘餘風險的考量：由於 Hook 流程完全是非互動式的，任何設立授權門檻的做法最終都會退化為“要求使用者在每個 Workspace 先執行一條前置命令”，這種純粹的摩擦對於絕大多數良性開發場景是不可接受的。況且本專案目前的主要使用形態（個人開發者、處理自有倉庫）中，發生攻擊的前提條件較弱。相應的緩解措施為：來自程式碼倉庫的身份配置與關閉類設定一律進行播報（Session-start 時提示一行 + doctor 診斷），絕不允許靜默生效。

未來擴充性預留（僅記錄，不包含在本 RFC 實施範圍內）：若未來確需收緊安全策略，保留了兩個互不衝突的演進方向。其一，引入類似 direnv 或 mise 的一次性內容雜湊授權機制，但僅對 `peer.*` 等身份敏感鍵生效；其二，推行“Key, not authority”原則——倉庫內的檔案僅負責宣告 Workspace 的邏輯名稱，由使用者級的登錄檔將該名稱對映到實際的 Peer，從而剝奪倉庫直接指揮寫入目標的權力。這兩個方向均能在現有分層體系上增量加裝，且不會破壞本 RFC 設定的檔案格式。

## 實施階段

- **P0：基礎衛生修復（可獨立發版）**：`sync.mjs` 改為僅匯出各目標清單，並將 `main()` 邏輯擋在入口判斷之後（當前機制只要 import 就會觸發全量同步）；`sync.test.mjs` 改為匯入這些清單（現有測試清單已過期，副本漂移可能會被 CI 靜默放過）；修復 Rust 配置寫路徑中丟棄 `plugin` 段的資料丟失 Bug（`ov config add|edit` 與交互向導改用 `serde_json::Value` 級別的合併機制，確保未知鍵在往返序列化時得以保留）；為 Session pin 機制增加版本欄位；當 `peer_scope: "actor"` 被舊版服務端響應 400/422 降級時，將靜默失敗改為丟擲警告；將新編寫的測試檔案註冊進 `.github/workflows/pr.yml`。
- **P1：搭建配置引擎**：新增共享模組 `workspace-config.mjs`（負責發現、純粹的 parse、安全底線過濾、合併以及 Provenance 溯源）、`workspace-registry.mjs`（負責目錄制登錄檔讀寫、負證據查詢機制）、`workspace-identity.mjs`（負責 Git 身份推導、歸一化、Sanitize 字元清理及快取）；將上述模組加入 `HARNESS_SHARED_FILES` 以同步至 7 個目標端，同時手工同步 `agent-plugins/servers/` 下的副本；接入 `loadPluginSettings`（函式簽名增加 cwd 引數；由於 Hook 頂層呼叫的 `loadConfig()` 早於 stdin 的解析，Workspace 層的配置必須延遲懶載入），並串聯各 Harness 的 cfg 組裝點；實現外掛 doctor 的 Provenance 診斷輸出。此階段系統行為保持不變（因為新層級預設均為空）。
- **P2：Peer 來源規則與預設策略切換**：確保 `peer.source` 在全鏈路生效（環境變數 / ovcli 的 `plugin` 字典 / Workspace 檔案；為 doctor 增加對 `plugin.*` 內部已知鍵的拼寫檢查支援——現有的 `KNOWN_OVCLI_KEYS` 僅校驗頂層鍵，而 `plugin` 自身已經在白名單內）；將預設策略正式切換為 `git` 推導，非 Git 目錄預設不派生（根目錄查詢同時識別 `.openviking/config.json` 標記檔案）；上線 Dual-read 兜底機制；在 doctor 中增加對舊 Peer 的檢測邏輯；同步更新引用了舊推導規則的 5 處 README 檔案、`docs/en/agent-integrations/16-capability-reference.md`、`docs/en/configuration/02-client.md` 以及全部的中文映象文件，並在 Changelog 中詳細說明預設行為的變化與兜底恢復機制。
- **P3：CLI 命令（後續，本次 PR 不含）**：CLI 面整體推遲，本次以純外掛改動合入；Rust 側保留的只有 `ov config add|edit` 丟 `plugin` 段的修復（`serde_json::Value` 級合併）。
- **獨立 PR（涉及行為變更，需附帶 Release Note）**：Claude Code、OpenCode 及 agent-plugins 這三個 MCP Proxy 停止使用 `process.cwd()` 推導 Peer（此舉違反了其共享模組自身的約定，Codex 側已有測試禁止此行為），改為由父程序在啟動時（Launch-time）注入 `OPENVIKING_PEER_ID` 環境變數（倉庫內部已有先例：dsh 父程序就是如此注入的，見 `examples/dsh-memory-plugin/mcp.mjs:27`；若父程序未注入，其 Proxy 仍會回退到 `process.cwd()`，本次將一併修正）；當 Actor 作用域下缺乏顯式 Peer 時，觸發警告並降級處理，而不是在啟動時直接丟擲異常。

## 備選方案（已否決）

- **使用 Root-commit SHA 作為 Git 身份**：在本倉庫實測中被證偽——`git rev-list --max-parents=0 --all` 會返回 29 個根節點（結果取決於 Fetch 過哪些引用），執行 Fetch 操作會導致身份發生漂移；Shallow clone 根本沒有根節點；Fork 倉庫繼承了上游的 root commit，在常規的審查外部 PR 流程中，會導致完全零配置的身份串臺。
- **在提交的檔案中隨機生成並記錄 Workspace ID 作為唯一身份**：穩定性極佳，但嚴重依賴於該提交檔案必須存在（如果倉庫未採納或未提交該檔案則徹底無效），並且將該檔案作為“權威”來源時，等於暴露了投毒攻擊面；其“作為鍵”的設計思想已部分被未來的“Key, not authority”可選方向收錄。
- **設立授權門檻（Direnv 式的 Trust Gate 或 Key-not-authority）**：基於產品決策否決——在完全非互動的 Hook 場景下，任何授權機制都必然退化為要求使用者對每個 Workspace 單獨執行一條前置審批命令，帶來的日常操作摩擦是不可接受的；其設計要點已歸檔在「風險與信任取捨」中備用。
- **擴充 `ovcli.conf` 的頂層 Schema**：由於存在三個不同機制的 Schema 守門人（Pydantic 設定的 `extra:"forbid"`、SDK 的硬編碼白名單、Rust 重寫檔案時的靜默丟鍵行為），引入任何頂層新鍵對於舊版客戶端都是致命的硬錯誤；而 `plugin` 字典是目前唯一可行的零變更安全通道。
- **非 Git 目錄繼續按 cwd 派生（初稿的 `{cwd}` 回退檔）**：被 Codex desktop 的 projectless 目錄證偽——每個一次性任務鑄造一個 peer。為此評估過的補救都沒有采納：讀 `~/.codex/.codex-global-state.json` 裡的 `projectless-thread-ids`（Electron 私有格式、1.25 MB、僅桌面版存在，SessionEnd 只有 3 秒預算）；按 app 路徑設黑名單或在 codex 外掛內建 `~/Documents/Codex`（依賴具體應用與作業系統的目錄佈局，`~/Documents/trae_projects` 之類的目錄立刻又要補一條）；使用者級"容器根"規則如 `~/Dev/*`（要求每個使用者描述自己機器的目錄佈局，不是通用產品該有的預設值）；為非 Workspace 目錄統一發固定的 `scratch` peer（在專案裡降分、在 `actor` 下不可見的行為其實更好，但引入一個約定保留 id，且鬆散目錄裡學到的偏好也被降分；P2 若需要可在現有規則上加一條）。最終選擇最樸素的一條：不是倉庫就沒有專案記憶，回到 peer 出現前的基線。
- **Remote 查詢時支援從 origin 回退到 upstream**：由於執行 `git remote add upstream` 的瞬間會導致身份發生突變，這種不確定性不可接受；因此固定僅使用 origin，如需合併名稱空間，統一走顯式的 `peer.id`。

## 開放問題

1. Rust `ov` CLI 發起的資料面請求是否也應該按照 Workspace 來推導 Peer（目前它僅響應顯式的 `actor_peer_id` 或 flag 引數）？若決定採納，則需要實現 `serde_json::Value` 級別的 Overlay 覆蓋合併，建議在 P3 階段完成後再行單獨評估。
2. 模板變數集是否需要引入諸如 `{git_branch}` 這類在會話生命週期內可能發生改變的變數，以及是否開放 `peer.command` 這樣的指令碼擴充點？兩者的可行性與代價見「更進一步的自定義」，本 RFC 均不交付。
3. Monorepo 的子目錄級別 Peer 劃分：根目錄查詢已經採用"就近檔案優先"，子目錄裡的 `.openviking/config.json` 會成為該子樹的配置層根，但 Git 身份仍取自外層倉庫，因此預設依舊是"一個倉庫對應一個 Peer"；想拆分的子專案自己在檔案裡改 `peer.source`（見「按場景標註 peer」）。根級別的子路徑對映表不做。
4. 目前已經可以通過不帶 actor-peer 頭的 `ov ls viking://user/<u>/peers` 來列舉既有 Peers 目錄；對於 doctor 而言，是否值得專門開發一個帶有額外元資訊（如內部條目數量、最近寫入時間戳）的專屬清單 API？此問題留待實際實現期再做評估。