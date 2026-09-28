"""Explicit platform registration. Unknown types never fall back to a default."""

from fastapi import HTTPException

from vikingbot.studio.providers.telegram.provider import TelegramProvider

PROVIDERS = {"telegram": TelegramProvider()}


def get_provider(record):
    platform = record.get("type")
    if platform not in PROVIDERS:
        raise HTTPException(400, "Unsupported IM type")
    return PROVIDERS[platform]


def validate_settings(provider, value):
    if hasattr(provider, "validate_settings"):
        return provider.validate_settings(value)
    if value:
        raise HTTPException(400, "Settings are unavailable for this platform")
    return {}
