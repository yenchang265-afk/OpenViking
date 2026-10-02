# Vikingbot 問答效果反饋觀測方案設計

**Author:** OpenViking Team
**Status:** Revised Draft
**Date:** 2026-04-30

---

## 1. 背景

基於當前程式碼複核，vikingbot 現狀更準確地說是“過程可觀測”，而不是“結果可觀測”。

當前已經存在的能力包括：

- `AgentLoop` 最終返回的 `OutboundMessage` 已攜帶 `time_cost`、`token_usage`、`iteration`、`tools_used_names`
- bus 已支援 `REASONING`、`TOOL_CALL`、`TOOL_RESULT`、`ITERATION`、`NO_REPLY` 等過程事件
- Langfuse 已接入 `session_id` / `user_id` 透傳、LLM generation、tool span
- session 以 JSONL 持久化歷史訊息，assistant 訊息可儲存 `token_usage` 與 `tools_used`

但原方案的若干前提與當前實現已經有偏差，主要體現在：

- Phase 1 已經補齊 `response_id`，並打通到 `OutboundMessage`、session JSONL、OpenAPI 返回體與 Langfuse metadata
- Phase 2 當前工作樹已經補齊顯式反饋入口，OpenAPI 提供 `POST /bot/v1/feedback`
- `response_completed` 與 `feedback_submitted` 已經進入實現範圍；`response_outcome_evaluated` 仍然屬於 Phase 3，但當前工作樹已經落地最小規則版實現
- session JSONL 的 assistant message 仍然不是完整的響應事實表，但當前已經把標準化 `response_completed` 以 `session.metadata["response_facts"][response_id]` 的形式持久化到 metadata 首行
- OpenAPI 當前只透出 `response`、`reasoning`、`tool_call`、`tool_result`，並未把 `ITERATION` 等過程事件完整暴露出來
- Langfuse 當前寫入的 generation metadata 已覆蓋 `response_id`；`query_category`、`prompt_version`、`bot_version` 仍未穩定覆蓋；Phase 3 outcome 當前通過 trace event 與 observation score 記錄，而不是事後回寫已結束 generation metadata
- 程式碼中還沒有穩定的 `query_category`、`prompt_version`、`bot_version` 欄位來源，因此原方案裡大量切片分析暫時沒有資料基礎

### 1.1 截至 2026-04-30 的實現狀態更新

為避免後續討論繼續把“設計目標”誤寫成“當前能力”，這裡先明確當前程式碼狀態：

1. Phase 1 已完成並已單獨提交，`response_id` 已經貫通最終回答鏈路。
2. Phase 2 當前實現已經包含 `POST /bot/v1/feedback`、`FeedbackRequest` / `FeedbackResponse`、`OutboundEventType.FEEDBACK_SUBMITTED`。
3. 顯式反饋當前採用最小化落地：反饋事件追加寫入 session JSONL 的 `session.metadata["feedback_events"]`，而不是新建獨立事實表。
4. `feedback_submitted` 屬於 analytics-only 事件，使用者側 channel 明確忽略該事件，避免把分析事件誤發到使用者可見通道。
5. `response_outcome_evaluated` 仍然是 Phase 3 能力，但當前僅實現 analytics-only 的最小規則版，不應誤寫成完整離線評測體系。

因此，這份方案需要從“直接建設完整反饋歸因體系”調整為“三步走”：

1. 先把一次回答變成可識別、可關聯、可沉澱的結構化物件。
2. 再補顯式反饋閉環。
3. 最後再做隱式結果判斷、問題分類和版本歸因。

在這個調整後的前提下，現有資訊仍然足以回答“系統有沒有執行”“模型和工具有沒有被呼叫”，但還不足以回答更關鍵的問題：

1. 使用者是否覺得這次回答有效。
2. 回答是否真正解決了使用者問題。
3. 哪類問題效果差。
4. 效果差是因為模型、工具、時延，還是對話策略。
5. 改 prompt、改模型、改工具後，效果是否提升。

本方案的目標是為 vikingbot 建立一套面向“問答效果反饋”的觀測體系，形成從回答生成到使用者反饋、再到問題歸因的完整閉環，並且保證每一階段都建立在當前程式碼已具備的事實基礎上。

---

## 2. 設計目標

### 2.1 目標

本方案希望建立一套可持續使用的指標體系，用於衡量 vikingbot 的問答質量和使用者體驗。

設計目標如下：

