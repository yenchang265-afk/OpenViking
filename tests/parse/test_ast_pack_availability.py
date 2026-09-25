# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0

import threading
import time
from unittest.mock import Mock

from openviking.parse.parsers.code.ast.pack_availability import PackAvailability


def _availability(downloaded=(), manifest=("python", "go"), download=None, timeout=1.0):
    return PackAvailability(
        downloaded_languages=lambda: list(downloaded),
        manifest_languages=lambda: list(manifest),
        download=download or Mock(return_value=1),
        timeout_seconds=timeout,
    )


def test_cached_language_is_available_without_download():
    download = Mock()
    availability = _availability(downloaded=("python",), download=download)

    assert availability.ensure("python")
    download.assert_not_called()


def test_language_outside_manifest_is_unavailable_without_download():
    download = Mock()
    availability = _availability(download=download)

    assert not availability.ensure("brainfuck")
    download.assert_not_called()


def test_language_outside_manifest_does_not_disable_other_downloads():
    manifest = Mock(return_value=["python"])
    download = Mock(return_value=1)
    availability = PackAvailability(
        downloaded_languages=lambda: [],
        manifest_languages=manifest,
        download=download,
        timeout_seconds=1.0,
    )

    assert not availability.ensure("brainfuck")
    assert not availability.ensure("brainfuck")
    assert availability.ensure("python")
    download.assert_called_once_with(["python"])


def test_manifest_fetch_error_disables_further_downloads():
    manifest = Mock(side_effect=RuntimeError("Failed to fetch manifest"))
    download = Mock()
    availability = PackAvailability(
        downloaded_languages=lambda: [],
        manifest_languages=manifest,
        download=download,
        timeout_seconds=1.0,
    )

    assert not availability.ensure("python")
    assert not availability.ensure("go")
    manifest.assert_called_once()
    download.assert_not_called()


def test_manifest_fetch_timeout_returns_promptly_and_disables_further_downloads():
    release = threading.Event()
    manifest = Mock(side_effect=lambda: release.wait(5) and [])
    availability = PackAvailability(
        downloaded_languages=lambda: [],
        manifest_languages=manifest,
        download=Mock(),
        timeout_seconds=0.05,
    )

    started = time.monotonic()
    try:
        assert not availability.ensure("python")
        assert not availability.ensure("go")
        assert time.monotonic() - started < 2
    finally:
        release.set()
    manifest.assert_called_once()


def test_successful_download_is_remembered():
    download = Mock(return_value=1)
    availability = _availability(download=download)

    assert availability.ensure("python")
    assert availability.ensure("python")
    download.assert_called_once_with(["python"])


def test_download_error_disables_further_downloads():
    download = Mock(side_effect=RuntimeError("Download error: connection refused"))
    availability = _availability(download=download)

    assert not availability.ensure("python")
    assert not availability.ensure("go")
    download.assert_called_once_with(["python"])


def test_download_timeout_returns_promptly_and_disables_further_downloads():
    release = threading.Event()
    download = Mock(side_effect=lambda _names: release.wait(5))
    availability = _availability(download=download, timeout=0.05)

    started = time.monotonic()
    try:
        assert not availability.ensure("python")
        assert time.monotonic() - started < 2
        assert not availability.ensure("go")
    finally:
        release.set()
    download.assert_called_once_with(["python"])


def test_cached_language_still_available_after_network_failure():
    download = Mock(side_effect=RuntimeError("offline"))
    availability = _availability(downloaded=("go",), download=download)

    assert not availability.ensure("python")
    assert availability.ensure("go")


def test_cache_listing_error_falls_back_to_download():
    download = Mock(return_value=1)
    availability = PackAvailability(
        downloaded_languages=Mock(side_effect=OSError("unreadable cache")),
        manifest_languages=lambda: ["python"],
        download=download,
        timeout_seconds=1.0,
    )

    assert availability.ensure("python")
    download.assert_called_once_with(["python"])


def test_download_disallowed_uses_cache_only_without_marking_failure():
    manifest = Mock(return_value=["python"])
    download = Mock(return_value=1)
    availability = PackAvailability(
        downloaded_languages=lambda: [],
        manifest_languages=manifest,
        download=download,
        timeout_seconds=1.0,
    )

    assert not availability.ensure("python", allow_download=False)
    manifest.assert_not_called()
    download.assert_not_called()
    assert availability.ensure("python")
    download.assert_called_once_with(["python"])
