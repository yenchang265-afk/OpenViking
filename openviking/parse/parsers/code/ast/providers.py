# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Routing for language-pack, bundled-grammar, and LLM-fallback code summaries."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from openviking.parse.parsers.code.ast.aider_repomap import (
    _extract_with_grep_ast,
    has_tag_query,
    tag_query_language,
)
from openviking.parse.parsers.code.ast.bundled_grammars import (
    extract_bundled_skeleton,
    supports_bundled_skeleton,
)
from openviking.parse.parsers.code.ast.pack_availability import ensure_pack_language
from openviking.parse.parsers.code.ast.process_engine import (
    _detect_process_language,
    extract_process_skeleton,
    supports_process_skeleton,
)
from openviking_cli.utils import get_logger

logger = get_logger(__name__)

_IMPORT_ONLY_PREFIXES = ("#", "imports:", "module:", "language:")


def supports_code_skeleton(file_name: str) -> bool:
    """Return whether any skeleton extractor recognizes the file."""

    return (
        has_tag_query(file_name)
        or supports_process_skeleton(file_name)
        or supports_bundled_skeleton(file_name)
    )


@dataclass(frozen=True)
class SkeletonExtractionResult:
    text: Optional[str]
    provider: str
    should_fallback_to_llm: bool
    reason: str


def is_skeleton_useful(text: Optional[str]) -> bool:
    """Return whether a skeleton contains extractor-produced structure."""

    if not text or not text.strip():
        return False
    return any(
        line.strip() and not line.strip().startswith(_IMPORT_ONLY_PREFIXES)
        for line in text.splitlines()
    )


def extract_skeleton_result(
    file_name: str,
    content: str,
    verbose: bool = False,
    *,
    allow_download: bool = True,
) -> SkeletonExtractionResult:
    """Extract a skeleton, signalling when the caller must use LLM fallback.

    tree-sitter-language-pack is used when its parser for the file's language is
    cached or can be downloaded. Otherwise (e.g. behind a firewall) the grammars
    bundled as pip dependencies are used. The LLM is the last resort.

    A first-time parser download may block for up to the download timeout; call
    this off the event loop, or pass ``allow_download=False`` on latency-sensitive
    paths to use only cached parsers.
    """

    pack_language = _pack_language(file_name)
    if pack_language is not None and ensure_pack_language(
        pack_language, allow_download=allow_download
    ):
        return _extract_with_language_pack(file_name, content, verbose)

    reasons = ["language pack parser unavailable" if pack_language else "no language pack route"]
    text = extract_bundled_skeleton(file_name, content)
    if is_skeleton_useful(text):
        return SkeletonExtractionResult(text, "bundled", False, "bundled grammar succeeded")
    if supports_bundled_skeleton(file_name):
        reasons.append("bundled grammar produced no useful skeleton")
    else:
        reasons.append("no bundled grammar")
    return _llm_fallback(file_name, "; ".join(reasons))


def _pack_language(file_name: str) -> Optional[str]:
    """Return the language-pack parser name the pack route would load."""

    if has_tag_query(file_name):
        return tag_query_language(file_name)
    return _detect_process_language(file_name)


def _extract_with_language_pack(
    file_name: str,
    content: str,
    verbose: bool,
) -> SkeletonExtractionResult:
    reasons: list[str] = []
    if has_tag_query(file_name):
        text = None
        if content:
            rel_name = Path(file_name).name or "source.txt"
            text = _extract_with_grep_ast(file_name, rel_name, content, verbose)
        if is_skeleton_useful(text):
            return SkeletonExtractionResult(text, "aider_repomap", False, "maintained tags query")
        return _llm_fallback(file_name, "tags query produced no useful skeleton")
    else:
        reasons.append("no maintained tags query")

    text = extract_process_skeleton(file_name, content, verbose=verbose)
    if is_skeleton_useful(text):
        return SkeletonExtractionResult(text, "process", False, "process extraction succeeded")
    reasons.append("process produced no useful skeleton")
    return _llm_fallback(file_name, "; ".join(reasons))


def _llm_fallback(file_name: str, reason: str) -> SkeletonExtractionResult:
    logger.debug("Code skeleton requires LLM fallback for '%s': %s", file_name, reason)
    return SkeletonExtractionResult(None, "llm", True, reason)
