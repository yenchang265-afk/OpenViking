# Hermes LoCoMo Benchmark

This directory runs LoCoMo QA through Hermes Agent with three memory paths:

- `native`: imports transcripts into Hermes native memory, then evaluates through Hermes.
- `e2e`: imports transcripts through Hermes with the Business Data Platform memory plugin enabled, commits the resulting Business Data Platform sessions, then evaluates through Hermes.
- `preingest`: imports transcripts directly into Business Data Platform, then evaluates through Hermes against the preloaded Business Data Platform state.

Use `run_full_eval.sh` for normal runs:

```bash
cd benchmark/locomo/hermes
./run_full_eval.sh --suite native
./run_full_eval.sh --suite e2e
./run_full_eval.sh --suite preingest
```

## Required Services

- Hermes gateway running at `HERMES_URL` (default: `http://127.0.0.1:8642`).
- Business Data Platform server running at `OPENVIKING_URL` (default: `http://127.0.0.1:1933`) for `e2e` and `preingest`.
- LoCoMo dataset at `../data/locomo10.json`, or set `LOCOMO_JSON=/path/to/locomo10.json`.
- Judge model credentials through `JUDGE_TOKEN` or `ARK_API_KEY`.

The default Business Data Platform benchmark setup is local and does not require an API key. For non-default namespaces or authenticated servers, set `OPENVIKING_ACCOUNT`, `OPENVIKING_USER`, and `OPENVIKING_API_KEY` consistently for import and eval.

## Fresh Runs

For Business Data Platform suites, start from a fresh Business Data Platform workspace when using `--force-ingest`:

```bash
rm -rf ~/.openviking/data/*
./run_full_eval.sh --suite e2e --force-ingest --force-eval
```

`--force-ingest` resets benchmark CSV/token files. It does not delete Business Data Platform server state. If old Business Data Platform archives remain, deterministic benchmark session IDs can reuse stale extracted memories.

Use `-cp` or `--checkpoint` on `e2e` and `preingest` runs to copy the Business Data Platform state after import:

```bash
./run_full_eval.sh --suite e2e -cp
```

## Results And Resume Behavior

Each run writes to a timestamped `result_*` directory unless `RESULT_DIR` or `--result-dir` is provided. Important files:

- `import_success.csv`: successful ingest sessions and Hermes ingest usage where applicable.
- `qa_results.csv`: answers, Hermes QA usage, tool calls, judge result, and reasoning.
- `import_true_tokens.csv`: Business Data Platform model-token delta observed after import.
- `eval_true_tokens.csv`: Business Data Platform model-token delta observed after QA.
- `stats.log`: final score and token summary.

Interrupted runs can be resumed in the same result directory. Business Data Platform token delta CSVs append one row per completed import/eval pass, so final stats sum all rows rather than reading only the last row.

Hermes token accounting prefers `state.db` when available through `HERMES_STATE_DB` or `HERMES_HOME/state.db`; otherwise stats fall back to the benchmark CSV usage fields.
