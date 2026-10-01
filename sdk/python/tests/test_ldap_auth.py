import pytest
import base64
import json
import os
from pathlib import Path

from openviking_sdk import AsyncHTTPClient
from openviking_sdk.config import (
    resolve_client_config,
    get_basic_auth_header,
    load_ovcli_config,
)


class TestBasicAuthHeader:
    """測試 Basic Auth header 生成"""

    def test_get_basic_auth_header(self):
        """測試 Basic Auth header 編碼正確"""
        header = get_basic_auth_header("alice", "password123")
        expected = "Basic " + base64.b64encode(b"alice:password123").decode("ascii")
        assert header == expected

    def test_get_basic_auth_header_special_characters(self):
        """測試特殊字元的密碼"""
        header = get_basic_auth_header("user", "p@ss:w0rd!")
        expected = "Basic " + base64.b64encode(b"user:p@ss:w0rd!").decode("ascii")
        assert header == expected

    def test_get_basic_auth_header_unicode(self):
        """測試 Unicode 字元"""
        header = get_basic_auth_header("user", "pässwörd")
        expected = "Basic " + base64.b64encode("user:pässwörd".encode("utf-8")).decode("ascii")
        assert header == expected


class TestClientConfigLDAP:
    """測試 LDAP 配置解析"""

    def test_explicit_ldap_arguments(self):
        """測試顯式傳遞 LDAP 引數"""
        config = resolve_client_config(
            url="http://localhost:1933",
            auth_mode="ldap",
            ldap_username="alice",
            ldap_password="password123",
        )
        assert config.auth_mode == "ldap"
        assert config.ldap_username == "alice"
        assert config.ldap_password == "password123"
        assert config.api_key is None

    def test_env_ldap_variables(self, monkeypatch):
        """測試環境變數 LDAP 配置"""
        # Isolate from the real user config
        import openviking_sdk.config as config_module
        original_default = config_module.DEFAULT_OVCLI_CONF
        config_module.DEFAULT_OVCLI_CONF = Path("/nonexistent/path/ovcli.conf")
        monkeypatch.delenv("OPENVIKING_CLI_CONFIG_FILE", raising=False)
        monkeypatch.setenv("OPENVIKING_URL", "http://env-host:1933")
        monkeypatch.setenv("OPENVIKING_AUTH_MODE", "ldap")
        monkeypatch.setenv("OPENVIKING_USERNAME", "bob")
        monkeypatch.setenv("OPENVIKING_PASSWORD", "secret456")
        monkeypatch.delenv("OPENVIKING_API_KEY", raising=False)

        try:
            config = resolve_client_config()
            assert config.auth_mode == "ldap"
            assert config.ldap_username == "bob"
            assert config.ldap_password == "secret456"
        finally:
            config_module.DEFAULT_OVCLI_CONF = original_default

    def test_explicit_overrides_env(self, monkeypatch):
        """測試顯式引數覆蓋環境變數"""
        import openviking_sdk.config as config_module
        original_default = config_module.DEFAULT_OVCLI_CONF
        config_module.DEFAULT_OVCLI_CONF = Path("/nonexistent/path/ovcli.conf")
        monkeypatch.delenv("OPENVIKING_CLI_CONFIG_FILE", raising=False)
        monkeypatch.setenv("OPENVIKING_AUTH_MODE", "ldap")
        monkeypatch.setenv("OPENVIKING_USERNAME", "env-user")
        monkeypatch.setenv("OPENVIKING_PASSWORD", "env-pass")

        try:
            config = resolve_client_config(
                url="http://localhost:1933",
                auth_mode="ldap",
                ldap_username="explicit-user",
                ldap_password="explicit-pass",
            )
            assert config.auth_mode == "ldap"
            assert config.ldap_username == "explicit-user"
            assert config.ldap_password == "explicit-pass"
        finally:
            config_module.DEFAULT_OVCLI_CONF = original_default

    def test_no_ldap_config_defaults(self, monkeypatch):
        """測試無 LDAP 配置時的預設值"""
        monkeypatch.delenv("OPENVIKING_AUTH_MODE", raising=False)
        monkeypatch.delenv("OPENVIKING_USERNAME", raising=False)
        monkeypatch.delenv("OPENVIKING_PASSWORD", raising=False)
        monkeypatch.delenv("OPENVIKING_CLI_CONFIG_FILE", raising=False)

        # Need to make sure no user config is loaded
        # Patch the default config path to not exist
        import openviking_sdk.config as config_module
        original_default = config_module.DEFAULT_OVCLI_CONF
        config_module.DEFAULT_OVCLI_CONF = Path("/nonexistent/path/ovcli.conf")
        try:
            config = resolve_client_config(url="http://localhost:1933")
            assert config.auth_mode is None
            assert config.ldap_username is None
            assert config.ldap_password is None
        finally:
            config_module.DEFAULT_OVCLI_CONF = original_default

    def test_ldap_partial_config(self, monkeypatch):
        """測試部分 LDAP 配置"""
        monkeypatch.delenv("OPENVIKING_AUTH_MODE", raising=False)
        monkeypatch.delenv("OPENVIKING_USERNAME", raising=False)
        monkeypatch.delenv("OPENVIKING_PASSWORD", raising=False)
        monkeypatch.delenv("OPENVIKING_CLI_CONFIG_FILE", raising=False)
        
        import openviking_sdk.config as config_module
        original_default = config_module.DEFAULT_OVCLI_CONF
        config_module.DEFAULT_OVCLI_CONF = Path("/nonexistent/path/ovcli.conf")
        try:
            # 只設置 username，不設定 password
            config = resolve_client_config(
                url="http://localhost:1933",
                ldap_username="alice",
            )
            assert config.ldap_username == "alice"
            assert config.ldap_password is None
        finally:
            config_module.DEFAULT_OVCLI_CONF = original_default


