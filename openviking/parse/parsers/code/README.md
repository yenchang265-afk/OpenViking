# 程式碼解析方案 (Code Parser)

OpenViking 通過 **Code Parser** 模組實現對程式碼倉庫的整體解析與理解。與普通文件的拆解式處理不同，程式碼解析採用了基於目錄結構的整體對映策略，旨在保持程式碼專案的完整上下文。

## 概覽

| 特性 | 策略 | 說明 |
|------|------|------|
| **解析粒度** | 檔案級 | 不進行 Chunking 拆分，保持單檔案完整性 |
| **目錄對映** | 1:1 對映 | 本地目錄結構直接對映為 Viking URI 路徑 |
| **處理模式** | 非同步處理 | Parser 負責搬運，SemanticProcessor 負責理解 |
| **後設資料** | 自動提取 | 提取語言、依賴、符號定義等基礎資訊 |

## 核心設計思考

程式碼倉庫作為一種特殊的資源型別，具有以下顯著特徵，這些特徵直接決定了我們的技術方案：

1.  **檔案粒度適中**：大多數程式碼檔案（KB 級）都在大模型上下文視窗範圍內（<10k tokens），無需像長文件那樣進行物理切分。
2.  **結構即語義**：程式碼的目錄結構（Directory Structure）本身就蘊含了模組劃分、層級依賴等重要架構資訊，必須嚴格保留。
3.  **高頻迭代**：程式碼變動頻繁，系統需支援增量更新，避免重複索引未變動的檔案。
4.  **後設資料豐富**：程式碼中的註釋、DocString、Import 語句等包含了高密度的語義資訊。

## 上下文對映體系

我們將程式碼倉庫對映到 OpenViking 的標準分層描述體系中。

### 1. Viking URI 映射

假設使用者匯入了 `OpenViking` 倉庫：

```python
client.add_resource(
    "https://github.com/volcengine/OpenViking",
    to="viking://resources/github/volcengine/OpenViking"
)
```

系統將生成如下標準化的目錄樹結構，能夠完整體現深層級的檔案路徑：

```text
viking://resources/github/volcengine/OpenViking/
├── .abstract.md        # L0: 專案級摘要
├── .overview.md        # L1: 專案級概覽
├── docs/
│   ├── .abstract.md
│   ├── .overview.md
│   ├── zh/...
│   └── en/...
├── src/
│   ├── .abstract.md
│   ├── .overview.md
│   └── index/          # 深層目錄結構
│       ├── .abstract.md
│       ├── .overview.md
│       └── index/      # 更深層的子模組
│           ├── .abstract.md
│           ├── .overview.md
│           ├── index_engine.cpp    # L2: 具體程式碼檔案（C++）
│           └── ...
└── openviking/
    ├── .abstract.md
    ├── .overview.md
    └── ...
```

在這顆目錄樹中，每一層目錄都會有一個 `.abstract.md` 檔案和 `.overview.md` 檔案：
*   `.abstract.md`：目錄的摘要，介紹本目錄的功能和在專案中的作用。
*   `.overview.md`：目錄的概覽，介紹本目錄的檔案結構、關鍵實體的位置等。

### 2. 語義層級 (Context Layers)

*   **L0 (Abstract)**：目錄的簡短功能描述，用於快速檢索。
*   **L1 (Overview)**：目錄的詳細概覽，包含檔案結構分析、關鍵類/函式索引。
*   **L2 (Detail)**：原始程式碼檔案內容。對於程式碼檔案，我們**不進行拆分**，直接儲存完整內容。

## 資料處理原則

1. 本方案對於任意程式語言的程式碼倉庫均適用，不應該特殊處理任意程式語言的差異性，需要考慮策略足夠通用。
2. 對於程式碼倉庫中的文件，除了圖片以外，不要讓大模型處理文本以外的其他模態內容，如影片、音訊等。
   - **說明**：".md"、".txt"、".rst" 等純文本格式的文件檔案**會被處理**，因為它們屬於"文本內容"
   - **排除**：影片（.mp4, .mov, .avi 等）、音訊（.mp3, .wav, .m4a 等）等非文本格式**不會被處理**
3. 可以忽略程式碼倉庫中的隱藏檔案，如 .git 資料夾下面的內容，__pycache__ 資料夾下面的內容等；同時遵循 `.gitignore` 規則。
4. 對於程式碼倉庫中的符號連結，我們應當忽略並記錄其目標路徑，而不是直接解析符號連結。
5. 對於程式碼倉庫中的子目錄，我們應當遞迴地處理，確保所有包含程式碼的目錄，都被正確對映到 Viking URI 路徑。

