# 常見問題

## 基礎概念

### OpenViking 是什麼？解決什麼問題？

OpenViking 用檔案系統組織 Agent 的資源、記憶和技能，支援按路徑瀏覽、語義檢索和按需讀取。應用可以把會話中提取的偏好與經驗儲存下來，在後續任務中複用。

它針對構建 Agent 時的四個常見問題：

- **上下文碎片化**：記憶、資源、技能分散在不同位置，難以統一管理
- **檢索效果不佳**：平鋪式分塊儲存丟失了周邊結構，檢索結果缺少完整語境
- **上下文不可觀測**：隱式檢索鏈路出錯時難以排查
- **記憶迭代有限**：缺少可跨會話積累的任務記憶

例如，使用者讓 Agent 修改部署方案時，Agent 可以檢索專案文件，再讀取相關配置；上次會話中已確認的部署約束，如果已提取為記憶，也可以在這次任務中檢索和複用。應用需要接入檢索與會話提交流程，安裝資料庫本身不會讓 Agent 自動獲得這些上下文。首次使用可從[匯入一份資料並檢索](../getting-started/02-quickstart.md)開始，再按需要接入[Agent 工具](../agent-integrations/01-overview.md)。

### OpenViking 和傳統向量資料庫有什麼本質區別？

向量資料庫主要提供向量儲存和相似度檢索。OpenViking 在向量檢索之上，提供上下文目錄、分層摘要、資源匯入、會話和記憶管理。已有向量資料庫的能力因產品而異，選型時應按具體需求比較。

| 需求 | OpenViking 提供的能力 |
| --- | --- |
| 組織上下文 | 用 `viking://` 路徑管理資源、記憶和技能 |
| 檢索內容 | 在目錄範圍內做向量檢索，可配置意圖分析和 Rerank |
| 控制讀取量 | 先讀目錄摘要或概覽，再按需讀取詳細內容 |
| 複用會話經驗 | 提交會話後，按記憶策略提取和更新記憶 |
| 排查檢索問題 | 使用日誌與 telemetry 檢視處理和檢索過程 |

如果應用只需要對已有向量做相似度查詢，應先評估現有資料庫是否夠用。需要目錄瀏覽、摘要與詳情分層讀取，或跨會話記憶管理時，再評估 OpenViking。用自己的資料和代表性問題比較召回內容、讀取量、延遲和處理成本；收益取決於資料、模型與配置。

### 什麼是 L0/L1/L2 分層模型？為什麼需要它？

Agent 可以先讀摘要定位內容，再按需讀全文，減少不相關內容進入上下文。

| 層級 | 內容 | 預設正文目標 | 用途 |
| --- | --- | --- | --- |
| L0 | 目錄摘要 `.abstract.md` | 256 字元 | 檢索與快速篩選 |
| L1 | 目錄概覽 `.overview.md` | 4,000 字元 | 導航與精排 |
| L2 | 原始檔案或解析後的內容 | 無統一上限 | 按需讀取詳情 |

L0/L1 是目錄級附屬檔案，是否可用取決於處理狀態和配置。資源摘要的生成目標按字元計算，可通過 `semantic.abstract_max_chars` 和 `semantic.overview_max_chars` 調整。截斷會保留完整句子，因此首句可能超過目標；這不是已儲存附屬檔案的硬上限，詳見[上下文層級](../concepts/03-context-layers.md)。

### Viking URI 是什麼？有什麼作用？

Viking URI 是 OpenViking 的統一資源識別符號，格式為 `viking://{scope}/{path}`。它讓系統能精準定位任何上下文：

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

### OpenViking 是如何訪問 AGFS 檔案系統的？

OpenViking 通過 Rust 繫結（`ragfs_python` / `RAGFSBindingClient`）在 Python 程序內直接執行 RAGFS 檔案系統邏輯。檔案系統呼叫在程序內完成；使用遠端儲存後端時仍會訪問網路。RAGFS 共享庫隨預編譯 wheel 提供，也可從原始碼構建。

> [!WARNING]
> OpenViking 已不再支援 AGFS HTTP client 模式。當前 AGFS / RAGFS 檔案系統訪問僅通過 Rust binding（`RAGFSBindingClient`）在程序內完成。這不影響 OpenViking server 的 HTTP API、`ov` CLI，或 `AsyncHTTPClient` / `SyncHTTPClient` 訪問 OpenViking 服務端的能力。

### 遇到 "AGFS binding library not found" 錯誤怎麼辦？

