import json
import tempfile
import zipfile
from pathlib import Path

import httpx
import pytest
from openviking_sdk import AsyncHTTPClient, OpenVikingError


class _SessionServer:
    """Mock upload-session API that records requests and assembles parts."""

    def __init__(self, *, part_size=4, create_status=200, fail_part=None):
        self.part_size = part_size
        self.create_status = create_status
        self.fail_part = fail_part
        self.requests = []
        self.files = []
        self.parts = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.requests.append((request.method, path))
        if request.method == "POST" and path == "/api/v1/uploads":
            if self.create_status != 200:
                return httpx.Response(self.create_status, json={"status": "error"})
            body = json.loads(request.content)
            self.files = body["files"]
            self.kind, self.name = body["kind"], body["name"]
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "result": {"upload_id": "u1", "part_size_bytes": self.part_size},
                },
            )
        if request.method == "PUT" and path.startswith("/api/v1/uploads/u1/files/"):
            _, index, _, number = path.rsplit("/", 3)
            if self.fail_part == (int(index), int(number)):
                return httpx.Response(500, json={"status": "error", "error": {"message": "boom"}})
            self.parts[(int(index), int(number))] = request.content
            return httpx.Response(200, json={"status": "ok", "result": {}})
        if request.method == "POST" and path == "/api/v1/uploads/u1/complete":
            return httpx.Response(
                200, json={"status": "ok", "result": {"temp_file_id": "session_u1"}}
            )
        if request.method == "DELETE" and path == "/api/v1/uploads/u1":
            return httpx.Response(200, json={"status": "ok", "result": {}})
        if request.method == "POST" and path == "/api/v1/resources/temp_upload":
            return httpx.Response(200, json={"status": "ok", "result": {"temp_file_id": "legacy"}})
        return httpx.Response(404, json={"status": "error"})

    def assembled(self, index):
        numbers = sorted(n for i, n in self.parts if i == index)
        return b"".join(self.parts[(index, n)] for n in numbers)


def _client_for(server, **kwargs) -> AsyncHTTPClient:
    client = AsyncHTTPClient(url="http://testserver", **kwargs)
    client._http = httpx.AsyncClient(
        transport=httpx.MockTransport(server), base_url="http://testserver"
    )
    return client


def _make_folder(tmp_path: Path) -> Path:
    root = tmp_path / "docs"
    (root / "sub").mkdir(parents=True)
    (root / "a.md").write_bytes(b"0123456789")
    (root / "sub" / "b.txt").write_bytes(b"xyz")
    (root / "empty.txt").write_bytes(b"")
    return root


@pytest.mark.asyncio
async def test_folder_upload_uses_session_parts_without_zip(tmp_path):
    server = _SessionServer(part_size=4)
    client = _client_for(server)
    folder = _make_folder(tmp_path)

    temp_file_id = await client._upload_path(folder)

    assert temp_file_id == "session_u1"
    assert (server.kind, server.name) == ("directory", "docs")
    by_path = {f["path"]: i for i, f in enumerate(server.files)}
    assert set(by_path) == {"a.md", "sub/b.txt", "empty.txt"}
    assert server.assembled(by_path["a.md"]) == b"0123456789"
    assert sorted(n for i, n in server.parts if i == by_path["a.md"]) == [1, 2, 3]
    assert server.assembled(by_path["sub/b.txt"]) == b"xyz"
    assert ("POST", "/api/v1/resources/temp_upload") not in server.requests


@pytest.mark.asyncio
async def test_file_upload_uses_a_file_session(tmp_path):
    server = _SessionServer(part_size=3)
    client = _client_for(server)
    file_path = tmp_path / "report.pdf"
    file_path.write_bytes(b"abcdefg")

    assert await client._upload_path(file_path) == "session_u1"
    assert (server.kind, server.name) == ("file", "report.pdf")
    assert server.files == [{"path": "report.pdf", "size": 7}]
    assert server.assembled(0) == b"abcdefg"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [404, 405, 409])
async def test_falls_back_to_legacy_upload_when_sessions_unavailable(tmp_path, status):
    server = _SessionServer(create_status=status)
    client = _client_for(server)

    assert await client._upload_path(_make_folder(tmp_path)) == "legacy"
    assert server.requests[-1] == ("POST", "/api/v1/resources/temp_upload")


@pytest.mark.asyncio
async def test_shared_upload_mode_skips_sessions(tmp_path):
    server = _SessionServer()
    client = _client_for(server, upload_mode="shared")
    file_path = tmp_path / "f.md"
    file_path.write_text("# f\n")

    assert await client._upload_path(file_path) == "legacy"
    assert server.requests == [("POST", "/api/v1/resources/temp_upload")]


@pytest.mark.asyncio
async def test_failed_part_aborts_the_session(tmp_path):
    server = _SessionServer(part_size=4, fail_part=(0, 2))
    client = _client_for(server)
    file_path = tmp_path / "f.bin"
    file_path.write_bytes(b"0123456789")

    with pytest.raises(OpenVikingError):
        await client._upload_path(file_path)

    assert server.requests[-1] == ("DELETE", "/api/v1/uploads/u1")
    assert ("POST", "/api/v1/uploads/u1/complete") not in server.requests


class _FakeHTTPClient:
    def __init__(self):
        self.calls = []

    async def post(self, path, json=None, files=None, data=None):
        self.calls.append({"path": path, "json": json, "files": files, "data": data})
        return object()


def test_zip_directory_creates_forward_slash_paths():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        root_dir = tmpdir / "test_project"
        root_dir.mkdir()
        (root_dir / "file1.txt").write_text("content1")
        (root_dir / "subdir").mkdir()
        (root_dir / "subdir" / "file2.txt").write_text("content2")

        client = AsyncHTTPClient(url="http://localhost:1933")
        zip_path = client._zip_directory(str(root_dir))

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                assert "file1.txt" in names
                assert "subdir/file2.txt" in names
                assert all("\\" not in name for name in names)
        finally:
            Path(zip_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_upload_temp_file_forwards_upload_mode():
    with tempfile.TemporaryDirectory() as tmpdir:
        upload_file = Path(tmpdir) / "demo.md"
        upload_file.write_text("# Demo\n")

        client = AsyncHTTPClient(
            url="http://localhost:1933",
            upload_mode="shared",
        )
        fake_http = _FakeHTTPClient()
        client._http = fake_http
        client._handle_response = lambda _response: {"temp_file_id": "shared_abc"}

        temp_file_id = await client._upload_temp_file(str(upload_file))

        assert temp_file_id == "shared_abc"
        call = fake_http.calls[-1]
        assert call["path"] == "/api/v1/resources/temp_upload"
        assert call["data"] == {"upload_mode": "shared"}
