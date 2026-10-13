# OAuth 2.1 接入指南

OpenViking 提供原生 OAuth 授權，供支援其發現、動態註冊和 PKCE 流程的客戶端接入，包括 Claude.ai、Claude Desktop、ChatGPT、Cursor 等 MCP 客戶端。協議端點（註冊、authorize、token、metadata）由官方 `mcp.server.auth` SDK 提供，非 MCP 的 OAuth 客戶端也可以走同一流程。使用者在 Studio 確認身份和授權，客戶端取得 access token 和 refresh token。API Key 認證仍可使用。

## 推薦配置

先按[認證指南](04-authentication.md)配置 API Key 模式，建立 account 和 user/admin key。OAuth consent 需要這個已註冊身份，開啟 OAuth 不會自動建立。下面的片段應合併到已有配置。

> **前提**：公網 HTTPS。OAuth 2.1（以及 MCP SDK）對非 localhost 的 issuer
> **強制要求 HTTPS**。請參閱[公網訪問指南](12-public-access.md)瞭解如何配置
> Caddy 或 nginx 的 HTTPS。

1. **配置 HTTPS** — 按[公網訪問指南](12-public-access.md)設定好
   `https://ov.your-domain.com`（Caddy + `.env` + `docker compose up`）。

2. **在 `~/.openviking/ov.conf` 啟用 OAuth：**

   ```json
   { "oauth": { "enabled": true } }
   ```

3. **重啟**（`docker compose restart openviking`）。

4. **接入客戶端。** Claude.ai → Connectors → Add → 輸入
   `https://ov.your-domain.com/mcp`。瀏覽器跳到
   `https://ov.your-domain.com/studio/oauth/consent`：如果尚未登入 Studio，
   先在彈出的"連線與身份"對話方塊裡粘入 API Key；然後在 consent 卡片上點
   **Authorize**。瀏覽器自動跳回 Claude.ai，連接器就位。

連線後，確認客戶端能發現工具並讀取有許可權的 URI。後續章節介紹本地聯調、token 行為和故障排查。

---

## 為什麼需要原生 OAuth

客戶端需要瀏覽器授權和 token 重新整理時，使用 OAuth。授權流程由服務端自己完成，客戶端和 API Key 之間沒有中間代理。首次登入 Studio 仍需已註冊的 user/admin API Key，後續授權可以複用 Studio 身份。

---

## 工作原理

OpenViking 授權 UI 預設走 **OpenViking Studio** 內的 consent 頁面（與主服務
同源、與 Studio 共用 session）。MCP 客戶端開啟瀏覽器授權時：

```
1.  MCP 客戶端  POST /mcp                                       → 401 + WWW-Authenticate
2.  MCP 客戶端  GET  /.well-known/oauth-protected-resource      (RFC 9728)
3.  MCP 客戶端  GET  /.well-known/oauth-authorization-server    (RFC 8414)
4.  MCP 客戶端  POST /register                                  動態客戶端註冊 (RFC 7591)
5.  MCP 客戶端  GET  /authorize?...                             (瀏覽器重定向)
6.  服務端     →    /studio/oauth/consent?pending=...
                    consent 頁載入，並 fetch /api/v1/auth/oauth/pending/<id>
                    渲染 client_name / redirect_host / scopes
7.  使用者      在 Studio 已登入的 tab 上點 Authorize（也可在 IdentityPicker
              裡臨時貼上另一個 API Key 完成一次性授權）
8.  Studio    POST /api/v1/auth/oauth-verify (Authorization: Bearer <api-key>,
              body: {pending_id, decision})，服務端把 pending 標記為 verified
              並繫結呼叫方的身份（account / user / role）
9.  Studio    輪詢 /oauth/authorize/page/status，命中 "approved"，
              自動跳轉回 MCP 客戶端的 redirect_uri 並附 auth code
10. MCP 客戶端 POST /token (PKCE S256)                          → access_token (ovat_...)
                                                                  + refresh_token (ovrt_...)
11. MCP 客戶端 POST /mcp (Authorization: Bearer ovat_...)        → 調工具
```

授權 consent 直接發生在 Studio 內，**不需要跨標籤複製驗證碼**。Studio 的
sessionStorage 裡已經持有 API Key（你登入 Studio 時填的那個），consent 頁用
它做 `Authorization: Bearer` 調 verify。

如果當前裝置打不開 Studio（例如 CLI MCP 客戶端、跨裝置授權場景），consent
頁底部的 "Use another device →" 連結會回退到服務端 HTML 授權頁
`/oauth/authorize/page`：頁面顯示 6 字元 `display_code`，讓你在另一臺已經
登入 Studio 的裝置上開啟 `/studio/oauth/verify` 輸入。