1. 能穩定衡量單條回答和單個會話的效果。
2. 能區分“模型回答差”“工具呼叫差”“執行太慢”等不同失敗模式。
3. 能支援按模型、渠道、問題型別、版本進行切片分析。
4. 能與 Langfuse trace 關聯，支援從壞樣本回溯到具體執行鏈路。
5. 能漸進式落地，先最小可用，再逐步增強。

### 2.2 非目標

本方案當前不追求以下目標：

1. 不試圖用單一指標替代所有人工判斷。
2. 不要求第一版就接入複雜的離線評測平臺。
3. 不要求所有指標都進入 Prometheus；部分更適合儲存在業務事件或分析倉庫中。
4. 不要求完全依賴 Langfuse 完成所有聚合分析；Langfuse 更適合作為 trace 容器和樣本診斷入口。

---

## 3. 核心問題與總體思路

### 3.1 需要回答的核心問題

該體系主要服務於以下五類問題：

1. 使用者覺得這次回答好不好。
2. 這次回答是否一次性解決問題。
3. 哪些問題型別和使用場景效果最差。
4. 壞結果主要集中在哪個執行環節。
5. 系統改動前後，效果是上升、持平還是回退。

### 3.2 總體思路

觀測體系分為四層：

1. 使用者反饋層：看使用者主觀評價。
2. 會話結果層：看問題是否被解決。
3. 執行質量層：看耗時、工具、LLM 呼叫質量。
4. 歸因分析層：按模型、渠道、問題型別、版本等維度切片。

核心鏈路如下：

`一次回答 -> 使用者反饋 -> 會話結果 -> trace 歸因`

換句話說，系統不能只採“過程”，也必須採“結果”。

### 3.3 現狀約束下的方案調整

為了避免方案設計繼續偏離當前實現，整體落地順序調整為以下三層依賴：

1. `response identity`：先給每次最終回答分配穩定的 `response_id`，並把它同時寫入 `OutboundMessage`、session message、OpenAPI 返回體和 Langfuse metadata。
2. `response facts`：再沉澱一條結構化 `response_completed` 事件，把當前已經能拿到的欄位先穩定儲存下來，並以 `session.metadata["response_facts"][response_id]` 的形式落盤，例如 `session_id`、`user_id`、`time_cost_ms`、`prompt_tokens`、`completion_tokens`、`total_tokens`、`iteration_count`、`tool_count`、`tools_used_names`、`response_length`、`created_at`。
3. `feedback & outcome`：最後在 `response_id` 基礎上補反饋事件與隱式結果判斷，否則後續指標會缺少關聯主鍵。

這意味著：

- 原方案中依賴 `query_category`、`prompt_version`、`bot_version` 的切片分析，需要從 MVP 下調到增強階段
- `good_answer_rate`、`one_turn_resolution_rate`、`reask_rate` 等結果指標，不適合作為第一批必須落地的線上指標
- 第一階段更應聚焦“把已有過程指標可靠地沉澱為響應事實”，而不是急於定義複雜的結果分數

---

## 4. 指標分層設計

## 4.1 使用者反饋層

這層是問答效果評估的長期核心，但不應被當成 Phase 1 的落地前提。

### 4.1.1 顯式滿意度指標

建議定義以下指標：

| 指標名 | 定義 | 說明 |
| --- | --- | --- |
| `feedback_coverage` | 有反饋回答數 / 總回答數 | 衡量樣本覆蓋率，避免只看好評率 |
| `thumbs_up_rate` | 點贊回答數 / 有反饋回答數 | 基礎正反饋指標 |
| `thumbs_down_rate` | 點踩回答數 / 有反饋回答數 | 基礎負反饋指標 |
| `csat_score` | 使用者評分均值 | 適用於 5 分制或 10 分制滿意度 |
| `dissatisfaction_reason_distribution` | 各類差評原因佔比 | 用於定位主要失敗模式 |

當前實現口徑補充：

- `responses_total` 以 session JSONL 中所有 `role == "assistant"` 且帶 `response_id` 的最終回答為準。
- `feedback_coverage` 的分母是 `responses_total`，分子是出現過顯式 feedback 的去重 `response_id` 數量。
- `thumbs_up_rate` / `thumbs_down_rate` 當前仍以 `feedback_total` 為分母，用於衡量顯式反饋內部的正負分佈。
- `positive_feedback_rate` / `negative_feedback_rate` / `reask_rate` / `one_turn_resolution_rate` 當前統一以 `responses_total` 為分母，用於衡量全部最終回答上的結果佔比。

差評原因建議最少支援以下標籤：

