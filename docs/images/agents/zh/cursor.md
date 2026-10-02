## 步驟1：安裝

1. 在終端執行如下安裝命令：

   ```bash
   bash <(curl -fsSL https://ovrelease.tos-cn-beijing.volces.com/memory-plugin-shared/install.sh)
   ```

2. 安裝器會依次詢問以下資訊：語言（English / 中文）、Business Data Platform 憑據。在 Business Data Platform 憑據配置中，選擇連線至「火山引擎 Business Data Platform 雲服務 [api.vikingdb.cn-beijing.volces.com]」，並填入 API KEY：

   ```text
   {{OPENVIKING_API_KEY}}
   ```

## 步驟2：驗證

1. 點選「Customize → MCPs」，確認可以看到「openviking User」和「openviking Plugin」兩項。
2. 點選「Customize → Hooks」，確認可以看到「openviking-memory」條目。

## 故障排查

| 問題 | 處理 |
|---|---|
| Hook 沒跑 | 完全退出 Cursor，重啟，再建會話 |
| 連線 / 鑑權失敗 | 檢查 `~/.openviking/ovcli.conf`，重啟 Cursor |
| 需要日誌 | `OPENVIKING_DEBUG=1`，看 `~/.openviking/logs/cursor-hooks.log` |

## 參考

- 手動配置文件：[Cursor](https://docs.openviking.net/zh/agent-integrations/12-cursor)
- 原始碼：[examples/agent-hook-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/agent-hook-plugin)
