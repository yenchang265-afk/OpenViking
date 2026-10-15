# Working Memory 預設關閉

OpenViking 現在預設 `working_memory.enabled=false`。commit 仍會儲存原始訊息並排程長期記憶抽取，但除非顯式開啟 WM，否則不會生成歸檔 overview 或保留 checkpoint 摘要。這個開關不影響長期記憶、recall、profile 或工具。

## 升級服務端與外掛

升級 OpenViking Python 包**不會**更新已安裝在各 agent 宿主中的外掛副本。請按各外掛的安裝說明逐個更新，然後重啟對應宿主。如果某個會話依賴 OV 歷史，請先完成這一步，再把它切換到宿主原生的歷史管理。舊版接管（takeover）外掛不支援新的預設值，服務端也無法繞過它們的輪詢問題。

| 整合 | 新預設行為 | 顯式開啟 |
| --- | --- | --- |
| Claude Code、Codex / TraeCode CLI、OpenCode | resume/compact 時不自動注入歸檔；以宿主歷史為準 | `resumeArchiveInject: true` 啟用補充的歸檔注入，不會生成摘要 |
| Pi 官方擴充 | 使用 Pi 原生 compaction；不接管，也不在 resume 時注入歸檔 | `takeoverEnabled: true`；commit 時顯式請求 WM |
| OpenClaw | `contextManagementMode: "native"`：保留宿主訊息，壓縮交給宿主 | `contextManagementMode: "openviking"`；commit 時顯式請求 WM |
| VikingBot | `session_context_enabled: true`：由 OV 管理歷史與壓縮，commit 時顯式請求 WM | 設定 `session_context_enabled: false` 使用 VikingBot 現有的本地模式 |
| LangChain / LangGraph | 中介軟體只做捕獲和 recall，不再拉取 OV 會話歷史 | 舊版 OV 歷史介面卡需要開啟 WM，並由應用顯式決定 |

已有的顯式外掛配置和環境變數仍優先於預設值。如果某個安裝之前開啟了接管或注入，要切換時請刪除這些配置或設為 false，安裝器不會覆蓋你的選擇。Hermes、WorkBuddy、AstrBot 等其他捕獲/recall 類整合沿用服務端預設值，它們的宿主歷史不受此變更影響。

Pi 的實驗性上下文管理擴充不在本次 WM 關閉適配範圍內，請勿把它當作 WM 關閉後的歷史後端。

## 已持久化的策略與佇列中的任務

舊版序列化在 `working_memory` 為 true 時會省略該欄位。因此，即使通過 Studio 或常規的使用者/會話儲存 API 顯式開啟，該欄位也可能已丟失。現在，被選中的策略缺少該欄位時一律視為 **false**，無法還原使用者當初的意圖，需要的話請重新顯式開啟 WM。原始配置中仍保留 true 的策略，在被選中時保持不變。策略優先順序仍然是整份策略選擇，缺失欄位不會從低優先順序策略補齊。

新的序列化始終包含 WM 布林值。新的佇列快照包含 `memory_policy_version: 1`。沒有版本號的舊佇列/恢復快照，在缺少 WM 欄位時仍沿用提交時的 WM=true 語義，因此這些已提交的任務在升級後仍可能生成摘要。這不會把已儲存的使用者/會話策略標記為已開啟。如果不能接受升級後仍有 WM 生成，請在升級前先排空舊任務。

## 按次顯式生成

`POST /api/v1/sessions/{id}/commit` 接受 `enable_working_memory`：

- 省略或 `null`：使用解析後的會話/使用者/服務端策略。
- `true` 或 `false`：**僅覆蓋本次 commit 的 WM**，不改變 `self`、`peer`、`memory_types` 或已儲存的策略。
- 字串和數字會被拒絕。響應中的 `effective_enable_working_memory` 反映實際生效的 commit 策略。

更新後的接管類整合在依賴摘要之前，要求拿到明確的 true 確認。缺少確認、WM 已關閉，或歸檔已完成/失敗但沒有可用摘要時，保留宿主原生歷史。Pi 在輪詢時檢查歸檔狀態，到達終態邊界時再讀取一次，然後立即回退到原生 compaction，不會等到超時。

## 歷史 API 的返回內容

`GET /sessions/{id}/context` 返回的是有邊界的 prompt 檢視，不是完整的對話記錄。關閉生成策略後，仍可讀取已有的合格摘要。一旦更新的 WM 關閉歸檔完成，其邊界會截斷該檢視：overview 為空，只保留 retained/active 訊息和更新的待處理原始訊息。它不會恢復更早的摘要，也不會回放所有歸檔。WM 關閉下的正常完成不算歸檔失敗。

`GET /sessions/{id}/archives/{archive_id}` 對已完成的 WM 關閉歸檔返回原始 `messages`，其中 `overview: ""`、`abstract: ""`。顯式的歸檔工具仍可使用。待處理、失敗、缺失或損壞的歸檔保持原有的錯誤行為。Recall 內部仍可使用合格的舊摘要；關閉生成不會刪除已儲存的歷史。

## 應用與舊會話

LangChain 請使用 `with_openviking_memory(..., history_factory=...)` 並配合宿主的歷史提供者。未提供 provider 的舊版 `with_openviking_context` 會警告它依賴 OV 歷史。中介軟體預設 `include_session_context=False`。請把它放在原生 summarization 中介軟體之前，使原始訊息在框架替換它們之前被捕獲。訊息捕獲水位線儲存在 graph state 中。可執行的[原生歷史示例](https://github.com/volcengine/OpenViking/blob/main/integrations/frameworks/langchain/examples/langgraph/middleware/native_history.py)及其固定版本的依賴，演示了 LangChain summarization 配合 SQLite checkpointer 的用法。

VikingBot 是“預設使用宿主歷史”的例外：它仍然使用 OV Working Memory 管理上下文和壓縮。它的會話上下文 commit 會顯式傳送 `enable_working_memory: true`，包括已儲存策略關閉了 WM 的既有會話。它保持現有的 commit-and-clear 流程；之後的上下文讀取使用 OV 的 overview/checkpoint 和保留的訊息，生成仍在進行時則使用待處理歸檔中的訊息。如果服務端未確認 WM 生成，該 commit 會被視為失敗，本地歷史保留以便重試。此變更不會替換 VikingBot 的本地壓縮。

部分由 OV 管理的舊會話已不再有完整的宿主對話記錄。請停止寫入，並使用[歷史匯出工具](https://github.com/volcengine/OpenViking/blob/main/examples/session-history-export/README.md)，通過宿主支援的檔案/上下文入口準備一個新的宿主會話。繼續之前，請確認宿主擁有必要的歷史。僅匯出**不等於**已匯入或已驗證的遷移；該工具不會修改宿主的私有對話記錄、不會更改策略，也不會刪除源資料。如果原始來源不完整，不要自動切換依賴歷史的會話。

## 診斷與回滾

OpenClaw 的健康檢查僅在 commit 確認 WM=true 時才要求有 overview。Pi 的 live E2E 預設使用原生歷史；如需測試顯式接管，請設定 `E2E_TAKEOVER=1`。測試 WM/checkpoint 的用例需要顯式開啟。

重新開啟 WM 隻影響之後的 commit，不會為之前的歸檔補建缺失的摘要。回滾服務端行為時，請保留原始備份和更新後的外掛。舊版客戶端可能重新應用舊的接管邊界，不得悄悄替換已遷移到宿主歷史的會話。
