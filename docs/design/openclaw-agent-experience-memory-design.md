# OpenClaw 接入 Business Data Platform Agent Experience Recall 設計

日期：2026-05-28

## 當前結論

Business Data Platform 已經負責從 session commit 後的軌跡中抽取 agent experience。本 PR 不重做經驗抽取、不改 commit policy，也不新增“長期記憶/經驗記憶是否抽取”的控制面。

本 PR 只做執行期使用面：

1. 經驗記憶功能預設關閉，必須顯式配置 `agentExperience.enabled: true` 才啟用。
2. 啟用後，OpenClaw 在 `transformContext assemble` 階段判斷當前 turn 是否像執行任務。
3. 符合條件時，從 `viking://user/memories/experiences` 檢索 agent experience。
4. 同一輪也保留原有長期記憶 auto recall，並把 experience 和長期記憶分成不同 section。
5. 使用統一的 `<openviking-context>` 外殼注入到 latest user message 前；即使只有長期記憶，也使用這個外殼。
6. `afterTurn` 寫 session 前剝離 `<openviking-context>`，避免把召回內容再次寫回 OV。

這是一版“OpenClaw 能用 OV 經驗記憶”的基準實現，不是完整的多 hook experience system。

## 不在本 PR 中處理的事

以下內容明確不屬於本 PR：

- 不新增或修改 OV 服務端的 trajectory -> experience 抽取邏輯。
- 不新增 commit 時的 extraction policy。一次 commit 是否抽長期記憶、是否抽 experience，由 OV core 後續控制面解決。
- 不改變現有 `afterTurn()` session capture 主鏈路。
- 不改變現有 `compact()` / `commitSession()` 觸發策略。
- 不新增 OpenClaw host hook。
- 不實現 skill load / subagent start / write preflight 的自動注入。
- 不新增 `experience_recall` 工具。
- 不把 experience 和普通長期記憶混成同一種記憶格式。

## 為什麼接在 transformContext assemble

OpenClaw 外掛當前有兩類 assemble：

- preflight assemble：用於回讀 OV session context，把已有 session 上下文給 OpenClaw。
- transformContext assemble：LLM 看到訊息前最後一次改寫訊息上下文。

經驗記憶是“執行前提醒”，應該發生在 LLM 決策前。當前 OpenClaw 外掛沒有 MemOS 那種 `before_prompt_build` hook，也沒有 `before_subagent_start` / 可中斷 `before_tool_call`。因此當前可落地的正確位置是 transformContext assemble。

當前程式碼路徑：

```text
examples/openclaw-plugin/context-engine.ts
  assemble()
    -> isTransformContextAssemble
    -> latestMessage.role === "user"
    -> prepareRecallQuery()
    -> shouldRecallAgentExperience()
    -> buildAgentExperienceRecallContext()
    -> buildLongTermMemoryRecallContext()
    -> buildOpenVikingContextBlock()
    -> prependRecallToLatestUserMessage()
```

## 當前 PR 的檔案改動

### `examples/openclaw-plugin/config.ts`

新增 `agentExperience` 配置，並在 parse 階段補齊預設值：

```ts
agentExperience?: {
  enabled?: boolean;
  recallLimit?: number;
  scoreThreshold?: number;
  maxInjectedChars?: number;
  minQueryChars?: number;
};
```

預設值：

```ts
{
  enabled: false,
  recallLimit: 3,
  scoreThreshold: 0.35,
  maxInjectedChars: 6000,
  minQueryChars: 12,
}
```

`enabled` 預設是 `false`，這是保守釋出開關：預設不觸發 experience recall，也不增加額外檢索請求。使用者確認服務端 experience 資料質量和注入效果後，再顯式開啟。

`ParsedMemoryOpenVikingConfig` 是 schema parse 後的執行期型別，重點是讓 `agentExperience` 的子欄位也變成 required，避免 TypeScript 仍然認為 `recallLimit` / `maxInjectedChars` 可能是 undefined。

