# 路徑鎖與崩潰恢復

OpenViking 通過**路徑鎖**和**持久化佇列恢復**兩種機制保護核心寫操作（`rm`、`mv`、`add_resource`、`session.commit`）的一致性，協調併發寫入，並在程序重啟後繼續處理已入隊的會話任務。路徑鎖和佇列恢復不構成跨 VikingFS、VectorDB、QueueManager 的原子事務。

## 設計哲學

OpenViking 是上下文資料庫，FS 是源資料，VectorDB 是派生索引。索引通常可以從保留的源資料重建；恢復丟失的源資料則依賴備份。因此：

> **寧可搜不到，不要搜到壞結果。**

## 設計原則

1. **寫互斥**：參與鎖協議的不同 owner 不能同時取得衝突路徑的鎖
2. **預設生效**：受保護的寫操作預設加鎖；普通讀取和底層 mkdir 不自動加鎖
3. **鎖只保護併發**：執行時申請和釋放 lease，不提供跨儲存的 undo/journal/commit 語義
4. **持久化任務恢復**：`SessionCommit` 佇列恢復會話 Phase 2；資源派生處理由相應的持久化佇列恢復
5. **鎖與佇列配合**：業務路徑可在持鎖時入隊並交接 lease；重試和去重取決於具體任務協議，不能把所有 enqueue 視為天然冪等

## 架構

<PathLockDiagram />

## 兩個核心元件

### 元件 1：路徑鎖系統

執行時鎖由 Rust RAGFS 的 `PathLockManager` 和 Provider 管理。Python 服務通過 binding 申請、續用、交接和釋放 lease。後文的 `LockContext` 示例僅說明生命週期，不是當前 Python SDK 或執行時類介面。

- **範圍**：EXACT 保護路徑本身，TREE 保護路徑及其子樹。
- **Provider**：預設 filesystem 儲存鎖檔案；cache 用 Redis 原子檢查和寫入 token；memory 只在當前程序內協調。
- **lease**：記錄 owner、覆蓋路徑、token 位置和續期狀態。後臺任務可以接收顯式交接的 lease。
- **失敗處理**：釋放前校驗 owner，過期鎖由後續獲取時的 stale 檢查清理；鎖釋放不會撤銷已寫入的資料。

### 元件 2：持久化 `SessionCommit` 佇列（崩潰恢復）

佇列名為 `SessionCommit`，任務型別為 `session_commit`。

`session.commit` 的 Phase 2 不再使用獨立 RedoLog。Phase 1 會先把 archive 後設資料持久化，再把
`SessionCommitMsg` 寫入持久化佇列；程序重啟後，QueueManager 會繼續消費遺留的 `session_commit`
任務並恢復 Phase 2。

恢復使用已儲存的 archive 和處理狀態。記憶提取包含模型呼叫，不能假設重新執行會生成逐字相同的內容。

## 一致性問題與解決方案

### rm(uri)

| 問題 | 方案 |
|------|------|
| 先刪檔案再刪索引 -> 檔案已刪但索引殘留 -> 搜尋返回不存在的檔案 | **調換順序**：先刪索引再刪檔案。索引刪除失敗 -> 原始檔仍在，重試可完成可能只執行了一部分的索引清理 |

**加鎖策略**（根據目標型別區分）：
- 刪除**目錄**：`lock_mode="tree"`，鎖目錄自身及其整棵子樹
- 刪除**檔案**：`lock_mode="exact"`，鎖檔案路徑本身

操作流程：

```
1. 檢查目標是目錄還是檔案，選擇鎖模式
2. 獲取鎖
3. 刪除 VectorDB 索引 -> 搜尋立刻不可見
4. 刪除 FS 檔案
5. 釋放鎖
```

索引 URI 收集或 VectorDB 刪除失敗 -> 直接拋異常，鎖自動釋放，原始檔仍在。多記錄刪除在部分
後端可能已經執行了一部分，但重試可以安全補完清理。FS 刪除失敗 -> VectorDB 已刪但檔案還在，
重試同樣安全。

### mv(old_uri, new_uri)

| 問題 | 方案 |
|------|------|
| 檔案移到新路徑但索引指向舊路徑 -> 搜尋返回舊路徑（不存在） | 先 copy 再更新索引，失敗時清理副本 |

**加鎖策略**（由公開的 `VikingFS.mv` 實現申請）：
- 移動**目錄**：源路徑加 TreeLock，目標路徑加 TreeLock
- 移動**檔案**：源路徑和目標路徑各加 EXACT 鎖

