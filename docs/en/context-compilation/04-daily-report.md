# Example: Daily Report

Compile timestamped conversation logs, agent sessions, IM messages, collaborative documents, meeting notes, and task records into concise, evidence-grounded **daily reports**: one page per day.

Skill source: [openviking/system_assets/compile/example-skills/daily-report](https://github.com/yenchang265-afk/OpenViking/tree/main/openviking/system_assets/compile/example-skills/daily-report)

Check the [prerequisites](01-overview.md#prerequisites) and run these commands from the OpenViking repository root. Replace the source directory with your own material.

## Step 1: Prepare the sources

Daily-report sources are usually sessions, messages, or documents already in OpenViking. To import a batch of records from local:

```bash
ov add-resource ./work-logs --to viking://resources/work-logs --wait
ov ls -r viking://resources/work-logs
```

## Step 2: Add the Skill

The Daily Report Skill ships with OpenViking. Every account has a read-only copy at `viking://system/compile/example-skills/daily-report`, synced at server start and when an account is created, so `--skill` can use it directly. Check that it is there:

```bash
ov ls viking://system/compile/example-skills
# → viking://system/compile/example-skills/daily-report/
```

To customize the Skill, install an editable copy and pass its URI to `--skill` instead:

```bash
ov add-skill openviking/system_assets/compile/example-skills/daily-report -p viking://agent/skills
```

## Step 3: Run compile

Spell out the **date, timezone, report subject, and emphasis** in `--instruction` — the Skill uses it to scope and prioritize:

```bash
ov compile \
  --from viking://resources/work-logs \
  --to viking://resources/daily-report \
  --skill viking://system/compile/example-skills/daily-report \
  --instruction "Daily report for 2026-08-20 in Asia/Shanghai, focused on my outcomes and decisions"
```

For several days at once, put the date range in `--instruction` (each day is still its own page):

```bash
ov compile \
  --from viking://resources/work-logs \
  --to viking://resources/daily-report \
  --skill viking://system/compile/example-skills/daily-report \
  --instruction "One daily report per day for 2026-08-18 to 2026-08-20 in Asia/Shanghai"
```

The command returns a `task_id` immediately:

```bash
ov task status cmp_01abc      # progress and final result
ov task cancel cmp_01abc      # cooperative cancel
```

## Step 4: Inspect the output

Reports are plain Markdown — just read them:

```bash
ov tree viking://resources/daily-report
ov read viking://resources/daily-report/2026-08-20.md
```


## Related docs

- [Context Compilation Overview](./01-overview.md)
- [Knowledge Distillation example](./05-knowledge-distillation.md)
- [Agent Runtime API](../api/23-agent-runtime.md)
