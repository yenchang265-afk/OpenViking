# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Adapter behavior against a recording fake Elasticsearch client."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from openviking.storage.collection_schemas import CollectionSchemas
from openviking.storage.expr import Eq, Or
from openviking.storage.vectordb_adapters.elasticsearch.collection import (
    DISTANCE_KEY,
    INDEXES_KEY,
    META_KEY,
    SPARSE_FIELD_KEY,
)
from openviking.storage.vectordb_adapters.elasticsearch.query import INTERNAL_FIELD
from openviking.storage.vectordb_adapters.elasticsearch_adapter import (
    ElasticsearchCollectionAdapter,
)
from openviking_cli.utils.config.vectordb_config import ElasticsearchConfig

INDEX = "openviking_context"


class _ApiError(Exception):
    def __init__(self, status_code: int, error: str = ""):
        super().__init__(f"{status_code} {error}")
        self.status_code = status_code
        self.error = error


class _FakeIndices:
    def __init__(self, client: "_FakeClient"):
        self._client = client

    def exists(self, index):
        return index in self._client.mappings

    def create(self, index, settings, mappings):
        if index in self._client.mappings:
            raise _ApiError(400, "resource_already_exists_exception")
        self._client.calls.append(("create", {"settings": settings, "mappings": mappings}))
        self._client.mappings[index] = mappings

    def get_mapping(self, index):
        return {index: {"mappings": self._client.mappings[index]}}

    def put_mapping(self, index, meta=None, properties=None):
        mapping = self._client.mappings[index]
        if meta is not None:
            mapping["_meta"] = meta
        if properties:
            mapping.setdefault("properties", {}).update(properties)
        self._client.calls.append(("put_mapping", {"meta": meta, "properties": properties}))

    def delete(self, index):
        if index not in self._client.mappings:
            raise _ApiError(404, "index_not_found_exception")
        del self._client.mappings[index]

    def refresh(self, index):
        self._client.calls.append(("refresh", {}))


class _FakeClient:
    """Records requests; responses are queued per API name."""

    def __init__(self):
        self.mappings: Dict[str, Dict[str, Any]] = {}
        self.calls: List[tuple] = []
        self.responses: Dict[str, List[Any]] = {}
        self.indices = _FakeIndices(self)
        self.closed = False

    def queue(self, api: str, *responses: Any) -> None:
        self.responses.setdefault(api, []).extend(responses)

    def _respond(self, api: str, default: Any) -> Any:
        queue = self.responses.get(api)
        return queue.pop(0) if queue else default

    def bulk(self, index, operations, refresh):
        self.calls.append(("bulk", {"operations": operations, "refresh": refresh}))
        return self._respond("bulk", {"errors": False, "items": []})

    def mget(self, index, ids, source_excludes):
        self.calls.append(("mget", {"ids": ids, "source_excludes": source_excludes}))
        return self._respond(
            "mget", {"docs": [{"_id": i, "found": True, "_source": {"id": i}} for i in ids]}
        )

    def search(self, index, **body):
        self.calls.append(("search", body))
        return self._respond("search", {"hits": {"hits": []}})

    def count(self, index, query):
        self.calls.append(("count", {"query": query}))
        return self._respond("count", {"count": 0})

    def delete_by_query(self, index, query, conflicts, refresh, **params):
        self.calls.append(("delete_by_query", {"query": query, "refresh": refresh, **params}))
        return self._respond("delete_by_query", {"deleted": 0, "failures": []})

    def get(self, index, id, source_includes):
        self.calls.append(("get", {"id": id}))
        return self._respond("get", {"_id": id, "_source": {}})

    def close(self):
        self.closed = True

    def last(self, api: str) -> Dict[str, Any]:
        return [body for name, body in self.calls if name == api][-1]


def _adapter(client: _FakeClient, **config: Any) -> ElasticsearchCollectionAdapter:
    return ElasticsearchCollectionAdapter(
        collection_name="context",
        config=ElasticsearchConfig(**config),
        client=client,
    )


