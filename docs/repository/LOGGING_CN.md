# 開發者日誌輸出說明

本檔案規定 OpenViking 各執行時（Python、Rust、C++ 引擎、TypeScript）的日誌級別語義、內容邊界和落地方式。它面向提交程式碼的開發者，不是給終端使用者的部署說明；`log.level`、`log.format`、`log.output` 等配置項仍以[配置指南](../zh/guides/01-configuration.md)為準。

級別用途約束適用於 OpenViking 自有程式碼；第三方依賴保留原有級別語義，按 8.10 接入統一輸出。本文包含尚未落地的目標規範，現狀和實施順序分別見第 7、9 節，不能把規範示例視為當前已支援的配置能力。

相關入口：

- 日誌實現：`openviking_cli/utils/logger.py`（`get_logger`、`reconfigure_logging`、OTel 橋接）
- 日誌配置模型：`openviking_cli/utils/config/log_config.py`
- 審計事件匯流排：`openviking/observability/events.py`、`openviking/observability/usage_audit/`
- 貢獻流程：[CONTRIBUTING_CN.md](CONTRIBUTING_CN.md)

---

## 1. 級別語義

一條日誌應該落在哪一級，只取決於**這條記錄的作用**，不取決於「看起來嚴不嚴重」。

| 級別 | 唯一職責 | 允許出現的內容 | 禁止出現的內容 |
| --- | --- | --- | --- |
| `CRITICAL` | 程序級不可繼續 | 啟動致命失敗、關鍵狀態無法恢復 | 一般業務錯誤、可重試失敗 |
| `ERROR` | 需要人介入的失敗 | 未處理異常、依賴不可用導致請求失敗、資料一致性風險、後臺任務重試耗盡、審計/安全機制自身失效 | 預期內的業務拒絕（4xx 記 `INFO`）、重試中的單次失敗、已降級成功、效能偏慢、髒資料跳過 |
| `WARNING` | **僅限審計類事件** | 許可權與角色變更、帳號成員操作、金鑰生命週期、認證失敗、配置與資料刪除等安全敏感動作，以及 `api_key` 模式下 ROOT 身份的任何呼叫（見 3.5） | 兜底降級、重試退避、依賴缺失、慢呼叫、跳過/忽略、髒資料、快取未命中、觀測側通道失敗 |
| `INFO` | 兜底邏輯、狀態遷移與請求拒絕 | 重試與退避、降級與回退、熔斷開啟/恢復、主備切換、啟動/關閉、一次性遷移、彙總統計、4xx 業務拒絕（引數錯誤、未找到、未授權） | 成功請求的逐條業務細節、迴圈內逐條明細、payload 內容 |
| `DEBUG` | 業務過程 | 請求入參與出參摘要、狀態機遷移、檢索與解析中間結果、分支決策、快取操作細節 | 敏感值、超大物件、熱迴圈內的高頻逐條輸出 |

補充約定：

- `ERROR` 和 `CRITICAL` 都不允許在正常控制流裡出現。如果一次失敗能通過重試、降級或前端提示解決，它就不是 `ERROR`。
- `WARNING` 是**受控級別**，語義邊界由本檔案第 3 節鎖定。任何「我覺得值得注意」的記錄都不能進 `WARNING`，那是 `INFO`。
- `INFO` 承載「系統自己扛住了」的訊號。兜底、重試、退避、熔斷的狀態變化必須可觀測，但不需要人立刻處理。
- `DEBUG` 是預設的業務過程出口。寫業務程式碼時，先假設它屬於 `DEBUG`，再判斷是否命中第 3 節的審計清單或第 5 節的兜底與拒絕清單。
- 無論落在哪一級，**能寫什麼欄位**由第 4 節的日誌安全規則決定。級別合規不代表內容合規。
- 4xx 固定記 `INFO`：不升級為 `ERROR`（不是故障），也不下沉到 `DEBUG`（否則預設級別下看不到呼叫方誤用）。
- ROOT 呼叫是級別規則的單點例外：介面本身該走 `INFO` 或 `DEBUG`，但只要是 `api_key` 模式下的 ROOT 身份發起，就按 `WARNING` 留審計（見 3.5）。dev 與 trusted 模式不計。

### 判定順序

```text
這次記錄是不是安全敏感的使用者/管理員動作？
  是 → WARNING（審計，見第 3 節）
  否 ↓
請求/任務最終失敗且需要人介入嗎？
  是 → ERROR
  否 ↓
這次記錄描述的是「系統自己兜住了」的過程嗎（重試、降級、熔斷、回切）？
  是 → INFO
  否 ↓
DEBUG
```

### 容易誤判的邊界

| 場景 | 結論 | 理由 |
| --- | --- | --- |
| 客戶端引數錯誤、未找到資源、未授權（4xx） | `INFO` | 預期結果，不是故障；但反映呼叫方誤用，需要可觀測 |
| 認證失敗、越權嘗試（401/403 的安全面） | `INFO` 響應日誌 + 審計 `WARNING` | 兩條記錄目的不同，見 3.1 |
| `api_key` 模式下 ROOT 身份呼叫任意介面（含只讀） | `WARNING` | 超級使用者呼叫一律留審計，不以介面的業務級別為準；見 3.5 |
| 第一次呼叫失敗、第二次成功 | `INFO`（記錄重試） | 系統已恢復 |
| 重試次數耗盡、請求最終失敗 | `ERROR`（只記一條） | 需要人介入 |
| 主 provider 失敗切到備 provider 併成功 | `INFO` | 兜底成功 |
| 切到備 provider 後結果質量下降/欄位缺失 | `INFO` + 明確欄位標記，不升級為 `WARNING` | 仍屬兜底，不是審計 |
| 依賴不可用但走了預設值（如摘要為空） | `INFO` | 兜底 |
| 依賴不可用且無兜底、功能整體不可用 | `ERROR` | 故障 |
| 慢呼叫超閾值 | `INFO`（需要長期觀測時）或 `DEBUG` | 不是錯誤 |
| 觀測/指標寫入自身失敗 | `INFO`，首次 `ERROR` | 旁路通道，不得汙染業務級別 |
| 快取鎖搶不到、回源資料庫 | `INFO` | 兜底 |
| 迴圈裡 N 條資料裡有 M 條髒資料 | 一條 `INFO` 彙總 + 明細 `DEBUG` | 控制噪聲 |
| 配置裡出現未知欄位、非法值被忽略 | `INFO` | 相容兜底 |
| 請求頭 `X-Request-ID` 非法、已自動重建 | `INFO` | 客戶端衛生問題，非安全事件 |

---

## 2. 為什麼不是按「嚴重程度」分級

按嚴重程度分級會讓級別隨開發者主觀判斷漂移：同一類失敗，A 覺得是 `WARNING`，B 覺得是 `ERROR`。本倉庫當前就呈現了這個結果——`WARNING` 成了使用最多的級別（見第 7 節）。

按**作用**分級後，級別是可判定的客觀屬性：

- 需要人處理的 → `ERROR`，可以直接接告警。
- 需要留痕追責的 → `openviking.audit` 的 `WARNING`，按審計事件欄位接審計管道。
- 系統自愈的過程、呼叫方被正常拒絕的結果 → `INFO`，可以直接接容量/穩定性看板。
- 其餘細節 → `DEBUG`，只在排障時開啟。

自有程式碼可以據此選擇消費鏈路；混合輸出中的第三方日誌必須結合 logger 和事件欄位路由，不能僅憑 `WARNING` 判定為審計。

---

## 3. 審計類日誌（自有程式碼中 `WARNING` 的唯一合法用途）

### 3.1 必須覆蓋的事件

以下動作發生時必須有審計記錄。當前倉庫在多數位置缺失（見 7.3），新增這些記錄屬於純增量改動。

