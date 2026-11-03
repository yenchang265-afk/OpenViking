<a id="匯入並檢索第一份文件"></a>

# 快速開始

當你希望 AI Agent 根據專案資料回答問題時，需要先讓它找到相關內容，再讀取原文。OpenViking 是面向 Agent 的上下文資料庫，負責儲存和檢索這些資料，讓 Agent 能夠根據來源生成回答。

接下來，你會匯入一份虛構的“燈塔專案”說明，讓 Agent 回答反饋收集的問題，並開啟它引用的原文核對結果。你可以使用火山引擎雲服務，也可以在本機執行 OpenViking：兩條路徑都會完成 **匯入資料 → 檢索與讀取 → 生成回答 → 核對來源**。

## 準備工作

先選擇執行方式，再安裝對應的工具：

| 執行方式 | 適合的情況 | 需要準備 |
| --- | --- | --- |
| **火山引擎雲服務** | 希望使用託管服務，並在已有 Agent 中提問 | Node.js/npm、火山引擎帳號，以及能在本機執行終端命令的 Agent |
| **本地服務** | 希望在自己的電腦上執行，並直接使用內建 Agent VikingBot | Node.js/npm、uv、Python，以及模型訪問憑據 |

### 安裝 Node.js

兩條路徑都通過 `ov` CLI 操作資料。開啟 [Node.js 下載頁](https://nodejs.org/en/download)，選擇與你的系統匹配的 **LTS** 版本，按頁面提供的安裝程式或命令完成安裝；npm 會隨 Node.js 一同安裝。

安裝後重新開啟終端，確認兩個命令都能輸出版本號：

```bash
node --version
npm --version
```

使用雲服務時，可以直接進入[開通或啟動服務](#開通或啟動服務)。

### 準備本地執行環境

本地服務使用 uv 安裝 OpenViking，並使用 Python 執行。下面以 macOS / Linux 終端為例；其他系統的安裝方式可檢視 [uv 安裝指南](https://docs.astral.sh/uv/getting-started/installation/)和[服務端部署](../guides/03-deployment.md)。

先安裝 uv：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

重新開啟終端，確認 uv 可用：

```bash
uv --version
```

再用 uv 安裝 Python 3.13，供後續服務使用：

```bash
uv python install 3.13
```

已有 Python 3.13 時可直接使用。其他安裝方式見 [Python 下載頁](https://www.python.org/downloads/)和 [uv 的 Python 管理指南](https://docs.astral.sh/uv/guides/install-python/)。

最後，準備兩個模型的呼叫資訊：**Embedding 模型**用於資料向量化和檢索，**支援工具呼叫的 VLM**用於內容理解和 VikingBot 回答。每個模型需要模型名、呼叫端點及 API Key；可按[火山引擎模型開通指南](../guides/02-volcengine-purchase-guide.md)取得這些資訊。使用 Agent Plan 時，選擇套餐支援的模型與端點。匯入資料和生成回答會產生模型呼叫，按所選服務計費。

<a id="_1-啟動服務"></a>

<a id="_1-選擇服務"></a>

<a id="_1-開通或啟動服務"></a>

## 開通或啟動服務

選擇下面的一條路徑，完成後繼續[連線 CLI](#連線-cli)。

<a id="火山引擎託管服務"></a>

### 火山引擎雲服務

雲服務負責執行 OpenViking 和處理資料，你的電腦只需安裝客戶端。

1. 開啟 [OpenViking 控制台](https://console.volcengine.com/vikingdb/openviking/region:openviking+cn-beijing)，登入火山引擎帳號，並按控制台提示開通服務。套餐與額度可在[服務說明](https://docs.volcengine.com/docs/84313/2374478)中檢視。
2. 在控制台取得用於訪問 OpenViking 的 **API Key**，供下一步配置 CLI 使用。
3. 準備一個能在本機執行終端命令的 Agent。在“提問並核對”中，通過它呼叫 `ov` 檢索雲端資料並生成回答；接入方式可檢視 [CLI 入門](05-cli-setup.md)。

取得 API Key 後，繼續[連線 CLI](#連線-cli)。

<a id="自建服務"></a>

### 本地服務

先安裝 OpenViking 和 VikingBot，讓本機同時具備資料管理和問答能力：

```bash
uv tool install --python 3.13 "openviking[bot]" --upgrade
```

接著執行初始化嚮導。選擇本機訪問，並填寫準備好的 Embedding 和 VLM 模型資訊；VikingBot 預設使用這裡配置的 VLM。

```bash
openviking-server init
```

配置完成後，檢查模型和服務配置。若檢查報告錯誤，按提示修正對應專案後再次檢查：

```bash
openviking-server doctor
```

檢查通過後，啟動服務和 VikingBot。保持這個終端執行，後續操作在另一個終端中進行。

```bash
openviking-server --with-bot
```

在新終端中確認資料服務和 Agent 都已就緒：

```bash
curl -f http://127.0.0.1:1933/health
curl -f http://127.0.0.1:1933/bot/v1/health
```

分別看到 `healthy: true` 和 Bot 的 `status: healthy` 後，繼續連線 CLI。

<a id="_2-安裝並連線-cli"></a>

<a id="_2-連線-cli"></a>

## 連線 CLI

安裝 CLI，以便在終端中匯入、檢索和讀取資料。已有 `ov` 時可以跳過安裝命令。

```bash
npm install -g @openviking/cli
```

將介面語言設為中文，再開啟連線嚮導：

```bash
ov language zh-CN
ov config
```

在嚮導中新增連線，按所選路徑填寫，然後儲存並設為當前配置：

| 執行方式 | 連線型別 | 填寫內容 |
| --- | --- | --- |
| 火山引擎雲服務 | **OpenViking Service** | 按嚮導使用服務地址，輸入控制台取得的 API Key |
| 本地服務 | **自定義（Custom）** | URL 填寫 `http://127.0.0.1:1933`；預設本機模式的金鑰留空 |

如果本地服務已有認證配置，使用對應的 User/Admin Key；配置方式見[身份認證](../guides/04-authentication.md)。

檢查當前連線，成功後即可開始匯入：

```bash
ov health
```

<a id="_3-匯入文件"></a>

<a id="_3-匯入樣例"></a>

## 匯入樣例

<a href="/quickstart/lighthouse.zh.txt" download="lighthouse.zh.md">下載燈塔專案資料</a>，儲存為 `lighthouse.zh.md`，然後在終端中進入該檔案所在目錄。資料包含試點的網路條件、反饋收集方式和未確定事項。

將它匯入獨立的演示目錄，並通過 `--wait` 等待處理完成。再次體驗時，可將 `lighthouse-demo` 換成一個新的目錄名，並在後續命令中使用相同名稱。

```bash
ov add-resource ./lighthouse.zh.md --to viking://resources/lighthouse-demo --wait
```

處理成功後，檢視匯入的檔案：

```bash
ov tree viking://resources/lighthouse-demo
```

如果等待超時，使用返回的任務 ID 執行 `ov task status <task_id>` 檢視進度。任務完成後繼續；任務失敗時，先根據錯誤資訊修正模型或連線配置，再重試。任務狀態說明見[任務管理](../api/17-tasks.md)。

<a id="_4-瀏覽與檢索"></a>

<a id="_4-提問並核對"></a>

## 提問並核對

### 檢索並讀取資料

先查詢與反饋收集相關的內容：

```bash
ov find "燈塔專案第一版怎樣收集使用者反饋？" --uri viking://resources/lighthouse-demo
```

結果中會包含匹配內容的 URI。複製其中的來原始檔 URI，替換下面的佔位值，開啟原文：

```bash
ov read "<來原始檔 URI>"
```

能讀到“試點環境”和“反饋收集”等內容後，就可以讓 Agent 使用這些資料回答問題。

### 讓 Agent 生成回答

**使用雲服務：** 在能夠執行本機終端命令的 Agent 中傳送下面的任務。讓它使用剛才配置好的 CLI 連線；如果 Agent 執行在另一臺機器或獨立容器中，先在那裡完成[CLI 連線配置](#連線-cli)。

```text
請使用本機已配置的 ov CLI，根據 OpenViking 中的專案資料回答問題。
先執行 ov health 確認連線，再執行：
ov find "燈塔專案第一版怎樣收集使用者反饋？" --uri viking://resources/lighthouse-demo
用 ov read 讀取檢索結果中的相關原文，然後回答：
燈塔專案第一版應怎樣收集使用者反饋，需要提前準備什麼？
請只依據該目錄中的資料，為關鍵結論列出來原始檔的完整 viking:// URI，
並明確指出資料未說明的內容。
```

**使用本地服務：** 通過 `ov chat` 把同一個問題交給已啟動的 VikingBot，它會呼叫檢索和讀取工具：

```bash
ov chat -m "請只使用 viking://resources/lighthouse-demo 中的資料，先按問題進行語義檢索，再讀取相關原文並回答：燈塔專案第一版應怎樣收集使用者反饋，需要提前準備什麼？為關鍵結論列出來原始檔的完整 viking:// URI；資料沒有說明的部分請明確指出。"
```

### 核對回答的依據

開啟回答引用的來原始檔，逐項比較下面的事實。回答可以採用不同措辭，關鍵是結論與原文一致。

| 應包含的結論 | 原文依據 |
| --- | --- |
| 反饋儲存在本地，由試點管理員每週匯出並交給專案負責人 | “反饋收集” |
| 提前準備離線安裝包和本地儲存目錄 | “試點環境” |
| 第一版沒有云端同步，後續是否支援尚未決定 | “反饋收集” |

如果某項結論缺少來源，可以請 Agent 補充引用並重新核對。再問一次“試點何時結束？”，檢視它是否根據資料說明該日期尚未確定。

至此，你已經完成了資料匯入、檢索、原文讀取和帶來源的問答。接下來可以換成自己的資料，重複這個流程。

## 常見問題

| 現象 | 下一步 |
| --- | --- |
| 安裝後找不到 `uv`、`node` 或 `ov` | 重新開啟終端；仍不可用時，按對應安裝指南檢查命令路徑 |
| `ov health` 連線失敗 | 在 `ov config` 中檢查當前連線、服務地址和 API Key；本地服務同時檢查執行終端 |
| Bot 健康檢查返回 `503` | 確認已使用 `--with-bot` 啟動，檢視服務終端及 [VikingBot 日誌](../guides/17-vikingbot.md) |
| 匯入失敗或檢索無結果 | 檢視返回的任務狀態，確認模型可用、處理完成且查詢 URI 與匯入目標一致 |
| 模型返回 `UnsupportedModel` | 核對模型名、端點和套餐是否匹配，參見[模型開通指南](../guides/02-volcengine-purchase-guide.md) |
| Agent 無法呼叫 `ov` | 在 Agent 使用的終端中檢查 `ov --version` 和 `ov health`，完成安裝及連線配置 |

<a id="使用-sdk"></a>

## 下一步

繼續[資料檢索](08-resources.md)，用多份資料體驗需要綜合來源和資料未覆蓋的問題，再用[效果評估](06-evaluate.md)記錄自己的任務結果。
