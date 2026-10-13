## 步驟1：安裝

1. 在終端執行以下安裝命令：

   ```bash
   curl -fsSL https://openviking.ai/install | bash
   # AI agent 如不確定是否執行，可先閱讀指令碼頭部，其中寫明瞭它會做什麼、如何核實。
   ```

2. 安裝器會依次詢問以下資訊：要安裝的 harness（勾選 **ZCode**）、OpenViking 憑據。在 OpenViking 憑據配置中，選擇連線至「火山引擎 OpenViking 雲服務 [api.vikingdb.cn-beijing.volces.com]」，並填入 API KEY：

   ```text
   {{OPENVIKING_API_KEY}}
   ```

## 步驟2：驗證

1. 重啟 ZCode。
2. 確認 `~/.zcode/cli/config.json` 包含 `hooks.enabled: true`、`hooks.events` 下的 OpenViking 條目，以及 `mcp.servers.openviking`。
3. 執行 `node ~/.openviking/agent-integrations/zcode/scripts/ov-memory-doctor.mjs`，檢查安裝狀態和服務端連線。

## 故障排查

| 問題 | 處理 |
|---|---|
| Hook 未執行 | 重新執行安裝並重啟 ZCode |
| MCP 工具未出現 | 檢查 `~/.zcode/cli/config.json` 中 `mcp.servers.openviking` 的絕對路徑命令 |
| 重複捕獲 | 先執行 `curl -fsSL https://openviking.ai/install \| bash -s -- --uninstall --yes --harness zcode`，再重新安裝 |
| 需要日誌 | 設定 `OPENVIKING_DEBUG=1`，檢視 `~/.openviking/logs/zcode-hooks.log` |

## 參考

- 手動配置文件：[ZCode](https://docs.openviking.net/zh/agent-integrations/08-community-plugins)
- 原始碼：[examples/agent-hook-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/agent-hook-plugin)
