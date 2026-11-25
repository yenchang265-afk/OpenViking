# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0

"""Tests for server infrastructure: health, system status, middleware, error handling."""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from openviking.server.app import create_app
from openviking.server.config import ServerConfig
from openviking.server.runtime import ServerRuntime
from openviking.server.runtime import initialize_auth_plugin as _initialize_auth_plugin
from openviking.service.core import OpenVikingService
from openviking_cli.utils.config.open_viking_config import (
    OpenVikingConfig,
    OpenVikingConfigSingleton,
)


async def test_health_endpoint(client: httpx.AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


async def test_health_endpoint_checks_supplied_api_key_without_requiring_it(service):
    key = "test-root-key"
    config = ServerConfig(auth_mode="api_key", host="127.0.0.1", root_api_key=key)
    app = create_app(config=config, service=service)
    await _initialize_auth_plugin(app, service, config)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            anonymous = await client.get("/health")
            assert anonymous.status_code == 200
            assert anonymous.json()["auth_mode"] == "api_key"
            assert anonymous.json()["healthy"] is True
            assert {"account_id", "user_id", "role"}.isdisjoint(anonymous.json())

            authenticated = await client.get("/health", headers={"X-API-Key": key})
            assert authenticated.status_code == 200
            identity = authenticated.json()
            assert (identity["account_id"], identity["user_id"], identity["role"]) == (
                "default",
                "default",
                "root",
            )

            rejected = await client.get("/health", headers={"X-API-Key": "stale-key"})
            assert rejected.status_code == 401
            assert rejected.json()["error"] == {
                "code": "UNAUTHENTICATED",
                "message": "Invalid API key format",
                "details": {},
            }
    finally:
        await app.state.auth_plugin.shutdown()


@pytest.mark.parametrize(
    "credentials",
    [
        "anonymous",
        "partial",
        "trusted",
        "keyed",
        "malformed",
        "asserted-root",
        "root-only",
        "invalid-root-only",
    ],
)
async def test_health_trusted_identity_contract(credentials, service):
    app = create_app(
        config=ServerConfig(auth_mode="trusted", host="127.0.0.1", root_api_key="test-root-key"),
        service=service,
    )
    await _initialize_auth_plugin(app, service, app.state.config)
    headers = {}
    if credentials not in ("anonymous", "root-only", "invalid-root-only"):
        headers["X-OpenViking-Account"] = "account-a"
    if credentials in ("trusted", "keyed", "malformed", "asserted-root"):
        headers["X-OpenViking-User"] = "alice"
    if credentials in ("keyed", "malformed", "asserted-root", "root-only"):
        headers["X-API-Key"] = "test-root-key"
    if credentials == "invalid-root-only":
        headers["X-API-Key"] = "invalid-key"
    if credentials == "malformed":
        headers["X-OpenViking-User"] = "alice/../root"
    if credentials == "asserted-root":
        headers["X-OpenViking-Role"] = "root"
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health", headers=headers)
    finally:
        await app.state.auth_plugin.shutdown()
    body = response.json()
    expected_status = 401 if credentials in ("trusted", "invalid-root-only") else 200
    assert response.status_code == expected_status
    if expected_status == 401:
        assert body["error"]["code"] == "UNAUTHENTICATED"
        return
    if credentials == "keyed":
        assert (body["account_id"], body["user_id"], body["role"]) == ("account-a", "alice", "user")
    elif credentials == "root-only":
        assert body["role"] == "root"
    else:
        assert "role" not in body
    assert body["root_api_key_required"] is True
    if credentials == "malformed":
        assert {"account_id", "user_id", "role"}.isdisjoint(body)


@pytest.mark.parametrize("roles", [["api"], ["queue_worker"], ["scheduler"]])
async def test_system_status(app, roles):
    node = create_app(config=ServerConfig(roles=roles))
    node.state.auth_plugin = app.state.auth_plugin
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=node), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/system/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["result"]["initialized"] is True


