# pgvector 目錄過濾索引最佳化

pgvector 的目錄過濾使用租戶條件和歸一化 URI 範圍。百萬行實測中，普通
`uri` 索引沒有被用於這些目錄範圍查詢：即使目錄只命中約百行，查詢仍先掃描
整個租戶的候選。與查詢表示式一致的 B-tree 複合索引可以顯著減少小目錄和
空目錄的掃描成本；對覆蓋整個租戶的範圍，收益有限。

本文記錄索引方案與實測依據。**當前後端不會自動建立這個表示式索引**；
它只在隔離壓測 collection 上驗證過，測試結束隨表刪除。基礎配置與能力邊界
見 [PostgreSQL + pgvector](25-pgvector.md)。

## 目錄過濾如何執行

`PathScope("uri", "viking://resources/g00/d000", depth)` 在 path 欄位上轉換為
`/resources/g00/d000` 範圍，並與 `account_id`、`level`、ACL 等條件一起編譯為
引數化 SQL。`level=0/1/2` 分別對應 L0 摘要、L1 概覽、L2 內容；它與路徑深度
是兩個獨立條件。

| `depth` | 範圍 |
| --- | --- |
| 小於 0 | 當前節點及全部後代 |
| 等於 0 | 當前節點的精確路徑 |
| 大於 0 | 當前節點及相對路徑段數不超過 `depth` 的後代 |

查詢對儲存的 `uri` 應用下列 SQL 表示式：

```sql
CASE
    WHEN uri IS NULL THEN NULL
    WHEN btrim(uri) = ''
      OR rtrim(btrim(uri), '/') = '' THEN '/'
    ELSE rtrim(btrim(uri), '/')
END
```

下文用 `N(uri)` 表示這個表示式；它不是新增列或資料庫函式。無限深度查詢
可概括為：

```text
account_id = :account_id
AND (N(uri) = :path OR N(uri) LIKE :child_pattern ESCAPE '\')
AND level = :level
```

例如 `:path` 為 `/resources/g00/d000`，子路徑模式為
`/resources/g00/d000/%`。路徑中的 `%`、`_` 和 `\` 會先轉義；末尾 `/`
用於區分目錄邊界。正深度查詢還會計算匹配路徑的相對段數。

SQL 實現見
[`_sql_normalized_path` 與 `_build_path_scope_clause`](https://github.com/volcengine/OpenViking/blob/eaf44199aacfb601f059202bd8d04246e5248f2e/openviking/storage/vectordb_adapters/opengauss/sql.py#L191-L224)。
pgvector 複用這部分過濾編譯邏輯。

## 為什麼普通 URI 索引沒有解決問題

普通 B-tree 索引的鍵是原始 `uri`，目錄條件比較的卻是
`CASE/btrim/rtrim` 表示式。此次執行計劃只使用 `account_id` 索引，再對取出的
租戶行執行路徑過濾。

百萬行表中，單目錄查詢命中 100 行，但租戶條件取出 100,000 個候選。
並行 Bitmap Heap Scan 的路徑過濾合計移除約 99,900 行。由於租戶行交錯儲存、
`work_mem=4MB`，計劃還出現 lossy bitmap 和額外的索引條件重查。
純過濾 `count(*)` 的 p50 為 141.11 ms，flat Top-10 為 141.42 ms，
說明這一組的主要開銷在掃描和過濾，而不是最後 100 行的距離計算。

`level=0/1` 可以利用既有的 `level` 和 `account_id` 索引做 BitmapAnd，
在本次資料分佈中將候選縮小到 1,000 行。`level=2` 佔資料的 98%，其選擇性
不足以解決這個掃描問題。實際收益取決於各層記錄比例與租戶物理佈局。

## 複合表示式索引

第一列使用 `account_id`，第二列使用與目錄查詢相同的歸一化 URI 表示式，
並指定 `text_pattern_ops`：

```sql
-- 將 public."context" 替換為實際 collection 表，
-- 併為每個表選擇獨立的索引名稱。
CREATE INDEX context_account_uri_scope_idx
ON public."context" (
    account_id,
    (CASE
        WHEN uri IS NULL THEN NULL
        WHEN btrim(uri) = ''
          OR rtrim(btrim(uri), '/') = '' THEN '/'
        ELSE rtrim(btrim(uri), '/')
    END) text_pattern_ops
);