- `irrelevant`: 答非所問
- `incorrect`: 資訊錯誤
- `incomplete`: 不夠完整
- `too_slow`: 太慢
- `tool_failed`: 工具執行失敗
- `too_verbose`: 重複或囉嗦
- `not_actionable`: 無法操作
- `bad_format`: 格式不好

### 4.1.2 反饋強度指標

二元點贊不足以表達問題嚴重程度，因此建議增加：

| 指標名 | 定義 | 說明 |
| --- | --- | --- |
| `strong_negative_rate` | 強負反饋數 / 有反饋回答數 | 例如“錯誤”或“無法完成任務”類差評 |
| `recover_after_negative_rate` | 差評後被修復的比例 | 衡量 bot 的糾錯與恢復能力 |

---

## 4.2 會話結果層

這層用於回答“即便使用者沒點反饋，這次回答到底算不算成功”。

### 4.2.1 單輪解決率

| 指標名 | 定義 | 說明 |
| --- | --- | --- |
| `one_turn_resolution_rate` | 單輪解決回答數 / 總回答數 | 使用者一次提問後 bot 第一次正式回答即解決問題 |

可先使用以下代理訊號：

1. 使用者顯式好評。
2. 回答後短時間內無追問且會話結束。
3. 使用者後續切換到新話題，而不是繼續糾錯或重問。

### 4.2.2 重問率

| 指標名 | 定義 | 說明 |
| --- | --- | --- |
| `reask_rate` | 回答後短時間內同主題再次提問的比例 | 是最重要的隱式失敗訊號之一 |

重問訊號可包括：

- “不是這個意思”
- “你沒回答我的問題”
- “重新回答”
- “還是不對”
- 同主題關鍵詞在短時間內重複出現

### 4.2.3 澄清和解決輪次

| 指標名 | 定義 | 說明 |
| --- | --- | --- |
| `clarification_turn_rate` | 需要多輪澄清的會話佔比 | 衡量首答命中程度 |
| `avg_turns_to_resolution` | 從首次提問到解決的平均輪次 | 衡量整體問答效率 |

### 4.2.4 放棄和無回覆

| 指標名 | 定義 | 說明 |
| --- | --- | --- |
| `no_reply_rate` | `NO_REPLY` 回答佔比 | 衡量系統未回覆情況 |
| `abandonment_after_answer_rate` | 回答後用戶直接離開的比例 | 用於識別體驗斷點 |

---

## 4.3 執行質量層

這層用於回答“效果差的根因是什麼”。

### 4.3.1 響應效率指標

| 指標名 | 定義 | 說明 |
| --- | --- | --- |
| `response_latency_ms_p50/p95/p99` | 端到端回答耗時分位數 | 核心體驗指標 |
| `first_tool_latency_ms` | 首次工具呼叫前耗時 | 用於識別前置 LLM 慢或工具規劃慢 |
| `end_to_end_time_cost` | 單條回答總耗時 | 可直接複用現有 `time_cost` |
| `iteration_count_avg` | 平均迭代次數 | 反映 agent 複雜度和穩定性 |
| `tool_count_avg` | 平均工具呼叫數 | 反映問題依賴工具程度 |

### 4.3.2 LLM 質量代理指標

| 指標名 | 定義 | 說明 |
| --- | --- | --- |
| `answer_length_avg` | 平均回答長度 | 用於識別過短或過長 |
| `reasoning_present_rate` | 含 reasoning 的回答佔比 | 適用於支援 reasoning 的模型 |
| `tool_call_rate` | 觸發工具呼叫的回答佔比 | 看問題型別與工具依賴 |
| `multi_iteration_rate` | `iteration > 1` 的回答佔比 | 迭代過多通常意味著策略不穩 |
| `max_iteration_hit_rate` | 達到最大迭代限制的比例 | 是重要失敗訊號 |

### 4.3.3 工具執行質量指標

| 指標名 | 定義 | 說明 |
| --- | --- | --- |
| `tool_success_rate` | 成功工具呼叫數 / 總工具呼叫數 | 總體工具穩定性 |
| `tool_error_rate_by_name` | 按工具名統計的錯誤率 | 識別問題工具 |
| `tool_timeout_rate_by_name` | 按工具名統計超時率 | 識別慢工具 |
| `tool_result_used_rate` | 工具結果最終促成有效回答的比例 | 衡量工具有效性 |
| `tool_waste_rate` | 工具被呼叫但對結果無幫助的比例 | 衡量無效執行 |

### 4.3.4 成本質量比指標

