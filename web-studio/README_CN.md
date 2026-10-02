# Business Data Platform Web Studio

[English](README.md) / 中文

Web Studio 是 Business Data Platform 的 React/Vite 前端工作臺，面向開發者使用。它是一個靜態單頁應用，用於資源管理、檢索、Bot 會話和運維診斷。

Web Studio 不內嵌 Business Data Platform 的儲存、索引、檢索、任務佇列或 VikingBot 執行時。它必須連線一個正在執行的 Business Data Platform Server。

## 執行契約

預設本地服務端地址：

```text
http://127.0.0.1:1933
```

會話介面依賴 Business Data Platform Server 代理出來的 VikingBot API：

```text
GET  /bot/v1/health
POST /bot/v1/chat
POST /bot/v1/chat/stream
POST /bot/v1/feedback
```

本地開發和部署時，都應使用 bot 支援啟動 Business Data Platform Server：

```bash
openviking-server --with-bot
```

不帶 `--with-bot` 時，資源、搜尋、任務、系統狀態等核心 API 仍可能可用，但 `/bot/v1/*` 會返回 `503`；sessions 頁面無法提供真實聊天能力。

## 快速開始

### 1. 啟動服務端

從倉庫根目錄開發：

```bash
uv pip install -e ".[bot,dev]"
openviking-server init
openviking-server doctor
openviking-server --with-bot
```

或使用已釋出包：

```bash
pip install "openviking[bot]"
openviking-server init
openviking-server doctor
openviking-server --with-bot
```

檢查 Web Studio 必需的服務端能力：

```bash
curl http://127.0.0.1:1933/health
curl http://127.0.0.1:1933/ready
curl http://127.0.0.1:1933/bot/v1/health
```

### 2. 啟動 Web Studio

本地開發、構建和測試請使用 Node.js 22.x，與 Studio 構建流程保持一致。

當前 Vitest/jsdom 組合在 Node.js 26 下可能出現 `localStorage` 測試錯誤。遇到該問題時，請切換到 Node.js 22.x，並在 `web-studio/` 目錄執行 `npm ci && npm test`。

```bash
cd web-studio
npm install
npm run dev
```

瀏覽器訪問：

```text
http://127.0.0.1:3000
```

如果要覆蓋初始服務端地址：

```bash
VITE_OV_BASE_URL=http://127.0.0.1:1933 npm run dev
```

連線彈窗仍可以在執行時覆蓋 server URL、API key、account ID 和 user ID。

## 連線與鑑權

業務程式碼應使用 `src/lib/ov-client` 下的適配層，而不是直接從 `src/gen/ov-client` 匯入。適配層集中處理 base URL、鑑權頭、telemetry 預設值和錯誤歸一化。

瀏覽器儲存：

| 值                      | 儲存             | 鍵名                    |
| ----------------------- | ---------------- | ----------------------- |
| API key                 | `sessionStorage` | `ov_console_api_key`    |
| Base URL、account、user | `localStorage`   | `ov_console_connection` |

請求適配層會注入：

- `X-API-Key`
- `X-OpenViking-Account`
- `X-OpenViking-User`

生產或多租戶部署應在 Business Data Platform Server 中配置真實的 `server.root_api_key` 或 user key，並在 Web Studio 中填寫匹配的連線資訊。

## 常用命令

| 命令                        | 用途                                            |
| --------------------------- | ----------------------------------------------- |
| `npm run dev`               | 啟動 Vite 開發伺服器，埠 3000。               |
| `npm run build`             | 構建靜態生產產物到 `dist/`。                    |
| `npm run preview`           | 本地預覽 `dist/` 構建產物。                     |
| `npm run lint`              | 運行當前業務程式碼範圍的 ESLint。                 |
| `npm run format`            | 用 Prettier 檢查格式。                          |
| `npm run check`             | 執行 Prettier 寫入和 ESLint 自動修復。          |
| `npm run test`              | 執行 Vitest。                                   |
| `npm run gen-server-client` | 從服務端 OpenAPI 重新生成 `src/gen/ov-client`。 |

## 生成的 OpenAPI Client

生成程式碼目錄：

```text
src/gen/ov-client
```

不要手動修改生成產物。需要從目標 Business Data Platform Server 版本重新生成：

```bash
openviking-server --with-bot
cd web-studio
npm run gen-server-client
```

當前生成指令碼讀取：

```text
http://127.0.0.1:1933/openapi.json
```

指令碼會格式化 OpenAPI 文件、整理 operation ID，並執行 `@hey-api/openapi-ts`。

## 專案結構

```text
src/routes/              TanStack Router 路由
src/routes/<page>/       頂層頁面模組
src/routes/<page>/-*     頁面私有元件、hooks、schemas 和工具函式
src/components/ui/       共享基礎 UI 元件
src/components/          共享業務元件
src/hooks/               共享 React hooks
src/lib/ov-client/       Business Data Platform client 執行時適配層
src/gen/ov-client/       OpenAPI 生成客戶端
src/i18n/locales/        en 和 zh-CN 翻譯資源
src/styles.css           全域樣式和設計 token
types/ov-server/         手工補充的服務端 typed result 子集
```

頁面私有實現應放在對應路由目錄下。新增或修改使用者可見文本時，應遵循 [Web Studio 國際化貢獻指南](./CONTRIBUTING_CN.md)。

## 部署

Web Studio 的部署產物是 `dist/` 靜態檔案。Business Data Platform Server 仍然是獨立執行依賴。

### 1. 啟動必需的服務端

生產或類生產環境示例：

```bash
openviking-server --host 0.0.0.0 --port 1933 --with-bot
```

