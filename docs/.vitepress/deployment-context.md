# 官網部署內容上下文

更新日期：2026-09-22。範圍：官網內容、雙語導航與閱讀入口；不修改部署工具或環境。

## 內容目標

讓讀者完成：選擇服務方式 → 準備環境 → 配置與預覽 → 部署與驗收 → 維護與排障。

託管服務、開源自建、Viking 私有交付分別說明。官網保留決策條件、操作主線、失敗分支和驗收標準；完整 CLI 引數、依賴初始化 SQL、授權操作細節繼續指向對應隨包手冊。無需複製所有附件或增加與部署無關的產品頁。

## 來源與證據範圍

- 輸入包：`viking-deploy-v0.3.0-20260922-87c30111.zip`，27,641,644 bytes。
- SHA-256：`11720a376d17d2a6d305854b6dc68b6e4e3d92851a94255298041fb3d1a80075`。這是本地下載記錄，不是釋出方簽名證明。
- ZIP CRC 檢查通過。靜態讀取包內手冊；未執行 ovadmin、未接入叢集、未執行部署與 smoke。
- 下載連結帶簽名，只用於取得輸入，不寫入站點、示例、日誌附件或 llms.txt。
- `NOTICE.md` 將該包限定為授權測試材料，無生產、商用、對外服務或再分發授權。手冊裡的生產建議不覆蓋此限制。本站內容以本地待審稿交付，公開發布前由內容負責人按實際授權範圍確定可公開的內容；不分發原始手冊、二進位制或物料清單。

| 官網主題 | 隨包依據 | 應保留的限制 |
| --- | --- | --- |
| 環境、資源、依賴 | `Viking部署手冊.md` §1–5；`版本相容性說明.md`；`基礎元件配置要求.md` | 私有組合的規劃參考不等於開源最低配置，不承諾容量或 HA |
| 安裝主線 | `install.md`；`Viking部署手冊.md` §6；`ovadmin使用手冊.md` | VikingDB Ready 後部署 OpenViking；Operator 與 workspace 分開建立 |
| 授權首次啟動 | `install.md`；部署手冊 §6.4–6.5 | CRD、CR 與首次狀態同步在匯入前；不提供啟用材料 |
| 模型與模板 | `Viking模型要求.md` §3、6 | CR 覆蓋向量庫維度，不覆蓋 embedding 維度；修改源模板 |
| 驗收 | 部署手冊 §7–8；升級說明 §2.5 | 當前 generation Ready、License Active（如啟用）、doctor、各產品 P0 分別驗證 |
| 升級和排障 | `Viking升級說明.md`；ovadmin 手冊 §3.9–4 | 配置備份不等於資料備份；回滾不可僅降映象；失敗先觀測 |
| 開源 Helm 入口 | 倉庫 `deploy/helm/README.md` | 使用 `deploy/helm/openviking`、`config.*` 欄位與 root key；區別於私有 Operator |

版本衝突處理：部署手冊把 Kubernetes 1.24+ 寫為建議，版本相容矩陣寫為最低值。官網標明“相容矩陣宣告”，未補造最大版本。包版本 v0.3.0 不代表 runtime 版本。命令示例使用交付清單佔位值，不沿用手冊中的舊 runtime tag。

## 資訊組織參考

- [MongoDB Ops Manager installation checklist](https://www.mongodb.com/docs/ops-manager/current/core/installation-checklist/)：部署前先確定拓撲、安全和備份，區分測試安裝與正式執行。
- [GitLab installation](https://docs.gitlab.com/install/)：按 requirements、installation methods、offline、post-install、upgrade 組織任務入口。
- [GitLab requirements](https://docs.gitlab.com/install/requirements/)：說明資源要求與工作負載的關係。

只借鑑任務路徑，不引入 MongoDB / GitLab 的元件要求或容量數字作為 Viking 的結論。

## 站點適配位置

- `docs/{zh,en}/guides/19-deployment-checklist.md`：方式選擇、條件與環境清單。
- `docs/{zh,en}/guides/20-private-deployment.md`：版本範圍、物料、配置、安裝、客戶端與驗收。
- `docs/{zh,en}/guides/21-private-operations.md`：配置生命週期、升級、回滾準備、故障表。
- `docs/{zh,en}/guides/03-deployment.md`：保留既有開源安裝內容，增加新入口並修正 Helm 路徑。
- `docs/.vitepress/docs-navigation.ts`：在“配置與部署”下、服務端部署之後增加“企業私有化部署”子欄目，依次放置部署前檢查、安裝與驗收、升級與排障。
- `docs/.vitepress/theme/components/DocsHome.vue`：在既有“部署與運維”條目中增加“企業私有化部署”連結。
- 目錄與搜尋繼續使用既有 Markdown 掃描機制；不再維護第二套頁面清單。本檔案置於 `.vitepress`，不進入網站正文和 llms.txt。

## 驗證記錄

改動前 `check:docs` 已報告 `zh/qa/harness-qa-plan.md` 缺少英文對應頁。該檔案是工作區已有內容，不納入本次修復；驗收應比較新增錯誤，不能刪減檢查來獲得全綠。

本次驗證結果：

- `npm run docs:build` 通過；構建仍有既有 promql / caddyfile 高亮回退提示。
- 文件一致性檢查覆蓋 100 篇英文、101 篇中文、1,104 個本地連結；僅保留改動前已有的 QA 頁面英文缺失，無新增錯誤。
- 六個新頁面進入生成 HTML、`llms.txt`、`docs-search-index.json`；本 context 與本次簽名下載地址未進入公開文本產物。
- ego-browser 實測英文首頁 → checklist → private deployment → operations；中文切換、首頁入口、清單與安裝頁跳轉通過。
- 首頁“私有交付”篩選返回兩個對應頁面；全站關鍵詞查詢在遠端不可用後回退本地，返回安裝、運維、清單與服務端部署頁。未驗證遠端檢索；釋出流程需同步並驗收遠端索引。
- 桌面頁面與 390px 手機首頁無整頁橫向溢位，截圖檢查通過。
- 未執行部署命令、叢集驗收、提交或線上釋出。頁面中的命令為隨包手冊靜態核對結果。


## 閱讀與導航調整（2026-09-22）

按使用者要求，正文移除測試包適用範圍、NOTICE 和測試用途宣告；來源版本及其使用限制只作為本 context 的資料記錄保留。正文保留影響實際操作的版本相容、License 啟用、容量與資料恢復約束，不由刪除提示推導新的生產能力承諾。

企業私有化部署頁標題後提供“聯絡我們獲取部署物料”按鈕。中文跳轉 README_CN.md 的商業版本錨點，英文跳轉倉庫首頁的 commercial-editions 錨點；複用 VitePress VPButton，在正文中保留段落間距並去掉連結下劃線；不傳送聯絡訊息。

調整驗證：構建通過；瀏覽器確認“企業私有化部署”為配置與部署下的可摺疊子欄目，包含三篇頁面。中英文 CTA 的實際 href 與使用者指定地址一致，適用範圍提示已移除。桌面與手機視口檢查通過。文件一致性檢查仍僅報告原有 QA 頁面缺少英文版本。

欄目命名：統一使用 `Enterprise Deployment / 企業私有化部署`，覆蓋側欄、首頁入口、頁面標題與交叉引用；保留現有 URL。

恢復記錄（2026-09-24）：本次內容曾於 2026-09-22 在工作區完成但未提交，後被 `git clean` 清除；現依據當時的編輯記錄在 main 上重放，並把側欄改動從 `config.ts` 遷到已合入的 `docs-navigation.ts`。