這通常表示 RAGFS 共享庫缺失或無法載入。先檢查 Python 版本和平臺是否有對應的預編譯 wheel，並嘗試重新安裝。只有平臺缺少 wheel 或需要修改原始碼時才[從原始碼構建](https://github.com/volcengine/OpenViking/blob/main/docs/repository/CONTRIBUTING_CN.md)，屆時需準備原生編譯工具鏈。

### 如何安裝 OpenViking？

```bash
pip install openviking --upgrade --force-reinstall
```

### 如何配置 OpenViking？

在使用者主目錄下建立 `~/.openviking/ov.conf`，將示例中的模型和憑據替換為實際配置：

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
    "provider": "vikingdb",
    "ak": "your-access-key",
    "sk": "your-secret-key",
    "model_name": "doubao-seed-rerank",
    "model_version": "251028"
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
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(url="http://localhost:1933", api_key="your-key")
client.initialize()
```

Embedding、VLM、儲存等服務配置由 OpenViking Server 通過 `ov.conf` 管理。

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
client.add_resource(
    path="./document.pdf",
    parent="viking://resources",  # 存到這個目錄下面，檔名由來源決定
    options={"reason": "專案技術文件"},  # 未傳 instruction 時用於生成 L0/L1 摘要，也用於資源相關的記憶提取
)

# 新增網頁
client.add_resource(
    path="https://example.com/api-docs",
    options={"reason": "API 參考文件"},
)

# 等待處理完成
client.wait_processed()
```

### `to` 和 `parent` 有什麼區別？該用哪個？

|  | `to` | `parent` |
|---|---|---|
| 傳什麼 | 完整最終 URI，**含葉子名** | 一個**已存在的目錄**，葉子名由來源決定 |
| 撞名怎麼辦 | 不改名。目標目錄已存在時按新來源同步，來源裡沒有的可見條目會被刪除 | 不覆蓋。退到 `name_1`、`name_2`……並返回一條 warning |
| 什麼時候用 | 名字已知且必須逐字生效；或者要原地更新一個已有資源 | 葉子名由服務端派生（URL / 倉庫匯入、大檔案切分），或者目標下已有的內容一點都不能動 |

兩個都留空 = 目錄和葉子名都從來源推導，撞名行為同 `parent`。資源名稱空間根目錄是例外：`to` 為 `viking://resources` 等資源根目錄時，會按父目錄處理。資源根目錄不存在時會自動建立；其他父目錄不存在時，可傳入 `options={"create_parent": True}`。

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
| **會話上下文** | 不使用 | 可選，傳入 `session_id` 且啟用意圖分析時使用 |
| **意圖分析** | 不使用 | 有會話內容且啟用意圖分析時使用 LLM |
| **延遲** | 取決於 Embedding、檢索和 Rerank | 使用意圖分析時增加一次 LLM 呼叫 |
| **適用場景** | 簡單語義搜尋 | 複雜任務、需要理解上下文 |

```python
# find(): 簡單直接的語義搜尋
results = client.find(
    query="OAuth 認證流程",
    target_uri="viking://resources/",
)

# search(): 複雜任務，需要意圖分析
results = client.search(
    query="幫我實現使用者登入功能",
    session_id=session.session_id,
)
```

**選擇建議**：
- 明確知道要找什麼 → 用 `find()`
- 複雜任務需要多種上下文 → 用 `search()`

### 如何使用會話管理？

會話管理是 OpenViking 的核心能力，支援對話追蹤和記憶提取：

```python
from openviking_sdk import TextPart

# 建立會話
session_info = client.create_session()
session = client.session(session_id=session_info["session_id"])

# 新增對話訊息
session.add_message(
    role="user",
    parts=[TextPart(text="幫我分析這段程式碼的效能問題")],
)
session.add_message(
    role="assistant",
    parts=[TextPart(text="我來分析一下...")],
)

# 提交會話，觸發記憶提取
session.commit()
```

### OpenViking 支援哪些記憶型別？

OpenViking 內建 `profile`、`preferences`、`entities`、`events`、`identity`、`soul`、`cases`、`trajectories`、`experiences` 等記憶型別。提交會話後，系統會按當前記憶策略提取適用內容；也可以根據業務需要擴充或調整記憶型別。

記憶儲存在當前使用者或 Peer 名稱空間，不存在當前可寫的 `viking://agent/memories` 目錄。完整型別與路徑見 [上下文型別](../concepts/02-context-types.md)。

### 如何使用類 Unix 的檔案系統 API？

```python
# 列出目錄內容
items = client.ls(uri="viking://resources/")

# 讀取完整內容（L2）
content = client.read(uri="viking://resources/doc.md")

# 獲取摘要（L0）
abstract = client.abstract(uri="viking://resources")

# 獲取概覽（L1）
overview = client.overview(uri="viking://resources")
```

## 檢索最佳化

### 如何提升檢索質量？

1. **檢查摘要**：確認 L0/L1 是否準確反映來源；需要調整時使用匯入的 `instruction` 或摘要模板
2. **組織目錄結構**：匯入時用 `parent` 指定現有父目錄，或用 `to` 指定最終 URI
3. **使用會話上下文**：保持 `retrieval.enable_intent` 開啟（預設），並向 `search()` 傳入有內容的會話
4. **選擇合適的 Embedding 模式**：多模態內容使用 `multimodal` 輸入
5. **評估 Rerank 模型**：對代表性查詢比較啟用前後的排序結果，再決定是否啟用。可以嘗試用 Jev（TypeSafe System One）做 rerank：它對每個候選單獨判斷與查詢的相關性，各候選分數互不競爭；配置見[配置指南](../guides/01-configuration.md#rerank)

### 檢索結果的分數是如何計算的？

未啟用 Rerank 時，結果直接使用向量分數。啟用 Rerank 時，使用其分數排序；請求失敗或返回無效結果時回退到向量分數。訪問頻次、更新時間和父目錄分數均不參與加權。

### 全域檢索是如何執行的？

每條查詢在指定目錄範圍、許可權過濾和 level 條件內執行一次全域向量檢索。THINKING 模式且配置了可用 Rerank 時，召回最多 `2 × limit` 條候選，統一精排一次後返回最多 `limit` 條；不啟用 Rerank 時直接召回 `limit` 條。檢索不會逐層遍歷目錄，也不會在精排後觸發下一輪召回。

## 故障排除

### 資源新增後沒有被索引

**可能原因及解決方案**：

1. **未等待處理完成**
   ```python
   result = client.add_resource(path="./doc.pdf", wait=True)
   print(result)
   ```
   新匯入時可用 `wait=True` 等待。排查已經提交的匯入時，用返回的 `task_id` 查詢任務，不必重複匯入。狀態仍為 `pending` 或 `running` 時需要繼續等待；`failed` 或 `cancelled` 時檢視任務詳情。請求超時也不能據此判斷後臺任務已經失敗，詳見[非同步任務](../api/17-tasks.md)。

2. **Embedding 模型配置錯誤**
   - 檢查 `~/.openviking/ov.conf` 中的 `api_key` 是否正確
   - 確認模型名稱和 endpoint 配置正確

3. **文件格式不支持**
   - 檢查副檔名是否在支援列表中
   - 確認檔案內容有效且未損壞

4. **檢視服務端處理日誌**
   在執行服務端的終端或日誌系統中檢視對應任務的錯誤。客戶端的 Python 日誌設定不會開啟遠端服務端日誌。

### 搜尋沒有返回預期結果

**排查步驟**：

1. **確認資源存在，再查詢匯入任務狀態**
   用匯入時返回的 `task_id` 查詢任務；`completed` 表示處理完成，`failed` 或 `cancelled` 需先檢查原因。
   ```python
   # 檢查資源是否存在
   items = client.ls(uri="viking://resources/")
   task = client.get_task("<匯入時返回的 task_id>")
   print(task["status"] if task is not None else "任務不存在或已過期")
   ```

2. **檢查 `target_uri` 過濾條件**
   - 確保搜尋範圍包含目標資源
   - 嘗試擴大搜索範圍

3. **嘗試不同的查詢方式**
   - 使用更具體或更寬泛的關鍵詞
   - 嘗試 `find()` 和 `search()` 對比效果

4. **檢查 L0 摘要質量**
   ```python
   abstract = client.abstract(uri="viking://resources/your-doc")
   print(abstract)  # 確認摘要是否準確反映內容
   ```

### 記憶提取不工作

**排查步驟**：

1. **確保呼叫了 `commit()`**
   ```python
   session.commit()  # 觸發記憶提取
   ```

2. **檢查 VLM 配置**
   - 記憶提取需要 VLM 模型
   - 確認 `vlm` 配置正確

3. **確認對話內容有意義**
   - 閒聊內容可能不會產生記憶
   - 需要包含可提取的資訊（偏好、實體、事件等）

4. **檢視記憶目錄**
   ```python
   memories = client.ls(uri="viking://~/memories/")
   ```

### 效能問題

**最佳化建議**：

1. **定位瓶頸**：先檢查處理佇列、模型延遲和儲存耗時，再調整併發
2. **合理設定 `batch_size`**：Embedding 配置中調整批處理大小
3. **使用本地儲存**：開發階段使用 `local` 後端減少網路延遲
4. **非同步操作**：應用自身已有事件迴圈（FastAPI、agent 框架）時用 `AsyncHTTPClient`；指令碼和 notebook 用 `SyncHTTPClient`，它是非同步客戶端的包裝

## 部署相關

### OpenViking 是開源的嗎？

OpenViking 主體採用 AGPLv3，CLI 和大部分示例採用 Apache 2.0。各元件及例外見倉庫的[許可證說明](https://github.com/volcengine/OpenViking#license)。

## 相關文件

- [簡介](../getting-started/01-introduction.md) - 瞭解 OpenViking 的設計理念
- [快速開始](../getting-started/02-quickstart.md) - 5 分鐘上手教程
- [架構概述](../concepts/01-architecture.md) - 深入理解系統設計
- [檢索機制](../concepts/07-retrieval.md) - 檢索流程詳解
- [配置指南](../guides/01-configuration.md) - 完整配置參考
