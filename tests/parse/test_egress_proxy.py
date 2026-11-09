# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Admin-managed per-host egress proxies for parser network operations."""

import asyncio
import base64
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from openviking.parse.accessors.git_accessor import GitAccessor
from openviking.parse.egress_proxy import (
    EgressProxyAdapter,
    configure_egress_proxies,
    egress_proxy_host_for,
    parse_egress_proxies,
)
from openviking.parse.network import (
    ParserNetworkContext,
    ParserNetworkOperation,
    create_parser_httpx_client,
    open_parser_url,
    overlay_parser_subprocess_env,
    register_parser_network_adapter,
    reset_parser_network_adapter,
)
from openviking.service import core as service_core
from openviking.service.core import OpenVikingService
from openviking.utils.git_auth import GitHttpAuthConfig, build_git_http_auth_env
from openviking_cli.utils.config.parser_config import CodeConfig

ADO_REPO = "https://dev.azure.com/org/project/_git/repo"
SECRET = "pr0xy-s3cret"


@pytest.fixture(autouse=True)
def clean_adapter():
    configure_egress_proxies(SimpleNamespace(egress_proxies={}))
    reset_parser_network_adapter()
    yield
    configure_egress_proxies(SimpleNamespace(egress_proxies={}))
    reset_parser_network_adapter()


def _context(operation=ParserNetworkOperation.GIT_COMMAND, url=ADO_REPO):
    return ParserNetworkContext(operation, url)


def _adapter(**route):
    entry = {"url": "http://proxy.corp:8080", **route}
    return EgressProxyAdapter(parse_egress_proxies({"dev.azure.com": entry}))


@asynccontextmanager
async def _recording_proxy():
    """Local proxy that records each CONNECT head, then refuses the tunnel."""
    heads = []

    async def handle(reader, writer):
        heads.append((await reader.readuntil(b"\r\n\r\n")).decode("latin1"))
        writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}", heads
    finally:
        server.close()
        await server.wait_closed()


class TestParseEgressProxies:
    def test_empty_config_has_no_routes(self):
        assert parse_egress_proxies(None) == {}
        assert parse_egress_proxies({}) == {}

    def test_host_is_normalized(self):
        routes = parse_egress_proxies({"Dev.Azure.COM.": {"url": "http://proxy.corp:8080"}})
        assert set(routes) == {"dev.azure.com"}
        assert routes["dev.azure.com"].proxy_host == "proxy.corp:8080"

    @pytest.mark.parametrize(
        "host",
        ["https://dev.azure.com", "dev.azure.com/org", "*.azure.com", "dev.azure.com:443", ""],
    )
    def test_rejects_anything_but_a_bare_host(self, host):
        with pytest.raises(ValueError, match="host"):
            parse_egress_proxies({host: {"url": "http://proxy.corp:8080"}})

    @pytest.mark.parametrize(
        "url",
        [
            "socks5://proxy.corp:1080",
            "ftp://proxy.corp",
            "https://proxy.corp:443",
            "http://proxy.corp",
            "proxy.corp:8080",
            "http://",
            "http://proxy.corp:notaport",
            "http://proxy.corp:8080/path",
            "http://proxy.corp:8080?x=1",
            None,
        ],
    )
    def test_rejects_invalid_proxy_url(self, url):
        with pytest.raises(ValueError, match="url"):
            parse_egress_proxies({"dev.azure.com": {"url": url}})

    def test_rejects_credentials_in_url_without_echoing_them(self):
        with pytest.raises(ValueError, match="username") as error:
            parse_egress_proxies({"dev.azure.com": {"url": f"http://svc:{SECRET}@proxy.corp:8080"}})
        assert SECRET not in str(error.value)

    def test_rejects_unknown_field_so_typos_cannot_disable_auth(self):
        with pytest.raises(ValueError, match="pasword"):
            parse_egress_proxies(
                {"dev.azure.com": {"url": "http://proxy.corp:8080", "pasword": SECRET}}
            )

    def test_password_requires_username(self):
        with pytest.raises(ValueError, match="username"):
            parse_egress_proxies(
                {"dev.azure.com": {"url": "http://proxy.corp:8080", "password": SECRET}}
            )

    def test_rejects_missing_ca_file(self, tmp_path):
        with pytest.raises(ValueError, match="ca_file"):
            parse_egress_proxies(
                {
                    "dev.azure.com": {
                        "url": "http://proxy.corp:8080",
                        "ca_file": str(tmp_path / "missing.pem"),
                    }
                }
            )

    def test_rejects_non_object_config(self):
        with pytest.raises(ValueError, match="egress_proxies"):
            parse_egress_proxies(["dev.azure.com"])
        with pytest.raises(ValueError, match="dev.azure.com"):
            parse_egress_proxies({"dev.azure.com": "http://proxy.corp:8080"})

    def test_password_is_not_in_repr(self):
        routes = parse_egress_proxies(
            {
                "dev.azure.com": {
                    "url": "http://proxy.corp:8080",
                    "username": "svc",
                    "password": SECRET,
                }
            }
        )
        assert SECRET not in repr(routes)


