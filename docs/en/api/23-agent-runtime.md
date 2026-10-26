# Agent Runtime API

Applications submit Compile tasks through OpenViking's Compile API. OpenViking validates requests, persists tasks as durable queue work, and runs them in the server process, so interrupted tasks resume after a restart.

**Code entry points**:

- `openviking/server/routers/compile.py` - Compile task creation
- `openviking/server/routers/tasks.py` - task inspection and cancellation
- `openviking/service/compile_service.py` - request validation and task execution
- `openviking/service/external_task_service.py` - durable queue-backed task lifecycle
- `openviking/compile/` - the Skill pipeline (plan, map, shuffle, reduce, finalize)

## Compile task API

### Create a task

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `from` | string[] | Yes | - | One or more source directories |
| `to` | string | Yes | - | Target Resource directory or a supported Skill namespace; Memory directories use `--skill memory` |
| `skill` | string | Yes | - | Skill directory or its `SKILL.md` URI |
| `instruction` | string | No | Skill-driven default | Additional instructions for this Compile run |
| `args` | object | No | - | Optional `last_compile_time` and `wiki_links` (see below) |

`args` accepts only these keys; any other key returns `400 INVALID_ARGUMENT`:

| Key | Type | Description |
|-----|------|-------------|
| `last_compile_time` | ISO 8601 timestamp or Unix seconds | Incremental compile: only source files modified at or after this time are processed. With no newer files the task completes without model calls or writes |
| `wiki_links` | boolean | Rebuild resource `index.md` files from the actual Markdown paths |

Compile uses the account's configured `vlm` model. The Python example uses `SyncHTTPClient`; await `compile()` with `AsyncHTTPClient`.

**HTTP API**

```http
POST /api/v1/compile
```

```bash
curl -X POST http://localhost:1933/api/v1/compile \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -H "Idempotency-Key: studio-compile-001" \
  -d '{
    "from": ["viking://resources/research"],
    "to": "viking://resources/research-wiki",
    "skill": "viking://user/default/skills/research-compiler",
    "instruction": "Track the historical progress and preserve supporting evidence.",
    "args": {"wiki_links": true}
  }'
```

The endpoint returns `202 Accepted` with an OV task record:

```json
{
  "status": "ok",
  "result": {
    "task_id": "cmp_01abc",
    "task_type": "compile",
    "status": "pending",
    "stage": "queued",
    "resource_id": "viking://resources/research"
  }
}
```

**CLI**

```bash
ov compile \
  --from viking://resources/research \
  --to viking://resources/research-wiki \
  --skill viking://user/default/skills/research-compiler \
  --instruction "Track the historical progress and preserve supporting evidence." \
  --args '{"wiki_links":true}'
```

`--args` must be a JSON object. The command returns a task ID immediately after submission.

**SDKs**

The Python, TypeScript, and Go SDKs pass `instruction` and `args` through their Compile options:

::: code-group

```python [Python]
task = client.compile(
    ["viking://resources/research"],
    "viking://resources/research-wiki",
    "viking://user/default/skills/research-compiler",
    {"args": {"wiki_links": True}},
)
```

```ts [TypeScript]
const task = await client.compile(
  ["viking://resources/research"],
  "viking://resources/research-wiki",
  "viking://user/default/skills/research-compiler",
  { args: { wiki_links: true } },
);
```

```go [Go]
task, err := client.Compile(
    ctx,
    []string{"viking://resources/research"},
    "viking://resources/research-wiki",
    "viking://user/default/skills/research-compiler",
    &openviking.CompileOptions{
        Args: map[string]any{"wiki_links": true},
    },
)
```

:::

### Target settings and operation history

These endpoints use the current account and authentication context. `to` is the registered target's `viking://` URI. Reading or updating one target requires write access; listing targets returns only accessible targets.

