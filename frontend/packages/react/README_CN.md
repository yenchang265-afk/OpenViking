# @openviking/react

[English](README.md) / 中文

公開 UI 元件、組合模組 均支援可選的 `locale: 'zh-CN' | 'en-US'`。Props 覆蓋最近的模組或 Provider，均未配置時預設 `en-US`。已有 `labels` 保留逐項覆蓋能力，業務內容、插槽和回撥文案仍由宿主提供。

OpenViking AI 應用介面的 React 基礎：構建工具、文件、分層目錄與區域性化樣式。FileTree、Tui 與 FilePreview 已提供可用檢視，另附五種檔案型別圖示。Console 提供原生命令面板與受控對話檢視，ScopeCascade 提供三級級聯選擇器，FileBrowser 提供目錄、預覽與看板聯動。

本包沿用倉庫的 AGPL-3.0-only 許可證。當 `react@<version>` 標籤與本包 manifest 中的版本一致時，釋出工作流會將其釋出到 npm。

## 模組目錄

| 原始碼目錄                                                                | 公開入口                                      | 職責                                                                |
| ------------------------------------------------------------------------- | --------------------------------------------- | ------------------------------------------------------------------- |
| [components/directory-tour](./src/components/directory-tour/README.md)    | `@openviking/react/components/directory-tour` | 目錄錨點引導，支援宿主非同步定位、獨立高亮與異常恢復                |
| [components/file-tree](./src/components/file-tree/README_CN.md)           | `@openviking/react/components/file-tree`      | 目錄樹渲染、展開、選中與事件回傳；檢視為佔位實現                    |
| [components/file-preview](./src/components/file-preview/README_CN.md)     | `@openviking/react/components/file-preview`   | 只讀預覽狀態與擴充套件頁籤；檢視為佔位實現                          |
| [components/tui](./src/components/tui/README_CN.md)                       | `@openviking/react/components/tui`            | 已確認的命令記錄、結果與輸入區型別；檢視仍為佔位實現                |
| [components/scope-switcher](./src/components/scope-switcher/README_CN.md) | `@openviking/react/components/scope-switcher` | 無狀態作用域佈局與獨立 ScopeSelector，提供選項、面板及搜尋互動      |
| [components/agent-connect](./src/components/agent-connect/README_CN.md)   | `@openviking/react/components/agent-connect`  | 固定 Figma 接入檢視，內建原始圖示、文案與剪貼簿反饋                 |
| [components/viking-bot](./src/components/viking-bot/README_CN.md)         | `@openviking/react/components/viking-bot`     | 對話檢視契約，按契約渲染的檢視仍為佔位實現                          |
| [modules](./src/modules/README_CN.md)                                     | `@openviking/react/modules/<模組>`            | Console 面板、ScopeCascade 級聯選擇與 FileBrowser 聯動              |
| [client](./src/client/index.ts)                                           | `@openviking/react/client`                    | 框架無關的請求客戶端：`createOvClient`、`OvClient`、`OvClientError` |
| [hooks](./src/hooks/README_CN.md)、[utils](./src/utils/README_CN.md)      | 僅包內使用                                    | 跨模組 Hook 與純工具                                                |

元件按各自契約逐步實現。FileTree 已按契約渲染全部行型別並實現鍵盤互動；FilePreview 已實現頁籤外殼、標題操作與純文本預覽、編輯基礎，正文尚未接入 FileViewer。ScopeSwitcher 已實現無狀態佈局，獨立 ScopeSelector 子元件管理本級展開，資料訂閱、搜尋與請求由宿主提供。Tui 只渲染固定尺寸空殼；AgentConnect 按 Figma 佈局內建中英文 Agent 與開發接入詳情和原始圖示，由呼叫方提供金鑰與語言，支援可選受控選擇和剪貼簿反饋，具體限制見各自文件。包還提供五種檔案型別圖示。
元件通過 props 接收檢視資料與狀態，通過回調錶達使用者意圖，遵循 [元件目錄約定](./src/components/AGENTS.md)。[modules](./src/modules/README_CN.md) 按業務能力規劃 Hook 與檢視：Hook 負責取數、狀態和操作，組合檢視將其接入元件。完整頁面與產品專屬流程由宿主負責，管理後臺不在本期範圍內。`console` 已匯出原生命令組合檢視，編排 Hook 保持內部實現，對話通過宿主提供的資料與回撥接入；`file-browser` 提供目錄、預覽與看板聯動。

