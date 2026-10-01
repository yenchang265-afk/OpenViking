# 服務端部署

OpenViking 以 HTTP 服務執行。安裝服務端之前，先選擇由誰執行服務：

| 服務方式 | 你需要準備什麼 |
| --- | --- |
| [火山引擎託管 OpenViking](https://www.volcengine.com/product/openviking-service) | 在[控制台](https://console.volcengine.com/vikingdb/openviking/region:openviking+cn-beijing)獲取 API Key，用獨立 CLI 連線，無需本地服務端或模型配置。 |
| 團隊已有服務或他人部署 | 向管理員獲取服務地址和 user/admin key。 |
| 自建 OpenViking | 按下文安裝、配置和執行服務端。 |

託管及已有服務使用者可直接從 [CLI 快速開始](../getting-started/02-quickstart.md)進入。託管服務的可用範圍、套餐和額度見[官方服務文件](https://docs.volcengine.com/docs/84313/2374478)。

本頁後續內容適用於自建服務。

容量規劃應使用有代表性的資料集和預期併發量測量記憶體、磁碟佔用，為原始檔案、索引和快照預留空間。擴大工作負載前，通過[可觀測性](../guides/05-observability.md)檢查容量餘量。

## 快速開始

先按[自建服務快速開始](../getting-started/02-quickstart.md)安裝服務端。Python 3.14 下使用火山引擎 Ark 時，上游 Python SDK 可能輸出 Pydantic V1 相容性警告；此場景可使用 Python 3.13 避免該警告。

```bash
# 使用初始化嚮導建立或重新整理 ~/.openviking/ov.conf
openviking-server init

# 如果你在嚮導中選擇 OpenAI Codex，init 會幫你處理 Codex 登入/匯入

# 啟動前校驗本地配置、模型訪問和鑑權狀態
openviking-server doctor

# 配置檔案在預設路徑 ~/.openviking/ov.conf 時，直接啟動
openviking-server

# 配置檔案在其他位置時，通過 --config 指定
openviking-server --config /path/to/ov.conf

# 在另一終端按快速開始配置 ov，連線本服務後驗證
ov health
```

## 命令列選項

| 選項 | 描述 | 預設值 |
|------|------|--------|
| `--config` | 配置檔案路徑 | `~/.openviking/ov.conf` |
| `--host` | 繫結的主機地址 | `127.0.0.1` |
| `--port` | 繫結的埠 | `1933` |

**示例**

```bash
# 使用預設配置
openviking-server

# 使用自定義埠
openviking-server --port 8000

# 指定配置檔案、主機地址和埠
openviking-server --config /path/to/ov.conf --host 127.0.0.1 --port 8000
```

## 配置

服務端從 `ov.conf` 讀取所有配置。配置檔案各段詳情見 [配置指南](01-configuration.md)。

`ov.conf` 中的 `server` 段控制服務端行為：

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 1933,
    "root_api_key": "your-secret-root-key",
    "cors_origins": ["*"]
  },
  "storage": {
    "workspace": "./data",
    "agfs": { "backend": "local" },
    "vectordb": { "backend": "local" }
  }
}
```

## 部署模式

### 獨立模式（嵌入儲存）

伺服器管理本地 RAGFS 和 VectorDB。在 `ov.conf` 中配置本地儲存路徑：

```json
{
  "storage": {
    "workspace": "./data",
    "agfs": { "backend": "local" },
    "vectordb": { "backend": "local" }
  }
}
```

```bash
openviking-server
```

## 使用 Systemd 部署服務（推薦）

對於 Linux 系統，可以使用 Systemd 服務來管理 OpenViking，實現自動重啟、開機自啟等功能。首先，你應該已經成功安裝並配置了 OpenViking 伺服器，確保它可以正常執行，再進行服務化部署。

### 建立 Systemd 服務檔案

建立 `/etc/systemd/system/openviking.service` 檔案：

```ini
[Unit]
Description=OpenViking HTTP Server
After=network.target

[Service]
Type=simple
# 替換為執行 OpenViking 的使用者
User=your-username
# 替換為使用者組
Group=your-group
# 替換為工作目錄
WorkingDirectory=/var/lib/openviking
# 使用實際安裝位置中的絕對路徑
ExecStart=/path/to/your/python/bin/openviking-server
Restart=always
RestartSec=5
# 配置檔案路徑
Environment="OPENVIKING_CONFIG_FILE=/etc/openviking/ov.conf"

