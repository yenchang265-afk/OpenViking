# ScopeSwitcher

[English](README.md) / 中文

`ScopeSwitcher` 是已實現的無狀態麵包屑佈局。通過 `@openviking/react/components/scope-switcher` 匯出的獨立 `ScopeSelector` 子元件組合層級，不再支援舊的 `levels` 屬性。每個子元件維護自己的展開狀態、接收本級資料，佈局根元件不彙總狀態或訂閱請求。

```tsx
<ScopeSwitcher>
  <ScopeSelector level={libraryLevel} />
  <ScopeSelector level={spaceLevel} />
  <ScopeSelector level={userLevel} />
</ScopeSwitcher>
```

## 職責邊界

- 宿主決定子元件的數量、順序與語義。不需要的層級直接省略；`fixed` 層級只展示當前值，不提供下拉。
- 選中項、選項、搜尋關鍵字、載入、錯誤和分頁由宿主提供。元件不取數、不持久化、不接管路由；`onScroll` 上報滾動資訊，供宿主實現分頁。
- 庫 → 空間 → 使用者的介面級聯可使用 `@openviking/react/modules/scope-cascade` 的 `useScopeCascade` 和 `ScopeCascade`。模組負責請求協調與獨立訂閱，元件仍為純檢視。

## 展開與選擇

- 不傳 `level.visible` 時，各選擇器自行管理開合。可選的 `onVisibleChange` 上報開合請求，包括選擇、Escape、外部點選和焦點離開選擇器。
- 傳入 `level.visible` 後由宿主控制開合，並通過 `onVisibleChange` 寫回狀態。選擇時先請求關閉，再呼叫 `onSelect`；受控宿主可以等非同步操作完成後再關閉。
- 選擇後，面板實際關閉時焦點返回觸發按鈕；如果焦點已移到外部則不搶回。Escape 關閉並恢復觸發按鈕焦點。停用的選擇器不能展開。

## 搜尋、插槽與鍵盤互動

- 傳入 `onSearchKeywordChange` 啟用搜索。當已載入數量或 `total` 超過 `SCOPE_SWITCHER_SEARCH_THRESHOLD`（10），或 `searchKeyword` 非空時顯示搜尋框。宿主過濾選項，檢視高亮命中內容。
- `renderPanel({ search, list })` 可將內建搜尋框、列表或狀態節點與標題、動作和自定義控制元件組合。自定義控制元件保留自身的鍵盤行為。
- `renderOption(content, option)` 可擴充套件或替換預設行內容。巢狀互動控制元件不會觸發行選擇。停用選項以及 `busy` 時的全部選項都不可選擇。
- 選項行支援 ArrowUp/ArrowDown、Home/End 移動焦點，Enter/空格選擇。內建搜尋框的上下方向鍵進入列表，Home/End 保留文本編輯行為。
- 觸發器使用 `aria-haspopup="dialog"` 與 `aria-expanded`；面板內的 `listbox` 包含帶 `aria-selected` 的 `option` 行。載入、空態與錯誤支援文案和兜底節點。

## 樣式與開發

顯式匯入 `@openviking/react/components/scope-switcher/style.css`，包含麵包屑膠囊、展開和選中態、下拉麵板，以及窄屏底部面板樣式。JavaScript 不隱式引入 CSS。

開發命令見[前端工作區 README](../../../../../README.md)，模組約定見[包說明](../../../README.md)。完整欄位契約以型別宣告為準。
