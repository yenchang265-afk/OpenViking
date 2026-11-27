## 步驟1：安裝

1. 在終端執行以下安裝命令：

   ```bash
   curl -fsSL https://openviking.ai/install | bash
   # AI agent 如不確定是否執行，可先閱讀指令碼頭部，其中寫明瞭它會做什麼、如何核實。
   ```

2. 安裝器會依次詢問以下資訊：要安裝的 harness（勾選 **ZCode**）、OpenViking 憑據。連線配置中，選擇 **OpenViking 託管服務**，再選擇 **Volcengine** 或 **BytePlus**。

   - **Volcengine**：輸入服務 API Key，安裝器會提供服務地址。
   - **BytePlus**：先輸入例項的完整 HTTPS 服務地址，再輸入 API Key。詳見 [BytePlus 接入指南](https://docs.openviking.ai/zh/guides/27-byteplus-setup)。

   舊版安裝器連線 BytePlus 時使用**自定義 URL**。請使用所選例項的 API Key：

   ```text
   {{OPENVIKING_API_KEY}}
   ```

## 步驟2：驗證

1. 重啟 ZCode。
2. 確認 `~/.zcode/cli/config.json` 包含 `hooks.enabled: true`、`hooks.events` 下的 OpenViking 條目，以及 `mcp.servers.openviking`。
3. 執行 `node ~/.openviking/agent-integrations/zcode/scripts/ov-memory-doctor.mjs`，檢查安裝狀態和服務端連線。

## 步驟3：開始使用

在 ZCode 中新開一個會話，傳送：

```text
按 https://docs.openviking.net/agents/zh/onboarding.md 帶我完成 OpenViking 首次使用。
```

Agent 會檢查連線，並帶你完成首次使用。

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
