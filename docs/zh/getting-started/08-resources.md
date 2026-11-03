<a id="資源檢索"></a>

# 資料檢索

專案說明、會議記錄和反饋流程往往分散在多份文件中。將這些資料匯入 OpenViking 後，可以按問題的含義檢索相關內容，再讓 Agent 讀取原文，綜合回答並標註來源。

本節使用四份虛構的“燈塔專案”資料，帶你完成 **匯入資料 → 檢索 → 讀取原文 → 生成回答 → 核對來源**。你會分別檢視只需一份資料就能回答、需要綜合多份資料，以及資料尚未給出答案的三類問題。

## 準備環境

開始前，請準備以下環境：

- **OpenViking 服務和 CLI**：按照[快速開始](02-quickstart.md)完成連線配置，當前帳號需要具備目標目錄的匯入和讀取許可權。
- **VikingBot**：本節通過 `ov chat` 生成回答。請確認服務已啟用 VikingBot，並完成模型配置，具體方法見 [VikingBot](11-vikingbot.md)。CLI 和 VikingBot 應連線同一服務，並能訪問同一份資料。
- **模型配置**：資料處理、語義檢索和生成回答會使用已配置的模型，併產生相應的模型呼叫費用。

如果使用自己的 Agent，可以按[快速開始中的接入方式](02-quickstart.md#讓-agent-生成回答)連線資料服務，再使用下文的問題和核對標準。

## 準備資料

下載[燈塔專案資料包](/quickstart/lighthouse-zh-v1.zip)，在終端中進入下載檔案所在的目錄，再解壓：

```bash
unzip lighthouse-zh-v1.zip
```

解壓後得到 `lighthouse-zh/` 目錄，其中包含以下檔案：

| 檔案 | 內容 |
| --- | --- |
| `project.md` | 試點的網路條件、離線安裝包和本地儲存準備 |
| `feedback.md` | 反饋匯出時間、責任人和交付方式 |
| `meeting.md` | 反饋登記模板、匯出演練和待確認事項 |
| `limits.md` | 資料覆蓋範圍及尚未提供的資訊 |

## 匯入資料

將整個目錄匯入獨立的演示路徑。`--wait` 會等待資料處理完成，便於後續檢索。再次體驗時，可將 `onboarding-zh-v1` 換成新的目錄名，並同步修改後續命令中的 URI。

```bash
ov add-resource ./lighthouse-zh --to viking://resources/onboarding-zh-v1 --wait
```

處理成功後，檢視匯入結果：

```bash
ov tree viking://resources/onboarding-zh-v1
```

這組 Markdown 檔案處理後會分別放入同名目錄。確認目錄中包含以下檔案，再繼續檢索：

```text
viking://resources/onboarding-zh-v1/
├── project/project.md
├── feedback/feedback.md
├── meeting/meeting.md
└── limits/limits.md
```

如果等待超時，可用返回的任務 ID 執行 `ov task status <task_id>` 檢視進度。任務完成後繼續；任務失敗時，根據錯誤資訊檢查模型或連線配置。任務狀態說明見[任務管理](../api/17-tasks.md)。

<a id="檢索與回答"></a>

## 檢索資料

先提出一個需要綜合專案說明和會議記錄的問題，將檢索範圍限定在剛才匯入的目錄：

```bash
ov find "燈塔專案怎樣收集反饋，開始試點前要準備什麼？" --uri viking://resources/onboarding-zh-v1
```

檢索結果會列出匹配內容及其 URI。檢視命中內容是否涉及反饋收集和試點準備，再讀取相關原文。`ov find` 用於找到相關資料，下一步的原文讀取用於確認具體依據。

## 讀取原文

根據檢索結果中的 URI 開啟來原始檔。這組樣例中，與問題相關的檔案包括專案說明、會議記錄和反饋流程：

```bash
ov read viking://resources/onboarding-zh-v1/project/project.md
ov read viking://resources/onboarding-zh-v1/meeting/meeting.md
ov read viking://resources/onboarding-zh-v1/feedback/feedback.md
```

閱讀時可以留意：安裝包和本地目錄寫在專案說明中，登記模板和匯出演練寫在會議記錄中。要回答完整的試點準備要求，需要結合這兩份資料。

## 生成回答

把檢索、讀取和回答交給 VikingBot。在新會話中提出下面三個問題，並要求它為結論提供來源、明確標註未知資訊。重複體驗時，可以將會話名換成新的名稱。

```bash
ov chat --session lighthouse-resources-v1 -m "請只使用 viking://resources/onboarding-zh-v1 的資料，先進行語義檢索，再讀取相關原文，依次回答：反饋由誰在什麼時候匯出？試點開始前要準備什麼？試點何時結束、預算多少？每項結論列出完整來源 URI，資料未說明的內容請標為尚未確定。"
```

回答應包含反饋匯出安排、試點準備事項和待確認資訊，併為相關結論附上完整的 `viking://` 來源 URI。

## 核對來源

使用 `ov read` 開啟回答引用的檔案，逐項核對下表。回答措辭可以不同，事實和來源應與原文一致。

| 問題型別 | 問題 | 預期事實 | 來源 |
| --- | --- | --- | --- |
| 單份資料 | 誰在什麼時候匯出反饋？ | 試點管理員每週五匯出，並交給專案負責人 | `feedback/feedback.md` |
| 多份資料 | 試點開始前要準備什麼？ | 離線安裝包、本地儲存目錄、反饋登記模板、一次離線匯出演練 | `project/project.md`、`meeting/meeting.md` |
| 尚無答案 | 試點何時結束、預算多少？ | 兩項均尚未確定 | `meeting/meeting.md` |

結合 `ov chat` 的工具呼叫輸出或 Bot 日誌，確認 Agent 檢索了相關資料、讀取了來原始檔，並在回答中使用了這些內容。對於多份資料的問題，檢查回答是否遺漏其中一份的要求；對於尚未確定的事項，檢查是否保留了原文中的未知狀態。

## 常見問題

| 現象 | 處理方法 |
| --- | --- |
| 匯入目錄中缺少檔案 | 檢查解壓目錄是否包含四份資料，並檢視匯入結果和任務錯誤 |
| 檢索沒有相關結果 | 確認處理已完成、查詢 URI 與匯入目錄一致，再嘗試用更具體的問題檢索 |
| CLI 可以讀取，Agent 無法訪問 | 核對兩者連線的服務、帳號和目錄訪問許可權 |
| 檢索已命中，但回答遺漏內容 | 檢視 Agent 實際讀取的檔案，請它補讀相關來源並完善回答 |
| 回答給出具體結束日期或預算 | 對照會議記錄，請 Agent 將缺少依據的結論修正為“尚未確定” |

## 換成自己的資料

選擇一組你熟悉的專案資料，分別準備單份資料、多份資料和資料未覆蓋的問題，按同樣的流程檢索與核對。可以使用[效果評估](06-evaluate.md)中的記錄表，比較檢索結果、原文讀取和回答質量。支援的格式、匯入選項和增量處理方式見[資料管理](../api/02-resources.md)。

樣例目錄還可用於後續的[上下文編譯](13-compile.md)和[匯入匯出](15-transfer.md)。如需清理，可在 Studio 中確認目錄 URI 後刪除該演示目錄。
