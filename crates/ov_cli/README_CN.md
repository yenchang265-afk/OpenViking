# OpenViking CLI

[OpenViking](https://github.com/volcengine/OpenViking) 的命令列客戶端。OpenViking 是面向 Agent 的上下文資料庫。

本目錄構建原生 `ov` 二進位制。你可以用它配置 OpenViking 連線、匯入資源、瀏覽 `viking://` 路徑、檢索上下文、檢視服務狀態、管理 session，以及執行管理員操作。

English documentation: [README.md](README.md).

## 安裝

### 通過 npm 安裝

```bash
npm i -g @openviking/cli
```

npm 包會安裝適配 macOS、Linux 或 Windows 的平臺二進位制。

### 從原始碼安裝

```bash
# OpenViking 要求 Rust >= 1.91.1。
cargo install --path crates/ov_cli
```

如果你正在本 crate 內開發：

```bash
cd crates/ov_cli
cargo install --path .
```

## 配置

推薦使用互動式配置管理器：

```bash
ov config
```

`ov config` 可以新增、編輯、刪除、校驗和切換配置。CLI 會把當前 active 客戶端配置寫到 `~/.openviking/ovcli.conf`。命名配置會儲存為 `~/.openviking/ovcli.conf.<name>`，`ov config switch <name>` 會把選中的命名配置複製為 active 配置。

較新的 CLI 版本在非互動式 shell 中執行大多數命令前，需要先儲存顯示語言：

```bash
ov language en
# 或
ov language zh-CN
```

指令碼和 Agent 場景建議使用確定性的配置命令，並通過 stdin 或已有環境變數傳遞金鑰：

```bash
# OpenViking Service
printf '%s' "$OPENVIKING_API_KEY" | \
  ov config add ov-service --name prod --api-key-stdin --activate -o json

# 本地無鑑權自定義服務
ov config add custom --name local --url http://127.0.0.1:1933 --activate -o json

# 使用 user API key 的遠端自定義服務
printf '%s' "$OPENVIKING_API_KEY" | \
  ov config add custom --name remote --url https://ov.example.com --api-key-stdin --activate -o json
```

驗證 active 配置：

```bash
ov config show
ov config list -o json
ov config validate
ov health
ov status
```

`ov config show` 會隱藏金鑰。除非你明確知道 `~/.openviking/ovcli.conf` 可能包含 API Key，否則不要直接列印原始配置檔案。

### 手動配置檔案

仍然支援手動編輯配置。一個最小的自定義服務配置示例如下：

```json
{
  "url": "http://localhost:1933",
  "api_key": "your-api-key",
  "account": "acme",
  "user": "alice"
}
```

使用普通 user API key 時，`account` 和 `user` 通常可以省略，因為服務端可以從 key 推導身份。使用 `trusted` 鑑權或租戶級操作時，建議顯式配置它們。僅 root key 的配置必須顯式配置 `account` 和 `user`，因為 root key 本身不包含租戶身份。

更完整的配置說明見 [docs/zh/getting-started/05-cli-setup.md](../../docs/zh/getting-started/05-cli-setup.md)。

## 快速開始

```bash
# 檢查連線
ov health
ov status

# 新增資源並等待處理完成
ov add-resource https://raw.githubusercontent.com/volcengine/OpenViking/refs/heads/main/docs/en/about/01-about-us.md --wait

# 瀏覽上下文
ov ls viking://resources
ov tree viking://resources -L 2
ov read viking://resources/...

# 檢索上下文
ov find "what is openviking"
ov grep "openviking" --uri viking://resources
```

當前安裝版本的準確命令面以 `ov --help` 和 `ov <command> --help` 為準。

## 命令分組

### 資源管理

- `add-resource` - 匯入本地檔案、目錄、URL、Git 倉庫和支援的文件源。
- `add-skill` - 從目錄、`SKILL.md` 或原始內容新增 skill。
- `skills` - 列出、檢索、檢視、更新、刪除和校驗已安裝 skills。
- `export` / `import` - 以 `.ovpack` 格式匯出或匯入上下文。
- `backup` / `restore` - 把公共 OpenViking scope 備份或恢復為 restore-only `.ovpack`。

### 檔案系統

- `ls` - 列出目錄內容。
- `tree` - 顯示目錄樹。
- `mkdir` - 建立目錄。
- `rm` - 刪除資源或目錄。
- `cp` - 複製檔案，或使用 `-r` 遞迴複製目錄。
- `mv` - 移動或重新命名資源。
- `stat` - 檢視資源後設資料。
- `attrs` - 獲取邏輯擴充屬性。
- `get` - 下載檔案到本地路徑。

```bash
# 目標父目錄必須已存在；已有檔案直接覆蓋，已有目錄遞迴合併。
ov cp viking://resources/docs/guide.md viking://resources/archive/guide-copy.md
ov cp -r viking://resources/docs viking://resources/docs-backup
```

### 內容訪問

- `read` - 讀取 L2 全量內容。
- `abstract` - 讀取 L0 摘要。
- `overview` - 讀取 L1 概覽。
- `write` - 替換、追加或建立文本內容。

### 搜索

- `find` - 語義檢索。
- `search` - 上下文感知檢索，實驗特性。
- `grep` - 內容模式搜尋。
- `glob` - 文件 glob 搜索。

### Session 與記憶

- `session new` - 建立 session，並可設定事件記憶預設 tags 和自動提交策略。
- `session list` - 列出 sessions。
- `session get` - 檢視 session 詳情。
- `session get-session-context` - 獲取合併後的 session 上下文。
- `session add-message` / `session add-messages` - 向 session 添加消息。
- `session config set` - 更新 session 的可變配置。
- `session commit` - 歸檔訊息並抽取記憶，可覆蓋本次事件 tags。
- `add-memory` - 一次性建立 session、新增訊息並提交，實驗特性。

```bash
ov session new --session-id s1 --event-tags team=search,channel=web \
  --auto-commit-policy-json '{"message_count_threshold":25}'
ov session new --session-id s2 --no-auto-commit
ov session config set s1 --event-tags team=search,channel=app
ov session config set s1 --auto-commit-policy-json '{"message_count_threshold":25}'
ov session config set s1 --no-auto-commit
ov session commit s1 --event-tags team=search,channel=web
ov session commit s1 --no-event-tags
```

### 交互式工具

- `tui` - 互動式檔案瀏覽器。
- `chat` - 與 vikingbot agent 對話。

### 狀態與可觀測性

- `health` - 快速健康檢查。
- `status` - 聚合服務元件狀態。
- `wait` - 等待非同步處理佇列完成。
- `task status` / `task list` - 跟蹤非同步任務。
- `task watch` - 管理自動重新整理 watch 任務。
- `observer queue` - 佇列狀態。
- `observer vikingdb` - VikingDB 狀態。
- `observer models` - VLM、embedding 和 rerank 模型狀態。
- `observer retrieval` - 檢索質量指標。
- `observer filesystem` - 檔案系統操作指標。
- `observer system` - 整體系統狀態。

### 配置

- `config` - 交互式配置管理器。
- `config show` - 顯示 active 配置並隱藏金鑰。
- `config validate` - 校驗 active 配置。
- `config list` - 列出命名配置。
- `config switch` - 切換 active 配置。
- `config add` - 非交互式新增命名配置。
- `config edit` - 非互動式編輯命名配置。
- `config delete` - 刪除命名配置。
- `language` / `lang` - 選擇 CLI 顯示語言（`en` 或 `zh-CN`）。
- `version` - 顯示 CLI 版本。

### 工作區快照

- `snapshot commit` - 建立工作區快照。
- `snapshot restore` - 把路徑或工作區恢復到歷史快照。
- `snapshot show` - 顯示 commit 後設資料或 blob 內容。
- `snapshot log` - 檢視快照歷史。
- `snapshot ignore-get` / `snapshot ignore-set` / `snapshot ignore-delete` - 管理 account `.ovgitignore`。

### 隱私

- `privacy` - 管理隱私配置分類、目標、版本和 active 配置。

### 管理員命令

需要 `root_api_key` 的命令使用 `--sudo`。

- `admin create-account` - 建立 account 和首個 admin 使用者。
- `admin list-accounts` - 列出 accounts，僅 ROOT。
- `admin delete-account` - 刪除 account，僅 ROOT。
- `admin register-user` - 註冊使用者。
- `admin list-users` - 列出 account 內使用者。
- `admin remove-user` - 移除使用者。
- `admin set-role` - 修改使用者角色，僅 ROOT。
- `admin regenerate-key` - 輪轉使用者 API key。
- `admin migrate` - 遷移 legacy agent/session 資料，僅 ROOT。
- `system` - 管理類系統工具命令。
- `reindex` - 為 URI 重建語義和向量產物。

## 輸出格式

預設輸出是面向人的表格或卡片渲染。指令碼中建議使用 JSON：

```bash
ov -o json ls viking://resources
ov -o json config list
```

部分幫助文本也可能展示長引數 `--output json`。`-o json` 是測試和自動化示例中常用的緊湊寫法。

## 示例

```bash
# 新增 URL 並等待處理完成
ov add-resource https://example.com/docs --wait --timeout 60

# 新增本地目錄並過濾檔案
ov add-resource ./dir \
  --wait --timeout 600 \
  --ignore-dirs "node_modules,dist" \
  --include "*.md,*.py" \
  --exclude "*.tmp,*.log"

# 匯入到可預測的父路徑
ov add-resource ./docs -p "viking://resources/docs/{calendar:today}" --wait

# 帶過濾條件的搜尋
ov find "API authentication" --threshold 0.7 --limit 5
ov find "authentication" --uri viking://resources/project --level 0,1

# 遞迴列目錄
ov ls viking://resources --recursive

# 按修改時間排序並分頁
ov ls viking://resources --offset 100 --limit 50 \
  --sort-by mtime --sort-order desc
ov tree viking://resources --offset 100 --limit 50

# 寫入呼叫方提供的 tags，再按 tags 過濾或回顯
ov write viking://resources/docs/api.md --content "# API" \
  --tags team=search,env=prod
ov ls viking://resources/docs --tags team=search,env=prod --fields tags
ov grep "TODO" --uri viking://resources/docs --tags team=search,env=prod
ov glob "**/*.md" --uri viking://resources/docs --tags team=search,env=prod

# 臨時通過 CLI 引數覆蓋身份
ov --account acme --user alice ls viking://

# 使用 root API key 執行管理員命令
ov --sudo admin create-account acme --admin alice --seed alice-seed
ov admin register-user acme bob --role user --seed bob-seed
ov admin regenerate-key acme bob --seed bob-new-seed

# Glob 搜索
ov glob "**/*.md" --uri viking://resources
ov glob "**/*.md" --uri viking://resources -f tags

# Session 工作流
SESSION=$(ov -o json session new | jq -r '.result.session_id')
ov session add-message "$SESSION" --role user --content "Hello"
ov session commit "$SESSION"

# Watch 任務管理
ov add-resource https://example.com/docs --to viking://resources/docs --watch-interval 60
ov task watch ls
ov task watch trigger viking://resources/docs
```

## 開發

```bash
# 構建
cargo build --release

# 使用剛構建出的精確二進位制做 smoke
target/release/ov --version
target/release/ov -o json health

# 執行測試
cargo test

# 本地安裝
cargo install --path .
```

驅動外部 e2e harness 時，請顯式指向 `target/release/ov`，避免誤用 `PATH` 中已經安裝的舊版 `ov`。