### `examples/openclaw-plugin/auto-recall.ts`

新增經驗召回相關邏輯，但仍放在 `auto-recall.ts` 中。原因是當前外掛還沒有統一 recall source 目錄體系，經驗召回和長期記憶召回共享 query preparation、timeout、token estimate、context block 構造等基礎設施。

核心新增/調整：

- `OPENVIKING_CONTEXT_TAG = "openviking-context"`
- `ExperienceRecallTrigger`
- `shouldRecallAgentExperience()`
- `isCronSession()`
- `buildAgentExperienceRecallContext()`
- `buildOpenVikingContextBlock()`
- `buildLongTermMemorySection()`
- `buildLongTermMemoryRecallContext()` 過濾掉 experience memory，避免 experience 出現在長期記憶區；同時生成 `Long-term Memories` section，交給統一外殼注入。

經驗召回複用配置項 `autoRecallTimeoutMs`，不單獨開 experience timeout；預設值仍是 `5000ms`。

### `examples/openclaw-plugin/context-engine.ts`

在 transformContext assemble 中接入兩路 recall：

```text
experience recall
  -> 只查 viking://user/memories/experiences
  -> 受 agentExperience 配置和 shouldRecallAgentExperience 控制

long-term recall
  -> 查 viking://user/memories
  -> recallResources=true 時查 viking://resources
  -> 過濾掉 experiences
```

然後統一生成 `<openviking-context>` 外殼：

```ts
const combinedBlock = buildOpenVikingContextBlock({
  sections: [experienceRecall.block, recall.section],
});
```

如果沒有 experience 命中，普通長期記憶仍然作為 `Long-term Memories` section 放入 `<openviking-context>`。如果兩個結果都為空，直接 passthrough，不改寫 messages。

### `examples/openclaw-plugin/text-utils.ts`

新增剝離：

```text
<openviking-context ...>...</openviking-context>
```

並保留歷史格式清理：

```text
<relevant-memories>...</relevant-memories>
```

這樣 `afterTurn()` 寫 session 前會清理當前格式和歷史格式注入塊，避免本輪召回內容進入下一輪抽取。執行時新注入統一使用 `<openviking-context>`。

### tests

PR 中保留單元測試：

- `tests/ut/agent-experience-recall.test.ts`
- `tests/ut/context-engine-assemble.test.ts`
- `tests/ut/context-engine-afterTurn.test.ts`
- `tests/ut/text-utils.test.ts`

`tests/integration/test_openclaw_openviking_strict_e2e.py` 只作為本地嚴格聯調指令碼保留，不進入遠端 PR。

## 執行時流程

### 1. 進入 assemble

當前只在 transformContext assemble 階段自動注入。前置條件：

- session 沒有被 `bypassSessionPatterns` 命中。
- latest message 是 user。
- `cfg.autoRecall` 或 `cfg.agentExperience.enabled` 至少一個開啟。
- latest user message 沒有已經包含 `<openviking-context>`。
- `prepareRecallQuery()` 清理後的 query 非空，且長度至少 5。

如果以上任一條件不滿足，直接 passthrough。

### 2. 生成 query

query 來自 latest user message：

```ts
const recallQuery = prepareRecallQuery(extractAgentMessageText(latestMessage));
```

`prepareRecallQuery()` 會先呼叫 `sanitizeUserTextForCapture()`，因此舊的注入塊、sender metadata、conversation metadata 等噪音不會進入 recall query。query 最長 4000 字元，超出會截斷並寫日誌。

### 3. 判斷是否要查 experience

經驗召回首先受總開關控制：`agentExperience.enabled` 預設關閉。只有顯式開啟後，才會進入 `shouldRecallAgentExperience()`。這個 task gate 是內建邏輯，不再提供單獨配置開關。

硬跳過：

- session bypass。
- query 為空或短於 `agentExperience.minQueryChars`。
- latest user text 已包含 `<openviking-context>`。

強制召回：

