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

`ov.conf.standalone-local.example` needs only `OPENVIKING_ROOT_API_KEY`.

Changing examples does not migrate data. To move an existing installation, follow
the transition steps in
[Shared state and multiple server replicas](../../docs/en/guides/23-shared-deployment.md#transition-an-existing-installation).

## First-time setup on the stack examples

These steps start a new deployment from an image, with the storage services
already running. The local example skips step 4.

| Service | Must be ready |
|---|---|
| MySQL or MariaDB | Empty database and user; startup checks tables but does not create them |
| Redis | Version 6.2 or later, `noeviction`, persistence on |
| S3 | Bucket already exists |
| Elasticsearch | Reachable; the index is created automatically |
| Models | Embedding and VLM endpoints reachable, models pulled |

Use a fresh database, bucket or prefix, and `service_name` for each deployment,
or its data will mix with whatever already uses them.

### 1. Load the image

```sh
IMAGE=<image:tag>
docker pull "$IMAGE"    # or: docker load -i image.tar
```

### 2. Generate secrets

```sh
mkdir -p /srv/openviking && cd /srv/openviking && umask 077
cat > ov.env <<E
OPENVIKING_ROOT_API_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')
OPENVIKING_ENCRYPTION_ROOT_KEY=$(openssl rand -hex 32)
OPENVIKING_WATCH_ENCRYPTION_KEY=$(openssl rand -base64 32)
OPENVIKING_MYSQL_PASSWORD=<db password>
OPENVIKING_REDIS_PASSWORD=<redis password>
OPENVIKING_S3_ACCESS_KEY=<s3 key>
OPENVIKING_S3_SECRET_KEY=<s3 secret>
E
```

Back up `OPENVIKING_ENCRYPTION_ROOT_KEY` separately from the data. Losing it loses
saved credentials and any encrypted files.

### 3. Write `ov.conf`

Copy an example to `/srv/openviking/ov.conf`, then set your service hosts,
`service_name`, S3 bucket and prefix, and models.

### 4. Create tables

Apply [`schema.sql`](schema.sql) once, connected to the empty database, using a
`mysql` or `mariadb` client (the image has none). Or paste the whole file into your
SQL client and run it top to bottom.

```sh
mysql -h <db host> -u openviking -p openviking < schema.sql
```

This creates 12 tables, including `ov_oauth_records`, which stays unused while OAuth
is off. A second run fails on existing tables. The server creates its tiered storage
tables itself on first mount.

`schema.sql` is a snapshot of one image, named in its header. If your image is newer,
compare these against the header's image, and apply anything new in number order:

- `openviking/server/account_stores/sql/changes/`
- `openviking/service/sql/changes/`
- `python -m openviking.server.shared_schema --config <ov.conf>`, which prints the
  usage, audit and OAuth DDL for what the config enables

### 5. Start one instance

```sh
docker run -d --name openviking --network <net> \
  -p 127.0.0.1:1933:1933 -v "$PWD:/app/.openviking" --env-file ov.env \
  -e OPENVIKING_WITH_BOT=0 "$IMAGE" --without-bot

curl -s http://127.0.0.1:1933/ready
```

The entrypoint enables the bot by default and shared mode rejects an embedded bot,
so keep it disabled here. Wait for `"status":"ready"` with every check `ok`.

### 6. Create the first account

```sh
ROOT=$(grep '^OPENVIKING_ROOT_API_KEY=' ov.env | cut -d= -f2-)
curl -X POST http://127.0.0.1:1933/api/v1/admin/accounts \
  -H "X-API-Key: $ROOT" -H "Content-Type: application/json" \
  -d '{"account_id": "acme", "admin_user_id": "alice"}'
```

`user_key` in the response is that admin's API key, so save it.

### 7. Smoke test

```sh
curl -H "X-API-Key: <user_key>" 'http://127.0.0.1:1933/api/v1/fs/ls?uri=viking://'
```

Then log in at `http://127.0.0.1:1933/studio/` with the user key and upload a small
file. Confirm it indexes and that search finds it, which exercises S3, MySQL, Redis,
Elasticsearch and the embedding model together. The root key cannot call data APIs.

### 8. Add replicas and the bot

Both are optional. Give replicas the same `ov.conf` and secrets, and add them only
after step 7 passes. Run exactly one bot, separately, with persistent storage;
the guide's
[Separate VikingBot for Studio](../../docs/en/guides/23-shared-deployment.md#separate-vikingbot-for-studio)
section covers the setup.

## Notes

`encryption.root_key` protects saved credentials even though file encryption stays
off. Keep it safe: every replica must use the same value. Add `"enabled": true`
under `encryption` to encrypt file content as well.

Keep `server.with_bot: false` on the stack examples and run VikingBot separately;
the guide covers the setup.
