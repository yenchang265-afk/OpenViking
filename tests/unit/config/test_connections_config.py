"""Connection inheritance across both config loaders and the native mount seam."""

import json
import os
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from openviking.config.config_file import _validate
from openviking.server.config import load_server_config
from openviking.utils.agfs_utils import _generate_plugin_config, mount_agfs_backend
from openviking_cli.utils.config.connections_config import (
    ConnectionsConfig,
    MySQLConnectionConfig,
    resolve_mysql_connections,
)
from openviking_cli.utils.config.open_viking_config import OpenVikingConfig


@pytest.fixture
def raw_config(tmp_path):
    return {
        "connections": {
            "mysql": {
                "host": "mysql.internal",
                "port": 3307,
                "user": "ov",
                "password": "p@ss:/?#%",
                "database": "openviking",
                "ssl": True,
            }
        },
        "storage": {
            "workspace": str(tmp_path / "workspace"),
            "task_store": {"provider": "mysql", "params": {"maxsize": 3}},
            "agfs": {
                "backend": "s3",
                "s3": {
                    "bucket": "test",
                    "endpoint": "https://s3.example.test",
                    "region": "us-east-1",
                    "access_key": "test",
                    "secret_key": "test",
                },
                "tiered": {
                    "enabled": True,
                    "mysql": {"table": "test_entries", "max_connections": 4},
                },
            },
        },
        "oauth": {"enabled": True, "backend": "mysql"},
        "server": {
            "account_store": {"provider": "mysql"},
            "observability": {"usage_audit": {"backend": "mysql"}},
        },
        "embedding": {
            "dense": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "dimension": 1536,
                "api_key": "test",
            }
        },
        "vlm": {"provider": "openai", "model": "test", "api_key": "test"},
    }


def test_all_mysql_backends_inherit_one_connection(raw_config, tmp_path):
    original = deepcopy(raw_config)
    environment = dict(os.environ)
    config = OpenVikingConfig.from_dict(raw_config)
    path = tmp_path / "ov.conf"
    path.write_text(json.dumps(raw_config))
    server = load_server_config(str(path))
    for params in (
        config.storage.task_store.params,
        config.oauth.mysql,
        server.account_store.params,
        server.observability.usage_audit.mysql,
    ):
        assert params["host"] == "mysql.internal"
        assert params["port"] == 3307
        assert params["password"] == original["connections"]["mysql"]["password"]
        assert params["ssl"] is True
    assert config.storage.task_store.params["maxsize"] == 3
    assert raw_config == original
    assert dict(os.environ) == environment
    assert original["connections"]["mysql"]["password"] not in repr(config)
    assert original["connections"]["mysql"]["password"] not in repr(server)


def test_tiered_binding_uses_same_credentials_without_dsn_env(raw_config):
    config = OpenVikingConfig.from_dict(raw_config)
    mounts = _generate_plugin_config(config.storage.agfs, Path(config.storage.workspace))
    params = mounts["s3fs"]["config"]
    url = urlsplit(params["tiered_dsn"])
    assert url.hostname == "mysql.internal"
    assert url.port == 3307
    assert unquote(url.username) == "ov"
    assert unquote(url.password) == raw_config["connections"]["mysql"]["password"]
    assert parse_qs(url.query)["ssl-mode"] == ["VERIFY_IDENTITY"]
    assert "tiered_dsn_env" not in params
    assert params["tiered_table"] == "test_entries"
    assert params["tiered_max_connections"] == 4
    assert config.git.backend == "agfs"
    assert "_connection" not in config.model_dump()["storage"]["agfs"]["tiered"]["mysql"]


def test_complete_legacy_connections_remain_independent(raw_config):
    legacy = {"user": "legacy", "password": "separate", "database": "legacy_db"}
    raw_config["storage"]["task_store"]["params"] = legacy.copy()
    raw_config["storage"]["agfs"]["tiered"]["mysql"]["dsn_env"] = "LEGACY_DSN"
    config = OpenVikingConfig.from_dict(raw_config)
    assert config.storage.task_store.params == legacy
    params = _generate_plugin_config(config.storage.agfs, Path(config.storage.workspace))["s3fs"][
        "config"
    ]
    assert params["tiered_dsn_env"] == "LEGACY_DSN"
    assert "tiered_dsn" not in params


@pytest.mark.parametrize(
    "partial", [{"host": "other"}, {"password": "private-value"}, {"ssl": False}]
)
def test_partial_inline_connection_is_rejected_without_exposing_secrets(raw_config, partial):
    raw_config["server"]["account_store"]["params"] = partial
    with pytest.raises(ValueError, match="partial MySQL connection") as caught:
        resolve_mysql_connections(raw_config)
    assert "private-value" not in str(caught.value)
    assert raw_config["connections"]["mysql"]["password"] not in str(caught.value)


def test_defaults_do_not_enable_other_backends(raw_config):
    raw_config["server"]["account_store"] = {"provider": "file"}
    resolved = resolve_mysql_connections(raw_config)
    assert resolved["server"]["account_store"] == {"provider": "file"}


