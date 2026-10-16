//! Timeout and retry settings for S3 requests.
//!
//! Without explicit settings the AWS SDK bounds only connection setup, so a
//! stalled S3 endpoint can hang a request (and the caller's thread) forever.
//! These settings give every request a deadline and are read from mount config
//! so deployments can tune them per backend (LAN SeaweedFS vs WAN AWS/TOS).

use std::collections::HashMap;
use std::time::Duration;

use aws_sdk_s3::config::retry::RetryConfig;
use aws_sdk_s3::config::timeout::TimeoutConfig;

use crate::core::{ConfigValue, Error, Result};

/// Config keys understood by [`S3ResilienceSettings::from_config`].
#[cfg(test)]
pub(crate) const RESILIENCE_CONFIG_KEYS: &[&str] = &[
    "connect_timeout_ms",
    "read_timeout_ms",
    "operation_attempt_timeout_ms",
    "operation_timeout_ms",
    "metadata_attempt_timeout_ms",
    "metadata_operation_timeout_ms",
    "max_attempts",
    "retry_mode",
    "initial_backoff_ms",
    "max_backoff_ms",
    "max_concurrent_requests",
];

const MAX_ATTEMPTS_LIMIT: u32 = 10;
const MAX_CONCURRENT_REQUESTS_LIMIT: i64 = 10_000;

/// Client-side throttling strategy used by the SDK retry layer.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RetryMode {
    /// Exponential backoff with jitter.
    Standard,
    /// Standard plus client-side rate limiting when the service throttles.
    Adaptive,
}

/// Deadlines and retry policy applied to every S3 request.
///
/// Data operations (object bodies, copies, multipart) use the `operation_*`
/// timeouts; metadata operations (HEAD, LIST, DELETE, marker PUT) use the
/// tighter `metadata_*` timeouts so a hung metadata call fails fast.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct S3ResilienceSettings {
    /// Max time to establish a TCP/TLS connection.
    pub connect_timeout: Duration,
    /// Max wait for the first response byte after the request is sent.
    pub read_timeout: Duration,
    /// Per-attempt deadline for data operations.
    pub operation_attempt_timeout: Duration,
    /// Total deadline for data operations, including retries.
    pub operation_timeout: Duration,
    /// Per-attempt deadline for metadata operations.
    pub metadata_attempt_timeout: Duration,
    /// Total deadline for metadata operations, including retries.
    pub metadata_operation_timeout: Duration,
    /// Max attempts per request, including the first.
    pub max_attempts: u32,
    /// Retry strategy.
    pub retry_mode: RetryMode,
    /// Backoff before the first retry.
    pub initial_backoff: Duration,
    /// Upper bound on retry backoff.
    pub max_backoff: Duration,
    /// Max S3 requests in flight per mount; 0 means unlimited. A request that
    /// cannot start within `metadata_operation_timeout` fails with a timeout.
    pub max_concurrent_requests: usize,
}

impl Default for S3ResilienceSettings {
    fn default() -> Self {
        Self {
            // SDK default is 3.1s, which is tight for cross-region TLS.
            connect_timeout: Duration::from_millis(5_000),
            // Bounds a stalled connection: each attempt waits at most this long for
            // the response to start, so a hung backend fails in ~max_attempts x 20s
            // instead of minutes. Only time-to-first-byte; large transfers are not
            // limited by it (operation_attempt_timeout bounds them).
            read_timeout: Duration::from_millis(20_000),
            // Fits an 8 MiB multipart part at ~100 KB/s.
            operation_attempt_timeout: Duration::from_millis(120_000),
            operation_timeout: Duration::from_millis(300_000),
            metadata_attempt_timeout: Duration::from_millis(15_000),
            metadata_operation_timeout: Duration::from_millis(45_000),
            max_attempts: 3,
            retry_mode: RetryMode::Standard,
            initial_backoff: Duration::from_millis(1_000),
            max_backoff: Duration::from_millis(20_000),
            max_concurrent_requests: 128,
        }
    }
}

