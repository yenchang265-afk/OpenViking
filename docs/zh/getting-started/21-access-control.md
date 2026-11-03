# 訪問控制

ACL 用於決定同一個 Account 內，哪些使用者可以讀取、修改或管理共享資料。適合專案協作、指定成員可讀和分組維護等場景。

本頁建立一個僅 Alice 可管理、Bob 可讀的共享目錄，再驗證讀取、拒絕寫入和撤銷授權。Account 管理員保留共享資料的隱式管理權。

## 準備工作

先完成[認證](17-authentication.md)，準備 `acme-admin`、`acme-alice` 和 `acme-bob` 三個連線。Alice 與 Bob 均為普通使用者，便於驗證授權效果。

ACL 適用於 `viking://resources/...`。個人記憶、個人資料和 Peer 空間保持 User 邊界；分享其中的內容可參考[知識共享](22-sharing.md)。

## 開啟 ACL

由 acme 的團隊管理員執行。在終端設定服務地址，並通過隱藏輸入提供 team-admin 的 Admin Key：

```bash
export OV_URL="http://127.0.0.1:1933"
read -r -s ADMIN_KEY
export ADMIN_KEY
```

開啟當前 Account 的 ACL 檢查：

```bash
curl -sS -X PATCH "$OV_URL/api/v1/admin/accounts/acme/configuration" \
  -H "X-API-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"settings":{"acl":{"enabled":true}}}'
```

檢查返回的 `result.settings.acl.enabled` 為 `true`。該開關預設關閉，關閉時共享資料不執行 ACL 過濾；單獨寫入授權條目不會自動開啟開關。

## 建立受限目錄

共享根目錄預設授予當前 Account 全員 `manage`，下級目錄繼承父目錄許可權。要限定到指定成員，使用 `restricted` 截斷繼承，並在建立時設定直接授權。

由團隊管理員建立一個新的示例目錄：

```bash
ov config switch acme-admin
ov mkdir viking://resources/team-knowledge \
  --acl '{"acl_mode":"restricted","entries":[{"principal":"user:alice","level":"manage"},{"principal":"user:bob","level":"read"}]}'
```

目錄已存在時先用 `ov acl get` 檢查其許可權；本次體驗可換一個新名稱，避免覆蓋原有授權。

| 許可權 | 可以執行的操作 |
| --- | --- |
| `read` | 讀取、列目錄和檢索 |
| `write` | 包含 read，並允許寫入、建立、刪除或移動檔案 |
| `manage` | 包含 write，並允許管理 ACL、刪除或移動目錄 |

## 寫入一份資料

由 Alice 釋出一份說明。寫入會觸發語義與向量處理，需要可用模型，併產生模型呼叫：

```bash
ov config switch acme-alice
ov write viking://resources/team-knowledge/access-check.md \
  --mode create --content "團隊約定：每週五彙總專案反饋。" --wait
```

新檔案繼承目錄許可權。檢視目錄授權與檔案正文：

```bash
ov acl get viking://resources/team-knowledge
ov read viking://resources/team-knowledge/access-check.md
```

如果等待超時，使用返回的任務 ID 查詢處理狀態，完成後繼續。

## 用 Bob 驗證

Bob 使用自己的連線讀取並檢索：

```bash
ov config switch acme-bob
ov read viking://resources/team-knowledge/access-check.md
ov find "什麼時候彙總專案反饋？" --uri viking://resources/team-knowledge
```

預期能讀到正文，檢索結果包含這份資料。再嘗試建立一個檔案：

```bash
ov write viking://resources/team-knowledge/bob-check.md \
  --mode create --content "Bob 的寫入檢查。"
```

由於 Bob 只有 `read`，寫入應被拒絕。如果成功，檢查當前身份是否為管理員、帳號 ACL 是否已開啟，以及目錄的有效許可權中是否還有其他授權。

## 調整授權

Alice 擁有 `manage`，可以授予 Bob 編輯許可權：

```bash
ov config switch acme-alice
ov acl grant viking://resources/team-knowledge --principal user:bob --level write
```

Bob 重新執行剛才的寫入命令應成功。後續只需閱讀時，將許可權設定回 `read`；合作結束時撤銷直接授權：

```bash
ov acl grant viking://resources/team-knowledge --principal user:bob --level read
ov acl revoke viking://resources/team-knowledge --principal user:bob
```

以上兩條由 Alice 執行。撤銷後切換到 Bob，再讀取 `access-check.md` 應被拒絕。許可權索引更新可能有短暫延遲，可每隔 2 秒檢查，先觀察最多 30 秒；持續可讀時檢查有效許可權和其他授權來源。

`revoke` 刪除當前節點的直接條目。若使用者還通過父目錄或使用者組獲得許可權，相應訪問仍然有效。撤銷也不會刪除使用者已下載的副本。需要繼續下一篇共享體驗時，由 Alice 恢復 Bob 的 `read` 許可權。

## 授權給使用者組

成員較多時，可以由管理員建立 Account 內的使用者組，維護成員後，把目錄授權給 `group:<group_id>`。組內成員變更從後續請求生效，適合為多個專案小組管理訪問。建立組與成員的完整步驟見 [Admin API](../api/08-admin.md#使用者組)。

## 下一步

繼續[知識共享](22-sharing.md)，將個人積累的專案知識釋出到這個受控目錄。許可權繼承和移動目錄的完整規則見 [ACL 概念](../concepts/15-acl.md)。
