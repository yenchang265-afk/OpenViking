# 跨模組 Hook

[English](README.md) / 中文

預留多個模組實際共用的 Hook，按真實複用需求增加實現。
公共 Hook 有實際實現後再從 `@openviking/react/hooks` 開放，不提供 CSS。業務模組專屬的公開 Hook 留在 `modules/<模組>/`，從對應模組入口匯出，供組合檢視和宿主獨立複用，不提升到本目錄。私有 Hook 留在各模組內；元件使用的 Hook 同樣遵守檢視層邊界，資料獲取和業務編排由模組 Hook 或宿主負責。
當前僅提供目錄說明，沒有 Hook 實現或公開入口。

開發與構建入口見 [UI workspace README](../../../../README.md)，模組約定見[包說明](../../README.md)。
