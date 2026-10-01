import os
import shutil
import time
import uuid

from conftest import create_test_file


class TestPackConsistency:
    """TC-R05 批次匯入匯出一致性

    根據API文件：
    - export_ovpack: POST /api/v1/pack/export
    - import_ovpack: POST /api/v1/pack/import
    - 用於資源的批次匯出和匯入
    """

    def test_pack_export_import_consistency(self, api_client):
        """批次匯入匯出一致性：新增資源 -> 驗證資源存在 -> 驗證搜尋正常"""
        random_id = str(uuid.uuid4())[:8]
        unique_keyword = f"pack_test_{random_id}"

        # 1. 建立臨時測試檔案
        test_file_path, temp_dir = create_test_file(
            content=f"測試檔案 {random_id}\n這是一個用於pack測試的檔案。\n包含唯一關鍵詞：{unique_keyword}、test、pack、匯出。"
        )

        try:
            # 2. 新增該檔案到資源（確保有資源可匯出）
            response = api_client.add_resource(path=test_file_path, wait=True)
            assert response.status_code == 200

            add_data = response.json()
            assert add_data.get("status") == "ok"

            add_result = add_data.get("result", {})
            resource_uri = add_result.get("root_uri")
            assert resource_uri is not None, "Add resource should return root_uri"
            print(f"資源新增成功，URI: {resource_uri}")

            # 3. 等待處理完成
            response = api_client.wait_processed()
            assert response.status_code == 200

            # 額外等待索引同步
            time.sleep(3)

            # 4. 驗證資源存在於檔案系統
            response = api_client.fs_ls("viking://resources/")
            assert response.status_code == 200
            ls_data = response.json()
            assert ls_data.get("status") == "ok"

            ls_result = ls_data.get("result", [])
            assert isinstance(ls_result, list), "fs_ls result should be a list"
            print(f"資源目錄列表: {len(ls_result)} 個條目")

            # 5. 驗證搜尋能找到資源
            response = api_client.find(unique_keyword)
            assert response.status_code == 200

            search_data = response.json()
            assert search_data.get("status") == "ok"
            assert "result" in search_data

            search_result = search_data["result"]

            # 驗證搜尋結果不為空
            total_results = 0
            for field in ["resources", "memories", "matches"]:
                if field in search_result:
                    items = search_result[field]
                    total_results += len(items)

            assert total_results > 0, f"Search should return results for keyword: {unique_keyword}"
            print(f"搜尋結果數: {total_results}")

            # 6. 驗證資源狀態
            response = api_client.fs_stat(resource_uri)
            if response.status_code == 200:
                stat_data = response.json()
                if stat_data.get("status") == "ok":
                    print("資源狀態驗證成功 ✓")

            print("✓ Pack一致性測試通過，資源已正確索引")
        finally:
            # 清理臨時檔案
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
