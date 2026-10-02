# Business Data Platform 原生 OAuth 2.1（MCP 客戶端授權）實施方案

> **更新（Studio 遷移）**：本文件保留 Phase 1 的設計與術語作為歷史記錄。當前
> 預設授權 UI 已經從獨立的 `/console` (埠 8020) 遷移到主服務上的 Business Data Platform
> Studio（同源、掛載在 `/studio`）。要點：
>
> - `provider.authorize()` 預設 redirect 到 `/studio/oauth/consent?pending=<id>`
>   而不是 `/oauth/authorize/page`。consent SPA 跑在 Studio 自己的 tab 裡，
>   直接複用 `sessionStorage` 裡已有的 API Key 調
>   `POST /api/v1/auth/oauth-verify`（請求體改用 `pending_id` 取代
>   `display_code`，並通過新增的公開端點
>   `GET /api/v1/auth/oauth/pending/{pending_id}` 拿 client_name /
>   redirect_host / scopes 渲染 consent 卡片）。
> - 服務端 HTML 頁面 `/oauth/authorize/page` 退化為**跨裝置 fallback**：
>   顯示 6 字元 `display_code` + 引導文案，讓使用者在另一臺已登入 Studio 的裝置
>   開啟 `/studio/oauth/verify` 輸入碼完成授權。同裝置的 quick-authorize
>   面板（依賴 `sessionStorage.ov_console_api_key` 跨 tab 探測）已移除，
>   不再需要把 API Key 寫到 `localStorage`。
> - OTP push 流程（`POST /api/v1/auth/otp` 簽發、Studio 裡"OAuth client OTP"
>   區塊生成短期碼交給客戶端）從未接通消費端，已整體移除（後端端點 + 前端入口 +
>   `otp_ttl_seconds` 配置）。Studio 側邊欄底部的那個槽位改造成"OAuth 驗證"入口，
>   直接開啟跨裝置 `display_code` 驗證表單。
> - 舊的 `/console` 獨立服務（8020 + `openviking.console` Python 包 +
>   `python -m openviking.console.bootstrap`）已在 #2160 整體下線，本次遷移
>   是該 PR commit message 裡明確指向的 OAuth follow-up。Caddy 仍保留
>   `:1934 → openviking:1933` 的 legacy 單上游反代以相容舊書籤，公網 HTTPS
>   按 12-public-access 指南在 Caddyfile 裡 append `:443` domain block。
>
> 下文的 "Phase 1" 描述仍然刻畫了 device-flow 的核心思路（含已移除的 OTP push
> 端點，僅作歷史記錄）；新遷移在此之上把 UI 層從 `/console` 替換為 `/studio`，
> 並把 Studio consent 作為同裝置主路徑。

## Context

