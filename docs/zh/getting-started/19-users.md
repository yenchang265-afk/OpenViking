# User

User 是 Account 內的資料歸屬身份。OpenViking 用它區分個人記憶、私有資料和會話，讓同一團隊中的 Alice 和 Bob 各自保留長期上下文，同時使用團隊共享資料。

這裡的 User 是訪問服務時的身份，可以由應用對映到一個真實使用者或獨立的應用身份。多個 Agent 如果使用同一 User Key，就會使用同一個使用者空間；需要各自獨立的個人資料時，使用不同 User。

## 理解使用者空間

Alice 的目錄如下：

```text
viking://user/alice/
├── memories/    # Alice 的長期記憶
├── resources/   # Alice 的私有資料
├── skills/      # Alice 的私有技能
├── peers/       # Alice 的互動物件
└── sessions/    # Alice 的會話
```

`viking://~/` 是當前使用者家目錄的別名。Alice 使用時展開為 `viking://user/alice/`，Bob 使用時展開為 `viking://user/bob/`。共享資料位於同一 Account 的 `viking://resources/`。

## 準備工作

先完成[認證](17-authentication.md)，建立同屬 `acme` 的普通使用者 Alice 和 Bob，並儲存 `acme-alice`、`acme-bob` 連線。本例建立一個空的私有目錄和一個會話，不觸發記憶提取。

## 建立私有內容

Alice 切換到自己的連線，核對身份並建立目錄：

```bash
ov config switch acme-alice
ov health -o json
ov mkdir viking://~/resources/personal-check
ov ls viking://~/resources
```

目錄列表中應出現 `personal-check`。再建立一個由 Alice 持有的會話，並關閉自動提交：

```bash
ov session new --session-id alice-user-check --no-auto-commit
ov session add-message alice-user-check --role user --content "這是 Alice 的個人專案討論。"
ov session get alice-user-check
```

確認會話中能讀到這條訊息。會話訊息已儲存；提交後才進入記憶提取流程，後續操作見[記憶使用](09-memory.md)。

## 用 Bob 核對邊界

Bob 使用自己的連線列出家目錄：

```bash
ov config switch acme-bob
ov ls viking://~/resources
```

這裡展示 Bob 的私有資料目錄。繼續嘗試訪問 Alice 剛建立的目錄：

```bash
ov ls viking://user/alice/resources/personal-check
```

這次訪問應被拒絕。相同 Account 允許團隊協作，但個人空間仍按 User 劃分。需要分享其中的知識時，由 Alice 將選定內容釋出到共享資料區，見[知識共享](22-sharing.md)。

## User 與角色

User 決定資料屬於誰，角色決定允許執行哪些管理操作：

| 使用者角色 | 主要能力 |
| --- | --- |
| USER | 個人資料操作和已授權共享資料的訪問 |
| ADMIN | 自己的使用者空間、團隊成員管理、當前 Account 共享資料的管理 |

管理員的日常資料請求仍使用自己的 User 身份。API Key 模式下，管理員不能通過修改身份請求頭切換為 Alice 或 Bob。平臺 ROOT 負責 Account 等平臺操作，其 Root Key 不用於普通租戶資料讀取。

應用可以在多個會話中複用同一個使用者身份，使長期記憶持續積累；會話 ID 用來區分對話，Peer 用來區分該使用者下的穩定互動物件。

## 檢查結果

Alice 能訪問自己的目錄和會話，Bob 的家目錄解析到自己，並且不能讀取 Alice 的私有目錄。如果兩人看到了同一個個人空間，先核對是否共用了同一個 Key。

## 下一步

閱讀 [Peer](20-peers.md)，為同一使用者面對的不同互動物件分別組織資料和記憶。使用者註冊、角色調整和金鑰輪換見 [Admin API](../api/08-admin.md)。
