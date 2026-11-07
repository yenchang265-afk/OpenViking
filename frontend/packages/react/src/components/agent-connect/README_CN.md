# AgentConnect

[English](README.md) / 中文

Agent 接入檢視。宿主傳入頁籤、當前頁籤的條目與選中項詳情；元件渲染列表與詳情，按需複製正文，並上報切換意圖。

```tsx
import { AgentConnect } from '@openviking/react/components/agent-connect';
import '@openviking/react/components/agent-connect/style.css';

<AgentConnect
  tabs={tabs}
  activeTabId={activeTabId}
  items={items}
  selectedId={selectedId}
  detail={detail}
  onTabChange={setActiveTabId}
  onSelect={setSelectedId}
  onCopy={trackCopy}
/>;
```

目錄從哪來、正文怎麼渲染，都由宿主決定——元件不碰這些。複製正文是元件自己的職責。

## 為什麼正文是「宿主給的節點」

接入說明天然是 Markdown 與程式碼塊，且不同宿主的目錄來源並不一致：一處從遠端 JSON 拉取，另一處可能是本地檔案。如果元件自己取數、自己渲染 Markdown，它就必須知道宿主的目錄地址、快取策略與 Markdown 方言，最後和某個文件站綁死。

這裡反過來：**宿主提供條目與正文，元件只負責排版與上報**。

- 正文是節點，宿主可以傳 Markdown 渲染結果、純文本或任意元件。
- 複製用的純文本與展示用的正文分開：展示可以帶格式，複製必須是乾淨文本。
- 頁籤與選中項都是受控的，元件不快取目錄。

## 元件負責什麼

- 渲染頁籤行與當前頁籤的高亮。
- 渲染左側條目列表：圖示、名稱、一句話說明與選中態。
- 渲染右側詳情：標題、圖示、說明、標籤、正文與複製按鈕。
- 複製：由元件完成，成功後通知已複製的文本。

## 元件不負責什麼

- 不請求目錄，不渲染 Markdown，不判斷某項是否可接入。
- 不維護頁籤、選中項與正文——全部受控。
- 不接管路由與埋點：切換頁籤與選中條目只上報意圖，`onCopy` 只是複製成功後的通知。
- 不內建任何具體 Agent 的名稱或接入方式，條目完全由宿主宣告。

## 文件與開發

- 屬性表與可執行示例見[元件文件](../../../../../docs/docs/en/components/agent-connect.mdx)（[中文](../../../../../docs/docs/zh/components/agent-connect.mdx)）。
- 開發與構建命令見[前端工作區 README](../../../../../README.md)，模組約定見[包說明](../../../README_CN.md)。
- 獨立樣式入口 `@openviking/react/components/agent-connect/style.css`，與 JS 入口分離，可按需引入。

當前是佔位元件：只渲染固定尺寸的空殼，不消費 props。上述為目標行為。
