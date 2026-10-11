# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Regression tests for Git preflight process cleanup."""

import asyncio
import os
import signal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest

from openviking.parse.mode import ParseMode
from openviking.server.identity import RequestContext, Role
from openviking.service import resource_service as resource_service_module
from openviking.service.resource_service import ResourceService
from openviking_cli.exceptions import InvalidArgumentError
from openviking_cli.session.user_id import UserIdentifier

pytestmark = pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX-only")


async def test_account_github_token_is_used_for_repository_preflight(monkeypatch):
    token_resolver = AsyncMock(return_value="account-token")
    processor = SimpleNamespace(github_token_for=token_resolver)
    service = ResourceService(resource_processor=processor)
    service._preflight_git_source = AsyncMock(
        return_value=SimpleNamespace(
            source_name="private",
            source_path="https://github.com/org/private",
            source_format="repository",
        )
    )
    monkeypatch.setattr(resource_service_module, "is_git_repo_url", lambda _path: True)
    monkeypatch.setattr(resource_service_module, "is_github_url", lambda _path: True)
    ctx = RequestContext(
        user=UserIdentifier("account-1", "user-1"),
        role=Role.USER,
    )

    plan = await service._prepare_standard_source_plan(
        path="https://github.com/org/private",
        ctx=ctx,
        mode=ParseMode.DEFAULT,
        allow_local_path_resolution=False,
        processor_kwargs={},
    )

    token_resolver.assert_awaited_once_with("https://github.com/org/private", ctx)
    preflight_auth = service._preflight_git_source.await_args.kwargs["auth_config"]
    assert preflight_auth.username == "oauth2"
    assert preflight_auth.token == "account-token"
    assert plan is not None
    assert plan.task_auth == {}
    assert "account-token" not in str(plan.processor_args)


@pytest.mark.parametrize(
    "source",
    [
        "git@github.com:org/private.git",
        "ssh://git@github.com/org/private.git",
    ],
)
async def test_default_github_token_is_not_applied_to_ssh_preflight(monkeypatch, source):
    token_resolver = AsyncMock(return_value="account-token")
    processor = SimpleNamespace(github_token_for=token_resolver)
    service = ResourceService(resource_processor=processor)
    service._preflight_git_source = AsyncMock(
        return_value=SimpleNamespace(
            source_name="private",
            source_path=source,
            source_format="repository",
        )
    )
    monkeypatch.setattr(resource_service_module, "is_git_repo_url", lambda _path: True)
    monkeypatch.setattr(resource_service_module, "is_github_url", lambda _path: True)
    ctx = RequestContext(
        user=UserIdentifier("account-1", "user-1"),
        role=Role.USER,
    )

    plan = await service._prepare_standard_source_plan(
        path=source,
        ctx=ctx,
        mode=ParseMode.DEFAULT,
        allow_local_path_resolution=False,
        processor_kwargs={},
    )

    token_resolver.assert_not_awaited()
    service._preflight_git_source.assert_awaited_once_with(source, auth_config=None)
    assert plan is not None


async def test_git_preflight_timeout_kills_process_group_and_bounds_reap(monkeypatch):
    process = Mock(pid=43210)
    process.communicate = AsyncMock(return_value=(b"", b""))
    process.kill = Mock()
    captured = {}
    wait_timeouts = []
    killpg = Mock()

    async def fake_exec(*_args, **kwargs):
        captured.update(kwargs)
        return process

    async def fake_wait_for(awaitable, timeout):
        wait_timeouts.append(timeout)
        if len(wait_timeouts) == 1:
            awaitable.close()
            raise asyncio.TimeoutError
        return await awaitable

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(os, "killpg", killpg)

    with pytest.raises(InvalidArgumentError, match="preflight timed out"):
        await ResourceService()._preflight_git_source("https://github.com/org/private")

    assert (
        captured.get("start_new_session"),
        killpg.call_args_list,
        wait_timeouts,
    ) == (True, [call(process.pid, signal.SIGKILL)], [10.0, 1.0])
    process.kill.assert_not_called()


async def test_git_preflight_cancellation_kills_process_group_and_bounds_reap(monkeypatch):
    process = Mock(pid=43210)
    process.communicate = AsyncMock(side_effect=[asyncio.CancelledError, (b"", b"")])
    process.wait = AsyncMock()
    process.kill = Mock()
    captured = {}
    wait_timeouts = []
    killpg = Mock()

    async def fake_exec(*_args, **kwargs):
        captured.update(kwargs)
        return process

    async def fake_wait_for(awaitable, timeout):
        wait_timeouts.append(timeout)
        return await awaitable

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(os, "killpg", killpg)

    with pytest.raises(asyncio.CancelledError):
        await ResourceService()._preflight_git_source("https://github.com/org/private")

    assert (
        captured.get("start_new_session"),
        killpg.call_args_list,
        wait_timeouts,
    ) == (True, [call(process.pid, signal.SIGKILL)], [10.0, 1.0])
    process.kill.assert_not_called()