Studio 側邊欄底部的"**OAuth 驗證**"入口會直接開啟這個跨裝置驗證表單（桌面端
彈出對話方塊，移動端跳轉 `/studio/oauth/verify`），讓你在另一臺已登入的裝置上確認
授權，而不必先開啟授權頁。

---

## 快速驗證（HTTP，僅本地）

沿用上面的 API Key 模式和已註冊 user/admin key，不要用無認證 Dev 身份完成 consent。

最快確認 OAuth 裝配正確的方式是在 `127.0.0.1` 跑一遍。MCP SDK 接受
`http://127.0.0.1` 與 `http://localhost` 作為 issuer URL 而無需 HTTPS — 但
Claude.ai / Claude Desktop 等線上客戶端**只接受公網 HTTPS**，所以這個模式只
適合用 [MCP Inspector](https://github.com/modelcontextprotocol/inspector)
之類的本地工具做聯調。

1. **在 `~/.openviking/ov.conf` 啟用 OAuth：**

   ```json
   {
     "oauth": {
       "enabled": true
     }
   }
   ```

2. **啟動：**

   ```bash
   docker compose up -d
   ```

   或不用 Docker：

   ```bash
   openviking-server
   ```

3. **開啟 Studio 並登入**：訪問 <http://127.0.0.1:1933/studio>，在右上角
   開啟"連線與身份"對話方塊，把 API Key 粘進去 → Save。

4. **接一個本地 MCP 客戶端**（例如 MCP Inspector）到
   `http://127.0.0.1:1933/mcp`。客戶端會走上面那套流程，瀏覽器自動跳到
   `/studio/oauth/consent?pending=...`，確認即可拿到 token。如果想在另一臺
   已登入的裝置上確認，用側邊欄底部"**OAuth 驗證**"入口（移動端
   `/studio/oauth/verify`）。

線上接 Claude.ai / Claude Desktop 走[公網訪問指南](12-public-access.md)。

---

## 生產部署（HTTPS）

OAuth 2.1 對非 localhost 的 issuer **強制要求 HTTPS**。
[公網訪問指南](12-public-access.md)詳細介紹了 Caddy、nginx、docker compose、
CDN 的配置方法。簡要步驟：

1. 按[公網訪問指南 § 新增 HTTPS](12-public-access.md#新增-https公網訪問)
   讓 `https://your-domain.com` 通過 443 提供 HTTPS，代理轉發到 OpenViking 埠（預設 1933）。
2. 啟用 OAuth：`ov.conf` 裡 `{ "oauth": { "enabled": true } }`。
3. 在 Compose 的 `.env` 設定 `OPENVIKING_PUBLIC_BASE_URL=https://your-domain.com`。
4. 執行 `docker compose up -d` 應用容器環境變數變化。僅執行 `restart` 不會載入 `.env` 的修改。

HTTPS + OAuth 就緒後，按下面的方式接入客戶端。

---

## 接入僅支援 OAuth 的 MCP 客戶端

### Claude.ai (Web)

1. Settings → Connectors → **Add connector**。
2. 輸入 `https://my.ov/mcp` 作為伺服器 URL。
3. Claude 彈出授權頁面，自動跳到
   `https://my.ov/studio/oauth/consent?pending=...`。
4. 如未登入 Studio，先在彈出的"連線與身份"對話方塊裡填 API Key（也可在
   IdentityPicker 裡臨時粘一個 key 一次性授權）。
5. 在 consent 卡片確認 client_name / redirect_host 後點 **Authorize**。
6. 瀏覽器自動跳回 Claude，token 已頒發。

> 如果你在 CLI 裝置上觸發授權（本地瀏覽器打不開 consent），把
> authorize URL 複製到桌面瀏覽器，或在 consent 頁底部點 "Use another
> device →" 走 6 字元碼的跨裝置路徑（在另一臺已登入 Studio 的裝置開啟
> `/studio/oauth/verify` 輸入碼）。

### Claude Desktop / Claude Code

Claude Desktop 流程相同。Claude Code 直接用 API Key 更簡單：

```bash
claude mcp add --transport http openviking https://my.ov/mcp \
  --header "Authorization: Bearer <api-key>"
```

如果你想讓 Claude Code 走 OAuth，體驗和 Claude.ai 一致。

### ChatGPT (Codex / Plus / Enterprise)

在 ChatGPT 中通過開發者模式建立自定義 App，填入服務的 MCP URL，並完成瀏覽器中的 OAuth 授權。可用入口和管理許可權因套餐與工作區設定而異，按 [OpenAI 官方接入說明](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt)操作。Codex 的外掛與 MCP 配置見 [Codex 整合](../agent-integrations/04-codex.md)。

### Cursor

Cursor 看到 401 + `WWW-Authenticate: Bearer resource_metadata=...` 後會自動
進入 OAuth 流程。在 Cursor 的 MCP 設定里加 URL 即可。

---

## 用 `curl` 驗證完整流程

不需要真實 MCP 客戶端：

將 `OV_OAUTH_ORIGIN` 設為服務 HTTPS origin，`API_KEY` 設為已註冊使用者的 user/admin key。示例需要 `curl`、`jq`、OpenSSL 和 Python 3；按註釋從瀏覽器複製 pending ID 和授權碼。

```bash
OV_OAUTH_ORIGIN=https://my.ov
CID=$(curl -fsS "$OV_OAUTH_ORIGIN/register" \
  -H "Content-Type: application/json" \
  -d '{"redirect_uris":["http://127.0.0.1:9999/cb"],"client_name":"test","token_endpoint_auth_method":"none"}' \
  | jq -er '.client_id')

VERIFIER=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
CHALLENGE=$(printf "%s" "$VERIFIER" | openssl dgst -sha256 -binary | openssl base64 -A | tr '+/' '-_' | tr -d '=')
STATE=$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')
printf '%s\n' "$OV_OAUTH_ORIGIN/authorize?response_type=code&client_id=$CID&redirect_uri=http://127.0.0.1:9999/cb&code_challenge=$CHALLENGE&code_challenge_method=S256&state=$STATE"

# Open the URL in a browser; approve in Studio or supply its pending ID here.
curl -fsS "$OV_OAUTH_ORIGIN/api/v1/auth/oauth-verify" \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"pending_id":"<pending-id>","decision":"approve"}'

# From the redirect URL, verify state matches $STATE and copy the code.
# The callback page need not load for this manual test.
AUTH_CODE='<code-from-callback-url>'
TOKEN_RESPONSE=$(curl -fsS "$OV_OAUTH_ORIGIN/token" \
  --data-urlencode "grant_type=authorization_code" \
  --data-urlencode "code=$AUTH_CODE" \
  --data-urlencode "client_id=$CID" \
  --data-urlencode "code_verifier=$VERIFIER" \
  --data-urlencode "redirect_uri=http://127.0.0.1:9999/cb")
ACCESS_TOKEN=$(printf '%s' "$TOKEN_RESPONSE" | jq -er '.access_token')

curl -fsS "$OV_OAUTH_ORIGIN/mcp" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"manual-test","version":"1"}}}'

curl -fsS "$OV_OAUTH_ORIGIN/mcp" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'

curl -fsS "$OV_OAUTH_ORIGIN/mcp" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":2}'
```

---

## 配置參考

`ov.conf` 片段：

```jsonc
{
  "oauth": {
    "enabled": false,                       // 預設關閉
    "issuer": null,                         // 例 "https://my.ov"（可選；env 變數優先順序更高）
    "access_token_ttl_seconds": 3600,       // 1 小時
    "refresh_token_ttl_seconds": 2592000,   // 30 天
    "auth_code_ttl_seconds": 300,           // 5 分鐘
    "db_filename": "oauth.db"               // 相對 storage.workspace
  }
}
```

環境變數：

| 變數 | 用途 |
|---|---|
| `OPENVIKING_PUBLIC_BASE_URL` | 最高優先順序的公網 origin override（用作 issuer / PRM / `WWW-Authenticate`） |
| `OPENVIKING_CONFIG_FILE` | `ov.conf` 路徑（也可用 `--config`） |

---

## Token 模型

| Token | 形態 | 字首 | TTL | 儲存 |
|---|---|---|---|---|
| Access token | `secrets.token_urlsafe(40)` | `ovat_` | 1 小時 | SQLite (SHA-256 索引) |
| Refresh token | `secrets.token_urlsafe(40)` | `ovrt_` | 30 天 | SQLite (SHA-256 索引) |
| Authorization code | `secrets.token_urlsafe(40)` | `ovac_` | 5 分鐘 | SQLite (SHA-256 索引) |
| Display code（頁面） | 6 字元（去 O/0/I/1） | — | 10 分鐘 | SQLite (`oauth_pending_authorizations`) |

所有 token 都是 opaque（不簽發 JWT），OAuth 不需要 JWT 簽名金鑰。部署仍需管理 API 憑證、保護 token 資料庫，以及保留已配置的儲存加密金鑰。
每次請求按 SHA-256 雜湊查 SQLite，撤銷 token 是一次 `UPDATE`。

### Token 與身份

每個 token 在簽發時繫結一個 `(account_id, user_id, role)` 三元組。token 使用該身份，訪問時仍受當前資源 ACL 和 key 有效性約束。使用者後續提升角色不會升級已簽發 token，降權檢查可能拒絕舊 token。OAuth token 不能用於批准新的 OAuth 客戶端。

### OAuth 生命週期 ≤ 授權 Key 生命週期

每個 token 額外記錄授權方 API Key 的 SHA-256 指紋。每次 OAuth bearer
鑑權時服務端重算該使用者當前的 key 指紋並嚴格比對，效果：

- **輪換** 使用者 API Key（`regenerate_key`）立即讓該使用者名稱下所有 OAuth
  access / refresh token 失效。無需手動撤銷，下一次 bearer 請求即返回
  401，客戶端需重新走授權流程。
- **刪除** 使用者（`remove_user`）同理：指紋查詢返回 `None`，所有 OAuth
  token 立即停用。
- **ROOT** key 和 **trusted-mode** 身份無法簽發 OAuth（沒有 per-user
  key 可繫結）。`/api/v1/auth/oauth-verify` 會以 400 拒絕這類呼叫方。

指紋演算法為 `sha256(stored_key_value)`：API Key 雜湊未開啟時即明文 key
的 SHA-256，開啟時即 Argon2id 雜湊結果的 SHA-256。兩種情況下 stored
值都是建立/輪換時寫入一次後不再變動，因此指紋在兩次輪換之間穩定。

---

## 故障排查

### Claude.ai 直接報 "We couldn't connect" 沒彈出授權頁

Claude.ai 第一步是 GET `/.well-known/oauth-protected-resource`。如果這一步
404，OAuth 流程就根本不會啟動。檢查：

```bash
curl -i https://my.ov/.well-known/oauth-protected-resource
```

應當返回帶 `authorization_servers` 欄位的 JSON。如果是 404，要麼
`oauth.enabled = false`，要麼反代沒把 `/.well-known/...` 路徑轉發到 1933。

### "Issuer URL must be HTTPS"

MCP SDK 拒絕非 `127.0.0.1` / `localhost` 的 `http://` issuer。三選一：

- 設定 `OPENVIKING_PUBLIC_BASE_URL=https://my.ov`
- 在 `ov.conf` 裡把 `oauth.issuer` 寫成 `https://...`
- 僅本地測試時讓客戶端直連 `http://127.0.0.1:1933`

### 跨裝置 fallback 頁有碼，但 `/studio/oauth/verify` 報 "Invalid code"

碼是 6 字元**全大寫**，傳輸時區分大小寫。`/studio/oauth/verify` 的輸入框會
自動轉大寫。如果手動輸入，注意字母與數字的混淆字元（字母表已經排除了 `O`、`0`、`I`、`1`）。

### Refresh 一次後再用舊 token 被拒

Refresh token 是一次性的。如果舊 refresh 與新 refresh **同時被使用**（例如客戶
端有 bug），第二個會被拒絕，整條 token 鏈會被撤銷（RFC 9700 §4.14）。客戶端必
須重新走 authorize 流程。

### `/mcp` 401 沒有 `WWW-Authenticate` 頭

這個頭只在 `app.state` 上有 `oauth_provider` 時才發出 — 即
`oauth.enabled = true`。檢查：

```bash
curl -i https://my.ov/mcp -d '{}' -H 'Content-Type: application/json' | grep -i www-authenticate
```

---

## 參考

- [公網訪問與反向代理指南](12-public-access.md) — HTTPS、Caddy、nginx、docker compose
- [MCP 規範 — Authorization](https://modelcontextprotocol.io/specification/2025-03-26/basic/authorization)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://datatracker.ietf.org/doc/html/rfc8414)
- [RFC 9728 — OAuth 2.0 Protected Resource Metadata](https://datatracker.ietf.org/doc/html/rfc9728)
- [RFC 7591 — Dynamic Client Registration](https://datatracker.ietf.org/doc/html/rfc7591)
- [RFC 7636 — PKCE](https://datatracker.ietf.org/doc/html/rfc7636)
- [OpenViking MCP 整合指南](06-mcp-integration.md)

[Compose restart 的配置載入行為](https://docs.docker.com/reference/cli/docker/compose/restart/)。
