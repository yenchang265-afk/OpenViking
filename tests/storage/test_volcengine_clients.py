import pytest
import requests
from volcengine.base.Request import Request

from openviking.storage.vectordb.collection.volcengine_clients import ClientForDataApi
from openviking.storage.vectordb_adapters.base import VIKINGDB_STRING_FIELD_BYTE_LIMIT
from openviking.storage.vectordb_adapters.local_adapter import LocalCollectionAdapter


def test_data_client_do_req_uses_signed_query_params(monkeypatch):
    captured = {}

    def fake_request(**kwargs):
        captured.update(kwargs)
        return object()

    def fake_prepare_request(self, method, path, params=None, data=None):
        request = Request()
        request.method = method
        request.path = path
        request.body = '{"project": "default"}'
        request.headers = {"Authorization": "signed-auth"}
        request.query = {
            "Action": "Search",
            "Version": "2025-06-09",
            "X-Date": "20260405T091640Z",
            "X-Signature": "signed",
        }
        return request

    monkeypatch.setattr(ClientForDataApi, "prepare_request", fake_prepare_request)

    client = ClientForDataApi("test-ak", "test-sk", "cn-beijing")
    monkeypatch.setattr(client._session, "request", fake_request)
    client.do_req(
        "POST",
        "/api/vikingdb/data/search/vector",
        req_params={"Action": "Search", "Version": "2025-06-09"},
        req_body={"project": "default"},
    )

    assert captured["params"]["X-Date"] == "20260405T091640Z"
    assert captured["params"]["X-Signature"] == "signed"


def test_clients_keep_pooled_session_reused_across_calls(monkeypatch):
    """Each client owns one keep-alive session that serves every request."""
    from requests.adapters import HTTPAdapter

    client = ClientForDataApi("test-ak", "test-sk", "cn-beijing")
    adapter = client._session.get_adapter("https://example.com")
    assert isinstance(adapter, HTTPAdapter)
    # HTTP and HTTPS share the same pooled adapter instance.
    assert client._session.get_adapter("http://example.com") is adapter

    seen_sessions = []

    def fake_prepare_request(self, *args, **kwargs):
        request = Request()
        request.method = "POST"
        request.path = "/api/vikingdb/data/search/vector"
        request.body = "{}"
        request.headers = {}
        request.query = {}
        return request

    def fake_request(self, **kwargs):
        seen_sessions.append(self)
        return object()

    monkeypatch.setattr(ClientForDataApi, "prepare_request", fake_prepare_request)
    monkeypatch.setattr(requests.Session, "request", fake_request)

    client = ClientForDataApi("test-ak", "test-sk", "cn-beijing")
    client.do_req("POST", "/api/vikingdb/data/search/vector")
    client.do_req("POST", "/api/vikingdb/data/search/vector")

    assert len(seen_sessions) == 2
    assert seen_sessions[0] is seen_sessions[1] is client._session


def test_local_adapter_does_not_apply_remote_abstract_limit():
    adapter = LocalCollectionAdapter(
        collection_name="context", project_path="", index_name="default"
    )
    abstract = "😀" * VIKINGDB_STRING_FIELD_BYTE_LIMIT

    normalized = adapter._normalize_record_for_write({"abstract": abstract})

    assert normalized["abstract"] == abstract


def test_adapter_truncates_abstract_at_configured_string_limit():
    class _LimitedAdapter(LocalCollectionAdapter):
        _STRING_FIELD_BYTE_LIMIT = VIKINGDB_STRING_FIELD_BYTE_LIMIT

    adapter = _LimitedAdapter(collection_name="context", project_path="", index_name="default")
    abstract = "a" * (VIKINGDB_STRING_FIELD_BYTE_LIMIT - 3) + "你好"

    stored = adapter._normalize_record_for_write({"abstract": abstract})["abstract"]

    assert len(stored.encode("utf-8")) <= VIKINGDB_STRING_FIELD_BYTE_LIMIT
    assert abstract.startswith(stored)
    assert stored.endswith("你")


def test_http_collection_update_data_posts_to_update_endpoint(monkeypatch):
    captured = {}

    class _Response:
        status_code = 200
        text = '{"data": ["doc-1"]}'

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(
        "openviking.storage.vectordb.collection.http_collection.requests.post",
        _fake_post,
    )

    from openviking.storage.vectordb.collection.http_collection import HttpCollection

    collection = HttpCollection(
        ip="127.0.0.1",
        port=1933,
        meta_data={"ProjectName": "default", "CollectionName": "context"},
    )

    result = collection.update_data([{"id": "doc-1", "name": "updated"}])

    assert result == ["doc-1"]
    assert captured["url"] == "http://127.0.0.1:1933/api/vikingdb/data/update"
    assert captured["json"] == {
        "project": "default",
        "collection_name": "context",
        "fields": '[{"id": "doc-1", "name": "updated"}]',
    }


def test_http_adapter_strict_count_propagates_http_failure(monkeypatch):
    from openviking.storage.vectordb.collection.collection import Collection
    from openviking.storage.vectordb.collection.http_collection import HttpCollection
    from openviking.storage.vectordb_adapters.http_adapter import HttpCollectionAdapter

    class _Response:
        status_code = 503
        text = "unavailable"

        @staticmethod
        def raise_for_status():
            raise requests.HTTPError("503 unavailable")

    monkeypatch.setattr(
        "openviking.storage.vectordb.collection.http_collection.requests.post",
        lambda *args, **kwargs: _Response(),
    )
    adapter = HttpCollectionAdapter(
        host="127.0.0.1",
        port=1933,
        project_name="default",
        collection_name="context",
        index_name="default",
    )
    adapter._collection = Collection(
        HttpCollection(
            ip="127.0.0.1",
            port=1933,
            meta_data={"ProjectName": "default", "CollectionName": "context"},
        )
    )

    with pytest.raises(requests.HTTPError, match="503 unavailable"):
        adapter.strict_count()


def test_http_collection_update_index_preserves_explicit_empty_scalar_index(monkeypatch):
    captured = {}

    class _Response:
        status_code = 200
        text = '{"data": {}}'

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _Response()

    monkeypatch.setattr(
        "openviking.storage.vectordb.collection.http_collection.requests.post",
        _fake_post,
    )

    from openviking.storage.vectordb.collection.http_collection import HttpCollection

    collection = HttpCollection(
        ip="127.0.0.1",
        port=1933,
        meta_data={"ProjectName": "default", "CollectionName": "context"},
    )

    collection.update_index("default", [])

    assert captured["url"].endswith("UpdateVikingdbIndex")
    assert captured["json"]["ScalarIndex"] == "[]"
