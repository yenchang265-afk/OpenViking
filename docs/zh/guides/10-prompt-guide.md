# Business Data Platform Prompt 說明與自定義指南

本文介紹 Business Data Platform 當前的 prompt 模板體系，重點說明：

- 當前有哪些 prompt
- 它們分別用於哪個處理環節
- 它們會影響哪些對外能力或結果
- 模板檔案的格式要求是什麼
- 如何安全地自定義 prompt

本文只覆蓋 `openviking/prompts/templates/` 下的模板，以及少量與模板載入有關的配置項。

## 總覽

Business Data Platform 當前的 prompt 主要分為兩類：

1. 普通 prompt 模板
   - 存放在 `openviking/prompts/templates/<category>/*.yaml`
   - 用於給模型下發任務，例如做圖片理解、文件總結、記憶提取、檢索意圖分析等
2. memory schema 模板
   - 存放在 `openviking/prompts/templates/memory/*.yaml`
   - 用於定義某類記憶的欄位、檔名模板、內容模板和目錄規則

從使用角度看，這些模板主要服務於以下處理環節：

| 類別 | 代表模板 | 主要作用 | 生效環節 | 影響的對外能力 |
|------|----------|----------|----------|----------------|
| `vision` | `vision.image_understanding` | 圖片、頁面、表格理解 | 資源解析、掃描件理解 | 圖片解析、PDF 頁面理解、表格抽取結果 |
| `parsing` | `parsing.context_generation` | 文件結構劃分與節點語義生成 | 資源匯入與解析 | 文件章節結構、節點摘要、影像摘要 |
| `semantic` | `semantic.document_summary` | 檔案與目錄級摘要 | 語義索引構建 | 檔案摘要、目錄概覽、後續檢索質量 |
| `retrieval` | `retrieval.intent_analysis` | 檢索意圖分析與查詢規劃 | 檢索前分析 | 搜尋 query 規劃、上下文召回方向 |
| `compression` | `compression.ov_wm_v2` | 工作記憶壓縮與 session archive 摘要 | session commit / memory 管線 | session 壓縮質量和工作記憶質量 |
| `memory` | `profile` | 記憶型別定義 | 記憶落盤與更新 | 不同記憶型別的組織方式和最終內容 |
| `processing` | `processing.tool_chain_analysis` | 從互動或資源背景中提煉經驗 | 後處理與經驗沉澱 | 策略提煉、工具鏈經驗、互動學習結果 |
| `indexing` | `indexing.relevance_scoring` | 評估候選內容相關性 | 檢索與索引輔助 | 相關性打分質量 |
| `skill` | `skill.overview_generation` | 提煉 Skill 資訊 | Skill 資源處理 | Skill 檢索摘要 |
| `test` | `test.skill_test_generation` | 自動生成測試樣例 | 測試與驗證輔助 | Skill 測試樣例生成 |

## Prompt 格式要求

### 普通 Prompt YAML

普通 prompt 模板通常包含以下字段：

```yaml
metadata:
  id: "semantic.document_summary"
  name: "Document Summary"
  description: "Generate summary for documentation files"
  version: "1.0.0"
  language: "en"
  category: "semantic"

variables:
  - name: "file_name"
    type: "string"
    description: "Input file name"
    required: true

template: |
  ...

output_schema:
  ...

llm_config:
  ...
```

欄位含義：

- `metadata`
  - 描述模板身份與分類
  - 其中 `id` 通常與檔案路徑對應，例如 `semantic.document_summary`
- `variables`
  - 定義模板可接受的輸入變數
  - 常見欄位包括 `name`、`type`、`description`、`default`、`required`、`max_length`
- `template`
  - 真正傳送給模型的 prompt 正文
  - 使用 Jinja2 變數渲染
- `output_schema`
  - 可選
  - 用於描述期望輸出結構，方便呼叫方約束模型返回
