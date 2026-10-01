# VKE 部署指南

本文件介紹如何將 Vikingbot 部署到火山引擎容器服務（VKE）。

## 目錄

- [架構概述](#架構概述)
- [前置準備](#前置準備)
  - [1. 火山引擎帳號](#1-火山引擎帳號)
  - [2. 建立 VKE 叢集](#2-建立-vke-叢集)
  - [3. 建立容器映象倉庫](#3-建立容器映象倉庫)
  - [4. 建立 TOS 儲存桶（可選）](#4-建立-tos-儲存桶可選)
  - [5. 獲取訪問憑證](#5-獲取訪問憑證)
  - [6. 配置本地環境](#6-配置本地環境)
- [快速部署](#快速部署)
- [配置詳解](#配置詳解)
- [手動部署](#手動部署)
- [驗證部署](#驗證部署)
- [故障排查](#故障排查)

---

## 架構概述

```
┌─────────────────────────────────────────────────────────────┐
│                      火山引擎 VKE                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                   Namespace: default                   │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │              Deployment: vikingbot               │  │  │
│  │  │  ┌───────────────────────────────────────────┐  │  │  │
│  │  │  │  Pod (2 replicas)                         │  │  │  │
│  │  │  │  ┌─────────────────────────────────────┐  │  │  │  │
│  │  │  │  │  Container: vikingbot               │  │  │  │  │
│  │  │  │  │  - Port: 18791 (gateway)           │  │  │  │  │
│  │  │  │  │  - Volume: /root/.vikingbot         │  │  │  │  │
│  │  │  │  └─────────────────────────────────────┘  │  │  │  │
│  │  │  └───────────────────────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  │                                                           │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │  Service: vikingbot (ClusterIP)                │  │  │
│  │  │  - Port: 80 → TargetPort: 18791               │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  │                                                           │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │  PVC: vikingbot-data (10Gi)                    │  │  │
│  │  │  └──→ PV: vikingbot-tos-pv (TOS)              │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  TOS Bucket: vikingbot_data                          │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 前置準備

### 1. 火山引擎帳號

- 註冊火山引擎帳號：https://www.volcengine.com/
- 完成實名認證
- 開通以下服務：
  - **容器服務 VKE**
  - **容器映象服務 CR**
  - **物件儲存 TOS**（可選，用於持久化儲存）

---

### 2. 建立 VKE 叢集

1. 登入火山引擎控制台
2. 進入 **容器服務 VKE** → **叢集**
3. 點選 **建立叢集**
4. 配置叢集引數：
   - **叢集名稱**：vikingbot（或自定義）
   - **Kubernetes 版本**：選擇最新穩定版（推薦 1.24+）
   - **容器執行時**：containerd
   - **網路模式**：Flannel 或 Calico
   - **Service CIDR**：預設即可
5. 配置節點池：
   - **節點規格**：推薦 2核4G 或更高（ecs.g1.large）
   - **節點數量**：至少 2 個節點
   - **系統盤**：40Gi SSD
6. 確認配置並建立叢集

> **等待叢集建立完成**（約 10-15 分鐘）

---

### 3. 建立容器映象倉庫

1. 進入 **容器映象服務 CR** → **名稱空間**
2. 點選 **建立名稱空間**
   - 名稱：`vikingbot`
   - 型別：私有
3. 進入 **映象倉庫**
4. 點選 **建立映象倉庫**
   - 名稱：`vikingbot`
   - 名稱空間：選擇剛才建立的 `vikingbot`
   - 描述：Vikingbot 映象倉庫

---

### 4. 建立 TOS 儲存桶（可選）

如果使用 TOS 作為持久化儲存，需要建立儲存桶：

1. 進入 **物件儲存 TOS** → **儲存桶列表**
2. 點選 **建立儲存桶**
3. 配置引數：
   - **名稱**：`vikingbot-data`（或自定義）
   - **地域**：選擇與 VKE 叢集相同的地域（如 cn-beijing）
   - **儲存型別**：標準儲存
   - **許可權**：私有
4. 點選 **確定** 建立

---

### 5. 獲取訪問憑證

#### 5.1 建立 AccessKey（僅 TOS 儲存需要）

1. 滑鼠懸停在右上角頭像，點選 **API 訪問金鑰**
2. 點選 **新建金鑰**
3. 完成手機驗證
4. 保存生成的 **AccessKey ID** 和 **Secret Access Key**

> **重要**：Secret Access Key 只顯示一次，請妥善儲存！

#### 5.2 獲取 Kubeconfig

1. 進入 **容器服務 VKE** → **叢集**
2. 找到你的叢集，點選 **連線**
3. 在 **叢集訪問憑證** 頁籤，點選 **下載** 獲取 Kubeconfig
4. 將下載的檔案儲存到 `~/.kube/config`，或配置 `KUBECONFIG` 環境變數

驗證連線：
```bash
kubectl get nodes
```

---

### 6. 配置本地環境

確保本地已安裝：

- **Docker**：用於構建映象
- **kubectl**：用於操作 Kubernetes 叢集
- **Python 3**：部署指令碼需要

驗證安裝：
```bash
docker --version
kubectl version --client
python3 --version
```

---

## 快速部署

### 步驟 1：複製配置檔案

```bash
mkdir -p ~/.config/vikingbot
cp deploy/vke/vke_deploy.example.yaml ~/.config/vikingbot/vke_deploy.yaml
```

### 步驟 2：編輯配置

```bash
vim ~/.config/vikingbot/vke_deploy.yaml
```

填入以下信息：

```yaml
volcengine_region: cn-beijing               # 地域

image_registry: vikingbot-cn-beijing.cr.volces.com  # 映象倉庫地址
image_namespace: vikingbot
image_repository: vikingbot
image_tag: latest

# 映象倉庫登入憑證（如果是私有倉庫）
registry_username: "你的火山引擎帳號"
registry_password: "你的火山引擎密碼"

# 儲存型別：local (EBS) 或 tos
storage_type: tos

# TOS 配置（僅 storage_type=tos 時需要）
volcengine_access_key: AKLTxxxxxxxxxx
volcengine_secret_key: xxxxxxxxxx
tos_bucket: vikingbot_data
tos_path: /.vikingbot/
tos_region: cn-beijing
```

### 步驟 3：執行部署

```bash
cd /path/to/vikingbot
chmod +x deploy/vke/deploy.sh
deploy/vke/deploy.sh
```

部署指令碼會自動完成：
1. 構建 Docker 映象
2. 推送映象到火山引擎 CR
3. 建立 K8s 資源（Secret、PV、PVC、Deployment、Service）
4. 等待部署完成

---

## 配置詳解

### vke_deploy.yaml 配置項

| 配置項 | 說明 | 必填 | 示例 |
|--------|------|------|------|
| `volcengine_access_key` | 火山引擎 AccessKey ID | 執行 TOS 部署時 | `AKLTxxxx` |
| `volcengine_secret_key` | 火山引擎 Secret Access Key | 執行 TOS 部署時 | `xxxx` |
| `volcengine_region` | 地域 | 是 | `cn-beijing` |
| `image_registry` | 映象倉庫地址 | 是 | `vikingbot-cn-beijing.cr.volces.com` |
| `image_namespace` | 名稱空間 | 是 | `vikingbot` |
| `image_repository` | 倉庫名稱 | 是 | `vikingbot` |
| `image_tag` | 映象標籤 | 否 | `latest` |
| `use_timestamp_tag` | 使用時間戳標籤 | 否 | `false` |
| `registry_username` | 映象倉庫使用者名稱 | 否 | |
| `registry_password` | 映象倉庫密碼 | 否 | |
| `storage_type` | 儲存型別：`local` 或 `tos` | 否 | `local` |
| `tos_bucket` | TOS 桶名 | storage_type=tos | `vikingbot_data` |
| `tos_path` | TOS 路徑 | storage_type=tos | `/.vikingbot/` |
| `tos_region` | TOS 地域 | storage_type=tos | `cn-beijing` |
| `k8s_namespace` | K8s 名稱空間 | 否 | `default` |
| `k8s_replicas` | Pod 副本數 | 否 | `1` |
| `kubeconfig_path` | kubeconfig 路徑 | 否 | `~/.kube/config` |

---

## 手動部署

如果不想使用一鍵部署指令碼，可以按以下步驟手動操作。

### 1. 構建並推送映象

```bash
# 構建映象
docker build --platform linux/amd64 -f deploy/Dockerfile -t vikingbot .

# 登入映象倉庫
docker login vikingbot-cn-beijing.cr.volces.com -u <username> -p <password>

# Tag 映象
docker tag vikingbot vikingbot-cn-beijing.cr.volces.com/vikingbot/vikingbot:latest

# 推送
docker push vikingbot-cn-beijing.cr.volces.com/vikingbot/vikingbot:latest
```

### 2. 準備 Kubernetes Manifest

複製 `deploy/vke/k8s/deployment.yaml`，替換以下變數：

- `__IMAGE_NAME__`：完整映象名
- `__REPLICAS__`：副本數
- `__ACCESS_MODES__`：訪問模式（`ReadWriteOnce` 或 `ReadWriteMany`）
- `__STORAGE_CLASS_CONFIG__`：StorageClass 配置
- `__VOLUME_NAME_CONFIG__`：VolumeName 配置

### 3. 建立 TOS Secret（僅使用 TOS 時）

```bash
# Base64 編碼 AccessKey
AK_B64=$(echo -n "your-access-key" | base64)
SK_B64=$(echo -n "your-secret-key" | base64)

# 建立 Secret
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: vikingbot-tos-secret
type: Opaque
data:
  AccessKeyId: ${AK_B64}
  SecretAccessKey: ${SK_B64}
EOF
```

### 4. 部署應用

```bash
kubectl apply -f deploy/vke/k8s/deployment.yaml
```

---

## 驗證部署

### 檢視 Pod 狀態

```bash
kubectl get pods -l app=vikingbot
```

預期輸出：
```
NAME                         READY   STATUS    RESTARTS   AGE
vikingbot-746d99fd94-xxxxx   1/1     Running   0          2m
```

### 查看 Service

```bash
kubectl get svc vikingbot
```

### 檢視日誌

```bash
# 檢視所有 Pod 日誌
kubectl logs -l app=vikingbot --tail=100

# 跟隨日誌
kubectl logs -f deployment/vikingbot
```

### 檢視部署狀態

```bash
kubectl rollout status deployment/vikingbot
```

### 訪問 Gateway（本地埠轉發）

```bash
kubectl port-forward svc/vikingbot 8080:80
```

然後訪問：http://localhost:8080

---

## 故障排查

### Pod 無法啟動

```bash
# 查看 Pod 事件
kubectl describe pod <pod-name>

# 檢視日誌
kubectl logs <pod-name>
```

### 映象拉取失敗

檢查：
1. 映象倉庫地址是否正確
2. 映象是否已推送
3. 倉庫是否為私有，是否配置了 ImagePullSecret

### 儲存掛載失敗

```bash
# 檢視 PVC 狀態
kubectl get pvc

# 檢視 PV 狀態
kubectl get pv

# 查看事件
kubectl describe pvc vikingbot-data
```

### 健康檢查失敗

健康檢查路徑：`/health`，埠：`18791`

```bash
# 進入 Pod 內部檢查
kubectl exec -it <pod-name> -- bash

# 在 Pod 內測試
curl http://localhost:18791/health
```

---

## 常用命令

```bash
# 擴容/縮容
kubectl scale deployment vikingbot --replicas=3

# 更新映象
kubectl set image deployment/vikingbot vikingbot=vikingbot-cn-beijing.cr.volces.com/vikingbot/vikingbot:new-tag

# 重啟 Deployment
kubectl rollout restart deployment/vikingbot

# 回滾
kubectl rollout undo deployment/vikingbot

# 刪除所有資源
kubectl delete -f deploy/vke/k8s/deployment.yaml
```

---

## 附錄

### 地域列表

| 地域 ID | 地域名稱 |
|---------|----------|
| cn-beijing | 華北2（北京） |
| cn-shanghai | 華東2（上海） |
| cn-guangzhou | 華南1（廣州） |
| cn-shenzhen | 華南2（深圳） |

### 映象倉庫地址格式

```
{namespace}-{region}.cr.volces.com
```

示例：`vikingbot-cn-beijing.cr.volces.com`

---

## 參考連結

- [火山引擎 VKE 文件](https://www.volcengine.com/docs/6460)
- [火山引擎 CR 文件](https://www.volcengine.com/docs/6420)
- [火山引擎 TOS 文件](https://www.volcengine.com/docs/6349)
- [Kubernetes 官方文件](https://kubernetes.io/docs/)
