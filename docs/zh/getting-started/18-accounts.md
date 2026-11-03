# Account

Account 是 OpenViking 的團隊或租戶空間。一個服務可以承載多個 Account，每個 Account 擁有自己的使用者、資料、記憶和會話。

適合為不同團隊、客戶或獨立業務建立資料邊界。同一團隊的成員放在同一個 Account 中協作；需要在團隊內進一步限制資料訪問時，使用 [ACL](21-access-control.md)。

## 理解邊界

| 範圍 | 內容 | 共享方式 |
| --- | --- | --- |
| Account | 團隊的使用者與資料 | 與其他 Account 隔離 |
| User | 個人記憶、資料和會話 | 使用者自身訪問；適合分享的知識可釋出到共享資料區 |
| 共享資料區 | `viking://resources/...` | 當前 Account 內共享，可通過 ACL 細分授權 |

兩個 Account 可以使用相同的 URI，例如 `viking://resources/team-check`。請求憑據決定實際訪問哪個 Account，URI 中不需要拼接 Account ID。這是邏輯資料隔離；獨立儲存或模型配置見 [Account 配置參考](../api/08-admin.md)。

## 準備工作

先完成[認證](17-authentication.md)，已有 `acme`、管理員 `team-admin` 和 Alice、Bob。平臺管理員持有 Root Key，並已在終端中設定 `OV_URL`、`ROOT_KEY`。本例再建立 `beta` 團隊。

建立 Account 由平臺管理員執行，團隊管理員負責本 Account 的成員管理。以下驗證只建立空目錄，不呼叫生成模型。

## 建立第二個團隊

平臺管理員建立 `beta` 及其首個管理員：

```bash
curl -sS -X POST "$OV_URL/api/v1/admin/accounts" \
  -H "X-API-Key: $ROOT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"account_id":"beta","admin_user_id":"beta-admin"}'
```

儲存返回的 `result.user_key` 並交給 beta-admin。由 beta-admin 通過 `ov config` 儲存名為 `beta-admin` 的連線，使用相同服務地址和自己的 Admin Key。

## 在 acme 建立內容

由 acme 的 Alice 執行。在她的連線下建立一個新的共享目錄：

```bash
ov config switch acme-alice
ov health -o json
ov mkdir viking://resources/team-check
ov ls viking://resources
```

確認身份屬於 `acme`，並且目錄列表中出現 `team-check`。如果目錄已存在，選擇新名稱進行驗證。

## 從 beta 核對隔離

由 beta-admin 使用自己的連線檢查同一 URI：

```bash
ov config switch beta-admin
ov health -o json
ov stat viking://resources/team-check
```

確認當前 Account 是 `beta`。如果 beta 內還沒有同名目錄，應返回未找到；acme 中剛建立的目錄不會出現在這裡。

再由 beta-admin 建立同名目錄：

```bash
ov mkdir viking://resources/team-check
ov ls viking://resources
```

建立應成功。現在兩個團隊各自擁有一個 `team-check`，後續內容變更也各自在所屬 Account 內生效。

## 選擇團隊連線

API Key 模式下，每個使用者憑據繫結一個 Account 和 User。需要訪問另一團隊時，由該團隊管理員建立對應身份並提供憑據，再儲存新的連線。

業務應用應按登入使用者對映到相應的 OpenViking 連線。一個請求的 `--account` 引數無法把已有使用者 Key 變成其他團隊的身份；上游統一傳遞身份的部署方式見[身份認證](../guides/04-authentication.md)。

## 檢查結果

| 檢查項 | 預期結果 |
| --- | --- |
| Alice 的健康響應 | `account_id` 為 `acme` |
| beta-admin 的健康響應 | `account_id` 為 `beta` |
| beta 建立目錄前 | 看不到 acme 的 `team-check` |
| beta 建立同名目錄後 | 兩個 Account 各自保有獨立目錄 |

如果結果不符，先用 `ov config show` 和 `ov health -o json` 核對當前服務、使用者和 Account。預設無鑑權的本機模式不適合作為多使用者身份隔離的驗證環境。

## 下一步

繼續 [User](19-users.md) 驗證同一 Account 下的個人資料邊界；跨 Account 交付資料時，檢視[知識共享](22-sharing.md)。
