# 上下文編譯概覽

`ov compile` 讀取 OpenViking 中的文件、筆記、網頁或會話記錄，按指定 Skill 整理成 Wiki、知識圖譜、日報等內容，並寫回 OpenViking。

## 它是怎麼工作的

使用已安裝 Skill 編譯時，需要指定：

- `--from`：一個或多個來源目錄或檔案。
- `--to`：輸出目錄。
- `--skill`：已安裝的 Skill URI，定義輸出內容和結構。

可選的 `--instruction` 用來補充本次任務的範圍、受眾、語言、側重點或日期。

編譯由 OpenViking 伺服器自身執行，與 `add_resource` 一樣作為持久佇列工作（見 [Agent Runtime API](../api/23-agent-runtime.md)）。它以請求使用者的身份讀取來源和 Skill，通過 plan / map / shuffle / reduce 流水線整理並寫入內容。任務非同步執行，返回 `task_id` 後可查詢進度和結果；被伺服器重啟中斷的任務會從頭重新執行。

## 一條命令跑起來

先按 [LLM Wiki 示例](02-llm-wiki.md) 匯入來源、安裝 Skill，再執行：

```bash
ov compile \
  --from viking://resources/research \
  --to viking://resources/research-wiki \
  --skill viking://agent/skills/llm-wiki \
  --instruction "把研究資料整理成便於團隊檢索的知識庫"
```

命令會立即返回一個 `cmp_...` 任務 ID，之後用 `ov task status <id>` 檢視進度、用 `ov task cancel <id>` 取消。完整的欄位說明、任務生命週期和 HTTP 介面見 [Agent Runtime API](../api/23-agent-runtime.md)。

## 使用 Web Studio

Studio 提供 `/compile` 列表、`/compile/new` 新建表單和 `/compile/tasks/<task_id>` 任務詳情頁。可以選擇並預覽 Skill、瀏覽來源目錄、提交多個來源、檢視或取消任務，以及開啟產物目錄。檔案系統終端也支援 `compile` 和 `task`，並可將引數帶入表單。

任務列表游標使用程序內金鑰簽名，並繫結呼叫者和篩選條件。服務重啟後舊遊標失效，重新整理列表即可重新開始。一個副本簽發的游標不能直接用於另一個副本。分頁掃描已儲存的任務記錄，不依賴索引，讀取成本仍隨保留的歷史數量增長。

重試 HTTP 提交時，複用相同的 `Idempotency-Key` 和請求引數；同一 Key 對應的引數變化時返回 `409`。提交恢復只在任務記錄保留期間有效：完成或取消的記錄在最後一次更新後保留 24 小時，失敗記錄保留 7 天。這不是永久提交歷史，也不保證跨例項 exactly-once。提交恢復見 [Agent Runtime](../api/23-agent-runtime.md)，任務操作見[任務管理](../api/17-tasks.md)。

## 換個 Skill，就換一種產物

Skill 決定輸出內容和結構。倉庫提供以下示例，其中 LLM Wiki 和 Knowledge Graph 還包含視覺化指令碼：

| Skill | 產物形態 | 適合 | 示例 |
|-------|---------|------|------|
| **LLM Wiki** | 一套互相連結的 Markdown 頁面（實體頁、概念頁、方法頁……）加一個導航 `index.md` | 需要人和 Agent 都能快速檢索、導航、複用的知識庫 | [LLM Wiki 示例](./02-llm-wiki.md) |
| **Knowledge Graph** | `entities/*.md` 節點 + 一個 `relations.jsonl` 關係表 | 需要按實體、型別、關係去遍歷的結構化知識圖譜 | [Knowledge Graph 示例](./03-knowledge-graph.md) |
| **日報** | 每個日期一頁 `<YYYY-MM-DD>.md` | 從對話、會話、訊息、任務記錄裡還原「每天真正做了什麼」 | [日報示例](./04-daily-report.md) |
| **知識蒸餾** | 按主題組織的高層次結論頁 | 從一個或多個知識庫裡提煉跨來源的發現、趨勢、變化 | [知識蒸餾示例](./05-knowledge-distillation.md) |

前兩個示例還給出了從**匯入來源 → 新增 Skill → 執行編譯 → 視覺化產物**的完整 `ov` 命令，照著做就能得到一張可互動的 HTML 圖。

這些 Skill 隨 OpenViking 一起發佈（`openviking/system_assets/compile/example-skills`），預設會在伺服器啟動與建立帳戶時安裝到每個帳戶共享的 `viking://agent/skills`。同名的既有 Skill 不會被覆寫，管理員刪除的內建 Skill 也不會被重新安裝；將 `server.builtin_skills` 設為 `false` 即可關閉。在 Studio 的檔案系統頁面中，對資料夾按右鍵選擇 **使用 Skill 編譯 ▸ &lt;Skill&gt;**，即可開啟以該資料夾為來源的編譯表單；對 Skill 資料夾按右鍵則可選擇 **使用此 Skill 編譯**。
## 不止生成新產物：整理已有記憶

除了用 Skill 把來源材料編譯成新的知識產物，`ov compile` 還有一種特殊模式——把 `--skill` 設為 `memory`，即可基於記憶框架而非 Skill 流水線，對已有的**記憶**目錄做就地整理（去重、合併、拆分、精簡）。詳見 [記憶整理](./06-memory-consolidation.md)。

## 前置條件

- 一個已配置 `vlm` 模型的 OpenViking 服務。`--skill memory` 模式不傳 `--from`。預設端點是 `http://localhost:1933`；遠端使用需要 API Key，參見 [鑑權](../guides/04-authentication.md)。沒有服務先看 [快速開始](../getting-started/02-quickstart.md)。
- `ov` CLI 已配置好連線（`~/.openviking/ovcli.conf`，或由 `OPENVIKING_CLI_CONFIG_FILE` 指定的檔案）。
- 示例中的 `examples/...` 是倉庫相對路徑。先下載 [OpenViking 倉庫](https://github.com/volcengine/OpenViking)，在倉庫根目錄執行命令。
- 視覺化指令碼需要 Python 3。[LLM Wiki 指令碼](https://github.com/volcengine/OpenViking/blob/main/examples/compile/graph-show/llm-wiki/wiki_graph.py)還需要 `openviking` Python 包。

## 相關文件

- [Agent Runtime API](../api/23-agent-runtime.md) — 建立、查詢和取消 Compile 任務的完整參考
- [Skills API](../api/04-skills.md) — 如何管理和自定義 Skill
