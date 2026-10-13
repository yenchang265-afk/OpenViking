# MCP 工具與協議

OpenViking Server 內建 [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) 端點。支援 Streamable HTTP 的客戶端可直接連線；只支援 stdio 的客戶端可使用 [Agent Plugins 包](../agent-integrations/15-agent-plugins.md)提供的代理。

> **快速接入？** 見 [MCP 客戶端](../agent-integrations/06-mcp-clients.md) 獲取各平臺配置片段和注意事項。本頁面覆蓋完整的工具參考和進階配置。

## 前提條件

準備可訪問的 OpenViking 服務地址和對應憑證。需要自行部署時，先完成[快速開始](../getting-started/02-quickstart.md)；使用託管服務或已有部署時，無需在本地安裝服務端。

MCP 端點位於 `http://<server>:1933/mcp`，與 REST API 同進程、同埠。

## 客戶端接入

下表列出已有接入配置。連線後，用當前客戶端版本確認能發現工具，並讀取一項有許可權的資料：

| 平臺 | 接入方式 |
|------|----------|
| **Claude Code** | `type: http` 接入 |
| **Trae** | 標準 MCP 配置 |
| **Cursor** | 標準 MCP 配置 |
| **ChatGPT** | 通過自定義 App 接入 OAuth，見 [OAuth 指南](11-oauth.md) |
| **Codex** | 使用 [Codex 整合](../agent-integrations/04-codex.md)中的 MCP 配置 |
| **OpenCode** | OpenCode 原生 `mcp` 配置 |
| **Manus** | 標準 MCP 配置 |
| **Claude.ai / Claude Desktop** | 原生 OAuth 2.1（見 [11-oauth](11-oauth.md)） |

## 鑑權方式

MCP 使用服務端認證配置。API Key 模式下，用 User/Admin key 傳入以下任一 header：

- `X-Api-Key: <your-key>`
- `Authorization: Bearer <your-key>`

只有 `dev` 模式無需認證，監聽 localhost 本身不會關閉認證。OAuth 客戶端使用下文授權流程，其他模式見[認證指南](04-authentication.md)。

## 客戶端配置

### 通用 MCP 客戶端

支援 `mcpServers` 配置且允許自定義請求頭的客戶端，可參考以下示例。欄位名和傳輸型別以客戶端文件為準：

```json
{
  "mcpServers": {
    "openviking": {
      "url": "https://your-server.com/mcp",
      "headers": {
        "Authorization": "Bearer your-api-key-here"
      }
    }
  }
}
```

### Claude Code

Claude Code 需要額外指定 `"type": "http"`。可通過命令列新增：

```bash
claude mcp add --transport http openviking \
  https://your-server.com/mcp \
  --header "Authorization: Bearer your-api-key-here"
```

或在 `.mcp.json` 中手動配置：

```json
{
  "mcpServers": {
    "openviking": {
      "type": "http",
      "url": "https://your-server.com/mcp",
      "headers": {
        "Authorization": "Bearer your-api-key-here"
      }
    }
  }
}
```

加 `--scope user` 可將配置設為全域（所有專案共享）。

### OpenCode

在 `~/.config/opencode/opencode.json` 中配置：

```json
{
  "mcp": {
    "openviking": {
      "type": "remote",
      "url": "https://your-server.com/mcp",
      "enabled": true,
      "oauth": false,
      "headers": {
        "Authorization": "Bearer your-api-key-here"
      }
    }
  }
}
```

### Claude.ai / Claude Desktop（OAuth）

通過 Claude.ai / Claude Desktop 的遠端連接器介面接入時，使用下文 OAuth 流程。OpenViking 已經原生實現 OAuth 2.1（DCR + PKCE + opaque token，SQLite 後端，配合 Studio consent 授權頁），不再需要外部代理。

按 OAuth 指南在服務端啟用 `oauth.enabled` 並配置 HTTPS，再讓客戶端連線 `https://your-server.com/mcp`，在瀏覽器中完成授權。

**詳見 [OAuth 2.1 接入指南](11-oauth.md)** 和 **[公網訪問指南](12-public-access.md)**：

- Studio 授權確認流程，以及可選的 6 字元碼跨裝置授權
- HTTP（本地）與 HTTPS（生產）兩階段部署，包含 Caddy / nginx 反代模板和 docker-compose 示例
- Claude.ai / Claude Desktop 接入步驟
- `OPENVIKING_PUBLIC_BASE_URL` 與 `oauth` 配置項
- Token 模型（`ovat_` / `ovrt_` / `ovac_` 字首）與撤銷


## 可用的 MCP 工具

以下列出內建 MCP 工具。實際可用工具以所連線服務的 `tools/list` 響應為準：

