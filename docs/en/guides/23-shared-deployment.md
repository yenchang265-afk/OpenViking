# Shared state and multiple server replicas

Set `server.deployment_mode` to `shared` when server pods must be disposable.
Standalone mode remains the default and continues to support local storage.
Use a build containing these backends; changing the configuration of an older
image does not add them.

| Authority | Shared backend |
|---|---|
| Content, sessions, staged sources, upload sessions, runtime account/cluster settings | S3 through AGFS; MySQL + S3 when tiered |
| Git version objects and refs, when enabled | Shared S3 or AGFS Git backend |
| Vectors | Elasticsearch, openGauss, or a remote vector HTTP service |
| Queues, path locks, coherent filesystem cache | Redis |
| Account identities and API keys | MySQL |
| Task and Work records | MySQL |
| OAuth registrations, pending authorizations, codes and tokens | MySQL |
| Usage projections and request audit history | MySQL |
| One-use MCP upload/download credentials | Redis |

All replicas must use the same `service_name`, backend namespaces, S3 bucket and
prefix, vector collection, model configuration, credentials, and encryption root
key. Different deployments need distinct namespaces. Redis must retain queue,
lock, and transfer state: enable persistence and use a no-eviction policy. Transfer
tokens require Redis 6.2 or later (`GETDEL`). Install the existing `mysql` and
`expiry` extras when building a Python environment.

The filesystem cache must use `backend: cache` and `multi_instance: true`.
Set `cache.params.default_ttl_seconds` to a positive value. Disable the S3
plugin's per-process metadata cache with `storage.agfs.s3.cache_enabled: false`.
Shared mode validates these choices before serving requests. It also rejects
embedded gateway/bot processes, local authorities, and multi-write backups.
Run the gateway separately with its supported shared-storage configuration.

QueueFS must use `mode: shared`. Choose a positive `recover_stale_sec` longer
than the maximum permitted job duration; the example uses one day. The standalone
default of zero recovers all processing messages at startup and is rejected here
because other replicas may still be executing them. Recovery after a worker crash
can therefore be delayed by this threshold. Validate recovery timing with your
own ingestion sizes before deployment.

Resource watches use `storage.watch_store.provider: mysql` in shared mode.
Provision `openviking/service/sql/001_watch_tasks.sql` and configure the same
`storage.watch_store.params.credential_encryption_key` on every replica (a
base64-encoded 32-byte key). Watch connections inherit `connections.mysql`.
Every replica serves the Watch API. Set `enable_watch_scheduler: true` on
replicas that should participate in scheduling, with `watch_leader_provider`
set to `auto` or `cache`; both use the shared Redis leader lease with MySQL.
Replicas with scheduling disabled still serve watch requests. File watch stores
and process-local leadership are rejected in shared mode. Existing file watch
records are not automatically migrated to MySQL.

Workers may keep scratch files, downloaded inputs, open connections, and derived
in-memory caches. No later request should require a previous request's pod.
Uploads must use shared mode; an explicit local upload is rejected. Transfer
credentials bind the original identity, OAuth origin, peer scope, permissions,
and operation. Upload and download credentials occupy separate namespaces and
are consumed atomically, including when requests reach different workers.

Task streams send periodic `resync` events in shared mode. Clients re-read the
authorized task list on `ready` and `resync`, so work performed on another pod
becomes visible. `ready.complete` is false: the local `task` frames alone are not
a complete cluster change log. No Redis notification delivery guarantee is
required; MySQL remains the task authority.

## Provision and deploy

