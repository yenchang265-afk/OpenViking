# Syncing upstream with focused AI assistance

Official remote: `upstream` (`volcengine/OpenViking`). Fork remote: `origin`
(`yenchang265-afk/OpenViking`). Use regular merge commits to preserve shared history.

## Prepare a sync

Run from the repository root, replacing the refs with the intended fork branch and
upstream revision. The script fetches upstream unless `--no-fetch` is supplied.

```sh
python3 scripts/sync_upstream.py --base origin/main --upstream upstream/main --worktree /tmp/openviking-sync
```

Choose the base explicitly: the script merges committed history only. Commit and
push any fork changes you want included first, or select a local committed branch.
Existing uncommitted work stays in the original checkout. The destination must be
new. A timestamped sync branch is created; use `--branch` to choose its name.
No commit, push, or PR is performed automatically.

The script prints a context report path in the new worktree's Git metadata. Feed
that report and this guide to the agent first. Exit 1 with unresolved paths means
the merge needs resolution; other failures require inspecting the merge output.
Git may reuse conflict resolutions, but they still need review and staging.

## Fork behavior to preserve

- Web search and fetch are disabled by default through `tools.web.enabled`.
  External-service skills are opt-in; the deleted github-proxy skill stays deleted.
  Reference: `7b662074bd2c`.
- Removed Volcengine/VikingDB embedding, VLM and rerank implementations and the Ark
  SDK dependency stay removed. OpenAI remains the embedding default; unsupported
  sparse/hybrid embedding is rejected. Reference: `3e69425e550c`.
- Volcengine KMS stays removed. Keep the `0x03` envelope marker for stored-data
  compatibility. Keep fork image defaults and fork project URLs.
  Reference: `d97c2fe724bc`.
- The Feishu Drive accessor stays removed; drop upstream Feishu-only helpers and
  examples (e.g. `_source_skipped_items`). The Volcengine/VikingDB vector adapters
  and remote `path_glob`/grep sections stay removed; upstream backends such as
  `pgvector` are added next to the fork's `elasticsearch`.
- These are scoped fork decisions, not a blanket ban on every Volcengine string.
  The provider-removal commit explicitly left wizard and bot registry references
  for follow-up. Investigate relevant changes rather than deleting all matches.

Last documented upstream sync: branch `sync/upstream-20261125-133836`, through
upstream `a4b083e` (previous: branch `sync/upstream-20261118-155451`, through `989e6c7`).
Confirm ancestry with Git; update this note after each accepted sync.

- The single-provider `cache` shape (`{"backend"|"provider": ..., "params": ...}`) keeps
  loading as `cache.instances.default` in Python (`normalize_legacy_cache`) and Rust
  (`normalize_canonical_cache`); `connections.redis` is inherited per Redis instance.
  CacheFS `multi_instance` / `max_file_size_bytes` travel in the binding's `cache.cachefs`.
- In-server Compile keeps upstream's configuration API (`compile_name`, create/update,
  runs, scheduler) but executes in-process (`CompileService.run`); there is no Runtime
  HTTP client, archive call or `CompileDependencyFailure` path.
- The Compile pipeline (`openviking/compile`) follows upstream `989e6c7`'s Markdown
  file-worker design. `agent_loop.agent_runner` implements upstream's worker contract
  in-server (private output directory, read-only `assignment.json`/`inputs/`, natural
  completion); upstream's VikingBot "simple" executor (`simple.py`) is not ported, and
  the llm-wiki example Skill stays at the fork version because upstream's rewrite
  persists pages by running `scripts/write_wiki.py`, which in-server Compile cannot exec.
- Studio keeps the fork's context-menu delete/move UI; upstream's header copy/move/delete
  dialogs were not adopted (their API helpers remain in `resources/lib/api.ts`).
- Server hosting follows upstream's `ServerRuntime` (`openviking/server/runtime.py`) and
  phased service lifecycle (`initialize` → `wire_runtime` → `recover` → `start_background`).
  Fork hooks live there: durable ExternalTask owners are re-checked through
  `key_store_identity_resolver` in `ServerRuntime.wire`; watch options are enabled in
  `OpenVikingService.configure_runtime`; `create_app` still runs `validate_shared_deployment`,
  the `external_bot_api_url` proxy and the local temp-upload sweep loop. No Compile Runtime
  backend is configured (`configure_local_backend` is not called).
