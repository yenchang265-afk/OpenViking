---
description: 自建部署前，準備工作負載、模型、儲存、網路與運維條件。
---

# 部署前檢查

用 Python、Docker 或 Helm chart 自行執行服務前，先核對以下清單。已有服務地址和 API Key 的使用者，從 [CLI 快速開始](../getting-started/02-quickstart.md)連線即可。

## 所有自建環境都要確認

| 專案 | 部署前應有的答案 | 參考 |
| --- | --- | --- |
| 工作負載 | 文件數量與大小、向量維度、併發請求、匯入頻率、保留週期 | [可觀測性](05-observability.md) |
| 模型服務 | provider、模型名、API Base、金鑰、輸出維度、限流與超時；從執行環境可訪問 | [配置指南](01-configuration.md) |
| 儲存 | workspace 的持久化位置、容量、許可權、備份位置和恢復方式 | [儲存架構](../concepts/05-storage.md)、[快照](15-snapshot.md) |
| 網路與身份 | 客戶端入口、TLS、DNS、反向代理、管理員與業務使用者金鑰 | [公網訪問](12-public-access.md)、[認證](04-authentication.md) |
| 運維責任 | 誰接收告警、執行升級、保管金鑰和恢復資料 | [可觀測性與排障](05-observability.md) |

資源配置需要用業務樣本驗證。容器啟動成功、單次健康檢查通過，都不足以證明容量滿足要求。

## 模型接入檢查

- Embedding 必須返回固定維度的 dense vector。核對模型實際輸出、`embedding.dense.dimension` 和向量庫維度一致。
- 確認 API Base 是否包含 `/v1` 或 `/api/v3`。文本與多模態 Embedding 的介面、請求體可能不同，不能僅憑“OpenAI 相容”判斷可用。
- VLM / LLM 用於理解、摘要和記憶抽取。圖片任務需驗證圖片輸入，啟用工具呼叫的 Agent 需驗證 tool calls。
- 從服務實際執行的位置（例如容器或 Pod 網路）測試鑑權、DNS、證書和超時；本機能訪問不代表服務能訪問。
- 已有資料更換 Embedding 模型時，即使維度相同，也要評估向量語義變化和重建索引方案。

準備完成後，繼續閱讀[服務端部署](03-deployment.md)。
