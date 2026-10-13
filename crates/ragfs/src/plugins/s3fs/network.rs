//! Timeout and retry settings for the S3FS client.
//!
//! Pure helpers (no network) so config parsing and SDK mapping can be unit-tested.
//! Without an attempt timeout a stalled S3 response blocks the calling thread
//! indefinitely, so every request is bounded by default.

use std::collections::HashMap;
use std::time::Duration;

use aws_sdk_s3::config::retry::RetryConfig;
use aws_sdk_s3::config::timeout::TimeoutConfig;

use crate::core::{ConfigValue, Error, Result};

/// Matches the AWS SDK default connect timeout.
pub(crate) const DEFAULT_CONNECT_TIMEOUT_MS: u64 = 3_100;
/// Per-attempt limit; generous enough for a single PUT at the multipart threshold.
pub(crate) const DEFAULT_ATTEMPT_TIMEOUT_MS: u64 = 60_000;
/// Matches the AWS SDK standard retry mode.
pub(crate) const DEFAULT_MAX_ATTEMPTS: u32 = 3;
/// Upper bound that keeps a misconfigured mount from retrying forever.
pub(crate) const MAX_MAX_ATTEMPTS: u32 = 10;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum RetryMode {
    Standard,
    Adaptive,
}

/// Timeout and retry behavior read from mount config.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct NetworkSettings {
    pub(crate) connect_timeout: Duration,
    /// Time to send the request and receive the first response byte.
    pub(crate) read_timeout: Option<Duration>,
    pub(crate) attempt_timeout: Duration,
    /// Total time across all attempts; unset means `max_attempts * attempt_timeout` bounds it.
    pub(crate) operation_timeout: Option<Duration>,
    pub(crate) max_attempts: u32,
    pub(crate) retry_mode: RetryMode,
}

impl Default for NetworkSettings {
    fn default() -> Self {
        Self {
            connect_timeout: Duration::from_millis(DEFAULT_CONNECT_TIMEOUT_MS),
            read_timeout: None,
            attempt_timeout: Duration::from_millis(DEFAULT_ATTEMPT_TIMEOUT_MS),
            operation_timeout: None,
            max_attempts: DEFAULT_MAX_ATTEMPTS,
            retry_mode: RetryMode::Standard,
        }
    }
}

impl NetworkSettings {
    /// Read `*_timeout_ms`, `max_attempts` and `retry_mode`, applying defaults.
    pub(crate) fn from_config(config: &HashMap<String, ConfigValue>) -> Result<Self> {
        let defaults = Self::default();
        let connect_timeout =
            optional_millis(config, "connect_timeout_ms")?.unwrap_or(defaults.connect_timeout);
        let read_timeout = optional_millis(config, "read_timeout_ms")?;
        let attempt_timeout =
            optional_millis(config, "attempt_timeout_ms")?.unwrap_or(defaults.attempt_timeout);
        let operation_timeout = optional_millis(config, "operation_timeout_ms")?;
        let max_attempts = match config.get("max_attempts") {
            None => defaults.max_attempts,
            Some(value) => match value.as_int() {
                Some(n) if (1..=MAX_MAX_ATTEMPTS as i64).contains(&n) => n as u32,
                _ => {
                    return Err(Error::config(format!(
                        "invalid max_attempts: expected an integer between 1 and {MAX_MAX_ATTEMPTS}"
                    )))
                }
            },
        };
        let retry_mode = match config.get("retry_mode") {
            None => defaults.retry_mode,
            Some(value) => match value.as_string() {
                Some("standard") => RetryMode::Standard,
                Some("adaptive") => RetryMode::Adaptive,
                _ => {
                    return Err(Error::config(
                        "invalid retry_mode: expected 'standard' or 'adaptive'",
                    ))
                }
            },
        };
        Ok(Self {
            connect_timeout,
            read_timeout,
            attempt_timeout,
            operation_timeout,
            max_attempts,
            retry_mode,
        })
    }

    pub(crate) fn timeout_config(&self) -> TimeoutConfig {
        let mut builder = TimeoutConfig::builder()
            .connect_timeout(self.connect_timeout)
            .operation_attempt_timeout(self.attempt_timeout);
        builder
            .set_read_timeout(self.read_timeout)
            .set_operation_timeout(self.operation_timeout);
        builder.build()
    }

    pub(crate) fn retry_config(&self) -> RetryConfig {
        let base = match self.retry_mode {
            RetryMode::Standard => RetryConfig::standard(),
            RetryMode::Adaptive => RetryConfig::adaptive(),
        };
        base.with_max_attempts(self.max_attempts)
    }
}

