# OpenViking Helm Chart

Deploy OpenViking on Kubernetes using Helm.

## Prerequisites

- Kubernetes 1.24+
- Helm 3.x
- Single-instance mode (default): a storage class that supports `ReadWriteOnce`
  persistent volumes (for RocksDB data)
- Multi-instance mode: S3-compatible storage, Elasticsearch / openGauss (or an
  HTTP vector service) and Redis. See [Multi-instance mode](#multi-instance-mode).

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

### OpenViking Gateway

The chart can run [OpenViking Gateway](https://docs.openviking.ai/en/guides/15-gateway)
as a second container in the OpenViking pod, sharing its volume and `ov.conf`. The gateway
requires OpenViking Server to use API key authentication.

Create a Secret with the fixed keys `encryption-key` and `admin-token`:

```bash
kubectl create secret generic openviking-gateway \
  --from-literal=encryption-key="$(python3 -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')" \
  --from-literal=admin-token="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
```

Back up the encryption key along with the volume. The gateway can read its stored data only
with this exact key, and the key can't be rotated.

Then enable the gateway in your values:

```yaml
gateway:
  enabled: true
  existingSecret: openviking-gateway
  workers: 2

config:
  server:
    auth_mode: api_key
  gateway:
    public_url: https://ov.example.com
```

- The chart generates the rest of `config.gateway`: bind address, port, workers,
  internal URLs and a `storage_path` on the data volume. Values you set under
  `config.gateway` take precedence.
- Set `public_url` to the address clients use, written out literally. The gateway does not
  expand `${VAR}` placeholders, and its container does not receive `extraEnv`.
- With the ingress enabled, the chart routes `/v1`, `/api/v3`, `/api/compatible/v1` and
  `/gateway/uploads` to the gateway. It never routes the gateway's `/admin` paths;
  keep it that way in your own ingress rules.
- Keep `replicaCount: 1`. The gateway's storage must be used from a single host; scale with
  `gateway.workers` instead.

The chart does not set ingress annotations. Model requests stream and can be large, so turn off
proxy buffering and allow 32 MiB request bodies and 600-second read timeouts. For the NGINX
annotations, Studio setup and troubleshooting, see
[OpenViking Gateway deployment and operations](https://docs.openviking.ai/en/guides/22-gateway-operations#helm).

## Multi-instance mode

The default chart runs one pod. Its embedded vector store and local workspace
belong to that one process. Set `multiInstance.enabled: true` to run several
API replicas against shared backends instead:

```
Ingress (hash on Authorization)
  ├─ /api/v1/admin/*  → <release>-control  (1 pod, Recreate)
  └─ everything else  → <release>-api      (Deployment, optional HPA + PDB)
Shared: S3 · Elasticsearch/openGauss · Redis (queues + path locks)
```

Start from the example file. It is sized as a starting point for about 100k
employees with about 5k concurrently active:

```bash
helm upgrade --install openviking ./deploy/helm/openviking \
  -f deploy/helm/openviking/values-multi-instance.yaml \
  -f my-overrides.yaml
```

### What the chart does in this mode

- Renders `<release>-api` and `<release>-control` Deployments. Each pod gets
  an `emptyDir` for its local workspace. `replicaCount` and `persistence` are
  ignored.
- API pods get a config with `enable_watch_scheduler: false`,
  `memory.session_auto_commit.enabled: false` and
  `server.api_key_watch_enabled: true`, unless you set the last one yourself.
  These background jobs have no leader election, so only the control pod runs
  them, using `config` as you wrote it. The WatchScheduler is on by default.
  Session auto-commit is off by default; enable it under `config.memory` if
  you need it, and it will run on the control pod only.
- Routes `/api/v1/admin` to the control pod. User adds and key rotations merge
  into `users.json` under a cross-pod path lock. Deleting a user, however,
  rewrites the whole file from the pod's in-memory snapshot, which can drop
  users another pod just added. Keep admin writes on one pod, and apply the
  same rule in your own routing.
- Uses a rolling update with `maxUnavailable: 0`, a `preStop` sleep and a
  120-second termination grace. A clean shutdown removes the pod's Redis queue
  heartbeat, so its in-flight jobs are recovered. A crashed pod's jobs are only
  recovered the next time any instance starts.
- Refuses to render unless all of these hold:

  | Key | Required value |
  |---|---|
  | `config.storage.vectordb.backend` | not `local` or `cuvs` |
  | `config.storage.agfs.backend` | `s3` |
  | `config.cache.provider` | `redis` |
  | `config.storage.agfs.pathlock.namespace` | set |
  | `config.storage.agfs.queuefs.backend` | `cache` |
  | `config.storage.agfs.pathlock.provider` | `cache` |
  | `config.storage.agfs.cachefs.backend` | not `cache` (it assumes a single writer) |
  | `config.server.temp_upload.default_mode` | `shared` |
  | `gateway.enabled` | `false` (run the gateway as its own single-replica release) |

### Settings that matter at scale

- **`server.workers: 1`.** MCP upload tokens are process-local, and restart
  recovery needs a single worker. Scale with pods.
- **Affinity is best effort.** Hashing on the `Authorization` header
  (`nginx.ingress.kubernetes.io/upstream-hash-by`) usually keeps a caller on
  one pod, which MCP uploads and task-list cursors need, because each process
  holds its own upload tokens and signs cursors with its own key. A caller still
  moves to another pod when its token is refreshed or when pods are added or
  removed. An MCP upload or cursor in flight at that moment fails, and the
  client has to start it again.
- **`server.timeout_keep_alive`** must be higher than the load balancer's idle
  timeout (75 vs 60).
- **`cache.params.command_timeout_ms`.** The default of 20 ms times out under
  load. Use about 1000.
- **LLM concurrency.** `vlm.max_concurrent` (default 32) and
  `embedding.max_concurrent` (default 10) apply per process. Multiply by
  `maxReplicas` and keep the total under what the model backend can serve.
  OpenViking has no RPM/TPM limit, so enforce global limits in an LLM gateway
  such as LiteLLM.
- **Authentication.** For a large workforce, prefer `auth_mode: oidc` against
  company SSO and map `account_id` from a claim such as department. Per-user
  API keys don't scale well:
  - each user is created with its own admin call, because there is no bulk
    endpoint;
  - each change rewrites the account's `users.json`;
  - every API pod checks the size and mtime of all `users.json` files every
    `api_key_watch_interval_seconds`, and reloads whenever one changes.
- **Per-pod disk.** Each pod's `emptyDir` counts against node ephemeral
  storage. Set an `ephemeral-storage` request, as the example does, so the
  scheduler reserves space and the pods are not the first evicted under disk
  pressure.
- **Per-pod state.** Usage audit and OAuth SQLite files live in the pod's
  `emptyDir`. Read usage from `/metrics` (Prometheus) or OTel, and keep
  `oauth.enabled: false` unless requests stay on one pod.
- **Runtime config.** Change config by editing values and rolling out.
  `PATCH /api/v1/admin/configuration` with `source=file` cannot write the
  read-only ConfigMap.

### Client configuration

Point every client at the ingress, never at individual pods.

`ovcli.conf`, distributed by MDM or a dotfile template, with no per-user
secrets in it:

```json
{
  "url": "https://ov.corp.example.com",
  "auth_mode": "oidc",
  "timeout": 60
}
```

Supply the token through `OPENVIKING_OIDC_TOKEN`, for example from an SSO
helper.

Agent plugins (Claude Code, Codex, OpenClaw, ...) read environment variables:

```bash
OPENVIKING_URL=https://ov.corp.example.com
OPENVIKING_TIMEOUT_MS=15000
OPENVIKING_RECALL_TIMEOUT_MS=30000   # default 120000 is long for a per-prompt hook
```

Plugin `authMode` accepts `trusted` or `api_key`. To use SSO from plugins,
either:

- send a bearer token (`OPENVIKING_BEARER_TOKEN`), or
- put a gateway in front that validates SSO and forwards
  `X-OpenViking-Account` / `X-OpenViking-User` with the root key
  (`auth_mode: trusted`). Allow only that gateway to reach the pods.

The Python SDK and the `ov` CLI do not retry. Retry idempotent reads (search,
ls, read) with jitter on 429/502/503. Never auto-retry `add_resource` or
session commits. Reuse one client per process so connections stay alive.

## Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `replicaCount` | Number of replicas in single-instance mode (must be 1) | `1` |
| `multiInstance.enabled` | Run api + control Deployments against shared backends | `false` |
| `multiInstance.api.replicas` | API replicas when autoscaling is off | `3` |
| `multiInstance.api.autoscaling.*` | HPA on CPU (`enabled`, `minReplicas`, `maxReplicas`, `targetCPUUtilizationPercentage`) | off, 3, 20, 60 |
| `multiInstance.api.podDisruptionBudget.*` | PDB for API pods (`enabled`, `maxUnavailable`) | on, 1 |
| `multiInstance.api.topologySpread.enabled` | Spread API pods over nodes and zones | `true` |
| `multiInstance.api.resources` / `multiInstance.control.resources` | Per-component resources; empty uses `resources` | `{}` |
| `multiInstance.terminationGracePeriodSeconds` | Pod termination grace | `120` |
| `multiInstance.preStopSleepSeconds` | Sleep before SIGTERM | `15` |
| `multiInstance.localVolumeSizeLimit` | Per-pod `emptyDir` size limit | `20Gi` |
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
| `gateway.enabled` | Run OpenViking Gateway as a second container in the pod | `false` |
| `gateway.existingSecret` | Secret with `encryption-key` and `admin-token`; required when enabled | `""` |
| `gateway.workers` | Gateway worker processes | `2` |
| `gateway.port` | Gateway container and Service port | `1935` |
| `gateway.resources` | Gateway container resources | `{}` |

## Upgrading

```bash
helm upgrade openviking ./deploy/helm/openviking -f my-values.yaml
```

In single-instance mode the deployment uses a `Recreate` strategy to avoid data
corruption from multiple pods accessing the same RocksDB volume simultaneously.
Multi-instance API pods roll; the control pod is recreated.

Switching an existing release from single- to multi-instance mode does not
migrate data. The single-instance PVC holds a local vector store and local
files, which a multi-instance release does not read. Re-ingest into the shared
backends, or migrate the data first.

## Uninstalling

```bash
helm uninstall openviking
```

Note: The PersistentVolumeClaim is retained by Helm and becomes orphaned after
uninstall. Delete it explicitly to remove the stored data:

```bash
kubectl delete pvc openviking-data
```