- `llm_config`
  - 可選
  - 用於描述模型呼叫建議引數，不直接屬於 prompt 正文

編寫普通 prompt 時，建議遵守以下要求：

- `metadata.id` 與模板的類別和用途保持一致
- 變數名保持穩定，避免與呼叫方約定不一致
- `template` 中的佔位變數應與 `variables` 定義一致
- 如果模板要求結構化輸出，應明確寫清欄位、格式和約束
- 如果存在長度敏感輸入，應通過 `max_length` 或上游截斷控制 prompt 大小

### Memory Schema YAML

`memory/*.yaml` 不是普通 prompt 文本模板，而是記憶型別定義。下面是一個示意結構，用來說明常見欄位；實際內建模板是否包含 `content_template`、目錄是否帶子目錄，取決於具體 memory type。

```yaml
memory_type: "profile"
description: "User profile memory"
fields:
  - name: "content"
    type: "string"
    description: "Profile content"
    merge_op: "patch"
filename_template: "profile.md"
content_template: |
  ...
embedding_template: |
  ...
directory: "viking://user/{{ user_space }}/memories/..."
enabled: true
operation_mode: "upsert"
stage: "user"
peer_enabled: true
```

欄位含義：

- `memory_type`
  - 該記憶型別的名稱
- `description`
  - 對該類記憶的定義和提取要求
- `fields`
  - 該類記憶包含哪些欄位
- `filename_template`
  - 生成檔名時使用的模板
- `content_template`
  - 落盤時使用的正文模板
- `embedding_template`
  - 用於渲染參與語義檢索的向量化（embedding）文本的模板；未設定時使用預設表示
- `directory`
  - 該類記憶寫入的目錄
- `enabled`
  - 是否啟用該類記憶
- `operation_mode`
  - 該類記憶的更新模式，例如 `upsert`
- `stage`
  - 抽取階段。預設是 `user`，參與會話使用者記憶抽取；`agent` 用於 trajectories、experiences 這類執行派生 schema。
- `peer_enabled`
  - 當 `peer_id` 或訊息 ranges 指向某個 peer 時，是否將該類記憶按 peer 分目錄儲存。預設是 `true`；如果該類記憶必須保留在當前 user 目錄下，設定為 `false`。

編寫 memory schema 時，建議重點關注：

- 欄位粒度是否穩定
- 檔名模板是否可預測、可檢索
- 目錄規則是否符合預期檢索範圍
- 合併策略是否適合該類記憶

## 當前 Prompt 模板說明

下面按類別列出當前全部模板。每個條目都說明它用於哪個處理環節，以及主要影響哪類對外能力。

閱讀這一節時，可以用一個簡單規則：

- 普通 prompt 模板，重點看“作用”和“關鍵輸入”
- memory schema，重點看“作用”和“關鍵欄位”

### Compression

這一類 prompt 主要用於 session 壓縮和 working memory 更新。長期記憶抽取使用 `memory` 類別下的 v2 schema-driven memory templates。

- `compression.ov_wm_v2`
  - 生效環節：首次 working memory 生成階段
  - 影響能力：session archive 概覽和當前 working memory 質量
  - 作用：為 session 建立初始結構化 working memory 文件
  - 關鍵輸入：`messages`

- `compression.ov_wm_v2_update`
  - 生效環節：增量 working memory 更新階段
  - 影響能力：session archive 概覽和 working memory 連續性
  - 作用：基於 keep、update、append 操作更新已有 working memory 文件
  - 關鍵輸入：`previous_working_memory`、`messages`

- `compression.structured_summary`
  - 生效環節：session archive 摘要生成階段
  - 影響能力：歷史會話壓縮摘要、後續回顧和檢索效果
  - 作用：為歸檔後的 session 生成結構化摘要
  - 關鍵輸入：`latest_archive_overview`、`messages`

### Indexing

這一類 prompt 主要用於為檢索或索引輔助流程做相關性判斷。

