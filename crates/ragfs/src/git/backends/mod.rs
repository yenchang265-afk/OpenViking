//! Git storage backends

pub mod agfs;
pub mod local;

#[cfg(feature = "s3")]
pub mod s3;

pub use agfs::{AgfsIndexStore, AgfsObjectStore, AgfsRefStore};
pub use local::{LocalObjectStore, LocalRefStore};

#[cfg(feature = "s3")]
pub use s3::{CasMode, S3Config, S3ObjectStore, S3RefStore};