- `triggerHint` 不是 `task_start`，例如 `cron_start`。
- `sessionKey` 包含 `:cron:`，或 `runtimeContext.isCron === true`，或 `runtimeContext.automationKind === "cron"`。

普通 task gate 使用確定性打分：

```text
+3 write/edit/modify/delete/migrate/deploy/release/configure/patch 等副作用動作
+2 fix/debug/test/build/run/implement/refactor/integrate/troubleshoot 等執行動作
+2 error/exception/failed/retry/traceback/test failed 等失敗訊號
+2 檔案路徑、程式碼物件、hook/API/tool/package/module 等工程物件
+1 經驗/踩坑/最佳實踐/avoid/best practice/lesson/pitfall 等經驗意圖
-3 閒聊、翻譯、總結當前對話等非執行場景
-2 純知識問答，並且沒有工程物件和執行動詞
```

`score >= 3` 才自動查 experience。

### 4. 檢索 experience

經驗召回只查 agent experience 目錄：

```ts
client.find(queryText, {
  targetUri: "viking://user/memories/experiences",
  limit: Math.max(expCfg.recallLimit * 4, 12),
  scoreThreshold: expCfg.scoreThreshold,
}, agentId)
```

後處理：

- 只保留 URI/category 看起來是 experience 的結果。
- 按 URI 去重。
- 截到 `agentExperience.recallLimit` 條，預設 3。
- `level === 2` 時用 `client.read()` 讀取完整內容；否則使用 abstract / overview / uri。
- 只渲染結構化 experience，或者 metadata/URI 明確標記為 experience 的內容。
- 總注入字元不超過 `agentExperience.maxInjectedChars`。
- 受 `autoRecallTimeoutMs` 控制；超時或失敗只 warn，不阻塞 OpenClaw。

當前不查 raw trajectories。

### 5. 渲染 experience

OV experience 當前主要結構是：

```markdown
## Situation
...

## Approach
...

## Reflect
...
```

OpenClaw 注入時對映為更適合執行期閱讀的欄位：

```markdown
### Experience: <filename>
Source: <uri>
Score: <score>

Trigger:
- from Situation

Do:
- from Approach

Avoid:
- from Reflect

Scope:
- from Situation

Check:
- from Reflect or Approach
```

如果原文缺某個欄位，會用摘要或固定 fallback 補齊，避免給 LLM 一個空標題。

### 6. 檢索長期記憶

原有 auto recall 保留，但輸出不再直接包 `<relevant-memories>`。它現在只生成 `## Long-term Memories` section，再交給統一外殼。transformContext assemble 和非 transformContext assemble 都統一注入 `<openviking-context>`。

搜尋範圍：

- `viking://user/memories`
- `viking://resources`，僅 `recallResources=true`

後處理：

- 合併結果並按 URI 去重。
- 只保留 leaf memory。
- 過濾掉 experience memory，避免和 `Agent Experiences` 重複。
- 使用現有 `postProcessMemories()` / `pickMemoriesForInjection()` 排序和截斷。
- 使用 `recallMaxInjectedChars` 做完整條目預算控制，單條記憶不截半。

### 7. 注入外殼

長期記憶單獨注入時也使用統一外殼：

```markdown
<openviking-context>
## Long-term Memories

Source: openviking-auto-recall
The following Business Data Platform memories may be relevant:
- [profile] ...
</openviking-context>

<original latest user message>
```

同時注入 agent experience 和長期記憶時：

```markdown
<openviking-context>
## Agent Experiences

These are prior execution lessons learned by this agent. Use them as task guidance, not as user facts.

### Experience: openclaw-plugin-file-write-guard
Source: viking://user/default/memories/experiences/openclaw-plugin-file-write-guard.md
Score: 0.910

Trigger:
- 當修改 OpenClaw 外掛 afterTurn 寫回邏輯時。

Do:
- 在寫回 OV session 前剝離注入上下文塊。

Avoid:
- 避免把注入經驗再次寫回 transcript。

Scope:
- 當修改 OpenClaw 外掛 afterTurn 寫回邏輯時。

Check:
- 避免把注入經驗再次寫回 transcript。

## Long-term Memories

Source: openviking-auto-recall
The following Business Data Platform memories may be relevant:
- [profile] ...
</openviking-context>

<original latest user message>
```