操作流程：

```
1. 檢查源是目錄還是檔案，確定 src_is_dir
2. 獲取 mv 鎖（內部根據 src_is_dir 選擇 TreeLock 或 ExactPathLock）
3. Copy 到新位置（源還在，安全）
4. 如果是目錄，刪除副本中被 cp 帶過去的鎖檔案
5. 更新 VectorDB 中的 URI
   - 失敗 -> 嘗試清理副本；索引或清理可能部分完成，需檢查後再重試
6. 刪除源
7. 釋放鎖
```

### add_resource

| 問題 | 方案 |
|------|------|
| 檔案從臨時目錄移到正式目錄後崩潰 -> 檔案存在但永遠搜不到 | 先提交內容計劃，再由持久化佇列完成派生索引 |
| 資源已落盤但語義處理/向量化還在跑時被 rm 刪除 -> 處理白跑 | 生命週期 TreeLock，從落盤持續到處理完成 |

**首次新增和增量更新**使用同一條計劃提交路徑：

```
1. 獲取 final_uri 的資源鎖。
2. 持鎖構建 R/N/F/V 快照：
   - R：歸一化後的請求意圖
   - N：解析產物清單
   - F：當前正式資源樹
   - V：當前向量記錄；build_index=false 時跳過
3. 編譯 ContextUpdatePlan。
4. 同步把計劃中的內容動作提交到 final_uri。
5. 清理 parser artifact。
6. 入隊直接索引動作；需要語義處理時，再入隊攜帶剩餘 SemanticPlan 的 SemanticMsg。
7. 將資源鎖交接給語義處理；沒有語義任務時直接釋放。
```

因此正式內容樹會先於 semantic 和 embedding 工作更新。內容提交成功後，
派生摘要和向量可能短暫落後，並由佇列任務補齊；佇列不再負責把 parser
臨時樹複製到正式樹。

此期間 `rm` 嘗試獲取同路徑 TreeLock 會失敗，丟擲 `ResourceBusyError`。

自動命名由資源層處理，不屬於鎖服務：`ResourceProcessor` 先用 `exists(candidate_uri)`
判斷候選目錄是否已佔用；已存在則嘗試 `_1`、`_2` 字尾。候選目錄不存在時才嘗試
獲取該目錄的 `TreeLock`，且不等待；如果同名正在被併發請求處理，就直接嘗試下一個字尾。

**服務重啟恢復**：`SemanticMsg` 和 `SemanticPlan` 儲存在持久化 QueueFS 後端中。語義處理通過 `lock_handoff` 嘗試接管 lease；對可恢復的過期交接，按 `covered_paths` 重新申請覆蓋範圍後繼續。鎖衝突或不可恢復的交接錯誤仍會使處理失敗，需檢查任務狀態。

### 派生語義檔案（.abstract.md / .overview.md）

`.abstract.md` 和 `.overview.md` 是後臺生成的派生檔案，不作為普通使用者原始檔寫入。它們的併發保護分兩層：

| 問題 | 方案 |
|------|------|
| 多個後臺任務同時重新整理同一個目錄摘要，舊結果覆蓋新結果 | 相同 dirty key 使用 `coalesce_version`，只有最新版本允許寫回 |
| 最新任務寫回派生檔案時與另一個寫回交錯 | 寫 `.abstract.md`、`.overview.md` 前獲取各自的 ExactPathLock |

例子：同一目錄下併發寫入 `a.md`、`b.md`、`c.md` 時，前臺寫入分別持有 `ExactPathLock(a.md)`、`ExactPathLock(b.md)`、`ExactPathLock(c.md)`，互不阻塞。後臺可能產生多個 `docs/` 摘要重新整理任務，但只有最新 version 能寫回 `docs/.overview.md` 和 `docs/.abstract.md`；舊任務在寫回前發現自己過期後直接丟棄結果。

memory 目錄摘要使用同一規則。比如併發更新：

```text
viking://user/default/memories/preferences/theme.md
viking://user/default/memories/preferences/editor.md
```

兩個檔案寫入各自持有 ExactPathLock；`preferences/.overview.md` 和 `preferences/.abstract.md` 的後臺重新整理不再持有長時間 TreeLock，而是通過 `coalesce_version` 淘汰舊任務，並在最終寫派生檔案時短暫獲取 ExactPathLock。

### session.commit()

