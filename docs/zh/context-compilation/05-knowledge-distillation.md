# 示例：知識蒸餾

把一個或多個知識庫、文件集合**蒸餾**成按主題組織、有出處的高層次知識：跨來源的發現、趨勢、變化、驅動因素、對比、影響和不確定性。

典型用途：蒸餾一個知識庫、對比多個集合，如從一疊財報裡推匯出「跨報告期的變化」這類高階洞察。

產物是一棵按主題組織的淺層工件樹，每個主題目錄是一個持久的語義領域，每一頁是一條獨立有用的高層次結論：

```text
revenue-quality/
  growth-shifted-from-volume-to-pricing.md
  overseas-growth-offset-domestic-slowdown.md
profitability/
  margin-recovered-but-cash-conversion-weakened.md
risk/
  customer-concentration-increased.md
```

> 上面只是形態示例——真實的主題和結論由你給的領域決定。

Skill 原始碼：[openviking/builtin_skills/compile/knowledge-distillation](https://github.com/yenchang265-afk/OpenViking/tree/main/openviking/builtin_skills/compile/knowledge-distillation)

## 第一步：準備來源

```bash
ov add-resource ./finance-reports --to viking://resources/finance-reports
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

## 第四步：看看產物

先看主題樹，再鑽進具體結論頁：

```bash
ov tree viking://resources/finance-insights
ov read viking://resources/finance-insights/revenue-quality/growth-shifted-from-volume-to-pricing.md
```

## 相關文件

- [上下文編譯概覽](./01-overview.md)
- [日報示例](./04-daily-report.md)
- [Agent Runtime API](../api/23-agent-runtime.md)
