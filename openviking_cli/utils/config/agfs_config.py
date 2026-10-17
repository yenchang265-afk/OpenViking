# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
from __future__ import annotations

import math
from enum import Enum
from typing import Any, List, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

from openviking_cli.utils.logger import get_logger

logger = get_logger(__name__)


class DirectoryMarkerMode(str, Enum):
    """How S3 directory markers should be persisted."""

    NONE = "none"
    EMPTY = "empty"
    NONEMPTY = "nonempty"


class S3Config(BaseModel):
    """Configuration for S3 backend."""

    bucket: Optional[str] = Field(default=None, description="S3 bucket name")

    region: Optional[str] = Field(
        default=None,
        description="AWS region where the bucket is located (e.g., us-east-1, cn-beijing)",
    )

    access_key: Optional[str] = Field(
        default=None,
        description="S3 access key ID (required; RAGFS has no default credential chain). "
        'Use "${VAR}" to read it from the environment.',
    )

    secret_key: Optional[str] = Field(
        default=None,
        description="S3 secret access key corresponding to the access key ID (required). "
        'Use "${VAR}" to read it from the environment.',
    )

    endpoint: Optional[str] = Field(
        default=None,
        description="Custom S3 endpoint URL. Required for S3-compatible services like MinIO or LocalStack. "
        "Leave empty for standard AWS S3.",
    )

    prefix: Optional[str] = Field(
        default="",
        description="Optional key prefix for namespace isolation. All objects will be stored under this prefix.",
    )

    use_ssl: bool = Field(
        default=True,
        description="Enable/Disable SSL (HTTPS) for S3 connections. Set to False for local testing without HTTPS.",
    )

    use_path_style: bool = Field(
        default=True,
        description="true represent UsePathStyle for MinIO and some S3-compatible services; false represent VirtualHostStyle for TOS  and some S3-compatible services.",
    )

    directory_marker_mode: DirectoryMarkerMode = Field(
        default=DirectoryMarkerMode.EMPTY,
        description="How to persist S3 directory markers: 'none' skips marker creation, 'empty' writes a zero-byte marker, and 'nonempty' writes a non-empty marker payload. Defaults to 'empty'.",
    )

    disable_batch_delete: bool = Field(
        default=False,
        description="Disable batch delete (DeleteObjects) and use sequential single-object deletes instead. "
        "Required for S3-compatible services like Alibaba Cloud OSS that require a Content-MD5 header "
        "for DeleteObjects but AWS SDK v2 does not send it by default. Defaults to False.",
    )

    normalize_encoding_chars: str = Field(
        default="?#%+@",
        description="Characters to escape in S3 object keys as !HH hexadecimal bytes. "
        "Set to an empty string to disable key normalization. Defaults to ?#%+@.",
    )

    auto_detect_content_type: bool = Field(
        default=False,
        description="Automatically infer S3 object Content-Type from the object key filename extension "
        "during uploads. Disabled by default for backward compatibility.",
    )

    multipart_threshold_bytes: Optional[int] = Field(
        default=None,
        gt=0,
        description="Files larger than this are uploaded with S3 multipart upload. "
        "Unset uses the s3fs default (16 MiB).",
    )

    multipart_part_size_bytes: Optional[int] = Field(
        default=None,
        ge=5 * 1024 * 1024,
        le=5 * 1024 * 1024 * 1024,
        description="Multipart upload part size; S3 requires 5 MiB to 5 GiB. "
        "Unset uses the s3fs default (8 MiB).",
    )

    multipart_concurrency: Optional[int] = Field(
        default=None,
        ge=1,
        le=32,
        description="Multipart parts uploaded at once; memory held is this times the part "
        "size. Unset uses the s3fs default (4).",
    )

    # Request deadlines and retries. Unset values use the s3fs defaults, which bound
    # every S3 call so a slow or stalled endpoint fails fast instead of hanging.
    connect_timeout_ms: Optional[int] = Field(
        default=None, gt=0, description="Max time to connect to S3. s3fs default: 5000."
    )

    read_timeout_ms: Optional[int] = Field(
        default=None,
        gt=0,
        description="Max wait for the first response byte after sending a request. "
        "s3fs default: 20000.",
    )

    operation_attempt_timeout_ms: Optional[int] = Field(
        default=None,
        gt=0,
        description="Per-attempt deadline for data operations (GET/PUT/copy/multipart part). "
        "s3fs default: 120000.",
    )

    operation_timeout_ms: Optional[int] = Field(
        default=None,
        gt=0,
        description="Total deadline for data operations, including retries. s3fs default: 300000.",
    )

    metadata_attempt_timeout_ms: Optional[int] = Field(
        default=None,
        gt=0,
        description="Per-attempt deadline for HEAD/LIST/DELETE. s3fs default: 15000.",
    )

    metadata_operation_timeout_ms: Optional[int] = Field(
        default=None,
        gt=0,
        description="Total deadline for HEAD/LIST/DELETE, including retries. s3fs default: 45000.",
    )

    max_attempts: Optional[int] = Field(
        default=None,
        ge=1,
        le=10,
        description="Max attempts per S3 request, including the first. s3fs default: 3.",
    )

    retry_mode: Optional[Literal["standard", "adaptive"]] = Field(
        default=None,
        description="'adaptive' adds client-side rate limiting when S3 throttles (e.g. 503 "
        "SlowDown). s3fs default: 'standard'.",
    )

    initial_backoff_ms: Optional[int] = Field(
        default=None, gt=0, description="Initial retry backoff. s3fs default: 1000."
    )

    max_backoff_ms: Optional[int] = Field(
        default=None, gt=0, description="Max retry backoff. s3fs default: 20000."
    )

    max_concurrent_requests: Optional[int] = Field(
        default=None,
        ge=0,
        le=10_000,
        description="Max S3 requests in flight per mount; 0 means unlimited. A request that "
        "cannot start within metadata_operation_timeout_ms fails with a timeout. "
        "s3fs default: 128.",
    )

    # Metadata (listing/stat) cache in front of S3. Unset values use the s3fs defaults.
    cache_enabled: Optional[bool] = Field(
        default=None, description="Cache directory listings and stat results. s3fs default: true."
    )

    cache_max_size: Optional[int] = Field(
        default=None, gt=0, description="Max cached directory listings. s3fs default: 1000."
    )

    cache_ttl: Optional[int] = Field(
        default=None, ge=0, description="Directory listing cache TTL in seconds. s3fs default: 30."
    )

    stat_cache_ttl: Optional[int] = Field(
        default=None, ge=0, description="Stat cache TTL in seconds. s3fs default: 60."
    )

    def validate_config(self):
        """Validate S3 configuration completeness"""
        missing = []
        if not self.bucket:
            missing.append("bucket")
        if not self.endpoint:
            missing.append("endpoint")
        if not self.region:
            missing.append("region")
        if not self.access_key:
            missing.append("access_key")
        if not self.secret_key:
            missing.append("secret_key")

        if missing:
            raise ValueError(f"S3 backend requires the following fields: {', '.join(missing)}")

        # Mirrors s3fs: an http:// or https:// endpoint wins and use_ssl is ignored.
        scheme = next((s for s in ("https", "http") if self.endpoint.startswith(f"{s}://")), None)
        if (
            "use_ssl" in self.model_fields_set
            and scheme is not None
            and self.use_ssl != (scheme == "https")
        ):
            logger.warning(
                "S3Config: use_ssl=%s is ignored because endpoint uses %s://; "
                "the endpoint scheme decides whether TLS is used.",
                self.use_ssl,
                scheme,
            )

        return self


