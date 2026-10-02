# VikingBot 接入 OpenViking 會話壓縮改造方案

## 結論

該方案可行，但不能直接沿用當前 VikingBot 的 OpenViking 接入方式。

當前 OpenViking 服務端已經具備以下關鍵能力：

- 穩定 session 的訊息追加
- `pending_tokens` 累積
- `commit(keep_recent_count=...)`
- `get_session_context()` 返回 `latest_archive_overview` 與 live messages

真正需要改造的是 VikingBot 側的寫路徑、讀路徑、配置與舊壓縮鏈路的退場策略。

## 目標

把 VikingBot 的長對話壓縮鏈路改為：

1. 同一個 bot session 持續寫入同一個 OpenViking session。
2. 每輪僅增量同步本輪新增訊息，不重複全量重傳。
3. 當 OpenViking session 的 `pending_tokens` 達到閾值時觸發 `commit`。
4. 下一輪模型呼叫前，從 OpenViking 讀取已壓縮上下文。
5. 本地 session 在未壓縮前保留原始訊息日誌；OpenViking commit 成功後清空本地 JSONL，由 OpenViking 負責長上下文壓縮與回放。

## 非目標

第一版不做以下事情：

- 不讓 OpenViking 完全替代本地 session 儲存。
- 不把全部 tool trace / reasoning 直接納入 OpenViking 壓縮主鏈路。
- 不依賴 memory extraction 完成後才能繼續下一輪對話。
- 不同時保留兩套自動壓縮主鏈路並行工作。

## 當前實現與方案的關鍵差異

### 1. 當前 `ov_server.py` 不是穩定 session 模式

當前 `bot/vikingbot/openviking_mount/ov_server.py` 的 `commit(...)` 會在每次提交時重新建立 session，再把整段訊息寫入並立刻 commit。

這與目標方案衝突，因為它會導致：

- `pending_tokens` 無法持續累積
- 下一輪無法從同一個 session 取回壓縮結果
- 無法做真正的增量同步

因此，這個檔案必須從“一次性提交器”改造成“穩定 session 訪問層”。

### 2. 當前 `loop.py` 仍以本地 history 為主

當前 `bot/vikingbot/agent/loop.py` 仍然使用：

- `session.get_history(...)` 作為模型 history
- `len(session.messages) > self.memory_window` 作為本地自動壓縮觸發條件

這意味著現有主鏈路仍是“本地 session 驅動”，而不是“OpenViking session 驅動”。

### 3. 當前 `context.py` 只會拼本地 history

當前 `bot/vikingbot/agent/context.py` 的 prompt 組裝仍是：

1. system prompt
2. 本地 history
3. memory/context 注入
4. 當前 user message

如果要接入 OpenViking 壓縮上下文，必須顯式擴充 prompt assembly。

### 4. 現有舊 compact hook 會與新鏈路衝突

當前 `bot/vikingbot/hooks/builtins/openviking_hooks.py` 裡仍有舊的 `message.compact` 邏輯：

- 有的模式下會把 session 拆成 admin session + per-user session
- 這與新方案的“一個房間對應一個穩定 OV session”衝突

因此新鏈路啟用後，舊 compact hook 必須被停用、繞過或顯式降級為非主路徑。

## 設計原則

### 1. OpenViking 負責長上下文壓縮，本地 session 負責壓縮前原始日誌

第一版不建議讓 OpenViking 直接替代本地 session 的短期落盤能力。

推薦職責劃分：

- 本地 session：在壓縮前儲存原始訊息，相容現有 provider-specific 欄位
- OpenViking session：儲存用於長對話壓縮和回放的核心訊息鏈路

達到 token/window 閾值併成功 commit 後，本地 session JSONL 會被清空，下一輪通過 OpenViking context 回放已壓縮歷史。

### 2. OpenViking session 必須穩定

一個 `SessionKey.safe_name()` 對應一個穩定的 `ov_session_id`。

第一版建議直接使用：

- `ov_session_id = SessionKey.safe_name()`

不再在每次 commit 時重新 `create_session()`。

### 3. OpenViking 讀路徑優先，本地只補 unsynced delta

OpenViking 的 `get_session_context()` 返回的不是純摘要，而是：

