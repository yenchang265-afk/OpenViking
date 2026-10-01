# 認證

> **先看這裡：選擇適合你的認證模式**

## 📚 前置知識 - 我該用哪個？

| 認證模式 | 是什麼？ | 適合誰？ | **推薦度** |
|---------|----------|---------|------------|
| **API Key** (預設) | OpenViking 自己管理使用者和金鑰 | 小團隊、獨立部署 | ⭐⭐⭐⭐⭐ |
| **OIDC** | 對接企業單點登入（Okta/Auth0/Keycloak/Azure AD 等） | 企業 SSO 整合 | ⭐⭐⭐⭐ |
| **LDAP** | 對接企業使用者目錄（Windows AD/OpenLDAP） | 已有企業目錄服務 | ⭐⭐⭐⭐ |
| **Trusted** | 上游閘道器/反向代理斷言身份 | 部署在受信任內網/閘道器後 | ⭐⭐⭐ |
| **Dev** | 無認證，僅本地開發 | **只用於本地開發！** | ⭐⭐ |

### 🔍 決策樹

```
┌─────────────────────────────────────────────────────┐
│ 企業裡有現成的身份系統？                           │
├─────────────────────────────────────────────────────┤
│ 是 SaaS 身份？（Okta/Auth0/Keycloak）               │
│ → 用 **OIDC** ✅                                      │
│                                                     │
│ 是本地目錄？（Windows AD/OpenLDAP）                  │
│ → 用 **LDAP** ✅                                      │
├─────────────────────────────────────────────────────┤
│ 沒有身份系統？                                       │
│ → 用 **API Key**（預設）✅                           │
├─────────────────────────────────────────────────────┤
│ 部署在內部閘道器後面？                                 │
│ → 用 **Trusted** ✅                                   │
└─────────────────────────────────────────────────────┘
```

---

## 🏁 快速開始 - 3分鐘跑起來

### 方案一：API Key（最簡單）

只需要配置 `root_api_key`，剩下的預設就好！

```json
{
  "server": {
    "auth_mode": "api_key",
    "root_api_key": "your-secret-root-key-here"
  }
}
```

啟動伺服器：
```bash
openviking-server
```

用 API 管理使用者：
```bash
# 建立帳號 + 管理員
curl -X POST http://localhost:1933/api/v1/admin/accounts \
  -H "X-API-Key: your-secret-root-key" \
  -H "Content-Type: application/json" \
  -d '{"account_id": "my-team", "admin_user_id": "alice"}'
```

### 方案二：OIDC（企業 SSO）

**最小配置（不需要 mapping）：**

```json
{
  "server": {
    "auth_mode": "oidc",
    "oidc": {
      "issuer": "https://your-company.okta.com"
    }
  }
}
```

預設自動使用：
- `account_id` → 所有使用者在同一組織（"default"）
- `user_id` → 使用 OIDC 標準欄位 `sub`
- `role` → 預設為 `user`

啟動後健康檢查會自動驗證是否連線成功！

**進階配置（需要隔離團隊時）：**
參考下方「🔧 Identity Mapping 詳解」章節。

### 方案三：LDAP（企業目錄）

**最小配置（搜尋繫結模式）：**

```json
{
  "server": {
    "auth_mode": "ldap",
    "ldap": {
      "host": "ldap.your-company.com",
      "port": 636,
      "use_ssl": true,
      "bind_dn": "cn=openviking,dc=your-company,dc=com",
      "bind_password": "${LDAP_PASSWORD}",
      "base_dn": "dc=your-company,dc=com",
      "user_search_filter": "(uid=%s)"
    }
  }
}
```

預設自動使用：
- `account_id` → 所有使用者在同一組織（"default"）
- `user_id` → 使用 LDAP 字段 `uid`
- `role` → 預設為 `user`

---

## 📚 概念詳解

### OIDC 是什麼？

OIDC (OpenID Connect) 是業界標準的單點登入協議。

| 術語 | 說明 |
|------|------|
| **Issuer** | OIDC 提供商的 URL（如 `https://your-company.okta.com`） |
| **Claims** | Token 裡包含的使用者資訊（如 `sub` = 使用者ID，`email` = 郵箱） |
| **JWKS** | 用於驗證 Token 簽名的金鑰集（自動從 Issuer 發現） |
| **Audience** | 可選，驗證 Token 是發給誰的 |

