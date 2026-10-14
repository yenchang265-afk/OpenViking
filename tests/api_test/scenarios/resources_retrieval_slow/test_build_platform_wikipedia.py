import pytest
from build_test_helpers import (
    assert_resource_indexed,
    assert_root_uri_valid,
    assert_source_format,
)


class TestBuildPlatformWikipedia:
    """TC-P05 Wikipedia 平臺 URL 構建測試"""

    WIKI_URLS = [
        "https://en.wikipedia.org/api/rest_v1/page/summary/Software_testing",
        "https://en.wikipedia.org/wiki/Software_testing",
    ]

    def test_build_wikipedia_page(self, api_client):
        """TC-P05 Wikipedia頁面構建：驗證 wikipedia.org URL 走 WEBPAGE 路由且內容可檢索"""
        for wiki_url in self.WIKI_URLS:
            response = api_client.add_resource(path=wiki_url, wait=True)
            data = response.json()
            if response.status_code == 403:
                assert data["status"] == "error"
                error = data["error"]
                assert error["code"] == "PERMISSION_DENIED"
                assert error["details"]["upstream_status_code"] == 403
                assert error["details"]["source"] == wiki_url
                continue
            if response.status_code == 412:
                assert data["status"] == "error"
                assert data["error"]["code"] == "FAILED_PRECONDITION"
                assert "site disallows crawlers" in data["error"]["message"]
                continue

            assert response.status_code == 200, response.text
            assert data.get("status") == "ok"

            result = data.get("result", {})
            root_uri = result.get("root_uri")
            assert root_uri, "Wikipedia頁面構建應返回root_uri, 實際為空"
            assert_root_uri_valid(root_uri)

            meta = result.get("meta", {})
            assert meta.get("url_type") in ("webpage", "download_text", "download_html", None), (
                f"meta.url_type 應為 webpage/download_text/download_html, 實際: {meta.get('url_type')}"
            )

            assert_source_format(api_client, root_uri, ["html", "markdown"])

            stat_resp = api_client.fs_stat(root_uri)
            assert stat_resp.status_code == 200

            assert_resource_indexed(api_client, root_uri, "software testing")

            print(f"✓ TC-P05 Wikipedia頁面構建通過, root_uri: {root_uri}")
            return

        pytest.skip("所有 Wikipedia URL 均拒絕訪問或禁止爬蟲，未驗證內容構建")
