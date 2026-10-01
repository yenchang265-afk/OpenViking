# OpenViking 安裝 SOP（For Agent）

## 目標

幫助使用者以最小路徑完成 OpenViking 安裝、配置、自檢和啟動。

本文面向 OpenViking 服務端安裝。如果只需要配置客戶端 CLI，請使用 [OpenViking CLI 配置指南](05-cli-setup.md)。

## 總原則

- 預設走普通使用者安裝路徑，不預設走原始碼構建
- 預設使用預編譯包，不預設要求 Go / Rust / C++ / CMake
- 配置不確定時必須先問使用者，不要替使用者猜 provider、model、api_base、api_key、workspace
- 只有在安裝失敗並明確指向本地編譯，或使用者主動要求原始碼安裝時，才進入原始碼構建路徑

## SOP

### 1. 判斷路徑

先判斷使用者屬於哪一類：

#### A. 普通最小安裝
滿足任一情況即可進入：
- 使用者只是想安裝並跑起來
- 使用者只是想體驗或接入 OpenViking
- 使用者沒有要求原始碼開發
- 使用者沒有要求修改底層原生元件

執行路徑：
1. 安裝 Python 包
2. 詢問模型配置
3. 生成 `~/.openviking/ov.conf`
4. 執行 `openviking-server doctor`
5. 啟動 `openviking-server`

#### B. 本地模型安裝（Ollama）
滿足任一情況即可進入：
- 使用者明確說要本地模型
- 使用者明確說要 Ollama
- 使用者不想手填大量模型引數

執行路徑：
1. 執行 `openviking-server init`
2. 執行 `openviking-server doctor`
3. 啟動 `openviking-server`

#### C. Docker 安裝
滿足任一情況即可進入：
- 使用者明確說要用 Docker 安裝或執行
- 使用者不想在本機直接安裝 Python 包
- 使用者想把配置和資料通過 volume 掛載持久化

執行路徑：
1. 確認使用者是否已有現成 `ov.conf`
2. 如果沒有，先確認模型配置或引導在容器內執行 `openviking-server init`
3. 使用映象或 `docker-compose.yml` 啟動容器
4. 驗證 `/health`

#### D. Windows 安裝
滿足任一情況即可進入：
- 使用者當前在 Windows 環境
- 使用者要求 Windows 安裝步驟

執行路徑：
1. 優先按普通最小安裝路徑走預編譯 wheel
2. 使用 Windows 的環境變數寫法配置 `OPENVIKING_CONFIG_FILE`
3. 執行 `openviking-server doctor`
4. 啟動 `openviking-server`
5. 只有在 wheel 不可用或安裝失敗時，才進入 Windows 本地編譯路徑

#### E. 原始碼構建
只有以下情況才進入：
- 使用者明確要求原始碼安裝
- 安裝失敗且錯誤資訊明確要求本地編譯
- 當前平臺沒有預編譯 wheel
- 使用者明確要修改或重編底層原生元件

進入後再說明需要：
- Go 1.22+
- Rust 1.91.1+
- C++ 編譯器
- CMake

### 2. 提問

如果使用者沒有給出完整模型配置，先問，不要直接寫配置檔案。

#### 必問項

1. 你準備使用哪種模型提供商？
   - `openai`
   - `azure`
   - `volcengine`
   - `openai-codex`
   - `ollama`

2. 你是否已經確定：
   - embedding 模型名
   - VLM 模型名
   - API Key / 鑑權方式

3. `storage.workspace` 想放在哪個目錄？

#### 按 provider 繼續追問

##### openai
- embedding 模型名
- VLM 模型名
- 是否使用 `https://api.openai.com/v1`
- API Key 是否已準備好

##### azure
- embedding deployment name
- VLM deployment name
- Azure API Base
- Azure API Key
- 是否使用預設 `api_version = 2025-01-01-preview`

##### volcengine
- embedding 模型名
- VLM 模型名
- 是否使用 `https://ark.cn-beijing.volces.com/api/v3`
- API Key 是否已準備好

##### openai-codex
- 是否希望通過 `openviking-server init` 完成 Codex OAuth
- VLM 模型名
- embedding 使用哪個 provider 和模型

##### ollama
- 是否接受直接執行 `openviking-server init`
- 是否已經安裝 Ollama
- 希望使用哪些本地 embedding / VLM 模型

