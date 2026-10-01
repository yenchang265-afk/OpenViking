# VikingDB FastAPI Server

重構後的 VikingDB Collection Server，使用 FastAPI 替代 Flask。

## 檔案說明

- **app_models.py**: Pydantic 資料模型定義 (替代 Flask-RESTful 的 reqparse)
- **api_fastapi.py**: FastAPI 路由和 API 端點 (替代 Flask-RESTful 的 Resource 類)
- **server_fastapi.py**: FastAPI 主伺服器檔案 (替代 Flask 應用)

## 安裝依賴

```bash
pip install fastapi uvicorn pydantic
```

## 執行服務

### 方式 1: 直接執行
```bash
cd openviking/storage/vectordb/service
python server_fastapi.py
```

### 方式 2: 使用 uvicorn 執行
```bash
cd openviking/storage/vectordb/service
uvicorn server_fastapi:app --host 0.0.0.0 --port 5000 --reload
```

## 配置

### 環境變數
- `VIKINGDB_PERSIST_PATH`: 資料持久化路徑，預設為 `./vikingdb_data/`
  - 設定為空字串使用 volatile mode (記憶體模式)
  - 設定為路徑使用 persistent mode (持久化模式)

示例:
```bash
export VIKINGDB_PERSIST_PATH="./my_data_path/"
python server_fastapi.py
```

## API 文件

FastAPI 自動生成互動式 API 文件:

- **Swagger UI**: http://localhost:5000/docs
- **ReDoc**: http://localhost:5000/redoc

## API 端點

### Collection APIs
- `POST /CreateVikingdbCollection` - 建立 Collection
- `POST /UpdateVikingdbCollection` - 更新 Collection
- `GET /GetVikingdbCollection` - 獲取 Collection 資訊
- `GET /ListVikingdbCollection` - 列出所有 Collections
- `POST /DeleteVikingdbCollection` - 刪除 Collection

### Data APIs
- `POST /api/vikingdb/data/upsert` - 寫入/更新資料
- `GET /api/vikingdb/data/fetch_in_collection` - 獲取資料
- `POST /api/vikingdb/data/delete` - 刪除資料

### Index APIs
- `POST /CreateVikingdbIndex` - 建立索引
- `POST /UpdateVikingdbIndex` - 更新索引
- `GET /GetVikingdbIndex` - 獲取索引資訊
- `GET /ListVikingdbIndex` - 列出所有索引
- `POST /DeleteVikingdbIndex` - 刪除索引

### Search APIs
- `POST /api/vikingdb/data/search/vector` - 向量搜索
- `POST /api/vikingdb/data/search/id` - 通過 ID 搜尋
- `POST /api/vikingdb/data/search/multi_modal` - 多模態搜尋
- `POST /api/vikingdb/data/search/scalar` - 標量欄位搜尋
- `POST /api/vikingdb/data/search/random` - 隨機搜尋
- `POST /api/vikingdb/data/search/keywords` - 關鍵詞搜尋

### 健康檢查
- `GET /` - 根端點
- `GET /health` - 健康檢查端點

## 主要改進

### 1. 現代化框架
- 使用 FastAPI 替代 Flask，性能更好
- 支援非同步操作
- 自動生成 OpenAPI 文件

### 2. 型別安全
- 使用 Pydantic 模型進行請求驗證
- 自動型別檢查和資料驗證
- 更好的 IDE 支持

### 3. 更好的開發體驗
- 自動互動式 API 文件 (Swagger UI)
- 請求和響應的自動驗證
- 更清晰的錯誤訊息

### 4. 性能提升
- FastAPI 基於 Starlette 和 Pydantic，效能優於 Flask
- 支援非同步處理
- 更高效的請求處理

## 與原 Flask 版本的相容性

API 端點路徑和請求/響應格式與原 Flask 版本完全相容，可以無縫切換。

## 測試

使用 curl 測試:

```bash
# 建立 Collection
curl -X POST "http://localhost:5000/CreateVikingdbCollection" \
  -H "Content-Type: application/json" \
  -d '{
    "CollectionName": "test_collection",
    "ProjectName": "default",
    "Description": "Test collection",
    "Fields": "[{\"FieldName\":\"id\",\"FieldType\":\"int64\",\"IsPrimaryKey\":true},{\"FieldName\":\"text\",\"FieldType\":\"string\"}]"
  }'

# 獲取健康狀態
curl "http://localhost:5000/health"
```

使用 Python requests:

```python
import requests
import json

# 建立 Collection
response = requests.post(
    "http://localhost:5000/CreateVikingdbCollection",
    json={
        "CollectionName": "test_collection",
        "ProjectName": "default",
        "Description": "Test collection",
        "Fields": json.dumps([
            {
                "FieldName": "id",
                "FieldType": "int64",
                "IsPrimaryKey": True
            },
            {
                "FieldName": "text",
                "FieldType": "string"
            }
        ])
    }
)
print(response.json())
```
