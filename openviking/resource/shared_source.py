# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Shared-upload SOURCE references for durable resource ingestion.

Unlike :mod:`openviking.resource.staged_source`, a shared upload already lives in
durable VikingFS storage (``viking://upload/...``) with its own TTL cleanup, so
the SOURCE phase does not copy it into a task-owned temp bundle. The API only
validates and records a reference; the worker downloads the content once into a
worker-local file for parsing. Ownership of the shared object stays with the
upload store's TTL policy — the task never deletes it as its own temp.
"""

import asyncio
import json
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, BinaryIO, Dict

from openviking.parse.accessors.base import LocalResource, SourceType
from openviking.server.error_mapping import is_not_found_error
from openviking.server.identity import RequestContext, Role
from openviking.utils.path_safety import sanitize_relative_viking_path

_SHARED_UPLOAD_ROOT = "viking://upload"
# ``file``: one object at ``content_uri`` (single-request uploads).
# ``session``: a chunked upload session rooted at ``content_uri``; its parts are joined
# when the upload is consumed (see :func:`download_session_upload`).
_LAYOUTS = ("file", "session")
_KINDS = ("file", "directory")
_SESSION_MANIFEST = "session.json"


@dataclass(frozen=True)
class SharedSource:
    """A validated reference to a shared upload consumed as a SOURCE input."""

    temp_file_id: str
    content_uri: str
    account_id: str
    original_filename: str
    file_ext: str
    meta: Dict[str, Any]
    layout: str = "file"
    kind: str = "file"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SharedSource":
        if not isinstance(data, dict):
            raise ValueError("shared_source must be an object")
        temp_file_id = data.get("temp_file_id")
        content_uri = data.get("content_uri")
        account_id = data.get("account_id")
        original_filename = data.get("original_filename") or ""
        file_ext = data.get("file_ext") or ""
        meta = data.get("meta")
        if not isinstance(temp_file_id, str) or not temp_file_id.startswith("shared_"):
            raise ValueError("shared_source.temp_file_id must be a shared upload id")
        if not isinstance(content_uri, str) or not content_uri.startswith(
            f"{_SHARED_UPLOAD_ROOT}/"
        ):
            raise ValueError("shared_source.content_uri must live under the upload root")
        if not isinstance(account_id, str) or not account_id:
            raise ValueError("shared_source.account_id must be a non-empty string")
        if not isinstance(original_filename, str):
            raise ValueError("shared_source.original_filename must be a string")
        if not isinstance(file_ext, str):
            raise ValueError("shared_source.file_ext must be a string")
        if meta is not None and not isinstance(meta, dict):
            raise ValueError("shared_source.meta must be an object")
        # Messages queued before session uploads existed carry neither field.
        layout = data.get("layout") or "file"
        kind = data.get("kind") or "file"
        if layout not in _LAYOUTS:
            raise ValueError(f"shared_source.layout must be one of {_LAYOUTS}")
        if kind not in _KINDS or (layout == "file" and kind != "file"):
            raise ValueError("shared_source.kind must be 'file', or 'directory' for a session")
        return cls(
            temp_file_id=temp_file_id,
            content_uri=content_uri.rstrip("/"),
            account_id=account_id,
            original_filename=original_filename,
            file_ext=file_ext,
            meta=dict(meta or {}),
            layout=layout,
            kind=kind,
        )


def _append_file(out: BinaryIO, part_path: Path) -> int:
    with part_path.open("rb") as part:
        shutil.copyfileobj(part, out, 1024 * 1024)
    return part_path.stat().st_size


async def download_session_upload(
    root_uri: str,
    local_root: Path,
    *,
    viking_fs: Any,
    ctx: RequestContext,
) -> Path:
    """Rebuild a completed shared upload session under ``local_root`` and return its path.

    Each file's parts are downloaded one at a time and appended to the local file, so
    memory stays bounded by the copy buffer and every byte crosses the network once.
    ``ctx`` must be able to read the upload root (callers pass an internal ROOT context).
    """
    manifest = json.loads(await viking_fs.read_file(f"{root_uri}/{_SESSION_MANIFEST}", ctx=ctx))
    if not manifest.get("completed"):
        raise ValueError("Shared upload session is not completed")
    kind, name, part_size = manifest["kind"], manifest["name"], int(manifest["part_size"])
    if kind not in _KINDS or not name or Path(name).name != name or part_size <= 0:
        raise ValueError("Shared upload session manifest is invalid")

    tree = local_root / "tree"
    target_root = tree / name
    part_path = local_root / "part.tmp"
    for index, entry in enumerate(manifest["files"]):
        size = int(entry["size"])
        if kind == "file":
            target = target_root
        else:
            target = target_root / sanitize_relative_viking_path(entry["path"])
            if not target.resolve().is_relative_to(target_root.resolve()):
                raise ValueError(f"Shared upload session path escapes its root: {entry['path']!r}")
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        written = 0
        out = await asyncio.to_thread(target.open, "wb")
        try:
            for number in range(1, -(-size // part_size) + 1):
                part_uri = f"{root_uri}/parts/{index}/{number:06d}"
                await viking_fs.read_file_to_path(part_uri, part_path, ctx=ctx)
                written += await asyncio.to_thread(_append_file, out, part_path)
        finally:
            await asyncio.to_thread(out.close)
        if written != size:
            raise ValueError(
                f"Shared upload session file {entry['path']!r} has {written} bytes, expected {size}"
            )
    await asyncio.to_thread(part_path.unlink, missing_ok=True)
    return target_root


async def materialize_shared_source(
    shared: "SharedSource",
    *,
    viking_fs: Any,
    ctx: RequestContext,
) -> LocalResource:
    """Download a shared upload into a worker-local file (or folder) for parsing.

    The shared object is owned by the upload store's TTL policy, so the returned
    resource only cleans up the worker-local copy. A missing or expired object
    fails loudly instead of yielding an empty input.
    """
    suffix = shared.file_ext or Path(shared.original_filename).suffix or ".tmp"
    local_root = Path(tempfile.mkdtemp(prefix="ov_shared_source_"))
    filename = shared.original_filename or f"resource{suffix}"
    local_path = local_root / Path(filename).name
    try:
        internal_ctx = RequestContext(user=ctx.user, role=Role.ROOT)
        if shared.layout == "session":
            local_path = await download_session_upload(
                shared.content_uri, local_root, viking_fs=viking_fs, ctx=internal_ctx
            )
        else:
            await viking_fs.read_file_to_path(shared.content_uri, local_path, ctx=internal_ctx)
    except asyncio.CancelledError:
        shutil.rmtree(local_root, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(local_root, ignore_errors=True)
        if is_not_found_error(exc):
            raise ValueError("Shared upload content is missing or expired") from exc
        raise

    meta = dict(shared.meta)
    meta["_cleanup_path"] = str(local_root)
    return LocalResource(
        path=local_path,
        source_type=SourceType.LOCAL,
        original_source=shared.original_filename or shared.temp_file_id,
        meta=meta,
        is_temporary=True,
    )
