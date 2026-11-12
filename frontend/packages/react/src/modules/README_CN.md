# 區塊

[English](README.md) / 中文

`modules/` 存放區塊。每個區塊由內部 Hook 和組合元件組成：Hook 載入資料、適配資料並維護狀態，組合元件把 Hook 返回的資料和操作接入 `components/` 的檢視。宿主直接使用組合元件，自行組裝完整頁面。
VikingBot 是無頭模組：從 `@openviking/react/modules/viking-bot` 匯入 `useVikingBotChat`、`useVikingBotSessions` 及契約。Console 預設內建呼叫；獨立 VikingBot 宿主也可直接使用。它不匯出組合檢視或 CSS，Hook 不從包根或 Console 轉匯出。

## 區塊

| 區塊            | 元件           | 公開入口                                  | 組合內容                                                          |
| --------------- | -------------- | ----------------------------------------- | ----------------------------------------------------------------- |
| `file-browser`  | `FileBrowser`  | `@openviking/react/modules/file-browser`  | 圍繞同一個當前資源的目錄樹、搜尋與檔案預覽                        |
| `console`       | `Console`      | `@openviking/react/modules/console`       | 同一面板內的對話（`VikingBot`）與命令（`CommandConsole`）兩種模式 |
| `scope-cascade` | `ScopeCascade` | `@openviking/react/modules/scope-cascade` | 級聯的庫、空間與使用者選擇器                                        |
| `viking-bot`    | 無頭 Hook      | `@openviking/react/modules/viking-bot`    | 對話請求、流式狀態與會話管理，無組合檢視或 CSS                    |

每個區塊還有樣式入口 `@openviking/react/modules/<區塊>/style.css`，它包含所組合元件的樣式。用法、屬性和示例見[區塊文件](../../../../docs/docs/zh/modules/index.mdx)。

## 職責

- `useFileBrowser` 與 `useConsole` 是內部實現。它們通過共享 Client 呼叫 OpenViking 原生 API，繼承 Provider 的請求配置，管理載入、空態、錯誤、分頁、重新整理、重試，並清理仍在進行的請求。`ScopeCascade` 自己不發請求：三個載入函式由宿主提供。`Console` 通過 VikingBot 模組傳送原生對話請求，也允許宿主通過 `conversation` 接管。
- 組合元件把 Hook 返回的資料和操作交給 `components/` 的檢視，並協調區塊內的互動。
- 除上述 VikingBot 無頭模組外，宿主直接使用組合元件，不匯出其內部 Hook 或控制器。
- 標準接入只需要服務地址與鑑權，不要求逐區塊實現資料 Adapter。非標準閘道器由宿主在請求接入層統一適配。登入、帳號作用域、路由、許可權執行、頁面佈局及產品專屬流程由宿主負責。
- 區塊粒度以共同完成的互動流程為準：目錄、搜尋和預覽組成 `file-browser`；對話與命令組成 `console`。宿主組合區塊，不按內部檢視分別接入。

依賴方向是單向的：`modules/` → `components/` → `shared/`，以及 `modules/` → `client/`。元件是純檢視，只接收資料、狀態和回呼，不取數，也不從 `modules/` 匯入任何東西。僅一個區塊使用的 Hook、型別和工具留在該區塊目錄；多個區塊共用的程式碼再放入 `src/shared/`。

## 請求契約與預設配置

共享 Client 按 method、路徑、query 和 body 向 OpenViking 原生 API 發請求，並解析原生響應外殼。它維護在 `src/client/`，從 `@openviking/react/client` 匯出：基於 `fetch` 的 `createOvClient`、`OvClient` 介面、`OvRequestOptions`、`OvClientError`，以及路徑表 `OV_PATHS` 與 `OV_PATH_BUILDERS`。該目錄裡只有 `OpenVikingProvider` 使用 React。區塊 Hook 消費原生資料並派生檢視所需的狀態與操作，宿主因此不需要逐區塊維護資料協議。客戶端本身的用法見 [Client README](../client/README_CN.md)。