| 工具 | 說明 | 主要引數 |
|------|------|----------|
| `find` | 無 session 上下文的快速語義檢索。只傳 `context_type="skill"` 時改走包級 skill 檢索：每個 skill 包只返回一條命中，URI 指向該包的 `SKILL.md`，摘要取自 skill 本身，即使命中的是包內輔助檔案也是如此；不傳 `target_uri` 時同時檢索自己的 skill 和帳戶共享的 `viking://agent/skills`。`skill` 與其它 context_type 混用時仍走通用檢索路徑 | `query`, `target_uri`(可選), `limit`, `min_score`, `level`(可選), `context_type`(可選), `read_content`(可選——直接內聯每條命中的內容), `events_time_decay_protection`(可選) |
| `search` | 深度語義檢索；`mode="context"` 組裝可直接注入的上下文，並替代原 `recall` 工具。`list` 模式下每個 skill 包也只出一條命中，URI 指向 `SKILL.md`、摘要取自包本身，但 `limit` 在合併之前生效，所以一個包在多個檔案上命中時會佔掉多個名額，返回條數少於 `limit` | `query`, `mode`（`list` 或 `context`）, `target_uri`（僅 list 模式）, `session_id`(可選), `limit`, `min_score`, `level`（list 模式）, `context_type`(可選), `events_time_decay_protection`（兩種模式均可選），以及 context 模式的 `quotas`, `purpose`, `max_tokens`, `detail` 或 `detail_by_category`, `dedup_turns`, `exclude_uris`, `peer_scope`, 標量 `other_peer_penalty` 或按類別設定的 `other_peer_penalties`, `rewrite`（`off` 或 `auto`） |
| `read` | 讀取一個或多個 `viking://` URI 的內容。PNG、JPEG、GIF、WebP 返回 MCP 原生圖片內容；WAV、MP3、FLAC、OGG、M4A 返回原生音訊內容。MCP 沒有標準影片內容塊，因此暫不支援影片 | `uris`（單個字串或陣列）, `offset`, `limit`（文本行數） |
| `list` | 列出 `viking://` 目錄下的條目 | `uri`, `recursive`(可選) |
| `tree` | 以縮排形式展示 `viking://` URI 下的遞迴目錄樹——當需要全面瞭解檔案樹結構時使用（單層列表用 `list`，按檔名查詢用 `glob`） | `uri`(可選), `level_limit`(預設 3), `node_limit`(預設 1000), `include_abstract`(可選——同時展示每個目錄的摘要；skill 目錄的摘要就是它的名字和描述) |
| `remember` | 儲存訊息到長期記憶（觸發記憶提取） | `messages`（`{role, content}` 列表） |
| `write` | 向 `viking://` 檔案寫入文本（建立/覆蓋/追加）。自動建立缺失的父目錄；覆蓋前請先用 `read` 檢視當前內容；只改檔案區域性時優先用 `edit`。skill 包不要用它維護：呼叫方自己的 `skills/` 子樹會被拒絕，寫 `viking://agent/skills` 則生成繞過安裝流程的普通檔案，請改用 `add_skill` | `uri`, `content`, `mode`(可選:預設 `replace` — 覆蓋或在缺失時建立,`append` — 追加或在缺失時建立,`create` — 已存在則失敗), `wait`(可選,阻塞直到重建索引完成), `timeout`(可選), `acl`(可選) |
| `edit` | 在已有 `viking://` 檔案中把精確字串替換為新文本——用於區域性修改，避免整檔案重寫。若 `old_string` 找不到、或匹配多處且 `replace_all` 為 false，則編輯失敗且檔案保持不變。編輯 skill 包內的檔案不會重新觸發 skill 安裝流程，請改用 `add_skill` | `uri`, `old_string`, `new_string`, `replace_all`(可選), `wait`(可選,阻塞直到重建索引完成), `timeout`(可選) |
| `add_resource` | 新增本地檔案或 URL 作為資源(本地檔案觸發漸進式上傳流) | `path`, `temp_file_id`(可選), `description`(可選), `watch_interval`(可選,分鐘數 — 遠端 URL 的自動重新整理週期), `processing_mode`(可選：預設 `semantic_and_vectors`；傳 `vectors_only` 時跳過 VLM 語義理解，只向量化當前檔案), `to`(可選,目標 `viking://resources/...` URI；`watch_interval > 0` 時若省略 `to`,watch 將自動繫結到本次 add 建立的資源 URI), `args`(可選,特定 parser 引數，包括 `{"parse_mode":"no_split"}` 用於正常解析但每個源文件只生成一個 Markdown 正文) |
| `add_skill` | 新建、安裝或替換 agent skill。新 skill 直接傳完整 SKILL.md 文本；Git 與 GitHub tree URL 預設安裝源裡的全部 skill，可用 `skills` 挑選；本地 SKILL.md、目錄或 zip 會和 `add_resource` 一樣返回簽名上傳 URL | `data`（SKILL.md 文本）或 `path`（Git URL 或本地路徑）, `skills`(可選), `target_uri`(可選；`viking://agent/skills` 表示帳戶共享), `list_only`(可選) |
| `list_watches` | 列出當前 Agent 可見的 watch 任務（自動重新整理訂閱），每行顯示目標 URI、重新整理間隔（分鐘）、active/paused 狀態以及下一次排程時間 | 無 |
| `cancel_watch` | 按目標 URI 取消（刪除）watch 任務。若需調整重新整理週期或臨時暫停，請取消後使用新的 `watch_interval` 重新新增 | `to_uri`（必須匹配 watch 任務的 `to` 值，例如 `viking://resources/...`） |
| `grep` | 在 `viking://` 檔案中進行正則內容搜尋 | `uri`, `pattern`（字串或陣列）, `case_insensitive`, `node_limit` |
| `glob` | 按 glob 模式匹配檔案 | `pattern`, `uri`(可選範圍), `node_limit` |
| `forget` | 刪除任意 `viking://` URI（先用 `search` 查詢；刪除目錄需 `recursive=true`）。用它刪 skill 目錄會殘留該 skill 的 privacy 配置，請改用 `ov skills remove` 或 `DELETE /api/v1/skills/{name}` | `uri`, `recursive`（可選） |
| `health` | 檢查 OpenViking 服務健康狀態 | 無 |
| `list_users` | 查詢當前 account 的使用者 ID；預設不返回憑證，管理員也一樣 | `query`(可選，ID 子串), `limit`(預設 100), `page`(預設 1), `include_credentials`(預設 false，僅 ADMIN/ROOT 可設為 true) |
| `list_groups` | 查詢當前 account 的組 ID，不返回成員名單 | 無 |
| `get_acl` | 檢視共享資源的直接、繼承和有效 ACL；要求該節點的 manage 或帳號 ADMIN | `uri` |
| `set_acl` | 設定共享資源 ACL；按修改前的許可權校驗 manage | `uri`, `acl` |

