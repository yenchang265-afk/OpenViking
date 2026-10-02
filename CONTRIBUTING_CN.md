# 為 Business Data Platform 做貢獻

[English](CONTRIBUTING.md) / 中文 / [日本語](CONTRIBUTING_JA.md)

感謝你參與 Business Data Platform。本指南旨在幫助貢獻者提交清晰、聚焦且便於評審的改動。

我們歡迎 Bug 報告、功能請求、文件改進和程式碼貢獻。

## 我們重視什麼

Business Data Platform 重視聚焦且經過充分理解的改動。無論是否使用 AI 工具，貢獻者都要對
理解、解釋和驗證自己的改動負責。

優先提交最小而完整的改動。程式碼簡潔，是減少概念、分支、重複規則和猜測式抽象，
不是壓縮必要的程式碼行數。好的改動應當直接、易讀，並且能從入口到可觀察行為解釋清楚。

具體來說：

- 一個 PR 只解決一個內聚的問題，不要混入無關清理或重構。
- 複用現有規則的 Owner，不要引入平行機制。
- 避免猜測式 Fallback、Flag、狀態欄位和抽象。
- 刪除被新實現替代的程式碼、測試和相容路徑。
- 當必要結構能讓職責、生命週期或失敗處理更清楚時，應當保留它。

### 評審優先順序

維護者精力有限，因此會優先檢視聚焦的 PR：

- **改動不超過 100 行**的 PR，通常能得到更及時的檢視。
- **改動不超過 200 行**的 PR，會比更大的 PR 優先檢視。

這只是評審優先順序，不是硬性限制或響應時間承諾。改動行數按手寫原始碼、測試和文件的
新增行與刪除行之和計算；生成檔案、第三方程式碼和鎖檔案不計入規模判斷。

不要為了控制行數省略必要的測試或文件。只有當拆分後的每個 PR 都能獨立理解且保持
正確時，才拆分大改動。PR 小不代表可以降低正確性、設計質量或相容性要求。

## 開始之前

1. 全域搜尋已有 Issue、PR 和程式碼，確認是否已經存在相同的行為或領域規則。
2. 修復 Bug 時，儘量通過真實生產入口復現問題。
3. 確認 Owner 模組，並追蹤相關值或狀態在哪裡建立、規範化、儲存和消費。
4. 開發功能時，先說明要解決的問題和預期行為，再設計實現。

以下改動應在實現前先提交 Issue 或發起討論：

- 公開的 REST、SDK、CLI、MCP 或配置語義；
- 持久化資料、儲存 Schema、VFS/AGFS 路徑或加密檔案行為；
- 非同步任務歸屬、佇列、取消、清理或結果狀態；
- 資源匯入與監聽、Session 生命週期或記憶抽取；
- 檢索 Level、目錄範圍或排序語義；
- Tenant、Account、User 或 Peer 身份邊界；
- 涉及多個 Owner 模組或大型架構重構。

討論中請給出當前行為、目標行為、具體請求或配置示例，以及相容性影響。這樣維護者
可以在開始實現前確認設計邊界。