def _created(client: _FakeClient, **config: Any) -> ElasticsearchCollectionAdapter:
    adapter = _adapter(client, **config)
    created = adapter.create_collection(
        "context",
        CollectionSchemas.context_collection("context", 4),
        distance="cosine",
        sparse_weight=0.0,
        index_name="default",
    )
    assert created is True
    return adapter


def _created_sparse(client: _FakeClient, sparse_weight: float = 0.3, **config: Any):
    adapter = _adapter(client, **config)
    assert adapter.create_collection(
        "context",
        CollectionSchemas.context_collection("context", 4),
        distance="cosine",
        sparse_weight=sparse_weight,
        index_name="default",
    )
    return adapter


def _hits(*hits: Dict[str, Any]) -> Dict[str, Any]:
    return {"hits": {"hits": list(hits)}}


def test_create_collection_builds_strict_mapping_with_metadata():
    client = _FakeClient()
    _created(client, number_of_replicas=0)

    create = client.last("create")
    assert create["settings"] == {"number_of_shards": 1, "number_of_replicas": 0}
    mappings = create["mappings"]
    assert mappings["dynamic"] == "strict"
    assert mappings["properties"]["vector"]["dims"] == 4
    assert mappings["properties"]["vector"]["index_options"] == {
        "type": "hnsw",
        "m": 16,
        "ef_construction": 100,
    }
    stored = client.mappings[INDEX]["_meta"]
    assert stored[DISTANCE_KEY] == "cosine"
    assert stored[META_KEY]["CollectionName"] == "context"
    assert stored[INDEXES_KEY]["default"]["VectorIndex"]["Distance"] == "cosine"


def test_flat_index_type_omits_hnsw_parameters():
    client = _FakeClient()
    _created(client, index_type="int8_flat")
    options = client.last("create")["mappings"]["properties"]["vector"]["index_options"]
    assert options == {"type": "int8_flat"}


def test_existing_index_is_reloaded_from_mapping_meta():
    client = _FakeClient()
    _created(client)

    reloaded = _adapter(client)

    assert reloaded.collection_exists()
    assert reloaded.get_collection().list_indexes() == ["default"]
    assert (
        reloaded.create_collection(
            "context",
            CollectionSchemas.context_collection("context", 4),
            distance="cosine",
            sparse_weight=0.0,
            index_name="default",
        )
        is False
    )


def test_foreign_index_is_not_adopted():
    client = _FakeClient()
    client.mappings[INDEX] = {"properties": {}}

    with pytest.raises(RuntimeError, match="not created by Business Data Platform"):
        _adapter(client).collection_exists()


def test_distance_change_on_existing_index_is_rejected():
    client = _FakeClient()
    _created(client)

    adapter = ElasticsearchCollectionAdapter(
        collection_name="context",
        config=ElasticsearchConfig(),
        distance_metric="l2",
        client=client,
    )
    with pytest.raises(ValueError, match="distance"):
        adapter.collection_exists()


def test_dense_only_collection_stores_sparse_vectors_without_indexing():
    client = _FakeClient()
    _created(client)

    mappings = client.last("create")["mappings"]
    assert mappings["properties"]["sparse_vector"] == {"type": "object", "enabled": False}
    assert SPARSE_FIELD_KEY not in client.mappings[INDEX]["_meta"]


def test_sparse_collection_maps_rank_features_and_records_sparse_weight():
    client = _FakeClient()
    _created_sparse(client, sparse_weight=0.3)

    mappings = client.last("create")["mappings"]
    assert mappings["properties"]["sparse_vector"] == {"type": "rank_features"}
    stored = client.mappings[INDEX]["_meta"]
    assert stored[SPARSE_FIELD_KEY] == "sparse_vector"
    vector_index = stored[INDEXES_KEY]["default"]["VectorIndex"]
    assert vector_index["EnableSparse"] is True
    assert vector_index["SearchWithSparseLogitAlpha"] == 0.3


def test_sparse_index_on_dense_only_collection_is_rejected():
    client = _FakeClient()
    adapter = _created(client)

    with pytest.raises(ValueError, match="sparse_vector"):
        adapter.get_collection().create_index(
            "hybrid",
            {"VectorIndex": {"EnableSparse": True, "SearchWithSparseLogitAlpha": 0.5}},
        )


