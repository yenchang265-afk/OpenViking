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

輸入 `ov health` 檢查 ov 的版本和連線狀態
```bash
ov health
```
