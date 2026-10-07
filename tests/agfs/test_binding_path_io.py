"""Path-based I/O through the real ragfs_python binding (write_file_from_path / read_file_to_path).

Skipped when the native binding is not built into openviking/lib.
"""

from pathlib import Path

import pytest

from openviking.pyagfs import get_binding_client
from openviking.pyagfs.exceptions import AGFSIoError, AGFSNotFoundError

try:
    RAGFSBindingClient, _ = get_binding_client()
except ImportError:
    RAGFSBindingClient = None

pytestmark = pytest.mark.skipif(RAGFSBindingClient is None, reason="ragfs_python binding not built")

_CTX = {"account_id": "acct"}


@pytest.fixture
def client(tmp_path: Path):
    root = tmp_path / "fs"
    (root / "acct").mkdir(parents=True)
    c = RAGFSBindingClient()
    c.mount("localfs", "/local", {"local_dir": str(root)})
    return c


@pytest.mark.parametrize("size", [0, 3 * 1024 * 1024 + 5])
def test_write_file_from_path_and_read_file_to_path_round_trip(client, tmp_path, size):
    data = bytes(i % 251 for i in range(size))
    src = tmp_path / "src.bin"
    dst = tmp_path / "dst.bin"
    src.write_bytes(data)

    written = client.write_file_from_path("/local/acct/a.bin", str(src), ctx=_CTX)
    read = client.read_file_to_path("/local/acct/a.bin", str(dst), ctx=_CTX)

    assert (written, read) == (size, size)
    assert dst.read_bytes() == data
    assert client.read("/local/acct/a.bin", ctx=_CTX) == data


def test_write_file_from_path_missing_source_raises_io_error(client, tmp_path):
    with pytest.raises(AGFSIoError):
        client.write_file_from_path("/local/acct/a.bin", str(tmp_path / "missing.bin"), ctx=_CTX)


def test_read_file_to_path_missing_file_raises_not_found(client, tmp_path):
    with pytest.raises(AGFSNotFoundError):
        client.read_file_to_path("/local/acct/missing.bin", str(tmp_path / "out"), ctx=_CTX)