## 技術實現方案

### 1. 倉庫識別與拉取

擴充 `URLTypeDetector` 以支援程式碼倉庫識別：

*   **識別邏輯**：檢測 URL 是否為 GitHub/GitLab 一級倉庫地址（如 `https://github.com/org/repo` 或 `*.git`）。
*   **拉取策略**：
    *   **Git Clone**：優先使用 `git clone --depth 1` 進行淺克隆，速度最快。
    *   **Zip Download**：作為降級方案，下載 `main.zip` 或 `master.zip`。
*   **過濾機制**：內建過濾規則，自動忽略 `.git`, `.idea`, `__pycache__`, `node_modules` 等非程式碼資源。

### 2. 解析流程 (CodeRepositoryParser)

解析器遵循 V5.0 的非同步處理架構：

1.  **物理搬運 (Parser Phase)**：
    *   將拉取到的程式碼倉庫（經過過濾）完整上傳到 `viking://temp/{uuid}/` 臨時目錄。
    *   在此階段**不進行**任何 LLM 呼叫，確保 `add_resource` 介面能快速返回。
    *   僅進行基礎的靜態分析（如檔案型別識別）。

2.  **非同步理解 (Semantic Phase)**：
    *   `TreeBuilder` 將臨時目錄移入正式路徑（如 `viking://resources/...`）。
    *   系統自動生成 `SemanticMsg` 並推入 `SemanticQueue`。
    *   後臺 `SemanticProcessor` 消費訊息，遍歷目錄樹，非同步生成各級目錄的 `.abstract.md` 和 `.overview.md`。

### 3. 使用示例

```python
# 匯入程式碼倉庫
client.add_resource(
    "https://github.com/volcengine/OpenViking",
    to="viking://resources/github/volcengine/OpenViking",
    reason="引入 OpenViking 原始碼作為參考"
)

# 搜尋程式碼邏輯
results = client.find(
    "OpenViking 和 VikingDB 的關係是什麼？",
    target_uri="viking://resources/github/volcengine/OpenViking/OpenViking/docs/zh/"
)
```

> 考慮到當前效能不佳，可以用小一點的倉庫測試：https://github.com/msgpack/msgpack-python

## 實現細節

### 檔案過濾規則

程式碼解析器實現了以下過濾規則：

1. **隱藏目錄忽略**：自動忽略 `.git`, `.idea`, `__pycache__`, `node_modules` 等非程式碼目錄
2. **二進位制檔案忽略**：跳過 `.pyc`, `.so`, `.dll`, `.exe`, `.bin` 等編譯檔案
3. **媒體檔案忽略**：不處理影片（.mp4, .mov, .avi 等）、音訊（.mp3, .wav, .m4a 等）等非文本內容
4. **文件檔案處理**：`.md`, `.txt`, `.rst` 等純文本格式的文件檔案**會被處理**，因為它們屬於"文本內容"
5. **符號連結處理**：檢測並跳過符號連結，記錄目標路徑但不解析內容
6. **檔案大小限制**：跳過大於 10MB 的檔案和零位元組檔案

### 檔案型別檢測

解析器包含輔助方法 `_detect_file_type()` 用於檢測檔案型別，可返回：
- `"code"`：程式語言檔案（.py, .java, .js, .cpp 等）
- `"documentation"`：文件檔案（.md, .txt, .rst 等）
- `"other"`：其他文本文件
- `"binary"`：二進位制檔案（已通過 `IGNORE_EXTENSIONS` 過濾）

### 測試驗證

包含完整的測試檔案 `tests/misc/test_code_parser.py` 驗證：
- `IGNORE_DIRS` 包含所有必需的目錄
- `IGNORE_EXTENSIONS` 包含所有必需的格式
- 符號連結處理正確實現
- 檔案型別檢測邏輯準確

### 最佳化 TODO
- 支援採用更輕量的模型進行檔案摘要，加快處理速度
- 設計長任務的追蹤機制，幫助觀測任務佇列中的任務歸屬，提供處理任務的統計資訊
- 支援增量解析，只解析新增或變動的檔案，避免重複解析已處理檔案
- 大幅提升端到端的處理效能！

## 相關文件

*   [上下文型別](docs/zh/concepts/context-types.md)
*   [Viking URI](docs/zh/concepts/viking-uri.md)
*   [上下文層級](docs/zh/concepts/context-layers.md)
