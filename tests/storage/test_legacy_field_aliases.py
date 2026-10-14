# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""``created_by`` was ``uploaded_by``: collections created before the rename keep working."""

from typing import Any, Dict, List

import pytest

from openviking.core.context import Context
from openviking.storage.viking_vector_index_backend import _SingleAccountBackend
from openviking_cli.utils.config.vectordb_config import VectorDBBackendConfig

_BASE_FIELDS = ["id", "uri", "level", "account_id", "context_type", "updated_by"]


class _Collection:
    def __init__(self, fields: List[str]):
        self._fields = fields

    def get_meta_data(self, **_: Any) -> Dict[str, Any]:
        return {"Fields": [{"FieldName": name} for name in self._fields]}


class _Adapter:
    mode = "elasticsearch"
    USE_CONTENT_FIELD = False

    def __init__(self, fields: List[str], records: List[Dict[str, Any]] | None = None):
        self._collection = _Collection(fields)
        self.records = records or []
        self.upserts: List[Any] = []
        self.output_fields: List[Any] = []

    def get_collection(self):
        return self._collection

    def upsert(self, data):
        self.upserts.append(data)
        return [data["id"]]

    def get(self, ids):
        return [dict(record) for record in self.records if record["id"] in ids]

    def query(self, **kwargs):
        self.output_fields.append(kwargs.get("output_fields"))
        return [dict(record) for record in self.records]


def _backend(adapter: _Adapter) -> _SingleAccountBackend:
    return _SingleAccountBackend(
        config=VectorDBBackendConfig(backend="local", name="context", dimension=4),
        bound_account_id="acc1",
        shared_adapter=adapter,
    )


def _record(**fields: Any) -> Dict[str, Any]:
    return {"id": "r1", "uri": "viking://resources/a", "account_id": "acc1", **fields}


@pytest.mark.asyncio
async def test_unmigrated_collection_keeps_writing_the_legacy_field():
    adapter = _Adapter([*_BASE_FIELDS, "uploaded_by"])

    await _backend(adapter).upsert(_record(created_by="alice"))

    assert adapter.upserts[0]["uploaded_by"] == "alice"
    assert "created_by" not in adapter.upserts[0]


@pytest.mark.asyncio
async def test_migrated_collection_writes_the_new_field():
    adapter = _Adapter([*_BASE_FIELDS, "uploaded_by", "created_by"])

    await _backend(adapter).upsert(_record(created_by="alice"))

    assert adapter.upserts[0]["created_by"] == "alice"
    assert "uploaded_by" not in adapter.upserts[0]


@pytest.mark.asyncio
async def test_reads_fold_the_legacy_field_into_created_by():
    adapter = _Adapter(
        [*_BASE_FIELDS, "uploaded_by", "created_by"],
        [
            _record(uploaded_by="alice"),
            _record(id="r2", uploaded_by="old", created_by="bob"),
        ],
    )
    backend = _backend(adapter)

    fetched = await backend.get(["r1"])
    queried = await backend.query(output_fields=["uri", "created_by"])

    assert fetched[0]["created_by"] == "alice" and "uploaded_by" not in fetched[0]
    assert [record["created_by"] for record in queried] == ["alice", "bob"]
    assert adapter.output_fields[-1] == ["uri", "created_by", "uploaded_by"]


@pytest.mark.asyncio
async def test_reads_never_request_a_field_the_collection_lacks():
    unmigrated = _Adapter([*_BASE_FIELDS, "uploaded_by"], [_record(uploaded_by="alice")])
    fresh = _Adapter([*_BASE_FIELDS, "created_by"], [_record(created_by="bob")])

    old_records = await _backend(unmigrated).query(output_fields=["uri", "created_by"])
    new_records = await _backend(fresh).query(output_fields=["uri", "created_by"])

    assert unmigrated.output_fields[-1] == ["uri", "uploaded_by"]
    assert old_records[0]["created_by"] == "alice"
    assert fresh.output_fields[-1] == ["uri", "created_by"]
    assert new_records[0]["created_by"] == "bob"


def test_context_reads_legacy_uploaded_by():
    ctx = Context.from_dict({"uri": "viking://resources/x/a.py", "uploaded_by": "alice"})

    assert ctx.created_by == "alice"
    assert ctx.to_dict()["created_by"] == "alice"
    assert "uploaded_by" not in ctx.to_dict()
