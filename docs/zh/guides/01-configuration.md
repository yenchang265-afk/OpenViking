# 配置模型與服務

本文用於選擇模型、組合配置示例和理解生效範圍。只查欄位時，請看[服務端配置欄位](../configuration/01-server.md)或[客戶端配置欄位](../configuration/02-client.md)；首次部署從[部署路徑](00-overview.md)開始。

OpenViking 使用 JSON 配置檔案（`ov.conf`）進行設定。配置檔案支援 Embedding、VLM、Rerank、儲存、解析器等多個模組的配置。

本頁供配置服務端時查閱。只連線已有服務端時，使用 [CLI 配置指南](../getting-started/05-cli-setup.md)，無需在客戶端配置模型或儲存。

首次配置可以執行下面的嚮導。已有配置時，按要調整的能力查詢對應段落，將示例欄位合併到現有 JSON 物件中；不要用一個區域性示例覆蓋整份檔案。修改 `ov.conf` 後需重啟服務，執行時可修改的少數字段見下文。

首次配置推薦優先使用：

```bash
openviking-server init
openviking-server doctor
```

`openviking-server init` 會分別引導你填寫 Embedding 和 VLM 的配置。對於 `OpenAI`、`Volcengine`、`Kimi`、`GLM` 這類 API 型 VLM，按提示填寫對應的 VLM API Key；如果要使用 Codex 作為 VLM，請選擇 `OpenAI Codex`，嚮導會自動幫你處理已有 Codex 鑑權的匯入，或直接引導你完成登入。

## 快速開始

在使用者配置目錄 `~/.openviking/` 下建立 `ov.conf`：

```json
{
  "service_name": "openviking-server",
  "storage": {
    "workspace": "./data",
    "vectordb": {
      "name": "context",
      "backend": "local"
    },
    "agfs": {
      "backend": "local"
    }
  },
  "embedding": {
    "dense": {
      "api_base" : "<api-endpoint>",
      "api_key"  : "<your-api-key>",
      "provider" : "<provider-type>",
      "dimension": 1024,
      "model"    : "<model-name>"
    }
  },
  "vlm": {
    "api_base" : "<api-endpoint>",
    "api_key"  : "<your-api-key>",
    "provider" : "<provider-type>",
    "model"    : "<model-name>"
  }
}

```

如果 `provider` 是 `openai-codex`，並且 Codex OAuth 已經就緒，則 `vlm.api_key` 可以省略。

頂層 `service_name` 預設是 `"openviking-server"`。使用 cache 的模組會把它作為
Redis 名稱空間。OTel 的 `service_name` 顯式配置時保持原值，省略時繼承該值。

### ov.conf 的有序憑據陣列

`vlm` 和 `query_planner` 支援有序的 `credentials` 陣列；Embedding 在已配置的 `dense`、`sparse` 或 `hybrid` 節內支援同樣的陣列。索引 0 優先順序最高，後續元素提供故障切換憑據。模型配置節仍是 JSON 物件，原有單憑據配置繼續相容。

將以下欄位合併到你的 `ov.conf`，並在啟動服務前設定 `PRIMARY_API_KEY` 和 `BACKUP_API_KEY`：

```json
{
  "vlm": {
    "model": "your-vlm-model",
    "credentials": [
      {"id": "primary", "provider": "openai", "api_key": "${PRIMARY_API_KEY}"},
      {"id": "backup", "provider": "openai", "api_key": "${BACKUP_API_KEY}"}
    ]
  },
  "embedding": {
    "dense": {
      "model": "text-embedding-3-small",
      "dimension": 1536,
      "credentials": [
        {"id": "primary", "provider": "openai", "api_key": "${PRIMARY_API_KEY}"},
        {"id": "backup", "provider": "openai", "api_key": "${BACKUP_API_KEY}"}
      ]
    }
  }
}
```

每項憑據可以獨立指定 provider、模型及連線欄位；未指定模型時使用父級的 `model`。Embedding 憑據必須與父級模型的向量維度和輸入語義相容。`query_planner.credentials` 使用與 VLM 相同的格式。Rerank 仍使用單配置，不支援 `credentials` 陣列。

## 配置範圍與生效方式

OpenViking 的配置分為兩個層級：

- **啟動配置**從 `ov.conf` 讀取，用於定義程序基線和執行時配置源。修改後需要重啟服務；執行時配置介面不會改寫 `ov.conf`。
- **執行時配置**由配置源按 Cluster 和 Account 作用域分別持久化，可以通過 Admin API 修改。

只有顯式宣告為執行時欄位的配置，才會暴露在執行時配置 API 中。當前可修改範圍如下：

| 範圍 | 配置 | 生命週期 | 生效說明 |
| --- | --- | --- | --- |
| Cluster | `agent_evolution` | 動態配置 | ROOT 可通過 Admin API 修改，作為叢集預設值使用。 |
| Account | `agent_evolution` | 動態配置 | ROOT 或該 Account 的 ADMIN 可修改。Agent Evolution 為相容舊行為保留已廢棄的 Cluster 整段回退。 |
| Account | `github`、`acl` | 動態配置 | ROOT 或該 Account 的 ADMIN 可修改；不回退到 Cluster。 |
| Account | `vlm`、`query_planner` | 動態配置 | 僅 ROOT 可讀寫。每段已配置的模型配置都必須包含 `model` 和非空 `credentials` 陣列，`timeout` 可選；ADMIN 無法讀取或修改這兩段配置。 |
| Account | `embedding` | 部分動態 | 僅 ROOT 可讀寫。憑證、重試、併發、故障回切和熔斷引數可動態修改；模型身份、向量空間欄位、文本來源和輸入 token 上限僅能在建立時設定。 |
| Account | `vectordb` | 僅建立時配置 | 僅 ROOT 可在 Account 建立請求的 `settings` 中設定，後續新增、修改和重置均被拒絕。Account 專屬連線僅支援 `http` 遠端後端。 |

Cluster 的 `embedding`、`vlm`、`query_planner`、`memory`、儲存、解析器、檢索等普通配置仍然是啟動配置。Account 的 `memory` 不在當前 Account 配置 API 範圍內。

Account 與 Cluster 配置分別儲存和釋出。Account 未配置時是否使用 Cluster
屬於業務預設行為，不是配置框架中的隱式繼承。VLM 業務解析器負責這項策略：
Account 未配置 VLM 時使用 Cluster VLM；Account 已配置時，模型服務身份來自
Account，並按 VLM 業務規則組合部分 Cluster 執行引數。Account 設定 `timeout`
時覆蓋 Cluster 的值，未設定或重置後使用 Cluster 的值。Query Planner 的選擇順序為
Account `query_planner`、Account `vlm`、Cluster `query_planner`、Cluster `vlm`。

向量配置解析器會聯合校驗有效的 Embedding 和 VectorDB 配置。Account
`embedding: {}` 是合法配置；未宣告 Account 模型模式時使用 Cluster 模型繫結。
Account 憑證和顯式 VectorDB 連線必須獨立提供連線與鑑權欄位。遠端集合、索引和
訪問授權需要由外部預先建立。修改 embedding 憑證不會遷移歷史向量，呼叫方需要
保證模型相容。

處理 Account 業務的程式碼必須通過 `VLMResolver` 解析模型配置，並把得到的
`VLMConfig` 顯式傳給下層函式。`ClusterVLMResolver` 僅限啟動、診斷和離線評測
等依賴組裝入口使用。CI 架構測試會拒絕其他生產模組新增對 Cluster VLM
或 Query Planner 配置的直接讀取。

修改執行時配置使用以下介面：

```http
GET   /api/v1/admin/configuration
PATCH /api/v1/admin/configuration

GET   /api/v1/admin/accounts/{account_id}/configuration
PATCH /api/v1/admin/accounts/{account_id}/configuration
```

請求體使用 `settings` 包裝 PATCH 文件：

```json
{
  "settings": {
    "agent_evolution": {
      "enabled": true
    }
  }
}
```

