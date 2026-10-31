//! Optional provider-independent caching for RAGFS filesystems.
//!
//! This module is intentionally not installed by [`crate::MountableFS`] by
//! default. Callers opt in by wrapping an existing [`crate::FileSystem`] with
//! [`CachedFileSystem`].

mod envelope;
mod metrics;
#[cfg(test)]
mod multi_instance_tests;
mod policy;
#[cfg(test)]
mod stress_tests;
mod versions;
mod wrapper;

pub use metrics::{CacheMetrics, CacheMetricsSnapshot, CacheOperation, CacheOperationSnapshot};
pub use policy::{CacheDecision, CachePolicy, CacheTraversalMode, CacheTreeMode};
pub use wrapper::CachedFileSystem;
