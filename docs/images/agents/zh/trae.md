## 步驟1：安裝

1. 根據所使用的客戶端，在終端執行對應的安裝命令：

   **Trae 國際版**

   ```bash
   bash <(curl -fsSL https://ovrelease.tos-cn-beijing.volces.com/memory-plugin-shared/install.sh) --harness trae --dist tos
   ```

   **Trae 中國版**

   ```bash
   bash <(curl -fsSL https://ovrelease.tos-cn-beijing.volces.com/memory-plugin-shared/install.sh) --harness trae-cn --dist tos
   ```

   **TraeCode CLI 2.0**

   ```bash
   bash <(curl -fsSL https://ovrelease.tos-cn-beijing.volces.com/memory-plugin-shared/install.sh) --harness trae-cli --dist tos
   ```

2. 安裝器會依次詢問以下資訊：語言（English / 中文）、OpenViking 憑據。在 OpenViking 憑據配置中，選擇連線至「火山引擎 OpenViking 雲服務 [api.vikingdb.cn-beijing.volces.com]」，並填入 API KEY：

   ```text
   {{OPENVIKING_API_KEY}}
   ```

## 步驟2：驗證

**TRAE / TRAE CN**：在「設定 → MCP → 已配置的 MCP Servers」中確認能夠看到 `openviking` 條目即表示接入成功。

**TraeCode CLI 2.0**：Hook 要先信任才會執行。啟動 `trae-cli`，在信任確認上選 **Trust all and continue**：

```text
Hooks need review
6 hooks are new or changed.
Hooks can run outside the sandbox after you trust them.

  1. Review hooks
> 2. Trust all and continue
  3. Continue without trusting (hooks won't run)
```

再執行 `trae-cli plugin list`，確認 `openviking-memory` 已啟用。錯過這個提示，或當時選了第 3 項，Hook 就不會執行：輸入 `/hooks` 補上信任並開啟條目，`/plugins` 裡確認外掛已啟用——兩個開關相互獨立，都要是開著的。外掛更新動了 Hook 時會再要求信任一次。

## 故障排查

| 問題 | 處理 |
|---|---|
| 沒有自動召回 | 完全退出 TRAE，重啟，再建會話 |
| TraeCode CLI 2.0 裝了外掛但不召回 | 啟動時的 Hook 信任被跳過：`/hooks` 裡信任並開啟，`/plugins` 裡確認外掛已啟用 |
| 連線 / 鑑權失敗 | 檢查 `~/.openviking/ovcli.conf`，重啟客戶端 |
| 需要日誌 | `~/.openviking/logs/trae-hooks.log`、`trae-cn-hooks.log` 或 `codex-hooks.log`（TraeCode CLI 2.0） |

## 參考

- 手動配置文件：[TRAE](https://docs.openviking.net/zh/agent-integrations/13-trae)
- 原始碼：[examples/agent-hook-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/agent-hook-plugin)（TRAE / TRAE CN）、[examples/codex-memory-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/codex-memory-plugin)（TraeCode CLI 2.0）
