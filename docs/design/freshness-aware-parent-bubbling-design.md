# 設計草案：基於 Freshness 的上級摘要冒泡策略

狀態：討論稿

關聯 RFC：`docs/design/l0-l1-okf-sidecars-rfc.md`

## 摘要

本文繼續細化 L0/L1 OKF sidecar RFC 中的 `Freshness-Aware Parent Bubbling`。目標是在不引入複雜排程基礎設施、不擴大 freshness 資料模型的前提下，減少沒有實際收益的上級摘要生成、模型呼叫和逐級寫放大。

首版策略只做兩層判斷：

1. 子目錄摘要完成後，先判斷父目錄實際使用的子目錄 L0 正文是否發生變化；如果 L0 未變，停止冒泡。
2. 如果 L0 確實變化，則小目錄立即重新整理；寬目錄只累計現有的 `pending_child_changes`，變化比例達到閾值後再重新整理。檔案的新增、刪除和修改在這裡統一視為一次直接子項變化。

對於寬目錄，取樣只是一次摘要生成過程中的有界輸入手段，不是一個需要持久化、追蹤或參與排程判斷的“取樣成員集合”。

首版不提供最長陳舊時間兜底，不維護唯一變化子項集合，也不調整現有 freshness 欄位的定義。它是一套務實的成本控制策略，而不是嚴格的即時一致性協議。

## 當前實現與四個具體問題

當前 resource/skill 語義任務成功後，會執行以下流程：

1. 將父目錄 sidecar 的 `pending_child_changes` 加一。
2. 立即為父目錄入隊一次非遞迴語義重新整理。
3. 父目錄重新整理成功後，對更上一級重複同樣的流程。

這個實現簡單，但存在四個值得明確的問題。

### 1. 子目錄 L0 未變時仍然冒泡

父目錄生成摘要時，消費的是直接子目錄的 L0 正文，而不是子目錄 L1，也不是 sidecar metadata。

如果子目錄重新生成後只有 L1 或 metadata 發生變化，而 L0 正文沒有變化，那麼父目錄的實際輸入沒有改變。此時仍然重新整理父目錄屬於無效冒泡。

這是首版最應優先解決的問題，因為判斷依據明確、實現成本低，而且每一級目錄都可以獨立停止繼續向上傳播。

### 2. `pending_child_changes` 統計的是事件次數

當前實現對每次觀察到的變化執行整數累加。因此，同一個熱點子目錄連續變化十次，會被計為十次 pending change，而不是一個發生變化的直接子項。

這與“唯一變化直接子項數”的理想語義並不完全一致。不過，OpenViking 中常規檔案變化頻率並不高；即使偶爾出現熱點連續變化，它最多讓目錄更早達到重新整理閾值，不會讓摘要比現在更陳舊。

因此，首版有意容忍這個近似：

- 不持久化 changed child key；
- 不對跨事件的同一 URI 去重；
- 不引入集合截斷、雜湊衝突或額外 metadata；
- 繼續將 `pending_child_changes` 當作簡單的變化事件計數使用。

一次批次請求內部仍可對重複 URI 做自然去重，但不建立跨請求的唯一子項狀態。

### 3. 取樣發生在子項摘要工作之後

當前目錄語義樹會先生成或讀取所有直接子項的摘要，最後才使用 `overview_sample_limit` 選出進入父目錄 overview prompt 的部分輸入。

這能夠限制 prompt 大小，卻沒有避免未參與本次聚合的子項摘要工作。對於寬目錄，如果我們的目標是降低重新摘要成本，就應當在排程本輪父目錄聚合所需的子項摘要之前完成有界取樣。

這裡的取樣是本輪生成過程中的臨時決策，不形成持久化的“當前取樣成員”概念，也不參與是否立即重新整理的判斷。

### 4. 僅使用變化比例可能長期不重新整理

例如，一個包含 161 個直接子項的目錄始終只有 3 個檔案發生變化，那麼它可能長期達不到 10% 的重新整理閾值。

這是比例閾值的已知取捨。首版不為此引入最長陳舊時間、定時掃描、延遲訊息或 dirty-directory registry，原因是這些機制會顯著擴大實現和運維複雜度，而當前場景中的預期收益有限。

在沒有後續變化的情況下，目錄可以通過顯式重新整理、重新匯入或其他自然語義任務獲得更新。是否需要時間兜底，應在上線觀察真實 pending 分佈後再決定，先不討論。

