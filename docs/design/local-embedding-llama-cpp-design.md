# OpenViking 本地 Embedding Llama-cpp 設計文件

Date: 2026-04-11
Status: 已批准進入實現

## 目標

為 OpenViking 增加內建的本地 dense embedding 能力，並滿足以下產品行為：

- 當用戶沒有顯式配置 `embedding` 時，OpenViking 預設使用本地 embedding backend
- 預設本地模型為 `bge-small-zh-v1.5-f16`
- 本地推理基於 `llama-cpp-python` 載入 GGUF 模型
- 本地推理依賴不放入主依賴，而是通過 optional extra 單獨分發，降低安裝風險

最終效果是：在不改變“預設走本地 embedding”這一產品目標的前提下，讓方案具備可實現性和可維護性。

## 範圍

本次設計包含：

- 新增 `embedding.backend = "local"` backend
- 當用戶未提供 embedding 配置時，自動生成隱式本地 embedding 配置
- 基於 `llama-cpp-python` 的 dense embedder
- 預設模型 `bge-small-zh-v1.5-f16`
- 模型路徑解析、下載和快取目錄管理
- query/document 雙路編碼語義
- collection 後設資料校驗和 rebuild 規則
- 啟動期校驗與錯誤提示
- 測試方案和 benchmark 預留

本次設計不包含：

- 本地 sparse embedding
- 本地 hybrid embedding
- 本地失敗後靜默回退到遠端 provider
- 執行時自動安裝依賴
- 替換現有遠端 provider

## 決策摘要

OpenViking 採用以下組合策略：

1. 產品預設行為：如果使用者沒有配置 embedding，OpenViking 會隱式選擇本地 embedding backend。
2. 依賴分發策略：`llama-cpp-python` 不進入主依賴，而是通過 `openviking[local-embed]` 之類的 optional extra 分發。
3. 預設本地模型：`bge-small-zh-v1.5-f16`。
4. 失敗策略：如果系統預設選擇了本地 embedding，但本地依賴或模型不可用，則直接報錯，並給出清晰恢復指引；不會靜默回退到遠端模型。

這和 QMD 的做法不完全相同。QMD 是 Node CLI 產品，可以把 `node-llama-cpp` 作為主依賴；而 OpenViking 是 Python SDK 和服務元件，如果讓原生依賴阻斷主包安裝，代價會更高。

## 為什麼這樣設計

調研結論和當前程式碼約束基本指向同一個方向：

- QMD 證明了“預設本地 embedding”這個產品方向是成立的。
- OpenClaw / ArkClaw 證明了基於 GGUF 的本地 memory search 有明確使用者價值。
- OpenViking 當前架構決定了 embedding 初始化失敗會在啟動期暴露，而不是延後到查詢時。
- 在 Python 生態裡，原生依賴失敗的成本通常比 QMD 所在的 npm/Node 生態更高。

因此，這個設計是在保留產品目標的前提下，儘量縮小原生依賴失敗的影響範圍。

## 使用者可見行為

### 預設行為

如果配置中沒有 `embedding`：

- OpenViking 自動生成一份隱式 local dense embedding 配置
- backend 設定為 `local`
- model 設定為 `bge-small-zh-v1.5-f16`
- dimension 設定為該模型對應維度

使用者應感知到的行為是：“本地 embedding 是預設值”。

### 顯式行為

如果使用者顯式配置了 `embedding`，則始終以顯式配置為準，包括：

- 顯式 `backend: "local"`
- 顯式遠端 backend，例如 `openai`、`volcengine`、`vikingdb`
- 顯式 `model_path`
- 顯式 `cache_dir`

不應存在覆蓋使用者配置的隱式重寫。

### 安裝體驗

基礎安裝：

```bash
pip install openviking
```

啟用本地 embedding：

```bash
pip install "openviking[local-embed]"
```

如果使用者依賴預設本地行為，但沒有安裝 local extra，系統必須在啟動時給出可執行的錯誤提示，至少包含：

- 當前預設啟用了本地 embedding
- 缺少 `llama-cpp-python`
- 啟用本地 embedding 的安裝命令
- 如果使用者想改成遠端 provider，應如何顯式配置

## 配置設計

在 `EmbeddingModelConfig` 中新增 `local` 作為合法 backend。

本地 dense backend 支持的字段：

- `backend`: `"local"`
- `model`: 邏輯模型名，預設 `bge-small-zh-v1.5-f16`
- `model_path`: 可選，顯式指定 GGUF 檔案路徑
- `cache_dir`: 可選，快取根目錄，預設 `~/.cache/openviking/models/`
- `dimension`: 可選，但通常應由內建模型登錄檔推導
- `batch_size`: 預留給後續批次 embedding

