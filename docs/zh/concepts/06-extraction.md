# 上下文提取

Business Data Platform 採用三層非同步架構處理文件解析和上下文提取。

## 概覽

```
輸入檔案 → Parser → TreeBuilder → SemanticQueue → 向量庫
           ↓           ↓              ↓
        解析轉換    檔案移動     L0/L1 生成
        (無 LLM)   入隊語義      (LLM 非同步)
```

**設計原則**：解析與語義分離，Parser 不呼叫 LLM，語義生成非同步進行。

## Parser（解析器）

Parser 負責文件格式轉換和結構化，在臨時目錄建立檔案結構。

### 支持格式

| 格式 | 解析器 | 副檔名 | 支援情況 |
|------|--------|--------|------|
| Markdown | MarkdownParser | .md, .markdown | 已支持 |
| 純文本 | TextParser | .txt | 已支援 |
| PDF | PDFParser | .pdf | 已支持 |
| HTML | HTMLParser | .html, .htm | 已支持 |
| 程式碼 | CodeRepositoryParser | github 程式碼倉庫等 | 遵循 `.gitignore` 並忽略常見非程式碼目錄 |
| 圖片 | ImageParser | .png, .jpg 等 |  |
| 影片 | VideoParser | .mp4, .avi, .mov, .mkv, .webm, .flv, .wmv |  |
| 音訊 | AudioParser | .mp3, .wav, .ogg, .flac, .aac, .m4a, .opus |  |

### 核心流程 (以文件為例)

```python
# 1. 解析文件
parse_result = registry.parse("/path/to/doc.md")

# 2. 返回臨時目錄 URI
parse_result.temp_dir_path  # viking://temp/abc123
```

### 智能分割

```
如果 document_tokens <= 1024:
    → 儲存為單檔案
否則:
    → 按標題分割
    → 小節 < 512 tokens → 合併
    → 大節 > 1024 tokens → 建立子目錄
```

### 返回結果

```python
ParseResult(
    temp_dir_path: str,    # 臨時目錄 URI
    source_format: str,    # pdf/markdown/html
    parser_name: str,      # 解析器名稱
    parse_time: float,     # 耗時（秒）
    meta: Dict,            # 後設資料
)
```

## TreeBuilder（樹構建器）

TreeBuilder 負責將臨時目錄移動到 AGFS，併入隊語義處理。

### 核心流程

```python
building_tree = tree_builder.finalize_from_temp(
    temp_dir_path="viking://temp/abc123",
    scope="resources",  # resources/user
)
```

### 5 階段處理

1. **查詢文件根目錄**：確保臨時目錄下恰好 1 個子目錄
2. **確定目標 URI**：根據 scope 對映基礎 URI
3. **遞迴移動目錄樹**：複製所有檔案到 AGFS
4. **清理臨時目錄**：刪除臨時檔案
5. **入隊語義生成**：提交 SemanticMsg 到佇列

### URI 映射

| scope | 基礎 URI |
|-------|----------|
| resources | `viking://resources` |
| user | `viking://user` |

## SemanticQueue（語義佇列）

SemanticQueue 非同步處理 L0/L1 生成和向量化。

### 訊息結構

```python
SemanticMsg(
    id: str,           # UUID
    uri: str,          # 目錄 URI
    context_type: str, # resource/memory/skill
    status: str,       # pending/processing/completed
)
```

### 處理流程（自底向上）

```
葉子目錄 → 父目錄 → 根目錄
```

### 單目錄處理步驟

1. **併發生成檔案摘要**：限制併發數 10
2. **收集子目錄摘要**：讀取已生成的 .abstract.md
3. **生成 .overview.md**：LLM 生成 L1 概覽
4. **提取 .abstract.md**：從 overview 提取 L0 摘要
5. **寫入檔案**：以 OKF Markdown 儲存正文和受保護後設資料
6. **向量化**：建立 Context 併入隊 EmbeddingQueue

L0/L1 是目錄級 sidecar，不是 per-file sidecar。生成父目錄摘要時只使用子目錄 L0 的正文，OKF frontmatter 不進入 prompt。Embedding 使用正文和白名單中的 `directory`；`source`、`generated_by`、`freshness` 不進入向量輸入。

