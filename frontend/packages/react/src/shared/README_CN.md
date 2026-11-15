# 內部共享程式碼

[English](README.md) / 中文

供多個元件或區塊複用的內部程式碼，**沒有公開入口**。這裡的內容不出現在包根入口、子路徑或 `package.json` 的 `exports` 中：宿主無法匯入，也不承擔相容性承諾。

出現第二個真實消費者時，程式碼才提升到這裡；單個元件用到的東西留在該元件目錄內。共享程式碼不依賴 `components/`、`modules/` 或任何宿主契約：依賴是單向的，從它們指向本目錄。需要業務資料、路由或宿主服務的程式碼屬於 `modules/`。放置規則見 [Frontend Agent Guide](../../../../AGENTS.md)。

這裡的樣式由使用它的元件自己的 `style.css` 引入，而不是 `components/style.css`：沒有公開入口指向本目錄。

## 內容

有哪些目錄以實際目錄為準，下面只說明每個目錄的用途。

### `primitives/`

內部通用基礎件。業務內容與專屬樣式由呼叫方通過 `children` 或 props 提供。

- `button`：Arco 精簡按鈕，提供型別、尺寸、圖示、載入態、原生事件和 ref。只有 `htmlType="submit"` 時才提交表單。不含連結、按鈕組和 `ConfigProvider` 耦合。
- `input`：Arco 精簡 `Input`，提供原生事件、表單屬性、ref、尺寸以及裝飾性前後綴，另有帶樣式的 `TextArea`。不含密碼顯隱、計數、清空和自動尺寸。
- `select`：通過 children 組合選項，單選和多選統一使用陣列值，提供 Input 外殼、無邊框 Simple 模式及自定義回顯和觸發器。見 [Select](./primitives/select/README.md)。
- `modal`：改編自 Arco 的受控居中彈窗，提供過渡動畫、焦點鎖和共享的 body 滾動鎖。關閉按鈕文案放在它自己的 `locales/` 中。
- `drawer`：右側抽屜，提供過渡動畫、焦點鎖和共享的 body 滾動鎖，內容通過 `children` 傳入。
- `tooltip`：渲染到 `document.body` 的定位浮層，懸停或聚焦時顯示，也可以點選切換。渲染到 body 是因為祖先容器的 `overflow: hidden` 會裁掉常規浮層。
- `popover`：`tooltip` 的白底卡片版本，用於結構化或可互動的內容，同樣渲染到 `document.body`，觸發方式與方位選項和 `tooltip` 一致。
- `divider`：一條 `role="separator"` 的分隔線，長度、粗細和顏色由呼叫方給出。
- `resizable`：`ResizableHandle`，可拖拽的 `role="separator"` 分隔條，用指標拖動或方向鍵調整相鄰面板的寬度。寬度由呼叫方持有，每個夾取後的值通過 `onResize` 回傳。
- `overlay`：`tooltip`、`popover`、`modal`、`drawer` 這類浮層共用的定位與滾動工具。`useOverlayPosition` 在空間不足時把浮層翻到對側並夾在視口內，`lockBodyScroll` 記錄各個持有者，最後一個釋放時恢復宿主的內聯樣式，`OverlayPlacement` 是共用的方位型別。
- `notification`：右上角通知棧，展示任務狀態與結果反饋，見 [Notification](#notification)。

### `auth/`

`components/auth/` 下六個表單共用的部分：帶標題、說明、錯誤提示、提交按鈕和協議確認的 `<form>` 外框（`form-frame.tsx`），帶可選密碼顯隱的輸入項（`fields.tsx`），協議連結與確認彈窗（`agreements.tsx`），管理取值與校驗的 `useForm`，提供本地化文案的 `useAuthLabels`，以及 `auth.css`。

### `dashboard/`

`DashboardState`（載入中、出錯並帶重試按鈕、為空三種狀態塊），以及 `dashboard.css`，其中是 WikiDashboard 與 ExperienceDashboard 共用的狀態塊、頁籤欄和主體樣式。

### 語言

- `locale.ts`：`Locale` 型別（`'en-US' | 'zh-CN'`）、`resolveLocale` 與 `mergeLabels`。顯式的 `labels` 項優先於語言的預設值，`undefined` 繼承預設值，空字串保留為顯式覆蓋。檔案裡沒有業務文案。
- `locale-context.tsx`：`useLocale` 與 `LocaleProvider`，各公開入口共用的語言作用域。它與請求 Client 的 Context 分離，因此切換語言不影響請求和狀態。

譯文放在各自所屬目錄的 `locales/en-US.ts` 與 `locales/zh-CN.ts`；`auth/` 和 `primitives/modal/` 採用同樣的佈局。

### Notification

- `useNotification` 返回例項隔離的操作 API 與上下文佔位，佔位放在呼叫方的語言與主題作用域內。
- API 提供 `loading`、`info`、`success`、`warning`、`error`、`normal`、`remove` 和 `clear`，同一 `id` 原位更新通知，`btn` 提供操作內容。
- `loading` 使用與 Button 共用的內建 `LoadingIcon`，預設持續顯示；其他通知預設 3000 ms 後關閉，`duration: 0` 停用自動關閉，懸停和鍵盤焦點暫停計時。
- 關閉按鈕與自動關閉計時器在開始移除前呼叫 `onDismiss`；移除與清空在退出動畫結束後呼叫各通知的 `onClose`，任務輪詢、取消任務和終態操作由呼叫方負責。
- 僅提供右上角，不提供全域性 API。
- [內部任務演示](../../../../docs/docs/_demos/notification-tasks.tsx) 消費私有文件構建，手動模擬執行、成功和失敗狀態。

## 說明

- Button 與 Input 只複用 Arco 的互動邏輯。視覺規則改編自 `@arco-design/theme-ve-o-aml-design@0.0.36`（MIT），不使用 Arco 預設皮膚，顏色對映到 `src/theme.css` 的 `--ov-ui-color-*`，宿主可以覆蓋。不引入全域性 reset、私有圖示或字型資源。Arco 的宣告見 [`LICENSE.arco-design`](../../LICENSE.arco-design)。
- 文件站通過 `docs/internal-controls.ts` 使用內部控制元件的構建產物（`rslib.config.ts` 中的 `docs-controls` 入口），這些文件專用產物不進入 npm 包。示例裡的 `#demo-controls` 僅供文件站使用，宿主接入時換成自己的控制元件。
- 測試通過 `scripts/test.mjs` 裡的私有構建訪問內部基礎件，不經過包匯出。

開發命令見[前端工作區 README](../../../../README.md)，元件約定見[元件指南](../components/AGENTS.md)。