fn optional_millis(config: &HashMap<String, ConfigValue>, key: &str) -> Result<Option<Duration>> {
    let Some(value) = config.get(key) else {
        return Ok(None);
    };
    match value.as_int() {
        Some(n) if n > 0 => Ok(Some(Duration::from_millis(n as u64))),
        _ => Err(Error::config(format!(
            "invalid {key}: expected a positive integer (milliseconds)"
        ))),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use aws_sdk_s3::config::retry::RetryMode as SdkRetryMode;

    fn config(entries: &[(&str, ConfigValue)]) -> HashMap<String, ConfigValue> {
        entries
            .iter()
            .map(|(k, v)| (k.to_string(), v.clone()))
            .collect()
    }

    #[test]
    fn settings_default_when_unset() {
        let settings = NetworkSettings::from_config(&HashMap::new()).unwrap();
        assert_eq!(settings, NetworkSettings::default());
        assert_eq!(settings.connect_timeout, Duration::from_millis(3_100));
        assert_eq!(settings.attempt_timeout, Duration::from_secs(60));
        assert_eq!(settings.read_timeout, None);
        assert_eq!(settings.operation_timeout, None);
        assert_eq!(settings.max_attempts, 3);
        assert_eq!(settings.retry_mode, RetryMode::Standard);
    }

    #[test]
    fn settings_read_configured_values() {
        let settings = NetworkSettings::from_config(&config(&[
            ("connect_timeout_ms", ConfigValue::Int(1_000)),
            ("read_timeout_ms", ConfigValue::Int(2_000)),
            ("attempt_timeout_ms", ConfigValue::Int(5_000)),
            ("operation_timeout_ms", ConfigValue::Int(20_000)),
            ("max_attempts", ConfigValue::Int(5)),
            ("retry_mode", ConfigValue::String("adaptive".to_string())),
        ]))
        .unwrap();
        assert_eq!(settings.connect_timeout, Duration::from_secs(1));
        assert_eq!(settings.read_timeout, Some(Duration::from_secs(2)));
        assert_eq!(settings.attempt_timeout, Duration::from_secs(5));
        assert_eq!(settings.operation_timeout, Some(Duration::from_secs(20)));
        assert_eq!(settings.max_attempts, 5);
        assert_eq!(settings.retry_mode, RetryMode::Adaptive);
    }

    #[test]
    fn settings_reject_non_positive_or_non_int_timeouts() {
        for key in [
            "connect_timeout_ms",
            "read_timeout_ms",
            "attempt_timeout_ms",
            "operation_timeout_ms",
        ] {
            for bad in [
                ConfigValue::Int(0),
                ConfigValue::Int(-1),
                ConfigValue::String("fast".to_string()),
            ] {
                let result = NetworkSettings::from_config(&config(&[(key, bad.clone())]));
                assert!(matches!(result, Err(Error::Config(_))), "{key}={bad:?}");
            }
        }
    }

    #[test]
    fn settings_reject_max_attempts_out_of_range() {
        for bad in [0, MAX_MAX_ATTEMPTS as i64 + 1] {
            let result =
                NetworkSettings::from_config(&config(&[("max_attempts", ConfigValue::Int(bad))]));
            assert!(matches!(result, Err(Error::Config(_))), "{bad}");
        }
    }

    #[test]
    fn settings_reject_unknown_retry_mode() {
        let result = NetworkSettings::from_config(&config(&[(
            "retry_mode",
            ConfigValue::String("legacy".to_string()),
        )]));
        assert!(matches!(result, Err(Error::Config(_))));
    }

    #[test]
    fn timeout_config_maps_all_fields() {
        let settings = NetworkSettings {
            connect_timeout: Duration::from_millis(100),
            read_timeout: Some(Duration::from_millis(200)),
            attempt_timeout: Duration::from_millis(300),
            operation_timeout: Some(Duration::from_millis(400)),
            ..NetworkSettings::default()
        };
        let timeouts = settings.timeout_config();
        assert_eq!(timeouts.connect_timeout(), Some(Duration::from_millis(100)));
        assert_eq!(timeouts.read_timeout(), Some(Duration::from_millis(200)));
        assert_eq!(
            timeouts.operation_attempt_timeout(),
            Some(Duration::from_millis(300))
        );
        assert_eq!(
            timeouts.operation_timeout(),
            Some(Duration::from_millis(400))
        );
    }

    #[test]
    fn timeout_config_leaves_optional_timeouts_unset_by_default() {
        let timeouts = NetworkSettings::default().timeout_config();
        assert_eq!(timeouts.read_timeout(), None);
        assert_eq!(timeouts.operation_timeout(), None);
    }

    #[test]
    fn retry_config_maps_mode_and_attempts() {
        let standard = NetworkSettings::default().retry_config();
        assert_eq!(standard.mode(), SdkRetryMode::Standard);
        assert_eq!(standard.max_attempts(), 3);

        let adaptive = NetworkSettings {
            max_attempts: 6,
            retry_mode: RetryMode::Adaptive,
            ..NetworkSettings::default()
        }
        .retry_config();
        assert_eq!(adaptive.mode(), SdkRetryMode::Adaptive);
        assert_eq!(adaptive.max_attempts(), 6);
    }
}