class QueueFSConfig(BaseModel):
    """Configuration for QueueFS backend."""

    mode: str = Field(
        default="shared",
        description="QueueFS namespace mode: 'shared' | 'worker'",
    )

    backend: str = Field(
        default="sqlite",
        description="QueueFS backend: 'memory' | 'sqlite' | 'sqlite3' | 'cache'",
    )

    db_path: Optional[str] = Field(
        default=None,
        description="SQLite database path for QueueFS when backend is 'sqlite' or 'sqlite3'.",
    )

    recover_stale_sec: int = Field(
        default=0,
        description="Recover processing messages older than this many seconds on startup (0 = recover all).",
    )

    busy_timeout_ms: int = Field(
        default=5000,
        description="SQLite busy timeout for QueueFS in milliseconds.",
    )

    @model_validator(mode="after")
    def validate_config(self):
        """Validate QueueFS mode and backend choices."""
        valid_modes = {"shared", "worker"}
        if self.mode not in valid_modes:
            raise ValueError("queuefs mode must be one of: 'shared', 'worker'")

        valid_backends = {"memory", "sqlite", "sqlite3", "cache"}
        if self.backend not in valid_backends:
            raise ValueError(
                "queuefs backend must be one of: 'memory', 'sqlite', 'sqlite3', 'cache'; "
                "backend='redis' was removed, use backend='cache' with top-level cache.provider/cache.params"
            )
        if self.recover_stale_sec < 0:
            raise ValueError("queuefs recover_stale_sec must be >= 0")
        if self.busy_timeout_ms < 0:
            raise ValueError("queuefs busy_timeout_ms must be >= 0")
        return self


