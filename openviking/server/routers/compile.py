# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Compile task and routing embedding APIs."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Path, Query, status
from fastapi import Response as FastAPIResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from openviking.server.auth import get_request_context
from openviking.server.dependencies import get_service
from openviking.server.identity import RequestContext
from openviking.server.models import Response
from openviking.service.compile_service import (
    CompileConfigUpdate,
    CompileCreateRequest,
    CompileRequest,
)
from openviking.service.compile_targets import CompileName

router = APIRouter(prefix="/api/v1", tags=["compile"])


@router.post("/compile/create")
async def create_compile_task(
    body: CompileCreateRequest,
    ctx: RequestContext = Depends(get_request_context),
):
    """Create a tagged, account-scoped configuration without running Compile."""
    return Response(
        status="ok", result=await get_service().compile.create_compile_task(body, ctx=ctx)
    )


@router.post("/compile", status_code=status.HTTP_202_ACCEPTED)
async def create_compile(
    body: CompileRequest,
    response: FastAPIResponse,
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
    if body.compile_name is None and not body.is_memory_mode:
        # RFC 9745 date for the full-input request form (2026-11-07 UTC).
        response.headers["Deprecation"] = "@1794009600"
        response.headers["Link"] = (
            "<https://docs.openviking.ai/en/api/23-agent-runtime#execute-compile>; "
            'rel="deprecation"; title="POST /api/v1/compile/create, then POST /api/v1/compile with compile_name"'
        )
    return Response(status="ok", result=result.to_dict())


__all__ = ["router"]


@router.get("/compile/config")
async def get_compile_config(
    compile_name: Annotated[CompileName, Query()],
    ctx: RequestContext = Depends(get_request_context),
):
    return Response(status="ok", result=await get_service().compile.get_config(compile_name, ctx))


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
    scope: Literal["user", "account"] = Query("user"),
    compile_name: CompileName | None = None,
    ctx: RequestContext = Depends(get_request_context),
):
    """List the caller's configurations, or all configurations in the account for ADMIN."""
    return Response(
        status="ok",
        result=await get_service().compile.list_configs(
            ctx, limit=limit, cursor=cursor, scope=scope, compile_name=compile_name
        ),
    )


@router.get("/compile/runs")
async def list_compile_runs(
    compile_name: Annotated[CompileName, Query()],
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    ctx: RequestContext = Depends(get_request_context),
):
    result = await get_service().compile.list_runs(compile_name, ctx, limit=limit, cursor=cursor)
    return Response(status="ok", result=result)


@router.get("/compile/runs/{task_id}")
async def get_compile_run(
    compile_name: Annotated[CompileName, Query()],
    task_id: str = Path(..., min_length=1, max_length=128, pattern=r"^cmp_[0-9a-f]+$"),
    ctx: RequestContext = Depends(get_request_context),
):
    """Read a frozen run without exposing execution credentials or private checkpoints."""
    result = await get_service().compile.get_run(compile_name, task_id, ctx)
    return Response(status="ok", result=result)


@router.get("/compile/runs/{task_id}/outputs")
async def run_outputs(
    compile_name: Annotated[CompileName, Query()],
    task_id: str = Path(..., min_length=1, max_length=128, pattern=r"^cmp_[0-9a-f]+$"),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    ctx: RequestContext = Depends(get_request_context),
):
    """Derive a run's changed output files from its frozen snapshots."""
    return Response(
        status="ok",
        result=await get_service().compile.run_outputs(
            compile_name, task_id, ctx, limit=limit, cursor=cursor
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
    def validate_texts(self):
        """Reject blank texts; the embedder applies the configured input token budget."""
        if any(not text.strip() for text in self.texts):
            raise ValueError("Compile embedding texts must not be blank")
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
