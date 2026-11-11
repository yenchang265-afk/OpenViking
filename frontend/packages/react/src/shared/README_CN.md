# 內部共享程式碼

[English](README.md) / 中文

供本包元件複用的內部程式碼，**沒有公開入口**。這裡的內容不出現在包根入口、子路徑或 `package.json` 的 `exports` 中——宿主無法匯入，也不承擔相容性承諾。

只有出現第二個真實消費者時才提升到這裡；單個元件用到的東西留在該元件目錄內。

內部 `components/drawer` 是已明確確認的目錄例外：它作為通用右側抽屜保留在這裡，目前唯一直接消費者是 `FileBrowserEntries`。其他內部程式碼仍遵循第二個真實消費者的門檻，詳見 [Frontend Agent Guide](../../../../AGENTS.md)。

這裡的樣式由使用它的元件自己的樣式表引入，而不是 `components/style.css`：沒有公開入口指向本目錄，用它的元件負責按需引入。

## 內容

- `components/drawer`：提供過渡動畫、焦點鎖與滾動鎖的右側抽屜。通過 `children` 接收內容，由 `file-browser-entries` 提供業務內容與專屬樣式。
- `components/tooltip`：渲染到 `document.body` 的定位浮層，被 `file-preview` 用於複製路徑提示與摺疊層級選單。它存在的理由是祖先容器的 `overflow: hidden` 會裁掉常規浮層。
- `components/popover`：白底卡片的浮層，同樣 portal 到 `document.body`，被檔案樹的節點資訊與檔案預覽使用。
- `components/divider`：一條分隔線，尺寸與顏色由呼叫方內聯給出。
- `components/resizable`：可拖拽的分隔條 `ResizableHandle`，用指標捕獲處理拖動、支援方向鍵改寬，寬度由呼叫方受控持有。`file-browser` 用它調整目錄樹寬度。

## 邊界

共享程式碼不得依賴 `components/`、`modules/` 或任何宿主契約——依賴方向是單向的，從公開元件指向本目錄。需要業務資料、路由或宿主服務的能力屬於 `modules/`。

開發與構建入口見 [UI workspace README](../../../../README.md)，元件約定見[元件指南](../components/AGENTS.md)。
