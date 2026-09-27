"""Telegram-specific credentials, allowlist settings and channel configuration."""

import re

import httpx
from fastapi import HTTPException

from vikingbot.config.schema import TelegramChannelConfig

TOKEN_PATTERN = re.compile(r"^(\d{5,20}):[A-Za-z0-9_-]{30,64}$")
USER_ID_PATTERN = re.compile(r"^\d{1,20}$")
USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
MAX_ALLOWED_USERS = 100


class TelegramProvider:
    type = "telegram"

    def validate_settings(self, value):
        if not isinstance(value, dict) or set(value) - {"allow_from"}:
            raise HTTPException(400, "Unsupported Telegram settings")
        entries = value.get("allow_from")
        if not isinstance(entries, list) or not entries or len(entries) > MAX_ALLOWED_USERS:
            raise HTTPException(400, "Add 1–100 allowed Telegram users")
        allowed = []
        for entry in entries:
            item = str(entry).strip().removeprefix("@") if isinstance(entry, str) else ""
            if USERNAME_PATTERN.match(item):
                item = item.lower()
            elif not USER_ID_PATTERN.match(item):
                raise HTTPException(400, "Allowed users must be Telegram user IDs or @usernames")
            if item not in allowed:
                allowed.append(item)
        return {"allow_from": allowed}

    def apply_settings(self, service, record):
        allowed = self.validate_settings(record.get("settings", {}))["allow_from"]
        runtime = service.runtime(record)
        if runtime:
            runtime.config.allow_from = allowed
        for config in service.config.channels:
            if self._same_bot(config, record["bot_id"]):
                config["allow_from"] = allowed

    def runtime_key(self, record):
        return "telegram__" + record["bot_id"]

    def validate_token(self, body):
        token = str(body.get("token", "")).strip()
        match = TOKEN_PATTERN.match(token)
        if not match:
            raise HTTPException(400, "Paste the bot token from @BotFather")
        return token, match.group(1)

    async def prepare(self, body):
        token, _ = self.validate_token(body)
        bot = await self.get_me(token)
        return {
            "bot_id": str(bot["id"]),
            "token": token,
            "bot_name": bot.get("first_name") or "VikingBot",
            "bot_username": bot.get("username", ""),
        }

    async def credentials(self, record, body):
        token, _ = self.validate_token(body)
        bot = await self.get_me(token)
        if str(bot["id"]) != record["bot_id"]:
            raise HTTPException(409, "This token belongs to a different Telegram bot")
        return {**record, "token": token, "bot_username": bot.get("username", "")}

    def public_fields(self, record):
        return {
            "app_id": record["bot_id"],
            "bot_username": record.get("bot_username", ""),
            "settings": self.validate_settings(record.get("settings", {})),
        }

    def install(self, service, record):
        from vikingbot.studio.providers.telegram.channel import StudioTelegramChannel

        channel_config = TelegramChannelConfig(
            token=record["token"],
            allow_from=self.validate_settings(record.get("settings", {}))["allow_from"],
            memory_peer=[],
            memory_user=[],
        )
        channel = StudioTelegramChannel(
            channel_config,
            service.manager.bus,
            record=record,
            store=service.store,
            workspace_path=service.config.workspace_path,
        )
        service.manager.add_channel(channel)
        # Agent configuration is the same object; keep runtime channel policy in sync.
        service.config.channels = [
            c for c in service.config.channels if not self._same_bot(c, record["bot_id"])
        ]
        service.config.channels.append(channel_config.model_dump(mode="json"))
        return channel

    async def get_me(self, token):
        # The token is part of the URL, so never chain transport errors that repeat it.
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            data = response.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(502, "Cannot reach Telegram; retry the connection check") from None
        bot = data.get("result") if isinstance(data, dict) and data.get("ok") else None
        if not isinstance(bot, dict) or not bot.get("id"):
            raise HTTPException(400, "Telegram rejected the bot token")
        return bot

    def onboarding(self, record, runtime, body):
        raise HTTPException(400, "Unknown action")

    @staticmethod
    def _same_bot(config, bot_id):
        return (
            isinstance(config, dict)
            and config.get("type") == "telegram"
            and str(config.get("token", "")).split(":")[0] == bot_id
        )
