# 多租戶

OpenViking 的多租戶不是“為每個團隊部署一套獨立服務”，而是在同一個 OpenViking Server 內，用 `account` 和 `user` 兩層身份邊界來隔離和共享資料。

它適合兩類典型場景：

- 多個團隊或客戶共享一套 OpenViking 服務，但資料必須隔離
- 一個團隊內的多個使用者需要共享資源、隔離記憶

## 能做什麼

啟用多租戶後，你可以：

- 用一個 OpenViking Server 服務多個團隊、客戶或應用
- 用 `account` 隔離不同團隊的資料
- 在同一個 `account` 內共享 `resources`，並用 ACL 對目錄或檔案細化授權
- 用 `user` 隔離使用者級記憶和會話
- 用 ROOT / ADMIN / USER 角色分層管理許可權
- 支持 OpenClaw 插件、Vikingbot、CLI、HTTP SDK 等不同接入方式

## 核心身份模型

### `account_id`

`account` 是最外層租戶邊界，可以理解為工作區、團隊或客戶空間。

- 不同 `account` 之間的資料預設完全隔離
- Root 使用者可以建立、刪除 `account`
- `resources`、`user`、`session` 都落在某個 `account` 下

### `user_id`

`user` 是 account 內的使用者邊界。

- 使用者記憶和使用者會話按 `user_id` 隔離
- 普通 user 只能訪問自己的 user space
- admin 可以管理本 account 下的使用者

### 角色

| 角色 | 作用域 | 典型能力 |
|------|--------|----------|
| ROOT | 全域 | 建立/刪除 account、跨租戶訪問、管理使用者 |
| ADMIN | 單個 account | 管理本 account 的使用者、重置 user key |
| USER | 單個 account | 訪問自己的 user/peer/session 資料和 account 內共享資源 |

## 認證模式

OpenViking Server 支援兩種多租戶相關認證模式：

| 模式 | 配置 | 身份來源 | 適用場景 |
|------|------|----------|----------|
| `api_key` | `server.auth_mode = "api_key"` | Root key 或 user key | 標準部署方式 |
| `trusted` | `server.auth_mode = "trusted"` | 上游顯式注入 `X-OpenViking-Account` / `X-OpenViking-User` | 受信閘道器後面 |

在 trusted 模式下，上游閘道器還可以斷言 `X-OpenViking-Role: user` 或 `X-OpenViking-Role: admin`。角色斷言要求服務端已配置 `root_api_key`，且請求攜帶匹配的 API Key。`X-OpenViking-Role: root` 會被拒絕；ROOT 只保留給已校驗的 Admin API 回退路徑。

### `root_api_key` 的作用

配置 `server.root_api_key` 後，OpenViking 才進入正式多租戶模式：

- Root key 用於管理 account 和 user
- User key 由 Admin API 生成，用於普通業務讀寫
- 服務端會從 user key 反解出 `account_id`、`user_id` 和角色

如果 `auth_mode = "api_key"` 且未配置 `root_api_key`，服務端會進入開發模式：

- 預設所有請求都被視為 ROOT
- 預設身份是 `default/default`
- 只允許繫結在 localhost 上使用

## 共享與隔離邊界

### 邏輯層

| 資料型別 | 是否跨 account 共享 | account 內是否共享 | 預設隔離邊界 |
|----------|---------------------|-------------------|--------------|
| 共享資源 (`viking://resources`) | 否 | 預設共享，可用 ACL 限制 | account / ACL |
| 使用者資源 (`viking://user/{user_id}/resources`) | 否 | 否 | user |
| Peer 資源 (`viking://user/{user_id}/peers/{peer_id}/resources`) | 否 | 否 | user / peer |
| 記憶 | 否 | 否 | user / peer |
| 技能 | 否 | 否 | user |
| 會話 | 否 | 否 | user / session |

### 儲存層

對使用者來說，URI 仍然是統一的 `viking://...`：

```text
viking://resources/project-a/
viking://user/alice/memories/
viking://user/alice/resources/
viking://user/alice/peers/web-visitor-alice/resources/
```

但底層儲存會自動帶上 account 字首：

```text
/local/{account_id}/resources/project-a/
/local/{account_id}/user/alice/memories/
/local/{account_id}/user/alice/resources/
/local/{account_id}/user/alice/peers/web-visitor-alice/resources/
```

因此多租戶隔離不是靠“不同 URI 字首”，而是靠請求上下文中的 `account_id` 和 `user_id` 共同生效。

### 檔案系統與檢索層

