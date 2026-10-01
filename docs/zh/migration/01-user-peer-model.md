# OpenViking 0.3.x 到 0.4.0 升級指南

> **版本範圍：** 本頁記錄 0.3.x 到 0.4.0 的歷史遷移流程，不適用於當前版本的 Agent 目錄。當前 `viking://agent/...` 統一表示帳號內公共目錄，已移除 Agent ID 路徑相容及其遷移、cleanup。當前 `admin migrate` 只處理舊 Session 資料。

本文面向已經執行 OpenViking 0.3.x 的使用者，說明升級到 0.4.0 前後需要做什麼、哪些舊用法仍然相容、資料遷移如何執行，以及業務程式碼如何逐步遷移到新模型。

## 是否需要升級

如果繼續停留在 0.3.x，現有 `agent_id`、`viking://agent/...`、`viking://session/...` 行為不會變化，但也無法使用 0.4.0 的能力：

- 沒有 User / Peer 資料模型。
- 沒有 legacy agent/session 資料遷移和 cleanup 命令。
- 沒有 `actor_peer_id` 請求級 peer 檢視。
- 後續圍繞新模型的修復和能力不會回補到舊模型。

如果升級到 0.4.0，可以先不遷移資料。0.4.0 提供執行期相容，舊資料不會因為升級立即不可讀：

- `agent_id` 仍可臨時配置。當前 HTTP SDK client 會把它對映成請求級 `actor_peer_id`。
- `viking://agent/...` 仍可讀舊 agent 資料，但只讀。
- `viking://session/...` 仍可讀舊 session 資料，並會合並新 session 檢視。

推薦順序：

```text
備份
  -> 升級 server / CLI / SDK
  -> 驗證舊資料仍可讀
  -> 執行資料遷移
  -> 驗證新路徑
  -> 逐步遷移業務用法
  -> 可選 cleanup
```

## 升級前備份

先用 0.3.x 相容版本建立備份。建議使用 `0.3.24`：

```bash
pip install openviking==0.3.24 --upgrade --force-reinstall
ov backup ./backups/openviking-before-0.4.0.ovpack
```

確認當前版本：

```bash
python -c "import openviking; print(openviking.__version__)"
ov version
```

不要在 0.3.x 上執行 `ov --sudo admin migrate`。遷移命令只在 0.4.0 或更新版本可用。

## 升級服務和客戶端

安裝 0.4.0，重啟服務端，並確保 CLI / SDK 也升級到同一版本線：

```bash
pip install openviking==0.4.0 --upgrade --force-reinstall
openviking-server --config ov.conf
```

如果使用倉庫內 Rust `ov` CLI，需要重新構建或安裝 CLI；否則本地 `ov` 可能仍是舊二進位制。

升級後先驗證配置和舊資料讀取：

```bash
ov config validate
ov ls viking://agent
ov ls viking://session
ov session list
```

`viking://session` 的相容合併發生在服務端。只升級 CLI、不重啟 server，不會改變服務端讀取行為。

## 兼容性速查

| 舊用法 | 0.4.0 行為 |
| --- | --- |
| client 配置 `agent_id` | 支援。當前 HTTP SDK client 會對映成請求級 `actor_peer_id`；它本身不再觸發 legacy agent 模式。 |
| `ov ls viking://agent` | 支援讀；如果設定了 `agent_id` / `actor_peer_id`，只顯示當前 actor peer 對應的 legacy agent。 |
| 讀 `viking://agent/<agent_id>/...` | 支援讀舊資料。 |
| 寫 `viking://agent/...` | 不支援。新寫入應進入 `viking://user/<user_id>/peers/<peer_id>/...`。 |
| `ov ls viking://session` | 支援讀，會合並新 session 和舊 session。 |
| 讀 `viking://session/<session_id>/...` | 支援讀，按新路徑優先、舊路徑兜底。 |
| 寫 `viking://session/...` | 不支援。新 session 寫入 `viking://user/<user_id>/sessions/...`。 |
| HTTP SDK `find` / `search` 傳 `agent_id` | 支援，只查選中的 actor peer 檢視，不會自動查未遷移的舊 agent 資料。 |
| `find` / `search` body 傳舊 `peer_id` | 不支援。新 peer 檢視使用 `actor_peer_id` 或 `X-OpenViking-Actor-Peer`。 |
| 同時配置 `actor_peer_id` 和 `agent_id` | 不支援，會報錯。 |
| HTTP SDK `agent_id` client 下顯式傳 message `peer_id` | 支援。該 message 使用顯式 `peer_id`；未提供時不會從 `agent_id` 推導。 |
| `role_id` 記憶隔離 | 不再支援，升級後忽略。 |

