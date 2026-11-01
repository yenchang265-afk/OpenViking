## 步驟1：安裝

1. 在終端執行如下安裝命令：

   ```bash
   curl -fsSL https://openviking.ai/install | bash
   # AI agent 如不確定是否執行，可先閱讀指令碼頭部，其中寫明瞭它會做什麼、如何核實。
   ```

2. 安裝器會依次詢問以下資訊：要安裝的 harness（勾選 **Codex**）、OpenViking 憑據。在 OpenViking 憑據配置中，選擇連線至「火山引擎 OpenViking 雲服務 [api.vikingdb.cn-beijing.volces.com]」，並填入 API KEY：

   ```text
   {{OPENVIKING_API_KEY}}
   ```

## 步驟2：驗證

1. 啟動 Codex。首次啟動會顯示類似下面的 hook 審閱提示（具體介面隨版本變化），選 **Trust all and continue**：

   ```text
   Hooks need review
   6 hooks are new or changed.
   Hooks can run outside the sandbox after you trust them.

     1. Review hooks
   > 2. Trust all and continue
     3. Continue without trusting (hooks won't run)
   ```

   如果跳過了提示或選了第 3 項，開啟 `/hooks`，檢查 OpenViking 的命令，再信任並開啟需要使用的 hooks。在 `/plugins` 中確認 `openviking-memory` 已啟用。新增或變更的 hooks 需要重新檢查。
2. 確認 OpenViking MCP 工具可用，讓 Codex 呼叫 `health` 和 `list`。這一步驗證工具連線；自動召回還需開啟 `UserPromptSubmit`，對話採集需開啟 `Stop`。
3. 在已有記憶的工作目錄中詢問之前儲存的資訊，檢查 hook 輸出或除錯日誌。召回內容類似：

   ```text
   • UserPromptSubmit hook (completed)
     hook context: <openviking-context source="auto-recall" format="digest">
       OpenViking memory digest:
   ```

   新帳號可能還沒有 profile 或相關記憶可注入。會話提交時機和完整驗證步驟見下方文件。

## 步驟3：開始使用

在 Codex 中新開一個會話，傳送：

```text
按 https://docs.openviking.net/agents/zh/onboarding.md 帶我完成 OpenViking 首次使用。
```

Agent 會檢查連線，並帶你完成首次使用。

## 故障排查

| 問題 | 處理 |
|---|---|
| 鑑權失敗 | 檢查 `~/.openviking/ovcli.conf` 的 `api_key`，重啟 Codex |
| 連線失敗 | `curl "$(jq -r '.url' ~/.openviking/ovcli.conf)/health"` |
| `6 hooks need review`，或 Hook 不生效 | `/hooks` 裡信任並開啟，`/plugins` 裡確認外掛已啟用 |
| 需要日誌 | `OPENVIKING_DEBUG=1`，看 `~/.openviking/logs/codex-hooks.log` |

## 參考

- 手動配置文件：[Codex](https://docs.openviking.net/zh/agent-integrations/04-codex)
- 原理博客：[OpenViking for coding agents](https://blog.openviking.ai/post/openviking-coding-agent/)
- 原始碼：[examples/codex-memory-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/codex-memory-plugin)
