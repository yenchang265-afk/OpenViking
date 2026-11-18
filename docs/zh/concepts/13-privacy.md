# 隱私配置與自動管理

本文介紹 OpenViking 的隱私配置能力，以及它與技能/會話寫入（提取）和讀取（載入還原）的協作機制。

## 目標

隱私配置用於把敏感值（如 `api_key`、`token`）從內容（如技能、會話）中分離出來。被自動掃描的敏感資訊，儲存在 OpenViking 使用者空間的隱私配置中並保留版本記錄，內容則儲存佔位符，讀取時可根據當前生效配置還原。

核心目標：

- 啟用功能後，在寫入時自動提取敏感值並佔位符化
- 讀取時按內容型別還原
- 支援版本查詢、切換與審計

---

## 核心物件與儲存結構

隱私配置在當前使用者空間內按二級鍵組織：`category + target_key`。

| 內容 | `category` | `target_key` |
|---|---|---|
| Skill | `skill` | Skill 名稱 |
| Session | `session` | Session ID |
| 個人金鑰 | `credential` | 如 `github`、`database` |

使用者空間下的儲存路徑：

```
viking://user/{user_id}/privacy/{category}/{target_key}/
├── .meta.json                 # 元資訊（active_version/latest_version/labels 等）
├── current.json               # 當前生效版本快照
└── history/
    ├── version_1.json
    ├── version_2.json
    └── ...
```

`current.json` 與 `history/version_x.json` 都是完整的隱私值字典（`values` 整包）。而 Session 或 Skill 中的正文只會儲存這些隱私值的引用（即佔位符）。

---

## 版本語義

### upsert（寫入）

- 每次 upsert 都以傳入 `values` 作為“新快照候選”
- 如果與當前版本 `values` 完全一致，則不新建版本，直接返回當前版本
- 否則建立新版本並自動設為當前生效版本
- 允許新增 key（不會因“未知 key”報錯）
- `values` 是完整快照，不是部分更新；省略的舊 key 不會保留在新版本中

### activate（激活）

- 將歷史版本設定為當前生效版本（寫回 `current.json`）
- 更新 `.meta.json` 中的 `active_version`
- 不會輪換或撤銷第三方服務中的金鑰；這裡只切換 OpenViking 使用的值

---

## 使用方法

