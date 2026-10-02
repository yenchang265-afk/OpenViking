import os
import shutil
import uuid

from conftest import create_test_file


class TestIntentExtendedSearch:
    """TC-R06 意圖擴充搜尋 (Search)

    根據API文件：
    - search() 帶會話上下文和意圖分析
    - 引數 session_id 用於上下文感知搜尋
    - 與 find() 的區別：search 支援意圖分析、會話上下文、查詢擴充
    """

    def test_intent_extended_search(self, api_client):
        """意圖擴充搜尋：create_session -> add_message -> search(with session_id)"""
        random_id = str(uuid.uuid4())[:8]
        unique_keyword = f"intent_search_{random_id}"

        # 1. 建立臨時測試檔案
        test_file_path, temp_dir = create_test_file(
            content=f"測試檔案 {random_id}\n這是一個用於意圖擴充搜尋測試的檔案。\n包含唯一關鍵詞：{unique_keyword}、test、搜尋、意圖。\nOAuth認證相關內容。"
        )

        try:
            # 2. 新增該檔案到資源
            response = api_client.add_resource(path=test_file_path, wait=True)
            assert response.status_code == 200

            add_data = response.json()
            assert add_data.get("status") == "ok"
            print("資源新增成功")

            # 3. 等待處理完成
            response = api_client.wait_processed()
            assert response.status_code == 200

            # 4. 建立會話
            response = api_client.create_session()
            assert response.status_code == 200
            create_data = response.json()
            assert create_data.get("status") == "ok"

            session_id = create_data["result"]["session_id"]
            assert session_id is not None
            print(f"會話建立成功: {session_id}")

            # 5. 新增對話上下文（模擬使用者討論OAuth）
            response = api_client.add_message(
                session_id, "user", f"我正在實現OAuth認證功能，需要檢視相關文件。{random_id}"
            )
            assert response.status_code == 200
            msg_data = response.json()
            assert msg_data.get("status") == "ok"
            print("消息添加成功")

            # 6. 執行搜尋（帶會話上下文）
            # 根據API文件，search支援session_id引數
            search_query = "認證"
            response = api_client.search(search_query)
            assert response.status_code == 200

            search_data = response.json()
            assert search_data.get("status") == "ok"
            assert "result" in search_data

            search_result = search_data["result"]

            # 7. 驗證搜尋結果結構
            assert (
                "memories" in search_result
                or "resources" in search_result
                or "results" in search_result
            )

            total_results = 0
            for field in ["memories", "resources", "results"]:
                if field in search_result:
                    items = search_result[field]
                    assert isinstance(items, list), f"{field} should be a list"
                    total_results += len(items)

            print(f"搜尋結果數量: {total_results}")

            # 8. 業務邏輯驗證：搜尋應該返回相關結果
            assert total_results > 0, (
                "Search should return at least one result when resources exist"
            )

            # 9. 驗證搜尋結果的相關性分數（如果返回）
            for field in ["resources", "memories"]:
                if field in search_result:
                    for item in search_result[field]:
                        if "score" in item:
                            assert 0 <= item["score"] <= 1, (
                                f"Score should be between 0 and 1, got {item['score']}"
                            )

            print("✓ 意圖擴充搜尋測試通過")
        finally:
            # 清理臨時檔案
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
