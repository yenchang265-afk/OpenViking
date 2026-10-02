# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Logical index handle for the Elasticsearch backend."""

from __future__ import annotations

import copy
from typing import Any, Dict

from openviking.storage.vectordb.index.index import IIndex


class ElasticsearchIndexHandle(IIndex):
    """Logical index handle; the ANN index itself lives in the ES mapping."""

    def __init__(self, name: str, meta: Dict[str, Any]):
        self._name = name
        self._meta = meta

    def get_name(self) -> str:
        return self._name

    def get_meta_data(self) -> Dict[str, Any]:
        return copy.deepcopy(self._meta)

    def upsert_data(self, delta_list):
        """Data writes go through ElasticsearchCollection."""

    def delete_data(self, delta_list):
        """Data deletes go through ElasticsearchCollection."""

    def search(
        self, query_vector=None, limit=10, filters=None, sparse_raw_terms=None, sparse_values=None
    ):
        return [], []

    def aggregate(self, filters=None):
        return {}

    def update(self, scalar_index=None, description=None):
        """Index metadata updates go through ElasticsearchCollection.update_index."""

    def rebuild_scalar_index(self, scalar_index, cands_fields):
        """Elasticsearch indexes every mapped field; nothing to rebuild."""

    def close(self):
        """No resources to release."""

    def drop(self):
        """Dropping is handled by ElasticsearchCollection.drop_index."""
