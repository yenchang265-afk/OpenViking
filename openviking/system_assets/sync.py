# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Synchronize packaged system assets into an account's system namespace."""

import asyncio
import base64
from dataclasses import replace
from pathlib import Path

from openviking.core.namespace import uri_parts
from openviking.core.namespace_policy import (
    SYSTEM_EXAMPLE_SKILLS_ROOT,
    SYSTEM_FIXED_DIRECTORIES,
    SYSTEM_MEMORY_BUILTIN_ROOT,
)
from openviking.server.identity import RequestContext, Role
from openviking.storage.content_write import ContentWriteCoordinator
from openviking.storage.errors import LockAcquisitionError, ResourceBusyError
from openviking.storage.viking_fs import VikingFS
from openviking.system_assets import SYSTEM_ASSETS_DIR
from openviking_cli.exceptions import NotFoundError
from openviking_cli.utils.logger import get_logger

logger = get_logger(__name__)

# Backoff between sync attempts on a root a peer instance is writing (~6 s total).
_LOCK_RETRY_DELAYS: tuple[float, ...] = (0.1, 0.3, 0.8, 1.6, 3.2)

_MANAGED_ASSET_ROOTS = (
    (Path("compile/example-skills"), SYSTEM_EXAMPLE_SKILLS_ROOT),
    (Path("memory/memory_templates/builtin"), SYSTEM_MEMORY_BUILTIN_ROOT),
)


class SystemAssetSynchronizer:
    """Converge one account's builtin assets to the packaged contents."""

    def __init__(
        self,
        viking_fs: VikingFS,
        assets_dir: Path = SYSTEM_ASSETS_DIR,
    ):
        self._viking_fs = viking_fs
        self._coordinator = ContentWriteCoordinator(viking_fs=viking_fs)
        self._assets_dir = assets_dir

    async def sync(self, ctx: RequestContext) -> int:
        root_ctx = replace(ctx, role=Role.ROOT, actor_peer_id=None)
        for uri in sorted(SYSTEM_FIXED_DIRECTORIES, key=lambda value: len(uri_parts(value))):
            await self._viking_fs.mkdir(uri, exist_ok=True, ctx=root_ctx)

        for relative_root, _ in _MANAGED_ASSET_ROOTS:
            source_root = self._assets_dir / relative_root
            if not source_root.is_dir():
                raise FileNotFoundError(f"packaged system asset directory not found: {source_root}")

        written = 0
        for relative_root, target_root in _MANAGED_ASSET_ROOTS:
            written += await self._sync_root(
                self._assets_dir / relative_root, target_root, root_ctx
            )
        return written

    async def _sync_root(
        self, source_root: Path, target_root: str, root_ctx: RequestContext
    ) -> int:
        """Write the assets that differ under one root; retry while a peer holds its lock.

        Instances starting together sync the same account at once. A busy root
        means a peer is writing it, so back off and recompute what still differs.
        """
        for delay in (*_LOCK_RETRY_DELAYS, None):
            operations = await self._pending_operations(source_root, target_root, root_ctx)
            if not operations:
                return 0
            try:
                await self._coordinator.batch_write(
                    root_uri=target_root,
                    operations=operations,
                    ctx=root_ctx,
                )
            except (LockAcquisitionError, ResourceBusyError):
                if delay is None:
                    raise
                logger.info(
                    "System assets under %s are being written by another instance; "
                    "retrying in %.2fs",
                    target_root,
                    delay,
                )
                await asyncio.sleep(delay)
                continue
            return len(operations)
        return 0

    async def _pending_operations(
        self, source_root: Path, target_root: str, root_ctx: RequestContext
    ) -> list[dict[str, str]]:
        operations = []
        for source_path in sorted(path for path in source_root.rglob("*") if path.is_file()):
            relative_path = source_path.relative_to(source_root).as_posix()
            target_uri = f"{target_root}/{relative_path}"
            expected = source_path.read_bytes()
            try:
                current = await self._viking_fs.read_file_bytes(target_uri, ctx=root_ctx)
            except (FileNotFoundError, NotFoundError):
                current = None
            if current == expected:
                continue
            operations.append(
                {
                    "uri": target_uri,
                    "content_base64": base64.b64encode(expected).decode("ascii"),
                    "mode": "replace",
                }
            )
        return operations
