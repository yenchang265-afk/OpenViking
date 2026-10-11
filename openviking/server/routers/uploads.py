# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Upload limits and chunked, resumable upload sessions.

A session uploads one file or one folder as numbered parts per file::

    POST   /api/v1/uploads                                  create  -> upload_id
    PUT    /api/v1/uploads/{id}/files/{index}/parts/{n}     raw part body
    GET    /api/v1/uploads/{id}                             received parts (resume)
    POST   /api/v1/uploads/{id}/complete                    -> temp_file_id
    DELETE /api/v1/uploads/{id}                             abort

The returned ``temp_file_id`` is passed to ``POST /api/v1/resources`` like any temp
upload. New sessions follow ``temp_upload.default_mode``: ``local`` stages them on the
receiving server's disk (``session_<id>``), ``shared`` keeps them in shared storage so any
replica can serve every request of a session (``shared_<id>``). Requests on an existing
session go to the store that owns its id, whatever the current mode.
"""

from typing import Any, Dict, List, Literal, Union

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from openviking.server.auth import get_request_context
from openviking.server.identity import RequestContext
from openviking.server.models import Response
from openviking.server.shared_upload_sessions import (
    SharedUploadSessionStore,
    is_shared_session_upload_id,
)
from openviking.server.temp_upload_store import TempUploadStore
from openviking.server.upload_sessions import UploadSessionStore, UploadTooLargeError

router = APIRouter(prefix="/api/v1/uploads", tags=["uploads"])


class UploadFileSpec(BaseModel):
    path: str
    size: int


class CreateUploadRequest(BaseModel):
    kind: Literal["file", "directory"]
    name: str
    files: List[UploadFileSpec] = Field(min_length=1)


def _ok(result: Any) -> Dict[str, Any]:
    return Response(status="ok", result=result).model_dump(exclude_none=True)


SessionStore = Union[UploadSessionStore, SharedUploadSessionStore]


def _new_session_store(request: Request) -> SessionStore:
    """The store new sessions go to, chosen by ``temp_upload.default_mode``."""
    config = request.app.state.config
    if config.temp_upload.default_mode == "shared":
        return SharedUploadSessionStore(config)
    return TempUploadStore.build(config).session_store()


def _session_store(request: Request, upload_id: str) -> SessionStore:
    """The store that owns ``upload_id``; unknown ids get the local store's 404."""
    config = request.app.state.config
    if is_shared_session_upload_id(upload_id):
        return SharedUploadSessionStore(config)
    return TempUploadStore.build(config).session_store()


def _too_large(exc: UploadTooLargeError) -> HTTPException:
    return HTTPException(status_code=413, detail=str(exc))


@router.get("/limits")
async def get_upload_limits(
    request: Request,
    _ctx: RequestContext = Depends(get_request_context),
):
    """Return ``server.upload``: max file/session bytes, max files and part size."""
    return _ok(request.app.state.config.upload.model_dump())


@router.post("")
async def create_upload(
    request: Request,
    body: CreateUploadRequest,
    ctx: RequestContext = Depends(get_request_context),
):
    """Start an upload session for one file or one folder."""
    store = _new_session_store(request)
    try:
        created = await store.create(
            kind=body.kind,
            name=body.name,
            files=[f.model_dump() for f in body.files],
            ctx=ctx,
        )
    except UploadTooLargeError as exc:
        raise _too_large(exc) from exc
    return _ok(created)


@router.put("/{upload_id}/files/{file_index}/parts/{part_number}")
async def put_upload_part(
    request: Request,
    upload_id: str,
    file_index: int,
    part_number: int,
    ctx: RequestContext = Depends(get_request_context),
):
    """Store one part from the raw request body; re-sending a part replaces it."""
    store = _session_store(request, upload_id)
    try:
        stored = await store.put_part(upload_id, file_index, part_number, request.stream(), ctx)
    except UploadTooLargeError as exc:
        raise _too_large(exc) from exc
    return _ok(stored)


@router.get("/{upload_id}")
async def get_upload_status(
    request: Request,
    upload_id: str,
    ctx: RequestContext = Depends(get_request_context),
):
    """Report which parts have been received so a client can resume."""
    return _ok(await _session_store(request, upload_id).status(upload_id, ctx))


@router.post("/{upload_id}/complete")
async def complete_upload(
    request: Request,
    upload_id: str,
    ctx: RequestContext = Depends(get_request_context),
):
    """Assemble all parts and return the ``temp_file_id`` for ``add_resource``."""
    return _ok(await _session_store(request, upload_id).complete(upload_id, ctx))


@router.delete("/{upload_id}")
async def abort_upload(
    request: Request,
    upload_id: str,
    ctx: RequestContext = Depends(get_request_context),
):
    """Discard a session and everything it staged."""
    await _session_store(request, upload_id).abort(upload_id, ctx)
    return _ok({"upload_id": upload_id, "aborted": True})