**帳號與成員**

- 建立/刪除帳號，帳號狀態變更（啟用、停用、遷移）
- 邀請、加入、移除成員；成員角色變更（`set_role`）
- 帳號級設定的重置與覆蓋（含 `reset_memory_template` 一類動作）

**許可權**

- ACL 授予、撤銷、刪除（`grant_acl` / `revoke_acl` / `delete_acl`）
- 跨帳號、跨使用者的資源授權
- 管理員、ROOT 許可權的授予與回收

**金鑰與憑證**

- API Key 建立、重新生成、吊銷、遷移
- OAuth/OIDC 身份繫結、解綁、受信身份批次註冊
- 金鑰/憑證明文匯出

**認證結果**

- 登入失敗、Token 校驗失敗、簽名校驗失敗
- 越權訪問被拒絕（角色不滿足、跨租戶訪問）
- 認證健康檢查從通過變為異常

需要注意：這一組是審計記錄，與請求返回 4xx 時的 `INFO` 響應日誌不是同一條。響應日誌記「這次請求被拒了」，審計記錄記「誰在什麼時候嘗試了什麼」。兩者的 logger、欄位、消費者都不同，允許並存；但普通 4xx（引數錯誤、資源不存在）只記 `INFO`，不進審計。

**配置與資料**

- 服務端配置、使用者配置、Runtime 配置的寫入與回滾
- 帳號資料刪除、任務刪除、快照刪除、批次匯出（ovpack）
- 隱私條目的寫入與清理

### 3.2 必填欄位

一條審計記錄至少包含（欄位取值同樣受第 4 節約束，`peer_id`、金鑰、正文不得進入審計）：

| 欄位 | 說明 |
| --- | --- |
| `ts` | UTC 時間戳，ISO 8601，固定毫秒精度，格式見 8.10.1 |
| `event` | 已登記的穩定事件名，統一以 `audit.` 開頭，如 `audit.account.create`、`audit.acl.grant` |
| `result` | `success` / `failure` |
| `actor_id` / `actor_role` / `actor_type` | 操作者身份；已知 `actor_type` 取 `user`、`admin`、`root`、`service`。認證失敗等無法確認身份的場景，相應欄位為 `null`，不能把輸入的使用者名稱當已認證主體 |
| `account_id` | 被操作物件所屬帳號；無帳號範圍的 ROOT 呼叫為 `null`，不能填虛構的預設帳號 |
| `target_type` / `target_id` | 物件型別與安全標識，如 `user`、`api_key`、`config`、`http_route`；不得把金鑰或原始 URI 當標識 |
| `action` | 由 helper 從 `event` 的末段生成 |
| `request_id` / `trace_id` | 從執行上下文取得；沒有對應上下文時為 `null` |
| `source_ip` / `user_agent` | 經 4.2 處理的入口資訊；不可用或不能安全提取時為 `null` |
| `error_code` | 失敗時必須是穩定錯誤碼，成功時為 `null`；不放異常訊息或堆疊 |

以上欄位必須存在，但明確允許為空的欄位使用 `null`，文本出口按 8.10 渲染。`actor_role` 是實際生效的角色，`actor_type` 是主體型別；後臺服務使用 `service`，不新增 `system` 這一別名。ROOT 呼叫還必須包含 3.5 的 HTTP 欄位。

### 3.3 輸出形式

當前範圍：日誌規範改造只調整現有日誌的級別、內容、格式和初始化。已有 Usage/Audit 儲存會儲存用量及 HTTP 請求記錄，但尚未處理本節的 `audit.*` 安全操作事件。對應的輔助函式、事件覆蓋、schema、落庫、查詢和保留期管理記為獨立功能待辦，本輪日誌改造不新增這些能力。

審計需要**雙寫**，不能只有其中一路：

1. **結構化事件**：目標是經事件匯流排發出，再由 `usage_audit` 投影持久化，形成可查詢、可保留期管理的主通道。現有 `try_publish_event()` 是 best-effort，現有投影也尚未處理這些 `audit.*` 事件；落地時必須補齊事件識別、持久化和失敗反饋，不能把「呼叫釋出函式」等同於「審計已落盤」。
2. **日誌副本**：寫入專用 logger `openviking.audit`，級別 `WARNING`。這是給日誌採集、SIEM、離線取證用的旁路副本。

日誌副本的採集條件必須同時檢查 `logger=openviking.audit` 和明確的審計 `event` 欄位，並校驗必填欄位。不能把整個程序的 `WARNING` 都送入審計管道；第三方告警的邊界見 8.10.6。

所有呼叫點統一使用待實現的 `log_audit()`。以下程式碼是目標介面示例，**不是當前可匯入的 API**。helper 的職責固定為：

- 呼叫方顯式傳入 `event`、`result`、操作者、帳號、目標和 `error_code`；不從任意請求引數猜測身份或目標。
- helper 捕獲事件時間 `ts`、生成 `action`，從執行上下文提取 `request_id`、`trace_id`、`source_ip`、`user_agent`；沒有上下文時保留上述欄位並填 `null`。
- 按 4.2 校驗、轉換欄位後，將**同一份完整記錄**送往兩個出口。日誌副本使用固定訊息 `"audit event"`，業務欄位全部放在 `extra`，由 8.10 的 formatter 輸出；採集端不需要解析訊息正文來尋找事件名或身份。

例如 ACL 授權完成後：

```python
log_audit(
    event="audit.acl.grant",
    result="success",
    actor_id=actor_id,
    actor_role=actor_role,
    actor_type="admin",
    account_id=account_id,
    target_type="user",
    target_id=target_user_id,
    error_code=None,
)
```

示例假定呼叫方是已認證管理員；其他主體傳入真實的 `actor_type`。失敗時使用 `result="failure"` 和對應的穩定 `error_code`，其他欄位保持同一 schema。

約束：

- 審計日誌**先執行後記錄**，記錄實際結果（成功與失敗都要寫），不要只記成功。
- 欄位校驗、釋出或持久化失敗由審計設施在失敗邊界記錄一條安全的 `ERROR`，並且不能回滾業務事務；不能吞掉失敗後宣稱雙寫成功。
- 審計記錄不得被業務層的 `except Exception` 靜默吞掉。
- 審計訊息裡禁止出現明文金鑰、密碼、Token、完整請求體。




### 3.4 反例

```python
# 反例：帳號遷移寫成 INFO，審計管道拿不到
logger.info("Migrated API key for user %s in account %s", user_id, account_id)

# 正例：由後臺遷移服務執行，log_audit 為 3.3 的目標介面
log_audit(
    event="audit.api_key.migrate",
    result="success",
    actor_id="api-key-migrator",
    actor_role=service_role,
    actor_type="service",
    account_id=account_id,
    target_type="api_key",
    target_id=user_id,
    error_code=None,
)
```

這裡 `service_role` 是服務實際使用的角色，`target_id` 用金鑰所屬使用者的穩定 ID，不是金鑰值。無請求上下文的後臺操作，其關聯欄位由 helper 填 `null`。

### 3.5 ROOT 呼叫

ROOT 是最高許可權身份。**在 `api_key` 鑑權模式下，任何以 ROOT 身份發生的呼叫都必須留一條 `WARNING` 審計**，即使這次呼叫只讀、即使它對業務毫無影響。

理由：ROOT 被誤用或洩露時，事後唯一能還原的就是軌跡；只讀呼叫同樣可能跨租戶讀取資料，其危害不比寫入小。ROOT 呼叫普通業務介面時本該落 `INFO`，此時以 `WARNING` 為準。

#### 觸發條件

兩個條件同時成立才記錄：

