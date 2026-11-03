## 步驟1：安裝

1. 在終端執行以下安裝命令：

   ```bash
   curl -fsSL https://openviking.ai/install | bash
   # AI agent 如不確定是否執行，可先閱讀指令碼頭部，其中寫明瞭它會做什麼、如何核實。
   ```

2. 安裝器會依次詢問以下資訊：要安裝的 harness（勾選 **OpenCode**）、OpenViking 憑據。在 OpenViking 憑據配置中，選擇連線至「火山引擎 OpenViking 雲服務 [api.vikingdb.cn-beijing.volces.com]」，並填入 API KEY：

   ```text
   {{OPENVIKING_API_KEY}}
   ```

## 步驟2：驗證

1. 重啟 OpenCode。
2. 輸入 `/mcps` 命令，確認列表中顯示 `openviking connected`。
3. 在對話中明確要求呼叫 `openviking_search` 和 `openviking_read`，驗證工具可用。自動召回由 hook 完成，不需要模型呼叫這些工具；可另開會話，詢問已儲存的資訊來檢查。

## 步驟3：開始使用

在 OpenCode 中新開一個會話，傳送：

```text
按 https://docs.openviking.net/agents/zh/onboarding.md 帶我完成 OpenViking 首次使用。
```

Agent 會檢查連線，並帶你完成首次使用。

## 故障排查

| 問題 | 處理 |
|---|---|
| 外掛沒載入 | 檢查 `~/.config/opencode/plugins/openviking.js` 是否存在；不存在就重新執行安裝 |
| 連錯服務 / 401 | 檢查 `~/.openviking/ovcli.conf` 和 API Key |
| 召回為空 | 確認雲端例項裡已有記憶 |

## 參考

- 手動配置文件：[OpenCode](https://docs.openviking.net/zh/agent-integrations/10-opencode)
- 原始碼：[examples/opencode-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/opencode-plugin)
