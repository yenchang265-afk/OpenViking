# 主備儲存

V2 多寫以一個 primary backend 作為業務真相，並把檔案複製到配置的 backup。

## 讀寫模型

- 所有直接讀取只訪問 primary。backup 不參與業務讀取。
- primary 變更成功後立即返回。
- metadata 持久化和 backup 應用在後臺非同步執行。
- backup 落後不會改變 primary 已返回的結果。
- 多寫 metadata 只儲存在 primary。

該模型是最終一致。程序可能在 primary 成功和事件持久化之間崩潰，導致該次
複製事件丟失。發生此情況後，需要從 primary 重建受影響的 backup。

## Metadata 模型

每個 account 使用固定數量的 metadata partition。事件路由到一個 partition，
追加到 segment log，再由每個 backup 獨立消費。Checkpoint 壓縮舊歷史，GC
清理不再需要的 metadata。

`initial_partitions` 僅在 account metadata 首次建立時決定 partition 數量。
已有 account 始終使用持久化的 partition 數量和 routes，修改配置不會改變
現有佈局。本期不支援擴容或縮容。

## 首次啟用匯入

`.multiwrite.json` 不存在時，啟動流程建立 `V2/migrating` 狀態，先啟用前臺
V2 事件提交，再在後臺匯入 primary 當前檔案。匯入成功後切換為 `stable`。
匯入不會刪除 backup 中多餘的舊檔案。

舊多寫協議和舊遷移欄位直接拒絕，不執行轉換或解釋。

## 運維

V2 不提供同步狀態或手工重試 API 和 CLI 命令。請使用多寫 Prometheus 指標
觀察佇列深度、worker 失敗、backup lag、協議版本和協議狀態。

## 相關文件

- [儲存架構](./05-storage.md)
- [指標](./12-metrics.md)
- [配置指南](../guides/01-configuration.md)
- [多寫儲存指南](../guides/13-multi-write-storage.md)
- [OVPack 匯入匯出](../guides/09-ovpack.md)