def test_redis_mysql_account_store_inherits_nested_mysql_only(raw_config):
    raw_config["server"]["account_store"] = {
        "provider": "redis_mysql",
        "params": {"redis": {"host": "redis.internal"}},
    }
    resolved = resolve_mysql_connections(raw_config)["server"]["account_store"]["params"]
    assert resolved["mysql"]["host"] == "mysql.internal"
    assert resolved["redis"] == {"host": "redis.internal"}


def test_preview_and_model_roundtrip_preserve_inheritance(raw_config):
    config = _validate(json.dumps(raw_config))
    restored = OpenVikingConfig.from_dict(config.model_dump())
    assert restored.storage.task_store.params == config.storage.task_store.params
    assert restored.storage.agfs.tiered.mysql._connection == config.connections.mysql


@pytest.mark.parametrize(
    "ssl, expected",
    [
        (None, {"ssl-mode": ["DISABLED"]}),
        (True, {"ssl-mode": ["VERIFY_IDENTITY"]}),
        (
            {"ca": "/certs/root.pem", "check_hostname": False},
            {"ssl-mode": ["VERIFY_CA"], "ssl-ca": ["/certs/root.pem"]},
        ),
        (
            {"ca": "/certs/root.pem", "cert": "/certs/client.pem", "key": "/certs/client.key"},
            {
                "ssl-mode": ["VERIFY_IDENTITY"],
                "ssl-ca": ["/certs/root.pem"],
                "ssl-cert": ["/certs/client.pem"],
                "ssl-key": ["/certs/client.key"],
            },
        ),
    ],
)
def test_native_connection_preserves_tls_policy(raw_config, ssl, expected):
    connection = MySQLConnectionConfig(**{**raw_config["connections"]["mysql"], "ssl": ssl})
    assert parse_qs(urlsplit(connection.tiered_dsn()).query) == expected


def test_ipv6_connection_encodes_host_and_password(raw_config):
    connection = MySQLConnectionConfig(**{**raw_config["connections"]["mysql"], "host": "::1"})
    parsed = urlsplit(connection.tiered_dsn())
    assert parsed.hostname == "::1"
    assert unquote(parsed.password) == connection.password


def test_invalid_shared_connection_does_not_print_credentials():
    with pytest.raises(ValueError) as caught:
        ConnectionsConfig(mysql={"user": "ov", "password": "private-value"})
    assert "private-value" not in str(caught.value)


def test_programmatic_server_config_inherits_central_connection(raw_config, monkeypatch):
    from openviking.server import app as app_module
    from openviking.server import dependencies
    from openviking.server.config import ServerConfig

    root = OpenVikingConfig.from_dict(raw_config)
    monkeypatch.setattr(app_module, "get_openviking_config", lambda: root)
    monkeypatch.setattr(dependencies, "_server_config", dependencies.get_server_config())
    server = ServerConfig(
        account_store={"provider": "mysql"}, observability={"usage_audit": {"backend": "mysql"}}
    )
    app = app_module.create_app(config=server)
    assert app.state.config.account_store.params["host"] == "mysql.internal"
    assert app.state.config.observability.usage_audit.mysql["host"] == "mysql.internal"
    assert server.account_store.params == {}


def test_tiered_mount_rejects_old_binding_before_touching_mounts(raw_config):
    config = OpenVikingConfig.from_dict(raw_config)
    client = Mock()
    client.get_capabilities.return_value = {"features": ["tiered"]}
    with pytest.raises(RuntimeError, match="updated RAGFS native binding"):
        mount_agfs_backend(client, config.storage.agfs)
    client.mount.assert_not_called()
    client.unmount.assert_not_called()


def test_tiered_mount_passes_shared_connection_to_compatible_binding(raw_config):
    config = OpenVikingConfig.from_dict(raw_config)
    client = Mock()
    client.get_capabilities.return_value = {"features": ["tiered", "tiered_shared_connection"]}
    mount_agfs_backend(client, config.storage.agfs)
    assert any("tiered_dsn" in call.args[2] for call in client.mount.call_args_list)


def test_all_shared_connections_and_canonical_selectors(raw_config):
    raw_config["connections"].update(
        {
            "redis": {"endpoints": ["rediss://redis:6379"], "password": "redis-secret"},
            "s3": raw_config["storage"]["agfs"]["s3"],
            "elasticsearch": {
                "hosts": ["https://es:9200"],
                "username": "ov",
                "password": "es-secret",
            },
        }
    )
    raw_config["cache"] = {"backend": "redis", "params": {"default_ttl_seconds": 300}}
    raw_config["storage"]["agfs"]["s3"] = {"prefix": "production/"}
    raw_config["storage"]["agfs"]["pathlock"] = {"backend": "cache"}
    raw_config["storage"]["vectordb"] = {"backend": "elasticsearch"}
    raw_config["storage"]["task_store"] = {"backend": "mysql"}
    original = deepcopy(raw_config)
    config = OpenVikingConfig.model_validate(raw_config)
    assert raw_config == original
    assert config.cache.params["password"] == "redis-secret"
    assert config.cache.params["default_ttl_seconds"] == 300
    assert config.storage.agfs.s3.bucket == "test"
    assert config.storage.agfs.s3.prefix == "production/"
    assert config.storage.vectordb.elasticsearch.password == "es-secret"
    assert "redis-secret" not in repr(config)
    assert "es-secret" not in repr(config)
    assert config.storage.task_store.params["host"] == "mysql.internal"
    dumped = config.model_dump()
    assert dumped["cache"]["backend"] == "redis"
    assert "provider" not in dumped["cache"]
    assert dumped["embedding"]["dense"]["provider"] == "openai"
    OpenVikingConfig.model_validate(dumped)


