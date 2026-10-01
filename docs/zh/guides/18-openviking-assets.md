# OpenViking Assets

> 實驗性功能。`openviking-assets/1` 協議和命令列行為仍可能在後續版本中調整。

OpenViking Assets 用宣告檔案描述“一個知識庫應該由哪些資源組成”。最簡單的形態是
一個 Manifest 檔案直接定義要接入的資產；團隊也可以在共享的 Catalog 中維護可接入
資源的全集，再用多個 Manifest 按名稱選擇不同用途所需的資源。執行 Manifest 時，
OpenViking 會逐項建立或更新資源，並在本地儲存資產與 `viking://` 資源之間的對映。

它適合管理多倉程式碼問答庫、團隊文件集和其他需要重複構建、持續更新的資源集合。

## 與其他資源操作的區別

| 能力 | 描述 |
| --- | --- |
| `ov add-resource <source>` | 新增或更新一個資源，描述的是一次資源操作。 |
| OpenViking Assets | 宣告一組資源的預期構成，可以 review、共享並重復執行。 |
| OVPack | 匯出或匯入已經生成的資料快照，搬運的是內容和可選索引資料。 |

OpenViking Assets 不替代現有資源處理流程。Git 拉取、內容解析、語義提取、向量化和
Watch 更新仍由 `add_resource` 及服務端連接器完成；Assets 只增加宣告、解析和逐項編排。

## 概念模型

OpenViking Assets 包含三個主要物件：

- **Manifest**：實際執行的檔案。可以在 `catalog:` 下直接定義要接入的資產，也可以按名稱
  從單獨的 Catalog 檔案中選擇資產。
- **Catalog**：團隊可接入資源的目錄，包含來源、分支、預設更新週期和憑據別名。只有在多個
  Manifest 需要共享時才作為單獨檔案存在，否則直接寫在 Manifest 裡。
- **State**：某個 Manifest 上次執行的結果，以及資產到 `viking://` 資源的對映。

```text
manifest.yaml（使用共享 Catalog 時再加 catalog.yaml）
          |
          v
服務端解析和校驗 openviking-assets/1
          |
          v
Resolved Assets
          |
          v
CLI 解析本地憑據和 State
          |
          v
逐個呼叫 add_resource -> viking:// resources
```

服務端是協議解析的權威實現。CLI 會把 Manifest 的原始 YAML（使用單獨 Catalog 檔案時
一併傳送 Catalog YAML）傳送到當前配置的 OpenViking 服務，由服務端完成嚴格校驗並返回
執行計劃；服務端的解析介面本身不會建立資源。

## 協議

### Manifest

Manifest 描述一次知識庫構建。最簡單的形態下它是唯一需要的檔案：在 `catalog:` 下
直接定義資產：

```yaml
protocol: openviking-assets/1

defaults:
  git:
    auth_ref: team-git
    watch_interval: 60

catalog:
  - name: openviking
    connector: git
    description: OpenViking 主倉庫
    params:
      repo_url: https://github.com/volcengine/OpenViking
      branch: main

  - name: requests
    connector: git
    description: Requests HTTP 客戶端原始碼
    watch_interval: 0
    params:
      repo_url: https://github.com/psf/requests
      branch: main

assets: [openviking]   # 可選：省略 = 執行上面定義的全部資產
```

Manifest 頂層欄位：

| 欄位 | 必填 | 說明 |
| --- | --- | --- |
| `protocol` | 定義 `catalog` 時必填 | 當前必須為 `openviking-assets/1`；只按名稱選擇資產的 Manifest 可省略，但設定時同樣會校驗。 |
| `defaults` | 否 | 為本檔案定義的資產設定連接器級預設值；只能與 `catalog` 一起使用。 |
| `catalog` | 否 | 資產定義列表（欄位見下）。定義了 `catalog` 的 Manifest 自身就是完整配置。 |
| `assets` | 見說明 | 要執行的資產名稱。`catalog` 在同一檔案中時可省略——省略表示執行全部定義的資產；資產定義在單獨 Catalog 檔案中時必填。 |
| `include` | 否 | v1 不支援組合其他 Manifest；非空時解析失敗。 |

重複的資產名稱會按首次出現的位置去重。選擇不存在的資產時，整個解析失敗。

`defaults.git` 支持：

