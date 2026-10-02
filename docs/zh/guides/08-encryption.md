# 加密指南

本指南介紹如何在 Business Data Platform 中啟用和使用靜態資料加密功能。

## 概述

Business Data Platform 提供透明的靜態資料加密，確保多租戶環境下的資料安全與隔離：

- ✅ **透明加密**：API 無變化，應用層無感知
- ✅ **多租戶隔離**：不同帳戶使用獨立金鑰
- ✅ **三種金鑰提供程式**：Local、Vault、火山引擎 KMS
- ✅ **向後相容**：未加密的舊檔案仍可正常讀取

加密功能的概念說明見 [資料加密](../concepts/10-encryption.md)。

## 多寫儲存中的加密

多寫儲存複用同一套透明加密機制。加密仍在 RAGFS 內部完成，Python SDK、HTTP API 和 CLI 不需要處理加解密。

規則：

- 全域 `encryption.enabled=true` 時，primary backend 必須加密。
- backup backend 可以通過自己的 `encryption.enabled` 控制是否加密。
- `.redirect.json` 和 `.sync_log.json` 等多寫內部後設資料跟隨 primary 加密策略。
- Business Data Platform 不提供也不需要公開的加解密 API 來操作這些內部檔案。

更多多寫配置見 [多寫儲存指南](./13-multi-write-storage.md)。

## 快速開始

### 1. 初始化根金鑰（Local 模式）

```bash
ov system crypto init-key --output-file ~/.openviking/master.key
```

### 2. 配置加密

編輯 `~/.openviking/ov.conf`：

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
import asyncio
from pathlib import Path
from openviking_sdk import AsyncHTTPClient


async def test():
    # 啟用認證時，將 OPENVIKING_API_KEY 設定為繫結租戶身份的 user/admin key。
    client = AsyncHTTPClient(url="http://localhost:1933")
    try:
        await client.initialize()
        sample = Path("./encrypted-sample.txt")
        sample.write_text("Hello, encrypted world!", encoding="utf-8")
        imported = await client.add_resource(
            path=str(sample),
            wait=True,
            timeout=120,
        )
        results = await client.find(
            query="encrypted", target_uri=imported["root_uri"]
        )
        print(f"找到 {len(results.get('resources', []))} 個資源")
    finally:
        await client.close()


asyncio.run(test())
```

示例會等待匯入處理完成並檢查檢索；檢索成功本身不能證明檔案已加密。請按下方“驗證加密”的檔案內容檢查步驟確認儲存檔案頭。

## API Key 哈希配置

Business Data Platform 提供兩層加密保護：

| 加密層 | 配置項 | 演算法 | 可逆性 | 說明 |
|--------|--------|------|--------|------|
| **檔案層** | `encryption.enabled` | AES-GCM | ✅ 可逆 | 保護整個儲存檔案 |
| **API key 欄位層** | `encryption.api_key_hashing.enabled` | Argon2id | ❌ 不可逆 | 保護 API key 本身 |

### ⚠️ Breaking Change 說明

**版本變更**：Business Data Platform v0.3.12 → later versions

**行為變化**：
- **之前**：`encryption.enabled = true` 隱式啟用 API key Argon2id 雜湊
- **現在**：需要顯式配置 `encryption.api_key_hashing.enabled`

**影響**：
- 升級後，如果 `encryption.enabled = true` 但 `encryption.api_key_hashing.enabled` 未顯式配置為 `true`，會在啟動時看到以下警告日誌：
  ```
  API key hashing is disabled while file encryption is enabled.
  Previously, encryption.enabled=true implicitly enabled API key Argon2id hashing.
  Now, API keys will be stored in plaintext within AES-GCM encrypted files.
  To maintain the previous behavior, set encryption.api_key_hashing.enabled=true.
  ```

**遷移選項**：

| 選項 | 配置 | 行為 |
|------|------|------|
| **保持原有行為** | `api_key_hashing.enabled = true` | API key 使用 Argon2id 雜湊儲存 |
| **推薦新行為** | `api_key_hashing.enabled = false`（預設） | API key 明文儲存（檔案層仍加密） |

### 預設行為

**預設情況下，`encryption.api_key_hashing.enabled = false`**：
- API key 以明文儲存在 JSON 檔案中
- 如果 `encryption.enabled = true`，整個檔案會被 AES-GCM 加密保護
- `ov admin list-users` 可以顯示完整的 API key

### 啟用 Argon2id 雜湊

如果需要最進階別的 API key 保護，可以啟用 Argon2id 單向雜湊：

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
- `ov admin list-users` 只顯示 `key_prefix` 而不是完整的 API key
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
| **Local** | 開發環境、單節點部署 | 簡單，無需外部服務 | 金鑰儲存在本地，安全性較低 |
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

---

## Vault 模式詳細指南

### 前置條件

1. 已部署 HashiCorp Vault 服務
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
vault secrets enable -version=2 kv

# 或 KV v1
vault secrets enable kv
```

