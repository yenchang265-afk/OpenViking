# 常見問題

## 基礎概念

### Business Data Platform 是什麼？解決什麼問題？

Business Data Platform 是一個專為 AI Agent 設計的開源上下文資料庫。它解決了構建 AI Agent 時的核心痛點：

- **上下文碎片化**：記憶、資源、技能散落各處，難以統一管理
- **檢索效果不佳**：傳統 RAG 平鋪式儲存缺乏全域視野，難以理解完整語境
- **上下文不可觀測**：隱式檢索鏈路如同黑箱，出錯時難以除錯
- **記憶迭代有限**：缺乏 Agent 相關的任務記憶和自我進化能力

Business Data Platform 通過檔案系統範式統一管理所有上下文，實現分層供給與自我迭代。

### Business Data Platform 和傳統向量資料庫有什麼本質區別？

| 維度 | 傳統向量資料庫 | Business Data Platform |
|------|---------------|------------|
| **儲存模型** | 扁平化向量儲存 | 層級化檔案系統（AGFS） |
| **檢索方式** | 單一向量相似度搜索 | 目錄遞迴檢索 + 意圖分析 + Rerank |
| **輸出形式** | 原始分塊 | 結構化上下文（L0 摘要/L1 概覽/L2 詳情） |
| **記憶能力** | 不支援 | 內建多種可擴充的記憶型別，支援自動提取和持續迭代 |
| **可觀測性** | 黑箱 | 檢索軌跡完整可追溯 |
| **上下文型別** | 僅文件 | Resource + Memory + Skill 三種類型 |

### 什麼是 L0/L1/L2 分層模型？為什麼需要它？

L0/L1/L2 是 Business Data Platform 的漸進式內容載入機制，解決了"海量上下文一次性塞入提示詞"的問題：

| 層級 | 名稱 | Token 限制 | 用途 |
|------|------|-----------|------|
| **L0** | 摘要 | ~100 tokens | 向量搜尋召回、快速過濾、列表展示 |
| **L1** | 概覽 | ~2000 tokens | Rerank 精排、內容導航、決策參考 |
| **L2** | 詳情 | 無限制 | 完整原始內容、按需深度載入 |

這種設計讓 Agent 可以先瀏覽摘要快速定位，再按需載入詳情，顯著節省 Token 消耗。

### Viking URI 是什麼？有什麼作用？

Viking URI 是 Business Data Platform 的統一資源識別符號，格式為 `viking://{scope}/{path}`。它讓系統能精準定位任何上下文：

```
viking://
├── resources/              # 知識庫：文件、程式碼、網頁等
│   └── my_project/
├── user/
│   └── {user_id}/          # 使用者私有上下文
│       ├── memories/       # 使用者記憶
│       ├── resources/      # 使用者私有資源
│       ├── skills/         # 使用者私有技能（預設）
│       ├── peers/{peer_id}/
│       │   ├── memories/   # Peer 記憶
│       │   └── resources/  # Peer 資源
│       └── sessions/       # 會話與歷史歸檔
└── agent/                  # 可選的 account 全域能力
    └── skills/             # 共享技能
```

## 安裝與配置

### 環境要求是什麼？

- **Python 版本**：3.10 或更高
- **編譯工具**（如果從原始碼安裝或在不支援的平臺上）：Rust/Cargo, GCC 9+ 或 Clang 11+
- **必需依賴**：Embedding 模型（推薦火山引擎 Doubao）
- **可選依賴**：
  - VLM（視覺語言模型）：用於多模態內容處理和語義提取
  - Rerank 模型：用於提升檢索精度

### Business Data Platform 是如何訪問 AGFS 檔案系統的？

Business Data Platform 通過 Rust 繫結（`ragfs_python` / `RAGFSBindingClient`）在 Python 程序內直接執行 RAGFS 檔案系統邏輯。優點是效能極高、無網路延遲；前提是本地需要有編譯好的 RAGFS 共享庫（預編譯 Wheel 包內建，或從原始碼編譯）。