- `indexing.relevance_scoring`
  - 生效環節：候選內容相關性評估階段
  - 影響能力：檢索結果排序、候選篩選質量
  - 作用：評估候選內容與使用者查詢之間的相關性
  - 關鍵輸入：`query`、`candidate`

### Memory

這一類 YAML 定義不同記憶型別的結構，不是單次推理 prompt。它們共同決定當前使用者或 Peer 的記憶如何落盤、如何更新、如何被後續檢索使用。

- `cases`
  - 生效環節：案例型記憶落盤與更新階段
  - 影響能力：可訓練、可評估的任務案例沉澱
  - 作用：定義具體任務輸入、評估標準和支撐證據
  - 關鍵欄位：`case_name`、`task_signature`、`input`、`rubric`、`evidence`

- `entities`
  - 生效環節：實體型記憶落盤與更新階段
  - 影響能力：人物、專案、組織、系統等實體資訊的長期儲存
  - 作用：定義命名實體及其屬性資訊的儲存結構
  - 關鍵欄位：`category`、`name`、`content`

- `events`
  - 生效環節：事件型記憶落盤與更新階段
  - 影響能力：事件回顧、帶時間線的資訊保留、對話敘事記錄
  - 作用：定義事件摘要、目標、時間範圍等結構化事件記憶
  - 關鍵欄位：`event_name`、`goal`、`summary`、`ranges`

- `experiences`
  - 生效環節：經驗型記憶落盤與更新階段
  - 影響能力：從任務結果中沉澱可複用指導
  - 作用：記錄持久的執行經驗及其替代的舊記憶
  - 關鍵欄位：`experience_name`、`content`、`supersedes`

- `identity`
  - 生效環節：agent identity 記憶落盤階段
  - 影響能力：agent 身份設定的長期一致性
  - 作用：定義 agent 的名字、形象、風格、自我介紹等身份欄位
  - 關鍵欄位：`name`、`creature`、`vibe`、`emoji`、`avatar`、`introduction`

- `preferences`
  - 生效環節：偏好型記憶落盤與更新階段
  - 影響能力：使用者偏好 recall 和後續個性化表現
  - 作用：定義不同主題下的使用者偏好記憶
  - 關鍵欄位：`user`、`topic`、`content`

- `profile`
  - 生效環節：使用者 profile 記憶落盤與更新階段
  - 影響能力：使用者畫像、工作背景、穩定屬性的長期儲存
  - 作用：定義“使用者是誰”這一類穩定資訊的儲存結構
  - 關鍵欄位：`content`

- `skills`
  - 生效環節：skill 使用記憶落盤與更新階段
  - 影響能力：skill 使用統計、經驗沉澱與推薦流程
  - 作用：定義 skill 使用次數、成功率、適用場景等資訊
  - 關鍵欄位：`skill_name`、`total_executions`、`success_count`、`fail_count`、`best_for`、`recommended_flow`

- `soul`
  - 生效環節：agent soul 記憶落盤階段
  - 影響能力：agent 核心邊界、連續性和長期人格穩定性
  - 作用：定義 agent 的核心真值、邊界、風格和連續性
  - 關鍵欄位：`core_truths`、`boundaries`、`vibe`、`continuity`

- `tools`
  - 生效環節：工具使用記憶落盤與更新階段
  - 影響能力：工具使用經驗、最佳引數、失敗模式沉澱
  - 作用：定義工具呼叫統計和工具使用經驗的儲存結構
  - 關鍵欄位：`tool_name`、`static_desc`、`call_count`、`success_time`、`when_to_use`、`optimal_params`

- `trajectories`
  - 生效環節：agent 軌跡型記憶落盤階段（`stage: agent`，僅追加）
  - 影響能力：agent 任務軌跡中可複用的操作契約沉澱——多步決策、工具呼叫、執行鏈路
  - 作用：定義"任務軌跡中提煉出哪些可複用的操作/契約"這一類軌跡型記憶
  - 關鍵欄位：`trajectory_name`、`outcome`、`retrieval_anchor`、`content`