class AGFSCacheTraversalMode(str, Enum):
    """Traversal strategy for cache-aware recursive RAGFS APIs."""

    BACKEND = "backend"
    CACHED_TRAVERSAL = "cached_traversal"


class AGFSCacheFSConfig(BaseModel):
    """CacheFS behavior independent from the selected global Provider."""

    backend: Literal["local", "cache"] = Field(
        default="local",
        description="CacheFS backend: 'local' | 'cache'",
    )
    max_file_size_bytes: int = Field(
        default=1024 * 1024,
        description="Maximum full-file object size admitted to cache",
    )
    traversal_mode: AGFSCacheTraversalMode = Field(
        default=AGFSCacheTraversalMode.BACKEND,
        description="Traversal strategy for tree, glob, and grep",
    )
    bypass_prefixes: list[str] = Field(
        default_factory=list,
        description="Path prefixes that bypass cache",
    )

    @model_validator(mode="after")
    def validate_config(self):
        """Validate CacheFS limits."""
        if self.max_file_size_bytes <= 0:
            raise ValueError("cachefs max_file_size_bytes must be > 0")
        return self


class RedisCacheConfig(BaseModel):
    """Configuration for Redis cache provider."""

    mode: str = Field(default="standalone", description="Redis deployment mode")
    endpoints: list[str] = Field(
        default_factory=lambda: ["redis://127.0.0.1:6379"],
        description="Redis endpoint URLs",
    )
    username: str = Field(default="", description="Redis ACL username")
    password_env: str = Field(default="", description="Environment variable containing password")
    password: str = Field(
        default="",
        description="Legacy plaintext Redis password; prefer password_env",
        repr=False,
    )
    master_name: Optional[str] = Field(default=None, description="Sentinel master name")
    sentinel_username: str = Field(default="", description="Sentinel ACL username")
    sentinel_password_env: str = Field(
        default="", description="Environment variable containing Sentinel password"
    )
    sentinel_password: str = Field(
        default="",
        description="Legacy plaintext Sentinel password; prefer sentinel_password_env",
        repr=False,
    )
    db: int = Field(default=0, description="Redis database number")
    pool_size: int = Field(default=32, description="Redis command concurrency")
    connect_timeout_ms: int = Field(default=1000, description="Redis connect timeout")
    command_timeout_ms: int = Field(default=20, description="Redis command timeout")
    default_ttl_seconds: int = Field(default=3600, description="Redis default cache TTL")
    tls_insecure_skip_verify: bool = Field(
        default=False, description="Skip Redis TLS certificate verification"
    )

    @model_validator(mode="after")
    def validate_config(self):
        if self.mode not in {"standalone", "cluster", "sentinel"}:
            raise ValueError("redis mode must be standalone, cluster, or sentinel")
        if not self.endpoints:
            raise ValueError("redis endpoints must not be empty")
        schemes = set()
        for endpoint in self.endpoints:
            parsed = urlparse(endpoint)
            if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
                raise ValueError("redis endpoints must use redis:// or rediss:// URLs")
            schemes.add(parsed.scheme)
            try:
                port = parsed.port
            except ValueError as error:
                raise ValueError("redis endpoint port is invalid") from error
            if port == 0:
                raise ValueError("redis endpoint port is invalid")
            if (
                parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "redis endpoints must not include credentials, database paths, "
                    "query parameters, or fragments; use dedicated redis fields"
                )
        if self.mode == "standalone" and len(self.endpoints) != 1:
            raise ValueError("redis standalone mode requires exactly one endpoint")
        if self.mode == "cluster" and self.db != 0:
            raise ValueError("redis cluster mode requires db=0")
        if self.mode == "sentinel" and not (self.master_name or "").strip():
            raise ValueError("redis sentinel mode requires master_name")
        if self.db < 0 or self.db > 255:
            raise ValueError("redis db must be between 0 and 255")
        if self.pool_size <= 0:
            raise ValueError("redis pool_size must be > 0")
        if self.connect_timeout_ms <= 0:
            raise ValueError("redis connect_timeout_ms must be > 0")
        if self.command_timeout_ms <= 0:
            raise ValueError("redis command_timeout_ms must be > 0")
        if self.default_ttl_seconds < 0:
            raise ValueError("redis default_ttl_seconds must be >= 0")
        if len(schemes) != 1:
            raise ValueError("redis endpoints must use the same URL scheme")
        if self.password_env and self.password:
            raise ValueError("redis password and password_env cannot both be configured")
        if self.sentinel_password_env and self.sentinel_password:
            raise ValueError(
                "redis sentinel_password and sentinel_password_env cannot both be configured"
            )
        if self.tls_insecure_skip_verify and schemes != {"rediss"}:
            raise ValueError("redis tls_insecure_skip_verify requires rediss:// endpoints")
        return self


