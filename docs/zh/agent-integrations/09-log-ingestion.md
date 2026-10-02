# 匯入本地 Agent 日誌（openviking-server ingest）

`openviking-server ingest` 把你本地已有的 AI 編碼 / agent harness 的對話日誌（Claude Code、Codex、WorkBuddy、OpenCode、MiMo、Hermes、OpenClaw）解析成標準訊息，再通過 Business Data Platform 既有的會話管線“重放”進去（`建立會話 → 批次追加訊息 → 提交`，提交時觸發記憶抽取），從而把這些歷史與新增對話沉澱為長期記憶。它與各 harness 的“記憶外掛”互補：外掛在對話**進行時**即時掛載捕獲，而本工具用於**匯入既有日誌**與**離線監聽新增日誌**，無需外掛、也無需改動對應 harness。

與外掛方案的關鍵區別：本工具是 Business Data Platform 的**客戶端**，跑在日誌所在的機器上，通過 SDK 指向本地或遠端 server；它預設**完全關閉**，不會“裝上就掃你本地檔案”。

原始碼：[openviking/ingest](https://github.com/volcengine/OpenViking/tree/main/openviking/ingest)

## 預設關閉

該特性預設雙重關閉，必須顯式開啟：

- 總開關 `ingest.enabled` 預設 `false`；
- 每個 harness 的 `enabled` 預設 `false`，未列出的 harness 不會被讀取；
- 存量回填需手動執行命令，且支援 `--dry-run`（只統計、不寫入）與 `--since`（限定時間窗）先行驗證。

## 支持的 harness

| harness | 狀態 | 預設日誌路徑 | 說明 |
|---|---|---|---|
| `claude_code` | 支援 | `~/.claude/projects/*/*.jsonl` | append-only JSONL，位元組偏移游標 |
| `codex` | 支持 | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` | append-only JSONL |
| `workbuddy` | 支援 | `~/.workbuddy/projects/*/*.jsonl` | append-only JSONL；會把系統提示等注入到 user 輪裡，介面卡會剝離並只保留 `<user_query>` |
| `hermes` | 支援 | `~/.hermes/sessions/*.jsonl` | 群聊 agent，user 取原始使用者名稱 |
| `openclaw` | 支援 | `~/.openclaw/agents/*/sessions/*.jsonl` | 群聊 agent，user 取原始使用者名稱 |
| `opencode` | 實驗性 | `~/.local/share/opencode/opencode.db` | SQLite，按 `(time, id)` 輪詢；舊版檔案儲存暫不支援 |
| `mimo` | 實驗性 | `~/.local/share/mimocode/mimocode.db` | SQLite，按 `(time, id)` 輪詢；跳過 `part.synthetic` 文本與 `agent_id != main` |
| `cursor` | 暫緩 | `~/Library/Application Support/Cursor/User/**/state.vscdb` | 無文件、隨版本漂移的 KV blob，暫未實現 |

> 這裡的 harness（agent 框架）指 CC / Codex 等整套工具，區別於 Business Data Platform 裡“tool（工具呼叫）”的概念。

## 在 ov.conf 中開啟

先在執行 ingest 命令的同一 shell 中設定以下變數。示例連線本地 dev 服務；認證部署應替換 URL，並使用繫結租戶身份的 user/admin API Key：

```bash
export OPENVIKING_URL="http://localhost:1933"
export OPENVIKING_API_KEY=""  # 僅用於本地 dev；認證部署應填寫 user/admin key。
```

配置載入器會展開這些變數。未設定的變數會保留為字面字串，因此使用下面的佔位值時不要跳過此步驟。

在 `ov.conf` 增加 `ingest` 段，列出要匯入的 harness 並設定其模式：

```json
{
  "ingest": {
    "enabled": true,
    "server_url": "$OPENVIKING_URL",
    "api_key": "$OPENVIKING_API_KEY",
    "account": "default",
    "user": "default",
    "harnesses": {
      "claude_code": { "enabled": true, "mode": "both" },
      "codex":       { "enabled": true, "mode": "backfill" },
      "workbuddy":   { "enabled": true, "mode": "both" },
      "opencode":    { "enabled": false, "mode": "watch", "experimental": true },
      "mimo":        { "enabled": false, "mode": "watch", "experimental": true },
      "hermes":      { "enabled": false, "mode": "both", "user_field": "sender" },
      "openclaw":    { "enabled": false, "mode": "both", "user_field": "sender" }
    }
  }
}
```

- `mode`：`off` | `backfill`（一次性匯入存量）| `watch`（監聽新增）| `both`。
- `paths`：覆蓋該 harness 的預設發現路徑（可填多個）。
- `user_field`：群聊 harness 中存放原始使用者名稱的欄位名，用作 user 側 peer_id。
- `commit`：提交策略，含 `commit_token_threshold`、`commit_idle_seconds`、`keep_recent_count`。
- 部署期開關也可用環境變數覆蓋：`OPENVIKING_INGEST_ENABLED`、`OPENVIKING_INGEST_SERVER_URL`、`OPENVIKING_INGEST_API_KEY`。

`server_url` 留空時回退到 `OPENVIKING_URL` 或 `http://localhost:1933`，因此既能指向本地 server，也能指向遠端。

## 使用

`openviking-server ingest` 命令隨 Business Data Platform 一同安裝。

```bash
# 檢視已註冊 harness 及其配置
openviking-server ingest list-sources

# 先幹跑：統計會回填多少 session / 訊息，不寫入
openviking-server ingest backfill --dry-run

# 只回填某個 harness、且只回填某日期之後的會話
openviking-server ingest backfill --harness claude_code --since 2026-06-01

# 正式回填（存量）
openviking-server ingest backfill

# 監聽新增日誌並增量重放（前臺阻塞）
openviking-server ingest watch --harness claude_code

# 按每個 harness 配置的 mode 執行：先回填再監聽
openviking-server ingest run

# 檢視各會話已匯入到哪裡（讀取游標狀態）
openviking-server ingest status
```

`--reset` 會在重放前刪除並重建對應的 OV 會話；不加 `--reset` 時，重複執行是冪等的（游標保證不會重複追加）。

## peer_id

每條訊息都會帶上 peer_id，便於 Business Data Platform 同時為人類與模型建立畫像：

- assistant 訊息：`{harness}/{模型名}`（provider 有意義時為 `{harness}/{provider}/{模型名}`），例如 `claude_code/claude-opus-4-8`、`opencode/bytedance_ark/doubao-...`；
- user 訊息：單使用者開發型 harness（claude_code / codex / opencode）取會話 cwd 所在倉庫的 git 身份（`user.email` / `user.name`），無 git 倉庫時回退為配置的 `ingest.user`；群聊 harness（hermes / openclaw）取日誌裡的原始使用者名稱（由 `user_field` 指定）。

任何包含非 ASCII 字元的標識（例如中文或混合文字使用者名稱）都會將完整標識編碼為無碰撞的
`ext-<base64>` 形式。`ext-` 名稱空間為編碼身份保留；如果 ASCII 身份清理後會成為
`ext-` id，系統也會對其編碼，避免它冒充已有編碼身份。新的讀取和寫入只使用規範 id。
舊版本可能把多個混合文字身份，或一個混合文字身份與真實 ASCII 身份，摺疊到同一個 peer
目錄中。Business Data Platform 不會把這些歸屬不明確的目錄自動附加為別名；遷移既有資料前，
運維人員必須先確認其真實歸屬。

## 工作原理

每個 harness 對應一個輕量介面卡，把其日誌解析為標準訊息，交給“重放器”執行 `ensure_session → 批次追加（每批 ≤100）→ commit`。記憶抽取只在 **commit** 時由 server 端觸發。OV 會話 id 形如 `import__{harness}__{原始會話id}`，確定且冪等。

- **存量回填**：列舉所有會話，從游標讀到末尾後逐會話提交一次。
- **監聽增量**：參照 Business Data Platform 自身的 `WatchScheduler`，用**定時輪詢**（非檔案系統事件）+ 持久游標驅動；漏一拍、休眠或重啟後，下一拍從游標讀到末尾即可自愈。JSONL 用位元組偏移游標（含半行/截斷/輪轉處理），SQLite 用 `(time, id)` 游標只讀讀取（相容 WAL）。

游標狀態持久化在 `~/.openviking/ingest/state.db`，因此回填與監聽都能在重啟後續傳，且不會重複入庫。

## 成本與隱私

- 提交會觸發記憶抽取（LLM 呼叫）。一次性回填數月曆史可能產生大量呼叫，建議先 `--dry-run`、用 `--since` 收窄時間窗、按 harness 分批開啟。
- 日誌中可能含敏感內容（憑據、檔案內容）。請在受信任的部署中使用，並確認 `server_url` 指向你期望的 server。
- tool 呼叫的輸入/輸出預設按低價值丟棄，僅入庫 user / assistant 文本。

## 參見

- [整合能力參考](./16-capability-reference.md)
- [概覽](./01-overview.md) — 各 harness 的記憶外掛（即時捕獲方案）
- [部署指南 → CLI](../guides/03-deployment.md#cli) — `ov.conf` / 憑據配置
