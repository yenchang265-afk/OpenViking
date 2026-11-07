# @openviking/react

[English](README.md) / 中文

OpenViking AI 應用介面的 React 基礎：構建工具、文件、分層目錄與區域性化樣式。FileTree 與 FilePreview 提供佔位檢視，另附五種檔案型別圖示。三個業務模組佔位元件支援先完成佈局接入，ScopeCascade 已提供三級級聯 Hook 與組合檢視。

本包沿用倉庫的 AGPL-3.0-only 許可證。當 `react@<version>` 標籤與本包 manifest 中的版本一致時，釋出工作流會將其釋出到 npm。

## 模組目錄

| 原始碼目錄                                                                | 公開入口                                      | 職責                                                                |
| ------------------------------------------------------------------------- | --------------------------------------------- | ------------------------------------------------------------------- |
| [components/file-tree](./src/components/file-tree/README_CN.md)           | `@openviking/react/components/file-tree`      | 目錄樹渲染、展開、選中與事件回傳；檢視為佔位實現                    |
| [components/file-preview](./src/components/file-preview/README_CN.md)     | `@openviking/react/components/file-preview`   | 只讀預覽狀態與擴充套件頁籤；檢視為佔位實現                          |
| [components/tui](./src/components/tui/README_CN.md)                       | `@openviking/react/components/tui`            | 已確認的命令記錄、結果與輸入區型別；檢視仍為佔位實現                |
| [components/scope-switcher](./src/components/scope-switcher/README_CN.md) | `@openviking/react/components/scope-switcher` | 無狀態作用域佈局與獨立 ScopeSelector，提供選項、面板及搜尋互動      |
| [components/agent-connect](./src/components/agent-connect/README_CN.md)   | `@openviking/react/components/agent-connect`  | Agent 接入檢視的頁籤、列表與詳情契約；檢視仍為佔位實現              |
| [modules](./src/modules/README_CN.md)                                     | `@openviking/react/modules/<模組>`            | ScopeCascade 級聯 Hook 與組合檢視，以及三個業務模組佔位元件         |
| [client](./src/client/index.ts)                                           | `@openviking/react/client`                    | 框架無關的請求客戶端：`createOvClient`、`OvClient`、`OvClientError` |
| [hooks](./src/hooks/README_CN.md)、[utils](./src/utils/README_CN.md)      | 僅包內使用                                    | 跨模組 Hook 與純工具                                                |

元件按各自契約逐步實現。FileTree 已按契約渲染全部行型別並實現鍵盤互動；FilePreview 已實現頁籤外殼、標題操作與純文本預覽、編輯基礎，正文尚未接入 FileViewer。ScopeSwitcher 已實現無狀態佈局，獨立 ScopeSelector 子元件管理本級展開，資料訂閱、搜尋與請求由宿主提供。Tui 與 AgentConnect 只渲染固定尺寸空殼，具體限制見各自文件。包還提供五種檔案型別圖示。
元件通過 props 接收檢視資料與狀態，通過回調錶達使用者意圖，遵循 [元件目錄約定](./src/components/AGENTS.md)。[modules](./src/modules/README_CN.md) 按業務能力規劃 Hook 與檢視：Hook 負責取數、狀態和操作，組合檢視將其接入元件。完整頁面與產品專屬流程由宿主負責，管理後臺不在本期範圍內。當前 `file-browser`、`console` 與 `task-center` 已提供佔位元件、基礎 Props / Labels 型別與樣式，可先接入佈局；這三個模組的業務 Hook、資料載入和聯動尚未實現。