class StorageCircuitBreakerConfig(BaseModel):
    """Circuit breaker for storage calls, scoped per account and per other mount."""

    enabled: bool = Field(
        default=True,
        description="Fail storage calls fast (HTTP 503) while their backend keeps timing out, "
        "instead of making every call wait for its full deadline. Scoped per account "
        "(/local/{account}) and per other mount, so one tenant cannot pause others.",
    )
    failure_threshold: int = Field(
        default=5,
        ge=1,
        description="Consecutive timeout/network failures in a scope that open its circuit.",
    )
    reset_timeout_seconds: float = Field(
        default=15.0,
        gt=0,
        description="Seconds an open circuit waits before letting a probe call through.",
    )
    max_reset_timeout_seconds: float = Field(
        default=120.0,
        gt=0,
        description="Upper bound for the wait, which doubles each time a probe fails.",
    )

    @model_validator(mode="after")
    def _reset_within_max(self) -> "StorageCircuitBreakerConfig":
        if self.reset_timeout_seconds > self.max_reset_timeout_seconds:
            raise ValueError("reset_timeout_seconds must not exceed max_reset_timeout_seconds")
        return self


class AGFSPathLockConfig(BaseModel):
    """Configuration for the native RAGFS path lock service."""

    @model_validator(mode="after")
    def ignore_deprecated_lock_timeout(self):
        """Warn and force the deprecated timeout back to the fixed runtime value."""
        if "lock_timeout_secs" in self.model_fields_set:
            logger.warning(
                "AGFSPathLockConfig: 'storage.agfs.pathlock.lock_timeout_secs' is deprecated "
                "and ignored; the runtime wait timeout is fixed at 0.0 seconds."
            )
            self.lock_timeout_secs = 0.0
        return self

    provider: str = Field(
        default="filesystem",
        description="PathLock provider: 'filesystem' | 'memory' | 'cache'",
    )
    lock_timeout_secs: float = Field(
        default=0.0,
        description="Deprecated internal field. Runtime auto-pathlock wait timeout is fixed at 0.0 seconds.",
    )
    lock_expire_secs: float = Field(
        default=30.0,
        description="Seconds before an unrefreshed lock token becomes stale.",
    )

    @model_validator(mode="after")
    def validate_config(self):
        """Validate provider and timeout/expiry ranges."""
        if self.provider not in {"filesystem", "memory", "cache"}:
            raise ValueError("pathlock provider must be one of: 'filesystem', 'memory', 'cache'")
        if not math.isfinite(self.lock_expire_secs) or self.lock_expire_secs < 1.0:
            raise ValueError("pathlock lock_expire_secs must be finite and >= 1.0")
        return self