在 MCP 工具中訪問自己的工作區，請使用家目錄別名 `viking://~`。它在所有控制面
（REST API、`ov` CLI、SDK 和 MCP）上都會展開為 `viking://user/<當前使用者>`，因此
`viking://~/notes/todo.md` 會解析成 `viking://user/<當前使用者>/notes/todo.md`。
響應始終回顯展開後的 canonical URI，這些 canonical URI 也可以直接作為工具入參使用。

無 uid 的寫法 `viking://user/<segment>/...`（`memories`、`resources`、`skills`、`peers`、
`privacy`、`sessions`）不再被接受，這類呼叫會報錯並提示改用 `viking://~/...`。
`viking://user` 本身是所有使用者空間的容器，而不是自己空間的快捷方式。詳見
[Viking URI](../concepts/04-viking-uri.md)。

> **注**：MCP 僅暴露 watch 管理的最小閉包（`list_watches` + `cancel_watch`）。pause / resume / trigger 和統一的 `update` 動作刻意不在此處暴露，請通過 REST `/api/v1/watches/*` 介面或 `ov task watch` CLI 使用上述操作。

> `processing_mode=vectors_only` 會跳過 VLM 語義理解階段，不生成或重新整理 `.abstract.md` / `.overview.md`；它只向量化當前非隱藏資源檔案，並保留已存在的舊語義產物。

### 資源許可權與授權物件

`list_users`、`list_groups` 對當前 account 的普通使用者開放，不接受跨 account 查詢引數。
`list_users` 預設僅返回 `user_id` 和匹配總數，`list_groups` 僅返回 `group_id`。
管理員也必須顯式傳 `include_credentials=true` 才會返回可用的憑證欄位；普通使用者傳該引數會得到
`PERMISSION_DENIED`，即使查詢結果為空也一樣。trusted 鑑權模式禁止返回憑證。
組成員管理和成員名單查詢仍使用管理員介面。

完整 ACL 的查詢和修改都要求資源的 `manage` 許可權；普通使用者即使是資源 manager，也不會因此獲得
讀取帳號憑證的許可權。`write` 和 `add_resource` 接受可選的 `acl` 引數，複用核心的許可權校驗：
已有目標要求自身 manage，新目標要求從父目錄繼承 manage。不傳 ACL 時，已有目標保留原許可權，新目標繼承父目錄。
`add_resource` 的遠端匯入、臨時檔案匯入、本地檔案上傳後自動匯入均保留這個引數。

例如，將已有共享資料只授權給 Bob 讀取：

```json
{
  "uri": "viking://resources/project-a",
  "acl": {
    "acl_mode": "restricted",
    "entries": [{"principal": "user:bob", "level": "read"}]
  }
}
```

