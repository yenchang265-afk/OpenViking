# 資源訪問控制（ACL）

OpenViking ACL 用於在同一個 account 內，把共享資源目錄或檔案授權給使用者或使用者組。ACL 不改變 account 隔離：任何授權都只在當前 account 內生效。

ACL 採用協作文件式的繼承模型。目錄授權預設持續作用於所有後代，子目錄和檔案可以繼續增加直接授權，也可以用 restricted 模式在某個節點切斷繼承許可權。

## 適用 URI

ACL 只作用於共享資源：

```text
viking://resources/...
```

- `viking://resources/...` 的 account `ADMIN` 隱式擁有 `manage`。
- `viking://resources` 的根 ACL 固定為 `user:* = manage`，不可修改；下級節點預設繼承，直到 restricted 邊界。
- `viking://user/{user_id}/resources/...` 是個人私有區，不接受 ACL。需要分享時，將資源移動到有權寫入的共享目錄，並繼承該目錄的 ACL。

隱式管理權不會寫入 ACL 條目，也不能被 ACL 刪除。它保證共享資源始終有人能夠首次設定或恢復許可權。

## Principal 與許可權級別

ACL 條目使用帶型別的 principal：

- `user:{user_id}`：當前 account 內的使用者。
- `group:{group_id}`：由呼叫者指定、在當前 account 內唯一的使用者組 ID。
- `user:*`：當前 account 內任意使用者。

不支援 `group:*`。使用者組是平鋪結構；修改成員關係不會重寫資源 ACL 或 context 記錄，而是在下一次請求構造 `RequestContext.group_ids` 時生效。
請求建立的非同步解析和語義任務會攜帶同一份 group 身份。`add-resource` 寫入目標通過鑑權後，自動語義維護會保留原呼叫者身份，並顯式使用內部 ACL bypass，不會把呼叫者角色改成 `ADMIN`。

| Level | 允許的操作 |
|-------|------------|
| `read` | 讀取、列目錄、`find/search/grep` |
| `write` | `read` 的能力，以及寫入、建立、刪除或移動檔案、修改 tags |
| `manage` | `write` 的能力，以及刪除或移動目錄、管理 ACL |

高等級包含低等級能力。授予 `manage`，等價於同時授予 `read` 和 `write`。

## 繼承規則

普通節點合併 direct 與 inherited；restricted 節點只使用 direct：

```text
effective(node) = direct(node) + (acl_mode(node) == "restricted" ? empty : inherited(node))
```

`inherited(node)` 始終儲存父節點當前的有效許可權。即使節點處於 restricted 模式，這個欄位也會隨父節點繼續更新；退出 restricted 後會立即使用最新 inherited。後代繼承的是當前節點的有效許可權，因此不會繞過中間的 restricted 邊界。

例如，先將 `A` 設為 restricted，截斷根目錄的全員管理授權，再配置：

```text
read user:bob   on viking://resources/A
write group:engineering on viking://resources/A/B
read user:carol on viking://resources/A/B/C/report.md
```

`report.md` 的有效許可權為：

- Bob：`read`
- `engineering` 的成員：`write`
- Carol：`read`

如果把 `A/B` 設為 restricted，Bob 在 `A` 上的許可權不會對 `A/B` 及其後代生效，但儲存的 inherited 不會被刪除。刪除 restricted 後，Bob 會立即恢復從 `A` 繼承的許可權。

## 預設行為與 `acl_mode`

帳號級 `acl.enabled` 預設關閉。關閉時，共享資源繼續使用原有 URI namespace
可見性和寫入規則，不執行 ACL 鑑權和過濾。索引仍按統一繼承規則儲存 ACL，開關不影響已存許可權。

開啟後，根目錄固定授予 `user:* = manage`，當前 account 內所有成員都可以管理
持續繼承根許可權的共享內容。未傳 `acl` 時，新節點的直接授權為空，只繼承父目錄的有效許可權，
不會因為建立了內容而獲得額外許可權。`add-resource` 的根節點和內部節點遵循相同規則。
已有且未設定 ACL 的共享內容按預設繼承計算，不進行歷史資料遷移；重新關閉後，
已有 ACL 不參與訪問判斷。重新向量化或未顯式傳入 ACL 的覆蓋寫不改變直接 ACL。建立時可通過 [acl](../api/12-acl.md) 設定目標節點許可權。

`acl_mode` 表示當前資源如何使用 ACL，與帳號總開關 `acl.enabled` 不是一回事：

- `none`：尚未寫入 ACL 欄位；開啟 ACL 後，共享節點按預設繼承規則計算許可權。
- `inherit`：使用直接許可權和父目錄傳下來的許可權。
- `restricted`：只使用直接許可權，但仍儲存並更新父目錄傳下來的許可權。

有 `manage` 許可權的使用者可以切換 `inherit` / `restricted`，不能直接設定 `none` 繞過父目錄許可權。退出 restricted 後恢復繼承父目錄許可權；父鏈未被其他 restricted 截斷時，全員恢復 `manage`。restricted 節點即使沒有直接許可權也不會變公開，其沒有單獨授權的後代同樣不可訪問；帳號管理員仍有隱式管理權。