建議配置示例：

```json
{
  "embedding": {
    "dense": {
      "backend": "local",
      "model": "bge-small-zh-v1.5-f16",
      "cache_dir": "~/.cache/openviking/models"
    }
  }
}
```

顯式模型路徑示例：

```json
{
  "embedding": {
    "dense": {
      "backend": "local",
      "model": "bge-small-zh-v1.5-f16",
      "model_path": "/data/models/bge-small-zh-v1.5-f16.gguf"
    }
  }
}
```

## 架構設計

### 新增元件

新增一個本地 dense embedder 實現，例如：

- `openviking/models/embedder/local_embedders.py`
- `LocalDenseEmbedder`

其職責包括：

- 校驗 `llama-cpp-python` 是否可用
- 將邏輯模型名解析為 GGUF 模型規格
- 解析或下載模型檔案
- 初始化 llama embedding context
- 提供 query/document 雙路 embedding 方法
- 返回模型維度
- 在 `close()` 時釋放本地資源

### Factory 與配置改造

需要修改：

- `EmbeddingModelConfig.validate_config()` 以接受 `backend == "local"`
- `EmbeddingConfig._create_embedder()` 以支持 `("local", "dense")`
- 預設配置生成邏輯，使“缺失 embedding 配置”自動變成 local dense

### 模型登錄檔

新增一個內建本地模型登錄檔。第一版可以先做成簡單對映，按邏輯模型名索引：

- 邏輯模型名
- GGUF 下載 URL 或 HuggingFace 定位資訊
- 預期維度
- 推薦 prompt 規則
- 可選的目標檔名

首個內建模型為：

- `bge-small-zh-v1.5-f16`

## Query / Document 雙路編碼

這部分不是可選最佳化，而是本方案必須處理的設計點。

BGE/E5 一類模型是檢索導向模型，通常需要區分：

- query：使用者輸入的搜尋詞或問題
- document：被儲存和檢索的文本塊

OpenViking 當前只有 `embed(text)`，這不足以表達這種語義差異。

設計上新增顯式介面：

- `embed_query(text: str) -> EmbedResult`
- `embed_document(text: str) -> EmbedResult`

為了相容現有程式碼，`embed(text)` 可以保留為一個薄封裝，但內部必須帶角色語義。新的檢索程式碼應呼叫 `embed_query()`，新的入庫程式碼應呼叫 `embed_document()`。

query/document 的格式規則必須封裝在本地 embedder 內部，而不是散落在業務層拼裝。

## 模型解析與下載流程

### 解析順序

1. 如果配置了 `model_path`，直接使用該路徑。
2. 否則通過內建本地模型登錄檔解析 `model`。
3. 如果目標檔案不存在，則下載到 `cache_dir`。
4. 用解析後的 GGUF 檔案初始化 `llama-cpp-python`。

### 快取目錄

預設目錄：

- `~/.cache/openviking/models/`

行為要求：

- 目錄不存在時自動建立
- 下載後的 GGUF 檔案儲存在這裡
- 如果目標檔案已存在，則不重複下載

### 下載策略

第一版需要支持：

- 可讀性好的錯誤輸出
- 穩定可預測的檔案命名
- 失敗後可手動重試

第一版暫不要求：

- 斷點續傳
- 多映象源自動切換
- 後臺非同步下載器

## 啟動時機與失敗行為

OpenViking 當前在 client 啟動時就初始化 embedder，本地方案保持這一行為。

因此，下面這些問題都會在啟動期直接暴露：

- 沒有安裝 local extra
- `llama-cpp-python` import 失敗
- 模型檔案缺失且下載失敗
- GGUF 檔案存在但載入失敗
- 當前 collection 後設資料與配置模型不一致

### 錯誤處理規則

缺少本地依賴：

- 直接丟擲明確的配置/執行時錯誤
- 錯誤資訊中必須包含：缺失包名、安裝命令、切換遠端 provider 的方法

模型下載失敗：

- 丟擲包含邏輯模型名、解析 URL、快取目錄和原始異常的錯誤

模型載入失敗：

- 丟擲 GGUF 不相容、檔案損壞或當前執行環境不支援的錯誤

後設資料不一致：

- 丟擲“當前 embedding 設定與已有索引不相容，需要 rebuild”的錯誤

不允許靜默回退：

- 本地初始化失敗時，不得悄悄切換到 `openai`、`volcengine` 或 `vikingdb`

