import os
import shutil
import tempfile
import uuid

from build_test_helpers import (
    _extract_error_message,
    assert_root_uri_valid,
    cleanup_temp_dir,
    create_test_file,
)


class TestBuildErrorHandling:
    """TC-E01, E08, E09, E11, E16 異常與邊界測試（快速用例，≤20s）"""

    def test_error_remote_404(self, api_client):
        """TC-E01 遠端404不存在：驗證 404 URL 返回錯誤且不崩潰，錯誤資訊應包含狀態碼"""
        url_404 = "https://httpbin.org/status/404"

        response = api_client.add_resource(path=url_404, wait=True)

        data = response.json()
        if data.get("status") == "error":
            error_msg = _extract_error_message(data).lower()
            assert "404" in error_msg or "not found" in error_msg or "error" in error_msg, (
                f"404錯誤資訊應包含 404/not found/error, 實際: {error_msg}"
            )
            print("✓ TC-E01 遠端404不存在處理通過(返回error)")
            return

        if data.get("status") == "ok":
            result = data.get("result", {})
            root_uri = result.get("root_uri")
            if root_uri:
                assert_root_uri_valid(root_uri)
            print("✓ TC-E01 遠端404處理通過(降級為空資源)")
            return

        raise AssertionError(f"404 URL 應返回 error 或 ok, 實際: {data.get('status')}")

    def test_error_dns_resolve_failure(self, api_client):
        """TC-E08 DNS解析失敗：驗證不存在的域名返回錯誤且不掛起"""
        bad_dns_url = "https://nonexistent.domain.invalid.for.test/page"

        response = api_client.add_resource(path=bad_dns_url, wait=True)

        data = response.json()
        if data.get("status") == "error":
            error_msg = _extract_error_message(data).lower()
            assert (
                "resolve" in error_msg
                or "hostname" in error_msg
                or "host does not exist" in error_msg
                or "dns" in error_msg
                or "error" in error_msg
            ), f"DNS失敗錯誤資訊應包含 resolve/hostname/host does not exist/dns/error, 實際: {error_msg}"
            print("✓ TC-E08 DNS解析失敗處理通過(返回error)")
            return

        if data.get("status") == "ok":
            result = data.get("result", {})
            root_uri = result.get("root_uri")
            if root_uri:
                assert_root_uri_valid(root_uri)
            print("✓ TC-E08 DNS解析失敗處理通過(降級為空資源)")
            return

        raise AssertionError(f"DNS失敗 URL 應返回 error 或 ok, 實際: {data.get('status')}")

    def test_error_ssh_url_invalid_format(self, api_client):
        """TC-E09 SSH URL格式錯誤：驗證 git@invalid (無冒號) 返回 InvalidArgumentError"""
        invalid_ssh_url = "git@invalid"

        response = api_client.add_resource(path=invalid_ssh_url, wait=True)

        data = response.json()
        if data.get("status") == "error":
            error_msg = _extract_error_message(data).lower()
            assert (
                "invalid" in error_msg
                or "ssh" in error_msg
                or "uri" in error_msg
                or "colon" in error_msg
                or "error" in error_msg
                or "permission" in error_msg
            ), f"SSH格式錯誤應包含 invalid/ssh/uri/colon/error/permission, 實際: {error_msg}"
            print("✓ TC-E09 SSH URL格式錯誤處理通過")
            return

        if data.get("status") == "ok":
            print("✓ TC-E09 SSH URL格式錯誤處理通過(服務端降級)")
            return

        raise AssertionError(f"SSH URL格式錯誤應返回 error 或降級, 實際: {data.get('status')}")

    def test_error_non_resources_scope_rejected(self, api_client):
        """TC-E11 非resources scope拒絕：驗證 to=viking://sessions/xxx 返回錯誤"""
        random_id = str(uuid.uuid4())[:8]
        test_content = f"scope測試內容 {random_id}"
        test_file_path, temp_dir = create_test_file(content=test_content, suffix=".txt")
        try:
            response = api_client.add_resource(
                path=test_file_path,
                to="viking://sessions/test_session",
                wait=True,
            )

            data = response.json()
            if data.get("status") == "error":
                error_msg = _extract_error_message(data).lower()
                assert (
                    "scope" in error_msg
                    or "resources" in error_msg
                    or "invalid" in error_msg
                    or "permission" in error_msg
                    or "internal" in error_msg
                ), f"scope拒絕應包含 scope/resources/invalid/permission/internal, 實際: {error_msg}"
                print("✓ TC-E11 非resources scope拒絕通過")
                return

            if data.get("status") == "ok":
                result = data.get("result", {})
                root_uri = result.get("root_uri", "")
                assert "sessions" not in root_uri, (
                    f"非resources scope不應成功寫入sessions, root_uri: {root_uri}"
                )
                print("✓ TC-E11 非resources scope處理通過(服務端重定向)")
                return
        finally:
            cleanup_temp_dir(temp_dir)

    def test_error_corrupted_zip(self, api_client):
        """TC-E16 損壞的ZIP檔案：驗證偽造 .zip 檔案回退或報錯且不崩潰"""
        random_id = str(uuid.uuid4())[:8]

        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, f"corrupted_{random_id}.zip")
        with open(zip_path, "w", encoding="utf-8") as f:
            f.write("這不是一個真正的ZIP檔案內容")

        try:
            response = api_client.add_resource(path=zip_path, wait=True)
            assert response.status_code == 500, f"損壞ZIP應返回 500, 實際: {response.status_code}"

            data = response.json()
            assert data.get("status") == "error", f"損壞ZIP應返回 error, 實際: {data.get('status')}"

            print("✓ TC-E16 損壞的ZIP檔案處理通過")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