1. 認證模式為 `api_key`（`AuthMode.API_KEY`）；
2. 經認證解析出的 `identity.role == Role.ROOT`，即持有 root API key（`server/api_keys/key_mgr.py:131`）。

#### 不觸發的情況

| 情況 | 原因 |
| --- | --- |
| `dev` 模式（`auth/plugins/dev.py:41`） | 無認證，所有請求被合成 ROOT，不是真實超級使用者 |
| `trusted` 模式（`auth/plugins/trusted.py:183`） | ROOT 由網關注入（admin path、`/health` control probe），不代表真實操作者 |
| 自定義 auth 模式 | 語義未知，預設不記；需要審計的模式應在自己外掛裡呼叫 `log_audit()` |
| 未認證路由（`/health`、`/ready`、`/metrics`） | 不產生 ROOT 身份 |
| 程序內構造的 ROOT context（TTL、semantic processor、viking_fs、system_assets、pack_service、core） | 不經過認證入口，天然不觸發 |

#### 實現位置

`_build_request_context()`（`server/auth/__init__.py:113`）是唯一同時能看到 `identity.role`、認證模式和 `request.state` 的收口點。不要把它散進 38 處 `Role.ROOT` 引用裡（其中 18 處是等值判斷）。

推薦「入口打標、完成輸出」，保證一條記錄裡既有呼叫方也有結果：

```python
# _build_request_context()：只打標，不輸出
if ctx.role == Role.ROOT and _auth_mode(request) == AuthMode.API_KEY.value:
    request.state.root_audit = {
        "actor_id": identity.user_id or "root-key",
        "account_id": identity.account_id,
    }
```

```python
# 請求完成階段：輸出唯一一條
if (root_audit := getattr(request.state, "root_audit", None)) is not None:
    log_audit(
        event="audit.root.invoke",
        result="success" if status_code < 400 else "failure",
        actor_id=root_audit["actor_id"],
        actor_role="root",
        actor_type="root",
        account_id=root_audit["account_id"],
        target_type="http_route",
        target_id=http_route,
        http_route=http_route,
        http_method=method,
        http_status_code=status_code,
        error_code=None if status_code < 400 else error_code,
    )
```

`http_route` 必須是匹配後的路由模板，不能使用帶路徑引數或 query 的原始 URL；失敗的 `error_code` 來自響應分類，未分類時用固定的 `HTTP_REQUEST_FAILED`。呼叫發生在執行上下文清理前，由 helper 注入請求關聯與入口欄位。

`_auth_mode()` 已有實現（`server/auth/__init__.py:32`），不要自己再讀一次 config。注意它在拿不到 config 時會回落到 `api_key`，單元測試裡要顯式注入認證模式，否則測試請求會被當成真實 ROOT。

#### 必填欄位

包含 3.2 的全部欄位，其中 `event=audit.root.invoke`、`action=invoke`、`actor_role=root`、`actor_type=root`、`target_type=http_route`、`target_id` 為路由模板；另外包含 `http_method`、`http_route`、`http_status_code`。

- root API key 沒有帳號與使用者，`actor_id` 寫 `root-key`，不要寫成 `default/default`。
- 失敗同樣記錄，`result=failure` 並帶 `error_code`。
- 高危動作（ROOT 讀取金鑰明文、跨帳號讀寫）額外標 `sensitive=true`，便於單獨告警。

#### 約束

- 一條請求一條，不重複。入口與完成階段不要各記一次。
- 不採樣。審計取樣等於放棄審計；ROOT 輪詢（Studio 任務輪詢、SDK 健康檢查）造成量大時，降低輪詢頻率或改用非 ROOT 身份，而不是在服務端丟樣本。
- 記錄內容仍受第 4 節約束：不寫請求體、不寫路徑引數原文、不寫上下文內容。

---

## 4. 日誌安全規則

日誌檔案、trace 屬性、審計儲存是三條獨立出口，任一條洩露都算洩露。本節按**欄位**規定什麼能出來。

### 4.1 白名單，而不是黑名單

預設拒絕。只有 4.2 表中「允許」一欄的欄位可以原樣輸出；其餘欄位必須轉換（雜湊、截斷、脫敏、取相對路徑），或降級為聚合量（長度、計數、耗時、布林）。判斷不了歸屬時按禁止處理。

### 4.2 欄位分級

| 分級 | 欄位 | 處理方式 |
| --- | --- | --- |
| 允許 | 日誌框架生成的 `ts`、`level`、`logger`、`pid` | 原樣輸出；logger 使用固定模組名或元件名，不拼接使用者輸入 |
| 允許 | `account_id`、`user_id`、`request_id`、`trace_id`、`span_id`、`operation`、`http_method`、`http_route`、`http_status_code`、`duration_ms`、`role`、`task_id`、`task_type`、`task_status`、`task_stage`、重試次數、佇列深度、`error_code`、`error_type`、`file_type` | 使用已驗證的身份/關聯標識、固定列舉、異常型別名或數值；`http_route` 只使用路由模板 |
| 允許 | `event`、`action`、`result`、`actor_role`、`actor_type`、`target_type` | 使用已登記事件及固定列舉；按 3.2 校驗，不能由使用者自由文本生成 |
| 允許 | `degraded`、`sensitive`、`truncated`、`payload`、`total`、`failed`、`skipped`、`original_length` | 布林值或非負計數，不攜帶正文 |
| 允許但需校驗/轉換 | `actor_id`、`target_id` | 來自已認證主體、固定服務標識或已解析物件的穩定 ID；若含路徑、URI、peer 段則按 4.4–4.7 轉換；不能使用金鑰、憑證或任意請求原文。`target_type=http_route` 時僅使用路由模板 |
| 允許但需校驗/轉換 | `source_ip` | 只保留傳輸層或受信代理解析並驗證的單個 IP 地址；不原樣記錄轉發頭，不可確定時為 `null` |
| 允許但需校驗/轉換 | `user_agent` | 只保留經白名單解析的產品族與版本摘要，去掉其他自由文本並限制為 256 位元組；不能安全解析時為 `null`，不保留原始請求頭 |
| 允許但需轉換 | 本地路徑、`viking://` URI、`resource_id`、異常訊息 | 按 4.4–4.8 處理 |
| 禁止 | `peer_id`、金鑰與憑證、上下文內容、絕對路徑、完整請求/響應體、模型輸入輸出 | 永不輸出 |

任務元資訊（`task_id`、`task_type`、狀態、階段、耗時、重試與錯誤計數、佇列深度）可以直接列印，這是排障最常用的維度。任務的 `meta` 是例外：只有在確認其值不含 URI、路徑、金鑰後才可整體列印，否則只打印鍵名，不列印值。

`resource_id` 只允許作為不透明部署標籤列印；一旦它來自環境變數且可能是路徑或 URL，按 4.7 處理。

### 4.3 已有的注入基線

`_get_log_context()` 目前只注入 `trace_id`、`span_id`、`request_id`、`operation`、`account_id`、`user_id`；`RootSpanAttributes.to_log_fields()` 也刻意排除了 `url_path` 與 `url_query`。這是本節的既有實現基線，新增注入欄位同樣受 4.2 約束。

但 `ObservabilityContext.extra` 會無條件合併進日誌欄位，因此 `extra` 不是法外之地。

### 4.4 `peer_id`

禁止出現在日誌、trace 屬性、審計欄位中，包括四種間接形式：

1. `viking://user/{user_id}/peers/{peer_id}/...` 一類 URI 內嵌 peer_id；
2. `RequestContext.actor_peer_id`；
3. 序列化物件時被帶出（`%r`、`%s`、`asdict()`、`model_dump()`）；
4. 任務 `meta` 中的資源定位資訊。

替代寫法：