規則：

- 外殼統一用 `<openviking-context>`，表達“Business Data Platform 注入的上下文”，不繫結 OpenClaw/VikingBot/Codex 任一消費方。
- 內部用 Markdown section 區分經驗記憶和長期記憶。
- `Agent Experiences` 在前，因為它影響執行策略。
- `Long-term Memories` 在後，因為它更多是使用者事實、偏好、資源。
- 沒有命中的 section 直接省略。
- 兩個 section 都沒有時，不注入任何東西。
- 清理邏輯相容歷史 `<relevant-memories>` 和當前 `<openviking-context>`。

## 為什麼 experience block 和 long-term block 不合成一個 section

它們都屬於 recall，但語義不同：

- long-term memory 是事實/偏好/資源，回答時可以當作上下文事實。
- agent experience 是執行策略/踩坑/驗證方式，只能當作任務指導，不能當成使用者事實。

如果混在同一個 bullet list 裡，模型容易把“以前修 bug 的做法”當成“當前使用者事實”。所以它們共享 `<openviking-context>` 外殼，但必須分 section。

## 與 MemOS 的關係

MemOS OpenClaw adapter 的自動注入點是 `before_prompt_build`，返回 `{ prependContext }`。它不是每個 tool 呼叫前無腦注入，也不是 subagent 啟動時一定注入。

OV OpenClaw 當前沒有這個 hook，但 transformContext assemble 在語義上等價於“LLM prompt 構造前最後一次上下文改寫”。所以本 PR 採用 transformContext assemble。

MemOS 值得參考的是三點：

- 用一個外層 block 包住注入內容，便於清理。
- 經驗和普通記憶分割槽展示。
- 經驗要渲染成行動指導，而不是原始軌跡。

本 PR 不復刻 MemOS 的 L1 Trace / L2 Policy / L3 World Model / Skill 層級。OV 服務端已經負責 trajectory 和 experience 的沉澱，OpenClaw 外掛只消費結果。

## 與 VikingBot 的關係

VikingBot 目前已有多個經驗注入點：

- skill 讀取後追加 `## Related Experiences`
- subagent task 前追加 `## Agent Experience`
- write tool 前檢測寫類工具，插入 `## Relevant Agent Experience`
- cron/benchmark 場景通過任務 prompt 讀取 experience

這些是 VikingBot 內部 agent loop 的直接拼接邏輯，不是一個跨外掛的公共 envelope。

因此新外殼不應該叫 `vikingbot-context`，也不應該叫 `openclaw-context`。`<openviking-context>` 更適合作為 OV 面向不同 agent 外掛的統一注入外殼。未來 VikingBot 如果遷移到公共外掛協議，也可以選擇複用這個 envelope；但本 PR 不改 VikingBot。

## 後續更精確接入點

下列入口從原理上適合注入 experience，但需要 OpenClaw host 暴露更精確的 hook 或可中斷控制面。當前 PR 不實現。

### Skill 載入時

適合原因：agent 已經選擇讀取某個 `SKILL.md`，此時用 skill name/description 查經驗，注入到 skill 內容旁邊，相關性比全域 prompt 更高。

需要 host 支持：

```ts
tool_result_persist / after_tool_call
  -> 允許外掛修改 read_file(SKILL.md) 返回給 LLM 的 tool result
```

外掛邏輯：

```text
read_file(SKILL.md)
  -> parse name/description
  -> query experiences
  -> append "Related Experiences" to this tool result only
```

### Subagent 啟動時

適合原因：subagent 是冷啟動，最需要攜帶“類似子任務過去怎麼做”的經驗。

需要 host 支持：

