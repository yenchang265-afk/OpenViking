# 隱私配置與自動管理

本文介紹 OpenViking 的隱私配置能力，以及它與技能/會話寫入（提取）和讀取（載入還原）的協作機制。

## 目標

隱私配置用於把敏感值（如 `api_key`、`token`）從內容（如技能、會話）中分離出來。被自動掃描的敏感資訊，儲存在 OpenViking 使用者空間的隱私配置中並保留版本記錄，內容則儲存佔位符，讀取時可根據當前生效配置還原。

核心目標：

- 寫入時自動提取敏感值並佔位符化
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

## 技能的隱私提取與讀取還原

### 自動提取（寫入鏈路）

當通過 `add_skill` 寫入 Skill 時，會走隱私提取與佔位符化流程。

```
add_skill
  -> SkillProcessor._sanitize_skill_privacy
    -> PrivacySanitizer（保護已登記的個人金鑰）
    -> extract_skill_privacy_values (LLM 抽取 values)
    -> placeholderize_skill_content_with_blocks (明文替換為佔位符)
    -> privacy.upsert(category="skill", target_key=skill_name, values=...)
  -> 寫入佔位符化後的 SKILL.md
```

#### 關鍵點

1. **抽取結果來源**：模型返回 JSON，讀取 `values` 欄位作為隱私鍵值。  
2. **內容替換**：原文中命中的敏感片段會替換為佔位符：
   - <code>&#123;&#123;ov_privacy:skill:&#123;skill_name&#125;:&#123;field_name&#125;&#125;&#125;</code>
3. **保留塊對映**：會同時記錄：
   - `original_content_blocks`
   - `replacement_content_blocks`
4. **寫盤結果**：匹配成功的片段以佔位符儲存，未匹配內容保持原樣。該流程處理技能正文，不等於掃描並清理所有附件。

---

### 載入還原（讀取鏈路）

讀取 `SKILL.md` 時，預設保留佔位符；顯式指定 `raw=true` 時，`FSService.read` 會嘗試還原佔位符。

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

`read` 返回的是還原後的值；“額外配置”提示也會包含配置值。Privacy API 和歷史快照同樣可以返回完整值，該功能不等於響應脫敏或儲存加密。需要加密儲存時，另見[儲存加密](./10-encryption.md)。

## 會話的隱私提取與讀取還原

### 自動提取（寫入鏈路）

向 Session 寫入訊息時，會在工具輸出外接和訊息落盤前，通過常見的規則，提取敏感值並替換為佔位符。

```
Session.add_messages_async
  -> extract_and_store_session_privacy
    -> PrivacySanitizer（保護已登記的個人金鑰）
    -> PrivacyExtractor（規則提取新值並佔位符化）
    -> privacy.insert_values(category="session", target_key=session_id, updates=...)
  -> 工具輸出外接
  -> 寫入佔位符化後的訊息
```

#### 關鍵點

1. **抽取結果來源**：通過固定的常見規則（不呼叫模型）識別敏感值，將結果作為隱私鍵值。
2. **覆蓋範圍**：處理 TextPart 文本、ContextPart 摘要和 ToolPart 輸入、輸出。工具輸入中，敏感欄位對應的值整體儲存和遮罩。
3. **內容替換**：原文中的敏感片段會替換為佔位符：
   - 當前 Session 的敏感值統一使用以下佔位符，以 Session ID 或其雜湊對映值標識會話：<code>&#123;&#123;ov_privacy:session:&#123;session_id&#125;:&#123;field_name&#125;&#125;&#125;</code>。
   - 若敏感片段與已登記的個人金鑰（credential）匹配，則優先使用唯一匹配欄位的佔位符，例如 <code>&#123;&#123;ov_privacy:alice:viking://~/privacy/credential/github#/values/pat&#125;&#125;</code>。
4. **寫盤結果**：匹配成功的片段以佔位符儲存，未匹配內容保持原樣。新提取的隱私值儲存在當前 Session 的配置中。

---

### 載入還原（讀取鏈路）

讀取 Session 訊息或外接工具輸出時，預設保留佔位符；顯式指定 `raw=true` 時，`FSService.read` 會嘗試還原佔位符。

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
- 內容面：通過 `read` 自動恢復佔位符
- 兩者解耦：內容檔案負責佔位符，隱私服務負責敏感值與版本

PrivacySanitizer 不根據欄位名猜測敏感性。當前 active Privacy 中長度不少於 6 個 Unicode 字元的字串值會參與正文自動掃描與引用替換；更短的值仍可儲存、引用和顯式讀取，但不會參與全文替換，以降低普通正文誤命中。Python 負責目錄、引用和快取策略，匹配器構建、最長匹配與正文重寫由 `ragfs` 的 Rust Aho-Corasick 實現完成，並通過 PyO3 複用不可變 matcher、掃描時釋放 GIL。匹配目錄按使用者和本程序 revision 快取，本程序修改會立即失效，另外設有 3600 秒快取 TTL 以覆蓋多 worker/多節點修改。

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
- 對上層呼叫透明：`read` 即可拿到還原後的可執行技能文本
- 對不完整配置提供可觀測提示，便於排障

---

## 相關文件

- [技能](../api/04-skills.md) - Skill 寫入與讀取 API
- [會話](../api/05-sessions.md) - Session 建立、訊息寫入
- [隱私配置 API](../api/10-privacy.md) - 隱私配置端點說明
- [上下文提取](./06-extraction.md) - 內容提取主流程
- [架構概述](./01-architecture.md) - 系統分層與模組關係
