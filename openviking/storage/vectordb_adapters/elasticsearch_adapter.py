# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Elasticsearch 8.x vector database adapter.

Each OpenViking collection maps to one Elasticsearch index named
``<index_prefix><collection name>`` with a ``dense_vector`` field for kNN
search. Requires ``pip install "openviking[elasticsearch]"``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from openviking.storage.expr import FilterExpr, Or
from openviking.storage.vectordb.collection.collection import Collection
from openviking.storage.vectordb_adapters.base import CollectionAdapter
from openviking_cli.utils import get_logger
from openviking_cli.utils.config.vectordb_config import (
    ElasticsearchConfig,
    VectorDBBackendConfig,
)

from .elasticsearch.client import create_client, is_already_exists
from .elasticsearch.collection import (
    DISTANCE_KEY,
    INDEXES_KEY,
    META_KEY,
    ElasticsearchCollection,
    ElasticsearchSettings,
)
from .elasticsearch.query import MATCH_NONE

logger = get_logger(__name__)

# https://www.elastic.co/guide/en/elasticsearch/reference/8.19/indices-create-index.html
_INDEX_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_MAX_INDEX_NAME_BYTES = 255
_EMPTY_OR_FILTER: Dict[str, Any] = {"op": "or", "conds": []}


def es_index_name(prefix: str, collection_name: str) -> str:
    name = f"{prefix}{collection_name}"
    if (
        not _INDEX_NAME_PATTERN.match(name)
        or name in {".", ".."}
        or len(name.encode("utf-8")) > _MAX_INDEX_NAME_BYTES
    ):
        raise ValueError(
            f"Invalid Elasticsearch index name {name!r} (index_prefix + collection name): "
            "use lowercase letters, digits, '_', '-' or '.', starting with a letter or digit"
        )
    return name