Phase 1 使用會話根目錄的 EXACT 鎖劃定提交邊界。模型呼叫耗時不可控，因此摘要生成和記憶提取放在後臺，不在這個邊界鎖內等待：

```text
Phase 1：持鎖準備併發布歸檔
  1. 讀取訊息與提交策略，分配歸檔編號，劃分歸檔和保留訊息
  2. 寫歸檔訊息及後設資料
  3. 入隊 SessionCommitMsg 並建立 task
  4. 寫當前保留訊息、會話後設資料和 phase1 ready 標記
  5. 釋放鎖，返回 task_id（無可歸檔內容時 skipped）

Phase 2：後臺處理已釋出歸檔
  1. 讀取歸檔訊息並生成摘要
  2. 提取、更新記憶並安排派生處理
  3. 寫 memory_diff.json 和完成標記
```

**崩潰恢復分析**：

| 時間點 | 應檢查什麼 |
| --- | --- |
| Phase 1 尚未釋出 | 歸檔準備可能只完成一部分；檢查歸檔狀態和當前訊息，不把目錄存在當作提交成功 |
| 已入隊但 ready 尚未寫入 | 後臺處理需要核對 Phase 1 狀態；錯誤路徑會嘗試記錄失敗標記，不能僅憑 task 存在判斷成功 |
| Phase 2 提取或寫入中途 | 持久化佇列可恢復處理，但模型重試不保證生成相同正文 |
| Phase 2 完成 | 核對 task 最終狀態、歸檔完成標記和實際記憶變更 |

## LockContext

以下虛擬碼說明申請、使用、釋放鎖的順序。當前執行時使用 RAGFS lease API，不能直接從 Python SDK 匯入 `LockContext`：

```python
# Conceptual example: production path locks are acquired inside the Rust ragfs layer.

# Exact 鎖（寫操作、語義處理）
async with LockContext(lock_manager, [path], lock_mode="exact"):
    # 執行操作...
    pass

# Tree 鎖（刪除目錄、目錄生命週期保護）
async with LockContext(lock_manager, [path], lock_mode="tree"):
    # 執行操作...
    pass

# MV 鎖（移動操作）
async with LockContext(lock_manager, [src], lock_mode="mv", mv_dst_path=dst):
    # 執行操作...
    pass
```

**鎖模式**：

| lock_mode | 用途 | 行為 |
|-----------|------|------|
| `exact` | 檔案寫入、單檔案刪除、派生檔案寫回 | 鎖定指定路徑；與同路徑鎖和祖先目錄 TreeLock 衝突 |
| `tree` | 刪除目錄、資源生命週期、目錄級保護 | 鎖定子樹根節點；與同路徑鎖、後代鎖和祖先 TreeLock 衝突 |
| `mv` | 移動操作 | 目錄移動：源路徑 TreeLock + 目標路徑 TreeLock；檔案移動：源路徑和目標路徑均 ExactPathLock（通過 `src_is_dir` 控制） |

**異常處理**：業務呼叫通過 `finally` 釋放或交接 lease。鎖衝突會返回相應 busy/鎖獲取錯誤；釋放失敗或程序退出後的 token 依賴過期清理。

## 鎖型別（EXACT vs TREE）

鎖機制使用兩種鎖型別來處理不同的衝突場景：

| | 同路徑 EXACT | 同路徑 TREE | 後代 EXACT | 祖先 TREE |
|---|---|---|---|---|
| **EXACT** | 衝突 | 衝突 | — | 衝突 |
| **TREE** | 衝突 | 衝突 | 衝突 | 衝突 |

- **EXACT (E)**：鎖定一個具體路徑本身。檔案、目錄名、尚未建立的目標路徑都可以使用；若祖先目錄持有 TreeLock 則阻塞。
- **TREE (T)**：用於刪除目錄、移動目錄、資源生命週期保護等。邏輯上覆蓋整棵子樹，但只為根路徑儲存一個 Provider token。衝突檢查覆蓋 Provider scope 內的後代和持有 Tree 鎖的祖先。Filesystem Provider 可能為了寫鎖檔案而建立尚不存在的目標目錄。

### 路徑範圍與目標型別

Exact 和 Tree 表達操作範圍，檔案、目錄或缺失路徑表達目標的當前狀態，兩者獨立。鎖保護路徑名字，目標不存在也可以申請鎖。