@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("POST", "/api/v1/system/backend/sync-status", {"uri": "viking://resources"}),
        ("POST", "/api/v1/system/backend/sync-retry", {"uri": "viking://resources"}),
        ("GET", "/api/v1/system/sync/viking://resources", None),
        ("POST", "/api/v1/system/sync/viking://resources/retry", None),
    ],
)
async def test_removed_sync_routes_return_404(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    json: dict | None,
):
    """Removed V1 sync routes must stay unregistered."""
    resp = await client.request(method, path, json=json)
    assert resp.status_code == 404


async def test_process_time_header(client: httpx.AsyncClient):
    resp = await client.get("/health")
    assert "x-process-time" in resp.headers
    value = float(resp.headers["x-process-time"])
    assert value >= 0


async def test_openviking_error_handler(client: httpx.AsyncClient):
    """Requesting a non-existent resource should return structured error."""
    resp = await client.get(
        "/api/v1/fs/stat", params={"uri": "viking://resources/nonexistent/path"}
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] is not None


@pytest.mark.parametrize("roles", [["queue_worker"], ["scheduler"]])
async def test_non_api_route_access(roles):
    app = create_app(config=ServerConfig(roles=roles))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for path in (
            "/this/route/does/not/exist",
            "/api/v1/tasks",
            "/api/v1/admin/ttl/configuration",
            "/mcp",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/studio",
            "/gateway/v1/models",
            "/authorize",
            "/favicon.ico",
        ):
            assert (await client.get(path)).status_code == 404, path
        assert (await client.get("/api/v1/system/status")).status_code == 401
        assert (await client.post("/api/v1/system/wait", json={})).status_code == 401
        assert (
            await client.post("/api/v1/system/consistency", json={"uri": "viking://resources"})
        ).status_code == 401


async def test_lifespan_retains_account_store_when_service_close_cancelled(monkeypatch):
    service = Mock(spec=OpenVikingService, _initialized=False)
    service.stop_background = AsyncMock(side_effect=asyncio.CancelledError("shutdown"))
    monkeypatch.setattr(ServerRuntime, "start", AsyncMock())
    monkeypatch.setattr(OpenVikingConfigSingleton, "_instance", OpenVikingConfig.from_dict({}))
    app = create_app(config=ServerConfig(), service=service)
    app.state.auth_plugin = SimpleNamespace(shutdown=AsyncMock())

    with pytest.raises(asyncio.CancelledError, match="shutdown"):
        async with app.router.lifespan_context(app):
            pass
    app.state.auth_plugin.shutdown.assert_not_awaited()
    service.release_storage.assert_not_called()