The [shared Helm values](https://github.com/yenchang265-afk/OpenViking/blob/main/examples/k8s-helm/shared-values.yaml) provide an
overlay for two replicas with disposable `emptyDir` workspaces. Fill in service
addresses, TLS settings, model credentials, and the referenced Kubernetes Secret.
Keep startup configuration identical and managed externally. The startup-file
editor is read-only in shared mode; runtime account/cluster settings continue to
use their shared AGFS documents.

Configure MySQL once in `connections.mysql` (host, port, database, user, password,
and optional `ssl`). Every selected MySQL backend inherits those connection
details automatically, including tiered AGFS. No connection name or separate
DSN environment variable is needed. Backend selections remain explicit;
defining a connection does not enable a subsystem. Pool sizes, tables and retention
stay in their subsystem settings.

Configure the other shared services in `connections.redis`, `connections.s3`, and
`connections.elasticsearch`. Redis endpoint/topology/authentication settings feed
`cache.params`; TTL and pool settings stay in `cache.params`. S3 endpoint, bucket,
region, and credentials feed the selected AGFS and Git S3 backends; prefix and cache
policy stay local. Elasticsearch hosts, authentication, and TLS feed the selected
vector backend; index and request policies stay local.

Storage selectors use `backend`, including cache, path locks, task/account stores,
and transfer tokens. The old `provider` spelling remains accepted; conflicting
`backend` and `provider` values are rejected. LLM `provider` still selects a model
vendor. Complete inline connections remain independent overrides. When central
connections exist, partial connection overrides are rejected: Redis requires
`endpoints`, S3 requires endpoint/region/bucket/access_key/secret_key, and
Elasticsearch requires `hosts`. Secrets from central and inline connections are
never combined.

Using the central connection for tiered storage requires a matching rebuilt native
extension: startup refuses an older binding rather than allowing it to silently
use a legacy DSN environment variable.

Complete legacy inline connections remain supported as independent overrides.
With central defaults present, a partial inline host/user/password/database/TLS
override is rejected to avoid accidentally mixing credentials. Tiered storage
can still use a separately configured legacy `mysql.dsn_env`; an explicit
`dsn_env` overrides the central connection for that mount. Credentials and TLS
settings must match on every replica. `ssl: true` verifies the certificate and
hostname in both Python and native storage; custom CA/client certificates use
`ssl: {"ca": "/path/ca.pem", "cert": "/path/client.pem", "key": "/path/client.key"}`.

The example enables size-tiered AGFS storage: files smaller than 1 MiB and the
path index live in MySQL; larger files live in S3. Git storage defaults to the tiered
AGFS backend too. Tiered AGFS creates its index tables on first mount. Table names are optional: the
defaults are `agfs_entries` and `agfs_git_entries` for Git; set a custom table only
when separate namespaces need isolation. For an
existing untiered bucket, stop untiered writers and follow the
[tiered-storage migration instructions](01-configuration.md#size-tiered-storage)
before starting replicas; `import_existing` stays false in the example.

Provision account and task tables through your database migration system using:

- `openviking/server/account_stores/sql/init.sql` and applicable changes;
- `openviking/service/sql/task_store_init.sql` and applicable changes;
- `openviking/service/sql/001_watch_tasks.sql` for watches.

Provision OAuth and usage/audit tables from the same configuration the server
will load. Review the DDL first, then explicitly apply it:

```sh
python -m openviking.server.shared_schema --config ov.conf
python -m openviking.server.shared_schema --config ov.conf --apply
```

This creates missing tables; it never drops, resets, or migrates existing data.
Server startup checks schemas but does not create them. Separate database users
can be configured for accounts, tasks, OAuth, and audit storage.

```sh
helm upgrade --install openviking ./deploy/helm/openviking \
  -f examples/k8s-helm/shared-values.yaml --set image.tag=<compatible-build>
```

Shared mode uses RollingUpdate, rejects a shared workspace PVC, and permits
multiple replicas. Standalone mode keeps Recreate and the single-replica guard.
Collect logs and metrics centrally; counters and open streams remain per-process.

## Transition an existing installation

Changing a backend selection does **not** migrate its data. Before switching:

1. Back up the current workspace and all external stores. Stop new mutations and
   drain the old queue before stopping every writer.
2. Copy persisted AGFS data to the chosen shared namespace and rebuild or migrate
   the vector index. Preserve embedding dimensions and collection settings.
3. Migrate account identities and keys into the relational account store. Preserve
   identifiers and key semantics; verify existing credentials before reopening
   traffic. Persisted Task records need a separate migration if history is required.
4. Existing SQLite OAuth grants are not imported automatically. Either migrate
   them explicitly or require clients to register and authorize again. Retain the
   SQLite database for rollback. Audit history likewise stays in its previous store
   unless explicitly imported.
5. Start one server with the shared profile, verify identities and data, then add
   a second replica. Alternate requests between pods, including upload/consume,
   OAuth code exchange, session mutation, task lookup, and key revocation.
6. Verify worker termination during ingestion and session commit recovers accepted
   work without duplicate effects before adopting the profile in production.

Rollback must account for writes accepted after cutover. Returning to an old
workspace snapshot would lose those writes; stop writers and migrate them back
or restore a consistent backup of **all** authorities together.

Focused shared-store tests live in `tests/server/test_shared_transfer_tokens.py`
and `tests/server/test_shared_mysql_state.py`. The MySQL tests require an isolated
`ov_stateless_test` database and an explicit `OV_TEST_MYSQL_PORT`; they exercise
independent connections, one-shot races, replay tombstones, cross-pod visibility,
concurrent usage increments, and parity with the standalone SQLite reader.
