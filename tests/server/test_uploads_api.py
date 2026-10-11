# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""HTTP API for chunked upload sessions, end to end through add_resource."""

import httpx
import pytest

from openviking.server.config import TempUploadConfig, UploadConfig
from openviking.server.identity import RequestContext, Role
from openviking_cli.session.user_id import UserIdentifier

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


@pytest.fixture
def shared_mode(app, small_parts):
    app.state.config.temp_upload = TempUploadConfig(default_mode="shared")


async def _ingest(client, temp_file_id, **body):
    resp = await client.post(
        "/api/v1/resources",
        json={"temp_file_id": temp_file_id, "reason": "chunked", "wait": True, **body},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["result"]


async def _ingested_tree(client, root_uri):
    tree = await client.get("/api/v1/fs/tree", params={"uri": root_uri, "output": "original"})
    assert tree.status_code == 200, tree.text
    return sorted(
        (entry["uri"].removeprefix(root_uri), entry["size"]) for entry in tree.json()["result"]
    )


async def test_shared_folder_session_ingests_like_a_local_one(
    client: httpx.AsyncClient, upload_temp_dir, small_parts, app
):
    files = [("readme.md", b"# hello\n"), ("notes/n.txt", b"x" * (MIB + 5))]
    trees = {}
    for mode in ("local", "shared"):
        app.state.config.temp_upload = TempUploadConfig(default_mode=mode)
        created = await _create(client, "directory", f"tt_{mode}", files)
        upload_id = created["upload_id"]
        await _send_all(client, upload_id, files)

        status = await client.get(f"/api/v1/uploads/{upload_id}")
        assert [f["received_parts"] for f in status.json()["result"]["files"]] == [[1], [1, 2]]
        done = await client.post(f"/api/v1/uploads/{upload_id}/complete")
        temp_file_id = done.json()["result"]["temp_file_id"]

        result = await _ingest(client, temp_file_id, to="viking://resources")
        assert result["root_uri"] == f"viking://resources/tt_{mode}"
        trees[mode] = await _ingested_tree(client, result["root_uri"])

    assert temp_file_id == f"shared_{upload_id}"
    assert trees["shared"] == trees["local"]
    paths = [path for path, _ in trees["shared"]]
    assert "/readme/readme.md" in paths
    assert any(path.startswith("/notes/n/") for path in paths)  # the 2-part file, split


async def test_shared_file_session_ingests_single_file(
    client: httpx.AsyncClient, upload_temp_dir, shared_mode
):
    body = b"# Guide\n\n" + b"body " * 300_000
    created = await _create(client, "file", "guide.md", [("guide.md", body)])
    await _send_all(client, created["upload_id"], [("guide.md", body)])
    done = await client.post(f"/api/v1/uploads/{created['upload_id']}/complete")

    result = await _ingest(client, done.json()["result"]["temp_file_id"])
    assert result["root_uri"].endswith("guide.md") or "guide" in result["root_uri"]


async def test_shared_session_lives_in_shared_storage_only(
    client: httpx.AsyncClient, upload_temp_dir, shared_mode, service
):
    """Nothing is staged on the receiving server's disk, so any replica can continue."""
    files = [("a.md", b"# a\n" * 1000)]
    created = await _create(client, "file", "a.md", files)
    upload_id = created["upload_id"]
    await _send_all(client, upload_id, files)
    await client.post(f"/api/v1/uploads/{upload_id}/complete")

    assert not (upload_temp_dir / "sessions").exists()
    bucket, leaf = upload_id.split("-")
    root = f"viking://upload/{bucket}/{leaf}"
    ctx = RequestContext(user=UserIdentifier.the_default_user(), role=Role.ROOT)
    names = {e["name"] for e in await service.viking_fs.ls(root, show_all_hidden=True, ctx=ctx)}
    assert {"session.json", "parts", "meta"} <= names


async def test_shared_session_resumes_and_refuses_missing_parts(
    client: httpx.AsyncClient, upload_temp_dir, shared_mode
):
    data = b"y" * (MIB + 10)
    created = await _create(client, "file", "y.bin", [("y.bin", data)])
    upload_id = created["upload_id"]
    resp = await client.put(f"/api/v1/uploads/{upload_id}/files/0/parts/2", content=data[MIB:])
    assert resp.status_code == 200, resp.text

    status = await client.get(f"/api/v1/uploads/{upload_id}")
    assert status.json()["result"]["files"][0]["received_parts"] == [2]
    incomplete = await client.post(f"/api/v1/uploads/{upload_id}/complete")
    assert incomplete.status_code == 400
    assert "missing parts" in incomplete.json()["error"]["message"]

    resp = await client.put(f"/api/v1/uploads/{upload_id}/files/0/parts/1", content=data[:MIB])
    assert resp.status_code == 200, resp.text
    done = await client.post(f"/api/v1/uploads/{upload_id}/complete")
    assert done.status_code == 200, done.text
    again = await client.post(f"/api/v1/uploads/{upload_id}/complete")
    assert again.json()["result"] == done.json()["result"]
    late = await client.put(f"/api/v1/uploads/{upload_id}/files/0/parts/1", content=data[:MIB])
    assert late.status_code == 400


async def test_shared_session_limits_and_abort(
    client: httpx.AsyncClient, upload_temp_dir, shared_mode
):
    created = await _create(client, "file", "f.bin", [("f.bin", b"x" * (MIB + 1))])
    upload_id = created["upload_id"]

    too_big = await client.put(
        f"/api/v1/uploads/{upload_id}/files/0/parts/1", content=b"x" * (MIB + 1)
    )
    assert too_big.status_code == 413
    short = await client.put(f"/api/v1/uploads/{upload_id}/files/0/parts/1", content=b"x")
    assert short.status_code == 400
    unknown = await client.get("/api/v1/uploads/2026010100-" + "0" * 32)
    assert unknown.status_code == 404

    assert (await client.delete(f"/api/v1/uploads/{upload_id}")).status_code == 200
    assert (await client.get(f"/api/v1/uploads/{upload_id}")).status_code == 404


async def test_local_session_finishes_after_switching_to_shared(
    client: httpx.AsyncClient, upload_temp_dir, small_parts, app
):
    files = [("keep.md", b"# keep\n")]
    created = await _create(client, "file", "keep.md", files)
    app.state.config.temp_upload = TempUploadConfig(default_mode="shared")

    await _send_all(client, created["upload_id"], files)
    done = await client.post(f"/api/v1/uploads/{created['upload_id']}/complete")

    assert done.status_code == 200, done.text
    assert done.json()["result"]["temp_file_id"].startswith("session_")
