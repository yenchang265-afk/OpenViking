## 💬 聊天應用

通過 Telegram、Discord、WhatsApp、Mochat、釘釘、Slack、郵件或 QQ 與您的 vikingbot 對話 —— 隨時隨地。

| 渠道 | 設定難度 |
|---------|-------|
| **Telegram** | 簡單（只需一個令牌） |
| **Discord** | 簡單（機器人令牌 + 許可權） |
| **WhatsApp** | 中等（掃描二維碼） |
| **Mochat** | 中等（claw 令牌 + websocket） |
| **釘釘** | 中等（應用憑證） |
| **Slack** | 中等（機器人 + 應用令牌） |
| **郵件** | 中等（IMAP/SMTP 憑證） |
| **QQ** | 簡單（應用憑證） |

渠道配置位於 `~/.openviking/ov.conf` 的 `bot.channels`。下面的 Telegram 示例展示完整外層結構；後續片段中的 `channels` 欄位都應合併到同一個 `bot` 物件中。

<details>
<summary><b>Telegram</b>（推薦）</summary>

**1. 建立機器人**
- 開啟 Telegram，搜尋 `@BotFather`
- 傳送 `/newbot`，按照提示操作
- 複製令牌

**2. 配置**

```json
{
  "bot": {
    "channels": [
      {
        "type": "telegram",
        "enabled": true,
        "token": "YOUR_BOT_TOKEN",
        "allowFrom": ["YOUR_USER_ID"]
      }
    ]
  }
}
```

> 您可以在 Telegram 設定中找到您的 **使用者 ID**。它顯示為 `@yourUserId`。
> 複製這個值**不帶 `@` 符號**並貼上到配置檔案中。


**3. 執行**

```bash
vikingbot gateway
```

</details>

<details>
<summary><b>Mochat (Claw IM)</b></summary>

預設使用 **Socket.IO WebSocket**，並帶有 HTTP 輪詢回退。

**1. 讓 vikingbot 為您設定 Mochat**

只需向 vikingbot 傳送此訊息（將 `xxx@xxx` 替換為您的真實郵箱）：

```
Read https://raw.githubusercontent.com/HKUDS/MoChat/refs/heads/main/skills/vikingbot/skill.md and register on MoChat. My Email account is xxx@xxx Bind me as your owner and DM me on MoChat.
```

註冊後，請將返回的渠道設定新增到 `~/.openviking/ov.conf` 的 `bot.channels`，然後連線 Mochat。

**2. 重啟閘道器**

```bash
vikingbot gateway
```

就這麼簡單 —— vikingbot 處理剩下的一切！

<br>

<details>
<summary>手動配置（進階）</summary>

如果您更喜歡手動配置，請將下面的 `channels` 欄位合併到 `~/.openviking/ov.conf` 的 `bot` 物件：

> 請保密 `claw_token`。它只應在 `X-Claw-Token` 頭中傳送到您的 Mochat API 端點。

```json
{
  "channels": [
    {
      "type": "mochat",
      "enabled": true,
      "base_url": "https://mochat.io",
      "socket_url": "https://mochat.io",
      "socket_path": "/socket.io",
      "claw_token": "claw_xxx",
      "agent_user_id": "6982abcdef",
      "sessions": ["*"],
      "panels": ["*"],
      "reply_delay_mode": "non-mention",
      "reply_delay_ms": 120000
    }
  ]
}
```


</details>

</details>

<details>
<summary><b>Discord</b></summary>

**1. 建立機器人**
- 訪問 https://discord.com/developers/applications
- 建立應用 → 機器人 → 新增機器人
- 複製機器人令牌

**2. 啟用意圖**
- 在機器人設定中，啟用 **MESSAGE CONTENT INTENT**
- （可選）如果您計劃使用基於成員資料的允許列表，啟用 **SERVER MEMBERS INTENT**

**3. 獲取您的使用者 ID**
- Discord 設定 → 進階 → 啟用 **開發者模式**
- 右鍵點選您的頭像 → **複製使用者 ID**

**4. 配置**

```json
{
  "channels": [
    {
      "type": "discord",
      "enabled": true,
      "token": "YOUR_BOT_TOKEN",
      "allowFrom": ["YOUR_USER_ID"]
    }
  ]
}
```

**5. 邀請機器人**
- OAuth2 → URL 生成器
- 範圍：`bot`
- 機器人許可權：`傳送訊息`、`讀取訊息歷史`
- 開啟生成的邀請 URL 並將機器人新增到您的伺服器

**6. 執行**

```bash
vikingbot gateway
```

</details>

<details>
<summary><b>WhatsApp</b></summary>

需要 **Node.js ≥18**。

**1. 連結裝置**

```bash
vikingbot channels login
# 使用 WhatsApp 掃描二維碼 → 設定 → 連結裝置
```

**2. 配置**

```json
{
  "channels": [
    {
      "type": "whatsapp",
      "enabled": true,
      "allowFrom": ["+1234567890"]
    }
  ]
}
```

**3. 執行**（兩個終端）

```bash
# 終端 1
vikingbot channels login

# 終端 2
vikingbot gateway
```

</details>

<details>
<summary><b>QQ（QQ單聊）</b></summary>

使用 **botpy SDK** 配合 WebSocket —— 不需要公網 IP。目前僅支援 **私聊**。

