# 內部 Hook

Hook 是元件或模組的內部實現，放在對應目錄內。實際跨元件複用的 Hook 放在 `src/shared/`。當前不提供 `@openviking/react/hooks` 或業務無頭 Hook 公開入口。

取數 Hook 僅位於模組內；元件私有 Hook 只管理本地 UI 互動，不感知介面。
