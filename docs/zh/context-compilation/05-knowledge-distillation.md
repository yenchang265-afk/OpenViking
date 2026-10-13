# 示例：知識蒸餾

從一個或多個知識庫中提煉結論，按主題組織，並保留出處與不確定性。

例如，對比多期財報，分析營收、利潤和風險隨時間的變化。

輸出按主題分目錄，每頁說明一條結論：

```text
revenue-quality/
  growth-shifted-from-volume-to-pricing.md
  overseas-growth-offset-domestic-slowdown.md
profitability/
  margin-recovered-but-cash-conversion-weakened.md
risk/
  customer-concentration-increased.md
```

> 以上僅展示目錄結構。實際主題和結論由來源與指令決定，檔名概括結論。

Skill 原始碼：[openviking/builtin_skills/compile/knowledge-distillation](https://github.com/yenchang265-afk/OpenViking/tree/main/openviking/builtin_skills/compile/knowledge-distillation)

先確認[前置條件](01-overview.md#前置條件)，並在 OpenViking 倉庫根目錄執行以下命令。來源目錄需替換為自己的資料目錄。

## 第一步：準備來源

```bash
ov add-resource ./finance-reports --to viking://resources/finance-reports --wait
ov ls -r viking://resources/finance-reports
```

## 第二步：添加 Skill

Knowledge Distillation Skill 隨 OpenViking 一起發佈，預設會安裝到每個帳戶共享的 `viking://agent/skills`（伺服器選項 `server.builtin_skills`）。確認它已存在：

```bash
ov skills list
# → viking://agent/skills/knowledge-distillation
```

如果管理員刪除了它，可從套件原始碼重新加入：

```bash
ov add-skill openviking/builtin_skills/compile/knowledge-distillation -p viking://agent/skills
```

## 第三步：執行編譯

在 `--instruction` 裡說清**分析問題、對比維度、基線和範圍**——這直接決定蒸餾的方向：

```bash
ov compile \
  --from viking://resources/finance-reports \
  --to viking://resources/finance-insights \
  --skill viking://agent/skills/knowledge-distillation \
  --instruction "對比近三年財報，找到營收質量、盈利能力和風險的變化及驅動因素"
```

`--from` 可以傳多個來源，用於跨知識庫對比：

```bash
ov compile \
  --from viking://resources/finance-2024,viking://resources/finance-2025 \
  --to viking://resources/finance-insights \
  --skill viking://agent/skills/knowledge-distillation \
  --instruction "對比兩個年度知識庫，找出關鍵指標的變化與結構性差異"
```

命令會立刻返回 `task_id`：

```bash
ov task status cmp_01abc      # 檢視進度與最終結果
ov task cancel cmp_01abc      # 協作式取消
```

## 第四步：檢視產物

先檢視目錄，再讀取實際生成的結論頁。下面的檔名僅為示例：

```bash
ov tree viking://resources/finance-insights
ov read viking://resources/finance-insights/revenue-quality/growth-shifted-from-volume-to-pricing.md
```

預設不生成 `index.md`；需要導航頁時，在 `--instruction` 中明確要求。再次編譯同一主題時，Skill 會要求更新已有分析頁，並標註可能隨時間變化的結論。

## 相關文件

- [上下文編譯概覽](./01-overview.md)
- [日報示例](./04-daily-report.md)
- [Agent Runtime API](../api/23-agent-runtime.md)