def test_sparse_vectors_are_escaped_on_write_and_restored_on_read():
    client = _FakeClient()
    adapter = _created_sparse(client)

    adapter.upsert({"id": "a", "sparse_vector": {"u.s.": 0.5, "zero": 0.0}})

    _, document = client.last("bulk")["operations"]
    assert document["doc"]["sparse_vector"] == {"u%2Es%2E": 0.5}

    client.queue(
        "mget",
        {
            "docs": [
                {
                    "_id": "a",
                    "found": True,
                    "_source": {"id": "a", "sparse_vector": {"u%2Es%2E": 0.5}},
                }
            ]
        },
    )
    assert adapter.get(["a"]) == [{"sparse_vector": {"u.s.": 0.5}, "id": "a"}]


def test_upsert_merges_documents_and_derives_path_fields():
    client = _FakeClient()
    adapter = _created(client)

    ids = adapter.upsert(
        # A raw path (not viking://) is stored as written; only the derived copy is normalized.
        {"id": "a", "uri": "/resources/docs/", "vector": [1, 0, 0, 0], "level": 1}
    )

    assert ids == ["a"]
    bulk = client.last("bulk")
    assert bulk["refresh"] == "wait_for"
    action, document = bulk["operations"]
    assert action == {"update": {"_id": "a", "retry_on_conflict": 3}}
    assert document["doc_as_upsert"] is True
    doc = document["doc"]
    assert doc["uri"] == "/resources/docs/"
    assert doc[INTERNAL_FIELD] == {"uri_norm": "/resources/docs", "uri_depth": 2}
    assert doc["vector"] == [1.0, 0.0, 0.0, 0.0]
    assert doc["id"] == "a"


def test_upsert_rejects_unknown_fields_and_bad_vectors():
    client = _FakeClient()
    adapter = _created(client)

    with pytest.raises(ValueError, match="unknown fields"):
        adapter.upsert({"id": "a", "not_in_schema": 1})
    with pytest.raises(ValueError, match="dimension"):
        adapter.upsert({"id": "a", "vector": [1, 0]})


def test_bulk_item_failures_raise():
    client = _FakeClient()
    adapter = _created(client)
    client.queue(
        "bulk",
        {
            "errors": True,
            "items": [
                {
                    "update": {
                        "_id": "a",
                        "status": 400,
                        "error": {"type": "mapper_parsing_exception", "reason": "bad"},
                    }
                }
            ],
        },
    )
    with pytest.raises(RuntimeError, match="mapper_parsing_exception"):
        adapter.upsert({"id": "a", "level": 1})


def test_update_data_requires_existing_records():
    client = _FakeClient()
    adapter = _created(client)
    client.queue("mget", {"docs": [{"_id": "missing", "found": False}]})

    with pytest.raises(ValueError, match="missing"):
        adapter.update_data([{"id": "missing", "level": 2}])
    assert not [name for name, _ in client.calls if name == "bulk"]


def test_update_data_sends_partial_updates_without_upsert():
    client = _FakeClient()
    adapter = _created(client)

    assert adapter.update_data([{"id": "a", "level": 2}]) == ["a"]
    action, document = client.last("bulk")["operations"]
    assert action == {"update": {"_id": "a", "retry_on_conflict": 3}}
    assert document == {"doc": {"level": 2, "id": "a"}}


def test_get_decodes_uris_and_hides_internal_fields():
    client = _FakeClient()
    adapter = _created(client)
    client.queue(
        "mget",
        {
            "docs": [
                {
                    "_id": "a",
                    "found": True,
                    "_source": {"id": "a", "uri": "/resources/a.md", INTERNAL_FIELD: {"x": 1}},
                },
                {"_id": "b", "found": False},
            ]
        },
    )

    assert adapter.get(["a", "b"]) == [{"uri": "viking://resources/a.md", "id": "a"}]
    assert client.last("mget")["source_excludes"] == [INTERNAL_FIELD]


