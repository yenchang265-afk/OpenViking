# VikingBot

VikingBot 是 OpenViking 內建的 AI Agent，可以接收任務、呼叫模型和工具，並結合 OpenViking 中的資料、記憶和技能生成回答。你可以通過命令列與它對話，整理任務、查詢專案資料，或按照技能完成重複工作。

本節採用本機執行方式，帶你啟動 VikingBot、整理一份任務清單，再在同一會話中繼續追問。完成後，你可以確認服務連線正常、模型能夠回覆，以及後續對話能沿用已有上下文。

## 準備環境

開始前，請準備以下環境：

| 準備項 | 用途與準備方式 |
| --- | --- |
| uv 和 Python | 安裝並執行 OpenViking 與 VikingBot。以下命令使用 Python 3.13，安裝方法見[準備本地執行環境](02-quickstart.md#準備本地執行環境) |
| Node.js/npm | 安裝 `ov` CLI，安裝方法見[安裝 Node.js](02-quickstart.md#安裝-node-js) |
| 模型訪問憑據 | 準備 Embedding 模型和支援工具呼叫的 VLM 的模型名、端點及 API Key，開通方法見[模型開通指南](../guides/02-volcengine-purchase-guide.md) |

VikingBot 預設使用 OpenViking 配置中的 VLM，Embedding 模型用於後續資料檢索。使用 Agent Plan 時，選擇套餐支援的模型與端點；模型呼叫按所選服務計費。

如果已經按快速開始啟動了帶 VikingBot 的本機服務，可以直接進入[連線 CLI](#連線-cli)。

<a id="啟動與連線"></a>

## 啟動服務

安裝 OpenViking 和 VikingBot，讓本機具備資料管理和 Agent 對話能力：

```bash
uv tool install --python 3.13 "openviking[bot]" --upgrade
```

首次使用時，執行初始化嚮導，選擇本機訪問並填寫準備好的模型資訊。已有配置時，可以直接進行配置檢查。

```bash
openviking-server init
```

檢查模型和服務配置。如果報告錯誤，按提示修正對應專案後再次檢查：

```bash
openviking-server doctor
```

已有服務啟用了 API Key 認證時，可先按[身份認證](../guides/04-authentication.md)為 Bot 配置連線身份，併為 CLI 準備相應的 User/Admin Key。

檢查通過後，一起啟動 OpenViking 和 VikingBot。`--with-bot` 會啟用 Agent 對話入口；保持這個終端執行，後續命令在另一個終端中執行。如果本機服務已在執行但尚未啟用 Bot，可先在原終端停止服務，再使用下面的命令啟動。

```bash
openviking-server --with-bot
```

本節後續命令使用預設地址 `http://127.0.0.1:1933`。

## 連線 CLI

在新終端中安裝 CLI。已有可用的 `ov` 時，可以直接配置連線。

```bash
npm install -g @openviking/cli
```

將介面語言設為中文，再開啟連線嚮導：

```bash
ov language zh-CN
ov config
```

選擇自定義（Custom）連線，URL 填寫 `http://127.0.0.1:1933`，預設本機模式的金鑰留空；已啟用認證時，填寫準備好的 User/Admin Key。儲存並設為當前配置；已有對應連線時，直接選擇它即可。更多連線方式見 [CLI 入門](05-cli-setup.md)。

先確認 CLI 能連線資料服務：

```bash
ov health
```

結果中應包含 `healthy: true`。接著檢查 Bot 對話入口：

```bash
curl -f http://127.0.0.1:1933/bot/v1/health
```

返回 `status: healthy` 後，可以開始對話。接下來的任務會進一步確認模型能否正常生成回覆。

<a id="完成任務並追問"></a>

## 完成一次任務

將一份虛構的任務清單交給 VikingBot，讓它按完成狀態整理。`--session` 指定本次會話，後續使用同一名稱可以繼續討論這份清單。重複體驗時，可將示例中的會話名換成新的名稱。

```bash
ov chat --session bot-review-v1 -m "以下是虛構任務清單：資料匯入已完成，來源核對待完成，演示排練待完成。請整理為簡短的已完成和待完成清單。"
```

回覆應將“資料匯入”列為已完成，將“來源核對”和“演示排練”列為待完成。你可以對照輸入檢查狀態是否保留準確；具體措辭和排版可以不同。

## 繼續追問

保持同一個 `--session`，請 VikingBot 根據已有清單建議下一步：

```bash
ov chat --session bot-review-v1 -m "沿用剛才的清單，建議先完成哪一步，並用一句話說明理由。"
```

這次無需重新提供任務清單，回覆應圍繞“來源核對”和“演示排練”提出建議。例如，可以建議先核對來源，以便在演示前確認內容準確。建議順序可以不同，依據應來自前一輪的待辦事項。

同一會話中的追問會使用已有對話上下文。使用新的會話名稱可以開始另一段對話；希望在不同會話中複用專案背景或偏好時，可繼續[記憶使用](09-memory.md)，瞭解記憶的儲存與召回。

## 檢查結果

| 檢查項 | 預期結果 |
| --- | --- |
| 服務連線 | `ov health` 和 Bot 健康檢查均成功 |
| 單次任務 | 回覆準確保留三項任務及其完成狀態 |
| 連續對話 | 追問回覆使用前一輪的待辦資訊，並說明建議理由 |

如果回覆遺漏了某項任務或改變了完成狀態，可以指出差異，請 VikingBot 根據原始清單修訂。

## 常見問題

| 現象 | 處理方法 |
| --- | --- |
| 安裝後找不到 `openviking-server` 或 `ov` | 重新開啟終端；仍不可用時，按 uv 或 npm 的安裝說明檢查命令路徑 |
| 提示埠已被佔用 | 確認是否已有本機服務；需要啟用 Bot 時，在原服務終端停止後再帶 `--with-bot` 啟動 |
| `ov health` 連線失敗 | 在 `ov config` 中確認當前連線地址，並檢查服務終端是否仍在執行 |
| Bot 健康檢查返回 `503` | 確認啟動時啟用了 `--with-bot`，並檢視服務日誌中的 Bot 啟動資訊 |
| 健康檢查成功，但模型呼叫失敗 | 根據錯誤資訊檢查模型名、端點、憑據和套餐支援情況 |
| 追問沒有沿用清單 | 確認兩次命令使用相同的 `--session` 和 CLI 連線身份，並確認第一輪已返回完整回覆 |

## 繼續使用

連線和對話正常後，可以讓 VikingBot 使用 OpenViking 中的上下文完成任務：

| 目標 | 下一步 |
| --- | --- |
| 根據專案資料回答，並核對來源 | [資料檢索](08-resources.md) |
| 在新會話中複用背景和偏好 | [記憶使用](09-memory.md) |
| 按固定工作方法處理不同輸入 | [技能使用](10-skills.md) |

接入飛書等聊天平臺、獨立除錯或配置模型時，可檢視 [VikingBot 指南](../guides/17-vikingbot.md)；在程式中傳送訊息可檢視 [Bot API](../api/24-vikingbot.md)。VikingBot Gateway 承接 Bot 訊息和聊天渠道；為相容客戶端提供模型請求入口的能力見 [OpenViking 閘道器](12-gateway.md)。

## 結束體驗

保留會話名稱，便於之後繼續討論。本機服務可在執行終端按 Ctrl+C 停止，停止後 CLI 對話入口也會隨之關閉。需要清理測試會話時，可在 Studio 中確認對應會話後刪除。