## 設計原則

- 比較父目錄真正消費的語義輸入，而不是比較包含 metadata 的原始 sidecar 位元組。
- 子目錄向上冒泡時，只以 L0 正文變化作為語義訊號。
- 檔案新增、刪除和修改對於寬目錄閾值統計是等價的。
- 不把“是否屬於上次 sample”作為排程條件。
- 不持久化變化子項集合，只累計簡單計數。
- 不改變現有 freshness 的四個欄位及其基本含義。
- 顯式重新整理、首次匯入和同步等待應保持可預測，不應被自動閾值靜默延遲。
- 檔案自身的解析、摘要和向量維護，與目錄聚合摘要是否延遲分開處理。
- 首版複用現有持久佇列、路徑鎖和 coalesce 機制，不新增時間排程系統。

## 非目標

首版明確不解決以下問題：

- 不保證 pending change 在固定時間內一定被聚合。
- 不精確統計唯一變化的直接子項數。
- 不記錄或維護某個目錄的持久化取樣成員集合。
- 不根據新增、刪除、修改設定不同權重。
- 不根據檔案大小、型別或摘要差異程度計算加權變化率。

## 保持現有 Freshness 模型

繼續使用 RFC 已定義的欄位：

```yaml
freshness:
  total_entries: 161
  sampled_entries: 32
  unsampled_entries: 129
  pending_child_changes: 3
```

欄位解釋保持不變：

- `total_entries`：上一次成功生成目錄摘要時觀察到的直接子項總數。
- `sampled_entries`：上一次生成實際使用的直接子項數量。
- `unsampled_entries`：上一次生成未取樣的直接子項數量。
- `pending_child_changes`：上一次生成完成後，已知發生變化、但尚未反映到當前正文中的直接子項數。

上述欄位定義不變。首版只是在實現上使用輕量的事件累加來近似維護 `pending_child_changes`，暫不對跨事件的同一直接子項去重。因此實際計數可能被重複事件保守高估。該近似只用於判斷變化規模是否值得觸發一次父目錄重新整理，不應被當作精確審計資料。

新增和刪除可能使當前真實直接子項數與 `total_entries` 暫時不一致。首版仍使用上一次成功生成記錄的 `total_entries` 作為閾值分母；下一次成功重新整理會重新列目錄並修正這些計數。

## 語義變化判斷

### 子目錄變化

子目錄語義任務開始前讀取舊 L0 body，生成完成後取得新 L0 body，對規範化正文計算 digest：

```text
old_l0_digest = hash(normalize(old_l0_body))
new_l0_digest = hash(normalize(new_l0_body))
```

digest 不包含：

- YAML frontmatter；
- freshness；
- source；
- generated_by；
- 檔案修改時間或其他儲存屬性。

決策規則：

- 新舊 L0 digest 相同：不標記父目錄 pending，不為父目錄入隊，冒泡在當前層終止。
- 新舊 L0 digest 不同：向父目錄上報一次普通的 direct-child change。
- 舊 L0 不存在或無法可靠解析：保守地視為發生變化。

L1 是否變化只決定當前目錄自己的寫回或向量維護，不決定是否繼續向祖先冒泡。

### 直接檔案變化

對於直接檔案，新增、刪除和修改都向所在目錄貢獻變化計數。首版不要求在入隊前比較新舊檔案摘要，因為這樣會把語義生成工作前移到排程判斷階段，抵消低成本策略的收益。

一次批次操作中有多少個不同的 changed URI，就對本輪 pending 增加多少；後續獨立事件再次修改同一個 URI，可以再次累加。

## 排程決策

策略輸出只有三種：

```text
NOOP
MARK_PENDING
REFRESH_NOW
```

建議按以下順序判斷：

| 條件 | 決策 | 說明 |
| --- | --- | --- |
| 子目錄新舊 L0 正文相同 | `NOOP` | 父目錄實際輸入沒有變化 |
| 父目錄不存在有效 sidecar | `REFRESH_NOW` | 沒有可繼續使用的摘要基線 |
| 首次匯入或顯式語義重新整理 | `REFRESH_NOW` | 保持呼叫者意圖 |
| 父目錄上次記錄的 `total_entries <= overview_sample_limit` | `REFRESH_NOW` | 小目錄變化後直接重新整理 |
| 寬目錄累計變化率低於閾值 | `MARK_PENDING` | 只更新 freshness，不入隊 |
| 寬目錄累計變化率達到閾值 | `REFRESH_NOW` | 入隊一次有界父目錄重新整理 |

