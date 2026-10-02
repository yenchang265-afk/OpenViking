# OpenViking TOS 安裝包釋出與安裝說明

> 更新時間：2026-06-03
> 釋出目錄：`latest`（預設）與可指定日期目錄（示例：`2026.6.3`）
> 釋出內容：`install.sh`、`openviking.tgz`、`manifest.json`

## 1. 本次釋出結論

當前釋出協議只發布三個檔案：一個相容多區域的 `install.sh`，一個外掛壓縮包 `openviking.tgz`，一個描述檔案 `manifest.json`。三個檔案會覆蓋上傳到 4 個 TOS bucket，並設定物件 ACL 為公開讀（public-read）。每個 bucket 都先上傳日期目錄；日期目錄可用 `--release-dir <yyyy.m.d>` 指定，未指定時按運行當天動態生成，不能固定死某個日期。`latest` 目錄只有在元件穩定後顯式指定 `--publish-latest` 才上傳：

- `latest/install.sh`
- `latest/openviking.tgz`
- `latest/manifest.json`
- `2026.6.3/install.sh`
- `2026.6.3/openviking.tgz`
- `2026.6.3/manifest.json`

安裝指令碼預設安裝 `latest/openviking.tgz`；如需安裝固定日期版本，可新增 `--date 2026.6.3`。

如果目標 bucket 不存在，上傳指令碼會先自動建立 bucket，再上傳物件。本文中的驗證命令均使用 dry-run 或本地語法/單測校驗，不執行真實 TOS 上傳。

## 2. 域名規則

`install.sh` 預設使用內部域名，適用於內部網路環境：

```text
ivolces.com
```

公網測試或公網安裝時，需要顯式新增：

```bash
--external
```

此時指令碼會使用公網域名：

```text
volces.com
```

## 3. 已釋出的公網下載地址

### 3.1 arkclaw-ov-cn-beijing

```text
https://arkclaw-ov-cn-beijing.tos-cn-beijing.volces.com/latest/install.sh
https://arkclaw-ov-cn-beijing.tos-cn-beijing.volces.com/latest/openviking.tgz
https://arkclaw-ov-cn-beijing.tos-cn-beijing.volces.com/latest/manifest.json
https://arkclaw-ov-cn-beijing.tos-cn-beijing.volces.com/2026.6.3/install.sh
https://arkclaw-ov-cn-beijing.tos-cn-beijing.volces.com/2026.6.3/openviking.tgz
https://arkclaw-ov-cn-beijing.tos-cn-beijing.volces.com/2026.6.3/manifest.json
```

### 3.2 arkclaw-ov-cn-guangzhou

```text
https://arkclaw-ov-cn-guangzhou.tos-cn-guangzhou.volces.com/latest/install.sh
https://arkclaw-ov-cn-guangzhou.tos-cn-guangzhou.volces.com/latest/openviking.tgz
https://arkclaw-ov-cn-guangzhou.tos-cn-guangzhou.volces.com/latest/manifest.json
https://arkclaw-ov-cn-guangzhou.tos-cn-guangzhou.volces.com/2026.6.3/install.sh
https://arkclaw-ov-cn-guangzhou.tos-cn-guangzhou.volces.com/2026.6.3/openviking.tgz
https://arkclaw-ov-cn-guangzhou.tos-cn-guangzhou.volces.com/2026.6.3/manifest.json
```

### 3.3 arkclaw-ov-cn-shanghai

```text
https://arkclaw-ov-cn-shanghai.tos-cn-shanghai.volces.com/latest/install.sh
https://arkclaw-ov-cn-shanghai.tos-cn-shanghai.volces.com/latest/openviking.tgz
https://arkclaw-ov-cn-shanghai.tos-cn-shanghai.volces.com/latest/manifest.json
https://arkclaw-ov-cn-shanghai.tos-cn-shanghai.volces.com/2026.6.3/install.sh
https://arkclaw-ov-cn-shanghai.tos-cn-shanghai.volces.com/2026.6.3/openviking.tgz
https://arkclaw-ov-cn-shanghai.tos-cn-shanghai.volces.com/2026.6.3/manifest.json
```

