# OpenViking 發版說明

本文說明 OpenViking 倉庫的發版目標、版本與 tag 約定、主要發版流程，以及補發和驗證方式。內容以倉庫中已追蹤的 GitHub Actions、構建配置和包配置為準。

## 發版目標

OpenViking 的發版目標不是單一產物，而是圍繞不同使用入口釋出一組相互關聯的資產：

- `openviking` Python 主包：面向本地執行時、服務端、CLI 及完整功能使用者。
- Python SDK `openviking-sdk`：面向只通過 HTTP 呼叫已有 OpenViking 服務的輕量客戶端使用者。
- Docker 映象：面向容器化部署，釋出到 GHCR 和 Docker Hub。
- TOS 釋出資產：面向原始碼包、安裝指令碼和穩定下載路徑。
- Rust CLI / npm 包：面向通過 npm 安裝 `ov` CLI 的使用者。
- OpenClaw / ClawHub 外掛：面向 OpenClaw 外掛分發渠道。
- VikingBot：當前隨 `openviking[bot]` 和官方 Docker 映象分發；歷史獨立發版入口單獨說明，避免誤用。

一次正式主版本發版應確保 Python 包、Docker 映象和 TOS 資產使用同一個主版本 tag；SDK、CLI、ClawHub 外掛則使用各自獨立的 tag 或 version 名稱空間。

## 版本與 tag 約定

推薦使用以下 tag 約定：

| 產物 | 推薦 tag / version | 說明 |
| --- | --- | --- |
| `openviking` 主包 | `vX.Y.Z` | 主 release tag，例如 `v0.3.26`。 |
| `openviking-sdk` | `python-sdk@X.Y.Z` | SDK 專用 tag，例如 `python-sdk@0.1.3`。 |
| Rust CLI / npm CLI | `cli@X.Y.Z` | CLI 專用 tag，例如 `cli@0.2.0`。 |
| ClawHub 外掛 latest | `YYYY.M.D` 或 `YYYY.M.D-N` | 由 workflow 自動生成或手動指定。 |
| ClawHub 插件 dev | `YYYY.M.D-dev.N` | dev channel 使用。 |

主包版本通過 `setuptools_scm` 從 Git tag 解析；正式主發版建議統一使用 `vX.Y.Z`。SDK 版本同樣通過 `setuptools_scm` 解析，但只匹配 `python-sdk@*` tag，以避免和主包 tag 混淆。

## 正式主包發版流程

主包正式發版走根目錄 GitHub Release：

1. 確認待發布改動已合入目標分支，且 PR / main 分支檢查通過。
2. 建立主包 tag，例如 `v0.3.26`。
3. 在 GitHub 上基於該 tag 釋出 Release。
4. `03. Release` workflow 會在 Release published 時觸發。
5. workflow 複用 `_Build Distribution` 構建 sdist 和多平臺 wheel。
6. workflow 將構建產物釋出到 PyPI。
7. workflow 構建並推送多架構 Docker 映象。
8. `Release TOS Upload` workflow 會上傳原始碼 zip 和安裝指令碼到 TOS。

正式主發版的釋出目標包括：

- PyPI：`openviking`
- GHCR：`ghcr.io/<owner>/<repo>`
- Docker Hub：`<dockerhub-user>/openviking`
- TOS：版本化 release 路徑和可選 `latest` 穩定路徑

## 主包手動構建、測試釋出與補發

根目錄 release workflow 也支援手動觸發，可選擇釋出目標：

- `none`：只構建，不釋出。
- `testpypi`：釋出到 TestPyPI。
- `pypi`：釋出到 PyPI。
- `both`：同時釋出 TestPyPI 和 PyPI。

如需基於已有構建產物補發 Python 包，可使用 `_Publish Distribution` workflow，並傳入對應的 build run id。該流程適合釋出失敗後的補發，不建議作為正常主發版入口。

## Docker 映象釋出與補發

正式主發版時，Docker 映象由主 release workflow 自動構建併發布。映象會推送到 GHCR 和 Docker Hub，並在正式 release 下寫入版本 tag 與 `latest` tag。

倉庫還提供獨立的 `Build and Push Docker Image` workflow，適用於：

- 手動指定版本重建映象。
- `main` 分支映象構建。
- tag 觸發後的映象補發。

注意：獨立 Docker workflow 當前也會在 `v*.*.*` tag push 時自動觸發。正式 GitHub Release 的釋出口徑仍以 `03. Release` workflow 為準；獨立 Docker workflow 應視為映象專用構建或補發路徑，避免與正式 release 產物口徑混淆。

為避免重複釋出，正式版本優先使用主 release workflow；只有映象補發或特殊驗證時才使用獨立 Docker workflow。

## TOS 釋出資產

TOS 釋出流程會生成原始碼 zip，並上傳以下型別資產：

