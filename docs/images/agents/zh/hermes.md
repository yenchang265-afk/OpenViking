## 步驟1：安裝

1. 在終端執行如下命令，啟動 OpenViking 記憶配置嚮導：

   ```bash
   hermes memory setup openviking
   ```

2. 執行後將出現配置來源選擇介面：

   ```text
   OpenViking config source
     ↑↓ navigate  ENTER/SPACE select  ESC cancel
    → (●) Use existing OpenViking profile - choose from detected ovcli.conf profiles
      (○) Create new OpenViking profile - enter a new URL/API key
   ```

   選項說明：

   - 複用現有 Profile：直接讀取本地已有的 `ovcli.conf` 中的 OpenViking 地址和金鑰，無需重複填寫。
   - 新建 Profile：需手動輸入 OpenViking 服務的訪問 URL 和 API 金鑰，適合首次配置或連線新例項的場景。

3. 若選擇「Create new OpenViking profile」，將出現連線方式選擇，請選擇「OpenViking Service (VolcEngine Cloud)」：

   ```text
   OpenViking connection
     ↑↓ navigate  ENTER/SPACE select  ESC cancel

    → (●) OpenViking Service (VolcEngine Cloud) - use the managed OpenViking endpoint
      (○) Custom - use a local, VPS, or self-hosted OpenViking server
   ```

4. 填入 API KEY：

   ```text
   {{OPENVIKING_API_KEY}}
   ```

5. 填寫「Hermes peer ID in OpenViking」：該欄位為 Hermes 在 OpenViking 中的 Agent 身份標識，用於區分不同 Agent 產生的記憶。可直接按 Enter 使用預設值「hermes」，也可自定義填寫。
6. 選擇配置儲存方式，建議選擇「Mirror to OpenViking store」：

   ```text
   Save OpenViking config
     ↑↓ navigate  ENTER/SPACE select  ESC cancel
      (○) Keep in Hermes only - write values only to Hermes .env
    → (●) Mirror to OpenViking store - write ~/.openviking/ovcli.conf.<name> and link it
   ```

7. 填寫「OpenViking profile name」：Hermes 的多租戶能力可隔離不同 Profile 的模型、記憶、配置及憑據。建議為每個 Hermes Profile 配置獨立的 OpenViking 環境或身份，並在此填寫一個便於識別的本地配置名稱，以區分對應的 OpenViking 配置。該名稱僅用於本地標識，不會建立新使用者，也不會改變帳號身份或許可權。
8. 配置完成後將顯示如下確認資訊：

   ```text
   OpenViking memory is ready
     Created and linked OpenViking profile.
     Config file: ~/.openviking/ovcli.conf.hermes
     Start a new Hermes session to activate.
   ```

## 步驟2：驗證

1. 執行以下命令驗證記憶外掛狀態：

   ```bash
   hermes memory status
   ```

2. 返回如下結果即表示接入成功：

   ```text
   Memory status
   ────────────────────────────────────────
     Built-in (MEMORY.md / USER.md):
       Memory injection:   enabled ✓
       User profile:       enabled ✓
       Memory tool:        enabled ✓
     Provider:  openviking

     openviking config:
       use_ovcli_config: True
       ovcli_config_path: ~/.openviking/ovcli.conf.hermes
       endpoint: `https://api.vikingdb.cn-beijing.volces.com/openviking`
       agent: hermes

     Plugin:    installed ✓
     Status:    available ✓

     Installed plugins:
       • byterover  (API key / local)
       • hindsight  (API key / local)
       • holographic  (local)
       • honcho  (API key / local)
       • mem0  (API key / local)
       • openviking  (API key / local) ← active
       • retaindb  (API key / local)
       • supermemory  (requires API key)
   ```

## 故障排查

| 問題 | 處理 |
|---|---|
| Provider 不是 openviking | 重跑 `hermes memory setup openviking` |
| Status 不是 available | 檢查 API Key |

## 參考

- 手動配置文件：[Hermes](https://docs.openviking.net/zh/agent-integrations/05-hermes)
- 原理說明：[OpenViking memory provider](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers#openviking)