### 3.4 arkclaw-ov

```text
https://arkclaw-ov.tos-cn-beijing.volces.com/latest/install.sh
https://arkclaw-ov.tos-cn-beijing.volces.com/latest/openviking.tgz
https://arkclaw-ov.tos-cn-beijing.volces.com/latest/manifest.json
https://arkclaw-ov.tos-cn-beijing.volces.com/2026.6.3/install.sh
https://arkclaw-ov.tos-cn-beijing.volces.com/2026.6.3/openviking.tgz
https://arkclaw-ov.tos-cn-beijing.volces.com/2026.6.3/manifest.json
```

## 4. 推薦安裝方式

### 4.1 內部網路安裝 latest（預設）

在內部網路環境中，直接下載對應區域的 `install.sh` 並執行即可。指令碼預設使用內部域名並安裝 `latest/openviking.tgz`。

以廣州區域為例：

```bash
wget https://arkclaw-ov-cn-guangzhou.tos-cn-guangzhou.ivolces.com/latest/install.sh -O install.sh
bash install.sh --region cn-guangzhou
```

### 4.2 公網安裝 latest

公網環境需要使用公網下載地址，並在執行指令碼時加 `--external`。

以廣州區域為例：

```bash
wget https://arkclaw-ov-cn-guangzhou.tos-cn-guangzhou.volces.com/latest/install.sh -O install.sh
bash install.sh --external --region cn-guangzhou
```

### 4.3 安裝固定日期版本

如需安裝 `2026.6.3` 固定版本：

```bash
wget https://arkclaw-ov-cn-guangzhou.tos-cn-guangzhou.volces.com/2026.6.3/install.sh -O install.sh
bash install.sh --external --region cn-guangzhou --date 2026.6.3
```

### 4.4 指定 bucket 安裝

如果使用預設 bucket `arkclaw-ov`，可指定 bucket：

```bash
wget https://arkclaw-ov.tos-cn-beijing.volces.com/latest/install.sh -O install.sh
bash install.sh --external --region cn-beijing --bucket arkclaw-ov
```

### 4.5 自定義 TOS Base URL

如果希望完全指定下載根路徑，可使用 `--tos-base-url`：

```bash
bash install.sh --tos-base-url https://arkclaw-ov.tos-cn-beijing.volces.com
```

預設下載：

```text
https://arkclaw-ov.tos-cn-beijing.volces.com/latest/openviking.tgz
```

如果需要日期目錄：

```bash
bash install.sh --tos-base-url https://arkclaw-ov.tos-cn-beijing.volces.com --date 2026.6.3
```

對應下載：

```text
https://arkclaw-ov.tos-cn-beijing.volces.com/2026.6.3/openviking.tgz
```

## 5. install.sh 引數速查

| 引數 | 說明 | 預設值 |
| --- | --- | --- |
| `--internal` | 使用內部域名 `ivolces.com` | 預設開啟 |
| `--external` | 使用公網域名 `volces.com` | 關閉 |
| `--latest` | 安裝 `latest/openviking.tgz` | 預設開啟 |
| `--date <date>` | 安裝日期目錄版本，如 `2026.6.3/openviking.tgz` | 無 |
| `--release-path <path>` | 安裝自定義目錄下的 `openviking.tgz` | `latest` |
| `--region <region>` | 指定區域，如 `cn-beijing` / `cn-guangzhou` / `cn-shanghai` | 自動識別，失敗時為 `cn-beijing` |
| `--bucket <bucket>` | 指定 bucket 名稱 | `arkclaw-ov` |
| `--tos-base-url <url>` | 完整指定 TOS 根 URL | 自動按 bucket/region/domain 生成 |
| `--manifest-url <url>` | 完整指定 manifest URL | 自動按 bucket/region/domain/release-path 生成 |
| `--source local` | 從 `install.sh` 同目錄安裝本地 `openviking.tgz` | 遠端下載 |
| `--tarball <path>` | 從指定本地 tgz 安裝 | 無 |
| `--verify-only` | 僅下載/校驗，不安裝 | 關閉 |
| `--dry-run` | 列印動作，不執行下載/安裝 | 關閉 |
| `--no-restart` | 安裝後不重啟 OpenClaw gateway | 預設會重啟 |

