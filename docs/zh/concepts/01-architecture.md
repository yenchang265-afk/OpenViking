# 架構概述

OpenViking 是為 AI Agent 設計的上下文資料庫，將所有上下文（Memory、Resource、Skill）統一抽象為目錄結構，支援語義檢索和漸進式內容載入。

## 系統概覽

<ArchitectureDiagram />

<details>
<summary>文本版本</summary>

```text
CLI / SDK / HTTP client
          |
      HTTP Server
          |
      Service Layer
          |
   +------+------+----------------+
   |             |                |
Retrieval     Sessions       Resource / Skill import
   |             |                |
   |       Memory extraction  Parse / Semantic queues
   |             |                |
   +-------------+----------------+
                 |
             VikingFS
           /          \
      RAGFS         Vector index
```

</details>

## 核心模組

<div class="module-table">

| 模組 | 職責 | 關鍵能力 |
|------|------|---------|
| **Client** | 統一入口 | 通過 HTTP API 提交 SDK/CLI 支援的操作 |
| **Service** | 業務邏輯 | FSService、SearchService、SessionService、ResourceService、PackService、DebugService |
| **Retrieve** | 上下文檢索 | 意圖分析（IntentAnalyzer）、全域檢索（HierarchicalRetriever）、Rerank 精排 |
| **Session** | 會話管理 | 訊息記錄、使用追蹤、會話歸檔、觸發記憶提交 |
| **Parse** | 上下文提取 | 文件解析（PDF/MD/HTML）、樹構建（TreeBuilder）、非同步語義生成 |
| **Memory** | 記憶提取 | 按 MemoryType Schema 提取記憶（ExtractLoop），由 LLM 合併去重後以 patch 寫回（MemoryUpdater）；由 `SessionCompressorV3` 編排 |
| **Storage** | 儲存層 | VikingFS 虛擬檔案系統、向量索引、RAGFS 整合 |

</div>

## Service 層

Service 層將業務邏輯與傳輸層解耦，CLI 和 SDK 通過 HTTP Server 訪問業務能力：

| Service | 職責 | 主要方法 |
|---------|------|----------|
| **FSService** | 檔案系統操作 | ls, mkdir, rm, mv, tree, stat, read, abstract, overview, grep, glob |
| **SearchService** | 語義搜尋 | search, find |
| **SessionService** | 會話管理 | session, sessions, commit, delete |
| **ResourceService** | 資源匯入 | add_resource, add_skill, wait_processed |
| **PackService** | 匯入匯出、備份恢復 | export_ovpack, import_ovpack, backup_ovpack, restore_ovpack |
| **DebugService** | 除錯服務 | observer (ObserverService) |

## 雙層儲存

OpenViking 採用雙層儲存架構，實現內容與索引分離（詳見 [儲存架構](./05-storage.md)）：

| 儲存層 | 職責 | 內容 |
|--------|------|------|
| **RAGFS** | 內容儲存 | L0/L1/L2 完整內容、多媒體檔案、關聯關係 |
| **向量庫** | 索引儲存 | URI、向量、後設資料和檢索需要的文本（包括摘要） |

## 資料流概覽

### 添加上下文

```
輸入 → Parser → TreeBuilder → ResourceProcessor → RAGFS → SemanticQueue → 向量庫
```

1. **Parser**：將源文件解析為檔案與目錄；是否呼叫模型取決於所選 Parser
2. **TreeBuilder**：確定目標 URI，保留臨時產物引用
3. **ResourceProcessor**：將內容寫入 RAGFS，入隊語義處理
4. **SemanticQueue**：非同步自底向上生成 L0/L1
5. **向量庫**：建立索引用於語義搜尋

### 檢索上下文

```
查詢 → 意圖分析 → 全域檢索 → Rerank → 結果
```

1. **意圖分析**：分析查詢意圖，生成 0-5 個型別化查詢
2. **全域檢索**：每條查詢在許可權範圍內執行一次向量搜尋
3. **Rerank**：可選，對召回候選統一精排一次
4. **結果**：返回按相關性排序的上下文

### 會話提交

```
訊息 → 歸檔邊界 → 歸檔 → 記憶提取 → 儲存
```

1. **訊息**：累積對話訊息和使用記錄
2. **歸檔邊界**：按提交引數劃分歸檔訊息和保留訊息；預設歸檔全部當前訊息
3. **歸檔**：生成歷史片段的 L0/L1
4. **記憶提取**：根據記憶策略和 MemoryType Schema 從訊息中提取記憶
5. **儲存**：寫入 RAGFS + 向量庫

## 部署模式

### HTTP 模式

用於團隊共享、生產環境和跨語言整合：

```python
# Python SDK 連線 OpenViking Server
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(url="http://localhost:1933", api_key="your-key")
```

```bash
# 或使用 curl / 任意 HTTP 客戶端
curl http://localhost:1933/api/v1/search/find \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"query": "how to use openviking"}'
```

- Server 作為獨立程序執行（`openviking-server`）
- 客戶端通過 HTTP API 連線
- 支援任何能發起 HTTP 請求的語言
- 參見 [服務部署](../guides/03-deployment.md) 瞭解配置方法

## 設計原則

| 原則 | 說明 |
|------|------|
| **儲存層純粹** | 儲存層只做 RAGFS 操作和基礎向量搜尋，Rerank 在檢索層完成 |
| **三層資訊** | L0/L1/L2 實現漸進式詳情載入，節省 Token 消耗 |
| **兩階段檢索** | 向量搜尋召回候選 + Rerank 精排提高準確性 |
| **單一資料來源** | RAGFS 儲存原始檔，向量記錄保留檢索需要的文本與後設資料 |

## 相關文件

- [上下文型別](./02-context-types.md) - Resource/Memory/Skill 三種類型
- [上下文層級](./03-context-layers.md) - L0/L1/L2 模型
- [Viking URI](./04-viking-uri.md) - 統一資源識別符號
- [儲存架構](./05-storage.md) - 雙層儲存詳解
- [檢索機制](./07-retrieval.md) - 檢索流程詳解
- [上下文提取](./06-extraction.md) - 解析和提取流程
- [會話管理](./08-session.md) - 會話和記憶管理
- [事務模型](./09-transaction.md) - 寫入與一致性模型
- [資料加密](./10-encryption.md) - 靜態資料加密與金鑰架構
- [多租戶](./11-multi-tenant.md) - account / user / peer 隔離模型
- [指標](./12-metrics.md) - `/metrics` 使用方式與關鍵指標說明
- [使用者隱私配置](./13-privacy.md) - 隱私版本管理、自動提取Skill/Session隱私配置
