# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Upload limit discovery so every client validates against the server's own limits."""

from fastapi import APIRouter, Depends, Request

from openviking.server.auth import get_request_context
from openviking.server.identity import RequestContext
from openviking.server.models import Response

router = APIRouter(prefix="/api/v1/uploads", tags=["uploads"])


@router.get("/limits")
async def get_upload_limits(
    request: Request,
    _ctx: RequestContext = Depends(get_request_context),
):
    """Return ``server.upload``: max file/session bytes, max files and part size."""
    return Response(status="ok", result=request.app.state.config.upload.model_dump()).model_dump(
        exclude_none=True
    )
