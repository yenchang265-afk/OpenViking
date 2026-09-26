# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Decide whether tree-sitter-language-pack can serve a language without hanging.

The language pack downloads parser libraries on first use. Behind a firewall
that silently drops traffic, every such call blocks for about a minute. Both the
manifest lookup and the download can hit the network, so they run together under
one timeout. After any failure the pack is only used for languages that are
already cached, for the rest of the process.
"""

import threading
from typing import Callable, Iterable

import tree_sitter_language_pack

from openviking_cli.utils import get_logger

logger = get_logger(__name__)

_DOWNLOAD_TIMEOUT_SECONDS = 15.0

_FETCHED = "fetched"
_NOT_IN_MANIFEST = "not_in_manifest"
_FAILED = "failed"


class PackAvailability:
    """Thread-safe, per-process record of which pack parsers are usable."""

    def __init__(
        self,
        *,
        downloaded_languages: Callable[[], Iterable[str]],
        manifest_languages: Callable[[], Iterable[str]],
        download: Callable[[list[str]], object],
        timeout_seconds: float = _DOWNLOAD_TIMEOUT_SECONDS,
    ) -> None:
        self._downloaded_languages = downloaded_languages
        self._manifest_languages = manifest_languages
        self._download = download
        self._timeout_seconds = timeout_seconds
        self._lock = threading.Lock()
        self._ready: set[str] = set()
        self._not_in_manifest: set[str] = set()
        self._network_failed = False

    def ensure(self, lang: str, *, allow_download: bool = True) -> bool:
        """Return whether the pack parser for ``lang`` is cached or was just downloaded.

        With ``allow_download=False`` only already-cached parsers count, so the
        call never touches the network.
        """

        if lang in self._ready:
            return True
        with self._lock:
            if lang in self._ready or self._is_cached(lang):
                self._ready.add(lang)
                return True
            if not allow_download or self._network_failed or lang in self._not_in_manifest:
                return False

            outcome = self._fetch_with_timeout(lang)
            if outcome == _FETCHED:
                self._ready.add(lang)
                return True
            if outcome == _NOT_IN_MANIFEST:
                self._not_in_manifest.add(lang)
                return False
            self._network_failed = True
            return False

    def _is_cached(self, lang: str) -> bool:
        try:
            return lang in set(self._downloaded_languages())
        except Exception as exc:
            logger.debug("Unable to list cached tree-sitter parsers: %s", exc)
            return False

    def _fetch_with_timeout(self, lang: str) -> str:
        """Check the manifest and download ``lang``; both may hit the network."""

        result: dict[str, object] = {}

        def _run() -> None:
            try:
                if lang not in set(self._manifest_languages()):
                    result["outcome"] = _NOT_IN_MANIFEST
                    return
                self._download([lang])
                result["outcome"] = _FETCHED
            except BaseException as exc:  # noqa: BLE001 - reported to the waiting caller
                result["error"] = exc

        # Daemon thread: a hung fetch must not block interpreter shutdown.
        worker = threading.Thread(target=_run, name=f"tslp-fetch-{lang}", daemon=True)
        worker.start()
        worker.join(self._timeout_seconds)

        if worker.is_alive():
            logger.warning(
                "tree-sitter-language-pack fetch for '%s' timed out after %.0fs; "
                "using bundled grammars for uncached languages in this process",
                lang,
                self._timeout_seconds,
            )
            return _FAILED
        if "error" in result:
            logger.warning(
                "tree-sitter-language-pack fetch for '%s' failed (%s); "
                "using bundled grammars for uncached languages in this process",
                lang,
                result["error"],
            )
            return _FAILED
        return str(result["outcome"])


_default_availability = PackAvailability(
    downloaded_languages=tree_sitter_language_pack.downloaded_languages,
    manifest_languages=tree_sitter_language_pack.manifest_languages,
    download=tree_sitter_language_pack.download,
)


def ensure_pack_language(lang: str, *, allow_download: bool = True) -> bool:
    """Return whether tree-sitter-language-pack can parse ``lang`` right now."""

    return _default_availability.ensure(lang, allow_download=allow_download)