- `releases/<tag>/openviking-<tag>-source.zip`
- Claude Code memory plugin 安裝指令碼
- Codex memory plugin 安裝指令碼
- 對應 TOS install 指令碼

正式 GitHub Release 會自動觸發 TOS 上傳，並覆蓋穩定路徑。手動觸發時指定 tag，workflow 上傳該 tag 的版本化路徑；只有設定 `update_latest=true`（預設 `false`）才會覆蓋穩定路徑，因此補傳舊版本的資產不會把使用者退回到舊版本。

如果 TOS 相關 secrets 未配置完整，workflow 會跳過上傳並在 step summary 中說明，不會使整個流程失敗。

### 文件站上的 Memory 外掛下載

安裝器和 Memory 外掛從文件站下載，不再從 TOS 釋出桶下載。兩條文件部署流水線（`17. Docs` 部署到 GitHub Pages 的 `docs.openviking.ai`，`19. Docs TOS Deploy` 部署到 `docs.openviking.net`）都會執行 `.github/scripts/build-plugin-downloads.sh`，把產物釋出到 `/dl` 下，目錄結構與釋出桶一致：`memory-plugin-shared/install.sh` 和 `bootstrap.sh`、`releases/latest/memory-plugin-marketplace.zip`、`plugins/claude/marketplace.json` 和 `plugins/claude/openviking-memory-<外掛版本>.zip`、`plugins/memory-plugins.git`，以及安裝站點的版本檢查讀取的 `releases/latest/channels.json`。

只要推送到 `main` 的提交改動了文件、外掛、安裝器或 `.github/scripts`，兩條流水線就會部署，所以外掛改動合入即釋出，不需要打 tag，也不需要發 GitHub Release。釋出出去的安裝器以 `<日期>-<commit>` 作為版本號。釋出外掛修復時，合入修復並按 `.github/scripts/check-plugin-version-bumps.sh` 的要求升級外掛版本；回滾時在 `main` 上 revert 該改動並再次升級版本號。兩條流水線也可以在 `main` 上手動觸發。

TOS 釋出桶仍會隨每次發版收到同樣的檔案，供仍指向它的安裝使用，見下文。

### TOS 上的 Memory 外掛熱修復與回滾

指向 TOS 釋出桶的安裝讀它的穩定路徑：`plugins/claude/marketplace.json`（Claude Code）、`plugins/memory-plugins.git`（Codex 和 TraeCode CLI）、`releases/latest/memory-plugin-marketplace.zip`（其他所有宿主）、`releases/latest/channels.json`（安裝時的版本解析），以及 `memory-plugin-shared/install.sh` 和 `bootstrap.sh`。workflow 每次執行都從所給 tag 對應的 commit 構建這全部內容。

在那裡不發產品版本、單獨釋出外掛熱修復：

1. 合入修復，並按 `.github/scripts/check-plugin-version-bumps.sh` 的要求升級外掛版本。Claude Code 只在版本號變化時更新已安裝的外掛。
2. 在“上一個正式版本 + 修復”的 commit 上打 tag，例如從上一個 `vX.Y.Z` tag 拉分支並 cherry-pick 修復。tag 不要以 `v` 開頭，例如 `memory-plugins-YYYY.M.D`，也不要為它釋出 GitHub Release：推送 `v*.*.*` tag 會觸發 Docker workflow，釋出 Release 會觸發主包發版 workflow，主包版本號也從 `v*` tag 解析。
3. 推送 tag，然後執行 `gh workflow run release-tos.yml -f tag=<tag> -f update_latest=true`。

回滾時執行 `gh workflow run release-tos.yml -f tag=<上一個正常的 tag> -f update_latest=true`。workflow 定義取自預設分支，但它呼叫的指令碼來自 tag 的 checkout，所以只能重新發布已經包含當前釋出指令碼的 tag；要退回更早的外掛程式碼，按熱修復流程釋出。

兩種操作完成後，Claude Code（URL marketplace）在下次檢查更新時生效，版本號變低也算更新。Codex 在下次啟動時生效，TraeCode CLI 在執行 `trae-cli plugin marketplace upgrade` 時生效。Cursor、TRAE、TRAE CN、ZCode、Kimi Code、OpenCode、pi，以及使用本地目錄 marketplace 的 Claude Code，需要重新執行安裝器才會變化。dsh 從 npm 安裝，不受影響。

## Python SDK 發版流程

Python SDK 位於 `sdk/python`，PyPI 包名為 `openviking-sdk`。SDK 使用獨立 tag 名稱空間：

```text
python-sdk@X.Y.Z
```

典型流程：

