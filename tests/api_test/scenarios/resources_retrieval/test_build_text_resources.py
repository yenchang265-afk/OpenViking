import uuid

from build_test_helpers import (
    assert_resource_indexed,
    assert_root_uri_valid,
    assert_source_format,
    assert_tree_has_child_nodes,
    cleanup_temp_dir,
    create_test_file,
)


class TestBuildTextResources:
    """TC-B02, B15 文本類資源構建測試（快速用例，≤20s）"""

    def test_build_markdown_file(self, api_client):
        """TC-B02 Markdown檔案構建：驗證 .md 檔案新增後 heading 結構保留為子節點"""
        random_id = str(uuid.uuid4())[:8]
        unique_keyword = f"md_keyword_{random_id}"
        content = (
            f"# Markdown測試標題 {random_id}\n\n"
            f"包含唯一關鍵詞：{unique_keyword}\n\n"
            f"## 第一節\n\n第一段內容。\n\n"
            f"## 第二節\n\n第二段內容。\n\n"
            f"### 子節\n\n子節內容。\n"
        )

        test_file_path, temp_dir = create_test_file(content=content, suffix=".md")
        try:
            response = api_client.add_resource(path=test_file_path, wait=True)
            assert response.status_code == 200

            data = response.json()
            assert data.get("status") == "ok"

            result = data.get("result", {})
            root_uri = result.get("root_uri")
            assert_root_uri_valid(root_uri)

            stat_resp = api_client.fs_stat(root_uri)
            assert stat_resp.status_code == 200

            assert_source_format(api_client, root_uri, "markdown")

            assert_tree_has_child_nodes(api_client, root_uri, min_nodes=1)

            assert_resource_indexed(api_client, root_uri, unique_keyword)

            print(f"✓ TC-B02 Markdown檔案構建通過, root_uri: {root_uri}")
        finally:
            cleanup_temp_dir(temp_dir)

    def test_build_empty_file(self, api_client):
        """TC-B15 空檔案構建：驗證空 .txt 檔案被明確拒絕"""
        test_file_path, temp_dir = create_test_file(content="", suffix=".txt")
        try:
            response = api_client.add_resource(path=test_file_path, wait=True)
            assert response.status_code == 400, response.text
            data = response.json()
            assert data["status"] == "error"
            assert data["error"]["code"] == "INVALID_ARGUMENT"
            assert "empty" in data["error"]["message"].lower()

            print("✓ TC-B15 空檔案被拒絕並返回 INVALID_ARGUMENT")
        finally:
            cleanup_temp_dir(temp_dir)