自動脫敏預設關閉（`mode=off`，`restore=true`）。可通過[使用者 settings](../api/08-admin.md#user-settings) 設定 `privacy`，也可用 `server.user_config_defaults.privacy` 提供部署預設值；使用者設定優先。

| `mode` | 新敏感值自動發現的範圍 | 已提前登記的敏感值自動匹配的範圍 |
|---|---|---|
| `off` （預設值）| 關閉 | 關閉 |
| `registered` | 關閉 | Skill、Session |
| `auto` （推薦）| Skill、Session | Skill、Session |
| `auto_strict` | Skill、Session | Skill、Session，以及普通檔案寫入、資源匯入和預設讀取 |

另外，`restore` 獨立控制 `raw=true` 時 Skill、Session 的讀取還原。`custom_rules` 可補充自定義的敏感值格式規則，`never_mask` 可按精確值排除某些特定值的自動發現與匹配

> `ov privacy resolve` 不受這些開關限制。

自動發現敏感值，使用的是內建憑據格式檢測器（如火山方舟、GitHub Token、JWT、常見型別的私鑰）。自定義的敏感值，可自行存入 `credential` 或通過 `custom_rules` 配置識別規則。修改設定後，對後續讀寫請求生效。

---

## 技能的隱私提取與讀取還原

### 已登記值保護（寫入鏈路）

當通過 `add_skill` 寫入 Skill 時，會按 `mode` 執行已登記值保護和新值提取。

```
add_skill
  -> SkillProcessor.prepare_skill_privacy（檢測正文中的敏感片段）
  -> SkillProcessor.apply_skill_privacy
    -> PrivacySanitizer（匹配已登記值）
    -> 複用或儲存 Skill 欄位，生成佔位符
  -> 寫入佔位符化後的 SKILL.md
```

#### 關鍵點

1. **抽取結果來源**：預設採用規則檢測器和使用者自定義規則來抽取，可通過`OPENVIKING_SKILL_PRIVACY_EXTRACTION_METHOD=vlm` 切換為模型提取。
2. **內容替換**：原文中命中的敏感片段會替換為佔位符：
   - <code>&#123;&#123;ov_privacy:skill:&#123;skill_name&#125;:&#123;field_name&#125;&#125;&#125;</code>
3. **後設資料保護**：自動發現與按值匹配只處理正文，不處理 `name`、`description` 等後設資料。
4. **寫盤結果**：匹配成功的片段以佔位符儲存，未匹配內容保持原樣。該流程處理技能正文，不等於掃描並清理所有附件。
5. **配置保留**：更新技能時會合並新發現的欄位，並保留已有欄位及歷史；清理需顯式刪除。

---

### 載入還原（讀取鏈路）

讀取 `SKILL.md` 時，預設保留佔位符；顯式指定 `raw=true` 且 `restore=true` 時，`FSService.read` 會嘗試還原佔位符。

```
fs.read(uri)
  -> get_skill_name_from_uri(uri)
  -> restore_skill_content
    -> privacy.get_current(category, target_key)
    -> 還原正文中的引用
```

#### URI 匹配

當前支援通過後綴識別 Skill：`/skills/{name}/SKILL.md`，可相容 user-scoped skill 路徑，例如：

- `viking://~/skills/{name}/SKILL.md`
- `viking://user/{user_id}/skills/{name}/SKILL.md`

#### restore 規則

`restore_skill_content` 的行為如下：

1. **content 中有佔位符，且 privacy value 存在且非空**  
   -> 直接替換為對應值。

2. **content 中有佔位符，但 privacy value 缺失或為空**  
   -> 保留佔位符不替換，並記入 `unresolved_entries`。

3. **privacy 中存在 key 且非空，但 content 中沒有對應占位符**  
   -> 記入“額外配置”提示（`Configured but not referenced in content`）。

4. 當存在 `unresolved_entries` 或“額外配置”時，會在內容末尾追加：
   - `[Privacy Config Notice]`
   - `Missing config: ...`（如有）
   - `Configured but not referenced in content: ...`（如有）

指向當前使用者 Privacy 欄位的佔位符也會按其引用還原；指向其他使用者或缺失欄位時，保留佔位符。

> 僅當該 skill 已有 `current` 配置時，才會追加該技能的配置提示。

---

啟用還原時，`raw=true` 讀取返回的是敏感值原值；“額外配置”提示也會包含配置值。Privacy API 和歷史快照同樣可以返回完整值，該功能不等於儲存加密。需要加密儲存時，另見[儲存加密](./10-encryption.md)。

## 會話的隱私提取與讀取還原

### 自動提取（寫入鏈路）

向 Session 寫入訊息時，會按 `mode` 在工具輸出外接和訊息落盤前，將已登記值和新發現的敏感值替換為佔位符。

```
Session.add_messages_async
  -> extract_and_store_session_privacy
    -> PrivacySanitizer（保護已登記的個人金鑰）
    -> 規則檢測器（mode 為 auto / auto_strict 時發現新值）
    -> 儲存新增 Session Privacy 值，生成佔位符
  -> 工具輸出外接
  -> 寫入佔位符化後的訊息
```

#### 關鍵點

1. **匹配來源**：已登記的個人金鑰與當前 Session 的 Privacy 值；若啟用自動發現時，根據內建和使用者自定義的格式規則識別新的敏感值
2. **覆蓋範圍**：處理 TextPart 文本、ContextPart 摘要和 ToolPart 輸入、輸出；容器中的字串逐項處理，不根據欄位名整體儲存和遮罩。
3. **內容替換**：原文中的敏感片段會替換為佔位符：
   - 當前 Session 的敏感值統一使用以下佔位符，以 Session ID 或其雜湊對映值標識會話：<code>&#123;&#123;ov_privacy:session:&#123;session_id&#125;:&#123;field_name&#125;&#125;&#125;</code>。
   - 若敏感片段與已登記的個人金鑰（credential）匹配，則優先使用其欄位佔位符，例如 <code>&#123;&#123;ov_privacy:alice:viking://~/privacy/credential/github#/values/pat&#125;&#125;</code>。
4. **寫盤結果**：匹配成功的片段以佔位符儲存，未匹配內容保持原樣；同一 Session 內重複發現的值複用欄位，已有佔位符保持原引用。

---

### 載入還原（讀取鏈路）

讀取 Session 訊息或外接工具輸出時，預設保留佔位符；顯式指定 `raw=true` 且 `restore=true` 時，`FSService.read` 會嘗試還原佔位符。

```
fs.read(uri)
  -> get_session_id_from_uri(uri, session_root)
  -> restore_session_content
    -> privacy.get_current(category, target_key)
    -> 還原正文中的引用
```

#### URI 匹配

當前支援還原當前使用者 Session 目錄下的以下檔案：

- `sessions/{session_id}/messages.jsonl`
- `sessions/{session_id}/history/archive_*/messages.jsonl`
- `sessions/{session_id}/tool-results/{id}/output.txt`

#### restore 規則

`restore_session_content` 的行為如下：

1. **content 中有佔位符，且 privacy value 存在且非空**

   -> 直接替換為對應值；工具輸入中的整值佔位符按原始 JSON 型別還原。

2. **content 中有佔位符，但 privacy value 缺失或為空**

   -> 保留佔位符不替換。

3. **content 中的佔位符指向其他使用者，或使用不屬於當前會話的 <code>&#123;&#123;ov_privacy:session:...&#125;&#125;</code>**

   -> 保留佔位符不替換。

> 還原隻影響讀取結果，不修改儲存檔案。引用跟隨當前生效配置，輪換欄位值或啟用其他版本後，歷史訊息下次讀取時也使用新的當前值。

---

## 與 CLI/API 的關係

- 管理面：通過 Privacy API/CLI 管理版本（查詢、寫入、回滾）
- 內容面：在 `read` 時通過傳入 `raw=true` 可自動恢復佔位符
- 兩者解耦：內容檔案負責佔位符，隱私服務負責敏感值與版本

PrivacySanitizer 不根據欄位名猜測敏感性。當前 active Privacy 中長度不少於 6 個 Unicode 字元的字串值會參與正文自動掃描與引用替換；更短的值仍可儲存、引用和顯式讀取，但不會參與全文替換，以降低普通正文誤命中。Python 負責目錄、引用和快取策略，匹配器構建、最長匹配與正文重寫由 `ragfs` 的 Rust Aho-Corasick 實現完成，並通過 PyO3 複用不可變 matcher、掃描時釋放 GIL。匹配目錄按使用者和本程序 revision 快取，本程序修改會立即失效，另外設有 3600 秒快取 TTL 以覆蓋多 worker/多節點修改。

上述按值匹配優先使用當前使用者的 `credential`；未命中時，僅使用當前 Skill 或 Session 中符合憑據格式的值，其他物件不參與匹配。匹配遵循詞邊界，並排除 `never_mask` 中的值。

以儲存 GitHub Personal Access Token（PAT）為例：

```bash
# 首次寫入或輪換 GitHub PAT；credential/github 是 target，pat 是 field
ov privacy upsert credential github --field-pat 'github_pat_...'

# 盤點當前目標和欄位，不暴露值
ov privacy tree --category credential --references

# target 只有 pat 一個欄位時可以省略 field
ov privacy reference credential github
ov privacy resolve credential github

# 顯式指定 field 的等價形式
ov privacy reference credential github pat
ov privacy resolve credential github pat
ov privacy resolve '{{ov_privacy:alice:viking://~/privacy/credential/github#/values/pat}}'

# 檢視/切換歷史版本，或刪除 pat 欄位（最後一個欄位刪除後 target 也會刪除）
ov privacy versions credential github
ov privacy activate credential github 1
ov privacy delete credential github pat --yes

# 掃描一個明確的 URI；預設僅報告，--fix 才會替換明文 PAT
ov privacy scan --uri viking://~/resources/project-a
```

---

## 設計收益

- 降低明文敏感資訊在技能正文中的暴露風險
- 為外部金鑰輪換後的配置切換保留版本記錄
- 對上層呼叫透明：`read (raw=true)` 可拿到還原後的可執行技能文本
- 對不完整配置提供可觀測提示，便於排障

---

## 相關文件

- [技能](../api/04-skills.md) - Skill 寫入與讀取 API
- [會話](../api/05-sessions.md) - Session 建立、訊息寫入
- [隱私配置 API](../api/10-privacy.md) - 隱私配置端點說明
- [上下文提取](./06-extraction.md) - 內容提取主流程
- [架構概述](./01-architecture.md) - 系統分層與模組關係