def test_vector_query_builds_filtered_knn_and_converts_scores():
    client = _FakeClient()
    adapter = _created(client, num_candidates=50)
    client.queue(
        "search",
        {"hits": {"hits": [{"_id": "a", "_score": 0.75, "_source": {"uri": "/resources/a"}}]}},
    )

    records = adapter.query(
        query_vector=[1, 0, 0, 0], filter=Eq("account_id", "acc"), limit=5, offset=3
    )

    body = client.last("search")
    assert body["knn"]["k"] == 8
    assert body["knn"]["num_candidates"] == 50
    assert body["knn"]["filter"] == {"terms": {"account_id": ["acc"]}}
    assert body["size"] == 5
    assert body["from_"] == 3
    assert body["source"] == {"excludes": [INTERNAL_FIELD]}
    assert records == [{"uri": "viking://resources/a", "id": "a", "_score": pytest.approx(0.5)}]


def test_vector_query_rejects_k_above_elasticsearch_limit():
    client = _FakeClient()
    adapter = _created(client)
    with pytest.raises(ValueError, match="10000"):
        adapter.query(query_vector=[1, 0, 0, 0], limit=9000, offset=1001)


def test_sparse_vector_query_is_rejected():
    client = _FakeClient()
    adapter = _created(client)
    with pytest.raises(NotImplementedError, match="sparse"):
        adapter.query(sparse_query_vector={"a": 1.0}, limit=1)


def test_dense_only_index_ignores_sparse_query_alongside_dense_query():
    client = _FakeClient()
    adapter = _created(client)

    adapter.query(query_vector=[1, 0, 0, 0], sparse_query_vector={"a": 1.0}, limit=1)

    searches = [body for name, body in client.calls if name == "search"]
    assert len(searches) == 1
    assert "knn" in searches[0] and "query" not in searches[0]


def test_hybrid_query_fuses_dense_and_sparse_scores():
    client = _FakeClient()
    adapter = _created_sparse(client, sparse_weight=0.3)
    client.queue(
        "search",
        # kNN recall: cosine 0.9 and 0.5
        _hits(
            {"_id": "a", "_score": 0.95, "_source": {"uri": "/a", "sparse_vector": {"apple": 0.5}}},
            {"_id": "b", "_score": 0.75, "_source": {"uri": "/b"}},
        ),
        # sparse recall: "c" is found only here
        _hits(
            {
                "_id": "c",
                "_score": 2.9,
                "_source": {"uri": "/c", "sparse_vector": {"u%2Es%2E": 1.0, "apple": 1.0}},
            },
            {"_id": "a", "_score": 0.5, "_source": {"uri": "/a", "sparse_vector": {"apple": 0.5}}},
        ),
        # exact dense score for "c": cosine 0.2
        _hits({"_id": "c", "_score": 0.6}),
    )

    records = adapter.query(
        query_vector=[1, 0, 0, 0],
        sparse_query_vector={"apple": 1.0, "u.s.": 2.0, "neg": -1.0},
        filter=Eq("account_id", "acc"),
        limit=2,
        output_fields=["uri"],
    )

    knn, sparse, gap = [body for name, body in client.calls if name == "search"]
    account = {"terms": {"account_id": ["acc"]}}
    assert knn["knn"]["k"] == 6 and knn["knn"]["filter"] == account
    assert knn["source"]["includes"] == ["uri", "sparse_vector"]
    assert sparse["size"] == 6
    assert sparse["query"]["bool"]["filter"] == [account]
    assert [clause["rank_feature"]["field"] for clause in sparse["query"]["bool"]["should"]] == [
        "sparse_vector.apple",
        "sparse_vector.u%2Es%2E",
    ]
    assert gap["knn"]["filter"] == {"ids": {"values": ["c"]}}
    assert gap["knn"]["k"] == 1 and gap["source"] is False

    # c: 0.7 * 0.2 + 0.3 * (1 * 1 + 2 * 1); a: 0.7 * 0.9 + 0.3 * 0.5; b: 0.7 * 0.5
    assert [record["id"] for record in records] == ["c", "a"]
    assert records[0]["_score"] == pytest.approx(1.04)
    assert records[1]["_score"] == pytest.approx(0.78)
    assert all(set(record) == {"id", "uri", "_score"} for record in records)


