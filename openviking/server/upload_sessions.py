# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Chunked, resumable upload sessions staged on local disk.

A session uploads one file or one directory tree as numbered parts per file. Parts are
streamed to disk with bounded buffers, may be re-sent (idempotent), and are assembled
into ``sessions/<id>/tree/<name>`` on completion. The resulting ``session_<id>``
temp_file_id resolves to that file or directory for ``add_resource``.

Layout under the upload temp dir::

    sessions/<id>/session.json          owner, kind, name, files, part size, completed
    sessions/<id>/parts/<file>/<n>      received parts (removed after assembly)
    sessions/<id>/tree/<name>[/...]     assembled upload

Sessions are bound to the creating account and user, and are local to one server
process's disk (``temp_upload.default_mode=local``).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Literal, Tuple

from openviking.server.config import UploadConfig
from openviking.server.identity import RequestContext
from openviking.utils.path_safety import sanitize_relative_viking_path
from openviking_cli.exceptions import InvalidArgumentError, NotFoundError, PermissionDeniedError

SESSION_TEMP_FILE_PREFIX = "session_"
_SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_META_NAME = "session.json"
_COPY_CHUNK_BYTES = 1024 * 1024
_KINDS = ("file", "directory")


class UploadTooLargeError(InvalidArgumentError):
    """An upload, file or part is larger than the configured limit (HTTP 413)."""


def is_session_temp_file_id(temp_file_id: str) -> bool:
    return temp_file_id.startswith(SESSION_TEMP_FILE_PREFIX)


