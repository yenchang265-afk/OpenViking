"""Compile outcomes when the agent writes nothing."""

from datetime import datetime, timezone

import pytest

from openviking.compile.runner import (
    EMPTY_OUTPUT_MESSAGE,
    list_source_files,
    pipeline_incomplete_error,
)


class _TreeClient:
    """Two-level source tree with per-file modification times."""

    tree = {
        "viking://resources/raw": [
            {
                "uri": "viking://resources/raw/old.md",
                "isDir": False,
                "modTime": "2026-01-01T00:00:00Z",
            },
            {"uri": "viking://resources/raw/sub", "isDir": True},
        ],
        "viking://resources/raw/sub": [
            {
                "uri": "viking://resources/raw/sub/new.md",
                "isDir": False,
                "modTime": "2026-06-01T00:00:00Z",
            },
        ],
    }

    async def stat(self, uri):
        return {"isDir": uri in self.tree}

    async def list_resources(self, uri, node_limit, offset=0):
        return self.tree[uri][offset : offset + node_limit]


async def test_list_source_files_walks_tree_and_applies_cutoff():
    client = _TreeClient()
    assert await list_source_files(client, ["viking://resources/raw"]) == [
        "viking://resources/raw/old.md",
        "viking://resources/raw/sub/new.md",
    ]
    cutoff = datetime(2026, 3, 1, tzinfo=timezone.utc)
    assert await list_source_files(client, ["viking://resources/raw"], cutoff=cutoff) == [
        "viking://resources/raw/sub/new.md"
    ]


async def test_list_source_files_rejects_empty_sources_without_cutoff():
    client = _TreeClient()
    client.tree = {"viking://resources/empty": []}
    with pytest.raises(ValueError, match="no files"):
        await list_source_files(client, ["viking://resources/empty"])


def test_published_pipeline_output_is_not_an_error():
    assert pipeline_incomplete_error(published=True, conflicts=[], failures=[]) is None


def test_empty_pipeline_output_suggests_a_more_capable_model():
    error = pipeline_incomplete_error(published=False, conflicts=[], failures=[])
    assert error.code == "COMPILE_INCOMPLETE"
    assert error.message == EMPTY_OUTPUT_MESSAGE


@pytest.mark.parametrize(
    ("conflicts", "failures"),
    [
        ([{"uri": "viking://resources/wiki/a.md", "message": "changed"}], []),
        ([], ["Source read failed: viking://resources/raw/a.md: timeout"]),
    ],
)
def test_pipeline_output_lost_to_conflicts_or_failures_keeps_the_generic_message(
    conflicts, failures
):
    error = pipeline_incomplete_error(published=False, conflicts=conflicts, failures=failures)
    assert error.code == "COMPILE_INCOMPLETE"
    assert error.message == "No output was acknowledged."
