#!/usr/bin/env python3

import json
import os
import sys
from pathlib import Path

from openviking_cli.utils.config.config_loader import resolve_config_path
from openviking_cli.utils.config.consts import (
    DEFAULT_OV_CONF,
    OPENVIKING_CONFIG_ENV,
)

_USE_COLOR = (
    hasattr(sys.stdout, "isatty")
    and sys.stdout.isatty()
    and os.environ.get("TERM", "dumb") != "dumb"
    and "NO_COLOR" not in os.environ
)


def _color(text: str, code: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def _log_info(message: str) -> None:
    print(_color(f"  │ {message}", "2"))


def _log_warn(message: str) -> None:
    print(f"  {_color('!', '33')} {message}")


def _log_ok(message: str) -> None:
    print(f"  {_color('✓', '32')} {message}")


def _log_error(message: str) -> None:
    print(f"  {_color('✗', '31')} {message}", file=sys.stderr)


def _is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _prompt_text(prompt: str, default: str | None = None) -> str:
    print(f"\n  {_color('?', '33')} {prompt}")
    if default:
        print(f"    {_color('預設:', '2')} {default}")
    raw = input(f"    {_color('>', '32')} ").strip()
    if not raw and default is not None:
        return default
    return raw


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        raw = f.read()
    return json.loads(raw)


def _resolve_ov_conf_path() -> Path:
    configured_path = os.environ.get(OPENVIKING_CONFIG_ENV, "").strip()
    if configured_path:
        return Path(configured_path).expanduser()

    resolved = resolve_config_path(None, OPENVIKING_CONFIG_ENV, DEFAULT_OV_CONF)
    default_path = (
        str(resolved) if resolved is not None else str(Path.home() / ".openviking" / "ov.conf")
    )

    if _is_interactive():
        _log_info(f"OpenViking 配置預設路徑: {default_path}")
        chosen = _prompt_text("直接回車使用預設，或輸入新路徑", default=default_path)
    else:
        chosen = default_path
    return Path(chosen).expanduser()


def _warn_deprecated_or_conflicting_fields(ov_data: dict) -> None:
    ov_server = (ov_data.get("bot") or {}).get("ov_server") or {}
    server_auth_mode = str((ov_data.get("server") or {}).get("auth_mode") or "").strip().lower()
    if str(ov_server.get("root_api_key") or "").strip():
        _log_warn("bot.ov_server.root_api_key 已廢棄，評測不會再把它當作認證 key 使用。")
    api_key_type = str(ov_server.get("api_key_type") or "").strip().lower()
    if api_key_type and api_key_type != "user" and server_auth_mode != "trusted":
        _log_warn("bot.ov_server.api_key_type 不是 user；後續會在 User key 校驗通過後同步為 user。")


def main() -> int:
    try:
        ov_conf_path = _resolve_ov_conf_path()
        if not ov_conf_path.exists():
            _log_error(f"ov.conf 不存在: {ov_conf_path}")
            return 1

        try:
            ov_data = _load_json(ov_conf_path)
        except Exception as exc:
            _log_error(f"讀取 ov.conf 失敗: {exc}")
            return 1

        _warn_deprecated_or_conflicting_fields(ov_data)
        _log_ok("本地配置可讀取；將繼續連線 OpenViking 校驗 API key。")
        return 0
    except KeyboardInterrupt:
        _log_error("使用者取消。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
