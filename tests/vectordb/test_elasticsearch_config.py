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
    assert config.elasticsearch.index_type == "bbq_hnsw"
    assert config.elasticsearch.rescore_oversample == 3.0


def test_elasticsearch_rescore_oversample_can_be_disabled_but_not_below_one():
    assert ElasticsearchConfig(rescore_oversample=None).rescore_oversample is None
    with pytest.raises(ValueError, match="rescore_oversample"):
        ElasticsearchConfig(rescore_oversample=0.5)


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


def test_elasticsearch_accepts_sparse_weight():
    config = VectorDBBackendConfig(backend="elasticsearch", sparse_weight=0.5)
    assert config.sparse_weight == 0.5


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


@pytest.mark.parametrize(
    "index_type",
    [
        "bbq_hnsw",
        "bbq_flat",
        "bbq_disk",
        "hnsw",
        "int8_hnsw",
        "int4_hnsw",
        "flat",
        "int8_flat",
        "int4_flat",
    ],
)
def test_elasticsearch_accepts_every_dense_vector_index_type(index_type):
    assert ElasticsearchConfig(index_type=index_type).index_type == index_type


def test_elasticsearch_rejects_unknown_index_type():
    with pytest.raises(ValueError, match="index_type"):
        ElasticsearchConfig(index_type="ivf")


def test_elasticsearch_bbq_disk_tuning_defaults_to_cluster_defaults():
    config = ElasticsearchConfig(index_type="bbq_disk")
    assert config.cluster_size is None
    assert config.visit_percentage is None


@pytest.mark.parametrize("cluster_size", [63, 65537])
def test_elasticsearch_rejects_cluster_size_out_of_range(cluster_size):
    with pytest.raises(ValueError, match="cluster_size"):
        ElasticsearchConfig(index_type="bbq_disk", cluster_size=cluster_size)


def test_elasticsearch_cluster_size_requires_bbq_disk():
    with pytest.raises(ValueError, match="cluster_size"):
        ElasticsearchConfig(index_type="hnsw", cluster_size=384)


@pytest.mark.parametrize("visit_percentage", [-0.1, 100.1])
def test_elasticsearch_rejects_visit_percentage_out_of_range(visit_percentage):
    with pytest.raises(ValueError, match="visit_percentage"):
        ElasticsearchConfig(index_type="bbq_disk", visit_percentage=visit_percentage)


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
