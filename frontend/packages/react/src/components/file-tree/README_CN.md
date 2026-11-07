# FileTree

[English](README.md) / 中文

面向資源瀏覽的目錄樹。宿主把樹狀態展平成有序行列表傳進來，通過 `operations` 提供非同步執行能力；元件負責渲染、鍵盤互動，並在操作成功後通知。

> **當前是佔位實現。** 它已按公開 props 渲染全部已定義的行型別，接入方可對著 API 開發，但樣式、圖示與互動細節都會調整，檢視後續按本文契約重寫。

```tsx
import { FileTree } from '@openviking/react/components/file-tree';
import '@openviking/react/components/file-tree/style.css';

<FileTree
  rows={rows}
  selectedId={selectedId}
  operations={{
    select: async (row) => setSelectedId(row.id),
    toggleExpand: async (row) => toggle(row.id),
  }}
/>;
```

`rows` 從哪來、分頁怎麼取、許可權怎麼判，都由宿主決定——元件不碰這些。

## 為什麼是「展平行列表」

目錄樹最常見的做法是讓元件接收巢狀結構，自己遞迴渲染、自己維護展開集合、自己決定何時請求子節點。這樣元件就得知道宿主的分頁策略、錯誤重試方式、帳號作用域切換時機，最後變成一個什麼都懂一點、又和某個後端綁死的東西。

這裡反過來：**宿主負責把樹狀態壓平成一維陣列，元件只按順序渲染**。

```ts
type FileTreeRow =
  | FileTreeEntryRow // 目錄或檔案
  | FileTreeLoadingRow // 子節點載入中
  | FileTreeLoadMoreRow // 還有下一頁
  | FileTreeErrorRow // 子節點載入失敗
  | FileTreeEmptyRow; // 展開後是空的
```

帶來的直接結果：

- 分頁、懶載入、失敗重試都由宿主在自己那側實現，元件不需要知道「怎麼取下一頁」。
- 只返回全部子節點的資料來源不會產出 `load-more` 行，行為自然等價，不用傳開關。
- 行是普通物件，宿主可以在傳進來之前做任何加工（排序、過濾、許可權收斂）。

代價是宿主需要寫一個「樹狀態 → 行陣列」的轉換函式。這份成本換的是元件可以同時服務分頁資料來源與全量資料來源、服務不同的鑑權模型，而 UI 完全一致。

## 元件負責什麼

- 渲染行：圖示、縮排、層級標記、副標題、寫入中指示。
- 鍵盤互動：方向鍵移動、左右鍵展開摺疊、Enter/Space 選中，`role="tree"` 與 `aria-*` 完整。
- 選中、展開、載入更多、重試和開啟保留策略設定通過 `operations` 執行，完成後才觸發對應的 `on…` 成功通知；失敗時不觸發。省略執行方法時停用對應操作，省略通知不影響執行。
- 三類整樹級狀態的展示位：載入中、載入失敗、空樹，內容由宿主給。
- 懸停浮層的延遲、定位與抑制。

## 元件不負責什麼

- 不請求任何資料，不建連線，不做許可權判斷。
- 不維護展開集合與選中項——兩者都是受控的。
- 點選目錄與點選檔案共用 `operations.select`，由宿主按 `row.type` 分流；選中成功後通過 `onSelect` 通知。
- 工具欄、搜尋、匯入來源、許可權流程屬於頁面層，通過 `slots.toolbar` 注入。

## 擴充套件點

**行尾與懸停**：`renderDashboard` 放行尾指示器（例如看板入口），`renderRowTooltip` 放懸停內容。兩者返回 `null` 即不顯示；看板判定屬於產品語義，元件不內建路徑規則。

**行級一次性效果**：高亮、閃爍、臨時描邊不屬於樹的屬性。元件給每條行元素設定 `data-file-tree-row-id`（常量 `FILE_TREE_ROW_ATTRIBUTE`），頁面層可直接查詢該元素，也可以用 `getRowAttributes` 按行資料追加屬性，或用 `ref` 控制代碼的 `getRowElement` / `scrollToRow`。三種方式可組合，都不改變元件狀態。

**ref**：按 `forwardRef` 契約定義（型別 `FileTreeComponent`），React 18 與 19 都能拿到控制代碼。不要把它宣告成 `FileTreeProps` 的欄位——React 18 會把 `ref` 從 props 中剝離。

## 主題

樣式區域性化，不修改應用的全域性樣式。顏色、圓角、焦點環通過 `--ov-ui-*` 變數覆蓋，完整清單見元件文件的主題變量表。

## 文件與開發

- 屬性表、可執行示例、主題變數見[元件文件](../../../../../docs/docs/en/components/file-tree.mdx)（[中文](../../../../../docs/docs/zh/components/file-tree.mdx)）。
- 開發與構建命令見[前端工作區 README](../../../../../README.md)，模組約定見[包說明](../../../README.md)。
- 獨立樣式入口 `@openviking/react/components/file-tree/style.css`，與 JS 入口分離，可按需引入。
