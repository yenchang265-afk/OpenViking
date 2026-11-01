# 部署模式

<a id="使用方式"></a>

你可以自行執行 OpenViking，連線火山引擎託管服務，或申請企業私有化交付。選擇時先看資料放在哪裡、誰負責執行和需要怎樣的支援。

已有服務地址與 API Key 的使用者無需重新部署，直接進入 [CLI 入門](05-cli-setup.md)。想在本機跑一次完整問答，按[快速開始](02-quickstart.md)操作。

## 選擇一條路徑

| 方式 | 資料與執行環境 | 運維與支援 | 需要準備 |
| --- | --- | --- | --- |
| **開源自建** | 自己的本機、伺服器或雲環境，儲存由自己配置 | 自行部署、升級、備份與配置訪問控制；通過開源社群獲取幫助 | 執行環境、模型訪問憑據和儲存 |
| **雲服務** | 火山引擎託管的服務環境，區域與資料使用條件以服務說明為準 | 服務方執行基礎設施；使用者管理自己的接入、資料與授權 | 開通服務，獲取連線資訊和 API Key |
| **企業部署** | 按交付方案部署到自己的雲帳號、VPC 或離線環境 | 運維分工、技術支援及驗收範圍按實際交付約定 | 申請部署物料與 License，完成環境檢查 |

“開源/商業”描述軟體與支援方式，“自建/託管”描述部署責任。開源自建也可用於團隊環境，選擇時可以結合訪問控制需求、部署條件和支援方式綜合考慮。各版本的具體能力與限制見相應版本和服務說明。

## 開源自建

適合需要控制環境、自己除錯或接入應用的使用者。開源伺服器採用 AGPLv3；本機體驗不需要企業部署物料。按照[快速開始](02-quickstart.md)準備模型、啟動服務和 VikingBot，再匯入樣例問答。

團隊共享前，需要完善身份認證、持久化、備份和運維。Docker、開源 Helm 等路徑見[服務端部署](../guides/03-deployment.md)；許可文本見 [LICENSE](https://github.com/volcengine/OpenViking/blob/main/LICENSE)。

## 雲服務

火山引擎的 OpenViking Context 是基於開源 OpenViking 核心的託管服務。開通後，在 [OpenViking 控制台](https://console.volcengine.com/vikingdb/openviking/region:openviking+cn-beijing)獲取 API Key，在 `ov config` 中選擇 **OpenViking Service** 並儲存連線，無需在本機啟動資料服務。

套餐、額度、可用區域與支援範圍見[官方服務說明](https://docs.volcengine.com/docs/84313/2374478)。VikingBot 和 Compile Runtime 的可用性取決於所選服務的配置；如需使用，可以向服務提供方瞭解支援情況。資料服務也支援通過自己的 Agent 接入。

## 企業部署

適合需要私有化交付、部署物料和官方支援的團隊。通過[官方諮詢入口](https://my.feishu.cn/share/base/form/shrcnMFqymCd9sq77sLk34Krxoc)確認方案，按實際交付要求申請物料與 License。

當前[企業部署指南](../guides/20-private-deployment.md)使用 Kubernetes 環境中的 VikingDB 和 OpenViking。準備部署物料時，可以按照[部署前檢查](../guides/19-deployment-checklist.md)一併準備映象、儲存和依賴環境。

## 選好之後

取得 URL 和資料訪問憑據後，進入 [CLI 入門](05-cli-setup.md)。如果想先驗證完整本地體驗，使用[快速開始](02-quickstart.md)。

依據：[專案商業版本說明](https://github.com/volcengine/OpenViking/blob/main/docs/repository/README_CN.md#商業版本)、[雲服務產品介紹](https://docs.volcengine.com/docs/84313/2374478)、[企業部署指南](../guides/20-private-deployment.md)。核對日期：2026-10-27。