#### Docker 額外必問項

如果使用者選擇 Docker，還要繼續確認：
- 使用者是想用 `docker run` 還是 `docker compose`
- 本機是否已有 `~/.openviking/ov.conf`
- 是否要把宿主機 `~/.openviking` 掛載到容器 `/app/.openviking`
- 是否要直接通過環境變數 `OPENVIKING_CONF_CONTENT` 注入完整 JSON 配置

#### Windows 額外必問項

如果使用者在 Windows，還要繼續確認：
- 使用者使用的是 PowerShell 還是 cmd.exe
- 使用者是否只接受預編譯 wheel 安裝
- 如果需要本地編譯，是否已安裝 CMake 和 MinGW

### 3. 生成配置

只有在使用者確認完必要資訊後，才能寫 `~/.openviking/ov.conf`。

#### 最小配置結構

```json
{
  "storage": {
    "workspace": "..."
  },
  "embedding": {
    "dense": {
      "provider": "...",
      "api_base": "...",
      "api_key": "...",
      "model": "..."
    }
  },
  "vlm": {
    "provider": "...",
    "api_base": "...",
    "api_key": "...",
    "model": "..."
  }
}
```

#### 可選欄位

只有在 provider 需要、README 示例明確包含、或使用者明確要求時，才加入：
- `dimension`
- `api_version`
- `max_concurrent`
- `temperature`
- `max_retries`

#### 不要做的事

- 不要填假金鑰
- 不要填使用者未確認的路徑
- 不要把 README 註釋複製進 JSON
- 不要替使用者猜模型名或私有 API 地址

### 4. 執行命令

#### 路徑 A：普通最小安裝

```bash
pip install openviking --upgrade --force-reinstall
```

使用者確認配置後寫入 `~/.openviking/ov.conf`，然後執行：

```bash
openviking-server doctor
openviking-server
```

#### 路徑 B：本地模型安裝（Ollama）

```bash
openviking-server init
openviking-server doctor
openviking-server
```

#### 路徑 C：Docker 安裝

##### 方案 1：使用現成映象直接執行

如果使用者已有本機配置目錄，優先建議：

```bash
docker run --rm \
  -p 1933:1933 \
  -v ~/.openviking:/app/.openviking \
  ghcr.io/volcengine/openviking:latest
```

說明：
- 映象推薦優先使用 `ghcr.io`；如果拉取失敗，改用 `openviking-cn-beijing.cr.volces.com/volcengine/openviking:latest`
- 容器內預設配置路徑是 `/app/.openviking/ov.conf`
- 容器內 `HOME=/app`
- 建議把宿主機 `~/.openviking` 掛載到容器 `/app/.openviking` 持久化配置、CLI 配置和 workspace 資料
- Web Studio 由 OV server 自身在 `http://127.0.0.1:1933/studio` 提供，不需要額外埠

##### 方案 2：使用 `docker-compose.yml`

如果使用者希望使用 compose，倉庫裡已有示例：
- 映象：`ghcr.io/volcengine/openviking:latest`（拉取失敗時改用 `openviking-cn-beijing.cr.volces.com/volcengine/openviking:latest`）
- 端口：`1933:1933`
- volume：`~/.openviking:/app/.openviking`

此時直接讓使用者基於倉庫根目錄執行：

```bash
docker compose up -d
```

##### 方案 3：容器內初始化配置

如果使用者還沒有 `ov.conf`，可以二選一：

1. 先在宿主機生成並掛載進容器
2. 啟動容器後進入容器內執行：

```bash
docker exec -it openviking openviking-server init
```

Dockerfile 還支援在首次啟動時通過 `OPENVIKING_CONF_CONTENT` 注入完整 JSON；如果使用者明確想這樣做，可以採用，但前提仍是配置值已確認。

##### Docker 驗證

啟動後驗證：

```bash
curl http://localhost:1933/health
```

#### 路徑 D：Windows 安裝

優先按預編譯 wheel 路徑執行：

```bat
pip install openviking --upgrade --force-reinstall
```

配置檔案寫好後，按使用者 shell 設定環境變數。

##### PowerShell

```powershell
$env:OPENVIKING_CONFIG_FILE = "$HOME/.openviking/ov.conf"
```

##### cmd.exe

