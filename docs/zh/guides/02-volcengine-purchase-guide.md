# 火山引擎模型購買指南

本指南適用於自建 OpenViking：開通火山方舟模型、取得 API Key，並驗證服務端配置。使用託管 OpenViking 時，無需在客戶端配置這些模型，見[快速開始](../getting-started/02-quickstart.md)。

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

以下模板說明配置結構；替換所有字串佔位值後再使用。已有配置時只更新相關段落，保留儲存、認證等其他配置：

```json
{
  "vlm": {
    "provider": "<provider-type>",
    "api_key": "<your-api-key>",
    "model": "<model-id>",
    "api_base": "<api-endpoint>",
    "temperature": 0.1,
    "max_retries": 3
  },
  "embedding": {
    "dense": {
      "provider": "<provider-type>",
      "api_key": "<your-api-key>",
      "model": "<model-id>",
      "api_base": "<api-endpoint>",
      "dimension": 1024,
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
| `temperature` | float | 否 | 生成溫度；支援範圍取決於模型，本例使用 0.1 |
| `max_retries` | int | 否 | 請求失敗時的重試次數，推薦 3 |

#### Embedding 配置字段

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `provider` | string | 是 | 模型服務提供商，火山引擎填 `"volcengine"` |
| `api_key` | string | 是 | 火山方舟 API Key |
| `model` | string | 是 | 模型 ID，如 `doubao-embedding-vision-251215` |
| `api_base` | string | 否 | API 端點地址，預設為北京區域端點，具體可見附錄-區域端點 |
| `dimension` | int | 是 | 向量維度，必須與模型輸出及索引一致；本例選擇 1024 |
| `input` | string | 否 | 輸入型別：`"multimodal"`（多模態）或 `"text"`（純文本），預設`"multimodal"` |

### 配置示例

將以下模型段落寫入 `~/.openviking/ov.conf`，並保留已有的其他配置：

```json
{
  "vlm": {
    "provider": "volcengine",
    "api_key": "your-ark-api-key",
    "model": "doubao-seed-2-0-lite-260428",
    "api_base": "https://ark.cn-beijing.volces.com/api/v3",
    "temperature": 0.1,
    "max_retries": 3
  },
  "embedding": {
    "dense": {
      "provider": "volcengine",
      "api_key": "your-ark-api-key",
      "model": "doubao-embedding-vision-251215",
      "api_base": "https://ark.cn-beijing.volces.com/api/v3",
      "dimension": 1024,
      "input": "multimodal"
    }
  }
}
```

將兩處 `your-ark-api-key` 替換為第 3 步取得的 API Key。這裡是模型憑據，與連線 OpenViking Server 的 user/admin key 不同。

## 驗證配置

### 測試連線

先檢查模型配置，再啟動服務：

```bash
openviking-server doctor
openviking-server
```

另開終端，按[快速開始](../getting-started/02-quickstart.md)配置 CLI 並建立其中的 `quickstart.md`，然後匯入到未使用的目錄：

```bash
ov add-resource ./quickstart.md --to viking://resources/model-check --wait
ov find "誰負責備份流程？" --uri viking://resources/model-check
```

匯入請求被接受不代表模型配置驗證成功。等任務完成後再檢索；超時可通過返回的 task ID 查詢進度，失敗則檢視任務錯誤。

### 檢視使用情況

在火山方舟控制台：

1. 訪問 **"概覽"** 頁面
2. 檢視 **Token 消耗統計**
3. 在 **"費用中心"** 檢視帳單明細

## 費用說明

### 計費方式

| 模型型別 | 計費單位 |
|---------|---------|
| VLM | 所選模型的輸入/輸出計費規則見[方舟價格說明](https://www.volcengine.com/product/ark) |
| Embedding | 所選模型及輸入模態的計費規則見[方舟價格說明](https://www.volcengine.com/product/ark) |

### 免費額度

是否有贈送額度、適用模型、有效期及超額計費方式，以帳戶控制台和[火山方舟價格說明](https://www.volcengine.com/product/ark)為準。先用小文件觀察實際 token 消耗，再估算批次匯入成本；免費額度不保證覆蓋任意規模的試用。

## 故障排除

### 常見錯誤

#### API Key 無效

```
Error: Invalid API Key
```

**解決方法**：
1. 檢查 API Key 是否完整複製、有無多餘空格
2. 確認 API Key 未被刪除或過期
3. 重新建立 API Key

#### 模型未開通

```
Error: Model not activated
```

**解決方法**：
1. 在火山方舟控制台檢查模型狀態
2. 確認所選模型 ID 對當前帳號可用
3. 檢查帳戶餘額是否充足

#### 網路連線問題

```
Error: Connection timeout
```

**解決方法**：
1. 檢查網路連線
2. 確認 `api_base` 配置正確
3. 如在海外，確認可訪問火山引擎服務
4. 服務可達但處理較慢時，再按[配置指南](01-configuration.md)調整相應超時

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

本文使用官方示例中的北京端點。其他地域請複製控制台給出的模型呼叫地址，不要只替換域名中的地域字串。

### 模型版本對照

| 用途 | 本文示例模型 ID |
| --- | --- |
| VLM | `doubao-seed-2-0-lite-260428` |
| Embedding | `doubao-embedding-vision-251215` |

這些是示例版本，不代表最新版本。可用版本見[方舟模型釋出記錄](https://docs.volcengine.com/docs/ark/model-release-announcement?lang=zh)，Embedding 的輸入和維度配置見[向量化文件](https://docs.volcengine.com/docs/ark/vectorization?lang=zh)。更換 Embedding 模型前，應檢查現有索引是否需要重建。
