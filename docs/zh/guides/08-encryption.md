# 加密指南

本指南介紹如何在 OpenViking 中啟用和使用靜態資料加密功能。

## 概述

OpenViking 可以按帳戶加密儲存中新寫入的檔案。加解密由儲存層處理，客戶端沿用現有 API：

- **透明加密**：API 無變化，應用層無感知
- **多租戶隔離**：不同帳戶使用獨立金鑰
- **三種金鑰提供程式**：Local、Vault、火山引擎 KMS
- **向後相容**：未加密的舊檔案仍可正常讀取

加密功能的概念說明見 [資料加密](../concepts/10-encryption.md)。

## 主備儲存中的加密

主備儲存複用同一套透明加密機制。加密仍在 RAGFS 內部完成，Python SDK、HTTP API 和 CLI 不需要處理加解密。

規則：

- 全域 `encryption.enabled=true` 時，primary backend 必須加密。
- backup backend 可以通過自己的 `encryption.enabled` 控制是否加密。
- V2 多寫 metadata 儲存在 raw primary，不經過 `EncryptionWrappedFS`。
- OpenViking 不提供也不需要公開的加解密 API 來操作這些內部檔案。

更多主備儲存配置見 [主備儲存指南](./13-multi-write-storage.md)。

## 快速開始

### 1. 初始化根金鑰（Local 模式）

```bash
ov system crypto init-key --output-file ~/.openviking/master.key
```

### 2. 配置加密

將下面的加密配置合併到 `~/.openviking/ov.conf`，保留已有模型和服務端配置：

```json
{
  "encryption": {
    "enabled": true,
    "provider": "local",
    "local": {
      "key_file": "~/.openviking/master.key"
    }
  },
  "storage": {
    "workspace": "./data"
  }
}
```

### 3. 驗證