```python
# 反例：完整 URI 暴露 peer
logger.info("rebuild failed uri=%s", "viking://user/u1/peers/p9/memories")

# 正例：截斷到 user 級，peer 只留關聯雜湊
logger.info("rebuild failed user=%s peer=%s", user_id, short_hash(peer_id))
```

需要跨日誌關聯同一 peer 時，用不可逆短雜湊（`sha256(peer_id)[:8]`）。雜湊只在同一部署內具備關聯意義，不要在跨環境分析中複用結論。

### 4.5 金鑰與憑證

以下值一律禁止，且禁止任何足以還原的派生形式（字首、字尾、長度組合）：

- API Key、User Key、`submission_token`、`submission_hash`
- OAuth access/refresh token、JWT、OIDC 斷言
- Cookie、`Authorization`、簽名頭、預簽名 URL
- 資料庫/Redis 連線串中的憑證
- 加密金鑰、`ov privacy` 管理的明文條目

唯一例外：診斷輸出必須展示 key 時使用 `mask_api_key()`（僅露末端 4 位），且僅在顯式診斷開關下啟用。

`repr=False`（`RequestContext.api_key`、`TaskRecord.auth`）只擋 `repr()`，擋不住 `asdict()`、`model_dump()`、`__dict__`。因此規則是**禁止把整個物件塞進日誌**，而不是依賴 `repr=False`。

### 4.6 上下文內容

「上下文內容」指任何由使用者、模型或外部資源產生、且未被等價剪裁的文本：

- prompt、system prompt、messages、tool call 引數與結果
- 會話正文、記憶正文、摘要正文、Rule 正文、技能正文
- 文件/網頁/程式碼正文與片段、檢索命中的 chunk 文本
- 使用者輸入、模型輸出

允許輸出的替代量：字元數、token 數、條目數、語言、檔案型別、`sha256[:8]`、是否命中。

現有 `log_payloads` 是反例：`models/rerank/jev_rerank.py:191`、`service/rule_jev.py:76` 在開關開啟時用 **`WARNING`** 列印完整請求與響應 payload，query 與文件正文全部落盤。整改方向：預設關閉（當前已是預設）、開啟時降為 `DEBUG`、強制標註 `payload=true` 並經過脫敏，且只在排障環境啟用。

### 4.7 路徑

禁止列印絕對路徑。它洩露部署目錄、主機使用者名稱，以及 `workspace/{account_id}/{user_id}/peers/{peer_id}/` 這樣的目錄結構——等於把 peer_id 和租戶佈局一起暴露。

規則：

- 只打印 workspace 內的**相對路徑**、純檔名或副檔名；
- 使用者可控路徑（zip 條目名、markdown 圖片路徑、上傳檔名、WebDAV 路徑）禁止原樣列印，它們可能含 `../`、絕對路徑或 peers 段；
- 需要定位時用 `相對路徑 + sha256[:8]`；
- `viking://` URI 與本地路徑同等對待，peer 段按 4.4 處理；
- 異常訊息中的路徑同樣適用；無法可靠提取並轉換時不輸出異常原文，改記異常型別與穩定錯誤碼。現有 `sanitize_error()` 不處理路徑，不能據此認定內容安全。

當前有 34 處日誌直接列印 `file_path` / `path_str` / `resolved_path` 一類變數（如 `parse/parsers/markdown.py:845`、`parse/parsers/text_encoding.py:74`），屬於待整改範圍。

### 4.8 異常與錯誤訊息

異常字串經常內嵌觸發值（`InvalidArgumentError("bad uri: ...")`），所以 `logger.warning("...: %s", e)` 本身就是一條洩露通道。

- 預設只輸出 `type(exc).__name__`、由程式確定的穩定錯誤碼及明確允許的結構化欄位；不能把 `str(exc)` 當作錯誤碼。
- `task_domain.sanitize_error()` 目前只替換部分憑證字首並截斷長度，不處理絕對路徑、peer URI 或普通 `password=` 值。它不是通用日誌脫敏器，呼叫它不構成輸出異常文本的許可。
- `sanitize_public_http_error()` 處理已知憑證模式與大小限制，也不保證移除路徑、peer 或上下文正文。現有工具只能作為區域性防護，不能替代欄位白名單。
- 只有經場景明確的安全提取、脫敏與驗證後才可輸出異常摘要；這項能力落地前省略異常原文。完整堆疊只在 `ERROR` 且顯式本地排障時輸出，並先處理異常訊息、原始碼行、路徑等可能攜帶的敏感內容；不能直接用 `exc_info=True` 繞過此要求。
- 不輸出 `repr(exc.args)` 或未經處理的異常物件。

### 4.9 三個出口同時成立

| 出口 | 現有防護 | 要求 |
| --- | --- | --- |
| 日誌檔案/stdout | 公共 formatter 與 `log_safety.py` 欄位白名單 | 呼叫點仍負責訊息內容安全；formatter 無法脫敏任意文本 |
| OTel trace 屬性 | `to_log_fields()` 已排除 `url_path`、`url_query` | 新增 span 屬性同樣受本節約束；`url.path` 只在確有需要時保留 |
| 審計儲存 | `sanitize_public_http_error()`、`sanitize_error()`、`SENSITIVE_TASK_KEYS` 的區域性防護 | 仍須按本節校驗/轉換欄位；不能假定現有函式覆蓋路徑、peer 與正文 |

### 4.10 建議的實現與檢查

- 使用 `openviking/observability/log_safety.py`：`short_hash()`、`safe_uri_for_log()`、`safe_path_for_log()`、`safe_log_fields()`；為異常摘要定義按場景提取允許欄位的介面，不承諾用通用正則清洗任意異常文本。
- `repr=False` 只作兜底，不能當防線。
- CI：用 AST 掃描 logger 呼叫，命中停用識別符號（`peer_id`、`api_key`、`token`、`prompt`、`content`、`messages`、絕對路徑變數）先告警，穩定後阻斷。
- 測試：脫敏函式補單測；審計路徑與 `log_payloads` 路徑各補一條失敗用例。

### 4.11 安全評審清單

- [ ] 新增日誌欄位都在 4.2 白名單內，或已按 4.4–4.8 轉換。
- [ ] 沒有列印 `peer_id`，也沒有列印會內嵌 peer 段的完整 URI。
- [ ] 沒有列印金鑰、憑證、token、Cookie、連線串。
- [ ] 沒有列印 prompt、messages、正文、chunk、模型輸出。
- [ ] 沒有列印絕對路徑；使用者可控路徑已轉換。
- [ ] 沒有用 `%r` / `%s` / `asdict()` / `model_dump()` 列印整個物件。
- [ ] `extra` 欄位同樣合規。

---

## 5. 兜底、重試與 4xx 拒絕（`INFO`）

`INFO` 的讀者是運維和值班同學：他們需要知道「系統正在自己掙扎」或者「呼叫方被正常拒絕」，但不需要被叫醒。兜底類記錄必須滿足三個條件：**有狀態遷移、有次數、有結果**。

### 5.1 重試與退避

```python
logger.info(
    "retry operation=%s attempt=%d/%d delay=%.2fs error=%s",
    operation_name,
    attempt + 1,
    retry_limit,
    delay,
    type(exc).__name__,
)
```

- 每次重試一條 `INFO`，**不要用 `WARNING`**。
- 重試耗盡後的最終失敗再打一條 `ERROR`，且只打一條。
- 批次重試按批匯總，不要每條資料一條日誌。
- 重試中的異常預設只放型別和穩定錯誤碼；摘要與最終失敗的堆疊仍須滿足 4.8 的顯式排障和安全處理條件。

### 5.2 降級與兜底

```python
logger.info(
    "vlm unavailable; using empty summary file_type=%s",
    file_type,
)
```

