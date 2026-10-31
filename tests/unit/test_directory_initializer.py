from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest

from openviking.core.directories import PRESET_DIRECTORIES, DirectoryInitializer
from openviking.core.namespace import (
    canonical_user_root,
    is_session_uri,
    may_include_hidden_actor_peers,
)
from openviking.server.identity import RequestContext, Role
from openviking_cli.session.user_id import UserIdentifier


class _FakeVikingDB:
    def __init__(self):
        self.embedding_messages = []
        self.get_calls = []

    async def get(self, ids, ctx):
        self.get_calls.append((ids, ctx))
        return []

    async def enqueue_embedding_msg(self, message):
        self.embedding_messages.append(message)


class _FakeVikingFS:
    def __init__(self):
        self.contexts = {}

    async def read_file(self, uri, ctx):
        directory, filename = uri.rsplit("/", 1)
        name = filename.removeprefix(".").removesuffix(".md")
        if directory not in self.contexts or name not in self.contexts[directory]:
            raise FileNotFoundError(uri)
        return self.contexts[directory][name]

    async def write_context(self, uri, abstract="", overview="", is_leaf=False, ctx=None):
        if ctx.actor_peer_id and may_include_hidden_actor_peers(uri, ctx):
            raise PermissionError(f"actor peer cannot mutate {uri}")
        context = self.contexts.setdefault(uri, {})
        if abstract:
            context["abstract"] = abstract
        if overview:
            context["overview"] = overview
        context["is_leaf"] = is_leaf


@pytest.mark.asyncio
async def test_initialize_account_workspace_batches_preset_directories(monkeypatch):
    vikingdb = _FakeVikingDB()
    viking_fs = _FakeVikingFS()
    viking_fs.contexts["viking://agent"] = {}
    viking_fs.contexts["viking://agent/tools"] = {"abstract": "Existing tool configuration"}
    initializer = DirectoryInitializer(vikingdb, viking_fs=viking_fs)
    ctx = RequestContext(user=UserIdentifier("acme", "alice"), role=Role.ADMIN)

    account_count, user_count = await initializer.initialize_account_workspace(ctx)

    user_root = canonical_user_root(ctx)
    expected_user_uris = {
        user_root,
        *(f"{user_root}/{child.path}" for child in PRESET_DIRECTORIES["user"].children),
    }
    expected_agent_uris = {
        "viking://agent",
        "viking://agent/skills",
        "viking://agent/endpoints",
        "viking://agent/tools",
        "viking://agent/payments",
    }
    expected_uris = {"viking://resources", *expected_agent_uris, *expected_user_uris}
    assert account_count == 6
    assert user_count == len(expected_user_uris)
    assert set(viking_fs.contexts) == expected_uris
    assert f"{user_root}/memories/preferences" not in viking_fs.contexts
    for uri in expected_agent_uris:
        assert viking_fs.contexts[uri]["abstract"]
        assert viking_fs.contexts[uri]["overview"]
    assert viking_fs.contexts["viking://agent/tools"]["abstract"] == "Existing tool configuration"
    assert len(vikingdb.get_calls) == 1

    assert await initializer.initialize_account_directories(ctx) == 0
    assert set(viking_fs.contexts) == expected_uris
    vectorized_uris = {uri for uri in expected_uris if not is_session_uri(uri)}
    assert len(vikingdb.get_calls[0][0]) == 2 * len(vectorized_uris)
    assert len(vikingdb.embedding_messages) == 2 * len(vectorized_uris)
    for message in vikingdb.embedding_messages:
        uri = message.context_data["uri"]
        if uri in expected_agent_uris:
            name = "abstract" if message.context_data["level"] == 0 else "overview"
            assert message.message == viking_fs.contexts[uri][name]
            assert message.context_data["parent_uri"] == (
                None if uri == "viking://agent" else "viking://agent"
            )

    malformed_abstract = "---\ndirectory: viking://resources/\n"
    viking_fs.contexts["viking://resources"]["abstract"] = malformed_abstract

    second_account_count, second_user_count = await initializer.initialize_account_workspace(ctx)

    assert (second_account_count, second_user_count) == (0, 0)
    assert viking_fs.contexts["viking://resources"]["abstract"] == malformed_abstract
    assert set(viking_fs.contexts) == expected_uris
    assert len(vikingdb.get_calls) == 1

    storage_error = PermissionError("storage access denied")
    monkeypatch.setattr(viking_fs, "read_file", AsyncMock(side_effect=storage_error))
    with pytest.raises(PermissionError) as exc_info:
        await initializer.initialize_account_workspace(ctx)
    assert exc_info.value is storage_error


@pytest.mark.asyncio
async def test_initialize_user_directories_ignores_actor_peer_view_for_preset_structure():
    vikingdb = _FakeVikingDB()
    viking_fs = _FakeVikingFS()
    initializer = DirectoryInitializer(vikingdb, viking_fs=viking_fs)
    ctx = RequestContext(
        user=UserIdentifier("acme", "support-bot"),
        role=Role.USER,
        actor_peer_id="customer-a",
    )

    count = await initializer.initialize_user_directories(ctx)

    user_root = canonical_user_root(ctx)
    expected_uris = {
        user_root,
        *(f"{user_root}/{child.path}" for child in PRESET_DIRECTORIES["user"].children),
    }
    assert count == len(expected_uris)
    assert set(viking_fs.contexts) == expected_uris


