# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Pure helpers that translate OpenViking schema and filter DSL to Elasticsearch."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Hidden object that holds derived path fields. It is excluded from every
# response so callers only see the fields they wrote.
INTERNAL_FIELD = "ov_internal"

# Keyword terms longer than this are stored but not indexed. 8191 characters
# keeps the UTF-8 encoding under Lucene's 32766-byte term limit.
KEYWORD_IGNORE_ABOVE = 8191

DATE_FORMAT = "strict_date_optional_time||epoch_millis"

_SIMILARITY_BY_DISTANCE = {
    "cosine": "cosine",
    "l2": "l2_norm",
    "ip": "max_inner_product",
}

_PATH_SCOPE_DEPTH_PATTERN = re.compile(r"\s*-d=(-?\d+)\s*")
_WILDCARD_SPECIAL = re.compile(r"([\\*?])")

# Field names become ES mapping keys; dots would create nested objects.
_FIELD_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def field_name(field: Dict[str, Any]) -> str:
    return field.get("FieldName") or field.get("field_name") or field.get("name", "")


def field_type(field: Dict[str, Any]) -> str:
    return field.get("FieldType") or field.get("field_type") or field.get("type", "string")


def vector_dimension(fields: Iterable[Dict[str, Any]]) -> int:
    for field in fields:
        if field_type(field) == "vector":
            return int(
                field.get("Dimension")
                or field.get("dimension")
                or field.get("Dim")
                or field.get("dim")
                or 0
            )
    return 0


def similarity_for_distance(distance: str) -> str:
    try:
        return _SIMILARITY_BY_DISTANCE[distance]
    except KeyError:
        raise ValueError(
            f"Elasticsearch backend does not support distance={distance!r}; "
            f"supported: {', '.join(sorted(_SIMILARITY_BY_DISTANCE))}"
        ) from None