檔案系統操作和語義檢索都受租戶約束：

- 非 ROOT 請求會自動按 `account_id` 過濾
- `resources` 預設允許檢索 account 內共享資源；設定 ACL 後按有效 ACL 過濾
- 使用者資源始終按當前 `user space` 隔離；需要共享時移動到 `viking://resources`
- `memory` 和 `skill` 繼續按當前 `user space` 過濾
- Actor peer 會把 `viking://user/{user}/peers` 過濾到一個 peer，並作用於檔案系統和檢索操作

這意味著“能搜到什麼”與“能讀到什麼”保持一致，不會因為向量召回而越權。

<a id="peer-restricted-view"></a>

### Peer 集合過濾

`peer_id` 是當前 user 邊界內的內容範圍，不會改變 tenant 或 user 身份。

當一次請求只應該看到當前使用者 peer 集合中的某一個 peer 時，設定
`X-OpenViking-Actor-Peer: <peer_id>`，或使用 SDK/CLI 的 `actor_peer_id`：

- 空 target 檢索仍包含當前使用者根和公共 `viking://resources`。
- 檢索解析到 `viking://user/{user}/peers` 時，只選擇該 peer 的 memories/resources。
- 檔案系統操作不能 read、list、tree、grep/search/find、write、move 或 delete `viking://user/{user}/peers` 下的其他 peer。
- User-scoped memories、resources、skills、共享 resources 和 session 歸屬不因 actor peer 改變。
- peer ID 必須是安全的單段路徑標識，例如 `web-visitor-alice`。

## 標準使用流程

### 1. 啟用多租戶

```json
{
  "server": {
    "auth_mode": "api_key",
    "root_api_key": "your-secret-root-key"
  }
}
```

### 2. ROOT 建立工作區和首個管理員

```bash
curl -X POST http://localhost:1933/api/v1/admin/accounts \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-root-key" \
  -d '{
    "account_id": "acme",
    "admin_user_id": "alice"
  }'
```

### 3. ADMIN 或 ROOT 註冊普通使用者

```bash
curl -X POST http://localhost:1933/api/v1/admin/accounts/acme/users \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <admin-or-root-key>" \
  -d '{
    "user_id": "bob",
    "role": "user"
  }'
```

### 4. 普通業務訪問優先使用 user key

常規讀寫、搜尋、會話提交等請求，優先用 user key：

```bash
curl http://localhost:1933/api/v1/fs/ls?uri=viking:// \
  -H "X-API-Key: <bob-user-key>"
```

這樣服務端可以直接從 key 反解身份，無需額外傳 `account` / `user`。

### 5. 資料 API 身份來自 user 或 admin key

在 `api_key` 模式下，`ls`、`find`、`sessions` 這類租戶級資料 API 會從 API
key 自身解析有效的 account 和 user。不要在該模式下發送
`X-OpenViking-Account` 或 `X-OpenViking-User`；基於 header 的身份斷言只屬於
trusted mode。

`ADMIN` key 可以用它自己的 account/user 身份訪問資料 API：

```bash
curl http://localhost:1933/api/v1/fs/ls?uri=viking:// \
  -H "X-API-Key: <admin-user-key>"
```

`ROOT` key 用於 Admin API 以及少量 system/monitoring API。它在 `api_key`
模式下不能訪問租戶級資料 API，因為它沒有繫結到某個租戶使用者。資料訪問請使用
user/admin key；如果需要上游斷言身份，請使用 trusted mode。

## 接入實踐

### OpenClaw 外掛 2.0：每個例項使用 user key

OpenClaw 外掛當前的多租戶實踐是“外掛側只持有一個使用者身份”：

- 遠端模式配置 `baseUrl + apiKey`，可選 `peer_role` / `peer_prefix`
- `apiKey` 推薦配置為某個 user 的 user key
- 服務端從 user key 自動解析 `account_id` 和 `user_id`
- 外掛把 OpenClaw agent 身份保留在 peer/session metadata 中，而不是租戶 header 中

典型配置：

```bash
openclaw config set plugins.entries.openviking.config.mode remote
openclaw config set plugins.entries.openviking.config.baseUrl "http://your-server:1933"
openclaw config set plugins.entries.openviking.config.apiKey "<user-api-key>"
openclaw config set plugins.entries.openviking.config.peer_role assistant
openclaw config set plugins.entries.openviking.config.peer_prefix "<peer-prefix>"
```

這種模式的特點：

