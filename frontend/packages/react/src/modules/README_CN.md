# 業務模組

[English](README.md) / 中文

`modules/` 按共同完成的互動流程組織 Hook 與組合檢視，共享狀態與聯動在模組內維護。Hook 負責載入請求、適配資料與維護狀態，組合檢視把 Hook 返回的資料和操作接入 `components/`。完整頁面由宿主組裝。

Console 已匯出命令組合檢視，取數與狀態 Hook 內建，接通原生請求、取消、重試與身份隔離；對話服務後續接入。FileBrowser 已通過 `useFileBrowser` 實現目錄、搜尋與預覽聯動。

## 當前可接入的模組

Console 已提供原生命令面板；FileBrowser 已實現目錄、搜尋與預覽聯動。各模組均有公開型別與獨立樣式入口，下文區分本期實現與後續目標。

模組預設通過 Hook 取數，宿主給配置、受控值與文案，模組通過回撥上報變化。Wiki 與經驗看板是純 UI；FileBrowser 的私有 Hook 負責取數與適配，再向看板傳入展示資料。

| 模組           | 元件          | 公開入口                                 |
| -------------- | ------------- | ---------------------------------------- |
| `file-browser` | `FileBrowser` | `@openviking/react/modules/file-browser` |
| `console`      | `Console`     | `@openviking/react/modules/console`      |

```tsx
import { FileBrowser } from '@openviking/react/modules/file-browser';
import '@openviking/react/modules/file-browser/style.css';

<FileBrowser locale="zh-CN" labels={{ title: '檔案瀏覽' }} />;
```

模組元件與主 Props 型別也從 `@openviking/react` 根入口匯出；Labels、Slots 與列舉型別從模組子路徑匯出。可執行示例與屬性說明見[模組文件](../../../../docs/docs/zh/modules/index.mdx)。以下各節描述目標架構和待遷入能力。

## 職責

- 模組 Hook 預設通過共享 Client 呼叫開源原生 API，繼承 Provider 的請求配置，管理載入、空態、錯誤、分頁、重新整理、重試和必要的連線清理。
- Hook 返回檢視可消費的資料、狀態與操作；組合檢視負責把這些能力接入元件，協調模組內的互動。
- 宿主直接使用組合元件，Hook 為內部實現，不提供無頭介面。
- 標準接入只配置服務地址與鑑權，不要求宿主逐模組實現資料 Adapter；非標準閘道器在宿主請求接入層適配。認證、帳號作用域、路由、許可權執行、頁面佈局及產品專屬流程仍由宿主負責。

依賴方向為 `modules → components`。元件保持純 UI，只接收資料、狀態和回撥；原生取數放在模組私有 Hook 中。模組專屬 Hook、型別、工具和私有檢視留在模組目錄；跨元件內部 Hook 有真實複用需求後再放入 `src/shared/`。

## 個人終端的層級

當前按個人終端規劃共享能力，管理後臺不在本期範圍內。層級表示職責與依賴方向，不對應新的 npm 包：

| 層級           | 職責                                                                                   |
| -------------- | -------------------------------------------------------------------------------------- |
| 宿主應用       | 頁面佈局、路由、登入與帳號、當前庫 / 資料空間 / User、許可權與能力配置，以及模組間聯動 |
| `modules/`     | 一項可獨立接入的業務能力：資料載入 Hook、業務狀態與操作、可替換的組合檢視              |
| `components/`  | 可獨立使用的純 UI 元件，不感知介面                                                     |
| 服務與基礎能力 | 開源原生 API Client、資源型別與純資料轉換；按實際實現放入 `client/`、`lib/` 等邊界     |

宿主可以直接使用元件或模組提供的組合檢視。每個業務模組獨佔一個目錄，粒度以可獨立接入的互動流程為準：目錄、搜尋和預覽組成 `file-browser`；對話與 TUI 組成 `console`，在模組內切換模式。宿主組合這兩個區域及其他模組，不按內部檢視分別接入。

## 請求契約與預設配置

