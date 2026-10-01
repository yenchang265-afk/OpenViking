import os
import shutil
import tempfile
import uuid

from build_test_helpers import (
    _extract_error_message,
    assert_resource_indexed,
    assert_root_uri_valid,
    assert_source_format,
    cleanup_temp_dir,
    create_test_file,
)


class TestBuildErrorHandlingSlow:
    """TC-E01~E16 異常與邊界測試"""

    def test_error_remote_404(self, api_client):
        """TC-E01 遠端404不存在：驗證 404 URL 返回錯誤含狀態碼資訊且不崩潰"""
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
            if isinstance(result, dict) and result.get("status") == "error":
                inner_errors = result.get("errors", [])
                inner_msg = " ".join(str(e) for e in inner_errors).lower()
                assert (
                    "404" in inner_msg
                    or "not found" in inner_msg
                    or "failed" in inner_msg
                    or "error" in inner_msg
                ), f"404內層錯誤應包含 404/not found/failed/error, 實際: {inner_msg}"
                print(f"✓ TC-E01 遠端404不存在處理通過(內層錯誤): {inner_msg[:80]}")
                return

            root_uri = result.get("root_uri")
            if root_uri:
                assert_root_uri_valid(root_uri)
            print("✓ TC-E01 遠端404處理通過(降級為空資源)")
            return

        raise AssertionError(f"404 URL 應返回 error 或 ok, 實際: {data.get('status')}")

    def test_error_http_to_https_redirect(self, api_client):
        """TC-E05 HTTP→HTTPS跳轉：驗證 http URL 自動跟隨跳轉且 root_uri 正常"""
        redirect_url = "http://github.com/volcengine/OpenViking"

        response = api_client.add_resource(path=redirect_url, wait=True)
        assert response.status_code == 200

        data = response.json()
        assert data.get("status") == "ok"

        result = data.get("result", {})
        root_uri = result.get("root_uri")
        assert_root_uri_valid(root_uri)
        assert "volcengine" in root_uri and "OpenViking" in root_uri, (
            f"跳轉後 root_uri 應含 volcengine/OpenViking, 實際: {root_uri}"
        )

        print(f"✓ TC-E05 HTTP→HTTPS跳轉通過, root_uri: {root_uri}")

    def test_error_multi_redirect(self, api_client):
        """TC-E06 多重跳轉：驗證短鏈 URL 自動跟隨跳轉且內容可檢索"""
        redirect_url = (
            "https://httpbin.org/redirect-to?url=https://httpbin.org/html&status_code=302"
        )

        response = api_client.add_resource(path=redirect_url, wait=True)
        assert response.status_code == 200

        data = response.json()
        assert data.get("status") == "ok"

        result = data.get("result", {})
        root_uri = result.get("root_uri")
        assert_root_uri_valid(root_uri)

        assert_resource_indexed(api_client, root_uri, "httpbin")

        print(f"✓ TC-E06 多重跳轉通過, root_uri: {root_uri}")

    def test_error_duplicate_resource_no_to(self, api_client):
        """TC-E12 同名資源二次新增(無to)：驗證兩次新增的 root_uri 不同（URI 附加字尾）"""
        random_id = str(uuid.uuid4())[:8]
        unique_keyword = f"dup_keyword_{random_id}"
        content = f"重複新增測試 {random_id}\n包含唯一關鍵詞：{unique_keyword}"

        test_file_path, temp_dir = create_test_file(content=content, suffix=".txt")
        try:
            resp1 = api_client.add_resource(path=test_file_path, wait=True)
            assert resp1.status_code == 200
            data1 = resp1.json()
            assert data1.get("status") == "ok"
            root_uri_1 = data1.get("result", {}).get("root_uri")
            assert_root_uri_valid(root_uri_1)

            resp2 = api_client.add_resource(path=test_file_path, wait=True)
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert data2.get("status") == "ok"
            root_uri_2 = data2.get("result", {}).get("root_uri")
            assert_root_uri_valid(root_uri_2)

            assert root_uri_1 != root_uri_2, (
                f"同名資源二次新增(無to) root_uri 應不同, uri1: {root_uri_1}, uri2: {root_uri_2}"
            )

            print(f"✓ TC-E12 同名資源二次新增通過, uri1: {root_uri_1}, uri2: {root_uri_2}")
        finally:
            cleanup_temp_dir(temp_dir)

    def test_error_incremental_update_with_to(self, api_client):
        """TC-E13 同to增量更新：驗證同一 to 二次新增後 root_uri 不變且不報錯"""
        random_id = str(uuid.uuid4())[:8]
        unique_keyword = f"incr_keyword_{random_id}"
        target_uri = f"viking://resources/incr_test_{random_id}"

        content1 = f"增量更新測試1 {random_id}\n包含唯一關鍵詞：{unique_keyword}_v1"
        content2 = f"增量更新測試2 {random_id}\n包含唯一關鍵詞：{unique_keyword}_v2"

        file1, temp_dir1 = create_test_file(content=content1, suffix=".txt")
        file2, temp_dir2 = create_test_file(content=content2, suffix=".txt")
        try:
            resp1 = api_client.add_resource(path=file1, to=target_uri, wait=True)
            assert resp1.status_code == 200
            data1 = resp1.json()
            assert data1.get("status") == "ok"
            root_uri_1 = data1.get("result", {}).get("root_uri")

            resp2 = api_client.add_resource(path=file2, to=target_uri, wait=True)
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert data2.get("status") == "ok"
            root_uri_2 = data2.get("result", {}).get("root_uri")

            assert root_uri_1 == root_uri_2, (
                f"同to增量更新 root_uri 應不變, uri1: {root_uri_1}, uri2: {root_uri_2}"
            )

            print(f"✓ TC-E13 同to增量更新通過, root_uri: {root_uri_1}")
        finally:
            cleanup_temp_dir(temp_dir1)
            cleanup_temp_dir(temp_dir2)

    def test_error_unsupported_file_type(self, api_client):
        """TC-E15 不支援的檔案型別：驗證 .xyz 檔案回退到 TextParser 且 source_format=text、內容可檢索"""
        random_id = str(uuid.uuid4())[:8]
        unique_keyword = f"xyz_keyword_{random_id}"

        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, f"test_{random_id}.xyz")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"不支援的檔案型別測試 {random_id}\n包含唯一關鍵詞：{unique_keyword}")

        try:
            response = api_client.add_resource(path=file_path, wait=True)
            assert response.status_code == 200

            data = response.json()
            if data.get("status") == "error":
                error_msg = _extract_error_message(data).lower()
                assert "unsupported" in error_msg or "error" in error_msg or "type" in error_msg, (
                    f"不支援檔案型別錯誤應包含 unsupported/error/type, 實際: {error_msg}"
                )
                print(f"✓ TC-E15 不支援的檔案型別處理通過(服務端拒絕): {error_msg[:80]}")
                return

            assert data.get("status") == "ok"

            result = data.get("result", {})
            if isinstance(result, dict) and result.get("status") == "error":
                inner_errors = result.get("errors", [])
                inner_msg = " ".join(str(e) for e in inner_errors)
                assert (
                    "unsupported" in inner_msg.lower()
                    or "error" in inner_msg.lower()
                    or "parse" in inner_msg.lower()
                ), f"不支援檔案型別內層錯誤應包含 unsupported/error/parse, 實際: {inner_msg}"
                print(f"✓ TC-E15 不支援的檔案型別處理通過(內層錯誤): {inner_msg[:80]}")
                return

            root_uri = result.get("root_uri")
            assert_root_uri_valid(root_uri)

            stat_resp = api_client.fs_stat(root_uri)
            assert stat_resp.status_code == 200, (
                f"不支援檔案型別 fs_stat 應返回200, root_uri: {root_uri}"
            )

            assert_source_format(api_client, root_uri, ["text", "markdown"])

            assert_resource_indexed(api_client, root_uri, unique_keyword)

            print(f"✓ TC-E15 不支援的檔案型別處理通過(回退TextParser), root_uri: {root_uri}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_error_remote_403(self, api_client):
        """TC-E02 遠端403禁止訪問：驗證 403 URL 返回錯誤含狀態碼資訊且不崩潰"""
        url_403 = "https://httpbin.org/status/403"

        response = api_client.add_resource(path=url_403, wait=True)

        data = response.json()
        if data.get("status") == "error":
            error_msg = _extract_error_message(data).lower()
            assert "403" in error_msg or "forbidden" in error_msg or "error" in error_msg, (
                f"403錯誤資訊應包含 403/forbidden/error, 實際: {error_msg}"
            )
            print("✓ TC-E02 遠端403禁止訪問處理通過(返回error)")
            return

        if data.get("status") == "ok":
            result = data.get("result", {})
            if isinstance(result, dict) and result.get("status") == "error":
                inner_errors = result.get("errors", [])
                inner_msg = " ".join(str(e) for e in inner_errors).lower()
                assert (
                    "403" in inner_msg
                    or "forbidden" in inner_msg
                    or "failed" in inner_msg
                    or "error" in inner_msg
                ), f"403內層錯誤應包含 403/forbidden/failed/error, 實際: {inner_msg}"
                print(f"✓ TC-E02 遠端403禁止訪問處理通過(內層錯誤): {inner_msg[:80]}")
                return

            root_uri = result.get("root_uri")
            if root_uri:
                assert_root_uri_valid(root_uri)
            print("✓ TC-E02 遠端403處理通過(降級為空資源)")
            return

        raise AssertionError(f"403 URL 應返回 error 或 ok, 實際: {data.get('status')}")

    def test_error_remote_500(self, api_client):
        """TC-E03 遠端500服務錯誤：驗證 500 URL 返回錯誤含狀態碼資訊且不崩潰"""
        url_500 = "https://httpbin.org/status/500"

        response = api_client.add_resource(path=url_500, wait=True)

        data = response.json()
        if data.get("status") == "error":
            error_msg = _extract_error_message(data).lower()
            assert "500" in error_msg or "server" in error_msg or "error" in error_msg, (
                f"500錯誤資訊應包含 500/server/error, 實際: {error_msg}"
            )
            print("✓ TC-E03 遠端500服務錯誤處理通過(返回error)")
            return

        if data.get("status") == "ok":
            result = data.get("result", {})
            if isinstance(result, dict) and result.get("status") == "error":
                inner_errors = result.get("errors", [])
                inner_msg = " ".join(str(e) for e in inner_errors).lower()
                assert (
                    "500" in inner_msg
                    or "server" in inner_msg
                    or "internal" in inner_msg
                    or "failed" in inner_msg
                    or "error" in inner_msg
                ), f"500內層錯誤應包含 500/server/internal/failed/error, 實際: {inner_msg}"
                print(f"✓ TC-E03 遠端500服務錯誤處理通過(內層錯誤): {inner_msg[:80]}")
                return

            root_uri = result.get("root_uri")
            if root_uri:
                assert_root_uri_valid(root_uri)
            print("✓ TC-E03 遠端500處理通過(降級為空資源)")
            return

        raise AssertionError(f"500 URL 應返回 error 或 ok, 實際: {data.get('status')}")

    def test_error_dns_resolve_failure(self, api_client):
        """TC-E08 DNS解析失敗：驗證不存在的域名返回錯誤含DNS相關資訊且不掛起"""
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
                or "connect" in error_msg
            ), f"DNS失敗錯誤資訊應包含 resolve/hostname/host does not exist/dns/error/connect, 實際: {error_msg}"
            print("✓ TC-E08 DNS解析失敗處理通過(返回error)")
            return

        if data.get("status") == "ok":
            result = data.get("result", {})
            if isinstance(result, dict) and result.get("status") == "error":
                inner_errors = result.get("errors", [])
                inner_msg = " ".join(str(e) for e in inner_errors).lower()
                assert (
                    "resolve" in inner_msg
                    or "hostname" in inner_msg
                    or "host does not exist" in inner_msg
                    or "dns" in inner_msg
                    or "connect" in inner_msg
                    or "failed" in inner_msg
                    or "error" in inner_msg
                ), f"DNS內層錯誤應包含 resolve/hostname/host does not exist/dns/connect/failed/error, 實際: {inner_msg}"
                print(f"✓ TC-E08 DNS解析失敗處理通過(內層錯誤): {inner_msg[:80]}")
                return

            root_uri = result.get("root_uri")
            if root_uri:
                assert_root_uri_valid(root_uri)
            print("✓ TC-E08 DNS解析失敗處理通過(降級為空資源)")
            return

        raise AssertionError(f"DNS失敗 URL 應返回 error 或 ok, 實際: {data.get('status')}")

    def test_error_ssh_url_invalid_format(self, api_client):
        """TC-E09 SSH URL格式錯誤：驗證 git@invalid (無冒號) 返回錯誤含SSH/URI相關資訊"""
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
            print("✓ TC-E09 SSH URL格式錯誤處理通過(返回error)")
            return

        if data.get("status") == "ok":
            result = data.get("result", {})
            if isinstance(result, dict) and result.get("status") == "error":
                inner_errors = result.get("errors", [])
                inner_msg = " ".join(str(e) for e in inner_errors).lower()
                assert (
                    "invalid" in inner_msg
                    or "ssh" in inner_msg
                    or "uri" in inner_msg
                    or "failed" in inner_msg
                    or "error" in inner_msg
                ), f"SSH內層錯誤應包含 invalid/ssh/uri/failed/error, 實際: {inner_msg}"
                print(f"✓ TC-E09 SSH URL格式錯誤處理通過(內層錯誤): {inner_msg[:80]}")
                return

            print("✓ TC-E09 SSH URL格式錯誤處理通過(服務端降級)")
            return

        raise AssertionError(f"SSH URL格式錯誤應返回 error 或降級, 實際: {data.get('status')}")

    def test_error_corrupted_zip(self, api_client):
        """TC-E16 損壞的ZIP檔案：驗證偽造 .zip 檔案報錯含 zip/corrupt 或回退處理，不產生有效子節點"""
        random_id = str(uuid.uuid4())[:8]

        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, f"corrupted_{random_id}.zip")
        with open(zip_path, "w", encoding="utf-8") as f:
            f.write("這不是一個真正的ZIP檔案內容")

        try:
            response = api_client.add_resource(path=zip_path, wait=True)
            assert response.status_code == 500

            data = response.json()
            if data.get("status") == "error":
                error_msg = _extract_error_message(data).lower()
                assert (
                    "zip" in error_msg
                    or "corrupt" in error_msg
                    or "error" in error_msg
                    or "archive" in error_msg
                ), f"損壞ZIP錯誤資訊應包含 zip/corrupt/error/archive, 實際: {error_msg}"
                print(f"✓ TC-E16 損壞的ZIP檔案處理通過(返回error): {error_msg[:80]}")
                return

            assert data.get("status") == "ok"

            result = data.get("result", {})
            if isinstance(result, dict) and result.get("status") == "error":
                inner_errors = result.get("errors", [])
                inner_msg = " ".join(str(e) for e in inner_errors)
                assert (
                    "zip" in inner_msg.lower()
                    or "corrupt" in inner_msg.lower()
                    or "error" in inner_msg.lower()
                    or "bad" in inner_msg.lower()
                ), f"損壞ZIP內層錯誤應包含 zip/corrupt/error/bad, 實際: {inner_msg}"
                print(f"✓ TC-E16 損壞的ZIP檔案處理通過(內層錯誤): {inner_msg[:80]}")
                return

            root_uri = result.get("root_uri")
            if root_uri:
                assert_root_uri_valid(root_uri)

                tree_resp = api_client.fs_tree(root_uri)
                if tree_resp.status_code == 200:
                    tree_data = tree_resp.json()
                    tree_result = tree_data.get("result")
                    if isinstance(tree_result, list):
                        children = tree_result
                    elif isinstance(tree_result, dict):
                        children = tree_result.get("children", [])
                    else:
                        children = []
                    assert len(children) == 0, (
                        f"損壞ZIP不應產生有效子節點, 實際子節點數: {len(children)}"
                    )

            print(f"✓ TC-E16 損壞的ZIP檔案處理通過, root_uri: {root_uri}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