模組預設通過共享 Client 消費 OpenViking 原生 API，由 Provider 下發 `baseURL`、headers 等配置，模組可通過 `requestOptions` 區域性覆蓋。標準接入無需逐模組實現 Adapter；非標準閘道器集中在宿主請求接入層適配。請求契約——`OvRequestOptions`、`OvClient` 與 `OvClientError`——來自 `@openviking/react/client` 子路徑，自帶基於 `fetch` 的實現；Provider 從同一子路徑匯出；業務 Hook 均為模組內部實現；ScopeCascade 按宿主提供的三個介面適配函式接入，不依賴 Provider。詳見[請求約定](./src/modules/README_CN.md#請求契約與預設配置)。

### Props 約定

同一套 props 由不同宿主接入。宿主之間的流程與介面不同，互動與 UI 對齊，因此：

- 元件只接收**已適配的資料**：檔案條目、頁籤與內容來源由模組 Hook 或宿主對映成包內型別，元件不引用任一宿主的資料模型。
- 狀態用受控欄位表達，回撥只上報意圖，不返回業務資料。
- 介面文案內建中英文，通過可選的 `locale: 'zh-CN' | 'en-US'` 選擇；已有 labels 可逐項覆蓋，動態文案由宿主在接入層對映 i18next 或 Starling。
- 圖示、擴充套件頁籤、額外欄位、工具欄動作通過插槽或節點傳入，元件不繫結第三方 UI 庫。
- 列表型元件按上層展開後的行/項渲染，分頁、載入、錯誤、空態由模組 Hook 或宿主提供。

`WikiDashboard` 從 `@openviking/react/components/wiki-dashboard` 匯出，`ExperienceDashboard` 從 `@openviking/react/components/experience-dashboard` 匯出。兩者均為純 UI，接收展示資料和狀態；原生取數及響應適配由 FileBrowser 內部負責；元件和主 Props 型別同時從根入口匯出。FileBrowser 自動識別 Wiki/經驗入口，並接受 `dashboardKinds` 和 `renderDashboard` 接入宿主許可權與閘道器資料。各自樣式通過元件的 `style.css` 匯出，FileBrowser 樣式已包含兩類看板。詳見[看板文件](../../docs/docs/zh/components/index.mdx)。

## 公開入口與樣式

- 根入口只匯出各元件、各業務模組的元件本體與主 Props 型別（`<元件名>Props`），當前為 `FileTree`、`Tui`、`ScopeSwitcher`、`ScopeSelector`、`ScopeCascade`、`AgentConnect` 、Console、FileBrowser、WikiDashboard 與 ExperienceDashboard；行型別、選項型別、控制代碼與文案包等子型別只從 `components/<元件>`、`modules/<模組>` 子路徑匯出。`FilePreview` 不在根入口：它的型別依賴可選的 `@ark-design/ui`，放進根宣告會讓該 peer 變成必需。ScopeCascade 從 `modules/scope-cascade` 匯出元件，訂閱 Hook 保持內部實現，Console 從 `modules/console` 匯出組合檢視，編排 Hook 保持內部實現；FileBrowser 提供目錄與看板聯動。不提供 `@openviking/react/components` 或 `@openviking/react/modules` 分類聚合 JS 入口。包匯出顯式列舉，內部檔案不開放。
- 元件只提供明確列出的分層子路徑，不保留舊路徑別名。
- JS 入口共享實現，不隱式載入 CSS。整包、元件集合與單模組樣式由同一份原始碼構建，選擇所需範圍匯入即可。

| 範圍         | CSS 入口                                        |
| ------------ | ----------------------------------------------- |
| 整包         | `@openviking/react/style.css`                   |
| 元件集合     | `@openviking/react/components/style.css`        |
| 單元件       | `@openviking/react/components/<模組>/style.css` |
| 業務模組集合 | `@openviking/react/modules/style.css`           |
| 單業務模組   | `@openviking/react/modules/<模組>/style.css`    |

各 CSS 入口可獨立使用，並包含所依賴的元件樣式。所有業務 Hook 和控制器均為內部實現，不提供無頭 Hook 公開入口。

```tsx
import { FileBrowser } from '@openviking/react/modules/file-browser';
import '@openviking/react/modules/file-browser/style.css';

<FileBrowser
  locale="zh-CN"
  labels={{ title: '檔案瀏覽', description: '佔位元件，待接入。' }}
/>;
```

Console 的原生命令通過 Provider 請求配置接入，僅在顯式提交命令後訪問服務；對話資料和回撥由宿主提供。

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

將三個引用穩定的介面適配函式直接傳給 `<ScopeCascade {...api} onChange={handleSelection} />`。介面返回 `{ id, label }` 選項並接收 `AbortSignal`。元件內建請求、級聯、取消、重試和各級獨立訂閱。`onChange` 返回完整 `{ libraryId, spaceId, userId }` 身份，身份不完整時返回 `null`。從 `@openviking/react/modules/scope-cascade` 匯入元件和 Props，並引入對應 `/style.css`。

## 內建文案維護

內建語言資源就近放在各元件、模組的 `locales/en-US.ts` 與 `locales/zh-CN.ts`，隨程式碼一起維護。共同的語言型別、預設值和逐項覆蓋規則位於內部 `src/shared/locale.ts`；該檔案不存放業務詞條，也不提供公開入口。模組僅維護流程文案，元件預設文案由元件自己維護。

動態文案使用型別化格式化函式，日期與數字使用 `Intl`。`npm test` 自動檢查中英文 key、字串佔位符和格式化函式引數數量，型別檢查約束引數型別。已有 `labels` 的未定義項繼承當前語言，空字串作為顯式覆蓋保留。

在 `OpenVikingProvider` 上配置子樹語言。模組與元件的可選 `locale` Props 覆蓋最近的語言作用域，最終預設 `en-US`。內部 `src/shared/locale-context.tsx` 由各公開入口共享，與請求 Client 配置分離，切換語言保留請求和狀態。
