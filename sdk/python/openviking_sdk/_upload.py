"""Chunked upload sessions: send a local file or folder in parts without zipping it.

Uses the server's ``/api/v1/uploads`` API (one part in memory at a time). Returns
``None`` when the server does not offer sessions so callers can fall back to the
single-request ``/api/v1/resources/temp_upload``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ._utils import _path_is_relative_to

if TYPE_CHECKING:
    from openviking_sdk.client import AsyncHTTPClient

# Older servers (no route), method not allowed, or sessions refused (shared upload mode).
_SESSIONS_UNAVAILABLE = frozenset({404, 405, 409})


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
            await _send_file_parts(client, upload_id, index, entry["local"], part_size)
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


async def _send_file_parts(
    client: "AsyncHTTPClient", upload_id: str, index: int, local: Path, part_size: int
) -> None:
    with open(local, "rb") as f:
        number = 1
        while part := f.read(part_size):
            client._handle_response(
                await client._request(
                    "PUT",
                    f"/api/v1/uploads/{upload_id}/files/{index}/parts/{number}",
                    content=part,
                    headers={"Content-Type": "application/octet-stream"},
                )
            )
            number += 1
