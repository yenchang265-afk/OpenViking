# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""``server.upload`` limits and the deprecated ``temp_upload.shared_max_size_bytes`` alias."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from openviking.server import config as server_config_module
from openviking.server import temp_upload_store
from openviking.server.config import ServerConfig
from openviking_cli.exceptions import InvalidArgumentError

MIB = 1024 * 1024


def test_upload_limits_default_to_spec_values():
    upload = ServerConfig().upload

    assert upload.max_file_bytes == 2048 * MIB
    assert upload.max_session_bytes == 5120 * MIB
    assert upload.max_files == 10_000
    assert upload.part_size_bytes == 8 * MIB


def test_legacy_shared_max_size_bytes_maps_to_max_file_bytes(monkeypatch):
    logger = MagicMock()
    monkeypatch.setattr(server_config_module, "logger", logger)

    config = ServerConfig(temp_upload={"shared_max_size_bytes": 100 * MIB})

    assert config.upload.max_file_bytes == 100 * MIB
    logger.warning.assert_called_once()
    assert "shared_max_size_bytes" in logger.warning.call_args.args[0]


def test_explicit_max_file_bytes_wins_over_legacy_alias(monkeypatch):
    monkeypatch.setattr(server_config_module, "logger", MagicMock())

    config = ServerConfig(
        temp_upload={"shared_max_size_bytes": 100 * MIB},
        upload={"max_file_bytes": 300 * MIB},
    )

    assert config.upload.max_file_bytes == 300 * MIB


@pytest.mark.parametrize(
    "upload",
    [
        {"max_file_bytes": 0},
        {"max_session_bytes": -1},
        {"max_files": 0},
        {"part_size_bytes": 1024},
        {"max_file_bytes": 10 * MIB, "max_session_bytes": 5 * MIB},
    ],
)
def test_invalid_upload_limits_are_rejected(upload):
    with pytest.raises(ValidationError):
        ServerConfig(upload=upload)


class _UploadFile:
    filename = "big.bin"

    def __init__(self, size: int) -> None:
        self._remaining = size

    async def read(self, size: int) -> bytes:
        chunk = min(size, self._remaining)
        self._remaining -= chunk
        return b"x" * chunk


@pytest.mark.asyncio
async def test_temp_upload_store_enforces_max_file_bytes(monkeypatch, tmp_path: Path):
    config = ServerConfig(upload={"max_file_bytes": 8 * MIB, "max_session_bytes": 8 * MIB})
    monkeypatch.setattr(
        temp_upload_store,
        "get_openviking_config",
        lambda: SimpleNamespace(storage=SimpleNamespace(get_upload_temp_dir=lambda: tmp_path)),
    )
    store = temp_upload_store.TempUploadStore(config)

    assert await store.save_upload(_UploadFile(8 * MIB), "local", object())
    with pytest.raises(InvalidArgumentError, match="exceeds size limit"):
        await store.save_upload(_UploadFile(8 * MIB + 1), "local", object())