生產環境應在 `ov.conf` 中配置 `server.root_api_key`。如果 Web Studio 和 Business Data Platform Server 不同源，需要把 Web Studio 的訪問源加入 `server.cors_origins`。

最小健康檢查：

```bash
curl https://ov-api.example.com/health
curl https://ov-api.example.com/ready
curl https://ov-api.example.com/bot/v1/health
```

`/bot/v1/health` 是 Web Studio 部署契約的一部分。只有 core server 健康但 bot proxy 不健康時，會話介面仍然不可用。

### 2. 構建靜態檔案

獨立前端域名部署：

```bash
cd web-studio
npm ci
VITE_OV_BASE_URL=https://ov-api.example.com npm run build
```

`VITE_OV_BASE_URL` 是瀏覽器中的初始 Business Data Platform API origin。使用者仍可以在連線彈窗中修改它。

### 3. 獨立 host 部署

示例 URL：

```text
https://web-studio.example.com/
```

最小 nginx 示例：

```nginx
server {
    listen 80;
    server_name web-studio.example.com;

    root /srv/web-studio/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

### 4. 同 host 根路徑部署

示例 URL：

```text
https://ov.example.com/
```

將 Business Data Platform API 路徑反向代理到 server，並把 Web Studio 釋出在 `/`：

```nginx
server {
    listen 80;
    server_name ov.example.com;

    root /srv/web-studio/dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:1933;
    }

    location /bot/ {
        proxy_pass http://127.0.0.1:1933;
    }

    location /health {
        proxy_pass http://127.0.0.1:1933;
    }

    location /ready {
        proxy_pass http://127.0.0.1:1933;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

構建命令：

```bash
VITE_OV_BASE_URL=https://ov.example.com npm run build
```

### 5. 同 host 子路徑部署

示例 URL：

```text
https://ov.example.com/web-studio/
```

這種佈局下，Web Studio 掛載在 `/web-studio/`，Business Data Platform API 仍保留在 host 根路徑：

```text
https://ov.example.com/api/*
https://ov.example.com/bot/*
https://ov.example.com/health
https://ov.example.com/ready
```

構建時同時傳入兩個值：

```bash
cd web-studio
npm ci
VITE_OV_BASE_URL=https://ov.example.com npm run build -- --base=/web-studio/
```

含義：

- `VITE_OV_BASE_URL=https://ov.example.com`：瀏覽器請求 API 的 origin。
- `--base=/web-studio/`：Vite 靜態資源 base 和 TanStack Router 掛載路徑。

把 `dist/` 釋出到：

```text
/srv/web-studio
```

nginx 示例：

```nginx
server {
    listen 80;
    server_name ov.example.com;

    root /srv;

    location = /web-studio {
        return 301 /web-studio/;
    }

    location /web-studio/ {
        try_files $uri $uri/ /web-studio/index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:1933;
    }

    location /bot/ {
        proxy_pass http://127.0.0.1:1933;
    }

    location /health {
        proxy_pass http://127.0.0.1:1933;
    }

    location /ready {
        proxy_pass http://127.0.0.1:1933;
    }
}
```

不要把 `VITE_OV_BASE_URL` 設定成 `https://ov.example.com/web-studio`。`/web-studio/` 只是前端掛載路徑；Business Data Platform API 請求仍應訪問 `https://ov.example.com/api/*` 和 `https://ov.example.com/bot/*`。

### 6. Docker 服務端依賴

官方 Business Data Platform 映象可以作為 API server 依賴：

```bash
# 推薦優先使用 ghcr.io；如果訪問有問題，可改用 openviking-cn-beijing.cr.volces.com/volcengine/openviking:latest
docker run -d \
  --name openviking \
  -p 1933:1933 \
  -p 8020:8020 \
  -v ~/.openviking:/app/.openviking \
  --restart unless-stopped \
  ghcr.io/volcengine/openviking:latest
```

官方映象預設會啟動 VikingBot。用於 Web Studio 會話頁時，不要傳 `--without-bot`，也不要設定 `OPENVIKING_WITH_BOT=0`。

Web Studio 靜態檔案仍需單獨構建和託管，除非你的部署映象或平臺顯式把 `web-studio/dist` 打包進去。

## 常見問題

### `/bot/v1/*` 返回 503

服務端沒有用 `--with-bot` 啟動，或者 VikingBot gateway 啟動失敗。安裝 bot 依賴後重啟：

```bash
uv pip install -e ".[bot,dev]"
openviking-server --with-bot
```

服務端日誌中應能看到 `Bot API proxy enabled`。

### 生成 client 時拉不到 OpenAPI

`npm run gen-server-client` 讀取 `http://127.0.0.1:1933/openapi.json`。先啟動本地 server，並確保這個 server 版本就是前端要適配的目標版本。

### 瀏覽器出現 CORS 錯誤

如果 Web Studio 和 Business Data Platform Server 不同源，需要在 `ov.conf` 的 `server.cors_origins` 中加入 Web Studio 的訪問源並重啟 server。同源部署時，反向代理 `/api/`、`/bot/`、`/health` 和 `/ready` 到 Business Data Platform Server。

### 連線彈窗反覆開啟

通常是 API key 缺失或無效、key 屬於另一個 server，或選擇的 account/user 與 key 的許可權範圍不匹配。先用相同 server URL 和 key 直接請求一個 API 驗證，再更新 Web Studio 連線設定。

## 相關文件

- [Web Studio 國際化貢獻指南](./CONTRIBUTING_CN.md)：翻譯歸屬、服務端動態文本和審查清單。
- [Business Data Platform server deployment](../docs/en/guides/03-deployment.md)：服務端部署說明。
- [VikingBot validation with Business Data Platform Server](../bot/docs/vikingbot-phase1-validation-with-openviking-server.md)：Bot proxy 驗證流程。
