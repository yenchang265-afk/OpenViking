## 步驟1：配置 MCP

1. 開啟 WorkBuddy，點選左側導航欄的 **專家·技能·連接器**，進入 **連接器** 標籤頁。
![開啟 WorkBuddy 連接器](https://docs.openviking.net/agents/image/workbuddy/01-open-connectors.webp)

2. 點選右上角的 **自定義連接器**，進入 MCP 服務管理面板。
![開啟自定義連接器](https://docs.openviking.net/agents/image/workbuddy/02-custom-connector.webp)

3. 點選 **配置 MCP**，進入 MCP 配置編輯器。
![進入 MCP 配置編輯器](https://docs.openviking.net/agents/image/workbuddy/03-configure-mcp.webp)

4. 在配置檔案中填入以下內容：

   ```json
   {
     "mcpServers": {
       "OpenViking": {
         "url": "https://api.vikingdb.cn-beijing.volces.com/openviking/mcp",
         "headers": {
           "Authorization": "Bearer {{OPENVIKING_API_KEY}}"
         }
      }
     }
   }
   ```

5. 點選右上角的 **儲存**。頂部出現“配置儲存成功”的綠色提示後，配置即已儲存。
![保存 MCP 配置](https://docs.openviking.net/agents/image/workbuddy/04-save-config.webp)

6. 返回 MCP 列表。如果系統提示“首次連線此 MCP 服務需要您的信任確認”，點選 **信任** 完成接入。
![信任 OpenViking MCP 服務](https://docs.openviking.net/agents/image/workbuddy/05-trust-server.webp)

## 步驟2：驗證

返回 MCP 列表頁，確認 `OpenViking` 出現在“我的 MCP”中、狀態為開啟，展開後可看到已啟用工具。

![驗證 OpenViking MCP 工具](https://docs.openviking.net/agents/image/workbuddy/06-verify-tools.webp)

## 故障排查

| 問題 | 處理 |
|---|---|
| MCP 列表中未出現 `OpenViking` | 檢查 JSON 配置格式並重新儲存 |
| MCP 連線狀態異常 | 重新整理連線；若仍異常，檢查 JSON 配置及網路連通性 |