## 文件操作

所有檔案介面使用同一套許可權判斷：

| 操作 | 所需能力 |
|------|----------|
| read、stat、list、tree、find、search、grep、glob | read |
| write、create、mkdir、set tags | write |
| 刪除或移動檔案 | write |
| 刪除或移動目錄 | 目錄及完整子樹的 manage |
| 管理 ACL | manage |
| move 目標父目錄 | write |

服務端會先 canonicalize URI，再在同一個鑑權入口中依次執行 account/owner/actor peer 等硬邊界、開啟時的有效 ACL 或關閉時的原有 namespace 規則，以及寫入和刪除的 namespace 防護。

帳號開啟 `acl.enabled` 時，普通共享節點繼承根目錄的全員 `manage`，成員可據此
修改節點 ACL。restricted 下的建立者只有父目錄授予的許可權，不會自動獲得 `manage`。

目錄上的 ACL 授權會被所有後代繼承。`list`、`tree` 和批次結果仍逐個檢查有效 ACL，因為預設開放的目錄下可能存在獨立的 restricted 邊界。

共享區內部移動時，節點自己的 direct ACL 和 restricted 狀態隨節點移動，inherited 按新父節點重新計算。個人資源移入共享區時不攜帶 ACL，只繼承目標目錄許可權；共享資源移回個人區時清空 ACL。

遞迴修改 tags、刪除或移動目錄會先校驗完整目標子樹。任一節點缺少所需能力，或子樹掃描不完整，操作都會整體中止。

目錄 `stat` 的 `count` 使用相同的路徑和 ACL 標量過濾，表示當前使用者可見的 context 數量。

## 檢索過濾

ACL 只儲存在 context collection。每條 context 記錄維護當前節點和繼承許可權兩組原生標量欄位：

```text
acl_mode
acl_direct_grants
acl_inherited_grants
```

`acl_direct_grants` 是當前節點直接 ACL，`acl_inherited_grants` 是父節點當前有效 ACL，`acl_mode` 決定 inherited 是否參與當前節點的有效許可權。每個 principal 只儲存最高 level，編碼為 `{mask}:{principal}`：`1` 表示 `read`、`3` 表示 `write`、`7` 表示 `manage`。不維護獨立 ACL collection。

ACL 隨索引更新，允許同一 URI 的不同索引記錄短暫保留不同版本。讀取採用索引返回的一份 ACL 快照，不合並不同版本的授權，也不因副本暫時不一致阻斷處理。許可權變更按索引更新進度生效，不保證強一致。

請求的可用 principal 為 `user:{ctx.user_id}`、`user:*`，以及 `ctx.group_ids` 中每個 ID 對應的 `group:{group_id}`。檢索在共享區內用 `acl_mode IN [inherit, restricted]` 判斷受控資源，再匹配各 principal 的 `1`、`3`、`7` grant token：inherit 匹配 direct 或 inherited，restricted 只匹配 direct。未寫入 ACL 欄位（欄位缺失、為 `null` 或 `none`）的共享記錄按根目錄預設全員授權參與檢索。已儲存的 inherit 節點必須匹配自己的直接或繼承授權，不能因為模式是 inherit 就放行全員。個人資源始終按 URI owner 隔離。

檢索 target URI 只是搜尋範圍，不要求呼叫者能夠讀取 target 節點本身。使用者即使不能讀取中間目錄，也可以檢索到深層單獨授權給自己的檔案。

帳號開啟 `acl.enabled` 時，共享區 context 寫入會保留同 URI 已有 direct ACL；
新節點的直接授權為空，從父節點生成 inherited ACL；沒有受限邊界時，繼承欄位
包含 `7:user:*`。建立者身份不參與授權計算。重新向量化和普通覆蓋寫不會把受控記錄
恢復為預設可見，也不能通過普通 context 欄位直接改 ACL。帳號關閉該開關時，檢索
只使用原有 account 和 URI scope 過濾，不使用這些 ACL 欄位。

## 示例

以下假定 `project-a` 已設為 restricted，且操作者擁有該節點的 `manage`。
將目錄授權給 Bob 只讀：

```bash
ov acl grant viking://resources/project-a --principal user:bob --level read
```

Bob 可以讀取和檢索該目錄的後代，但不能寫入或刪除。升級為 `write`：

```bash
ov acl grant viking://resources/project-a --principal user:bob --level write
```

刪除 Bob 在當前節點上的直接授權：

```bash
ov acl revoke viking://resources/project-a --principal user:bob
```

如果 Bob 仍被祖先目錄授權，該繼承許可權繼續有效。

只使用當前節點直接授權，同時保留並繼續更新繼承欄位：

```bash
ov acl set viking://resources/project-a --acl-mode restricted
```

## 相關文件

- [ACL API](../api/12-acl.md) - HTTP、SDK 和 CLI 接口
- [多租戶](./11-multi-tenant.md) - account、user 和角色邊界
- [Viking URI](./04-viking-uri.md) - URI namespace
- [檢索](./07-retrieval.md) - 分層檢索流程