- 兜底分支必須記錄**觸發了哪個兜底**和**降級後的行為**，否則排障時無法區分「本來就是這樣」和「悄悄降級了」。
- 兜底導致結果不完整時（如摘要為空、欄位缺失），在訊息裡顯式寫出 `degraded=true` 一類的標記，讓下游能篩。
- 不允許把兜底寫成 `WARNING`，否則 `WARNING` 會重新變成「需要注意」垃圾桶。

### 5.3 熔斷與狀態遷移

`INFO` 記錄狀態機的每一次躍遷：`CLOSED → OPEN`、`OPEN → HALF_OPEN`、`HALF_OPEN → CLOSED`，以及主備切換與回切。倉庫裡 `openviking/utils/circuit_breaker.py` 已經是這個寫法，可以當作範例。

### 5.4 啟動、關閉、遷移

程序啟動/關閉、一次性資料遷移、快取預熱、後臺任務的啟停，統一 `INFO`。單次請求的生命週期不要用 `INFO` 鋪滿。

### 5.5 4xx 業務拒絕

客戶端引數錯誤、資源不存在、未授權等 4xx 結果固定記 `INFO`。理由有三：

- 它不是故障，所以不能是 `ERROR`，否則告警通道會被呼叫方誤用淹沒；
- 它反映真實的呼叫方問題（SDK 用法錯誤、許可權配置缺失、URI 拼錯），排障時有用，所以不能沉到 `DEBUG`；
- 它按請求產生，量級可控，不構成 `INFO` 噪聲。

```python
logger.info(
    "request rejected status=%d error_code=%s route=%s",
    400,
    code,
    http_route,
)
```

約束：

- 一條請求一條拒絕日誌，不要在 service 層和 router 層各記一次。
- 4xx 不產生 `ERROR`，也不寫堆疊。
- 401/403 中屬於安全事件的（認證失敗、越權嘗試）另外產生一條審計 `WARNING`，見 3.1；普通 4xx（引數錯誤、404）不進審計。
- 4xx 的響應日誌與審計記錄是兩條不同用途的記錄，允許並存，但不要用同一條日誌冒充兩者。

---

## 6. 業務過程日誌（`DEBUG`）

默認出口。這裡放的是**成功路徑**上的業務過程；被拒絕的請求走 5.5 的 `INFO`。寫作要求：

- 記錄**決策依據**，不記錄無資訊量的進度。`"start to process"` / `"done"` 這類沒有價值。
- 摘要化大物件：URI、數量、長度、雜湊、耗時；不要整段文件、整段 prompt、整個響應體。
- 熱路徑先判斷級別再拼裝：

```python
if logger.isEnabledFor(logging.DEBUG):
    logger.debug("retrieval candidates=%s", summarize(candidates))
```

- 中間結果只在 DEBUG 打，且單條有長度上限（建議 ≤ 2 KB，超出截斷並標註 `truncated=true`）。

---

## 7. 現狀盤點

以下資料取自當前 `main`（統計範圍 `openviking/`、`openviking_cli/`、`openviking_gateway/`，不含 `tests/`、`benchmark/`、`bot/`）。

### 7.1 級別分佈

| 包 | DEBUG | INFO | WARNING | ERROR | EXCEPTION | CRITICAL |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `openviking/` | 266 | 385 | **471** | 247 | 88 | 4 |
| `openviking_cli/` | 5 | 6 | 17 | 2 | 0 | 0 |
| `openviking_gateway/` | 1 | 0 | 5 | 0 | 8 | 0 |
| 合計 | 272 | 391 | **493** | 249 | 96 | 4 |

`WARNING` 是使用最多的級別，比 `INFO` 多 26%，比 `DEBUG` 多 81%。這與「`WARNING` 僅限審計」的目標完全相反。

### 7.2 `WARNING` 的實際內容

493 條 `WARNING` 中：

- 含 `fail` / `error` / `unavailable` / `invalid` / `unable` / `exception` 等失敗語義：約 190 條
- 含 `fallback` / `retry` / `degrade` / `skip` / `ignor` / `disabled` / `missing` 等兜底語義：約 41 條
- 含 `account` / `permission` / `role` / `acl` / `api_key` / `revoke` / `grant` 等審計語義：按關鍵詞匹配約 **7 條**，且這幾條都是失敗路徑（如「受信身份批次註冊失敗，將重試」），不是審計事件

也就是說，`WARNING` 里約 98% 的內容按新規範應該下沉到 `INFO` 或 `DEBUG`，而真正該在 `WARNING` 的審計事件基本不存在。

典型反例（按新規範應降級）：

| 位置 | 當前 | 應改為 |
| --- | --- | --- |
| `openviking/utils/model_retry.py:491` | 可重試錯誤後 `WARNING`，附退避時間 | `INFO` |
| `openviking/models/embedder/base.py:422` | 慢呼叫（≥3s）`WARNING` | `INFO` |
| `openviking/server/account_stores/redis_mysql.py:485` | 鎖不可用、回源 MySQL `WARNING` | `INFO` |
| `openviking/server/account_stores/file.py:248` | 帳號儲存過載失敗、將重試 `WARNING` | `INFO` |
| `openviking/storage/queuefs/semantic_processor.py:1357` | VLM 不可用、用空摘要 `WARNING` | `INFO` |
| `openviking/observability/http_observability_middleware.py:557` | 指標寫入失敗 `WARNING` | `INFO`（首次可 `ERROR`） |
| `openviking/server/request_id.py:77` | `X-Request-ID` 非法已重建 `WARNING` | `INFO` |

### 7.3 審計缺口

| 模組 | 日誌呼叫數 | 說明 |
| --- | ---: | --- |
| `openviking/server/api_keys/key_mgr.py` | 0 | 帳號建立、使用者註冊、金鑰重生成、角色設定、刪除全流程無日誌 |
| `openviking/server/routers/acl.py` | 0 | ACL 查詢/設定/刪除/授予/撤銷全部無日誌 |
| `openviking/server/routers/admin.py` | 6 | `create_account`、`delete_account` 無審計；6 條全部是清理階段的異常 |
| `openviking/server/routers/system.py` | 2 | 身份解析失敗用 `WARNING`，屬兜底 |

結論：不是「`WARNING` 用錯了地方」這麼簡單，而是**審計能力本身缺失**。這是優先順序最高的一項。

### 7.4 分模組改造前的實現基線

以下清單保留 PR #7769 和日誌基礎批次之前的基線。基礎批次已將預設級別改為 `INFO`，將 tracer 遷到 stdlib logging，統一 Python/root 與 Rust/C++ 輸出，並關閉獨立伺服器重複的 Uvicorn 訪問日誌；bootstrap 狀態提示保留直接控制台列印。安全操作審計能力記為獨立功能待辦，剩餘現有日誌呼叫點整改繼續按後續批次推進。