### Parsing

這一類 prompt 主要用於把原始資源內容轉成適合檢索和理解的結構化節點、章節、摘要或影像概述。

- `parsing.chapter_analysis`
  - 生效環節：長文件章節劃分階段
  - 影響能力：文件章節結構、頁面組織效果
  - 作用：分析文件內容並劃分合理的章節結構
  - 關鍵輸入：`start_page`、`end_page`、`total_pages`、`content`

- `parsing.context_generation`
  - 生效環節：文件節點語義生成階段
  - 影響能力：節點 abstract/overview 質量、後續檢索匹配效果
  - 作用：為文本節點生成更短、更適合檢索的語義標題、abstract 和 overview
  - 關鍵輸入：`title`、`content`、`children_info`、`instruction`、`context_type`、`is_leaf`

- `parsing.image_summary`
  - 生效環節：影像節點摘要階段
  - 影響能力：圖片資源的語義概述和後續檢索效果
  - 作用：為影像內容生成簡潔摘要
  - 關鍵輸入：`context`

- `parsing.semantic_grouping`
  - 生效環節：語義分組與切分階段
  - 影響能力：文件節點粒度、內容塊切分質量
  - 作用：根據語義決定內容應該合併還是拆分
  - 關鍵輸入：`items`、`threshold`、`mode`

### Processing

這一類 prompt 主要用於從互動記錄、工具鏈和資源背景中提煉策略或經驗，不直接面向單次使用者問答，而是面向後處理和知識沉澱。

- `processing.interaction_learning`
  - 生效環節：互動後經驗提煉階段
  - 影響能力：可複用互動經驗、有效資源和成功 skill 的沉澱
  - 作用：從互動記錄中抽取可複用經驗
  - 關鍵輸入：`interactions_summary`、`effective_resources`、`successful_skills`

- `processing.strategy_extraction`
  - 生效環節：資源新增後策略提煉階段
  - 影響能力：資源背景意圖的結構化提煉和後續複用
  - 作用：從資源新增原因、指令和抽象資訊中提煉使用策略
  - 關鍵輸入：`reason`、`instruction`、`abstract`

- `processing.tool_chain_analysis`
  - 生效環節：工具鏈分析階段
  - 影響能力：工具組合模式識別、工具經驗沉澱
  - 作用：分析工具呼叫鏈並識別有價值的使用模式
  - 關鍵輸入：`tool_calls`

### Retrieval

這一類 prompt 主要用於檢索前理解使用者意圖，決定 query plan 和上下文型別。

- `retrieval.intent_analysis`
  - 生效環節：檢索前意圖分析階段
  - 影響能力：檢索 query 規劃、召回方向、不同 context 型別的搜尋質量
  - 作用：結合壓縮摘要、最近訊息和當前訊息生成檢索計劃
  - 關鍵輸入：`compression_summary`、`recent_messages`、`current_message`、`context_type`、`target_abstract`

### Semantic

這一類 prompt 主要用於檔案級和目錄級摘要生成，是語義索引構建的重要部分。

- `semantic.code_summary`
  - 生效環節：程式碼檔案摘要階段
  - 影響能力：程式碼檔案語義索引、程式碼檢索與理解結果
  - 作用：為程式碼檔案生成結構、函式、類和關鍵邏輯摘要
  - 關鍵輸入：`file_name`、`content`、`output_language`

- `semantic.document_summary`
  - 生效環節：文件檔案摘要階段
  - 影響能力：文件內容摘要、文件檢索與概覽效果
  - 作用：為 Markdown、Text、RST 等文件生成內容摘要
  - 關鍵輸入：`file_name`、`content`、`output_language`