### Freshness、取樣與父級重新整理

每次生成都會記錄直接子項覆蓋情況，超過 `semantic.overview_sample_limit`（預設 32）時使用穩定取樣。resource/skill 的父級重新整理取決於子目錄 L0 正文變化和 freshness 閾值，L0 正文不變時不向上傳播。`pending_child_changes` 統計等待重新整理的變化事件，同一子項重複變化也會分別計數。閾值、手動重新整理和延後更新的規則見[上下文層級](03-context-layers.md)。

### 處理限制

| 引數 | 預設值 | 說明 |
|------|--------|------|
| `max_concurrent_llm` | 10 | 併發 LLM 呼叫數 |
| `max_images_per_call` | 10 | 單次 VLM 最大圖片數 |
| `max_sections_per_call` | 20 | 單次 VLM 最大章節數 |
| `overview_sample_limit` | 32 | 單個目錄摘要使用的直接子項樣本上限 |

## 程式碼骨架提取

對於程式碼檔案，Business Data Platform 使用固定的程式碼骨架提取路線。該路線內建在程式碼摘要流程中，不再通過逐語言解析引數選擇或調節。

### 程式碼骨架內容

骨架可包含 import、類、方法、函式及其他語言級符號。具體輸出取決於該語言維護中的 query 或通用解析結果，但提取路線本身是固定的。

### 提取路線

程式碼骨架提取按以下固定順序執行：

1. 語言存在維護中的 `tags.scm` 時，優先使用 tags query。
2. 不存在對應的 `tags.scm` 時，使用 `tree-sitter-language-pack.process()`。
3. 兩種提取方式都無可用結果時，才將 `semantic.code_summary` 作為兜底處理。

第 1、2 步需要 `tree-sitter-language-pack` 中對應語言的解析器，該解析器會在首次使用時從 GitHub 下載。當解析器未快取且無法下載時（例如處於防火牆之後），Business Data Platform 改用隨 pip 依賴安裝的語法包：Python、JavaScript、TypeScript/TSX、Java、C/C++、Rust、Go、C#、PHP 和 Lua，此時骨架會列出每個定義所在的原始碼行。其他語言則使用 `semantic.code_summary` 兜底。

manifest 查詢與下載共用 15 秒超時。首次失敗後，當前程序不再嘗試下載，只使用已快取的解析器，因此靜默丟包的防火牆最多隻會拖慢一個檔案。

長短程式碼檔案都遵循同一路由。

## 三種上下文提取

### 流程對比

| 環節 | Resource | Memory | Skill |
|------|----------|--------|-------|
| **Parser** | 通用流程 | 通用流程 | 通用流程 |
| **基礎 URI** | `viking://resources` | `viking://~/memories` | `viking://~/skills` |
| **TreeBuilder scope** | resources | user | user |
| **SemanticMsg type** | resource | memory | skill |

### 資源提取

```python
# 新增資源
await client.add_resource(
    path="/path/to/doc.pdf",
    options={"reason": "API 文件"},
)

# 流程: Parser → TreeBuilder(scope=resources) → SemanticQueue
```

### 技能提取

```python
# 添加技能
await client.add_skill(
    data={
        "name": "search-web",
        "content": "# search-web\\n...",
    },
)

# 流程: 直接寫入 viking://~/skills/{name}/ → SemanticQueue
```

### 記憶提取

```python
# 記憶從會話自動提取
await session.commit()

# 流程: SessionCompressorV3 → ExtractLoop → MemoryUpdater → SemanticQueue
```

V3 只提供一個提取入口。它先提取啟用的使用者記憶 schema（包括 `cases`）；
只有本次提取實際產生至少一個 case，才會繼續訓練 trajectory、experience，
以及可選的可執行 session skill。沒有 case 的會話不會生成這些執行派生記憶。

## 相關文件

- [架構概述](./01-architecture.md) - 系統整體架構
- [上下文層級](./03-context-layers.md) - L0/L1/L2 模型
- [儲存架構](./05-storage.md) - AGFS 和向量庫
- [會話管理](./08-session.md) - 記憶提取詳解
