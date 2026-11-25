# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0

import io
import json
import tempfile
import zipfile
from email.parser import BytesParser
from email.policy import default
from pathlib import Path

import httpx
import pytest
from openviking_sdk import AsyncHTTPClient, OpenVikingError, SyncHTTPClient


class _SessionServer:
    """Mock upload-session API that records requests and assembles parts."""

    def __init__(
        self, *, part_size=4, create_status=200, fail_part=None, fail_status=500, fail_times=None
    ):
        self.part_size = part_size
        self.create_status = create_status
        self.fail_part = fail_part
        self.fail_status = fail_status
        # None: fail_part always fails; N: it fails its first N attempts.
        self.fail_times = fail_times
        self.part_attempts = {}
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
            key = (int(index), int(number))
            attempt = self.part_attempts.get(key, 0)
            self.part_attempts[key] = attempt + 1
            if self.fail_part == key and (self.fail_times is None or attempt < self.fail_times):
                return httpx.Response(
                    self.fail_status, json={"status": "error", "error": {"message": "boom"}}
                )
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
async def test_failed_part_aborts_the_session(tmp_path, no_retry_delay):
    server = _SessionServer(part_size=4, fail_part=(0, 2))
    client = _client_for(server)
    file_path = tmp_path / "f.bin"
    file_path.write_bytes(b"0123456789")

    with pytest.raises(OpenVikingError):
        await client._upload_path(file_path)

    assert server.requests[-1] == ("DELETE", "/api/v1/uploads/u1")
    assert ("POST", "/api/v1/uploads/u1/complete") not in server.requests


@pytest.fixture
def no_retry_delay(monkeypatch):
    monkeypatch.setattr("openviking_sdk._upload._PART_RETRY_BASE_DELAY", 0)


@pytest.mark.asyncio
async def test_transient_part_failure_is_retried(tmp_path, no_retry_delay):
    server = _SessionServer(part_size=4, fail_part=(0, 2), fail_status=503, fail_times=2)
    client = _client_for(server)
    file_path = tmp_path / "f.bin"
    file_path.write_bytes(b"0123456789")

    assert await client._upload_path(file_path) == "session_u1"
    assert server.part_attempts[(0, 2)] == 3
    assert server.assembled(0) == b"0123456789"


@pytest.mark.asyncio
async def test_rejected_part_is_not_retried(tmp_path, no_retry_delay):
    server = _SessionServer(part_size=4, fail_part=(0, 2), fail_status=400)
    client = _client_for(server)
    file_path = tmp_path / "f.bin"
    file_path.write_bytes(b"0123456789")

    with pytest.raises(OpenVikingError):
        await client._upload_path(file_path)
    assert server.part_attempts[(0, 2)] == 1
    assert server.requests[-1] == ("DELETE", "/api/v1/uploads/u1")


def _change_after_listing(monkeypatch, change):
    from openviking_sdk import _upload

    original = _upload.list_upload_files

    def listing_then_change(path):
        entries = original(path)
        change(path)
        return entries

    monkeypatch.setattr(_upload, "list_upload_files", listing_then_change)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("label", "change", "changed_path"),
    [
        ("grows", lambda root: (root / "a.md").write_bytes(b"0123456789-more"), "a.md"),
        ("shrinks", lambda root: (root / "sub" / "b.txt").write_bytes(b"x"), "sub/b.txt"),
        ("is removed", lambda root: (root / "sub" / "b.txt").unlink(), "sub/b.txt"),
    ],
)
async def test_file_changed_after_listing_fails_naming_it(
    tmp_path, monkeypatch, label, change, changed_path
):
    server = _SessionServer(part_size=4)
    client = _client_for(server)
    folder = _make_folder(tmp_path)
    _change_after_listing(monkeypatch, change)

    with pytest.raises(OpenVikingError) as raised:
        await client._upload_path(folder)

    assert changed_path in str(raised.value), label
    assert "changed while uploading" in str(raised.value), label
    assert raised.value.code == "FAILED_PRECONDITION"
    assert server.requests[-1] == ("DELETE", "/api/v1/uploads/u1")
    # Never more than the declared bytes are offered for a file.
    for index, entry in enumerate(server.files):
        assert len(server.assembled(index)) <= entry["size"]


def test_directory_import_removes_partial_zip(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "first.txt").write_text("first", encoding="utf-8")
    (source / "second.txt").write_text("second", encoding="utf-8")
    archives = tmp_path / "archives"
    archives.mkdir()
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(archives))
    original_write = zipfile.ZipFile.write

    def fail_after_first_entry(archive, filename, *args, **kwargs):
        if archive.namelist():
            raise FileNotFoundError("source disappeared during packing")
        return original_write(archive, filename, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "write", fail_after_first_entry)
    # add_resource prefers upload sessions (no zip); shared mode takes the zip path.
    client = SyncHTTPClient(url="http://localhost:1933", upload_mode="shared")

    with pytest.raises(FileNotFoundError, match="source disappeared during packing"):
        client.add_resource(str(source))

    assert list(archives.iterdir()) == []
    assert (source / "first.txt").read_text(encoding="utf-8") == "first"
    assert (source / "second.txt").read_text(encoding="utf-8") == "second"


