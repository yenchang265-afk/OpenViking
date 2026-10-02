# 隱私配置與 Skill 隱私提取/載入

本文介紹 OpenViking 的隱私配置能力，以及它與 Skill 寫入（提取）和讀取（載入還原）的協作機制。

## 目標

隱私配置用於把敏感值（如 `api_key`、`token`、`base_url`）從技能正文中分離出來，避免明文長期儲存在 `SKILL.md` 中，同時保留版本化管理與回滾能力。

核心目標：

- 寫入時自動抽取敏感值並佔位符化
- 讀取時按當前生效配置自動還原
- 支援版本查詢、切換與審計

---

## 核心物件與儲存結構

隱私配置按二級鍵組織：`category + target_key`。

- `category`：配置類別（當前 Skill 使用 `skill`）
- `target_key`：目標標識（通常是 skill 名）

使用者空間下的儲存路徑：

```
viking://user/{user_space}/privacy/{category}/{target_key}/
├── .meta.json                 # 元信息（active_version/latest_version/labels 等）
├── current.json               # 當前生效版本快照
└── history/
    ├── version_1.json
    ├── version_2.json
    └── ...
```

`current.json` 與 `history/version_x.json` 都是完整快照（`values` 整包）。

---

## 版本語義

### upsert（寫入）

- 每次 upsert 都以傳入 `values` 作為“新快照候選”
- 如果與當前版本 `values` 完全一致，則不新建版本，直接返回當前版本
- 否則建立新版本並自動設為當前生效版本
- 允許新增 key（不會因“未知 key”報錯）

### activate（激活）

- 將歷史版本設定為當前生效版本（寫回 `current.json`）
- 更新 `.meta.json` 中的 `active_version`

---

## Skill 隱私提取（寫入鏈路）

當通過 `add_skill` 寫入 Skill 時，會走隱私提取與佔位符化流程。

```
add_skill
  -> SkillProcessor._sanitize_skill_privacy
    -> extract_skill_privacy_values (LLM 抽取 values)
    -> placeholderize_skill_content_with_blocks (明文替換為佔位符)
    -> privacy.upsert(category="skill", target_key=skill_name, values=...)
  -> 寫入佔位符化後的 SKILL.md
```

### 關鍵點

1. **抽取結果來源**：模型返回 JSON，讀取 `values` 欄位作為隱私鍵值。  
2. **內容替換**：原文中命中的敏感片段會替換為佔位符：
   - <code>&#123;&#123;ov_privacy:skill:&#123;skill_name&#125;:&#123;field_name&#125;&#125;&#125;</code>
3. **保留塊對映**：會同時記錄：
   - `original_content_blocks`
   - `replacement_content_blocks`
4. **寫盤結果**：`SKILL.md` 持久化的是佔位符內容，不是明文值。

---

## Skill 載入還原（讀取鏈路）

讀取 `SKILL.md` 時，`FSService.read` 會嘗試自動還原佔位符。

```
fs.read(uri)
  -> get_skill_name_from_uri(uri)
  -> privacy.get_current(category="skill", target_key=skill_name)
  -> restore_skill_content(content, skill_name, current.values)
```

### URI 匹配

當前支援通過後綴識別 Skill：`/skills/{name}/SKILL.md`，可相容 user-scoped skill 路徑，例如：

- `viking://~/skills/{name}/SKILL.md`
- `viking://user/{user_id}/skills/{name}/SKILL.md`

### restore 規則

`restore_skill_content` 的行為如下：

1. **content 中有佔位符，且 privacy value 存在且非空**  
   -> 直接替換為對應值。

2. **content 中有佔位符，但 privacy value 缺失或為空**  
   -> 保留佔位符不替換，並記入 `unresolved_entries`。

3. **privacy 中存在 key 且非空，但 content 中沒有對應占位符**  
   -> 記入“額外配置”提示（`Configured but not referenced in content`）。

4. 當存在 `unresolved_entries` 或“額外配置”時，會在內容末尾追加：
   - `[OpenViking Privacy Notice]`
   - `Related configured privacy values: ...`
   - `Not replaced (missing config): ...`（如有）
   - `Configured but not referenced in content: ...`（如有）

> 注意：當前實現中，僅當該 skill 已有 `current` 配置時才會進入 restore。若沒有當前配置，不會追加 notice。

---

## 與 CLI/API 的關係

- 管理面：通過 Privacy API/CLI 管理版本（查詢、寫入、回滾）
- 內容面：通過 `read` 自動恢復佔位符
- 兩者解耦：內容檔案負責佔位符，隱私服務負責敏感值與版本

常用命令：

```bash
openviking privacy categories
openviking privacy list skill
openviking privacy skill <target_key>
openviking privacy upsert skill <target_key> --values-json '{"api_key":"..."}'
openviking privacy activate skill <target_key> <version>
openviking read viking://user/default/skills/<target_key>/SKILL.md
```

---

## 設計收益

- 降低明文敏感資訊在技能正文中的暴露風險
- 通過版本化支援金鑰輪換與快速回滾
- 對上層呼叫透明：`read` 即可拿到還原後的可執行技能文本
- 對不完整配置提供可觀測提示，便於排障

---

## 相關文件

- [技能](../api/04-skills.md) - Skill 寫入與讀取 API
- [隱私配置 API](../api/10-privacy.md) - 隱私配置端點說明
- [上下文提取](./06-extraction.md) - 內容提取主流程
- [架構概述](./01-architecture.md) - 系統分層與模組關係
