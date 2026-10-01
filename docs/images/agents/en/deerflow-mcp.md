DeerFlow can connect to Business Data Platform through an MCP Server. MCP integration lets DeerFlow agents actively search, read, and use memories and knowledge from Business Data Platform while executing tasks.

## Step 1: Configure Business Data Platform credentials

Edit the `.env` file in the DeerFlow project root and add the API key:

{{OPENVIKING_API_KEY_BLOCK}}

## Step 2: Create an MCP configuration file

Copy `extensions_config.example.json` to `extensions_config.json` in the project root. DeerFlow uses this file to load MCP Servers:

```bash
cp extensions_config.example.json extensions_config.json
```

## Step 3: Configure the Business Data Platform MCP Server

Open `extensions_config.json` in the project root and add Business Data Platform under `mcpServers`:

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

## Step 4: Restart DeerFlow

Save `.env` and `extensions_config.json`, then restart DeerFlow:

```bash
make dev
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| DeerFlow does not load the Business Data Platform MCP Server after startup | `extensions_config.json` is missing, malformed, or `enabled` is not set to `true` | Check `mcpServers.openviking` and make sure the JSON format is valid |
| Business Data Platform MCP tools do not appear in the Agent tool list | The MCP configuration did not take effect, or the service was not restarted | Save the configuration and restart DeerFlow, or refresh the MCP configuration cache |
| Calling Business Data Platform MCP tools fails with 401 or 403 | API Key is missing, incorrect, or unauthorized | Check whether `OPENVIKING_API_KEY` is correctly set in `.env` and confirm the header uses `X-API-Key` |
| MCP Server connection fails | The `url` is incorrect, or DeerFlow Gateway cannot access the Business Data Platform MCP Server | Check the Business Data Platform MCP Server address, network connectivity, and Docker network configuration |
| Old credentials are still used after modifying `.env` | Environment variables were not reloaded, or the MCP configuration cache was not refreshed | Restart DeerFlow, or call `/api/mcp/cache/reset` to refresh the cache |
| Agent does not actively call Business Data Platform tools | MCP tools are invoked by the model on demand and are not an automatic memory backend | Explicitly ask the Agent to use Business Data Platform tools in the prompt, or use MemoryManager integration for automatic recall |