**問題**：Claude.ai / Claude Desktop / ChatGPT 等只接受 OAuth 2.1 的 MCP 客戶端，必須經由社群專案 [MCP-Key2OAuth](https://github.com/t0saki/MCP-Key2OAuth) 的 Cloudflare Workers 代理才能連線 Business Data Platform 的 `/mcp`。痛點：

1. **額外部署單元** — 自建 CF Worker + 2 個 KV namespace，運維成本高
2. **生態繫結** — `@cloudflare/workers-oauth-provider` + KV 強繫結 CF Workers，無法脫離 CF 生態
3. **體驗差與信任風險** — 使用者在瀏覽器手動貼上 API Key，且 Worker 部署方有解密 Key 的能力

**目標**：在 Business Data Platform 服務端原生實現 OAuth 2.1（MCP 子集），消除中間代理；保留 API Key 認證向後相容；提供順手的瀏覽器授權 UX。

**最終決策（與設計早期不同）**：

- **協議層用 `mcp.server.auth` SDK**（已在依賴中）。SDK 提供完整的 RFC 6749 / 7591 / 8414 實現：DCR、authorize 解析、token endpoint、metadata、PKCE S256 校驗、redirect_uri 校驗、錯誤碼格式化。
- **Token 用 opaque + SQLite，不用 JWT**。Access / refresh / auth_code / OTP 全部是 `secrets.token_urlsafe()` 隨機串，按 SHA-256 雜湊存表，每次校驗做一次 SQLite 查詢。**Business Data Platform 側零密碼學程式碼**。
- **不做 redirect_uri 白名單**，但 SDK 會強制 strict-equal 校驗防 code injection。
- **Phase 1 用 device-flow 風格的 OTP 流程**：authorize page **顯示** 6 字元碼，使用者在 console（已登入環境）**輸入** 該碼確認授權。比早期的"console 取碼、page 輸入"流程少一次 tab 切換，且符合 RFC 8628 的心理模型。

---

## 架構

```
┌─────────────────────────────────────────────────────────────────┐
│                    Business Data Platform 1933                              │
│                                                                 │
│  ┌────────────────────┐   ┌──────────────────────────┐          │
│  │ mcp.server.auth    │   │ openviking.server.oauth  │          │
│  │ (SDK, 協議層)      │   │ (適配 + 自定義路由)      │          │
│  ├────────────────────┤   ├──────────────────────────┤          │
│  │ /.well-known/      │   │ /.well-known/            │          │
│  │   oauth-auth-server│   │   oauth-protected-       │          │
│  │ /register (DCR)    │   │   resource (PRM 9728)    │          │
│  │ /authorize         │   │ /oauth/authorize/page    │          │
│  │ /token             │   │ /oauth/authorize/page/   │          │
│  │ /revoke            │   │   status (輪詢)          │          │
│  └─────────┬──────────┘   │ /api/v1/auth/oauth-      │          │
│            │              │   verify (確認入口)       │          │
│            │              │ /api/v1/auth/otp         │          │
│            │              │   (legacy push)           │          │
│            │              └──────────┬───────────────┘          │
│            │                          │                          │
│            ↓ load_access_token()     ↓ DELETE/INSERT            │
│  ┌────────────────────┐   ┌──────────────────────────┐          │
│  │ auth.py            │   │ workspace/oauth.db       │          │
│  │ resolve_identity   │   │  oauth_clients           │          │
│  │ 識別 ovat_ →       │   │  oauth_codes (otp+code)  │          │
│  │ provider 查找      │   │  oauth_refresh_tokens    │          │
│  │ → ResolvedIdentity │   │  oauth_access_tokens     │          │
│  └────────────────────┘   │  oauth_pending_authorizations       │
│                           │   (display_code, verified, ...)     │
│                           └──────────────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                                ↑ verify (Bearer)
┌─────────────────────────────────────────────────────────────────┐
│                    Business Data Platform Console 8020                      │
│  Settings → "Authorize an MCP client" 表單                      │
│   - 輸入 6 字元 display_code → 調 /console/api/v1/ov/auth/      │
│     oauth-verify (proxy → 1933 /api/v1/auth/oauth-verify)       │
│  瀏覽器 sessionStorage 存 API Key (key=ov_console_api_key)      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 設計要點

### 1. 認證模式

不引入新的 `AuthMode.OAUTH`。OAuth 疊加在現有 `AuthMode.API_KEY` 之上：當 `oauth.enabled = true` 時，`Authorization: Bearer <token>` 優先按 OAuth 處理：

- 若 token 以 `ovat_` 字首開頭 → 走 `provider.load_access_token()` 路徑，**fail-closed**（字首正確但查不到不會回退到 API Key 路徑）
- 否則 → 走現有 APIKeyManager 路徑，行為與改動前完全一致

`ResolvedIdentity` 新增 `from_oauth: bool` 標記位；`get_request_context` 對 OAuth 身份跳過 ROOT-tenant-headers 強校驗（claims 已釘死 account/user）。

### 2. Token 許可權範圍與撤銷

OAuth token = API Key 等效，能調任何當前使用者身份能調的 REST 端點（不僅 `/mcp`）。

- **不是許可權放大**：opaque token 都釘死 `(account_id, user_id, role)`
- **撤銷粒度**：以 `(account, user)` 為單位 — 刪除某 user 的 API Key 時一刀切撤銷該 user 名下所有 OAuth token，見 `OAuthStore.revoke_tokens()`
- Phase 2 計劃引入 OAuth scope 做更細收緊

### 3. Token 形態（全部 opaque）

| 型別 | 形態 | 字首 | TTL | 儲存 |
|---|---|---|---|---|
| access_token | `secrets.token_urlsafe(40)` | `ovat_` | 1h | SQLite (SHA-256 哈希) |
| refresh_token | `secrets.token_urlsafe(40)` | `ovrt_` | 30d | SQLite (SHA-256 哈希) |
| authorization_code | `secrets.token_urlsafe(40)` | `ovac_` | 5min | SQLite (SHA-256 哈希) |
| display_code (人類可讀) | 6 字元（去歧義字母+數字） | — | 10min | pending_authorizations |
| OTP（legacy push） | 同上 | — | 5min | oauth_codes |

字首是 fast-path discriminator（不參與鑑權決策）— 讓 `auth.py` 在每次請求只對 `ovat_` 開頭的 bearer 做 DB 查詢，普通 API Key 不受影響。

### 4. 公網 URL 解析（issuer / PRM resource / WWW-Authenticate / page 連結）

統一 4 級回退：

1. `OPENVIKING_PUBLIC_BASE_URL` 環境變數（最高優先順序，部署 override）
2. `oauth.issuer` 配置項
3. `X-Forwarded-Proto` + `X-Forwarded-Host`（反代場景）
4. 請求 scheme + `Host` 頭（直連）

非 localhost 部署強烈建議顯式設定 (1) 或 (2)，因為 SDK 強制 issuer 必須是 HTTPS（除 loopback）。

### 5. PKCE / redirect_uri / 錯誤格式

由 SDK 強制 S256，`plain` 拒絕；`code_verifier` 長度 43–128。SDK 在 `TokenHandler` 中驗證。`/authorize` 時 `OAuthClientMetadata.validate_redirect_uri` 做 strict-equal；`/token` 時再次比對（防 code injection）。RFC 6749 錯誤碼由 SDK 返回。

### 6. WWW-Authenticate 401 頭

`/mcp` 鑑權失敗時 `_IdentityASGIMiddleware` 注入：
```
WWW-Authenticate: Bearer resource_metadata="https://<host>/.well-known/oauth-protected-resource"
```
URL 走 §4 的 4 級回退。RFC 9728 客戶端發現入口。

---

## 端到端流程（device-flow / pull 模式）

```
1. 使用者輸入 https://my.ov/mcp 到 Claude.ai
2. Claude POST /mcp → 401 + WWW-Authenticate: Bearer resource_metadata="..."
3. Claude GET /.well-known/oauth-protected-resource     → 拿 issuer
4. Claude GET /.well-known/oauth-authorization-server   → 拿 endpoint        [SDK]
5. Claude POST /register {redirect_uris}                → 拿 client_id      [SDK]
6. Claude 瀏覽器跳到 /authorize → SDK 校驗 → 調 provider.authorize() →
   server 生成 display_code (e.g. "AB3X7K") + pending → 302 → 
   /oauth/authorize/page?pending=...                                          [SDK→OV]
7. Page 顯示大字 "AB3X7K" + 連結 https://my.ov/console，
   並啟動 JS 輪詢 /oauth/authorize/page/status?pending=...
8. 使用者切到 console (sessionStorage 已經在登入) → Settings →
   "Authorize an MCP client" 輸入 AB3X7K → 點 Authorize
9. Console JS POST /console/api/v1/ov/auth/oauth-verify {code, decision}
   ↓ proxy
   1933 POST /api/v1/auth/oauth-verify
   → server 找 pending by display_code → mark verified, 寫入 caller 身份
10. Page 下次輪詢命中 status=approved → response.redirect_url 含 auth_code
11. Page JS window.location.replace(redirect_url) → Claude 收到 ?code=...&state=...
12. Claude POST /token (PKCE) → ovat_ + ovrt_                                [SDK]
13. Claude POST /mcp (Authorization: Bearer ovat_...) → 通過                  [SDK→auth.py]
```

**同源加速（可選）**：第 7 步 page JS 檢測到 `sessionStorage.ov_console_api_key` 存在（即與 console 同域 + 已登入）時，顯示綠色 "Quick authorize" 面板。點選該按鈕等價於在 console 輸入碼 → 直接跳到第 10 步。**仍要點選確認**，不會自動一步跳轉。要讓同源生效，nginx 反代把 8020 與 1933 放到同一域名（`/console/...` → 8020，`/...` → 1933）。

---

## 模組清單

### 新增 / 改寫

| 檔案 | 用途 | 行數 |
|---|---|---|
| `openviking/server/oauth/storage.py` | SQLite 5 張表 + CRUD + GC + verify/find_pending_by_display_code | ~620 |
| `openviking/server/oauth/provider.py` | `OAuthAuthorizationServerProvider` Protocol 適配；子類化 SDK 的 `AuthorizationCode/RefreshToken/AccessToken` 嵌入 `(account, user, role)`；`authorize()` 自動生成 display_code | ~280 |
| `openviking/server/oauth/router.py` | PRM、authorize page (HTML+JS)、page/status 輪詢、`/api/v1/auth/oauth-verify` | ~440 |
| `openviking/server/oauth/otp.py` | `generate_otp`（cross-device display_code）/ `hash_secret`（stdlib） | ~30 |
| `openviking_cli/utils/config/oauth_config.py` | `OAuthConfig` pydantic | ~70 |

### 修改

| 檔案 | 改動 |
|---|---|
| `openviking/server/auth.py` | `_try_resolve_oauth_token`：識別 `ovat_` → `provider.load_access_token` → `ResolvedIdentity(from_oauth=True)` |
| `openviking/server/identity.py` | `ResolvedIdentity.from_oauth: bool` |
| `openviking/server/mcp_endpoint.py` | 401 注入 `WWW-Authenticate` 頭；`_scope_to_origin` 4 級回退含 env |
| `openviking/server/app.py` | lifespan 初始化 `OAuthStore` + GC 任務；`create_app` 用 `mcp.server.auth.routes.create_auth_routes()` 掛 SDK routes + 自定義 router；issuer 優先讀 `OPENVIKING_PUBLIC_BASE_URL` env |
| `openviking_cli/utils/config/open_viking_config.py` | 接入 `OAuthConfig` |
| `openviking/console/app.py` | 加 `POST /console/api/v1/ov/auth/otp` 和 `POST /console/api/v1/ov/auth/oauth-verify` 轉發路由 |
| `openviking/console/static/index.html` | Settings 面板加 "Authorize an MCP client" 表單（device flow 入口）和摺疊的 legacy "Get OTP" 入口 |
| `openviking/console/static/app.js` | 表單事件 handler；調 verify 端點；keydown=Enter 觸發授權 |

### 刪除（vs 早期 JWT 方案）

- `openviking/server/oauth/jwt.py`（手搓 HS256）
- `tests/server/oauth/test_jwt.py`

---

## 端點全表

| 端點 | 方法 | 由誰實現 | 鑑權 | 說明 |
|---|---|---|---|---|
| `/.well-known/oauth-authorization-server` | GET | SDK | 無 | RFC 8414 |
| `/.well-known/oauth-protected-resource` | GET | Business Data Platform | 無 | RFC 9728，列出 issuer 和 bearer_methods |
| `/register` | POST | SDK | 無 | DCR (RFC 7591)，SDK 生成 client_id/secret，調 `provider.register_client()` |
| `/authorize` | GET/POST | SDK → provider.authorize() | 無 | SDK 校驗 client + redirect_uri + PKCE，調 `provider.authorize()` 生成 display_code + pending_id；返回 302 → `/oauth/authorize/page?pending=...` |
| `/oauth/authorize/page` | GET | Business Data Platform | 無 | 顯示 display_code + console 連結 + 同源 quick-authorize 面板（如檢測到 sessionStorage 中的 API key）；JS 輪詢 status |
| `/oauth/authorize/page/status` | GET | Business Data Platform | 無 | 返回 `{status: pending\|approved\|expired, redirect_url?}`；status=approved 時原子簽發 auth_code 並刪除 pending |
| `/token` | POST | SDK | client auth | SDK 驗 PKCE / redirect_uri / client，調 `provider.exchange_authorization_code()` 或 `exchange_refresh_token()` |
| `/revoke` | POST | SDK | client auth | SDK 調 `provider.revoke_token()` |
| `POST /api/v1/auth/oauth-verify` | POST | Business Data Platform | 現有 API Key（`Depends(get_request_context)`） | 接受 `{pending_id 或 code, decision: approve\|deny}`；approve 時把 caller 身份寫入 pending；deny 時刪除 pending |

---

## 部署運維

### 啟動

| 服務 | 命令 | 預設埠 |
|---|---|---|
| 主服務（API + MCP + OAuth） | `openviking-server [--host --port --config --workers]` | 1933 |
| Web Console | `python -m openviking.console.bootstrap [--host --port --openviking-url --write-enabled]` | 8020 |

> Console 當前沒有 `openviking-console` entry point，只能 `python -m`。後續可加。

### 關鍵配置

| 項 | 何處 | 說明 |
|---|---|---|
| 儲存路徑 | `ov.conf:storage.workspace`（預設 `./data`） | `oauth.db` 落在 `<workspace>/oauth.db` |
| OAuth 啟用 | `ov.conf:oauth.enabled = true` | 預設 false，關閉時所有 OAuth 路徑不掛載 |
| Issuer URL | `OPENVIKING_PUBLIC_BASE_URL` env > `ov.conf:oauth.issuer` | 非 localhost 必須 HTTPS |
| TTL | `ov.conf:oauth.{access,refresh,auth_code,otp}_ttl_seconds` | 預設 1h / 30d / 5min / 5min |
| Console 上游 | `--openviking-url`（預設 `http://127.0.0.1:1933`） | 反代後改成 `http://127.0.0.1:1933` 即可 |

### nginx 反代模板（推薦部署形態，**未在倉庫**）

```nginx
server {
  listen 443 ssl;
  server_name my.ov;

  # 8020 console
  location /console {
    proxy_pass http://127.0.0.1:8020;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host  $host;
  }

  # 其他都走 1933 (REST + MCP + OAuth + .well-known)
  location / {
    proxy_pass http://127.0.0.1:1933;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host  $host;
  }
}
```

這種部署下 console 和 OAuth page 同源，page 的"quick-authorize"面板自動可用。後續可在 `deploy/` 下落一份正式模板。

---

## 實施進度

### ✅ M1 — 基礎設施
- `OAuthConfig` 接入 `OpenVikingConfig`（預設 disabled）
- `OAuthStore` 5 張表 + CRUD + 原子一次性消費 + revoke_tokens
- `oauth/otp.py` OTP 生成
- `app.py` lifespan 注入 store + provider + GC

### ✅ M2 — Bearer 路徑與 401 頭
- `auth.py` `_try_resolve_oauth_token` 識別 `ovat_` 字首走 OAuth 路徑
- `ResolvedIdentity.from_oauth` 標記位 + `get_request_context` 跳過 ROOT-tenant 強校驗
- `mcp_endpoint.py` 401 注入 `WWW-Authenticate` 頭（含 4 級 origin 回退）

### ✅ M3 — SDK 接入與完整流程
- `OpenVikingOAuthProvider`（8 個 Protocol 方法）
- 自定義 authorize HTML 頁 + display_code 顯示 + JS 輪詢
- `POST /api/v1/auth/oauth-verify`（device flow 確認入口）
- `POST /api/v1/auth/otp`（legacy push flow，**已移除**——從未接通消費端）
- `GET /.well-known/oauth-protected-resource`（RFC 9728）
- `app.py` 用 `create_auth_routes()` 掛 SDK 路由

### ✅ M4 — Console 集成
- console proxy 加 `oauth-verify` / `otp` 轉發
- Settings 加 "Authorize an MCP client" 表單（device flow）
- legacy "Get OTP" 摺疊在 details 內
- 同源 quick-authorize 面板（page JS 檢測 sessionStorage）

### ✅ M5 — `OPENVIKING_PUBLIC_BASE_URL` 環境變數
- 4 級 origin 回退在 `_public_origin` (router) 和 `_scope_to_origin` (mcp_endpoint) 共用
- SDK issuer 啟動時讀

### ⏳ Phase 1 剩餘
1. **Claude.ai / Claude Desktop / Cursor 端到端實測**（需要起 server，等 benchmark 跑完）
2. **`deploy/nginx.conf.example`** + 部署文件（同源 quick-authorize 的運維側條件）
3. **`openviking-console` entry point script**（讓 8020 啟動統一為 `openviking-console`）

### 🔜 Phase 2 / 3（不在本 PR 範圍）
- OAuth scope 機制（`mcp` / `fs.read` / `fs.write` / `admin`）
- GitHub / Google 第三方登入（`identity_links` 表）
- 郵件 OTP 投遞（SMTP 整合）
- `ov otp` Rust CLI 子命令

---

## 驗證

### 單元 / 整合測試
```bash
pytest tests/server/oauth/ -v   # 38 通過（含完整 device flow happy path）
pytest tests/server/test_auth.py tests/server/test_mcp_endpoint.py -v   # 迴歸
```

### 端到端 curl（device flow）
```bash
# 1. 註冊客戶端
curl -X POST -H "Content-Type: application/json" \
  -d '{"redirect_uris":["http://127.0.0.1:9999/cb"],"client_name":"test","token_endpoint_auth_method":"none"}' \
  http://127.0.0.1:1933/register

# 2. PKCE
VERIFIER=$(openssl rand -base64 64 | tr -d '=+/' | head -c 64)
CHALLENGE=$(printf "%s" "$VERIFIER" | openssl dgst -sha256 -binary | basenc --base64url | tr -d '=')

# 3. 瀏覽器: GET /authorize?... → 跳到 /oauth/authorize/page → 顯示 6 字元碼 e.g. "AB3X7K"

# 4. 使用者在 console 輸入 AB3X7K（或直接 curl）
curl -X POST -H "X-Api-Key: $ROOT_KEY" -H "Content-Type: application/json" \
  -d '{"code":"AB3X7K","decision":"approve"}' \
  http://127.0.0.1:1933/api/v1/auth/oauth-verify

# 5. Page 自動 302 回 redirect_uri，從中取 auth_code

# 6. 換 token
curl -X POST -d "grant_type=authorization_code&code=ovac_...&client_id=...&code_verifier=$VERIFIER&redirect_uri=..." \
  http://127.0.0.1:1933/token
# → {"access_token":"ovat_...","refresh_token":"ovrt_...","expires_in":3600}

# 7. 調 MCP
curl -X POST -H "Authorization: Bearer ovat_..." \
  http://127.0.0.1:1933/mcp -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

### 向後相容
- `oauth.enabled=false`（預設）：`auth.py` 中 `oauth_provider is None`，OAuth 分流被跳過；行為與改動前一致
- `oauth.enabled=true`：`Authorization: Bearer <api_key>`（無 `ovat_` 字首）仍走 APIKeyManager；現有客戶端無感知

---

## 關鍵檔案路徑速查

**新增**：
- `openviking/server/oauth/{provider,storage,router,otp,__init__}.py`
- `openviking_cli/utils/config/oauth_config.py`
- `tests/server/oauth/test_{storage,router,auth_integration,mcp_www_authenticate}.py`

**修改**：
- `openviking/server/auth.py`（`_try_resolve_oauth_token`）
- `openviking/server/mcp_endpoint.py`（`WWW-Authenticate` + `_scope_to_origin`）
- `openviking/server/identity.py`（`from_oauth` 字段）
- `openviking/server/app.py`（lifespan + `create_auth_routes` + env-aware issuer）
- `openviking_cli/utils/config/open_viking_config.py`（接入 `OAuthConfig`）
- `openviking/console/app.py`（proxy `/auth/otp`, `/auth/oauth-verify`）
- `openviking/console/static/{index.html,app.js}`（device flow 表單 + 同源 quick-authorize）

**複用**（不改）：
- `openviking/server/identity.py:AuthMode/Role/ResolvedIdentity`
- `openviking_cli/utils/config/storage_config.py:StorageConfig.workspace`
- `mcp.server.auth.*`（官方 SDK，無新依賴）

---

## 風險與已識別問題

| 風險 | 處理 |
|---|---|
| 反代後 `issuer` 派生錯（HTTPS 終結於代理） | `OPENVIKING_PUBLIC_BASE_URL` env 或 `oauth.issuer` 配置；非 localhost 部署強烈建議顯式設 |
| 同源 quick-authorize 是隱式確認 | 即使檢測到 sessionStorage，**仍需點選 "Authorize" 按鈕**才生效，不會一步跳轉 |
| display_code 暴力列舉 | 6 字元 × 32 字母表 = ~1B 組合；TTL 10min；pending 一次性消費；建議在反代層加每 IP 速率限制 |
| Refresh token 重放 | 實現：檢測重放→`store.revoke_tokens(account, user)` 一併撤銷該 user 名下所有 OAuth state |
| Token 許可權範圍 = 整個 REST API | 已與使用者確認 Phase 1 不限制；Phase 2 引入 scope 機制收緊 |
| API Key → 撤銷 OAuth token 的精度 | 當前粒度 `(account, user)`：刪 user 時調 `revoke_tokens` cascade；滿足需求 |
| Console 與 OAuth page 同源依賴反代 | 文件提供 nginx 模板；不反代時退化為"console 複製 OTP，page 輸入"流程仍可用 |
