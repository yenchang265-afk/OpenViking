# 上下文層級（L0/L1/L2）

OpenViking 使用三層資訊模型，在檢索效率、導航能力和原始內容完整性之間取得平衡。

## 概覽

| 層級 | 名稱 | 儲存形式 | 預設正文上限 | 用途 |
| --- | --- | --- | --- | --- |
| **L0** | 摘要 | 目錄內的 `.abstract.md` | 256 字元 | 向量檢索、快速過濾 |
| **L1** | 概覽 | 目錄內的 `.overview.md` | 4000 字元 | Rerank、內容導航 |
| **L2** | 詳情 | 原始檔案和子目錄 | 無統一上限 | 完整內容、按需載入 |

L0/L1 是**目錄級語義 sidecar**。它們描述一個目錄，不是為每個普通檔案建立的同名伴生檔案。檔案摘要會作為輸入，聚合到所在目錄的 L1 中。

L0 和 L1 通常成對生成，但系統允許只存在其中一個。例如，`mkdir()` 會先建立 L0：未傳入 `description` 時使用目錄名作為預設正文，傳入後使用該說明。因此只有 `.abstract.md` 的目錄也是合法狀態。讀取和向量重建只處理實際存在的層級。

正文上限由 `semantic.abstract_max_chars` 和 `semantic.overview_max_chars` 配置；上表是預設值。限制只作用於 Markdown 正文，不會截斷 sidecar 後設資料。

## L0：摘要

L0 是目錄內容的最精簡表示，用於向量召回和快速相關性判斷。

```markdown
API 認證指南，涵蓋 OAuth 2.0、JWT 令牌和 API 金鑰的安全訪問方式。
```

通過語義 accessor 讀取時，只返回可見正文：

```python
abstract = client.abstract(uri="viking://resources/docs/auth")
```

## L1：概覽

L1 提供更完整的目錄摘要和導航資訊，用於 Rerank 和決定是否繼續載入 L2。

```markdown
# 認證指南

本目錄介紹 API 的主要認證方式。

## 快速導航

- `oauth.md`：OAuth 2.0 流程和程式碼示例
- `jwt.md`：令牌生成和驗證
- `api-keys.md`：API Key 認證
```

```python
overview = client.overview(uri="viking://resources/docs/auth")
```

L0 從 L1 正文中提取：取 H1 標題之後、第一個 `##` 標題之前的 Brief Description 段落。YAML frontmatter 不參與提取。

## L2：詳情

L2 是原始檔案或解析後的完整內容，只在需要時載入，並保留源格式和結構。

```python
content = client.read(uri="viking://resources/docs/auth/oauth.md")
```

## 目錄結構

一個已完成語義處理的目錄通常如下：

```text
viking://resources/docs/auth/
├── .abstract.md          # L0，隱藏的目錄級 sidecar
├── .overview.md          # L1，隱藏的目錄級 sidecar
├── oauth.md              # L2，完整內容
├── jwt.md                # L2，完整內容
└── api-keys.md           # L2，完整內容
```

普通 `ls` 預設隱藏 `.abstract.md` 和 `.overview.md`。它們不一定同時存在；不要依賴“每個目錄始終具有兩個 sidecar”的假設。

## OKF sidecar 格式

新生成的 L0/L1 使用最小 OKF Markdown：YAML frontmatter 加可見 Markdown 正文。

```markdown
---
directory: viking://resources/docs/auth/
source:
  kind: http
  uri: https://example.com/auth.pdf
generated_by:
  component: SemanticProcessor
  trigger: resource_ingest
freshness:
  total_entries: 3
  sampled_entries: 3
  unsampled_entries: 0
  pending_child_changes: 0
---

API 認證指南，涵蓋 OAuth 2.0、JWT 令牌和 API 金鑰。
```

初始後設資料欄位如下：

| 欄位 | 含義 |
| --- | --- |
| `directory` | sidecar 所描述的目錄 URI |
| `source` | 可選的匯入來源；通常只記錄在匯入根目錄 |
| `generated_by` | 生成元件和粗粒度觸發原因 |
| `freshness` | 直接子項覆蓋率和已知的待重新整理變化 |

已知欄位會進行 schema 校驗。未知頂層欄位或已知物件中的未知巢狀欄位會被靜默丟棄，不會進入 preview、embedding、canonical writeback 或 metadata 防寫比較。沒有 frontmatter 的舊 sidecar 繼續作為 legacy Markdown 讀取；YAML 損壞、缺少必填 `directory` 或已知欄位型別錯誤仍會顯式失敗。

## 不同讀取表面的行為

同一個 sidecar 在不同表面返回不同檢視：

