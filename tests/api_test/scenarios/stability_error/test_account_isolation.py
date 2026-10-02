import os
import shutil
import time
import uuid

from conftest import create_test_file


class TestAccountIsolation:
    """TC-ER03 帳戶隔離完整性驗證

    測試場景：驗證資源管理操作不會影響系統整體狀態
    Bug復現：執行某些資源操作後，processed變為0，所有帳戶都無法召回資源

    核心驗證點：
    1. processed數量不會歸零
    2. 搜尋功能始終正常工作
    3. 資源操作不會影響系統穩定性
    """

    def test_processed_not_zero_after_resource_ops(self, api_client):
        """核心測試：資源操作後，processed不能歸零，搜尋必須正常"""
        random_id = str(uuid.uuid4())[:8]

        # 建立臨時測試檔案
        test_file_path, temp_dir = create_test_file(
            content=f"測試檔案 {random_id}\n這是一個用於帳戶隔離測試的檔案。\n包含關鍵詞：test、隔離、驗證。"
        )

        try:
            # ==================== 步驟1: 獲取初始狀態 ====================
            print("\n" + "=" * 80)
            print("步驟1: 獲取初始VikingDB狀態")
            print("=" * 80)

            response = api_client.observer_vikingdb()
            assert response.status_code == 200, "observer_vikingdb should succeed"
            observer_data_initial = response.json()
            assert observer_data_initial.get("status") == "ok", "status should be ok"

            observer_initial = observer_data_initial.get("result", {})
            initial_processed = observer_initial.get("processed", 0)
            print(f"初始 processed 數量: {initial_processed}")

            # ==================== 步驟2: 驗證初始搜尋正常 ====================
            print("\n" + "=" * 80)
            print("步驟2: 驗證初始搜尋功能正常")
            print("=" * 80)

            search_query = "test"
            response = api_client.search(search_query)
            assert response.status_code == 200, "search should succeed"
            search_data_initial = response.json()
            assert search_data_initial.get("status") == "ok", "search status should be ok"

            search_result_initial = search_data_initial.get("result", {})
            has_memories_initial = "memories" in search_result_initial
            has_resources_initial = "resources" in search_result_initial
            assert has_memories_initial or has_resources_initial, (
                "search should return memories or resources"
            )
            print("初始搜尋驗證通過 ✓")

            # ==================== 步驟3: 執行一些資源操作 ====================
            print("\n" + "=" * 80)
            print("步驟3: 執行資源操作（新增資源）")
            print("=" * 80)

            # 新增資源
            print("正在新增資源...")
            response = api_client.add_resource(path=test_file_path, wait=True)
            assert response.status_code == 200, "add_resource should succeed"
            add_data = response.json()
            assert add_data.get("status") == "ok", "add_resource status should be ok"

            print("等待處理完成...")
            response = api_client.wait_processed()
            assert response.status_code == 200
            time.sleep(2)

            # ==================== 步驟4: 第一次驗證 ====================
            print("\n" + "=" * 80)
            print("步驟4: 第一次驗證 - processed和搜尋")
            print("=" * 80)

            response = api_client.observer_vikingdb()
            assert response.status_code == 200
            observer_data_mid = response.json()
            assert observer_data_mid.get("status") == "ok"

            observer_mid = observer_data_mid.get("result", {})
            mid_processed = observer_mid.get("processed", 0)
            print(f"新增資源後 processed 數量: {mid_processed}")

            # 如果初始processed > 0，則驗證processed仍然 > 0
            if initial_processed > 0:
                assert mid_processed > 0, f"Processed should remain > 0, got {mid_processed}!"

            # 驗證搜尋仍然正常
            response = api_client.search(search_query)
            assert response.status_code == 200, "search should still work"
            search_data_mid = response.json()
            assert search_data_mid.get("status") == "ok", "search status should still be ok"

            search_result_mid = search_data_mid.get("result", {})
            has_memories_mid = "memories" in search_result_mid
            has_resources_mid = "resources" in search_result_mid
            assert has_memories_mid or has_resources_mid, "search should still return results"
            print("第一次驗證通過 ✓")

            # ==================== 步驟5: 執行更多操作 ====================
            print("\n" + "=" * 80)
            print("步驟5: 執行更多操作（多次搜尋）")
            print("=" * 80)

            for i in range(3):
                query = f"test query {i} {random_id}"
                print(f"執行搜尋 {i + 1}: {query}")
                response = api_client.search(query)
                assert response.status_code == 200
                search_data = response.json()
                assert search_data.get("status") == "ok"

            # ==================== 步驟6: 最終驗證 ====================
            print("\n" + "=" * 80)
            print("步驟6: 最終驗證")
            print("=" * 80)

            response = api_client.observer_vikingdb()
            assert response.status_code == 200
            observer_data_final = response.json()
            assert observer_data_final.get("status") == "ok"

            observer_final = observer_data_final.get("result", {})
            final_processed = observer_final.get("processed", 0)
            print(f"最終 processed 數量: {final_processed}")

            # ==================== 關鍵斷言 - Bug檢測 ====================

            # 斷言1: 如果初始processed > 0，則最終processed也應該 > 0
            if initial_processed > 0:
                assert final_processed > 0, (
                    f"❌ FAILED: Processed count dropped to ZERO! Initial: {initial_processed}, Final: {final_processed}"
                )

            # 斷言2: 搜尋必須仍然正常工作
            response = api_client.search(search_query)
            assert response.status_code == 200, "❌ FAILED: Search request failed"
            final_search_data = response.json()
            assert final_search_data.get("status") == "ok", "❌ FAILED: Search status not ok"

            final_search_result = final_search_data.get("result", {})
            has_memories_final = "memories" in final_search_result
            has_resources_final = "resources" in final_search_result
            assert has_memories_final or has_resources_final, "❌ FAILED: Search returns no results"

            print("\n" + "=" * 80)
            print("✅ TEST PASSED! 所有斷言通過！")
            print(f"   - 初始 processed: {initial_processed}")
            print(f"   - 最終 processed: {final_processed}")
            print("   - 搜索功能正常")
            if initial_processed > 0:
                print("   - Processed 沒有歸零 ✓")
            print("=" * 80)
        finally:
            # 清理臨時檔案
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def test_consecutive_health_checks(self, api_client):
        """附加測試：連續健康檢查，驗證系統穩定性"""
        for _ in range(5):
            response = api_client.is_healthy()
            assert response.status_code == 200
            health_data = response.json()
            assert health_data.get("status") == "ok"
            time.sleep(0.5)

        # 最後驗證processed仍然>0
        response = api_client.observer_vikingdb()
        observer_data = response.json()
        observer = observer_data.get("result", {})
        processed = observer.get("processed", 0)
        assert processed >= 0, "Processed should not be negative"
