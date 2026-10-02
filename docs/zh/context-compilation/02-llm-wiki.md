# 示例：LLM Wiki

把一批異構來源編譯成一套 Karpathy 風格、有出處、互相連結的 **LLM Wiki**：每一頁有明確的檢索目的，開頭一句話直給結論，術語統一，關係顯式，證據緊貼結論，並由一個 `index.md` 做導航入口。

這套 Skill 會按頁面的檢索目的挑選最合適的頁面型別：

| 頁面型別 | 用於 |
|---------|------|
| `entity` | 有穩定身份的具名事物（人、組織、產品、專案、系統、資料集、標準、事件……） |
| `concept` | 可複用的思想、機制、模式、協議、心智模型 |
| `method` | 有前置條件、有序步驟、可驗證結果的可複用流程 |
| `comparison` | 在明確維度上對兩個及以上物件做並排評估 |
| `analysis` | 圍繞一個問題的跨來源結論 |
| `summary` | 單一來源的忠實數字化摘要（僅當 `--instruction` 明確要求時才生成） |

預設以 `entity` 和 `concept` 為主，其餘型別只在滿足各自的嚴格判定時才提升。產物是一個**知識庫**，不是逐文件的摘要拼盤。

Skill 原始碼：[examples/compile/ov-compile-skills/llm-wiki](https://github.com/volcengine/OpenViking/tree/main/examples/compile/ov-compile-skills/llm-wiki) · 視覺化指令碼：[examples/compile/graph-show/llm-wiki](https://github.com/volcengine/OpenViking/tree/main/examples/compile/graph-show/llm-wiki)

## 第一步：準備來源

如果材料還沒進 Business Data Platform，先匯入。目錄型來源用 `ov add-resource`，單檔案可以用 `ov write`：

```bash
# 匯入一個目錄作為來源
ov add-resource ./my-research --to viking://resources/research

# 或者寫入單個檔案
ov mkdir viking://resources/research
ov write viking://resources/research/notes.md \
  --from-file ./notes.md --mode create
```

確認來源已就位：

```bash
ov ls -r viking://resources/research
```

## 第二步：添加 Skill

把 LLM Wiki 的 Skill 裝進服務。預設落到你的使用者私有 skills 名稱空間；想讓團隊共用就用 `-p viking://agent/skills`：

```bash
ov add-skill examples/compile/ov-compile-skills/llm-wiki
```

檢視裝好的 Skill URI：

```bash
ov skills list
# → viking://agent/skills/llm-wiki  （或 viking://user/<你>/skills/llm-wiki）
```

## 第三步：執行編譯

```bash
ov compile \
  --from viking://resources/research \
  --to viking://resources/research-wiki \
  --skill viking://agent/skills/llm-wiki \
  --instruction "面向團隊檢索整理成 Wiki，保留每條結論的出處"
```

- `--from` 可以重複或用逗號分隔，一次傳多個來源。
- `--to` 目錄不存在時會自動建立。
- 想要機器可讀結果加 `-o json`；命令會立即返回 `task_id`，用它查詢或取消任務：

```bash
ov task status cmp_01abc      # 檢視進度與最終結果
ov task cancel cmp_01abc      # 協作式取消
```

## 第四步：看看產物

編譯完成後目標目錄裡就是一套 Markdown 知識庫。先看導航頁，再按需鑽進去：

```bash
ov tree viking://resources/research-wiki
ov read viking://resources/research-wiki/index.md
```

典型結構（頁面型別對應目錄）：

```text
research-wiki/
├── index.md            # 導航入口，型別 index
├── entity/
│   └── <標題>.md
├── concept/
│   └── <標題>.md
├── method/…  comparison/…  analysis/…
```

## 第五步：視覺化成互動式圖譜

`wiki_graph.py` 會**直接連線 Business Data Platform 服務**讀取 Wiki 頁面（不需要先下載到本地），把頁面按型別著色、按連結連邊，生成一個獨立的互動式 HTML：

```bash
python examples/compile/graph-show/llm-wiki/wiki_graph.py \
  viking://resources/research-wiki \
  -o research-wiki-graph.html \
  --title "研究知識庫"
```

用瀏覽器開啟 `research-wiki-graph.html` 即可。節點是頁面（按 `entity`/`concept`/`method`… 分色），邊是頁面之間的連結，點節點能看正文。

連線配置的解析順序和 `ov` 一致：命令列引數 → `OPENVIKING_*` 環境變數 → `~/.openviking/ovcli.conf`。遠端服務顯式傳參：

```bash
python examples/compile/graph-show/llm-wiki/wiki_graph.py \
  viking://resources/research-wiki \
  --url https://openviking.example.com \
  --api-key "$OPENVIKING_API_KEY" \
  -o research-wiki-graph.html --title "研究知識庫"
```

一次傳多個 Wiki，可以把它們畫在同一張圖裡對比：

```bash
python examples/compile/graph-show/llm-wiki/wiki_graph.py \
  viking://resources/wiki-a viking://resources/wiki-b \
  -o combined.html --title "兩個知識庫對照"
```

## 相關文件

- [上下文編譯概覽](./01-overview.md)
- [Knowledge Graph 示例](./03-knowledge-graph.md)
- [Agent Runtime API](../api/23-agent-runtime.md)