**1. 註冊並建立機器人**
- 訪問 [QQ 開放平臺](https://q.qq.com) → 註冊為開發者（個人或企業）
- 建立新的機器人應用
- 進入 **開發設定** → 複製 **AppID** 和 **AppSecret**

**2. 設定沙箱測試環境**
- 在機器人管理控制台中，找到 **沙箱配置**
- 在 **在訊息列表配置** 下，點選 **新增成員** 並新增您自己的 QQ 號
- 新增完成後，用手機 QQ 掃描機器人的二維碼 → 開啟機器人資料卡 → 點選「發訊息」開始聊天

**3. 配置**

> - `allowFrom`：留空以供公開訪問，或新增使用者 openid 以限制。您可以在使用者向機器人發訊息時在 vikingbot 日誌中找到 openid。
> - 生產環境：在機器人控制台提交稽核併發布。檢視 [QQ 機器人文件](https://bot.q.qq.com/wiki/) 瞭解完整發布流程。

```json
{
  "channels": [
    {
      "type": "qq",
      "enabled": true,
      "appId": "YOUR_APP_ID",
      "secret": "YOUR_APP_SECRET",
      "allowFrom": []
    }
  ]
}
```

**4. 執行**

```bash
vikingbot gateway
```

現在從 QQ 向機器人傳送訊息 —— 它應該會回覆！

</details>

<details>
<summary><b>釘釘</b></summary>

使用 **流模式** —— 不需要公網 IP。

**1. 建立釘釘機器人**
- 訪問 [釘釘開放平臺](https://open-dev.dingtalk.com/)
- 建立新應用 -> 新增 **機器人** 功能
- **配置**：
  - 開啟 **流模式**
- **許可權**：添加發送訊息所需的許可權
- 從「憑證」獲取 **AppKey**（客戶端 ID）和 **AppSecret**（客戶端金鑰）
- 釋出應用

**2. 配置**

```json
{
  "channels": [
    {
      "type": "dingtalk",
      "enabled": true,
      "clientId": "YOUR_APP_KEY",
      "clientSecret": "YOUR_APP_SECRET",
      "allowFrom": []
    }
  ]
}
```

> `allowFrom`：留空以允許所有使用者，或新增 `["staffId"]` 以限制訪問。

**3. 執行**

```bash
vikingbot gateway
```

</details>

<details>
<summary><b>Slack</b></summary>

使用 **Socket 模式** —— 不需要公網 URL。

**1. 建立 Slack 應用**
- 訪問 [Slack API](https://api.slack.com/apps) → **建立新應用** →「從零開始」
- 選擇名稱並選擇您的工作區

**2. 配置應用**
- **Socket 模式**：開啟 → 生成一個具有 `connections:write` 範圍的 **應用級令牌** → 複製它（`xapp-...`）
- **OAuth 與許可權**：新增機器人範圍：`chat:write`、`reactions:write`、`app_mentions:read`
- **事件訂閱**：開啟 → 訂閱機器人事件：`message.im`、`message.channels`、`app_mention` → 儲存更改
- **應用主頁**：滾動到 **顯示標籤頁** → 啟用 **訊息標籤頁** → 勾選 **"允許使用者從訊息標籤頁傳送斜槓命令和訊息"**
- **安裝應用**：點選 **安裝到工作區** → 授權 → 複製 **機器人令牌**（`xoxb-...`）

**3. 配置 vikingbot**

```json
{
  "channels": [
    {
      "type": "slack",
      "enabled": true,
      "botToken": "xoxb-...",
      "appToken": "xapp-...",
      "groupPolicy": "mention"
    }
  ]
}
```

**4. 執行**

```bash
vikingbot gateway
```

直接向機器人傳送私信或在頻道中 @提及它 —— 它應該會回覆！

> [!TIP]
> - `groupPolicy`：`"mention"`（預設 —— 僅在 @提及時回覆）、`"open"`（回覆所有頻道訊息）或 `"allowlist"`（限制到特定頻道）。
> - 私信策略預設為開放。設定 `"dm": {"enabled": false}` 以停用私信。

</details>

<details>
<summary><b>郵件</b></summary>

給 vikingbot 一個自己的郵箱帳戶。它通過 **IMAP** 輪詢收件箱並通過 **SMTP** 回覆 —— 就像一個個人郵件助手。

**1. 獲取憑證（Gmail 示例）**
- 為您的機器人建立一個專用的 Gmail 帳戶（例如 `my-vikingbot@gmail.com`）
- 啟用兩步驗證 → 建立 [應用密碼](https://myaccount.google.com/apppasswords)
- 將此應用密碼用於 IMAP 和 SMTP

**2. 配置**

> - `consentGranted` 必須為 `true` 以允許郵箱訪問。這是一個安全門 —— 設定為 `false` 以完全停用。
> - `allowFrom`：留空以接受來自任何人的郵件，或限制到特定發件人。
> - `smtpUseTls` 和 `smtpUseSsl` 分別預設為 `true` / `false`，這對 Gmail（埠 587 + STARTTLS）是正確的。無需顯式設定它們。
> - 如果您只想讀取/分析郵件而不傳送自動回覆，請設定 `"autoReplyEnabled": false`。

```json
{
  "channels": [
    {
      "type": "email",
      "enabled": true,
      "consentGranted": true,
      "imapHost": "imap.gmail.com",
      "imapPort": 993,
      "imapUsername": "my-vikingbot@gmail.com",
      "imapPassword": "your-app-password",
      "smtpHost": "smtp.gmail.com",
      "smtpPort": 587,
      "smtpUsername": "my-vikingbot@gmail.com",
      "smtpPassword": "your-app-password",
      "fromAddress": "my-vikingbot@gmail.com",
      "allowFrom": ["your-real-email@gmail.com"]
    }
  ]
}
```


**3. 執行**

```bash
vikingbot gateway
```

</details>
