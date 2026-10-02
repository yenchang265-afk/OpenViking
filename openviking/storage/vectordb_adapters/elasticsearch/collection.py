# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""ICollection implementation backed by a single Elasticsearch index."""

from __future__ import annotations

import copy
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from openviking.storage.vectordb.collection.collection import ICollection
from openviking.storage.vectordb.collection.result import (
    AggregateResult,
    DataItem,
    FetchDataInCollectionResult,
    SearchItemResult,
    SearchResult,
)
from openviking_cli.utils import get_logger

from .client import is_not_found
from .index_handle import ElasticsearchIndexHandle
from .query import (
    INTERNAL_FIELD,
    build_properties,
    build_query,
    bulk_errors,
    count_condition_matches,
    derived_path_fields,
    field_name,
    field_type,
    path_fields,
    similarity_from_score,
    sort_score,
    split_batches,
    text_search_fields,
    validate_vector,
    vector_dimension,
)

logger = get_logger(__name__)

META_KEY = "ov_collection"
INDEXES_KEY = "ov_indexes"
DISTANCE_KEY = "ov_distance"

# Upper bound for grouped counts; matches the largest page other backends return.
_GROUPED_COUNT_SIZE = 10000
_SOURCE_EXCLUDES = [INTERNAL_FIELD]
# Default index.max_result_window: from + size beyond this needs search_after.
_RESULT_WINDOW = 10000
# Elasticsearch rejects kNN k (and num_candidates) above 10000.
_MAX_KNN_K = 10000


@dataclass(frozen=True)
class ElasticsearchSettings:
    refresh: str = "wait_for"
    bulk_batch_size: int = 500
    num_candidates: int = 100


def _check_result_window(limit: int, offset: int, operation: str) -> None:
    if max(offset, 0) + limit > _RESULT_WINDOW:
        raise ValueError(
            f"Elasticsearch {operation} supports limit + offset <= {_RESULT_WINDOW}, "
            f"got {max(offset, 0) + limit}"
        )


def _refresh_param(policy: str) -> Any:
    return {"true": True, "false": False}.get(policy, policy)


