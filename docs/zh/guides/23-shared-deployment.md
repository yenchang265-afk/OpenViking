# 共用狀態與多副本部署

當伺服器 Pod 必須能隨時替換時，將 `server.deployment_mode` 設為 `shared`。
預設仍為 standalone 模式，支援本機儲存。請使用包含共用後端實作的版本；
只修改舊映像的設定，不會為它增加這些功能。

| 狀態來源 | 共用後端 |
|---|---|
| 內容、會話、暫存來源、上傳會話、執行期帳戶／叢集設定 | 經由 AGFS 使用 S3；分層儲存使用 MySQL + S3 |
| Git 版本物件與參照（啟用時） | 共用 S3 或 AGFS Git 後端 |
| 向量 | Elasticsearch、openGauss 或遠端向量 HTTP 服務 |
| 佇列、路徑鎖、一致的檔案系統快取 | Redis |
| 帳戶身分與 API 金鑰 | MySQL |
| Task 與 Work 記錄 | MySQL |
| OAuth 註冊、待授權請求、授權碼與權杖 | MySQL |
| 用量投影與請求稽核歷史 | MySQL |
| 一次性 MCP 上傳／下載憑證 | Redis |

所有副本必須使用相同的 `service_name`、後端命名空間、S3 儲存桶與前綴、向量集合、
模型設定、憑證及加密根金鑰。不同部署需使用不同命名空間。Redis 必須保留佇列、鎖與
傳輸狀態：請啟用持久化，並使用不逐出資料的策略。傳輸權杖需要 Redis 6.2 以上版本
（`GETDEL`）。建立 Python 環境時，請安裝現有的 `mysql` 與 `expiry` extras。

檔案系統快取必須使用 `backend: cache` 與 `multi_instance: true`，
且 `cache.params.default_ttl_seconds` 必須為正數。請以
`storage.agfs.s3.cache_enabled: false` 停用 S3 外掛的程序內中繼資料快取。
共用模式會在提供服務前驗證這些設定，也會拒絕內嵌 gateway／bot、本機狀態來源及
多重寫入備份。請將 gateway 作為獨立服務執行，並使用它支援的共用儲存設定。

QueueFS 必須使用 `mode: shared`。`recover_stale_sec` 必須為正數，並大於允許的
最長工作時間；範例使用一天。standalone 預設值為零，啟動時會回收所有處理中訊息；
共用模式拒絕此值，因為其他副本可能仍在執行工作。因此 worker 當機後的回收可能延遲
到這個門檻。部署前，請以實際匯入資料大小驗證回收時間。

第一版共用模式不支援資源監看。請設定 `enable_watch_scheduler: false`：
不載入監看登錄，也不執行更新迴圈。帶有監看選項的請求會在匯入前被拒絕；
監看管理端點會回報排程器不可用。既有監看定義仍保留，供 standalone 模式使用，
但不會在共用模式執行。單次匯入仍可使用。

Worker 可以保留工作暫存檔、下載輸入、連線及衍生的記憶體快取。
後續請求不應依賴先前請求所在的 Pod。上傳必須使用共用模式，明確指定本機上傳會被拒絕。
傳輸憑證綁定原始身分、OAuth 來源、對端範圍、權限與操作。
上傳與下載憑證使用不同命名空間，且以原子操作消耗，即使請求送到不同 worker 也一樣。

共用模式的工作串流會定期傳送 `resync` 事件。用戶端在 `ready` 與 `resync` 時
重新讀取已授權的工作清單，即可看到其他 Pod 完成的工作。`ready.complete` 為 false：
本機 `task` 訊框不是完整的叢集變更日誌。不依賴 Redis 通知的送達保證；
MySQL 仍是工作的權威資料來源。

## 佈建與部署