> [!WARNING]
> Business Data Platform 已不再支援 AGFS HTTP client 模式。當前 AGFS / RAGFS 檔案系統訪問僅通過 Rust binding（`RAGFSBindingClient`）在程序內完成。這不影響 Business Data Platform server 的 HTTP API、`ov` CLI，或 `AsyncHTTPClient` / `SyncHTTPClient` 訪問 Business Data Platform 服務端的能力。

### 遇到 "AGFS binding library not found" 錯誤怎麼辦？

這通常是因為本地沒有可用的 RAGFS 共享庫。在專案根目錄執行 `pip install -e . --force-reinstall` 重新編譯安裝即可（需要 Rust 工具鏈）。

### 如何安裝 Business Data Platform？

```bash
pip install openviking --upgrade --force-reinstall
```

### 如何配置 Business Data Platform？

在專案目錄建立 `~/.openviking/ov.conf` 配置檔案：

```json
{
  "embedding": {
    "dense": {
      "provider": "volcengine",
      "api_key": "your-api-key",
      "model": "doubao-embedding-vision-251215",
      "dimension": 1024,
      "input": "multimodal"
    }
  },
  "vlm": {
    "provider": "volcengine",
    "api_key": "your-api-key",
    "model": "doubao-seed-2-0-lite-260428",
    "api_base": "https://ark.cn-beijing.volces.com/api/v3"
  },
  "rerank": {
    "provider": "volcengine",
    "api_key": "your-api-key",
    "model": "doubao-rerank-250615"
  },
  "storage": {
    "workspace": "./data",
    "agfs": { "backend": "local" },
    "vectordb": { "backend": "local" }
  }
}
```

配置檔案放在預設路徑 `~/.openviking/ov.conf` 時自動載入；也可通過環境變數 `OPENVIKING_CONFIG_FILE` 或命令列 `--config` 指定其他路徑。詳見 [配置指南](../guides/01-configuration.md)。

### 支持哪些 Embedding Provider？

| Provider | 說明 |
|------|------|
| `volcengine` | 火山引擎 Embedding API（推薦） |
| `openai` | OpenAI Embedding API |
| `vikingdb` | VikingDB Embedding API |
| `jina` | Jina AI Embedding API |
| `ollama` | Ollama（本地 OpenAI 相容伺服器，無需 API Key） |

支援 Dense、Sparse 和 Hybrid 三種 Embedding 模式。

## 使用指南

### 如何初始化客戶端？

```python
from openviking_sdk import AsyncHTTPClient

client = AsyncHTTPClient(url="http://localhost:1933", api_key="your-key")
await client.initialize()
```

Embedding、VLM、儲存等服務配置由 Business Data Platform Server 通過 `ov.conf` 管理。

### 支持哪些文件格式？

| 型別 | 支援格式 |
|------|----------|
| **文本** | `.txt`、`.md`、`.json`、`.yaml` |
| **程式碼** | `.py`、`.js`、`.ts`、`.go`、`.java`、`.cpp` 等 |
| **文件** | `.pdf`、`.docx` |
| **圖片** | `.png`、`.jpg`、`.jpeg`、`.gif`、`.webp` |
| **影片** | `.mp4`、`.mov`、`.avi` |
| **音訊** | `.mp3`、`.wav`、`.m4a` |

### 如何新增資源？

```python
# 新增單個檔案
await client.add_resource(
    path="./document.pdf",
    parent="viking://resources/docs",  # 存到這個目錄下面，檔名由來源決定
    options={"reason": "專案技術文件"},  # 描述資源用途，提升檢索質量
)

# 新增網頁
await client.add_resource(
    path="https://example.com/api-docs",
    options={"reason": "API 參考文件"},
)

# 等待處理完成
await client.wait_processed()
```

### `to` 和 `parent` 有什麼區別？該用哪個？