| 指標名 | 定義 | 說明 |
| --- | --- | --- |
| `tokens_per_positive_answer` | 總 token / 正反饋回答數 | 評估成本效率 |
| `latency_per_positive_answer` | 總耗時 / 正反饋回答數 | 評估體驗效率 |
| `tool_calls_per_positive_answer` | 總工具數 / 正反饋回答數 | 看質量提升是否依賴複雜呼叫 |

---

## 4.4 歸因分析層

該層不是單獨的一組指標，而是要求前面所有指標都支援按關鍵維度切片。

建議將切片維度分成“當前階段可穩定支援的”與“後續增強補齊的”。

當前階段優先支援：

- `channel`
- `chat_type`
- `model`
- `provider`
- `session_type`
- `tool_used`
- `tool_name`
- `language`
- `user_segment`
- `time_bucket`

後續增強再補：

- `query_category`
- `prompt_version`
- `bot_version`

如果不支援這些維度切片，最終只能看到“整體效果一般”，但無法定位具體問題來源。這裡尤其要避免把 `query_category`、`prompt_version`、`bot_version` 誤寫成當前已經穩定存在的欄位來源。

---

## 5. 北極星指標與結果分級

## 5.1 北極星指標

考慮到當前實現尚無反饋入口、也無隱式 outcome 計算鏈路，北極星指標需要分階段定義。

### Phase 1 北極星指標

如果第一階段只能盯少量核心指標，建議優先使用以下五個：

1. `response_completed_count`
2. `response_latency_p95`
3. `tool_success_rate`
4. `max_iteration_hit_rate`
5. `no_reply_rate`

這五個指標都可以建立在當前程式碼已存在或只需極小補充的資料之上，能先回答“系統有沒有穩定產出答案”。

### Phase 2 北極星指標

在 `response_id` 和反饋入口穩定後，再升級為以下五個：

1. `good_answer_rate`
2. `one_turn_resolution_rate`
3. `reask_rate`
4. `thumbs_down_rate`
5. `response_latency_p95`

其中 `good_answer_rate` 建議作為 Phase 2 之後的綜合指標，定義如下：

```text
good_answer_rate =
(顯式正反饋回答數 + 隱式成功回答數) / 總回答數
```

隱式成功回答數可先使用以下判定：

- 非 `NO_REPLY`
- 非錯誤結束
- 非最大迭代耗盡
- 無短時間內重問
- 無顯式負反饋

## 5.2 回答結果分級

建議為每條最終回答打一個離散標籤 `outcome_label`，而不是隻做散亂的數值統計。

建議標籤如下：

- `excellent`
- `good`
- `neutral`
- `bad`
- `failed`

建議規則：

| 標籤 | 規則 |
| --- | --- |
| `excellent` | 有顯式好評，且無後續重問 |
| `good` | 無顯式反饋，但單輪結束，無重問 |
| `neutral` | 有繼續追問，但最終解決 |
| `bad` | 有差評，或短時間內重問/糾錯 |
| `failed` | 工具失敗、LLM error、無回答、達到最大迭代仍未完成 |

這樣所有統計都可以統一以 `outcome_label` 為基礎聚合。

---

## 6. 事件模型設計

為了支撐上述指標，需要補充結構化事件。當前 vikingbot 已經有過程事件，但還缺少結果與反饋事件。

這裡建議把事件模型拆成“必須先落地”和“後續增強”兩層，而不是一次性並列設計。

### 6.0 當前已存在的過程事件

當前程式碼裡已經存在但尚未沉澱為分析事實表的過程事件包括：

- `REASONING`
- `TOOL_CALL`
- `TOOL_RESULT`
- `ITERATION`
- `NO_REPLY`

這些事件更適合用於線上流式展示和單次問題排查，不適合作為最終分析主表。後續新增事件應圍繞“最終回答”來建立主鍵和關聯關係。

### 6.0.1 分階段事件落地狀態

截至當前程式碼狀態：

1. Phase 1 已經落地 `response_completed` 相關主鏈路。
2. Phase 2 當前工作樹已經落地 `feedback_submitted` 與 `/bot/v1/feedback`。
3. `response_outcome_evaluated` 已進入第三階段實現，當前版本僅覆蓋 session 歷史加顯式反饋的最小規則推導。

## 6.1 `response_completed`

該事件在最終回答產生時記錄，是整套分析的主事實表。

當前實現狀態補充：