共享 Client 以 OpenViking 原生 API 的 method、路徑、query / body 和響應 DTO 為契約，維護在 `src/client/`，從 `@openviking/react/client` 匯出。它自帶基於 `fetch` 的 `createOvClient`，並提供模組依賴的契約——請求形狀、配置解析、`OvClient` 與 `OvClientError`。程式碼不依賴 React，出現 React 之外的消費方後再拆為獨立包。模組 Hook 消費原生資料並派生檢視所需的狀態與操作，不要求宿主逐模組維護資料協議。

React 接入由 `@openviking/react/client` 的 `OpenVikingProvider` 通過 Context 下發通用配置，並在 Provider 例項內複用穩定的 Client。宿主傳的是身份欄位——`apiKey`、`accountId`、`userId`、`resourceId`——請求頭由 Client 組裝；模組通過內部 Hook 取用，不自己拼請求。Context 不承擔業務資料快取；Provider 掛載本身不取數，也不讀取瀏覽器中儲存的憑證。

| 配置          | 約定                                                                                                                   |
| ------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `baseURL`     | 服務地址及可選閘道器字首，不包含原生介面的 `/api/v1`；預設空字串，表示瀏覽器同源請求。服務端發起請求時顯式提供絕對地址 |
| `apiKey`      | 憑證。開源版對映為 `X-API-Key`；商業版由瀏覽器 Cookie 承載。函式形式每次請求重新求值                                   |
| `accountId`   | OpenViking 帳號，對應資料空間                                                                                          |
| `userId`      | 帳號內的使用者                                                                                                         |
| `resourceId`  | 當前庫；資料面介面需要它                                                                                               |
| `credentials` | 傳給 `fetch` 的 `RequestCredentials`。預設 `include`，可按需覆蓋為 `same-origin` 或 `omit`                             |

模組元件使用同一份可選 `requestOptions` 覆蓋型別，即 `@openviking/react/client` 的 `OvRequestOptions`。按欄位解析：**模組顯式配置 → 最近的 Provider 配置 → 庫預設值**；巢狀 Provider 在父配置上覆蓋。不傳欄位或傳 `undefined` 表示繼承，`baseURL: ''` 則明確切回同源；覆蓋裡省略的身份欄位繼承 Provider 的值，顯式傳空字串則清除它。覆蓋不修改父 Provider，不影響其他模組例項。大部分接入只配置一次 Provider。兩個模組的 `FileBrowserProps` 與 `ConsoleProps` 均已宣告該欄位。

Provider、`useFileBrowser` 和 `useConsole` 已實現。FileBrowser 自動載入目錄，Console 只在顯式提交命令時發請求。宿主在應用根部配置一次：

```tsx
import { OpenVikingProvider } from '@openviking/react/client';

<OpenVikingProvider
  baseURL={endpoint}
  apiKey={apiKey}
  accountId={accountId}
  userId={userId}
  resourceId={libraryId}
>
  <FileBrowser locale="zh-CN" />
  <Console locale="zh-CN" />
</OpenVikingProvider>;
```

模組通過內部 Hook 取客戶端，只傳需要覆蓋的欄位，例如訪問另一個庫時：

```ts
const rows = await client.request<FsEntry[]>({
  method: 'GET',
  path: OV_PATHS.fsLs,
  query: { uri },
  options: { resourceId: libraryId },
});
```

該 Hook 不對外匯出：宿主不需要知道模組會發什麼請求。純檢視元件完全不需要 Provider。當前身份可由 Context 下發，其中 `accountId` 對應資料空間，`userId` 對應該空間內的 User；身份作用域與請求配置分別維護。URI、查詢詞等模組業務引數仍通過模組 / Hook 入參提供。

- **路徑只有一處拼接**：介面路徑由 `@openviking/react/client` 的 `OV_PATHS` / `OV_PATH_BUILDERS` 集中維護，模組不寫字面量。Client 保留 `baseURL` 的路徑字首。例如 `/gateway/openviking` 加 `/api/v1/fs/ls` 得到 `/gateway/openviking/api/v1/fs/ls`，不會因介面路徑以 `/` 開頭而丟掉閘道器字首。模組不拼接域名或服務字首。
- **響應只在 Client 解析**：區分 HTTP 失敗與原生響應的 `status: 'error'`，保留服務端錯誤碼、狀態和請求標識。`request` 預設返回 `result`；二進位制響應用 `responseType: 'blob'` 取原始位元組，事件流用 `stream` 逐個消費，兩者都不強轉 JSON。`has_more` 這類 `result` 之外的分頁後設資料目前不返回，需要分頁的模組按 `offset` / `node_limit` 自行判斷。
- **配置與身份變化要隔離**：請求、快取鍵和訂閱以實際生效的服務地址及宿主當前連線 / 身份作用域隔離。切換服務或帳號後取消舊請求並忽略過期結果；動態 headers 不代替身份切換訊號，也不把 API Key 明文放入快取鍵。
- **適配集中在接入層**：原生介面只需配置地址和 headers；存量閘道器若有額外封裝，由宿主在共享 Client 接入層統一適配，並保留取消訊號、響應狀態及流。無法等價表達的能力通過顯式擴充套件契約接入，不在每個模組增加宿主分支。

