"""Startup checks for replicas whose workspace may be discarded at any time."""


def validate_shared_deployment(server, config):
    if server.deployment_mode != "shared":
        return
    storage = config.storage
    agfs = storage.agfs
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    require(agfs.backend == "s3", "storage.agfs.backend must be s3")
    require(
        agfs.s3.cache_enabled is False,
        "storage.agfs.s3.cache_enabled must be false to avoid per-replica metadata caches",
    )
    require(
        config.cache is not None and config.cache.provider == "redis",
        "cache.provider must be redis",
    )
    require(agfs.queuefs.backend == "cache", "storage.agfs.queuefs.backend must be cache")
    require(agfs.queuefs.mode == "shared", "storage.agfs.queuefs.mode must be shared")
    require(
        agfs.queuefs.recover_stale_sec > 0,
        "storage.agfs.queuefs.recover_stale_sec must be positive; never recover all live work at replica startup",
    )
    require(agfs.pathlock.provider == "cache", "storage.agfs.pathlock.provider must be cache")
    require(
        agfs.cachefs.backend == "cache" and agfs.cachefs.multi_instance,
        "storage.agfs.cachefs must use backend=cache and multi_instance=true",
    )
    require(
        storage.vectordb.backend in {"http", "opengauss", "elasticsearch"},
        "storage.vectordb must use a remote backend",
    )
    require(storage.task_store.provider == "mysql", "storage.task_store.provider must be mysql")
    require(server.account_store.provider == "mysql", "server.account_store.provider must be mysql")
    require(server.get_effective_auth_mode() == "api_key", "server.auth_mode must be api_key")
    require(
        server.transfer_tokens.provider == "redis", "server.transfer_tokens.provider must be redis"
    )
    require(
        server.temp_upload.default_mode == "shared",
        "server.temp_upload.default_mode must be shared",
    )
    require(
        not config.oauth.enabled or config.oauth.backend == "mysql",
        "enabled OAuth requires oauth.backend=mysql",
    )
    usage = server.observability.usage_audit
    require(
        not usage.enabled or usage.backend == "mysql",
        "enabled usage/audit requires server.observability.usage_audit.backend=mysql",
    )
    require(not config.gateway.enabled, "run the gateway separately with shared storage")
    require(not server.with_bot, "run VikingBot separately")
    require(
        not config.enable_watch_scheduler,
        "enable_watch_scheduler must be false; resource watches are unavailable in shared mode",
    )
    require(
        not agfs.tiered.enabled or agfs.tiered.backend == "mysql",
        "enabled tiered storage requires a mysql backend",
    )
    require(not agfs.backups, "shared mode does not yet support multi-write backup configurations")
    require(
        not config.git.enabled or config.git.backend in {"s3", "agfs"},
        "enabled Git version storage must use a shared s3 or agfs backend",
    )
    encryption = config.encryption
    # Saved credentials (durable tasks, Connector watches) are encrypted even when
    # file encryption is disabled, so every replica needs the same root key.
    if encryption.provider == "local":
        require(
            bool(encryption.local.root_key),
            "local encryption requires an explicit shared encryption.local.root_key "
            "(saved credentials are encrypted even when encryption.enabled is false)",
        )
    if errors:
        raise ValueError("Invalid shared deployment configuration:\n- " + "\n- ".join(errors))
