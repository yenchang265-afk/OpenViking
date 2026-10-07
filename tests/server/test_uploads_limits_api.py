# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""GET /api/v1/uploads/limits serves the server's own upload limits to clients."""

import httpx

from openviking.server.config import UploadConfig

MIB = 1024 * 1024


async def test_upload_limits_endpoint_returns_configured_limits(
    client: httpx.AsyncClient, app
) -> None:
    app.state.config.upload = UploadConfig(
        max_file_bytes=100 * MIB,
        max_session_bytes=300 * MIB,
        max_files=50,
        part_size_bytes=4 * MIB,
    )

    resp = await client.get("/api/v1/uploads/limits")

    assert resp.status_code == 200
    assert resp.json() == {
        "status": "ok",
        "result": {
            "max_file_bytes": 100 * MIB,
            "max_session_bytes": 300 * MIB,
            "max_files": 50,
            "part_size_bytes": 4 * MIB,
        },
    }


async def test_upload_limits_endpoint_defaults(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/uploads/limits")

    assert resp.status_code == 200
    assert resp.json()["result"]["max_file_bytes"] == 2048 * MIB