1. **預設級別壓制了 `INFO`**：`LogConfig.level` 預設 `WARNING`（`openviking_cli/utils/config/log_config.py:12`），而 `_load_log_config()` 的兜底值是 `INFO`（`openviking_cli/utils/logger.py:684`）。按新規範把兜底/重試放進 `INFO` 後，預設部署將完全看不到這些訊號。
2. **惰性格式化違規**：啟用 ruff 的 `G` 規則可掃出 480 處，其中 `G004`（f-string 日誌）449 處、`G201`（`.error(..., exc_info=True)` 應為 `.exception()`）27 處、`G001` 4 處。當前 `pyproject.toml` 只啟用了 `E/W/F/I/C/B`，這些問題不會被 CI 攔住。
3. **兩套日誌棧**：主體是 stdlib `logging` + `get_logger()`，但 `openviking/telemetry/tracer.py` 仍用 `loguru`，其獨立輸出未納入統一 formatter。
4. **多執行時各配一套**：Rust binding 通過 `openviking/utils/agfs_utils.py` 接收 `log.level` 和 `log.output`，C++ 引擎通過 `openviking/storage/vectordb/utils/logging_init.py` 轉換 Python 格式；共享配置源並未統一最終輸出。Rust 仍使用獨立的 tracing formatter，且 `CRITICAL` 配置對映為 `ERROR`，格式與級別對映缺少統一校驗。
5. **訪問日誌重複**：`openviking.observability.http` 對每個請求打一條完成日誌（`openviking/server/request_id.py:86`），`uvicorn.access` 也會打一條；當 `log.level=INFO` 時同一請求出現兩條。
6. **`print()` 殘留**：庫程式碼中 334 處 `print(`，主要集中在 `openviking/server/bootstrap.py` 的啟動路徑，繞過級別控制與脫敏。
7. **只有純文本格式**：`_build_standard_handler()` 只掛了 `logging.Formatter(format_string)`，沒有 JSON 選項；`request_id` 是拼進訊息體的（`openviking_cli/utils/logger.py:489`），採集側無法按欄位切分。
8. **迴圈內無收斂**：`local_collection.py`（18 條 `WARNING`）、`semantic_processor.py`（11 條）等在逐條處理場景中直接打日誌，批次失敗會刷屏。
9. **同一輸出流有多種格式**：Python 預設時間沒有時區、以逗號分隔毫秒；Rust 輸出 UTC、微秒和 `WARN`；loguru 使用另一套分隔符；啟動 `print()` 沒有日誌頭。把這些輸出交給 systemd 或容器採集並不會自動統一應用日誌格式。
10. **第三方接管 root logger**：當前 MCP 依賴的 `FastMCP` 構造過程呼叫 `logging.basicConfig()`，root 尚無 handler 且 Rich 可用時會安裝 `RichHandler`。MCP、APScheduler 等傳播到 root 的記錄因此使用短日期、分欄、自動折行與重複時間省略。`_MANAGED_LOGGER_ROOTS` 當前只覆蓋 `openviking`、`openviking_cli`、`uvicorn`，未覆蓋這一齣口。

---

## 8. 補充規範（原原則之外需要補齊的部分）

原原則只定義了「級別 → 用途」的對映，落地還需要下面這些約定。

### 8.1 一條日誌只記一次

由**決定最終處理結果的邊界**記錄一次：HTTP 響應邊界、後臺任務終態或啟動入口負責判斷結果與級別；中間層只傳播或包裝異常，不提前記錄最終失敗。捕獲並完成降級的層記錄 `INFO`；一次重試記錄的是嘗試與退避，不是最終 `ERROR`。若中間層返回錯誤物件，仍由消費該物件並決定最終結果的邊界記錄。

```python
# 反例：中間層提前記錄，邊界處理時又記錄一次
except Exception as exc:
    logger.exception("compile tag validation failed")
    raise OpenVikingError(...) from exc

# 正例：底層純丟擲，邊界層統一記錄
except (ConfigPatchError, ValueError) as exc:
    raise InvalidArgumentError(str(exc)) from exc
```

邊界按第 1、5 節記錄 4xx 拒絕、兜底或最終失敗；即使框架要求邊界繼續丟擲，也要明確後續記錄者不再重複記錄同一失敗。異常欄位與堆疊仍受 4.8 約束。

### 8.2 惰性格式化

Python stdlib 日誌使用 `%s` 等佔位符，禁止 f-string 和 `.format()`：

```python
# 反例
logger.warning(f"Failed to resolve identity: {e}")
# 正例
logger.info("identity resolution failed error_type=%s", type(e).__name__)
```

佔位符避免級別關閉時的字串格式化開銷，也保留原始訊息模板供聚合使用。惰性格式化不等於脫敏，禁止值無論用 f-string 還是 `%s` 都不能輸出；非 Python 執行時使用各自的惰性或結構化日誌介面。

### 8.3 結構化欄位優先

需要被檢索、聚合、告警的維度放 `extra`，不要只拼進訊息：

```python
logger.info(
    "HTTP request completed method=%s route=%s status=%d duration_ms=%.1f",
    method, route, status_code, duration_ms,
    extra={"http_method": method, "http_route": route,
           "http_status_code": status_code, "duration_ms": duration_ms},
)
```

約定欄位名：`request_id`、`trace_id`、`account_id`、`user_id`、`operation`、`http_route`、`duration_ms`、`result`、`degraded`；審計欄位使用 3.2 的完整 schema，不另設 `actor`、`account`、`route` 等別名。

### 8.4 敏感資訊

欄位級規則見第 4 節，那裡是唯一權威口徑。`mask_api_key()` 僅用於 4.5 允許的顯式診斷展示；`sanitize_public_http_error()` 與 `sanitize_error()` 的侷限見 4.8，不能把呼叫這些函式視為可輸出任意異常文本的依據。日誌、trace 和審計落盤均按同一欄位規則處理。

### 8.5 噪聲控制

- 迴圈/批次場景：一條彙總 + 明細 `DEBUG`，彙總裡帶 `total` / `failed` / `skipped`。
- 同一最終失敗只保留決策邊界的一條 `ERROR`，重複診斷細節按需放 `DEBUG`；不能因為去重就把審計 `WARNING` 或兜底 `INFO` 升為 `ERROR`。
- 第三方庫的閾值在 server 日誌初始化入口統一配置，不要靠業務呼叫方自己 `setLevel`；不得為降低噪聲批次改寫其級別語義，見 8.10.6。
- 高頻路徑（每請求、每 chunk、每候選）預設 `DEBUG`，且先 `isEnabledFor`。

### 8.6 單條日誌體積

單條訊息建議 ≤ 2 KB，結構化欄位值 ≤ 1 KB。超長時截斷並標註 `truncated=true`、`original_length=<n>`。禁止直接 `%r` 一個大物件或整個異常上下文。

### 8.7 文案風格

- 統一英文，便於跨團隊 grep 與英文文件對應。
- 小寫開頭，不加句號，不寫「Oops」「Something went wrong」這類無資訊量措辭。
- 來源統一由日誌頭的 `logger` 表達，不再要求訊息手寫 `[模組名]`；存量字首可以逐步清理，穩定事件名或操作名仍可保留。
- 同一條訊息的模板保持穩定，變數只放在佔位符位置，否則聚合時會產生大量離散值。

### 8.8 不記錄的東西

- 不做「函式進入/退出」式埋點（用 tracing 或 profiler）。
- 不為日誌而日誌：一條日誌要能回答「發生了什麼、影響誰、下一步看什麼」中的至少一個。
- 不在日誌裡輸出業務邏輯判斷結果作為唯一證據；關鍵分支要落到指標或事件匯流排。

### 8.9 測試

- 用 `caplog` 斷言**級別與結構化欄位**，不要斷言完整文案。
- 審計路徑必須有針對性測試，至少覆蓋成功與失敗兩種結果。
- 不為「日誌是否被呼叫」寫 mock 斷言。
- 格式與接入測試必須檢查最終輸出流，覆蓋第三方和原生元件；`caplog` 不能代替 8.10.7 的驗收。

### 8.10 統一輸出格式與初始化

Bootstrap 的啟動進度、依賴檢查、啟動結果及失敗提示使用直接 `print(..., flush=True)`，確保不受 `log.level` 和檔案日誌輸出配置影響。錯誤寫 stderr，其餘狀態寫 stdout。控制台訊息仍遵守第 4 節內容邊界，並與格式化執行日誌分開驗收。

以下是 server 日誌的目標規範，覆蓋 Python、Rust、C++、TypeScript、第三方依賴和併入 server 日誌的子程序輸出。獨立執行的 CLI/SDK 的宿主邊界見 8.10.4–8.10.5。格式轉換必須在初始化與適配層完成，不能讓業務程式碼手工拼日誌頭。

