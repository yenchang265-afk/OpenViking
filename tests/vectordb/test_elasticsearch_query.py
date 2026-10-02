# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
import math

import pytest

from openviking.storage.collection_schemas import CollectionSchemas
from openviking.storage.vectordb_adapters.elasticsearch.query import (
    INTERNAL_FIELD,
    MATCH_NONE,
    build_properties,
    build_query,
    bulk_errors,
    count_condition_matches,
    derived_path_fields,
    normalize_path,
    path_depth,
    similarity_from_score,
    sort_score,
    text_search_fields,
    validate_vector,
)

PATHS = {"uri"}


def test_mapping_covers_context_schema_field_types():
    schema = CollectionSchemas.context_collection("context", 8)

    props = build_properties(
        schema["Fields"],
        distance="cosine",
        index_options={"type": "hnsw", "m": 16, "ef_construction": 100},
    )

    assert props["id"] == {"type": "keyword"}
    assert props["vector"]["type"] == "dense_vector"
    assert props["vector"]["dims"] == 8
    assert props["vector"]["similarity"] == "cosine"
    assert props["vector"]["index_options"]["type"] == "hnsw"
    assert props["uri"]["type"] == "keyword"
    assert props[INTERNAL_FIELD]["properties"]["uri_norm"]["type"] == "keyword"
    assert props[INTERNAL_FIELD]["properties"]["uri_depth"]["type"] == "integer"
    assert props["abstract"]["fields"]["text"]["type"] == "text"
    assert props["content"] == {"type": "text"}
    assert props["search_tags"]["type"] == "keyword"
    assert props["level"] == {"type": "long"}
    assert props["created_at"]["type"] == "date"
    assert props["sparse_vector"] == {"type": "object", "enabled": False}


@pytest.mark.parametrize(
    ("distance", "similarity"),
    [("cosine", "cosine"), ("l2", "l2_norm"), ("ip", "max_inner_product")],
)
def test_mapping_maps_distance_to_similarity(distance, similarity):
    props = build_properties(
        [{"FieldName": "vector", "FieldType": "vector", "Dim": 2}],
        distance=distance,
        index_options={"type": "flat"},
    )
    assert props["vector"]["similarity"] == similarity


def test_mapping_rejects_unsupported_distance_and_field_names():
    with pytest.raises(ValueError, match="distance"):
        build_properties(
            [{"FieldName": "vector", "FieldType": "vector", "Dim": 2}],
            distance="l1",
            index_options={},
        )
    with pytest.raises(ValueError, match="field name"):
        build_properties(
            [{"FieldName": "a.b", "FieldType": "string"}], distance="cosine", index_options={}
        )


def test_text_search_fields_use_text_subfields():
    fields = [
        {"FieldName": "id", "FieldType": "string"},
        {"FieldName": "abstract", "FieldType": "string"},
        {"FieldName": "content", "FieldType": "text"},
        {"FieldName": "level", "FieldType": "int64"},
    ]
    assert text_search_fields(fields) == ["abstract.text", "content"]


@pytest.mark.parametrize(
    ("raw", "normalized", "depth"),
    [
        ("/", "/", 0),
        ("  ", "/", 0),
        ("/resources/", "/resources", 1),
        ("/resources/docs/a.md", "/resources/docs/a.md", 3),
    ],
)
def test_path_normalization_and_depth(raw, normalized, depth):
    assert normalize_path(raw) == normalized
    assert path_depth(normalized) == depth


def test_derived_path_fields_only_for_present_paths():
    assert derived_path_fields({"uri": "/a/b/", "level": 1}, PATHS) == {
        "uri_norm": "/a/b",
        "uri_depth": 2,
    }
    assert derived_path_fields({"level": 1}, PATHS) == {}
    assert derived_path_fields({"uri": None}, PATHS) == {"uri_norm": None, "uri_depth": None}


def test_empty_filters_mean_no_constraint():
    assert build_query(None) is None
    assert build_query({}) is None
    assert build_query({"op": "and", "conds": []}) is None


def test_empty_or_and_empty_must_match_nothing():
    assert build_query({"op": "or", "conds": []}) == MATCH_NONE
    assert build_query({"op": "must", "field": "account_id", "conds": []}) == MATCH_NONE
    assert build_query({"op": "must_not", "field": "account_id", "conds": []}) is None


def test_and_or_combinations():
    query = build_query(
        {
            "op": "and",
            "conds": [
                {"op": "must", "field": "account_id", "conds": ["acc"]},
                {
                    "op": "or",
                    "conds": [
                        {"op": "must", "field": "level", "conds": [0]},
                        {"op": "must", "field": "level", "conds": [1]},
                    ],
                },
            ],
        }
    )
    assert query == {
        "bool": {
            "filter": [
                {"terms": {"account_id": ["acc"]}},
                {
                    "bool": {
                        "should": [{"terms": {"level": [0]}}, {"terms": {"level": [1]}}],
                        "minimum_should_match": 1,
                    }
                },
            ]
        }
    }


def test_must_not_wraps_terms():
    assert build_query({"op": "must_not", "field": "acl_mode", "conds": ["restricted"]}) == {
        "bool": {"must_not": [{"terms": {"acl_mode": ["restricted"]}}]}
    }


def test_path_scope_exact_match_uses_normalized_field():
    query = build_query({"op": "must", "field": "uri", "conds": ["/a/b/"], "para": "-d=0"}, PATHS)
    assert query == {"term": {f"{INTERNAL_FIELD}.uri_norm": "/a/b"}}


