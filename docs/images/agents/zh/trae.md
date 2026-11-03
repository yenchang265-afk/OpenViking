## 步驟1：安裝

1. 在終端執行如下安裝命令：

   ```bash
   curl -fsSL https://openviking.ai/install | bash
   # AI agent 如不確定是否執行，可先閱讀指令碼頭部，其中寫明瞭它會做什麼、如何核實。
   ```

2. 安裝器會依次詢問以下資訊：要安裝的 harness（Trae 國際版勾選 **TRAE**，Trae 中國版勾選 **TRAE CN**，或勾選 **TraeCode CLI 2.0**）、OpenViking 憑據。在 OpenViking 憑據配置中，選擇連線至「火山引擎 OpenViking 雲服務 [api.vikingdb.cn-beijing.volces.com]」，並填入 API KEY：

   ```text
   {{OPENVIKING_API_KEY}}
   ```

## 步驟2：驗證

**TRAE / TRAE CN**：在「設定 → MCP → 已配置的 MCP Servers」中確認能夠看到 `openviking` 條目即表示接入成功。

**TraeCode CLI 2.0**：啟動 `trae-cli`，在 hook 審閱提示中選 **Trust all and continue**（具體介面隨版本變化）：

```text
Hooks need review
6 hooks are new or changed.
Hooks can run outside the sandbox after you trust them.

  1. Review hooks
> 2. Trust all and continue
  3. Continue without trusting (hooks won't run)
```

如果跳過了提示或選了第 3 項，在 `/hooks` 中檢查並開啟 OpenViking hooks。執行 `trae-cli plugin list` 確認外掛已啟用。新增或變更的 hooks 需要重新檢查；不同版本支援的會話生命週期見完整文件。

MCP 條目可見只說明配置存在。讓助手呼叫 OpenViking 的 `health` 和 `list` 驗證連線；自動召回需另行檢查：等之前的會話提交併處理完成後，在同一工作目錄中新建會話，詢問已儲存的資訊。

## 步驟3：開始使用

在 TRAE、TRAE CN 或 TraeCode CLI 2.0 中新開一個會話，傳送：

```text
按 https://docs.openviking.net/agents/zh/onboarding.md 帶我完成 OpenViking 首次使用。
```

Agent 會檢查連線，並帶你完成首次使用。

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