class TestConfigFileLDAP:
    """測試配置檔案中的 LDAP 配置"""

    def test_load_ldap_config_from_file(self, tmp_path, monkeypatch):
        """測試從配置檔案載入 LDAP 配置"""
        config_data = {
            "url": "http://file-host:1933",
            "auth_mode": "ldap",
            "ldap_username": "config-user",
            "ldap_password": "config-pass",
            "account": "default",
        }
        config_file = tmp_path / "ovcli.conf"
        config_file.write_text(json.dumps(config_data))

        # 設定配置檔案路徑
        monkeypatch.setenv("OPENVIKING_CLI_CONFIG_FILE", str(config_file))
        # 清除其他環境變數
        monkeypatch.delenv("OPENVIKING_AUTH_MODE", raising=False)
        monkeypatch.delenv("OPENVIKING_USERNAME", raising=False)
        monkeypatch.delenv("OPENVIKING_PASSWORD", raising=False)

        config = load_ovcli_config()
        assert config is not None
        assert config.url == "http://file-host:1933"
        assert config.auth_mode == "ldap"
        assert config.ldap_username == "config-user"
        assert config.ldap_password == "config-pass"

    def test_config_file_ldap_missing_password(self, tmp_path, monkeypatch):
        """測試配置檔案中缺少密碼"""
        config_data = {
            "url": "http://file-host:1933",
            "auth_mode": "ldap",
            "ldap_username": "config-user",
            # password 缺失
        }
        config_file = tmp_path / "ovcli.conf"
        config_file.write_text(json.dumps(config_data))

        monkeypatch.setenv("OPENVIKING_CLI_CONFIG_FILE", str(config_file))

        config = load_ovcli_config()
        assert config is not None
        assert config.ldap_username == "config-user"
        assert config.ldap_password is None

    def test_config_file_api_key_mode(self, tmp_path, monkeypatch):
        """測試 API Key 模式（向後相容）"""
        config_data = {
            "url": "http://file-host:1933",
            "api_key": "sk-test-key",
            # 沒有 auth_mode，預設使用 API Key
        }
        config_file = tmp_path / "ovcli.conf"
        config_file.write_text(json.dumps(config_data))

        monkeypatch.setenv("OPENVIKING_CLI_CONFIG_FILE", str(config_file))

        config = load_ovcli_config()
        assert config is not None
        assert config.api_key == "sk-test-key"
        assert config.auth_mode is None