- `semantic.file_summary`
  - 生效環節：通用檔案摘要階段
  - 影響能力：目錄索引與通用檔案檢索質量
  - 作用：為單個檔案生成摘要，作為目錄 abstract/overview 的上游輸入
  - 關鍵輸入：`file_name`、`content`、`output_language`

- `semantic.overview_generation`
  - 生效環節：目錄級概覽生成階段
  - 影響能力：目錄 overview、層級檢索與導航體驗
  - 作用：根據檔案摘要和子目錄 abstract 生成目錄級 overview
  - 關鍵輸入：`dir_name`、`file_summaries`、`children_abstracts`、`output_language`

### Skill

這一類 prompt 主要用於把 Skill 內容壓縮成適合檢索和複用的摘要。

- `skill.overview_generation`
  - 生效環節：Skill 內容處理階段
  - 影響能力：Skill 檢索摘要、Skill 發現效果
  - 作用：從 Skill 名稱、描述和正文中抽取關鍵檢索資訊
  - 關鍵輸入：`skill_name`、`skill_description`、`skill_content`

### Test

這一類 prompt 主要用於輔助生成測試樣例。

- `test.skill_test_generation`
  - 生效環節：Skill 測試輔助階段
  - 影響能力：Skill 場景測試設計與驗證樣例生成
  - 作用：根據多個 Skill 的名稱和描述生成測試用例
  - 關鍵輸入：`skills_info`

### Vision

這一類 prompt 主要用於圖片、頁面、表格和多模態文件分析，直接影響圖片解析和掃描件理解結果。

- `vision.batch_filtering`
  - 生效環節：多圖批次篩選階段
  - 影響能力：多圖文件理解中的圖片保留與忽略策略
  - 作用：批次判斷多張圖片是否值得納入文件理解
  - 關鍵輸入：`document_title`、`image_count`、`images_info`

- `vision.image_filtering`
  - 生效環節：單圖篩選階段
  - 影響能力：圖片是否進入後續理解流程
  - 作用：判斷單張圖片是否對文件理解有意義
  - 關鍵輸入：`document_title`、`context`

- `vision.image_understanding`
  - 生效環節：圖片理解階段
  - 影響能力：圖片解析結果、圖片 abstract/overview/detail_text 質量
  - 作用：使用 VLM 對圖片生成三層資訊
  - 關鍵輸入：`instruction`、`context`

- `vision.page_understanding`
  - 生效環節：掃描頁理解階段
  - 影響能力：掃描 PDF 頁面理解與後續語義化結果
  - 作用：理解單頁圖片化文件內容
  - 關鍵輸入：`instruction`、`page_num`

- `vision.page_understanding_batch`
  - 生效環節：多頁批次理解階段
  - 影響能力：批次掃描頁理解效率與結果一致性
  - 作用：批次理解多頁圖片化文件內容
  - 關鍵輸入：`page_count`、`instruction`

- `vision.table_understanding`
  - 生效環節：表格理解階段
  - 影響能力：圖片表格解析、表格摘要和結構理解
  - 作用：分析表格圖片並生成三層資訊
  - 關鍵輸入：`instruction`、`context`

- `vision.unified_analysis`
  - 生效環節：多模態統一分析階段
  - 影響能力：包含圖片、表格和章節的複雜文件解析結果
  - 作用：批次分析文件中的圖片、表格和章節資訊
  - 關鍵輸入：`title`、`instruction`、`reason`、`content_preview`、`image_count`、`images_section`、`table_count`、`tables_section`

## 如何自定義 Prompt

Business Data Platform 支援兩種主要的自定義方式：

1. 覆蓋普通 prompt 模板
2. 擴充 memory schema

在進入具體方法之前，可以先用下面的邊界判斷改動風險：

