# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Compile task and routing embedding APIs."""

from fastapi import APIRouter, Depends, Header, Path, Query, status
from fastapi import Response as HTTPResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from openviking.server.auth import get_request_context
from openviking.server.dependencies import get_service
from openviking.server.identity import RequestContext
from openviking.server.models import Response
from openviking.service.compile_service import CompileConfigUpdate, CompileRequest

router = APIRouter(prefix="/api/v1", tags=["compile"])


@router.post(
    "/compile",
    status_code=status.HTTP_202_ACCEPTED,
    responses={status.HTTP_200_OK: {"description": "Compile update settings saved"}},
)
async def create_compile(
    body: CompileRequest,
    response: HTTPResponse,
    ctx: RequestContext = Depends(get_request_context),
    idempotency_key: str | None = Header(
        None, min_length=16, max_length=128, pattern=r"^[A-Za-z0-9:._-]+$"
    ),
):
    """Save explicit update settings, or queue a durable Compile task run in-server as the caller."""
    result = await get_service().compile.create(
        body,
        ctx=ctx,
        **({"idempotency_key": idempotency_key} if idempotency_key else {}),
    )
    if isinstance(result, dict):
        response.status_code = status.HTTP_200_OK
        return Response(status="ok", result=result)
    return Response(status="ok", result=result.to_dict())


__all__ = ["router"]


@router.get("/compile/config")
async def get_compile_config(
    to: str = Query(..., min_length=1),
    ctx: RequestContext = Depends(get_request_context),
):
    return Response(status="ok", result=await get_service().compile.get_config(to, ctx))


@router.post("/compile/config/update")
async def update_compile_config(
    body: CompileConfigUpdate,
    ctx: RequestContext = Depends(get_request_context),
):
    return Response(status="ok", result=await get_service().compile.update_config(body, ctx))


@router.get("/compile/configs")
async def list_compile_configs(
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    ctx: RequestContext = Depends(get_request_context),
):
    return Response(
        status="ok",
        result=await get_service().compile.list_configs(ctx, limit=limit, cursor=cursor),
    )


@router.get("/compile/operations")
async def list_compile_operations(
    to: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    ctx: RequestContext = Depends(get_request_context),
):
    result = await get_service().compile.list_operations(to, ctx, limit=limit, cursor=cursor)
    return Response(status="ok", result=result)


@router.get("/compile/operations/{operation_id}")
async def get_compile_operation(
    operation_id: str = Path(
        ..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9:._-]*$"
    ),
    to: str = Query(..., min_length=1),
    ctx: RequestContext = Depends(get_request_context),
):
    """Read one operation using to for authorization and the history's public field set."""
    result = await get_service().compile.get_operation(to, operation_id, ctx)
    return Response(status="ok", result=result)


@router.get("/compile/operations/{operation_id}/outputs")
async def operation_outputs(
    operation_id: str = Path(
        ..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9:._-]*$"
    ),
    to: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    ctx: RequestContext = Depends(get_request_context),
):
    """List one operation's output files and frozen version references."""
    return Response(
        status="ok",
        result=await get_service().compile.operation_outputs(
            to, operation_id, ctx, limit=limit, cursor=cursor
        ),
    )


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
