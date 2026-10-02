# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Elasticsearch adapter against a live cluster.

Set ``OPENVIKING_ELASTICSEARCH_URL`` (e.g. ``http://127.0.0.1:9200``) to run.
"""

from __future__ import annotations

import os
import uuid

import pytest

from openviking.storage.collection_schemas import CollectionSchemas
from openviking.storage.expr import Contains, Eq, In, Or, PathScope, Range
from openviking.storage.vectordb_adapters.elasticsearch_adapter import (
    ElasticsearchCollectionAdapter,
)
from openviking_cli.utils.config.vectordb_config import ElasticsearchConfig

pytestmark = pytest.mark.integration

_RECORDS = [
    {
        "id": "a",
        "uri": "viking://resources/docs",
        "level": 0,
        "vector": [1, 0, 0, 0],
        "abstract": "root docs",
        "account_id": "acc",
        "search_tags": ["team=x"],
        "updated_at": "2026-01-01T00:00:00",
    },
    {
        "id": "b",
        "uri": "viking://resources/docs/a.md",
        "level": 2,
        "vector": [0.9, 0.1, 0, 0],
        "abstract": "apple banana",
        "account_id": "acc",
        "search_tags": ["team=y"],
        "updated_at": "2026-02-01T00:00:00",
    },
    {
        "id": "c",
        "uri": "viking://resources/docs/sub/b.md",
        "level": 2,
        "vector": [0, 1, 0, 0],
        "abstract": "cherry",
        "account_id": "acc",
        "updated_at": "2026-03-01T00:00:00",
    },
    {
        "id": "d",
        "uri": "viking://resources/other.md",
        "level": 2,
        "vector": [0, 0, 1, 0],
        "abstract": "durian apple",
        "account_id": "acc2",
    },
]


def _config(prefix: str) -> ElasticsearchConfig:
    url = os.getenv("OPENVIKING_ELASTICSEARCH_URL")
    if not url:
        pytest.skip("OPENVIKING_ELASTICSEARCH_URL is not configured")
    return ElasticsearchConfig(hosts=[url], index_prefix=prefix, number_of_replicas=0)


@pytest.fixture
def adapter():
    pytest.importorskip("elasticsearch")
    config = _config(f"ovtest_{uuid.uuid4().hex[:8]}_")
    instance = ElasticsearchCollectionAdapter("context", config)
    instance.create_collection(
        "context",
        CollectionSchemas.context_collection("context", 4),
        distance="cosine",
        sparse_weight=0.0,
        index_name="default",
    )
    instance.upsert([dict(record) for record in _RECORDS])
    yield instance
    instance.drop_collection()
    instance.close()


def _ids(records):
    return sorted(record["id"] for record in records)


def test_fetch_count_and_reload(adapter):
    assert [r["uri"] for r in adapter.get(["a", "missing"])] == ["viking://resources/docs"]
    assert adapter.count() == 4
    assert adapter.count(Eq("account_id", "acc")) == 3

    reloaded = ElasticsearchCollectionAdapter("context", adapter._config)
    assert reloaded.collection_exists()
    assert reloaded.count() == 4
    reloaded.close()


@pytest.mark.parametrize(
    ("depth", "expected"), [(0, ["a"]), (1, ["a", "b"]), (-1, ["a", "b", "c"])]
)
def test_path_scope_depth(adapter, depth, expected):
    records = adapter.query(
        filter=PathScope("uri", "viking://resources/docs/", depth=depth), limit=50
    )
    assert _ids(records) == expected


def test_path_scope_from_root(adapter):
    records = adapter.query(filter=PathScope("uri", "viking://", depth=2), limit=50)
    assert _ids(records) == ["a", "d"]


def test_vector_search_scores_and_paging(adapter):
    records = adapter.query(query_vector=[1, 0, 0, 0], limit=3, filter=Eq("account_id", "acc"))
    assert [r["id"] for r in records] == ["a", "b", "c"]
    assert records[0]["_score"] == pytest.approx(1.0, abs=1e-3)
    assert records[2]["_score"] == pytest.approx(0.0, abs=1e-3)
    assert [r["id"] for r in adapter.query(query_vector=[1, 0, 0, 0], limit=2, offset=1)] == [
        "b",
        "c",
    ]


def test_filters(adapter):
    assert _ids(adapter.query(filter=In("search_tags", ["team=y"]), limit=10)) == ["b"]
    assert _ids(adapter.query(filter=Contains("abstract", "pple"), limit=10)) == ["b", "d"]
    assert _ids(adapter.query(filter=Range("level", gte=1), limit=10)) == ["b", "c", "d"]
    assert adapter.count(Or([])) == 0


def test_scalar_order_puts_missing_last(adapter):
    records = adapter.query(order_by="updated_at", order_desc=True, limit=10)
    assert [r["id"] for r in records] == ["c", "b", "a", "d"]
    assert records[-1]["_score"] == 0.0


def test_keyword_search(adapter):
    assert _ids(adapter.search_by_keywords(query="apple")) == ["b", "d"]
    assert _ids(adapter.search_by_keywords(query="apple", filter=Eq("account_id", "acc2"))) == ["d"]


def test_update_preserves_other_fields_and_rejects_missing(adapter):
    adapter.update_data([{"id": "b", "abstract": "apple updated"}])
    record = adapter.get(["b"])[0]
    assert record["abstract"] == "apple updated"
    assert record["uri"] == "viking://resources/docs/a.md"
    assert record["level"] == 2
    with pytest.raises(ValueError, match="nope"):
        adapter.update_data([{"id": "nope", "abstract": "x"}])


def test_grouped_count_and_deletes(adapter):
    collection = adapter.get_collection()
    assert collection.aggregate_data("default", field="account_id").agg == {"acc": 3, "acc2": 1}
    assert adapter.delete(filter=Eq("account_id", "acc2")) == 1
    adapter.delete(ids=["a"])
    assert adapter.count() == 2
    adapter.clear()
    assert adapter.count() == 0


def test_zero_vector_record_is_stored_but_not_recalled(adapter):
    adapter.upsert({"id": "z", "uri": "viking://resources/empty.md", "vector": [0, 0, 0, 0]})
    assert [r["id"] for r in adapter.get(["z"])] == ["z"]
    recalled = adapter.query(query_vector=[1, 0, 0, 0], limit=10)
    assert "z" not in {r["id"] for r in recalled}


def test_distance_mismatch_on_existing_index(adapter):
    other = ElasticsearchCollectionAdapter("context", adapter._config, distance_metric="l2")
    with pytest.raises(ValueError, match="distance"):
        other.collection_exists()
    other.close()