#### 8.10.1 時間

- 統一 UTC、ISO 8601，固定格式 `YYYY-MM-DDTHH:mm:ss.SSSZ`，例如 `2026-11-13T22:56:01.028Z`。先轉換到 UTC，再輸出 `Z`；禁止直接給本地時間加 `Z`。
- 使用事件產生時間，進入非同步佇列前捕獲；不要以寫盤或採集時間替代。原生高精度時間在輸出層統一到毫秒。
- 啟動、執行、關閉階段均適用；不受主機時區、locale 或終端寬度影響。不混用逗號毫秒、短日期、無時區時間，連續事件也不能省略時間。

#### 8.10.2 級別名稱與對映

最終輸出只使用大寫 `DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`。**配置閾值對映與輸出名稱歸一化是兩件事，必須分別驗證**：接受 `WARNING` 配置不代表輸出已經不是 `WARN`。

| 原生級別或別名 | 輸出名稱 | 約束 |
| --- | --- | --- |
| `debug` / `DEBUG` | `DEBUG` | 統一大小寫 |
| `info` / `INFO` | `INFO` | 統一大小寫 |
| `warn` / `WARN` / `warning` / `WARNING` | `WARNING` | 不保留 `WARN` 縮寫 |
| `error` / `ERROR` | `ERROR` | 不改變事件語義 |
| `fatal` / `FATAL` / `critical` / `CRITICAL` | `CRITICAL` | 僅對映原本的致命級別，不能把普通錯誤升級 |
| `trace` / `TRACE` | `DEBUG` | 原生 TRACE 僅在顯式啟用時歸一化，不因這張表預設開啟 |

- 配置層統一校驗、歸一化後再傳給各執行時；支援的配置別名必須明確記錄，未知值報配置錯誤，不允許各元件自行回退到不同級別。
- Rust tracing 沒有原生 `CRITICAL`；當前把 `CRITICAL` 閾值對映到 `ERROR` 是有損相容，無法只篩選致命事件，必須記錄這一限制。程序不可繼續的事件應由能表達 `CRITICAL` 的邊界層記錄；不能把所有 Rust `ERROR` 重新命名為 `CRITICAL`。
- 輸出名稱歸一化不重分類第三方事件，見 8.10.6。

#### 8.10.3 日誌頭與欄位

文本輸出的固定順序為：`ts level logger pid request_id trace_id message`，其餘結構化欄位追加在後。例如：

```text
2026-11-13T22:56:01.028Z INFO openviking.server.bootstrap pid=452394 request_id=- trace_id=- message="server started"
```

- `logger` 使用完整 Python logger 名、Rust target 或穩定的元件名；`pid` 是產生事件的程序。來源不能只藏在訊息字首中。
- 可空欄位在文本中寫 `-`，結構化事件和未來 JSON 輸出使用 `null`；`request_id`、`trace_id` 不可用時也遵守這一規則。後臺和啟動日誌不能編造請求標識。
- `message` 及追加欄位中的字串值按 JSON 字串規則引用和轉義；數字、布林值保持型別。換行、回車和控制字元不能破壞記錄邊界，所有值仍須先經過第 4 節的安全處理。
- 關聯欄位只由統一適配層注入，不再向訊息正文重複拼接。程式碼檔案與行號如需輸出，按 4.2 顯式登記為可選欄位，路徑仍受 4.7 約束。
- 當前介面卡只接受公共格式，並在載入時歸一舊內建格式；其他自定義格式校驗失敗。未來支援的自定義 `log.format` 必須保留必需欄位及時間、級別約定；不支援的跨執行時轉換應明確報錯，不能靜默退回元件預設值。未來 JSON formatter 使用相同欄位和語義。

#### 8.10.4 初始化與輸出歸屬

- server 入口擁有日誌配置，在載入會配置日誌的依賴、建立元件之前安裝最小統一輸出；讀取配置後沿用同一格式契約。bootstrap 配置載入失敗直接通過 `print(..., flush=True)` 寫 stderr。
- Python root 與受管 logger 統一接入，至少覆蓋 Uvicorn、MCP、APScheduler。明確 handler 與 `propagate` 歸屬，一條事件在每個目標出口只出現一次；審計雙寫與 OTel 匯出是不同出口。
- 禁止業務模組另裝 `basicConfig`、RichHandler 或獨立 formatter。對依賴的初始化副作用由整合層處理，不能任由後加載的元件改變輸出格式或閾值。
- 自有 loguru 呼叫遷到 `get_logger()`；暫時保留時，只能經單向橋接進入統一齣口，並移除重複 sink。Rust/C++ 在原生適配層實現同一契約，不能僅替換 `%l` / `%(levelname)s` 就宣稱格式一致。
- 多 worker 的每個程序分別初始化；重複初始化與配置過載不得累積 handler、重複輸出或丟失關聯欄位。不能熱更新的原生配置要明確要求重啟，不能只更新 Python 後聲稱全域生效。
- 被管理的子程序保留自身 PID 和元件名。併入同一日誌流時須遵守同一契約；尚未適配的輸出保留在明確標識的獨立日誌檔案，不冒充父程序事件。
- 作為 SDK 嵌入其他應用時，不能擅自清空或重配宿主 root logger；全域接管僅屬於獨立 server 入口，嵌入場景由宿主顯式選擇接入方式。

#### 8.10.5 非互動輸出與 `print()` 邊界

- server 的 stdout/stderr、檔案、systemd 和容器採集輸出統一 UTF-8，不使用 ANSI 顏色、Rich 分欄、自動折行、進度條或重複時間省略。一條事件佔一條物理行；檢視器自行換行不屬於應用輸出。
- 允許輸出的異常堆疊先按 4.8 脫敏，再把換行轉義到同一記錄中；不得產生無法歸屬事件的裸續行。JSON 模式同樣使用一行一個物件。
- Bootstrap 的啟動進度、依賴檢查、啟動結果及其管理的程序提示保留直接 `print(..., flush=True)`；其他執行日誌經過統一 logger。控制台訊息仍須保證內容安全，不列印原始憑證、異常全文或子程序正文。
- 互動式 CLI 的幫助、命令結果、進度展示可使用專用終端渲染；這不屬於 server 執行日誌。機器可讀結果和 stdio 協議佔用 stdout 時，診斷日誌必須寫 stderr，不能汙染協議流。

#### 8.10.6 第三方語義與審計隔離

- 第 1–3 節的級別用途約束適用於自有程式碼，不能要求第三方依賴把 `WARNING` 改成審計專用；例如 APScheduler 的任務錯過執行時間告警仍是執行告警。
- 第三方日誌保留原有級別語義與 logger 名稱，只統一時間、名稱拼寫、欄位和輸出方式；不能為了滿足審計約定，把所有第三方 `WARNING` 批次降到 `INFO`。
- 噪聲通過集中配置的 logger 閾值和明確的定向規則控制；任何會隱藏第三方故障的規則都應有針對性驗證。不得通過關閉第三方日誌來通過格式驗收。
- 審計日誌以專用 logger 和明確的審計事件欄位識別，遵守 3.2–3.3；第三方 `WARNING` 不進入審計，也不能替代必須由自有程式碼產生的審計記錄。

#### 8.10.7 驗收

對日誌初始化與適配層的改動，捕獲實際 stdout/stderr 或日誌檔案，至少驗證：

