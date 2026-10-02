# 多版本管理（快照）指南

本指南介紹如何啟用並使用 Business Data Platform 的多版本管理（快照）能力。多版本管理在 VikingFS 之上提供基於 Git 的 `commit`/`log`/`show`/`restore` 原語，讓你把帳號下的資源樹儲存成一系列不可變快照，隨時回溯歷史、對比版本，並把工作區恢復到任意歷史狀態。

多版本管理由內嵌在 Rust RAGFS 層的 [gitoxide](https://github.com/Byron/gitoxide) 驅動，以 `account_id` 為粒度維護一個邏輯 Git 倉庫（每個帳號一個倉庫），對呼叫方完全透明——你無需手動執行任何 `git` 命令。

> 關於各命令引數和響應結構的完整 API 參考，見 [多版本管理 API](../api/11-snapshot.md)。

## 何時需要 commit

普通 `write`、`rm` 等操作直接改變當前工作區，啟用快照不代表每次寫入都會自動生成版本。沒有成功覆蓋該路徑的 snapshot commit，就不能通過快照找回它此前的內容。建議在匯入完成、批次修改前後或一個業務階段結束時提交，並儲存返回的 `commit_oid`。

Snapshot 儲存檔案樹的版本，不會回滾當前 ACL，也不儲存向量索引的歷史。`restore` 寫回檔案後按需非同步重建索引；它會修改工作區，執行前先用 `dry_run` 檢查計劃。

`client.snapshot.commit()` 與會話的 `session.commit()` 職責不同：前者儲存檔案版本，後者歸檔對話並處理記憶。部分記憶流程會在更新 experience 後呼叫 snapshot，這不等於所有寫入都自動快照。

## 提交範圍與併發

USER / ADMIN 必須給 `commit` 和 `log` 傳入 `paths`，給 `restore` 傳入 `project_dir`，給 `show` 傳入檔案 `path`。只有本地 ROOT 可以省略這些範圍引數。對自己有寫許可權的專案目錄提交，可以避免把無關資源納入同一次快照。

| `commit(paths=...)` 輸入 | 含義 |
| --- | --- |
| 現存檔案 URI | 處理該檔案 |
| 現存目錄 URI | 遞迴處理當前檔案，並記錄此前快照中該子樹內檔案的刪除 |
| 缺失 URI | 記錄此前快照中該路徑及其子樹的刪除；此前也不存在則無改動 |
| `[]` | 顯式空範圍，不產生改動 |
| `None` / 省略 | 整棵帳號樹，僅限 ROOT |

區域性提交沿用分支上一次快照作為基礎，範圍外檔案保留原快照版本。刪除後仍要提交被刪除 URI 或覆蓋它的父目錄；從 `paths` 中去掉該 URI 會漏記刪除。路徑末尾 `/` 不是檔案/目錄型別宣告，當前介面沒有逐目標的顯式型別引數。

非 ROOT 的顯式路徑提交先按當前狀態選鎖，再檢查範圍許可權並生成快照：

| 目標狀態 | Filesystem PathLock | Cache（Redis）PathLock |
| --- | --- | --- |
| 現存檔案 | Exact | Exact |
| 現存目錄 | Tree | Tree |
| 缺失路徑 | 跳過該目標的鎖 | Tree |

Filesystem 對缺失目標跳過鎖，避免鎖檔案建立目標目錄或缺失的父目錄鏈；該目標仍參與快照刪除處理。此時併發重建同一路徑可能被漏記或讀到尚未寫完的內容，後續提交才能記錄最終狀態。ROOT 不經過這段顯式路徑加鎖流程。

快照不能視為任意併發 I/O 的全域原子檢視。需要確定的業務檢查點時，應先結束該範圍內的寫入，再提交；鎖只協調參與 [PathLock 協議](../concepts/09-transaction.md) 的操作。

## 前置條件

- 已有可用的 `ov.conf`。
- 已確認資源的讀寫正常（多版本管理建立在檔案系統資源之上）。
- 如果選擇 S3 後端存放 Git 物件，已準備好 bucket、region、endpoint 和訪問憑據。

## 啟用多版本管理

多版本管理預設**開啟**（`git.enabled` 預設為 `true`）。Git 物件的儲存後端可以選擇 `local`（本地檔案系統）或 `s3`（S3 相容物件儲存）；當不顯式設定 `git.backend` 時，會**自動繼承 `storage.agfs.backend`**（`storage.agfs.backend` 為 `memory` 時對映為 `local`）。如需關閉多版本管理，把 `git.enabled` 設為 `false` 即可。

### 本地後端（推薦用於單機部署）

```json
{
  "storage": {
    "workspace": "./data"
  },
  "git": {
    "enabled": true,
    "backend": "local",
    "default_branch": "main",
    "author_name": "viking-bot",
    "author_email": "bot@viking.local",
    "local": {
      "base_dir": ""
    }
  }
}
```

配置說明：

| 欄位 | 預設值 | 說明 |
|------|--------|------|
| `git.enabled` | `true` | 是否啟用多版本管理。設為 `false` 可關閉快照功能 |
| `git.backend` | 繼承 `storage.agfs.backend` | Git 物件後端：`local` 或 `s3`。不顯式設定時繼承 `storage.agfs.backend`（`memory` 對映為 `local`） |
| `git.default_branch` | `main` | 未顯式指定時使用的預設分支名 |
| `git.author_name` | `viking-bot` | 呼叫方未傳 `author_name` 時使用的預設提交者名字 |
| `git.author_email` | `bot@viking.local` | 預設提交者郵箱 |
| `git.local.base_dir` | `""` | Git 物件/引用的存放目錄。**留空時預設使用 `{storage.workspace}/.ovgit`** |

> 通常把 `git.local.base_dir` 留空即可，讓快照資料自動落在工作區下的 `.ovgit` 目錄，便於和資源資料一起備份與遷移。

### S3 後端（推薦用於分散式/雲端部署）

把 Git 物件與引用存到 S3 相容物件儲存（如火山引擎 TOS、MinIO、AWS S3）。當 `backend` 為 `s3` 時，**必須**提供 `git.s3` 段，且 `bucket`、`region` 不能為空。

> 提示：`git.s3` 的 `bucket`、`region`、`endpoint`、`access_key`、`secret_key` 在未顯式設定時會**自動繼承 `storage.agfs.s3`** 的對應欄位。因此當 `storage.agfs` 已經配置為 s3 後端時，通常無需重複填寫 `git.s3`——只要不顯式設定 `git.backend`，多版本管理會直接複用 `storage.agfs` 的 bucket 與訪問憑據。

```json
{
  "storage": {
    "workspace": "./data"
  },
  "git": {
    "enabled": true,
    "backend": "s3",
    "default_branch": "main",
    "author_name": "viking-bot",
    "author_email": "bot@viking.local",
    "s3": {
      "bucket": "your-tos-bucket",
      "region": "cn-beijing",
      "endpoint": "https://tos-s3-cn-beijing.volces.com",
      "access_key": "<your-volcengine-ak>",
      "secret_key": "<your-volcengine-sk>",
      "prefix": ".ovgit",
      "use_path_style": false,
      "cas_mode": "native"
    }
  }
}
```

配置說明：

| 欄位 | 預設值 | 說明 |
|------|--------|------|
| `git.s3.bucket` | 繼承 `storage.agfs.s3.bucket` | 存放 Git 物件/引用的 bucket，必填（可由 `storage.agfs.s3` 繼承） |
| `git.s3.region` | 繼承 `storage.agfs.s3.region`，否則 `us-east-1` | bucket 所在區域，必填 |
| `git.s3.prefix` | `.ovgit` | 鍵字首，所有資料存放在 `{prefix}/{account}/...` 下 |
| `git.s3.endpoint` | 繼承 `storage.agfs.s3.endpoint`，否則 `""` | 自定義 S3 端點（MinIO/TOS 等）；標準 AWS S3 留空 |
| `git.s3.access_key` / `git.s3.secret_key` | 繼承 `storage.agfs.s3` 對應欄位，否則 `null` | 直接讀取的憑據；留空則走 SDK 預設憑據鏈 |
| `git.s3.use_path_style` | `true` | `true` 用 path-style 定址（MinIO 等）；`false` 用 virtual-host 定址（TOS 等） |
| `git.s3.cas_mode` | `native` | 引用 CAS 模式。`native` 使用 S3 條件寫（If-Match） |

修改配置後，重啟 Business Data Platform 服務（或重新初始化 SDK 客戶端）使其生效。

> 倉庫中提供了可直接參考的完整示例：[ov.conf.git-local.example](https://github.com/volcengine/OpenViking/blob/main/examples/snapshot/ov.conf.git-local.example) 與 [ov.conf.git-s3-tos.example](https://github.com/volcengine/OpenViking/blob/main/examples/snapshot/ov.conf.git-s3-tos.example)。

## 目錄結構變化：`.ovgit` 目錄

啟用 `local` 後端且 `base_dir` 留空時，Business Data Platform 會在工作區下新增一個 **`.ovgit`** 目錄用於存放 Git 物件和引用：

```text
data/                      # storage.workspace
├── viking/                # 使用者可見的資源樹（viking:// 對映到這裡）
│   └── ...
└── .ovgit/                # 多版本管理資料（新增）
    └── {account_id}/      # 每個帳號一個邏輯 Git 倉庫
        ├── objects/       # Git 物件（commit/tree/blob），標準 fanout 佈局 aa/bb...
        ├── refs/
        │   └── heads/
        │       └── main   # 分支引用，內容為 40 位十六進位制 OID
        └── HEAD           # 當前分支指標，內容為 "ref: refs/heads/main"
```

要點：

- `.ovgit` 是內部資料目錄，**不會**通過 `viking://` 暴露，使用者在檔案系統 API（`ls`/`read` 等）中看不到也無法修改它。
- 它與 Git 的標準物件庫佈局一致（內容定址的 `objects/`、loose 引用的 `refs/`），但由 Business Data Platform 自動管理，**無需也不應**手動執行 `git` 命令去操作它。
- 備份或遷移工作區時，把 `.ovgit` 一併複製即可保留完整的版本歷史。
- 選擇 `s3` 後端時，不會建立本地 `.ovgit` 目錄，資料改為存放在 bucket 的 `{prefix}/{account}/...` 鍵下。

## 使用方法

啟用後，三種呼叫方式都會出現快照相關命令。下面以一個"提交 → 修改 → 恢復"的最小流程演示。

### Python SDK

快照方法掛在 `client.snapshot.*` 名稱空間下。

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
print("v1:", v1["commit_oid"])

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

# 4. 讀取歷史檔案內容
print(client.snapshot.show(v1["commit_oid"], path=f"{root}/guide.md"))

# 5. 把工作區恢復到 v1（會在 v2 之上生成一個新的“正向”提交）
client.snapshot.restore(project_dir=root, source_commit=v1["commit_oid"], message="restore to v1")

client.close()
```

### CLI

CLI 子命令位於 `ov snapshot` 下：

```bash
# 提交當前工作區狀態
ov snapshot commit -m "v1 initial import" --paths viking://resources/my_project -o json

# 回溯歷史（最新在前）
ov snapshot log --paths viking://resources/my_project --limit 10 -o json

# 讀取歷史檔案內容
ov snapshot show <commit_oid> --path viking://resources/my_project/guide.md

# 讀取某個提交中的檔案內容（預設輸出到 stdout，可用 --out-file 寫入本地檔案）
ov snapshot show <commit_oid> --path viking://resources/my_project/guide.md --out-file ./guide.md

# 把目錄恢復到某個歷史快照（位置引數依次為 <source_commit> <project_dir>）
ov snapshot restore <commit_oid> viking://resources/my_project -m "restore to v1" -o json

# 先預演，確認會改動哪些檔案
ov snapshot restore <commit_oid> viking://resources/my_project --dry-run -o json
```

### HTTP API

```bash
# 提交
curl -X POST "http://localhost:1933/api/v1/snapshot/commit" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"message": "v1 initial import", "paths": ["viking://resources/my_project"]}'

# 回溯歷史
curl -X GET "http://localhost:1933/api/v1/snapshot/log?branch=main&limit=10&paths=viking://resources/my_project" \
  -H "X-API-Key: your-key"

# 讀取歷史檔案內容
curl -X GET "http://localhost:1933/api/v1/snapshot/show?target_ref=<commit_oid>&path=viking://resources/my_project/guide.md" \
  -H "X-API-Key: your-key"

# 恢復
curl -X POST "http://localhost:1933/api/v1/snapshot/restore" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"project_dir": "viking://resources/my_project", "source_commit": "<commit_oid>", "message": "restore to v1"}'
```

## 重要語義：正向恢復

`restore` 採用**正向恢復（forward-commit）**：它讀取 `source_commit` 的內容，把差異寫回工作區，並在**當前 HEAD 之上生成一個新的提交**。因此：

- 新提交的父提交是恢復操作發生前的 HEAD，**不是** `source_commit`。
- HEAD 始終單調向前推進，**歷史永遠不會被改寫或丟失**——回到舊版本本身也是一次新的提交。
- `restore` 隻影響 `project_dir`（省略時為整棵帳號樹）範圍內的檔案，範圍之外的檔案保持不變。

## 使用 `.ovgitignore` 排除文件

帳號根目錄下的 `.ovgitignore` 是一個帳號級的排除規則檔案，作用類似根 `.gitignore`：匹配該規則的檔案在 `commit` 時被排除出快照。它與系統內建的剪枝規則（`_system`、`tasks`、向量索引派生檔案等）疊加生效。

要點：

- 規則檔案本身**不會被 `.ovgitignore` 規則忽略**，即使規則匹配 `.ovgitignore` 也會被正常納入快照——這樣規則的變更可追溯、可恢復。
- 規則**隻影響 `commit`**；`restore`、`show`、`log` 仍以提交內容為準，不把當前 `.ovgitignore` 當作過濾器。因此恢復一個歷史快照時，即便其中某些檔案匹配當前規則，仍會被正常恢復。
- 若某個檔案在更早的提交中已被跟蹤、之後新增規則匹配到它，下一次 `commit` 會把它從新快照中移除（工作區的檔案本身不受影響）。
- `.ovgitignore` 不會進入向量索引/檢索。

### 規則語法

`.ovgitignore` 為 UTF-8 文本，支援常見的 glob 子集：

- 空行被忽略。
- 首個非空白字元為 `#` 的行是註釋。
- 行首/行尾空白會被裁剪。
- **不支援** `!` 取反（出現會讓 `commit` 失敗並報錯）。
- **不支援** Git 風格的反斜槓轉義。
- 文件大小上限 64 KiB。

