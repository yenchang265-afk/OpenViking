"""Onboarding job contract and recovery tests against a fake platform provider."""

import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from vikingbot.studio.onboarding import OnboardingJobs
from vikingbot.studio.providers.registry import PROVIDERS
from vikingbot.studio.store import StudioStore


class FakeProvider:
    type = "fake"

    async def run_onboarding(self, jobs, run):
        pass


@pytest.fixture(autouse=True)
def fake_provider(monkeypatch):
    monkeypatch.setitem(PROVIDERS, FakeProvider.type, FakeProvider())


def make_jobs(tmp_path):
    return OnboardingJobs(SimpleNamespace(store=StudioStore(tmp_path / "studio.sqlite3")))


def run_record(**extra):
    return {
        "id": "run",
        "account": "a",
        "type": "fake",
        "name": "VikingBot",
        "identity": {"user_id": "bot", "api_key": "private-key"},
        "state": "creating",
        "request_id": str(uuid.uuid4()),
        **extra,
    }


async def test_start_is_idempotent_and_scoped(tmp_path, monkeypatch):
    jobs = make_jobs(tmp_path)
    launches = []

    def launch(run):
        jobs.service.store.save_onboarding(run)
        launches.append(run)

    monkeypatch.setattr(jobs, "launch", launch)
    body = {"type": "fake", "request_id": str(uuid.uuid4())}
    identity = {"user_id": "bot", "api_key": "private-key"}
    first = await jobs.start("a", body, identity)
    second = await jobs.start("a", body, identity)
    third = await jobs.start("a", {**body, "request_id": str(uuid.uuid4())}, identity)
    assert first["id"] == second["id"] == third["id"]
    assert len(launches) == 1
    with pytest.raises(HTTPException) as error:
        jobs.get("other-account", first["id"])
    assert error.value.status_code == 404
    assert "private-key" not in json.dumps(first)
    assert jobs.current("other-account", "fake") is None


def test_restart_keeps_checkpoints_but_not_fake_live_qr(tmp_path):
    jobs = make_jobs(tmp_path)
    run = run_record(app_id="cli_existing", create_started=True, state="configuring")
    jobs.service.store.save_onboarding(run)
    restarted = OnboardingJobs(jobs.service)
    restored = restarted.get("a", "run")
    assert restored["app_id"] == "cli_existing"
    assert restored["state"] == "interrupted"
    public = restarted.public(restored)
    assert public["can_retry"]
    assert "qr" not in public and "identity" not in public


async def test_unknown_creation_result_cannot_retry(tmp_path):
    jobs = make_jobs(tmp_path)
    run = run_record(create_started=True, state="failed")
    jobs.service.store.save_onboarding(run)
    assert not jobs.public(run)["can_retry"]
    with pytest.raises(HTTPException):
        await jobs.update("a", "run", "retry")


async def test_cannot_cancel_once_app_mutation_started(tmp_path):
    jobs = make_jobs(tmp_path)
    jobs.service.store.save_onboarding(run_record())
    with pytest.raises(HTTPException) as error:
        await jobs.update("a", "run", "cancel")
    assert error.value.status_code == 409


async def test_manual_recovery_releases_current_job_without_forgetting_app(tmp_path):
    jobs = make_jobs(tmp_path)
    run = run_record(state="failed", app_id="cli_saved")
    jobs.service.store.save_onboarding(run)
    await jobs.update("a", "run", "manual")
    assert jobs.current("a", "fake") is None
    assert jobs.get("a", "run")["app_id"] == "cli_saved"


async def test_retry_waits_for_previous_session_cleanup(tmp_path, monkeypatch):
    jobs = make_jobs(tmp_path)
    run = run_record(state="expired")
    jobs.service.store.save_onboarding(run)
    closed = []

    async def finish_cleanup():
        closed.append(True)

    import asyncio

    jobs.tasks["run"] = asyncio.create_task(finish_cleanup())

    def launch(restarted):
        assert closed == [True]
        restarted["state"] = "initializing"

    monkeypatch.setattr(jobs, "launch", launch)
    result = await jobs.update("a", "run", "retry")
    assert result["state"] == "initializing"
