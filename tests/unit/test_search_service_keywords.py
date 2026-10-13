from types import SimpleNamespace

import pytest

from openviking.server.identity import RequestContext, Role
from openviking.service.search_service import SearchService
from openviking_cli.exceptions import InvalidArgumentError
from openviking_cli.session.user_id import UserIdentifier


def _ctx():
    return RequestContext(user=UserIdentifier("account", "user"), role=Role.USER)


@pytest.mark.asyncio
async def test_keywords_search_is_rejected_without_a_fulltext_backend():
    # Only the VikingDB/Volcengine backends index content for full-text search,
    # and this build ships neither, so the check never consults the vector store.
    def no_vector_store_access():
        raise AssertionError("keyword support must not depend on the vector store")

    fs = SimpleNamespace(_get_vector_store=no_vector_store_access)

    with pytest.raises(InvalidArgumentError, match="Keyword search is not supported"):
        await SearchService(fs).ensure_keywords_search_supported(_ctx())