模組預設通過共享 Client 消費 OpenViking 原生 API，由 Provider 下發 `baseURL`、headers 等配置，模組或獨立 Hook 可通過 `requestOptions` 區域性覆蓋。標準接入無需逐模組實現 Adapter；非標準閘道器集中在宿主請求接入層適配。請求契約——`OvRequestOptions`、`OvClient` 與 `OvClientError`——來自 `@openviking/react/client` 子路徑，自帶基於 `fetch` 的實現；Provider 從同一子路徑匯出；這些原生 API 模組的 Hook 尚未實現；ScopeCascade 按宿主提供的三個介面適配函式接入，不依賴 Provider。詳見[請求約定](./src/modules/README_CN.md#請求契約與預設配置)。

### Props 約定

同一套 props 由不同宿主接入。宿主之間的流程與介面不同，互動與 UI 對齊，因此：

- 元件只接收**已適配的資料**：檔案條目、頁籤與內容來源由模組 Hook 或宿主對映成包內型別，元件不引用任一宿主的資料模型。
- 狀態用受控欄位表達，回撥只上報意圖，不返回業務資料。
- 文案通過 labels 傳入，預設為英文；動態文案由宿主在接入層對映 i18next 或 Starling。
- 圖示、擴充套件頁籤、額外欄位、工具欄動作通過插槽或節點傳入，元件不繫結第三方 UI 庫。
- 列表型元件按上層展開後的行/項渲染，分頁、載入、錯誤、空態由模組 Hook 或宿主提供。

## 公開入口與樣式

- 根入口只匯出各元件、各業務模組的元件本體與主 Props 型別（`<元件名>Props`），當前為 `FileTree`、`Tui`、`ScopeSwitcher`、`ScopeSelector`、`ScopeCascade`、`AgentConnect` 與三個業務模組佔位元件；行型別、選項型別、控制代碼與文案包等子型別只從 `components/<元件>`、`modules/<模組>` 子路徑匯出。`FilePreview` 不在根入口：它的型別依賴可選的 `@ark-design/ui`，放進根宣告會讓該 peer 變成必需。ScopeCascade 從 `modules/scope-cascade` 匯出組合檢視與獨立訂閱 Hook，其他業務模組仍為佔位。不提供 `@openviking/react/components` 或 `@openviking/react/modules` 分類聚合 JS 入口。包匯出顯式列舉，內部檔案不開放。
- 元件只提供明確列出的分層子路徑，不保留舊路徑別名。
- JS 入口共享實現，不隱式載入 CSS。整包、元件集合與單模組樣式由同一份原始碼構建，選擇所需範圍匯入即可。

| 範圍         | CSS 入口                                        |
| ------------ | ----------------------------------------------- |
| 整包         | `@openviking/react/style.css`                   |
| 元件集合     | `@openviking/react/components/style.css`        |
| 單元件       | `@openviking/react/components/<模組>/style.css` |
| 業務模組集合 | `@openviking/react/modules/style.css`           |
| 單業務模組   | `@openviking/react/modules/<模組>/style.css`    |

各 CSS 入口可獨立使用，整包 CSS 已包含模組佔位樣式。真實能力遷入後，模組 CSS 須同步包含組合檢視與依賴元件的樣式；單獨使用模組 Hook 無需匯入 CSS。跨模組公共 Hook 有真實實現後再開放 `@openviking/react/hooks`；模組專屬的公開 Hook 從對應模組入口匯出，私有 Hook 和工具不進入公共匯出。

```tsx
import { FileBrowser } from '@openviking/react/modules/file-browser';
import '@openviking/react/modules/file-browser/style.css';

<FileBrowser
  labels={{ title: '檔案瀏覽', description: '佔位元件，待接入。' }}
/>;
```

其餘模組分別匯出 `Console` 和 `TaskCenter`，目前都接受 `className`、`style` 與 `labels`，無需 Provider 或請求配置。

經驗看板屬於預覽擴充套件；任務進度先歸所屬模組；API Key 展示控制元件按需複用，憑證建立及管理由宿主負責。本次不新增這些獨立模組。

## 圖示

```tsx
import { PdfIcon } from '@openviking/react/icons';

<PdfIcon width={20} height={20} className="file-icon" alt="PDF" />;
```

圖示預設以 16 × 16 的圖片渲染。裝飾性圖示可沿用預設空 `alt`，用於傳達檔案型別時可提供描述。SVG 隨構建產物內聯，宿主直接消費包匯出。

React 與 ReactDOM 為 peer dependencies（`^18.2.0 || ^19.0.0`），由 Rslib 自動 externalize。Rslib 產出共享的 ESM JavaScript 與宣告檔案，以及獨立構建的 CSS 入口。公開入口 `@openviking/react/style.css` 指向 `dist/style.css`。樣式區域性化，不重置應用樣式。

在 `frontend/` 下執行 `npm run build:lib` 生成 `packages/react/dist/`。文件開發與部署見[前端工作區 README](../../README.md)。

### ScopeCascade

將三個引用穩定的介面適配函式傳給 `useScopeCascade({ loadLibraries, loadSpaces, loadUsers })`，再渲染 `<ScopeCascade controller={controller} />`。介面返回 `{ id, label }` 選項並接收 `AbortSignal`；空間介面額外接收庫 ID，使用者介面接收庫 ID 與空間 ID。模組負責級聯請求、下級重置、載入、錯誤、重試和舊響應隔離。每一級獨立訂閱，呼叫 Hook 的根元件不訂閱請求狀態。

從 `@openviking/react/modules/scope-cascade` 匯入 Hook 和組合檢視，並顯式匯入對應 `/style.css`。自定義介面可在葉子元件中使用 `useScopeCascadeLevel(controller.levels[index])`，無需 `memo`。適配函式引用變化會重置級聯；當前按完整列表載入，不包含服務端搜尋和分頁。