| 欄位 | 說明 |
| --- | --- |
| `auth_ref` | 本地憑據檔案中的預設別名。 |
| `watch_interval` | 預設 Watch 週期，單位為分鐘；`0` 表示不自動重新整理。 |

Git 資產支援：

| 欄位 | 必填 | 說明 |
| --- | --- | --- |
| `name` | 是 | 唯一資產名稱，必須匹配 `[A-Za-z0-9][A-Za-z0-9._-]*`。 |
| `connector` | 是 | v1 只支持 `git`。 |
| `description` | 否 | 資產用途說明。 |
| `params.repo_url` | 是 | Git clone URL。 |
| `params.branch` | 否 | 要接入的分支；設定時不能為空。 |
| `auth_ref` | 否 | 覆蓋 `defaults.git.auth_ref`。 |
| `watch_interval` | 否 | 覆蓋 `defaults.git.watch_interval`。 |

校驗是嚴格的：未知欄位、重複資產名和不支援的連接器都會使整個解析失敗，即使有問題的資產
沒有被本次執行選擇。`params` 內容和 clone URL 安全性針對被選中的資產校驗。這些規則與
資產定義所在的位置無關——寫在 Manifest 的 `catalog` 裡和寫在單獨的 Catalog 檔案裡完全相同。

### 多個 Manifest 共享一個 Catalog

當多個 Manifest 複用同一批資源時，把資產定義移到單獨的 Catalog 檔案中，通常命名為
`catalog.yaml`。Catalog 包含 `protocol`、可選的 `defaults`，以及同樣的 `catalog` 塊——
一份 Catalog 檔案就是一個不做選擇的 Manifest：

```yaml
protocol: openviking-assets/1

defaults:
  git:
    auth_ref: team-git
    watch_interval: 60

catalog:
  - name: openviking
    connector: git
    description: OpenViking 主倉庫
    params:
      repo_url: https://github.com/volcengine/OpenViking
      branch: main

  - name: requests
    connector: git
    description: Requests HTTP 客戶端原始碼
    watch_interval: 0
    params:
      repo_url: https://github.com/psf/requests
      branch: main
```

每個 Manifest 只需按名稱選擇：

```yaml
assets:
  - openviking
  - requests
```

全團隊維護一份 Catalog；在 Catalog 中修改資產，所有選擇它的 Manifest 都會生效。因為兩種
文件同構，Catalog 也可以直接執行：`ov add-resource -m catalog.yaml` 會匯入它定義的全部資產。

CLI 按以下規則查詢 Catalog 檔案：

1. 傳入 `--args catalog:<file>` 時使用該路徑；相對路徑基於當前工作目錄。
2. 未傳入時讀取 Manifest 所在目錄下的 `catalog.yaml`。

定義了 `catalog` 的 Manifest 不使用單獨的 Catalog 檔案；同時傳入會導致解析失敗。

### 資產身份

服務端根據以下資訊生成穩定的 `asset_id`：

```text
connector + normalized locator + ref
```

Git URL 會去除協議、使用者名稱字首、埠、結尾的 `.git` 和 `/`，並把主機名統一為小寫。
因此，同一倉庫的 HTTPS、SSH 和 SCP 風格地址通常會得到相同定位符；不同分支會得到不同資產。

資產名稱不參與身份計算。重新命名資產但保持來源和分支不變時，會繼續關聯原資源；修改來源或
分支時會產生新資產，舊資源被報告為 orphan。

出於安全原因，clone URL 不能：

- 為空或包含控制字元；
- 以 `-` 開頭；
- 使用 `ext::`、`fd::` 等 Git remote-helper 傳輸格式。

## 快速開始

### 前置條件

1. 安裝支援 OpenViking Assets 的 `ov` CLI。
2. 配置支援 `/api/v1/openviking-assets/resolve` 的 OpenViking 服務。
3. 確認 CLI 可以連線服務：

```bash
ov health
```

### 編寫並驗證 Manifest

建立 `manifest.yaml`：

```yaml
protocol: openviking-assets/1

catalog:
  - name: openviking
    connector: git
    params:
      repo_url: https://github.com/volcengine/OpenViking
      branch: main
```

先驗證：

```bash
ov add-resource --manifest manifest.yaml --args dry_run:true
```

`dry_run` 會完成以下操作：

