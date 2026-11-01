# 上下文編譯

將燈塔專案的四份資料整理成一份小型 Wiki，開啟正文核對來源和未知事項。

## 認識 LLM Wiki

LLM Wiki 利用大模型，將分散在文件、會議記錄和反饋中的資訊，整理成按主題組織、相互連結的 Markdown 知識庫。同一專案或概念的相關內容可以彙集到一頁，通過導航頁瀏覽，並保留指向原始資料的引用，方便讀者和 Agent 查閱、核對與複用。

例如，燈塔專案的目標、反饋流程和準備事項分佈在四份資料中。編譯後，一篇專案頁面就可以串起這些資訊，標明尚未確定的日期和預算，併為關鍵事實附上來源。後續瞭解專案時，可以先閱讀這篇頁面，再沿引用檢視細節。

OpenViking 通過 LLM Wiki Skill 定義整理方式，由 Compile Runtime 讀取來源並生成頁面。生成的 Wiki 可繼續用於閱讀和檢索；關鍵結論仍需結合原始資料核對。下面用燈塔資料完成一次編譯。

## 準備來源與技能

本頁需要已配置 Compile Runtime 的服務。本機預設使用已安裝 `openviking[bot]` 並以 `--with-bot` 啟動的 VikingBot，模型和連線配置見[快速開始](02-quickstart.md)。

先完成[資料檢索](08-resources.md#準備資料)的資料匯入，確認 `viking://resources/onboarding-zh-v1` 可讀取。下載 [Wiki Skill v1](/quickstart/llm-wiki-v1.zip)，安裝到有寫許可權的共享技能目錄：

```bash
ov add-skill ./llm-wiki-v1.zip -p viking://agent/skills --wait
ov read viking://agent/skills/llm-wiki/SKILL.md
```

這個樣例包包含專案自帶的 LLM Wiki Skill。編譯將呼叫模型並在下面的新目錄中寫入產物；重複體驗時使用新的目標目錄名。

## 提交編譯

```bash
ov compile --from viking://resources/onboarding-zh-v1 \
  --to viking://resources/onboarding-wiki-v1 \
  --skill viking://agent/skills/llm-wiki \
  --instruction "請用中文生成一個 index.md 和一篇 entity/lighthouse.md。正文圍繞隔離網路中的反饋試點，綜合專案、反饋和會議資料，保留完整來源 viking:// URI，明確未知日期。僅在目標目錄寫入。"
```

記錄返回的 `cmp_...` 任務 ID，查詢進度：

```bash
ov task status <cmp_task_id>
```

每隔 5 秒檢視一次，先觀察最多 5 分鐘。狀態為 `completed` 後讀取產物；仍在執行時可稍後再查，或用 `ov task cancel <cmp_task_id>` 請求取消。失敗時檢視任務錯誤和 Compile Runtime 配置。

編譯完成後，目標目錄中應包含導航頁和專案正文。你可以參考 [Wiki 正文示例](/quickstart/wiki-output-zh-v1.txt)，瞭解內容組織和來源引用方式，再按下文核對生成結果。

## 開啟正文

```bash
ov tree viking://resources/onboarding-wiki-v1
ov read viking://resources/onboarding-wiki-v1/index.md
ov read viking://resources/onboarding-wiki-v1/entity/lighthouse.md
```

如果實際檔名與指令不同，可從 `tree` 和導航頁找到正文 URI。核對以下內容：隔離網路條件、離線安裝包與本地目錄、每週五匯出反饋、模板與演練準備，以及尚未確定的日期和預算。開啟正文引用的來源，逐項確認依據。

| 情況 | 檢查方向 |
| --- | --- |
| Runtime 不可用 | 服務端是否安裝 Bot 依賴並啟用編譯執行端 |
| 找不到來源或 Skill | URI、讀許可權與前置處理結果 |
| 正文缺少依據 | 檢查實際讀取記錄和來源引用，補充編譯指令後使用新目標重試 |

完成標誌是一篇可閱讀、可導航且關鍵事實有來源支援的正文。檔案結構、頁面型別和視覺化見 [LLM Wiki 示例](../context-compilation/02-llm-wiki.md)。清理時確認演示目標目錄，保留需要的產物後在 Studio 中刪除。
