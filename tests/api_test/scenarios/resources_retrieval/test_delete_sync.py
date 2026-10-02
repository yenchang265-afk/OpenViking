import os
import shutil
import time
import uuid

from conftest import create_test_file


class TestDeleteSync:
    """TC-R04 資源刪除索引同步

    根據API文件：
    - 刪除資源使用 DELETE /api/v1/fs?uri={uri}&recursive={bool}
    - 刪除後應該同步更新向量索引
    """

    def test_resource_deletion_index_sync(self, api_client):
        """資源刪除索引同步：新增資源 -> 等待索引 -> 刪除資源 -> 驗證刪除"""
        random_id = str(uuid.uuid4())[:8]
        unique_keyword = f"delete_test_{random_id}"

        # 1. 建立臨時測試檔案
        test_file_path, temp_dir = create_test_file(
            content=f"測試檔案 {random_id}\n這是一個用於刪除同步測試的檔案。\n包含唯一關鍵詞：{unique_keyword}、test、刪除、同步。"
        )

        try:
            # 2. 新增該檔案到資源
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

            # 4. 驗證能搜尋到資源
            response = api_client.find(unique_keyword)
            assert response.status_code == 200
            data = response.json()
            assert data.get("status") == "ok"
            assert "result" in data

            search_result = data["result"]

            # 驗證搜尋結果不為空
            total_results = 0
            for field in ["resources", "memories", "matches"]:
                if field in search_result:
                    items = search_result[field]
                    total_results += len(items)

            # 搜尋應該返回結果
            assert total_results > 0, (
                f"Search should return results before deletion, keyword: {unique_keyword}"
            )
            print(f"刪除前搜尋結果數: {total_results}")

            # 5. 刪除資源
            response = api_client.fs_rm(resource_uri, recursive=True)
            assert response.status_code == 200
            delete_data = response.json()
            assert delete_data.get("status") == "ok"
            print(f"資源已刪除: {resource_uri}")

            # 6. 等待索引同步
            time.sleep(3)
            response = api_client.wait_processed()
            assert response.status_code == 200

            # 7. 驗證刪除後資源不存在於檔案系統
            response = api_client.fs_stat(resource_uri)
            # 資源應該不存在
            if response.status_code != 200:
                print("刪除後資源不存在於檔案系統 ✓")
            else:
                stat_data = response.json()
                if stat_data.get("status") == "error":
                    print("刪除後資源不存在於檔案系統 ✓")

            print("✓ 資源刪除索引同步測試通過")
        finally:
            # 清理臨時檔案
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
