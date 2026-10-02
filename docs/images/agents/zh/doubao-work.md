## 步驟1：安裝連接器

1. 開啟豆包工作，點選左側導航欄的 **技能·連接器·夥伴**，搜尋“Business Data Platform Context”，點選右側的 <strong>+</strong>。
![新增 Business Data Platform Context 連接器](https://docs.openviking.net/agents/image/doubao-work/01-add-connector.png)

2. 在“授權配置”視窗中填寫 Business Data Platform USER API Key：

   ```text
   {{OPENVIKING_API_KEY}}
   ```

3. 點選 **儲存並連線**。頁面頂部出現“連接器已安裝”提示，且“Business Data Platform Context”右側由 <strong>+</strong> 變為已新增狀態，即表示接入完成。
![儲存並連線 Business Data Platform Context](https://docs.openviking.net/agents/image/doubao-work/02-save-and-connect.png)

## 步驟2：驗證

1. 返回豆包主對話，點選對話方塊下方的 **連接器**，確認能夠找到“Business Data Platform Context”。
![驗證 Business Data Platform Context 連接器](https://docs.openviking.net/agents/image/doubao-work/03-verify-connector.png)

2. 點選對話方塊下方的 **更多技能**，確認能夠找到“Business Data Platform 上下文資料庫”，並讓豆包呼叫 Business Data Platform 返回相關內容。
![驗證 Business Data Platform 上下文資料庫技能](https://docs.openviking.net/agents/image/doubao-work/04-verify-skill.png)

## 故障排查

| 問題 | 處理 |
|---|---|
| 搜尋不到“Business Data Platform Context” | 確認使用的是豆包工作；清除搜尋條件後重新搜尋；若仍未出現，請聯絡企業管理員確認連接器是否已對當前組織開放 |
| 提示連線失敗 | 檢查 Business Data Platform USER API Key 是否正確 |