- `latest_archive_overview`
- pending archive messages
- 當前 live messages

因此，VikingBot 讀路徑不能再把本地 history 整段拼進去。

正確規則應為：

- 以 OpenViking 返回內容作為主 history
- 本地僅補“尚未成功寫入 OpenViking 的尾部 delta”

否則會產生重複上下文。

### 4. 請求身份與訊息說話人分離

群聊場景中要區分兩層身份：

- OpenViking request identity：誰在發起這次 API 呼叫
- message speaker identity：這條訊息是誰說的

第一版建議：

- 請求繼續使用當前合法的 bot/account/user 身份
- 每條訊息的真實說話人通過 `peer_id` 記錄

不要把“當前 `sender_id`”直接等同於每次請求的 OpenViking user 身份，否則會和現有許可權/名稱空間語義衝突。

## 核心方案

## 1. 穩定的 OpenViking Session 繫結

在本地 session metadata 中維護：

```json
{
  "openviking": {
    "enabled": true,
    "session_id": "<SessionKey.safe_name()>",
    "last_synced_local_index": 0,
    "last_commit_at": null,
    "last_pending_tokens": 0,
    "last_context_read_at": null,
    "last_sync_status": "idle"
  }
}
```

欄位說明：

- `session_id`: 穩定的 OpenViking session id
- `last_synced_local_index`: 已成功同步到 OpenViking 的本地訊息下標上界
- `last_commit_at`: 最近一次 commit 時間
- `last_pending_tokens`: 最近一次觀測到的 `pending_tokens`
- `last_context_read_at`: 最近一次讀 context 時間
- `last_sync_status`: `idle` / `syncing` / `error`

其中最關鍵的是 `last_synced_local_index`，它決定增量同步與去重是否正確。

## 2. 寫路徑：每輪結束後增量同步到 OpenViking

寫路徑觸發點位於 `bot/vikingbot/agent/loop.py` 當前一輪完成、本地 `session.add_message(...)` + `save(...)` 之後。

### 同步內容

第一版只同步核心對話訊息：

- user message
- assistant final content

第一版不建議寫入：

- 全量 tool trace
- `reasoning_content`
- 大體積工具輸出

原因：

- 這些內容會顯著放大壓縮噪聲
- 當前 provider replay 仍主要依賴本地 session
- 第一版目標是先打通穩定會話壓縮閉環，而不是完整映象全部除錯資訊

### 同步流程

```text
1. 讀取 session.metadata.openviking
2. 若不存在 session_id，則建立/確保穩定 session
3. 根據 last_synced_local_index 找出新增訊息
4. 將新增訊息轉換為 OV message parts
5. 呼叫 append_messages / batch_add_messages 寫入 OV
6. 讀取 session meta，獲取 pending_tokens
7. 若 pending_tokens >= commit_token_threshold 或訊息數達到 memory_window，則觸發 commit_session(keep_recent_count=N)
8. 更新本地 metadata 中的同步游標與快照
9. 如果本次實際執行了 commit，則清空本地 session JSONL，並重置本地同步游標但保留穩定 session_id
```

### 寫路徑要求

- 只在“成功寫入 OV”後推進 `last_synced_local_index`
- commit 失敗不應回滾已成功寫入的訊息游標
- commit 成功代表本輪壓縮完成，應清空本地 session JSONL；後續 prompt 由 OpenViking context + 新的本地未同步 tail 組成
- commit 與 extract 非同步執行時，下一輪仍可繼續讀取 session context

## 3. 讀路徑：模型呼叫前優先從 OpenViking 組裝 history

讀路徑觸發點位於 `bot/vikingbot/agent/loop.py` 當前構建 `messages = await message_context.build_messages(...)` 之前。

### 讀取流程

```text
1. 讀取本地 metadata.openviking
2. 若未啟用或尚未建立穩定 session，則退化為本地 history 模式
3. 呼叫 get_session_context(session_id, token_budget)
4. 取回 latest_archive_overview + messages
5. 根據 last_synced_local_index，僅補本地未同步 delta
6. 將組裝後的 history 傳給 ContextBuilder.build_messages(...)
```

