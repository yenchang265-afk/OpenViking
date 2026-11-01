# 認證

API Key 用於確認請求來自誰，以及可以執行哪些操作。團隊使用 OpenViking 時，可以由平臺管理員配置 Root Key，再為團隊管理員和普通使用者建立各自的訪問憑據。

本頁完成一個最小流程：啟用 API Key 認證，建立 `acme` 團隊及管理員 `team-admin`，再建立普通使用者 Alice 和 Bob。後續團隊管理文件沿用這些身份。

## 準備工作

本例適用於可以修改配置並重啟的自建服務。準備已安裝的 `ov` CLI、curl，以及已有的服務端配置。模型和儲存的配置沿用[快速開始](02-quickstart.md)；本文的 JSON 只展示需要合併的欄位。

火山引擎雲服務由平臺管理認證和帳號，按控制台提供的流程獲取憑據。以下 Root Key 配置用於自建服務。

| 身份 | 憑據 | 用途 |
| --- | --- | --- |
| 平臺管理員 ROOT | `server.root_api_key` | 建立和管理 Account 等平臺操作 |
| 團隊管理員 ADMIN | 建立管理員時返回的 `user_key` | 管理本 Account 的使用者，以及該管理員自己的資料和團隊共享資料 |
| 普通使用者 USER | 建立使用者時返回的 `user_key` | 訪問個人資料和已授權的共享資料 |

API Key 模式下，服務端從憑據解析 Account、User 和角色。Root Key 沒有繫結租戶使用者，日常資料、記憶和會話操作使用 User/Admin Key。

## 配置 Root Key

由平臺管理員先備份當前使用的 `ov.conf`。生成一個隨機金鑰，例如在本機終端執行：

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

將生成的值儲存在受控位置，並填入服務端配置的 `server` 段。保留原有的模型、儲存和其他服務引數：

```json
{
  "server": {
    "host": "127.0.0.1",
    "auth_mode": "api_key",
    "root_api_key": "<隨機生成的 Root Key>"
  }
}
```

用原配置路徑和啟動引數重啟服務。預設路徑的本機服務可以使用：

```bash
openviking-server --config ~/.openviking/ov.conf
```

如需同時使用 VikingBot，在原啟動命令中保留 `--with-bot`。網路部署的地址、HTTPS 和反向代理配置見[服務部署](../guides/03-deployment.md)。

認證啟用後，客戶端需要使用對應憑據。原有資料仍保留在原儲存位置和 Account 下，建立新團隊不會自動遷移此前的預設帳號資料。

## 建立團隊管理員

由平臺管理員執行。本例使用 macOS / Linux 的 bash 或 zsh；將 `OV_URL` 換成實際服務地址。執行 `read` 後貼上剛才設定的 Root Key，再按回車，輸入時不會回顯：

```bash
export OV_URL="http://127.0.0.1:1933"
read -r -s ROOT_KEY
export ROOT_KEY
```

建立 `acme` 團隊，並同時建立第一個管理員 `team-admin`：

```bash
curl -sS -X POST "$OV_URL/api/v1/admin/accounts" \
  -H "X-API-Key: $ROOT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"account_id":"acme","admin_user_id":"team-admin"}'
```

檢查響應的 `status` 為 `ok`，並儲存 `result.user_key`。這是 **team-admin 的 Admin Key**，與 Root Key 不同。通過安全渠道將它交給該團隊管理員。響應包含憑據，儲存和轉發時僅提供給對應使用者。

如果 `acme` 已存在，使用已有帳號繼續；需要獨立體驗時，選擇新名稱並同步替換後續命令中的 Account ID。

## 建立普通使用者

由團隊管理員開啟 CLI 連線嚮導：

```bash
ov config
```

新增名為 `acme-admin` 的自定義連線，填寫上述服務地址和 team-admin 的 Admin Key，儲存並啟用。檢查連線後，建立兩個普通使用者：

```bash
ov health
ov admin register-user acme alice --role user
ov admin register-user acme bob --role user
```

兩次註冊分別返回各自的 `user_key`。管理員將對應憑據交給 Alice 和 Bob；兩人使用自己的憑據分別儲存 `acme-alice`、`acme-bob` 命名連線。詳細連線步驟見 [CLI 入門](05-cli-setup.md)。

需要增加另一位管理員時，可以註冊 `--role admin` 的使用者；角色管理介面見 [Admin API](../api/08-admin.md)。團隊管理員無需持有 Root Key 即可管理本團隊成員。

## 核對身份

在 Alice 的終端中選中她的連線：

```bash
ov config switch acme-alice
ov health -o json
ov ls viking://~/
```

健康響應應顯示 `account_id: acme`、`user_id: alice`、`role: user`，並且能夠列出 Alice 的家目錄。用 team-admin 的連線檢查時，身份應為 `team-admin`、角色為 `admin`。

每個人可以在自己的電腦上使用這些連線名稱。如果由同一位操作者驗證多個身份，先儲存相應命名連線，再在每組操作前切換。修改 `--user` 或 `--account` 不會改變 API Key 繫結的身份。

## 常見問題

| 現象 | 下一步 |
| --- | --- |
| 啟用認證後舊連線失敗 | 在 `ov config` 中補充該使用者的 User/Admin Key |
| Root Key 可以建立團隊，但不能讀取資料 | 使用團隊內的 User/Admin Key 執行資料操作 |
| 普通使用者建立成員被拒絕 | 切換到該 Account 的管理員連線 |
| 新團隊看不到之前的資料 | 核對原資料所屬 Account，按[知識共享](22-sharing.md)選擇釋出或遷移 |

平臺管理員完成操作後，可用 `unset ROOT_KEY` 清除當前終端的變數。金鑰輪換和其他認證模式見[身份認證](../guides/04-authentication.md)。

## 下一步

繼續閱讀 [Account](18-accounts.md)，建立第二個團隊並驗證資料隔離。