1. `response_completed` 當前已經在 `AgentLoop` 中標準化構建。
2. 同一份 payload 會寫入 `session.metadata["response_facts"][response_id]`，並隨 session save 持久化到 JSONL metadata 首行。
3. 同一份 payload 也會寫入 Langfuse generation metadata。
4. 該事件仍然是 analytics-only，不會暴露到 OpenAPI 對外返回或使用者可見 channel。

建議欄位：

| 欄位名 | 說明 |
| --- | --- |
| `response_id` | 回答唯一 ID |
| `trace_id` | 對應 Langfuse trace ID，如當前階段難以穩定獲取可先留空 |
| `session_id` | 會話 ID |
| `user_id` | 使用者 ID |
| `channel` | 渠道 |
| `chat_type` | 單聊/群聊等，如當前階段無統一來源可先從 channel metadata 推斷 |
| `model` | 模型名 |
| `provider` | provider 名，如當前階段無穩定欄位可由 provider 配置推導 |
| `message_id` | 原始訊息 ID，如 channel 無該概念可為空 |
| `time_cost_ms` | 端到端耗時 |
| `prompt_tokens` | 輸入 token |
| `completion_tokens` | 輸出 token |
| `total_tokens` | 總 token |
| `iteration_count` | 迭代次數 |
| `tool_count` | 工具呼叫數 |
| `tools_used_names` | 工具名列表 |
| `finish_reason` | LLM 結束原因，如當前未顯式透出則可先根據 provider 返回補齊 |
| `has_reasoning` | 是否有 reasoning 內容；當前階段也可先退化為“是否產生過 reasoning 事件” |
| `response_length` | 回答長度 |
| `query_category` | 問題分類，第二階段再補 |
| `prompt_version` | prompt 版本，第二階段再補 |
| `bot_version` | bot 版本，第二階段再補 |

其中當前階段最低要求欄位應收斂為：

- `response_id`
- `session_id`
- `user_id`
- `channel`
- `time_cost_ms`
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `iteration_count`
- `tool_count`
- `tools_used_names`
- `response_length`
- `created_at`

## 6.2 `feedback_submitted`

該事件在使用者提交點贊、點踩、評分或文字反饋時記錄。

該事件不應作為 MVP 前提。只有在 `response_id` 已經能從客戶端拿到並可靠回傳後，才值得接入。

當前實現狀態補充：

1. OpenAPI 已提供 `POST /bot/v1/feedback`。
2. 反饋按 `response_id` 回查 assistant message；找不到時返回 `404 Response not found`。
3. 反饋會追加寫入 session JSONL metadata 下的 `feedback_events`。
4. 反饋會發布 `feedback_submitted` analytics 事件，但不會向用戶側 channel 透出。

建議欄位：

| 欄位名 | 說明 |
| --- | --- |
| `response_id` | 關聯的回答 ID |
| `session_id` | 會話 ID |
| `user_id` | 使用者 ID |
| `feedback_type` | `thumb_up` / `thumb_down` / `rating` |
| `feedback_score` | 數值評分 |
| `feedback_reason` | 差評原因標籤 |
| `feedback_text` | 使用者補充說明 |
| `feedback_delay_sec` | 回答到反饋的間隔 |

## 6.3 `response_outcome_evaluated`

該事件由系統後處理產生，用於沉澱隱式結果判斷。

當前實現狀態補充：

1. 該事件已經以 analytics-only 方式落地，不會透傳到使用者可見 channel。
2. 當前在兩個時機觸發：顯式反饋寫入時，以及新一輪 user turn 到來前對上一條 assistant response 做隱式評估時。
3. 評估結果當前寫入 session JSONL metadata 下的 `response_outcomes[response_id]`。
4. 當前規則版優先使用顯式 `thumb_up` / `thumb_down`，否則結合 10 分鐘內 follow-up、後續 user turn 數和是否缺少反饋來推導 outcome。
5. 當前實現是 Phase 3 的最小可用版本，不等同於完整離線 judge 或評審模型。

補充說明：`response_outcomes` 當前只覆蓋“已經被顯式反饋或被後處理規則評估過”的回答，不能等價替代總回答事實表。因此 summary / channel 聚合中的 `responses_total` 不能從 `response_outcomes` 推導，而應從 assistant `response_id` 記錄統計。

該事件建議放在第三階段持續增強，因為它依賴：

- session 歷史中能穩定關聯 user / assistant 訊息
- `response_id` 已經繫結到 assistant 最終回答
- 對“重問/糾錯/切換話題/放棄”已有穩定規則

建議欄位：

