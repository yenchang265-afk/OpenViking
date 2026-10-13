---
description: 區分託管、自建和私有交付，準備叢集、映象、儲存、模型與驗收條件。
---

# 部署前檢查

先確定服務方式，再準備環境。已有服務地址和 API Key 的使用者，從 [CLI 快速開始](../getting-started/02-quickstart.md)連線即可。

| 你的目標 | 選擇 | 下一步 |
| --- | --- | --- |
| 使用服務，由平臺管理基礎設施 | 火山引擎託管 OpenViking | [服務端部署中的託管入口](03-deployment.md) |
| 自己執行開源服務 | Python / Docker / 開源 Helm chart | [服務端部署](03-deployment.md) |
| 已取得 VikingDB / OpenViking 私有交付包 | Kubernetes、Operator 與 ovadmin | [企業私有化部署](20-private-deployment.md) |

私有交付的元件、授權和配置機制與開源服務不同。下文中標註“私有交付”的要求不適用於所有 OpenViking 安裝。

## 所有自建環境都要確認

| 專案 | 部署前應有的答案 | 參考 |
| --- | --- | --- |
| 工作負載 | 文件數量與大小、向量維度、併發請求、匯入頻率、保留週期 | [可觀測性](05-observability.md) |
| 模型服務 | provider、模型名、API Base、金鑰、輸出維度、限流與超時；從執行環境可訪問 | [配置指南](01-configuration.md) |
| 儲存 | workspace 的持久化位置、容量、許可權、備份位置和恢復方式 | [儲存架構](../concepts/05-storage.md)、[快照](15-snapshot.md) |
| 網路與身份 | 客戶端入口、TLS、DNS、反向代理、管理員與業務使用者金鑰 | [公網訪問](12-public-access.md)、[認證](04-authentication.md) |
| 運維責任 | 誰接收告警、執行升級、保管金鑰和恢復資料 | [可觀測性與排障](05-observability.md) |

資源配置需要用業務樣本驗證。容器啟動成功、單次健康檢查通過，都不足以證明容量滿足要求。

## 私有交付：版本與環境

部署前核對下面的環境與版本要求，並以所用部署包的相容矩陣確認元件組合。

| 專案 | 部署要求 | 需要核對 |
| --- | --- | --- |
| OS / CPU | Linux，預設 x86_64 | arm64 需有對應映象和二進位制 |
| Kubernetes | 相容矩陣宣告 1.24+ | 實際版本、CRD、CNI、CSI 與 RBAC；未宣告最大相容版本 |
| Helm / kubectl | Helm 3.x，不支援 Helm 4；kubectl 與叢集差異不超過一個 minor | 在部署機核對工具版本 |
| profile | `standalone` 用於演示和復現；`cluster` 用於叢集驗證 | 按環境選擇 profile，並驗證副本、排程與故障恢復 |
| 版本組合 | ovadmin、VikingDB、OpenViking runtime、Operator 屬於同一交付組合 | 記錄 `ovadmin version --output json`；不能用包名推斷 runtime 版本 |

隨包文件給出的叢集規劃參考為至少 3 臺機器，每臺 32 核、256 GiB 記憶體、2 TiB 本地盤。**這不是開源 OpenViking 的最低配置，也不是已驗證的容量承諾。** 是否適合你的環境取決於索引規模、向量維度、QPS、構建併發、副本和基礎元件部署位置。將基礎元件與業務混布的三節點形態，僅作為研發、演示或 POC 的起點。

## 私有交付：基礎設施清單

| 範圍 | 確認內容 |
| --- | --- |
| 許可權 | 部署 kubeconfig；建立 CRD 和 RBAC 的許可權；Operator 管理目標 namespace 的許可權；按隨包許可權表申請 |
| 叢集獨佔 | 一個 Kubernetes 叢集只裝一套私有交付，見下文說明 |
| Namespace | 業務與 Operator 的 namespace，預設示例分別為 `vikingdb`、`viking-system`；Secret 的作用域 |
| 排程 | `cluster` 預設使用 `nodeLevel=online` / `nodeLevel=offline`；實際節點標籤、汙點和資源能滿足排程 |
| Registry | 完整倉庫字首、交付映象 tag、拉取憑據；部署機登入與叢集拉取分別驗證；Registry 不會自動建倉庫時（如 Amazon ECR）先建好倉庫 |
| 儲存 | 可用 StorageClass；分別配置 VikingDB 資料盤、OpenViking workspace PVC 與外部基礎元件儲存 |
| 網路 | Pod / Service DNS、API Server、中介軟體與模型訪問；叢集 DNS 字尾；入口域名和 TLS |
| 授權 | 離線授權：準備當前叢集 fingerprint 對應的授權檔案。線上授權：準備一次性 activation code 和授權服務 HTTPS 地址，部署機和叢集都要能訪問該地址。確認有效期、續期與遙測安排 |

