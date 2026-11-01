# Docker Compose: external state (S3 + Elasticsearch + Redis)

`ov.conf.example` here matches the optional profiles in the root
`docker-compose.yml`. With it, the OpenViking container keeps no queue, lock,
file or vector state of its own:

| State | Backend | Compose profile | Host inside the network |
|---|---|---|---|
| Files, sessions, API keys (AGFS) | S3 via SeaweedFS | `s3` | `seaweedfs:8333` |
| Vectors | Elasticsearch 8.x | `elasticsearch` | `elasticsearch:9200` |
| Job queue + path locks | Redis | `redis` | `redis:6379` |

Some files still live in the workspace (`/app/.openviking/data`): usage-audit
and OAuth SQLite databases, temp uploads and logs. Mount `/app/.openviking` if
you need those to survive container replacement.

## 1. Build the image

The Elasticsearch backend is not in the upstream image. Build this repo:

```bash
docker build -t openviking:local .
```

## 2. Create `.env` next to `docker-compose.yml`

```bash
OPENVIKING_IMAGE=openviking:local
OPENVIKING_ROOT_API_KEY=<random>
S3_ACCESS_KEY=<random>
S3_SECRET_KEY=<random>
S3_BUCKET=openviking
REDIS_PASSWORD=<random>
OPENAI_API_KEY=<your key>
```

Generate random values with e.g. `python3 -c "import secrets;print(secrets.token_urlsafe(32))"`.
`.env` is gitignored; never commit it.

## 3. Install the config

```bash
mkdir -p ~/.openviking
cp examples/docker-compose/ov.conf.example ~/.openviking/ov.conf
chmod 600 ~/.openviking/ov.conf
```

`ov.conf` expands `${VAR}` from the container environment at load time, and
Redis reads its password from `REDIS_PASSWORD` via `password_env`. The compose
`openviking` service passes all of these through from `.env`. An unset
variable is left as the literal text `${VAR}`, which then fails
authentication — check `.env` first if a backend rejects credentials.

Swap the `embedding` / `vlm` blocks for your provider. Keep the embedding
model and `dimension` fixed once data is indexed; changing them requires a
reindex.

## 4. Start

The sidecars also join the external `openviking-net` network, which must
exist first:

```bash
docker network create openviking-net   # once
docker compose --profile s3 --profile elasticsearch --profile redis up -d
```

`s3-init` creates the bucket once and exits. Check readiness:

```bash
curl -s http://127.0.0.1:1933/ready
```

## Running OpenViking outside compose

To run the app container separately (`docker run`), put it on the external
network the sidecars also join, and pass the same variables:

```bash
docker run -d --name openviking --network openviking-net -p 1933:1933 \
  --env-file .env -v ~/.openviking:/app/.openviking openviking:local
```

## Running several instances

`ov.conf.multi-instance.example` runs several OpenViking containers against the same
backends. On top of `ov.conf.example` it adds what each instance must share or keep
apart:

- `storage.task_store` on MySQL/MariaDB (`tiered` profile), so one instance can finish
  work queued by another;
- `storage.agfs.tiered` (small files and the path index in MariaDB);
- `cachefs.multi_instance: true` and a 600 s cache TTL;
- `server.api_key_watch_enabled`, so users and keys created on one instance reach the
  others within 10 s;
- `server.temp_upload.default_mode: shared`, so any instance can take an upload chunk;
- a usage-audit SQLite file per instance (`${OV_INSTANCE_ID}`);
- `enable_watch_scheduler` from `${OV_ENABLE_WATCH_SCHEDULER}`: `true` on exactly one
  instance, or every instance re-imports every due watch.

Add `MARIADB_PASSWORD` and `RAGFS_TIERED_DSN` to `.env`, start the `tiered` profile too,
and create the Task store tables once:

```bash
docker compose exec -T mariadb sh -c 'mariadb -uopenviking -p"$MARIADB_PASSWORD" openviking' \
  < openviking/service/sql/task_store_init.sql
```

Then give each container its own name, host port, `OV_INSTANCE_ID` and scheduler flag:

```bash
for i in a b; do
  docker run -d --name "openviking-$i" --network openviking-net \
    -p "$([ $i = a ] && echo 19331 || echo 19332):1933" --env-file .env \
    -e OPENVIKING_CONFIG_FILE=/app/.openviking/ov.conf.multi-instance \
    -e OV_INSTANCE_ID="$i" -e OV_ENABLE_WATCH_SCHEDULER="$([ $i = a ] && echo true || echo false)" \
    -e OPENVIKING_WITH_BOT=0 -v ~/.openviking:/app/.openviking openviking:local
done
```

with the example copied to `~/.openviking/ov.conf.multi-instance`. Put a load balancer
in front, with readiness on `/ready`: it returns 503 while Redis is unreachable. The
gateway, OAuth and vikingbot keep state in one instance's workspace, so leave them off.
For Kubernetes, the Helm chart's `multiInstance` mode applies the same settings; see
`deploy/helm/README.md`.

## Migrating an existing local install

Switching `vectordb` from `local` to `elasticsearch` starts with an empty
index. Rebuild vectors from stored content (no VLM calls) with an account
admin key — ROOT keys cannot call data APIs:

```bash
curl -X POST http://127.0.0.1:1933/api/v1/content/reindex \
  -H "X-API-Key: <admin-user-key>" -H 'Content-Type: application/json' \
  -d '{"uri": "viking://", "mode": "vectors_only", "wait": true}'
```

Switching `queuefs` to `cache` does not move queued jobs from the old SQLite
queue; let the queue drain before switching.

## Not for production as-is

The compose sidecars are for local use: Elasticsearch runs with security
disabled, and all three bind to `127.0.0.1` only. For production, use managed
or secured services (ES auth + TLS, Redis with persistence and auth, a real
S3 bucket) and point the same config keys at them.