[共用 Helm values](https://github.com/yenchang265-afk/OpenViking/blob/main/examples/k8s-helm/shared-values.yaml) 是兩副本部署的覆寫範例，
使用可丟棄的 `emptyDir` 工作區。請填入服務位址、TLS 設定、模型憑證及引用的
Kubernetes Secret。啟動設定必須由外部管理，並在所有副本保持一致。
共用模式的啟動設定編輯器為唯讀；執行期帳戶／叢集設定仍使用共用 AGFS 文件。

在 `connections.mysql` 設定一次 host、port、database、user、password 及選用的 `ssl`。
所有已選用的 MySQL 後端（含分層 AGFS）會自動繼承連線，不需要連線名稱或額外 DSN
環境變數。後端仍須明確選用；定義連線不會啟用子系統。連線池大小、資料表與保留策略
仍放在各子系統設定中。

其他共用服務設定於 `connections.redis`、`connections.s3` 與
`connections.elasticsearch`。Redis 端點、拓樸與驗證設定提供給 `cache.params`；
TTL 與連線池設定仍留在 `cache.params`。S3 端點、儲存桶、區域與憑證提供給已選用的
AGFS／Git S3 後端；前綴與快取策略仍由各子系統設定。Elasticsearch 主機、驗證及 TLS
提供給已選用的向量後端；索引與請求策略仍由向量設定管理。

儲存選擇器統一使用 `backend`，包含快取、路徑鎖、工作／帳戶儲存與傳輸權杖。
舊的 `provider` 名稱仍可使用，但與 `backend` 同時指定且值不同時會被拒絕。
LLM 的 `provider` 仍用來選擇模型供應商。完整的行內連線仍可作為獨立覆寫。
有中央連線時，不接受部分連線覆寫：Redis 必須提供 `endpoints`；S3 必須提供
endpoint、region、bucket、access_key、secret_key；Elasticsearch 必須提供 `hosts`。
中央連線與行內連線的憑證不會混用。

分層儲存使用中央連線時，必須搭配重新建置的原生擴充。
啟動時會拒絕舊 binding，避免它默默改用舊 DSN 環境變數。

MySQL 的完整舊式行內連線仍可獨立覆寫。存在中央預設值時，部分
host／user／password／database／TLS 覆寫會被拒絕，以避免憑證混用。
分層儲存仍可使用舊的 `mysql.dsn_env`；明確指定時，它會覆寫該掛載的中央連線。
每個副本的憑證與 TLS 設定必須相同。`ssl: true` 會在 Python 與原生儲存中驗證
憑證及主機名稱。自訂 CA／用戶端憑證可使用
`ssl: {"ca": "/path/ca.pem", "cert": "/path/client.pem", "key": "/path/client.key"}`。

範例啟用依大小分層的 AGFS：小於 1 MiB 的檔案及路徑索引存於 MySQL，較大檔案存於 S3。
Git 也預設使用分層 AGFS 後端。分層 AGFS 第一次掛載時會建立索引表。
資料表名稱為選填，預設為 `agfs_entries`，Git 則為 `agfs_git_entries`；
需要隔離命名空間時才設定自訂表名。若已有未分層的儲存桶，請先停止未分層的寫入端，
並在啟動副本前依照[分層儲存遷移說明](01-configuration.md)操作。
範例的 `import_existing` 保持 false。

請透過資料庫遷移系統佈建帳戶與工作資料表，使用下列檔案及適用的變更：

- `openviking/server/account_stores/sql/init.sql`；
- `openviking/service/sql/task_store_init.sql`。

OAuth 與用量／稽核資料表必須使用伺服器將載入的設定來佈建。先檢查 DDL，再明確套用：

```sh
python -m openviking.server.shared_schema --config ov.conf
python -m openviking.server.shared_schema --config ov.conf --apply
```

這只會建立缺少的資料表，不會刪除、重設或遷移既有資料。伺服器啟動時會檢查 schema，
但不會建立它。帳戶、工作、OAuth 與稽核儲存可以分別設定不同的資料庫使用者。

```sh
helm upgrade --install openviking ./deploy/helm/openviking \
  -f examples/k8s-helm/shared-values.yaml --set image.tag=<compatible-build>
```

共用模式使用 RollingUpdate，拒絕共用工作區 PVC，並允許多副本。
standalone 模式維持 Recreate 與單副本限制。請集中收集日誌與指標；
計數器及開啟中的串流仍屬於各程序。

## 轉換既有安裝

切換後端**不會**遷移資料。切換前請完成：

1. 備份目前工作區與所有外部儲存。停止新的修改，排空舊佇列，再停止所有寫入端。
2. 將持久化 AGFS 資料複製到選定的共用命名空間，並重建或遷移向量索引。
   保留 embedding 維度及集合設定。
3. 將帳戶身分與金鑰遷移到關聯式帳戶儲存，保留識別碼與金鑰語意。
   重新開放流量前驗證既有憑證；若需保留 Task 歷史，必須另行遷移記錄。
4. 既有 SQLite OAuth 授權不會自動匯入。請明確遷移，或要求用戶端重新註冊與授權。
   保留 SQLite 資料庫以供回復。稽核歷史也會留在原儲存，除非明確匯入。
5. 先以共用設定啟動一台伺服器，驗證身分與資料後再加入第二個副本。
   輪流將請求送到不同 Pod，涵蓋上傳／消耗憑證、OAuth 授權碼交換、會話修改、工作查詢及金鑰撤銷。
6. 正式使用前，驗證匯入與會話提交期間終止 worker 後，已接受的工作能恢復且不產生重複副作用。

回復必須考慮切換後已接受的寫入。直接回到舊工作區快照會遺失這些寫入；
請先停止寫入端，再將資料遷回，或一起還原**所有**權威儲存的一致備份。

共用儲存測試位於 `tests/server/test_shared_transfer_tokens.py` 與
`tests/server/test_shared_mysql_state.py`。MySQL 測試需要隔離的 `ov_stateless_test`
資料庫及明確的 `OV_TEST_MYSQL_PORT`，涵蓋獨立連線、一次性消耗競爭、重放墓碑、
跨 Pod 可見性、並行用量累加及與 standalone SQLite reader 的一致性。
