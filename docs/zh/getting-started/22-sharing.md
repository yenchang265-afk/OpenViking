# 知識共享

個人記憶幫助 Agent 延續使用者的工作背景。專案約定和可複用經驗需要被同事使用時，可以由記憶所有者整理出共享內容，釋出到團隊資料目錄，再由其他成員的 Agent 檢索、閱讀和引用。

本頁以 Alice 向 Bob 分享海岬專案評審約定為例，完成 **選擇記憶 → 整理內容 → 授權釋出 → Bob 檢索並使用 → 後續更新**，並說明跨團隊的處理方式。

## 選擇共享方式

| 場景 | 操作方式 |
| --- | --- |
| 同一 Account 內共享資料 | 釋出到 `viking://resources/...`，通過 ACL 授權使用者或使用者組 |
| 同一 Account 內共享個人經驗 | 所有者選擇記憶內容，整理成共享資料，再授權釋出 |
| 不同 Account 之間交付知識 | 來源方整理可交付內容，目標方使用自己的憑據匯入，並配置目標許可權 |
| 多人共同積累長期團隊記憶 | 由應用編排知識選擇、釋出和更新；當前沒有跨 User 私有記憶自動合併的共享開關 |

個人記憶目錄和 Peer 記憶目錄不接受共享資料 ACL。釋出後的內容作為共享資料維護，與原始記憶分別儲存。

## 準備工作

先完成[認證](17-authentication.md)，準備普通使用者 Alice、Bob，以及各自的 CLI 連線。按[訪問控制](21-access-control.md)開啟 `acme` 的 ACL，並建立 `viking://resources/team-knowledge`：Alice 為 `manage`，Bob 為 `read`。如果已體驗撤銷授權，由 Alice 先恢復 Bob 的 `read`。

Alice 應已有一份準備分享的專案記憶。首次體驗可在 Alice 連線下完成[記憶使用](09-memory.md)中的“儲存專案背景”和“檢視生成的記憶”，獲得海岬專案約定；本頁不依賴 VikingBot，能執行 CLI 的 Agent 即可完成最後的問答。

匯入、檢索和 Agent 回答會使用相應模型。每位成員使用自己的憑據；共享流程由以下角色分工完成：

| 角色 | 負責的操作 |
| --- | --- |
| 團隊管理員 | 開啟 ACL、準備共享目錄和初始許可權 |
| Alice 或她的 Agent | 讀取 Alice 的記憶、整理草稿、釋出和維護 |
| Bob 或他的 Agent | 檢索已授權資料、讀取原文並用於任務 |

## Alice 選擇記憶

在 Alice 的終端或 Agent 中使用她自己的連線：

```bash
ov config switch acme-alice
ov find "海岬專案的評審約定" --uri viking://~/memories
```

讀取相關結果，確認哪些內容適合分享：

```bash
ov read "<記憶 URI>"
```

可以把下面的任務交給 Alice 的 Agent：

```text
請從我的海岬專案記憶中整理可以共享給 Bob 的評審約定。
讀取原文，區分已確認的要求和待確定事項，生成 Markdown 草稿。
草稿附上供我核對的來源，先讓我確認，再發布到團隊資料目錄。
```

由 Alice 確認要共享的內容。對外發布的正文應包含可理解的事實，或引用 Bob 有權讀取的來源；Alice 的私有記憶 URI 可以留在個人核對記錄中。

## Alice 整理草稿

如果使用前述海岬樣例，核對記憶後，在本機建立 `cape-review.md`：

```markdown
# 海岬專案評審約定

## 評審要求

- 每次評審討論兩項風險。
- 摘要使用中文三條要點。
- 交付檔案統一命名為 cape-review.csv。

## 待補充資訊

- 本次評審的具體風險尚未提供。

## 維護資訊

- 維護人：Alice
- 適用範圍：海岬專案評審
```

這是與樣例輸入對應的共享正文。使用真實專案時，以讀到的記憶和 Alice 確認的內容替換，並保留適用範圍與待確定事項。

## Alice 釋出資料

根據資料所在位置選擇一種釋出方式：已有資料可以在服務端直接複製；本機新整理的草稿可以使用 `add-resource` 匯入。兩種方式都使用 Alice 的連線，併發布到已為 Bob 授權的目錄。

### 複製已有資料

如果待分享的內容已儲存在 Alice 的個人資料目錄，確認正文和引用適合共享後，可以直接複製，無需下載到本地。以下示例假設原始檔為 `viking://~/resources/cape-review/cape-review.md`；執行時替換為實際 URI。

Alice 需要能夠讀取源資料，並對目標目錄擁有 `write` 或 `manage` 許可權。先在 `team-knowledge` 下建立一個新的釋出目錄，再複製檔案：

```bash
ov config switch acme-alice
ov read viking://~/resources/cape-review/cape-review.md
ov mkdir viking://resources/team-knowledge/cape-review
ov cp viking://~/resources/cape-review/cape-review.md \
  viking://resources/team-knowledge/cape-review/cape-review.md -o json
ov read viking://resources/team-knowledge/cape-review/cape-review.md
```

這裡的 `~` 指向當前連線使用者 Alice。新建的共享資料繼承目標目錄許可權，Bob 可以按後文步驟檢索和讀取；Alice 的原始資料仍儲存在個人目錄中。

如果整個源目錄都適合共享，可以用下面的命令替代上面的 `mkdir` 和單檔案 `cp`。目標父目錄 `team-knowledge` 需已存在，目標 URI 就是複製後的目錄位置：