- 讀取本地 YAML 檔案（使用單獨 Catalog 檔案時一併讀取）；
- 呼叫當前 OpenViking 服務解析並校驗協議；
- 檢查所有 `auth_ref` 是否能在本地解析；
- 讓服務端使用最終憑據對每個 Git 倉庫執行只讀 `git ls-remote` 許可權預檢；
- 輸出每個資產將執行的 create 或 sync 操作；
- 不克隆倉庫、不提交資源、不建立任務，也不寫入 State。

任何倉庫不可讀時，dry-run 立即以 `PERMISSION_DENIED` 退出，不再輸出可執行計劃。

### 應用 Manifest

確認計劃後去掉 `dry_run`：

```bash
ov add-resource --manifest manifest.yaml
```

倉庫中包含一個完整示例（一份共享 Catalog 加一份按名選擇的 Manifest），位於
[`examples/openviking-assets`](https://github.com/volcengine/OpenViking/tree/main/examples/openviking-assets)。

## 憑據

Manifest 和 Catalog 只儲存 `auth_ref` 別名，不應儲存 token、密碼或私鑰。CLI 預設從以下
檔案解析別名：

```text
~/.openviking/openviking_assets_credentials.yaml
```

示例：

```yaml
credentials:
  team-git:
    username: oauth2
    token: replace-with-your-token
```

可以使用環境變數覆蓋檔案位置：

```bash
export OPENVIKING_ASSETS_CREDENTIALS_FILE=/secure/path/assets-credentials.yaml
```

執行前，CLI 會先解析所有選中資產的 `auth_ref`，然後由服務端在實際執行環境中用
`git ls-remote` 校驗每個倉庫的讀取許可權。只要有一個別名不存在或倉庫不可讀，整個操作都會
在提交任何資源之前失敗；`dry_run` 也執行相同預檢。原生 Git 憑據別名只支援 `username` 和
`token`，並保持上述扁平結構。使用預設的原生 Git 鏈路時，CLI 會在呼叫 `add_resource` 時將它們放入
`args.auth_config`，而 `branch` 或 `commit` 仍留在 `args` 頂層。解析出的 Git 引數會通過
當前配置的 OpenViking 服務連線傳送，因此遠端部署應使用 TLS，並限制憑據檔案的本地訪問許可權。

當最終 `watch_interval` 大於 `0` 時，OpenViking 會把通過 `auth_ref` 解析出的 HTTPS Git
token 儲存到 Watch task 私有且與倉庫 URL 繫結的鑑權狀態中。token 不會寫入 Manifest
State、普通入庫佇列或 Watch API/MCP/CLI 返回。週期為 `0` 時，token 仍只在本次請求內使用。
Git PAT 沒有通用重新整理流程，token 過期或被撤銷後需要重建 Watch。

Watch 私有狀態儲存在 `viking://resources/.watch_tasks.json`。啟用 VikingFS 檔案加密時會
靜態加密；否則服務端控制檔案及其備份包含明文 token 狀態。生產環境應限制服務端儲存訪問並
啟用加密。

即使沒有指定 `--wait`，原生憑據匯入也需要等 clone 和 parse 完成後，服務端才會返回 task；
因此 CLI 對這類資產預設使用 300 秒請求超時，大倉庫可通過 `--timeout <秒>` 調大。token
會放在 HTTPS 請求體中傳輸，生產環境應保持診斷請求體 dump 關閉。

如果目標服務已經具備訪問倉庫所需的 SSH key 或其他認證配置，可以不設定 `auth_ref`。

## Create、Sync 和 State

非 dry-run 執行後，CLI 在 Manifest 旁寫入：

```text
<manifest-file>.state.json
```

例如：

```text
manifest.yaml.state.json
```

State 使用 `openviking-assets-state/1` 協議，記錄：

- `asset_id`、名稱、連接器、定位符和 ref；
- 對應的 `resource_uri` 和 `task_id`；
- 最近一次執行狀態、錯誤和時間。

執行規則：

| 條件 | 行為 |
| --- | --- |
| State 中沒有該 `asset_id` 的資源 URI | create：建立新資源。 |
| State 中已有資源 URI | sync：把 URI 作為 `to` 再次呼叫 `add_resource`。 |
| 資產不再被 Manifest 選擇 | 報告 orphan，保留資源和 State，不自動刪除。 |
| `asset_id` 因來源或分支變化 | 建立新資產，舊資產成為 orphan。 |

State 屬於執行環境，不是 Catalog 或 Manifest 協議的一部分。共享 Manifest 倉庫通常應在
`.gitignore` 中加入：

```text
*.state.json
```

不要併發執行同一個 Manifest；當前 State 檔案不提供跨程序鎖。

內容級同步進度不儲存在 Manifest State 中。持續重新整理由 OpenViking Watch 和連接器負責。

## 更新週期

`watch_interval` 的優先順序從高到低為：

1. CLI 的 `--watch-interval`；
2. 單個資產的 `watch_interval`；
3. `defaults.git.watch_interval`；
4. `0`，不自動重新整理。

例如，臨時把 Manifest 中全部資產調整為每 60 分鐘重新整理：

```bash
ov add-resource --manifest manifest.yaml --watch-interval 60
```

後續內容重新整理由 Watch 執行。原生 HTTPS Git 資產使用 `auth_ref` 時，服務端會在每次重新整理時
從 Watch 私有狀態恢復與倉庫繫結的 token。重新執行 Manifest 仍可用於應用 Catalog/Manifest
構成變化、恢復失敗資產或顯式觸發同步。

## 失敗處理

許可權預檢先於所有資源提交。任一資產預檢失敗時：

1. 命令立即以原始錯誤碼退出，例如 `PERMISSION_DENIED`；
2. 不提交任何資產，不建立後臺任務；
3. 不寫入 State；
4. `skip_failed` 不會跳過預檢失敗。

只有全部預檢成功後，才進入以下逐資產執行階段。

預設採用 fail-fast：

1. 當前資產失敗；
2. 後續資產標記為未嘗試；
3. 已成功資產和失敗記錄寫入 State；
4. 命令以非零狀態退出。

使用 `skip_failed` 可以繼續處理其餘資產：

```bash
ov add-resource --manifest manifest.yaml --args skip_failed:true
```

`skip_failed` 不會把部分失敗轉換為成功。只要有資產失敗，命令最終仍以非零狀態退出；
已經成功的資源不會回滾。全部資產失敗時，命令會報告沒有任何資產成功應用。

## 命令列選項

與 `--manifest` 搭配使用的引數：

| 引數 | 說明 |
| --- | --- |
| `-m, --manifest <file>` | Manifest 文件。 |
| `--args <key:value,...>` | Manifest 執行選項，多個選項用逗號分隔，支援的鍵見下表。 |
| `--wait` | 等待每個資源處理完成。 |
| `--timeout <seconds>` | HTTP 請求超時。原生私有 Git 即使沒有 `--wait` 也會使用該值，預設 300 秒。 |
| `--watch-interval <minutes>` | 覆蓋全部資產的更新週期。 |

`--args` 支援的執行選項：

| 鍵 | 說明 |
| --- | --- |
| `catalog:<file>` | 按名稱選擇資產的 Manifest 使用的單獨 Catalog 檔案；省略時使用 Manifest 同目錄的 `catalog.yaml`。Manifest 自身定義了 `catalog` 時不使用。 |
| `dry_run:true` | 解析協議並校驗所有倉庫的讀取許可權；不提交資源、不建立任務、不寫 State。 |
| `skip_failed:true` | 一個資產失敗後繼續處理其他資產。 |

`--args` 既支援 `key:value,...` 逗號分隔形式，也支援整段 JSON 物件，例如
`--args '{"dry_run": true, "catalog": "shared/catalog.yaml"}'`。

執行選項由 CLI 在本地消費，不會作為資源引數傳送給服務端；未知的鍵會直接報錯。

## 當前限制

`openviking-assets/1` 當前具有以下邊界：

- 只支援 Git 資產；
- Manifest 必須平鋪，不支援遞迴 `include`；
- 服務端 resolver 只返回計劃，不執行批次提交；
- 服務端 preflight 通過只讀 `git ls-remote` 校驗倉庫許可權，不下載倉庫內容；
- CLI 按順序逐個執行資產；
- 不自動刪除 orphan；
- 不包含 `ov share` 指標碼或從現有知識庫匯出 Manifest 的能力；
- State 是本地檔案，不在多臺機器之間自動同步；
- CLI 和服務端都必須支援同一協議版本。

## 相關文件

- [OpenViking Assets API](../api/22-openviking-assets.md)
- [資源管理 API](../api/02-resources.md)
- [資源 Watch API](../api/15-watches.md)
- [OVPack 匯入匯出](09-ovpack.md)
- [OpenViking Assets 示例](https://github.com/volcengine/OpenViking/tree/main/examples/openviking-assets)