impl S3ResilienceSettings {
    /// Read timeout/retry keys from mount config, applying defaults.
    ///
    /// A default that is unset is clamped to the explicitly configured bound it
    /// must not exceed (e.g. lowering only `operation_timeout_ms` also lowers the
    /// default attempt timeout); two explicit values that conflict are rejected.
    pub fn from_config(config: &HashMap<String, ConfigValue>) -> Result<Self> {
        let d = Self::default();
        let operation_timeout = millis(config, "operation_timeout_ms", d.operation_timeout)?;
        let metadata_operation_timeout = millis(
            config,
            "metadata_operation_timeout_ms",
            d.metadata_operation_timeout,
        )?;
        let max_backoff = millis(config, "max_backoff_ms", d.max_backoff)?;
        let settings = Self {
            connect_timeout: millis(config, "connect_timeout_ms", d.connect_timeout)?,
            read_timeout: millis(config, "read_timeout_ms", d.read_timeout)?,
            operation_attempt_timeout: millis(
                config,
                "operation_attempt_timeout_ms",
                d.operation_attempt_timeout.min(operation_timeout),
            )?,
            operation_timeout,
            metadata_attempt_timeout: millis(
                config,
                "metadata_attempt_timeout_ms",
                d.metadata_attempt_timeout.min(metadata_operation_timeout),
            )?,
            metadata_operation_timeout,
            max_attempts: max_attempts(config, d.max_attempts)?,
            retry_mode: retry_mode(config, d.retry_mode)?,
            initial_backoff: millis(
                config,
                "initial_backoff_ms",
                d.initial_backoff.min(max_backoff),
            )?,
            max_backoff,
            max_concurrent_requests: max_concurrent_requests(config, d.max_concurrent_requests)?,
        };
        settings.validate()?;
        Ok(settings)
    }

    fn validate(&self) -> Result<()> {
        if self.operation_attempt_timeout > self.operation_timeout {
            return Err(Error::config(
                "operation_attempt_timeout_ms must not exceed operation_timeout_ms",
            ));
        }
        if self.metadata_attempt_timeout > self.metadata_operation_timeout {
            return Err(Error::config(
                "metadata_attempt_timeout_ms must not exceed metadata_operation_timeout_ms",
            ));
        }
        if self.initial_backoff > self.max_backoff {
            return Err(Error::config(
                "initial_backoff_ms must not exceed max_backoff_ms",
            ));
        }
        Ok(())
    }

    /// Client-level timeouts (data-operation class).
    pub fn timeout_config(&self) -> TimeoutConfig {
        TimeoutConfig::builder()
            .connect_timeout(self.connect_timeout)
            .read_timeout(self.read_timeout)
            .operation_attempt_timeout(self.operation_attempt_timeout)
            .operation_timeout(self.operation_timeout)
            .build()
    }

    /// SDK retry policy.
    pub fn retry_config(&self) -> RetryConfig {
        let base = match self.retry_mode {
            RetryMode::Standard => RetryConfig::standard(),
            RetryMode::Adaptive => RetryConfig::adaptive(),
        };
        base.with_max_attempts(self.max_attempts)
            .with_initial_backoff(self.initial_backoff)
            .with_max_backoff(self.max_backoff)
    }

    /// Apply timeouts and retries to an S3 client config builder.
    pub fn apply(&self, builder: aws_sdk_s3::config::Builder) -> aws_sdk_s3::config::Builder {
        builder
            .timeout_config(self.timeout_config())
            .retry_config(self.retry_config())
    }

    /// Per-operation override that swaps in the metadata-class deadlines.
    ///
    /// The SDK merges an override's timeout config with the client's, so
    /// connect/read timeouts and retries carry over unchanged.
    pub fn metadata_override(&self) -> aws_sdk_s3::config::Builder {
        aws_sdk_s3::config::Builder::default().timeout_config(
            TimeoutConfig::builder()
                .operation_attempt_timeout(self.metadata_attempt_timeout)
                .operation_timeout(self.metadata_operation_timeout)
                .build(),
        )
    }
}

fn millis(config: &HashMap<String, ConfigValue>, key: &str, default: Duration) -> Result<Duration> {
    let Some(value) = config.get(key) else {
        return Ok(default);
    };
    match value.as_int() {
        Some(n) if n > 0 => Ok(Duration::from_millis(n as u64)),
        _ => Err(Error::config(format!(
            "invalid {key}: expected a positive integer (milliseconds)"
        ))),
    }
}

