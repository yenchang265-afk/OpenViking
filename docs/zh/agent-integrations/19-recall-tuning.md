# 調整召回延遲

適用於已完成外掛接入的使用者。首次安裝從[整合選型](01-overview.md)開始。

查詢擴充和召回壓縮都會增加模型呼叫。優先考慮響應速度時，可以關閉這兩項；檢索、預算控制和跨輪去重仍然保留：

```bash
export OPENVIKING_RECALL_QUERY_EXPANSION=off
export OPENVIKING_RECALL_COMPRESS=off
```

也可以在 `~/.openviking/ovcli.conf` 中配置：

```json
{
  "plugin": {
    "recallQueryExpansion": "off",
    "recallCompress": "off"
  }
}
```

### 選擇壓縮方式

| 值 | 行為 |
| --- | --- |
| `off` | 不壓縮召回結果 |
| `server` | 請求 OpenViking 服務端壓縮 |
| `client` | 只用本地壓縮器，適用於 Claude Code 和 Codex |
| `auto` | 有本地壓縮器時優先使用，否則請求服務端自動處理 |

Claude Code 和 Codex 預設使用 `auto`，本地壓縮器分別是 `claude -p` 和 `codex exec`，見[Agent 整合能力：召回摘要](./16-capability-reference.md#_3-2-5-召回再摘要)。其他支援雲端壓縮的整合預設保持 `off`，需要顯式開啟。服務端壓縮適用於 Claude Code、Codex、OpenCode、DSH、pi、Cursor、TRAE、TRAE CN、ZCode、OpenClaw 和 Hermes 外部外掛，要求服務端支援 context-search rewrite。Hermes 內建 provider 不支援召回摘要。

這些設定控制自動召回。模型主動呼叫 MCP `search` 時，使用該次呼叫傳入的引數。完整規則與舊服務端回退行為見[共享外掛說明](https://github.com/volcengine/OpenViking/blob/main/examples/memory-plugin-shared/README.md#cloud-recall-compression)。

共享外掛讀取 `ovcli.conf` 的 `plugin` 段；`plugin.<harness>` 可覆蓋某個客戶端的配置。環境變數優先順序更高；舊變數 `OPENVIKING_RECALL_REWRITE` 仍可作為 `OPENVIKING_RECALL_COMPRESS` 的別名使用，詳見[外掛配置](../configuration/02-client.md#外掛配置)。修改後重啟對應 Agent，使 hook 程序載入新配置。這些都是外掛客戶端配置，不需要修改服務端的 `ov.conf`。

### 請求超時

查詢擴充、檢索和 digest 壓縮依次執行。查詢擴充預設超時為 5 秒（`retrieval.recall_intent_timeout_s`），digest 預設超時為 30 秒（`retrieval.recall_rewrite_timeout_s`）。

`OPENVIKING_RECALL_CONTEXT_TIMEOUT_MS` 或 `plugin.recallContextTimeoutMs` 控制客戶端等待整個 context 請求的上限。未設定時沿用外掛的普通超時；請求帶 session 且未將 query expansion 設為 `off` 時至少 15 秒，請求 digest 時至少 45 秒。自定義值應高於該請求會用到的服務端超時，並低於宿主 hook 的超時；客戶端提前結束會丟失整個響應。
