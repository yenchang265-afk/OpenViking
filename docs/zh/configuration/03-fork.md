# 分支相容性

本頁適用於 [`yenchang265-afk/OpenViking`](https://github.com/yenchang265-afk/OpenViking)。倉庫定期合併上游更新，同時保留 [UPSTREAM_SYNC.md](https://github.com/yenchang265-afk/OpenViking/blob/main/UPSTREAM_SYNC.md) 列出的分支決策。

## 安裝與文件範圍

PyPI 的 `openviking` 套件、官方安裝腳本、託管服務和上游版本說明描述的是上游發行版本。安裝官方套件不會安裝此分支的變更。執行本倉庫版本時，請依照[原始碼建置步驟](https://github.com/yenchang265-afk/OpenViking/blob/main/docs/repository/CONTRIBUTING_CN.md)，使用此分支的 clone URL 與預定部署的版本。部署分支映像時，請使用此分支部署檔案所設定的映像倉庫。

歷史更新日誌與效能評測描述其註明的上游版本。[火山引擎購買指南](../guides/02-volcengine-purchase-guide.md) 保留供上游使用者參考，其中的原生提供程式配置無法用於此分支。

## 服務端模型提供程式

| 元件 | 本倉庫已實作的提供程式 |
| --- | --- |
| Dense Embedding | `openai`、`azure`、`jina`、`ollama`、`gemini`、`voyage`、`dashscope`、`minimax`、`cohere`、`litellm`、`local` |
| VLM 與 Query Planner | `openai`、`azure`、`kimi`、`glm`、`litellm`、`openai-codex` |
| Rerank | `cohere`、`openai`、`litellm`、`jev` |

此分支已移除原生 `volcengine` 和 `vikingdb` 模型實作，也未提供 Sparse 或 Hybrid Embedding 的工廠實作。請配置 `embedding.dense`；將 `storage.vectordb.sparse_weight` 設為非零不會提供稀疏向量模型。配置結構仍保留部分舊欄位，設定精靈也可能繼續列出上游選項。請選擇已支援的提供程式，並在啟動服務前執行 `openviking-server doctor`。

未配置 Embedding 模型時，預設使用本地 512 維的 `bge-small-zh-v1.5-f16`。明確配置 Dense 模型時，提供程式預設為 `openai`。本地模型需要 `local-embed` 額外依賴；詳見[模型配置](../guides/01-configuration.md#本地-provider-local)。

已移除的 Ark VLM 後端原本提供音訊與影片理解；目前其餘後端未實作此能力，設定 `vlm.media.enabled` 也不會新增這項能力。圖片輸入仍取決於提供程式與模型。VikingBot 有獨立的提供程式登錄表，其獨立代理憑據與服務端 `vlm` 設定是不同的配置契約。

支援的示例請參閱[服務端配置](01-server.md)。變更既有工作區的 Embedding 提供程式、模型或維度時，可能需要重建索引。

## 加密

根金鑰提供程式為 `local` 和 `vault`，不支援 `volcengine_kms`。儲存格式保留 `0x03` 封裝標記以維持相容性，但這不代表恢復已移除的 KMS 提供程式。

請勿僅修改 provider 名稱來恢復加密資料。保留原始金鑰與備份，在仍能解密的部署中匯出既有 KMS 加密資料，再匯入使用受支援提供程式的新部署。詳見[加密指南](../guides/08-encryption.md)。

## VikingBot 外部工具

網頁搜尋與擷取預設透過 `tools.web.enabled` 停用，外部服務技能需明確啟用。需要時請自行配置；假設網頁工具預設啟用的上游示例需依此分支調整。

## 維護文件

共同描述的行為改變時，請同步更新英文與繁體中文頁面。核對示例時，應以服務端提供程式登錄表和配置工廠為準，而非僅依據設定精靈標籤或上游版本說明。提交前請執行 [CONTRIBUTING.md](https://github.com/yenchang265-afk/OpenViking/blob/main/CONTRIBUTING.md#documentation) 所列的文件檢查與建置步驟。
