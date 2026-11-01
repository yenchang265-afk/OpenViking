"""Chunked upload sessions: send a local file or folder in parts without zipping it.

Uses the server's ``/api/v1/uploads`` API (one part in memory at a time). Returns
``None`` when the server does not offer sessions so callers can fall back to the
single-request ``/api/v1/resources/temp_upload``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import httpx

from ._utils import _path_is_relative_to
from .errors import FailedPreconditionError

if TYPE_CHECKING:
    from openviking_sdk.client import AsyncHTTPClient

# Older servers (no route), method not allowed, or sessions refused (shared upload mode).
_SESSIONS_UNAVAILABLE = frozenset({404, 405, 409})

# A part is re-sent after network errors, 5xx and these statuses, with doubling delays.
_TRANSIENT_STATUSES = frozenset({408, 429})
_PART_RETRIES = 3
_PART_RETRY_BASE_DELAY = 0.5


def list_upload_files(path: Path) -> List[Dict[str, Any]]:
    """Return ``[{path, size, local}]`` for a file, or every regular file in a folder.

    Folder entries use forward-slash paths relative to the folder; symlinks and anything
    resolving outside the folder are skipped, matching the legacy zip upload.
    """
    if path.is_file():
        return [{"path": path.name, "size": path.stat().st_size, "local": path}]
    root = path.resolve()
    entries = []
    for file_path in sorted(path.rglob("*")):
        if file_path.is_symlink() or not file_path.is_file():
            continue
        if not _path_is_relative_to(file_path.resolve(), root):
            continue
        entries.append(
            {
                "path": file_path.relative_to(path).as_posix(),
                "size": file_path.stat().st_size,
                "local": file_path,
            }
        )
    return entries


async def upload_via_session(client: "AsyncHTTPClient", path: Path) -> Optional[str]:
    """Upload ``path`` through a chunked session and return its ``temp_file_id``.

    Returns ``None`` if sessions are unavailable on the server or the folder is empty.
    On any failure after the session is created, the session is aborted best-effort
    and the error is re-raised.
    """
    entries = list_upload_files(path)
    if not entries:
        return None
    kind = "file" if path.is_file() else "directory"
    response = await client._request(
        "POST",
        "/api/v1/uploads",
        json={
            "kind": kind,
            "name": path.name,
            "files": [{"path": e["path"], "size": e["size"]} for e in entries],
        },
    )
    if response.status_code in _SESSIONS_UNAVAILABLE:
        return None
    created = client._handle_response(response)
    upload_id = created["upload_id"]
    part_size = int(created["part_size_bytes"])

    try:
        for index, entry in enumerate(entries):
            await _send_file_parts(client, upload_id, index, entry, part_size)
        done = client._handle_response(
            await client._request("POST", f"/api/v1/uploads/{upload_id}/complete")
        )
    except BaseException:
        try:
            await client._request("DELETE", f"/api/v1/uploads/{upload_id}")
        except Exception:
            pass
        raise
    return done["temp_file_id"]


def _changed_while_uploading(entry: Dict[str, Any]) -> FailedPreconditionError:
    """The file no longer has the size the session was created with."""
    return FailedPreconditionError(
        f"'{entry['path']}' changed while uploading (it was {entry['size']} bytes when the "
        "upload started). Retry, or leave out files that are being written, such as .git "
        "or logs.",
        details={"path": entry["path"], "size": entry["size"]},
    )


def _is_transient_status(status_code: int) -> bool:
    return status_code >= 500 or status_code in _TRANSIENT_STATUSES


async def _put_part(client: "AsyncHTTPClient", url: str, part: bytes) -> None:
    """PUT one part, re-sending it after network errors and transient statuses."""
    for attempt in range(_PART_RETRIES + 1):
        last_attempt = attempt == _PART_RETRIES
        try:
            response = await client._request(
                "PUT", url, content=part, headers={"Content-Type": "application/octet-stream"}
            )
        except httpx.TransportError:
            if last_attempt:
                raise
        else:
            if last_attempt or not _is_transient_status(response.status_code):
                client._handle_response(response)
                return
        await asyncio.sleep(_PART_RETRY_BASE_DELAY * 2**attempt)


async def _send_file_parts(
    client: "AsyncHTTPClient", upload_id: str, index: int, entry: Dict[str, Any], part_size: int
) -> None:
    """Send exactly the ``entry["size"]`` bytes the session declared, as numbered parts."""
    try:
        f = open(entry["local"], "rb")
    except FileNotFoundError:
        raise _changed_while_uploading(entry) from None
    with f:
        remaining = entry["size"]
        number = 1
        while remaining > 0:
            want = min(part_size, remaining)
            part = f.read(want)
            if len(part) < want:
                raise _changed_while_uploading(entry)
            await _put_part(
                client, f"/api/v1/uploads/{upload_id}/files/{index}/parts/{number}", part
            )
            remaining -= want
            number += 1
        if f.read(1):
            # More bytes than declared: the file grew after the listing.
            raise _changed_while_uploading(entry)
