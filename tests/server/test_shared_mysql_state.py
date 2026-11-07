"""Real database contracts. Run against an isolated ov_stateless_test database."""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from openviking.observability.events import ObservabilityEvent
from openviking.observability.usage_audit.mysql_store import MySQLUsageAuditStore
from openviking.observability.usage_audit.mysql_store import metadata as usage_metadata
from openviking.observability.usage_audit.sqlite_store import SQLiteUsageAuditStore
from openviking.server.oauth.mysql_store import MySQLOAuthStore
from openviking.server.oauth.mysql_store import metadata as oauth_metadata

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("OV_TEST_MYSQL_PORT"),
        reason="set OV_TEST_MYSQL_PORT for an isolated test database",
    ),
]


@pytest.fixture(scope="module")
def mysql_params():
    params = {
        "host": "127.0.0.1",
        "port": int(os.environ["OV_TEST_MYSQL_PORT"]),
        "user": "root",
        "password": "ov-test-only",
        "database": "ov_stateless_test",
    }
    engine = create_engine(
        URL.create(
            "mysql+pymysql",
            **{
                "username": params["user"],
                "password": params["password"],
                "host": params["host"],
                "port": params["port"],
                "database": params["database"],
            },
        )
    )
    try:
        oauth_metadata.create_all(engine)
        usage_metadata.create_all(engine)
        yield params
    finally:
        engine.dispose()


async def test_oauth_cross_replica_one_shot_and_replay_tombstones(mysql_params):
    service = "test-" + uuid4().hex
    stores = [MySQLOAuthStore(service_name=service, params=mysql_params) for _ in range(2)]
    other = MySQLOAuthStore(service_name="other-" + uuid4().hex, params=mysql_params)
    await asyncio.gather(*(store.initialize() for store in [*stores, other]))
    claims = {
        "client_id": "client",
        "account_id": "acct",
        "user_id": "alice",
        "role": "user",
        "scope": "mcp",
        "resource": "https://example.test/mcp",
        "authorizing_key_fp": "a" * 64,
    }
    try:
        await stores[0].register_client(
            client_id="client", redirect_uris=["https://example.test/cb"]
        )
        assert (await stores[1].get_client("client"))["client_id"] == "client"
        assert await other.get_client("client") is None
        await stores[0].insert_auth_code(
            code_plain="code",
            ttl_seconds=60,
            redirect_uri="https://example.test/cb",
            code_challenge="challenge",
            code_challenge_method="S256",
            **claims,
        )
        results = await asyncio.gather(
            *(stores[i % 2].consume_auth_code("code") for i in range(16))
        )
        assert sum(item is not None for item in results) == 1
        await stores[0].insert_refresh(token_plain="refresh", ttl_seconds=60, **claims)
        results = await asyncio.gather(
            *(
                stores[i % 2].consume_refresh(token_plain="refresh", replaced_by_plain="next")
                for i in range(16)
            )
        )
        assert sum(item is not None for item in results) == 1
        await stores[1].gc_expired()
        assert await stores[0].is_refresh_known_but_consumed("refresh")
        await stores[0].insert_access(token_plain="access", ttl_seconds=60, **claims)
        assert await stores[1].load_access("access") is not None
        assert await stores[1].revoke_access("access")
        assert await stores[0].load_access("access") is None
        await stores[0].insert_access(token_plain="expired", ttl_seconds=-1, **claims)
        assert await stores[1].load_access("expired") is None
        pending = await stores[0].create_pending_authorization(
            client_id="client",
            redirect_uri="https://example.test/cb",
            redirect_uri_provided_explicitly=True,
            code_challenge="challenge",
            scopes=["mcp"],
            resource=None,
            state="state",
            display_code="ABC123",
        )
        assert (await stores[1].find_pending_by_display_code(" abc123 "))["pending_id"] == pending
        results = await asyncio.gather(
            *(
                store.mark_pending_verified(
                    pending_id=pending,
                    account_id="acct",
                    user_id="alice",
                    role="user",
                    verified_key_fp="a" * 64,
                )
                for store in stores
            )
        )
        assert results.count(True) == 1
        assert (await stores[0].load_pending_authorization(pending))["verified"] is True
        await stores[1].revoke_tokens(account_id="acct", user_id="alice")
        assert await stores[0].load_pending_authorization(pending) is None
    finally:
        await asyncio.gather(*(store.close() for store in [*stores, other]))