- `redis_mysql` account storage uses upstream's named CacheRuntime instance
  (`account_store.params.cache = {"instance": "<name>"}`); the old inline Redis `cache`
  shape and the `redis-mysql` extra are gone (the `mysql` extra covers it).
- Keyword search `args` (`bm25_k1`, `bm25_b`, `post_process_input_limit`) are validated
  upstream-style; the Elasticsearch adapter rejects BM25 tuning (similarity is per index)
  and ignores `advance`.
- In-server Compile ports upstream's recovery proof (`completion_status`,
  `recovery_proof`, `verify_recovery_sources`; `OVClient.git_show_bytes` reads snapshot
  blobs) and Compile image normalization (`media.read_image(for_compile=True)`).
- Usage/audit storage supports the fork's `mysql` backend next to upstream's `postgres`;
  the queue observer keeps the fork's per-context `active_errors` alongside upstream's
  per-account scoping.

## Chinese text conventions

The fork's Chinese docs (`docs/zh`, `bot/docs/zh`, top-level `*_CN.md`)
are Traditional Chinese (Taiwan), converted with OpenCC `s2twp` plus term fixes
(全域, 帳號/帳戶, 回呼, 連接器, 進階). Upstream edits these files in Simplified, so
resolve them as a 3-way merge of the fork file against the *converted* merge base
and *converted* upstream side, and convert newly added upstream zh docs. Web Studio
uses `zh-TW` locales instead of upstream `zh-CN`; port upstream `zh-CN` changes
there. Exception: `frontend/` zh docs and `README_CN.md` files use plain `s2twp`
(only 賬→帳; they keep 回撥, 全域性); realign their tables with prettier 3.6.
The generated `frontend/docs/docs/zh/guide/changelog.md` stays Simplified, byte-identical
to upstream (`npm run check:release-notes` regenerates it from `CHANGELOG.md`).
Frontend React sources, demos, tests and site config stay Simplified.

Merge sync PRs with a merge commit, never squash. Squashing #120 dropped the
upstream parents, so the next sync replayed already-synced commits; #129 fixed it
with a tree-preserving `git merge -s ours <last-synced-upstream>` before merging.
After the merge, run `scripts/compile_upstream_sync.py sync --to upstream/main`
and `check` (ruff version from `openviking/compile/UPSTREAM.json`).

## Resolve and validate

Give the agent this instruction:

> Read UPSTREAM_SYNC.md and the generated sync context. Resolve remaining conflicts
> while preserving the listed fork behavior. Inspect relevant code and callers as
> needed, preferring the code graph when available. Review reused resolutions too.
> Run focused checks, expand validation according to changed areas and CI, and
> report failures and risks. Do not commit or push without instruction.

From the sync worktree, with project and bot dependencies/native runtime installed:

```sh
bash bot/scripts/test_all.sh -q -k web_tools_disabled
uv run --no-sync pytest -q -o addopts='' tests/misc/test_config_validation.py tests/unit/crypto/test_providers_mock.py tests/misc/test_rerank_openai.py
uv run --no-sync pytest -q -o addopts='' tests/vectordb/test_cuvs_config.py tests/vectordb/test_cuvs_index.py tests/vectordb/test_cuvs_collection.py tests/vectordb/test_str_to_uint64.py
git diff --check
git diff --cached --check
```

The cuVS command matches `_test_lite.yml`. These checks are a starting point;
run relevant tests for other changed areas and required PR checks. Provider removal
and deployment defaults also require reviewing the merged diff. Passing the listed
tests alone does not prove every fork invariant. Missing dependencies or native
runtime are blocked checks, not passes.

Stage resolved files explicitly, review `git diff --cached`, and commit the merge
after validation. Update this guide's synced revision. Push the sync branch and
open a PR targeting the fork branch when authorized. Suggested cadence: weekly,
adjusted to upstream activity.

To abandon an uncommitted merge, run `git merge --abort` in its worktree. Keep the
worktree until any useful edits are saved. No automatic cleanup deletes work.

## Conflict memory

Repository-local settings (enabled during initial setup):

```sh
git config --local rerere.enabled true
git config --local rerere.autoupdate false
```

Git records resolutions locally; they are not distributed through ordinary pushes.
To correct a reused resolution during a conflict, use `git rerere forget path/to/file`,
then resolve it again. To undo setup, unset these two local settings. Keep agent
context focused on this guide, the report, relevant conflicts and failed checks;
load additional context when the evidence requires it.
