<a id="一條提示詞接入-agent"></a>

<a id="一鍵整合-agent"></a>

# 一鍵接入

通過一條提示詞，將 OpenViking 接入你正在使用的程式設計 Agent。Agent 會在本機檢測到的各個 Agent 裡安裝 OpenViking 記憶外掛，檢查連線，問你要不要匯入近期工作，再告訴你怎麼重啟。重啟後，你問的第一個問題就能用上 OpenViking。

Agent 按一份簡短的指南執行。指南以純 Markdown 釋出，任何 Agent 都能直接獲取：

- 中文：`https://docs.openviking.ai/agents/zh/onboarding.md`
- 英文：`https://docs.openviking.ai/agents/en/onboarding.md`

兩份也都可以從 `docs.openviking.net` 訪問，中國大陸訪問通常更快。

## 提示詞

複製提示詞，傳送前把 `<API_KEY>` 換成你的 key，在 [OpenViking 控制台](https://console.volcengine.com/vikingdb/openviking/region:openviking+cn-beijing?utm_source=opensource_docs&utm_medium=referral&utm_campaign=getting-started_07-agent-onboarding)的**使用者管理 → API Key** 中獲取。

<AgentPrompt>

```text
幫我安裝 OpenViking 記憶外掛，並帶我開始使用。OpenViking 是為 Agent 提供的上下文資料庫（https://github.com/volcengine/OpenViking），下面的命令和連結來自它的官方文件。

1. 執行官方安裝器。它需要聯網並寫入我的主目錄，如果被你的沙箱攔住，請向我申請批准：
   curl -fsSL https://openviking.ai/install | bash -s -- --yes --lang zh --url https://api.vikingdb.cn-beijing.volces.com/openviking --api-key <API_KEY>
2. 裝好後讀 OpenViking 的接入引導，按它帶我完成設定。匯入歷史、寫協作規則這類選擇，引導會讓你先問我。docs.openviking.ai 和 docs.openviking.net 是同一個文件站，哪個打得開用哪個：
   https://docs.openviking.ai/agents/zh/onboarding.md

API key 是我在 OpenViking 控制台給自己生成的，安裝器會把它存到本機的 ~/.openviking/ovcli.conf。命令裡原樣使用就行，回覆裡不用再顯示它，也不要寫進別的檔案或規則。全程用中文和我交流。
```

</AgentPrompt>

安裝器會給本機檢測到的所有受支援的 Agent 都裝上外掛，所以你裝過的其他 Agent 也會裝上；每個 Agent 都要各自重啟後，外掛才會在裡面生效。安裝器還會同時安裝 `ov` 命令，Agent 要用它檢查連線、新增檔案。`--lang` 設定安裝器的語言，安裝器最後列印的引導連結也隨之選擇語言。想只裝其中幾個，加上 `--harness` 並用逗號分隔列出，例如 `--harness claude,cli`，詳見[統一安裝器](../agent-integrations/16-capability-reference.md#_3-1-2-統一安裝器)。

**自部署服務。** 把 URL 換成你自己服務的地址。要用 user key，root key 不能讀寫記憶。本地服務沒有開啟鑑權時，傳 `--api-key ''`。

**關於 key。** 安裝器只能通過命令列引數接收 key，所以 key 會出現在這段對話裡，也會留在 Agent 本地的會話記錄和日誌中。指南要求 Agent 不復述 key、不把它寫進任何地方。外掛目前還不會從儲存的對話裡刪除 key，重啟後的第一次儲存會把安裝對話也存進去：在 Codex 上，不管回到原對話還是開新會話都會這樣，這段安裝對話連同 key 可能被儲存到你自己的 OpenViking 帳號裡；在 Claude Code 上開新會話可以避免，所以 Agent 會請你不要回到安裝對話。如果你不想把 key 貼進聊天，可以自己在終端執行 `curl -fsSL https://openviking.ai/install | bash`，再把[已經裝好](#已經裝好)一節的提示詞發給 Agent。

## 已經裝好

如果外掛已經裝好，在 Agent 裡開一個新會話，傳送：

```text
按 https://docs.openviking.ai/agents/zh/onboarding.md 帶我完成 OpenViking 首次使用。
```

## Agent 會做什麼

1. **檢查安裝結果。** 讀取安裝器的輸出並執行 `ov health`，告訴你已經連上、外掛裝進了哪些 Agent；裝進了不止一個時，它們用的是同一份上下文。
2. **說明哪些事會自動發生。** 每次提問前，外掛會召回相關記憶；每輪對話結束後，外掛儲存對話，服務端在後臺提取長期記憶。這一步不需要你另外批准，請求安裝本身就是同意。
3. **問你要不要帶入已有工作。** 預設匯入當前專案最近 14 天的會話。你也可以描述某一類工作，例如「和支付重構有關的討論」：Agent 會列出候選會話和每個會話的摘要，挑出相符的，先給你看挑選結果，再上傳。Claude Code 和 Codex 的歷史由匯入指令碼直接讀取；其他 Agent 會先寫一個小指令碼把自己的會話轉成 JSONL，再交給同一個匯入指令碼。Agent 會先告訴你找到了哪些工作、有多大，你確認後才匯入；已經在 OpenViking 裡的會話不會重複上傳。匯入後，Agent 會馬上從 OpenViking 讀回這項工作做到哪、定過什麼，讓你在重啟前就看到匯入的用處。只傳送使用者和助手的文本，工具呼叫及其輸出會被丟棄，API key 會被刪除。本機有 Claude Code 或 Codex 的歷史時，在其他 Agent 上也會一併提議匯入。你也可以點名要儲存的檔案，例如設計文件，Agent 用 `ov add-resource` 把它新增到你個人資源裡這個專案的目錄。
4. **提議一套長期協作規則。** Agent 會提議在你的使用者級規則檔案（例如 Claude Code 的 `~/.claude/CLAUDE.md`、Codex 的 `~/.codex/AGENTS.md`）里加一段規則，對你所有專案生效：先用 OpenViking 召回的上下文，不夠再檢索；把重要決定（連同理由）、階段進展和下一步，以及方案、調研、交付物等工作產出主動存進 OpenViking，放在你個人資源下每個專案一個的目錄裡（`resources/<專案名>/`，進展和決定記在其中的 `notes/`）；繼續一個專案時先看之前存下的內容；用到或存了東西會簡短告訴你。你也可以讓它按你的角色（產品、研發、市場、設計等）調整，補上這個角色還要儲存的內容。規則放在一對 `<!-- openviking:start -->` / `<!-- openviking:end -->` 標記之間，檔案裡原有的內容不動；你同意才寫，寫完會讀回確認。個人規則只能在應用設定裡改的 Agent（例如 TRAE、Cursor），會請你自己貼上進去。它不會把規則寫進專案檔案。
5. **告訴你怎麼重啟。** 外掛要在 Agent 重新啟動後才會載入。Agent 會給出你正在對話的這個 Agent 的具體操作：Codex 裡先信任 OpenViking 的 hooks（CLI 在會話裡輸入 `/hooks`，桌面版點輸入框下方的 hooks 圖示），再退出、回到同一段對話（CLI 執行 `codex resume --last`），說一句「已重啟」，如果仍出現「Hooks need review」，選 **Trust all and continue**；Claude Code 和其他 Agent 開一個新會話，發它給你的第一句話。安裝器如果還裝進了其他 Agent，它會告訴你那些也需要重啟。
6. **讓你看到 OpenViking 在起作用。** 重啟之後，你的第一個問題會基於召回的上下文回答，Agent 會告訴你在哪裡能看到：Claude Code 的來源卡片、Codex 的 OV-Usage 行，等等。

Agent 只在需要你做決定時提問：帶入哪些工作（看到數量後再確認一次），以及要不要寫入協作規則；每次都會先講清對你有什麼用、會傳送或改動什麼。已經選過的不會重複問。

## 另請參閱

- [Agent 接入概覽](../agent-integrations/01-overview.md)
- [Agent 整合能力](../agent-integrations/16-capability-reference.md)
- [安裝和使用 CLI](05-cli-setup.md)
