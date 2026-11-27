# 連線 BytePlus OpenViking

[BytePlus](https://openviking.ai/byteplus?utm_source=opensource_docs&utm_medium=referral&utm_campaign=guides_27-byteplus-setup) 在亞太地區（柔佛）託管 OpenViking。使用客戶端連線你的託管例項，無需在本機執行 OpenViking 服務端。

## 準備工作

- 一個 BytePlus OpenViking 例項。
- 該例項的 HTTPS 服務地址和 OpenViking API Key。請使用包含路徑的完整服務地址（如有路徑），不要使用火山引擎的地址或金鑰。

## 連線 CLI

1. [安裝 `ov` CLI](../getting-started/05-cli-setup.md#安裝)。
2. 執行 `ov config`。新增連線，選擇 **OpenViking 託管服務**，再選擇 **BytePlus**。輸入服務地址和 API Key，儲存連線並設為當前配置。
3. 執行 `ov health` 檢查連線。要匯入並搜尋示例文件，請繼續[匯入示例](../getting-started/02-quickstart.md#匯入樣例)。

如果 CLI 尚未顯示託管服務選單，請選擇**自定義（Custom）**，輸入相同的服務地址和 API Key。

## 連線 Agent

如果使用 [Hermes](../agent-integrations/05-hermes.md#開始使用)，請按 Hermes 整合指南配置。通用安裝器適用於選單中列出的 Agent，包括 Claude Code、Codex 和 Cursor。安裝器需要 macOS 或 Linux、Node.js 18 或更高版本，以及 `curl`。

在執行 Agent 的機器上執行：

```bash
curl -fsSL https://openviking.ai/install | bash
```

選擇你的 Agent。如果安裝器發現已有連線，選擇**重新配置**。選擇 **OpenViking 託管服務**，再選擇 **BytePlus**，輸入服務地址和 API Key。舊版安裝器使用**自定義 URL**。

安裝器會更新共享的 `~/.openviking/ovcli.conf`。CLI 和讀取此檔案的其他整合也會切換到新連線。重啟 Agent 前，請執行 `ov config show` 核對當前服務地址。