```ts
before_subagent_start(event: {
  task?: string;
  mission?: string;
  profile?: string;
  childSessionKey?: string;
}) -> { prependContext?: string }
```

如果 host 只有 `subagent_spawned`，那通常已經太晚，只能記錄後設資料，不能保證改到子 agent 初始 prompt。

### Write 類工具呼叫前

適合原因：寫檔案、改檔案、刪除檔案是副作用動作，經驗最能減少“寫了又改”的情況。

但正確實現必須支援 cancel/replan：

```text
LLM 準備呼叫 write_file/edit_file
  -> plugin 查經驗
  -> 若命中，取消當前 tool call
  -> 把經驗作為 user/context message 插入
  -> 重新讓 LLM 決定是否還要寫、怎麼寫
```

如果 host 只允許不可變的 `before_tool_call`，那這點不能正確做。繼續執行原 tool call 意味著經驗來得太晚。

### Cron 重複任務

cron 原理上適合注入 experience，因為任務重複、經驗命中率高。

當前 PR 已經支援在 transformContext assemble 中識別：

```text
sessionKey includes ":cron:"
runtimeContext.isCron === true
runtimeContext.automationKind === "cron"
```

識別後 trigger 是 `cron_start`，並繞過普通 task gate。前提是該 cron session 沒被 `bypassSessionPatterns` 跳過。不要預設把 cron 加入 bypass。

如果未來 host 暴露 automation name/prompt，query 應該從當前 latest user message 擴充為：

```text
sessionKey
automation name
automation prompt
latest task text
recent failure/success summary
```

## 清理與防汙染

經驗召回最容易出的問題是自我汙染：本輪注入的經驗被當成本輪使用者輸入寫回 session，下次 commit 又把它抽成新的經驗。

當前 PR 的防線：

1. assemble 前檢查 latest user message 是否已有 `<openviking-context>`，有則不重複注入。
2. `sanitizeUserTextForCapture()` 會剝離：
   - `<openviking-context>`
   - 歷史 `<relevant-memories>`
3. `afterTurn()` 寫 session 前走現有文本清理路徑，因此注入塊不會寫回 OV。
4. long-term recall 過濾 experience URI/category，避免 experience 被長期記憶 section 再注入一次。

## 測試覆蓋

當前 PR 的單元測試覆蓋：

- 普通知識問答不會觸發 experience recall。
- 執行型任務會觸發 experience recall。
- cron trigger 會強制 recall。
- experience memory 不會出現在 `Long-term Memories` section。
- 已存在 `<openviking-context>` 會阻止重複注入。
- `<openviking-context>` / 歷史 `<relevant-memories>` 會被清理。
- afterTurn 寫 session 前會剝離注入塊。

本地嚴格 e2e 指令碼保留在工作區，但不進入遠端 PR。

## 驗收標準

合併前應滿足：

- `npm run typecheck` 通過。
- `npm run build` 通過。
- `npm run test` 通過。
- PR diff 不包含 `tests/integration/test_openclaw_openviking_strict_e2e.py`。
- 預設配置下不會觸發 experience recall；必須顯式設定 `agentExperience.enabled: true`。
- 預設關閉 experience 時，普通長期記憶 auto recall 也使用 `<openviking-context>` 外殼。
- 普通問答不會因為預設配置無腦注入 experience。
- 執行型任務在有相關 experience 命中時注入 `Agent Experiences` section。
- 同一 block 中長期記憶和經驗記憶分割槽清晰。
- 注入塊不會被寫回 OV session。

## 最終邊界

```text
OpenClaw 外掛負責：
  - 判斷當前 turn 是否值得使用 agent experience
  - 檢索 viking://user/memories/experiences
  - 渲染 Agent Experiences section
  - 與 Long-term Memories 共同放入 <openviking-context>
  - 寫 session 前清理注入塊

Business Data Platform 服務端負責：
  - session commit
  - trajectory 抽取
  - experience 生成和更新
  - memory vectorization
  - 未來的抽取 policy / world model / skill 演進
```