async def test_usage_matches_sqlite_and_sums_concurrent_replicas(mysql_params, tmp_path):
    service = "test-" + uuid4().hex
    stores = [MySQLUsageAuditStore(service_name=service, params=mysql_params) for _ in range(2)]
    local = SQLiteUsageAuditStore(tmp_path / "audit.sqlite")
    await asyncio.gather(*(store.initialize() for store in [*stores, local]))
    timestamp = datetime(2026, 11, 6, 12, 30, tzinfo=timezone.utc)
    events = [
        ObservabilityEvent(
            event_name="vlm.call",
            payload={"prompt_tokens": 7, "completion_tokens": 3, "model_name": "model"},
            timestamp=timestamp,
            account_id="acct",
            user_id="alice",
        ),
        ObservabilityEvent(
            event_name="http.request",
            payload={
                "method": "POST",
                "route": "/api/v1/search/search",
                "api_type": "search",
                "status": 200,
                "duration_ms": 1.5,
            },
            timestamp=timestamp,
            account_id="acct",
            user_id="alice",
            request_id="request-1",
        ),
    ]
    try:
        await asyncio.gather(*(stores[i % 2].record_batch(events) for i in range(8)))
        await local.record_batch(events * 8)
        scope = {"account_id": "acct", "user_id": "alice"}
        day = dict(**scope, user_date="2026-11-06", tz=timezone.utc)
        assert await stores[1].get_today_tokens(**day) == await local.get_today_tokens(**day)
        window = dict(
            **scope,
            utc_start=timestamp - timedelta(hours=1),
            utc_end=timestamp + timedelta(hours=1),
        )
        assert await stores[1].get_window_tokens(**window) == await local.get_window_tokens(
            **window
        )
        assert await stores[1].get_minute_tokens(**window) == await local.get_minute_tokens(
            **window
        )
        assert await stores[1].get_today_retrievals(**day) == await local.get_today_retrievals(
            **day
        )
        series = dict(
            **scope, start_user_date="2026-11-05", end_user_date="2026-11-07", tz=timezone.utc
        )
        assert await stores[1].get_token_series(
            **series, bucket="day"
        ) == await local.get_token_series(**series, bucket="day")
        assert await stores[1].get_context_commit_heatmap(
            **series, bucket="4h"
        ) == await local.get_context_commit_heatmap(**series, bucket="4h")
        assert await stores[1].query_audit_logs(**scope) == await local.query_audit_logs(**scope)
        samples = dict(**scope, utc_start=timestamp - timedelta(hours=1))
        assert await stores[1].get_request_samples(**samples) == await local.get_request_samples(
            **samples
        )
        await stores[0].delete_data(**scope)
        assert (await stores[1].get_today_tokens(**day))["total"] == 0
        assert (await stores[1].query_audit_logs(**scope))["total"] == 0
    finally:
        await asyncio.gather(*(store.close() for store in [*stores, local]))


async def test_usage_retention_timezones_filters_and_owner_isolation(mysql_params, tmp_path):
    service = "test-" + uuid4().hex
    options = {
        "usage_retention_days": 2,
        "audit_retention_days": 2,
        "audit_retention_per_account": 2,
    }
    shared = MySQLUsageAuditStore(service_name=service, params=mysql_params, **options)
    local = SQLiteUsageAuditStore(tmp_path / "retention.sqlite", **options)
    other = MySQLUsageAuditStore(service_name="other-" + uuid4().hex, params=mysql_params)
    stores = [shared, local, other]
    await asyncio.gather(*(store.initialize() for store in stores))
    try:
        for day in (1, 5, 6):
            events = []
            for user in ("alice", "bob"):
                timestamp = datetime(2026, 11, day, 18, 30, tzinfo=timezone.utc)
                for source in ("vlm", "rerank", "embedding"):
                    events.append(
                        ObservabilityEvent(
                            event_name=source + ".call",
                            payload={"prompt_tokens": 7, "completion_tokens": 3},
                            timestamp=timestamp,
                            account_id="acct",
                            user_id=user,
                        )
                    )
                events.append(
                    ObservabilityEvent(
                        event_name="http.request",
                        payload={
                            "method": "POST",
                            "route": "/api/v1/sessions/{session_id}/commit",
                            "status": 200,
                            "duration_ms": 1.5,
                            "request_id": f"commit-{day}-{user}",
                        },
                        timestamp=timestamp,
                        account_id="acct",
                        user_id=user,
                    )
                )
            await shared.record_batch(events)
            await local.record_batch(events)
        for tz in (timezone.utc, ZoneInfo("Asia/Kolkata"), ZoneInfo("America/New_York")):
            for user in (None, "alice", "bob"):
                scope = {"account_id": "acct", "user_id": user}
                today = dict(**scope, user_date="2026-11-06", tz=tz)
                assert await shared.get_today_tokens(**today) == await local.get_today_tokens(
                    **today
                )
                series = dict(
                    **scope, start_user_date="2026-11-01", end_user_date="2026-11-07", tz=tz
                )
                assert await shared.get_token_series(
                    **series, bucket="day"
                ) == await local.get_token_series(**series, bucket="day")
                assert await shared.get_context_commit_heatmap(
                    **series, bucket="4h"
                ) == await local.get_context_commit_heatmap(**series, bucket="4h")
        for statuses in ([], ["success"], ["2xx"], ["failed"], ["200"]):
            query = {"account_id": "acct", "statuses": statuses, "page_size": 1}
            assert await shared.query_audit_logs(**query) == await local.query_audit_logs(**query)
        assert (await other.query_audit_logs(account_id="acct"))["total"] == 0
        await shared.delete_data(account_id="acct", user_id="alice")
        assert (await shared.query_audit_logs(account_id="acct", user_id="bob"))["total"] == 1
        assert (await shared.query_audit_logs(account_id="acct", user_id="alice"))["total"] == 0
    finally:
        await asyncio.gather(*(store.close() for store in stores))


@pytest.mark.parametrize("store_class", [MySQLOAuthStore, MySQLUsageAuditStore])
async def test_failed_startup_releases_connection_and_runtime(mysql_params, store_class):
    broken = {**mysql_params, "database": "ov_stateless_test_missing"}
    store = store_class(service_name="test-" + uuid4().hex, params=broken)
    with pytest.raises(Exception, match="Unknown database"):
        await asyncio.wait_for(store.initialize(), timeout=10)
    assert store._engine is None
    assert store._mysql_lease is False
    await store.close()