def test_code_config_rejects_invalid_route_on_load():
    """The admin config editor validates through config load, before any restart."""
    with pytest.raises(ValueError, match="url"):
        CodeConfig.from_dict({"egress_proxies": {"dev.azure.com": {"url": "proxy.corp:8080"}}})


def test_code_config_loads_field_and_hides_it_from_repr():
    assert CodeConfig().egress_proxies == {}
    entry = {"url": "http://proxy.corp:8080", "username": "svc", "password": SECRET}
    config = CodeConfig.from_dict({"egress_proxies": {"dev.azure.com": entry}})
    assert config.egress_proxies["dev.azure.com"] == entry
    assert SECRET not in repr(config)


class TestSupports:
    @pytest.mark.parametrize(
        "source",
        [ADO_REPO, "https://org@dev.azure.com/org/project/_git/repo", "https://DEV.azure.com./x"],
    )
    def test_matches_configured_https_host(self, source):
        assert _adapter().supports(_context(url=source)) is True

    @pytest.mark.parametrize(
        "source",
        [
            "https://github.com/org/repo",
            "https://evil.dev.azure.com/x",
            "https://dev.azure.com.evil.example/x",
            "git@ssh.dev.azure.com:v3/org/project/repo",
            "ssh://git@dev.azure.com/org/project/repo",
        ],
    )
    def test_other_hosts_and_ssh_are_not_routed(self, source):
        assert _adapter().supports(_context(url=source)) is False


class TestSubprocessOverlay:
    def test_sets_every_proxy_variable_and_clears_exclusions(self):
        overlay = _adapter().subprocess_env_overlay(_context())
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            assert overlay[key] == "http://proxy.corp:8080"
        assert overlay["NO_PROXY"] == ""
        assert overlay["no_proxy"] == ""

    def test_percent_encodes_credentials(self):
        overlay = _adapter(username="svc@corp", password="p:a/ss").subprocess_env_overlay(
            _context()
        )
        assert overlay["HTTPS_PROXY"] == "http://svc%40corp:p%3Aa%2Fss@proxy.corp:8080"

    def test_ca_file_is_applied_to_git_only(self, tmp_path):
        ca_file = tmp_path / "ca.pem"
        ca_file.write_text("unused")
        adapter = _adapter(ca_file=str(ca_file))
        git = adapter.subprocess_env_overlay(_context())
        assert git["GIT_SSL_CAINFO"] == str(ca_file)
        crawl = adapter.subprocess_env_overlay(_context(ParserNetworkOperation.WEB_CRAWL))
        assert "GIT_SSL_CAINFO" not in crawl

    def test_does_not_overwrite_git_auth_config(self):
        """Overlay values replace base values, so GIT_CONFIG_* must stay untouched."""
        register_parser_network_adapter(_adapter())
        base = build_git_http_auth_env(GitHttpAuthConfig("oauth2", "pat"), ADO_REPO)
        env = overlay_parser_subprocess_env(_context(), base)
        assert env["GIT_CONFIG_COUNT"] == base["GIT_CONFIG_COUNT"]
        assert env["HTTPS_PROXY"] == "http://proxy.corp:8080"
        values = [env[f"GIT_CONFIG_VALUE_{i}"] for i in range(int(env["GIT_CONFIG_COUNT"]))]
        assert any(value.startswith("Authorization: Basic ") for value in values)


