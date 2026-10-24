"""Transient Compile routing embeddings with the account's configured embedder."""

from __future__ import annotations

import asyncio
import math
from typing import Any

from openviking.core.namespace import classify_uri
from openviking.core.path_variables import resolve_path_variables
from openviking.core.uri_validation import validate_request_viking_uri
from openviking.models.embedder.base import embed_compat
from openviking.server.identity import RequestContext
from openviking_cli.exceptions import InvalidArgumentError


async def compile_embeddings(
    service: Any,
    ctx: RequestContext,
    texts: list[str],
    *,
    target_uri: str,
    expected_model: str | None = None,
) -> dict[str, Any]:
    """Embed task-local routing candidates without indexing or retaining their content.

    Target validation uses the same tenant identity and ACL checks as file reads.
    The configured embedder supplies provider concurrency/rate controls.
    """
    target = validate_request_viking_uri(resolve_path_variables(target_uri), ctx)
    classification = classify_uri(target)
    if classification.context_type != "resource" and not classification.is_skill_namespace:
        raise InvalidArgumentError(
            "Compile embeddings require a resource or Skill namespace target"
        )
    fs = service.viking_fs
    await fs.stat(target, ctx=ctx, skip_count=True)
    embedder = fs._get_embedder(ctx)
    # The account's effective embedding settings identify task-local cached vectors.
    model = (await service.embedding_provider.get_status(ctx.account_id)).fingerprint
    if expected_model and expected_model != model:
        raise InvalidArgumentError("Compile embedding model changed during the task")
    # Small chunks also bound providers whose embed_async implementation has no limiter.
    vectors = []
    for start in range(0, len(texts), 4):
        batch = await asyncio.gather(
            *(embed_compat(embedder, text) for text in texts[start : start + 4])
        )
        for result in batch:
            vector = result.dense_vector
            if not vector or len(vector) > 8192 or not all(math.isfinite(x) for x in vector):
                raise InvalidArgumentError("Compile requires finite dense embedding vectors")
            vectors.append(vector)
    return {"model": model, "vectors": vectors}
