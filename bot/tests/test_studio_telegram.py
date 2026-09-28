"""Studio-managed Telegram bots: credential checks, allowlist and session isolation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from vikingbot.bus.events import OutboundMessage
from vikingbot.config.schema import SessionKey, TelegramChannelConfig
from vikingbot.studio.providers.registry import PROVIDERS, get_provider
from vikingbot.studio.providers.telegram.channel import StudioTelegramChannel
from vikingbot.studio.providers.telegram.provider import TelegramProvider
from vikingbot.studio.store import StudioStore

REAL_ASYNC_CLIENT = httpx.AsyncClient
TOKEN = "123456789:" + "A" * 35
OTHER_TOKEN = "987654321:" + "B" * 35


def get_me_transport(result=None, *, ok=True, status=200):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        body = {"ok": ok, "result": result} if ok else {"ok": False, "description": "Unauthorized"}
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler), seen


@pytest.fixture
def provider():
    return TelegramProvider()


def use_transport(monkeypatch, transport):
    monkeypatch.setattr(
        "vikingbot.studio.providers.telegram.provider.httpx.AsyncClient",
        lambda **kwargs: REAL_ASYNC_CLIENT(transport=transport, **kwargs),
    )


def test_telegram_is_registered():
    assert get_provider({"type": "telegram"}) is PROVIDERS["telegram"]


@pytest.mark.parametrize(
    "value",
    [{}, {"allow_from": []}, {"allow_from": ["@x"]}, {"allow_from": "alice"}, {"other": 1}],
)
def test_settings_require_a_valid_allowlist(provider, value):
    with pytest.raises(HTTPException) as error:
        provider.validate_settings(value)
    assert error.value.status_code == 400


def test_settings_normalize_usernames_and_ids(provider):
    settings = provider.validate_settings({"allow_from": [" @Alice_01 ", "42", "alice_01"]})
    assert settings == {"allow_from": ["alice_01", "42"]}


async def test_prepare_checks_token_with_telegram(provider, monkeypatch):
    transport, seen = get_me_transport(
        {"id": 123456789, "is_bot": True, "first_name": "Viking", "username": "viking_bot"}
    )
    use_transport(monkeypatch, transport)
    fields = await provider.prepare({"token": f"  {TOKEN} "})
    assert seen == [f"https://api.telegram.org/bot{TOKEN}/getMe"]
    assert fields == {
        "bot_id": "123456789",
        "token": TOKEN,
        "bot_name": "Viking",
        "bot_username": "viking_bot",
    }
    assert provider.runtime_key(fields) == "telegram__123456789"


@pytest.mark.parametrize("token", ["", "not-a-token", "123:short", "abc:" + "A" * 35])
async def test_prepare_rejects_malformed_tokens_without_network(provider, token):
    with pytest.raises(HTTPException) as error:
        await provider.prepare({"token": token})
    assert error.value.status_code == 400


async def test_prepare_reports_rejected_token_without_leaking_it(provider, monkeypatch):
    transport, _ = get_me_transport(ok=False, status=401)
    use_transport(monkeypatch, transport)
    with pytest.raises(HTTPException) as error:
        await provider.prepare({"token": TOKEN})
    assert error.value.status_code == 400
    assert TOKEN not in str(error.value.detail)


async def test_prepare_reports_unreachable_telegram(provider, monkeypatch):
    def fail(request):
        raise httpx.ConnectError("boom " + str(request.url))

    use_transport(monkeypatch, httpx.MockTransport(fail))
    with pytest.raises(HTTPException) as error:
        await provider.prepare({"token": TOKEN})
    assert error.value.status_code == 502
    assert error.value.__cause__ is None
    assert TOKEN not in str(error.value.detail)


async def test_credentials_must_belong_to_the_same_bot(provider, monkeypatch):
    record = {"bot_id": "123456789", "token": TOKEN, "bot_username": "viking_bot"}
    transport, _ = get_me_transport({"id": 987654321, "first_name": "Other"})
    use_transport(monkeypatch, transport)
    with pytest.raises(HTTPException) as error:
        await provider.credentials(record, {"token": OTHER_TOKEN})
    assert error.value.status_code == 409

    new_token = "123456789:" + "C" * 35
    transport, _ = get_me_transport({"id": 123456789, "first_name": "Viking", "username": "v"})
    use_transport(monkeypatch, transport)
    rotated = await provider.credentials(record, {"token": new_token})
    assert rotated["token"] == new_token
    assert rotated["bot_id"] == "123456789"


def test_public_fields_never_include_the_token(provider):
    record = {
        "bot_id": "123456789",
        "token": TOKEN,
        "bot_username": "viking_bot",
        "settings": {"allow_from": ["alice"]},
    }
    public = provider.public_fields(record)
    assert TOKEN not in str(public)
    assert public == {
        "app_id": "123456789",
        "bot_username": "viking_bot",
        "settings": {"allow_from": ["alice"]},
    }


def studio_record():
    return {
        "id": "conn",
        "account": "a",
        "type": "telegram",
        "bot_id": "123456789",
        "token": TOKEN,
        "bot_name": "Viking",
        "bot_username": "viking_bot",
        "settings": {"allow_from": ["alice"]},
        "identity": {"user_id": "bot-user", "api_key": "private", "role": "user"},
        "enabled": True,
        "revision": 1,
    }


def make_service(tmp_path):
    return SimpleNamespace(
        manager=SimpleNamespace(bus=SimpleNamespace(publish_inbound=AsyncMock()), channels={}),
        store=StudioStore(tmp_path / "studio.db"),
        config=SimpleNamespace(channels=[], workspace_path=tmp_path),
        runtime=lambda record: None,
    )


def test_install_registers_channel_and_agent_config(provider, tmp_path):
    service = make_service(tmp_path)
    added = []
    service.manager.add_channel = added.append
    service.config.channels = [
        {"type": "telegram", "token": "123456789:old"},
        {"type": "slack", "bot_token": "keep"},
    ]
    channel = provider.install(service, studio_record())
    assert added == [channel]
    assert channel.config.channel_key() == provider.runtime_key(studio_record())
    assert channel.config.allow_from == ["alice"]
    assert service.config.channels[0] == {"type": "slack", "bot_token": "keep"}
    assert service.config.channels[1]["token"] == TOKEN


def test_apply_settings_updates_running_allowlist(provider, tmp_path):
    service = make_service(tmp_path)
    service.manager.add_channel = lambda channel: None
    channel = provider.install(service, studio_record())
    service.runtime = lambda record: channel
    record = studio_record() | {"settings": {"allow_from": ["bobby7", "7"]}}
    provider.apply_settings(service, record)
    assert channel.config.allow_from == ["bobby7", "7"]
    assert service.config.channels[-1]["allow_from"] == ["bobby7", "7"]


def make_channel(tmp_path, publish=None):
    record = studio_record()
    config = TelegramChannelConfig(token=TOKEN, allow_from=["alice", "42"])
    bus = SimpleNamespace(publish_inbound=publish or AsyncMock())
    store = StudioStore(tmp_path / "studio.db")
    channel = StudioTelegramChannel(config, bus, record=record, store=store)
    channel._running = True
    return channel, bus, store


async def test_allowed_message_is_scoped_recorded_and_bound_to_identity(tmp_path):
    channel, bus, store = make_channel(tmp_path)
    await channel._handle_message(
        sender_id="42|Alice",
        sender_name="Alice A",
        chat_id="-100",
        content="hello",
        metadata={"message_id": 7, "is_group": True, "chat_title": "Team"},
    )
    message = bus.publish_inbound.await_args.args[0]
    assert message.session_key == SessionKey(
        type="telegram", channel_id="123456789", chat_id="studio:conn:-100"
    )
    assert message.openviking_connection["user_id"] == "bot-user"
    assert message.actor_peer_id.startswith("telegram-")
    assert "-100" not in message.actor_peer_id
    assert message.metadata["studio_managed"] is True
    assert message.metadata["chat_type"] == "group"
    [conversation] = store.conversations("conn")
    assert conversation["conversation"] == "-100"
    assert conversation["group_name"] == "Team"
    assert channel.status()["last_received"]


async def test_usernames_match_case_insensitively(tmp_path):
    channel, bus, _ = make_channel(tmp_path)
    await channel._handle_message(sender_id="1|ALICE", chat_id="5", content="hi")
    assert bus.publish_inbound.await_count == 1


async def test_unlisted_sender_never_reaches_agent_or_history(tmp_path):
    channel, bus, store = make_channel(tmp_path)
    await channel._handle_message(sender_id="99|mallory", chat_id="5", content="hi")
    bus.publish_inbound.assert_not_awaited()
    assert store.conversations("conn") == []


async def test_duplicate_telegram_message_is_ignored(tmp_path):
    channel, bus, _ = make_channel(tmp_path)
    for _ in range(2):
        await channel._handle_message(
            sender_id="42", chat_id="5", content="hi", metadata={"message_id": 1}
        )
    assert bus.publish_inbound.await_count == 1


async def test_send_strips_scope_and_records_delivery(tmp_path, monkeypatch):
    channel, _, store = make_channel(tmp_path)
    delivered = []

    async def deliver(self, msg):
        delivered.append(msg.session_key.chat_id)
        return True

    monkeypatch.setattr("vikingbot.channels.telegram.TelegramChannel.send", deliver)
    key = SessionKey(type="telegram", channel_id="123456789", chat_id="studio:conn:5")
    assert await channel.send(OutboundMessage(session_key=key, content="answer", response_id="r1"))
    assert delivered == ["5"]
    [reply] = store.history("conn", "5")
    assert reply["role"] == "assistant"
    assert reply["status"] == "sent"
    assert channel.status()["last_sent"]


async def test_send_refuses_messages_from_a_replaced_connection(tmp_path, monkeypatch):
    channel, _, store = make_channel(tmp_path)
    deliver = AsyncMock(return_value=True)
    monkeypatch.setattr("vikingbot.channels.telegram.TelegramChannel.send", deliver)
    key = SessionKey(type="telegram", channel_id="123456789", chat_id="studio:old:5")
    assert await channel.send(OutboundMessage(session_key=key, content="stale")) is False
    deliver.assert_not_awaited()
    assert store.conversations("conn") == []


async def test_failed_start_is_reported_in_status(tmp_path, monkeypatch):
    channel, _, _ = make_channel(tmp_path)
    monkeypatch.setattr(
        "vikingbot.channels.telegram.TelegramChannel.start",
        AsyncMock(side_effect=RuntimeError("secret " + TOKEN)),
    )
    await channel.start()
    status = channel.status()
    assert status["state"] == "connecting"
    assert status["last_error"]
    assert TOKEN not in status["last_error"]


def telegram_update(text, *, username="Alice", chat_type="private"):
    reply = AsyncMock()
    message = SimpleNamespace(
        text=text,
        caption=None,
        photo=None,
        voice=None,
        audio=None,
        document=None,
        chat_id=-100 if chat_type != "private" else 5,
        message_id=11,
        chat=SimpleNamespace(type=chat_type, title="Team" if chat_type != "private" else None),
        reply_text=reply,
    )
    user = SimpleNamespace(id=1, username=username, first_name="A", full_name="Alice A")
    return SimpleNamespace(message=message, effective_user=user), reply


async def test_commands_honor_username_allowlist_and_group_metadata(tmp_path):
    channel, bus, _ = make_channel(tmp_path)
    update, _ = telegram_update("/new", chat_type="group")
    await channel._forward_command(update, None)
    message = bus.publish_inbound.await_args.args[0]
    assert message.sender_id == "1|Alice"
    assert message.content == "/new"
    assert message.metadata["chat_type"] == "group"


async def test_start_ignores_unlisted_senders(tmp_path):
    channel, _, _ = make_channel(tmp_path)
    update, reply = telegram_update("/start", username="mallory1")
    await channel._on_start(update, None)
    reply.assert_not_awaited()

    update, reply = telegram_update("/start")
    await channel._on_start(update, None)
    reply.assert_awaited_once()
