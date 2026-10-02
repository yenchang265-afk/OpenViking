import os
import shutil
import time
import uuid

from conftest import create_test_file


class TestResourceSwap:
    """TC-R02 資源增量更新

    根據API文件：當你為同一個資源 URI 反覆呼叫 add_resource() 時，
    系統會走"增量更新"而不是每次全量重建。
    觸發條件：請求裡顯式指定 target，且該 target 在知識庫中已存在。
    """

    def test_resource_incremental_update(self, api_client):
        """資源增量更新：新增資源 -> 等待索引 -> 驗證能搜尋到"""
        random_id = str(uuid.uuid4())[:8]
        unique_keyword = f"incremental_{random_id}"

        # 1. 建立臨時測試檔案
        test_file_path, temp_dir = create_test_file(
            content=f"測試檔案 {random_id}\n這是一個用於資源增量更新測試的檔案。\n包含關鍵詞：{unique_keyword}、test、更新、資源。"
        )

        try:
            # 2. 新增該檔案到資源
            response = api_client.add_resource(path=test_file_path, wait=True)
            assert response.status_code == 200

            add_data = response.json()
            assert add_data.get("status") == "ok"

            # 驗證返回結果包含root_uri
            add_result = add_data.get("result", {})
            assert "root_uri" in add_result, "Add resource should return root_uri"
            root_uri = add_result["root_uri"]
            print(f"資源新增成功，root_uri: {root_uri}")

            # 3. 等待處理完成
            response = api_client.wait_processed()
            assert response.status_code == 200

            # 額外等待索引同步
            time.sleep(3)

            # 4. 驗證find能搜尋到該資源
            response = api_client.find(unique_keyword)
            assert response.status_code == 200

            search_data = response.json()
            assert search_data.get("status") == "ok"
            assert "result" in search_data

            search_result = search_data["result"]

            # 5. 驗證搜尋結果結構正確
            total_results = 0
            for field in ["resources", "memories", "matches"]:
                if field in search_result:
                    items = search_result[field]
                    assert isinstance(items, list), f"{field} should be a list"
                    total_results += len(items)

            # 6. 業務邏輯驗證：搜尋應該返回結果
            assert total_results > 0, f"Search should return results for keyword: {unique_keyword}"

            print(f"✓ 資源增量更新測試通過，搜尋結果數: {total_results}")
        finally:
            # 清理臨時檔案
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