def test_pure_sparse_query_on_sparse_index_skips_knn():
    client = _FakeClient()
    adapter = _created_sparse(client, sparse_weight=0.5)
    client.queue(
        "search",
        _hits({"_id": "a", "_score": 1.0, "_source": {"sparse_vector": {"t": 4.0}}}),
    )

    records = adapter.query(sparse_query_vector={"t": 0.5}, limit=1)

    searches = [body for name, body in client.calls if name == "search"]
    assert len(searches) == 1 and "knn" not in searches[0]
    assert records[0]["_score"] == pytest.approx(0.5 * 2.0)
    assert records[0]["sparse_vector"] == {"t": 4.0}


def test_sparse_weight_of_one_ranks_by_sparse_score_only():
    client = _FakeClient()
    adapter = _created_sparse(client, sparse_weight=1.0)

    adapter.query(query_vector=[1, 0, 0, 0], sparse_query_vector={"t": 1.0}, limit=1)

    searches = [body for name, body in client.calls if name == "search"]
    assert len(searches) == 1 and "knn" not in searches[0]


def test_sparse_index_survives_reload():
    client = _FakeClient()
    _created_sparse(client)

    reloaded = _adapter(client)
    reloaded.query(sparse_query_vector={"t": 1.0}, limit=1)

    assert "rank_feature" in str(client.last("search")["query"])


def test_hybrid_query_applies_time_decay_to_fused_score():
    client = _FakeClient()
    adapter = _created_sparse(client, sparse_weight=0.5)
    client.queue(
        "search",
        _hits({"_id": "a", "_score": 0.9, "_source": {"updated_at": 0, "sparse_vector": {}}}),
        _hits({"_id": "a", "_score": 0.0, "_source": {"updated_at": 0, "sparse_vector": {}}}),
    )

    records = adapter.query(
        query_vector=[1, 0, 0, 0],
        sparse_query_vector={"t": 1.0},
        limit=1,
        output_fields=["uri"],
        advance={"time_decay": {"protection": "0", "origin": "1970-01-08T00:00:00+00:00"}},
    )

    knn = [body for name, body in client.calls if name == "search"][0]
    assert knn["source"]["includes"] == ["uri", "updated_at", "sparse_vector"]
    # fused 0.5 * 0.8 + 0.5 * 0, halved by one scale of decay
    assert records[0]["_origin_score"] == pytest.approx(0.4)
    assert records[0]["_score"] == pytest.approx(0.2)
    assert "updated_at" not in records[0] and "sparse_vector" not in records[0]


def test_plain_filter_query_scans_in_id_order():
    client = _FakeClient()
    adapter = _created(client)

    adapter.query(filter=Eq("account_id", "acc"), limit=20, output_fields=["uri"])

    body = client.last("search")
    assert "knn" not in body
    assert body["sort"] == [{"id": {"order": "asc"}}]
    assert body["query"] == {"terms": {"account_id": ["acc"]}}
    assert body["source"] == {"excludes": [INTERNAL_FIELD], "includes": ["uri"]}


def test_deep_pages_use_search_after():
    client = _FakeClient()
    adapter = _created(client)

    def hits(start: int, count: int) -> Dict[str, Any]:
        return {
            "hits": {
                "hits": [
                    {"_id": f"r{i}", "_source": {}, "sort": [f"r{i}"]}
                    for i in range(start, start + count)
                ]
            }
        }

    client.queue("search", hits(0, 10000), hits(10000, 15))

    records = adapter.query(filter=Eq("account_id", "acc"), limit=10, offset=10005)

    searches = [body for name, body in client.calls if name == "search"]
    assert "from_" not in searches[0] and searches[0]["size"] == 10000
    assert searches[1]["search_after"] == ["r9999"]
    assert [record["id"] for record in records] == [f"r{i}" for i in range(10005, 10015)]


def test_scalar_query_sorts_with_missing_last_and_id_tiebreak():
    client = _FakeClient()
    adapter = _created(client)
    client.queue(
        "search",
        {"hits": {"hits": [{"_id": "a", "_source": {}, "sort": [-(2**63), "a"]}]}},
    )

    records = adapter.query(order_by="updated_at", order_desc=True, limit=3)

    assert client.last("search")["sort"] == [
        {"updated_at": {"order": "desc", "missing": "_last"}},
        {"id": {"order": "desc"}},
    ]
    assert records[0]["_score"] == 0.0