3. 配置 Business Data Platform：

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
      "kv_version": 1,
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

為 Token 配置最小許可權：

```hcl
path "transit/encrypt/openviking-root" {
  capabilities = ["update"]
}

path "transit/decrypt/openviking-root" {
  capabilities = ["update"]
}
```

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

### 配置 Business Data Platform

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

加密檔案以魔術數 `OVE1` 開頭：

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

### 方法二：跨提供程式驗證

嘗試用不同提供程式解密彼此的資料，應該會失敗（這是正常的安全行為）：

```python
# 用 Provider A 加密
encrypted = await provider_a.encrypt_file_key(plaintext, "test-account")

# 嘗試用 Provider B 解密（應該失敗）
try:
    await provider_b.decrypt_file_key(encrypted, "test-account")
    print("❌ 安全漏洞：跨提供程序解密成功！")
except Exception as e:
    print("✓ 安全：跨提供程式解密失敗，符合預期")
```

---

## 遷移說明

### 從無加密遷移到有加密

啟用加密不會改寫已有明文檔案。為了向後相容，這些檔案仍可讀取；新寫入的資料會使用加密。如需加密已有公開 scope，應通過 OVPack 將其遷移到全新的空加密儲存環境：

1. 停止業務寫入，在原未加密環境執行時建立邏輯備份：

```bash
ov backup ./backups/before-encryption.ovpack
```

2. 停止 Business Data Platform，啟用加密，並將儲存配置指向**全新的空** workspace/backend。驗證完成前保留原資料和加密金鑰備份。
3. 啟動加密環境。API Key 模式下，先建立目標 account 和持有 admin key 的恢復操作使用者，再讓 CLI 使用該 key 連線目標環境，參見 [全量備份和恢復](09-ovpack.md#全量備份和恢復)。恢復過程會通過加密儲存層寫入 package 內容：

建立 account 會生成 scope 目錄，因此 `fail` 會拒絕這次恢復。僅在確認目標只有新建 account 的預置內容後，使用下方的 `overwrite`。如果已有業務資料，先停止操作，按 OVPack 指南備份目標並審查衝突。

```bash
ov restore ./backups/before-encryption.ovpack --on-conflict overwrite
```

4. 切流前驗證資源、使用者、session 和索引資料。OVPack 不包含 queue、upload、lock、watch 和 relation 檔案等執行時/內部狀態，這些內容需要單獨重建或驗證。

支援的 scope 和恢復選項詳見 [OVPack 匯入與匯出](09-ovpack.md#全量備份和恢復)。

### 切換金鑰提供程式

1. 備份現有資料和金鑰
2. 使用舊提供程式解密所有資料
3. 配置新提供程序
4. 重新加密所有資料

**注意**：這是一個破壞性操作，建議在測試環境先驗證。

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

### 跨提供程式解密失敗（這是正常的）

```
Error: KeyMismatchError
```

**說明**：這是預期的安全行為。不同提供程式使用不同的根金鑰，無法相互解密。

### 部分讀取返回密文

如果使用舊版本 Business Data Platform 建立的加密檔案，部分讀取可能返回密文。

**解決方案**：升級到最新版本的 Business Data Platform。

---

## 相關文件

- [資料加密](../concepts/10-encryption.md) - 加密概念說明
- [配置指南](./01-configuration.md) - 完整配置參考
- [多租戶](../concepts/11-multi-tenant.md) - 帳號、使用者與 Agent 的隔離模型