@pytest.mark.asyncio
@pytest.mark.parametrize("with_links", [False, True], ids=["regular-files", "omit-links"])
async def test_zip_directory_creates_forward_slash_paths(
    tmp_path, monkeypatch, sdk_transport, with_links
):
    source = tmp_path / "project"
    nested = source / "subdir"
    nested.mkdir(parents=True)
    (source / "same.txt").write_bytes(b"root")
    (nested / "same.txt").write_bytes(b"nested")
    if with_links:
        outside = tmp_path / "outside.txt"
        outside.write_bytes(b"outside")
        try:
            (source / "file-link").symlink_to(outside)
            (source / "inside-link").symlink_to(source / "same.txt")
            (source / "dir-link").symlink_to(tmp_path, target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"symlinks are not available in this environment: {exc}")
    archives = tmp_path / "archives"
    archives.mkdir()
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(archives))
    result = {"root_uri": "viking://resources/project"}
    paths = []

    def handle(request):
        paths.append(request.url.path)
        if request.url.path == "/api/v1/resources/temp_upload":
            message = BytesParser(policy=default).parsebytes(
                f"Content-Type: {request.headers['content-type']}\r\n\r\n".encode()
                + request.content
            )
            file_part = next(part for part in message.iter_parts() if part.get_filename())
            zip_data = file_part.get_payload(decode=True)
            assert isinstance(zip_data, bytes)
            with zipfile.ZipFile(io.BytesIO(zip_data)) as archive:
                assert sorted(archive.namelist()) == ["same.txt", "subdir/same.txt"]
                assert archive.read("same.txt") == b"root"
                assert archive.read("subdir/same.txt") == b"nested"
            return httpx.Response(
                200, json={"status": "ok", "result": {"temp_file_id": "upload-1"}}
            )
        assert json.loads(request.content) == {
            "source_name": "project",
            "temp_file_id": "upload-1",
            "wait": False,
        }
        return httpx.Response(200, json={"status": "ok", "result": result})

    sdk_transport(handle)
    # add_resource prefers upload sessions (no zip); shared mode takes the zip path.
    client = AsyncHTTPClient(url="http://localhost:1933", upload_mode="shared")
    await client.initialize()
    try:
        assert await client.add_resource(str(source)) == result
    finally:
        await client.close()

    assert paths == ["/api/v1/resources/temp_upload", "/api/v1/resources"]
    assert list(archives.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("upload_mode", "expected_mode"),
    # Fork: local mode uploads through sessions, so only shared mode posts temp_upload.
    [(None, b"shared"), ("shared", b"shared")],
    ids=["from-config", "explicit"],
)
async def test_upload_temp_file_forwards_upload_mode(
    tmp_path, monkeypatch, sdk_transport, upload_mode, expected_mode
):
    config = tmp_path / "ovcli.conf"
    config.write_text(
        json.dumps(
            {
                "url": "http://gateway.example",
                "gateway_token": "gateway-token",
                "upload": {
                    "mode": "shared",
                    "ignore_dirs": ".cache",
                    "include": "*.md",
                    "exclude": "*.tmp",
                },
            }
        )
    )
    monkeypatch.setenv("OPENVIKING_CLI_CONFIG_FILE", str(config))
    source = tmp_path / "demo.md"
    source.write_bytes(b"# Demo\n")
    requests = []

    def handle(request):
        requests.append(request)
        token = request.headers.get("X-Gateway-Token")
        if token is None:
            return httpx.Response(401, headers={"X-VikingBot-Gateway": "true"})
        if request.url.path == "/api/v1/resources/temp_upload":
            message = BytesParser(policy=default).parsebytes(
                f"Content-Type: {request.headers['content-type']}\r\n\r\n".encode()
                + request.content
            )
            file_part, mode_part = sorted(
                message.iter_parts(),
                key=lambda part: part.get_filename() is None,
            )
            assert file_part.get_filename() == "demo.md"
            assert file_part.get_payload(decode=True) == b"# Demo\n"
            assert mode_part.get_param("name", header="content-disposition") == "upload_mode"
            assert mode_part.get_payload(decode=True) == expected_mode
            return httpx.Response(
                200, json={"status": "ok", "result": {"temp_file_id": "upload-1"}}
            )
        assert json.loads(request.content)["temp_file_id"] == "upload-1"
        return httpx.Response(
            200, json={"status": "ok", "result": {"root_uri": "viking://resources/demo"}}
        )

    sdk_transport(handle)
    client = AsyncHTTPClient(upload_mode=upload_mode)
    await client.initialize()
    try:
        assert (await client.add_resource(str(source)))["root_uri"] == "viking://resources/demo"
    finally:
        await client.close()

    assert [(r.method, r.url.path, r.headers.get("X-Gateway-Token")) for r in requests] == [
        ("GET", "/health", None),
        ("POST", "/api/v1/resources/temp_upload", "gateway-token"),
        ("POST", "/api/v1/resources", None),
        ("POST", "/api/v1/resources", "gateway-token"),
    ]
