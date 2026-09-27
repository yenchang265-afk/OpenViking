"""Telegram channel with persisted delivery evidence and a dedicated OV identity."""

import hashlib
import uuid
from dataclasses import replace
from datetime import datetime, timezone

from loguru import logger

from vikingbot.bus.events import InboundMessage
from vikingbot.channels.telegram import TelegramChannel
from vikingbot.config.schema import SessionKey


def now():
    return datetime.now(timezone.utc).isoformat()


class StudioTelegramChannel(TelegramChannel):
    def __init__(self, config, bus, *, record, store, **kwargs):
        super().__init__(config, bus, **kwargs)
        self.record = record
        self._session_prefix = f"studio:{record['id']}:"
        self.store = store
        self.last_received = None
        self.last_sent = None
        self.last_error = None

    async def start(self):
        self.last_error = None
        try:
            await super().start()
        except Exception as exc:
            # Telegram errors can echo the request URL, which contains the bot token.
            logger.warning(
                f"Studio Telegram bot {self.record['bot_id']} stopped: {type(exc).__name__}"
            )
            self.last_error = "Cannot connect to Telegram; check the token and network"
            self._running = False

    def is_allowed(self, sender_id):
        # Telegram usernames are case-insensitive; the allowlist stores them lowercased.
        allowed = set(self.config.allow_from)
        return any(part.lower() in allowed for part in str(sender_id).split("|") if part)

    async def _handle_message(
        self,
        sender_id,
        chat_id,
        content,
        sender_name=None,
        need_reply=True,
        media=None,
        metadata=None,
    ):
        if not self._running or not self.is_allowed(sender_id):
            return
        metadata = dict(metadata or {})
        metadata["studio_managed"] = True
        metadata["chat_type"] = "group" if metadata.get("is_group") else "private"
        self.last_received = now()
        inserted = self.store.append(
            self.record["id"],
            chat_id,
            str(metadata.get("message_id") or uuid.uuid4()),
            {
                "role": "user",
                "content": content,
                "sender": sender_name or "",
                "sender_id": sender_id,
                "time": now(),
                "status": "received",
                "chat_type": metadata["chat_type"],
                "title": metadata.get("chat_title") or sender_name or "",
            },
        )
        if not inserted:
            return
        # Partition peer memory by chat, never by the installing administrator.
        peer = "telegram-" + hashlib.sha256(chat_id.encode()).hexdigest()[:24]
        await self.bus.publish_inbound(
            InboundMessage(
                sender_id=sender_id,
                sender_name=sender_name,
                session_key=SessionKey(
                    type="telegram",
                    channel_id=self.channel_id,
                    chat_id=self._session_prefix + chat_id,
                ),
                actor_peer_id=peer,
                content=content,
                need_reply=need_reply,
                media=media or [],
                metadata=metadata,
                openviking_connection=dict(self.record["identity"]),
            )
        )

    async def send(self, msg):
        # A replaced connection must never deliver an old in-flight response.
        if not msg.session_key.chat_id.startswith(self._session_prefix):
            return False
        # Only the Agent session is scoped; Telegram delivery uses the original chat ID.
        msg = replace(
            msg,
            session_key=msg.session_key.model_copy(
                update={"chat_id": msg.session_key.chat_id.removeprefix(self._session_prefix)}
            ),
        )
        accepted = await super().send(msg)
        if msg.is_normal_message:
            if accepted:
                self.last_sent = now()
            self.store.append(
                self.record["id"],
                msg.session_key.chat_id,
                msg.response_id or str(uuid.uuid4()),
                {
                    "role": "assistant",
                    "content": msg.content,
                    "sender": self.record["bot_name"],
                    "time": now(),
                    "status": "sent" if accepted else "send_failed",
                },
            )
        return accepted

    def status(self):
        # Poller evidence, never infer connection from the channel's start flag.
        updater = getattr(self._app, "updater", None)
        connected = self._running and bool(updater and updater.running)
        return {
            "state": "connected" if connected else "connecting",
            "last_received": self.last_received,
            "last_sent": self.last_sent,
            "last_error": self.last_error,
        }
