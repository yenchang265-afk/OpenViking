-- Provision before enabling oauth.backend=mysql. No existing SQLite data is
-- moved by switching backends; migrate grants or require reauthorization.
CREATE TABLE IF NOT EXISTS ov_oauth_records (
    service_name VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
    kind VARCHAR(16) COLLATE utf8mb4_bin NOT NULL,
    record_id VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
    payload JSON NOT NULL,
    expires_at BIGINT NOT NULL,
    used BOOLEAN NOT NULL DEFAULT FALSE,
    account_id VARCHAR(128) COLLATE utf8mb4_bin NULL,
    user_id VARCHAR(128) COLLATE utf8mb4_bin NULL,
    display_code VARCHAR(64) COLLATE utf8mb4_bin NULL,
    PRIMARY KEY (service_name, kind, record_id),
    KEY ix_ov_oauth_expiry (service_name, kind, expires_at),
    KEY ix_ov_oauth_owner (service_name, account_id, user_id),
    KEY ix_ov_oauth_display (service_name, kind, display_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
