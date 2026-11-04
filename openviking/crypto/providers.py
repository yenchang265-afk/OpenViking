# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""
Key provider abstractions and implementations.

Provides multiple key management methods:
- LocalFileProvider: Local file storage for Root Key
- VaultProvider: HashiCorp Vault
"""

import abc
import asyncio
import importlib
import os
import secrets
import time
from abc import ABC
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from openviking.crypto.exceptions import (
    AuthenticationFailedError,
    ConfigError,
)
from openviking_cli.utils.logger import get_logger

logger = get_logger(__name__)


def _record_encryption_metrics(
    *metrics: Tuple[str, Dict[str, Any]],
    debug_message: Optional[str] = None,
) -> None:
    """Emit encryption metrics without creating a hard import edge back into crypto."""
    try:
        encryption_module = importlib.import_module("openviking.metrics.datasources.encryption")
        datasource = encryption_module.EncryptionEventDataSource
        for metric_name, metric_kwargs in metrics:
            getattr(datasource, metric_name)(**metric_kwargs)
    except Exception:
        if debug_message:
            logger.debug(debug_message, exc_info=True)


# HKDF related constants
HKDF_SALT = b"openviking-kek-salt-v1"
HKDF_INFO_PREFIX = b"openviking:kek:v1:"

# Provider types
PROVIDER_LOCAL = 0x01
PROVIDER_VAULT = 0x02
PROVIDER_VOLCENGINE = 0x03


def decode_inline_root_key(root_key: object) -> bytes:
    """Decode a 32-byte root key without exposing it in validation errors."""
    error = "encryption.local.root_key must be a 64-character hexadecimal string"
    if not isinstance(root_key, str) or len(root_key) != 64:
        raise ConfigError(error)
    try:
        decoded = bytes.fromhex(root_key)
    except ValueError as exc:
        raise ConfigError(error) from exc
    if len(decoded) != 32:
        raise ConfigError(error)
    return decoded


class RootKeyProvider(ABC):
    """Root Key Provider abstract base class."""

    @abc.abstractmethod
    async def get_root_key(self) -> bytes:
        """Get Root Key (only used by Local Provider)."""
        pass

    @abc.abstractmethod
    async def derive_account_key(self, account_id: str) -> bytes:
        """Derive Account Key for the specified account."""
        pass

    @abc.abstractmethod
    async def encrypt_file_key(self, plaintext_key: bytes, account_id: str) -> Tuple[bytes, bytes]:
        """Encrypt File Key."""
        pass

    @abc.abstractmethod
    async def decrypt_file_key(self, encrypted_key: bytes, iv: bytes, account_id: str) -> bytes:
        """Decrypt File Key."""
        pass

    async def _hkdf_derive(
        self, root_key: bytes, account_id: str, salt: bytes, info_prefix: bytes
    ) -> bytes:
        """
        Derive key using HKDF.

        Args:
            root_key: Root key
            account_id: Account ID
            salt: HKDF salt
            info_prefix: HKDF info prefix

        Returns:
            Derived key
        """
        start = time.perf_counter()
        status = "ok"
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.hkdf import HKDF

            hkdf = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                info=info_prefix + account_id.encode(),
            )
            return hkdf.derive(root_key)
        except ImportError:
            status = "error"
            raise ConfigError("cryptography library is required for encryption")
        except Exception:
            status = "error"
            raise
        finally:
            elapsed = time.perf_counter() - start
            _record_encryption_metrics(
                (
                    "record_key_derivation",
                    {"status": status, "duration_seconds": elapsed},
                ),
                debug_message="Failed to record encryption key derivation metrics",
            )


class BaseProvider(RootKeyProvider):
    """Base provider with common encryption functionality."""

    async def _aes_gcm_encrypt(self, key: bytes, iv: bytes, plaintext: bytes) -> bytes:
        """AES-GCM encryption."""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(key)
            return aesgcm.encrypt(iv, plaintext, associated_data=None)
        except ImportError:
            raise ConfigError("cryptography library is required for encryption")

    async def _aes_gcm_decrypt(self, key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
        """AES-GCM decryption."""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(key)
            return aesgcm.decrypt(iv, ciphertext, associated_data=None)
        except ImportError:
            raise ConfigError("cryptography library is required for encryption")
        except Exception as e:
            raise AuthenticationFailedError(f"Decryption failed: {e}")

    async def encrypt_file_key(self, plaintext_key: bytes, account_id: str) -> Tuple[bytes, bytes]:
        """
        Encrypt File Key with Account Key.

        Args:
            plaintext_key: Plaintext File Key
            account_id: Account ID

        Returns:
            (encrypted_key, iv)
        """
        account_key = await self.derive_account_key(account_id)
        iv = secrets.token_bytes(12)
        encrypted_key = await self._aes_gcm_encrypt(account_key, iv, plaintext_key)
        return encrypted_key, iv

    async def decrypt_file_key(self, encrypted_key: bytes, iv: bytes, account_id: str) -> bytes:
        """
        Decrypt File Key with Account Key.

        Args:
            encrypted_key: Encrypted File Key
            iv: Initialization vector
            account_id: Account ID

        Returns:
            Decrypted File Key
        """
        account_key = await self.derive_account_key(account_id)
        return await self._aes_gcm_decrypt(account_key, iv, encrypted_key)


class LocalFileProvider(BaseProvider):
    """Local Root Key Provider backed by a file or inline configuration."""

    def __init__(self, key_file: Optional[str] = None, root_key: Optional[str] = None):
        """
        Initialize LocalFileProvider.

        Args:
            key_file: Root Key file path.
            root_key: 32-byte Root Key encoded as 64 hexadecimal characters.
        """
        if (key_file is None) == (root_key is None):
            raise ConfigError("exactly one of key_file or root_key must be configured")
        self.key_file = Path(key_file).expanduser() if key_file is not None else None
        self._root_key = decode_inline_root_key(root_key) if root_key is not None else None

    async def get_root_key(self) -> bytes:
        """Get Root Key."""
        if self._root_key is not None:
            _record_encryption_metrics(("record_key_cache_hit", {"provider": "local"}))
            return self._root_key

        _record_encryption_metrics(("record_key_cache_miss", {"provider": "local"}))

        start = time.perf_counter()
        status = "ok"
        try:
            self._root_key = await self._load_or_create_root_key()
            return self._root_key
        except Exception:
            status = "error"
            raise
        finally:
            elapsed = time.perf_counter() - start
            _record_encryption_metrics(
                (
                    "record_key_load",
                    {
                        "status": status,
                        "provider": "local",
                        "duration_seconds": elapsed,
                    },
                ),
                ("record_key_version_usage", {"key_version": "local"}),
                debug_message="Failed to record encryption key metrics for provider=local",
            )

    async def _load_or_create_root_key(self) -> bytes:
        """Load or create Root Key."""
        assert self.key_file is not None
        if self.key_file.exists():
            # Read existing key
            with open(self.key_file, "r") as f:
                hex_key = f.read().strip()
            try:
                return bytes.fromhex(hex_key)
            except ValueError:
                raise ConfigError(f"Invalid root key format in {self.key_file}")
        else:
            # Create new key
            root_key = secrets.token_bytes(32)
            # Ensure parent directory exists
            self.key_file.parent.mkdir(parents=True, exist_ok=True)
            # Write file with permissions 0600
            with open(self.key_file, "w") as f:
                f.write(root_key.hex())
            # Set file permissions
            os.chmod(self.key_file, 0o600)
            logger.info("Created new root key at %s", self.key_file)
            return root_key

    async def derive_account_key(self, account_id: str) -> bytes:
        """Derive Account Key from Root Key."""
        root_key = await self.get_root_key()
        return await self._hkdf_derive(root_key, account_id, HKDF_SALT, HKDF_INFO_PREFIX)


class VaultProvider(BaseProvider):
    """HashiCorp Vault Key Provider.

    Uses HashiCorp Vault's transit secrets engine for key management.
    Core features:
    - Root key management: Vault transit secrets engine (encrypted)
    - Account Key derivation: HKDF-SHA256 (from root key)
    - File Key encryption: AES-256-GCM (with Account Key)
    """

    def __init__(
        self,
        addr: str,
        token: str,
        mount_path: str = "transit",
        kv_mount_path: str = "secret",
        kv_version: int = 1,
        root_key_name: str = "openviking-root-key",
        encrypted_root_key_key: str = "openviking-encrypted-root-key",
    ):
        """
        Initialize VaultProvider.

        Args:
            addr: Vault server address (e.g., "http://127.0.0.1:8200")
            token: Vault authentication token
            mount_path: Transit secrets engine mount path (default: "transit")
            kv_mount_path: KV secrets engine mount path (default: "secret")
            kv_version: KV secrets engine version (1 or 2, default: 1)
            root_key_name: Transit engine key name (default: "openviking-root-key")
            encrypted_root_key_key: KV engine key path (default: "openviking-encrypted-root-key")
        """
        self.addr = addr
        self.token = token
        self.mount_path = mount_path
        self.kv_mount_path = kv_mount_path
        self.kv_version = kv_version
        self.root_key_name = root_key_name
        self.encrypted_root_key_key = encrypted_root_key_key
        self._client: Any = None
        self._root_key: Optional[bytes] = None

    async def _get_client(self):
        """
        Get or create Vault client.

        Returns:
            Vault client instance
        """
        if not self._client:
            try:
                import hvac
            except ImportError:
                raise ConfigError(
                    "hvac library is required for Vault provider. Install with: pip install hvac"
                )

            self._client = hvac.Client(url=self.addr, token=self.token)

            # Verify Vault is accessible
            is_auth = await asyncio.to_thread(self._client.is_authenticated)
            if not is_auth:
                raise AuthenticationFailedError("Failed to authenticate with Vault")

            # Ensure transit engine is enabled
            await self._ensure_transit_engine_enabled()

            # Ensure root key exists
            await self._ensure_root_key_exists()

        return self._client

    async def _ensure_transit_engine_enabled(self):
        """Ensure transit secrets engine is enabled."""
        try:
            # Check if transit engine is already enabled
            engines = await asyncio.to_thread(self._client.sys.list_mounted_secrets_engines)
            if f"{self.mount_path}/" not in engines["data"]:
                await asyncio.to_thread(
                    self._client.sys.enable_secrets_engine,
                    backend_type="transit",
                    path=self.mount_path,
                )
                logger.info(f"Enabled transit secrets engine at {self.mount_path}")
        except Exception as e:
            logger.warning(f"Failed to check/enable transit engine: {e}")

    async def _ensure_root_key_exists(self):
        """Ensure root key exists in Vault transit engine."""
        try:
            # Try to read the key
            await asyncio.to_thread(
                self._client.secrets.transit.read_key,
                name=self.root_key_name,
                mount_point=self.mount_path,
            )
        except Exception:
            # Key doesn't exist, create it
            await asyncio.to_thread(
                self._client.secrets.transit.create_key,
                name=self.root_key_name,
                key_type="aes256-gcm96",
                mount_point=self.mount_path,
            )
            logger.info(f"Created root key {self.root_key_name} in Vault")

    async def _encrypt_with_vault(self, plaintext: bytes) -> bytes:
        """
        Encrypt data with Vault transit.

        Args:
            plaintext: Plaintext data

        Returns:
            Encrypted data
        """
        client = await self._get_client()
        import base64

        plaintext_b64 = base64.b64encode(plaintext).decode("utf-8")
        response = await asyncio.to_thread(
            client.secrets.transit.encrypt_data,
            name=self.root_key_name,
            plaintext=plaintext_b64,
            mount_point=self.mount_path,
        )
        ciphertext_str = response["data"]["ciphertext"]
        return ciphertext_str.encode("utf-8")

    async def _decrypt_with_vault(self, ciphertext: bytes) -> bytes:
        """
        Decrypt data with Vault transit.

        Args:
            ciphertext: Encrypted data

        Returns:
            Decrypted data
        """
        client = await self._get_client()
        import base64

        ciphertext_str = ciphertext.decode("utf-8")
        response = await asyncio.to_thread(
            client.secrets.transit.decrypt_data,
            name=self.root_key_name,
            ciphertext=ciphertext_str,
            mount_point=self.mount_path,
        )
        return base64.b64decode(response["data"]["plaintext"])

    async def _get_or_create_root_key(self) -> bytes:
        """
        Get or create root key.

        Returns:
            Root key bytes
        """
        if self._root_key is not None:
            return self._root_key

        client = await self._get_client()
        import base64

        from hvac.exceptions import InvalidPath

        try:
            # Try to read encrypted root key from Vault kv
            if self.kv_version == 2:
                response = await asyncio.to_thread(
                    client.secrets.kv.v2.read_secret_version,
                    path=self.encrypted_root_key_key,
                    mount_point=self.kv_mount_path,
                )
            else:
                response = await asyncio.to_thread(
                    client.secrets.kv.v1.read_secret,
                    path=self.encrypted_root_key_key,
                    mount_point=self.kv_mount_path,
                )
        except InvalidPath:
            # Generate new root key
            import secrets

            self._root_key = secrets.token_bytes(32)

            # Encrypt and store root key in Vault kv. Any failure here (transit
            # encrypt down, KV write outage) must clear the cached ephemeral key
            # before raising: otherwise a retried get_root_key() hits the
            # `self._root_key is not None` fast path and encrypts data with a key
            # that was never persisted — the data-loss class this provider guards.
            try:
                encrypted_root_key = await self._encrypt_with_vault(self._root_key)
                if self.kv_version == 2:
                    await asyncio.to_thread(
                        client.secrets.kv.v2.create_or_update_secret,
                        path=self.encrypted_root_key_key,
                        mount_point=self.kv_mount_path,
                        secret={
                            "encrypted_root_key": base64.b64encode(encrypted_root_key).decode(
                                "utf-8"
                            )
                        },
                    )
                else:
                    await asyncio.to_thread(
                        client.secrets.kv.v1.create_or_update_secret,
                        path=self.encrypted_root_key_key,
                        mount_point=self.kv_mount_path,
                        secret={
                            "encrypted_root_key": base64.b64encode(encrypted_root_key).decode(
                                "utf-8"
                            )
                        },
                    )
                logger.info("Created and stored new root key in Vault")
            except Exception as e:
                self._root_key = None
                raise ConfigError(
                    f"Failed to persist root key to Vault. "
                    f"Refusing to start with ephemeral key (data loss risk): {e}"
                )
            return self._root_key

        if self.kv_version == 2:
            encrypted_root_key_b64 = response["data"]["data"]["encrypted_root_key"]
        else:
            encrypted_root_key_b64 = response["data"]["encrypted_root_key"]
        encrypted_root_key = base64.b64decode(encrypted_root_key_b64)
        self._root_key = await self._decrypt_with_vault(encrypted_root_key)
        logger.info("Loaded existing root key from Vault")

        return self._root_key

    async def get_root_key(self) -> bytes:
        """
        Get root key.

        Returns:
            Root key
        """
        if self._root_key is not None:
            _record_encryption_metrics(("record_key_cache_hit", {"provider": "vault"}))
            return self._root_key

        _record_encryption_metrics(("record_key_cache_miss", {"provider": "vault"}))

        start = time.perf_counter()
        status = "ok"
        try:
            self._root_key = await self._get_or_create_root_key()
            return self._root_key
        except Exception:
            status = "error"
            raise
        finally:
            elapsed = time.perf_counter() - start
            _record_encryption_metrics(
                (
                    "record_key_load",
                    {
                        "status": status,
                        "provider": "vault",
                        "duration_seconds": elapsed,
                    },
                ),
                ("record_key_version_usage", {"key_version": str(self.root_key_name)}),
                debug_message="Failed to record encryption key metrics for provider=vault",
            )

    async def derive_account_key(self, account_id: str) -> bytes:
        """
        Derive Account Key using HKDF.

        Args:
            account_id: Account ID

        Returns:
            Derived Account Key
        """
        root_key = await self.get_root_key()
        return await self._hkdf_derive(root_key, account_id, HKDF_SALT, HKDF_INFO_PREFIX)


def create_root_key_provider(
    provider_type: str,
    config: Dict[str, Any],
) -> RootKeyProvider:
    """
    Create RootKeyProvider instance.

    Args:
        provider_type: Provider type ("local", "vault")
        config: Configuration dictionary

    Returns:
        RootKeyProvider instance
    """
    if provider_type == "local":
        local_config = config.get("local", {})
        key_file_path = local_config.get("key_file")
        root_key = local_config.get("root_key")

        if key_file_path is not None and root_key is not None:
            raise ConfigError(
                "encryption.local.root_key and encryption.local.key_file are mutually exclusive"
            )
        if root_key is not None:
            return LocalFileProvider(root_key=root_key)
        if key_file_path is None:
            key_file_path = "~/.openviking/master.key"
        if not key_file_path:
            raise ConfigError("encryption.local.key_file is required")
        return LocalFileProvider(key_file_path)

    elif provider_type == "vault":
        vault_config = config.get("vault", {})
        address = vault_config.get("address")
        token = vault_config.get("token")
        mount_point = vault_config.get("mount_point", "transit")
        kv_mount_point = vault_config.get("kv_mount_point", "secret")
        kv_version = vault_config.get("kv_version", 1)
        # 相容 key_name（舊欄位，作為 root_key_name 的回退）
        # 注意：Pydantic model_dump 後 root_key_name/key_name 總是帶有預設值，
        #       因此必須顯式區分使用者是否顯式傳入了 key_name（不是預設值 "openviking-root"）。
        root_key_name = vault_config.get("root_key_name", "openviking-root-key")
        key_name_val = vault_config.get("key_name", "openviking-root")
        if root_key_name == "openviking-root-key" and key_name_val != "openviking-root":
            root_key_name = key_name_val
        encrypted_root_key_key = vault_config.get(
            "encrypted_root_key_key", "openviking-encrypted-root-key"
        )

        if not address or not token:
            raise ConfigError("vault.address and vault.token are required")
        return VaultProvider(
            address,
            token,
            mount_point,
            kv_mount_point,
            kv_version,
            root_key_name,
            encrypted_root_key_key,
        )

    else:
        raise ConfigError(f"Unsupported provider type: {provider_type}")
