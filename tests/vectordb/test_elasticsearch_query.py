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
    build_sparse_query,
    bulk_errors,
    count_condition_matches,
    decode_sparse_vector,
    derived_path_fields,
    encode_sparse_vector,
    normalize_path,
    path_depth,
    similarity_from_score,
    sort_score,
    sparse_dot,
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


def test_mapping_maps_sparse_vector_to_rank_features_when_enabled():
    schema = CollectionSchemas.context_collection("context", 8)

    props = build_properties(
        schema["Fields"], distance="cosine", index_options={}, sparse_features=True
    )

    assert props["sparse_vector"] == {"type": "rank_features"}


def test_sparse_terms_are_escaped_reversibly():
    raw = {"u.s.": 1.0, "100%": 2.0, "%2E": 3.0, "plain": 4.0}

    encoded = encode_sparse_vector(raw)

    assert not any("." in term for term in encoded)
    assert len(encoded) == len(raw)
    assert decode_sparse_vector(encoded) == raw


def test_sparse_encoding_drops_non_positive_weights_and_rejects_bad_values():
    assert encode_sparse_vector({"a": 0.5, "b": 0, "c": -1.0, "": 2.0, "d": 1e-40}) == {"a": 0.5}
    assert encode_sparse_vector({7: 1}) == {"7": 1.0}
    with pytest.raises(ValueError, match="non-finite"):
        encode_sparse_vector({"a": math.inf})
    with pytest.raises(ValueError, match="non-numeric"):
        encode_sparse_vector({"a": "x"})
    with pytest.raises(ValueError, match="mapping"):
        encode_sparse_vector([1.0, 2.0])


def test_sparse_query_sums_linear_rank_features():
    query = build_sparse_query("sparse_vector", {"a": 0.5, "b%2E": 2.0}, {"term": {"x": 1}})

    assert query == {
        "bool": {
            "should": [
                {"rank_feature": {"field": "sparse_vector.a", "linear": {}, "boost": 0.5}},
                {"rank_feature": {"field": "sparse_vector.b%2E", "linear": {}, "boost": 2.0}},
            ],
            "minimum_should_match": 1,
            "filter": [{"term": {"x": 1}}],
        }
    }
    assert "filter" not in build_sparse_query("s", {"a": 1.0}, None)["bool"]


def test_sparse_dot_is_inner_product_over_shared_terms():
    assert sparse_dot({"a": 2.0, "b": 1.0}, {"a": 0.5, "c": 9.0}) == pytest.approx(1.0)
    assert sparse_dot({"a": 2.0}, None) == 0.0
    assert sparse_dot({"a": 2.0}, {}) == 0.0


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
    # l2_norm: es = 1 / (1 + d^2); OpenViking reports 1 / (1 + d)
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
