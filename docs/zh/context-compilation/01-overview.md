# 上下文編譯概覽

`ov compile` 把散落在 OpenViking 裡的原始材料——文件、筆記、網頁、訪談記錄、研究資料、程式碼倉庫——**編譯**成結構化、可檢索、方便人和 Agent 反覆使用的知識產物。

## 它是怎麼工作的

你只需要提供三樣東西：

- **從哪裡來（`--from`）**：一個或多個來源目錄/檔案；
- **到哪裡去（`--to`）**：產物寫入的目標目錄；
- **用哪個 Skill（`--skill`）**：一份描述「要編譯成什麼樣」的說明書。

再加上一個可選的 **`--instruction`**：給這次編譯的補充指令，比如範圍、受眾、語言、側重點。Skill 定義了「編譯成什麼形態」，`--instruction` 則在此之上告訴 Agent「這一次具體要什麼」。

剩下的交給 OpenViking。Compile 依賴 [VikingBot](../concepts/15-vikingbot.md)：任務被接受後，VikingBot 會載入你指定的 Skill，以你的身份讀取來源，在一個獨立的 **Agent Loop** 裡自主地閱讀、歸納、組織、寫頁面——就像你僱了一個人，把一堆資料整理成一份乾淨的知識庫，然後把成品交回給你。整個過程是非同步的，你可以等它跑完，也可以拿到 `task_id` 之後去做別的事。

換句話說：**你負責給材料和目標，Agent 負責真正把知識整理出來。** 

## 一條命令跑起來

```bash
ov compile \
  --from viking://resources/research \
  --to viking://resources/research-wiki \
  --skill viking://agent/skills/llm-wiki \
  --instruction "把研究資料整理成便於團隊檢索的知識庫"
```

命令會立即返回一個 `cmp_...` 任務 ID，之後用 `ov task status <id>` 檢視進度、用 `ov task cancel <id>` 取消。完整的欄位說明、任務生命週期和 HTTP 介面見 [Agent Runtime API](../api/23-agent-runtime.md)。

## 換個 Skill，就換一種產物

Compile 本身不規定「編譯成什麼」——那由 Skill 決定。同一批來源，配不同的 Skill，就能得到形態完全不同的知識產物。下面是我們提供的示例 Skill，前兩個還各自配了一個視覺化指令碼，可以直接照著跑：

| Skill | 產物形態 | 適合 | 示例 |
|-------|---------|------|------|
| **LLM Wiki** | 一套互相連結的 Markdown 頁面（實體頁、概念頁、方法頁……）加一個導航 `index.md` | 需要人和 Agent 都能快速檢索、導航、複用的知識庫 | [LLM Wiki 示例](./02-llm-wiki.md) |
| **Knowledge Graph** | `entities/*.md` 節點 + 一個 `relations.jsonl` 關係表 | 需要按實體、型別、關係去遍歷的結構化知識圖譜 | [Knowledge Graph 示例](./03-knowledge-graph.md) |
| **日報** | 每個日期一頁 `<YYYY-MM-DD>.md` | 從對話、會話、訊息、任務記錄裡還原「每天真正做了什麼」 | [日報示例](./04-daily-report.md) |
| **知識蒸餾** | 按主題組織的高層次結論頁 | 從一個或多個知識庫裡提煉跨來源的發現、趨勢、變化 | [知識蒸餾示例](./05-knowledge-distillation.md) |

前兩個示例還給出了從**匯入來源 → 新增 Skill → 執行編譯 → 視覺化產物**的完整 `ov` 命令，照著做就能得到一張可互動的 HTML 圖。

這些 Skill 隨 OpenViking 一起發佈（`openviking/builtin_skills/compile`），預設會在伺服器啟動與建立帳戶時安裝到每個帳戶共享的 `viking://agent/skills`。同名的既有 Skill 不會被覆寫，管理員刪除的內建 Skill 也不會被重新安裝；將 `server.builtin_skills` 設為 `false` 即可關閉。在 Studio 的 Playground 上下文樹中，對資料夾按右鍵選擇 **使用 Skill 編譯 ▸ <Skill>**，即可開啟以該資料夾為來源的編譯表單；對 Skill 資料夾按右鍵則可選擇 **使用此 Skill 編譯**。

## 前置條件

- 一個正在執行、且啟用了 Bot（`--with-bot`）的 OpenViking 服務。預設端點是 `http://localhost:1933`；遠端使用需要 API Key，參見 [鑑權](../guides/04-authentication.md)。沒有服務先看 [快速開始](../getting-started/02-quickstart.md)。
- `ov` CLI 已配置好連線（`~/.openviking/ovcli.conf` 或 `OPENVIKING_*` 環境變數）。
- 視覺化指令碼需要 Python 3；LLM Wiki 的指令碼還會用到 `openviking` Python 包來直接讀取服務裡的 Wiki 頁面。

## 相關文件

- [VikingBot 概念](../concepts/15-vikingbot.md) — Compile 背後的執行體
- [Agent Runtime API](../api/23-agent-runtime.md) — 建立、查詢和取消 Compile 任務的完整參考
- [Skills API](../api/04-skills.md) — 如何管理和自定義 Skill
