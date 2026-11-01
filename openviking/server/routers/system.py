# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""System endpoints for OpenViking HTTP Server."""

import asyncio
from typing import Awaitable, Callable, TypeVar

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from openviking.core.path_variables import resolve_path_variables
from openviking.core.uri_validation import validate_request_viking_uri
from openviking.server.auth import get_request_context
from openviking.server.dependencies import get_service
from openviking.server.identity import AuthMode, RequestContext
from openviking.server.models import Response
from openviking.storage.viking_fs import get_viking_fs
from openviking_cli.exceptions import UnauthenticatedError
from openviking_cli.utils import get_logger

logger = get_logger(__name__)

router = APIRouter()

T = TypeVar("T")


def _is_ready_check_ok(value) -> bool:
    """Return whether one readiness check value represents a healthy state."""
    if isinstance(value, dict):
        status = value.get("status")
        if status not in ("ok", "not_configured", "not_supported"):
            return False
        nested = value.get("checks")
        if nested is None:
            return True
        return all(_is_ready_check_ok(item) for item in nested.values())
    return value in ("ok", "not_configured", "not_supported")


_DEFAULT_READY_PROBE_TIMEOUT_SECONDS = 5.0

# In-flight readiness probes by name. Storage calls run to completion even when
# the awaiting request gives up, so repeated probes against a stalled backend
# share one call instead of stacking blocked threads.
_inflight_probes: dict[str, asyncio.Task] = {}


def _consume_probe_outcome(task: asyncio.Task) -> None:
    """Retrieve a finished probe's exception so late failures are not logged as unhandled."""
    if not task.cancelled():
        task.exception()


async def _bounded_probe(name: str, probe: Callable[[], Awaitable[T]], timeout: float) -> T:
    """Wait up to ``timeout`` seconds for a probe without cancelling it.

    Raises ``TimeoutError`` when the probe is still running; it keeps running and
    later callers wait on it rather than starting another.
    """
    loop = asyncio.get_running_loop()
    task = _inflight_probes.get(name)
    if task is None or task.done() or task.get_loop() is not loop:
        task = loop.create_task(probe())
        task.add_done_callback(_consume_probe_outcome)
        _inflight_probes[name] = task
    done, _ = await asyncio.wait({task}, timeout=timeout)
    if not done:
        raise TimeoutError(f"timed out after {timeout:g}s")
    return task.result()


def _ready_probe_timeout(request: Request) -> float:
    config = getattr(request.app.state, "config", None)
    return getattr(config, "ready_probe_timeout_seconds", _DEFAULT_READY_PROBE_TIMEOUT_SECONDS)


async def _probe_agfs_readiness() -> dict[str, object]:
    """Return structured AGFS filesystem readiness."""
    viking_fs = get_viking_fs()
    checks: dict[str, object] = {}

    await viking_fs.ls("viking://", ctx=None)
    checks["filesystem"] = "ok"

    return {"status": "ok", "checks": checks}


@router.get("/health", tags=["system"])
async def health_check(request: Request):
    """Health check endpoint (no authentication required)."""
    from openviking import __version__

    result = {"status": "ok", "healthy": True, "version": __version__}

    try:
        config = getattr(request.app.state, "config", None)
        effective_auth_mode = AuthMode.API_KEY.value
        if config is not None and hasattr(config, "get_effective_auth_mode"):
            effective_auth_mode = config.get_effective_auth_mode()
        result["auth_mode"] = effective_auth_mode
        if effective_auth_mode == AuthMode.TRUSTED.value:
            result["root_api_key_required"] = True

        x_api_key = request.headers.get("X-API-Key")
        authorization = request.headers.get("Authorization")
        account = request.headers.get("X-OpenViking-Account")
        user = request.headers.get("X-OpenViking-User")
        trusted_identity = effective_auth_mode == AuthMode.TRUSTED.value and account and user

        if x_api_key or authorization or trusted_identity:
            try:
                from openviking.server.auth import resolve_identity

                identity = await resolve_identity(
                    request,
                    x_api_key=x_api_key,
                    authorization=authorization,
                    x_openviking_account=account,
                    x_openviking_user=user,
                )
                result["account_id"] = str(identity.account_id)
                result["user_id"] = str(identity.user_id)
                result["role"] = str(identity.role)
            except UnauthenticatedError:
                raise
            except Exception as e:
                logger.warning(f"Failed to resolve identity: {e}")
    except UnauthenticatedError:
        raise
    except Exception as e:
        logger.error(f"Failed to get health check: {e}")

    return result


