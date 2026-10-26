"""Task-private scratch directory replacing the bot sandbox's file API for Compile."""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class ScratchFile:
    """A regular file in scratch; ``path`` is relative to the scratch root."""

    path: str
    size: int


class ScratchDir:
    """Confine relative task paths to one local directory.

    The pipeline only needs file reads, writes, listings and same-directory replacement;
    there is no command execution. Paths are POSIX-relative to the root.
    """

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.sandbox_cwd = str(self.root)

    def local_file_path(self, relative: str) -> Path:
        path = PurePosixPath(relative)
        if path.is_absolute():
            # Callers may pass sandbox_cwd-joined paths; accept only those under the root.
            candidate = Path(relative).resolve()
        else:
            if ".." in path.parts:
                raise ValueError(f"Scratch path escapes the task directory: {relative}")
            candidate = (self.root / Path(*path.parts)).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError(f"Scratch path escapes the task directory: {relative}")
        return candidate

    async def write_file(self, relative: str, content: str | bytes) -> None:
        path = self.local_file_path(relative)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content, encoding="utf-8")

        await asyncio.to_thread(write)

    async def write_file_bytes(self, relative: str, content: bytes) -> None:
        await self.write_file(relative, content)

    async def read_file_bytes(self, relative: str) -> bytes:
        path = self.local_file_path(relative)
        return await asyncio.to_thread(path.read_bytes)

    async def list_files(
        self, relative: str = ".", *, max_entries: int | None
    ) -> list[ScratchFile]:
        """Recursively list regular files below ``relative``; symlinks are not followed.

        Returned paths are relative to the scratch root and include ``relative``.
        A ``max_entries`` quota counts directories and files and raises ValueError
        on overflow; None lists everything.
        """
        if max_entries is not None and max_entries <= 0:
            raise ValueError("max_entries must be positive")
        start = PurePosixPath(relative)
        start_path = self.local_file_path(relative)

        def inventory() -> list[ScratchFile]:
            files: list[ScratchFile] = []
            pending = [(start, start_path)]
            visited = 0
            while pending:
                directory, local_directory = pending.pop()
                try:
                    entries = list(os.scandir(local_directory))
                except FileNotFoundError:
                    continue
                for entry in entries:
                    visited += 1
                    if max_entries is not None and visited > max_entries:
                        raise ValueError(f"Scratch inventory exceeds {max_entries} entries")
                    child = directory / entry.name
                    if entry.is_dir(follow_symlinks=False):
                        pending.append((child, Path(entry.path)))
                    elif entry.is_file(follow_symlinks=False):
                        size = entry.stat(follow_symlinks=False).st_size
                        files.append(ScratchFile(path=child.as_posix(), size=size))
            return sorted(files, key=lambda item: item.path)

        return await asyncio.to_thread(inventory)

    async def list_dir(self, relative: str) -> list[str]:
        """Return sorted entry names; directories end with ``/``."""
        path = self.local_file_path(relative)

        def entries() -> list[str]:
            if not path.is_dir():
                raise FileNotFoundError(relative)
            return sorted(
                f"{item.name}/" if item.is_dir() else item.name for item in path.iterdir()
            )

        return await asyncio.to_thread(entries)

    def reset(self) -> None:
        """Start a fresh attempt; interrupted attempts re-run from the beginning."""
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)

    def remove(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