| HTTP API | Description and result (`status: "ok"`) |
|----------|------------------------|
| `GET /api/v1/compile/config?to={to}` | `result` contains target settings and run status |
| `POST /api/v1/compile/config/update` | Required JSON body field `to` identifies the registered Compile output directory to configure; `result` contains the updated settings and run status |
| `GET /api/v1/compile/configs` | Optional query parameters: `limit` (1–100, default 20) and `cursor`; `result.targets` contains this page of visible target summaries ordered by `target_id` ascending; pass `result.next_cursor` unchanged as the next page's `cursor`; null marks the last page |
| `GET /api/v1/compile/operations?to={to}` | `result.operations` contains operations, newest first; `result.next_cursor` continues pagination |
| `GET /api/v1/compile/operations/{operation_id}/outputs?to={to}` | `result.outputs` contains output files and frozen version references, ordered by URI; `result.next_cursor` continues pagination |

The update body requires `to`, `from` (a non-empty source URI array), `skill`, and `auto_update` (boolean). When `auto_update=true`, a valid `update_schedule` is required. When `auto_update=false`, the schedule can be omitted or null; the saved rule is cleared and the returned value is null. New targets have no default rule, and enabling updates after disabling them requires a rule. Optional `instruction` preserves the saved value when omitted; `null` or an empty string clears it. Updating settings does not submit a Compile task.

`update_schedule` requires `frequency` (`daily` or `weekly`). Optional `hour` (0–23) and `minute` (0–59) default to 0. Weekly schedules also accept `weekday` (1=Monday through 7=Sunday, default 1). Schedules use `Asia/Shanghai` time.

Scheduled updates require `compile_api.scheduler_enabled=true` (default `false`) and valid `expiry.service_name` and `expiry.redis` configuration. `compile_api.scheduler_backend` only accepts `redis` (the default); `local` is invalid. Enabling `auto_update` while scheduling is disabled returns `COMPILE_SCHEDULER_DISABLED`. Manual incremental Compile and version management do not require Redis.

Both history endpoints accept optional query parameters `limit` (1–100, default 20) and `cursor`. Pass the returned `next_cursor` unchanged; `null` marks the last page. `operation_id` is 1–128 characters, starts with a letter or digit, and otherwise allows letters, digits, `:`, `.`, `_`, and `-`. Operations remain queryable after target deletion. Missing targets, operations, or output manifests return `404`. A null `version_id` or `snapshot_id` on an output item indicates that the corresponding reference is unavailable.

### Check Compile availability

```http
GET /api/v1/compile/capabilities
```

Uses the current authentication context and takes no request parameters. Returns `200 OK`:

```json
{
  "status": "ok",
  "result": {
    "configured": true,
    "can_create": true,
    "reason_code": null
  }
}
```

| Field | Meaning |
|-------|---------|
| `configured` | Whether the server's Compile runtime is initialized |
| `can_create` | Whether the current authentication context can submit Compile tasks |
| `reason_code` | `NOT_CONFIGURED` while the runtime is not initialized; otherwise `null` |

An unavailable runtime is reported in the result with `can_create: false`, not as an HTTP error. This does not probe model health or validate a particular Compile request.

### Compile routing embeddings

`POST /api/v1/compile/embeddings` embeds transient routing texts using the current authentication context, without indexing or retaining them. Compile itself calls the same logic in-process.

Body: required `target_uri` (an existing resource or Skill namespace target with read access); optional `texts` (string array, default `[]`, at most 32 texts, each 1–1024 characters and not whitespace-only); optional `expected_model` (model fingerprint; a non-empty value must match the current model).

Returns `200 OK` with `status: "ok"` and `result: {"model": "...", "vectors": [...]}`. Vectors follow input order; empty `texts` returns only the model fingerprint and an empty vector array.

### Find a task by submission key

```http
GET /api/v1/compile/submissions/{key}
```

Use this endpoint when a task creation response was lost or timed out. Pass the same key that was sent in the optional `Idempotency-Key` header of `POST /api/v1/compile`.

| Parameter | Location | Type | Required | Description |
|-----------|----------|------|----------|-------------|
| `key` | Path | string | Yes | 16–128 characters; only letters, digits, `:`, `.`, `_`, and `-` are allowed |