### LDAP 是什麼？

LDAP (Lightweight Directory Access Protocol) 是企業使用者目錄的標準協議。

| 術語 | 說明 |
|------|------|
| **DN** | 唯一標識物件的路徑（如 `uid=alice,ou=users,dc=example,dc=com`） |
| **Base DN** | 搜尋使用者的根節點（如 `dc=example,dc=com`） |
| **Bind DN** | 連線 LDAP 用的服務帳號 |
| **Attribute** | 使用者屬性（如 `uid`, `email`, `memberOf`） |

### Identity Mapping 是什麼？

簡單說：**把外部身份源的欄位對映到 OpenViking 的身份上。**

```
外部身份源       →       Mapping 規則       →       OpenViking 身份
─────────────────────────────────────────────────────────────────────
OIDC Claims: {
  "sub": "user123",          →      claim="sub"        →  user_id = "user123"
  "department": "eng",       →      claim="department" →  account_id = "eng"
  "role": "admin"            →      mapping={"admin":"admin"} → role = "admin"
}
```

支持的模式：
- **Organization**：所有使用者在同一組織（預設）
- **Team**：按部門/團隊隔離（從外部欄位提取）

---

## ⚙️ 完整配置參考

### OIDC 完整配置

```json
{
  "server": {
    "auth_mode": "oidc",
    "oidc": {
      "issuer": "https://your-company.okta.com",
      "client_id": "0oabc123def456",
      "client_secret": "${OIDC_CLIENT_SECRET}",
      "audience": "openviking",
      "jwks_uri": "https://your-company.okta.com/oauth2/v1/keys",
      "token_location": "header",
      "token_header_name": "Authorization",
      "token_header_prefix": "Bearer ",
      "identity": {
        "account_id": {
          "mode": "organization",
          "source": "claim",
          "claim": "tenant_id",
          "prefix": "org-",
          "fallback": "default-org"
        },
        "user_id": {
          "source": "claim",
          "claim": "sub",
          "prefix": "user-",
          "normalize": "lowercase"
        },
        "role": {
          "source": "claim",
          "claim": "role",
          "mapping": {
            "administrator": "admin",
            "developer": "user",
            "viewer": "user"
          },
          "default": "user"
        }
      }
    }
  }
}
```

### LDAP 完整配置

```json
{
  "server": {
    "auth_mode": "ldap",
    "ldap": {
      "host": "ldap.your-company.com",
      "port": 636,
      "use_ssl": true,
      "use_starttls": false,
      "bind_dn": "cn=openviking,dc=your-company,dc=com",
      "bind_password": "${LDAP_PASSWORD}",
      "base_dn": "dc=your-company,dc=com",
      "user_search_filter": "(uid=%s)",
      "user_search_base": "ou=users,dc=your-company,dc=com",
      "username_attribute": "uid",
      "email_attribute": "mail",
      "name_attribute": "cn",
      "user_dn_pattern": "uid=%s,ou=users,dc=your-company,dc=com",
      "identity": {
        "account_id": {
          "mode": "team",
          "source": "dn_attribute",
          "attribute": "ou",
          "prefix": "team-",
          "fallback": "default"
        },
        "user_id": {
          "source": "attribute",
          "attribute": "uid",
          "normalize": "lowercase"
        },
        "role": {
          "source": "group_membership",
          "group_mapping": {
            "cn=openviking-admins,ou=groups,dc=your-company,dc=com": "admin",
            "cn=openviking-users,ou=groups,dc=your-company,dc=com": "user"
          },
          "default": "user"
        }
      }
    }
  }
}
```

### 進階 Mapping 示例

#### 1. 正則提取

從郵箱裡提取使用者名稱：
```json
{
  "user_id": {
    "source": "claim",
    "claim": "email",
    "regex": "^([^@]+)@",
    "regex_group": 1
  }
}
```
輸入：`alice@example.com` → 輸出：`alice`

#### 2. 多字段回退

