---
description: 用 Docker Compose、Helm 或自建反向代理部署 OpenViking 閘道器，在 Studio 中管理閘道器並排查問題。
---

# OpenViking 閘道器部署與運維

本頁寫給負責執行 OpenViking 閘道器的人，內容包括部署閘道器，在 Studio 中管理上游、上下文配置和金鑰，保護資料，日常運維，以及排查問題。閘道器能做什麼、客戶端怎麼接入，見[OpenViking 閘道器](15-gateway.md)；整體架構見其中的[一張圖看懂架構](15-gateway.md#一張圖看懂架構)。

閘道器目前處於 Beta 階段，設定和介面可能隨版本調整，升級前請先閱讀釋出說明。

閘道器是獨立於 OpenViking Server 的程序，預設監聽 1935 埠。客戶端把模型請求發給閘道器；管理閘道器則在 Studio 中進行，Studio 由 OpenViking Server 提供，管理操作經 OpenViking Server 轉發給閘道器。兩者之間只走 HTTP：閘道器呼叫 OpenViking 的公開介面搜尋記憶、儲存對話和執行工具，OpenViking Server 則呼叫閘道器的管理介面。下圖是對外只開一個 HTTPS 地址時的請求路徑：

```text
                       客戶端
                         |
                         v
          反向代理 (https://ov.example.com)
             |                                  |
             | /v1/*                            | 其他路徑：
             | /api/v3/*                        | /studio、/api/v1、
             | /api/compatible/v1/*             | /mcp、/health 等
             | /gateway/uploads                 |
             v                                  v
      OpenViking 閘道器 :1935 <----- 管理 ---- OpenViking Server :1933
         |        |                                  ^
         |        +-------- 搜尋、儲存、工具 --------+
         v
      模型服務商 (上游)
```

## 環境要求

- **OpenViking Server 0.4.16 或更高版本，並執行在 API Key 模式**（`server.auth_mode: "api_key"`，同時配置 `root_api_key`）。閘道器用每個人自己的 OpenViking 金鑰，以這個人的身份訪問 OpenViking。dev 模式下任何金鑰都按 root 身份處理，而閘道器不接受 root 身份，所以一個閘道器金鑰也簽發不了。
- **閘道器本身**：在 Python 3.10 或更高版本上安裝 `openviking[gateway]` 可選依賴，或者使用官方 OpenViking Docker 映象，映象裡已經包含 `openviking-gateway` 命令。
- **用於 Studio 的帳號管理員金鑰。** 你在 Studio 中配置的內容，都屬於登入所用金鑰所在的帳號。root key 也能用，但它管理的是它解析到的那個帳號，所以優先使用帳號管理員的金鑰。
- **每位領取閘道器金鑰的人都要是同一帳號中的 OpenViking 使用者**，普通使用者和管理員都可以，root 不行。簽發時由 OpenViking Server 讀取這個使用者的 OpenViking 金鑰；如果它只儲存金鑰雜湊，就需要這個使用者自己提供金鑰。
- **模型服務商的 API Key。** 訂閱登入會被拒絕；Coding Plan 金鑰預設也會被拒絕，除非你明確允許。
- **單臺主機上的本地磁碟**，用於閘道器儲存（預設 `~/.openviking/gateway`）。不支援網路檔案系統，也不支援在多臺主機之間共享儲存。同一時間只執行一個閘道器例項；需要更多處理能力時增加工作程序，見[擴充](#擴充)。
- **加密金鑰和管理令牌**，見下一節。

## 加密金鑰和管理令牌

| 名稱 | 環境變數 | 誰需要 | 作用 |
| --- | --- | --- | --- |
| 加密金鑰 | `OPENVIKING_GATEWAY_ENCRYPTION_KEY` | 閘道器 | 加密閘道器儲存的全部資料：上游 API Key 和請求頭、繫結到閘道器金鑰的 OpenViking 金鑰、對話狀態和請求日誌。必須是 Fernet 金鑰，即 32 位元組隨機數的 URL 安全 base64 編碼。 |
| 管理令牌 | `OPENVIKING_GATEWAY_ADMIN_TOKEN` | 閘道器和 OpenViking Server | 你在 Studio 中操作時，OpenViking Server 用它向閘道器的管理介面證明身份。至少 32 個字元。 |

兩者各生成一次：

```bash
# 加密金鑰（格式與 cryptography 包中 Fernet.generate_key() 的輸出相同）
python3 -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())'

# 管理令牌
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

把它們放進金鑰管理系統或部署環境，不要寫進 `ov.conf`，也不要提交到程式碼倉庫。如果要從其他名稱的環境變數讀取，在 `gateway` 中設定 `encryption_key_env` 和 `admin_token_env`。

- **加密金鑰不能更換。** 閘道器不會重新加密已儲存的資料，換了金鑰就讀不出原來的內容。請把金鑰和閘道器儲存一起備份。金鑰丟失後，只能把 `storage_path` 指向一個空目錄，重新配置上游、上下文配置和金鑰。
- **管理令牌可以輪換。** 給兩個程序設定相同的新值，然後都重啟。它只保護管理介面，不加密任何資料。
- 缺少有效的加密金鑰或管理令牌時，閘道器在啟動階段就會退出。OpenViking Server 沒有管理令牌也能啟動，但 Studio 的 OpenViking 閘道器頁面會提示缺少管理令牌。

## 部署

### 部署方式

閘道器和 OpenViking 之間只走 HTTP，所以可以裝在同一臺機器、放在同一個 Pod，也可以分開部署。無論哪種形態，都要滿足[環境要求](#環境要求)：OpenViking 0.4.16 或更高版本並開啟 API Key 認證，閘道器儲存放在一臺主機的本地磁碟上，同一時間只執行一個閘道器例項，閘道器持有加密金鑰，兩個程序配置同一個管理令牌。負載均衡、故障轉移和限流交給接在閘道器後面的 LiteLLM 或 new-api。

| 形態 | 適合 | 怎麼部署 | 要留意 |
| --- | --- | --- | --- |
| 單機 | 個人試用 | 安裝 `openviking[gateway]`，執行 `openviking-gateway`，和 OpenViking 讀取同一份 `ov.conf`，步驟見[快速開始](15-gateway.md#快速開始)。 | 只在本機使用時可以不配反向代理。 |
| [Docker Compose](#docker-compose) | 小團隊、單臺伺服器 | 閘道器是單獨的容器，自帶的 Caddy 在 1934 埠按路徑分流。 | 閘道器埠不對映到主機；加密金鑰只傳給閘道器容器。 |
| [Helm](#helm) | Kubernetes | 閘道器作為 OpenViking Pod 裡的第二個容器，共用儲存卷和 `ov.conf`。 | 保持一個副本；Chart 不支援把閘道器拆成單獨的 Pod。 |
| [分開部署](#分開部署) | 閘道器和 OpenViking 在不同的機器或 Pod | 自己編寫 Deployment 或服務定義，兩邊的 `ov.conf` 放同一份 `gateway` 配置。 | 兩邊互相要能訪問；鏈路上傳輸使用者的 OpenViking 金鑰；網路延遲會佔用召回的等待時間。 |

兩個程序讀取同一個 `ov.conf` 中的 `gateway` 部分。OpenViking Server 用它找到閘道器，供 Studio 和資料刪除使用；閘道器則用到整個部分。這一部分有幾條規則：

- 閘道器讀取 `--config` 指定的檔案，沒有指定時讀取 `OPENVIKING_CONFIG_FILE`，再沒有就讀取 `~/.openviking/ov.conf`。與 OpenViking Server 不同，它不會回退到 `/etc/openviking/ov.conf`。
- 閘道器不展開 `$VAR` 或 `${VAR}` 佔位符。`gateway` 中請寫字面值，金鑰和令牌放在上面的環境變數裡。
- 未知的鍵會報錯。OpenViking Server 報告 `Unknown config field 'gateway.<name>'`，閘道器則拒絕啟動。
- 修改這一部分後，要重啟 OpenViking Server。

其中三個地址容易混淆：

| 設定 | 誰使用 | 常見取值 |
| --- | --- | --- |
| `url` | OpenViking Server，用來訪問閘道器的管理介面 | `http://127.0.0.1:1935`；Docker Compose 中為 `http://gateway:1935` |
| `openviking_url` | 閘道器，用來訪問 OpenViking Server | `http://127.0.0.1:1933`；Docker Compose 中為 `http://openviking:1933` |
| `public_url` | 客戶端。Studio 的接入說明顯示這個地址，OpenViking 工具也用它生成上傳連結。 | `https://ov.example.com` |

### 路由

讓 OpenViking Server 和閘道器共用同一個公網 HTTPS 地址，由反向代理按路徑分流：

| 路徑 | 轉發到 | 用途 |
| --- | --- | --- |
| `/v1/*` | 閘道器 | Anthropic Messages、Chat Completions、Responses 和模型列表 |
| `/api/v3/*` | 閘道器 | 方舟路徑（火山方舟和 BytePlus 方舟）下的 Chat Completions、Responses 和模型列表 |
| `/api/compatible/v1/*` | 閘道器 | 方舟的 Anthropic 相容路徑 |
| `/gateway/uploads` | 閘道器 | OpenViking 工具的一次性檔案上傳 |
| 其他所有路徑 | OpenViking Server | Studio、REST API、MCP、OAuth、`/health` |

按這種佈局，`public_url` 就填這個公網地址，例如 `https://ov.example.com`。Anthropic 客戶端直接使用這個地址，OpenAI 風格的客戶端在後面加上 `/v1`。

> **安全**：不要從公網入口轉發閘道器的 `/admin/*` 路徑，也不要直接暴露閘道器埠。閘道器的管理介面只認管理令牌，持有令牌就能管理任何帳號。Studio 經由 OpenViking Server 訪問管理介面，OpenViking Server 會確認你是帳號管理員，並把每次呼叫限制在你自己的帳號內。只轉發上面四組路徑，1933 和 1935 埠都留在代理後面，不對外開放。

不管用哪種代理，閘道器路徑都要按長時間的流式模型呼叫來配置：

- **關閉響應緩衝**，流式回覆才能邊生成邊送達客戶端。
- **請求體上限至少 32 MiB**（`max_body_bytes`）。帶工具輸出的長對話請求體很大，nginx 預設的 1 MB 會讓這些請求失敗。
- **讀超時至少 600 秒**（`upstream_timeout_seconds`）。
- **`/gateway/uploads` 的訪問日誌不記錄查詢字串**，因為裡面帶有一次性上傳令牌。閘道器本身不寫訪問日誌。

### Docker Compose

倉庫自帶的 `docker-compose.yml` 在 `gateway` profile 下定義了 `gateway` 服務。它與 OpenViking Server 使用同一個映象、同一個 `~/.openviking` 掛載和同一個 `ov.conf`。它的 1935 埠只在 Compose 網路內可達，客戶端通過自帶的 Caddy 訪問閘道器，Caddy 已經在 1934 埠把閘道器路徑轉發過去。

1. **把加密金鑰和管理令牌寫進 `.env`**，放在 `docker-compose.yml` 旁邊：

   ```dotenv
   OPENVIKING_GATEWAY_ENCRYPTION_KEY=<encryption-key>
   OPENVIKING_GATEWAY_ADMIN_TOKEN=<admin-token>
   ```

   Compose 把管理令牌傳給兩個容器，加密金鑰只傳給閘道器。其中任何一個為空，閘道器都會退出，Compose 則會不停地重啟它。

2. **把以下設定合併進 `~/.openviking/ov.conf`：**

   ```json
   {
     "server": {
       "auth_mode": "api_key",
       "root_api_key": "<root-key>"
     },
     "gateway": {
       "enabled": true,
       "host": "0.0.0.0",
       "url": "http://gateway:1935",
       "openviking_url": "http://openviking:1933",
       "public_url": "http://<your-host>:1934"
     }
   }
   ```

   客戶端還在訪問自帶 Caddy 的埠時，使用 `http://<your-host>:1934`；配好 HTTPS 地址之後改用它。`storage_path` 可以保持預設：在容器內它解析為 `/app/.openviking/gateway`，正好位於掛載卷中。

3. **帶上 profile 啟動：**

   ```bash
   docker compose --profile gateway up -d
   ```

   之後執行 `up` 時也要帶上 `--profile gateway`。修改 `ov.conf` 後，用 `docker compose --profile gateway restart openviking gateway` 重啟兩個容器。

4. **檢查路由。** 不帶金鑰的請求應該到達閘道器並被拒絕：

   ```bash
   curl -s http://127.0.0.1:1934/v1/models
   # {"detail":"Invalid or revoked OpenViking Gateway key"}
   ```

   然後開啟 Studio，確認“概覽”標籤頁顯示 OpenViking 已連線。啟動錯誤可以用 `docker compose logs gateway` 檢視。

如果閘道器啟動時 OpenViking Server 還沒有就緒，閘道器會先在不帶記憶的狀態下執行，直到下一次檢查 OpenViking，最多等 60 秒（`health_interval_seconds`）。這段時間裡發出的訊息不帶記憶直接發給模型。

**HTTPS。** 按[公網訪問與反向代理](12-public-access.md#新增-https公網訪問)中的方式 A 設定 `OPENVIKING_PUBLIC_BASE_URL`、開放 80 和 443 埠並新增 Caddy 卷，但 `Caddyfile` 中的域名塊改用下面這段，讓閘道器路徑轉發到閘道器：

```caddyfile
{$OPENVIKING_PUBLIC_BASE_URL} {
    @gateway path /v1/* /api/v3/* /api/compatible/v1/* /gateway/uploads
    handle @gateway {
        reverse_proxy gateway:1935 {
            flush_interval -1
        }
    }
    handle {
        reverse_proxy openviking:{$OPENVIKING_SERVER_PORT:1933}
    }
}
```

然後把 `gateway.public_url` 設為同一個地址，並寫成字面值（例如 `https://ov.example.com`），再重啟。

### Helm

Chart 把閘道器作為 OpenViking Pod 中的第二個容器執行，與 OpenViking 共用儲存卷和 `ov.conf`。

1. **建立 Secret。** 鍵名 `encryption-key` 和 `admin-token` 是固定的：

   ```bash
   kubectl create secret generic openviking-gateway \
     --from-literal=encryption-key="$(python3 -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')" \
     --from-literal=admin-token="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
   ```

2. **在 values 中啟用閘道器。** 下面的 NGINX Ingress 註解是針對流式響應和大請求的推薦配置，Chart 不會自動設定：

   ```yaml
   gateway:
     enabled: true
     existingSecret: openviking-gateway
     workers: 2

   config:
     server:
       auth_mode: api_key
       # 按 Chart README 的說明從 Secret 傳入 root_api_key。
     gateway:
       public_url: https://ov.example.com

   ingress:
     enabled: true
     className: nginx
     annotations:
       nginx.ingress.kubernetes.io/proxy-buffering: "off"
       nginx.ingress.kubernetes.io/proxy-request-buffering: "off"
       nginx.ingress.kubernetes.io/proxy-body-size: 32m
       nginx.ingress.kubernetes.io/proxy-read-timeout: "600"
       nginx.ingress.kubernetes.io/proxy-send-timeout: "600"
     hosts:
       - host: ov.example.com
         paths:
           - path: /
             pathType: Prefix
     tls:
       - secretName: ov-example-com-tls
         hosts:
           - ov.example.com
   ```

values 中的 `gateway.enabled` 為 true 時，Chart 會：

- 生成 `gateway` 部分的其餘設定：`enabled`、`host: 0.0.0.0`、`port`、`workers`、`url: http://127.0.0.1:<port>`、`openviking_url: http://127.0.0.1:<config.server.port>` 和 `storage_path: <persistence.mountPath>/gateway`。你在 `config.gateway` 下寫的值優先。`public_url` 就在那裡設定，並寫成字面值。
- 把管理令牌傳給兩個容器，把加密金鑰傳給閘道器容器。閘道器容器不接收 `extraEnv`。
- 在 Service 上新增 `gateway` 埠。啟用 Ingress 時，把 `/v1`、`/api/v3`、`/api/compatible/v1` 和 `/gateway/uploads` 路由到這個埠，並排在你自己的路徑之前。
- 為閘道器的 `/health` 新增就緒探針。`gateway.resources` 設定閘道器容器的資源請求和限制。

保持 `replicaCount: 1`。閘道器的儲存位於 ReadWriteOnce 捲上，只能由一臺主機使用；需要更多處理能力時，調大 `gateway.workers`。如何從 Secret 傳入 root key 和模型金鑰，見 [Chart README](https://github.com/volcengine/OpenViking/blob/main/deploy/helm/README.md)。

### 分開部署

閘道器和 OpenViking 執行在不同的機器或 Pod 上時，Chart 和 Compose 檔案不再適用，需要自己編寫部署定義。兩邊的 `ov.conf` 放同一份 `gateway` 配置，並注意以下幾點：

- **兩個方向的地址都要填。** 閘道器通過 `openviking_url` 訪問 OpenViking；OpenViking Server 通過 `url` 訪問閘道器，Studio 的管理操作和刪除使用者資料都經過這個地址。兩個地址都應該是內網地址，閘道器的 `host` 要監聽對方能訪問的網絡卡。
- **保護兩者之間的鏈路。** 閘道器呼叫 OpenViking 時帶著使用者自己的 OpenViking 金鑰，管理請求也帶著管理令牌，所以這段鏈路要走內網或 TLS。
- **留意延遲。** 每條新訊息的召回最多等上下文配置中的**超時時間**（預設 2 秒），閘道器到 OpenViking 的網路延遲也算在裡面。延遲較高時，召回更容易超時，訊息就不帶記憶發給模型。
- **注意版本匹配。** 兩邊分別升級時，先升級 OpenViking，再升級閘道器，見[升級](#升級)。

### 自建反向代理

nginx 與兩個程序在同一臺主機上時，把閘道器路徑寫在兜底的 location 之前：

```nginx
server {
    listen 443 ssl;
    http2 on;  # nginx < 1.25.1：刪掉這一行，改用 `listen 443 ssl http2;`
    server_name ov.example.com;

    ssl_certificate     /etc/letsencrypt/live/ov.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ov.example.com/privkey.pem;

    # 模型 API：流式回覆、很長的歷史、響應慢的模型。
    location ~ ^/(v1|api/v3|api/compatible/v1)/ {
        proxy_pass http://127.0.0.1:1935;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_request_buffering off;
        client_max_body_size 32m;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 一次性檔案上傳。查詢字串裡帶著上傳令牌。
    location = /gateway/uploads {
        proxy_pass http://127.0.0.1:1935;
        proxy_http_version 1.1;
        proxy_request_buffering off;
        client_max_body_size 32m;
        proxy_read_timeout 120s;
        access_log off;
    }

    # Studio、REST API、MCP 和其他所有路徑。
    location / {
        proxy_pass http://127.0.0.1:1933;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_read_timeout 300s;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host  $host;
    }
}
```

如果調大了 `max_body_bytes` 或 `upstream_timeout_seconds`，`client_max_body_size` 和各項超時也要一起調大。其他代理同樣按這四組路徑和[路由](#路由)一節列出的設定來配置。

### 擴充

- **工作程序。** `workers`（1–64；預設 1，Helm Chart 中為 2）決定主機上執行幾個閘道器程序。它們共用儲存檔案，每個程序還會在後臺儲存對話。
- **單臺主機。** 不支援在多臺主機上執行閘道器，也不支援網路檔案系統。使用 Helm 時保持一個副本。
- **變更傳播。** 吊銷金鑰或編輯上游後，其他工作程序大約 2 秒內跟上。
- **健康狀態按程序計算。** 每個工作程序獨立檢查 OpenViking，所以“概覽”標籤頁上的 OpenViking 狀態來自恰好響應這次查詢的那個程序。
- **沒有負載均衡和限流。** 每段對話固定在一個上游上，閘道器不會換一個上游重試，也不限流；服務商返回的 429 原樣傳給客戶端。需要負載均衡、故障轉移或配額時，在閘道器後面接 LiteLLM 或 new-api，再把它新增為上游。

## 在 Studio 中管理閘道器

在 OpenViking Server 上開啟 `/studio`，進入**連線設定**，把帳號管理員金鑰填入**管理員 API 金鑰**。側邊欄的“設定”分組裡隨即出現**OpenViking 閘道器**，只有帳號管理員和 root 能看到它。這些頁面上的所有內容都屬於該金鑰所在的帳號。頁面頂部顯示客戶端應該使用的閘道器地址，即 `public_url`；`public_url` 為空時顯示 `url`，“接入”標籤頁會提示客戶端可能連不上這個地址。

如果閘道器沒有配置好或者無法訪問，頁面會顯示一張設定卡片，指出要修改哪項配置，見 [Studio 顯示設定卡片](#studio-顯示設定卡片)。否則頁面有六個標籤頁：**概覽**、**上游**、**上下文配置**、**金鑰**、**請求日誌**和**接入**。初次設定就按這個順序：新增上游，建立上下文配置，簽發閘道器金鑰，最後按“接入”標籤頁的說明接入客戶端。

### 上游

上游是模型服務商的一個介面，只使用一種 API：Anthropic Messages、Chat Completions 或 Responses。閘道器不在它們之間做轉換，所以客戶端用到幾種 API，就要新增幾個上游，即使它們來自同一個服務商：Claude Code 用 Anthropic Messages，Codex CLI 用 Responses，大多數聊天應用和 SDK 用 Chat Completions。

各服務商提供的協議如下。在編輯頁選擇服務商後，會自動填入它的預設 Base URL：

| 服務商 | 協議 | 預設 Base URL |
| --- | --- | --- |
| 通用 | 三種都有 | 無，需要自己填寫 |
| Anthropic | Anthropic Messages | `https://api.anthropic.com` |
| OpenAI | Chat Completions、Responses | `https://api.openai.com/v1` |
| DeepSeek | 三種都有 | `https://api.deepseek.com`；Anthropic Messages 為 `https://api.deepseek.com/anthropic` |
| 火山方舟 | 三種都有 | `https://ark.cn-beijing.volces.com` |
| BytePlus 方舟（海外站） | 三種都有 | `https://ark.ap-southeast.bytepluses.com` |

上游編輯頁分為四部分。

**介面。**

- **服務商**決定可以選哪些協議，並讓閘道器適配各家服務商的差異。編輯頁只提供服務商支援的協議，見上表。列表裡沒有的服務商、LiteLLM 和 new-api 這類相容代理，以及 [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) 這類把訂閱帳號包裝成 API 的反向代理，都選*通用*（見[自定義上游](15-gateway.md#自定義上游)；用訂閱額度時是否合規請自行確認）。
  - *通用*、*Anthropic* 和 *OpenAI* 轉發請求的方式相同。
  - *DeepSeek*：請求帶工具時，DeepSeek 要求歷史裡之前每條回覆都帶著推理內容，而很多聊天應用不會把推理內容發回來。DeepSeek 上游預設開啟**補全推理內容回傳**（見下文“路由”），所以請求保持思考模式也能得到 OpenViking 工具。關閉這項設定後，只有請求關閉了思考模式（`"thinking": {"type": "disabled"}`）時才提供 OpenViking 工具；標準的 Responses 請求沒有 `thinking` 欄位，這時也得不到工具。記憶照常補充。
  - *火山方舟*和它的海外站 *BytePlus 方舟*行為相同：請求發往方舟自己的路徑。Chat Completions 和 Responses 的每段對話都使用一個固定的 `prompt_cache_key`，方舟的字首快取就能跟著對話走。如果請求的模型、思考模式、取樣引數、系統提示詞或工具與對話的第一個請求不同，就會被標記為**快取引數有變化**（`ark_cache_parameters_changed`），因為這些引數一變，方舟就會重新建立快取。
- **協議**決定上游能處理哪些客戶端請求，也決定閘道器如何傳送金鑰：Anthropic Messages 用 `x-api-key`，另外兩種用 `Authorization: Bearer`。
- **Base URL。** 選擇服務商後，編輯頁會填入上表中的預設地址。切換服務商或協議時，只有地址為空或仍是之前的預設地址，才會換成新的預設地址，自己填寫的地址不會被覆蓋；地址與預設地址不同時，點輸入框下方的**使用預設地址**即可恢復。閘道器把客戶端的請求路徑拼接在後面，並去掉重複的 `/v1`，所以 `https://api.openai.com/v1` 和 `https://api.anthropic.com` 都能用。編輯頁會顯示請求實際發往的地址。火山方舟和 BytePlus 方舟請填寫不帶路徑的地址，例如 `https://ark.cn-beijing.volces.com`，它適用於全部三種協議；以 `/api/v3` 結尾的地址只適用於 Chat Completions 和 Responses，以 `/api/compatible/v1` 結尾的只適用於 Anthropic Messages。API 路徑不以 `/v1` 結尾的服務商（例如 `…/api/paas/v4`）不能直接使用，需要在中間加一個 LiteLLM 之類的相容代理。

**憑證。**

- **API Key 由誰提供**：
  - **由閘道器保管 API Key**（預設）：閘道器傳送上游的 API Key，客戶端只需要閘道器金鑰。
  - **每個客戶端自帶 API Key**：每個請求除了閘道器金鑰，還要在 `X-OpenViking-Upstream-Key` 請求頭裡帶上客戶端自己的服務商 API Key。缺少這個請求頭的請求返回 401 "Upstream API key is missing"。閘道器按服務商慣用的請求頭把這個 API Key 傳過去，`X-OpenViking-*` 請求頭本身從不轉發。
- **API Key** 和**額外請求頭**只能寫入，不能讀回。編輯上游時，API Key 留空表示保留已儲存的值。額外請求頭只顯示名稱：值留空表示保留，刪除這一行表示刪除這個請求頭。已儲存的 API Key 無法清空；不想再用它時，改為“每個客戶端自帶 API Key”，或者刪除這個上游。
- **額外請求頭**會加到發往這個上游的每個請求上，例如服務商的版本或組織請求頭，並覆蓋客戶端傳送的同名請求頭。不允許設定 `Host`、`Content-Length`、`Transfer-Encoding` 和 `Connection`。
- **這是 Coding Plan 或訂閱金鑰。** 服務商通常只允許 Coding Plan 這類訂閱金鑰用在自家的程式設計工具裡，通過共享閘道器使用可能導致訂閱被封禁。勾選後，路由到這個上游的每個請求都會被拒絕，返回 403 "Coding Plan upstreams are disabled; configure a model API key"，除非同時勾選**仍然允許**。閘道器無法從金鑰本身分辨它是不是訂閱金鑰，需要你自己標記。Claude 訂閱令牌（`sk-ant-oat…`）始終會被拒絕。

**模型。**

- **模型**列出這個上游提供的模型名。留空表示接受任何名稱。只有列出的名稱和別名會出現在客戶端可以請求的模型列表（`/v1/models`）中。
- **模型別名**把客戶端使用的名稱對映為發給上游的模型，例如把 Claude Code 請求的 Claude 模型名對映到服務商提供的模型。別名會出現在模型列表中，請求日誌顯示的是客戶端使用的名稱。
- **上下文視窗**以 token 為單位記錄各個模型的上下文視窗（至少 1,024），鍵是經過別名對映、實際發給上游的模型名。長對話按這個視窗的比例觸發壓縮。沒有列在這裡的模型使用上下文配置的**預設上下文視窗**，那裡也沒有設定時按 1,000,000 token 計算，所以視窗更小的模型都要列出來，見[長對話](#長對話)。

**路由。**

- **優先順序。** 對每個請求，閘道器從金鑰繫結的已啟用上游中挑出使用這種 API、並且提供所請求模型的那些，再選優先順序最高的一個。只要原來的上游還能服務，對話就一直留在它開始時的上游上，所以修改優先順序隻影響新對話。
- **啟用。** 停用的上游不接收請求，也不出現在模型列表裡。原本使用它的對話會轉到下一個候選上游，這會造成一次服務商快取未命中，並丟掉之前的 Claude 思考塊；這些請求會被標記為**上游已切換**（`upstream_changed`）。想保留恢復的餘地，就用停用代替刪除。
- **允許 OpenViking 工具**決定能否通過這個上游提供 OpenViking 工具。關閉後立即生效，已經帶工具的對話也會受影響。
- **補全推理內容回傳。** 客戶端回傳歷史時，常常丟掉模型之前回復裡的推理內容。開啟後，閘道器記下經它轉發的每條回覆的推理內容，在後續請求裡放回原來的回覆上：Chat Completions 補回 `reasoning_content`，Anthropic Messages 把 thinking 塊放回原位，Responses 把帶明文內容的 reasoning 項放回對應條目之前。每輪補回的內容逐位元組相同，所以服務商的提示詞快取照常命中；補回的內容計入輸入 token。客戶端自己回傳了推理內容的回覆保持不變。DeepSeek、火山方舟和 BytePlus 方舟預設開啟，其他服務商預設關閉。DeepSeek 在帶工具的請求裡缺少推理內容會報錯，所以關閉後，DeepSeek 上游只在請求關閉思考模式時提供 OpenViking 工具。即使開啟，有些請求也補不回推理內容，這些請求同樣得不到工具：對話換了上游（`upstream_changed`）、Claude 對話丟了記憶記錄（`missing_injection_record`），或者客戶端把思考內容當作正文發回。
- **最小可快取長度**（僅火山方舟和 BytePlus 方舟）是模型能快取的最短提示詞長度，隻影響請求日誌如何報告快取資格。

其他上游設定都立即生效，對進行中的對話也一樣。閘道器沒有故障轉移：選中的上游出錯時，客戶端會收到這個錯誤；服務商無法訪問時返回 502 "Model upstream is unavailable"。

列表中的**測試**和編輯頁的**測試連線**會用上游的憑證和請求頭請求服務商的模型列表（`/v1/models`，火山方舟和 BytePlus 方舟為 `/api/v3/models`），最多等待 10 秒。測試通過說明主機可達，並且服務商接受這個 API Key。測試不檢查模型名，也不檢查 Coding Plan 設定。沒有模型列表介面、或者訪問這個介面需要額外請求頭的服務商，可能測試失敗而實際請求正常。“每個客戶端自帶 API Key”的上游無法測試。

有金鑰在使用的上游不能刪除；先吊銷這些金鑰，或者改為停用這個上游。

### 上下文配置

上下文配置是一組有名字的記憶設定。每個閘道器金鑰使用一份上下文配置，一份上下文配置可以供多個金鑰使用。比如可以準備一份“Coding”配置，召回記憶、資源和技能；再準備一份“Chat”配置，只召回記憶，預算也更小。

“上下文配置”標籤頁為每份配置顯示一張卡片，概括四個部分的設定和使用它的金鑰數。標籤頁還是空的時候，**使用推薦設定建立**一鍵建立一份名為“預設”的配置，**自定義**開啟編輯頁；之後用**新建配置**開啟編輯頁。有金鑰在使用的配置不能刪除；想做一份變體，用**複製一份**最快。

> **注意**：儲存的修改只對之後開始的對話生效。對話在第一個請求時記下金鑰當時的上下文配置並一直沿用，因為在對話中途改變模型看到的內容會破壞服務商快取。每次聊天都新開對話的客戶端很快就能用上新設定。Claude Code、Codex 以及傳送固定會話請求頭的客戶端會一直沿用舊設定，直到開始新對話，或者這段對話閒置滿 30 天（`session_ttl_days`）。

各部分都有自己的開關，長對話部分的兩項功能各有一個：

| 部分 | 作用 | 主要設定和預設值 |
| --- | --- | --- |
| 召回記憶 | 用每條新的使用者訊息搜尋 OpenViking，把相關內容附加到這條訊息上。 | 檢索範圍：記憶、資源、技能 · 單條訊息預算：1,600 token · 單個上下文視窗預算：30,000 token · 相關度閾值：0.35 · 超時時間：2 秒 |
| 儲存對話 | 把已完成的輪次寫入 OpenViking 會話並提交，供 OpenViking 提取記憶。 | 最新回覆等待時長：600 秒 · 提交閾值：20,000 token · 保留最近訊息：10 |
| 長對話 | 對話接近模型的上下文視窗時壓縮：由同一個模型寫摘要，用摘要替換之前的訊息。Agent 自管上下文視窗是實驗性的另一種方式。 | 壓縮：開啟 · 壓縮時機：上下文視窗的 0.9 · 摘要長度上限：8,000 token · Agent 自管上下文視窗：關閉 |
| OpenViking 工具 | 讓模型在回答時使用 OpenViking 的工具。支援 Chat Completions、完整歷史的 Responses 和 Anthropic Messages，新建的配置預設開啟。 | 預設勾選只讀工具，會修改資料的工具不勾選 |

召回設定的實際效果：

- **會話開頭提供使用者畫像**獨立於召回。啟用讀取工具後，還會提供記憶和技能目錄。**開頭內容預算**預設限制為 4,000 token，其中技能最多佔四分之一；設為 0 時全部省略。這些內容不佔召回預算。
- 召回採用 OpenViking 在指定預算內選取和排版的內容，也包括只提供 URI、供模型之後讀取的條目。

- 檢索文本是去掉客戶端噪聲後的使用者訊息，最多擷取**檢索文本長度**個字元（8,000）。少於 3 個字元的訊息不搜尋。
- 每條訊息最多補充**單條訊息預算**與**單個上下文視窗預算**剩餘額度中較小的那個；剩餘額度不足 64 token 時跳過搜尋。無論是閘道器還是客戶端壓縮了對話，單個上下文視窗預算都會重新計算。預算設為 0 就關閉了召回。這裡的 token 數是偏保守的估算，不是服務商的計費數。
- OpenViking 在**超時時間**內沒有返回時，這條訊息不帶記憶直接發給模型，之後也不會補上，客戶端重試也一樣。
- **按分類限量**（在“進階設定”中）可以給事件、實體、偏好、經驗、資源和技能六個分類分別設定條數上限，只搜尋上限大於 0 的分類。關閉時，所有來源放在一起排序。

**召回摘要。** 開啟**顯示召回摘要**（預設關閉）後，每條新使用者訊息的回覆都以一段簡短的摘要開頭，說明閘道器給這條訊息補充了什麼：

```text
> OpenViking context: user profile, memory index, skill list, earlier sessions
> OpenViking recall: 4 items (3 memories, 1 resource) — booking_duplicate_handling, user_lang_pref, +2 more
```

`context` 行只出現在對話的第一條回覆裡，並且只列出開頭實際提供的內容：使用者畫像、記憶目錄、技能目錄，以及這段對話較早部分在 OpenViking 中的儲存位置。`recall` 行按類別統計召回的條目數，並列出最多三個條目名。搜尋失敗時，這一行改為說明原因，例如 `> OpenViking recall failed: OpenViking unavailable`。沒有找到相關內容、召回已關閉或預算已用完時不顯示 `recall` 行，因此在第一條回覆之後，這樣的訊息沒有摘要。工具步驟等後續請求從不顯示摘要；客戶端重試同一條訊息時，摘要和第一次相同。在 Anthropic Messages 中，摘要單獨佔一個文本塊；在 Responses 中單獨佔一條助手訊息；在 Chat Completions 中是回覆文本的開頭。要求結構化輸出（JSON 格式）的請求，以及 `n` 大於 1 的 Chat Completions 請求，不顯示摘要。無論是否開啟 OpenViking 工具，這項設定都有效。模型看不到摘要：客戶端隨下一條訊息把回覆發回來時，閘道器會先刪掉摘要再轉發請求，也不會把它儲存到 OpenViking。和其他上下文配置一樣，改動隻影響新對話。

儲存設定的實際效果：

- 下一條使用者訊息到達時，上一輪就會儲存。**最新回覆等待時長**決定閘道器等多久之後把最後一輪也儲存下來並提交會話，這樣短對話也能被提交。
- **提交閾值**：會話中待提交的內容達到這麼多 token 時就提交一次。每次提交後，OpenViking 在後臺提取記憶。
- **保留最近訊息**：提交後，會話中保留最新的若干完整輪次，至少包含這麼多條訊息。
- 召回和儲存相互獨立：只儲存不召回、或者只召回不儲存的配置都有效。

[配置參考](#配置參考)列出了每項設定的 API 名稱和取值範圍。

### 閘道器金鑰

閘道器金鑰（`ovgw_…`）是客戶端用來代替服務商 API Key 的憑證。每個金鑰屬於一個 OpenViking 使用者，使用一份上下文配置和一組上游。

在“金鑰”標籤頁選擇**簽發金鑰**，然後填寫：

- **名稱**：方便日後辨認，例如“alice · Claude Code”。
- **OpenViking 使用者**：本帳號中的一個使用者或管理員。閘道器以這個使用者的身份搜尋和儲存記憶。簽發時，OpenViking Server 讀取這個使用者的 OpenViking 金鑰並交給閘道器，閘道器加密儲存；金鑰不經過瀏覽器，之後也不再顯示。如果 OpenViking Server 只儲存金鑰的雜湊（啟用了 `encryption.api_key_hashing.enabled`），或者因為其他原因讀不到某個使用者的金鑰，這個使用者在列表裡不可選。這時選擇**貼上 OpenViking 金鑰**，填入該使用者自己的金鑰。用 root key 登入 Studio 時沒有使用者列表可選：root key 解析到的帳號可能不是 Studio 當前顯示的帳號，所以要貼上使用者的金鑰。貼上的金鑰不能是 root key。
- **上下文配置**。
- **上游**：至少一個。這個金鑰只能訪問選中的上游。
- **允許的模型**（可選）：留空表示允許這些上游提供的所有模型。這裡填客戶端傳送的名稱，包括別名。請求其他模型會返回 403 "Model is not allowed by this key"，模型列表也只顯示允許的名稱。

簽發前，閘道器會向 OpenViking 核實這個使用者的 OpenViking 金鑰。如果貼上的是 root key、其他帳號的金鑰或無效的金鑰，或者 OpenViking 無法訪問，簽發就會失敗，見[簽發金鑰失敗](#簽發金鑰失敗)。

簽發成功後，**複製閘道器金鑰**對話方塊顯示完整金鑰。這是唯一一次顯示：閘道器只儲存金鑰的雜湊和開頭幾個字元。對話方塊裡還有 Claude Code、Codex CLI 和聊天客戶端的配置，已經填好真實金鑰和閘道器地址，可以直接貼上。金鑰丟了就重新簽發一個。

- **金鑰不能編輯。** 要更換金鑰的上下文配置、上游、允許的模型或 OpenViking 使用者，就簽發一個新金鑰，再吊銷舊的。
- **對話屬於使用者，不屬於金鑰。** 只要客戶端傳送相同的會話 ID，同一 OpenViking 使用者的新金鑰就會接著原來的對話，所以換金鑰不會打斷對話。
- **吊銷**會立即切斷客戶端的訪問（其他工作程序約 2 秒內跟上），正在進行的請求會正常完成。最後使用這個金鑰的對話裡還沒儲存的輪次會被丟棄，對話和記憶本身都保留。想換金鑰又不丟輪次，就先把客戶端切到新金鑰，再吊銷舊的。
- **OpenViking 金鑰變了怎麼辦。** 閘道器儲存的是簽發時這個使用者的 OpenViking 金鑰。如果該金鑰被重新生成或刪除，閘道器金鑰仍能通過客戶端認證，但記憶搜尋會失敗，儲存也會因 `openviking_http_401` 暫停。為該使用者重新簽發閘道器金鑰（Studio 會讀取新的 OpenViking 金鑰），切換客戶端，再吊銷舊的閘道器金鑰。
- **每人一個金鑰。** 使用同一個金鑰的人共享其 OpenViking 使用者的記憶。請給每人簽發一個金鑰；想讓不同客戶端使用不同的上下文配置，就按客戶端再分開簽發。

**刪除該使用者的閘道器資料…**（在金鑰的**更多操作**選單中）會弔銷該 OpenViking 使用者的所有閘道器金鑰，並刪除閘道器為該使用者儲存的對話狀態。OpenViking 中的會話和記憶不受影響，需要在 OpenViking 中刪除。在 OpenViking 中刪除使用者或帳號時，閘道器會自動做同樣的清理，見[安全與資料](#安全與資料)。

### 請求日誌和概覽

**概覽**標籤頁彙總日誌保留期（預設 30 天）內最新的 10,000 條請求日誌：

- 第一個請求到達之前，顯示**快速開始**清單。
- **請求數**：模型請求的數量、最近一次請求的時間，以及這些請求用掉的輸出 token。
- **首次呼叫快取命中率**：每條新使用者訊息的第一次模型呼叫中，命中服務商提示詞快取的輸入 token 所佔的比例。這是判斷閘道器是否健康最重要的指標，應該接近不經過閘道器時服務商能達到的水平；明顯下降通常說明閘道器傳送的歷史和上一次請求對不上了，見[首次呼叫快取命中率下降](#首次呼叫快取命中率下降)。
- **輪內快取命中率**：同一輪裡後續呼叫的快取命中率，例如工具步驟和 OpenViking 工具的往返。這個值通常都很高。
- **召回的記憶條數**：補充到新訊息中的記憶條數，以及每次檢索 OpenViking 的平均耗時（只統計實際檢索了的訊息）。
- **OpenViking**：顯示已連線、異常或啟動中，附帶版本和認證模式，異常時還會給出原因。OpenViking 無法訪問期間，請求照常發給模型，只是不帶記憶。卡片中的**儲存對話**一欄還會統計正在重試或已暫停儲存的對話數。
- **降級請求**：每種異常出現的次數和說明，異常型別見[故障排查中的表格](#降級請求的異常)。
- **最近請求**，以及前往“請求日誌”標籤頁的連結。

**請求日誌**標籤頁按時間倒序列出最新的 1,000 條記錄，停留在第一頁時每 30 秒重新整理一次。可以按**全部**、**新訊息**、**工具步驟**或**異常**篩選，也可以按**請求型別**篩選，或者按模型、對話或金鑰搜尋。各列顯示型別、模型（客戶端傳送的名稱）、服務商返回的 HTTP 狀態、token（輸入、快取佔比、輸出）、**記憶**（`+3` 表示這次搜尋補充的條數，附帶搜尋耗時；`↺ 4` 表示之前 4 條訊息補充的記憶被原樣放回）、**儲存**狀態和**異常**。展開一行可以看到對話 ID、上游、金鑰、耗時、token 明細、記憶搜尋結果、上下文視窗（用了多少，以及是否壓縮或開啟了新視窗）、儲存狀態和下次重試時間、OpenViking 工具詳情；有異常的請求還會說明發生了什麼、該怎麼處理。

只有到達模型服務商的請求才會被記錄。閘道器先行拒絕的請求不會記錄，例如金鑰無效、模型不在金鑰的允許範圍內、沒有匹配的上游、請求體超過上限，這些情況下客戶端會直接收到錯誤。

| 型別 | 含義 | 記憶 |
| --- | --- | --- |
| 新訊息 | 最後一條是新使用者訊息的請求 | 搜尋一次，並放回之前的記憶；這一輪會被儲存 |
| 工具步驟 | 同一輪的延續，例如帶著工具結果繼續 | 放回之前的記憶；隨所在輪次一起儲存 |
| 輔助請求 | 生成標題、摘要、壓縮、建議和許可權檢查的請求 | 放回之前的記憶；從不儲存 |
| 子 Agent | 客戶端的子 Agent 發出的請求 | 放回之前的記憶；從不儲存 |
| Token 計數 | token 計數請求（`/v1/messages/count_tokens`） | 放回之前的記憶，計數才和實際傳送的內容一致 |
| 直接轉發 | 不做改動、不帶記憶直接轉發的請求：其他介面、依賴服務商端狀態的 Responses 請求、壓縮過或無法解析的請求體 | 無 |
| 記憶同步 | 後臺儲存事件，不是模型請求 | — |

**儲存**列顯示每段對話的儲存狀態：

- **正常**：儲存正常進行。
- **已關閉**：這段對話的上下文配置不儲存對話。
- **重試中**：OpenViking 拒絕了儲存，或者無法訪問。閘道器會在 10、20、40、80 秒後依次重試。
- **已暫停**：連續 5 次失敗。閘道器之後每 5 分鐘重試一次，直到成功。未儲存的輪次會一直保留，直到儲存成功或者對話過期。

展開的行會顯示原因，例如 OpenViking 拒絕了金鑰（`openviking_http_401`，即使用者的 OpenViking 金鑰已失效），或者 OpenViking 無法訪問（`openviking_unavailable`）。提示對話歷史有改動（`history_changed`）是正常的：客戶端編輯、重新生成或壓縮了對話，閘道器用當前歷史在新的 OpenViking 會話中繼續儲存。

展開行中的**重新同步對話…**會為這段對話新建一個 OpenViking 會話。使用者下次發訊息時，閘道器把對話的完整歷史寫進這個會話。已經儲存的內容留在舊會話裡，所以 OpenViking 可能會把部分記憶提取兩次。修復了原因但對話仍然暫停，或者想要一份乾淨的對話副本時，可以用它。下一條訊息到達之前，什麼都不會發生。重新同步需要記錄上顯示的那個金鑰；如果它已被吊銷，請選同一段對話裡更新的一條記錄。

## OpenViking 工具

開啟 OpenViking 工具後，模型可以在回答過程中使用 OpenViking 服務提供的工具，訪問範圍受該使用者的許可權限制。工具呼叫由閘道器執行，客戶端會持續收到回答，直到本次回覆結束。顯示的 token 用量包含期間所有模型呼叫。這項功能對各類客戶端意味著什麼、模型能用哪些工具、使用者在回覆裡看到什麼，見 OpenViking 閘道器指南中的[讓任意客戶端擁有 Agentic 記憶](15-gateway.md#讓任意客戶端擁有-agentic-記憶)；本節說明客戶端要求、設定和上限。

三種協議都支援流式和非流式請求：

| 協議 | 客戶端要求 |
| --- | --- |
| Chat Completions | 回傳完整 `messages` 歷史。 |
| Responses | 使用 `store: false` 和完整 `input` 歷史；下一輪迴傳本輪返回的全部 `output` 內容，包括 reasoning 和客戶端工具呼叫。帶 `previous_response_id`、`conversation` 或 `background` 的請求繼續普通轉發，不提供閘道器工具；`item_reference` 無法還原完整歷史。 |
| Anthropic Messages | 回傳完整 `messages` 歷史，保留 thinking/signature 塊。計數請求使用相同工具定義，但不執行工具。 |

模型在同一條回覆中同時呼叫 OpenViking 和客戶端工具時，閘道器會處理 OpenViking 呼叫，客戶端照常執行自己的工具並回傳結果。Responses 支援客戶端的 function 和 custom 工具，Anthropic Messages 支援客戶端的 tool_use 呼叫。

這項功能面向無法連線 OpenViking MCP 伺服器的聊天應用和 API 應用。支援 MCP 或有外掛的客戶端，例如 Claude Code 和 Codex，用 MCP 或外掛更合適，因為客戶端會在那裡顯示每次工具呼叫及其結果，並在呼叫前請求確認。

新建的上下文配置預設開啟 **OpenViking 工具**，“使用推薦設定建立”也一樣。**工具**清單來自你的 OpenViking 服務，預設只勾選只讀工具：`find`、`search`、`grep`、`glob`、`list`、`tree`、`read`、`list_watches`、`get_acl`、`list_users`、`list_groups` 和 `health`。會修改資料的工具預設不勾選：`remember`、`write`、`edit`、`add_resource`、`add_skill`、`forget`、`set_acl` 和 `cancel_watch`。比如想讓模型儲存記憶，就勾選 `remember`；想讓它匯入網頁或附件，就勾選 `add_resource`。已有的上下文配置保留原來的設定。還沒有閘道器金鑰時，先簽發一個金鑰再載入清單。OpenViking 後續新增的工具也會預設可用，已有對話仍沿用開始時的工具清單。

每個上游的**允許 OpenViking 工具**預設開啟。兩個開關都開啟後，新對話會獲得選中的工具，名稱加上 `openviking_` 字首，例如 `openviking_find`、`openviking_read`、`openviking_grep` 和 `openviking_glob`。Studio 中的說明介紹各個工具的用途；只有 OpenViking 提供了相應資訊時，頁面才顯示只讀標記。提供給模型的工具定義會隨對話中的每個請求傳送，OpenViking 的全部工具約佔 3,500 個輸入 token，所以取消勾選用不到的工具也能節省 token。

> **注意**：所有選中的工具都直接執行，不經過客戶端的許可權確認，包括寫入和刪除資料的工具。勾選會修改資料的工具之前，先確認可以接受這一點；給聊天應用用的上下文配置，建議不要勾選 `forget` 和 `set_acl`。呼叫提示用於說明已經發生的操作，不是許可權確認。

**工具呼叫提示。** 開啟**顯示工具呼叫**（預設開啟）時，閘道器每執行一次 OpenViking 工具呼叫，就在回覆中呼叫發生的位置加一行提示：

```text
> OpenViking find: "release date" — done
```

提示寫明工具名；能夠識別呼叫物件時，還會顯示：檢索的查詢詞，讀取、列出或寫入的 URI，或者正在匯入的檔案或技能。流式回覆中，呼叫一開始提示就會出現，所以匯入這類耗時的呼叫進行時，使用者也能看到閘道器在工作；非流式回覆會在最終訊息裡帶上同樣的提示。呼叫結束後再補上結果：`done` 表示完成，`failed` 表示呼叫返回了錯誤，`skipped` 表示閘道器拒絕了這次呼叫，沒有執行，例如工具輪數已達上限或 token 預算已經用完。每條提示單獨成段。在 Chat Completions 中，提示是回覆文本的一部分；在 Anthropic Messages 中，同一輪呼叫的提示放在同一個文本塊裡；在 Responses 中，同一輪呼叫的提示放在同一條助手訊息裡。模型看不到這些提示，它收到的是真實的呼叫和結果；閘道器也不會把提示儲存到 OpenViking。要隱藏提示，在上下文配置的 **OpenViking 工具**部分關閉**顯示工具呼叫**，回覆裡就只有模型自己的輸出。和其他工具設定一樣，改動隻影響新對話。

對話是否帶工具，由它第一個能用工具的請求決定（生成標題這類輔助請求不算），之後保持不變，所以修改上下文配置隻影響新對話。唯一的例外是關閉工具：模型還沒呼叫過閘道器工具時，客戶端出現了自己的 OpenViking 工具，例如 MCP 伺服器在第一輪之後才連上。請求沒有帶工具時，請求日誌的詳情會說明原因：

| 原因 | 說明 |
| --- | --- |
| `tools_require_full_history` | Responses 工具需要 `store: false` 和完整 input 歷史，不能使用 `item_reference`。 |
| `upstream_tools_disabled` | 上游關閉了**允許 OpenViking 工具**。 |
| `tools_multiple_choices` | 請求要求返回多個候選（`n` 大於 1）。 |
| `tools_structured_output` | 請求要求結構化輸出（`response_format`、`text.format` 或 `output_config.format`）。 |
| `tools_non_function` | Chat Completions 客戶端傳入了 function 以外型別的工具。 |
| `tools_forced_choice` | `tool_choice` 為 `required`，或者指定了某個工具。 |
| `deepseek_reasoning_history_required` | 上游的服務商是 DeepSeek，請求沒有關閉思考模式（`"thinking": {"type": "disabled"}`），而之前的回覆發到上游時會缺少推理內容：關閉了**補全推理內容回傳**，或者這個請求補不回推理內容，因為對話換了上游、丟了記憶記錄，或者思考內容被當作正文發回。標準的 Responses 請求沒有 `thinking` 欄位，按開啟思考模式處理。 |
| `tool_name_collision` | 客戶端已接入 OpenViking 工具，閘道器在這段對話剩下的部分不再提供自己的工具；模型已經呼叫過閘道器工具的分支除外。誤判同樣會持續整段對話，開新對話即可。滿足以下任一條件即算：MCP 服務名（`server_label`、`mcp_server_name`、`mcp_servers[].name`）含有單詞 `openviking`；以 OpenViking 工具名命名的工具名中也含這個單詞，如 `mcp__claude_ai_OpenViking__search`（連接器的 `authenticate` 工具不算），包括獨佔一行列出的延遲載入工具名；帶字首、以 OpenViking 工具名結尾的工具（如 `mcp__ov__read`）在定義中出現 `viking://`。此外，任一請求中客戶端工具與閘道器工具同名也算，因為上游會拒絕重名工具。 |
| `tools_unavailable` | 無法從 OpenViking 載入工具清單，也沒有之前載入成功的清單。連線恢復後請開始新對話。 |
| `tools_not_selected_at_session_start` | 上下文配置開啟了工具，但這段對話的工具列表是空的：配置裡沒有選中任何 OpenViking 工具，或者對話是在閘道器升級前開始的、當時沒拿到工具。開始新對話即可。 |

輔助請求、子 Agent 請求和檢測到 OpenViking 外掛的對話都不帶 OpenViking 工具。這類請求如果回傳了模型用過這些工具的歷史，閘道器仍會附上工具定義，讓這段歷史保持有效，但會拒絕新的 OpenViking 呼叫。客戶端自己的工具在每個請求裡都照常可用。

**匯入檔案和技能。** OpenViking 服務提供匯入工具、且配置中勾選了它們時即可使用。通過 URL 匯入不需要 shell 工具，本地檔案則需要以下上傳方式之一：

- **有 shell 工具**（名稱類似 bash、shell、exec_command、terminal 或 run_command 的客戶端工具）：匯入工具返回一個一次性上傳連結，模型再用客戶端自己的 shell 工具上傳檔案，這一步會經過客戶端的許可權確認。技能目錄會先打包成 zip。連結指向 `public_url` 加上 `/gateway/uploads`，所以 `public_url` 必須是客戶端能訪問的地址，代理也要把這個路徑轉發給閘道器。沒有設定 `public_url` 時，匯入會失敗並提示 "Set gateway.public_url for client uploads"。
- **有附件**：沒有 shell 工具時，模型可以匯入使用者訊息裡附帶的檔案，檔案可以是 base64 資料，也可以是附件文本，支援 Responses `input_file` 和 Anthropic `document.source` 內嵌的 `base64`、`text` 資料。Open WebUI 通常只發送提取出的文本，這些文本會作為文本檔案匯入。附件中的 URL 和服務商的檔案 ID 不會被抓取；匯入支援的遠端資源時，請使用匯入工具的 URL 引數。

上傳大小受 `max_body_bytes` 限制（預設 32 MiB）。

上下文配置中 **OpenViking 工具**部分的**進階設定**裡有以下上限：

| 設定 | API 名稱 | 預設值 | 範圍 | 達到上限時 |
| --- | --- | --- | --- | --- |
| 每次請求的工具輪數 | `tool_max_rounds` | 不限 | 1 及以上 | 拒絕後續的 OpenViking 呼叫，模型用已有結果和客戶端自己的工具繼續。 |
| 單次呼叫超時 | `tool_timeout_seconds` | 30 秒 | 最多 120 秒 | 這次呼叫向模型返回錯誤。 |
| 結果大小上限 | `tool_result_bytes` | 65,536 位元組 | 1,024–1,048,576 | 結果被截斷。 |
| 總時長 | `tool_total_seconds` | 不限 | 大於 0 秒 | 請求失敗，返回 504 "Hidden tool request timed out"。 |
| Token 預算 | `tool_total_tokens` | 不限 | 1,024 及以上 | 拒絕後續的 OpenViking 呼叫，模型用已有結果和客戶端自己的工具繼續。這不是計費上限，最終回答可能超出它。 |

輪數、總時長和 Token 預算預設都不限，和 Agent 自己的工具迴圈一樣：模型會一直使用 OpenViking 工具直到完成。流式請求中，使用者可以隨時中斷回覆，客戶端斷開後閘道器也會停止。非流式請求在客戶端斷開後仍會繼續執行，所以如果客戶端傳送非流式請求，請設定**總時長**。欄位留空即表示不限。這項預設值修改之前儲存的上下文配置仍保留原來的值（5 輪、120 秒、100,000 Token），清空這幾項即可取消限制。

Token 預算用於模型使用 OpenViking 工具時新增的呼叫、結果和後續生成內容，客戶端已有的對話、工具定義和圖片不計入。閘道器保留客戶端設定的回答長度上限（`max_tokens`、`max_completion_tokens` 或 `max_output_tokens`）。預算用完後，閘道器會拒絕之後的 OpenViking 呼叫，模型利用已有結果和客戶端自己的工具繼續回答。

單次工具呼叫失敗時，模型會收到錯誤結果，並可據此繼續回答。如果整個回答失敗，例如服務商拒絕了後續模型請求，或者 OpenViking 呼叫被拒絕後模型仍繼續呼叫，客戶端會收到錯誤，請求日誌中會顯示 **OpenViking 工具呼叫失敗**（`hidden_tool_loop_failed`）。流式 Responses 請求以 `response.failed` 事件結束；Chat Completions 和 Anthropic Messages 返回 `gateway_tool_error` 錯誤。

如果某個上游反覆失敗，可以關閉它的**允許 OpenViking 工具**。已使用過這些工具的 Claude 對話可能同時出現 **工具歷史無法繼續使用**（`hidden_tool_history_unavailable`）：之前的思考內容無法繼續使用，閘道器已將其去掉。可根據請求詳情中的工具停用原因恢復原設定，或開始一段新對話。重試的工具呼叫會複用第一次呼叫的結果，中斷的寫入操作不會自動重做。

## 長對話

模型的上下文視窗限制了一段對話能有多長。開啟**壓縮**（預設開啟）後，閘道器會在對話撐滿視窗之前，把較早的部分換成一份摘要。

**何時壓縮。** 每收到一條新的使用者訊息或一個工具步驟，閘道器都會估算上下文視窗用了多少：取服務商為這段對話上一次回覆報告的 token 用量，再加上之後新增訊息的估算值。沒有這份用量時（例如流式 Chat Completions 沒有設定 `stream_options.include_usage`），就估算整個請求。估算值達到**壓縮時機**（視窗的 0.9）時，閘道器開始壓縮。輔助請求、子 Agent 請求和 token 計數請求不會觸發壓縮。

上下文視窗取自上游**上下文視窗**中該模型的條目（按發給上游的模型名查詢），沒有時取上下文配置的**預設上下文視窗**。兩者都沒有，閘道器按 1,000,000 token 計算。視窗更小的模型請設定其中一項，否則還沒等到壓縮，服務商就會以對話過長為由拒絕請求。

**摘要怎麼生成。** 閘道器向同一個上游、同一個模型額外發一次非流式請求，客戶端的系統提示詞、工具和思考設定都保持不變，所以大部分內容能命中服務商的提示詞快取。純文本摘要無法遵守的設定會去掉：強制的工具選擇改為不呼叫工具，結構化輸出格式和停止序列也不保留。這個請求包含壓縮位置之前的對話，以及一條要求模型為自己寫摘要的指令。摘要要覆蓋：使用者的目標和最新請求的原文、關鍵決定和當前進度、檔案、路徑和識別符號、出過的錯誤和修正、未完成的事項，以及最近幾次工具結果裡的要點。之前的摘要會並進新摘要。摘要是純文本，最多**摘要長度上限**個 token（8,000）。思考內容也計入輸出上限，而有些模型（如 DeepSeek V4.1）即使請求裡沒有思考設定也會預設思考，所以閘道器總是在摘要長度上限之外再留 16,000 token 的輸出餘量；客戶端手動指定了思考預算時，改為加上這份預算。這次請求和其他請求一樣由服務商計費。

**之後模型收到什麼。** 壓縮位置取決於請求型別：

- 新的使用者訊息：壓縮位置就在這條訊息之前。模型收到 system 和 developer 訊息、作為一條使用者訊息的摘要，以及這條新訊息。
- 工具步驟：壓縮位置在最近一次工具結果之後，模型從摘要出發繼續完成任務。

摘要訊息開頭說明閘道器替換了對話較早的部分、這段內容不是使用者寫的，結尾附上這段對話開頭的閘道器說明和使用者畫像，所以壓縮後它們仍然保留。之後凡是重新發送這段歷史的請求，包括輔助請求和 token 計數請求，都會做同樣的替換；子 Agent 通常傳送自己單獨的歷史，不受影響。每次壓縮會讓服務商快取在壓縮位置失效一次，之後快取照常命中。

**壓縮位置之前的內容不保留原文**，最近幾輪也不例外。模型之前的回覆和其中的思考內容都依賴被替換掉的歷史，只保留其中一部分會破壞 Claude 的思考簽名。壓縮位置之後生成的內容照常傳送，思考內容也一樣。

**查詢被壓縮的內容。** 對話本身仍然儲存在 OpenViking 裡。開啟了**儲存對話**、並且這段對話提供了 `openviking_grep` 和 `openviking_read` 工具時，摘要後面會附上查詢方法：這段對話對應的 OpenViking 會話（`viking://user/<user_id>/sessions/<session_id>/`）、會話裡訊息的存放位置，以及檢索步驟：先用具體的關鍵詞 grep 會話，拿到行號，再讀取匹配位置前後的內容。如果壓縮發生在一輪對話中間，壓縮位置之前的部分會立即儲存到 OpenViking，模型在這一輪裡就能檢索到。

**壓縮失敗時。** 如果摘要請求失敗，或者回復裡呼叫了工具、內容為空、因長度上限被截斷，閘道器就改為傳送完整歷史，並且 60 秒內不會在這段對話裡再次嘗試。請求日誌中這條請求的詳情會顯示**壓縮失敗**及原因。如果摘要寫完後上下文仍達到**壓縮時機**，比如系統提示詞和工具本身就佔了視窗的大部分，閘道器會保留這份摘要，但同樣等 60 秒再嘗試壓縮，原因顯示為 `still_over_threshold`。

**不再使用 Working Memory。** 摘要由對話所用的模型生成，不再使用 OpenViking 的會話摘要。閘道器新建的 OpenViking 會話都關閉了 Working Memory：提交時仍會歸檔訊息，OpenViking 也照常提取記憶，只是不再生成會話摘要。

**記憶預算。** 每壓縮一次，**單個上下文視窗預算**就重新計算，壓縮位置之前補充過的記憶也可能再次補充。

**客戶端自己的壓縮。** 閘道器壓縮之後，客戶端仍會發送完整歷史，閘道器在每個請求裡把壓縮位置之前的部分替換掉。客戶端看到的用量很小，按 token 用量決定是否壓縮的客戶端很少再自己壓縮，所以特別長的會話最終可能超過 `max_body_bytes`。客戶端壓縮或編輯歷史後，閘道器把新歷史儲存到新的 OpenViking 會話；檢索工具可用時，新歷史開頭的閘道器說明會告訴模型之前的會話在哪裡。

請求日誌中每條請求的詳情會顯示上下文視窗用了多少、較早的歷史是否被替換，以及新生成摘要的大小和耗時。

### 實驗性：Agent 自管上下文視窗

開啟 **Agent 自管上下文視窗**（預設關閉）後，由模型自己決定何時開啟新的上下文視窗，並自己寫交接筆記，不必等閘道器生成摘要。這項設定只在能使用 [OpenViking 工具](#openviking-工具)的對話中生效，其他對話不受影響，壓縮照上文所述進行。開啟壓縮時，如果模型一直不開新視窗，壓縮仍會兜底。

模型會看到：

- 在 OpenViking 工具之外多出兩個工具。它們不在上下文配置的**工具**清單裡，只由這項設定控制。
  - `openviking_new_context(reason, notes, next_steps)`：開啟新視窗，`next_steps` 可省略。它必須在一輪裡單獨呼叫；和其他工具在同一輪呼叫時，這一輪的每個呼叫都返回錯誤，視窗不會重置。如果閘道器在本次請求裡已經在同一位置替換過上下文，比如剛壓縮過，它同樣返回錯誤。
  - `openviking_context_remaining()`：返回視窗序號、已用和剩餘 token 的估算值、本視窗內的使用者輪數、距使用者上一條訊息的時間，以及一句建議。
- 開頭的閘道器說明裡多一行，告訴模型它用這兩個工具自己管理上下文視窗。
- 每條新的使用者訊息之後，記憶塊末尾有一行狀態：`[context-status] window wN · ~X/Y tokens (P%) · T since your previous message`。
- 視窗用到**軟提醒時機**（0.7）和**硬提醒時機**（0.85）時，閘道器分別發出軟提醒和硬提醒。軟提醒每個視窗只發一次，要求模型做完當前這一步就開啟新視窗，並在交接筆記裡記下之後要用到的確切路徑、行號和取值。硬提醒要求模型立即開啟新視窗，此後每一步都會重複，直到模型開啟新視窗或壓縮接手。提醒附在新的使用者訊息上，工具步驟裡則附在工具結果上。

模型呼叫 `openviking_new_context` 後，閘道器把目前為止的對話換成一個視窗頭，模型在同一條回覆裡接著工作。視窗頭先說明這是模型開啟的第 N 個視窗、內容不是使用者寫的，然後依次是 reason、notes 和 next_steps、使用者最新一條訊息的原文、檢索之前視窗的方法（條件和壓縮時相同），以及這段對話開頭的閘道器說明。之後的請求會根據客戶端的歷史重建同一個視窗。重置之前的內容會立即儲存到 OpenViking，之後仍可檢索。reason 和 notes 只出現在視窗頭裡，不會儲存到 OpenViking。每次重置會讓服務商快取失效一次，但不需要摘要請求。

請求日誌中每條請求的詳情會顯示視窗序號、模型是否開啟了新視窗，以及收到了哪種提醒。效果取決於所用的模型，後續版本中的行為也可能調整。

## 安全與資料

**按使用者隔離。** 每個閘道器金鑰繫結一位 OpenViking 使用者。閘道器用這位使用者自己的 OpenViking 金鑰搜尋記憶、儲存對話和呼叫工具，所以許可權不會超出使用者本人；各使用者的對話狀態也互相隔離。會話和記憶的正本始終在 OpenViking，閘道器只儲存讓對話繼續所需的狀態。

**閘道器儲存什麼。** 閘道器在 `storage_path` 下儲存兩個 SQLite 資料庫：

- `management.sqlite3`：上游、上下文配置、閘道器金鑰、請求日誌，以及 Responses ID 到上游的對映。上游 API Key、請求頭的值，以及繫結到閘道器金鑰的 OpenViking 金鑰都加密儲存。閘道器金鑰本身只儲存雜湊和一段短字首。
- `kernel.sqlite3`：每段對話的狀態，包括補充到訊息中的記憶文本（原樣放回需要它）、OpenViking 工具的往返記錄、摘要，以及等待儲存的對話文本。

儲存的值都用加密金鑰加密。檔案只有執行閘道器的使用者能讀取。

**請求日誌包含什麼。** 只有後設資料：請求型別、模型、狀態、上游、對話 ID 的雜湊、token 數、記憶條數和耗時、儲存狀態和異常。從不包含訊息文本、召回的記憶、工具引數和結果，也不包含任何金鑰。閘道器不寫 HTTP 訪問日誌，錯誤資訊也從不回顯提交的值。

**服務商能看到什麼。** 每個上游都會收到完整的模型輸入，包括閘道器補充的記憶和 OpenViking 工具的結果。只新增你放心交出這些資料的服務商。

**保留期限。** 清理任務每小時執行一次：

| 資料 | 保留時長 | 設定 |
| --- | --- | --- |
| 對話狀態 | 最後一次使用後 30 天 | `session_ttl_days` |
| 請求日誌 | 30 天 | `log_retention_days` |
| Responses ID 對映 | 30 天 | `response_ttl_seconds` |
| OpenViking 中的會話和記憶 | 遵循 OpenViking 自己的規則 | — |

**刪除資料。**

- 在 Studio 中刪除某個使用者的閘道器資料（金鑰的**更多操作**選單 → **刪除該使用者的閘道器資料…**），或者用帳號管理員金鑰呼叫 OpenViking Server 的 `DELETE /api/v1/admin/gateway/users/{user_id}/data`。這會弔銷該使用者的閘道器金鑰，並刪除其對話狀態。請求日誌中的後設資料按保留期限自然過期。
- 在 OpenViking 中刪除使用者時，閘道器會自動執行同樣的操作。刪除帳號時，還會從閘道器中刪除這個帳號的上游、上下文配置、金鑰和請求日誌。如果當時閘道器無法訪問，OpenViking 會持續重試。不再使用閘道器時，把 `gateway.enabled` 設為 `false`，刪除操作就不會再等待閘道器。
- OpenViking 中的會話和記憶要通過 OpenViking 刪除，不經過閘道器。
- 在 OpenViking 中刪除一條記憶，不會抹掉已經補充進對話的副本：閘道器為了原樣放回，在對話狀態裡保留了補充過的記憶文本，直到對話過期。要立即清除，就刪除該使用者的閘道器資料。這會同時吊銷他的全部閘道器金鑰，之後要重新簽發。

**訪問控制。**

- 客戶端用閘道器金鑰認證，放在 `Authorization: Bearer` 或 `x-api-key` 中。金鑰可以隨時吊銷。
- 閘道器用每個使用者自己的 OpenViking 金鑰做記憶搜尋、儲存和工具呼叫，所以它能做的事不會超出這個使用者的許可權。
- 管理令牌只應由 OpenViking Server 持有，閘道器的 `/admin/*` 路徑必須保持私有（見[路由](#路由)）。Studio 使用者由 OpenViking Server 校驗：只有帳號管理員和 root 能訪問，並且只能管理自己的帳號。管理令牌則不受帳號限制，持有它就能管理所有帳號，所以閘道器埠不能對公網開放。
- 帳號管理員能為本帳號的任何使用者簽發閘道器金鑰（OpenViking 只儲存金鑰雜湊時，需要使用者本人提供金鑰）。拿到閘道器金鑰就能以該使用者的身份召回記憶、呼叫工具，所以簽發權實際上等於讀取本帳號所有使用者記憶的許可權，只交給可信的管理員。
- `/gateway/uploads` 不需要閘道器金鑰。每次上傳由 OpenViking 簽發的一次性令牌授權，閘道器只把它轉發到 OpenViking 的上傳介面。不要讓它的查詢字串出現在代理日誌裡。
- `X-OpenViking-*` 請求頭、客戶端憑證和 Cookie 從不轉發給上游。

**備份。** 備份 `storage_path`，包括兩個資料庫及其 `-wal` 和 `-shm` 檔案，並和加密金鑰放在一起。要得到一致的副本，先停止閘道器，或者使用 SQLite 的線上備份（`sqlite3 kernel.sqlite3 ".backup kernel.backup.sqlite3"`，`management.sqlite3` 同理）。各種丟失的後果如下：

- **丟失 `kernel.sqlite3`**：之前補充的記憶無法放回。每段進行中的對話會有一次服務商快取未命中，Claude 對話會丟失一次之前的思考內容（**記憶記錄缺失**，`missing_injection_record`），尚未儲存的輪次也會丟失。
- **丟失 `management.sqlite3`**：上游、上下文配置、金鑰和請求日誌全部丟失。需要重新配置，並簽發新金鑰。
- **丟失加密金鑰**：兩個資料庫都無法讀取，只能從空的 `storage_path` 重新開始。

## 日常運維

OpenViking 閘道器頁面只對帳號管理員和 root 開放。初次設定按“上游 → 上下文配置 → 簽發金鑰 → 接入”的順序進行，之後的日常工作集中在下面幾件事上。

- **盯住首次呼叫快取命中率。** “概覽”標籤頁上的**首次呼叫快取命中率**反映跨輪次的提示快取，應該接近不經過閘道器時服務商能達到的水平；**輪內快取命中率**覆蓋工具步驟，正常時很高。明顯下降時，見[首次呼叫快取命中率下降](#首次呼叫快取命中率下降)。
- **用請求日誌定位單個請求。** 按新訊息、工具步驟或異常篩選，展開一行就能看到召回結果、儲存狀態和 OpenViking 工具的停用原因，見[請求日誌和概覽](#請求日誌和概覽)。
- **設定對外地址。** 共享部署必須設定 `public_url`。不設定時，Studio 的接入說明顯示內部地址，OpenViking 工具的上傳連結也無法使用。
- **定期備份。** 備份閘道器儲存目錄和加密金鑰，方法和丟失的後果見[安全與資料](#安全與資料)中的“備份”。

### 升級

- OpenViking Server 的版本不能低於 `min_server_version`（0.4.16），否則記憶搜尋和儲存都會停止，也無法簽發金鑰。閘道器和 OpenViking 分開升級時，先升級 OpenViking，再升級閘道器。
- 升級前閱讀釋出說明。新版本的閘道器如果不能讀取舊的儲存格式，會在啟動時報 `Unsupported gateway schema`，見[閘道器無法啟動](#閘道器無法啟動)。

### 觀測

閘道器不匯出 Prometheus 之類的監控指標，也不寫 HTTP 訪問日誌。執行狀態通過 Studio 的“概覽”和“請求日誌”標籤頁，或者 OpenViking Server 上的管理 API（`/api/v1/admin/gateway/overview` 和 `logs`）檢視；程序是否存活可以用閘道器的 `/health` 檢查。

## 設計取捨

下表說明閘道器幾項關鍵設計的原因和代價，幫助你判斷它是否適合自己的場景：

| 設計 | 選擇及原因 | 代價 |
| --- | --- | --- |
| 接入位置 | 接在模型呼叫路徑上，而不是給每個 Agent 安裝外掛：裝不了外掛的客戶端也能用，服務商金鑰集中管理。 | 看不到工作目錄，按專案隔離記憶要給每個專案使用不同的 OpenViking 使用者。 |
| 工具由誰執行 | 閘道器在回覆過程中代為執行 OpenViking 工具，並把工具往返存下來，下一輪原樣放回：沒有工具、不支援 MCP 的客戶端也能讓模型主動使用記憶。 | 沒有逐次確認；客戶端必須每輪迴傳完整歷史；需要管理員收緊工具清單和上限。 |
| 記憶放在哪 | 附加在最新的使用者訊息末尾，而不是系統提示詞裡：系統提示詞改動一個字，整份快取都會失效；附加在末尾並在之後原樣放回，字首就始終不變。 | 閘道器必須可靠地記下每處補充的原文，記錄丟失時快取會失效一次。 |
| 儲存時機 | 晚一輪儲存：下一條訊息帶回上一輪，才能確認使用者保留了它。 | 最後一輪要等**最新回覆等待時長**（預設 10 分鐘）之後才儲存。 |
| 長對話 | 由閘道器讓同一個模型寫摘要：只有閘道器知道模型實際收到了什麼，摘要請求也大部分命中快取。 | 觸發壓縮的那一輪多一次模型呼叫和一次計費；壓縮位置之前的原文不再發給模型。 |
| 本地狀態 | 單臺主機上的 SQLite，不引入 Postgres、Redis 這類依賴，適合在單臺主機上自部署。 | 閘道器不能多機互備，是模型呼叫路徑上的單點。 |
| 客戶端身份 | 閘道器簽發自己的金鑰，而不是直接使用 OpenViking 金鑰：可以單獨吊銷，同一個人的不同客戶端可以繫結不同的上下文配置。 | 閘道器要加密保管使用者的 OpenViking 金鑰；閘道器金鑰洩露，等於該使用者的記憶洩露。 |

## 配置參考

`ov.conf` 中的 `gateway` 部分，所有鍵都取預設值：

```jsonc
{
  "gateway": {
    "enabled": false,                                  // 設為 true 之前，閘道器拒絕啟動
    "host": "127.0.0.1",                               // 監聽地址
    "port": 1935,
    "workers": 1,                                      // 本機執行 1–64 個程序
    "url": "http://127.0.0.1:1935",                    // OpenViking Server 訪問閘道器的地址
    "openviking_url": "http://127.0.0.1:1933",         // 閘道器訪問 OpenViking Server 的地址
    "public_url": "",                                  // 客戶端訪問閘道器的地址
    "storage_path": "~/.openviking/gateway",   // 只能是本地磁碟
    "encryption_key_env": "OPENVIKING_GATEWAY_ENCRYPTION_KEY",
    "admin_token_env": "OPENVIKING_GATEWAY_ADMIN_TOKEN",
    "min_server_version": "0.4.16",
    "session_ttl_days": 30,
    "response_ttl_seconds": 2592000,
    "log_retention_days": 30,
    "max_body_bytes": 33554432,
    "upstream_timeout_seconds": 600,
    "health_interval_seconds": 60
  }
}
```

| 鍵 | 預設值 | 說明 |
| --- | --- | --- |
| `enabled` | `false` | 開啟閘道器。為 false 時閘道器拒絕啟動，Studio 的 OpenViking 閘道器頁面顯示設定卡片。 |
| `host` | `127.0.0.1` | 監聽地址。OpenViking 執行在 dev 模式時，必須是迴環地址。 |
| `port` | `1935` | 閘道器埠。 |
| `workers` | `1` | 本機上的閘道器程序數，1–64。 |
| `url` | `http://127.0.0.1:1935` | OpenViking Server 用來管理閘道器和刪除資料的地址。`public_url` 為空時，Studio 也顯示這個地址。 |
| `openviking_url` | `http://127.0.0.1:1933` | 閘道器訪問 OpenViking Server 的地址。 |
| `public_url` | 空 | 客戶端使用的地址。Studio 的接入說明顯示它，OpenViking 工具的上傳連結也用它。所有共享部署都應設定。 |
| `storage_path` | `~/.openviking/gateway` | 兩個資料庫所在的目錄，必須位於本地磁碟。 |
| `encryption_key_env` | `OPENVIKING_GATEWAY_ENCRYPTION_KEY` | 儲存加密金鑰的環境變數。 |
| `admin_token_env` | `OPENVIKING_GATEWAY_ADMIN_TOKEN` | 儲存管理令牌的環境變數。 |
| `min_server_version` | `0.4.16` | 閘道器支援的最低 OpenViking Server 版本。版本更低或無法解析時，記憶搜尋和儲存都會停止，也無法簽發金鑰。 |
| `session_ttl_days` | `30` | 對話閒置多少天后刪除它的狀態。 |
| `response_ttl_seconds` | `2592000` | Responses ID 到上游的對映保留多久（至少 60）。 |
| `log_retention_days` | `30` | 請求日誌的保留天數。 |
| `max_body_bytes` | `33554432` | 請求體和上傳的最大位元組數（至少 1,024）。超出時返回 413。 |
| `upstream_timeout_seconds` | `600` | 單次呼叫服務商的總時限。 |
| `health_interval_seconds` | `60` | 閘道器檢查 OpenViking 的間隔（至少 1）。 |

URL 類設定必須是普通的 `http` 或 `https` 地址，不能包含帳號密碼、查詢引數或片段；末尾的 `/` 會被去掉。

**環境變數：**

| 變數 | 讀取方 | 用途 |
| --- | --- | --- |
| `OPENVIKING_GATEWAY_ENCRYPTION_KEY` | 閘道器 | 加密金鑰（見[加密金鑰和管理令牌](#加密金鑰和管理令牌)）。 |
| `OPENVIKING_GATEWAY_ADMIN_TOKEN` | 閘道器和 OpenViking Server | 管理令牌，至少 32 個字元。 |
| `OPENVIKING_CONFIG_FILE` | 閘道器和 OpenViking Server | 沒有指定 `--config` 時使用的 `ov.conf` 路徑。 |

**上下文配置的設定。** 先列 Studio 中的名稱，再列管理 API 中的名稱（管理 API 把上下文配置稱為 `policies`）：

| Studio 名稱 | API 名稱 | 預設值 | 取值範圍 | 含義 |
| --- | --- | --- | --- | --- |
| 名稱 | `name` | `Default` | | 顯示名稱。 |
| 召回記憶 | `recall` | `true` | | 為每條新的使用者訊息搜尋記憶。 |
| 會話開頭提供使用者畫像 | `profile` | `true` | | 新對話開始時提供畫像，獨立於召回。 |
| 開頭內容預算 | `profile_max_tokens` | `4000` | 0–32,000 | 畫像和目錄的獨立預算；0 表示省略。目錄需要啟用讀取工具。 |
| 顯示召回摘要 | `show_recall` | `false` | | 在回覆開頭用一行說明 OpenViking 補充了什麼，或召回失敗的原因。模型看不到這一行。 |
| 檢索範圍 | `context_types` | `memory`、`resource`、`skill` | 至少一個 | 搜尋範圍：記憶、資源、技能。 |
| 單條訊息預算 | `max_tokens` | `1600` | 64–32,000 | 一條訊息最多補充的 token 數。 |
| 單個上下文視窗預算 | `session_max_tokens` | `30000` | ≥ 0 | 一個上下文視窗內最多補充的 token 數，每次壓縮後重新計算；0 表示關閉召回。 |
| 相關度閾值 | `score_threshold` | `0.35` | 0–1 | 接受的最低相關度分數。 |
| 超時時間 | `recall_timeout` | `2`（秒） | 最多 30 | 搜尋最多等待多久，超時後訊息不帶記憶繼續傳送。 |
| 檢索文本長度 | `query_max_chars` | `8000` | 3–32,000 | 用作檢索文本的訊息字元數。 |
| 按分類限量 | `quotas` | `{}`（關閉） | 鍵：`events`、`entities`、`preferences`、`experiences`、`resources`、`skills` | 每個分類最多取的條數；只搜尋大於 0 的分類。 |
| 儲存對話 | `capture` | `true` | | 把已完成的輪次儲存到 OpenViking。 |
| 最新回覆等待時長 | `idle_seconds` | `600`（秒） | ≥ 1 | 停頓多久之後儲存最後一輪並提交會話。 |
| 提交閾值 | `commit_tokens` | `20000` | ≥ 1 | 會話中待提交的 token 數達到這個值時提交。 |
| 保留最近訊息 | `keep_recent_messages` | `10` | 0–1,000 | 提交後會話中保留的訊息數。 |
| 壓縮 | `compaction` | `true` | | 接近上下文視窗時，用摘要替換對話較早的部分。 |
| 壓縮時機 | `compaction_threshold` | `0.9` | 0.5–0.98 | 上下文視窗用到多大比例時壓縮。 |
| 摘要長度上限 | `summary_max_tokens` | `8000` | 1,000–32,000 | 一份摘要最多多少 token。 |
| 預設上下文視窗 | `context_window` | 未設定（按 1,000,000 計算） | ≥ 1,024 | 上游沒有列出該模型時使用的視窗。 |
| Agent 自管上下文視窗 | `agent_windows` | `false` | | 實驗性。讓模型自己開啟新的上下文視窗；需要 OpenViking 工具。 |
| 軟提醒時機 | `window_soft_ratio` | `0.7` | 0.3–0.95，須低於 `window_hard_ratio` | 上下文視窗用到這個比例時，提醒模型儘快開啟新視窗。 |
| 硬提醒時機 | `window_hard_ratio` | `0.85` | 0.4–0.97 | 上下文視窗用到這個比例時，要求模型立即開啟新視窗。 |
| OpenViking 工具 | `gateway_tools` | `true` | | 為 Chat、完整歷史的 Responses 和 Anthropic Messages 提供 OpenViking 工具。 |
| 取消勾選的工具 | `disabled_tools` | 會修改資料的 8 個工具：`remember`、`write`、`edit`、`add_resource`、`add_skill`、`forget`、`set_acl` 和 `cancel_watch` | OpenViking 工具原名，不帶 `openviking_` | 新對話不提供這些工具，其餘可用工具都會提供，包括以後新增的。API 請求省略這個欄位時使用預設列表；列表為空且總開關開啟時，提供全部可用工具。 |
| 顯示工具呼叫 | `show_tool_calls` | `true` | | 每次 OpenViking 工具呼叫都在回覆里加一行提示。 |
| 每次請求的工具輪數 | `tool_max_rounds` | `null`（不限） | 1 及以上 | 見 [OpenViking 工具](#openviking-工具)。 |
| 單次呼叫超時 | `tool_timeout_seconds` | `30` | 最多 120 | |
| 結果大小上限 | `tool_result_bytes` | `65536` | 1,024–1,048,576 | |
| 總時長 | `tool_total_seconds` | `null`（不限） | 大於 0 | |
| Token 預算 | `tool_total_tokens` | `null`（不限） | 1,024 及以上 | |

**上游設定：**

| Studio 名稱 | API 名稱 | 預設值 | 含義 |
| --- | --- | --- | --- |
| 名稱 | `name` | | 顯示名稱。 |
| 協議 | `protocol` | | `anthropic`（Anthropic Messages）、`chat`（Chat Completions）或 `responses`（Responses）。 |
| 服務商 | `vendor` | `generic` | `generic`、`anthropic`、`openai`、`deepseek`、`ark`（火山方舟）或 `byteplus`（BytePlus 方舟）。Studio 只提供服務商支援的協議，API 接受任意組合。 |
| Base URL | `base_url` | | 服務商地址；各服務商的預設地址和路徑規則見[上游](#上游)。 |
| API Key 由誰提供 | `auth_mode` | `managed` | `managed`（由閘道器保管 API Key）或 `passthrough`（每個客戶端自帶 API Key）。 |
| API Key | `api_key` | | 只能寫入。編輯時留空表示保留已儲存的金鑰。 |
| 額外請求頭 | `headers` | `{}` | 值只能寫入，名稱可見。 |
| 模型 | `models` | `[]` | 提供的模型名；留空表示接受任何名稱。 |
| 模型別名 | `aliases` | `{}` | 客戶端使用的名稱 → 發給上游的模型。 |
| 上下文視窗 | `context_windows` | `{}` | 模型 → token 數，每項至少 1,024。 |
| 優先順序 | `priority` | `0` | 數值越大，新對話越優先使用。 |
| 啟用 | `enabled` | `true` | 停用的上游不接收請求。 |
| 允許 OpenViking 工具 | `allow_gateway_tools` | `true` | 能否通過這個上游提供 OpenViking 工具。 |
| 補全推理內容回傳 | `replay_reasoning` | `null`（跟隨服務商） | 把客戶端丟掉的推理內容補回之前的回覆。`null` 時 `deepseek`、`ark` 和 `byteplus` 開啟，其他服務商關閉；`true` 或 `false` 覆蓋服務商預設值。Studio 中開關與服務商預設值一致時儲存為 `null`。 |
| 這是 Coding Plan 或訂閱金鑰 | `coding_plan` | `false` | 除非另外允許，否則拒絕發往這個上游的請求。 |
| 仍然允許 | `allow_coding_plan` | `false` | 允許使用被標記為 Coding Plan 的金鑰。 |
| 最小可快取長度 | `cache_min_tokens` | `1024` | 僅火山方舟和 BytePlus 方舟；影響快取資格的報告。 |

**閘道器金鑰欄位：** 名稱（`name`）、OpenViking 金鑰（`openviking_key`）、上下文配置（`policy_id`）、上游（`upstream_ids`，至少一個）和允許的模型（`models`）。通過 OpenViking Server 簽發時，可以用本帳號使用者的 `user_id` 代替 `openviking_key`，由 OpenViking Server 讀取這個使用者的金鑰；兩者只能提供一個。

Studio 通過 OpenViking Server 上 `/api/v1/admin/gateway/` 下的管理 API 操作閘道器，資源包括 `overview`、`logs`、`guides`、`upstreams`、`policies`、`keys` 和 `users/{user_id}/data`。指令碼也可以用帳號管理員金鑰呼叫這些路徑。

## 故障排查

### 常見現象

| 現象 | 原因 | 處理 |
| --- | --- | --- |
| 某段對話沒有召回，也沒有儲存 | 檢測到 OpenViking 外掛，閘道器讓出了這段對話，召回、儲存和 OpenViking 工具都交給外掛。 | 正常行為，避免同一份內容補充兩次、儲存兩次，見[閘道器還是外掛](15-gateway.md#閘道器還是外掛)。 |
| 儲存顯示“重試中”，之後變成“已暫停” | OpenViking 拒絕儲存或無法訪問，常見原因是使用者的 OpenViking 金鑰被重新生成過。 | 修好原因後閘道器會自動恢復；金鑰失效時重新簽發閘道器金鑰，見[OpenViking 中看不到對話](#openviking-中看不到對話)。 |
| 上下文配置開啟了工具，對話裡卻沒有 | 還沒有能用工具的請求、第一個能用的請求載入 OpenViking 工具列表失敗、客戶端沒有回傳完整歷史，或者客戶端自己接了 OpenViking 工具。 | 在請求日誌裡檢視停用原因（見 [OpenViking 工具](#openviking-工具)）。客戶端接了 OpenViking MCP 伺服器時出現 `tool_name_collision` 屬於正常；其他原因修正後開始新對話。 |
| 請求不帶記憶 | OpenViking 無法訪問或超時、預算用完、沒有相關內容等。 | 見[沒有補充記憶](#沒有補充記憶)。 |
| 長對話被服務商以過長為由拒絕 | 閘道器不知道模型的實際視窗，壓縮得太晚。 | 見[長對話超出上下文長度](#長對話超出上下文長度)。 |

### 閘道器無法啟動

| 提示資訊 | 原因和處理 |
| --- | --- |
| `configure a Fernet encryption key and an admin token of at least 32 characters` | 閘道器的環境裡缺少加密金鑰或管理令牌，或者長度不夠。把兩者（見[加密金鑰和管理令牌](#加密金鑰和管理令牌)）載入到啟動閘道器的 shell、`.env` 或 Secret 中。 |
| `Set gateway.enabled=true in ov.conf` | 缺少這一部分、沒有開啟，或者閘道器讀到了別的檔案。閘道器依次讀取 `--config`、`OPENVIKING_CONFIG_FILE`、`~/.openviking/ov.conf`，不會讀取其他位置。 |
| `Missing OpenViking Gateway dependencies: …` | 安裝可選依賴：`pip install "openviking[gateway]"`。 |
| 某個 `gateway` 欄位的校驗錯誤 | 有未知的鍵、拼寫錯誤或無效的值。`${VAR}` 佔位符不會展開，所以寫在數字或 URL 欄位裡的佔位符同樣會報錯。 |
| `OpenViking Gateway must bind to loopback when OpenViking uses dev authentication` | OpenViking 執行在 dev 模式，而 `host` 不是迴環地址。把 OpenViking 切換到 API Key 模式。 |
| `Unsupported gateway schema; configure a fresh storage_path` | 儲存由不相容的閘道器版本寫入。把 `storage_path` 指向一個空目錄，重新設定閘道器。 |

在 Docker Compose 中，閘道器反覆重啟通常是因為 `.env` 裡的加密金鑰或管理令牌為空；`docker compose logs gateway` 會顯示具體資訊。

### Studio 顯示設定卡片

OpenViking Server 無法使用閘道器時，OpenViking 閘道器頁面會顯示一張設定卡片，而不是各個標籤頁：

- **OpenViking 閘道器未開啟**：OpenViking Server 的 `ov.conf` 中沒有 `gateway.enabled: true`。加上之後重啟 OpenViking Server。
- **缺少管理令牌**：OpenViking Server 的環境裡沒有管理令牌，或者它短於 32 個字元。設定好之後重啟 OpenViking Server；Docker Compose 通過 `.env` 設定，Helm 通過 `gateway.existingSecret` 設定。
- **OpenViking 連不上閘道器**：OpenViking Server 訪問不到 `gateway.url`。檢查閘道器是否在執行，以及 `url` 是否是 OpenViking Server 能訪問的地址，在 Docker Compose 中應為 `http://gateway:1935`（Helm 由 Chart 自動設定）。

如果兩個程序都在執行，頁面卻提示“金鑰被拒絕，請檢查連線設定”，而同一個管理員金鑰在**使用者與許可權**頁面能正常使用，就說明兩個程序的管理令牌不一致，閘道器返回的是 401 "Invalid gateway management credential"。給兩者設定相同的令牌，然後都重啟。

如果側邊欄裡沒有**OpenViking 閘道器**，說明 Studio 沒有管理員許可權：在**連線設定**中把帳號管理員或 root 的金鑰填入**管理員 API 金鑰**。OpenViking 執行在 dev 模式時，Studio 會隱藏管理頁面。

### 簽發金鑰失敗

**簽發閘道器金鑰**對話方塊會顯示簽發失敗的原因。括號裡的程式碼是管理 API 返回的原因值。

| Studio 中的提示 | 原因和處理 |
| --- | --- |
| 服務端讀不到這個使用者的 OpenViking 金鑰，請改為貼上。 | OpenViking Server 讀不到所選使用者的金鑰，通常是因為它只儲存金鑰的雜湊（`encryption.api_key_hashing.enabled`）。選擇**貼上 OpenViking 金鑰**，填入該使用者自己的金鑰。 |
| 這是 Root 金鑰。（`root_key_not_allowed`） | OpenViking 金鑰是 root key，或者 OpenViking 執行在 dev 模式，此時任何金鑰都按 root 身份處理。請使用使用者自己的金鑰，並啟用 API Key 模式。 |
| 這個 OpenViking 金鑰屬於其他帳號。 | 金鑰所屬的帳號不是你在 Studio 中管理的帳號。 |
| OpenViking 拒絕了這個金鑰。（`openviking_http_401`） | 金鑰不完整、已被重新生成，或者它的使用者已被刪除。請使用該使用者當前的金鑰。 |
| OpenViking 無法識別這個金鑰所屬的使用者（`openviking_identity_missing`） | OpenViking 沒有返回這個金鑰對應的使用者。請使用本帳號中某個使用者的金鑰。 |
| 閘道器連不上 OpenViking，無法校驗這個金鑰。（`openviking_unavailable`） | 閘道器訪問不到 `openviking_url`。 |
| OpenViking 版本低於閘道器的要求。（`openviking_version_mismatch`） | OpenViking Server 的版本低於 `min_server_version`（0.4.16），請升級。從原始碼倉庫安裝、沒有版本標籤的服務可能報告 `0.1.dev123` 這樣的開發版本號；請安裝正式版本，或者把 `min_server_version` 改成與之匹配的值。 |

### 客戶端收到閘道器返回的錯誤

這些拒絕都發生在請求到達服務商之前，所以不會出現在請求日誌裡。

| 狀態碼和提示 | 原因和處理 |
| --- | --- |
| 401 "Invalid or revoked OpenViking Gateway key" | 客戶端沒有傳送閘道器金鑰、傳送了已吊銷的金鑰，或者傳送的是服務商的 API Key。檢查客戶端實際傳送的是哪個金鑰。 |
| 403 "Claude subscription OAuth credentials are not supported" | 客戶端傳送了 Claude 訂閱令牌，例如 Claude Code 用訂閱帳號登入且沒有設定 `ANTHROPIC_AUTH_TOKEN`；或者上游儲存的就是訂閱令牌。請使用 API Key。 |
| 403 "Model is not allowed by this key" | 模型不在金鑰允許的範圍內。簽發一個允許這個模型的金鑰。 |
| 404 "No allowed upstream matches this protocol and model" | 金鑰繫結的已啟用上游中，沒有一個使用客戶端呼叫的 API 並提供所請求的模型。檢查上游的協議、模型和別名、是否啟用，以及金鑰綁定了哪些上游。 |
| 401 "Upstream API key is missing" | 上游要求每個客戶端在 `X-OpenViking-Upstream-Key` 中自帶 API Key，或者由閘道器保管 API Key 的上游沒有填寫。 |
| 403 "Coding Plan upstreams are disabled; configure a model API key" | 上游被標記為 Coding Plan 金鑰。請改用模型 API Key，或者有意勾選**仍然允許**。 |
| 404 "Unknown response for this key"、403 "Response upstream is no longer allowed" | 查詢的 Responses 響應不是這個金鑰建立的，或者它的上游已被停用、不再繫結到這個金鑰。 |
| 413 | 請求體超過了 `max_body_bytes`，或者超過了代理自己的上限。 |
| 426 | 對 Responses API 發起了 WebSocket 連線。這是預期行為，Codex 會改用 HTTP。 |
| 502 "Model upstream is unavailable" | 閘道器連不上服務商，或者呼叫超過了 `upstream_timeout_seconds`。在上游上執行**測試連線**。 |
| 503 "Dev authentication requires a loopback gateway" | OpenViking 執行在 dev 模式。把它切換到 API Key 模式。 |
| 504 "Hidden tool request timed out" | OpenViking 工具的往返超過了上下文配置中工具的**總時長**；未設定**總時長**時，是工具往返中的某次模型請求超過了 `upstream_timeout_seconds`。 |

### 沒有補充記憶

先在請求日誌裡找到這個請求。找不到，說明客戶端沒有經過閘道器，或者請求被閘道器拒絕了（見上一節）。找到了，就展開它檢視記憶搜尋結果：

- **沒有找到相關內容**（`empty`）：新使用者通常如此。只有對話被提交、OpenViking 提取之後才會有記憶。
- **召回已關閉或預算已用完**（`disabled`）：上下文配置關閉了召回，這段對話的預算已經用完，或者訊息短於 3 個字元。
- **OpenViking 無法訪問或響應超時**（`openviking_unavailable`）：檢視“概覽”標籤頁上的 OpenViking 卡片。如果 OpenViking 在執行但響應慢，可以考慮調長**超時時間**。
- **OpenViking 拒絕了這個金鑰**（`openviking_http_401`）：使用者的 OpenViking 金鑰已失效。用當前的 OpenViking 金鑰簽發新的閘道器金鑰。
- **OpenViking 版本低於閘道器的要求**（`openviking_version_mismatch`）：見[簽發金鑰失敗](#簽發金鑰失敗)。
- **檢測到 OpenViking 外掛**（`plugin_present`）：閘道器發現了 OpenViking 外掛，並讓出了這段對話。
- **型別不是新訊息**：工具步驟、輔助請求和子 Agent 請求從不搜尋，它們放回之前的訊息得到的記憶。

搜尋失敗的訊息之後也不會補上記憶；下一條訊息會重新搜尋。

### OpenViking 中看不到對話

- **儲存晚一輪。** 下一條訊息到達時，上一輪才會出現；最後一輪要等**最新回覆等待時長**過去（預設 10 分鐘）。
- **上下文配置不儲存對話。** 這時**儲存**列顯示“已關閉”。
- **儲存正在重試或已暫停。** 展開的行會顯示原因。修復原因（例如 OpenViking 金鑰失效）後，閘道器會在 5 分鐘內重試。如果對話一直暫停，使用**重新同步對話…**。
- **檢測到 OpenViking 外掛**（`plugin_present`）：閘道器不會為這段對話儲存任何內容。
- **你用其他使用者的身份檢視。** 會話屬於閘道器金鑰背後的 OpenViking 使用者，名稱為 `gateway-…`。
- **記憶比會話出現得晚。** OpenViking 只在提交之後才在後臺提取記憶。

### 首次呼叫快取命中率下降

先和不經過閘道器時服務商能達到的命中率比較，再檢視最近請求上標出的異常：

- **記憶記錄缺失**（`missing_injection_record`）：閘道器儲存丟失、從舊備份恢復，或者記錄已過期，之前補充的記憶無法放回。進行中的對話在一次未命中之後就會恢復。
- **上游已切換**（`upstream_changed`）：對話原來的上游被停用、沒有繫結到客戶端當前使用的金鑰，或者不再提供這個模型，於是對話轉到了另一個上游。
- **快取引數有變化**（`ark_cache_parameters_changed`）：在火山方舟或 BytePlus 方舟上，客戶端在同一段對話裡改變了模型、思考模式、取樣引數、系統提示詞或工具。
- 沒有標出異常：客戶端本身可能每輪都在改動之前的訊息或系統提示詞，例如插入當前時間，閘道器無法修正這種情況。每次壓縮、模型每次開啟新的上下文視窗，也都會造成一次未命中，這是預期內的。

### 長對話超出上下文長度

如果服務商以對話過長為由拒絕長對話的請求：

- **閘道器不知道模型的視窗大小。** 上游的**上下文視窗**裡沒有這個模型，上下文配置也沒有設定**預設上下文視窗**時，閘道器按 1,000,000 token 計算，對視窗更小的模型來說壓縮得太晚。請補上模型的視窗大小。
- **對話所用的上下文配置關閉了壓縮。** 修改配置只對新對話生效。
- **壓縮失敗。** 請求詳情會顯示原因，閘道器 60 秒後再次嘗試。如果摘要總因長度上限被截斷，就調大**摘要長度上限**。原因是 `still_over_threshold` 時，說明系統提示詞、工具和摘要本身就佔滿了大部分視窗：調小**摘要長度上限**，或者檢查模型的上下文視窗設定。

### 檔案匯入失敗

- "Set gateway.public_url for client uploads"：把 `public_url` 設為客戶端能訪問的地址。
- 上傳連結無法訪問，或者返回 404：在代理中把 `/gateway/uploads` 轉發給閘道器。
- 413：檔案超過了 `max_body_bytes` 或代理的上限。
- 502 "OpenViking upload is unavailable"：閘道器連不上 OpenViking Server。
- 沒有提供匯入工具：OpenViking 服務未提供該工具、上下文配置中取消了勾選，或當前請求無法使用閘道器工具。請檢查工具清單和請求詳情。

### 降級請求的異常

“請求日誌”和“概覽”標籤頁會標出閘道器沒能完整處理的請求。Studio 顯示異常名稱，括號裡的程式碼是管理 API 中對應的值：

| 異常 | 發生了什麼 | 怎麼處理 |
| --- | --- | --- |
| 記憶不可用（`memory_store_failure`） | 閘道器無法讀寫自己的儲存，或者該使用者的閘道器資料剛被刪除。請求不帶記憶發給了模型；對 Claude 來說，之前的思考內容被去掉了。 | 檢查磁碟空間、許可權和閘道器日誌。剛刪除過該使用者的閘道器資料時出現這一項是正常的。 |
| 原樣轉發（`unsafe_json`） | 請求中有無法精確重新編碼的數字或重複的鍵，所以閘道器逐位元組原樣轉發，沒有補充記憶。 | 通常只與某個客戶端有關，閘道器這邊無需調整。 |
| 上游已切換（`upstream_changed`） | 對話原來的上游無法再服務，轉到了另一個上游，造成一次快取未命中，之前的 Claude 思考內容也被去掉。 | 重新啟用這個上游，或者讓客戶端改用包含它的金鑰；也可以接受這次切換。 |
| 記憶記錄缺失（`missing_injection_record`） | Claude 對話中，之前補充的記憶已經沒有記錄，所以之前的思考內容被去掉了一次。 | 儲存丟失後，或者在很久以前的對話裡出現，都在預期之內。反覆出現時，開始一段新對話。 |
| 檢測到 OpenViking 外掛（`plugin_present`） | 檢測到了 OpenViking 外掛，這段對話不再使用閘道器記憶。 | 使用外掛時出現這一項是正常的。同一個客戶端在外掛和閘道器之間二選一。 |
| 快取引數有變化（`ark_cache_parameters_changed`） | 在火山方舟或 BytePlus 方舟上，影響快取的引數與對話的第一個請求不同，提示詞快取很可能沒有命中。 | 在同一段對話裡保持模型、思考模式、取樣引數、系統提示詞和工具不變。 |
| 工具歷史無法繼續使用（`hidden_tool_history_unavailable`） | Claude 對話曾使用 OpenViking 工具，但當前請求無法使用這些工具，之前的思考內容已被去掉。 | 檢視請求詳情中的工具停用原因，恢復原設定，或開始一段新對話。 |
| OpenViking 工具呼叫失敗（`hidden_tool_loop_failed`） | 模型使用 OpenViking 工具時未能完成回答，客戶端收到了錯誤。 | 見 [OpenViking 工具](#openviking-工具)。 |
| 回覆未儲存（`capture_parse_failure`） | 流式回覆無法解析，這條回覆沒有儲存。客戶端不受影響。 | 無需處理，僅供瞭解。 |