class AGFSConfig(BaseModel):
    """Configuration for RAGFS (Rust-based AGFS)."""

    name: str = Field(
        default="primary",
        description="Logical backend name, globally unique across primary and all backups",
    )

    path: Optional[str] = Field(
        default=None,
        description="[Deprecated in favor of `storage.workspace`] RAGFS data storage path. This will be ignored if `storage.workspace` is set.",
    )

    port: Any = Field(
        default=None,
        exclude=True,
        description="[Deprecated] Legacy AGFS service port. Ignored by RAGFS.",
    )

    log_level: Any = Field(
        default=None,
        exclude=True,
        description="[Deprecated] Legacy AGFS log level. Ignored by RAGFS.",
    )

    url: Any = Field(
        default=None,
        exclude=True,
        description="[Deprecated] Legacy AGFS service URL. Ignored by RAGFS.",
    )

    mode: Any = Field(
        default=None,
        exclude=True,
        description="[Deprecated] Legacy AGFS client mode. Ignored by RAGFS.",
    )

    impl: Any = Field(
        default=None,
        exclude=True,
        description="[Deprecated] Legacy AGFS binding implementation selector. Ignored by RAGFS.",
    )

    backend: str = Field(
        default="local", description="RAGFS storage backend: 'local' | 's3' | 'memory'"
    )

    timeout: int = Field(default=10, description="RAGFS request timeout (seconds)")

    fs_executor_threads: int = Field(
        default=64,
        ge=1,
        description="Threads in the dedicated pool that runs blocking storage calls, kept "
        "separate from the default executor so a slow backend cannot starve other work.",
    )

    fs_queue_timeout_ms: int = Field(
        default=30_000,
        gt=0,
        description="A storage call that cannot start within this time (all storage threads "
        "busy) fails fast with a timeout (HTTP 503) instead of queueing indefinitely.",
    )

    circuit_breaker: StorageCircuitBreakerConfig = Field(
        default_factory=StorageCircuitBreakerConfig,
        description="Circuit breaker for storage calls, scoped per account and per other mount.",
    )

    queue_db_path: Optional[str] = Field(
        default=None,
        description="Override path of the queuefs sqlite database file. "
        "Defaults to '{storage.workspace}/_system/queue/queue.db' when not set. "
        "Useful when the workspace volume does not support sqlite (e.g. some network filesystems).",
    )

    queuefs: QueueFSConfig = Field(
        default_factory=QueueFSConfig,
        description="QueueFS configuration.",
    )

    cachefs: AGFSCacheFSConfig = Field(
        default_factory=AGFSCacheFSConfig,
        description="CacheFS configuration.",
    )

    pathlock: AGFSPathLockConfig = Field(
        default_factory=AGFSPathLockConfig,
        description="Native RAGFS path lock configuration.",
    )

    retry_times: Any = Field(
        default=None,
        exclude=True,
        description="[Deprecated] Legacy AGFS retry count. Ignored by RAGFS.",
    )

    use_ssl: Any = Field(
        default=None,
        exclude=True,
        description="[Deprecated] Legacy AGFS SSL switch. Ignored by RAGFS.",
    )

    lib_path: Any = Field(
        default=None,
        exclude=True,
        description="[Deprecated] Legacy AGFS binding library path. Ignored by RAGFS.",
    )

    # S3 backend configuration
    # These settings are used when backend is set to 's3'.
    # RAGFS will act as a gateway to the specified S3 bucket.
    s3: S3Config = Field(default_factory=lambda: S3Config(), description="S3 backend configuration")

    # Multi-write configuration
    backups: Optional[dict[str, Any]] = Field(
        default=None, description="Multi-write backups configuration. None = single backend mode."
    )
    redirects: Optional[List[dict[str, Any]]] = Field(
        default=None, description="[Deprecated] Primary redirect policies. Ignored by V2."
    )

    @model_validator(mode="after")
    def validate_config(self):
        """Validate configuration completeness and consistency"""
        deprecated_fields = (
            "port",
            "log_level",
            "url",
            "mode",
            "impl",
            "retry_times",
            "use_ssl",
            "lib_path",
        )
        for field_name in deprecated_fields:
            if field_name in self.model_fields_set:
                logger.warning(
                    "AGFSConfig: 'storage.agfs.%s' is deprecated and ignored after the RAGFS migration.",
                    field_name,
                )

        if self.backend not in ["local", "s3", "memory"]:
            raise ValueError(
                f"Invalid RAGFS backend: '{self.backend}'. Must be one of: 'local', 's3', 'memory'"
            )

        if self.backend == "local":
            pass

        elif self.backend == "s3":
            # Validate S3 configuration
            self.s3.validate_config()

        if self.queue_db_path is not None and self.queuefs.db_path is None:
            logger.warning(
                "AGFSConfig: 'storage.agfs.queue_db_path' is deprecated; "
                "prefer 'storage.agfs.queuefs.db_path'."
            )

        if self.queuefs.backend == "memory":
            if self.queuefs.db_path is not None or self.queue_db_path is not None:
                logger.warning(
                    "AGFSConfig: QueueFS backend is 'memory'; "
                    "db_path/queue_db_path will be ignored."
                )

        if self.backups is not None:
            initial_partitions = self.backups.get("initial_partitions", 16)
            if (
                not isinstance(initial_partitions, int)
                or isinstance(initial_partitions, bool)
                or not 1 <= initial_partitions <= 1024
            ):
                raise ValueError("backups initial_partitions must be between 1 and 1024")

            checkpoint_interval_secs = self.backups.get("checkpoint_interval_secs", 86400)
            if (
                not isinstance(checkpoint_interval_secs, int)
                or isinstance(checkpoint_interval_secs, bool)
                or checkpoint_interval_secs < 60
            ):
                raise ValueError("backups checkpoint_interval_secs must be at least 60")

            if self.backups.get("provider", "filesystem") not in {"filesystem", "cache"}:
                raise ValueError("backups provider must be 'filesystem' or 'cache'")

            names = set()
            for item in self.backups.get("items", []):
                if not isinstance(item, dict):
                    raise ValueError("backups items must be objects")
                name = item.get("name")
                if not isinstance(name, str) or not name.strip():
                    raise ValueError("backup name must not be empty")
                name = name.strip()
                if name == "primary":
                    raise ValueError("backup name 'primary' is reserved")
                if name in names:
                    raise ValueError("backup names must be unique")
                names.add(name)

        return self