class ElasticsearchCollection(ICollection):
    """OpenViking collection stored as one Elasticsearch index.

    Collection and logical index metadata are persisted in the mapping
    ``_meta`` so a restarted process can recover them without a side table.
    """

    def __init__(
        self,
        client: Any,
        index: str,
        meta: Dict[str, Any],
        distance: str,
        settings: ElasticsearchSettings,
        indexes: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        super().__init__()
        self._client = client
        self._index = index
        self._meta = copy.deepcopy(meta)
        self._distance = distance
        self._settings = settings
        self._indexes: Dict[str, Dict[str, Any]] = copy.deepcopy(indexes or {})
        self._lock = threading.Lock()
        self._bulk_depth = 0
        self._refresh_fields()

    # ------------------------------------------------------------------
    # Mapping and metadata
    # ------------------------------------------------------------------

    @staticmethod
    def create_physical_index(
        client: Any,
        index: str,
        meta: Dict[str, Any],
        distance: str,
        *,
        index_options: Dict[str, Any],
        number_of_shards: int,
        number_of_replicas: Optional[int],
    ) -> None:
        settings: Dict[str, Any] = {"number_of_shards": number_of_shards}
        if number_of_replicas is not None:
            settings["number_of_replicas"] = number_of_replicas
        mappings = {
            "dynamic": "strict",
            "properties": build_properties(
                meta.get("Fields", []), distance=distance, index_options=index_options
            ),
            "_meta": {META_KEY: meta, INDEXES_KEY: {}, DISTANCE_KEY: distance},
        }
        client.indices.create(index=index, settings=settings, mappings=mappings)

    @staticmethod
    def read_stored_meta(client: Any, index: str) -> Optional[Dict[str, Any]]:
        """Return the mapping ``_meta`` of *index*, or None when it is not ours."""
        response = client.indices.get_mapping(index=index)
        body = dict(response)
        mapping = (body.get(index) or next(iter(body.values()), {})).get("mappings", {})
        stored = mapping.get("_meta") or {}
        if META_KEY not in stored:
            return None
        return stored

    def _refresh_fields(self) -> None:
        fields = self._meta.get("Fields", [])
        self._field_names = {field_name(field) for field in fields} | {"id"}
        self._path_fields = path_fields(fields)
        self._text_fields = text_search_fields(fields)
        self._vector_field = next(
            (field_name(field) for field in fields if field_type(field) == "vector"), None
        )
        self._dim = vector_dimension(fields)

    def _persist_meta(self) -> None:
        self._client.indices.put_mapping(
            index=self._index,
            meta={
                META_KEY: self._meta,
                INDEXES_KEY: self._indexes,
                DISTANCE_KEY: self._distance,
            },
        )

    def update(
        self,
        fields: Optional[Dict[str, Any] | List[Dict[str, Any]]] = None,
        description: Optional[str] = None,
    ):
        """Update collection metadata.

        ``fields`` is either a dict of metadata keys or a list of field
        definitions (the schema-update form); new field definitions are added
        to the mapping.
        """
        with self._lock:
            previous = copy.deepcopy(self._meta)
            if isinstance(fields, list):
                known = {field_name(field) for field in self._meta.get("Fields", [])}
                self._meta["Fields"] = list(self._meta.get("Fields", [])) + [
                    field for field in fields if field_name(field) not in known
                ]
            elif fields:
                self._meta.update(fields)
            if description is not None:
                self._meta["Description"] = description
            new_fields = [
                field
                for field in self._meta.get("Fields", [])
                if field_name(field) not in {field_name(old) for old in previous.get("Fields", [])}
            ]
            try:
                if new_fields:
                    self._client.indices.put_mapping(
                        index=self._index,
                        properties=build_properties(
                            new_fields, distance=self._distance, index_options={}
                        ),
                    )
                self._persist_meta()
            except Exception:
                self._meta = previous
                raise
            self._refresh_fields()

    def get_meta_data(self) -> Dict[str, Any]:
        meta = copy.deepcopy(self._meta)
        index_meta = self._indexes.get(self._default_index_name())
        if index_meta and "ScalarIndex" in index_meta:
            meta.setdefault("ScalarIndex", list(index_meta["ScalarIndex"]))
        return meta

    def _default_index_name(self) -> Optional[str]:
        return next(iter(self._indexes), None)

    def close(self):
        """The client is owned by the adapter."""

    def drop(self):
        try:
            self._client.indices.delete(index=self._index)
        except Exception as error:
            if not is_not_found(error):
                raise

    def begin_bulk_ingest(self) -> None:
        with self._lock:
            self._bulk_depth += 1

    def end_bulk_ingest(self) -> None:
        with self._lock:
            if self._bulk_depth == 0:
                return
            self._bulk_depth -= 1
            finished = self._bulk_depth == 0
        if finished:
            self._client.indices.refresh(index=self._index)

    def _write_refresh(self) -> Any:
        # Inside a bulk-ingest scope, skip per-request refresh and refresh once at the end.
        if self._bulk_depth:
            return False
        return _refresh_param(self._settings.refresh)

    # ------------------------------------------------------------------
    # Logical index management
    # ------------------------------------------------------------------

    def create_index(self, index_name: str, meta_data: Dict[str, Any]) -> ElasticsearchIndexHandle:
        vector_index = meta_data.get("VectorIndex") or {}
        requested = str(vector_index.get("Distance") or self._distance).lower()
        if requested != self._distance:
            raise ValueError(
                f"Elasticsearch index {self._index!r} was created with distance "
                f"{self._distance!r}; cannot add an index with distance {requested!r}"
            )
        if vector_index.get("EnableSparse"):
            raise NotImplementedError("Elasticsearch backend does not support sparse indexes")
        with self._lock:
            self._indexes[index_name] = copy.deepcopy(meta_data)
            self._persist_meta()
        return ElasticsearchIndexHandle(index_name, meta_data)

    def has_index(self, index_name: str) -> bool:
        return index_name in self._indexes

    def get_index(self, index_name: str) -> Optional[ElasticsearchIndexHandle]:
        meta = self._indexes.get(index_name)
        return ElasticsearchIndexHandle(index_name, meta) if meta is not None else None

    def list_indexes(self) -> List[str]:
        return list(self._indexes)

    def drop_index(self, index_name: str):
        with self._lock:
            if self._indexes.pop(index_name, None) is not None:
                self._persist_meta()

    def update_index(
        self,
        index_name: str,
        scalar_index: Optional[Any] = None,
        description: Optional[str] = None,
    ):
        with self._lock:
            meta = self._indexes.get(index_name)
            if meta is None:
                raise KeyError(f"Index {index_name!r} does not exist")
            if scalar_index is not None:
                meta["ScalarIndex"] = list(scalar_index)
            if description is not None:
                meta["Description"] = description
            self._persist_meta()

    def get_index_meta_data(self, index_name: str) -> Dict[str, Any]:
        return copy.deepcopy(self._indexes.get(index_name) or {})

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _query(self, filters: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        return build_query(filters, self._path_fields)

    def _source(self, output_fields: Optional[List[str]]) -> Dict[str, Any]:
        source: Dict[str, Any] = {"excludes": list(_SOURCE_EXCLUDES)}
        if output_fields is not None:
            source["includes"] = [field for field in output_fields if field != "id"] or ["id"]
        return source

    @staticmethod
    def _hit_fields(hit: Dict[str, Any]) -> Dict[str, Any]:
        fields = dict(hit.get("_source") or {})
        fields.pop("id", None)
        fields.pop(INTERNAL_FIELD, None)
        return fields

    def _search(self, **body: Any) -> List[Dict[str, Any]]:
        response = self._client.search(index=self._index, **body)
        return list(dict(response).get("hits", {}).get("hits", []))

    def search_by_vector(
        self,
        index_name: str,
        dense_vector: Optional[List[float]] = None,
        limit: int = 10,
        offset: int = 0,
        filters: Optional[Dict[str, Any]] = None,
        sparse_vector: Optional[Dict[str, float]] = None,
        output_fields: Optional[List[str]] = None,
    ) -> SearchResult:
        # Reject sparse queries before the dense short-circuit so a pure sparse
        # query fails loudly instead of looking like "no recall".
        if sparse_vector:
            raise NotImplementedError("Elasticsearch backend does not support sparse vector search")
        if not dense_vector or limit <= 0 or self._vector_field is None:
            return SearchResult(data=[])
        vector = validate_vector(dense_vector, self._dim, field="query vector")
        k = limit + max(offset, 0)
        if k > _MAX_KNN_K:
            raise ValueError(
                f"Elasticsearch kNN search supports limit + offset <= {_MAX_KNN_K}, got {k}"
            )
        knn: Dict[str, Any] = {
            "field": self._vector_field,
            "query_vector": vector,
            "k": k,
            "num_candidates": min(max(k, self._settings.num_candidates), 10000),
        }
        query = self._query(filters)
        if query is not None:
            knn["filter"] = query
        hits = self._search(
            knn=knn,
            size=limit,
            from_=max(offset, 0),
            source=self._source(output_fields),
        )
        return SearchResult(
            data=[
                SearchItemResult(
                    id=hit.get("_id"),
                    fields=self._hit_fields(hit),
                    score=similarity_from_score(self._distance, hit.get("_score")),
                )
                for hit in hits
            ]
        )

    def search_by_scalar(
        self,
        index_name: str,
        field: str,
        order: Optional[str] = "desc",
        limit: int = 10,
        offset: int = 0,
        filters: Optional[Dict[str, Any]] = None,
        output_fields: Optional[List[str]] = None,
    ) -> SearchResult:
        direction = "desc" if (order or "desc").lower() == "desc" else "asc"
        hits = self._paged_search(
            query=self._query(filters),
            sort=[
                {field: {"order": direction, "missing": "_last"}},
                {"id": {"order": direction}},
            ],
            limit=limit,
            offset=offset,
            output_fields=output_fields,
        )
        return SearchResult(
            data=[
                SearchItemResult(
                    id=hit.get("_id"),
                    fields=self._hit_fields(hit),
                    score=sort_score((hit.get("sort") or [None])[0]),
                )
                for hit in hits
            ]
        )

    def search_by_filter(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        offset: int = 0,
        output_fields: Optional[List[str]] = None,
    ) -> SearchResult:
        """Filtered scan in ``id`` order with no scoring; supports deep pages."""
        hits = self._paged_search(
            query=self._query(filters),
            sort=[{"id": {"order": "asc"}}],
            limit=limit,
            offset=offset,
            output_fields=output_fields,
        )
        return SearchResult(
            data=[
                SearchItemResult(id=hit.get("_id"), fields=self._hit_fields(hit), score=0.0)
                for hit in hits
            ]
        )

    def _paged_search(
        self,
        *,
        query: Optional[Dict[str, Any]],
        sort: List[Dict[str, Any]],
        limit: int,
        offset: int,
        output_fields: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        """Sorted search that pages past ``index.max_result_window`` with ``search_after``.

        ``sort`` must end with a unique tiebreaker (``id``) so pages never
        overlap or skip documents.
        """
        if limit <= 0:
            return []
        offset = max(offset, 0)
        body: Dict[str, Any] = {
            "query": query or {"match_all": {}},
            "sort": sort,
            "source": self._source(output_fields),
        }
        if offset + limit <= _RESULT_WINDOW:
            return self._search(size=limit, from_=offset, **body)
        hits: List[Dict[str, Any]] = []
        to_skip = offset
        search_after: Optional[List[Any]] = None
        while len(hits) < limit:
            page_size = min(_RESULT_WINDOW, to_skip + limit - len(hits))
            page = self._search(
                size=page_size,
                **body,
                **({"search_after": search_after} if search_after is not None else {}),
            )
            if not page:
                break
            search_after = page[-1].get("sort")
            if to_skip:
                skipped = min(to_skip, len(page))
                to_skip -= skipped
                page = page[skipped:]
            hits.extend(page[: limit - len(hits)])
            if search_after is None:
                break
        return hits

    def search_by_random(
        self,
        index_name: str,
        limit: int = 10,
        offset: int = 0,
        filters: Optional[Dict[str, Any]] = None,
        output_fields: Optional[List[str]] = None,
        advance: Optional[Dict[str, Any]] = None,
    ) -> SearchResult:
        _check_result_window(limit, offset, "random search")
        hits = self._search(
            query={
                "function_score": {
                    "query": self._query(filters) or {"match_all": {}},
                    "random_score": {},
                    "boost_mode": "replace",
                }
            },
            size=limit,
            from_=offset,
            source=self._source(output_fields),
        )
        return SearchResult(
            data=[
                SearchItemResult(id=hit.get("_id"), fields=self._hit_fields(hit), score=0.0)
                for hit in hits
            ]
        )

    def search_by_keywords(
        self,
        index_name: str,
        keywords: Optional[List[str]] = None,
        query: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        filters: Optional[Dict[str, Any]] = None,
        output_fields: Optional[List[str]] = None,
    ) -> SearchResult:
        text = (query or " ".join(keyword for keyword in keywords or [] if keyword)).strip()
        if not text or not self._text_fields or limit <= 0:
            return SearchResult(data=[])
        _check_result_window(limit, offset, "keyword search")
        bool_query: Dict[str, Any] = {
            "must": [{"multi_match": {"query": text, "fields": list(self._text_fields)}}]
        }
        filter_query = self._query(filters)
        if filter_query is not None:
            bool_query["filter"] = [filter_query]
        hits = self._search(
            query={"bool": bool_query},
            size=limit,
            from_=offset,
            source=self._source(output_fields),
        )
        return SearchResult(
            data=[
                SearchItemResult(
                    id=hit.get("_id"),
                    fields=self._hit_fields(hit),
                    score=float(hit.get("_score") or 0.0),
                )
                for hit in hits
            ]
        )

    def search_by_id(
        self,
        index_name: str,
        id: Any,
        limit: int = 10,
        offset: int = 0,
        filters: Optional[Dict[str, Any]] = None,
        output_fields: Optional[List[str]] = None,
    ) -> SearchResult:
        if self._vector_field is None:
            return SearchResult(data=[])
        try:
            document = dict(
                self._client.get(
                    index=self._index, id=str(id), source_includes=[self._vector_field]
                )
            )
        except Exception as error:
            if is_not_found(error):
                return SearchResult(data=[])
            raise
        vector = (document.get("_source") or {}).get(self._vector_field)
        if not vector:
            return SearchResult(data=[])
        result = self.search_by_vector(
            index_name,
            dense_vector=vector,
            limit=limit + offset + 1,
            offset=0,
            filters=filters,
            output_fields=output_fields,
        )
        candidates = [item for item in result.data if str(item.id) != str(id)]
        return SearchResult(data=candidates[offset : offset + limit])

    def search_by_multimodal(
        self,
        index_name: str,
        text: Optional[str],
        image: Optional[Any],
        video: Optional[Any],
        limit: int = 10,
        offset: int = 0,
        filters: Optional[Dict[str, Any]] = None,
        output_fields: Optional[List[str]] = None,
    ) -> SearchResult:
        raise NotImplementedError(
            "Elasticsearch backend requires upstream multimodal embedding before vector search"
        )

    # ------------------------------------------------------------------
    # Data operations
    # ------------------------------------------------------------------

    def _prepare_document(
        self, record: Dict[str, Any], record_index: int
    ) -> tuple[str, Dict[str, Any]]:
        record_id = str(record.get("id") or record.get("_id") or uuid.uuid4())
        document = {key: value for key, value in record.items() if key not in {"id", "_id"}}
        unknown = sorted(set(document) - self._field_names)
        if unknown:
            raise ValueError(
                f"Elasticsearch record at index {record_index} contains unknown fields: {unknown}"
            )
        if self._vector_field and document.get(self._vector_field) is not None:
            vector = validate_vector(
                document[self._vector_field],
                self._dim,
                field=f"record[{record_index}].{self._vector_field}",
            )
            # Elasticsearch rejects all-zero vectors under cosine similarity
            # (some embedders return them for empty text). Store the record
            # without a vector: it stays filterable but never matches kNN.
            if self._distance == "cosine" and not any(vector):
                logger.debug("elasticsearch: storing %s without a zero cosine vector", record_id)
                document[self._vector_field] = None
            else:
                document[self._vector_field] = vector
        derived = derived_path_fields(document, self._path_fields)
        if derived:
            document[INTERNAL_FIELD] = derived
        document["id"] = record_id
        return record_id, document

    def _bulk(
        self, operations: List[Dict[str, Any]], *, ignore_not_found: bool = False
    ) -> List[str]:
        """Run bulk operations; return IDs that were missing when not ignored."""
        missing: List[str] = []
        for batch in split_batches(operations, self._settings.bulk_batch_size * 2):
            response = dict(
                self._client.bulk(
                    index=self._index, operations=batch, refresh=self._write_refresh()
                )
            )
            failures = []
            for item_id, status, error in bulk_errors(response):
                if status == 404:
                    if not ignore_not_found:
                        missing.append(item_id)
                    continue
                failures.append((item_id, status, error))
            if failures:
                details = "; ".join(
                    f"{item_id}: {status} {(error or {}).get('type', '')} "
                    f"{(error or {}).get('reason', '')}".strip()
                    for item_id, status, error in failures[:5]
                )
                raise RuntimeError(
                    f"Elasticsearch bulk write failed for {len(failures)} document(s): {details}"
                )
        return missing

    def upsert_data(self, data_list: List[Dict[str, Any]], ttl: int = 0):
        """Insert or merge records; unspecified fields of existing records are kept."""
        if not data_list:
            return
        operations: List[Dict[str, Any]] = []
        for record_index, record in enumerate(data_list):
            record_id, document = self._prepare_document(record, record_index)
            operations.append({"update": {"_id": record_id, "retry_on_conflict": 3}})
            operations.append({"doc": document, "doc_as_upsert": True})
        self._bulk(operations)

    def update_data(self, data_list: List[Dict[str, Any]]):
        """Update existing records while preserving unspecified fields."""
        if not data_list:
            return []
        for record in data_list:
            if "id" not in record:
                raise ValueError("primary key 'id' is required for update")
        prepared = [
            self._prepare_document(record, record_index)
            for record_index, record in enumerate(data_list)
        ]
        ids = [record_id for record_id, _ in prepared]
        existing = self.fetch_data(ids)
        if existing.ids_not_exist:
            raise ValueError(f"record not found for primary key(s): {existing.ids_not_exist}")
        operations: List[Dict[str, Any]] = []
        for record_id, document in prepared:
            operations.append({"update": {"_id": record_id, "retry_on_conflict": 3}})
            operations.append({"doc": document})
        missing = self._bulk(operations)
        if missing:
            raise ValueError(f"record not found for primary key(s): {missing}")
        return ids

    def fetch_data(self, primary_keys: List[Any]) -> FetchDataInCollectionResult:
        if not primary_keys:
            return FetchDataInCollectionResult(items=[], ids_not_exist=[])
        str_keys = [str(key) for key in primary_keys]
        items: List[DataItem] = []
        found: set[str] = set()
        for batch in split_batches(str_keys, self._settings.bulk_batch_size):
            response = dict(
                self._client.mget(
                    index=self._index, ids=batch, source_excludes=list(_SOURCE_EXCLUDES)
                )
            )
            for document in response.get("docs", []):
                if not document.get("found"):
                    continue
                document_id = str(document.get("_id"))
                found.add(document_id)
                items.append(DataItem(id=document_id, fields=self._hit_fields(document)))
        return FetchDataInCollectionResult(
            items=items, ids_not_exist=[key for key in str_keys if key not in found]
        )

    def delete_data(self, primary_keys: List[Any]):
        if not primary_keys:
            return
        operations = [{"delete": {"_id": str(key)}} for key in primary_keys]
        self._bulk(operations, ignore_not_found=True)

    def delete_by_filter(self, filters: Dict[str, Any], limit: Optional[int] = None) -> int:
        """Delete documents matching *filters*; return how many were deleted."""
        query = self._query(filters)
        if query is None:
            # An unconstrained filter must never turn into "delete everything".
            return 0
        params: Dict[str, Any] = {}
        if limit is not None:
            params["max_docs"] = limit
        response = dict(
            self._client.delete_by_query(
                index=self._index,
                query=query,
                conflicts="proceed",
                refresh=self._settings.refresh != "false" and not self._bulk_depth,
                **params,
            )
        )
        failures = response.get("failures") or []
        if failures:
            raise RuntimeError(
                f"Elasticsearch delete_by_query failed for {len(failures)} document(s): "
                f"{failures[0]}"
            )
        return int(response.get("deleted", 0))

    def delete_all_data(self):
        response = dict(
            self._client.delete_by_query(
                index=self._index,
                query={"match_all": {}},
                conflicts="proceed",
                refresh=True,
            )
        )
        failures = response.get("failures") or []
        conflicts = int(response.get("version_conflicts") or 0)
        if failures or conflicts or response.get("timed_out"):
            raise RuntimeError(
                "Elasticsearch delete_all_data did not delete every document "
                f"(failures={len(failures)}, version_conflicts={conflicts}, "
                f"timed_out={bool(response.get('timed_out'))})"
            )

    def aggregate_data(
        self,
        index_name: str,
        op: str = "count",
        field: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        cond: Optional[Dict[str, Any]] = None,
    ) -> AggregateResult:
        if op != "count":
            raise NotImplementedError(f"Elasticsearch backend does not support aggregate op={op!r}")
        query = self._query(filters) or {"match_all": {}}
        if not field:
            response = dict(self._client.count(index=self._index, query=query))
            return AggregateResult(agg={"_total": int(response.get("count", 0))}, op=op)
        response = dict(
            self._client.search(
                index=self._index,
                query=query,
                size=0,
                aggs={"groups": {"terms": {"field": field, "size": _GROUPED_COUNT_SIZE}}},
            )
        )
        buckets = response.get("aggregations", {}).get("groups", {}).get("buckets", [])
        agg: Dict[str, Any] = {}
        for bucket in buckets:
            count = int(bucket.get("doc_count", 0))
            if count_condition_matches(count, cond):
                key = bucket.get("key_as_string", bucket.get("key"))
                agg[str(key)] = count
        return AggregateResult(agg=agg, op=op, field=field)
