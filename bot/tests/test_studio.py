"""Studio connection persistence, isolation and gateway boundaries."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from vikingbot.studio.providers.registry import PROVIDERS, get_provider
from vikingbot.studio.service import StudioService
from vikingbot.studio.store import StudioStore


class FakeProvider:
    type = "fake"

    def runtime_key(self, record):
        return "fake__" + record["app_id"]

    def public_fields(self, record):
        return {"app_id": record.get("app_id")}

    async def credentials(self, record, body):
        return {**record, "app_secret": body["app_secret"]}


@pytest.fixture(autouse=True)
def fake_provider(monkeypatch):
    monkeypatch.setitem(PROVIDERS, FakeProvider.type, FakeProvider())


def record():
    return {
        "id": "connection",
        "account": "a",
        "type": "fake",
        "app_id": "cli_test",
        "app_secret": "secret",
        "bot_name": "Bot",
        "enabled": True,
        "revision": 1,
        "step": 2,
        "identity": {"user_id": "group-user", "api_key": "private", "role": "user"},
    }


def test_store_survives_restart_deduplicates_and_paginates(tmp_path):
    path = tmp_path / "studio.db"
    store = StudioStore(path)
    store.save(record())
    for i in range(105):
        store.append(
            "connection",
            "group",
            str(i),
            {
                "content": str(i),
                "title": "Team",
                "chat_type": "group",
            },
        )
    store.append("connection", "group", "0", {"content": "duplicate"})
    reloaded = StudioStore(path)
    assert reloaded.connections("b") == []
    assert reloaded.connections("a")[0]["id"] == "connection"
    page = reloaded.history("connection", "group")
    assert len(page) == 101
    assert page[0]["content"] == "104"
    assert len(reloaded.history("connection", "group", page[99]["id"])) == 5
    assert reloaded.conversations("connection")[0]["title"] == "0"
    assert reloaded.conversations("connection")[0]["group_name"] == "Team"
    store.append(
        "connection",
        "group#topic",
        "topic",
        {
            "role": "user",
            "content": "First question",
            "chat_type": "group",
            "title": "Team / First question",
            "topic_title": "Release plan",
        },
    )
    topic = reloaded.conversations("connection")[0]
    assert topic["title"] == "Release plan"
    assert topic["group_name"] == "Team"
    assert path.stat().st_mode & 0o777 == 0o600


def test_public_config_never_returns_credentials_and_filters_accounts(tmp_path):
    manager = SimpleNamespace(channels={})
    config = SimpleNamespace(bot_data_path=tmp_path)
    service = StudioService(config, manager)
    service.store.save(record())
    public = service.public(record())
    assert "secret" not in str(public)
    assert "private" not in str(public)
    with pytest.raises(HTTPException) as error:
        service.get("other-account", "connection")
    assert error.value.status_code == 404


async def test_private_gateway_rejects_loopback_without_secret(tmp_path, monkeypatch):
    import httpx
    from fastapi import FastAPI
    from vikingbot.studio.router import create_router

    monkeypatch.delenv("OPENVIKING_BOT_STUDIO_TOKEN", raising=False)
    channel = SimpleNamespace(
        _gateway_token=lambda: "internal", _is_loopback_request=lambda r: True
    )
    service = StudioService(SimpleNamespace(bot_data_path=tmp_path), SimpleNamespace(channels={}))
    app = FastAPI()
    app.include_router(create_router(channel, service))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for token in ["", "wrong"]:
            response = await client.post(
                "/studio/dispatch",
                headers={"X-Gateway-Token": token},
                json={"account": "a", "action": "list"},
            )
            assert response.status_code == 403
        response = await client.post(
            "/studio/dispatch",
            headers={"X-Gateway-Token": "internal"},
            json={"account": "a", "action": "list"},
        )
        assert response.status_code == 200


async def test_failed_secret_rotation_preserves_old_connection(tmp_path, monkeypatch):
    service = StudioService(SimpleNamespace(bot_data_path=tmp_path), SimpleNamespace(channels={}))
    service.store.save(record())
    monkeypatch.setattr(
        get_provider(record()), "credentials", AsyncMock(side_effect=HTTPException(400, "Invalid"))
    )
    with pytest.raises(HTTPException):
        await service.update(
            "a", "connection", {"revision": 1, "action": "credentials", "app_secret": "wrong"}
        )
    assert service.get("a", "connection")["app_secret"] == "secret"
    assert service.get("a", "connection")["enabled"]


def test_unknown_or_missing_platform_is_rejected():
    for value in ({}, {"type": "unknown"}):
        with pytest.raises(HTTPException) as error:
            get_provider(value)
        assert error.value.status_code == 400


def test_managed_group_tools_deny_local_and_unregistered_capabilities():
    from vikingbot.studio.policy import disabled_group_tools

    assert disabled_group_tools(
        ["openviking_search", "exec", "read_file", "mcp_admin", "spawn"]
    ) == ["exec", "read_file", "mcp_admin", "spawn"]


async def test_delete_connection_stops_runtime_and_cleans_owned_data(tmp_path):
    service = StudioService(SimpleNamespace(bot_data_path=tmp_path), SimpleNamespace(channels={}))
    item = record()
    service.store.save(item)
    service.store.save({**item, "id": "other", "account": "b"})
    service.store.append(item["id"], "group", "event", {"content": "hello"})
    runtime = SimpleNamespace(stop=AsyncMock())
    key = get_provider(item).runtime_key(item)
    service.manager.channels[key] = runtime
    with pytest.raises(HTTPException) as error:
        await service.update("b", item["id"], {"action": "delete", "revision": 1})
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        await service.update("a", item["id"], {"action": "delete", "revision": 0})
    assert error.value.status_code == 409
    runtime.stop.assert_not_awaited()
    assert await service.update("a", item["id"], {"action": "delete", "revision": 1}) == {
        "deleted": True
    }
    runtime.stop.assert_awaited_once()
    assert key not in service.manager.channels
    assert service.store.connections("a") == []
    assert len(service.store.connections("b")) == 1
    assert service.store.history(item["id"]) == []
