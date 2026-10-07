# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Measure peak RSS growth of the upload/ingest storage paths for one large file.

Run in its own process (see test_upload_memory.py) so pytest's memory does not skew
the numbers. Linux only: each scenario resets the high-water mark via
/proc/self/clear_refs and reports ``VmHWM - VmRSS(before)`` in MiB as JSON.

    python tests/integration/upload_memory_probe.py --backend local --size 1073741824
    python tests/integration/upload_memory_probe.py --backend s3 ...  # needs OV_S3_TEST_*

``control_buffered`` deliberately reads the whole file into memory; it must grow by at
least the file size, which proves the measurement can see buffering.
"""

import argparse
import asyncio
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Awaitable, Callable, Dict

MIB = 1024 * 1024


def _status_kib(field: str) -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(f"{field}:"):
            return int(line.split()[1])
    raise RuntimeError(f"{field} not found in /proc/self/status")


async def _measure(run: Callable[[], Awaitable[None]]) -> float:
    Path("/proc/self/clear_refs").write_text("5")
    before = _status_kib("VmRSS")
    await run()
    return (_status_kib("VmHWM") - before) / 1024


def _build_viking_fs(backend: str, workdir: Path, prefix: str):
    from openviking.pyagfs import get_binding_client
    from openviking.storage.viking_fs import VikingFS
    from openviking.utils.agfs_utils import RagfsBindingConfig, mount_agfs_backend
    from openviking_cli.utils.config.agfs_config import AGFSConfig, S3Config

    client_type, _ = get_binding_client()
    if backend == "s3":
        agfs = AGFSConfig(
            path=str(workdir / "agfs"),
            backend="s3",
            s3=S3Config(
                bucket=os.environ["OV_S3_TEST_BUCKET"],
                endpoint=os.environ["OV_S3_TEST_ENDPOINT"],
                access_key=os.environ["OV_S3_TEST_ACCESS_KEY"],
                secret_key=os.environ["OV_S3_TEST_SECRET_KEY"],
                region="us-east-1",
                prefix=prefix,
                use_ssl=os.environ["OV_S3_TEST_ENDPOINT"].startswith("https://"),
                use_path_style=True,
            ),
        )
    else:
        agfs = AGFSConfig(path=str(workdir / "agfs"), backend="local")
    config = RagfsBindingConfig(agfs=agfs)
    client = client_type(None, config=config.to_binding_dict())
    mount_agfs_backend(client, config)
    return VikingFS(agfs=client), client


class _FileUpload:
    """Minimal stand-in for Starlette's UploadFile, reading the file in chunks."""

    def __init__(self, path: Path) -> None:
        self.filename = path.name
        self.content_type = "application/octet-stream"
        self._file = path.open("rb")

    async def read(self, size: int) -> bytes:
        return self._file.read(size)

    def close(self) -> None:
        self._file.close()


async def _run(backend: str, size: int) -> Dict[str, float]:
    from types import SimpleNamespace

    from openviking.parse.accessors.base import LocalResource, SourceType
    from openviking.parse.output import AgfsParseOutputStore, ParseArtifactWriter
    from openviking.resource.staged_source import materialize_source, stage_source
    from openviking.server import temp_upload_store
    from openviking.server.identity import RequestContext, Role
    from openviking_cli.session.user_id import UserIdentifier

    workdir = Path(tempfile.mkdtemp(prefix="ov_upload_memory_"))
    prefix = f"_it/memory/{os.getpid()}-{time.time_ns()}/"
    vfs, client = _build_viking_fs(backend, workdir, prefix)
    ctx = RequestContext(user=UserIdentifier.the_default_user(), role=Role(Role.ROOT))
    src = workdir / "big.bin"
    with src.open("wb") as f:
        f.truncate(size)

    async def stage_and_materialize() -> None:
        resource = LocalResource(
            path=src, source_type=SourceType.LOCAL, original_source=str(src), is_temporary=False
        )
        staged = await stage_source(resource, viking_fs=vfs, ctx=ctx)
        restored = await materialize_source(staged, viking_fs=vfs, ctx=ctx)
        assert restored.path.stat().st_size == size
        shutil.rmtree(restored.meta["_cleanup_path"], ignore_errors=True)
        await vfs.delete_temp(staged.temp_uri, ctx=ctx)

    async def shared_temp_upload() -> None:
        temp_upload_store.get_viking_fs = lambda: vfs
        store = temp_upload_store.TempUploadStore(
            SimpleNamespace(
                temp_upload=SimpleNamespace(ttl_seconds=3600, shared_max_size_bytes=size + 1)
            )
        )
        store._schedule_shared_cleanup = lambda _ctx: None
        upload = _FileUpload(src)
        try:
            temp_file_id = await store.save_upload(upload, "shared", ctx)
        finally:
            upload.close()
        resolved = await store.resolve_for_consume(temp_file_id, ctx)
        assert Path(resolved.local_path).stat().st_size == size
        await resolved.cleanup()

    async def parse_artifact_write() -> None:
        writer = await ParseArtifactWriter.create(AgfsParseOutputStore(viking_fs=vfs, ctx=ctx))
        await writer.write_from_path("doc/big.bin", src)
        await writer.finalize(resource_rel="doc")
        await writer.cleanup()

    async def control_buffered() -> None:
        await vfs.write_file_bytes(
            "viking://resources/_memory_control.bin", src.read_bytes(), ctx=ctx
        )

    results: Dict[str, float] = {}
    try:
        for name, scenario in [
            ("stage_and_materialize", stage_and_materialize),
            ("shared_temp_upload", shared_temp_upload),
            ("parse_artifact_write", parse_artifact_write),
            ("control_buffered", control_buffered),
        ]:
            results[name] = round(await _measure(scenario), 1)
    finally:
        try:
            client.rm("/local", recursive=True, ctx={"account_id": "_system"})
        except Exception:
            pass
        shutil.rmtree(workdir, ignore_errors=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["local", "s3"], default="local")
    parser.add_argument("--size", type=int, default=1024 * MIB)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(_run(args.backend, args.size))))


if __name__ == "__main__":
    main()