```bash
ov cp -r viking://~/resources/cape-review \
  viking://resources/team-knowledge/cape-review -o json
ov tree viking://resources/team-knowledge/cape-review
```

複製會同時複製已有向量記錄；目標父目錄的摘要可能非同步重新整理。響應中的 `semantic_status: queued` 表示摘要重新整理已入隊，`failed` 表示需要檢視 `semantic_error`。釋出後由 Bob 檢索並讀取正文，確認可用。完整行為見[檔案系統 API](../api/03-filesystem.md#cp)。

複製生成獨立副本，源資料後續修改不會自動同步。再次複製同名檔案會覆蓋目標正文，目錄複製會合併到已有目錄並保留目標獨有檔案。首次釋出使用新路徑；後續更新前核對目標內容，並檢查正文中引用的私有 URI 是否需要替換。

### 匯入本地草稿

如果使用前面整理的本地 Markdown 草稿，在檔案所在目錄執行，使用一個新的釋出路徑：

```bash
ov add-resource ./cape-review.md \
  --to viking://resources/team-knowledge/cape-review --wait
```

釋出目錄繼承 `team-knowledge` 的許可權。處理完成後，展開目錄並讀取實際正文 URI：

```bash
ov tree viking://resources/team-knowledge/cape-review
ov read "<共享正文 URI>"
```

記錄共享正文 URI，供 Bob 閱讀及後續更新。若等待超時，儲存返回的任務 ID，通過 `ov task status <task_id>` 檢查；確認完成後再讓 Bob 使用。

## Bob 檢索並使用

Bob 使用自己的連線檢索：

```bash
ov config switch acme-bob
ov find "海岬專案評審應採用什麼格式和交付檔名？" \
  --uri viking://resources/team-knowledge/cape-review
```

讀取結果中的共享正文 URI，核對內容。隨後在 Bob 的 Agent 中傳送：

```text
請使用我的 ov CLI 連線，檢索 viking://resources/team-knowledge/cape-review，
讀取相關原文，按海岬專案約定準備一份評審提綱。
列出摘要格式、風險討論數量和交付檔名，並引用共享資料的完整 URI。
具體風險未提供時，請保留待填寫項。
```

Agent 需要能夠執行 CLI，並在檢索流程中包含這個共享目錄。資料授權成功後，仍需由 Agent 檢索和讀取，才能把內容用於回答。

| 核對項 | 預期結果 |
| --- | --- |
| 訪問身份 | Bob 的 `ov health -o json` 顯示 `acme` / `bob` |
| 來源 | 命中 `team-knowledge/cape-review` 下的共享資料 |
| 回答 | 兩項風險、三條中文摘要、`cape-review.csv` |
| 未知資訊 | 具體風險保留待填寫，或明確說明未提供 |
| 私有邊界 | Bob 仍不能讀取 Alice 原始的私有記憶目錄 |

## 維護共享內容

預設由 Alice 維護。通過服務端複製釋出的資料，可以在原始檔更新並確認後，再次執行同一條檔案複製命令；這會覆蓋共享副本的正文，並保留目標許可權。

通過本地草稿釋出時，修改本機 `cape-review.md` 後，可以更新前面記錄的共享正文 URI：

```bash
ov config switch acme-alice
ov write "<共享正文 URI>" --from-file ./cape-review.md --mode replace --wait
```

這會替換該檔案的完整正文，並重新處理；釋出前核對本地檔案包含需要保留的全部內容。完成後，Bob 重新檢索、讀取，確認使用的是更新後的約定。

Alice 的個人記憶後續發生變化時，共享資料不會自動同步。需要共同維護時，Alice 可以授予 Bob `write`；合作結束時可撤銷授權，方法見[訪問控制](21-access-control.md)。Bob 已經下載或複製的內容需要另外管理。

## 跨團隊交付

如果 Bob 屬於另一個 Account，例如 `beta`，acme 的 ACL 無法直接授權 beta 的使用者。`user:bob` 只表示當前 Account 內的 Bob。

可由 Alice 將已確認的 `cape-review.md` 通過團隊認可的渠道交給 beta 的資料維護人。beta 管理員先按[訪問控制](21-access-control.md)在 **beta** 內開啟 ACL，建立受限共享目錄並授予目標成員許可權；把示例 Account ID 和使用者 ID 換成 beta 的實際成員。

獲得目標目錄寫許可權後，beta 的維護人使用自己的連線，在收到檔案的目錄中匯入：

```bash
ov config switch beta-admin
ov add-resource ./cape-review.md \
  --to viking://resources/team-knowledge/cape-review --wait
```

這裡的 `beta-admin` 是 [Account](18-accounts.md) 中建立的目標團隊連線。目標目錄、許可權和成員由 beta 獨立管理；匯入後由目標成員檢索並核對原文。來源與目標各自儲存一份資料，後續更新需要再次交付或由應用同步。

批次遷移可參考[匯入匯出](15-transfer.md)，完成後重新核對目標身份、目錄許可權和正文中的來源連結。如果多個小組需要長期共同維護同一份資料，可以把協作成員放在同一 Account 下，通過使用者組與 ACL 管理不同範圍。

## 下一步

用一份真實專案約定重複這個流程，確認 Bob 的 Agent 能找到共享內容並用於任務。更完整的多資料問答流程見[資料檢索](08-resources.md)。