匹配路徑使用帳號相對的 Git 樹路徑（`/` 分隔），如 `resources/proj/a.log`。例如 `*.log` 匹配任意深度的 `.log` 檔案，`build/` 匹配名為 `build` 的目錄及其內容，`/cache/**` 僅匹配帳號根下的 `cache/`。

### Python SDK

```python
# 寫入規則
client.snapshot.set_gitignore(content="*.log\n")

# 讀取（不存在時返回空字串）
print(client.snapshot.get_gitignore())

# 刪除（不存在也視為成功，冪等）
client.snapshot.delete_gitignore()
```

隨後提交時，匹配規則的檔案會被排除，響應裡的 `ignored` 欄位給出本次被排除的候選路徑數：

```python
v = client.snapshot.commit(message="with ignore", paths=["viking://resources/my_project"])
print(v["result"], v.get("ignored"))  # created, 1
```

### CLI

```bash
# 設定（用 --content 直接傳內容，或用 --file 從檔案讀取）
ov snapshot ignore-set --content "*.log" -o json
ov snapshot ignore-set --file ./my-rules -o json

# 讀取（-o json 返回 {"result": "<內容>"}；不加 -o json 時直接把內容打到 stdout）
ov snapshot ignore-get -o json

# 刪除（冪等）
ov snapshot ignore-delete -o json
```

