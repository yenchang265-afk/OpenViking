# CLI 入門

`ov` 是 OpenViking 的命令列客戶端。你可以在終端中用它匯入資料、檢索內容和讀取原文，也可以讓能夠執行終端命令的 Agent 呼叫它，為回答提供依據。

本頁從安裝和連線開始，帶你瀏覽一份資料、按問題檢索並讀取結果。完成後，你就可以在自己的終端或 Agent 中使用同一個 OpenViking 連線。

## 準備工作

準備以下工具和連線資訊：

| 準備項 | 獲取方式 |
| --- | --- |
| Node.js 和 npm | 從 [Node.js 官網](https://nodejs.org/en/download)安裝 LTS 版本，npm 隨安裝包提供；已有可用的 `ov` 時可直接進入[連線](#連線) |
| OpenViking 服務 | 使用已開通的火山引擎雲服務或正在執行的自建服務；還沒有服務時，先完成[快速開始](02-quickstart.md#開通或啟動服務)中的開通或啟動步驟 |
| 訪問憑據 | 雲服務使用控制台提供的 API Key；開啟認證的自建服務使用管理員提供的 User/Admin Key；預設無鑑權的本機服務可留空 |
| 一份可訪問的資料 | 使用服務中已有的資料；首次體驗可在連線成功後[匯入燈塔樣例](02-quickstart.md#匯入樣例) |

安裝 Node.js 後，重新開啟終端，確認 Node.js 和 npm 可用：

```bash
node --version
npm --version
```

CLI 通過 HTTP 連線服務。僅安裝 CLI 時，無需在本機安裝 Python 或配置模型；資料處理使用服務端配置的模型。

## 安裝

使用 npm 安裝 `ov`：

```bash
npm install -g @openviking/cli
```

安裝後設定顯示語言，便於後續互動和 Agent 呼叫。中文使用 `zh-CN`，英文使用 `en`：

```bash
ov language zh-CN
```

確認終端可以找到 CLI 並輸出版本號：

```bash
ov --version
```

如果安裝服務端時已提供 `ov`，可以直接使用已有命令。

## 連線

開啟連線嚮導，為要訪問的服務新增一個命名連線：

```bash
ov config
```

按所選服務填寫連線資訊，儲存後設為當前配置。已有對應連線時，直接選中它即可。

| 服務 | 連線型別 | 填寫內容 |
| --- | --- | --- |
| 本機預設服務 | 自定義（Custom） | URL 為 `http://127.0.0.1:1933`；預設無鑑權模式下金鑰留空 |
| 遠端自建服務 | 自定義（Custom） | 使用管理員提供的服務 URL 和 User/Admin Key |
| 火山引擎雲服務 | OpenViking Service | 使用嚮導提供的服務地址，輸入控制台取得的 API Key |

可以將連線命名為 `local`、`cloud` 等便於識別的名稱。服務 URL 指向 OpenViking 資料服務；模型的 API 地址配置在服務端。

通過嚮導輸入金鑰，可以避免把金鑰明文寫入命令歷史。在 API Key 認證模式下，普通資料訪問使用 User/Admin Key，Root Key 用於服務管理。更多身份配置見[身份認證](../guides/04-authentication.md)。

## 檢查連線

先檢視當前連線，核對服務地址。該命令會隱藏金鑰：

```bash
ov config show
```

再驗證配置、連線和認證：

```bash
ov config validate
```

檢查通過後，檢視服務健康狀態：

```bash
ov health
```

結果中的 `healthy: true` 表示服務健康。接下來讀取一份資料，確認當前身份可以訪問所需內容。資料匯入所用的模型，以及 VikingBot 的問答能力，在各自的使用步驟中驗證。

## 瀏覽與讀取

列出當前服務中可訪問的共享資料目錄：

```bash
ov ls viking://resources
```

如果還沒有資料，先[匯入燈塔樣例](02-quickstart.md#匯入樣例)，等待處理完成後回到這裡。以下使用樣例目錄 `viking://resources/lighthouse-demo`；使用自己的資料時，將命令中的目錄 URI 換成實際路徑。

展開目錄，找到資料正文對應的檔案 URI：

```bash
ov tree viking://resources/lighthouse-demo
```

複製輸出中的檔案 URI，替換下面的佔位值，讀取正文：

```bash
ov read "<檔案 URI>"
```

樣例正文包含“試點環境”和“反饋收集”等內容。能夠讀到正文，說明連線和檔案訪問已完成。

## 檢索資料

當你有具體問題時，可以先檢索相關內容，再讀取命中的原文。檢索使用服務端的模型配置，可能產生模型呼叫費用。

```bash
ov find "燈塔專案第一版怎樣收集使用者反饋？" --uri viking://resources/lighthouse-demo
```

結果會列出匹配內容及其 URI。選擇與問題相關的結果，用 `ov read` 讀取正文，核對反饋由誰收集、如何交付。CLI 返回的檢索結果可以作為 Agent 生成回答的依據。

## 交給 Agent 使用

在能夠執行終端命令的 Agent 中傳送下面的任務，讓它使用已配置的 CLI 完成檢索、閱讀和回答：

```text
請使用已配置的 ov CLI，查詢 viking://resources/lighthouse-demo 中的資料。
先按“燈塔專案第一版怎樣收集使用者反饋，需要提前準備什麼？”進行 ov find 檢索，
再用 ov read 讀取相關結果的原文，然後回答這個問題。
為關鍵結論列出來原始檔的完整 viking:// URI；資料未說明的內容請明確指出。
```

Agent 需要能訪問 `ov` 命令及其連線配置。如果 Agent 執行在另一臺電腦、容器或不同系統使用者下，在該環境中完成安裝和連線，再執行任務。

`ov chat` 則將問題傳送給服務端的 **VikingBot**。使用它需要目標服務已啟用 VikingBot；本機可按 [VikingBot](11-vikingbot.md) 章節使用 `openviking-server --with-bot` 啟動。火山引擎雲服務路徑使用上面的 Agent 呼叫方式完成問答。`ov health` 檢查的是資料服務，Bot 的可用狀態需另外檢查。

## 切換連線

同時使用雲端和本地服務時，先列出已儲存的連線：

```bash
ov config list
```

開啟選擇器，切換到目標連線：

```bash
ov config switch
```

切換後檢視當前地址，並重新檢查連線：

```bash
ov config show
ov health
```

切換連線後，命令訪問的是目標服務及當前身份下的內容。雲端匯入的資料會保留在雲端；在本地體驗同一樣例時，需要向本地服務匯入。遷移已有資料可參考[匯入匯出](15-transfer.md#資料服務間遷移)。

兩類配置檔案分別負責連線和服務執行：

| 配置檔案 | 用途 |
| --- | --- |
| `~/.openviking/ovcli.conf` | CLI 當前連線、訪問憑據和命令預設行為 |
| `~/.openviking/ov.conf` | 自建服務的模型、儲存和服務引數 |

需要指定其他配置路徑或在指令碼中管理命名連線時，檢視[客戶端配置](../configuration/02-client.md)和 `ov config --help`。

## 常用命令

| 目的 | 命令 |
| --- | --- |
| 檢視目錄 | `ov ls "<目錄 URI>"`、`ov tree "<目錄 URI>"` |
| 按問題檢索 | `ov find "問題" --uri "<目錄 URI>"` |
| 讀取原文 | `ov read "<檔案 URI>"` |
| 檢視已生成的目錄概覽 | `ov overview "<目錄 URI>"` |
| 檢視後臺任務 | `ov task status <task_id>` |
| 查詢引數 | `ov --help`、`ov <命令> --help` |

## 常見問題

| 現象 | 下一步 |
| --- | --- |
| 找不到 `npm` 或 `ov` | 安裝 Node.js 後重新開啟終端；若 npm 已可用而 `ov` 不可用，檢查 npm 全域可執行檔案目錄是否在 `PATH` 中 |
| npm 安裝許可權錯誤 | 按 [npm 官方指南](https://docs.npmjs.com/resolving-eacces-permissions-errors-when-installing-packages-globally)調整全域安裝許可權 |
| 命令提示設定語言 | 執行 `ov language zh-CN` 或 `ov language en`，儲存顯示語言 |
| 連線失敗 | 用 `ov config show` 核對當前 URL；本機服務需保持執行，再用 `ov config validate` 檢查 |
| 認證失敗或讀取被拒絕 | 核對 Key 型別和資料訪問許可權，見[身份認證](../guides/04-authentication.md) |
| 切換連線後找不到原資料 | 核對目標服務和身份；向該服務匯入樣例，或遷移原資料 |
| `ov chat` 返回 `404 page not found` | 核對當前地址是否提供 VikingBot 介面；雲服務可由已有 Agent 呼叫 CLI 完成問答，本地服務按 [VikingBot](11-vikingbot.md) 章節啟動並檢查 Bot |
| 匯入時模型返回 `UnsupportedModel` | 核對服務端 `ov.conf` 中模型名稱、端點和套餐是否匹配，參見[模型開通指南](../guides/02-volcengine-purchase-guide.md) |
| 找不到目錄概覽 | 檢視資料處理狀態；概覽是否生成取決於處理方式與配置，見[上下文層級](../concepts/03-context-layers.md) |

## 讓 Agent 配置

也可以讓 Agent 幫你完成安裝和連線。複製下面的提示詞，並補充要連線的服務型別、連線名稱和自建服務地址。API Key 通過互動向導輸入，或由已有的可信環境變數提供。

<AgentPrompt>

```text
請幫我安裝並配置 OpenViking CLI（ov），連線我指定的 OpenViking 服務。

先檢查 ov 是否已安裝；需要安裝時使用 npm install -g @openviking/cli。
如果缺少 Node.js/npm，請說明安裝方式。將 CLI 顯示語言設為 zh-CN。

根據我提供的目標，檢視 ov config list -o json，複用匹配的命名連線；
新建連線前檢視 ov config add ov-service --help 或 ov config add custom --help。
使用明確的 --name 儲存連線，並將已確認的目標設為當前配置。
如果服務型別、URL 或憑據來源缺失，請向我詢問缺失項。
遇到同名但內容不同的配置，先說明差異，再詢問是否替換。

API Key 使用 --api-key-env 從已有環境變數讀取，或通過 --api-key-stdin 傳入。
如果沒有可用的安全輸入方式，引導我在終端執行 ov config 輸入金鑰。
展示配置時使用 ov config show，避免輸出憑據。

完成後執行 ov config validate 和 ov health，檢查實際返回結果。
告訴我當前連線的服務地址、檢查結果，以及仍需處理的問題。
本次任務完成安裝和連線，資料匯入由後續任務指定。
```

</AgentPrompt>

## 下一步

繼續[快速開始](02-quickstart.md#提問並核對)，完成帶來源的資料問答；準備匯入自己的專案資料時，檢視[資料檢索](08-resources.md)。

<!-- Preserve incoming links to previous section titles. -->
<a id="_1-安裝"></a>
<a id="_2-連線"></a>
<a id="_4-瀏覽與讀取"></a>
<a id="安裝與使用-cli"></a>
<a id="準備"></a>
<a id="_1-安裝-ov"></a>
<a id="_2-新增連線"></a>
<a id="_3-檢查連線"></a>
<a id="ov-能做什麼"></a>
<a id="管理多個連線"></a>
<a id="api-key"></a>
<a id="找不到-ov"></a>
<a id="npm-報許可權錯誤"></a>
<a id="命令提示需要顯示語言"></a>
<a id="本機服務沒有響應"></a>
<a id="api-key-校驗失敗"></a>
<a id="當前配置不對"></a>