- 在 UTC 與 Asia/Shanghai 環境下，固定事件時間都輸出同一 UTC 時間戳，精度和格式一致。
- 正常請求、異常、關閉及 Python、MCP/APScheduler、Rust/C++ 的格式化執行日誌滿足必填欄位和單行約定。bootstrap 啟動/配置失敗提示單獨驗收：高日誌閾值和檔案輸出下仍直接顯示在 stdout/stderr。
- 非 TTY 重定向下無 ANSI、Rich 分欄、隱去的時間或裸續行；各元件遵守 `INFO`、`WARNING` 等閾值，原生級別對映的限制有獨立用例。
- 重複初始化、配置過載和多 worker 下，同一事件在每個目標出口恰好一次，PID 正確，請求關聯欄位不串到其他請求。
- 一條第三方 `WARNING` 保留為執行告警，一條 `openviking.audit` 事件進入審計，兩者不混淆。

斷言欄位、格式和記錄數量，不鎖定完整業務文案；原生元件與子程序需要實際出口驗證，不能只斷言 Python logger 被呼叫。

---

## 9. 落地路線

按模組分組依次提交，開始每組前同步上游，減少檔案重疊和衝突。第 3、4 批合併到同一個 PR；後續批次在前一組合入後再開始。

| 批次 | 範圍 | 狀態 |
| --- | --- | --- |
| 1 | 模型日誌及安全 payload 摘要 | 已合入 #7769 |
| 2 | 日誌初始化、觀測日誌、Python/Rust/C++ 輸出 | 已合入 #7778；C++ 相容性修復 #7794 |
| 3 | 認證、帳號、ACL、ROOT 相關現有日誌 | 已與第 4 批一同合入 #7806，不新增審計能力 |
| 4 | 業務服務現有日誌 | 已與第 3 批一同合入 #7806 |
| 5 | 解析、匯入、連接器 | 已合入 #7899 |
| 6 | 儲存與佇列，包括 Watch | 已合入 #7933 |
| 7 | 檢索、核心與工具 | 已實現；獨立 PR |
| 8 | 會話、記憶、編譯、CLI、Gateway | 第七批合入後 |

以下優先順序清單保留原始規範待辦。現有日誌整改按上述模組批次落實；新增審計能力不納入本輪改造。

| 優先順序 | 事項 | 影響面 | 說明 |
| --- | --- | --- | --- |
| P0 | 補齊審計事件（帳號、成員、角色、ACL、API Key、配置、刪除） | 新增程式碼，不改現有日誌 | 對應 7.3 的缺口，收益最大、風險最低 |
| P0 | 把 `log_payloads` 的完整 payload 輸出從 `WARNING` 降為 `DEBUG` 並強制脫敏 | 2 處（`jev_rerank.py`、`rule_jev.py`） | 當前開關一開就把 query 與正文寫進 WARNING，違反第 4.6 節 |
| P0 | ROOT 呼叫審計：`_build_request_context` 打標 + 完成階段輸出一條 `WARNING` | 1 個收口點 | 僅 `api_key` 模式；dev/trusted 與程序內構造天然不計，見 3.5 |
| P0 | 明確預設日誌級別 | 1 個欄位 + 文件 | 若堅持 `WARNING` 預設值，必須在文件中說明「兜底/重試預設不可見」 |
| P0 | 引入 `openviking.audit` logger 與 `log_audit()` 幫助函式 | 審計接入的前置能力 | 統一 schema、欄位轉換、事件投影與雙寫失敗反饋，驗證實際持久化後再接入業務事件 |
| P1 | 啟用 ruff `G` 規則 | CI | 先 `per-file-ignores` 圈定存量，再逐步清零 480 處 |
| P1 | 新增 `log_safety.py`（`short_hash`、`safe_uri_for_log`、`safe_path_for_log`、`safe_log_fields`） | 新增模組 | 給 4.4–4.8 的轉換提供唯一入口 |
| P1 | 統一 server 日誌初始化與最終輸出 | Python/root、Uvicorn、MCP/APScheduler、tracer、Rust/C++ | 落實 8.10；包含 bootstrap 控制台提示可見性、tracer loguru 遷移/橋接和實際輸出驗收，不等待全倉整改 |
| P2 | 按 7.2 清單把 `WARNING` 下沉到 `INFO`/`DEBUG` | ~190 處 | 建議按模組分批，每批附一條迴歸測試 |
| P2 | 迴圈內日誌收斂 | ~30 個檔案 | 彙總 + 明細 |
| P2 | 整改路徑類日誌（34 處）與 `peer_id` 間接洩露 | ~34 處 | 改為相對路徑 + 短雜湊 |
| P3 | 訪問日誌去重 | 2 處 | 明確由 `uvicorn.access` 還是 `observability.http` 承擔 |
| P3 | 清理其餘執行日誌的 `print()` | 全倉剩餘呼叫點 | bootstrap 控制台提示保留；互動式 CLI 展示與協議輸出按 8.10.5 區分，不機械替換 |
| P4 | JSON 格式化輸出選項 | 1 個 handler | 便於採集側按欄位切分 |

### PR 評審清單

提交前自查：

- [ ] 新增的每條日誌都能對上第 1 節的級別語義，沒有把兜底/重試寫成 `WARNING`。
- [ ] 安全敏感動作走 `log_audit()`，成功與失敗都記錄，欄位齊全。
- [ ] 沒有 f-string 或 `.format()` 日誌。
- [ ] 最終失敗由決策邊界記錄一次；中間層沒有提前記錄或重複堆疊，兜底與重試按 `INFO` 處理。
- [ ] 審計欄位已按 4.2 分類，示例與呼叫使用 3.2 的完整 schema；沒有把任意異常文本交給現有脫敏函式後直接輸出。
- [ ] 沒有把金鑰、Token、正文、完整 payload 寫進日誌。
- [ ] 沒有列印 `peer_id`、內嵌 peer 段的完整 URI、絕對路徑（第 4.4、4.7 節）。
- [ ] ROOT 可達的介面已確認會走 3.5 的審計，而不是隻打 `INFO`。
- [ ] 安全欄位自查已過一遍第 4.11 節清單。
- [ ] 迴圈/批次路徑有彙總，沒有逐條刷屏。
- [ ] 新增日誌文案是英文、模板穩定，來源由日誌頭的 logger 表達。
- [ ] server 輸出滿足 8.10 的 UTC 毫秒時間、統一級別名稱、必填欄位和單行約定。
- [ ] 沒有新增獨立 handler、Rich 輸出或執行日誌 `print()`；初始化與過載不會重複輸出。
- [ ] 第三方日誌保留語義，審計按專用 logger 和事件欄位路由，不按 `WARNING` 一刀切。
- [ ] 日誌初始化或跨執行時適配有實際輸出驗收，覆蓋 8.10.7。

---

## 10. 快速參考

以下級別用途針對自有程式碼；第三方語義與統一輸出契約見 8.10。

```text
審計（許可權/帳號/金鑰/配置/刪除）      → WARNING  openviking.audit
需要人介入的失敗                     → ERROR
重試、退避、降級、熔斷、主備切換      → INFO
4xx 業務拒絕（引數/未找到/未授權）    → INFO
api_key 模式下 ROOT 的任何呼叫       → WARNING  openviking.audit
業務過程、中間結果、成功請求細節      → DEBUG
程序無法繼續                         → CRITICAL
```

```text
可列印：account_id、user_id、request_id、trace_id、task_*、耗時、計數、錯誤碼
需轉換：本地路徑 → 相對路徑；URI → 去掉 peer 段；異常 → 型別 + 穩定錯誤碼 + 允許欄位
禁列印：peer_id、金鑰憑證、上下文內容、絕對路徑、完整 payload
```

```python
from openviking_cli.utils.logger import get_logger

logger = get_logger(__name__)

logger.debug("retrieval candidates=%d level=%s", len(candidates), level)   # 業務過程
logger.info("retry operation=embed attempt=%d/%d delay=%.2fs", n, limit, d) # 兜底
logger.error("ingest task failed after retries task_id=%s error_code=%s", task_id, error_code)
```
