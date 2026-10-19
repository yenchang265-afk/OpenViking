# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0

"""Tests for the /studio mount (openviking/server/app.py).

The docker `all-in-one` image locates Studio through OPENVIKING_WEB_STUDIO_DIR,
and the `server` image ships no bundle, so both paths must keep working.
"""

from pathlib import Path

import httpx

from openviking.server.app import create_app
from openviking.server.config import ServerConfig


def _write_bundle(dist: Path) -> None:
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>studio</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('studio')", encoding="utf-8")


async def _get(app, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(path, follow_redirects=False)


async def test_studio_served_from_env_dir(tmp_path: Path, monkeypatch):
    dist = tmp_path / "dist"
    _write_bundle(dist)
    monkeypatch.setenv("OPENVIKING_WEB_STUDIO_DIR", str(dist))
    app = create_app(config=ServerConfig())

    root = await _get(app, "/")
    assert root.status_code == 302
    assert root.headers["location"] == "/studio/"

    deep_link = await _get(app, "/studio/resources/some/route")
    assert deep_link.status_code == 200
    assert deep_link.text == "<html>studio</html>"
    assert deep_link.headers["cache-control"] == "no-store"

    asset = await _get(app, "/studio/assets/app.js")
    assert asset.status_code == 200
    assert asset.text == "console.log('studio')"

    escape = await _get(app, "/studio/..%2F..%2Fetc%2Fpasswd")
    assert escape.text == "<html>studio</html>"


async def test_studio_routes_skipped_without_bundle(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENVIKING_WEB_STUDIO_DIR", str(tmp_path / "missing"))
    app = create_app(config=ServerConfig())

    assert (await _get(app, "/")).status_code == 404
    assert (await _get(app, "/studio/")).status_code == 404
    # Favicons do not depend on the Studio bundle.
    assert (await _get(app, "/favicon.ico")).status_code == 200