鎖路徑必須是絕對路徑。Manager 在獲取鎖或檢查租約覆蓋範圍前，對空路徑、
相對路徑、重複 `/`、`.` 或 `..` 路徑段及 NUL 返回 `InvalidRequest`。
非根路徑末尾的單個 `/` 會被移除。Redis 和 SQLite 的 token 操作要求路徑
已完成這一規範化；Redis Lua 批次獲取也會在修改 token 前校驗全部請求。
應使用 `/local/account-a/file`，避免 `/local/account-a/./file`、
`/local/account-a//file` 等別名。

以下衝突關係限定為不同 owner、同一 Provider scope 內的請求：

| 已持有 | 新請求 | 衝突 |
| --- | --- | --- |
| Exact(`/docs/a.md`) | Exact 或 Tree(`/docs/a.md`) | 是 |
| Exact(`/docs`) | Exact(`/docs/a.md`) | 否 |
| Tree(`/docs`) | Exact 或 Tree(`/docs/a.md`) | 是 |
| Exact(`/docs/a.md`) | Tree(`/docs`) | 是 |
| Tree(`/docs/a.md`) | Exact(`/docs/b.md`) | 否 |

`Tree(/docs/a.md)` 不會擴大為 `Tree(/docs)`。反過來，目錄自身的 Exact 也不能保護子樹，遞迴刪除需要 Tree。

鎖只協調參與協議的操作。底層 `PathLockWrappedFS` 對 create、write、truncate、非遞迴 remove 使用 Exact，對 remove_all 使用 Tree；檔案 rename 鎖源和目標的 Exact，底層目錄 rename 鎖源 Tree 和目標 Exact；公開目錄 `mv` 額外保護源、目標兩棵子樹。read、stat、列目錄和 mkdir 直接轉發，上層可另行持鎖。繞過協議的 I/O 不會被作業系統自動阻斷。

## 鎖機制

### Filesystem Provider 鎖協議

鎖型別由呼叫者選擇。Filesystem Provider 對所有目標統一使用父目錄 sidecar：

| 目標狀態 | Exact token | Tree token |
| --- | --- | --- |
| 現存檔案 `/docs/a` | `/docs/.exact.ovlock.a.<hash>`，內容為 E | 同一 sidecar，內容為 T |
| 現存目錄 `/docs/a` | `/docs/.exact.ovlock.a.<hash>`，內容為 E | 同一 sidecar，內容為 T |
| 缺失路徑 `/docs/a` | `/docs/.exact.ovlock.a.<hash>`，內容為 E | 同一 sidecar，內容為 T |

sidecar 位於目標旁邊，但只代表該目標，不會鎖住整個父目錄。遞迴刪除目標時不會刪除位於父目錄中的 token，因此鎖的互斥保護會持續到 lease 正式釋放。`<hash>` 來自完整後端路徑的 SHA-1 字首，與業務檔案內容無關。

`.exact.ovlock.*` 根據實際鎖型別儲存 E 或 T。為相容升級前遺留 token，衝突檢測仍讀取目標內部的 `.path.ovlock`，但新鎖不再寫入該位置。檔名是儲存協議的一部分，不能單憑名字判斷邏輯鎖型別。token 內容為：

```text
{owner_id}:{time_ns}:{lock_type}
```

`lock_type` 為 `E` 或 `T`。該歸屬 token 用於競爭檢查、續期和條件釋放，不代表所有業務寫入都有儲存端 fencing 校驗。

lease 將邏輯範圍 `covered_paths` 與 token 位置 `lock_paths` 分開記錄。Owned lease 控制續期、釋放和交接；Borrowed lease 僅提供已有鎖的覆蓋證明，不能釋放外層鎖。

#### 協議遷移與釋出

新版本對新 sidecar 和舊 `.path.ovlock` 執行雙讀，但只向新 sidecar 寫入 token。升級前已存在的 lease 不做原地遷移：續期、釋放和交接繼續使用 lease 中記錄的舊 `lock_paths`，直到舊 token 正常釋放或過期。

舊版本不會檢查祖先路徑的新 sidecar，因此 Filesystem Provider 不能讓新舊版本在同一後端上同時處理寫請求。當前版本採用協調切換：

1. 停止新的寫請求，等待活躍 lease 和待交接任務排空，然後停止所有舊例項。
2. 全量啟動新版本例項，確認舊 token 已釋放或可按過期規則回收，再恢復寫流量。

如果部署必須保持零停機滾動升級，需要拆成兩個可獨立釋出的協議階段：先發布“新舊雙讀、仍寫舊 token”的相容版本；全部例項升級後，再統一切換為“新舊雙讀、只寫新 sidecar”。兩個階段之間不得存在舊例項讀取新 sidecar 的視窗。

