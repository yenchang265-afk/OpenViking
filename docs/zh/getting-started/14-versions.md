# 版本管理

在獨立演示目錄中儲存兩個版本、檢視差異，並將檔案恢復為第一版。連線準備見 [CLI 入門](05-cli-setup.md)，模型和索引處理會沿用服務端配置。

## 儲存第一版

```bash
ov mkdir viking://resources/onboarding-versions-v1
ov write viking://resources/onboarding-versions-v1/plan.md --mode create --content "反饋每週五匯出。" --wait
ov snapshot commit -m "onboarding v1" --paths viking://resources/onboarding-versions-v1 -o json
```

記錄返回的 `commit_oid` 為 `<v1>`。本頁只操作該演示目錄；重複體驗時可以換一個新目錄名。快照由 `snapshot commit` 顯式儲存，`session commit` 用於會話歸檔與記憶提取。

## 修改並比較

```bash
ov write viking://resources/onboarding-versions-v1/plan.md --content "反饋每週一匯出。" --wait
ov snapshot commit -m "onboarding v2" --paths viking://resources/onboarding-versions-v1 -o json
```

記錄第二個 `commit_oid` 為 `<v2>`，將下面的佔位符替換為實際 ID：

```bash
ov snapshot show <v1> --path viking://resources/onboarding-versions-v1/plan.md
ov snapshot diff viking://resources/onboarding-versions-v1/plan.md --from <v1> --to <v2>
```

舊版應為“每週五”，差異應顯示改為“每週一”。

## 預覽並恢復

```bash
ov snapshot restore <v1> viking://resources/onboarding-versions-v1 --dry-run -o json
```

核對計劃中的新增、修改和刪除範圍，確認都屬於本次演示目錄。恢復會將範圍內的差異寫回工作區；有需要保留的新修改時，先另行儲存。確認計劃後執行：

```bash
ov snapshot restore <v1> viking://resources/onboarding-versions-v1 -m "restore onboarding v1" -o json
ov read viking://resources/onboarding-versions-v1/plan.md
ov snapshot log --paths viking://resources/onboarding-versions-v1 -o json
```

正文應恢復為“每週五”，歷史中可看到恢復產生的新提交。`applied` 表示已應用，`noop` 表示選定原始檔樹與當前 HEAD 相同；可結合正文讀取核對工作區狀態。

## 檢查檢索狀態

恢復會按需要安排語義和向量重建。將恢復結果中的 `task_id` 填入下方命令，任務完成後驗證檢索：

```bash
ov task status <task_id>
ov find "反饋什麼時候匯出？" --uri viking://resources/onboarding-versions-v1
```

如果相關處理尚未完成，繼續查詢對應任務，完成後再驗證。先以 2 分鐘為觀察視窗，保留仍在執行的任務 ID 供稍後檢視。

快照儲存選定範圍內的原始檔樹，許可權使用當前 ACL，向量索引按恢復後的內容重建。帳號排除規則與系統剪枝會影響儲存範圍，詳見[版本參考](../api/11-snapshot.md)和[快照指南](../guides/15-snapshot.md)。演示目錄可在 Studio 中確認後清理；歷史保留規則見快照指南。
