# 示例：日報

把帶時間戳的對話記錄、Agent 會話、IM 訊息、協作文件、會議紀要、任務記錄等材料，編譯成簡潔、有出處的**日報**：每天一頁。

Skill 原始碼：[openviking/builtin_skills/compile/daily-report](https://github.com/yenchang265-afk/OpenViking/tree/main/openviking/builtin_skills/compile/daily-report)

## 第一步：準備來源

日報的來源通常是已經在 OpenViking 裡的會話、訊息或文件。如果要從本地匯入一批記錄：

```bash
ov add-resource ./work-logs --to viking://resources/work-logs
ov ls -r viking://resources/work-logs
```

## 第二步：添加 Skill

Daily Report Skill 隨 OpenViking 一起發佈，預設會安裝到每個帳戶共享的 `viking://agent/skills`（伺服器選項 `server.builtin_skills`）。確認它已存在：

```bash
ov skills list
# → viking://agent/skills/daily-report
```

如果管理員刪除了它，可從套件原始碼重新加入：

```bash
ov add-skill openviking/builtin_skills/compile/daily-report -p viking://agent/skills
```

## 第三步：執行編譯

在 `--instruction` 裡說清楚**日期、時區、報告物件和側重點**，Skill 會據此定位和取捨：

```bash
ov compile \
  --from viking://resources/work-logs \
  --to viking://resources/daily-report \
  --skill viking://agent/skills/daily-report \
  --instruction "生成 2026-08-20 的日報，聚焦我的工作產出與決策"
```

一次生成多天，把日期範圍寫進 `--instruction` 即可（每天仍是獨立一頁）：

```bash
ov compile \
  --from viking://resources/work-logs \
  --to viking://resources/daily-report \
  --skill viking://agent/skills/daily-report \
  --instruction "生成 2026-08-18 至 2026-08-20 每天一份日報"
```

命令會立刻返回 `task_id`：

```bash
ov task status cmp_01abc      # 檢視進度與最終結果
ov task cancel cmp_01abc      # 協作式取消
```

## 第四步：看看產物

日報是純 Markdown，直接讀即可：

```bash
ov tree viking://resources/daily-report
ov read viking://resources/daily-report/2026-08-20.md
```


## 相關文件

- [上下文編譯概覽](./01-overview.md)
- [知識蒸餾示例](./05-knowledge-distillation.md)
- [Agent Runtime API](../api/23-agent-runtime.md)
