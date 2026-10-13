---
description: Prepare the workload, models, storage, network, and operations for a self-managed deployment.
---

# Deployment Checklist

Review this list before running the service yourself with Python, Docker, or the Helm chart. If you already have an endpoint and API key, connect through the [CLI quick start](../getting-started/02-quickstart.md).

## For every self-managed installation

| Area | Decide before deployment | Reference |
| --- | --- | --- |
| Workload | Document count and size, vector dimensions, concurrency, ingestion frequency, retention | [Observability](05-observability.md) |
| Models | Provider, model name, API base, credentials, output dimensions, rate limits, timeouts, connectivity from the runtime | [Configuration](01-configuration.md) |
| Storage | Persistent workspace location, capacity, permissions, backup destination, restore procedure | [Storage](../concepts/05-storage.md), [snapshots](15-snapshot.md) |
| Network and identity | Client endpoint, TLS, DNS, proxy, administrator and application keys | [Public access](12-public-access.md), [authentication](04-authentication.md) |
| Operations | Owners for alerts, upgrades, credentials, and recovery | [Diagnostics](05-observability.md) |

Measure capacity with representative data. A running container or a successful health probe does not demonstrate that the deployment can handle your workload.

## Model integration checks

- Embedding must return fixed-size dense vectors. Align actual output, `embedding.dense.dimension`, and vector database dimensions.
- Confirm whether the API base includes `/v1` or `/api/v3`. Text and multimodal embedding may use different paths and request bodies; “OpenAI compatible” alone is insufficient.
- VLM / LLM supports understanding, summaries, and memory extraction. Validate image input for image tasks and tool calls for agents that use tools.
- Test authentication, DNS, certificates, and timeouts from where the service runs, such as the container or Pod network. Connectivity from a laptop does not establish connectivity from the service.
- Changing embedding models can change vector semantics even when dimensions match. Plan index rebuilding before switching an existing dataset.

Continue to [server deployment](03-deployment.md).