### Cache Provider 鎖協議

Cache Provider 將相同 token 格式存入 Redis HASH field，並通過 Lua
原子完成整批衝突檢查和寫入：

```text
field = logical_path
value = owner_id:time_ns:lock_type
```

HASH key 按路徑 scope 隔離：

```text
{service_name}:ov:pathlock:global:tokens
{service_name}:ov:pathlock:scope:_system:tokens
{service_name}:ov:pathlock:scope:account:{account}:tokens
```

所有 key 都使用 `{service_name}` 作為 Redis Cluster hash tag。Exact 獲取使用
`HMGET` 讀取目標和祖先；Tree 獲取只對所屬 scope 的 HASH 執行
`HGETALL`。`/` 和 `/local` 的 Tree 鎖會返回 `InvalidRequest`，因為它們的
子樹跨越 account 和 `_system` HASH。Tree 根路徑應使用 `/local/<account>`、
`/local/_system` 或其後代。`/` 和 `/local` 的 Exact 鎖仍然支援，只保護
對應路徑本身。跨 scope batch 會被拒絕。

### Filesystem 獲取鎖流程（EXACT 模式）

```
迴圈直到超時（輪詢間隔：200ms）：
    1. 檢查目標路徑是否被其他操作鎖定
       - 陳舊鎖？ -> 移除後重試
       - 活躍鎖？ -> 等待
    2. 檢查所有祖先目錄是否有 TREE 鎖
       - 陳舊鎖？ -> 移除後重試
       - 活躍鎖？ -> 等待
    3. 確保鎖檔案所在父目錄存在；如果不存在則建立目錄
    4. 寫入 EXACT (E) 鎖檔案
    5. TOCTOU 雙重檢查：重新掃描目標路徑和祖先目錄的 TREE 鎖
       - 發現衝突：比較 (timestamp, handle_id)
       - 後到者（更大的 timestamp/handle_id）主動讓步（刪除自己的鎖），防止活鎖
       - 等待後重試
    6. 驗證鎖檔案歸屬（fencing token 匹配）
    7. 成功

超時（預設 0 = 不等待）丟擲 LockAcquisitionError
```

### Filesystem 獲取鎖流程（TREE 模式）

```
迴圈直到超時（輪詢間隔：200ms）：
    1. 檢查目標路徑是否被其他操作鎖定
       - 陳舊鎖？ -> 移除後重試
       - 活躍鎖？ -> 等待
    2. 檢查所有祖先目錄是否有 TREE 鎖
       - 陳舊鎖？ -> 移除後重試
       - 活躍鎖？ -> 等待
    3. 掃描所有後代目錄，檢查是否有其他操作持有的鎖
       - 目標目錄不存在？ -> 視為無後代鎖
       - 陳舊鎖？ -> 移除後重試
       - 活躍鎖？ -> 等待
    4. 確保 Resolver 選定的 sidecar 父目錄存在；不會建立缺失目標本身
    5. 在父目錄 sidecar 寫入 TREE (T) token
    6. TOCTOU 雙重檢查：重新掃描後代目錄和祖先目錄
       - 發現衝突：比較 (timestamp, handle_id)
       - 後到者（更大的 timestamp/handle_id）主動讓步（刪除自己的鎖），防止活鎖
       - 等待後重試
    7. 驗證鎖檔案歸屬（fencing token 匹配）
    8. 成功

超時（預設 0 = 不等待）丟擲 LockAcquisitionError
```

### 缺失目錄建立規則

鎖系統允許為了放置 sidecar 而建立缺失的父目錄鏈，但不會建立被鎖目標本身。建立前必須先檢查衝突：

```
1. 發現祖先 TreeLock / 同路徑鎖 / 後代鎖衝突 -> 不建立目錄，直接失敗或等待
2. 當前無衝突 -> 可以建立 sidecar 的父目錄並寫鎖
3. 寫鎖後再次檢查時發現新衝突 -> 刪除自己的鎖並失敗或重試
4. 第 3 步不會回滾剛建立的空目錄
```

例子：

```text
請求 A 正在刪除 viking://resources/books
=> A 持有 TreeLock(/resources/books)

請求 B 想新增 viking://resources/books/java-guide
=> B 在建立 java-guide 目錄前發現祖先 TreeLock
=> B 不建立目錄，返回 busy
```

