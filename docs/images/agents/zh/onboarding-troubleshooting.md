# OpenViking 接入引導：故障排查（給 Agent 看）

[接入引導](https://docs.openviking.net/agents/zh/onboarding.md)裡的命令失敗時查這一頁。找到對應現象，修好後重試一次；仍然失敗，就告訴使用者哪一步沒成、影響什麼、他可以怎麼處理。

| 現象 | 處理 |
|---|---|
| `服務拒絕了該 API key（HTTP 401/403）` 或 `該服務需要 API key`（英文 `The server rejected the API key`、`The server requires an API key`） | key 錯誤、已失效，或屬於其他帳號。請使用者到 OpenViking 控制台（使用者管理 → API Key）重新複製 key，在他自己的終端裡用新的 `--api-key` 重跑安裝命令。自部署服務要用 user key，root key 不能讀寫記憶。 |
| `無法連線 <url>`（英文 `Cannot reach`） | 執行 `curl -sS -o /dev/null -w '%{http_code}\n' <url>/health`。只要返回 HTTP 狀態碼（包括 401），服務就是可達的。超時或連線錯誤說明被代理、VPN 或防火牆擋住了，請使用者處理。 |
| 當前宿主出現 `未找到 … CLI，跳過：<命令>`（英文 `CLI not found; skipping`，例如 `未找到 Codex 格式 CLI，跳過：codex`） | 安裝器所在的 shell 找不到這個宿主的命令，常見原因是 `PATH` 只在互動式 shell 裡設定。請使用者在自己的終端裡（能直接執行該命令的地方）執行他原始訊息中的安裝命令，然後從步驟 1 繼續。不要把命令貼回給使用者，命令裡有 key。 |
| 沒有 Node.js，或版本低於 18（pi 需要 22.19 及以上） | 請使用者安裝或升級 Node.js，然後重跑安裝器。 |
| 沙箱攔截了聯網或寫入主目錄 | 請使用者批准在沙箱外執行。不要繞過沙箱。 |
| Codex 裡 `curl` 返回退出碼 7 或 6 | 多半是沙箱攔住了聯網，不是網站掛了。申請在沙箱外執行這條命令。 |
| 宿主拒絕執行 `curl … \| bash` | 請使用者在自己的終端裡執行他原始訊息中的安裝命令，然後從步驟 1 繼續。不要把命令貼回給使用者，命令裡有 key。 |
| 當前宿主不在 `完成` 裡，`未完成` 裡也沒提到它 | 安裝器沒檢測到當前宿主。只為它重跑一次，`<值>` 取接入引導附錄 A 的 `--harness` 列：`curl -fsSL https://openviking.ai/install \| bash -s -- --yes --harness <值>,cli`。已儲存的連線會保留，不用再帶 key。然後從步驟 1 繼續。 |
| Windows | 安裝器只支援 macOS 和 Linux。告訴使用者後停止。 |
| docs.openviking.net 打不開 | 換成 docs.openviking.ai，路徑不變。安裝器本身會自動嘗試兩個站點。 |
| 找不到 `ov` 命令 | 用 `--yes --harness cli` 重跑安裝器，已儲存的連線會保留。`ov` 已安裝但不在 `PATH` 裡時，把 `$(npm prefix -g)/bin` 加進 `PATH`；安裝器回退到 `~/.local` 時則是 `~/.local/bin`。 |
| `ov` 提示需要先設定顯示語言 | 執行 `ov language zh-CN`（或 `ov language en`）。 |
| DeepSeek Harness：`dsh plugin add` 失敗 | 安裝 pnpm（`npm i -g pnpm`），再用 `--harness dsh` 重跑安裝器。 |
| `安裝校驗失敗`（英文 `Installation validation failed`） | 重跑當前宿主的安裝。仍然失敗，把失敗的檢查項告訴使用者。 |
| 匯入指令碼提示 `not supported yet` | 指令碼不能直接讀這個宿主的歷史，按[其他宿主：把會話轉成 JSONL](https://docs.openviking.net/agents/zh/onboarding-other-hosts.md)轉換後用 `--input` 匯入。 |
| 匯入指令碼提示 `--session: no session matches …` | 給的 id 不對，什麼都沒有上傳。重新執行 `--list`，用它列印的 id。 |
| 重啟後沒有召回 | 先分清是庫裡沒有相關內容，還是 hook 沒執行。Codex 和 TraeCode CLI：在 `/hooks` 裡信任 OpenViking 的 hook，在 `/plugins` 裡確認 `openviking-memory` 已啟用。Cursor 和 TRAE：應用沒有完全退出。其他情況執行診斷：Claude Code 用 `/openviking-memory:ov` 或 `ov-memory-doctor` skill；Codex 用 `$ov-memory-doctor` skill；Cursor、TRAE、TRAE CN、ZCode 執行 `node ~/.openviking/agent-integrations/<cursor\|trae\|trae-cn\|zcode>/scripts/ov-memory-doctor.mjs`；pi 用 `/viking`；DeepSeek Harness 執行 `dsh --profile <profile> --dump-config`（`<profile>` 是安裝器輸出的那個），輸出裡應包含 `openviking-memory`。命令列宿主還可以在啟動前設定 `OPENVIKING_DEBUG=1`，hook 日誌會寫到 `~/.openviking/logs/`；從程式塢或啟動器開啟的桌面應用讀不到 shell 裡設定的環境變數。 |