### 推薦上下文順序

1. system prompt
2. OpenViking `latest_archive_overview`
3. OpenViking `messages`
4. 本地 unsynced delta history
5. 當前 user message

### 去重規則

這是第一版最關鍵的邊界條件：

- 不能再把本地 `session.get_history(...)` 全量拼到 OpenViking context 後面
- 本地只允許補尚未成功同步到 OpenViking 的訊息
- 一旦訊息已確認 append 成功，就不應再出現在 local delta 中

否則很容易出現重複輪次，導致模型重複理解、工具誤觸發或 token 浪費。

## 4. token budget 的使用方式

`session_context_token_budget` 不能被視為最終 prompt 的硬上限。

第一版應採用兩層預算：

### 第一層：OpenViking context budget

用於控制呼叫 `get_session_context(session_id, token_budget=...)` 的預算目標。

### 第二層：VikingBot 最終 prompt trim

在組裝出：

- OV overview
- OV messages
- local unsynced delta
- current user message

之後，仍需在 VikingBot 側做一次最終裁剪，確保不會超過 provider 的上下文限制。

否則在大群聊或訊息內容較長時，仍可能超出模型視窗。

## 5. 群聊語義

群聊推薦語義如下：

- 一個聊天房間對應一個穩定 `ov_session_id`
- OpenViking request identity 繼續按當前 bot/account 配置走
- 每條 user/assistant message 的實際說話者寫入 `peer_id`

建議對映：

- user message: `role="user"`, `peer_id=<真實 sender_id>`
- assistant message: `role="assistant"`, `peer_id=<bot/agent id 或預設 assistant 標識>`

這樣可以同時滿足：

- 會話不被拆碎
- 群聊參與者身份可保留
- 不破壞當前 OpenViking 的身份回退邏輯

## 需要改動的檔案

### 1. `bot/vikingbot/openviking_mount/ov_server.py`

把現有一次性 `commit(...)` 改造成穩定 session 訪問層。

建議新增或重構為以下介面：

- `ensure_session(session_id: str) -> dict`
- `append_messages(session_id: str, messages: list[dict], peer_id_resolver=...) -> dict`
- `get_session(session_id: str) -> dict`
- `get_session_context(session_id: str, token_budget: int) -> dict`
- `commit_session(session_id: str, keep_recent_count: int = 0) -> dict`

要求：

- 不再每次重新建立 session
- 允許批次追加訊息
- 能返回最新 `pending_tokens`
- commit 時能傳 `keep_recent_count`

### 2. `bot/vikingbot/agent/loop.py`

需要新增兩段邏輯：

- 模型呼叫前：讀取 OV context 並構造 history
- 一輪結束後：把本輪新增訊息增量同步到 OV，並按閾值決定是否 commit

同時需要關閉或門控當前本地自動 compact 主鏈路：

- 當 `session_context_enabled=true` 時，不再使用 `len(session.messages) > self.memory_window` 觸發舊壓縮主鏈路
- `/compact` 可保留為顯式命令，但行為要重新定義，避免與新鏈路重複

### 3. `bot/vikingbot/agent/context.py`

需要讓 `build_messages(...)` 支援接收“外部已組裝好的 history”。

推薦方式：

- `loop.py` 先準備好 `history`
- `context.py` 只負責拼：system prompt、memory、當前 user message

這樣可以避免把 OpenViking 邏輯硬塞進 `ContextBuilder` 內部。

### 4. `bot/vikingbot/session/manager.py`

當前 metadata merge 已支援巢狀字典，可直接用於持久化：

- `metadata["openviking"][...]`

這裡只需要補充新欄位的讀寫約定，不需要重新設計儲存格式。

### 5. `bot/vikingbot/config/schema.py`

在 `AgentsConfig` 中增加配置項：

- `session_context_enabled: bool = False`
- `session_context_token_budget: int = 12000`
- `commit_token_threshold: int = 6000`
- `commit_keep_recent_count: int = 10`

其中：

- `session_context_enabled`：總開關
- `session_context_token_budget`：OV context 讀取預算
- `commit_token_threshold`：觸發 commit 的閾值
- `commit_keep_recent_count`：commit 後保留的 recent live messages 數量