[Install]
WantedBy=multi-user.target
```

啟動前替換所有佔位值。以服務使用者執行 `command -v openviking-server` 確認執行檔路徑，建立工作目錄，並讓該使用者能夠訪問配置、workspace 及本地加密金鑰。此 unit 使用 `/etc/openviking/ov.conf`，不會自動使用你個人 home 目錄下生成的配置。系統服務省略 `User` 會以 root 執行。

### 管理服務

建立好服務檔案後，使用以下命令管理 OpenViking 服務：

```bash
# 過載 systemd 配置
sudo systemctl daemon-reload

# 啟動服務
sudo systemctl start openviking.service

# 設定開機自啟
sudo systemctl enable openviking.service

# 檢視服務狀態
sudo systemctl status openviking.service

# 檢視服務日誌
sudo journalctl -u openviking.service -f
```

## 連線客戶端

### Python SDK

```bash
python -m pip install --upgrade openviking-sdk
```

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(url="http://localhost:1933", api_key="your-key")
client.initialize()

results = client.find(query="how to use openviking")
client.close()
```

### CLI

CLI 從 `ovcli.conf` 讀取連線配置。在 `~/.openviking/ovcli.conf` 中配置：

```json
{
  "url": "http://localhost:1933",
  "api_key": "your-key"
}
```

也可通過 `OPENVIKING_CLI_CONFIG_FILE` 環境變數指定配置檔案路徑：

```bash
export OPENVIKING_CLI_CONFIG_FILE=/path/to/ovcli.conf
```

### curl

```bash
curl http://localhost:1933/api/v1/fs/ls?uri=viking:// \
  -H "X-API-Key: your-key"
```

## 雲原生部署

### Docker

OpenViking 提供預構建的 Docker 映象，釋出在 GitHub Container Registry。執行目錄為 `/app/.openviking`，因此預設的 `storage.workspace`（`./data`）解析為 `/app/.openviking/data`。預設工作區、`ov.conf` 和 `ovcli.conf` 共用一個持久卷。若將工作區配置為此目錄以外的絕對路徑，需要另外掛載該路徑：

```bash
docker run -d \
  --name openviking \
  -p 1933:1933 \
  -v ~/.openviking:/app/.openviking \
  --restart unless-stopped \
  ghcr.io/volcengine/openviking:latest
```

> 推薦優先使用 `ghcr.io` 映象；如果訪問有問題，可改用 `openviking-cn-beijing.cr.volces.com/volcengine/openviking:latest`。本節後續命令同理。

Docker 映象預設會同時啟動：
- OpenViking HTTP 服務，埠 `1933`（繫結 `0.0.0.0`），同時在 `/studio` 提供 Web Studio 前端
- `vikingbot` gateway

由於容器內服務繫結 `0.0.0.0`（Docker 埠對映所必需），你**必須**在 `ov.conf` 中設定 `root_api_key`：

```json
{
  "server": {
    "root_api_key": "your-secret-root-key"
  }
}
```

未設定時服務將拒絕啟動。如需自定義繫結地址，可通過環境變數 `OPENVIKING_SERVER_HOST` 覆蓋。

**從舊映象升級：** 執行目錄為 `/app` 的舊映象會把 `./data` 解析為預設掛載之外的 `/app/data`。刪除舊容器前，先停止容器並備份其實際工作區（例如 `docker cp openviking:/app/data ./openviking-data-backup`）。啟動替換容器前，將備份恢復到掛載的宿主機工作區，通常為 `~/.openviking/data`。若目標工作區已存在，先確認要保留的資料，不要直接覆蓋。絕對工作區路徑不變；其他相對路徑現在以 `/app/.openviking` 為基準。

升級容器的方式
```bash
docker stop openviking
docker pull ghcr.io/volcengine/openviking:latest
docker rm -f openviking
# 然後重新 docker run ...
```

如果你希望本次容器啟動時關閉 `vikingbot`，可以使用下面任一方式：

```bash
docker run -d \
  --name openviking \
  -p 1933:1933 \
  -v ~/.openviking:/app/.openviking \
  --restart unless-stopped \
  ghcr.io/volcengine/openviking:latest \
  --without-bot
```

```bash
docker run -d \
  --name openviking \
  -e OPENVIKING_WITH_BOT=0 \
  -p 1933:1933 \
  -v ~/.openviking:/app/.openviking \
  --restart unless-stopped \
  ghcr.io/volcengine/openviking:latest
```

#### 無法使用 `docker -v` 時

