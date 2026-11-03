# OpenViking 接入引導：其他宿主的歷史匯入（給 Agent 看）

匯入指令碼只能直接讀 Claude Code 和 Codex 的歷史。在其他宿主上，使用者在[接入引導](https://docs.openviking.net/agents/zh/onboarding.md)步驟 3 選了匯入時，先由你把這個宿主的會話轉成 JSONL，再交給同一個指令碼。範圍選擇、確認和結果說明都和接入引導裡一樣，這一頁只講轉換。

1. 執行 `echo "${TMPDIR:-/tmp}"`，記下這個臨時目錄，下面寫作 `<tmp>`。之後寫檔案、跑命令都用這個絕對路徑，不要再寫 `${TMPDIR:-/tmp}`。下載匯入指令碼：

   ```bash
   curl -fsSL https://docs.openviking.net/dl/memory-plugin-shared/import-history.mjs -o "<tmp>/ov-import-history.mjs"
   ```

2. 找到當前宿主在本機儲存會話的地方。下表是提示，以本機實際為準。只讀，不要改。

   | 宿主 | `--harness` | 會話位置 |
   |---|---|---|
   | TraeCode CLI 2.0 | `trae-cli` | `~/.trae/cli/sessions/`，和 Codex 相同的 rollout 格式 |
   | Kimi Code | `kimicode` | `~/.kimi-code/sessions/`（設定了 `$KIMI_CODE_HOME` 時在該目錄下），每個會話的 `state.json` 帶 cwd，訊息在 `agents/main/wire.jsonl` |
   | OpenCode | `opencode` | SQLite 庫 `~/.local/share/opencode/opencode.db`，沒有 `sqlite3` 時可用 Node 22 的 `node:sqlite` 只讀開啟；`synthetic` 的文本是注入內容，`parent_id` 非空的是子代理會話 |
   | pi | `pi` | `~/.pi/agent/sessions/*/*.jsonl`，每個檔案第一行 `{"type":"session"}` 帶 id 和 cwd |
   | DeepSeek Harness | `dsh` | `~/.dsh/sessions/` |
   | Cursor、TRAE、TRAE CN、ZCode | `cursor`、`trae`、`trae-cn`、`zcode` | 未確認 |

3. 在 `<tmp>` 下寫一個小轉換指令碼，把會話寫進 `<tmp>/ov-sessions.jsonl`，每行一個會話：

   ```json
   {"id": "<宿主自己的會話 id>", "cwd": "<會話所在目錄的絕對路徑>", "messages": [{"role": "user", "text": "……", "created_at": "2026-10-16T08:00:00Z"}, {"role": "assistant", "text": "……", "created_at": "2026-10-16T08:00:05Z"}]}
   ```

   - `id` 用宿主記錄裡的原生會話 id，不要自己生成；`cwd` 用會話實際所在的目錄；每條訊息都帶上 ISO 8601 時間。子代理的會話加上 `"subagent": true`。
   - 只放使用者和助手說的話。工具呼叫、工具輸出、系統提示、思考過程，以及宿主或外掛注入的內容（例如 `<openviking-context>`、提醒、通知）都不要放。
   - 儲存裡的會話全部寫進去，不要按專案、目錄或時間篩選：指令碼會按 `--cwd` 判斷哪些屬於這個專案（包括子目錄），按 `--since` 篩時間，`--list` 和 `--session` 也照常可用。唯一要排除的是當前這段對話，因為它含有安裝命令裡的 key；認不出是哪一段時，排除最近 2 小時內有更新的會話。
   - 不用自己刪 key，指令碼會做；也不要自己去查 JSONL 裡有沒有 key，命令裡不能出現 key 或它的任何一段。轉換指令碼只讀本地檔案、只寫這一個 JSONL，不傳送任何東西。
   - 檢查轉換結果時只看摘要，例如行數和每行的 id、cwd、訊息數，不要把整個 JSONL 列印到對話裡：裡面有其他專案的對話。

4. 試執行。在接入引導的命令上加 `--input "<tmp>/ov-sessions.jsonl"`，`--harness` 用上表的值，例如：

   ```bash
   node "<tmp>/ov-import-history.mjs" --harness <值> --input "<tmp>/ov-sessions.jsonl" --cwd "$PWD" --since 14d --max-sessions 20 --dry-run --json
   ```

   指令碼指出某一行格式不對時，改轉換指令碼、重新生成，再試執行。數量明顯不對（例如範圍內一個會話都沒有，或訊息數遠少於實際對話）時，先檢查轉換，不要直接匯入。要上傳的是 0 個、但有狀態為 `imported` 或 `live` 的會話，說明內容已經在 OpenViking 裡，不是轉換出錯，按接入引導 3b 直接去讀回。

5. 之後和接入引導裡一樣：按 3b 請使用者確認（當前這段對話已經由轉換指令碼排除，不會出現在「仍在活動」裡），他確認後把 `--dry-run` 換成 `--yes --wait` 正式匯入，再按 3c 讀回。匯入完，或者決定不匯入，都要刪掉 JSONL 和轉換指令碼；寫到過幾個位置就刪幾處，再用 `ls` 確認已經刪掉。

找不到會話儲存在哪，或者改了兩三次仍轉換不對，就告訴使用者這次沒能匯入這個宿主的歷史，OpenViking 會從外掛生效後的對話開始積累，然後回到接入引導的步驟 4。