如果兩個請求同時建立 `java-guide`，兩邊都可能先看到“當前無衝突”，但最終只有
fencing token 校驗通過的一方成功持有 `TreeLock(java-guide)`；失敗方會刪除自己的鎖。

獲取失敗的回滾和正常釋放只清理 token，不保證刪除為存放 sidecar 建立的父目錄鏈。Snapshot 對缺失目標採用單獨的策略，見 [快照的範圍與併發](../guides/15-snapshot.md#提交範圍與併發)。

### 鎖過期清理

**自動續期**：Rust PathLockManager 每隔 `lock_expire / 3` 重新整理活躍 lease；預設過期時間為 30 秒，不是業務操作的最長執行時間。程序退出後續期停止。

**陳舊鎖檢測**：PathLockEngine 檢查歸屬 token 中的時間戳。超過 `lock_expire`（預設 30s）的鎖被視為陳舊鎖，在加鎖過程中自動移除。

**失鎖後的授權失效**：手動和後臺續租使用相同規則。token 不存在或 owner 不匹配時，同 owner 下共享實際 token 路徑（`lock_paths`）的所有本地 lease 立即整份失效，包括待交接的 lease。Tree 祖先和 Exact 後代使用不同 token，不會因邏輯覆蓋關係連帶失效。

網路等不確定錯誤允許短暫重試，但每個 token 距離最近一次成功確認達到 `0.8 × lock_expire`（預設 24 秒）時撤銷授權。使用單調時鐘分別記錄各 token 的確認時間；部分續租成功、重入和本地交接/接管不會延長失敗 token 的期限。寫入授權檢查也會檢查期限，無需等待下次心跳。失效 lease 不能再授權後續受保護寫入、續租、複用 owner 或交接/接管，且不會恢復有效。

**程序內清理**：失效 lease 保留釋放能力和本地引用，後臺重試帶 owner 校驗的清理。token 已不存在或已被其他 owner 接管均視為清理完成，不會刪除新 owner 的 token；仍被其他有效本地 lease 引用的 token 也不會被刪除。從首次失效起超過六個心跳間隔（`2 × lock_expire`，預設 60 秒），即使 Provider 持續不可用也記錄剩餘路徑並移除本地 entry，遺留的遠端 token 依賴過期清理。重試不會延長該視窗。

**失效診斷**：manager 在清理期間保留首次失效的時間與原因。`pathlock lease invalidated` 日誌包含 `reason`、`lease_ref`、`owner_id` 和 `affected_paths`。`TokenLost` 表示必要 token 缺失或歸屬不符，應檢查 token 過期、刪除和接管情況；`ConfirmationDeadlineExceeded` 表示安全期限內未能確認歸屬，應檢查 Provider 健康、網路延遲和續租排程，對應 token 日誌還包含 `since_last_confirmation_ms` 和 `failures`；`ReleaseFailed` 表示釋放或降級錯誤導致撤銷授權並進入清理重試，釋放日誌會記錄具體錯誤。後續響應和清理失敗不會覆蓋首次原因或重置時間，清理視窗耗盡的日誌也會保留該原因。

上述檢查在發現失鎖或達到期限後拒絕後續操作；不會中斷已經通過授權檢查的寫入，也不提供儲存側 fencing。

**孤兒鎖**：程序崩潰後遺留的 Provider token，在後續 acquire 檢查同一路徑或 scope 時通過 stale lock 檢測自動移除。

## 崩潰恢復

服務啟動後，QueueManager 會繼續消費持久化的 `session_commit` 任務：

| 場景 | 恢復方式 |
|------|---------|
| session_memory 提取中途崩潰 | 從 archive 恢復 Phase 2 並繼續消費 `session_commit` 任務 |
| 鎖持有期間崩潰 | Provider token 保留，後續匹配的 acquire 通過 stale 檢測自動清理（預設 30s 過期）|
| enqueue 後 worker 處理前崩潰 | QueueFS SQLite 持久化，worker 重啟後自動拉取 |
| 孤兒索引 | `rm` 對不存在的目標也會嘗試清理相關向量記錄 |

### 防線總結

| 異常場景 | 防線 | 恢復時機 |
|---------|------|---------|
| 操作中途崩潰 | 鎖自動過期 + stale 檢測 | 下次獲取同路徑鎖時 |
| add_resource 語義處理中途崩潰 | 生命週期鎖過期 + SemanticProcessor 重啟時重新獲取 | worker 重啟後 |
| session.commit Phase 2 崩潰 | 持久化 `SessionCommit` 佇列 + 重試消費 | 重啟時 |
| enqueue 後 worker 處理前崩潰 | QueueFS SQLite 持久化 | worker 重啟後 |
| 孤兒索引 | `rm` 對不存在的目標也會嘗試清理相關向量記錄 | 呼叫 `rm` 時 |

## 配置

路徑鎖預設啟用，並使用 `filesystem` Provider。多程序通過 Redis 協調時，
設定 `storage.agfs.pathlock.provider=cache`。Cache PathLock 要求配置頂層
Redis Cache Provider，並使用頂層 `service_name` 作為 Redis namespace。
執行時等待超時固定為 `0.0` 秒。`storage.transaction` 僅保留為相容舊配置：`lock_timeout`
已廢棄且會被忽略，`lock_expire` 會在未顯式配置新欄位時自動對映，
`redo_recovery_enabled` 已廢棄且會被忽略。

推薦寫法：

```json
{
  "storage": {
    "agfs": {
      "pathlock": {
        "provider": "filesystem",
        "lock_expire_secs": 30.0
      }
    }
  }
}
```

Redis 配置：

```json
{
  "service_name": "production",
  "cache": {
    "provider": "redis",
    "params": {
      "mode": "standalone",
      "endpoints": ["redis://127.0.0.1:6379"]
    }
  },
  "storage": {
    "agfs": {
      "pathlock": {
        "provider": "cache",
        "lock_expire_secs": 30.0
      }
    }
  }
}
```

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `provider` | str | `filesystem`、`memory`、`sqlite` 或 `cache` | `filesystem` |
| `sqlite_path` | str / null | 使用 `sqlite` 時可覆蓋本地資料庫絕對路徑；見 [SQLite 配置](../configuration/01-server.md#storage) | 使用 `sqlite` 時為 `{storage.workspace}/_system/pathlock/pathlock.db` |
| `lock_expire_secs` | float | 未重新整理的鎖進入 stale 狀態前的秒數 | `30.0` |

跨容器或主機共享 EFS 的副本應使用 `provider="cache"`，連線共享 Redis。
SQLite 僅支援同機共享同一個本地磁碟資料庫檔案，不支援 EFS/NFS/SMB
或各容器獨立的本地資料庫。參見[部署限制與 Provider 選擇](../configuration/01-server.md#storage)。

相容舊寫法：

```json
{
  "storage": {
    "transaction": {
      "lock_expire": 30.0
    }
  }
}
```

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `lock_timeout` | float | 已廢棄且忽略。執行時等待超時固定為 `0.0`。 | `0.0` |
| `lock_expire` | float | 已廢棄。改用 `storage.agfs.pathlock.lock_expire_secs`。 | `30.0` |

### QueueFS 持久化

重啟恢復要求佇列內容已持久化。QueueFS 預設使用 SQLite；使用 cache 後端時，永續性取決於所配置的 Provider。memory 後端不保留程序退出後的任務。

### 單例項路徑鎖 Provider 切換：filesystem → Redis

這裡切換的是 **路徑鎖的儲存與協調後端**：從 filesystem Provider 使用的
`.ovlock` 鎖檔案，切換為 cache Provider 使用的 Redis 鎖記錄。
業務檔案仍儲存在原有檔案儲存中，QueueFS 仍使用原有持久化佇列後端
（例如 SQLite）；業務資料和佇列訊息無需遷入 Redis。

此流程僅支援 **單例項、停機切換**。按以下步驟操作：

1. 暫停新請求和任務提交，禁用可能自動拉起舊例項的自動重啟或排程策略，
   保留原有檔案儲存和持久化佇列。
2. 停止舊服務及其所有佇列消費程序。在程序管理器或部署平臺中核對舊例項的
   PID / 容器已全部退出，且沒有殘留子程序、獨立 worker 或其他訪問同一儲存的
   filesystem 路徑鎖寫入者；確認舊例項的鎖心跳續租任務也已停止。
   **完成此檢查前，不得啟動使用 Redis 路徑鎖的新例項。**
3. 將 `storage.agfs.pathlock.provider` 從 `filesystem` 改為 `cache`，
   並將該 cache Provider 配置為使用 Redis。
4. 啟動一個新例項，檢查積壓任務從原佇列恢復、在 Redis 中取得新路徑鎖並正常消費，
   再恢復請求入口和任務提交。

`handoff` 會保留舊程序內的 lease 並繼續心跳續租，因此停止請求入口或關閉監聽埠
不足以證明舊寫入者已停止；必須確認上述程序全部退出。程序退出後，其記憶體中的
lease registry 和心跳任務隨之終止，磁碟上仍可能殘留 `.ovlock` token。
無需排空佇列、刪除這些鎖檔案或等待舊租約過期。

filesystem 與 Redis 是相互獨立的鎖協調域，Redis 的 acquire **不會檢查或阻擋
舊 filesystem token**。如果舊程序仍在執行，同一路徑可能同時被兩套後端授予
不同 owner，兩個程序也可能同時寫業務檔案；等待舊 token 過期不能替代退出檢查。

新 handoff 包含 `handle_mode`；舊訊息缺少該欄位時仍可恢復。
消費者遇到 Provider 變化或舊 token 不可用時，按完整邏輯路徑和 Exact/Tree
型別重新加鎖，獲得新 owner 後才執行任務。優先使用 `covered_paths`；
舊 `.path.ovlock` 可反解 Tree 路徑，無法反解的 Exact 檔名使用任務自身的
完整路徑請求。不會只恢復混合批次中的部分路徑。
重新加鎖遇到衝突或服務錯誤時保留任務重試；非法覆蓋、失效引用和重複 adopt
不會觸發重新加鎖。舊 `.ovlock` 檔案無需掃描或複製到 Redis。

恢復必須攜帶有效帳號上下文；缺少上下文或覆蓋路徑不屬於該帳號時拒絕恢復。
語義任務優先保留 `covered_paths` 中的 Exact/Tree 型別；歷史訊息缺少覆蓋型別、
無法確定原始粒度時，按任務路徑保守獲取 Tree 鎖並記錄 warning。
這可能將原來的 Exact 鎖擴大為 Tree 鎖，降低恢復期間的併發度。

### 恢復阻塞的重試與告警

QueueFS 沒有全域最大重試次數或死信佇列。AddResource、Reindex、ContentWrite
和 Semantic 消費者對 `HandoffRecoveryBlocked` 的每條投遞鏈最多重試 8 次
（首次嘗試之外），通過替代訊息中的 `lock_handoff_retry` 持久化計數。
如果替代訊息已入隊、原訊息尚未 ACK 時程序崩潰，恢復後兩條訊息可能形成
不同的投遞鏈，各自沿用訊息中的計數，因此這不是同一 work 的全域重試上限。
每次重試前等待
`min(0.5 × 2^retry, 30)` 秒；退避期間仍佔用當前消費者槽位。
等待取消或重新入隊失敗時，不 ACK 原訊息；達到上限時結束該 work 並記錄失敗，
關聯任務通過任務跟蹤機制進入 FAILED，可查詢失敗原因。失敗不會自動進入死信佇列。

每次阻塞記錄 warning，達到上限記錄 error，並匯出
`openviking_pathlock_recovery_blocked_total{queue, outcome}`，其中 `outcome`
為 `retry` 或 `exhausted`。先啟用 `server.observability.metrics.enabled`
和 `server.observability.metrics.exporters.prometheus.enabled`，配置 Prometheus
抓取 `/metrics`，再將以下示例加入 Prometheus 告警規則：

```yaml
groups:
  - name: openviking-pathlock-recovery
    rules:
      - alert: OpenVikingPathlockRecoveryBlocked
        expr: sum by (queue) (increase(openviking_pathlock_recovery_blocked_total{outcome="retry"}[5m])) >= 8
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "OpenViking 路徑鎖恢復反覆阻塞"
      - alert: OpenVikingPathlockRecoveryExhausted
        expr: sum by (queue) (increase(openviking_pathlock_recovery_blocked_total{outcome="exhausted"}[5m])) > 0
        labels:
          severity: critical
        annotations:
          summary: "OpenViking 路徑鎖恢復已達重試上限"
```

閾值應按業務流量調整。告警後結合日誌中的 `task_id` 和失敗原因檢查競爭寫入者或
Redis 可用性，解決原因後重新提交失敗任務。指標啟用和規則配置見
[指標體系](./12-metrics.md)及 [Grafana 與 Prometheus](../guides/11-grafana-prometheus.md)。

## 相關文件

- [架構概述](./01-architecture.md) - 系統整體架構
- [儲存架構](./05-storage.md) - AGFS 和向量庫
- [會話管理](./08-session.md) - 會話和記憶管理
- [配置](../guides/01-configuration.md) - 配置檔案說明