不要直接沿用生成配置中的 `local-path`、磁碟容量或節點標籤。OpenViking workspace 預設 requests / limits 均為 2 CPU / 4 GiB，這是配置預設值，需按負載核對。

`cluster` profile 生成的 VikingDB 預設資源按上文三臺大規格機器估算，例如 `viking` 預設 2 副本，每副本 16 CPU / 128 GiB。部署前把 `vdb.yaml` 裡所有元件的 `replicas × requests` 加總，與目標節點池的可分配容量對比；`setup apply --dry-run` 不做容量校驗，超出時只會在部署後表現為大量 Pod `Pending`。

**叢集獨佔。** VikingDB / OpenViking 的 CRD 是叢集級資源，VikingDB Operator 監聽所有 namespace，授權 webhook `vikingdb-license-guard.openviking.ai` 名稱固定，Operator 讀取授權的 system namespace 固定為 `viking-system`。同一叢集裝第二套，即使業務 namespace 不同，也會覆蓋 CRD、出現兩個 Operator 同時處理同一資源，並爭用 webhook 和授權 Secret。需要多套環境時使用不同的叢集。

**共享叢集的影響。** 授權 webhook 中的 `managed-workload.openviking.ai` 不限 namespace，校驗叢集內所有帶 `app.kubernetes.io/managed-by=Helm` 標籤的 Deployment、StatefulSet、Job 的更新和刪除，失敗策略為 `Fail`。VikingDB Operator 不可用時，集群裡其他 Helm 應用的升級和刪除也會被拒絕。與其他業務共用叢集前，要評估這一影響，並把 Operator 的可用性納入運維範圍。

`cluster` 交付依賴客戶提供或按交付方案准備的基礎元件：

| 元件 | 隨包推薦版本 | 隨包宣告的最低版本 / 條件 |
| --- | --- | --- |
| MySQL | 8.0 | 5.7+ |
| Redis | 6.2.x | 未宣告最低版本 |
| Kafka | 3.x | 3.0+ |
| ZooKeeper | 3.7.2 | 未宣告最低版本 |
| HDFS | 3.3.x | 高可用形態 |
| HBase | 2.5.x | 依賴 HDFS 和 ZooKeeper |

這張表記錄本次交付口徑，不代表持續更新的相容認證。連線可達後，還要按隨包《基礎元件配置要求》核對資料庫、Topic、名稱空間、目錄、許可權和初始化結果。外部依賴升級後需重新驗收。

HDFS 模型目錄（預設 `/home/vikingdb_data`）要讓 VikingDB 的執行身份可寫。fermat 等元件在容器內以 `root` 執行，且不設定 `HADOOP_USER_NAME`，在 simple 認證下訪問 HDFS 的使用者就是 `root`。HDFS 開啟許可權檢查且 `root` 不是超級使用者時（如 Amazon EMR 預設配置），需給 `root` 授予該目錄的寫許可權，做法見[企業私有化部署](20-private-deployment.md#_2-生成並編輯配置)。

## 模型接入檢查

- Embedding 必須返回固定維度的 dense vector。核對模型實際輸出、`embedding.dense.dimension` 和向量庫維度一致。
- 確認 API Base 是否包含 `/v1` 或 `/api/v3`。文本與多模態 Embedding 的介面、請求體可能不同，不能僅憑“OpenAI 相容”判斷可用。
- VLM / LLM 用於理解、摘要和記憶抽取。圖片任務需驗證圖片輸入，啟用工具呼叫的 Agent 需驗證 tool calls。
- 從實際 Pod 網路測試鑑權、DNS、證書和超時；本機能訪問不代表 Pod 能訪問。
- 已有資料更換 Embedding 模型時，即使維度相同，也要評估向量語義變化和重建索引方案。

私有交付中，`OpenVikingWorkspace.spec.vectordb.dimension` 會覆蓋模板中的儲存維度，但不會同步修改 `embedding.dense.dimension`。兩處必須分別核對。

準備完成後進入[企業私有化部署](20-private-deployment.md)。日常維護見[升級與排障](21-private-operations.md)。
