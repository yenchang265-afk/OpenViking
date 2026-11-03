from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from openviking.server.identity import RequestContext, Role
from openviking.service.search_service import SearchService
from openviking_cli.exceptions import InvalidArgumentError
from openviking_cli.session.user_id import UserIdentifier


def _ctx():
    return RequestContext(user=UserIdentifier("account", "user"), role=Role.USER)


def _fs_with_backend_mode(mode):
    requested = []

    async def get_account_backend(account_id):
        requested.append(account_id)
        return SimpleNamespace(_mode=mode)

    vector_store = SimpleNamespace(get_account_backend=get_account_backend)
    return SimpleNamespace(_get_vector_store=lambda: vector_store), requested


@pytest.mark.asyncio
async def test_keywords_search_is_allowed_on_an_elasticsearch_backend():
    # Elasticsearch indexes the content field and scores keyword queries with BM25.
    fs, requested = _fs_with_backend_mode("elasticsearch")

    await SearchService(fs).ensure_keywords_search_supported(_ctx())

    assert requested == ["account"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["local", "http", "cuvs"])
async def test_keywords_search_is_rejected_without_a_fulltext_backend(mode):
    fs, _ = _fs_with_backend_mode(mode)

    with pytest.raises(InvalidArgumentError, match="Keyword search is not supported"):
        await SearchService(fs).ensure_keywords_search_supported(_ctx())


@pytest.mark.asyncio
async def test_keywords_search_is_rejected_without_a_vector_store():
    fs = SimpleNamespace(_get_vector_store=lambda: None)

    with pytest.raises(InvalidArgumentError, match="Keyword search is not supported"):
        await SearchService(fs).ensure_keywords_search_supported(_ctx())


@pytest.mark.asyncio
@pytest.mark.parametrize("has_fulltext", [True, False])
async def test_keywords_search_on_opengauss_follows_the_fulltext_probe(has_fulltext):
    fs, _ = _fs_with_backend_mode("opengauss")
    check = AsyncMock(return_value=has_fulltext)
    fs._collection_has_fulltext = check
    service = SearchService(fs)

    if has_fulltext:
        await service.ensure_keywords_search_supported(_ctx())
    else:
        with pytest.raises(InvalidArgumentError, match="Keyword search is not supported"):
            await service.ensure_keywords_search_supported(_ctx())

    check.assert_awaited_once_with(
        fs._get_vector_store(),
        _ctx(),
        supported_modes=("opengauss",),
        raise_on_error=True,
    )


@pytest.mark.asyncio
async def test_keywords_capability_check_propagates_metadata_failures():
    fs, _ = _fs_with_backend_mode("opengauss")
    fs._collection_has_fulltext = AsyncMock(side_effect=RuntimeError("metadata unavailable"))

    with pytest.raises(RuntimeError, match="metadata unavailable"):
        await SearchService(fs).ensure_keywords_search_supported(_ctx())
