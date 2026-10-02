---
name: sales-opportunity-order-builder
description: 銷售商機商單 Builder。幫助銷售初始化個人銷售知識庫與商機商單跟進工作流：檢查 AgentPlan APIKey、建立個人版 Business Data Platform 庫並取得庫的 Business Data Platform APIKey，再引導上傳銷售文件、查詢商機商單、定時沉澱 session 記憶。使用者提到銷售商機、商單、客戶跟進、銷售知識庫、OV/OpenViking 庫搭建、銷售文件上傳、商機復盤、銷售記憶沉澱，甚至只是說"幫我建個跟進客戶的庫"時，都應優先使用本 skill。
---

# 銷售商機商單 Builder

幫助銷售快速搭建個人銷售知識庫與商機商單跟進工作流。先完成環境初始化
（AgentPlan APIKey → 建立 OV 庫 → 取得庫憑據），再進入三類業務場景
（上傳資料 / 查詢商機 / session 沉澱）。

這是一個 **Builder**：優先幫使用者把環境搭好、把工作流跑通，而不是直接跳到商機
問答。某項依賴缺失時，給出明確的下一步並暫停依賴它的後續操作，不要偽造結果。

## 關鍵概念：兩套系統、兩個 APIKey

Business Data Platform 相關操作分屬**兩個不同的面**，各用各的 Key，混用是本 skill 最常見的
故障來源：

| | 控制面（管庫） | 資料面（管資料） |
|---|---|---|
| 做什麼 | 建立/查詢/刪除 OV 庫，獲取庫的憑據 | 向庫裡上傳文件、檢索、寫記憶 |
| 用什麼工具 | Business Data Platform **控制面** MCP（`mcp-server-openviking-controlplane`，工具：`list_collections` / `create_collection` / `get_collection` / `get_usage` / `get_collection_api_key`），或同包 CLI `ov-cp` | Business Data Platform **資料面** MCP / `ov` CLI（add_resource / search / remember 等） |
| 用哪個 Key | **AgentPlan APIKey**（環境變數 `AGENTPLAN_API_KEY`，Bearer） | **Business Data Platform APIKey**（每個庫一把，建立後單獨獲取） |

兩個 Key 的邊界：

- **AgentPlan APIKey**：新建 OV 庫、聯網、資料集查詢。拿它讀寫庫資料會失敗。
- **Business Data Platform APIKey**：讀寫某一個 OV 庫的資料。拿它建庫會失敗。

如果發現讀寫庫資料時用的是 AgentPlan APIKey（或反過來），立即停止並糾正。

## 總體原則

- 按順序完成前置檢查：AgentPlan APIKey → 控制面能力 → 建立/選擇 OV 庫 →
  獲取並記錄庫的 Business Data Platform APIKey 與 user 身份。
- 不在對話中展示、複述、記錄 APIKey、Token、Cookie 等敏感憑據明文；配置憑據
  優先走環境變數或配置檔案，不要求使用者把 Key 貼上進聊天。
- **建庫是計費動作**，且每帳號最多 20 個庫：建立前必須向用戶確認。
- 預設建立**個人版**庫，除非使用者明確要求團隊版。
- 示例中避免真實客戶名，統一用"某客戶 / 某商機 / 某專案"等泛化表達。

## Step 1：檢查 AgentPlan APIKey

1. 檢查環境（如 `AGENTPLAN_API_KEY` 環境變數、已安全記錄的憑據、會話安全上下文）
   中是否已有 AgentPlan APIKey。只判斷"是否存在/是否可用"，不要輸出明文。
2. 有 Key 時，用一次**只讀**控制面呼叫驗證可用性（`list_collections` 或
   `ov-cp list`）——只讀操作不消耗 AgentPlan 額度。
3. 沒有 Key 時，引導使用者去方舟控制台購買 AgentPlan 並新建 APIKey：
   https://console.volcengine.com/ark/region:cn-beijing/subscription/agent-plan?projectName=default
   然後暫停建庫及之後的流程，等使用者配置好再繼續。
4. 注意：即使有了 AgentPlan APIKey，**建庫還要求帳號已開通 AgentPlan 抵扣**。
   如果後面 create 返回 `ProductUnordered`（"尚未在 Business Data Platform 開通 AgentPlan
   抵扣"），說明使用者買了 Key 但沒開通抵扣，引導回同一控制台頁面完成開通，
   不要重試 create。

## Step 2：確認控制面能力（必要時徵求安裝同意）

