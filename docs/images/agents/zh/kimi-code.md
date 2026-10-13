## 步驟1：安裝

1. 在終端執行以下安裝命令：

   ```bash
   curl -fsSL https://openviking.ai/install | bash
   # AI agent 如不確定是否執行，可先閱讀指令碼頭部，其中寫明瞭它會做什麼、如何核實。
   ```

2. 安裝器會依次詢問以下資訊：要安裝的 harness（勾選 **Kimi Code**）、OpenViking 憑據。在 OpenViking 憑據配置中，選擇連線至「火山引擎 OpenViking 雲服務 [api.vikingdb.cn-beijing.volces.com]」，並填入 API KEY：

   ```text
   {{OPENVIKING_API_KEY}}
   ```

## 步驟2：驗證

1. 在 Kimi Code 中執行 `/reload`，或新建會話。
2. 確認 `~/.kimi-code/plugins/installed.json` 中有 `openviking-memory` 條目。
3. 新開會話，詢問之前提到過的資訊，確認召回生效。

## 故障排查

| 問題 | 處理 |
|---|---|
| 外掛沒載入 | 檢查 `~/.kimi-code/plugins/managed/openviking-memory/` 是否存在；不存在就重新執行安裝，再執行 `/reload` |
| 連錯服務 / 401 | 檢查 `~/.openviking/ovcli.conf` 和 API Key |
| 需要日誌 | 設定 `OPENVIKING_DEBUG=1`，檢視 `~/.openviking/logs/kimicode-hooks.log` |
| 只解除安裝該外掛 | `curl -fsSL https://openviking.ai/install \| bash -s -- --uninstall --yes --harness kimicode` |

## 參考

- 手動配置文件：[Kimi Code](https://docs.openviking.net/zh/agent-integrations/08-community-plugins)
- 原始碼：[examples/agent-hook-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/agent-hook-plugin)