## 6. 上傳指令碼說明

上傳指令碼路徑：

```text
scripts/upload_tos.py
```

執行上傳（真實上傳，需要 `TEAM_TEST_AK` / `TEAM_TEST_SK`）：

```bash
python3 scripts/upload_tos.py --release-dir 2026.6.3
```

只驗證指令碼路徑、物件 key、bucket 與 latest 策略，不真實上傳 TOS：

```bash
python3 scripts/upload_tos.py --release-dir 2026.6.3 --dry-run
```

不指定 `--release-dir` 時，指令碼預設使用運行當天的 `yyyy.m.d` 作為日期目錄。

元件穩定後再發布 latest：

```bash
python3 scripts/upload_tos.py --release-dir 2026.6.3 --publish-latest
```

完整發布入口會先構建三檔案產物，再呼叫上傳指令碼：

```bash
TEAM_TEST_AK=... TEAM_TEST_SK=... scripts/release-to-tos.sh --release-dir 2026.6.3
TEAM_TEST_AK=... TEAM_TEST_SK=... scripts/release-to-tos.sh --release-dir 2026.6.3 --publish-latest
```

僅做釋出指令碼正確性驗證、不上傳 TOS：

```bash
scripts/release-to-tos.sh --release-dir 2026.6.3 --dry-run
```

上傳指令碼會讀取環境變數：

```text
TEAM_TEST_AK
TEAM_TEST_SK
```

上傳物件：

```text
install.sh
openviking.tgz
manifest.json
```

上傳路徑：

```text
2026.6.3/install.sh
2026.6.3/openviking.tgz
2026.6.3/manifest.json
latest/install.sh       # 僅 --publish-latest 時上傳
latest/openviking.tgz   # 僅 --publish-latest 時上傳
latest/manifest.json    # 僅 --publish-latest 時上傳
```

上傳目標 bucket：

```text
arkclaw-ov-cn-beijing
arkclaw-ov-cn-guangzhou
arkclaw-ov-cn-shanghai
arkclaw-ov
```

如果 bucket 不存在，上傳指令碼會自動建立對應 bucket。

上傳時已設定物件 ACL：

```text
public-read
```

## 7. 本次驗證結果

### 7.1 本地指令碼測試

本地只驗證指令碼正確性，不做真實 TOS 上傳。已通過以下測試：

```bash
npx vitest run tests/ut/tos-release-contract.test.ts
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_upload_tos.py
bash -n scripts/install.sh
bash -n scripts/release-to-tos.sh
node --check scripts/generate-release-manifest.mjs
node --check scripts/tos-release-client.mjs
```

測試覆蓋：

- 預設使用 `latest/openviking.tgz`
- `--date 2026.6.3` 使用日期目錄
- 預設內部域名為 `ivolces.com`
- `--external` 使用公網域名 `volces.com`
- 上傳指令碼預設只上傳指定日期目錄，`--publish-latest` 時才上傳 `latest`
- 不指定 `--release-dir` 時動態使用當天日期目錄
- bucket 不存在時自動建立 bucket
- 上傳物件使用 `public-read` ACL

## 8. 常見問題

### 8.1 為什麼公網測試必須加 --external？

因為 `ivolces.com` 是內部域名，在當前公網測試環境無法連通。加 `--external` 後，指令碼會改用 `volces.com` 公網域名。

### 8.2 預設不指定日期時安裝哪個版本？

預設安裝 `latest/openviking.tgz`。

### 8.3 如何回滾到固定日期目錄？

使用 `--date`：

```bash
bash install.sh --date 2026.6.3
```

公網環境：

```bash
bash install.sh --external --date 2026.6.3
```

### 8.4 覆蓋上傳是否安全？

本次需求明確要求同路徑已有檔案直接覆蓋。上傳指令碼未開啟禁止覆蓋，並在每次上傳時設定 public-read ACL。
