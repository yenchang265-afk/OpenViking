# 選擇部署路徑

如果你只需要使用別人提供的服務地址和 API Key，直接[連線 CLI](../getting-started/05-cli-setup.md)或[接入 Agent](../agent-integrations/01-overview.md)。下面的路徑面向服務部署與運維人員。

| 部署目標 | 閱讀順序 | 完成標準 |
| --- | --- | --- |
| 本地體驗 | [快速開始](../getting-started/02-quickstart.md) | 匯入一份文件，檢索並讀取其中的內容 |
| 自建共享服務 | [部署前檢查](19-deployment-checklist.md) → [自建服務](03-deployment.md) → [身份認證](04-authentication.md) → [公網訪問](12-public-access.md) | 驗證持久化、授權訪問、未授權拒絕和首次資料處理 |

## 配置模型與訪問控制

首次設定模型，使用[配置模型與服務](01-configuration.md)；查某個欄位，使用[服務端配置欄位](../configuration/01-server.md)。服務端 `ov.conf` 與客戶端 `ovcli.conf` 的職責不同，客戶端欄位見[客戶端配置](../configuration/02-client.md)。

開放遠端訪問前完成身份認證和反向代理配置。需要 OAuth 的 MCP 客戶端繼續閱讀 [OAuth 2.1](11-oauth.md)。多使用者共享時，理解[多租戶身份](../concepts/11-multi-tenant.md)和 [ACL 繼承](../concepts/15-acl.md)；需要靜態資料加密時，按[加密指南](08-encryption.md)配置。

## 執行後如何檢查

先從[觀測與排障入口](05-observability.md)選擇工具。單次請求看[操作遙測](07-operation-telemetry.md)，時間趨勢看 [Prometheus / Grafana](11-grafana-prometheus.md)，指標含義查[指標口徑](../concepts/12-metrics.md)。常見問題見[FAQ](../faq/faq.md)。

有儲存或效能需求時，再選擇[主備儲存](13-multi-write-storage.md)、[RAGFS 快取](14-ragfs-cache.md)或 [cuVS](16-cuvs.md)。這些是按需配置項，不是首次部署的必經步驟。