|  | `to` | `parent` |
|---|---|---|
| 傳什麼 | 完整最終 URI，**含葉子名** | 一個**已存在的目錄**，葉子名由來源決定 |
| 撞名怎麼辦 | 不改名。目標已存在時按新來源同步，來源裡沒有的可見條目會被刪除 | 不覆蓋。退到 `name_1`、`name_2`……並返回一條 warning |
| 什麼時候用 | 名字已知且必須逐字生效；或者要原地更新一個已有資源 | 葉子名由服務端派生（URL / 倉庫匯入、大檔案切分），或者目標下已有的內容一點都不能動 |

兩個都留空 = 目錄和葉子名都從來源推導，撞名行為同 `parent`。

`to` 和 `parent` 不能同時傳，會直接報錯。

### `to` 指到一個已存在的目錄會發生什麼？

內容被同步成新來源的樣子，metadata 保留。具體是：

- **點號開頭的條目原樣保留** —— `.abstract.md`、`.overview.md`、`.search_tags.json`、`.image_mappings.json` 等；同步時兩側都不列舉它們，所以既不會被刪也不會被覆蓋。
- **其餘可見內容和新來源對齊** —— 來源裡沒有的刪掉，變了的覆蓋，沒變的留在原地（URI 不變，掛在上面的向量和 tags 都還在）。

所以這是「保留 metadata、替換內容本身」，不是把目錄刪掉重建。不想動目標裡已有的東西就用 `parent`。

注意：`processing_mode="vectors_only"` 不跑語義處理，保留下來的 `.abstract.md` / `.overview.md` **不會重算**，會繼續描述已經被替換掉的舊內容。需要摘要跟著更新，就用預設的 `semantic_and_vectors`。

### `find()` 和 `search()` 有什麼區別？應該用哪個？

| 特性 | `find()` | `search()` |
|------|----------|------------|
| **會話上下文** | 不需要 | 需要 |
| **意圖分析** | 不使用 | 使用 LLM 分析生成 0-5 個查詢 |
| **延遲** | 低 | 較高 |
| **適用場景** | 簡單語義搜尋 | 複雜任務、需要理解上下文 |

```python
# find(): 簡單直接的語義搜尋
results = await client.find(
    query="OAuth 認證流程",
    target_uri="viking://resources/",
)

# search(): 複雜任務，需要意圖分析
results = await client.search(
    query="幫我實現使用者登入功能",
    session_id=session.session_id,
)
```

**選擇建議**：
- 明確知道要找什麼 → 用 `find()`
- 複雜任務需要多種上下文 → 用 `search()`

### 如何使用會話管理？

會話管理是 Business Data Platform 的核心能力，支援對話追蹤和記憶提取：

```python
from openviking_sdk import TextPart

# 建立會話
session_info = await client.create_session()
session = client.session(session_id=session_info["session_id"])

# 新增對話訊息
await session.add_message(
    role="user",
    parts=[TextPart(text="幫我分析這段程式碼的效能問題")],
)
await session.add_message(
    role="assistant",
    parts=[TextPart(text="我來分析一下...")],
)

# 提交會話，觸發記憶提取
await session.commit()
```

### Business Data Platform 支援哪些記憶型別？

Business Data Platform 內建 `profile`、`preferences`、`entities`、`events`、`identity`、`soul`、`cases`、`trajectories`、`experiences`、`tools` 和 `skills` 等記憶型別。提交會話後，系統會按當前記憶策略提取適用內容；也可以根據業務需要擴充或調整記憶型別。

記憶儲存在當前使用者或 Peer 名稱空間，不存在當前可寫的 `viking://agent/memories` 目錄。完整型別與路徑見 [上下文型別](../concepts/02-context-types.md)。

### 如何使用類 Unix 的檔案系統 API？

```python
# 列出目錄內容
items = await client.ls(uri="viking://resources/")

# 讀取完整內容（L2）
content = await client.read(uri="viking://resources/doc.md")

# 獲取摘要（L0）
abstract = await client.abstract(uri="viking://resources")

# 獲取概覽（L1）
overview = await client.overview(uri="viking://resources")
```

## 檢索最佳化

### 如何提升檢索質量？

