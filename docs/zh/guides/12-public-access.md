# 公網訪問與反向代理

OpenViking 預設在 1933 埠對外提供 REST API、MCP、OAuth、`.well-known/*`
以及 Web Studio (`/studio`)。本指南講怎麼把它放到公網 HTTPS 域名後面。

> **為什麼需要 HTTPS**：OAuth 2.1 / MCP SDK 對非 localhost 的 issuer
> **強制要求 HTTPS** —— Claude.ai、Claude Desktop、ChatGPT、Cursor 等 OAuth
> MCP 客戶端沒有 TLS 拒絕連線，會報 "Issuer URL must be HTTPS"。
> 僅 API Key 鑑權的客戶端（含 Claude Code `--header` 直連）在 HTTP 下也能
> 工作，但生產環境仍建議上 TLS。

前提：有公網域名、80 + 443 埠可達、DNS 已指向。

## 先配置認證，再開放反向代理

釋出任何路由前都要配置認證，即使上游只監聽 `127.0.0.1`。反向代理會讓這個本地服務可從公網訪問。預設 `dev` 模式以 ROOT 身份接受請求；TLS 和 `OPENVIKING_PUBLIC_BASE_URL` 都不會增加身份認證。

使用 API Key 認證時，將下面的配置合併到 `ov.conf`，用金鑰替換佔位值，然後重啟服務：

```json
{
  "server": {
    "auth_mode": "api_key",
    "root_api_key": "<your-secret-root-key>"
  }
}
```

root key 僅用於管理操作，例如通過 [Admin API](04-authentication.md) 建立 account 和首個管理員。租戶資料 API 使用返回的 user/admin key。不要把 root key 放進公開的瀏覽器客戶端，也不要讓反向代理為所有請求自動附加 root key。後端埠應保持私有，讓客戶端通過預期的 HTTPS 入口訪問。

允許使用者接入前，在公網 URL 上驗證：

```bash
# 上述 API Key 配置下預期為 401，不能成功返回目錄列表。
curl -sS -o /dev/null -w '%{http_code}\n' \
  'https://ov.your-domain.com/api/v1/fs/ls?uri=viking://resources'

# 先將 OPENVIKING_API_KEY 設定為繫結租戶身份的 user/admin key。預期為 200。
curl -sS -o /dev/null -w '%{http_code}\n' \
  -H "X-API-Key: $OPENVIKING_API_KEY" \
  'https://ov.your-domain.com/api/v1/fs/ls?uri=viking://resources'

# health 刻意不要求認證；這裡的 200 不能證明訪問控制已生效。
curl -sS https://ov.your-domain.com/health
```

如果使用 OIDC 或可信身份閘道器，應遵循對應模式的 [認證要求](04-authentication.md)，並驗證未認證的資料請求會被拒絕。不要讓可自行填寫身份請求頭的呼叫者直接訪問 `trusted` 後端。

<a id="新增-https公網訪問"></a>

## 方式 A：用自帶 Caddy 自動簽發 Let's Encrypt 證書（推薦）

`docker compose up` 預設帶一個 Caddy 反代容器。給它追加一個域名塊即可讓
443 埠跑起來。

### 1. 建立 `.env`

```dotenv
OPENVIKING_PUBLIC_BASE_URL=https://ov.your-domain.com
OV_ACME_EMAIL=admin@your-domain.com   # 可選；推薦用於 Let's Encrypt
```

`OPENVIKING_PUBLIC_BASE_URL` 同時被 OpenViking 容器（釋出在 OAuth 後設資料和
`WWW-Authenticate` 頭中）和 Caddy（作為 HTTPS 站點地址）讀取。

### 2. 在 `Caddyfile` 追加域名塊

```caddyfile
{$OPENVIKING_PUBLIC_BASE_URL} {
    reverse_proxy openviking:{$OPENVIKING_SERVER_PORT:1933}
    # 繫結 ACME 註冊郵箱（可選）：
    # tls {$OV_ACME_EMAIL}
}
```

### 3. 取消 `docker-compose.yml` 中的 HTTPS 註釋

三處：

```yaml
# caddy.ports 裡取消註釋：
- "80:80"
- "443:443"

# caddy.volumes 裡取消註釋：
- caddy_data:/data
- caddy_config:/config

# 檔案末尾取消註釋：
volumes:
  caddy_data:
  caddy_config:
```

### 4. 啟動

```bash
docker compose up -d
```

首次 HTTPS 請求觸發 ACME 證書籤發，後續使用快取。Caddy 自動續期。

### 5. 驗證

```bash
curl https://ov.your-domain.com/health
# {"status": "ok"}

# OAuth 後設資料（如果 oauth.enabled = true）：
curl https://ov.your-domain.com/.well-known/oauth-authorization-server

# 瀏覽器訪問 Studio：
open https://ov.your-domain.com/studio
```

## 方式 B：用你自己的反向代理

已經有 nginx / Traefik / Envoy / Cloudflare 在做 TLS 終止時，直接把上游指向
OV 服務的 1933 埠。

### nginx

```nginx
server {
    listen 443 ssl http2;
    server_name ov.your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/ov.your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ov.your-domain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:1933;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host  $host;
    }
}

server {
    listen 80;
    server_name ov.your-domain.com;
    return 301 https://$host$request_uri;
}
```

### Caddy（宿主機執行，不走 compose）

```caddyfile
ov.your-domain.com {
    reverse_proxy 127.0.0.1:1933
}
```

### Cloudflare / CDN

CDN 源站指向 `http://your-server-ip:1933`。設定
`OPENVIKING_PUBLIC_BASE_URL=https://ov.your-domain.com` 讓服務端知道自己的
公網地址。確保 CDN 轉發 `Host`、`X-Forwarded-Proto`、`X-Forwarded-Host` 頭。

## 告訴服務端公網 URL

OAuth 後設資料、`WWW-Authenticate` 頭、資源 URL 都需要包含公網 origin。
解析順序（**優先順序從高到低**）：

1. `OPENVIKING_PUBLIC_BASE_URL` 環境變數
2. `ov.conf` 裡的 `oauth.issuer`
3. `X-Forwarded-Proto` + `X-Forwarded-Host` 請求頭
4. 請求的 `Host` 頭

在反代後面，務必顯式設定選項 1：

```bash
export OPENVIKING_PUBLIC_BASE_URL="https://ov.your-domain.com"
```

或者 `ov.conf`：

```jsonc
{
  "oauth": {
    "enabled": true,
    "issuer": "https://ov.your-domain.com"
  }
}
```

## 相容備註：`:1934` 單上游反代

`docker compose up` 預設在 1934 埠啟一個 Caddy 反代，單純 `reverse_proxy
openviking:1933`，**僅為相容已經書籤到 1934 的舊部署保留**。新部署直接連
1933 即可，沒有任何路由價值；不需要這個入口可以從 `docker-compose.yml` 註釋
掉 caddy 服務和 1934 埠對映。

## 相關文件

- [部署指南](03-deployment.md) — Docker、systemd、Kubernetes
- [OAuth 指南](11-oauth.md) — OAuth 2.1 配置與客戶端接入
- [認證](04-authentication.md) — API Key 管理
