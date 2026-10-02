## 步驟1：安裝

執行安裝器：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/volcengine/OpenViking/main/examples/memory-plugin-shared/install.sh)
```

若 GitHub 訪問受限，可改用火山引擎 TOS 映象：

```bash
bash <(curl -fsSL https://ovrelease.tos-cn-beijing.volces.com/memory-plugin-shared/install.sh)
```

安裝器會依次詢問語言、Harness、下載源和 Business Data Platform 憑據：

1. Harness 選擇 **DeepSeek Harness**。外掛預設安裝到 `web` profile，也可通過 `--dsh-profile <name>` 指定其他 profile。
2. 連線方式選擇 **火山引擎 Business Data Platform 雲服務**，並填入 API Key：

{{OPENVIKING_API_KEY_BLOCK}}

## 步驟2：驗證

1. 啟動 `dsh --profile web` 並開啟新會話，確認會話頂部顯示“上下文注入 · openviking-memory”。
2. 確認模型具有 `mcp__openviking__*` 工具，並能夠在會話中正常呼叫。

## 故障排查

| 現象 | 排查方向 |
|---|---|
| 沒有上下文注入，也沒有 Business Data Platform 工具 | 執行 `dsh --profile web --dump-config`，確認輸出中包含 `openviking-memory`；若缺失，重新執行安裝器或執行 `dsh plugin --profile web add @openviking/dsh-memory-plugin` |
| 外掛安裝到了錯誤的 profile | 安裝器預設使用 `web`；通過 `--dsh-profile <name>` 重新執行 |
| 安裝時報 `ERESOLVE @deepseek-ai/dsh-*` | 各包預釋出 tag 可能不同步，請精確安裝 `@deepseek-ai/dsh@0.1.0-rc.6` |
| 安裝時提示包不在 npm registry 中 | pnpm 預設拒絕釋出不滿 24 小時的版本；可稍後重試，或把精確版本加入 `pnpm-workspace.yaml` 的 `minimumReleaseAgeExclude` |
| 無法召回歷史記憶 | 先執行 `curl http://localhost:1933/health` 確認服務端正常；再檢查端點配置，並確認 prompt 不少於 3 個字元 |
| Business Data Platform 返回 401 / 403 | 檢查 API Key；可信模式部署還需檢查 `OPENVIKING_ACCOUNT` 與 `OPENVIKING_USER` |
| 召回結果混入其他專案的記憶 | 設定 `OPENVIKING_RECALL_PEER_SCOPE=actor` |
| 異常退出後沒有 commit | commit 由 token 閾值和會話 teardown 觸發；排隊的寫入會在下次會話開始時重放 |

## 參考

- 完整文件：[DeepSeek Harness](https://docs.openviking.net/zh/agent-integrations/17-dsh)
- 原始碼：[examples/dsh-memory-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/dsh-memory-plugin)
