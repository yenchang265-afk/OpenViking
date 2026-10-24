# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Compile task and routing embedding APIs."""

from fastapi import APIRouter, Depends, Header, Path, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from openviking.server.auth import get_request_context
from openviking.server.dependencies import get_service
from openviking.server.identity import RequestContext
from openviking.server.models import Response
from openviking.service.compile_service import CompileRequest

router = APIRouter(prefix="/api/v1", tags=["compile"])


@router.post("/compile", status_code=status.HTTP_202_ACCEPTED)
async def create_compile(
    body: CompileRequest,
    ctx: RequestContext = Depends(get_request_context),
    idempotency_key: str | None = Header(
        None, min_length=16, max_length=128, pattern=r"^[A-Za-z0-9:._-]+$"
    ),
):
    """Queue a durable Compile task that runs in this server as the caller."""
    task = await get_service().compile.create(
        body,
        ctx=ctx,
        **({"idempotency_key": idempotency_key} if idempotency_key else {}),
    )
    return Response(status="ok", result=task.to_dict())


__all__ = ["router"]


@router.get("/compile/capabilities")
async def compile_capabilities(ctx: RequestContext = Depends(get_request_context)):
    return Response(status="ok", result=get_service().compile.capabilities(ctx))


@router.get("/compile/submissions/{key}")
async def get_submission(
    key: str = Path(..., min_length=16, max_length=128, pattern=r"^[A-Za-z0-9:._-]+$"),
    ctx: RequestContext = Depends(get_request_context),
):
    from openviking.service.external_task_service import submission_task_id
    from openviking.service.task_tracker import get_task_tracker
    from openviking_cli.exceptions import NotFoundError

    task_id = submission_task_id(ctx, "compile", "cmp_", key)
    task = await get_task_tracker().get(
        task_id, account_id=ctx.account_id, user_id=ctx.user.user_id
    )
    if task is None:
        raise NotFoundError(key, "submission")
    return Response(status="ok", result=task.to_dict())


class CompileEmbeddingRequest(BaseModel):
    """Transient Compile routing text; an empty batch requests model identity only."""

    model_config = ConfigDict(extra="forbid")
    target_uri: str
    texts: list[str] = Field(default_factory=list, max_length=32)
    expected_model: str | None = None

    @model_validator(mode="after")
    def bound_text(self):
        """Bound each routing description and the total before contacting the provider."""
        if any(not text.strip() or len(text) > 1024 for text in self.texts):
            raise ValueError("Compile embedding texts require 1..1024 characters")
        return self


@router.post("/compile/embeddings")
async def compile_embeddings(
    request: CompileEmbeddingRequest,
    _ctx: RequestContext = Depends(get_request_context),
):
    """Embed task-local routing candidates without indexing or retaining their content."""
    from openviking.compile.embeddings import compile_embeddings as embed

    result = await embed(
        get_service(),
        _ctx,
        request.texts,
        target_uri=request.target_uri,
        expected_model=request.expected_model,
    )
    return Response(status="ok", result=result).model_dump()
