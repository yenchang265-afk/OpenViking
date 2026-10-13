"""Compile outcomes when the agent writes nothing."""

import pytest
from vikingbot.compile.service import (
    _EMPTY_OUTPUT_MESSAGE,
    _pipeline_incomplete_error,
    _target_has_pages,
)

from openviking_cli.exceptions import OpenVikingError


class _GlobClient:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error

    async def glob(self, pattern, uri):
        if self._error is not None:
            raise self._error
        return self._result


async def test_target_with_markdown_pages_has_pages():
    client = _GlobClient({"matches": ["viking://resources/wiki/index.md"]})
    assert await _target_has_pages(client, "viking://resources/wiki") is True


async def test_empty_target_has_no_pages():
    assert await _target_has_pages(_GlobClient({"matches": []}), "viking://resources/wiki") is False


async def test_missing_target_has_no_pages():
    client = _GlobClient(error=OpenVikingError("missing", code="NOT_FOUND"))
    assert await _target_has_pages(client, "viking://resources/wiki") is False


async def test_unreadable_target_raises_the_underlying_error():
    # The task runner reports a raw OpenVikingError under its own code.
    client = _GlobClient(error=OpenVikingError("denied", code="PERMISSION_DENIED"))
    with pytest.raises(OpenVikingError) as raised:
        await _target_has_pages(client, "viking://resources/wiki")
    assert raised.value.code == "PERMISSION_DENIED"


def test_published_pipeline_output_is_not_an_error():
    assert _pipeline_incomplete_error(published=True, conflicts=[], failures=[]) is None


def test_empty_pipeline_output_suggests_a_more_capable_model():
    error = _pipeline_incomplete_error(published=False, conflicts=[], failures=[])
    assert error.code == "COMPILE_INCOMPLETE"
    assert error.message == _EMPTY_OUTPUT_MESSAGE


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
    error = _pipeline_incomplete_error(published=False, conflicts=conflicts, failures=failures)
    assert error.code == "COMPILE_INCOMPLETE"
    assert error.message == "No output was acknowledged."
