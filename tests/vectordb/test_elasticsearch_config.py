# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
import pytest

from openviking.storage.vectordb_adapters.elasticsearch_adapter import (
    ElasticsearchCollectionAdapter,
    es_index_name,
)
from openviking.storage.vectordb_adapters.factory import _ADAPTER_REGISTRY
from openviking_cli.utils.config.vectordb_config import (
    ElasticsearchConfig,
    VectorDBBackendConfig,
)


def test_elasticsearch_backend_is_registered_and_accepted():
    config = VectorDBBackendConfig(backend="elasticsearch")

    assert _ADAPTER_REGISTRY["elasticsearch"] is ElasticsearchCollectionAdapter
    assert config.elasticsearch is not None
    assert config.elasticsearch.hosts == ["http://127.0.0.1:9200"]
    assert config.elasticsearch.refresh == "wait_for"
    assert config.elasticsearch.index_type == "hnsw"


def test_unknown_backend_error_lists_elasticsearch():
    with pytest.raises(ValueError, match="'elasticsearch'"):
        VectorDBBackendConfig(backend="qdrant")


@pytest.mark.parametrize("distance", ["cosine", "L2", "ip"])
def test_elasticsearch_accepts_supported_distances(distance):
    config = VectorDBBackendConfig(backend="elasticsearch", distance_metric=distance)
    assert config.distance_metric == distance.lower()


def test_elasticsearch_rejects_l1_distance():
    with pytest.raises(ValueError, match="distance_metric"):
        VectorDBBackendConfig(backend="elasticsearch", distance_metric="l1")


def test_elasticsearch_rejects_sparse_weight():
    with pytest.raises(ValueError, match="sparse_weight"):
        VectorDBBackendConfig(backend="elasticsearch", sparse_weight=0.5)


def test_elasticsearch_requires_username_and_password_together():
    with pytest.raises(ValueError, match="together"):
        ElasticsearchConfig(username="elastic")
    config = ElasticsearchConfig(username="elastic", password="secret")
    assert config.username == "elastic"


def test_elasticsearch_rejects_api_key_with_basic_auth():
    with pytest.raises(ValueError, match="either api_key"):
        ElasticsearchConfig(api_key="key", username="elastic", password="secret")


@pytest.mark.parametrize("prefix", ["Upper_", "_hidden", "-dash", "has space"])
def test_elasticsearch_rejects_invalid_index_prefix(prefix):
    with pytest.raises(ValueError, match="index_prefix"):
        ElasticsearchConfig(index_prefix=prefix)


def test_elasticsearch_allows_empty_index_prefix():
    assert ElasticsearchConfig(index_prefix="").index_prefix == ""


def test_elasticsearch_rejects_ef_construction_below_m():
    with pytest.raises(ValueError, match="ef_construction"):
        ElasticsearchConfig(m=32, ef_construction=16)


def test_elasticsearch_rejects_empty_hosts():
    with pytest.raises(ValueError, match="hosts"):
        ElasticsearchConfig(hosts=[])


def test_elasticsearch_config_forbids_unknown_fields():
    with pytest.raises(ValueError):
        ElasticsearchConfig(host="localhost")


def test_es_index_name_combines_prefix_and_collection():
    assert es_index_name("openviking_", "context") == "openviking_context"


@pytest.mark.parametrize("collection", ["Context", "with space", "a*b"])
def test_es_index_name_rejects_invalid_collection_names(collection):
    with pytest.raises(ValueError, match="Invalid Elasticsearch index name"):
        es_index_name("openviking_", collection)
