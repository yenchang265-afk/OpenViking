# Fork compatibility

These notes apply to [`yenchang265-afk/OpenViking`](https://github.com/yenchang265-afk/OpenViking). The repository regularly merges upstream changes, but preserves the fork decisions in [UPSTREAM_SYNC.md](https://github.com/yenchang265-afk/OpenViking/blob/main/UPSTREAM_SYNC.md).

## Installation and documentation scope

The PyPI package `openviking`, the official install scripts, managed services, and upstream release notes describe upstream distributions. Installing an official package does not install this fork's changes. To run this checkout, follow the [source-build instructions](https://github.com/yenchang265-afk/OpenViking/blob/main/CONTRIBUTING.md) using this fork's clone URL and the revision you intend to deploy. Use the image repository configured in this fork's deployment files when deploying its images.

Historical changelog entries and benchmark results describe their named upstream release. The [Volcengine purchase guide](../guides/02-volcengine-purchase-guide.md) is retained for upstream users; its native provider configuration does not run in this fork.

## Server model providers

| Component | Providers implemented in this checkout |
| --- | --- |
| Dense embedding | `openai`, `azure`, `jina`, `ollama`, `gemini`, `voyage`, `dashscope`, `minimax`, `cohere`, `litellm`, `local` |
| VLM and query planner | `openai`, `azure`, `kimi`, `glm`, `litellm`, `openai-codex` |
| Rerank | `cohere`, `openai`, `litellm`, `jev` |

The native `volcengine` and `vikingdb` model implementations have been removed. Sparse and hybrid embedding have no factory implementation in this checkout. Configure `embedding.dense`; a nonzero `storage.vectordb.sparse_weight` does not supply a sparse model. The config schema still contains some legacy fields, and the setup wizard can still offer upstream choices. Select a supported provider and run `openviking-server doctor` before starting the service.

When no embedding model is configured, the default is the local 512-dimensional `bge-small-zh-v1.5-f16` model. An explicit dense model configuration defaults its provider to `openai`. The local model requires the `local-embed` extra; see [model configuration](../guides/01-configuration.md#local-provider-local).

The removed Ark VLM backend supplied audio/video understanding. No remaining backend implements it; `vlm.media.enabled` does not add this capability. Image input remains provider- and model-dependent. VikingBot has its own provider registry, so its standalone agent credentials are a separate contract from the server's `vlm` settings.

See [server configuration](01-server.md) for supported examples. Changing an embedding provider, model, or dimension on an existing workspace can require reindexing.

## Encryption

The root-key providers are `local` and `vault`. `volcengine_kms` is unavailable. The stored envelope marker `0x03` remains reserved for compatibility; it does not restore the removed KMS provider.

Do not switch provider names to recover encrypted data. Preserve the original keys and backups. Export existing KMS-encrypted data from a deployment that can still decrypt it, then import it into a deployment configured with a supported provider. See the [encryption guide](../guides/08-encryption.md).

## VikingBot external tools

Web search and fetch are disabled by default through `tools.web.enabled`. External-service skills are opt-in. Configure these deliberately when needed; upstream examples that assume enabled web tools need adjustment for this fork.

## Keeping documentation current

Update English and Traditional Chinese pages together when their shared behavior changes. Check examples against the server provider registries and configuration factories rather than relying on wizard labels or upstream release notes. Run the documentation checks and build described in [CONTRIBUTING.md](https://github.com/yenchang265-afk/OpenViking/blob/main/CONTRIBUTING.md#documentation) before submitting changes.
