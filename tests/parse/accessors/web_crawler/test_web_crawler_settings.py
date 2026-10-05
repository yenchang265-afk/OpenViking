# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0

from openviking.parse.accessors.web_crawler.config import CrawlConfig
from openviking.parse.accessors.web_crawler.web_crawler import _build_settings


def test_download_size_is_capped_to_max_html_bytes():
    """Scrapy must abort oversized bodies instead of buffering up to 1 GiB."""
    settings = _build_settings(CrawlConfig(max_html_bytes=4096))

    assert settings.getint("DOWNLOAD_MAXSIZE") == 4096
    assert settings.getint("DOWNLOAD_WARNSIZE") == 0
