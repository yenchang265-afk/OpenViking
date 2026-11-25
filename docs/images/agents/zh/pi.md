## 步驟1：安裝

1. 在終端執行以下安裝命令：

   ```bash
   curl -fsSL https://openviking.ai/install | bash
   # AI agent 如不確定是否執行，可先閱讀指令碼頭部，其中寫明瞭它會做什麼、如何核實。
   ```

2. 安裝器會依次詢問以下資訊：要安裝的 harness（勾選 **pi**）、OpenViking 憑據。連線配置中，選擇 **OpenViking 託管服務**，再選擇 **Volcengine** 或 **BytePlus**。

   - **Volcengine**：輸入服務 API Key，安裝器會提供服務地址。
   - **BytePlus**：先輸入例項的完整 HTTPS 服務地址，再輸入 API Key。詳見 [BytePlus 接入指南](https://docs.openviking.ai/zh/guides/27-byteplus-setup)。

   舊版安裝器連線 BytePlus 時使用**自定義 URL**。請使用所選例項的 API Key：

   ```text
   {{OPENVIKING_API_KEY}}
   ```

## 步驟2：驗證

1. 啟動 `pi`，確認底部狀態列顯示 `OV ✓`。
2. 輸入 `/viking` 命令，確認顯示當前 session 對映和已註冊的 `openviking_*` 工具數量。
3. 新開會話，詢問之前提到過的資訊，確認召回生效。

## 步驟3：開始使用

在 pi 中新開一個會話，傳送：

```text
按 https://docs.openviking.net/agents/zh/onboarding.md 帶我完成 OpenViking 首次使用。
```

Agent 會檢查連線，並帶你完成首次使用。

## 故障排查

| 問題 | 處理 |
|---|---|
| 擴充沒載入 | 檢查 `~/.pi/agent/extensions/openviking/index.ts` 是否存在；不存在就重新執行安裝。不要再用 `pi install` 註冊，否則會載入兩遍 |
| `/viking` 命令出現兩個 | 執行 `pi remove ~/.pi/agent/extensions/openviking`，刪掉多餘的 `packages` 條目 |
| 狀態列顯示 `OV ✗` / 401 | 檢查 `~/.openviking/ovcli.conf` 和 API Key |
| 狀態列顯示 `tools ✗` | 執行 `/viking` 檢視握手錯誤；`/mcp` 拒絕 root API Key，請改用 user key |

## 參考

- 手動配置文件：[pi](https://docs.openviking.net/zh/agent-integrations/11-pi)
- 原始碼：[examples/pi-coding-agent-extension](https://github.com/volcengine/OpenViking/tree/main/examples/pi-coding-agent-extension)
