# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0

"""Summarize native CacheFS counters into hit rates for the console."""

from __future__ import annotations

from typing import Any, Iterable, Optional

_OPERATION_ORDER = ("read", "read_dir", "tree", "grep")
_KIND_ORDER = ("file", "directory")


def _hit_rate(hits: int, misses: int) -> Optional[float]:
    """Return hits over cache lookups, or None before the first lookup."""
    lookups = hits + misses
    return hits / lookups if lookups else None


def _counter(record: dict[str, Any]) -> int:
    """Return a native counter's raw value, treating anything else as zero."""
    value = record.get("value")
    return value if record.get("type") == "counter" and type(value) is int else 0


def _ordered(groups: dict[str, dict[str, int]], order: Iterable[str]) -> list[str]:
    """Return known group names in display order, followed by unknown ones sorted."""
    known = [name for name in order if name in groups]
    return known + sorted(name for name in groups if name not in known)


def summarize_cache_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Return overall and per-operation CacheFS hit rates since process start.

    ``records`` is the flat list returned by the RAGFS binding's ``metrics()``.
    CacheFS only emits ``ragfs_cache_*`` series when at least one mount is
    wrapped by the cache, so their absence means CacheFS is disabled. Hit rates
    count cache lookups only; reads bypassed by policy are reported separately.
    """
    kinds: dict[str, dict[str, int]] = {}
    operations: dict[str, dict[str, int]] = {}
    totals = {
        "bypasses": 0,
        "errors": 0,
        "stale_versions": 0,
        "invalidation_failures": 0,
        "backend_saved": 0,
        "bytes_from_cache": 0,
        "bytes_from_backend": 0,
    }
    enabled = False
    for record in records:
        name = record.get("name")
        labels = record.get("labels") or {}
        value = _counter(record)
        if name == "ragfs_cache_requests_total":
            enabled = True
            counts = kinds.setdefault(str(labels.get("kind", "")), {"hits": 0, "misses": 0})
            result = labels.get("result")
            if result == "hit":
                counts["hits"] += value
            elif result == "miss":
                counts["misses"] += value
        elif name == "ragfs_cache_operation_requests_total":
            counts = operations.setdefault(
                str(labels.get("operation", "")), {"hits": 0, "misses": 0, "bypasses": 0}
            )
            key = {"hit": "hits", "miss": "misses", "bypass": "bypasses"}.get(
                str(labels.get("result"))
            )
            if key:
                counts[key] += value
        elif name == "ragfs_cache_policy_bypasses_total":
            totals["bypasses"] += value
        elif name == "ragfs_cache_errors_total":
            totals["errors"] += value
        elif name == "ragfs_cache_stale_versions_total":
            totals["stale_versions"] += value
        elif name == "ragfs_cache_invalidation_failures_total":
            # Bumps that failed after retries: other instances may serve stale
            # entries for the affected paths until the cache TTL expires.
            totals["invalidation_failures"] += value
        elif name == "ragfs_cache_inflight_events_total" and labels.get("event") == "backend_saved":
            totals["backend_saved"] += value
        elif name == "ragfs_cache_bytes_total":
            source = labels.get("source")
            if source == "cache":
                totals["bytes_from_cache"] += value
            elif source == "backend":
                totals["bytes_from_backend"] += value

    if not enabled:
        return {"enabled": False, "message": "CacheFS is not enabled."}

    hits = sum(counts["hits"] for counts in kinds.values())
    misses = sum(counts["misses"] for counts in kinds.values())
    return {
        "enabled": True,
        "hits": hits,
        "misses": misses,
        "lookups": hits + misses,
        "hit_rate": _hit_rate(hits, misses),
        **totals,
        "kinds": [
            {"kind": kind, **kinds[kind], "hit_rate": _hit_rate(**kinds[kind])}
            for kind in _ordered(kinds, _KIND_ORDER)
        ],
        "operations": [
            {
                "operation": operation,
                **operations[operation],
                "hit_rate": _hit_rate(
                    operations[operation]["hits"], operations[operation]["misses"]
                ),
            }
            for operation in _ordered(operations, _OPERATION_ORDER)
        ],
    }
