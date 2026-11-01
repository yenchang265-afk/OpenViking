# OpenViking Helm Chart

Deploy OpenViking on Kubernetes using Helm.

## Prerequisites

- Kubernetes 1.24+
- Helm 3.x
- A storage class that supports `ReadWriteOnce` persistent volumes (single replica only;
  see [Multiple replicas](#multiple-replicas) for shared backends)

## Installation

### Quick Start

```bash
helm install openviking ./deploy/helm/openviking \
  --set-string config.server.root_api_key="YOUR_ROOT_API_KEY" \
  --set-string config.embedding.dense.api_key="YOUR_VOLCENGINE_API_KEY" \
  --set-string config.vlm.api_key="YOUR_VOLCENGINE_API_KEY"
```

The chart deploys `ghcr.io/volcengine/openviking:latest` by default. To choose
a different image tag:

```bash
# newest image from the main branch
helm upgrade --install openviking ./deploy/helm/openviking --set image.tag=main

# pinned release image
helm upgrade --install openviking ./deploy/helm/openviking --set image.tag=v0.3.17

# use the default latest image
helm upgrade --install openviking ./deploy/helm/openviking --set image.tag=
```

We recommend the `ghcr.io` image. If `ghcr.io` is hard to reach, add
`--set image.repository=openviking-cn-beijing.cr.volces.com/volcengine/openviking`.

### Install with Custom Values

Create a `my-values.yaml` file:

```yaml
replicaCount: 1

resources:
  limits:
    cpu: "4"
    memory: 8Gi
  requests:
    cpu: "1"
    memory: 2Gi

persistence:
  size: 50Gi
  storageClass: "gp3"

config:
  storage:
    workspace: /app/.openviking/openviking_workspace
  log:
    level: INFO
    output: stdout
  server:
    host: "0.0.0.0"
    port: 1933
    workers: 1
    root_api_key: "your-secret-key"
  embedding:
    dense:
      api_base: "https://ark.cn-beijing.volces.com/api/v3"
      api_key: "your-volcengine-api-key"
      provider: "volcengine"
      dimension: 1024
      model: "doubao-embedding-vision-251215"
      input: "multimodal"
    max_concurrent: 10
  vlm:
    api_base: "https://ark.cn-beijing.volces.com/api/v3"
    api_key: "your-volcengine-api-key"
    provider: "volcengine"
    model: "doubao-seed-2-0-lite-260428"
    temperature: 0.0
    max_retries: 2
    thinking: false
    max_concurrent: 100
```

Then install:

```bash
helm install openviking ./deploy/helm/openviking -f my-values.yaml
```

### Using Secrets for API Keys

For production, avoid putting API keys directly in values. Use `extraEnv` with
Kubernetes secrets instead:

```bash
# Create a secret
kubectl create secret generic openviking-api-keys \
  --from-literal=root-api-key="YOUR_ROOT_API_KEY" \
  --from-literal=embedding-api-key="YOUR_KEY" \
  --from-literal=vlm-api-key="YOUR_KEY"
```

Then reference it in your values:

```yaml
config:
  server:
    root_api_key: "${OPENVIKING_ROOT_API_KEY}"
  embedding:
    dense:
      api_key: "${OPENVIKING_EMBEDDING_API_KEY}"
  vlm:
    api_key: "${OPENVIKING_VLM_API_KEY}"

extraEnv:
  - name: OPENVIKING_ROOT_API_KEY
    valueFrom:
      secretKeyRef:
        name: openviking-api-keys
        key: root-api-key
  - name: OPENVIKING_EMBEDDING_API_KEY
    valueFrom:
      secretKeyRef:
        name: openviking-api-keys
        key: embedding-api-key
  - name: OPENVIKING_VLM_API_KEY
    valueFrom:
      secretKeyRef:
        name: openviking-api-keys
        key: vlm-api-key
```

OpenViking expands environment variables inside `ov.conf` at startup, so the
ConfigMap can contain placeholders while the actual secrets stay in Kubernetes
Secrets.

### Multiple replicas

By default the chart runs one pod with a `ReadWriteOnce` volume. To run several API
replicas, keep no state in the pods and set `multiInstance.enabled: true`. Every replica
then needs the same shared backends:

| State | Setting | Why |
|---|---|---|
| Files | `config.storage.agfs.backend: s3` (optionally `tiered` to MySQL/MariaDB) | Local AGFS would give each pod its own files |
| Vectors | `config.storage.vectordb.backend: elasticsearch`, `http` or `opengauss` | The embedded `local`/`cuvs` store locks the workspace to one process |
| Locks, queue, file cache | `config.cache.provider: redis`, `pathlock.provider: cache` (and usually `queuefs.backend: cache`, `cachefs.backend: cache`) | Pods coordinate through Redis |
| Tasks | `config.storage.task_store.provider: mysql` | The file Task store counts open work in process memory; a Task whose work another pod finishes would wait forever |

`helm install` fails with an explanation when one of these is missing, or when
`replicaCount > 1` without `multiInstance.enabled`. The gateway, OAuth and the bot keep
their state in the pod's workspace, so they are refused in this mode.

In multi-instance mode the chart:

- gives each pod an `emptyDir` workspace (`multiInstance.workspaceSizeLimit`) instead of
  the PVC, and sets `OV_INSTANCE_ID` to the pod name;
- sets `storage.agfs.cachefs.multi_instance: true` (when CacheFS uses the cache),
  `server.temp_upload.default_mode: shared`, and, with the default `file` account store,
  `server.api_key_watch_enabled: true` with a 10 s poll so users and keys created on one
  pod reach the others. Values you set explicitly in `config` win;
- runs the watch scheduler in a separate single-replica `<release>-scheduler` Deployment
  (`Recreate`, no Service traffic) and turns it off on the API replicas, so each due watch
  runs once. Disable it with `multiInstance.scheduler.enabled: false` if you do not use
  watches;
- rolls out API replicas with `RollingUpdate` (`maxSurge: 1`, `maxUnavailable: 0`).
  Override with `strategy`. Use `Recreate` for a release that changes the CacheFS format,
  because old and new versions must not share a cache namespace.

Before the first install, create the Task store tables from
`openviking/service/sql/task_store_init.sql`. Keep secrets out of the ConfigMap: put every
`${VAR}` the config references in one Secret and load it with `envFrom`.
[`values-multi-instance.yaml`](openviking/values-multi-instance.yaml) is a complete example:

```bash
kubectl create secret generic openviking-secrets \
  --from-literal=OPENVIKING_ROOT_API_KEY="$(openssl rand -base64 32)" \
  --from-literal=REDIS_PASSWORD=... \
  --from-literal=S3_ACCESS_KEY=... --from-literal=S3_SECRET_KEY=... \
  --from-literal=MARIADB_PASSWORD=... \
  --from-literal=RAGFS_TIERED_DSN="mysql://openviking:<MARIADB_PASSWORD>@mariadb:3306/openviking" \
  --from-literal=OPENAI_API_KEY=...
helm install openviking ./deploy/helm/openviking \
  -f deploy/helm/openviking/values-multi-instance.yaml
```

Probes stay as they are: liveness on `/health`, readiness on `/ready`. `/ready` returns 503
while the cache provider is unreachable, which takes a pod out of the Service without
restarting it. Do not point liveness at `/ready`, or a Redis outage restarts every pod at
once. Set `OPENVIKING_PUBLIC_BASE_URL` (or `config.server.public_base_url`) to the address
clients use, because MCP upload and download links are built from it.

Sizing: each pod opens up to 16 MySQL connections for the tiered store plus the Task store
pool, so check the database's `max_connections` against the replica count. Each pod also
runs its own queue workers against the embedding and VLM providers; lower
`config.queue_workers` if a self-hosted model server cannot keep up.

### OpenViking Gateway

Set `gateway.enabled: true` to run [OpenViking Gateway](https://docs.openviking.ai/en/guides/15-gateway)
inside the server container. The chart adds `gateway.enabled` to `ov.conf` and stores
gateway data in `<persistence.mountPath>/gateway` on the persistent volume. There is no
sidecar and no extra Service port: clients use `/gateway` on the server port, and the existing Ingress
forwards every path to OpenViking.

Model requests stream, so the Ingress must turn off response buffering and allow request
bodies of at least 32 MiB and timeouts of 600 seconds. The chart does not set these
annotations for you. With NGINX:

```yaml
gateway:
  enabled: true
  existingSecret: ""  # optional: Secret with a management-key entry
config:
  server:
    auth_mode: api_key
  gateway:
    public_url: https://ov.example.com
ingress:
  enabled: true
  className: nginx
  annotations:
    nginx.ingress.kubernetes.io/proxy-buffering: "off"
    nginx.ingress.kubernetes.io/proxy-request-buffering: "off"
    nginx.ingress.kubernetes.io/proxy-body-size: 32m
    nginx.ingress.kubernetes.io/proxy-read-timeout: "600"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "600"
  hosts:
    - host: ov.example.com
      paths:
        - path: /
          pathType: Prefix
```

Set `config.gateway.public_url` to the address clients use, without `/gateway`; Studio's
setup guides and file upload links are built from it, with `/gateway` appended. Clients use
`https://ov.example.com/gateway/v1` (OpenAI-compatible) or `https://ov.example.com/gateway`
(Anthropic).

#### Secrets

The gateway encrypts its stored data with the server's `config.encryption` settings; with
server encryption off, it stores them unencrypted.

`gateway.existingSecret` optionally names a Secret. Both entries are optional:

- `management-key` (at least 32 characters) is passed as
  `OPENVIKING_GATEWAY_MANAGEMENT_KEY`. With it, only requests that carry this key can change
  upstreams and context profiles; see
  [Gateway management key](https://docs.openviking.ai/en/guides/22-gateway-operations#gateway-management-key).
- `encryption-key` is the v0.5.0 gateway key, passed as `OPENVIKING_GATEWAY_ENCRYPTION_KEY`.
  It is only read once, to migrate data stored by the v0.5.0 gateway.

```bash
kubectl create secret generic openviking-gateway \
  --from-literal=management-key="$(openssl rand -base64 32)"
```

Keep `replicaCount: 1` (and `multiInstance.enabled: false`): the gateway's SQLite databases serve one pod only. The default
local vectordb also locks the workspace to a single worker, so raise the server's `workers`
setting only after switching to a remote vectordb backend such as VikingDB.

#### Upgrading from the sidecar chart

- Keep the persistent volume. On first start the server re-encrypts the gateway's stored
  data with its own encryption settings, reading the old key from the `encryption-key`
  entry of `gateway.existingSecret` or from `encryption.key` in the gateway storage
  directory. If old encrypted data exists and neither is present, the server refuses to start.
  Keep the `encryption-key` entry for the upgrade release only; after the server has started
  once, the key is no longer read and you can remove the entry.
- Remove `gateway.port`, `gateway.workers` and `gateway.resources`.
- Remove `host`, `port`, `workers`, `url`, `openviking_url` and `admin_token_env` from
  `config.gateway`. The server ignores them with a startup warning.
- Point `config.gateway.public_url` at the server's public address, not port 1935, and
  move clients to the server port and the `/gateway` prefix: `http://host:1935/v1` becomes
  `https://ov.example.com/gateway/v1`. The management API moved from
  `/api/v1/admin/gateway/...` to `/gateway/admin/...`.
- The shared admin token is gone and does not act as a management key. To restrict
  changes to upstreams and context profiles, add a `management-key` entry to
  `gateway.existingSecret`.

For deployment, Studio management, backups and troubleshooting, see
[OpenViking Gateway deployment and operations](https://docs.openviking.ai/en/guides/22-gateway-operations).

## Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `replicaCount` | Number of API replicas; more than 1 requires `multiInstance.enabled` | `1` |
| `multiInstance.enabled` | Run several replicas against shared backends (see [Multiple replicas](#multiple-replicas)) | `false` |
| `multiInstance.workspaceSizeLimit` | `emptyDir` size limit for each pod's workspace | `""` |
| `multiInstance.scheduler.enabled` | Run the watch scheduler in a separate single-replica Deployment | `true` |
| `multiInstance.scheduler.resources` | Resources for the scheduler pod (defaults to `resources`) | `{}` |
| `strategy` | Deployment strategy; empty = `Recreate`, or `RollingUpdate` in multi-instance mode | `{}` |
| `envFrom` | Extra environment sources, e.g. a Secret holding every `${VAR}` in `config` | `[]` |
| `podDisruptionBudget.enabled` | Create a PodDisruptionBudget for the API pods | `false` |
| `podDisruptionBudget.minAvailable` | Minimum available API pods | `1` |
| `image.repository` | Container image repository | `ghcr.io/volcengine/openviking` |
| `image.tag` | Container image tag (`latest`, `main`, pinned release, or empty for `latest`) | `latest` |
| `image.pullPolicy` | Image pull policy | `Always` |
| `service.type` | Kubernetes service type | `ClusterIP` |
| `service.port` | Service port | `1933` |
| `persistence.enabled` | Enable persistent storage | `true` |
| `persistence.size` | PVC size | `20Gi` |
| `persistence.storageClass` | Storage class name | `""` (default) |
| `persistence.mountPath` | Container path for OpenViking persistent state | `/app/.openviking` |
| `bot.enabled` | Start vikingbot alongside the API server | `false` |
| `persistence.existingClaim` | Use an existing PVC | `""` |
| `resources.limits.cpu` | CPU limit | `2` |
| `resources.limits.memory` | Memory limit | `4Gi` |
| `resources.requests.cpu` | CPU request | `500m` |
| `resources.requests.memory` | Memory request | `1Gi` |
| `ingress.enabled` | Enable ingress | `false` |
| `config.server.root_api_key` | API key required when server binds to 0.0.0.0 | `""` |
| `config` | Full ov.conf configuration object | See `values.yaml` |
| `extraEnv` | Additional environment variables | `[]` |
| `gateway.enabled` | Run OpenViking Gateway inside the server container, under `/gateway` on the server port | `false` |
| `gateway.existingSecret` | Optional Secret with optional entries `management-key` (required to change upstreams and context profiles) and `encryption-key` (v0.5.0 key, read once for migration) | `""` |

## Upgrading

```bash
helm upgrade openviking ./deploy/helm/openviking -f my-values.yaml
```

A single-replica deployment uses a `Recreate` strategy so two pods never open the same
embedded vector store volume at once. Multi-instance deployments roll out with
`RollingUpdate`; see [Multiple replicas](#multiple-replicas).

## Uninstalling

```bash
helm uninstall openviking
```

Note: The PersistentVolumeClaim is retained by Helm and becomes orphaned after
uninstall. Delete it explicitly to remove the stored data:

```bash
kubectl delete pvc openviking-data
```
