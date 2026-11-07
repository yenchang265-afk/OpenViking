"""A shared profile must reject local authorities before serving requests."""

import json
import re
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from openviking.server.config import ServerConfig
from openviking.server.shared_deployment import validate_shared_deployment


def configuration():
    server = ServerConfig(
        deployment_mode="shared",
        auth_mode="api_key",
        root_api_key="test-root",
        account_store={"provider": "mysql"},
        transfer_tokens={"provider": "redis"},
        temp_upload={"default_mode": "shared"},
        observability={"usage_audit": {"backend": "mysql"}},
    )
    config = NS(
        enable_watch_scheduler=False,
        git=NS(enabled=True, backend="s3"),
        cache=NS(provider="redis"),
        gateway=NS(enabled=False),
        oauth=NS(enabled=True, backend="mysql"),
        encryption=NS(enabled=False),
        storage=NS(
            vectordb=NS(backend="elasticsearch"),
            task_store=NS(provider="mysql"),
            agfs=NS(
                backend="s3",
                s3=NS(cache_enabled=False),
                queuefs=NS(backend="cache", mode="shared", recover_stale_sec=86400),
                pathlock=NS(provider="cache"),
                cachefs=NS(backend="cache", multi_instance=True),
                tiered=NS(enabled=False),
                backups=None,
            ),
        ),
    )
    return server, config


def test_valid_shared_profile():
    validate_shared_deployment(*configuration())


def test_shared_helm_example_passes_real_config_validation(tmp_path, monkeypatch):
    import yaml

    from openviking.config.config_file import _validate

    root = Path(__file__).resolve().parents[2]
    defaults = yaml.safe_load((root / "deploy/helm/openviking/values.yaml").read_text())["config"]
    overlay = yaml.safe_load((root / "examples/k8s-helm/shared-values.yaml").read_text())["config"]

    def merge(target, changes):
        for name, value in changes.items():
            if isinstance(value, dict) and isinstance(target.get(name), dict):
                merge(target[name], value)
            else:
                target[name] = value

    merge(defaults, overlay)
    defaults["storage"]["workspace"] = str(tmp_path / "workspace")
    content = json.dumps(defaults)
    for name in re.findall(r"\$\{([A-Z0-9_]+)\}", content):
        monkeypatch.setenv(name, "test-value")
    config = _validate(content)
    assert config.storage.agfs.backend == "s3"


@pytest.mark.parametrize(
    "target,path,value",
    [
        ("config", "storage.agfs.backend", "local"),
        ("config", "storage.agfs.s3.cache_enabled", True),
        ("config", "cache.provider", "memory"),
        ("config", "storage.agfs.queuefs.backend", "sqlite"),
        ("config", "storage.agfs.queuefs.mode", "worker"),
        ("config", "storage.agfs.queuefs.recover_stale_sec", 0),
        ("config", "storage.agfs.pathlock.provider", "filesystem"),
        ("config", "storage.agfs.cachefs.multi_instance", False),
        ("config", "storage.vectordb.backend", "local"),
        ("config", "storage.task_store.provider", "file"),
        ("config", "oauth.backend", "sqlite"),
        ("config", "gateway.enabled", True),
        ("config", "enable_watch_scheduler", True),
        ("config", "git.backend", "local"),
        ("server", "account_store.provider", "file"),
        ("server", "transfer_tokens.provider", "memory"),
        ("server", "temp_upload.default_mode", "local"),
        ("server", "observability.usage_audit.backend", "sqlite"),
        ("server", "with_bot", True),
    ],
)
def test_shared_profile_rejects_local_state(target, path, value):
    server, config = configuration()
    obj = server if target == "server" else config
    *parents, name = path.split(".")
    for parent in parents:
        obj = getattr(obj, parent)
    setattr(obj, name, value)
    with pytest.raises(ValueError, match="Invalid shared deployment"):
        validate_shared_deployment(server, config)


def test_standalone_keeps_local_defaults():
    _, config = configuration()
    config = deepcopy(config)
    config.storage.agfs.backend = "local"
    validate_shared_deployment(ServerConfig(), config)


def test_encrypted_replicas_require_explicit_shared_root_key():
    server, config = configuration()
    config.encryption = NS(enabled=True, provider="local", local=NS(root_key=None))
    with pytest.raises(ValueError, match="shared encryption.local.root_key"):
        validate_shared_deployment(server, config)
    config.encryption.local.root_key = "0" * 64
    validate_shared_deployment(server, config)


@pytest.mark.parametrize(
    "options", [{"watch_interval": 60}, {"is_active": False}, {"watch_interval": -1}]
)
async def test_shared_resource_requests_reject_watch_options_before_ingestion(options):
    from openviking.server.identity import RequestContext, Role
    from openviking.service.resource_service import ResourceService
    from openviking_cli.exceptions import FailedPreconditionError
    from openviking_cli.session.user_id import UserIdentifier

    service = ResourceService()
    service.set_watch_requests_enabled(False)
    ctx = RequestContext(user=UserIdentifier("acct", "alice"), role=Role.USER)
    with pytest.raises(FailedPreconditionError, match="watches are unavailable"):
        await service.add_resource("https://example.test/doc", ctx=ctx, **options)
