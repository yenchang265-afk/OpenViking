# OpenViking Helm Chart

此 Helm Chart 用於在 Kubernetes 上部署 OpenViking，提供可擴充、生產就緒的 RAG（檢索增強生成）和語義搜尋服務。

## 概述

[OpenViking](https://github.com/volcengine/OpenViking) 是一個開源的 RAG 和語義搜尋引擎，作為上下文資料庫 MCP（Model Context Protocol）伺服器執行。此 Helm Chart 支援在 Kubernetes 叢集上輕鬆部署，相容主流雲服務商。

## 前置條件

- Kubernetes 1.24+
- Helm 3.8+
- 有效的火山引擎 API Key（用於 embedding 和 VLM 服務）

## 安裝

### 新增 Helm 倉庫（釋出後可用）

```bash
helm repo add openviking https://volcengine.github.io/openviking
helm repo update
```

### 從本地 Chart 安裝

```bash
# 克隆倉庫
git clone https://github.com/volcengine/OpenViking.git
cd OpenViking/deploy/helm

# 使用預設值安裝
helm install openviking ./openviking

# 使用自定義值安裝
helm install openviking ./openviking -f my-values.yaml
```

### 快速開始

```bash
# GCP 部署
helm install openviking ./openviking \
  --set cloudProvider=gcp \
  --set openviking.config.embedding.dense.api_key=YOUR_API_KEY

# AWS 部署
helm install openviking ./openviking \
  --set cloudProvider=aws \
  --set openviking.config.embedding.dense.api_key=YOUR_API_KEY
```

## 配置

### 雲服務商支援

此 Chart 支援為主流雲服務商自動配置 LoadBalancer 註解：

| 雲服務商 | 配置值 |
|----------|--------|
| Google Cloud Platform | `cloudProvider: gcp` |
| Amazon Web Services | `cloudProvider: aws` |
| 其他/通用 | `cloudProvider: ""`（預設） |

### 關鍵配置選項

| 引數 | 說明 | 預設值 |
|------|------|--------|
| `cloudProvider` | 雲服務商，用於 LoadBalancer 註解 | `""` |
| `replicaCount` | 副本數量 | `1` |
| `image.repository` | 容器映象倉庫 | `ghcr.io/astral-sh/uv` |
| `image.tag` | 容器映象標籤 | `python3.12-bookworm` |
| `service.type` | Kubernetes 服務型別 | `LoadBalancer` |
| `service.port` | 服務埠 | `1933` |
| `openviking.config.server.api_key` | 認證 API Key | `null` |
| `openviking.config.embedding.dense.api_key` | 火山引擎 API Key | `null` |

### OpenViking 配置

`ov.conf` 中的所有 OpenViking 配置選項都在 `openviking.config` 下可用。完整預設配置請參見 `values.yaml`。

### Embedding 配置

Embedding 服務需要火山引擎 API Key：

```yaml
openviking:
  config:
    embedding:
      dense:
        api_key: "your-api-key-here"
        api_base: "https://ark.cn-beijing.volces.com/api/v3"
        model: "doubao-embedding-vision-251215"
```

### VLM 配置

視覺語言模型支援：

```yaml
openviking:
  config:
    vlm:
      api_key: "your-api-key-here"
      api_base: "https://ark.cn-beijing.volces.com/api/v3"
      model: "doubao-seed-2-0-lite-260428"
```

## 儲存

### 預設（emptyDir）

預設情況下，Chart 使用 `emptyDir` 捲進行資料儲存。這適用於開發和測試，但 Pod 重啟後**資料將丟失**。

### 持久化儲存（可選）

使用 PVC 啟用持久化儲存：

```yaml
openviking:
  dataVolume:
    enabled: true
    usePVC: true
    size: 50Gi
    storageClassName: standard
    accessModes:
      - ReadWriteOnce
```

## 安全

### API Key 認證

啟用 API Key 認證以保護 OpenViking 伺服器：

```yaml
openviking:
  config:
    server:
      api_key: "your-secure-api-key"
      cors_origins:
        - "https://your-domain.com"
```

### 金鑰管理

生產環境建議使用 Kubernetes Secrets 或外部金鑰管理：

```bash
# 從字面值建立 Secret
kubectl create secret generic openviking-config \
  --from-literal=ov.conf='{"server":{"api_key":"secret"}}'

# 或掛載現有 Secret
helm install openviking ./openviking \
  --set existingSecret=openviking-config
```

## 自動擴縮容

為生產工作負載啟用 Horizontal Pod Autoscaler：

```yaml
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 80
  targetMemoryUtilizationPercentage: 80
```

## 資源限制

預設資源配置：

```yaml
resources:
  limits:
    cpu: 2000m
    memory: 4Gi
  requests:
    cpu: 500m
    memory: 1Gi
```

根據工作負載需求調整。

## 使用示例

### 使用 CLI 連線

```bash
# 獲取 LoadBalancer IP
export OPENVIKING_IP=$(kubectl get svc openviking -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# 建立 CLI 配置
cat > ~/.openviking/ovcli.conf <<EOF
{
  "url": "http://$OPENVIKING_IP:1933",
  "api_key": null,
  "output": "table"
}
EOF

# 測試連線
openviking health
```

### Python 客戶端

```python
from openviking_sdk import SyncHTTPClient

# 獲取服務端點
# kubectl get svc openviking

client = SyncHTTPClient(url="http://<load-balancer-ip>:1933", api_key="your-key")
client.initialize()

# 新增資源
client.add_resource(path="./document.pdf")
client.wait_processed()

# 搜索
results = client.find("your search query")
print(results)

client.close()
```

## 故障排除

### Pod 啟動失敗

檢查 Pod 日誌：
```bash
kubectl logs -l app.kubernetes.io/name=openviking
```

### 健康檢查失敗

驗證配置：
```bash
kubectl get secret openviking-config -o jsonpath='{.data.ov\.conf}' | base64 -d
```

### LoadBalancer 未獲取 IP

等待雲服務商分配負載均衡器：
```bash
kubectl get svc openviking -w
```

檢查 `values.yaml` 中雲服務商特定的註解。

## 解除安裝

```bash
helm uninstall openviking
```

刪除持久化資料（如果啟用了 PVC）：
```bash
kubectl delete pvc openviking-data
```

## 貢獻

歡迎貢獻！請參見 [OpenViking 倉庫](https://github.com/volcengine/OpenViking) 的貢獻指南。

## 許可證

此 Helm Chart 採用 Apache License 2.0 許可證，與 OpenViking 專案許可證一致。
