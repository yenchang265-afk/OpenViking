# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0

import pytest

from openviking.session.memory.dataclass import MemoryFile
from openviking.session.memory.utils.resource_refs import (
    contains_resource_uri,
    content_references_resource,
    extract_resource_uris,
    sync_memory_resource_refs,
    unlink_resource_references_from_memory,
)


@pytest.mark.parametrize(
    ("name", "encoded"),
    [("a#one.md", "a%23one.md"), ("a%23one.md", "a%2523one.md")],
)
@pytest.mark.parametrize("bare", [False, True])
def test_resource_refs_preserve_literal_filenames(name, encoded, bare):
    root = "viking://resources/source/"
    uri = root + name
    content = f"Source {uri}" if bare else f"[Source]({root}{encoded}#intro)"
    mf = MemoryFile(content=content, extra_fields={})

    assert extract_resource_uris(content) == [uri]
    assert sync_memory_resource_refs(mf, source="compile")
    assert mf.extra_fields["resource_refs"][0]["resource_uri"] == uri
    assert f"]({root}{encoded}" in mf.content
    assert not sync_memory_resource_refs(mf, source="compile")
    assert extract_resource_uris(mf.content) == [uri]
    assert content_references_resource(mf.content, uri)
    for other in {"a#one.md", "a%23one.md", "a#two.md", "a"} - {name}:
        assert not content_references_resource(mf.content, root + other)
        assert not unlink_resource_references_from_memory(mf, root + other)
    assert unlink_resource_references_from_memory(mf, uri)
    assert mf.content == "Source"
    assert "resource_refs" not in mf.extra_fields


def test_extract_resource_uris_stops_at_common_sentence_delimiters():
    cases = [
        (
            "看了 viking://resources/images/foo.jpeg，覺得不錯",
            "viking://resources/images/foo.jpeg",
        ),
        (
            "看了 viking://resources/images/foo.jpeg。還看了別的",
            "viking://resources/images/foo.jpeg",
        ),
        (
            "看了 viking://resources/images/foo.jpeg；然後記錄",
            "viking://resources/images/foo.jpeg",
        ),
        (
            "看了 viking://resources/images/foo.jpeg！真的好",
            "viking://resources/images/foo.jpeg",
        ),
        (
            "看了 viking://resources/images/foo.jpeg？真的好",
            "viking://resources/images/foo.jpeg",
        ),
        (
            "看了 viking://resources/images/foo.jpeg、還有別的",
            "viking://resources/images/foo.jpeg",
        ),
        (
            "看了 viking://resources/images/foo.jpeg）然後記錄",
            "viking://resources/images/foo.jpeg",
        ),
        (
            "read viking://resources/images/foo.jpeg, then commented",
            "viking://resources/images/foo.jpeg",
        ),
    ]

    for content, expected in cases:
        assert extract_resource_uris(content) == [expected]


def test_extract_resource_uris_does_not_match_resource_prefix_words():
    cases = [
        "viking://resources2/images/foo",
        "viking://resources-old/images/foo",
        "viking://user/alice/resources2/images/foo",
        "viking://user/alice/resources-old/images/foo",
        "viking://user/alice/peers/bob/resources2/images/foo",
        "viking://user/alice/peers/bob/resources-old/images/foo",
    ]

    for content in cases:
        assert not contains_resource_uri(content)
        assert extract_resource_uris(content) == []


def test_sync_memory_resource_refs_keeps_bare_uri_clean_before_chinese_punctuation():
    resource_uri = "viking://resources/images/2026/06/12/yueqian_jpeg"
    mf = MemoryFile(
        content=(
            f"昨天晚上我看了 {resource_uri}，這張圖是越前龍馬的照片。"
            "以後提到越前龍馬照片，可以參考這個資源。"
        ),
        extra_fields={},
    )

    changed = sync_memory_resource_refs(mf, source="session.commit")

    assert changed is True
    assert f"]({resource_uri})，這張圖是越前龍馬的照片。" in mf.content
    refs = mf.extra_fields["resource_refs"]
    assert refs == [
        {
            "resource_uri": resource_uri,
            "source": "session.commit",
            "created_at": refs[0]["created_at"],
            "match_text": "昨天晚上我看了",
        }
    ]


def test_unlink_resource_references_preserves_visible_markdown_text():
    resource_uri = "viking://resources/images/2026/06/12/yueqian_jpeg"
    child_uri = f"{resource_uri}/child.jpeg"
    mf = MemoryFile(
        content=(f"使用者儲存了[越前龍馬照片]({resource_uri})。\n使用者也儲存了[子圖]({child_uri})。"),
        extra_fields={
            "resource_refs": [
                {"resource_uri": resource_uri, "source": "content.write"},
                {"resource_uri": child_uri, "source": "content.write"},
            ]
        },
    )

    changed = unlink_resource_references_from_memory(mf, resource_uri, recursive=False)

    assert changed is True
    assert mf.content == f"使用者儲存了越前龍馬照片。\n使用者也儲存了[子圖]({child_uri})。"
    assert mf.extra_fields["resource_refs"] == [
        {"resource_uri": child_uri, "source": "content.write"}
    ]


def test_unlink_resource_references_removes_bare_uri_but_keeps_sentence():
    resource_uri = "viking://resources/images/2026/06/12/yueqian_jpeg"
    mf = MemoryFile(
        content=f"使用者儲存了越前龍馬照片 {resource_uri}。",
        extra_fields={"resource_refs": [{"resource_uri": resource_uri}]},
    )

    changed = unlink_resource_references_from_memory(mf, resource_uri)

    assert changed is True
    assert mf.content == "使用者儲存了越前龍馬照片。"
    assert "resource_refs" not in mf.extra_fields
