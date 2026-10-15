---
description: 用 Docker Compose、Helm 或獨立程序部署 OpenViking 閘道器，在 Studio 中管理閘道器並排查問題。
---

# OpenViking 閘道器部署與運維

本頁寫給執行 OpenViking 閘道器的人：怎麼部署，怎麼在 Studio 中管理上游、上下文配置和金鑰，資料存在哪裡、怎麼備份，以及出了問題怎麼查。閘道器能做什麼、客戶端怎麼接入，見[OpenViking 閘道器](15-gateway.md)；整體結構見[一張圖看懂架構](15-gateway.md#一張圖看懂架構)。

閘道器目前處於 Beta 階段，設定和介面可能隨版本調整，升級前請先讀釋出說明。

## 環境要求

- **OpenViking 的認證方式**：`api_key` 或本地 dev 模式。閘道器不支援 trusted 認證。
- **OpenViking 版本**：嵌入執行時和 Server 同版本釋出，無需額外檢查；獨立執行時要求 OpenViking Server 0.4.16 或更高版本。
- **安裝**：閘道器包含在 OpenViking 核心包中。可選的 `gateway-fast` extra（`pip install "openviking[gateway-fast]"`）裝上更快的事件迴圈和 HTTP 解析器。
- **登入身份**：遠端部署需要 OpenViking API 金鑰，普通使用者、帳號管理員和 root 都能登入 Studio 的閘道器頁面。本地 dev 模式不需要金鑰，固定使用 `default/default` 身份。
- **儲存**：本地磁碟。閘道器的 SQLite 資料庫只供一臺主機使用，不支援網路檔案系統或跨主機共享儲存。

## 金鑰和憑證

閘道器涉及四種金鑰，各管一件事：

| 金鑰 | 用途 | 在哪裡使用 |
| --- | --- | --- |
| OpenViking API 金鑰 | 登入 Studio；決定以哪個帳號、哪個使用者的身份讀寫記憶 | 管理請求的 `X-API-Key` 或 `Authorization: Bearer` |
| 閘道器金鑰（`ovgw_…`） | 客戶端接入；每把繫結一位使用者、一份上下文配置和一組上游 | 客戶端的 API Key 輸入框 |
| 閘道器管理金鑰（可選） | 限制誰能修改上游和上下文配置 | `gateway.management_key`；請求頭 `X-OpenViking-Gateway-Management-Key` |
| 上游 API Key | 呼叫模型服務商 | 上游編輯頁 |

閘道器沒有自己的加密金鑰，本地儲存按 OpenViking 的加密配置加密，見[加密](#加密)。

### 閘道器管理金鑰

不設定管理金鑰時，帳號內每個登入的使用者都能新增和修改本帳號的上游和上下文配置。設定之後，只有帶上這把金鑰的請求能修改它們，OpenViking 的 admin 和 root 也不例外；其他人只能檢視、測試，並在簽發金鑰時選用。管理金鑰不限制誰能登入，也不限制使用者給自己簽發閘道器金鑰。完整的許可權規則見[許可權矩陣](../api/25-gateway.md#憑證和帳號範圍)。

設定方法：

- **`openviking-server init`**（嵌入）：遠端部署回答 **Allow users to configure their own gateway upstreams?** 時選 no，init 會生成一個以 `ovgm_` 開頭的值，列印出來並寫入 `ov.conf` 的 `gateway.management_key`。
- **`openviking-gateway init`**（獨立）：回答 **Require a management key to change upstreams and profiles?** 時選 yes，init 會生成一個 `ovgm_` 開頭的值，只列印一次，並寫入 `gateway.conf` 的 `management_key`。
- **手動設定**：值至少 32 個字元，可以用 `openssl rand -base64 32` 生成。寫進 `management_key`，或者設定環境變數 `OPENVIKING_GATEWAY_MANAGEMENT_KEY`；兩種部署下環境變數都優先於配置檔案，見[配置參考](#配置參考)。
- **Compose 和 Helm**：Compose 會把 `OPENVIKING_GATEWAY_MANAGEMENT_KEY` 傳進容器；Helm 從 `gateway.existingSecret` 指定的 Secret 中讀取 `management-key` 欄位。見 [Docker Compose](#docker-compose) 和 [Helm](#helm)。

管理金鑰不提供命令列引數，因為命令列引數會出現在程序列表和 shell 歷史裡。設定、更換或去掉管理金鑰後需要重啟，這不會弔銷已簽發的閘道器金鑰，也不會改動已有的上游和上下文配置。

### 加密

閘道器用 OpenViking 自己的加密功能保護已存的憑證和對話狀態（見[加密指南](08-encryption.md)）：

- **嵌入**：閘道器沿用 Server 在 `ov.conf` 中的 `encryption` 段，不需要為閘道器單獨設定。
- **獨立**：在 `gateway.conf` 中加一個 `encryption` 塊，欄位和 `ov.conf` 的 `encryption` 段完全相同，例如：

  ```json
  {
    "openviking_url": "https://ov.example.com",
    "encryption": {
      "enabled": true,
      "provider": "local",
      "local": { "key_file": "~/.openviking/master.key" }
    }
  }
  ```

加密關閉或沒有這個塊時，閘道器以明文儲存，只靠檔案許可權保護。之後再開啟加密不會出問題：已有的明文值照常可讀，新寫入的值會加密。反過來，關閉加密或換一把根金鑰後，已加密的值就讀不出來了，所以要保持寫入時的加密設定。按加密指南備份根金鑰，丟了它，閘道器的資料庫就無法讀取。

v0.5 閘道器用自己的金鑰加密資料，這些資料會在首次啟動時轉換，見[遷移](#遷移)。

## 部署

### 部署方式

| 方式 | 怎麼開啟 | 客戶端地址 |
| --- | --- | --- |
| 嵌入 Server（包括 Compose 和 Helm） | 在 `ov.conf` 中開啟 `gateway.enabled` | Server 地址加 `/gateway`，預設 `http://127.0.0.1:1933/gateway` |
| 獨立執行 | 先 `openviking-gateway init`，再 `openviking-gateway` | 閘道器自己的地址加 `/gateway`，預設 `http://127.0.0.1:1935/gateway` |

兩種方式都在 `/gateway` 下提供相同的模型路徑和管理路徑。嵌入部署不需要第二個程序，也不需要按路徑分流的反向代理；獨立部署不用改動已有 OpenViking 服務的配置。

### 在 Server 中啟用

執行 `openviking-server init`，在 **Enable OpenViking Gateway on the same port?** 處回答 yes，然後啟動或重啟服務。已有配置時，在選單中選擇 **Update gateway**。遠端部署還會詢問是否允許使用者自行配置上游，見[閘道器管理金鑰](#閘道器管理金鑰)。

也可以手動把下面的內容合併進 `ov.conf`，再重啟：

```json
{
  "gateway": {
    "enabled": true
  }
}
```

使用 API 金鑰的服務端上，root 也可以在 Studio 的 OpenViking 閘道器頁面點**開啟閘道器**：Studio 會把 `gateway.enabled: true` 寫入 `ov.conf` 並重啟服務（從 Studio 重啟要求服務端只有一個 worker，否則 Studio 只儲存檔案，需要你自行重啟）。

開啟服務端的 `/studio/`，在側邊欄選擇 **OpenViking 閘道器**。dev 模式下，如果預設帳號還沒有上游，閘道器啟動時會匯入服務端可用的 VLM 憑證作為上游，並建立 `default` 上下文配置。匯入的 Coding Plan 上游需要確認後才能使用；沒有可匯入的憑證時，請手動新增上游。

**讓 Agent 修改配置。** 持有 root API 金鑰的 Agent 可以通過[執行時配置介面](../api/08-admin.md#runtime-configuration)修改 `ov.conf` 並重啟服務。獨立閘道器不提供這組介面。

### 路由

兩種部署方式下，閘道器的所有 URL 都在 `/gateway` 下。嵌入部署中，Server 把整個 `/gateway` 字首交給閘道器，其他路徑仍由 Server 自己處理：

| 路徑字首 | 用途 |
| --- | --- |
| `/gateway/v1/` | 模型 API 和模型列表 |
| `/gateway/api/v3/` | 方舟相容客戶端 |
| `/gateway/api/compatible/v1/` | 方舟 Anthropic 相容客戶端 |
| `/gateway/uploads` | 工具上傳 |
| `/gateway/admin/` | 管理 API，需要認證 |

因此客戶端使用下面的 Base URL，把 `http://127.0.0.1:1933` 換成你的 Server 地址即可：

| 客戶端 | Base URL |
| --- | --- |
| Claude Code 和 Anthropic SDK | `http://127.0.0.1:1933/gateway` |
| OpenAI 相容的客戶端和 SDK，包括 Codex、OpenCode、pi 和 Open WebUI | `http://127.0.0.1:1933/gateway/v1` |
| 火山方舟和 BytePlus 方舟 SDK | `http://127.0.0.1:1933/gateway/api/v3` |

`/health` 仍是 Server 自己的健康檢查，嵌入閘道器不單獨提供 `/health`。

獨立閘道器在自己的埠上提供同樣的 `/gateway` 路徑，另外在根路徑提供：

- `/` 跳轉到 `/studio/`，Studio 只包含閘道器和連線頁面。
- `/health` 返回 `service: "openviking-gateway"`、`auth_mode` 和 `openviking_url`；請求帶有效的 OpenViking 憑證時，還返回撥用方身份。

**對外地址。** 共享部署要把 `public_url` 設為客戶端訪問 Server（或獨立閘道器）的地址，不帶 `/gateway`，閘道器會自己加上。嵌入閘道器不設定時，沿用 Server 的對外地址（`OPENVIKING_PUBLIC_BASE_URL` 或 `server.public_base_url`）。Studio 的接入指南用它生成配置：Anthropic 客戶端使用 `<public_url>/gateway`，OpenAI 風格的客戶端使用 `<public_url>/gateway/v1`。不設定時，指南使用瀏覽器訪問 Studio 的地址；但檔案匯入的上傳連結必須依賴 `public_url`，見[匯入檔案和技能](#匯入檔案和技能)。

### Docker Compose

在 `.env` 中設定 `OPENVIKING_GATEWAY_ENABLED=true`，然後執行 `docker compose up -d`；也可以在掛載的 `ov.conf` 裡開啟 `gateway.enabled`。閘道器在 `openviking` 服務內執行，不需要單獨的服務或 profile。不用 Compose 時，`docker run` 加上 `-e OPENVIKING_GATEWAY_ENABLED=true` 即可：

```bash
docker run -d -p 1933:1933 -v ~/.openviking:/app/.openviking \
  -e OPENVIKING_GATEWAY_ENABLED=true \
  ghcr.io/volcengine/openviking:latest
```

容器內 Server 監聽 `0.0.0.0`，所以 `ov.conf` 要使用 API 金鑰認證。

- **管理金鑰**：在 `.env` 中設定 `OPENVIKING_GATEWAY_MANAGEMENT_KEY`，自帶的 Compose 檔案會把它傳進容器；也可以寫進掛載的 `ov.conf` 的 `gateway.management_key`。Compose 檔案還會傳入 `OPENVIKING_GATEWAY_ENCRYPTION_KEY`，它只在遷移 v0.5 資料時讀取一次，見[遷移](#遷移)。
- **對外地址**：設定 `OPENVIKING_PUBLIC_BASE_URL`（自帶的 Compose 檔案會傳入）即可，閘道器沒有單獨配置 `public_url` 時沿用它。
- **修改配置後**：執行 `docker compose restart openviking`；啟動錯誤用 `docker compose logs openviking` 檢視。

自帶的 Caddy 把所有路徑轉發到 `openviking:1933`。可以繼續用相容埠 1934，也可以直接訪問 Server 的 1933。配置 HTTPS 時，一條 `reverse_proxy openviking:1933` 就能承載 Studio、管理介面和模型流量，見[公網訪問](12-public-access.md)。

### Helm

在 chart values 中設定 `gateway.enabled: true`。閘道器嵌入 server 容器，資料儲存在 `<persistence.mountPath>/gateway`，Service 和 Ingress 都使用 Server 埠。保持 `replicaCount: 1`。

```yaml
gateway:
  enabled: true
  existingSecret: ""  # 可選：Secret 名稱，欄位 management-key
config:
  gateway:
    public_url: https://ov.example.com
```

- 閘道器和 Server 一樣，按 chart 的 `config.encryption` 設定加密資料。
- `existingSecret` 指定的 Secret 中有 `management-key` 欄位時，修改上游和上下文配置需要這把管理金鑰。
- 模型請求是流式的：Ingress 要關閉響應緩衝，允許至少 32 MiB 的請求體和 600 秒超時。

NGINX annotations、建立 Secret 的命令和從 sidecar 版本升級的說明見 [chart README](https://github.com/volcengine/OpenViking/blob/main/deploy/helm/README.md#openviking-gateway)。

### 獨立部署

獨立閘道器不讀取 `ov.conf`，只需要知道 OpenViking 的地址，已有的開源版或商業版服務不用改配置：

```bash
openviking-gateway init   # 寫入 ~/.openviking/gateway.conf
openviking-gateway
```

`openviking-gateway init` 依次詢問 OpenViking 地址（會實際訪問一次，並顯示服務端的認證模式和版本）、監聽地址（預設 `127.0.0.1:1935`），以及是否要求[管理金鑰](#閘道器管理金鑰)。結果寫入 `~/.openviking/gateway.conf`，或者 `--config` 指定的檔案，只有你自己能讀。想修改設定就再執行一次：它把當前值作為預設值，已有的金鑰不改就原樣保留。生成的檔案類似這樣：

```json
{
  "openviking_url": "https://ov.example.com",
  "host": "127.0.0.1",
  "port": 1935
}
```

開啟閘道器的 `/studio/`，用 OpenViking 使用者、帳號管理員或 root 的 API 金鑰登入。連線頁會顯示閘道器連線的 OpenViking 地址。獨立閘道器讀不到遠端服務的 VLM 配置，所以不能匯入模型配置，上游要手動新增。

**設定從哪裡來。** 命令列只有 `--config` 一個引數。設定了 `--config` 或 `OPENVIKING_GATEWAY_CONFIG_FILE` 時，它必須指向已存在的檔案；兩者都沒設定時，閘道器讀取 `~/.openviking/gateway.conf` 和 `/etc/openviking/gateway.conf` 中第一個存在的檔案。環境變數可以覆蓋其中任何欄位。容器裡可以完全不用檔案：設定 `OPENVIKING_GATEWAY_OPENVIKING_URL`，再按需加上 `OPENVIKING_GATEWAY_HOST=0.0.0.0` 之類的變數。兩處都沒有 OpenViking 地址時，閘道器退出，並提示執行 `openviking-gateway init` 或設定 `OPENVIKING_GATEWAY_OPENVIKING_URL`。全部欄位和覆蓋規則見[配置參考](#配置參考)。

**啟動檢查。** 獨立閘道器啟動前會先訪問一次 OpenViking：

- OpenViking 使用 trusted 認證時，閘道器拒絕啟動。
- 繫結非迴環地址時，必須確認 OpenViking 使用 `api_key` 認證才會啟動；OpenViking 連不上或處於 dev 模式時，閘道器直接退出。請先啟動 OpenViking，或者只繫結 `127.0.0.1`。
- 跨主機連線 OpenViking 時，請使用 TLS 或私有網路。

**連線公共 OpenViking 服務。** 連線 `https://api.vikingdb.cn-beijing.volces.com/openviking` 且沒有設定管理金鑰時，啟動日誌和 Studio 都會顯示 `public_openviking_without_management_key` 告警：任何持有該服務 API 金鑰的人都能登入這臺閘道器，並修改所在帳號的上游。閘道器只給你自己或團隊使用時，設定 `OPENVIKING_GATEWAY_MANAGEMENT_KEY` 後重啟即可限制修改；這不限制誰能登入，也不限制他們給自己簽發閘道器金鑰。

### 反向代理和 HTTPS

把整個站點轉發到 Server（嵌入）或閘道器（獨立），不需要按路徑分流。以 Caddy 為例：

```caddyfile
ov.example.com {
    reverse_proxy 127.0.0.1:1933 {
        flush_interval -1
    }
}
```

無論用哪種代理，都要滿足三點：關閉響應緩衝，流式輸出才能實時到達；允許至少 32 MiB 的請求體；讀取超時至少 600 秒。另外，不要在代理日誌中記錄 `/gateway/uploads` 的查詢字串，其中帶有一次性上傳令牌。對外發布前先配置好認證，見[公網訪問](12-public-access.md)。

### 擴充

一個儲存目錄只供一臺主機上的一套部署使用，嵌入閘道器和獨立閘道器不能共用同一目錄。嵌入閘道器跟隨 Server 的 worker 設定；獨立閘道器用 `workers` 設定，取值 1–64。需要在服務商之間負載均衡、故障轉移或限流時，把 LiteLLM 這類服務新增為上游。

## 在 Studio 中管理閘道器

用 OpenViking API 金鑰連線 Studio 後，在側邊欄開啟 **OpenViking 閘道器**。上游和上下文配置由整個帳號共享，閘道器金鑰和請求日誌屬於各個使用者：

- **沒有設定管理金鑰**：每個登入的使用者都能新增和修改本帳號的上游和上下文配置。
- **設定了管理金鑰**：“上游”和“上下文配置”標籤頁變為只讀，OpenViking 的 admin 和 root 也一樣。只讀時仍能檢視和測試上游（看不到 API Key 和請求頭），並在給自己簽發金鑰時選用。點**輸入閘道器管理金鑰**解鎖編輯，頁頭會顯示“可修改上游和上下文配置”；解鎖狀態保持到點選**鎖定**或關閉瀏覽器標籤頁。管理金鑰被更換後，Studio 會自動鎖定。
- **閘道器金鑰**：每個人都能給自己簽發；帳號管理員可以給本帳號的使用者簽發；root 先在側邊欄切換帳號。見[閘道器金鑰](#閘道器金鑰)。

上游和上下文配置儲存後，立即對使用它們的金鑰生效（上下文配置隻影響之後開始的對話）。還沒有可用的上游或上下文配置、自己又不能修改時，請聯絡部署閘道器的人。

### 上游

上游是模型服務的一個介面，只使用一種 API：Anthropic Messages、Chat Completions 或 Responses。閘道器不在 API 之間轉換，所以客戶端用到幾種 API，就要新增幾個上游，即使它們來自同一家服務商：Claude Code 用 Anthropic Messages，Codex CLI 用 Responses，大多數聊天應用和 SDK 用 Chat Completions。

在編輯頁選擇服務商後，會自動填入它的預設 Base URL：

| 服務商 | 協議 | 預設 Base URL |
| --- | --- | --- |
| 通用 | 三種都有 | 無，自己填寫 |
| Anthropic | Anthropic Messages | `https://api.anthropic.com` |
| OpenAI | Chat Completions、Responses | `https://api.openai.com/v1` |
| DeepSeek | 三種都有 | `https://api.deepseek.com`；Anthropic Messages 為 `https://api.deepseek.com/anthropic` |
| 火山方舟 | 三種都有 | Chat Completions 和 Responses 為 `https://ark.cn-beijing.volces.com/api/v3`；Anthropic Messages 為 `https://ark.cn-beijing.volces.com/api/compatible` |
| BytePlus 方舟（海外站） | 三種都有 | Chat Completions 和 Responses 為 `https://ark.ap-southeast.bytepluses.com/api/v3`；Anthropic Messages 為 `https://ark.ap-southeast.bytepluses.com/api/compatible` |

#### 介面

- **服務商**決定可選的協議，並讓閘道器適配各家的差異。列表裡沒有的服務商、LiteLLM 和 new-api 這類相容代理，以及 [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) 這類把訂閱帳號包裝成 API 的反向代理，都選*通用*（見[自定義上游](15-gateway.md#自定義上游)；用訂閱額度是否合規請自行確認）。
  - *通用*、*Anthropic* 和 *OpenAI* 轉發請求的方式相同。
  - *DeepSeek*：請求帶工具時，DeepSeek 要求歷史中之前每條回覆都帶推理內容，而很多聊天應用不回傳它。DeepSeek 上游預設開啟**補全推理內容回傳**（見下文“路由和開關”），所以請求保持思考模式也能用 OpenViking 工具。關閉這項後，只有請求關閉了思考模式（`"thinking": {"type": "disabled"}`）才提供 OpenViking 工具；標準 Responses 請求沒有 `thinking` 欄位，這時也得不到工具。記憶照常補充。
  - *火山方舟*和 *BytePlus 方舟*行為相同：Chat Completions 和 Responses 的每段對話使用一個固定的 `prompt_cache_key`，方舟的字首快取就能跟著對話走。請求的模型、思考模式、取樣引數、系統提示詞或工具和對話的第一個請求不同時，方舟會重建快取，請求被標為**快取引數有變化**（`ark_cache_parameters_changed`）。
- **協議**決定上游接受哪種 API。Anthropic 上游同時傳送 `x-api-key` 和 `Authorization: Bearer`，Chat Completions 和 Responses 上游只傳送 Bearer。
- **Base URL** 按服務商 SDK 文件填寫，閘道器在後面拼接端點：
  - Chat Completions 和 Responses 拼接 `/chat/completions` 或 `/responses`。只填域名時不會自動補 `/v1`，OpenAI 要寫 `https://api.openai.com/v1`。
  - Anthropic Messages 拼接 `/v1/messages`，所以 Base URL 不能以 `/v1` 結尾，否則儲存時被拒絕。
  - 末尾的斜槓會被去掉。`/api/paas/v4` 這類帶版本路徑的地址可以直接使用。
  - 客戶端用方舟路徑（`/gateway/api/v3/`、`/gateway/api/compatible/v1/`）發來的請求，按同樣的規則拼接。
  - 一個上游只有一個 Base URL。同一服務商的不同協議地址不同時，要分別建上游：例如智譜 Chat Completions 用 `https://open.bigmodel.cn/api/paas/v4`，Responses 用 `https://open.bigmodel.cn/api/v1`。方舟 Coding Plan 的 Chat Completions 和 Responses 用 `…/api/coding/v3`，Anthropic Messages 用 `…/api/coding`。

  編輯頁會實時預覽最終的請求地址；OpenAI、方舟這類地址漏掉路徑，或者 Anthropic 地址多了 `/v1` 時，會給出提示和一鍵修正。

#### 憑證

- **API Key 由誰提供**：
  - **由閘道器保管 API Key**（預設）：閘道器傳送上游的 API Key，客戶端只需要閘道器金鑰。
  - **每個客戶端自帶 API Key**：每個請求除了閘道器金鑰，還要在 `X-OpenViking-Upstream-Key` 請求頭裡帶上客戶端自己的服務商 API Key，缺少時返回 401 "Upstream API key is missing"。閘道器按服務商慣用的請求頭轉發這個 API Key，`X-OpenViking-*` 請求頭本身從不轉發。
- **API Key 和額外請求頭只寫不讀**：留空表示保留已存的值，刪除請求頭行就刪除這個請求頭。**修改 Base URL 會清除已存的 API Key 和請求頭值**，所以每次改地址都要重新填寫，已存的金鑰不會被髮往新地址。
- **額外請求頭**加在發往這個上游的每個請求上，例如服務商的版本或組織請求頭，並覆蓋客戶端傳送的同名請求頭。不能設定 `Host`、`Content-Length`、`Transfer-Encoding` 和 `Connection`。
- **這是 Coding Plan 或訂閱金鑰**：服務商通常只允許 Coding Plan 這類訂閱金鑰用在自家的程式設計工具裡，通過共享閘道器使用可能導致訂閱被封禁。勾選後，發往這個上游的請求一律被拒絕，返回 403 "Coding Plan upstreams are disabled; configure a model API key"，除非同時勾選**允許通過閘道器使用這個套餐**。閘道器無法從金鑰本身分辨它是不是訂閱金鑰，需要你自己標記。Claude 訂閱令牌（`sk-ant-oat…`）始終被拒絕。

#### 模型

- **模型**列出這個上游提供的模型名，留空表示接受任何名稱。只有列出的名稱和別名會出現在模型列表（`/gateway/v1/models`）裡。
- **模型別名**把客戶端使用的名稱對映為發給上游的模型，例如把 Claude Code 請求的 Claude 模型名對映到服務商提供的模型。別名出現在模型列表中，請求日誌顯示客戶端使用的名稱。
- **上下文視窗**按模型記錄視窗大小（token，至少 1,024），鍵是對映之後、實際發給上游的模型名。長對話按視窗的比例觸發壓縮，視窗小於 1,000,000 token 的模型都要列出來，見[長對話](#長對話)。

#### 路由和開關

- **優先順序**：對每個請求，閘道器在金鑰繫結的已啟用上游中，找出使用這種 API 並提供所請求模型的上游，選優先順序最高的一個。對話一旦開始，只要原來的上游還能服務就一直用它，所以修改優先順序隻影響新對話。
- **啟用**：停用的上游不接收請求，也不出現在模型列表裡。原本使用它的對話會轉到下一個候選上游，造成一次服務商快取未命中，並丟掉之前的 Claude 思考塊，這些請求被標為**上游已切換**（`upstream_changed`）。想保留恢復的餘地，就停用而不是刪除。
- **允許 OpenViking 工具**：決定能否通過這個上游提供 OpenViking 工具。關閉後立即生效，已經帶工具的對話也受影響。
- **補全推理內容回傳**：客戶端回傳歷史時常常丟掉模型之前回復裡的推理內容。開啟後，閘道器記下經它轉發的每條回覆的推理內容，在後續請求中放回原處：Chat Completions 補回 `reasoning_content`，Anthropic Messages 放回 thinking 塊，Responses 把帶明文內容的 reasoning 項放回對應條目之前。補回的內容每次逐位元組相同，服務商的提示快取照常命中，但計入輸入 token。客戶端自己回傳了推理內容的回覆保持不變。DeepSeek、火山方舟和 BytePlus 方舟預設開啟，其他服務商預設關閉。有些請求即使開啟也補不回推理內容：對話換了上游（`upstream_changed`）、Claude 對話丟了記憶記錄（`missing_injection_record`），或者客戶端把思考內容當作正文發回；DeepSeek 上游的這類請求同樣得不到 OpenViking 工具。
- **最小可快取長度**（僅火山方舟和 BytePlus 方舟）：模型能快取的最短提示詞長度，隻影響請求日誌如何報告快取資格。

除了優先順序，其他上游設定都立即生效，進行中的對話也一樣。閘道器不做故障轉移：選中的上游出錯時，客戶端收到這個錯誤；服務商無法訪問時返回 502 "Model upstream is unavailable"。

#### 測試和刪除

在上游列表裡點**測試**，閘道器用已存的憑證請求服務商的模型列表，告訴你地址是否有響應、金鑰是否被接受。只讀使用者也能測試。測試不驗證具體模型，也不代表允許使用 Coding Plan；各種結果的含義見[連線測試](../api/25-gateway.md#連線測試)。

有金鑰在用的上游不能刪除：先吊銷這些金鑰，或者改為停用這個上游。

### 匯入 OpenViking 模型配置

嵌入部署中，**使用 OpenViking 的模型配置**（上游頁頭的**從 OpenViking 匯入**）把服務端的 VLM 憑證匯入為當前帳號的上游。沒有設定管理金鑰時只有 root（包括本地 dev）能匯入；設定了管理金鑰時需要先解鎖。

- 結果分三組顯示：已匯入、需要確認、未匯入。路徑中帶 `coding` 或 `plan` 的上游被標為 Coding Plan，確認服務商條款允許後，勾選**允許通過閘道器使用這個套餐**才能使用。
- 重複匯入不會產生重複的上游。再次匯入時，地址、API Key、請求頭、協議和服務商按服務端配置重新整理；你在閘道器裡改過的名稱、啟用狀態、優先順序、模型、別名、上下文視窗和 Coding Plan 確認都保留。
- Codex OAuth 和 Azure 憑證、缺少 `api_base` 的 LiteLLM 憑證，以及不使用 OpenAI Chat Completions API 的 LiteLLM 路由會被跳過，原因見[匯入 VLM 配置](../api/25-gateway.md#匯入-vlm-配置)。

### 上下文配置

上下文配置是一組有名字的記憶設定。每個閘道器金鑰使用一份，一份可以供多個金鑰使用。比如準備一份“Coding”配置，召回記憶、資源和技能；再準備一份“Chat”配置，只召回記憶，預算也小一些。

“上下文配置”標籤頁為每份配置顯示一張卡片，概括各部分的設定和使用它的金鑰數。標籤頁為空時，**使用推薦設定建立**一鍵建立一份名為“預設”的配置，**自定義**開啟編輯頁；之後用**新建配置**。有金鑰在用的配置不能刪除；想做一份變體，用**複製一份**最快。

> **注意**：儲存的修改只對之後開始的對話生效。對話在第一個請求時記下當時的上下文配置並一直沿用，因為中途改變模型看到的內容會破壞服務商快取。每次聊天都新開對話的客戶端很快就能用上新設定；Claude Code、Codex 以及傳送固定會話請求頭的客戶端會一直沿用舊設定，直到開始新對話，或者這段對話閒置滿 30 天（`session_ttl_days`）。

| 部分 | 作用 | 主要設定和預設值 |
| --- | --- | --- |
| 召回記憶 | 用每條新的使用者訊息檢索 OpenViking，把相關內容附加到這條訊息上。 | 檢索範圍：記憶、資源、技能 · 單條訊息預算：1,600 token · 單個上下文視窗預算：30,000 token · 相關度閾值：0.35 · 超時時間：2 秒 |
| 儲存對話 | 把完成的輪次寫入 OpenViking 會話並提交，供 OpenViking 提取記憶。 | 最新回覆等待時長：600 秒 · 提交閾值：20,000 token · 保留最近訊息：10 |
| 長對話 | 對話接近上下文視窗時，讓同一個模型寫摘要，替換之前的訊息。 | 壓縮：開啟 · 壓縮時機：視窗的 0.9 · 摘要長度上限：8,000 token · Agent 自管上下文視窗：關閉 |
| OpenViking 工具 | 讓模型在回答時使用 OpenViking 的工具。 | 開啟 · 只勾選只讀工具，見 [OpenViking 工具](#openviking-工具) |

每個部分都有自己的開關，長對話部分的壓縮和 Agent 自管上下文視窗各有一個。召回和儲存相互獨立，只召回不儲存、只儲存不召回都可以。

**召回的細節：**

- **會話開頭提供使用者畫像**獨立於召回。提供 `read` 工具時，開頭還提供記憶和技能目錄。**開頭內容預算**預設 4,000 token，技能最多佔四分之一，設為 0 時全部省略；這部分不佔召回預算。
- 召回內容由 OpenViking 在預算內選取和排版，也可能只給出 URI，供模型之後讀取。
- 檢索文本是去掉客戶端噪聲後的使用者訊息，最多取**檢索文本長度**（8,000）個字元。少於 3 個字元的訊息不檢索。
- 每條訊息最多補充**單條訊息預算**和**單個上下文視窗預算**剩餘額度中較小的那個；剩餘額度不足 64 token 時跳過檢索。無論閘道器還是客戶端壓縮了對話，單個上下文視窗預算都重新計算。預算設為 0 就等於關閉召回。這裡的 token 數是偏保守的估算，不是服務商的計費數。
- OpenViking 在**超時時間**內沒有返回時，這條訊息不帶記憶發給模型，之後也不補，客戶端重試也一樣。
- **按分類限量**（在“進階設定”中）可以給事件、實體、偏好、經驗、資源和技能六類分別設條數上限，只檢索上限大於 0 的類別。關閉時，所有來源放在一起排序。

**召回摘要。** 開啟**顯示召回摘要**（預設關閉）後，每條新使用者訊息的回覆以一段簡短摘要開頭，說明閘道器補充了什麼：

```text
> OpenViking context: user profile, memory index, skill list, earlier sessions
> OpenViking recall: 4 items (3 memories, 1 resource) — booking_duplicate_handling, user_lang_pref, +2 more
```

- `context` 行只出現在對話的第一條回覆裡，列出開頭實際提供的內容：使用者畫像、記憶目錄、技能目錄，以及這段對話較早部分在 OpenViking 中的位置。
- `recall` 行按類別統計召回條數，最多列出三個條目名。檢索失敗時改為說明原因，例如 `> OpenViking recall failed: OpenViking unavailable`。沒有找到內容、召回已關閉或預算用完時不顯示，所以第一條回覆之後，這類訊息沒有摘要。
- 工具步驟等後續請求不顯示摘要；客戶端重試同一條訊息時，摘要和第一次相同。
- 摘要在 Anthropic Messages 中單獨佔一個文本塊，在 Responses 中單獨佔一條助手訊息，在 Chat Completions 中位於回覆文本開頭。要求結構化輸出的請求，以及 `n` 大於 1 的 Chat Completions 請求，不顯示摘要。
- 模型看不到摘要：客戶端隨下一條訊息把回覆發回來時，閘道器先刪掉摘要再轉發，也不把它儲存到 OpenViking。

**儲存的細節：**

- 下一條使用者訊息到達時，上一輪就會儲存。**最新回覆等待時長**決定閘道器等多久之後儲存最後一輪並提交會話，這樣短對話也能被提交。
- **提交閾值**：會話中待提交的內容達到這麼多 token 時提交一次。每次提交後，OpenViking 在後臺提取記憶。
- **保留最近訊息**：提交後，會話中保留最新的若干完整輪次，至少包含這麼多條訊息。

每項設定的 API 名稱和取值範圍見[配置參考](#配置參考)。

### 閘道器金鑰

閘道器金鑰（`ovgw_…`）是客戶端用來代替服務商 API Key 的憑證。每把金鑰屬於一位 OpenViking 使用者，使用一份上下文配置和一組上游。

在“金鑰”標籤頁點**簽發金鑰**，依次填寫：

- **名稱**：方便日後辨認，例如“alice · Claude Code”。
- **給誰用**：普通使用者只能給自己簽發；帳號管理員可以選本帳號的使用者；root 先在側邊欄切換帳號。閘道器會從 OpenViking 讀取所選使用者的 API 金鑰；OpenViking 只儲存金鑰雜湊時讀不出來，Studio 會顯示**貼上使用者 API 金鑰**輸入框，填入該使用者當前的金鑰。root API 金鑰不能繫結到閘道器金鑰。本地 dev 模式下，金鑰以 `default` 使用者的身份讀寫記憶。
- **上下文配置**。
- **上游**：至少一個，金鑰只能訪問選中的上游。
- **允許的模型**（可選）：留空表示允許這些上游的全部模型。這裡填客戶端傳送的名稱，包括別名。請求其他模型返回 403 "Model is not allowed by this key"，模型列表也只顯示允許的名稱。

簽發前，閘道器會向 OpenViking 核實這位使用者的金鑰。貼上的是 root 金鑰、其他帳號的金鑰或無效金鑰，或者 OpenViking 連不上時，簽發失敗，見[簽發金鑰失敗](#簽發金鑰失敗)。

簽發成功後，**複製閘道器金鑰**對話方塊顯示完整金鑰，這是唯一一次：閘道器只儲存它的雜湊和開頭幾個字元。對話方塊裡還有 Claude Code、Codex CLI 和聊天客戶端的配置，已填好真實金鑰和閘道器地址，可以直接貼上。金鑰丟了就重新簽發。

- **金鑰不能編輯。** 要更換上下文配置、上游、允許的模型或使用者，就簽發新金鑰，再吊銷舊的。
- **對話屬於使用者，不屬於金鑰。** 客戶端傳送相同的會話 ID 時，同一使用者的新金鑰會接著原來的對話，換金鑰不會打斷對話。
- **吊銷**後，這把金鑰立即不能再用；使用者的對話狀態和日誌保留，直到被顯式刪除或過期。
- **OpenViking 金鑰變了。** 使用者的 OpenViking API 金鑰重新生成或使用者被刪除後，OpenViking 會拒絕閘道器儲存的舊金鑰。閘道器在隨後的請求中發現這一點（最多延遲約 30 秒），刪除繫結它的閘道器金鑰，對話狀態和日誌保留。請用當前的 OpenViking 金鑰重新簽發。OpenViking 暫時連不上或出錯時，閘道器不刪除金鑰，請求照常發給模型，只是不帶記憶。
- **每人一把金鑰。** 共用一把金鑰的人共享其 OpenViking 使用者的記憶。請給每人簽發一把；想讓不同客戶端使用不同的上下文配置，再按客戶端分開簽發。

帳號管理員和 root 可以在金鑰頁使用**刪除該使用者的閘道器資料…**：吊銷該使用者的全部閘道器金鑰，刪除閘道器為該使用者儲存的對話狀態（包括尚未儲存到 OpenViking 的內容）和請求日誌。已存入 OpenViking 的記憶不受影響，見[安全與資料](#安全與資料)。

### 請求日誌和概覽

普通使用者只看到自己的請求，帳號管理員和 root 看到整個帳號的請求。

**概覽**標籤頁彙總日誌保留期（預設 30 天）內最新的 10,000 條請求：

- 第一個請求到達之前，顯示**快速開始**清單，順序是“上游 → 上下文配置 → 簽發金鑰 → 接入”。
- **請求數**：模型請求的數量、最近一次請求的時間，以及這些請求的輸出 token。
- **首次呼叫快取命中率**：每條新使用者訊息的第一次模型呼叫中，命中服務商提示快取的輸入 token 所佔比例。這是判斷閘道器是否健康最重要的指標，應該接近不經過閘道器時服務商能達到的水平；明顯下降通常說明閘道器傳送的歷史和上一次對不上了，見[首次呼叫快取命中率下降](#首次呼叫快取命中率下降)。
- **輪內快取命中率**：同一輪裡後續呼叫的命中率，例如工具步驟和 OpenViking 工具的往返，通常很高。
- **召回的記憶條數**：補充到新訊息中的條數，以及每次檢索 OpenViking 的平均耗時（只統計實際檢索了的訊息）。
- **OpenViking**：已連線、異常或啟動中，附帶版本；異常時給出原因。OpenViking 連不上期間，請求照常發給模型，只是不帶記憶。卡片中的**儲存對話**一欄統計正在重試或已暫停儲存的對話數。
- **降級請求**：每種異常出現的次數和說明，見[降級請求的異常](#降級請求的異常)。
- **最近請求**，以及前往“請求日誌”標籤頁的連結。

**請求日誌**標籤頁按時間倒序列出最新的 1,000 條記錄，停留在第一頁時每 30 秒重新整理一次。可以按**全部**、**新訊息**、**工具步驟**或**異常**篩選，也可以按請求型別篩選，或者按模型、對話或金鑰搜尋。

各列依次是型別、模型（客戶端傳送的名稱）、服務商返回的 HTTP 狀態、token（輸入、快取佔比、輸出）、**記憶**、**儲存**狀態和**異常**。**記憶**列中，`+3` 表示這次檢索補充了 3 條，並附檢索耗時；`↺ 4` 表示之前 4 條訊息補充的記憶被原樣放回。展開一行可以看到對話 ID、上游、金鑰、耗時、token 明細、記憶檢索結果、上下文視窗用量（以及是否壓縮或開啟了新視窗）、儲存狀態和下次重試時間、OpenViking 工具詳情；有異常的請求還會說明發生了什麼、怎麼處理。

只有到達模型服務商的請求才會記錄。被閘道器先行拒絕的請求不記錄，例如金鑰無效、模型不在允許範圍內、沒有匹配的上游、請求體超限，這些情況下客戶端直接收到錯誤。

| 型別 | 含義 | 記憶 |
| --- | --- | --- |
| 新訊息 | 最後一條是新使用者訊息的請求 | 檢索一次，並放回之前的記憶；這一輪會被儲存 |
| 工具步驟 | 同一輪的延續，例如帶著工具結果繼續 | 放回之前的記憶；隨所在輪次一起儲存 |
| 輔助請求 | 生成標題、摘要、壓縮、建議和許可權檢查的請求 | 放回之前的記憶；從不儲存 |
| 子 Agent | 客戶端的子 Agent 發出的請求 | 放回之前的記憶；從不儲存 |
| Token 計數 | token 計數請求（`/gateway/v1/messages/count_tokens`） | 放回之前的記憶，計數才和實際傳送的內容一致 |
| 直接轉發 | 原樣轉發、不帶記憶的請求：其他介面、依賴服務商端狀態的 Responses 請求、壓縮過或無法解析的請求體 | 無 |
| 記憶同步 | 後臺儲存事件，不是模型請求 | — |

**儲存**列顯示每段對話的儲存狀態：

- **正常**：儲存正常進行。
- **已關閉**：這段對話的上下文配置不儲存對話。
- **重試中**：OpenViking 拒絕了儲存或無法訪問。閘道器在 10、20、40、80 秒後依次重試。
- **已暫停**：連續失敗 5 次。閘道器之後每 5 分鐘重試一次，直到成功；未儲存的輪次一直保留，直到儲存成功或對話過期。
- **已暫停**，原因為 `gateway_key_revoked`：這段對話的閘道器金鑰已被吊銷或刪除，閘道器不再重試。使用者之後用有效金鑰在這段對話裡發請求時，儲存自動恢復。

展開的行會顯示原因，例如 OpenViking 拒絕了金鑰（`openviking_http_401`，即使用者的 OpenViking 金鑰已失效），或者 OpenViking 無法訪問（`openviking_unavailable`）。對話歷史有改動（`history_changed`）是正常的：客戶端編輯、重新生成或壓縮了對話，閘道器用當前歷史在新的 OpenViking 會話中繼續儲存。

展開行中的**重新同步對話…**為這段對話新建一個 OpenViking 會話，使用者下次發訊息時，閘道器把完整歷史寫進去。已經儲存的內容留在舊會話裡，所以部分記憶可能被提取兩次。原因已經修復、對話卻仍然暫停，或者想要一份乾淨的對話副本時，可以用它。下一條訊息到達之前什麼都不會發生。重新同步需要記錄上顯示的那把金鑰；它已被吊銷時，請選同一段對話裡更新的一條記錄。

## OpenViking 工具

開啟 OpenViking 工具後，模型能在回答過程中使用 OpenViking 服務提供的工具，範圍受該使用者自己的 OpenViking 許可權限制。呼叫由閘道器執行，客戶端持續收到回答直到本次回覆結束，顯示的 token 用量包含期間所有模型呼叫。這項功能對各類客戶端意味著什麼、使用者在回覆裡看到什麼，見[讓任意客戶端擁有 Agentic 記憶](15-gateway.md#讓任意客戶端擁有-agentic-記憶)；本節說明客戶端要求、設定和上限。

這項功能面向接不了 OpenViking MCP 伺服器的聊天應用和 API 應用。Claude Code、Codex 這類支援 MCP 或有外掛的客戶端，用 MCP 或外掛更合適，因為它們會顯示每次工具呼叫和結果，並在呼叫前請求確認。

### 客戶端要求

三種協議都支援流式和非流式請求：

| 協議 | 客戶端要求 |
| --- | --- |
| Chat Completions | 回傳完整的 `messages` 歷史。 |
| Responses | 使用 `store: false` 和完整的 `input` 歷史；下一輪迴傳本輪返回的全部 `output` 內容，包括 reasoning 和客戶端工具呼叫。帶 `previous_response_id`、`conversation` 或 `background` 的請求照常轉發，不提供閘道器工具；`item_reference` 無法還原完整歷史。 |
| Anthropic Messages | 回傳完整的 `messages` 歷史，保留 thinking 和 signature 塊。token 計數請求帶相同的工具定義，但不執行工具。 |

模型在同一條回覆中同時呼叫 OpenViking 工具和客戶端工具時，閘道器處理 OpenViking 呼叫，客戶端照常執行自己的工具並回傳結果。Responses 支援客戶端的 function 和 custom 工具，Anthropic Messages 支援客戶端的 tool_use 呼叫。

### 選擇工具

新建的上下文配置預設開啟 **OpenViking 工具**，“使用推薦設定建立”也一樣。**工具**清單來自你的 OpenViking 服務，預設只勾選只讀工具：

- **預設勾選**：`find`、`search`、`grep`、`glob`、`list`、`tree`、`read`、`list_watches`、`get_acl`、`list_users`、`list_groups` 和 `health`。
- **預設不勾選**（會修改資料）：`remember`、`write`、`edit`、`add_resource`、`add_skill`、`forget`、`set_acl` 和 `cancel_watch`。想讓模型儲存記憶就勾選 `remember`，想讓它匯入網頁或附件就勾選 `add_resource`。

OpenViking 以後新增的工具會預設可用，已有對話仍沿用開始時的工具清單。已有的上下文配置保留原來的勾選。

每個上游的**允許 OpenViking 工具**預設開啟。兩個開關都開啟時，新對話獲得選中的工具，名稱加上 `openviking_` 字首，例如 `openviking_find`、`openviking_read`。Studio 會說明每個工具的用途；只有 OpenViking 提供了相應資訊時，才顯示只讀標記。工具定義隨對話中的每個請求傳送，全部工具約佔 3,500 個輸入 token，所以取消用不到的工具也能省 token。

> **注意**：選中的工具直接執行，不經過客戶端的許可權確認，寫入和刪除資料的工具也一樣。勾選會修改資料的工具前，先確認能接受這一點；給聊天應用用的配置，建議不勾選 `forget` 和 `set_acl`。呼叫提示只說明已經發生的操作，不是許可權確認。

### 工具呼叫提示

開啟**顯示工具呼叫**（預設開啟）時，閘道器每執行一次 OpenViking 工具呼叫，就在回覆中呼叫發生的位置加一行提示：

```text
> OpenViking find: "release date" — done
```

- 提示寫明工具名；能識別呼叫物件時，還顯示檢索的查詢詞，讀取、列出或寫入的 URI，或者正在匯入的檔案或技能。
- 流式回覆中，呼叫一開始提示就出現，匯入這類耗時的呼叫進行時，使用者也能看到閘道器在工作；非流式回覆在最終訊息裡帶上同樣的提示。
- 呼叫結束後補上結果：`done` 表示完成，`failed` 表示呼叫返回了錯誤，`skipped` 表示閘道器拒絕了這次呼叫、沒有執行，例如工具輪數或 token 預算已經用完。
- 每條提示單獨成段。在 Chat Completions 中，提示是回覆文本的一部分；在 Anthropic Messages 中，同一輪呼叫的提示放在同一個文本塊裡；在 Responses 中，放在同一條助手訊息裡。
- 模型看不到這些提示，它收到的是真實的呼叫和結果；閘道器也不把提示儲存到 OpenViking。

要隱藏提示，在上下文配置的 **OpenViking 工具**部分關閉**顯示工具呼叫**。和其他工具設定一樣，改動隻影響新對話。

### 什麼時候不提供工具

對話是否帶工具，由它第一個能用工具的請求決定（生成標題這類輔助請求不算），之後保持不變，所以修改上下文配置隻影響新對話。唯一的例外是關閉：模型還沒呼叫過閘道器工具時，客戶端出現了自己的 OpenViking 工具，例如 MCP 伺服器在第一輪之後才連上。

輔助請求、子 Agent 請求和檢測到 OpenViking 外掛的對話都不帶 OpenViking 工具。這類請求如果回傳了模型用過這些工具的歷史，閘道器仍附上工具定義，讓這段歷史保持有效，但拒絕新的 OpenViking 呼叫。客戶端自己的工具在每個請求裡都照常可用。

請求沒有帶工具時，請求日誌的詳情會說明原因：

| 原因 | 說明 |
| --- | --- |
| `tools_require_full_history` | Responses 請求需要 `store: false` 和完整 input 歷史，不能使用 `item_reference`。 |
| `upstream_tools_disabled` | 上游關閉了**允許 OpenViking 工具**。 |
| `tools_multiple_choices` | 請求要求返回多個候選（`n` 大於 1）。 |
| `tools_structured_output` | 請求要求結構化輸出（`response_format`、`text.format` 或 `output_config.format`）。 |
| `tools_non_function` | Chat Completions 客戶端傳入了 function 以外型別的工具。 |
| `tools_forced_choice` | `tool_choice` 為 `required`，或者指定了某個工具。 |
| `deepseek_reasoning_history_required` | 上游是 DeepSeek，請求沒有關閉思考模式（`"thinking": {"type": "disabled"}`），而之前的回覆發到上游時會缺推理內容：關閉了**補全推理內容回傳**，或者這個請求補不回推理內容（對話換了上游、丟了記憶記錄，或者思考內容被當作正文發回）。標準 Responses 請求沒有 `thinking` 欄位，按開啟思考模式處理。 |
| `tool_name_collision` | 客戶端已經接了 OpenViking 工具，閘道器在這段對話剩下的部分不再提供自己的工具（模型已經呼叫過閘道器工具的分支除外）。判斷條件見下文。 |
| `tools_unavailable` | 無法從 OpenViking 載入工具清單，也沒有之前載入成功的清單。連線恢復後開始新對話。 |
| `tools_not_selected_at_session_start` | 上下文配置開啟了工具，但這段對話的工具列表為空：配置裡一個工具都沒選，或者對話在閘道器升級前就已開始。開始新對話即可。 |

滿足以下任一條件，閘道器就認為客戶端已經接了 OpenViking 工具（`tool_name_collision`）：

- MCP 服務名（`server_label`、`mcp_server_name`、`mcp_servers[].name`）含單詞 `openviking`。
- 以 OpenViking 工具名結尾的工具名中也含這個單詞，例如 `mcp__claude_ai_OpenViking__search`；聯結器的 `authenticate` 工具不算。獨佔一行列出的延遲載入工具名也算。
- 帶字首、以 OpenViking 工具名結尾的工具（例如 `mcp__ov__read`），定義中出現 `viking://`。
- 任一請求中，客戶端工具和閘道器工具同名，因為上游會拒絕重名工具。

誤判同樣會持續整段對話，開始新對話即可。

### 匯入檔案和技能

OpenViking 服務提供匯入工具、上下文配置也勾選了它們時，模型就能匯入資料。按 URL 匯入不需要額外條件；匯入本地檔案需要以下兩種方式之一：

- **客戶端有 shell 工具**（名稱類似 bash、shell、exec_command、terminal 或 run_command）：匯入工具返回一個一次性上傳連結，模型再用客戶端的 shell 工具上傳檔案，這一步經過客戶端的許可權確認。技能目錄會先打包成 zip。連結指向 `public_url` 加 `/gateway/uploads`，所以 `public_url` 必須是客戶端能訪問的地址，前面的代理也要像其他路徑一樣轉發它。沒有設定 `public_url` 時，匯入失敗並提示 "Set gateway.public_url for client uploads"。
- **使用者訊息帶附件**：沒有 shell 工具時，模型可以匯入使用者訊息裡附帶的檔案，檔案可以是 base64 資料，也可以是附件文本，支援 Responses `input_file` 和 Anthropic `document.source` 中內嵌的 `base64`、`text` 資料。Open WebUI 通常只傳送提取出的文本，這些文本作為文本檔案匯入。附件中的 URL 和服務商的檔案 ID 不會被抓取；要匯入遠端資源，請用匯入工具的 URL 引數。

上傳大小受 `max_body_bytes` 限制（預設 32 MiB）。

### 上限

上下文配置中 **OpenViking 工具**部分的**進階設定**裡有以下上限：

| 設定 | API 名稱 | 預設值 | 範圍 | 達到上限時 |
| --- | --- | --- | --- | --- |
| 每次請求的工具輪數 | `tool_max_rounds` | 不限 | 1 及以上 | 拒絕之後的 OpenViking 呼叫，模型用已有結果和客戶端自己的工具繼續。 |
| 單次呼叫超時 | `tool_timeout_seconds` | 30 秒 | 最多 120 秒 | 這次呼叫向模型返回錯誤。 |
| 結果大小上限 | `tool_result_bytes` | 65,536 位元組 | 1,024–1,048,576 | 結果被截斷。 |
| 總時長 | `tool_total_seconds` | 不限 | 大於 0 秒 | 請求失敗，返回 504 "Hidden tool request timed out"。 |
| Token 預算 | `tool_total_tokens` | 不限 | 1,024 及以上 | 拒絕之後的 OpenViking 呼叫，模型用已有結果和客戶端自己的工具繼續。這不是計費上限，最終回答可能超出它。 |

輪數、總時長和 Token 預算預設都不限，和 Agent 自己的工具迴圈一樣，模型會一直使用 OpenViking 工具直到完成。流式請求中，使用者可以隨時中斷回覆，客戶端斷開後閘道器也會停止。**非流式請求在客戶端斷開後仍會繼續執行，所以客戶端傳送非流式請求時，請設定總時長。**欄位留空表示不限。這幾項預設值改為“不限”之前儲存的上下文配置仍保留原來的值（5 輪、120 秒、100,000 token），清空即可取消限制。

Token 預算只計算模型使用 OpenViking 工具時新增的呼叫、結果和後續生成內容，客戶端已有的對話、工具定義和圖片不計入。閘道器保留客戶端設定的回答長度上限（`max_tokens`、`max_completion_tokens` 或 `max_output_tokens`）。

### 失敗處理

- **單次呼叫失敗**：模型收到錯誤結果，可以據此繼續回答。
- **整個回答失敗**：例如服務商拒絕了後續的模型請求，或者 OpenViking 呼叫被拒絕後模型仍堅持呼叫。客戶端收到錯誤，請求日誌顯示 **OpenViking 工具呼叫失敗**（`hidden_tool_loop_failed`）。流式 Responses 請求以 `response.failed` 事件結束；Chat Completions 和 Anthropic Messages 返回 `gateway_tool_error` 錯誤。
- **某個上游反覆失敗**：關閉它的**允許 OpenViking 工具**。用過這些工具的 Claude 對話可能隨之出現**工具歷史無法繼續使用**（`hidden_tool_history_unavailable`）：之前的思考內容無法繼續使用，閘道器已將其去掉。可以按請求詳情中的停用原因恢復設定，或者開始新對話。
- **重試**：重試的工具呼叫複用第一次呼叫的結果，中斷的寫入操作不會自動重做。

## 長對話

模型的上下文視窗限制了一段對話的長度。開啟**壓縮**（預設開啟）後，閘道器會在對話撐滿視窗之前，把較早的部分換成一份摘要。

**何時壓縮。** 每收到一條新的使用者訊息或一個工具步驟，閘道器都估算一次視窗用量：取服務商為這段對話上一次回覆報告的 token 用量，加上之後新增訊息的估算值。沒有這份用量時（例如流式 Chat Completions 沒有設定 `stream_options.include_usage`），就估算整個請求。估算值達到**壓縮時機**（視窗的 0.9）時開始壓縮。輔助請求、子 Agent 請求和 token 計數請求不觸發壓縮。

**視窗大小從哪來。** 閘道器先查上游**上下文視窗**中該模型的條目（按發給上游的模型名查詢），沒有時用上下文配置的**預設上下文視窗**，兩者都沒有時按 1,000,000 token 計算。使用視窗更小的模型時請設定其中一項，否則還沒等到壓縮，服務商就會以對話過長為由拒絕請求。

**摘要怎麼生成。** 閘道器向同一個上游、同一個模型額外發一次非流式請求，客戶端的系統提示詞、工具和思考設定保持不變，所以大部分內容能命中服務商的提示快取。純文本摘要做不到的設定會被去掉：強制的工具選擇改為不呼叫工具，結構化輸出格式和停止序列也不保留。這次請求包含壓縮位置之前的對話，以及一條讓模型為自己寫摘要的指令，摘要要覆蓋：

- 使用者的目標和最新請求的原文；
- 關鍵決定和當前進度；
- 檔案、路徑和識別符號；
- 出過的錯誤和修正；
- 未完成的事項；
- 最近幾次工具結果裡的要點。

之前的摘要會併入新摘要。摘要是純文本，最長**摘要長度上限**（8,000）個 token。思考內容也計入輸出上限，而有些模型（如 DeepSeek V4.1）即使請求裡沒有思考設定也會預設思考，所以閘道器總在摘要長度上限之外再留 16,000 token 的輸出餘量；客戶端手動指定了思考預算時，改為加上這份預算。這次請求和其他請求一樣由服務商計費。

**壓縮之後模型收到什麼。** 壓縮位置取決於請求型別：

- 新的使用者訊息：壓縮位置就在這條訊息之前。模型收到 system 和 developer 訊息、作為一條使用者訊息的摘要，以及這條新訊息。
- 工具步驟：壓縮位置在最近一次工具結果之後，模型從摘要出發繼續完成任務。

摘要訊息開頭說明閘道器替換了對話較早的部分、這段內容不是使用者寫的；結尾附上這段對話開頭的閘道器說明和使用者畫像，壓縮後它們仍然保留。之後凡是重發這段歷史的請求，包括輔助請求和 token 計數請求，都做同樣的替換；子 Agent 通常傳送自己單獨的歷史，不受影響。每次壓縮讓服務商快取在壓縮位置失效一次，之後照常命中。

**壓縮位置之前的原文一概不保留**，最近幾輪也一樣。模型之前的回覆和其中的思考內容都依賴被替換掉的歷史，只保留一部分會破壞 Claude 的思考簽名。壓縮位置之後生成的內容照常傳送，包括思考內容。

**查詢被壓縮的內容。** 對話本身仍儲存在 OpenViking 裡。開啟了**儲存對話**、這段對話也提供了 `openviking_grep` 和 `openviking_read` 工具時，摘要後面會附上查詢方法：這段對話對應的 OpenViking 會話（`viking://user/<user_id>/sessions/<session_id>/`）、會話中訊息的存放位置，以及檢索步驟：先用具體關鍵詞 grep 會話拿到行號，再讀取匹配位置前後的內容。壓縮發生在一輪中間時，壓縮位置之前的部分會立即儲存到 OpenViking，模型在這一輪裡就能檢索到。

**壓縮失敗時。** 摘要請求失敗，或者回復裡呼叫了工具、內容為空、因長度上限被截斷時，閘道器改為傳送完整歷史，並在 60 秒內不再為這段對話嘗試壓縮。請求詳情會顯示**壓縮失敗**及原因。如果摘要寫完後用量仍達到**壓縮時機**（例如系統提示詞和工具本身就佔了視窗的大部分），閘道器保留這份摘要，同樣 60 秒後再嘗試，原因顯示為 `still_over_threshold`。

**不再生成 Working Memory 摘要。** 摘要由對話所用的模型生成，不使用 OpenViking 的會話摘要。閘道器新建的 OpenViking 會話都關閉了 Working Memory：提交時照常歸檔訊息、提取記憶，只是不生成會話摘要。

**記憶預算重新計算。** 每壓縮一次，**單個上下文視窗預算**就重新計算，壓縮位置之前補充過的記憶可能再次補充。

**客戶端仍傳送完整歷史。** 閘道器壓縮後，客戶端還是傳送完整歷史，閘道器在每個請求裡替換壓縮位置之前的部分。客戶端看到的用量很小，按用量決定何時壓縮的客戶端很少再自己壓縮，所以特別長的會話最終可能超過 `max_body_bytes`。客戶端壓縮或編輯歷史後，閘道器把新歷史儲存到新的 OpenViking 會話；檢索工具可用時，新歷史開頭的閘道器說明會告訴模型之前的會話在哪裡。

請求日誌中每條請求的詳情會顯示上下文視窗用量、較早的歷史是否被替換，以及新摘要的大小和耗時。

### 實驗性：Agent 自管上下文視窗

開啟 **Agent 自管上下文視窗**（預設關閉）後，由模型自己決定何時開啟新的上下文視窗，並自己寫交接筆記，不必等閘道器生成摘要。這項設定只對能使用 [OpenViking 工具](#openviking-工具)的對話生效，其他對話照常壓縮。開啟壓縮時，如果模型一直不開新視窗，壓縮仍會兜底。

模型會看到：

- **兩個額外的工具**。它們不在上下文配置的**工具**清單裡，只由這項設定控制：
  - `openviking_new_context(reason, notes, next_steps)`：開啟新視窗，`next_steps` 可省略。它必須在一輪裡單獨呼叫；和其他工具同一輪呼叫時，這一輪的每個呼叫都返回錯誤，視窗不重置。閘道器在本次請求裡已經在同一位置替換過上下文（例如剛壓縮過）時，它同樣返回錯誤。
  - `openviking_context_remaining()`：返回視窗序號、已用和剩餘 token 的估算值、本視窗內的使用者輪數、距使用者上一條訊息的時間，以及一句建議。
- **開頭的閘道器說明裡多一行**，告訴模型它用這兩個工具自己管理上下文視窗。
- **一行狀態**：每條新的使用者訊息之後，記憶塊末尾附上 `[context-status] window wN · ~X/Y tokens (P%) · T since your previous message`。
- **兩級提醒**：視窗用到**軟提醒時機**（0.7）時，閘道器提醒一次，要求模型做完當前這一步就開啟新視窗，並在交接筆記裡記下之後要用的確切路徑、行號和取值。用到**硬提醒時機**（0.85）時，要求模型立即開啟新視窗，此後每一步都重複，直到模型開啟新視窗或壓縮接手。提醒附在新的使用者訊息上，工具步驟裡則附在工具結果上。

模型呼叫 `openviking_new_context` 後，閘道器把目前為止的對話換成一個視窗頭，模型在同一條回覆裡接著工作。視窗頭依次包含：這是模型開啟的第 N 個視窗、內容不是使用者寫的；reason、notes 和 next_steps；使用者最新一條訊息的原文；檢索之前視窗的方法（條件和壓縮時相同）；這段對話開頭的閘道器說明。之後的請求會根據客戶端的歷史重建同一個視窗。重置之前的內容會立即儲存到 OpenViking，之後仍可檢索；reason 和 notes 只出現在視窗頭裡，不儲存到 OpenViking。每次重置讓服務商快取失效一次，但不需要摘要請求。

請求日誌中每條請求的詳情會顯示視窗序號、模型是否開啟了新視窗，以及收到了哪種提醒。效果取決於所用的模型，後續版本中的行為也可能調整。

## 安全與資料

**按使用者隔離。** 每把閘道器金鑰繫結一位 OpenViking 使用者。閘道器用這位使用者自己的 OpenViking 金鑰檢索記憶、儲存對話和呼叫工具，所以能做的事不會超出使用者本人的許可權；各使用者的對話狀態互相隔離。會話和記憶的正本始終在 OpenViking，閘道器只儲存讓對話繼續所需的狀態。

**閘道器儲存什麼。** `storage_path` 下有兩個 SQLite 資料庫，檔案只有執行閘道器的系統使用者能讀取；開啟[加密](#加密)後，儲存的每個值也都會加密：

- `management.sqlite3`：上游、上下文配置、閘道器金鑰、請求日誌，以及每個 Responses 響應由哪個上游建立。其中包括上游 API Key、請求頭的值，以及閘道器金鑰繫結的 OpenViking 金鑰，加密關閉時它們以明文儲存；閘道器金鑰本身只存雜湊和一段短字首。
- `kernel.sqlite3`：每段對話的狀態，包括補充到訊息中的記憶原文（原樣放回需要它）、OpenViking 工具的往返記錄、摘要，以及等待儲存的對話文本。

**請求日誌記什麼。** 只有後設資料：請求型別、模型、狀態、上游、對話 ID 的雜湊、token 數、記憶條數和耗時、儲存狀態和異常。不記錄訊息文本、召回的記憶、工具引數和結果，也不記錄任何金鑰。閘道器不寫 HTTP 訪問日誌，錯誤資訊也不回顯提交的值。

**服務商能看到什麼。** 每個上游都收到完整的模型輸入，包括閘道器補充的記憶和 OpenViking 工具的結果。只新增你放心交出這些資料的服務商。

**保留期限。** 清理任務每小時執行一次：

| 資料 | 保留時長 | 設定 |
| --- | --- | --- |
| 對話狀態 | 最後一次使用後 30 天 | `session_ttl_days` |
| 請求日誌 | 30 天 | `log_retention_days` |
| Responses 響應與上游的對應關係 | 30 天 | `response_ttl_seconds` |
| OpenViking 中的會話和記憶 | 遵循 OpenViking 自己的規則 | — |

**刪除資料。** 吊銷閘道器金鑰、或者它繫結的 OpenViking 金鑰失效，都不會刪除使用者資料。要刪除，有三種途徑：

- 帳號管理員或 root 在 Studio 中用**刪除該使用者的閘道器資料…**，或者呼叫 `DELETE /gateway/admin/users/{user_id}/data`：吊銷該使用者的閘道器金鑰，刪除對話狀態和日誌，包括尚未儲存的內容。
- root 呼叫 `DELETE /gateway/admin/account/data?account_id=<account>`，清除整個帳號的閘道器資料。
- 嵌入部署中，在 OpenViking 裡刪除使用者或帳號時，閘道器自動刪除對應的閘道器資料。獨立部署沒有這一步，資料保留到顯式刪除或過期。

已存入 OpenViking 的記憶和會話不受這些操作影響。反過來，在 OpenViking 中刪除一條記憶後，閘道器為進行中的對話儲存的那份記憶副本仍會被原樣放回，直到對話過期；要立即清除，刪除該使用者的閘道器資料。

**訪問控制。**

- 客戶端用閘道器金鑰認證，放在 `Authorization: Bearer` 或 `x-api-key` 中，金鑰可以隨時吊銷。
- 管理金鑰只控制上游和上下文配置的修改，不授予讀取記憶、日誌或簽發金鑰的許可權，見[許可權矩陣](../api/25-gateway.md#憑證和帳號範圍)。
- 帳號管理員能給本帳號的任何使用者簽發閘道器金鑰（OpenViking 只存金鑰雜湊時，需要使用者本人提供金鑰）。拿到閘道器金鑰就能以該使用者的身份召回記憶、呼叫工具，所以簽發權實際上等於讀取本帳號所有使用者記憶的許可權，只交給可信的管理員。
- `/gateway/uploads` 不需要閘道器金鑰。每次上傳由 OpenViking 簽發的一次性令牌授權，閘道器只把它轉發到 OpenViking 的上傳介面。不要讓它的查詢字串出現在代理日誌裡。
- `X-OpenViking-*` 請求頭、客戶端憑證和 Cookie 從不轉發給上游。

**備份。** 備份 `storage_path`，包括兩個資料庫及其 `-wal`、`-shm` 檔案；開啟加密時，還要保管好 OpenViking 根金鑰的備份。要得到一致的副本，先停止閘道器，或者用 SQLite 的線上備份（`sqlite3 kernel.sqlite3 ".backup kernel.backup.sqlite3"`，`management.sqlite3` 同理）。丟失不同檔案的後果：

- **丟失 `kernel.sqlite3`**：之前補充的記憶無法放回。每段進行中的對話會有一次服務商快取未命中，Claude 對話會丟掉一次之前的思考內容（**記憶記錄缺失**，`missing_injection_record`），尚未儲存的輪次也會丟失。
- **丟失 `management.sqlite3`**：上游、上下文配置、金鑰和請求日誌全部丟失，需要重新配置並簽發新金鑰。
- **丟失根金鑰**（開啟加密時）：兩個資料庫中已加密的值都無法讀取，只能從空的 `storage_path` 重新開始。

## 日常運維

- **盯住首次呼叫快取命中率。** 它反映跨輪次的提示快取，應該接近不經過閘道器時服務商能達到的水平；**輪內快取命中率**覆蓋工具步驟，正常時很高。明顯下降時，見[首次呼叫快取命中率下降](#首次呼叫快取命中率下降)。
- **用請求日誌定位單個請求。** 按新訊息、工具步驟或異常篩選，展開一行就能看到召回結果、儲存狀態和 OpenViking 工具的停用原因，見[請求日誌和概覽](#請求日誌和概覽)。
- **設定對外地址。** 把 `public_url` 設為客戶端訪問的地址（不帶 `/gateway`），反向代理後的客戶端配置和上傳連結才能保持一致。
- **定期備份。** 備份閘道器儲存目錄；開啟加密時還要備份 OpenViking 根金鑰，見[安全與資料](#安全與資料)中的“備份”。

### 升級

- 升級前讀釋出說明。新版本的閘道器讀不了舊的儲存格式時，啟動會報 `Unsupported gateway schema`，見[閘道器無法啟動](#閘道器無法啟動)。
- 獨立閘道器要求 OpenViking Server 不低於 `min_server_version`（0.4.16），否則記憶檢索和儲存都會停止，也無法簽發金鑰。兩者分開升級時，先升級 OpenViking，再升級閘道器。嵌入閘道器和 Server 同版本釋出，不做這項檢查。
- 從 sidecar 或舊版獨立閘道器升級，見[遷移](#遷移)。

### 觀測

閘道器不匯出 Prometheus 之類的監控指標，也不寫 HTTP 訪問日誌。執行狀態通過 Studio 的“概覽”和“請求日誌”標籤頁檢視，或者呼叫管理 API 的 `/gateway/admin/overview` 和 `/gateway/admin/logs`。程序存活用 `/health` 檢查：嵌入部署用 Server 的健康檢查，獨立部署用閘道器自己的。

## 設計取捨

下表說明閘道器幾項關鍵設計的原因和代價，幫你判斷它是否適合自己的場景：

| 設計 | 選擇及原因 | 代價 |
| --- | --- | --- |
| 接入位置 | 接在模型呼叫路徑上，而不是給每個 Agent 裝外掛：裝不了外掛的客戶端也能用，服務商金鑰集中管理。 | 看不到工作目錄，按專案隔離記憶要給每個專案用不同的 OpenViking 使用者。 |
| 工具由誰執行 | 閘道器在回覆過程中代為執行 OpenViking 工具，存下往返並在下一輪原樣放回：沒有工具、不支援 MCP 的客戶端也能讓模型主動使用記憶。 | 沒有逐次確認；客戶端必須每輪迴傳完整歷史；需要管理員收緊工具清單和上限。 |
| 記憶放在哪 | 附加在最新使用者訊息末尾，而不是系統提示詞裡：系統提示詞改一個字整份快取就失效；附加在末尾並在之後原樣放回，字首始終不變。 | 閘道器必須可靠地記下每處補充的原文，記錄丟失時快取失效一次。 |
| 儲存時機 | 晚一輪儲存：下一條訊息帶回上一輪，才能確認使用者保留了它。 | 最後一輪要等**最新回覆等待時長**（預設 10 分鐘）之後才儲存。 |
| 長對話 | 由閘道器讓同一個模型寫摘要：只有閘道器知道模型實際收到了什麼，摘要請求也大部分命中快取。 | 觸發壓縮的那一輪多一次模型呼叫和計費；壓縮位置之前的原文不再發給模型。 |
| 本地狀態 | 單臺主機上的 SQLite，不引入 Postgres、Redis 這類依賴，適合自部署。 | 閘道器不能多機互備，是模型呼叫路徑上的單點。 |
| 客戶端身份 | 閘道器簽發自己的金鑰，而不是直接用 OpenViking 金鑰：可以單獨吊銷，同一個人的不同客戶端可以繫結不同的上下文配置。 | 閘道器要儲存使用者的 OpenViking 金鑰，因此應開啟加密；閘道器金鑰洩露，等於該使用者的記憶洩露。 |

## 配置參考

兩種部署用同一套欄位，區別只在配置檔案放在哪、用什麼命令生成：

- **嵌入**：寫在 `ov.conf` 的 `gateway` 段，由 `openviking-server init` 生成。host、port 和 workers 跟隨 Server。
- **獨立**：寫在 `gateway.conf` 的根層，沒有 `gateway` 外層，由 `openviking-gateway init` 生成。設定了 `--config` 或 `OPENVIKING_GATEWAY_CONFIG_FILE` 時，它必須指向已存在的檔案；兩者都沒設定時，閘道器讀取 `~/.openviking/gateway.conf` 和 `/etc/openviking/gateway.conf` 中第一個存在的檔案。`OPENVIKING_CONFIG_FILE` 只用來選擇 Server 的配置。

| 欄位 | 適用於 | 預設值 | 含義 |
| --- | --- | --- | --- |
| `enabled` | 嵌入 | `false` | 在 Server 中開啟閘道器 |
| `openviking_url` | 獨立 | —（必填） | OpenViking Server 的地址 |
| `host` | 獨立 | `127.0.0.1` | 監聽地址 |
| `port` | 獨立 | `1935` | 監聽埠 |
| `workers` | 獨立 | `1` | worker 程序數，1–64 |
| `encryption` | 獨立 | 不設定（明文） | 欄位同 `ov.conf` 的 `encryption` 段，見[加密](#加密)；嵌入閘道器沿用 Server 的設定 |
| `public_url` | 兩者 | 空 | 客戶端訪問的對外地址，不帶 `/gateway`（閘道器自己加）；嵌入時為空則沿用 Server 的對外地址；都沒有時接入指南用請求來源地址，檔案上傳不可用 |
| `storage_path` | 兩者 | `~/.openviking/gateway` | 本地儲存目錄 |
| `management_key` | 兩者 | 空 | 可選的閘道器管理金鑰，至少 32 個字元 |
| `min_server_version` | 兩者 | `0.4.16` | 獨立閘道器要求的 OpenViking Server 最低版本 |
| `session_ttl_days` | 兩者 | `30` | 對話閒置多少天后過期，最小 1 |
| `response_ttl_seconds` | 兩者 | `2592000` | Responses 響應與上游的對應關係保留多少秒，最小 60 |
| `log_retention_days` | 兩者 | `30` | 請求日誌保留天數，最小 1 |
| `max_body_bytes` | 兩者 | `33554432` | 請求和上傳的大小上限，至少 1,024 位元組 |
| `upstream_timeout_seconds` | 兩者 | `600` | 服務商請求超時，必須大於 0 |
| `health_interval_seconds` | 兩者 | `60` | 檢查 OpenViking 狀態的間隔秒數，最小 1 |

**環境變數優先於配置檔案。** 兩種部署規則相同：非空的 `OPENVIKING_GATEWAY_<欄位名大寫>` 環境變數（例如 `OPENVIKING_GATEWAY_PUBLIC_URL`、`OPENVIKING_GATEWAY_MANAGEMENT_KEY`）覆蓋檔案中的值，值為空等於沒有設定。檔案中的值也可以寫成 `"$VAR"` 引用環境變數。`encryption` 塊只能寫在檔案裡。容器通常不需要配置檔案，用環境變數設定需要的欄位即可。

URL 必須是 HTTP(S)，不能含憑證、查詢引數或 fragment。未知欄位會導致校驗失敗；已刪除的欄位除外，它們會被忽略並在啟動時列印警告，包括 `encryption_key_env`，以及 `ov.conf` 中[遷移](#遷移)列出的 v0.5 欄位。

**上下文配置的設定。** 先列 Studio 中的名稱，再列管理 API 中的名稱（管理 API 把上下文配置稱為 `policies`）：

| Studio 名稱 | API 名稱 | 預設值 | 取值範圍 | 含義 |
| --- | --- | --- | --- | --- |
| 名稱 | `name` | `Default` | | 顯示名稱。 |
| 召回記憶 | `recall` | `true` | | 為每條新的使用者訊息檢索記憶。 |
| 會話開頭提供使用者畫像 | `profile` | `true` | | 新對話開始時提供畫像，獨立於召回。 |
| 開頭內容預算 | `profile_max_tokens` | `4000` | 0–32,000 | 畫像和目錄的獨立預算；0 表示省略。目錄需要提供 `read` 工具。 |
| 顯示召回摘要 | `show_recall` | `false` | | 在回覆開頭說明 OpenViking 補充了什麼，或召回失敗的原因。模型看不到。 |
| 檢索範圍 | `context_types` | `memory`、`resource`、`skill` | 至少一個 | 檢索哪些內容：記憶、資源、技能。 |
| 單條訊息預算 | `max_tokens` | `1600` | 64–32,000 | 一條訊息最多補充的 token 數。 |
| 單個上下文視窗預算 | `session_max_tokens` | `30000` | ≥ 0 | 一個上下文視窗內最多補充的 token 數，每次壓縮後重新計算；0 表示關閉召回。 |
| 相關度閾值 | `score_threshold` | `0.35` | 0–1 | 接受的最低相關度分數。 |
| 超時時間 | `recall_timeout` | `2`（秒） | 最多 30 | 檢索最多等多久，超時後訊息不帶記憶繼續傳送。 |
| 檢索文本長度 | `query_max_chars` | `8000` | 3–32,000 | 取訊息的多少個字元作為檢索文本。 |
| 按分類限量 | `quotas` | `{}`（關閉） | 鍵：`events`、`entities`、`preferences`、`experiences`、`resources`、`skills` | 每個分類最多取的條數；只檢索大於 0 的分類。 |
| 儲存對話 | `capture` | `true` | | 把完成的輪次儲存到 OpenViking。 |
| 最新回覆等待時長 | `idle_seconds` | `600`（秒） | ≥ 1 | 停頓多久之後儲存最後一輪並提交會話。 |
| 提交閾值 | `commit_tokens` | `20000` | ≥ 1 | 會話中待提交的 token 數達到這個值時提交。 |
| 保留最近訊息 | `keep_recent_messages` | `10` | 0–1,000 | 提交後會話中保留的訊息數。 |
| 壓縮 | `compaction` | `true` | | 接近上下文視窗時，用摘要替換對話較早的部分。 |
| 壓縮時機 | `compaction_threshold` | `0.9` | 0.5–0.98 | 上下文視窗用到多大比例時壓縮。 |
| 摘要長度上限 | `summary_max_tokens` | `8000` | 1,000–32,000 | 一份摘要最多多少 token。 |
| 預設上下文視窗 | `context_window` | 未設定（按 1,000,000 計算） | ≥ 1,024 | 上游沒有列出該模型時使用的視窗。 |
| Agent 自管上下文視窗 | `agent_windows` | `false` | | 實驗性。讓模型自己開啟新的上下文視窗；需要 OpenViking 工具。 |
| 軟提醒時機 | `window_soft_ratio` | `0.7` | 0.3–0.95，須低於 `window_hard_ratio` | 視窗用到這個比例時，提醒模型儘快開啟新視窗。 |
| 硬提醒時機 | `window_hard_ratio` | `0.85` | 0.4–0.97 | 視窗用到這個比例時，要求模型立即開啟新視窗。 |
| OpenViking 工具 | `gateway_tools` | `true` | | 為 Chat Completions、完整歷史的 Responses 和 Anthropic Messages 提供 OpenViking 工具。 |
| 取消勾選的工具 | `disabled_tools` | 會修改資料的 8 個工具，見[選擇工具](#選擇工具) | OpenViking 工具原名，不帶 `openviking_` | 新對話不提供這些工具，其餘可用工具都提供，包括以後新增的。API 請求省略這個欄位時使用預設列表；列表為空且總開關開啟時，提供全部可用工具。 |
| 顯示工具呼叫 | `show_tool_calls` | `true` | | 每次 OpenViking 工具呼叫都在回覆里加一行提示。 |
| 每次請求的工具輪數 | `tool_max_rounds` | `null`（不限） | 1 及以上 | 見[上限](#上限)。 |
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
| Base URL | `base_url` | | 服務商地址；預設地址和拼接規則見[上游](#上游)。 |
| API Key 由誰提供 | `auth_mode` | `managed` | `managed`（由閘道器保管 API Key）或 `passthrough`（每個客戶端自帶 API Key）。 |
| API Key | `api_key` | | 只寫，見[憑證](#憑證)。 |
| 額外請求頭 | `headers` | `{}` | 只寫，見[憑證](#憑證)。 |
| 模型 | `models` | `[]` | 提供的模型名；留空表示接受任何名稱。 |
| 模型別名 | `aliases` | `{}` | 客戶端使用的名稱 → 發給上游的模型。 |
| 上下文視窗 | `context_windows` | `{}` | 模型 → token 數，每項至少 1,024。 |
| 優先順序 | `priority` | `0` | 數值越大，新對話越優先使用。 |
| 啟用 | `enabled` | `true` | 停用的上游不接收請求。 |
| 允許 OpenViking 工具 | `allow_gateway_tools` | `true` | 能否通過這個上游提供 OpenViking 工具。 |
| 補全推理內容回傳 | `replay_reasoning` | `null`（跟隨服務商） | 把客戶端丟掉的推理內容補回之前的回覆。`null` 時 `deepseek`、`ark` 和 `byteplus` 開啟，其他服務商關閉；`true` 或 `false` 覆蓋服務商預設值。Studio 中開關與服務商預設值一致時儲存為 `null`。 |
| 這是 Coding Plan 或訂閱金鑰 | `coding_plan` | `false` | 除非另外允許，否則拒絕發往這個上游的請求。 |
| 允許通過閘道器使用這個套餐 | `allow_coding_plan` | `false` | 允許使用被標記為 Coding Plan 的金鑰。 |
| 最小可快取長度 | `cache_min_tokens` | `1024` | 僅火山方舟和 BytePlus 方舟；影響快取資格的報告。 |

閘道器金鑰的欄位、全部管理操作、許可權規則和錯誤原因見[管理 API](../api/25-gateway.md)。

## 遷移

以下步驟適用於從早期版本的 sidecar 或獨立閘道器遷移到嵌入閘道器。

1. **先備份。** 備份 `storage_path`（兩個資料庫，以及存在的話 `encryption.key`）。停止舊的閘道器程序或 sidecar，再啟用嵌入閘道器。
2. **刪掉舊欄位。** 從 `ov.conf` 的 `gateway` 段刪除 `host`、`port`、`workers`、`url`、`openviking_url`、`admin_token_env` 和 `encryption_key_env`。Server 會忽略這些欄位並在啟動時列印警告，舊的 `ov.conf` 仍能啟動，但還是應該清理掉。`openviking-server init` → **Update gateway** 會自動刪除它們。想繼續獨立執行閘道器，就執行 `openviking-gateway init`，或者把設定移到單獨的 `gateway.conf`，去掉 `gateway` 外層和 `enabled`。獨立閘道器的命令不再接受 `--openviking-url`、`--host`、`--port`、`--workers` 和 `--storage-path`，這些設定改寫到 `gateway.conf` 或環境變數中。
3. **改對外地址。** 把 `public_url` 改為 Server 的對外地址（不帶 `/gateway`），或者刪掉。舊版快速開始把它設成了 `http://127.0.0.1:1935`，嵌入閘道器不再監聽這個埠，接入指南和上傳連結都會指向一個不存在的地址。`openviking-server init` → **Update gateway** 發現 `public_url` 指向別的埠時，會詢問是否清除。
4. **改客戶端地址和部署配置。** 閘道器的所有 URL 現在都在 `/gateway` 下，所以客戶端要同時改埠和路徑：`http://host:1935/v1` 改為 `http://host:1933/gateway/v1`，Claude Code 的 `ANTHROPIC_BASE_URL` 從 `http://host:1935` 改為 `http://host:1933/gateway`，方舟 SDK 改用 `http://host:1933/gateway/api/v3`。舊路徑不再提供服務。呼叫管理 API 的指令碼把 `/api/v1/admin/gateway/...` 改為 `/gateway/admin/...`。移除舊的 1935 Service 和 Ingress 路由、Compose 的 `gateway` 服務和 profile，以及 Helm 的 sidecar 配置 `gateway.workers`、`gateway.port`、`gateway.resources`。1935 仍是獨立執行的預設埠，獨立閘道器也使用同樣的 `/gateway` 路徑。
5. **首次啟動會轉換已存資料。** v0.5 閘道器用自己的金鑰加密資料。新版閘道器（嵌入或獨立）首次啟動時，用這把舊金鑰解密，再按當前的[加密](#加密)設定重新寫入；加密關閉時寫成明文，所以想讓資料繼續加密，要在這次啟動前開啟 OpenViking 加密。舊金鑰從環境變數 `OPENVIKING_GATEWAY_ENCRYPTION_KEY` 讀取，或者從 `storage_path` 下的 `encryption.key` 讀取。`encryption_key_env` 會被忽略：如果你曾用它指向別的環境變數，這次啟動時把金鑰匯出為 `OPENVIKING_GATEWAY_ENCRYPTION_KEY`。存在舊的加密資料、兩處卻都沒有金鑰時，閘道器拒絕啟動，錯誤資訊會寫明這兩個位置。用 Helm 時，只在這次升級的版本中保留 `existingSecret` 裡的 `encryption-key` 欄位。啟動成功後舊金鑰不會再被讀取，可以刪掉這個環境變數、Secret 欄位和 `encryption.key`。
6. **移除共享 admin token。** `OPENVIKING_GATEWAY_ADMIN_TOKEN` **不會**被當作管理金鑰。需要限制誰能修改上游和上下文配置時，顯式設定 `management_key`。
7. **核對上游地址。** 首次啟動時，閘道器會改寫一次已存上游的 Base URL，讓每個上游繼續請求升級前的同一個地址：
   - 火山方舟和 BytePlus 方舟的 Chat Completions、Responses 上游，只有域名的補上 `/api/v3`。
   - 其他 Chat Completions、Responses 上游，路徑不以 `/v1`、`/v4` 這類版本段結尾的補上 `/v1`。這包括純域名（`https://api.deepseek.com` → `https://api.deepseek.com/v1`），也包括帶路徑字首的地址（`https://openrouter.ai/api` → `https://openrouter.ai/api/v1`，或者掛在 `/litellm` 下的自建代理）。
   - 方舟和 BytePlus 方舟的 Anthropic 上游，只有域名的補上 `/api/compatible`。
   - 以 `/v1` 結尾的 Anthropic Base URL 去掉 `/v1`。

   已經以其他版本段結尾的地址保持不變，例如智譜的 `https://open.bigmodel.cn/api/paas/v4`：升級前它會被拼成 `…/v4/v1` 而請求失敗，升級後按填寫的地址直接可用。新建和修改的上游按[上游](#上游)中的規則拼接，以 `/v1` 結尾的 Anthropic Base URL 會被拒絕。
8. **瞭解日誌和吊銷的變化。** 請求日誌新增使用者列，沒有使用者的舊記錄只出現在帳號管理員和 root 的檢視中。吊銷金鑰不再刪除使用者資料，顯式刪除和保留期照常生效。

## 故障排查

### 常見現象

| 現象 | 原因 | 處理 |
| --- | --- | --- |
| 某段對話沒有召回，也沒有儲存 | 檢測到 OpenViking 外掛，閘道器把召回、儲存和工具都讓給了外掛。 | 正常行為，避免同一份內容被補充、儲存兩次，見[閘道器還是外掛](15-gateway.md#閘道器還是外掛)。 |
| 儲存顯示“重試中”，之後變成“已暫停” | OpenViking 拒絕儲存或無法訪問；或者這段對話的閘道器金鑰已被吊銷（`gateway_key_revoked`），例如使用者的 OpenViking 金鑰被重新生成過。 | OpenViking 恢復後閘道器會自動恢復儲存。金鑰被吊銷時，重新簽發閘道器金鑰，使用者的下一個請求會恢復儲存。見[OpenViking 中看不到對話](#openviking-中看不到對話)。 |
| 上下文配置開啟了工具，對話裡卻沒有 | 還沒有能用工具的請求，第一個能用的請求載入工具清單失敗，客戶端沒有回傳完整歷史，或者客戶端自己接了 OpenViking 工具。 | 在請求日誌裡檢視原因（見[什麼時候不提供工具](#什麼時候不提供工具)）。客戶端接了 OpenViking MCP 伺服器時出現 `tool_name_collision` 是正常的；其他原因修正後開始新對話。 |
| 請求不帶記憶 | OpenViking 無法訪問或超時、預算用完、沒有相關內容等。 | 見[沒有補充記憶](#沒有補充記憶)。 |
| 長對話被服務商以過長為由拒絕 | 閘道器不知道模型的實際視窗，壓縮得太晚。 | 見[長對話超出上下文長度](#長對話超出上下文長度)。 |

### 閘道器無法啟動

嵌入閘道器無法啟動時，整個 OpenViking Server 都會停止。請在 Server 日誌中檢視啟動錯誤（Compose 中用 `docker compose logs openviking`）。

- **v0.5 資料缺少舊金鑰**：儲存目錄裡有 v0.5 閘道器加密的資料，但既沒有 `OPENVIKING_GATEWAY_ENCRYPTION_KEY`，`storage_path` 下也沒有 `encryption.key`。提供原來的金鑰，見[遷移](#遷移)第 5 步。
- **舊欄位**：刪除[遷移](#遷移)第 2 步列出的欄位。
- **管理金鑰太短**：至少 32 個字元；用 `$VAR` 引用的環境變數沒有設定時，也會報這個錯。
- **加密設定**：Server 的 `encryption` 段（嵌入）或 `gateway.conf` 的 `encryption` 塊（獨立）不合法，或者載入不了根金鑰。見[加密指南](08-encryption.md)。
- **儲存格式不支援**（`Unsupported gateway schema`）：儲存目錄由不相容的閘道器版本寫入（更舊的版本，或降級前更新的版本）。換一個空的 `storage_path`。
- **獨立執行缺少 OpenViking 地址**：執行 `openviking-gateway init`，或者設定 `OPENVIKING_GATEWAY_OPENVIKING_URL`。
- **獨立執行找不到配置檔案**：`--config` 或 `OPENVIKING_GATEWAY_CONFIG_FILE` 指定的檔案不存在。改正路徑，或者用 `openviking-gateway init --config <路徑>` 生成它。
- **獨立執行繫結非迴環地址**：啟動檢查必須連上 OpenViking 並確認它使用 `api_key` 認證，否則閘道器退出。先啟動 OpenViking（在容器中要等它就緒），或者繫結 `127.0.0.1`。

### Studio 顯示設定卡片

| 卡片 | 處理 |
| --- | --- |
| 這臺 OpenViking 沒有開啟閘道器（404） | 執行 `openviking-server init` → **Update gateway**，或者在 `ov.conf` 中設定 `gateway.enabled: true` 後重啟。使用 API 金鑰的服務端上，root 也可以直接在這個頁面點**開啟閘道器**。帳號管理員和普通使用者看到的卡片只提示聯絡部署者開啟閘道器。 |
| 先連線 OpenViking，或者 OpenViking API 金鑰無效（401） | 開啟連線設定，填入當前的 OpenViking API 金鑰。 |
| 閘道器不支援 Trusted 模式（`trusted_mode_unsupported`） | 把 Server 改為 `api_key` 認證。 |
| 閘道器連不上 OpenViking（`openviking_unreachable`） | 只出現在獨立閘道器：檢查 `openviking_url`（`gateway.conf` 或 `OPENVIKING_GATEWAY_OPENVIKING_URL`）和網路。 |

“上游”和“上下文配置”標籤頁只讀，是因為部署者設定了閘道器管理金鑰：點**輸入閘道器管理金鑰**解鎖。OpenViking 的 root 或 admin API 金鑰不能解鎖編輯；管理金鑰被更換後（`management_key_invalid`），Studio 會重新鎖定。

### 簽發金鑰失敗

**簽發金鑰**對話方塊會顯示失敗原因，括號裡是管理 API 返回的 `reason`。

| Studio 中的提示 | 原因和處理 |
| --- | --- |
| 服務端讀不到這個使用者的使用者 API 金鑰，請改為貼上（`user_key_unreadable`） | OpenViking Server 只儲存了金鑰雜湊（`encryption.api_key_hashing.enabled`）。在**貼上使用者 API 金鑰**中填入該使用者自己的金鑰。 |
| 不接受 Root API 金鑰，請使用本帳號下的使用者 API 金鑰（`root_key_not_allowed`） | root API 金鑰不能繫結到閘道器金鑰，改用某個使用者或帳號管理員的 API 金鑰。本地 dev 模式的 `default/default` 不受此限。 |
| 這個 OpenViking API 金鑰屬於其他帳號（`other_account`） | 金鑰所屬的帳號不是你在 Studio 中管理的帳號。 |
| OpenViking 拒絕了這個金鑰（`openviking_http_401`） | 金鑰不完整、已被重新生成，或者使用者已被刪除。使用該使用者當前的金鑰。 |
| OpenViking 無法識別這個金鑰所屬的使用者（`openviking_identity_missing`） | OpenViking 沒有返回這個金鑰對應的使用者。使用本帳號中某個使用者的金鑰。 |
| 閘道器連不上 OpenViking，無法校驗這個金鑰（`openviking_unavailable`） | 閘道器訪問不到 OpenViking；獨立閘道器檢查 `openviking_url`。 |
| OpenViking 版本低於閘道器的要求（`openviking_version_mismatch`） | 僅獨立閘道器：OpenViking Server 低於 `min_server_version`（0.4.16），請升級。從原始碼安裝、沒有版本標籤的服務可能報告 `0.1.dev123` 這樣的開發版本號；請安裝正式版本，或者把 `min_server_version` 改成與之匹配的值。 |

### 客戶端收到閘道器返回的錯誤

這些拒絕都發生在請求到達服務商之前，所以不會出現在請求日誌裡。

| 狀態碼和提示 | 原因和處理 |
| --- | --- |
| 401 "Invalid gateway key. It may have been revoked, or removed because its OpenViking API key was regenerated…" | 客戶端沒有傳送閘道器金鑰，傳送了已吊銷的金鑰或服務商的 API Key，或者使用者的 OpenViking API 金鑰重新生成後，閘道器刪除了這把金鑰。檢查客戶端實際傳送的金鑰，必要時重新簽發。 |
| 403 "Claude subscription OAuth credentials are not supported" | 客戶端傳送了 Claude 訂閱令牌，例如 Claude Code 用訂閱帳號登入且沒有設定 `ANTHROPIC_AUTH_TOKEN`；或者上游儲存的就是訂閱令牌。請改用 API Key。 |
| 403 "Model is not allowed by this key" | 模型不在金鑰允許的範圍內。簽發一把允許這個模型的金鑰。 |
| 404 "No allowed upstream matches this protocol and model" | 金鑰繫結的已啟用上游中，沒有一個使用客戶端呼叫的 API 並提供所請求的模型。檢查上游的協議、模型和別名、是否啟用，以及金鑰繫結了哪些上游。 |
| 401 "Upstream API key is missing" | 上游要求每個客戶端在 `X-OpenViking-Upstream-Key` 中自帶 API Key，或者由閘道器保管 API Key 的上游沒有填寫。 |
| 403 "Coding Plan upstreams are disabled; configure a model API key" | 上游被標記為 Coding Plan 金鑰。改用模型 API Key，或者有意勾選**允許通過閘道器使用這個套餐**。 |
| 404 "Unknown response for this key"、403 "Response upstream is no longer allowed" | 查詢的 Responses 響應不是這把金鑰建立的，或者建立它的上游已停用、不再繫結到這把金鑰。 |
| 413 | 請求體超過了 `max_body_bytes`，或者超過了代理自己的上限。 |
| 426 | 對 Responses API 發起了 WebSocket 連線。這是預期行為，Codex 會改用 HTTP。 |
| 502 "Model upstream is unavailable" | 閘道器連不上服務商，或者呼叫超過了 `upstream_timeout_seconds`。在上游上點**測試**。 |
| 504 "Hidden tool request timed out" | OpenViking 工具的往返超過了上下文配置中工具的**總時長**；沒有設定總時長時，是往返中某次模型請求超過了 `upstream_timeout_seconds`。 |

### 沒有補充記憶

先在請求日誌裡找到這個請求。找不到，說明客戶端沒有經過閘道器，或者請求被閘道器拒絕了（見上一節）。找到後展開它，檢視記憶檢索結果：

- **沒有找到相關內容**（`empty`）：新使用者通常如此。對話提交、OpenViking 提取之後才會有記憶。
- **召回已關閉或預算已用完**（`disabled`）：上下文配置關閉了召回，這段對話的預算已經用完，或者訊息短於 3 個字元。
- **OpenViking 無法訪問或響應超時**（`openviking_unavailable`）：檢視“概覽”標籤頁上的 OpenViking 卡片。OpenViking 在執行但響應慢時，可以調長**超時時間**。
- **OpenViking 拒絕了這個金鑰**（`openviking_http_401`）：使用者的 OpenViking 金鑰已失效。用當前的金鑰簽發新的閘道器金鑰。
- **OpenViking 版本低於閘道器的要求**（`openviking_version_mismatch`）：見[簽發金鑰失敗](#簽發金鑰失敗)。
- **檢測到 OpenViking 外掛**（`plugin_present`）：閘道器發現了 OpenViking 外掛，讓出了這段對話。
- **型別不是新訊息**：工具步驟、輔助請求和子 Agent 請求從不檢索，它們放回之前的訊息得到的記憶。

檢索失敗的訊息之後也不會補上記憶；下一條訊息會重新檢索。

### OpenViking 中看不到對話

- **儲存晚一輪。** 下一條訊息到達時，上一輪才會出現；最後一輪要等**最新回覆等待時長**（預設 10 分鐘）。
- **上下文配置不儲存對話。** 這時**儲存**列顯示“已關閉”。
- **儲存正在重試或已暫停。** 展開的行會顯示原因。原因修復後（例如 OpenViking 恢復訪問），閘道器會在 5 分鐘內重試。原因為 `gateway_key_revoked` 時，重新簽發閘道器金鑰，下一個請求會恢復儲存。對話一直暫停時，用**重新同步對話…**。
- **檢測到 OpenViking 外掛**（`plugin_present`）：閘道器不為這段對話儲存任何內容。
- **你用的是其他使用者的身份。** 會話屬於閘道器金鑰背後的 OpenViking 使用者，名稱形如 `gateway-…`。
- **記憶比會話出現得晚。** OpenViking 在提交之後才在後臺提取記憶。

### 首次呼叫快取命中率下降

先和不經過閘道器時服務商能達到的命中率比較，再看最近請求上標出的異常：

- **記憶記錄缺失**（`missing_injection_record`）：閘道器儲存丟失、從舊備份恢復，或者記錄已過期，之前補充的記憶無法放回。進行中的對話在一次未命中之後就會恢復。
- **上游已切換**（`upstream_changed`）：對話原來的上游被停用、沒有繫結到客戶端當前用的金鑰，或者不再提供這個模型，於是對話轉到了另一個上游。
- **快取引數有變化**（`ark_cache_parameters_changed`）：在火山方舟或 BytePlus 方舟上，客戶端在同一段對話裡改變了模型、思考模式、取樣引數、系統提示詞或工具。
- **沒有標出異常**：客戶端本身可能每輪都在改動之前的訊息或系統提示詞，例如插入當前時間，閘道器無法修正。每次壓縮、模型每次開啟新的上下文視窗，也都會造成一次未命中，這是預期內的。

### 長對話超出上下文長度

服務商以對話過長為由拒絕長對話的請求時，通常是下面三種原因之一：

- **閘道器不知道模型的視窗大小。** 上游的**上下文視窗**裡沒有這個模型，上下文配置也沒有設定**預設上下文視窗**，閘道器就按 1,000,000 token 計算，對視窗更小的模型壓縮得太晚。補上模型的視窗大小。
- **對話所用的上下文配置關閉了壓縮。** 修改配置只對新對話生效。
- **壓縮失敗。** 請求詳情會顯示原因，閘道器 60 秒後再試。摘要總因長度上限被截斷時，調大**摘要長度上限**。原因是 `still_over_threshold` 時，說明系統提示詞、工具和摘要本身就佔滿了大部分視窗：調小**摘要長度上限**，或者檢查模型的上下文視窗設定。

### 檔案匯入失敗

- "Set gateway.public_url for client uploads"：把 `public_url` 設為客戶端能訪問的地址。
- 上傳連結無法訪問或返回 404：確認 `public_url` 不是舊的 `:1935` 地址，也沒有以 `/gateway` 結尾，並且代理像其他路徑一樣轉發 `/gateway/uploads`。
- 413：檔案超過了 `max_body_bytes` 或代理的上限。
- 502 "OpenViking upload is unavailable"：閘道器連不上 OpenViking Server。
- 模型沒有匯入工具：OpenViking 服務沒有提供該工具，上下文配置沒有勾選，或者當前請求不能使用閘道器工具。檢查工具清單和請求詳情。

### 降級請求的異常

“請求日誌”和“概覽”標籤頁會標出閘道器沒能完整處理的請求。Studio 顯示異常名稱，括號裡是管理 API 中對應的值：

| 異常 | 發生了什麼 | 怎麼處理 |
| --- | --- | --- |
| 記憶不可用（`memory_store_failure`） | 閘道器無法讀寫自己的儲存，或者該使用者的閘道器資料剛被刪除。請求不帶記憶發給了模型；Claude 對話中之前的思考內容被去掉。 | 檢查磁碟空間、許可權和閘道器日誌。剛刪除過該使用者的閘道器資料時出現屬於正常。 |
| 原樣轉發（`unsafe_json`） | 請求中有無法精確重新編碼的數字或重複的鍵，閘道器逐位元組原樣轉發，沒有補充記憶。 | 通常只與某個客戶端有關，閘道器這邊無需調整。 |
| 上游已切換（`upstream_changed`） | 對話原來的上游無法再服務，轉到了另一個上游，造成一次快取未命中，之前的 Claude 思考內容也被去掉。 | 重新啟用這個上游，或者讓客戶端改用包含它的金鑰；也可以接受這次切換。 |
| 記憶記錄缺失（`missing_injection_record`） | Claude 對話中，之前補充的記憶已經沒有記錄，之前的思考內容被去掉一次。 | 儲存丟失後，或者在很久以前的對話裡出現，都在預期之內。反覆出現時，開始新對話。 |
| 檢測到 OpenViking 外掛（`plugin_present`） | 檢測到 OpenViking 外掛，這段對話不再使用閘道器記憶。 | 使用外掛時出現屬於正常。同一個客戶端在外掛和閘道器之間二選一。 |
| 快取引數有變化（`ark_cache_parameters_changed`） | 在火山方舟或 BytePlus 方舟上，影響快取的引數與對話的第一個請求不同，提示快取很可能沒有命中。 | 在同一段對話裡保持模型、思考模式、取樣引數、系統提示詞和工具不變。 |
| 工具歷史無法繼續使用（`hidden_tool_history_unavailable`） | Claude 對話用過 OpenViking 工具，但當前請求不能使用這些工具，之前的思考內容已被去掉。 | 檢視請求詳情中的工具停用原因，恢復原設定，或者開始新對話。 |
| OpenViking 工具呼叫失敗（`hidden_tool_loop_failed`） | 模型使用 OpenViking 工具時未能完成回答，客戶端收到錯誤。 | 見[失敗處理](#失敗處理)。 |
| 回覆未儲存（`capture_parse_failure`） | 流式回覆無法解析，這條回覆沒有儲存，客戶端不受影響。 | 無需處理，僅供瞭解。 |
| 金鑰未校驗（`revocation_check_unavailable`） | OpenViking 無法確認這把閘道器金鑰，請求在沒有檢查是否已吊銷的情況下照常處理。 | 檢查 OpenViking 是否可達、執行是否正常。 |
