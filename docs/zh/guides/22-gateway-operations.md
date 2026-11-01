---
description: 把 OpenViking 閘道器嵌入 Server、用 Docker Compose 或 Helm 部署，或者作為獨立程序執行；再對外暴露、做好保護，並在升級中保持穩定執行。
---

# OpenViking 閘道器部署與運維

本頁寫給把 OpenViking 閘道器作為服務來執行的人：按合適的方式部署、放到反向代理後面、控制誰能修改配置，以及在升級和遷移中保持服務正常。你需要一臺使用 API 金鑰認證或本地 dev 模式的 OpenViking Server，完整條件見[環境要求](#requirements)。第一次接觸閘道器，請先讀[OpenViking 閘道器](15-gateway.md)。

> **注意**：閘道器目前處於 Beta 階段，設定和介面可能隨版本調整，升級前請先讀釋出說明。

**要找別的內容？** 本頁只講執行閘道器，其他內容見：

- Studio 標籤頁和各項設定：[在 Studio 中管理 OpenViking 閘道器](../gateway/06-manage-in-studio.md)，以及[上游](../gateway/07-upstreams.md)、[上下文配置](../gateway/08-context-profiles.md)、[閘道器金鑰](../gateway/09-gateway-keys.md)和[閘道器概覽與請求日誌](../gateway/10-overview-and-requests.md)。
- 報錯、告警或 Studio 設定卡片：[OpenViking 閘道器排障](../gateway/12-troubleshooting.md)。
- 配置欄位或環境變數：[配置參考](../gateway/13-configuration.md)。
- 存了什麼、誰能看到、保留多久、怎麼備份：[安全與資料](../gateway/11-security-and-data.md)。
- OpenViking 工具或長對話：[閘道器中的 OpenViking 工具](../gateway/04-openviking-tools.md)和[閘道器中的長對話](../gateway/05-long-conversations.md)。
- 某個客戶端怎麼配置：[把客戶端接入 OpenViking 閘道器](../gateway/03-connect-clients.md)。

## 環境要求 {#requirements}

| 條件 | 說明 |
| --- | --- |
| OpenViking 認證方式 | `api_key` 或本地 dev 模式。閘道器不支援 trusted 認證。 |
| OpenViking 版本 | 嵌入執行時和 Server 同版本釋出，無需額外檢查；獨立執行時要求 OpenViking Server 0.4.16 或更高版本。 |
| 安裝 | 閘道器包含在 OpenViking 核心包中。可選的 `gateway-fast` extra（`pip install "openviking[gateway-fast]"`）裝上更快的事件迴圈和 HTTP 解析器。 |
| 登入身份 | 遠端部署需要 OpenViking API 金鑰，普通使用者、帳號管理員和 root 都能登入 Studio 的閘道器頁面。本地 dev 模式不需要金鑰，固定使用 `default/default` 身份。 |
| 儲存 | 單機使用本地磁碟上的 SQLite，多副本使用共享 Redis。Redis 需要 `pip install "openviking[expiry]"`，官方映象已包含。 |

## 選擇部署方式 {#deployment-options}

閘道器可以執行在 OpenViking Server 內部（嵌入），也可以作為單獨的程序執行（獨立）。兩種方式都在 `/gateway` 下提供相同的模型路徑和管理路徑。

| 方式 | 適用場景 | 怎麼開啟 | 客戶端地址 |
| --- | --- | --- | --- |
| 嵌入 Server（包括 Compose 和 Helm） | OpenViking Server 由你自己執行。不需要第二個程序，也不需要按路徑分流的反向代理。 | 在 `ov.conf` 中開啟 `gateway.enabled` | Server 地址加 `/gateway`，預設 `http://127.0.0.1:1933/gateway` |
| 獨立執行 | 不想改動 OpenViking 服務的配置，例如使用 OpenViking 商業版服務。 | 先 `openviking-gateway init`，再 `openviking-gateway` | 閘道器自己的地址加 `/gateway`，預設 `http://127.0.0.1:1935/gateway` |

選好之後，按你的部署方式閱讀對應小節：[在 Server 中啟用](#enable-it-in-the-server)、[Docker Compose](#docker-compose)、[Helm](#helm)或[獨立部署](#standalone-deployment)。

## 在 Server 中啟用 {#enable-it-in-the-server}

嵌入閘道器執行在 OpenViking Server 內部、和 Server 共用埠，預設關閉（`gateway.enabled` 為 `false`）。開啟之前，Studio 的 **OpenViking 閘道器**頁面會顯示**這臺 OpenViking 沒有開啟閘道器**。開啟方式有三種。

**用 `openviking-server init`。** 在 **Enable OpenViking Gateway on the same port?** 處回答 yes，然後啟動或重啟服務。已有配置時，在選單中選擇 **Update gateway**。遠端部署還會詢問是否允許使用者自行配置上游，見[閘道器管理金鑰](#gateway-management-key)。

**改 `ov.conf`。** 把下面的內容合併進 `ov.conf`，再重啟服務：

```json
{
  "gateway": {
    "enabled": true
  }
}
```

**在 Studio 中開啟。** 使用 API 金鑰的服務端上，root 可以在 Studio 的 OpenViking 閘道器頁面點**開啟閘道器**，Studio 會把 `gateway.enabled: true` 寫入 `ov.conf` 並重啟服務。確認對話方塊還可以順便生成閘道器管理金鑰，見[閘道器管理金鑰](#gateway-management-key)。幾種例外情況：

- 從 Studio 重啟要求服務端只有一個 worker，否則 Studio 只儲存檔案，需要你自行重啟。
- 設定了 `OPENVIKING_GATEWAY_ENABLED` 時，它會覆蓋 `ov.conf` 中的 `gateway.enabled`，值為 false 時重啟後閘道器仍不開啟。
- `ov.conf` 只讀時（例如由 Helm ConfigMap 掛載），Studio 改不了它。請在 Helm values 中設定 `gateway.enabled: true`，或者設定 `OPENVIKING_GATEWAY_ENABLED=true`，然後重啟服務。

**資料存放位置。** 未設定 `gateway.storage_path`（或 `OPENVIKING_GATEWAY_STORAGE_PATH`）時，嵌入閘道器把資料庫放在 `<storage.workspace>/gateway`。如果該目錄沒有閘道器資料庫，而舊的預設目錄 `~/.openviking/gateway` 有，服務端繼續使用舊目錄並列印警告；把目錄複製到新位置或設定 `storage_path` 即可消除警告。獨立閘道器仍預設使用 `~/.openviking/gateway`。

**確認已經開啟。** 開啟服務端的 `/studio/`，在側邊欄選擇 **OpenViking 閘道器**，應看到閘道器的各個標籤頁，而不是未開啟的提示卡片。本地 dev 模式下，如果預設帳號還沒有上游，閘道器啟動時會匯入服務端可用的 VLM 憑證作為上游，並建立 `default` 上下文配置。匯入的 Coding Plan 上游需要確認後才能使用；沒有可匯入的憑證時，請手動新增上游（見[新增上游](../gateway/07-upstreams.md#add-an-upstream)）。

**讓 Agent 修改配置。** 持有 root API 金鑰的 Agent 可以通過[執行時配置介面](../api/08-admin.md#runtime-configuration)修改 `ov.conf` 並重啟服務。獨立閘道器不提供這組介面。

## Docker Compose {#docker-compose}

用 Docker Compose 部署時，閘道器在 `openviking` 服務內執行，不需要單獨的服務或 profile。

1. 在 `.env` 中設定 `OPENVIKING_GATEWAY_ENABLED=true`，或者在掛載的 `ov.conf` 裡開啟 `gateway.enabled`。設定了這個變數時，以變數為準。
2. 確認掛載的 `ov.conf` 使用 API 金鑰認證：容器內 Server 監聽 `0.0.0.0`。
3. 執行 `docker compose up -d`，開啟 1933 埠上的 `/studio/`，選擇 **OpenViking 閘道器**，應看到閘道器的各個標籤頁。服務沒起來時，用 `docker compose logs openviking` 檢視啟動錯誤。

不用 Compose 時，`docker run` 加上 `-e OPENVIKING_GATEWAY_ENABLED=true` 即可：

```bash
docker run -d -p 1933:1933 -v ~/.openviking:/app/.openviking \
  -e OPENVIKING_GATEWAY_ENABLED=true \
  ghcr.io/volcengine/openviking:latest
```

- **管理金鑰**：在 `.env` 中設定 `OPENVIKING_GATEWAY_MANAGEMENT_KEY`，自帶的 Compose 檔案會把它傳進容器；也可以寫進掛載的 `ov.conf` 的 `gateway.management_key`。Compose 檔案還會傳入 `OPENVIKING_GATEWAY_ENCRYPTION_KEY`，它只在遷移 v0.5 資料時讀取一次，見[遷移](#migration)。
- **對外地址**：設定 `OPENVIKING_PUBLIC_BASE_URL`（自帶的 Compose 檔案會傳入）即可，閘道器沒有單獨配置 `public_url` 時沿用它。見[對外地址](#public-address)。
- **修改配置後**：改了掛載的 `ov.conf`，執行 `docker compose restart openviking`；改了 `.env`，執行 `docker compose up -d`，因為 `restart` 沿用原來的容器，讀不到 `.env` 的新值。

自帶的 Caddy 把所有路徑轉發到 `openviking:1933`。可以繼續用相容埠 1934，也可以直接訪問 Server 的 1933。配置 HTTPS 時，一條 `reverse_proxy openviking:1933` 就能承載 Studio、管理介面和模型流量，見[公網訪問](12-public-access.md)。

獨立容器需要掛載 `gateway.conf` 並使用閘道器命令。在檔案中設定 `host: "0.0.0.0"`，以及啟用 API key 認證的 `openviking_url`。選擇包含所配置功能的映象：

```bash
docker run -d --no-healthcheck -p 1935:1935 \
  -v "$PWD/gateway.conf:/etc/openviking/gateway.conf:ro" \
  -v gateway-data:/app/.openviking \
  ghcr.io/volcengine/openviking:'<gateway-image-tag>' openviking-gateway
```

`--no-healthcheck` 關閉映象自帶的 1933 埠 Server 探針。獨立閘道器改用 `http://localhost:1935/health` 探測。

## Helm {#helm}

用嵌入式 `deploy/helm/openviking` chart 部署時，在 chart values 中設定 `gateway.enabled: true`。閘道器嵌入 server 容器，資料儲存在 `<persistence.mountPath>/gateway`，Service 和 Ingress 都使用 Server 埠。保持 `replicaCount: 1`。

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
- 模型請求是流式的：Ingress 要關閉響應緩衝，允許至少 32 MiB 的請求體和 600 秒超時（見[反向代理和 HTTPS](#reverse-proxy-and-https)）。

NGINX annotations、建立 Secret 的命令和從 sidecar 版本升級的說明見 [chart README](https://github.com/volcengine/OpenViking/blob/main/deploy/helm/README.md#openviking-gateway)。

獨立部署使用 `deploy/helm/openviking-gateway`。它有自己的 80 埠 Service，轉發到 1935，並執行 `openviking-gateway`。`config` 值是獨立的 `gateway.conf` 物件，chart 固定 `host`、`port` 和 `storage_path`。

在包含這些功能的版本釋出之前，需要把 `image.tag` 設為包含它們的構建，見 [chart README](https://github.com/volcengine/OpenViking/blob/main/deploy/helm/README.md#standalone-openviking-gateway)。

```bash
helm upgrade --install gateway ./deploy/helm/openviking-gateway \
  --set-string image.tag='<gateway-image-tag>' \
  --set-string config.openviking_url=https://ov.example.com
```

預設使用單副本 SQLite、持久卷和 `Recreate` 更新策略。叢集必須有預設 StorageClass，或配置 `persistence.storageClass`/`persistence.existingClaim`。設定 `persistence.enabled: false` 後，更換 Pod 會丟失 SQLite 狀態，Helm NOTES 會顯示警告。解除安裝會保留 PVC。擴容前必須把兩個 provider 都改成 Redis，見[擴充](#scaling)。

chart 設定了 `session_ttl_seconds: 604800` 和 `response_ttl_seconds: 604800`，比閘道器 30 天的預設值短；需要其他值時覆蓋 `config.*`。每個 Pod 請求 500m CPU 和 1Gi 記憶體，上限為 2 CPU 和 4Gi；可按負載設定 `resources`。

獨立 chart 的 `existingSecret` 接受 `management-key`、`redis-password` 和 `root-key`。前兩項分別注入 `OPENVIKING_GATEWAY_MANAGEMENT_KEY` 和 `OPENVIKING_GATEWAY_REDIS_PASSWORD`；`config.storage.redis.password_env` 指向後者。local 和 KMS 加密把 `root-key` 只讀掛載到 `/etc/openviking-gateway/keys/root-key`，並將 provider 的 `key_file` 指向它。安裝前先按[加密](#encryption)生成金鑰。上游憑證和 KMS AK/SK 在 `config` 中寫 `$VAR`，通過 `extraEnv` 的 `secretKeyRef` 注入，不要將明文憑證寫入 ConfigMap。

`extraVolumes` 和 `extraVolumeMounts` 支援私有 CA 檔案；`extraEnv`、`podLabels`、`podAnnotations`、`nodeSelector`、`affinity`、`tolerations`、`imagePullSecrets` 用於部署環境的其他設定。ConfigMap 變化通過 `checksum/config` 觸發滾動更新。外部 Secret 改動後需要重啟 Deployment，讓所有副本載入一致的憑證。

chart 不建立 Ingress。把代理指向它的 Service，並保持 `fullnameOverride`、`nameOverride` 和 release 名不變：Service 和 Deployment 同名，selector 是 `app.kubernetes.io/name` 與 `app.kubernetes.io/instance`。直接對外開放時，配置 `service.type: LoadBalancer` 和 `service.loadBalancerSourceRanges`。可選的 `networkPolicy.enabled` 將 1935 埠入站限制為 `networkPolicy.ingressFrom`，空列表會拒絕入站。放行代理實際的來源網段或 Pod selector，並在所用 CNI 上驗證 kubelet 探針。

## 獨立部署 {#standalone-deployment}

獨立閘道器不讀取 `ov.conf`，只需要知道 OpenViking 的地址，已有的開源版或商業版服務不用改配置。

1. 執行 `openviking-gateway init`。它依次詢問 OpenViking 地址（會實際訪問一次，並顯示服務端的認證模式和版本）、監聽地址（預設 `127.0.0.1:1935`），以及是否要求[管理金鑰](#gateway-management-key)。結果寫入 `~/.openviking/gateway.conf`，或者 `--config` 指定的檔案，只有你自己能讀：

   ```json
   {
     "openviking_url": "https://ov.example.com",
     "host": "127.0.0.1",
     "port": 1935
   }
   ```

2. 執行 `openviking-gateway`。它先完成[啟動檢查](#startup-checks)，然後在你選的地址上監聽。
3. 開啟閘道器的 `/studio/`，用 OpenViking 使用者、帳號管理員或 root 的 API 金鑰登入。應看到閘道器頁面，以及顯示閘道器所連 OpenViking 地址的連線頁。
4. 手動新增上游。獨立閘道器讀不到遠端服務的 VLM 配置，所以不能匯入模型配置。

之後想修改設定，再執行一次 `openviking-gateway init` 即可：它把當前值作為預設值，已有的金鑰不改就原樣保留。

### 設定從哪裡來 {#standalone-config-sources}

命令列只有 `--config` 一個引數。設定了 `--config` 或 `OPENVIKING_GATEWAY_CONFIG_FILE` 時，它必須指向已存在的檔案；兩者都沒設定時，閘道器讀取 `~/.openviking/gateway.conf` 和 `/etc/openviking/gateway.conf` 中第一個存在的檔案。環境變數可以覆蓋其中任何欄位，所以容器裡可以完全不用檔案：設定 `OPENVIKING_GATEWAY_OPENVIKING_URL`，再按需加上 `OPENVIKING_GATEWAY_HOST=0.0.0.0` 之類的變數。

兩處都沒有 OpenViking 地址時，閘道器退出，並提示執行 `openviking-gateway init` 或設定 `OPENVIKING_GATEWAY_OPENVIKING_URL`。全部欄位和覆蓋規則見[配置參考](../gateway/13-configuration.md#configuration-reference)。

### 啟動檢查 {#startup-checks}

選擇 Redis 後端時，啟動 PING 必須成功。地址、憑據錯誤或 Redis 不可達會使啟動失敗，Kubernetes 會重啟容器；滾動釋出使用 `maxUnavailable: 0`。執行時 Redis 故障不會改變 `/health`；鑑權階段儲存失敗返回純文本 HTTP 500，並在 stderr 輸出異常棧。

獨立閘道器開始監聽前會先檢查 OpenViking 的認證模式：

- OpenViking 使用 trusted 認證時，閘道器拒絕啟動。
- 繫結非迴環地址時，必須確認 OpenViking 使用 `api_key` 認證才會啟動。連線失敗或 HTTP 5xx 響應會輸出告警，並在 1、2、4、8、16、30 秒後依次重試，後續等待上限為 30 秒。dev 模式、未知認證模式以及 HTTP 404 等其他錯誤仍會立即退出。
- 迴環地址（`127.0.0.1`、`::1`、`localhost`）只探測一次，OpenViking 不可達時也能啟動；仍然拒絕 trusted 認證。
- 跨主機連線 OpenViking 時，請使用 TLS 或私有網路。

等待期間 HTTP 埠尚未監聽。Kubernetes 的啟動探針此時仍會失敗，應按預期的 OpenViking 中斷時長設定 `startupProbe` 預算（`periodSeconds × failureThreshold`）。例如 `periodSeconds: 2`、`failureThreshold: 150` 允許等待約 300 秒，之後 kubelet 會重啟容器。閘道器自身不另設啟動等待期限。

### 連線公共 OpenViking 服務 {#public-openviking-service}

獨立閘道器連線公共 OpenViking 服務 `https://api.vikingdb.cn-beijing.volces.com/openviking`、又沒有設定管理金鑰時，會對該服務的所有使用者開放。啟動日誌會顯示 `public_openviking_without_management_key` 告警，Studio 會顯示**這臺閘道器對所有 OpenViking 商業版使用者開放**：任何持有該服務 API 金鑰的人都能登入這臺閘道器，並修改所在帳號的上游。

閘道器只給你自己或團隊使用時，設定 `OPENVIKING_GATEWAY_MANAGEMENT_KEY` 後重啟即可限制修改。這不限制誰能登入，也不限制他們給自己簽發閘道器金鑰。

## 路由 {#routes}

兩種部署方式下，閘道器的所有 URL 都在 `/gateway` 下。嵌入部署中，Server 把整個 `/gateway` 字首交給閘道器，其他路徑仍由 Server 自己處理：

| 路徑字首 | 用途 |
| --- | --- |
| `/gateway/v1/` | 模型 API 和模型列表 |
| `/gateway/api/v3/` | 方舟相容客戶端 |
| `/gateway/api/compatible/v1/` | 方舟 Anthropic 相容客戶端 |
| `/gateway/uploads` | 工具上傳 |
| `/gateway/downloads` | 工具下載 |
| `/gateway/admin/` | 管理 API，需要認證 |

因此客戶端使用下面的 Base URL，把 `http://127.0.0.1:1933` 換成你的 Server 地址即可。各客戶端的具體設定見[把客戶端接入 OpenViking 閘道器](../gateway/03-connect-clients.md#connect-clients)。

| 客戶端 | Base URL |
| --- | --- |
| Claude Code 和 Anthropic SDK | `http://127.0.0.1:1933/gateway` |
| OpenAI 相容的客戶端和 SDK，包括 Codex、OpenCode、pi 和 Open WebUI | `http://127.0.0.1:1933/gateway/v1` |
| 火山方舟和 BytePlus 方舟 SDK | `http://127.0.0.1:1933/gateway/api/v3` |

`/health` 仍是 Server 自己的健康檢查，嵌入閘道器不單獨提供 `/health`。獨立閘道器在自己的埠上提供同樣的 `/gateway` 路徑，另外在根路徑提供兩個地址：

- `/` 跳轉到 `/studio/`，Studio 只包含閘道器和連線頁面。
- `/health` 返回 `service: "openviking-gateway"`、`auth_mode` 和 `openviking_url`；請求帶有效的 OpenViking 憑證時，還返回呼叫方身份。

### 對外地址 {#public-address}

對外地址 `public_url` 是客戶端訪問 Server（或獨立閘道器）時使用的地址，不帶 `/gateway`，閘道器會自己加上。它預設為空，此時嵌入閘道器沿用 Server 的對外地址（`OPENVIKING_PUBLIC_BASE_URL` 或 `server.public_base_url`）。共享部署都應設定它，前面有反向代理時更是必須設定：

- **嵌入**：在 `ov.conf` 中設定 `gateway.public_url`，然後重啟服務。
- **獨立**：設定 `gateway.conf` 中的 `public_url` 或環境變數 `OPENVIKING_GATEWAY_PUBLIC_URL`，然後重啟閘道器。

有兩樣東西依賴它：

- **Studio 的接入指南**：Anthropic 客戶端使用 `<public_url>/gateway`，OpenAI 風格的客戶端使用 `<public_url>/gateway/v1`。
- **OpenViking 工具的上傳和下載連結**，除非 `mcp_file_links` 設為 `direct`，見[匯入檔案和技能](../gateway/04-openviking-tools.md#import-files-and-skills)。

一個對外地址都沒有設定時，指南用的是請求到達伺服器時的協議和主機。經過反向代理時，這可能是內部地址或 `http://` 地址，**接入**標籤頁會提示**客戶端可能連不上這個地址**；如果是 `127.0.0.1` 這類迴環地址，則提示**只有閘道器所在的機器能使用這個地址**。

## 反向代理和 HTTPS {#reverse-proxy-and-https}

把整個站點轉發到 Server（嵌入）或閘道器（獨立），不需要按路徑分流。以 Caddy 為例：

```caddyfile
ov.example.com {
    reverse_proxy 127.0.0.1:1933 {
        flush_interval -1
    }
}
```

無論用哪種代理，都要滿足下面幾項：

| 設定 | 取值 | 原因 |
| --- | --- | --- |
| 響應緩衝 | 關閉 | 流式輸出才能即時到達 |
| 請求體大小 | 至少 32 MiB | 這是閘道器自身對請求和上傳的預設上限；長對話每次都傳送完整歷史（見[副作用](../gateway/05-long-conversations.md#side-effects)） |
| 讀取超時 | 至少 600 秒 | 閘道器預設最多等待服務商 600 秒 |
| `/gateway/uploads` 和 `/gateway/downloads` 的日誌 | 不記錄查詢字串 | 其中帶有一次性令牌 |

獨立閘道器的 `keep_alive_seconds`（預設 75）應大於負載均衡器的後端空閒超時。

響應頭髮出後，空閒事件流每 15 秒傳送一條 SSE 註釋（`: keep-alive`），包括執行 OpenViking 工具期間。SSE 客戶端會忽略註釋，模型事件和捕獲的回覆不受影響。代理的空閒超時應大於 15 秒，並關閉響應緩衝。心跳只在完整事件的邊界傳送，上游壓縮流禁用心跳，因此仍需保留上面的較長讀取超時，以覆蓋事件傳到一半或響應頭尚未到達時的等待。心跳間隔固定，不會延長服務商超時或工具的總時間限制。

對外發布前，先配置好認證和[對外地址](#public-address)，見[公網訪問](12-public-access.md)。

## 金鑰和憑證 {#keys-and-credentials}

閘道器涉及四種金鑰，各管一件事：

| 金鑰 | 用途 | 在哪裡使用 |
| --- | --- | --- |
| OpenViking API 金鑰 | 登入 Studio；決定以哪個帳號、哪個使用者的身份讀寫記憶 | 管理請求的 `X-API-Key` 或 `Authorization: Bearer` |
| 閘道器金鑰（`ovgw_…`） | 客戶端接入；每把繫結一位使用者、一份上下文配置和一組上游（見[閘道器金鑰](../gateway/09-gateway-keys.md#gateway-keys)） | 客戶端的 API Key 輸入框 |
| 閘道器管理金鑰（可選） | 限制誰能修改上游和上下文配置 | `gateway.management_key`；請求頭 `X-OpenViking-Gateway-Management-Key` |
| 上游 API Key | 呼叫模型服務商（見[憑證](../gateway/07-upstreams.md#credentials)） | 上游編輯頁 |

閘道器沒有自己的加密金鑰，本地儲存按 OpenViking 的加密配置加密，見[加密](#encryption)。

### 閘道器管理金鑰 {#gateway-management-key}

閘道器管理金鑰是一項可選的部署金鑰，用來限制誰能修改[上游和上下文配置](15-gateway.md#key-terms)。它預設不設定，此時帳號內每個登入的使用者都能新增和修改本帳號的上游和上下文配置。設定之後，只有帶上這把金鑰的請求能修改它們，帳號管理員和 root 也不例外。它不限制誰能登入，也不限制使用者給自己簽發閘道器金鑰。

只讀使用者在 Studio 裡還能看到什麼、做什麼，見[誰能修改什麼](../gateway/06-manage-in-studio.md#who-can-change-what)；包括管理 API 在內的完整規則見[許可權矩陣](../api/25-gateway.md#credentials-and-account-scope)。

**像部署金鑰一樣保管它。** 管理金鑰本身就能當憑證用，不需要 OpenViking API 金鑰：帶上 `account_id`，它可以檢視、建立、修改和刪除任意帳號的上游和上下文配置，包括把上游指向另一個服務商地址。但它讀不了記憶和日誌，也不能簽發閘道器金鑰。只把它交給維護上游的人。

設定方法：

- **`openviking-server init`**（嵌入）：遠端部署回答 **Allow users to configure their own gateway upstreams?** 時選 no，init 會生成一個以 `ovgm_` 開頭的值，列印出來並寫入 `ov.conf` 的 `gateway.management_key`。
- **`openviking-gateway init`**（獨立）：回答 **Require a management key to change upstreams and profiles?** 時選 yes，init 會生成一個 `ovgm_` 開頭的值，只列印一次，並寫入 `gateway.conf` 的 `management_key`。
- **Studio**（嵌入，root）：點**開啟閘道器**後彈出的確認對話方塊裡有一個核取方塊**只有持有閘道器管理金鑰的人才能修改上游和上下文配置**，預設不勾選。勾選後，Studio 會生成一個 `ovgm_` 開頭的值，寫入 `ov.conf` 的 `gateway.management_key`（同時寫入 `gateway.enabled: true`），並且只顯示一次。
- **手動設定**：值至少 32 個字元，可以用 `openssl rand -base64 32` 生成。寫進 `management_key`，或者設定環境變數 `OPENVIKING_GATEWAY_MANAGEMENT_KEY`；兩種部署下環境變數都優先於配置檔案，見[配置參考](../gateway/13-configuration.md#configuration-reference)。
- **Compose 和 Helm**：Compose 會把 `OPENVIKING_GATEWAY_MANAGEMENT_KEY` 傳進容器；Helm 從 `gateway.existingSecret`（嵌入）或 `existingSecret`（獨立）指定的 Secret 中讀取 `management-key` 欄位。見 [Docker Compose](#docker-compose) 和 [Helm](#helm)。

管理金鑰不提供命令列引數，因為命令列引數會出現在程序列表和 shell 歷史裡。設定、更換或去掉管理金鑰後需要重啟，這不會弔銷已簽發的閘道器金鑰，也不會改動已有的上游和上下文配置。

#### 忘記閘道器管理金鑰 {#lost-the-management-key}

沒人記得[閘道器管理金鑰](#gateway-management-key)時，按閘道器讀取它的順序查詢：

1. 環境變數 `OPENVIKING_GATEWAY_MANAGEMENT_KEY`，它優先於配置檔案。Compose 部署一般寫在 `docker-compose.yml` 旁邊的 `.env` 裡；Helm 從 `gateway.existingSecret`（嵌入）或 `existingSecret`（獨立）指定的 Secret 中讀取 `management-key` 欄位。
2. 沒有設定環境變數時，看 `ov.conf` 的 `gateway.management_key`（嵌入）或 `gateway.conf` 的 `management_key`（獨立）。值寫成 `$VAR` 時，金鑰在對應的環境變數裡。

嵌入部署的 root 還可以在 Studio 的**設定** → **服務端配置** → **檔案編輯**中檢視 `ov.conf`。`openviking-server init` 和 Studio **開啟閘道器**生成的金鑰都以明文儲存在這裡。

實在找不回來，就換一把新的：

1. 生成一個至少 32 個字元的新值，例如用 `openssl rand -base64 32`。
2. 寫到原來的位置。把環境變數設為空字串不會清除檔案裡的值，需要刪掉這個變數。
3. 重啟。Compose 部署改了 `.env` 之後，要執行 `docker compose up -d` 才會生效，`docker compose restart` 讀不到新值。
4. 在 Studio 中點**輸入閘道器管理金鑰**，貼上新值。已簽發的閘道器金鑰、上游和上下文配置都不受影響。

## 加密 {#encryption}

閘道器用 OpenViking 自己的加密功能保護已存的憑證和對話狀態（見[加密指南](08-encryption.md)）。加密關閉或沒有配置時，閘道器以明文儲存，依靠儲存訪問控制保護。

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

共享部署的每個副本必須只讀掛載同一份 root key。local provider 使用**十六進位制文本**，不要生成原始位元組：

```bash
umask 077
openssl rand -hex 32 > gateway-root-key
kubectl create secret generic gateway-credentials --from-file=root-key=gateway-root-key
```

設定 `existingSecret: gateway-credentials`、`config.encryption.enabled: true` 和 `config.encryption.provider: local`。需要時，在同一個 Secret 中新增 `management-key` 和 `redis-password`。

使用 `provider: volcengine_kms` 時，`root-key` 是 **KMS 密文檔案**，不是十六進位制文本。在受保護的本地可寫目錄中，把 `encryption.volcengine_kms.key_file` 設為絕對路徑，通過環境變數引用提供 KMS 憑證，啟動一次閘道器。啟動成功後停止，將生成的檔案放入 Secret 的 `root-key`。各副本使用一致的 KMS key ID 和憑證。檔案不存在時，provider 會在首次使用時生成；只讀 Secret 掛載下生成失敗，閘道器會拒絕啟動。Vault 將加密 root key 儲存在 Vault 中，不使用這個檔案掛載。

之後修改加密設定時：

- **開啟加密**不會出問題：已有的明文值照常可讀，新寫入的值會加密。
- **關閉加密或換一把加密根金鑰**後，已加密的值就讀不出來了，所以要保持寫入時的加密設定。
- **丟失加密根金鑰**後，閘道器的資料庫就無法讀取。請按加密指南備份加密根金鑰。

v0.5 閘道器用自己的金鑰加密資料，這些資料會在首次啟動時轉換，見[遷移](#migration)。

## 擴充 {#scaling}

SQLite 供一臺主機上的一套部署使用，不要跨主機共享目錄，也不要讓嵌入閘道器和獨立閘道器共用。獨立程序支援 `workers: 1–64`，Kubernetes 中建議 `workers: 1`，通過增加 Pod 擴容。嵌入閘道器遵循 Server 的 worker 和副本限制。

獨立閘道器使用多副本時，必須把 **`storage.kernel` 和 `storage.management` 都設為 `redis`**，共享同一份 `storage.redis` 連線與 `storage.key_prefix`，並只讀掛載同一份加密 root key。任一 provider 是 SQLite 時，chart 會拒絕多副本。下面是雙副本的起點，需要合併你的 URL 和 Secret 設定：

```yaml
replicaCount: 2
existingSecret: gateway-credentials
config:
  capture_concurrency: 4
  storage:
    kernel: redis
    management: redis
    key_prefix: "ovgw:"
    redis:
      mode: standalone
      endpoints: ["redis://redis:6379"]
      password_env: OPENVIKING_GATEWAY_REDIS_PASSWORD
  encryption:
    enabled: true
    provider: local
```

無管理面、按金鑰隔離的部署再加上 `management_api: false`、`openviking_keys: true`、`tenancy: key`、`default_upstreams` 和 `request_log_sink: stdout`，見[直接使用 OpenViking API 金鑰](../gateway/09-gateway-keys.md#openviking-keys)和[部署預設上游](../gateway/07-upstreams.md#deployment-default-upstreams)。沒有管理 API 時，在 OpenViking 中刪除使用者不會通知閘道器，該使用者的閘道器資料按[保留期限](../gateway/11-security-and-data.md#retention)過期。部署在它前面的服務遵循[宿主整合約定](#host-integration-contract)。

Redis `mode: standalone` 用於單個端點，包括託管代理；`mode: cluster` 用 Redis Cluster 端點且資料庫必須為 0。TLS 用 `rediss://`，端點 URL 中不要寫憑證。`pool_size` 限制每個程序同時執行的 Redis 命令數，超出的命令等待空閒連線。保持 `pool_size >= capture_concurrency + 8`。Redis 位於鑑權路徑，整體不可用時請求返回 HTTP 500；需要高可用時使用主從和自動切換，記憶體和持久化按 [Redis 記憶體策略](#redis-memory-policy)配置。

Redis 部署使用 `RollingUpdate`，配置 `maxUnavailable: 0`、`maxSurge: 1`；多副本時建立 `maxUnavailable: 1` 的 PDB。通過 `affinity` 把副本分散到不同節點。各程序快取管理記錄，所以修改管理配置或吊銷簽發金鑰後，其他副本最多 **2 秒**後生效。

所有探針都不帶憑證訪問 `/health`，只返回本地狀態，不呼叫 OpenViking 或 Redis。startupProbe 預算為 300 秒（`2 × 150`）。啟動完成後，OpenViking 故障不會使 Pod 摘流。

停機預算是 `15s preStop + upstream_timeout_seconds + 最多 100s capture 排空`。chart 預設的 `terminationGracePeriodSeconds: 660` 覆蓋 preStop 和一條持續到預設 600 秒上游超時的流；capture 尚未排空就被 Kubernetes 終止時，其他副本會在 lease 到期後接手。要讓 capture 在 Pod 被終止前排空，把它調到 `15 + upstream_timeout_seconds + 100`（預設超時下為 715）。

### 宿主整合約定 {#host-integration-contract}

部署在無管理面閘道器前面的服務（例如為每個請求選擇模型端點的服務）轉發客戶端請求時，設定這些請求頭：

| 請求頭 | 取值 |
| --- | --- |
| `X-API-Key` 或 `Authorization: Bearer` | 客戶端的 OpenViking API 金鑰，原樣透傳 |
| `X-OpenViking-Upstream-URL` | 選中的端點，必須與某個 `default_upstreams` 條目的 `base_url` 相同；其他值返回 403，且不發出任何請求。見[按請求指定上游](../gateway/07-upstreams.md#upstream-url-header) |
| `X-OpenViking-Upstream-Key` | 服務商 API Key，用於 `auth_mode: passthrough` 的上游 |
| 其他請求頭 | 客戶端自己的請求頭，例如 `X-OpenViking-Session` 和 `X-OpenViking-Context`，原樣透傳 |

閘道器把請求轉發給服務商之前，會去掉所有 `X-OpenViking-*` 請求頭、客戶端憑證和逐跳請求頭。

## Redis 記憶體策略 {#redis-memory-policy}

為閘道器單獨準備 Redis 例項，不要與 OpenViking 的 `expiry_redis_host` 定時器儲存共用。從下面的 `redis.conf` 開始，按負載設定 `maxmemory`：

```conf
maxmemory 2gb
maxmemory-policy volatile-lru
appendonly yes
appendfsync everysec
```

`volatile-lru` 只驅逐本來就會過期的資料：對話狀態、replay、待投遞 capture 和 OpenViking 金鑰記錄。每類資料丟失的影響見 [Redis 對話狀態](../gateway/11-security-and-data.md#redis-conversation-state)。不要使用 `allkeys-*`：它也會驅逐沒有 TTL 的資料，導致簽發的金鑰、上游和上下文配置消失，已刪除的對話狀態可能重新出現，待投遞 capture 不再被排程。`noeviction` 也能執行，但記憶體滿後寫入失敗，請求無法獲得記憶增強。

監控 `evicted_keys` 的增速和記憶體用量；容量充足時不會發生驅逐。閘道器不檢查驅逐策略或其他任何 Redis 設定。觀察 capture 積壓可用 `ZCARD <key_prefix>v1:k:{cap}:ready`，它統計已排程或正在處理的 capture，其中可能有少量稍後才清理的過期條目。Redis Cluster 中所有 capture 資料位於同一個分片，應為 OpenViking 故障期間的積壓預留該分片容量。capture lease 使用 Redis 時鐘，排程時間則來自閘道器宿主，各宿主應通過 NTP 保持時鐘同步。

未啟用持久化時，Redis 重啟會刪除閘道器的全部管理資料：已簽發的閘道器金鑰失效，上游和上下文配置需要重新設定。AOF 讓這些資料、待投遞 capture 和刪除操作在重啟後保留。在 Redis 7.2 上，禁用的 `default` 使用者也要保留命令許可權（例如 `user default off ~* &* +@all`）：AOF 回放事務時會檢查這些許可權，缺少時回放的寫入會因 `NOPERM` 失敗。`appendfsync everysec` 仍可能丟失約一秒的寫入，非同步主從切換也可能丟失最近的寫入。AOF 重寫和快照期間需為寫時複製預留記憶體。備份中可能保留其生成之後才刪除的資料。

## 觀測與例行檢查 {#monitoring}

閘道器不匯出 Prometheus 之類的監控指標。請求日誌預設寫入儲存，可通過 Studio 的[概覽和請求日誌](../gateway/10-overview-and-requests.md#overview)標籤頁檢視，或者呼叫管理 API 的 `/gateway/admin/overview` 和 `/gateway/admin/logs`。

在閘道器配置中設定 `request_log_sink: "stdout"`，或設定 `OPENVIKING_GATEWAY_REQUEST_LOG_SINK=stdout`，重啟後新記錄只寫到 stdout。每個完成的模型請求和後臺儲存狀態變更各產生一行 JSON，即使 stdout 接到管道也會立即重新整理。每條記錄包含 `time`（寫入時的 Unix 秒數）、`account`、`user_id`（舊儲存狀態可能為 `null`），以及位於頂層的現有請求指標，如 `kind`、`status`、`input_tokens` 和 `cached_tokens`。不包含憑證、提示詞或回覆。採集系統負責這些記錄的保留期限和訪問許可權；`log_retention_days` 只作用於儲存中的日誌。

當 `management_api: false` 關閉 Studio 和管理介面時，配置 stdout sink 並採集程序或容器日誌進行觀測。管理面開啟但選擇 stdout sink 時也採用同樣流程：請求日誌頁和概覽中的請求統計不會收到新記錄。之前已儲存的記錄仍可見，直到過期。

從請求日誌的頂層欄位統計 reason 和首調快取結果。對 capture 暫停（`kind: capture`）、佇列增長、`openviking_http_429`、Redis 記憶體/驅逐和 HTTP 錯誤率設定告警。identify 拒絕發生在代理請求記錄之前，所以從代理訪問日誌統計 401/402/403 和 Redis 故障引發的 500，具體 traceback 看閘道器 stderr。代理併發連線數可以近似表示在途流數。確認平臺實際採集 stdout；只掛一個目錄不會把它轉成檔案日誌。

### 例行檢查 {#day-to-day-operations}

- **程序存活：** `/health`。嵌入部署用的是 Server 的健康檢查，獨立部署用的是閘道器自己的。
- **閘道器健康：** **概覽**標籤頁上的**首次呼叫快取命中率**（[含義](../gateway/10-overview-and-requests.md#overview)），或從 stdout 指標計算：在同一帳號和時間視窗內，篩選 `kind: "user"` 的記錄，將 `first_upstream_cached_tokens` 的總和除以 `first_upstream_input_tokens` 的總和。某個欄位缺失時，用該條記錄的 `cached_tokens` 或 `input_tokens` 代替（未報告的用量按 0 計）。分母為零表示沒有報告輸入用量。這些欄位位於頂層，不在巢狀的 `metrics` 物件中。命中率明顯下降時，見[首次呼叫快取命中率下降](../gateway/12-troubleshooting.md#the-first-call-cache-hit-rate-dropped)。
- **單個請求：** 在**請求日誌**標籤頁展開對應的行，或按 `account`、`user_id` 和 `request_id` 查詢 stdout 記錄；見[請求日誌](../gateway/10-overview-and-requests.md#requests)。後臺儲存事件的 `kind` 為 `capture`，通過雜湊後的 `session` 標識對話。
- **對外地址：** `public_url` 仍是客戶端訪問的地址，見[對外地址](#public-address)。
- **備份：** SQLite 目錄或 Redis 持久化/備份；開啟加密時還有加密根金鑰，見[備份與恢復](../gateway/11-security-and-data.md#backups)。

## 升級 {#upgrades}

- 升級前讀釋出說明。新版本的閘道器讀不了舊的儲存格式時，啟動會報 `Unsupported gateway schema`，見[閘道器無法啟動](../gateway/12-troubleshooting.md#the-gateway-does-not-start)。
- 獨立閘道器要求 OpenViking Server 不低於 `min_server_version`（0.4.16），否則無法簽發金鑰，儲存重試也會以 `openviking_version_mismatch` 失敗；記憶檢索也可能失敗，顯示為 `openviking_http_<status>`。兩者分開升級時，先升級 OpenViking，再升級閘道器。嵌入閘道器和 Server 同版本釋出，不做這項檢查。
- 從 sidecar 或舊版獨立閘道器升級，見[遷移](#migration)。

- SQLite 切換到 Redis 後，會話快取從空開始。management 儲存中的已簽發 `ovgw_` 金鑰、上游和上下文配置需要重建，沒有提供遷移命令。使用 OpenViking key 時，可以通過部署預設值提供上游和上下文配置。
- Redis 鍵包含佈局版本（`<storage.key_prefix>v1:`）。佈局相同時，回滾可以繼續讀現有狀態。將來佈局版本變化時從空開始：會話資料按快取處理，OpenViking key 記錄在訪問時重建，使用簽發金鑰的部署需要重新配置。不要假設存在跨版本資料遷移。
- 緊急停用時移除代理路由，或將閘道器 Deployment 縮到零。客戶端可以把 Base URL 改回模型服務商，繼續使用原模型憑證，此時沒有閘道器記憶能力。`helm rollback` 的目標構建必須相容當前配置欄位和 Redis 佈局。

## 從早期版本遷移 {#migration}

以下步驟適用於從早期版本的 sidecar 或獨立閘道器遷移到嵌入閘道器。第 4 步和第 7 步的細節見列表後面的兩張表。

1. **先備份。** 備份 `storage_path`（兩個資料庫，以及存在的話 `encryption.key`）。停止舊的閘道器程序或 sidecar，再啟用嵌入閘道器。
2. **刪掉舊欄位。** 從 `ov.conf` 的 `gateway` 段刪除 `host`、`port`、`workers`、`url`、`openviking_url`、`admin_token_env` 和 `encryption_key_env`。Server 會忽略這些欄位並在啟動時列印警告，舊的 `ov.conf` 仍能啟動，但還是應該清理掉；`openviking-server init` → **Update gateway** 會自動刪除它們。

   想繼續獨立執行閘道器，就執行 `openviking-gateway init`，或者把設定移到單獨的 `gateway.conf`，去掉 `gateway` 外層和 `enabled`。獨立閘道器的命令不再接受 `--openviking-url`、`--host`、`--port`、`--workers` 和 `--storage-path`，這些設定改寫到 `gateway.conf` 或環境變數中。
3. **改對外地址。** 把 `public_url` 改為 Server 的對外地址（不帶 `/gateway`），或者刪掉。舊版快速開始把它設成了 `http://127.0.0.1:1935`，嵌入閘道器不再監聽這個埠，接入指南和上傳連結都會指向一個不存在的地址。`openviking-server init` → **Update gateway** 發現 `public_url` 指向別的埠時，會詢問是否清除。
4. **改客戶端地址和部署配置。** 閘道器的所有 URL 現在都在 `/gateway` 下，所以客戶端要同時改埠和路徑，舊路徑不再提供服務，見[新地址](#new-addresses)。移除舊的 1935 Service 和 Ingress 路由、Compose 的 `gateway` 服務和 profile，以及 Helm 的 sidecar 配置 `gateway.workers`、`gateway.port`、`gateway.resources`。
5. **首次啟動會轉換已存資料。** v0.5 閘道器用自己的金鑰加密資料。新版閘道器（嵌入或獨立）首次啟動時，用這把舊金鑰解密，再按當前的[加密](#encryption)設定重新寫入；加密關閉時寫成明文，所以想讓資料繼續加密，要在這次啟動前開啟 OpenViking 加密。

   舊金鑰從環境變數 `OPENVIKING_GATEWAY_ENCRYPTION_KEY` 讀取，或者從 `storage_path` 下的 `encryption.key` 讀取。`encryption_key_env` 會被忽略：如果你曾用它指向別的環境變數，這次啟動時把金鑰匯出為 `OPENVIKING_GATEWAY_ENCRYPTION_KEY`。存在舊的加密資料、兩處卻都沒有金鑰時，閘道器拒絕啟動，錯誤資訊會寫明這兩個位置。用嵌入式 Helm chart 時，只在這次升級的版本中保留 `gateway.existingSecret` 裡的 `encryption-key` 欄位。獨立 chart 在這次升級時通過 `extraEnv` 注入遷移變數。啟動成功後舊金鑰不會再被讀取，可以刪掉這個環境變數、Secret 欄位和 `encryption.key`。
6. **移除共享 admin token。** `OPENVIKING_GATEWAY_ADMIN_TOKEN` **不會**被當作管理金鑰。需要限制誰能修改上游和上下文配置時，顯式設定 `management_key`，見[閘道器管理金鑰](#gateway-management-key)。
7. **核對上游地址。** 首次啟動時，閘道器會改寫一次已存上游的 Base URL，讓每個上游繼續請求升級前的同一個地址，見[已存上游地址的變化](#upstream-address-rewrite)。在**上游**標籤頁對每個上游點**測試**，確認它仍然可用。
8. **瞭解日誌和吊銷的變化。** 請求日誌新增使用者列，沒有使用者的舊記錄只出現在帳號管理員和 root 的檢視中。吊銷金鑰不再刪除使用者資料，顯式刪除和保留期照常生效。

### 新地址 {#new-addresses}

把 `host` 換成你的 Server 地址：

| 物件 | 遷移前 | 遷移後 |
| --- | --- | --- |
| OpenAI 相容客戶端 | `http://host:1935/v1` | `http://host:1933/gateway/v1` |
| Claude Code 的 `ANTHROPIC_BASE_URL` | `http://host:1935` | `http://host:1933/gateway` |
| 火山方舟和 BytePlus 方舟 SDK | 舊的閘道器地址 | `http://host:1933/gateway/api/v3` |
| 呼叫管理 API 的指令碼 | `/api/v1/admin/gateway/...` | `/gateway/admin/...` |

1935 仍是獨立執行的預設埠，獨立閘道器也使用同樣的 `/gateway` 路徑。

### 已存上游地址的變化 {#upstream-address-rewrite}

| 上游 | 已存的 Base URL | 首次啟動後 |
| --- | --- | --- |
| 火山方舟和 BytePlus 方舟的 Chat Completions、Responses 上游 | 只有域名 | 補上 `/api/v3` |
| 其他 Chat Completions、Responses 上游 | 路徑不以 `/v1`、`/v4` 這類版本段結尾，包括純域名和帶路徑字首的地址 | 補上 `/v1`：`https://api.deepseek.com` → `https://api.deepseek.com/v1`，`https://openrouter.ai/api` → `https://openrouter.ai/api/v1`，或者掛在 `/litellm` 下的自建代理 |
| 火山方舟和 BytePlus 方舟的 Anthropic 上游 | 只有域名 | 補上 `/api/compatible` |
| Anthropic 上游 | 以 `/v1` 結尾 | 去掉 `/v1` |
| 任意上游 | 已經以其他版本段結尾，例如智譜的 `https://open.bigmodel.cn/api/paas/v4` | 保持不變。升級前它會被拼成 `…/v4/v1` 而請求失敗，升級後按填寫的地址直接可用。 |

新建和修改的上游按 [Base URL 的拼接規則](../gateway/07-upstreams.md#base-url)拼接，以 `/v1` 結尾的 Anthropic Base URL 會被拒絕。

## 下一步 {#next-steps}

- [在 Studio 中管理 OpenViking 閘道器](../gateway/06-manage-in-studio.md)：新增上游、建立上下文配置，簽發第一批閘道器金鑰。
- [安全與資料](../gateway/11-security-and-data.md)：瞭解閘道器存了什麼、誰能訪問，以及怎麼備份和刪除資料。
- [OpenViking 閘道器排障](../gateway/12-troubleshooting.md)：根據啟動錯誤、設定卡片或失敗的請求找到解決辦法。
