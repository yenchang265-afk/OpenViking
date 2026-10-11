# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Tests for the shared-upload SOURCE reference and worker materialization."""

import json
from pathlib import Path

import pytest

from openviking.parse.accessors.base import SourceType
from openviking.resource.shared_source import SharedSource, materialize_shared_source
from openviking.server.identity import RequestContext, Role
from openviking_cli.session.user_id import UserIdentifier


def _valid_payload() -> dict:
    return {
        "temp_file_id": "shared_2026010112abcdef",
        "content_uri": "viking://upload/2026010112/abcdef/content",
        "account_id": "acct-1",
        "original_filename": "repo.zip",
        "file_ext": ".zip",
        "meta": {"resolved_extension": ".zip"},
    }


class TestSharedSourceValidation:
    def test_roundtrip(self) -> None:
        src = SharedSource.from_dict(_valid_payload())
        assert src.temp_file_id == "shared_2026010112abcdef"
        assert src.content_uri == "viking://upload/2026010112/abcdef/content"
        assert SharedSource.from_dict(src.to_dict()) == src

    def test_rejects_non_shared_temp_file_id(self) -> None:
        payload = _valid_payload()
        payload["temp_file_id"] = "upload_plainlocal"
        with pytest.raises(ValueError, match="temp_file_id"):
            SharedSource.from_dict(payload)

    def test_rejects_content_uri_outside_upload_root(self) -> None:
        payload = _valid_payload()
        payload["content_uri"] = "viking://resources/secret/content"
        with pytest.raises(ValueError, match="content_uri"):
            SharedSource.from_dict(payload)

    def test_rejects_missing_account(self) -> None:
        payload = _valid_payload()
        payload["account_id"] = ""
        with pytest.raises(ValueError, match="account_id"):
            SharedSource.from_dict(payload)

    def test_payload_queued_before_sessions_reads_as_a_single_file(self) -> None:
        src = SharedSource.from_dict(_valid_payload())
        assert (src.layout, src.kind) == ("file", "file")

    @pytest.mark.parametrize(
        ("layout", "kind"), [("zip", "file"), ("session", "symlink"), ("file", "directory")]
    )
    def test_rejects_unknown_layout_or_kind(self, layout: str, kind: str) -> None:
        payload = {**_valid_payload(), "layout": layout, "kind": kind}
        with pytest.raises(ValueError, match="layout|kind"):
            SharedSource.from_dict(payload)


class _FakeVikingFS:
    def __init__(
        self,
        content: bytes,
        content_uri: str,
        account_id: str,
        *,
        exists: bool = True,
    ) -> None:
        self._content = content
        self._content_uri = content_uri
        self._account_id = account_id
        self._exists = exists
        self.read_calls: list[str] = []
        self.read_contexts = []

    async def exists(self, uri: str, *, ctx) -> bool:
        return self._exists and uri == self._content_uri

    async def read_file_to_path(self, uri: str, local_path, *, ctx) -> int:
        self.read_calls.append(uri)
        self.read_contexts.append(ctx)
        if uri != self._content_uri:
            raise FileNotFoundError(uri)
        Path(local_path).write_bytes(self._content)
        return len(self._content)

    async def read_file_bytes(self, uri: str, *, ctx) -> bytes:
        raise AssertionError("materialize must stream instead of buffering the upload")


def _ctx() -> RequestContext:
    return RequestContext(user=UserIdentifier("acct-1", "user-1"), role=Role.USER)


@pytest.mark.asyncio
class TestMaterializeSharedSource:
    async def test_downloads_content_once_to_local_file(self) -> None:
        src = SharedSource.from_dict(_valid_payload())
        vfs = _FakeVikingFS(b"PK\x03\x04zip-bytes", src.content_uri, "acct-1")

        resource = await materialize_shared_source(src, viking_fs=vfs, ctx=_ctx())
        try:
            assert resource.source_type == SourceType.LOCAL
            assert resource.path.exists()
            assert resource.path.suffix == ".zip"
            assert resource.path.read_bytes() == b"PK\x03\x04zip-bytes"
            # Worker downloads the shared object exactly once; API never staged it.
            assert vfs.read_calls == [src.content_uri]
            assert vfs.read_contexts[0].role == "root"
            assert vfs.read_contexts[0].account_id == "acct-1"
        finally:
            resource.cleanup()
        assert not resource.path.exists()

    async def test_missing_content_fails_without_writing_file(self) -> None:
        src = SharedSource.from_dict(_valid_payload())
        vfs = _FakeVikingFS(b"", "viking://upload/other/leaf/content", "acct-1")

        with pytest.raises(ValueError, match="missing"):
            await materialize_shared_source(src, viking_fs=vfs, ctx=_ctx())

    async def test_exact_read_succeeds_even_when_exists_is_stale(self) -> None:
        src = SharedSource.from_dict(_valid_payload())
        vfs = _FakeVikingFS(b"payload", src.content_uri, "acct-1", exists=False)

        resource = await materialize_shared_source(src, viking_fs=vfs, ctx=_ctx())
        try:
            assert resource.path.read_bytes() == b"payload"
        finally:
            resource.cleanup()


