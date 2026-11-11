# VikingBot

[English](README.md) / 中文

可選 `locale: 'zh-CN' | 'en-US'` 覆蓋最近的模組或 Provider；均未配置時預設 `en-US`。已有 `labels` 可逐項覆蓋。業務內容仍由宿主提供。

對話檢視：訊息列表、輸入區與待確認互動區。渲染使用 **Ark Design**（`@ark-design/ui`）——與火山版控制台同一套元件庫——只接收已歸一化的訊息模型，宿主協議不進入元件。

> **當前狀態：佔位實現。** API 契約已確定，並按契約渲染出可用檢視，但檢視尚未經過設計評審，真實實現會被重寫。請把 props 與互動模型當作交付物，視覺表現視為臨時方案。

`viking-bot.tsx` 對應 `@openviking/react/components/viking-bot`；待確認互動區對應 `@openviking/react/components/viking-bot/interaction`。

## 為什麼一套模型能接兩版

開源版流式下發 `parts` 陣列、用自己的技術棧渲染 Markdown；火山版下發 Managed Agent 事件、用 Ark Design 渲染執行時間線。兩者的訊息形態、流式語義、以及是否存在人工確認步驟都不一樣。

因此元件只擁有**兩版共有的部分**：

- 訊息是 `{ id, role, parts }`，`role` 覆蓋 `user`、`assistant`、`system` 與 `tool`。
- 每個片段自帶判別值，`groupId` 把需要合併摺疊的片段歸入同一個執行塊。
- 流式是 `{ parts, insertIndex, iteration }`；在末尾追加的宿主把 `insertIndex` 傳成訊息數量即可。
- 渲染方式不同的宿主替換 `messageList`、`composer` 或 `interaction`，而不是改造內建檢視。

宿主協議的適配留在各宿主倉庫：元件不引入任何後端事件型別。

## 元件負責

- 用 Ark 的 `ChatMessageList`、`Bubble`、`ActivityTimeline`、`MDRenderer`、`ErrorCard` 渲染訊息列表。
- 用 Ark 的 `Sender` 渲染輸入區。
- 用 Ark 的 `AskHuman` 渲染 `choice`、`text`、`schedule`、`repair` 四種內建互動表單。
- 複製訊息正文並上報意圖，複製動作由宿主執行。
- 合併同一輪的連續助手訊息，並按 `groupId` 歸併片段。

## 宿主負責

- 取數、流式連線、會話建立與持久化。
- 把自身事件歸一化成包內訊息模型。
- 上傳附件；元件只上報使用者選擇或拖入的檔案。
- 判定輪次結束及其後續動作。
- 需要樹選擇器、上傳器等宿主能力時，用 `custom` 互動自行渲染。

## 替換區域

```tsx
<VikingBot
  locale="zh-CN"
  messages={messages}
  streaming={streaming}
  draft={draft}
  onDraftChange={setDraft}
  onSend={send}
  onCancel={abort}
  messageList={<MyActivityTimeline messages={messages} />}
  composer={<MySender value={draft} onChange={setDraft} onSend={send} />}
/>
```

`children` 替換整個主體。`interaction` 優先於 `composer`，兩版宿主在待確認時都是這個行為；宿主自帶互動區時用 `interactionSlot` 整塊替換。

省略 `draft` 時不渲染輸入區，只讀會話因此不會多出一個不可用的輸入框。

## 互動

待確認問題是宿主狀態，不是後端暫停：宿主從自己的流裡算出問題，答案發回後清除。元件只渲染表單並上報答案，宿主決定怎麼發回去。

`choice`、`text`、`schedule`、`repair` 由元件內建渲染。`custom` 收到 `{ disabled, submitting, submit, cancel }` 後自行渲染，因此樹選擇器、Skill 上傳器這類能力不需要進入公共庫。

## Ark 走懶載入

Ark 依賴瀏覽器專用模組，在純 Node 程序裡無法解析，因此所有用到它的入口都放在 `lazy()` 之後——與 `FilePreview` 正文入口同一做法。包的頂層入口在沒有 `window` 的環境下可以正常匯入，Ark 被編譯進獨立 chunk，`@ark-design/ui` 保持 optional peer。

## 開發入口

開發與構建入口見 [前端工作區 README](../../../../../README.md)，模組約定見[包說明](../../../README.md)。

獨立樣式入口為 `@openviking/react/components/viking-bot/style.css`，引入主題基線與檢視用到的 Ark 元件樣式。
