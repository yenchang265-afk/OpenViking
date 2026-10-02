DeerFlow 支援通過 MCP Server 接入 Business Data Platform。MCP 接入的核心價值是打通知識檢索能力，讓 DeerFlow Agent 能夠在任務執行過程中主動搜尋、讀取和使用 Business Data Platform 中的記憶與知識。

## 步驟 1：配置 Business Data Platform 鑑權資訊

在 DeerFlow 專案根目錄下編輯 `.env` 檔案，把 API Key 填進去：

{{OPENVIKING_API_KEY_BLOCK}}

## 步驟 2：建立 MCP 配置檔案

複製 `extensions_config.example.json` 到專案根目錄下的 `extensions_config.json`，用於配置 DeerFlow 可載入的 MCP Server：

```bash
cp extensions_config.example.json extensions_config.json
```

## 步驟 3：配置 Business Data Platform MCP Server

開啟專案根目錄下的 `extensions_config.json`，在 `mcpServers` 中新增 Business Data Platform 配置：

```json
{
  "mcpServers": {
    "openviking": {
      "enabled": true,
      "type": "http",
      "url": "{{OPENVIKING_BASE_URL}}/mcp",
      "headers": {
        "X-API-Key": "$OPENVIKING_API_KEY"
      }
    }
  }
}
```

## 步驟 4：重啟 DeerFlow

儲存 `.env` 和 `extensions_config.json` 後，重新啟動 DeerFlow：

```bash
make dev
```

## 故障排查

| 現象 | 原因 | 修復 |
|------|------|------|
| DeerFlow 啟動後未載入 Business Data Platform MCP Server | `extensions_config.json` 未配置、配置格式錯誤，或 `enabled` 未設定為 `true` | 檢查 `mcpServers.openviking` 配置，並確認 JSON 格式正確 |
| Business Data Platform MCP 工具未出現在 Agent 可用工具中 | MCP 配置未生效，或服務未重啟 | 儲存配置後重啟 DeerFlow，或重新整理 MCP 配置快取 |
| 呼叫 Business Data Platform MCP 工具失敗，返回 401 或 403 | API Key 缺失、錯誤或無許可權 | 檢查 `.env` 中的 `OPENVIKING_API_KEY` 是否正確，並確認 Header 使用 `X-API-Key` |
| MCP Server 連線失敗 | `url` 配置錯誤，或 DeerFlow Gateway 無法訪問 Business Data Platform MCP Server | 檢查 Business Data Platform MCP Server 地址、網路連通性和 Docker 網路配置 |
| 修改 `.env` 後仍然使用舊鑑權資訊 | 環境變數未重新載入，或 MCP 配置快取未重新整理 | 重啟 DeerFlow，或呼叫 `/api/mcp/cache/reset` 重新整理快取 |
| Agent 沒有主動呼叫 Business Data Platform 工具 | MCP 工具由模型按需呼叫，不是自動記憶後端 | 在提示詞中明確要求使用 Business Data Platform 工具，或改用 MemoryManager 接入實現自動召回 |