class TestRealTraffic:
    async def test_git_probe_reaches_proxy_with_watch_credentials(self):
        async with _recording_proxy() as (proxy_url, heads):
            configure_egress_proxies(
                SimpleNamespace(egress_proxies={"dev.azure.com": {"url": proxy_url}})
            )
            with pytest.raises(RuntimeError):
                await GitAccessor().probe_git_remote_head(
                    ADO_REPO, auth_config={"token": "pat-value"}
                )
        assert heads, "git never contacted the configured proxy"
        assert heads[0].startswith("CONNECT dev.azure.com:443 ")
        # The source token stays inside the tunnel; the proxy never receives it.
        assert base64.b64encode(b"oauth2:pat-value").decode() not in "".join(heads)

    async def test_httpx_client_sends_proxy_auth_to_proxy(self):
        async with _recording_proxy() as (proxy_url, heads):
            configure_egress_proxies(
                SimpleNamespace(
                    egress_proxies={
                        "dev.azure.com": {"url": proxy_url, "username": "svc", "password": SECRET}
                    }
                )
            )
            client = create_parser_httpx_client(
                _context(ParserNetworkOperation.HTTP_RESOURCE, f"{ADO_REPO}/file"),
            )
            async with client as active:
                with pytest.raises(httpx.HTTPError):
                    await active.get(f"{ADO_REPO}/file")
        expected = base64.b64encode(f"svc:{SECRET}".encode()).decode()
        assert heads[0].startswith("CONNECT dev.azure.com:443 ")
        assert f"proxy-authorization: basic {expected}".lower() in heads[0].lower()

    async def test_urllib_opener_reaches_proxy(self):
        async with _recording_proxy() as (proxy_url, heads):
            configure_egress_proxies(
                SimpleNamespace(egress_proxies={"dev.azure.com": {"url": proxy_url}})
            )
            with pytest.raises(OSError):
                await asyncio.to_thread(
                    open_parser_url,
                    _context(ParserNetworkOperation.GIT_ARCHIVE, f"{ADO_REPO}/a.zip"),
                    f"{ADO_REPO}/a.zip",
                    timeout=10,
                )
        assert heads[0].startswith("CONNECT dev.azure.com:443 ")

    async def test_urllib_ignores_server_no_proxy_and_sends_proxy_auth(self, monkeypatch):
        monkeypatch.setenv("NO_PROXY", "*")
        monkeypatch.setenv("no_proxy", "*")
        async with _recording_proxy() as (proxy_url, heads):
            configure_egress_proxies(
                SimpleNamespace(
                    egress_proxies={
                        "dev.azure.com": {"url": proxy_url, "username": "svc", "password": SECRET}
                    }
                )
            )
            with pytest.raises(OSError):
                await asyncio.to_thread(
                    open_parser_url,
                    _context(ParserNetworkOperation.GIT_ARCHIVE, f"{ADO_REPO}/a.zip"),
                    f"{ADO_REPO}/a.zip",
                    timeout=10,
                )
        expected = base64.b64encode(f"svc:{SECRET}".encode()).decode()
        assert heads, "urllib bypassed the configured proxy"
        assert heads[0].startswith("CONNECT dev.azure.com:443 ")
        assert f"proxy-authorization: basic {expected}".lower() in heads[0].lower()

    async def test_unconfigured_host_keeps_default_client(self):
        configure_egress_proxies(
            SimpleNamespace(egress_proxies={"dev.azure.com": {"url": "http://proxy.corp:8080"}})
        )
        fake = httpx.MockTransport(lambda _request: httpx.Response(204))
        client = create_parser_httpx_client(
            _context(ParserNetworkOperation.HTTP_RESOURCE, "https://example.com/a"),
            transport=fake,
        )
        async with client as active:
            assert (await active.get("https://example.com/a")).status_code == 204