嘗試多個欄位，第一個有值的生效：
```json
{
  "user_id": {
    "source": "claim",
    "claims": ["username", "email", "sub"],
    "fallback": "guest"
  }
}
```

#### 3. 組合欄位

把 Tenant ID 和 Department 拼起來：
```json
{
  "account_id": {
    "source": "composite",
    "parts": [
      {"source": "claim", "claim": "tenant_id"},
      {"literal": "-"},
      {"source": "claim", "claim": "department"}
    ]
  }
}
```
輸入：`tenant_id="acme"`, `department="eng"` → 輸出：`acme-eng`

---

## 🐛 故障排除

### OIDC 常見問題

#### 問題 1：「找不到 issuer」

```
❌ oidc_issuer_configured: Issuer is not configured
```

**解決方法：**
- 檢查 URL 是否有協議（`https://`）
- 確認 URL 是否可以訪問：
  ```bash
  curl https://your-company.okta.com/.well-known/openid-configuration
  ```

#### 問題 2：「無法獲取 JWKS」

```
⚠️ oidc_jwks_accessible: Failed to fetch JWKS: ...
```

**解決方法：**
- 檢查網路連線
- 可能是防火牆問題，嘗試手動配置 `jwks_uri`

#### 問題 3：「Token 驗證失敗」

**診斷步驟：**
1. 檢查 Token 格式是否正確
2. 檢視日誌，確認 `iss` 匹配配置
3. 如果是過期 Token，這是正常的，需要重新登入

---

### LDAP 常見問題

#### 問題 1：「無法連線 LDAP」

```
⚠️ ldap_connection: Failed to connect to LDAP: Connect timeout
```

**解決方法：**
- 檢查伺服器地址和埠
- 確認 `use_ssl` 設定正確：
  - LDAPS (SSL) 通常端口 636
  - 普通 LDAP 通常端口 389
  - 可以用 `ldapsearch` 測試：
    ```bash
    ldapsearch -x -H ldaps://ldap.your-company.com:636 -b "dc=your-company,dc=com"
    ```

#### 問題 2：「Bind 失敗」

```
⚠️ ldap_connection: Bind failed: Invalid credentials
```

**解決方法：**
- 檢查 `bind_dn` 和 `bind_password`
- 確認 Bind 帳號在 LDAP 中存在

#### 問題 3：「找不到使用者」

```
❌ 搜尋結果為空
```

**解決方法：**
- 檢查 `user_search_filter` 是否正確
- 檢查 `base_dn` 是否正確
- 嘗試用 `ldapsearch` 手動測試：
  ```bash
  ldapsearch -x -H ldaps://ldap.your-company.com:636 -D "cn=openviking,dc=your-company,dc=com" -W -b "dc=your-company,dc=com" "(uid=alice)"
  ```

---

### 通用除錯技巧

1. **啟用 Debug 日誌**（啟動時看到更多細節）
2. **先看健康檢查**（啟動時自動執行）
3. **檢查配置格式**（JSON 是否有效）
4. **檢視日誌**（重點看錯誤資訊前面的內容）

---

## 🔧 自定義認證外掛（進階）

如果內建的模式不夠用，可以自己開發！

服務端採用外掛化認證架構。每種 `auth_mode` 對應一個 `AuthPlugin` 實現。內建外掛（`dev`, `api_key`, `trusted`, `oidc`, `ldap`）會自動註冊；第三方外掛可通過繼承 `AuthPlugin` 並在啟動前註冊來擴充。

### 插件接口（`openviking.server.auth.plugin.AuthPlugin`）

| 方法 | 用途 |
|------|------|
| `resolve_identity(request, api_key, x_openviking_account, x_openviking_user)` | 將憑據解析為 `ResolvedIdentity` |
| `validate_config(config)` | 在啟動時校驗 `ServerConfig`；遇到致命錯誤應呼叫 `sys.exit(1)` |
| `initialize(app, service, config)` | 在 `app.state` 上初始化執行時狀態（如 `APIKeyManager`） |
| `get_request_context_checks(path, identity)` | 可選的認證後路徑/身份檢查 |
| `requires_api_key_manager()` | Admin API 路由是否需要 `APIKeyManager` |
| `can_skip_api_key_for_bot_proxy()` | Bot 代理是否可以跳過 API Key 校驗（如 `dev` 模式） |