def test_count_and_empty_or_filter():
    client = _FakeClient()
    adapter = _created(client)
    client.queue("count", {"count": 7}, {"count": 0})

    assert adapter.count(Eq("account_id", "acc")) == 7
    assert client.last("count")["query"] == {"terms": {"account_id": ["acc"]}}
    assert adapter.count(Or([])) == 0
    assert client.last("count")["query"] == {"match_none": {}}


def test_grouped_count_uses_terms_aggregation():
    client = _FakeClient()
    adapter = _created(client)
    client.queue(
        "search",
        {
            "aggregations": {
                "groups": {
                    "buckets": [{"key": "acc", "doc_count": 3}, {"key": "acc2", "doc_count": 1}]
                }
            }
        },
    )

    result = adapter.get_collection().aggregate_data(
        "default", op="count", field="account_id", cond={"gt": 1}
    )

    assert result.agg == {"acc": 3}
    assert client.last("search")["aggs"]["groups"]["terms"]["field"] == "account_id"


def test_delete_by_filter_uses_delete_by_query():
    client = _FakeClient()
    adapter = _created(client)
    client.queue("delete_by_query", {"deleted": 4, "failures": []})

    assert adapter.delete(filter=Eq("account_id", "acc"), limit=10) == 4
    call = client.last("delete_by_query")
    assert call["query"] == {"terms": {"account_id": ["acc"]}}
    assert call["max_docs"] == 10
    assert call["refresh"] is True


def test_delete_with_unconstrained_filter_deletes_nothing():
    client = _FakeClient()
    adapter = _created(client)

    assert adapter.delete(filter={}) == 0
    assert not [name for name, _ in client.calls if name == "delete_by_query"]


def test_delete_by_ids_ignores_missing_documents():
    client = _FakeClient()
    adapter = _created(client)
    client.queue(
        "bulk",
        {"errors": True, "items": [{"delete": {"_id": "gone", "status": 404}}]},
    )

    assert adapter.delete(ids=["gone"]) == 1


def test_keyword_search_runs_bm25_over_text_fields():
    client = _FakeClient()
    adapter = _created(client)
    client.queue("search", {"hits": {"hits": [{"_id": "a", "_score": 2.5, "_source": {}}]}})

    records = adapter.search_by_keywords(query="apple", filter=Eq("account_id", "acc"))

    query = client.last("search")["query"]["bool"]
    assert "abstract.text" in query["must"][0]["multi_match"]["fields"]
    assert query["filter"] == [{"terms": {"account_id": ["acc"]}}]
    assert records == [{"id": "a", "_score": 2.5}]


def test_keyword_search_restricts_fields_and_accepts_bm25_mode():
    client = _FakeClient()
    adapter = _created(client)

    adapter.search_by_keywords(query="apple", mode="bm25", fields=["abstract"])

    assert client.last("search")["query"]["bool"]["must"][0]["multi_match"]["fields"] == [
        "abstract.text"
    ]
    adapter.search_by_keywords(query="apple", fields=["content", "missing"])
    assert client.last("search")["query"]["bool"]["must"][0]["multi_match"]["fields"] == ["content"]
    client.calls.clear()
    assert adapter.search_by_keywords(query="apple", fields=["missing"]) == []
    assert not client.calls
    with pytest.raises(NotImplementedError, match="mode"):
        adapter.search_by_keywords(query="apple", mode="phrase")


def test_strict_metadata_read_is_served_locally():
    client = _FakeClient()
    adapter = _created(client)

    meta = adapter.get_collection().get_meta_data(raise_on_error=True)

    assert meta["CollectionName"] == "context"


