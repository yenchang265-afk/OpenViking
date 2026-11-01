## 步驟1：安裝

1. 在終端執行如下安裝命令：

   ```bash
   curl -fsSL https://openviking.ai/install | bash
   # AI agent 如不確定是否執行，可先閱讀指令碼頭部，其中寫明瞭它會做什麼、如何核實。
   ```

2. 安裝器會依次詢問以下資訊：要安裝的 harness（勾選 **Cursor**）、OpenViking 憑據。在 OpenViking 憑據配置中，選擇連線至「火山引擎 OpenViking 雲服務 [api.vikingdb.cn-beijing.volces.com]」，並填入 API KEY：

   ```text
   {{OPENVIKING_API_KEY}}
   ```

## 步驟2：驗證

1. 點選「Customize → MCPs」，確認可以看到「openviking User」和「openviking Plugin」兩項。
2. 點選「Customize → Hooks」，確認可以看到「openviking-memory」條目。

## 步驟3：開始使用

在 Cursor 中新開一個會話，傳送：

```text
按 https://docs.openviking.net/agents/zh/onboarding.md 帶我完成 OpenViking 首次使用。
```

Agent 會檢查連線，並帶你完成首次使用。

## 故障排查

| 問題 | 處理 |
|---|---|
| Hook 沒跑 | 完全退出 Cursor，重啟，再建會話 |
| 連線 / 鑑權失敗 | 檢查 `~/.openviking/ovcli.conf`，重啟 Cursor |
| 需要日誌 | `OPENVIKING_DEBUG=1`，看 `~/.openviking/logs/cursor-hooks.log` |

## 參考

- 手動配置文件：[Cursor](https://docs.openviking.net/zh/agent-integrations/12-cursor)
- 原始碼：[examples/agent-hook-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/agent-hook-plugin)