@router.get("/ready", tags=["system"])
async def readiness_check(request: Request):
    """Readiness probe — checks AGFS, VectorDB, and APIKeyManager.

    Returns 200 when all subsystems are operational, 503 otherwise.
    No authentication required (designed for K8s probes).
    """
    # If service is still initializing, return 503 immediately
    try:
        service = get_service()
        if not service._initialized:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "reason": "initializing"},
            )
    except RuntimeError:
        # get_service() raises RuntimeError when service not yet set
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": "initializing"},
        )

    checks = {}
    probe_timeout = _ready_probe_timeout(request)

    # 1. AGFS: probe filesystem access
    try:
        checks["agfs"] = await _bounded_probe("agfs", _probe_agfs_readiness, probe_timeout)
    except Exception as e:
        checks["agfs"] = {"status": "error", "checks": {"filesystem": f"error: {e}"}}

    # 2. VectorDB: health_check()
    try:
        viking_fs = get_viking_fs()
        storage = viking_fs._get_vector_store()
        if storage:
            healthy = await _bounded_probe("vectordb", storage.health_check, probe_timeout)
            checks["vectordb"] = "ok" if healthy else "unhealthy"
        else:
            checks["vectordb"] = "not_configured"
    except Exception as e:
        checks["vectordb"] = f"error: {e}"

    # 3. APIKeyManager: check if loaded
    try:
        manager = getattr(request.app.state, "api_key_manager", None)
        if manager is not None:
            checks["api_key_manager"] = "ok"
        else:
            checks["api_key_manager"] = "not_configured"
    except Exception as e:
        checks["api_key_manager"] = f"error: {e}"

    # 4. Embedding: the provider is initialized by the service startup path.
    # There is no Account context on an unauthenticated readiness probe, so do
    # not create or probe a Cluster-scoped embedder here.
    try:
        embedding_provider = getattr(service, "embedding_provider", None)
        checks["embedding"] = "ok" if embedding_provider is not None else "not_initialized"
    except Exception as e:
        checks["embedding"] = f"error: {e}"

    # 5. Ollama: connectivity check if configured
    try:
        from openviking_cli.utils.config.open_viking_config import OpenVikingConfigSingleton
        from openviking_cli.utils.ollama import check_ollama_running, detect_ollama_in_config

        ov_config = OpenVikingConfigSingleton.get_instance()
        uses_ollama, ollama_host, ollama_port = detect_ollama_in_config(ov_config)
        if uses_ollama:
            if check_ollama_running(ollama_host, ollama_port):
                checks["ollama"] = "ok"
            else:
                checks["ollama"] = f"unreachable at {ollama_host}:{ollama_port}"
        else:
            checks["ollama"] = "not_configured"
    except Exception as e:
        checks["ollama"] = f"error: {e}"

    all_ok = all(_is_ready_check_ok(v) for v in checks.values())
    status_code = 200 if all_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ready" if all_ok else "not_ready", "checks": checks},
    )


@router.get("/api/v1/system/status", tags=["system"])
async def system_status(
    ctx: RequestContext = Depends(get_request_context),
):
    """Get system status.

    ``result.user`` is the authenticated request's ``user_id`` (from API key or
    headers), not the process-wide service default — clients use this to resolve
    multi-tenant paths (e.g. OpenClaw plugin).
    """
    service = get_service()
    return Response(
        status="ok",
        result={
            "initialized": service._initialized,
            "user": ctx.user.user_id,
        },
    )


class WaitRequest(BaseModel):
    """Legacy wait parameters, retained for request compatibility."""

    timeout: float | None = Field(
        default=None,
        deprecated=True,
        description="Deprecated compatibility parameter; accepted and ignored.",
    )


class ConsistencyRequest(BaseModel):
    """Request model for filesystem/vector-index consistency checks."""

    uri: str


@router.post("/api/v1/system/wait", tags=["system"])
async def wait_processed(
    request: WaitRequest | None = Body(None),
    _ctx: RequestContext = Depends(get_request_context),
):
    """Wait for all processing to complete."""
    service = get_service()
    result = await service.resources.wait_processed()
    return Response(status="ok", result=result)


@router.post("/api/v1/system/consistency", tags=["system"])
async def check_consistency(
    request: ConsistencyRequest,
    ctx: RequestContext = Depends(get_request_context),
):
    """Check filesystem/vector-index consistency for a URI subtree."""
    service = get_service()
    uri = validate_request_viking_uri(resolve_path_variables(request.uri), ctx)
    result = await service.check_consistency(
        uri=uri,
        ctx=ctx,
    )
    return Response(status="ok", result=result)
