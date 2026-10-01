# Vikingbot Docker 一鍵部署

本目錄提供 Vikingbot 的 Docker 一鍵部署指令碼，支援本地快速部署和多架構支援。

## 前置要求

請先安裝 Docker：

- **macOS**: 下載 [Docker Desktop](https://www.docker.com/products/docker-desktop)
- **Windows**: 下載 [Docker Desktop](https://www.docker.com/products/docker-desktop)
- **Linux**: 參考 [Docker 官方文件](https://docs.docker.com/engine/install/)

部署指令碼還會使用 Python 3 驗證現有 `ov.conf` 的 JSON 結構和 Gateway 埠。

驗證依賴：
```bash
docker --version
python3 --version
```

## 快速開始

### 從火山引擎映象部署（推薦）

如果你已經有推送到火山引擎映象倉庫的映象，可以直接拉取並部署：

```bash
# 1. 建立必要的目錄結構
mkdir -p ~/.vikingbot/

# 2. 啟動容器
docker run -d \
    --name vikingbot \
    --restart unless-stopped \
    --platform linux/amd64 \
    -v ~/.vikingbot:/root/.vikingbot \
    -p 18791:18791 \
    vikingbot-cn-beijing.cr.volces.com/vikingbot/vikingbot:latest \
    gateway

# 3. 檢視日誌
docker logs --tail 50 -f vikingbot
```

按 `Ctrl+C` 退出日誌檢視，容器繼續後臺執行。

### 原生代碼構建映象部署

如果你想從原生代碼構建映象並部署：

#### 一行命令部署

```bash
./deploy/docker/deploy.sh
```

指令碼會自動檢測本地架構（arm64/amd64）並構建適配的映象。

#### 分步部署

##### 1. 構建映象

```bash
./deploy/docker/build-image.sh
```

##### 2. 部署服務

```bash
./deploy/docker/deploy.sh
```

##### 3. 停止服務

```bash
./deploy/docker/stop.sh
```

## 多架構支援

指令碼自動支援多架構，無需手動配置！

### 自動檢測（推薦）

指令碼會自動檢測你的系統架構並使用對應映象：

```bash
# Apple Silicon (M1/M2/M3) - 自動使用 linux/arm64
./deploy/docker/deploy.sh

# Intel/AMD - 自動使用 linux/amd64
./deploy/docker/deploy.sh
```

### 手動指定架構

如需手動指定：

```bash
# 構建 arm64 映象（Apple Silicon）
PLATFORM=linux/arm64 ./deploy/docker/build-image.sh

# 構建 amd64 映象（Intel/AMD）
PLATFORM=linux/amd64 ./deploy/docker/build-image.sh

# 同時構建兩個架構（多架構映象）
MULTI_ARCH=true ./deploy/docker/build-image.sh
```

### 使用指定架構部署

```bash
# 使用 arm64 映象部署
PLATFORM=linux/arm64 ./deploy/docker/deploy.sh

# 使用 amd64 映象部署
PLATFORM=linux/amd64 ./deploy/docker/deploy.sh
```

## 檔案說明

| 檔案 | 說明 |
|------|------|
| `build-image.sh` | 一鍵構建 Docker 映象（支援多架構） |
| `deploy.sh` | 一鍵部署（自動構建映象+啟動容器，自動檢測架構） |
| `stop.sh` | 停止並清理容器 |
| `image_upload.sh` | 將本地映象上傳到火山引擎映象倉庫 |
| `image_upload.example.yaml` | 映象上傳配置檔案示例 |
| `README.md` | 本文件 |

## 使用 Docker Compose

專案根目錄也提供了 `docker-compose.yml`：

```bash
# 啟動服務
docker-compose up -d

# 檢視日誌
docker-compose logs -f

# 停止服務
docker-compose down
```

## 環境變數配置

### build-image.sh

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `IMAGE_NAME` | `vikingbot` | 映象名稱 |
| `IMAGE_TAG` | `latest` | 映象標籤 |
| `DOCKERFILE` | `deploy/Dockerfile` | Dockerfile 路徑 |
| `NO_CACHE` | `false` | 是否不使用快取 |
| `PLATFORM` | 自動檢測 | 目標平臺 (linux/amd64, linux/arm64) |
| `MULTI_ARCH` | `false` | 是否構建多架構映象 |

**示例：**

```bash
# 構建帶版本標籤的映象
IMAGE_TAG=v1.0.0 ./deploy/docker/build-image.sh

# 不使用快取重新構建
NO_CACHE=true ./deploy/docker/build-image.sh

# 構建 arm64 映象
PLATFORM=linux/arm64 ./deploy/docker/build-image.sh

# 同時構建 amd64+arm64 多架構映象
MULTI_ARCH=true ./deploy/docker/build-image.sh
```

### deploy.sh

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `CONTAINER_NAME` | `vikingbot` | 容器名稱 |
| `IMAGE_NAME` | `vikingbot` | 映象名稱 |
| `IMAGE_TAG` | `latest` | 映象標籤 |
| `HOST_PORT` | `18791` | 主機埠 |
| `CONTAINER_PORT` | `18791` | 容器端口 |
| `COMMAND` | `gateway` | 啟動命令 |
| `AUTO_BUILD` | `true` | 映象不存在時自動構建 |
| `PLATFORM` | 自動檢測 | 使用的映象平臺 |

**示例：**

```bash
# 使用自定義埠
HOST_PORT=8080 ./deploy/docker/deploy.sh

# 不自動構建映象
AUTO_BUILD=false ./deploy/docker/deploy.sh

# 強制使用 arm64 映象
PLATFORM=linux/arm64 ./deploy/docker/deploy.sh
```

### stop.sh

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `CONTAINER_NAME` | `vikingbot` | 容器名稱 |
| `REMOVE_IMAGE` | `false` | 是否同時刪除映象 |
| `REMOVE_VOLUME` | `false` | 是否同時刪除資料卷 |

**示例：**

```bash
# 完全清理（容器+映象+資料卷）
REMOVE_IMAGE=true REMOVE_VOLUME=true ./deploy/docker/stop.sh
```

## 配置文件

首次部署時，指令碼會自動建立配置檔案：`~/.vikingbot/ov.conf`。指令碼同時生成隨機 Gateway Token；在非本機請求中通過 `X-Gateway-Token` 請求頭傳入該值。

編輯該檔案填入你的 API keys：

```json
{
  "bot": {
    "agents": {
      "provider": "openrouter",
      "model": "openrouter/anthropic/claude-3.5-sonnet",
      "api_key": "sk-or-xxx"
    },
    "gateway": {
      "host": "0.0.0.0",
      "port": 18791,
      "token": "指令碼生成的隨機值"
    }
  }
}
```

**重要：** `bot.gateway.port` 必須與 `CONTAINER_PORT` 一致；指令碼預設都使用 **18791**。如果現有配置不是有效 JSON、缺少 `bot.gateway`，或埠不一致，部署會在替換舊容器前停止並提示修復配置。

## 訪問控制台

部署成功後，訪問：http://localhost:18791

## 常用命令

```bash
# 檢視日誌
docker logs -f vikingbot

# 進入容器
docker exec -it vikingbot bash

# 執行 vikingbot 命令
docker exec vikingbot vikingbot status

# 重啟容器
docker restart vikingbot
```

## 架構相容性說明

| 系統 | 架構 | 自動檢測 | 手動指定 |
|------|------|----------|----------|
| Apple Silicon (M1/M2/M3) | arm64 | ✓ | `PLATFORM=linux/arm64` |
| Intel Mac | amd64 | ✓ | `PLATFORM=linux/amd64` |
| Linux PC/Server | amd64 | ✓ | `PLATFORM=linux/amd64` |
| Linux ARM Server | arm64 | ✓ | `PLATFORM=linux/arm64` |
| Windows (WSL2) | amd64 | ✓ | `PLATFORM=linux/amd64` |

## 與 VKE 部署共用 Dockerfile

注意：本地 Docker 部署和 VKE 部署**共用同一個 Dockerfile**（`deploy/Dockerfile`），確保了環境一致性。

- VKE 部署：使用 `deploy/vke/vke_deploy.py`
- 本地部署：使用 `deploy/docker/deploy.sh`
- 兩者都使用：`deploy/Dockerfile`

Dockerfile 已移除平臺硬編碼，支援靈活的多架構構建！

## 跨平臺映象構建（推送到倉庫）

如果你需要構建可以在 Windows/Mac/Linux 多平臺執行的映象，可以使用 `build-multiarch.sh`：

### 前置準備

1. 準備一個 Docker 映象倉庫（如 Docker Hub, ACR, Harbor 等）
2. 登入到映象倉庫

### 構建並推送跨平臺映象

```bash
# 構建 linux/amd64 + linux/arm64 雙架構映象並推送
REGISTRY=your-registry.com PUSH=true ./deploy/docker/build-multiarch.sh
```

### 環境變數配置

| 變數 | 說明 | 示例 |
|------|------|------|
| `REGISTRY` | 映象倉庫地址 | `registry.example.com` |
| `IMAGE_NAME` | 映象名稱 | `vikingbot` |
| `IMAGE_TAG` | 映象標籤 | `latest` |
| `PUSH` | 是否推送 | `true` / `false` |
| `PLATFORMS` | 目標架構 | `linux/amd64,linux/arm64` |

### 使用跨平臺映象

推送成功後，在任何平臺都可以直接使用：

```bash
# 在 Apple Silicon Mac 上
PLATFORM=linux/arm64 ./deploy/docker/deploy.sh

# 在 Intel/AMD Linux 上
PLATFORM=linux/amd64 ./deploy/docker/deploy.sh

# 或讓指令碼自動檢測
./deploy/docker/deploy.sh
```

### 驗證映象架構

```bash
# 檢視映象支援的架構
docker manifest inspect your-registry.com/vikingbot:latest
```
