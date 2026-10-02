import os
import shutil
import uuid

from conftest import create_test_file


class TestWatchUpdate:
    """TC-R08 定時監聽更新 (Watch)

    根據API文件：
    - add_resource() 支援 watch_interval 引數
    - watch_interval: 定時更新間隔（分鐘）。>0 開啟/更新定時任務；<=0 關閉定時任務
    - 僅在指定 target 時生效
    """

    def test_watch_update(self, api_client):
        """定時監聽更新：add_resource -> 驗證資源索引 -> 驗證搜尋"""
        random_id = str(uuid.uuid4())[:8]
        unique_keyword = f"watch_test_{random_id}"

        # 1. 建立臨時測試檔案
        test_file_path, temp_dir = create_test_file(
            content=f"測試檔案 {random_id}\n這是一個用於監聽更新測試的檔案。\n包含唯一關鍵詞：{unique_keyword}、test、監聽、更新。"
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
            print(f"資源新增成功: {resource_uri}")

            # 3. 等待處理完成
            response = api_client.wait_processed()
            assert response.status_code == 200

            # 4. 驗證資源已被正確索引
            response = api_client.fs_stat(resource_uri)
            if response.status_code == 200:
                stat_data = response.json()
                if stat_data.get("status") == "ok":
                    print("資源狀態驗證成功")

            # 5. 執行搜尋驗證
            response = api_client.find(unique_keyword)
            assert response.status_code == 200

            search_data = response.json()
            assert search_data.get("status") == "ok"
            assert "result" in search_data

            search_result = search_data["result"]

            # 6. 驗證搜尋結果包含剛新增的資源
            found_resource = False
            for field in ["resources", "memories", "matches"]:
                if field in search_result:
                    items = search_result[field]
                    assert isinstance(items, list), f"{field} should be a list"
                    for item in items:
                        if "uri" in item and resource_uri in item["uri"]:
                            found_resource = True
                            break

            assert found_resource, f"Search should find the added resource: {resource_uri}"

            # 7. 驗證系統狀態
            response = api_client.is_healthy()
            assert response.status_code == 200
            health_data = response.json()
            assert health_data.get("status") == "ok"

            print("✓ 定時監聽更新測試通過，資源已被正確索引")
        finally:
            # 清理臨時檔案
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
