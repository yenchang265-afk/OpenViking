# 架構概述

Business Data Platform 是為 AI Agent 設計的上下文資料庫，將所有上下文（Memory、Resource、Skill）統一抽象為目錄結構，支援語義檢索和漸進式內容載入。

## 系統概覽

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           Business Data Platform 系統架構                               │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│                              ┌─────────────┐                               │
│                              │   Client    │                               │
│                              │ (Business Data Platform)│                               │
│                              └──────┬──────┘                               │
│                                     │ 委託                                  │
│                              ┌──────▼──────┐                               │
│                              │   Service   │                               │
│                              │    Layer    │                               │
│                              └──────┬──────┘                               │
│                                     │                                      │
│           ┌─────────────────────────┼─────────────────────────┐            │
│           │                         │                         │            │
│           ▼                         ▼                         ▼            │
│    ┌─────────────┐          ┌─────────────┐          ┌─────────────┐      │
│    │  Retrieve   │          │   Session   │          │    Parse    │      │
│    │ (上下文檢索) │          │  (會話管理)  │          │ (上下文提取) │      │
│    │             │          │             │          │             │      │
│    │ search/find │          │ add         │          │ 文件解析    │      │
│    │ 意圖分析    │          │ commit      │          │ L0/L1/L2    │      │
│    │ Rerank     │          │ commit      │          │ 樹構建      │      │
│    └──────┬──────┘          └──────┬──────┘          └──────┬──────┘      │
│           │                        │                        │             │
│           │                        │ 記憶提取               │             │
│           │                        ▼                        │             │
│           │                 ┌─────────────┐                 │             │
│           │                 │ Compressor  │                 │             │
│           │                 │ 壓縮/去重    │                 │             │
│           │                 └──────┬──────┘                 │             │
│           │                        │                        │             │
│           └────────────────────────┼────────────────────────┘             │
│                                    ▼                                      │
│    ┌─────────────────────────────────────────────────────────────────┐    │
│    │                         Storage 層                               │    │
│    │              AGFS (檔案內容)  +  向量庫 (索引)                    │    │
│    └─────────────────────────────────────────────────────────────────┘    │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

## 核心模組

| 模組 | 職責 | 關鍵能力 |
|------|------|---------|
| **Client** | 統一入口 | 提供所有操作介面，委託給 Service 層 |
| **Service** | 業務邏輯 | FSService、SearchService、SessionService、ResourceService、PackService、DebugService |
| **Retrieve** | 上下文檢索 | 意圖分析（IntentAnalyzer）、層級檢索（HierarchicalRetriever）、Rerank 精排 |
| **Session** | 會話管理 | 訊息記錄、使用追蹤、會話壓縮、記憶提交 |
| **Parse** | 上下文提取 | 文件解析（PDF/MD/HTML）、樹構建（TreeBuilder）、非同步語義生成 |
| **Compressor** | 記憶壓縮 | Schema 驅動的記憶提取、LLM 去重決策 |
| **Storage** | 儲存層 | VikingFS 虛擬檔案系統、向量索引、AGFS 整合 |

## Service 層

Service 層將業務邏輯與傳輸層解耦，便於 HTTP Server 和 CLI 複用：

| Service | 職責 | 主要方法 |
|---------|------|----------|
| **FSService** | 檔案系統操作 | ls, mkdir, rm, mv, tree, stat, read, abstract, overview, grep, glob |
| **SearchService** | 語義搜尋 | search, find |
| **SessionService** | 會話管理 | session, sessions, commit, delete |
| **ResourceService** | 資源匯入 | add_resource, add_skill, wait_processed |
| **PackService** | 匯入匯出、備份恢復 | export_ovpack, import_ovpack, backup_ovpack, restore_ovpack |
| **DebugService** | 除錯服務 | observer (ObserverService) |

## 雙層儲存

Business Data Platform 採用雙層儲存架構，實現內容與索引分離（詳見 [儲存架構](./05-storage.md)）：

| 儲存層 | 職責 | 內容 |
|--------|------|------|
| **AGFS** | 內容儲存 | L0/L1/L2 完整內容、多媒體檔案、關聯關係 |
| **向量庫** | 索引儲存 | URI、向量、後設資料（不儲存檔案內容） |

## 資料流概覽

### 添加上下文

```
輸入 → Parser → TreeBuilder → AGFS → SemanticQueue → 向量庫
```

1. **Parser**：解析文件，建立檔案和目錄結構（無 LLM 呼叫）
2. **TreeBuilder**：移動臨時目錄到 AGFS，入隊語義處理
3. **SemanticQueue**：非同步自底向上生成 L0/L1
4. **向量庫**：建立索引用於語義搜尋

### 檢索上下文

```
查詢 → 意圖分析 → 層級檢索 → Rerank → 結果
```

1. **意圖分析**：分析查詢意圖，生成 0-5 個型別化查詢
2. **層級檢索**：目錄級遞迴搜尋，使用優先佇列
3. **Rerank**：標量過濾 + 模型重排
4. **結果**：返回按相關性排序的上下文

### 會話提交

```
訊息 → 壓縮 → 歸檔 → 記憶提取 → 儲存
```

1. **訊息**：累積對話訊息和使用記錄
2. **壓縮**：保留最近 N 輪，舊訊息歸檔
3. **歸檔**：生成歷史片段的 L0/L1
4. **記憶提取**：根據記憶策略和 MemoryType Schema 從訊息中提取記憶
5. **儲存**：寫入 AGFS + 向量庫

## 部署模式

### HTTP 模式

用於團隊共享、生產環境和跨語言整合：

```python
# Python SDK 連線 Business Data Platform Server
client = SyncHTTPClient(url="http://localhost:1933", api_key="xxx")
```

```bash
# 或使用 curl / 任意 HTTP 客戶端
curl http://localhost:1933/api/v1/search/find \
  -H "X-API-Key: xxx" \
  -d '{"query": "how to use openviking"}'
```

- Server 作為獨立程序執行（`openviking-server`）
- 客戶端通過 HTTP API 連線
- 支援任何能發起 HTTP 請求的語言
- 參見 [服務部署](../guides/03-deployment.md) 瞭解配置方法

## 設計原則

| 原則 | 說明 |
|------|------|
| **儲存層純粹** | 儲存層只做 AGFS 操作和基礎向量搜尋，Rerank 在檢索層完成 |
| **三層資訊** | L0/L1/L2 實現漸進式詳情載入，節省 Token 消耗 |
| **兩階段檢索** | 向量搜尋召回候選 + Rerank 精排提高準確性 |
| **單一資料來源** | 所有內容從 AGFS 讀取，向量庫僅儲存引用和索引 |

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
- [多租戶](./11-multi-tenant.md) - account / user / agent 隔離模型
- [指標](./12-metrics.md) - `/metrics` 使用方式與關鍵指標說明
- [使用者隱私配置](./13-privacy.md) - 隱私版本管理、自動提取Skill隱私配置