## 執行資料遷移

確認升級後舊資料可讀，再執行遷移：

```bash
ov --sudo admin migrate --output json
```

響應會返回 task id：

```json
{
  "task_id": "..."
}
```

查詢任務：

```bash
ov --sudo task status <task_id>
ov --sudo task list --task-type legacy_migration
```

HTTP API：

```http
POST /api/v1/admin/migrate
X-API-Key: <root-key>
```

請求體可以為空，等價於：

```json
{
  "action": "migrate"
}
```

查詢任務：

```http
GET /api/v1/tasks/{task_id}
X-API-Key: <root-key>
```

ROOT 查詢遷移任務時不會按普通 account/user 過濾。遷移會為整個儲存建立一個 root 級別 task，不會按 account 分別建立 task。

## 遷移規則

0.4.0 的新模型是 User / Peer：

```text
User = 自然人或業務使用者
Peer = User 下的互動物件
Session = User 下的會話狀態
Skill = User 下的可執行技能
```

遷移目標：

| 舊資料 | 新位置 |
| --- | --- |
| `viking://agent/<agent_id>/memories/...` | `viking://user/<user_id>/peers/<agent_id>/memories/...` |
| `viking://agent/<agent_id>/resources/...` | `viking://user/<user_id>/peers/<agent_id>/resources/...` |
| `viking://agent/<agent_id>/skills/<skill>/...` | `viking://user/<user_id>/skills/<skill>/...` |
| `viking://session/<session_id>/...` | `viking://user/<user_id>/sessions/<session_id>/...` |

共享 legacy agent 資料會複製到每個目標 user 的 peer 目錄。如果舊路徑已經表達了 user owner，只遷移到該 user。

遷移會一併處理已有向量索引：對實際複製成功的 memory / resource / skill 檔案或目錄，直接讀取舊記錄中的 `vector` / `sparse_vector` 和標量欄位，重寫 URI 後寫入新記錄。遷移不會重新向量化，也不會自動呼叫 `reindex`。共享 legacy agent 資料複製到多個 user 時，會按每個目標 user URI 寫入多份向量記錄。

沒有向量 payload 的舊標量記錄會跳過並計入 `migrated.skipped_vector_records`。Session 遷移只複製檔案狀態，不處理向量索引。

Session owner 按以下順序解析：

1. `.meta.json.created_by_user_id`
2. `.meta.json.user_id`、`.meta.json.owner_user_id` 或 `.meta.json.created_by`
3. 舊路徑裡的 user hint，例如 `/session/alice/sess-001`
4. 單使用者 account 下的唯一註冊使用者

多使用者 account 下，如果某個 legacy session 無法識別 owner，preflight 會失敗。升級後的執行期相容可以臨時讀取舊 session，但正式遷移前仍應補齊 owner。

Legacy agent instructions 不遷移：

```text
viking://agent/<agent_id>/instructions
```

遷移會記錄 warning，不建立替代目錄。

## 遷移前檢查

以下問題會在 task 建立前直接失敗：

- 物理儲存中存在 legacy 資料，但對應 account 不在 API key user registry 中。
- 多使用者 account 下存在無法識別 owner 的 legacy session。
- session owner 存在，但不是合法的 OpenViking user id。

以下問題會記錄為 warning 或 skipped，並繼續遷移：

- 目標 user 已經存在同名 skill。舊 skill 會被跳過，不覆蓋現有 skill。
- 發現 legacy agent instructions。Instructions 不遷移。
- 存在共享 legacy agent，但 account 下沒有可遷移的目標 user。

如果遷移發現 legacy 資料 owner 不在 user registry 中，會自動註冊該 user。遷移結果只記錄自動建立了哪些使用者，不返回明文 user key。

如果開啟了 `api_key_hashing`，明文 key 無法從儲存中反查。需要重新生成：

```bash
ov --sudo admin regenerate-key <account_id> <user_id>
```

## 驗證遷移結果

檢視任務結果：

```bash
ov --sudo task status <task_id>
```

重點看：

- `migrated.files` / `migrated.directories`
- `migrated.vector_records` / `migrated.skipped_vector_records`
- `migrated.operations`
- `skipped`
- `warnings`
- `created_users`

驗證新路徑：

```bash
ov ls viking://user/<user_id>/peers/<agent_id>/memories
ov ls viking://user/<user_id>/skills
ov ls viking://user/<user_id>/sessions
```

