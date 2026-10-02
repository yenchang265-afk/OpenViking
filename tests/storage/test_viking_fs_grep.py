# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0

import re
import time
from unittest.mock import AsyncMock

import pytest

import openviking.storage.viking_fs as viking_fs_module
from openviking.server.identity import RequestContext, Role
from openviking.storage.acl import AclEntry, AclLevel, AclMode, DirectAcl, EffectiveAcl
from openviking.storage.viking_fs import _DEFAULT_GREP_FILE_CONCURRENCY, VikingFS
from openviking.storage.viking_fs import _grep as grep_module
from openviking_cli.exceptions import PermissionDeniedError
from openviking_cli.session.user_id import UserIdentifier


class _DummyAgfs:
    pass


@pytest.fixture
def fs(monkeypatch):
    viking_fs = VikingFS(agfs=_DummyAgfs())
    monkeypatch.setattr(viking_fs, "stat", _fake_stat)
    monkeypatch.setattr(
        viking_fs,
        "_uri_to_path",
        lambda uri, ctx=None: uri.replace("viking://", "/"),
    )
    monkeypatch.setattr(
        viking_fs,
        "_path_to_uri",
        lambda path, ctx=None: path.replace("/", "viking://", 1),
    )
    return viking_fs


async def _fake_stat(uri, ctx=None, skip_count=False):
    return {"name": uri.rsplit("/", 1)[-1], "isDir": True}