@pytest.mark.parametrize(
    "kind,section,field,partial",
    [
        ("redis", "cache", "params", {"password": "private"}),
        ("s3", "agfs", "s3", {"bucket": "other"}),
        ("elasticsearch", "vectordb", "elasticsearch", {"password": "private"}),
    ],
)
def test_partial_connections_never_mix_credentials(kind, section, field, partial):
    defaults = {
        "redis": {"endpoints": ["redis://redis:6379"]},
        "s3": {
            "endpoint": "https://s3",
            "region": "us-east-1",
            "bucket": "ov",
            "access_key": "key",
            "secret_key": "secret",
        },
        "elasticsearch": {"hosts": ["https://es:9200"]},
    }
    selected = {"backend": kind, field: partial}
    raw = {"connections": {kind: defaults[kind]}}
    if section == "cache":
        raw[section] = selected
    else:
        raw["storage"] = {section: selected}
    with pytest.raises(ValueError, match="partial"):
        resolve_mysql_connections(raw)


def test_backend_alias_conflicts_and_legacy_support():
    from openviking_cli.utils.config.cache_config import CacheConfig

    assert CacheConfig(provider="redis").model_dump()["backend"] == "redis"
    assert CacheConfig(backend="redis", provider="redis").provider == "redis"
    with pytest.raises(ValueError, match="conflict"):
        CacheConfig(backend="redis", provider="dynamic")


def test_untiered_s3_git_inherits_connection(raw_config):
    raw_config["connections"]["s3"] = raw_config["storage"]["agfs"]["s3"]
    raw_config["storage"]["agfs"]["s3"] = {"prefix": "data/"}
    raw_config["storage"]["agfs"].pop("tiered")
    config = OpenVikingConfig.model_validate(raw_config)
    assert config.git.backend == "s3"
    assert config.git.s3.bucket == "test"
    assert config.git.s3.secret_key == "test"


def test_complete_inline_redis_does_not_inherit_auth():
    raw = {
        "connections": {"redis": {"endpoints": ["rediss://central:6379"], "password": "secret"}},
        "cache": {"backend": "redis", "params": {"endpoints": ["redis://local:6379"]}},
    }
    resolved = resolve_mysql_connections(raw)
    assert resolved["cache"]["params"] == {"endpoints": ["redis://local:6379"]}


def test_redis_mysql_nested_cache_inherits_connection(raw_config):
    raw_config["connections"]["redis"] = {"endpoints": ["redis://shared:6379"]}
    raw_config["server"]["account_store"] = {
        "backend": "redis_mysql",
        "params": {"cache": {"backend": "redis", "params": {"pool_size": 8}}},
    }
    params = resolve_mysql_connections(raw_config)["server"]["account_store"]["params"]
    assert params["cache"]["params"]["endpoints"] == ["redis://shared:6379"]
    assert params["cache"]["params"]["pool_size"] == 8
    assert params["mysql"]["host"] == "mysql.internal"


def test_inline_elasticsearch_does_not_inherit_central_auth():
    raw = {
        "connections": {"elasticsearch": {"hosts": ["https://central:9200"], "api_key": "secret"}},
        "storage": {
            "vectordb": {
                "backend": "elasticsearch",
                "elasticsearch": {"hosts": ["http://local:9200"]},
            }
        },
    }
    resolved = resolve_mysql_connections(raw)
    assert resolved["storage"]["vectordb"]["elasticsearch"] == {"hosts": ["http://local:9200"]}


def test_programmatic_server_inherits_redis_without_central_mysql(monkeypatch):
    from openviking.server import app as app_module
    from openviking.server import dependencies
    from openviking.server.config import ServerConfig

    root = OpenVikingConfig(connections={"redis": {"endpoints": ["redis://shared:6379"]}})
    monkeypatch.setattr(app_module, "get_openviking_config", lambda: root)
    monkeypatch.setattr(dependencies, "_server_config", dependencies.get_server_config())
    server = ServerConfig(
        account_store={
            "backend": "redis_mysql",
            "params": {
                "mysql": {"user": "ov", "password": "secret", "database": "ov"},
                "cache": {"backend": "redis"},
            },
        }
    )
    app = app_module.create_app(config=server)
    assert app.state.config.account_store.params["cache"]["params"]["endpoints"] == [
        "redis://shared:6379"
    ]
    assert "params" not in server.account_store.params["cache"]
