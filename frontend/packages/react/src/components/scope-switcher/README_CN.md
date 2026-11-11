# ScopeSwitcher

[English](README.md) / 中文

可選 `locale: 'zh-CN' | 'en-US'` 覆蓋最近的模組或 Provider；均未配置時預設 `en-US`。已有 `labels` 可逐項覆蓋。業務內容仍由宿主提供。

`ScopeSwitcher` 是已實現的無狀態麵包屑佈局。通過 `@openviking/react/components/scope-switcher` 匯出的獨立 `ScopeSelector` 子元件組合層級，不再支援舊的 `levels` 屬性。每個子元件維護自己的展開狀態、接收本級資料，佈局根元件不彙總狀態或訂閱請求。

```tsx
<ScopeSwitcher locale="zh-CN">
  <ScopeSelector locale="zh-CN" kind="selectable" identity={...} data={...} state={...} actions={...} />
  <ScopeSelector locale="zh-CN" kind="selectable" identity={...} data={...} state={...} actions={...} />
  <ScopeSelector locale="zh-CN" kind="fixed" identity={...} trigger={{ label: 'default' }} />
</ScopeSwitcher>
```

## 職責邊界

- 宿主決定子元件的數量、順序與語義。不需要的層級直接省略；`fixed` 層級只展示當前值，不提供下拉。
- 選中項、選項、搜尋關鍵字、載入、錯誤和分頁由宿主提供。`data.options` 是判斷選中值是否有效的權威集合，`data.visibleOptions` 只是渲染子集，因此搜尋過濾不會讓當前作用域失效。元件不取數、不持久化、不接管路由；`actions.onScroll` 上報滾動資訊，供宿主實現分頁。
- 庫 → 空間 → 使用者的介面級聯可使用 `@openviking/react/modules/scope-cascade` 的 `useScopeCascade` 和 `ScopeCascade`。模組負責請求協調與獨立訂閱，元件仍為純檢視。

## 展開與選擇

- 不傳 `state.visible` 時，各選擇器自行管理開合。可選的 `actions.onVisibleChange` 上報開合請求，包括選擇、Escape、外部點選和焦點離開選擇器。
- 傳入 `state.visible` 後由宿主控制開合，並通過 `actions.onVisibleChange` 寫回狀態。選擇時先請求關閉，再呼叫 `actions.onSelect`；受控宿主可以等非同步操作完成後再關閉。
- 選擇後，面板實際關閉時焦點返回觸發按鈕；如果焦點已移到外部則不搶回。Escape 關閉並恢復觸發按鈕焦點。停用的選擇器不能展開。

## 搜尋、插槽與鍵盤互動

- 傳入 `actions.onSearchKeywordChange` 啟用搜索。當已載入數量或 `total` 超過 `SCOPE_SWITCHER_SEARCH_THRESHOLD`（10），或 `searchKeyword` 非空時顯示搜尋框。宿主過濾選項，檢視高亮命中內容。
- `slots.renderPanel({ search, list })` 可將內建搜尋框、列表或狀態節點與標題、動作和自定義控制元件組合。自定義控制元件保留自身的鍵盤行為。面板高度上限不變，宿主內容更高時在面板內滾動。
- `slots.renderOption(content, option)` 可擴充套件或替換預設行內容。巢狀互動控制元件不會觸發行選擇。停用選項以及 `busy` 時的全部選項都不可選擇。
- 選項行支援 ArrowUp/ArrowDown、Home/End 移動焦點，Enter/空格選擇。內建搜尋框的上下方向鍵進入列表，Home/End 保留文本編輯行為。
- 觸發器使用 `aria-haspopup="dialog"` 與 `aria-expanded`；面板內的 `listbox` 包含帶 `aria-selected` 的 `option` 行。載入、空態與錯誤支援文案和兜底節點。

## 樣式與開發

顯式匯入 `@openviking/react/components/scope-switcher/style.css`，包含麵包屑膠囊、展開和選中態、下拉麵板，以及窄屏底部面板樣式。JavaScript 不隱式引入 CSS。

整行 32px 高，無描邊。每一段是獨立的 32px 高、16px 圓角膠囊，左右 8px 內邊距、圖示與文字間距 8px，文字 13px、字重 500。懸停、聚焦和展開時描主色邊框；常態保留透明描邊，因此邊框出現時不會引起位移。

整行不換行。空間不足時各層級收縮、標籤省略，因此文案在中英文之間切換不會改變外框高度。

帶下拉的層級在懸停、聚焦和展開時給按鈕鋪淺底，與面板裡選項行的反饋一致。不帶下拉的層級（`kind: 'fixed'`）幾何引數完全相同，只去掉箭頭和懸停反饋，因此只讀的作用域仍屬於同一條麵包屑。相鄰層級由 CSS 畫出 `#c9cbd4` 的 `/`。

面板內懸停行鋪淺底，選中行常駐主色淺底、文字加粗、行尾顯示勾選；文字顏色不變，設計稿用字重和底色區分選中。搜尋命中片段染主色，不加黃底。

選項行首圖示裝在一個 24px 的底槽裡：純白底、0.5px `#edeef2` 描邊、12px 圓角，圖形本身保持 14px。宿主渲染圓形頭像時把 `--ov-ui-scope-switcher-option-icon-radius` 設為 `50%`。

圖示由宿主通過 `trigger.icon` 與 `option.icon` 傳入，元件本身不內建任何層級圖示，也不按層級語義推斷。需要預設圖示時從 `@openviking/react/icons` 取 `LibraryIcon`、`SpaceIcon`、`UserIcon`；`ScopeCascade` 的預設檢視已經在適配函式沒給 `icon` 時自動補上這三個，宿主給了就照用宿主的。

主題變數宣告在 `.ov-scope-switcher` 上，宿主可只覆蓋其中一條：`--ov-ui-scope-switcher-divider`、`-icon`、`-option-icon`、`-option-icon-size`、`-option-icon-radius`、`-row-hover`、`-tag-background`、`-tag-text`、`-panel-width`、`-option-height`、`-option-gap`、`-list-max-height`、`-panel-max-height`。

共用顏色走包級主題基線，寫法為 `var(--ov-ui-color-<token>, var(--ov-ui-<token>-default, 兜底))`：宿主在祖先上設定了 `--ov-ui-color-*` 就用宿主的，否則用基線預設值。元件不在自己根節點上宣告公開的 `--ov-ui-color-*`，否則會阻斷宿主的值向下繼承。這裡用到的 token：`text-1`、`text-3`、`text-disabled`、`border-1`、`border-2`、`border-3`、`bg-1`、`primary`、`primary-light`。

開發命令見[前端工作區 README](../../../../../README.md)，模組約定見[包說明](../../../README.md)。完整欄位契約以型別宣告為準。
