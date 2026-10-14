# 資料組織指引

本指引規定 OpenViking 中 Resource 的目錄組織方式。目錄用於確定可見範圍、檢索範圍和協作邊界。

## 上下文型別

| 型別 | 內容 | 寫入與組織方式 |
| --- | --- | --- |
| Resource | 文件、網站、程式碼倉庫、資料集及編譯後的知識庫 | 通過 `add_resource`、`ov add-resource` 或 `ov compile` 寫入，按本指引組織 |
| Memory | 從互動中提取的偏好、事實、事件和經驗 | 通過 session commit 等記憶抽取流程寫入，由 memory schema 和抽取系統組織 |
| Skill | 可重複執行的方法、約束、指令碼和配套資料 | 通過 `add_skill` 或 `ov add-skill` 安裝 |

本指引的目錄約定僅適用於 Resource。不要在 `memories/` 下套用 Resource 目錄結構。

## 可見範圍

| 位置 | 可見範圍 | 用途 |
| --- | --- | --- |
| `viking://resources/` | 當前 account 共享 | 多個身份共同使用的資料；細粒度許可權由 ACL 控制 |
| `viking://~/resources/` | 當前認證身份私有 | 當前身份獨立使用的資料 |
| `viking://~/peers/<peer>/resources/` | 當前身份下的指定 peer | 與穩定互動物件關聯的資料 |

OpenViking `user` 是經過認證的上下文所有者，可以代表人、Agent、應用或服務身份。`viking://~` 始終指向當前請求身份自己的 user 空間。

`account_id` 已構成團隊共享邊界，無需再增加 `teams/<team>/`。密碼、令牌、私鑰等秘密不得作為普通 Resource 上傳。

## 目錄約定

`projects/<project>/` 是可選的協作容器。僅當專案名稱穩定，且多個身份需要共享、檢索和維護同一批上下文時使用。專案目錄不替代 account 或 ACL 的可見性控制。

其餘分類目錄可以直接位於 Resource 根目錄，也可以位於一個專案目錄下並按需建立，不要求每個空間具備完整分類，只作為一種約定，避免不同的 Agent 由於理解不一致建立出諸如 `doc`, `docs`, `documents` 甚至 `pdfs` 這樣的重複目錄導致資訊溝通不暢。我們在下表約定一些常用的目錄名命名，其完整路徑如 `viking://resources/repos`。

| 目錄 | 內容 | 邊界 |
| --- | --- | --- |
| `repos/` | 完整程式碼倉庫 | 保留倉庫內部結構；不要按程式語言拆分 |
| `docs/` | 手冊、規範、產品文件、Office 文件、論文、預印本及其他文件快照 | 復現程式碼和獨立資料集分別放入 `repos/` 與 `datasets/` |
| `sites/` | 以 URL、域名或 Feed 為來源，並按網頁樹匯入或更新的內容 | 單個離線文件放入 `docs/` |
| `wiki/` | 經歸納、去重、重組並建立導航或連結的知識庫 | 用作 LLM Wiki 等 `ov compile` 任務的穩定輸出；原始來源保留在來源目錄 |
| `datasets/` | 表格、語料、評測集、結構化歸檔、觀測資料及訓練或分析資料 | 點雲、GIS 等觀測資料屬於資料集 |
| `media/` | 供直接觀看或收聽的圖片、音訊和影片成品 | 可編輯原始檔和工程產物放入 `artifacts/` |
| `artifacts/` | 進入編輯、製造、渲染或執行流程的非文件產物 | 包括圖紙、CAD、3D 模型、場景、視覺原始檔、模板和品牌素材 |
| `items/` | 以商品、產品、SKU 或其他業務物件為粒度的實體集合 | 批次表格和訓練資料放入 `datasets/` |
| `people/` | 以人物、客戶、聯絡人或其他身份為粒度的實體集合 | 可見範圍和敏感資訊仍由 user 空間、account 與 ACL 控制 |
| `inbox/` | 當前身份尚未歸類的 Resource | 僅建議位於 `viking://~/resources/`，不作為 account 共享空間的長期分類 |
| `projects/<project>/` | 專案協作上下文 | 可選容器；確有專案需要時，在其下繼續使用本表中的分類目錄 |

`items/` 和 `people/` 是實體集合目錄的示例，不是保留名稱。Agent 可以根據領域使用 `companies/`、`positions/` 或其他明確的複數名詞。此類目錄當前仍是普通 Resource 目錄，用於與後續 Item 檢索能力對齊；當前版本不提供專門的 Item 檢索語義。

時間序列資料（日報、郵件歸檔、定期報告等）在分類目錄下按日期分層即可，不要再為日期新建分類。URI 中可以直接使用服務端路徑變數，例如 `viking://resources/docs/{calendar:ym}/` 會渲染為 `docs/2026/05/`；常用變數包括 `{calendar:today}`、`{calendar:ym}`、`{calendar:yq}`、`{calendar:yw}`，CLI、SDK 和 MCP 原樣傳遞模板，由服務端解析。詳見 [Viking URI 路徑變數](../concepts/04-viking-uri.md#路徑變數)。

目錄名稱不代表格式支援情況。匯入前應檢查[資源管理支援的格式](../api/02-resources.md#資源型別)。`artifacts/` 中尚未支援的檔案應通過已啟用的物件儲存 Connector 儲存，或等待相應的原始檔案儲存與解析能力。

## 新增和更新引數說明

1. 一個邏輯來源只保留一個穩定根目錄，新增前可使用 `list(ls)` 或 `stat` 檢查目標是否存在。
2. 新增來源使用建議使用 `parent` 指定其父目錄位置，同步固定來源或希望直接指定目標目錄則使用精確的 `to`，一般建議用 `parent`。
3. 預期父目錄不存在時，CLI 使用 `--parent-auto-create`，SDK 和 API 使用 `create_parent=true`；MCP 的 `parent` 會自動建立目錄。
4. 可重複讀取且會變化的遠端來源使用 watch 機制，避免手動重複匯入副本。
5. `reason` 應說明資源新增意圖和用途，`tags` 僅在請求或系統規範明確要求時新增。
6. 匯入完成後返回最終 URI、可見範圍和任務狀態；處理完成後再檢索。

Account 管理者可以通過 `user_config_defaults.add_targets.resource_uri` 設定預設新增目錄；身份級 `add_targets.resource_uri` 可以覆蓋該預設值。顯式傳入的 `to` 或 `parent` 始終優先。

## Agent 歸檔規則

1. 先區分 Resource、Memory 和 Skill。
2. 沿用目標空間已有的目錄規範；存在 `RESOURCE_POLICY.md` 時優先遵循。
3. 有明確協作專案時使用 `projects/<project>/`，否則按來源或形態歸檔。
4. 無法確定可見範圍時，寫入當前身份的 `viking://~/resources/inbox/`，並返回最終位置。
5. 實體集合目錄按領域命名，不建立無依據的實體分類。
6. 目標已有同一邏輯來源，或共享範圍無法確定時，先確認再寫入。