## OpenViking Python HTTP SDK 需要補的能力

OpenViking 服務端和 Python HTTP SDK 需要完整透出以下呼叫能力：

- `commit_session(session_id, keep_recent_count=0, telemetry=False)`
- `Session.commit(keep_recent_count=0, telemetry=False)`
- `Session.commit_async(keep_recent_count=0, telemetry=False)`

對應實現位於 `sdk/python/openviking_sdk/client.py`，VikingBot 通過 HTTP 服務呼叫這些介面。

## 與舊鏈路的共存策略

### 必須處理的衝突點

以下舊鏈路會與新方案衝突：

- `bot/vikingbot/hooks/builtins/openviking_hooks.py`
- `bot/vikingbot/agent/loop.py` 中基於 `memory_window` 的自動 compact
- 任何仍按“全量 session -> 一次性 commit”的舊呼叫點

### 推薦策略

當 `session_context_enabled=true` 時：

1. 停用舊的 `message.compact` OpenViking hook 主路徑
2. 停用 `len(session.messages) > self.memory_window` 的舊自動壓縮
3. 保留 `/compact` 作為顯式運維命令，但它應呼叫新的 stable-session commit 邏輯，而不是舊 fanout 邏輯

## 分階段實施

## 第一階段：打通最小閉環

目標：不動 provider 行為的前提下，讓 OpenViking 真正接管長對話壓縮。

實施項：

1. 重構 `ov_server.py` 為穩定 session 訪問層
2. 在 `loop.py` 中接入 after-turn 增量同步
3. 在 `loop.py` 中接入 before-call OV context 讀取
4. 在本地 metadata 中儲存 `openviking` 同步狀態
5. 啟用去重規則：本地僅補 unsynced delta

驗收標準：

- 同一 session 多輪對話使用同一個 `ov_session_id`
- `pending_tokens` 可持續增長
- 達到閾值後能成功 commit
- 下一輪能讀到 `latest_archive_overview` 和 live messages
- prompt 中無重複歷史片段

## 第二階段：補齊 keep_recent_count 與預算控制

實施項：

1. 修改 OpenViking Python client wrapper
2. 讓 `commit_keep_recent_count` 配置生效
3. 在 VikingBot 側增加最終 prompt trim

驗收標準：

- commit 後最近 N 條訊息仍保留在 live session 中
- 長會話下 prompt 大小可控
- 不因 context 過長導致 provider 呼叫失敗

## 第三階段：清理舊鏈路

實施項：

1. 門控舊 `message.compact` hook
2. 門控舊 `memory_window` 自動 compact
3. 明確 `/compact` 與新方案的關係
4. 檢查其他工具或工廠函式是否仍依賴舊一次性 commit 邏輯

驗收標準：

- 新舊鏈路不會同時對同一 session 生效
- 群聊不會被拆成多個 OV session
- 迴歸測試中 history 組裝路徑唯一且可解釋

## 風險與注意事項

### 1. 重複上下文風險

如果本地 delta 計算不準確，最容易出現訊息重複拼接。

這是第一版必須優先規避的問題。

### 2. provider-specific 欄位丟失風險

當前本地 session 會保留部分 provider 特有欄位，例如 `reasoning_content`。

因此第一版推薦保留“本地原始日誌 + OV 壓縮層”的雙層職責，而不是直接完全切換到 OV history。

### 3. 群聊身份對映風險

如果直接把 `sender_id` 當作每次 OV 請求 user 身份，容易與當前 account/user/peer 許可權語義衝突。

應優先通過 `peer_id` 保留真實說話人。

### 4. 提取非同步性的認知風險

commit 之後的 memory extraction 是後臺過程。

下一輪對話可依賴 session context，但不要把“新 memory 必然已可檢索”當成同步保證。

## 一句話總結

把 VikingBot 改成“本地原始日誌 + OpenViking 長上下文壓縮層”的雙層結構：每輪增量寫入穩定 OV session，達到 `pending_tokens` 閾值就 commit，下一輪優先讀取 `latest_archive_overview + live messages`，本地只補尚未同步的 delta，並在啟用新鏈路後退場舊的 compact/fanout 邏輯。