部分託管平臺（如 Railway、Fly.io、Heroku 這類 PaaS）不支援把宿主機目錄繫結掛載進容器。這種環境下，如果容器啟動時找不到 `ov.conf`，entrypoint 不會崩潰 —— 它會列印一段修復指引並阻塞等待檔案出現。你可以選用以下兩種方式之一：

**方案 A：通過 `OPENVIKING_CONF_CONTENT` 注入完整配置內容。** entrypoint 會在啟動 server 前把這個環境變數的值寫入到 `OPENVIKING_CONFIG_FILE`（預設 `/app/.openviking/ov.conf`）：

```bash
docker run -d \
  --name openviking \
  -p 1933:1933 \
  -e OPENVIKING_CONF_CONTENT="$(cat ~/.openviking/ov.conf)" \
  --restart unless-stopped \
  ghcr.io/volcengine/openviking:latest
```

**方案 B：容器起來之後再 `docker exec` 進去用嚮導配置。** 容器在等待 `ov.conf` 期間是存活的，`exec` 進去執行 setup wizard，它會按 `OPENVIKING_CONFIG_FILE` 寫到 server 正在監聽的位置：

```bash
docker exec -it openviking openviking-server init
```

`ov.conf` 出現後，entrypoint 會自動恢復並啟動 server。

也可以使用 Docker Compose，專案根目錄提供了 `docker-compose.yml`：

```bash
docker compose up -d
```

啟動後可以訪問：
- API 服務：`http://localhost:1933`
- Web Studio：`http://localhost:1933/studio`（與 API 同源）
- 相容入口：`http://localhost:1934`（Caddy 反代到 1933，僅為已有部署保留）

### 部署到 Railway

點選下方按鈕一鍵部署到 Railway：

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/openviking)

#### 預置資源與環境

- **服務映象**：拉取官方映象 `ghcr.io/volcengine/openviking:latest`，監聽 1933 埠，Railway 自動分配 HTTPS 域名。
- **持久化儲存**：掛載持久卷至 `/app/.openviking`，`storage.workspace` 位於該捲上，保證重新部署後資料與配置不丟失。
- **預設配置**：預設採用 OpenAI 預設。部署時僅需填寫 `OPENAI_API_KEY`；管理員金鑰 `OPENVIKING_ROOT_API_KEY` 自動生成，部署完成後可在 Railway 的 **Variables** 標籤頁檢視。

#### 快速初始化（Web Studio）

部署完成後，在瀏覽器中即可完成首次初始化：

1. **配置管理員金鑰**：從 Railway 服務變數中複製 `OPENVIKING_ROOT_API_KEY`，訪問 `https://<你的域名>/studio/settings` 並儲存。
2. **建立使用者**：進入 `https://<你的域名>/studio/users` 建立首個帳戶與使用者，系統將展示該使用者的 API Key。
3. **開始使用**：後續訪問 Web Studio、`ov` CLI 或 SDK 時，均使用上述使用者的 API Key。

#### 配置管理

- **首次生成配置**：模板在 `OPENVIKING_CONF_CONTENT` 中預置了完整配置並引用 `${OPENAI_API_KEY}`。該變數僅在首次啟動且 `ov.conf` 尚不存在時生效。
- **後續修改配置**：首次啟動後，請通過 `railway ssh` 或 `railway service files upload --overwrite` 直接修改持久捲上的 `ov.conf`；也可以刪除 `ov.conf` 後重新部署，讓服務按當前 `OPENVIKING_CONF_CONTENT` 重新生成配置檔案。

#### 資源與費用參考

- **推薦配置**：長期執行建議選擇 **Hobby** 計劃（$5/月，包含 $5 用量抵扣）。以 ~0.5 GB 常駐記憶體估算，月均成本通常在 $5–$7 左右。
- **免費額度說明**：Railway Free 計劃（$1/月額度）不足以支援服務常駐執行；Trial 贈金適合短期體驗評估，額度到期 30 天后持久卷將被清理，請注意按需備份資料。

> **安全提示**：服務部署後預設監聽並暴露於公網。請妥善保管 `OPENVIKING_ROOT_API_KEY`，在對外開放前請閱讀[公網訪問安全指南](12-public-access.md)。

### 多例項部署注意事項

使用本地向量後端（`local` 或 `cuvs`）時，OpenViking 預設通過作業系統檔案鎖獨佔 `storage.workspace`。`.openviking.lock` 檔案會保留在磁碟上，檔案存在不代表服務正在執行；正常關閉或程序終止後，作業系統會釋放鎖。不要手動刪除執行中服務的鎖檔案。

