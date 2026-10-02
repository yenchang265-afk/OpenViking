# DeepSeek Harness 記憶外掛

為 [DeepSeek Harness](https://www.npmjs.com/package/@deepseek-ai/dsh)（`dsh`）接入跨專案、跨會話的長期記憶。安裝後每次對話都會自動召回相關記憶並捕獲新內容，模型也會直接拿到 OpenViking 工具以及 `openviking-memory`、`openviking-skills` 兩個技能，無需額外配置。

原始碼：[examples/dsh-memory-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/dsh-memory-plugin)

## 安裝

DSH 與其他記憶外掛共用同一個安裝器。它會依次詢問語言（English/中文）、要安裝的 harness、下載源和 OpenViking 憑據；每一步都是冪等的，重複執行完全安全。

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/volcengine/OpenViking/main/examples/memory-plugin-shared/install.sh)
```

GitHub 訪問困難的地區，可以從火山引擎 TOS 映象運行同一個安裝器（或在下載源選項裡選「TOS 映象」）：

```bash
bash <(curl -fsSL https://ovrelease.tos-cn-beijing.volces.com/memory-plugin-shared/install.sh)
```

選擇 DSH 後，安裝器會詢問裝到哪個 profile，預設 `web`。也可以用 `--dsh-profile <name>` 提前指定。

用一段時間後，開一個新會話問問之前提過的事情——它會記得。

<details>
<summary><b>手動安裝</b></summary>

1. **配置連線** —— 寫 `~/.openviking/ovcli.conf`（`url`、`api_key`，可選 `account`/`user`），或設定 `OPENVIKING_URL` 和 `OPENVIKING_API_KEY`。如果用純本地模式（`http://127.0.0.1:1933`，無鑑權），這步可以跳過，外掛預設就指向本地。

2. **把外掛裝進 profile**：

   ```bash
   dsh plugin --profile web add @openviking/dsh-memory-plugin
   ```

   `dsh plugin` 會轉發給 profile 目錄下的 pnpm，所以任何 profile 名都可以；`web` 是 `dsh` 首次執行時自動建立的那個。

3. **確認 profile 已生效**：

   ```bash
   dsh --profile web --dump-config
   ```

   輸出裡應該能看到 `openviking-memory` 外掛組。

> 還沒有 `ovcli.conf`？見[部署指南 → CLI](../guides/03-deployment.md#cli)。
>
> 解除安裝：`dsh plugin --profile web rm @openviking/dsh-memory-plugin`。

</details>

## 驗證

啟動 `dsh --profile web` 開啟一個會話，會話開頭應該能看到一條 OpenViking 上下文注入，模型也應該具備 `mcp__openviking__*` 工具。問一句更早會話裡聊過的事，確認召回生效。

如果什麼都沒有，設定 `OV_DEBUG_LOG=/tmp/ov-dsh.log` 後檢視該檔案。

## 工作方式

外掛以 Cordis 外掛的形式跑在 DSH 程序內，而不是外掛 hook，因此能貼著會話走。會話開始時注入 OpenViking 畫像塊、可用記憶索引和 OpenViking 技能清單 `<available-skills>`；每個模型步驟前用當前輸入做語義檢索，把結果作為持久訊息追加到同一步驟——因此注入會隨會話重放，也對壓縮可見。它直接從 DSH 的事件流捕獲 user、assistant 以及（可選的）工具結果訊息，待同步 token 超過閾值即 commit，並保留最近十條訊息在本地上下文中。寫入失敗會進入待寫佇列，在下次會話開始時重放。

每個 DSH 會話對映為 OpenViking 中的 `dsh-<session-id>`，子 agent 各自擁有獨立會話。

模型看到的工具面就是 OpenViking 的 MCP 工具集，經由與其他記憶整合相同的 stdio 代理接入，以 `mcp__openviking__` 字首釋出。由於該代理每個 profile 只起一個程序，`mcp__openviking__remember` 寫入的是服務端一個短生命週期的會話而不是當前會話（對話本身仍由自動捕獲記錄），工具呼叫帶的也是啟動時解析的 actor peer。若一個程序要服務多個工作區且需要精確歸屬工具呼叫，請顯式設定 `OPENVIKING_PEER_ID`。外掛同時附帶兩個共享技能：`openviking-memory` 讓模型知道何時該檢索、讀取和寫入，`openviking-skills` 講如何查詢、使用、建立、共享和遷移存放在 OpenViking 裡的技能。

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
| `OV_DEBUG_LOG` | — | 把除錯日誌寫到該路徑 |

行為引數寫在 profile 的 Cordis patch 條目裡：

```yaml
- insert:
    - id: openviking-memory
      name: '@deepseek-ai/cordis-plugin-group'
      group: true
      isolate:
        openvikingMemory: true
      config:
        - id: openviking-memory-runtime
          name: '@openviking/dsh-memory-plugin'
          config:
            recallTokenBudget: 2000
            scoreThreshold: 0.35
            captureToolResults: false
            commitTokenThreshold: 20000
```

同一個 `config` 塊裡的 `syncTurns: false` 讓該整合變成只讀：畫像注入和記憶召回照常，但什麼都不再寫回——不捕獲對話、不 commit，也不重放此前會話排入佇列的寫入，那些寫入會一直留在佇列裡，直到某個仍在寫入的會話把它們排空。

同一個 `config` 塊裡的 `peerSource` 決定工作區 peer 的派生方式。預設的 `"git"` 取倉庫歸一化後的 `origin` URL（`git@github.com:volcengine/OpenViking.git` 得到 `github.com-volcengine-openviking`），其次是倉庫根路徑，因此同一個倉庫的每個 clone、worktree 和子目錄共用同一個 peer；不在倉庫中則完全不傳送 peer，在那裡記下的內容進入使用者級空間 `viking://user/<you>/memories`。`"cwd"` 恢復此前的行為——把工作目錄路徑中的非字母數字字元全部替換成 `-`；`"none"` 則完全不傳送 peer。要讓倉庫之外的目錄擁有獨立記憶，請為它設定 `OPENVIKING_PEER_ID`（見[讓一個目錄擁有獨立記憶](../configuration/02-client.md#讓一個目錄擁有獨立記憶)）。

同一個 `config` 塊裡的 `skillCatalog` 和 `skillCatalogTokenBudget` 控制會話開始時注入的技能清單。清單先列你自己的技能，再列帳號內共享在 `viking://agent/skills` 下的技能，每條描述截到約 40 token；它有獨立的預算（預設 `1200` token，不佔用畫像預算），描述放不下時只列名稱。`skillCatalog: false` 或把預算設為 `0` 即可關閉；對應的環境變數是 `OPENVIKING_SKILL_CATALOG` 和 `OPENVIKING_SKILL_CATALOG_TOKEN_BUDGET`。

patch 中寫的憑證優先於環境變數。行為旋鈕按優先順序從高到低解析：`OPENVIKING_*` 環境變數、工作區的 `.openviking/config.json` 與 `config.local.json`、`ovcli.conf` 的 `plugin.dsh`、`ovcli.conf` 的 `plugin`，最後才是這個 patch 塊。完整引數列表見[外掛 README](https://github.com/volcengine/OpenViking/tree/main/examples/dsh-memory-plugin)。

</details>

## 常見問題

| 現象 | 排查方向 |
|------|----------|
| 沒有注入，也沒有 OpenViking 工具 | `dsh --profile web --dump-config` 裡應能看到 `openviking-memory`；重新執行安裝器或 `dsh plugin --profile web add …` |
| 裝到了錯誤的 profile | 安裝器預設 `web`；用 `--dsh-profile <name>` 重新執行 |
| 安裝時報 `ERESOLVE` | `@deepseek-ai/dsh-*` 各包預釋出 tag 不同步；請精確安裝 `@deepseek-ai/dsh@0.1.0-rc.6` |
| 安裝時報包「不在 npm registry 中」 | pnpm 預設拒絕釋出不滿 24 小時的版本（`minimumReleaseAge`）。等一等，或把該精確版本加進 profile 的 `pnpm-workspace.yaml` 的 `minimumReleaseAgeExclude` |
| 召不回任何內容 | `curl http://localhost:1933/health`；檢查端點配置，以及 prompt 是否長於最小查詢長度（3 個字元） |
| OpenViking 返回 401 / 403 | 檢查 `OPENVIKING_API_KEY`；可信模式部署還要檢查 `OPENVIKING_ACCOUNT` 與 `OPENVIKING_USER` |
| 串入了其他專案的記憶 | 設定 `OPENVIKING_RECALL_PEER_SCOPE=actor` |
| 崩潰後沒有 commit | commit 由 token 閾值和 teardown 觸發；排隊的寫入會在下次會話開始時重放 |

## 延伸閱讀

- [整合能力參考](./16-capability-reference.md)
