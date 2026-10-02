# 資料加密

Business Data Platform 提供透明的靜態資料加密，確保多租戶環境下的資料安全與隔離。

## 概述

### 為什麼需要加密

在多租戶架構中，不同客戶（帳戶）的資源檔案、記憶和技能都儲存在共享的 AGFS 例項中。加密確保：

- 即使攻擊者獲得 AGFS 磁碟訪問許可權，也無法讀取任何客戶的明文資料
- 不同帳戶的資料使用獨立金鑰加密，實現租戶隔離
- 所有加密解密操作集中在 VikingFS 層，AGFS 和外部物件儲存只看到密文

### 對誰透明

加密功能對使用者和開發者完全透明：

- **客戶端 API 無變化**：現有程式碼無需修改
- **應用層無感知**：讀寫操作與未加密時完全相同
- **向後相容**：未加密的舊檔案仍可正常讀取

## 三層金鑰架構

Business Data Platform 採用信封加密（Envelope Encryption）架構，使用三層金鑰體系：

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Root Key（根金鑰）                          │
│  • 整個 Business Data Platform 例項全域唯一                       │
│  • 儲存：KMS 服務 / ~/.openviking/master.key         │
│  • 用途：派生所有帳戶金鑰                              │
└────────────────────┬────────────────────────────────────┘
                     │ HKDF 派生
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 2: Account Key（帳戶金鑰，KEK）                │
│  • 每個帳戶一個獨立金鑰                                │
│  • 不儲存，執行時派生                                  │
│  • 用途：加密該帳戶下的所有檔案金鑰                    │
└────────────────────┬────────────────────────────────────┘
                     │ AES-256-GCM 加密
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 3: File Key（檔案金鑰，DEK）                   │
│  • 每次寫操作生成新的隨機金鑰                          │
│  • 加密後儲存在檔案頭（信封）中                        │
│  • 用途：加密實際檔案內容                              │
└─────────────────────────────────────────────────────────┘
```

### 金鑰層次說明

| 層級 | 名稱 | 說明 | 數量 |
|------|------|------|------|
| **Root Key** | 根金鑰 | 整個系統的主金鑰，用於派生所有帳戶金鑰 | 1 個例項 |
| **Account Key** | 帳戶金鑰 | 每個帳戶獨立的金鑰，從根金鑰派生 | 每個帳戶 1 個 |
| **File Key** | 檔案金鑰 | 每個檔案的一次性隨機金鑰 | 每次寫入 1 個 |

## 金鑰提供程式

Business Data Platform 支援三種金鑰提供程式，適應不同的部署場景：

| 提供程式 | 適用場景 | Root Key 儲存 | 特點 |
|---------|---------|--------------|------|
| **Local** | 開發環境、單節點部署 | 本地檔案 `~/.openviking/master.key` | 簡單，無需外部服務 |
| **Vault** | 生產環境、多雲部署 | HashiCorp Vault Transit Engine | 企業級金鑰管理，支援金鑰版本控制 |
| **Volcengine KMS** | 火山引擎雲部署 | 火山引擎 KMS | 雲原生金鑰管理服務 |

### Local（本地文件）

適合開發環境和單節點部署：

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

**初始化命令**：
```bash
ov system crypto init-key --output-file ~/.openviking/master.key
```

### Vault（HashiCorp Vault）

適合生產環境和多雲部署：

```json
{
  "encryption": {
    "enabled": true,
    "provider": "vault",
    "vault": {
      "address": "https://vault.example.com:8200",
      "token": "hvs.your-vault-token",
      "mount_point": "transit",
      "kv_mount_point": "secret",
      "kv_version": 1,
      "root_key_name": "openviking-root-key",
      "encrypted_root_key_key": "openviking-encrypted-root-key"
    }
  }
}
```

### Volcengine KMS（火山引擎）

適合火山引擎雲部署：

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

## 工作原理

### 寫流程

```
客戶端              VikingFS             FileEncryptor        KeyManager        AGFS
  │                   │                       │                    │             │
  │  write(uri, data) │                       │                    │             │
  │──────────────────>│                       │                    │             │
  │                   │  encrypt(account_id,  │                    │             │
  │                   │           plaintext)  │                    │             │
  │                   │──────────────────────>│                    │             │
  │                   │                       │derive_account_key()│             │
  │                   │                       │───────────────────>│             │
  │                   │                       │<───────────────────│             │
  │                   │                       │  account_key       │             │
  │                   │  1. 生成隨機 File Key                        │             │
  │                   │  2. 用 File Key 加密內容                     │             │
  │                   │  3. 用 Account Key 加密 File Key            │             │
  │                   │  4. 構建信封格式                             │             │
  │                   │<──────────────────────│                    │             │
  │                   │  ciphertext           │                    │             │
  │                   │─────────────────────────────────────────────────────────>│
  │                   │                       │                    │  Write      │
  │<──────────────────│                       │                    │             │
  │   success         │                       │                    │             │
```

### 讀流程

```
客戶端              VikingFS             FileEncryptor          KeyManager        AGFS
  │                   │                       │                     │             │
  │  read(uri)        │                       │                     │             │
  │──────────────────>│                       │                     │             │
  │                   │──────────────────────────────────────────────────────────>│
  │                   │                       │                     │  Read       │
  │                   │<──────────────────────────────────────────────────────────│
  │                   │  raw_bytes            │                     │             │
  │                   │  檢查魔術數 == "OVE1"?  │                     │             │
  │                   │  是 → decrypt()       │                      │             │
  │                   │──────────────────────>│                     │             │
  │                   │                       │ derive_account_key()│             │
  │                   │                       │────────────────────>│             │
  │                   │                       │<────────────────────│             │
  │                   │                       │  account_key        │             │
  │                   │  1. 解析信封格式                              │             │
  │                   │  2. 用 Account Key 解密 File Key             │             │
  │                   │  3. 用 File Key 解密內容                      │             │
  │                   │<──────────────────────│                     │             │
  │                   │  plaintext            │                     │             │
  │<──────────────────│                       │                     │             │
  │   content         │                       │                     │             │
```

### 信封格式

加密檔案使用統一的信封格式，以魔術數 `OVE1`（Business Data Platform Encryption v1）開頭：

```
┌─────────────────────────────────────────────────────────────┐
│  魔術數   │  版本    │  Provider   │  加密的 File Key  │  ..   │
│  4 位元組   │  1 位元組  │   1 位元組    │     可變長度       │  ...  │
│  "OVE1"  │   0x01  │  0x01=local │                  │  ...  │
└─────────────────────────────────────────────────────────────┘
```

- 如果檔案不以 `OVE1` 開頭，視為未加密檔案，直接返回明文
- 支援向後相容，舊檔案無需遷移

## 多租戶隔離

不同帳戶的資料使用獨立的 Account Key 加密：

- 帳戶 A 的金鑰無法解密帳戶 B 的檔案
- 即使 AGFS 被完全訪問，沒有對應金鑰也無法讀取資料
- 租戶隔離在金鑰層面實現，不依賴儲存層許可權

## 配置示例

詳細配置說明請參考 [配置文件](../guides/01-configuration.md#encryption)。

## 相關文件

- [儲存架構](./05-storage.md) - VikingFS 和 AGFS 架構
- [配置指南](../guides/01-configuration.md) - 加密配置詳解
- [多租戶](./11-multi-tenant.md) - 帳號、使用者與 Agent 的隔離模型