遷移只複製資料，不刪除 legacy 路徑或舊向量記錄。重複執行是冪等的：已存在的目標檔案和 skill 會被跳過，不會覆蓋。如果遷移後的檢索結果不符合預期，再由使用者對新路徑手動執行 `reindex`；遷移流程本身不會觸發 reindex。

## 業務用法遷移

### Client 配置

舊配置可以先繼續用：

```json
{
  "agent_id": "legacy-agent"
}
```

推薦逐步改成：

```json
{
  "actor_peer_id": "legacy-agent"
}
```

不要同時配置：

```json
{
  "actor_peer_id": "customer-a",
  "agent_id": "legacy-agent"
}
```

這會報錯。

### 檔案路徑

舊路徑：

```text
viking://agent/code-agent/memories/profile.md
viking://session/sess-001/messages.jsonl
```

新路徑：

```text
viking://user/alice/peers/code-agent/memories/profile.md
viking://user/alice/sessions/sess-001/messages.jsonl
```

`viking://session/<session_id>` 可以繼續作為當前 user session 的讀 alias 使用，但新寫入和長期引用建議使用 `viking://user/<user_id>/sessions/<session_id>`。

### find / search

`find` / `search` 不再接受 legacy agent 身份欄位，也不會自動包含未遷移的舊 agent 資料。舊 `viking://agent/...` 路徑仍可通過內容和檔案系統介面只讀訪問，但應先完成遷移再使用新檢索路徑。

遷移完成並確認不再需要舊 agent 資料後，所有 client 都改為 client/request 級 `actor_peer_id`。

### 會話訊息

Session 不再從 legacy agent id 推導訊息歸屬；需要表達說話人時必須顯式使用 message `peer_id`。

## 暫不遷移資料

升級後可以暫時不遷移，但要知道這些限制：

- 舊 agent/session 資料可讀，但舊 namespace 不可寫。
- 新 session 和新資源會寫入新 namespace，資料會在新舊路徑並存一段時間。
- `find` / `search` 不會預設查舊 `viking://agent` 資料。
- 多使用者 account 下 owner 不明確的舊 session，執行期可能可讀，但正式遷移會被 preflight 攔截。
- cleanup 之前舊目錄和舊向量記錄仍會保留。

因此不遷移適合作為短期過渡，不建議作為長期狀態。

## 可選 cleanup

確認遷移結果無誤後，可以刪除舊 namespace：

```bash
ov --sudo admin migrate --cleanup --output json
ov --sudo task status <cleanup_task_id>
```

HTTP 請求體：

```json
{
  "action": "cleanup"
}
```

Cleanup 只刪除：

```text
/local/<account>/agent
/local/<account>/session
/local/<account>/user/<user>/agent
```

Cleanup 會先刪除上述 legacy URI scope 下的舊向量記錄，再刪除對應 AGFS 目錄。若向量讀取或刪除失敗，該目錄會被跳過，避免舊檔案已刪除但舊索引仍殘留。Cleanup 不會刪除新 user / peer 路徑下的檔案或向量記錄。

不會刪除新模型目錄：

```text
/local/<account>/user/<user>/peers
/local/<account>/user/<user>/sessions
/local/<account>/user/<user>/skills
```

Cleanup 後，`viking://agent/...` 不再用於讀取遷移後的 peer 資料；請使用新路徑。`viking://session/...` 仍可作為當前 user session 的 alias 讀取新 session。

## 常見問題

### ov ls viking://agent 只看到一個 agent

如果配置了 `agent_id` 或 `actor_peer_id`，這是預期行為。`viking://agent` 根目錄會過濾到當前 actor peer，只顯示對應 legacy agent。

### ov ls viking://session 仍為空

確認服務端已經重啟並載入 0.4.0。`viking://session` 的合併讀發生在服務端；只升級 CLI 不會改變服務端讀取行為。

### 配置同時有 actor_peer_id 和 agent_id

這是不允許的。保留 `agent_id` 進入 legacy 模式，或刪除 `agent_id` 後改用 `actor_peer_id`。

### Preflight 報告 unknown account

物理儲存中存在某個 account 的 legacy 資料，但 API key registry 中沒有這個 account。先恢復或重新建立該 account，再重新執行遷移。

### Preflight 報告 unresolved session owner

給 legacy session 的 `.meta.json` 補充 owner 欄位，或把 session 移到能明確識別 owner 的舊路徑下，然後重新執行遷移。

### 某個 skill 沒有遷移

檢視 task 的 `skipped` 列表。最常見原因是目標 user 已經存在同名 skill。遷移不會覆蓋現有 skill。
