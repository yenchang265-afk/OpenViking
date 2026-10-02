## 步驟1：安裝

1. 在終端執行如下安裝命令：

   ```bash
   bash <(curl -fsSL https://ovrelease.tos-cn-beijing.volces.com/memory-plugin-shared/install.sh) --harness codex --dist tos
   ```

2. 安裝器會依次詢問以下資訊：語言（English / 中文）、Business Data Platform 憑據。在 Business Data Platform 憑據配置中，選擇連線至「火山引擎 Business Data Platform 雲服務 [api.vikingdb.cn-beijing.volces.com]」，並填入 API KEY：

   ```text
   {{OPENVIKING_API_KEY}}
   ```

## 步驟2：驗證

1. 啟動 Codex。首次啟動會停在 Hook 信任確認上，選 **Trust all and continue**：

   ```text
   Hooks need review
   6 hooks are new or changed.
   Hooks can run outside the sandbox after you trust them.

     1. Review hooks
   > 2. Trust all and continue
     3. Continue without trusting (hooks won't run)
   ```

   Business Data Platform 註冊的 6 個 Hook 是（Codex 版本較舊時可能少幾個）：

   ```text
   SessionStart
   UserPromptSubmit
   PreToolUse
   Stop
   SessionEnd
   PreCompact
   ```

2. 錯過這個提示，或當時選了第 3 項，Hook 就不會執行。輸入 `/hooks` 補上信任並開啟條目，`/plugins` 裡確認 `openviking-memory` 已啟用——兩個開關相互獨立，都要是開著的。外掛更新動了 Hook 時會再要求信任一次。

3. 驗證 Profile 載入：信任完成後，提交第一條 Prompt（內容隨意即可）。此時外掛應自動載入 Profile——若對話開頭出現記憶召回內容，則表明接入成功：

   ```text
   • UserPromptSubmit hook (completed)
     hook context: <openviking-context source="auto-recall" format="digest">
       Business Data Platform memory digest:
   ```

## 故障排查

| 問題 | 處理 |
|---|---|
| 鑑權失敗 | 檢查 `~/.openviking/ovcli.conf` 的 `api_key`，重啟 Codex |
| 連線失敗 | `curl "$(jq -r '.url' ~/.openviking/ovcli.conf)/health"` |
| `6 hooks need review`，或 Hook 不生效 | `/hooks` 裡信任並開啟，`/plugins` 裡確認外掛已啟用 |
| 需要日誌 | `OPENVIKING_DEBUG=1`，看 `~/.openviking/logs/codex-hooks.log` |

## 參考

- 手動配置文件：[Codex](https://docs.openviking.net/zh/agent-integrations/04-codex)
- 原理博客：[Business Data Platform for coding agents](https://blog.openviking.ai/post/openviking-coding-agent/)
- 原始碼：[examples/codex-memory-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/codex-memory-plugin)