def test_vector_query_applies_event_time_decay():
    client = _FakeClient()
    adapter = _created(client)
    day = 24 * 60 * 60 * 1000
    client.queue(
        "search",
        {
            "hits": {
                "hits": [
                    # cosine 0.8, 7 days old: 5 days past protection, decays to ~0.49
                    {"_id": "old", "_score": 0.9, "_source": {"updated_at": 100 * day}},
                    # cosine 0.6, inside the protection window: unchanged
                    {
                        "_id": "new",
                        "_score": 0.8,
                        "_source": {"updated_at": "1970-04-17T00:00:00+00:00"},
                    },
                    # no timestamp: cosine 0.5 is kept
                    {"_id": "undated", "_score": 0.75, "_source": {}},
                ]
            }
        },
    )
    origin = "1970-04-18T00:00:00+00:00"  # 107 days after the epoch

    records = adapter.query(
        query_vector=[1, 0, 0, 0],
        limit=2,
        output_fields=["uri"],
        advance={"time_decay": {"protection": "2d", "origin": origin}},
    )

    body = client.last("search")
    assert body["knn"]["k"] == 6
    assert body["size"] == 6 and body["from_"] == 0
    assert body["source"]["includes"] == ["uri", "updated_at"]
    assert [record["id"] for record in records] == ["new", "undated"]
    assert records[0]["_score"] == pytest.approx(0.6)
    assert records[0]["_origin_score"] == pytest.approx(0.6)
    assert records[0]["_time_score"] == pytest.approx(1.0)
    assert "updated_at" not in records[0]
    assert records[1]["_score"] == pytest.approx(0.5)
    assert "_time_score" not in records[1]


def test_time_decay_halves_similarity_each_scale_past_protection():
    client = _FakeClient()
    adapter = _created(client)
    day = 24 * 60 * 60 * 1000
    client.queue(
        "search",
        {"hits": {"hits": [{"_id": "a", "_score": 0.9, "_source": {"updated_at": 0}}]}},
    )

    records = adapter.query(
        query_vector=[1, 0, 0, 0],
        limit=1,
        advance={"time_decay": {"protection": "0", "origin": "1970-01-08T00:00:00+00:00"}},
    )

    assert 7 * day == 604_800_000
    assert records[0]["_origin_score"] == pytest.approx(0.8)
    assert records[0]["_time_score"] == pytest.approx(0.5)
    assert records[0]["_score"] == pytest.approx(0.4)


def test_bulk_ingest_defers_refresh_until_scope_ends():
    client = _FakeClient()
    adapter = _created(client)

    adapter.begin_bulk_ingest()
    adapter.upsert({"id": "a", "level": 1})
    assert client.last("bulk")["refresh"] is False
    adapter.end_bulk_ingest()

    assert client.calls[-1][0] == "refresh"


def test_close_closes_client():
    client = _FakeClient()
    adapter = _created(client)
    adapter.close()
    assert client.closed


def test_zero_vector_under_cosine_is_stored_without_vector():
    client = _FakeClient()
    adapter = _created(client)

    adapter.upsert({"id": "empty", "vector": [0, 0, 0, 0], "level": 1})

    _, document = client.last("bulk")["operations"]
    assert document["doc"]["vector"] is None


def test_delete_all_data_raises_when_documents_remain():
    client = _FakeClient()
    adapter = _created(client)
    client.queue("delete_by_query", {"deleted": 3, "failures": [], "version_conflicts": 2})

    with pytest.raises(RuntimeError, match="version_conflicts=2"):
        adapter.clear()


def test_collection_update_accepts_new_field_definitions():
    client = _FakeClient()
    adapter = _created(client)

    adapter.get_collection().update(fields=[{"FieldName": "extra_tag", "FieldType": "string"}])

    put = [body for name, body in client.calls if name == "put_mapping" and body["properties"]]
    assert put[-1]["properties"]["extra_tag"]["type"] == "keyword"
    field_names = [f["FieldName"] for f in adapter.get_collection().get_meta_data()["Fields"]]
    assert "extra_tag" in field_names
    adapter.upsert({"id": "a", "extra_tag": "x"})


@pytest.mark.parametrize("search", ["random", "keywords"])
def test_unpageable_searches_reject_deep_windows(search):
    client = _FakeClient()
    adapter = _created(client)

    with pytest.raises(ValueError, match="10000"):
        if search == "random":
            adapter.search_by_random(limit=10, offset=9995)
        else:
            adapter.search_by_keywords(query="apple", limit=10, offset=9995)