def _total_parts(size: int, part_size: int) -> int:
    return -(-size // part_size)


def _validate_name(name: Any) -> str:
    if (
        not isinstance(name, str)
        or not name
        or len(name) > 255
        or name in {".", ".."}
        or any(ch in name for ch in "/\\\x00")
    ):
        raise InvalidArgumentError(f"Invalid upload name: {name!r}")
    return name


def _normalize_rel_path(path: Any) -> str:
    if not isinstance(path, str) or "\x00" in path:
        raise InvalidArgumentError(f"Invalid upload path: {path!r}")
    try:
        normalized = sanitize_relative_viking_path(path)
    except ValueError as exc:
        raise InvalidArgumentError(f"Invalid upload path: {path!r}") from exc
    if any(segment in {"", ".", ".."} for segment in normalized.split("/")):
        raise InvalidArgumentError(f"Invalid upload path: {path!r}")
    return normalized


def _validate_files(kind: str, name: str, files: Any, limits: UploadConfig) -> List[Dict[str, Any]]:
    if not isinstance(files, list) or not files:
        raise InvalidArgumentError("An upload needs at least one file")
    if len(files) > limits.max_files:
        raise InvalidArgumentError(f"Too many files: {len(files)} > {limits.max_files}")
    if kind == "file" and len(files) != 1:
        raise InvalidArgumentError("A file upload must contain exactly one file")

    validated: List[Dict[str, Any]] = []
    seen: set[str] = set()
    dir_prefixes: set[str] = set()
    total = 0
    for entry in files:
        if not isinstance(entry, dict):
            raise InvalidArgumentError("Each file needs a path and a size")
        path = _normalize_rel_path(entry.get("path"))
        size = entry.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise InvalidArgumentError(f"Invalid size for {path!r}: {size!r}")
        if size > limits.max_file_bytes:
            raise UploadTooLargeError(
                f"{path!r} exceeds size limit ({limits.max_file_bytes} bytes)."
            )
        folded = path.casefold()
        parents = folded.split("/")[:-1]
        if folded in seen or folded in dir_prefixes:
            raise InvalidArgumentError(f"Conflicting upload path: {path!r}")
        if any("/".join(parents[: i + 1]) in seen for i in range(len(parents))):
            raise InvalidArgumentError(f"Conflicting upload path: {path!r}")
        seen.add(folded)
        dir_prefixes.update("/".join(parents[: i + 1]) for i in range(len(parents)))
        total += size
        validated.append({"path": path, "size": size})

    if total > limits.max_session_bytes:
        raise UploadTooLargeError(f"Upload exceeds size limit ({limits.max_session_bytes} bytes).")
    if kind == "file" and validated[0]["path"] != name:
        raise InvalidArgumentError("A file upload's path must equal its name")
    return validated


def _write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


class UploadSessionStore:
    """Create, fill, inspect, complete and resolve chunked upload sessions."""

    _complete_locks: Dict[str, asyncio.Lock] = {}

    def __init__(self, root: Path, *, limits: UploadConfig, ttl_seconds: int) -> None:
        self.sessions_dir = Path(root) / "sessions"
        self.limits = limits
        self.ttl_seconds = ttl_seconds

    # -- lifecycle -------------------------------------------------------------

    async def create(
        self,
        *,
        kind: Literal["file", "directory"],
        name: str,
        files: List[Dict[str, Any]],
        ctx: RequestContext,
    ) -> Dict[str, Any]:
        if kind not in _KINDS:
            raise InvalidArgumentError(f"kind must be one of {_KINDS}")
        name = _validate_name(name)
        validated = _validate_files(kind, name, files, self.limits)
        await asyncio.to_thread(self._sweep_expired)

        upload_id = uuid.uuid4().hex
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
        session_dir = self.sessions_dir / upload_id

        def _create() -> None:
            (session_dir / "parts").mkdir(parents=True)
            _write_json_atomic(session_dir / _META_NAME, meta)

        await asyncio.to_thread(_create)
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
        session_dir, meta = self._load(upload_id, ctx)
        if meta["completed"]:
            raise InvalidArgumentError("Upload is already completed")
        expected = self._expected_part_size(meta, file_index, part_number)

        part_dir = session_dir / "parts" / str(file_index)
        await asyncio.to_thread(part_dir.mkdir, parents=True, exist_ok=True)
        final = part_dir / f"{part_number:06d}"
        tmp = part_dir / f"{part_number:06d}.{uuid.uuid4().hex}.tmp"
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
        except BaseException:
            await asyncio.to_thread(f.close)
            await asyncio.to_thread(tmp.unlink, missing_ok=True)
            raise
        await asyncio.to_thread(f.close)
        if received != expected:
            await asyncio.to_thread(tmp.unlink, missing_ok=True)
            raise InvalidArgumentError(
                f"Part {part_number} of file {file_index} has {received} bytes, expected {expected}"
            )
        await asyncio.to_thread(os.replace, tmp, final)
        return {"file_index": file_index, "part_number": part_number, "size": received}

    async def status(self, upload_id: str, ctx: RequestContext) -> Dict[str, Any]:
        session_dir, meta = self._load(upload_id, ctx)

        def _received(index: int) -> List[int]:
            part_dir = session_dir / "parts" / str(index)
            if not part_dir.is_dir():
                return []
            return sorted(int(p.name) for p in part_dir.iterdir() if p.name.isdigit())

        files = []
        for index, f in enumerate(meta["files"]):
            files.append(
                {
                    **f,
                    "index": index,
                    "total_parts": _total_parts(f["size"], meta["part_size"]),
                    "received_parts": []
                    if meta["completed"]
                    else await asyncio.to_thread(_received, index),
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
        self._load(upload_id, ctx)
        lock = self._complete_locks.setdefault(upload_id, asyncio.Lock())
        async with lock:
            session_dir, meta = self._load(upload_id, ctx)
            if not meta["completed"]:
                await asyncio.to_thread(self._assemble, session_dir, meta)
                meta = {**meta, "completed": True}
                await asyncio.to_thread(_write_json_atomic, session_dir / _META_NAME, meta)
        self._complete_locks.pop(upload_id, None)
        return {"temp_file_id": f"{SESSION_TEMP_FILE_PREFIX}{upload_id}"}

    async def abort(self, upload_id: str, ctx: RequestContext) -> None:
        session_dir, _ = self._load(upload_id, ctx)
        await asyncio.to_thread(shutil.rmtree, session_dir, True)

    def resolve(self, temp_file_id: str, ctx: RequestContext) -> Tuple[Path, str]:
        """Return ``(local_path, name)`` of a completed session's assembled upload."""
        upload_id = temp_file_id.removeprefix(SESSION_TEMP_FILE_PREFIX)
        session_dir, meta = self._load(upload_id, ctx)
        if not meta["completed"]:
            raise NotFoundError(temp_file_id, "upload")
        path = session_dir / "tree" / meta["name"]
        if not path.exists():
            raise NotFoundError(temp_file_id, "upload")
        return path, meta["name"]

    # -- internals -------------------------------------------------------------

    def _load(self, upload_id: str, ctx: RequestContext) -> Tuple[Path, Dict[str, Any]]:
        if not isinstance(upload_id, str) or not _SESSION_ID_RE.match(upload_id):
            raise NotFoundError(str(upload_id), "upload")
        session_dir = self.sessions_dir / upload_id
        try:
            meta = json.loads((session_dir / _META_NAME).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise NotFoundError(upload_id, "upload") from exc
        if meta.get("account") != ctx.account_id or meta.get("user") != ctx.user.user_id:
            raise PermissionDeniedError("Upload does not belong to the current user.")
        return session_dir, meta

    @staticmethod
    def _expected_part_size(meta: Dict[str, Any], file_index: Any, part_number: Any) -> int:
        files = meta["files"]
        if isinstance(file_index, bool) or not isinstance(file_index, int):
            raise InvalidArgumentError(f"Invalid file index: {file_index!r}")
        if not 0 <= file_index < len(files):
            raise InvalidArgumentError(f"File index {file_index} is out of range")
        size, part_size = files[file_index]["size"], meta["part_size"]
        total = _total_parts(size, part_size)
        if isinstance(part_number, bool) or not isinstance(part_number, int):
            raise InvalidArgumentError(f"Invalid part number: {part_number!r}")
        if not 1 <= part_number <= total:
            raise InvalidArgumentError(f"Part number {part_number} is out of range 1..{total}")
        return min(part_size, size - (part_number - 1) * part_size)

    @staticmethod
    def _assemble(session_dir: Path, meta: Dict[str, Any]) -> None:
        part_size = meta["part_size"]
        missing = []
        for index, f in enumerate(meta["files"]):
            part_dir = session_dir / "parts" / str(index)
            for n in range(1, _total_parts(f["size"], part_size) + 1):
                if not (part_dir / f"{n:06d}").is_file():
                    missing.append(f"{f['path']}#{n}")
        if missing:
            shown = ", ".join(missing[:10])
            raise InvalidArgumentError(f"Upload has missing parts: {shown}")

        root = session_dir / "tree" / meta["name"]
        for index, f in enumerate(meta["files"]):
            target = root if meta["kind"] == "file" else root / f["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")
            with tmp.open("wb") as out:
                part_dir = session_dir / "parts" / str(index)
                for n in range(1, _total_parts(f["size"], part_size) + 1):
                    with (part_dir / f"{n:06d}").open("rb") as part:
                        shutil.copyfileobj(part, out, _COPY_CHUNK_BYTES)
            if tmp.stat().st_size != f["size"]:
                tmp.unlink(missing_ok=True)
                raise InvalidArgumentError(f"Assembled size mismatch for {f['path']!r}")
            os.replace(tmp, target)
        shutil.rmtree(session_dir / "parts", ignore_errors=True)

    def _sweep_expired(self) -> None:
        if self.ttl_seconds <= 0 or not self.sessions_dir.is_dir():
            return
        cutoff = time.time() - self.ttl_seconds
        for entry in self.sessions_dir.iterdir():
            if not entry.is_dir() or not _SESSION_ID_RE.match(entry.name):
                continue
            marker = entry / _META_NAME
            try:
                mtime = (marker if marker.exists() else entry).stat().st_mtime
            except OSError:
                continue
            if mtime < cutoff:
                shutil.rmtree(entry, ignore_errors=True)


def build_session_store(server_config: Any, upload_temp_dir: Path) -> UploadSessionStore:
    """Build the store for the server's upload temp dir and ``server.upload`` limits."""
    ttl = getattr(getattr(server_config, "temp_upload", None), "ttl_seconds", 0) or 0
    return UploadSessionStore(upload_temp_dir, limits=server_config.upload, ttl_seconds=ttl)


__all__ = [
    "SESSION_TEMP_FILE_PREFIX",
    "UploadSessionStore",
    "UploadTooLargeError",
    "build_session_store",
    "is_session_temp_file_id",
]
