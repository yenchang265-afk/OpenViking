---
description: 私有交付的配置生效、升級驗收、回滾準備和故障排查。
---

# 企業私有化部署：升級與排障

使用 ovadmin 和 Operator 維護[企業私有化部署](20-private-deployment.md)，包括配置更新、版本升級和故障排查。開源服務的容器更新見[服務端部署](03-deployment.md)。交付包版本和 runtime 版本分別核對。

## 配置修改如何生效

| 修改內容 | 修改位置 | 生效路徑 |
| --- | --- | --- |
| 模型地址、金鑰、Embedding 配置 | Secret Template / ConfigMap Template | 重新渲染並滾動 workspace |
| workspace 儲存與向量後端 | Workspace 宣告及交付配置 | 按 `workspace update` 流程；先確認資料遷移影響 |
| VikingDB 映象、排程、觀測配置 | `vdb.yaml` / 對應 values | dry-run 後執行 `setup apply --module vikingdb` |
| 客戶端入口 | 生成客戶端配置時選擇 endpoint | 重新生成並驗證呼叫方的連線 |

模板更新後，在實際 namespace 執行：

```bash
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" workspace restart "${WORKSPACE_NAME}" \
  --namespace vikingdb --yes --wait
```

該命令會滾動工作負載，需安排變更視窗。不要修改生成的最終 Secret、Pod 檔案或受 Operator 管理的 Deployment 來維持配置。替換 Embedding 模型或維度時，先確定索引重建方案。

## 升級檢查單

1. **記錄基線。** 儲存當前配置目錄、版本、CR 狀態、workspace 清單和 License 狀態。當前未 Ready 或授權異常時，先處理原因。
2. **確認恢復路徑。** 備份 workspace 資料、外部依賴資料、配置、金鑰和授權材料，並確認各自恢復步驟。配置副本不是資料備份；[OpenViking 快照](15-snapshot.md)也不能代替整套外部基礎設施的備份。
3. **核對版本組合。** 記錄 `ovadmin version --output json` 與 `version --cluster`。跨 `x.y` 升級按釋出說明確認；單獨替換某一產品映象後，原交付組合的相容結論不再自動成立。
4. **生成候選配置。** 在新目錄執行本輪 `ovadmin init config`，遷移已確認的 namespace、Registry、Secret 引用、StorageClass、排程和資源值。不要覆蓋當前配置目錄或照搬舊版預設映象。
5. **檢查與預覽。** 執行 `check`，分別對本次變更涉及的 VikingDB、OpenViking 執行 `setup apply --dry-run`；確認映象已同步、依賴可達、授權匹配。
6. **執行與驗收。** 按隨包升級順序變更，保留命令輸出與事件。重複 CR Ready、License Active（如啟用）、doctor 和各產品 P0 驗收，再驗證業務呼叫。

本輪預設 workspace requests / limits 均為 2 CPU / 4 GiB。升級候選配置要保留經過確認的資源規格，不能把預設值當成現有容量方案。

升級失敗時暫停後續變更，保留失敗狀態、dry-run 與事件。依據預先確認的回滾方案，使用舊配置、舊交付物和必要的資料恢復。**降級映象不保證恢復資料相容性。** 回滾後重復完整驗收，不直接編輯受管子資源繞開 Operator。

## 先收集狀態，再修復

下面是讀取狀態的入口；替換配置目錄、叢集名與 workspace 名稱：

```bash
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" version --cluster
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" check
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" cluster get vikingdb
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" workspace get "${WORKSPACE_NAME}"
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" doctor
kubectl -n vikingdb get pods,pvc,jobs,svc -o wide
kubectl -n vikingdb get events --sort-by=.lastTimestamp
```

| 現象 | 優先檢查 | 下一步 |
| --- | --- | --- |
| ImagePullBackOff / 映象檢查失敗 | 完整字首、交付 tag、倉庫是否已同步、各 namespace 的拉取 Secret | 修正源配置或補齊映象，再預覽 |
| Pod Pending | 節點標籤、汙點、資源 requests、PVC 與節點親和性 | 用 Pod / PVC 事件區分排程和儲存問題 |
| PVC Pending / 無可用 StorageClass | 實際 StorageClass、kubeconfig context、列舉儲存類的 RBAC | 顯式指定適用的儲存類；不直接刪除 PVC |
| License 非 Active | fingerprint、有效期、system namespace、CR 首次同步；線上授權還要查叢集到授權服務的網路和證書 | 按隨包授權流程處理，再查狀態；線上授權可用 `license renew <叢集名> --yes` 手動續期 |
| `license checksum mismatch` | `.vlic` 是否由本叢集 fingerprint 簽發、檔案是否被改動 | 不修改檔案內容；用本叢集 `fingerprint.json` 重新申請原始 `.vlic` |
| API Server 訪問失敗，但已提交資源 | 部署機到 API Server 的網路與 API 狀態 | 恢復後用 `cluster get` / `doctor` 查最終狀態，不立即重灌 |
| workspace Ready，但匯入或檢索失敗 | 模型鑑權、維度、API 路徑、限流、向量服務、使用者 Key | 執行 OpenViking P0 並讀取對應失敗階段 |
| Root Key 可管理但資料訪問失敗 | 是否把 Root Key 用於資料面 | 改用 User / Admin Key |
| 模型配置更新後未變化 | 修改的是否為源模板；是否重渲染 | 使用 `workspace restart`，重新驗證模型請求 |
| 叢集內可訪問，外部不可訪問 | 客戶端 endpoint 是否為 Service DNS、Ingress / LB / TLS | 配好外部入口，再生成對應客戶端配置 |
| VikingDB Ready，但索引一直 `INIT`；workspace 的 `VectorDBReady` 為 `False` | fermat 容器 `/var/log/tiger/hdfs_upload.log` 中的 `Permission denied: user=root` | 給 `root` 授予 HDFS 模型目錄寫許可權（見[部署文件](20-private-deployment.md#_2-生成並編輯配置)），fermat 會自動重試上傳。meta 日誌中同時出現的 `slot ... resource not enough` 不一定是原因 |
| 修改 Deployment 被拒絕：`direct update is rejected ... managed by VikingDbCluster` | 是否直接修改了受管工作負載 | 改 `vdb.yaml` 後執行 `setup apply --module vikingdb` |
| tbase-api / tbase-scan `Pending`，其他元件正常 | 節點汙點；本版不渲染 `spec.tbase` 的 `tolerations` | 用 `spec.tbase.nodeSelector` 排程到無汙點節點 |
| apply 報 `namespaces "viking-infra" not found` | `spec.observability.oneAgent.enabled` | 未部署配套觀測棧時設為 `false` |
| `open /tmp/openviking-operator-install.yaml: permission denied` | 部署機上其他使用者留下的同名檔案 | 以 `TMPDIR=<自有目錄>` 執行 `setup apply --module openviking` |

## 交付給支援人員的資訊

提供交付版本、發生時間、受影響操作、CR 條件、相關事件、doctor 與 P0 的失敗階段，以及脫敏後的配置差異。不要上傳 kubeconfig 憑據、模型金鑰、Root/User Key、授權檔案、完整 Secret 或帶簽名下載連結。

預設啟用採集元件不等於監控平臺已可用。本版隨包說明中，VictoriaMetrics / Grafana 由交付方案單獨準備。需確認指標接收、Dashboard 載入、告警接收與保留週期。離線授權環境還需按授權策略安排續期與遙測回傳。
