//! Multipart upload planning for S3FS path-based writes.
//!
//! Pure helpers (no network) so part sizing and config validation can be unit-tested.

use std::collections::HashMap;

use crate::core::{ConfigValue, Error, Result};

const MIB: u64 = 1024 * 1024;
/// Objects at or below this size use a single PutObject.
pub(crate) const DEFAULT_MULTIPART_THRESHOLD_BYTES: u64 = 16 * MIB;
/// Default size of each UploadPart.
pub(crate) const DEFAULT_MULTIPART_PART_SIZE_BYTES: u64 = 8 * MIB;
/// S3 rejects non-final parts smaller than 5 MiB.
pub(crate) const MIN_PART_SIZE_BYTES: u64 = 5 * MIB;
/// S3 rejects parts larger than 5 GiB.
pub(crate) const MAX_PART_SIZE_BYTES: u64 = 5 * 1024 * MIB;
/// S3 allows at most 10,000 parts per upload.
pub(crate) const MAX_PARTS: u64 = 10_000;

/// Thresholds for choosing single PUT vs multipart, read from mount config.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct MultipartSettings {
    pub(crate) threshold_bytes: u64,
    pub(crate) part_size_bytes: u64,
}

impl Default for MultipartSettings {
    fn default() -> Self {
        Self {
            threshold_bytes: DEFAULT_MULTIPART_THRESHOLD_BYTES,
            part_size_bytes: DEFAULT_MULTIPART_PART_SIZE_BYTES,
        }
    }
}

impl MultipartSettings {
    /// Read `multipart_threshold_bytes` / `multipart_part_size_bytes`, applying defaults.
    pub(crate) fn from_config(config: &HashMap<String, ConfigValue>) -> Result<Self> {
        let defaults = Self::default();
        let threshold_bytes = positive_int(
            config,
            "multipart_threshold_bytes",
            defaults.threshold_bytes,
        )?;
        let part_size_bytes = positive_int(
            config,
            "multipart_part_size_bytes",
            defaults.part_size_bytes,
        )?;
        if !(MIN_PART_SIZE_BYTES..=MAX_PART_SIZE_BYTES).contains(&part_size_bytes) {
            return Err(Error::config(format!(
                "invalid multipart_part_size_bytes: {part_size_bytes} \
                 (must be between {MIN_PART_SIZE_BYTES} and {MAX_PART_SIZE_BYTES})"
            )));
        }
        Ok(Self {
            threshold_bytes,
            part_size_bytes,
        })
    }
}

fn positive_int(config: &HashMap<String, ConfigValue>, key: &str, default: u64) -> Result<u64> {
    let Some(value) = config.get(key) else {
        return Ok(default);
    };
    match value.as_int() {
        Some(n) if n > 0 => Ok(n as u64),
        _ => Err(Error::config(format!(
            "invalid {key}: expected a positive integer"
        ))),
    }
}

/// Part size that keeps an upload of `total` bytes within [`MAX_PARTS`].
pub(crate) fn effective_part_size(total: u64, configured: u64) -> u64 {
    configured.max(total.div_ceil(MAX_PARTS))
}

/// `(offset, len)` of each part for an upload of `total` bytes.
pub(crate) fn part_ranges(total: u64, part_size: u64) -> Vec<(u64, u64)> {
    (0..total)
        .step_by(part_size as usize)
        .map(|offset| (offset, part_size.min(total - offset)))
        .collect()
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

    #[test]
    fn settings_default_when_unset() {
        let settings = MultipartSettings::from_config(&HashMap::new()).unwrap();
        assert_eq!(settings, MultipartSettings::default());
        assert_eq!(settings.threshold_bytes, 16 * MIB);
        assert_eq!(settings.part_size_bytes, 8 * MIB);
    }

    #[test]
    fn settings_read_int_values() {
        let settings = MultipartSettings::from_config(&config(&[
            (
                "multipart_threshold_bytes",
                ConfigValue::Int(64 * MIB as i64),
            ),
            (
                "multipart_part_size_bytes",
                ConfigValue::Int(16 * MIB as i64),
            ),
        ]))
        .unwrap();
        assert_eq!(settings.threshold_bytes, 64 * MIB);
        assert_eq!(settings.part_size_bytes, 16 * MIB);
    }

    #[test]
    fn settings_reject_part_size_outside_s3_limits() {
        for bad in [MIN_PART_SIZE_BYTES - 1, MAX_PART_SIZE_BYTES + 1] {
            let result = MultipartSettings::from_config(&config(&[(
                "multipart_part_size_bytes",
                ConfigValue::Int(bad as i64),
            )]));
            assert!(matches!(result, Err(Error::Config(_))), "{bad}");
        }
    }

    #[test]
    fn settings_reject_non_positive_or_non_int_threshold() {
        for bad in [ConfigValue::Int(0), ConfigValue::String("big".to_string())] {
            let result =
                MultipartSettings::from_config(&config(&[("multipart_threshold_bytes", bad)]));
            assert!(matches!(result, Err(Error::Config(_))));
        }
    }

    #[test]
    fn effective_part_size_keeps_configured_size_within_part_limit() {
        assert_eq!(effective_part_size(1, 8 * MIB), 8 * MIB);
        assert_eq!(effective_part_size(MAX_PARTS * 8 * MIB, 8 * MIB), 8 * MIB);
    }

    #[test]
    fn effective_part_size_grows_past_part_limit() {
        let total = MAX_PARTS * 8 * MIB + 1;
        let size = effective_part_size(total, 8 * MIB);
        assert!(size > 8 * MIB);
        assert!(total.div_ceil(size) <= MAX_PARTS);
    }

    #[test]
    fn part_ranges_cover_total_with_short_last_part() {
        assert_eq!(part_ranges(0, 8), vec![]);
        assert_eq!(part_ranges(16, 8), vec![(0, 8), (8, 8)]);
        assert_eq!(part_ranges(17, 8), vec![(0, 8), (8, 8), (16, 1)]);
        assert_eq!(part_ranges(3, 8), vec![(0, 3)]);
    }
}