@pytest.mark.asyncio
async def test_collect_grep_files_skips_directory_vector_count(monkeypatch):
    viking_fs = VikingFS(agfs=_DummyAgfs())
    stat = AsyncMock(return_value={"isDir": True})
    monkeypatch.setattr(viking_fs, "stat", stat)
    monkeypatch.setattr(viking_fs, "ls", AsyncMock(return_value=[]))

    assert await viking_fs._collect_grep_files(
        "viking://resources",
        excluded_prefix=None,
        level_limit=1,
    ) == []
    stat.assert_awaited_once_with("viking://resources", ctx=None, skip_count=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("entry_count", [999, 1000, 1001, 10000])
async def test_collect_grep_files_paginates_wide_directories(monkeypatch, entry_count):
    viking_fs = VikingFS(agfs=_DummyAgfs())
    entries = [
        {"name": f"archive_{index:05d}.jsonl", "isDir": False} for index in range(entry_count)
    ]
    offsets = []

    async def fake_ls(uri, node_limit, offset, ctx=None):
        assert uri == "viking://user/test/sessions/session-1/history"
        offsets.append(offset)
        return entries[offset : offset + node_limit]

    monkeypatch.setattr(viking_fs, "stat", AsyncMock(return_value={"isDir": True}))
    monkeypatch.setattr(viking_fs, "ls", fake_ls)

    files = await viking_fs._collect_grep_files(
        "viking://user/test/sessions/session-1/history",
        excluded_prefix=None,
        level_limit=1,
    )

    assert len(files) == entry_count
    assert files[-1].endswith(f"archive_{entry_count - 1:05d}.jsonl")
    assert offsets == list(range(0, entry_count + 1, grep_module._GREP_LS_PAGE_SIZE))


@pytest.mark.asyncio
async def test_grep_fallback_finds_match_after_first_directory_page(monkeypatch):
    viking_fs = VikingFS(agfs=_DummyAgfs())
    entries = [
        {"name": f"archive_{index:04d}.jsonl", "isDir": False} for index in range(1001)
    ]

    async def fake_ls(uri, node_limit, offset, ctx=None):
        return entries[offset : offset + node_limit]

    async def fake_read(uri, ctx=None):
        return b"needle" if uri.endswith("archive_1000.jsonl") else b"haystack"

    monkeypatch.setattr(viking_fs, "stat", AsyncMock(return_value={"isDir": True}))
    monkeypatch.setattr(viking_fs, "ls", fake_ls)
    monkeypatch.setattr(viking_fs, "read", fake_read)

    result = await viking_fs._grep_encrypted(
        "viking://user/test/sessions/session-1/history",
        pattern="needle",
        level_limit=1,
    )

    assert result["matches"] == [
        {
            "line": 1,
            "uri": (
                "viking://user/test/sessions/session-1/history/archive_1000.jsonl"
            ),
            "content": "needle",
        }
    ]
    assert result["files_scanned"] == 1001


@pytest.mark.asyncio
async def test_collect_grep_files_preserves_dfs_order_across_pages(monkeypatch):
    viking_fs = VikingFS(agfs=_DummyAgfs())
    entries = {
        "viking://resources": [
            {"name": "a.md", "isDir": False},
            {"name": "dir", "isDir": True},
            {"name": "z.md", "isDir": False},
        ],
        "viking://resources/dir": [
            {"name": "nested.md", "isDir": False},
        ],
    }

    async def fake_ls(uri, node_limit, offset, ctx=None):
        return entries.get(uri, [])[offset : offset + node_limit]

    monkeypatch.setattr(grep_module, "_GREP_LS_PAGE_SIZE", 2)
    monkeypatch.setattr(viking_fs, "stat", AsyncMock(return_value={"isDir": True}))
    monkeypatch.setattr(viking_fs, "ls", fake_ls)

    assert await viking_fs._collect_grep_files(
        "viking://resources",
        excluded_prefix=None,
        level_limit=1,
    ) == [
        "viking://resources/a.md",
        "viking://resources/dir/nested.md",
        "viking://resources/z.md",
    ]


@pytest.mark.asyncio
async def test_collect_grep_files_skips_acl_denied_subtrees(monkeypatch):
    viking_fs = VikingFS(agfs=_DummyAgfs())
    listed = []

    async def fake_ls(uri, node_limit, offset, ctx=None):
        listed.append(uri)
        if uri == "viking://resources":
            return [
                {"name": "public.md", "isDir": False},
                {"name": "private", "isDir": True, "access": "denied"},
                {"name": "revoked", "isDir": True},
            ]
        if uri == "viking://resources/revoked":
            raise PermissionDeniedError("access revoked", resource=uri)
        raise AssertionError(f"grep must not enter {uri}")

    monkeypatch.setattr(viking_fs, "stat", AsyncMock(return_value={"isDir": True}))
    monkeypatch.setattr(viking_fs, "ls", fake_ls)

    assert await viking_fs._collect_grep_files(
        "viking://resources",
        excluded_prefix=None,
        level_limit=1,
    ) == ["viking://resources/public.md"]
    assert listed == ["viking://resources", "viking://resources/revoked"]


@pytest.mark.asyncio
async def test_collect_grep_files_propagates_root_acl_denial(monkeypatch):
    viking_fs = VikingFS(agfs=_DummyAgfs())
    monkeypatch.setattr(viking_fs, "stat", AsyncMock(return_value={"isDir": True}))
    monkeypatch.setattr(
        viking_fs,
        "ls",
        AsyncMock(side_effect=PermissionDeniedError("access denied")),
    )

    with pytest.raises(PermissionDeniedError, match="access denied"):
        await viking_fs._collect_grep_files(
            "viking://resources",
            excluded_prefix=None,
            level_limit=1,
        )


@pytest.mark.asyncio
async def test_collect_grep_files_propagates_later_page_failure(monkeypatch):
    viking_fs = VikingFS(agfs=_DummyAgfs())

    async def fake_ls(uri, node_limit, offset, ctx=None):
        if offset:
            raise RuntimeError("page 2 failed")
        return [{"name": f"file_{index:04d}.md", "isDir": False} for index in range(node_limit)]

    monkeypatch.setattr(viking_fs, "stat", AsyncMock(return_value={"isDir": True}))
    monkeypatch.setattr(viking_fs, "ls", fake_ls)

    with pytest.raises(RuntimeError, match="page 2 failed"):
        await viking_fs._collect_grep_files(
            "viking://resources",
            excluded_prefix=None,
            level_limit=1,
        )


@pytest.mark.asyncio
async def test_collect_grep_files_propagates_later_page_acl_denial(monkeypatch):
    viking_fs = VikingFS(agfs=_DummyAgfs())

    async def fake_ls(uri, node_limit, offset, ctx=None):
        if uri == "viking://resources":
            return [{"name": "child", "isDir": True}]
        if offset:
            raise PermissionDeniedError("access revoked", resource=uri)
        return [{"name": f"file_{index:04d}.md", "isDir": False} for index in range(node_limit)]

    monkeypatch.setattr(viking_fs, "stat", AsyncMock(return_value={"isDir": True}))
    monkeypatch.setattr(viking_fs, "ls", fake_ls)

    with pytest.raises(PermissionDeniedError, match="access revoked"):
        await viking_fs._collect_grep_files(
            "viking://resources",
            excluded_prefix=None,
            level_limit=1,
        )


@pytest.mark.asyncio
async def test_collect_grep_files_propagates_root_stat_failure(monkeypatch):
    viking_fs = VikingFS(agfs=_DummyAgfs())
    monkeypatch.setattr(
        viking_fs,
        "stat",
        AsyncMock(side_effect=RuntimeError("root stat failed")),
    )

    with pytest.raises(RuntimeError, match="root stat failed"):
        await viking_fs._collect_grep_files(
            "viking://resources",
            excluded_prefix=None,
            level_limit=1,
        )


@pytest.mark.asyncio
async def test_primary_only_session_grep_uses_native_agfs(monkeypatch):
    viking_fs = VikingFS(agfs=_DummyAgfs())
    native_result = {"matches": [], "count": 0, "match_count": 0, "files_scanned": 4}
    native_grep = AsyncMock(return_value=native_result)
    fallback_grep = AsyncMock()
    monkeypatch.setattr(viking_fs, "_session_native_grep_safe", AsyncMock(return_value=True))
    monkeypatch.setattr(viking_fs, "_grep_with_agfs", native_grep)
    monkeypatch.setattr(viking_fs, "_grep_encrypted", fallback_grep)

    result = await viking_fs._grep_fs(
        uri="viking://user/alice/sessions/session-1",
        pattern="needle",
        exclude_uri="viking://user/alice/sessions/session-1/tools",
        case_insensitive=True,
        node_limit=7,
        level_limit=3,
        ctx=None,
    )

    assert result == native_result
    native_grep.assert_awaited_once_with(
        uri="viking://user/alice/sessions/session-1",
        pattern="needle",
        exclude_uri="viking://user/alice/sessions/session-1/tools",
        case_insensitive=True,
        node_limit=7,
        level_limit=4,
        ctx=None,
        before_context=0,
        after_context=0,
    )
    fallback_grep.assert_not_awaited()


@pytest.mark.asyncio
async def test_session_grep_with_visible_legacy_data_uses_merge_fallback(monkeypatch):
    viking_fs = VikingFS(agfs=_DummyAgfs())
    fallback_result = {"matches": [], "count": 0, "match_count": 0, "files_scanned": 2}
    native_grep = AsyncMock()
    fallback_grep = AsyncMock(return_value=fallback_result)
    monkeypatch.setattr(viking_fs, "_session_native_grep_safe", AsyncMock(return_value=False))
    monkeypatch.setattr(viking_fs, "_grep_with_agfs", native_grep)
    monkeypatch.setattr(viking_fs, "_grep_encrypted", fallback_grep)

    result = await viking_fs._grep_fs(
        uri="viking://user/alice/sessions/session-1",
        pattern="needle",
        exclude_uri=None,
        case_insensitive=False,
        node_limit=None,
        level_limit=10,
        ctx=None,
    )

    assert result == fallback_result
    native_grep.assert_not_awaited()
    fallback_grep.assert_awaited_once()
    assert fallback_grep.await_args.kwargs["level_limit"] == 10


@pytest.mark.asyncio
async def test_session_native_and_legacy_fallback_keep_level_limit_results_equal(monkeypatch):
    viking_fs = VikingFS(agfs=_DummyAgfs())
    match = {
        "uri": "viking://user/alice/sessions/s1/messages.jsonl",
        "line": 1,
        "content": "payment failed",
    }

    async def fake_native_grep(**kwargs):
        matches = [match] if kwargs["level_limit"] >= 2 else []
        return {
            "matches": matches,
            "count": len(matches),
            "match_count": len(matches),
            "files_scanned": len(matches),
        }

    async def fake_fallback_grep(**kwargs):
        matches = [match] if kwargs["level_limit"] >= 1 else []
        return {
            "matches": matches,
            "count": len(matches),
            "match_count": len(matches),
            "files_scanned": len(matches),
        }

    monkeypatch.setattr(viking_fs, "_grep_with_agfs", fake_native_grep)
    monkeypatch.setattr(viking_fs, "_grep_encrypted", fake_fallback_grep)
    native_safe = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(viking_fs, "_session_native_grep_safe", native_safe)
    kwargs = {
        "uri": "viking://user/alice/sessions",
        "pattern": "payment failed",
        "exclude_uri": None,
        "case_insensitive": False,
        "node_limit": None,
        "level_limit": 1,
        "ctx": None,
    }

    assert await viking_fs._grep_fs(**kwargs) == await viking_fs._grep_fs(**kwargs)


@pytest.mark.asyncio
async def test_virtual_empty_session_root_uses_merge_fallback(monkeypatch):
    viking_fs = VikingFS(agfs=_DummyAgfs())
    primary_path = "/local/default/user/alice/sessions"
    path_exists = AsyncMock(return_value=False)
    legacy_items = AsyncMock(return_value=[])
    monkeypatch.setattr(viking_fs, "_agfs_path_exists", path_exists)
    monkeypatch.setattr(viking_fs, "_legacy_session_root_items", legacy_items)

    assert not await viking_fs._session_native_grep_safe(
        "viking://user/alice/sessions", None
    )
    path_exists.assert_awaited_once_with(primary_path)
    legacy_items.assert_not_awaited()


@pytest.mark.asyncio
async def test_grep_preserves_dfs_order_and_node_limit(monkeypatch):
    fs = VikingFS(agfs=_DummyAgfs())

    async def fake_stat(uri, ctx=None, skip_count=False):
        return {"isDir": True}

    async def fake_ls(uri, ctx=None, **kwargs):
        entries = {
            "viking://resources": [
                {"name": "dir_a", "isDir": True},
                {"name": "dir_b", "isDir": True},
            ],
            "viking://resources/dir_a": [
                {"name": "a1.md", "isDir": False},
                {"name": "a2.md", "isDir": False},
            ],
            "viking://resources/dir_b": [
                {"name": "b1.md", "isDir": False},
            ],
        }
        return entries.get(uri, [])

    def fake_agfs_read(path, offset=0, size=-1):
        contents = {
            "/resources/dir_a/a1.md": "match a1 line1\nskip\nmatch a1 line3",
            "/resources/dir_a/a2.md": "match a2 line1",
            "/resources/dir_b/b1.md": "match b1 line1",
        }
        return contents[path].encode()

    monkeypatch.setattr(fs, "stat", fake_stat)
    monkeypatch.setattr(fs, "ls", fake_ls)
    monkeypatch.setattr(
        fs,
        "_uri_to_path",
        lambda uri, ctx=None: uri.replace("viking://", "/"),
    )
    monkeypatch.setattr(fs.agfs, "read", fake_agfs_read, raising=False)

    result = await fs.grep("viking://resources", pattern="match", node_limit=3)

    assert result["count"] == 3
    assert result["files_scanned"] == 2
    assert result["matches"] == [
        {
            "line": 1,
            "uri": "viking://resources/dir_a/a1.md",
            "content": "match a1 line1",
        },
        {
            "line": 3,
            "uri": "viking://resources/dir_a/a1.md",
            "content": "match a1 line3",
        },
        {
            "line": 1,
            "uri": "viking://resources/dir_a/a2.md",
            "content": "match a2 line1",
        },
    ]


@pytest.mark.asyncio
async def test_grep_allowed_uris_filters_before_node_limit(monkeypatch):
    fs = VikingFS(agfs=_DummyAgfs())

    async def fake_stat(uri, ctx=None, skip_count=False):
        return {"isDir": True}

    async def fake_ls(uri, ctx=None, **kwargs):
        return [
            {"name": "untagged.md", "isDir": False},
            {"name": "tagged.md", "isDir": False},
        ]

    def fake_agfs_read(path, offset=0, size=-1):
        return b"match"

    monkeypatch.setattr(fs, "stat", fake_stat)
    monkeypatch.setattr(fs, "ls", fake_ls)
    monkeypatch.setattr(
        fs,
        "_uri_to_path",
        lambda uri, ctx=None: uri.replace("viking://", "/"),
    )
    monkeypatch.setattr(fs.agfs, "read", fake_agfs_read, raising=False)

    result = await fs.grep(
        "viking://resources",
        pattern="match",
        node_limit=1,
        allowed_uris={"viking://resources/tagged.md"},
    )

    assert result["matches"] == [
        {"line": 1, "uri": "viking://resources/tagged.md", "content": "match"}
    ]
    assert result["files_scanned"] == 1


@pytest.mark.asyncio
async def test_grep_applies_content_transform_before_matching(monkeypatch):
    fs = VikingFS(agfs=_DummyAgfs())

    async def fake_stat(uri, ctx=None, skip_count=False):
        return {"isDir": True}

    async def fake_ls(uri, ctx=None, **kwargs):
        if uri == "viking://resources":
            return [{"name": "memory.md", "isDir": False}]
        return []

    read_paths = []

    def fake_agfs_read(path, offset=0, size=-1):
        read_paths.append(path)
        return b'before\nvisible\nafter\n<!-- MEMORY_FIELDS {"secret":"hidden"} -->'

    monkeypatch.setattr(fs, "stat", fake_stat)
    monkeypatch.setattr(fs, "ls", fake_ls)
    monkeypatch.setattr(
        fs,
        "_uri_to_path",
        lambda uri, ctx=None: uri.replace("viking://", "/"),
    )
    monkeypatch.setattr(fs.agfs, "read", fake_agfs_read, raising=False)

    result = await fs.grep(
        "viking://resources",
        pattern="visible|secret",
        content_transform=lambda content, _uri: content.split("<!--", 1)[0].rstrip(),
        before_context=2,
        after_context=2,
    )

    assert result["matches"] == [
        {
            "line": 2,
            "uri": "viking://resources/memory.md",
            "content": "visible",
            "before_context": [{"line": 1, "content": "before"}],
            "after_context": [{"line": 3, "content": "after"}],
        }
    ]
    assert read_paths == ["/resources/memory.md"]


@pytest.mark.asyncio
async def test_grep_parallel_limits_context_construction_per_file(monkeypatch):
    fs = VikingFS(agfs=_DummyAgfs())
    lines = ["hit"] * 400
    monkeypatch.setattr(fs, "read", AsyncMock(return_value="\n".join(lines)))

    build_calls = 0
    original_build_match = fs._build_grep_match

    def count_build_calls(*args, **kwargs):
        nonlocal build_calls
        build_calls += 1
        return original_build_match(*args, **kwargs)

    monkeypatch.setattr(fs, "_build_grep_match", count_build_calls)

    matches, files_scanned = await fs._grep_files_parallel(
        ["viking://resources/a.md"],
        compiled_pattern=re.compile("hit"),
        node_limit=1,
        before_context=400,
        after_context=400,
    )

    assert files_scanned == 1
    assert len(matches) == 1
    assert build_calls == 1
    assert matches[0]["before_context"] == []
    assert len(matches[0]["after_context"]) == 399


@pytest.mark.asyncio
async def test_grep_parallel_reads_respect_concurrency_limit(monkeypatch):
    fs = VikingFS(agfs=_DummyAgfs())

    async def fake_stat(uri, ctx=None, skip_count=False):
        return {"isDir": True}

    async def fake_ls(uri, ctx=None, **kwargs):
        entries = {
            "viking://resources": [{"name": f"file{i}.md", "isDir": False} for i in range(12)]
        }
        return entries.get(uri, [])

    active_reads = 0
    max_active_reads = 0

    def fake_agfs_read(path, offset=0, size=-1):
        nonlocal active_reads, max_active_reads
        active_reads += 1
        max_active_reads = max(max_active_reads, active_reads)
        time.sleep(0.01)
        active_reads -= 1
        return f"match from {path}".encode()

    monkeypatch.setattr(fs, "stat", fake_stat)
    monkeypatch.setattr(fs, "ls", fake_ls)
    monkeypatch.setattr(
        fs,
        "_uri_to_path",
        lambda uri, ctx=None: uri.replace("viking://", "/"),
    )
    monkeypatch.setattr(fs.agfs, "read", fake_agfs_read, raising=False)

    result = await fs.grep("viking://resources", pattern="match")

    assert result["count"] == 12
    assert result["files_scanned"] == 12
    assert max_active_reads > 1
    assert max_active_reads <= min(12, _DEFAULT_GREP_FILE_CONCURRENCY)


@pytest.mark.asyncio
async def test_grep_parallel_reads_work_with_blocking_agfs_read(monkeypatch):
    fs = VikingFS(agfs=_DummyAgfs())

    async def fake_stat(uri, ctx=None, skip_count=False):
        return {"isDir": True}

    async def fake_ls(uri, ctx=None, **kwargs):
        if uri == "viking://resources":
            return [{"name": f"file{i}.md", "isDir": False} for i in range(8)]
        return []

    def fake_agfs_read(path, offset=0, size=-1):
        time.sleep(0.05)
        return f"match from {path}".encode()

    monkeypatch.setattr(fs, "stat", fake_stat)
    monkeypatch.setattr(fs, "ls", fake_ls)
    monkeypatch.setattr(
        fs,
        "_uri_to_path",
        lambda uri, ctx=None: uri.replace("viking://", "/"),
    )
    monkeypatch.setattr(fs.agfs, "read", fake_agfs_read, raising=False)

    started = time.perf_counter()
    result = await fs.grep("viking://resources", pattern="match")
    elapsed = time.perf_counter() - started

    assert result["count"] == 8
    assert result["files_scanned"] == 8
    assert elapsed < 0.30


@pytest.mark.asyncio
async def test_grep_stops_scheduling_later_batches_after_node_limit(monkeypatch):
    fs = VikingFS(agfs=_DummyAgfs())

    async def fake_stat(uri, ctx=None, skip_count=False):
        return {"isDir": True}

    async def fake_ls(uri, ctx=None, **kwargs):
        if uri == "viking://resources":
            return [{"name": f"file{i}.md", "isDir": False} for i in range(6)]
        return []

    read_paths = []

    def fake_agfs_read(path, offset=0, size=-1):
        read_paths.append(path)
        contents = {
            "/resources/file0.md": "match file0 line1\nmatch file0 line2",
            "/resources/file1.md": "match file1 line1",
            "/resources/file2.md": "match file2 line1",
            "/resources/file3.md": "match file3 line1",
            "/resources/file4.md": "match file4 line1",
            "/resources/file5.md": "match file5 line1",
        }
        return contents[path].encode()

    monkeypatch.setattr(fs, "stat", fake_stat)
    monkeypatch.setattr(fs, "ls", fake_ls)
    monkeypatch.setattr(
        fs,
        "_uri_to_path",
        lambda uri, ctx=None: uri.replace("viking://", "/"),
    )
    monkeypatch.setattr(fs.agfs, "read", fake_agfs_read, raising=False)
    monkeypatch.setattr(viking_fs_module, "_DEFAULT_GREP_FILE_CONCURRENCY", 2)

    result = await fs.grep("viking://resources", pattern="match", node_limit=2)

    assert result["count"] == 2
    assert result["files_scanned"] == 1
    assert read_paths == ["/resources/file0.md", "/resources/file1.md"]


@pytest.mark.asyncio
async def test_grep_delegates_to_agfs_with_expected_filters(monkeypatch, fs):
    calls = []

    async def fake_grep(**kwargs):
        calls.append(kwargs)
        return {"matches": [], "files_scanned": 0}

    monkeypatch.setattr(fs._async_agfs, "grep", fake_grep)

    result = await fs.grep(
        "viking://resources",
        pattern="needle",
        exclude_uri="viking://resources/archive",
        case_insensitive=True,
        node_limit=10,
        level_limit=3,
    )

    assert result == {"matches": [], "count": 0, "match_count": 0, "files_scanned": 0}
    assert calls == [
        {
            "path": "/resources",
            "pattern": "needle",
            "recursive": True,
            "case_insensitive": True,
            "stream": False,
            "node_limit": 10,
            "exclude_path": "/resources/archive",
            "level_limit": 3,
            "before_context": 0,
            "after_context": 0,
        }
    ]


@pytest.mark.asyncio
async def test_grep_with_context_uses_agfs_and_maps_context(monkeypatch, fs):
    agfs_grep = AsyncMock(
        return_value={
            "matches": [
                {
                    "file": "a.md",
                    "line": 2,
                    "content": "needle",
                    "before_context": [{"line": 1, "content": "before"}],
                    "after_context": [{"line": 3, "content": "after"}],
                }
            ],
            "files_scanned": 1,
        }
    )
    fallback = AsyncMock()
    monkeypatch.setattr(fs._async_agfs, "grep", agfs_grep)
    monkeypatch.setattr(fs, "_grep_encrypted", fallback)

    result = await fs.grep(
        "viking://resources",
        pattern="needle",
        before_context=1,
        after_context=2,
    )

    agfs_grep.assert_awaited_once_with(
        path="/resources",
        pattern="needle",
        recursive=True,
        case_insensitive=False,
        stream=False,
        node_limit=None,
        exclude_path=None,
        level_limit=10,
        before_context=1,
        after_context=2,
    )
    fallback.assert_not_awaited()
    assert result["matches"] == [
        {
            "line": 2,
            "uri": "viking://resources/a.md",
            "content": "needle",
            "before_context": [{"line": 1, "content": "before"}],
            "after_context": [{"line": 3, "content": "after"}],
        }
    ]


@pytest.mark.asyncio
async def test_grep_maps_agfs_matches_to_viking_uris(monkeypatch, fs):
    async def fake_grep(**kwargs):
        return {
            "matches": [
                {"file": "dir/a.md", "line": 2, "content": "first match"},
                {"file": "/dir/b.md", "line_number": 5, "content": "second match"},
            ],
            "files_scanned": 7,
        }

    monkeypatch.setattr(fs._async_agfs, "grep", fake_grep)

    result = await fs.grep("viking://resources", pattern="match")

    assert result == {
        "matches": [
            {
                "line": 2,
                "uri": "viking://resources/dir/a.md",
                "content": "first match",
            },
            {
                "line": 5,
                "uri": "viking://resources/dir/b.md",
                "content": "second match",
            },
        ],
        "count": 2,
        "match_count": 2,
        "files_scanned": 7,
    }


@pytest.mark.asyncio
async def test_grep_applies_node_limit_to_backend_results(monkeypatch, fs):
    async def fake_grep(**kwargs):
        return {
            "matches": [
                {"file": "a.md", "line": 1, "content": "a"},
                {"file": "b.md", "line": 1, "content": "b"},
                {"file": "c.md", "line": 1, "content": "c"},
            ]
        }

    monkeypatch.setattr(fs._async_agfs, "grep", fake_grep)

    result = await fs.grep("viking://resources", pattern="match", node_limit=2)

    assert result["count"] == 2
    assert result["match_count"] == 2
    assert result["files_scanned"] == 2
    assert [match["uri"] for match in result["matches"]] == [
        "viking://resources/a.md",
        "viking://resources/b.md",
    ]


class _RestrictedAclManager:
    """ACL manager stub: enabled, with per-URI effective ACLs from `resolve_many`."""

    def __init__(self, effective_by_uri):
        self.effective_by_uri = effective_by_uri

    async def is_enabled(self, account_id):
        return True

    async def resolve_many(self, uris, ctx):
        return {uri: self.effective_by_uri[uri] for uri in uris}


def _acl_grep_fs(monkeypatch, effective_by_uri):
    """VikingFS with a native-grep stub returning one restricted resource match."""
    viking_fs = VikingFS(agfs=_DummyAgfs())

    async def fake_grep(**kwargs):
        return {
            "matches": [
                {"file": "secret.md", "line": 1, "content": "SECRET_MARKER_4977"},
            ],
            "count": 1,
        }

    monkeypatch.setattr(viking_fs._async_agfs, "grep", fake_grep)
    viking_fs.acl_manager = _RestrictedAclManager(effective_by_uri)
    return viking_fs


def _restricted_acl() -> EffectiveAcl:
    """RESTRICTED inheritance with no grants — denies every non-bypassing principal."""
    return EffectiveAcl(AclMode.RESTRICTED, DirectAcl(), DirectAcl())


@pytest.mark.asyncio
async def test_grep_with_agfs_denies_acl_restricted_content_without_grant(monkeypatch):
    """Native grep must not leak restricted-inheritance content to a user with no grant."""
    viking_fs = _acl_grep_fs(
        monkeypatch,
        {"viking://resources/secret.md": _restricted_acl()},
    )
    ctx = RequestContext(user=UserIdentifier("acct1", "mallory"), role=Role.USER)

    result = await viking_fs._grep_with_agfs(
        "viking://resources", pattern="SECRET_MARKER_4977", ctx=ctx
    )

    assert result["matches"] == []
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_grep_with_agfs_allows_acl_granted_content(monkeypatch):
    """Authorized principals keep receiving restricted-inheritance content through grep."""
    granted = EffectiveAcl(
        AclMode.RESTRICTED,
        DirectAcl.from_entries([AclEntry("user:mallory", AclLevel.READ)]),
        DirectAcl(),
    )
    viking_fs = _acl_grep_fs(
        monkeypatch,
        {"viking://resources/secret.md": granted},
    )
    ctx = RequestContext(user=UserIdentifier("acct1", "mallory"), role=Role.USER)

    result = await viking_fs._grep_with_agfs(
        "viking://resources", pattern="SECRET_MARKER_4977", ctx=ctx
    )

    assert [m["uri"] for m in result["matches"]] == ["viking://resources/secret.md"]
    assert result["count"] == 1