```bash
curl http://localhost:1933/api/v1/compile/submissions/studio-compile-001 \
  -H "X-API-Key: your-key"
```

Returns `200 OK` with `status: "ok"` and the existing OV task record in `result`, using the same structure as the task creation response above. Lookup is scoped to the current account and user and does not create a task. A missing submission, including a key used only by another user, returns `404`; an invalid key returns `400 INVALID_ARGUMENT`.

To retry creation safely, reuse the same `Idempotency-Key` and request parameters. A key reused with different parameters returns `409`. Without this header, creation does not provide a submission key for this lookup.

### Get task status

For ordinary user requests, a task is visible only to its creator; missing tasks and tasks owned by another user return `404`. ROOT queries have separate administrative visibility and cannot cancel tasks.

```http
GET /api/v1/tasks/{task_id}
```

```bash
ov task status cmp_01abc
```

Terminal task responses also contain the result or error.

### Cancel a task

```http
POST /api/v1/tasks/{task_id}/cancel
```

```bash
ov task cancel cmp_01abc
```

The task first enters `cancelling`, then becomes `cancelled` after in-process work and cleanup settle. Compile checks for cancellation before it publishes to the target, so a cancelled task normally writes nothing. A cancel that arrives while publishing waits for it to finish; the task becomes `cancelled` and keeps its result. Completed writes are not rolled back. Repeated cancellation of an already `cancelled` task is idempotent.

| Status | Typical stages |
|--------|----------------|
| `pending` | `queued` |
| `running` | `running`, `collecting_context`, `pipeline`, `writing`; memory mode reports `consolidating` |
| `cancelling` | Settling in-process work and resource cleanup |
| `completed` | `completed`, `salvaged` |
| `failed` | Stage where the failure occurred; the response contains `error` |
| `cancelled` | `cancelled` |

### Legacy endpoints

The following legacy VikingBot proxy routes on OV are retired and return migration guidance only:

```http
POST /bot/v1/compile
GET /bot/v1/compile/{task_id}
POST /bot/v1/compile/{task_id}/cancel
```

Create tasks through `/api/v1/compile`; inspect and cancel them through `/api/v1/tasks/{task_id}`.

## Execution and restart recovery

Compile runs inside the OpenViking server, the same way `add_resource` processing does:

- Each task is a durable QueueFS message on the `ExternalTask` queue. The message is acknowledged only after the task outcome is saved.
- If the server stops or crashes while a task is running, the message is delivered again on the next start and the task **runs again from the beginning**. Partial work from the interrupted attempt is discarded; publishing to the target happens only at the end of an attempt, and unchanged pages are left as they are.
- Tasks for the same target run one at a time; other tasks for that target wait in the queue.
- Model calls use the account's `vlm` configuration and share the server-wide `vlm.max_concurrent` capacity. Per-task stage concurrency is set under [`compile_api`](../guides/01-configuration.md#compile-api).
- A task gets at most 3 attempts. `meta.attempts` counts them; a task interrupted three times fails with `INTERRUPTED` instead of re-running on every restart.
- A task runs with its creator's identity and permissions. No API key or other credential is stored with the task. With API key or trusted authentication, each attempt re-checks the creator: it keeps only groups the user still belongs to, and fails with `UNAUTHENTICATED` if the user is being deleted or the account is no longer active. API key authentication also runs with the lower of the submit-time and current role and fails if the user was removed. Scratch files of failed attempts are kept for 7 days and deleted with their user or account. After a restart, recovered tasks wait until authentication is ready.
- Each user can have at most `compile_api.max_active_tasks_per_user` (default 10) pending or running Compile tasks; more return `429 RESOURCE_EXHAUSTED`.

`queue_workers.external_task.max_concurrent` sets how many Compile tasks run at once.

## Related documentation

- [Background Tasks](17-tasks.md) - generic task inspection, cancellation, and listing
- [Context Compilation](../context-compilation/01-overview.md) - Compile scenarios and examples
- [Skills API](04-skills.md) - managing the Skills used by Compile
