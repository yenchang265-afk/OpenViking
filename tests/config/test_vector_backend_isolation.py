"""An Account-owned VectorDB must not inherit Cluster backend connections."""

import pytest

from openviking.config.vector import resolve_effective_vectordb
from openviking_cli.utils.config.vectordb_config import VectorDBBackendConfig

ACCOUNT_VECTORDB = {
    "backend": "http",
    "name": "account_context",
    "url": "http://account-vectordb:5000",
    "index_name": "default",
    "dimension": 8,
}


@pytest.mark.parametrize(
    ("backend", "connection"),
    [
        (
            "elasticsearch",
            {"hosts": ["http://cluster-es:9200"], "api_key": "cluster-es-secret"},
        ),
        (
            "opengauss",
            {"host": "cluster-gauss", "user": "cluster", "password": "cluster-gauss-secret"},
        ),
    ],
)
def test_account_vectordb_drops_cluster_connection_and_credentials(backend, connection):
    cluster = VectorDBBackendConfig.model_validate({"backend": backend, backend: connection})

    effective = resolve_effective_vectordb(cluster, ACCOUNT_VECTORDB)

    assert effective.backend == "http"
    assert effective.url == "http://account-vectordb:5000"
    dumped = effective.model_dump_json()
    assert "cluster" not in dumped
    assert "secret" not in dumped