```bat
set "OPENVIKING_CONFIG_FILE=%USERPROFILE%\.openviking\ov.conf"
```

然後執行：

```bat
openviking-server doctor
openviking-server
```

如果使用者還要配置 CLI 檔案：

##### PowerShell

```powershell
$env:OPENVIKING_CLI_CONFIG_FILE = "$HOME/.openviking/ovcli.conf"
```

##### cmd.exe

```bat
set "OPENVIKING_CLI_CONFIG_FILE=%USERPROFILE%\.openviking\ovcli.conf"
```

#### 路徑 E：原始碼構建

只有進入原始碼構建路徑後，才向用戶說明並準備 Go / Rust / C++ / CMake。

### 5. 失敗分流

#### 情況 1：配置檔案缺失、路徑錯誤或 JSON 無法解析

優先檢查：
- `~/.openviking/ov.conf` 是否存在
- 是否通過環境變數或 `--config` 指向了錯誤路徑
- 配置文件是否是合法 JSON

處理原則：
- 先修正配置檔案路徑或 JSON 語法
- 再重新執行 `openviking-server doctor`

#### 情況 2：模型配置不完整

典型表現：
- 缺少 embedding 或 VLM 配置
- 缺少 `provider` / `model` / `api_key`
- `openai-codex` 只配了 VLM，但 embedding 沒配

處理原則：
- 先補齊最小配置
- 不要替使用者猜模型名或金鑰
- 如果是 `openai-codex`，提醒使用者它主要解決 VLM，embedding 仍需單獨確認

#### 情況 3：模型服務不可連通或鑑權不可用

優先檢查：
- API Base 是否正確
- API Key / 鑑權方式是否正確
- 如果是 `openai-codex`，是否已經通過 `openviking-server init` 完成 OAuth
- 如果是 Ollama，服務是否已啟動

處理原則：
- 先修正 provider 配置和鑑權狀態
- 對 Ollama 優先建議：

```bash
openviking-server init
```

- 然後重新執行：

```bash
openviking-server doctor
```

#### 情況 4：本地依賴或打包產物不可用

典型表現：
- 原生引擎模組無法匯入
- AGFS / RAGFS 相關繫結不可用
- 安裝後缺少打包產物

處理原則：
- 先執行一次標準重灌：

```bash
pip install openviking --upgrade --force-reinstall
```

- 如果仍失敗，再判斷是否需要進入原始碼構建路徑
- 不要一開始就預設要求使用者安裝整套本地構建工具鏈

#### 情況 5：安裝過程進入原始碼編譯

優先確認是否屬於：
- 當前平臺沒有對應 wheel
- 使用者本來就在走原始碼安裝
- 預編譯產物缺失

處理原則：
- 只有確認進入原始碼構建路徑後，才補充 Go / Rust / C++ / CMake
- Windows 本地編譯優先補 CMake 和 MinGW
- 不要把原始碼構建依賴當作普通安裝預設前置

#### 情況 6：Windows 安裝失敗

優先按這個順序判斷：
1. 當前 Python / 架構是否命中了預編譯 wheel
2. 是否實際進入了原始碼編譯路徑
3. 環境變數是否按 PowerShell 或 cmd.exe 正確設定
4. 如果進入本地編譯，是否缺少 CMake / MinGW

處理原則：
- 優先修正 wheel、路徑和環境變數問題
- 只有明確進入本地編譯路徑時，才補裝構建依賴

#### 情況 7：Docker 啟動後不可用

優先檢查：
- `~/.openviking` 是否正確掛載到 `/app/.openviking`
- 容器內是否存在 `/app/.openviking/ov.conf`
- 模型配置是否完整
- `curl http://localhost:1933/health` 是否返回正常
- 是否需要進入容器執行 `openviking-server init`

處理原則：
- 先修正 volume 掛載和配置檔案
- 再檢查 provider、模型和鑑權配置

#### 情況 8：使用者不知道怎麼選模型

先不要寫配置。

引導規則：
- 使用者已有某家雲服務帳號，就優先沿用該 provider
- 使用者想本地執行，就優先建議 Ollama + `openviking-server init`
- 使用者想用 `openai-codex`，提醒它主要解決 VLM，embedding 仍需單獨確認

## 其他詳細參考
- [OpenViking 官方GitHub 倉庫](https://github.com/volcengine/OpenViking)
