# AgentConnect

[English](README.md) / 中文

按 [Figma 節點 10468:23946](https://www.figma.com/design/ecpd1ZGHKRYibm1ODKEpM6/OpenViking-Console?node-id=10468-23946) 實現的接入檢視。標題、兩個頁籤、十四個 Agent 與四個開發接入方式的名稱、圖示、說明、標籤及正文均內建。呼叫方傳入 `apiKey`；`locale: 'zh-CN' | 'en-US'` 可選，省略時繼承上層語言，最終預設 `en-US`。`baseUrl` 可覆蓋預設雲服務地址。

```tsx
import { AgentConnect } from '@openviking/react/components/agent-connect';
import '@openviking/react/components/agent-connect/style.css';

<AgentConnect apiKey={apiKey} locale="zh-CN" />;
```

## 設計與互動約定

- 每個程式碼塊提供獨立複製按鈕；顯示、隱藏和複製使用圖示按鈕，提供本地化懸浮提示與無障礙標籤，複製成功切換為勾選圖示並播報反饋。含 API Key 的程式碼塊預設脫敏，可顯示或隱藏原值，同一指南最多顯示一個程式碼塊中的金鑰。安裝器命令也採用該互動。獨立複製始終使用原始金鑰，整篇複製保留現有正文格式；成功後的 `onCopy` 返回實際複製的程式碼塊或完整正文。切換指南或憑據後恢復脫敏並重置複製反饋。

- 指南使用 `react-markdown`、`remark-gfm`、`rehype-raw` 和 `rehype-sanitize` 渲染 Markdown 與白名單 HTML，支援加粗、換行、摺疊說明、列表和表格；過濾指令碼、事件屬性及不安全的連結協議。程式碼中的標籤保持字面文本，指南圖片不載入，複製仍使用原始 Markdown。
- 安裝器命令顯式指定當前 Agent 的 `--harness`，並包含接入引導需要的 `cli`；Claude Code 對應 `claude`、Kimi Code 對應 `kimicode`、DeepSeek Harness 對應 `dsh`，TRAE 對應國際版 `trae`。
- 安裝器命令中的服務地址和金鑰使用 Shell 單引號轉義，執行後引數保持呼叫方字面值；不將 Shell 轉義應用到 JSON、Python 或純文本指南。自定義 Hermes 地址使用 **Custom** 連線步驟，並填寫該地址。
- 指南追加 `/mcp` 等子路徑時移除服務地址末尾的斜槓；API 示例的 `url` 變數也使用該規範化地址，以便隨後拼接 `/api/v1/...`。安裝器引數和不拼接路徑的獨立地址保留呼叫方原值。
- 指南、憑據或地址變化會建立新的複製互動例項：清空反饋和 pending 狀態，返回舊指南也不會恢復舊反饋。已發起的 Clipboard API 寫入無法取消，但過期完成結果不更新介面或呼叫 `onCopy`。
- 宿主可提供 `agreementUrl`，協議引用渲染為可用滑鼠和鍵盤訪問的連結；未提供時僅顯示資料訪問提示，不顯示無目標的協議引用。

- 語言僅由呼叫方通過 `locale` 引數指定，元件和示例不提供語言選擇 UI。
- 預設 1000px 寬、949px 最小高度，左側列表 200px，列間距 40px，詳情寬 660px；標題、膠囊頁籤、行高、圖示尺寸、指令排版和光暈以設計截圖為準。
- 預設選中「接入主流 Agent」與 Codex。頁籤和條目使用例項內狀態，也可通過 `activeTabId`、`selectedId` 控制，並通過可選回撥通知宿主。頁籤支援方向鍵、Home、End。
- 主流頁籤展示完整本地目錄：Codex、Claude Code、豆包工作、WorkBuddy、TRAE、Cursor、OpenClaw、Hermes Agent、OpenCode、DeepSeek Harness、DeerFlow、pi、ZCode、Kimi Code；移除接入應用和 vscode。開發頁籤展示 MCP、CLI、API、SDK，使用相同列表與詳情佈局。選擇不屬於當前分組時顯示該分組第一項；各分組記住例項內選擇。
- `showOverseasTag` 預設 `false`，不顯示「境外」標籤。設為 `true` 時，Codex、Claude Code、Cursor、OpenClaw、Hermes Agent、OpenCode、pi 的詳情增加「境外」標籤（英文為 Overseas），原接入方式標籤保留。標籤按 Agent 產品歸屬維護，不根據其使用的模型推斷部署地區。
- DeerFlow 詳情內建 MemoryManager、MCP 兩種接入說明，可獨立切換與複製；預設 MemoryManager，切換說明後複製反饋重置。新增圖示使用本地目錄中的原始 Logo，以透明度蒙版保留輪廓並跟隨主題文字色，保證暗色可見。
- CLI 詳情合併本地 `cli.md` 與 `agent-cli.md`，提供「手動終端安裝」「通過 AI Agent 安裝」兩個內部頁籤，預設手動安裝。頁籤沿用參考元件的底部邊線、24px 間距與主色選中下劃線，顏色跟隨主題；複製僅包含當前頁籤正文，切換後反饋重置。
- 後設資料與正文從倉庫 [本地目錄](../../../../../../docs/images/agents) 生成元件內建快照，不在執行時載入遠端 JSON 或 Markdown。Codex、Claude Code、TRAE、Cursor、OpenCode、DeepSeek Harness、pi、ZCode、Kimi Code 沿用參考元件的官方安裝器完整指令，其他條目使用對應本地文件。更新文件後執行 `node packages/react/src/components/agent-connect/generate-content.mjs`。
- 頁面預設展示脫敏金鑰，程式碼塊可主動顯示原值，複製正文使用呼叫方的原始金鑰；替換服務地址與文件中的金鑰佔位符。金鑰不寫入 DOM 屬性或本地持久化。語言、金鑰、地址、分組或條目變化後，複製反饋重置。
- 複製按鈕使用 Clipboard API，成功後顯示「已複製」並通知 `onCopy`；失敗顯示「複製失敗，請重試」，可再次操作。指令只作為設計展示文本，不執行其中的安裝命令。
- 圖示來自設計稿匯出的 SVG，位於 [圖示目錄](../../../../icons/svg/agent-connect/README.md)，JS 構建包含圖示，無需宿主提供 URL。
- 顏色使用主題基線；暗色跟隨宿主 `.dark`。窄容器可橫向瀏覽原始佈局，保持設計比例，不改成另一套佈局。
- Codex 圖示使用透明外底和正常混合模式，保留內部白色符號；詳情圖示描邊使用主題邊框，避免在暗色背景上變黑或出現白框。

原來的 `tabs`、`items`、`detail`、`labels` 輸入已移除。文案與圖示固定是此次設計還原的明確要求。

屬性表與可執行示例見[元件文件](../../../../../docs/docs/zh/components/agent-connect.mdx)，命令見[前端工作區 README](../../../../../README.md)。
