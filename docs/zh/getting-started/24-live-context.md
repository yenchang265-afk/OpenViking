# 即時上下文

專案進度、待辦數量和服務狀態會隨時變化。即時上下文（Live Context）讓 Agent 通過一個固定的 `viking://` 路徑，在讀取時查詢資料來源，取得當次呼叫的結果。

OpenViking 將遠端 MCP 工具與固定引數繫結為一個可檢索的 Markdown 節點。Agent 找到節點後，像讀取資料一樣完整讀取它，OpenViking 就會呼叫對應工具。本節以 Lighthouse 演示專案為例：掛載待處理反饋查詢，將數量從 3 條改為 1 條，再讀取同一路徑檢視變化。

## 與直接呼叫 MCP 的區別

兩種方式都能查詢最新資料，區別在於 Agent 如何找到和使用它：

| | Agent 直接呼叫 MCP | 通過 OpenViking 掛載 |
| --- | --- | --- |
| 查詢方式 | 選擇工具，按工具定義填寫引數並呼叫 | 檢索業務含義明確的節點，再完整讀取 |
| 本例中的操作 | 呼叫 `project_status`，傳入 `project=Lighthouse` | 找到“Lighthouse 待處理反饋”節點，讀取其 URI |
| 接入與維護 | 在 Agent 宿主中配置上游 MCP 連線 | 在 OpenViking 中管理上游連線、工具繫結和固定引數；Agent 使用 OpenViking 的檢索與讀取入口 |

掛載讓這類查詢與普通資料使用同一套檢索和讀取方式，固定引數由節點複用。配置工作在掛載時完成，Agent 使用節點時無需再構造這些引數。只有少量工具、查詢引數經常變化時，直接呼叫 MCP 通常更直接；高頻且引數穩定的查詢適合掛載。

## 準備環境

