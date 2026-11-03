# 示例：Knowledge Graph

將來源中的實體及其關係整理成知識圖譜：實體帶語義型別，關係是帶型別的有向邊，每條陳述和邊都保留出處。輸出包含實體檔案和關係表：

```text
entities/
  <entity-id>.md      # 每個節點一個檔案，frontmatter 裡有 type/id/title/entity_type/description/sources
relations.jsonl       # 每行一條有向邊
```

每條邊是一行緊湊 JSON，可讀成 `<from> <relation> <to>` 這樣一句話：

```json
{"from":"孫悟空","relation":"member_of","label":"屬於","to":"取經隊伍","evidence":["viking://resources/source.md"]}
```

`relation` 是穩定、語言無關的機器謂詞（`member_of`、`leads`、`located_in`……），`label` 是對應的本地化顯示名（`屬於`、`率領`、`位於`……），`entity_type` 用於視覺化時的節點顏色、形狀和過濾。圖譜可以增量重新整理：已有節點和邊會被保留、合併證據，新知識追加進來。

Skill 原始碼：[examples/compile/ov-compile-skills/knowledge-graph](https://github.com/yenchang265-afk/OpenViking/tree/main/examples/compile/ov-compile-skills/knowledge-graph) · 視覺化指令碼：[examples/compile/graph-show/knowledge-graph](https://github.com/volcengine/OpenViking/tree/main/examples/compile/graph-show/knowledge-graph)

先確認[前置條件](01-overview.md#前置條件)，並在 OpenViking 倉庫根目錄執行以下命令。來源目錄需替換為自己的資料目錄。

## 第一步：準備來源

```bash
ov add-resource ./journal-to-the-west --to viking://resources/journal --wait
ov ls -r viking://resources/journal
```

## 第二步：添加 Skill

```bash
ov add-skill examples/compile/ov-compile-skills/knowledge-graph -p viking://agent/skills --wait
ov skills list
# → viking://agent/skills/knowledge-graph
```

## 第三步：執行編譯

```bash
ov compile \
  --from viking://resources/journal \
  --to viking://resources/journal-kg \
  --skill viking://agent/skills/knowledge-graph \
  --instruction "抽取人物、地點、法寶及其關係，構建可遍歷的知識圖譜"
```

命令會立刻返回 `task_id`，之後：

```bash
ov task status cmp_01abc      # 檢視進度與最終結果
ov task cancel cmp_01abc      # 協作式取消
```

## 第四步：檢視產物

```bash
ov tree viking://resources/journal-kg
ov read viking://resources/journal-kg/relations.jsonl
ov read viking://resources/journal-kg/entities/孫悟空.md
```

## 第五步：視覺化成互動式圖譜

在 Studio 中，於檔案系統頁面開啟產物資料夾，並將標頭從 **內容** 切換為 **圖譜**，即可在瀏覽器中探索同一張圖：點選節點檢視詳細資訊（含關係與證據）、搜尋、按實體類型篩選，並逐跳擴大高亮的鄰居範圍。下方腳本則會產生一個獨立的 HTML 檔案。

與 LLM Wiki 的指令碼不同，`knowledge_graph.py` 讀取的是**本地目錄**（需要 `entities/` 和 `relations.jsonl` 都在本地）。所以先把產物拉到本地，再生成 HTML。

`ov get` 一次下載一個檔案。下面的指令碼只下載實體 Markdown 和關係表：

```bash
SRC="viking://resources/journal-kg"
DST="./journal-kg"
mkdir -p "$DST"
ov ls -r -s "$SRC" | while read -r uri; do
  # 只下載檔案（entities/*.md 和 relations.jsonl），跳過目錄
  case "$uri" in
    "$SRC"/entities/*.md|"$SRC"/relations.jsonl) ;;
    *) continue ;;
  esac
  rel="${uri#$SRC/}"
  mkdir -p "$DST/$(dirname "$rel")"
  ov get "$uri" "$DST/$rel"
done
```

> `ov get` 要求本地目標檔案尚不存在。重複下載時，將 `DST` 換為一個新目錄，保留上次結果。

確認本地目錄結構正確：

```bash
find ./journal-kg          # 應能看到 entities/*.md 和 relations.jsonl
```

生成交互式 HTML：

```bash
python examples/compile/graph-show/knowledge-graph/knowledge_graph.py \
  ./journal-kg \
  -o journal-kg.html \
  --title "西遊知識圖譜"
```

用瀏覽器開啟 `journal-kg.html`。指令碼會先做校驗——`relations.jsonl` 必須是合法 JSON、每個實體檔案都要有穩定的 `id` 和 `title`、每條邊的兩端都要能對上某個實體節點——校驗不通過會直接報錯並指出問題行，所以它同時也是產物質量的檢查器。節點按 `entity_type` 分色分形，邊顯示本地化 `label`，點節點能看到該實體的正文、別名和出處。

## 相關文件

- [上下文編譯概覽](./01-overview.md)
- [LLM Wiki 示例](./02-llm-wiki.md)
- [Agent Runtime API](../api/23-agent-runtime.md)
