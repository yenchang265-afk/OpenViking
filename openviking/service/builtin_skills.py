# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Install the bundled compile Skills into every account by default.

The Skills in ``openviking/builtin_skills/compile`` are installed into each
account's shared ``viking://agent/skills`` root, so ``ov compile`` and Studio
can use them without a manual ``ov add-skill``.

Installing never overwrites: a Skill whose directory already exists is left
as is. Each account records the names it has been given in
``/local/{account_id}/_system/builtin_skills.json``, so a built-in that an
admin deletes is not installed again. New built-ins added in later releases
are still installed once.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from openviking.pyagfs import AGFSAlreadyExistsError, AGFSNotFoundError, AsyncAGFSClient
from openviking.pyagfs.async_client import fs_ctx_from_agfs_path
from openviking.server.identity import RequestContext, Role
from openviking.service.task_store import SYSTEM_TASK_USER_ID
from openviking.storage.viking_fs import get_viking_fs
from openviking_cli.session.user_id import UserIdentifier
from openviking_cli.utils.logger import get_logger

logger = get_logger(__name__)

BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent.parent / "builtin_skills" / "compile"
BUILTIN_SKILLS_ROOT = "viking://agent/skills"
INSTALLED_RECORD_PATH = "/local/{account_id}/_system/builtin_skills.json"
_SOURCE_METADATA = {"type": "builtin", "source": "ov-compile-skills", "operation": "add"}


def bundled_skills() -> list[tuple[str, str]]:
    """Return ``(name, SKILL.md content)`` for every bundled Skill, by name."""
    return [
        (path.parent.name, path.read_text(encoding="utf-8"))
        for path in sorted(BUILTIN_SKILLS_DIR.glob("*/SKILL.md"))
    ]


async def _read_installed(client: AsyncAGFSClient, account_id: str) -> set[str]:
    path = INSTALLED_RECORD_PATH.format(account_id=account_id)
    try:
        result = await client.read(path, fs_ctx=fs_ctx_from_agfs_path(path))
    except AGFSNotFoundError:
        return set()
    raw = getattr(result, "content", result)
    try:
        names = json.loads(raw).get("installed", [])
    except (ValueError, AttributeError):
        logger.warning("Ignoring unreadable built-in Skill record at %s", path)
        return set()
    return {name for name in names if isinstance(name, str)} if isinstance(names, list) else set()


async def _write_installed(client: AsyncAGFSClient, account_id: str, names: Iterable[str]) -> None:
    path = INSTALLED_RECORD_PATH.format(account_id=account_id)
    parent = path.rsplit("/", 1)[0]
    try:
        await client.mkdir(parent, fs_ctx=fs_ctx_from_agfs_path(parent))
    except AGFSAlreadyExistsError:
        pass
    payload = json.dumps({"installed": sorted(names)}, indent=2).encode("utf-8")
    await client.write(path, payload, fs_ctx=fs_ctx_from_agfs_path(path))


async def install_builtin_skills(service: Any, account_id: str, *, wait: bool = False) -> list[str]:
    """Install the bundled Skills this account has never had; return their names."""
    viking_fs = get_viking_fs()
    client = AsyncAGFSClient(viking_fs.agfs)
    # The shared agent root belongs to the account, not to any one user.
    ctx = RequestContext(user=UserIdentifier(account_id, SYSTEM_TASK_USER_ID), role=Role.ROOT)
    recorded = await _read_installed(client, account_id)
    known = set(recorded)
    installed: list[str] = []
    for name, content in bundled_skills():
        if name in known:
            continue
        if not await viking_fs.exists(f"{BUILTIN_SKILLS_ROOT}/{name}", ctx=ctx):
            await service.resources.add_skill(
                content,
                ctx,
                allow_local_path_resolution=False,
                apply_privacy=False,
                wait=wait,
                target_uri=BUILTIN_SKILLS_ROOT,
                source_metadata=dict(_SOURCE_METADATA),
            )
            installed.append(name)
        known.add(name)
    if known != recorded:
        await _write_installed(client, account_id, known)
    if installed:
        logger.info("Installed built-in Skills for account %s: %s", account_id, installed)
    return installed


async def install_builtin_skills_for_accounts(service: Any, account_ids: Iterable[str]) -> None:
    """Best effort per account: one failing account does not stop the rest."""
    for account_id in account_ids:
        try:
            await install_builtin_skills(service, account_id)
        except Exception:
            logger.exception("Could not install built-in Skills for account %s", account_id)