| 改動型別 | 風險級別 | 說明 |
|----------|----------|------|
| 改 prompt 措辭、補示例、調整語氣 | 低 | 通常隻影響模型表達方式，不改變呼叫方協議 |
| 改輸出風格、改抽取偏好、改摘要粒度 | 中 | 會影響結果分佈，需要重新驗證目標能力 |
| 改變數名、改輸出結構、改 memory 欄位名 | 高 | 容易和呼叫方或解析邏輯不相容 |
| 改 `directory`、`filename_template`、`merge_op` | 很高 | 會直接影響記憶儲存位置、組織方式和更新行為 |

### 覆蓋普通 Prompt 模板

適用場景：

- 想調整記憶提取偏好
- 想改變摘要風格
- 想讓圖片理解輸出更細或更簡
- 想調整檢索意圖分析的規劃方式

可用配置：

- `prompts.templates_dir`
- 環境變數 `OPENVIKING_PROMPT_TEMPLATES_DIR`

載入優先順序：

1. 顯式傳入的模板目錄
2. 環境變數 `OPENVIKING_PROMPT_TEMPLATES_DIR`
3. `ov.conf` 中的 `prompts.templates_dir`
4. 內建模板目錄 `openviking/prompts/templates/`

也就是說，普通 prompt 的自定義方式本質上是“優先從自定義目錄查詢，同路徑未命中時再回退到內建模板”。

推薦做法：

1. 先複製內建模板目錄中的目標檔案
2. 保持相同的類別目錄和檔名
3. 僅修改 prompt 正文或輸出要求
4. 儘量不要修改已被呼叫方依賴的變數名

示例目錄：

```text
custom-prompts/
├── compression/
│   └── ov_wm_v2.yaml
├── retrieval/
│   └── intent_analysis.yaml
└── semantic/
    └── document_summary.yaml
```

示例配置：

```json
{
  "prompts": {
    "templates_dir": "/path/to/custom-prompts"
  }
}
```

或者：

```bash
export OPENVIKING_PROMPT_TEMPLATES_DIR=/path/to/custom-prompts
```

影響面示例：

- 修改 `compression.ov_wm_v2`
  - 主要影響首次 working memory 生成
  - 最終影響 session archive 質量和後續 recall 效果
- 修改 `retrieval.intent_analysis`
  - 主要影響檢索前 query plan
  - 最終影響搜尋方向和召回效果
- 修改 `semantic.document_summary`
  - 主要影響文件摘要階段
  - 最終影響文件索引和摘要結果

### 擴充 Memory Schema

適用場景：

- 想新增一類業務記憶
- 想調整某類記憶的欄位結構
- 想改變記憶落盤目錄或檔案模板

可用配置：

- `memory.custom_templates_dir`

載入行為：

- 內建 memory schema 會先載入
- 如果配置了 `memory.custom_templates_dir`，再繼續載入自定義目錄中的 schema
- 因此，memory 自定義更接近“擴充和補充”，而不是完全替換整套內建模板

示例目錄：

```text
custom-memory/
├── project_decisions.yaml
└── user_preferences_ext.yaml
```

示例配置：

```json
{
  "memory": {
    "custom_templates_dir": "/path/to/custom-memory"
  }
}
```

擴充 memory schema 時建議：

- 優先參考現有 `memory/*.yaml` 寫法
- 先確定該類記憶是否真的需要獨立型別
- 保持欄位名清晰、可穩定更新
- 確保 `directory` 和 `filename_template` 易於檢索和維護

影響面示例：

- 新增 `project_decisions`
  - 影響記憶落盤型別和後續搜尋組織方式
- 修改 `preferences`
  - 影響使用者偏好類記憶的組織方式和 recall 顆粒度
- 修改 `tools`
  - 影響工具經驗沉澱和工具使用建議結果

### 自定義時的高風險改動

以下改動最容易破壞現有鏈路：

- 修改普通 prompt 的變數名
- 修改 prompt 的預期輸出結構，但未同步調整呼叫方解析邏輯
- 修改 memory schema 的關鍵欄位名
- 修改 `directory` 導致檢索範圍變化
- 修改 `filename_template` 導致歷史檔案組織方式變化
- 修改 `merge_op` 導致已有記憶更新策略變化

