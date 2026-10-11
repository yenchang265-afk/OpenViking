# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Chunked upload sessions in shared storage, for ``temp_upload.default_mode=shared``.

Same API, limits and validation as :class:`~openviking.server.upload_sessions.UploadSessionStore`,
but every piece of state lives under the shared upload root, so any replica can take any
request of a session and the store keeps nothing in process memory::

    viking://upload/<YYYYMMDDHH>/<hex>/session.json      owner, kind, name, files, part size
    viking://upload/<YYYYMMDDHH>/<hex>/parts/<file>/<n>  received parts
    viking://upload/<YYYYMMDDHH>/<hex>/meta              shared-upload meta, written on complete

The upload id is the bucketed shared-upload id (``<YYYYMMDDHH>-<hex>``), and completing the
session returns ``shared_<upload id>``: the same temp_file_id family as a single-request
shared upload, so ``add_resource`` and the other consumers resolve it through the shared
path. Completing only checks that every part is present and writes the meta; the parts are
joined once, when the upload is consumed (see
:func:`openviking.resource.shared_source.download_session_upload`), so completing a large
upload does not move its bytes inside one request. Hour buckets, sessions included, are
removed by the shared-upload TTL cleanup.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Literal, Tuple

from openviking.server.config import ServerConfig
from openviking.server.error_mapping import is_not_found_error
from openviking.server.identity import RequestContext, Role
from openviking.server.upload_sessions import (
    UploadSessionStore,
    UploadTooLargeError,
    _total_parts,
    _validate_files,
    _validate_name,
)
from openviking.storage.viking_fs import LS_ALL_NODES, get_viking_fs
from openviking_cli.exceptions import InvalidArgumentError, NotFoundError, PermissionDeniedError

_ROOT = "viking://upload"
_MANIFEST = "session.json"
_KINDS = ("file", "directory")


def _split_upload_id(upload_id: Any) -> Tuple[str, str] | None:
    from openviking.server.temp_upload_store import _split_shared_upload_id

    if not isinstance(upload_id, str):
        return None
    return _split_shared_upload_id(upload_id)


def is_shared_session_upload_id(upload_id: Any) -> bool:
    """Whether ``upload_id`` names a shared-storage session (``<YYYYMMDDHH>-<hex>``)."""
    return _split_upload_id(upload_id) is not None