遠端向量後端（`http`、`volcengine`、`vikingdb`）不會獲取此 workspace 鎖，包括檔案存放在共享 NAS 上的情況，無需設定 `storage.skip_process_lock=true`。把本地向量資料庫放在 NAS 上，並不會使它支援多程序共享。

使用本地向量後端從 `.openviking.pid` 舊版本升級時，必須先停止所有使用該 workspace 的舊版服務，再啟動新版。新版不再根據遺留 PID 判斷目錄是否被佔用，新舊鎖機制不支援混用。

多例項部署時，通常建議注意這幾項配置：

- 把 `server.temp_upload.default_mode` 設為 `"shared"`，這樣臨時上傳檔案可以被其他副本消費。
- 共享儲存應使用遠端向量後端。保留的 `storage.skip_process_lock` 開關只關閉本地後端的啟動保護，不會使本地向量儲存支援多程序共享。
- 對 QueueFS，建議通過 `storage.agfs.queuefs.db_path` 顯式指定例項本地的 SQLite 路徑。如果啟用了 usage audit，建議通過 `server.observability.usage_audit.sqlite_path` 顯式指定例項本地的 SQLite 路徑，不要預設和共享 workspace 卷混用。

示例：

```json
{
  "server": {
    "temp_upload": {
      "default_mode": "shared"
    }
  },
  "storage": {
    "vectordb": {
      "backend": "http",
      "url": "http://vector-db:5000"
    }
  }
}
```

這個示例使用遠端 HTTP 向量服務。請將 URL 替換為實際的向量服務地址，或配置 `volcengine`、`vikingdb` 後端。

如果你還需要為 QueueFS 和 usage audit 顯式指定本地 SQLite 路徑，可以參考：

```json
{
  "server": {
    "temp_upload": {
      "default_mode": "shared"
    },
    "observability": {
      "usage_audit": {
        "sqlite_path": "/var/lib/openviking-local/usage_audit.sqlite3"
      }
    }
  },
  "storage": {
    "vectordb": {
      "backend": "http",
      "url": "http://vector-db:5000"
    },
    "agfs": {
      "queuefs": {
        "db_path": "/var/lib/openviking-local/queue.db"
      }
    }
  }
}
```

這個變體適用於多個例項共享同一個 `workspace`，但 QueueFS 和 usage audit 的 SQLite 檔案仍然放在各例項本地路徑的場景。

如需公網 HTTPS 訪問，請參考 [公網訪問指南](12-public-access.md)。

如需自行構建映象，請顯式傳入 OpenViking 版本：
`docker build --build-arg OPENVIKING_VERSION=0.3.12 -t openviking:latest .`

### Kubernetes + Helm

專案提供了 Helm chart，位於 `examples/k8s-helm/`：

```bash
helm install openviking ./examples/k8s-helm \
  --set openviking.config.embedding.dense.api_key="YOUR_API_KEY" \
  --set openviking.config.vlm.api_key="YOUR_API_KEY"
```

詳細的雲上部署指南（包括火山引擎 TOS + VikingDB + 方舟配置）請參考 [雲上部署指南](https://github.com/volcengine/OpenViking/blob/main/examples/cloud/GUIDE.md)。

## 健康檢查

| 端點 | 認證 | 用途 |
|------|------|------|
| `GET /health` | 否 | 存活探針 — 立即返回 `{"status": "ok"}` |
| `GET /ready` | 否 | 就緒探針 — 檢查 AGFS、VectorDB、APIKeyManager、Embedding、Ollama |

```bash
# 存活探針
curl http://localhost:1933/health

# 就緒探針
curl http://localhost:1933/ready
# {"status": "ready", "checks": {"agfs": "ok", "vectordb": "ok", "api_key_manager": "ok", "embedding": "ok", "ollama": "ok"}}
```

在 Kubernetes 中，使用 `/health` 作為存活探針，`/ready` 作為就緒探針。

## 相關文件

- [公網訪問與反向代理](12-public-access.md) - HTTPS、Caddy、nginx
- [認證](04-authentication.md) - API Key 設定
- [OAuth 接入指南](11-oauth.md) - 面向 MCP 客戶端的 OAuth 2.1
- [可觀測性與排障](05-observability.md) - 健康檢查、追蹤與排障
- [API 概覽](../api/01-overview.md) - 完整 API 參考
