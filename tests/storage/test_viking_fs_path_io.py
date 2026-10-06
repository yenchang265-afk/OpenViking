"""VikingFS path-based file I/O (write_file_from_path / read_file_to_path) on real storage."""

import pytest

from openviking.pyagfs import get_binding_client
from openviking.server.identity import RequestContext, Role
from openviking.storage.viking_fs import VikingFS
from openviking.utils.agfs_utils import RagfsBindingConfig, mount_agfs_backend
from openviking_cli.exceptions import InvalidArgumentError, NotFoundError, PermissionDeniedError
from openviking_cli.session.user_id import UserIdentifier
from openviking_cli.utils.config.agfs_config import AGFSConfig


@pytest.fixture
def binding_fs(tmp_path):
    try:
        client_type, _ = get_binding_client()
    except ImportError:
        client_type = None
    if client_type is None:
        pytest.skip("RAGFS native extension is unavailable")
    config = RagfsBindingConfig(agfs=AGFSConfig(path=str(tmp_path / "agfs"), backend="local"))
    client = client_type(None, config=config.to_binding_dict())
    mount_agfs_backend(client, config)
    return VikingFS(agfs=client)


def root_ctx() -> RequestContext:
    return RequestContext(user=UserIdentifier.the_default_user(), role=Role(Role.ROOT))


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [0, 3 * 1024 * 1024 + 5])
async def test_write_file_from_path_round_trips_and_creates_parents(binding_fs, tmp_path, size):
    data = bytes(i % 251 for i in range(size))
    src = tmp_path / "src.bin"
    dst = tmp_path / "dst.bin"
    src.write_bytes(data)
    uri = "viking://resources/nested/dir/file.bin"

    written = await binding_fs.write_file_from_path(uri, src, ctx=root_ctx())
    read = await binding_fs.read_file_to_path(uri, dst, ctx=root_ctx())

    assert (written, read) == (size, size)
    assert dst.read_bytes() == data
    assert await binding_fs.read_file_bytes(uri, ctx=root_ctx()) == data


@pytest.mark.asyncio
async def test_write_file_from_path_checks_write_acl_before_writing(
    binding_fs, tmp_path, monkeypatch
):
    src = tmp_path / "src.bin"
    src.write_bytes(b"payload")
    uri = "viking://resources/denied.bin"
    actions = []

    async def deny(checked_uri, ctx=None, action=None):
        actions.append(action)
        raise PermissionDeniedError(f"denied: {checked_uri}")

    monkeypatch.setattr(binding_fs, "_ensure_access", deny)

    with pytest.raises(PermissionDeniedError):
        await binding_fs.write_file_from_path(uri, src, ctx=root_ctx())

    monkeypatch.undo()
    assert [a.name for a in actions] == ["WRITE"]
    with pytest.raises(NotFoundError):
        await binding_fs.read_file_bytes(uri, ctx=root_ctx())


@pytest.mark.asyncio
async def test_read_file_to_path_missing_file_raises_not_found(binding_fs, tmp_path):
    with pytest.raises(NotFoundError):
        await binding_fs.read_file_to_path(
            "viking://resources/missing.bin", tmp_path / "out", ctx=root_ctx()
        )


@pytest.mark.asyncio
async def test_read_file_to_path_rejects_directory(binding_fs, tmp_path):
    await binding_fs.write_file_bytes("viking://resources/folder/child.txt", b"x", ctx=root_ctx())

    with pytest.raises(InvalidArgumentError):
        await binding_fs.read_file_to_path(
            "viking://resources/folder", tmp_path / "out", ctx=root_ctx()
        )