這裡沒有以下特殊規則：

- sampled child 變化不要求立即重新整理；
- 新增導致本輪臨時 sample 變化不要求立即重新整理；
- 刪除導致本輪臨時 sample 變化不要求立即重新整理；
- 目錄變化和檔案變化不設定不同閾值。

對於寬目錄，所有增刪改都只是 `pending_child_changes` 的增量。

## 寬目錄閾值

繼續用 `semantic.overview_sample_limit` 區分小目錄和寬目錄，當前預設值為 32。

首版只新增一個比例配置：

```yaml
semantic:
  overview_sample_limit: 32
  freshness_refresh_ratio: 0.10
```

寬目錄的判斷為：

```text
pending_after = pending_before + current_change_count
change_ratio = pending_after / max(total_entries, 1)

refresh_now = change_ratio >= freshness_refresh_ratio
```

等價的整數閾值為：

```text
refresh_threshold = ceil(freshness_refresh_ratio * total_entries)
```

示例：

| 上次記錄的直接子項數 | 10% 閾值 |
| ---: | ---: |
| 33 | 4 |
| 161 | 17 |
| 1000 | 100 |

首版不額外設定最小變化數或最大變化數，以減少配置項並保持“變化比例”含義直觀。如果真實執行資料顯示超寬目錄等待過久或一次重新整理積壓過多，再考慮增加上限。

由於熱點子項可重複累計，閾值可能比真實的唯一檔案變化率更早達到。這是有意接受的保守偏差：它可能多觸發一次重新整理，但不會讓目錄更久不重新整理。

程式碼實現時注意將公式的上述解釋註釋到程式碼。

## 達到閾值後的重新整理方式

寬目錄達到閾值後，不應只攜帶“最後一次變化的 URI”執行普通增量重新整理。此前被延遲的變化沒有持久化 URI 集合，僅保留了計數；只處理最後一次變化會遺漏先前事件。

因此，閾值觸發的任務應被定義為一次當前目錄的有界完整聚合：

1. 重新列舉當前直接子項。
2. 根據 `overview_sample_limit` 選出本輪有界輸入。
3. 為本輪選中的輸入讀取或生成當前摘要。
4. 生成新的 L1，並從 L1 正文提取 L0。
5. 寫入最新的 `total_entries`、`sampled_entries` 和 `unsampled_entries`。
6. 消費本輪重新整理開始時已經觀察到的 pending 計數。

這裡的“完整”是指從當前目錄狀態重新開始一次聚合決策，不是讀取寬目錄中的全部檔案內容。實際進入目錄摘要的輸入仍受 `overview_sample_limit` 限制。

每次重新整理都可以根據當時的目錄狀態重新進行確定性取樣。系統不記錄“上次 sample 中有哪些成員”，排程器也不基於 sample membership 做判斷。

## 將取樣前移

為了讓寬目錄閾值真正降低成本，應把本輪目錄聚合取樣前移到昂貴工作之前：

```text
列舉直接子項
  -> 確定本輪有界 sample
  -> 只為本輪聚合準備 sample 所需的摘要輸入
  -> 生成目錄 L1/L0
```

取樣演算法只需要滿足兩個條件：

- 對同一個穩定目錄重複執行時結果確定；
- 能夠覆蓋目錄中不同位置的子項，而不是永遠只取前 32 個。

可以繼續使用現有的確定性保序取樣。是否改成雜湊取樣不屬於 freshness 冒泡首版的必要條件，因為我們不再賦予 sample membership 排程語義。

必須區分兩類工作：

- 文件自身的解析、摘要或向量更新；
- 檔案摘要作為輸入參與父目錄 L1/L0 聚合。

父目錄聚合被延遲或採樣，不能導致發生變化的檔案失去自身應有的向量維護。取樣前移只減少為“生成目錄摘要”而進行的額外工作。

## Sidecar 寫回結果

當前 sidecar 寫回只返回成功與否，無法區分正文變化和 metadata 變化。建議返回結構化結果：

```python
AbstractOverviewWriteResult(
    wrote=True,
    overview_body_changed=True,
    abstract_body_changed=False,
)
```

語義如下：