@pytest.mark.parametrize(
    "roles, enable_default_resources, explicit_cluster_resources",
    [
        (["api"], True, False),
        (["api"], False, False),
        (["queue_worker"], False, True),
        (["scheduler"], False, False),
    ],
)
async def test_readiness_tracks_startup_and_filesystem_health(
    monkeypatch, enable_default_resources, explicit_cluster_resources, roles
):
    filesystem = SimpleNamespace(
        ls=AsyncMock(return_value=[]),
        agfs=SimpleNamespace(ls=Mock(return_value=[])),
        _get_vector_store=lambda: SimpleNamespace(health_check=AsyncMock(return_value=True)),
    )
    values = {"enable_default_resources": enable_default_resources}
    if explicit_cluster_resources:
        values["storage"] = {"vectordb": {"backend": "local"}}
    config = OpenVikingConfig.from_dict(values)
    service = SimpleNamespace(
        _initialized=False,
        _config=config,
        embedding_provider=object(),
    )
    monkeypatch.setattr(OpenVikingConfigSingleton, "_instance", config)
    monkeypatch.setattr("openviking.server.dependencies._service", service)
    monkeypatch.setattr("openviking.server.routers.system.get_viking_fs", lambda: filesystem)
    monkeypatch.setattr(
        "openviking_cli.utils.ollama.detect_ollama_in_config",
        lambda config: (False, None, None),
    )

    app = create_app(config=ServerConfig(roles=roles), service=service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        liveness = await client.get("/health")
        assert liveness.status_code == 200
        assert liveness.json()["healthy"] is True
        initializing = await client.get("/ready")
        assert initializing.status_code == 503
        assert initializing.json() == {"status": "not_ready", "reason": "initializing"}
        filesystem.ls.assert_not_awaited()

        service._initialized = True
        ready = await client.get("/ready")
        assert ready.status_code == 200
        assert ready.json() == {
            "status": "ready",
            "checks": {
                "agfs": {"status": "ok", "checks": {"filesystem": "ok"}},
                "api_key_manager": "not_configured",
                # Fork: PathLock/QueueFS cache probe (no cache backends here).
                "cache": "not_configured",
                "embedding": "ok",
                **({"ollama": "not_configured"} if enable_default_resources else {}),
                "vectordb": "ok" if config.storage.vectordb is not None else "not_configured",
            },
        }

        if enable_default_resources:
            filesystem.ls.side_effect = OSError("storage unavailable")
        else:
            filesystem.agfs.ls.side_effect = OSError("storage unavailable")
        unavailable = await client.get("/ready")
        assert unavailable.status_code == 503
        assert unavailable.json()["status"] == "not_ready"
        assert unavailable.json()["checks"]["agfs"] == {
            "status": "error",
            "checks": {"filesystem": "error"},
        }
        assert (await client.get("/health")).status_code == 200


async def test_slow_init_does_not_block_health(monkeypatch):
    """Health endpoint responds quickly even when initialization is slow."""

    # Health is stateless — it doesn't call get_service() or depend on _initialized
    class MockService:
        _initialized = False

    service = MockService()
    monkeypatch.setattr("openviking.server.dependencies._service", service)

    app = create_app(config=ServerConfig(), service=service)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start = time.perf_counter()
        resp = await client.get("/health")
        elapsed = time.perf_counter() - start

        assert resp.status_code == 200
        # Health responds instantly since it's stateless (no service dependency)
        assert elapsed < 0.5


# Fork additions: readiness probe timeouts and cache-backend probes.
def _ready_app(monkeypatch, viking_fs, storage=None, **server_config):
    """Create an app whose readiness dependencies are initialized mocks."""

    class MockService:
        _initialized = True
        embedding_provider = object()
        # Readiness probes the cluster vector store only when one is configured.
        _config = SimpleNamespace(
            enable_default_resources=True, storage=SimpleNamespace(vectordb=object())
        )

    service = MockService()
    monkeypatch.setattr("openviking.server.dependencies._service", service)
    monkeypatch.setattr("openviking.server.routers.system.get_viking_fs", lambda: viking_fs)
    monkeypatch.setattr(
        "openviking_cli.utils.ollama.detect_ollama_in_config",
        lambda config: (False, None, None),
    )
    app = create_app(config=ServerConfig(**server_config), service=service)
    # Patched after create_app, which reads the real config singleton.
    monkeypatch.setattr(
        "openviking_cli.utils.config.open_viking_config.OpenVikingConfigSingleton.get_instance",
        lambda: SimpleNamespace(
            embedding=SimpleNamespace(get_embedder=lambda: None), storage=storage
        ),
    )
    return app


def _cache_storage(*, pathlock="cache", queuefs="cache"):
    return SimpleNamespace(
        agfs=SimpleNamespace(
            pathlock=SimpleNamespace(provider=pathlock),
            queuefs=SimpleNamespace(backend=queuefs),
        )
    )


class _CacheBackedVikingFS:
    """VikingFS whose PathLock and queue registry round-trip through a cache provider."""

    def __init__(self, error=None):
        self.error = error
        self.calls = []
        fs = self

        class _Agfs:
            async def pathlock_is_locked(self, path, ignore_stale=True, *, fs_ctx=None):
                fs.calls.append(("pathlock_is_locked", path))
                if fs.error is not None:
                    raise fs.error
                return False

            async def ls(self, path, *args, **kwargs):
                fs.calls.append(("ls", path))
                if fs.error is not None:
                    raise fs.error
                return []

        self._async_agfs = _Agfs()

    async def ls(self, path, ctx=None):
        return []

    def _get_vector_store(self):
        class MockVectorStore:
            async def health_check(self):
                return True

        return MockVectorStore()


async def test_ready_probes_cache_backed_pathlock_and_queue(monkeypatch):
    viking_fs = _CacheBackedVikingFS()
    app = _ready_app(monkeypatch, viking_fs, storage=_cache_storage())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/ready")

    assert resp.status_code == 200
    assert resp.json()["checks"]["cache"] == {
        "status": "ok",
        "checks": {"pathlock": "ok", "queue": "ok"},
    }
    assert ("pathlock_is_locked", "/") in viking_fs.calls
    assert ("ls", "/queue") in viking_fs.calls


async def test_ready_returns_503_when_cache_provider_is_unreachable(monkeypatch):
    error = RuntimeError("cache queue_exists: Redis SISMEMBER: Timeout Error")
    app = _ready_app(monkeypatch, _CacheBackedVikingFS(error), storage=_cache_storage())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/ready")

    assert resp.status_code == 503
    cache = resp.json()["checks"]["cache"]
    assert cache["status"] == "error"
    assert "Redis SISMEMBER" in cache["checks"]["pathlock"]


async def test_ready_skips_cache_probe_without_cache_backends(monkeypatch):
    viking_fs = _CacheBackedVikingFS()
    storage = _cache_storage(pathlock="filesystem", queuefs="sqlite")
    app = _ready_app(monkeypatch, viking_fs, storage=storage)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/ready")

    assert resp.status_code == 200
    assert resp.json()["checks"]["cache"] == "not_configured"
    assert viking_fs.calls == []


class _StalledVikingFS:
    """VikingFS whose storage calls block until released, like a hung S3 backend."""

    def __init__(self, *, stall_ls=True, stall_vector=False):
        self.release = asyncio.Event()
        self.ls_calls = 0
        self._stall_ls = stall_ls
        self._stall_vector = stall_vector

    async def ls(self, path, ctx=None):
        self.ls_calls += 1
        if self._stall_ls:
            await self.release.wait()
        return []

    def _get_vector_store(self):
        fs = self

        class MockVectorStore:
            async def health_check(self):
                if fs._stall_vector:
                    await fs.release.wait()
                return True

        return MockVectorStore()


async def test_ready_returns_503_when_filesystem_probe_stalls(monkeypatch):
    """A hung storage backend makes /ready fail fast instead of hanging the probe."""
    viking_fs = _StalledVikingFS()
    app = _ready_app(monkeypatch, viking_fs, ready_probe_timeout_seconds=0.2)
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            start = time.perf_counter()
            first = await client.get("/ready")
            second = await client.get("/ready")
            elapsed = time.perf_counter() - start

        assert first.status_code == 503
        assert second.status_code == 503
        assert "timed out" in first.json()["checks"]["agfs"]["checks"]["filesystem"]
        assert elapsed < 2.0
        # The second probe waits on the still-running first one instead of
        # stacking another blocked storage call.
        assert viking_fs.ls_calls == 1
    finally:
        viking_fs.release.set()
        await asyncio.sleep(0)


async def test_ready_returns_503_when_vectordb_probe_stalls(monkeypatch):
    viking_fs = _StalledVikingFS(stall_ls=False, stall_vector=True)
    app = _ready_app(monkeypatch, viking_fs, ready_probe_timeout_seconds=0.2)
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await asyncio.wait_for(client.get("/ready"), timeout=2.0)

        assert resp.status_code == 503
        assert "timed out" in resp.json()["checks"]["vectordb"]
    finally:
        viking_fs.release.set()
        await asyncio.sleep(0)
