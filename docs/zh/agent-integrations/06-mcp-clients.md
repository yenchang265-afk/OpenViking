# MCP 客戶端

支援 [MCP](https://modelcontextprotocol.io/) Streamable HTTP 的客戶端可直接連線 OpenViking 的 `/mcp` 端點。僅支援 stdio 的客戶端可使用 [Agent Plugins 包](./15-agent-plugins.md)中的代理。

## 快速配置

以下示例適用於接受 `mcpServers` 和自定義請求頭的客戶端。其他客戶端按下方對應說明配置：

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

服務執行在 `dev` 模式時無需認證，應僅監聽本機迴環地址。認證模式下，即使從本機訪問也需要憑據。

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

### Trae / Cursor

在客戶端的 MCP 配置中新增上述服務 URL 和 API Key。

### ChatGPT

通過開發者模式建立自定義 App，再完成 OAuth 授權，見 [OAuth 指南](../guides/11-oauth.md#chatgpt-codex-plus-enterprise)。

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

託管的遠端連接器流程使用 OpenViking 原生 OAuth；在授權頁填寫已有的 OpenViking User/Admin Key。Claude Desktop 的本地 stdio 配置是另一種接入方式。

在服務端啟用 `oauth.enabled` 並配置 HTTPS 後，讓客戶端連線 `https://your-server.com/mcp`，在瀏覽器中完成授權。

HTTPS 配置、部署模板和完整授權流程詳見 [OAuth 2.1 指南](../guides/11-oauth.md) 和 [公網訪問指南](../guides/12-public-access.md)。

## 可用工具

連線後，OpenViking 會提供檢索、記憶、資源、watch 和檔案系統工具。完整工具清單、引數、漸進式檔案上傳和進階配置見 [MCP 整合指南](../guides/06-mcp-integration.md#可用的-mcp-工具)。

## 故障排查

| 現象 | 修復 |
|------|------|
| 連線被拒絕 | 確認 `openviking-server` 正在執行：`curl http://localhost:1933/health` |
| 認證錯誤 | 檢查客戶端是否使用有效的 user/admin key。見 [鑑權指南](../guides/04-authentication.md) |

## 參見

- [整合能力參考](./16-capability-reference.md)
- [MCP 整合指南](../guides/06-mcp-integration.md) — 工具引數、漸進式上傳、`OPENVIKING_PUBLIC_BASE_URL`
- [OAuth 2.1 指南](../guides/11-oauth.md) — 用於 Claude Desktop、Claude.ai、Cursor
- [MCP 規範](https://modelcontextprotocol.io/)
