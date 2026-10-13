# 上下文提取

資源匯入依次經過解析、目標路徑確定、內容寫入、語義生成和向量化。記憶和技能有各自的入口，也會使用語義處理和向量索引。

## 概覽

<IngestionPipelineDiagram />

解析與目錄語義生成分開處理。具體解析器可能呼叫模型或外部解析服務，因此不能把解析階段視為一律不使用 LLM。匯入介面通常先返回任務 ID；需要立即檢索時，應先確認該任務完成，見[任務管理](../api/17-tasks.md)。

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
| 圖片 | ImageParser | .png, .jpg 等 | 已支援；處理依賴媒體配置 |
| 影片 | VideoParser | .mp4, .avi, .mov, .mkv, .webm, .flv, .wmv, .ts（僅 MPEG-TS 內容） | 已支援；處理依賴媒體配置 |
| 音訊 | AudioParser | .mp3, .wav, .ogg, .flac, .aac, .m4a, .opus, .ac3 | 已支援；處理依賴媒體配置 |

### 解析產物

內部 `registry.parse()` 是非同步介面，返回 `ParseResult`。解析產物可以存放在本地臨時目錄或 AGFS；`temp_dir_path` 不一定是 Viking URI，`artifact_ref` 用來標識其儲存後端。這些是服務端實現細節，客戶端應使用資源匯入 API。

| 欄位 | 含義 |
| --- | --- |
| `root` | 解析後的資源樹根節點 |
| `temp_dir_path` | 臨時產物位置 |
| `artifact_ref` | 產物後端及根路徑 |
| `source_format` / `parser_name` | 源格式和解析器名稱 |
| `parse_time` | 解析耗時（秒） |
| `meta` / `warnings` | 後設資料及解析警告 |

### 文件分節

Markdown 解析器按標題和大小組織章節，合併較短小節，拆分過長內容。預設 `max_section_size` 為 2048 tokens，`max_section_chars` 為 6000 字元。配置還定義了 `section_size_flexibility=0.3`，但當前 Markdown 分節程式碼未使用該值。過長的單個表格行可以保持完整。這些值是分節目標，不能當作每個輸出檔案的絕對上限。

不同解析器和 `parse_mode` 的行為不同。需要保持單檔案時，可在支援的匯入中使用 `parse_mode="no_split"`，詳見[資源管理](../api/02-resources.md)。

## TreeBuilder（樹構建器）

`TreeBuilder.finalize_from_temp()` 檢查解析產物並確定最終 URI，返回包含根節點和臨時位置的 `BuildingTree`。它本身不復制檔案、不清理產物，也不提交語義任務。

### 匯入中的後續步驟

1. 根據解析產物、`to` 或 `parent` 確定目標 URI，並檢查目標路徑。
2. 匯入處理器將內容寫入最終儲存，處理資源鎖和已有內容更新。
3. 提交後續語義處理和向量化，按產物所屬後端清理臨時資料。

預設資源根目錄是 `viking://resources`。個人資源應顯式指定 `viking://~/resources/...`；`viking://user` 是使用者空間容器，不能當作自己的資源根。

## SemanticQueue（語義佇列）

SemanticQueue 非同步處理 L0/L1 生成和向量化。

### 訊息結構

下面列出部分內部訊息欄位，不是客戶端提交格式：

| 欄位 | 含義 |
| --- | --- |
| `id` | 訊息 UUID |
| `uri` | 待處理目錄 |
| `context_type` | resource、memory、skill 或 session |
| `status` | 佇列處理狀態 |
| `recursive` | 是否處理子目錄 |
| `propagate_to_parent` | 完成後是否允許安排父目錄重新整理 |

### 處理流程（自底向上）

```
葉子目錄 → 父目錄 → 根目錄
```

### 單目錄處理步驟

1. **併發生成檔案摘要**：併發上限由 `vlm.max_concurrent` 控制
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
| `vlm.max_concurrent` | 32 | 語義處理併發上限，傳入 `SemanticProcessor.max_concurrent_llm` |
| `max_images_per_call` | 10 | `VLMProcessor` 構造引數：單次最大圖片數，非 `ov.conf` 欄位 |
| `max_sections_per_call` | 20 | `VLMProcessor` 構造引數：單次最大章節數，非 `ov.conf` 欄位 |
| `semantic.overview_sample_limit` | 32 | 單個目錄摘要使用的直接子項樣本上限 |

## 程式碼骨架提取

對於程式碼檔案，OpenViking 使用固定的程式碼骨架提取路線。該路線內建在程式碼摘要流程中，不再通過逐語言解析引數選擇或調節。

### 程式碼骨架內容

骨架可包含 import、類、方法、函式及其他語言級符號。具體輸出取決於該語言維護中的 query 或通用解析結果，但提取路線本身是固定的。

### 提取路線

程式碼骨架提取按以下固定順序執行：

1. 語言存在維護中的 `tags.scm` 時，優先使用 tags query。
2. 不存在對應的 `tags.scm` 時，使用 `tree-sitter-language-pack.process()`。
3. 兩種提取方式都無可用結果時，才將 `semantic.code_summary` 作為兜底處理。

第 1、2 步需要 `tree-sitter-language-pack` 中對應語言的解析器，該解析器會在首次使用時從 GitHub 下載。當解析器未快取且無法下載時（例如處於防火牆之後），OpenViking 改用隨 pip 依賴安裝的語法包：Python、JavaScript、TypeScript/TSX、Java、C/C++、Rust、Go、C#、PHP 和 Lua，此時骨架會列出每個定義所在的原始碼行。其他語言則使用 `semantic.code_summary` 兜底。

manifest 查詢與下載共用 15 秒超時。首次失敗後，當前程序不再嘗試下載，只使用已快取的解析器，因此靜默丟包的防火牆最多隻會拖慢一個檔案。

長短程式碼檔案都遵循同一路由。

## 三種上下文提取

### 流程對比

| 環節 | Resource | Memory | Skill |
|------|----------|--------|-------|
| **入口** | 資源解析器 | 會話提取、記憶更新 | 技能匯入 |
| **基礎 URI** | `viking://resources` | `viking://~/memories` | `viking://~/skills` |
| **SemanticMsg type** | resource | memory | skill |

以下示例使用已配置的同步 Python SDK 客戶端 `client`。

### 資源提取

```python
# 新增資源
client.add_resource(
    path="/path/to/doc.pdf",
    options={"reason": "API 文件"},
)

# 流程: Parser → TreeBuilder(scope=resources) → SemanticQueue
```

### 技能提取

```python
# 新增技能
client.add_skill(
    data={
        "name": "search-web",
        "content": "# search-web\n...",
    },
)

# 流程: 直接寫入 viking://~/skills/{name}/ → SemanticQueue
```

### 記憶提取

```python
# 記憶從會話自動提取
client.commit_session(session_id)

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