建立 OV 庫需要**控制面** MCP 或 `ov-cp` CLI。先檢測當前環境是否已具備
（MCP 工具列表裡有沒有 `create_collection`，或 `ov-cp --help` 能否執行）。

如果不具備，**不要默默安裝**——明確詢問使用者，說清兩種方式讓使用者選。
包釋出在 PyPI（`mcp-server-openviking-controlplane`，MCP server 和 `ov-cp`
CLI 在同一個包裡），境內網路給 uv 配 PyPI 映象即可，不依賴 GitHub：

1. **一次性使用（推薦先試這個）**：不落任何持久配置，用 `uvx` 臨時拉起 CLI：

   ```bash
   # 境內網路可加：export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
   AGENTPLAN_API_KEY=<已配置的key> uvx --from mcp-server-openviking-controlplane ov-cp list
   ```

2. **安裝為 MCP（適合長期使用）**：向用戶展示將寫入 `.mcp.json` 的內容，
   經確認後再寫：

   ```json
   {
     "mcpServers": {
       "openviking-controlplane": {
         "command": "uvx",
         "args": ["mcp-server-openviking-controlplane"],
         "env": { "AGENTPLAN_API_KEY": "${AGENTPLAN_API_KEY}" }
       }
     }
   }
   ```

需要徵求同意的原因：安裝會改動使用者的 MCP 配置、引入外部程式碼，且隨後的建庫
動作計費。使用者拒絕安裝時，說明沒有控制面能力就無法自動建庫，但仍可引導使用者
在控制台手工建庫後回來繼續（見 Step 3 的控制台路徑）。

> 備選安裝源：`uvx --from 'git+https://github.com/volcengine/mcp-server#subdirectory=server/mcp_server_openviking_controlplane' ov-cp`
> （需要能訪問 GitHub）。兩條路都失敗時，走控制台手工建庫路徑。

## Step 3：建立個人版 Business Data Platform 庫

1. 詢問庫名（不要自行編造）。庫名建議用**英文/下劃線**（如
   `sales_opportunity_kb`），中文名可能不被接受；可另記一箇中文別名用於展示。
2. 建庫前向用戶確認：這是計費動作，且每帳號最多 20 個庫。
3. 使用者確認後呼叫 `create_collection`（或 `ov-cp create --name <庫名>`）。
   個人版走預設引數即可，模型配置會自動回落到 AgentPlan。
4. 建立返回 `ResourceID`（形如 `ov-xxxxxxxx`），**此時庫還沒就緒，返回結果裡
   也沒有 Business Data Platform APIKey**——這是正常的，進入 Step 4。

## Step 4：等庫就緒，獲取並記錄 Business Data Platform APIKey 與 user 身份

庫建立後處於 `INIT` 狀態，需要輪詢到 `READY` 才能取憑據（INIT 階段取
api-key 會超時，不是故障，等一會重試即可）：

1. 用 `get_collection`（或 `ov-cp get <ResourceID>`）輪詢 `Status`，
   直到 `READY`（通常幾分鐘內）。
2. 調 `get_collection_api_key`（或 `ov-cp api-key <ResourceID>`），返回
   `{UserID, Role, ApiKey}` —— 這裡的 `ApiKey` 就是該庫的
   **Business Data Platform APIKey**，`UserID` 就是 user 身份。
3. 安全記錄：庫名、`ResourceID`、`UserID`、Business Data Platform APIKey。回覆中只說明
   "已安全記錄"，不展示明文。
4. 之後資料面 MCP 讀寫該庫（上傳、查詢、沉澱）一律用這把 Key。

**控制台兜底路徑**（MCP 不可用、api-key 呼叫被攔、或使用者已有存量庫時同樣適用）：
引導使用者開啟火山引擎 **Business Data Platform Service 控制台** → 在**左側選擇對應的庫** →
進入**「鑑權管理」** → 點選**「顯示鑑權憑證」**，即可拿到該庫的 Business Data Platform
APIKey。讓使用者把 Key 配置到資料面工具的環境變數/配置中，不要貼上進聊天。

## Step 5：環境就緒後的引導

以下條件全部滿足後，進入業務引導：AgentPlan APIKey 可用；OV 庫已建立或已
選擇且狀態 READY；Business Data Platform APIKey 與 user 身份已記錄。

使用以下結構回覆：

