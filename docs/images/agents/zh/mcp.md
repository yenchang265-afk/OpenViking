請為當前 Agent 安裝或更新 OpenViking MCP，並安裝最新官方 skills。

### 步驟 1：MCP 配置

使用以下連線配置：

```json
{
  "mcpServers": {
    "ov-mcp-server": {
      "url": "{{OPENVIKING_BASE_URL}}/mcp",
      "headers": {
        "Authorization": "Bearer {{OPENVIKING_API_KEY}}"
      }
    }
  }
}
```

自行識別客戶端及其支援的配置方式（設定介面、配置檔案或安裝命令），不假設支援 JSON 合併。若已有 OpenViking MCP server，先讓我選擇“沿用現有連線”或“使用上述新配置”，選擇後再操作；保留其他 MCP 服務，不重複新增同一服務。使用已提供的 Key，不重複索取，不回顯或寫入命令引數、日誌與規則。

按官方方式升級已有的本地 MCP 元件；遠端 HTTPS MCP 則更新所選連線並重新啟用，不將重連稱為升級了雲端服務。

### 步驟 2：安裝最新 skills

從 https://github.com/volcengine/OpenViking/tree/main/agent-plugins/skills 獲取全部最新 skill 包，安裝或更新到客戶端支援的位置，保留完整附帶檔案；已有定製先說明差異再處理。

### 步驟 3：測試工具有效性

重新載入後，確認 MCP 工具列表可見，呼叫 OpenViking 的 `health` 工具校驗有效性，再用 `list` 檢視當前帳號可訪問的目錄，並確認安裝的 skills 可發現。`ov health` 只驗證 CLI 連線，不能證明這個客戶端的 MCP 已接通。