如果只是想最佳化效果，通常優先考慮這些低風險改法：

- 給 prompt 增加更明確的輸出示例
- 強化“該保留什麼、該忽略什麼”的規則
- 調整摘要粒度或表達風格
- 只改某一類 prompt，而不是同時改多類

保守做法是：

1. 先複製現有模板
2. 儘量只改指令內容和表達方式
3. 結構欄位最後再改
4. 每次只改一類 prompt，方便定位影響範圍

## 驗證與排查

修改 prompt 之後，建議按“模板是否命中”和“能力是否變化”兩層來驗證。

### 先驗證模板是否命中

檢查項：

- 自定義目錄是否配置正確
- 檔案路徑是否與原模板保持相同相對路徑
- YAML 格式是否有效
- 變數名是否和原模板一致

如果是普通 prompt，重點確認：

- 模板是否被正確載入
- 目標環節是否真的使用了該模板

如果是 memory schema，重點確認：

- 新 schema 是否被成功載入
- 目標記憶型別是否真的參與了提取和落盤

### 再驗證對外結果是否變化

從使用者角度驗證最有效：

- 如果改的是 `vision` 類別範本，就重新解析圖片、表格或掃描 PDF，看結果是否變化
- 如果改的是 `semantic` 或 `parsing` 類別範本，就重新匯入文件或檔案，看摘要和結構是否變化
- 如果改的是 `retrieval` 類別範本，就重新執行相關搜尋，看 query 規劃和召回效果是否變化
- 如果改的是 `compression` 類別範本，就重新觸發 session commit 或 memory 處理流程，看記憶抽取和合並結果是否變化
- 如果改的是 `memory` 類 schema，就檢查最終落盤的記憶檔案內容、目錄和欄位結構是否符合預期

### 常見排查思路

現象與優先檢查項：

| 現象 | 優先檢查 |
|------|----------|
| 修改後結果完全沒變 | 自定義目錄未生效，或檔案路徑不匹配 |
| 模型報缺少變數 | 模板變數名與呼叫方不一致 |
| 返回內容格式錯亂 | prompt 輸出格式改了，但下游解析還按舊結構處理 |
| 新 memory 型別沒有出現 | `memory.custom_templates_dir` 未生效，或 schema 未被正確載入 |
| 檢索結果變差 | `retrieval`、`semantic` 或 `compression` 類 prompt 改得過於激進 |

## 附錄

### 模板目錄

內建 prompt 模板目錄：

```text
openviking/prompts/templates/
```

其中：

- `compression/`：壓縮、提取、合併
- `indexing/`：相關性評估
- `memory/`：記憶型別定義
- `parsing/`：結構分析與語義節點生成
- `processing/`：經驗與策略提煉
- `retrieval/`：檢索意圖分析
- `semantic/`：檔案和目錄摘要
- `skill/`：Skill 摘要
- `test/`：測試樣例生成
- `vision/`：圖片、頁面、表格理解

### 關鍵配置項

與 prompt 自定義相關的配置主要有：

| 配置項 | 用途 |
|--------|------|
| `prompts.templates_dir` | 指定普通 prompt 模板覆蓋目錄 |
| `OPENVIKING_PROMPT_TEMPLATES_DIR` | 通過環境變數指定普通 prompt 模板覆蓋目錄 |
| `memory.custom_templates_dir` | 指定 custom memory schema 目錄 |

### 選型建議

如果你的目標是：

- 改模型“怎麼說、怎麼提取、怎麼總結”
  - 優先改普通 prompt 模板
- 改“記憶長什麼樣、存在哪裡、怎麼組織”
  - 優先改 memory schema

如果不確定該改哪一層，先問自己一句：

“我要改的是模型的指令，還是最終記憶檔案的結構？”

這個問題通常足以幫助你區分應該改普通 prompt 還是 memory schema。
