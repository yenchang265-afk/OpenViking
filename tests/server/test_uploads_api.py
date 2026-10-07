# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""HTTP API for chunked upload sessions, end to end through add_resource."""

import httpx
import pytest

from openviking.server.config import TempUploadConfig, UploadConfig

MIB = 1024 * 1024


@pytest.fixture
def small_parts(app):
    app.state.config.upload = UploadConfig(
        max_file_bytes=4 * MIB, max_session_bytes=8 * MIB, max_files=10, part_size_bytes=MIB
    )


async def _create(client, kind, name, files):
    resp = await client.post(
        "/api/v1/uploads",
        json={"kind": kind, "name": name, "files": [{"path": p, "size": len(d)} for p, d in files]},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["result"]


async def _send_all(client, upload_id, files, part_size=MIB):
    for index, (_, data) in enumerate(files):
        for n in range(1, -(-len(data) // part_size) + 1):
            resp = await client.put(
                f"/api/v1/uploads/{upload_id}/files/{index}/parts/{n}",
                content=data[(n - 1) * part_size : n * part_size],
                headers={"Content-Type": "application/octet-stream"},
            )
            assert resp.status_code == 200, resp.text


async def test_folder_session_ingests_like_a_zip_upload(
    client: httpx.AsyncClient, upload_temp_dir, small_parts
):
    files = [("bb/readme.md", b"# hello\n"), ("bb/notes/n.txt", b"x" * (MIB + 5))]
    created = await _create(client, "directory", "tt_b", files)
    await _send_all(client, created["upload_id"], files)

    status = await client.get(f"/api/v1/uploads/{created['upload_id']}")
    assert [f["received_parts"] for f in status.json()["result"]["files"]] == [[1], [1, 2]]
    done = await client.post(f"/api/v1/uploads/{created['upload_id']}/complete")
    temp_file_id = done.json()["result"]["temp_file_id"]

    resp = await client.post(
        "/api/v1/resources",
        json={
            "temp_file_id": temp_file_id,
            "to": "viking://resources",
            "reason": "chunked folder",
            "wait": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["result"]["root_uri"] == "viking://resources/tt_b"


async def test_file_session_ingests_single_file(
    client: httpx.AsyncClient, upload_temp_dir, small_parts
):
    files = [("guide.md", b"# Guide\n\n" + b"body " * 300_000)]
    created = await _create(client, "file", "guide.md", files)
    await _send_all(client, created["upload_id"], files)
    done = await client.post(f"/api/v1/uploads/{created['upload_id']}/complete")

    resp = await client.post(
        "/api/v1/resources",
        json={
            "temp_file_id": done.json()["result"]["temp_file_id"],
            "reason": "chunked file",
            "wait": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"


async def test_oversized_part_is_413_and_bad_requests_are_4xx(
    client: httpx.AsyncClient, upload_temp_dir, small_parts
):
    created = await _create(client, "file", "f.bin", [("f.bin", b"x" * (MIB + 1))])
    upload_id = created["upload_id"]

    too_big = await client.put(
        f"/api/v1/uploads/{upload_id}/files/0/parts/1", content=b"x" * (MIB + 1)
    )
    assert too_big.status_code == 413
    out_of_range = await client.put(f"/api/v1/uploads/{upload_id}/files/0/parts/9", content=b"x")
    assert out_of_range.status_code == 400
    traversal = await client.post(
        "/api/v1/uploads",
        json={"kind": "directory", "name": "d", "files": [{"path": "../x", "size": 1}]},
    )
    assert traversal.status_code == 400
    oversized_file = await client.post(
        "/api/v1/uploads",
        json={"kind": "file", "name": "big", "files": [{"path": "big", "size": 4 * MIB + 1}]},
    )
    assert oversized_file.status_code == 413
    unknown = await client.get("/api/v1/uploads/" + "0" * 32)
    assert unknown.status_code == 404


async def test_abort_deletes_session(client: httpx.AsyncClient, upload_temp_dir, small_parts):
    created = await _create(client, "file", "f.bin", [("f.bin", b"abc")])

    resp = await client.delete(f"/api/v1/uploads/{created['upload_id']}")

    assert resp.status_code == 200
    assert (await client.get(f"/api/v1/uploads/{created['upload_id']}")).status_code == 404


async def test_sessions_are_refused_in_shared_mode(client: httpx.AsyncClient, upload_temp_dir, app):
    app.state.config.temp_upload = TempUploadConfig(default_mode="shared")

    resp = await client.post(
        "/api/v1/uploads",
        json={"kind": "file", "name": "f.bin", "files": [{"path": "f.bin", "size": 1}]},
    )

    assert resp.status_code == 409