修改加密配置後重啟服務，再對該服務執行示例。在執行指令碼的環境中安裝 [Python SDK](../api/01-overview.md#完全不依賴配置檔案使用-python-sdk-客戶端)。

```python
from pathlib import Path
from openviking_sdk import SyncHTTPClient


def test():
    # 啟用認證時，將 OPENVIKING_API_KEY 設定為繫結租戶身份的 user/admin key。
    client = SyncHTTPClient(url="http://localhost:1933")
    try:
        client.initialize()
        sample = Path("./encrypted-sample.txt")
        sample.write_text("Hello, encrypted world!", encoding="utf-8")
        imported = client.add_resource(
            path=str(sample),
            wait=True,
            timeout=120,
        )
        results = client.find(
            query="encrypted", target_uri=imported["root_uri"]
        )
        print(f"找到 {len(results.get('resources', []))} 個資源")
    finally:
        client.close()


test()
```

示例會等待匯入處理完成並檢查檢索；檢索成功本身不能證明檔案已加密。請按下方“驗證加密”的檔案內容檢查步驟確認儲存檔案頭。

## API Key 哈希配置

檔案加密和 API Key 雜湊是兩項獨立配置：

| 加密層 | 配置項 | 演算法 | 可逆性 | 說明 |
|--------|--------|------|--------|------|
| **檔案層** | `encryption.enabled` | AES-GCM | 可逆 | 保護整個儲存檔案 |
| **API key 欄位層** | `encryption.api_key_hashing.enabled` | Argon2id | 不可逆 | 保護 API key 本身 |

### 預設行為

**預設情況下，`encryption.api_key_hashing.enabled = false`**：
- API key 以明文儲存在 JSON 檔案中
- 如果 `encryption.enabled = true`，整個檔案會被 AES-GCM 加密保護
- `ov admin list-users` 傳入 `--reveal-api-keys` 後可以顯示完整的 API key
- 如果 `encryption.enabled = true` 且未啟用 API key 雜湊，服務端啟動時會輸出一條說明此情況的 INFO 日誌

### 啟用 Argon2id 雜湊

啟用 Argon2id 單向雜湊後，服務端不再儲存可還原的 API Key 明文：

```json
{
  "encryption": {
    "enabled": true,
    "api_key_hashing": {
      "enabled": true
    }
  }
}
```

**注意**：啟用後：
- API key 使用 Argon2id 單向雜湊儲存
- 無法從雜湊值還原出明文 key
- `ov admin list-users` 只顯示 `key_prefix` 而不是完整的 API key（呼叫方自身的行也無法顯示明文，因為服務端未儲存明文）
- 只有在建立使用者或重新生成 key 時才能看到明文 key

### 配置示例

```json
{
  "encryption": {
    "enabled": true,
    "provider": "local",
    "local": {
      "key_file": "~/.openviking/master.key"
    },
    "api_key_hashing": {
      "enabled": false
    }
  }
}
```

## 金鑰提供程式選擇

| 提供程式 | 適用場景 | 優點 | 缺點 |
|---------|---------|------|------|
| **Local** | 開發環境、單節點部署 | 簡單，無需外部服務 | 需要管理本地金鑰許可權和獨立金鑰備份 |
| **Vault** | 生產環境、多雲部署 | 企業級金鑰管理，支援版本控制 | 需要部署和維護 Vault |
| **Volcengine KMS** | 火山引擎雲部署 | 雲原生金鑰管理服務 | 僅限火山引擎環境 |

---

## Local 模式詳細指南

### 初始化根金鑰

```bash
# 生成並儲存到指定路徑
ov system crypto init-key --output-file ~/.openviking/master.key

# 或者使用簡短命令
ov system crypto init-key -f ~/.openviking/master.key
```

**輸出示例**：
```
✓ Root key generated successfully
✓ Saved to: /Users/you/.openviking/master.key
```

### 安全提示

- ⚠️ 妥善保管 `master.key` 文件
- 建議設定檔案許可權為 `600`（僅所有者可讀寫）
- 定期備份金鑰檔案
- 不要將金鑰檔案提交到版本控制系統

### 配置示例

```json
{
  "encryption": {
    "enabled": true,
    "provider": "local",
    "local": {
      "key_file": "~/.openviking/master.key"
    }
  }
}
```

### 在配置中直接提供根金鑰

對於簡單、受控的部署，Local provider 可以直接從 `ov.conf` 讀取同一個 32 位元組根金鑰，
不再使用單獨的金鑰檔案：

```json
{
  "encryption": {
    "enabled": true,
    "provider": "local",
    "local": {
      "root_key": "<64 個十六進位制字元的根金鑰>"
    }
  }
}
```

配置值是 32 位元組金鑰的十六進位制表示，因此必須恰好包含 64 個十六進位制字元。可以使用
`openssl rand -hex 32` 生成，也可以在兩種 Local 配置之間遷移時直接複用已有
`master.key` 的內容。

- 不要同時配置 `root_key` 和 `key_file`；如果兩者都省略，Local provider 仍使用
  `~/.openviking/master.key`。
- 內聯金鑰不會自動生成；金鑰丟失或改變後，已有加密資料將無法讀取。
- 此時必須把 `ov.conf` 當作金鑰檔案管理：只允許服務使用者讀取、安全備份，並且禁止提交到版本控制。
- 生產環境需要集中式金鑰管理時，仍建議使用 Vault 或 KMS。

---

## Vault 模式詳細指南

### 前置條件

1. 已部署 HashiCorp Vault 服務，並在服務端 Python 環境安裝 `hvac`
2. 已啟用 Transit 引擎
3. 有足夠許可權的 Vault Token

### 配置 Vault

1. 啟用 Transit 引擎（如果尚未啟用）：

```bash
vault secrets enable transit
```

2. 啟用 KV 引擎（如果尚未啟用）：

```bash
# KV v2（推薦）
vault secrets enable -path=secret -version=2 kv

# 或 KV v1
vault secrets enable -path=secret -version=1 kv
```

按實際部署選擇一條 KV 命令，不要兩條都執行。下面使用 `secret` 掛載點和 KV v2。先由管理員建立 Transit key：

```bash
vault write -f transit/keys/openviking-root-key type=aes256-gcm96
```

3. 配置 OpenViking：

```json
{
  "encryption": {
    "enabled": true,
    "provider": "vault",
    "vault": {
      "address": "https://vault.example.com:8200",
      "token": "hvs.xxxxxxxxxxxxxxxxxxxxx",
      "mount_point": "transit",
      "kv_mount_point": "secret",
      "kv_version": 2,
      "root_key_name": "openviking-root-key",
      "encrypted_root_key_key": "openviking-encrypted-root-key"
    }
  }
}
```

**配置引數說明**：

| 引數 | 說明 | 預設值 |
|------|------|--------|
| `address` | Vault 伺服器地址 | 必需 |
| `token` | Vault 認證令牌 | 必需 |
| `mount_point` | Transit 引擎掛載路徑 | `"transit"` |
| `kv_mount_point` | KV 引擎掛載路徑 | `"secret"` |
| `kv_version` | KV 引擎版本（1 或 2） | `1` |
| `root_key_name` | Transit 引擎中的金鑰名稱 | `"openviking-root-key"` |
| `encrypted_root_key_key` | KV 引擎中儲存加密根金鑰的路徑 | `"openviking-encrypted-root-key"` |

### Vault 許可權建議

對於上面的配置，服務 token 需要讀取 Transit key 後設資料、加解密許可權，以及儲存封裝根金鑰的 KV 讀寫許可權。提前建立引擎和 Transit key 後，可參考：

```hcl
path "auth/token/lookup-self" {
  capabilities = ["read"]
}

path "transit/keys/openviking-root-key" {
  capabilities = ["read"]
}

path "secret/data/openviking-encrypted-root-key" {
  capabilities = ["read", "create", "update"]
}

path "transit/encrypt/openviking-root-key" {
  capabilities = ["update"]
}

path "transit/decrypt/openviking-root-key" {
  capabilities = ["update"]
}
```

使用 KV v1 時，將 `secret/data/openviking-encrypted-root-key` 改為 `secret/openviking-encrypted-root-key`。provider 還會檢查 `sys/mounts`；許可權不足會記錄警告，Transit 已啟用時不會因此停止啟動。

---

## Volcengine KMS 模式詳細指南

### 前置條件

1. 已開通火山引擎 KMS 服務
2. 已建立對稱金鑰
3. 有有效的 Access Key 和 Secret Key

### 建立 KMS 金鑰

1. 訪問 [火山引擎 KMS 控制台](https://console.volcengine.com/kms)
2. 點選"建立金鑰"
3. 選擇"對稱金鑰"，演算法選擇 `AES_256`
4. 記錄金鑰 ID

### 配置 OpenViking

```json
{
  "encryption": {
    "enabled": true,
    "provider": "volcengine_kms",
    "volcengine_kms": {
      "key_id": "d926aa0d-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "region": "cn-beijing",
      "access_key": "AKLTxxxxxxxxxxxxxxxxxx",
      "secret_key": "Tmpxxxxxxxxxxxxxxxxxxxxxx",
      "endpoint": null,
      "key_file": "~/.openviking/openviking-volcengine-root-key.enc"
    }
  }
}
```

**配置引數說明**：

| 引數 | 說明 | 預設值 |
|------|------|--------|
| `key_id` | KMS 金鑰 ID | 必需 |
| `region` | 區域 | 必需 |
| `access_key` | Access Key | 必需 |
| `secret_key` | Secret Key | 必需 |
| `endpoint` | 自定義 KMS 端點（可選） | `null`（使用預設端點） |
| `key_file` | 加密根金鑰本地快取檔案路徑 | `"~/.openviking/openviking-volcengine-root-key.enc"` |

### 許可權建議

為 Access Key 配置最小許可權：

```json
{
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "kms:Encrypt",
        "kms:Decrypt"
      ],
      "Resource": [
        "trn:kms:*:*:key/d926aa0d-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      ]
    }
  ]
}
```

---

## 驗證加密

### 方法一：檢查檔案內容

檢查物理後端檔案，API 返回的內容已經解密。下面的路徑需換成實際檔案路徑。加密檔案以魔術數 `OVE1` 開頭：

```bash
# 檢視檔案前 4 位元組
hexdump -C ./data/agfs/your-file | head -1
```

**加密文件**：
```
00000000  4f 56 45 31 01 01 00 00  00 20 8a 7b 2c 9d 1e  |OVE1..... .{,..|
```
（前 4 位元組是 `4f 56 45 31` = "OVE1"）

**未加密文件**：
```
00000000  7b 22 63 6f 6e 74 65 6e  74 73 22 3a 5b 7b 22 70  |{"contents":[{"p|
```

### 方法二：重啟後讀回

重啟前後，通過 API 讀取同一份已匯入檔案，確認內容一致，再按上面的方法核對物理儲存檔案頭。這能檢查部署是否重新載入了原金鑰，並能讀取已有密文。

內部 provider 呼叫丟擲異常不能直接當作加密驗證通過。引數錯誤、依賴缺失和網路錯誤都可能在解密前失敗。

---

## 遷移說明

### 從無加密遷移到有加密

啟用加密不會改寫已有明文檔案。為了向後相容，這些檔案仍可讀取；新寫入的資料會使用加密。如需加密已有公開 scope，應通過 OVPack 將其遷移到全新的空加密儲存環境：

1. 停止業務寫入，在原未加密環境執行時建立邏輯備份：

```bash
ov backup ./backups/before-encryption.ovpack
```

2. 停止 OpenViking，啟用加密，並將儲存配置指向**全新的空** workspace/backend。驗證完成前保留原資料和加密金鑰備份。
3. 啟動加密環境。API Key 模式下，先建立目標 account 和持有 admin key 的恢復操作使用者，再讓 CLI 使用該 key 連線目標環境，參見 [全量備份和恢復](09-ovpack.md#全量備份和恢復)。恢復過程會通過加密儲存層寫入 package 內容：

建立 account 會生成 scope 目錄，因此 `fail` 會拒絕這次恢復。僅在確認目標只有新建 account 的預置內容後，使用下方的 `overwrite`。如果已有業務資料，先停止操作，按 OVPack 指南備份目標並審查衝突。

```bash
ov restore ./backups/before-encryption.ovpack --on-conflict overwrite
```

4. 切流前驗證資源、使用者、session 和索引資料。OVPack 不包含 queue、upload、lock、watch 和 relation 檔案等執行時/內部狀態，這些內容需要單獨重建或驗證。

支援的 scope 和恢復選項詳見 [OVPack 匯入與匯出](09-ovpack.md#全量備份和恢復)。

### 切換金鑰提供程式

保持舊 provider 和金鑰可用，匯出邏輯 OVPack 備份。按上面的遷移步驟，在使用新 provider 的獨立空環境恢復，核對內容、許可權和重建後的索引，再切換流量。直接修改原環境的 provider 配置不會重新加密已有檔案。

---

## 故障排除

### 金鑰檔案找不到

```
Error: Key file not found: ~/.openviking/master.key
```

**解決方案**：
1. 檢查檔案路徑是否正確
2. 使用絕對路徑
3. 確保 `~` 被正確展開（使用 `expanduser()`）

### Vault 連線失敗

```
Error: Failed to connect to Vault
```

**解決方案**：
1. 檢查 Vault 服務是否執行
2. 驗證 `address` 配置
3. 檢查網路連線和防火牆
4. 確認 Token 有效且未過期

### 火山 KMS 認證失敗

```
Error: Invalid credentials
```

**解決方案**：
1. 檢查 Access Key 和 Secret Key 是否正確
2. 確認金鑰有足夠許可權
3. 驗證區域配置正確

### 已有密文無法讀取

檢查原根金鑰、provider 配置、account 身份和密文是否仍然完整。Vault 需要保留 Transit key 和存放封裝根金鑰的 KV 條目；KMS 需要保留 KMS key 和本地封裝金鑰檔案。不要通過生成新根金鑰修復舊密文的讀取問題。

部分讀取會先載入並校驗整個加密檔案，再返回所需的明文切片。部分讀取返回密文時，記錄服務版本，在測試副本上比較完整讀取與部分讀取，核對儲存加密配置和相關修復後再升級。保留原資料及金鑰，以便回退。

---

## 相關文件

- [資料加密](../concepts/10-encryption.md) - 加密概念說明
- [配置指南](./01-configuration.md) - 完整配置參考
- [多租戶](../concepts/11-multi-tenant.md) - 帳號、使用者與 Agent 的隔離模型

Vault 參考：[KV v2](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2)、[Transit API](https://developer.hashicorp.com/vault/api-docs/secret/transit)。
