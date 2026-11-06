"""Cross-replica and consume-once contracts for transfer credentials."""

import asyncio
import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import fakeredis
import pytest
from redis.exceptions import ConnectionError

from openviking.server.config import ServerConfig
from openviking.server.identity import Role
from openviking.server.upload_token_store import (
    UploadTokenError,
    UploadTokenStore,
    download_token_store,
    transfer_token_lifespan,
    upload_token_store,
)
from openviking.storage.acl import AclEntry, AclLevel, AclMode, AclSpec


@pytest.fixture
def replicas():
    server = fakeredis.FakeServer()
    clients = [fakeredis.FakeRedis(server=server) for _ in range(2)]
    return [UploadTokenStore(redis=client, namespace="test:upload:") for client in clients]


async def test_peer_redeems_all_bound_claims(replicas):
    acl = AclSpec(
        entries=(AclEntry(principal="user:alice", level=AclLevel.READ),),
        acl_mode=AclMode.RESTRICTED,
    )
    token, _ = await replicas[0].aissue(
        "acct",
        "alice",
        60,
        role=Role.ADMIN,
        actor_peer_id="peer-1",
        from_oauth=True,
        to="viking://resources/docs",
        parent="viking://resources",
        reason="remember",
        processing_mode="vectors_only",
        tags=["tag"],
        tag_mode="append",
        parse_mode="text",
        acl=acl,
        kind="skill",
        skill_target_uri="viking://agent/skills",
        skill_names=["demo"],
        list_only=True,
        uri="viking://resources/doc.pdf",
    )
    result = await replicas[1].aconsume(token)
    assert result.account_id == "acct"
    assert result.user_id == "alice"
    assert result.role == Role.ADMIN
    assert result.actor_peer_id == "peer-1"
    assert result.from_oauth is True
    assert result.to == "viking://resources/docs"
    assert result.parent == "viking://resources"
    assert result.reason == "remember"
    assert result.processing_mode == "vectors_only"
    assert result.tags == ["tag"]
    assert result.tag_mode == "append"
    assert result.parse_mode == "text"
    assert result.acl == acl
    assert result.kind == "skill"
    assert result.skill_target_uri == "viking://agent/skills"
    assert result.skill_names == ["demo"]
    assert result.list_only is True
    assert result.uri == "viking://resources/doc.pdf"
    with pytest.raises(UploadTokenError):
        replicas[0].consume(token)


async def test_concurrent_redemption_has_exactly_one_winner(replicas):
    token, _ = replicas[0].issue("acct", "alice", 60, role=Role.USER)
    results = await asyncio.gather(
        *(replicas[i % 2].aconsume(token) for i in range(32)),
        return_exceptions=True,
    )
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, UploadTokenError) for result in results) == 31


def test_namespaces_isolate_direction_and_deployment(replicas):
    token, _ = replicas[0].issue("acct", "alice", 60, role=Role.USER)
    for namespace in ("test:download:", "other:upload:"):
        other = UploadTokenStore(redis=replicas[1]._redis, namespace=namespace)
        with pytest.raises(UploadTokenError):
            other.consume(token)
    assert replicas[1].consume(token).user_id == "alice"


def test_redis_expiry_and_hashed_key(replicas):
    token, _ = replicas[0].issue("acct", "alice", 60, role=Role.USER)
    key = replicas[0]._key(token)
    assert token not in key
    assert 0 < replicas[0]._redis.ttl(key) <= 60
    replicas[0]._redis.pexpire(key, 0)
    with pytest.raises(UploadTokenError):
        replicas[1].consume(token)


def test_outage_never_falls_back_to_local_memory(replicas):
    token, _ = replicas[0].issue("acct", "alice", 60, role=Role.USER)
    replicas[0]._redis.connection_pool.connection_kwargs["server"].connected = False
    with pytest.raises(ConnectionError):
        replicas[0].consume(token)
    with pytest.raises(ConnectionError):
        replicas[0].issue("acct", "alice", 60, role=Role.USER)
    assert replicas[0]._store == {}


async def test_lifespan_closes_client_without_deleting_peer_tokens(monkeypatch):
    from openviking.server.account_stores import redis_client
    from openviking_cli.utils.config import open_viking_config

    client = fakeredis.FakeRedis()
    close = Mock(wraps=client.close)
    client.close = close
    monkeypatch.setattr(
        redis_client,
        "create_redis_client",
        lambda *a, **kw: SimpleNamespace(
            client=client,
            sentinel_clients=(),
        ),
    )
    monkeypatch.setattr(
        open_viking_config,
        "get_openviking_config",
        lambda: SimpleNamespace(
            cache=SimpleNamespace(provider="redis", params={}),
            service_name="test",
        ),
    )
    async with transfer_token_lifespan(ServerConfig(transfer_tokens={"provider": "redis"})):
        token, _ = await upload_token_store.aissue("acct", "alice", 60, role=Role.USER)
        with pytest.raises(UploadTokenError):
            await download_token_store.aconsume(token)
        peer = UploadTokenStore(redis=client, namespace="openviking:test:transfer:upload:")
    close.assert_called_once()
    assert peer.consume(token).user_id == "alice"


async def test_lifespan_rejects_redis_tokens_without_shared_cache(monkeypatch):
    from openviking_cli.utils.config import open_viking_config

    monkeypatch.setattr(
        open_viking_config,
        "get_openviking_config",
        lambda: SimpleNamespace(
            cache=None,
        ),
    )
    with pytest.raises(ValueError, match="requires cache.provider=redis"):
        async with transfer_token_lifespan(ServerConfig(transfer_tokens={"provider": "redis"})):
            pytest.fail("startup must fail")


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("OV_TEST_REDIS_URL"), reason="set OV_TEST_REDIS_URL for isolated Redis"
)
def test_token_survives_issuing_process_exit():
    import redis

    namespace = "test:" + uuid4().hex + ":upload:"
    code = """
import os, sys
import redis
from openviking.server.upload_token_store import UploadTokenStore
store = UploadTokenStore(redis=redis.Redis.from_url(os.environ['OV_TEST_REDIS_URL']), namespace=sys.argv[1])
token, _ = store.issue('acct', 'alice', 60, role='user', uri='viking://resources/doc.pdf')
print(token)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, namespace],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    token = result.stdout.strip().splitlines()[-1]
    client = redis.Redis.from_url(os.environ["OV_TEST_REDIS_URL"])
    try:
        peer = UploadTokenStore(redis=client, namespace=namespace)
        assert peer.consume(token).uri == "viking://resources/doc.pdf"
        with pytest.raises(UploadTokenError):
            peer.consume(token)
    finally:
        client.close()