1. 合入 SDK 相關改動。
2. 建立並推送 tag，例如 `python-sdk@0.1.3`。
3. `Python SDK Release` workflow 被 tag 觸發。
4. workflow 使用 `setuptools_scm` 解析 SDK 版本。
5. workflow 校驗當前 tag 是否等於 `python-sdk@<resolved-version>`。
6. workflow 構建 `sdk/python` 併發布到 PyPI。

SDK workflow 也支援手動觸發，並可選擇 `testpypi`、`pypi` 或 `both`。手動觸發適合驗證和補發；正式 SDK 發版建議使用 `python-sdk@X.Y.Z` tag。

## Rust CLI / npm 發版流程

Rust CLI 的 tag 格式為：

```text
cli@X.Y.Z
```

推送 `cli@*` tag 後，`Rust CLI Build` workflow 會為多個平臺構建 `ov` 二進位制，併發布 npm 包：

- 平臺包：`@openviking/cli-linux-x64`、`@openviking/cli-linux-arm64`、`@openviking/cli-darwin-x64`、`@openviking/cli-darwin-arm64`、`@openviking/cli-win32-x64`
- wrapper 包：`@openviking/cli`

workflow 會把 tag 中的版本寫入平臺包和 wrapper 包。如果 npm 上已存在同版本包，workflow 會跳過已釋出版本。

## OpenClaw / ClawHub 外掛釋出

OpenClaw 外掛通過 `ClawHub release (OpenViking plugin)` workflow 手動釋出。輸入引數包括：

- `version`：可選；為空時由 workflow 按日期自動生成。
- `channel`：`auto`、`dev` 或 `latest`。
- `changelog`：本次外掛釋出說明。

workflow 會先解析 channel 和 version，再打包 `examples/openclaw-plugin`，推送生成的 package branch，最後呼叫 ClawHub 官方 trusted publishing workflow 釋出。

推薦做法：

- 正式渠道使用 `latest` 或 `auto`。
- 開發驗證使用 `dev`。
- 手動指定 version 時，確保符合對應 channel 的格式要求。

## VikingBot 釋出說明

VikingBot 當前不再作為推薦的獨立 PyPI 包發版路徑維護。現行分發方式是隨主包釋出：

- Python 安裝入口：`pip install "openviking[bot]"`。
- 原始碼開發入口：`uv pip install -e ".[bot]"`。
- 官方 Docker 映象預設已包含 VikingBot，可通過 `--without-bot` 或 `OPENVIKING_WITH_BOT=0` 關閉。

根倉庫原有的 `First Release to PyPI` workflow 已刪除。當前 `bot/` 目錄沒有獨立的 `pyproject.toml`、`setup.py` 或 `setup.cfg`，因此不能從這個倉庫作為獨立 Python 包釋出。

同時，`bot/.github/workflows/release.yml` 位於 `bot` 子目錄，它應視為歷史上的 bot 子專案或拆分倉庫釋出參考，不應當作根倉庫當前可直接觸發的 GitHub Actions workflow。如需恢復獨立 `vikingbot` 包，需要先補齊 `bot/` 下獨立 Python 包配置、版本策略和釋出憑證策略。

## 發版前檢查清單

發版前建議逐項確認：

- 待發布改動已合入目標分支。
- CI / PR 檢查已通過。
- 版本號未在 PyPI、npm 或 Docker registry 中釋出過。
- tag 命名符合對應產物約定。
- Python 包依賴、構建配置和 README 已同步更新。
- Docker Hub、PyPI/TestPyPI、TOS、npm、ClawHub 等釋出所需 secrets 或 trusted publishing 配置可用。
- Release notes 已準備好，且說明破壞性變更、遷移步驟和重要修復。

## 發版後驗證清單

發版後建議驗證：

- PyPI / TestPyPI 上的包版本與 tag 一致。
- `pip install openviking==<version>` 或 `pip install openviking-sdk==<version>` 可成功安裝。
- Docker registry 中存在版本 tag 和預期的 `latest` / `main` tag。
- 多架構 Docker manifest 可正常拉取。
- TOS 版本化路徑和穩定路徑可訪問。
- npm 上存在對應 CLI 平臺包和 wrapper 包。
- ClawHub 外掛 channel 和 version 符合預期。

## 故障處理與補發原則

- PyPI 和 npm 已釋出版本通常不可覆蓋；如包內容有誤，應釋出新版本。
- Docker 的 `latest`、`main` 和手動指定 tag 可通過映象補發 workflow 重建，但應保留已釋出版本 tag 的可追溯性。
- TOS 的版本化路徑應視為不可變資產；穩定路徑可通過手動 workflow 覆蓋。
- 如果構建成功但釋出失敗，優先使用補發 workflow 或手動 dispatch，避免重新建立不同內容的同名 tag。
- 如 tag 命名錯誤，優先刪除錯誤 tag 並重新建立正確 tag，前提是該 tag 尚未觸發不可逆釋出。