class SharedUploadSessionStore:
    """Create, fill, inspect, complete and abort chunked sessions in shared storage."""

    def __init__(self, server_config: ServerConfig) -> None:
        self.server_config = server_config
        self.limits = server_config.upload
        self.ttl_seconds = server_config.temp_upload.ttl_seconds

    @staticmethod
    def _internal_ctx(ctx: RequestContext) -> RequestContext:
        return RequestContext(user=ctx.user, role=Role.ROOT)

    @staticmethod
    def _root_uri(upload_id: str) -> str:
        split = _split_upload_id(upload_id)
        if split is None:
            raise NotFoundError(str(upload_id), "upload")
        bucket, leaf = split
        return f"{_ROOT}/{bucket}/{leaf}"

    # -- lifecycle -------------------------------------------------------------

    async def create(
        self,
        *,
        kind: Literal["file", "directory"],
        name: str,
        files: List[Dict[str, Any]],
        ctx: RequestContext,
    ) -> Dict[str, Any]:
        from openviking.server.temp_upload_store import TempUploadStore, _new_shared_upload_id

        if kind not in _KINDS:
            raise InvalidArgumentError(f"kind must be one of {_KINDS}")
        name = _validate_name(name)
        validated = _validate_files(kind, name, files, self.limits)

        upload_id = _new_shared_upload_id()
        created_at = time.time()
        meta = {
            "version": 1,
            "upload_id": upload_id,
            "account": ctx.account_id,
            "user": ctx.user.user_id,
            "kind": kind,
            "name": name,
            "part_size": self.limits.part_size_bytes,
            "files": validated,
            "created_at": created_at,
            "completed": False,
        }
        await self._write_manifest(upload_id, meta, ctx)
        # Expired hour buckets, abandoned sessions included, go with the shared cleanup.
        TempUploadStore.build(self.server_config)._schedule_shared_cleanup(ctx)
        return {
            "upload_id": upload_id,
            "part_size_bytes": meta["part_size"],
            "expires_at": created_at + self.ttl_seconds if self.ttl_seconds else None,
            "files": [
                {**f, "index": i, "total_parts": _total_parts(f["size"], meta["part_size"])}
                for i, f in enumerate(validated)
            ],
        }

    async def put_part(
        self,
        upload_id: str,
        file_index: int,
        part_number: int,
        chunks: AsyncIterator[bytes],
        ctx: RequestContext,
    ) -> Dict[str, Any]:
        meta = await self._load(upload_id, ctx)
        if meta["completed"]:
            raise InvalidArgumentError("Upload is already completed")
        expected = UploadSessionStore._expected_part_size(meta, file_index, part_number)

        fd, tmp = tempfile.mkstemp(prefix="ov_shared_part_")
        os.close(fd)
        try:
            received = 0
            f = await asyncio.to_thread(open, tmp, "wb")
            try:
                async for chunk in chunks:
                    received += len(chunk)
                    if received > expected:
                        raise UploadTooLargeError(
                            f"Part {part_number} exceeds size limit ({expected} bytes)."
                        )
                    await asyncio.to_thread(f.write, chunk)
            finally:
                await asyncio.to_thread(f.close)
            if received != expected:
                raise InvalidArgumentError(
                    f"Part {part_number} of file {file_index} has {received} bytes, "
                    f"expected {expected}"
                )
            # Each (file, part) has its own object and a re-sent part carries the same
            # bytes, so concurrent writes from different replicas cannot interleave.
            await get_viking_fs().write_file_from_path(
                self._part_uri(upload_id, file_index, part_number),
                tmp,
                ctx=self._internal_ctx(ctx),
                auto_pathlock=False,
            )
        finally:
            await asyncio.to_thread(Path(tmp).unlink, missing_ok=True)
        return {"file_index": file_index, "part_number": part_number, "size": received}

    async def status(self, upload_id: str, ctx: RequestContext) -> Dict[str, Any]:
        meta = await self._load(upload_id, ctx)
        files = []
        for index, f in enumerate(meta["files"]):
            received = (
                [] if meta["completed"] else sorted(await self._received(upload_id, index, ctx))
            )
            files.append(
                {
                    **f,
                    "index": index,
                    "total_parts": _total_parts(f["size"], meta["part_size"]),
                    "received_parts": received,
                }
            )
        return {
            "upload_id": upload_id,
            "kind": meta["kind"],
            "name": meta["name"],
            "part_size_bytes": meta["part_size"],
            "completed": meta["completed"],
            "files": files,
        }

    async def complete(self, upload_id: str, ctx: RequestContext) -> Dict[str, Any]:
        """Check every part is stored at its expected size, then publish the upload.

        Idempotent and safe to repeat from any replica: both writes are deterministic.
        """
        meta = await self._load(upload_id, ctx)
        temp_file_id = f"shared_{upload_id}"
        if not meta["completed"]:
            part_size = meta["part_size"]
            missing = []
            for index, f in enumerate(meta["files"]):
                received = await self._received(upload_id, index, ctx)
                for n in range(1, _total_parts(f["size"], part_size) + 1):
                    expected = min(part_size, f["size"] - (n - 1) * part_size)
                    if received.get(n) != expected:
                        missing.append(f"{f['path']}#{n}")
            if missing:
                raise InvalidArgumentError(f"Upload has missing parts: {', '.join(missing[:10])}")
            meta = {**meta, "completed": True}
            await self._write_manifest(upload_id, meta, ctx)

        root = self._root_uri(upload_id)
        await get_viking_fs().write_file(
            f"{root}/meta",
            json.dumps(
                {
                    "version": 3,
                    "layout": "session",
                    "kind": meta["kind"],
                    "temp_file_id": temp_file_id,
                    "account": meta["account"],
                    "user": meta["user"],
                    "original_filename": meta["name"],
                    "content_type": None,
                    "file_ext": Path(meta["name"]).suffix if meta["kind"] == "file" else "",
                    "size": sum(f["size"] for f in meta["files"]),
                    "storage_uri": root,
                },
                ensure_ascii=False,
            ),
            ctx=self._internal_ctx(ctx),
            auto_pathlock=False,
        )
        return {"temp_file_id": temp_file_id}

    async def abort(self, upload_id: str, ctx: RequestContext) -> None:
        await self._load(upload_id, ctx)
        await get_viking_fs().remove_files(
            self._root_uri(upload_id),
            recursive=True,
            ctx=self._internal_ctx(ctx),
            auto_pathlock=False,
        )

    # -- internals -------------------------------------------------------------

    def _part_uri(self, upload_id: str, file_index: int, part_number: int) -> str:
        return f"{self._root_uri(upload_id)}/parts/{file_index}/{part_number:06d}"

    async def _write_manifest(
        self, upload_id: str, meta: Dict[str, Any], ctx: RequestContext
    ) -> None:
        await get_viking_fs().write_file(
            f"{self._root_uri(upload_id)}/{_MANIFEST}",
            json.dumps(meta, ensure_ascii=False),
            ctx=self._internal_ctx(ctx),
            auto_pathlock=False,
        )

    async def _load(self, upload_id: str, ctx: RequestContext) -> Dict[str, Any]:
        uri = f"{self._root_uri(upload_id)}/{_MANIFEST}"
        try:
            meta = json.loads(await get_viking_fs().read_file(uri, ctx=self._internal_ctx(ctx)))
        except Exception as exc:
            raise NotFoundError(upload_id, "upload") from exc
        if not isinstance(meta, dict) or meta.get("upload_id") != upload_id:
            raise NotFoundError(upload_id, "upload")
        if meta.get("account") != ctx.account_id or meta.get("user") != ctx.user.user_id:
            raise PermissionDeniedError("Upload does not belong to the current user.")
        return meta

    async def _received(
        self, upload_id: str, file_index: int, ctx: RequestContext
    ) -> Dict[int, int]:
        """Part number -> stored size for one file; empty when nothing was received."""
        try:
            entries = await get_viking_fs().ls(
                f"{self._root_uri(upload_id)}/parts/{file_index}",
                show_all_hidden=True,
                node_limit=LS_ALL_NODES,
                ctx=self._internal_ctx(ctx),
            )
        except Exception as exc:
            if is_not_found_error(exc):
                return {}
            raise
        return {
            int(entry["name"]): int(entry.get("size") or 0)
            for entry in entries
            if not entry.get("isDir") and str(entry.get("name", "")).isdigit()
        }


__all__ = ["SharedUploadSessionStore", "is_shared_session_upload_id"]