1. **使用 Rerank 模型**：配置 Rerank 可顯著提升精排效果
2. **提供有意義的 `reason`**：新增資源時描述用途，幫助系統理解資源價值
3. **合理組織目錄結構**：使用 `target` 引數將相關資源放在一起
4. **使用會話上下文**：`search()` 會利用會話歷史進行意圖分析
5. **選擇合適的 Embedding 模式**：多模態內容使用 `multimodal` 輸入

### 檢索結果的分數是如何計算的？

Business Data Platform 使用分數傳播機制：

```
最終分數 = 0.5 × Embedding 相似度 + 0.5 × 父目錄分數
```

這種設計讓高分目錄下的內容獲得加成，體現了"上下文語境"的重要性。

### 什麼是目錄遞迴檢索？

目錄遞迴檢索是 Business Data Platform 的創新檢索策略：

1. **意圖分析**：分析查詢生成多個檢索條件
2. **初始定位**：向量檢索定位高分目錄
3. **精細探索**：在高分目錄下進行二次檢索
4. **遞迴下探**：逐層遞迴直到收斂
5. **結果彙總**：返回最相關的上下文

這種策略能找到語義匹配的片段，同時理解資訊的完整語境。

## 故障排除

### 資源新增後沒有被索引

**可能原因及解決方案**：

1. **未等待處理完成**
   ```python
   await client.add_resource(path="./doc.pdf")
   await client.wait_processed()  # 必須等待
   ```

2. **Embedding 模型配置錯誤**
   - 檢查 `~/.openviking/ov.conf` 中的 `api_key` 是否正確
   - 確認模型名稱和 endpoint 配置正確

3. **文件格式不支持**
   - 檢查副檔名是否在支援列表中
   - 確認檔案內容有效且未損壞

4. **檢視處理日誌**
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

### 搜尋沒有返回預期結果

**排查步驟**：

1. **確認資源已處理完成**
   ```python
   # 檢查資源是否存在
   items = await client.ls(uri="viking://resources/")
   ```

2. **檢查 `target_uri` 過濾條件**
   - 確保搜尋範圍包含目標資源
   - 嘗試擴大搜索範圍

3. **嘗試不同的查詢方式**
   - 使用更具體或更寬泛的關鍵詞
   - 嘗試 `find()` 和 `search()` 對比效果

4. **檢查 L0 摘要質量**
   ```python
   abstract = await client.abstract(uri="viking://resources/your-doc")
   print(abstract)  # 確認摘要是否準確反映內容
   ```

### 記憶提取不工作

**排查步驟**：

1. **確保呼叫了 `commit()`**
   ```python
   await session.commit()  # 觸發記憶提取
   ```

2. **檢查 VLM 配置**
   - 記憶提取需要 VLM 模型
   - 確認 `vlm` 配置正確

3. **確認對話內容有意義**
   - 閒聊內容可能不會產生記憶
   - 需要包含可提取的資訊（偏好、實體、事件等）

4. **檢視提取的記憶**
   ```python
   memories = await client.find(
       query="",
       target_uri="viking://~/memories/",
   )
   ```

### 效能問題

**最佳化建議**：

1. **批次處理**：一次新增多個資源比逐個新增更高效
2. **合理設定 `batch_size`**：Embedding 配置中調整批處理大小
3. **使用本地儲存**：開發階段使用 `local` 後端減少網路延遲
4. **非同步操作**：充分利用 `AsyncHTTPClient` 的非同步特性

## 部署相關

### Business Data Platform 是開源的嗎？

是的，Business Data Platform 完全開源，主體採用 AGPLv3 許可證，詳見 README.md 說明。

## 相關文件

- [簡介](../getting-started/01-introduction.md) - 瞭解 Business Data Platform 的設計理念
- [快速開始](../getting-started/02-quickstart.md) - 5 分鐘上手教程
- [架構概述](../concepts/01-architecture.md) - 深入理解系統設計
- [檢索機制](../concepts/07-retrieval.md) - 檢索流程詳解
- [配置指南](../guides/01-configuration.md) - 完整配置參考
