---
description: 查詢 OpenViking 閘道器的配置欄位、環境變數、上下文配置設定和上游設定。
---

# OpenViking 閘道器配置參考

本頁供修改 `ov.conf`、`gateway.conf` 或環境變數的運維人員查閱，也方便把 Studio 中的名稱對應到管理 API 的欄位名。每張表都列出名稱、預設值和可選值；設定的作用和什麼時候需要改，見各節連結的功能頁面。

## 配置放在哪裡 {#configuration-reference}

嵌入閘道器和獨立閘道器的欄位大部分相同，區別在於寫在哪個檔案裡、用什麼命令生成。只有一種部署形態使用的欄位，在[閘道器欄位](#gateway-fields)的“適用於”一列中標出。

| | 嵌入 | 獨立 |
| --- | --- | --- |
| 檔案 | `ov.conf` 的 `gateway` 段 | `gateway.conf` 的根層，沒有 `gateway` 外層 |
| 生成命令 | `openviking-server init` | `openviking-gateway init` |
| 讀取哪個檔案 | Server 自己的 `ov.conf` | `--config` 或 `OPENVIKING_GATEWAY_CONFIG_FILE` 指定的檔案，且檔案必須存在；兩者都沒設定時，讀取 `~/.openviking/gateway.conf` 和 `/etc/openviking/gateway.conf` 中第一個存在的檔案 |
| host、port 和 workers | 跟隨 Server | 由 `host`、`port`、`workers` 欄位設定 |

`OPENVIKING_CONFIG_FILE` 只用來選擇 Server 的配置，不會讓獨立閘道器讀取它指向的檔案。

## 閘道器欄位 {#gateway-fields}

| 欄位 | 適用於 | 預設值 | 可選值 | 含義 |
| --- | --- | --- | --- | --- |
| `enabled` | 嵌入 | `false` | | 在 Server 中開啟閘道器 |
| `openviking_url` | 獨立 | —（必填） | HTTP(S) URL | OpenViking Server 的地址 |
| `host` | 獨立 | `127.0.0.1` | | 監聽地址 |
| `port` | 獨立 | `1935` | 1–65,535 | 監聽埠 |
| `workers` | 獨立 | `1` | 1–64 | worker 程序數 |
| `keep_alive_seconds` | 獨立 | `75` | 大於 0 | 兩次請求之間保留空閒 HTTP 連線的秒數；應大於負載均衡器的後端空閒超時 |
| `public_url` | 兩者 | 空 | HTTP(S) URL，不帶 `/gateway` | 客戶端訪問的對外地址，`/gateway` 由閘道器自己加。為空時，嵌入閘道器沿用 Server 的對外地址；兩者都沒有時，接入指南使用請求來源地址，MCP 檔案上傳和下載也不可用（`mcp_file_links` 為 `direct` 時除外）。見[對外地址](../guides/22-gateway-operations.md#public-address) |
| `mcp_file_links` | 兩者 | `proxy` | `proxy`、`direct` | MCP 上傳和下載工具返回的連結如何交給客戶端。`proxy` 改寫為 `public_url` 加 `/gateway/uploads` 或 `/gateway/downloads`，需要設定 `public_url`。`direct` 原樣透傳 OpenViking 的連結，需要 Server 的 `OPENVIKING_PUBLIC_BASE_URL`（或 `server.public_base_url`）是客戶端能訪問的地址 |
| `storage_path` | 兩者 | `~/.openviking/gateway` | | 本地儲存目錄 |
| `storage` | 兩者 | 兩個後端均為 `sqlite` | 見[儲存後端](#storage) | 分別選擇後端，共用 Redis 連線配置 |
| `encryption` | 獨立 | 不設定（明文） | 欄位同 `ov.conf` 的 `encryption` 段 | 加密本地儲存的資料，見[加密](../guides/22-gateway-operations.md#encryption)；嵌入閘道器沿用 Server 的設定 |
| `management_api` | 兩者 | `true` | `true`、`false` | 註冊閘道器管理路由；關閉時也移除獨立閘道器的 OpenViking 管理代理和 Studio，模型路由和 `/health` 繼續可用 |
| `management_key` | 兩者 | 空 | 至少 32 個字元 | 可選的[閘道器管理金鑰](../guides/22-gateway-operations.md#gateway-management-key) |
| `openviking_keys` | 兩者 | `false` | `true`、`false` | 允許客戶端用使用者的 OpenViking API 金鑰代替閘道器金鑰，使用帳號的預設上下文配置和全部已啟用的上游，見[直接使用 OpenViking API 金鑰](09-gateway-keys.md#openviking-keys) |
| `tenancy` | 兩者 | `account` | `account`、`key` | 按帳號或按金鑰隔離 OpenViking 金鑰請求；`key` 要求 `management_api: false` |
| `default_upstreams` | 兩者 | `{}` | 穩定 ID 到[上游設定](#upstream-settings)的物件對映 | 帳號沒有儲存上游時供 OpenViking 金鑰使用，見[部署預設上游](07-upstreams.md#deployment-default-upstreams) |
| `default_profile` | 兩者 | 內建上下文配置預設值 | [上下文配置設定](#context-profile-settings) | 帳號沒有 ID 為 `default` 的配置時使用，也是嵌入式 dev 模式初始化寫入的配置 |
| `min_server_version` | 兩者 | `0.4.16` | 版本號 | 獨立閘道器要求的 OpenViking Server 最低版本 |
| `session_ttl_seconds` | 兩者 | `2592000`（30 天） | 3600 及以上 | 對話閒置多少秒後過期；也決定快取的 OpenViking 金鑰及其使用者記錄的固定壽命 |
| `response_ttl_seconds` | 兩者 | `2592000`（30 天） | 60 及以上 | Responses 響應與上游的對應關係保留多少秒 |
| `request_log_sink` | 兩者 | `store` | `store`, `stdout` | 將請求和後臺儲存日誌寫入儲存，或以每條一行 JSON 寫到 stdout 並立即重新整理；見[觀測](../guides/22-gateway-operations.md#monitoring) |
| `log_retention_days` | 兩者 | `30` | 1 及以上 | 儲存中的請求日誌保留天數；stdout 的保留期限由日誌採集系統管理 |
| `max_body_bytes` | 兩者 | `33554432`（32 MiB） | 1,024 及以上 | 請求和上傳的大小上限，單位為位元組 |
| `upstream_timeout_seconds` | 兩者 | `600` | 大於 0 | 服務商請求超時 |
| `health_interval_seconds` | 兩者 | `60` | 1 及以上 | 檢查 OpenViking 狀態的間隔秒數 |
| `capture_concurrency` | 兩者 | `1` | 1 及以上 | 每個程序併發投遞的會話數；停機時停止新 claim，最多等待在途投遞 100 秒 |
| `client_rules` | 兩者 | `{}`（只用內建規則） | 見[客戶端規則](#client-rules) | 在閘道器內建的輔助請求和客戶端插入訊息識別規則上增刪條目 |

例如，獨立閘道器的 `gateway.conf` 可以在尚未配置任何帳號時路由 OpenViking 金鑰：

```json
{
  "openviking_url": "http://openviking:1933",
  "openviking_keys": true,
  "default_upstreams": {
    "ark-chat": {
      "name": "Ark Chat",
      "protocol": "chat",
      "base_url": "https://ark.cn-beijing.volces.com/api/v3",
      "api_key": "$ARK_API_KEY",
      "models": ["your-model-id"]
    }
  },
  "default_profile": {"max_tokens": 2400}
}
```

## 儲存後端 {#storage}

預設使用本地 SQLite，無需外部服務。`storage.kernel` 和 `storage.management` 分別選擇 `sqlite` 或 `redis`；Redis 後端共用一個客戶端及 `storage.redis` 連線配置。使用 Redis 時安裝 `pip install "openviking[expiry]"`，官方映象已經包含依賴。閘道器 CI 覆蓋 Redis 單機和 Cluster；Sentinel 配置可以通過校驗，但不在閘道器 CI 覆蓋範圍內。

```json
{
  "storage": {
    "kernel": "redis",
    "management": "redis",
    "key_prefix": "ovgw:",
    "redis": {
      "mode": "standalone",
      "endpoints": ["rediss://redis.example.com:6379"],
      "username": "gateway",
      "password_env": "OPENVIKING_GATEWAY_REDIS_PASSWORD",
      "pool_size": 32,
      "command_timeout_ms": 5000
    }
  },
  "session_ttl_seconds": 604800
}
```

`OPENVIKING_GATEWAY_STORAGE` 接受相同 `storage` 物件的 JSON。密碼通過指定的環境變數注入，例如來自 Kubernetes Secret。`key_prefix` 預設為 `ovgw:`，不能包含 `{`、`}`、`*`、`?`、`[`、`]` 或 `\`；所有鍵都以該字首加 `v1:` 開頭。不同部署使用不同字首。

`storage.redis` 複用 OpenViking 的 `RedisCacheConfig`：`mode`、`endpoints`、`username`、`password_env`、舊式 `password`、`db`、`pool_size`、`connect_timeout_ms`、`command_timeout_ms`、`default_ttl_seconds`、`tls_insecure_skip_verify`，以及 Sentinel 欄位 `master_name`、`sentinel_username`、`sentinel_password_env`、`sentinel_password`。為容納較大的對話值，閘道器把命令超時預設值從 20 改為 5000 毫秒；`default_ttl_seconds` 不控制閘道器保留期限。URL 只包含協議、主機和埠，憑據和資料庫使用專門欄位。Cluster 使用 `mode: "cluster"`、多個種子地址和 `db: 0`。TLS 由 `rediss://` 協議決定；私有 CA 通過證書卷和指向證書的 `SSL_CERT_FILE` 配置（Helm 使用 `extraVolumes`、`extraVolumeMounts`）。

為閘道器單獨準備 Redis 例項，使用 `volatile-lru` 驅逐策略並啟用 AOF；`redis.conf` 設定和監控項見 [Redis 記憶體策略](../guides/22-gateway-operations.md#redis-memory-policy)。

替換密碼和字首後，執行以下命令建立 ACL 使用者。Cluster 必須在**每個節點**分別執行，因為 ACL 不在節點之間同步：

```bash
redis-cli ACL SETUSER gateway reset on '>replace-with-secret' '~ovgw:*' \
  +@read +@write +@scripting +@connection +@transaction +ping +time +scan +unlink
```

Cluster 還需授予 `'+cluster|slots' '+cluster|shards'`。Lua 指令碼需要 `+time`；CI 會驗證這些許可權及字首隔離。應用命令遇到連線錯誤不會自動重試，因為失敗的寫入可能已經到達 Redis。

## 環境變數 {#environment-variables}

每個閘道器欄位都能用環境變數設定，變數名是 `OPENVIKING_GATEWAY_` 加上大寫的欄位名，兩種部署形態都適用：

```bash
OPENVIKING_GATEWAY_PUBLIC_URL=https://ov.example.com
OPENVIKING_GATEWAY_MANAGEMENT_KEY='<management-key>'
```

- **環境變數優先於配置檔案。** 非空的環境變數覆蓋檔案中的值，值為空等於沒有設定。
- 以 `tcp://` 或 `udp://` 開頭的值會被忽略。這樣，Kubernetes 為名為 `openviking-gateway` 的 Service 自動注入的變數（例如 `OPENVIKING_GATEWAY_PORT=tcp://…`）不會覆蓋檔案。
- 檔案中的值也可以寫成 `"$VAR"`，從環境變數中取值。
- `encryption` 塊只能寫在檔案裡。
- `client_rules`、`storage`、`default_upstreams` 和 `default_profile` 用 JSON 傳整段配置，例如 `OPENVIKING_GATEWAY_CLIENT_RULES='{"auxiliary_patterns":{"add":["You are the Acme title writer"]}}'` 或 `OPENVIKING_GATEWAY_DEFAULT_PROFILE='{"max_tokens":2400}'`。
- 容器通常不需要配置檔案，用環境變數設定需要的欄位即可。

## 校驗 {#validation}

| 物件 | 規則 |
| --- | --- |
| `openviking_url` 和 `public_url` | 必須是 HTTP(S)，不能含憑證、查詢引數或 fragment |
| 上游的 `base_url` | 規則不同，見[介面](07-upstreams.md#endpoint) |
| `management_key` | 解析 `$VAR` 引用後至少 32 個字元；`$VAR` 沒能解析時校驗失敗 |
| `tenancy` | `key` 要求 `management_api: false`；`openviking_keys` 關閉時此欄位不生效 |
| `client_rules` | 新增的模式必須是合法的 Python 正規表示式；新增的標籤名以英文字母開頭，只能包含英文字母、數字、`_`、`.`、`:` 和 `-` |
| 未知欄位 | 校驗失敗 |
| 已刪除的欄位 | 忽略，啟動時列印警告：`encryption_key_env`、`session_ttl_days`（已由 `session_ttl_seconds` 取代），以及 `ov.conf` 中[遷移](../guides/22-gateway-operations.md#migration)列出的 v0.5 欄位 |

## 客戶端規則 {#client-rules}

閘道器靠固定文本區分[輔助請求](10-overview-and-requests.md#request-types)、客戶端代使用者插入的訊息和真正的使用者訊息，這些文本列在內建的 [`client-rules.json`](https://github.com/volcengine/OpenViking/blob/main/openviking_gateway/client-rules.json) 裡。如果某個客戶端的標題、摘要請求在請求日誌裡顯示為**新訊息**，或者真實訊息被當成了輔助請求，可以在 `client_rules` 裡增刪條目：

```json
{
  "gateway": {
    "enabled": true,
    "client_rules": {
      "auxiliary_patterns": {
        "add": ["You are the Acme title writer"],
        "remove": ["Create a short.{0,40}title"]
      },
      "noise_tags": { "add": ["acme-context"] }
    }
  }
}
```

在 `gateway.conf` 裡，`client_rules` 直接寫在根層級，不需要外面的 `gateway`。

| 列表 | 條目 | 命中後的效果 |
| --- | --- | --- |
| `auxiliary_patterns` | 正規表示式，不區分大小寫 | 分別與 Messages 的 `system` 欄位、Responses 的 `instructions` 和最後一條使用者訊息匹配，命中的請求算作**輔助請求**。Chat Completions `messages` 和 Responses `input` 裡的 system、developer 訊息不參與匹配，這類客戶端要匹配使用者訊息裡的文本。 |
| `noise_patterns` | 正規表示式，區分大小寫 | 閘道器讀取對話時忽略這些文本：不參與請求分類和記憶檢索，也不寫入儲存的訊息和工具結果，但仍原樣發給模型。刪完為空的使用者訊息不算新使用者訊息，請求按同一輪的延續處理。 |
| `noise_tags` | 標籤名 | `<tag …>…</tag>` 塊（不區分大小寫），處理方式同 `noise_patterns`。 |
| `plugin_tags` | 標籤名 | 系統提示詞或客戶端訊息中出現 `<tag`，表示客戶端裡執行著 OpenViking 記憶外掛。該對話此後閘道器只做轉發：不加記憶、不提供 OpenViking 工具、不儲存（見[兩者同時使用時](../guides/15-gateway.md#when-both-are-in-use)）。只新增外掛自己寫入的標籤。 |

- **`add` 追加到內建列表，`remove` 從內建列表中去掉條目。** `remove` 的條目要和 `client-rules.json` 裡的寫法完全一致。沒有匹配到任何條目的 `remove`（例如升級後內建條目改了寫法）會被忽略，啟動時列印警告。內建列表不能整體替換，這樣後續版本新增的條目仍然生效。
- **只匹配客戶端自己寫的文本。** 用客戶端自己提示詞裡的整句，不要用短語。使用者訊息一旦命中，這一整輪都算輔助請求，不檢索也不儲存；如果模式還能命中主對話的系統提示詞，對話裡的每個請求都會這樣。噪聲模式要錨定整條訊息（JSON 裡寫作 `"\\A…\\Z"`），避免從真實訊息裡刪掉文字。
- **修改在啟動時生效。** 改完後重啟 Server 或獨立閘道器。

## 上下文配置的設定 {#context-profile-settings}

在 Studio 中：**上下文配置** → 開啟一份配置。下面幾張表按編輯器的分割槽排列，先寫 Studio 中的名稱，再寫管理 API 中的名稱（管理 API 把上下文配置稱為 `policies`）。**名稱**（`name`，預設 `Default`）是配置的顯示名稱；各分割槽的作用見[上下文配置](08-context-profiles.md#context-profiles)。**允許客戶端覆蓋設定**（`client_overrides`，預設 `true`）允許客戶端用 `X-OpenViking-Context` 請求頭為新對話修改其餘所有設定，見[允許客戶端覆蓋設定](08-context-profiles.md#client-overrides)。

### 召回記憶 {#profile-recall}

作用見[召回記憶](08-context-profiles.md#recall-memory)。

| Studio 名稱 | API 名稱 | 預設值 | 取值範圍 | 含義 |
| --- | --- | --- | --- | --- |
| 召回記憶 | `recall` | `true` | | 為每條新的使用者訊息檢索記憶。 |
| 會話開頭提供使用者畫像 | `profile` | `true` | | 新對話開始時提供畫像，獨立於召回。 |
| 開頭內容預算 | `profile_max_tokens` | `4000` | 0–32,000 | 畫像和目錄的獨立預算；0 表示省略。目錄需要提供 OpenViking 的 `read` 工具（`openviking_read`）。 |
| 顯示召回摘要 | `show_recall` | `false` | | 在回覆開頭說明 OpenViking 補充了什麼，或召回失敗的原因。模型看不到。 |
| 檢索範圍 | `context_types` | `memory`、`resource`、`skill` | 開啟召回時至少一個（僅 Studio 校驗） | 檢索哪些內容：記憶、資源、技能。 |
| 單條訊息預算 | `max_tokens` | `1600` | 64–32,000 | 一條訊息最多補充的 token 數。 |
| 單個上下文視窗預算 | `session_max_tokens` | `30000` | 0 及以上 | 一個上下文視窗內最多補充的 token 數，每次壓縮後重新計算；0 表示關閉召回。 |
| 相關度閾值 | `score_threshold` | `0.35` | 0–1 | 接受的最低相關度分數。 |
| 超時時間 | `recall_timeout` | `2`（秒） | 大於 0，最多 30 | 檢索最多等多久，超時後訊息不帶記憶繼續傳送。 |
| 檢索文本長度 | `query_max_chars` | `8000` | 3–32,000 | 取訊息的多少個字元作為檢索文本。 |
| 按分類限量 | `quotas` | `{}`（關閉） | 鍵：`events`、`entities`、`preferences`、`experiences`、`resources`、`skills`；設定時至少一項大於 0（僅 Studio 校驗） | 每個分類最多取的條數；只檢索大於 0 的分類。 |

管理 API 儲存 `context_types` 和 `quotas` 的鍵時不做校驗。`quotas` 裡出現未知的鍵時，OpenViking 會拒絕檢索請求，導致每次召回都失敗。

### 儲存對話 {#profile-saving}

作用見[儲存對話](08-context-profiles.md#save-conversations)。

| Studio 名稱 | API 名稱 | 預設值 | 取值範圍 | 含義 |
| --- | --- | --- | --- | --- |
| 儲存對話 | `capture` | `true` | | 把完成的輪次儲存到 OpenViking。 |
| 最新回覆等待時長 | `idle_seconds` | `600`（秒） | 1 及以上 | 停頓多久之後儲存最後一輪並提交會話。 |
| 提交閾值 | `commit_tokens` | `20000` | 1 及以上 | 會話中待提交的 token 數達到這個值時提交。 |
| 保留最近訊息 | `keep_recent_messages` | `10` | 0–1,000 | 提交後會話中保留的訊息數。 |

### 長對話 {#profile-long-conversations}

作用見[閘道器中的長對話](05-long-conversations.md#long-conversations)。

| Studio 名稱 | API 名稱 | 預設值 | 取值範圍 | 含義 |
| --- | --- | --- | --- | --- |
| 壓縮 | `compaction` | `true` | | 接近上下文視窗時，用摘要替換對話較早的部分。 |
| 壓縮時機 | `compaction_threshold` | `0.9` | 0.5–0.98 | 上下文視窗用到多大比例時壓縮。 |
| 摘要長度上限 | `summary_max_tokens` | `8000` | 1,000–32,000 | 一份摘要最多多少 token。 |
| 預設上下文視窗 | `context_window` | 未設定（按 1,000,000 計算） | 1,024 及以上 | 上游沒有列出該模型時使用的視窗，見[設定模型的上下文視窗](05-long-conversations.md#context-window)。 |
| Agent 自管上下文視窗 | `agent_windows` | `false` | | 實驗性。讓模型自己開啟新的上下文視窗；需要 OpenViking 工具。 |
| 軟提醒時機 | `window_soft_ratio` | `0.7` | 0.3–0.95，須低於 `window_hard_ratio` | 視窗用到這個比例時，提醒模型儘快開啟新視窗。 |
| 硬提醒時機 | `window_hard_ratio` | `0.85` | 0.4–0.97 | 視窗用到這個比例時，要求模型立即開啟新視窗。 |

### OpenViking 工具 {#profile-tools}

作用見[選擇工具](04-openviking-tools.md#choose-tools)和[上限](04-openviking-tools.md#limits)。

| Studio 名稱 | API 名稱 | 預設值 | 取值範圍 | 含義 |
| --- | --- | --- | --- | --- |
| OpenViking 工具 | `gateway_tools` | `true` | | 為 Chat Completions、完整歷史的 Responses 和 Anthropic Messages 提供 OpenViking 工具。 |
| 工具（未勾選的項） | `disabled_tools` | 會修改資料的 8 個工具 | OpenViking 工具原名，不帶 `openviking_` | 新對話不提供這些工具，其餘可用工具都提供，包括以後新增的。 |
| 顯示工具呼叫 | `show_tool_calls` | `true` | | 每次 OpenViking 工具呼叫都在回覆里加一行提示。 |
| 每次請求的工具輪數 | `tool_max_rounds` | `null`（不限） | 1 及以上 | 工具呼叫達到這個輪數後，拒絕繼續呼叫 OpenViking 工具。 |
| 單次呼叫超時 | `tool_timeout_seconds` | `30`（秒） | 大於 0，最多 120 | 超時的呼叫向模型返回錯誤。 |
| 結果大小上限 | `tool_result_bytes` | `65536`（位元組） | 1,024–1,048,576 | 超出部分在交給模型前截掉。 |
| 總時長 | `tool_total_seconds` | `null`（不限） | 大於 0 | 超過這個秒數模型仍在呼叫工具時，請求失敗。 |
| Token 預算 | `tool_total_tokens` | `null`（不限） | 1,024 及以上 | 工具呼叫和結果在一次請求中最多增加的估算 token 數，用完後拒絕繼續呼叫 OpenViking 工具。 |

API 請求省略 `disabled_tools` 時使用預設列表；列表為空且 `gateway_tools` 開啟時，提供全部可用工具。

## 上游設定 {#upstream-settings}

在 Studio 中：**上游** → 開啟一個上游。下面幾張表按編輯器的四個分割槽排列；各欄位的作用見[上游](07-upstreams.md#upstreams)。

### 介面 {#upstream-endpoint}

| Studio 名稱 | API 名稱 | 預設值 | 可選值 | 含義 |
| --- | --- | --- | --- | --- |
| 名稱 | `name` | —（必填） | | 顯示名稱。 |
| 服務商 | `vendor` | `generic` | `generic`、`anthropic`、`openai`、`deepseek`、`ark`（火山方舟）、`byteplus`（BytePlus 方舟） | Studio 只提供服務商支援的協議，API 接受任意組合。 |
| 協議 | `protocol` | —（必填） | `anthropic`（Anthropic Messages）、`chat`（Chat Completions）、`responses`（Responses） | 這個上游使用的 API。 |
| Base URL | `base_url` | —（必填） | HTTP(S) URL | 服務商地址；預設地址見[什麼是上游](07-upstreams.md#upstreams)，拼接規則見[介面](07-upstreams.md#endpoint)。 |
| 拼接協議介面路徑 | `append_endpoint_path` | `true` | | 拼接所選協議的介面路徑；關閉時把 `base_url` 直接作為完整請求地址。 |

### 憑證 {#upstream-credentials}

| Studio 名稱 | API 名稱 | 預設值 | 可選值 | 含義 |
| --- | --- | --- | --- | --- |
| API Key 由誰提供 | `auth_mode` | `managed` | `managed`（由閘道器保管 API Key）、`passthrough`（每個客戶端自帶 API Key） | 見[憑證](07-upstreams.md#credentials)。 |
| 金鑰傳送方式 | `key_header` | `authorization` | `authorization`（Bearer）、`api-key`、`x-api-key` | `base_url` 含 `{api_key}` 時不生效。 |
| API Key | `api_key` | 空 | | 只寫，見[憑證](07-upstreams.md#credentials)。 |
| 額外請求頭 | `headers` | `{}` | 請求頭名稱 → 取值 | 只寫，見[憑證](07-upstreams.md#credentials)。 |
| 這是 Coding Plan 或訂閱金鑰 | `coding_plan` | `false` | | 除非另外允許，否則拒絕發往這個上游的請求。 |
| 允許通過閘道器使用這個套餐 | `allow_coding_plan` | `false` | | 允許使用被標記為 Coding Plan 的金鑰。 |

### 模型 {#upstream-models}

| Studio 名稱 | API 名稱 | 預設值 | 可選值 | 含義 |
| --- | --- | --- | --- | --- |
| 模型 | `models` | `[]` | 模型名 | 提供的模型名；留空表示接受任何名稱。 |
| 模型別名 | `aliases` | `{}` | 客戶端使用的名稱 → 發給上游的模型 | |
| 上下文視窗 | `context_windows` | `{}` | 模型 → token 數，每項至少 1,024 | 各模型的上下文視窗，見[設定模型的上下文視窗](05-long-conversations.md#context-window)。 |

### 路由 {#upstream-routing}

| Studio 名稱 | API 名稱 | 預設值 | 可選值 | 含義 |
| --- | --- | --- | --- | --- |
| 優先順序 | `priority` | `0` | 整數 | 數值越大，新對話越優先使用。 |
| 啟用 | `enabled` | `true` | | 停用的上游不接收請求。 |
| 允許 OpenViking 工具 | `allow_gateway_tools` | `true` | | 能否通過這個上游提供 OpenViking 工具。 |
| 補全推理內容回傳 | `replay_reasoning` | `null`（跟隨服務商） | `null`、`true`、`false` | 把客戶端丟掉的推理內容補回之前的回覆。`null` 時 `deepseek`、`ark` 和 `byteplus` 開啟，其他服務商關閉；`true` 或 `false` 覆蓋服務商預設值。Studio 中開關與服務商預設值一致時儲存為 `null`。 |
| 最小可快取長度 | `cache_min_tokens` | `1024` | 0 及以上 | 僅火山方舟和 BytePlus 方舟；影響快取資格的報告。 |

## 下一步 {#next-steps}

- [獨立部署](../guides/22-gateway-operations.md#standalone-deployment)：生成 `gateway.conf`，單獨執行閘道器。
- [在 Server 中啟用](../guides/22-gateway-operations.md#enable-it-in-the-server)：在 `ov.conf` 中開啟嵌入閘道器。
- [上下文配置](08-context-profiles.md)和[上游](07-upstreams.md)：用 Studio 的說法解釋上面這些設定的作用。
- [管理 API](../api/25-gateway.md)：閘道器金鑰的欄位、全部管理操作、許可權規則和錯誤原因。
