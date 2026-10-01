# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Collection implementations for VikingDB."""

from openviking.storage.vectordb.collection.collection import Collection, ICollection
from openviking.storage.vectordb.collection.http_collection import (
    HttpCollection,
    get_or_create_http_collection,
)
from openviking.storage.vectordb.collection.local_collection import (
    LocalCollection,
    get_or_create_local_collection,
)

__all__ = [
    "ICollection",
    "Collection",
    "HttpCollection",
    "get_or_create_http_collection",
    "LocalCollection",
    "get_or_create_local_collection",
]