請使用倉庫提供的 GitHub 模板提交 [Bug 報告](https://github.com/volcengine/OpenViking/issues/new?template=bug_report.yml)、
[功能請求](https://github.com/volcengine/OpenViking/issues/new?template=feature_request.yml)和
[使用問題](https://github.com/volcengine/OpenViking/issues/new?template=question.yml)。

## 找到正確的模組

如果已知受影響模組，請在 Issue 或 PR 中註明。如果不確定，先描述可觀察行為和使用場景，
維護者會協助路由。

這張表根據 2026 年 6 月 24 日至 8 月 24 日已合併 PR 中持續的提交和評審活動整理。
它用於協助路由，不代表排他性的程式碼所有權；只需 @ 與改動直接相關的聯絡人。

| 領域 | 模組 | 代表路徑或主題 | 近期活躍維護者 / 評審者 |
|---|---|---|---|
| Platform | Server、API、Auth、Identity、Admin、Task | `openviking/server`、`openviking/service` | `@qin-ctx` |
| Resource | 匯入、Watch 與任務流水線 | `openviking/resource` | `@qin-ctx`、`@KCHENPENGFEI` |
| Resource | 資源解析 | `openviking/parse` | `@zihengli-bytedance`、`@KCHENPENGFEI` |
| Memory | Session、記憶抽取與編譯 | `openviking/session`、記憶抽取、`ov compile` | `@chenjw`、`@heaoxiang-ai`、`@fujiajie666` |
| Retrieval | Search 與 VectorDB | `openviking/retrieve`、`openviking/storage/vectordb` | `@zhoujh01`、`@t0saki` |
| Storage | RAGFS、PathLock、QueueFS 與加密 | `openviking/storage`、`openviking/pyagfs`、`openviking/crypto`、`crates/ragfs*` | `@baojun-zhang` |
| Integration | Agent Plugin 與 MCP | `agent-plugins`、記憶外掛示例、Server MCP | `@t0saki`、`@ZaynJarvis` |
| Integration | VikingBot 與 Agent 編譯 | `bot`、`ov compile` | `@yeshion23333`、`@fujiajie666` |
| Client | SDK、CLI 與 LangChain | `sdk`、`crates/ov_cli`、`examples/langchain` | `@zhoujh01`、`@t0saki`、`@ehz0ah` |
| Product | Web Studio | `web-studio` | `@yufeng201`、`@ZaynJarvis` |
| Project | 文件、CI 與 Plugin 釋出 | `docs`、`.github/workflows` | `@yufeng201`、`@ZaynJarvis` |

跨模組改動或 Owner 不明確時，請先確認主要影響域，再 @ `@qin-ctx`、`@ZaynJarvis` 或 `@zhoujh01`。

## 開發環境

### 前置要求

- Python 3.10+
- 從原始碼構建、開發 Rust Binding 或內建 `ov` CLI 時需要 Rust 1.91.1+
- 僅開發 `sdk/go` 時需要 Go 1.22+
- 支援 C++17 的編譯器：GCC 9+ 或 Clang 11+
- CMake 3.15+

Linux 請安裝 `build-essential`，部分環境還需要 `pkg-config`。macOS 請安裝 Xcode
Command Line Tools。Windows 本地原生構建請安裝 CMake 和 MinGW。

### 安裝

Fork 倉庫，然後克隆自己的 Fork：

```bash
git clone https://github.com/YOUR_USERNAME/OpenViking.git
cd Business Data Platform
```

推薦使用 `uv`：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --all-extras
```

驗證環境：

```bash
uv run python -c "import openviking; print(openviking.__version__)"
```

配置本地 Server：

```bash
uv run openviking-server init
uv run openviking-server doctor
```

配置說明和 Provider 示例見[配置指南](https://docs.openviking.ai/zh/guides/01-configuration)。

修改 RAGFS Rust Binding、內建 Rust CLI 或 C++ 擴充後，需要重新構建原生元件：

```bash
uv pip install -e . --force-reinstall
```

SDK、Integration、Plugin 和 Benchmark 可能有額外要求，請檢視對應目錄中的 README 或
包配置。

## 修改程式碼

### 職責與設計

- 行為應放在所屬模組中。上層只負責傳輸或消費結果，不要重複實現相同規則。
- 在邊界把外部兼容表達轉換為唯一的規範領域模型，內層業務邏輯不應猜測輸入形態。
- 面向客戶端的邊界應保留有意義的 Server、Network、Timeout、Auth 和 Conflict 錯誤。
- 任務狀態必須與產生它的任務保持因果關聯，不能通過全域佇列狀態或無關回調推斷完成。
- 每個值和規則只保留一個權威來源。

如果區域性邊緣 Case 開始改變任務邊界、公開語義或整體架構，應暫停實現並回到設計討論，
不要在主流程中不斷增加特殊分支。

### 安全開發要求

以下要求定義了 Business Data Platform 的變更必須遵守的安全邊界，用於開發評審和安全整改，不代表所有現有功能或已釋出版本都已符合要求。

#### 不可信輸入不得轉變為可執行命令

外部請求、工具引數、匯入資料、後設資料和模型輸出都必須視為不可信輸入。通過身份認證或擁有資源訪問許可權，不代表擁有在伺服器上執行命令的許可權。

- 不得將不可信值拼接進 Shell 命令或可執行程式碼。資料操作必須始終區分資料與指令，下游工具和整合也必須遵守這一要求。
- 確實需要呼叫外部程式時，必須使用由服務端控制的可執行程式和結構化引數。僅停用 Shell 並不足夠，還必須按業務語義校驗輸入，防止其被解釋為命令選項。在支援時使用選項結束標記；不得通過普通資料 API 提供任意命令或額外命令引數的透傳能力。
- 必須控制可執行程式的查詢路徑、子程序環境和工具配置。不可信輸入不得通過配置或其他間接機制啟用額外執行能力。環境中隱式繼承的配置不得悄然擴大服務端操作的許可權或行為範圍。
- 通過服務端工作流提供的 Agent 和 Skill 執行能力，必須執行在隔離環境中，並明確限制檔案系統、網路和憑據的訪問範圍。不得預設在宿主機執行，也不得回退到宿主機執行。工作目錄、提示詞和命令黑名單都不能代替沙箱。停用命令執行時，也必須阻止通過檔案工具或其他間接路徑執行命令。

#### 遠端操作不得訪問任意伺服器檔案

服務端 API 應操作經過授權的 Business Data Platform 資源和上傳檔案，不得訪問任意宿主機路徑。對服務管理的儲存進行合法訪問時，也必須遵守已認證帳號、使用者和資源許可權限定的範圍。

- 不得接受伺服器本地路徑或 `file://` URL，用於匯入、讀取、搜尋、預覽或匯出宿主機檔案。遠端客戶端必須使用經過授權的資源 URI，或屬於請求主體的上傳檔案。不得通過這些操作或錯誤響應暴露伺服器配置、憑據、程序環境相關檔案或其他租戶的資料。
- 必須在解析路徑並實際執行檔案操作的層級落實路徑範圍限制和許可權校驗。檢查解析後的最終目標，覆蓋路徑穿越、編碼路徑、絕對路徑、符號連結和歸檔檔案條目。僅檢查原始路徑字串或呼叫方的初始目錄並不足夠；每個被訪問的檔案都必須處於允許範圍內。
- 間接訪問也必須遵守同樣的邊界：匯入的程式碼倉庫和歸檔檔案、上傳檔案、生成產物、搜尋結果及 Agent 工具都不得繞過限制。遠端獲取和重定向不得轉變為本地檔案訪問或未經授權的內部服務訪問。
- 本地運維流程可以按設計訪問本地檔案或執行管理命令，但這些許可權必須明確授予，不能讓遠端呼叫方通過請求引數、工具引數或匯入內容獲得這些許可權。

#### 驗證與報告

涉及上述邊界的修改，必須沿真實呼叫鏈追蹤不可信輸入，覆蓋相關 API、服務層、原生繫結層、外部程式和檔案系統操作。在相應邊界驗證形似命令選項的輸入、Shell 特殊字元、特製檔案內容、路徑穿越、符號連結和跨租戶訪問。通過聚焦的契約測試或範圍受控的復現進行驗證；正常請求成功不能證明隔離有效。

命令或引數注入、任意伺服器檔案訪問，以及突破預定執行邊界或租戶邊界的行為都屬於安全問題。疑似問題應通過 [SECURITY.md](SECURITY.md) 中的私密渠道報告。公開文件和 PR 應說明必須遵守的安全邊界，不得披露尚未修復問題的利用方法或敏感資料。

### 程式碼風格

Python 使用 Ruff 進行格式化和 Lint，使用 mypy 進行型別檢查，配置行寬為 100 字元。

對改動路徑執行檢查：

```bash
uv run ruff format <changed-paths>
uv run ruff check <changed-paths>
uv run mypy <changed-paths>
```

公開 API 應包含簡短且有用的 Docstring。優先使用清晰命名和直接控制流，不要用註釋
重複解釋程式碼本身。

Rust、Go、TypeScript、文件和 Plugin 改動，請使用對應元件定義的格式化、Lint、型別檢查
和測試命令。

### 測試

驗證受影響的最小有效公開契約和主要失敗邊界。

- 優先修改已有的高價值契約測試。
- 預設不要新增單元測試或測試檔案。
- 不要測試私有 Helper 是否存在、Mock 呼叫順序、簡單欄位透傳或框架行為，除非它保護
  長期公開契約。
- 小而明確的修復不必自動新增測試，但必須說明驗證方式。
- 臨時復現、診斷、壓測和驗證指令碼統一放在 `test_scripts/`，不要放入原始碼、Benchmark
  或維護指令碼目錄。

執行相關的聚焦測試，例如：

```bash
uv run pytest tests/client/test_http_client_config.py
uv run pytest tests/server/ -k "search"
```

只有改動範圍和風險需要時才執行完整 Python 測試：

```bash
uv run pytest
```

## 提交 Pull Request

基於最新的 `main` 建立分支，完成聚焦改動後向 `main` 提交 PR。

Commit Message 和 PR 標題使用 [Conventional Commits](https://www.conventionalcommits.org/)：

```text
feat(parser): support xlsx resources
fix(retrieval): preserve rerank score order
docs: clarify server configuration
refactor(storage): remove duplicate path normalization
```

完整填寫倉庫的 PR 模板。有效的 PR 描述應說明：

- 改動前後的可觀察行為；
- Bug 的根因和真實執行路徑；
- 受影響的入口和 Owner 模組；
- 相容性或遷移影響；
- 實際執行的驗證命令；
- 問題已經復現，還是僅根據程式碼推斷。

請準確選擇 Human Involvement。專案接受 AI 輔助貢獻，但作者仍對改動負責，並且必須
能解釋它與系統其他部分如何互動。

提交前：

- 完整檢查 Diff，刪除無關或意外生成的改動。
- 確認被替代的 Helper、分支、Mock 和註釋已經刪除。
- 公開行為變化時更新相關文件。
- 如實說明未執行的檢查及具體原因，不要聲稱執行了實際未執行的測試。

CI 會根據受影響路徑執行相應檢查。CI 通過是必要條件，但不能替代作者驗證和維護者評審。

## 文件

專案文件位於 `docs/en/` 和 `docs/zh/`。程式碼示例必須可執行，語言應清晰簡潔；當對應
翻譯存在時，應同步更新兩種語言。

## 社群

請保持尊重、包容、建設性，並聚焦技術討論。開放式設計或使用討論請前往
[GitHub Discussions](https://github.com/volcengine/OpenViking/discussions)，可執行的 Bug
和功能請求請提交到 [GitHub Issues](https://github.com/volcengine/OpenViking/issues)。
