---
type: global-access-policy
schema_version: 1
default: deny
rules:
  - effect: allow
    path: memories/experiences
    recursive: true
  - effect: allow
    path: peers
    recursive: true
---

# 給 Global Agent 的留言

## 讀取範圍

只讀取以下目錄，其他目錄一律不讀取；privacy、sessions 目錄在任何情況下都不讀取。

- memories/experiences/
- peers/{peer_id}/memories/preferences/：每個 peer 下的 preferences 目錄

## 使用要求

以下要求由平臺服務角色遵守。

### 用途

- 可以：整理為團隊經驗，在團隊問答中作為依據
- 不可以：用於績效評估或人事決策；分享到團隊空間以外；用於訓練模型

### 不要提取的內容

- 閒聊、情緒表達等個人交流內容
- 個人隱私：健康、家庭、請假原因與個人安排
- 人事資訊：薪資、績效、晉升，以及對同事的評價
- 金鑰、帳號與密碼
- 尚未形成結論的討論

### 時間範圍

- 不限