class TestAsyncHTTPClientLDAP:
    """測試 AsyncHTTPClient 的 LDAP 支援"""

    def test_client_ldap_attributes(self, monkeypatch):
        """測試客戶端儲存 LDAP 屬性"""
        monkeypatch.delenv("OPENVIKING_CLI_CONFIG_FILE", raising=False)
        import openviking_sdk.config as config_module
        original_default = config_module.DEFAULT_OVCLI_CONF
        config_module.DEFAULT_OVCLI_CONF = Path("/nonexistent/path/ovcli.conf")
        try:
            client = AsyncHTTPClient(
                url="http://localhost:1933",
                auth_mode="ldap",
                ldap_username="alice",
                ldap_password="password123",
            )
            assert client._auth_mode == "ldap"
            assert client._ldap_username == "alice"
            assert client._ldap_password == "password123"
        finally:
            config_module.DEFAULT_OVCLI_CONF = original_default

    def test_client_no_ldap_by_default(self, monkeypatch):
        """測試預設不使用 LDAP"""
        monkeypatch.delenv("OPENVIKING_CLI_CONFIG_FILE", raising=False)
        import openviking_sdk.config as config_module
        original_default = config_module.DEFAULT_OVCLI_CONF
        config_module.DEFAULT_OVCLI_CONF = Path("/nonexistent/path/ovcli.conf")
        try:
            client = AsyncHTTPClient(
                url="http://localhost:1933",
                api_key="sk-test",
            )
            assert client._auth_mode is None
            assert client._ldap_username is None
            assert client._ldap_password is None
        finally:
            config_module.DEFAULT_OVCLI_CONF = original_default

    @pytest.mark.asyncio
    async def test_client_initialize_with_ldap(self, monkeypatch):
        """測試初始化時新增 LDAP header"""
        monkeypatch.delenv("OPENVIKING_CLI_CONFIG_FILE", raising=False)
        import openviking_sdk.config as config_module
        original_default = config_module.DEFAULT_OVCLI_CONF
        config_module.DEFAULT_OVCLI_CONF = Path("/nonexistent/path/ovcli.conf")
        try:
            client = AsyncHTTPClient(
                url="http://localhost:1933",
                auth_mode="ldap",
                ldap_username="alice",
                ldap_password="password123",
            )
            await client.initialize()
            try:
                # 檢查 HTTP client 的 headers（HTTP headers 是小寫的）
                assert client._http is not None
                headers = {k.lower(): v for k, v in client._http.headers.items()}
                assert "authorization" in headers
                expected_auth = get_basic_auth_header("alice", "password123")
                assert headers["authorization"] == expected_auth
                # 確認沒有 x-api-key header
                assert "x-api-key" not in headers
            finally:
                await client.close()
        finally:
            config_module.DEFAULT_OVCLI_CONF = original_default

    @pytest.mark.asyncio
    async def test_client_initialize_with_api_key(self, monkeypatch):
        """測試 API Key 模式不新增 Authorization header"""
        monkeypatch.delenv("OPENVIKING_CLI_CONFIG_FILE", raising=False)
        import openviking_sdk.config as config_module
        original_default = config_module.DEFAULT_OVCLI_CONF
        config_module.DEFAULT_OVCLI_CONF = Path("/nonexistent/path/ovcli.conf")
        try:
            client = AsyncHTTPClient(
                url="http://localhost:1933",
                api_key="sk-test-key",
            )
            await client.initialize()
            try:
                assert client._http is not None
                headers = {k.lower(): v for k, v in client._http.headers.items()}
                assert "x-api-key" in headers
                assert headers["x-api-key"] == "sk-test-key"
                # 確認沒有 authorization header
                assert "authorization" not in headers
            finally:
                await client.close()
        finally:
            config_module.DEFAULT_OVCLI_CONF = original_default

    @pytest.mark.asyncio
    async def test_client_ldap_missing_password(self, monkeypatch):
        """測試 LDAP 模式但缺少密碼時不新增 header"""
        monkeypatch.delenv("OPENVIKING_CLI_CONFIG_FILE", raising=False)
        import openviking_sdk.config as config_module
        original_default = config_module.DEFAULT_OVCLI_CONF
        config_module.DEFAULT_OVCLI_CONF = Path("/nonexistent/path/ovcli.conf")
        try:
            client = AsyncHTTPClient(
                url="http://localhost:1933",
                auth_mode="ldap",
                ldap_username="alice",
                # password 缺失
            )
            await client.initialize()
            try:
                assert client._http is not None
                headers = {k.lower(): v for k, v in client._http.headers.items()}
                # 不應該新增 authorization header
                assert "authorization" not in headers
            finally:
                await client.close()
        finally:
            config_module.DEFAULT_OVCLI_CONF = original_default

    @pytest.mark.asyncio
    async def test_client_ldap_extra_headers_combined(self, monkeypatch):
        """測試 LDAP header 與其他自定義 header 共存"""
        monkeypatch.delenv("OPENVIKING_CLI_CONFIG_FILE", raising=False)
        import openviking_sdk.config as config_module
        original_default = config_module.DEFAULT_OVCLI_CONF
        config_module.DEFAULT_OVCLI_CONF = Path("/nonexistent/path/ovcli.conf")
        try:
            client = AsyncHTTPClient(
                url="http://localhost:1933",
                auth_mode="ldap",
                ldap_username="alice",
                ldap_password="password123",
                extra_headers={"X-Custom": "value"},
            )
            await client.initialize()
            try:
                assert client._http is not None
                headers = {k.lower(): v for k, v in client._http.headers.items()}
                assert "authorization" in headers
                assert "x-custom" in headers
            finally:
                await client.close()
        finally:
            config_module.DEFAULT_OVCLI_CONF = original_default