- **OpenViking 服務和 CLI**：按照[快速開始](02-quickstart.md)完成連線配置。兩者都需要支援即時上下文；執行 `ov mcps --help` 確認 CLI 提供該命令。註冊和掛載會使用服務端的模型及索引配置，可能產生模型呼叫費用。
- **Python 和 uv**：樣例需要 Python 3.10+ 和 [uv](https://docs.astral.sh/uv/getting-started/installation/)。執行 `python3 --version` 和 `uv --version` 檢查；`uv run` 會安裝指令碼宣告的 MCP 依賴。
- **訪問許可權**：使用同一個 OpenViking 使用者完成操作，並確認能夠在 `viking://resources/onboarding-live-context-v1/` 下建立節點。

開始前，確認 CLI 當前連線的服務和身份，並檢查 MCP 管理介面是否可用：

```bash
ov health
ov mcps list
```

`health` 應返回健康狀態；啟用 API Key 鑑權時，還應顯示當前 Account、User 和角色。`mcps list` 應正常返回列表，空列表也可以繼續。使用能夠訪問目標目錄的 User/Admin Key；`api_key` 模式下，Root Key 不用於本節的資料操作。若返回 404、缺少 API Key 或身份錯誤，先通過 `ov config` 檢查並選擇正確的連線。

本例適用於 OpenViking 服務直接執行在本機的環境，MCP 樣例也在本機執行。使用容器或遠端 OpenViking 服務時，`127.0.0.1` 指向服務自身的執行環境；需要準備服務端可訪問的 Streamable HTTP MCP 地址，接入方法見[即時上下文接入與編排](../guides/24-live-context-arrangement.md)。

## 啟動樣例資料來源

下載[即時上下文樣例包](/quickstart/live-context-demo-v1.zip)，在終端進入下載目錄。解壓後啟動樣例，包內的 `status.json` 已將虛構的待處理反饋數量設為 3 條：

```bash
unzip live-context-demo-v1.zip
cd live-context-demo
uv run live-context-demo.py
```

保持這個終端執行。指令碼在 `http://127.0.0.1:8765/mcp` 提供 `project_status` 工具，每次呼叫都會重新讀取同目錄中的 `status.json`。工具只查詢資料，不會修改反饋。

如果 8765 埠已被佔用，可以使用 `uv run live-context-demo.py --port 18765` 啟動，並將後續 `validate` 和 `add` 命令中的埠一併改為 `18765`。

另開一個終端，進入同一目錄，驗證 OpenViking 服務能連線樣例並發現工具：

```bash
ov mcps validate '{"mcpServers":{"onboarding-live-v1":{"url":"http://127.0.0.1:8765/mcp"}}}'
```

確認驗證通過，發現的工具數量為 1 後繼續。如果連線失敗，先檢查樣例程序是否執行，以及 OpenViking 服務是否直接執行在本機。

## 註冊並掛載節點

將資料來源註冊到當前使用者的工具目錄，等待工具目錄處理完成：

```bash
ov mcps add '{"mcpServers":{"onboarding-live-v1":{"url":"http://127.0.0.1:8765/mcp"}}}' --wait
ov mcps show onboarding-live-v1
```

確認工具列表中有 `project_status`，引數包含字串型別的 `project`。`viking://~/tools/` 表示當前使用者的工具目錄。重複體驗時，如果提示同名 Server 已存在，先用 `show` 確認地址和工具仍與本例一致，再繼續。

把這個工具掛載到演示目錄，固定查詢 Lighthouse 專案：

```bash
ov mcps mount \
  viking://~/tools/onboarding-live-v1/project_status.json \
  viking://resources/onboarding-live-context-v1/status.md \
  --title "Lighthouse 待處理反饋" \
  --description "查詢 Lighthouse 演示專案當前的待處理反饋數量。" \
  --args '{"project":"Lighthouse"}' \
  --wait
```

掛載成功後，檢視繫結關係：

```bash
ov mcps mounts --mcp onboarding-live-v1
```

結果應包含 `status.md` 的 URI、`project_status` 工具和 `project=Lighthouse` 引數。再次掛載到同一 URI 會更新繫結；重複體驗時請確認這是本次演示節點。

## 讀取並觀察變化

先按業務問題檢索節點，無需指定上游工具名：

```bash
ov find "Lighthouse 專案現在有多少條待處理反饋？" \
  --uri viking://resources/onboarding-live-context-v1
```

在結果中找到 `status.md`，核對標題和描述是否對應 Lighthouse 待處理反饋。檢索找到的是查詢入口，當前數量需要完整讀取後才能獲得：

```bash
ov read viking://resources/onboarding-live-context-v1/status.md
```

結果應包含以下欄位：

```json
{"project":"Lighthouse","pending_feedback":3}
```

在第二個終端中修改資料來源，再次讀取同一 URI：

```bash
printf '%s\n' '{"pending_feedback":1}' > status.json
ov read viking://resources/onboarding-live-context-v1/status.md
```

此時 `pending_feedback` 應變為 `1`。本次只修改了樣例資料來源，未重新匯入資料、同步工具或修改掛載；讀取時，OpenViking 再次呼叫了同一個工具。

“即時”表示讀取時發起查詢，資料的新舊程度取決於上游系統。它不會讓資料來源主動推送變化，也不會自動更新 Agent 已經讀過的回答。

## 讓 Agent 使用節點

如果已經完成 [Agent 接入](07-agent-onboarding.md)，可以讓 Agent 自己檢索並讀取節點。Agent 應連線同一服務，並使用能夠訪問該節點和當前使用者工具目錄的身份。使用一個未直接連線樣例 MCP Server 的 Agent 會話，輸入：

```text
Lighthouse 專案現在有多少條待處理反饋？
請在 OpenViking 的 viking://resources/onboarding-live-context-v1/ 下
檢索相關上下文，完整讀取找到的節點後回答，並引用來源 URI。
如果讀取失敗，請說明原因，不要沿用之前的數量。
```

檢查呼叫記錄：Agent 應先檢索到 `status.md`，再完整讀取它，最後回答 1 條待處理反饋並引用節點 URI。提示詞只給了業務問題和檢索範圍，沒有提供上游工具名、引數格式或節點的完整路徑；這些繫結由 OpenViking 處理。

數量從 3 變為 1 展示了讀取時查詢資料來源；Agent 通過檢索找到節點，再用統一的讀取入口取得結果，展示了掛載後的使用方式。

## 檢查結果

| 檢查項 | 預期結果 |
| --- | --- |
| 工具可用 | `show` 中有 `project_status` 及其引數定義 |
| 掛載正確 | `mounts` 中的節點 URI、工具和專案引數一致 |
| 節點可發現 | 按業務問題檢索，結果中包含 `status.md` |
| 首次讀取 | 返回 Lighthouse 專案，待處理反饋為 3 條 |
| 資料來源更新後讀取 | 同一 URI 返回 1 條，無需重新掛載 |
| Agent 使用（可選） | 無需直接接入樣例 MCP，記錄中有檢索及完整讀取，回答包含最新數量和來源 URI |

## 常見問題

| 現象 | 處理方法 |
| --- | --- |
| CLI 不識別 `mcps`，或服務沒有對應介面 | 更新到支援即時上下文的 CLI 和服務端；安裝入口見 [CLI 入門](05-cli-setup.md) |
| 驗證或讀取連線失敗 | 保持樣例程序執行，確認從 OpenViking 服務端能訪問 MCP 地址 |
| 讀取後仍為 3 條 | 確認修改的是樣例指令碼同目錄的 `status.json`，再發起一次讀取 |
| 檢索沒有找到節點 | 先用 `mounts` 確認掛載，再檢查掛載處理結果、索引狀態和檢索範圍；直接讀取成功不代表索引已可用 |
| 返回節點描述檔案 | 使用不帶分頁引數的 `ov read`；分頁讀取或 API 的 `raw=true` 不執行上游工具 |
| 提示工具不是隻讀工具 | 本例工具已宣告只讀；其他工具若明確標為非只讀或破壞性，不能通過 `read` 執行，需按[工具呼叫介面](../api/26-mcp-live-context.md)顯式呼叫 |
| Agent 回答仍使用舊數量 | 檢查是否真的執行了本次完整讀取，並確認服務和使用者身份一致 |

`find`、`search` 和目錄瀏覽不會呼叫即時節點。上游工具返回錯誤時，讀取也會報錯，應先排查資料來源。

## 繼續使用

你可以把這個方式用於專案進度、工單數量或服務狀態等高頻查詢。固定引數的查詢適合掛載為即時上下文；引數隨問題變化的查詢，可以通過工具發現與呼叫完成。Studio 編排、鑑權、工具變更同步和 Context as Code 見[即時上下文接入與編排](../guides/24-live-context-arrangement.md)。

體驗結束後，先解除安裝本次節點，再刪除樣例 Server 註冊：

```bash
ov mcps unmount viking://resources/onboarding-live-context-v1/status.md --wait
ov mcps remove onboarding-live-v1
```

回到執行樣例的終端，按 `Ctrl+C` 停止資料來源。