### 註冊自定義外掛示例

```python
from openviking.server.auth.plugin import AuthPlugin
from openviking.server.auth.registry import register_auth_plugin
from openviking.server.identity import ResolvedIdentity, Role

@register_auth_plugin
class CustomAuthPlugin(AuthPlugin):
    auth_mode = "custom"

    async def resolve_identity(self, request, *, api_key=None, x_openviking_account=None, x_openviking_user=None):
        # 自定義認證邏輯...
        return ResolvedIdentity(role=Role.USER, account_id="...", user_id="...")

    def validate_config(self, config):
        pass

    async def initialize(self, app, service, config):
        pass
```

然後在 `ov.conf` 中設定 `server.auth_mode = "custom"`。

### 自定義角色

內建的 `Role` 類支援動態註冊自定義角色及許可權等級：

```python
from openviking.server.identity import Role

Role.register("operator", rank=1)  # 許可權介於 USER (0) 與 ADMIN (1) 之間
```

自定義角色可直接用於 `require_role()` 和 `require_auth_role()` 裝飾器。

---

## 內建認證模式詳情

### Trusted 模式

trusted 模式的普通資料面請求無需預先註冊 user 或建立 user API Key。服務端會非同步批次註冊
該 account/user，使其最終出現在既有 account/user 管理介面中（預設五分鐘刷盤）。註冊不會
建立 user API Key，也不會修改 group 或已有 user 的角色。設定
`server.trusted_identity_flush_interval_seconds` 為 `0` 可完全關閉註冊能力；
`/api/v1/admin/*` 請求不會被註冊。

```bash
# 建立工作區 + 首個 admin
curl -X POST http://localhost:1933/api/v1/admin/accounts \
  -H "X-API-Key: your-secret-root-key" \
  -H "Content-Type: application/json" \
  -d '{"account_id": "acme", "admin_user_id": "alice"}'
# 返回: {"result": {"account_id": "acme", "admin_user_id": "alice", "user_key": "..."}}

# 註冊普通使用者（ROOT 或 ADMIN 均可）
curl -X POST http://localhost:1933/api/v1/admin/accounts/acme/users \
  -H "X-API-Key: your-secret-root-key" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "bob", "role": "user"}'
# 返回: {"result": {"account_id": "acme", "user_id": "bob", "user_key": "..."}}
```

