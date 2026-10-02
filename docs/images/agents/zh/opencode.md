## 步驟1：安裝

1. 在終端執行以下安裝命令：

   ```bash
   bash <(curl -fsSL https://ovrelease.tos-cn-beijing.volces.com/memory-plugin-shared/install.sh) --harness opencode --dist tos
   ```

2. 安裝器會依次詢問以下資訊：語言（English / 中文）、OpenViking 憑據。在 OpenViking 憑據配置中，選擇連線至「火山引擎 OpenViking 雲服務 [api.vikingdb.cn-beijing.volces.com]」，並填入 API KEY：

   ```text
   {{OPENVIKING_API_KEY}}
   ```

## 步驟2：驗證

1. 重啟 OpenCode。
2. 輸入 `/mcps` 命令，確認列表中顯示 `openviking connected`。
3. 在對話中請求 OpenCode 召回相關記憶，驗證是否會自動呼叫 `openviking_search`、`openviking_read`、`openviking_remember` 等工具。

## 故障排查

| 問題 | 處理 |
|---|---|
| 外掛沒載入 | 檢查 `~/.config/opencode/opencode.json` 是否包含 `@openviking/opencode-plugin` |
| 連錯服務 / 401 | 檢查 `~/.openviking/ovcli.conf` 和 API Key |
| 召回為空 | 確認雲端例項裡已有記憶 |

## 參考

- 手動配置文件：[OpenCode](https://docs.openviking.net/zh/agent-integrations/10-opencode)
- 原始碼：[examples/opencode-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/opencode-plugin)