`OpenVikingProvider` 通過 Context 下發通用配置，並在 Provider 例項內複用穩定的 Client。宿主傳的是欄位值（`baseURL`、`apiKey`、`accountId`、`userId`、`resourceId`、`credentials`），請求頭由 Client 組裝；區塊通過內部 Hook 取用客戶端，不自己拼請求。Context 不快取業務資料。Provider 掛載本身不取數，也不讀取瀏覽器中儲存的憑證。每個欄位及其請求頭見 Client README 的[配置欄位](../client/README_CN.md#配置欄位)。

`FileBrowserProps` 與 `ConsoleProps` 宣告同一個可選的 `requestOptions` 覆蓋，型別是 `OvRequestOptions`，按欄位解析：**區塊顯式配置 → 最近的 Provider 配置 → 庫預設值**。巢狀的 Provider 只覆蓋它宣告的欄位。不傳欄位或傳 `undefined` 表示繼承，`baseURL: ''` 明確切回同源。覆蓋裡省略的身份欄位繼承 Provider 的值，顯式傳空字串則清除它。覆蓋不會修改父 Provider，也不影響其他區塊例項。大部分接入只配置一次 Provider。`ScopeCascade` 沒有 `requestOptions`：它通過宿主傳入的三個載入函式工作。

宿主在應用根部配置一次 Provider：

```tsx
import { OpenVikingProvider } from '@openviking/react/client';
import { Console } from '@openviking/react/modules/console';
import { FileBrowser } from '@openviking/react/modules/file-browser';

<OpenVikingProvider
  baseURL={endpoint}
  apiKey={apiKey}
  accountId={accountId}
  userId={userId}
  resourceId={libraryId}
>
  <FileBrowser />
  <Console />
</OpenVikingProvider>;
```

區塊內部通過 Hook 取客戶端，只傳需要覆蓋的欄位，例如訪問另一個庫時：

```ts
const rows = await client.request<FsEntry[]>({
  method: 'GET',
  path: OV_PATHS.fsLs,
  query: { uri },
  options: { resourceId: libraryId },
});
```

該 Hook 不對外匯出：宿主不需要知道區塊會發什麼請求。`components/` 下的元件完全不需要 Provider。URI、查詢詞等業務引數是區塊的 props，不屬於 Provider 配置。

- **路徑只有一處拼接**：介面路徑集中在 `OV_PATHS` 與 `OV_PATH_BUILDERS`，區塊不寫字面量；Client 保留 `baseURL` 的路徑字首，例如 `/gateway/openviking` 加 `/api/v1/fs/ls` 得到 `/gateway/openviking/api/v1/fs/ls`，不會因介面路徑以 `/` 開頭而丟掉閘道器字首。區塊不拼接域名或服務字首。
- **響應只在 Client 解析**：HTTP 失敗與原生響應的 `status: 'error'` 都丟擲 `OvClientError`，保留服務端錯誤碼、狀態和請求標識。`request` 返回 `result`；`requestEnvelope` 返回 `{ result, hasMore }`，用於分頁列表，FileBrowser 就用它配合 `node_limit` 與 `offset` 分頁。`responseType: 'blob'` 返回原始位元組，`stream` 逐個產出事件流事件，兩者都不強轉 JSON。
- **身份與配置變化要隔離**：新的客戶端（Provider 配置變了）、`requestOptions` 裡變化的欄位，以及 FileBrowser 的 `rootUri` 變化，都會讓區塊視為新的作用域：中止仍在進行的請求並丟棄它們的遲到結果，舊帳號的響應因此不會落進新檢視。以函式形式傳入的身份無法自己通知變化：FileBrowser 按函式引用區分它們，Console 則提供顯式的 `scopeKey`，身份變化時要同時更換它。
- **適配集中在接入層**：原生介面只需要地址和請求頭。存量閘道器由宿主在共享 Client 接入層統一適配一次，並保留取消訊號、響應狀態及流。無法等價表達的能力通過擴充套件契約接入，不在每個區塊增加宿主分支。

## 區塊邊界

- **當前資源由 FileBrowser 協調**：它在目錄、搜尋和預覽之間同步當前 URI。宿主傳入 `uri` 與 `onUriChange` 即可受控地決定 URI，例如開啟 `Console` 通過 `onOpenUri` 上報的連結。區塊只上報變化，不直接操作其他區塊的狀態或路由。
- **身份由宿主提供**：切換庫、空間或使用者，與切換登入帳號是不同的操作。`ScopeCascade` 提供庫、空間與使用者的選擇；登入、帳號儲存、API Key 管理與失效處理仍歸宿主。
- **看板是元件**：`wiki-dashboard` 與 `experience-dashboard` 是 `components/` 下的純檢視。FileBrowser 的私有 Hook 載入原生資料、適配成看板的展示模型並渲染。`dashboardKinds` 限制 FileBrowser 識別哪些看板，`renderDashboard` 用宿主自己的檢視替換內建檢視，返回空值則保留內建檢視。
- **佈局**：每個區塊負責自己內部區域的佈局，宿主通過 props 和插槽定製。外部佈局以及區塊在頁面中的位置由宿主決定。

## 新增或修改區塊

每個區塊使用獨立的 kebab-case 目錄，入口檔案與目錄同名。`index.ts` 匯出組合元件及宿主需要的型別，Hook 保持內部實現。公開的 JS 與 CSS 入口要同時加入 `package.json` 的 `exports` 和 `rslib.config.ts`，並在 `modules/style.css` 中引入該區塊的 `style.css`。區塊樣式包含所組合元件的樣式。不提供聚合 `modules/` 的 JavaScript 入口。

步驟、命令與 CI 見[前端工作區 README](../../../../README.md)，包的入口見[包說明](../../README_CN.md)，實施約束見本目錄 [AGENTS.md](./AGENTS.md)。
