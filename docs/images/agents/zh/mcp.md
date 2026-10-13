### 步驟 1：MCP 配置

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

### 步驟 2：測試 MCP 工具連通性

重新連線客戶端中的 MCP 服務，確認工具列表可見，再讓助手呼叫 OpenViking 的 `health` 工具。工具呼叫成功後，再用 `list` 檢視當前帳號可訪問的目錄。`ov health` 只驗證 CLI 連線，不能證明這個客戶端的 MCP 已接通。
