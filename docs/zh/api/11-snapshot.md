# 多版本管理（快照）

Business Data Platform 在 VikingFS 之上提供了一套基於 Git 的多版本管理能力，稱為**快照（Snapshot）**。它把某個帳號（account）下的整棵資源樹儲存成一系列不可變的提交（commit），讓你能夠回溯歷史、對比版本，並把工作區恢復到任意一個歷史狀態。

快照能力底層由內嵌在 Rust RAGFS 層的 [gitoxide](https://github.com/Byron/gitoxide) 驅動，按 `account_id` 維護一個邏輯 Git 倉庫（每個帳號一個倉庫），對呼叫方完全透明——你無需關心 `.ovgit` 目錄、物件庫或引用細節。

五個核心命令：

| 命令 | 作用 |
|------|------|
| `commit` | 把當前工作區狀態儲存成一個新快照 |
| `log` | 從最新提交開始回溯歷史 |
| `show` | 檢視某個提交的後設資料，或讀取該提交中某個檔案的內容 |
| `diff` | 以 unified diff 格式對比某個檔案在兩個快照中的內容 |
| `restore` | 把目錄（或整棵帳號樹）恢復到某個歷史快照的狀態 |

此外還提供帳號級 `.ovgitignore` 排除規則的管理命令（`get`/`set`/`delete`），用於在 `commit` 時按規則排除匹配的檔案。詳見 [ignore 管理](#ignore-管理)。

## 核心概念

- **提交（commit）**：一個快照對應一個提交，由 40 位十六進位制的 SHA-1 `commit_oid` 唯一標識。多數命令也接受 OID 的縮寫字首，或分支名（如 `main`）。
- **分支（branch）**：預設分支為 `main`。除非顯式傳入，所有命令都作用在 `main` 上。
- **正向恢復（forward-commit restore）**：`restore` **不會**回退或改寫歷史。它會讀取 `source_commit` 的內容，把差異寫回工作區，並在當前 HEAD 之上**生成一個新的提交**。因此新提交的父提交是恢復操作發生前的 HEAD，而**不是** `source_commit`。HEAD 始終單調向前推進，歷史永遠不會丟失。
- **作用範圍**：`commit` 可以通過 `paths` 限定只快照部分 URI；`restore` 可以通過 `project_dir` 限定只恢復某個子目錄，目錄之外的檔案保持不變。

## ACL 許可權

快照使用操作發生時的當前 ACL，不儲存、回滾或讀取歷史 ACL。未開啟 ACL 的公共資源保持原有的全部可見行為；開啟 ACL 後，許可權要求如下：

| 操作 | 許可權要求 |
|------|----------|
| `show(path=...)` / `diff` / `log` | `read` |
| `commit` | `write`；目錄會遞迴檢查當前全部子節點，任一子節點無權則整次失敗 |
| `restore` 覆蓋已有檔案 | 檔案的 `write` |
| `restore` 新建檔案 | 父目錄的 `write` |
| `restore` 刪除檔案 | 檔案的 `write` |
| `.ovgitignore` 讀寫刪除 | ADMIN |

USER 和 ADMIN 呼叫 `commit`、`log`、`restore` 時必須顯式傳入 `paths` 或 `project_dir`；`show` 必須傳入 `path`，不帶 `path` 的全域提交後設資料查詢只保留給本地 ROOT 模式。使用者可以操作自己有權訪問的公共資源和自己的 `viking://user/{user_id}/...`，不能訪問其他使用者空間。目錄操作會先完整鑑權，不會靜默跳過無權子節點；`restore` 會先鑑權全部寫入和刪除項，再開始修改。

恢復後的既有節點保留當前 ACL。被恢復的新節點繼承當前父目錄 ACL，不會給執行 `restore` 的使用者額外授予 `manage`。後臺向量重建屬於已授權操作的系統工作，不會再次受父目錄 ACL 阻斷。

## API 實現介紹

- HTTP 路由：[snapshot.py](https://github.com/volcengine/OpenViking/blob/main/openviking/server/routers/snapshot.py)，字首 `/api/v1/snapshot`。
- 名稱空間（SDK）：[client.py](https://github.com/volcengine/OpenViking/blob/main/sdk/python/openviking_sdk/client.py)，暴露為 `client.snapshot.*`。
- 底層語義實現：[_snapshot.py](https://github.com/volcengine/OpenViking/blob/main/openviking/storage/viking_fs/_snapshot.py) 的 `commit` / `restore` / `show` / `log` / `diff`。
- CLI 命令：[main.rs](https://github.com/volcengine/OpenViking/blob/main/crates/ov_cli/src/main.rs) 的 `SnapshotCmd`，子命令 [snapshot.rs](https://github.com/volcengine/OpenViking/blob/main/crates/ov_cli/src/commands/snapshot.rs)。

## API 參考

### commit()

把當前工作區狀態儲存成一個新的快照。

區域性提交保留範圍外的上次快照內容。刪除檔案或目錄後，仍需把該 URI 或其父目錄傳入 `paths` 才會記錄刪除。末尾 `/` 不宣告型別。非 ROOT 提交對現存檔案加 Exact、現存目錄加 Tree；缺失路徑在 filesystem 鎖後端不加鎖，在 cache 後端加 Tree。缺失目標的併發重建不保證被本次快照完整記錄，見 [提交範圍與併發](../guides/15-snapshot.md#提交範圍與併發)。

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| message | str | 是 | - | 提交說明 |
| paths | List[str] | 否 | null | 限定本次快照的 `viking://` URI 列表，條目可以是檔案或目錄；目錄會按照快照的剪枝規則遞迴展開。USER/ADMIN 必須顯式傳入；`null` 只保留給本地 ROOT 模式的整棵帳號樹快照。傳入空列表 `[]` 表示顯式的空路徑集（不會產生改動）。缺失路徑會從新快照移除此前的同名檔案及其子樹；若此前也不存在則告警並無改動 |
| branch | str | 否 | `main` | 要推進的分支 |
| author_name | str | 否 | null | 覆蓋預設的提交者名字（預設 `viking-bot`） |
| author_email | str | 否 | null | 覆蓋預設的提交者郵箱 |

**Python HTTP SDK**

```python
result = client.snapshot.commit(
    message="v1 initial import",
    paths=["viking://resources/my_md.md"],
)
print(result["commit_oid"])
```

**TypeScript SDK**

```typescript
console.log(await client.gitCommit({ message: "Update docs", paths: ["resources/docs"] }));
```

**HTTP API**

```
POST /api/v1/snapshot/commit
```

```bash
curl -X POST "http://localhost:1933/api/v1/snapshot/commit" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "message": "v1 initial import",
    "paths": ["viking://resources/my_md.md"]
  }'
```

**CLI**

```bash
ov snapshot commit -m "v1 initial import" --paths viking://resources/my_md.md -o json
```

**響應**

新建快照時：

```json
{
  "status": "ok",
  "result": {
    "result": "created",
    "commit_oid": "3f2a1b9c4d5e6f70819293a4b5c6d7e8f9a0b1c2",
    "changed": 3,
    "ignored": 1
  }
}
```

`changed` 為本次提交中新增/修改/刪除的路徑數；`ignored` 為本次被帳號 `.ovgitignore` 規則排除的候選路徑數（系統內建剪枝不計入）。當工作區相對上一次提交沒有任何變化時返回 `noop`，`commit_oid` 為當前 HEAD（`noop` 同樣返回 `ignored`，但不含 `changed`）：

```json
{
  "status": "ok",
  "result": {
    "result": "noop",
    "commit_oid": "3f2a1b9c4d5e6f70819293a4b5c6d7e8f9a0b1c2",
    "ignored": 0
  }
}
```

---

### log()

從某個分支的 HEAD 開始，沿首個父提交（`parents[0]`）逐層回溯歷史，按時間從新到舊返回提交列表。

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| branch | str | 否 | `main` | 要回溯的分支 |
| limit | int | 否 | 20 | 最多返回的提交數量。HTTP 介面限制範圍為 1–500 |
| paths | List[str] | 否 | null | 只返回修改了任一指定 `viking://` URI 的提交；USER/ADMIN 必須顯式傳入。本地 ROOT 模式可省略以查詢全域歷史。最多接受 32 條路徑，每條 account-relative 路徑最多包含 64 個層級。HTTP 介面通過重複 `paths` 查詢引數傳入多個 URI |

過濾發生在限制返回數量之前，因此 `limit=10` 和 `paths=[X]` 表示最多返回 10 條與 X 有關的提交，而不是先取最近 10 條提交再過濾。

為限制儲存開銷，過濾請求最多檢查 1,000 條提交。如果尚未收集到請求數量的匹配結果，並且仍存在未檢查的更早歷史，介面將返回 `INVALID_ARGUMENT` 錯誤，而不是返回不完整的歷史列表。非過濾請求不受該掃描預算限制，因為每檢查一條提交都會推進返回數量限制。

**Python HTTP SDK**

```python
history = client.snapshot.log(
    limit=10,
    paths=["viking://resources/a.md", "viking://resources/docs"],
)
for commit in history:
    print(commit["oid"], commit["message"])
```

**TypeScript SDK**

```typescript
console.log(
  await client.gitLog("main", 20, [
    "viking://resources/a.md",
    "viking://resources/docs",
  ]),
);
```

**HTTP API**

```
GET /api/v1/snapshot/log?branch={branch}&limit={limit}&paths={uri1}&paths={uri2}
```

```bash
curl --get "http://localhost:1933/api/v1/snapshot/log" \
  --data-urlencode "branch=main" \
  --data-urlencode "limit=10" \
  --data-urlencode "paths=viking://resources/a.md" \
  --data-urlencode "paths=viking://resources/docs" \
  -H "X-API-Key: your-key"
```

**CLI**

```bash
ov snapshot log --limit 10 \
  --paths viking://resources/a.md,viking://resources/docs \
  -o json
```

**響應**

`result` 是一個提交後設資料列表，每個元素與 [show()](#show) 返回的提交後設資料結構相同：

```json
{
  "status": "ok",
  "result": [
    {
      "oid": "9a0b1c2d3e4f5061728394a5b6c7d8e9f0a1b2c3",
      "tree": "11223344556677889900aabbccddeeff00112233",
      "parents": ["3f2a1b9c4d5e6f70819293a4b5c6d7e8f9a0b1c2"],
      "author": {
        "name": "viking-bot",
        "email": "bot@openviking.local",
        "time_seconds": 1750300000,
        "tz_offset_seconds": 28800
      },
      "committer": {
        "name": "viking-bot",
        "email": "bot@openviking.local",
        "time_seconds": 1750300000,
        "tz_offset_seconds": 28800
      },
      "message": "v2 modify delete add"
    }
  ]
}
```

> 當分支還沒有任何提交時，HTTP 介面返回 `404 NOT_FOUND`。

---

### show()

檢視某個提交的後設資料；如果同時指定 `path`，則返回該提交中對應檔案的內容。

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| target_ref | str | 是 | - | 提交 OID（支援縮寫字首）、分支名或標籤 |
| path | str | 否 | null | 某個檔案的 `viking://` URI；省略時返回提交後設資料，但僅限本地 ROOT 模式 |

**Python HTTP SDK**

```python
# 檢視提交後設資料（僅本地 ROOT 模式）
meta = client.snapshot.show("3f2a1b9c")
print(meta["message"], meta["parents"])

# 讀取該提交中某個檔案的內容
blob = client.snapshot.show("3f2a1b9c", path="viking://resources/my_project/guide.md")
```

**TypeScript SDK**

```typescript
console.log(await client.gitShow("main", "viking://resources/docs/api.md"));
```

> 注意：帶 `path` 讀取檔案內容時，Python 客戶端返回 `{"oid": str, "size": int, "bytes": bytes}` 字典。

**HTTP API**

```
GET /api/v1/snapshot/show?target_ref={ref}[&path={uri}]
```

```bash
# 提交後設資料（返回 JSON，僅本地 ROOT 模式）
curl -X GET "http://localhost:1933/api/v1/snapshot/show?target_ref=3f2a1b9c" \
  -H "X-API-Key: your-key"

# 讀取檔案內容（返回二進位制流）
curl -X GET "http://localhost:1933/api/v1/snapshot/show?target_ref=3f2a1b9c&path=viking://resources/my_project/guide.md" \
  -H "X-API-Key: your-key"
```

不帶 `path` 時返回提交後設資料 JSON；帶 `path` 時返回原始位元組流（`Content-Type: application/octet-stream`），並附帶兩個響應頭：

- `X-Snapshot-Oid`：blob 物件的 OID
- `X-Snapshot-Size`：blob 位元組數

**CLI**

```bash
# 提交後設資料（僅本地 ROOT 模式）
ov snapshot show 3f2a1b9c -o json

# 讀取檔案內容（預設輸出到 stdout，可用 --out-file 寫入本地檔案）
ov snapshot show 3f2a1b9c --path viking://resources/my_project/guide.md --out-file ./guide.md
```

**響應（提交後設資料）**

```json
{
  "status": "ok",
  "result": {
    "oid": "3f2a1b9c4d5e6f70819293a4b5c6d7e8f9a0b1c2",
    "tree": "00112233445566778899aabbccddeeff00112233",
    "parents": [],
    "author": {
      "name": "viking-bot",
      "email": "bot@openviking.local",
      "time_seconds": 1750299000,
      "tz_offset_seconds": 28800
    },
    "committer": {
      "name": "viking-bot",
      "email": "bot@openviking.local",
      "time_seconds": 1750299000,
      "tz_offset_seconds": 28800
    },
    "message": "v1 initial import"
  }
}
```

---

### diff()

對比一個 UTF-8 檔案在兩個快照引用中的內容，並返回 unified diff。`to_ref` 必填；省略 `from_ref` 時，舊版本按空檔案處理，可用於展示檔案的初始版本。

**Python HTTP SDK**

```python
result = client.snapshot.diff(
    "viking://resources/my_project/guide.md",
    from_ref="3f2a1b9c",
    to_ref="9a0b1c2d",
)
print(result["diff_text"])
```

**TypeScript SDK**

```typescript
const result = await client.gitDiff(
  "viking://resources/my_project/guide.md",
  "9a0b1c2d",
  "3f2a1b9c",
);
console.log(result.diff_text);
```

**HTTP API**

```
GET /api/v1/snapshot/diff?path={uri}&from={old_ref}&to={new_ref}
```

```bash
curl --get "http://localhost:1933/api/v1/snapshot/diff" \
  --data-urlencode "path=viking://resources/my_project/guide.md" \
  --data-urlencode "from=3f2a1b9c" \
  --data-urlencode "to=9a0b1c2d" \
  -H "X-API-Key: your-key"
```

**CLI**

```bash
ov snapshot diff viking://resources/my_project/guide.md \
  --from 3f2a1b9c \
  --to 9a0b1c2d
```

**響應**

```json
{
  "status": "ok",
  "result": {
    "path": "viking://resources/my_project/guide.md",
    "from_commit": "3f2a1b9c...",
    "to_commit": "9a0b1c2d...",
    "change_type": "modified",
    "diff_text": "--- a/guide.md\n+++ b/guide.md\n@@ -1 +1 @@\n-old line\n+new line\n"
  }
}
```

`change_type` 為 `added`、`deleted`、`modified` 或 `unchanged`。參與對比的單側檔案上限為 10 MiB 和 100,000 行，生成的 diff 上限為 20 MiB；超限時返回 `RESOURCE_EXHAUSTED`，不會返回被截斷的 diff。

---

### restore()

把某個目錄（或整棵帳號樹）恢復到 `source_commit` 時的狀態。

這是**正向恢復**：它會計算 `source_commit` 與當前 HEAD 之間的差異並寫回工作區，然後在當前 HEAD 之上生成一個**新的提交**。新提交的父提交是恢復前的 HEAD（而非 `source_commit`），歷史不會被改寫。`project_dir` 之外的檔案保持不變。

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| source_commit | str | 是 | - | 要恢復到的來源：提交 OID（支援縮寫字首）、分支名或標籤 |
| project_dir | str | 否 | null | 要恢復的子目錄 `viking://` URI；USER/ADMIN 必須顯式傳入，省略時恢復整棵帳號樹僅用於本地 ROOT 模式 |
| branch | str | 否 | `main` | 要推進的分支 |
| dry_run | bool | 否 | false | 僅計算並返回差異，不做任何寫入 |
| message | str | 否 | null | 新提交的說明；省略時自動生成 |
| author_name | str | 否 | null | 覆蓋預設的提交者名字 |
| author_email | str | 否 | null | 覆蓋預設的提交者郵箱 |

**Python HTTP SDK**

```python
result = client.snapshot.restore(
    project_dir="viking://resources/my_project",
    source_commit="3f2a1b9c",
    message="restore to v1",
)
print(result["result"], result["new_commit_oid"])

# 先預演，確認要改動哪些檔案
plan = client.snapshot.restore(
    project_dir="viking://resources/my_project",
    source_commit="3f2a1b9c",
    dry_run=True,
)
print(plan["diff"])
```

**TypeScript SDK**

```typescript
console.log(await client.gitRestore({
  projectDir: "viking://resources/docs",
  sourceCommit: "3f2a1b9c",
}));
```

**HTTP API**

```
POST /api/v1/snapshot/restore
```

```bash
curl -X POST "http://localhost:1933/api/v1/snapshot/restore" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "project_dir": "viking://resources/my_project",
    "source_commit": "3f2a1b9c",
    "message": "restore to v1"
  }'
```

**CLI**

```bash
# 位置引數依次為 <source_commit> <project_dir>
ov snapshot restore 3f2a1b9c viking://resources/my_project -m "restore to v1" -o json

# 預演
ov snapshot restore 3f2a1b9c viking://resources/my_project --dry-run -o json
```

**響應（applied）**

成功寫入並生成新提交時，`result` 為 `applied`。注意 `parent_commit` 等於恢復前的舊 HEAD，印證了正向恢復語義：

```json
{
  "status": "ok",
  "result": {
    "result": "applied",
    "new_commit_oid": "c3d4e5f60718293a4b5c6d7e8f9a0b1c2d3e4f50",
    "source_commit": "3f2a1b9c4d5e6f70819293a4b5c6d7e8f9a0b1c2",
    "parent_commit": "9a0b1c2d3e4f5061728394a5b6c7d8e9f0a1b2c3",
    "written": 1,
    "deleted": 1,
    "unchanged": 1,
    "written_paths": ["resources/my_project/guide.md"],
    "deleted_paths": ["resources/my_project/changelog.md"],
    "task_id": "snapshot_restore_reindex-..."
  }
}
```

當恢復產生向量副作用（寫入/刪除檔案）時，響應會附帶一個 `task_id`，可通過 `GET /api/v1/tasks/{task_id}` 輪詢後臺向量重建進度。

**響應（noop）**

來源與當前狀態位元組級一致、無需改動時返回 `noop`，不生成新提交：

```json
{
  "status": "ok",
  "result": {
    "result": "noop",
    "head": "9a0b1c2d3e4f5061728394a5b6c7d8e9f0a1b2c3",
    "source": "3f2a1b9c4d5e6f70819293a4b5c6d7e8f9a0b1c2"
  }
}
```

**響應（dry_run）**

`dry_run=true` 時只返回計劃差異，不做任何寫入。差異中的路徑均相對於 `project_dir`：

```json
{
  "status": "ok",
  "result": {
    "result": "dry_run",
    "head": "9a0b1c2d3e4f5061728394a5b6c7d8e9f0a1b2c3",
    "source": "3f2a1b9c4d5e6f70819293a4b5c6d7e8f9a0b1c2",
    "diff": {
      "to_write": [{"path": "guide.md", "oid": "..."}],
      "to_delete": ["changelog.md"],
      "unchanged": ["notes/todo.md"]
    }
  }
}
```

---

## ignore 管理

帳號根目錄下的 `.ovgitignore` 是帳號級排除規則檔案。在 `commit` 時，匹配規則的檔案被排除出快照；規則檔案本身不會被 `.ovgitignore` 規則忽略（即使規則匹配 `.ovgitignore` 也不會被排除），且不進入向量索引。規則隻影響 `commit`，不影響 `restore`/`show`/`log`。

語法為常見 glob 子集：空行被忽略、`#` 開頭為註釋、行首尾空白被裁剪；**不支援** `!` 取反與反斜槓轉義；檔案大小上限 64 KiB（寫入時即校驗）。匹配路徑為帳號相對 Git 樹路徑（`/` 分隔）。

提供三個方法：`get_gitignore`（讀取，缺失返回空串）、`set_gitignore`（寫入）、`delete_gitignore`（刪除，缺失即成功、冪等）。三者都要求 ADMIN 許可權，只需請求上下文中的帳號，無路徑引數。

### get_gitignore()

讀取帳號 `.ovgitignore` 內容；檔案不存在時返回空字串。

**Python HTTP SDK**

```python
content = client.snapshot.get_gitignore()
```

**TypeScript SDK**

```typescript
console.log(await client.gitGetIgnore());
```

**HTTP API**

```
GET /api/v1/snapshot/ignore
```

```bash
curl -X GET "http://localhost:1933/api/v1/snapshot/ignore" \
  -H "X-API-Key: your-key"
```

**CLI**

```bash
ov snapshot ignore-get -o json
```

**響應**

```json
{
  "status": "ok",
  "result": "*.log\n"
}
```

> 不帶 `-o json` 時，CLI 直接把原始內容打到 stdout（可重定向到檔案）。

### set_gitignore()

寫入帳號 `.ovgitignore` 內容（覆蓋）。寫入前校驗大小上限（64 KiB）；語法（取反、轉義等）在 `commit` 時由 Rust 層校驗。

**引數**

| 引數 | 型別 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| content | str | 是 | - | `.ovgitignore` 檔案內容（UTF-8） |

**Python HTTP SDK**

```python
client.snapshot.set_gitignore(content="*.log\n")
```

**TypeScript SDK**

```typescript
await client.gitSetIgnore("*.tmp\n.cache/\n");
```

**HTTP API**

```
PUT /api/v1/snapshot/ignore
```

```bash
curl -X PUT "http://localhost:1933/api/v1/snapshot/ignore" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"content": "*.log\n"}'
```

**CLI**

```bash
# 用 --content 直接傳內容，或用 --file 從檔案讀取
ov snapshot ignore-set --content "*.log" -o json
ov snapshot ignore-set --file ./my-rules -o json
```

**響應**

```json
{
  "status": "ok",
  "result": null
}
```

### delete_gitignore()

刪除帳號 `.ovgitignore`。檔案不存在也視為成功（冪等）。

**Python HTTP SDK**

```python
client.snapshot.delete_gitignore()
```

**TypeScript SDK**

```typescript
await client.gitDeleteIgnore();
```

**HTTP API**

```
DELETE /api/v1/snapshot/ignore
```

```bash
curl -X DELETE "http://localhost:1933/api/v1/snapshot/ignore" \
  -H "X-API-Key: your-key"
```

**CLI**

```bash
ov snapshot ignore-delete -o json
```

**響應**

```json
{
  "status": "ok",
  "result": null
}
```

## 典型流程

下面演示一個"提交 → 修改 → 恢復"的完整流程（Python SDK）：

```python
from openviking_sdk import SyncHTTPClient

client = SyncHTTPClient(url="http://localhost:1933", api_key="your-key")
client.initialize()

root = "viking://resources/my_project"

# 1. 寫入初始內容並提交 v1
client.write(
    uri=f"{root}/guide.md",
    content="# Guide\n\nv1 content\n",
    mode="create",
)
v1 = client.snapshot.commit(message="v1 initial import", paths=[root])

# 2. 修改後再提交 v2
client.write(
    uri=f"{root}/guide.md",
    content="# Guide\n\nv2 content\n",
    mode="replace",
)
v2 = client.snapshot.commit(message="v2 update", paths=[root])

# 3. 檢視歷史
for c in client.snapshot.log(limit=10, paths=[root]):
    print(c["oid"][:8], c["message"])

# 4. 把工作區恢復到 v1（會在 v2 之上生成一個新提交）
client.snapshot.restore(project_dir=root, source_commit=v1["commit_oid"], message="restore to v1")

client.close()
```

更多端到端示例參見倉庫中的 [examples/snapshot/](https://github.com/volcengine/OpenViking/tree/main/examples/snapshot) 目錄，涵蓋 SDK、HTTP、CLI 三種呼叫方式。

## 錯誤處理

| 場景 | HTTP 狀態碼 | 錯誤碼 |
|------|-------------|--------|
| 分支/提交不存在，或 `show` 的 `path` 在該提交中不存在 | 404 | `NOT_FOUND` |
| 未傳入必要的操作範圍，或當前身份缺少對應 ACL 許可權 | 403 | `PERMISSION_DENIED` |
| 恢復期間分支被併發提交改寫（CAS 衝突） | 409 | `CONFLICT` |
| `.ovgitignore` 過大、非 UTF-8，或包含不支援的 `!` 取反/反斜槓轉義語法（`commit` 時校驗） | 400 | `INVALID_ARGUMENT` |
| 請求體包含未知欄位（請求模型為 `extra="forbid"`） | 400 | `INVALID_ARGUMENT` |

## 相關文件

- [檔案系統](03-filesystem.md)：快照建立在檔案系統資源之上
- [系統](07-system.md)：通過 `GET /api/v1/tasks/{task_id}` 跟蹤 restore 觸發的後臺向量重建
- [API 概覽](01-overview.md)：完整端點總覽