class TestLDAPEdgeCases:
    """測試 LDAP 邊界情況"""

    def test_empty_username_password(self):
        """測試空使用者名稱和密碼"""
        header = get_basic_auth_header("", "")
        expected = "Basic " + base64.b64encode(b":").decode("ascii")
        assert header == expected

    def test_auth_mode_case_sensitive(self, monkeypatch):
        """測試 auth_mode 大小寫（當前實現區分大小寫）"""
        monkeypatch.delenv("OPENVIKING_CLI_CONFIG_FILE", raising=False)
        monkeypatch.setenv("OPENVIKING_URL", "http://localhost:1933")
        monkeypatch.setenv("OPENVIKING_AUTH_MODE", "LDAP")
        monkeypatch.setenv("OPENVIKING_USERNAME", "alice")
        monkeypatch.setenv("OPENVIKING_PASSWORD", "secret")
        
        import openviking_sdk.config as config_module
        original_default = config_module.DEFAULT_OVCLI_CONF
        config_module.DEFAULT_OVCLI_CONF = Path("/nonexistent/path/ovcli.conf")
        try:
            config = resolve_client_config()
            # 當前實現是區分大小寫的，所以 "LDAP" 會被保留但不會觸發 Basic Auth
            assert config.auth_mode == "LDAP"
        finally:
            config_module.DEFAULT_OVCLI_CONF = original_default

    def test_mixed_auth_config(self, monkeypatch):
        """測試同時配置 API Key 和 LDAP"""
        monkeypatch.delenv("OPENVIKING_CLI_CONFIG_FILE", raising=False)
        import openviking_sdk.config as config_module
        original_default = config_module.DEFAULT_OVCLI_CONF
        config_module.DEFAULT_OVCLI_CONF = Path("/nonexistent/path/ovcli.conf")
        try:
            client = AsyncHTTPClient(
                url="http://localhost:1933",
                api_key="sk-test",
                auth_mode="ldap",
                ldap_username="alice",
                ldap_password="password123",
            )
            # LDAP 配置被儲存
            assert client._auth_mode == "ldap"
            assert client._api_key == "sk-test"
            assert client._ldap_username == "alice"
        finally:
            config_module.DEFAULT_OVCLI_CONF = original_default

    @pytest.mark.asyncio
    async def test_mixed_auth_ldap_wins(self, monkeypatch):
        """測試同時配置時 LDAP 新增 Authorization header"""
        monkeypatch.delenv("OPENVIKING_CLI_CONFIG_FILE", raising=False)
        import openviking_sdk.config as config_module
        original_default = config_module.DEFAULT_OVCLI_CONF
        config_module.DEFAULT_OVCLI_CONF = Path("/nonexistent/path/ovcli.conf")
        try:
            client = AsyncHTTPClient(
                url="http://localhost:1933",
                api_key="sk-test",
                auth_mode="ldap",
                ldap_username="alice",
                ldap_password="password123",
            )
            await client.initialize()
            try:
                headers = {k.lower(): v for k, v in client._http.headers.items()}
                # LDAP 應該新增 authorization header
                assert "authorization" in headers
                # 也可以同時有 x-api-key（兩者都會新增）
                assert "x-api-key" in headers
            finally:
                await client.close()
        finally:
            config_module.DEFAULT_OVCLI_CONF = original_default