_SESSION_ROOT = "viking://upload/2026010112/" + "a" * 32


class _FakeSessionVFS:
    """Shared storage holding one chunked session: a manifest and its parts."""

    def __init__(self, manifest: dict, parts: dict[str, bytes]) -> None:
        self.objects = {f"{_SESSION_ROOT}/session.json": json.dumps(manifest).encode()}
        self.objects.update({f"{_SESSION_ROOT}/parts/{k}": v for k, v in parts.items()})
        self.read_calls: list[str] = []

    async def read_file(self, uri: str, *, ctx) -> str:
        if uri not in self.objects:
            raise FileNotFoundError(uri)
        return self.objects[uri].decode()

    async def read_file_to_path(self, uri: str, local_path, *, ctx) -> int:
        self.read_calls.append(uri)
        if uri not in self.objects:
            raise FileNotFoundError(uri)
        Path(local_path).write_bytes(self.objects[uri])
        return len(self.objects[uri])

    async def read_file_bytes(self, uri: str, *, ctx) -> bytes:
        raise AssertionError("session parts must be streamed, not buffered")


def _session_source(kind: str, name: str) -> SharedSource:
    return SharedSource.from_dict(
        {
            "temp_file_id": "shared_2026010112-" + "a" * 32,
            "content_uri": _SESSION_ROOT,
            "account_id": "acct-1",
            "original_filename": name,
            "file_ext": Path(name).suffix if kind == "file" else "",
            "meta": {},
            "layout": "session",
            "kind": kind,
        }
    )


def _manifest(kind: str, name: str, files: list[tuple[str, int]], **extra) -> dict:
    return {
        "kind": kind,
        "name": name,
        "part_size": 4,
        "files": [{"path": p, "size": n} for p, n in files],
        "completed": True,
        **extra,
    }


@pytest.mark.asyncio
class TestMaterializeSharedSession:
    async def test_joins_a_file_from_its_parts(self) -> None:
        src = _session_source("file", "report.txt")
        vfs = _FakeSessionVFS(
            _manifest("file", "report.txt", [("report.txt", 10)]),
            {"0/000001": b"0123", "0/000002": b"4567", "0/000003": b"89"},
        )

        resource = await materialize_shared_source(src, viking_fs=vfs, ctx=_ctx())
        try:
            assert resource.path.name == "report.txt"
            assert resource.path.read_bytes() == b"0123456789"
            assert vfs.read_calls == [f"{_SESSION_ROOT}/parts/0/00000{n}" for n in (1, 2, 3)]
        finally:
            resource.cleanup()
        assert not resource.path.exists()

    async def test_rebuilds_a_folder_tree(self) -> None:
        src = _session_source("directory", "docs")
        vfs = _FakeSessionVFS(
            _manifest("directory", "docs", [("a.md", 5), ("sub/deep/b.txt", 3), ("e.md", 0)]),
            {"0/000001": b"# he", "0/000002": b"l", "1/000001": b"xyz"},
        )

        resource = await materialize_shared_source(src, viking_fs=vfs, ctx=_ctx())
        try:
            root = resource.path
            assert root.name == "docs" and root.is_dir()
            restored = {
                p.relative_to(root).as_posix(): p.read_bytes()
                for p in root.rglob("*")
                if p.is_file()
            }
            assert restored == {"a.md": b"# hel", "sub/deep/b.txt": b"xyz", "e.md": b""}
        finally:
            resource.cleanup()
        assert not root.exists()

    @pytest.mark.parametrize(
        ("manifest", "parts", "error"),
        [
            (
                _manifest("file", "f.txt", [("f.txt", 3)], completed=False),
                {"0/000001": b"abc"},
                "not completed",
            ),
            (
                _manifest("directory", "d", [("../escape.txt", 3)]),
                {"0/000001": b"abc"},
                "Unsafe|escapes",
            ),
            (_manifest("file", "f.txt", [("f.txt", 3)]), {"0/000001": b"ab"}, "expected 3"),
            (_manifest("file", "f.txt", [("f.txt", 3)]), {}, "missing"),
        ],
        ids=["incomplete", "path-escape", "short-part", "missing-part"],
    )
    async def test_refuses_a_bad_session(self, manifest, parts, error) -> None:
        src = _session_source(manifest["kind"], manifest["name"])

        with pytest.raises(ValueError, match=error):
            await materialize_shared_source(
                src, viking_fs=_FakeSessionVFS(manifest, parts), ctx=_ctx()
            )
