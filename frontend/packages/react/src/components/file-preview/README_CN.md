# FilePreview 檔案預覽

[English](README.md) / 中文

可選 `locale: 'zh-CN' | 'en-US'` 覆蓋最近的模組或 Provider；均未配置時預設 `en-US`。已有 `labels` 可逐項覆蓋。業務內容仍由宿主提供。

控制台式檔案頁籤、麵包屑、分級內容、圖片預覽、原始碼與編輯。元件和型別從 `@openviking/react/components/file-preview` 匯入，樣式需顯式匯入 `@openviking/react/components/file-preview/style.css`。

檔案頁籤接收 `source`，可選 `levels`（L0/L1/L2 或宿主自定義標籤）與 `resolveImage(src, source)`，後者用於鑑權或相對路徑 Markdown 圖片。每級提供獨立內容，可覆蓋資源與編輯能力。宿主負責取數與返回 URL 的生命週期。原始圖片使用二進位制 `file` 或可訪問 `url`。動作與許可權標記由宿主插槽提供，頁尾可放更新時間和內容解析說明。

檢視器按需載入，外殼支援 SSR。完整介面和控制台示例見 `frontend/docs/docs/` 中的中英文元件文件。
