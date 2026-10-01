import uuid

from build_test_helpers import (
    assert_resource_indexed,
    assert_root_uri_valid,
    assert_source_format,
    cleanup_temp_dir,
    create_test_file,
)


class TestBuildTextResourcesSlow:
    """TC-B01, B02, B14, B15 文本類資源構建測試"""

    def test_build_txt_file(self, api_client):
        """TC-B01 純文本檔案構建：驗證 .txt 檔案新增後 source_format=text 且內容可檢索"""
        random_id = str(uuid.uuid4())[:8]
        unique_keyword = f"txt_keyword_{random_id}"
        content = f"純文本測試檔案 {random_id}\n包含唯一關鍵詞：{unique_keyword}\n用於驗證txt檔案構建產物。"

        test_file_path, temp_dir = create_test_file(content=content, suffix=".txt")
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

            assert_source_format(api_client, root_uri, ["text", "markdown"])

            assert_resource_indexed(api_client, root_uri, unique_keyword)

            print(f"✓ TC-B01 純文本檔案構建通過, root_uri: {root_uri}")
        finally:
            cleanup_temp_dir(temp_dir)

    def test_build_markdown_file(self, api_client):
        """TC-B02 Markdown檔案構建：驗證 .md 檔案新增後 heading 結構保留為子節點"""
        from build_test_helpers import assert_tree_has_child_nodes

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

    def test_build_raw_content(self, api_client):
        """TC-B14 原始內容字串構建：驗證純文本內容寫入檔案後新增可檢索"""
        random_id = str(uuid.uuid4())[:8]
        unique_keyword = f"raw_keyword_{random_id}"
        raw_content = (
            f"原始內容測試 {random_id}\n包含唯一關鍵詞：{unique_keyword}\n用於驗證字串輸入構建。"
        )

        test_file_path, temp_dir = create_test_file(content=raw_content, suffix=".txt")
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

            assert_source_format(api_client, root_uri, ["text", "markdown"])

            assert_resource_indexed(api_client, root_uri, unique_keyword)

            print(f"✓ TC-B14 原始內容字串構建通過, root_uri: {root_uri}")
        finally:
            cleanup_temp_dir(temp_dir)
