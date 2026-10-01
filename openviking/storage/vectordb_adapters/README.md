# VectorDB Adapter 接入指南（新增第三方後端）

本指南說明如何在 `openviking/storage/vectordb_adapters` 下新增一個第三方向量庫後端，並接入 OpenViking 現有檢索鏈路。

---

## 1. 目標與範圍

### 目標
- 以最小改動新增一個向量庫後端。
- 保持上層業務介面不變（`find/search` 等無需改呼叫方式）。
- 將後端差異封裝在 Adapter 層，不洩漏到業務層。

### 非目標
- 不改上層語義檢索策略（租戶、目錄層級、召回策略）。
- 不增加新的對外 API 協議。

---

## 2. 架構位置與職責

當前分層職責如下：

1. **上層語義層（OpenViking 業務）**  
   面向語義介面，不關心後端協議差異。

2. **通用向量儲存層（Store/Backend）**  
   提供統一查詢、寫入、刪除、計數能力。

3. **Adapter 層（本目錄）**  
   負責把統一能力對映到具體後端實現（local/http/volcengine/vikingdb/thirdparty）。

新增後端時，主要只改第 3 層。

---

## 3. 接入前提

在開始前，請確認：

- 你已拿到第三方後端的：
  - 集合管理 API（查/建/刪集合）
  - 資料 API（upsert/get/delete/search/aggregate）
- 你已明確該後端的：
  - 認證方式（AK/SK、token、header）
  - 過濾語法能力（是否支援 must/range/and/or）
  - 索引引數約束（dense/sparse、距離度量、索引型別）

---

## 4. 接入步驟

## Step 1：新增 Adapter 文件

在目錄下新增檔案，例如：

- `openviking/storage/vectordb_adapters/thirdparty_adapter.py`

定義類：

- `ThirdPartyCollectionAdapter(CollectionAdapter)`

基類位於：

- `openviking/storage/vectordb_adapters/base.py`

---

## Step 2：實現最小必需方法

你需要實現以下方法：

1. `from_config(cls, config)`  
   - 從 `VectorDBBackendConfig` 讀取後端配置並構造 adapter。
   - collection 名建議使用 `config.name or "context"`。

2. `_load_existing_collection_if_needed(self)`  
   - 懶載入已存在 collection handle。
   - 若不存在，保持 `_collection is None`。

3. `_create_backend_collection(self, meta)`  
   - 按傳入 schema 建立 collection 並返回 handle。

---

## Step 3：按後端能力補充可選 Hook

如後端有差異，可重寫：

- `_sanitize_scalar_index_fields(...)`
- `_build_default_index_meta(...)`

若後端支援服務端全文檢索（BM25 grep）並需要寫入 `content` 全文欄位，設定類屬性：

- `USE_CONTENT_FIELD = True`（預設為 `False`）

預設 `False` 時，寫入時會自動跳過 `content` 欄位（該欄位僅 VikingDB 系後端使用），新增後端無需額外程式碼。

目的：把後端特性差異收斂在 adapter 內。

---

## Step 4：註冊到 Factory

編輯：

- `openviking/storage/vectordb_adapters/factory.py`

在 `_ADAPTER_REGISTRY` 增加映射，例如：

```python
"thirdparty": ThirdPartyCollectionAdapter
```

這樣 `create_collection_adapter(config)` 會自動路由到你的實現。

---

## Step 5：補充配置模型

確保配置中可宣告新 backend（如 `backend: thirdparty`）及其專屬欄位（endpoint/auth/region 等）。

原則：
- `create_collection` 時使用配置中的 name 繫結 collection。
- 後續操作預設繫結，不需要每次傳 collection_name。

---

## Step 6：配置 ov.conf

對於沒有提交到倉庫，或者在第三方倉庫的 Adapter，可以通過配置 `backend` 為完整的類路徑來動態載入。
同時，可以使用 `custom_params` 欄位傳遞自定義引數。

在 `ov.conf`  中添加如下配置：

```json
{
  "storage": {
    "vectordb": {
      "backend": "tests.storage.mock_backend.MockCollectionAdapter",
      "name": "mock_test_collection",
      "custom_params": {
        "custom_param1": "val1",
        "custom_param2": 123
      }
    }
  }
}
```

注意：
1. `backend`: 填寫 Adapter 類的完整 Python 路徑（例如 `my_project.adapters.MyAdapter`）。
2. `custom_params`: 這是一個字典，你可以放入任何自定義引數，Adapter 的 `from_config` 方法可以通過 `config.custom_params` 獲取這些值。



---

## 5. Filter 與查詢相容規則

- Adapter 需要相容統一過濾表達。
- 上層傳入的過濾表達會經由統一編譯流程進入後端查詢。
- 若第三方語法不同，請在 adapter 內做對映，不改上層呼叫協議。

關鍵原則：
- **後端 DSL 不上浮到業務層**。
- **業務層不依賴第三方私有查詢語法**。

---

## 6. 最小程式碼骨架（示例）

```python
from __future__ import annotations
from typing import Any, Dict

from openviking.storage.vectordb_adapters.base import CollectionAdapter

class ThirdPartyCollectionAdapter(CollectionAdapter):
    def __init__(self, *, endpoint: str, token: str, collection_name: str):
        super().__init__(collection_name=collection_name)
        self.mode = "thirdparty"
        self._endpoint = endpoint
        self._token = token

    @classmethod
    def from_config(cls, config: Any):
        if not config.thirdparty or not config.thirdparty.endpoint:
            raise ValueError("ThirdParty backend requires endpoint")
        return cls(
            endpoint=config.thirdparty.endpoint,
            token=config.thirdparty.token,
            collection_name=config.name or "context",
        )

    def _load_existing_collection_if_needed(self) -> None:
        if self._collection is not None:
            return
        # TODO: 查詢遠端 collection 是否存在，存在則初始化 handle
        # self._collection = ...
        pass

    def _create_backend_collection(self, meta: Dict[str, Any]):
        # TODO: 調後端 create collection，並返回 collection handle
        # return ...
        raise NotImplementedError
```

---

## 7. 測試要求（必須）

至少覆蓋以下場景：

1. backend 工廠路由正確（能建立到新 adapter）。
2. collection 生命週期可用（exists/create/drop）。
3. 基礎資料鏈路可用（upsert/get/delete/query）。
4. count/aggregate 行為正確。
5. filter 條件可正確生效（含組合條件）。

---

## 8. 常見問題與排查

### Q1：啟動時報 backend 不支援
- 檢查 factory 是否註冊。
- 檢查配置裡的 backend 字串是否與 registry key 一致。

### Q2：集合建立成功但查詢為空
- 檢查 collection 繫結名是否一致。
- 檢查索引是否建立成功。
- 檢查 filter 對映是否把條件誤轉成空條件。

### Q3：count 與 query 條數不一致
- 檢查 aggregate API 的欄位命名與返回結構解析。
- 檢查 count 使用的 filter 與 query 使用的 filter 是否一致。

---

## 9. 驗收標準

當滿足以下條件，即可視為接入完成：

- `backend=thirdparty` 可正常初始化。
- create 後可完成 upsert/get/query/delete/count 全流程。
- 不改上層業務呼叫方式即可參與 `find/search` 檢索鏈路。
- 後端差異全部封裝在 adapter 層。