class ElasticsearchCollectionAdapter(CollectionAdapter):
    """OpenViking CollectionAdapter backed by an Elasticsearch 8.x index."""

    mode = "elasticsearch"
    USE_CONTENT_FIELD = False

    def __init__(
        self,
        collection_name: str,
        config: ElasticsearchConfig,
        index_name: str = "default",
        distance_metric: str = "cosine",
        client: Optional[Any] = None,
    ):
        super().__init__(collection_name=collection_name, index_name=index_name)
        self._config = config.model_copy(deep=True)
        self._distance = (distance_metric or "cosine").lower()
        self._es_index = es_index_name(self._config.index_prefix, collection_name)
        self._client = client if client is not None else create_client(self._config)
        self._es_backend: Optional[ElasticsearchCollection] = None
        self._settings = ElasticsearchSettings(
            refresh=self._config.refresh,
            bulk_batch_size=self._config.bulk_batch_size,
            num_candidates=self._config.num_candidates,
        )

    @classmethod
    def from_config(cls, config: VectorDBBackendConfig) -> "ElasticsearchCollectionAdapter":
        if config.elasticsearch is None:
            raise ValueError("VectorDB elasticsearch backend requires 'elasticsearch' config")
        return cls(
            collection_name=config.name or "context",
            config=config.elasticsearch,
            index_name=config.index_name or "default",
            distance_metric=config.distance_metric,
        )

    @property
    def es_index(self) -> str:
        return self._es_index

    def _compile_filter(self, expr: FilterExpr | Dict[str, Any] | None) -> Dict[str, Any]:
        compiled = super()._compile_filter(expr)
        # The base compiler collapses an empty Or to ``{}`` (unfiltered). A
        # vacuous OR is a contradiction; keep it so the query matches nothing.
        if isinstance(expr, Or) and not compiled:
            return dict(_EMPTY_OR_FILTER)
        return compiled

    def _index_options(self) -> Dict[str, Any]:
        options: Dict[str, Any] = {"type": self._config.index_type}
        if self._config.index_type.endswith("hnsw"):
            options["m"] = self._config.m
            options["ef_construction"] = self._config.ef_construction
        return options

    def _bind_collection(self, meta: Dict[str, Any], stored: Dict[str, Any]) -> None:
        self._es_backend = ElasticsearchCollection(
            self._client,
            self._es_index,
            meta,
            self._distance,
            self._settings,
            indexes=stored.get(INDEXES_KEY) or {},
        )
        self._collection = Collection(self._es_backend)

    def _load_existing_collection_if_needed(self) -> None:
        if self._collection is not None:
            return
        if not self._client.indices.exists(index=self._es_index):
            return
        stored = ElasticsearchCollection.read_stored_meta(self._client, self._es_index)
        if stored is None:
            raise RuntimeError(
                f"Elasticsearch index {self._es_index!r} exists but was not created by "
                "Business Data Platform; refusing to adopt it"
            )
        stored_distance = stored.get(DISTANCE_KEY)
        if stored_distance and stored_distance != self._distance:
            raise ValueError(
                f"Elasticsearch index {self._es_index!r} uses distance {stored_distance!r} but "
                f"distance_metric is {self._distance!r}; the vector similarity is fixed at index "
                "creation, so reindex into a new collection to change it"
            )
        self._bind_collection(dict(stored[META_KEY]), stored)

    def _create_backend_collection(self, meta: Dict[str, Any]) -> Collection:
        try:
            ElasticsearchCollection.create_physical_index(
                self._client,
                self._es_index,
                meta,
                self._distance,
                index_options=self._index_options(),
                number_of_shards=self._config.number_of_shards,
                number_of_replicas=self._config.number_of_replicas,
            )
        except Exception as error:
            if not is_already_exists(error):
                raise
            # Another process created the index between our existence check and
            # create call; adopt it only if it carries OpenViking metadata.
            logger.info("elasticsearch_adapter: index %s created concurrently", self._es_index)
            self._load_existing_collection_if_needed()
            if self._collection is None:
                raise
            return self._collection
        logger.info("elasticsearch_adapter: created index %s", self._es_index)
        self._bind_collection(meta, {})
        return self._collection

    def _build_default_index_meta(
        self,
        *,
        index_name: str,
        distance: str,
        use_sparse: bool,
        sparse_weight: float,
        scalar_index_fields: list[str],
    ) -> Dict[str, Any]:
        if use_sparse:
            raise NotImplementedError(
                "Elasticsearch backend does not support sparse or hybrid vector indexes"
            )
        return {
            "IndexName": index_name,
            "VectorIndex": {
                "IndexType": self._config.index_type,
                "Distance": distance or self._distance,
            },
            "ScalarIndex": scalar_index_fields,
        }

    def query(
        self,
        *,
        query_vector: Optional[list[float]] = None,
        sparse_query_vector: Optional[Dict[str, float]] = None,
        filter: Optional[Dict[str, Any] | FilterExpr] = None,
        limit: int = 10,
        offset: int = 0,
        output_fields: Optional[list[str]] = None,
        order_by: Optional[str] = None,
        order_desc: bool = False,
    ) -> list[Dict[str, Any]]:
        if query_vector or sparse_query_vector or order_by:
            return super().query(
                query_vector=query_vector,
                sparse_query_vector=sparse_query_vector,
                filter=filter,
                limit=limit,
                offset=offset,
                output_fields=output_fields,
                order_by=order_by,
                order_desc=order_desc,
            )
        # The base class samples plain filters with a random-vector kNN search,
        # which Elasticsearch caps at k <= 10000. A filtered scan pages through
        # any number of matches instead.
        collection = self._es_collection()
        result = collection.search_by_filter(
            filters=self._compile_filter(filter),
            limit=limit,
            offset=offset,
            output_fields=output_fields,
        )
        records: list[Dict[str, Any]] = []
        for item in result.data:
            record = dict(item.fields) if item.fields else {}
            record["id"] = item.id
            record["_score"] = 0.0
            records.append(self._normalize_record_for_read(record))
        return records

    def delete(
        self,
        *,
        ids: Optional[list[str]] = None,
        filter: Optional[Dict[str, Any] | FilterExpr] = None,
        limit: Optional[int] = None,
    ) -> int:
        if ids is not None or filter is None:
            return super().delete(ids=ids, filter=filter)
        if limit is not None and limit <= 0:
            return 0
        return self._es_collection().delete_by_filter(self._compile_filter(filter), limit=limit)

    def _es_collection(self) -> ElasticsearchCollection:
        self.get_collection()  # loads the bound collection or raises CollectionNotFoundError
        if self._es_backend is None:
            raise RuntimeError("Elasticsearch adapter has no bound collection")
        return self._es_backend

    def update_data(self, data_list: list[Dict[str, Any]]) -> list[str]:
        normalized = [self._normalize_record_for_write(record) for record in data_list]
        return list(self.get_collection().update_data(normalized) or [])

    def begin_bulk_ingest(self) -> None:
        self.get_collection().begin_bulk_ingest()

    def end_bulk_ingest(self) -> None:
        self.get_collection().end_bulk_ingest()

    def close(self) -> None:
        super().close()
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                logger.debug("elasticsearch_adapter: client close failed", exc_info=True)
            self._client = None


__all__ = ["ElasticsearchCollectionAdapter", "MATCH_NONE", "es_index_name"]
