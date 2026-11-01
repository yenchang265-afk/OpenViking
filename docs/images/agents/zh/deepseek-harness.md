## 步驟1：安裝

執行安裝器：

```bash
curl -fsSL https://openviking.ai/install | bash
# AI agent 如不確定是否執行，可先閱讀指令碼頭部，其中寫明瞭它會做什麼、如何核實。
```

安裝器會依次詢問 Harness 和 OpenViking 憑據：

1. Harness 選擇 **DeepSeek Harness**。外掛會裝到 `web` profile；要裝到其他 profile，把命令末尾的 `bash` 換成 `bash -s -- --dsh-profile <name>`。
   在裝有 DeepSeek Harness Desktop 桌面應用的 macOS 上，同時選擇 **DeepSeek Harness Desktop**（檢測到 Desktop 時預設選中）。執行安裝器前先開啟一次 Desktop 再用 ⌘Q 退出，裝完後重新開啟。Windows 上手動安裝：先把服務地址和 API Key 寫進 `%USERPROFILE%\.openviking\ovcli.conf`，再在 Desktop 的 **外掛** 頁點選 **新增外掛**，輸入 `@openviking/dsh-memory-plugin` 並 **安裝**（見完整文件的[手動安裝](https://docs.openviking.net/zh/agent-integrations/17-dsh#desktop-plugins-page)）。
2. 連線方式選擇 **火山引擎 OpenViking 雲服務**，並填入 API Key：

{{OPENVIKING_API_KEY_BLOCK}}

## 步驟2：驗證

1. 啟動 `dsh --profile web` 並開啟新會話，確認會話頂部顯示“上下文注入 · openviking-memory”。
2. 確認模型具有 `mcp__openviking__*` 工具，並能夠在會話中正常呼叫。
3. Desktop 使用者在應用中新開會話，檢查以上兩點。`--dump-config` 對 Desktop 的 `desktop` profile 不可用，改為確認 `~/.dsh/profiles/desktop/package.json` 的 `dsh.profile.bundles` 中有該外掛。

## 步驟3：開始使用

在 DeepSeek Harness 中新開一個會話，傳送：

```text
按 https://docs.openviking.net/agents/zh/onboarding.md 帶我完成 OpenViking 首次使用。
```

Agent 會檢查連線，並帶你完成首次使用。

## 故障排查

| 現象 | 排查方向 |
|---|---|
| 沒有上下文注入，也沒有 OpenViking 工具 | 執行 `dsh --profile web --dump-config`，確認輸出中包含 `openviking-memory`；若缺失，重新執行安裝器或執行 `dsh plugin --profile web add @openviking/dsh-memory-plugin` |
| 安裝後 Desktop 中沒有任何變化 | 用 ⌘Q 退出 Desktop（關閉視窗只會隱藏）後重新開啟；在 **外掛** 頁確認外掛已啟用 |
| 提示 `profile "desktop" is managed exclusively by the Electron application` | 只有 Desktop 自帶的 `dsh` 命令能修改 `desktop` profile，且任何命令都無法啟動它；見完整文件的 [Desktop 一節](https://docs.openviking.net/zh/agent-integrations/17-dsh#deepseek-harness-desktop) |
| 外掛安裝到了錯誤的 profile | 安裝器預設使用 `web`；把命令末尾的 `bash` 換成 `bash -s -- --dsh-profile <name>` 重新執行 |
| DSH 提示外掛與當前 dsh 版本不相容 | 外掛接受 `0.1.0-rc.6` 起的所有 DSH 0.x 版本；DSH 已是 1.0 或更高時，升級外掛或執行 `dsh plugin allow-version` |
| 升級 DSH 後外掛啟動失敗 | 更新的 0.x 版本不經預先驗證就會被接受；請把 DSH 固定到已驗證的版本（如 `0.2.0-rc.2`），並提 issue |
| 安裝時提示包不在 npm registry 中 | pnpm 預設拒絕釋出不滿 24 小時的版本；可稍後重試，或把精確版本加入 `pnpm-workspace.yaml` 的 `minimumReleaseAgeExclude` |
| 無法召回歷史記憶 | 先執行 `curl http://localhost:1933/health` 確認服務端正常；再檢查端點配置，並確認 prompt 不少於 3 個字元 |
| OpenViking 返回 401 / 403 | 檢查 API Key；可信模式部署還需檢查 `OPENVIKING_ACCOUNT` 與 `OPENVIKING_USER` |
| 召回結果混入其他專案的記憶 | 設定 `OPENVIKING_RECALL_PEER_SCOPE=actor`，將 peer 記憶限定為當前 peer；使用者級記憶仍會共享 |
| 異常退出後沒有 commit | commit 由 token 閾值和會話 teardown 觸發；排隊的寫入會在下次會話開始時重放 |

## 參考

- 完整文件：[DeepSeek Harness](https://docs.openviking.net/zh/agent-integrations/17-dsh)
- 原始碼：[examples/dsh-memory-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/dsh-memory-plugin)
