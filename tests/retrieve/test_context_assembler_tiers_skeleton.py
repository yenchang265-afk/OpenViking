# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest.mock import Mock

from openviking.parse.parsers.code.ast import SkeletonExtractionResult
from openviking.retrieve.context_assembler import tiers


def test_code_overview_never_downloads_parsers(monkeypatch):
    extract = Mock(
        return_value=SkeletonExtractionResult(
            text="# sample.py [Python]\n\ndef run()",
            provider="process",
            should_fallback_to_llm=False,
            reason="process extraction succeeded",
        )
    )
    monkeypatch.setattr(tiers, "extract_skeleton_result", extract)
    candidate = SimpleNamespace(is_directory=False, base_uri="viking://resources/repo/sample.py")

    overview = tiers.overview_from_content(candidate, "def run():\n    pass\n")

    assert overview == "# sample.py [Python]\n\ndef run()"
    assert extract.call_args.kwargs == {"allow_download": False}
