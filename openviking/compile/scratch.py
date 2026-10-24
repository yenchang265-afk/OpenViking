"""Task-private scratch directory replacing the bot sandbox's file API for Compile."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path, PurePosixPath


class ScratchDir:
    """Confine relative task paths to one local directory.

    The pipeline only needs file reads, writes and same-directory replacement;
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

    async def read_file_bytes(self, relative: str) -> bytes:
        path = self.local_file_path(relative)
        return await asyncio.to_thread(path.read_bytes)

    def reset(self) -> None:
        """Start a fresh attempt; interrupted attempts re-run from the beginning."""
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)

    def remove(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