ANALYZE public."context";
```

`account_id` 限定租戶；表示式鍵與查詢匹配；`text_pattern_ops` 支援這裡的
路徑字首 `LIKE` 範圍以及精確匹配。空目錄可以通過索引確認沒有候選，
不必遍歷整個租戶。規劃器仍根據統計資訊和成本選擇執行方式。

索引不改變路徑、租戶或 ACL 語義，也不單獨最佳化正深度的段數計算。
它是標量 B-tree 索引；向量距離仍由 flat 或 HNSW 路徑計算。
flat 查詢設定 `enable_indexscan=off` 以保持精確檢索，但仍允許 Bitmap Scan，
因此可以使用該索引。

對同一個百萬行、100 行命中的查詢，索引後的關鍵計劃為：

```text
Bitmap Heap Scan
  Actual Rows: 100
  Exact Heap Blocks: 77
  Rows Removed by Filter: 0
  BitmapOr
    Bitmap Index Scan on the scope index: 2 rows (exact path)
    Bitmap Index Scan on the scope index: 98 rows (child prefix)
```

這 2 行分別為 L0/L1，98 行為 L2 檔案；節點摘錄省略了完整條件與距離排序。
加上 `level=2` 後只返回該層的候選。

## 實測方法

測試於 **2026-11-13** 執行，程式碼版本為
`eaf44199aacfb601f059202bd8d04246e5248f2e`。
通過真實 `collection adapter.query` 查詢 PostgreSQL；測量包含連線池、
SQL 和結果讀取，不包含 HTTP、embedding 生成或完整遞迴檢索流程。

| 專案 | 設定 |
| --- | --- |
| 主機 | macOS arm64，18 邏輯 CPU，48 GiB 記憶體 |
| 資料庫 | PostgreSQL 17.6，pgvector 0.8.7，本機 loopback |
| PostgreSQL | `shared_buffers=128MB`、`work_mem=4MB`、`max_parallel_workers_per_gather=2`、`lc_collate=C` |
| 連線池 | `min_size=1`、`max_size=4` |
| 向量 | 128 維隨機單位向量，cosine 距離；另測 20,000 行 4096 維 flat |
| 資料規模 | 100,000 行基線與 1,000,000 行主測 |
| 百萬行佈局 | 10 個交錯租戶，每租戶 10 個組、每組 100 個目錄、每目錄 100 行 |
| 層級比例 | 每目錄 L0/L1 各 1 行，L2 98 行；L2 中一半放在 `sub` 下 |
| 查詢 | 限定租戶 `a0`，Top-10；目錄範圍、深度及 level 分別測試 |
| 樣本 | 每條件預熱 5 次；十萬行 flat 與 level 補測各 100 次，其餘每條件 200 次 |
| 併發 | 閉環客戶端執行緒，1 或 4 |

百萬行佈局包含 10,000 個 `(account_id, 目錄路徑)` 組合。資料通過二進位制
COPY 匯入，屬於合成測試集；不是生產請求或寫入吞吐測試。
當前配置與表示式索引按順序測試，未控制 OS 頁快取。
20 個查詢向量使用與首批資料相同的隨機 seed（基準 seed 為 `20261113`），
對應語料前 20 行，其中 2 行屬於租戶 `a0`。Recall 僅描述這組有限的語料內查詢。

共記錄 98 組條件、14,800 次測量請求。各條件彙總見
[主測 CSV](/benchmarks/pgvector-directory-filtering-20261113/measurements.csv)
和 [level 補測 CSV](/benchmarks/pgvector-directory-filtering-20261113/levels-measurements.csv)。
CSV 保留條件、樣本數、命中數、延遲分位數、QPS 和已測量的 Recall；
不包含逐請求結果 ID 或完整執行計劃。

### 百萬行：OV level 過濾

以下均為單併發 flat Top-10，單位為 ms。level 補測單獨重建相同分佈的
百萬行資料，每條件測量 100 次。

| level | 範圍 | 命中行 | 當前 p50 | 當前 p99 | 表示式索引 p50 | 表示式索引 p99 |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | 單目錄子樹 | 98 | 144.28 | 197.60 | 0.48 | 0.95 |
| 2 | 空目錄 | 0 | 139.95 | 174.44 | 0.38 | 0.82 |
| 2 | 租戶根目錄 | 98,000 | 145.01 | 252.04 | 143.62 | 209.90 |
| 0 | 單目錄子樹 | 1 | 7.29 | 9.18 | 0.60 | 1.21 |
| 1 | 單目錄子樹 | 1 | 6.98 | 9.53 | 0.50 | 0.93 |

L2 單目錄的 p50 改善約 300 倍；租戶根目錄仍需處理約十萬行，
路徑索引的收益有限。L0/L1 已能利用層級索引，但路徑索引進一步縮小了候選範圍。

### 百萬行：路徑深度與併發

下面不額外限定 level，因此單目錄包括 2 個摘要和 98 個檔案。
單位為 ms，均為單併發 flat Top-10。

| 範圍 | 命中行 | 當前 p50 | 當前 p99 | 表示式索引 p50 | 表示式索引 p99 |
| --- | --- | --- | --- | --- | --- |
| 租戶根目錄 | 100,000 | 155.16 | 214.50 | 139.60 | 192.18 |
| 一級目錄子樹 | 10,000 | 140.67 | 167.60 | 11.77 | 12.45 |
| 單目錄子樹 | 100 | 141.42 | 181.79 | 0.46 | 0.65 |
| `depth=1` | 51 | 143.07 | 176.39 | 0.55 | 0.92 |
| `depth=0` | 2 | 132.26 | 162.81 | 0.34 | 0.49 |
| 空目錄 | 0 | 137.67 | 168.53 | 0.36 | 0.65 |

單目錄、併發 4 時，QPS 從 13.6 提升到 3,524.9，p99 從 456.80 ms
降到 10.11 ms。這裡包含連線池等待與額外連線的建立/釋放成本，
不是 4 條固定保活連線的純 SQL 吞吐。

### 十萬行：HNSW 後過濾

HNSW 使用 `m=16`、`ef_construction=64`、`ef_search=100`，
`iterative_scan=strict_order`，掃描上限保持資料庫預設值。
單併發下，以同一資料、同一組 20 個查詢向量的 flat 結果作為真值，
Recall 分母為 `min(10, 命中行數)`。

| 範圍 | 命中行 | flat p50 ms | HNSW 配置 p50 ms | 平均 Recall@10 |
| --- | --- | --- | --- | --- |
| 租戶根目錄 | 10,000 | 12.43 | 3.41 | 52.5% |
| 單目錄子樹 | 100 | 10.75 | 18.93 | 67.0% |
| 空目錄 | 0 | 10.54 | 29.81 | 不適用 |

這三種範圍的計劃使用 HNSW Index Scan。單目錄的一次計劃在返回 10 行前
過濾掉 6,155 個候選，空目錄過濾掉 19,916 個候選。配置 HNSW 不代表每次都
走 ANN：此次 `depth=0/1` 使用標量 Bitmap Scan 加精確排序，其 100% Recall
不能歸因於 HNSW。

該組測試沒有驗證“表示式索引 + HNSW”的組合，也沒有調優 HNSW 引數。
不能據此認定 HNSW 普遍不適合目錄過濾，或將返回滿 Top-10 等同於高召回。

### 4096 維的邊界

4096 維僅測 20,000 行 flat，以下不限定 level，單併發：

| 範圍 | 命中行 | 當前 p50 ms | 表示式索引 p50 ms |
| --- | --- | --- | --- |
| 租戶根目錄 | 2,000 | 13.13 | 14.13 |
| 單目錄子樹 | 100 | 5.40 | 4.19 |
| 空目錄 | 0 | 4.77 | 3.44 |

該組的 URI 掃描、向量處理和 TOAST 成本與百萬行 128 維測試不同。
當前 adapter 的 `vector` HNSW 上限為 2000 維，4096 維使用 flat；
不能把 128 維的索引加速比或 ANN 結果外推到百萬行 4096 維場景。

## 如何驗證與落地

先在代表性資料上新增上述索引並執行 `ANALYZE`，然後給實際 adapter SQL
加上 `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`。同時記錄過濾命中數、
掃描/重查行數、heap block、p50/p95/p99、吞吐以及 ANN Recall。
窄範圍的計劃應能利用 scope 索引收窄候選；覆蓋整個租戶時，規劃器可能繼續
選擇原有 account 索引或其他掃描方式。

索引名稱不是索引定義校驗。部署前確認目標 collection 的欄位及表示式，
避免用 `IF NOT EXISTS` 掩蓋同名但定義不同的索引。線上建索引可評估
`CREATE INDEX CONCURRENTLY`，它需要在事務塊之外執行，並檢查構建後索引
是否有效；本次壓測使用的是載入完成後的普通 `CREATE INDEX`。
額外索引帶來的磁碟佔用和寫入維護成本尚未單獨測量。

手工索引的回退示例：

```sql
DROP INDEX public.context_account_uri_scope_idx;
```

後續自動化可複用同一個 SQL 表示式建構子，分別處理新 collection 建索引、
已有 collection 的遷移和物理索引定義校驗。還需驗證尾斜槓、空路徑、
LIKE 特殊字元、不同深度、ACL 條件、目錄傾斜、併發寫入及不同資料庫記憶體配置。
按候選規模選擇精確或 ANN 檢索屬於後續方案，當前沒有自動切換策略。

本次是本機預熱後的合成壓測，p99 樣本有限，也未覆蓋真實 ACL 複雜度、
完整服務鏈路、長期負載、冷快取、租戶物理聚集或分割槽。
結果用於判斷索引方向，不能作為生產延遲或容量承諾。
