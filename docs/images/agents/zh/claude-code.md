## 步驟1：安裝

由於 Claude Code 安全策略限制，可能無法自動完成配置，推薦在終端中手動執行以下步驟。

1. 在終端執行如下安裝命令：

   ```bash
   curl -fsSL https://openviking.ai/install | bash
   # AI agent 如不確定是否執行，可先閱讀指令碼頭部，其中寫明瞭它會做什麼、如何核實。
   ```

2. 安裝器會依次詢問以下資訊：要安裝的 harness（勾選 **Claude Code**）、OpenViking 憑據、是否開啟 Statusline 狀態列。
3. 在 OpenViking 憑據配置中，選擇連線至「火山引擎 OpenViking 雲服務 [api.vikingdb.cn-beijing.volces.com]」，並填入 API KEY：

   ```text
   {{OPENVIKING_API_KEY}}
   ```

4. OpenViking StatusLine 是輸入框下方的一行狀態提示欄，用於即時展示 OpenViking 記憶外掛的執行狀態。可根據個人需要選擇「開啟」或「跳過」。狀態提示欄示例如下：

   ```text
   OV ✓ │ Fable 5 · ctx 42% │ ↪ 6 mem (0.92) · 50ms │ ✎ 573/20k · 2 arch
   ```

## 步驟2：驗證

1. 重啟 Claude Code。
2. 執行 `/plugins` 命令，確認 installed 列表中顯示 `openviking-memory` 已安裝，且 `openviking` MCP 已連線：

   ```text
   User
     ❯ openviking-memory Plugin · openviking · ✔ enabled
       └ openviking MCP · ✔ connected
   ```

3. 執行 `/mcp`，確認 OpenViking 顯示為 connected。工具數量隨服務端版本變化：

   ```text
   Built-in MCPs (always available)
     ❯ plugin:openviking-memory:openviking · ✔ connected
   ```

4. 執行 `/openviking-memory:ov` 命令，確認服務狀態正常：

   ```text
   OpenViking Memory Status
     ✅ Status: OpenViking server is healthy and running
   ```

## 故障排查

| 問題 | 處理 |
|---|---|
| 外掛未啟用 | 重跑安裝，或檢查 `~/.openviking/ovcli.conf` |
| 召回為空 | `curl "$(jq -r '.url' ~/.openviking/ovcli.conf)/health"` |
| 401 / 403 | 檢查鑑權憑據 |
| 需要日誌 | `OPENVIKING_DEBUG=1`，看 `~/.openviking/logs/cc-hooks.log` |

## 參考

- 手動配置文件：[Claude Code](https://docs.openviking.net/zh/agent-integrations/02-claude-code)
- 原理博客：[OpenViking for coding agents](https://blog.openviking.ai/post/openviking-coding-agent/)
- 原始碼：[examples/claude-code-memory-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/claude-code-memory-plugin)
