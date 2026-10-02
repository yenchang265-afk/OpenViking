# Tool Stub 設計文件

**範圍**: Business Data Platform 當前 `tool stub` 能力的實現說明，覆蓋型別識別、規則化摘要、原文外接、回溯讀取與測試邊界。
**狀態**: 已實現，本文件描述當前程式碼行為，不額外引入新需求。

---

## 概述

Business Data Platform 原生已經支援 tool result preview。原有鏈路能夠在 session 寫入階段把過大的 tool output externalize，並在 `ToolPart` 中留下一個 preview stub，同時保留 ref 供後續回溯。

這次工作的重點不是新建 externalize 機制，而是在現有能力上最佳化 preview 的生成方式：從偏 `head + tail` 的直接截斷，升級為按內容型別輸出更穩定、更可讀的規則化摘要。

換句話說，本次改動保持下面這些基礎能力不變：

1. 哪些 tool output 需要 externalize，仍由 session 寫入階段決定。
2. 原始內容仍寫入 `ToolResultStore`。
3. `ToolPart` 仍保留 stub 和 `tool_output_ref`。
4. 原文回溯方式仍是 `read/search/list`。

這次變化主要集中在 preview 生成層：

1. 在 session 寫入階段識別哪些 tool output 需要 externalize。
2. 原始輸出寫入 session 下的 tool result store。
3. preview 從簡單截斷最佳化為基於內容和 MIME 的 deterministic synopsis。
4. 把原始 `ToolPart.tool_output` 替換成 stub 文本，並保留 `tool_output_ref`。
5. 後續通過 `read/search/list` 工具按 ref 回溯原文。

`text` 型別只做規則化摘要，不接 LLM。

---

## 設計目標

1. 在保留 OV 原生 externalize 和 ref 回溯鏈路的前提下，最佳化 preview 的可讀性。
2. 減少大 tool output 對上下文視窗的佔用。
3. 把原有偏 `head + tail` 的截斷 preview，升級為按型別輸出的規則化摘要。
4. 對常見文本型輸出給出穩定、可讀的 deterministic synopsis。
5. 保留原始輸出，支援按 ref 精確回溯。
6. 當前版本不做 LLM 摘要，只做 deterministic 的規則化摘要。

---

## 端到端流程

### 1. 選擇哪些輸出需要 externalize

