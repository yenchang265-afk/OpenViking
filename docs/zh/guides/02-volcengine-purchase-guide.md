# 火山引擎模型購買指南

本指南介紹如何在火山引擎購買和配置 OpenViking 所需的模型服務。

## 概述

OpenViking 需要以下模型服務：

| 模型型別 | 用途 | 推薦模型 |
|---------|------|---------|
| VLM（視覺語言模型） | 內容理解、語義生成 | `doubao-seed-2-0-lite-260428` |
| Embedding | 向量化、語義檢索 | `doubao-embedding-vision-251215` |

## 前置條件

- 有效的手機號或郵箱
- 完成實名認證（個人或企業）

## 購買流程

### 1. 註冊帳號

訪問 [火山引擎官網](https://www.volcengine.com/)：

1. 點選右上角"登入/註冊"
2. 選擇註冊方式（手機號/郵箱）
3. 完成驗證並設定密碼
4. 進行實名認證


### 2. 開通火山方舟

火山方舟是火山引擎的 AI 模型服務平臺。

#### 訪問控制台

1. 登入後進入[控制台](https://console.volcengine.com/)
2. 搜索"火山方舟"
3. 點選進入[火山方舟控制台](https://console.volcengine.com/ark/region:ark+cn-beijing/model)
4. 首次使用需要點選"開通服務"並同意協議

### 3. 建立 API Key

訪問：[API Key 管理頁面](https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey)

所有模型呼叫都需要 API Key。

1. 在火山方舟左側導航欄選擇 **"API Key 管理"**
2. 點選 **"建立 API Key"**
3. 複製儲存API Key以用於後續配置

<div align="center">
<img src="../../images/create_api_key.gif" width="80%">
</div>


### 4. 開通 VLM 模型

訪問：[模型管理頁面](https://console.volcengine.com/ark/region:ark+cn-beijing/model)

1. 在左側導航欄選擇 **"開通管理"**
2. 選擇 **"語言模型"** 一列
3. 找到 **Doubao-Seed-2.0** 模型
4. 點選"開通"按鈕
5. 確認付費方式

<div align="center">
<img src="../../images/activate_vlm_model.gif" width="80%">
</div>

開通後可直接使用模型 ID：`doubao-seed-2-0-lite-260428`

### 5. 開通 Embedding 模型

訪問：[模型管理頁面](https://console.volcengine.com/ark/region:ark+cn-beijing/model)

1. 在左側導航欄選擇 **"開通管理"**
2. 選擇 **"向量模型"** 一列
3. 找到 **Doubao-Embedding-Vision** 模型
4. 點選"開通"
5. 確認付費方式

<div align="center">
<img src="../../images/activate_emb_model.gif" width="80%">
</div>

開通後使用模型 ID：`doubao-embedding-vision-251215`

## 配置 OpenViking

### 配置模板

建立 `~/.openviking/ov.conf` 檔案，使用以下模板：

```json
{
  "vlm": {
    "provider": "<provider-type>",
    "api_key": "<your-api-key>",
    "model": "<model-id>",
    "api_base": "<api-endpoint>",
    "temperature": <temperature-value>,
    "max_retries": <retry-count>
  },
  "embedding": {
    "dense": {
      "provider": "<provider-type>",
      "api_key": "<your-api-key>",
      "model": "<model-id>",
      "api_base": "<api-endpoint>",
      "dimension": <vector-dimension>,
      "input": "<input-type>"
    }
  }
}
```

### 配置欄位說明

#### VLM 配置字段

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `provider` | string | 是 | 模型服務提供商，火山引擎填 `"volcengine"` |
| `api_key` | string | 是 | 火山方舟 API Key |
| `model` | string | 是 | 模型 ID，如 `doubao-seed-2-0-lite-260428` |
| `api_base` | string | 否 | API 端點地址，預設為北京區域端點，具體可見附錄-區域端點 |
| `temperature` | float | 否 | 生成溫度，控制輸出隨機性，範圍 0-1，推薦 0.1 |
| `max_retries` | int | 否 | 請求失敗時的重試次數，推薦 3 |

#### Embedding 配置字段

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `provider` | string | 是 | 模型服務提供商，火山引擎填 `"volcengine"` |
| `api_key` | string | 是 | 火山方舟 API Key |
| `model` | string | 是 | 模型 ID，如 `doubao-embedding-vision-251215` |
| `api_base` | string | 否 | API 端點地址，預設為北京區域端點，具體可見附錄-區域端點 |
| `dimension` | int | 是 | 向量維度，取決於模型（通常為 1024 或 768） |
| `input` | string | 否 | 輸入型別：`"multimodal"`（多模態）或 `"text"`（純文本），預設`"multimodal"` |

### 配置示例

將以下內容儲存為 `~/.openviking/ov.conf`：

```json
{
  "vlm": {
    "provider": "volcengine",
    "api_key": "sk-1234567890abcdef1234567890abcdef",
    "model": "doubao-seed-2-0-lite-260428",
    "api_base": "https://ark.cn-beijing.volces.com/api/v3",
    "temperature": 0.1,
    "max_retries": 3
  },
  "embedding": {
    "dense": {
      "provider": "volcengine",
      "api_key": "sk-1234567890abcdef1234567890abcdef",
      "model": "doubao-embedding-vision-251215",
      "api_base": "https://ark.cn-beijing.volces.com/api/v3",
      "dimension": 1024,
      "input": "multimodal"
    }
  }
}
```

> ⚠️ **注意**：請將示例中的 `api_key` 替換為你在第 3 步獲取的真實 API Key！

## 驗證配置

### 測試連線

```python
import asyncio
from openviking_sdk import AsyncHTTPClient

async def test():
    client = AsyncHTTPClient(url="http://localhost:1933", api_key="your-key")
    await client.initialize()

    # 新增簡單資源測試
    result = await client.add_resource(
        path="https://example.com",
        options={"reason": "測試連線"},
    )
    print(f"✓ 配置成功: {result['root_uri']}")

    await client.close()

asyncio.run(test())
```

### 檢視使用情況

在火山方舟控制台：

1. 訪問 **"概覽"** 頁面
2. 檢視 **Token 消耗統計**
3. 在 **"費用中心"** 檢視帳單明細

## 費用說明

### 計費方式

| 模型型別 | 計費單位 |
|---------|---------|
| VLM | 按輸入/輸出 Token 計費 |
| Embedding | 按文本長度計費 |

### 免費額度

火山引擎為新使用者提供免費額度：

- 首次開通贈送 Token
- 足夠完成 OpenViking 的試用體驗
- 詳見：[火山方舟定價說明](https://www.volcengine.com/docs/82379/1399514)

## 故障排除

### 常見錯誤

#### API Key 無效

```
Error: Invalid API Key
```

**解決方法**：
1. 檢查 API Key 是否正確複製（完整的 `sk-` 開頭字串）
2. 確認 API Key 未被刪除或過期
3. 重新建立 API Key

#### 模型未開通

```
Error: Model not activated
```

**解決方法**：
1. 在火山方舟控制台檢查模型狀態
2. 確認模型處於"執行中"狀態
3. 檢查帳戶餘額是否充足

#### 網路連線問題

```
Error: Connection timeout
```

**解決方法**：
1. 檢查網路連線
2. 確認 `api_base` 配置正確
3. 如在海外，確認可訪問火山引擎服務
4. 增加配置中的超時時間

### 獲取幫助

- [火山引擎文件中心](https://www.volcengine.com/docs)
- [火山方舟 API 文件](https://www.volcengine.com/docs/82379)
- [OpenViking GitHub Issues](https://github.com/volcengine/OpenViking/issues)

## 相關文件

- [配置指南](./01-configuration.md) - 完整配置參考
- [快速開始](../getting-started/02-quickstart.md) - 開始使用 OpenViking

## 附錄

### 區域端點

| 區域 | API Base |
|------|----------|
| 北京 | `https://ark.cn-beijing.volces.com/api/v3` |
| 上海 | `https://ark.cn-shanghai.volces.com/api/v3` |

### 模型版本對照

| 模型名稱 | 當前版本 | 釋出日期 |
|---------|---------|---------|
| Doubao-Seed-2.0 | `doubao-seed-2-0-lite-260428` | 2025-12-28 |
| Doubao-Embedding-Vision | `doubao-embedding-vision-251215` | 2025-06-15 |

> 注：模型版本可能更新，請以火山方舟控制台顯示為準。