- `wrote`：是否成功完成寫回流程；
- `overview_body_changed`：L1 可見正文是否改變；
- `abstract_body_changed`：L0 可見正文是否改變。

metadata 從 `pending_child_changes > 0` 重置或減少，也可能造成 raw sidecar 變化，但這種變化不應被視為 L0/L1 語義變化。

後續行為：

- L0 正文改變：可以向父目錄上報一次變化；
- 只有 L1 正文改變：只處理當前目錄自己的寫回和向量維護；
- L0/L1 正文都未改變：不需要重新向量化正文，也不繼續冒泡；
- 只有 freshness 改變：只寫 metadata。

### 標記和決策

在 sidecar exact-path lease 下：

1. 讀取當前 `pending_child_changes`。
2. 加上本次 `current_change_count`。
3. 寫回新計數。
4. 基於寫回後的計數和現有 `total_entries` 做閾值判斷。
5. 釋放 lease 後再執行 enqueue。

這樣 metadata 更新和排程判斷來自同一個一致快照。併發事件即使同時到達，也不會簡單覆蓋彼此的計數。

## API 語義

以下操作預設繞過寬目錄閾值，立即重新整理：

- 首次資源匯入；
- reindex 等觸發的顯式語義重新整理；

普通後臺檔案變化可以被閾值延遲。如果一次操作只更新 freshness 而沒有入隊目錄摘要，返回結果應明確表達：

```json
{
  "semantic_status": "deferred",
  "semantic_root_uri": "viking://resources/example"
}
```

此時檔案自身的向量維護狀態應單獨表達，不能因為目錄摘要被延遲就返回整體 `complete` 或錯誤地聲稱已經 `queued`。

## 實現邊界

保持 `SemanticProcessor` 是 resource、skill 和 memory 語義處理的統一入口，不引入新的頂層 processor。

建議職責劃分如下：

| 位置 | 職責 |
| --- | --- |
| `openviking/storage/queuefs/semantic_ops/freshness_policy.py` | 純粹的 `NOOP` / `MARK_PENDING` / `REFRESH_NOW` 判斷 |
| `openviking/storage/semantic_sidecar.py` | 在 lease 下原子累加、讀取和消費現有 freshness 計數 |
| `SemanticTreeExecutor` | 在寬目錄聚合前完成本輪取樣，並返回 L0/L1 正文變化結果 |
| `SemanticProcessor` | 根據 L0 是否變化決定是否繼續向父目錄冒泡 |
| content write、delete、resource 路徑 | 將檔案增刪改統一記錄為所在目錄的變化計數 |

不新增 maintenance service、定時 sweep、延遲佇列或 dirty-directory registry。

### 取樣前移

- 寬目錄在生成子項聚合輸入前完成取樣。
- 未進入本輪目錄 sample 的子項不會僅為父目錄聚合而產生額外摘要呼叫。
- 發生變化的檔案仍然完成自身需要的向量維護。
- 穩定目錄重複重新整理產生確定性的取樣結果。

### API 行為

- 自動延遲返回 `semantic_status: deferred`。
- 實際入隊返回 `queued`，同步完成返回 `complete`。
- 目錄聚合延遲與檔案自身向量狀態可以被呼叫方區分。

## 示例

假設一個目錄上次生成時有 161 個直接子項，`overview_sample_limit=32`，重新整理比例為 10%。

1. 子目錄 `a/` 完成語義生成，但新舊 L0 相同：不修改父目錄 freshness，也不繼續冒泡。
2. 檔案 `x.md`、`y.md` 和 `z.md` 發生修改：`pending_child_changes` 變為 3，低於閾值 17，不重新整理目錄摘要。
3. `x.md` 後續又被修改十次：pending 可以累計到 13。首版不做跨事件去重。
4. 再發生四次任意直接子項增刪改後，pending 達到 17，觸發一次父目錄重新整理。
5. 重新整理重新列舉當前目錄並選擇本輪最多 32 個輸入，不關心這些輸入是否屬於某個歷史 sample。
6. 重新整理開始時捕獲 pending snapshot；執行期間新增的變化計數會在寫回後保留。
7. 如果重新整理後的父目錄 L0 仍然未變，則冒泡在父目錄停止，不再重新整理祖父目錄。
8. 如果目錄長期停留在 3 個 pending 且沒有其他自然重新整理，首版允許它繼續保持這一 freshness 狀態。