def test_path_scope_unbounded_matches_node_and_descendants():
    query = build_query({"op": "must", "field": "uri", "conds": ["/a"], "para": "-d=-1"}, PATHS)
    assert query == {
        "bool": {
            "should": [
                {"term": {f"{INTERNAL_FIELD}.uri_norm": "/a"}},
                {"prefix": {f"{INTERNAL_FIELD}.uri_norm": "/a/"}},
            ],
            "minimum_should_match": 1,
        }
    }


def test_path_scope_bounded_depth_is_relative_to_prefix():
    query = build_query({"op": "must", "field": "uri", "conds": ["/a/b"], "para": "-d=2"}, PATHS)
    descendants = query["bool"]["should"][1]["bool"]["filter"]
    assert descendants[0] == {"prefix": {f"{INTERNAL_FIELD}.uri_norm": "/a/b/"}}
    assert descendants[1] == {"range": {f"{INTERNAL_FIELD}.uri_depth": {"lte": 4}}}


def test_path_scope_from_root_uses_slash_prefix():
    query = build_query({"op": "must", "field": "uri", "conds": ["/"], "para": "-d=1"}, PATHS)
    descendants = query["bool"]["should"][1]["bool"]["filter"]
    assert descendants[0] == {"prefix": {f"{INTERNAL_FIELD}.uri_norm": "/"}}
    assert descendants[1] == {"range": {f"{INTERNAL_FIELD}.uri_depth": {"lte": 1}}}


def test_bounded_path_scope_on_non_path_field_is_rejected():
    with pytest.raises(ValueError, match="path fields"):
        build_query({"op": "must", "field": "name", "conds": ["/a"], "para": "-d=1"}, PATHS)


def test_path_must_without_para_matches_raw_values():
    assert build_query({"op": "must", "field": "uri", "conds": ["/a", "/b"]}, PATHS) == {
        "terms": {"uri": ["/a", "/b"]}
    }


def test_range_time_range_prefix_and_contains():
    assert build_query({"op": "range", "field": "level", "gte": 1, "lt": 3}) == {
        "range": {"level": {"gte": 1, "lt": 3}}
    }
    assert build_query({"op": "time_range", "field": "updated_at", "gte": "2026-01-01"}) == {
        "range": {"updated_at": {"gte": "2026-01-01"}}
    }
    assert build_query({"op": "range", "field": "level"}) is None
    assert build_query({"op": "prefix", "field": "name", "prefix": "ab"}) == {
        "prefix": {"name": "ab"}
    }
    assert build_query({"op": "contains", "field": "abstract", "substring": "a*b?c\\"}) == {
        "wildcard": {"abstract": {"value": "*a\\*b\\?c\\\\*"}}
    }


def test_unsupported_filter_op_raises():
    with pytest.raises(NotImplementedError, match="geo_range"):
        build_query({"op": "geo_range", "field": "loc"})


def test_similarity_from_score_inverts_elasticsearch_rescaling():
    # cosine: es = (1 + cos) / 2
    assert similarity_from_score("cosine", 1.0) == pytest.approx(1.0)
    assert similarity_from_score("cosine", 0.5) == pytest.approx(0.0)
    # l2_norm: es = 1 / (1 + d^2); Business Data Platform reports 1 / (1 + d)
    assert similarity_from_score("l2", 1.0 / (1.0 + 4.0)) == pytest.approx(1.0 / 3.0)
    # max_inner_product: dot >= 0 -> dot + 1; dot < 0 -> 1 / (1 - dot)
    assert similarity_from_score("ip", 3.5) == pytest.approx(2.5)
    assert similarity_from_score("ip", 0.25) == pytest.approx(-3.0)
    assert similarity_from_score("cosine", None) == 0.0
    assert similarity_from_score("cosine", math.nan) == 0.0


def test_sort_score_handles_missing_and_non_numeric_values():
    assert sort_score(1772323200000) == 1772323200000.0
    assert sort_score(-(2**63)) == 0.0
    assert sort_score(2**63 - 1) == 0.0
    assert sort_score("abc") == 0.0
    assert sort_score(None) == 0.0
    assert sort_score(True) == 0.0


def test_validate_vector():
    assert validate_vector([1, 2], 2) == [1.0, 2.0]
    with pytest.raises(ValueError, match="dimension"):
        validate_vector([1, 2, 3], 2)
    with pytest.raises(ValueError, match="non-finite"):
        validate_vector([1.0, math.inf], 2)
    with pytest.raises(ValueError, match="list"):
        validate_vector("1,2", 2)


def test_count_condition_matches():
    assert count_condition_matches(5, None)
    assert count_condition_matches(5, {"gt": 4, "lte": 5})
    assert not count_condition_matches(5, {"gt": 5})
    assert not count_condition_matches(5, {"lt": 5})


def test_bulk_errors_reports_failed_items_only():
    response = {
        "errors": True,
        "items": [
            {"update": {"_id": "a", "status": 200}},
            {"update": {"_id": "b", "status": 404, "error": {"type": "document_missing"}}},
            {"delete": {"_id": "c", "status": 400, "error": {"type": "mapper_parsing"}}},
        ],
    }
    assert bulk_errors(response) == [
        ("b", 404, {"type": "document_missing"}),
        ("c", 400, {"type": "mapper_parsing"}),
    ]
    assert bulk_errors({"errors": False, "items": []}) == []