| 欄位名 | 說明 |
| --- | --- |
| `response_id` | 回答 ID |
| `resolved_in_one_turn` | 是否單輪解決 |
| `reask_within_10m` | 10 分鐘內是否重問 |
| `clarification_turns` | 後續澄清輪次 |
| `follow_up_without_feedback` | 是否出現 follow-up 且無顯式反饋 |
| `outcome_label` | 最終結果標籤 |

---

## 7. Query 分類設計

問答效果不能只看總體平均值，必須按問題型別分層。

但結合當前實現，`query_category` 不應作為 Phase 1 前提，而應放到 Phase 2 之後補齊。

第二階段建議至少支援以下分類：

- `general_qa`
- `code_explanation`
- `bug_diagnosis`
- `file_operation`
- `shell_execution`
- `web_search`
- `workflow_task`
- `memory_or_profile`

後續可以進一步擴充成更穩定的分類：

- `factual`
- `reasoning`
- `retrieval_heavy`
- `tool_heavy`
- `multi_step`
- `social_chitchat`

分類來源可以按階段逐步演進：

1. 先使用規則或關鍵字分類，並明確這是增強能力而非現狀能力。
2. 再引入離線模型分類。
3. 最終沉澱為穩定的業務問題 taxonomy。

---

## 8. 與 Langfuse 的整合設計

Langfuse 適合作為 trace 容器、壞樣本入口和鏈路診斷工具，但不建議把全部業務分析都壓在 Langfuse 查詢上。

結合當前實現，需要先明確“已經有的”和“還沒有的”。

當前已經有：

- `trace` 裝飾器會透傳 `session_id`、`user_id`
- provider 會寫入 LLM generation
- tool registry 會寫入 tool span，並附帶 `success`、`duration_ms`

當前還沒有：

- 統一寫入 generation / trace 的 `query_category`
- 統一寫入 generation / trace 的 `prompt_version`、`bot_version`
- 統一且完善的 outcome 聚合檢視；當前已落地的是 trace event `response_outcome_evaluated` 與 observation score `response_outcome_label`

## 8.1 Langfuse 中應承載的內容

建議按三類承載資訊，而不是把所有欄位都塞進 generation metadata：

1. trace / generation metadata：
- `response_id`
- `channel`
- `chat_type`
- `query_category`
- `session_type`
- `iteration_count`
- `tool_count`
- `tool_names`
- `prompt_version`
- `bot_version`

2. outcome event：
- `response_outcome_evaluated`

3. outcome score：
- `response_outcome_label`

對於 Phase 3 當前實現，需要明確避免一種不準確表述：不要寫成“在顯式 feedback 之後把 `final_outcome_label` 回寫到已結束 generation metadata”。真實落地方式是把 outcome 寫到原 trace 下的 event，並把離散標籤寫到對應 observation score。

其中建議的接入優先順序是：

1. 先補 `response_id`、`iteration_count`、`tool_count`、`tool_names`
2. 再補 `query_category`
3. Phase 3 outcome 統一使用 `response_outcome_evaluated` event + `response_outcome_label` score
4. 最後再補 `prompt_version`、`bot_version`

## 8.2 Langfuse score 建議

建議將關鍵結果寫入 Langfuse score，方便直接篩 trace：

- `response_outcome_label`
- `user_feedback_score`
- `implicit_resolution_score`
- `response_quality_score`
- `tool_execution_score`
- `latency_satisfaction_score`

其中：

- `response_outcome_label` 適合使用離散列舉值，例如 `positive_feedback`、`negative_feedback`、`reasked`、`resolved`
- `user_feedback_score` 可取 `1 / 0 / -1`
- `implicit_resolution_score` 可取 `1 / 0`
- `response_quality_score` 可為綜合分

## 8.3 Langfuse 與分析倉庫的關係

建議職責分工如下：

| 系統 | 職責 |
| --- | --- |
| Langfuse | trace 展示、樣本回溯、執行鏈路診斷、壞案例篩選 |
| 業務事件倉庫 | 指標聚合、趨勢分析、A/B 對比、報表與告警 |

換句話說，Langfuse 用來回答“這條壞樣本具體發生了什麼”，而聚合分析系統用來回答“最近哪類問題整體變差了”。

---

## 9. Dashboard 與告警設計

## 9.1 建議的三個 Dashboard

Dashboard 同樣需要分階段理解：

- Phase 1 先做“執行穩定性看板”和“執行診斷看板”
- Phase 2 之後再補“業務效果看板”和“差評分析看板”

### 9.1.1 業務效果看板