Provider 的繼承遵循 [React Context](https://react.dev/reference/react/useContext)，請求層遷入參考[現有 Client 封裝](../../../../../web-studio/src/shared/api/ov-client/client.ts)。傳輸層與 Provider 已按這些約定實現；首個模組 Hook 落地時再一起驗證。

## 業務模組劃分

下表描述目標能力。FileBrowser 的目錄、搜尋與預覽聯動和 Console 命令側已實現；對話服務由宿主接入。產品引導、資源與 Skill 匯入流程及同步配置由宿主負責，不提供對應業務模組。

| 模組           | Hook 與業務職責                                                                                   | 組合檢視                                                                    |
| -------------- | ------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `file-browser` | 統一管理目錄、檢索、當前 URI、預覽載入與編輯儲存；協調定位、重新整理、歷史與版本對比              | 組合 `FileTree`、搜尋互動與 `FilePreview`，提供目錄和內容聯動的檔案瀏覽區域 |
| `console`      | 統一管理對話 / TUI 模式、公共上下文與工具欄；處理對話會話、訊息流、附件、記憶提交及命令執行與記錄 | 組合模組內的對話檢視、`Tui` 與模式切換，提供完整的互動面板                  |

歷史列表與版本對比先作為 `file-browser` 的預覽能力，編譯確認作為 `console` 中的 Bot 動作流程；有獨立消費需求後再拆公開模組，不為每個按鈕或彈窗建模組。公共檢視元件按真實複用需求補充，表中組合檢視不要求提前新增元件佔位。

### 檔案瀏覽模組

`file-browser` 計劃覆蓋目錄導航、搜尋與內容預覽的整個聯動區域，通過內部 `useFileBrowser` 協調取數，對外提供 `FileBrowser` 組合元件：

- Hook 統一返回目錄、搜尋、當前資源及預覽的資料、狀態與操作。內部可拆私有 Hook，不對外公開 Hook。
- 點選目錄節點或搜尋結果後，模組協調當前 URI、目錄定位與預覽載入；切換資源時清理舊請求，避免過期內容覆蓋當前預覽。
- 儲存、重新命名或刪除資源後，模組重新整理受影響的目錄、搜尋結果與預覽；刪除當前資源時同步清理選中狀態和內容。
- 組合檢視負責區域內的搜尋、目錄與預覽佈局。`FileTree`、`FilePreview` 等純檢視元件保持獨立，不承擔資料載入或跨元件編排。
- 連線 Agent、匯入資源等操作入口通過宿主回撥或插槽接入；模組不內建接入彈窗、匯入流程或產品引導。配額提示等產品內容也通過宿主插槽接入。

以上互動已實現：`useFileBrowser` 取數與協調目錄、搜尋、預覽的聯動，`FileBrowser` 組合檢視按控制台的上下文面板佈局渲染。

### 互動面板模組

`console` 覆蓋對話與 TUI 共用的整個面板，對外提供 `Console` 組合元件：

- Hook 統一管理當前模式、公共上下文、對話與命令的資料、狀態和操作；組合檢視協調模式切換與工具欄操作。
- 對話與 TUI 使用同一服務、身份與宿主傳入的資源上下文；各自維護訊息歷史、命令記錄與執行狀態，切換模式時保留各自狀態。
- 對話能力包括會話、訊息流、附件、記憶提交與編譯動作；TUI 能力包括命令定義、執行、取消與執行記錄，可用命令遵循宿主提供的能力。
- 組合檢視負責模式切換、公共工具欄與內容區域，操作按當前模式分發。`Tui` 作為可獨立消費的純檢視元件接入；對話檢視複用 VikingBot，服務接入後續實現。
- 開啟資源、定位產物或重新整理目錄通過事件交給宿主，與 `file-browser` 的聯動不依賴對方私有狀態；登入、身份切換與產品引導仍由宿主負責。

`Console` 已實現命令執行、取消、重試、記錄與獨立草稿，同一模組入口僅公開元件和必要型別，`useConsole` 作為內部實現；對話會話、流式回覆、附件和記憶提交後續接入。支援的命令子集見 [Console 文件](../../../../docs/docs/zh/modules/console.mdx)。

## 組合與擴充套件邊界

- **當前資源由檔案瀏覽模組協調**：`file-browser` 預設維護選中 URI 並同步目錄、搜尋和預覽。宿主可受控傳入 URI，或通過模組公開操作開啟任務產物與 Bot 連結；模組上報資源變化，不直接操作其他模組的 Store 或路由。
- **預覽頁籤屬於同一資源**：個人終端不維護多個已開啟檔案的工作區頁籤。L0 / L1 / 目錄內容以及經驗看板等屬於當前資源的內容檢視；不據此收窄通用 `FilePreview` 的頁籤 API。
- **特定內容通過擴充套件接入**：經驗看板、會話內容及 Wiki 等檢視有獨立的取數與展示邏輯，通過預覽擴充套件頁籤接入，留在業務擴充套件或宿主；不讓通用 `FilePreview` 識別這些業務型別。Skill 瀏覽複用目錄與目錄內容。
- **任務狀態歸任務資料來源**：`console` 不上報任務進度或資源變更——它觀察不到請求返回之後才完成的非同步工作。需要響應任務結果的宿主自行從任務資料來源讀取；任務狀態不在各模組複製維護。
- **身份由宿主提供**：庫 / 資料空間 / User 切換與登入帳號切換是不同操作。作用域切換檢視由宿主提供；登入、帳號儲存、API Key 管理與失效處理仍歸宿主。模組按顯式作用域隔離請求、快取與訂閱，切換後清理舊操作。
- **可選能力由宿主接入**：刪除、OAuth、OVPack、同步來源、隱私及境外提示由宿主提供服務能力、動作和文案。OVPack 使用獨立的目錄遷移服務契約，不混入普通資源上傳；可作為目錄操作擴充套件。當前不規劃 TOS 匯入、手寫 Skill、獨立編譯頁面或管理後臺模組。
- **佈局按模組邊界負責**：`file-browser` 負責目錄、搜尋與預覽的內部佈局，`console` 負責對話 / TUI 模式切換及面板內部佈局；宿主可通過元件引數和插槽定製。兩個區域的外部佈局由宿主決定；引導、任務、幫助、帳號等頂欄入口的位置也歸宿主。

## 當前狀態與開發入口

每個模組使用獨立的 kebab-case 目錄，入口檔案與目錄同名。FileBrowser 與 Console 均從模組入口匯出元件及必要型別，Hook 和控制器保持私有，並提供獨立樣式與構建入口。

開發命令和構建入口見 [前端工作區 README](../../../../README.md)，包結構見[包說明](../../README.md)，實施約束見本目錄 [AGENTS.md](./AGENTS.md)。

已開放 `@openviking/react/modules/<模組>`，不提供分類聚合 JS 入口。模組 CSS 同時提供 `@openviking/react/modules/style.css` 與 `@openviking/react/modules/<模組>/style.css`，整包 `@openviking/react/style.css` 也包含模組樣式。Console 樣式包含 Tui 與 VikingBot，其餘模組樣式包含當前檢視；後續單獨使用 Hook 無需匯入 CSS。

## 獨立看板

`wiki-dashboard` 與 `experience-dashboard` 作為獨立元件從 `components/` 匯出元件和資料型別，Hook 內建，由 FileBrowser 自動組合；宿主也可單獨消費。看板保留只讀資料擴充套件入口 `data`，便於對映閘道器附加指標。FileBrowser 的 `dashboardKinds` 由宿主對映許可權，`renderDashboard` 可接入同一看板元件的宿主資料。資源不存在時不顯示 Wiki 入口，已識別的零衝突 Wiki 保留空看板。
