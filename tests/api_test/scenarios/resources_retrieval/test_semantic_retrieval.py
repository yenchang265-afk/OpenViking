import os
import uuid

from conftest import create_test_file


class TestSemanticRetrieval:
    """TC-R01 語義檢索全鏈路驗證"""

    def test_semantic_retrieval_end_to_end(self, api_client):
        """語義檢索全鏈路驗證：新增資源 -> 等待處理 -> 搜尋驗證"""
        random_id = str(uuid.uuid4())[:8]
        unique_keyword = f"unique_keyword_{random_id}"

        # 1. 建立臨時測試檔案，包含唯一關鍵詞
        test_file_path, temp_dir = create_test_file(
            content=f"測試檔案 {random_id}\n這是一個用於語義檢索測試的檔案。\n包含唯一關鍵詞：{unique_keyword}、test、測試、檢索。"
        )

        try:
            # 2. 新增該檔案到資源
            response = api_client.add_resource(path=test_file_path, wait=True)
            assert response.status_code == 200

            add_data = response.json()
            assert add_data.get("status") == "ok"

            # 驗證新增資源的返回結果
            add_result = add_data.get("result", {})
            assert "root_uri" in add_result or "resource_id" in add_result, (
                "Add resource should return root_uri or resource_id"
            )

            # 儲存新增的資源URI，用於後續驗證
            added_resource_uri = add_result.get("root_uri") or add_result.get("resource_id")

            # 3. 等待處理完成
            response = api_client.wait_processed()
            assert response.status_code == 200

            # 4. 執行語義搜尋，使用唯一關鍵詞
            search_query = unique_keyword
            response = api_client.find(search_query)
            assert response.status_code == 200

            search_data = response.json()
            assert search_data.get("status") == "ok"
            assert "result" in search_data

            search_result = search_data["result"]

            # 5. 驗證搜尋結果結構正確
            found_added_resource = False
            total_results = 0

            for field in ["resources", "memories", "matches"]:
                if field in search_result:
                    items = search_result[field]
                    assert isinstance(items, list), f"{field} should be a list"
                    total_results += len(items)

                    # 如果有結果，驗證每個結果的結構
                    for item in items:
                        assert "score" in item or "uri" in item, (
                            "Each search result should have score or uri"
                        )

                        # 驗證是否找到新增的資源
                        if "uri" in item and added_resource_uri:
                            if added_resource_uri in item["uri"]:
                                found_added_resource = True

            # 記錄搜尋結果數量
            print(f"Total search results: {total_results}")

            # 6. 驗證業務邏輯：搜尋結果應該包含剛新增的資源
            # 這是一個重要的業務邏輯驗證，應該保持失敗狀態以發現問題
            if added_resource_uri:
                assert found_added_resource, (
                    f"Search result should contain the added resource: {added_resource_uri}. "
                    f"This indicates that the resource was not correctly indexed or the search algorithm has issues."
                )

            # 7. 驗證搜尋結果的相關性（如果返回了score）
            for field in ["resources", "memories", "matches"]:
                if field in search_result:
                    items = search_result[field]
                    for item in items:
                        if "score" in item:
                            # 驗證score是合理的範圍（0-1）
                            assert 0 <= item["score"] <= 1, (
                                f"Score should be between 0 and 1, got {item['score']}"
                            )

            # 8. 業務邏輯驗證：驗證資源是否被正確索引
            # 使用更通用的關鍵詞進行搜尋
            response = api_client.find("test")
            assert response.status_code == 200
            general_search_data = response.json()
            assert general_search_data.get("status") == "ok"

            # 記錄通用搜索的結果數量
            general_search_result = general_search_data.get("result", {})
            general_total = 0
            for field in ["resources", "memories", "matches"]:
                if field in general_search_result:
                    general_total += len(general_search_result[field])

            print(f"General search results: {general_total}")

            # 9. 業務邏輯驗證：驗證資源列表
            response = api_client.fs_ls("viking://")
            assert response.status_code == 200
            ls_data = response.json()
            assert ls_data.get("status") == "ok"

            ls_result = ls_data.get("result", [])
            print(f"Total resources in root: {len(ls_result)}")

            # 10. 業務邏輯驗證：驗證系統狀態
            response = api_client.is_healthy()
            assert response.status_code == 200
            health_data = response.json()
            assert health_data.get("status") == "ok"
            print("✓ System is healthy")

            print("✓ Semantic retrieval test passed")
        finally:
            # 清理臨時檔案
            import shutil

            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