async def test_azure_devops_proxy_reaches_preflight_and_private_task_auth(monkeypatch):
    repo_url = "https://dev.azure.com/org/project/_git/private"
    proxy = "http://proxy-user:proxy-secret@proxy.corp.example:8080"
    service = ResourceService(resource_processor=SimpleNamespace())
    service._preflight_git_source = AsyncMock(
        return_value=SimpleNamespace(
            source_name="private",
            source_path=repo_url,
            source_format="repository",
        )
    )
    ctx = RequestContext(user=UserIdentifier("account-1", "user-1"), role=Role.USER)

    plan = await service._prepare_standard_source_plan(
        path=repo_url,
        ctx=ctx,
        mode=ParseMode.DEFAULT,
        allow_local_path_resolution=False,
        processor_kwargs={"auth_config": {"token": "azure-pat", "proxy": proxy}},
    )

    preflight_auth = service._preflight_git_source.await_args.kwargs["auth_config"]
    assert preflight_auth.token == "azure-pat"
    assert preflight_auth.proxy == proxy
    assert plan is not None
    assert plan.task_auth["proxy"] == proxy
    assert plan.task_auth["token"] == "azure-pat"
    assert "proxy-secret" not in str(plan.processor_args)
    assert "azure-pat" not in str(plan.processor_args)


async def test_http_add_resource_rejects_private_git_proxy_before_preflight(monkeypatch):
    from openviking_cli.exceptions import PermissionDeniedError

    service = ResourceService(
        resource_processor=SimpleNamespace(), skill_processor=Mock(), viking_fs=Mock()
    )
    service._preflight_git_source = AsyncMock()
    monkeypatch.setattr(
        "openviking.utils.network_guard._resolve_host_addresses",
        lambda _host: {"10.0.0.5"},
    )
    ctx = RequestContext(user=UserIdentifier("account-1", "user-1"), role=Role.USER)

    with pytest.raises(PermissionDeniedError, match="allow_private_networks") as exc_info:
        await service.add_resource(
            path="https://dev.azure.com/org/project/_git/private",
            ctx=ctx,
            to="viking://resources/private",
            enforce_public_remote_targets=True,
            args={
                "auth_config": {
                    "token": "azure-pat",
                    "proxy": "http://u:proxy-secret@proxy.corp.example:8080",
                }
            },
        )

    service._preflight_git_source.assert_not_awaited()
    assert "proxy-secret" not in str(exc_info.value)


async def test_add_resource_rejects_auth_config_for_non_git_sources(monkeypatch):
    service = ResourceService(
        resource_processor=SimpleNamespace(), skill_processor=Mock(), viking_fs=Mock()
    )
    service._prepare_standard_source_plan = AsyncMock()
    ctx = RequestContext(user=UserIdentifier("account-1", "user-1"), role=Role.USER)

    with pytest.raises(InvalidArgumentError, match="azure_devops_domains") as exc_info:
        await service.add_resource(
            # Azure DevOps Server shape on a host missing from code.*_domains.
            path="https://tfs.unconfigured.example/tfs/Coll/Project/_git/private",
            ctx=ctx,
            to="viking://resources/private",
            args={"auth_config": {"token": "azure-pat"}},
        )

    service._prepare_standard_source_plan.assert_not_awaited()
    assert "azure-pat" not in str(exc_info.value)


async def test_queued_git_execution_rechecks_proxy_before_processing(monkeypatch):
    from openviking_cli.exceptions import PermissionDeniedError

    processor = SimpleNamespace(process_resource=AsyncMock())
    service = ResourceService(
        resource_processor=processor, skill_processor=Mock(), viking_fs=Mock()
    )
    # Proxy resolved public at submit time; DNS now points it at a private host.
    monkeypatch.setattr(
        "openviking.utils.network_guard._resolve_host_addresses",
        lambda _host: {"10.0.0.5"},
    )
    ctx = RequestContext(user=UserIdentifier("account-1", "user-1"), role=Role.USER)

    with pytest.raises(PermissionDeniedError, match="allow_private_networks"):
        await service._execute_resource_ingestion(
            path="https://dev.azure.com/org/project/_git/private",
            ctx=ctx,
            defer_post_processing=False,
            to="viking://resources/private",
            enforce_public_remote_targets=True,
            auth_config={"token": "azure-pat", "proxy": "http://proxy.corp.example:8080"},
        )

    processor.process_resource.assert_not_awaited()