ACL 使用者組是例外：組和成員通過 [Admin API](../api/08-admin.md#使用者組) 維護，成員必須是當前 account 已註冊的使用者。客戶端不能通過 header 或 token claim 宣告組；服務端認證使用者後查詢組登錄檔，並把結果寫入本次請求的 `RequestContext.group_ids`。

受信部署也可以通過受信閘道器呼叫 Admin API，目前支援兩種方式：

- 攜帶受信部署自身的 `root_api_key`。對於 `/api/v1/admin/*`，服務端校驗該 key 後會將請求視為 ROOT。
- 如果 Admin 路由指向具體 account/user，也可以同時攜帶 `X-OpenViking-Account` + `X-OpenViking-User`。這些 header 必須與目標 URL 匹配，並會保留為請求身份；授權仍來自受信 `root_api_key`。

角色更新 API 只支援將使用者提升為 ADMIN。Trusted Admin API 的管理許可權來自已校驗的部署 root key，無需也不支援建立 ROOT 使用者。

下面是“受信上游身份”這種方式的示例：

```bash
# 首先，註冊閘道器管理員（在 api_key 模式下執行一次）
curl -X POST http://localhost:1933/api/v1/admin/accounts \
  -H "X-API-Key: your-secret-root-key" \
  -H "Content-Type: application/json" \
  -d '{"account_id": "platform", "admin_user_id": "gateway-admin"}'

# 然後，在 trusted 模式下使用該身份呼叫 Admin API
curl -X POST http://localhost:1933/api/v1/admin/accounts \
  -H "X-API-Key: your-secret-root-key" \
  -H "X-OpenViking-Account: platform" \
  -H "X-OpenViking-User: gateway-admin" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "acme",
    "admin_user_id": "alice"
  }'
```

## 客戶端使用

OpenViking 支援兩種方式傳遞 API Key：

**X-API-Key 請求頭**

```bash
curl http://localhost:1933/api/v1/fs/ls?uri=viking:// \
  -H "X-API-Key: <user-key>"
```

**Authorization: Bearer 請求頭**

```bash
curl http://localhost:1933/api/v1/fs/ls?uri=viking:// \
  -H "Authorization: Bearer <user-key>"
```

**Python SDK（HTTP）**

```python
import openviking_sdk as ov

client = ov.SyncHTTPClient(
    url="http://localhost:1933",
    api_key="<user-key>",
)
```

**CLI（通過 ovcli.conf）**

```json
{
  "url": "http://localhost:1933",
  "api_key": "<user-key>"
}
```

如果使用普通 `user key` 或 `admin key`，`account` 和 `user` 可以省略，因為服務端可以從 key 反查出來；如果使用 `trusted` 模式，則建議明確配置。

**CLI 覆蓋引數**

```bash
openviking --account acme --user alice ls viking://
```

### 使用 --sudo 和 Root API Key

CLI 支援在 `ovcli.conf` 中同時配置 `api_key`（用於普通使用者操作）和 `root_api_key`（用於管理員操作）：

```json
{
  "url": "http://localhost:1933",
  "api_key": "<user-key>",
  "root_api_key": "<root-key>"
}
```

當需要執行管理員命令（`admin`、`system`、`reindex`）時，使用 `--sudo` 標誌提升許可權：

```bash
# 列出所有帳戶（需要 root 許可權）
ov --sudo admin list-accounts

# 重新索引內容
ov --sudo reindex viking://

# 系統命令
ov --sudo system status
```

`--sudo` 標誌：
- 僅適用於管理員命令：`admin`、`system`、`reindex`
- 用於非管理員命令時會報錯
- `ovcli.conf` 中未配置 `root_api_key` 時會報錯
- 請求時使用 `root_api_key` 替代 `api_key`

### 租戶資料訪問

租戶級資料 API（如 `ls`、`find`、resources、sessions 等）在 `api_key`
模式下必須使用綁定了 account/user 的 key。這個 key 可以是 `USER` key，也可以是
`ADMIN` key；`ADMIN` key 會以它自己的 user 身份訪問資料，不能通過
`X-OpenViking-Account` / `X-OpenViking-User` 切換身份。

ACL 檢查還會使用服務端解析的 account 內使用者組。成員變更從下一次請求生效，不需要簽發新 API Key，也不會修改資源 ACL。

`ROOT` key 沒有繫結租戶 user，因此在 `api_key` 模式下不能訪問租戶級資料 API。
如果部署需要由上游閘道器斷言 `account` / `user`，請使用 `trusted` 模式，而不是在
root key 請求上攜帶身份 header。

**ovcli.conf**

```json
{
  "url": "http://localhost:1933",
  "auth_mode": "trusted",
  "api_key": "your-trusted-server-key",
  "account": "acme",
  "user": "alice"
}
```

## Trusted 模式

Trusted 模式不會查詢 user key，而是直接信任每個請求顯式攜帶的身份請求頭：

```json
{
  "server": {
    "auth_mode": "trusted",
    "host": "127.0.0.1"
  }
}
```

### Dev 模式

當 `auth_mode = "dev"`（或未配置 `root_api_key` 時自動推導）時，認證停用，所有請求以 ROOT 身份訪問 default account。

```json
{
  "server": {
    "host": "127.0.0.1"
  }
}
```

> **安全提示：** 預設 `host` 為 `127.0.0.1`。如果需要將服務暴露到網路，**必須**配置 `root_api_key`。

---

## CLI 配置 LDAP 認證

OpenViking CLI (`ov`) 支援通過 LDAP 進行認證。配置完成後，所有 CLI 命令會自動使用 LDAP 憑據。

### 配置方式

#### 1. 配置檔案方式（推薦）

編輯 `~/.openviking/ovcli.conf` 檔案，新增 LDAP 認證配置：

```json
{
    "url": "http://localhost:1933",
    "auth_mode": "ldap",
    "ldap_username": "alice",
    "ldap_password": "password123",
    "account": "default"
}
```

**配置項說明：**

| 配置項 | 必需 | 說明 |
|--------|------|------|
| `url` | 是 | OpenViking 伺服器地址 |
| `auth_mode` | 是 | 認證模式，設定為 `"ldap"` 啟用 LDAP |
| `ldap_username` | 是 | LDAP 使用者名稱（UID） |
| `ldap_password` | 否 | LDAP 密碼（不提供時 CLI 不傳送密碼） |
| `account` | 否 | OpenViking 帳戶 ID（預設為 `"default"`） |

#### 2. 混合配置

可以部分配置在檔案中，部分通過環境變數（如 `OPENVIKING_URL`、`OPENVIKING_ACCOUNT`）覆蓋。

### 使用 CLI

配置完成後，所有 CLI 命令會自動使用 LDAP 認證：

```bash
# 列出資源
ov ls viking://

# 讀取資源
ov read viking://resources/example.md

# 寫入資源
ov write viking://resources/test.md --content "Hello LDAP!"
```

### 構建 Rust CLI（如需更新）

如果修改了 Rust CLI 原始碼，需要重新構建：

```bash
make build-cli
```

構建後的二進位制檔案位於 `openviking/bin/ov`。

### 切換認證模式

編輯 `~/.openviking/ovcli.conf`，修改 `auth_mode` 為 `"api_key"` 或刪除該欄位即可切換認證模式。

### 安全建議

1. **避免明文儲存密碼**：推薦使用環境變數或金鑰管理工具，而非在配置檔案中硬編碼密碼
2. **使用 HTTPS**：生產環境中確保伺服器使用 HTTPS 連線
3. **最小許可權**：使用普通使用者帳戶進行日常操作，管理員帳戶僅用於管理任務
4. **定期輪換密碼**：遵循組織的密碼安全策略

### 故障排查

**"Missing LDAP credentials" 錯誤：**
- 檢查 `auth_mode` 是否設定為 `"ldap"`
- 確認 `username` 和 `password` 配置正確

**"LDAP authentication failed" 錯誤：**
- 驗證 LDAP 使用者名稱和密碼是否正確
- 檢查 LDAP 伺服器是否可訪問
- 檢視伺服器端日誌獲取詳細錯誤資訊

**"Permission denied" 錯誤：**
- 確認使用者 LDAP 組是否對映到正確的 OpenViking 角色
- 檢查操作是否需要管理員許可權
- 聯絡系統管理員確認許可權配置

**除錯模式：**
```bash
# 啟用詳細日誌
RUST_LOG=debug ov ls viking://

# 檢查配置
ov doctor
```

---

## 相關文件

- [多租戶](../concepts/11-multi-tenant.md) - 多租戶能力、共享邊界與接入實踐
- [資源訪問控制（ACL）](../concepts/15-acl.md) - account 內資源許可權
- [配置](01-configuration.md) - 配置檔案說明
- [服務部署](03-deployment.md) - 服務部署
- [API 概覽](../api/01-overview.md) - API 參考

---

## 📝 附錄：Admin API 參考

| 方法 | 端點 | 角色 | 說明 |
|------|------|------|------|
| POST | `/api/v1/admin/accounts` | ROOT | 建立工作區 + 首個 admin |
| GET | `/api/v1/admin/accounts` | ROOT | 列出所有工作區 |
| DELETE | `/api/v1/admin/accounts/{id}` | ROOT | 刪除工作區 |
| POST | `/api/v1/admin/accounts/{id}/users` | ROOT, ADMIN | 註冊使用者 |
| GET | `/api/v1/admin/accounts/{id}/users` | ROOT, ADMIN | 列出使用者 |
| DELETE | `/api/v1/admin/accounts/{id}/users/{uid}` | ROOT, ADMIN | 移除使用者 |
| PUT | `/api/v1/admin/accounts/{id}/users/{uid}/role` | ROOT, ADMIN | 將使用者提升為 ADMIN；ADMIN 僅限本帳戶 |
| POST | `/api/v1/admin/accounts/{id}/users/{uid}/key` | ROOT, ADMIN | 重新生成 user key |
