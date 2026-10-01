import concurrent.futures
import os
import shutil
import tempfile
import uuid


def _create_test_file(content):
    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, f"test_{uuid.uuid4().hex[:8]}.txt")
    with open(file_path, "w") as f:
        f.write(content)
    return file_path, temp_dir


class TestConcurrentWrite:
    """TC-ER02 併發寫入衝突驗證"""

    def test_concurrent_write_conflict(self, api_client):
        """併發寫入衝突驗證：併發呼叫 add_resource (Same URI)"""
        random_id = str(uuid.uuid4())[:8]

        # 1. 建立臨時測試檔案
        test_file_path, temp_dir = _create_test_file(
            content=f"測試檔案 {random_id}\n這是一個用於併發寫入測試的檔案。\n包含關鍵詞：test、併發、寫入。"
        )

        try:
            # 2. 定義併發任務函式
            def add_resource_task():
                try:
                    response = api_client.add_resource(path=test_file_path, wait=True)
                    return response.status_code, response.json()
                except Exception as e:
                    return 500, {"error": str(e)}

            # 3. 併發執行多個任務
            num_tasks = 3
            results = []

            with concurrent.futures.ThreadPoolExecutor(max_workers=num_tasks) as executor:
                futures = [executor.submit(add_resource_task) for _ in range(num_tasks)]
                for future in concurrent.futures.as_completed(futures):
                    results.append(future.result())

            # 4. 驗證所有請求都返回合理的響應
            assert len(results) == num_tasks

            for status_code, response_data in results:
                # 要麼成功（200），要麼返回合理的錯誤（429或其他）
                assert status_code == 200, f"Unexpected status code: {status_code}"

                if status_code == 200:
                    assert response_data.get("status") in ["ok", "error"], (
                        "Response should have valid status"
                    )
        finally:
            # 清理臨時檔案
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