@pytest.mark.asyncio
async def test_system_assets_sync_only_for_account_initialization():
    synchronizer = SimpleNamespace(sync=AsyncMock())
    initializer = DirectoryInitializer(
        _FakeVikingDB(),
        viking_fs=_FakeVikingFS(),
        system_asset_synchronizer=synchronizer,
    )
    ctx = RequestContext(user=UserIdentifier("acme", "alice"), role=Role.ADMIN)

    await initializer.initialize_account_workspace(ctx, sync_system_assets=False)
    synchronizer.sync.assert_not_awaited()

    await initializer.initialize_account_workspace(ctx)
    await initializer.initialize_account_directories(ctx)
    await initializer.initialize_user_directories(ctx)

    assert synchronizer.sync.await_args_list == [call(ctx), call(ctx)]


def test_preset_directory_uris_cover_seeded_directories_only():
    from openviking.core.directories import preset_directory_uris

    ctx = RequestContext(user=UserIdentifier("acme", "alice"), role=Role.USER)
    user_root = canonical_user_root(ctx)

    uris = preset_directory_uris(ctx)

    assert {
        "viking://resources",
        "viking://agent",
        "viking://agent/skills",
        user_root,
        f"{user_root}/memories",
        f"{user_root}/resources",
        f"{user_root}/privacy",
        f"{user_root}/peers",
    } <= uris
    assert f"{user_root}/memories/preferences" not in uris
    assert "viking://resources/proj" not in uris


def _raise_lock_conflict(uri):
    """Mirror VikingFS.write_context, which re-raises a PathLock conflict as IOError."""
    from openviking.storage.errors import LockAcquisitionError

    try:
        raise LockAcquisitionError("lock acquire timed out after 0ms")
    except LockAcquisitionError as e:
        raise IOError(f"Failed to write {uri}: {e}")


class _ContendedVikingFS(_FakeVikingFS):
    """Fails writes to chosen URIs with a lock conflict, as when a peer holds the lock."""

    def __init__(self, conflicts, on_conflict=None):
        super().__init__()
        self.conflicts = dict(conflicts)
        self.on_conflict = on_conflict
        self.write_calls = []

    async def write_context(self, uri, abstract="", overview="", is_leaf=False, ctx=None):
        self.write_calls.append(uri)
        if self.conflicts.get(uri, 0) > 0:
            self.conflicts[uri] -= 1
            if self.on_conflict is not None:
                self.on_conflict(self, uri)
            _raise_lock_conflict(uri)
        await super().write_context(uri, abstract, overview, is_leaf, ctx)


@pytest.fixture
def no_lock_backoff(monkeypatch):
    monkeypatch.setattr("openviking.core.directories._LOCK_RETRY_DELAYS", (0.0, 0.0, 0.0))


@pytest.mark.asyncio
async def test_workspace_init_adopts_directory_a_peer_created_while_locked(no_lock_backoff):
    def peer_wins(fs, uri):
        fs.contexts[uri] = {"abstract": "peer abstract", "overview": "peer overview"}

    viking_fs = _ContendedVikingFS({"viking://agent": 1}, on_conflict=peer_wins)
    initializer = DirectoryInitializer(_FakeVikingDB(), viking_fs=viking_fs)
    ctx = RequestContext(user=UserIdentifier("acme", "alice"), role=Role.ADMIN)

    await initializer.initialize_account_workspace(ctx)

    assert viking_fs.contexts["viking://agent"]["abstract"] == "peer abstract"
    assert viking_fs.write_calls.count("viking://agent") == 1
    assert "viking://agent/skills" in viking_fs.contexts


@pytest.mark.asyncio
async def test_workspace_init_retries_a_transient_lock_conflict(no_lock_backoff):
    viking_fs = _ContendedVikingFS({"viking://agent": 2})
    initializer = DirectoryInitializer(_FakeVikingDB(), viking_fs=viking_fs)
    ctx = RequestContext(user=UserIdentifier("acme", "alice"), role=Role.ADMIN)

    account_count, _ = await initializer.initialize_account_workspace(ctx)

    assert account_count == 6
    assert viking_fs.write_calls.count("viking://agent") == 3
    assert viking_fs.contexts["viking://agent"]["abstract"]


@pytest.mark.asyncio
async def test_workspace_init_gives_up_on_a_lock_that_never_clears(no_lock_backoff):
    viking_fs = _ContendedVikingFS({"viking://agent": 99})
    initializer = DirectoryInitializer(_FakeVikingDB(), viking_fs=viking_fs)
    ctx = RequestContext(user=UserIdentifier("acme", "alice"), role=Role.ADMIN)

    with pytest.raises(IOError, match="lock acquire timed out"):
        await initializer.initialize_account_workspace(ctx)
    assert viking_fs.write_calls.count("viking://agent") == 4


@pytest.mark.asyncio
async def test_workspace_init_does_not_retry_other_write_errors(no_lock_backoff):
    viking_fs = _ContendedVikingFS({})
    viking_fs.write_context = AsyncMock(side_effect=IOError("Failed to write: disk full"))
    initializer = DirectoryInitializer(_FakeVikingDB(), viking_fs=viking_fs)
    ctx = RequestContext(user=UserIdentifier("acme", "alice"), role=Role.ADMIN)

    with pytest.raises(IOError, match="disk full"):
        await initializer.initialize_account_workspace(ctx)
    agent_calls = [
        c
        for c in viking_fs.write_context.await_args_list
        if c.kwargs.get("uri") == "viking://agent"
    ]
    assert len(agent_calls) == 1
