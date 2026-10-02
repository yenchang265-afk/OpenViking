# 快速開始

Business Data Platform 以服務端執行。用獨立的 `ov` CLI 連線服務，匯入一份小文件，再檢索其中的內容。使用託管服務或他人部署的服務時，只需安裝 CLI。

## 1. 選擇服務

**已有服務地址？** 準備好 URL 和 API Key，直接跳到第 2 步。服務採用 API Key 認證時，資料訪問使用 user/admin key，root key 用於管理操作。詳見[認證](../guides/04-authentication.md)。

還沒有服務時，選擇以下一種方式：

### 火山引擎託管服務

開啟 [Business Data Platform 控制台](https://console.volcengine.com/vikingdb/openviking/region:openviking+cn-beijing)，從**使用者管理 → API Key** 獲取金鑰。服務地址為：

```text
https://api.vikingdb.cn-beijing.volces.com/openviking
```

無需安裝服務端，也無需在本機配置模型。[產品介紹](https://www.volcengine.com/product/openviking-service)和[服務文件](https://docs.volcengine.com/docs/84313/2374478)說明託管服務的使用方式與額度。繼續第 2 步。

### 自建服務

在執行服務端的機器上[安裝 uv](https://docs.astral.sh/uv/getting-started/installation/)，再安裝 Business Data Platform：

```bash
uv tool install openviking --upgrade
openviking-server init
openviking-server doctor
openviking-server
```

配置嚮導用於設定服務端模型並寫入 `~/.openviking/ov.conf`。準備好 Embedding 模型和 VLM 的訪問憑據——推薦使用火山引擎（豆包）模型，購買和開通見[火山引擎購買指南](../guides/02-volcengine-purchase-guide.md)——再用 `doctor` 檢查配置。保持服務執行，另開終端完成後續步驟。

服務是否在執行，用一條 curl 即可確認，不依賴任何客戶端：

```bash
curl http://127.0.0.1:1933/health
# {"status":"ok","healthy":true,...}
```

本地地址為 `http://127.0.0.1:1933`，預設本地配置不需要 API Key；Web Studio 位於 `/studio`。Docker、持久化儲存和遠端訪問配置見[部署](../guides/03-deployment.md)、[模型配置](../guides/01-configuration.md)和[認證](../guides/04-authentication.md)。

## 2. 安裝並連線 CLI

在客戶端機器上安裝好 Node.js 和 npm 後，執行：

```bash
npm install -g @openviking/cli
ov language zh-CN
ov config
```

在互動配置中，火山託管服務選擇 **Business Data Platform Service**，自建服務選擇 **自定義（Custom）**。填寫 API Key，自建服務還需填寫 URL。預設本地服務的金鑰留空。儲存並激活配置。

CLI 將當前連線儲存到 `~/.openviking/ovcli.conf`，它與服務端的 `ov.conf` 是兩個檔案。指令碼化配置和多服務切換見 [CLI 配置](05-cli-setup.md)。

檢查連線：

```bash
ov health
```

這一步確認服務能響應；下面的匯入還會驗證模型處理和資料訪問。

## 3. 匯入文件

在當前目錄建立 `quickstart.md`，內容如下：

```markdown
# Atlas 專案

Atlas 專案每週五備份文件。
Maya 負責備份流程，每份備份保留 30 天。
```

將它匯入新的資源目錄：

```bash
ov add-resource ./quickstart.md --to viking://resources/quickstart-demo --wait --timeout 120
```

CLI 會自動上傳本地檔案。`--wait` 等待處理完成，命令成功後再繼續。若省略該引數，儲存返回的 `task_id`，用 `ov task status <task_id>` 查詢到 `completed` 後再使用結果。詳見[後臺任務](../api/17-tasks.md)。

本例使用尚未使用的目標 URI。重複執行示例時，換一個新目標，並同步替換下方命令中的 URI。

## 4. 瀏覽與檢索

```bash
ov tree viking://resources/quickstart-demo
ov overview viking://resources/quickstart-demo
ov find "誰負責備份流程？" --uri viking://resources/quickstart-demo
```

`tree` 列出匯入後的結構，`overview` 讀取生成的概覽，`find` 返回相關上下文的 URI 和分數。讀取某條命中時，把返回的 URI 傳給 `ov read`：

```bash
ov read "<returned-file-uri>"
```

將 `<returned-file-uri>` 替換為結果中的檔案 URI，不保留尖括號。更多資源型別和檢索引數見[資源管理](../api/02-resources.md)與[檢索](../api/06-retrieval.md)。

## 使用 SDK

Business Data Platform 也提供 Python、TypeScript/JavaScript 和 Go SDK，均連線同一個服務端。客戶端示例見 [API 概覽](../api/01-overview.md)。