該看板屬於 Phase 2 及之後。

建議展示：

- `good_answer_rate`
- `one_turn_resolution_rate`
- `thumbs_down_rate`
- `reask_rate`

支援按以下維度切片：

- 時間
- 模型
- channel
- query_category

### 9.1.2 執行診斷看板

建議展示：

- `response_latency_p95`
- `tool_error_rate_by_name`
- `max_iteration_hit_rate`
- `response_completed_count`

支援按以下維度切片：

- provider
- tool_name

`prompt_version` 相關切片應放到後續增強階段，前提是程式碼中已經有穩定欄位來源。

### 9.1.3 差評分析看板

該看板同樣屬於 Phase 2 及之後。

建議展示：

- 差評原因分佈
- 差評樣本 Top N
- 差評 trace 中常見工具鏈
- 差評 query_category 排名

## 9.2 告警建議

建議優先配置以下五類告警：

1. `response_latency_p95` 超閾值
2. `tool_success_rate` 突降
3. `max_iteration_hit_rate` 突增
4. `no_reply_rate` 突增
5. `response_completed_count` 異常下降

在 Phase 2 接入反饋後，再補：

1. `thumbs_down_rate` 突增
2. `good_answer_rate` 突降

這些告警比單純盯錯誤日誌更接近真實使用者體驗變化。

---

## 10. 分階段落地計劃

## 10.1 Phase 1: MVP

第一階段先做最小可用版本，目標是快速建立結構化響應事實閉環。

建議優先落地：

1. `response_id` 機制
2. `response_completed` 事件
3. 在 `OutboundMessage`、session message、OpenAPI 響應中透出 `response_id`
4. Langfuse trace / generation metadata 關聯 `response_id`
5. 最小指標集

MVP 指標集建議為：

1. `response_completed_count`
2. `response_latency_p95`
3. `tool_success_rate`
4. `tool_error_rate_by_name`
5. `max_iteration_hit_rate`
6. `no_reply_rate`
7. `avg_iteration_count`
8. `avg_tool_count`

說明：原始 Phase 1 規劃裡，這些結果指標並不屬於必須項；但截至當前工作樹，`feedback_coverage`、`thumbs_up_rate`、`thumbs_down_rate`、`one_turn_resolution_rate`、`reask_rate` 已經具備最小可用的資料入口與離線聚合能力。當前需要強調的不是“是否存在”，而是“口徑是否統一”，尤其是 `responses_total` 必須基於所有 assistant `response_id`，而不是 `response_outcomes`。

## 10.2 Phase 2: 增強歸因能力

第二階段重點提升分析和歸因能力。

截至當前工作樹，以下第 1、2 項已經進入實現狀態，並且已經通過 `openviking-server --with-bot` 完成真實代理路徑驗證；後續重點應放在補充更系統的驗證沉澱與指標消費，而不是把尚未完成的 Phase 3 能力提前寫成已實現。

建議增加：

1. 點贊/點踩反饋入口與 `feedback_submitted` 事件
2. OpenAPI 反饋介面或統一 feedback webhook
3. query 分類
4. `feedback_coverage`
5. `thumbs_up_rate`
6. `thumbs_down_rate`
7. `negative_rate_by_query_category`
8. `model_comparison_by_query_category`

## 10.3 Phase 3: 離線評測與評審模型

第三階段再考慮引入隱式 outcome 判斷與離線質量評審能力。

截至當前工作樹，`response_outcome_evaluated` 的最小規則版已經落地；後續重點從“是否實現”轉為“規則是否足夠穩健、指標如何消費、是否接入 judge”。

建議先補：

1. 增強 `response_outcome_evaluated` 後處理
2. `one_turn_resolution_rate`
3. `reask_rate`
4. `good_answer_rate`
5. `outcome_label`
6. `recover_after_negative_rate`
7. `tool_helpfulness_rate_by_name`
8. `tokens_per_positive_answer`
9. `latency_vs_feedback_correlation`

建議引入 LLM-as-a-Judge，為每條回答提供輔助分數：

- `relevance_score`
- `correctness_score`
- `completeness_score`
- `actionability_score`
- `tone_score`

這一層只能作為輔助，不應替代真實使用者反饋。

---

## 11. 與當前 vikingbot 架構的對應關係

結合當前程式碼結構，建議的最小落點如下：

