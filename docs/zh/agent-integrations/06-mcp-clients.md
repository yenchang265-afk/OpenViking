# MCP 客戶端

任何相容 [MCP](https://modelcontextprotocol.io/) 的客戶端都可以直接連線 OpenViking 內建的 `/mcp` 端點——無需安裝外掛或啟動額外程序。適用於 Cursor、Trae、Manus、Claude Desktop、ChatGPT 等。

## 快速配置

大多數 MCP 客戶端使用標準 `mcpServers` 格式：

```json
{
  "mcpServers": {
    "openviking": {
      "url": "https://your-server.com/mcp",
      "headers": {
        "Authorization": "Bearer your-api-key-here"
      }
    }
  }
}
```

本地服務未配置 `root_api_key` 時（dev 模式）無需認證。

## 各平臺注意事項

### Claude Code

Claude Code 需要額外指定 `"type": "http"`，通過命令列新增：

```bash
claude mcp add --transport http openviking \
  https://your-server.com/mcp \
  --header "Authorization: Bearer your-api-key-here"
```

加 `--scope user` 使配置全局生效。

> 如果你需要免工具呼叫的自動召回與自動捕獲，請使用 [Claude Code 記憶外掛](./02-claude-code.md)。

### Trae / Cursor / ChatGPT

使用上面的標準 `mcpServers` 配置即可——均已通過 API Key 鑑權驗證。

### Codex

Codex 請使用 [Codex 記憶外掛](./04-codex.md)。外掛通過 manifest 提供 stdio MCP 代理，並讓 MCP 與生命週期 hooks 共用同一套憑據配置。

### OpenCode

在 `~/.config/opencode/opencode.json` 中使用 OpenCode 原生 `mcp` 配置：

```json
{
  "mcp": {
    "openviking": {
      "type": "remote",
      "url": "https://your-server.com/mcp",
      "enabled": true,
      "oauth": false,
      "headers": {
        "Authorization": "Bearer your-api-key-here"
      }
    }
  }
}
```

### Claude Desktop / Claude.ai (OAuth)

這些客戶端要求 OAuth 2.1——無法直接傳 API Key。OpenViking 自帶原生 OAuth 2.1 實現，無需外部代理。

如果你已經為 OpenViking 服務配好了 HTTPS，直接連線 `https://your-server.com/mcp` 端點即可——客戶端會自動引導你完成 OAuth 授權流程。

HTTPS 配置、部署模板和完整授權流程詳見 [OAuth 2.1 指南](../guides/11-oauth.md) 和 [公網訪問指南](../guides/12-public-access.md)。

## 可用工具

連線後，OpenViking 會提供檢索、記憶、資源、watch 和檔案系統工具。完整工具清單、引數、漸進式檔案上傳和進階配置見 [MCP 整合指南](../guides/06-mcp-integration.md#可用的-mcp-工具)。

## 故障排查

| 現象 | 修復 |
|------|------|
| 連線被拒絕 | 確認 `openviking-server` 正在執行：`curl http://localhost:1933/health` |
| 認證錯誤 | 確保客戶端配置中的 API Key 與服務端一致。見 [鑑權指南](../guides/04-authentication.md) |

## 參見

- [整合能力參考](./16-capability-reference.md)
- [MCP 整合指南](../guides/06-mcp-integration.md) — 工具引數、漸進式上傳、`OPENVIKING_PUBLIC_BASE_URL`
- [OAuth 2.1 指南](../guides/11-oauth.md) — 用於 Claude Desktop、Claude.ai、Cursor
- [MCP 規範](https://modelcontextprotocol.io/)
