# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0

import sys
import types
from types import SimpleNamespace

import pytest
from starlette.responses import PlainTextResponse

from openviking.server.config import ServerConfig
from openviking.service.builtin_skills import (
    BUILTIN_SKILLS_ROOT,
    bundled_skills,
    install_builtin_skills,
)
from openviking_cli.session.user_id import UserIdentifier

BUNDLED = [
    "daily-report",
    "knowledge-distillation",
    "knowledge-graph",
    "llm-wiki",
    "ov-session-report",
]


@pytest.fixture(autouse=True)
def _stub_mcp_endpoint(monkeypatch):
    """Keep these router tests independent from the optional MCP package."""
    module = types.ModuleType("openviking.server.mcp_endpoint")

    def create_mcp_app():
        async def _endpoint(_request):
            return PlainTextResponse("mcp stub")

        return _endpoint

    module.create_mcp_app = create_mcp_app
    monkeypatch.setitem(sys.modules, "openviking.server.mcp_endpoint", module)


async def _agent_skill_names(client) -> set[str]:
    response = await client.get("/api/v1/skills")
    assert response.status_code == 200, response.text
    return {
        skill["name"]
        for skill in response.json()["result"]["skills"]
        if skill["uri"].startswith(f"{BUILTIN_SKILLS_ROOT}/")
    }


def test_bundled_skills_ship_with_the_package():
    skills = bundled_skills()
    assert [name for name, _ in skills] == BUNDLED
    for name, content in skills:
        assert content.startswith("---\n")
        assert f"name: {name}\n" in content


async def test_installs_every_bundled_skill_once(client, service):
    account_id = service.user.account_id
    assert await install_builtin_skills(service, account_id) == BUNDLED
    assert await _agent_skill_names(client) == set(BUNDLED)

    # Idempotent: a second pass (e.g. the next server start) installs nothing.
    assert await install_builtin_skills(service, account_id) == []


async def test_keeps_an_existing_skill_with_the_same_name(client, service):
    custom = "---\nname: llm-wiki\ndescription: Team's own wiki Skill\n---\n\n# Custom\n"
    response = await client.post(
        "/api/v1/skills",
        json={"data": custom, "target_uri": BUILTIN_SKILLS_ROOT, "wait": True},
    )
    assert response.status_code == 200, response.text

    installed = await install_builtin_skills(service, service.user.account_id)

    assert "llm-wiki" not in installed
    detail = await client.get(
        "/api/v1/skills/llm-wiki",
        params={"target_uri": BUILTIN_SKILLS_ROOT, "include_content": True},
    )
    assert detail.status_code == 200, detail.text
    assert "# Custom" in detail.json()["result"]["content"]


async def test_does_not_bring_back_a_deleted_built_in(client, service):
    account_id = service.user.account_id
    # Wait out semantic processing; it holds the skill's path lock meanwhile.
    await install_builtin_skills(service, account_id, wait=True)
    deleted = await client.delete(
        "/api/v1/skills/llm-wiki", params={"target_uri": BUILTIN_SKILLS_ROOT}
    )
    assert deleted.status_code == 200, deleted.text

    assert await install_builtin_skills(service, account_id) == []
    assert "llm-wiki" not in await _agent_skill_names(client)


async def test_account_creation_respects_the_config_switch(monkeypatch):
    from openviking.server.routers import admin

    calls: list[str] = []

    async def fake_install(_service, account_id):
        calls.append(account_id)
        return []

    monkeypatch.setattr("openviking.service.builtin_skills.install_builtin_skills", fake_install)

    monkeypatch.setattr(
        "openviking.server.dependencies.get_server_config",
        lambda: ServerConfig(builtin_skills=False),
    )
    await admin._install_builtin_skills(object(), "acme")
    assert calls == []

    monkeypatch.setattr("openviking.server.dependencies.get_server_config", lambda: ServerConfig())
    await admin._install_builtin_skills(object(), "acme")
    assert calls == ["acme"]


async def test_account_creation_survives_an_install_failure(monkeypatch):
    from openviking.server.routers import admin

    async def broken_install(_service, _account_id):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr("openviking.service.builtin_skills.install_builtin_skills", broken_install)
    monkeypatch.setattr("openviking.server.dependencies.get_server_config", lambda: ServerConfig())

    await admin._install_builtin_skills(object(), "acme")


def test_startup_covers_every_live_account():
    from openviking.server.app import _builtin_skill_account_ids

    class Manager:
        def get_accounts(self):
            return [
                {"account_id": "default", "status": "active"},
                {"account_id": "acme", "status": "active"},
                {"account_id": "leaving", "status": "deleting"},
            ]

    service = SimpleNamespace(user=UserIdentifier("default", "default"))
    app = SimpleNamespace(state=SimpleNamespace(api_key_manager=Manager()))
    assert _builtin_skill_account_ids(app, service) == ["default", "acme"]

    dev_app = SimpleNamespace(state=SimpleNamespace(api_key_manager=None, auth_plugin=None))
    assert _builtin_skill_account_ids(dev_app, service) == ["default"]