- 接入簡單，外掛不需要管理 account/user 生命週期
- 最適合“一個 OpenClaw 例項對應一個 OpenViking 使用者”的場景
- `peer_prefix` 用於區分 OpenClaw 執行時身份，參與 peer/session 後設資料
- 同一 account 內的 `resources` 預設共享，也可以通過 ACL 限制到指定使用者；memory 按 user scope 隔離

### OpenClaw 外掛為何通常不配 `account` / `user`

因為在 `api_key` 模式下，user key 已經足夠表達身份：

- `account`、`user` 由服務端從 key 反解
- 外掛可以提供 `peer_prefix` 作為執行時身份標籤
- 外掛內部寫入 user-scoped memory，並用 `peer_id` 表達每條訊息的說話人

如果給外掛直接配置 root key，則普通租戶資料 API 沒有從 key 綁定出來的租戶使用者，
這不適合作為日常讀寫方式。

### Vikingbot：root key 代管使用者身份

Vikingbot 當前的實踐與 OpenClaw 外掛不同，它更接近“平臺代理多個終端使用者”：

- bot 連線 OpenViking 時持有 root key
- bot 配置固定的 `account_id`
- bot 會在該 account 下自動註冊使用者
- bot 會快取每個 user 的 user key，並儘量用對應 user key 去提交/檢索 memory

相關配置示例：

```json
{
  "bot": {
    "ov_server": {
      "server_url": "http://127.0.0.1:1933",
      "root_api_key": "test",
      "account_id": "default",
      "admin_user_id": "default"
    }
  }
}
```

這種模式的特點：

- 適合一個 bot 服務承載多個聊天使用者
- 同一 account 下的 `resources` 預設共享，ACL 可以對具體目錄或檔案細化許可權
- 使用者記憶通過自動註冊的 user 身份隔離
- bot 側需要承擔更多租戶生命週期管理邏輯

## 什麼時候選哪種實踐

| 場景 | 推薦方式 |
|------|----------|
| 一個 OpenClaw 例項對應一個固定身份 | OpenClaw 外掛 + user key |
| 一個閘道器/機器人服務承載很多終端使用者 | Vikingbot + root key 代管使用者 |
| 受信閘道器統一注入身份 | `trusted` 模式 |
| 單機本地體驗、無需真正租戶隔離 | 開發模式（無 `root_api_key`） |

## 常見誤區

### 1. `root_api_key` 不是常規業務 key

Root key 主要用於：

- 建立/刪除 account
- 註冊使用者
- 重置 key
- 運維和除錯

正常業務請求應按呼叫者身份使用 user key 或 admin key。

### 2. `peer_id` 不決定 account

`peer_id` 表示當前使用者下的互動物件。它不建立租戶，但可以通過顯式 peer URI 或
peer 集合過濾選擇當前使用者內的 peer 內容子空間，例如
`viking://user/{user_id}/peers/{peer_id}/memories` 或
`viking://user/{user_id}/peers/{peer_id}/resources`。

- account 邊界由 `account_id` 決定
- user 邊界由 `user_id` 決定
- peer 內容仍位於該 user 邊界內

### 3. 不配置 `root_api_key` 不等於“單租戶正式部署”

這只是開發模式：

- 預設全部請求以 ROOT 身份執行
- 不適合暴露到公網或團隊共享環境

### 4. OpenClaw 外掛和 Vikingbot 不是同一種租戶實踐

- OpenClaw 外掛：更像“客戶端拿到一個 user 身份後直接訪問”
- Vikingbot：更像“平臺代理多個使用者，並代為申請和管理 user key”

## 相關文件

- [認證](../guides/04-authentication.md) - 認證模式、請求頭和 key 規則
- [配置](../guides/01-configuration.md) - `root_api_key` 和 `auth_mode`
- [管理員（多租戶）](../api/08-admin.md) - Admin API 參考
- [API 概覽](../api/01-overview.md) - CLI / HTTP 連線方式
- [資源訪問控制（ACL）](./15-acl.md) - account 內資源授權、繼承和檢索過濾
- [ACL API](../api/12-acl.md) - HTTP、SDK 和 CLI 接口
- [資料加密](./10-encryption.md) - 多租戶下的靜態資料加密
- [多租戶示例](https://github.com/volcengine/OpenViking/blob/main/examples/multi_tenant/README.md) - 完整管理流程示例
- [OpenClaw 插件](https://github.com/volcengine/OpenViking/blob/main/examples/openclaw-plugin/README_CN.md) - OpenClaw 的接入方式
- [Vikingbot](https://github.com/volcengine/OpenViking/blob/main/bot/README_CN.md) - bot 的多使用者接入方式