1. 在 `vikingbot.bus.events.OutboundMessage` 增加 `response_id` 字段。
2. 在 `AgentLoop._process_message` 生成最終 `OutboundMessage` 前建立 `response_id`。
3. 在 `session.add_message("assistant", ...)` 時把 `response_id` 一併寫入 JSONL 訊息。
4. 在 OpenAPI `ChatResponse` 與流式最終事件中返回 `response_id`，讓客戶端具備回傳反饋的主鍵。
5. 在 agent loop 中構建標準化 `response_completed`，並隨 session save 將其寫入 `session.metadata["response_facts"]`，同時繼續以 analytics-only 事件形式釋出。
6. 在 Langfuse generation / tool span metadata 中寫入 `response_id`、`iteration_count`、`tool_count`、`tool_names`。

第二階段再補：

1. OpenAPI 反饋介面。
2. channel 側反饋事件接入。
3. `feedback_submitted` 事件。
4. `query_category`、`prompt_version`、`bot_version` 的欄位來源。

第三階段再補：

1. 基於 session 歷史的 `response_outcome_evaluated` 後處理。
2. 更穩健的 `outcome_label` 規則。
3. 單輪解決、重問、放棄等隱式結果指標消費。

因此，第一階段無需大改 agent 主迴圈，但也不只是把“最終回答”和“後續反饋”關聯起來，而是要先把“最終回答本身”沉澱成結構化、可關聯、可復盤的響應事實。

---

## 12. 風險與注意事項

### 12.1 反饋覆蓋率不足

如果使用者反饋入口不明顯，最終會導致顯式反饋覆蓋率過低。因此不能只依賴點贊/點踩，必須同時建設隱式成功指標。

### 12.2 不能讓高基數字段汙染通用指標系統

像 `session_id`、`user_id`、完整錯誤文本、完整問題文本，不適合直接進入高頻指標標籤。它們更適合存到事件系統或 trace metadata。

### 12.3 LLM Judge 不能替代真實使用者

離線模型評分可以幫助排序和篩樣本，但不能當成使用者體驗的真實代表。

### 12.4 反饋體系要支援版本對比

若沒有 `prompt_version`、`bot_version`、`model` 等欄位，後續幾乎無法評估最佳化是否有效。

### 12.5 不要把“設想中的欄位”誤當成“現有能力”

本次複核發現，設計文件最容易偏離現狀的地方，不在於指標定義本身，而在於把“應該有的欄位”寫成了“已經穩定存在的欄位”。

後續繼續推進時需要遵守兩個原則：

1. 文件中的“當前已有能力”必須只寫程式碼裡已經穩定產出的欄位和事件。
2. 文件中的“建議欄位”必須明確區分為 MVP 必需、第二階段補齊、第三階段增強，避免把實現順序倒置。

---

## 13. 結論

vikingbot 的問答效果反饋觀測，不能只停留在 token、trace 和工具呼叫層面，必須建立從“執行過程”到“最終結果”的完整鏈路。

本方案建議的主線是：

1. 以 `response_completed` 為核心事實事件。
2. 先建立響應事實，再疊加顯式反饋和隱式結果。
3. Phase 1 先用 `response_completed_count`、`response_latency_p95`、`tool_success_rate`、`max_iteration_hit_rate`、`no_reply_rate` 保障系統穩定性；Phase 2 之後再升級為效果類北極星指標組合。
4. 通過 Langfuse trace + 業務事件聚合實現從趨勢發現到壞樣本回溯的閉環。

最終目標不是“記錄更多日誌”，而是讓團隊能夠明確回答：

- 哪些回答真的好。
- 哪些回答正在變差。
- 為什麼變差。
- 改完以後是否真的變好。

---

## 14. Verification

如需對當前最小實現做 targeted 驗證，推薦使用 `uv` 執行以下回歸集：

```bash
uv run --extra test --extra bot -m pytest bot/tests/test_feedback_stats.py bot/tests/test_openapi_auth.py bot/tests/test_outcome_evaluator.py bot/tests/test_agent_loop_outcome.py tests/metrics/collectors/test_feedback_collector.py tests/server/test_prometheus_metrics.py
```

預期結果：

1. feedback stats、OpenAPI feedback、outcome evaluator、agent loop `response_facts` 持久化相關用例全部通過
2. feedback collector 與 `/metrics` 暴露相關用例全部通過

## 15. Related Docs

- [OpenViking Metrics 概念文件](../../docs/zh/concepts/12-metrics.md) - feedback 指標族、PromQL 示例與 `/metrics` 暴露說明
- [OpenViking Metrics API 文件](../../docs/zh/api/09-metrics.md) - `/metrics` 端點行為與抓取方式