fn max_attempts(config: &HashMap<String, ConfigValue>, default: u32) -> Result<u32> {
    let Some(value) = config.get("max_attempts") else {
        return Ok(default);
    };
    match value.as_int() {
        Some(n) if (1..=MAX_ATTEMPTS_LIMIT as i64).contains(&n) => Ok(n as u32),
        _ => Err(Error::config(format!(
            "invalid max_attempts: expected an integer between 1 and {MAX_ATTEMPTS_LIMIT}"
        ))),
    }
}

fn max_concurrent_requests(config: &HashMap<String, ConfigValue>, default: usize) -> Result<usize> {
    let Some(value) = config.get("max_concurrent_requests") else {
        return Ok(default);
    };
    match value.as_int() {
        Some(n) if (0..=MAX_CONCURRENT_REQUESTS_LIMIT).contains(&n) => Ok(n as usize),
        _ => Err(Error::config(format!(
            "invalid max_concurrent_requests: expected an integer between 0 (unlimited) \
             and {MAX_CONCURRENT_REQUESTS_LIMIT}"
        ))),
    }
}

fn retry_mode(config: &HashMap<String, ConfigValue>, default: RetryMode) -> Result<RetryMode> {
    let Some(value) = config.get("retry_mode") else {
        return Ok(default);
    };
    match value.as_string() {
        Some("standard") => Ok(RetryMode::Standard),
        Some("adaptive") => Ok(RetryMode::Adaptive),
        _ => Err(Error::config(
            "invalid retry_mode: expected \"standard\" or \"adaptive\"",
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn config(entries: &[(&str, ConfigValue)]) -> HashMap<String, ConfigValue> {
        entries
            .iter()
            .map(|(k, v)| (k.to_string(), v.clone()))
            .collect()
    }

    fn assert_config_err(entries: &[(&str, ConfigValue)]) {
        let result = S3ResilienceSettings::from_config(&config(entries));
        assert!(matches!(result, Err(Error::Config(_))), "{entries:?}");
    }

    #[test]
    fn defaults_when_unset() {
        let settings = S3ResilienceSettings::from_config(&HashMap::new()).unwrap();
        assert_eq!(settings, S3ResilienceSettings::default());
        assert_eq!(settings.connect_timeout, Duration::from_secs(5));
        assert_eq!(settings.read_timeout, Duration::from_secs(20));
        assert_eq!(settings.operation_attempt_timeout, Duration::from_secs(120));
        assert_eq!(settings.metadata_operation_timeout, Duration::from_secs(45));
        assert_eq!(settings.max_attempts, 3);
        assert_eq!(settings.retry_mode, RetryMode::Standard);
    }

    #[test]
    fn reads_overrides() {
        let settings = S3ResilienceSettings::from_config(&config(&[
            ("connect_timeout_ms", ConfigValue::Int(250)),
            ("read_timeout_ms", ConfigValue::Int(500)),
            ("operation_attempt_timeout_ms", ConfigValue::Int(1_000)),
            ("operation_timeout_ms", ConfigValue::Int(3_000)),
            ("metadata_attempt_timeout_ms", ConfigValue::Int(100)),
            ("metadata_operation_timeout_ms", ConfigValue::Int(300)),
            ("max_attempts", ConfigValue::Int(5)),
            ("retry_mode", ConfigValue::String("adaptive".to_string())),
            ("initial_backoff_ms", ConfigValue::Int(10)),
            ("max_backoff_ms", ConfigValue::Int(20)),
        ]))
        .unwrap();
        assert_eq!(settings.connect_timeout, Duration::from_millis(250));
        assert_eq!(settings.read_timeout, Duration::from_millis(500));
        assert_eq!(settings.operation_attempt_timeout, Duration::from_secs(1));
        assert_eq!(settings.operation_timeout, Duration::from_secs(3));
        assert_eq!(
            settings.metadata_attempt_timeout,
            Duration::from_millis(100)
        );
        assert_eq!(
            settings.metadata_operation_timeout,
            Duration::from_millis(300)
        );
        assert_eq!(settings.max_attempts, 5);
        assert_eq!(settings.retry_mode, RetryMode::Adaptive);
        assert_eq!(settings.initial_backoff, Duration::from_millis(10));
        assert_eq!(settings.max_backoff, Duration::from_millis(20));
    }

    #[test]
    fn rejects_non_positive_or_non_int_timeouts() {
        for key in RESILIENCE_CONFIG_KEYS.iter().filter(|k| k.ends_with("_ms")) {
            assert_config_err(&[(key, ConfigValue::Int(0))]);
            assert_config_err(&[(key, ConfigValue::Int(-1))]);
            assert_config_err(&[(key, ConfigValue::String("1s".to_string()))]);
        }
    }

    #[test]
    fn rejects_max_attempts_out_of_range() {
        assert_config_err(&[("max_attempts", ConfigValue::Int(0))]);
        assert_config_err(&[("max_attempts", ConfigValue::Int(11))]);
        assert_config_err(&[("max_attempts", ConfigValue::Bool(true))]);
    }

    #[test]
    fn reads_max_concurrent_requests() {
        assert_eq!(S3ResilienceSettings::default().max_concurrent_requests, 128);
        for n in [0, 1, 512] {
            let settings = S3ResilienceSettings::from_config(&config(&[(
                "max_concurrent_requests",
                ConfigValue::Int(n),
            )]))
            .unwrap();
            assert_eq!(settings.max_concurrent_requests, n as usize);
        }
        assert_config_err(&[("max_concurrent_requests", ConfigValue::Int(-1))]);
        assert_config_err(&[("max_concurrent_requests", ConfigValue::Int(10_001))]);
    }

    #[test]
    fn rejects_unknown_retry_mode() {
        assert_config_err(&[("retry_mode", ConfigValue::String("aggressive".to_string()))]);
    }

    #[test]
    fn rejects_attempt_timeout_above_operation_timeout() {
        assert_config_err(&[
            ("operation_attempt_timeout_ms", ConfigValue::Int(2_000)),
            ("operation_timeout_ms", ConfigValue::Int(1_000)),
        ]);
        assert_config_err(&[
            ("metadata_attempt_timeout_ms", ConfigValue::Int(2_000)),
            ("metadata_operation_timeout_ms", ConfigValue::Int(1_000)),
        ]);
    }

    #[test]
    fn clamps_unset_defaults_to_explicit_upper_bounds() {
        let settings = S3ResilienceSettings::from_config(&config(&[
            ("operation_timeout_ms", ConfigValue::Int(10_000)),
            ("metadata_operation_timeout_ms", ConfigValue::Int(2_000)),
            ("max_backoff_ms", ConfigValue::Int(200)),
        ]))
        .unwrap();
        assert_eq!(settings.operation_attempt_timeout, Duration::from_secs(10));
        assert_eq!(settings.metadata_attempt_timeout, Duration::from_secs(2));
        assert_eq!(settings.initial_backoff, Duration::from_millis(200));
    }

    #[test]
    fn rejects_initial_backoff_above_max_backoff() {
        assert_config_err(&[
            ("initial_backoff_ms", ConfigValue::Int(500)),
            ("max_backoff_ms", ConfigValue::Int(100)),
        ]);
    }

    #[test]
    fn sdk_configs_carry_settings() {
        let settings = S3ResilienceSettings::default();
        let timeouts = settings.timeout_config();
        assert_eq!(timeouts.connect_timeout(), Some(settings.connect_timeout));
        assert_eq!(timeouts.read_timeout(), Some(settings.read_timeout));
        assert_eq!(
            timeouts.operation_attempt_timeout(),
            Some(settings.operation_attempt_timeout)
        );
        assert_eq!(
            timeouts.operation_timeout(),
            Some(settings.operation_timeout)
        );

        let retry = settings.retry_config();
        assert_eq!(retry.max_attempts(), 3);
        assert_eq!(retry.initial_backoff(), settings.initial_backoff);
        assert_eq!(retry.max_backoff(), settings.max_backoff);

        let override_cfg = settings.metadata_override().build();
        let meta = override_cfg.timeout_config().unwrap();
        assert_eq!(
            meta.operation_attempt_timeout(),
            Some(settings.metadata_attempt_timeout)
        );
        assert_eq!(
            meta.operation_timeout(),
            Some(settings.metadata_operation_timeout)
        );
    }
}
