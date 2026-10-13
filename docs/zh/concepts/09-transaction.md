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

鎖型別由呼叫者選擇，Resolver 根據目標狀態決定 token 位置：

| 目標狀態 | Exact token | Tree token |
| --- | --- | --- |
| 現存檔案 `/docs/a` | `/docs/.exact.ovlock.a.<hash>`，內容為 E | 同一 sidecar，內容為 T |
| 現存目錄 `/docs/a` | `/docs/a/.path.ovlock`，內容為 E | 同一目錄內檔案，內容為 T |
| 缺失路徑 `/docs/a` | 父目錄 sidecar，內容為 E | 建立目標目錄後寫內部 `.path.ovlock`，內容為 T |

sidecar 位於目標旁邊，但只代表該目標，不會鎖住整個父目錄。`<hash>` 來自完整後端路徑的 SHA-1 字首，與業務檔案內容無關。

`.exact.ovlock.*` 可以存 Tree token，`.path.ovlock` 也可以存 Exact token。檔名是儲存協議的一部分，不能單憑名字判斷邏輯鎖型別。token 內容為：

```text
{owner_id}:{time_ns}:{lock_type}
```

`lock_type` 為 `E` 或 `T`。該歸屬 token 用於競爭檢查、續期和條件釋放，不代表所有業務寫入都有儲存端 fencing 校驗。

lease 將邏輯範圍 `covered_paths` 與 token 位置 `lock_paths` 分開記錄。Owned lease 控制續期、釋放和交接；Borrowed lease 僅提供已有鎖的覆蓋證明，不能釋放外層鎖。

### Cache Provider 鎖協議

Cache Provider 將相同 token 格式存入 Redis HASH field，並通過 Lua
原子完成整批衝突檢查和寫入：

```text
field = logical_path
value = owner_id:time_ns:lock_type
```

HASH key 按路徑 scope 隔離：

```text
ov:pathlock:{namespace}:global:tokens
ov:pathlock:{namespace}:scope:_system:tokens
ov:pathlock:{namespace}:scope:account:{account}:tokens
```

所有 key 都使用 `{namespace}` 作為 Redis Cluster hash tag。Exact 獲取使用
`HMGET` 讀取目標和祖先；Tree 獲取只對所屬 scope 的 HASH 執行
`HGETALL`。`/` 和 `/local` 的 global 鎖不會掃描 account 或 `_system`
HASH。跨 scope batch 會被拒絕。

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
    4. 確保 Resolver 選定的 token 父目錄存在；缺失目標會因此被建立成目錄
    5. 寫入 TREE (T) token（現存檔案用 sidecar，其餘用內部 .path.ovlock）
    6. TOCTOU 雙重檢查：重新掃描後代目錄和祖先目錄
       - 發現衝突：比較 (timestamp, handle_id)
       - 後到者（更大的 timestamp/handle_id）主動讓步（刪除自己的鎖），防止活鎖
       - 等待後重試
    7. 驗證鎖檔案歸屬（fencing token 匹配）
    8. 成功

超時（預設 0 = 不等待）丟擲 LockAcquisitionError
```

### 缺失目錄建立規則

鎖系統允許為了放置鎖檔案而建立目錄，但建立前必須先檢查衝突：

```
1. 發現祖先 TreeLock / 同路徑鎖 / 後代鎖衝突 -> 不建立目錄，直接失敗或等待
2. 當前無衝突 -> 可以建立目錄並寫鎖
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
fencing token 校驗通過的一方成功持有 `TreeLock(java-guide)`；失敗方會刪除自己的鎖，
已創建出來的空目錄可以保留。

獲取失敗的回滾和正常釋放只清理 token，不保證刪除為存放 token 建立的目錄。Exact sidecar 也可能建立缺失的父目錄鏈。Snapshot 對缺失目標採用單獨的策略，見 [快照的範圍與併發](../guides/15-snapshot.md#提交範圍與併發)。

### 鎖過期清理

**自動續期**：Rust PathLockManager 每隔 `lock_expire / 3` 重新整理活躍 lease；預設過期時間為 30 秒，不是業務操作的最長執行時間。程序退出後續期停止。

**陳舊鎖檢測**：PathLockEngine 檢查歸屬 token 中的時間戳。超過 `lock_expire`（預設 30s）的鎖被視為陳舊鎖，在加鎖過程中自動移除。

**程序內清理**：Rust PathLockManager 在續期迴圈中檢查長期未成功續期的 lease，以 `2 × lock_expire` 為閾值嘗試清理，並校驗歸屬後釋放 token。

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
Redis Cache Provider 和非空 PathLock namespace。執行時等待超時固定為
`0.0` 秒。`storage.transaction` 僅保留為相容舊配置：`lock_timeout`
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
        "namespace": "production",
        "lock_expire_secs": 30.0
      }
    }
  }
}
```

| 引數 | 型別 | 說明 | 預設值 |
|------|------|------|--------|
| `provider` | str | `filesystem`、`memory` 或 `cache` | `filesystem` |
| `namespace` | str 或 null | `provider=cache` 時必填，用於標識一個 OpenViking 部署 | `null` |
| `lock_expire_secs` | float | 未重新整理的鎖進入 stale 狀態前的秒數 | `30.0` |

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

## 相關文件

- [架構概述](./01-architecture.md) - 系統整體架構
- [儲存架構](./05-storage.md) - AGFS 和向量庫
- [會話管理](./08-session.md) - 會話和記憶管理
- [配置](../guides/01-configuration.md) - 配置檔案說明