PATCH 採用三態語義：欄位缺失表示不修改，具體值表示設定或替換，`null`
表示從當前作用域刪除該值。物件遞迴合併，陣列整體替換。響應只返回該作用域
的配置，不返回業務組合後的有效配置。宣告式 `fallback` 已廢棄，只支援整段
配置，且僅用於相容舊行為；新功能需要在業務解析器中實現 Cluster 預設值。
詳見 [Admin API - 執行時配置](../api/08-admin.md#runtime-configuration)。

## Account Embedding 與 VectorDB

ROOT 可在建立 Account 時配置 `settings.embedding` 和 `settings.vectordb`，
兩者使用 Account 專用白名單模型。Account 與 Cluster 配置分別儲存，向量業務
resolver 為 Account 未設定的值應用 Cluster 預設。Provider 連線只能通過完整
`credentials` binding 提交，不能跨 Account/Cluster 拼接。配置查詢只返回
Account 配置。

VectorDB 建立後不可修改。新舊 Account 均可輪換完整 Embedding
credentials/deployment binding，並更新重試、併發、failback 和熔斷引數；
外層 model 身份及其他向量空間欄位僅建立時可設。相容 endpoint 更新不打斷
在途呼叫，也不會自動重建歷史向量。

Account 獨立配置的 VectorDB 僅支援遠端 backend；Account 不能選擇 local/cuvs，
也不能設定本地路徑、cuVS 調優或自定義 adapter 引數。未設定 VectorDB 的
Account 複用 Cluster 連線並保留資料過濾。遠端資源由外部控制面提前建立。許可權與 PATCH 規則見
[Admin 配置 API](../api/08-admin.md#runtime-configuration)。

## 配置示例

<details>
<summary><b>火山引擎（豆包模型）</b></summary>

```json
{
  "embedding": {
    "dense": {
      "api_base" : "https://ark.cn-beijing.volces.com/api/v3",
      "api_key"  : "your-volcengine-api-key",
      "provider" : "volcengine",
      "dimension": 1024,
      "model"    : "doubao-embedding-vision-251215",
      "input": "multimodal"
    }
  },
  "vlm": {
    "api_base" : "https://ark.cn-beijing.volces.com/api/v3",
    "api_key"  : "your-volcengine-api-key",
    "provider" : "volcengine",
    "model"    : "doubao-seed-2-0-lite-260428"
  }
}
```

</details>

<details>
<summary><b>OpenAI 模型</b></summary>

```json
{
  "embedding": {
    "dense": {
      "api_base" : "https://api.openai.com/v1",
      "api_key"  : "your-openai-api-key",
      "provider" : "openai",
      "dimension": 1536,
      "model"    : "text-embedding-3-small"
    }
  },
  "vlm": {
    "api_base" : "https://api.openai.com/v1",
    "api_key"  : "your-openai-api-key",
    "provider" : "openai",
    "model"    : "gpt-5.4"
  }
}
```

</details>

<details>
<summary><b>火山引擎 Embedding + Codex VLM</b></summary>

使用 `openviking-server init` 完成 Codex 登入/匯入後，再執行 `openviking-server doctor`。

```json
{
  "embedding": {
    "dense": {
      "api_base" : "https://ark.cn-beijing.volces.com/api/v3",
      "api_key"  : "your-volcengine-api-key",
      "provider" : "volcengine",
      "dimension": 1024,
      "model"    : "doubao-embedding-vision-251215"
    }
  },
  "vlm": {
    "provider" : "openai-codex",
    "model"    : "gpt-5.6-terra",
    "api_base" : "https://chatgpt.com/backend-api/codex",
    "reasoning_effort": "xhigh"
  }
}
```

OpenAI 已於 2026 年 8 月 31 日[停止在 ChatGPT 登入的 Codex 中提供 `gpt-5.4`](https://learn.chatgpt.com/docs/models#deprecated-codex-models)。已有配置需將 `ov.conf` 中的 `vlm.model` 改為 `gpt-5.6-terra` 並重啟服務；升級 OpenViking 不會自動修改已儲存的模型設定。此次退役不影響使用 API Key 的 `provider: "openai"`。

</details>

<details>
<summary><b>火山引擎 Embedding + Kimi Coding VLM</b></summary>

```json
{
  "embedding": {
    "dense": {
      "api_base" : "https://ark.cn-beijing.volces.com/api/v3",
      "api_key"  : "your-volcengine-api-key",
      "provider" : "volcengine",
      "dimension": 1024,
      "model"    : "doubao-embedding-vision-251215"
    }
  },
  "vlm": {
    "provider" : "kimi",
    "model"    : "kimi-code",
    "api_key"  : "your-kimi-subscription-api-key",
    "api_base" : "https://api.kimi.com/coding"
  }
}
```

`kimi` 會自動應用 Kimi Coding 的預設配置，包括預設的 Kimi Coding User-Agent。

</details>

<details>
<summary><b>火山引擎 Embedding + GLM Coding Plan VLM</b></summary>

```json
{
  "embedding": {
    "dense": {
      "api_base" : "https://ark.cn-beijing.volces.com/api/v3",
      "api_key"  : "your-volcengine-api-key",
      "provider" : "volcengine",
      "dimension": 1024,
      "model"    : "doubao-embedding-vision-251215"
    }
  },
  "vlm": {
    "provider" : "glm",
    "model"    : "glm-4.6v",
    "api_key"  : "your-zai-api-key",
    "api_base" : "https://api.z.ai/api/coding/paas/v4"
  }
}
```

如果 OpenViking 需要處理圖片，請使用 `glm-4.6v` 或 `glm-5v-turbo` 這類支援視覺輸入的模型。

</details>

## 配置部分

### embedding

用於向量搜尋的 Embedding 模型配置，支援 dense、sparse 和 hybrid 三種模式。

#### Dense Embedding

```json
{
  "embedding": {
    "max_concurrent": 10,
    "max_retries": 3,
    "text_source": "content_only",
    "max_input_tokens": 4096,
    "dense": {
      "provider": "volcengine",
      "api_key": "your-api-key",
      "model": "doubao-embedding-vision-251215",
      "dimension": 1024,
      "input": "multimodal",
      "batch_size": 32
    }
  }
}
```

**引數**

| 引數 | 型別 | 說明 |
|------|------|------|
| `max_concurrent` | int | 最大併發 Embedding 請求數（`embedding.max_concurrent`，預設：`10`；必須 `>= 1`） |
| `max_retries` | int | Embedding provider 瞬時錯誤的最大重試次數（`embedding.max_retries`，預設：`3`；`0` 表示停用重試） |
| `text_source` | str | 文本檔案向量化時使用的文本來源。`content_only` 讀取原文內容；`summary_first` 優先使用摘要，沒有摘要時回退到原文；`summary_only` 已棄用，作為 `summary_first` 的相容別名；舊配置仍可載入，會記錄警告並歸一為 `summary_first`。預設：`content_only` |
| `max_input_tokens` | int | 使用原文內容向量化時，傳送給 embedding 模型的最大估算 token 數。預設：`4096` |
| `provider` | str | `"openai"`、`"azure"`、`"volcengine"`、`"vikingdb"`、`"jina"`、`"ollama"`、`"gemini"`、`"voyage"`、`"dashscope"`、`"minimax"`、`"cohere"`、`"litellm"` 或 `"local"` |
| `api_key` | str | API Key |
| `model` | str | 模型名稱 |
| `dimension` | int | 向量維度；Voyage 對應 `output_dimension` |
| `input` | str | 輸入型別：`"text"` 或 `"multimodal"` |
| `batch_size` | int | 批次請求大小 |
| `encoding_format` | str | （僅 OpenAI / Azure）Embedding 值的傳輸格式：`"float"` 或 `"base64"`。留空時使用 OpenAI Python SDK 預設值；當上遊網關無法正確處理 base64 embedding payload 時，可設定為 `"float"`。 |
| `extra_body` | object | （僅 OpenAI / Azure）合併進每次 embedding 請求體的額外 JSON 欄位。適用於接受廠商專有欄位的 OpenAI 相容閘道器，例如 OpenRouter 的 provider 路由 `{"provider": {"sort": "latency"}}`。發生衝突時，顯式設定的 `query_param`/`document_param` 鍵優先。 |

`embedding.max_retries` 僅對瞬時錯誤生效，例如 `429`、`5xx`、超時和連線錯誤；`400`、`401`、`403`、`AccountOverdue` 這類永久錯誤不會自動重試。退避策略為指數退避，初始延遲 `0.5s`，上限 `8s`，並帶隨機抖動。

#### Embedding 熔斷（Circuit Breaker）

當 embedding provider 出現連續瞬時錯誤（如 `429`、`5xx`）時，OpenViking 會觸發熔斷，在一段時間內暫停呼叫 provider，並將 embedding 任務重新入隊。超過基礎 `reset_timeout` 後進入 HALF_OPEN，允許一次探測請求；如果探測失敗，則下一次 `reset_timeout` 翻倍（上限為 `max_reset_timeout`）。

```json
{
  "embedding": {
    "circuit_breaker": {
      "failure_threshold": 5,
      "reset_timeout": 60,
      "max_reset_timeout": 600
    }
  }
}
```

| 引數 | 型別 | 說明 |
|------|------|------|
| `circuit_breaker.failure_threshold` | int | 連續失敗多少次後熔斷（預設：`5`） |
| `circuit_breaker.reset_timeout` | float | 基礎恢復等待時間（秒，預設：`60`） |
| `circuit_breaker.max_reset_timeout` | float | 指數退避後的最大恢復等待時間（秒，預設：`600`） |

**可用模型**

| 模型 | 維度 | 輸入型別 | 說明 |
|------|------|----------|------|
| `doubao-embedding-vision-251215` | 1024 | multimodal | 推薦 |
| `doubao-embedding-250615` | 1024 | text | 僅文本 |

使用 `input: "multimodal"` 時，OpenViking 可以嵌入文本、圖片（PNG、JPG 等）和混合內容。以圖搜圖需要該模式；純文本 embedding 模型仍會索引圖片 summary，但不能接收圖片查詢。

Hybrid 是否支援圖片取決於 dense 通道。圖文完整輸入進入 dense，sparse 只接收文字；純圖輸入跳過 sparse。Volcengine hybrid 對純文本保留一次合併請求，對圖文分別請求多模態 dense 和文本 sparse。dense 模型和維度應與索引中已有的向量保持相容。

**支援的 provider:**
- `openai`: OpenAI Embedding API
- `azure`: Azure OpenAI Embedding API
- `volcengine`: 火山引擎 Embedding API
- `vikingdb`: VikingDB Embedding API
- `jina`: Jina AI Embedding API
- `ollama`: Ollama 本地 OpenAI 兼容 Embedding API
- `voyage`: Voyage AI Embedding API
- `minimax`: MiniMax Embedding API
- `cohere`: Cohere Embedding API
- `gemini`: Google Gemini Embedding API（僅文本；需安裝 `google-genai>=1.39.0`）
- `dashscope`: DashScope（阿里通義）Embedding API
- `litellm`: LiteLLM Embedding API
- `local`: 本地 GGUF embedding 模型

**OpenAI 兼容 provider 的 JSON float embedding 示例:**

```json
{
  "embedding": {
    "dense": {
      "provider": "openai",
      "api_key": "your-api-key",
      "api_base": "https://your-openai-compatible-endpoint/v1",
      "model": "text-embedding-3-large",
      "dimension": 3072,
      "encoding_format": "float"
    }
  }
}
```

`encoding_format` 是可選欄位，只會傳給 `provider: "openai"` 和 `provider: "azure"`。留空時使用 OpenAI Python SDK 預設行為；如果 OpenAI 相容上游閘道器無法正確反序列化 base64 embedding payload，可設定為 `"float"`。

**OpenRouter provider 路由示例:**

```json
{
  "embedding": {
    "dense": {
      "provider": "openai",
      "api_key": "your-openrouter-api-key",
      "api_base": "https://openrouter.ai/api/v1",
      "model": "qwen/qwen3-embedding-8b",
      "dimension": 4096,
      "extra_body": {
        "provider": {
          "sort": "latency"
        }
      }
    }
  }
}
```

`extra_body` 會合並進每次 embedding 請求，因此無需改動程式碼即可調優接受廠商專有欄位的 OpenAI 相容閘道器（例如 OpenRouter 的 provider 路由偏好）。該欄位只會傳給 `provider: "openai"` 和 `provider: "azure"`。

**Azure OpenAI provider 的 JSON float embedding 示例:**

```json
{
  "embedding": {
    "dense": {
      "provider": "azure",
      "api_key": "your-azure-api-key",
      "api_base": "https://your-resource-name.openai.azure.com",
      "api_version": "2025-01-01-preview",
      "model": "your-embedding-deployment-name",
      "dimension": 3072,
      "encoding_format": "float"
    }
  }
}
```

對於 Azure OpenAI，`model` 必須填寫 Azure 中配置的 embedding deployment name。

**minimax provider 配置示例:**

```json
{
  "embedding": {
    "dense": {
      "provider": "minimax",
      "api_key": "your-minimax-api-key",
      "model": "embo-01",
      "dimension": 1536,
      "query_param": "query",
      "document_param": "db",
      "extra_headers": {
        "GroupId": "your-group-id"
      }
    }
  }
}
```

**vikingdb provider 配置示例:**

```json
{
  "embedding": {
    "dense": {
      "provider": "vikingdb",
      "model": "bge_large_zh",
      "ak": "your-access-key",
      "sk": "your-secret-key",
      "region": "cn-beijing",
      "dimension": 1024
    }
  }
}
```

**jina provider 配置示例:**

```json
{
  "embedding": {
    "dense": {
      "provider": "jina",
      "api_key": "jina_xxx",
      "model": "jina-embeddings-v5-text-small",
      "dimension": 1024
    }
  }
}
```

可用 Jina 模型:
- `jina-embeddings-v5-text-small`: 677M 引數, 1024 維, 最大序列長度 32768 (預設)
- `jina-embeddings-v5-text-nano`: 239M 引數, 768 維, 最大序列長度 8192

**Voyage provider 配置示例：**

```json
{
  "embedding": {
    "dense": {
      "provider": "voyage",
      "api_key": "pa-xxx",
      "api_base": "https://api.voyageai.com/v1",
      "model": "voyage-4-lite",
      "dimension": 1024
    }
  }
}
```

可使用 `voyage-4-lite`、`voyage-4`、`voyage-4-large` 等文本模型。可用模型與維度見 [Voyage 文本 Embedding 文件](https://docs.voyageai.com/docs/embeddings)。

省略 `dimension` 時，OpenViking 按內建模型表（`voyage-3`、`voyage-3-large`、`voyage-3.5`、`voyage-3.5-lite`、`voyage-4`、`voyage-4-lite`、`voyage-4-large`、`voyage-code-3`、`voyage-context-3`、`voyage-finance-2`、`voyage-law-2`）選擇維度；未識別的模型回退為 1024。使用新模型時，請顯式填寫其支援的輸出維度。當前介面卡傳送普通文本 `input`，不傳遞 Voyage 的 `input_type`，也不支援量化輸出或需要專用上下文介面的呼叫方式。

**本地部署 (GGUF/MLX):** Jina 嵌入模型是開源的, 在 [Hugging Face](https://huggingface.co/jinaai) 上提供 GGUF 和 MLX 格式。可以使用任何 OpenAI 相容的推理伺服器 (如 llama.cpp、MLX、vLLM) 本地執行, 並將 `api_base` 指向本地端點:

```json
{
  "embedding": {
    "dense": {
      "provider": "jina",
      "api_key": "local",
      "api_base": "http://localhost:8080/v1",
      "model": "jina-embeddings-v5-text-nano",
      "dimension": 768
    }
  }
}
```

獲取 API Key: https://jina.ai

**gemini provider 配置示例:**

SDK 1.39.0 起提供所需的客戶端上下文管理器和關閉方法，用於在所屬事件迴圈內完成非同步嵌入請求及清理。啟用此 provider 前，請升級固定在舊版本的 SDK。

> **注意：** 需要在服務端環境安裝 `google-genai>=1.39.0`——uv 安裝：`uv tool install openviking --upgrade --with "google-genai>=1.39.0"`；pip 安裝：`pip install "google-genai>=1.39.0"`。非同步批次嵌入改用 extra：`uv tool install "openviking[gemini-async]" --upgrade` 或 `pip install "openviking[gemini-async]"`。

```json
{
  "embedding": {
    "dense": {
      "provider": "gemini",
      "api_key": "your-google-api-key",
      "model": "gemini-embedding-2-preview",
      "dimension": 3072
    }
  }
}
```

可用 Gemini 嵌入模型:
- `gemini-embedding-2-preview`: 8192 token 輸入限制, 1–3072 輸出維度 (MRL)
- `gemini-embedding-001`: 2048 token 輸入限制, 1–3072 輸出維度 (MRL)
- `text-embedding-004`: 2048 token 輸入限制, 768 輸出維度（固定）

推薦維度: `768`、`1536` 或 `3072`（預設: `3072`）。

獲取 API Key: https://aistudio.google.com/apikey

**DashScope（阿里通義）provider 配置示例:**

```json
{
  "embedding": {
    "dense": {
      "provider": "dashscope",
      "api_key": "${DASHSCOPE_API_KEY}",
      "model": "text-embedding-v4",
      "dimension": 1024,
      "input": "text"
    }
  }
}
```

**可用 DashScope 模型:**

| 模型 | 維度 | 輸入型別 | 說明 |
|------|------|----------|------|
| `text-embedding-v3` | 1024 | text | 針對中文最佳化 |
| `text-embedding-v4` | 1024 | text | 針對中文最佳化 |
| `tongyi-embedding-vision-plus` | 1152 | multimodal | 支援通過 `enable_fusion` 啟用融合向量 |
| `tongyi-embedding-vision-flash` | 768 | multimodal | 更快，成本更低 |
| `qwen3-vl-embedding` | 2560 | multimodal | 文本 + 影像 + 影片 |
| `qwen2.5-vl-embedding` | 1024 | multimodal | 文本 + 影像 + 影片 |

**輸入和多模態引數**:

| 引數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `input` | str | `"multimodal"` | 嵌入模式：`"text"` 或 `"multimodal"` |
| `enable_fusion` | bool | `false` | 為 `tongyi-embedding-vision-*` 模型啟用融合向量 |
| `res_level` | int | `2` | 影像解析度級別（1=高，2=中，3=低） |
| `max_video_frames` | int | `16` | 影片最大嵌入幀數 |

**端點選擇** — DashScope 為中國區（`cn`）和國際區（`intl`）提供 `api_base` 預設值:

| 區域 | `api_base` | 說明 |
|------|-----------|------|
| 中國 | `https://dashscope.aliyuncs.com`（預設） | 推薦中國大陸使用者使用 |
| 國際 | `https://dashscope-intl.aliyuncs.com` | 推薦中國境外使用者使用 |

如果使用自定義閘道器，`api_base` 應填寫閘道器根地址。OpenViking 會根據
輸入模式自動追加 endpoint 路徑，因此不要在 `api_base` 中包含
`/compatible-mode/v1`（文本模式）或
`/api/v1/services/embeddings/multimodal-embedding/multimodal-embedding`
（多模態模式）。

獲取 API Key: https://dashscope.console.aliyun.com/api-key

**非對稱檢索**（索引和查詢使用不同的 task type）:

```json
{
  "embedding": {
    "dense": {
      "provider": "gemini",
      "api_key": "your-google-api-key",
      "model": "gemini-embedding-2-preview",
      "dimension": 3072,
      "query_param": "RETRIEVAL_QUERY",
      "document_param": "RETRIEVAL_DOCUMENT"
    }
  }
}
```

支持的 task type: `RETRIEVAL_QUERY`、`RETRIEVAL_DOCUMENT`、`SEMANTIC_SIMILARITY`、`CLASSIFICATION`、`CLUSTERING`、`CODE_RETRIEVAL_QUERY`、`QUESTION_ANSWERING`、`FACT_VERIFICATION`。

#### 本地 provider（`local`）

未配置 `dense`、`sparse` 或 `hybrid` embedding 時（包括省略 `embedding`），OpenViking 預設選擇 `dense: {"provider": "local", "model": "bge-small-zh-v1.5-f16"}`。該 GGUF 模型輸出 512 維向量，無需 API Key。

安裝本地推理依賴：

```bash
pip install "openviking[local-embed]"
```

首次使用時，OpenViking 將模型下載到 `~/.cache/openviking/models`；已有快取則複用。通過 `embedding.dense.cache_dir` 修改快取目錄，或用 `embedding.dense.model_path` 指定已有 GGUF 檔案以跳過下載。顯式指定的檔案不存在時會報錯，不會轉為下載。該模型的維度固定為 512。

#### Sparse Embedding

> 以下示例使用 `doubao-embedding-vision-251215`。所選模型是否支援文本 sparse 輸出，請核對方舟[向量化文件](https://docs.volcengine.com/docs/ark/vectorization?lang=zh&redirect=1)。

```json
{
  "embedding": {
    "sparse": {
      "provider": "volcengine",
      "api_key": "your-api-key",
      "model": "doubao-embedding-vision-251215"
    }
  }
}
```

Sparse 輸出是 embedding provider 的能力，不會因為設定
`storage.vectordb.sparse_weight` 就自動出現。OpenViking 當前只為
`volcengine` 和 `vikingdb` 實現了 `sparse` / `hybrid` embedding provider；
OpenAI 相容介面、Ollama 和內建 `local` provider 目前都只支援 dense。
因此，自託管的 `/v1/embeddings` 不會被自動當成 sparse 介面，OpenViking
也不會額外探測 `/v1/embeddings/sparse` 路由。

當 provider 只返回 dense vector 時，OpenViking 不會自動補充 BM25 或其他
sparse-vector 兜底。若要啟用混合檢索，需要配置受支援的 sparse/hybrid
provider，並設定 `storage.vectordb.sparse_weight > 0`。自託管模型的記憶體需求
取決於具體 provider 和模型，不由 OpenViking 控制；生產啟用前請按模型文件
評估資源佔用。

#### Hybrid Embedding

支援兩種方式：

**方式一：使用單一混合模型**

```json
{
  "embedding": {
    "hybrid": {
      "provider": "volcengine",
      "api_key": "your-api-key",
      "model": "doubao-embedding-vision-251215",
      "dimension": 1024
    }
  }
}
```

**方式二：組合 dense + sparse**

```json
{
  "embedding": {
    "dense": {
      "provider": "volcengine",
      "api_key": "your-api-key",
      "model": "doubao-embedding-vision-251215",
      "dimension": 1024
    },
    "sparse": {
      "provider": "volcengine",
      "api_key": "your-api-key",
      "model": "doubao-embedding-vision-251215"
    }
  }
}
```

### vlm

用於語義提取（L0/L1 生成）的視覺語言模型。

```json
{
  "vlm": {
    "provider": "volcengine",
    "api_key": "your-api-key",
    "model": "doubao-seed-2-0-lite-260428",
    "api_base": "https://ark.cn-beijing.volces.com/api/v3",
    "max_retries": 3,
    "media": {
      "enabled": true,
      "max_concurrent": 2,
      "file_processing_timeout": 1800,
      "file_poll_interval": 3,
      "video_fps": 1.0
    }
  }
}
```

**引數**

| 引數 | 型別 | 說明 |
|------|------|------|
| `api_key` | str | API Key。`openai-codex` 在 Codex OAuth 可用時可省略；使用 provider 原生憑據的 `litellm` 路由也可省略 |
| `forward_api_key` | bool | 僅 LiteLLM 使用。覆蓋是否把 `api_key` 透傳給 LiteLLM。預設情況下，OpenViking 不會把佔位 key 透傳給 `bedrock/`、`sagemaker/`、`vertex_ai/` 等 AWS/GCP 原生鑑權路由；如果明確使用 LiteLLM 的 Bedrock bearer-token API-key 鑑權，可設為 `true` |
| `model` | str | 模型名稱 |
| `api_base` | str | API 端點（可選） |
| `thinking` | bool | 啟用思考模式（僅對部分火山模型生效，預設：`false`） |
| `max_concurrent` | int | 語義處理階段 LLM 最大併發呼叫數（預設：`32`） |
| `max_retries` | int | VLM provider 瞬時錯誤的最大重試次數（預設：`3`；`0` 表示停用重試） |
| `credentials` | array | 有序 VLM 憑據/模型列表，索引 0 優先順序最高。每項可單獨覆蓋 `provider`、`model`、`api_key`、`api_base`、`api_version`、`extra_headers`、`extra_request_body`、`reasoning_effort` 和 `keepalive_expiry` |
| `failback_timeout_seconds` | float | 切換到低優先順序 credential 後，嘗試逐級切回的時間閾值（預設：`600`） |
| `failback_request_count` | int | 低優先順序 credential 成功處理多少次請求後嘗試逐級切回（預設：`50`） |
| `backup` | object | 可選的備用 VLM 配置（結構與 `vlm` 相同），當主 VLM 遇到限流、`5xx`、超時或連線失敗等可重試錯誤時自動切換。僅支援 1 層備用 &mdash; 備用 VLM 本身不能再巢狀 `backup` |
| `timeout` | float | 單次 VLM API 請求的 HTTP 超時時間（秒），傳遞給底層 OpenAI/LiteLLM 客戶端。慢端點（如 DashScope、本地推理）可調大。必須 `> 0`（預設：`600.0`） |
| `keepalive_expiry` | float | OpenAI 相容 VLM 客戶端的空閒連線保留秒數。設為 `0` 可停用空閒連線複用；不設定時使用 OpenAI SDK 預設值。必須 `>= 0` |
| `extra_headers` | object | 相容 HTTP provider 的自定義請求頭。`kimi` 預設已注入所需訂閱請求頭，也支援在這裡覆蓋或擴充 |
| `extra_request_body` | object | 傳給 OpenAI 相容 completion 請求的額外 JSON body 欄位，可用於 Ollama `{"think": false}` 等 provider 專有引數 |
| `reasoning_effort` | str | `openai`、`azure`、`kimi`、`glm` 和 `openai-codex` 的推理強度，顯式配置時傳送；可用值由模型決定。不設定時，GPT-5/o 系列名稱保留 `low`，其他模型不傳送。Chat Completions 請求中，`extra_request_body.reasoning_effort` 優先 |
| `media` | object | 音影片執行引數；音影片理解複用該 VLM 的 provider、模型、憑據、client、超時、重試、請求頭、輸出 token 限制、故障切換和 token 統計 |
| `media.enabled` | bool | 啟用音影片理解（預設：`false`） |
| `media.max_concurrent` | int | 音影片呼叫最大併發數（預設：`2`） |
| `media.file_processing_timeout` | float | Provider 側媒體預處理最長等待秒數（預設：`1800`） |
| `media.file_poll_interval` | float | Provider 側媒體預處理輪詢間隔秒數（預設：`3`） |
| `media.video_fps` | float | Provider 支援時使用的影片取樣幀率，範圍 `0.2` 到 `5.0`（預設：`1.0`） |

`vlm.max_retries` 僅對瞬時錯誤生效，例如 `429`、`5xx`、超時和連線錯誤；認證、鑑權、欠費等永久錯誤不會自動重試。退避策略為指數退避，初始延遲 `0.5s`，上限 `8s`，並帶隨機抖動。

**可用模型**

| 模型 | 說明 |
|------|------|
| `doubao-seed-2-0-lite-260428` | 推薦用於語義提取 |
| `doubao-pro-32k` | 用於更長上下文 |

新增資源時，VLM 生成：

1. **L0（摘要）**：檔案或目錄摘要，預設字元上限為 256
2. **L1（概覽）**：目錄概覽，包含導航資訊，預設字元上限為 4000

VLM 配置返回 `is_available() == false` 時，通用檔案摘要會返回空內容，目錄概覽會退回“尚未就緒”的佔位內容；可由本地解析器提取的程式碼骨架等仍按各自路徑處理。這種狀態不能視為已完成語義索引，應檢查模型配置和對應處理任務。

**支持的 provider：**
- `volcengine`：火山引擎 VLM API
- `openai`：OpenAI 兼容 VLM API
- `openai-codex`：通過 ChatGPT/Codex OAuth 使用 Codex VLM
- `kimi`：Kimi Coding 訂閱端點，內建 provider 預設配置
- `glm`：Z.AI GLM Coding Plan 端點，使用 OpenAI 相容請求格式
- `litellm`：LiteLLM VLM API，支援 `bedrock/`、`sagemaker/`、`vertex_ai/`、`azure/` 等顯式 LiteLLM 路由

對於 `openai-codex`，請通過 `openviking-server init` 完成鑑權，再使用 `openviking-server doctor` 做校驗。

對於 `litellm`，當底層路由使用環境變數或 provider 原生憑據時可以省略
`api_key`，例如 Bedrock/SageMaker 的 AWS IAM/IRSA，或 Vertex AI 的
ADC/service-account 憑據。Azure 路由仍會正常使用 `api_key`。如果明確要使用
LiteLLM 的 Bedrock bearer-token API-key 鑑權，請設定 `forward_api_key=true`。

**自定義 HTTP Headers**

對於 OpenAI 相容的 provider（如 OpenRouter），可以通過 `extra_headers` 新增自定義 HTTP 請求頭：

```json
{
  "vlm": {
    "provider": "openai",
    "api_key": "your-api-key",
    "model": "gpt-4o",
    "api_base": "https://openrouter.ai/api/v1",
    "extra_headers": {
      "HTTP-Referer": "https://your-site.com",
      "X-OpenRouter-Title": "Your App Name"
    }
  }
}
```

常見使用場景：
- **OpenRouter**：可選的 `HTTP-Referer` 和 `X-OpenRouter-Title` 用於[應用歸屬與展示](https://openrouter.ai/docs/app-attribution)，不作為 API 認證憑據；`X-Title` 仍可相容
- **Kimi Coding**: 需要自定義 user agent 或追加訂閱請求頭時可以在這裡覆蓋
- **OpenCode Go**（`https://opencode.ai/zen/go/v1`）: 請求不帶 `x-opencode-session` 會返回 HTTP 400 `MissingSessionID`。配置一個固定值即可，例如 `"extra_headers": {"x-opencode-session": "openviking-<your-host>"}`。OpenCode Go 只用這個 id 做路由和 prompt cache 最佳化，固定值不影響使用
- **自定義代理**: 新增認證頭或追蹤頭
- **API 閘道器**: 新增版本或路由標識

**自定義請求 Body**

通過 `extra_request_body` 配置 provider 專有 JSON body 欄位。OpenAI 相容路由使用 SDK 的 `extra_body`；LiteLLM Anthropic 路由將 `thinking`、`output_config` 等原生選項直接傳給 LiteLLM，使其進入請求 body 頂層。LiteLLM 仍會校驗模型是否支援這些選項。在 Anthropic 路由中，LiteLLM 控制引數名（包括 `api_key`、`api_base`、`metadata`、`mock_response`）以及呼叫自身管理的欄位（`model`、`messages`、`tools`、`tool_choice`、`stream`、`timeout` 和請求頭）會報錯，不會覆蓋呼叫。憑據和路由請使用各自的專用配置。

例如，關閉 Ollama 的思考模式：

```json
{
  "vlm": {
    "provider": "litellm",
    "api_key": "ollama",
    "model": "ollama/llama3.1",
    "api_base": "http://127.0.0.1:11434",
    "extra_request_body": {
      "think": false
    }
  }
}
```

**音影片理解**

音訊和影片理解是當前 VLM 的可選能力，複用相同的 provider、模型、憑據、client、請求超時、重試、請求頭、最大輸出 token、故障切換鏈路和 token 統計。通過巢狀的 `vlm.media` 引數啟用，不再單獨配置媒體模型。

```json
{
  "vlm": {
    "provider": "volcengine",
    "api_key": "${VOLCENGINE_API_KEY}",
    "model": "${VOLCENGINE_MODEL}",
    "api_base": "https://ark.cn-beijing.volces.com/api/v3",
    "timeout": 1200,
    "max_retries": 3,
    "max_tokens": 4096,
    "media": {
      "enabled": true,
      "file_processing_timeout": 1800,
      "file_poll_interval": 3,
      "max_concurrent": 2,
      "video_fps": 1.0
    }
  }
}
```

`vlm.extra_request_body` 也適用於音影片的方舟 Responses 請求，例如 `{"service_tier": "flex", "thinking": {"type": "disabled"}}`。請使用所選模型和 Responses API 支援的欄位。顯式配置的額外欄位通過 SDK 覆蓋自動生成的請求欄位，包括 `store`；響應儲存預設設為 `false`，僅在顯式配置時覆蓋。這些欄位不會傳給檔案上傳、狀態查詢或刪除請求。

VLM 的 `model` 填寫對應的方舟模型 endpoint ID。`video_fps` 僅用於影片，控制傳送給方舟的影片取樣幀率。

推薦使用 `doubao-seed-2-0-lite-260428` 或 `doubao-seed-2-0-mini-260428` 作為音影片理解模型。它們是可直接採用的推薦示例，並非完整的支援模型列表；方舟會持續更新模型及其輸入能力。影片理解的可選模型請參考方舟官方[影片輸入能力列表](https://console.volcengine.com/ark/region:cn-beijing/docs/82379/1330310?lang=zh#ff5ef604)，音訊理解的可選模型請參考方舟官方[音訊輸入能力列表](https://console.volcengine.com/ark/region:cn-beijing/docs/82379/1330310?lang=zh#9619c0ba)。如果 `model` 填寫的是 `ep-*` 推理接入點 ID，請確認該接入點背後的基礎模型支援對應的媒體輸入。OpenViking 不會在配置載入時校驗模型的音訊或影片能力。

**可接入格式與可理解格式**

| 型別 | 現有 Parser 可接入並儲存 | 本版本可由方舟理解 |
|------|--------------------------|--------------------|
| 音訊 | MP3、WAV、OGG、FLAC、AAC、M4A、OPUS、AC3 | MP3、WAV、AAC、M4A |
| 影片 | MP4、AVI、MOV、MKV、WEBM、FLV、WMV、TS | MP4、AVI、MOV |

不在“可理解”列中的格式繼續沿用現有 Parser 和儲存行為；OpenViking 不會對這些檔案轉碼，也不會把它們傳送給理解模型。當檔案被識別為音訊或影片葉子節點時，空媒體摘要會使用檔名入庫。

對於支援的檔案，OpenViking 將媒體上傳到方舟 Files API，且不顯式指定 `expire_at`，因此檔案保留時間遵循方舟的預設策略。檔案處理完成後，OpenViking 通過預設停用響應儲存的 Responses API 請求引用其 `file_id`，最後在較短的清理超時內嘗試刪除方舟檔案。遠端刪除屬於 best-effort；如果刪除失敗或超時，不會覆蓋已經成功的理解結果，檔案將繼續遵循方舟的預設保留策略。本地臨時檔案獨立清理，即使遠端清理失敗或請求被取消也會刪除。

- 目錄中只有一個音訊或影片檔案且理解成功時，該摘要直接成為目錄 L1，並通過現有語義鏈路派生 L0，不再呼叫通用 VLM 做第二次總結。
- 媒體位於混合目錄時，其摘要仍參與現有通用 VLM 聚合。
- 音影片理解未啟用、理解格式不支援或模型最終失敗時，媒體摘要為空；目錄 L0/L1 生成保持原有通用行為，被識別為音訊或影片的葉子節點則使用檔名作為 DETAIL 向量和 BM25 內容。Provider 錯誤和媒體理解狀態文字不會寫入媒體摘要或葉子索引。

媒體處理會把檔案內容傳送給所配置的外部 provider。停用響應儲存和 best-effort 刪除可以降低非預期留存風險，但不能替代 provider 自身的隱私與留存控制；上傳檔案未顯式指定過期時間，其保留週期由方舟的預設策略決定。方舟 Files 的儲存/處理以及 Responses 的模型 token 可能產生費用；啟用前請確認 provider 的隱私、留存和計費條款。詳見火山方舟官方[音訊理解文件](https://docs.volcengine.com/docs/82379/2377589?lang=zh)和[影片理解文件](https://docs.volcengine.com/docs/82379/1895586?lang=zh)。

### bot.compile

配置單個 Resource Compile 任務各階段的併發工作數，適用於直接模型呼叫和 agent 執行：

```json
{
  "bot": {
    "compile": {
      "map_concurrency": 8,
      "shuffle_concurrency": 4,
      "shuffle_batch_size": 4,
      "reduce_concurrency": 6
    }
  }
}
```

| 欄位 | 預設值 | 說明 |
|------|--------|------|
| `map_concurrency` | 繼承 `vlm.max_concurrent` | Map 提取工作併發數 |
| `shuffle_concurrency` | 繼承 `vlm.max_concurrent` | Shuffle 路由工作及 embedding 批次併發數 |
| `shuffle_batch_size` | `4` | 每次 Shuffle 路由請求的主記錄數上限；與併發數、字元軟預算獨立 |
| `reduce_concurrency` | 繼承 `vlm.max_concurrent` | Reduce 工作併發數；同路徑候選的最終 merge 複用此值 |

三個併發配置項必須為正整數；省略或設為 `null` 時繼承預設值。`shuffle_batch_size` 必須為正整數，省略時為 `4`，不接受 `null`。路由逐條儲存合法結果，僅失敗記錄重新組批重試，最後一次降為單條；每條記錄最多嘗試三輪。修改後需重啟 VikingBot 服務。一個 VikingBot 服務內的所有 Compile 任務仍共享 `vlm.max_concurrent` 限制的模型請求容量，因此提進階段併發不會突破這一總上限。Embedding 請求另受 embedding 服務的併發限制。恢復任務預設使用相同的 reduce 配置，顯式 `--concurrency` 可覆蓋恢復併發數。

Compile 繼承模型的 thinking 和 reasoning 配置。模型請求使用有效模型超時配置（`bot.agents.timeout` 或繼承的 `vlm.timeout`）。

### query_planner

可選的輕量模型配置，用於檢索前的意圖分析和 query 規劃/改寫。配置結構與 `vlm` 相同，用於 `search()` 的意圖分析、query expansion，以及可選的服務端 recall 摘要重寫。未配置或配置為空時，OpenViking 會回退到 `vlm`，保持向後相容。

> 在 `openviking-server init` 裡可勾選啟用本地輕量 query planner，嚮導會自動拉取 Ollama 模型並寫入 `query_planner` 配置。對於已知的 query planner 模型，`search()` 會在執行時自動選擇匹配的內建 prompt；不在對映表中的模型繼續使用 `retrieval.intent_analysis`。

推薦優先使用本地 Ollama 模型 [`guoxuter/ov_intent_analysis_sft:v7_q8`](https://ollama.com/guoxuter/ov_intent_analysis_sft:v7_q8)。該模型基於 Qwen3.5-0.8B 進行微調，可本地部署，適合用小模型承擔檢索規劃：在閒聊、問候或上下文已足夠的場景下拒絕檢索，從而減少不必要的記憶注入和 token 消耗；需要檢索時，再生成面向 `skill`、`resource`、`memory` 的結構化查詢。此前的 [`v4_q8`](https://ollama.com/guoxuter/ov_intent_analysis_sft:v4_q8) 版本仍作為可選項繼續支援。

使用前請先拉取模型，並確保 Ollama 服務可訪問：

```bash
ollama pull guoxuter/ov_intent_analysis_sft:v7_q8
```

然後在 OpenViking 配置中新增：

```json
{
  "query_planner": {
    "provider": "litellm",
    "model": "ollama/guoxuter/ov_intent_analysis_sft:v7_q8",
    "api_base": "http://127.0.0.1:11434",
    "temperature": 0.0,
    "timeout": 60,
    "extra_request_body": {
      "think": false
    }
  }
}
```

對於 `ollama/guoxuter/ov_intent_analysis_sft:v7_q8`（以及 `v4_q8`），OpenViking 會在 search 階段自動使用對應的內建 prompt（分別為 `retrieval.ov_intent_analysis_sft_v7` 和 `retrieval.ov_intent_analysis_sft_v4`），不需要替換 prompt 檔案，也不需要設定 `prompts.templates_dir`。如果使用未對映的模型，OpenViking 會繼續使用預設的 `retrieval.intent_analysis` prompt。

這樣可以用小模型承擔檢索規劃，同時保留更強的 `vlm` 處理語義提取、記憶提取和多模態內容。延遲需按模型、硬體和請求負載測量。


### code

程式碼骨架提取內建在程式碼摘要流程中，不再提供解析器級配置。OpenViking 會在語言存在維護中的 `tags.scm` 時優先使用 tags query；不存在對應的 `tags.scm` 時，使用 `tree-sitter-language-pack.process()`；當前提取路線無可用結果時，才將 `semantic.code_summary` 作為兜底處理。若 `tree-sitter-language-pack` 無法下載解析器（例如處於防火牆之後），常用語言會改用隨依賴安裝的語法包，無需額外配置。

當前保留的 `code` 配置欄位用於遠端程式碼資源的網路防護和程式碼託管白名單。提取路線詳見 [程式碼骨架提取](../concepts/06-extraction.md#程式碼骨架提取)。

#### 遠端資源網路防護

通過 URL 拉取資源時，預設網路檢查會拒絕解析到非公網地址的目標。普通公網 URL 無需加入程式碼託管白名單；列入白名單的可信程式碼主機會跳過地址範圍檢查。接入自建 GitHub Enterprise / GitLab / Azure DevOps 時，可將主機加入 `code` 下對應的平臺列表：

| 欄位 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `github_domains` | list[str] | 允許的 GitHub 主機（在此新增你的 GitHub Enterprise 主機） | `["github.com", "www.github.com"]` |
| `gitlab_domains` | list[str] | 允許的 GitLab 主機（在此新增你的自建 GitLab 主機） | `["gitlab.com", "www.gitlab.com"]` |
| `azure_devops_domains` | list[str] | 允許的 Azure DevOps 主機 | `["dev.azure.com", "ssh.dev.azure.com", "vs-ssh.visualstudio.com"]` |
| `code_hosting_domains` | list[str] | 允許的通用程式碼託管主機 | `["github.com", "gitlab.com", "gitcode.com", "gitee.com", "bitbucket.org", "codeberg.org", "gitea.com", "atomgit.com", "git.sr.ht"]` |

如果需要允許其他私有網路目標（例如內部映象），可將頂層 `allow_private_networks` 設為 `true`。該開關預設關閉；`localhost` 及其子域等本地主機名仍會被拒絕。下面同時演示啟用私有網路訪問和新增程式碼主機：

```json
{
  "allow_private_networks": true,
  "code": {
    "github_domains": ["github.com", "github.example.com"]
  }
}
```

需要 GitHub、GitLab 或 Azure DevOps 專屬 URL 語義時，應配置到對應的平臺欄位；
其他 Git 主機統一新增到 `code_hosting_domains`。

### pdf

PDF 解析配置。支援三種策略：`local`（本地 pdfplumber）、`mineru`（遠端 MinerU API）、`auto`（先本地、失敗回退 MinerU）。

```json
{
  "pdf": {
    "strategy": "auto",
    "mineru_endpoint": "http://127.0.0.1:8000",
    "mineru_timeout": 300.0,
    "mineru_bodys": {
      "backend": "hybrid-auto-engine",
      "lang_list": ["ch"],
      "parse_method": "auto"
    }
  }
}
```

| 引數 | 型別 | 說明 |
|------|------|------|
| `strategy` | str | 解析策略：`local` / `mineru` / `auto`（預設 `auto`） |
| `mineru_endpoint` | str | MinerU API **base URL**（如 `http://127.0.0.1:8000`） |
| `mineru_timeout` | float | 請求超時秒數（預設 `300.0`） |
| `mineru_bodys` | dict | MinerU API multipart form 引數 |

**MinerU 協議**：同步呼叫 `POST {mineru_endpoint}/file_parse`，multipart 檔案欄位為 `files`，form 引數由 `mineru_bodys` 透傳。

### 外部解析 API（`parser_api`） {#parser-api}

頂層 `parser_api` 配置將指定格式交給外部 Understanding files/responses API。它只替換 Parser 階段；TreeBuilder、持久化和語義處理仍由 OpenViking 完成。路由與非同步行為見[資源處理流程](../api/02-resources.md#資源處理流程)。

| 欄位 | 預設值 | 含義 |
| --- | --- | --- |
| `enable` | `false` | 啟用外部解析。 |
| `extensions` | `[]` | 交給外部解析的副檔名；轉為小寫並去掉開頭的點。 |
| `host` | `""` | 帶協議的 API 地址，如 `https://parser.example.com`；啟用時必填。 |
| `api_key` | `""` | 外部 API 憑證；啟用時必填。 |
| `enable_resumable_upload` | `false` | 啟用斷點續傳。 |
| `upload_simple_max_bytes` | `536870912`（512 MiB） | 簡單上傳的大小閾值。 |
| `upload_part_size_bytes` | `8388608`（8 MiB） | 分片上傳的分片大小。 |
| `http_timeout_seconds` | `10.0` | 單次 HTTP 請求超時秒數。 |
| `response_timeout_seconds` | `1800` | 等待解析結果的超時秒數。 |
| `poll_interval_ms` | `3000` | 結果輪詢間隔，單位毫秒。 |

大小、超時和輪詢引數都必須大於零。

### rerank

用於搜尋結果精排的 Rerank 模型。支援 VikingDB（火山引擎）、Cohere、OpenAI
兼容接口、LiteLLM 和 Jev。

**火山引擎 (VikingDB):**

```json
{
  "rerank": {
    "provider": "vikingdb",
    "ak": "your-access-key",
    "sk": "your-secret-key",
    "model_name": "doubao-seed-rerank",
    "model_version": "251028"
  }
}
```

**OpenAI 兼容提供方 (如 DashScope):**

```json
{
  "rerank": {
    "provider": "openai",
    "api_key": "your-api-key",
    "api_base": "https://dashscope.aliyuncs.com/compatible-api/v1/reranks",
    "model": "qwen3-rerank",
    "timeout": 120,
    "max_input_tokens": 2048,
    "threshold": 0.1
  }
}
```

**Jev (TypeSafe System One) 提供方:**

```json
{
  "rerank": {
    "provider": "jev",
    "api_key": "your-typesafe-api-key",
    "model": "jev-latest",
    "timeout": 120,
    "log_payloads": false,
    "threshold": 0.1
  }
}
```

通過 Vercel AI Gateway 使用 Jev 時，把 `api_base` 指向 Vercel 的
[TypeSafe 相容端點](https://vercel.com/docs/ai-gateway/sdks-and-apis/typesafe)，
`model` 使用 Vercel 模型 ID。請求和響應格式與 TypeSafe 直連完全相同，介面卡
不做任何區分：

```json
{
  "rerank": {
    "provider": "jev",
    "api_key": "your-vercel-ai-gateway-api-key",
    "api_base": "https://ai-gateway.vercel.sh/typesafe",
    "model": "typesafe-ai/jev",
    "threshold": 0.1
  }
}
```

走 Vercel 時注意：

- `api_key` 用 `vercel ai-gateway api-keys create` 生成的長期 AI Gateway API
  key，不要用 `vercel env pull` 拉取的 OIDC token，後者 12 小時過期。
- Vercel 團隊須先在 AI Gateway 頁面繫結信用卡，否則請求返回 403
  `customer_verification_required`。
- `api_base` 必須帶 `/typesafe` 字尾；`https://ai-gateway.vercel.sh/v1` 是
  Vercel 自有的 evaluate 協議，介面卡不支援。

Jev 介面卡將 query 和候選文件作為共享的 System One `state`，支援兩種模式：

- `noul`（預設）：為每篇文件提出獨立的相關性問題，返回的 yes 機率作為分數。
  所有問題放在一次 HTTP 請求中，各文件分數不要求總和為 1。
- `choice`：用一個問題橫向比較所有候選文件，以 `candidate_{index}` 對應輸入
  下標，並按原文件順序讀取 `probabilities` 作為分數。

通過 `rerank.mode` 選擇模式；未配置或配置為 `null` 時預設使用 `noul`。Choice
返回候選池內總和為 1 的相對機率，不是絕對相關機率，不適合使用絕對分數閾值。
啟用 Choice 時建議同時設定 `"threshold": 0`。MCP `find` 和 `search` 的
`min_score` 會覆蓋該配置，因此通過 MCP 使用 Choice 時還需要顯式傳入
`min_score=0`。

**引數**

| 引數 | 型別 | 說明 |
|------|------|------|
| `provider` | str | `"vikingdb"`、`"cohere"`、`"openai"`、`"litellm"` 或 `"jev"`。省略時基於欄位自動識別。 |
| `ak` | str | VikingDB Access Key（僅 `vikingdb` 提供方使用） |
| `sk` | str | VikingDB Secret Key（僅 `vikingdb` 提供方使用） |
| `model_name` | str | 模型名稱（僅 `vikingdb` 提供方使用，預設：`doubao-seed-rerank`） |
| `api_key` | str | API Key（用於 `openai`、`cohere` 或 `jev` 提供方） |
| `api_base` | str | 介面地址（用於 `openai` 或 `jev`；Jev 預設為 `https://api.typesafe.ai`，Vercel 使用 `https://ai-gateway.vercel.sh/typesafe`） |
| `model` | str | 模型名稱（用於 OpenAI 相容、LiteLLM 或 `jev` 提供方） |
| `mode` | `"noul"`、`"choice"` 或 `null` | Jev Rerank 模式；省略或 `null` 時使用 `"noul"` |
| `timeout` | float | HTTP Rerank provider（包括 Jev）的請求超時時間，單位為秒。預設：`30.0` |
| `max_input_tokens` | int | 每個 query-document 對傳送給 reranker 的最大估算原始文本 token 數；超長輸入會保留開頭和結尾。`0` 表示不截斷。預設：`0` |
| `log_payloads` | bool | 記錄完整 rerank 請求和響應；日誌可能包含 query 和文件內容。預設：`false` |
| `threshold` | float | 分數閾值，範圍為 `0.0` 到 `1.0`。低於此值的結果會被過濾。預設：`0.1` |
| `extra_headers` | object | 自定義 HTTP 請求頭（OpenAI 相容 provider 可用，可選） |

**支持的提供方:**
- `vikingdb`: 火山引擎 VikingDB Rerank API (使用 AK/SK)
- `cohere`: Cohere Rerank API
- `openai`: OpenAI 相容的 Rerank 介面
- `litellm`: LiteLLM Rerank 介面
- `jev`: Jev (TypeSafe System One) 結構化判定介面，支援 Choice 橫向比較和 Noul 獨立評分

如果未配置 Rerank，搜尋僅使用向量相似度。

### retrieval

會話意圖分析和上下文組裝的超時配置。

```json
{
  "retrieval": {
    "enable_intent": true,
    "recall_intent_timeout_s": 5.0,
    "recall_rewrite_timeout_s": 30.0
  }
}
```

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `enable_intent` | bool | `search()` 收到 `session_id` 時是否執行意圖分析和查詢規劃。 | `true` |

普通 `search()` 的會話意圖分析和 `mode="context"` 的查詢擴充共用 `recall_intent_timeout_s`；上下文 digest 重寫使用獨立的超時配置：

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `recall_intent_timeout_s` | float | 會話意圖分析和上下文查詢擴充的超時；超時或失敗後回退為使用者原查詢 | `5.0` |
| `recall_rewrite_timeout_s` | float | digest 重寫的超時；超時後 `digest` 為空並照常返回 `rendered` | `30.0` |

查詢擴充需要傳入有內容的 `session_id` 並啟用意圖分析，重寫需要傳入 `rewrite`。這些模型呼叫受各自超時限制；失敗後回退到未擴充的查詢或未重寫的結果。

### storage

用於儲存上下文資料 ，包括檔案儲存（RAGFS）和向量庫儲存（VectorDB）。

#### 根級配置

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `workspace` | str | 本地資料儲存路徑（主要配置） | "./data" |
| `skip_process_lock` | bool | 是否跳過本地向量後端（`local`、`cuvs`）對 `storage.workspace` 的 `.openviking.lock` 獨佔檔案鎖。其他後端不會獲取此鎖。跳過檢查不代表本地向量儲存支援多程序共享。 | `false` |
| `agfs` | object | RAGFS（Rust 實現的 AGFS）配置 | {} |
| `vectordb` | object | 向量庫儲存配置 | {} |
| `task_store` | object | 持久化 Task/Work 後端配置 | `{"provider":"file"}` |


```json
{
  "storage": {
    "workspace": "./data",
    "agfs": {
      "backend": "local",
      "timeout": 10
    },
    "vectordb": {
      "backend": "local"
    }
  }
}
```

#### task_store

Task 記錄預設使用本地 FileStore。需要多個 OpenViking 程序共享
Task/Work 狀態時，先在 MySQL 中執行
`openviking/service/sql/task_store_init.sql`，再選擇關係型後端：

```json
{
  "storage": {
    "task_store": {
      "provider": "mysql",
      "params": {
        "user": "openviking",
        "password": "change-me",
        "database": "openviking",
        "host": "127.0.0.1",
        "port": 3306,
        "table": "ov_tasks"
      }
    }
  }
}
```

`params.table` 是表字首，必須以 ASCII 字母開頭，只能包含 ASCII 字母、數字和
下劃線，最多 38 個字元，確保派生的表名、索引名和約束名不超過 MySQL 的 64 字元上限。
使用自定義字首時，需要在建表 SQL 中統一替換 `ov_tasks`。

MySQL 後端需要安裝 `openviking[mysql]` extra。Task mutation、Task
最終化和 execution event 更新在同一個資料庫事務中提交。`task_id`
是全域唯一身份；`account_id` 和 `user_id` 用於鑑權和查詢範圍。同一部署
不要同時讓 FileStore 和 MySQL 表作為寫入端。

#### agfs (RAGFS)

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `backend` | str | `"local"`、`"s3"` 或 `"memory"` | `"local"` |
| `timeout` | float | 請求超時時間（秒） | `10.0` |
| `backups` | object | 多寫儲存配置。配置後頂層 `backend` 作為 primary，`backups.items[]` 作為 backup | `null` |
| `queuefs` | object | QueueFS 配置。控制 `/queue` 的名稱空間模式、後端和執行時引數 | `{ "mode": "shared", "backend": "sqlite", "recover_stale_sec": 0, "busy_timeout_ms": 5000 }` |
| `queue_db_path` | str（可選）| 舊版相容欄位，用於覆蓋 QueueFS 的 sqlite 資料庫檔案路徑。已被 `storage.agfs.queuefs.db_path` 取代。未設定時預設為 `{storage.workspace}/_system/queue/queue.db`。適用於 workspace 卷不支援 sqlite 的場景（例如某些網路檔案系統） | `null` |
| `fs_executor_threads` | int | 執行阻塞式儲存呼叫的專用執行緒池大小，與預設 executor 隔離，避免後端緩慢（如高延遲 S3）拖垮向量資料庫等其他阻塞工作 | `64` |
| `fs_queue_timeout_ms` | int | 儲存呼叫若在此時間內無法開始（所有儲存執行緒忙碌），立即以逾時失敗（`503 UNAVAILABLE`），而非無限排隊 | `30000` |
| `circuit_breaker.enabled` | bool | 儲存呼叫的斷路器，依帳號（`/local/{account}`）與其他掛載點分別計算。某範圍連續 `failure_threshold` 次逾時或網路失敗（如 S3 中斷）後，該範圍的呼叫立即以 `503 UNAVAILABLE` 失敗，而非每次都等待完整期限；其他範圍不受影響，因此單一租戶無法讓其他租戶的儲存暫停；本機執行緒池飽和不計入 | `true` |
| `circuit_breaker.failure_threshold` | int | 觸發斷路的連續失敗次數 | `5` |
| `circuit_breaker.reset_timeout_seconds` | float | 斷路後放行一次探測呼叫前的等待時間；探測成功即恢復 | `15` |
| `circuit_breaker.max_reset_timeout_seconds` | float | 等待時間上限；每次探測失敗時等待時間加倍 | `120` |
| `s3` | object | S3 後端配置（`backend=s3` 時使用） | - |


**配置示例**

RAGFS 預設使用 Rust binding 模式，通過 Rust 實現直接訪問檔案系統。

> [!WARNING]
> `storage.agfs` 已不再支援 AGFS HTTP client 模式，也無需再配置舊的 HTTP client 入口。當前 AGFS / RAGFS 檔案系統訪問僅通過 Rust binding（`RAGFSBindingClient`）在程序內完成。這不影響 OpenViking server 的 HTTP API、`ov` CLI，或 `AsyncHTTPClient` / `SyncHTTPClient` 訪問 OpenViking 服務端的能力。

##### 主備儲存配置

`storage.agfs.backups` 啟用非同步 V2 多寫。頂層 backend 始終是唯一直接讀取來源。

```json
{
  "storage": {
    "workspace": "./data",
    "agfs": {
      "backend": "local",
      "backups": {
        "initial_partitions": 16,
        "checkpoint_interval_secs": 86400,
        "provider": "filesystem",
        "items": [
          {
            "name": "local-backup",
            "backend": "local",
            "params": {
              "workspace": "./data/backup"
            }
          }
        ]
      }
    }
  }
}
```

`backups` 常用字段：

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `initial_partitions` | int | account 首次初始化的 metadata partition 數；修改不影響已有 account | `16` |
| `checkpoint_interval_secs` | int | Checkpoint 掃描間隔，最小值為 `60` | `86400` |
| `provider` | str | Metadata provider：`filesystem` 或複用頂層 CacheRuntime 的 `cache` | `"filesystem"` |
| `items` | array | backup 列表，包含 `name`、`backend`、`params` 和可選 `encryption` | `[]` |

Python 配置層仍接受舊 sync、retry、operations、excludes 和 redirects
欄位，輸出 warning 後會在呼叫 Rust 前刪除，欄位不生效。

更多配置示例見 [主備儲存指南](./13-multi-write-storage.md)。

##### 全域 Cache Provider、CacheFS 與 PathLock 配置

頂層 `service_name` 表示當前 OpenViking 部署名。CacheFS、`backend=cache`
的 QueueFS、Cache PathLock 和 cache-backed 多寫 metadata 都會從它生成
Redis 名稱空間。

全域 `cache` 與 `storage` 並列，標準配置只包含 Provider 名稱和 Provider 自有引數：

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `provider` | str | 全局 Cache Provider；本期支持 `redis` | 必填 |
| `params` | object | Provider 自有引數；當 `provider=redis` 時解析為 Redis 連線引數 | `{}` |

`storage.agfs.cachefs` 只控制 CacheFS 業務行為：

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `backend` | str | `local` 完全沿用原檔案系統；`cache` 啟用 CacheFS wrapper | `local` |
| `max_file_size_bytes` | int | 允許快取的單檔案最大位元組數 | `1048576` |
| `traversal_mode` | str | `backend` 或 `cached_traversal` | `backend` |
| `bypass_prefixes` | array[str] | 繞過快取的路徑字首 | `[]` |

`storage.agfs.pathlock` 選擇 PathLock 儲存 Provider：

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `provider` | str | `filesystem`、`memory` 或 `cache`；`cache` 複用 Redis CacheRuntime | `filesystem` |
| `lock_expire_secs` | float | 未重新整理的鎖進入 stale 狀態前的秒數；不得小於 `1.0` | `30.0` |
| `lock_timeout_secs` | float | 已廢棄且忽略；執行時等待超時固定為 `0.0` | `0.0` |

```json
{
  "service_name": "production",
  "cache": {
    "provider": "redis",
    "params": {
      "mode": "sentinel",
      "endpoints": [
        "redis://sentinel-1:26379",
        "redis://sentinel-2:26379"
      ],
      "master_name": "mymaster",
      "password_env": "OPENVIKING_REDIS_PASSWORD",
      "connect_timeout_ms": 1000,
      "command_timeout_ms": 1000
    }
  },
  "storage": {
    "agfs": {
      "cachefs": {
        "backend": "cache"
      },
      "queuefs": {
        "backend": "cache"
      },
      "pathlock": {
        "provider": "cache",
        "lock_expire_secs": 30.0
      }
    }
  }
}
```

標準配置沒有全域 `cache.enabled`，也沒有各模組自己的 Redis namespace 欄位。當 CacheFS 或 QueueFS 選擇 `backend=cache`、PathLock 選擇 `provider=cache`，或多寫選擇 `backups.provider=cache` 時初始化 CacheRuntime。Cache PathLock 當前只支援 `cache.provider=redis`，不支援 DynamicProvider。全部模組使用本地 Provider 時不解析 `cache.params`，也不連線 Provider。

請把 Provider 引數遷移到頂層 `cache.provider/cache.params`，用頂層 `service_name` 生成共享 Redis 名稱，業務模組改為 `cachefs.backend="cache"`、`queuefs.backend="cache"` 或 `backups.provider="cache"`；Redis 的 `singleton` 改為 `standalone`，`tls_enabled` 改為使用 `rediss://` endpoint。

##### QueueFS 配置

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `mode` | str | QueueFS 名稱空間模式：`"shared"` 使用 `/queue`；`"worker"` 為每個 worker 隔離到 `/queue/worker-<index\|pid>` | `"shared"` |
| `backend` | str | QueueFS 後端：`"memory"`、`"sqlite"`、`"sqlite3"` 或 `"cache"` | `"sqlite"` |
| `db_path` | str（可選） | 當 backend 為 `"sqlite"` 或 `"sqlite3"` 時使用的 QueueFS sqlite 資料庫路徑 | `null` |
| `recover_stale_sec` | int | 啟動時恢復超過該秒數的 `processing` 佇列訊息；`0` 表示恢復全部 stale processing 訊息 | `0` |
| `busy_timeout_ms` | int | QueueFS sqlite 的 busy timeout，單位毫秒 | `5000` |

說明：

- 即使主 AGFS 儲存後端是 `local`、`s3` 或 `memory`，QueueFS 預設仍使用 `sqlite`。
- `mode=shared` 會繼續使用歷史上的全域佇列名稱空間 `/queue`；`mode=worker` 會為每個 worker 隔離到 `/queue/worker-<index|pid>`。
- `db_path` 僅在 QueueFS backend 為 `sqlite` 或 `sqlite3` 時生效。
- `recover_stale_sec` 和 `busy_timeout_ms` 僅在 QueueFS backend 為 `sqlite` 或 `sqlite3` 時生效。
- `queuefs.backend=cache` 自動繫結頂層 `cache.provider + cache.params`，並使用頂層 `service_name` 作為 key 字首。
- Redis Cluster 模式的 endpoints 是初始節點，且必須配置 `db=0`；slot 路由、`MOVED`/`ASK`、拓撲更新和重連由 Fred RedisProvider 處理。
- Redis Sentinel 模式的 endpoints 是 Sentinel 節點，並且必須配置非空 `master_name`；master 發現和故障切換後的重連由 Fred RedisProvider 處理。
- `username` 和 `password` 用於 Redis 資料節點；`sentinel_username` 和 `sentinel_password` 僅用於 Sentinel 節點。
- Cache backend 使用 `{service_name}:ov:*` key；連線同一 Redis 叢集的不同部署必須配置不同的 `service_name`。
- Cache backend 的例項心跳 TTL 為 30 秒，每 10 秒續約一次。同一 QueueFS cache namespace 中只有一個存活例項持有經 token 校驗的 30 秒 leader lease，並每 10 秒掃描過期的 `processing` 訊息；該例項停止後，其他例項會在 lease 到期後接管。正常關閉會刪除 heartbeat，因此恢復可以立即開始。
- 所有 Redis 讀命令都傳送到主節點，不提供副本讀配置。
- `tls_insecure_skip_verify=true` 時 endpoint 必須使用 `rediss://`。
- 如果同時設定了 `storage.agfs.queuefs.db_path` 和舊欄位 `storage.agfs.queue_db_path`，以前者為準。
- 如果 QueueFS backend 為 `memory`，則 `db_path` 和舊欄位 `queue_db_path` 都會被忽略。

示例：

```json
{
  "storage": {
    "workspace": "./data",
    "agfs": {
      "backend": "local",
      "queuefs": {
        "mode": "shared",
        "backend": "sqlite",
        "db_path": "./data/_system/queue/custom-queue.db"
      }
    }
  }
}
```

```json
{
  "storage": {
    "workspace": "./data",
    "agfs": {
      "backend": "local",
      "queuefs": {
        "mode": "worker",
        "backend": "memory"
      }
    }
  }
}
```

舊欄位相容示例：

```json
{
  "storage": {
    "workspace": "./data",
    "agfs": {
      "backend": "local",
      "queue_db_path": "./data/_system/queue/queue.db"
    }
  }
}
```

##### S3 後端配置

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `bucket` | str | S3 儲存桶名稱 | null |
| `region` | str | 儲存桶所在的 AWS 區域（例如 us-east-1, cn-beijing） | null |
| `access_key` | str | S3 訪問金鑰 ID | null |
| `secret_key` | str | 與訪問金鑰 ID 對應的 S3 秘密訪問金鑰 | null |
| `endpoint` | str | 自定義 S3 端點，對於 MinIO 或 LocalStack 等 S3 相容服務是必需的。可以填完整 URL（`https://...` 或 `http://...`），也可以只填主機名；只填主機名時會根據 `use_ssl` 自動補 `https://` 或 `http://` | null |
| `prefix` | str | 用於名稱空間隔離的可選鍵字首 | "" |
| `use_ssl` | bool | 為 S3 連線啟用/停用 SSL（HTTPS）。也用於決定 `endpoint` 僅填主機名時自動補的協議字首 | true |
| `use_path_style` | bool | true 表示對 MinIO 和某些 S3 相容服務使用 PathStyle；false 表示對 TOS 和某些 S3 相容服務使用 VirtualHostStyle | true |
| `auto_detect_content_type` | bool | 上傳時根據 object key / 檔名字尾自動推斷 MIME 型別，並寫入 S3 物件的 `Content-Type` | false |
| `directory_marker_mode` | str | 目錄 marker 的持久化方式，可選 `none`、`empty`、`nonempty` | `"empty"` |
| `normalize_encoding_chars` | str | 需要在 S3 object key 中轉義為 `!HH` 十六進位制位元組的字元集合；空字串表示關閉編碼 | `"?#%+@"` |
| `tiered` | object | 依大小分層儲存：小檔放 MariaDB、大檔放 S3，見[依大小分層儲存](#size-tiered-storage) | 關閉 |

`directory_marker_mode` 用來控制 RAGFS 在 S3 中如何落目錄物件：

- `empty` 是預設值。RAGFS 會寫入 0 位元組目錄 marker，並保留空目錄語義。
- `nonempty` 會寫入非空目錄 marker。對於 TOS 這類拒絕 0 位元組目錄 marker 的 S3 相容後端，應使用這個模式。
- `none` 會讓 RAGFS 採用更接近原生 S3 prefix 的目錄語義，不再建立目錄 marker 物件。此時空目錄不會被持久化，只有目錄下至少存在一個子物件後，相關目錄才可能被發現。

典型選擇：

- 對 MinIO、SeaweedFS 以及大多數 PathStyle 後端，保持預設 `empty` 即可。
- 對 TOS 或其他拒絕 0 位元組目錄 marker 的 VirtualHostStyle 後端，使用 `nonempty`。
- 如果你想完全使用 prefix 風格行為，並且不需要持久化空目錄，可以使用 `none`。

`normalize_encoding_chars` 用來控制 RAGFS 在發起 S3 請求前需要重寫哪些字元：

- 預設值是 `"?#%+@"`，所以只會轉義 `?`、`#`、`%`、`+`、`@`。
- 被轉義的位元組會編碼成 `!HH`，其中 `HH` 是該位元組的大寫十六進位制值。
- 沒有列在 `normalize_encoding_chars` 裡的字元，包括中文和其他 Unicode 字元，都會保持原樣。
- 設為 `""` 時，會在 object key 中保留原始路徑段。

`auto_detect_content_type` 預設關閉，以相容歷史行為。開啟後，RAGFS 會根據 object key / 檔名字尾推斷 MIME 型別，並寫入 S3 物件的 `Content-Type`：

- 探測依據是 object key / 檔名字尾，不做檔案內容 sniff。
- key 以 `/` 結尾的目錄 marker 不會寫 `Content-Type`。
- 無法識別的字尾會回退到 `application/octet-stream`。

示例：

```json
{
  "storage": {
    "agfs": {
      "backend": "s3",
      "s3": {
        "bucket": "my-bucket",
        "endpoint": "s3.amazonaws.com",
        "region": "us-east-1",
        "access_key": "your-ak",
        "secret_key": "your-sk",
        "auto_detect_content_type": true
      }
    }
  }
}
```

<details>
<summary><b>PathStyle S3</b></summary>
支援 PathStyle 模式的 S3 儲存， 如 MinIO、SeaweedFS.

```json
{
  "storage": {
    "agfs": {
      "backend": "s3",
      "s3": {
        "bucket": "my-bucket",
        "endpoint": "s3.amazonaws.com",
        "region": "us-east-1",
        "access_key": "your-ak",
        "secret_key": "your-sk",
        "normalize_encoding_chars": "?#%+@"
      }
    }
  }
}
```
</details>


<details>
<summary><b>VirtualHostStyle S3</b></summary>
支援 VirtualHostStyle 模式的 S3 儲存， 如 TOS.

```json
{
  "storage": {
    "agfs": {
      "backend": "s3",
      "s3": {
        "bucket": "my-bucket",
        "endpoint": "s3.amazonaws.com",
        "region": "us-east-1",
        "access_key": "your-ak",
        "secret_key": "your-sk",
        "use_path_style": false,
        "directory_marker_mode": "nonempty",
        "normalize_encoding_chars": "?#%+@"
      }
    }
  }
}
```

</details>

##### 依大小分層儲存 {#size-tiered-storage}

物件儲存對每個物件都有固定成本。MinIO 的每個物件都會在其 erasure set 的每顆磁碟寫入中繼資料，大量小物件會造成 inode 壓力、列表變慢、修復（heal）時間變長，因此維運團隊常要求物件至少 1 MiB。但使用者經常上傳小檔（程式碼、詞彙表、領域筆記），OpenViking 本身也會在每個目錄寫入很小的 `.abstract.md`、`.overview.md`、`.meta.json`、`.relations.json`。

啟用 `tiered.enabled` 後，RAGFS 會把所有小於 `small_threshold_bytes` 的檔案**以及路徑索引**存進 MariaDB（或 MySQL），只有較大的檔案才寫入 S3。使用者仍可上傳任意大小的檔案，而 bucket 永遠不會收到小於門檻的物件。

```
CachedFileSystem（Redis，可選）→ TieredFileSystem → { MariaDB：索引 + 小於 1 MiB 的檔案 | S3：≥ 1 MiB 的檔案 }
```

| 欄位 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `enabled` | bool | 為 S3 掛載啟用分層 | `false` |
| `small_threshold_bytes` | int | 小於此大小的檔案留在 MariaDB（上限 8 MiB） | 未設定（1 MiB） |
| `dsn_env` | str | 存放 DSN `mysql://user:pass@host:3306/db` 的環境變數名稱 | 未設定（`RAGFS_TIERED_DSN`） |
| `table` | str | 索引資料表名稱（英數字與 `_`） | 未設定（`agfs_entries`） |
| `max_connections` | int | MariaDB 連線池大小（1–256） | 未設定（16） |
| `import_existing` | bool | 啟動時為分層前就存在於 bucket 的物件建立索引（見下文） | `false` |

```json
{
  "storage": {
    "agfs": {
      "backend": "s3",
      "s3": {
        "bucket": "openviking",
        "endpoint": "http://minio:9000",
        "region": "us-east-1",
        "access_key": "${S3_ACCESS_KEY}",
        "secret_key": "${S3_SECRET_KEY}",
        "directory_marker_mode": "none",
        "tiered": { "enabled": true }
      }
    }
  }
}
```

啟動服務時在環境變數中提供 DSN，例如 `RAGFS_TIERED_DSN=mysql://openviking:<password>@mariadb:3306/openviking`。DSN 只從環境變數讀取，不會寫進 `ov.conf`。若要強制 TLS，加上 `?ssl-mode=VERIFY_CA&ssl-ca=/path/ca.pem`。資料表會在首次啟動時建立。若啟用了分層但環境變數不存在，掛載會在啟動時直接失敗，不會悄悄退回未分層的儲存。compose 檔內附 `mariadb` sidecar：`docker compose --profile tiered up -d mariadb`。

運作方式：

- **大檔使用不可變的 blob key。** 大檔存在 bucket 的 `_blobs/<xx>/<uuid>` 下，由 MariaDB 記錄每個路徑對應的 key。rename、move、replace 都只更新資料列，不做 S3 複製。
- **MariaDB 是唯一的事實來源。** 大檔寫入順序：先上傳 blob，再更新資料列，最後刪除舊 blob。刪除順序：先刪資料列，再刪 blob。當機最多留下沒被引用的 blob，不會出現指向不存在內容的路徑。
- **目錄列表來自 MariaDB，** 所以 `ls`、`stat`、`tree` 不會呼叫 S3 LIST。
- 請將 `directory_marker_mode` 設為 `none`。目錄已存在 MariaDB，marker 物件只會多出零位元組物件。

**git 歷史（快照）。** 啟用分層後，OpenViking 會另外掛載 `/ovgit`：同一個 bucket 上的第二個分層掛載，S3 prefix 為 `.ovgit`，資料表為 `agfs_git_entries`（或 `<table>_git`）。此時 `git.backend` 預設為 `agfs`，git 物件、分支指標和 commit 索引都經由這個掛載儲存，因此小的 git 物件（通常約 1 KB）同樣進 MariaDB。分層啟用時會拒絕 `git.backend: "s3"`，因為它會把每個 git 物件直接寫進 bucket。`local` 仍可使用，但只適用單一實例。`/ovgit` 的配置與舊的 S3 git 後端相同（`.ovgit/{account}/objects/…`），所以 `import_existing` 也會一併遷移既有的 git 歷史。

MariaDB 設定：`max_allowed_packet` ≥ 16 MiB（MariaDB 預設值）、`innodb_file_per_table=ON`，以及對該資料庫具備 `CREATE, SELECT, INSERT, UPDATE, DELETE` 權限的使用者。請將 MariaDB 與 bucket 一起備份；還原時多出沒被引用的 blob 是安全的。

設定 Redis 快取（`cache.provider = "redis"`）時，快取會包在分層掛載外層，常用的小檔與目錄列表直接由 Redis 回應。請讓快取策略的 `max_file_size` 接近分層門檻，避免 Redis 存放數 MB 的值。

**現有 bucket。** 若索引是空的但 bucket 已有物件，掛載會拒絕啟動，現有檔案不會悄悄從視圖中消失。遷移時，只需在一次啟動中設定 `import_existing: true`：小檔會複製進 MariaDB 並刪除原物件；大檔則就地建立索引，資料列直接指向原本的物件 key，不做任何複製。匯入中途當機後可以安全地重跑。完成後請關閉此選項，因為每次執行都會列出整個 bucket。

限制：分層不支援 multi-write（`backups`）掛載。

#### vectordb

向量庫儲存的配置

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `backend` | str | VectorDB 後端型別: 'local'（基於檔案）, 'http'（遠端服務）, 'cuvs'（本地儲存 + GPU dense search）、'opengauss'（openGauss DataVec）或 'elasticsearch'（Elasticsearch 8.x） | "local" |
| `name` | str | VectorDB 的集合名稱 | "context" |
| `url` | str | 'http' 型別的遠端服務 URL（例如 `http://localhost:5000`） | null |
| `project_name` | str | 專案名稱（別名 project） | "default" |
| `distance_metric` | str | 向量相似度搜索的距離度量（例如 'cosine', 'l2', 'ip'） | "cosine" |
| `dimension` | int | 向量嵌入的維度 | 0 |
| `sparse_weight` | float | 混合向量搜尋的稀疏權重，僅在使用混合索引時生效 | 0.0 |
| `elasticsearch` | object | 'elasticsearch' 後端的配置，見下文 | - |
| `cuvs` | object | NVIDIA cuVS 配置，也用於在 'local' 下顯式開啟視訊記憶體感知自動模式，參見 [cuVS 使用指南](./16-cuvs.md) | - |

預設使用本地模式
```
{
  "storage": {
    "vectordb": {
      "backend": "local"
    }
  }
}
```

<details>
<summary><b>Elasticsearch</b></summary>
使用 Elasticsearch 8.12+ 叢集的 `dense_vector` kNN 搜尋儲存向量（預設的 `bbq_hnsw` 索引型別需要 8.18+）。安裝用戶端：`pip install "openviking[elasticsearch]"`。

```json
{
  "storage": {
    "vectordb": {
      "backend": "elasticsearch",
      "name": "context",
      "distance_metric": "cosine",
      "elasticsearch": {
        "hosts": ["https://es.example.com:9200"],
        "api_key": "your-api-key",
        "index_prefix": "openviking_"
      }
    }
  }
}
```

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `hosts` | list[str] | Elasticsearch 節點位址 | `["http://127.0.0.1:9200"]` |
| `api_key` | str | API Key；不能與 `username`/`password` 同時設定 | null |
| `username` / `password` | str | Basic 認證憑據，需同時設定 | null |
| `ca_certs` | str | 用於 TLS 校驗的 CA 憑證路徑 | null |
| `verify_certs` | bool | 是否校驗 TLS 憑證 | true |
| `request_timeout` | float | 請求逾時（秒） | 30 |
| `index_prefix` | str | 索引名稱字首；索引名稱為 `<index_prefix><name>`，必須為小寫 | "openviking_" |
| `number_of_shards` | int | 每個索引的主分片數 | 1 |
| `number_of_replicas` | int | 每個索引的副本數；未設定時使用叢集預設值（單節點叢集請設為 `0`） | null |
| `refresh` | str | 寫入重新整理策略：`wait_for`（寫入後下一次搜尋可見）、`true` 或 `false` | "wait_for" |
| `index_type` | str | `dense_vector` 索引型別：`bbq_hnsw`、`bbq_flat`、`hnsw`、`int8_hnsw`、`flat` 或 `int8_flat`。`bbq` 型別需要 Elasticsearch 8.18+ 且至少 64 維；`flat` 型別需要 8.13+ | "bbq_hnsw" |
| `m` / `ef_construction` | int | HNSW 建構引數 | 16 / 100 |
| `num_candidates` | int | 每個分片的最少 kNN 候選數（會提高到請求的 k） | 100 |
| `bulk_batch_size` | int | 每個 bulk 請求的文件數 | 500 |
| `rescore_oversample` | float | 對 `bbq` 索引型別，kNN 會用原始向量對每個分片的 `k × rescore_oversample` 個候選重新評分；設為 `null` 停用 | 3.0 |

- 預設的 `bbq_hnsw` 以 1-bit 二值量化儲存向量（記憶體約為 `hnsw` 的 1/32），並用原始向量對前幾名候選重新評分，因此回傳的相似度與其他索引型別一致。需要 Elasticsearch 8.18 或更新版本；較舊的叢集請將 `index_type` 設為 `hnsw`。Embedding 少於 64 維時預設會回退為 `hnsw`，明確指定 `bbq` 型別則會報錯。索引型別在建立集合時固定，既有集合保持原型別。
- `distance_metric` 對應 `dense_vector` 的 similarity：`cosine` → `cosine`、`l2` → `l2_norm`、`ip` → `max_inner_product`。該值在建立索引時固定，修改需要新建 collection。
- 稀疏/混合檢索：建立集合時若 `sparse_weight > 0`，`sparse_vector` 欄位會對映為 `rank_features`。評分方式與本地引擎一致：`(1 - sparse_weight) × dense 相似度 + sparse_weight × 稀疏內積`，候選集為 kNN 與稀疏召回結果的聯集（各召回請求視窗的 3 倍）。不帶 dense 向量的查詢為純稀疏檢索。稀疏對映在建立索引時固定；若要在既有集合上啟用，需要重建索引到新集合。純 dense 集合會忽略稀疏查詢向量。
- `rank_features` 只能儲存正權重，因此權重為零或負數的稀疏詞項在寫入和查詢時會被丟棄。
- 不支援多模態檢索。
- 使用 `cosine` 時，embedding 全為 0 的記錄（部分 embedder 對空文字會傳回全 0 向量）儲存時不帶向量：可被過濾查詢到，但不會出現在向量檢索結果中。
- 單次向量檢索最多傳回 10000 筆（`limit + offset`）；過濾和排序查詢透過 `search_after` 翻頁，不受此限制。
- OpenViking 以嚴格 mapping 建立索引，並將中繼資料儲存在 mapping 的 `_meta` 中；不會接管非 OpenViking 建立的既有索引。
</details>

##### ACL schema

ACL 只維護在 context collection。除 `acl_mode: string`（`none`、`inherit` 或 `restricted`）外，需要以下 `list<string>` 標量索引欄位：

```text
acl_direct_grants
acl_inherited_grants
```

每個元素使用 `{mask}:{principal}` 格式，其中 `1` 表示 `read`、`3` 表示 `write`、`7` 表示 `manage`。

本地 backend 會在啟動時為存量 collection 增加欄位並重建標量索引。舊記錄不做全量回填；缺失 ACL 欄位按 `acl_mode=none` 和空列表讀取。

遠端 backend 的存量 collection 需要由部署方預先新增這些欄位和 scalar index，OpenViking 只校驗 schema。許可權模型詳見 [資源訪問控制（ACL）](../concepts/15-acl.md)。



## 配置文件

OpenViking 使用兩個配置檔案：

| 配置檔案 | 用途 | 預設路徑 |
|---------|------|---------|
| `ov.conf` | OpenViking Server 配置 | `~/.openviking/ov.conf` |
| `ovcli.conf` | HTTP 客戶端和 CLI 連線遠端服務端 | `~/.openviking/ovcli.conf` |

配置檔案放在預設路徑時，OpenViking 自動載入，無需額外設定。

> **Root key 雙檔案規則：** `ov.conf` 中的 `server.root_api_key` 是服務端
> 接受的憑據；`ovcli.conf` 中的 `root_api_key` 是 `ov --sudo` 使用的客戶端
> 副本。如果該 CLI 用於管理這個服務端，兩處值必須一致，並在輪換時同時更新。
> 普通租戶資料使用的 `api_key` 仍是另一把 user/admin 憑據。

### 配置過載邊界

服務端只在程序啟動時讀取 `ov.conf`，不會監聽檔案變化。修改 `embedding`、
`vlm`、`rerank`、`retrieval`、`storage` 或 `server` 配置後，需要重啟
OpenViking 服務。已經執行中的佇列任務不會自動遷移到新配置；請使用部署環境
原有的服務管理方式重啟，並在服務恢復後執行 `openviking-server doctor` 驗證。

`ovcli.conf` 屬於客戶端配置。新的 `ov` 命令或新建的 HTTP client 會讀取當前
檔案；已經執行中的 client 或外掛可能繼續使用構造時載入的連線與憑據，修改後
應重啟對應客戶端或外掛。

如果配置檔案在其他位置，有兩種指定方式：

```bash
# 方式一：環境變數
export OPENVIKING_CONFIG_FILE=/path/to/ov.conf
export OPENVIKING_CLI_CONFIG_FILE=/path/to/ovcli.conf

# 方式二：命令列引數（僅 serve 命令）
openviking-server --config /path/to/ov.conf
```

### ov.conf

本文件上方各配置段（embedding、vlm、rerank、storage）均屬於服務端的 `ov.conf`。

如需配置 memory 相關行為，可在 `ov.conf` 中新增 `memory` 段：

```json
{
  "memory": {
    "custom_templates_dir": "/path/to/custom-memory"
  }
}
```

| 欄位 | 說明 | 預設值 |
|------|------|--------|
| `version` | 已廢棄且會被忽略。OpenViking 始終使用 v3 記憶抽取鏈路；已有配置中保留該欄位仍可正常載入，不會報錯。 | `"v3"` |
| `custom_templates_dir` | 自定義 memory schema 目錄。後加載的同名 `memory_type` 會覆蓋內建定義，新型別會追加；詳見 [Prompt 指南](10-prompt-guide.md)。 | `""` |
| `extraction_enabled` | session commit 時是否執行長期記憶抽取。 | `true` |
| `session_skill_extraction_enabled` | session commit 時是否同時抽取可複用 skill 到當前使用者的 skill 目錄。 | `false` |
| `link_enabled` | 記憶抽取是否寫入和解析 memory links。 | `false` |
| `session_auto_commit` | 服務端 session 自動 commit 的全域控制項。該配置屬於 `memory` 段，不屬於 `server` 段；詳見 [Session Auto Commit 配置](#session-auto-commit-配置)。 | 見下文 |

#### 記憶連結（`memory.link_enabled`）

`memory.link_enabled` 預設為 `false`。啟用後，抽取流程將臨時 page ID 解析為 URI，並把連結存入記憶後設資料。每條連結包含 `from_uri`、`to_uri`、`link_type`（預設 `related_to`）、`weight`（預設 `0.5`，抽取時限制在 0–1）、`match_text`（對話中的一個詞或 `null`）、`description` 和 `created_at`。

`link_type` 是關係標籤，不是封閉列舉。抽取時將其歸一化為小寫 snake_case，允許一到三個字母單詞；無效標籤回退為 `related_to`。這些連結描述記憶間的關係；當前檢索流程不遍歷連結，也不使用連結權重排序。

#### Session Auto Commit 配置

`memory.session_auto_commit` 用於控制服務端 session 自動 commit 的全域行為。

```json
{
  "memory": {
    "session_auto_commit": {
      "enabled": false,
      "idle_backend": "local",
      "check_interval_seconds": 600.0,
      "scan_rate_limit_files_per_second": 2.0
    }
  }
}
```

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `enabled` | bool | 自動 commit 總開關。開啟後：未顯式傳入 `auto_commit_policy` 的新 session 會套用預設 policy，同時啟動後臺 idle 掃描器；關閉後兩者都不發生 | `false` |
| `idle_backend` | string | idle 超時發現後端：`local` 掃描 session 後設資料；`redis` 使用分散式 expiry 排程 | `local` |
| `check_interval_seconds` | float | 兩輪 idle 掃描之間的最小間隔，單位秒，必須大於 `0` | `600.0` |
| `scan_rate_limit_files_per_second` | float | idle 掃描時每秒最多讀取的 session `.meta.json` 檔案數，必須大於 `0`，用於限制大量 session 掃描時的儲存 IO 壓力 | `2.0` |

說明：

- `memory.session_auto_commit` 是服務端全域配置，不是單個 session 的業務 policy。
- session 級別的自動觸發引數通過 session 級 `auto_commit_policy` 設定（見下表）。可以在建立 session 時通過 `POST /api/v1/sessions` 設定，也可以通過 `PATCH /api/v1/sessions/{session_id}/config` 部分更新。PATCH 時省略 `auto_commit_policy` 會保留現有策略，傳 `null` 會停用自動 commit；通過 `GET /api/v1/sessions/{session_id}` 檢視生效策略。
- `enabled=false` 時：既無顯式 policy、也無 `server.user_config_defaults.auto_commit_policy` 的新 Session 保持 auto commit 關閉，並返回 `auto_commit_policy: null`；同時不啟動 `SessionAutoCommitScheduler`。
- `enabled=true` 時：
  - 既無顯式 policy、也無部署級預設 policy 的新 Session 會帶上下方內建 policy。
  - `idle_backend="local"` 時，`SessionAutoCommitScheduler` 啟動後立即開始掃描；掃描過程以 `scan_rate_limit_files_per_second` 為上限序列讀取 session `.meta.json`，每輪結束後至少等待 `check_interval_seconds`。
  - `idle_backend="redis"` 時，服務通過頂層 `expiry` 配置整體啟用 expiry 上報、釋出和 callback 消費。
- token 和 message-count 自動觸發在訊息寫入後內聯執行，不依賴 scheduler，但同樣以 session 是否帶有 `auto_commit_policy` 為前提。

#### 分散式 Expiry 配置

共享同一份 expiry 狀態的 API、publisher 和 callback 例項必須使用相同且穩定的 `service_name`。它表示部署的文件服務名，不是單個 Pod 名。

```json
{
  "expiry": {
    "service_name": "openviking-documents",
    "publisher_separate_process": true,
    "shard_count": 128,
    "session_consumer_concurrency": 8,
    "redis": {
      "mode": "cluster",
      "endpoints": ["redis://redis-proxy.example.com:6379"],
      "username": "openviking",
      "password_env": "OPENVIKING_EXPIRY_REDIS_PASSWORD"
    }
  }
}
```

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `service_name` | string | 使用同一份 expiry 資料的所有例項共享的穩定文件服務名 | `""` |
| `publisher_separate_process` | bool | 由 `openviking-server` 在獨立子程序中託管 publisher；為 `false` 時 publisher 在各 API 程序內執行 | `true` |
| `shard_count` | int | expiry 邏輯分片數；所有共享同一 namespace 的例項必須一致，取值範圍為 `1..512` | `128` |
| `session_consumer_concurrency` | int | 每個 API 程序中 Session expiry callback 的併發數，必須大於 `0` | `8` |
| `redis.mode` | string | Redis 部署模式：`standalone` 或 `cluster` | `standalone` |
| `redis.endpoints` | string array | Redis 地址；叢集模式可以只配置一個統一 proxy 地址 | `[]` |
| `redis.username` | string | Redis ACL 使用者名稱 | `""` |
| `redis.password_env` | string | 儲存 Redis 密碼的環境變數名；變數不存在時啟動失敗 | `""` |
| `redis.password` | string | 相容用明文密碼；建議使用 `password_env`，兩者互斥 | `""` |

啟用 Redis idle auto commit 時必須配置 `service_name` 和 Redis 地址。使用者名稱與密碼只能使用上述獨立欄位，不能寫入 endpoint URI。預設 `publisher_separate_process=true` 時，`openviking-server` 會在開始服務前拉起一個內部 publisher 子程序，在服務關閉時停止它，並在子程序異常退出時一併退出。publisher 不再暴露為公共 CLI 命令。

##### 單 session 自動 commit 策略

當 session 帶有 `auto_commit_policy` 時，未傳的欄位會回退到下方內建預設值。沒有儲存 policy 的 session 保持 auto commit 關閉。除 idle 超時的寫入下限外，取值會被 clamp 到 `[0, 上限]`；未知欄位會以 `InvalidArgumentError` 拒絕。設定和檢視方式見 [Sessions API](../api/05-sessions.md#create-session)。

| 欄位 | 型別 | 預設值 | 最小值 | 上限 | 說明 |
|------|------|--------|--------|------|------|
| `pending_token_threshold` | int | 150000 | 0 | 1000000 | 當未提交的 pending token 超過該值（嚴格大於）時，會在訊息寫入後觸發一次自動 commit。 |
| `message_count_threshold` | int | 100 | 0 | 1000 | 當未提交的 live message 數量超過該值（嚴格大於）時，會在訊息寫入後觸發一次自動 commit。 |
| `idle_timeout_seconds` | int | 86400 | 0（關閉）或 300 | 604800 | 新傳入的正數最短為 5 分鐘；存量的小於 300 的正值繼續按原值讀取。idle 觸發的 commit 會歸檔全部積壓訊息，並忽略 `keep_recent_count`。 |
| `keep_recent_count` | int | 0 | 0 | 500 | 閾值觸發的自動 commit 後保留（不歸檔）的最近 live message 數量。idle 超時觸發的 commit 會忽略該值並歸檔所有訊息。 |
| `min_commit_interval_seconds` | int | 0 | 0 | 604800 | 兩次自動 commit 之間的最小間隔秒數（節流）。 |

程式碼入口：`openviking/session/auto_commit_policy.py:AutoCommitPolicy`。

### ovcli.conf

你可以手動編輯此檔案，也可以用 `ov config` 互動式生成。如果你維護著多個服務端的配置，可以用 `ov config switch` 在它們之間切換。

如需按步驟配置 CLI，請閱讀 [OpenViking CLI 配置指南](../getting-started/05-cli-setup.md)。

HTTP 客戶端（`SyncHTTPClient` / `AsyncHTTPClient`）和 CLI 工具連線遠端服務端的配置檔案：

```json
{
  "url": "http://localhost:1933",
  "api_key": "your-secret-key",
  "profile": false,
  "upload": {
    "mode": "local",
    "ignore_dirs": "node_modules,.cache,.nx",
    "include": "*.md,*.pdf",
    "exclude": "*.tmp,*.log"
  }
}
```

| 欄位 | 說明 | 預設值 |
|------|------|--------|
| `url` | 服務端地址 | （必填） |
| `api_key` | 通常填寫用於資料訪問的 user/admin key。API Key 模式下，這裡填 root key 只能呼叫管理 API | `null`（無認證） |
| `root_api_key` | `ov` CLI 帶 `--sudo` 時使用的 root key；CLI 在 `api_key` 未設定時也會回退到它。Python HTTP SDK 不使用該回退 | `null` |
| `account` | 可選的 trusted 模式 account 身份 header | `null` |
| `user` | 可選的 trusted 模式 user 身份 header | `null` |
| `profile` | 是否預設給 HTTP 請求追加 `profile=1`。對 Python HTTP client 和 `ov` CLI 都生效；也可通過 CLI 的 `--profile` 單次開啟。是否真正生效還取決於服務端是否開啟 `server.profile_enabled`。 | `false` |
| `upload.ignore_dirs` | `add-resource` 預設忽略目錄列表（CSV） | `null` |
| `upload.include` | `add-resource` 預設包含模式（CSV） | `null` |
| `upload.exclude` | `add-resource` 預設排除模式（CSV） | `null` |
| `upload.mode` | Python HTTP client 的臨時上傳後端：`"local"`（僅當前例項本地磁碟）或 `"shared"`（分散式共享儲存）。Rust `ov` CLI 不讀取這個欄位；如需 shared 上傳，請設定 `OPENVIKING_UPLOAD_MODE=shared`。 | `null`（使用服務端 `temp_upload.default_mode`，預設仍為 `"local"`） |

本地目錄上傳會預設遵循 `.gitignore`（根目錄和子目錄，含 `!` 反向規則）。`ignore_dirs/include/exclude` 會在此基礎上進一步過濾。

trusted 閘道器部署下，也可以在單次命令裡用 CLI 引數覆蓋這些身份欄位：

```bash
ov --account acme --user alice ls viking://
```

對於 `add-resource`，上傳過濾引數會與 `ovcli.conf` 預設值做合併（追加），不會覆蓋：

```bash
# ovcli.conf: upload.exclude="*.log"
ov add-resource ./docs --exclude "*.tmp"
# 實際傳送給服務端的 exclude: "*.log,*.tmp"
```

詳見 [服務部署](./03-deployment.md)。

## server 段

將 OpenViking 作為 HTTP 服務執行時，在 `ov.conf` 中新增 `server` 段：

```json
{
  "server": {
    "host": "127.0.0.1",
    "port": 1933,
    "auth_mode": "api_key",
    "root_api_key": "your-secret-root-key",
    "account_store": {
      "provider": "file",
      "params": {}
    },
    "profile_enabled": false,
    "cors_origins": ["*"],
    "public_base_url": "https://ov.example.com",
    "upload_signed_ttl_seconds": 600,
    "temp_upload": {
      "default_mode": "local",
      "shared_max_size_bytes": 536870912,
      "ttl_seconds": 43200
    },
    "user_config_defaults": {
      "add_targets": {
        "resource_uri": "viking://~/resources",
        "skill_uri": "viking://~/skills"
      },
      "memory_policy": {
        "memory_types": ["profile", "preferences", "events", "entities", "experiences"]
      }
    },
    "agent_evolution": {
      "enabled": false
    }
  }
}
```

| 欄位 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `host` | str | 繫結地址 | `127.0.0.1` |
| `port` | int | 繫結埠 | `1933` |
| `auth_mode` | str / null | 內建模式：`"dev"`、`"api_key"`、`"trusted"`、`"oidc"`、`"ldap"`。省略或設為 null 時，有非空 `root_api_key` 則推導為 `api_key`，否則為 `dev`。 | `null` |
| `root_api_key` | str | `api_key` 模式必填的 Root API Key；`trusted` 模式在所有部署中均必填，包括 localhost，不負責解析普通使用者身份 | `null` |
| `account_store.provider` | str | 完整 Account Store Provider。內建 `"file"`、`"mysql"` 和 `"redis_mysql"`；統一持久化 Account、User、Group 和 API Key。`"file"` 相容現有 AGFS JSON 登錄檔，並由 Provider 自身維護程序內查詢索引。`"redis_mysql"` 保持 MySQL 為權威儲存，並增加共享 Redis 認證和請求身份讀取快取。 | `"file"` |
| `account_store.params` | object | Provider 啟動引數。不能通過這裡覆蓋框架注入的 VikingFS 和 File Provider API Key Hash 配置。 | `{}` |
| `profile_enabled` | bool | 是否允許 HTTP 請求通過 `profile=1` 開啟請求級 cProfile。關閉時服務端會忽略該請求引數；開啟後，CLI 可以顯示返回的 `profile`，而 Python HTTP client 預設只觸發服務端 profile，不會把頂層 `profile` 欄位自動附著到大多數 SDK 返回值上。 | `false` |
| `cors_origins` | list | CORS 允許的來源 | `["*"]` |
| `public_base_url` | str | MCP `add_resource` 和 `add_skill` 工具向客戶端返回的上傳指令裡使用的對外可見 base URL。解析順序：環境變數 `OPENVIKING_PUBLIC_BASE_URL` → 本欄位 → 請求頭 `X-Forwarded-Host` / `X-Forwarded-Proto` → 請求頭 `Host` → 監聽地址兜底。當 server 部署在反向代理後且代理不轉發 `X-Forwarded-*` 時，請顯式設定本欄位（或環境變數）。 | `null` |
| `upload_signed_ttl_seconds` | int | MCP `add_resource` 和 `add_skill` 為本地檔案上傳 mint 的一次性 token 的過期時間（秒），走 `POST /api/v1/resources/temp_upload?token=...`；MCP `download` 為 `GET /api/v1/content/download?token=...` mint 的一次性 token 也用這個時長。 | `600`（10 分鐘） |
| `temp_upload.default_mode` | str | `POST /api/v1/resources/temp_upload` 的服務端預設模式（客戶端未顯式傳 `upload_mode` 時使用）：`"local"`（僅當前例項本地磁碟，單機預設行為）或 `"shared"`（分散式共享儲存，多副本部署可跨例項消費）。新的 shared 上傳會固定寫入內部 `viking://upload/<created_at_ms>-<uuid>/content` 和 `meta` 物件，在 `ttl_seconds` 指定的時間內可重複消費。 | `"local"` |
| `temp_upload.shared_max_size_bytes` | int | `shared` 模式下接受的最大檔案大小（位元組）。超過此閾值的請求會在寫入物件儲存之前被拒絕。 | `536870912`（512 MiB） |
| `temp_upload.ttl_seconds` | int | local 和 shared 臨時上傳檔案共用的保留時間（秒）。每次對應模式的上傳會清理超過此時間的檔案；shared 只需一次上傳根目錄列舉，從每個一級目錄名解析建立時間，並遞迴刪除過期目錄，不依賴檔案系統修改時間；設為 `0` 時停用自動清理。 | `43200`（12 小時） |
| `user_config_defaults.add_targets.resource_uri` | str | `add_resource` 未傳 `to` 和 `parent` 時使用的部署級預設資源新增目錄。`viking://~/...` 會按請求使用者解析。 | `null` |
| `user_config_defaults.add_targets.skill_uri` | str | `add_skill` 未傳 `target_uri` 時使用的部署級預設技能新增根目錄。僅允許 `viking://~/skills` 和 `viking://agent/skills`。 | `null` |
| `user_config_defaults.memory_policy` | object | Session 和 User 都未顯式配置策略時使用的部署級預設記憶抽取策略。 | `null` |
| `user_config_defaults.auto_commit_policy` | object | 新建 Session 未顯式指定策略時使用的部署級自動 Commit 預設策略。 | `null` |
| `agent_evolution.enabled` | bool | Agent 進化的叢集啟動預設值，執行時可由 Account 或 Cluster Admin settings 覆蓋。開啟時，session commit 可按 session `memory_policy` 生成或更新 cases、trajectories 和 experiences；關閉後已有記憶仍可讀取和檢索。 | `false` |

MySQL Provider 預設儲存高熵 API Key 的帶版本 SHA-256 摘要，並通過獨立摘要索引
進行固定成本查詢。將 `credential_storage` 設為 `"encrypted"` 可改用 AES-GCM
可逆加密；此時必須提供 `credential_encryption_key`，其值為 base64 編碼的
32 位元組金鑰。MySQL 不會持久化 API Key 原文。雜湊模式的使用者列表只展示 key
prefix；加密模式可為同一列表工作流解密展示 key。`credential_storage` 僅決定
新寫入憑證的格式，讀取時根據每條記錄的 `material` 字首選擇解碼方式。從加密模式
遷移到雜湊模式時，應保留 `credential_encryption_key`，直到所有舊加密憑證完成
輪換。`aesgcm:v1` 記錄不包含 key id，因此不支援直接替換該加密金鑰。

安裝 MySQL extra 後，通過頂層 `service_name` 配置部署名稱。該值會寫入每張
Account Store 表的 `service_name` 列，並在多個 OpenViking 叢集共用一個資料庫時
充當隔離邊界。修改 `service_name` 會選擇另一組邏輯 Account Store 分割槽。

Provider 不會建立或遷移資料庫表。啟動服務前，應通過現有 DBA 或部署流程手工建立
`openviking/server/account_stores/sql/init.sql` 中定義的規範化表。後續經評審的
schema 變更按順序存放於 `openviking/server/account_stores/sql/changes/`。
五張 `ov_accounts*` 表的名稱固定；多個 OpenViking 叢集共用資料庫時，通過不同的
頂層 `service_name` 隔離部署，不使用不同表字首。

```json
{
  "service_name": "production",
  "server": {
    "account_store": {
      "provider": "mysql",
      "params": {
        "host": "db.example.com",
        "user": "openviking",
        "password": "secret",
        "database": "openviking",
        "credential_storage": "encrypted",
        "credential_encryption_key": "base64-encoded-32-byte-key"
      }
    }
  }
}
```

`redis_mysql` 需要安裝 `redis-mysql` extra，並在引數中巢狀同一份 MySQL 配置。
其 `cache` 配置沿用頂層 `cache` 的 `provider/params` 結構，目前 Python
客戶端支援 `standalone`、`cluster` 和 `sentinel` 三種 Redis 部署模式。
它預設以固定 60 秒 TTL 快取 API Key 繫結、User、每個 User 的 Group ID 和刪除記錄。
快取重建與同一 Account 的修改共用 Redis 租約，正常快取命中不獲取該租約。修改會先
提交 MySQL，再失效相關快取。Redis 不可用時 MySQL 修改仍會成功，遺留快取最多保持到
固定 TTL 到期。快取回填同時維護 Account
級、按過期時間排序的 key 索引；每次寫入已索引快取時會清理過期成員，因此刪除或重建
Account 時只會清理該 Account 當前的 User、Group、刪除記錄和憑據快取。API Key 繫結會
校驗 Account 和 User 的憑據 fence，所以正常的換 Key、吊銷和刪 User 會使舊繫結失效。
索引的最後一個有序集合成員被移除後，Redis 會自動刪除空索引；清理結束時不再單獨刪除
索引，避免失去租約的舊請求誤刪新回填的索引。建立身份或換 Key 會同時清除攜帶和未攜帶
User 提示的負快取。
Redis 連線和命令超時通過 `cache.params.connect_timeout_ms` 和
`cache.params.command_timeout_ms` 配置，未配置時均為 5000 毫秒；這不是整個請求的總超時。

```json
{
  "server": {
    "account_store": {
      "provider": "redis_mysql",
      "params": {
        "mysql": {
          "host": "db.example.com",
          "user": "openviking",
          "password": "secret",
          "database": "openviking"
        },
        "cache": {
          "provider": "redis",
          "params": {
            "mode": "sentinel",
            "endpoints": [
              "rediss://sentinel-1.example.com:26379",
              "rediss://sentinel-2.example.com:26379",
              "rediss://sentinel-3.example.com:26379"
            ],
            "master_name": "openviking",
            "username": "openviking",
            "password_env": "OPENVIKING_REDIS_PASSWORD",
            "sentinel_password_env": "OPENVIKING_SENTINEL_PASSWORD",
            "key_prefix": "ov:account-auth",
            "ttl_seconds": 60,
            "lock_ttl_seconds": 60,
            "lock_wait_seconds": 30
          }
        }
      }
    }
  }
}
```

省略 `auth_mode`（或設為 `null`）時，配置了非空 `root_api_key` 則選擇 `api_key`，否則選擇 `dev`。`dev` 僅允許監聽 localhost，不進行身份認證。`root_api_key` 不能配置為空字串。

顯式設定 `auth_mode: "api_key"` 時，包括 localhost 在內都必須提供非空 `root_api_key`；缺少該 key 會導致啟動失敗，不會回退到開發模式。使用 root key 呼叫 Admin API 建立 account 和 user/admin key，資料訪問使用這些繫結租戶身份的 key。`trusted` 模式接受可信網關注入的 account/user 身份頭，無需預先建立 user key；其 root key 在啟動和每個認證請求中均必填，包括 localhost。角色解析、OIDC/LDAP 配置與閘道器要求參見 [身份認證](04-authentication.md)。

`user_config_defaults` 提供新增目標和記憶抽取的部署級預設配置。新增操作中，顯式請求目標仍然優先：`add_resource.to` / `add_resource.parent` 優先於使用者預設值，`add_skill.target_uri` 優先於使用者預設值。記憶策略優先順序為 Session 策略 > User `settings/user_config.json` 策略 > `server.user_config_defaults.memory_policy` > 核心預設策略。`server.agent_evolution.enabled` 提供啟動預設值，執行時優先順序為 Account 覆蓋 > Cluster 執行時覆蓋 > 啟動值。無需重啟的修改應使用 Admin settings 介面；直接編輯 `ov.conf` 需要重啟後生效。

支援的 add target URI：

- `resource_uri` 作為 `add_resource` 的預設父目錄使用，等價於 `parent=<uri>, create_parent=true`。它必須是當前請求使用者可寫的 resource 目錄 URI，支援 `viking://resources` 或 `viking://resources/...`、`viking://~/resources` 或 `viking://~/resources/...`、`viking://user/{user_id}/resources` 或 `viking://user/{user_id}/resources/...`、`viking://user/{user_id}/peers/{peer_id}/resources` 或 `viking://user/{user_id}/peers/{peer_id}/resources/...`。`viking://~/...` 家目錄別名會按請求使用者解析。
- `skill_uri` 作為 `add_skill` 的預設目標根目錄使用。v1 只允許 `viking://~/skills` 和 `viking://agent/skills`；不支援顯式寫成 `viking://user/{user_id}/skills`。
- 舊寫法相容：早期配置中的 `viking://user/resources` 和 `viking://user/skills` 會在配置載入時自動歸一化為 `viking://~/resources` 和 `viking://~/skills`，並列印一條 info 日誌。新配置請直接使用 `viking://~/...`；在 `add_targets` 之外，無 uid 的寫法會在請求入口被拒絕。

### 執行時配置來源 {#runtime-configuration-source}

頂層 `runtime_config` 在啟動時選擇執行時配置來源，不放在 `server` 內。

| 欄位 | 預設值 | 含義 |
| --- | --- | --- |
| `source` | `"file"` | `file` 通過 AGFS 儲存配置；`memory` 只儲存在當前程序中；也可填寫已註冊的自定義來源名稱。 |
| `module` | `null` | 用於註冊自定義來源的 Python 模組。來源也可通過 `openviking.config_source` entry-point group 註冊。 |
| `params` | `{}` | 通過 `ConfigSourceContext.params` 傳給自定義來源工廠的引數。 |

自定義來源實現 `ConfigSource.load(scope)`、`update(scope, mutate)` 和 `delete(scope)`。來源必須防止併發讀改寫丟失更新，包括跨執行緒和事件迴圈的呼叫。更新回呼可能被重試，因此不能有副作用。

檔案來源在 AGFS 中把 Account 配置寫入 `/local/{account_id}/_system/setting.json`，把 Cluster 配置寫入 `/local/_system/runtime_config/cluster.json`。前一版本的位元組儲存在同目錄的 `setting.backup.json` 和 `cluster.backup.json`；主檔案丟失或無效時可讀取備份。原有 Account 配置繼續使用原路徑。

管理器每 30 秒重新整理 Cluster 和已快取的 Account。24 小時未使用的 Account 從快取移除並停止輪詢，已儲存的配置仍保留。重新整理失敗時繼續使用上一次有效配置。Admin settings GET 返回已儲存的覆蓋值，不是合併後的生效配置，也不能證明所有派生客戶端都已切換。修改配置使用 [Admin API](../api/08-admin.md)，各消費者的行為見[配置過載邊界](#配置過載邊界)。

### 工具輸出外接 {#tool-output-externalization}

`server.tool_output_externalization` 將會話中過大的工具輸出存入該會話的 `tool-results/`，訊息保留預覽 stub 和 `tool_output_ref`。完整輸出可通過[會話管理](../api/05-sessions.md)中的 tool-result read、search、list API 回讀。

| 欄位 | 預設值 | 含義 |
| --- | --- | --- |
| `enabled` | `true` | 啟用工具輸出外接。 |
| `threshold_chars` | `20000` | 單條輸出超過此字元數時外接。 |
| `preview_chars` | `2000` | 單條輸出的預覽字元目標。 |
| `assistant_turn_inline_budget_chars` | `100000` | 同一 assistant turn 中工具輸出的內聯預算。 |
| `assistant_turn_preview_budget_chars` | `10000` | 在該輪各輸出之間分配的預覽預算。 |
| `min_preview_chars` | `1000` | 分配單條預覽時的下限。 |
| `aggregate_selection_strategy` | `"largest_first"` | 目前唯一支援的策略：需要縮減該輪內聯大小時優先外接較大輸出。 |
| `failure_mode` | `"preserve_raw"` | 儲存失敗時：`preserve_raw` 保留原文；`reject` 丟擲錯誤；`preview_only` 只保留預覽，不提供可恢復原文的引用。 |

這些預算用於選擇外接輸出和分配預覽。預覽後設資料和最小預覽大小可能使結果超出預算；`preserve_raw` 在寫入失敗時也可能使該輪超出預算。

### Usage Reporter

可選的 Usage Reporter 從已 commit session 的 tool parts 中抽取記憶使用事件。內建檔案日誌 Sink 將每個事件寫成一行扁平 JSON，並按小時滾動專用日誌檔案：

```json
{
  "server": {
    "usage_reporter": {
      "enabled": true,
      "extractors": ["memory_usage"],
      "sinks": [
        {
          "type": "file_log",
          "config": {
            "path": "/var/log/openviking_usage/usage.log",
            "resource_id_env": "OV_RESOURCE_ID",
            "rotation_interval_hours": 1,
            "backup_count": 168
          }
        }
      ]
    }
  }
}
```

內建 `file_log` Sink 替代了此前的 `http` Sink。原來使用
`"type": "http"` 的部署需要遷移為 `file_log` 並採集專用日誌檔案，或配置實現
原投遞協議的 `custom` Sink。

啟動服務前需要設定 `resource_id_env` 指定的環境變數。該變數的值用於標識當前部署的 OpenViking 資源，隔離 account、user 和 URI 相同但 resource 不同的資料。Sink 會自動建立父目錄、立即追加事件、按 UTC 每小時滾動檔案，並保留 `backup_count` 個歷史檔案；它不會寫入 OpenViking 預設 stdout 日誌。

每行格式如下：

```json
{"event_time":"2026-08-05 11:30:00","tenant_id":"resource_id:ov-example;account_id:default;user_id:default;resource_uri:viking://user/default/memories/experiences/example.md","event_name":"experience.recall.count","object_id":"ue_<sha256>","count":1,"tags":{"resource_type":"experience"}}
```

`event_time` 使用 UTC 時間。`tenant_id` 由部署 resource ID、事件所屬的 account、user 和 Experience URI 拼接。`memory.recalled` 對映為 `experience.recall.count`，`memory.injected` 對映為 `experience.inject.count`。`object_id` 是穩定的 Usage Event ID。下游必須使用 `(tenant_id, object_id)` 複合鍵去重，不能跨 tenant 僅按 `object_id` 全域去重。查詢時按 `tenant_id`、`event_name` 和 `event_time` 範圍過濾，再通過 `sum(count)` 彙總。檔案採集和下游投遞仍為 best-effort。

#### 自定義 Sink

在 `server.usage_reporter.sinks` 中新增：

```json
{"type": "custom", "class_path": "my_app.usage.MySink", "config": {}}
```

該類必須能被服務端匯入。`config` 作為關鍵字引數傳給建構函式。類需實現 `async def write(self, *, events: list[UsageEvent]) -> None`；`UsageEvent` 定義於 `openviking.usage_reporter.models`，提供 `event_id` 和 `to_dict()`。輸入是事件物件列表，不是 `file_log` 輸出的扁平 JSON 行。

投遞採用 best-effort：Sink 錯誤和超時會記錄到日誌，phase-2 重放可能再次傳送同一事件。自定義 Sink 需定義重試和去重策略。若輸出檔案日誌格式，應設定 `object_id = event.event_id`，並按上述部署/account/user/resource 範圍內的 `(tenant_id, object_id)` 去重。這不是 exactly-once 投遞協議。

啟動方式和部署詳情見 [服務部署](./03-deployment.md)，認證詳情見 [認證](./04-authentication.md)。

<a id="encryption"></a>

## encryption 段

啟用靜態資料加密後，儲存層按帳戶加密新寫入的檔案，客戶端沿用現有 API。已有明文檔案不會自動加密，需單獨遷移或重寫。

```json
{
  "encryption": {
    "enabled": true,
    "provider": "local|vault|volcengine_kms"
  }
}
```

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `enabled` | bool | 是否啟用加密 | `false` |
| `provider` | str | 金鑰提供程式：`"local"`、`"vault"` 或 `"volcengine_kms"` | - |
| `api_key_hashing.enabled` | bool | 僅 File Provider：是否對 API key 欄位啟用 Argon2id 單向雜湊（與檔案級 `enabled` 獨立控制），詳見 [加密指南](./08-encryption.md) | `false` |

### Local（本地文件）

適合開發環境和單節點部署：

```json
{
  "encryption": {
    "enabled": true,
    "provider": "local",
    "local": {
      "key_file": "~/.openviking/master.key"
    }
  }
}
```

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `local.key_file` | str | 根金鑰檔案路徑 | `~/.openviking/master.key` |

### Vault（HashiCorp Vault）

適合生產環境和多雲部署：

```json
{
  "encryption": {
    "enabled": true,
    "provider": "vault",
    "vault": {
      "address": "https://vault.example.com:8200",
      "token": "vault-token-xxx",
      "mount_point": "transit",
      "key_name": "openviking-root"
    }
  }
}
```

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `vault.address` | str | Vault 服務地址 | - |
| `vault.token` | str | Vault 訪問令牌 | - |
| `vault.mount_point` | str | Transit 引擎掛載點 | `"transit"` |
| `vault.key_name` | str | 根金鑰名稱 | `"openviking-root"` |

### Volcengine KMS（火山引擎）

適合火山引擎雲部署：

```json
{
  "encryption": {
    "enabled": true,
    "provider": "volcengine_kms",
    "volcengine_kms": {
      "key_id": "kms-key-id-xxx",
      "region": "cn-beijing",
      "access_key": "AKLTxxxxxxxx",
      "secret_key": "Tmpxxxxxxxx"
    }
  }
}
```

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `volcengine_kms.key_id` | str | KMS 金鑰 ID | - |
| `volcengine_kms.region` | str | 區域 | `"cn-beijing"` |
| `volcengine_kms.access_key` | str | 火山引擎 Access Key | - |
| `volcengine_kms.secret_key` | str | 火山引擎 Secret Key | - |

加密功能的詳細說明見 [資料加密](../concepts/10-encryption.md)，完整使用流程見 [加密指南](./08-encryption.md)。

## storage.transaction 段

`storage.transaction` 已廢棄，僅保留為相容舊配置。新配置請使用 `storage.agfs.pathlock` 配置 PathLock Provider 和過期時間；Redis key 名稱來自頂層 `service_name`。若舊欄位仍然出現，OpenViking 會在執行時給出 warning；其中 `lock_timeout` 已廢棄且會被忽略，`lock_expire` 會在未顯式配置新欄位時自動對映到新的 `pathlock` 配置，`redo_recovery_enabled` 則會被忽略。

推薦寫法：

```json
{
  "storage": {
    "agfs": {
      "pathlock": {
        "provider": "filesystem",
        "lock_expire_secs": 30.0
      }
    }
  }
}
```

相容舊寫法（不推薦新專案繼續使用）：

```json
{
  "storage": {
    "transaction": {
      "lock_expire": 30.0
    }
  }
}
```

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `lock_timeout` | float | 已廢棄且忽略。執行時等待超時固定為 `0.0`。 | `0.0` |
| `lock_expire` | float | 已廢棄。改用 `storage.agfs.pathlock.lock_expire_secs`。未顯式配置新欄位時會自動對映。 | `30.0` |
| `redo_recovery_enabled` | bool | 已廢棄且忽略。當前版本的 `session.commit` phase-2 恢復由持久化 `session_commit` 佇列負責。 | `true` |

路徑鎖機制的詳細說明見 [路徑鎖與崩潰恢復](../concepts/09-transaction.md)。

## Task Tracker 持久化

任務跟蹤器記錄非同步任務狀態，適用於返回 `task_id` 的介面（任務型別包括 `session_commit`、`add_resource`、`add_skill`、`admin_reindex`）。Task 記錄寫入 AGFS，共享同一持久化儲存的例項可以查詢同一個 `task_id`，任務歷史可在重啟後訪問，但仍受保留清理策略影響。使用 `memory` 檔案儲存後端時，記錄不能跨程序重啟保留。

無需配置 `storage.task_tracker`。如果舊配置裡仍包含 `storage.task_tracker`，OpenViking 會記錄 warning 並忽略它。

Task 記錄檔案位於所屬帳號的系統目錄：

```text
/local/{account_id}/_system/tasks/{user_id}/{task_id}.json
```

## 配置結構示意

下面展示主要配置段的結構，不是可直接執行的完整配置或 JSON Schema。`string` 和用 `|` 連線的選項需要替換為實際值；沒有列出的欄位見前文各模組。

```json
{
  "embedding": {
    "max_concurrent": 10,
    "max_retries": 3,
    "text_source": "content_only",
    "max_input_tokens": 4096,
    "dense": {
      "provider": "volcengine",
      "api_key": "string",
      "model": "string",
      "dimension": 1024,
      "input": "multimodal",
      "encoding_format": "float|base64"
    }
  },
  "vlm": {
    "provider": "string",
    "api_key": "string",
    "model": "string",
    "api_base": "string",
    "thinking": false,
    "max_concurrent": 32,
    "max_retries": 3,
    "extra_headers": {},
    "extra_request_body": {}
  },
  "rerank": {
    "provider": "vikingdb|cohere|openai|litellm|jev",
    "api_key": "string",
    "model": "string",
    "api_base": "string",
    "max_input_tokens": 0,
    "threshold": 0.1,
    "extra_headers": {}
  },
  "retrieval": {
    "enable_intent": true
  },
  "encryption": {
    "enabled": false,
    "provider": "local|vault|volcengine_kms",
    "local": {
      "key_file": "~/.openviking/master.key"
    },
    "vault": {
      "address": "https://vault.example.com:8200",
      "token": "string",
      "mount_point": "transit",
      "key_name": "openviking-root"
    },
    "volcengine_kms": {
      "key_id": "string",
      "region": "cn-beijing",
      "access_key": "string",
      "secret_key": "string"
    }
  },
  "storage": {
    "workspace": "string",
    "agfs": {
      "backend": "local|s3|memory",
      "timeout": 10,
      "pathlock": {
        "provider": "filesystem",
        "lock_expire_secs": 30.0
      }
    },
    "vectordb": {
      "backend": "local|cuvs|http|opengauss|elasticsearch",
      "url": "string",
      "project": "string"
    }
  },
  "server": {
    "host": "string",
    "port": 1933,
    "root_api_key": "string",
    "account_store": {
      "provider": "file",
      "params": {}
    },
    "cors_origins": ["string"]
  }
}
```

說明：
- `storage.vectordb.sparse_weight` 用於混合（dense + sparse）索引/檢索的權重，僅在使用 hybrid 索引時生效；設定為 > 0 才會啟用 sparse 訊號。

## 故障排除

### API Key 錯誤

```
Error: Invalid API key
```

檢查 API Key 是否正確且有相應許可權。

### 維度不匹配

```
Error: Vector dimension mismatch
```

確保配置中的 `dimension` 與模型輸出維度匹配。

### VLM 超時

```
Error: VLM request timeout
```

- 檢查網路連線
- 增加配置中的超時時間
- 對偶發超時，適當增大 `vlm.max_retries`
- 嘗試更小的模型
- 如為批次匯入場景，結合降低 `vlm.max_concurrent`

### 速率限制

```
Error: Rate limit exceeded
```

先從 provider 返回的錯誤中確認限制的是請求數、token 用量還是帳戶配額，再調整請求節奏或申請相應額度。
- 優先降低 `embedding.max_concurrent` / `vlm.max_concurrent`
- 對偶發 `429` 可保留少量 `max_retries`；若希望快速失敗，可將其設為 `0`

## 相關文件

- [火山引擎購買指南](./02-volcengine-purchase-guide.md) - API Key 獲取
- [API 概覽](../api/01-overview.md) - 客戶端初始化
- [服務部署](./03-deployment.md) - Server 配置
- [上下文層級](../concepts/03-context-layers.md) - L0/L1/L2