## Collection 後設資料與重建規則

當前系統只在寫入時校驗向量維度，這在本地模型成為預設值之後是不夠的。

需要至少持久化以下後設資料：

- `embedding_backend`
- `embedding_model`
- `embedding_dimension`
- `embedding_model_identity`

其中 `embedding_model_identity` 用於區分“看起來模型名相同，但實際模型檔案不同”的情況，可以採用：

- 解析後的模型路徑
- 模型路徑雜湊
- 文件哈希（如果成本可接受）

### 重建觸發條件

只要以下任一項發生變化：

- backend
- model
- dimension
- model identity

都應判定現有向量不可相容。系統需要：

- 在啟動時直接報錯並提示 rebuild，或
- 在使用者顯式觸發時執行 rebuild 流程

第一版建議採用顯式 rebuild，而不是隱式遷移。

## 資料流改造

### 入庫流程

當前流程：

- 語義處理得到文本
- 佇列消費者呼叫 `embed()`

改造後流程：

- 佇列消費者呼叫 `embed_document()`
- 本地 embedder 自動套用 document 側規則
- 向量寫入時附帶與當前模型一致的 collection 後設資料

### 檢索流程

當前流程：

- retriever 呼叫 `embed()`

改造後流程：

- retriever 呼叫 `embed_query()`
- 本地 embedder 自動套用 query 側規則
- 檢索時使用與 document 同體系生成的向量

## 開發順序

1. 增加 `local` backend 的配置校驗和 factory 註冊。
2. 增加“缺失 embedding 配置時預設生成 local dense 配置”的邏輯。
3. 實現基於 `llama-cpp-python` 的 `LocalDenseEmbedder`。
4. 增加內建本地模型登錄檔，並接入 `bge-small-zh-v1.5-f16`。
5. 增加模型路徑解析、快取目錄和自動下載邏輯。
6. 增加 `embed_query()` / `embed_document()` 雙路介面。
7. 持久化 collection embedding 後設資料，並補一致性檢查。
8. 增加 rebuild-required 錯誤流。
9. 更新使用者文件、示例配置和安裝說明。

## 測試計劃

### 配置測試

- 缺失 `embedding` 時自動生成隱式 local dense 配置
- 顯式遠端配置時不觸發預設本地邏輯
- `model_path` 能覆蓋邏輯模型解析
- `cache_dir` 覆蓋生效

### 依賴與初始化測試

- 缺少 `llama-cpp-python` 時，啟動錯誤資訊正確
- 顯式 local backend 且依賴已安裝時可成功初始化
- 非法 GGUF 路徑會觸發模型載入失敗
- 下載失敗時錯誤資訊完整可讀

### Embedding 行為測試

- `embed_query()` 與 `embed_document()` 走不同路徑
- 返回維度與模型維度一致

### 後設資料與重建測試

- 首次啟動時能生成和當前模型一致的後設資料
- 改變 model identity 時會觸發需要重建
- 改變 dimension 時會觸發需要重建

### 檢索迴歸測試

- 中文 query 能正確召回中文文件
- query/document 雙路編碼不會破壞現有檢索鏈路
- 現有遠端 provider 行為保持不變

### 打包測試

- `pip install openviking` 可以在不安裝本地依賴的情況下成功
- `pip install "openviking[local-embed]"` 可以啟用本地 import 路徑
- 缺少 extra 且觸發預設本地行為時，報錯應明確，而不是模糊 import failure

## 基準測試

至少記錄以下指標：

- 依賴已安裝且模型已快取時的啟動耗時
- 首次下載模型時的啟動耗時
- 單條 embedding 延遲
- 批次 embedding 延遲
- 在代表性中文語料上的索引構建吞吐

在 benchmark 出來之前，不應假設“預設本地 embedding”在所有環境裡都同樣合適。

## 運維說明

推薦安裝命令：

```bash
pip install "openviking[local-embed]"
```

如果使用者想使用遠端 embedding：

- 顯式配置 `embedding.dense.backend`
- 提供相應 provider 的憑證

## 風險

- 原生依賴安裝失敗
- 預編譯 wheel 覆蓋不足
- GGUF 與執行時版本不相容
- 使用者預期“零配置”但實際缺少 local extra
- 模型切換後索引不相容
- 未做批次聚合時索引吞吐偏低

## 交付物

- 本地 dense embedder 實現
- local backend 配置與 factory 整合
- 內建模型登錄檔
- 啟動期錯誤提示與安裝指引
- collection 後設資料校驗
- rebuild-required 機制
- 測試和 benchmark 腳手架
- 使用者文件更新