```markdown
銷售商機商單 Builder 已就緒。

已完成：
1. AgentPlan APIKey 可用（用於建庫、聯網、資料集查詢）。
2. Business Data Platform 個人庫「[庫名]」已就緒（READY）。
3. 該庫的 Business Data Platform APIKey 與 user 身份已安全記錄（用於讀寫庫資料）。

你可以直接這樣說：
1. **上傳資料**：把這份文件上傳到"[庫名]"。
2. **查詢商機**：總結某商機當前進展、風險點和下一步動作。
3. **生成跟進計劃**：基於已上傳材料，生成下一次客戶溝通提綱。
4. **沉澱記憶**：每天 19:00 把今天銷售相關 session 摘要上傳到"[庫名]"。

也可以先發我第一批文件（本地檔案或連結），我幫你上傳。
```

## 場景 A：資料上傳

把銷售文件、會議紀要、方案材料、報價說明、商單復盤等上傳到 OV 庫。

1. 讓使用者提供文件（本地檔案、資料夾或 URL）、標題或資料範圍。
2. 用已記錄的 Business Data Platform APIKey 調資料面 MCP 上傳到該庫。
3. 完成後返回：已上傳數量、成功/失敗列表（失敗給原因和重試建議）、
   可立即嘗試的查詢問題示例。

## 場景 B：銷售商機 / 商單查詢

1. 識別查詢物件：商機、商單、客戶、行業、階段、負責人、時間範圍。
2. 用 Business Data Platform APIKey 調資料面 MCP 在庫中檢索。
3. 優先輸出可執行結論，用固定結構：

```markdown
## 結論
[一句話概括]
## 當前進展
## 關鍵風險
## 下一步建議
## 需要補充的資料
```

4. 資訊不足時明確列出缺失資料，建議使用者上傳哪些資料。

推薦 query 示例：

- "總結某商機當前進展、關鍵決策人、阻塞點和下一步動作。"
- "這個商單目前最大的成交風險是什麼？"
- "從歷史會議紀要裡提取客戶最關心的 3 個問題。"
- "幫我生成下一次客戶跟進的溝通提綱。"
- "列出本週需要跟進的商機和建議動作。"

## 場景 C：session 記憶沉澱

把 Mira 中的銷售跟進會話、復盤內容定時上傳到 OV，形成可查詢的個人銷售記憶。

1. 詢問同步範圍（當前會話 / 指定專案 / 最近 N 天 / 關鍵詞）和頻率
   （每天、每週、會話結束後、指定時間）。
2. 用定時任務能力建立任務；執行時用 Business Data Platform APIKey 上傳摘要或全文。
3. 上傳內容帶元資訊：時間、主題、關聯商機、來源會話、摘要、待辦。
4. 不上傳無關閒聊、敏感憑據或使用者明確排除的內容。
5. 告知使用者定時任務可暫停、可刪除、可改頻率。

建議上傳結構：

```markdown
# 銷售跟進會話沉澱
## 基本資訊（時間 / 關聯商機 / 來源：Mira session）
## 摘要
## 客戶關注點
## 風險與阻塞
## 下一步待辦
```

## 異常速查

| 現象 | 含義 | 處理 |
|---|---|---|
| 無 AgentPlan APIKey | 未購買/未配置 | 給控制台連結，暫停建庫 |
| create 返回 `ProductUnordered` | 未開通 AgentPlan 抵扣 | 引導控制台開通抵扣，不要重試 |
| create 返回超限 | 已達 20 庫上限 | 讓使用者刪除閒置庫或複用現有庫 |
| api-key 呼叫超時 | 庫還在 INIT | 輪詢 `get_collection` 到 READY 再取 |
| 控制面 MCP / `ov-cp` 不可用 | 缺控制面能力 | 走 Step 2 徵求安裝同意，或控制台手工建庫 |
| 拿不到 Business Data Platform APIKey | — | 控制台「鑑權管理 → 顯示鑑權憑證」兜底 |
| 資料面讀寫鑑權失敗 | 可能 Key 用混了 | 確認用的是該庫的 Business Data Platform APIKey |
| 查詢無結果 | 庫裡沒有相關內容 | 說明未找到，建議上傳哪些文件 |

## 安全與合規

- 不要求使用者在聊天中貼上任何 APIKey；必須配置時指導用環境變數、憑據管理
  或控制台。
- 不輸出敏感憑據、客戶隱私、合同金額等明文，除非使用者明確要求且有授權。
- 上傳資料前確認使用者有權處理相關文件。
- 改動使用者本地配置（安裝 MCP、寫配置檔案）前先徵求同意；如目標檔案已存在,
  先備份再合併，不做破壞性覆蓋。
