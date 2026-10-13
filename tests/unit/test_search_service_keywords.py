from types import SimpleNamespace

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
