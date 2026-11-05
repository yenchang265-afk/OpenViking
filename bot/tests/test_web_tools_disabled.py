"""Web tools must stay unregistered unless tools.web.enabled is set."""

from vikingbot.agent.tools.factory import register_default_tools
from vikingbot.agent.tools.registry import ToolRegistry
from vikingbot.config.schema import Config


def _tool_names(config: Config) -> set[str]:
    registry = ToolRegistry()
    register_default_tools(
        registry,
        config,
        include_image_tool=False,
        include_viking_tools=False,
    )
    return set(registry.tool_names)


def test_web_tools_disabled_by_default():
    names = _tool_names(Config())
    assert "web_search" not in names
    assert "web_fetch" not in names


def test_web_tools_registered_when_enabled():
    config = Config()
    config.tools.web.enabled = True
    names = _tool_names(config)
    assert {"web_search", "web_fetch"} <= names


def test_default_skills_exclude_external_network_skills():
    skills = Config().skills
    for name in ("github-proxy", "github", "weather", "summarize"):
        assert name not in skills
