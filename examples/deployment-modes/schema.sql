-- OpenViking MySQL/MariaDB schema for a new deployment using the stack examples.
-- Generated from image openviking:main-6e77b0add (version 0.5.4.dev244).
--
-- Run once, against an empty database, connected to that database.
-- It is not idempotent: a second run fails on existing tables.
-- Tiered AGFS tables (agfs_entries, agfs_git_entries) are created by the server
-- on first mount and are not listed here.
--
-- Sources are the image's own files. For a different image, regenerate this file
-- or check those sources for new files under changes/.

-- ======================================================================
-- Source: server/account_stores/sql/init.sql
-- ======================================================================

-- OpenViking MySQL account store initial schema.
-- Execute manually before starting a MySQL account-store deployment.
-- Table names are fixed and service_name isolates OpenViking deployments.

CREATE TABLE `ov_accounts` (
    account_pk BIGINT NOT NULL AUTO_INCREMENT,
    service_name VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    account_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    deletion_task_id VARCHAR(64) NULL,
    deletion_owner_account_id VARCHAR(255) COLLATE utf8mb4_bin NULL,
    deletion_owner_user_id VARCHAR(255) COLLATE utf8mb4_bin NULL,
    PRIMARY KEY (account_pk),
    CONSTRAINT uq_ov_accounts_account_identity UNIQUE (service_name, account_id),
    CONSTRAINT uq_ov_accounts_account_service_pk UNIQUE (service_name, account_pk),
    INDEX ix_ov_accounts_account_deletion (service_name, deletion_task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `ov_accounts_users` (
    user_pk BIGINT NOT NULL AUTO_INCREMENT,
    service_name VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    account_pk BIGINT NOT NULL,
    user_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    `role` VARCHAR(16) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    deletion_task_id VARCHAR(64) NULL,
    deletion_owner_account_id VARCHAR(255) COLLATE utf8mb4_bin NULL,
    deletion_owner_user_id VARCHAR(255) COLLATE utf8mb4_bin NULL,
    PRIMARY KEY (user_pk),
    CONSTRAINT fk_ov_accounts_user_account
        FOREIGN KEY (service_name, account_pk)
        REFERENCES `ov_accounts` (service_name, account_pk)
        ON DELETE CASCADE,
    CONSTRAINT uq_ov_accounts_user_identity
        UNIQUE (service_name, account_pk, user_id),
    CONSTRAINT uq_ov_accounts_user_service_pk UNIQUE (service_name, user_pk),
    CONSTRAINT uq_ov_accounts_user_account_pk
        UNIQUE (service_name, account_pk, user_pk),
    INDEX ix_ov_accounts_user_admin (service_name, account_pk, `role`),
    INDEX ix_ov_accounts_user_deletion (service_name, deletion_task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `ov_accounts_groups` (
    group_pk BIGINT NOT NULL AUTO_INCREMENT,
    service_name VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    account_pk BIGINT NOT NULL,
    group_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (group_pk),
    CONSTRAINT fk_ov_accounts_group_account
        FOREIGN KEY (service_name, account_pk)
        REFERENCES `ov_accounts` (service_name, account_pk)
        ON DELETE CASCADE,
    CONSTRAINT uq_ov_accounts_group_identity
        UNIQUE (service_name, account_pk, group_id),
    CONSTRAINT uq_ov_accounts_group_service_pk UNIQUE (service_name, group_pk),
    CONSTRAINT uq_ov_accounts_group_account_pk
        UNIQUE (service_name, account_pk, group_pk)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `ov_accounts_group_members` (
    service_name VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    account_pk BIGINT NOT NULL,
    group_pk BIGINT NOT NULL,
    user_pk BIGINT NOT NULL,
    PRIMARY KEY (service_name, account_pk, group_pk, user_pk),
    CONSTRAINT fk_ov_accounts_member_group
        FOREIGN KEY (service_name, account_pk, group_pk)
        REFERENCES `ov_accounts_groups` (service_name, account_pk, group_pk)
        ON DELETE CASCADE,
    CONSTRAINT fk_ov_accounts_member_user
        FOREIGN KEY (service_name, account_pk, user_pk)
        REFERENCES `ov_accounts_users` (service_name, account_pk, user_pk)
        ON DELETE CASCADE,
    INDEX ix_ov_accounts_member_user (service_name, account_pk, user_pk)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `ov_accounts_credentials` (
    credential_id VARCHAR(32) COLLATE ascii_bin NOT NULL,
    service_name VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    user_pk BIGINT NOT NULL,
    material TEXT COLLATE ascii_bin NOT NULL,
    lookup_digest VARCHAR(64) COLLATE ascii_bin NOT NULL,
    prefix VARCHAR(8) COLLATE ascii_bin NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT 0,
    version BIGINT NOT NULL DEFAULT 1,
    sequence BIGINT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    revoked_at DATETIME(6) NULL,
    active_user_pk BIGINT NULL,
    PRIMARY KEY (credential_id),
    CONSTRAINT fk_ov_accounts_credential_user
        FOREIGN KEY (service_name, user_pk)
        REFERENCES `ov_accounts_users` (service_name, user_pk)
        ON DELETE CASCADE,
    CONSTRAINT uq_ov_accounts_active_credential
        UNIQUE (service_name, active_user_pk),
    INDEX ix_ov_accounts_credential_lookup
        (service_name, lookup_digest, revoked, user_pk),
    INDEX ix_ov_accounts_credential_history
        (service_name, user_pk, revoked, sequence)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ======================================================================
-- Source: service/sql/task_store_init.sql
-- ======================================================================

-- OpenViking MySQL Task/Work store schema.
-- Provision this schema before selecting storage.task_store.provider=mysql.
-- For a custom table prefix, replace ov_tasks consistently in all tables,
-- indexes, constraints, and the foreign-key target.
-- Use at most 38 ASCII letters/digits/underscores, starting with a letter,
-- so all derived identifiers remain within MySQL's 64-character limit.

CREATE TABLE `ov_tasks` (
    task_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    task_type VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    status VARCHAR(16) COLLATE ascii_bin NOT NULL,
    created_at DOUBLE NOT NULL,
    updated_at DOUBLE NOT NULL,
    resource_id TEXT COLLATE utf8mb4_bin NULL,
    account_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    user_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    meta JSON NULL,
    stage VARCHAR(255) NULL,
    result JSON NULL,
    error TEXT NULL,
    auth JSON NULL,
    processing_seconds DOUBLE NULL,
    reject_if_active BOOLEAN NOT NULL DEFAULT 0,
    is_internal BOOLEAN NOT NULL DEFAULT 0,
    active_business_key VARBINARY(32) NULL,
    PRIMARY KEY (task_id),
    UNIQUE KEY uq_ov_tasks_active_business_key (active_business_key),
    KEY ix_ov_tasks_owner_created (account_id, user_id, created_at, task_id),
    KEY ix_ov_tasks_account_created (account_id, created_at, task_id),
    KEY ix_ov_tasks_created (created_at, task_id),
    KEY ix_ov_tasks_owner_status (account_id, user_id, status),
    KEY ix_ov_tasks_owner_internal_created
        (account_id, user_id, is_internal, created_at, task_id),
    KEY ix_ov_tasks_expiry (status, updated_at, task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC;

CREATE TABLE `ov_tasks_works` (
    task_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    work_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    account_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    user_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    queue_name VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    state VARCHAR(16) COLLATE ascii_bin NOT NULL,
    requeue_count INT NOT NULL DEFAULT 0,
    error TEXT NULL,
    errors JSON NULL,
    context_count INT NOT NULL DEFAULT 0,
    enqueued_at DOUBLE NOT NULL,
    started_at DOUBLE NULL,
    finished_at DOUBLE NULL,
    updated_at DOUBLE NOT NULL,
    PRIMARY KEY (task_id, work_id),
    CONSTRAINT fk_ov_tasks_works_task
        FOREIGN KEY (task_id) REFERENCES `ov_tasks` (task_id)
        ON DELETE CASCADE,
    KEY ix_ov_tasks_works_state (task_id, state),
    KEY ix_ov_tasks_works_queue (task_id, queue_name, state),
    KEY ix_ov_tasks_works_owner (account_id, user_id, task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC;

CREATE TABLE `ov_tasks_execution_events` (
    task_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    seq INT NOT NULL,
    recorded_at VARCHAR(64) COLLATE ascii_bin NOT NULL,
    kind VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    status VARCHAR(16) COLLATE ascii_bin NOT NULL,
    stage VARCHAR(128) NULL,
    operation TEXT NULL,
    error TEXT NULL,
    dropped_count INT NOT NULL DEFAULT 0,
    started_mid_task BOOLEAN NOT NULL DEFAULT 0,
    PRIMARY KEY (task_id, seq),
    CONSTRAINT fk_ov_tasks_execution_events_task
        FOREIGN KEY (task_id) REFERENCES `ov_tasks` (task_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC;

-- ======================================================================
-- Source: service/sql/001_watch_tasks.sql
-- ======================================================================

-- OpenViking MySQL Watch store schema.
-- Provision once before selecting storage.watch_store.provider=mysql.
-- For a custom storage.watch_store.params.table, replace ov_watch_tasks
-- consistently in table and index names.
-- Compatible with MySQL 5.7.

CREATE TABLE `ov_watch_tasks` (
    service_name VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    task_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    account_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    user_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    original_role VARCHAR(64) COLLATE ascii_bin NOT NULL,
    target_uri_hash CHAR(64) COLLATE ascii_bin NOT NULL,
    target_uri_key VARCHAR(768) COLLATE utf8mb4_bin NOT NULL,
    target_uri TEXT COLLATE utf8mb4_bin NULL,
    enabled BOOLEAN NOT NULL,
    deleted BOOLEAN NOT NULL DEFAULT 0,
    watch_interval DOUBLE NOT NULL,
    next_run_at DOUBLE NULL,
    current_run_id VARCHAR(255) COLLATE utf8mb4_bin NULL,
    run_started_at DOUBLE NULL,
    last_execution_time DOUBLE NULL,
    last_task_id VARCHAR(255) COLLATE utf8mb4_bin NULL,
    last_status VARCHAR(64) COLLATE ascii_bin NULL,
    last_error TEXT COLLATE utf8mb4_bin NULL,
    payload JSON NOT NULL,
    connector BOOLEAN NOT NULL DEFAULT 0,
    -- AES-GCM ciphertext under storage.watch_store.params.credential_encryption_key.
    auth_state MEDIUMTEXT COLLATE ascii_bin NULL,
    connector_states MEDIUMTEXT COLLATE ascii_bin NULL,
    created_at DOUBLE NOT NULL,
    updated_at DOUBLE NOT NULL,
    PRIMARY KEY (service_name, task_id),
    KEY ix_ov_watch_tasks_due (service_name, enabled, next_run_at),
    KEY ix_ov_watch_tasks_run (service_name, run_started_at),
    KEY ix_ov_watch_tasks_target (service_name, account_id, target_uri_hash),
    KEY ix_ov_watch_tasks_target_prefix
        (service_name(128), account_id(128), deleted, target_uri_key(384)),
    KEY ix_ov_watch_tasks_list
        (service_name(128), account_id(128), user_id(128), deleted, created_at, task_id),
    KEY ix_ov_watch_tasks_list_all
        (service_name, deleted, created_at, task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC;

-- ======================================================================
-- Source: server/account_stores/sql/changes/0001_account_user_list_indexes.sql
-- ======================================================================

-- Add indexes for account and user management list pagination.
--
-- These indexes support:
-- - list_accounts(): service-scoped ordering by created_at/account_id
-- - list_users_page(): active-user pagination by account and created_at/user_pk
-- - list_users_page(role_filter=...): active-user pagination by account, role,
--   and created_at/user_pk

ALTER TABLE `ov_accounts`
    ADD INDEX ix_ov_accounts_account_created
        (service_name, created_at, account_id);

ALTER TABLE `ov_accounts_users`
    ADD INDEX ix_ov_accounts_user_active_created
        (service_name, account_pk, deletion_task_id, created_at, user_pk),
    ADD INDEX ix_ov_accounts_user_role_active_created
        (service_name, account_pk, `role`, deletion_task_id, created_at, user_pk);

-- ======================================================================
-- Source: service/sql/changes/0001_task_store_service_name.sql
-- ======================================================================

-- Add service_name isolation to an existing OpenViking MySQL Task/Work store.
--
-- This script migrates tables created from openviking/service/sql/task_store_init.sql
-- before service_name was introduced. If the existing rows belong to a deployment
-- whose configured service_name is not 'openviking-server', replace that literal
-- consistently before running this script. For a custom table prefix, replace
-- ov_tasks consistently in all table and index names.

ALTER TABLE `ov_tasks_works`
    DROP FOREIGN KEY fk_ov_tasks_works_task;

ALTER TABLE `ov_tasks_execution_events`
    DROP FOREIGN KEY fk_ov_tasks_execution_events_task;

ALTER TABLE `ov_tasks`
    ADD COLUMN service_name VARCHAR(255) COLLATE utf8mb4_bin
        NOT NULL DEFAULT 'openviking-server' FIRST,
    ADD COLUMN resource_id_hash VARCHAR(64) COLLATE ascii_bin NULL AFTER resource_id,
    ADD COLUMN active_business_key_hex VARCHAR(64) COLLATE ascii_bin NULL
        AFTER active_business_key;

UPDATE `ov_tasks`
SET
    resource_id_hash = CASE
        WHEN resource_id IS NULL THEN NULL
        ELSE SHA2(resource_id, 256)
    END,
    active_business_key_hex = CASE
        WHEN active_business_key IS NULL THEN NULL
        ELSE LOWER(HEX(active_business_key))
    END;

ALTER TABLE `ov_tasks_works`
    ADD COLUMN service_name VARCHAR(255) COLLATE utf8mb4_bin
        NOT NULL DEFAULT 'openviking-server' FIRST;

ALTER TABLE `ov_tasks_execution_events`
    ADD COLUMN service_name VARCHAR(255) COLLATE utf8mb4_bin
        NOT NULL DEFAULT 'openviking-server' FIRST;

ALTER TABLE `ov_tasks`
    DROP INDEX uq_ov_tasks_active_business_key,
    DROP COLUMN active_business_key,
    CHANGE COLUMN active_business_key_hex active_business_key
        VARCHAR(64) COLLATE ascii_bin NULL,
    DROP INDEX ix_ov_tasks_owner_created,
    DROP INDEX ix_ov_tasks_account_created,
    DROP INDEX ix_ov_tasks_created,
    DROP INDEX ix_ov_tasks_owner_status,
    DROP INDEX ix_ov_tasks_owner_internal_created,
    DROP INDEX ix_ov_tasks_expiry,
    DROP PRIMARY KEY,
    ADD PRIMARY KEY (service_name, task_id),
    ADD UNIQUE KEY uq_ov_tasks_active_business_key
        (service_name, active_business_key),
    ADD KEY ix_ov_tasks_owner_created
        (service_name, account_id, user_id, created_at),
    ADD KEY ix_ov_tasks_account_created
        (service_name, account_id, created_at, task_id),
    ADD KEY ix_ov_tasks_created
        (service_name, created_at, task_id),
    ADD KEY ix_ov_tasks_owner
        (service_name, account_id, user_id),
    ADD KEY ix_ov_tasks_owner_internal_created
        (service_name, account_id, user_id, is_internal, created_at),
    ADD KEY ix_ov_tasks_acct_type_created
        (service_name, account_id, task_type, created_at),
    ADD KEY ix_ov_tasks_acct_status_created
        (service_name, account_id, status, created_at),
    ADD KEY ix_ov_tasks_acct_resource_created
        (service_name, account_id, resource_id_hash, created_at),
    ADD KEY ix_ov_tasks_acct_internal_created
        (service_name, account_id, is_internal, created_at),
    ADD KEY ix_ov_tasks_expiry
        (service_name, status, updated_at, task_id);

ALTER TABLE `ov_tasks_works`
    DROP INDEX ix_ov_tasks_works_state,
    DROP INDEX ix_ov_tasks_works_queue,
    DROP INDEX ix_ov_tasks_works_owner,
    DROP PRIMARY KEY,
    ADD PRIMARY KEY (service_name, task_id, work_id),
    ADD KEY ix_ov_tasks_works_state
        (service_name, task_id, state),
    ADD KEY ix_ov_tasks_works_queue
        (service_name, task_id, queue_name),
    ADD KEY ix_ov_tasks_works_owner
        (service_name, account_id, user_id);

ALTER TABLE `ov_tasks_execution_events`
    DROP PRIMARY KEY,
    ADD PRIMARY KEY (service_name, task_id, seq);

-- ======================================================================
-- Source: python -m openviking.server.shared_schema (usage, audit and OAuth)
-- OAuth tables are only used when oauth.enabled is true; unused otherwise.
-- ======================================================================


CREATE TABLE ov_oauth_records (
	service_name VARCHAR(64) NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	record_id VARCHAR(128) NOT NULL, 
	payload JSON NOT NULL, 
	expires_at BIGINT NOT NULL, 
	used BOOL NOT NULL, 
	account_id VARCHAR(128), 
	user_id VARCHAR(128), 
	display_code VARCHAR(64), 
	PRIMARY KEY (service_name, kind, record_id)
)CHARSET=utf8mb4 COLLATE utf8mb4_bin

;
CREATE INDEX ix_ov_oauth_display ON ov_oauth_records (service_name, kind, display_code);
CREATE INDEX ix_ov_oauth_expiry ON ov_oauth_records (service_name, kind, expires_at);
CREATE INDEX ix_ov_oauth_owner ON ov_oauth_records (service_name, account_id, user_id);

CREATE TABLE ov_request_audit (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	service_name VARCHAR(64) NOT NULL, 
	request_id VARCHAR(128), 
	account_id VARCHAR(128) NOT NULL, 
	user_id VARCHAR(128), 
	method VARCHAR(16) NOT NULL, 
	route TEXT NOT NULL, 
	api_type VARCHAR(128) NOT NULL, 
	status_code INTEGER NOT NULL, 
	duration_ms DOUBLE NOT NULL, 
	error_code TEXT, 
	error_message TEXT, 
	error_details TEXT, 
	created_at VARCHAR(40) NOT NULL, 
	PRIMARY KEY (id)
)CHARSET=utf8mb4 COLLATE utf8mb4_bin

;
CREATE INDEX ix_ov_audit_owner_created ON ov_request_audit (service_name, account_id, created_at, id);

CREATE TABLE ov_usage_buckets (
	service_name VARCHAR(64) NOT NULL, 
	bucket_id VARCHAR(64) NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	account_id VARCHAR(128) NOT NULL, 
	user_id VARCHAR(128) NOT NULL, 
	date_utc VARCHAR(10) NOT NULL, 
	dimensions JSON NOT NULL, 
	count BIGINT NOT NULL, 
	result_count BIGINT NOT NULL, 
	PRIMARY KEY (service_name, bucket_id)
)CHARSET=utf8mb4 COLLATE utf8mb4_bin

;
CREATE INDEX ix_ov_usage_owner_date ON ov_usage_buckets (service_name, account_id, date_utc);
