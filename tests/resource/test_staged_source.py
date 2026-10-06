"""Durable source staging streams files through VikingFS instead of buffering them."""

import os
import shutil

import pytest

from openviking.parse.accessors.base import LocalResource, SourceType
from openviking.pyagfs import get_binding_client
from openviking.resource.staged_source import materialize_source, stage_source
from openviking.server.identity import RequestContext, Role
from openviking.storage.viking_fs import VikingFS
from openviking.utils.agfs_utils import RagfsBindingConfig, mount_agfs_backend
from openviking_cli.session.user_id import UserIdentifier
from openviking_cli.utils.config.agfs_config import AGFSConfig


@pytest.fixture
def streaming_only_fs(tmp_path, monkeypatch):
    """Real binding VikingFS whose whole-file byte methods fail if called."""
    try:
        client_type, _ = get_binding_client()
    except ImportError:
        client_type = None
    if client_type is None:
        pytest.skip("RAGFS native extension is unavailable")
    config = RagfsBindingConfig(agfs=AGFSConfig(path=str(tmp_path / "agfs"), backend="local"))
    client = client_type(None, config=config.to_binding_dict())
    mount_agfs_backend(client, config)
    vfs = VikingFS(agfs=client)

    async def no_buffered_io(*args, **kwargs):
        raise AssertionError("staging must not buffer whole files")

    monkeypatch.setattr(vfs, "write_file_bytes", no_buffered_io)
    monkeypatch.setattr(vfs, "read_file_bytes", no_buffered_io)
    return vfs


def root_ctx() -> RequestContext:
    return RequestContext(user=UserIdentifier.the_default_user(), role=Role(Role.ROOT))


def _resource(path) -> LocalResource:
    return LocalResource(
        path=path,
        source_type=SourceType.LOCAL,
        original_source=str(path),
        meta={"original_filename": path.name},
        is_temporary=False,
    )


async def _round_trip(vfs, source):
    staged = await stage_source(_resource(source), viking_fs=vfs, ctx=root_ctx())
    restored = await materialize_source(staged, viking_fs=vfs, ctx=root_ctx())
    return staged, restored


@pytest.mark.asyncio
async def test_single_file_round_trips_through_path_io(streaming_only_fs, tmp_path):
    data = bytes(i % 251 for i in range(3 * 1024 * 1024 + 7))
    source = tmp_path / "report.pdf"
    source.write_bytes(data)

    staged, restored = await _round_trip(streaming_only_fs, source)

    try:
        assert restored.path.name == "report.pdf"
        assert restored.path.read_bytes() == data
        assert staged.meta == {"original_filename": "report.pdf"}
    finally:
        shutil.rmtree(restored.meta["_cleanup_path"], ignore_errors=True)


@pytest.mark.asyncio
async def test_directory_round_trips_and_skips_symlinks(streaming_only_fs, tmp_path):
    source = tmp_path / "docs"
    (source / "sub" / "deeper").mkdir(parents=True)
    (source / "a.txt").write_bytes(b"alpha")
    (source / "empty.txt").write_bytes(b"")
    (source / "sub" / "b.bin").write_bytes(bytes(range(256)) * 4096)
    (source / "sub" / "deeper" / "c.md").write_bytes(b"# c")
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"secret")
    os.symlink(outside, source / "link.txt")

    _, restored = await _round_trip(streaming_only_fs, source)

    try:
        files = {
            p.relative_to(restored.path).as_posix(): p.read_bytes()
            for p in restored.path.rglob("*")
            if p.is_file()
        }
        assert files == {
            "a.txt": b"alpha",
            "empty.txt": b"",
            "sub/b.bin": bytes(range(256)) * 4096,
            "sub/deeper/c.md": b"# c",
        }
    finally:
        shutil.rmtree(restored.meta["_cleanup_path"], ignore_errors=True)
