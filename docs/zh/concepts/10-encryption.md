# 資料加密

<script setup>
import EncryptionFlowDiagram from '../../.vitepress/theme/components/EncryptionFlowDiagram.vue'
</script>

OpenViking 支援靜態資料加密，在寫入儲存前加密檔案，並在授權讀取時解密。不同 account 使用獨立的帳戶金鑰。

## 概述

### 為什麼需要加密

多個 account 可以共用 AGFS。啟用加密後：

- 已加密檔案需要對應金鑰才能解密；金鑰應與資料分開保護
- 不同帳戶的資料使用獨立金鑰加密，實現租戶隔離
- 執行時由 RAGFS 的加密包裝層處理檔案讀寫；每個後端的加密範圍取決於配置

### 對誰透明

啟用加密不改變客戶端 API：

- **客戶端 API 無變化**：現有程式碼無需修改
- **返回明文**：授權讀取仍返回解密後的內容；金鑰不可用或密文校驗失敗時，讀寫會報錯
- **相容舊檔案**：未加密的舊檔案仍可讀取；開啟加密不會自動加密已有檔案

## 三層金鑰架構

OpenViking 採用信封加密（Envelope Encryption）架構，使用三層金鑰體系：

<KeyHierarchyDiagram />

### 金鑰層次說明

| 層級 | 名稱 | 說明 | 數量 |
|------|------|------|------|
| **Root Key** | 根金鑰 | 整個系統的主金鑰，用於派生所有帳戶金鑰 | 1 個例項 |
| **Account Key** | 帳戶金鑰 | 每個帳戶獨立的金鑰，從根金鑰派生 | 每個帳戶 1 個 |
| **File Key** | 檔案金鑰 | 每個檔案的一次性隨機金鑰 | 每次寫入 1 個 |

## 金鑰提供程式

OpenViking 支援三種金鑰提供程式，適應不同的部署場景：

| 提供程式 | 適用場景 | Root Key 儲存 | 特點 |
|---------|---------|--------------|------|
| **Local** | 開發環境、單節點部署 | 本地檔案 `~/.openviking/master.key` | 簡單，無需外部服務 |
| **Vault** | 生產環境、多雲部署 | 經 Transit 加密後存入 Vault KV | 由 Vault 保護根金鑰 |
| **Volcengine KMS** | 火山引擎雲部署 | 經 KMS 加密後存入本地 `key_file` | 由 KMS 保護根金鑰 |

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

執行時在啟動階段取得根金鑰，再由 RAGFS `EncryptionWrappedFS` 處理受保護後端的檔案內容。Python 的金鑰提供程式負責載入或解封根金鑰；每次檔案讀寫不需要到 KMS 派生帳戶金鑰。

### 寫流程

<EncryptionFlowDiagram mode="write" />

1. 用根金鑰和 `account_id` 經 HKDF-SHA256 派生帳戶金鑰（可在執行時快取）。
2. 為這次加密生成隨機 File Key 和 nonce。
3. 用 File Key 對內容執行 AES-256-GCM 加密，再用帳戶金鑰加密 File Key。
4. 將信封頭、加密後的 File Key、nonce 和內容密文寫入後端。

### 讀流程

<EncryptionFlowDiagram mode="read" />

讀取加密檔案時，先用帳戶金鑰解封 File Key，再校驗並解密內容。沒有 `OVE1` 標記的舊檔案按明文讀取。金鑰錯誤或密文認證失敗會報錯，不會返回解密結果。

### 信封格式

加密檔案使用統一的信封格式，以魔術數 `OVE1`（OpenViking Encryption v1）開頭：

| 欄位 | 長度 | 取值 |
| --- | --- | --- |
| Magic | 4 位元組 | `OVE1` |
| Version | 1 位元組 | `0x01` |
| Provider | 1 位元組 | `0x01` = local |
| Encrypted File Key | 可變 | 用帳戶金鑰封裝的 File Key |
| … | | nonce 和內容密文 |

- 如果檔案不以 `OVE1` 開頭，視為未加密檔案，直接返回明文
- 舊檔案可繼續讀取；需要保護存量明文時，必須另行遷移或重寫

## 多租戶隔離

不同帳戶的資料使用獨立的 Account Key 加密：

- 帳戶 A 的金鑰無法解密帳戶 B 的檔案
- 對已經加密的檔案，僅取得後端密文仍需要對應金鑰才能解密
- 獨立金鑰補充租戶訪問控制，不能代替身份認證和儲存許可權管理

## 加密範圍

這裡保護的是啟用了加密的檔案後端。它不自動加密獨立向量庫、日誌或匯出的 OVPack；向量記錄可能包含摘要和記憶正文。主備儲存的 backup 可單獨關閉加密，部署時需要逐個檢查後端配置。

## 配置示例

詳細配置說明請參考 [配置文件](../guides/01-configuration.md#encryption)。

## 相關文件

- [儲存架構](./05-storage.md) - VikingFS 和 AGFS 架構
- [配置指南](../guides/01-configuration.md) - 加密配置詳解
- [多租戶](./11-multi-tenant.md) - 帳號、使用者與 Agent 的隔離模型