入口在 [session.py](https://github.com/volcengine/OpenViking/blob/main/openviking/session/session.py#L685) 的 `_externalize_large_tool_output_group()`。

當前按兩類條件觸發：

1. 單個 tool output 超過 `threshold_chars`。
2. 同一個 assistant turn 中多個 tool output 的總 inline 體積超過 `assistant_turn_inline_budget_chars`。

命中後會進入 externalization 流程。觸發閾值仍沿用 OV 原有配置；規則化摘要本身不改變“什麼時候 externalize”。

### 2. 外接原始結果並替換 ToolPart

入口在 [session.py](https://github.com/volcengine/OpenViking/blob/main/openviking/session/session.py#L606) 的 `_externalize_tool_part()`。

這一步會：

1. 把原始 `tool_output` 寫入 `ToolResultStore`。
2. 呼叫 preview 生成邏輯產出 stub 文本。
3. 用 stub 替換 `ToolPart.tool_output`。
4. 把原始結果的 ref 寫入 `ToolPart.tool_output_ref`。

因此被 stub 後，訊息裡保留的是 preview，不再是完整原始 tool result；原始結果仍在外接儲存裡。

### 3. 生成 synopsis 和 stub

入口在 [tool_result_store.py](https://github.com/volcengine/OpenViking/blob/main/openviking/session/tool_result_store.py#L38) 的 `make_preview()`：

1. 原生 preview/stub 能力保留，但內容生成邏輯從簡單截斷演進為 typed synopsis。
2. `generate_tool_result_synopsis()` 負責型別識別和摘要生成。
3. `render_tool_result_stub()` 負責把摘要渲染成最終 stub 文本。

核心實現位於 [tool_result_synopsis.py](https://github.com/volcengine/OpenViking/blob/main/openviking/session/tool_result_synopsis.py#L363)。

當前原則：

1. externalize 觸發閾值沿用 OV 原有配置。
2. 常見型別使用固定規則上限生成 synopsis，不依賴 `preview_chars` 控制摘要長度。
3. `preview_chars` 只作為無法規則化時的 fallback head/tail 取樣預算，並作為相容欄位保留在 stub header / metadata 中。

### 4. 原文回溯

當前回溯能力由 session 暴露三類工具：

1. [session.py](https://github.com/volcengine/OpenViking/blob/main/openviking/session/session.py#L932) `read_tool_result()`：按 `offset/limit` 讀取原始內容片段。
2. [session.py](https://github.com/volcengine/OpenViking/blob/main/openviking/session/session.py#L952) `search_tool_result()`：在原始內容中做關鍵字搜尋。
3. [session.py](https://github.com/volcengine/OpenViking/blob/main/openviking/session/session.py#L972) `list_tool_results()`：列出當前 session 已 externalize 的結果。

對應儲存層實現位於 [tool_result_store.py](https://github.com/volcengine/OpenViking/blob/main/openviking/session/tool_result_store.py#L77)。

---

## 支援的資料型別

當前支援的 synopsis kind 定義在 [tool_result_synopsis.py](https://github.com/volcengine/OpenViking/blob/main/openviking/session/tool_result_synopsis.py#L18)：

`json` / `csv` / `tsv` / `yaml` / `xml` / `code` / `text` / `unknown`

### 型別對照表

| 型別 | 識別方式 | 處理辦法 | stub 中保留內容 |
|---|---|---|---|
| `json` | MIME 含 `json`，或內容以 `{` / `[` 開頭且能被 JSON decoder 解析 | 解析 top-level shape，提取 keys、array length、標量示例 | `summary + structure + notable_items` |
| `csv` | 含逗號，且能按 CSV 讀成規則表格 | 統計行列數、列名，保留首條資料樣例 | `summary + structure` |
| `tsv` | 含製表符，且能按 TSV 讀成規則表格 | 統計行列數、列名，保留首條資料樣例 | `summary + structure` |
| `yaml` | 滿足 YAML 啟發式並能 `yaml.safe_load()` 成 dict/list | 提取 top-level keys 和 child type | `summary + structure` |
| `xml` | MIME 含 `xml`，或內容以 `<` 開頭且可解析 | 提取 root tag、屬性數、子標籤計數 | `summary + structure` |
| `code` | 命中程式碼模式正則 | 提取 imports、symbols、line_count | `summary + structure + notable_items` |
| `text` | 作為最終 fallback | 規則化文本摘要，不保留全文 sample | `summary` |
| `unknown` | 空內容、binary-like 內容，或帶明確 MIME 但解析失敗的結構化內容 | 無法規則化時使用 fallback head/tail sample | `summary + sample` |

---

## 型別識別順序

識別順序定義在 [tool_result_synopsis.py](https://github.com/volcengine/OpenViking/blob/main/openviking/session/tool_result_synopsis.py#L363)。

當前順序如下：

1. 空內容：直接標為 `unknown`。
2. binary-like 內容：如果出現 NUL 或控制字元比例過高，標為 `unknown`。
3. `json`
4. `xml`
5. `tsv`
6. `csv`
7. `yaml`
8. `code`
9. 最終 fallback 為 `text`

這個順序的目的是優先識別結構化格式，再識別程式碼，最後才把剩餘內容視作普通文本。日誌樣式輸出不再作為獨立型別處理，會走 `text`，與 lossless-claw 的 large-file exploration 行為保持一致。

---

## 各型別處理策略

### JSON

實現位於 [tool_result_synopsis.py](https://github.com/volcengine/OpenViking/blob/main/openviking/session/tool_result_synopsis.py#L150)。

輸出重點：

1. 頂層型別是 object 還是 array。
2. top-level keys，最多 10 個。
3. 子字段是 object / array / scalar。
4. 最多若干條標量示例。
5. 若第一個 JSON value 後還有額外字元，會記入 `trailing_chars_after_first_json_value`。
6. 不額外保留原始 JSON sample。

### CSV / TSV

實現位於 [tool_result_synopsis.py](https://github.com/volcengine/OpenViking/blob/main/openviking/session/tool_result_synopsis.py#L218)。

輸出重點：

1. 列數與資料行數。
2. 首行列名。
3. 首條資料樣例，最多 180 字元。

只接受“列數基本一致”的表格；不規則分隔文本不會被誤判成表格。

### YAML

實現位於 [tool_result_synopsis.py](https://github.com/volcengine/OpenViking/blob/main/openviking/session/tool_result_synopsis.py#L184) 與 [tool_result_synopsis.py](https://github.com/volcengine/OpenViking/blob/main/openviking/session/tool_result_synopsis.py#L268)。

輸出重點：

1. 頂層是 object 還是 array。
2. top-level keys，最多 30 個。
3. 每個 key 對應的 child type。
4. 不額外保留 YAML sample。

### XML

實現位於 [tool_result_synopsis.py](https://github.com/volcengine/OpenViking/blob/main/openviking/session/tool_result_synopsis.py#L204)。

輸出重點：

1. 根標籤名。
2. 根節點屬性數量。
3. 一級子標籤頻次，最多 30 個。
4. 不額外保留 XML sample。

### Code

實現位於 [tool_result_synopsis.py](https://github.com/volcengine/OpenViking/blob/main/openviking/session/tool_result_synopsis.py#L280)。

輸出重點：

1. 總行數。
2. import 語句，最多 12 條，單條最多 180 字元。
3. 頂層 symbol，如 `class Foo`、`def bar`、`fn baz`，最多 24 條，單條最多 200 字元。
4. 不額外保留 head/tail sample。

當前是輕量規則識別，不做 AST 級程式碼摘要。

### Text

實現位於 [tool_result_synopsis.py](https://github.com/volcengine/OpenViking/blob/main/openviking/session/tool_result_synopsis.py#L319)。

`text` 型別明確不接 LLM，只做 deterministic fallback。摘錄採用固定上限，不受 `preview_chars` 影響。

日誌樣式輸出也歸入 `text`。如果需要定位錯誤/警告行，優先通過 stub 中的 ref 使用 `openviking_tool_result_search` 搜尋原始 payload，避免僅靠關鍵字把普通文件誤判成日誌。

輸出重點：

1. `Characters`
2. `Words`
3. `Lines`
4. `Detected section headers`
5. `Opening excerpt`
6. `Closing excerpt`

標題提取規則：

1. Markdown 標題，如 `# Heading`
2. 全大寫風格標題行，如 `SYSTEM STATUS`

摘錄規則：

1. opening excerpt 固定最多取前 500 字符。
2. closing excerpt 固定最多取後 500 字元。
3. 先壓縮空白，再寫入摘要。
4. 不額外保留 `sample` 欄位，避免把完整原文重新帶回上下文。

### Unknown

`unknown` 是當前實現裡的保守分類，不是富型別支援。

當前會落到 `unknown` 的場景包括：

1. 輸出為空。
2. 文本中存在明顯二進位制控制字元。
3. MIME 明確標成 JSON/XML，但內容解析失敗。

對這些內容，stub 保留基礎說明；非空內容會使用 `preview_chars` 生成 head/tail fallback sample。原始 payload 仍通過 ref 回溯。

---

## Stub 文本結構

渲染邏輯位於 [tool_result_synopsis.py](https://github.com/volcengine/OpenViking/blob/main/openviking/session/tool_result_synopsis.py#L436)。

當前 stub 由兩部分組成：

### Header

包含：

1. `tool_name`
2. `kind`
3. `original_chars`
4. `preview_chars`
5. `ref`
6. `sha256`
7. `reason`

### Body

按 synopsis 內容選擇性渲染：

1. `Synopsis`
2. `Structure`
3. `Notable items`
4. `Sample`
5. `Explore`

其中 `Explore` 會提示模型使用：

1. `openviking_tool_result_search`
2. `openviking_tool_result_read`
3. `openviking_tool_result_list`

---

## 原始內容儲存與回溯

實現位於 [tool_result_store.py](https://github.com/volcengine/OpenViking/blob/main/openviking/session/tool_result_store.py#L101)。

每個 externalized tool result 會寫入兩類檔案：

1. `output.txt`：原始輸出內容。
2. `metadata.json`：後設資料和 synopsis。

後設資料包括：

1. `tool_result_id`
2. `session_id`
3. `message_id`
4. `tool_id`
5. `tool_name`
6. `created_at`
7. `original_chars`
8. `preview_chars`
9. `sha256`
10. `mime_type`
11. `synopsis_kind`
12. `synopsis`
13. `storage_uri`
14. `output_uri`
16. `offset_unit=unicode_code_point`

### 讀取方式

1. `read()`：按 `offset/limit` 讀取原始文本片段，適合長文本逐段展開。
2. `search()`：在原始文本中查關鍵詞，並返回帶 offset 的 snippet。
3. `list()`：按 session 列出已有外接結果，便於發現 ref。

當前讀取模型是“面向長文本”的；它適合回看日誌、程式碼、表格文本、普通文本。

---

## 當前邊界與取捨

1. `text` 不接 LLM，原因是我們當前只需要穩定、低成本、可測試的規則化 stub。
2. 當前回溯介面是 `read/search/list`，更適合大文本原文回看。
3. `offset/limit` 對“順序文本展開”很合適，但對圖片、二進位制、複雜多模態結果並不理想。

---

## 測試覆蓋

當前相關測試包括：

1. [test_tool_result_synopsis.py](https://github.com/volcengine/OpenViking/blob/main/tests/session/test_tool_result_synopsis.py#L1)：覆蓋型別識別和 synopsis 生成，包括固定 caps、text 的 500/500 deterministic fallback，以及 unknown 的 head/tail fallback。
2. [test_tool_result_externalization.py](https://github.com/volcengine/OpenViking/blob/main/tests/session/test_tool_result_externalization.py#L1)：覆蓋 externalization、stub 替換、閾值邊界、aggregate budget、ref 回溯等端到端流程。
3. [test_api_sessions.py](https://github.com/volcengine/OpenViking/blob/main/tests/server/test_api_sessions.py#L190)：覆蓋 HTTP API 層的 tool result externalization、stub 文案、`read/list/search` 回溯，以及 `synopsis_kind` / `synopsis.kind` 後設資料透出。

當前相關測試共 29 個用例通過，可作為後續繼續補齊真實輸出迴歸用例的基礎。

---

## 結論

Business Data Platform 當前的 `tool stub` 已經具備一版完整閉環：

1. OV 原生的 externalize、preview stub、ref 回溯鏈路繼續保留。
2. preview 生成方式已從偏 `head + tail` 的截斷，升級為按型別的規則化摘要。
3. `text` 型別採用 deterministic 規則摘要，不接 LLM。
4. 能通過 `read/search/list` 對外接原文進行回溯。

後續優先順序應放在更深的迴歸測試、更多真實輸出樣本，以及是否需要繼續最佳化 `read/search/list` 的原文回溯體驗，而不是先擴充 LLM 摘要或媒體解析。
