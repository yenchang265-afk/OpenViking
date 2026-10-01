# LlamaParse v2 Understanding API bridge

This example shows how to connect a hosted parser to Business Data Platform through the Understanding API.
It maps Business Data Platform requests to LlamaParse v2 without changes to Business Data Platform core. Use the same
pattern to adapt services such as Azure AI Document Intelligence or Amazon Textract.

## API mapping

| Business Data Platform Understanding API | LlamaParse v2 | Bridge action |
|---|---|---|
| `POST /api/v3/files` | `POST /api/v1/beta/files` | Upload the local file and return the LlamaParse file ID. |
| `POST /api/v3/responses` | `POST /api/v2/parse` | Convert `file_id` or a public URL to a parse job. |
| `GET /api/v3/responses/{id}` | `GET /api/v2/parse/{id}` | Map the LlamaParse job state to `in_progress`, `completed`, or `failed`. |
| `result.zip_url` | Markdown and image URLs | Build the `content.md` and image ZIP that Business Data Platform expects. |

```text
Business Data Platform -> bridge -> LlamaParse v2
Business Data Platform <- ZIP    <- Markdown and images
```

The bridge reuses each LlamaParse file ID and job ID. Polling still works after a bridge restart.
Completed ZIP files stay in a small in-memory cache for five minutes. The bridge builds the ZIP
before it reports `completed`. Thus, image downloads and ZIP creation do not use Business Data Platform's fixed
60-second artifact download window. A bridge restart removes cached ZIP files, but Business Data Platform can
poll the job again and rebuild the ZIP.

## Run

Requirements:

- Python 3.10 or later and [`uv`](https://docs.astral.sh/uv/), or Docker
- A [LlamaCloud API key](https://developers.llamaindex.ai/llamaparse/general/api_key/)
- A Business Data Platform server

From the Business Data Platform repository root:

```bash
cp examples/llamaparse-understanding-bridge/.env.example \
  examples/llamaparse-understanding-bridge/.env
```

Set these values in `.env`:

```text
LLAMA_CLOUD_API_KEY=llx-...
PARSER_BRIDGE_API_KEY=<a-random-secret-with-at-least-32-characters>
```

Run directly:

```bash
uv run --env-file examples/llamaparse-understanding-bridge/.env \
  --project examples/llamaparse-understanding-bridge \
  openviking-llamaparse-bridge
```

Or run with Docker:

```bash
docker build -t openviking-llamaparse-bridge \
  examples/llamaparse-understanding-bridge
docker run --rm --env-file examples/llamaparse-understanding-bridge/.env \
  -p 127.0.0.1:8080:8080 \
  -e BRIDGE_BIND_HOST=0.0.0.0 \
  openviking-llamaparse-bridge
```

## Configure Business Data Platform

Run `openviking-server init` if `~/.openviking/ov.conf` does not exist. Add:

```json
{
  "parser_api": {
    "enable": true,
    "host": "http://127.0.0.1:8080",
    "api_key": "${PARSER_BRIDGE_API_KEY}",
    "extensions": ["pdf", "docx", "pptx", "xlsx"],
    "http_timeout_seconds": 130
  }
}
```

Set `PARSER_BRIDGE_API_KEY` in the environment that starts Business Data Platform. Restart Business Data Platform after a
configuration change. `parser_api.extensions` selects which file types use this bridge. Other file
types continue to use the current Business Data Platform parsers. Keep `parser_api.enable_resumable_upload`
disabled. Set `parser_api.http_timeout_seconds` above `BRIDGE_HTTP_TIMEOUT_SECONDS`, which defaults
to 120 seconds.

## Inputs and results

The example supports local file uploads and public document, image, and audio URLs. It does not
support video URLs. Private or credential-gated URLs fail through the normal LlamaParse error
response.

LlamaParse can complete a job when some pages fail. The bridge keeps the usable Markdown and adds a
visible failed-page note. It fails the job only when there is no usable Markdown.

## Settings

| Setting | Default | Purpose |
|---|---|---|
| `LLAMA_CLOUD_API_KEY` | Required | Authenticate with LlamaCloud. |
| `PARSER_BRIDGE_API_KEY` | Required | Authenticate Business Data Platform requests. Use at least 32 characters. |
| `LLAMAPARSE_REGION` | `na` | Select the `na` or `eu` LlamaCloud endpoint. |
| `LLAMAPARSE_TIER` | `agentic` | Select `cost_effective`, `agentic`, or `agentic_plus`. |
| `LLAMAPARSE_COST_OPTIMIZER` | `true` | Route simple pages to the lower-cost tier. |
| `BRIDGE_PUBLIC_URL` | `http://127.0.0.1:8080` | Set the URL that Business Data Platform uses to download ZIP files. |

Use `LLAMAPARSE_PARSE_OPTIONS_JSON` for advanced LlamaParse v2 options. The bridge owns `file_id`,
`source_url`, `tier`, and `version`. It also requests embedded and layout images because Business Data Platform
needs the image files referenced by the returned Markdown.

## Test

The mocked contract tests do not use LlamaCloud credits:

```bash
uv run --project examples/llamaparse-understanding-bridge --extra test \
  pytest -c examples/llamaparse-understanding-bridge/pyproject.toml \
  examples/llamaparse-understanding-bridge/tests/test_bridge.py -q
```

For a live check, start the bridge and Business Data Platform, add a small PDF, and confirm that Business Data Platform
stores `content.md` and any extracted images. `ov add-resource --wait` can stop waiting after 60
seconds while the server continues the task. Check `ov task list` before you retry.