### HTTP API

```bash
# 讀取
curl -X GET "http://localhost:1933/api/v1/snapshot/ignore" \
  -H "X-API-Key: your-key"

# 寫入
curl -X PUT "http://localhost:1933/api/v1/snapshot/ignore" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"content": "*.log\n"}'

# 刪除
curl -X DELETE "http://localhost:1933/api/v1/snapshot/ignore" \
  -H "X-API-Key: your-key"
```

## 注意事項

- 修改 `git` 配置後必須重啟服務 / 重新初始化客戶端才能生效。
- 啟用 `s3` 後端時，`git.s3.bucket` 與 `git.s3.region` 為必填項，缺失會導致初始化失敗。
- 恢復操作如涉及向量副作用（寫入/刪除檔案），響應會返回一個 `task_id`，可通過 `GET /api/v1/tasks/{task_id}` 輪詢後臺向量重建進度（參見 [系統指南](05-observability.md) 與 [API 概覽](../api/01-overview.md)）。
- `.ovgitignore` 內容過大（超過 64 KiB）或包含 `!` 取反、反斜槓轉義等不支援語法時，`commit` 會失敗並報 `invalid operation` 錯誤；寫入時（`set_gitignore`）會預先校驗大小。
- 不要手動用外部 `git` 工具去操作 `.ovgit` 目錄，它由 Business Data Platform 維護。

## 相關文件

- [多版本管理 API](../api/11-snapshot.md)：命令引數與響應的完整參考
- [配置說明](01-configuration.md)：`ov.conf` 完整配置項
- [多寫儲存指南](13-multi-write-storage.md)：資源資料的多後端複製
