---
description: 使用 Viking 私有交付包，從配置預覽、VikingDB 部署到 OpenViking Workspace 與 P0 驗收。
---

# 企業私有化部署

<p><VPButton text="聯絡我們獲取部署物料" href="https://github.com/volcengine/OpenViking/blob/main/docs/repository/README_CN.md#%E5%95%86%E4%B8%9A%E7%89%88%E6%9C%AC" /></p>

通過部署物料，在自己的 Kubernetes 叢集中安裝 VikingDB 和 OpenViking。開始前，請先完成[部署前檢查](19-deployment-checklist.md)。Python、Docker 和開源 Helm 安裝見[服務端部署](03-deployment.md)。

## 1. 獲取物料並同步映象

部署物料需要先申請：在 [README 商業版本](https://github.com/volcengine/OpenViking/blob/main/docs/repository/README_CN.md#%E5%95%86%E4%B8%9A%E7%89%88%E6%9C%AC)登記郵箱，稽核通過後，安裝包下載連結和試用 License 會發到登記郵箱。

解壓後核對 `bin/ovadmin`、`viking-docs/` 與交付清單。安裝包只含 CLI 和文件，執行映象要按 `vikinglist` 另外下載，再匯入客戶 Registry。映象已同步到 Registry 時跳過本節。

以下命令在部署機執行。替換所有佔位值；`ovadmin` 負責部署，業務訪問用的是 `ov` CLI。

```bash
export VIKING_HOME=/opt/viking-deploy
export CONFIG_DIR=/opt/viking-deploy/conf
export MATERIAL_DIR=/opt/viking-deploy/materials
export IMAGE_REGISTRY='<registry.example.com/team/viking>'
export PATH="${VIKING_HOME}/bin:${PATH}"

ovadmin version --output json

# 下載映象離線包到 ${MATERIAL_DIR}/repo
ovadmin material download --listfile "${VIKING_HOME}/vikinglist" \
  --output-dir "${MATERIAL_DIR}"

# 先登入 Registry（docker login 或 skopeo login），再匯入並按清單檢查
ovadmin material import-registry --repo-dir "${MATERIAL_DIR}/repo" \
  --registry "${IMAGE_REGISTRY}"
ovadmin material check-registry --listfile "${VIKING_HOME}/vikinglist" \
  --image-registry "${IMAGE_REGISTRY}"
```

`vikinglist` 裡的下載地址帶簽名和有效期，返回 `HTTP 403` 時向交付方重新獲取。部署機無法訪問下載地址時，在聯網機器下載後，把 `repo` 目錄拷到部署機。部署機沒有 Docker daemon 時，`skopeo login` 後給 `import-registry` 加 `--skopeo-bin "$(command -v skopeo)"`。Registry 中已有的同名 tag 預設跳過，可以放心重跑。`check-registry` 不再報告缺失映象後繼續。

匯入時注意：

- Registry 不會自動建倉庫時（如 Amazon ECR），先用 `import-registry --dry-run` 列出目標映象，逐個建立倉庫。
- `--crane-bin` 會把 `.tar.gz` 直接交給 `crane push`，而 crane 只接受未壓縮的 tar，會報 `archive/tar: invalid tar header`。改用 `--skopeo-bin`，或先 `gunzip` 再用 `crane push <file>.tar <target>` 逐個推送。
- `import-registry` 遇到第一個失敗就停止整批匯入。修復原因後重跑即可，已匯入的 tag 會跳過。

**初始化映象不在 `vikinglist` 中。** 使用 Flyway 自動初始化基礎元件（隨包《基礎元件配置要求》方式二）時，初始化 Job 預設引用下面三個映象。它們是 Docker Hub 上的公開映象，需要自行同步到 Registry 的對應路徑：

| 用途 | 預設引用 | 公開來源 |
| --- | --- | --- |
| MySQL DDL | `${IMAGE_REGISTRY}/infra/apecloud/mysql:8.0.39` | `docker.io/apecloud/mysql:8.0.39` |
| Kafka Topic | `${IMAGE_REGISTRY}/infra/apecloud/kafka:3.8.1-debian-12-r2` | `docker.io/apecloud/kafka:3.8.1-debian-12-r2` |
| HBase 表、HDFS 目錄 | `${IMAGE_REGISTRY}/infra/apecloud/hbase-hmaster:v2.5.6-1.0.0` | `docker.io/apecloud/hbase-hmaster:v2.5.6-1.0.0` |

```bash
crane copy docker.io/apecloud/mysql:8.0.39 "${IMAGE_REGISTRY}/infra/apecloud/mysql:8.0.39"
crane copy docker.io/apecloud/kafka:3.8.1-debian-12-r2 "${IMAGE_REGISTRY}/infra/apecloud/kafka:3.8.1-debian-12-r2"
crane copy docker.io/apecloud/hbase-hmaster:v2.5.6-1.0.0 "${IMAGE_REGISTRY}/infra/apecloud/hbase-hmaster:v2.5.6-1.0.0"
```

使用自備的客戶端映象時，在 `vdb.yaml` 的 `spec.global.flywayInitImages` 中配置 repository 和 tag。MySQL DDL 內建在 ovadmin 中，由 Flyway Job 執行，交付包裡沒有單獨的 SQL 檔案。

`setup apply --dry-run` 會逐個檢查 Registry 中的映象，業務映象和初始化映象都同步完成後才能預覽完整計劃。

隔離環境還要準備基礎元件、模型服務，以及 License 續期和遙測回傳方案；映象到位不代表系統可以完全離線執行。

## 2. 生成並編輯配置

```bash
ovadmin init config \
  --dir "${CONFIG_DIR}" \
  --profile cluster \
  --image-registry "${IMAGE_REGISTRY}" \
  --image-pull-secret viking-registry-secret \
  --openviking-storage-class '<storage-class-name>'
```

生成後，先編輯配置再部署：

| 檔案或物件 | 管理內容 |
| --- | --- |
| `ovadmin.conf` | 叢集訪問、配置目錄、OpenViking 映象、workspace 資源與儲存 |
| `vdb.yaml` | VikingDB 元件映象、依賴引用、排程、儲存與觀測配置 |
| ConfigMap Template | OpenViking 基礎執行配置 |
| Secret Template | 模型金鑰及其他敏感配置，使用 `ov.conf.secret` |
| `OpenVikingWorkspace` | workspace 的宣告，包括儲存和向量庫覆蓋值 |
| 生成的 `*.ovcli.conf` | 客戶端 endpoint 與 API Key，按憑據保管 |

完整映象字首必須含倉庫路徑。Operator 映象名以交付清單為準，本版為 `vikingdb_operator` 和 `openviking_operator`，不要改成帶連字元的名稱。映象 tag 使用交付組合，不從示例中抄舊值。

給節點打排程標籤：`cluster` 至少 2 個 online 節點和 1 個 offline 節點；`standalone` 把元件排程到 online 節點。

```bash
kubectl label node '<node-name>' nodeLevel=online --overwrite
kubectl label node '<offline-node-name>' nodeLevel=offline --overwrite
kubectl get nodes -L nodeLevel
```

生成的 `vdb.yaml` 還要按實際環境補充或修改下面幾項：

| 專案 | 原因 | 做法 |
| --- | --- | --- |
| `spec.middleware.hdfs.configMapName` | `init config` 不生成此欄位；缺少時 dry-run 也不會校驗 HDFS ConfigMap | 手工加上 `hdfs: {configMapName: hadoop-config}`，名稱與實際 ConfigMap 一致 |
| `spec.observability.oneAgent.enabled` | `cluster` profile 預設為 `true`，one-agent 的下游寫入 `viking-infra` namespace；沒有配套觀測棧時 apply 報 `namespaces "viking-infra" not found` | 未部署配套觀測棧時設為 `false` |
| 各元件 `replicas` 與 `resources` | 預設值按大規格節點估算，可能超出節點池容量 | 按節點池可分配容量調整，見[部署前檢查](19-deployment-checklist.md) |
| `spec.tbase` 排程 | 本版 Operator 不把 `spec.tbase` 下的 `tolerations` 渲染到 tbase-api / tbase-scan；直接修改 Deployment 會被授權 webhook 拒絕 | 專用節點帶汙點時，用 `spec.tbase.nodeSelector` 把 tbase 排程到無汙點、容量足夠的節點 |

專用節點帶汙點時，其他元件在 `vdb.yaml` 中逐一配置 `tolerations` 即可生效。

HDFS 模型目錄要讓 `root` 可寫（原因見[部署前檢查](19-deployment-checklist.md)）。Flyway 預設以 `hadoop` 使用者建立目錄並設為 `755`，執行時 fermat 以 `root` 寫入。目錄建立後，用 HDFS 管理員身份新增 ACL：

```bash
hdfs dfs -setfacl -R -m user:root:rwx,default:user:root:rwx,default:user:hadoop:rwx /home/vikingdb_data
hdfs dfs -getfacl /home/vikingdb_data
```

HDFS 未開啟 ACL 時，改用 `hdfs dfs -chown -R root /home/vikingdb_data` 或其他符合客戶規範的授權方式。缺少寫許可權時，VikingDB 仍會 Ready，但索引一直停在 `INIT`。

然後核對業務與 Operator namespace、外部依賴 Secret / ConfigMap 和 StorageClass。按隨包《基礎元件配置要求》完成依賴初始化。執行配置預檢，並在配置所指定的 namespace 初始化拉映象 Secret：

```bash
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" check
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" init secret --all-namespaces
```

## 3. 部署 VikingDB

```bash
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" setup apply \
  --module vikingdb --dir "${CONFIG_DIR}" --dry-run
```

核對預覽中的 namespace、映象、拉取 Secret、外部依賴、資源和排程。修正不一致項後再執行：

```bash
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" setup apply \
  --module vikingdb --dir "${CONFIG_DIR}" --yes
```

如啟用 License，首次 apply 可能因等待授權 Active 而退出。此時 `VikingDbCluster` CR 已建立，Operator 完成首次狀態同步後，用當前叢集生成指紋，交給授權簽發方換取 `.vlic`，匯入後用同一配置重跑 apply：

```bash
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" license fingerprint \
  --system-namespace viking-system --out fingerprint.json

# 取得與本叢集 fingerprint 匹配的 .vlic 後
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" license import \
  --system-namespace viking-system --file '<license.vlic>'
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" license status
```

`.vlic` 必須由本叢集的 `fingerprint.json` 簽發，其他叢集的指紋或改過的檔案都會校驗失敗。

使用線上授權時，不需要 fingerprint 和 `.vlic`。同樣等 CR 完成首次狀態同步後，用一次性 activation code 啟用，再用同一配置重跑 apply：

```bash
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" license activate \
  --system-namespace viking-system \
  --code '<activation-code>' \
  --endpoint 'https://<license-endpoint>' \
  --yes
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" license status vikingdb
```

activation code 只能成功使用一次，不要寫入配置檔案、指令碼或日誌。啟用後 `license status` 的 Mode 為 `online`，續期和遙測由 Operator 自動完成，續期憑據儲存在 `viking-system/viking-license-renewal`。離線和線上兩種方式不能混用。等待授權時，CR 的原因文案固定為 `provide offline .vlic via import secret`，線上授權環境按本段啟用即可。

未啟用授權時跳過授權步驟。確認 VikingDB Ready 後再繼續：

```bash
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" cluster get vikingdb
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" doctor
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" check smoketest --target vdb --p0
```

如果叢集名不是 `vikingdb`，替換為實際名稱。Smoke 會建立測試物件並執行寫入，應在約定的驗收環境執行。

## 4. 部署 OpenViking 與 Workspace

如果只交付 VikingDB，跳過本節。

先把模型配置寫入 Secret Template，內容結構與 `ov.conf` 一致。下面是火山方舟的預設模型，Embedding 輸出維度為 `1024`；換其他模型服務時，同時核對介面協議和維度，見[部署前檢查](19-deployment-checklist.md#模型接入檢查)。

```json
{
  "embedding": {
    "dense": {
      "provider": "volcengine",
      "model": "doubao-embedding-vision-251215",
      "api_base": "https://ark.cn-beijing.volces.com/api/v3",
      "api_key": "<embedding-api-key>",
      "dimension": 1024,
      "input": "multimodal"
    }
  },
  "vlm": {
    "provider": "volcengine",
    "model": "doubao-seed-2-0-lite-260428",
    "api_base": "https://ark.cn-beijing.volces.com/api/v3",
    "api_key": "<vlm-api-key>"
  }
}
```

儲存為 `ov.conf.secret` 後寫入 Secret，然後刪除本地明文檔案：

```bash
kubectl -n vikingdb create secret generic openviking-secrets \
  --from-file=ov.conf.secret=ov.conf.secret \
  --dry-run=client -o yaml | kubectl apply -f -
```

再預覽並安裝 OpenViking Operator，建立 workspace：

```bash
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" setup apply \
  --module openviking --dir "${CONFIG_DIR}" --dry-run

# 核對預覽後執行
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" setup apply \
  --module openviking --dir "${CONFIG_DIR}" --yes

export WORKSPACE_NAME='<workspace-name>'
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" workspace create "${WORKSPACE_NAME}" \
  --namespace vikingdb \
  --image '<runtime-image-from-delivery-manifest>' \
  --conf-template '<configmap-template-name>' \
  --conf-secret openviking-secrets \
  --wait

ovadmin -c "${CONFIG_DIR}/ovadmin.conf" workspace get "${WORKSPACE_NAME}"
```

Operator 安裝成功不會自動完成 workspace 建立。同名 workspace 已存在時，按隨包手冊使用 `workspace update`。

配置合併順序為：ConfigMap Template → Secret Template → Workspace CR 的 `spec.vectordb` / `spec.storage` 覆蓋。最終配置寫入 `<workspace-name>-ov-conf` Secret 並掛載到 `/app/ov.conf`。修改源模板或 CR，不要直接編輯生成的 Secret 或 Pod 內檔案。模板變更後的生效方式見[升級與排障](21-private-operations.md)。

## 5. 連線並驗收

```bash
export OV_CLIENT_CONF="${CONFIG_DIR}/${WORKSPACE_NAME}.ovcli.conf"
ovadmin -c "${CONFIG_DIR}/ovadmin.conf" workspace gen-conf "${WORKSPACE_NAME}" \
  --output "${OV_CLIENT_CONF}"
chmod 600 "${OV_CLIENT_CONF}"

ovadmin -c "${CONFIG_DIR}/ovadmin.conf" check smoketest \
  --target openviking --p0 --openviking-conf "${OV_CLIENT_CONF}"
```

生成配置內含 Root API Key，僅用於初始化與管理。業務資料訪問需 User / Admin Key；P0 冒煙會 provision 測試 User Key。不要將客戶端配置提交到程式碼庫或貼入日誌。

生成配置把 Root API Key 寫在 `api_key` 欄位。較新的 `ov` CLI 執行 `--sudo` 管理命令時讀取 `root_api_key` 欄位，因此先在客戶端配置中加一個值相同的 `root_api_key`，再註冊業務使用者，並把返回的 User Key 寫回 `api_key`：

```bash
ov admin register-user default '<user-id>' --sudo
```

之後日常的 `ov` 命令使用 User Key，`root_api_key` 只留給管理命令。

客戶端在叢集內可用 `gen-conf --endpoint-type service`。叢集外需可訪問的入口，可用 `--endpoint '<openviking-endpoint>'` 指定；生成配置不會替你建立 Ingress、TLS 或負載均衡。已存在的輸出檔案需確認後才加 `--force` 覆蓋。

以下條件全部滿足即完成部署：

- 所有節點 `Ready`，業務 Pod 沒有 `Pending`、`ImagePullBackOff` 或持續重啟。
- `check-registry` 沒有報告缺失映象；物料版本與執行版本一致。
- `VikingDbCluster` 當前 generation 為 Ready；部署 OpenViking 時 `OpenVikingWorkspace` 為 Ready。
- 啟用 License 時，`license status vikingdb` 的 State 為 `Active`，業務 namespace 中存在 `viking-license-verdict` Secret。
- `doctor` 通過，VikingDB P0 與 OpenViking P0 分別通過。
- 從業務客戶端驗證入口、鑑權、匯入、讀取和檢索。

Pod Running 不能替代上述驗收，上述檢查也不替代容量、恢復或高可用驗證。部署完成後，用生成的客戶端配置按 [CLI 快速開始](../getting-started/02-quickstart.md)連線服務。

## 隨包文件索引

在解壓後的 `viking-docs/` 中檢視：`install.md`（入口）、`Viking部署手冊.md`（完整流程）、`ovadmin使用手冊.md`（引數）、`Viking模型要求.md`（模型模板）、`基礎元件配置要求.md`（初始化）、`版本相容性說明.md`（兼容範圍）、`Viking升級說明.md`（升級）。後續維護見[升級與排障](21-private-operations.md)。
