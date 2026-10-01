# OpenViking Tool Server for Open WebUI

A standalone FastAPI server that exposes a curated subset of OpenViking
endpoints as **OpenAPI tools** so Open WebUI can call them as native tools.

[中文說明在下方 / Chinese instructions below.](#中文說明)

## What This Plugin Does

Open WebUI supports two integration mechanisms — Python "Functions" pasted into
its admin UI, and **external OpenAPI tool servers** auto-discovered from
`/openapi.json`. This plugin implements the second mechanism.

It is a **thin translation layer**: every tool route forwards a request to the
corresponding OpenViking HTTP endpoint, attaches tenant headers, and returns
the response. There is no business logic here — see the OpenViking server for
that.

## Tools Exposed

Seven curated tools, all auto-discovered by Open WebUI:

| Tool | OpenViking endpoint | Purpose |
| --- | --- | --- |
| `ov_search` | `POST /api/v1/search/find` | Semantic search across memories, resources, skills |
| `ov_recall_memories` | `POST /api/v1/search/find` (scoped to `viking://~/memories/`) | Recall personal memories for the current query |
| `ov_add_memory` | `POST /api/v1/content/write` to `viking://~/memories/<name>` | Persist a new memory |
| `ov_list_memories` | `GET /api/v1/fs/ls?uri=viking://~/memories/` | Browse the memories directory |
| `ov_read_resource` | `GET /api/v1/content/read` | Read full text content of any `viking://` URI |
| `ov_add_resource` | `POST /api/v1/resources` | Ingest a remote URL or path-reachable file |
| `ov_session_status` | `GET /api/v1/sessions/{id}` | Inspect counts and archive state of a session |

The list is intentionally small. Adding more is straightforward — see the
[Roadmap](#roadmap).

## Quickstart

```bash
cd examples/openwebui-plugin
pip install -e .
OV_API_KEY=your-key python -m openviking_openwebui
```

The server listens on `0.0.0.0:8765` by default. You should see:

```
INFO:     Uvicorn running on http://0.0.0.0:8765
```

Verify the OpenAPI spec is served:

```bash
curl http://localhost:8765/openapi.json | jq '.paths | keys'
```

## Wiring Into Open WebUI

1. Open WebUI → **Settings** → **Tools** → **Add Tool Server**.
2. Paste the URL where this server is reachable, e.g. `http://localhost:8765`.
3. Open WebUI fetches `/openapi.json`, lists all seven tools, and presents
   them to the LLM as callable tools on every chat turn.

No copy-pasting Python files, no admin-panel uploads. The same tool server is
reusable across any OpenAPI-aware client.

## Configuration

All configuration is via environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `OV_ENDPOINT` | `http://localhost:1933` | OpenViking server base URL |
| `OV_API_KEY` | _(empty)_ | Bearer token sent as `Authorization: Bearer …` |
| `OV_ACCOUNT` | `default` | Tenant — sent as `X-OpenViking-Account` |
| `OV_USER` | `default` | User — sent as `X-OpenViking-User` |
| `OV_AGENT` | `default` | Actor peer ID — sent as `X-OpenViking-Actor-Peer` |
| `OV_BIND` | `0.0.0.0:8765` | Host:port the tool server binds to |
| `OV_TIMEOUT` | `30` | HTTP timeout in seconds when calling OpenViking |

There is no config file. This is intentional — make the deployment unit one
binary and one set of env vars.

## Tool Reference

### `ov_search`
Top-level semantic search. Takes `{query, limit?, target_uri?, score_threshold?}`
and returns `{hits: [{uri, score, snippet?}], raw}`. Use this when you want to
search across memories, resources, and skills together.

### `ov_recall_memories`
Same as `ov_search` but `target_uri` is forced to `viking://~/memories/`,
so only personal memories are searched. Use this in chat to ask "what do you
remember about me re: X?".

### `ov_add_memory`
Persists a memory. Takes `{name, content, mode?, wait?}` and writes
`viking://~/memories/<name>` via OpenViking's content write API. `mode` is
one of `replace | append | create`.

### `ov_list_memories`
Lists entries directly under `viking://~/memories/`. Takes
`{recursive?, limit?}`.

### `ov_read_resource`
Reads any `viking://` URI's text content. Takes `{uri, offset?, limit?}`.

### `ov_add_resource`
Triggers OpenViking ingestion of a remote URL or path the OV server can reach.
Takes `{path, to?, parent?, reason?, instruction?, wait?}`. Pure HTTP forward —
the OV server validates the source.

### `ov_session_status`
Returns session metadata for a given session ID — message counts, archive
state, pending tokens. Takes `{session_id}`.

## Tests

```bash
cd examples/openwebui-plugin
pip install -e ".[test]"
pytest tests -x -q
```

The test suite uses `respx` to mock the OpenViking HTTP layer, and asserts
each tool calls the correct upstream method/path/body and forwards tenant
headers verbatim.

## Limitations

- **No streaming.** Open WebUI tools are request/response. Live transcript
  streaming is out of scope for this plugin.
- **No file uploads.** `ov_add_resource` accepts a remote URL or a path the OV
  server can reach itself. To upload binary blobs, hit the OV server's
  `temp_upload` endpoint directly.
- **No write-side memory deletion / move tools.** Read-mostly by design; users
  who want destructive operations should use the OV CLI.
- **Single tenant per process.** Tenant identity comes from env vars, so run
  one tool server per `(account, user)` pair if you need to multiplex.
- **No bundled Open WebUI instance.** This is a tool server only — bring your
  own Open WebUI.

## Roadmap

Adding a new tool is roughly:

1. Add a Pydantic request model in `openviking_openwebui/tools.py`.
2. Add a route handler decorated with `@router.post("/tools/<name>", operation_id="<name>")`.
3. Forward to the OpenViking endpoint via `OVClient`.
4. Add a test in `tests/test_tools.py` mocking the upstream call.

Likely candidates the community might want next: `ov_session_create`,
`ov_session_commit`, `ov_grep`, `ov_glob`, `ov_overview`, `ov_abstract`.

## Security

- Never commit `OV_API_KEY` to source control. Pass it via the environment.
- The tool server has no auth of its own — bind it to localhost or a private
  network, or front it with a proxy that enforces auth.
- Tenant identity is server-side trust: anyone with `OV_API_KEY` and the
  right `X-OpenViking-Account/User` headers can read that tenant's data. This
  matches OpenViking's standard trust model.

---

## 中文說明

這是一個獨立的 FastAPI 服務，將 OpenViking 的一組核心 HTTP 端點封裝為
**OpenAPI 工具**，供 Open WebUI 自動發現並呼叫。

### 它做什麼

Open WebUI 支援兩種工具整合方式：把 Python "Functions" 貼上進管理後臺，
或對接外部 OpenAPI 工具伺服器（自動從 `/openapi.json` 發現工具）。
本外掛實現第二種方式——純 HTTP 轉發，不重複實現任何業務邏輯。

### 暴露的 7 個工具

`ov_search`、`ov_recall_memories`、`ov_add_memory`、`ov_list_memories`、
`ov_read_resource`、`ov_add_resource`、`ov_session_status`。詳見上方表格。

### 快速開始

```bash
cd examples/openwebui-plugin
pip install -e .
OV_API_KEY=your-key python -m openviking_openwebui
```

預設監聽 `0.0.0.0:8765`。

### 接入 Open WebUI

進入 Open WebUI 的 **設定 → 工具 → 新增工具伺服器**，貼上
`http://localhost:8765`。Open WebUI 會自動讀取 `/openapi.json`
並把全部 7 個工具暴露給模型。

### 環境變數

`OV_ENDPOINT`、`OV_API_KEY`、`OV_ACCOUNT`、`OV_USER`、`OV_AGENT`、`OV_BIND`、
`OV_TIMEOUT`。預設值與說明見上方英文表格。

### 測試

```bash
pip install -e ".[test]"
pytest tests -x -q
```

### 添加更多工具

1. 在 `openviking_openwebui/tools.py` 中新增 Pydantic 請求模型；
2. 新增路由 handler，設定 `operation_id`；
3. 通過 `OVClient` 轉發到對應 OpenViking 端點；
4. 在 `tests/test_tools.py` 中加 mock 測試。