def _keyword(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    mapping: Dict[str, Any] = {"type": "keyword", "ignore_above": KEYWORD_IGNORE_ABOVE}
    if extra:
        mapping.update(extra)
    return mapping


def build_properties(
    fields: Iterable[Dict[str, Any]],
    *,
    distance: str,
    index_options: Dict[str, Any],
) -> Dict[str, Any]:
    """Build mapping properties for an OpenViking collection schema."""
    properties: Dict[str, Any] = {"id": {"type": "keyword"}}
    internal: Dict[str, Any] = {}
    for field in fields:
        name = field_name(field)
        ftype = field_type(field)
        if not name or name == "id":
            continue
        if not _FIELD_NAME_PATTERN.match(name):
            raise ValueError(f"Elasticsearch backend does not support field name {name!r}")
        if ftype == "vector":
            dim = vector_dimension([field])
            if dim <= 0:
                raise ValueError("Elasticsearch backend requires a positive vector dimension")
            properties[name] = {
                "type": "dense_vector",
                "dims": dim,
                "index": True,
                "similarity": similarity_for_distance(distance),
                "index_options": dict(index_options),
            }
        elif ftype == "path":
            properties[name] = _keyword()
            internal[f"{name}_norm"] = _keyword()
            internal[f"{name}_depth"] = {"type": "integer"}
        elif ftype == "string":
            properties[name] = _keyword({"fields": {"text": {"type": "text"}}})
        elif ftype == "text":
            properties[name] = {"type": "text"}
        elif ftype == "list<string>":
            properties[name] = _keyword()
        elif ftype in {"int64", "list<int64>"}:
            properties[name] = {"type": "long"}
        elif ftype == "int32":
            properties[name] = {"type": "integer"}
        elif ftype in {"float", "float32"}:
            properties[name] = {"type": "double"}
        elif ftype == "bool":
            properties[name] = {"type": "boolean"}
        elif ftype == "date_time":
            properties[name] = {"type": "date", "format": DATE_FORMAT}
        elif ftype == "sparse_vector":
            # Stored for round-trips only; sparse search is not supported.
            properties[name] = {"type": "object", "enabled": False}
        else:
            properties[name] = _keyword()
    if internal:
        properties[INTERNAL_FIELD] = {"type": "object", "properties": internal}
    return properties


def path_fields(fields: Iterable[Dict[str, Any]]) -> set[str]:
    return {field_name(field) for field in fields if field_type(field) == "path"}


def text_search_fields(fields: Iterable[Dict[str, Any]]) -> List[str]:
    """Fields searched by BM25 keyword queries."""
    result: List[str] = []
    for field in fields:
        name = field_name(field)
        ftype = field_type(field)
        if ftype == "string" and name != "id":
            result.append(f"{name}.text")
        elif ftype == "text":
            result.append(name)
    return result


def normalize_path(path: Any) -> str:
    stripped = str(path).strip() or "/"
    if stripped != "/":
        stripped = stripped.rstrip("/") or "/"
    return stripped


def path_depth(normalized: str) -> int:
    if normalized == "/":
        return 0
    # Count segments the way the SQL backend does: empty segments count too.
    return normalized.strip("/").count("/") + 1


def derived_path_fields(record: Dict[str, Any], names: Iterable[str]) -> Dict[str, Any]:
    """Return the hidden norm/depth values for path fields present in *record*."""
    derived: Dict[str, Any] = {}
    for name in names:
        if name not in record:
            continue
        value = record[name]
        if value is None:
            derived[f"{name}_norm"] = None
            derived[f"{name}_depth"] = None
            continue
        normalized = normalize_path(value)
        derived[f"{name}_norm"] = normalized
        derived[f"{name}_depth"] = path_depth(normalized)
    return derived


def parse_path_scope_depth(para: Any) -> Optional[int]:
    if not isinstance(para, str):
        return None
    match = _PATH_SCOPE_DEPTH_PATTERN.fullmatch(para)
    if not match:
        return None
    return int(match.group(1))


MATCH_NONE: Dict[str, Any] = {"match_none": {}}


def _path_scope_query(field: str, prefix: Any, depth: int, is_path: bool) -> Dict[str, Any]:
    """PathScope with the same relative-depth contract as the other backends.

    ``depth < 0`` is unbounded recursion, ``depth == 0`` an exact match, and a
    positive depth includes the node plus descendants at most ``depth``
    segments below it. Stored and query paths are normalized identically, so
    trailing slashes never change the result.
    """
    normalized = normalize_path(prefix)
    if is_path:
        norm_field = f"{INTERNAL_FIELD}.{field}_norm"
        depth_field = f"{INTERNAL_FIELD}.{field}_depth"
    else:
        norm_field = field
        depth_field = None
    exact = {"term": {norm_field: normalized}}
    if depth == 0:
        return exact
    child_prefix = "/" if normalized == "/" else f"{normalized}/"
    descendants: Dict[str, Any] = {"prefix": {norm_field: child_prefix}}
    if depth > 0:
        if depth_field is None:
            raise ValueError(
                f"Elasticsearch backend supports bounded path depth only on path fields; "
                f"got field {field!r}"
            )
        descendants = {
            "bool": {
                "filter": [
                    descendants,
                    {"range": {depth_field: {"lte": path_depth(normalized) + depth}}},
                ]
            }
        }
    return {"bool": {"should": [exact, descendants], "minimum_should_match": 1}}


def _range_query(field: str, condition: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    bounds = {
        bound: condition[bound]
        for bound in ("gt", "gte", "lt", "lte")
        if condition.get(bound) is not None
    }
    if not bounds:
        return None
    return {"range": {field: bounds}}


def _escape_wildcard(value: str) -> str:
    return _WILDCARD_SPECIAL.sub(r"\\\1", value)


def build_query(
    filters: Optional[Dict[str, Any]],
    path_field_names: Optional[set[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Translate OpenViking filter DSL to an Elasticsearch query clause.

    Returns ``None`` when the filter imposes no constraint.
    """
    if not filters:
        return None
    path_names = path_field_names or set()
    op = filters.get("op", "")

    if op in {"and", "or"}:
        clauses = [
            clause
            for clause in (build_query(cond, path_names) for cond in filters.get("conds", []))
            if clause is not None
        ]
        if op == "and":
            if not clauses:
                return None
            return clauses[0] if len(clauses) == 1 else {"bool": {"filter": clauses}}
        # A vacuous OR is a contradiction, not an unfiltered scan.
        if not clauses:
            return dict(MATCH_NONE)
        if len(clauses) == 1:
            return clauses[0]
        return {"bool": {"should": clauses, "minimum_should_match": 1}}

    field = filters.get("field", "")
    if not field:
        raise ValueError(f"Elasticsearch filter op={op!r} requires a field")
    is_path = field in path_names

    if op in {"must", "must_not"}:
        conds = list(filters.get("conds", []))
        depth = parse_path_scope_depth(filters.get("para", ""))
        if depth is not None and len(conds) == 1:
            clause = _path_scope_query(field, conds[0], depth, is_path)
        elif conds:
            clause = {"terms": {field: conds}}
        elif op == "must":
            # Empty In/Eq is a contradiction, not an unfiltered scan.
            return dict(MATCH_NONE)
        else:
            return None
        if op == "must":
            return clause
        return {"bool": {"must_not": [clause]}}

    if op == "prefix":
        return {"prefix": {field: str(filters.get("prefix", ""))}}

    if op in {"range", "time_range"}:
        return _range_query(field, filters)

    if op == "contains":
        raw = filters.get("substring", "")
        substring = _escape_wildcard("" if raw is None else str(raw))
        return {"wildcard": {field: {"value": f"*{substring}*"}}}

    raise NotImplementedError(f"Elasticsearch backend does not support filter op={op!r}")


# Sort values Elasticsearch substitutes for missing long/date fields.
_MISSING_SORT_SENTINELS = {-(2**63), 2**63 - 1}


def sort_score(value: Any) -> float:
    """Numeric score from a sort value; missing and non-numeric values score 0."""
    if value is None or isinstance(value, bool):
        return 0.0
    if isinstance(value, int) and value in _MISSING_SORT_SENTINELS:
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def similarity_from_score(distance: str, score: Any) -> float:
    """Convert an Elasticsearch kNN ``_score`` to OpenViking's similarity.

    The other backends report cosine similarity, raw inner product, and
    ``1 / (1 + l2)``; Elasticsearch rescales each to a positive score.
    """
    try:
        value = float(score)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(value):
        return 0.0
    if distance == "cosine":
        return 2.0 * value - 1.0
    if distance == "ip":
        if value >= 1.0:
            return value - 1.0
        return 1.0 - 1.0 / value if value > 0 else 0.0
    # l2_norm: score = 1 / (1 + d^2)
    if value <= 0:
        return 0.0
    squared = max(1.0 / value - 1.0, 0.0)
    return 1.0 / (1.0 + math.sqrt(squared))


def validate_vector(vector: Any, dimension: int, *, field: str = "vector") -> List[float]:
    if not isinstance(vector, (list, tuple)):
        raise ValueError(f"{field} must be a list of floats")
    if dimension and len(vector) != dimension:
        raise ValueError(f"{field} has dimension {len(vector)}, expected {dimension}")
    values: List[float] = []
    for value in vector:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{field} contains a non-finite value")
        values.append(number)
    return values


def count_condition_matches(count: int, cond: Optional[Dict[str, Any]]) -> bool:
    if not cond:
        return True
    gt, gte, lt, lte = (cond.get(key) for key in ("gt", "gte", "lt", "lte"))
    if gt is not None and count <= gt:
        return False
    if gte is not None and count < gte:
        return False
    if lt is not None and count >= lt:
        return False
    if lte is not None and count > lte:
        return False
    return True


def split_batches(items: List[Any], size: int) -> Iterable[List[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def bulk_errors(response: Dict[str, Any]) -> List[Tuple[str, int, Any]]:
    """Return ``(id, status, error)`` for failed items of a bulk response."""
    failures: List[Tuple[str, int, Any]] = []
    if not response.get("errors"):
        return failures
    for item in response.get("items", []):
        for result in item.values():
            status = int(result.get("status", 0))
            if status >= 300:
                failures.append((str(result.get("_id")), status, result.get("error")))
    return failures