以上為 `set_acl` 的引數。`entries` 完整替換直接授權，省略則保留；`acl_mode=inherit` 合併父級授權，
`restricted` 只使用直接授權。重置為繼承使用 `{"acl_mode":"inherit","entries":[]}`。
受限 ACL 可能移除操作者自身的訪問許可權；帳號 ADMIN 始終保留治理許可權。

工具執行失敗會標記 MCP `isError=true`，業務錯誤文本保留 `PERMISSION_DENIED` 等錯誤碼；
支援結構化輸出的工具還返回 `error.code/message/details`，同時保留原有 `result` 文本。
批次讀取或搜尋部分失敗時保留成功結果，並在失敗項中顯示原因。

### 新增本地檔案資源(單步上傳)

`add_resource` 工具同時接受**遠端 URL** 和**本地檔案路徑**。兩者的處理路徑不同:

- **遠端 URL**(`http(s)://`、`git@`、`ssh://`、`git://`):一次呼叫即完成,server 直接拉取併入庫。
- **本地檔案路徑**:返回**上傳指令**(純文本)。agent 把檔案以 `multipart/form-data`(欄位名 `file`)POST 到響應裡給出的 `temp_upload` URL。該 URL 內嵌一次性 token(預設 10 分鐘過期)作為鑑權憑證,無需 API Key。Server 隨後自動提交匯入並返回受理結果，後臺處理可以繼續進行；agent **無需**再次呼叫 `add_resource`。

在 `api_key` 鑑權模式下，token 保留髮起 MCP 呼叫時的角色，API Key 和 OAuth 呼叫均適用。上傳時會檢查使用者是否仍存在、是否正在刪除，以及角色是否已降級；不滿足條件時拒絕上傳。角色後來被提升也不會擴大舊 token 的許可權。trusted 模式的 token 仍按 USER 身份處理。

客戶端只要能讀取原始檔併發出 multipart HTTP 請求，就能上傳，無需預裝 `ov` CLI。沙箱也需要提供這兩項能力，僅傳入無法讀取的本地路徑不能完成檔案傳輸。token 上傳複用認證版的 `temp_upload` 路由(API Key 優先,否則走一次性 `?token=`)及其 `TempUploadStore` 持久化,所以 `local` / `shared` 上傳模式行為一致。注意:一次性 token 儲存在程序內,因此多 worker 部署下 `add_resource` 呼叫與後續的上傳 POST 必須落到同一個 worker(或以單 worker 執行),token 才能被解析。

#### 必須配置 `OPENVIKING_PUBLIC_BASE_URL` 的場景

工具響應裡給出的上傳 URL,server 端按以下順序解析:

1. 環境變數 `OPENVIKING_PUBLIC_BASE_URL`
2. `ov.conf` 中的 `server.public_base_url`
3. 請求頭 `X-Forwarded-Host` / `X-Forwarded-Proto`(由反代鏈轉發)
4. 請求頭 `Host`(直連場景)
5. 監聽地址兜底 `http://{host}:{port}`

只要 server 部署在反向代理(nginx / cloud LB / k8s ingress)後,**強烈建議顯式配置 `OPENVIKING_PUBLIC_BASE_URL`**。後兩層是兜底推斷,在以下情況會失敗:

- 反代/MCP proxy 不轉發 `X-Forwarded-*` 頭
- server 監聽 `0.0.0.0`(fallback URL 含 `0.0.0.0`,agent 無法連線)
- 多層代理存在 host 重寫

未配置該變數且 fallback 推斷生效時,工具響應末尾會自動附帶提示,告知使用者在 server 端設定該環境變數。Docker Compose 部署示例:

```yaml
services:
  openviking:
    # 推薦優先使用 ghcr.io；如果訪問有問題，可改用 openviking-cn-beijing.cr.volces.com/volcengine/openviking:latest
    image: ghcr.io/volcengine/openviking:latest
    environment:
      OPENVIKING_PUBLIC_BASE_URL: "https://ov.your-domain.com"
```

## 故障排除

### 連線被拒絕

**可能原因：** `openviking-server` 未執行，或執行在不同埠上。

**解決方案：** 驗證伺服器是否正在執行：

```bash
curl http://localhost:1933/health
# 預期返回：{"status": "ok"}
```

### 認證錯誤

**可能原因：** 客戶端的 API Key 無效、已過期，或不適用於租戶資料訪問。

**解決方案：** 確認客戶端使用目標 account 的有效 user/admin key；`api_key` 模式下，root key 只用於管理介面。參見[認證指南](04-authentication.md)。

## 參考

- [MCP 規範](https://modelcontextprotocol.io/)
- [OpenViking 配置](01-configuration.md)
- [OpenViking 部署](03-deployment.md)

客戶端配置參考：[Claude Code MCP](https://code.claude.com/docs/en/mcp)、[OpenCode MCP servers](https://opencode.ai/docs/mcp-servers/)。