| 訪問方式 | 返回內容 |
| --- | --- |
| `abstract()` / `overview()` | 僅 Markdown 正文 |
| `find`、search/rerank preview | 僅 Markdown 正文 |
| `ls output=agent`、tree agent 輸出 | 僅 Markdown 正文 |
| 直接 `read(".../.abstract.md")` | 原始 frontmatter 和正文 |
| 普通 `ls` | 預設不列出隱藏 sidecar |

語義生成父目錄摘要時也只讀取子目錄 L0 的正文，`source`、`generated_by` 和 `freshness` 不會進入總結 prompt。

## Embedding 後設資料白名單

L0/L1 的 embedding 輸入由正文和顯式白名單後設資料組成。當前白名單隻有 `directory`：

```markdown
---
directory: viking://resources/docs/auth/
---

API 認證指南，涵蓋 OAuth 2.0、JWT 令牌和 API 金鑰。
```

`source`、`generated_by`、`freshness` 以及未知欄位都不會進入 embedding。正常向量化和 admin `vectors_only` reindex 使用相同策略，避免重建索引後改變檢索輸入。L1 的 rerank scalar 仍然是純 L1 正文。

## Freshness 與穩定取樣

`freshness` 統計當前目錄的**直接子項**，而不是整個遞迴子樹：

- `total_entries`：參與目錄語義的直接檔案和直接子目錄總數。
- `sampled_entries`：本輪實際用於總結的直接子項數。
- `unsampled_entries`：未取樣的直接子項數，滿足 `sampled + unsampled = total`。
- `pending_child_changes`：尚未反映到當前正文中的直接子項變化事件數（同一子項重複變化會分別計數）。

當直接子項超過 `semantic.overview_sample_limit`（預設 32）時，系統使用確定性、保序的穩定取樣。相同目錄樹重複重新整理會選擇相同樣本，避免無意義的正文和 Git diff 抖動。

`pending_child_changes > 0` 表示正文仍然可讀，但已知落後於下層變化。父目錄重新整理成功後，該值會隨新的覆蓋率後設資料重置為 0。

resource/skill 的父目錄重新整理已使用 freshness 決策。子目錄 L0 正文不變時，不觸發向上傳播。正文變化後，若父目錄沒有 freshness 基線，或直接子項數不超過 `semantic.overview_sample_limit`，則立即安排重新整理。更大的目錄會累計 `pending_child_changes`，其與 `total_entries` 的比值達到 `semantic.freshness_refresh_ratio`（預設 `0.10`）時才重新整理。手動重新整理或匯入僅對請求的根目錄跳過閾值，不會強制重新整理所有祖先。傳播止於 namespace 根邊界。未達閾值時父目錄仍可讀，但保留 pending 狀態；閾值策略不承諾定時重新整理。

## 防寫

L0/L1 正文可以通過公共 `write` / `batch_write` 更新，但 metadata 受保護：

- 目標 sidecar 必須已存在；公共 API 不允許直接建立新的 `.abstract.md` / `.overview.md`。
- 只提交正文時，系統保留現有 metadata 並重新拼回 canonical OKF。
- 提交完整 OKF 時，已知 metadata 必須與現有值一致；修改受保護欄位會失敗。
- 未知 metadata 欄位會靜默丟棄。
- `append` 只追加正文，不會把使用者內容追加到 frontmatter。
- 正文更新只重建該目錄實際存在的 L0/L1 向量，不觸發語義重新生成，避免剛寫入的正文被覆蓋。

## 生成機制

SemanticProcessor 自底向上處理目錄：

```text
檔案摘要 → 葉子目錄 L1 → 葉子目錄 L0 → 父目錄 → namespace 根邊界
```

子目錄 L0 被聚合到父目錄 L1。Memory 目錄也通過統一的 SemanticProcessor 入口處理，但當前父級冒泡邏輯只用於 resource/skill。多模態檔案會先生成文本摘要，再作為普通檔案摘要參與其所在目錄的 L0/L1；不會為每個圖片、音訊或影片建立 per-file L0/L1 sidecar。

## 最佳實踐

| 場景 | 推薦層級 |
| --- | --- |
| 快速相關性檢查 | L0 |
| 理解目錄內容範圍 | L1 |
| 詳細資訊提取 | L2 |
| 為 LLM 構建初步上下文 | L1，必要時再載入 L2 |
| 檢查 sidecar 來源或 freshness | 直接讀取 sidecar 原始內容 |

## 相關文件

- [架構概述](./01-architecture.md) - 系統整體架構
- [上下文型別](./02-context-types.md) - 三種上下文型別
- [Viking URI](./04-viking-uri.md) - URI 規範
- [上下文提取](./06-extraction.md) - L0/L1 生成流程
- [檢索機制](./07-retrieval.md) - 檢索流程詳解
