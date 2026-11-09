# Deployment mode examples

Three `ov.conf` starting points. Copy one to `~/.openviking/ov.conf`, then set the
`${...}` variables in the server's environment. An unset `${VAR}` fails startup.

| File | Mode | Storage | Replicas |
|---|---|---|---|
| `ov.conf.standalone-local.example` | `standalone` | Local files, local vector store, no external services | 1 |
| `ov.conf.standalone-shared-stack.example` | `standalone` | S3 + MySQL + Redis + Elasticsearch | 1 |
| `ov.conf.shared.example` | `shared` | S3 + MySQL + Redis + Elasticsearch | 1 or more |

The last two differ only in `server.deployment_mode`. `shared` adds:

- Startup validation that rejects any local authority.
- A read-only startup-file editor in Studio.
- Task streams that send `resync` events, so work on other replicas becomes visible.

## Before starting

All three use Ollama for models, so the listed models must be pulled. The stack
examples use the host names of this repo's Docker Compose sidecars; change them
to match your services, and use TLS and Elasticsearch credentials outside local
development.

Stack variables:

| Variable | Value |
|---|---|
| `OPENVIKING_ROOT_API_KEY` | Random secret |
| `OPENVIKING_MYSQL_PASSWORD` | MySQL or MariaDB password |
| `OPENVIKING_REDIS_PASSWORD` | Redis password |
| `OPENVIKING_S3_ACCESS_KEY`, `OPENVIKING_S3_SECRET_KEY` | S3 credentials |
| `OPENVIKING_ENCRYPTION_ROOT_KEY` | `openssl rand -hex 32` |
| `OPENVIKING_WATCH_ENCRYPTION_KEY` | `openssl rand -base64 32` |

`ov.conf.standalone-local.example` needs only `OPENVIKING_ROOT_API_KEY`.

Provision the stack schemas first; startup checks them but does not create them.
See [Shared state and multiple server replicas](../../docs/en/guides/23-shared-deployment.md#provision-and-deploy).

Changing examples does not migrate data. To move an existing installation, follow
the guide's transition steps.

`encryption.root_key` protects saved credentials even though file encryption stays
off. Keep it safe: every replica must use the same value. Add `"enabled": true`
under `encryption` to encrypt file content as well.

Keep `server.with_bot: false` on the stack examples and run VikingBot separately;
the guide covers the setup.
