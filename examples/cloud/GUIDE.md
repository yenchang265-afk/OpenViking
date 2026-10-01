# OpenViking 雲上部署指南（火山引擎）

本文件介紹如何將 OpenViking 部署到火山引擎雲上，使用 TOS（物件儲存）+ VikingDB（向量資料庫）+ 方舟大模型作為後端。

## 概覽

雲上部署架構：

```
使用者請求 → OpenViking Server (1933)
                ├── AGFS → TOS (S3 相容協議，儲存檔案資料)
                ├── VectorDB → VikingDB (向量檢索)
                ├── Embedding → 方舟 API (doubao-embedding-vision)
                └── VLM → 方舟 API (doubao-seed)
```

> **地域說明**：TOS 和 VikingDB 均需要選擇地域（region），不同地域對應不同的服務域名。所有云服務應部署在同一地域以降低網路延遲。目前支援的地域包括 `cn-beijing`、`cn-shanghai`、`cn-guangzhou` 等，本文以 `cn-beijing` 為例。

## 前置條件

- 火山引擎帳號（[註冊地址](https://console.volcengine.com/)）
- 已安裝 OpenViking（`pip install openviking --upgrade --force-reinstall` 或從原始碼安裝）
- Python 3.11+

---

## 1. 開通雲服務

### 1.1 開通 TOS（物件儲存）

TOS 用於持久化儲存 OpenViking 的檔案資料（AGFS 後端）。

1. 登入 [火山引擎控制台](https://console.volcengine.com/)
2. 進入 **物件儲存 TOS** → 開通服務
3. 建立儲存桶：
   - 桶名稱：如 `openvikingdata`
   - 地域：如 `cn-beijing`（需與 VikingDB 等其他服務保持一致）
   - 儲存型別：標準儲存
   - 訪問許可權：私有
4. 記錄桶名稱、地域和 S3 相容 endpoint，填入配置檔案的 `storage.agfs.s3` 部分

> **注意**：AGFS 使用 S3 相容協議訪問 TOS，endpoint 需要使用 S3 相容域名（帶 `tos-s3-` 字首），而非 TOS 控制台顯示的標準域名。不同地域的 endpoint 不同，請查閱 [TOS 地域和訪問域名文件](https://www.volcengine.com/docs/6349/107356) 獲取你所在地域的 S3 相容 endpoint。例如：
>
> | 地域 | S3 兼容 endpoint |
> |------|-----------------|
> | cn-beijing | `https://tos-s3-cn-beijing.volces.com` |
> | cn-shanghai | `https://tos-s3-cn-shanghai.volces.com` |
> | cn-guangzhou | `https://tos-s3-cn-guangzhou.volces.com` |

### 1.2 開通 VikingDB（向量資料庫）

VikingDB 用於儲存和檢索向量嵌入。

1. 登陸 [火山引擎控制台](https://console.volcengine.com/) →  [進入 VikingDB 下單開通介面](https://console.volcengine.com/vikingdb/region:vikingdb+cn-beijing/home) -> 選擇對應的地域並開通向量資料庫
2. 開通服務（按量付費即可），選擇與 TOS 相同的地域
3. 無需手動建立 Collection，OpenViking 啟動後會自動建立
4. 在配置檔案中填寫 `storage.vectordb.volcengine.region`，OpenViking 會自動路由到對應地域的 VikingDB 服務

### 1.3 申請 AK/SK（IAM 訪問金鑰）

AK/SK 同時用於 TOS 和 VikingDB 的鑑權。

1. 進入 [火山引擎控制台](https://console.volcengine.com/) → **訪問控制 IAM**
2. 建立子使用者（建議不使用主帳號 AK/SK）
3. 為子使用者授權以下策略：
   - `TOSFullAccess`（或精確到桶級別的自定義策略）
   - `VikingDBFullAccess`
4. 為子使用者建立 **AccessKey**，記錄：
   - `Access Key ID`（即 AK）
   - `Secret Access Key`（即 SK）
5. 將 AK/SK 填入配置檔案中的以下位置：
   - `storage.vectordb.volcengine.ak` / `sk`
   - `storage.agfs.s3.access_key` / `secret_key`

### 1.4 申請方舟 API Key

方舟平臺提供 Embedding 和 VLM 模型的推理服務。

1. 進入 [火山方舟控制台](https://console.volcengine.com/ark)
2. 左側選單 → **API Key 管理** → 建立 API Key
3. 記錄生成的 API Key
4. 確認以下模型已開通（在 **模型廣場** 中申請）：
   - `doubao-embedding-vision-251215`（多模態 Embedding）
   - `doubao-seed-2-0-lite-260428`（VLM 推理）
5. 將 API Key 填入配置檔案的 `embedding.dense.api_key` 和 `vlm.api_key`

---

## 2. 準備配置檔案

### 2.1 複製示例配置

```bash
cp examples/cloud/ov.conf.example examples/cloud/ov.conf
```

### 2.2 編輯配置

開啟 `examples/cloud/ov.conf`，將佔位符替換為真實值。需要替換的欄位如下：

| 佔位符 | 替換為 | 說明 |
|--------|--------|------|
| `<your-root-api-key>` | 自定義強密碼 | 管理員金鑰，用於多租戶管理 |
| `<your-volcengine-ak>` | IAM Access Key ID | 火山引擎 AK，用於 TOS / VikingDB |
| `<your-volcengine-sk>` | IAM Secret Access Key | 火山引擎 SK |
| `<your-tos-bucket>` | TOS 桶名稱 | 如 `openvikingdata` |
| `<your-ark-api-key>` | 方舟 API Key | 用於 Embedding 和 VLM |

此外，還需根據實際地域修改以下欄位（示例中預設為 `cn-beijing`）：

| 欄位 | 說明 |
|------|------|
| `storage.vectordb.volcengine.region` | VikingDB 地域，如 `cn-beijing`、`cn-shanghai`、`cn-guangzhou` |
| `storage.agfs.s3.region` | TOS 地域，需與桶所在地域一致 |
| `storage.agfs.s3.endpoint` | TOS 的 S3 相容 endpoint，需與地域匹配（參考第 1.1 節） |

替換後的配置示例（脫敏）：

```json
{
  "server": {
    "root_api_key": "my-strong-secret-key-2024"
  },
  "storage": {
    "vectordb": {
      "volcengine": {
        "region": "cn-beijing",
        "ak": "AKLTxxxxxxxxxxxx",
        "sk": "T1dYxxxxxxxxxxxx"
      }
    },
    "agfs": {
      "s3": {
        "bucket": "openvikingdata",
        "region": "cn-beijing",
        "access_key": "AKLTxxxxxxxxxxxx",
        "secret_key": "T1dYxxxxxxxxxxxx",
        "endpoint": "https://tos-s3-cn-beijing.volces.com"
      }
    }
  },
  "embedding": {
    "dense": {
      "api_key": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
    }
  },
  "vlm": {
    "api_key": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  }
}
```

> **注意**：`ov.conf` 已被 `.gitignore` 排除，不會被提交到版本庫。請妥善保管你的憑據。

---

## 3. 啟動服務

| 方式 | 需要容器執行時 | 適合節點數 | 環境隔離 | 彈性伸縮 | 典型場景 |
|------|:---:|:---:|:---:|:---:|------|
| **Docker（推薦）** | 是 | 單機 | 容器隔離 | 不支援 | 開發、測試、單機生產，最省事 |
| systemd | 否 | 單機 | 無 | 不支援 | VM 上不想裝 Docker |
| Kubernetes + Helm | 是 | 暫不支援多節點 | 容器 + 編排 | 支援 | 已有 K8s 叢集的團隊 |

> **開發除錯**：如果只是本地快速驗證，可以直接執行：
> ```bash
> pip install openviking --upgrade --force-reinstall
>
> # 方式 A：放到預設路徑
> mkdir -p ~/.openviking && cp examples/cloud/ov.conf ~/.openviking/ov.conf
> openviking-server
>
> # 方式 B：通過環境變數指定
> OPENVIKING_CONFIG_FILE=examples/cloud/ov.conf openviking-server
> ```

### 方式一：systemd

適合在 VM 上以系統服務方式長期執行。

1. 安裝 OpenViking：

```bash
pip install openviking --upgrade --force-reinstall
```

2. 將配置檔案放到固定路徑：

```bash
sudo mkdir -p /etc/openviking
sudo cp ~/.openviking/ov.conf /etc/openviking/ov.conf
sudo chmod 600 /etc/openviking/ov.conf
```

3. 建立 systemd service 檔案：

```bash
sudo tee /etc/systemd/system/openviking.service > /dev/null << 'EOF'
[Unit]
Description=OpenViking Server
After=network.target

[Service]
Type=simple
Environment=OPENVIKING_CONFIG_FILE=/etc/openviking/ov.conf
ExecStart=/usr/local/bin/openviking-server  # 替換為 which openviking-server 的實際輸出
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
```

4. 啟動服務：

```bash
sudo systemctl daemon-reload
sudo systemctl start openviking
sudo systemctl status openviking
```

5. 確認服務正常後，設定開機自啟（可選）：

```bash
sudo systemctl enable openviking
```

常用管理命令：

```bash
sudo systemctl stop openviking       # 停止服務
sudo systemctl restart openviking    # 重啟服務
journalctl -u openviking -f          # 檢視即時日誌
```

### 方式二：Docker

單容器場景用 `docker run` 或 `docker compose` 均可，效果相同。

**docker run：**

```bash
# 假設你的配置檔案在 ~/.openviking/ov.conf
#
# -p  埠對映，宿主機埠:容器埠，啟動後通過 localhost:1933 訪問
# -v  掛載宿主機檔案到容器內，格式為 宿主機路徑:容器內路徑
#     ov.conf 掛載是必填的，data 目錄用於持久化資料（容器刪除後不丟失）
# --restart  程序崩潰或機器重啟後自動拉起
# 映象推薦優先使用 ghcr.io；如果訪問有問題，可改用 openviking-cn-beijing.cr.volces.com/volcengine/openviking:latest

docker run -d \
  --name openviking \
  -p 1933:1933 \
  -v ~/.openviking/ov.conf:/app/ov.conf \
  -v /var/lib/openviking/data:/app/data \
  --restart unless-stopped \
  ghcr.io/volcengine/openviking:latest
```

> 將 `~/.openviking/ov.conf` 替換為你實際的配置檔案路徑。

常用管理命令：

```bash
docker logs openviking        # 檢視日誌
docker logs -f openviking     # 即時跟蹤日誌
docker stop openviking        # 停止服務
docker restart openviking     # 重啟服務
docker rm -f openviking       # 刪除容器（重新 docker run 前需要先刪除）
```

**docker compose：**

專案根目錄的 `docker-compose.yml` 預設從 `/var/lib/openviking/ov.conf` 讀取配置：

```bash
# 把你的配置檔案複製到 docker-compose.yml 期望的路徑
sudo mkdir -p /var/lib/openviking
sudo cp ~/.openviking/ov.conf /var/lib/openviking/ov.conf

# 在專案根目錄下啟動（-d 表示後臺執行）
docker compose up -d
```

> 如果配置檔案不在 `/var/lib/openviking/ov.conf`，需要修改 `docker-compose.yml` 中 `volumes` 的掛載路徑。

常用管理命令：

```bash
docker compose stop        # 停止服務
docker compose restart     # 重啟服務
docker compose logs -f     # 檢視即時日誌
```

> 如需自行構建映象：`docker build -t openviking:latest .`

### 方式三：Kubernetes + Helm

Helm chart 預設的 `values.yaml` 只包含 embedding 和 vlm 配置。雲上部署需要補充 storage、server 等欄位。

推薦建立自定義 values 檔案 `my-values.yaml`：

```yaml
openviking:
  config:
    server:
      root_api_key: "my-strong-secret-key-2024"
    storage:
      workspace: /app/data
      vectordb:
        name: context
        backend: volcengine
        project: default
        volcengine:
          region: cn-beijing
          ak: "AKLTxxxxxxxxxxxx"
          sk: "T1dYxxxxxxxxxxxx"
      agfs:
        backend: s3
        timeout: 10
        s3:
          bucket: "openvikingdata"
          region: cn-beijing
          access_key: "AKLTxxxxxxxxxxxx"
          secret_key: "T1dYxxxxxxxxxxxx"
          endpoint: "https://tos-s3-cn-beijing.volces.com"
          prefix: openviking
          use_ssl: true
          use_path_style: false
    embedding:
      dense:
        model: "doubao-embedding-vision-251215"
        api_key: "your-ark-api-key"
        api_base: "https://ark.cn-beijing.volces.com/api/v3"
        dimension: 1024
        provider: volcengine
        input: multimodal
    vlm:
      model: "doubao-seed-2-0-lite-260428"
      api_key: "your-ark-api-key"
      api_base: "https://ark.cn-beijing.volces.com/api/v3"
      temperature: 0.0
      max_retries: 3
      provider: volcengine
      thinking: false
    auto_generate_l0: true
    auto_generate_l1: true
    default_search_mode: thinking
    default_search_limit: 3
    enable_memory_decay: true
    memory_decay_check_interval: 3600
```

然後安裝：

```bash
helm install openviking ./examples/k8s-helm -f my-values.yaml
```

或者通過 `--set` 逐個傳參（適合 CI/CD）：

```bash
helm install openviking ./examples/k8s-helm \
  --set openviking.config.server.root_api_key="my-strong-secret-key-2024" \
  --set openviking.config.embedding.dense.api_key="YOUR_ARK_API_KEY" \
  --set openviking.config.vlm.api_key="YOUR_ARK_API_KEY" \
  --set openviking.config.storage.vectordb.backend="volcengine" \
  --set openviking.config.storage.vectordb.volcengine.ak="YOUR_AK" \
  --set openviking.config.storage.vectordb.volcengine.sk="YOUR_SK" \
  --set openviking.config.storage.agfs.backend="s3" \
  --set openviking.config.storage.agfs.s3.bucket="openvikingdata" \
  --set openviking.config.storage.agfs.s3.access_key="YOUR_AK" \
  --set openviking.config.storage.agfs.s3.secret_key="YOUR_SK" \
  --set openviking.config.storage.agfs.s3.endpoint="https://tos-s3-cn-beijing.volces.com"
```

---

## 4. 驗證

### 4.1 健康檢查

```bash
curl http://localhost:1933/health
# 期望返回: {"status":"ok"}
```

### 4.2 就緒檢查

就緒介面會檢測 AGFS（TOS）和 VikingDB 的連線狀態，是驗證憑據是否正確的關鍵步驟：

```bash
curl http://localhost:1933/ready
# 期望返回: {"status":"ready","checks":{"agfs":"ok","vectordb":"ok","api_key_manager":"ok"}}
```

如果某個元件報錯，請檢查：

| checks 欄位 | 失敗原因 | 排查方向 |
|-------------|---------|---------|
| `agfs` | TOS 連線失敗 | 檢查 bucket、endpoint、AK/SK 是否正確 |
| `vectordb` | VikingDB 連線失敗 | 檢查 region、AK/SK、服務是否已開通 |
| `api_key_manager` | root_api_key 未配置 | 檢查 `server.root_api_key` 欄位 |

---

## 5. 多租戶管理

OpenViking 支援多租戶隔離。配置了 `root_api_key` 後自動啟用多租戶模式。

### 5.1 建立租戶（Account）

使用 `root_api_key` 建立租戶，同時會生成一個管理員使用者：

```bash
curl -X POST http://localhost:1933/api/v1/admin/accounts \
  -H "X-API-Key: YOUR_ROOT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "my-team",
    "admin_user_id": "admin"
  }'
```

返回結果中包含管理員的 API Key，**請妥善儲存**：

```json
{
  "status": "ok",
  "result": {
    "account_id": "my-team",
    "admin_user_id": "admin",
    "user_key": "abcdef1234567890..."
  }
}
```

### 5.2 註冊普通使用者

租戶管理員可以為租戶新增使用者：

```bash
curl -X POST http://localhost:1933/api/v1/admin/accounts/my-team/users \
  -H "X-API-Key: ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "role": "user"
  }'
```

返回使用者的 API Key：

```json
{
  "status": "ok",
  "result": {
    "user_id": "alice",
    "user_key": "fedcba0987654321..."
  }
}
```

### 5.3 檢視租戶下的使用者

```bash
curl http://localhost:1933/api/v1/admin/accounts/my-team/users \
  -H "X-API-Key: ADMIN_API_KEY"
```

---

## 6. 執行示例

`examples/cloud/` 目錄下提供了完整的多租戶 demo 指令碼，演示從使用者建立到資料使用的全流程。

### 6.1 setup_users.py — 初始化租戶和使用者

建立租戶 `demo-team`，註冊 alice（管理員）和 bob（普通使用者），並將 API Key 寫入 `user_keys.json` 供後續指令碼使用。

```bash
# 確保 server 已啟動，且 root_api_key 與 ov.conf 一致
uv run examples/cloud/setup_users.py --url http://localhost:1933 --root-key <your-root-api-key>
```

### 6.2 alice.py — 技術負責人的使用流程

Alice 演示：新增專案文件 → 語義搜尋 → 多輪對話 → 沉澱記憶 → 回顧記憶。

```bash
uv run examples/cloud/alice.py
```

指令碼會自動從 `user_keys.json` 讀取 API Key。也可以手動指定：

```bash
uv run examples/cloud/alice.py --url http://localhost:1933 --api-key <alice_key>
```

### 6.3 bob.py — 新入職成員的使用流程

Bob 演示：瀏覽團隊資源 → 回顧團隊記憶（Alice 沉澱的決策） → 新增自己的資源 → 對話 → 沉澱記憶 → 帶上下文搜尋。

建議在 alice.py 執行完畢後執行，這樣 Bob 可以看到 Alice 沉澱的團隊記憶：

```bash
uv run examples/cloud/bob.py
```

### 完整流程彙總

```bash
# 1. 啟動服務（確保 ~/.openviking/ov.conf 已就位）
openviking-server &

# 2. 等待服務就緒
curl http://localhost:1933/ready

# 3. 建立使用者
uv run examples/cloud/setup_users.py --root-key <your-root-api-key>

# 4. Alice: 新增文件 + 對話 + 沉澱記憶
uv run examples/cloud/alice.py

# 5. Bob: 瀏覽團隊資源和記憶 + 入職學習
uv run examples/cloud/bob.py
```

---

## 7. 運維

### 日誌

容器日誌預設輸出到 stdout，可通過 `docker logs` 或 K8s 日誌系統檢視：

```bash
docker logs -f openviking
```

配置檔案中 `log.level` 可調整日誌級別（`DEBUG` / `INFO` / `WARN` / `ERROR`）。

### 監控

- 健康檢查：`GET /health`
- 就緒檢查：`GET /ready`（檢測 AGFS、VikingDB、APIKeyManager 連線狀態）
- 系統狀態：`GET /api/v1/system/status`

### 資料備份

- **TOS 資料**：通過 TOS 控制台配置跨區域複製或定期備份
- **本地資料**（如使用 PVC）：定期快照 PersistentVolume

---

## 8. 常見問題

### systemd 啟動失敗（status=203/EXEC）

`status=203/EXEC` 表示 systemd 找不到 `ExecStart` 指定的執行檔。常見於使用 venv / conda 環境安裝 OpenViking 的情況，`openviking-server` 不在 `/usr/local/bin/` 下。

排查步驟：

```bash
# 1. 查詢實際路徑
which openviking-server

# 2. 將輸出路徑替換到 service 檔案的 ExecStart
sudo sed -i 's|ExecStart=.*|ExecStart=/實際/路徑/openviking-server|' /etc/systemd/system/openviking.service

# 3. 重新載入並啟動
sudo systemctl daemon-reload
sudo systemctl restart openviking
sudo systemctl status openviking
```

### docker: command not found

系統未安裝 Docker，請參考 [Docker 官方安裝文件](https://docs.docker.com/engine/install/) 選擇對應系統的安裝方式。安裝完成後啟動 Docker：

```bash
sudo systemctl start docker
```

然後重新執行 `docker run` 命令即可。

### TOS 連線失敗（agfs check failed）

- **endpoint 錯誤**：確認使用 S3 相容 endpoint（帶 `tos-s3-` 字首），不要用標準 endpoint（`tos-cn-` 字首）
- **地域不匹配**：確認 `storage.agfs.s3.region` 和 `storage.agfs.s3.endpoint` 與桶所在地域一致
- **bucket 不存在**：確認 TOS 控制台中桶已建立，且名稱和地域與配置一致
- **AK/SK 無許可權**：確認 IAM 子使用者擁有 `TOSFullAccess` 或對應桶的訪問策略

### VikingDB 鑑權失敗（vectordb check failed）

- **服務未開通**：在火山引擎控制台確認 VikingDB 已開通
- **地域錯誤**：確認 `storage.vectordb.volcengine.region` 與開通服務的地域一致
- **AK/SK 錯誤**：確認 `storage.vectordb.volcengine.ak/sk` 與 IAM 金鑰一致
- **許可權不足**：確認 IAM 子使用者擁有 `VikingDBFullAccess` 策略

### Embedding 模型呼叫失敗

- **模型未開通**：在方舟控制台 **模型廣場** 中確認 `doubao-embedding-vision-251215` 已申請並通過
- **API Key 錯誤**：確認 `embedding.dense.api_key` 填寫正確
- **API Base 錯誤**：確認為 `https://ark.cn-beijing.volces.com/api/v3`

### helm: command not found

系統未安裝 Helm，需要先安裝：

```bash
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

安裝後驗證：

```bash
helm version
```

### Kubernetes cluster unreachable

```
Error: INSTALLATION FAILED: Kubernetes cluster unreachable: Get "http://localhost:8080/version": dial tcp [::1]:8080: connect: connection refused
```

伺服器上沒有執行 Kubernetes 叢集。可以使用 k3s 快速搭建輕量級叢集：

```bash
# 安裝 k3s
curl -sfL https://get.k3s.io | sh -

# 配置 kubeconfig
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# 永久生效
echo 'export KUBECONFIG=/etc/rancher/k3s/k3s.yaml' >> ~/.bashrc

# 驗證叢集就緒
kubectl get nodes
```

看到節點狀態為 `Ready` 後，再執行 `helm install` 命令。

### helm install 時 path not found

```
Error: INSTALLATION FAILED: path "./examples/k8s-helm" not found
```

需要在 OpenViking 專案根目錄下執行 `helm install` 命令：

```bash
cd /path/to/OpenViking
helm install openviking ./examples/k8s-helm -f my-values.yaml
```

### Helm 安裝後 Pod CrashLoopBackOff

- 檢查 `kubectl logs <pod-name>`，通常是配置欄位缺失
- 確認 values 檔案中包含完整的 storage、embedding、vlm 配置（參考第 3 節 Helm 部分）
- 確認 `openviking.config` 下的 JSON 結構正確（Helm 會將其序列化為 ov.conf）