class TestConfigure:
    def test_no_routes_registers_nothing(self):
        configure_egress_proxies(SimpleNamespace(egress_proxies={}))
        assert overlay_parser_subprocess_env(_context(), None) is None
        assert egress_proxy_host_for(ADO_REPO) is None

    def test_host_lookup_exposes_only_host_and_port(self):
        configure_egress_proxies(
            SimpleNamespace(
                egress_proxies={
                    "dev.azure.com": {
                        "url": "http://proxy.corp:8080",
                        "username": "svc",
                        "password": SECRET,
                    }
                }
            )
        )
        assert egress_proxy_host_for(ADO_REPO) == "proxy.corp:8080"
        assert egress_proxy_host_for("https://github.com/org/repo") is None
        assert egress_proxy_host_for("tos://bucket/key") is None
        assert egress_proxy_host_for(None) is None

    def test_reconfigure_replaces_own_routes(self):
        first = {"dev.azure.com": {"url": "http://one.corp:8080"}}
        second = {"dev.azure.com": {"url": "http://two.corp:8080"}}
        configure_egress_proxies(SimpleNamespace(egress_proxies=first))
        configure_egress_proxies(SimpleNamespace(egress_proxies=second))
        assert egress_proxy_host_for(ADO_REPO) == "two.corp:8080"
        configure_egress_proxies(SimpleNamespace(egress_proxies={}))
        assert egress_proxy_host_for(ADO_REPO) is None

    def test_host_lookup_follows_live_adapter(self):
        configure_egress_proxies(
            SimpleNamespace(egress_proxies={"dev.azure.com": {"url": "http://proxy.corp:8080"}})
        )
        reset_parser_network_adapter()
        assert egress_proxy_host_for(ADO_REPO) is None

    def test_none_removes_own_routes(self):
        configure_egress_proxies(
            SimpleNamespace(egress_proxies={"dev.azure.com": {"url": "http://proxy.corp:8080"}})
        )
        configure_egress_proxies(None)
        assert egress_proxy_host_for(ADO_REPO) is None
        assert overlay_parser_subprocess_env(_context(), None) is None

    def test_conflict_with_foreign_adapter_fails_fast(self):
        foreign = SimpleNamespace(supports=lambda _context: False)
        register_parser_network_adapter(foreign)
        with pytest.raises(RuntimeError):
            configure_egress_proxies(
                SimpleNamespace(egress_proxies={"dev.azure.com": {"url": "http://proxy.corp:8080"}})
            )

    def test_empty_config_leaves_foreign_adapter_installed(self):
        foreign = SimpleNamespace(
            supports=lambda _context: True,
            subprocess_env_overlay=lambda _context: {"ROUTE": "foreign"},
        )
        register_parser_network_adapter(foreign)
        configure_egress_proxies(SimpleNamespace(egress_proxies={}))
        assert overlay_parser_subprocess_env(_context(), {})["ROUTE"] == "foreign"


class _StopInitialize(Exception):
    pass


def _bare_service(egress_proxies):
    service = OpenVikingService.__new__(OpenVikingService)
    service._initialized = False
    service._config = SimpleNamespace(code=SimpleNamespace(egress_proxies=egress_proxies))
    return service


class TestServiceStartup:
    async def test_initialize_installs_routes_after_taking_data_lock(self, monkeypatch):
        calls = []
        tracker = SimpleNamespace(load=AsyncMock(side_effect=_StopInitialize))
        monkeypatch.setattr(service_core, "get_task_tracker", lambda: tracker)
        service = _bare_service({"dev.azure.com": {"url": "http://proxy.corp:8080"}})
        with patch.object(
            OpenVikingService,
            "_ensure_data_dir_lock_acquired",
            side_effect=lambda *_: calls.append(egress_proxy_host_for(ADO_REPO)),
        ):
            with pytest.raises(_StopInitialize):
                await service.initialize()
        assert calls == [None]
        assert egress_proxy_host_for(ADO_REPO) == "proxy.corp:8080"

    async def test_lock_failure_leaves_routes_untouched(self):
        service = _bare_service({"dev.azure.com": {"url": "http://proxy.corp:8080"}})
        with patch.object(
            OpenVikingService, "_ensure_data_dir_lock_acquired", side_effect=_StopInitialize
        ):
            with pytest.raises(_StopInitialize):
                await service.initialize()
        assert egress_proxy_host_for(ADO_REPO) is None


async def test_assets_preflight_uses_proxy_overlay(monkeypatch):
    from openviking.server import openviking_assets

    process = SimpleNamespace(
        returncode=0,
        communicate=AsyncMock(return_value=(f"{'a' * 40}\tHEAD\n".encode(), b"")),
    )
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr(openviking_assets.asyncio, "create_subprocess_exec", spawn)
    configure_egress_proxies(
        SimpleNamespace(egress_proxies={"dev.azure.com": {"url": "http://proxy.corp:8080"}})
    )
    await openviking_assets.preflight_git_repository(asset_name="asset", repo_url=ADO_REPO)
    assert spawn.await_args.kwargs["env"]["HTTPS_PROXY"] == "http://proxy.corp:8080"
